# Estructura de desglose del trabajo (WBS)

Desglose orientado a entregables de Jarvis Local, del TFM al paso a producción. Cada
paquete de trabajo apunta a la evidencia que lo cierra en el repositorio. El estado es el
de `main` en noviembre de 2026; el seguimiento diario de tareas se hace en OpenProject
(ver [plan.md](plan.md)).

Leyenda de estado: hecho, en curso, pendiente, retirado.

| ID | Paquete de trabajo | Entregable | Estado | Evidencia |
|---|---|---|---|---|
| **1** | **Dirección del proyecto** | | | |
| 1.1 | Alcance y criterios de aceptación | 27 criterios con su forma de verificación | hecho (25 verificados, 2 retirados) | [ACCEPTANCE.md](../ACCEPTANCE.md) |
| 1.2 | Plan de fases y hoja de ruta | Fases 0 a 6 con criterio de cierre | hecho | [ROADMAP.md](../ROADMAP.md) |
| 1.3 | Viabilidad económica | BAC 10.625 €, presupuesto 11.156 €, VAN, TIR, ROI | hecho (memoria del TFM) | [ROADMAP.md](../ROADMAP.md), sección 1 |
| 1.4 | Registro de decisiones | Índice de decisiones con fecha y fuente | hecho | [decisiones.md](decisiones.md) |
| 1.5 | Gestión de riesgos del paso a producción | Registro RAID con responsables | en curso | [raid.md](raid.md) |
| **2** | **Plataforma base** (fase 0) | | | |
| 2.1 | Servicios de datos | PostgreSQL, Redis y Qdrant con health checks | hecho | `compose.yml` |
| 2.2 | API y worker | FastAPI (`apps/api`) y cola arq (`apps/worker`) | hecho | `apps/` |
| 2.3 | Inferencia local | `OllamaProvider` y router de inferencia | hecho | `packages/inference` |
| 2.4 | Selección de modelo | Benchmark de 4 modelos y selección por VRAM | hecho | [BENCHMARKS.md](../BENCHMARKS.md), [MODELS.md](../MODELS.md) |
| **3** | **RAG y documentos** | | | |
| 3.1 | Ingesta | Parsers, hash, deduplicación y chunking | hecho | `packages/documents` |
| 3.2 | Recuperación | Búsqueda híbrida, reranking y separación por empresa y proyecto | hecho | `packages/rag`, [EMPRESAS.md](../EMPRESAS.md) |
| 3.3 | Citas y abstención | Respuesta con documento y página; marca `insufficient_evidence` | hecho | `tests/unit/test_rag_abstention.py` |
| 3.4 | Consulta bilingüe | Traducción al inglés con glosario de ~450 términos | hecho | [GLOSARIO.md](../GLOSARIO.md) |
| **4** | **Agente y canal** (fase 1) | | | |
| 4.1 | Gateway del agente | OpenClaw con Telegram y lista blanca de usuarios | hecho | [OPENCLAW.md](../OPENCLAW.md), [TELEGRAM.md](../TELEGRAM.md) |
| 4.2 | Capacidades MCP | Skills `jarvis-rag`, `jarvis-pm`, `jarvis-email`, `jarvis-calendar`, `jarvis-office`, `jarvis-pdf` | hecho | `integrations/openclaw/skills` |
| 4.3 | Aprobación humana | Confirmación con botón de Telegram para toda acción externa | hecho | `packages/security`, [SECURITY.md](../SECURITY.md) |
| **5** | **Integraciones de gestión** (fases 2 a 5.4) | | | |
| 5.1 | Gestión de proyectos | OpenProject manejado desde Telegram (`jarvis-pm`) | hecho | [OPENPROJECT.md](../OPENPROJECT.md), `packages/openproject` |
| 5.2 | Correo | Leer, redactar y enviar con confirmación (IMAP/SMTP o Microsoft 365) | hecho | [EMAIL.md](../EMAIL.md) |
| 5.3 | Calendario | Reuniones de OpenProject, CalDAV o Microsoft 365 | hecho | [CALENDAR.md](../CALENDAR.md) |
| 5.4 | Actas | Audio a acta con faster-whisper, y tareas y riesgos a OpenProject si se confirma | hecho | [ACTAS.md](../ACTAS.md) |
| 5.5 | Documentos | DAFO, planes y resúmenes desde el RAG; Office y PDF a medida | hecho | [DOCGEN.md](../DOCGEN.md), [EDITORES.md](../EDITORES.md) |
| 5.6 | Memoria | Un árbol en Obsidian compartido con OpenProject | hecho | [OBSIDIAN.md](../OBSIDIAN.md), [MEMORY.md](../MEMORY.md) |
| 5.7 | Segundo canal (Teams) | | retirado (01-10-2026) | [ROADMAP.md](../ROADMAP.md), fase 5 |
| **6** | **Operación** (fases 5.2 y 6) | | | |
| 6.1 | Despliegue reproducible | `docker compose up` con perfiles opcionales | hecho | [DOCKER.md](../DOCKER.md) |
| 6.2 | Acceso remoto | Tailscale sin puertos abiertos | hecho | [ACCESO-REMOTO.md](../ACCESO-REMOTO.md) |
| 6.3 | Monitorización | Prometheus, Grafana y alertas por Telegram | hecho | [MONITORING.md](../MONITORING.md) |
| 6.4 | Copias de seguridad | Copia diaria y restauración probada (14/14 comprobaciones) | hecho | [BACKUP.md](../BACKUP.md) |
| 6.5 | Integración continua | ruff, pyright, pytest, shellcheck y `docker compose config` | hecho | `.github/workflows/ci.yml` |
| **7** | **Validación y transición** | | | |
| 7.1 | Benchmarks del sistema | RAG, traducción, actas y documentos medidos en la L4 | hecho | [BENCHMARKS.md](../BENCHMARKS.md) |
| 7.2 | Pruebas con usuarios (UAT) | 5 participantes, ahorro de tiempo y escala SUS | pendiente | [UAT.md](../UAT.md) |
| 7.3 | Demo de la defensa | Guion con proyecto ficticio | hecho | [DEMO.md](../DEMO.md) |
| 7.4 | Paso a producción | Piloto, formación y traspaso a operación | pendiente | [plan.md](plan.md), [raid.md](raid.md) |

## English summary

Deliverable-oriented WBS for Jarvis Local in seven branches: project management, base
platform, RAG, agent and channel, PM integrations, operations, and validation and
transition. Every work package links to the file or test that closes it. User acceptance
testing and the production rollout are the open packages.
