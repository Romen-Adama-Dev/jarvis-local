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
| `vram_21000` | ≥ 21000, < 38000 | `gemma4:26b-a4b-it-qat` | `gemma4:26b-a4b-it-qat` | 32768 |
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
