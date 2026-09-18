# Actas de reunión automáticas

Mandas la grabación de una reunión a Jarvis y te devuelve el acta: resumen, temas,
decisiones, acciones con responsable y fecha, y riesgos con probabilidad, impacto y
mitigación. Si le dices que sí, crea esas acciones y riesgos en OpenProject
(`docs/OPENPROJECT.md`). Todo se procesa en el servidor, sin servicios externos.

## Flujo

```
audio (Telegram, Obsidian o ~/jarvis-inbox)
  └─► jarvis_meeting_minutes (MCP) ─► POST /v1/meetings ─► worker
        1. faster-whisper large-v3-turbo en la GPU → transcripción con marcas de tiempo
        2. Gemma extrae el acta en JSON por bloques de ~5.000 palabras y los une
        3. acta en Markdown (con la transcripción como anexo) → PDF / Word con pandoc
  ◄── acta adjunta en el chat
      + nota en Obsidian: sources/proyectos/<proyecto>/actas/<fecha>-<título>.md
      + indexada en el RAG del proyecto ("¿qué se decidió sobre X en la reunión?")
  └─► "¿las creo en OpenProject?" → pm_import_minutes → Tareas y Riesgos
```

Medido en este servidor (NVIDIA L4, junto a `gemma4:26b`): 86 s de audio se transcriben en
3 s; una hora de reunión, unos 2 minutos. El acta de una reunión corta tarda unos
15 segundos; una larga, un bloque de unos 20 s por cada ~40 minutos de conversación. En
total, la reunión de prueba (1,5 min) tardó 51 segundos de punta a punta desde Telegram.

## Cómo usarlo

* **Por Telegram** (hasta 20 MB, el límite de descarga de los bots: unas 2 horas de nota de
  voz o 1 hora de m4a): adjunta el audio y di "hazme el acta, es del proyecto X". Las
  notas de voz de menos de 2 MB las transcribe OpenClaw al momento como un mensaje normal;
  si una nota corta es una reunión, pide el acta igualmente.
* **Grabaciones largas**: grábalas con la grabadora de Obsidian (plugin básico *Audio
  recorder*) o copia el archivo al vault; LiveSync lo lleva al servidor. También vale
  `~/jarvis-inbox` en el servidor. Luego: "haz el acta de `<nombre del archivo>`".
* Formatos de audio: ogg/opus, m4a, mp3, wav, webm, flac, aac. Acta en PDF (por
  defecto), Word o Markdown.
* Después: "créalas en OpenProject", "mándale el acta a Ana por correo" (adjunta el PDF
  con el flujo de confirmación del correo).

## Configuración

| Variable (`.env`) | Por defecto | Para qué |
|---|---|---|
| `MEETINGS_WHISPER_MODEL` | `large-v3-turbo` | Modelo de faster-whisper. En CPU usa `small` (lo fija `compose.cpu.yml`) o `medium` |
| `MEETINGS_WHISPER_DEVICE` | `auto` | `cuda`, `cpu` o `auto` (GPU si la hay) |
| `MEETINGS_LANGUAGE` | `es` | Idioma de la reunión; vacío = detectarlo |
| `MEETINGS_MAX_UPLOAD_MB` | `500` | Tamaño máximo de una grabación |

El modelo de transcripción (~1,6 GB) se descarga la primera vez en
`/srv/jarvis/models/whisper` (volumen `jarvis_srv`). El worker usa la GPU (`gpus: all`) y
libera la VRAM al terminar de transcribir, antes de que Gemma redacte el acta.

## Límites conocidos

* **Sin separación de hablantes**: la transcripción no dice quién habla. El modelo deduce
  asistentes y responsables por el contenido ("Luis comenta...", "Ana se encarga...").
  Diarización local (pyannote) queda como mejora.
* Los nombres propios pueden salir mal transcritos; el acta se marca como "revísala antes
  de distribuirla".
* Para asignar tareas en OpenProject, el responsable tiene que ser miembro del proyecto;
  si no, queda en la descripción.

## Dónde queda cada cosa

| Qué | Dónde |
|---|---|
| Audio, transcripción, acta (md y pdf/docx) | `/srv/jarvis/data/meetings/<trabajo>/` (volumen `jarvis_srv`) |
| Acta en la memoria | vault: `sources/proyectos/<proyecto>/actas/` |
| Acta en el RAG | documento `<fecha>-<título>.md` del proyecto |
| Tareas y riesgos | OpenProject, con "Origen: acta «título» (fecha)" en la descripción |
