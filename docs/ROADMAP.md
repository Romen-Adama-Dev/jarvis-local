---
name: jarvis-pmi-roadmap
description: Resumen del TFM (memoria), estado real del repo frente a esa memoria, y plan de evolución (capa MCP, correo, calendario, generación de documentos, Teams)
---

# JARVIS-PMI · Resumen, estado y plan de evolución

> Documento de trabajo. Une tres cosas: qué dice la memoria (TFM), qué tiene ya el
> repositorio `jarvis-local`, y qué queremos añadir (agente: correo, reuniones,
> generación de documentos, Telegram/Teams). Fecha: septiembre 2026 (actualizado el 1 de octubre).

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
  inferencia local con Ollama. OpenClaw y Telegram como capa opcional de
  interacción.
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
| **Multiempresa: documentación aislada por empresa y proyecto** | 🟡 (propuesta: colecciones separadas por cliente) | ✅ general / empresa / proyecto en el payload de Qdrant con `company` como tenant (`is_tenant`); la API impone el filtro en RAG y documentos generados; nombres tolerantes, reasignación sin reindexar y sitio reservado en el contexto para lo propio (`docs/EMPRESAS.md`); validado: sin fugas entre dos empresas | ⬜ permisos por usuario con varios usuarios |
| **Inferencia local** | ✅ | ✅ Ollama en contenedor con GPU (versión fijada); **auto-selección de modelo por VRAM** (`scripts/select-models`, la aplica `init`); `gemma4:26b-a4b-it-qat` en GPUs de 21-38 GB; limpieza opcional de modelos sin usar (`OLLAMA_PRUNE_UNUSED`). El modo profundo con AirLLM se evaluó y se retiró el 23-09 (`docs/BENCHMARKS.md`) | — |
| **Abstención sin evidencia** | ✅ | ✅ `packages/rag/orchestrator.py`; marca `insufficient_evidence` también cuando el modelo se abstiene con evidencia débil (criterio 14, 01-10) | — |
| **API + worker** | ✅ | ✅ FastAPI (`apps/api`) + arq (`apps/worker`) | — |
| **Infra reproducible** (Postgres/Redis/Qdrant, Docker) | ✅ | ✅ **todo Jarvis con `docker compose up`** (`docs/DOCKER.md`): `init` genera secretos y elige modelo, OpenClaw con voz y skills MCP en imagen propia, perfiles opcionales; `compose.cpu.yml` sin GPU; CI en cada PR (ruff, pyright, pytest, plugins, shellcheck y `compose config`) y construcción de las imágenes al publicar versión (`.github/workflows/ci.yml`) | — |
| **Embeddings** | ✅ | ✅ FastEmbed (denso + disperso) + reranker local (`RAG_RERANKER_MODEL`, `BAAI/bge-reranker-base`); la consulta se traduce también al inglés para encontrar documentación en inglés (23-09) | 🟡 reranker multilingüe (jina: mejor en español, licencia no comercial) |
| **Transporte Telegram** | 🟡 capa opcional | ✅ `integrations/openclaw`, config Telegram; indexación de PDFs recibidos con confirmación; entrega de documentos generados; menú de botones `/menu` (plugin `jarvis-menu`) y aprobación del envío de correo con botones (plugin `jarvis-aprobaciones`) | — |
| **Agente / orquestación** | 🟡 OpenClaw mencionado | ✅ OpenClaw + skills MCP (`jarvis-rag`, `jarvis-email`, `jarvis-calendar`, `jarvis-pm`, `jarvis-office`, vía `FastMCP`), plugins propios (`jarvis-menu`, `jarvis-aprobaciones`) y la skill de terceros revisada `agile-toolkit` | — |
| **Búsqueda web** | — | ✅ SearXNG **solo con permiso**: `web_search` está denegado; Jarvis busca primero en lo interno, sugiere aportar la documentación y, si se le autoriza, propone fuentes (`jarvis_web_sources`) y solo lee las aprobadas (`jarvis_web_read`, 23-09) | — |
| **Automatización** | — | ✅ n8n (perfil automation) | 🟡 flujos de correo/calendario |
| **Observabilidad** | ✅ supervisión | ✅ perfil `monitoring`: Prometheus, Grafana, sondas de cada servicio, GPU (DCGM), servidor y métricas HTTP de la API; alertas por Telegram (`docs/MONITORING.md`, 21-09), también `CopiaAtrasada` si pasan más de 26 h sin copia | — |
| **Voz local (STT/TTS)** | ✅ | ✅ whisper.cpp (AVX2) + Piper es_ES dentro de la imagen de OpenClaw | — |
| **Contestar correos** | ⬜ (roadmap) | ✅ MCP correo con backend IMAP/SMTP para cualquier proveedor (`packages/imapsmtp`) o Graph (`packages/msgraph/mail.py`); skill `jarvis-email`, borrador y envío aprobado con un botón de Telegram, fuera del modelo (`jarvis-aprobaciones`), adjuntos de doc-gen; cuenta Gmail de Jarvis configurada ; OpenProject envía sus avisos e invitaciones por la misma cuenta; correo → tarea (`pm_task_from_email`); validado el 18-09 con correos reales (invitaciones con .ics recibidas en Gmail) | ⬜ recibir en OpenProject respuestas por correo (IMAP entrante) |
| **Agendar / planificar reuniones** | ⬜ (roadmap) | ✅ MCP calendario con backend **OpenProject** (por defecto en la VM: la agenda son las reuniones de OpenProject y los vencimientos de tareas e hitos, `packages/openproject/calendar.py`), CalDAV o Graph; skill `jarvis-calendar`, propuesta→confirmación; invitaciones por OpenProject a sus usuarios y con .ics por el correo de Jarvis al resto; validado desde Telegram el 18-09 | ⬜ reuniones recurrentes, mover/cancelar reuniones, recordatorios proactivos por Telegram |
| **Generar documentos desde cero** | ⬜ (roadmap) | ✅ `packages/docgen` (resúmenes/DAFO/planes desde el RAG, docx/pptx/pdf/md, secciones en paralelo, entregados por Telegram con `MEDIA:`, `docs/DOCGEN.md`) y documentos Excel, Word, PowerPoint y OpenDocument a medida (`jarvis-office`, 21-09) | — |
| **Microsoft Teams** | ⬜ | 🟡 canal `msteams` soportado en OpenClaw (`scripts/configure-teams`, `docs/TEAMS.md`) | ⬜ **túnel público (Cloudflare Tunnel) + manifiesto de la app**, sin versionar todavía |
| **Licencia + gobernanza** | ⬜ declarado pendiente | ✅ `LICENSE` (MIT) + `CONTRIBUTING.md` | — |
| **Memoria evolutiva** | — | ✅ `memory-core` + `memory-wiki` de OpenClaw, vault Obsidian versionado en git privado (`vault-sync`), búsqueda semántica con `embeddinggemma` (`docs/MEMORY.md`) | 🟡 validar el árbol nuevo con un proyecto de punta a punta (guion de prueba preparado) |
| **Red de conocimiento / memoria única** | — | ✅ **un solo árbol** desde *🧭 Mapa de Jarvis*: empresas › {equipo, documentos, proyectos › {hitos, riesgos, reuniones › actas, tareas que pesan, documentos}} y conocimiento › {metodologías › documentos, documentación general, temas, directivas}; lo que cruza ramas son **nexos** (personas de varias empresas, metodologías por proyecto); nombres con icono por tipo y diagramas Mermaid; las notas se mueven con lo escrito a mano si cambian de rama (01-10); wiki de OpenProject sincronizada en ambos sentidos; `jarvis_remember` (`docs/OBSIDIAN.md`) | ⬜ personas deduplicadas con alias, relaciones entre riesgos y tareas, síntesis semanales automáticas |
| **Obsidian en móvil y portátil** | — | ✅ Self-hosted LiveSync: CouchDB por Tailscale + `livesync-bridge` con el vault, cifrado E2E (perfil `livesync`, `docs/OBSIDIAN.md`); iPhone configurado el 18-09; iPhone → vault sin reiniciar el puente y borrados propagados, validado el 21-09 | — |
| **Seguimiento y control de proyectos** | 🟡 (gestión del conocimiento; el seguimiento lo hace el PM a mano) | ✅ OpenProject 17.8 (perfil `pm`, `docs/OPENPROJECT.md`): empresas → proyectos, tareas, hitos, **riesgos**, Gantt y tableros por Tailscale; skill MCP `jarvis-pm` (9 herramientas) validada con Gemma: alta de riesgos, cambios de estado, informe de seguimiento, reuniones y correo → tarea desde el chat; simulación completa de un proyecto (Panadería La Espiga › Web corporativa) el 18-09 | ⬜ plantillas de proyecto (Water-Scrum-Fall), presupuesto y horas |
| **Actas de reunión automáticas** | 🟡 (STT local para notas de voz) | ✅ grabación → faster-whisper large-v3-turbo en GPU (1 h ≈ 2 min) → acta estructurada con Gemma (resumen, decisiones, acciones con responsable y fecha, riesgos) → PDF/Word, nota en Obsidian, RAG del proyecto y, con confirmación, tareas, riesgos y la **reunión cerrada con su acta** (decisiones y tareas como resultados) en OpenProject (`docs/ACTAS.md`); validado de punta a punta desde el agente | ⬜ separación de hablantes (diarización local) |
| **Acceso remoto al panel** | — | ✅ Tailscale en compose; panel de OpenClaw en `https://<host>.<tailnet>.ts.net` sin puertos abiertos, gateway solo en loopback (`docs/ACCESO-REMOTO.md`) | — |
| **Directivas y metodologías** | — | ✅ `MEMORY.md` de Jarvis por zonas (General, Metodologías, Proyectos) que él mismo mantiene (`jarvis_set_directive`, `jarvis_set_methodology`, `jarvis_set_project_methodology`); cada proyecto ve solo la documentación de su metodología; plantilla neutra, sin método impuesto (`docs/EMPRESAS.md`, 23-09) | — |
| **Administración del servidor** | — | ✅ servicio `admin` (perfil `admin`): reiniciar servicios y administrar OpenProject con aprobación, y cambios al repo como PR que fusiona el propietario (`docs/ADMIN.md`, 01-10) | 🟡 token de GitHub y `JARVIS_ADMIN_REPO` para probar `repo pr` |
| **Seguridad** | ✅ control de acceso | ✅ auditoría del 22-09 corregida: herramientas de archivos limitadas al workspace, `web_fetch` denegado, secretos fuera del entorno del agente, pandoc sin TeX en bruto, confirmaciones atómicas (`docs/SECURITY.md`) | — |
| **Directorio de servicios** | — | ✅ `jarvis_services` (Telegram/panel) y nota `SERVICIOS.md` en Obsidian: enlaces por Tailscale, IP del tailnet, direcciones internas con túnel SSH y estado en vivo, sin secretos (`packages/core/services.py`) | — |

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
`HybridRagOrchestrator.query(...)` (el mismo motor que `/ask`: sin
prompt ni retrieval nuevos, sin superficie de alucinación adicional; una
sección sin evidencia lo dice explícitamente en vez de inventar). Salida en
`.md`/`.docx`/`.pptx` (python-docx/python-pptx, ya dependencias del proyecto)
y `.pdf` (Pandoc + XeLaTeX vía subproceso, sin plantilla LaTeX vendorizada por
licencia; `scripts/install-docgen` o la imagen Docker). Expuesta como trabajo
asíncrono (`POST /v1/documents/generate`) y como
herramienta MCP `jarvis_generate_doc` en la skill `jarvis-rag`. El archivo
generado se entrega por Telegram (ver `docs/DOCGEN.md`).

**Fase 3 — Correo (borrador + aprobación) (✅ cerrada; IMAP/SMTP añadido el 15-09 para usarlo sin Azure; validada con correo real el 18-09; desde el 01-10 el envío se aprueba con un botón de Telegram).**
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
`jarvis_email_draft`; desde el 23-09 el envío se aprueba con un botón de Telegram,
fuera del modelo). El borrador+confirmación
reutiliza el `payload` genérico de `ConfirmationService` (añadido en
`feature/mcp-msgraph-base`) en vez de un mecanismo nuevo; scopes de Graph
necesarios: `Mail.Read`, `Mail.Send`.

**Fase 4 — Calendario / reuniones (✅ cerrada; CalDAV añadido el 15-09 y, desde el 18-09, OpenProject como calendario).** Nació en `feature/mcp-calendar`
(ver `docs/CALENDAR.md`). Sobre la base de `feature/mcp-msgraph-base`
(`packages/msgraph/calendar.py`: `get_calendar_view`/`create_event` vía Graph,
scopes `Calendars.Read`/`Calendars.ReadWrite`), expone `/v1/calendar/events`
(lectura) y el flujo **proponer → confirmar** de `/v1/calendar/draft` +
`/v1/calendar/draft/{token}/confirm`, reutilizando el campo genérico
`payload` de `ConfirmationService.request(...)` para guardar el evento
propuesto hasta la confirmación. Nuevo servidor MCP `jarvis-calendar`
(`jarvis_calendar_availability`, `jarvis_calendar_propose_event`,
`jarvis_calendar_confirm_event`) con la misma advertencia de siempre: **crear
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

**Fase 5.3 — OpenProject como centro: reuniones, calendario y correo (✅ 18 septiembre, rama `feat/sync-openproject-calendario-correo`).**
`CALENDAR_PROVIDER=openproject`: consultar y crear reuniones desde Telegram las deja en el
proyecto de OpenProject (o en "Agenda"), con invitación de OpenProject a sus usuarios y
.ics por el correo de Jarvis a los externos; la agenda incluye los vencimientos de tareas
e hitos. OpenProject envía por el SMTP de Jarvis y el admin tiene su correo, así las
invitaciones llegan a Gmail/Google Calendar y la suscripción iCal "Mis reuniones" las
lleva al iPhone. Las actas importadas quedan como reunión cerrada; `pm_meetings` y
`pm_task_from_email` en `jarvis-pm`. `scripts/check-integrations` comprueba que cada
integración responde de verdad.

**Fase 5.4 — Una sola memoria (✅ 18 septiembre, misma rama).**
Red de conocimiento en el vault (`packages/knowledge/red.py`, servicio `knowledge`):
empresas, proyectos, personas, hitos, riesgos, reuniones y documentos como notas enlazadas
con el frontmatter del wiki de OpenClaw; conceptos hub y nota raíz. `openproject-wiki-sync`
publica la nota de cada proyecto en la wiki de OpenProject y trae al vault sus páginas;
`jarvis_remember` escribe lo que el usuario pide recordar en esa misma red. Obsidian,
Jarvis y OpenProject comparten una memoria.

**Fase 6 — Endurecer y medir (✅ operación cerrada el 21-09; quedan la UAT y la medición).**
UAT con estos flujos, métricas de ahorro de tiempo (cierra el otro pendiente del
TFM), y decisión OpenClaw vs. cliente MCP ligero (Hermes/ZeroClaw). Tareas concretas:

* **Monitorización**: perfil `monitoring` adaptado a compose (Ollama, GPU con
  `dcgm-exporter`, API, CouchDB) y alertas básicas.
* **Copias de seguridad y restauración** probadas de PostgreSQL, Qdrant, estado de
  OpenClaw y CouchDB (criterios 21-22 de `docs/ACCEPTANCE.md`).
* **CI**: tests, ruff y pyright en cada PR, y construcción de las imágenes de compose.
* **Validaciones de punta a punta** (21-09): Obsidian móvil → vault sin reiniciar el
  puente, prueba sin Internet (criterio 27, `scripts/test-offline`). Correo y
  calendario (OpenProject) validados el 18-09.
* **CI de integraciones**: ejecutar `scripts/check-integrations` tras cada despliegue.
* **`docs/ACCEPTANCE.md`** actualizado el 21-09.
* Limpieza: rama remota `fix/openclaw-2026.9-deploy` borrada; imagen de `vault-sync`
  fijada en `alpine/git:v2.54.0` (01-10).

### 4.0 Estado al cierre del 18-09-2026

En `main`: OpenProject como centro de reuniones, calendario y correo (Fase 5.3) y una sola
memoria en Obsidian compartida con Jarvis y OpenProject (Fase 5.4). En la VM corren
`CALENDAR_PROVIDER=openproject`, los servicios `knowledge` y `openproject-wiki-sync`, y
`scripts/check-integrations` da 35/35. Simulación de referencia: Panadería La Espiga ›
Web corporativa (etiqueta `v0.6-simulacion` para el estado anterior).

### 4.0.1 Estado al 20-09-2026

* **Privacidad cerrada**: el workspace de OpenClaw son plantillas que se rellenan desde
  `.env` y del hardware detectado; el historial de git no necesita reescritura (no hay
  datos personales en ningún commit).
* **Memoria en dos capas**: árbol de empresa › proyecto › {hitos, riesgos, reuniones,
  tareas que pesan} y red de personas, documentos, actas y conceptos (`docs/OBSIDIAN.md`).
  Desplegado y migrado en la VM.
* **`pyright` vuelve a pasar** (eran 32 errores): ya no bloquea meterlo en la CI.
* **Datos de prueba retirados**: Acme Consulting › Migración ERP, Globex Corp › Portal
  Clientes y Panadería La Espiga › Web corporativa, con sus documentos del RAG y sus notas
  y actas del vault. Se conserva el PMBOK como documentación general y la etiqueta
  `v0.6-simulacion` como historia.
* **Proyecto de validación**: *Estudio Delta › App de reservas* (brief en el RAG, 4 tareas
  —una "En espera"—, 1 hito, 1 riesgo y la reunión de kick-off). Validado de punta a
  punta el 20-09: pregunta al RAG con cita del brief, resumen generado en PDF y en
  Markdown, red de conocimiento con el árbol nuevo, *Memoria de Jarvis* publicada en la
  wiki de los dos proyectos y `scripts/check-integrations` en **37/37**.

### 4.0.2 Estado al 01-10-2026

Entre el 21-09 y el 01-10 se fusionaron las PR #10 a #24:

* **Fuera**: AirLLM y el modo profundo (~37 s por token en la L4; criterios 5 y 16 retirados).
* **Agente**: menú de botones en Telegram, skill de terceros `agile-toolkit`, documentos
  Office a medida, directivas y metodologías por proyecto en `MEMORY.md`, búsqueda en
  internet solo con fuentes aprobadas, administración del servidor con aprobación y el
  envío de correo aprobado con un botón.
* **RAG**: la consulta también se traduce al inglés (el libro de Snyder aparece al preguntar
  en español) y la abstención queda marcada como `insufficient_evidence` (criterio 14).
* **Seguridad y documentación**: auditoría del 22-09 corregida e informe de coherencia de
  la documentación cerrado, salvo el caso G (si Teams sigue en el alcance).
* **Operación**: la copia perdida con la VM apagada se recupera al arrancar, con alerta
  `CopiaAtrasada`.
* **Memoria**: el vault pasa a ser **un solo árbol** unido por nexos (`docs/OBSIDIAN.md`).
* **Datos de prueba retirados** el 01-10 (Estudio Delta, Lab Métodos y 11LabsDLK en
  OpenProject, el RAG y el vault). Quedan el PMBOK y el libro de Snyder (metodología
  PMI) y las metodologías PMI y Scrum en `MEMORY.md`. `scripts/check-integrations`: **45/45**.

### 4.1 Qué queda (a 01-10-2026)

| Área | Pendiente | Prioridad |
|---|---|---|
| TFM | UAT con usuarios representativos y medición del ahorro de tiempo (el pendiente declarado en la memoria); decidir si hace falta la web de demo (Fase 5.1) o basta la demo en vivo por Telegram y Tailscale | Alta, según fecha de defensa |
| Validación | Proyecto de prueba de punta a punta con el árbol nuevo: audio → acta → OpenProject → árbol, nexos y wiki (guion preparado; base para la demo) | Alta |
| Operación | La copia al arrancar fallaba porque PostgreSQL aún no estaba listo: espera a PostgreSQL y Qdrant (`BACKUP_WAIT_SECONDS`, PR #25) | Alta |
| Admin | Token de GitHub de grano fino y `JARVIS_ADMIN_REPO` en `.env` para probar `repo pr` | Baja |
| Calendario | Mover y cancelar reuniones; reuniones recurrentes; recordatorio diario por Telegram ("qué tengo hoy", vencidos) con el cron de OpenClaw; huecos comunes | Media |
| Correo | Correo entrante en OpenProject (respuestas a avisos como comentarios) con un buzón aparte para no chocar con Jarvis; clasificación automática de la bandeja | Media |
| Proyectos | Plantillas Water-Scrum-Fall en OpenProject; horas y presupuesto; informe semanal automático | Media |
| Actas | Diarización (quién habla) local | Media |
| Memoria | Alias de personas (hoy solo se unen las variantes del propietario); síntesis semanal por proyecto; que las notas de persona también vayan a OpenProject; relaciones riesgo–tarea y decisiones en el frontmatter | Media |
| Multiusuario | Varias personas en Telegram con permisos por empresa/proyecto (RAG y OpenProject) | Media |
| Teams | Bloqueado por el registro de Azure Bot | Baja |
| Decisiones de Romen | Si Teams sigue en el alcance del TFM (caso G de `docs/DOC-COHERENCE-REPORT.md`); reranker multilingüe jina (mejor en español, licencia no comercial); publicar más servicios por Tailscale; rotar el token de Telegram y la contraseña de Gmail tras el TFM | — |

Cerrado desde la versión del 21-09: privacidad (20-09), operación de la Fase 6 (21-09),
`docs/ACCEPTANCE.md` (25 criterios ✅ y 2 retirados), validaciones de Obsidian móvil y sin
Internet (21-09), alerta de copia atrasada y abstención (01-10).

---

## 5. Las mejores "skills" (capacidades) para añadir al proyecto

Priorizadas por relación valor/esfuerzo para JARVIS-PMI:

1. ✅ **doc-gen** — generar documentos (.docx/.pptx/.md/.pdf) desde el corpus, con cita,
   reutilizando `HybridRagOrchestrator` sección a sección (ver `docs/DOCGEN.md`). *Alta / media.*
2. ✅ **mcp-host** — capa MCP en el worker (habilita todo lo demás). *Alta / media.*
3. ✅ **rag-as-mcp** — exponer tu propio RAG como servidor MCP (reutilizable por cualquier agente). *Alta / baja.*
4. ✅ **email-draft** — MCP de correo con borrador+aprobación. *Alta / media.*
5. ✅ **calendar** — MCP de calendario (CalDAV/Graph) para reuniones. *Media / media.*
6. 🟡 **teams-transport** (bloqueado por Azure Bot) — segundo canal Teams. *Media / media.*
7. ✅ **reranker** (`bge-reranker-base`; multilingüe pendiente) — reranker local para subir precisión de recuperación. *Media / baja.*
8. ⬜ **docling-ingest** — ingesta de PDFs escaneados/tablas con Docling. *Media / baja.*
9. ✅ **web-brief**, como fuentes aprobadas por el usuario (`jarvis_web_sources`) — usar tu SearXNG para informes con fuentes. *Baja / baja.*

> Nota: aquí "skills" son **capacidades del agente** (OpenClaw skills / servidores MCP),
> distintas de la *skill de Claude* para desarrollar el repo.

---

## 6. Fuentes (septiembre 2026)

- OpenClaw y alternativas locales/MCP: Composio, BuildBetter, Vellum.
- Estándar MCP y servidores (correo/calendario/Telegram/Teams): mcpservers.org, Composio, PulseMCP.
- Agente de correo 100% local: `microsoft/local-email-agent` (Foundry Local + MCP + LangChain).
