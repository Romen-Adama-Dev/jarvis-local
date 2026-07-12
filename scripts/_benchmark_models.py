import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

OLLAMA_HOST = "http://127.0.0.1:11434"

DEFAULT_CANDIDATES = [
    "llama3.1:8b-instruct-q4_K_M",
    "qwen2.5:7b-instruct-q4_K_M",
    "mistral:7b-instruct-q4_K_M",
    "gemma2:9b-instruct-q4_K_M",
]

PMI_CONTEXT = (
    "Según el PMBOK, el Valor Ganado (Earned Value, EV) es la medida del trabajo "
    "completado expresada en términos del presupuesto autorizado para ese trabajo. "
    "El Índice de Desempeño del Cronograma (SPI) se calcula como EV entre PV "
    "(Valor Planificado). Un SPI menor que 1 indica que el proyecto va retrasado "
    "respecto al cronograma planificado."
)

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "registrar_riesgo",
        "description": "Registra un riesgo en el registro de riesgos del proyecto",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "probabilidad": {"type": "string", "enum": ["baja", "media", "alta"]},
                "impacto": {"type": "string", "enum": ["bajo", "medio", "alto"]},
            },
            "required": ["nombre", "probabilidad", "impacto"],
        },
    },
}

PROMPTS: list[dict[str, object]] = [
    {
        "id": "instrucciones_es",
        "kind": "chat",
        "messages": [
            {
                "role": "user",
                "content": (
                    "En exactamente 3 viñetas, explica la diferencia entre un riesgo "
                    "y un problema (issue) en la gestión de proyectos según el PMBOK."
                ),
            }
        ],
    },
    {
        "id": "extraccion_estructurada",
        "kind": "chat",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Devuelve SOLO un JSON válido (sin texto adicional) con una lista "
                    "'grupos_de_procesos' que contenga los 5 grupos de procesos del "
                    "PMBOK en orden: inicio, planificación, ejecución, monitoreo y "
                    "control, y cierre."
                ),
            }
        ],
    },
    {
        "id": "contexto_rag_con_evidencia",
        "kind": "chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Responde EXCLUSIVAMENTE con la información delimitada por "
                    "<contexto>. Si no hay evidencia suficiente dilo explícitamente."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"<contexto>{PMI_CONTEXT}</contexto>\n\n" "Pregunta: ¿qué indica un SPI de 0.8?"
                ),
            },
        ],
    },
    {
        "id": "contexto_rag_sin_evidencia",
        "kind": "chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Responde EXCLUSIVAMENTE con la información delimitada por "
                    "<contexto>. Si no hay evidencia suficiente dilo explícitamente, "
                    "no inventes una respuesta."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"<contexto>{PMI_CONTEXT}</contexto>\n\nPregunta: ¿cuáles son las "
                    "seis restricciones dobles (triple constraint extendido) del "
                    "PMBOK 7 y cómo se relacionan con la gestión de interesados?"
                ),
            },
        ],
    },
    {
        "id": "tool_calling",
        "kind": "chat",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Se ha identificado que el proveedor principal del proyecto tiene "
                    "una probabilidad alta de retrasar la entrega de materiales, con "
                    "impacto alto en el cronograma. Registra este riesgo usando la "
                    "herramienta disponible."
                ),
            }
        ],
        "tools": [TOOL_SCHEMA],
    },
]


@dataclass
class PromptResult:
    prompt_id: str
    ttft_ms: float
    total_ms: float
    prompt_tokens: int
    completion_tokens: int
    tokens_per_second: float
    tool_call_emitted: bool
    response_preview: str
    error: str | None = None


@dataclass
class ModelReport:
    model: str
    pulled: bool
    vram_idle_mib: int
    vram_loaded_mib: int
    processor: str
    prompts: list[PromptResult] = field(default_factory=list)
    error: str | None = None


def gpu_memory_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip().splitlines()[0])


def ollama_processor(model: str) -> str:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, check=True)
    for line in out.stdout.splitlines()[1:]:
        if line.startswith(model):
            parts = line.split()
            for i, tok in enumerate(parts):
                if tok in {"GPU", "CPU"} or "%" in tok:
                    return " ".join(parts[i - 1 : i + 1]) if "%" in tok else tok
    return "unknown"


def ensure_pulled(model: str) -> bool:
    out = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
    if any(line.split()[0] == model for line in out.stdout.splitlines()[1:] if line.strip()):
        return False
    print(f">>> Descargando {model}", file=sys.stderr)
    subprocess.run(["ollama", "pull", model], check=True)
    return True


def run_prompt(client: httpx.Client, model: str, prompt: dict) -> PromptResult:
    payload = {"model": model, "messages": prompt["messages"], "stream": True}
    if "tools" in prompt:
        payload["tools"] = prompt["tools"]

    start = time.perf_counter()
    first_token_at: float | None = None
    text_parts: list[str] = []
    tool_call_emitted = False
    final: dict = {}

    with client.stream("POST", "/api/chat", json=payload, timeout=180.0) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            message = chunk.get("message", {})
            if message.get("content") and first_token_at is None:
                first_token_at = time.perf_counter()
            if message.get("content"):
                text_parts.append(message["content"])
            if message.get("tool_calls"):
                tool_call_emitted = True
            if chunk.get("done"):
                final = chunk

    end = time.perf_counter()
    ttft_ms = ((first_token_at or end) - start) * 1000
    total_ms = (end - start) * 1000
    eval_count = int(final.get("eval_count", 0))
    eval_duration_s = final.get("eval_duration", 0) / 1e9
    tokens_per_second = eval_count / eval_duration_s if eval_duration_s > 0 else 0.0

    return PromptResult(
        prompt_id=prompt["id"],
        ttft_ms=round(ttft_ms, 1),
        total_ms=round(total_ms, 1),
        prompt_tokens=int(final.get("prompt_eval_count", 0)),
        completion_tokens=eval_count,
        tokens_per_second=round(tokens_per_second, 1),
        tool_call_emitted=tool_call_emitted,
        response_preview="".join(text_parts)[:200],
    )


def benchmark_model(client: httpx.Client, model: str) -> ModelReport:
    vram_idle = gpu_memory_used_mib()
    pulled = ensure_pulled(model)
    try:
        warmup = {
            "model": model,
            "messages": [{"role": "user", "content": "hola"}],
            "stream": False,
        }
        client.post("/api/chat", json=warmup, timeout=180.0).raise_for_status()
        vram_loaded = gpu_memory_used_mib()
        processor = ollama_processor(model)

        report = ModelReport(
            model=model,
            pulled=pulled,
            vram_idle_mib=vram_idle,
            vram_loaded_mib=vram_loaded,
            processor=processor,
        )
        for prompt in PROMPTS:
            try:
                result = run_prompt(client, model, prompt)
                print(
                    f"  {model} :: {result.prompt_id} :: {result.tokens_per_second} tok/s",
                    file=sys.stderr,
                )
            except httpx.HTTPStatusError as exc:
                result = PromptResult(
                    prompt_id=prompt["id"],
                    ttft_ms=0.0,
                    total_ms=0.0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    tokens_per_second=0.0,
                    tool_call_emitted=False,
                    response_preview="",
                    error=str(exc),
                )
                print(f"  {model} :: {result.prompt_id} :: ERROR {exc}", file=sys.stderr)
            report.prompts.append(result)
        return report
    except Exception as exc:  # noqa: BLE001
        return ModelReport(
            model=model,
            pulled=pulled,
            vram_idle_mib=vram_idle,
            vram_loaded_mib=vram_idle,
            processor="error",
            error=str(exc),
        )
    finally:
        subprocess.run(["ollama", "stop", model], capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=",".join(DEFAULT_CANDIDATES))
    parser.add_argument("--output", default="docs/benchmarks")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    reports: list[ModelReport] = []
    with httpx.Client(base_url=OLLAMA_HOST) as client:
        for model in models:
            print(f"== Benchmarking {model} ==", file=sys.stderr)
            reports.append(benchmark_model(client, model))

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_path = output_dir / f"ollama-{timestamp}.json"
    out_path.write_text(
        json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2))
    print(f"Resultados guardados en {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
