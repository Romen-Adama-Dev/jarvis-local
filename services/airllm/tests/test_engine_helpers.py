from dataclasses import dataclass
from pathlib import Path

import huggingface_hub

from airllm_service.engine import build_prompt, disk_report, estimate_remote_model_bytes


class FakeTemplateTokenizer:
    chat_template = "{{ messages }}"

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize is False
        assert add_generation_prompt is True
        return "|".join(f"{m['role']}={m['content']}" for m in messages)


class FakePlainTokenizer:
    chat_template = None


def test_build_prompt_uses_chat_template():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hola"}]
    assert build_prompt(FakeTemplateTokenizer(), messages) == "system=s|user=hola"


def test_build_prompt_fallback_without_template():
    messages = [{"role": "user", "content": "hola"}]
    prompt = build_prompt(FakePlainTokenizer(), messages)
    assert prompt == "user: hola\n\nassistant:"


def test_disk_report_shape(tmp_path: Path):
    report = disk_report(tmp_path)
    assert set(report) == {"total_gb", "used_gb", "free_gb"}
    assert report["total_gb"] > 0


@dataclass
class FakeSibling:
    rfilename: str
    size: int | None


@dataclass
class FakeInfo:
    siblings: list[FakeSibling]


def test_estimate_prefers_safetensors_over_bin_duplicates(monkeypatch):
    info = FakeInfo(
        siblings=[
            FakeSibling("model-00001-of-00002.safetensors", 10),
            FakeSibling("model-00002-of-00002.safetensors", 6),
            FakeSibling("pytorch_model-00001-of-00002.bin", 9),
            FakeSibling("pytorch_model-00002-of-00002.bin", 5),
            FakeSibling("config.json", 1),
            FakeSibling("model.safetensors.index.json", None),
        ]
    )

    class FakeApi:
        def model_info(self, repo_id, files_metadata):
            return info

    monkeypatch.setattr(huggingface_hub, "HfApi", FakeApi)
    assert estimate_remote_model_bytes("org/model") == 16


def test_estimate_falls_back_to_bin(monkeypatch):
    info = FakeInfo(siblings=[FakeSibling("pytorch_model.bin", 7)])

    class FakeApi:
        def model_info(self, repo_id, files_metadata):
            return info

    monkeypatch.setattr(huggingface_hub, "HfApi", FakeApi)
    assert estimate_remote_model_bytes("org/model") == 7
