---
name: jarvis-pmi-roadmap
description: Resumen del TFM (memoria), estado real del repo frente a esa memoria, y plan de evolución (capa MCP, correo, calendario, generación de documentos, Teams)
---

# JARVIS-PMI · Resumen, estado y plan de evolución

> Documento de trabajo. Une tres cosas: qué dice la memoria (TFM), qué tiene ya el
> repositorio `jarvis-local`, y qué queremos añadir (agente: correo, reuniones,
> generación de documentos, Telegram/Teams). Fecha: septiembre 2026.

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
| **Inferencia local** (Ollama normal, AirLLM `/deep`) | ✅ | ✅ Ollama en host por GPU; `services/airllm`; **auto-selección de modelo por VRAM detectada** (`packages/core/hardware.py`, cerrado en `feature/model-autoselect`) | — |
| **Abstención sin evidencia** | ✅ | ✅ `packages/rag/orchestrator.py` | — |
| **API + worker** | ✅ | ✅ FastAPI (`apps/api`) + arq (`apps/worker`) | — |
| **Infra reproducible** (Postgres/Redis/Qdrant, Docker) | ✅ | ✅ `compose.yml` con profiles, `scripts/` idempotentes, `scripts/quickstart` "clona y arranca" | — |
| **Embeddings** | ✅ | ✅ FastEmbed (denso + disperso) | 🟡 reranker local (mejora recuperación) |
| **Transporte Telegram** | 🟡 capa opcional | ✅ `integrations/openclaw`, config Telegram | 🟡 endurecer (borrador→confirmación) |
| **Agente / orquestación** | 🟡 OpenClaw mencionado | ✅ OpenClaw + skill `jarvis-rag` | ⬜ **capa MCP** (estándar 2026) |
| **Búsqueda web** | — | ✅ SearXNG (perfil assistant) | — |
| **Automatización** | — | ✅ n8n (perfil automation) | 🟡 flujos de correo/calendario |
| **Observabilidad** | ✅ supervisión | ✅ Prometheus + Grafana, watchdog | — |
| **Voz local (STT/TTS)** | ✅ | 🟡 mencionada | 🟡 confirmar en repo |
| **Contestar correos** | ⬜ (roadmap) | ⬜ | ⬜ **MCP correo (borrador+aprobación)** |
| **Agendar / planificar reuniones** | ⬜ (roadmap) | ⬜ | ⬜ **MCP calendario (CalDAV/Graph)** |
| **Generar documentos desde cero** | ⬜ (roadmap) | ⬜ | ⬜ **skill doc-gen (docx/pptx/md)** |
| **Microsoft Teams** | ⬜ | ⬜ (solo Telegram) | ⬜ **MCP/conector Teams** |
| **Licencia + gobernanza** | ⬜ declarado pendiente | ⬜ | ⬜ **LICENSE + CONTRIBUTING** |

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

**Fase 0 — Base reproducible (cerrada en `feature/model-autoselect`).**
Auto-selección de modelo Ollama por VRAM detectada (`packages/core/hardware.py`,
`docs/BENCHMARKS.md`) y `scripts/quickstart` "clona y arranca". **LICENSE** (MIT)
y **CONTRIBUTING.md** → cierra el pendiente "open source formal" del TFM.

**Fase 1 — Capa MCP (fundacional).**
Introducir un cliente/host MCP en el worker o junto a OpenClaw. Primer servidor MCP
de prueba (p. ej. filesystem o el propio RAG expuesto como MCP). Criterio de éxito:
el agente llama a una herramienta MCP local y responde con trazabilidad.

**Fase 2 — Generación de documentos.**
*Skill* doc-gen: de una consulta RAG a un `.docx`/`.md` con fuentes citadas. Es la
más autónoma (no envía nada fuera) y la más lucida en demo.

**Fase 3 — Correo (borrador + aprobación).**
MCP de correo local. Flujo: leer → resumir → **redactar borrador** → confirmación
por Telegram → enviar. Reutiliza tu patrón de confirmación/TTL.

**Fase 4 — Calendario / reuniones.**
MCP de calendario (CalDAV o Graph). Leer disponibilidad, **proponer** hueco, crear
evento tras confirmación.

**Fase 5 — Segundo canal: Teams** (en marcha en `feature/mcp-teams-channel`).
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

**Fase 6 — Endurecer y medir.**
UAT con estos flujos, métricas de ahorro de tiempo (cierra el otro pendiente del
TFM), y decisión OpenClaw vs. cliente MCP ligero (Hermes/ZeroClaw).

---

## 5. Las mejores "skills" (capacidades) para añadir al proyecto

Priorizadas por relación valor/esfuerzo para JARVIS-PMI:

1. **doc-gen** — generar documentos (.docx/.pptx/.md) desde el corpus, con cita. *Alta / media.*
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
