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


def _render_k60(fmt: str, px: float):
    """Kleinteile-Blatt ausschnittweise rendern (Feld plus 30 mm Rand, statt der ganzen A4-Seite).
    Rueckgabe (BGR-Bild, Feldursprung im Bild in mm von unten links)."""
    import cv2
    import numpy as np
    import pypdfium2 as pdfium

    from core import matgen
    buf = io.BytesIO()
    matgen.build(buf, "K60")
    sp = matgen.layout(fmt)
    (gx, gy), (fw, fh) = sp["grid_origin_on_page_mm"], sp["grid_mm"]
    pw, ph = 210.0, 297.0
    m, pt = 30.0, 72 / 25.4
    crop = ((gx - m) * pt, (gy - m) * pt, (pw - gx - fw - m) * pt, (ph - gy - fh - m) * pt)  # links, unten, rechts, oben
    pdf = pdfium.PdfDocument(buf.getvalue())
    try:
        img = pdf[0 if fmt == "K60H" else 1].render(scale=px / pt, crop=crop).to_pil().convert("RGB")
    finally:
        pdf.close()
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR), (m, m)


def synthetic_photo(fmt: str = "A4", page: int = 0, tilt: float = 0.06, blur: bool = True,
                    objects: list[dict] | None = None, shadow: dict | None = None) -> bytes:
    """Gerendertes Blatt perspektivisch verzerrt auf grauem Grund – wie ein leicht schraeges Handyfoto.

    objects: Objekte in mm der Rasterflaeche (Ursprung unten links), z. B. {"rect": [x, y, w, h], "gray": 150}
    oder {"circle": [cx, cy, d], "gray": 235}. None = ein dunkles Rechteck mittig (bisheriges Verhalten).
    Optional je Objekt "alpha" (0..1): Pixel = alpha * gray + (1 - alpha) * Blatt (durchscheinendes Teil).
    shadow: Schlagschatten, z. B. {"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}: Streifen der Breite mm an
    den genannten Seiten der Bounding-Box jedes rect-/polygon-Objekts, dort Blatt * dark (Raster bleibt sichtbar)."""
    import cv2
    import numpy as np

    from core import matgen
    k60 = fmt in ("K60H", "K60D")
    px = 30.0 if k60 else 6.0
    if k60:
        sheet, (ox, oy) = _render_k60(fmt, px)
        objects = objects or []
    else:
        sheet = _render_page(fmt, page, px)
    h, w = sheet.shape[:2]
    if not k60 and page == 0 and objects is None:  # ein dunkles "Bauteil" mittig auflegen
        cv2.rectangle(sheet, (int(w * 0.35), int(h * 0.42)), (int(w * 0.65), int(h * 0.56)), (40, 42, 45), -1)
    elif k60 or page == 0:
        if not k60:
            ox, oy = matgen.layout(fmt)["grid_origin_on_page_mm"]
        page_h = h / px

        def P(x, y):
            return int(round((x + ox) * px)), int(round((page_h - (y + oy)) * px))
        for o in objects if shadow else []:  # Schatten zuerst zeichnen, das Objekt ueberdeckt ihn
            if "rect" in o:
                x, y, rw, rh = o["rect"]
            elif "polygon" in o:
                xs, ys = [q[0] for q in o["polygon"]], [q[1] for q in o["polygon"]]
                x, y, rw, rh = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
            else:
                continue
            m, sides = shadow["mm"], shadow["sides"]
            # jeder Streifen reicht um mm in die Ecke zur anderen Schattenseite: dort ueberlappen sie (dark ** 2)
            xl, xr = x - m * ("left" in sides), x + rw + m * ("right" in sides)
            yb, yt = y - m * ("bottom" in sides), y + rh + m * ("top" in sides)
            regions = [(x - m, yb, x, yt)] if "left" in sides else []
            regions += [(x + rw, yb, x + rw + m, yt)] if "right" in sides else []
            regions += [(xl, y - m, xr, y)] if "bottom" in sides else []
            regions += [(xl, y + rh, xr, y + rh + m)] if "top" in sides else []
            for x0, y0, x1, y1 in regions:
                (a0, b1), (a1, b0) = P(x0, y0), P(x1, y1)
                sheet[b0:b1, a0:a1] = (sheet[b0:b1, a0:a1].astype(np.float32) * shadow["dark"]).astype(np.uint8)
        for o in objects:
            g = (o["gray"],) * 3
            alpha = o.get("alpha", 1.0)
            layer = sheet.copy() if alpha < 1 else sheet
            if "rect" in o:
                x, y, rw, rh = o["rect"]
                cv2.rectangle(layer, P(x, y + rh), P(x + rw, y), g, -1)
            if "circle" in o:
                cx, cy, d = o["circle"]
                cv2.circle(layer, P(cx, cy), int(round(d / 2 * px)), g, -1, cv2.LINE_AA)
            if "polygon" in o:
                pts = np.array([P(x, y) for x, y in o["polygon"]], np.int32)
                cv2.fillPoly(layer, [pts], g, cv2.LINE_AA)
            if alpha < 1:  # nur in der Objektmaske mischen
                inside = (layer != sheet).any(axis=2)
                sheet[inside] = cv2.addWeighted(layer, alpha, sheet, 1 - alpha, 0)[inside]
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
    assert not k60 or len(data) < 8 * 1024 * 1024, "K60-Testfoto über dem Upload-Limit der Tests"
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


def bottom_of(objects: list[dict], rot: int, dx: float = 0.0, dy: float = 0.0, fmt: str = "A4", phi: float = 0.0) -> list[dict]:
    """Objekte so umrechnen, wie sie in der Unteransicht liegen: Umkehrung von vision.lage_matrix."""
    import numpy as np

    from core import vision
    gw, gh = vision.spec(fmt)["grid_mm"]
    inv = np.linalg.inv(vision.lage_matrix(rot, dx, dy, gw, gh, phi))
    out = []
    for o in objects:
        rest = {k: v for k, v in o.items() if k not in ("rect", "polygon", "circle")}
        if "rect" in o:
            x, y, w, h = o["rect"]
            out.append({**rest, "polygon": vision.apply_lage(inv, [[x, y], [x + w, y], [x + w, y + h], [x, y + h]])})
        elif "polygon" in o:
            out.append({**rest, "polygon": vision.apply_lage(inv, o["polygon"])})
        elif "circle" in o:
            cx, cy, d = o["circle"]
            (nx, ny), = vision.apply_lage(inv, [[cx, cy]])
            out.append({**rest, "circle": [nx, ny, d]})
    return out
