"""Aprobación de acciones con botones de Telegram, fuera del modelo.

La API manda al propietario el borrador con los botones Enviar/Descartar; el callback
(`correo:enviar:<token>`) lo atiende el plugin de OpenClaw `jarvis-aprobaciones`, que
confirma contra la API con el ID de quien pulsa. El token no llega nunca al agente, así
que un texto malicioso (un correo recibido, una página) no puede hacer que envíe nada.
"""

import httpx

from packages.core.errors import ValidationFailedError

NAMESPACE = "correo"
# Telegram corta los mensajes en 4096 caracteres; se deja sitio para el resultado.
_MAX_TEXT = 3800


def approval_keyboard(token: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Enviar", "callback_data": f"{NAMESPACE}:enviar:{token}"},
                {"text": "🗑️ Descartar", "callback_data": f"{NAMESPACE}:descartar:{token}"},
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


async def send_approval(bot_token: str, chat_id: int, text: str, token: str) -> None:
    if not bot_token or bot_token == "change-me":
        raise ValidationFailedError(
            "Sin Telegram no se puede aprobar el correo: los envíos se aprueban con un botón "
            "en Telegram (TELEGRAM_BOT_TOKEN)."
        )
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "reply_markup": approval_keyboard(token)},
        )
    if response.status_code != 200:
        # Sin la URL: lleva el token del bot.
        raise ValidationFailedError(
            f"Telegram no aceptó el aviso de aprobación (HTTP {response.status_code})"
        )
