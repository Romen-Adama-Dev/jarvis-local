# Integraciones — investigación y hoja de ruta

Investigación (2026-07-13) de proyectos autohosteados con licencia libre que OpenClaw puede aprovechar para acercarse a un asistente personal completo, respetando local-first y el hardware disponible (i7-6700K, 32 GB RAM, GTX 1070 8 GB ya ocupada por el LLM).

## Ya desplegado

| Proyecto | Licencia | Para qué | Estado |
|---|---|---|---|
| SearXNG | AGPL-3.0 | Búsqueda web sin API keys: da `web_search` a OpenClaw manteniendo las consultas en servidor propio | ✅ Perfil `assistant` de compose, plugin oficial configurado |
| whisper.cpp | MIT | Transcripción local de notas de voz de Telegram (modelo small q5, español, ~5 s por nota en CPU) | ✅ Paquete de Ubuntu + modelo en `/srv/jarvis/models/whisper`, cableado en `tools.media.audio` |
| Piper TTS | MIT | Respuestas con voz en español (es_ES-davefx-medium); modo `inbound`: responde con audio solo si le hablas | ✅ `uv tool install piper-tts` + wrapper `jarvis-tts`, cableado en `messages.tts` |
| changedetection.io | Apache-2.0 | Vigilar páginas web (precios, convocatorias…) | ✅ Perfil `assistant`, `127.0.0.1:5000` |
| Watchdog propio | (parte del repo) | Avisos proactivos a Telegram si cae un servicio, el disco pasa del 90% o la GPU no responde; sin coste de LLM | ✅ `scripts/jarvis-watchdog` + timer systemd cada 5 min |
| n8n | Fair-code (Sustainable Use) | Automatizaciones y webhooks | Perfil `automation` (opcional, ya previsto) |
| Open WebUI | BSD-3 | Interfaz web para Ollama (uso interno) | Perfil `webui` (opcional, ya previsto) |

## Alta prioridad (mucho valor, poco coste)

| Proyecto | Licencia | Para qué | Notas de encaje |
|---|---|---|---|
| ClawHub (registro de skills de OpenClaw) | — (skills individuales, revisar cada una) | +5.400 skills comunitarias instalables | Instalar solo skills auditadas; cada skill añade tokens al prompt del sistema (ver incidente en OPENCLAW.md) |

## Valorar más adelante

| Proyecto | Licencia | Para qué | Notas |
|---|---|---|---|
| Home Assistant | Apache-2.0 | Domótica: OpenClaw como voz/chat de la casa (existe el patrón "Kiwi Voice") | Solo si hay dispositivos que controlar |
| Paperless-ngx | GPL-3.0 | Archivo documental OCR (facturas, recibos) | Complementa al RAG: Paperless organiza, Jarvis indexa y responde |
| Gitea / Forgejo | MIT | Git self-hosted; OpenClaw tiene skills de issues/PRs | Útil si el repo del TFM se quiere fuera de GitHub |
| Nextcloud | AGPL-3.0 | Archivos, calendario, contactos self-hosted | Pesado; solo si se quiere ecosistema completo |
| Memos | MIT | Notas rápidas con API sencilla | Candidato a "libreta" de Jarvis vía skill |
| Firecrawl / Crawl4AI | AGPL-3.0 / Apache-2.0 | Scraping estructurado para alimentar el RAG | Cuando haga falta ingestar webs enteras |

## Criterios aplicados

1. Licencia libre (MIT/Apache/BSD preferidas; AGPL aceptable si solo se usa como servicio interno).
2. Sin dependencia de APIs de pago ni claves comerciales.
3. Consumo compatible con 32 GB RAM y GPU ya ocupada (servicios en CPU salvo Whisper opcional).
4. Integrable con OpenClaw por vía soportada (plugin, skill, MCP o HTTP local), no por shell arbitrario.
5. Cada integración debe poder apagarse sin romper el núcleo (perfiles de compose separados).

Fuentes de la investigación: documentación local de OpenClaw (`tools/searxng-search.md`, `tools/exec-approvals.md`), [awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills), [awesome-openclaw](https://github.com/SamurAIGPT/awesome-openclaw), [discusión Kiwi Voice](https://github.com/openclaw/openclaw/discussions/26230), [issue STT/TTS de OpenClaw](https://github.com/openclaw/openclaw/issues/49246), [guía KV cache de Ollama](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/), [issue de arquitecturas con flash attention](https://github.com/ollama/ollama/issues/13337).
