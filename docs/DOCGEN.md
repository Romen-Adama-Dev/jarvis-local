# Generación de documentos (doc-gen)

Jarvis puede producir un documento fundamentado en el corpus RAG: un DAFO
(`dafo`) o un plan de coordinación de proyecto (`plan`), en Markdown, `.docx`,
`.pptx` o `.pdf`. Es la Fase 2 de `docs/ROADMAP.md`.

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
jarvis_generate_doc(kind="plan", topic="Migración a Kubernetes", format="docx")
# -> "Generando plan sobre 'Migración a Kubernetes' en docx (trabajo <id>)..."
jarvis_job_result(job_id="<id>")
# -> resumen del documento (tipo, tema, formato, ruta, secciones sin evidencia)
```

## Limitación conocida

El archivo generado **no se envía automáticamente** por Telegram ni Teams
todavía: queda en el servidor, bajo `${JARVIS_DATA_DIR}/generated/<job_id>.<ext>`
(volumen `jarvis_srv` en despliegues Docker). La entrega del archivo al canal
de chat es trabajo futuro, fuera del alcance de esta fase; mientras tanto, la
skill informa al usuario de esta limitación al completar el trabajo.
