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
