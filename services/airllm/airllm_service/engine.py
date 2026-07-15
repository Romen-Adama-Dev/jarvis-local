import os
import shutil
import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import psutil
import structlog

from airllm_service.settings import ServiceSettings

logger = structlog.get_logger(__name__)

LAYERED_OVERHEAD_FACTOR = 2.2
GIB = 1024**3


class EngineStatus(StrEnum):
    NO_MODEL = "no_model"
    CHECKING = "checking"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass(slots=True)
class GenerationMetrics:
    duration_seconds: float
    prompt_tokens: int
    completion_tokens: int
    tokens_per_second: float
    rss_gb: float
    finished_at: float


@dataclass(slots=True)
class EngineState:
    status: EngineStatus = EngineStatus.NO_MODEL
    detail: str = ""
    model: str = ""
    device: str = ""
    busy: bool = False
    pending: int = 0
    load_seconds: float | None = None
    last_generation: GenerationMetrics | None = None
    started_at: float = field(default_factory=time.time)


def disk_report(path: Path) -> dict[str, float]:
    usage = shutil.disk_usage(path)
    return {
        "total_gb": round(usage.total / GIB, 1),
        "used_gb": round(usage.used / GIB, 1),
        "free_gb": round(usage.free / GIB, 1),
    }


def estimate_remote_model_bytes(repo_id: str) -> int:
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo_id, files_metadata=True)
    totals = {".safetensors": 0, ".bin": 0, ".pth": 0, ".gguf": 0}
    for sibling in info.siblings or []:
        if not sibling.size:
            continue
        for suffix, _ in totals.items():
            if sibling.rfilename.endswith(suffix):
                totals[suffix] += sibling.size
    for suffix in (".safetensors", ".bin", ".pth", ".gguf"):
        if totals[suffix]:
            return totals[suffix]
    return 0


def build_prompt(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    parts = [f"{m['role']}: {m['content']}" for m in messages]
    parts.append("assistant:")
    return "\n\n".join(parts)


class AirLLMEngine:
    def __init__(self, settings: ServiceSettings) -> None:
        self._settings = settings
        self._state = EngineState(model=settings.model)
        self._model: Any = None
        self._generate_lock = threading.Lock()
        self._state_lock = threading.Lock()

    @property
    def state(self) -> EngineState:
        return self._state

    def _set_status(self, status: EngineStatus, detail: str = "") -> None:
        with self._state_lock:
            self._state.status = status
            self._state.detail = detail
        logger.info("engine_status", status=status.value, detail=detail)

    def _resolve_device(self) -> str:
        if self._settings.device != "auto":
            return self._settings.device
        import torch

        return "cuda:0" if torch.cuda.is_available() else "cpu"

    def _hf_cache_has_model(self) -> bool:
        cache_root = Path(os.environ.get("HF_HOME", str(self._settings.models_dir / "hf")))
        marker = cache_root / "hub" / f"models--{self._settings.model.replace('/', '--')}"
        return marker.is_dir()

    def _check_capacity(self) -> None:
        models_dir = self._settings.models_dir
        models_dir.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(models_dir).free / GIB
        if self._hf_cache_has_model():
            if free_gb < self._settings.min_free_gb:
                raise RuntimeError(
                    f"Espacio insuficiente: {free_gb:.1f} GiB libres, "
                    f"mínimo {self._settings.min_free_gb} GiB"
                )
            return
        size_bytes = estimate_remote_model_bytes(self._settings.model)
        size_gb = size_bytes / GIB
        if size_gb > self._settings.max_model_download_gb:
            raise RuntimeError(
                f"El modelo {self._settings.model} pesa {size_gb:.1f} GiB y supera el límite "
                f"de descarga configurado ({self._settings.max_model_download_gb} GiB). "
                "Ajusta AIRLLM_MAX_MODEL_DOWNLOAD_GB solo si hay disco suficiente."
            )
        required_gb = size_gb * LAYERED_OVERHEAD_FACTOR + self._settings.min_free_gb
        if free_gb < required_gb:
            raise RuntimeError(
                f"Espacio insuficiente para {self._settings.model}: se necesitan "
                f"~{required_gb:.1f} GiB (modelo + shards por capas + margen) "
                f"y hay {free_gb:.1f} GiB libres"
            )
        logger.info(
            "capacity_ok",
            model=self._settings.model,
            size_gb=round(size_gb, 1),
            required_gb=round(required_gb, 1),
            free_gb=round(free_gb, 1),
        )

    def start_loading(self) -> None:
        if not self._settings.model:
            self._set_status(
                EngineStatus.NO_MODEL,
                "AIRLLM_MODEL no configurado; el servicio responde pero no puede generar",
            )
            return
        thread = threading.Thread(target=self._load, name="airllm-load", daemon=True)
        thread.start()

    def _load(self) -> None:
        try:
            self._set_status(EngineStatus.CHECKING, "comprobando espacio en disco")
            self._check_capacity()
            self._set_status(
                EngineStatus.LOADING,
                f"descargando/cargando {self._settings.model} (puede tardar minutos)",
            )
            start = time.perf_counter()
            device = self._resolve_device()
            import torch
            from airllm import AutoModel

            dtype = torch.float16 if device.startswith("cuda") else torch.float32
            layered_dir = (
                self._settings.models_dir / "layered" / self._settings.model.replace("/", "--")
            )
            layered_dir.mkdir(parents=True, exist_ok=True)
            kwargs: dict[str, Any] = {
                "device": device,
                "dtype": dtype,
                "max_seq_len": self._settings.max_seq_len,
                "layer_shards_saving_path": str(layered_dir),
            }
            if self._settings.compression:
                kwargs["compression"] = self._settings.compression
            self._model = AutoModel.from_pretrained(self._settings.model, **kwargs)
            elapsed = time.perf_counter() - start
            with self._state_lock:
                self._state.device = device
                self._state.load_seconds = round(elapsed, 1)
            self._set_status(EngineStatus.READY, f"modelo cargado en {elapsed:.0f}s")
        except Exception as exc:
            logger.error("engine_load_failed", error=str(exc), traceback=traceback.format_exc())
            self._set_status(EngineStatus.ERROR, f"{type(exc).__name__}: {exc}")

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int,
        temperature: float | None,
    ) -> tuple[str, GenerationMetrics]:
        if self._state.status is not EngineStatus.READY or self._model is None:
            raise RuntimeError(f"Motor no listo: {self._state.status} {self._state.detail}")
        with self._generate_lock:
            with self._state_lock:
                self._state.busy = True
            try:
                return self._generate_locked(messages, max_new_tokens, temperature)
            finally:
                self._release_device_cache()
                with self._state_lock:
                    self._state.busy = False

    def _release_device_cache(self) -> None:
        if not self._state.device.startswith("cuda"):
            return
        import torch

        torch.cuda.empty_cache()

    def _generate_locked(
        self,
        messages: list[dict[str, str]],
        max_new_tokens: int,
        temperature: float | None,
    ) -> tuple[str, GenerationMetrics]:
        model = self._model
        tokenizer = model.tokenizer
        prompt = build_prompt(tokenizer, messages)
        max_prompt_tokens = max(self._settings.max_seq_len - max_new_tokens, 256)
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=max_prompt_tokens,
        )
        input_ids = inputs["input_ids"].to(self._state.device)
        prompt_tokens = int(input_ids.shape[1])

        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "use_cache": True,
            "return_dict_in_generate": True,
        }
        if temperature is not None and temperature > 0:
            generate_kwargs["do_sample"] = True
            generate_kwargs["temperature"] = temperature

        start = time.perf_counter()
        try:
            output = model.generate(input_ids, **generate_kwargs)
        except TypeError:
            generate_kwargs.pop("do_sample", None)
            generate_kwargs.pop("temperature", None)
            output = model.generate(input_ids, **generate_kwargs)
        duration = time.perf_counter() - start

        sequences = getattr(output, "sequences", output)
        full = sequences[0]
        new_tokens = full[prompt_tokens:] if len(full) > prompt_tokens else full
        text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        completion_tokens = int(len(new_tokens))

        metrics = GenerationMetrics(
            duration_seconds=round(duration, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_per_second=round(completion_tokens / duration, 3) if duration > 0 else 0.0,
            rss_gb=round(psutil.Process().memory_info().rss / GIB, 2),
            finished_at=time.time(),
        )
        with self._state_lock:
            self._state.last_generation = metrics
        logger.info(
            "generation_done",
            duration_s=metrics.duration_seconds,
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            tokens_per_second=metrics.tokens_per_second,
            rss_gb=metrics.rss_gb,
        )
        return text, metrics
