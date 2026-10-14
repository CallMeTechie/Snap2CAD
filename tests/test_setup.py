"""Ersteinrichtung (eigener Prozess mit leerer Datenbank) und Einstellungen in der Verwaltung."""
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from conftest import H, ROOT

SETUP_SCRIPT = textwrap.dedent(r'''
    import sys
    from fastapi.testclient import TestClient
    from app import ai, settings
    from app.main import app

    H = {"X-Requested-With": "fetch"}
    calls = []

    def fake_verify(key, model=None):
        calls.append((key, model))
        return None if key == "sk-ant-api03-gueltiger-testschluessel-0000" else "Anthropic lehnt diesen API-Schlüssel ab."

    ai.verify = fake_verify
    LAN, WAN = ("192.168.1.20", 50000), ("80.1.2.3", 50000)
    body = {"username": "werkstatt", "display_name": "Werkstatt", "email": "w@beispiel.de",
            "password": "Fraesbahn-Aluminium-9", "api_key": "sk-ant-api03-gueltiger-testschluessel-0000"}

    with TestClient(app, client=LAN) as c:
        me = c.get("/api/me").json()
        assert me["setup"] == {"required": True, "key_from_env": False, "key_optional": False, "allowed": True}, me
        assert me["ai"] is False
        # vor der Einrichtung gibt es kein Konto, auch kein Standard-admin
        r = c.post("/api/auth/login", json={"username": "admin", "password": "irgendwas-langes-1"}, headers=H)
        assert r.status_code == 401, r.text

    with TestClient(app, client=WAN) as w:
        assert w.get("/api/me").json()["setup"]["allowed"] is False
        r = w.post("/api/setup", json=body, headers=H)
        assert r.status_code == 403, r.text

    with TestClient(app, client=LAN) as c:
        r = c.post("/api/setup", json=body, headers={})  # ohne CSRF-Header
        assert r.status_code == 403
        for bad, fragment in [({"password": "kurz"}, "12 Zeichen"), ({"password": "werkstatt-ist-toll-1"}, "Benutzernamen"),
                              ({"username": "a b"}, "Benutzername"), ({"api_key": ""}, "API-Schlüssel"),
                              ({"api_key": "sk-ant-api03-falscher-testschluessel-000"}, "lehnt"),
                              ({"email": "keine-mail"}, "E-Mail")]:
            r = c.post("/api/setup", json={**body, **bad}, headers=H)
            assert r.status_code == 400 and fragment in r.text, (bad, r.text)
        assert c.get("/api/me").json()["setup"]["required"] is True  # nichts angelegt

        r = c.post("/api/setup", json=body, headers=H)
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u["username"] == "werkstatt" and u["role"] == "admin" and not u["must_change_pw"]
        me = c.get("/api/me").json()
        assert "setup" not in me and me["user"]["username"] == "werkstatt" and me["ai"] is True
        assert settings.api_key_source() == "db" and settings.api_key_hint() == "…0000"
        s = c.get("/api/admin/settings").json()
        assert s["api_key"] == {"source": "db", "hint": "…0000"}
        assert "gueltiger" not in c.get("/api/admin/settings").text  # Schluessel nie im Klartext zurueck
        # zweiter Versuch: bereits eingerichtet
        r = c.post("/api/setup", json={**body, "username": "zweiter"}, headers=H)
        assert r.status_code == 409, r.text
        audit = [a["action"] for a in c.get("/api/admin/audit").json()]
        assert "setup" in audit and "setup_denied" in audit

    with TestClient(app, client=LAN) as c2:
        r = c2.post("/api/auth/login", json={"username": "w@beispiel.de", "password": body["password"]}, headers=H)
        assert r.status_code == 200, r.text
        # Schluessel ersetzen: ungueltiger wird abgelehnt, alter bleibt
        r = c2.put("/api/admin/settings", json={"api_key": "sk-ant-api03-falscher-testschluessel-000"}, headers=H)
        assert r.status_code == 400 and settings.api_key_hint() == "…0000"
        r = c2.put("/api/admin/settings", json={"clear_api_key": True}, headers=H)
        assert r.status_code == 200 and r.json()["api_key"]["source"] == "none"
        assert c2.get("/api/me").json()["ai"] is False

    from app import manage
    assert manage.main(["reset-link", "werkstatt"]) == 0
    assert manage.main(["reset-link", "gibtsnicht"]) == 1
    print("SETUP-OK")
''')


def _run(tmp: Path, **env):
    e = {**os.environ, "DATA_DIR": str(tmp / "data"), "RUNS_DIR": str(tmp / "runs"), "AI_FAKE": "",
         "ANTHROPIC_API_KEY": "", "ADMIN_INITIAL_PASSWORD": "", "SANDBOX_MODE": "local", "PYTHONPATH": str(ROOT), **env}
    return subprocess.run([sys.executable, "-c", SETUP_SCRIPT], cwd=ROOT / "web", env=e, capture_output=True,
                          text=True, timeout=120)


def test_first_run_setup_wizard():
    with tempfile.TemporaryDirectory() as d:
        r = _run(Path(d))
        assert "SETUP-OK" in r.stdout, r.stdout + r.stderr
        assert "Passwort:" not in r.stdout  # kein Passwort im Log


def test_setup_closed_once_users_exist(admin):
    r = admin.post("/api/setup", json={"username": "neu", "password": "Fraesbahn-Aluminium-9", "api_key": ""}, headers=H)
    assert r.status_code == 409
    assert "setup" not in admin.get("/api/me").json()


def test_setup_ip_rules():
    from app import auth
    assert auth.setup_ip_allowed("192.168.178.20")
    assert auth.setup_ip_allowed("10.0.0.5")
    assert auth.setup_ip_allowed("172.20.0.1")
    assert auth.setup_ip_allowed("127.0.0.1")
    assert auth.setup_ip_allowed("::1")
    assert auth.setup_ip_allowed("fd00::12")
    assert auth.setup_ip_allowed("::ffff:192.168.1.4")
    assert auth.setup_ip_allowed("100.101.102.103")  # Tailscale/CGNAT
    assert not auth.setup_ip_allowed("80.1.2.3")
    assert not auth.setup_ip_allowed("8.8.8.8")
    assert not auth.setup_ip_allowed("2a00:1450:4001::1")
    assert not auth.setup_ip_allowed("testclient")


def test_admin_settings(admin, user):
    from app import settings
    assert user.get("/api/admin/settings").status_code == 403
    s = admin.get("/api/admin/settings").json()
    assert s["api_key"]["source"] == "none" and s["ai_fake"] is True
    assert s["model"] == {"value": "claude-sonnet-5-5", "source": "default", "default": "claude-sonnet-5-5"}
    r = admin.put("/api/admin/settings", json={"api_key": "kein schluessel"}, headers=H)
    assert r.status_code == 400
    r = admin.put("/api/admin/settings", json={"api_key": "sk-ant-api03-testmodus-schluessel-abcd"}, headers=H)
    assert r.status_code == 200 and r.json()["api_key"] == {"source": "db", "hint": "…abcd"}
    r = admin.put("/api/admin/settings", json={"model": "claude-opus-5-5"}, headers=H)
    assert r.json()["model"]["value"] == "claude-opus-5-5" and admin.get("/api/me").json()["model"] == "claude-opus-5-5"
    assert admin.put("/api/admin/settings", json={"model": "bad model!"}, headers=H).status_code == 400
    r = admin.put("/api/admin/settings", json={"model": "", "clear_api_key": True}, headers=H)
    assert r.json()["model"]["source"] == "default" and r.json()["api_key"]["source"] == "none"
    assert settings.api_key() == ""


def test_env_key_takes_precedence():
    with tempfile.TemporaryDirectory() as d:
        script = textwrap.dedent(r'''
            from fastapi.testclient import TestClient
            from app.main import app
            with TestClient(app, client=("192.168.1.2", 1)) as c:
                s = c.get("/api/me").json()["setup"]
                assert s["key_from_env"] and s["key_optional"], s
                r = c.post("/api/setup", json={"username": "admin", "password": "Fraesbahn-Aluminium-9"},
                           headers={"X-Requested-With": "fetch"})
                assert r.status_code == 200, r.text
                st = c.get("/api/admin/settings").json()
                assert st["api_key"] == {"source": "env", "hint": "…wxyz"}, st
                r = c.put("/api/admin/settings", json={"clear_api_key": True}, headers={"X-Requested-With": "fetch"})
                assert r.status_code == 400
            print("ENV-OK")
        ''')
        e = {**os.environ, "DATA_DIR": f"{d}/data", "RUNS_DIR": f"{d}/runs", "AI_FAKE": "", "ADMIN_INITIAL_PASSWORD": "",
             "ANTHROPIC_API_KEY": "sk-ant-api03-aus-der-umgebung-wxyz", "SANDBOX_MODE": "local", "PYTHONPATH": str(ROOT)}
        r = subprocess.run([sys.executable, "-c", script], cwd=ROOT / "web", env=e, capture_output=True, text=True, timeout=120)
        assert "ENV-OK" in r.stdout, r.stdout + r.stderr
