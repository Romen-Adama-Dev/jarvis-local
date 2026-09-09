from packages.core.hardware import (
    LLAMA_31_8B,
    QWEN_25_7B,
    recommend_ollama_models,
)


def test_no_gpu_recommends_primary_only_and_flags_unverified():
    rec = recommend_ollama_models(None)
    assert rec.primary_model == QWEN_25_7B
    assert rec.powerful_model is None
    assert rec.tier == "cpu_only"
    assert rec.verified is False


def test_insufficient_vram_falls_back_and_flags_unverified():
    rec = recommend_ollama_models(2000)
    assert rec.primary_model == QWEN_25_7B
    assert rec.powerful_model is None
    assert rec.tier == "low_vram"
    assert rec.verified is False


def test_enough_for_primary_only_disables_powerful():
    rec = recommend_ollama_models(6000)
    assert rec.primary_model == QWEN_25_7B
    assert rec.powerful_model is None
    assert rec.tier == "primary_only"
    assert rec.verified is True


def test_benchmarked_hardware_recommends_validated_pair():
    rec = recommend_ollama_models(7500)
    assert rec.primary_model == QWEN_25_7B
    assert rec.powerful_model == LLAMA_31_8B
    assert rec.tier == "validated"
    assert rec.verified is True


def test_ample_vram_keeps_validated_pair_but_flags_unverified_headroom():
    rec = recommend_ollama_models(24000)
    assert rec.primary_model == QWEN_25_7B
    assert rec.powerful_model == LLAMA_31_8B
    assert rec.tier == "ample"
    assert rec.verified is False
