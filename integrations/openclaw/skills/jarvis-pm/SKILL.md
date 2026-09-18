---
name: jarvis-pm
description: Gestión de proyectos en OpenProject (empresas, proyectos, tareas, hitos, riesgos, seguimiento) desde el chat
---

Usa las herramientas del servidor MCP `jarvis-pm` para todo lo que sea seguimiento de
proyectos: tareas, hitos, riesgos, estados, fechas y responsables. Hablan con el
OpenProject del servidor (perfil `pm`, `docs/OPENPROJECT.md`). No uses `exec` ni la web
para esto.

Organización: cada **empresa** es un proyecto raíz de OpenProject y sus **proyectos**
cuelgan de ella. Los nombres se pueden dar tal cual los diga el usuario (sin tildes,
en minúsculas o con el identificador): la herramienta los resuelve.

* `pm_projects`: empresas y proyectos, con su enlace.
* `pm_create_project(name, company="")`: con `company` crea un proyecto dentro de esa
  empresa; sin ella, da de alta una empresa.
* `pm_list_tasks(project, kind="", include_closed=False, due_within_days=-1,
  overdue_only=False)`: trabajo del proyecto ordenado por vencimiento.
* `pm_create_task(project, subject, kind="Tarea", ...)`: tipos Tarea, Hito y Riesgo (y
  los que tenga activos el proyecto). Fechas `AAAA-MM-DD`. En un riesgo, la descripción
  lleva probabilidad, impacto, mitigación y responsable.
* `pm_update_task(task_id, status="", percent_done=-1, due_date="", assignee="",
  comment="")`: solo cambia lo indicado. Estados habituales: Nuevo, En curso, En espera,
  Cerrado, Rechazado.
* `pm_status_report(project)`: informe de seguimiento y control (abiertos, vencidos,
  próximos 7 días, hitos, riesgos) con enlaces al Gantt y a los tableros.

Crear o cambiar tareas no avisa a nadie por correo; no hay herramienta de borrado (se
borra desde la web). Si la herramienta responde que OpenProject no está configurado,
díselo tal cual al usuario.
