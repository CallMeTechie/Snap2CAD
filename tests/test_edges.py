"""Kantenerkennung auf synthetischen Draufsichten (Spec 2026-10-14-kanten-und-teile §1, A1)."""
import json
import math

import pytest

from conftest import synthetic_photo
from core import edges, vision

BOX = {"rect": [60, 80, 60, 40], "gray": 150}
PLATE = {"rect": [50, 105, 80, 20], "gray": 90}
HOLE = {"circle": [90, 115, 5], "gray": 235}


def _rect(objects, fmt="A4"):
    img = vision.load_image(synthetic_photo(fmt, objects=objects))
    a = vision.analyze(img, fmt)
    return vision.rectify_mat(img, a["homography"], a["format"])


def _close(poly, expected, tol):
    for ex in expected:
        d = min(math.hypot(p[0] - ex[0], p[1] - ex[1]) for p in poly)
        assert d <= tol, (ex, poly)


@pytest.fixture(scope="module")
def box():
    return edges.detect(_rect([BOX]), "A4")


@pytest.fixture(scope="module")
def two():
    return edges.detect(_rect([BOX, PLATE, HOLE]), "A4")


def test_quader_umriss(box):
    assert len(box["outlines"]) == 1
    poly = box["outlines"][0]["polygon"]
    assert len(poly) == 4
    _close(poly, [(60, 80), (120, 80), (120, 120), (60, 120)], 0.5)
    assert box["holes"] == [] and box["px_per_mm"] == 10.0


def test_platte_bohrung_innenkante(two):
    assert len(two["outlines"]) == 1
    poly = two["outlines"][0]["polygon"]
    _close(poly, [(50, 105), (50, 125), (130, 125), (130, 105), (60, 105), (60, 80), (120, 80), (120, 105)], 0.5)
    assert len(two["holes"]) == 1
    h = two["holes"][0]
    assert math.hypot(h["c"][0] - 90, h["c"][1] - 115) <= 0.3 and abs(h["d"] - 5) <= 0.3
    inner = [s for s in two["segments"] if s["kind"] == "inner"]
    assert any(abs(s["a"][1] - 105) < 1 and abs(s["b"][1] - 105) < 1 and abs(s["a"][0] - s["b"][0]) > 40 for s in inner), inner


def test_kandidaten_nummeriert_und_json(two):
    ids = [s["id"] for s in two["segments"]]
    assert ids == [f"K{i}" for i in range(1, len(ids) + 1)]
    assert sum(s["kind"] == "outline" for s in two["segments"]) == len(two["outlines"][0]["polygon"])
    json.dumps(two)


def test_leere_unterlage():
    res = edges.detect(_rect([]), "A4")
    assert res["outlines"] == [] and res["segments"] == [] and res["holes"] == []


def test_viele_objekte_begrenzt():
    objs = [{"rect": [30 + 20 * i, 30 + 22 * j, 15, 15], "gray": 120} for i in range(6) for j in range(7)]
    res = edges.detect(_rect(objs), "A4")
    assert 1 <= len(res["outlines"]) <= edges.MAX_OUTLINES
    assert all(len(o["polygon"]) <= edges.MAX_VERTS for o in res["outlines"])


def test_kandidatenbild(two):
    img = _rect([BOX, PLATE, HOLE])
    out = edges.draw_candidates(img, two)
    assert out.shape == img.shape and (out != img).any()


def test_objekt_am_rand():
    res = edges.detect(_rect([{"rect": [0, 60, 50, 30], "gray": 120}]), "A4")
    assert len(res["outlines"]) == 1
    poly = res["outlines"][0]["polygon"]
    assert all(-0.5 <= x <= 190.5 and -0.5 <= y <= 230.5 for x, y in poly)
    _close(poly, [(50, 60), (50, 90)], 0.5)


def test_heller_koerper_ohne_raster():
    """Helles Blech (fast Papierfarbe): nur das fehlende mm-Raster verraet das Objekt (echte Fotos, Kuehlkoerper + Platte)."""
    res = edges.detect(_rect([{"rect": [60, 80, 60, 40], "gray": 246}]), "A4")
    assert len(res["outlines"]) == 1
    _close(res["outlines"][0]["polygon"], [(60, 80), (120, 80), (120, 120), (60, 120)], 1.0)


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
