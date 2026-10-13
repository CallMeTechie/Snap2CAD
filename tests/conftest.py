"""Gemeinsame Test-Einrichtung.

Die App liest ihre Konfiguration beim Import aus Umgebungsvariablen. Deshalb wird die Umgebung hier
gesetzt, bevor irgendein Test `app` importiert: eigenes Datenverzeichnis, KI-Testmodus (keine echten
API-Aufrufe), Sandbox im lokalen Modus und kurze Zeitlimits.
"""
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="snap2cad-test-"))

os.environ.update({
    "DATA_DIR": str(TMP / "data"),
    "RUNS_DIR": str(TMP / "runs"),
    "AI_FAKE": "1",
    "ANTHROPIC_API_KEY": "",
    "SANDBOX_MODE": "local",
    "SANDBOX_TIMEOUT": "20",
    "SANDBOX_MEM_MB": "3072",
    "ADMIN_INITIAL_PASSWORD": "Start-Passwort-1",
    "DEFAULT_QUOTA": "3",
    "MAX_UPLOAD_MB": "8",
})
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))

H = {"X-Requested-With": "fetch"}
ADMIN_PW = "Bohrmaschine-Fraese-42"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def admin(app):
    """Angemeldeter Admin (Startpasswort bereits geaendert)."""
    from fastapi.testclient import TestClient
    c = TestClient(app)
    c.__enter__()
    r = c.post("/api/auth/login", json={"username": "admin", "password": "Start-Passwort-1"}, headers=H)
    if r.status_code == 200 and r.json()["user"]["must_change_pw"]:
        r = c.post("/api/auth/change-password", json={"current": "Start-Passwort-1", "new": ADMIN_PW}, headers=H)
        assert r.status_code == 200, r.text
    elif r.status_code != 200:
        r = c.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, headers=H)
        assert r.status_code == 200, r.text
    yield c
    c.__exit__(None, None, None)


_counter = {"n": 0}


@pytest.fixture()
def user(app, admin):
    """Frischer Nutzer, per Einladung angelegt und angemeldet."""
    from fastapi.testclient import TestClient
    _counter["n"] += 1
    name = f"nutzer{_counter['n']}"
    r = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H)
    token = r.json()["link"].rsplit("/", 1)[1]
    c = TestClient(app)
    r = c.post(f"/api/invite/{token}", json={"username": name, "display_name": name.title(),
                                              "password": "Schieblehre-Messing-7"}, headers=H)
    assert r.status_code == 200, r.text
    c.username = name
    return c


def _render_page(fmt: str, page: int, px_per_mm: float = 6.0):
    """PDF-Seite der Messunterlage als BGR-Bild rendern."""
    import cv2
    import numpy as np
    import pypdfium2 as pdfium

    from core import matgen
    buf = io.BytesIO()
    matgen.build(buf, fmt)
    pdf = pdfium.PdfDocument(buf.getvalue())
    img = pdf[page].render(scale=px_per_mm * 25.4 / 72).to_pil().convert("RGB")
    pdf.close()
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def synthetic_photo(fmt: str = "A4", page: int = 0, tilt: float = 0.06, blur: bool = True) -> bytes:
    """Gerendertes Blatt perspektivisch verzerrt auf grauem Grund – wie ein leicht schraeges Handyfoto."""
    import cv2
    import numpy as np
    sheet = _render_page(fmt, page)
    h, w = sheet.shape[:2]
    if page == 0:  # ein dunkles "Bauteil" mittig auflegen
        cv2.rectangle(sheet, (int(w * 0.35), int(h * 0.42)), (int(w * 0.65), int(h * 0.56)), (40, 42, 45), -1)
    W, H_ = int(w * 1.3), int(h * 1.2)
    dx, dy = w * tilt, h * tilt * 0.5
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * 0.15 + dx, h * 0.1], [w * 1.15 - dx, h * 0.1 + dy], [w * 1.15, h * 1.1], [w * 0.15, h * 1.1 - dy]])
    M = cv2.getPerspectiveTransform(src, dst)
    photo = cv2.warpPerspective(sheet, M, (W, H_), borderValue=(110, 112, 115))
    if blur:
        photo = cv2.GaussianBlur(photo, (3, 3), 0.8)
    ok, data = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return data.tobytes()


@pytest.fixture(scope="session")
def photo_a4() -> bytes:
    return synthetic_photo("A4", 0)


@pytest.fixture(scope="session")
def photo_a3() -> bytes:
    return synthetic_photo("A3", 0)


@pytest.fixture(scope="session")
def photo_gauge() -> bytes:
    return synthetic_photo("A4", 1, tilt=0.03)
