# Benchmarks — modelo de Ollama y sistema completo

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
| **Potente** (contextos RAG grandes) | `llama3.1:8b-instruct-q4_K_M` | `OLLAMA_POWERFUL_MODEL` | Modelo más grande de los dos que caben con margen de VRAM seguro (5137 MiB de 8192 MiB, ~63%, frente al 86% de `gemma2`); mismo cumplimiento de tool calling y no-alucinación. |

### Cuándo se usa cada uno

Ambos modelos están detrás del mismo `OllamaProvider` (modo `NORMAL` del
`InferenceRouter`). La elección entre `qwen2.5` (rápido) y `llama3.1` (potente)
ocurre en `packages/rag/orchestrator.py::select_normal_model`:

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

## Auto-selección por hardware (`scripts/quickstart`)

Este benchmark ancla la única franja validada (`vram_7000`, GTX 1070 8192 MiB)
de la auto-selección de modelo por VRAM total detectada: ver `docs/MODELS.md`
para la tabla completa de franjas y `scripts/select-models` para el script.
Fuera de esa franja, `scripts/select-models` extrapola razonadamente sin
inventar un modelo no evaluado; re-ejecutar `scripts/benchmark-models` con
candidatos mayores para validar las franjas superiores.

## Reproducir el benchmark

```bash
scripts/benchmark-models --models "llama3.1:8b-instruct-q4_K_M,qwen2.5:7b-instruct-q4_K_M"
```

Guarda un JSON con timestamp en `docs/benchmarks/`. Añadir o quitar modelos
candidatos con `--models "modelo1,modelo2,..."`.

## Benchmarks de Jarvis (sistema completo)

`scripts/benchmark-jarvis` mide el sistema en marcha tal como lo usa una persona, no solo
el modelo: la API, el RAG con su reranker, la traducción de la consulta, el worker de
actas con faster-whisper y la generación de documentos. Los casos están versionados en
`docs/benchmarks/casos/` y cada ejecución deja un JSON en `docs/benchmarks/`. No crea nada
en OpenProject, el vault ni el RAG. Las personas reales se miden aparte, con el protocolo de
[UAT.md](UAT.md).

```bash
scripts/benchmark-jarvis                         # todo, ~10 min en la L4
scripts/benchmark-jarvis --solo rag,traduccion   # solo algunos bloques
scripts/benchmark-jarvis --con-respuestas        # guarda también el texto de cada respuesta
```

Por defecto no guarda el texto de las respuestas del RAG, porque citan la documentación
indexada (con derechos de autor) y los resultados se suben al repo público.

| Bloque | Qué mide | Casos |
|---|---|---|
| `rag` | Respuesta correcta **y** con su documento entre las fuentes; abstención cuando la documentación no lo dice; latencia | 18 preguntas comprobadas en el texto indexado (14 del PMBOK en español, 4 del libro de Snyder en inglés preguntadas en español) y 4 fuera de dominio |
| `traduccion` | Términos técnicos correctos en la traducción de la consulta al inglés, con el mismo prompt y modelo que el RAG | 20 consultas de gestión de proyectos, 39 términos esperados |
| `actas` | Una reunión de 2 min sintetizada con la voz de Jarvis (Piper): tiempo total, error de transcripción (WER frente al guion) y los 15 elementos del acta | El guion de `casos/reunion.json` |
| `documentos` | Un resumen generado desde el RAG: tiempo y secciones con evidencia | "Los dominios de desempeño del proyecto" |

### Resultados del 01-10-2026

NVIDIA L4, `gemma4:26b-a4b-it-qat`, `main` en `41bf5c5`
(`docs/benchmarks/jarvis-2026-10-01T11-13-03.json`).

| Bloque | Resultado |
|---|---|
| RAG · preguntas con respuesta | **14/18** correctas con su fuente (16/18 citan el documento correcto) |
| RAG · fuera de dominio | **4/4** abstenciones; ninguna respuesta inventada |
| RAG · latencia | mediana **14,2 s**, p95 19,7 s |
| Traducción de la consulta | **35/39** términos, mediana 0,23 s |
| Actas | reunión de 2:06 en **28 s** (4,5 veces más rápido que el tiempo real), WER **9,1 %**, **15/15** elementos (fecha, 4 asistentes, 3 decisiones, 4 acciones con responsable y fecha, 2 riesgos, próxima reunión) |
| Documento generado | resumen de 4 secciones en **54 s**, 4/4 con evidencia |

Los cuatro fallos del RAG, revisados uno a uno:

* **MoSCoW** (PMBOK p. 276): el fragmento existe, pero no llega a los candidatos y Jarvis
  se abstiene. Un acrónimo en una lista de métodos: la búsqueda no lo encuentra.
* **Modelos de complejidad**: cita Cynefin, pero no la matriz de Stacey.
* **Evaluación del desempeño del equipo** (Snyder p. 173): describe qué se valora
  (alcance, calidad, cronograma, costo), no la escala (*Exceeds / Meets / Needs
  improvement*), que está en otro fragmento.
* **Lecciones aprendidas** (Snyder): varía entre ejecuciones. En una dio los apartados de
  la tabla de la p. 223, que son válidos; en otra respondió a medias y lo marcó como sin
  evidencia suficiente.

Dos de los cuatro son preguntas en español sobre el libro en inglés (2/4 en ese
documento, frente a 12/14 en el PMBOK): ahí está el margen de mejora.

### Traducción de la consulta: comparación de traductores

La consulta se traduce al inglés para encontrar también la documentación en inglés
(PR #18). Se midió el 01-10-2026 con las 20 consultas de `casos/traduccion.json`, contando
los términos técnicos esperados en la traducción:

| Traductor | Términos | Mediana | Ejemplo de fallo |
|---|---|---|---|
| **Gemma 4 26B** (el propio modelo de Jarvis, el que se usa) | **35/39** | 0,24 s | *total slack* por *float* (sinónimo válido) |
| TranslateGemma 4B (Ollama) | 27/39 | 0,17 s | *acta de constitución* → *incorporation certificate* |
| Opus-MT es-en (CTranslate2, int8, CPU) | 25/39 | 0,03 s | *ruta crítica* → *critical route* |

Un prompt que pedía "la terminología técnica del ámbito" no mejoró a Gemma (35/39). Con
eso se descartaron tanto un traductor dedicado como el reranker multilingüe jina: la
traducción actual ya conserva la terminología y tarda una fracción de segundo.

## AirLLM: evaluado y descartado

El modo profundo con AirLLM (servir por capas desde disco un modelo que no cabe en
VRAM) se midió en julio de 2026 sobre una GTX 1070 y en septiembre sobre la L4 del
despliegue actual. En la L4 la generación se quedó en ~37 s por token: ninguna
consulta llegó a terminar dentro del tiempo máximo del trabajo. Se retiró del
proyecto el 23-09-2026 junto con el servicio, el perfil `deep` y la herramienta
`jarvis_deep`. Las mediciones completas (dos informes de julio y la guía del servicio)
se retiraron con él y quedan en el historial de git, en el commit anterior a la
retirada.
