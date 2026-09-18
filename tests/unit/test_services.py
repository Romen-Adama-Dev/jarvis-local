from packages.core import services


def test_statuses_follow_profiles_and_tailscale(monkeypatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "tailscale,pm")
    monkeypatch.setenv("OPENPROJECT_HTTPS_PORT", "9445")
    monkeypatch.setattr(services, "_is_up", lambda s: s.name != "Redis")
    items = {s.service.name: s for s in services.statuses("jarvis.example.ts.net")}
    assert "OpenProject" in items and "n8n" not in items
    assert "Obsidian LiveSync (CouchDB)" not in items  # perfil livesync apagado
    assert items["Panel de OpenClaw"].tailnet_url == "https://jarvis.example.ts.net"
    assert items["OpenProject"].tailnet_url == "https://jarvis.example.ts.net:9445"
    assert items["API de Jarvis"].tailnet_url == ""
    assert items["API de Jarvis"].local_url == "http://127.0.0.1:8000/docs"
    assert items["PostgreSQL"].local_url == "127.0.0.1:5432"
    assert not items["Redis"].up


def test_without_tailscale_everything_is_local(monkeypatch):
    monkeypatch.setenv("COMPOSE_PROFILES", "pm")
    monkeypatch.setattr(services, "_is_up", lambda s: True)
    assert all(not s.tailnet_url for s in services.statuses("jarvis.example.ts.net"))


def test_vault_note_has_links_but_no_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPOSE_PROFILES", "tailscale,pm,livesync")
    monkeypatch.setenv("TAILSCALE_DNSNAME_FILE", str(tmp_path / "dnsname"))
    (tmp_path / "dnsname").write_text("jarvis.example.ts.net\n")
    monkeypatch.setattr(services, "_is_up", lambda s: True)
    monkeypatch.setattr(services, "tailnet_ip", lambda: "100.1.2.3")
    vault = tmp_path / "vault"
    vault.mkdir()
    note = services.write_vault_note(vault)
    assert note is not None
    text = note.read_text()
    assert "[https://jarvis.example.ts.net:8445](https://jarvis.example.ts.net:8445)" in text
    assert "`100.1.2.3`" in text
    assert "/run/jarvis/openproject_admin_password" in text
    assert "<!-- openclaw:wiki:raw-source -->" in text
    # Sin cambios reales no se reescribe (solo cambiaría la fecha).
    mtime = note.stat().st_mtime_ns
    services.write_vault_note(vault)
    assert note.stat().st_mtime_ns == mtime
    assert services.write_vault_note(tmp_path / "no-existe") is None
