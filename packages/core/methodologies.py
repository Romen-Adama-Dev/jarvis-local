"""Plantillas base de las metodologías habituales, para su zona de MEMORY.md.

Cuando el propietario dice que un proyecto «va con Kanban» y Kanban aún no tiene zona,
`jarvis-pm__pm_setup` guarda esta plantilla en vez de dejar el método sin reglas (con
ellas Jarvis sabe qué crear: historias y sprints, fases e hitos, o tarjetas y límite
WIP). Son un punto de partida estándar: el propietario las cambia cuando quiera con
`jarvis_set_methodology`, y lo que él defina nunca se pisa.
"""

from packages.core.directives import methodology_id

TEMPLATES = {
    "kanban": [
        "- **Trabajo:** Tarjetas de flujo continuo, sin sprints ni estimación en puntos.",
        "- **Tablero:** Nuevo → En curso → Cerrado; En espera = tarjeta bloqueada.",
        "- **Límite WIP:** Como máximo 2 tarjetas En curso por persona.",
        "- **Clases de servicio:** urgente (salta la cola), con fecha y estándar.",
        "- **Reuniones:** Revisión semanal del tablero de 30 minutos.",
    ],
    "scrum": [
        "- **Trabajo:** Historias de usuario con criterios de aceptación y puntos.",
        "- **Sprints:** De dos semanas.",
        "- **Ceremonias:** Sprint Planning, Daily (15 min), Sprint Review y Retrospectiva.",
        "- **Artefactos:** Product Backlog, Sprint Backlog e Incremento (Definition of Done).",
    ],
    "pmi": [
        "- **Ciclo de vida:** Predictivo, por fases: Inicio, Planificación, Ejecución, Cierre.",
        "- **Documentos:** Acta de constitución y registro de interesados antes de planificar.",
        "- **OpenProject:** Hitos con fecha fija, dependencias en el Gantt y registro de riesgos.",
        "- **Cambios:** Control de cambios sobre la línea base.",
    ],
    "cascada": [
        "- **Fases:** Requisitos, Diseño, Desarrollo, Pruebas y Entrega, una tras otra.",
        "- **Hitos:** Uno al cerrar cada fase; no se empieza una fase sin cerrar la anterior.",
        "- **Cambios:** Solo con control de cambios aprobado por el propietario.",
    ],
}


def template(method: str) -> str:
    """Reglas base de `method` ("" si no hay plantilla para él)."""
    return "\n".join(TEMPLATES.get(methodology_id(method), []))
