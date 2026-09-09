"""Detección de hardware y recomendación de modelos Ollama.

Sin dependencias de terceros a propósito: lo usa tanto la aplicación (vía
``uv run``) como ``scripts/quickstart`` con el ``python3`` del sistema, antes
de que exista un entorno virtual.

Los modelos y umbrales están anclados a la evidencia real de
``docs/BENCHMARKS.md`` (GTX 1070, 8192 MiB VRAM): de los 4 modelos
evaluados, solo ``qwen2.5:7b`` y ``llama3.1:8b`` soportan tool calling nativo
de Ollama y rechazan responder cuando el contexto no tiene evidencia
suficiente. Fuera del rango de VRAM medido, este módulo nunca inventa un
modelo nuevo: degrada la recomendación explícitamente y señala
``scripts/benchmark-models`` para validar candidatos en ese hardware.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass

QWEN_25_7B = "qwen2.5:7b-instruct-q4_K_M"
QWEN_25_7B_LOADED_VRAM_MIB = 4639
LLAMA_31_8B = "llama3.1:8b-instruct-q4_K_M"
LLAMA_31_8B_LOADED_VRAM_MIB = 5137

# docs/BENCHMARKS.md descarta gemma2:9b (7057/8192 MiB, ~86% de la VRAM total,
# "insuficiente para considerarlo seguro") y acepta llama3.1:8b (5137/8192,
# ~63%). Exigimos que la huella cargada de un modelo quepa en, como mucho,
# este porcentaje de la VRAM libre detectada.
SAFETY_MARGIN = 0.8


@dataclass(frozen=True)
class ModelRecommendation:
    primary_model: str
    powerful_model: str | None
    tier: str
    rationale: str
    verified: bool


def detect_gpu_free_vram_mib() -> int | None:
    """VRAM libre (MiB) de la primera GPU NVIDIA vía ``nvidia-smi``.

    ``None`` si no hay ``nvidia-smi`` en PATH, falla, o no devuelve un
    número (sin GPU NVIDIA, sin driver, o sandbox sin acceso a la GPU).
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    try:
        return int(first_line)
    except ValueError:
        return None


def recommend_ollama_models(free_vram_mib: int | None) -> ModelRecommendation:
    """Recomienda PRIMARY/POWERFUL (modo NORMAL) a partir de la VRAM libre.

    Nunca recomienda un modelo distinto del par validado en
    ``docs/BENCHMARKS.md``: con más VRAM libre que la probada sigue
    devolviendo el mismo par (funcionará igual o mejor) marcado
    ``verified=False``, invitando a re-benchmarkear con candidatos mayores
    en vez de inventar una recomendación sin medir.
    """
    if free_vram_mib is None:
        return ModelRecommendation(
            primary_model=QWEN_25_7B,
            powerful_model=None,
            tier="cpu_only",
            rationale=(
                "No se detectó GPU NVIDIA (nvidia-smi no disponible). "
                f"{QWEN_25_7B} se deja como valor por defecto, pero su "
                "rendimiento en CPU no está medido en este repositorio "
                "(docs/BENCHMARKS.md solo mide GPU): ejecuta "
                "scripts/benchmark-models para validarlo en este hardware."
            ),
            verified=False,
        )

    primary_threshold_mib = QWEN_25_7B_LOADED_VRAM_MIB / SAFETY_MARGIN
    powerful_threshold_mib = LLAMA_31_8B_LOADED_VRAM_MIB / SAFETY_MARGIN

    if free_vram_mib < primary_threshold_mib:
        return ModelRecommendation(
            primary_model=QWEN_25_7B,
            powerful_model=None,
            tier="low_vram",
            rationale=(
                f"Solo {free_vram_mib} MiB de VRAM libre, por debajo del "
                f"margen seguro para {QWEN_25_7B} ({QWEN_25_7B_LOADED_VRAM_MIB} "
                f"MiB cargado, {primary_threshold_mib:.0f} MiB exigidos con un "
                f"margen del {int(SAFETY_MARGIN * 100)}%). Riesgo real de CUDA "
                "OOM: libera VRAM o ejecuta scripts/benchmark-models con "
                "candidatos más pequeños."
            ),
            verified=False,
        )

    if free_vram_mib < powerful_threshold_mib:
        return ModelRecommendation(
            primary_model=QWEN_25_7B,
            powerful_model=None,
            tier="primary_only",
            rationale=(
                f"{free_vram_mib} MiB de VRAM libre alcanzan para {QWEN_25_7B} "
                f"con margen seguro, pero no para {LLAMA_31_8B} "
                f"({LLAMA_31_8B_LOADED_VRAM_MIB} MiB cargado, "
                f"{powerful_threshold_mib:.0f} MiB exigidos con margen). Modo "
                "potente desactivado."
            ),
            verified=True,
        )

    tier = "validated" if free_vram_mib <= 8192 else "ample"
    rationale = (
        f"{free_vram_mib} MiB de VRAM libre: par validado en "
        "docs/BENCHMARKS.md (GTX 1070, 8192 MiB) — los únicos dos modelos de "
        "los 4 evaluados que soportan tool calling nativo y no inventan "
        "respuestas sin evidencia."
    )
    if tier == "ample":
        rationale += (
            " Hay más VRAM libre que en el hardware benchmarkeado: este par "
            "sigue siendo seguro, pero no se ha probado si un modelo mayor "
            "daría mejor calidad en esta GPU — ejecuta scripts/benchmark-models "
            "con candidatos más grandes para explorarlo."
        )
    return ModelRecommendation(
        primary_model=QWEN_25_7B,
        powerful_model=LLAMA_31_8B,
        tier=tier,
        rationale=rationale,
        verified=(tier == "validated"),
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    free_vram = detect_gpu_free_vram_mib()
    recommendation = recommend_ollama_models(free_vram)

    if args.format == "json":
        print(json.dumps(asdict(recommendation), ensure_ascii=False))
        return

    print(f"VRAM libre detectada: {free_vram if free_vram is not None else 'sin GPU NVIDIA'} MiB")
    print(f"Nivel: {recommendation.tier} (verificado en benchmark: {recommendation.verified})")
    print(f"OLLAMA_PRIMARY_MODEL={recommendation.primary_model}")
    print(f"OLLAMA_POWERFUL_MODEL={recommendation.powerful_model or ''}")
    print(f"Motivo: {recommendation.rationale}")


if __name__ == "__main__":
    _main()
