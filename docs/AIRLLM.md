# AirLLM — modo profundo (/deep)

AirLLM ejecuta modelos que no caben en la VRAM cargando el modelo capa a capa desde disco. El precio es la latencia: cada token generado relee todas las capas, así que el disco es el cuello de botella (lo advierte la propia documentación del proyecto). En Jarvis es el segundo backend de inferencia, **nunca** el principal:

* Ollama: consultas normales (`/ask`), clasificación, RAG habitual.
* AirLLM: solo `/deep`, tareas profundas sin urgencia, vía cola de trabajos.

## Arquitectura

```mermaid
flowchart LR
    TG[Telegram /deep] --> OC[OpenClaw + skill jarvis-rag]
    OC -->|POST /v1/rag/deep-query| API[Jarvis API]
    API -->|Job queued 202| OC
    API -->|enqueue deep_rag_query| REDIS[(Redis/arq)]
    REDIS --> W[jarvis-worker]
    W -->|retrieval híbrido| QD[(Qdrant)]
    W -->|/v1/chat/completions| AIR[airllm-service :11500]
    AIR -->|capas desde disco| DISK[(/srv/jarvis/models/airllm)]
    W -->|resultado en job| PG[(PostgreSQL)]
    OC -->|jarvis_job_result| API
```

* `services/airllm/`: servicio FastAPI independiente con su propio entorno `uv` (versión fijada `airllm==2.11.0`, `torch==2.6.0+cu124` — la última rama de torch con soporte Pascal/GTX 1070). Escucha solo en `127.0.0.1:11500`.
* `packages/inference/airllm.py`: `AirLLMProvider` implementa la interfaz `InferenceProvider` contra la API OpenAI-compatible del servicio; el dominio nunca importa el SDK de AirLLM.
* La consulta profunda **no** pasa por la petición HTTP de la API: `POST /v1/rag/deep-query` devuelve un trabajo (HTTP 202) y el worker la ejecuta en segundo plano, de modo que Telegram y la API nunca se bloquean. El resultado se recoge con `GET /v1/jobs/{id}` (herramienta `jarvis_job_result`).

## Servicio airllm-service

| Endpoint | Uso |
|---|---|
| `GET /health` | estado (`no_model`, `checking`, `loading`, `ready`, `error`), dispositivo, disco, métricas de la última generación |
| `GET /v1/models` | modelo configurado |
| `POST /v1/chat/completions` | generación (OpenAI-compatible, sin streaming) |

Protecciones integradas:

* Comprueba el espacio libre **antes** de descargar: estima el tamaño real del modelo vía metadatos de Hugging Face y exige `tamaño × 2.2 + AIRLLM_MIN_FREE_GB` libres (original + shards por capas + margen).
* Rechaza descargas mayores que `AIRLLM_MAX_MODEL_DOWNLOAD_GB` (12 GiB por defecto): sin disco secundario no se bajan modelos de cientos de GiB.
* Concurrencia de generación 1 (lock) + cola corta (`AIRLLM_QUEUE_MAX_PENDING=2`); si está llena responde 503 con `Retry-After`.
* Timeout de generación configurable (`AIRLLM_GENERATION_TIMEOUT_SECONDS`, 1800 s por defecto).
* Carga del modelo en segundo plano: el servicio responde `/health` desde el primer segundo y systemd lo reinicia si cae (`Restart=on-failure`); tras un reinicio del servidor vuelve a cargar el modelo solo.
* Métricas por generación: duración, tokens de prompt y salida, tokens/s y RSS, en `/health` y en logs JSON (`/srv/jarvis/logs/airllm.log`).

Limitación conocida: una generación ya lanzada no puede abortarse (el bucle de capas de AirLLM no expone cancelación); la cancelación de trabajos (`/cancel`) surte efecto mientras el trabajo espera en cola, y el timeout corta la espera del cliente.

## Configuración (`/srv/jarvis/app/.env`)

| Variable | Significado |
|---|---|
| `AIRLLM_ENABLED` | habilita el modo profundo en API y worker |
| `AIRLLM_MODEL` | repo de Hugging Face a servir por capas |
| `AIRLLM_MODELS_DIR` | almacén de shards (`/srv/jarvis/models/airllm`) |
| `AIRLLM_DEVICE` | `cuda:0` en este equipo. La decisión anterior (`cpu`) resultó inviable con prompts RAG reales: el prefill de ~1.800 tokens en CPU fp32 tarda ~50 min por sí solo y toda consulta `/deep` moría por timeout (medido 2026-07-15, dos fallos reales con 504). En GPU el prefill es una sola pasada (~2 min) y cada token cuesta ~13 s |
| `AIRLLM_RELEASE_OLLAMA_VRAM` | convivencia en la GTX 1070 de 8 GiB: antes de cada generación deep el worker descarga de VRAM los modelos residentes de Ollama (`keep_alive=0`) y al terminar los recarga (`keep_alive=-1`); si detecta que un modelo quedó con offload parcial CPU/GPU lo recarga limpio. El servicio AirLLM libera su caché CUDA tras cada generación (en reposo retiene ~106 MiB). Sin esto, el prefill deep necesita ~3,4 GiB y provoca CUDA OOM con Ollama residente (5,3 GiB), o degrada Ollama a offload parcial permanente |
| `AIRLLM_COMPRESSION` | vacío, `4bit` u `8bit` (requiere bitsandbytes compatible; no soportado en Pascal — ver benchmark) |
| `AIRLLM_MAX_SEQ_LEN` | contexto máximo del modelo cargado |
| `AIRLLM_MIN_FREE_GB` / `AIRLLM_MAX_MODEL_DOWNLOAD_GB` | frenos de disco |
| `AIRLLM_TIMEOUT_SECONDS` | timeout del cliente (API/worker) hacia el servicio |

## Instalación

```bash
scripts/deploy            # sincroniza el código a /srv/jarvis/app
scripts/install-airllm    # venv aislado + unidad systemd airllm.service
curl -s http://127.0.0.1:11500/health | jq   # esperar status=ready
```

## Selección de modelo

Procedimiento obligatorio antes de cambiar `AIRLLM_MODEL`:

1. Calcular el espacio: tamaño del repo HF × 2.2 + 15 GiB de margen.
2. Comprobar `jarvis_disk` / `df -h /srv/jarvis`.
3. Estimar el tiempo de preparación (descarga + partición por capas: minutos a horas).
4. Probar primero con un modelo pequeño y medir con `scripts/benchmark-airllm`.
5. Documentar el resultado en `docs/benchmarks/`.

Estado actual del hardware (SSD raíz de 114 GiB, sin disco secundario): validado con `NousResearch/Meta-Llama-3.1-8B-Instruct` en fp16 (16 GiB, no cabe en los 8 GiB de VRAM: caso de uso legítimo de AirLLM). Requisitos de compatibilidad aprendidos por la vía dura: el checkpoint debe ser safetensors **multi-shard** con `model.safetensors.index.json` y **sin tied embeddings** (TinyLlama-1.1B falla por lo primero; Llama-3.2 1B/3B por lo segundo). Los modelos realmente "profundos" (70B) exigen ~140 GiB solo de shards: **quedan bloqueados hasta montar un disco dedicado en `/srv/jarvis/models`**, tal como prevé el diseño. Los resultados medidos y las conclusiones honestas de latencia están en `docs/benchmarks/` y resumidos en `docs/BENCHMARKS.md`: AirLLM en este equipo **no** es interactivo (~0.076 tok/s en generación) y solo tiene sentido detrás de la cola. Una consulta `/deep` realista (contexto RAG de ~1.800 tokens, 128 tokens de respuesta) tarda ~30 min en GPU; en CPU superaba los timeouts y fallaba siempre.

## Convivencia con Ollama en una sola GPU

La GTX 1070 (8 GiB) la comparte con Ollama, que es el backend principal y vive residente con `keep_alive=-1`. Medido en este equipo: el prefill deep necesita hasta 3,4 GiB de VRAM y el modelo de Ollama 5,3 GiB — no caben a la vez (CUDA OOM), y si Ollama carga mientras AirLLM retiene caché, queda **degradado a offload parcial CPU/GPU de forma permanente**. La solución tiene dos mitades:

* Worker (`AIRLLM_RELEASE_OLLAMA_VRAM=true`): antes de cada `deep_rag_query` llama a `OllamaProvider.release_vram()` (descarga todos los modelos residentes y recuerda cuáles eran) y al terminar —éxito o error— llama a `warm()` para recargarlos; `warm()` detecta cargas degradadas (`size_vram < size` en `/api/ps`) y las recarga limpias.
* Worker, guardián de VRAM: mientras dura la consulta profunda, un task asíncrono desaloja cada 20 s cualquier modelo que Ollama haya cargado entretanto (p. ej. por un `/ask` concurrente). Los modelos desalojados se acumulan en la lista que `warm()` restaura al final.
* Worker, reintento: si la generación falla (típicamente `CUDA out of memory` por la ventana de intrusión, ver abajo), desaloja de nuevo y reintenta la consulta una vez; el `job_timeout` de arq (7500 s) cubre ambos intentos.
* Servicio AirLLM: ejecuta `torch.cuda.empty_cache()` tras cada generación, dejando ~106 MiB residentes, de modo que Ollama recupera la GPU completa.

Por qué no basta con "reservar" VRAM: se probó reservar el pico (4 GiB) al inicio de cada generación vía el caching allocator de torch, pero AirLLM llama a `torch.cuda.empty_cache()` internamente en su bucle de capas (`airllm/utils.py`), lo que devuelve al driver cualquier bloque cacheado no asignado — la reserva se evapora en el primer barrido. Como AirLLM asigna VRAM de forma incremental durante toda la generación (~30 min, con picos de ~900 MiB para los logits), una carga concurrente de Ollama puede robarle el hueco en cualquier momento: de ahí el guardián + reintento.

Ventana conocida: un `/ask` durante una generación deep carga su modelo (degradado con offload parcial si hay poca VRAM), responde, y el guardián lo desaloja en ≤20 s; los `/ask` siguientes dentro de la ventana pagan recarga en frío. Si la intrusión llegó a tumbar la generación, el reintento la recupera a costa de repetirla. Con `AIRLLM_DEVICE=cpu` el mecanismo puede desactivarse poniendo `AIRLLM_RELEASE_OLLAMA_VRAM=false`.
