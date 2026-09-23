import importlib.util
from pathlib import Path

import pytest

_SERVER = Path(__file__).resolve().parents[2] / "integrations/openclaw/skills/jarvis-rag/server.py"


class _Response:
    status_code = 200

    def __init__(self, data: dict) -> None:
        self._data = data

    def json(self) -> dict:
        return self._data

    def raise_for_status(self) -> None:
        pass


class _FakeApi:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    def post(self, path: str, json: dict) -> _Response:
        self.posted.append(json)
        return _Response({"answer": "ok", "sources": []})


@pytest.fixture
def rag_server(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_INTERNAL_TOKEN", "test")
    spec = importlib.util.spec_from_file_location("jarvis_rag_server", _SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "MEMORY.md").write_text(
        "## Metodologías\n\n### Scrum\n\n### PMI\n\n## Proyectos\n\n"
        "- Estudio Delta › App de reservas: Scrum\n- Acme › ERP: PMI\n"
    )
    monkeypatch.setattr(module, "JARVIS_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(module, "_client", _FakeApi())
    return module


def test_ask_applies_project_methodology_from_memory(rag_server):
    answer = rag_server.jarvis_ask("¿Qué hago en la daily?", "Estudio Delta", "App de reservas")
    assert rag_server._client.posted[-1]["methodologies"] == ["scrum"]
    assert "Metodología del proyecto según MEMORY.md: scrum" in answer
    rag_server.jarvis_ask("¿Qué es la línea base?", "Acme", "ERP")
    assert rag_server._client.posted[-1]["methodologies"] == ["pmi"]


def test_ask_mixes_only_when_asked(rag_server):
    rag_server.jarvis_ask("Compara", "Acme", "ERP", methodology="PMI + Scrum")
    assert rag_server._client.posted[-1]["methodologies"] == ["PMI", "Scrum"]


def test_ask_without_project_or_memory_does_not_filter(rag_server, tmp_path):
    rag_server.jarvis_ask("¿Qué es un riesgo?")
    assert rag_server._client.posted[-1]["methodologies"] == []
    (tmp_path / "MEMORY.md").unlink()
    rag_server.jarvis_ask("¿Qué es un riesgo?", "Acme", "ERP")
    assert rag_server._client.posted[-1]["methodologies"] == []


def test_project_label_with_company_is_split(rag_server):
    rag_server.jarvis_ask("¿Qué es la daily?", project="Estudio Delta › App de reservas")
    sent = rag_server._client.posted[-1]
    assert (sent["company"], sent["project"]) == ("Estudio Delta", "App de reservas")
    assert sent["methodologies"] == ["scrum"]


def test_web_sources_lists_without_content_and_reads_only_approved(
    rag_server, monkeypatch, tmp_path
):
    monkeypatch.setattr(rag_server, "WEB_SOURCES_FILE", tmp_path / "web.json")
    results = [
        {"url": "https://scrumguides.org/guide.pdf", "title": "The Scrum Guide", "content": "8 h"},
        {"url": "https://blog.example/scrum", "title": "Un blog", "content": "4 h"},
        {"url": "javascript:alert(1)", "title": "Malo"},
    ]
    monkeypatch.setattr(rag_server, "_searxng", lambda query: results)
    listing = rag_server.jarvis_web_sources("sprint planning")
    assert "1. The Scrum Guide — scrumguides.org" in listing and "2. Un blog" in listing
    assert "8 h" not in listing and "javascript" not in listing
    assert "Indica qué fuentes" in rag_server.jarvis_web_read("ninguna")
    read = rag_server.jarvis_web_read("1")
    assert "8 h" in read and "4 h" not in read


def test_web_read_needs_a_previous_search(rag_server, monkeypatch, tmp_path):
    monkeypatch.setattr(rag_server, "WEB_SOURCES_FILE", tmp_path / "nada.json")
    assert "jarvis_web_sources" in rag_server.jarvis_web_read("1")


class _Documents(_FakeApi):
    def get(self, path: str) -> _Response:
        return _Response(
            {"documents": [{"filename": "pmbok.pdf", "doc_metadata": {"methodology": "PMI"}}]}
        )


def test_methodology_tools_keep_methods_apart(rag_server, tmp_path):
    rag_server._client = _Documents()
    assert "No se guardó" in rag_server.jarvis_set_methodology("Sprints", "- Sprints: 3 semanas")
    result = rag_server.jarvis_set_methodology("Scrum", "- Sprints: de tres semanas")
    assert "Guardado" in result and "No hay documentación de Scrum" in result
    assert "No hay documentación" not in rag_server.jarvis_set_methodology("PMI", "- Línea base")
    assert "Guardado" in rag_server.jarvis_set_methodology("Kanban", "- WIP: 3", new=True)
    result = rag_server.jarvis_set_project_methodology("Acme › Web", "Lean")
    assert "Lean no está definida" in result
    memory = (tmp_path / "MEMORY.md").read_text()
    assert "### Sprints" not in memory and "- Acme › Web: Lean" in memory
    assert "Guardado" in rag_server.jarvis_set_directive("Reuniones", "- Duración: 45 minutos")
