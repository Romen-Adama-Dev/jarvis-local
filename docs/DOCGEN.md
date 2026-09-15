# Generación de documentos (doc-gen)

Jarvis puede producir un documento fundamentado en el corpus RAG: un resumen de
un tema o de un documento indexado (`resumen`), un DAFO (`dafo`) o un plan de
coordinación de proyecto (`plan`), en Markdown, `.docx`, `.pptx` o `.pdf`, y
enviarlo por el chat. Es la Fase 2 de `docs/ROADMAP.md`.

## Cómo funciona

No hay generación libre ni prompt nuevo. Cada tipo de documento define una
lista fija de secciones (`packages/docgen/templates.py`), cada una con una
pregunta en español. Por cada sección se llama una vez a
`HybridRagOrchestrator.query(...)` — el mismo motor que usan `/ask` y `/deep`:
recuperación híbrida, reranking, presupuesto de contexto y generación
fundamentada. Si una sección no tiene evidencia en la documentación indexada,
el documento lo dice explícitamente en esa sección en vez de inventar
contenido; el resto de secciones no se ven afectadas. Esto significa que
doc-gen no introduce ninguna superficie nueva de alucinación: hereda las
mismas garantías de abstención y citación de fuentes que el resto del RAG.

Es un trabajo asíncrono (`arq`), igual que `/deep`: la API devuelve un
identificador de trabajo (HTTP 202) y el resultado se recoge después.

## Formatos y dependencias

| Formato | Librería | Dependencia extra |
|---|---|---|
| `md` | — | ninguna |
| `docx` | `python-docx` | ninguna (ya es dependencia del proyecto) |
| `pptx` | `python-pptx` | ninguna (ya es dependencia del proyecto) |
| `pdf` | Pandoc + XeLaTeX (subproceso) | `scripts/install-docgen` (bare-metal) o la imagen Docker, que ya los incluye |

El PDF se genera renderizando primero el Markdown y pasándolo por
`pandoc --pdf-engine=xelatex` (sin plantilla LaTeX propia, por licencia: solo
márgenes, tabla de contenidos y `DejaVu Serif` para acentos/ñ). Si pandoc o
xelatex no están instalados, la API/worker devuelven un error
`provider_unavailable` señalando `scripts/install-docgen` en vez de fallar
de forma confusa.

## Uso

### Vía API

```bash
curl -X POST http://127.0.0.1:8000/v1/documents/generate \
  -H "Authorization: Bearer $JARVIS_API_INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"kind": "dafo", "topic": "Proyecto Fénix", "format": "pdf"}'
# -> {"id": "...", "status": "queued", ...}

curl http://127.0.0.1:8000/v1/documents/generated/<job_id> \
  -H "Authorization: Bearer $JARVIS_API_INTERNAL_TOKEN" \
  -o fenix-dafo.pdf
# 409 si el trabajo aún no ha terminado; sigue el progreso con GET /v1/jobs/<job_id>
```

### Vía la skill MCP `jarvis-rag`

```
jarvis_generate_doc(kind="resumen", topic="Guía del PMBOK 7ª edición", format="pdf")
# (espera a que el trabajo termine, hasta DOCGEN_WAIT_SECONDS)
# -> "Documento generado (trabajo <id>): resumen sobre '...' en pdf.
#     ...
#     MEDIA:/home/<usuario>/.openclaw/workspace-jarvis/outbox/resumen-guia-del-pmbok-7a-edicion-<id>.pdf"
jarvis_job_result(job_id="<id>")
# -> lo mismo, si la espera se agotó antes de terminar
```

## Entrega por el chat

El archivo se genera en el servidor, bajo `${JARVIS_DATA_DIR}/generated/<job_id>.<ext>`
(volumen `jarvis_srv` en Docker), fuera del alcance del gateway de OpenClaw. Cuando el
trabajo termina, la skill `jarvis-rag` lo descarga con
`GET /v1/documents/generated/<job_id>` a `JARVIS_OUTBOX_DIR` (por defecto
`~/.openclaw/workspace-jarvis/outbox`, dentro del workspace del agente) y devuelve una
línea `MEDIA:<ruta>`. El agente la copia al final de su respuesta y OpenClaw adjunta el
archivo en Telegram (protocolo `MEDIA:` de OpenClaw; la regla está en el `AGENTS.md`
del workspace).

La skill espera hasta `DOCGEN_WAIT_SECONDS` (540 s por defecto) para que un modelo local
no tenga que sondear el trabajo: con `qwen2.5:32b` en una L4 un resumen de 4 secciones
tarda unos 4 minutos. Esa espera debe quedar por debajo del `requestTimeoutMs` del
servidor MCP `jarvis-rag` en `openclaw.json` (600 000 ms en la plantilla); si la
generación tarda más, la herramienta devuelve el identificador y `jarvis_job_result`
hace la entrega después.

El mismo documento se puede adjuntar a un correo con
`jarvis_email_draft(..., attachment_job_id="<id>")` (ver `docs/EMAIL.md`). El outbox no
se limpia solo.
