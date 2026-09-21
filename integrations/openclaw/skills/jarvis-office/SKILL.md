---
name: jarvis-office
description: Crea documentos ofimáticos reales (Excel, Word, PowerPoint y OpenDocument) con tablas, negritas y totales
---

Usa `jarvis_make_document` (servidor MCP `jarvis-office`) cuando el usuario pida un
fichero de Office o LibreOffice con contenido que ya tienes o que redactas tú: «hazme un
Excel con…», «genera un acta en Word», «pásamelo a PowerPoint», «en formato ODS».

* `format`: `xlsx`, `docx`, `pptx`, `ods`, `odt` u `odp` (también vale `excel`, `word`
  o `powerpoint`).
* `blocks`: lista ordenada de bloques `heading` (con `level` 1-3), `paragraph` (admite
  `**negrita**`), `bullets` (`items`) y `table` (`name`, `columns`, `rows`, `total`).
  En hojas de cálculo cada tabla es una hoja con cabecera, filtros y, con `total`, una
  fila de totales con fórmulas; en presentaciones cada `heading` de nivel 1 abre una
  diapositiva.
* Pasa los números como números (`1200.5`), no como texto con moneda.
* La herramienta devuelve una línea `MEDIA:<ruta>`: termina la respuesta con ella, sola
  y sin formato, para que el archivo llegue por el chat.

Diferencias con otras herramientas:

* Un documento **fundamentado en la documentación indexada** (resumen, DAFO, plan) es
  `jarvis_generate_doc` (jarvis-rag), que cita fuentes.
* Las **tareas de un proyecto de OpenProject** a Excel son `pm_export_tasks` (jarvis-pm).

No envía nada a nadie: solo crea el fichero. Mandarlo por correo sigue pasando por el
borrador y el «sí» del usuario.
