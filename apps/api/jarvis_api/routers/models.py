from fastapi import APIRouter

from apps.api.jarvis_api.deps import InferenceRouterDep
from apps.api.jarvis_api.schemas import ModelInfoResponse, ModelsResponse

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models", response_model=ModelsResponse)
async def list_models(inference_router: InferenceRouterDep) -> ModelsResponse:
    models: list[ModelInfoResponse] = []
    for provider in inference_router._providers.values():
        for model in await provider.list_models():
            models.append(
                ModelInfoResponse(
                    name=model.name,
                    provider=model.provider,
                    size_bytes=model.size_bytes,
                    supports_tools=model.supports_tools,
                )
            )
    return ModelsResponse(models=models)
