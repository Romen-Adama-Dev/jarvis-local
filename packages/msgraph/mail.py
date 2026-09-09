"""Funciones de correo sobre Microsoft Graph (`/me/mailFolders/inbox`, `/me/messages`,
`/me/sendMail`).

Funciones planas, no una clase: reciben un `MsGraphClient` ya autenticado como primer
argumento. Ninguna de ellas sabe nada de confirmación ni de MCP — eso vive en
`apps/api/jarvis_api/routers/email.py` y en el servidor MCP `jarvis-email`.
"""

from typing import Any

from packages.msgraph.client import MsGraphClient

_LIST_SELECT = "id,subject,from,receivedDateTime,bodyPreview"
_MESSAGE_SELECT = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body"


async def list_inbox(client: MsGraphClient, top: int = 10) -> list[dict[str, Any]]:
    """Lista los mensajes más recientes de la bandeja de entrada."""
    response = await client.get(
        "/me/mailFolders/inbox/messages",
        params={"$top": top, "$select": _LIST_SELECT, "$orderby": "receivedDateTime desc"},
    )
    return response["value"]


async def get_message(client: MsGraphClient, message_id: str) -> dict[str, Any]:
    """Obtiene un mensaje completo (incluido el cuerpo) por su identificador."""
    return await client.get(f"/me/messages/{message_id}", params={"$select": _MESSAGE_SELECT})


async def send_mail(
    client: MsGraphClient,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
) -> None:
    """Envía un correo (`POST /me/sendMail`). No hay confirmación aquí: quien llama
    ya debe haberla obtenido (ver `ConfirmationService`)."""
    message: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
    }
    if cc:
        message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
    await client.post("/me/sendMail", json={"message": message})
