"""Altas de personas en OpenProject con aprobación del propietario (botón de Telegram).

Mismo esquema que los correos (routers/email.py): el agente pide el alta, la API manda al
propietario quién y en qué proyectos con los botones «Dar de alta» y «Descartar», y solo
el botón (plugin jarvis-aprobaciones) puede confirmarla. El token no pasa por el modelo.
"""

import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from apps.api.jarvis_api.deps import ConfirmationServiceDep, SettingsDep
from apps.api.jarvis_api.schemas import (
    PeopleConfirmRequest,
    PeopleDraftRequest,
    PeopleDraftResponse,
)
from packages.core.errors import ValidationFailedError
from packages.openproject.client import OpenProjectClient
from packages.openproject.config import config_from_env
from packages.openproject.people import Person, onboard, parse_people
from packages.security.telegram_approval import (
    PEOPLE_NAMESPACE,
    people_approval_text,
    send_approval,
)

router = APIRouter(prefix="/v1/pm", tags=["pm"])
ACTION = "pm_people"


def _op() -> OpenProjectClient:
    config = config_from_env()
    if config is None:
        raise ValidationFailedError("OpenProject no está configurado (perfil pm).")
    return OpenProjectClient(config)


@router.post("/people/draft", response_model=PeopleDraftResponse, status_code=202)
async def people_draft(
    payload: PeopleDraftRequest,
    confirmation_service: ConfirmationServiceDep,
    settings: SettingsDep,
) -> PeopleDraftResponse:
    """Guarda las altas y manda a Telegram los botones para aprobarlas."""
    # Valida los correos y que los proyectos existen antes de molestar al propietario.
    people = parse_people("\n".join(f"{p.name} <{p.email}>" for p in payload.people))
    projects = [p.strip() for p in payload.projects if p.strip()]
    if not projects:
        raise ValidationFailedError("Indica al menos un proyecto («Empresa › Proyecto»).")
    op = _op()
    await asyncio.gather(*(asyncio.to_thread(op.find_project, p) for p in projects))
    names = ", ".join(p.name for p in people)
    pending = await confirmation_service.request(
        payload.telegram_user_id,
        action=ACTION,
        summary=f"Alta de {names} en {', '.join(projects)}",
        payload={"people": [asdict(p) for p in people], "projects": projects},
    )
    minutes = max(1, settings.confirmation_ttl_seconds // 60)
    try:
        await send_approval(
            settings.telegram_bot_token,
            payload.telegram_user_id,
            people_approval_text(pending.payload["people"], projects, minutes),
            pending.token,
            PEOPLE_NAMESPACE,
        )
    except Exception:
        await confirmation_service.cancel(pending.token)
        raise
    return PeopleDraftResponse(summary=pending.summary, expires_at=pending.expires_at)


@router.post("/people/{token}/cancel")
async def people_cancel(
    token: str, payload: PeopleConfirmRequest, confirmation_service: ConfirmationServiceDep
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    return {"cancelled": True, "people": [p["name"] for p in pending.payload.get("people", [])]}


@router.post("/people/{token}/confirm")
async def people_confirm(
    token: str, payload: PeopleConfirmRequest, confirmation_service: ConfirmationServiceDep
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    if pending.action != ACTION:
        raise ValidationFailedError("Esta confirmación no es de altas de personas.")
    people = [Person(**p) for p in pending.payload["people"]]
    lines = await asyncio.to_thread(onboard, _op(), people, pending.payload["projects"])
    return {"done": True, "lines": lines}
