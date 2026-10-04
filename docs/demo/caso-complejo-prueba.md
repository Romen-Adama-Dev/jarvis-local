# Prueba: Jarvis monta dos clientes unidos con un solo mensaje

Prueba del 2 de octubre de 2026 en `jarvis-gpu-us` (OpenProject vacío, modelo local
`gemma4:26b-a4b-it-qat` en la L4, OpenClaw 2026.9.4). Referencia de lo que debería
quedar: [caso-complejo.md](caso-complejo.md).

## El mensaje

Uno solo, como lo diría el propietario en un audio de Telegram (sesión aislada con
`openclaw agent --session-key agent:main:demo-dos-empresas --message-file …`):

> Jarvis, tenemos dos clientes nuevos. Da de alta la empresa Talleres Norte con el
> proyecto App de citas, que va con Scrum, y la empresa Clínica Dental Sonrisas con el
> proyecto Web de la clínica, que va con Kanban. Los dos proyectos están unidos: la web de
> la clínica va a usar la reserva de citas que hacemos para Talleres Norte, así que la
> integración en la web no puede empezar hasta que la app salga a producción el 15 de
> diciembre. Mis empleados van a trabajar en los dos proyectos: Diego Sanz, desarrollador
> (diego.sanz@demo.invalid); Marta Ruiz, de calidad (marta.ruiz@demo.invalid), y Lucía
> Martín, diseñadora (lucia.martin@demo.invalid). Dalos de alta en OpenProject, mételos en
> los dos proyectos y reparte entre ellos el trabajo inicial de cada uno. Cuando acabes,
> dime qué has creado y si ves algún conflicto de carga.

## Resultado: 4 min 17 s

| Segundo | Qué había en OpenProject |
|---|---|
| 0 | Nada |
| 85 | Las dos empresas y sus dos proyectos |
| 255 | 3 tareas por proyecto; respuesta final a los 257 s |

**Lo que hizo bien**

* Empresas y proyectos con la jerarquía correcta (empresa → proyecto).
* Metodología de cada proyecto en `MEMORY.md` (`Talleres Norte › App de citas: Scrum`,
  `Clínica Dental Sonrisas › Web de la clínica: Kanban`) y una zona Kanban nueva.
* Repartió el trabajo: una tarea por persona y proyecto.
* Entendió la dependencia y la explicó al final, y avisó de que los empleados no estaban
  dados de alta.

**Lo que no hizo o hizo mal**

| Falta | Por qué |
|---|---|
| Dar de alta a los empleados y meterlos en los proyectos | `jarvis-admin op usuario-nuevo` necesita la aprobación del propietario. En una ejecución sin chat (terminal) OpenClaw la deniega: *"Headless runs cannot wait for interactive exec approval"*. Desde Telegram saldría el botón. |
| Asignar las tareas | Sin usuarios, puso el nombre en el título (`[Diego Sanz] …`). |
| Fechas | Ninguna tarea tiene fecha; tampoco creó el hito «Salida a producción» del 15-dic. |
| Dependencia entre proyectos | `jarvis-pm` no tiene herramienta de relaciones: la dejó como texto en el título. |
| Scrum según su zona | Creó «Tarea», no historias de usuario con puntos ni sprints (las reglas de Scrum de `MEMORY.md` piden historias). |
| Conflictos de carga | Sin fechas, asignados ni dependencias, la red no tiene con qué detectarlos; la respuesta de Jarvis es genérica. |
| Zona Kanban | Reglas genéricas («gestión visual», «límites WIP») sin el número del límite ni las clases de servicio. |

En la primera prueba (encargo largo con todo el detalle, cortada a los 7 minutos) creó en
5 minutos 2 empresas, 3 proyectos y 20 paquetes, pero **reescribió reglas de la zona Scrum**
que el propietario no había pedido cambiar. En esta no las tocó.

También salió a la luz que `AGENTS.md` (con la sección de `TOOLS.md` que OpenClaw le
añade) pasaba de 20.000 caracteres y se truncaba; ahora lo vigila
`tests/unit/test_agents_md.py`.

## Qué falta para que Jarvis construya el caso de referencia solo

1. **Probarlo desde Telegram** (mensaje o audio): las altas piden el botón de aprobación.
2. **Herramientas en `jarvis-pm`**: dependencias entre paquetes (`pm_relate`), padre,
   sprint y puntos al crear una tarea, horas estimadas e imputadas, y alta de personas y
   membresías con aprobación.
3. **Instrucciones**: en `AGENTS.md`, que al dar de alta un proyecto cree desde el principio
   las fechas, el hito final y el tipo de paquete de su metodología (historias en Scrum).

## Benchmark: terminal frente a Telegram (mismo mensaje)

Segunda pasada el mismo día, con OpenProject vaciado antes, el mismo mensaje inyectado en
la sesión de Telegram del propietario (`--session-key agent:main:main --deliver`, tras
`/new`). Tiempos sacados de la trayectoria de cada sesión
(`openclaw sessions export-trajectory`).

| | Terminal (sesión aislada) | Telegram (sesión del propietario) |
|---|---|---|
| Tiempo total | **4 min 17 s** | **6 min 32 s** |
| Turnos del modelo | 10 | 8 (uno vacío de 197 s) |
| Llamadas a herramientas | 23, en lotes paralelos | 6, de una en una |
| Tiempo dentro de las herramientas | ~4 s | ~3 s |
| Primer proyecto creado | 72 s | 54 s |
| Resultado | 2 empresas, 2 proyectos, metodologías, zona Kanban, 6 tareas sin asignar | 1 empresa y 1 proyecto; se rinde y pregunta |
| Aprobaciones pedidas | 0 (denegada por no tener chat) | 0 (no llegó a las altas) |

* **El cuello de botella es el modelo**: más del 98 % del tiempo es generación de
  `gemma4:26b` (20–35 s por turno en la L4); las herramientas tardan un segundo.
* **Mucha variación con el mismo mensaje**: en Telegram creó Talleres Norte dos veces
  (la segunda falló), intentó crear el proyecto de la clínica sin haber creado la empresa
  y, tras ese error, pasó 197 s en un turno que no produjo nada antes de rendirse.
* **Menos turnos = más rápido y más fiable**: en terminal agrupó cuatro altas en un solo
  turno. Una herramienta que monte empresa + proyecto + metodología + miembros de una vez
  quitaría la mitad de los turnos.

## Después: `pm_setup` y `pm_add_people` (3 pasadas)

Con una herramienta que monta cliente + proyecto + metodología + hito + equipo en una
llamada y altas con el botón de Telegram (`scripts/benchmark-demo --veces 3 --aprobar`):
**122 s de mediana** (115–122) frente a 257–392 s, 12 de 16 comprobaciones (hasta 14), y
las altas de los tres empleados hechas en todas las pasadas, con sus tareas asignadas
solas al aprobarlas. Detalle en docs/BENCHMARKS.md, «Benchmark de la demo».
