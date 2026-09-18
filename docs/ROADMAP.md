---
name: jarvis-pmi-roadmap
description: Resumen del TFM (memoria), estado real del repo frente a esa memoria, y plan de evolución (capa MCP, correo, calendario, generación de documentos, Teams)
---

# JARVIS-PMI · Resumen, estado y plan de evolución

> Documento de trabajo. Une tres cosas: qué dice la memoria (TFM), qué tiene ya el
> repositorio `jarvis-local`, y qué queremos añadir (agente: correo, reuniones,
> generación de documentos, Telegram/Teams). Fecha: septiembre 2026 (actualizado el 17).

---

## 1. Resumen del TFM (memoria)

**JARVIS-PMI** es una plataforma **local y privada** de gestión del conocimiento
para *project managers*. Ataca la dispersión de información (actas, requisitos,
riesgos, cronogramas, repos) con una arquitectura **RAG** (generación aumentada
por recuperación). Nada —documentos, embeddings, prompts, respuestas— sale del
servidor hacia APIs en la nube.

- **Metodología:** híbrida **Water-Scrum-Fall** (gobierno predictivo → construcción
  iterativa → cierre predictivo), justificada con la **matriz de Stacey** y Cynefin.
- **Arquitectura:** FastAPI + worker asíncrono + PostgreSQL + Redis + Qdrant +
  inferencia local (Ollama para lo normal, AirLLM para el modo `/deep`). OpenClaw
  y Telegram como capa opcional de interacción.
- **Verificado en el MVP:** subida e indexación de PDF, respuesta con documento y
  sección, **abstención** cuando no hay evidencia, health checks, despliegue Docker,
  ejecución local de modelos, control de acceso, voz local y supervisión.
- **Viabilidad económica:** perfiles, horas, tarifas, reservas, VAN, TIR, ROI y
  periodo de recuperación (BAC 10.625 €, presupuesto 11.156 €).
- **Pendiente (declarado):** UAT con usuarios representativos, medición real del
  ahorro de tiempo y cierre económico. El repo es público pero **requiere licencia
  y gobernanza** antes de considerarse open source formal.
- **Valoración del director:** nivel matrícula; ajustes estéticos ya aplicados.

**Lectura clave para el plan:** el TFM ya contempla una **hoja de ruta de evolución**
(Tabla 59). Lo que quieres añadir (agente que contesta correos, agenda reuniones y
genera documentos) es exactamente esa evolución post-MVP, no un desvío del alcance.

---

## 2. Estado actual — las tres columnas

Leyenda: ✅ hecho · 🟡 parcial · ⬜ por hacer

| Capacidad / pieza | Memoria (TFM) describe | Repo `jarvis-local` tiene | Queremos añadir |
|---|---|---|---|
| **Ingesta + RAG** (PDF → chunks → embeddings → Qdrant → respuesta con fuente) | ✅ núcleo del proyecto | ✅ `packages/rag`, `packages/documents`, Qdrant | 🟡 mejor ingesta (Docling: escaneados/tablas) |
| **Inferencia local** (Ollama normal, AirLLM `/deep`) | ✅ | ✅ Ollama en contenedor con GPU (versión fijada); `services/airllm`; **auto-selección de modelo por VRAM** (`scripts/select-models`, la aplica `init`); `gemma4:26b-a4b-it-qat` en GPUs de 21-38 GB; limpieza opcional de modelos sin usar (`OLLAMA_PRUNE_UNUSED`) | 🟡 AirLLM `/deep` sin verificar en compose |
| **Abstención sin evidencia** | ✅ | ✅ `packages/rag/orchestrator.py` | — |
| **API + worker** | ✅ | ✅ FastAPI (`apps/api`) + arq (`apps/worker`) | — |
| **Infra reproducible** (Postgres/Redis/Qdrant, Docker) | ✅ | ✅ **todo Jarvis con `docker compose up`** (`docs/DOCKER.md`): `init` genera secretos y elige modelo, OpenClaw con voz y skills MCP en imagen propia, perfiles opcionales; `compose.cpu.yml` sin GPU | 🟡 CI que construya las imágenes y pruebe el arranque |
| **Embeddings** | ✅ | ✅ FastEmbed (denso + disperso) | 🟡 reranker local (mejora recuperación) |
| **Transporte Telegram** | 🟡 capa opcional | ✅ `integrations/openclaw`, config Telegram; indexación de PDFs recibidos con confirmación; entrega de documentos generados | — |
| **Agente / orquestación** | 🟡 OpenClaw mencionado | ✅ OpenClaw + skills MCP (`jarvis-rag`, `jarvis-email`, `jarvis-calendar`, vía `FastMCP`) | — |
| **Búsqueda web** | — | ✅ SearXNG, arranca por defecto (`web_search` de OpenClaw) | — |
| **Automatización** | — | ✅ n8n (perfil automation) | 🟡 flujos de correo/calendario |
| **Observabilidad** | ✅ supervisión | 🟡 perfil `monitoring` (Prometheus + Grafana) sin configurar para el despliegue compose | ⬜ métricas de Ollama/GPU, API y OpenClaw; alertas (Fase 6) |
| **Voz local (STT/TTS)** | ✅ | ✅ whisper.cpp (AVX2) + Piper es_ES dentro de la imagen de OpenClaw | — |
| **Contestar correos** | ⬜ (roadmap) | ✅ MCP correo con backend IMAP/SMTP para cualquier proveedor (`packages/imapsmtp`) o Graph (`packages/msgraph/mail.py`); skill `jarvis-email`, borrador→confirmación, adjuntos de doc-gen; cuenta Gmail de Jarvis configurada | 🟡 validar end-to-end con correos reales |
| **Agendar / planificar reuniones** | ⬜ (roadmap) | ✅ MCP calendario con backend CalDAV (`packages/caldavcal`) o Graph (`packages/msgraph/calendar.py`); skill `jarvis-calendar`, propuesta→confirmación | ⬜ configurar un calendario CalDAV (hoy sin calendario) y validar |
| **Generar documentos desde cero** | ⬜ (roadmap) | ✅ `packages/docgen` (resúmenes/DAFO/planes desde el RAG, docx/pptx/pdf/md, secciones en paralelo, entregados por Telegram con `MEDIA:`, `docs/DOCGEN.md`) | — |
| **Microsoft Teams** | ⬜ | 🟡 canal `msteams` soportado en OpenClaw (`scripts/configure-teams`, `docs/TEAMS.md`) | ⬜ **túnel público (Cloudflare Tunnel) + manifiesto de la app**, sin versionar todavía |
| **Licencia + gobernanza** | ⬜ declarado pendiente | ✅ `LICENSE` (MIT) + `CONTRIBUTING.md` | — |
| **Memoria evolutiva** | — | ✅ `memory-core` + `memory-wiki` de OpenClaw, vault Obsidian versionado en git privado (`vault-sync`), búsqueda semántica con `embeddinggemma` (`docs/MEMORY.md`) | 🟡 primera nota de proyecto real de punta a punta |
| **Obsidian en móvil y portátil** | — | ✅ Self-hosted LiveSync: CouchDB por Tailscale + `livesync-bridge` con el vault, cifrado E2E (perfil `livesync`, `docs/OBSIDIAN.md`); iPhone configurado el 18-09 | 🟡 comprobar que iPhone→vault llega sin reiniciar el puente |
| **Seguimiento y control de proyectos** | 🟡 (gestión del conocimiento; el seguimiento lo hace el PM a mano) | ✅ OpenProject 17.8 (perfil `pm`, `docs/OPENPROJECT.md`): empresas → proyectos, tareas, hitos, **riesgos**, Gantt y tableros por Tailscale; skill MCP `jarvis-pm` (6 herramientas) validada con Gemma: alta de riesgos, cambios de estado e informe de seguimiento desde el chat | — |
| **Actas de reunión automáticas** | 🟡 (STT local para notas de voz) | ✅ grabación → faster-whisper large-v3-turbo en GPU (1 h ≈ 2 min) → acta estructurada con Gemma (resumen, decisiones, acciones con responsable y fecha, riesgos) → PDF/Word, nota en Obsidian, RAG del proyecto y, con confirmación, tareas y riesgos en OpenProject (`docs/ACTAS.md`); validado de punta a punta desde el agente | ⬜ separación de hablantes (diarización local) |
| **Acceso remoto al panel** | — | ✅ Tailscale en compose; panel de OpenClaw en `https://<host>.<tailnet>.ts.net` sin puertos abiertos, gateway solo en loopback (`docs/ACCESO-REMOTO.md`) | — |

---

## 3. Lo nuevo (septiembre 2026): cómo darle esas funcionalidades

### 3.1 La decisión de arquitectura: MCP como capa de capacidades

En 2026 el estándar de facto para conectar herramientas a un agente es **MCP
(Model Context Protocol)**. En lugar de programar cada integración a mano dentro
de OpenClaw, se levantan **servidores MCP** (uno por capacidad) y el agente los
consume. Ventajas para JARVIS: siguen siendo **locales y privados**, son
**intercambiables**, y hay ecosistema ya hecho (correo, calendario, Telegram, Teams).

**¿Seguimos con OpenClaw o hay algo mejor?**

- **OpenClaw** sigue siendo enorme (375k+ estrellas) y ya lo tienes integrado. Es
  una opción válida: mantenlo como *gateway* del agente y añádele capacidades vía MCP.
- **Alternativas MCP-nativas** más ligeras/seguras si OpenClaw se te hace pesado:
  - **Hermes Agent** — MCP nativo, *skills* que mejoran con el uso, **workflows
    programados (cron)** — encaja con "agendar" y tareas recurrentes.
  - **ZeroClaw** — binario Rust minúsculo, ideal para servidor siempre encendido.
  - **NanoClaw** — ejecución aislada en contenedor (límites de seguridad claros).

**Recomendación:** no cambies de agente ahora. Adopta **MCP como capa de capacidades**
sobre tu OpenClaw actual; si más adelante quieres algo más ligero, migrar a un cliente
MCP (Hermes/ZeroClaw) es sencillo precisamente porque las capacidades ya serán MCP.

### 3.2 Las cuatro capacidades que pides

| Capacidad | Cómo (2026) | Nota de seguridad |
|---|---|---|
| **Contestar correos** | Servidor **MCP de correo** (IMAP/SMTP local, o `microsoft/local-email-agent`: Foundry Local + MCP + LangChain, 100% local) | **Nunca envío autónomo**: el modelo redacta borrador → confirmación humana (tu repo ya tiene `CONFIRMATION_TTL_SECONDS` y rate-limit) |
| **Planificar reuniones** | Servidor **MCP de calendario** (CalDAV para privado; Microsoft Graph si usas Outlook/Teams) para leer huecos y crear eventos | Solo crear/proponer; confirmación antes de invitar a terceros |
| **Generar documentos desde 0** | *Skill* de generación: el modelo produce contenido y lo materializa en **.docx/.pptx/.md** con plantillas (mismo enfoque que usas para el TFM) | Local; la fuente de datos es tu corpus RAG (con cita) |
| **Todo desde Telegram / Teams** | Telegram ya es MCP-nativo vía la skill `jarvis-rag`. Para Teams, **no hace falta un servidor MCP nuevo**: OpenClaw tiene canal oficial `@openclaw/msteams` (plugin de primera parte desde 2026.1.15) que da conversación de bot igual que Telegram — la misma skill `jarvis-rag` sirve a ambos canales sin cambios. Ver `docs/TEAMS.md`. | Lista blanca de usuarios (Telegram: `TELEGRAM_AUTHORIZED_USER_IDS`; Teams: `allowFrom` por AAD object ID). **Importante**: a diferencia de Telegram (long polling, sin exposición), Teams exige un *messaging endpoint* HTTPS alcanzable por el conector Bot Framework de Microsoft — requiere un túnel saliente (no abrir UFW), detallado en `docs/TEAMS.md`. |

**Idea de producto fuerte para el TFM/demo:** encadenar las cuatro en un flujo real de
PM — *"resume las actas del proyecto X, redacta el correo de seguimiento, propón hueco
de reunión la semana que viene y genera el acta en Word"* — todo local, con cita de
fuentes y aprobación humana en cada acción con efectos externos.

---

## 4. Plan por fases (roadmap accionable)

**Fase 0 — Base reproducible (✅ cerrada).**
Auto-selección de modelo Ollama por VRAM detectada (`scripts/select-models`,
`docs/MODELS.md`) y `scripts/quickstart` "clona y arranca". **LICENSE** (MIT)
y **CONTRIBUTING.md** → cierra el pendiente "open source formal" del TFM.

**Fase 1 — Capa MCP (✅ cerrada: skills `jarvis-rag`, `jarvis-email` y `jarvis-calendar` como servidores MCP de OpenClaw).**
Introducir un cliente/host MCP en el worker o junto a OpenClaw. Primer servidor MCP
de prueba (p. ej. filesystem o el propio RAG expuesto como MCP). Criterio de éxito:
el agente llama a una herramienta MCP local y responde con trazabilidad.

**Fase 2 — Generación de documentos (✅ cerrada).**
*Skill* doc-gen: DAFO o plan de coordinación, con secciones fijas por tipo de
documento, cada una resuelta con una llamada independiente a
`HybridRagOrchestrator.query(...)` (el mismo motor que `/ask`/`/deep`: sin
prompt ni retrieval nuevos, sin superficie de alucinación adicional; una
sección sin evidencia lo dice explícitamente en vez de inventar). Salida en
`.md`/`.docx`/`.pptx` (python-docx/python-pptx, ya dependencias del proyecto)
y `.pdf` (Pandoc + XeLaTeX vía subproceso, sin plantilla LaTeX vendorizada por
licencia; `scripts/install-docgen` o la imagen Docker). Expuesta como trabajo
asíncrono (`POST /v1/documents/generate`, igual que `/deep-query`) y como
herramienta MCP `jarvis_generate_doc` en la skill `jarvis-rag`. El archivo
generado se entrega por Telegram (ver `docs/DOCGEN.md`).

**Fase 3 — Correo (borrador + aprobación) (✅ implementada; IMAP/SMTP añadido el 15-09 para usarlo sin Azure; falta validación con correo real).**
MCP de correo local. Flujo: leer → resumir → **redactar borrador** → confirmación
por Telegram → enviar. Reutiliza tu patrón de confirmación/TTL.
La base de autenticación OAuth2 compartida con Graph (Fase 3 y Fase 4) está
**en marcha en `feature/mcp-msgraph-base`** (`packages/msgraph/`, ver
`docs/MSGRAPH.md`): device code flow con MSAL + cliente HTTP genérico, sin
herramientas de correo todavía.
Las herramientas MCP de correo propiamente dichas están **en marcha en
`feature/mcp-email`** (ver `docs/EMAIL.md`): `packages/msgraph/mail.py`
(`list_inbox`/`get_message`/`send_mail`), API interna `/v1/email` y el servidor
MCP `jarvis-email` (`jarvis_email_inbox`, `jarvis_email_read`,
`jarvis_email_draft`, `jarvis_email_confirm_send`). El borrador+confirmación
reutiliza el `payload` genérico de `ConfirmationService` (añadido en
`feature/mcp-msgraph-base`) en vez de un mecanismo nuevo; scopes de Graph
necesarios: `Mail.Read`, `Mail.Send`.

**Fase 4 — Calendario / reuniones (✅ implementada, CalDAV añadido el 15-09; sin calendario configurado todavía).** Nació en `feature/mcp-calendar`
(ver `docs/CALENDAR.md`). Sobre la base de `feature/mcp-msgraph-base`
(`packages/msgraph/calendar.py`: `get_calendar_view`/`create_event` vía Graph,
scopes `Calendars.Read`/`Calendars.ReadWrite`), expone `/v1/calendar/events`
(lectura) y el flujo **proponer → confirmar** de `/v1/calendar/draft` +
`/v1/calendar/draft/{token}/confirm`, reutilizando el campo genérico
`payload` de `ConfirmationService.request(...)` para guardar el evento
propuesto hasta la confirmación. Nuevo servidor MCP `jarvis-calendar`
(`jarvis_calendar_availability`, `jarvis_calendar_propose_event`,
`jarvis_calendar_confirm_event`) con la misma advertencia que `gog`: **crear
un evento nunca invita a terceros de forma autónoma**, solo tras confirmación
explícita del propietario cuando la propuesta incluye invitados.

**Fase 5 — Segundo canal: Teams** (🟡 soportado en configuración; bloqueado por el registro de Azure Bot, que no se puede usar).
Canal oficial `@openclaw/msteams` (no un servidor MCP nuevo: la skill
`jarvis-rag` ya sirve a cualquier canal). Mismo backend, otro transporte.
Requiere registro de Azure Bot (paso único del propietario) y un túnel
saliente hacia el *messaging endpoint*, ya que a diferencia de Telegram este
canal necesita recibir llamadas entrantes. Detalle completo en
`docs/TEAMS.md`.

**Fase 5.1 — Web pública de demo para la defensa del TFM (aparcada).**
Chat en vivo contra el RAG, con login privado (solo para la presentación),
frontend estático en Vercel. Backend aún sin decidir (túnel temporal a la VM,
endpoint permanente, o instancia separada) y corpus de demo pendiente de
definir. Retomar cuando se acerque la fecha de defensa; no bloquea las fases
1-5 de capacidades del agente.

**Fase 5.2 — Despliegue reproducible y acceso (✅ cerrada, 15-17 septiembre).**
Todo con `docker compose up` (`docs/DOCKER.md`); acceso remoto al panel por Tailscale
(`docs/ACCESO-REMOTO.md`); memoria en Obsidian del móvil y el portátil con LiveSync
(`docs/OBSIDIAN.md`); limpieza opcional de modelos de Ollama sin usar.

**Fase 6 — Endurecer y medir.**
UAT con estos flujos, métricas de ahorro de tiempo (cierra el otro pendiente del
TFM), y decisión OpenClaw vs. cliente MCP ligero (Hermes/ZeroClaw). Tareas concretas:

* **Monitorización**: perfil `monitoring` adaptado a compose (Ollama, GPU con
  `dcgm-exporter`, API, CouchDB) y alertas básicas.
* **Copias de seguridad y restauración** probadas de PostgreSQL, Qdrant, estado de
  OpenClaw y CouchDB (criterios 21-22 de `docs/ACCEPTANCE.md`).
* **CI**: tests, ruff y pyright en cada PR, y construcción de las imágenes de compose.
* **Validaciones de punta a punta pendientes**: correo real, calendario CalDAV, AirLLM
  `/deep`, edición desde Obsidian en el iPhone, prueba sin Internet (criterio 27).
* **Actualizar `docs/ACCEPTANCE.md`**, que refleja el estado de julio (Fase 9).
* Limpieza: rama remota `fix/openclaw-2026.9-deploy`, imagen `alpine/git` sin versión
  fijada en `vault-sync`.

---

## 5. Las mejores "skills" (capacidades) para añadir al proyecto

Priorizadas por relación valor/esfuerzo para JARVIS-PMI:

1. **doc-gen** — generar documentos (.docx/.pptx/.md/.pdf) desde el corpus, con cita,
   reutilizando `HybridRagOrchestrator` sección a sección (en marcha en
   `feature/doc-generation`, ver `docs/DOCGEN.md`). *Alta / media.*
2. **mcp-host** — capa MCP en el worker (habilita todo lo demás). *Alta / media.*
3. **rag-as-mcp** — exponer tu propio RAG como servidor MCP (reutilizable por cualquier agente). *Alta / baja.*
4. **email-draft** — MCP de correo con borrador+aprobación. *Alta / media.*
5. **calendar** — MCP de calendario (CalDAV/Graph) para reuniones. *Media / media.*
6. **teams-transport** — segundo canal Teams. *Media / media.*
7. **reranker** — reranker local para subir precisión de recuperación. *Media / baja.*
8. **docling-ingest** — ingesta de PDFs escaneados/tablas con Docling. *Media / baja.*
9. **web-brief** — usar tu SearXNG para informes con fuentes. *Baja / baja.*

> Nota: aquí "skills" son **capacidades del agente** (OpenClaw skills / servidores MCP),
> distintas de la *skill de Claude* para desarrollar el repo.

---

## 6. Fuentes (septiembre 2026)

- OpenClaw y alternativas locales/MCP: Composio, BuildBetter, Vellum.
- Estándar MCP y servidores (correo/calendario/Telegram/Teams): mcpservers.org, Composio, PulseMCP.
- Agente de correo 100% local: `microsoft/local-email-agent` (Foundry Local + MCP + LangChain).
