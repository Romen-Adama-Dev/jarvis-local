import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from airllm_service.engine import AirLLMEngine, EngineStatus, disk_report
from airllm_service.settings import get_service_settings

logger = structlog.get_logger(__name__)

settings = get_service_settings()
os.environ.setdefault("HF_HOME", str(settings.models_dir / "hf"))

engine = AirLLMEngine(settings)


class ChatMessagePayload(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessagePayload] = Field(min_length=1)
    max_tokens: int | None = None
    temperature: float | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessagePayload
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.start_loading()
    yield


app = FastAPI(title="Jarvis AirLLM Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    state = engine.state
    last = state.last_generation
    return {
        "status": state.status.value,
        "detail": state.detail,
        "model": state.model,
        "device": state.device,
        "busy": state.busy,
        "pending": state.pending,
        "load_seconds": state.load_seconds,
        "uptime_seconds": round(time.time() - state.started_at, 0),
        "disk": disk_report(settings.models_dir),
        "last_generation": {
            "duration_seconds": last.duration_seconds,
            "prompt_tokens": last.prompt_tokens,
            "completion_tokens": last.completion_tokens,
            "tokens_per_second": last.tokens_per_second,
            "rss_gb": last.rss_gb,
        }
        if last
        else None,
    }


@app.get("/v1/models")
async def list_models() -> dict:
    data = []
    if settings.model:
        data.append({"id": settings.model, "object": "model", "owned_by": "airllm"})
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(payload: ChatCompletionRequest) -> ChatCompletionResponse:
    state = engine.state
    if state.status in {EngineStatus.NO_MODEL, EngineStatus.ERROR}:
        raise HTTPException(status_code=503, detail=f"{state.status}: {state.detail}")
    if state.status in {EngineStatus.CHECKING, EngineStatus.LOADING}:
        raise HTTPException(
            status_code=503,
            detail=f"El modelo todavía se está cargando: {state.detail}",
            headers={"Retry-After": "60"},
        )
    if payload.model and payload.model != settings.model:
        raise HTTPException(
            status_code=400,
            detail=f"Este servicio solo sirve el modelo configurado: {settings.model}",
        )
    if state.pending >= settings.queue_max_pending:
        raise HTTPException(
            status_code=503,
            detail="Cola de AirLLM llena; reintenta más tarde",
            headers={"Retry-After": "120"},
        )

    max_new_tokens = min(
        payload.max_tokens or settings.max_new_tokens_default,
        settings.max_new_tokens_limit,
    )
    messages = [{"role": m.role, "content": m.content} for m in payload.messages]

    engine.state.pending += 1
    try:
        text, metrics = await asyncio.wait_for(
            asyncio.to_thread(
                engine.generate,
                messages,
                max_new_tokens=max_new_tokens,
                temperature=payload.temperature,
            ),
            timeout=settings.generation_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Generación cancelada por timeout ({settings.generation_timeout_seconds}s)",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        engine.state.pending -= 1

    finish_reason = "length" if metrics.completion_tokens >= max_new_tokens else "stop"
    return ChatCompletionResponse(
        id=f"airllm-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=settings.model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessagePayload(role="assistant", content=text),
                finish_reason=finish_reason,
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            total_tokens=metrics.prompt_tokens + metrics.completion_tokens,
        ),
    )
