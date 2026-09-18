# Demo: probar Jarvis de punta a punta desde Telegram

Guion para enseñar (o probar) todos los servicios de Jarvis con un proyecto ficticio,
**Talleres Norte › App de citas**. Sirve para una demo en directo o para que otra persona
(p. ej. un tutor con su Telegram autorizado) lo pruebe sola. Dura unos 30-40 minutos.

## ¿Basta con mandar un audio?

En parte. Con la **grabación de una reunión** y una frase que diga de qué proyecto es,
Jarvis hace solo:

1. Transcribe la grabación en el servidor (faster-whisper con GPU, ~2 min por hora).
2. Redacta el acta: resumen, asistentes, decisiones, acciones con responsable y fecha,
   riesgos y próxima reunión. Te la manda en PDF.
3. La guarda en Obsidian (nota enlazada al proyecto y a los asistentes) y la indexa en el
   RAG del proyecto.
4. Te pregunta si la pasa a OpenProject. Si dices que **sí**: tareas, riesgos y la reunión
   cerrada con el acta.
5. En los 10 minutos siguientes la red de conocimiento de Obsidian y la página *Memoria de
   Jarvis* de la wiki de OpenProject se actualizan con todo lo anterior.

Lo que **no** hace solo con el audio (hay que pedírselo, como en el guion de abajo):
dar de alta la empresa o el proyecto en OpenProject (sin ellos no puede crear las tareas),
convocar la próxima reunión, enviar el acta por correo o generar otros documentos. Todo lo
que sale fuera del servidor (correos, invitaciones, tareas desde un acta) espera siempre un
"sí" explícito.

Un audio suelto, sin decir que es una reunión, Jarvis lo trata como una **nota de voz**:
lo transcribe, lo toma como una orden y contesta también con voz.

## Antes de empezar (quien administra el servidor)

* La persona que prueba tiene que estar en `TELEGRAM_AUTHORIZED_USER_IDS` (`.env`) y, para
  abrir los enlaces de OpenProject y Obsidian, en el tailnet de Tailscale
  (`docs/ACCESO-REMOTO.md`). Sin Tailscale todo funciona igual por Telegram; solo no se
  abren los enlaces.
* `scripts/check-integrations` sin fallos.
* Perfiles `pm`, `livesync` (o `vault`) y `tailscale` activos y `CALENDAR_PROVIDER=openproject`.
* Si hay conversación anterior, empieza con `/new` en Telegram para que no se mezcle.

## Guion del audio de la reunión (~2 minutos)

Grábalo con la grabadora del móvil (o como nota de voz de Telegram) leyendo con
naturalidad. **Cambia las fechas** por días reales de las dos semanas siguientes a la
demo y `<tu nombre>` por el tuyo. Si puedes, que lean dos o tres personas.

> Buenos días. Empezamos la reunión de arranque del proyecto App de citas de Talleres
> Norte. Hoy es lunes 5 de octubre. Estamos `<tu nombre>`, jefe de proyecto; Irene Soler,
> desarrolladora; y Pablo Vidal, gerente de Talleres Norte.
>
> Primer punto, el alcance. Pablo confirma que quiere reserva de citas para los tres
> talleres y un panel para el personal. Se decide que no habrá pagos online en esta
> versión.
>
> Segundo punto, los horarios. Pablo enviará los horarios de los tres talleres antes del
> viernes 9 de octubre. Irene advierte de que, si los horarios no llegan a tiempo, el
> calendario de reservas se retrasa una semana. Es un riesgo alto; como mitigación, Irene
> empezará con un horario genérico de nueve a dos y de cuatro a siete.
>
> Tercer punto, el correo. Los recordatorios pueden caer en spam porque el dominio del
> cliente no tiene SPF ni DKIM. `<tu nombre>` se encarga de configurarlos antes del
> miércoles 14 de octubre.
>
> Cuarto punto, el diseño. Irene tendrá las maquetas de la reserva listas el lunes 12 de
> octubre y Pablo las revisará en dos días.
>
> Se decide también que la salida a producción será el lunes 7 de diciembre. La próxima
> reunión será el viernes 16 de octubre a las diez para revisar las maquetas. Gracias a
> todos.

## Mensajes, paso a paso

Escríbelos (o díctalos como notas de voz) de uno en uno y espera la respuesta. Con el
modelo local cada respuesta tarda entre 10 segundos y 1 minuto; el acta, unos minutos.
Entre corchetes, lo que debería pasar.

### 1. Conocer a Jarvis

1. `¿Qué servicios tienes y dónde los abro?`
   [Directorio de servicios con enlaces por Tailscale y estado de cada uno]

### 2. Alta del proyecto

2. `Da de alta la empresa Talleres Norte y dentro el proyecto App de citas.`
   [Dos proyectos en OpenProject, con enlace]

### 3. Documentación y preguntas (RAG)

3. Adjunta `docs/demo/brief-app-citas.md` con el texto:
   `Indexa este brief en el proyecto App de citas de Talleres Norte.`
   [Pregunta si lo añade y a qué proyecto si no está claro; lo indexa]
4. `Según el brief, ¿qué presupuesto y qué plazo tiene App de citas?`
   [18.000 € y 10 semanas, citando el brief]
5. `¿Qué dice la documentación de App de citas sobre el número de empleados de Talleres Norte?`
   [Dice que no hay evidencia suficiente en vez de inventar]
6. `Según el PMBOK, ¿qué es un registro de riesgos?` *(solo si el PMBOK está indexado
   como documentación general)* [Respuesta citando la guía]

### 4. La reunión: acta automática

7. Envía el audio de la reunión con el texto:
   `Es la reunión de arranque de App de citas de Talleres Norte. Haz el acta.`
   [Avisa de que empieza; a los pocos minutos: resumen, decisiones, acciones, riesgos y el
   PDF del acta. Pregunta si lo pasa a OpenProject]
8. `Sí, pásalo a OpenProject.`
   [Tareas con responsable y fecha, riesgos y la reunión con el acta]

### 5. Seguimiento del proyecto

9. `Añade a App de citas el hito "Salida a producción" para el 7 de diciembre.`
10. `¿Cómo va App de citas?`
    [Informe: abiertos por estado, vencidos, próximos 7 días, hitos, riesgos, enlaces al
    Gantt y a los tableros]
11. `Pasa a en curso la tarea de las maquetas y comenta que Irene ya ha empezado.`
12. `¿Qué vence esta semana en App de citas?`

### 6. Calendario y reuniones

13. `Convoca la próxima reunión de App de citas el viernes 16 de octubre de 10:00 a 11:00
    por videollamada e invita a <correo de prueba>.`
    [Propuesta con resumen; pregunta si la crea]
14. `Sí.`
    [Reunión en OpenProject; invitación con .ics en el correo indicado]
15. `¿Qué tengo la semana que viene?`
    [Reuniones y vencimientos de todos los proyectos]

### 7. Documentos y correo

16. `Hazme un resumen del proyecto App de citas en PDF.`
    [Documento generado desde la documentación del proyecto, enviado por Telegram]
17. `Mándame ese resumen por correo a <correo de prueba>.`
    [Borrador con destinatario, asunto, cuerpo y adjunto; pregunta si lo envía]
18. `Sí, envíalo.`
19. `¿Qué correos nuevos tengo?` y después `Pasa el último correo a tarea de App de citas.`
    [Lista de la bandeja; tarea creada con el remitente y el texto del correo]

### 8. Memoria

20. `Recuerda que Pablo prefiere que le llamemos por la mañana y nunca los lunes.`
    [Lo anota en la nota de Pablo Vidal en Obsidian]
21. `¿Qué sabes de Pablo Vidal?`
    [Rol, proyecto, tareas, reuniones y la preferencia anotada]

### 9. Voz e Internet

22. Nota de voz: *"¿Qué riesgos tiene abiertos App de citas?"*
    [Transcribe, responde con texto y con voz]
23. `Busca en Internet qué es DKIM y resúmemelo en tres líneas.`
    [Búsqueda web con SearXNG, con enlaces]

## Qué comprobar fuera de Telegram

| Dónde | Qué debería verse |
|---|---|
| OpenProject (`https://<servidor>.<tailnet>.ts.net:8445`) | Talleres Norte › App de citas con tareas, riesgos e hito en el Gantt; en *Reuniones*, la reunión de arranque (cerrada, con el acta) y la convocada; en la *Wiki*, *Memoria de Jarvis* |
| Obsidian (móvil o portátil con LiveSync) | Nota *Red de conocimiento*; en la vista de grafo, Talleres Norte enlazada con el proyecto, las personas, riesgos, hito, reuniones, el acta y el brief (tarda hasta 10 min) |
| Correo de prueba | Invitación a la reunión con archivo .ics y el correo con el resumen en PDF |
| Servidor | `scripts/check-integrations` sigue sin fallos |

## Si algo no sale

* Jarvis dice que falta un dato: respóndele (es lo esperado si el mensaje es ambiguo).
* El acta tarda: las grabaciones largas tardan más; pregúntale `¿cómo va el acta?`.
* Grabaciones de más de 20 MB: Telegram no las entrega al bot; guárdalas en Obsidian o en
  `~/jarvis-inbox` y di su nombre (`docs/ACTAS.md`).
* Respuestas raras tras muchos mensajes: `/new` y repite el paso.

## Limpiar después de la demo

En OpenProject, *Talleres Norte → Configuración → Borrar* (borra también App de citas).
En Obsidian, borra las notas de Talleres Norte, App de citas, sus personas y el acta
(`sources/proyectos/app-de-citas/`). El brief y el acta indexados se quitan del RAG
desde la API (`DELETE /v1/documents/{id}`).
