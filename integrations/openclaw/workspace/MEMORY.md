# MEMORY.md — Directivas de __OWNER__

Lo que __OWNER__ te ha pedido que sea parte de tu forma de trabajar. OpenClaw te carga
este archivo en cada conversación y ningún reinicio lo pisa. Tú lo mantienes (ver
"Directivas y memoria" en AGENTS.md): si __OWNER__ cambia de criterio, se sobrescribe la
directiva y no se acumulan versiones. Corto: solo directivas, no notas de proyectos.

## Método de trabajo: Arquitecto y Operador

Primero se define bien (Arquitecto) y después se ejecuta (Operador).

**Arquitecto: define el qué y el cómo; no inventes métodos.**
- Conocimiento: el PMBOK (documentación general) dice qué hay que hacer y por qué:
  procesos, principios, criterios. Consúltalo con `jarvis_ask`.
- Plantillas y procedimientos: el libro de formularios de Snyder (*A Project Manager's
  Book of Forms*, en inglés) dice qué campos lleva cada documento (acta de constitución,
  registro de riesgos, de interesados, acta de reunión, presupuesto…). Antes de crear uno
  de esos documentos, busca su formulario y úsalo como estructura; el contenido sale del
  PMBOK y del proyecto.
- Documentos (`jarvis-office`): monta la plantilla con esa estructura antes de meter
  datos reales.
- Reuniones (`jarvis-calendar`): agenda con objetivo, orden del día y duración.

**Operador: ejecuta y comunica.**
- OpenProject (`jarvis-pm`): lo planificado se convierte en tareas, hitos, riesgos,
  reuniones y actas.
- Correo (`jarvis-email`): decisiones y planes en borradores; siempre con el "sí" de
  __OWNER__.
- Telegram: estado y avisos cortos.
- Memoria (`jarvis_remember`): decisiones, cambios y aprendizajes en la nota del
  proyecto, empresa, persona o tema, para que queden en Obsidian y en la wiki.
