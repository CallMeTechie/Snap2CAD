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
    # R2: Familie mit den meisten Markern
    assert a["mat_ids"] == [20, 21, 22] and a["missing_ids"] == [23, 24, 25, 26, 27]


def test_rect_pxmm_und_verdict():
    assert vision.rect_pxmm({"rect": {"pxmm": 30.0}}) == 30.0
    assert vision.rect_pxmm({"rect": {"w_mm": 60}}) == 10.0
    assert vision.rect_pxmm(None) == 10.0 and vision.rect_pxmm({}) == 10.0
    q = (0.125, 0.25)
    assert [vision.verdict(8, e, q) for e in (0.12, 0.2, 0.3)] == ["gut", "brauchbar", "unsicher"]
    assert [vision.verdict(8, e) for e in (0.5, 1.0, 1.01)] == ["gut", "brauchbar", "unsicher"]
    assert vision.verdict(3, 0.01, q) == "nicht_auswertbar"


def test_bottom_warp_k60_massstab_und_rand():
    a = {"format": "K60D", "rect": {"pxmm": 30.0, "w_mm": 60, "h_mm": 80, "w": 1800, "h": 2400}}
    out = vision.bottom_warp(np.zeros((10, 10, 3), np.uint8), a, a)
    assert out.shape == (2400, 1800, 3)
    # ausserhalb des kleinen Bildes: Feldfarbe dunkel
    assert tuple(int(v) for v in out[1200, 900]) == (34, 34, 34)
    M = vision.bottom_warp_matrix(a, a)
    assert M[2, 2] == pytest.approx(1.0) and abs(M[0, 0]) == pytest.approx(1.0)  # gleiche pxmm: keine Skalierung


# ------------------------------------------------------------------ Kantenmassstab (§3)


def test_scale_for_profile():
    from core import edges
    a4, k = edges.scale_for("A4"), edges.scale_for("K60D")
    assert (a4.pxmm, a4.work, a4.k, a4.field, a4.hole_max, a4.frame) == (10.0, 4.0, 1.0, "grid", 2000.0, False)
    assert (k.pxmm, k.work, k.k, k.field, k.frame) == (30.0, 16.0, 0.25, "plain_dark", True)
    assert k.hole_max == pytest.approx(1256.6, abs=0.1)


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


@pytest.mark.parametrize("fmt,gray", [("K60H", 60), ("K60D", 220)])
def test_k60_kanten_quadrat_3mm(fmt, gray):
    from core import edges
    res = edges.detect(_k60_rect(fmt, [{"rect": [28.5, 38.5, 3, 3], "gray": gray}]), fmt)
    _rect_ok(res, 3, 3)
    assert res["px_per_mm"] == 30.0 and res["edge_scale"] == 0.25


@pytest.mark.parametrize("fmt,plate,hole", [("K60H", 90, 245), ("K60D", 220, 34)])
def test_k60_kanten_platte_mit_bohrung_1mm(fmt, plate, hole):
    from core import edges
    objects = [{"rect": [20, 34, 20, 12], "gray": plate}, {"circle": [30, 40, 1.0], "gray": hole}]
    res = edges.detect(_k60_rect(fmt, objects), fmt)
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
    # ragt 10 mm ueber den Rand; y 20–30 haelt Abstand zu Marker 25 (Mitte 73/40, 8 mm), den es sonst verdeckt
    res = edges.detect(_k60_rect("K60H", [{"rect": [50, 20, 20, 10], "gray": 60}]), "K60H")
    assert len(res["outlines"]) == 1, res["outlines"]
    xs, ys = zip(*res["outlines"][0]["polygon"], strict=True)
    assert abs(min(xs) - 50) <= 0.1 and 59.5 <= max(xs) <= 60.5, xs
    assert abs(min(ys) - 20) <= 0.1 and abs(max(ys) - 30) <= 0.1, ys


def test_k60_teil_dicht_am_rand():
    from core import edges
    _rect_ok(edges.detect(_k60_rect("K60D", [{"rect": [1, 30, 20, 10], "gray": 230}]), "K60D"), 20, 10)


def test_k60_falsche_variante_wenig_kontrast():
    from core import edges
    res = edges.detect(_k60_rect("K60D", [{"rect": [15, 30, 30, 20], "gray": 45}]), "K60D")
    assert res["outlines"] == [] and res["contrast"] is None, (res["outlines"], res["contrast"])  # dL ≈ 12 < 18


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
    assert parts.transfer_ids(SQ, [1, 2, 3, 4], moved, 5, edge_k=0.25)[0] == [5, 6, 7, 8]
    assert parts.transfer_ids(SQ, [1, 2, 3, 4], [[x + 0.2, y] for x, y in SQ], 5, edge_k=0.25)[0] == [1, 2, 3, 4]
    old = [{"id": 1, "c": [30, 40], "d": 1.0}]
    assert parts.transfer_holes(old, [{"c": [31.0, 40], "d": 1.0}], 2)[0][0]["id"] == 1
    assert parts.transfer_holes(old, [{"c": [31.0, 40], "d": 1.0}], 2, edge_k=0.25)[0][0]["id"] == 2
    seg = [{"id": "K1", "a": [28.5, 37.5], "b": [31.5, 37.5]}]                # 1 mm unter der Unterkante
    assert parts.snap_polygon(SQ, seg)[0][0] == [28.5, 37.5]
    assert parts.snap_polygon(SQ, seg, edge_k=0.25)[0][0] == [28.5, 38.5]
    assert parts.assign([[32.0, 40.0]], [(7, SQ)]) == 7                       # 0,5 mm ausserhalb
    assert parts.assign([[32.0, 40.0]], [(7, SQ)], edge_k=0.25) is None
    uneven = {"polygon": [[0, 0], [10, 0], [10, 5], [0, 5.5]], "edge_ids": [1, 2, 3, 4], "hidden": [], "holes": []}
    assert parts.is_rect(uneven["polygon"])                                  # Winkel weichen 2,9° ab (< 4°)
    warn = "gegenüberliegende Kanten ungleich – Kante prüfen"                # links 5,5 mm, rechts 5 mm
    assert warn not in [d["warn"] for d in parts.auto_dims(uneven)]          # 0,5 mm < 1 mm
    assert warn in [d["warn"] for d in parts.auto_dims(uneven, edge_k=0.25)]      # 0,5 mm > 0,25 mm


def test_k60_teile_default_unc():
    from app import parts
    assert parts.default_unc({"format": "K60H", "max_err": 0.05, "analysis": "{}"}, "top") == 0.1
    assert parts.default_unc({"format": "K60H", "max_err": None, "analysis": "{}"}, "top") == 0.12
    assert parts.default_unc({"format": "A4", "max_err": 0.3, "analysis": "{}"}, "top") == 0.5
    assert parts.default_unc(None, "top") == 0.5


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
