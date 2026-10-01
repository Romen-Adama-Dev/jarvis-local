# Pruebas con usuarios (UAT) y medición del ahorro de tiempo

Protocolo para cerrar el pendiente que declara la memoria del TFM: **pruebas de aceptación
con usuarios representativos** y **medición real del ahorro de tiempo**. Complementa los
benchmarks automáticos (`docs/BENCHMARKS.md`, "Benchmarks de Jarvis"), que miden el
sistema; aquí se mide lo que gana una persona al trabajar con él.

## Preguntas que responde

1. ¿Cuánto tiempo ahorra Jarvis en las tareas habituales de un *project manager*?
2. ¿El resultado es igual de bueno (o mejor) que haciéndolo a mano?
3. ¿Es fácil de usar? (escala SUS)
4. ¿Qué falla o confunde?

## Participantes

* **5 personas** (mínimo 3), con perfiles distintos: jefe de proyecto, miembro de un
  equipo o PMO, y alguien sin experiencia en gestión de proyectos (perfil novel).
* Ninguna ha usado Jarvis antes. Se les da 10 minutos de introducción con el
  [guion de ejemplo](#material) y la lista de cosas que se le pueden pedir.
* Datos **ficticios**: dos proyectos gemelos preparados para la prueba (ver "Material").
  Nadie trae documentación real; así no hay datos personales ni de clientes y la prueba
  se puede repetir.

## Diseño

**Intrasujeto con orden contrabalanceado.** Cada participante hace las mismas tareas de
dos formas: **sin Jarvis** (sus herramientas de siempre: PDF, Word/Excel, correo,
OpenProject en el navegador) y **con Jarvis** (Telegram). Para que no aprenda de la
primera vez, cada forma se hace sobre un proyecto distinto pero equivalente:

| Participante | Primera ronda | Segunda ronda |
|---|---|---|
| P1, P3, P5 | Sin Jarvis · proyecto A | Con Jarvis · proyecto B |
| P2, P4 | Con Jarvis · proyecto A | Sin Jarvis · proyecto B |

* **Proyecto A**: Talleres Norte › App de citas (reunión de arranque del guion de
  `docs/benchmarks/casos/reunion.json`).
* **Proyecto B**: Clínica Sur › Portal de pacientes, con la misma estructura: cuatro
  asistentes, tres decisiones, cuatro acciones y dos riesgos.

Las dos rondas el mismo día, con 10 minutos de descanso. Duración total: unas 2 h por
persona.

## Tareas

Cada tarea tiene un resultado comprobable y un tiempo máximo. Si se agota, se apunta como
no completada con el tiempo máximo.

| # | Tarea | Resultado que se pide | Máx. |
|---|---|---|---|
| T1 | Buscar en la documentación | Respuesta a 3 preguntas de la guía (p. ej. "¿qué es la variación del cronograma?"), con la página de donde sale | 15 min |
| T2 | Acta de una reunión | Acta de la grabación de 3 minutos: asistentes, decisiones, acciones con responsable y fecha, riesgos | 25 min |
| T3 | Pasar el acta a la herramienta | Las acciones y los riesgos dados de alta en OpenProject, con responsable y fecha | 15 min |
| T4 | Correo de seguimiento | Correo a los asistentes con decisiones y próximos pasos, listo para enviar | 10 min |
| T5 | Convocar la siguiente reunión | Reunión creada en el calendario con los asistentes | 5 min |
| T6 | Informe de estado | Informe con tareas abiertas, vencidas y riesgos del proyecto | 15 min |
| T7 | Documento desde una plantilla | Acta de constitución del proyecto con la estructura del libro de formularios | 20 min |
| T8 | Recuperar una decisión pasada | "¿Qué se decidió sobre el registro de usuarios y cuándo?" | 5 min |

## Qué se mide

| Métrica | Cómo | Dónde se apunta |
|---|---|---|
| **Tiempo** | Cronómetro desde que se lee la tarea hasta que el participante dice "listo" | `docs/uat/resultados.csv`, columna `segundos` |
| **Completada** | Sí/no, con la rúbrica de abajo | `completada` |
| **Calidad** | 0 (mal o incompleto), 1 (aceptable con fallos), 2 (correcto y completo), según la rúbrica de cada tarea | `calidad` |
| **Errores** | Datos inventados, omitidos o equivocados (un responsable o una fecha mal…) | `errores` |
| **Usabilidad** | Cuestionario SUS al acabar la ronda con Jarvis | `docs/uat/cuestionario-sus.md` |
| **Comentarios** | Lo que dice en voz alta (protocolo *think aloud*) y una entrevista de 5 minutos al final | `observaciones` |

**Rúbrica de calidad (2 puntos)**:

* T1: respuesta correcta y página correcta en las tres preguntas.
* T2: los 15 elementos del guion (fecha, 4 asistentes, 3 decisiones, 4 acciones con responsable y fecha, 2 riesgos, próxima reunión), igual que el benchmark de actas.
* T3: las 4 acciones y los 2 riesgos, con responsable y fecha.
* T4: decisiones y próximos pasos correctos, sin inventar nada.
* T5: fecha, hora y asistentes correctos.
* T6: refleja exactamente lo que hay en OpenProject.
* T7: todas las secciones del formulario, rellenas con lo que se sabe y marcando lo que falta.
* T8: la decisión correcta y su fecha.

## Análisis

Para cada tarea y participante: **ahorro = (tiempo sin Jarvis − tiempo con Jarvis) /
tiempo sin Jarvis**.

* Se da la **mediana y el rango intercuartílico** del ahorro por tarea y en total (con 5
  personas la media engaña).
* Diferencia de tiempos con la **prueba de Wilcoxon de rangos con signo** (muestras
  pareadas, sin suponer normalidad). Con n = 5 la prueba solo puede dar p < 0,05 si los
  cinco ahorran: se informa también el tamaño del efecto (r = Z/√n).
* La calidad se compara igual (0-2 por tarea): el ahorro solo cuenta si la calidad **no
  baja**.
* SUS: puntuación 0-100 por persona y media; 68 es la media de referencia del
  cuestionario.

## Criterios de aceptación

El TFM da por cumplido el objetivo si:

1. El ahorro mediano es **≥ 30 %** en al menos 5 de las 8 tareas.
2. La calidad con Jarvis es **igual o mejor** que sin Jarvis en al menos 6 de las 8 tareas.
3. **Ningún dato inventado** en lo que Jarvis entrega (T1, T2, T4, T6, T8).
4. **SUS ≥ 68**.

## Material

* **Guion de la reunión del proyecto A** (para grabarlo leído o reproducir el audio
  sintetizado): `docs/benchmarks/casos/reunion.json`. El del proyecto B se escribe con la
  misma estructura antes de la prueba.
* **Prueba guiada por Telegram** (cómo se pide cada cosa a Jarvis), la misma que sirve de
  demostración: crear empresa y proyecto → mandar el audio con "haz el acta" → "sí,
  créalo en OpenProject" → metodología del proyecto → recordar algo → pregunta al RAG →
  resumen en PDF. Ver `docs/DEMO.md`.
* **Documentación**: la que ya está indexada (Guía del PMBOK y libro de formularios de
  Snyder). Sin Jarvis, el participante la consulta en PDF.
* **Plantillas**: `docs/uat/resultados.csv` (una fila por participante, ronda y tarea) y
  `docs/uat/cuestionario-sus.md`.

## Antes de cada sesión

1. `scripts/backup` y `scripts/check-integrations` (todo en verde).
2. Cargar los proyectos A y B (vacíos de tareas) en OpenProject.
3. Cuenta de Telegram de prueba en `TELEGRAM_AUTHORIZED_USER_IDS` para el participante, o
   que use el móvil del responsable de la prueba.
4. Después: borrar lo creado (proyectos de OpenProject, sus carpetas en
   `entities/Empresas/` del vault y las actas indexadas).

## Privacidad

Los participantes no dan datos personales más allá de su perfil profesional (rol y años
de experiencia). Se apuntan con un código (P1…P5). Las grabaciones son del guion
ficticio. El consentimiento se pide por escrito antes de empezar, explicando que los
resultados se publican agregados y anónimos en la memoria del TFM.
