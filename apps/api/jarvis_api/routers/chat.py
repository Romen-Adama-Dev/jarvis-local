from fastapi import APIRouter

from apps.api.jarvis_api.deps import InferenceRouterDep
from apps.api.jarvis_api.schemas import ChatRequest, ChatResponse
from packages.core.errors import ValidationFailedError
from packages.inference.base import ChatMessage, Role
from packages.inference.router import InferenceMode

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, inference_router: InferenceRouterDep) -> ChatResponse:
    try:
        mode = InferenceMode(payload.mode)
    except ValueError as exc:
        raise ValidationFailedError(f"Modo de inferencia inválido: {payload.mode}") from exc

    messages = [ChatMessage(role=Role(m.role), content=m.content) for m in payload.messages]
    result = await inference_router.chat(mode, messages, model=payload.model)

    return ChatResponse(
        text=result.text,
        model=result.model,
        provider=result.provider,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
    )
