---
name: jarvis-rag
description: Consulta la documentación indexada de Jarvis (RAG local) y el estado del sistema
---

Usa las herramientas `jarvis_ask`, `jarvis_deep`, `jarvis_status`, `jarvis_models`,
`jarvis_disk`, `jarvis_jobs` y `jarvis_cancel_job` (servidor MCP `jarvis-rag`) para
todo lo relacionado con la documentación indexada y el estado de Jarvis. No uses
shell, `exec` ni ninguna otra herramienta genérica para esto: estas herramientas ya
hablan con la API de Jarvis de forma segura y auditada.

* `jarvis_ask`: consulta normal (Ollama). Úsala para la mayoría de preguntas.
* `jarvis_deep`: solo cuando el usuario pida explícitamente `/deep` o una tarea
  profunda sin urgencia. Puede no estar disponible todavía (AirLLM en construcción).
* Muestra siempre la respuesta completa devuelta por `jarvis_ask`/`jarvis_deep`,
  incluidas las fuentes: no las resumas ni las omitas.
* Si la herramienta indica que no hay evidencia suficiente, dilo tal cual al
  usuario. No inventes una respuesta alternativa.
* `jarvis_status`, `jarvis_models`, `jarvis_disk`, `jarvis_jobs` y
  `jarvis_cancel_job` responden directamente sin necesitar confirmación adicional.
* Cualquier acción administrativa o destructiva que no exista todavía como
  herramienta explícita (reiniciar servicios, borrar documentos, etc.) debe
  rechazarse: no existe una vía de shell arbitrario para realizarla.
