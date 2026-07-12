# Benchmarks — Selección de modelo Ollama

## Objetivo y metodología

El prompt de construcción exige no fijar el modelo generativo por defecto sin
antes probarlo en el hardware real. Este documento recoge el benchmark
reproducible ejecutado con `scripts/benchmark-models` sobre el hardware
descrito en `docs/ARCHITECTURE.md` (Intel i7-6700K, 32 GB RAM, NVIDIA GTX 1070
de 8 GB VRAM, driver 580.159.03, CUDA 13.0), una vez confirmado que Ollama usa
la GPU al 100 % (`ollama ps` → `100% GPU`, verificado tras el reinicio
necesario para que el driver NVIDIA quedase cargado).

Los resultados brutos están versionados en `docs/benchmarks/*.json`
(uno por ejecución, con timestamp UTC). Este documento resume y justifica la
decisión tomada a partir de ellos.

### Candidatos evaluados

Cuantizaciones `q4_K_M` (mejor relación calidad/VRAM para 8 GB) de cuatro
modelos instruct ampliamente soportados por Ollama y con buen soporte de
español:

| Modelo | Tamaño en disco |
|---|---|
| `llama3.1:8b-instruct-q4_K_M` | 4.9 GB |
| `qwen2.5:7b-instruct-q4_K_M` | 4.7 GB |
| `mistral:7b-instruct-q4_K_M` | 4.4 GB |
| `gemma2:9b-instruct-q4_K_M` | 5.8 GB |

### Batería de pruebas

Las preguntas usan como dominio de referencia el **PMI/PMBOK** (gestión de
proyectos), en línea con el uso previsto del RAG:

1. **`instrucciones_es`**: seguimiento de instrucciones de formato en español
   (3 viñetas exactas explicando riesgo vs. issue).
2. **`extraccion_estructurada`**: extracción a JSON estricto de los 5 grupos
   de procesos del PMBOK.
3. **`contexto_rag_con_evidencia`**: pregunta respondible únicamente con un
   fragmento de contexto delimitado (`<contexto>`) sobre EV/SPI — mide fidelidad
   al contexto recuperado, tal como hará el RAG real.
4. **`contexto_rag_sin_evidencia`**: pregunta **no** respondible con el mismo
   contexto (sobre el "triple constraint extendido" del PMBOK 7, que no
   aparece) — mide si el modelo **inventa** una respuesta o admite que no
   tiene evidencia suficiente. Este es el criterio más importante para un RAG
   que no debe alucinar.
5. **`tool_calling`**: se ofrece una herramienta `registrar_riesgo` vía el
   campo `tools` de la API de Ollama y se pide registrar un riesgo descrito
   en lenguaje natural — mide soporte real de tool calling nativo.

Por cada prompt se mide: tiempo hasta el primer token (streaming, TTFT),
tokens/segundo (`eval_count / eval_duration` reportado por Ollama), VRAM
usada en reposo y tras cargar el modelo (`nvidia-smi`), y el `PROCESSOR`
reportado por `ollama ps` (confirma offload 100% GPU vs. CPU).

## Resultados

| Modelo | VRAM cargado | Procesador | TTFT (ms, rango) | Tok/s (rango) | Tool calling | Rechaza sin evidencia |
|---|---|---|---|---|---|---|
| `llama3.1:8b-instruct-q4_K_M` | 5137 MiB | 100% GPU | 366–604 | 31.1–31.4 | ✅ | ✅ |
| `qwen2.5:7b-instruct-q4_K_M` | 4639 MiB | 100% GPU | 279–500 | 31.7–32.5 | ✅ | ✅ |
| `mistral:7b-instruct-q4_K_M` | 4829 MiB | 100% GPU | 201–450 | 34.0–35.0 | ❌ (HTTP 400) | ❌ (inventa una respuesta) |
| `gemma2:9b-instruct-q4_K_M` | 7057 MiB | 100% GPU | 475–822 | 23.1–23.9 | ❌ (HTTP 400) | ✅ (parcial, ver nota) |

Notas:

* **`mistral`** es el más rápido en tokens/segundo, pero falla dos criterios
  eliminatorios: la API de Ollama devuelve `400 Bad Request` al incluir el
  campo `tools` (sin soporte de tool calling en esta plantilla) y, más grave,
  **inventó una respuesta** sobre las "seis restricciones dobles del PMBOK 7"
  cuando el contexto proporcionado no contenía esa información, en vez de
  admitir que no tenía evidencia suficiente. Para un sistema RAG cuyo
  requisito explícito es "no permitas que el modelo invente una respuesta
  cuando el contexto recuperado sea insuficiente", esto lo descalifica pese a
  su velocidad.
* **`gemma2:9b`** es el modelo más grande y, en las 4 pruebas sin `tools`,
  respondió con calidad y sí evitó inventar. Pero (a) tampoco soporta el
  campo `tools` de Ollama (mismo error 400), y (b) su huella de VRAM en
  carga (7057 MiB de 8192 MiB disponibles, ~86%) deja un margen de menos de
  1.2 GB — insuficiente para considerarlo seguro junto a otros procesos que
  también usan la GPU (el propio servidor X/escritorio, u otra inferencia
  concurrente), con riesgo real de fallo por falta de memoria. No cumple el
  criterio "más potente sin que se cuelgue".
* **`llama3.1:8b`** y **`qwen2.5:7b`** son los dos únicos candidatos que
  superan las 5 pruebas sin fallos: soportan tool calling nativo de Ollama y
  rechazan explícitamente responder cuando no hay evidencia en el contexto.

## Decisión

Siguiendo el criterio del usuario ("quedarse solo con el más potente sin que
se cuelgue y el más rápido, y elegir uno u otro según la tarea"), se
descartan `mistral` y `gemma2` (`ollama rm`) y se conservan exactamente dos
modelos:

| Rol | Modelo | Variable de entorno | Justificación |
|---|---|---|---|
| **Rápido** (consultas normales) | `qwen2.5:7b-instruct-q4_K_M` | `OLLAMA_PRIMARY_MODEL` | Mejor tok/s y TTFT de los dos candidatos que sí cumplen tool calling y no inventan; menor huella de VRAM (4639 MiB) de los cuatro modelos probados. No es el más rápido en bruto (`mistral` lo era), pero `mistral` queda descartado por fallar los dos criterios funcionales obligatorios del proyecto. |
| **Potente** (contextos RAG grandes, dentro del modo normal — no confundir con `/deep`→AirLLM) | `llama3.1:8b-instruct-q4_K_M` | `OLLAMA_POWERFUL_MODEL` | Modelo más grande de los dos que caben con margen de VRAM seguro (5137 MiB de 8192 MiB, ~63%, frente al 86% de `gemma2`); mismo cumplimiento de tool calling y no-alucinación. |

### Cuándo se usa cada uno

Ambos modelos están detrás del mismo `OllamaProvider` (modo `NORMAL` del
`InferenceRouter`; el modo `DEEP` sigue siendo exclusivamente AirLLM, fase 8).
La elección entre `qwen2.5` (rápido) y `llama3.1` (potente) ocurre **dentro**
del modo `NORMAL`, en `packages/rag/orchestrator.py::select_normal_model`:

* Si el contexto recuperado por el RAG (tras deduplicar y aplicar el
  presupuesto de contexto) supera `POWERFUL_MODEL_CONTEXT_THRESHOLD_CHARS`
  (3000 caracteres, la mitad del presupuesto máximo de 6000), se usa
  `llama3.1:8b` para una síntesis de más fragmentos.
* En caso contrario —la mayoría de consultas cortas o con pocos fragmentos—
  se usa el modelo rápido (`qwen2.5:7b`, el configurado por defecto en el
  `OllamaProvider`).
* Cualquier llamada a `/v1/chat` puede además forzar un modelo concreto vía
  el campo `model` del payload, independientemente de esta heurística.

Este umbral es una heurística simple y documentada, no una regla exhaustiva:
queda como trabajo futuro afinarla con datos reales de uso (p. ej. según
longitud de la pregunta, número de fragmentos, o clasificación de intención).

### Estabilidad

Se realizaron descargas, cargas y descargas de los 4 modelos sin caídas del
servicio `ollama.service` (`systemctl status ollama` se mantuvo `active` en
todo momento). El único fallo observado (HTTP 400 en `tools`) es un rechazo
controlado de la API ante una plantilla de modelo sin soporte de tool
calling, no un cuelgue ni un error del servicio.

## Reproducir el benchmark

```bash
scripts/benchmark-models --models "llama3.1:8b-instruct-q4_K_M,qwen2.5:7b-instruct-q4_K_M"
```

Guarda un JSON con timestamp en `docs/benchmarks/`. Añadir o quitar modelos
candidatos con `--models "modelo1,modelo2,..."`.
