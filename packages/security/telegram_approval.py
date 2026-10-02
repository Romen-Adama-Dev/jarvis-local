"""Aprobación de acciones con botones de Telegram, fuera del modelo.

La API manda al propietario lo que se va a hacer con dos botones; el callback
(`correo:enviar:<token>`, `personas:alta:<token>`) lo atiende el plugin de OpenClaw
`jarvis-aprobaciones`, que confirma contra la API con el ID de quien pulsa. El token no
llega nunca al agente, así que un texto malicioso (un correo recibido, una página) no
puede hacer que envíe nada.
"""

import httpx

from packages.core.errors import ValidationFailedError

NAMESPACE = "correo"
PEOPLE_NAMESPACE = "personas"
# Espacio del callback → botón de aceptar (texto, acción). El de descartar es común.
_ACCEPT = {NAMESPACE: ("✅ Enviar", "enviar"), PEOPLE_NAMESPACE: ("✅ Dar de alta", "alta")}
# Telegram corta los mensajes en 4096 caracteres; se deja sitio para el resultado.
_MAX_TEXT = 3800


def approval_keyboard(token: str, namespace: str = NAMESPACE) -> dict:
    label, action = _ACCEPT[namespace]
    return {
        "inline_keyboard": [
            [
                {"text": label, "callback_data": f"{namespace}:{action}:{token}"},
                {"text": "🗑️ Descartar", "callback_data": f"{namespace}:descartar:{token}"},
            ]
        ]
    }


def email_approval_text(draft: dict, attachment: str | None, minutes: int) -> str:
    """Todo lo que se va a enviar, tal cual, para aprobarlo sin fiarse del resumen del
    agente. Texto plano: nada del cuerpo se interpreta como formato."""
    lines = [
        "✉️ Correo pendiente de tu aprobación",
        f"Para: {', '.join(draft['to'])}",
    ]
    if draft.get("cc"):
        lines.append(f"CC: {', '.join(draft['cc'])}")
    lines.append(f"Asunto: {draft['subject']}")
    if attachment:
        lines.append(f"Adjunto: {attachment}")
    footer = f"\n\nCaduca en {minutes} min."
    head = "\n".join(lines) + "\n\n"
    body = draft["body"]
    room = _MAX_TEXT - len(head) - len(footer)
    if len(body) > room:
        body = body[: max(0, room - 40)] + "\n[…cuerpo recortado en este aviso…]"
    return head + body + footer


def people_approval_text(people: list[dict], projects: list[str], minutes: int) -> str:
    """Quién se da de alta en OpenProject y en qué proyectos, tal cual, para aprobarlo."""
    lines = ["👥 Altas en OpenProject pendientes de tu aprobación", ""]
    lines += [f"• {p['name']} <{p['email']}>" for p in people]
    lines += ["", "En los proyectos:"]
    lines += [f"• {project}" for project in projects]
    lines += ["", "Se les asignarán las tareas en las que ya figuran como responsables."]
    return ("\n".join(lines))[: _MAX_TEXT - 40] + f"\n\nCaduca en {minutes} min."


async def send_approval(
    bot_token: str, chat_id: int, text: str, token: str, namespace: str = NAMESPACE
) -> None:
    if not bot_token or bot_token == "change-me":
        raise ValidationFailedError(
            "Sin Telegram no se puede aprobar: estas acciones se aprueban con un botón "
            "en Telegram (TELEGRAM_BOT_TOKEN)."
        )
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": approval_keyboard(token, namespace),
            },
        )
    if response.status_code != 200:
        # Sin la URL: lleva el token del bot.
        raise ValidationFailedError(
            f"Telegram no aceptó el aviso de aprobación (HTTP {response.status_code})"
        )
