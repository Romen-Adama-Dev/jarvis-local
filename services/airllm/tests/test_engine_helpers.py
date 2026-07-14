from pathlib import Path

from airllm_service.engine import build_prompt, disk_report


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
