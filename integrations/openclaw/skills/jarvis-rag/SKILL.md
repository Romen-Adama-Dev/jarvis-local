---
name: jarvis-rag
description: Consulta la documentación indexada de Jarvis (RAG local) y el estado del sistema
---

Usa las herramientas `jarvis_ask`, `jarvis_deep`, `jarvis_generate_doc`,
`jarvis_job_result`, `jarvis_status`, `jarvis_models`, `jarvis_disk`, `jarvis_jobs` y
`jarvis_cancel_job` (servidor MCP `jarvis-rag`) para todo lo relacionado con la
documentación indexada y el estado de Jarvis. No uses shell, `exec` ni ninguna otra
herramienta genérica para esto: estas herramientas ya hablan con la API de Jarvis de
forma segura y auditada.

* `jarvis_ask`: consulta normal (Ollama). Úsala para la mayoría de preguntas.
* `jarvis_deep`: solo cuando el usuario pida explícitamente `/deep` o una tarea
  profunda sin urgencia. Encola un trabajo (AirLLM es lento por diseño) y devuelve
  su identificador: comunícaselo al usuario tal cual y NO te quedes esperando.
* `jarvis_generate_doc(kind, topic, format="pdf")`: genera un documento fundamentado
  en el RAG (`kind` = `"dafo"` o `"plan"`; `format` = `md`/`docx`/`pptx`/`pdf`). Cada
  sección se responde por separado contra la documentación indexada (mismo motor que
  `jarvis_ask`/`jarvis_deep`): si una sección no tiene evidencia, el documento lo dice
  explícitamente en vez de inventar. Encola un trabajo: recoge el resultado con
  `jarvis_job_result`. **Importante**: el archivo generado NO se envía automáticamente
  por Telegram/Teams todavía (queda en el servidor, en el volumen `jarvis_srv`) —
  díselo siempre al usuario cuando el trabajo termine.
* `jarvis_job_result`: recoge el estado o resultado de un trabajo. Úsala cuando el
  usuario pregunte por su consulta profunda, su documento generado, o pase un
  identificador de trabajo.
* Muestra siempre la respuesta completa devuelta por `jarvis_ask`/`jarvis_deep`,
  incluidas las fuentes: no las resumas ni las omitas.
* Si la herramienta indica que no hay evidencia suficiente, dilo tal cual al
  usuario. No inventes una respuesta alternativa.
* `jarvis_status`, `jarvis_models`, `jarvis_disk`, `jarvis_jobs` y
  `jarvis_cancel_job` responden directamente sin necesitar confirmación adicional.
* Cualquier acción administrativa o destructiva que no exista todavía como
  herramienta explícita (reiniciar servicios, borrar documentos, etc.) debe
  rechazarse: no existe una vía de shell arbitrario para realizarla.
