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
    c.patch(f"/api/photos/{b['id']}", json={"bottom_align": {"rot": 0}}, headers=H)          # falsche Lage: IoU ~0,15
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
