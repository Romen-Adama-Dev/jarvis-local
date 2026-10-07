---
name: jarvis-pdf
description: Trabaja con PDF (unir, dividir, extraer, borrar o girar páginas, contraseña, formularios, marca de agua y reducir) con PrintCraft
---

Usa las herramientas del servidor MCP `jarvis-pdf` cuando el usuario quiera hacer algo
con un PDF que te ha enviado o que ya creaste: «únelos», «sepárame las páginas», «quita
la página 4», «gíralo», «ponle contraseña», «rellena este formulario», «ponle BORRADOR»,
«hazlo más ligero para el correo».

* `file` / `files`: el nombre del adjunto tal como aparece en `<file name="...">`, o el de
  un PDF que devolvió otra herramienta (outbox). No hace falta la ruta.
* `jarvis_pdf_combine(files)` une en el orden dado; `jarvis_pdf_split(file, every)` parte
  cada `every` páginas (más de 10 partes llegan en un ZIP).
* `jarvis_pdf_extract_pages(file, pages="3-5, 8")` y `jarvis_pdf_edit_pages(file,
  delete="2", rotate="1", degrees=90)`: los números son los del PDF original.
* `jarvis_pdf_protect(file, password)`: no repitas la contraseña en la respuesta.
* `jarvis_pdf_form(file)` lista los campos; `jarvis_pdf_form(file, values={...})` con los
  nombres exactos de esa lista devuelve el PDF relleno.
* `jarvis_pdf_watermark(file, text)` y `jarvis_pdf_compress(file)`.
* Cada herramienta devuelve una o varias líneas `MEDIA:<ruta>`: termina la respuesta con
  ellas, cada una sola en su línea y sin formato, para que los archivos lleguen por el
  chat.

El original nunca se modifica: el resultado es siempre un PDF nuevo en el outbox. No
pregunta si el adjunto va al RAG: eso solo es para `jarvis_upload` (jarvis-rag).
Mandarlo por correo sigue pasando por el borrador y el «sí» del usuario.
