import importlib.util
from pathlib import Path

import pytest

_SERVER = (
    Path(__file__).resolve().parents[2] / "integrations/openclaw/skills/jarvis-calendar/server.py"
)


@pytest.fixture
def calendar_server(monkeypatch):
    monkeypatch.setenv("JARVIS_API_INTERNAL_TOKEN", "test")
    monkeypatch.setenv("JARVIS_OWNER_TELEGRAM_ID", "1")
    spec = importlib.util.spec_from_file_location("jarvis_calendar_server", _SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("attendees", "split"),
    [
        ("Marcos Peña, Nuria Castro", ["Marcos Peña", "Nuria Castro"]),
        ("Marcos Peña y Nuria Castro", ["Marcos Peña", "Nuria Castro"]),
        ("ana@example.com cliente@panaderia.es", ["ana@example.com", "cliente@panaderia.es"]),
        ("Nuria Castro; marcos.pena@demo.invalid", ["Nuria Castro", "marcos.pena@demo.invalid"]),
        ("  ", []),
    ],
)
def test_names_with_spaces_stay_whole(calendar_server, attendees, split):
    assert calendar_server._split_attendees(attendees) == split
