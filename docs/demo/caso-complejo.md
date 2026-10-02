# Caso de referencia: un equipo para varios clientes

Cómo debe quedar OpenProject (y, a partir de él, la memoria de Jarvis en Obsidian) en el
caso "extremo" de la demo: **el mismo equipo trabaja para dos clientes, con tres
proyectos y una metodología distinta en cada uno**. Sirve de patrón para una demo en vivo
y para comprobar lo que Jarvis construye solo. El detalle completo de cada paquete de
trabajo (fechas, horas, padres, sprints, categorías…) está en
[caso-complejo.json](caso-complejo.json), exportado de OpenProject el 2 de octubre de 2026.

## Quién es quién

| Persona | Papel | Dónde trabaja |
|---|---|---|
| Romen | Director de proyectos (propietario; en OpenProject, *Administrador Admin*) | Todo; es el **responsable** de cada paquete |
| Diego Sanz | Desarrollador · equipo de Romen · 45 €/h | App de citas, Gijón (alta en la app), Soporte de la web |
| Marta Ruiz | Consultora de calidad · equipo de Romen · 40 €/h | App de citas, Gijón (plan de calidad), Soporte de la web |
| Lucía Martín | Diseñadora UX · equipo de Romen · 42 €/h | App de citas, Gijón (señalética) |
| Pablo Vidal | Gerente de Talleres Norte (cliente, patrocinador) | Proyectos de Talleres Norte |
| Elena Castro | Gerente de Clínica Dental Sonrisas (cliente) | Soporte de la web |

En OpenProject: grupos **Equipo de Romen** (miembro de todos los proyectos, rol Miembro) y
**Clientes** (cada contacto, solo en los proyectos de su empresa). Diego y Marta trabajan
con las dos empresas: en Obsidian son **nexos** (`🕸 Nexos`).

## Los tres proyectos

### Talleres Norte › App de citas — Scrum

* Reserva de citas desde el móvil para los tres talleres; 18.000 €; producción antes del
  15-dic-2026.
* **Sprints nativos** de tres semanas (la regla de la zona Scrum de `MEMORY.md`):
  Sprint 1 (28-sep → 16-oct, **en curso**, con su tablero de tareas), 2, 3 y 4 (hasta el
  18-dic).
* **Épico** «Reserva online de citas para los tres talleres» → 7 **historias de usuario**
  con **puntos** (8, 5, 3, 5, 2, 3 y una de 5 en la pila sin sprint: el registro de
  usuario, fuera de la primera versión) → **tareas hijas** con horas estimadas, cada una
  en su sprint.
* Hito «Salida a producción de App de citas» (15-dic). *Definition of Done* en la wiki.
* Riesgos del kick-off: acceso a la base de datos del taller (bloquea la integración del
  calendario) y huecos de los sábados.

### Talleres Norte › Apertura del taller de Gijón — PMI (predictivo)

* Tercer taller en una nave de Roces; 240.000 € (mano de obra 13.600 € + compras 226.400 €,
  con reserva del 10 %); apertura el 15-ene-2027. Estado **en riesgo**.
* **EDT** en cuatro tareas de resumen (1. Inicio, 2. Planificación, 3. Ejecución,
  4. Cierre) y **fases del ciclo de vida** con las mismas fechas (Iniciando,
  Planificación, Ejecutando, Cerrando).
* **Hitos con fecha fija** (planificación manual): acta de constitución aprobada (9-oct),
  licencia de actividad (27-nov), fin de obra (18-dic), inauguración (15-ene).
* **Dependencias** (14, tipo *precede*): acta → licencia y obra; obra → elevadores → fin de
  obra; licencia, fin de obra, personal y alta en la app → inauguración → cierre.
* Categorías (Obra, Licencias, Personal, Imagen, Calidad, Sistemas), prioridades, acta de
  constitución en la wiki (formato Snyder) y reunión de arranque del 8-oct con objetivo,
  orden del día y duración.

### Clínica Dental Sonrisas › Soporte de la web — Kanban

* Mantenimiento continuo; bolsa de 90 horas (3.900 €). Sin sprints ni hitos.
* **Tablero Kanban** por estado: Nuevo → En curso → En espera (bloqueada) → Cerrado. Límite
  WIP de 2 en curso por persona (zona Kanban de `MEMORY.md`).
* **Clases de servicio** como categorías (Urgente, Con fecha, Estándar) y prioridades: el
  fallo de Safari es urgente (prioridad Inmediata). Política del tablero en la wiki.
* Revisión semanal del tablero (7-oct, 30 minutos).

## Lo que une los proyectos (lo que Jarvis tiene que ver)

* **Dependencia entre proyectos**: «Salida a producción de App de citas» (15-dic)
  *precede a* «Dar de alta el taller de Gijón en la App de citas» (empieza el 21-dic):
  **solo 6 días de margen**.
* **Diego Sanz**, semana del 19-oct: «Conectar el calendario de huecos…» (App de citas,
  20-oct) y «Añadir el horario de verano…» (Soporte de la web, 20-oct): **dos clientes la
  misma semana**. Hay un riesgo en la clínica que lo dice y está relacionado con la tarea
  de la app.
* **Lucía Martín**, semana del 9-nov: señalética (Gijón) y panel del personal (App de
  citas) el mismo día.
* Horas imputadas la semana del 28-sep (11 apuntes, 30 h) para que haya carga real.

Con todo eso, la red escribe (docs/OBSIDIAN.md, «El plan y la carga»): en cada proyecto su
*Estado*, *Sprints*, *Fases (EDT)* o *Tablero*, *Dependencias con otros proyectos* y
*Alertas*; en cada persona su *Carga*; y en `🕸 Nexos` los *Conflictos entre empresas*.

## Qué puede construir Jarvis solo y qué no

Con sus herramientas (`jarvis-pm`, `jarvis-rag`, calendario) Jarvis **puede**: dar de alta
empresas y proyectos, crear paquetes de cualquier tipo (tarea, hito, riesgo, historia,
épico) con fechas, responsable y prioridad, cambiar su estado, fijar la metodología de
cada proyecto y sus reglas en `MEMORY.md` y convocar reuniones.

**No puede** (hoy se hace a mano o con `rails runner`): crear usuarios, grupos y
membresías; sprints; jerarquía (padre/hijo); dependencias; puntos; horas estimadas e
imputadas; categorías; presupuestos; páginas de wiki y noticias; estado del proyecto;
tableros; fases del ciclo de vida.

## Prueba: Jarvis construyendo el caso con un solo mensaje

Ver [caso-complejo-prueba.md](caso-complejo-prueba.md).
