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


from conftest import H as HDR   # H ist oben die Blatthoehe


def _up(c, pid, objects, view):
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("f.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": view}, headers=HDR)
    assert r.status_code == 200, r.text
    return r.json()


TOP = [{"polygon": L_SHAPE, "gray": 150}, HOLE]


@pytest.fixture()
def pair(user):
    pid = user.post("/api/projects", json={"name": "Lage"}, headers=HDR).json()["id"]
    t = _up(user, pid, TOP, "top")
    b = _up(user, pid, bottom_of(TOP, 90, -30, 22), "bottom")
    return user, pid, t, b


def test_unteransicht_wird_ausgerichtet(pair):
    c, pid, t, b = pair
    assert b["view"] == "bottom" and b["bottom_align"]["rot"] == 90 and not b["bottom_align"]["unsure"]
    assert b["bottom_align"]["auto"] is True and b["bottom_align"]["top_photo_id"] == t["id"]
    assert b["contrast"] is not None and b["bottom_rot_user"] is None


def test_draufsicht_spaeter(user):
    pid = user.post("/api/projects", json={"name": "Spaet"}, headers=HDR).json()["id"]
    b = _up(user, pid, bottom_of(TOP, 180), "bottom")
    assert b["bottom_align"] is None and b["align_note"] == "Draufsicht fehlt"
    _up(user, pid, TOP, "top")
    b1 = next(p for p in user.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == b["id"])
    assert b1["bottom_align"]["rot"] == 180


def test_messung_von_unten_und_to_top(pair):
    from app import db, parts
    c, pid, t, b = pair
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": b["id"], "kind": "length", "view": "bottom",
                                                          "points": [[10, 20], [30, 20]]}, headers=HDR).json()
    assert m["data"]["view"] == "bottom" and m["value"] == pytest.approx(20.0)
    ph = db.q1("SELECT * FROM photos WHERE id=?", (b["id"],))
    hole_b = bottom_of(TOP, 90, -30, 22)[1]["circle"][:2]
    assert parts.to_top(ph, [hole_b])[0] == pytest.approx(HOLE["circle"][:2], abs=0.5)


def test_suggest_nur_draufsicht(pair, monkeypatch):
    from app import ai
    c, pid, t, b = pair
    got, orig = [], ai.call
    monkeypatch.setattr(ai, "call", lambda s, m, **k: (got.append(m), orig(s, m, **k))[1])
    c.post(f"/api/projects/{pid}/suggest", json={"photo_id": b["id"]}, headers=HDR)
    caps = " ".join(x.get("text", "") for x in got[-1][0]["content"] if x["type"] == "text")
    assert f"Foto {t['id']})" in caps and f"Foto {b['id']})" not in caps


def _photo(c, pid, phid):
    return next(p for p in c.get(f"/api/projects/{pid}").json()["photos"] if p["id"] == phid)


def test_handwahl_und_referenzwechsel(pair):
    from app import db
    c, pid, t, b = pair
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=HDR).json()
    assert r["bottom_align"]["rot"] == 270 and r["bottom_align"]["auto"] is False and r["bottom_rot_user"] == 270
    assert c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 45}}, headers=HDR).status_code == 422
    t2 = _up(c, pid, TOP, "top")                                          # zweite Draufsicht, Referenz bleibt t
    assert c.delete(f"/api/photos/{t['id']}", headers=HDR).status_code == 200
    b2 = _photo(c, pid, b["id"])
    assert b2["bottom_align"]["top_photo_id"] == t2["id"] and b2["bottom_align"]["rot"] == 270   # Handwahl bleibt
    assert c.delete(f"/api/photos/{t2['id']}", headers=HDR).status_code == 200
    b3 = _photo(c, pid, b["id"])
    assert b3["bottom_align"] is None and "Draufsicht fehlt" in b3["align_note"] and b3["bottom_rot_user"] == 270
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": None}, headers=HDR).json()   # zurueck auf automatisch
    assert r["bottom_rot_user"] is None
    assert "bottom_rot_user" not in db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (b["id"],))["analysis"])


def test_umschalten_der_ansicht(user):
    pid = user.post("/api/projects", json={"name": "Umschalten"}, headers=HDR).json()["id"]
    t = _up(user, pid, TOP, "top")
    x = _up(user, pid, bottom_of(TOP, 180), "tilted")
    assert x["bottom_align"] is None
    r = user.patch(f"/api/photos/{x['id']}", json={"view": "bottom"}, headers=HDR).json()
    assert r["bottom_align"]["rot"] == 180
    m = user.post(f"/api/projects/{pid}/measurements", json={"photo_id": x["id"], "kind": "length", "view": "bottom",
                                                             "points": [[10, 20], [30, 20]]}, headers=HDR).json()
    assert m["data"]["view"] == "bottom"
    r = user.patch(f"/api/photos/{x['id']}", json={"view": "tilted", "bottom_align": {"rot": 90}}, headers=HDR)
    assert r.status_code == 400
    r = user.patch(f"/api/photos/{x['id']}", json={"view": "tilted"}, headers=HDR).json()
    assert r["bottom_align"] is None and r["align_note"] is None
    user.patch(f"/api/photos/{x['id']}", json={"view": "top"}, headers=HDR)                   # Messungen folgen top <-> bottom
    mm = next(q for q in user.get(f"/api/projects/{pid}").json()["measurements"] if q["id"] == m["id"])
    assert mm["data"]["view"] == "top"
    user.patch(f"/api/photos/{x['id']}", json={"view": "bottom"}, headers=HDR)
    user.patch(f"/api/photos/{t['id']}", json={"view": "tilted"}, headers=HDR)                # Referenz weg
    b = _photo(user, pid, x["id"])
    assert b["bottom_align"] is None and b["align_note"] == "Draufsicht fehlt"


def test_handwahl_nach_formatwechsel(pair):
    c, pid, t, b = pair
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=HDR)
    c.patch(f"/api/photos/{b['id']}", json={"format": "A3"}, headers=HDR)
    r = c.patch(f"/api/photos/{b['id']}", json={"format": "A4"}, headers=HDR).json()
    assert r["bottom_align"]["rot"] == 270 and r["bottom_align"]["auto"] is False


def test_erneut_anstossen(pair):
    c, pid, t, b = pair
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 270}}, headers=HDR)
    r = c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {}}, headers=HDR).json()     # neu rechnen, Handwahl bleibt
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
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=HDR).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremdl{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=HDR).status_code == 200
    assert f.get(f"/api/photos/{b['id']}/align.jpg").status_code == 404
    assert f.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 90}}, headers=HDR).status_code == 404
