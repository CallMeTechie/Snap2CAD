# Unteransicht, Prüfung vor dem Auftrag, Material und Kontrast – Umsetzungsplan (Stufe A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die CAD-KI bekommt eine ausgerichtete Unteransicht, verbindliche Umrisse, Schrägfotos im Original, eine Prüfung vor dem Auftrag und Werkstück-Angaben; die Kantenerkennung ignoriert Schlagschatten und kommt mit transparenten Teilen zurecht.

**Architecture:** Drei Wellen auf einem Branch. W1 (Tasks 1–4): Lage-Mathematik in `core/vision.py`, Ausrichtung und `bottom`-Ansicht im Server, Verknüpfung der Teile, Oberfläche. W2 (Tasks 5–9): Werkstück-Spalten, Prompt und Temperatur, Bildauswahl und Auftragsnachricht, Endpunkt `cad-check`, Oberfläche. W3 (Task 10): Kantenerkennung mit Hinweisen, Kontrast, veraltete Kanten. Task 11: Durchlauf im Browser, Review, Auslieferung.

**Tech Stack:** Python 3.13, FastAPI, SQLite, OpenCV, numpy, shapely; Vanilla-JS-Module; pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-15-unteransicht-pruefung-material-design.md`

## Global Constraints

- Entscheidungen des Nutzers (Spec „Entscheidungen des Nutzers“) sind gesetzt: Prüfung vor dem Auftrag; vier Lagen mit Handwahl; KI schätzt Werkstück, Handeingabe hat Vorrang; `same_as` automatisch über IoU ≥ 0,5; Hinweise für die Kantenerkennung nur aus `material_user=1`; Prüfung automatisch, sobald veraltet; neue KI-Schätzung ersetzt alte.
- Lage: `lage_matrix(rot, dx, dy, w, h) = Verschiebung(dx, dy) · Drehung(rot um (w/2, h/2), gegen den Uhrzeigersinn) · Spiegelung(x → w − x)`; `rot ∈ {0, 90, 180, 270}`; Festwert `lage_matrix(90, 0, 0, 190, 230)`: (10, 20) → (190, 200). Alle Stellen (`align_bottom`, `to_top`, `bottom_warp`, `bottom_of`) rufen diese eine Funktion.
- Höchstens 6 Bilder je Nachricht, Reihenfolge Draufsicht, Unteransicht, Höhenlehre, Schrägfotos (`jobs.pick_images`).
- Texte in der Oberfläche ohne „Claude“/„Anthropic“ (bestehender Test `tests/test_texts.py`); KI-Text sagt „Fotografiertes Original“, Oberfläche „Werkstück“.
- `AI_DAILY_LIMIT = 30`; `_ai_uses_today` zählt `suggest`, `edges_ai`, `cad_check`.
- Echte Fotos nur im Scratchpad (`/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad/nasfotos/`), nie im Repo.
- Keine Claude-Attribution in Commits.
- Jede Welle endet mit grüner lokaler Suite: `source /root/Snap2CAD-venv/bin/activate && ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs`.

## Review Focus

1. Unteransicht in Lage 90 oder 270 mit Versatz: `to_top` und `rect_top.jpg` müssen dieselbe Abbildung zeigen (Task 1 Festwerte, Task 2 Test `test_align_jpg_und_to_top_gleich`).
2. Zwei Draufsichten im Projekt, die erste wird gelöscht: Ausrichtung wechselt auf die nächste Referenz, Handwahl bleibt (Task 2 Test `test_referenz_wechselt`).
3. Prüfung mit `photo_ids: null`, danach ein Foto hochgeladen: `stale` muss wahr werden (Task 8 Test `test_hash_aufgeloeste_fotos`).
4. Werkstück von der KI geschätzt, Nutzer öffnet das Formular erneut: kein zweiter KI-Aufruf (Task 8 Test `test_idempotent_nach_schaetzung`).
5. Schlagschatten bei dunklem Objekt und helles Objekt ohne Hinweise: beide weiterhin erkannt (Task 10, bestehende Tests `test_quader_umriss`, `test_heller_koerper_ohne_raster` bleiben grün).

---

## Welle 1 – Unteransicht

### Task 1: Lage-Mathematik und Ausrichtung in `core/vision.py`

**Files:**
- Modify: `core/vision.py` (nach `rectify_gauge`)
- Modify: `tests/conftest.py` (`synthetic_photo`: `polygon`-Objekte; neue Hilfsfunktion `bottom_of`)
- Create: `tests/test_align.py`

**Interfaces:**
- Produces: `vision.lage_matrix(rot: int, dx: float, dy: float, w: float, h: float) -> np.ndarray (3×3 float64)`; `vision.apply_lage(M, pts) -> list[list[float]]`; `vision.align_bottom(top_outline, bottom_outline, bot_w, bot_h, rot=None) -> dict` mit `rot, dx, dy, iou, iou_next, unsure`; `vision.bottom_warp(rect_bot, analysis_bot, analysis_top=None, pxmm_out=PX_PER_MM) -> np.ndarray`; `conftest.bottom_of(objects, rot, dx=0.0, dy=0.0, fmt="A4") -> list[dict]`.

- [ ] **Step 1: Failing tests schreiben**

`tests/test_align.py`:

```python
"""Lage der Unteransicht (Spec 2026-10-15 §1, A1)."""
import numpy as np
import pytest

from conftest import bottom_of, synthetic_photo
from core import edges, vision

L_SHAPE = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 120], [60, 120]]   # 60 x 40, Schenkel 15
HOLE = {"circle": [110, 87.5], "d": 5}


def test_lage_matrix_festwerte():
    M = vision.lage_matrix(90, 0, 0, 190, 230)
    assert vision.apply_lage(M, [[10, 20]])[0] == pytest.approx([190, 200])
    M2 = vision.lage_matrix(90, -30, 5, 190, 230)
    assert vision.apply_lage(M2, [[10, 20]])[0] == pytest.approx([160, 205])
    assert vision.apply_lage(vision.lage_matrix(0, 0, 0, 190, 230), [[10, 20]])[0] == pytest.approx([180, 20])
    assert vision.apply_lage(vision.lage_matrix(180, 0, 0, 190, 230), [[10, 20]])[0] == pytest.approx([10, 210])


def test_bottom_warp_festwert():
    a_bot = {"rect": {"pxmm": 10.0, "w_mm": 190.0, "h_mm": 230.0, "w": 1900, "h": 2300}, "bottom_align": {"rot": 90, "dx": 0, "dy": 0}}
    a_top = {"rect": {"pxmm": 10.0, "w_mm": 190.0, "h_mm": 230.0, "w": 1900, "h": 2300}}
    M = vision.bottom_warp_matrix(a_bot, a_top, 10.0)
    assert (M @ np.array([100.0, 2100.0, 1.0]))[:2] == pytest.approx([1900, 300], abs=1)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_align_bottom_findet_lage(rot):
    dx, dy = (25.0, -20.0) if rot in (0, 180) else (-30.0, 22.0)
    inv = np.linalg.inv(vision.lage_matrix(rot, dx, dy, 190, 230))
    bottom = vision.apply_lage(inv, L_SHAPE)
    r = vision.align_bottom(L_SHAPE, bottom, 190, 230)
    assert r["rot"] == rot and r["iou"] >= 0.9 and r["iou"] - r["iou_next"] >= 0.2 and not r["unsure"]
    assert (r["dx"], r["dy"]) == pytest.approx((dx, dy), abs=0.5)
    back = vision.apply_lage(vision.lage_matrix(r["rot"], r["dx"], r["dy"], 190, 230), [vision.apply_lage(inv, [HOLE["circle"]])[0]])[0]
    assert back == pytest.approx(HOLE["circle"], abs=0.5)


def test_align_bottom_vorgegebene_lage():
    inv = np.linalg.inv(vision.lage_matrix(90, 0, 0, 190, 230))
    r = vision.align_bottom(L_SHAPE, vision.apply_lage(inv, L_SHAPE), 190, 230, rot=270)
    assert r["rot"] == 270 and r["iou_next"] >= 0.9   # beste der uebrigen ist die richtige Lage 90


def test_rechteck_unsicher():
    R = [[60, 80], [120, 80], [120, 120], [60, 120]]
    r = vision.align_bottom(R, vision.apply_lage(np.linalg.inv(vision.lage_matrix(0, 0, 0, 190, 230)), R), 190, 230)
    assert r["unsure"] and r["rot"] in (0, 180)
    r = vision.align_bottom(R, vision.apply_lage(np.linalg.inv(vision.lage_matrix(90, 0, 0, 190, 230)), R), 190, 230)
    assert r["unsure"] and r["rot"] in (90, 270)


def test_synthetische_unteransicht_rot_90():
    top = [{"polygon": L_SHAPE, "gray": 150}]
    img_t = vision.load_image(synthetic_photo("A4", objects=top))
    a_t = vision.analyze(img_t, "A4")
    out_t = edges.detect(vision.rectify_mat(img_t, a_t["homography"], "A4"), "A4")["outlines"][0]["polygon"]
    img_b = vision.load_image(synthetic_photo("A4", objects=bottom_of(top, 90, -30, 22)))
    a_b = vision.analyze(img_b, "A4")
    out_b = edges.detect(vision.rectify_mat(img_b, a_b["homography"], "A4"), "A4")["outlines"][0]["polygon"]
    r = vision.align_bottom(out_t, out_b, 190, 230)
    assert r["rot"] == 90 and r["iou"] >= 0.9 and not r["unsure"]
```

`tests/conftest.py` – in `synthetic_photo` nach dem `circle`-Zweig einfügen und `bottom_of` am Dateiende ergänzen:

```python
            if "polygon" in o:
                pts = np.array([P(x, y) for x, y in o["polygon"]], np.int32)
                cv2.fillPoly(sheet, [pts], g, cv2.LINE_AA)
```

```python
def bottom_of(objects: list[dict], rot: int, dx: float = 0.0, dy: float = 0.0, fmt: str = "A4") -> list[dict]:
    """Objekte so umrechnen, wie sie in der Unteransicht liegen: Umkehrung von vision.lage_matrix."""
    import numpy as np

    from core import vision
    gw, gh = vision.spec(fmt)["grid_mm"]
    inv = np.linalg.inv(vision.lage_matrix(rot, dx, dy, gw, gh))
    out = []
    for o in objects:
        if "rect" in o:
            x, y, w, h = o["rect"]
            out.append({**{k: v for k, v in o.items() if k != "rect"}, "polygon": vision.apply_lage(inv, [[x, y], [x + w, y], [x + w, y + h], [x, y + h]])})
        elif "polygon" in o:
            out.append({**o, "polygon": vision.apply_lage(inv, o["polygon"])})
        elif "circle" in o:
            cx, cy, d = o["circle"]
            (nx, ny), = vision.apply_lage(inv, [[cx, cy]])
            out.append({**o, "circle": [nx, ny, d]})
    return out
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `source /root/Snap2CAD-venv/bin/activate && python -m pytest -q -p no:cacheprovider tests/test_align.py`
Expected: FAIL mit `AttributeError: module 'core.vision' has no attribute 'lage_matrix'` bzw. ImportError `bottom_of`.

- [ ] **Step 3: Implementierung in `core/vision.py`** (nach `rectify_gauge`)

```python
# ------------------------------------------------------------------ Unteransicht (Spec 2026-10-15 §1)

LAGEN = (0, 90, 180, 270)


def lage_matrix(rot: int, dx: float, dy: float, w: float, h: float) -> np.ndarray:
    """Lage einer Unteransicht in Draufsicht-Koordinaten (mm, y nach oben): Spiegelung x -> w - x,
    Drehung um rot Grad gegen den Uhrzeigersinn um die Bildmitte (w/2, h/2), Verschiebung (dx, dy)."""
    if rot not in LAGEN:
        raise ValueError(f"rot muss in {LAGEN} liegen")
    mirror = np.array([[-1, 0, w], [0, 1, 0], [0, 0, 1]], np.float64)
    a = np.deg2rad(rot)
    c, s = np.cos(a), np.sin(a)
    to_c = np.array([[1, 0, -w / 2], [0, 1, -h / 2], [0, 0, 1]], np.float64)
    rotm = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)
    from_c = np.array([[1, 0, w / 2], [0, 1, h / 2], [0, 0, 1]], np.float64)
    shift = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], np.float64)
    return shift @ from_c @ rotm @ to_c @ mirror


def apply_lage(M: np.ndarray, pts) -> list[list[float]]:
    P = np.asarray(pts, np.float64).reshape(-1, 2)
    Q = (M @ np.hstack([P, np.ones((len(P), 1))]).T).T
    return [[round(float(x), 3), round(float(y), 3)] for x, y, _ in Q]


def align_bottom(top_outline, bottom_outline, bot_w: float, bot_h: float, rot: int | None = None) -> dict:
    """Beste Lage der Unteransicht zur Draufsicht ueber die Ueberlappung der Umrisse (IoU je Lage nach
    Schwerpunkt-Verschiebung). rot=None: alle vier Lagen; sonst nur diese, iou_next = beste der uebrigen."""
    from shapely.geometry import Polygon  # nur hier: core/ bleibt ohne harte shapely-Abhaengigkeit

    def valid(p):
        g = Polygon(p)
        return g if g.is_valid else g.buffer(0)
    T = valid(top_outline)
    ct = T.centroid
    scores = {}
    for r in LAGEN:
        P = valid(apply_lage(lage_matrix(r, 0, 0, bot_w, bot_h), bottom_outline))
        cp = P.centroid
        dx, dy = ct.x - cp.x, ct.y - cp.y
        Q = valid(apply_lage(lage_matrix(r, dx, dy, bot_w, bot_h), bottom_outline))
        union = T.union(Q).area
        scores[r] = (T.intersection(Q).area / union if union > 0 else 0.0, dx, dy)
    best = rot if rot is not None else max(LAGEN, key=lambda r: (scores[r][0], -r))
    iou, dx, dy = scores[best]
    iou_next = max(scores[r][0] for r in LAGEN if r != best)
    return {"rot": best, "dx": round(dx, 3), "dy": round(dy, 3), "iou": round(iou, 4), "iou_next": round(iou_next, 4),
            "unsure": bool(iou < 0.6 or iou - iou_next < 0.05)}


def _px_matrix(pxmm: float, h_mm: float) -> np.ndarray:
    return np.array([[pxmm, 0, 0], [0, -pxmm, h_mm * pxmm], [0, 0, 1]], np.float64)


def bottom_warp_matrix(analysis_bot: dict, analysis_top: dict | None, pxmm_out: float = PX_PER_MM) -> np.ndarray:
    """3x3-Pixelabbildung rect.jpg (Unteransicht) -> Draufsicht-Raster: S_top · lage_matrix · S_bot^-1."""
    rb = analysis_bot["rect"]
    al = analysis_bot.get("bottom_align") or {"rot": 0, "dx": 0.0, "dy": 0.0}
    rt = (analysis_top or analysis_bot)["rect"]
    L = lage_matrix(al["rot"], al["dx"], al["dy"], rb["w_mm"], rb["h_mm"])
    return _px_matrix(pxmm_out, rt["h_mm"]) @ L @ np.linalg.inv(_px_matrix(rb["pxmm"], rb["h_mm"]))


def bottom_warp(rect_bot: np.ndarray, analysis_bot: dict, analysis_top: dict | None = None,
                pxmm_out: float = PX_PER_MM) -> np.ndarray:
    rt = (analysis_top or analysis_bot)["rect"]
    M = bottom_warp_matrix(analysis_bot, analysis_top, pxmm_out)
    return cv2.warpAffine(rect_bot, M[:2], (int(rt["w_mm"] * pxmm_out), int(rt["h_mm"] * pxmm_out)),
                          flags=cv2.INTER_LINEAR, borderValue=(235, 236, 236))
```

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py tests/test_edges.py`
Expected: alle PASS (auch `test_synthetische_unteransicht_rot_90`; schlägt er wegen `bottom_of`-Rastergröße fehl, `vision.spec(fmt)["grid_mm"]` verwenden).

- [ ] **Step 5: Commit**

```bash
git add core/vision.py tests/conftest.py tests/test_align.py
git commit -m "Unteransicht: Lage-Matrix, Ausrichtung ueber Umriss-IoU, Pixelabbildung (Spec Stufe A §1)"
```

### Task 2: Fotoart `bottom` im Server, Ausrichtung, `align.jpg`, Handwahl

**Files:**
- Modify: `web/app/main.py` (`VIEWS`, `_photo_public`, `_analyze_store`, `photo_upload`, `PhotoPatch`/`photo_patch`, `photo_delete`, neue Route `align.jpg` vor `photo_file`, `meas_create` `view`, `/suggest` nur `top`)
- Modify: `web/app/parts.py` (`to_top`, `default_unc` für `bottom`)
- Modify: `tests/test_align.py` (API-Tests)

**Interfaces:**
- Consumes: Task 1.
- Produces: `main._reference_top(pid) -> dict | None`; `main._align_photo(ph) -> None` (schreibt `analysis.bottom_align`/`align_note`); `main._realign_project(pid)`; `parts.to_top(photo_row, x, y) -> list[float]`; `parts.reference_top(pid)`; `_photo_public` liefert `bottom_align`, `align_note`; `PhotoPatch.bottom_align: dict | None` (mit `"rot"`), Rücksetzen über `{"bottom_align": {"rot": null}}`.

- [ ] **Step 1: Failing API-Tests** (an `tests/test_align.py` anhängen)

```python
from conftest import H


def _up(c, pid, objects, view):
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("f.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": view}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def pair(user):
    pid = user.post("/api/projects", json={"name": "Lage"}, headers=H).json()["id"]
    top = [{"polygon": L_SHAPE, "gray": 150}]
    t = _up(user, pid, top, "top")
    b = _up(user, pid, bottom_of(top, 90, -30, 22), "bottom")
    return user, pid, t, b


def test_unteransicht_wird_ausgerichtet(pair):
    c, pid, t, b = pair
    assert b["view"] == "bottom" and b["bottom_align"]["rot"] == 90 and not b["bottom_align"]["unsure"]
    assert b["bottom_align"]["auto"] is True and b["bottom_align"]["top_photo_id"] == t["id"]
    r = c.get(f"/api/photos/{b['id']}/align.jpg")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"


def test_handwahl_und_referenzwechsel(pair):
    c, pid, t, b = pair
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=H).json()
    assert r["bottom_align"]["rot"] == 270 and r["bottom_align"]["auto"] is False
    t2 = _up(c, pid, [{"polygon": L_SHAPE, "gray": 150}], "top")   # zweite Draufsicht, Referenz bleibt t
    assert c.delete(f"/api/photos/{t['id']}", headers=H).status_code == 200
    b2 = next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == b["id"])
    assert b2["bottom_align"]["top_photo_id"] == t2["id"] and b2["bottom_align"]["rot"] == 270   # Handwahl bleibt
    assert c.delete(f"/api/photos/{t2['id']}", headers=H).status_code == 200
    b3 = next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == b["id"])
    assert b3["bottom_align"] is None and "Draufsicht fehlt" in b3["align_note"]
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": None}}, headers=H).json()   # zurueck auf automatisch
    assert r["bottom_align"] is None


def test_umschalten_auf_bottom_richtet_aus(user):
    pid = user.post("/api/projects", json={"name": "Umschalten"}, headers=H).json()["id"]
    top = [{"polygon": L_SHAPE, "gray": 150}]
    _up(user, pid, top, "top")
    x = _up(user, pid, bottom_of(top, 180), "tilted")
    assert x["bottom_align"] is None
    r = user.patch(f"/api/photos/{x['id']}", json={"view": "bottom"}, headers=H).json()
    assert r["bottom_align"]["rot"] == 180


def test_messung_von_unten_und_to_top(pair):
    from app import db, parts
    c, pid, t, b = pair
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": b["id"], "kind": "length", "view": "bottom",
                                                          "points": [[10, 20], [30, 20]]}, headers=H).json()
    assert m["data"]["view"] == "bottom" and m["value"] == pytest.approx(20.0)
    ph = db.q1("SELECT * FROM photos WHERE id=?", (b["id"],))
    al = ph and db.jload(ph["analysis"])["bottom_align"]
    M = vision.lage_matrix(al["rot"], al["dx"], al["dy"], 190, 230)
    assert parts.to_top(ph, 10, 20) == pytest.approx(vision.apply_lage(M, [[10, 20]])[0])
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py -k "ausgerichtet or handwahl or umschalten or to_top"`
Expected: FAIL (`view` wird zu `top`, `bottom_align` fehlt / KeyError).

- [ ] **Step 3: Implementierung**

`web/app/parts.py` – neben `default_unc`:

```python
def reference_top(project_id):
    """Referenz-Draufsicht: view='top', rect vorhanden, status gut/brauchbar, kleinste id (Spec §1)."""
    for ph in db.q("SELECT * FROM photos WHERE project_id=? AND view='top' AND status IN ('gut','brauchbar') ORDER BY id",
                   (project_id,)):
        if (db.jload(ph["analysis"], {}) or {}).get("rect"):
            return ph
    return None


def to_top(photo, x, y):
    """Punkt einer Unteransicht (mm) in Draufsicht-Koordinaten; ohne Ausrichtung nur die Spiegelung (rot=0)."""
    from core import vision
    a = db.jload(photo["analysis"], {}) or {}
    r = a["rect"]
    al = a.get("bottom_align") or {"rot": 0, "dx": 0.0, "dy": 0.0}
    return vision.apply_lage(vision.lage_matrix(al["rot"], al["dx"], al["dy"], r["w_mm"], r["h_mm"]), [[x, y]])[0]
```

In `default_unc`: `view == "gauge"` bleibt, alles andere (auch `bottom`) wie `top` – prüfen, dass der Code das schon tut (Zeile 361 ff.); sonst `if view in ("top", "bottom")`.

`web/app/main.py`:

```python
VIEWS = ("top", "bottom", "tilted", "gauge", "overview")
```

`_photo_public`: in der `analysis`-Whitelist `"contrast"` ergänzen (W3) und nach `"gauge_rect"`:

```python
            "bottom_align": a.get("bottom_align") if ph["view"] == "bottom" else None,
            "align_note": a.get("align_note") if ph["view"] == "bottom" else None,
```

`_analyze_store` – nach dem `rect`-Block den Umriss ablegen (Hinweise kommen in Task 10, hier `hints=None`):

```python
        try:
            res = edges.detect(rect, a["format"])
            a["outline_mm"] = res["outlines"][0]["polygon"] if res["outlines"] else None
            a["contrast"] = res.get("contrast")
        except Exception:  # noqa: BLE001 – Umriss ist optional
            a["outline_mm"] = None
    for n in ("rect_top.jpg", "small.jpg"):
        (d / n).unlink(missing_ok=True)
```

(`for n in ("rect.jpg", "gauge.jpg")` am Anfang um `"rect_top.jpg", "small.jpg"` erweitern statt des zweiten Blocks.)

Ausrichtung (neu, vor `photo_upload`):

```python
def _set_analysis(phid: int, a: dict):
    db.ex("UPDATE photos SET analysis=? WHERE id=?", (db.jdump(a), phid))


def _outline_of(ph: dict):
    a = db.jload(ph["analysis"], {}) or {}
    if "outline_mm" in a:
        return a["outline_mm"]
    rect_path = _photo_dir(ph["id"]) / "rect.jpg"
    if not a.get("rect") or not rect_path.is_file() or not _detect_lock.acquire(timeout=30):
        return "timeout" if a.get("rect") else None
    try:
        res = edges.detect(cv2.imread(str(rect_path)), ph["format"])
    finally:
        _detect_lock.release()
    a["outline_mm"] = res["outlines"][0]["polygon"] if res["outlines"] else None
    _set_analysis(ph["id"], a)
    return a["outline_mm"]


def _align_photo(ph: dict, top: dict | None):
    """bottom_align einer Unteransicht neu berechnen (Spec §1 „Wann“). Handwahl (bottom_rot_user) bleibt."""
    a = db.jload(ph["analysis"], {}) or {}
    user_rot = a.get("bottom_rot_user")
    a.pop("bottom_align", None)
    a.pop("align_note", None)
    if ph["view"] != "bottom" or not a.get("rect"):
        _set_analysis(ph["id"], a)
        return
    if top is None:
        a["align_note"] = "Draufsicht fehlt"
    else:
        ot, ob = _outline_of(top), _outline_of(ph)
        if ot == "timeout" or ob == "timeout":
            a["align_note"] = "Ausrichtung nicht berechnet – erneut versuchen"
        elif not ot or not ob:
            a["align_note"] = "Umriss nicht erkennbar"   # bottom_align bleibt null; to_top nutzt dann rot=0 ohne Versatz
        else:
            r = a["rect"]
            al = vision.align_bottom(ot, ob, r["w_mm"], r["h_mm"], rot=user_rot)
            if user_rot is not None:
                al["unsure"] = False
            a["bottom_align"] = {**al, "auto": user_rot is None, "top_photo_id": top["id"]}
    _set_analysis(ph["id"], a)


def _realign_project(pid: int):
    top = parts.reference_top(pid)
    for ph in db.q("SELECT * FROM photos WHERE project_id=? AND view='bottom'", (pid,)):
        _align_photo(ph, top)
```

Auslöser:
- `photo_upload`: nach dem `UPDATE photos … analysis` → `if view == "bottom": _align_photo(db.q1(...), parts.reference_top(pid))` und `if view == "top": _realign_project(pid)`.
- `photo_patch`: nach `UPDATE photos SET view` → wenn `body.view` oder `ph["view"]` in (`top`, `bottom`): `_realign_project(p["id"])` (deckt Umschalten auf/von `bottom` und `top` ab; eine Unteransicht, die zu etwas anderem wird, verliert `bottom_align` in `_align_photo`). Beim Formatwechsel: vor `_analyze_store` `user_rot = (db.jload(ph["analysis"], {}) or {}).get("bottom_rot_user")`, nach der Analyse `a["bottom_rot_user"] = user_rot` setzen, dann `_realign_project(p["id"])`. Neu in `PhotoPatch`: `bottom_align: dict | None = None`; Verarbeitung:

```python
    if body.bottom_align is not None:
        if ph["view"] != "bottom":
            raise HTTPException(400, "Nur für Fotos der Ansicht „Von unten“")
        rot = body.bottom_align.get("rot")
        if rot is not None and rot not in vision.LAGEN:
            raise HTTPException(400, "Lage muss 0, 90, 180 oder 270 sein")
        a = db.jload(ph["analysis"], {}) or {}
        a["bottom_rot_user"] = rot
        _set_analysis(phid, a)
        _align_photo(db.q1("SELECT * FROM photos WHERE id=?", (phid,)), parts.reference_top(p["id"]))
```

- `photo_delete`: nach dem Löschen `_realign_project(p["id"])`.

Route `align.jpg` **vor** `photo_file`:

```python
@app.get("/api/photos/{phid}/align.jpg")
def photo_align_jpg(phid: int, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u)
    a = db.jload(ph["analysis"], {}) or {}
    top = parts.reference_top(p["id"])
    if ph["view"] != "bottom" or not a.get("rect") or not top:
        raise HTTPException(404, "Keine Ausrichtung vorhanden")
    at = db.jload(top["analysis"], {}) or {}
    img = vision.bottom_warp(cv2.imread(str(_photo_dir(phid) / "rect.jpg")), a, at, 4.0)
    H = at["rect"]["h_mm"]
    for poly, col in ((at.get("outline_mm"), (12, 65, 194)), ([parts.to_top(ph, *q) for q in a.get("outline_mm") or []], (178, 60, 20))):
        if poly:
            pts = np.array([[int(x * 4), int((H - y) * 4)] for x, y in poly], np.int32)
            cv2.polylines(img, [pts], True, col, 2, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
```

(Farben BGR: Draufsicht-Umriss Orange `(12, 65, 194)`, eigener Umriss Blau `(178, 60, 20)`; `numpy as np` in main.py importieren, falls nicht vorhanden.)

`meas_create`: `data = {"view": body.view if body.view in ("top", "gauge", "bottom") else "top", …}`.

`/suggest`: in der Schleife `if used_photo is None and ph["view"] == "top" and (d / "rect.jpg").is_file():`.

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py tests/test_api.py tests/test_edges_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/main.py web/app/parts.py tests/test_align.py
git commit -m "Fotoart „Von unten“: Ausrichtung zur Referenz-Draufsicht, Handwahl, align.jpg, Messungen mit view=bottom"
```

### Task 3: Teile und Maßtabelle mit Unteransicht (`same_as`, „(unten)“)

**Files:**
- Modify: `web/app/parts.py` (`_sync_auto`, `refresh`, `link_bottom`, `part_public`, `cad_text` Teil „von unten“)
- Modify: `web/app/jobs.py` (`measurement_table`)
- Modify: `web/app/main.py` (`_csv`)
- Create: `tests/test_check.py` (Teil „tabelle“)

**Interfaces:**
- Consumes: `parts.to_top`, `parts.reference_top`, `match_parts` (Task 2).
- Produces: `parts.link_bottom(project_id)` (setzt `data.same_as`); `part_public()["same_as"]`, `part_public()["view"]`; `jobs.measurement_table(project_id, part_id)` berücksichtigt `same_as` und zeigt `(unten)`; `jobs.point_text(m, d, photos) -> str`.

- [ ] **Step 1: Failing test** `tests/test_check.py`:

```python
"""Pruefung vor dem Auftrag, Auftragsnachricht, Tabelle (Spec 2026-10-15 §2, A3–A5, A9)."""
import pytest

from conftest import H, bottom_of, synthetic_photo

L_SHAPE = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 120], [60, 120]]


def _up(c, pid, objects, view):
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("f.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": view}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def proj(user):
    pid = user.post("/api/projects", json={"name": "Stufe A"}, headers=H).json()["id"]
    top = [{"polygon": L_SHAPE, "gray": 150}]
    t = _up(user, pid, top, "top")
    b = _up(user, pid, bottom_of(top, 90, -30, 22), "bottom")
    return user, pid, t, b


def test_tabelle_unten_in_draufsicht_koordinaten(proj):
    from app import jobs
    c, pid, t, b = proj
    pt = c.post(f"/api/projects/{pid}/parts", json={"photo_id": t["id"], "label": "L", "polygon": L_SHAPE}, headers=H).json()
    poly_b = bottom_of([{"polygon": L_SHAPE, "gray": 150}], 90, -30, 22)[0]["polygon"]
    pb = c.post(f"/api/projects/{pid}/parts", json={"photo_id": b["id"], "label": "L unten", "polygon": poly_b}, headers=H).json()
    p = c.get(f"/api/projects/{pid}").json()
    pb = next(x for x in p["parts"] if x["id"] == pb["id"])
    assert pb["same_as"] == pt["id"] and pb["view"] == "bottom"
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": b["id"], "kind": "length", "view": "bottom",
                                                          "points": [[10, 20], [30, 20]]}, headers=H).json()
    text, rows = jobs.measurement_table(pid)
    line = next(l for l in text.splitlines() if l.startswith(f"| M{m['seq']} "))
    assert "(unten)" in line and "(190.0, 200.0)" not in line   # mit Versatz: (160, 205) ± Rundung
    assert "(160.0, 205.0)" in line or "(160.0, 205.1)" in line or "(159.9, 205.0)" in line
    text1, rows1 = jobs.measurement_table(pid, pt["id"])
    assert any(r["part_id"] == pb["id"] for r in rows1)          # Einzelteil-Auftrag nimmt das Unteransicht-Teil mit
    assert all(("(unten)" in l) for l in text1.splitlines() if "Kante" in l and f"T{pb['seq']}" in l)
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py -k tabelle`
Expected: FAIL (`KeyError: 'same_as'`).

- [ ] **Step 3: Implementierung**

`parts.py`:

```python
def link_bottom(project_id):
    """Unteransicht-Teile mit dem ueberlagerten Teil der Referenz-Draufsicht verknuepfen (Spec §1, same_as)."""
    top = reference_top(project_id)
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}
    rows = db.q("SELECT * FROM parts WHERE project_id=?", (project_id,))
    tops = [(r["id"], _data(r)["polygon"]) for r in rows if top and r["photo_id"] == top["id"]]
    for r in rows:
        ph = photos.get(r["photo_id"])
        if not ph or ph["view"] != "bottom":
            continue
        d = _data(r)
        same = None
        if tops and (db.jload(ph["analysis"], {}) or {}).get("bottom_align"):
            poly = [to_top(ph, x, y) for x, y in d["polygon"]]
            m = match_parts(tops, [(r["id"], poly)])
            same = m.get(r["id"])
        if d.get("same_as") != same:
            d["same_as"] = same
            db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), r["id"]))
```

- `_sync_auto(part, photo, fx, fy)`: `view = photo["view"] if photo and photo["view"] == "bottom" else "top"`; im Insert `md = {"view": view, …}` und `default_unc(photo, view)`; bei bestehenden Auto-Maßen `md.update(view=view, …)`.
- `refresh`: die drei Prüfungen `d.get("view", "top") == "top"` → `d.get("view", "top") in ("top", "bottom")`; am Ende `link_bottom(pid)`.
- `part_public`: `"same_as": d.get("same_as")`, `"view": (db.q1("SELECT view FROM photos WHERE id=?", (part["photo_id"],)) or {}).get("view", "top")`.
- `cad_text` ohne `part_id` (neues Format, Spec §2.2) und mit `part_id` ergänzen:

```python
def _poly_text(part, photo):
    d = _data(part)
    pts = d["polygon"]
    if photo and photo["view"] == "bottom":
        pts = [to_top(photo, x, y) for x, y in pts]
    s = "Umriss (mm) " + " ".join(f"({x:.1f}, {y:.1f})" for x, y in pts)
    if d.get("hidden"):
        s += "; verdeckte Kanten: " + ", ".join(f"K{e}" for e in d["hidden"])
    if d.get("holes"):
        hs = []
        for h in d["holes"]:
            c = to_top(photo, *h["c"]) if photo and photo["view"] == "bottom" else h["c"]
            hs.append(f"Ø {h['d']:.1f} bei ({c[0]:.1f}, {c[1]:.1f})")
        s += "; Bohrungen: " + ", ".join(hs)
    return s


def cad_text(project_id, part_id=None):
    rows = db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (project_id,))
    if not rows:
        return ""
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}
    seq = {r["id"]: r["seq"] for r in rows}

    def where(r):
        ph = photos.get(r["photo_id"])
        if ph and ph["view"] == "bottom":
            same = _data(r).get("same_as")
            return ("von unten, in Draufsicht-Koordinaten; derselbe Körper wie T%d, kein zusätzliches Teil" % seq[same]
                    if same in seq else "von unten, in Draufsicht-Koordinaten")
        return "Draufsicht"
    if part_id:
        t = next((r for r in rows if r["id"] == part_id), None)
        if not t:
            return ""
        lines = [f"Modelliert wird nur Teil T{t['seq']} „{t['label']}“ ({ROLE_TEXT[t['role']]}, {where(t)}): {_poly_text(t, photos.get(t['photo_id']))}."]
        for r in rows:
            if _data(r).get("same_as") == part_id:
                lines.append(f"Dazu T{r['seq']} „{r['label']}“ ({where(r)}): {_poly_text(r, photos.get(r['photo_id']))}.")
        return " ".join(lines) + " Maße anderer Teile sind nicht enthalten."
    lines = [f"T{r['seq']} „{r['label']}“ ({ROLE_TEXT[r['role']]}, {where(r)}): {_poly_text(r, photos.get(r['photo_id']))}" for r in rows]
    return "Teile im Foto (Umrisse verbindlich): " + "; ".join(lines) + ". Alle Teile als ein Körper modellieren."
```

Bestehenden Test `tests/test_edges_api.py::test_cad_auftrag_fuer_ein_teil` anpassen: `assert "Teile im Foto (Umrisse verbindlich): T1 „Quader“ (Grundkörper, Draufsicht)" in alle` und `"Modelliert wird nur Teil T2 „Platte“ (montiertes Teil, Draufsicht)"`.

`jobs.py`:

```python
def point_text(m: dict, d: dict, photos: dict) -> str:
    pts = d.get("points") or []
    if not pts:
        return d.get("view", "")
    if d.get("view") == "bottom" and m["photo_id"] in photos:
        ph = photos[m["photo_id"]]
        a = db.jload(ph["analysis"], {}) or {}
        tag = "(unten)" if a.get("bottom_align") else "(unten, nicht ausgerichtet, links-rechts gespiegelt)"
        pts = [to_top(ph, x, y) for x, y in pts]
        return "bottom " + tag + " " + " ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in pts[:3])
    return d.get("view", "") + " " + " ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in pts[:3])
```

(`from .parts import cad_text, to_top`.) In `measurement_table`: `photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}`; Filter mit `part_id`: `linked = {r["id"] for r in db.q("SELECT id, data FROM parts WHERE project_id=?", (project_id,)) if (db.jload(r["data"], {}) or {}).get("same_as") == part_id}`; `rows = [m for m in rows if m["part_id"] in (part_id, None) or m["part_id"] in linked]`; `where = point_text(m, d, photos)`. In `_csv` (main.py) dieselbe Umrechnung über `jobs.point_text` für die Spalte „Punkte (mm)“.

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_edges_api.py tests/test_parts_api.py tests/test_align.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/parts.py web/app/jobs.py web/app/main.py tests/test_check.py tests/test_edges_api.py
git commit -m "Teile von unten: same_as-Verknuepfung, Auto-Masse mit view=bottom, Tabelle und CAD-Text in Draufsicht-Koordinaten"
```

### Task 4: Oberfläche Welle 1 (Fotos prüfen, Messen)

**Files:**
- Modify: `web/static/js/photos.js` (`VIEW_LABEL.bottom`, Ansichtswahl beim Hochladen, Detail mit `align.jpg` und vier Lagen)
- Modify: `web/static/js/measure.js` (Quellen für `bottom`, `photoId()`, Seitenleiste „unten“/„= T1“)
- Modify: `web/static/js/edges.js` (`partsPanel`: Zusatz „unten“ und „= T1“)
- Modify: `web/static/js/cad.js` („Modell für“: Teile von unten mit Zusatz)

**Interfaces:**
- Consumes: `photo.bottom_align`, `photo.align_note`, `part.same_as`, `part.view` (Tasks 2–3).

- [ ] **Step 1: photos.js**

`VIEW_LABEL = { top: "Draufsicht", bottom: "Von unten", tilted: "Gekippt (Höhe)", gauge: "Höhenlehre", overview: "Übersicht" }`.

Ansichtswahl beim Hochladen: neben `fmtSel` ein `viewSel = h("select", { class: "input", "aria-label": "Ansicht der nächsten Fotos" }, Object.entries(VIEW_LABEL).map(([k, v]) => h("option", { value: k }, v)))`, im Kopf als Feld „Ansicht“; in `send()`: `form.append("view", viewSel.value)`.

Detail einer Unteransicht (`drawDetail`, nach den `note`-Blöcken):

```js
const LAGEN = [[0, "seitlich umgedreht"], [180, "nach vorn umgedreht"], [90, "seitlich umgedreht, ¼ gegen den Uhrzeigersinn gedreht"], [270, "seitlich umgedreht, ¼ im Uhrzeigersinn gedreht"]];
function alignBox(p) {
  const al = p.bottom_align;
  const setRot = async rot => { try { await api(`/api/photos/${p.id}`, { method: "PATCH", body: { bottom_align: { rot } } }); await reloadProject(); drawDetail(); } catch (e) { fail(e); } };
  return h("section", { class: "card", style: { gap: "10px" } }, h("h3", {}, "Lage zur Draufsicht"),
    al ? [h("figure", {}, h("img", { src: `/api/photos/${p.id}/align.jpg?v=${al.rot}-${al.dx}`, alt: "Überlagerung Unteransicht auf Draufsicht" }),
        h("figcaption", {}, `Überlappung ${num(al.iou * 100, 0)} % · ${al.auto ? "automatisch" : "von Hand"}`)),
      al.unsure ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, "Ausrichtung unsicher – bitte prüfen und Lage wählen.")) : null,
      h("div", { class: "seg", role: "group", "aria-label": "Lage" }, LAGEN.map(([r, t]) => h("button", { "aria-pressed": String(al.rot === r), onclick: () => setRot(r) }, t))),
      al.auto ? null : h("button", { class: "btn sm ghost", onclick: () => setRot(null) }, "Wieder automatisch")]
      : h("p", { class: "hint" }, p.align_note || "Draufsicht fehlt"));
}
```

Einfügen: `p.view === "bottom" ? alignBox(p) : null` vor `h("div", { class: \`duo …\` }, figs)`.

- [ ] **Step 2: measure.js und edges.js**

`buildSources`: `view: p.view === "bottom" ? "bottom" : "top"` für die `rect`-Quelle; `shown()` filtert schon nach `data.view === src.view`. `photoId: () => (src && src.view !== "gauge" ? src.photo.id : null)`; in `detectEdges` Prüfung `src.view !== "gauge"` statt `!== "top"`; im POST der Messung geht `view: src.view` bereits mit. `partsPanel` in edges.js: nach `ROLE[p.role]` den Zusatz `p.view === "bottom" ? " · unten" + (p.same_as ? ` = T${(S.project.parts.find(q => q.id === p.same_as) || {}).seq ?? "?"}` : "") : ""`. `cad.js` Auswahl „Modell für“: `\`${t.id_label} · ${t.label}${t.view === "bottom" ? " (unten)" : ""}\``.

- [ ] **Step 3: Prüfen**

Run: `for f in web/static/js/*.js; do node --check "$f"; done && node --test tests/js/*.test.mjs && python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: keine Fehler.

Browser-Probe (Scratchpad, Playwright wie in `pw/nach.mjs`): Draufsicht und Unteransicht (synthetisch aus `bottom_of`, als JPG gespeichert) hochladen, Detail der Unteransicht zeigt das Bild und vier Schaltflächen, Klick auf „¼ im Uhrzeigersinn“ ändert `rot` auf 270, „Wieder automatisch“ zurück auf 90.

- [ ] **Step 4: Commit und Wellenabschluss**

```bash
git add web/static/js/photos.js web/static/js/measure.js web/static/js/edges.js web/static/js/cad.js
git commit -m "Oberflaeche: Ansicht beim Hochladen, Lage der Unteransicht mit Ueberlagerung, Teile von unten"
source /root/Snap2CAD-venv/bin/activate && ruff check . && python -m pytest -q -p no:cacheprovider
```

---

## Welle 2 – Prüfung vor dem Auftrag, Werkstück, Auftragsnachricht

### Task 5: Werkstück-Spalten, Migration, `PATCH /api/projects`

**Files:**
- Modify: `web/app/db.py` (`SCHEMA` projects, `_migrate`)
- Modify: `web/app/main.py` (`ProjectPatch`, `project_patch`)
- Modify: `tests/test_parts_api.py` (`test_migration_werkstueck`), `tests/test_check.py`

**Interfaces:**
- Produces: Spalten `projects.color, material, transparent, finish, material_user, cad_check`; `ProjectPatch.color/material/transparent/finish/clear_material`; Konstante `main.FINISHES = ("matt", "glaenzend")`; `main.LIGHT_COLORS`.

- [ ] **Step 1: Failing tests**

`tests/test_parts_api.py`:

```python
OLD_PROJECTS = """CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0, ctrl_x REAL, ctrl_y REAL);"""


def test_migration_werkstueck(tmp_path, monkeypatch):
    from app import config, db
    path = tmp_path / "alt2.db"
    con = sqlite3.connect(path)
    con.executescript(OLD_PROJECTS + OLD_MEAS)
    con.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db, "_conn", None)
    try:
        cols = {r["name"] for r in db.q("PRAGMA table_info(projects)")}
        assert {"color", "material", "transparent", "finish", "material_user", "cad_check"} <= cols
        db._migrate(db.conn())  # zweiter Start aendert nichts
        assert {r["name"] for r in db.q("PRAGMA table_info(projects)")} == cols
    finally:
        db._conn.close()
```

`tests/test_check.py`:

```python
def test_werkstueck_felder(proj):
    c, pid, t, b = proj
    p = c.get(f"/api/projects/{pid}").json()
    assert p["material_user"] == 0 and p["transparent"] is None
    r = c.patch(f"/api/projects/{pid}", json={"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt"}, headers=H).json()
    assert (r["color"], r["material"], r["transparent"], r["finish"], r["material_user"]) == ("silber", "Aluminium", 1, "matt", 1)
    assert c.patch(f"/api/projects/{pid}", json={"transparent": 5}, headers=H).status_code == 422
    assert c.patch(f"/api/projects/{pid}", json={"finish": "rau"}, headers=H).status_code == 400
    r = c.patch(f"/api/projects/{pid}", json={"clear_material": True}, headers=H).json()
    assert r["material"] is None and r["material_user"] == 0
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_parts_api.py -k migration_werkstueck tests/test_check.py -k werkstueck`
Expected: FAIL (Spalten fehlen, `material_user` KeyError).

- [ ] **Step 3: Implementierung**

`db.py` SCHEMA `projects`: `ctrl_x REAL, ctrl_y REAL, color TEXT, material TEXT, transparent INTEGER, finish TEXT, material_user INTEGER NOT NULL DEFAULT 0, cad_check TEXT`. `_migrate`:

```python
    pcols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    for col, typ in (("color", "TEXT"), ("material", "TEXT"), ("transparent", "INTEGER"), ("finish", "TEXT"),
                     ("material_user", "INTEGER NOT NULL DEFAULT 0"), ("cad_check", "TEXT")):
        if col not in pcols:
            c.execute(f"ALTER TABLE projects ADD COLUMN {col} {typ}")
```

`main.py`:

```python
FINISHES = ("matt", "glaenzend")
LIGHT_COLORS = {"weiß", "weiss", "silber", "hellgrau", "beige", "natur"}


class ProjectPatch(BaseModel):
    ...
    color: str | None = Field(default=None, max_length=40)
    material: str | None = Field(default=None, max_length=40)
    transparent: int | None = Field(default=None, ge=0, le=2)
    finish: str | None = Field(default=None, max_length=20)
    clear_material: bool = False
```

In `project_patch` (in `atomic`): `if body.finish is not None and body.finish not in FINISHES: raise HTTPException(400, "Oberfläche: matt oder glaenzend")`; `if body.clear_material: db.ex("UPDATE projects SET color=NULL, material=NULL, transparent=NULL, finish=NULL, material_user=0 WHERE id=?", (pid,))`; für jedes gesetzte Feld `UPDATE projects SET <k>=?, material_user=1`. `_project_public` liefert die Spalten über `dict(p)` automatisch; `cad_check` wird in Task 8 aufbereitet (bis dahin roher Text oder `None`).

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_parts_api.py tests/test_check.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/db.py web/app/main.py tests/test_parts_api.py tests/test_check.py
git commit -m "Werkstueck-Felder am Projekt (Farbe, Material, Transparenz, Oberflaeche) mit Migration"
```

### Task 6: KI-Schicht: `CHECK_SYSTEM`, `parse_check`, Temperatur, Regeln 8 und 9

**Files:**
- Modify: `web/app/ai.py`
- Modify: `web/app/jobs.py` (`ai.call(…, temperature=0.0)` in `_run`)
- Modify: `tests/test_check.py`

**Interfaces:**
- Produces: `ai.CHECK_SYSTEM`; `ai.parse_check(text) -> dict` (`items`, `material`); `ai.call(..., temperature: float | None = None)`; `_fake` antwortet auf `CHECK_SYSTEM`.

- [ ] **Step 1: Failing tests** (`tests/test_check.py`)

```python
def test_parse_check_defensiv():
    from app import ai
    r = ai.parse_check('Hier: {"items": [{"kind": "hoehe", "text": "x" * 300}, {"kind": "bottom", "severity": "block", "text": 5},'
                       ' {"kind": "height", "severity": "block", "text": "Höhe fehlt"}], "material": {"color": "silber", "transparent": 7, "finish": "rau", "note": ["x"]}}')
    assert r["items"] == [{"kind": "other", "severity": "warn", "text": "x" * 200}, {"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    assert r["material"] == {"color": "silber", "material": None, "transparent": None, "finish": None, "note": ""}
    assert ai.parse_check("[]")["items"] == [] and ai.parse_check("kein json")["material"] is None


def test_prompt_regeln():
    from app import ai
    assert "ist verbindlich" in ai.CAD_SYSTEM and "Innenbohrungen" in ai.CAD_SYSTEM and "so einfach wie möglich" not in ai.CAD_SYSTEM
    assert "Fotografiertes Original" in ai.CAD_SYSTEM and "Offene Punkte" in ai.CAD_SYSTEM


def test_temperatur_wird_uebergeben(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from app import ai, config, settings
    seen = []

    class Stream:
        text_stream = iter(["ok"])

        def get_final_message(self):
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="m", stop_reason="end_turn")

    @contextmanager
    def stream(**kw):
        seen.append(kw)
        yield Stream()
    monkeypatch.setattr(config, "AI_FAKE", False)
    monkeypatch.setattr(settings, "api_key", lambda: "k")
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    ai.call("s", [{"role": "user", "content": "x"}], temperature=0.0)
    ai.call("s", [{"role": "user", "content": "x"}])
    assert seen[0]["temperature"] == 0.0 and "temperature" not in seen[1]
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py -k "parse_check or prompt_regeln or temperatur"`
Expected: FAIL.

- [ ] **Step 3: Implementierung in `ai.py`**

`CAD_SYSTEM` – Eingaben ergänzen: „- Ggf. eine Unteransicht (entzerrt, gespiegelt auf Draufsicht-Koordinaten: Bohrungen von unten und oben liegen übereinander) und Schrägansichten ohne Maßstab (nur für Form, Seitenflächen und Höhenverhältnis).“ „- Eine Zeile „Fotografiertes Original“ (Farbe, Material, Transparenz, Oberfläche des Teils, nicht das Fertigungsmaterial) und ggf. „Offene Punkte der Prüfung“.“ Regel 8 ersetzen und Regel 9/10 anfügen:

```
8. Der Umriss aus der Draufsicht (Teile-Polygone) ist verbindlich: Fasen, Stufen, Absätze und Bohrungen daraus
   nachbilden. Fehlt ein Maß (z. B. die Höhe einer Stufe), schätze es, kennzeichne es als Annahme und nenne es
   in `check_before_manufacturing`. Weglassen ist nur erlaubt, was kleiner als 0,5 mm ist. Laufzeit unter 60 Sekunden.
9. Bei transparenten oder teiltransparenten Teilen sind durchscheinende Strukturen Innenbohrungen oder
   Innenkonturen, keine Rillen oder Nuten der Oberfläche. Bohrungen von unten und oben an derselben Stelle sind
   in der Regel ein Loch (ggf. Stufenloch).
10. Zu jedem offenen Punkt der Prüfung steht in `assumptions`, was angenommen wurde.
```

```python
CHECK_SYSTEM = """Du prüfst vor dem CAD-Modellieren, ob die Unterlagen reichen. Du bekommst dieselben Fotos und Maße
wie der Konstrukteur: entzerrte Draufsicht (Maßstab steht dabei), ggf. Unteransicht (gespiegelt auf
Draufsicht-Koordinaten), Höhenlehre, Schrägansichten ohne Maßstab, Messtabelle, Teile-Umrisse.

Nenne, was zum vollständigen Nachbilden fehlt oder unsicher ist, je Punkt mit Art und Stufe:
kind: height (Höhe/Dicke unbekannt), bottom (Unterseite fehlt oder unklar), photo (weiteres Foto nötig, z. B. Seite),
measure (ein Maß fehlt oder widerspricht), sharpness (Kante unscharf, verdeckt oder im Schatten), other.
severity: block = ohne diese Angabe wird das Modell geraten; warn = die Genauigkeit leidet.
Jeder Text sagt, was der Nutzer tun soll (z. B. „Höhenlehre fotografieren oder Höhe als Maß eingeben“). Höchstens 8 Punkte,
keine Punkte zu Dingen, die schon in der Messtabelle stehen.

Schätze außerdem das fotografierte Teil: color (ein Wort, z. B. silber, schwarz, weiß), material (z. B. Aluminium,
Stahl, Kunststoff, Holz, Glas), transparent (0 nein, 1 teilweise, 2 ja), finish (matt oder glaenzend), note (ein Satz).

Antworte ausschließlich mit einem JSON-Objekt:
{"items": [{"kind": "height", "severity": "block", "text": "…"}],
 "material": {"color": "…", "material": "…", "transparent": 0, "finish": "matt", "note": "…"}}"""

CHECK_KINDS = ("height", "bottom", "photo", "measure", "sharpness", "other")
FINISHES = ("matt", "glaenzend")


def _json_object(text: str) -> dict | None:
    t = text.strip()
    m = _BLOCK.search(t)
    if m:
        t = m.group(2)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        return None
    try:
        o = json.loads(t[i:j + 1])
    except ValueError:
        return None
    return o if isinstance(o, dict) else None


def parse_check(text: str) -> dict:
    """Pruefergebnis defensiv lesen (Spec §2.1): unbekannte Art -> other, fehlende Stufe -> warn."""
    o = _json_object(text) or {}
    items = []
    for it in o.get("items") if isinstance(o.get("items"), list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("text"), str) or not it["text"].strip():
            continue
        items.append({"kind": it.get("kind") if it.get("kind") in CHECK_KINDS else "other",
                      "severity": it.get("severity") if it.get("severity") in ("block", "warn") else "warn",
                      "text": it["text"].strip()[:200]})
        if len(items) == 8:
            break
    mat = o.get("material")
    material = None
    if isinstance(mat, dict):
        tr = mat.get("transparent")
        material = {"color": _text(mat.get("color"), 40) or None, "material": _text(mat.get("material"), 40) or None,
                    "transparent": tr if tr in (0, 1, 2) else None,
                    "finish": mat.get("finish") if mat.get("finish") in FINISHES else None, "note": _text(mat.get("note"), 300)}
    return {"items": items, "material": material}
```

`call`: Signatur `…, on_progress=None, temperature: float | None = None`; `extra = {} if temperature is None else {"temperature": temperature}`; `client().messages.stream(model=…, max_tokens=…, system=…, messages=…, **extra)`. `_fake`: neuer Zweig

```python
    if system == CHECK_SYSTEM:
        return json.dumps({"items": [
            {"kind": "height", "severity": "block", "text": "Höhe des Grundkörpers unbekannt – Höhenlehre fotografieren oder Höhe als Maß eingeben."},
            {"kind": "bottom", "severity": "warn", "text": "Unterseite fehlt – Teil umdrehen und als „Von unten“ hochladen."}],
            "material": {"color": "silber", "material": "Aluminium", "transparent": 0, "finish": "matt", "note": "Testmodus"}},
            ensure_ascii=False), usage
```

`jobs._run`: `ai.call(ai.CAD_SYSTEM, msgs, cancel=ev, on_progress=lambda n: None, temperature=0.0)`.

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_texts.py tests/test_api.py -k "check or prompt or temperatur or claude or job"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/ai.py web/app/jobs.py tests/test_check.py
git commit -m "KI: Pruef-Prompt und parse_check, Temperatur 0 fuer CAD-Auftraege, verbindlicher Umriss als Regel"
```

### Task 7: Bildauswahl, `rect_top.jpg`, `small.jpg`, Auftragsnachricht mit Werkstück und Prüfpunkten

**Files:**
- Modify: `web/app/jobs.py` (`pick_images`, `build_initial_message`, `material_line`)
- Modify: `web/app/main.py` (`CheckItem`, `JobIn.check_items`, Übergabe in `jobs.create`-Optionen)
- Modify: `tests/test_check.py`, `tests/test_edges_api.py`

**Interfaces:**
- Produces: `jobs.pick_images(project_id, photo_ids) -> list[dict]` mit `{photo_id, kind: "top"|"bottom"|"gauge"|"tilted", path: Path, caption: str}`; `jobs.material_line(project) -> str`; `build_initial_message(project, text, options)` versteht `options["for_check"]`, `options["check_items"]`; `main.CheckItem`.

- [ ] **Step 1: Failing tests** (`tests/test_check.py`)

```python
def test_nachricht_bilder_und_text(proj):
    from app import db, jobs
    c, pid, t, b = proj
    g = _up(c, pid, [{"polygon": L_SHAPE, "gray": 150}], "tilted")
    for _ in range(5):
        _up(c, pid, [{"polygon": L_SHAPE, "gray": 150}], "top")
    c.patch(f"/api/projects/{pid}", json={"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt"}, headers=H)
    imgs = jobs.pick_images(pid, None)
    assert [i["kind"] for i in imgs] == ["top"] * 5 + ["bottom"] and len(imgs) == 6          # 6 Draufsichten + 1 unten + 1 gekippt -> 6
    imgs = jobs.pick_images(pid, [t["id"], b["id"], g["id"]])
    assert [i["kind"] for i in imgs] == ["top", "bottom", "tilted"]
    assert imgs[1]["path"].name == "rect_top.jpg" and "gespiegelt auf Draufsicht-Koordinaten" in imgs[1]["caption"]
    assert imgs[2]["path"].name == "small.jpg" and "Schrägansicht" in imgs[2]["caption"] and imgs[2]["path"].is_file()
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    msg = jobs.build_initial_message(project, "Nachbauen", {"photo_ids": [t["id"], b["id"], g["id"]], "name": "x",
                                                            "check_items": [{"kind": "height", "severity": "block", "text": "Höhe fehlt"}]})
    text = msg[0]["content"][0]["text"]
    assert "Fotografiertes Original (nicht das Fertigungsmaterial): silber, Aluminium, transparent: teilweise, matt" in text
    assert "## Offene Punkte der Prüfung\n- [block] Höhe fehlt" in text
    chk = jobs.build_initial_message(project, "", {"photo_ids": None, "part_id": None, "for_check": True, "process": "cnc", "cutter_d": 6})
    assert "Fräser" not in chk[0]["content"][0]["text"] and "Wunsch des Nutzers" not in chk[0]["content"][0]["text"]


def test_auftrag_mit_check_items(proj):
    from app import db
    c, pid, t, b = proj
    r = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "x",
                                  "check_items": [{"kind": "height", "severity": "block", "text": "Höhe fehlt"}]}, headers=H)
    assert r.status_code == 200, r.text
    msgs = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (r.json()["id"],))["messages"])
    assert "- [block] Höhe fehlt" in msgs[0]["content"][0]["text"]
    bad = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "x", "check_items": [{"kind": "x", "severity": "block", "text": "t"}]}, headers=H)
    assert bad.status_code == 422
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py -k "nachricht or check_items"`
Expected: FAIL (`pick_images` fehlt).

- [ ] **Step 3: Implementierung**

`jobs.py`:

```python
TRANSPARENT_TEXT = {0: "nein", 1: "teilweise", 2: "ja"}


def material_line(project: dict) -> str:
    parts_ = [project.get("color"), project.get("material"),
              f"transparent: {TRANSPARENT_TEXT[project['transparent']]}" if project.get("transparent") in TRANSPARENT_TEXT else None,
              project.get("finish")]
    parts_ = [p for p in parts_ if p]
    return f"Fotografiertes Original (nicht das Fertigungsmaterial): {', '.join(parts_)}" if parts_ else ""


def _small(pdir: Path) -> Path:
    out = pdir / "small.jpg"
    if not out.is_file():
        data, _ = ai.prepare_image(pdir / "orig.jpg")
        out.write_bytes(data)
    return out


def _rect_top(ph: dict, top: dict | None) -> Path:
    """Unteransicht in Draufsicht-Koordinaten, bei jedem Aufbau neu (kein veralteter Zwischenspeicher)."""
    pdir = config.DATA_DIR / "photos" / str(ph["id"])
    a = db.jload(ph["analysis"], {}) or {}
    at = db.jload(top["analysis"], {}) if top else None
    img = vision.bottom_warp(cv2.imread(str(pdir / "rect.jpg")), a, at if a.get("bottom_align") else None)
    out = pdir / "rect_top.jpg"
    out.write_bytes(vision.encode_jpg(img, 90))
    return out


def pick_images(project_id: int, photo_ids: list[int] | None) -> list[dict]:
    """Bilder fuer die KI (Spec §2.2): Draufsicht, Unteransicht, Hoehenlehre, Schraegfotos; hoechstens 6."""
    from .parts import reference_top
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (project_id,))
              if photo_ids is None or p["id"] in photo_ids]
    top = reference_top(project_id)
    groups: dict[str, list[dict]] = {"top": [], "bottom": [], "gauge": [], "tilted": []}
    for p in photos:
        pdir = config.DATA_DIR / "photos" / str(p["id"])
        a = db.jload(p["analysis"], {}) or {}
        if p["view"] == "top" and (pdir / "rect.jpg").is_file():
            groups["top"].append({"photo_id": p["id"], "kind": "top", "path": pdir / "rect.jpg",
                                  "caption": ai.scaled_caption(pdir / "rect.jpg", f"Foto {p['id']} (Draufsicht), entzerrt auf die Unterlage", vision.PX_PER_MM)})
        elif p["view"] == "bottom" and (pdir / "rect.jpg").is_file() and a.get("rect"):
            path = _rect_top(p, top)
            tag = ("entzerrt und gespiegelt auf Draufsicht-Koordinaten – Bohrungen von unten und oben liegen übereinander"
                   if a.get("bottom_align") else "entzerrt, nicht ausgerichtet, links-rechts gespiegelt")
            groups["bottom"].append({"photo_id": p["id"], "kind": "bottom", "path": path,
                                     "caption": ai.scaled_caption(path, f"Foto {p['id']} (von unten), {tag}", vision.PX_PER_MM)})
        elif p["view"] in ("tilted", "overview") and (pdir / "orig.jpg").is_file():
            path = _small(pdir)
            groups["tilted"].append({"photo_id": p["id"], "kind": "tilted", "path": path,
                                     "caption": f"Foto {p['id']}, Schrägansicht – nicht entzerrt, kein Maßstab; nur für Form, Seitenflächen und Höhenverhältnis."})
        if (pdir / "gauge.jpg").is_file():
            groups["gauge"].append({"photo_id": p["id"], "kind": "gauge", "path": pdir / "gauge.jpg",
                                    "caption": ai.scaled_caption(pdir / "gauge.jpg", f"Foto {p['id']}, entzerrte Höhenlehre (x −100…100 mm, y ab −10 mm)", vision.PX_PER_MM)})
    out = groups["top"] + groups["bottom"] + groups["gauge"] + groups["tilted"]
    return out[:6]
```

(`import cv2` und `from core import vision` in jobs.py; `config.DATA_DIR` wird schon genutzt.) `build_initial_message`: nach der Kopfzeile `material_line(project)` einfügen (wenn nicht leer); bei `options.get("for_check")` entfallen „Fertigung“, „Wunsch des Nutzers“, Fräser, Aufspannungen, Passungen, Toleranz, Zusatzwünsche; nach „## Wunsch des Nutzers“ (bzw. am Ende) `## Offene Punkte der Prüfung` mit `- [severity] text` je `options.get("check_items") or []`. Bilder: `for im in pick_images(project["id"], photo_ids): content += ai.image_ref(im["path"], im["caption"])` (alte Schleife ersetzen).

`main.py`:

```python
class CheckItem(BaseModel):
    kind: Literal["height", "bottom", "photo", "measure", "sharpness", "other"]
    severity: Literal["block", "warn"]
    text: str = Field(max_length=200)


class JobIn(BaseModel):
    ...
    check_items: list[CheckItem] = Field(default=[], max_length=8)
```

(`from typing import Literal`.) In `job_create` die Optionen um `"check_items": [i.model_dump() for i in body.check_items]` ergänzen.

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_edges_api.py tests/test_api.py`
Expected: PASS (die Anzahl der Bilder in `test_cad_auftrag_fuer_ein_teil` bleibt, weil dort nur Draufsichten liegen).

- [ ] **Step 5: Commit**

```bash
git add web/app/jobs.py web/app/main.py tests/test_check.py
git commit -m "Auftragsnachricht: Bildauswahl nach Ansicht (max. 6), Unteransicht gespiegelt, Schraegfotos im Original, Werkstueck und Pruefpunkte"
```

### Task 8: Endpunkt `POST /api/projects/{pid}/cad-check`, Hash, Idempotenz, Materialübernahme

**Files:**
- Create: `web/app/check.py` (`cad_hash`, `run_check`, `public_check`)
- Modify: `web/app/main.py` (Route, `_ai_uses_today`, `_project_public`)
- Modify: `tests/test_check.py`

**Interfaces:**
- Consumes: `jobs.build_initial_message(for_check)`, `jobs.pick_images`, `ai.CHECK_SYSTEM`, `ai.parse_check`, `ai.call(temperature=0.0)`.
- Produces: `check.cad_hash(project, photo_ids, part_id) -> str`; `check.run_check(project, photo_ids, part_id) -> dict` (KI-Aufruf, speichert `cad_check`, übernimmt Material); `check.public_check(project) -> dict | None` (mit `stale`); `_project_public()["cad_check"]`.

- [ ] **Step 1: Failing tests**

```python
def test_cad_check_testmodus(proj, monkeypatch):
    from app import ai
    c, pid, t, b = proj
    calls = []
    orig = ai.call
    monkeypatch.setattr(ai, "call", lambda *a, **k: (calls.append(k), orig(*a, **k))[1])
    r = c.post(f"/api/projects/{pid}/cad-check", json={"photo_ids": None, "part_id": None}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [(i["kind"], i["severity"]) for i in j["items"]] == [("height", "block"), ("bottom", "warn")]
    assert j["material"]["material"] == "Aluminium" and [i["kind"] for i in j["images"]] == ["top", "bottom"]
    assert calls[-1]["temperature"] == 0.0
    p = c.get(f"/api/projects/{pid}").json()
    assert p["material"] == "Aluminium" and p["material_user"] == 0 and p["cad_check"]["stale"] is False
    n = len(calls)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()["hash"] == j["hash"] and len(calls) == n   # idempotent
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    assert len(calls) == n + 1


def test_idempotent_nach_schaetzung_und_handeingabe(proj):
    c, pid, t, b = proj
    j = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is False      # KI-Schaetzung veraltet die Pruefung nicht
    c.patch(f"/api/projects/{pid}", json={"material": "Stahl"}, headers=H)
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is True       # Handeingabe schon
    j2 = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    assert j2["hash"] != j["hash"] and c.get(f"/api/projects/{pid}").json()["material"] == "Stahl"   # Handeingabe bleibt


def test_hash_aufgeloeste_fotos(proj):
    c, pid, t, b = proj
    j = c.post(f"/api/projects/{pid}/cad-check", json={"photo_ids": None}, headers=H).json()
    _up(c, pid, [{"polygon": L_SHAPE, "gray": 150}], "top")
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is True
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()["hash"] != j["hash"]


def test_cad_check_tageslimit(proj):
    from app import db
    c, pid, t, b = proj
    uid = c.get("/api/me").json()["user"]["id"]
    j = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    for _ in range(30):
        db.audit("cad_check", "Test", user_id=uid)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 200        # gleicher Hash: gespeichert
    assert c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H).status_code == 429
    assert c.post(f"/api/projects/{pid}/suggest", json={}, headers=H).status_code == 429          # zaehlt mit
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py -k "cad_check or idempotent or hash_auf"`
Expected: FAIL (404).

- [ ] **Step 3: Implementierung** `web/app/check.py`:

```python
"""Pruefung vor dem CAD-Auftrag (Spec 2026-10-15 §2.1)."""
from __future__ import annotations

import hashlib
import json
import threading

from . import ai, db, jobs

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def lock_for(pid: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.Lock())


def _r(v):
    return round(v, 2) if isinstance(v, float) else v


def cad_hash(project: dict, photo_ids: list[int] | None, part_id: int | None) -> str:
    pid = project["id"]
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,)) if photo_ids is None or p["id"] in photo_ids]
    al = []
    for p in photos:
        a = db.jload(p["analysis"], {}) or {}
        b = a.get("bottom_align") or {}
        al.append([p["id"], p["view"], p["format"], p["status"], b.get("rot"), _r(b.get("dx")), _r(b.get("dy"))])
    ms = [[m["id"], m["kind"], _r(m["value"]), _r(m["caliper"]), _r(m["unc"]), m["part_id"], (db.jload(m["data"], {}) or {}).get("view"),
           [[_r(x), _r(y)] for x, y in (db.jload(m["data"], {}) or {}).get("points") or []]]
          for m in db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY id", (pid,))]
    ps = []
    for t in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY id", (pid,)):
        d = db.jload(t["data"], {}) or {}
        ps.append([t["id"], t["label"], t["role"], [[_r(x), _r(y)] for x, y in d["polygon"]], d.get("hidden"), d.get("holes"), d.get("same_as")])
    mat = [project.get("color"), project.get("material"), project.get("transparent"), project.get("finish")] if project.get("material_user") else None
    blob = json.dumps({"photos": al, "meas": ms, "parts": ps, "part_id": part_id, "material": mat}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def stored(project: dict) -> dict | None:
    return db.jload(project.get("cad_check"), None)


def public_check(project: dict) -> dict | None:
    s = stored(project)
    if not s:
        return None
    return {**s, "stale": cad_hash(project, s.get("photo_ids"), s.get("part_id")) != s.get("hash")}


def run_check(project: dict, photo_ids: list[int] | None, part_id: int | None, h: str) -> dict:
    """KI-Aufruf, Ergebnis speichern, Material uebernehmen (nur bei material_user=0)."""
    pid = project["id"]
    msgs = jobs.build_initial_message(project, "", {"photo_ids": photo_ids, "part_id": part_id, "for_check": True})
    text, _ = ai.call(ai.CHECK_SYSTEM, msgs, max_tokens=2000, temperature=0.0)
    res = ai.parse_check(text)
    images = [{"photo_id": i["photo_id"], "kind": i["kind"]} for i in jobs.pick_images(pid, photo_ids)]
    out = {"items": res["items"], "material": res["material"], "images": images, "photo_ids": photo_ids, "part_id": part_id,
           "hash": h, "checked_at": db.now()}
    with db.atomic():
        if res["material"] and not project.get("material_user"):
            m = res["material"]
            db.ex("UPDATE projects SET color=?, material=?, transparent=?, finish=? WHERE id=?",
                  (m["color"], m["material"], m["transparent"], m["finish"], pid))
        db.ex("UPDATE projects SET cad_check=? WHERE id=?", (db.jdump(out), pid))
    return out
```

`main.py`:

```python
class CheckIn(BaseModel):
    photo_ids: list[int] | None = None
    part_id: int | None = None
    force: bool = False


@app.post("/api/projects/{pid}/cad-check")
def cad_check(pid: int, body: CheckIn, request: Request, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if body.part_id is not None and not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?", (body.part_id, pid)):
        raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
    with check.lock_for(pid):
        p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
        h = check.cad_hash(p, body.photo_ids, body.part_id)
        s = check.stored(p)
        if s and s.get("hash") == h and not body.force:
            return {**s, "stale": False}
        if not settings.ai_enabled():
            raise HTTPException(503, "KI ist nicht eingerichtet (Verwaltung → Einstellungen).")
        if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
            raise HTTPException(429, f"Tageslimit für KI-Funktionen erreicht ({AI_DAILY_LIMIT}).")
        db.audit("cad_check", f"Projekt {pid}", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
        try:
            out = check.run_check(p, body.photo_ids, body.part_id, h)
        except ai.AIError as e:
            raise HTTPException(502, str(e)) from None
    return {**out, "stale": False}
```

`_ai_uses_today`: `action IN ('suggest','edges_ai','cad_check')`. `_project_public`: `out["cad_check"] = check.public_check(p)` (immer, auch ohne `detail`). `from . import check` in main.py (Importreihenfolge: check importiert jobs und ai, kein Zyklus mit main).

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_edges_api.py -k "cad_check or idempotent or hash or tageslimit"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/check.py web/app/main.py tests/test_check.py
git commit -m "Pruefung vor dem Auftrag: cad-check mit Hash, Idempotenz, Tageslimit und Materialuebernahme"
```

### Task 9: Oberfläche Welle 2 (CAD-Formular, Werkstück-Kasten)

**Files:**
- Modify: `web/static/js/cad.js` (Kasten „Vor dem Modellieren“, automatische Prüfung, `check_items`, Bilderliste aus `cad_check.images`)
- Modify: `web/static/js/photos.js` (Kasten „Werkstück“)

**Interfaces:**
- Consumes: `POST /api/projects/{pid}/cad-check`, `project.cad_check` (`stale`, `items`, `material`, `images`, `photo_ids`, `part_id`), `PATCH /api/projects/{pid}` Werkstück-Felder.

- [ ] **Step 1: cad.js**

Im `form(main)`: Zustand `let chk = P.cad_check, checking = false;` Funktionen:

```js
const sel = () => ({ photo_ids: [...picked], part_id: partSel ? Number(partSel) : null });
const same = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());
const needCheck = () => !chk || chk.stale || !same(chk.photo_ids, sel().photo_ids) || (chk.part_id ?? null) !== sel().part_id;
async function runCheck(force = false) {
  if (checking) return; checking = true; drawCheck();
  try { chk = await api(`/api/projects/${P.id}/cad-check`, { method: "POST", body: { ...sel(), force } }); await reloadProject(); }
  catch (e) { chk = { error: e.message, items: [], images: [] }; }
  finally { checking = false; drawCheck(); }
}
const SEV = { block: ["err", "warn"], warn: ["warn", "warn"] };
function drawCheck() {
  const blocks = (chk?.items || []).filter(i => i.severity === "block").length;
  submit.replaceChildren(icon("cube"), blocks ? "Trotzdem erzeugen" : "CAD-Modell erzeugen");
  clear(checkBox, h("div", { class: "card-head" }, h("h2", {}, "Vor dem Modellieren"),
      h("button", { class: "btn sm", disabled: checking, onclick: () => runCheck(true) }, checking ? h("span", { class: "spin" }) : icon("refresh", 14), "Erneut prüfen")),
    chk?.error ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, `Prüfung nicht möglich: ${chk.error}`)) : null,
    chk && !chk.error ? (chk.items.length ? h("ul", { class: "checks" }, chk.items.map(i => h("li", {}, stateIcon(SEV[i.severity][0] === "err" ? "fail" : "warn"), h("span", {}, i.text))))
      : h("div", { class: "note ok" }, icon("check"), h("span", {}, "Die Unterlagen reichen für ein vollständiges Modell."))) : null,
    chk?.material ? h("span", { class: "xs muted" }, `Werkstück (geschätzt): ${[chk.material.color, chk.material.material, chk.material.finish].filter(Boolean).join(", ")} – unter „Fotos prüfen“ änderbar`) : null,
    chk?.checked_at ? h("span", { class: "xs muted" }, `Geprüft ${dt(chk.checked_at)}${chk.stale ? " · veraltet" : ""}`) : null);
}
```

`checkBox = h("section", { class: "card" })` im Formular vor `submit` in der rechten Spalte. Nach dem Aufbau: `drawCheck(); if (needCheck()) runCheck();`. Bei Änderung der Fotoauswahl (`drawPhotos`) und des Teils (`onchange` von `partBox`): `if (needCheck()) runCheck();`. Beim Absenden: `check_items: (chk?.items || []).map(i => ({ kind: i.kind, severity: i.severity, text: i.text }))`. Bilderliste: Beschriftung „Entzerrte Fotos · N“ wird zu „Bilder für die KI · N“ und listet `chk?.images` (Dateiname + Art: Draufsicht / Von unten / Höhenlehre / Schrägfoto (Original)); mehr als 6 Bilder nach Auswahl → `h("span", { class: "xs", style: { color: "var(--warn)" } }, "Nur die ersten 6 Bilder gehen mit")` (Zählung über die gewählten Fotos: top/bottom je 1, tilted/overview je 1, gauge je 1 zusätzlich).

- [ ] **Step 2: photos.js Werkstück-Kasten** über der Fotoliste:

```js
function werkstueck() {
  const P = S.project, mk = (k, ph) => h("input", { class: "input", value: P[k] || "", placeholder: ph, maxlength: 40 });
  const color = mk("color", "z. B. silber"), material = mk("material", "z. B. Aluminium");
  const transp = h("select", { class: "input" }, [["", "unbekannt"], ["0", "nein"], ["1", "teilweise"], ["2", "ja"]].map(([v, t]) => h("option", { value: v, selected: String(P.transparent ?? "") === v }, t)));
  const finish = h("select", { class: "input" }, [["", "unbekannt"], ["matt", "matt"], ["glaenzend", "glänzend"]].map(([v, t]) => h("option", { value: v, selected: (P.finish || "") === v }, t)));
  const save = async () => {
    const body = { color: color.value.trim(), material: material.value.trim() };
    if (transp.value !== "") body.transparent = Number(transp.value);
    if (finish.value) body.finish = finish.value;
    try { S.project = await api(`/api/projects/${P.id}`, { method: "PATCH", body }); draw(); } catch (e) { fail(e); }
  };
  [color, material, transp, finish].forEach(el => el.addEventListener("change", save));
  return h("section", { class: "card", style: { gap: "8px" } }, h("div", { class: "card-head" }, h("h3", {}, "Werkstück"),
      h("span", { class: "xs muted" }, P.material_user ? "von Hand gesetzt" : (P.material ? "von der KI geschätzt" : "noch nicht gesetzt"))),
    h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "flabel" }, "Farbe"), color), h("label", { class: "field" }, h("span", { class: "flabel" }, "Material"), material),
      h("label", { class: "field" }, h("span", { class: "flabel" }, "Transparent"), transp), h("label", { class: "field" }, h("span", { class: "flabel" }, "Oberfläche"), finish)),
    h("span", { class: "xs muted" }, "Vor „Kanten erkennen“ setzen – die Erkennung nutzt diese Angaben."),
    P.material_user ? h("button", { class: "btn sm ghost", style: { alignSelf: "flex-start" }, onclick: async () => { try { S.project = await api(`/api/projects/${P.id}`, { method: "PATCH", body: { clear_material: true } }); draw(); } catch (e) { fail(e); } } }, "Zurücksetzen") : null);
}
```

In `draw()` den Kasten neu zeichnen (Container `wsBox` im `aside` vor `list`, `clear(wsBox, werkstueck())`).

- [ ] **Step 3: Prüfen**

Run: `for f in web/static/js/*.js; do node --check "$f"; done && python -m pytest -q -p no:cacheprovider tests/test_texts.py`; Browser-Probe im Scratchpad: Formular öffnen → Prüfung läuft automatisch (Testmodus-Punkte erscheinen, Knopf heißt „Trotzdem erzeugen“), erneutes Öffnen ohne Änderung erzeugt keinen zweiten `POST …/cad-check` mit KI-Aufruf (Netzwerk: 200 mit gleichem `hash`), Auftrag absenden → `check_items` im Request-Body.

- [ ] **Step 4: Commit und Wellenabschluss**

```bash
git add web/static/js/cad.js web/static/js/photos.js
git commit -m "Oberflaeche: Pruefkasten vor dem Modellieren, Bilderliste, Werkstueck-Kasten"
source /root/Snap2CAD-venv/bin/activate && ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs
```

---

## Welle 3 – Kantenerkennung mit Hinweisen

### Task 10: Schatten, Transparenz, helle Teile, Kontrast, veraltete Kanten

**Files:**
- Modify: `core/edges.py` (`_grid_energy(win_mm)`, `_mask(rect, fmt, hints)`, `detect(rect, fmt, hints=None)`, `contrast`)
- Modify: `tests/conftest.py` (`synthetic_photo(shadow=…)`, Objekt-`alpha`)
- Modify: `tests/test_edges.py`
- Modify: `web/app/main.py` (`_hints(project)`, `_analyze_store` mit Hinweisen und `contrast`, `photo_edges` mit Hinweisen und `hints` in `edges.json`, `_photo_public` `contrast`/`low_contrast`)
- Modify: `web/app/parts.py` (`ai_parts`: Zeile „Fotografiertes Original“)
- Modify: `web/static/js/photos.js` (Kontrasthinweis), `web/static/js/measure.js` (Hinweis „Werkstück geändert – Kanten neu erkennen“)

**Interfaces:**
- Produces: `edges.detect(rect, fmt, hints=None)` mit `hints = {"transparent": 0|1|2, "light": bool}` und Rückgabeschlüssel `contrast`; `main._hints(project) -> dict`; `photo.contrast`, `photo.low_contrast`; `edges.json["hints"]`.

- [ ] **Step 1: Failing tests**

`conftest.synthetic_photo`: neue Parameter `shadow: dict | None = None` (`{"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}`: Streifen der Breite `mm` an den genannten Seiten jedes `rect`/`polygon`-Objekts (Bounding-Box), Blattpixel mit `dark` multipliziert, Raster bleibt sichtbar) und je Objekt `alpha` (Pixel = `alpha·gray + (1 − alpha)·Blatt`, über `cv2.addWeighted` im gefüllten Bereich). Tests in `tests/test_edges.py`:

```python
def test_schatten_bleibt_aussen():
    img = vision.load_image(synthetic_photo("A4", objects=[BOX], shadow={"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}))
    a = vision.analyze(img, "A4")
    res = edges.detect(vision.rectify_mat(img, a["homography"], "A4"), "A4")
    assert len(res["outlines"]) == 1 and len(res["outlines"][0]["polygon"]) == 4
    _close(res["outlines"][0]["polygon"], [(60, 80), (120, 80), (120, 120), (60, 120)], 0.5)


def test_transparenter_quader_mit_hinweis():
    res = edges.detect(_rect([{"rect": [60, 80, 60, 40], "gray": 200, "alpha": 0.5}]), "A4", hints={"transparent": 2})
    assert len(res["outlines"]) == 1
    _close(res["outlines"][0]["polygon"], [(60, 80), (120, 80), (120, 120), (60, 120)], 1.0)


def test_kontrastwert():
    assert edges.detect(_rect([BOX]), "A4")["contrast"] > 30
    assert edges.detect(_rect([{"rect": [60, 80, 60, 40], "gray": 225}]), "A4")["contrast"] < 20
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_edges.py -k "schatten or transparent or kontrast"`
Expected: FAIL (`schatten`: 8 statt 4 Ecken – so im Preflight gemessen; `transparent`: TypeError `hints`; `kontrast`: KeyError).

- [ ] **Step 3: Implementierung in `core/edges.py`**

- `_grid_energy(rect, win_mm=GRID_WIN_MM, smooth_mm=GRID_SMOOTH_MM)`.
- Neue Konstanten: `GRID_FINE_MM = 2.0` (feines Fenster für den Schatten-Veto), `SHADOW_CHROMA = 6.0` (Farbabstand, bis zu dem ein Unterschied als reiner Helligkeitsunterschied gilt), `TRANSP_MIN_DIFF = 9.0`, `LIGHT_DIFF_FACTOR = 0.6`, `LIGHT_GRID_FACTOR = 1.3`.
- `_mask(rect, fmt, hints)`:
  - Helligkeitsnormierung: `Lloc = cv2.boxFilter(lab[..., 0], -1, (k_bg, k_bg))`, `Lref = median(Lloc[band])`; `en = en * Lref / np.maximum(Lloc, 1)` **vor** `ref`/`paperish`; dieselbe Normierung für `fine = _grid_energy(rect, GRID_FINE_MM, GRID_FINE_MM)[:h, :w]` mit eigenem `ref_f = median(fine[band])`.
  - Schatten-Veto: `shadowlike = (dc < SHADOW_CHROMA) & (fine > GRID_PAPER * ref_f)`; `color = (diff > max(th, 18.0)) & ~shadowlike`.
  - `transparent == 2`: `nogrid[:] = 0`, `sure_bg[:] = False`, `color = diff > max(th * 0.5, TRANSP_MIN_DIFF)` (ohne Veto), `mask = close(color, 3 mm)`, `_fill_unround`, größte Komponente, **kein** GrabCut (Rückgabe direkt).
  - `transparent == 1`: `nogrid = en < 0.5 * GRID_OBJECT * ref`.
  - `light`: `color = diff > max(LIGHT_DIFF_FACTOR * th, 12.0) & ~shadowlike`, `nogrid = en < LIGHT_GRID_FACTOR * GRID_OBJECT * ref`.
  - Rückgabe zusätzlich `diff` (für den Kontrast).
- `detect(rect, fmt, hints=None)`: `mask, color, diff = _mask(rect, fmt, hints or {})`; `res["contrast"] = round(float(np.mean(diff[mask > 0])), 1) if mask.any() else 0.0`; `res["hints"] = hints or {}`.
- Kalibrierung: Nach GREEN der drei neuen Tests die bestehenden `tests/test_edges.py` laufen lassen (Quader, Platte+Bohrung, heller Körper) und die vier echten Fotos im Scratchpad mit `draw_candidates` prüfen (Umriss von Foto 1 ohne Schattensporn unten, mit beiden Fasen oben). Schwellen nur als Konstanten ändern; jede Änderung mit beiden Testläufen belegen.

Server: `main._hints(project)`: `{"transparent": project["transparent"] or 0, "light": (project.get("color") or "").strip().lower() in LIGHT_COLORS} if project.get("material_user") else {}`. `_analyze_store(phid, img, fmt)` lädt das Projekt über das Foto und ruft `edges.detect(rect, fmt, _hints(project))`; speichert `a["contrast"]`, `a["outline_mm"]`. `_photo_public`: `"contrast": a.get("contrast"), "low_contrast": a.get("contrast") is not None and a["contrast"] < 12`. `photo_edges`: `res = edges.detect(img, ph["format"], _hints(p))`; `edges.json` enthält `hints` (ist in `res`). `GET …/edges.json` liefert sie mit; `measure.js` vergleicht `r.hints` mit `{transparent: S.project.material_user ? (S.project.transparent || 0) : 0, light: …}` – einfacher: der Server liefert in `_photo_public` `edges_stale: bool` (Vergleich `edges.json["hints"]` gegen `_hints(project)`), und `measure.js` zeigt bei `photo.edges_stale` neben „Kanten erkennen“ den Hinweis „Werkstück geändert – Kanten neu erkennen“. `parts.ai_parts(photo_dir, res, material_text="")`: `content.append({"type": "text", "text": candidate_text(res) + ("\n" + material_text + "\nBei transparenten Teilen sind durchscheinende Strukturen Innenbohrungen, keine Rillen." if material_text else "")})`; `photo_edges` übergibt `jobs.material_line(p)`.

`photos.js`: bei `p.low_contrast` ein `note warn`: „Geringer Kontrast zur Unterlage – Licht seitlich, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen.“

- [ ] **Step 4: Tests grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_edges.py tests/test_edges_api.py tests/test_align.py tests/test_check.py`
Expected: PASS, inklusive der bestehenden Umriss-Tests.

- [ ] **Step 5: Commit und Wellenabschluss**

```bash
git add core/edges.py tests/conftest.py tests/test_edges.py web/app/main.py web/app/parts.py web/static/js/photos.js web/static/js/measure.js
git commit -m "Kantenerkennung: Schlagschatten ausgeschlossen, Hinweise fuer transparente und helle Teile, Kontrastwert, veraltete Kanten"
source /root/Snap2CAD-venv/bin/activate && ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs
```

---

### Task 11: Browser-Durchlauf, Review, Auslieferung

**Files:**
- Scratchpad: `pw/stufe_a.mjs` (Playwright, nicht im Repo)
- Modify: `README.md` (Fotoart „Von unten“, Prüfung vor dem Auftrag, Werkstück – je ein Satz im Abschnitt zum Ablauf)

- [ ] **Step 1: Playwright-Durchlauf** gegen einen lokalen Server (`AI_FAKE=1 SANDBOX_MODE=local`, Port 8765): Draufsicht und Unteransicht (synthetisch) hochladen → Detail der Unteransicht zeigt Lage, Klick auf eine andere Lage → `rot` geändert; Werkstück setzen; Messen: Quelle „Von unten“ wählbar, Messung mit `view=bottom`; CAD-Formular: Prüfkasten erscheint automatisch mit zwei Punkten, „Trotzdem erzeugen“ → Auftrag läuft durch (Testmodus), zweites Öffnen ohne KI-Aufruf; Konsole ohne Fehler.
  Expected: alle Prüfpunkte wahr, `konsolenfehler == []`.
- [ ] **Step 2: README** ergänzen, `pytest tests/test_texts.py` grün.
- [ ] **Step 3: Review** (whole-branch, wie bei PR #3/#4: JS-Kette und ein Server-Reviewer), Befunde beheben, Suite grün.
- [ ] **Step 4: Auslieferung** (Spec §7): PR → CI grün → Merge → CI auf `main` → NAS mit Sicherung (`backup-data-<datum>.tgz` bei gestoppten Containern) → `compose pull && up -d` → Gesundheit → A8 mit dem Kühlkörperblock (dreimal, Zählung Fasen/Stufen/Bohrungen notieren).

```bash
git add README.md
git commit -m "README: Unteransicht, Pruefung vor dem Auftrag, Werkstueck"
```
