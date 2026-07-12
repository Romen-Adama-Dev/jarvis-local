import uuid

from fastapi import APIRouter
from sqlalchemy import select

from apps.api.jarvis_api.deps import DbSession
from apps.api.jarvis_api.schemas import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
)
from packages.core.db.models import Conversation
from packages.core.errors import NotFoundError

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    session: DbSession, telegram_user_id: int | None = None
) -> ConversationListResponse:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())
    if telegram_user_id is not None:
        stmt = stmt.where(Conversation.telegram_user_id == telegram_user_id)
    rows = (await session.execute(stmt)).scalars().all()
    conversations = [ConversationResponse.model_validate(r) for r in rows]
    return ConversationListResponse(conversations=conversations)


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    payload: ConversationCreateRequest, session: DbSession
) -> ConversationResponse:
    conversation = Conversation(telegram_user_id=payload.telegram_user_id, title=payload.title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, session: DbSession) -> None:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversación no encontrada")
    await session.delete(conversation)
    await session.commit()
