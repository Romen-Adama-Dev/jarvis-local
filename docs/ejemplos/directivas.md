# Ejemplos de directivas

Jarvis empieza sin método de trabajo: su `MEMORY.md` viene vacío de directivas y es cada
usuario quien le dice cómo trabaja, desde el chat ("a partir de ahora…"). Jarvis lo
escribe en `MEMORY.md` y lo aplica desde el siguiente mensaje (ver "Directivas de Jarvis"
en [OBSIDIAN.md](../OBSIDIAN.md)).

`MEMORY.md` tiene zonas: **General** (vale para todo), **Metodologías** (una `###` por
método, se añaden las que hagan falta) y **Proyectos** (qué método sigue cada uno). Los
métodos no se mezclan salvo que se pida: ver "Metodologías por proyecto" en
[EMPRESAS.md](../EMPRESAS.md).

Estos son solo ejemplos de lo que se le puede dictar; ninguno viene activado. Cuando una
directiva nombre un libro o una guía, indéxalo antes como documentación general con su
metodología (`jarvis_upload(..., methodology="PMI")`): el repo no trae ninguno. Si no
lo tienes, Jarvis te propondrá fuentes de internet y solo usará las que apruebes.

## Asignar métodos a proyectos

> App de reservas de Estudio Delta va con Scrum; la Migración ERP de Acme, con PMI.

Jarvis lo escribe en la zona **Proyectos**:

```markdown
## Proyectos

- Estudio Delta › App de reservas: Scrum
- Acme › Migración ERP: PMI
```

## Predictivo con PMBOK y un libro de formularios

> A partir de ahora trabaja en dos fases. Primero define (qué y cómo): lo que hay que
> hacer y por qué sale del PMBOK; la estructura de cada documento (acta de constitución,
> registro de riesgos, de interesados, acta de reunión…) sale del libro de formularios
> que tengo indexado; monta la plantilla antes de meter datos reales y no inventes
> métodos. Después ejecuta: lo planificado va a OpenProject como tareas, hitos, riesgos
> y reuniones; decisiones y planes por correo en borrador con mi visto bueno; avisos
> cortos por Telegram; y lo aprendido, a la memoria del proyecto.

## Scrum

> A partir de ahora trabajamos con Scrum. En OpenProject, el trabajo son historias de
> usuario con criterios de aceptación y estimación en puntos; cada sprint dura dos
> semanas y es una versión. Las reuniones son planning, daily de 15 minutos, review y
> retrospectiva; de la retro guarda las acciones de mejora en la memoria del proyecto.
> No me propongas diagramas de Gantt ni actas de constitución.

## Kanban

> Trabajamos con Kanban: sin sprints ni estimaciones. Límite de 3 tareas "En curso" por
> persona; si alguien lo supera, avísame. Cada viernes, resúmeme el tiempo de ciclo y lo
> bloqueado.
