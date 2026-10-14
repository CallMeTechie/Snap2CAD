"""Verschluesselung des API-Schluessels mit SECRET_KEY (je Lauf ein eigener Prozess, gemeinsame Datenbank)."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from conftest import ROOT

KEY = "sk-ant-api03-geheimer-testschluessel-9876"
SECRET = "ein-langer-hauptschluessel-fuer-die-tests-0123456789"

SCRIPT = textwrap.dedent(r'''
    import sys
    from fastapi.testclient import TestClient
    from app import ai, settings
    from app.main import app

    ai.verify = lambda key, model=None: None
    H = {"X-Requested-With": "fetch"}
    step = sys.argv[1]
    with TestClient(app, client=("192.168.1.2", 1)) as c:
        if step == "setup":
            r = c.post("/api/setup", json={"username": "werkstatt", "password": "Fraesbahn-Aluminium-9",
                                           "api_key": sys.argv[2]}, headers=H)
            assert r.status_code == 200, r.text
        else:
            r = c.post("/api/auth/login", json={"username": "werkstatt", "password": "Fraesbahn-Aluminium-9"}, headers=H)
            assert r.status_code == 200, r.text
        k = c.get("/api/admin/settings").json()["api_key"]
        print("STATE", k["source"], k["encrypted"], k["secret_key_set"], settings.api_key() == sys.argv[2])
        if step == "replace":
            r = c.put("/api/admin/settings", json={"api_key": sys.argv[2], "password": "Fraesbahn-Aluminium-9"}, headers=H)
            assert r.status_code == 200, r.text
            k = r.json()["api_key"]
            print("STATE", k["source"], k["encrypted"], k["secret_key_set"], settings.api_key() == sys.argv[2])
''')


def _run(data: Path, step: str, key: str = KEY, secret: str = ""):
    e = {**os.environ, "DATA_DIR": str(data / "data"), "RUNS_DIR": str(data / "runs"), "AI_FAKE": "",
         "ANTHROPIC_API_KEY": "", "ADMIN_INITIAL_PASSWORD": "", "SANDBOX_MODE": "local", "PYTHONPATH": str(ROOT),
         "SECRET_KEY": secret}
    r = subprocess.run([sys.executable, "-c", SCRIPT, step, key], cwd=ROOT / "web", env=e, capture_output=True,
                       text=True, timeout=120)
    states = [ln.split()[1:] for ln in r.stdout.splitlines() if ln.startswith("STATE ")]
    return r, states


def _stored(data: Path) -> str:
    with sqlite3.connect(data / "data" / "snap2cad.db") as db:
        return db.execute("SELECT value FROM settings WHERE key='anthropic_api_key'").fetchone()[0]


def test_key_encrypted_with_secret_key():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        r, st = _run(d, "setup", secret=SECRET)
        assert st == [["db", "True", "True", "True"]], r.stdout + r.stderr
        raw = _stored(d)
        assert raw.startswith("enc:v1:") and KEY not in raw and "9876" not in raw
        # ohne SECRET_KEY: nicht lesbar, KI aus
        r, st = _run(d, "login")
        assert st == [["locked", "True", "False", "False"]], r.stdout + r.stderr
        assert "nicht entschlüsseln" in r.stdout
        # falscher SECRET_KEY: ebenso
        r, st = _run(d, "login", secret="x" * 40)
        assert st == [["locked", "True", "True", "False"]], r.stdout + r.stderr
        # neuer Schluessel mit falschem SECRET_KEY eingegeben: wieder lesbar
        r, st = _run(d, "replace", key="sk-ant-api03-ersatz-testschluessel-5555", secret="x" * 40)
        assert st[-1] == ["db", "True", "True", "True"], r.stdout + r.stderr


def test_plaintext_key_migrated_on_start():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        r, st = _run(d, "setup")
        assert st == [["db", "False", "False", "True"]], r.stdout + r.stderr
        assert _stored(d) == KEY
        r, st = _run(d, "login")  # beim naechsten Start: Hinweis im Log
        assert st == [["db", "False", "False", "True"]] and "unverschlüsselt" in r.stdout, r.stdout + r.stderr
        r, st = _run(d, "login", secret=SECRET)
        assert st == [["db", "True", "True", "True"]], r.stdout + r.stderr
        assert _stored(d).startswith("enc:v1:") and "verschlüsselt" in r.stdout
        with sqlite3.connect(d / "data" / "snap2cad.db") as db:
            assert db.execute("SELECT COUNT(*) FROM audit WHERE detail LIKE '%SECRET_KEY%'").fetchone()[0] == 1


def test_short_secret_key_refused():
    with tempfile.TemporaryDirectory() as d:
        r, st = _run(Path(d), "setup", secret="zu-kurz")
        assert r.returncode != 0 and "SECRET_KEY ist zu kurz" in r.stderr, r.stdout + r.stderr
