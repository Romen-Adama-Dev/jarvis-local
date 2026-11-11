# Decisiones de arquitectura (índice de ADR)

Las decisiones de Jarvis Local se tomaron y documentaron en la guía de cada área, no en
archivos ADR sueltos. Este índice las reúne con el formato de un registro de ADR: fecha,
decisión, alternativas descartadas y dónde está el razonamiento completo. Una decisión
nueva se añade al final con el siguiente número y, si sustituye a otra, cambia el estado de
la anterior.

| ADR | Fecha | Decisión | Alternativas descartadas | Estado | Fuente |
|---|---|---|---|---|---|
| 001 | 12-07-2026 | Pila de partida: FastAPI, worker arq sobre Redis, PostgreSQL, Qdrant y Ollama, con dominios separados en `packages/` | | Vigente | [ARCHITECTURE.md](../ARCHITECTURE.md), commit `09538f5` |
| 002 | 12-07-2026 | Inferencia solo local con Ollama, detrás de `packages/inference`; ningún paquete llama a APIs de modelos en la nube | APIs de inferencia en la nube | Vigente | [ARCHITECTURE.md](../ARCHITECTURE.md), [CONTRIBUTING.md](../../CONTRIBUTING.md) |
| 003 | 12-07-2026 | Modelo elegido por benchmark: `qwen2.5:7b` (rápido) y `llama3.1:8b` (potente) en la GTX 1070 | `mistral:7b`, el más rápido, por fallar el tool calling e inventar sin evidencia; `gemma2:9b` por VRAM y sin tool calling | Sustituida por 008 | [BENCHMARKS.md](../BENCHMARKS.md), "Decisión" |
| 004 | 13-07-2026 | OpenClaw como gateway del agente, con Telegram como canal y lista blanca de usuarios | | Vigente | [OPENCLAW.md](../OPENCLAW.md), commit `6131338` |
| 005 | 13-07-2026 | Comandos desde Telegram con aprobación explícita: lista blanca de solo lectura y el resto retenido hasta `/approve` | Prohibición total de shell (la regla inicial) | Vigente | [OPENCLAW.md](../OPENCLAW.md), "exec approvals"; [SECURITY.md](../SECURITY.md) |
| 006 | 09-09-2026 | MCP como capa de capacidades: un servidor MCP por área sobre el OpenClaw existente | Cambiar a Hermes Agent, ZeroClaw o NanoClaw | Vigente | [ROADMAP.md](../ROADMAP.md), 3.1 |
| 007 | 15-09-2026 | Despliegue con un solo `docker compose up` y servicios opcionales por perfiles | Instalación con systemd en el servidor (queda documentada como histórico) | Vigente | [DOCKER.md](../DOCKER.md), commit `8f42145` |
| 008 | 15-09-2026 | Modelo elegido por la VRAM detectada (`scripts/select-models`); en la L4, `gemma4:26b-a4b-it-qat` | Modelo fijo para cualquier hardware | Vigente | [MODELS.md](../MODELS.md) |
| 009 | 17-09-2026 | Memoria en Obsidian sincronizada con LiveSync (CouchDB propio) e historial en un repositorio git privado | Obsidian Git en el móvil, Obsidian Sync, Syncthing | Vigente | [OBSIDIAN.md](../OBSIDIAN.md), "Alternativas descartadas"; commit `8dc31a5` |
| 010 | 18-09-2026 | OpenProject como centro de proyectos, reuniones y calendario, con una skill `jarvis-pm` de pocas herramientas | Plane; MCP oficial de OpenProject (solo Enterprise); MCP de la comunidad con 116 herramientas | Vigente | [OPENPROJECT.md](../OPENPROJECT.md), "Alternativas consideradas"; commit `831a857` |
| 011 | 23-09-2026 | El envío de correo se aprueba con un botón de Telegram, fuera del modelo | Herramienta `jarvis_email_confirm_send` en manos del agente | Vigente | [EMAIL.md](../EMAIL.md), commit `252fcef` |
| 012 | 23-09-2026 | Retirar AirLLM y el modo `/deep` (criterios 5 y 16 fuera del alcance) | Mantenerlo: ~37 s por token en la L4 | Vigente | [BENCHMARKS.md](../BENCHMARKS.md), "AirLLM: evaluado y descartado"; commit `5ad46d1` |
| 013 | 23-09-2026 | Internet solo con permiso: primero lo interno, después fuentes que el propietario aprueba una a una | Búsqueda web libre del agente | Vigente | `integrations/openclaw/workspace/AGENTS.md`; [ROADMAP.md](../ROADMAP.md), 4.0.2 |
| 014 | 01-10-2026 | Teams y la web pública de demo fuera del alcance; Telegram es el único canal | Canal `@openclaw/msteams` (exige Azure Bot y un endpoint público) | Vigente | [ROADMAP.md](../ROADMAP.md), fases 5 y 5.1; commit `cef076a` |
| 015 | 01-10-2026 | Traducción de la consulta al inglés con el propio modelo y un glosario (39/39 términos) | Traductor dedicado (TranslateGemma, Opus-MT) y reranker multilingüe jina | Vigente | [BENCHMARKS.md](../BENCHMARKS.md); [GLOSARIO.md](../GLOSARIO.md); PR #30 |

## English summary

Index of the architecture decisions behind Jarvis Local, each with its date, the options
that were rejected and a link to the full reasoning in the docs or the commit history.
Notable entries: local-only inference (002), rejecting the fastest benchmarked model
because it hallucinated (003), MCP as the capability layer (006), OpenProject over Plane
(010) and approval buttons outside the model for outgoing email (011).
