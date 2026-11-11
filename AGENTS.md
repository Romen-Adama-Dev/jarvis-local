# Reglas para agentes de desarrollo

Valen para cualquier agente que trabaje en el código de este repositorio (Claude Code,
Codex u otros). El propietario define la arquitectura y los criterios de aceptación,
revisa cada PR y despliega; el agente ejecuta dentro de estas reglas.

No confundas este archivo con `integrations/openclaw/workspace/AGENTS.md`: ese es el prompt
de Jarvis en ejecución, tiene un límite de longitud que comprueba
`tests/unit/test_agents_md.py` y no recoge reglas de desarrollo.

## 1. ADN de gestión de proyectos

Esta regla va antes que las demás: cada cambio es un entregable de un proyecto gestionado.

* Trabaja sobre una tarea con ID y un criterio de aceptación que se pueda comprobar. Si la
  tarea no lo trae, escríbelo en la descripción de la PR antes de tocar código.
* Deja la gestión al día en el mismo commit, dentro de [docs/gestion/](docs/gestion/):
  * [wbs.md](docs/gestion/wbs.md) si un paquete de trabajo cambia de estado o aparece uno
    nuevo;
  * [raid.md](docs/gestion/raid.md) si el cambio abre, mitiga o cierra un riesgo, un
    supuesto, una incidencia o una dependencia;
  * [decisiones.md](docs/gestion/decisiones.md) si tomas una decisión duradera: nueva fila
    con fecha, alternativas descartadas y fuente.
* El plan vivo está en OpenProject. [plan.md](docs/gestion/plan.md) es una foto: separa lo
  real (historial de git) de lo estimado y no inventes fechas.
* Mide antes de decidir. Si cambias el modelo, el prompt del RAG, la recuperación o la
  traducción, lanza `scripts/benchmark-jarvis` y versiona el JSON en `docs/benchmarks/`.
* Nada se marca como hecho sin comprobarlo. En [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)
  cada criterio verificado dice cómo se verificó.

## 2. Producto

* **Local-first.** Ningún documento, embedding, prompt o respuesta sale del servidor hacia
  una API de modelos en la nube. Ollama es el único proveedor de inferencia y se usa a
  través de `packages/inference`.
* Toda acción con efecto fuera del servidor (enviar un correo, invitar a una reunión,
  crear tareas desde un acta, ejecutar un comando fuera de la lista blanca) pasa por
  confirmación explícita del propietario, con el patrón de `packages/security`.
* El RAG se abstiene cuando no hay evidencia. No relajes ese comportamiento para que pase
  un test.
* Internet solo con permiso: primero la documentación indexada y la memoria; después se
  propone al propietario que aporte la documentación; solo con su "sí" se buscan fuentes,
  y se responde únicamente con las que apruebe. No reintroduzcas una búsqueda web libre.
* Prompts y plantillas neutros: nada específico de un usuario concreto ni de una
  metodología (PMBOK, Scrum...) en lo que ve el modelo. Lo específico va en `.env` o en la
  memoria del despliegue.

## 3. Repositorio público

* Sin datos privados en código, documentación ni tests: ni correos reales, ni nombres de
  tailnet, ni IP de Tailscale, ni IDs de Telegram, ni contraseñas o tokens. Usa marcadores
  (`<tailnet>`, `tu-cuenta@example.com`) y datos ficticios.
* Los secretos viven en `.env` (usa `.env.example` como plantilla y documenta ahí cada
  variable nueva) y en `/run/jarvis`.
* Quien clone el repo debe poder arrancarlo con `docker compose up`. Todo cambio de
  despliegue se versiona y se documenta aquí, no solo en el servidor.
* Antes de probar con datos, haz copia (`scripts/backup`). Los datos de demo se vacían con
  `scripts/vaciar-demo`.

## 4. Flujo de trabajo

* Una tarea, una rama desde `main` (`tipo/descripcion-corta`), un commit y una PR que
  revisa el propietario. El agente no fusiona.
* Mensajes en español con Conventional Commits: `tipo(ámbito): resumen`
  (ver [CONTRIBUTING.md](CONTRIBUTING.md)) y el ID de la tarea como trailer
  (`Tarea: XXX-00`).
* Staging archivo a archivo, nunca `git add -A` ni `git add .`.
* Antes de abrir la PR: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .` y `uv run pyright`.

## English summary

Rules for coding agents working on this repo. The first rule is project management
discipline: every change starts from a task with a testable acceptance criterion and
updates the WBS, the RAID log and the decision index in `docs/gestion/` in the same
commit. Then come the product rules (local-only inference, human approval for external
actions, abstention without evidence, internet only with approval), public-repo hygiene
and the branch, commit and PR workflow.
