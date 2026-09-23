import pytest

from packages.admin import core


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("jarvis/feat-directivas-reuniones", True),
        ("jarvis/fix-typo", True),
        ("main", False),
        ("feat/memoria-directivas", False),  # ramas de otros: nunca
        ("jarvis/feat-../../main", False),
        ("jarvis/Feat-x", False),
    ],
)
def test_valid_branch(name, ok):
    assert core.valid_branch(name) is ok


def test_check_service():
    services = ["api", "openclaw", "admin"]
    assert core.check_service("api", services) is None
    assert "no se gestiona" in core.check_service("admin", services)
    assert "Hay: admin, api, openclaw" in core.check_service("nada", services)


def test_log_lines_are_bounded():
    assert core.log_lines(0) == 1
    assert core.log_lines(10_000) == core.MAX_LOG_LINES


def test_parse_ps_accepts_both_formats():
    assert core.parse_ps('[{"Service": "api"}]') == [{"Service": "api"}]
    assert core.parse_ps('{"Service": "api"}\n{"Service": "worker"}\n') == [
        {"Service": "api"},
        {"Service": "worker"},
    ]
    assert core.parse_ps("") == []


def test_known_secrets_and_redact(tmp_path):
    env = tmp_path / ".env"
    env.write_text("POSTGRES_PASSWORD=supersecreta1\nLOG_LEVEL=INFO\nAPI_TOKEN=corto\n")
    runtime = tmp_path / "run"
    runtime.mkdir()
    (runtime / "jarvis_admin_token").write_text("abcdef0123456789\n")
    (runtime / "models.env").write_text("OLLAMA_PRIMARY_MODEL=gemma\n")
    secrets = core.known_secrets(env, runtime)
    assert secrets == ["abcdef0123456789", "supersecreta1"]  # corto e INFO no cuentan
    text = "password supersecreta1 token abcdef0123456789 ghp_" + "a" * 36
    assert core.redact(text, secrets) == "password *** token *** ***"


def test_secrets_in_diff_flags_only_added_lines():
    diff = (
        "+++ b/docs/x.md\n+texto normal\n-supersecreta1\n"
        "+++ b/config.json\n+clave: supersecreta1\n"
        "+++ b/k.txt\n+-----BEGIN OPENSSH PRIVATE KEY-----\n"
    )
    assert core.secrets_in_diff(diff, ["supersecreta1"]) == ["config.json", "k.txt"]


def test_forbidden_files():
    paths = [".env", "infra/.env.prod", ".env.example", "backups/2026/x.sql", "a/id_ed25519",
             "docs/ok.md"]  # fmt: skip
    assert core.forbidden_files(paths) == [
        ".env",
        "infra/.env.prod",
        "backups/2026/x.sql",
        "a/id_ed25519",
    ]
