"""Messunterlage Mini fuer kleine Teile (ca. 1–40 mm): Layout, Erkennung, Genauigkeit, Kanten, Web-App."""
import io
import math

import pytest

from conftest import H, synthetic_photo
from core import edges, matgen, vision


@pytest.fixture(scope="module")
def photo_mini() -> bytes:
    return synthetic_photo("Mini")


def _detect(objects, hints=None):
    img = vision.load_image(synthetic_photo("Mini", objects=objects))
    a = vision.analyze(img)
    assert a["format"] == "Mini", a["found_ids"]
    return edges.detect(vision.rectify_mat(img, a["homography"], "Mini"), "Mini", hints)


def _extent(outline):
    xs = [q[0] for q in outline["polygon"]]
    ys = [q[1] for q in outline["polygon"]]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


# ------------------------------------------------------------------ Layout und PDF

def test_layout_mini():
    sp = matgen.layout("Mini")
    assert sp["grid_mm"] == [80, 60] and sp["marker_size_mm"] == 7.0
    assert sp["ids"] == list(range(20, 28)) and sorted(int(k) for k in sp["centers_mm"]) == sp["ids"]
    assert sp["grid_unit_mm"] == 0.5 and sp["px_per_mm"] == 20.0 and sp["verdict_mm"] == [0.2, 0.4]
    # alle Marker samt Ruhezone liegen in der Rasterflaeche, das Mittelfeld fuer das Teil bleibt frei
    half = sp["marker_size_mm"] / 2 + 1.5
    for x, y in sp["centers_mm"].values():
        assert half <= x <= 80 - half and half <= y <= 60 - half
    hg = sp["height_gauge"]
    assert hg["strips"] == {"A": [30, 31, 34], "B": [32, 33, 35]} and hg["vlen_mm"] == 50
    assert hg["px_per_mm"] == 20.0 and hg["x_range_mm"] == [-40.0, 40.0]


@pytest.mark.parametrize("fmt", ["A4", "A3"])
def test_grosse_formate_unveraendert(fmt):
    """Bereits gedruckte Unterlagen muessen weiter passen: IDs, Aufloesung und Lehre wie bisher."""
    sp = matgen.layout(fmt)
    assert sp["ids"] == list(range(8)) and sp["px_per_mm"] == 10.0 and sp["grid_unit_mm"] == 1.0
    assert sp["verdict_mm"] == [0.5, 1.0]
    assert sp["height_gauge"]["strips"] == {"A": [10, 11, 14], "B": [12, 13, 15]}
    assert sp["height_gauge"]["marker_size_mm"] == 18.0


def test_mini_ids_kollidieren_nicht():
    """Mini-, Blatt- und Lehren-Marker teilen sich keine ID – sonst waere die Formaterkennung mehrdeutig."""
    mini = matgen.layout("Mini")
    a4 = matgen.layout("A4")
    groups = [set(mini["ids"]), set(a4["ids"])]
    for sp in (mini, a4):
        groups.append({i for ids in sp["height_gauge"]["strips"].values() for i in ids})
    allids = [i for g in groups for i in g]
    assert len(allids) == len(set(allids))


def test_pdf_mini_drei_seiten():
    import pypdfium2 as pdfium
    buf = io.BytesIO()
    spec = matgen.build(buf, "Mini", header="Werkstatt")
    pdf = pdfium.PdfDocument(buf.getvalue())
    assert len(pdf) == 3
    text = pdf[0].get_textpage().get_text_range()
    assert "Messunterlage Mini" in text and "Kontrollmaß 100 mm" in text
    pdf.close()
    assert spec["grid_mm"] == [80, 60]


# ------------------------------------------------------------------ Erkennung und Entzerrung

def test_mini_wird_erkannt_und_ist_genau(photo_mini):
    img = vision.load_image(photo_mini)
    a = vision.analyze(img)
    assert a["format"] == "Mini" and a["format_auto"]
    assert a["mat_ids"] == list(range(20, 28)) and a["missing_ids"] == []
    assert a["status"] == "gut" and a["max_err_mm"] < 0.1
    rect = vision.rectify_mat(img, a["homography"], "Mini")
    assert rect.shape[:2] == (1200, 1600)  # 20 px/mm


def test_falsches_format_erzwungen(photo_mini):
    a = vision.analyze(vision.load_image(photo_mini), "A4")
    assert a["status"] == "nicht_auswertbar" and a["homography"] is None
    assert a["mat_ids"] == [] and a["missing_ids"] == list(range(8))


def test_blatt_wird_nicht_als_mini_erkannt(photo_a4):
    a = vision.analyze(vision.load_image(photo_a4))
    assert a["format"] == "A4" and a["missing_ids"] == []


def test_ampel_mini_strenger():
    assert vision.verdict(8, 0.15, "Mini") == "gut"
    assert vision.verdict(8, 0.3, "Mini") == "brauchbar"
    assert vision.verdict(8, 0.45, "Mini") == "unsicher"
    assert vision.verdict(8, 0.45, "A4") == "gut"
    assert vision.verdict(8, 0.45) == "gut"


def test_entzerrung_ohne_halbpixel_versatz():
    """Markermitten liegen in der Draufsicht bei (OpenCV-Pixelkoordinate + 0,5) / px – wie Kanten und Messansicht."""
    import numpy as np
    for fmt in ("Mini", "A4"):
        img = vision.load_image(synthetic_photo(fmt, objects=[]))
        a = vision.analyze(img)
        rect = vision.rectify_mat(img, a["homography"], fmt)
        px, gh = vision.px_per_mm(fmt), vision.spec(fmt)["grid_mm"][1]
        found = vision.detect(rect)
        d = [((found[int(k)].mean(axis=0)[0] + 0.5) / px - x, gh - (found[int(k)].mean(axis=0)[1] + 0.5) / px - y)
             for k, (x, y) in vision.spec(fmt)["centers_mm"].items() if int(k) in found]
        assert len(d) >= 6
        assert np.abs(np.mean(d, axis=0)).max() < 0.2 / px, (fmt, np.mean(d, axis=0))


def test_mini_hoehenlehre():
    img = vision.load_image(synthetic_photo("Mini", page=1, tilt=0.03))
    a = vision.analyze(img)
    g = a["gauge"]
    assert g is not None and g["format"] == "Mini" and len(g["ids"]) == 3 and g["ids"][0] in (30, 32)
    assert g["rms_mm"] < 0.1 and g["vlen_mm"] == 50
    out, (x0, x1, y0, y1) = vision.rectify_gauge(img, g)
    assert (x0, x1, y0, y1) == (-40.0, 40.0, -5.0, 55.0)
    assert out.shape[:2] == (1200, 1600)


# ------------------------------------------------------------------ Kanten kleiner Teile

@pytest.mark.parametrize("w,h", [(16, 8), (4, 3), (3, 3), (2.5, 2.5), (2, 2)])
def test_kleine_rechtecke(w, h):
    res = _detect([{"rect": [38.3, 27.4, w, h], "gray": 40}])
    assert len(res["outlines"]) == 1
    x, y, ew, eh = _extent(res["outlines"][0])
    # Toleranz 0,12 mm: davon ~0,04 mm aus dem Testbild (cv2.rectangle zeichnet die Eckpixel mit)
    assert abs(ew - w) <= 0.12 and abs(eh - h) <= 0.12, (ew, eh)
    assert abs(x - 38.3) <= 0.1 and abs(y - 27.4) <= 0.1, (x, y)
    assert res["px_per_mm"] == 20.0


def test_kante_auf_rasterlinie():
    """Liegt eine Teilkante genau auf einer 10-mm-Linie, darf die Linie die Kante nicht nach aussen ziehen."""
    res = _detect([{"rect": [30, 24, 20, 12], "gray": 60}])
    _, _, ew, eh = _extent(res["outlines"][0])
    assert abs(ew - 20) <= 0.1 and abs(eh - 12) <= 0.1, (ew, eh)


def test_duenner_draht_bleibt_ganz():
    res = _detect([{"rect": [30, 26, 20, 1.0], "gray": 40}])
    assert len(res["outlines"]) == 1
    _, _, ew, eh = _extent(res["outlines"][0])
    assert abs(ew - 20) <= 0.2 and abs(eh - 1) <= 0.1, (ew, eh)   # Ecken auf die verfeinerte Laengsseite gelegt


@pytest.mark.parametrize("d", [3.0, 1.5, 1.0])
def test_bohrungen_bis_1mm(d):
    res = _detect([{"rect": [30, 24, 20, 12], "gray": 60}, {"circle": [40, 30, d], "gray": 238}])
    assert len(res["holes"]) == 1
    hole = res["holes"][0]
    assert abs(hole["d"] - d) <= 0.05 and math.hypot(hole["c"][0] - 40, hole["c"][1] - 30) <= 0.1, hole


def test_scheibe_mit_loch():
    res = _detect([{"circle": [40, 30, 8], "gray": 60}, {"circle": [40, 30, 3], "gray": 238}])
    assert len(res["outlines"]) == 1 and len(res["holes"]) == 1
    assert abs(res["holes"][0]["d"] - 3) <= 0.05
    _, _, ew, eh = _extent(res["outlines"][0])
    assert abs(ew - 8) <= 0.1 and abs(eh - 8) <= 0.1, (ew, eh)   # Kreis-Fit statt Vieleck
    assert len(res["outlines"][0]["polygon"]) == edges.CIRCLE_VERTS


def test_helles_teil_mit_hinweis():
    res = _detect([{"rect": [30, 24, 20, 12], "gray": 205}], {"light": True})
    assert len(res["outlines"]) == 1
    _, _, ew, eh = _extent(res["outlines"][0])
    assert abs(ew - 20) <= 0.35 and abs(eh - 12) <= 0.35


def test_leere_karte_ohne_umriss():
    res = _detect([])
    assert res["outlines"] == [] and res["holes"] == []


# ------------------------------------------------------------------ Web-App

def test_api_mini(user):
    assert user.get("/api/mat.pdf?format=Mini&pages=mat").content[:4] == b"%PDF"
    sp = user.get("/api/mat/layout?format=Mini").json()
    assert sp["ids"][0] == 20 and sp["px_per_mm"] == 20.0
    assert user.get("/api/mat/preview.png?format=Mini&page=0").status_code == 200

    pid = user.post("/api/projects", json={"name": "Kleinteil"}, headers=H).json()["id"]
    r = user.post(f"/api/projects/{pid}/photos",
                  files={"file": ("mini.jpg", synthetic_photo("Mini", objects=[{"rect": [34, 26, 12, 8], "gray": 40}]),
                                  "image/jpeg")}, data={"view": "top"}, headers=H)
    assert r.status_code == 200, r.text
    ph = r.json()
    assert ph["format"] == "Mini" and ph["status"] == "gut"
    assert ph["rect"]["pxmm"] == 20.0 and ph["rect"]["w_mm"] == 80 and ph["rect"]["w"] == 1600
    assert ph["analysis"]["missing_ids"] == []
    p = user.get(f"/api/projects/{pid}").json()
    assert p["grid_h"] == 60.0
    # Kontrollmass: 100-mm-Skala auf demselben Ausdruck, senkrecht das 60-mm-Raster der Karte
    assert user.patch(f"/api/projects/{pid}", json={"ctrl_x": 99.6, "ctrl_y": 59.8}, headers=H).status_code == 200
    assert user.patch(f"/api/projects/{pid}", json={"ctrl_y": 230.0}, headers=H).status_code == 400
