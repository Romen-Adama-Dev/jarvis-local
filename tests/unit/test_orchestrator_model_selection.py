from packages.rag.orchestrator import select_normal_model


def test_uses_fast_default_when_no_powerful_model_configured():
    assert select_normal_model("contexto corto", powerful_model=None) is None


def test_uses_fast_default_for_short_context():
    short_context = "x" * 100
    assert select_normal_model(short_context, powerful_model="llama3.1:8b") is None


def test_switches_to_powerful_model_for_large_context():
    large_context = "x" * 3500
    assert select_normal_model(large_context, powerful_model="llama3.1:8b") == "llama3.1:8b"


def test_respects_custom_threshold():
    context = "x" * 500
    assert (
        select_normal_model(context, powerful_model="llama3.1:8b", threshold_chars=400)
        == "llama3.1:8b"
    )
    assert select_normal_model(context, powerful_model="llama3.1:8b", threshold_chars=600) is None
