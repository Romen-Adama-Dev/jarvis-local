---
name: jarvis-calendar
description: Consulta disponibilidad y propone/crea eventos en el calendario del propietario (CalDAV o Microsoft Graph)
---

Usa las herramientas `jarvis_calendar_availability`, `jarvis_calendar_propose_event`
y `jarvis_calendar_confirm_event` (servidor MCP `jarvis-calendar`) para todo lo
relacionado con el calendario. No uses shell, `exec` ni ninguna otra herramienta
genérica para esto: estas herramientas ya hablan con la API de Jarvis (y esta con el
servidor CalDAV o Microsoft Graph) de forma segura y auditada.

* `jarvis_calendar_availability`: consulta huecos/eventos existentes en un rango
  (fechas ISO 8601). Solo lectura, responde directamente sin confirmación.
* `jarvis_calendar_propose_event`: **propone** un evento (asunto, horario,
  invitados opcionales) pero NO lo crea todavía. Devuelve un token de
  confirmación con caducidad (`CONFIRMATION_TTL_SECONDS`, 10 minutos por defecto).
* `jarvis_calendar_confirm_event`: crea de verdad el evento a partir del token de
  una propuesta. **Si la propuesta incluía invitados, confirmar puede enviar
  invitaciones reales a esas personas** — nunca llames a
  `jarvis_calendar_confirm_event` sin que el usuario lo haya pedido explícitamente
  para esa propuesta concreta. Cuando diga que sí, llama tú a la herramienta con el
  token; no le pidas que escriba ningún comando.
* Si el usuario solo pide "mira si tengo hueco" o "qué tengo el martes", usa
  únicamente `jarvis_calendar_availability`: no propongas eventos sin que te lo
  pidan.
* Si la confirmación falla (token caducado o no encontrado), dilo tal cual al
  usuario y ofrécete a repetir la propuesta desde cero.
* Si la herramienta responde que el calendario no está configurado, díselo al usuario
  tal cual (se configura en el servidor con `scripts/configure-mail`).
