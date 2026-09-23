# MEMORY.md — Directivas de __OWNER__

Lo que __OWNER__ te ha pedido que sea parte de tu forma de trabajar. OpenClaw te carga
este archivo en cada conversación y ningún reinicio lo pisa. Tú lo mantienes (ver
"Directivas y memoria" en AGENTS.md) con `jarvis_set_*`: si __OWNER__ cambia de
criterio, se sobrescribe esa sección y no se acumulan versiones. Corto: solo directivas,
no notas de proyectos. `jarvis-rag` lee "Metodologías" y "Proyectos" para no mezclar la
documentación de un método con la de otro.

## General

Directivas que valen para todo, sea cual sea el proyecto, con un `### <Tema>` por tema.

## Metodologías

Un `### <Nombre>` por metodología (Scrum, PMI, Cascada…) con sus reglas: artefactos,
reuniones, plantillas y documentación de referencia. Se añaden las que __OWNER__ vaya
definiendo. Sin ninguna aquí, no supongas ningún método.

## Proyectos

Una línea por proyecto con su metodología, con el nombre de su zona:
`- Empresa › Proyecto: Scrum`. Varias (`PMI + Scrum`) solo si __OWNER__ pide mezclarlas.
Un proyecto que no está aquí no tiene metodología: pregúntala antes de planificarlo.
