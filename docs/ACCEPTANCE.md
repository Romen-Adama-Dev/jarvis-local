# Criterios de aceptación — estado

Estado a fecha de la Fase 7 (Ollama), 2026-07-12. Se actualizará al final de
cada fase siguiente. Leyenda: ✅ verificado · ⏳ implementado, pendiente de
verificación end-to-end · ❌ no implementado todavía.

| # | Criterio | Estado | Nota |
|---|---|---|---|
| 1 | Ubuntu Server arranca correctamente | ✅ | Servidor real, auditado en Fase 1 (`docs/ARCHITECTURE.md`). |
| 2 | Todos los servicios necesarios sobreviven a un reinicio | ✅ | Verificado hoy: el equipo se reinició para que el driver NVIDIA cargase, y `jarvis-api`, `jarvis-worker`, `ollama`, `postgres`, `redis`, `qdrant` (Docker con `restart: unless-stopped` + Docker Engine habilitado en systemd) volvieron a estar activos sin intervención manual. |
| 3 | Ningún servicio interno expuesto públicamente | ✅ | Todos vinculados a `127.0.0.1` o red interna Docker; UFW solo permite `22/tcp`. Verificado con `ss -tlnp` para Ollama en esta fase; el resto en Fase 4. |
| 4 | Ollama responde localmente | ✅ | `ollama.service` activo, `/api/version` responde, GPU al 100% (`ollama ps`). |
| 5 | AirLLM responde mediante su servicio independiente | ❌ | Pendiente de Fase 8. |
| 6 | Qdrant operativo | ✅ | `/ready` → `qdrant: healthy`. |
| 7 | PostgreSQL operativo | ✅ | `/ready` → `postgres: healthy`. |
| 8 | Redis operativo | ✅ | `/ready` → `redis: healthy`. |
| 9 | OpenClaw operativo | ❌ | Pendiente de Fase 9. |
| 10 | Telegram solo acepta al usuario autorizado | ❌ | Pendiente de Fase 9 (requiere token de bot y Telegram ID del usuario). |
| 11 | Un PDF puede enviarse por Telegram | ❌ | Pendiente de Fase 9. |
| 12 | El PDF se indexa correctamente | ⏳ | Pipeline de ingestión implementado en Fase 6 (`packages/documents`, `packages/rag`); falta demostrarlo con un PDF real de punta a punta (Fase 13). |
| 13 | Una pregunta sobre el PDF devuelve respuesta con página y fuente | ⏳ | `RagSource` incluye página/sección/chunk_id; falta la demostración end-to-end (Fase 13). |
| 14 | Una pregunta sin evidencia se rechaza correctamente | ⏳ | Implementado (`insufficient_evidence` en `HybridRagOrchestrator`); falta prueba end-to-end con documento real (Fase 13). |
| 15 | `/ask` utiliza Ollama | ✅ | Verificado en esta fase: `InferenceMode.NORMAL` → `OllamaProvider`, probado con `/v1/chat` real contra el servicio desplegado. |
| 16 | `/deep` utiliza AirLLM | ❌ | Pendiente de Fase 8/9. |
| 17 | Una tarea AirLLM no bloquea Telegram | ❌ | Pendiente de Fase 8/9. |
| 18 | Los trabajos pueden cancelarse | ⏳ | `POST /v1/jobs/{id}/cancel` implementado en Fase 5; falta prueba con un trabajo real de indexación/AirLLM en curso. |
| 19 | Las acciones administrativas requieren confirmación | ⏳ | `ConfirmationService` implementado en Fase 5; falta conectarlo a los comandos administrativos de OpenClaw (Fase 9/10). |
| 20 | Los logs no contienen secretos | ⏳ | Logging estructurado JSON sin volcar payloads completos; falta auditoría explícita (Fase 11). |
| 21 | Los backups se crean | ❌ | Pendiente de Fase 12. |
| 22 | Un backup se restaura correctamente | ❌ | Pendiente de Fase 12. |
| 23 | Todos los tests pasan | ⏳ | 14/14 tests pasan hoy (`uv run pytest`), pero la cobertura aún es parcial: solo lo añadido en Fases 6-7 tiene tests; RAG/API/seguridad end-to-end quedan para la Fase 13. |
| 24 | Ruff y el comprobador de tipos pasan | ✅ | `uv run ruff check .` y `uv run pyright` sin errores sobre todo el repo. |
| 25 | El benchmark queda documentado | ✅ | `docs/BENCHMARKS.md`, con metodología, resultados de 4 modelos y justificación de la selección final (Fase 7). |
| 26 | No existen llamadas a APIs externas de modelos | ✅ | `grep` sin coincidencias de `anthropic\|openai\|generativeai\|openrouter` en `packages/`, `apps/`, `services/`, `integrations/`. |
| 27 | El sistema funciona tras desconectar Internet general (excepto Telegram) | ❌ | Pendiente de prueba explícita (Fase 15). Los servicios de inferencia (Ollama, futuro AirLLM) y almacenamiento ya son 100% locales por diseño; falta la prueba de desconexión real. |

## Resumen por fase completada

* **Fase 1-3** (auditoría, bootstrap, seguridad base): hardware auditado, `jarvis-svc`, `/srv/jarvis`, UFW — ver `docs/ARCHITECTURE.md` y `docs/SECURITY.md`.
* **Fase 4** (infraestructura): Docker Engine, PostgreSQL, Redis, Qdrant con health checks, todo en loopback.
* **Fase 5** (API y dominio): FastAPI, SQLAlchemy/Alembic, `arq`, autorización/auditoría/confirmación, API mínima.
* **Fase 6** (RAG): ingestión (hash, dedup, parsing, chunking), embeddings locales (`fastembed`), recuperación híbrida en Qdrant.
* **Fase 7** (Ollama, esta fase): instalación nativa con systemd y GPU confirmada, `OllamaProvider`, benchmark de 4 modelos, selección de modelo rápido (`qwen2.5:7b-instruct-q4_K_M`) y potente (`llama3.1:8b-instruct-q4_K_M`) con heurística de selección según el tamaño del contexto RAG.
