# Selección automática de modelo Ollama por VRAM

`scripts/select-models` detecta la VRAM total de la GPU NVIDIA
(`nvidia-smi --query-gpu=memory.total`; sin GPU o sin `nvidia-smi` → `0`,
nivel `cpu`) y escribe de forma idempotente en `.env`:
`OLLAMA_PRIMARY_MODEL`, `OLLAMA_POWERFUL_MODEL`, `OLLAMA_CONTEXT_LENGTH` y
`JARVIS_MODEL_TIER`. Lo ejecuta `scripts/quickstart` en cada arranque; también
se puede ejecutar suelto para recalcular tras un cambio de GPU o para
descargar los modelos elegidos con `--pull`.

**Solo el nivel `vram_7000` está benchmarkeado** (`docs/BENCHMARKS.md`, GTX
1070, 8192 MiB VRAM total, VRAM libre real ≈ 7500 MiB tras el sistema
operativo). Es el único par (`qwen2.5:7b` / `llama3.1:8b`) con evidencia
medida de tool calling nativo y de rechazo a responder sin evidencia
suficiente en el contexto RAG: **no lo cambies** sin repetir ese benchmark
con `scripts/benchmark-models`. El resto de niveles son una extrapolación
razonada del mismo criterio (modelo más grande cuanta más VRAM total hay,
manteniendo margen para el sistema operativo y el resto del stack), sin
validar todavía en hardware real.

## Franjas (VRAM total, MiB)

| Nivel (`JARVIS_MODEL_TIER`) | VRAM total | `OLLAMA_PRIMARY_MODEL` | `OLLAMA_POWERFUL_MODEL` | `OLLAMA_CONTEXT_LENGTH` |
|---|---|---|---|---|
| `cpu` | sin GPU NVIDIA (`0`) | `qwen2.5:3b` | `qwen2.5:3b` | 8192 |
| `vram_lt_7000` | < 7000 | `qwen2.5:3b` | `qwen2.5:7b` | 16384 |
| `vram_7000` | ≥ 7000, < 11000 | `qwen2.5:7b` | `llama3.1:8b` | 32768 |
| `vram_11000` | ≥ 11000, < 15000 | `qwen2.5:7b` | `qwen2.5:14b` | 32768 |
| `vram_15000` | ≥ 15000, < 21000 | `qwen2.5:14b` | `qwen2.5:14b` | 32768 |
| `vram_21000` | ≥ 21000, < 38000 | `gemma4:26b-a4b-it-qat` | `gemma4:26b-a4b-it-qat` | 65536 |
| `vram_38000` | ≥ 38000, < 47000 | `qwen2.5:14b` | `qwen2.5:32b` | 32768 |
| `vram_47000` | ≥ 47000 | `qwen2.5:32b` | `qwen2.5:72b` | 32768 |

> ⚠️ Medidos en hardware real: `vram_7000` (GTX 1070, benchmark completo) y
> `vram_21000` (NVIDIA L4, ver abajo). El resto: úsalos como punto de partida
> razonable y valida con `scripts/benchmark-models` antes de confiar en ellos.

### `vram_21000`: NVIDIA L4 23 GB (2026-09-15)

Contexto 32768, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, Ollama 0.34.
Prueba de herramientas con las de Jarvis vía `/v1/chat/completions` (la API que usa
OpenClaw): pedir un resumen en PDF, preguntar por la documentación y charlar.

| Modelo | En GPU | Generación | Herramientas |
|---|---|---|---|
| `qwen2.5:32b` (anterior) | 24 GB, 10 % CPU | 6,9 tok/s | ✅ |
| `qwen3.6:35b-a3b` (MoE, 3B activos) | 22 GB, 7 % CPU | 49,7 tok/s | ✅ PDF y RAG; en la charla agotó 400 tokens razonando sin responder |
| **`gemma4:26b-a4b-it-qat`** (MoE, 4B activos) | **14 GB, 100 % GPU** | **70,4 tok/s** | ✅ las tres |

Gemma 4 razona por defecto: la API de RAG lo desactiva con `think: false` y OpenClaw
con `reasoning_effort: "none"`. Deja además ~8 GB libres para embeddings y reranker.

**Contexto de 64k (2026-10-04).** OpenClaw reserva una cuarta parte de la ventana para
compactar (8.192 tokens con 32k) y el prompt de Jarvis (instrucciones, memoria y
herramientas) ya ronda los 24.000 tokens: con 32k pasaba el umbral en cada mensaje y,
tras cada respuesta, hacía un volcado de memoria y una compactación (dos llamadas más a
Gemma, 40-60 s de GPU). Además la compactación reescribe el historial e invalida la caché
de prompt de Ollama, así que el turno siguiente vuelve a procesar el prompt entero. Con
65536 no compacta en una demo entera, Gemma ocupa 18,5 GB (0,6 GB más que con 32k) y los
turnos sencillos pasan de ~50 s a ~10 s (`scripts/ensayo-demo`, docs/demo/GUION.md). La
primera respuesta tras reiniciar Ollama u OpenClaw sigue tardando 1-4 minutos: procesa el
prompt sin caché (~250 tok/s en la L4).

### Presupuesto de VRAM en la L4 (2026-10-04)

Medido con `nvidia-smi` y el registro de carga de Ollama, con 64k de contexto:

| Qué | VRAM | Cómo se ahorra ya |
|---|---|---|
| Pesos de `gemma4:26b-a4b-it-qat` | 13,4 GB | Cuantizado a 4 bits (Q4_0) con QAT, entrenado para esa precisión: en BF16 serían ~50 GB |
| Caché KV: capas globales (65.536 celdas) | 2,7 GB | En `q8_0` (`OLLAMA_KV_CACHE_TYPE`), la mitad que en FP16; la comparten las 4 conversaciones paralelas (`OLLAMA_NUM_PARALLEL`) |
| Caché KV: capas de ventana deslizante (1.536 celdas) | 0,6 GB | 25 de las 30 capas de Gemma 4 solo miran 1.024 tokens atrás |
| Búferes de cálculo de Ollama | 1,3 GB al cargar | — |
| **Gemma, al cargar → tras una tarde de uso** | **18,4 → 19,8 GB** | |
| `embeddinggemma` (memoria de OpenClaw) | 0,9 GB | Modelo de 300M parámetros |
| Whisper de las actas (`large-v3-turbo`), solo mientras transcribe | +1,5 GB | `int8_float16`; se carga por acta y se libera al terminar (86 s de audio en 13 s) |
| **Pico durante un acta** | **22,3 de 23,0 GB** | Si no cabe, el acta se transcribe en CPU en vez de fallar |

No se entrena ni se ajusta ningún modelo (solo inferencia), así que técnicas de
entrenamiento como la acumulación de gradientes no aplican. Si hiciera falta más margen,
por orden de coste:

* `OLLAMA_KV_CACHE_TYPE=q4_0`: −1,6 GB, con algo de pérdida de calidad en contextos
  largos (sin medir con Jarvis).
* `OLLAMA_CONTEXT_LENGTH=49152`: −0,7 GB, pero la conversación más larga de los ensayos
  (36.453 tokens) llega justo al umbral de compactación de 48k (36.864).
* `MEETINGS_WHISPER_MODEL=small` para las actas: ~1 GB menos de pico, con peor
  transcripción.
* `OLLAMA_NUM_PARALLEL=2`: apenas ahorra (la caché global es compartida) y frena los
  documentos, que generan 4 secciones a la vez (`docgen_concurrency`).

## Uso

```bash
scripts/select-models              # detecta VRAM, escribe .env
scripts/select-models --dry-run    # solo muestra la recomendación, no escribe
scripts/select-models --pull       # además, 'ollama pull' de los modelos elegidos
JARVIS_MODEL_TIER=vram_21000 scripts/select-models   # fuerza un nivel concreto
```

`OLLAMA_CONTEXT_LENGTH` también alimenta el override de systemd de Ollama
(`scripts/install-ollama`): si `.env` ya define esa variable la usa, si no
cae a `32768` por defecto.
