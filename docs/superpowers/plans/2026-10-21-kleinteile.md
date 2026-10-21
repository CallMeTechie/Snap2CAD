# Kleinteile-Unterlage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Snap2CAD vermisst Kleinteile von wenigen Millimetern bis etwa 50 mm auf einer neuen Messunterlage „Kleinteile“ (Feld 60 × 80 mm, Blatt hell und Blatt dunkel); A4 und A3 bleiben exakt wie bisher.

**Architecture:** Jedes Messformat bekommt in `core/matgen.py` ein Profil (`PROFILES`): Auflösung der Entzerrung, Kantenmaßstab `k`, Feldart, Marker-IDs, Kontrollmaß, Qualitätsschwellen, Bohrungs-Obergrenze. `core/vision.py` erkennt das Format an der Marker-Familie und entzerrt mit dem Profil; `core/edges.py` rechnet alle Längen mit `k` (Flächen mit `k²`) und bekommt für Felder ohne Raster den Weg „Feldfarbe“; `web/app/parts.py`, `web/app/main.py`, `web/app/jobs.py` und die Oberfläche lesen Maßstab, Kontrollmaß und Schwellen aus dem Profil bzw. vom Foto. Goldwerte, die vor der ersten Änderung auf dem unveränderten Stand erzeugt werden, sichern A4/A3.

**Tech Stack:** Python 3.13, FastAPI, SQLite, OpenCV 5.0, ReportLab, pypdfium2, shapely; Vanilla-JS-Module; pytest, `node --test`, Playwright (nur Scratchpad).

**Spec:** `docs/superpowers/specs/2026-10-21-kleinteile-design.md`

**Ausführung:** SDD läuft **seriell** (ein Implementer zur Zeit, Tasks in Nummernfolge, jeder Task mit eigenem Review vor dem nächsten). Task 1 muss auf dem unveränderten Code laufen (Goldwerte); kein anderer Task darf vor ihm Code ändern. Tasks 3–7 bauen aufeinander auf (Profil → Erkennung → Kanten → Teile → API). Task 11 (Gesamtreview, PR, Merge, Auslieferung) führt der Controller selbst aus.

## Global Constraints

- Nutzerentscheidungen (Spec „Ziel“ und §7) sind gesetzt: Messfeld 60 × 80 mm; Blatt hell und Blatt dunkel je auf einem eigenen A4-Blatt; Feld ohne Raster; 8 Marker à 8 mm im weißen Rahmen außerhalb des Feldes; IDs 20–27 hell, 30–37 dunkel; Kontrollmaß 50 mm; 30 px/mm; keine Höhenlehre; gemischte Projekte nicht sperren, sondern Hinweis; F1 Qualitätsschwellen mit `k` (K60: gut ≤ 0,125 mm, brauchbar ≤ 0,25 mm); F2 `parts.py` wird mit umgestellt; F3 Bohrung K60 bis Ø 40 mm; F4 vertauschte Kleinteile-Variante → umschalten mit Hinweis (nicht zwischen A4/A3 und Kleinteilen).
- Namen wörtlich: Messformate `A4`, `A3`, `K60H`, `K60D`; Druckformat `K60`; `matgen.PROFILES`, `matgen.FORMATS` (= `PROFILES`), `matgen.PRINT_FORMATS = {"A4": ("A4",), "A3": ("A3",), "K60": ("K60H", "K60D")}`, `matgen.PRINT_PAGES = {"A4": ("mat", "gauge", "guide"), "A3": ("mat", "gauge", "guide"), "K60": ("mat", "dark", "guide")}`, `matgen.SIBLING = {"K60H": "K60D", "K60D": "K60H"}`, `matgen.edge_scale(fmt)`, `matgen.print_format_of(fmt)`; Layout-Felder `pxmm`, `edge_scale`, `field` (`grid` | `plain_light` | `plain_dark`), `ids`, `ctrl_mm`, `hole_max_mm2`, `quality_mm`, `marker_pos` (`grid` | `frame`), `label`; `vision.rect_pxmm(a)`; Analysefeld `format_note`; `edges.Scale`, `edges.scale_of(fmt)`, Ergebnisfeld `edge_scale`; Projektfelder `ctrl_ref`, `mixed_formats`; Fotofelder `quality_mm`, `n_markers`, `view_note`; JS-Modul `web/static/js/formats.js`; Anleitungsabschnitt `kleinteile`.
- Anzeigenamen wörtlich: „Kleinteile hell“, „Kleinteile dunkel“, „Kleinteile“ (Druckformat); Hinweis F4 „Format auf Kleinteile dunkel geändert“ bzw. „Format auf Kleinteile hell geändert“; Höhenlehre auf K60 „Höhenlehre gibt es bei Kleinteilen nicht – Teil kippen und als ‚Gekippt (Höhe)‘ fotografieren“; Fehlermeldung „Format muss A4, A3 oder K60 sein“; gemischte Projekte „Fotos auf verschiedenen Unterlagen – das Kontrollmaß gilt für die Unterlage des ersten Fotos (<Anzeigename>).“
- A4/A3 bleiben exakt: `tests/test_golden_a4a3.py` (Task 1) muss nach jedem Task grün sein. Alle Profilwerte für A4/A3 sind die heutigen Konstanten; jede neue Formel muss für `k = 1.0`, `pxmm = 10.0` bitgleich die alte Zahl ergeben (Multiplikation mit `1.0` ist exakt – keine Umstellung von Rechenreihenfolgen, die Rundung ändert, z. B. kein `x / k` statt `x * k` bei Längen, außer bei `WORK_PXMM / k`).
- `core` wird in `web/app/parts.py` und `web/app/jobs.py` **nur funktionslokal** importiert (Muster `jobs._rect_top`); `web/app/main.py` importiert `matgen`, `vision`, `edges` wie bisher.
- Keine neuen Abhängigkeiten (Python und JS). Keine Datenmigration (`photos.format` ist schon Text).
- Bestehende Tests werden nur angepasst in `tests/test_geom.py` (neue Signatur `geom.factors`) und `tests/js/help.test.mjs` (`SECTIONS` um `kleinteile`); alle anderen bleiben unverändert grün.
- Texte der Oberfläche deutsch, im `h()`-Stil, ohne „Claude“/„Anthropic“ (`tests/test_texts.py`).
- Zeilenlänge 130 (ruff E501, Regeln E, F, W, B); Variablennamen nicht `l` (E741); keine unbenutzten Zuweisungen (F841); `raise … from` in `except` (B904); keine Lambda-Zuweisung (E731). Snippets im Plan, die länger sind, beim Übernehmen an Wortgrenzen umbrechen. Jeder Task endet mit `ruff check` auf den geänderten Python-Dateien bzw. `node --check` auf den geänderten JS-Dateien.
- Commits **ohne jede Claude-Attribution** (keine `Co-Authored-By`-Zeile, kein „Generated with“ in PR-Texten) – Nutzerregel geht vor.
- Protokoll und Skripte nur im Scratchpad: `SP=/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad`, Skripte unter `$SP/kleinteile/`, Protokoll `$SP/kleinteile-protokoll.md`, Playwright `$SP/pw/kleinteile.mjs`; nie im Repo.
- Umgebung: eigene Läufe mit `export TMPDIR=/root/.cache/snap2cad-tmp` (vorher `mkdir -p`); vor jeder Suite `df -h /tmp` ≥ 1 GB frei, sonst nicht starten und melden; Suiten nie parallel; fremde Ordner in `/tmp` nicht anfassen. Lokal: `source /root/Snap2CAD-venv/bin/activate && cd /root/Snap2CAD && ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs && for f in web/static/js/*.js; do node --check "$f"; done` (pytest-xdist ist nicht installiert; die Suite läuft seriell, rund 5 Minuten). `tests/test_auth.py::test_unauthenticated_is_rejected` ist in Teilläufen reihenfolgeabhängig (vorbestehend) – nur die volle Suite zählt.
- Kantenerkennung K60: Toleranzen der Tests (±0,1 mm) werden **nicht** gelockert. Scheitert ein Genauigkeitstest, wird die Ursache mit superpowers:systematic-debugging gesucht (z. B. Schwelle, Kern, Randstreifen) und innerhalb des Spec-Designs behoben; jede Abweichung vom Plan-Code wird im Report als Ruling begründet.

## Review Focus

1. Ein Kleinteile-Blatt liegt auf der A4-Unterlage und beide sind im Foto: Snap2CAD nimmt das Kleinteile-Format, nicht A4 (Task 3 `test_k60_auf_a4_unterlage_gewinnt`).
2. Ein Teil ragt über den Feldrand hinaus: keine Ausnahme, der Umriss endet am Feld (Task 5 `test_k60_teil_ueber_feldrand`).
3. Falsche Variante (dunkles Teil auf dem dunklen Blatt): kein Absturz, wenig Kontrast oder kein Umriss, und der Kontrasthinweis nennt die andere Variante (Task 5 `test_k60_falsche_variante_wenig_kontrast`, Task 8 `lowContrastText`).
4. Ein Projekt mischt A4- und Kleinteile-Fotos: Kontrollmaß-Bezug kommt vom ersten Foto, `mixed_formats` ist wahr, die Oberfläche zeigt den Hinweis (Task 7 `test_k60_api_gemischt`, Task 8 `mixedText`).
5. Ein Eckpunkt eines Teils liegt knapp außerhalb des kleinen Feldes: erlaubt bis 2,5 mm, darüber 400 – nicht 10 mm wie bei A4 (Task 6 `test_k60_api_eckpunkt_spielraum`).

---

### Task 1: Goldwerte A4/A3 auf dem unveränderten Stand

**Files:**
- Create: `tests/test_golden_a4a3.py`
- Create: `tests/fixtures/golden_a4a3.json` (erzeugt, nicht von Hand geschrieben)

**Interfaces:**
- Consumes: unveränderter Code auf Branch `kleinteile` (main ff95d9b plus Spec/Plan-Commits); `conftest.synthetic_photo(fmt, page, tilt=…, objects=…, shadow=…)`, `vision.analyze`, `vision.rectify_mat`, `edges.detect`.
- Produces: `tests/test_golden_a4a3.py::test_golden_a4a3_unveraendert[<fall>]` – muss nach jedem späteren Task grün sein. Neue Schlüssel in den Ergebnissen sind erlaubt, alte müssen gleich bleiben.

- [ ] **Step 1: Prüfen, dass noch kein Code geändert ist**

Run: `cd /root/Snap2CAD && git diff --stat ff95d9b -- core web tests tools generator`
Expected: keine Ausgabe (nur `docs/` hat sich seit ff95d9b geändert).

- [ ] **Step 2: Test schreiben**

```python
"""A4/A3 bleiben exakt wie auf main ff95d9b (Spec Kleinteile §6, Goldwerte).

Neu erzeugen nur auf dem unveraenderten Stand (Plan Kleinteile, Task 1):
    SNAP2CAD_WRITE_GOLDEN=1 python -m pytest -q -p no:cacheprovider tests/test_golden_a4a3.py
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from conftest import synthetic_photo
from core import edges, vision

GOLDEN = Path(__file__).parent / "fixtures" / "golden_a4a3.json"
BOX = {"rect": [60, 80, 60, 40], "gray": 150}
PLATE = {"rect": [50, 105, 80, 20], "gray": 90}
HOLE = {"circle": [90, 115, 5], "gray": 235}
GLASS = {"rect": [60, 80, 60, 40], "gray": 200, "alpha": 0.5}
SHADOW = {"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}
L_SHAPE = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 120], [60, 120]]

# Name -> (Format, Seite, synthetic_photo-Argumente, Format fuer analyze, Hinweise fuer detect oder None = ohne Kanten)
CASES = {
    "a4_standard": ("A4", 0, {}, None, {}),
    "a3_standard": ("A3", 0, {}, None, {}),
    "a4_explizit": ("A4", 0, {}, "A4", None),
    "a4_hoehenlehre": ("A4", 1, {"tilt": 0.03}, "A4", None),
    "a4_quader": ("A4", 0, {"objects": [BOX]}, "A4", {}),
    "a4_zwei": ("A4", 0, {"objects": [BOX, PLATE, HOLE]}, "A4", {}),
    "a4_leer": ("A4", 0, {"objects": []}, "A4", {}),
    "a4_rand": ("A4", 0, {"objects": [{"rect": [0, 60, 50, 30], "gray": 120}]}, "A4", {}),
    "a4_hell": ("A4", 0, {"objects": [{"rect": [60, 80, 60, 40], "gray": 246}]}, "A4", {}),
    "a4_hell_hinweis": ("A4", 0, {"objects": [{"rect": [60, 80, 60, 40], "gray": 225}]}, "A4", {"light": True}),
    "a4_schatten": ("A4", 0, {"objects": [BOX], "shadow": SHADOW}, "A4", {}),
    "a4_glas_t2": ("A4", 0, {"objects": [GLASS]}, "A4", {"transparent": 2}),
    "a4_glas_t1": ("A4", 0, {"objects": [GLASS]}, "A4", {"transparent": 1}),
    "a4_l_bohrung": ("A4", 0, {"objects": [{"polygon": L_SHAPE, "gray": 150}, {"circle": [110, 87.5, 5], "gray": 235}]},
                     "A4", {}),
    "a3_quader": ("A3", 0, {"objects": [BOX]}, "A3", {}),
}


def _snap(name: str) -> dict:
    fmt, page, kw, afmt, hints = CASES[name]
    img = vision.load_image(synthetic_photo(fmt, page, **kw))
    a = vision.analyze(img, afmt)
    out = {"analyze": a}
    if a.get("homography") and a.get("format"):
        rect = vision.rectify_mat(img, a["homography"], a["format"])
        out["rect_shape"] = list(rect.shape)
        out["rect_md5"] = hashlib.md5(np.ascontiguousarray(rect).tobytes()).hexdigest()
        if hints is not None:
            out["detect"] = edges.detect(rect, a["format"], hints)
    return json.loads(json.dumps(out))  # Tupel -> Listen, int-Schluessel -> str (wie im JSON)


def _same(old, new, path="$"):
    """Alte Werte muessen gleich bleiben; neue Schluessel sind erlaubt. Floats nach Rundung (Homographie 9, sonst 3)."""
    if isinstance(old, dict):
        assert isinstance(new, dict), path
        for k, v in old.items():
            assert k in new, f"{path}.{k} fehlt"
            _same(v, new[k], f"{path}.{k}")
    elif isinstance(old, list):
        assert isinstance(new, list) and len(new) == len(old), f"{path}: Laenge {len(old)} -> {len(new) if isinstance(new, list) else new}"
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            _same(a, b, f"{path}[{i}]")
    elif isinstance(old, float) or isinstance(new, float):
        digits = 9 if "homography" in path else 3
        assert round(float(old), digits) == round(float(new), digits), f"{path}: {old} -> {new}"
    else:
        assert old == new, f"{path}: {old!r} -> {new!r}"


@pytest.fixture(scope="module")
def golden() -> dict:
    if os.environ.get("SNAP2CAD_WRITE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps({n: _snap(n) for n in CASES}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(CASES))
def test_golden_a4a3_unveraendert(golden, name):
    _same(golden[name], _snap(name))
```

- [ ] **Step 3: Goldwerte erzeugen und prüfen**

Run:
```bash
mkdir -p /root/.cache/snap2cad-tmp && export TMPDIR=/root/.cache/snap2cad-tmp
source /root/Snap2CAD-venv/bin/activate && cd /root/Snap2CAD
SNAP2CAD_WRITE_GOLDEN=1 python -m pytest -q -p no:cacheprovider tests/test_golden_a4a3.py
python -m pytest -q -p no:cacheprovider tests/test_golden_a4a3.py
python - <<'EOF'
import json; g = json.load(open("tests/fixtures/golden_a4a3.json"))
for n, v in g.items():
    d = v.get("detect") or {}
    print(n, v["analyze"]["format"], v["analyze"]["status"], len(d.get("outlines", [])), len(d.get("holes", [])), v.get("rect_md5", "-")[:8])
EOF
```
Expected: beide Läufe 15 passed. Die Übersicht zeigt `a4_standard A4 gut 1 0`, `a4_zwei A4 gut 1 1`, `a4_leer A4 gut 0 0`, `a4_hoehenlehre A4 gut - -` (ohne Kanten), `a3_quader A3 gut 1 0`; die Datei ist kleiner als 1 MB (`ls -la tests/fixtures/golden_a4a3.json`).

- [ ] **Step 4: Ruff und Commit**

```bash
ruff check tests/test_golden_a4a3.py
git add tests/test_golden_a4a3.py tests/fixtures/golden_a4a3.json
git commit -m "Kleinteile: Goldwerte A4/A3 auf dem unveraenderten Stand"
```

---

### Task 2: Formatprofile und Kleinteile-Blätter (`core/matgen.py`)

**Files:**
- Modify: `core/matgen.py` (Konstanten `FORMATS`/`PAGES` am Dateiende ersetzen; neue Funktionen `k60_page`, `k60_guide_page`, `_profile_fields`, `edge_scale`, `print_format_of`; `_spec`, `build`, `__main__`)
- Modify: `generator/make_mat.py`
- Test: `tests/test_core.py` (neue Tests am Ende; bestehende bleiben unverändert)

**Interfaces:**
- Consumes: bestehende Zeichenhelfer `marker`, `white_box`, `fmt`, `_title`, Farben `C1`, `C5`, `C10`, `INK`, `MUTED`, `ACCENT`.
- Produces:
  - `PROFILES: dict[str, dict]` mit Schlüsseln `A4`, `A3`, `K60H`, `K60D`; je Profil `page`, `marker_mm`, `ids` (Tupel), `field`, `pxmm`, `edge_scale`, `ctrl_mm`, `hole_max_mm2`, `quality_mm` (Tupel gut, brauchbar), `gauge` (bool), `border_bgr` (Tupel), `label`.
  - `FORMATS = PROFILES` (Messformate; `fmt in FORMATS` bleibt die Prüfung für Messformate), `PRINT_FORMATS`, `PRINT_PAGES`, `PAGES = ("mat", "gauge", "guide")` (bisheriger Name, Seiten von A4/A3), `SIBLING`.
  - `edge_scale(fmt: str | None) -> float` (1.0 ohne bekanntes Format), `print_format_of(fmt: str | None) -> str | None`.
  - `layout(fmt)` für Messformate: bisherige Felder plus `pxmm`, `edge_scale`, `field`, `ids` (Liste), `ctrl_mm`, `hole_max_mm2`, `quality_mm` (Liste), `marker_pos`, `label`; K60 ohne `height_gauge`; `grid_mm == [60, 80]`, `grid_origin_on_page_mm == [75.0, 170.0]`.
  - `build(out, fmt="A4", pages=None, header="")` für **Druckformate**; Rückgabe bei A4/A3 wie bisher das Layout, bei K60 `{"K60H": layout, "K60D": layout}`; `ValueError("Format muss A4, A3 oder K60 sein")` sonst (auch für `K60H`).

- [ ] **Step 1: Tests schreiben** (an das Ende von `tests/test_core.py`)

```python
def _render(pdf_bytes: bytes, page: int, px: float):
    import cv2
    import numpy as np
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        img = pdf[page].render(scale=px * 25.4 / 72).to_pil().convert("RGB")
    finally:
        pdf.close()
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def _pages(pdf_bytes: bytes) -> int:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    n = len(pdf)
    pdf.close()
    return n


def test_profile_a4_a3_unveraendert():
    for f in ("A4", "A3"):
        sp = matgen.layout(f)
        assert (sp["pxmm"], sp["edge_scale"], sp["field"], sp["ctrl_mm"], sp["marker_pos"]) == (10.0, 1.0, "grid", 100.0, "grid")
        assert sp["quality_mm"] == [0.5, 1.0] and sp["hole_max_mm2"] == 2000.0 and sp["ids"] == list(range(8))
        assert "height_gauge" in sp


@pytest.mark.parametrize("f,ids,field", [("K60H", list(range(20, 28)), "plain_light"), ("K60D", list(range(30, 38)), "plain_dark")])
def test_profile_k60(f, ids, field):
    sp = matgen.layout(f)
    assert sp["grid_mm"] == [60, 80] and sp["marker_size_mm"] == 8.0 and sp["grid_origin_on_page_mm"] == [75.0, 170.0]
    assert sp["ids"] == ids and sp["field"] == field and sp["marker_pos"] == "frame"
    assert (sp["pxmm"], sp["edge_scale"], sp["ctrl_mm"]) == (30.0, 0.25, 50.0)
    assert sp["quality_mm"] == [0.125, 0.25] and sp["hole_max_mm2"] == pytest.approx(1256.6, abs=0.1)
    assert "height_gauge" not in sp
    assert sorted(int(k) for k in sp["centers_mm"]) == ids
    for x, y in sp["centers_mm"].values():  # Marker-Mitte mindestens 8 mm ausserhalb des Feldes
        assert x <= -8 or x >= 68 or y <= -8 or y >= 88


def test_print_formats_und_helfer():
    assert matgen.PRINT_FORMATS == {"A4": ("A4",), "A3": ("A3",), "K60": ("K60H", "K60D")}
    assert matgen.PRINT_PAGES["K60"] == ("mat", "dark", "guide") and matgen.PAGES == ("mat", "gauge", "guide")
    assert matgen.print_format_of("K60D") == "K60" and matgen.print_format_of("A3") == "A3"
    assert matgen.print_format_of(None) is None and matgen.print_format_of("A5") is None
    assert matgen.edge_scale("K60H") == 0.25 and matgen.edge_scale("A4") == 1.0 and matgen.edge_scale(None) == 1.0
    assert matgen.SIBLING == {"K60H": "K60D", "K60D": "K60H"}


def test_k60_pdf_drei_seiten_und_marker_erkennbar():
    buf = io.BytesIO()
    spec = matgen.build(buf, "K60", header="Werkstatt Test")
    assert set(spec) == {"K60H", "K60D"}
    data = buf.getvalue()
    assert _pages(data) == 3
    for i, f in enumerate(("K60H", "K60D")):
        assert sorted(vision.detect(_render(data, i, 12.0))) == spec[f]["ids"]


def test_k60_feldfarbe_und_ueberstand():
    data = io.BytesIO()
    matgen.build(data, "K60")
    data = data.getvalue()
    px = 12.0
    for i, (lo, hi) in enumerate(((235, 256), (0, 60))):
        img = _render(data, i, px)
        h = img.shape[0]
        for x_mm, y_mm in ((105, 210), (75.5, 170.5), (134.5, 249.5)):  # Feldmitte und 0,5 mm innerhalb der Feldecken
            v = int(img[int(h - y_mm * px), int(x_mm * px)].mean())
            assert lo <= v < hi, (i, x_mm, y_mm, v)


def test_k60_seitenwahl():
    for fmt, pages, n in (("K60", ["dark"], 1), ("K60", ["gauge"], 3), ("A4", ["dark"], 3), ("A4", ["mat"], 1)):
        buf = io.BytesIO()
        matgen.build(buf, fmt, pages=pages)
        assert _pages(buf.getvalue()) == n, (fmt, pages)


def test_build_nur_druckformate():
    for bad in ("A5", "K60H", "K60D"):
        with pytest.raises(ValueError, match="Format muss A4, A3 oder K60 sein"):
            matgen.build(io.BytesIO(), bad)
```

- [ ] **Step 2: Tests laufen lassen, sie scheitern**

Run: `python -m pytest -q -p no:cacheprovider tests/test_core.py -k "profile or print_formats or k60 or nur_druckformate"`
Expected: FAIL (`KeyError: 'pxmm'`, `AttributeError: module 'core.matgen' has no attribute 'PRINT_FORMATS'` u. ä.).

- [ ] **Step 3: Profile und Helfer** – in `core/matgen.py` `import math` zu den Importen; `FIELD_DARK` nach `ACCENT`; den Block `FORMATS = {…}` / `PAGES = …` am Dateiende ersetzen durch:

```python
FIELD_DARK = HexColor("#222222")   # tiefes Schwarzgrau des dunklen Kleinteile-Feldes
```

```python
PROFILES = {
    "A4": {"page": A4, "marker_mm": 20.0, "ids": tuple(range(8)), "field": "grid", "pxmm": 10.0, "edge_scale": 1.0,
           "ctrl_mm": 100.0, "hole_max_mm2": 2000.0, "quality_mm": (0.5, 1.0), "gauge": True,
           "border_bgr": (235, 236, 236), "label": "A4"},
    "A3": {"page": A3, "marker_mm": 25.0, "ids": tuple(range(8)), "field": "grid", "pxmm": 10.0, "edge_scale": 1.0,
           "ctrl_mm": 100.0, "hole_max_mm2": 2000.0, "quality_mm": (0.5, 1.0), "gauge": True,
           "border_bgr": (235, 236, 236), "label": "A3"},
    "K60H": {"page": A4, "marker_mm": 8.0, "ids": tuple(range(20, 28)), "field": "plain_light", "pxmm": 30.0,
             "edge_scale": 0.25, "ctrl_mm": 50.0, "hole_max_mm2": round(math.pi * 20 ** 2, 1), "quality_mm": (0.125, 0.25),
             "gauge": False, "border_bgr": (235, 236, 236), "label": "Kleinteile hell"},
    "K60D": {"page": A4, "marker_mm": 8.0, "ids": tuple(range(30, 38)), "field": "plain_dark", "pxmm": 30.0,
             "edge_scale": 0.25, "ctrl_mm": 50.0, "hole_max_mm2": round(math.pi * 20 ** 2, 1), "quality_mm": (0.125, 0.25),
             "gauge": False, "border_bgr": (34, 34, 34), "label": "Kleinteile dunkel"},
}
FORMATS = PROFILES   # Messformate (am Foto gespeichert)
PRINT_FORMATS = {"A4": ("A4",), "A3": ("A3",), "K60": ("K60H", "K60D")}
PRINT_PAGES = {"A4": ("mat", "gauge", "guide"), "A3": ("mat", "gauge", "guide"), "K60": ("mat", "dark", "guide")}
PAGES = PRINT_PAGES["A4"]   # bisheriger Name: Seiten von A4/A3
SIBLING = {"K60H": "K60D", "K60D": "K60H"}
K60_FIELD = (60, 80)
K60_ORIGIN = (75.0, 170.0)   # Feldecke unten links auf dem Blatt (mm)
K60_OFF = 13.0               # Marker-Mitte ausserhalb der Feldkante (mm)
K60_BLEED = 2.0              # dunkles Feld ragt so weit ueber das Messfeld: kein heller Saum am Rand der Entzerrung
K60_TICK0 = 2.5              # Skala beginnt so weit ausserhalb der Feldkante (keine Linie auf der Feldkante)
_LOCK = threading.Lock()
_HEADER = ""


def edge_scale(fmt: str | None) -> float:
    return PROFILES[fmt]["edge_scale"] if fmt in PROFILES else 1.0


def print_format_of(fmt: str | None) -> str | None:
    return next((p for p, fs in PRINT_FORMATS.items() if fmt in fs), None)


def _profile_fields(fmt: str) -> dict:
    p = PROFILES[fmt]
    return {"pxmm": p["pxmm"], "edge_scale": p["edge_scale"], "field": p["field"], "ids": list(p["ids"]),
            "ctrl_mm": p["ctrl_mm"], "hole_max_mm2": p["hole_max_mm2"], "quality_mm": list(p["quality_mm"]),
            "marker_pos": "grid" if p["field"] == "grid" else "frame", "label": p["label"]}
```

(`_LOCK` und `_HEADER` standen schon dort – nicht doppelt anlegen.)

- [ ] **Step 4: Kleinteile-Blatt** – nach `strip_page` einfügen:

```python
def k60_page(c, W, H, fmt):
    """Kleinteile-Blatt (Spec Kleinteile §1): Feld 60 x 80 mm ohne Raster, hell oder dunkel; Skala und 8 Marker im
    weissen Rahmen ausserhalb des Feldes. Rueckgabe wie mat_page, Koordinaten ab Feldecke unten links."""
    p = PROFILES[fmt]
    fw, fh = K60_FIELD
    gx, gy = K60_ORIGIN
    s, off, t0 = p["marker_mm"], K60_OFF, K60_TICK0
    dark = p["field"] == "plain_dark"
    m = 10.0

    if dark:
        b = K60_BLEED
        c.setFillColor(FIELD_DARK)
        c.rect((gx - b) * mm, (gy - b) * mm, (fw + 2 * b) * mm, (fh + 2 * b) * mm, stroke=0, fill=1)

    # Skala auf dem Rahmen, nach aussen gerichtet; keine Linie auf der Feldkante (sie wuerde als Objekt erkannt)
    c.setStrokeColor(INK)
    for i in range(0, fw + 1):
        ln = 3.5 if i % 10 == 0 else (2.5 if i % 5 == 0 else 1.5)
        c.setLineWidth(0.35 if i % 10 == 0 else 0.2)
        c.line((gx + i) * mm, (gy - t0) * mm, (gx + i) * mm, (gy - t0 - ln) * mm)
        c.line((gx + i) * mm, (gy + fh + t0) * mm, (gx + i) * mm, (gy + fh + t0 + ln) * mm)
    for j in range(0, fh + 1):
        ln = 3.5 if j % 10 == 0 else (2.5 if j % 5 == 0 else 1.5)
        c.setLineWidth(0.35 if j % 10 == 0 else 0.2)
        c.line((gx - t0) * mm, (gy + j) * mm, (gx - t0 - ln) * mm, (gy + j) * mm)
        c.line((gx + fw + t0) * mm, (gy + j) * mm, (gx + fw + t0 + ln) * mm, (gy + j) * mm)
    c.setFont("Helvetica", 5)
    c.setFillColor(MUTED)
    for i in range(0, fw + 1, 10):   # nicht unter/ueber den Mittelmarkern
        if i != fw // 2:
            c.drawCentredString((gx + i) * mm, (gy - t0 - 5.6) * mm, str(i))
            c.drawCentredString((gx + i) * mm, (gy + fh + t0 + 4.4) * mm, str(i))
    for j in range(0, fh + 1, 10):   # nicht neben den Mittelmarkern
        if j != fh // 2:
            c.drawRightString((gx - t0 - 4.2) * mm, (gy + j - 0.9) * mm, str(j))
            c.drawString((gx + fw + t0 + 4.2) * mm, (gy + j - 0.9) * mm, str(j))

    # Marker im Rahmen (Reihenfolge wie A4: unten links, unten rechts, oben rechts, oben links, dann Seitenmitten)
    ids = p["ids"]
    pos = {ids[0]: (-off, -off), ids[1]: (fw + off, -off), ids[2]: (fw + off, fh + off), ids[3]: (-off, fh + off),
           ids[4]: (fw / 2, -off), ids[5]: (fw + off, fh / 2), ids[6]: (fw / 2, fh + off), ids[7]: (-off, fh / 2)}
    for mid, (px, py) in pos.items():
        white_box(c, gx + px, gy + py, s, 1.5)
        marker(c, mid, gx + px, gy + py, s)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 4.5)
        ty = gy + py + s / 2 + 1.6 if py > 0 else gy + py - s / 2 - 3.2   # oberhalb bzw. unterhalb des Markers
        c.drawCentredString((gx + px) * mm, ty * mm, f"ID {mid}")
    c.setStrokeColor(C5)
    c.setLineWidth(0.3)
    r = off + s / 2 + 3.5
    c.rect((gx - r) * mm, (gy - r) * mm, (fw + 2 * r) * mm, (fh + 2 * r) * mm, stroke=1, fill=0)

    # Kopfzeile
    name = "dunkel" if dark else "hell"
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(m * mm, (H - m - 6) * mm, _title(f"Messunterlage Kleinteile {name}"))
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (H - m - 10.5) * mm, f"Feld {fw} × {fh} mm ohne Raster  ·  Ursprung 0/0 unten links  ·  Version 1")
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString((W - m) * mm, (H - m - 6) * mm, "Drucken mit 100 % / Tatsächliche Größe")
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawRightString((W - m) * mm, (H - m - 10.5) * mm,
                      "Tintenstrahl, mattes Papier · nicht „An Seite anpassen“" if dark else "nicht „An Seite anpassen“ · Papier plan auflegen")

    # Kontrollmass 50 mm und Eintragsfeld
    by, bx = 128.0, gx + 5
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.line(bx * mm, by * mm, (bx + 50) * mm, by * mm)
    for i in range(0, 51):
        ln = 4 if i % 10 == 0 else (2.6 if i % 5 == 0 else 1.6)
        c.setLineWidth(0.4 if i % 10 == 0 else 0.25)
        c.line((bx + i) * mm, by * mm, (bx + i) * mm, (by + ln) * mm)
    c.setFont("Helvetica", 5.5)
    c.setFillColor(INK)
    for i in range(0, 51, 10):
        c.drawCentredString((bx + i) * mm, (by + 4.8) * mm, str(i))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(bx * mm, (by - 4) * mm, "Kontrollmaß 50 mm – mit Lineal prüfen")
    fx, fwid = gx - 15, fw + 30
    c.setLineWidth(0.6)
    c.rect(fx * mm, (by - 22) * mm, fwid * mm, 12 * mm, stroke=1, fill=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(MUTED)
    c.drawString((fx + 2) * mm, (by - 13.4) * mm, "Gemessen (0–50):")
    c.drawString((fx + 2) * mm, (by - 20.2) * mm, f"Gemessen Skala 0–{fh} senkrecht:")
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.3)
    c.line((fx + 22) * mm, (by - 13.8) * mm, (fx + fwid - 9) * mm, (by - 13.8) * mm)
    c.line((fx + 39) * mm, (by - 20.6) * mm, (fx + fwid - 9) * mm, (by - 20.6) * mm)
    c.drawString((fx + fwid - 7.5) * mm, (by - 13.4) * mm, "mm")
    c.drawString((fx + fwid - 7.5) * mm, (by - 20.2) * mm, "mm")

    # Kurzhinweise
    c.setFont("Helvetica", 7)
    c.setFillColor(INK)
    for n, t in enumerate(["Teil mittig ins Feld legen, die Marker frei lassen.",
                           "Helles, blankes oder durchsichtiges Teil → dunkles Blatt; dunkles Teil → helles Blatt.",
                           "Kamera senkrecht, 2×- oder 3×-Zoom aus 25–30 cm, kein Makro. Diffuses Licht, kein Blitz.",
                           "Höhe: Teil kippen und erneut fotografieren (keine Höhenlehre)."]):
        c.drawString(fx * mm, (by - 32 - n * 4.2) * mm, t)

    # Selbstbeschreibende Spezifikation
    sp = "  ".join(f"ID{i} ({fmt_mm(px)}|{fmt_mm(py)})" for i, (px, py) in pos.items())
    c.setFont("Helvetica", 4.6)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (m - 0.5) * mm, f"ArUco DICT_4X4_50 · Kante {fmt_mm(s)} mm · Mittelpunkte in mm ab Feldecke unten links: {sp}")
    return {"grid_mm": [fw, fh], "marker_size_mm": s, "centers_mm": {str(k): v for k, v in pos.items()},
            "grid_origin_on_page_mm": [gx, gy]}
```

Hinweis zum Namen: Die bestehende Funktion heißt `fmt(v)` (Zahl mit Komma). In `k60_page` verdeckt der Parameter `fmt` diese Funktion – deshalb im Rumpf von `k60_page` **nicht** `fmt(...)` aufrufen, sondern auf Modulebene direkt unter der Definition von `fmt` einen Alias anlegen: `fmt_mm = fmt`, und in `k60_page` `fmt_mm(...)` benutzen.

- [ ] **Step 5: Anleitungsseite Kleinteile** – nach `guide_page` einfügen:

```python
def k60_guide_page(c, W, H, specs):
    """Anleitung fuer die Kleinteile-Blaetter (Spec Kleinteile §5); specs = {"K60H": layout, "K60D": layout}."""
    m = 18 * mm
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK, spaceAfter=4)
    st_s = ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=ACCENT,
                          spaceBefore=9, spaceAfter=3)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=12.6, textColor=INK, spaceAfter=3)
    st_n = ParagraphStyle("n", parent=st_p, leftIndent=12, bulletIndent=0)
    st_small = ParagraphStyle("sm", parent=st_p, fontSize=7.5, leading=10, textColor=MUTED)

    def b(t):
        return Paragraph(t, st_n, bulletText="•")

    story = [
        Paragraph("Anleitung: Kleinteile fotografieren und vermessen lassen", st_h),
        Paragraph("Für Teile von wenigen Millimetern bis etwa 50 mm. Das Feld ist 60 × 80 mm groß und hat kein Raster; "
                  "gemessen wird am Unterschied zwischen Teil und Feld.", st_p),
        Paragraph("1  Variante wählen", st_s),
        b("<b>Helles Blatt:</b> dunkle oder bunte Teile."),
        b("<b>Dunkles Blatt:</b> helle, blanke, weiße oder durchsichtige Teile."),
        Paragraph("2  Drucken und prüfen", st_s),
        b("Drucken mit <b>100 % / Tatsächliche Größe</b>. Das dunkle Blatt möglichst mit Tintenstrahl auf mattem Papier – "
          "Laser-Toner glänzt auf großen dunklen Flächen."),
        b("Kontrollmaß 0–50 mit einem Stahllineal nachmessen und den Wert auf „Fotos prüfen“ eintragen."),
        b("Blatt plan auf einen festen Untergrund legen, Ecken mit Klebeband fixieren."),
        Paragraph("3  Fotografieren", st_s),
        b("Teil mittig ins Feld legen, alle 8 Marker frei lassen. Diffuses Licht, kein Blitz, keine harten Schatten – "
          "es gibt kein Raster, das einen Schatten von einer Kante unterscheidet."),
        b("Kamera senkrecht über dem Feld, <b>2×- oder 3×-Zoom aus 25–30 cm</b>, der Rahmen füllt das Bild. "
          "Kein Makro-Modus: Je näher die Kamera, desto größer die Parallaxe."),
        b("Höhe: Teil kippen und erneut fotografieren (Ansicht „Gekippt (Höhe)“ oder als weitere Draufsicht). "
          "Eine Höhenlehre gibt es für Kleinteile nicht."),
        Paragraph("Genauigkeit – realistisch", st_s),
        Paragraph("Flache Teile (Höhe bis 2 mm): etwa ±0,2–0,3 mm, mit Messschieber-Nachmessung ±0,1–0,2 mm. Höhere Teile "
                  "werden oben um Maß × Höhe ÷ Abstand zu groß gemessen (20 × 10 mm aus 25 cm: +0,8 mm; aus 8 cm: "
                  "+2,5 mm) – an der Auflagekante messen oder die Maße am Modell mit dem Messschieber korrigieren.", st_p),
        Spacer(1, 6),
    ]
    rows = [["Marker", "Blatt", "Mitte X (mm)", "Mitte Y (mm)"]]
    for f, name in (("K60H", "hell"), ("K60D", "dunkel")):
        for k, (px, py) in specs[f]["centers_mm"].items():
            rows.append([f"ID {k}", name, fmt(px), fmt(py)])
    t = Table(rows, colWidths=[22 * mm, 24 * mm, 28 * mm, 28 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, C1),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))
    story += [Paragraph("Marker-Referenz (ArUco DICT_4X4_50, Kante 8 mm, Ursprung = Feldecke unten links)", st_small), t]
    Frame(m, m, W * mm - 2 * m, H * mm - 2 * m, showBoundary=0).addFromList(story, c)
```

- [ ] **Step 6: `_spec`, `build`, `__main__` umstellen**

```python
def _spec(fmt):
    p = PROFILES[fmt]
    size = p["page"]
    W, H = (v / mm for v in size)
    c = canvas.Canvas(io.BytesIO(), pagesize=size)
    if p["field"] == "grid":
        spec = mat_page(c, W, H, fmt, p["marker_mm"])
        c.showPage()
        spec["height_gauge"] = strip_page(c, W, H, fmt)
    else:
        spec = k60_page(c, W, H, fmt)
    spec.update(_profile_fields(fmt))
    return spec


def layout(fmt):
    """Markerlayout und Profil eines Messformats (ohne PDF zu speichern)."""
    with _LOCK:
        return _spec(fmt)


def build(out, fmt="A4", pages=None, header=""):
    """PDF eines Druckformats erzeugen. out = Pfad oder Datei-Objekt. Rueckgabe: Layout (A4/A3) bzw.
    {"K60H": Layout, "K60D": Layout}. pages: Auswahl aus PRINT_PAGES[fmt]; leer oder ohne Treffer = alle Seiten."""
    global _HEADER
    if fmt not in PRINT_FORMATS:
        raise ValueError("Format muss A4, A3 oder K60 sein")
    allowed = PRINT_PAGES[fmt]
    pages = [p for p in allowed if p in (pages or ())] or list(allowed)
    size = PROFILES[PRINT_FORMATS[fmt][0]]["page"]
    W, H = (v / mm for v in size)
    with _LOCK:
        _HEADER = (header or "").strip()[:60]
        try:
            spec = {f: _spec(f) for f in PRINT_FORMATS[fmt]} if fmt == "K60" else _spec(fmt)
            c = canvas.Canvas(out, pagesize=size)
            c.setTitle("Messunterlage Kleinteile" if fmt == "K60" else f"Messunterlage {fmt}")
            for p in pages:
                if p == "mat" and fmt == "K60":
                    k60_page(c, W, H, "K60H")
                elif p == "mat":
                    mat_page(c, W, H, fmt, PROFILES[fmt]["marker_mm"])
                elif p == "dark":
                    k60_page(c, W, H, "K60D")
                elif p == "gauge":
                    strip_page(c, W, H, fmt)
                elif fmt == "K60":
                    k60_guide_page(c, W, H, spec)
                else:
                    guide_page(c, W, H, fmt, spec)
                c.showPage()
            c.save()
        finally:
            _HEADER = ""
    return spec


if __name__ == "__main__":
    out = sys.argv[1]
    specs = {f: build(f"{out}/Messunterlage_{f}.pdf", f) for f in PRINT_FORMATS}
    print(json.dumps(specs, indent=1))
```

`generator/make_mat.py`: Import `from core.matgen import PRINT_FORMATS, build` und `specs = {f: build(f"{out}/Messunterlage_{f}.pdf", f) for f in PRINT_FORMATS}`.

Vor dem Lauf: `grep -rn "matgen.FORMATS\[\|FORMATS\[" core web tools generator tests` – außer `matgen.py` selbst darf niemand `FORMATS[fmt]` als Tupel `(Seite, Kante)` lesen; Fundstellen auf `PROFILES[fmt]["page"]` / `["marker_mm"]` umstellen.

- [ ] **Step 7: Tests laufen lassen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_core.py tests/test_golden_a4a3.py`
Expected: PASS (alle bisherigen und neuen Tests in `test_core.py`, 15 Goldwert-Tests). Sichtprüfung: `python generator/make_mat.py $SP/kleinteile/pdf > /dev/null` (vorher `mkdir -p $SP/kleinteile/pdf`), dann Seite 1 und 2 von `Messunterlage_K60.pdf` mit 6 px/mm rendern und ansehen (Read auf ein PNG): Feld frei von Linien, Skala außen, Marker ohne Überlappung mit Beschriftungen.

- [ ] **Step 8: Ruff und Commit**

```bash
ruff check core/matgen.py generator/make_mat.py tests/test_core.py
git add core/matgen.py generator/make_mat.py tests/test_core.py
git commit -m "Kleinteile: Formatprofile, Druckformat K60 mit Blatt hell/dunkel und Anleitung"
```

---

### Task 3: Synthetische Kleinteile-Fotos und Erkennung/Entzerrung (`tests/conftest.py`, `core/vision.py`)

**Files:**
- Modify: `tests/conftest.py` (`_render_k60` neu, `synthetic_photo` erweitert)
- Modify: `core/vision.py` (Import, `spec`-Cache, `rect_pxmm`, `verdict`, `_pick`, `analyze`, `rectify_mat`, `bottom_warp_matrix`, `bottom_warp`)
- Create: `tests/test_kleinteile.py` (Abschnitt „Erkennung“; spätere Tasks ergänzen weitere Abschnitte)

**Interfaces:**
- Consumes: `matgen.PROFILES`, `FORMATS`, `SIBLING`, `layout` (Task 2).
- Produces:
  - `conftest._render_k60(fmt: str, px: float) -> tuple[np.ndarray, tuple[float, float]]` – Ausschnitt Feld + 30 mm Rand, Rückgabe (BGR-Bild, Feldursprung im Bild in mm von unten links = `(30.0, 30.0)`).
  - `conftest.synthetic_photo("K60H" | "K60D", objects=[…])` – Objekte in mm des Feldes; gerendert mit 30 px/mm; `page` wird bei K60 ignoriert; `objects=None` bei K60 = keine Objekte.
  - `vision.rect_pxmm(a: dict | None) -> float`; `vision.verdict(n_markers, max_err, quality=(0.5, 1.0))`; `vision.analyze(img, fmt=None)` mit `format_note` (nur wenn F4 umschaltet); `vision.rectify_mat(img, H, fmt, pxmm=None)`; `vision.bottom_warp_matrix(analysis_bot, analysis_top, pxmm_out=None)`; `vision.bottom_warp(rect_bot, analysis_bot, analysis_top=None, pxmm_out=None)`.

- [ ] **Step 1: `conftest.py` erweitern** – nach `_render_page` einfügen:

```python
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
```

In `synthetic_photo` die Zeilen von `px = 6.0` bis vor `for o in objects if shadow else []:` ersetzen durch:

```python
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
```

(Der Rest der Funktion – Schatten, Objekte, Verzerrung, Unschärfe, JPEG – bleibt wörtlich; die Einrückung des Objektblocks bleibt unter dem `elif`.) Am Ende vor `return data.tobytes()` ergänzen: `assert not k60 or len(data) < 8 * 1024 * 1024, "K60-Testfoto über dem Upload-Limit der Tests"`.

- [ ] **Step 2: Tests schreiben** – `tests/test_kleinteile.py` anlegen:

```python
"""Kleinteile-Unterlage K60 (Spec 2026-10-21-kleinteile): Erkennung, Kanten, Teile, API."""
import math

import numpy as np
import pytest

from conftest import H, _render_k60, _render_page, synthetic_photo
from core import matgen, vision

# ------------------------------------------------------------------ Erkennung und Entzerrung (§2)


@pytest.mark.parametrize("f", ["K60H", "K60D"])
def test_k60_formaterkennung_auto(f):
    img = vision.load_image(synthetic_photo(f))
    a = vision.analyze(img)
    assert a["format"] == f and a["format_auto"] is True and "format_note" not in a
    assert a["mat_ids"] == list(matgen.PROFILES[f]["ids"]) and a["missing_ids"] == []
    assert a["status"] == "gut" and a["max_err_mm"] <= 0.125
    assert a["gauge"] is None
    rect = vision.rectify_mat(img, a["homography"], f)
    assert rect.shape[:2] == (2400, 1800)  # 30 px/mm, genau das Feld
    med = float(np.median(rect))
    assert (med > 200) if f == "K60H" else (med < 70)


def test_k60_auf_a4_unterlage_gewinnt():
    sheet = _render_page("A4", 0, 6.0)
    small, _ = _render_k60("K60H", 6.0)
    Hs, Ws = sheet.shape[:2]
    h, w = small.shape[:2]
    y0, x0 = (Hs - h) // 2, (Ws - w) // 2
    sheet[y0:y0 + h, x0:x0 + w] = small
    a = vision.analyze(sheet)
    assert len(set(a["found_ids"]) & set(range(8))) >= 4  # A4-Marker sind sichtbar
    assert a["format"] == "K60H" and a["status"] == "gut"


def test_k60_variante_vertauscht_schaltet_um():
    img = vision.load_image(synthetic_photo("K60D"))
    a = vision.analyze(img, "K60H")
    assert a["format"] == "K60D" and a["format_note"] == "Format auf Kleinteile dunkel geändert"
    assert a["format_auto"] is False and a["status"] == "gut"


def test_k60_explizit_ohne_passende_marker():
    a = vision.analyze(vision.load_image(synthetic_photo("A4", 0)), "K60H")
    assert a["format"] == "K60H" and a["status"] == "nicht_auswertbar" and a["homography"] is None
    assert a["mat_ids"] == [] and a["missing_ids"] == list(range(20, 28)) and "format_note" not in a


def test_k60_drei_marker_nicht_auswertbar():
    import cv2
    sheet, (ox, oy) = _render_k60("K60H", 12.0)
    h = sheet.shape[0]
    for k, (x, y) in matgen.layout("K60H")["centers_mm"].items():
        if int(k) >= 23:  # nur 20, 21, 22 bleiben
            cx, cy = int((x + ox) * 12), int(h - (y + oy) * 12)
            cv2.rectangle(sheet, (cx - 72, cy - 72), (cx + 72, cy + 72), (255, 255, 255), -1)
    a = vision.analyze(sheet)
    assert a["status"] == "nicht_auswertbar" and a["homography"] is None and a["format"] is None


def test_rect_pxmm_und_verdict():
    assert vision.rect_pxmm({"rect": {"pxmm": 30.0}}) == 30.0
    assert vision.rect_pxmm({"rect": {"w_mm": 60}}) == 10.0 and vision.rect_pxmm(None) == 10.0 and vision.rect_pxmm({}) == 10.0
    q = (0.125, 0.25)
    assert [vision.verdict(8, e, q) for e in (0.12, 0.2, 0.3)] == ["gut", "brauchbar", "unsicher"]
    assert [vision.verdict(8, e) for e in (0.5, 1.0, 1.01)] == ["gut", "brauchbar", "unsicher"]
    assert vision.verdict(3, 0.01, q) == "nicht_auswertbar"


def test_bottom_warp_k60_massstab_und_rand():
    a = {"format": "K60D", "rect": {"pxmm": 30.0, "w_mm": 60, "h_mm": 80, "w": 1800, "h": 2400}}
    out = vision.bottom_warp(np.zeros((10, 10, 3), np.uint8), a, a)
    assert out.shape == (2400, 1800, 3)
    assert tuple(int(v) for v in out[1200, 900]) == (34, 34, 34)  # ausserhalb des kleinen Bildes: Feldfarbe dunkel
    M = vision.bottom_warp_matrix(a, a)
    assert M[2, 2] == pytest.approx(1.0) and abs(M[0, 0]) == pytest.approx(1.0)  # gleiche pxmm: keine Skalierung
```

- [ ] **Step 3: Tests laufen lassen, sie scheitern**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py`
Expected: FAIL (`AttributeError: … rect_pxmm`, Format `None` bzw. falsches Rechteckbild).

- [ ] **Step 4: `core/vision.py` umstellen**

Import: `from .matgen import FORMATS, PROFILES, SIBLING, layout`. Cache: `@lru_cache(maxsize=8)` über `spec`.

Neu nach `spec`:

```python
def rect_pxmm(a: dict | None) -> float:
    """Massstab des Rechteckbilds eines Fotos (px/mm); Rueckfall 10 fuer Fotos ohne gespeichertes pxmm."""
    return float(((a or {}).get("rect") or {}).get("pxmm") or PX_PER_MM)
```

`verdict` ersetzen:

```python
def verdict(n_markers: int, max_err: float | None, quality: tuple = (0.5, 1.0)) -> str:
    if n_markers < 4 or max_err is None:
        return "nicht_auswertbar"
    if max_err <= quality[0]:
        return "gut"
    if max_err <= quality[1]:
        return "brauchbar"
    return "unsicher"


def _pick(found: dict, fmt: str | None) -> tuple[list[str], str | None]:
    """Kandidaten fuer die Entzerrung und Hinweis (Spec Kleinteile §2 und §7 F4)."""
    def n(f):
        return sum(1 for i in PROFILES[f]["ids"] if i in found)
    if fmt in FORMATS:
        if n(fmt) < 4 and fmt in SIBLING and n(SIBLING[fmt]) >= 4:
            sib = SIBLING[fmt]
            return [sib], f"Format auf {PROFILES[sib]['label']} geändert"
        return ([fmt] if n(fmt) >= 4 else []), None
    fams: dict[tuple, list[str]] = {}
    for f, p in PROFILES.items():
        fams.setdefault(p["ids"], []).append(f)
    seen = [fs for fs in fams.values() if n(fs[0]) >= 4]
    small = [fs for fs in seen if PROFILES[fs[0]]["field"] != "grid"]
    if small:  # ein Kleinteile-Blatt auf der grossen Unterlage ist Absicht
        best = max(n(fs[0]) for fs in small)
        return [f for fs in small if n(fs[0]) == best for f in fs], None
    return (seen[0] if seen else []), None
```

`analyze` ersetzen (Höhenlehren-Teil wie bisher, nur mit Profilprüfung):

```python
def analyze(img: np.ndarray, fmt: str | None = None) -> dict:
    """Komplette Auswertung eines Fotos. fmt=None -> Format an der Marker-Familie erkennen (Spec Kleinteile §2)."""
    found = detect(img)
    h, w = img.shape[:2]
    res: dict = {"width": w, "height": h, "found_ids": sorted(found)}
    cands, note = _pick(found, fmt)
    if cands:
        scored = []
        for f in cands:
            ids = sorted(i for i in PROFILES[f]["ids"] if i in found)
            obj = mat_object_points(f)
            H = _fit(found, obj, ids)
            scored.append((_rms(H, found, obj, ids), f, H, obj, ids))
        rms, f, H, obj, ids = min(scored, key=lambda t: t[0])
        res["mat_ids"] = ids
        res["missing_ids"] = [i for i in PROFILES[f]["ids"] if i not in found]
        loo = _loo(found, obj, ids)
        max_err = max(loo.values()) if loo else rms
        res.update(format=f, format_auto=fmt not in FORMATS, homography=H.tolist(), rms_mm=round(rms, 3),
                   loo_mm={str(k): round(v, 3) for k, v in loo.items()}, max_err_mm=round(max_err, 3))
        if note:
            res["format_note"] = note
    else:
        f0 = fmt if fmt in FORMATS else None
        all_ids = PROFILES[f0]["ids"] if f0 else tuple(range(8))
        res["mat_ids"] = sorted(i for i in found if i in all_ids)
        res["missing_ids"] = [i for i in all_ids if i not in found]
        res.update(format=f0, homography=None, rms_mm=None, loo_mm={}, max_err_mm=None)
    quality = PROFILES[res["format"]]["quality_mm"] if res["format"] else (0.5, 1.0)
    res["status"] = verdict(len(res["mat_ids"]), res["max_err_mm"], quality)

    # Hoehenlehre (nur A4/A3)
    g = None
    f = res["format"] or "A4"
    if PROFILES[f]["gauge"]:
        for strip, ids in GAUGE_STRIPS.items():
            have = [i for i in ids if i in found]
            if have and (g is None or len(have) > len(g["ids"])):
                g = {"strip": strip, "ids": have}
        if g:
            obj = gauge_object_points(f, g["strip"])
            Hg = _fit(found, obj, g["ids"])
            g["homography"] = Hg.tolist()
            g["rms_mm"] = round(_rms(Hg, found, obj, g["ids"]), 3)
            g["vlen_mm"] = spec(f)["height_gauge"]["vlen_mm"]
    res["gauge"] = g
    return res
```

`rectify_mat`:

```python
def rectify_mat(img: np.ndarray, H, fmt: str, pxmm: float | None = None) -> np.ndarray:
    pxmm = pxmm or PROFILES[fmt]["pxmm"]
    gw, gh = spec(fmt)["grid_mm"]
    to_px = _px_matrix(pxmm, gh)
    return cv2.warpPerspective(img, to_px @ np.asarray(H), (int(gw * pxmm), int(gh * pxmm)),
                               flags=cv2.INTER_CUBIC, borderValue=PROFILES[fmt]["border_bgr"])
```

`bottom_warp_matrix` / `bottom_warp`:

```python
def bottom_warp_matrix(analysis_bot: dict, analysis_top: dict | None, pxmm_out: float | None = None) -> np.ndarray:
    """3x3-Pixelabbildung rect.jpg (Unteransicht) -> Draufsicht-Raster: S_top · lage_matrix · S_bot^-1.
    pxmm_out=None: Massstab der Draufsicht (bzw. der Unteransicht ohne Draufsicht)."""
    pxmm_out = pxmm_out or rect_pxmm(analysis_top or analysis_bot)
    rb = analysis_bot["rect"]
    al = analysis_bot.get("bottom_align") or {"rot": 0, "dx": 0.0, "dy": 0.0}
    rt = (analysis_top or analysis_bot)["rect"]
    L = lage_matrix(al["rot"], al["dx"], al["dy"], rb["w_mm"], rb["h_mm"], al.get("phi") or 0.0)
    return _px_matrix(pxmm_out, rt["h_mm"]) @ L @ np.linalg.inv(_px_matrix(rb["pxmm"], rb["h_mm"]))


def bottom_warp(rect_bot: np.ndarray, analysis_bot: dict, analysis_top: dict | None = None,
                pxmm_out: float | None = None) -> np.ndarray:
    ref = analysis_top or analysis_bot
    pxmm_out = pxmm_out or rect_pxmm(ref)
    rt = ref["rect"]
    M = bottom_warp_matrix(analysis_bot, analysis_top, pxmm_out)
    border = PROFILES.get(ref.get("format"), PROFILES["A4"])["border_bgr"]
    return cv2.warpAffine(rect_bot, M[:2], (int(rt["w_mm"] * pxmm_out), int(rt["h_mm"] * pxmm_out)),
                          flags=cv2.INTER_LINEAR, borderValue=border)
```

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py tests/test_core.py tests/test_align.py tests/test_golden_a4a3.py`
Expected: PASS.

- [ ] **Step 6: Ruff und Commit**

```bash
ruff check core/vision.py tests/conftest.py tests/test_kleinteile.py
git add core/vision.py tests/conftest.py tests/test_kleinteile.py
git commit -m "Kleinteile: Formaterkennung nach Marker-Familie, Entzerrung mit Profil, synthetische K60-Fotos"
```

---

### Task 4: Kantenerkennung mit Maßstab (`core/edges.py`, reiner Umbau)

**Files:**
- Modify: `core/edges.py`
- Test: `tests/test_kleinteile.py` (Abschnitt „Maßstab“)

**Interfaces:**
- Consumes: `vision.spec(fmt)` mit `pxmm`, `edge_scale`, `field`, `hole_max_mm2`, `marker_pos` (Task 2/3).
- Produces: `edges.Scale` (frozen dataclass: `pxmm`, `work`, `k`, `field`, `hole_max`, `frame`), `edges.scale_of(fmt) -> Scale`; `detect(...)` liefert zusätzlich `edge_scale` (= `k`), `px_per_mm` = `pxmm` des Profils. Alle internen Funktionen nehmen `sc: Scale`. Für A4/A3 ändert sich kein Ergebnis (Goldwerte).

- [ ] **Step 1: Test schreiben** (an `tests/test_kleinteile.py` anhängen)

```python
# ------------------------------------------------------------------ Kantenmassstab (§3)


def test_scale_of_profile():
    from core import edges
    a4, k = edges.scale_of("A4"), edges.scale_of("K60D")
    assert (a4.pxmm, a4.work, a4.k, a4.field, a4.hole_max, a4.frame) == (10.0, 4.0, 1.0, "grid", 2000.0, False)
    assert (k.pxmm, k.work, k.k, k.field, k.frame) == (30.0, 16.0, 0.25, "plain_dark", True)
    assert k.hole_max == pytest.approx(1256.6, abs=0.1)
```

- [ ] **Step 2: Test laufen lassen, er scheitert**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py -k scale_of`
Expected: FAIL (`AttributeError: module 'core.edges' has no attribute 'scale_of'`).

- [ ] **Step 3: `Scale` und `scale_of`** – nach den Konstanten einfügen (`from dataclasses import dataclass` zu den Importen; Modulkonstanten bleiben als Grundwerte für `k = 1` stehen, Kopfkommentar Zeile 3: „Eingabe: rect.jpg (Massstab aus dem Profil, genau die Feldflaeche)“):

```python
@dataclass(frozen=True)
class Scale:
    """Massstab eines Messformats (Spec Kleinteile §3): Laengen in mm mal k, Flaechen mal k²."""
    pxmm: float       # Rechteckbild px/mm
    work: float       # Arbeitsaufloesung der Maske px/mm (WORK_PXMM / k)
    k: float          # Kantenmassstab
    field: str        # grid | plain_light | plain_dark
    hole_max: float   # groesste Bohrung in mm²
    frame: bool       # Marker im Rahmen ausserhalb des Feldes


def scale_of(fmt: str) -> Scale:
    sp = spec(fmt)
    k = float(sp["edge_scale"])
    return Scale(float(sp["pxmm"]), WORK_PXMM / k, k, sp["field"], float(sp["hole_max_mm2"]), sp["marker_pos"] == "frame")
```

- [ ] **Step 4: Alle Stellen umstellen** – jede Funktion bekommt `sc: Scale` als letzten Parameter (vor optionalen), alle Aufrufer reichen `sc` weiter; `detect` ruft einmal `sc = scale_of(fmt)`. Ersetzungen (alte Zeilennummern von ff95d9b; `W` steht für `sc.work`, `px` für `sc.pxmm`):

| Zeile | Funktion | alt | neu |
|---|---|---|---|
| 48 | `_marker_mask(fmt, shape, pxmm)` | Signatur | `_marker_mask(fmt, shape, pxmm, sc)`; erste Zeile im Rumpf: `if sc.frame: return np.full(shape, 255, np.uint8)` (Marker liegen außerhalb des Feldes) |
| 53 | `_marker_mask` | `half = sp["marker_size_mm"] / 2 + 2` | `half = sp["marker_size_mm"] / 2 + 2 * sc.k` |
| 61, 65 | `_drop_small(mask, pxmm)` | `>= MIN_AREA_MM2` | Signatur `_drop_small(mask, pxmm, sc)`, Bedingung `>= MIN_AREA_MM2 * sc.k ** 2` |
| 70, 77 | `_grabcut(...)` | `m = int(10 * WORK_PXMM)` | Signatur `+ sc`; `m = int(10 * sc.k * sc.work)` |
| 95 | `_grabcut` | `_drop_small(out, WORK_PXMM)` | `_drop_small(out, sc.work, sc)` |
| 99–117 | `_grid_demod(rect)` | `PX_PER_MM` (4×) | Signatur `_grid_demod(rect, sc)`; jedes `PX_PER_MM` → `sc.pxmm` |
| 122–136 | `_grid_energy(rect, win_mm=…, smooth_mm=…, demod=None)` | `PX_PER_MM`, `WORK_PXMM`, `_grid_demod(rect)` | Signatur `_grid_energy(rect, sc, win_mm=GRID_WIN_MM, smooth_mm=GRID_SMOOTH_MM, demod=None)`; `box = _odd(win_mm * sc.k * sc.pxmm)`; `resize` mit `sc.work / sc.pxmm`; `k = _odd(smooth_mm * sc.k * sc.work)`; `_grid_demod(rect, sc)` |
| 140, 148 | `_fill_small(mask, max_mm2)` | `area / WORK_PXMM ** 2 <= max_mm2` | Signatur `_fill_small(mask, max_mm2, sc)`; `area / sc.work ** 2 <= max_mm2` (Aufrufer übergeben `max_mm2` schon skaliert) |
| 170 | `_mask(rect, fmt, hints)` | Signatur | `_mask(rect, fmt, hints, sc)` |
| 180 | `_mask` | `s = WORK_PXMM / PX_PER_MM` | `s = sc.work / sc.pxmm` |
| 183 | `_mask` | `_marker_mask(fmt, (h, w), WORK_PXMM)` | `_marker_mask(fmt, (h, w), sc.work, sc)` |
| 184 | `_mask` | `_odd(1.5 * WORK_PXMM)` | `_odd(1.5 * sc.k * sc.work)` |
| 187 | `_mask` | `b = int(8 * WORK_PXMM)` | `b = int(8 * sc.k * sc.work)` |
| 195 | `_mask` | `_odd((GRID_WIN_MM + GRID_SMOOTH_MM) * WORK_PXMM)` | `_odd((GRID_WIN_MM + GRID_SMOOTH_MM) * sc.k * sc.work)` |
| 196–197 | `_mask` | `_grid_demod(rect)`, `_grid_energy(rect, demod=demod)` | `_grid_demod(rect, sc)`, `_grid_energy(rect, sc, demod=demod)` |
| 202 | `_mask` | `_grid_energy(rect, GRID_FINE_MM, GRID_FINE_MM, demod)` | `_grid_energy(rect, sc, GRID_FINE_MM, GRID_FINE_MM, demod)` |
| 216 | `_mask` | `_mask_transparent(color, valid)` | `_mask_transparent(color, valid, sc)` |
| 227 | `_mask` | `_fill_small(_drop_small(nogrid, WORK_PXMM), FILL_MM2)` | `_fill_small(_drop_small(nogrid, sc.work, sc), FILL_MM2 * sc.k ** 2, sc)` |
| 232 | `_mask` | `_grabcut(_drop_small(mask, WORK_PXMM), closed, sure_fg, sure_bg)` | `_grabcut(_drop_small(mask, sc.work, sc), closed, sure_fg, sure_bg, sc)` |
| 233 | `_mask` | `_fill_unround(out, valid)` | `_fill_unround(out, valid, sc)` |
| 236 | `_mask` | `_drop_small(res[0], WORK_PXMM)` | `_drop_small(res[0], sc.work, sc)` |
| 241, 244 | `_mask_transparent(color, valid)` | `_odd(TRANSP_CLOSE_MM * WORK_PXMM)` | Signatur `+ sc`; `_odd(TRANSP_CLOSE_MM * sc.k * sc.work)`; `_fill_unround(m, valid, sc)` |
| 255–268 | `_fill_unround(mask, valid)` | `WORK_PXMM` (2×), `HOLE_MAX_MM2` | Signatur `+ sc`; `sc.work`; `area <= sc.hole_max` |
| 275–320 | `_refine(poly, gx, gy, gh)` | `px = PX_PER_MM`; `SEARCH_MM * px` (2×); `L < 5 * px`; `np.arange(2 * px, L - 2 * px, px / 2)`; `MAX_SHIFT_MM * px` | Signatur `+ sc`; `px = sc.pxmm`; `SEARCH_MM * sc.k * px`; `L < 5 * sc.k * px`; `np.arange(2 * sc.k * px, L - 2 * sc.k * px, sc.k * px / 2)`; `MAX_SHIFT_MM * sc.k * px`. Der `0.5`-Schritt von `offs` und die Schwelle `40` bleiben. |
| 326–328 | `_refine_hole(c, d0, gray, gh)` | `px = PX_PER_MM` | Signatur `+ sc`; `px = sc.pxmm` |
| 359–370 | `_holes(cnts, hier, gray, gh)` | `WORK_PXMM` (4×), `area < math.pi`, `_refine_hole(...)` | Signatur `+ sc`; `sc.work`; `area < math.pi * sc.k ** 2` (Kommentar „Ø < 2 mm · k“); `_refine_hole(c_mm, d0, gray, gh, sc)` |
| 376–391 | `_try_merge(a, b)` | `>= 1.0`, `L + 2`, `< -2` | Signatur `_try_merge(a, b, k=1.0)`; `>= 1.0 * k`; `lo_b > L + 2 * k or hi_b < -2 * k` |
| 397 | `_merge(segs)` | `_try_merge(segs[i], segs[j])` | `_merge(segs, k=1.0)`; `_try_merge(segs[i], segs[j], k)` |
| 419–439 | `_segments(gray, mask_full, gh)` | `px = PX_PER_MM`; `_odd(3 * px)`; `< 2 * px`; `_merge(segs)`; `>= MIN_SEG_MM` | Signatur `+ sc`; `px = sc.pxmm`; `_odd(3 * sc.k * px)`; `< 2 * sc.k * px`; `_merge(segs, sc.k)`; `>= MIN_SEG_MM * sc.k` |
| 443–449 | `detect` | — | nach `hints = hints or {}`: `sc = scale_of(fmt)`; `_mask(rect, fmt, hints, sc)` |
| 462–465 | `detect` | `WORK_PXMM`, `MIN_AREA_MM2`, `APPROX_MM * WORK_PXMM` | `sc.work`; `MIN_AREA_MM2 * sc.k ** 2`; `APPROX_MM * sc.k * sc.work` |
| 467 | `detect` | `eps < 8 * WORK_PXMM` | `eps < 8 * sc.k * sc.work` |
| 472–478 | `detect` | `WORK_PXMM` (5×), `_refine(coarse, gx, gy, gh)`, `_holes(hc, hh[0], gray, gh)` | `sc.work`; `_refine(coarse, gx, gy, gh, sc)`; `_holes(hc, hh[0], gray, gh, sc)` |
| 486 | `detect` | `_segments(gray, full, gh)` | `_segments(gray, full, gh, sc)` |
| 497 | `detect` | `"px_per_mm": PX_PER_MM` | `"px_per_mm": sc.pxmm, "edge_scale": sc.k` |

Danach: `grep -n "WORK_PXMM\|PX_PER_MM\|HOLE_MAX_MM2\|MIN_AREA_MM2\|FILL_MM2" core/edges.py` zeigt nur noch die Konstantendefinitionen, den Import (`PX_PER_MM` wird nicht mehr gebraucht → aus dem Import entfernen, falls ruff F401 meldet) und `scale_of`. `grep -rn "edges\._\(mask\|refine\|holes\|segments\|grid_energy\|fill_small\|drop_small\)" tests web` – rufen Tests interne Funktionen direkt auf, bekommen sie `edges.scale_of("A4")` als `sc` übergeben (das ist keine Teständerung im Sinne der Global Constraints, sondern Anpassung an die neue Signatur; im Report nennen).

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_golden_a4a3.py tests/test_edges.py tests/test_align.py tests/test_kleinteile.py -k "not k60_kanten"`
Expected: PASS – insbesondere alle 15 Goldwert-Tests (A4/A3 unverändert).

- [ ] **Step 6: Ruff und Commit**

```bash
ruff check core/edges.py tests/test_kleinteile.py
git add core/edges.py tests/test_kleinteile.py
git commit -m "Kleinteile: Kantenerkennung rechnet mit Massstab aus dem Profil (A4/A3 unveraendert)"
```

---
### Task 5: Weg „Feldfarbe“ für Felder ohne Raster (`core/edges.py`)

**Files:**
- Modify: `core/edges.py` (`_mask_plain` neu, Weiche in `_mask`, Bohrungs-Zugehörigkeit in `detect`)
- Test: `tests/test_kleinteile.py` (Abschnitt „Kanten K60“)

**Interfaces:**
- Consumes: `Scale`, `scale_of`, `_paper_fit`, `_drop_small`, `_grabcut`, `_fill_unround`, `_fill_small`, `_mask_transparent`, `_odd` (Task 4); `synthetic_photo("K60H"|"K60D", objects=…)` (Task 3).
- Produces: `detect(rect, "K60H"|"K60D", hints)` mit Umrissen, Bohrungen (`holes[].d`), Kanten; Raster-Weg unverändert (Goldwerte).

- [ ] **Step 1: Tests schreiben** (an `tests/test_kleinteile.py` anhängen)

```python
# ------------------------------------------------------------------ Kanten K60 (§3 Weg „Feldfarbe“)


def _k60_rect(fmt, objects):
    img = vision.load_image(synthetic_photo(fmt, objects=objects))
    a = vision.analyze(img, fmt)
    assert a["format"] == fmt and a["status"] == "gut"
    return vision.rectify_mat(img, a["homography"], fmt)


def _sides(poly):
    return sorted(math.dist(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _rect_ok(res, w, h, tol=0.1):
    assert len(res["outlines"]) == 1, res["outlines"]
    s = _sides(res["outlines"][0]["polygon"])
    assert len(s) == 4, res["outlines"][0]["polygon"]
    want = sorted([w, w, h, h])
    assert all(abs(a - b) <= tol for a, b in zip(s, want, strict=True)), (s, want)


def test_k60_kanten_quadrat_3mm():
    from core import edges
    res = edges.detect(_k60_rect("K60H", [{"rect": [28.5, 38.5, 3, 3], "gray": 60}]), "K60H")
    _rect_ok(res, 3, 3)
    assert res["px_per_mm"] == 30.0 and res["edge_scale"] == 0.25


@pytest.mark.parametrize("fmt,plate,hole", [("K60H", 90, 245), ("K60D", 220, 34)])
def test_k60_kanten_platte_mit_bohrung_1mm(fmt, plate, hole):
    from core import edges
    res = edges.detect(_k60_rect(fmt, [{"rect": [20, 34, 20, 12], "gray": plate}, {"circle": [30, 40, 1.0], "gray": hole}]), fmt)
    _rect_ok(res, 20, 12)
    assert len(res["holes"]) == 1, res["holes"]
    h = res["holes"][0]
    assert abs(h["d"] - 1.0) <= 0.1 and math.dist(h["c"], [30, 40]) <= 0.1, h


def test_k60_kanten_helles_teil_auf_dunkel():
    from core import edges
    _rect_ok(edges.detect(_k60_rect("K60D", [{"rect": [15, 30, 30, 20], "gray": 230}]), "K60D"), 30, 20)


def test_k60_kanten_durchscheinend_auf_dunkel():
    from core import edges
    rect = _k60_rect("K60D", [{"rect": [15, 30, 30, 20], "gray": 230, "alpha": 0.5}])
    _rect_ok(edges.detect(rect, "K60D", {"transparent": 2}), 30, 20)


def test_k60_kanten_dunkles_teil_auf_hell():
    from core import edges
    _rect_ok(edges.detect(_k60_rect("K60H", [{"rect": [15, 30, 30, 20], "gray": 60}]), "K60H"), 30, 20)


def test_k60_teil_ueber_feldrand():
    from core import edges
    res = edges.detect(_k60_rect("K60H", [{"rect": [50, 30, 20, 10], "gray": 60}]), "K60H")  # ragt 10 mm ueber den Rand
    for o in res["outlines"]:
        assert all(-0.5 <= x <= 60.5 and -0.5 <= y <= 80.5 for x, y in o["polygon"]), o["polygon"]


def test_k60_falsche_variante_wenig_kontrast():
    from core import edges
    res = edges.detect(_k60_rect("K60D", [{"rect": [15, 30, 30, 20], "gray": 45}]), "K60D")
    assert res["contrast"] is None or res["contrast"] < 12, res["contrast"]
```

- [ ] **Step 2: Tests laufen lassen, sie scheitern**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py -k k60_kanten`
Expected: FAIL (Raster-Weg findet auf dem Feld ohne Raster das ganze Feld oder nichts; die Bohrung fehlt).

- [ ] **Step 3: `_mask_plain` und Weiche** – vor `_mask` einfügen:

```python
def _mask_plain(rect: np.ndarray, hints: dict, sc: Scale) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Objektmaske auf einem Feld ohne Raster (Spec Kleinteile §3 „Feldfarbe“): Feldfarbe aus dem Randstreifen,
    Farbabstand beidseitig (hell auf dunkel und dunkel auf hell). Kein Rasterkriterium, kein Schatten-Veto.
    Rueckgabe wie _mask."""
    t = hints.get("transparent", 0)
    light = bool(hints.get("light", False))
    s = sc.work / sc.pxmm
    small = cv2.resize(rect, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    valid = np.full((h, w), 255, np.uint8)
    k = _odd(1.5 * sc.k * sc.work)
    closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    lab = cv2.cvtColor(closed, cv2.COLOR_BGR2LAB).astype(np.float32)
    b = int(8 * sc.k * sc.work)
    band = np.zeros((h, w), bool)
    band[:b] = True
    band[-b:] = True
    band[:, :b] = True
    band[:, -b:] = True
    field = _paper_fit(lab, band)
    dl = np.abs(field[..., 0] - lab[..., 0])
    dc = np.hypot(lab[..., 1] - field[..., 1], lab[..., 2] - field[..., 2])
    diff = np.clip(dl + 2 * dc, 0, 255).astype(np.uint8)
    th, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if t == 2:
        color = diff > max(TRANSP_DIFF_FACTOR * th, TRANSP_MIN_DIFF)
        return _mask_transparent(color, valid, sc), np.where(color, 255, 0).astype(np.uint8), diff
    if t == 1:
        thr = max(TRANSP_DIFF_FACTOR * th, TRANSP_MIN_DIFF)
    elif light:
        thr = max(LIGHT_DIFF_FACTOR * th, LIGHT_MIN_DIFF)
    else:
        thr = max(th, COLOR_MIN_DIFF)
    color = diff > thr
    mask = np.where(color, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    sure_fg = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    out = _grabcut(_drop_small(mask, sc.work, sc), closed, sure_fg, band, sc)
    return _fill_unround(out, valid, sc), np.where(color, 255, 0).astype(np.uint8), diff
```

In `_mask` als erste Anweisung nach dem Docstring: `if sc.field != "grid": return _mask_plain(rect, hints, sc)`.

- [ ] **Step 4: Bohrungs-Zugehörigkeit** – in `detect` den Block `inside = [h for h in _holes(…) if mask[…] > 0]` so ändern, dass auf Feldern ohne Raster gegen die Maske mit gefüllten eingeschlossenen Lücken bis zur Bohrungs-Obergrenze geprüft wird (der Raster-Weg prüft wie bisher gegen `mask`):

```python
        if hc:
            # Raster-Weg: das Rasterkriterium fuellt Bohrungen in der Maske; ohne Raster bleiben sie offen
            member = mask if sc.field == "grid" else _fill_small(mask, sc.hole_max, sc)
            inside = [h for h in _holes(hc, hh[0], gray, gh, sc)
                      if member[min(member.shape[0] - 1, int((gh - h["c"][1]) * sc.work)),
                                min(member.shape[1] - 1, int(h["c"][0] * sc.work))] > 0]
            holes = inside
```

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py tests/test_golden_a4a3.py tests/test_edges.py`
Expected: PASS. Scheitert ein K60-Genauigkeitstest: Global Constraints „Kantenerkennung K60“ (Ursache suchen, Toleranz bleibt).

- [ ] **Step 6: Ruff und Commit**

```bash
ruff check core/edges.py tests/test_kleinteile.py
git add core/edges.py tests/test_kleinteile.py
git commit -m "Kleinteile: Kantenerkennung auf Feldern ohne Raster (Weg Feldfarbe, Bohrungen bis Profilgrenze)"
```

---

### Task 6: Teile und Eckpunkte mit Maßstab (`web/app/parts.py`, `web/app/main.py`)

**Files:**
- Modify: `web/app/parts.py` (`edge_scale` neu; `auto_dims`, `transfer_ids`, `update_edge_ids`, `transfer_holes`, `snap_polygon`, `assign`, `default_unc`, `set_polygon`, `_sync_auto`, `refresh`, `ai_parts`)
- Modify: `web/app/main.py` (`inside` in `photo_edges`, `_polygon`)
- Test: `tests/test_kleinteile.py` (Abschnitt „Teile“)

**Interfaces:**
- Consumes: `matgen.edge_scale(fmt)` (Task 2); `detect(...)["edge_scale"]` (Task 4).
- Produces: `parts.edge_scale(fmt) -> float` (funktionslokaler Import von `core.matgen`); zusätzlicher Parameter `k: float = 1.0` (immer letzter, mit Standardwert) an `auto_dims(data, fx=1.0, fy=1.0, k=1.0)`, `transfer_ids(old_poly, old_ids, new_poly, next_id, k=1.0)`, `update_edge_ids(..., k=1.0)` (reicht `k` an `transfer_ids` weiter), `transfer_holes(old_holes, new_holes, next_id, k=1.0)`, `snap_polygon(poly, segments, preferred=(), k=1.0)`, `assign(points, parts, k=1.0)`. `plausible` behält seine Signatur, `ai_parts` übergibt `min_area=25.0 * k ** 2`.

- [ ] **Step 1: Tests schreiben** (an `tests/test_kleinteile.py` anhängen)

```python
# ------------------------------------------------------------------ Teile (§3 Zuordnung, F2)

SQ = [[28.5, 38.5], [31.5, 38.5], [31.5, 41.5], [28.5, 41.5]]  # 3 x 3 mm


def test_k60_teile_plausible():
    from app import parts
    assert not parts.plausible(SQ, [{"polygon": SQ}])                       # A4-Grenze 25 mm²
    assert parts.plausible(SQ, [{"polygon": SQ}], min_area=25.0 * 0.25 ** 2)


def test_k60_teile_schwellen_skaliert():
    from app import parts
    moved = [[x + 1.0, y] for x, y in SQ]                                    # 1 mm verschoben
    assert parts.transfer_ids(SQ, [1, 2, 3, 4], moved, 5)[0] == [1, 2, 3, 4]
    assert parts.transfer_ids(SQ, [1, 2, 3, 4], moved, 5, k=0.25)[0] == [5, 6, 7, 8]
    old = [{"id": 1, "c": [30, 40], "d": 1.0}]
    assert parts.transfer_holes(old, [{"c": [31.0, 40], "d": 1.0}], 2)[0][0]["id"] == 1
    assert parts.transfer_holes(old, [{"c": [31.0, 40], "d": 1.0}], 2, k=0.25)[0][0]["id"] == 2
    seg = [{"id": "K1", "a": [28.5, 37.5], "b": [31.5, 37.5]}]                # 1 mm unter der Unterkante
    assert parts.snap_polygon(SQ, seg)[0][0] == [28.5, 37.5]
    assert parts.snap_polygon(SQ, seg, k=0.25)[0][0] == [28.5, 38.5]
    assert parts.assign([[32.0, 40.0]], [(7, SQ)]) == 7                       # 0,5 mm ausserhalb
    assert parts.assign([[32.0, 40.0]], [(7, SQ)], k=0.25) is None
    uneven = {"polygon": [[0, 0], [10, 0], [10, 5], [0, 5.5]], "edge_ids": [1, 2, 3, 4], "hidden": [], "holes": []}
    assert parts.is_rect(uneven["polygon"])                                  # Winkel weichen 2,9° ab (< 4°)
    warn = "gegenüberliegende Kanten ungleich – Kante prüfen"                # links 5,5 mm, rechts 5 mm
    assert warn not in [d["warn"] for d in parts.auto_dims(uneven)]          # 0,5 mm < 1 mm
    assert warn in [d["warn"] for d in parts.auto_dims(uneven, k=0.25)]      # 0,5 mm > 0,25 mm


def test_k60_teile_default_unc():
    from app import parts
    assert parts.default_unc({"format": "K60H", "max_err": 0.05, "analysis": "{}"}, "top") == 0.1
    assert parts.default_unc({"format": "K60H", "max_err": None, "analysis": "{}"}, "top") == 0.12
    assert parts.default_unc({"format": "A4", "max_err": 0.3, "analysis": "{}"}, "top") == 0.5
    assert parts.default_unc(None, "top") == 0.5
```

`default_unc` K60: `round((0.05 or 0.3 * 0.25) + 0.2 * 0.25, 2) == 0.1`; ohne `max_err`: `round(0.075 + 0.05, 2) == 0.12` (Python rundet 0.125 → 0.12).

- [ ] **Step 2: Tests laufen lassen, sie scheitern**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py -k k60_teile`
Expected: FAIL (`TypeError: … unexpected keyword argument 'k'`).

- [ ] **Step 3: `parts.py` umstellen**

```python
def edge_scale(fmt):
    """Kantenmassstab k des Messformats (Spec Kleinteile §3a); 1.0 ohne bekanntes Format."""
    from core import matgen  # spaet: main.py setzt sys.path erst nach den App-Importen
    return matgen.edge_scale(fmt)
```

Ersetzungen (je Funktion Parameter `k=1.0` ans Ende):

| Funktion | alt | neu |
|---|---|---|
| `auto_dims` | `> EDGE_DIFF_MM` | `> EDGE_DIFF_MM * k` |
| `update_edge_ids` | `return transfer_ids(old_poly, old_ids, new_poly, next_id)` | `return transfer_ids(old_poly, old_ids, new_poly, next_id, k)` |
| `transfer_ids` | `if d < 3 and …` | `if d < 3 * k and …` (Docstring: „Mitte < 3 mm · k“) |
| `transfer_holes` | `if d <= 2 and …` | `if d <= 2 * k and …` (Docstring: „<= 2 mm · k“) |
| `snap_polygon` | `if dist >= 3 or …`; `… > 8:` | `if dist >= 3 * k or …`; `… > 8 * k:` |
| `assign` | `P.buffer(ON_EDGE_MM)`; `<= ON_EDGE_MM` | `P.buffer(ON_EDGE_MM * k)`; `<= ON_EDGE_MM * k` |

`default_unc` (Höhenlehren-Zweig unverändert):

```python
def default_unc(photo, view):
    """Standard-Unsicherheit einer Fotomessung (vorher main._default_unc); Zuschlaege mit k des Fotoformats."""
    if not photo:
        return 0.5
    a = db.jload(photo["analysis"], {}) or {}
    if view == "gauge" and a.get("gauge"):
        return round((a["gauge"].get("rms_mm") or 0.3) * 2 + 0.3, 2)
    k = edge_scale(photo["format"])
    return round((photo["max_err"] or 0.3 * k) + 0.2 * k, 2)
```

Aufrufer:
- `set_polygon(part, polygon, …)`: am Anfang `k = edge_scale((db.q1("SELECT format FROM photos WHERE id=?", (part["photo_id"],)) or {}).get("format"))`; `transfer_ids(…, k)`, `update_edge_ids(…, k)`, `transfer_holes(…, k)`.
- `_sync_auto(part, photo, fx, fy)`: `auto_dims(d, fx, fy, edge_scale(photo["format"]) if photo else 1.0)`.
- `refresh`: im Zuordnungsschritt `assign(d["points"], by_photo[m["photo_id"]], edge_scale(photos[m["photo_id"]]["format"]) if m["photo_id"] in photos else 1.0)`.
- `ai_parts`: `k = res.get("edge_scale", 1.0)`; `snap_polygon(it["polygon"], res["segments"], it["edges"], k)`; `plausible(poly, res["outlines"], min_area=25.0 * k ** 2)`.

`grep -n "transfer_ids\|update_edge_ids\|transfer_holes\|snap_polygon\|assign(\|auto_dims\|default_unc" web/app/*.py` – jeder weitere Aufrufer bekommt `k` aus dem Format seines Fotos oder bleibt bewusst bei 1.0 (im Report begründen).

- [ ] **Step 4: Eckpunkt-Spielraum in `main.py`** – Test zuerst (an `tests/test_kleinteile.py` anhängen):

```python
# ------------------------------------------------------------------ API (§2, §4, §5)

PLATE_H = [{"rect": [20, 34, 20, 12], "gray": 90}, {"circle": [30, 40, 1.0], "gray": 245}]


def _k60_project(c, fmt="K60H", objects=None, view="top", fmt_form=""):
    pid = c.post("/api/projects", json={"name": "Klein"}, headers=H).json()["id"]
    r = c.post(f"/api/projects/{pid}/photos", headers=H, data={"view": view, "format": fmt_form},
               files={"file": ("k.jpg", synthetic_photo(fmt, objects=PLATE_H if objects is None else objects), "image/jpeg")})
    assert r.status_code == 200, r.text
    return pid, r.json()


def test_k60_api_eckpunkt_spielraum(user):
    pid, ph = _k60_project(user)
    ok = [[-2.0, 30], [10, 30], [10, 40]]
    bad = [[-3.0, 30], [10, 30], [10, 40]]
    r = user.post(f"/api/projects/{pid}/parts", json={"photo_id": ph["id"], "label": "A", "polygon": ok}, headers=H)
    assert r.status_code == 200, r.text
    r = user.post(f"/api/projects/{pid}/parts", json={"photo_id": ph["id"], "label": "B", "polygon": bad}, headers=H)
    assert r.status_code == 400 and "außerhalb der Messfläche" in r.text
```

(`PartIn` hat `photo_id`, `label`, `role`, `polygon`.) Dann in `main.py`:

```python
def _margin_mm(photo: dict) -> float:
    """Spielraum fuer Eckpunkte ausserhalb des Feldes: 10 mm · k (A4/A3 10 mm, Kleinteile 2,5 mm)."""
    return 10.0 * matgen.edge_scale(photo.get("format"))
```

`_polygon`: `mg = _margin_mm(photo)` und die Bedingung `not (-mg <= q[0] <= r["w_mm"] + mg and -mg <= q[1] <= r["h_mm"] + mg)`. `photo_edges`: vor `def inside` `mg = _margin_mm(ph)`, in `inside` `-mg <= q[0] <= rect["w_mm"] + mg and -mg <= q[1] <= rect["h_mm"] + mg`.

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py tests/test_parts.py tests/test_parts_api.py tests/test_edges_api.py tests/test_golden_a4a3.py`
Expected: PASS.

- [ ] **Step 6: Ruff und Commit**

```bash
ruff check web/app/parts.py web/app/main.py tests/test_kleinteile.py
git add web/app/parts.py web/app/main.py tests/test_kleinteile.py
git commit -m "Kleinteile: Teile-Zuordnung, Einrasten, Unsicherheit und Eckpunkt-Spielraum mit Massstab"
```

---

### Task 7: API, Kontrollmaß, KI-Bilder (`web/app/main.py`, `web/app/geom.py`, `web/app/jobs.py`, `web/app/ai.py`, `tools/check_photo.py`)

**Files:**
- Modify: `web/app/geom.py:42-49` (`factors`)
- Modify: `web/app/main.py` (`_photo_public`, `_ctrl_ref`/`_mixed_formats` neu, `_factors`, `project_patch`, `_project_public`, Messunterlagen-Endpunkte, `_analyze_store`, `photo_align_jpg`, Vorschlags-Bildbeschriftung)
- Modify: `web/app/jobs.py` (`_rect_top`, `pick_images`)
- Modify: `web/app/ai.py:30` (Text)
- Modify: `tools/check_photo.py`
- Modify: `tests/test_geom.py:32-35` (neue Signatur)
- Test: `tests/test_kleinteile.py` (Abschnitt „API“)

**Interfaces:**
- Consumes: Profile (Task 2), `vision.rect_pxmm`, `format_note` (Task 3), `detect(...)["edge_scale"]` (Task 4), `_k60_project` (Task 6).
- Produces:
  - `geom.factors(project, ctrl_ref, grid_h) -> (fx, fy)`.
  - Projekt-API: `ctrl_ref` (float), `mixed_formats` (bool), wie bisher `format`, `grid_h` (Detail), `factors`.
  - Foto-API: `quality_mm` (Liste), `n_markers` (int), `view_note` (str | None), `analysis.format_note`.
  - `/api/mat.pdf`, `/api/mat/preview.png`, `/api/mat/layout` für Druckformate `A4`, `A3`, `K60`; Layout `K60` → `{"K60H": …, "K60D": …}`.
  - `jobs._rect_top(ph, top) -> tuple[Path, float] | None` (Pfad, px/mm).

- [ ] **Step 1: Tests schreiben** (an `tests/test_kleinteile.py` anhängen; `tests/test_geom.py::test_factors` auf die neue Signatur umstellen: `geom.factors({"ctrl_x": 99.5}, 100.0, 230)` und `geom.factors({"ctrl_x": 100.2, "ctrl_y": 229.0}, 100.0, 230)`, Erwartungen unverändert; dazu `assert geom.factors({"ctrl_x": 49.8}, 50.0, 80) == (pytest.approx(0.996), pytest.approx(0.996))`)

```python
def test_k60_api_foto_und_projekt(user):
    pid, ph = _k60_project(user)
    assert ph["format"] == "K60H" and ph["status"] == "gut"
    assert ph["rect"]["pxmm"] == 30.0 and ph["rect"]["w_mm"] == 60 and ph["rect"]["h_mm"] == 80
    assert ph["quality_mm"] == [0.125, 0.25] and ph["n_markers"] == 8 and ph["view_note"] is None
    p = user.get(f"/api/projects/{pid}").json()
    assert p["format"] == "K60H" and p["ctrl_ref"] == 50.0 and p["grid_h"] == 80.0 and p["mixed_formats"] is False


def test_k60_api_kontrollmass(user):
    pid, _ = _k60_project(user)
    p = user.patch(f"/api/projects/{pid}", json={"ctrl_x": 49.8, "ctrl_y": 80.4}, headers=H).json()
    assert p["factors"][0] == pytest.approx(49.8 / 50) and p["factors"][1] == pytest.approx(80.4 / 80)
    r = user.patch(f"/api/projects/{pid}", json={"ctrl_x": 100.0}, headers=H)
    assert r.status_code == 400 and "erwartet um 50 mm" in r.text


def test_k60_api_gemischt(user, photo_a4):
    pid, _ = _k60_project(user)
    r = user.post(f"/api/projects/{pid}/photos", headers=H, data={"view": "top"},
                  files={"file": ("a4.jpg", photo_a4, "image/jpeg")})
    assert r.status_code == 200
    p = user.get(f"/api/projects/{pid}").json()
    assert p["mixed_formats"] is True and p["format"] == "K60H" and p["ctrl_ref"] == 50.0


def test_k60_api_variante_hinweis(user):
    _, ph = _k60_project(user, fmt="K60D", objects=[{"rect": [15, 30, 30, 20], "gray": 230}], fmt_form="K60H")
    assert ph["format"] == "K60D" and ph["analysis"]["format_note"] == "Format auf Kleinteile dunkel geändert"


def test_k60_api_hoehenlehre_hinweis(user):
    _, ph = _k60_project(user, view="gauge")
    assert ph["view_note"] == "Höhenlehre gibt es bei Kleinteilen nicht – Teil kippen und als ‚Gekippt (Höhe)‘ fotografieren"
    assert ph["gauge"] is None


def test_mat_k60_endpunkte(admin):
    import pypdfium2 as pdfium
    r = admin.get("/api/mat.pdf?format=K60&pages=gauge&header=Test")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(pdfium.PdfDocument(r.content)) == 3
    assert 'Messunterlage_K60.pdf' in r.headers["content-disposition"]
    assert admin.get("/api/mat/preview.png?format=K60&page=1").status_code == 200
    assert admin.get("/api/mat/preview.png?format=K60&page=3").status_code == 400
    assert admin.get("/api/mat/preview.png?format=A4&page=2").status_code == 200
    lay = admin.get("/api/mat/layout?format=K60").json()
    assert set(lay) == {"K60H", "K60D"} and lay["K60D"]["ids"] == list(range(30, 38))
    assert admin.get("/api/mat/layout?format=A4").json()["grid_mm"] == [190, 230]
    for bad in ("K60H", "A5"):
        r = admin.get(f"/api/mat.pdf?format={bad}")
        assert r.status_code == 400 and "Format muss A4, A3 oder K60 sein" in r.text


def test_k60_api_kanten_teile_und_ki_bilder(user):
    from app import jobs
    pid, ph = _k60_project(user)
    r = user.post(f"/api/photos/{ph['id']}/edges", json={"use_ai": False}, headers=H)
    assert r.status_code == 200, r.text
    e = user.get(f"/api/photos/{ph['id']}/edges.json").json()
    assert e["px_per_mm"] == 30.0 and e["edge_scale"] == 0.25 and len(e["holes"]) == 1
    p = user.get(f"/api/projects/{pid}").json()
    assert p["parts"] and any(m["kind"] == "diameter" for m in p["measurements"])
    r = user.post(f"/api/projects/{pid}/photos", headers=H, data={"view": "bottom"},
                  files={"file": ("u.jpg", synthetic_photo("K60H", objects=PLATE_H), "image/jpeg")})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    imgs = jobs.pick_images(pid, None)
    caps = {i["kind"]: i["caption"] for i in imgs}
    assert "Bildbreite = 60.0 mm" in caps["top"] and "Bildbreite = 60.0 mm" in caps["bottom"], caps
    al = user.get(f"/api/photos/{bid}/align.jpg")
    assert al.status_code == 200
    import cv2
    img = cv2.imdecode(np.frombuffer(al.content, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[1] == 960  # 60 mm · 16 px/mm (ALIGN_PXMM / k)
```

- [ ] **Step 2: Tests laufen lassen, sie scheitern**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py -k "api and not eckpunkt" tests/test_geom.py`
Expected: FAIL (`KeyError: 'quality_mm'`, `ctrl_ref`, 400 bei `format=K60` usw.).

- [ ] **Step 3: `geom.factors`**

```python
def factors(project: dict, ctrl_ref: float | None, grid_h: float | None) -> tuple[float, float]:
    """Korrekturfaktoren aus dem Kontrollmass: ctrl_ref = waagerechter Bezug des Profils (A4/A3 100, Kleinteile 50)."""
    ref = ctrl_ref or 100.0
    fx = (project.get("ctrl_x") or ref) / ref
    fy = 1.0
    if project.get("ctrl_y") and grid_h:
        fy = project["ctrl_y"] / grid_h
    elif project.get("ctrl_x"):
        fy = fx
    return fx, fy
```

- [ ] **Step 4: `main.py`**

Helfer nach `_project_format`:

```python
def _ctrl_ref(fmt: str | None) -> float:
    return float(matgen.PROFILES[fmt]["ctrl_mm"]) if fmt in matgen.FORMATS else 100.0


def _mixed_formats(pid: int) -> bool:
    """Fotos auf verschiedenen Unterlagen (Druckformate; Kleinteile hell und dunkel zaehlen als eine)."""
    rows = db.q("SELECT DISTINCT format FROM photos WHERE project_id=? AND format IS NOT NULL", (pid,))
    return len({matgen.print_format_of(r["format"]) for r in rows} - {None}) > 1


GAUGE_NOTE_K60 = "Höhenlehre gibt es bei Kleinteilen nicht – Teil kippen und als ‚Gekippt (Höhe)‘ fotografieren"
```

- `_factors`: `return geom.factors(project, _ctrl_ref(fmt), _grid_h(fmt))`.
- `project_patch`: `fmt = _project_format(pid)`; `ref = _ctrl_ref(fmt) if k == "ctrl_x" else (_grid_h(fmt) or 230.0)`.
- `_project_public`: nach `out["factors"] = _factors(p)`: `out["ctrl_ref"] = _ctrl_ref(fmt)`; `out["mixed_formats"] = _mixed_formats(p["id"])`.
- `_photo_public`: Analyse-Schlüssel um `"format_note"` ergänzen; zusätzliche Felder:
  ```python
  prof = matgen.PROFILES.get(ph["format"])
  ...
  "quality_mm": list(prof["quality_mm"]) if prof else [0.5, 1.0],
  "n_markers": len(prof["ids"]) if prof else 8,
  "view_note": GAUGE_NOTE_K60 if ph["view"] == "gauge" and prof and not prof["gauge"] else None,
  ```
- `_analyze_store`: `a["rect"] = {"pxmm": matgen.PROFILES[a["format"]]["pxmm"], …}` (statt `vision.PX_PER_MM`; `gauge_rect` bleibt bei `vision.PX_PER_MM`).
- Messunterlage:
  ```python
  def _pages(fmt: str, pages: str) -> list[str]:
      allowed = matgen.PRINT_PAGES[fmt]
      return [x for x in allowed if x in (pages or "").split(",")] or list(allowed)
  ```
  `mat_pdf`: `if format not in matgen.PRINT_FORMATS: raise HTTPException(400, "Format muss A4, A3 oder K60 sein")`; `_pdf_bytes(format, _pages(format, pages), header[:60])`. `mat_preview`: `if format not in matgen.PRINT_FORMATS or not 0 <= page < len(matgen.PRINT_PAGES[format])`; Rendern mit `list(matgen.PRINT_PAGES[format])`. `mat_layout`: gleiche Prüfung und Meldung; `return {f: vision.spec(f) for f in matgen.PRINT_FORMATS[format]} if format == "K60" else vision.spec(format)`.
- `photo_align_jpg`: `pxo = ALIGN_PXMM / matgen.edge_scale(top["format"])`; `vision.bottom_warp(img, a, at, pxo)` und `draw_outlines(…, pxo, at["rect"]["h_mm"])`.
- Vorschlags-Bildbeschriftung (Route mit `ai.SUGGEST_SYSTEM`): `vision.rect_pxmm(db.jload(ph["analysis"], {}))` statt `vision.PX_PER_MM` bei `rect.jpg` (die Höhenlehre bleibt bei `vision.PX_PER_MM`).

- [ ] **Step 5: `jobs.py`**

`_rect_top` gibt `(out, pxmm)` zurück: `pxmm = vision.rect_pxmm(at or a)`; `vision.bottom_warp(img, a, at, pxmm)`; `return out, pxmm` (bei fehlendem Bild weiter `None`). In `pick_images`: Draufsicht `ai.scaled_caption(…, vision.rect_pxmm(a))`; Unteransicht `got = _rect_top(p, top)` / `if got: path, pxmm = got` und `ai.scaled_caption(path, …, pxmm)`. Höhenlehre unverändert. `grep -n "_rect_top" web/app/*.py tests/*.py` – weitere Aufrufer anpassen.

- [ ] **Step 6: `ai.py` und `tools/check_photo.py`**

`ai.py:30`: „Ursprung der Draufsicht: linke untere Ecke des Rasters, x nach rechts, y nach oben.“ → „Ursprung der Draufsicht: linke untere Ecke des Rasters bzw. Messfelds, x nach rechts, y nach oben.“ (`grep -rn "linke untere Ecke des Rasters" tests` – Tests mit dem alten Wortlaut anpassen und im Report nennen.)

`tools/check_photo.py`: Docstring „[--size A4|A3|K60H|K60D]“ und „massstaebliche Draufsicht (px/mm aus dem Profil)“; `choices=["A4", "A3", "K60H", "K60D"]`; nach `print(f"Bewertung: …")` bei `r.get("format_note")` die Notiz ausgeben; Speicherzeile `pxmm = vision.spec(r["format"])["pxmm"]` und `print(f"Draufsicht gespeichert: {out} ({pxmm:g} px/mm, Ursprung unten links)")`.

- [ ] **Step 7: Tests laufen lassen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_kleinteile.py tests/test_geom.py tests/test_api.py tests/test_align.py tests/test_edges_api.py tests/test_golden_a4a3.py`
Expected: PASS.

- [ ] **Step 8: Ruff und Commit**

```bash
ruff check web/app/main.py web/app/geom.py web/app/jobs.py web/app/ai.py tools/check_photo.py tests/test_kleinteile.py tests/test_geom.py
git add web/app/main.py web/app/geom.py web/app/jobs.py web/app/ai.py tools/check_photo.py tests/test_kleinteile.py tests/test_geom.py
git commit -m "Kleinteile: API mit Druckformat K60, Kontrollmass aus dem Profil, Hinweise, KI-Bilder im Massstab des Fotos"
```

---

### Task 8: Oberfläche – Formate, Unterlagen-Seite, Fotos prüfen (`formats.js`, `mat.js`, `photos.js`)

**Files:**
- Create: `web/static/js/formats.js`
- Create: `tests/js/formats.test.mjs`
- Modify: `web/static/js/mat.js`
- Modify: `web/static/js/photos.js` (Formatauswahl Z. 41–42, Bildunterschriften Z. 219–224, Balken Z. 226–231, Kontrollmaß Z. 235–236, Hinweise Z. 248–251, Legende Z. 268, Kontrollmaß-Labels Z. 272–273)

**Interfaces:**
- Consumes: Projektfelder `ctrl_ref`, `mixed_formats`, `format`, `grid_h`; Fotofelder `quality_mm`, `n_markers`, `view_note`, `analysis.format_note`, `rect.pxmm` (Task 7); `/api/mat/layout?format=K60` (Task 7).
- Produces: `formats.js` mit `FORMAT_LABEL`, `PRINT`, `isSmall(fmt)`, `barClass(v, q)`, `barWidth(v, q)`, `qualityLegend(q)`, `unsureText(q)`, `lowContrastText(fmt)`, `ctrlLabels(ref, gridH, small)`, `mixedText(fmt)`, `layoutFacts(fmt, sp)` (alle ohne DOM).

- [ ] **Step 1: Tests schreiben** – `tests/js/formats.test.mjs`:

```js
// Formate der Messunterlage (web/static/js/formats.js) – Aufruf: node --test tests/js/*.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { FORMAT_LABEL, PRINT, isSmall, barClass, barWidth, qualityLegend, unsureText, lowContrastText, ctrlLabels, mixedText, layoutFacts }
  from "../../web/static/js/formats.js";

test("Anzeigenamen und Druckformate", () => {
  assert.equal(FORMAT_LABEL.K60H, "Kleinteile hell");
  assert.equal(FORMAT_LABEL.K60D, "Kleinteile dunkel");
  assert.deepEqual(Object.keys(PRINT), ["A4", "A3", "K60"]);
  assert.deepEqual(PRINT.K60.pages.map(p => p[0]), ["mat", "dark", "guide"]);
  assert.deepEqual(PRINT.A4.pages.map(p => p[0]), ["mat", "gauge", "guide"]);
  assert.equal(PRINT.K60.ctrl, 50);
  assert.ok(isSmall("K60D") && !isSmall("A4") && !isSmall(null));
});

test("Restfehler-Balken: A4 wie bisher, Kleinteile mit eigenen Schwellen", () => {
  const a4 = [0.5, 1.0], k = [0.125, 0.25];
  assert.equal(barWidth(0.3, a4), 30);          // bisher v * 100
  assert.equal(barWidth(2, a4), 100);
  assert.deepEqual([0.4, 0.6, 1.2].map(v => barClass(v, a4)), ["", "warn", "err"]);
  assert.equal(barWidth(0.125, k), 50);
  assert.deepEqual([0.1, 0.2, 0.3].map(v => barClass(v, k)), ["", "warn", "err"]);
  assert.equal(qualityLegend(a4), "Skala 0–1 mm · Linie bei 0,5 mm = Grenze „gut“ · über 1 mm Foto wiederholen");
  assert.equal(qualityLegend(k), "Skala 0–0,25 mm · Linie bei 0,125 mm = Grenze „gut“ · über 0,25 mm Foto wiederholen");
  assert.match(unsureText(k), /^Restfehler über 0,25 mm\./);
});

test("Kontrast, Kontrollmaß und gemischte Projekte", () => {
  assert.doesNotMatch(lowContrastText("A4"), /andere Variante/);
  assert.match(lowContrastText("K60D"), /andere Variante probieren: helles Teil auf das dunkle Blatt, dunkles Teil auf das helle Blatt/);
  assert.deepEqual(ctrlLabels(100, 230, false),
    { x: "0–100 gemessen", xPlaceholder: "100,0", xAria: "Kontrollmaß 0–100 gemessen", y: "Raster 0–230 vertikal", yAria: "Raster 0–230 vertikal gemessen" });
  assert.deepEqual(ctrlLabels(50, 80, true),
    { x: "0–50 gemessen", xPlaceholder: "50,0", xAria: "Kontrollmaß 0–50 gemessen", y: "Skala 0–80 senkrecht", yAria: "Skala 0–80 senkrecht gemessen" });
  assert.equal(mixedText("K60H"), "Fotos auf verschiedenen Unterlagen – das Kontrollmaß gilt für die Unterlage des ersten Fotos (Kleinteile hell).");
});

test("Kennzahlen der Unterlage", () => {
  const a4 = { grid_mm: [190, 230], marker_size_mm: 20, ids: [0, 1, 2, 3, 4, 5, 6, 7], height_gauge: { vlen_mm: 220 } };
  assert.deepEqual(layoutFacts("A4", a4), [["Raster", "190 × 230 mm"], ["Marker", "8 × 20 mm"], ["Wörterbuch", "4X4_50 · ID 0–7"], ["Höhenlehre", "0–220 mm"]]);
  const k = { K60H: { grid_mm: [60, 80], marker_size_mm: 8, ids: [20, 21, 22, 23, 24, 25, 26, 27] },
              K60D: { grid_mm: [60, 80], marker_size_mm: 8, ids: [30, 31, 32, 33, 34, 35, 36, 37] } };
  assert.deepEqual(layoutFacts("K60", k), [["Feld", "60 × 80 mm"], ["Marker", "8 × 8 mm"], ["Wörterbuch", "4X4_50 · ID 20–27 / 30–37"], ["Höhenlehre", "keine – Teil kippen"]]);
});
```

- [ ] **Step 2: Test laufen lassen, er scheitert**

Run: `node --test tests/js/formats.test.mjs`
Expected: FAIL (`Cannot find module …/formats.js`).

- [ ] **Step 3: `web/static/js/formats.js`**

```js
// Formate der Messunterlage: Druckformate (PDF) und Messformate (am Foto) – Daten und Texte ohne DOM (Spec Kleinteile §5)
export const FORMAT_LABEL = Object.freeze({ A4: "A4", A3: "A3", K60H: "Kleinteile hell", K60D: "Kleinteile dunkel" });

const PAGES_BIG = Object.freeze([["mat", "Messunterlage"], ["gauge", "Höhenlehre zum Aufstellen"], ["guide", "Anleitung"]]);
const PHOTO_BIG = "Senkrecht, 50–70 cm, 2×-Zoom";
export const PRINT = Object.freeze({
  A4: Object.freeze({ title: "A4", field: "Feld 190 × 230 mm", ctrl: 100, photo: PHOTO_BIG, pages: PAGES_BIG }),
  A3: Object.freeze({ title: "A3", field: "Feld 270 × 360 mm", ctrl: 100, photo: PHOTO_BIG, pages: PAGES_BIG }),
  K60: Object.freeze({ title: "Kleinteile", field: "Feld 60 × 80 mm, hell + dunkel", ctrl: 50,
    photo: "Senkrecht, 2×/3×-Zoom aus 25–30 cm, kein Makro",
    pages: Object.freeze([["mat", "Blatt hell"], ["dark", "Blatt dunkel"], ["guide", "Anleitung"]]) }),
});

const de = v => String(v).replace(".", ",");
const span = ids => `${Math.min(...ids)}–${Math.max(...ids)}`;

export function isSmall(fmt) { return fmt === "K60H" || fmt === "K60D"; }
export function barClass(v, q) { return v > q[1] ? "err" : v > q[0] ? "warn" : ""; }
export function barWidth(v, q) { return Math.min(100, (v / q[1]) * 100); }
export function qualityLegend(q) {
  return `Skala 0–${de(q[1])} mm · Linie bei ${de(q[0])} mm = Grenze „gut“ · über ${de(q[1])} mm Foto wiederholen`;
}
export function unsureText(q) {
  return `Restfehler über ${de(q[1])} mm. Unterlage liegt vermutlich nicht flach oder das Foto ist unscharf – besser wiederholen.`;
}
export function lowContrastText(fmt) {
  const base = "Geringer Kontrast zur Unterlage – Licht seitlich, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen.";
  return isSmall(fmt) ? `${base} Oder die andere Variante probieren: helles Teil auf das dunkle Blatt, dunkles Teil auf das helle Blatt.` : base;
}
export function ctrlLabels(ref, gridH, small) {
  const y = small ? `Skala 0–${de(gridH)} senkrecht` : `Raster 0–${de(gridH)} vertikal`;
  return { x: `0–${de(ref)} gemessen`, xPlaceholder: `${de(ref)},0`, xAria: `Kontrollmaß 0–${de(ref)} gemessen`, y, yAria: `${y} gemessen` };
}
export function mixedText(fmt) {
  return `Fotos auf verschiedenen Unterlagen – das Kontrollmaß gilt für die Unterlage des ersten Fotos (${FORMAT_LABEL[fmt] || fmt}).`;
}
export function layoutFacts(fmt, sp) {
  if (fmt === "K60") {
    const h = sp.K60H, d = sp.K60D;
    return [["Feld", `${h.grid_mm[0]} × ${h.grid_mm[1]} mm`], ["Marker", `8 × ${de(h.marker_size_mm)} mm`],
      ["Wörterbuch", `4X4_50 · ID ${span(h.ids)} / ${span(d.ids)}`], ["Höhenlehre", "keine – Teil kippen"]];
  }
  return [["Raster", `${sp.grid_mm[0]} × ${sp.grid_mm[1]} mm`], ["Marker", `8 × ${de(sp.marker_size_mm)} mm`],
    ["Wörterbuch", `4X4_50 · ID ${span(sp.ids)}`], ["Höhenlehre", `0–${de((sp.height_gauge || {}).vlen_mm)} mm`]];
}
```

(Die Zahlenformatierung `de` reicht hier, weil alle Werte ganz oder mit höchstens drei Nachkommastellen ohne Tausendertrennung sind; `num` aus `lib.js` wird nicht importiert, damit das Modul ohne DOM testbar bleibt.)

- [ ] **Step 4: `mat.js` umbauen**

- Import: `import { PRINT, layoutFacts } from "./formats.js";`; `PAGE_NAMES` und `CAPTIONS` entfallen.
- `fmt`: gelesen aus `localStorage` `mu.fmt`, nur übernehmen, wenn `fmt in PRINT`, sonst `"A4"`.
- Seitenwahl je Format: `let pages = {}; const pagesBox = h("div");` und
  ```js
  function drawPages() {
    pages = Object.fromEntries(PRINT[fmt].pages.map(([k]) => [k, true]));
    clear(pagesBox, PRINT[fmt].pages.map(([k, t]) =>
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: true, onchange: e => { pages[k] = e.target.checked; update(); } }), t)));
  }
  ```
  `fieldset „Seiten im PDF“` enthält `pagesBox`; beim Formatwechsel (`onchange` der Radio-Buttons) `drawPages()` vor `update()`.
- `choice(f)`: Beschriftung `PRINT[f].title`, Zusatz `PRINT[f].field`; die Formatauswahl zeigt `h("div", { class: "grid3" }, choice("A4"), choice("A3"), choice("K60"))` (`.grid3` gibt es in `app.css`).
- Druckhinweis: der Text „Danach das 100-mm-Kontrollmaß mit dem Lineal prüfen.“ steht in einem `span`, der in `update()` auf `` `Danach das ${PRINT[fmt].ctrl}-mm-Kontrollmaß mit dem Lineal prüfen.` `` gesetzt wird.
- „Nach dem Drucken“ Schritt 03: Untertitel-`span` mit Referenz, in `update()` `PRINT[fmt].photo`.
- `update()`: `const sel = PRINT[fmt].pages.map(([k]) => k).filter(k => pages[k]);` Vorschau-Schleife über `PRINT[fmt].pages.map(([k]) => k)` mit Index `i`; Bildunterschrift `figs[i]` bekommt den Namen `PRINT[fmt].pages[i][1]` (beim Formatwechsel neu setzen: `figcaption` per Referenz speichern); `alt` mit diesem Namen; `download`-Name `` `Messunterlage_${fmt}.pdf` ``.
- Kennzahlen: `clear(facts, layoutFacts(fmt, sp).map(([k, v]) => fact(k, v)));`

- [ ] **Step 5: `photos.js` umstellen**

- Import ergänzen: `import { FORMAT_LABEL, isSmall, barClass, barWidth, qualityLegend, unsureText, lowContrastText, ctrlLabels, mixedText } from "./formats.js";`
- Formatauswahl: Optionen „Automatisch erkennen“, A4, A3, `h("option", { value: "K60H" }, FORMAT_LABEL.K60H)`, `h("option", { value: "K60D" }, FORMAT_LABEL.K60D)`.
- Bildunterschrift Original: `` `${(a.mat_ids || []).length} von ${p.n_markers || 8} Markern` ``; entzerrt: `h("span", { class: "mono" }, `${num(p.rect?.pxmm ?? 10, 0)} px/mm`)`.
- Unterzeile Kopf: `p.format ? `${FORMAT_LABEL[p.format] || p.format}${a.format_auto ? " (automatisch)" : ""}` : null`.
- Balken: `const q = p.quality_mm || [0.5, 1];` `w = barWidth(v, q)`, `class: barClass(v, q)`; Legende `qualityLegend(q)`; Hinweis „unsicher“ `unsureText(q)`; Kontrasthinweis `lowContrastText(p.format)`.
- Neue Hinweise direkt nach dem Kontrasthinweis: `a.format_note ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, a.format_note)) : null` und `p.view_note ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, p.view_note)) : null`.
- Kontrollmaß: `const gridH = S.project.grid_h || 230, ref = S.project.ctrl_ref || 100;` `const L = ctrlLabels(ref, gridH, isSmall(S.project.format));` `cx` mit `placeholder: L.xPlaceholder, "aria-label": L.xAria`; `cy` mit `"aria-label": L.yAria`; Feldbeschriftungen `L.x` und `L.y`. Unter den Faktor-Chips bei `S.project.mixed_formats` zusätzlich `h("div", { class: "note warn" }, icon("warn"), h("span", {}, mixedText(S.project.format)))`.

- [ ] **Step 6: Tests und Prüfungen**

Run: `node --test tests/js/*.test.mjs && for f in web/static/js/*.js; do node --check "$f"; done && python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: PASS. Sichtprüfung folgt im Browser-Durchlauf (Task 10).

- [ ] **Step 7: Commit**

```bash
git add web/static/js/formats.js tests/js/formats.test.mjs web/static/js/mat.js web/static/js/photos.js
git commit -m "Kleinteile: Oberflaeche fuer Formatwahl, Blatt hell/dunkel, Schwellen und Hinweise je Format"
```

---

### Task 9: Anleitung, README, ausgelieferte PDFs (`help.js`, `guide.js`, `README.md`, `pdf/`, `docs/marker_layout.json`)

**Files:**
- Modify: `web/static/js/help.js:11-15` (`SECTIONS`)
- Modify: `tests/js/help.test.mjs:39-40`
- Modify: `web/static/js/guide.js` (neue Funktion `kleinteile`, `BUILD`, Texte in `ablauf`, `unterlage`, `fotos`, `probleme`)
- Modify: `README.md` (Tabelle Z. 20–25, Absatz Kleinteile)
- Create: `pdf/Messunterlage_K60.pdf`; Modify: `docs/marker_layout.json`

**Interfaces:**
- Consumes: alles aus Tasks 2–8.
- Produces: Anleitungsabschnitt `#kleinteile`; README-Hinweise.

- [ ] **Step 1: Test anpassen** – `tests/js/help.test.mjs:39-40`:

```js
  assert.deepEqual(SECTIONS.map(s => s[0]),
    ["ablauf", "unterlage", "fotografieren", "kleinteile", "fotos", "messen", "kanten", "cad", "bemassung", "teams", "tastatur", "probleme"]);
```

Run: `node --test tests/js/help.test.mjs` – Expected: FAIL.

- [ ] **Step 2: `help.js`** – in `SECTIONS` nach `["fotografieren", "Fotografieren"]` den Eintrag `["kleinteile", "Kleinteile"]`.

- [ ] **Step 3: `guide.js`**

Neue Funktion nach `fotografieren()` (Hilfsfunktionen `section`, `card`, `P`, `B`, `UL` wie in `fotografieren`):

```js
function kleinteile() {
  return section("kleinteile", card(
    P("Für Teile von wenigen Millimetern bis etwa 50 mm gibt es eine eigene Unterlage: Feld 60 × 80 mm ohne Raster, als Blatt hell und Blatt dunkel. Beim Erzeugen der Messunterlage „Kleinteile“ wählen."),
    UL([
      [B("Variante wählen:"), " dunkle oder bunte Teile auf das helle Blatt; helle, blanke, weiße oder durchsichtige Teile auf das dunkle Blatt."],
      [B("Drucken:"), " mit 100 %. Das dunkle Blatt möglichst mit Tintenstrahl auf mattem Papier – Laser-Toner glänzt auf großen dunklen Flächen. Das 50-mm-Kontrollmaß nachmessen und auf „Fotos prüfen“ eintragen, senkrecht die Skala 0–80."],
      [B("Auflegen:"), " Teil mittig ins Feld, alle 8 Marker frei lassen. Diffuses Licht, keine harten Schatten – es gibt kein Raster, das einen Schatten von einer Kante unterscheidet."],
      [B("Fotografieren:"), " senkrecht, 2×- oder 3×-Zoom aus 25–30 cm, der Rahmen füllt das Bild. Kein Makro-Modus: Fehler ≈ Maß × Höhe ÷ Abstand – ein 20 mm breites, 10 mm hohes Teil wirkt oben aus 25 cm 0,8 mm, aus 8 cm 2,5 mm zu breit."],
      [B("Höhe:"), " Teil kippen und erneut fotografieren (Ansicht „Gekippt (Höhe)“ oder als weitere Draufsicht). Eine Höhenlehre gibt es für Kleinteile nicht."],
      [B("Genauigkeit:"), " flache Teile (Höhe bis 2 mm) etwa ±0,2–0,3 mm, mit Messschieber-Nachmessung ±0,1–0,2 mm. Höhere Teile an der Auflagekante messen oder die Maße am Modell mit dem Messschieber korrigieren."],
    ])));
}
```

`BUILD` um `kleinteile` ergänzen (Reihenfolge wie `SECTIONS`).

Texte anpassen (Wortlaut):
- `unterlage` Z. 36: „Die Messunterlage ist ein PDF mit 1-mm-Raster und acht ArUco-Markern, dazu auf Wunsch die Höhenlehre zum Aufstellen und eine Kurzanleitung. Für Kleinteile gibt es eine eigene Unterlage ohne Raster (siehe „Kleinteile“). Ein Ausdruck reicht für beliebig viele Messungen.“
- `unterlage` Z. 39: „die 100-mm-Skala unten links“ → „die 100-mm-Skala unten links (bei Kleinteilen 50 mm)“.
- `fotos` Z. 70: „erkennt A4 oder A3 automatisch“ → „erkennt A4, A3 und die Kleinteile-Blätter automatisch“ (genauen Satz vorher lesen; nur diese Wortgruppe ersetzen).
- `fotos` Z. 71: nach „darüber „unsicher – …““ ergänzen: „ Bei Kleinteilen gelten 0,125 und 0,25 mm.“
- `fotos` Z. 74: „(230 mm bei A4, 360 mm bei A3)“ → „(230 mm bei A4, 360 mm bei A3, Skala 80 mm bei Kleinteilen; waagerecht 50 mm bei Kleinteilen)“.
- `probleme` Z. 184: „Der Restfehler liegt über 1 mm.“ → „Der Restfehler liegt über 1 mm (bei Kleinteilen über 0,25 mm).“

- [ ] **Step 4: README, PDF, Layout-JSON**

```bash
SP=/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad
mkdir -p $SP/kleinteile/pdf
python generator/make_mat.py $SP/kleinteile/pdf > docs/marker_layout.json
cp $SP/kleinteile/pdf/Messunterlage_K60.pdf pdf/
git diff --stat docs/marker_layout.json   # A4/A3: nur neue Schluessel (Profil), Mittelpunkte unveraendert; neu: K60
```

README: Tabellenzeile nach A3 `| [`pdf/Messunterlage_K60.pdf`](pdf/Messunterlage_K60.pdf) | Kleinteile: Feld 60 × 80 mm ohne Raster, Blatt hell und Blatt dunkel, Anleitung |`; Zeile `docs/marker_layout.json` → „… für alle Formate“; ein Absatz nach dem Teams-Absatz: „**Kleinteile:** Für Teile von wenigen Millimetern bis etwa 50 mm gibt es die Unterlage „Kleinteile“ (Feld 60 × 80 mm, Blatt hell und Blatt dunkel, Marker-IDs 20–27 bzw. 30–37). Snap2CAD erkennt das Blatt an den Markern, entzerrt mit 30 px/mm und skaliert die Kantenerkennung entsprechend; Kontrollmaß 50 mm. Fotografieren mit 2×/3×-Zoom aus 25–30 cm, kein Makro.“

- [ ] **Step 5: Tests und Prüfungen**

Run: `node --test tests/js/*.test.mjs && for f in web/static/js/*.js; do node --check "$f"; done && python -m pytest -q -p no:cacheprovider tests/test_texts.py tests/test_core.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/static/js/help.js web/static/js/guide.js tests/js/help.test.mjs README.md pdf/Messunterlage_K60.pdf docs/marker_layout.json
git commit -m "Kleinteile: Anleitung, README, PDF der Kleinteile-Unterlage und Markerlayout"
```

---

### Task 10: Volle Suite, Entwurfs-PR mit CI und Browser-Durchlauf

**Files:**
- Scratchpad: `$SP/pw/kleinteile.mjs`, `$SP/kleinteile/*.jpg`, `$SP/kleinteile/server.log`, `$SP/kleinteile/shots/`, Protokoll `$SP/kleinteile-protokoll.md` (alles nicht im Repo)

**Interfaces:**
- Consumes: alles aus Tasks 1–9; lokaler Server mit `AI_FAKE=1 SANDBOX_MODE=local` auf Port 8766.
- Produces: grüne lokale Suite, Entwurfs-PR mit grüner CI, `ergebnis.json` und Bildschirmfotos.

- [ ] **Step 1: Volle Suite**

```bash
df -h /tmp
export TMPDIR=/root/.cache/snap2cad-tmp && source /root/Snap2CAD-venv/bin/activate && cd /root/Snap2CAD
ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs && for f in web/static/js/*.js; do node --check "$f"; done
```
Expected: alles grün (Zahl der Tests im Protokoll festhalten: bisher 681 pytest / 55 node, jetzt mehr).

- [ ] **Step 2: Entwurfs-PR und CI**

```bash
git push -u origin kleinteile
gh pr create --draft --base main --title "Kleinteile-Unterlage (Feld 60 × 80 mm, Blatt hell/dunkel)" --body-file $SP/kleinteile/pr.md
H=$(git rev-parse HEAD) && until gh run list -b kleinteile -L5 --json databaseId,headSha -q ".[] | select(.headSha==\"$H\") | .databaseId" | grep -q .; do sleep 5; done && gh run watch --exit-status $(gh run list -b kleinteile -L5 --json databaseId,headSha -q ".[] | select(.headSha==\"$H\") | .databaseId" | head -1)
```
`$SP/kleinteile/pr.md`: Ziel, Nutzerentscheidungen (Spec §7), Änderungen je Bereich, Tests (Zahlen), Hinweis „A4/A3 durch Goldwerte gesichert“, Spec- und Plan-Pfad; **keine** Attribution. Rote CI allein durch Trivy ohne Bezug zum Branch: nicht im Branch umgehen, an Marc melden. Scheitert der Goldwert-Test nur in der CI (andere CPU, Abweichung in der letzten Stelle): Ruling – Vergleich auf Toleranz eine Einheit der Rundungsstelle umstellen, im Protokoll mit Beispielwert begründen.

- [ ] **Step 3: Server und Testfotos**

```bash
SP=/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad
rm -rf $SP/kleinteile/data $SP/kleinteile/runs $SP/kleinteile/shots && mkdir -p $SP/kleinteile
cd /root/Snap2CAD && source /root/Snap2CAD-venv/bin/activate && TMPDIR=/root/.cache/snap2cad-tmp python - "$SP/kleinteile" <<'EOF'
import sys
sys.path.insert(0, "tests")
from conftest import synthetic_photo
d = sys.argv[1]
open(f"{d}/k60h.jpg", "wb").write(synthetic_photo("K60H", objects=[{"rect": [20, 34, 20, 12], "gray": 90}, {"circle": [30, 40, 1.0], "gray": 245}]))
open(f"{d}/k60d.jpg", "wb").write(synthetic_photo("K60D", objects=[{"rect": [15, 30, 30, 20], "gray": 230}]))
open(f"{d}/a4.jpg", "wb").write(synthetic_photo("A4", 0))
EOF
```
Server im Hintergrund (`run_in_background`):
```bash
cd /root/Snap2CAD/web && source /root/Snap2CAD-venv/bin/activate && \
  DATA_DIR=$SP/kleinteile/data RUNS_DIR=$SP/kleinteile/runs SANDBOX_MODE=local AI_FAKE=1 \
  uvicorn app.main:app --port 8766 > $SP/kleinteile/server.log 2>&1
```

- [ ] **Step 4: Playwright-Skript** `$SP/pw/kleinteile.mjs` (nutzt `playwright-core` aus `$SP/pw/node_modules`):

```js
// Kleinteile – Browser-Durchlauf gegen lokalen Server (AI_FAKE=1, SANDBOX_MODE=local)
import { chromium } from "playwright-core";
import fs from "fs";
const [B, OUT, DIR] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const H = { "X-Requested-With": "fetch" };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 950 } });
const page = await ctx.newPage();
const C = {}, N = {}, errs = [], failed = [];
page.on("console", m => { if (m.type() === "error") errs.push(`[${new URL(page.url()).pathname}] ${m.text()}`); });
page.on("pageerror", e => errs.push(`pageerror: ${e.message}`));
page.on("response", r => { if (r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });
const api = async (method, path, data) => {
  const r = await ctx.request.fetch(B + path, { method, headers: H, data });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; }
  if (!r.ok()) throw new Error(`${method} ${path} ${r.status()} ${t.slice(0, 200)}`);
  return j;
};
const upload = (pid, file, view, format = "") => ctx.request.post(`${B}/api/projects/${pid}/photos`, { headers: H,
  multipart: { file: { name: file, mimeType: "image/jpeg", buffer: fs.readFileSync(`${DIR}/${file}`) }, view, format } });
const step = async (name, fn) => { try { await fn(); } catch (e) { N[`${name}_FEHLER`] = String(e.stack || e).slice(0, 600); } };
const waitJob = async jid => { let J; for (let i = 0; i < 150; i++) { J = await api("GET", `/api/jobs/${jid}`); if (!["queued", "running"].includes(J.status)) return J; await sleep(1000); } return J; };

await api("POST", "/api/setup", { username: "admin", display_name: "Admin", password: "Messschieber-Lang-12345", api_key: "" });
const uid = (await api("GET", "/api/me")).user.id;
let pid = null, phid = null;

await step("unterlage", async () => {
  await page.goto(`${B}/anleitung#unterlage`); await sleep(1500);
  await page.locator('input[name="fmt"][value="K60"]').check(); await sleep(2500);
  const caps = await page.locator(".previews figcaption").allTextContents();
  C.seiten_hell_dunkel = caps.some(t => t.includes("Blatt hell")) && caps.some(t => t.includes("Blatt dunkel"));
  C.pdf_link_k60 = (await page.locator("a.btn.primary.big").getAttribute("href")).includes("format=K60");
  C.kennzahlen = (await page.locator("dl.facts").textContent()).includes("ID 20–27 / 30–37");
  const r = await ctx.request.get(B + (await page.locator("a.btn.primary.big").getAttribute("href")));
  C.pdf_laedt = r.ok() && (await r.body()).subarray(0, 4).toString() === "%PDF";
  await page.screenshot({ path: `${OUT}/unterlage_k60.png`, fullPage: false });
});

await step("projekt_und_foto", async () => {
  pid = (await api("POST", "/api/projects", { name: "Kleinteil" })).id;
  const up = await upload(pid, "k60h.jpg", "top");
  const ph = await up.json(); phid = ph.id;
  C.foto_k60h = up.ok() && ph.format === "K60H" && ph.status === "gut" && ph.rect.pxmm === 30;
  await page.goto(`${B}/`); await sleep(500);
  await page.evaluate(([u, p]) => localStorage.setItem(`mu.project.${u}`, p), [uid, pid]);
  await page.goto(`${B}/fotos`); await sleep(2500);
  const body = await page.locator("main").textContent();
  C.fotos_30pxmm = body.includes("30 px/mm");
  C.fotos_kleinteile_hell = body.includes("Kleinteile hell");
  C.fotos_legende = body.includes("Skala 0–0,25 mm");
  C.fotos_kontrollmass = (await page.getByLabel("Kontrollmaß 0–50 gemessen").count()) === 1;
  await page.screenshot({ path: `${OUT}/fotos_k60.png` });
});

await step("kontrollmass", async () => {
  await page.getByLabel("Kontrollmaß 0–50 gemessen").fill("49,9");
  await page.getByLabel("Kontrollmaß 0–50 gemessen").press("Tab"); await sleep(1200);
  const p = await api("GET", `/api/projects/${pid}`);
  C.kontrollmass_50 = Math.abs(p.factors[0] - 49.9 / 50) < 1e-9;
});

await step("kanten_und_messen", async () => {
  await api("POST", `/api/photos/${phid}/edges`, { use_ai: false });
  await page.goto(`${B}/messen`); await sleep(3000);
  const p = await api("GET", `/api/projects/${pid}`);
  const d = p.measurements.find(m => m.kind === "diameter");
  C.bohrung_1mm = !!d && Math.abs(d.value - 1.0) <= 0.1;
  const L = p.measurements.filter(m => m.kind === "length").map(m => m.value).sort((a, b) => a - b);
  C.platte_20x12 = L.length >= 2 && Math.abs(L[0] - 12 * 49.9 / 50) <= 0.15 && Math.abs(L[L.length - 1] - 20 * 49.9 / 50) <= 0.15;
  await page.screenshot({ path: `${OUT}/messen_k60.png` });
});

await step("variante_und_gemischt", async () => {
  const up = await upload(pid, "k60d.jpg", "top", "K60H");
  const ph = await up.json();
  C.variante_umgeschaltet = ph.format === "K60D" && ph.analysis.format_note === "Format auf Kleinteile dunkel geändert";
  await upload(pid, "a4.jpg", "overview");
  const up2 = await upload(pid, "a4.jpg", "top");
  C.a4_foto = (await up2.json()).format === "A4";
  await page.goto(`${B}/fotos`); await sleep(2500);
  C.hinweis_gemischt = (await page.locator("main").textContent()).includes("Fotos auf verschiedenen Unterlagen");
  await page.screenshot({ path: `${OUT}/fotos_gemischt.png` });
});

await step("cad", async () => {
  await page.goto(`${B}/cad`); await sleep(1500);
  await page.locator("#zweck").fill("Kleine Platte mit Bohrung");
  await page.waitForFunction(() => !document.querySelector('button[form="cadform"]').disabled, null, { timeout: 20000 });
  await page.locator('button[form="cadform"]').click();
  await page.waitForURL(/\/cad\/\d+/, { timeout: 20000 });
  const J = await waitJob(Number(page.url().split("/").pop()));
  C.cad_fertig = J.status === "done";
  await page.screenshot({ path: `${OUT}/cad_k60.png` });
});

await step("anleitung", async () => {
  await page.goto(`${B}/anleitung#kleinteile`); await sleep(1500);
  const t = await page.locator("#kleinteile").textContent();
  C.anleitung_kleinteile = t.includes("2×- oder 3×-Zoom aus 25–30 cm") && t.includes("dunkle Blatt");
  await page.locator("#kleinteile").screenshot({ path: `${OUT}/anleitung_kleinteile.png` });
});

await browser.close();
const ok = Object.values(C).filter(Boolean).length;
fs.writeFileSync(`${OUT}/ergebnis.json`, JSON.stringify({ ok, total: Object.keys(C).length, C, N, errs, failed }, null, 1));
console.log(`${ok}/${Object.keys(C).length}`, JSON.stringify({ C, N, errs, failed }, null, 1));
```

Run: `cd $SP/pw && node kleinteile.mjs http://127.0.0.1:8766 $SP/kleinteile/shots $SP/kleinteile`
Expected: alle Prüfpunkte `true`, `N` leer, `errs` leer, `failed` leer. Die Bildschirmfotos ansehen (Read): Unterlagen-Vorschau mit Blatt hell/dunkel, Fotos mit 30 px/mm und Legende 0–0,25 mm, Messen mit Umriss und Bohrung, Anleitung. Selektoren, die nicht passen (Labels aus Task 8/9), am Code abgleichen und im Skript anpassen – nicht am Produkt, außer ein Befund zeigt einen echten Fehler (dann Fix mit Test, eigener Commit, Suite und CI erneut).

- [ ] **Step 5: Aufräumen und Protokoll**

Server stoppen; `$SP/kleinteile-protokoll.md` um Abschnitt „Task 10“ ergänzen (Suite-Zahlen, CI-Lauf-ID, `ok/total`, Liste der Bildschirmfotos).

---

### Task 11: Gesamtreview, Merge und Auslieferung (Controller)

**Files:** keine im Repo außer Befund-Korrekturen; Scratchpad `$SP/kleinteile/nas_update.sh`, `$SP/kleinteile/rueckweg.sh`, Protokoll.

**Interfaces:**
- Consumes: Branch `kleinteile` mit grüner CI (Task 10).
- Produces: main mit Kleinteile, NAS auf der neuen Revision, Rückweg.

- [ ] **Step 1: Gesamtreview** – ein Reviewer auf dem fähigsten Modell über `git diff main...kleinteile` (Server, Kerne, Tests) und die JS-Kette footgun (`--level minor`) über `formats.js`, `mat.js`, `photos.js`, `guide.js`, `help.js`. Befunde: eine Fix-Runde mit Tests, eine Nachprüfung, Rest als Ruling parken.

- [ ] **Step 2: Merge** – nur nach Marcs Freigabe (Merge-Ablauf PR → CI grün → Merge → CI main → NAS). PR auf „ready“ setzen (Body bei Bedarf per `gh api -X PATCH repos/CallMeTechie/Snap2CAD/pulls/<n> -f body=@…`, weil `gh pr edit` am GraphQL-Fehler scheitert), `gh pr merge --merge`, CI auf main abwarten (Image wird veröffentlicht).

- [ ] **Step 3: NAS** – `/root/Snap2CAD-teams-protokoll/nas_update.sh` und `rueckweg.sh` nach `$SP/kleinteile/` kopieren, darin `vor-teams` durch `vor-kleinteile` ersetzen; `ssh -i ~/.ssh/id_ed25519_nas ma.backes@192.168.2.151 'sh -s' < $SP/kleinteile/nas_update.sh | tee $SP/kleinteile/update.log`. Erwartet: neue Sicherung `backup-data-<datum>-<n>.tgz`, Images `:vor-kleinteile`, beide Container healthy, Revision = Merge-Commit, `https://snap2cad.collabtive.cloud/api/mat/layout?format=K60` ohne Login 401 (Route erreicht die App, kein WAF-Block). Keine Datenmigration; bestehende Fotos unverändert (Format A4/A3).

- [ ] **Step 4: Abschluss** – Memory `snap2cad-nas.md` und Index aktualisieren, Protokoll und Skripte nach `/root/Snap2CAD-kleinteile-protokoll/` sichern, Bericht an Marc mit der Bitte um den Echtfoto-Test (Spec §6: Kleinteil auf echtem Ausdruck, Messschieber-Vergleich).
