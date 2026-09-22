# Skills de terceros para OpenClaw

Skills de ClawHub revisadas a mano y copiadas en el repo, para que `docker compose up`
las cargue sin descargar nada en el arranque. OpenClaw las lee desde aquí con
`skills.load.extraDirs` (`integrations/openclaw/config/openclaw.template.json`), con la
precedencia más baja: no pueden sustituir a las skills propias ni a las incluidas.

Toda skill de terceros es código no auditado por su autor para este proyecto (riesgo de
inyección de instrucciones o de exfiltración). Antes de añadir una:

1. Descargar el paquete sin instalarlo (`https://clawhub.ai/api/v1/download?slug=<slug>`)
   y leer todos sus ficheros: nada de scripts, URLs, comandos ni instrucciones ocultas
   (comentarios HTML, caracteres Unicode invisibles).
2. Descartarla si pide `exec`, red o credenciales, o si duplica algo que Jarvis ya hace.
3. Copiar el `SKILL.md` sin cambios salvo el frontmatter (`name`, `description`) y una nota
   de uso; apuntar aquí versión, licencia y SHA-256 del paquete.

| Skill | Versión | Licencia | SHA-256 del paquete | Por qué |
|---|---|---|---|---|
| `agile-toolkit` (olivermonneke) | 1.0.0 | MIT-0 | `064f0c6668cedd47944fde72dea60da5ec219b2bd27c0cc0d3eb3ce012900d90` | Retros, planificación de sprint, historias de usuario, dailies, métricas y salud del equipo; solo conocimiento, sin scripts ni red |

Evaluadas y descartadas (22-09-2026):

| Skill | Motivo |
|---|---|
| `audio-transcribe`, `auto-whisper-safe` | Jarvis ya transcribe en local: notas de voz con whisper en OpenClaw y reuniones con faster-whisper en GPU (`docs/ACTAS.md`) |
| `obsidian-cli-plugins`, `obsidian-official-cli` | Necesitan la app o el CLI de Obsidian en el servidor; la memoria ya la escriben `knowledge` y `jarvis_remember` (`docs/OBSIDIAN.md`) |
| `braindb`, `agent-memory` | Otra memoria paralela a la del vault: rompería la memoria única |
| `csv-pipeline`, `data-analyst` | Hacen que el agente ejecute Python y shell con `exec`; los Excel ya los genera `jarvis-office` (`docs/DOCGEN.md`) |
