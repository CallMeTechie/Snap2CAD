# Unteransicht, Prüfung vor dem Auftrag, Material und Kontrast – Umsetzungsplan (Stufe A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die CAD-KI bekommt eine ausgerichtete Unteransicht, verbindliche Umrisse, Schrägfotos im Original, eine Prüfung vor dem Auftrag und Werkstück-Angaben; die Kantenerkennung ignoriert Schlagschatten und kommt mit transparenten Teilen zurecht.

**Architecture:** Drei Wellen auf einem Branch. W1 (Tasks 1–6): Lage-Mathematik in `core/vision.py`, Kantenerkennung mit Hinweisen in `core/edges.py` (größtes Risiko, deshalb früh), `bottom`-Ansicht und Ausrichtung im Server, Verknüpfung der Teile, Oberfläche. W2 (Tasks 7–11): Werkstück-Spalten, Prompt und Temperatur, Bildauswahl und Auftragsnachricht, Endpunkt `cad-check`, Oberfläche. W3 (Task 12): Hinweise im Server, Kontrastwarnung, veraltete Kanten. Task 13: Durchlauf im Browser, Review, Auslieferung.

**Tech Stack:** Python 3.13, FastAPI, SQLite, OpenCV, numpy, shapely; Vanilla-JS-Module; pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-15-unteransicht-pruefung-material-design.md`

## Global Constraints

- Entscheidungen des Nutzers (Spec „Entscheidungen des Nutzers“) sind gesetzt: Prüfung vor dem Auftrag; vier Lagen mit Handwahl; KI schätzt Werkstück, Handeingabe hat Vorrang (auch bei einer Handeingabe **während** des KI-Aufrufs); `same_as` automatisch über IoU ≥ 0,5; Hinweise für die Kantenerkennung nur aus `material_user=1`; Prüfung automatisch, sobald veraltet; neue KI-Schätzung ersetzt alte.
- Lage: `lage_matrix(rot, dx, dy, w, h) = Verschiebung(dx, dy) · Drehung(rot um (w/2, h/2), gegen den Uhrzeigersinn) · Spiegelung(x → w − x)`; `rot ∈ {0, 90, 180, 270}`; Festwert `lage_matrix(90, 0, 0, 190, 230)`: (10, 20) → (190, 200). Alle Stellen (`align_bottom`, `to_top`, `bottom_warp`, `bottom_of`) rufen diese eine Funktion.
- `core/` bleibt ohne Web-Abhängigkeiten; shapely nur funktionslokal. In `web/app/jobs.py`, `web/app/parts.py` und `web/app/check.py` wird `core.vision` **nur funktionslokal** importiert (`main.py` setzt `sys.path` erst nach den App-Importen; Muster `parts.candidate_image`). `import cv2` auf Modulebene ist in Ordnung.
- `_align_photo`, `_realign_project`, `_outline_of` und `edges.detect` laufen **nie innerhalb von `db.atomic()`** (das hält die globale DB-Sperre); jede Ausrichtung endet mit `parts.link_bottom`.
- Höchstens 6 Bilder je Nachricht, Reihenfolge Draufsicht, Unteransicht, Höhenlehre, Schrägfotos (`jobs.pick_images`).
- Texte in der Oberfläche ohne „Claude“/„Anthropic“ (`tests/test_texts.py`); KI-Text sagt „Fotografiertes Original“, Oberfläche „Werkstück“.
- `AI_DAILY_LIMIT = 30`; `_ai_uses_today` zählt `suggest`, `edges_ai`, `cad_check`.
- Zeilenlänge 130 (ruff E501); Variablennamen nicht `l` (E741); keine unbenutzten Zuweisungen (F841). Code-Snippets im Plan, die länger sind, beim Übernehmen an Wortgrenzen umbrechen. Jeder Task endet mit `ruff check` auf den geänderten Dateien.
- Echte Fotos nur im Scratchpad (`/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad/nasfotos/`), nie im Repo.
- Keine Claude-Attribution in Commits.
- Jede Welle endet mit grüner lokaler Suite **und** grüner CI auf dem Branch: `source /root/Snap2CAD-venv/bin/activate && ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs && git push origin unteransicht-pruefung-material && gh run watch --exit-status $(gh run list -b unteransicht-pruefung-material -L1 --json databaseId -q '.[0].databaseId')`.
- Protokoll der Messwerte (Laufzeiten, Kalibrierung, Ausrichtung am echten Block): `/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad/stufe-a-protokoll.md` (nicht im Repo).

## Handlungsauftrag an Marc (vor Task 6)

Den Kühlkörperblock umgedreht auf der Unterlage fotografieren, je einmal „seitlich umgedreht“ und „nach vorn umgedreht“, und die zwei Fotos in Snap2CAD auf der NAS hochladen (Ansicht: beliebig, sie werden nur für die Messung in Task 6 Step 3a aus der NAS-DB kopiert). Ohne diese Fotos läuft die Messung in Task 6 mit einer simulierten Unteransicht aus Foto 1, und A8 bleibt der erste echte Test.

## Review Focus

1. Unteransicht in Lage 90 oder 270 mit Versatz: `to_top` und `rect_top.jpg` zeigen dieselbe Abbildung (Task 1 Festwerte, Task 4 `test_align_jpg_und_to_top_gleich`).
2. Zwei Draufsichten im Projekt, die erste wird gelöscht: Ausrichtung wechselt auf die nächste Referenz, Handwahl bleibt (Task 4 `test_handwahl_und_referenzwechsel`).
3. Prüfung mit `photo_ids: null`, danach ein Foto hochgeladen: `stale` wird wahr (Task 10 `test_hash_aufgeloeste_fotos`).
4. Werkstück von der KI geschätzt, Nutzer öffnet das Formular erneut: kein zweiter KI-Aufruf (Task 10 `test_idempotent_nach_schaetzung_und_handeingabe`).
5. Schlagschatten bei dunklem Objekt, helles Objekt ohne Hinweise, halbtransparenter Quader ohne Hinweis und mit `transparent: 1`: alle weiterhin erkannt (Task 2, bestehende Tests `test_quader_umriss`, `test_heller_koerper_ohne_raster` und neu `test_halbtransparent_ohne_oder_teilweise_nicht_schlechter`).

---

## Welle 1 – Unteransicht und Kantenerkennung

### Task 1: Lage-Mathematik und Ausrichtung in `core/vision.py`

**Files:**
- Modify: `core/vision.py` (nach `rectify_gauge`; `rectify_mat` nutzt künftig `_px_matrix`)
- Modify: `tests/conftest.py` (`synthetic_photo`: `polygon`-Objekte; Hilfsfunktion `bottom_of`)
- Create: `tests/test_align.py`

**Interfaces:**
- Produces: `vision.LAGEN = (0, 90, 180, 270)`; `vision.lage_matrix(rot, dx, dy, w, h) -> np.ndarray (3×3)`; `vision.apply_lage(M, pts) -> list[list[float]]`; `vision.align_bottom(top_outline, bottom_outline, bot_w, bot_h, rot=None) -> dict` mit `rot, dx, dy, iou, iou_next, unsure`; `vision.bottom_warp_matrix(analysis_bot, analysis_top, pxmm_out) -> np.ndarray`; `vision.bottom_warp(rect_bot, analysis_bot, analysis_top=None, pxmm_out=PX_PER_MM) -> np.ndarray`; `vision.draw_outlines(img, polys_mm, colors, pxmm, h_mm)`; `conftest.bottom_of(objects, rot, dx=0.0, dy=0.0, fmt="A4") -> list[dict]`.

- [ ] **Step 1: Failing tests schreiben**

`tests/test_align.py`:

```python
"""Lage der Unteransicht (Spec 2026-10-15 §1, A1)."""
import numpy as np
import pytest

from conftest import bottom_of, synthetic_photo
from core import edges, vision

L_SHAPE = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 120], [60, 120]]   # 60 x 40, Schenkel 15
HOLE = {"circle": [110, 87.5, 5], "gray": 235}
W, H = 190, 230


def _outline(objects):
    img = vision.load_image(synthetic_photo("A4", objects=objects))
    a = vision.analyze(img, "A4")
    return edges.detect(vision.rectify_mat(img, a["homography"], "A4"), "A4")["outlines"][0]["polygon"]


def test_lage_matrix_festwerte():
    assert vision.apply_lage(vision.lage_matrix(90, 0, 0, W, H), [[10, 20]])[0] == pytest.approx([190, 200])
    assert vision.apply_lage(vision.lage_matrix(90, -30, 5, W, H), [[10, 20]])[0] == pytest.approx([160, 205])
    assert vision.apply_lage(vision.lage_matrix(0, 0, 0, W, H), [[10, 20]])[0] == pytest.approx([180, 20])
    assert vision.apply_lage(vision.lage_matrix(180, 0, 0, W, H), [[10, 20]])[0] == pytest.approx([10, 210])


def test_bottom_warp_festwert():
    rect = {"pxmm": 10.0, "w_mm": 190.0, "h_mm": 230.0, "w": 1900, "h": 2300}
    M = vision.bottom_warp_matrix({"rect": rect, "bottom_align": {"rot": 90, "dx": 0, "dy": 0}}, {"rect": rect}, 10.0)
    assert (M @ np.array([100.0, 2100.0, 1.0]))[:2] == pytest.approx([1900, 300], abs=1)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_align_bottom_findet_lage(rot):
    dx, dy = (25.0, -20.0) if rot in (0, 180) else (-30.0, 22.0)
    inv = np.linalg.inv(vision.lage_matrix(rot, dx, dy, W, H))
    r = vision.align_bottom(L_SHAPE, vision.apply_lage(inv, L_SHAPE), W, H)
    assert r["rot"] == rot and r["iou"] >= 0.9 and r["iou"] - r["iou_next"] >= 0.2 and not r["unsure"]
    assert (r["dx"], r["dy"]) == pytest.approx((dx, dy), abs=0.5)
    hole_b = vision.apply_lage(inv, [HOLE["circle"][:2]])[0]
    back = vision.apply_lage(vision.lage_matrix(r["rot"], r["dx"], r["dy"], W, H), [hole_b])[0]
    assert back == pytest.approx(HOLE["circle"][:2], abs=0.5)


def test_align_bottom_vorgegebene_lage():
    inv = np.linalg.inv(vision.lage_matrix(90, 0, 0, W, H))
    r = vision.align_bottom(L_SHAPE, vision.apply_lage(inv, L_SHAPE), W, H, rot=270)
    assert r["rot"] == 270 and r["iou_next"] >= 0.9   # beste der uebrigen ist die richtige Lage 90


def test_rechteck_unsicher():
    R = [[60, 80], [120, 80], [120, 120], [60, 120]]
    for lage, erwartet in ((0, (0, 180)), (90, (90, 270))):
        r = vision.align_bottom(R, vision.apply_lage(np.linalg.inv(vision.lage_matrix(lage, 0, 0, W, H)), R), W, H)
        assert r["unsure"] and r["rot"] in erwartet


def test_zwei_verschiedene_teile_unsicher():
    r = vision.align_bottom([[60, 80], [120, 80], [120, 120], [60, 120]], [[40, 40], [70, 40], [70, 70], [40, 70]], W, H)
    assert r["unsure"]


def test_entartet_ohne_ausnahme():
    r = vision.align_bottom(L_SHAPE, [[10, 10], [20, 20], [30, 30]], W, H)   # kollinear
    assert r["unsure"] and r["iou"] == 0.0


def test_fast_symmetrisch_nie_sicher_falsch():
    """Umriss ohne eine Kante (Platte fehlt unten): richtige Lage oder unsicher, nie sicher falsch."""
    kurz = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 117], [60, 117]]
    for rot in (0, 180):
        inv = np.linalg.inv(vision.lage_matrix(rot, 10, -10, W, H))
        r = vision.align_bottom(L_SHAPE, vision.apply_lage(inv, kurz), W, H)
        assert r["rot"] == rot or r["unsure"]


@pytest.mark.parametrize("rot,dx,dy", [(0, 25, -20), (90, -30, 22), (180, 25, -20), (270, -30, 22)])
def test_synthetische_unteransicht(rot, dx, dy):
    top = [{"polygon": L_SHAPE, "gray": 150}, HOLE]
    r = vision.align_bottom(_outline(top), _outline(bottom_of(top, rot, dx, dy)), W, H)
    assert r["rot"] == rot and r["iou"] >= 0.9 and r["iou"] - r["iou_next"] >= 0.2 and not r["unsure"]
```

`tests/conftest.py` – in `synthetic_photo` nach dem `circle`-Zweig (12 Leerzeichen Einrückung) einfügen und `bottom_of` am Dateiende ergänzen:

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
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `source /root/Snap2CAD-venv/bin/activate && python -m pytest -q -p no:cacheprovider tests/test_align.py`
Expected: FAIL mit `ImportError: cannot import name 'bottom_of'`.

- [ ] **Step 3: Implementierung in `core/vision.py`**

`rectify_mat`: `to_px = _px_matrix(pxmm, gh)` (Definition unten, vor `rectify_mat` einfügen). Nach `rectify_gauge`:

```python
# ------------------------------------------------------------------ Unteransicht (Spec 2026-10-15 §1)

LAGEN = (0, 90, 180, 270)
ALIGN_MIN_IOU = 0.6
ALIGN_MIN_GAP = 0.05


def _px_matrix(pxmm: float, h_mm: float) -> np.ndarray:
    """mm (y nach oben) -> Pixel (y nach unten), wie rectify_mat."""
    return np.array([[pxmm, 0, 0], [0, -pxmm, h_mm * pxmm], [0, 0, 1]], np.float64)


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
    """Beste Lage der Unteransicht zur Draufsicht: IoU je Lage nach Schwerpunkt-Verschiebung.
    rot=None: alle vier Lagen; sonst nur diese (iou_next = beste der uebrigen drei)."""
    from shapely.geometry import Polygon  # nur hier: core/ bleibt ohne harte shapely-Abhaengigkeit

    def valid(p):
        if len(p) < 3:
            return Polygon()
        g = Polygon(p)
        return g if g.is_valid else g.buffer(0)
    unsure = {"rot": rot or 0, "dx": 0.0, "dy": 0.0, "iou": 0.0, "iou_next": 0.0, "unsure": True}
    T = valid(top_outline)
    if T.is_empty or T.area < 1.0:
        return unsure
    scores = {}
    for r in LAGEN:
        P = valid(apply_lage(lage_matrix(r, 0, 0, bot_w, bot_h), bottom_outline))
        if P.is_empty or P.area < 1.0:
            scores[r] = (0.0, 0.0, 0.0)
            continue
        dx, dy = T.centroid.x - P.centroid.x, T.centroid.y - P.centroid.y
        Q = valid(apply_lage(lage_matrix(r, dx, dy, bot_w, bot_h), bottom_outline))
        union = T.union(Q).area
        scores[r] = (T.intersection(Q).area / union if union > 0 else 0.0, dx, dy)
    best = rot if rot is not None else max(LAGEN, key=lambda r: (round(scores[r][0], 4), -r))
    iou, dx, dy = scores[best]
    if iou == 0.0:
        return unsure
    iou_next = max(scores[r][0] for r in LAGEN if r != best)
    return {"rot": best, "dx": round(dx, 3), "dy": round(dy, 3), "iou": round(iou, 4), "iou_next": round(iou_next, 4),
            "unsure": bool(iou < ALIGN_MIN_IOU or iou - iou_next < ALIGN_MIN_GAP)}


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


def draw_outlines(img: np.ndarray, polys_mm: list, colors: list, pxmm: float, h_mm: float) -> np.ndarray:
    """Umrisse (mm, y nach oben) in ein Bild zeichnen (fuer align.jpg)."""
    for poly, col in zip(polys_mm, colors, strict=True):
        if poly:
            pts = np.array([[int(x * pxmm), int((h_mm - y) * pxmm)] for x, y in poly], np.int32)
            cv2.polylines(img, [pts], True, col, 2, cv2.LINE_AA)
    return img
```

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py tests/test_edges.py tests/test_core.py && ruff check core/vision.py tests/conftest.py tests/test_align.py`
Expected: PASS, ruff sauber.

- [ ] **Step 5: Commit**

```bash
git add core/vision.py tests/conftest.py tests/test_align.py
git commit -m "Unteransicht: Lage-Matrix, Ausrichtung ueber Umriss-IoU, Pixelabbildung (Spec Stufe A §1)"
```

### Task 2: Kantenerkennung: Schlagschatten, Transparenz, helle Teile, Kontrast (`core/edges.py`)

**Files:**
- Modify: `core/edges.py` (`_grid_energy(win_mm, smooth_mm)`, `_mask(rect, fmt, hints)`, `detect(rect, fmt, hints=None)`)
- Modify: `tests/conftest.py` (`synthetic_photo(shadow=…)`, Objekt-`alpha`)
- Modify: `tests/test_edges.py`

**Interfaces:**
- Produces: `edges.detect(rect, fmt, hints=None)` mit `hints = {"transparent": 0|1|2, "light": bool}`; Rückgabe zusätzlich `contrast: float | None` (0–100, `None` ohne Umriss) und `hints`.

- [ ] **Step 1: Failing tests**

`conftest.synthetic_photo`: neue Parameter `shadow: dict | None = None` (`{"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}`: Streifen der Breite `mm` an den genannten Seiten der Bounding-Box jedes `rect`/`polygon`-Objekts; dort werden die Blattpixel mit `dark` multipliziert, das Raster bleibt sichtbar; Schatten vor den Objekten zeichnen) und je Objekt `alpha` (Pixel = `alpha·gray + (1 − alpha)·Blatt`: Objekt in eine Kopie zeichnen, mit `cv2.addWeighted` in der Objektmaske mischen). Tests in `tests/test_edges.py`:

```python
SHADOW = {"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}
GLASS = {"rect": [60, 80, 60, 40], "gray": 200, "alpha": 0.5}
CORNERS = [(60, 80), (120, 80), (120, 120), (60, 120)]


def test_schatten_bleibt_aussen():
    img = vision.load_image(synthetic_photo("A4", objects=[BOX], shadow=SHADOW))
    a = vision.analyze(img, "A4")
    res = edges.detect(vision.rectify_mat(img, a["homography"], "A4"), "A4")
    assert len(res["outlines"]) == 1 and len(res["outlines"][0]["polygon"]) == 4
    _close(res["outlines"][0]["polygon"], CORNERS, 0.5)


def test_transparenter_quader_mit_hinweis():
    res = edges.detect(_rect([GLASS]), "A4", hints={"transparent": 2})
    assert len(res["outlines"]) == 1
    _close(res["outlines"][0]["polygon"], CORNERS, 1.0)


def test_halbtransparent_ohne_oder_teilweise_nicht_schlechter():
    img = _rect([GLASS])
    for hints in (None, {"transparent": 1}):
        assert len(edges.detect(img, "A4", hints=hints)["outlines"]) == 1, hints


def test_heller_koerper_mit_hinweis():
    res = edges.detect(_rect([{"rect": [60, 80, 60, 40], "gray": 225}]), "A4", hints={"light": True})
    assert len(res["outlines"]) == 1
    _close(res["outlines"][0]["polygon"], CORNERS, 1.0)


def test_kontrastwert():
    assert edges.detect(_rect([BOX]), "A4")["contrast"] > 30
    assert edges.detect(_rect([{"rect": [60, 80, 60, 40], "gray": 225}]), "A4")["contrast"] < 20
    assert edges.detect(_rect([]), "A4")["contrast"] is None
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_edges.py -k "schatten or transparent or halbtransparent or hinweis or kontrast"`
Expected: FAIL (`schatten`: 8 statt 4 Ecken – im Preflight gemessen; `transparent`/`hinweis`: TypeError `hints`; `kontrast`: KeyError).

- [ ] **Step 3: Implementierung**

- `_grid_energy(rect, win_mm=GRID_WIN_MM, smooth_mm=GRID_SMOOTH_MM)`.
- Neue Konstanten (mit Kommentar): `GRID_FINE_MM = 2.0` (feines Fenster für den Schatten-Veto), `SHADOW_CHROMA = 6.0` (bis zu diesem Farbabstand gilt ein Unterschied als reiner Helligkeitsunterschied), `TRANSP_MIN_DIFF = 9.0`, `LIGHT_DIFF_FACTOR = 0.6`, `LIGHT_GRID_FACTOR = 1.3`.
- `_mask(rect, fmt, hints) -> (mask, color, diff)`; `t = hints.get("transparent", 0)`, `light = hints.get("light", False)`:
  - **Nur bei `t == 0`** Helligkeitsnormierung und Schatten-Veto: `Lloc = cv2.boxFilter(lab[..., 0], -1, (k_bg, k_bg))`, `Lref = median(Lloc[band])`, `en = en * Lref / np.maximum(Lloc, 1)` vor `ref`/`paperish`; `fine = _grid_energy(rect, GRID_FINE_MM, GRID_FINE_MM)[:h, :w]` ebenso normiert mit eigenem `ref_f = median(fine[band])`; `shadowlike = (dc < SHADOW_CHROMA) & (fine > GRID_PAPER * ref_f)`; `color = (diff > thr) & ~shadowlike`. (Im Preflight nachgebaut: Schatten 0,36 mm, Grau 40 mit Schatten 0,3 mm, Grau 150 0,3 mm, hell 0,53 mm.)
  - `t == 1`: wie bisher (keine Normierung, kein Veto), nur `nogrid = en < 0.5 * GRID_OBJECT * ref`.
  - `t == 2`: `nogrid[:] = 0`, `sure_bg[:] = False`, `color = diff > max(th * 0.5, TRANSP_MIN_DIFF)` (kein Veto), `mask = MORPH_CLOSE(color, 3 mm)`, `_fill_unround`, größte Komponente, kein GrabCut; `_refine` läuft wie immer in `detect`. (Nachgebaut: 4 Ecken, 0,49 mm.)
  - `light`: `thr = max(LIGHT_DIFF_FACTOR * th, 12.0)`, `nogrid = en < LIGHT_GRID_FACTOR * GRID_OBJECT * ref`.
  - Rückfall: Liefert `_mask` **ohne Hinweise** keine Komponente ≥ `MIN_AREA_MM2`, einmal ohne Normierung und Veto wiederholen (Verhalten vor dieser Stufe). (Nachgebaut: halbtransparenter Quader ohne Hinweis und mit `transparent: 1` je 1 Umriss, Schatten weiter 4 Ecken.)
- `detect(rect, fmt, hints=None)`: `hints = hints or {}`; `mask, color, diff = _mask(rect, fmt, hints)`; nach `outlines`: `res["contrast"] = round(float(np.mean(diff[mask > 0])) * 100 / 255, 1) if outlines else None` (uint8-Skala auf 0–100; nachgebaut: Grau 150 → 37, Grau 225 → 10,5); `res["hints"] = hints`.
- Kalibrierung: Nach GREEN die bestehenden `tests/test_edges.py` und die vier echten Fotos im Scratchpad mit `draw_candidates` prüfen (Foto 1 ohne Schattensporn unten, mit beiden Fasen oben); Laufzeit `detect` A4/A3 vorher/nachher ins Protokoll (Referenz VM: 0,44–0,70 s A4, 1,28 s A3; die zweite Rasterrunde kostet ca. 35–45 %). Schwellen nur als Konstanten ändern, jede Änderung mit beiden Testläufen belegen.
- **Zeitgrenze 6 h.** Sind `test_schatten_bleibt_aussen` oder `test_transparenter_quader_mit_hinweis` danach nicht grün: Messwerte (Eckenabweichung, Zahl der Komponenten) ins Protokoll, dann Marc per Auswahlfrage entscheiden lassen: (a) Schritt „äußere Kantenkette“ spezifizieren (konvexe Hülle der Gradientenketten über der Rauschschwelle um die Farbmaske, dann `_refine`; +4–8 h), (b) Transparenz-Teil von A2 auf ± 1,5 mm lockern, (c) bei `transparent = 2` nur die Handzeichnung anbieten. Ohne Entscheidung keine weitere Schwellen-Probiererei; die übrigen Tasks laufen unabhängig weiter.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_edges.py tests/test_edges_api.py tests/test_align.py && ruff check core/edges.py tests/`
Expected: PASS, inklusive `test_quader_umriss`, `test_platte_bohrung_innenkante`, `test_heller_koerper_ohne_raster`.

- [ ] **Step 5: Commit**

```bash
git add core/edges.py tests/conftest.py tests/test_edges.py
git commit -m "Kantenerkennung: Schlagschatten ausgeschlossen, Hinweise fuer transparente und helle Teile, Kontrastwert"
```

### Task 3: Fotoart `bottom` im Server, Umriss je Foto, Ausrichtung beim Hochladen

**Files:**
- Modify: `web/app/main.py` (`VIEWS`, `_photo_public`, `_analyze_store`, `_outline_of`, `_align_photo`, `_realign_project`, `photo_upload`, `meas_create`, `/suggest`)
- Modify: `web/app/parts.py` (`reference_top`, `to_top`, Stub `link_bottom`)
- Modify: `tests/test_align.py`

**Interfaces:**
- Consumes: Task 1, Task 2 (`detect(..., hints)`).
- Produces: `parts.reference_top(project_id) -> dict | None`; `parts.to_top(photo_row, pts: list) -> list[list[float]]` (Matrix einmal je Aufruf); `main._analyze_store(phid, img, fmt, view, hints=None)`; `main._outline_of(ph) -> list | None | "timeout"`; `main._align_photo(ph, top)`; `main._realign_project(pid)` (endet mit `parts.link_bottom`; bis Task 5 ein No-op-Stub in parts.py); `_photo_public` liefert `bottom_align`, `align_note`, `bottom_rot_user`, `contrast`, `low_contrast`; Hinweise (`_hints`) kommen erst in Task 12, hier `hints=None`.

- [ ] **Step 1: Failing API-Tests** (an `tests/test_align.py` anhängen)

```python
from conftest import H


def _up(c, pid, objects, view):
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("f.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": view}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


TOP = [{"polygon": L_SHAPE, "gray": 150}, HOLE]


@pytest.fixture()
def pair(user):
    pid = user.post("/api/projects", json={"name": "Lage"}, headers=H).json()["id"]
    t = _up(user, pid, TOP, "top")
    b = _up(user, pid, bottom_of(TOP, 90, -30, 22), "bottom")
    return user, pid, t, b


def test_unteransicht_wird_ausgerichtet(pair):
    c, pid, t, b = pair
    assert b["view"] == "bottom" and b["bottom_align"]["rot"] == 90 and not b["bottom_align"]["unsure"]
    assert b["bottom_align"]["auto"] is True and b["bottom_align"]["top_photo_id"] == t["id"]
    assert b["contrast"] is not None and b["bottom_rot_user"] is None


def test_draufsicht_spaeter(user):
    pid = user.post("/api/projects", json={"name": "Spaet"}, headers=H).json()["id"]
    b = _up(user, pid, bottom_of(TOP, 180), "bottom")
    assert b["bottom_align"] is None and b["align_note"] == "Draufsicht fehlt"
    _up(user, pid, TOP, "top")
    b1 = next(p for p in user.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == b["id"])
    assert b1["bottom_align"]["rot"] == 180


def test_messung_von_unten_und_to_top(pair):
    from app import db, parts
    c, pid, t, b = pair
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": b["id"], "kind": "length", "view": "bottom",
                                                          "points": [[10, 20], [30, 20]]}, headers=H).json()
    assert m["data"]["view"] == "bottom" and m["value"] == pytest.approx(20.0)
    ph = db.q1("SELECT * FROM photos WHERE id=?", (b["id"],))
    hole_b = bottom_of(TOP, 90, -30, 22)[1]["circle"][:2]
    assert parts.to_top(ph, [hole_b])[0] == pytest.approx(HOLE["circle"][:2], abs=0.5)


def test_suggest_nur_draufsicht(pair, monkeypatch):
    from app import ai
    c, pid, t, b = pair
    got, orig = [], ai.call
    monkeypatch.setattr(ai, "call", lambda s, m, **k: (got.append(m), orig(s, m, **k))[1])
    c.post(f"/api/projects/{pid}/suggest", json={"photo_id": b["id"]}, headers=H)
    caps = " ".join(x.get("text", "") for x in got[-1][0]["content"] if x["type"] == "text")
    assert f"Foto {t['id']})" in caps and f"Foto {b['id']})" not in caps
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py -k "ausgerichtet or spaeter or to_top or suggest"`
Expected: FAIL (`view` wird zu `top`, KeyError `bottom_align`).

- [ ] **Step 3: Implementierung**

`web/app/parts.py` (neben `default_unc`; `link_bottom` kommt in Task 5, hier als Stub `def link_bottom(project_id): pass`):

```python
def reference_top(project_id):
    """Referenz-Draufsicht: view='top', rect vorhanden, status gut/brauchbar, kleinste id (Spec §1)."""
    rows = db.q("SELECT * FROM photos WHERE project_id=? AND view='top' AND status IN ('gut','brauchbar') ORDER BY id",
                (project_id,))
    return next((ph for ph in rows if (db.jload(ph["analysis"], {}) or {}).get("rect")), None)


def to_top(photo, pts):
    """Punkte einer Unteransicht (mm) in Draufsicht-Koordinaten; ohne Ausrichtung nur die Spiegelung (rot=0)."""
    from core import vision  # spaet: main.py setzt sys.path erst nach den App-Importen
    a = db.jload(photo["analysis"], {}) or {}
    r = a["rect"]
    al = a.get("bottom_align") or {"rot": 0, "dx": 0.0, "dy": 0.0}
    return vision.apply_lage(vision.lage_matrix(al["rot"], al["dx"], al["dy"], r["w_mm"], r["h_mm"]), pts)
```

`web/app/main.py`:

```python
VIEWS = ("top", "bottom", "tilted", "gauge", "overview")
PLANAR = ("top", "bottom")
ALIGN_PXMM = 4.0
```

`_photo_public(ph)`: nach `"has_edges"`:

```python
            "contrast": a.get("contrast"), "low_contrast": a.get("contrast") is not None and a["contrast"] < 12,
            "bottom_align": a.get("bottom_align") if ph["view"] == "bottom" else None,
            "align_note": a.get("align_note") if ph["view"] == "bottom" else None,
            "bottom_rot_user": a.get("bottom_rot_user"),
```

`_analyze_store(phid, img, fmt, view, hints=None)`: Umriss nur für `view in PLANAR`, unter `_detect_lock` (Zeitlimit 30 s; bei Zeitüberschreitung bleibt `outline_mm` ungesetzt und `_outline_of` holt ihn nach). Nach dem `rect`-Block:

```python
    if a.get("rect") and view in PLANAR and _detect_lock.acquire(timeout=30):
        try:
            res = edges.detect(rect, a["format"], hints)
            a["outline_mm"] = res["outlines"][0]["polygon"] if res["outlines"] else None
            a["contrast"] = res["contrast"]
            a["outline_hints"] = hints or {}
        except Exception:  # noqa: BLE001 – Umriss ist optional
            a["outline_mm"] = None
        finally:
            _detect_lock.release()
```

(Die Dateischleife am Anfang bleibt `("rect.jpg", "gauge.jpg")`.) Aufrufer: `photo_upload` → `_analyze_store(phid, img, fmt, view)`; `photo_patch` (Formatwechsel) → `_analyze_store(phid, img, fmt, ph["view"])`.

Ausrichtung (neu, vor `photo_upload`; nie innerhalb von `db.atomic()`):

```python
def _set_analysis(phid: int, a: dict):
    db.ex("UPDATE photos SET analysis=? WHERE id=?", (db.jdump(a), phid))


def _outline_of(ph: dict):
    """Umriss (mm) aus analysis.outline_mm; sonst nachrechnen (unter _detect_lock). None = keiner, "timeout" = spaeter."""
    a = db.jload(ph["analysis"], {}) or {}
    if "outline_mm" in a:
        return a["outline_mm"]
    rect_path = _photo_dir(ph["id"]) / "rect.jpg"
    if not a.get("rect") or not rect_path.is_file():
        return None
    if not _detect_lock.acquire(timeout=30):
        return "timeout"
    try:
        img = cv2.imread(str(rect_path))
        res = edges.detect(img, ph["format"]) if img is not None else {"outlines": [], "contrast": None}
    except Exception:  # noqa: BLE001 – Umriss ist optional
        res = {"outlines": [], "contrast": None}
    finally:
        _detect_lock.release()
    outline = res["outlines"][0]["polygon"] if res["outlines"] else None
    with db.atomic():  # frisch lesen: ein paralleler Formatwechsel darf nicht ueberschrieben werden
        cur = db.q1("SELECT format, analysis FROM photos WHERE id=?", (ph["id"],))
        if not cur or cur["format"] != ph["format"]:
            return None
        a2 = db.jload(cur["analysis"], {}) or {}
        a2["outline_mm"], a2["contrast"] = outline, res["contrast"]
        _set_analysis(ph["id"], a2)
        ph["analysis"] = db.jdump(a2)
    return outline


def _align_photo(ph: dict, top: dict | None):
    """bottom_align einer Unteransicht neu berechnen (Spec §1 „Wann“); Handwahl (bottom_rot_user) bleibt."""
    ot = _outline_of(top) if top is not None and ph["view"] == "bottom" else None
    ob = _outline_of(ph) if ph["view"] == "bottom" else None
    with db.atomic():
        cur = db.q1("SELECT * FROM photos WHERE id=?", (ph["id"],))
        if not cur:
            return
        a = db.jload(cur["analysis"], {}) or {}
        user_rot = a.get("bottom_rot_user")
        a.pop("bottom_align", None)
        a.pop("align_note", None)
        if cur["view"] == "bottom" and a.get("rect"):
            if top is None:
                a["align_note"] = "Draufsicht fehlt"
            elif ot == "timeout" or ob == "timeout":
                a["align_note"] = "Ausrichtung nicht berechnet – erneut versuchen"
            elif not ot or not ob:
                a["align_note"] = "Umriss nicht erkennbar"   # bottom_align bleibt null: to_top nutzt rot=0 ohne Versatz
            else:
                r = a["rect"]
                al = vision.align_bottom(ot, ob, r["w_mm"], r["h_mm"], rot=user_rot)
                if user_rot is not None:
                    al["unsure"] = False
                a["bottom_align"] = {**al, "auto": user_rot is None, "top_photo_id": top["id"]}
        _set_analysis(cur["id"], a)


def _realign_project(pid: int):
    """Alle Unteransichten eines Projekts neu ausrichten, danach die Teile verknuepfen. Nie in db.atomic()."""
    top = parts.reference_top(pid)
    for ph in db.q("SELECT * FROM photos WHERE project_id=? AND view='bottom'", (pid,)):
        _align_photo(ph, top)
    with db.atomic():
        parts.link_bottom(pid)
```

Auslöser in `photo_upload` (nach dem `UPDATE photos … analysis`): `if view in PLANAR: _realign_project(pid)`.

`meas_create`: `data = {"view": body.view if body.view in ("top", "gauge", "bottom") else "top", …}`.

`/suggest`: in der Schleife `if used_photo is None and ph["view"] == "top" and (d / "rect.jpg").is_file():`.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py tests/test_api.py tests/test_edges_api.py && ruff check web/app/main.py web/app/parts.py tests/test_align.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/main.py web/app/parts.py tests/test_align.py
git commit -m "Fotoart „Von unten“: Umriss je Foto, Ausrichtung zur Referenz-Draufsicht beim Hochladen, Messungen mit view=bottom"
```

### Task 4: Handwahl, Ansichts- und Formatwechsel, Löschen, `align.jpg`

**Files:**
- Modify: `web/app/main.py` (`AlignIn`, `PhotoPatch.bottom_align`, `photo_patch`, `photo_delete`, Route `align.jpg` vor `photo_file`)
- Modify: `web/static/js/photos.js` (nur `VIEW_LABEL.bottom`, damit das `<select>` den Wert kennt; Rest in Task 6)
- Modify: `tests/test_align.py`

**Interfaces:**
- Consumes: Task 3.
- Produces: `PhotoPatch.bottom_align: AlignIn | None` mit `AlignIn.rot: Literal[0, 90, 180, 270] | None`; Semantik: `bottom_align: null` = zurück auf automatisch (löscht `bottom_rot_user`), `{"rot": 90}` = Handwahl, `{}` = mit unveränderter Handwahl neu berechnen (Spec §1 „stößt sie erneut an“); `GET /api/photos/{phid}/align.jpg`.

- [ ] **Step 1: Failing tests**

```python
def _photo(c, pid, phid):
    return next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == phid)


def test_handwahl_und_referenzwechsel(pair):
    from app import db
    c, pid, t, b = pair
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=H).json()
    assert r["bottom_align"]["rot"] == 270 and r["bottom_align"]["auto"] is False and r["bottom_rot_user"] == 270
    assert c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 45}}, headers=H).status_code == 422
    t2 = _up(c, pid, TOP, "top")                                          # zweite Draufsicht, Referenz bleibt t
    assert c.delete(f"/api/photos/{t['id']}", headers=H).status_code == 200
    b2 = _photo(c, pid, b["id"])
    assert b2["bottom_align"]["top_photo_id"] == t2["id"] and b2["bottom_align"]["rot"] == 270   # Handwahl bleibt
    assert c.delete(f"/api/photos/{t2['id']}", headers=H).status_code == 200
    b3 = _photo(c, pid, b["id"])
    assert b3["bottom_align"] is None and "Draufsicht fehlt" in b3["align_note"] and b3["bottom_rot_user"] == 270
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": None}, headers=H).json()   # zurueck auf automatisch
    assert r["bottom_rot_user"] is None
    assert "bottom_rot_user" not in db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (b["id"],))["analysis"])


def test_umschalten_der_ansicht(user):
    pid = user.post("/api/projects", json={"name": "Umschalten"}, headers=H).json()["id"]
    t = _up(user, pid, TOP, "top")
    x = _up(user, pid, bottom_of(TOP, 180), "tilted")
    assert x["bottom_align"] is None
    r = user.patch(f"/api/photos/{x['id']}", json={"view": "bottom"}, headers=H).json()
    assert r["bottom_align"]["rot"] == 180
    r = user.patch(f"/api/photos/{x['id']}", json={"view": "tilted"}, headers=H).json()
    assert r["bottom_align"] is None and r["align_note"] is None
    user.patch(f"/api/photos/{x['id']}", json={"view": "bottom"}, headers=H)
    user.patch(f"/api/photos/{t['id']}", json={"view": "tilted"}, headers=H)                  # Referenz weg
    b = _photo(user, pid, x["id"])
    assert b["bottom_align"] is None and b["align_note"] == "Draufsicht fehlt"


def test_handwahl_nach_formatwechsel(pair):
    c, pid, t, b = pair
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=H)
    c.patch(f"/api/photos/{b['id']}", json={"format": "A3"}, headers=H)
    r = c.patch(f"/api/photos/{b['id']}", json={"format": "A4"}, headers=H).json()
    assert r["bottom_align"]["rot"] == 270 and r["bottom_align"]["auto"] is False


def test_erneut_anstossen(pair):
    c, pid, t, b = pair
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=H)
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {}}, headers=H).json()     # neu rechnen, Handwahl bleibt
    assert r["bottom_align"]["rot"] == 270 and r["bottom_rot_user"] == 270


def test_align_jpg_und_to_top_gleich(pair):
    from app import db, parts
    c, pid, t, b = pair
    r = c.get(f"/api/photos/{b['id']}/align.jpg")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    ph, top = (db.q1("SELECT * FROM photos WHERE id=?", (i,)) for i in (b["id"], t["id"]))
    M = vision.bottom_warp_matrix(db.jload(ph["analysis"]), db.jload(top["analysis"]), 4.0)
    u, v = (M @ np.array([30 * 10.0, (230 - 50) * 10.0, 1.0]))[:2]
    assert (u / 4, 230 - v / 4) == pytest.approx(parts.to_top(ph, [[30, 50]])[0], abs=0.1)


def test_fremder_nutzer_lage(pair, app, admin):
    from fastapi.testclient import TestClient
    c, pid, t, b = pair
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremdl{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.get(f"/api/photos/{b['id']}/align.jpg").status_code == 404
    assert f.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 90}}, headers=H).status_code == 404
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py -k "handwahl or umschalten or formatwechsel or anstossen or align_jpg or fremder"`
Expected: FAIL (422/`bottom_align` unverändert, 404 bei `align.jpg`).

- [ ] **Step 3: Implementierung**

```python
class AlignIn(BaseModel):
    rot: Literal[0, 90, 180, 270] | None = None


class PhotoPatch(BaseModel):
    view: str | None = None
    format: str | None = None
    bottom_align: AlignIn | None = None
```

`photo_patch` (DB-Änderungen in `atomic`, die Ausrichtung danach):

```python
    ph, p = _own_photo(phid, u)
    realign = False
    if body.view in VIEWS and body.view != ph["view"]:
        db.ex("UPDATE photos SET view=? WHERE id=?", (body.view, phid))
        realign = body.view in PLANAR or ph["view"] in PLANAR
        if ph["view"] == "bottom":   # bottom_align/align_note entfernen; bottom_rot_user bleibt fuer ein Zurueckschalten
            _align_photo(db.q1("SELECT * FROM photos WHERE id=?", (phid,)), None)
        ph = db.q1("SELECT * FROM photos WHERE id=?", (phid,))
        with db.atomic():
            _refresh(p)   # Auto-Masse bekommen die neue Ansicht
    if body.format is not None and body.format != ph["format"]:
        img = vision.load_image((_photo_dir(phid) / "orig.jpg").read_bytes())
        a = _analyze_store(phid, img, body.format if body.format in matgen.FORMATS else None, ph["view"])
        with db.atomic():
            old = db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (phid,))["analysis"], {}) or {}
            if old.get("bottom_rot_user") is not None:
                a["bottom_rot_user"] = old["bottom_rot_user"]   # Handwahl ueberlebt den Formatwechsel
            db.ex("UPDATE photos SET format=?, status=?, max_err=?, analysis=? WHERE id=?",
                  (a.get("format"), a["status"], a.get("max_err_mm"), db.jdump(a), phid))
            parts.delete_photo_parts(phid)
            _refresh(p)
            for n in ("edges.json", "edges_ki.jpg"):
                (_photo_dir(phid) / n).unlink(missing_ok=True)
        realign = realign or ph["view"] in PLANAR
    if "bottom_align" in body.model_fields_set:
        if ph["view"] != "bottom":
            raise HTTPException(400, "Nur für Fotos der Ansicht „Von unten“")
        with db.atomic():
            a = db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (phid,))["analysis"], {}) or {}
            if body.bottom_align is None:
                a.pop("bottom_rot_user", None)                       # zurueck auf automatisch
            elif "rot" in body.bottom_align.model_fields_set:
                a["bottom_rot_user"] = body.bottom_align.rot        # Handwahl ({} = nur neu rechnen)
            _set_analysis(phid, a)
        realign = True
    if realign:
        _realign_project(p["id"])
    return _photo_public(db.q1("SELECT * FROM photos WHERE id=?", (phid,)))
```

`photo_delete`: nach dem `with db.atomic()`-Block und `shutil.rmtree` → `_realign_project(p["id"])`.

Route **vor** `photo_file`:

```python
@app.get("/api/photos/{phid}/align.jpg")
def photo_align_jpg(phid: int, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u)
    a = db.jload(ph["analysis"], {}) or {}
    top = parts.reference_top(p["id"])
    img = cv2.imread(str(_photo_dir(phid) / "rect.jpg")) if a.get("rect") else None
    if ph["view"] != "bottom" or img is None or not top:
        raise HTTPException(404, "Keine Ausrichtung vorhanden")
    at = db.jload(top["analysis"], {}) or {}
    out = vision.bottom_warp(img, a, at, ALIGN_PXMM)
    own = parts.to_top(ph, a["outline_mm"]) if a.get("outline_mm") else []
    vision.draw_outlines(out, [at.get("outline_mm"), own], [(12, 65, 194), (178, 60, 20)], ALIGN_PXMM, at["rect"]["h_mm"])
    return Response(vision.encode_jpg(out, 85), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
```

`photos.js`: `VIEW_LABEL = { top: "Draufsicht", bottom: "Von unten", tilted: "Gekippt (Höhe)", gauge: "Höhenlehre", overview: "Übersicht" }`. `Literal` in main.py importieren.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_align.py tests/test_api.py tests/test_parts_api.py tests/test_texts.py && ruff check web/app/main.py tests/test_align.py && node --check web/static/js/photos.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/main.py web/static/js/photos.js tests/test_align.py
git commit -m "Unteransicht: Handwahl der Lage, Neuberechnung bei Ansichts-, Format- und Referenzwechsel, align.jpg"
```

### Task 5: Teile und Maßtabelle mit Unteransicht (`same_as`, „(unten)“)

**Files:**
- Modify: `web/app/parts.py` (`_sync_auto`, `refresh`, `link_bottom`, `part_public`, `cad_text`, `_poly_text`)
- Modify: `web/app/jobs.py` (`top_points`, `measurement_table`)
- Modify: `web/app/main.py` (`_csv`)
- Create: `tests/test_check.py` (Teil „tabelle“)
- Modify: `tests/test_edges_api.py` (`test_cad_auftrag_fuer_ein_teil`)

**Interfaces:**
- Consumes: `parts.to_top`, `parts.reference_top`, `match_parts`, `_realign_project` (Task 3/4).
- Produces: `parts.link_bottom(project_id)` (setzt `data.same_as`, auch `None` für Teile, deren Foto keine Unteransicht mehr ist oder ohne `bottom_align`); `part_public()["same_as"]`, `part_public()["view"]`; `jobs.top_points(m, d, photos) -> tuple[str, list]` (Vermerk `""`, `"(unten)"`, `"(unten, nicht ausgerichtet, links-rechts gespiegelt)"`; Punkte in Draufsicht-Koordinaten); `measurement_table(project_id, part_id)` nimmt Teile mit `same_as == part_id` mit.

- [ ] **Step 1: Failing tests** `tests/test_check.py`:

```python
"""Pruefung vor dem Auftrag, Auftragsnachricht, Tabelle (Spec 2026-10-15 §2, A3–A5, A9)."""
import re

import pytest

from conftest import H, bottom_of, synthetic_photo

L_SHAPE = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 120], [60, 120]]
HOLE = {"circle": [110, 87.5, 5], "gray": 235}
TOP = [{"polygon": L_SHAPE, "gray": 150}, HOLE]
POLY_B = bottom_of(TOP, 90, -30, 22)[0]["polygon"]


def _up(c, pid, objects, view):
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("f.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": view}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _part(c, pid, phid, poly, label):
    r = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "label": label, "polygon": poly}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _parts(c, pid):
    return {x["id"]: x for x in c.get(f"/api/projects/{pid}").json()["parts"]}


@pytest.fixture()
def proj(user):
    pid = user.post("/api/projects", json={"name": "Stufe A"}, headers=H).json()["id"]
    t = _up(user, pid, TOP, "top")
    b = _up(user, pid, bottom_of(TOP, 90, -30, 22), "bottom")
    return user, pid, t, b


def test_tabelle_unten_in_draufsicht_koordinaten(proj):
    from app import jobs
    c, pid, t, b = proj
    pt = _part(c, pid, t["id"], L_SHAPE, "L")
    pb = _part(c, pid, b["id"], POLY_B, "L unten")
    pb = _parts(c, pid)[pb["id"]]
    assert pb["same_as"] == pt["id"] and pb["view"] == "bottom"
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": b["id"], "kind": "length", "view": "bottom",
                                                          "points": [[10, 20], [30, 20]]}, headers=H).json()
    text, rows = jobs.measurement_table(pid)
    line = next(ln for ln in text.splitlines() if ln.startswith(f"| M{m['seq']} "))
    x, y = map(float, re.search(r"\(unten\) \(([-\d.]+), ([-\d.]+)\)", line).groups())
    assert (x, y) == pytest.approx((160.0, 222.0), abs=0.5)        # lage_matrix(90, -30, 22): (10, 20) -> (160, 222)
    text1, rows1 = jobs.measurement_table(pid, pt["id"])
    assert any(r["part_id"] == pb["id"] for r in rows1)              # Einzelteil-Auftrag nimmt das Unteransicht-Teil mit
    auto_lines = [ln for ln in text1.splitlines() if f"| T{pb['seq']} |" in ln]
    assert auto_lines and all("(unten)" in ln for ln in auto_lines)
    csv = c.get(f"/api/projects/{pid}/measurements.csv").text
    assert "(unten)" in csv


def test_same_as_folgt_der_lage(proj):
    c, pid, t, b = proj
    pt = _part(c, pid, t["id"], L_SHAPE, "L")
    pb = _part(c, pid, b["id"], POLY_B, "u")
    assert _parts(c, pid)[pb["id"]]["same_as"] == pt["id"]
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 0}}, headers=H)          # falsche Lage: IoU ~0,25
    assert _parts(c, pid)[pb["id"]]["same_as"] is None
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": None}, headers=H)
    assert _parts(c, pid)[pb["id"]]["same_as"] == pt["id"]
    c.patch(f"/api/photos/{b['id']}", json={"view": "tilted"}, headers=H)
    assert _parts(c, pid)[pb["id"]]["same_as"] is None


def test_unteransicht_auto_masse_und_zuordnung(proj):
    c, pid, t, b = proj
    pb = _part(c, pid, b["id"], POLY_B, "u")
    p = c.get(f"/api/projects/{pid}").json()
    autos = [m for m in p["measurements"] if m["part_id"] == pb["id"] and m["source"] == "auto"]
    assert autos and all(m["data"]["view"] == "bottom" for m in autos)
    cx, cy = bottom_of(TOP, 90, -30, 22)[1]["circle"][:2]
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": b["id"], "kind": "length", "view": "bottom",
                                                          "points": [[cx - 3, cy], [cx + 3, cy]]}, headers=H).json()
    assert m["part_id"] == pb["id"]                                                           # Zuordnung auch bei bottom
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py`
Expected: FAIL (`KeyError: 'same_as'`).

- [ ] **Step 3: Implementierung**

`parts.py` – `link_bottom` (ersetzt den Stub):

```python
def link_bottom(project_id):
    """Unteransicht-Teile mit dem ueberlagerten Teil der Referenz-Draufsicht verknuepfen (Spec §1, same_as)."""
    top = reference_top(project_id)
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}
    rows = db.q("SELECT * FROM parts WHERE project_id=?", (project_id,))
    tops = [(r["id"], _data(r)["polygon"]) for r in rows if top and r["photo_id"] == top["id"]]
    for r in rows:
        ph, d, same = photos.get(r["photo_id"]), _data(r), None
        if ph and ph["view"] == "bottom" and tops and (db.jload(ph["analysis"], {}) or {}).get("bottom_align"):
            same = match_parts(tops, [(r["id"], to_top(ph, d["polygon"]))]).get(r["id"])
        if d.get("same_as") != same:
            d["same_as"] = same
            db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), r["id"]))
```

- `_sync_auto(part, photo, fx, fy)`: `view = "bottom" if photo and photo["view"] == "bottom" else "top"`; Insert `md = {"view": view, …}`, `default_unc(photo, view)`; bei vorhandenen Auto-Maßen `md.update(view=view, points=…, …)`.
- `refresh`: die drei Prüfungen `d.get("view", "top") == "top"` → `in ("top", "bottom")`; am Ende `link_bottom(pid)`.
- `part_public`: `"same_as": d.get("same_as")`, `"view": …` (aus `db.q1("SELECT view FROM photos WHERE id=?")`, Standard `"top"`).
- `cad_text`/`_poly_text` (Spec §2.2; `to_top(photo, pts)` einmal je Polygon):

```python
def _poly_text(part, photo):
    d, unten = _data(part), bool(photo and photo["view"] == "bottom")
    pts = to_top(photo, d["polygon"]) if unten else d["polygon"]
    s = "Umriss (mm) " + " ".join(f"({x:.1f}, {y:.1f})" for x, y in pts)
    if d.get("hidden"):
        s += "; verdeckte Kanten: " + ", ".join(f"K{e}" for e in d["hidden"])
    if d.get("holes"):
        cs = to_top(photo, [h["c"] for h in d["holes"]]) if unten else [h["c"] for h in d["holes"]]
        s += "; Bohrungen: " + ", ".join(f"Ø {h['d']:.1f} bei ({c[0]:.1f}, {c[1]:.1f})"
                                         for h, c in zip(d["holes"], cs, strict=True))
    return s


def cad_text(project_id, part_id=None):
    """Teile fuer die CAD-KI: Umrisse verbindlich (Spec §2.2); Unteransicht-Teile in Draufsicht-Koordinaten."""
    rows = db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (project_id,))
    if not rows:
        return ""
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}
    seq = {r["id"]: r["seq"] for r in rows}

    def where(r):
        ph = photos.get(r["photo_id"])
        if not ph or ph["view"] != "bottom":
            return "Draufsicht"
        same = _data(r).get("same_as")
        tail = f"; derselbe Körper wie T{seq[same]}, kein zusätzliches Teil" if same in seq else ""
        return "von unten, in Draufsicht-Koordinaten" + tail

    def line(r):
        return f"T{r['seq']} „{r['label']}“ ({ROLE_TEXT[r['role']]}, {where(r)}): {_poly_text(r, photos.get(r['photo_id']))}"
    if part_id:
        t = next((r for r in rows if r["id"] == part_id), None)
        if not t:
            return ""
        extra = [line(r) for r in rows if _data(r).get("same_as") == part_id]
        return ("Modelliert wird nur Teil " + line(t) + "." + (" Dazu " + "; ".join(extra) + "." if extra else "")
                + " Maße anderer Teile sind nicht enthalten.")
    return ("Teile im Foto (Umrisse verbindlich): " + "; ".join(line(r) for r in rows)
            + ". Alle Teile als ein Körper modellieren.")
```

`tests/test_edges_api.py::test_cad_auftrag_fuer_ein_teil` anpassen: `assert "Modelliert wird nur Teil T2 „Platte“ (montiertes Teil, Draufsicht): Umriss (mm) (" in text` und `assert "Teile im Foto (Umrisse verbindlich): T1 „Quader“ (Grundkörper, Draufsicht): Umriss (mm) (" in alle`.

`jobs.py` (`from .parts import cad_text, reference_top, to_top`):

```python
def top_points(m: dict, d: dict, photos: dict) -> tuple[str, list]:
    """Punkte einer Messung fuer Tabelle und CSV; Unteransicht in Draufsicht-Koordinaten mit Vermerk."""
    pts = d.get("points") or []
    if d.get("view") != "bottom" or not pts or m["photo_id"] not in photos:
        return "", pts
    ph = photos[m["photo_id"]]
    tag = "(unten)" if (db.jload(ph["analysis"], {}) or {}).get("bottom_align") else \
        "(unten, nicht ausgerichtet, links-rechts gespiegelt)"
    return tag, to_top(ph, pts)
```

`measurement_table`: `photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}`; mit `part_id`: `linked = {r["id"] for r in db.q("SELECT id, data FROM parts WHERE project_id=?", (project_id,)) if (db.jload(r["data"], {}) or {}).get("same_as") == part_id}`, `rows = [m for m in rows if m["part_id"] in (part_id, None) or m["part_id"] in linked]`; je Zeile `tag, pts = top_points(m, d, photos)`, `where = (f"{d.get('view', '')} {tag} " + " ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in pts[:3])).strip()`. `_csv` (main.py): Spalte „Ansicht“ = `f"{d.get('view', '')} {tag}".strip()`, Spalte „Punkte (mm)“ im bisherigen Format `x.2f/y.2f` über die umgerechneten Punkte.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_edges_api.py tests/test_parts_api.py tests/test_align.py tests/test_api.py && ruff check web/app tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/parts.py web/app/jobs.py web/app/main.py tests/test_check.py tests/test_edges_api.py
git commit -m "Teile von unten: same_as-Verknuepfung nach jeder Ausrichtung, Auto-Masse mit view=bottom, Tabelle und CAD-Text in Draufsicht-Koordinaten"
```

### Task 6: Oberfläche Welle 1 (Fotos prüfen, Messen) und Messpunkt am echten Block

**Files:**
- Modify: `web/static/js/photos.js` (Ansichtswahl beim Hochladen, Detail mit `align.jpg` und vier Lagen, „Erneut berechnen“)
- Modify: `web/static/js/measure.js` (`planar()`, Quellen für `bottom`)
- Modify: `web/static/js/edges.js` (`partsPanel`: „unten“ und „= T1“)
- Modify: `web/static/js/cad.js` („Modell für“: Zusatz „(unten)“)

**Interfaces:**
- Consumes: `photo.bottom_align`, `photo.align_note`, `photo.bottom_rot_user`, `part.same_as`, `part.view`; `PATCH bottom_align` mit `null` / `{rot}` / `{}`.

- [ ] **Step 1: photos.js**

Ansichtswahl beim Hochladen: neben `fmtSel` ein `viewSel = h("select", { class: "input", "aria-label": "Ansicht der nächsten Fotos" }, Object.entries(VIEW_LABEL).map(([k, v]) => h("option", { value: k }, v)))` als Feld „Ansicht“ im Kopf; in `send()`: `form.append("view", viewSel.value)`.

Detail einer Unteransicht (`drawDetail`, nach den `note`-Blöcken, `p.view === "bottom" ? alignBox(p) : null`):

```js
const LAGEN = [[0, "seitlich umgedreht"], [180, "nach vorn umgedreht"], [90, "seitlich umgedreht, ¼ gegen den Uhrzeigersinn gedreht"],
  [270, "seitlich umgedreht, ¼ im Uhrzeigersinn gedreht"]];
function alignBox(p) {
  const al = p.bottom_align;
  const patch = async body => { try { await api(`/api/photos/${p.id}`, { method: "PATCH", body }); await reloadProject(); drawDetail(); } catch (e) { fail(e); } };
  const retry = /nicht berechnet/.test(p.align_note || "") ? h("button", { class: "btn sm", onclick: () => patch({ bottom_align: {} }) }, "Erneut berechnen") : null;
  return h("section", { class: "card", style: { gap: "10px" } }, h("h3", {}, "Lage zur Draufsicht"),
    al ? [h("figure", {}, h("img", { src: `/api/photos/${p.id}/align.jpg?v=${al.rot}-${al.dx}-${al.dy}`, alt: "Überlagerung Unteransicht auf Draufsicht" }),
        h("figcaption", {}, `Überlappung ${num(al.iou * 100, 0)} % · ${al.auto ? "automatisch" : "von Hand"}`)),
      al.unsure ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, "Ausrichtung unsicher – bitte prüfen und Lage wählen.")) : null,
      h("div", { class: "seg", role: "group", "aria-label": "Lage" }, LAGEN.map(([r, t]) => h("button", { "aria-pressed": String(al.rot === r), onclick: () => patch({ bottom_align: { rot: r } }) }, t))),
      al.auto ? null : h("button", { class: "btn sm ghost", onclick: () => patch({ bottom_align: null }) }, "Wieder automatisch")]
      : [h("p", { class: "hint" }, p.align_note || "Draufsicht fehlt"), retry]);
}
```

- [ ] **Step 2: measure.js, edges.js, cad.js**

`measure.js`: `const planar = v => v === "top" || v === "bottom";` Alle `view === "top"`-Prüfungen an den Stellen `photoId` (Z. 106), `edges.json`-Abruf (Z. 140), `autoOk` (Z. 513), `partsPanel` (Z. 540), `detectEdges` (Z. 610), Standardquelle (Z. 650) → `planar(...)`. `buildSources`: Quelle mit `view: p.view === "bottom" ? "bottom" : "top"`, Schlüssel `${p.id}:${view}`, Label `… · Von unten` bei `bottom`. Der POST der Messung sendet bereits `view: src.view`. `edges.js` `partsPanel`: nach `ROLE[p.role]`: `p.view === "bottom" ? " · unten" + (p.same_as ? \` = T${(S.project.parts.find(q => q.id === p.same_as) || {}).seq ?? "?"}\` : "") : ""`. `cad.js` „Modell für“: `\`${t.id_label} · ${t.label}${t.view === "bottom" ? " (unten)" : ""}\``.

- [ ] **Step 3: Prüfen**

Run: `for f in web/static/js/*.js; do node --check "$f"; done && node --test tests/js/*.test.mjs && python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: keine Fehler.

Browser-Probe (Scratchpad, Playwright wie `pw/nach.mjs`): Draufsicht und Unteransicht (synthetisch aus `bottom_of`, als JPG) hochladen → Detail zeigt Bild und vier Schaltflächen; Klick „¼ im Uhrzeigersinn“ → `rot` 270; „Wieder automatisch“ → 90; Messseite: Quelle „Von unten“, Teil zeichnen, Seitenleiste zeigt „unten = T1“; Konsole ohne Fehler.

- [ ] **Step 3a: Messpunkt am echten Block** (Scratchpad, nicht im Repo): `align_bottom` mit dem Umriss aus `nasfotos/1_rect.jpg` (`edges.detect`) und den Umrissen der echten Unteransichten (Fotos 5/6 aus der NAS-DB, falls hochgeladen; sonst Simulation: Umriss von Foto 1 gespiegelt und gedreht, mit 3 mm gekürzter Plattenseite). `rot/iou/iou_next/unsure` ins Protokoll. Abnahme: richtige Lage **oder** `unsure=true`, nie falsche Lage mit `unsure=false`. (Im Preflight simuliert: `iou − iou_next = 0,075` bei Schwelle 0,05, also knapp.) Fällt die Probe falsch-sicher aus: `ALIGN_MIN_GAP` auf 0,1 setzen, Tests in Task 1 bleiben grün (Abstand ≥ 0,2), Befund ins Protokoll.

- [ ] **Step 4: Commit und Wellenabschluss** (lokale Suite und CI, siehe Global Constraints)

```bash
git add web/static/js/photos.js web/static/js/measure.js web/static/js/edges.js web/static/js/cad.js
git commit -m "Oberflaeche: Ansicht beim Hochladen, Lage der Unteransicht mit Ueberlagerung, Teile von unten"
```

---

## Welle 2 – Prüfung vor dem Auftrag, Werkstück, Auftragsnachricht

### Task 7: Werkstück-Spalten, Migration, `PATCH /api/projects`

**Files:**
- Modify: `web/app/db.py` (`SCHEMA` projects, `_migrate`)
- Modify: `web/app/main.py` (`ProjectPatch`, `project_patch`, `LIGHT_COLORS`)
- Modify: `web/app/ai.py` (`FINISHES`)
- Modify: `tests/test_parts_api.py` (`test_migration_werkstueck`), `tests/test_check.py`

**Interfaces:**
- Produces: Spalten `projects.color, material, transparent, finish, material_user, cad_check`; `ai.FINISHES = ("matt", "glaenzend")` (main.py nutzt `ai.FINISHES`); `main.LIGHT_COLORS = {"weiß", "weiss", "silber", "hellgrau", "beige", "natur"}`; `ProjectPatch.color/material/transparent/finish/clear_material`.

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
        db._migrate(db.conn())                                                  # zweiter Start aendert nichts
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
    body = {"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt"}
    r = c.patch(f"/api/projects/{pid}", json=body, headers=H).json()
    assert (r["color"], r["material"], r["transparent"], r["finish"], r["material_user"]) == ("silber", "Aluminium", 1, "matt", 1)
    assert c.patch(f"/api/projects/{pid}", json={"transparent": 5}, headers=H).status_code == 422
    assert c.patch(f"/api/projects/{pid}", json={"finish": "rau"}, headers=H).status_code == 400
    r = c.patch(f"/api/projects/{pid}", json={"clear_material": True}, headers=H).json()
    assert r["material"] is None and r["material_user"] == 0
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_parts_api.py -k migration_werkstueck tests/test_check.py -k werkstueck`
Expected: FAIL.

- [ ] **Step 3: Implementierung**

`db.py` SCHEMA `projects`: `…, ctrl_x REAL, ctrl_y REAL, color TEXT, material TEXT, transparent INTEGER, finish TEXT, material_user INTEGER NOT NULL DEFAULT 0, cad_check TEXT`. `_migrate`:

```python
    pcols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    for col, typ in (("color", "TEXT"), ("material", "TEXT"), ("transparent", "INTEGER"), ("finish", "TEXT"),
                     ("material_user", "INTEGER NOT NULL DEFAULT 0"), ("cad_check", "TEXT")):
        if col not in pcols:
            c.execute(f"ALTER TABLE projects ADD COLUMN {col} {typ}")
```

`ai.py`: `FINISHES = ("matt", "glaenzend")`. `main.py`: `LIGHT_COLORS = {"weiß", "weiss", "silber", "hellgrau", "beige", "natur"}`; `ProjectPatch` + `color: str | None = Field(default=None, max_length=40)`, `material` ebenso, `transparent: int | None = Field(default=None, ge=0, le=2)`, `finish: str | None = Field(default=None, max_length=20)`, `clear_material: bool = False`. In `project_patch` (innerhalb `atomic`): `if body.finish is not None and body.finish not in ai.FINISHES: raise HTTPException(400, "Oberfläche: matt oder glaenzend")`; `if body.clear_material: db.ex("UPDATE projects SET color=NULL, material=NULL, transparent=NULL, finish=NULL, material_user=0 WHERE id=?", (pid,))`; dann `for k in ("color", "material", "transparent", "finish"): v = getattr(body, k); if v is not None: db.ex(f"UPDATE projects SET {k}=?, material_user=1 WHERE id=?", ((v.strip() or None) if isinstance(v, str) else v, pid))` (feste Spaltenliste). `_project_public` liefert die Spalten über `dict(p)`; `cad_check` wird in Task 10 aufbereitet (bis dahin `out["cad_check"] = None`).

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_parts_api.py tests/test_check.py && ruff check web/app tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/db.py web/app/main.py web/app/ai.py tests/test_parts_api.py tests/test_check.py
git commit -m "Werkstueck-Felder am Projekt (Farbe, Material, Transparenz, Oberflaeche) mit Migration"
```

### Task 8: KI-Schicht: `CHECK_SYSTEM`, `parse_check`, Temperatur, Regeln 8 bis 10

**Files:**
- Modify: `web/app/ai.py`
- Modify: `web/app/jobs.py` (`ai.call(…, temperature=0.0)` in `_run`)
- Modify: `tests/test_check.py`

**Interfaces:**
- Produces: `ai.CHECK_SYSTEM`; `ai.CHECK_KINDS`; `ai.parse_check(text) -> {"items": [...], "material": dict | None}`; `ai._json_span(text, lo, hi) -> str | None` (gemeinsamer Helfer für `_json_array`/`_json_object`); `ai.call(..., temperature: float | None = None)`; `_fake` antwortet auf `CHECK_SYSTEM`.

- [ ] **Step 1: Failing tests** (`tests/test_check.py`)

```python
def test_parse_check_defensiv():
    from app import ai
    txt = ('Hier: {"items": [{"kind": "hoehe", "text": "' + "x" * 300 + '"}, {"kind": "bottom", "severity": "block", "text": 5},'
           ' {"kind": "height", "severity": "block", "text": "Höhe\\n fehlt"}],'
           ' "material": {"color": "silber", "transparent": 7, "finish": "rau", "note": ["x"]}}')
    r = ai.parse_check(txt)
    assert r["items"] == [{"kind": "other", "severity": "warn", "text": "x" * 200},
                          {"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    assert r["material"] == {"color": "silber", "material": None, "transparent": None, "finish": None, "note": ""}
    assert ai.parse_check("[]")["items"] == [] and ai.parse_check("kein json")["material"] is None


def test_prompt_regeln():
    from app import ai
    assert "ist verbindlich" in ai.CAD_SYSTEM and "Innenbohrungen" in ai.CAD_SYSTEM
    assert "so einfach wie möglich" not in ai.CAD_SYSTEM
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

`CAD_SYSTEM` – Eingaben ergänzen:
```
- Ggf. eine Unteransicht (entzerrt, gespiegelt auf Draufsicht-Koordinaten: Bohrungen von unten und oben liegen
  übereinander) und Schrägansichten ohne Maßstab (nur für Form, Seitenflächen und Höhenverhältnis).
- Eine Zeile „Fotografiertes Original“ (Farbe, Material, Transparenz, Oberfläche des Teils – nicht das
  Fertigungsmaterial) und ggf. „Offene Punkte der Prüfung“.
```
Regel 8 ersetzen, 9 und 10 anfügen (Zeilen ≤ 130 Zeichen, Umbrüche an Wortgrenzen):
```
8. Der Umriss aus der Draufsicht (Teile-Polygone) ist verbindlich: Fasen, Stufen, Absätze und Bohrungen daraus
   nachbilden. Fehlt ein Maß (z. B. die Höhe einer Stufe), schätze es, kennzeichne es als Annahme und nenne es in
   `check_before_manufacturing`. Weglassen ist nur erlaubt, was kleiner als 0,5 mm ist. Laufzeit unter 60 Sekunden.
9. Bei transparenten oder teiltransparenten Teilen sind durchscheinende Strukturen Innenbohrungen oder Innenkonturen,
   keine Rillen oder Nuten der Oberfläche. Bohrungen von unten und oben an derselben Stelle sind in der Regel ein
   Loch (ggf. Stufenloch).
10. Zu jedem offenen Punkt der Prüfung steht in `assumptions`, was angenommen wurde.
```

```python
CHECK_SYSTEM = """Du prüfst vor dem CAD-Modellieren, ob die Unterlagen reichen. Du bekommst dieselben Fotos und Maße
wie der Konstrukteur: entzerrte Draufsicht (Maßstab steht dabei), ggf. Unteransicht (gespiegelt auf
Draufsicht-Koordinaten), Höhenlehre, Schrägansichten ohne Maßstab, Messtabelle, Teile-Umrisse.

Nenne, was zum vollständigen Nachbilden fehlt oder unsicher ist, je Punkt mit Art und Stufe:
kind: height (Höhe/Dicke unbekannt), bottom (Unterseite fehlt oder unklar), photo (weiteres Foto nötig, z. B.
Seite), measure (ein Maß fehlt oder widerspricht), sharpness (Kante unscharf, verdeckt oder im Schatten), other.
severity: block = ohne diese Angabe wird das Modell geraten; warn = die Genauigkeit leidet.
Jeder Text sagt, was der Nutzer tun soll (z. B. „Höhenlehre fotografieren oder Höhe als Maß eingeben“).
Höchstens 8 Punkte, keine Punkte zu Dingen, die schon in der Messtabelle stehen.

Schätze außerdem das fotografierte Teil: color (ein Wort, z. B. silber, schwarz, weiß), material (z. B. Aluminium,
Stahl, Kunststoff, Holz, Glas), transparent (0 nein, 1 teilweise, 2 ja), finish (matt oder glaenzend), note (ein Satz).

Antworte ausschließlich mit einem JSON-Objekt:
{"items": [{"kind": "height", "severity": "block", "text": "…"}],
 "material": {"color": "…", "material": "…", "transparent": 0, "finish": "matt", "note": "…"}}"""

CHECK_KINDS = ("height", "bottom", "photo", "measure", "sharpness", "other")
FINISHES = ("matt", "glaenzend")


def _json_span(text: str, lo: str, hi: str) -> str | None:
    t = text.strip()
    m = _BLOCK.search(t)
    if m:
        t = m.group(2)
    i, j = t.find(lo), t.rfind(hi)
    return t[i:j + 1] if i >= 0 and j >= i else None


def _json_array(text: str, what: str) -> list:
    span = _json_span(text, "[", "]")
    if span is None:
        raise AIError(f"Die Antwort enthielt keine {what}.")
    try:
        return json.loads(span)
    except ValueError as e:
        raise AIError(f"Die {what} war kein gültiges JSON.") from e


def _json_object(text: str) -> dict | None:
    span = _json_span(text, "{", "}")
    try:
        o = json.loads(span) if span else None
    except (ValueError, RecursionError):
        return None
    return o if isinstance(o, dict) else None


def parse_check(text: str) -> dict:
    """Pruefergebnis defensiv lesen (Spec §2.1): unbekannte Art -> other, fehlende Stufe -> warn, Texte einzeilig."""
    o = _json_object(text) or {}
    items = []
    for it in o.get("items") if isinstance(o.get("items"), list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("text"), str) or not it["text"].strip():
            continue
        items.append({"kind": it.get("kind") if it.get("kind") in CHECK_KINDS else "other",
                      "severity": it.get("severity") if it.get("severity") in ("block", "warn") else "warn",
                      "text": " ".join(it["text"].split())[:200]})
        if len(items) == 8:
            break
    mat, material = o.get("material"), None
    if isinstance(mat, dict):
        tr = mat.get("transparent")
        material = {"color": _text(mat.get("color"), 40) or None, "material": _text(mat.get("material"), 40) or None,
                    "transparent": tr if tr in (0, 1, 2) else None,
                    "finish": mat.get("finish") if mat.get("finish") in FINISHES else None,
                    "note": _text(mat.get("note"), 300)}
    return {"items": items, "material": material}
```

`call`: Signatur `…, on_progress=None, temperature: float | None = None`; `extra = {} if temperature is None else {"temperature": temperature}`; `client().messages.stream(model=…, max_tokens=…, system=…, messages=…, **extra)`. `_fake`: neuer Zweig vor `SUGGEST_SYSTEM`:

```python
    if system == CHECK_SYSTEM:
        return json.dumps({"items": [
            {"kind": "height", "severity": "block",
             "text": "Höhe des Grundkörpers unbekannt – Höhenlehre fotografieren oder Höhe als Maß eingeben."},
            {"kind": "bottom", "severity": "warn", "text": "Unterseite fehlt – Teil umdrehen und als „Von unten“ hochladen."}],
            "material": {"color": "silber", "material": "Aluminium", "transparent": 0, "finish": "matt", "note": "Testmodus"}},
            ensure_ascii=False), usage
```

`jobs._run`: `ai.call(ai.CAD_SYSTEM, msgs, cancel=ev, on_progress=lambda n: None, temperature=0.0)`.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_texts.py tests/test_api.py tests/test_edges_api.py && ruff check web/app tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/ai.py web/app/jobs.py tests/test_check.py
git commit -m "KI: Pruef-Prompt und parse_check, Temperatur 0 fuer CAD-Auftraege, verbindlicher Umriss als Regel"
```

### Task 9: Bildauswahl, `rect_top.jpg`, `small.jpg`, Auftragsnachricht mit Werkstück und Prüfpunkten

**Files:**
- Modify: `web/app/jobs.py` (`pick_images`, `_small`, `_rect_top`, `_write_atomic`, `material_line`, `build_initial_message`)
- Modify: `web/app/main.py` (`CheckItem`, `JobIn.check_items`, `JobIn.photo_ids` max 30, Übergabe in `jobs.create`)
- Modify: `web/static/js/cad.js` (nur `usable`/`picked` für Schrägfotos; Rest in Task 11)
- Modify: `tests/test_check.py`

**Interfaces:**
- Produces: `jobs.pick_images(project_id, photo_ids) -> list[dict]` mit `{photo_id, kind: "top"|"bottom"|"gauge"|"tilted", path, caption}`; `jobs.material_line(project) -> str`; `build_initial_message(project, text, options)` versteht `options["for_check"]`, `options["check_items"]`, `options["images"]` (vorgewählte Liste, sonst `pick_images`); `main.CheckItem`.

- [ ] **Step 1: Failing tests** (`tests/test_check.py`)

```python
def test_nachricht_bilder_und_text(proj):
    from app import db, jobs
    c, pid, t, b = proj
    g = _up(c, pid, TOP, "tilted")
    for _ in range(4):
        _up(c, pid, TOP, "top")
    c.patch(f"/api/projects/{pid}", json={"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt"}, headers=H)
    imgs = jobs.pick_images(pid, None)
    assert [i["kind"] for i in imgs] == ["top"] * 5 + ["bottom"]     # 5 Draufsichten + 1 unten + 1 gekippt -> 6, gekippt faellt weg
    imgs = jobs.pick_images(pid, [t["id"], b["id"], g["id"]])
    assert [i["kind"] for i in imgs] == ["top", "bottom", "tilted"]
    assert imgs[1]["path"].name == "rect_top.jpg" and "gespiegelt auf Draufsicht-Koordinaten" in imgs[1]["caption"]
    assert imgs[2]["path"].name == "small.jpg" and "Schrägansicht" in imgs[2]["caption"] and imgs[2]["path"].is_file()
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    items = [{"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    opts = {"photo_ids": [t["id"], b["id"], g["id"]], "name": "x", "check_items": items}
    text = jobs.build_initial_message(project, "Nachbauen", opts)[0]["content"][0]["text"]
    assert "Fotografiertes Original (nicht das Fertigungsmaterial): silber, Aluminium, transparent: teilweise, matt" in text
    assert "## Offene Punkte der Prüfung\n- [block] Höhe fehlt" in text
    chk = jobs.build_initial_message(project, "", {"photo_ids": None, "part_id": None, "for_check": True, "process": "cnc", "cutter_d": 6})
    assert "Fräser" not in chk[0]["content"][0]["text"] and "Wunsch des Nutzers" not in chk[0]["content"][0]["text"]
    db.ex("UPDATE projects SET material_user=0 WHERE id=?", (pid,))
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    chk = jobs.build_initial_message(project, "", {"photo_ids": None, "for_check": True})
    assert "Fotografiertes Original" not in chk[0]["content"][0]["text"]            # KI-Schaetzung nicht zurueckfuettern
    assert "Fotografiertes Original" in jobs.build_initial_message(project, "x", {"photo_ids": None})[0]["content"][0]["text"]


def test_nachricht_ohne_draufsicht(user):
    from app import jobs
    pid = user.post("/api/projects", json={"name": "Nur unten"}, headers=H).json()["id"]
    _up(user, pid, bottom_of(TOP, 0), "bottom")
    imgs = jobs.pick_images(pid, None)
    assert [i["kind"] for i in imgs] == ["bottom"] and "nicht ausgerichtet, links-rechts gespiegelt" in imgs[0]["caption"]


def test_auftrag_mit_check_items(proj):
    from app import db
    c, pid, t, b = proj
    items = [{"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    r = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "x", "check_items": items}, headers=H)
    assert r.status_code == 200, r.text
    msgs = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (r.json()["id"],))["messages"])
    assert "- [block] Höhe fehlt" in msgs[0]["content"][0]["text"]
    bad = [{"kind": "x", "severity": "block", "text": "t"}]
    assert c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "x", "check_items": bad}, headers=H).status_code == 422
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py -k "nachricht or check_items"`
Expected: FAIL (`pick_images` fehlt).

- [ ] **Step 3: Implementierung**

`jobs.py` (`import cv2`, `import os`, `import threading` auf Modulebene; `vision` funktionslokal):

```python
TRANSPARENT_TEXT = {0: "nein", 1: "teilweise", 2: "ja"}


def material_line(project: dict) -> str:
    tr = project.get("transparent")
    bits = [project.get("color"), project.get("material"),
            f"transparent: {TRANSPARENT_TEXT[tr]}" if tr in TRANSPARENT_TEXT else None, project.get("finish")]
    bits = [b for b in bits if b]
    return f"Fotografiertes Original (nicht das Fertigungsmaterial): {', '.join(bits)}" if bits else ""


def _write_atomic(path: Path, data: bytes):
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _small(pdir: Path) -> Path | None:
    out = pdir / "small.jpg"
    if not out.is_file():
        if not (pdir / "orig.jpg").is_file():
            return None
        _write_atomic(out, ai.prepare_image(pdir / "orig.jpg")[0])
    return out


def _rect_top(ph: dict, top: dict | None) -> Path | None:
    """Unteransicht in Draufsicht-Koordinaten, bei jedem Aufbau neu (kein veralteter Zwischenspeicher)."""
    from core import vision  # spaet: main.py setzt sys.path erst nach den App-Importen
    pdir = config.DATA_DIR / "photos" / str(ph["id"])
    img = cv2.imread(str(pdir / "rect.jpg"))
    if img is None:
        return None
    a = db.jload(ph["analysis"], {}) or {}
    at = db.jload(top["analysis"], {}) if top and a.get("bottom_align") else None
    out = pdir / "rect_top.jpg"
    _write_atomic(out, vision.encode_jpg(vision.bottom_warp(img, a, at), 90))
    return out


def pick_images(project_id: int, photo_ids: list[int] | None) -> list[dict]:
    """Bilder fuer die KI (Spec §2.2): Draufsicht, Unteransicht, Hoehenlehre, Schraegfotos; hoechstens 6."""
    from core import vision  # spaet: siehe oben
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (project_id,))
              if photo_ids is None or p["id"] in photo_ids]
    top = reference_top(project_id)
    groups: dict[str, list[dict]] = {"top": [], "bottom": [], "gauge": [], "tilted": []}
    for p in photos:
        pdir = config.DATA_DIR / "photos" / str(p["id"])
        a = db.jload(p["analysis"], {}) or {}
        if p["view"] == "top" and (pdir / "rect.jpg").is_file():
            cap = ai.scaled_caption(pdir / "rect.jpg", f"Foto {p['id']} (Draufsicht), entzerrt auf die Unterlage",
                                    vision.PX_PER_MM)
            groups["top"].append({"photo_id": p["id"], "kind": "top", "path": pdir / "rect.jpg", "caption": cap})
        elif p["view"] == "bottom" and a.get("rect"):
            path = _rect_top(p, top)
            if path:
                tag = ("entzerrt und gespiegelt auf Draufsicht-Koordinaten – Bohrungen von unten und oben liegen übereinander"
                       if a.get("bottom_align") else "entzerrt, nicht ausgerichtet, links-rechts gespiegelt")
                cap = ai.scaled_caption(path, f"Foto {p['id']} (von unten), {tag}", vision.PX_PER_MM)
                groups["bottom"].append({"photo_id": p["id"], "kind": "bottom", "path": path, "caption": cap})
        elif p["view"] in ("tilted", "overview"):
            path = _small(pdir)
            if path:
                cap = (f"Foto {p['id']}, Schrägansicht – nicht entzerrt, kein Maßstab; "
                       "nur für Form, Seitenflächen und Höhenverhältnis.")
                groups["tilted"].append({"photo_id": p["id"], "kind": "tilted", "path": path, "caption": cap})
        if (pdir / "gauge.jpg").is_file():
            cap = ai.scaled_caption(pdir / "gauge.jpg", f"Foto {p['id']}, entzerrte Höhenlehre (x −100…100 mm, y ab −10 mm)",
                                    vision.PX_PER_MM)
            groups["gauge"].append({"photo_id": p["id"], "kind": "gauge", "path": pdir / "gauge.jpg", "caption": cap})
    return (groups["top"] + groups["bottom"] + groups["gauge"] + groups["tilted"])[:6]
```

`build_initial_message`: `ml = material_line(project)`; nach der Kopfzeile einfügen, wenn `ml and (not options.get("for_check") or project.get("material_user"))`. Bei `options.get("for_check")` entfallen „Fertigung“, „Wunsch des Nutzers“, Fräser, Aufspannungen, Passungen, Toleranz, Zusatzwünsche. Nach „## Wunsch des Nutzers“ bei `options.get("check_items")`: `"", "## Offene Punkte der Prüfung", *[f"- [{i['severity']}] {i['text']}" for i in options["check_items"]]`. Bilder: `for im in options.get("images") or pick_images(project["id"], photo_ids): content += ai.image_ref(im["path"], im["caption"])` (alte Schleife ersetzen). `_analyze_store` löscht **nicht** `rect_top.jpg`/`small.jpg`.

`main.py`:

```python
class CheckItem(BaseModel):
    kind: Literal[*ai.CHECK_KINDS]
    severity: Literal["block", "warn"]
    text: str = Field(max_length=200)

    @field_validator("text")
    @classmethod
    def _einzeilig(cls, v: str) -> str:
        return " ".join(v.split())
```

`JobIn`: `photo_ids: list[int] | None = Field(default=None, max_length=30)`, `check_items: list[CheckItem] = Field(default=[], max_length=8)`; in `job_create` Optionen um `"check_items": [i.model_dump() for i in body.check_items]`. (`from pydantic import field_validator`.)

`cad.js` (Fotoauswahl): `const usable = P.photos.filter(p => p.files.includes("rect") || p.files.includes("gauge") || ((p.view === "tilted" || p.view === "overview") && p.files.includes("orig")));`, `picked` mit `.slice(0, 6)`, Bildquelle `${p.files.includes("rect") ? "rect" : p.files.includes("gauge") ? "gauge" : "thumb"}.jpg`.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_edges_api.py tests/test_api.py && ruff check web/app tests && node --check web/static/js/cad.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/jobs.py web/app/main.py web/static/js/cad.js tests/test_check.py
git commit -m "Auftragsnachricht: Bildauswahl nach Ansicht (max. 6), Unteransicht gespiegelt, Schraegfotos im Original, Werkstueck und Pruefpunkte"
```

### Task 10: Endpunkt `POST /api/projects/{pid}/cad-check`, Hash, Idempotenz, Materialübernahme

**Files:**
- Create: `web/app/check.py` (`cad_hash`, `stored`, `public_check`, `run_check`, `lock_for`)
- Modify: `web/app/main.py` (Route, `_ai_uses_today`, `_project_public`)
- Modify: `tests/test_check.py`

**Interfaces:**
- Consumes: `jobs.build_initial_message(for_check, images)`, `jobs.pick_images`, `ai.CHECK_SYSTEM`, `ai.parse_check`, `ai.call(temperature=0.0)`.
- Produces: `check.cad_hash(project, photo_ids, part_id) -> str`; `check.run_check(project, photo_ids, part_id, h) -> dict`; `check.public_check(project) -> dict | None` (mit `stale`); `check.lock_for(pid) -> threading.Lock`; `_project_public(detail=True)["cad_check"]`; Antwort `409` bei laufender Prüfung desselben Projekts.

- [ ] **Step 1: Failing tests**

```python
def test_cad_check_testmodus(proj, monkeypatch):
    from app import ai
    c, pid, t, b = proj
    calls, orig = [], ai.call
    monkeypatch.setattr(ai, "call", lambda *a, **k: (calls.append(k), orig(*a, **k))[1])
    r = c.post(f"/api/projects/{pid}/cad-check", json={"photo_ids": None, "part_id": None}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [(i["kind"], i["severity"]) for i in j["items"]] == [("height", "block"), ("bottom", "warn")]
    assert j["material"]["material"] == "Aluminium" and [i["kind"] for i in j["images"]] == ["top", "bottom"]
    assert calls[-1]["temperature"] == 0.0 and j["stale"] is False
    p = c.get(f"/api/projects/{pid}").json()
    assert p["material"] == "Aluminium" and p["material_user"] == 0 and p["cad_check"]["stale"] is False
    n = len(calls)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()["hash"] == j["hash"] and len(calls) == n
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    assert len(calls) == n + 1
    assert c.get("/api/projects", headers=H).json()[0]["cad_check"] is None            # Liste ohne Hash-Rechnung


def test_idempotent_nach_schaetzung_und_handeingabe(proj):
    c, pid, t, b = proj
    j = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is False      # KI-Schaetzung veraltet die Pruefung nicht
    c.patch(f"/api/projects/{pid}", json={"material": "Stahl"}, headers=H)
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is True       # Handeingabe schon
    j2 = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    assert j2["hash"] != j["hash"] and c.get(f"/api/projects/{pid}").json()["material"] == "Stahl"


def test_hash_aufgeloeste_fotos(proj):
    c, pid, t, b = proj
    j = c.post(f"/api/projects/{pid}/cad-check", json={"photo_ids": None}, headers=H).json()
    _up(c, pid, TOP, "top")
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is True
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()["hash"] != j["hash"]


def test_cad_check_tageslimit(proj):
    from app import db
    c, pid, t, b = proj
    uid = c.get("/api/me").json()["user"]["id"]
    c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H)
    for _ in range(30):
        db.audit("cad_check", "Test", user_id=uid)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 200    # gleicher Hash: gespeichert
    _up(c, pid, TOP, "top")                                                                  # neuer Hash
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 429
    assert c.post(f"/api/projects/{pid}/suggest", json={}, headers=H).status_code == 429     # zaehlt mit


def test_ki_schaetzung_ersetzt_und_null(proj, monkeypatch):
    from app import ai
    c, pid, t, b = proj
    c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H)                              # Aluminium/silber
    monkeypatch.setattr(ai, "call", lambda *a, **k: ('{"items": [], "material": {"material": "Stahl", "transparent": 9}}', {}))
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    p = c.get(f"/api/projects/{pid}").json()
    assert (p["material"], p["color"], p["transparent"], p["finish"]) == ("Stahl", None, None, None)
    monkeypatch.setattr(ai, "call", lambda *a, **k: ('{"items": []}', {}))
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    assert c.get(f"/api/projects/{pid}").json()["material"] == "Stahl"                     # material fehlt -> unveraendert


def test_handeingabe_waehrend_pruefung_bleibt(proj, monkeypatch):
    from app import ai, db
    c, pid, t, b = proj
    orig = ai.call

    def call(*a, **k):
        db.ex("UPDATE projects SET material='Stahl', material_user=1 WHERE id=?", (pid,))
        return orig(*a, **k)
    monkeypatch.setattr(ai, "call", call)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 200
    p = c.get(f"/api/projects/{pid}").json()
    assert p["material"] == "Stahl" and p["material_user"] == 1


def test_pruefung_laeuft_bereits(proj):
    from app import check
    c, pid, t, b = proj
    with check.lock_for(pid):
        assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 409


def test_temperatur_je_aufruf(proj, monkeypatch):
    from app import ai
    c, pid, t, b = proj
    seen, orig = [], ai.call
    monkeypatch.setattr(ai, "call", lambda s, *a, **k: (seen.append((s, k.get("temperature"))), orig(s, *a, **k))[1])
    c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H)
    c.post(f"/api/projects/{pid}/suggest", json={}, headers=H)
    c.post(f"/api/photos/{t['id']}/edges", json={"use_ai": True}, headers=H)
    d = dict(seen)
    assert d[ai.CHECK_SYSTEM] == 0.0 and d[ai.SUGGEST_SYSTEM] is None and d[ai.PARTS_SYSTEM] is None


def test_fremder_nutzer_stufe_a(proj, app, admin):
    from fastapi.testclient import TestClient
    c, pid, t, b = proj
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremda{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 404
    assert f.patch(f"/api/projects/{pid}", json={"material": "x"}, headers=H).status_code == 404
    own = f.post("/api/projects", json={"name": "f"}, headers=H).json()["id"]
    r = f.post(f"/api/projects/{own}/cad-check", json={"photo_ids": [t["id"], b["id"]]}, headers=H).json()
    assert r["images"] == [] and r["photo_ids"] == []                                       # fremde Fotos ignoriert
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py -k "cad_check or idempotent or hash_auf or ersetzt or waehrend or laeuft or je_aufruf or fremder"`
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
    """Pruefsumme des Projektstands; photo_ids=None = alle Fotos zum Zeitpunkt der Berechnung (Spec §2.1)."""
    pid = project["id"]
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,))
              if photo_ids is None or p["id"] in photo_ids]
    al = []
    for p in photos:
        b = (db.jload(p["analysis"], {}) or {}).get("bottom_align") or {}
        al.append([p["id"], p["view"], p["format"], p["status"], b.get("rot"), _r(b.get("dx")), _r(b.get("dy"))])
    ms = []
    for m in db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY id", (pid,)):
        d = db.jload(m["data"], {}) or {}
        ms.append([m["id"], m["kind"], _r(m["value"]), _r(m["caliper"]), _r(m["unc"]), m["part_id"], d.get("view"),
                   [[_r(x), _r(y)] for x, y in d.get("points") or []]])
    ps = []
    for t in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY id", (pid,)):
        d = db.jload(t["data"], {}) or {}
        ps.append([t["id"], t["label"], t["role"], [[_r(x), _r(y)] for x, y in d["polygon"]], d.get("hidden"),
                   d.get("holes"), d.get("same_as")])
    mat = ([project.get("color"), project.get("material"), project.get("transparent"), project.get("finish")]
           if project.get("material_user") else None)
    blob = json.dumps({"photos": al, "meas": ms, "parts": ps, "part_id": part_id, "material": mat}, sort_keys=True,
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def stored(project: dict) -> dict | None:
    return db.jload(project.get("cad_check"), None)


def public_check(project: dict) -> dict | None:
    s = stored(project)
    if not s:
        return None
    return {**s, "stale": cad_hash(project, s.get("photo_ids"), s.get("part_id")) != s.get("hash")}


def run_check(project: dict, photo_ids: list[int] | None, part_id: int | None, h: str) -> dict:
    """KI-Aufruf, Ergebnis speichern, Material uebernehmen (nur solange material_user=0 – auch wenn die
    Handeingabe waehrend des Aufrufs kam)."""
    pid = project["id"]
    picked = jobs.pick_images(pid, photo_ids)
    msgs = jobs.build_initial_message(project, "", {"photo_ids": photo_ids, "part_id": part_id, "for_check": True,
                                                    "images": picked})
    text, _ = ai.call(ai.CHECK_SYSTEM, msgs, max_tokens=2000, temperature=0.0)
    res = ai.parse_check(text)
    out = {"items": res["items"], "material": res["material"],
           "images": [{"photo_id": i["photo_id"], "kind": i["kind"]} for i in picked],
           "photo_ids": photo_ids, "part_id": part_id, "hash": h, "checked_at": db.now()}
    with db.atomic():
        if res["material"]:
            m = res["material"]
            db.ex("UPDATE projects SET color=?, material=?, transparent=?, finish=? WHERE id=? AND material_user=0",
                  (m["color"], m["material"], m["transparent"], m["finish"], pid))
        db.ex("UPDATE projects SET cad_check=? WHERE id=?", (db.jdump(out), pid))
    return out
```

`main.py` (`from . import check`):

```python
class CheckIn(BaseModel):
    photo_ids: list[int] | None = Field(default=None, max_length=30)
    part_id: int | None = None
    force: bool = False


@app.post("/api/projects/{pid}/cad-check")
def cad_check(pid: int, body: CheckIn, request: Request, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if body.part_id is not None and not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?", (body.part_id, pid)):
        raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
    photo_ids = body.photo_ids
    if photo_ids is not None:
        own = {r["id"] for r in db.q("SELECT id FROM photos WHERE project_id=?", (pid,))}
        photo_ids = sorted(set(photo_ids) & own)
    lock = check.lock_for(pid)
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "Prüfung läuft bereits – Ergebnis folgt gleich.")
    try:
        p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
        h = check.cad_hash(p, photo_ids, body.part_id)
        s = check.stored(p)
        if s and s.get("hash") == h and not body.force:
            return {**s, "stale": False}
        if not settings.ai_enabled():
            raise HTTPException(503, "KI ist nicht eingerichtet (Verwaltung → Einstellungen).")
        with db.atomic():
            if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
                raise HTTPException(429, f"Tageslimit für KI-Funktionen erreicht ({AI_DAILY_LIMIT}).")
            db.audit("cad_check", f"Projekt {pid}", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
        try:
            out = check.run_check(p, photo_ids, body.part_id, h)
        except ai.AIError as e:
            raise HTTPException(502, str(e)) from None
    finally:
        lock.release()
    return {**out, "stale": False}
```

`_ai_uses_today`: `action IN ('suggest','edges_ai','cad_check')`. `_project_public`: `out["cad_check"] = check.public_check(p) if detail else None`.

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_check.py tests/test_edges_api.py tests/test_auth.py && ruff check web/app tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/check.py web/app/main.py tests/test_check.py
git commit -m "Pruefung vor dem Auftrag: cad-check mit Hash, Idempotenz, 409 bei laufender Pruefung, Tageslimit und Materialuebernahme"
```

### Task 11: Oberfläche Welle 2 (CAD-Formular, Werkstück-Kasten)

**Files:**
- Modify: `web/static/js/cad.js` (Import `reloadProject`; Kasten „Vor dem Modellieren“; automatische Prüfung; `check_items`; Bilderliste aus `cad_check.images`; 409-Wiederholung)
- Modify: `web/static/js/photos.js` (Kasten „Werkstück“)

**Interfaces:**
- Consumes: `POST /api/projects/{pid}/cad-check` (200 / 409 / 429 / 502), `project.cad_check` (`stale`, `items`, `material`, `images`, `photo_ids`, `part_id`, `checked_at`), `PATCH /api/projects/{pid}` Werkstück-Felder.

- [ ] **Step 1: cad.js**

Import: `import { S, ensureProject, reloadProject, go, onLeave, refreshMe, jobBadge } from "./app.js";`. Im `form(main)`: `let chk = P.cad_check, checking = false, again = false;` dazu:

```js
const sel = () => ({ photo_ids: [...picked], part_id: partSel ? Number(partSel) : null });
const same = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());
const needCheck = () => !chk || chk.error || chk.stale || !same(chk.photo_ids, sel().photo_ids) || (chk.part_id ?? null) !== sel().part_id;
async function runCheck(force = false) {
  if (checking) { again = true; return; }
  checking = true; drawCheck();
  try { chk = await api(`/api/projects/${P.id}/cad-check`, { method: "POST", body: { ...sel(), force } }); await reloadProject(); }
  catch (e) {
    if (e.status === 409) { checking = false; setTimeout(() => runCheck(false), 3000); return; }
    chk = { error: e.message, items: [], images: [] };
  } finally {
    checking = false; drawCheck();
    const rerun = again && !chk?.error; again = false;
    if (rerun && needCheck()) runCheck();
  }
}
function drawCheck() {
  const blocks = (chk?.items || []).filter(i => i.severity === "block").length;
  submit.replaceChildren(icon("cube"), blocks ? "Trotzdem erzeugen" : "CAD-Modell erzeugen");
  const mat = chk?.material ? [chk.material.color, chk.material.material, chk.material.finish].filter(Boolean).join(", ") : "";
  clear(checkBox, h("div", { class: "card-head" }, h("h2", {}, "Vor dem Modellieren"),
      h("button", { class: "btn sm", disabled: checking, onclick: () => runCheck(true) }, checking ? h("span", { class: "spin" }) : icon("refresh", 14), "Erneut prüfen")),
    chk?.error ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, `Prüfung nicht möglich: ${chk.error}`)) : null,
    chk && !chk.error ? (chk.items.length ? h("ul", { class: "checks" }, chk.items.map(i => h("li", {}, stateIcon(i.severity === "block" ? "fail" : "warn"), h("span", {}, i.text))))
      : h("div", { class: "note ok" }, icon("check"), h("span", {}, "Die Unterlagen reichen für ein vollständiges Modell."))) : null,
    mat ? h("span", { class: "xs muted" }, `Werkstück (geschätzt): ${mat} – unter „Fotos prüfen“ änderbar`) : null,
    chk?.checked_at ? h("span", { class: "xs muted" }, `Geprüft ${dt(chk.checked_at)}${chk.stale ? " · veraltet" : ""}`) : null);
}
```

`checkBox = h("section", { class: "card" })` in der rechten Spalte vor `submit`. Nach dem Aufbau: `drawCheck(); if (needCheck()) runCheck();`. Bei Änderung der Fotoauswahl (`drawPhotos`) und des Teils (`partBox.onchange`): `if (needCheck()) runCheck();`. Beim Absenden: `check_items: (chk?.items || []).map(i => ({ kind: i.kind, severity: i.severity, text: i.text }))`. Bilderliste: Beschriftung „Bilder für die KI · N“ listet `chk?.images` (Dateiname + Art: Draufsicht / Von unten / Höhenlehre / Schrägfoto (Original)); ergeben die gewählten Fotos mehr als 6 Bilder (top/bottom/tilted je 1, gauge je 1 zusätzlich) → `h("span", { class: "xs", style: { color: "var(--warn)" } }, "Nur die ersten 6 Bilder gehen mit")`.

- [ ] **Step 2: photos.js Werkstück-Kasten** (Container `wsBox` im `aside` vor `list`; in `draw()`: `clear(wsBox, werkstueck())`):

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
  const reset = async () => { try { S.project = await api(`/api/projects/${P.id}`, { method: "PATCH", body: { clear_material: true } }); draw(); } catch (e) { fail(e); } };
  return h("section", { class: "card", style: { gap: "8px" } }, h("div", { class: "card-head" }, h("h3", {}, "Werkstück"),
      h("span", { class: "xs muted" }, P.material_user ? "von Hand gesetzt" : (P.material ? "von der KI geschätzt" : "noch nicht gesetzt"))),
    h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "flabel" }, "Farbe"), color), h("label", { class: "field" }, h("span", { class: "flabel" }, "Material"), material),
      h("label", { class: "field" }, h("span", { class: "flabel" }, "Transparent"), transp), h("label", { class: "field" }, h("span", { class: "flabel" }, "Oberfläche"), finish)),
    h("span", { class: "xs muted" }, "Vor „Kanten erkennen“ setzen – die Erkennung nutzt diese Angaben."),
    P.material_user ? h("button", { class: "btn sm ghost", style: { alignSelf: "flex-start" }, onclick: reset }, "Zurücksetzen") : null);
}
```

- [ ] **Step 3: Prüfen**

Run: `for f in web/static/js/*.js; do node --check "$f"; done && python -m pytest -q -p no:cacheprovider tests/test_texts.py`; Browser-Probe im Scratchpad: Formular öffnen → Prüfung läuft automatisch (Testmodus-Punkte, Knopf „Trotzdem erzeugen“); erneutes Öffnen ohne Änderung → `POST …/cad-check` liefert 200 mit gleichem `hash` ohne KI-Aufruf (Server-Log); Auftrag absenden → `check_items` im Request-Body; Auswahl während einer laufenden Prüfung ändern → zweite Prüfung folgt.

- [ ] **Step 4: Commit und Wellenabschluss** (lokale Suite und CI)

```bash
git add web/static/js/cad.js web/static/js/photos.js
git commit -m "Oberflaeche: Pruefkasten vor dem Modellieren, Bilderliste, Werkstueck-Kasten"
```

---

## Welle 3 – Hinweise im Server, Kontrastwarnung, veraltete Kanten

### Task 12: `_hints`, `edges_stale`, `outline_hints`, Kontrastwarnung, Teile-Zuordnung mit Werkstück

**Files:**
- Modify: `web/app/main.py` (`_hints(project)`, `_analyze_store`/`_outline_of`/`photo_edges` mit Hinweisen, `_photo_public(ph, hints)`, `project_patch` realigniert bei geänderten Hinweisen)
- Modify: `web/app/parts.py` (`ai_parts(photo_dir, res, material_text="")`)
- Modify: `web/static/js/photos.js` (Kontrasthinweis), `web/static/js/measure.js` (Hinweis „Werkstück geändert – Kanten neu erkennen“)
- Modify: `tests/test_edges_api.py`, `tests/test_align.py`

**Interfaces:**
- Produces: `main._hints(project) -> dict` (`{}` bei `material_user=0`, sonst `{"transparent": …, "light": …}`); `photo.edges_stale`; `analysis.edges_hints`, `analysis.outline_hints`; `parts.ai_parts(..., material_text)`.

- [ ] **Step 1: Failing tests**

`tests/test_edges_api.py`:

```python
def test_hints_in_edges_json_und_veraltet(two):
    c, pid, phid = two
    c.patch(f"/api/projects/{pid}", json={"transparent": 2, "color": "silber"}, headers=H)
    c.post(f"/api/photos/{phid}/edges", json={"use_ai": False}, headers=H)
    assert c.get(f"/api/photos/{phid}/edges.json").json()["hints"] == {"transparent": 2, "light": True}
    ph = next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == phid)
    assert ph["edges_stale"] is False
    c.patch(f"/api/projects/{pid}", json={"transparent": 0}, headers=H)
    ph = next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == phid)
    assert ph["edges_stale"] is True
    c.patch(f"/api/projects/{pid}", json={"clear_material": True}, headers=H)
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)                # KI-Schaetzung aendert hints nicht
    ph = next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == phid)
    assert ph["edges_stale"] is True                                                           # hints {} vs. gespeichert transparent=2


def test_kontrastwarnung(user):
    pid, phid = _upload(user, [{"rect": [60, 80, 60, 40], "gray": 225}])
    ph = user.get(f"/api/projects/{pid}").json()["photos"][0]
    assert ph["low_contrast"] is True and ph["contrast"] < 20
```

`tests/test_align.py`:

```python
def test_werkstueck_aendert_umriss_und_lage(pair):
    from app import db
    c, pid, t, b = pair
    c.patch(f"/api/projects/{pid}", json={"transparent": 1}, headers=H)
    a = db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (b["id"],))["analysis"])
    assert a["outline_hints"] == {"transparent": 1, "light": False} and a["bottom_align"]["rot"] == 90
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_edges_api.py -k "hints or kontrast" tests/test_align.py -k werkstueck`
Expected: FAIL (`KeyError: 'hints'`/`edges_stale`/`outline_hints`).

- [ ] **Step 3: Implementierung**

```python
def _hints(project: dict) -> dict:
    """Hinweise fuer die Kantenerkennung nur aus Handeingaben (Spec §3); KI-Schaetzungen wirken nicht."""
    if not project.get("material_user"):
        return {}
    return {"transparent": project.get("transparent") or 0,
            "light": (project.get("color") or "").strip().lower() in LIGHT_COLORS}
```

- `_analyze_store(phid, img, fmt, view, hints)`; Aufrufer übergeben `_hints(p)` (`photo_upload` holt `p = _own_project(pid, u)`).
- `_outline_of(ph)`: Projekt laden (`db.q1("SELECT * FROM projects WHERE id=?", (ph["project_id"],))`), `hints = _hints(project)`; nachrechnen auch, wenn `a.get("outline_hints") != hints`; `edges.detect(img, ph["format"], hints)`; speichert `outline_hints`.
- `photo_edges`: `res = edges.detect(img, ph["format"], _hints(p))`; `parts.ai_parts(d, res, jobs.material_line(p))`; im `atomic`-Block zusätzlich `outline_mm`, `contrast`, `outline_hints`, `edges_hints = _hints(p)` in die frisch gelesene Analyse; nach dem Block bei `ph["view"] in PLANAR` → `_realign_project(p["id"])`.
- `_photo_public(ph, hints=None)`: `"edges_stale": hints is not None and (d / "edges.json").is_file() and a.get("edges_hints", {}) != hints`; `_project_public` berechnet `hp = _hints(p)` einmal und übergibt es; `photo_upload`/`photo_patch` übergeben `_hints(p)`.
- `project_patch`: vor den Änderungen `before = _hints(p)`; nach der Transaktion `if _hints(p_neu) != before: _realign_project(pid)` (die Ausrichtung rechnet die Umrisse mit den neuen Hinweisen nach).
- `parts.ai_parts(photo_dir, res, material_text="")`: `content.append({"type": "text", "text": candidate_text(res) + ("\n" + material_text + "\nBei transparenten Teilen sind durchscheinende Strukturen Innenbohrungen, keine Rillen." if material_text else "")})`.
- `photos.js`: bei `p.low_contrast` ein `note warn`: „Geringer Kontrast zur Unterlage – Licht seitlich, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen.“
- `measure.js`: neben „Kanten erkennen“ bei `photo.edges_stale` (aktuelles Foto aus `S.project.photos`) ein `h("span", { class: "xs", style: { color: "var(--warn)" } }, "Werkstück geändert – Kanten neu erkennen")`.

- [ ] **Step 4: Tests grün, ruff; Laufzeit protokollieren**

Run: `python -m pytest -q -p no:cacheprovider && ruff check . && node --test tests/js/*.test.mjs && for f in web/static/js/*.js; do node --check "$f"; done`
Expected: PASS. Upload-Zeit A4/A3 (synthetisch und Foto 1) mit und ohne Hinweise messen (`scratchpad/zeit.py`), ins Protokoll.

- [ ] **Step 5: Commit und Wellenabschluss** (lokale Suite und CI)

```bash
git add web/app/main.py web/app/parts.py web/static/js/photos.js web/static/js/measure.js tests/test_edges_api.py tests/test_align.py
git commit -m "Werkstueck-Hinweise in der Kantenerkennung, veraltete Kanten, Kontrastwarnung, Teile-Zuordnung mit Original-Zeile"
```

---

### Task 13: Browser-Durchlauf, Review, Auslieferung

**Files:**
- Scratchpad: `pw/stufe_a.mjs` (Playwright, nicht im Repo)
- Modify: `README.md` (Fotoart „Von unten“, Prüfung vor dem Auftrag, Werkstück: je ein Satz im Abschnitt zum Ablauf)

- [ ] **Step 1: Playwright-Durchlauf** gegen einen lokalen Server (`AI_FAKE=1 SANDBOX_MODE=local`, Port 8765): Draufsicht und Unteransicht (synthetisch) hochladen → Detail der Unteransicht zeigt Lage, Klick auf eine andere Lage → `rot` geändert, „Wieder automatisch“; Werkstück setzen → Messseite zeigt „Werkstück geändert“ nach einem früheren „Kanten erkennen“; Messen: Quelle „Von unten“, Messung mit `view=bottom`, Teil zeichnen → „unten = T1“; CAD-Formular: Prüfkasten erscheint automatisch mit zwei Punkten, „Trotzdem erzeugen“ → Auftrag läuft durch (Testmodus), zweites Öffnen ohne KI-Aufruf; Konsole ohne Fehler.
  Expected: alle Prüfpunkte wahr, `konsolenfehler == []`.
- [ ] **Step 2: README** ergänzen; `pytest tests/test_texts.py` grün.
- [ ] **Step 3: Review** (whole-branch, wie bei PR #3/#4: JS-Kette und ein Server-Reviewer), Befunde beheben, Suite grün.
- [ ] **Step 4: Auslieferung** (Spec §7): PR → CI grün → Merge → CI auf `main` → NAS mit Sicherung (`backup-data-<datum>.tgz` bei gestoppten Containern) → `compose pull && up -d` → Gesundheit; auf der DS918+ die Upload-Zeit einer A4-Draufsicht messen (über 6 s → Befund, vor A8 klären) → A8 mit dem Kühlkörperblock (dreimal, Zählung Fasen/Stufen/Bohrungen und Ausrichtung der echten Unteransicht ins Protokoll).

```bash
git add README.md
git commit -m "README: Unteransicht, Pruefung vor dem Auftrag, Werkstueck"
```
