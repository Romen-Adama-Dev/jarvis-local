# Guion de la demo: Jarvis por voz y por texto

Dos guiones cortos para enseñar Jarvis en directo por Telegram, ensayados paso a paso con
`scripts/ensayo-demo` el 4 de octubre de 2026 (NVIDIA L4, `gemma4:26b-a4b-it-qat` con 64k
de contexto, OpenClaw 2026.9.4). Los tiempos son los medidos. El recorrido largo, con todos
los servicios, sigue en [../DEMO.md](../DEMO.md).

* **Por voz** (≈ 12 minutos): un cliente nuevo con un proyecto PMI, consulta al PMBOK,
  acta de una reunión grabada, acta de constitución en Word, Excel, reunión en el
  calendario y memoria. Todo con notas de voz salvo la grabación de la reunión.
* **Por texto** (≈ 10 minutos): dos clientes con un mismo equipo y una dependencia entre
  ellos, un brief al RAG con preguntas citadas y una sin evidencia, PDF, correo con botón
  de aprobación, PowerPoint, Internet con fuentes aprobadas y conflictos de carga.

Se pueden mezclar: la voz luce más en las órdenes cortas y el texto en lo que lleva
correos o mucho detalle.

## Antes de empezar (15 minutos antes)

1. **Escenario limpio.** `scripts/vaciar-demo docs/demo/guion-voz.json docs/demo/guion-texto.json`
   borra lo que crean los guiones (y sus ensayos) y nada más; pide confirmación.
2. **Vocabulario de la voz.** En `.env`, `STT_VOCABULARY` con los nombres que vas a decir
   (`Talleres Norte, Gijón, App de citas, Snyder, Clínica Dental Sonrisas, Pablo Vidal,
   Diego Sanz, Marta Ruiz, Lucía Martín`) y, si lo cambias,
   `docker compose up -d openclaw worker`. Sin él whisper oye «Jijón» y Jarvis crea el
   proyecto con ese nombre.
3. **Documentación general**: el PMBOK y el libro de formularios de Snyder indexados como
   documentación general de PMI (`jarvis_list_projects` los enseña).
4. **Calentar a Jarvis.** En Telegram, `/new` y «Hola Jarvis». La primera respuesta tras
   reiniciar Ollama u OpenClaw tarda de 1 a 4 minutos (procesa sin caché unos 24.000 tokens
   de instrucciones); las siguientes, segundos.
5. **La grabación de la reunión**: léela con otras personas desde
   [reunion-arranque-gijon.txt](reunion-arranque-gijon.txt) y grábala con la grabadora del
   móvil (pesará más de 1 MB: así va directa al acta). O genera una con Piper: es la que
   usa `scripts/ensayo-demo docs/demo/guion-voz.json`.
6. Abre en el portátil OpenProject y Obsidian (por Tailscale) para enseñar lo que aparece.

## Guion por voz

Cada fila es una nota de voz (mantén pulsado el micrófono en Telegram), salvo la 4.
*Whisper* es lo que tarda la transcripción en el servidor; *Jarvis*, desde que la recibe
hasta que contesta.

| # | Di | Qué pasa | Whisper + Jarvis |
|---|---|---|---|
| 1 | «Hola Jarvis. Tenemos un cliente nuevo: Talleres Norte. Da de alta su proyecto Apertura del taller de Gijón, que va con PMI y termina con la inauguración el quince de enero de dos mil veintisiete.» | Empresa, proyecto, metodología PMI en `MEMORY.md` e hito «Inauguración» del 15-01-2027, con enlace | 16 + 31 s |
| 2 | «Según el PMBOK, ¿qué debe incluir el acta de constitución de un proyecto?» | Respuesta de la documentación indexada citando documento y página | 14 + 38 s |
| 3 | «¿Qué es la ruta crítica y cómo se dice en inglés?» | Glosario propio: *critical path* y su definición | 13 + 8 s |
| 4 | *Envía la grabación de la reunión* con el texto «Es la grabación de la reunión de arranque del proyecto de Gijón. Haz el acta.» | Transcribe en GPU y te manda el acta (PDF): resumen, 3 decisiones, 4-5 acciones con responsable y fecha, el riesgo de la licencia y la próxima reunión. La guarda en Obsidian y en el RAG del proyecto, y pregunta si la pasa a OpenProject | 62-91 s |
| 5 | «Sí, pásalo a OpenProject.» | Acciones como tareas con responsable y fecha, el riesgo y la reunión cerrada con el acta | 13 + 15 s |
| 6 | «Prepara el acta de constitución del proyecto de Gijón en un documento de Word, con la plantilla de Snyder y lo que se decidió en la reunión. El patrocinador es Pablo Vidal.» | Un Word con justificación, requisitos, riesgos, hitos, presupuesto y límites de autoridad sacados de la reunión | 14 + 42 s |
| 7 | «¿Cómo va el proyecto de Gijón?» | Informe: abiertos, vencidos, próximos 7 días, hitos, riesgos y enlaces al Gantt y al tablero | 13 + 16 s |
| 8 | «Exporta las tareas del proyecto de Gijón a Excel.» | El Excel, como archivo | 13 + 7 s |
| 9 | «Convoca la próxima reunión de seguimiento del proyecto de Gijón el viernes treinta de octubre de diez a once.» | Propuesta con los datos; pregunta si la crea | 14 + 20 s |
| 10 | «Sí, confírmala.» | Reunión en OpenProject con su enlace | 12 + 6 s |
| 11 | «Recuerda que Pablo Vidal prefiere que le llamemos por la mañana y nunca los lunes.» | Nota de Pablo Vidal en Obsidian | 13 + 6 s |
| 12 | «¿Qué sabes de Pablo Vidal?» | Cargo, proyecto, su tarea de la licencia y la preferencia | 12 + 24 s |

En total, unos 8 minutos de espera (2,5 de whisper y 5 de Jarvis), sin contar lo que tardas
en hablar ni lo que dura cada respuesta.

**Para que la voz salga bien**

* **Frases completas y los nombres en medio o al final.** «Prepara… en un documento de
  Word» se entiende; «Hazme en Word…» al principio de la nota se oye «Adam Enworth».
* **Confirma con «Sí, adelante» o «Sí, confírmala».** «Sí, créala» se oye «Sí, Corea».
* **Jarvis contesta con voz solo a las notas de voz**, y si la respuesta pasa de 500
  caracteres la voz es un resumen y el texto completo va escrito (`TTS_MAX_CHARS`). Las
  respuestas con un archivo (Word, Excel, PDF) llegan sin voz.
* Los meses y años dichos en letra se convierten bien en fechas («el quince de enero de
  dos mil veintisiete» → 2027-01-15).

## Guion por texto

| # | Escribe | Qué pasa | Jarvis |
|---|---|---|---|
| 1 | `¿Qué servicios tienes y dónde los abro?` | Directorio de servicios con enlaces por Tailscale y estado | 18 s |
| 2 | `Tenemos dos clientes nuevos. Talleres Norte, con el proyecto App de citas, que va con Scrum y sale a producción el 15 de diciembre. Y Clínica Dental Sonrisas, con el proyecto Web de la clínica, que va con Kanban. En los dos proyectos trabajan Diego Sanz, desarrollador (diego.sanz@demo.invalid), Marta Ruiz, de calidad (marta.ruiz@demo.invalid), y Lucía Martín, diseñadora (lucia.martin@demo.invalid). Dalos de alta y reparte el trabajo inicial de cada proyecto entre ellos.` | Dos empresas y proyectos con su metodología (Kanban con reglas de serie) y hito final, una tarea por persona y proyecto con fecha, y el aviso **👥 Altas en OpenProject** con el botón *Dar de alta*: al pulsarlo se crean las cuentas y se les asignan sus tareas | 86-90 s |
| 3 | `La integración de la web de la clínica no puede empezar hasta que App de citas salga a producción. Enlázalas en OpenProject.` | Dependencia entre las dos empresas en el Gantt (hito de la app → integración) | 16 s |
| 4 | *Adjunta* [brief-app-citas.md](brief-app-citas.md) con `Es el brief de App de citas de Talleres Norte: añádelo a la documentación de ese proyecto.` | Lo indexa en ese proyecto sin más preguntas (si no dices dónde, pregunta) | 27 s |
| 5 | `Según el brief, ¿qué presupuesto y qué plazo tiene App de citas?` | 18.000 € y 10 semanas, citando el brief | 10 s |
| 6 | `¿Y cuántos empleados tiene Talleres Norte?` | Dice que no hay evidencia en la documentación en vez de inventar | 28 s |
| 7 | `Hazme un resumen de App de citas en PDF.` | PDF generado de la documentación del proyecto, con fuentes | 42 s |
| 8 | `Mándaselo por correo a Pablo Vidal, pablo.vidal@demo.invalid, con un texto corto.` | Borrador con el PDF adjunto; te llega a Telegram con **Enviar / Descartar** (Jarvis no puede enviarlo) | 14 s |
| 9 | `Hazme un PowerPoint de 4 diapositivas con el plan del primer sprint de App de citas.` | El PowerPoint, como archivo | 51 s |
| 10 | `Busca en internet qué es DKIM.` | Solo la lista de fuentes y pregunta cuáles usar: nada de Internet sin tu aprobación | 20 s |
| 11 | `Usa la 1 y la 2.` | Respuesta con esas dos fuentes, citadas y marcadas como de Internet | 9 s |
| 12 | `¿Ves algún conflicto de carga entre los dos clientes?` | Las mismas personas con entregas la misma semana en las dos empresas | 43 s |

En total, unos 6 minutos de espera. En una demo real usa direcciones de correo tuyas en
lugar de las de `demo.invalid`, y pulsa *Descartar* si no quieres enviar el correo.

**Lo que no hace bien aún**: si la dependencia va dentro del mensaje largo del paso 2,
Jarvis la menciona pero no la crea (ni con `after` en `pm_create_task`); por eso va en un
mensaje aparte, donde la crea siempre.

## PDF por Telegram (opcional)

Los PDF de prueba están en [pdf/](pdf/) (datos ficticios de Talleres Norte). Encadena las
operaciones sobre el PDF unido sin volver a adjuntarlo.

| # | Escribe | Qué pasa | Jarvis |
|---|---|---|---|
| 1 | *Adjunta* `presupuesto-app-citas.pdf` y `anexo-condiciones.pdf` con `Únelos en un solo PDF: primero el presupuesto y luego el anexo.` | Un PDF de 3 páginas en ese orden | 24 s |
| 2 | `Ahora ponle la contraseña Norte2026 al PDF unido.` | El unido con contraseña (AES-256); no la repite en el chat | 6 s |
| 3 | `Del presupuesto que te pasé, sácame solo la página 2, la del calendario.` | PDF de una página | 8 s |
| 4 | `Al PDF unido ponle una marca de agua que diga BORRADOR.` | BORRADOR en diagonal en las 3 páginas | 15 s |
| 5 | `Divide el PDF unido en páginas sueltas.` | Tres PDF | 15 s |
| 6 | *Adjunta* `solicitud-acceso.pdf` con `¿Qué campos tiene este formulario?` | Nombre, Empresa, Correo y la casilla Acepto | 6 s |
| 7 | `Rellénalo: Ana Pérez, de Talleres Norte, ana.perez@demo.invalid, y marca que acepta las condiciones.` | El formulario relleno | 11 s |
| 8 | *Adjunta* `presupuesto-app-citas.pdf` con `Sácame la página 2 de este presupuesto y mándasela por correo a Ana Pérez, ana.perez@demo.invalid, con un texto corto.` | Borrador con la página en PDF adjunta (nombre y tamaño en el aviso de Telegram); pulsa *Descartar* | 28 s |

Unos 2 minutos de espera en total. En el navegador, el mismo PDF se abre en PrintCraft
(`https://<nombre>.ts.net:8446`, `docs/EDITORES.md`).

## Qué enseñar fuera de Telegram

| Dónde | Qué |
|---|---|
| OpenProject | Las empresas y proyectos con su metodología; el Gantt con hitos y la dependencia entre empresas; la reunión de arranque cerrada con su acta y la convocada |
| Obsidian | En *🧭 Mapa de Jarvis*, la empresa con su proyecto, el equipo, el acta colgando de la reunión y la nota de Pablo Vidal; los conflictos en *🕸 Nexos* (tarda hasta 10 minutos) |
| Telegram | Los archivos (acta en PDF, Word, Excel, PowerPoint) y los botones de aprobación |

## Si algo no sale

* **Jarvis tarda minutos en la primera respuesta**: no estaba caliente (paso 4 de la
  preparación). Espera; no mandes otro mensaje encima.
* **Transcribe mal un nombre**: dilo otra vez en la frase siguiente o escríbelo; si es un
  nombre que vas a repetir, añádelo a `STT_VOCABULARY`.
* **El acta no sale**: la grabación de más de 20 MB no llega por Telegram (guárdala en
  Obsidian o en `~/jarvis-inbox` y di su nombre); si se agota la espera, «¿cómo va el acta?».
* **Respuestas raras tras muchos mensajes**: `/new` y repite el paso.

## Ensayarlo

```bash
scripts/ensayo-demo docs/demo/guion-voz.json          # notas de voz simuladas
scripts/ensayo-demo docs/demo/guion-texto.json --desde 3 --hasta 5
scripts/ensayo-demo docs/demo/guion-pdf.json           # PDF (jarvis-pdf)
scripts/vaciar-demo docs/demo/guion-voz.json docs/demo/guion-texto.json
```

`ensayo-demo` manda cada paso a una sesión nueva de Jarvis como le llegaría por Telegram:
las notas de voz las dice Piper y las transcribe el mismo whisper, con el mismo
vocabulario, que usa OpenClaw. Mide la transcripción, el tiempo de Jarvis, las
herramientas, los archivos y cuánto duraría la respuesta hablada. No borra nada ni pulsa
botones (los correos y las altas te llegan a Telegram). Guarda los resultados en
`~/jarvis-ensayos/`, fuera del repo, porque las respuestas llevan los enlaces del servidor.

## Cómo se llegó a este guion (4 de octubre de 2026)

| Ensayo | Qué falló | Arreglo |
|---|---|---|
| Voz v1 | Cada mensaje tardaba 30-60 s de más: con 32k de contexto, OpenClaw compactaba la conversación tras cada respuesta (dos llamadas más a Gemma) | Contexto de 64k para la L4 (docs/MODELS.md): 0 compactaciones en los ensayos; el glosario pasa de 49 a 8 s y el informe de 68 a 16 s |
| Voz v1 | Whisper oía «Jijón», «pemboquet», «Schneider», «Axel» y «muerce» (por Gijón, PMBOK, Snyder, Excel y «en Word»), y tardaba 21-30 s por nota | Vocabulario en el `--prompt` de whisper (`STT_VOCABULARY`), idioma fijo y un hilo por núcleo físico: nombres bien y ~13 s por nota |
| Voz v1 | El acta: Jarvis no ve el nombre del audio, se lo inventaba, la herramienta no lo encontraba y acababa redactando el acta él mismo (400 s) | La herramienta usa la grabación más reciente si el nombre no existe, y `AGENTS.md` dice que el acta siempre la hace la herramienta: 62-91 s, con PDF y paso a OpenProject |
| Voz v1 | La grabación de la reunión se transcribía dos veces (CPU en OpenClaw y GPU en el worker) | Las grabaciones de más de 1 MB van directas a la herramienta |
| Voz v1-v2 | «Hazme en Word el acta de constitución» al principio: sin datos, Jarvis pedía más información o lo escribía en el chat | Después de la reunión, con «en un documento de Word» en medio de la frase: Word en 42 s |
| Voz v2 | Respuestas habladas de 45-60 s | Resumen hablado a partir de 500 caracteres; regla de respuesta corta para notas de voz |
| Texto v1 | Al recibir el brief, Jarvis pegaba sus instrucciones («Si dice que no, no lo indexes…») | Pregunta con sus palabras y, si ya le dices dónde, indexa sin preguntar |
| Texto v1 | Las fuentes salían como `input-PMBOK-7Ed---<uuid>.pdf` y Jarvis no citaba página | La herramienta da «PMBOK-7Ed (pág. 34)» y pide citar documento y página |
