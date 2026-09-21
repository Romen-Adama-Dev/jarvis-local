# Criterios de aceptación — estado

Estado a 21-09-2026 (Fase 6), sobre el despliegue con docker compose en la VM de GCP con
NVIDIA L4. Leyenda: ✅ verificado · ⏳ implementado, con una parte pendiente · ❌ no
implementado. Donde se indica una rama, lo verificado está en esa PR, aún sin fusionar.

| # | Criterio | Estado | Cómo se ha verificado |
|---|---|---|---|
| 1 | El servidor arranca correctamente | ✅ | Ubuntu en la VM de GCP (L4, 8 vCPU, 31 GB de RAM); `docker compose up -d` levanta la pila completa (`docs/DOCKER.md`). |
| 2 | Todos los servicios necesarios sobreviven a un reinicio | ✅ | Reinicio de la VM el 21-09 a las 08:19: los 23 contenedores volvieron solos (`restart: unless-stopped`) y `scripts/check-integrations` pasó 43/43. Se vio que OpenClaw arrancaba antes que Tailscale y dejaba el panel sin publicar: arreglado en `fix/openclaw-espera-tailscale` (espera a tailscaled, probado reproduciendo la carrera). |
| 3 | Ningún servicio interno expuesto públicamente | ✅ | `ss -tlnp`: fuera de loopback solo escuchan `sshd` (22) y `tailscaled`. Todos los servicios de Jarvis, incluidos los de monitorización, escuchan en `127.0.0.1`; OpenClaw, OpenProject y CouchDB se publican solo en el tailnet (`tailscale serve`). UFW está inactivo en la VM: el filtrado lo hace el firewall de GCP. |
| 4 | Ollama responde localmente | ✅ | `gemma4:26b-a4b-it-qat` al 100 % en GPU (`ollama ps`), `/api/version` en las sondas de Prometheus. |
| 5 | AirLLM responde mediante su servicio independiente | ✅ | Servicio `airllm` en compose (perfil `deep`, rama `feat/airllm-compose`): `NousResearch/Meta-Llama-3.1-8B-Instruct` cargado en `cuda:0`, `/health` en `ready`, generaciones completas (`docs/AIRLLM.md`). |
| 6 | Qdrant operativo | ✅ | `/ready` → `qdrant: healthy`; 770 vectores en `jarvis_documents`. |
| 7 | PostgreSQL operativo | ✅ | `/ready` → `postgres: healthy`; bases `jarvis` y `openproject`. |
| 8 | Redis operativo | ✅ | `/ready` → `redis: healthy`. |
| 9 | OpenClaw operativo | ✅ | OpenClaw 2026.9.4 en compose, `healthy`; responde por Telegram y por el panel del tailnet (`scripts/check-integrations`). |
| 10 | Telegram solo acepta al usuario autorizado | ✅ | `dmPolicy: "allowlist"` y `allowFrom` con `TELEGRAM_AUTHORIZED_USER_IDS` en `integrations/openclaw/config/openclaw.template.json`. |
| 11 | Un PDF puede enviarse por Telegram | ✅ | Adjuntos de Telegram localizados por nombre e indexados (`b3b6b3b`); validado con el brief de Estudio Delta el 20-09. |
| 12 | El PDF se indexa correctamente | ✅ | 8 documentos y 770 fragmentos en PostgreSQL y Qdrant, separados por empresa y proyecto (`docs/EMPRESAS.md`). |
| 13 | Una pregunta sobre el PDF devuelve respuesta con página y fuente | ✅ | `/v1/rag/query` sobre App de reservas devuelve respuesta con 4 fuentes (21-09); en Telegram, con cita (20-09). |
| 14 | Una pregunta sin evidencia se rechaza correctamente | ⏳ | El modelo se abstiene ("No cuento con información suficiente en los documentos…", pregunta sobre gofio escaldado, 21-09), pero `insufficient_evidence` sale `false`: solo se marca cuando la recuperación no encuentra ningún candidato. Falta marcarlo también cuando el modelo se abstiene. |
| 15 | `/ask` utiliza Ollama | ✅ | `InferenceMode.NORMAL` → `OllamaProvider`; respuestas en 14 s. |
| 16 | `/deep` utiliza AirLLM | ✅ | `POST /v1/rag/deep-query` → trabajo en cola → worker → AirLLM (rama `feat/airllm-compose`). En la L4 cada token cuesta ~37 s (lectura de capas del disco): útil solo con modelos que no caben en la GPU (`docs/AIRLLM.md`). |
| 17 | Una tarea AirLLM no bloquea Telegram | ✅ | Con una generación de AirLLM en curso, `/v1/rag/query` respondió en 14 s. Requiere `AIRLLM_RELEASE_OLLAMA_VRAM=false` en GPUs con VRAM para ambos: con `true` (pensado para 8 GB) el worker desaloja a Ollama durante toda la consulta profunda y la misma prueba fallaba por timeout. |
| 18 | Los trabajos pueden cancelarse | ✅ | `POST /v1/jobs/{id}/cancel` sobre un `/deep` en cola: pasa a `cancelling` y el worker lo cierra como `cancelled` al recogerlo sin ejecutarlo. Una generación ya en marcha no se puede abortar (limitación de AirLLM, `docs/AIRLLM.md`). |
| 19 | Las acciones administrativas requieren confirmación | ✅ | Correo: borrador → confirmación → envío, probado el 20-09. OpenProject y el vault solo cambian a petición explícita (`docs/SECURITY.md`). |
| 20 | Los logs no contienen secretos | ✅ | Auditoría del 21-09: ninguno de los 14 secretos (los de `init`, el token del bot y la contraseña del correo) aparece en los logs de los 25 contenedores. |
| 21 | Los backups se crean | ✅ | Perfil `backup` (rama `feat/copias-seguridad`): copia diaria de bases de datos, Qdrant, secretos, OpenClaw con el vault, CouchDB y adjuntos; 93 MB en 16 s (`docs/BACKUP.md`). |
| 22 | Un backup se restaura correctamente | ✅ | `scripts/test-restore`: restauración en un proyecto de compose aislado, 14/14 comprobaciones iguales a la instalación en marcha (filas, puntos de Qdrant, ficheros, secretos). |
| 23 | Todos los tests pasan | ✅ | 138 tests en `main` (140 con las ramas de monitorización y AirLLM), más los del servicio AirLLM; la CI los ejecuta en cada PR (rama `ci/github-actions`). |
| 24 | Ruff y el comprobador de tipos pasan | ✅ | `ruff check`, `ruff format --check` y `pyright` sin errores; también en la CI. |
| 25 | El benchmark queda documentado | ✅ | `docs/BENCHMARKS.md` y, para la L4, `docs/MODELS.md` y `docs/AIRLLM.md`. |
| 26 | No existen llamadas a APIs externas de modelos | ✅ | Sin SDKs de OpenAI, Anthropic, Gemini ni OpenRouter en `packages/`, `apps/`, `services/` ni `integrations/`. Las coincidencias de `openclaw.template.json` son el protocolo OpenAI-compatible con el que OpenClaw habla con **Ollama local** y los plugins `openai-whisper*`, desactivados. |
| 27 | El sistema funciona tras desconectar Internet general (excepto Telegram) | ✅ | `scripts/test-offline` (21-09): 24 contenedores sin salida a Internet salvo Telegram (iptables por contenedor); 7/7: `/ready`, RAG con cita, OpenProject y el agente de OpenClaw respondiendo por Telegram con las tareas del proyecto. Sin Internet no funcionan, por diseño, la búsqueda web (SearXNG), el correo (Gmail) ni el historial del vault en GitHub, que se pone al día al volver la conexión. |

## Pendiente

* Criterio 14: marcar `insufficient_evidence` cuando el modelo se abstiene.
* Fusionar las ramas de la Fase 6 citadas arriba.
* UAT con usuarios y medición del ahorro de tiempo (Fase 5.1 del TFM, `docs/ROADMAP.md`).
