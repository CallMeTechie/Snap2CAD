"""Teile: Geometrie, Kanten-Kennungen, Massstab (Spec 2026-10-14-kanten-und-teile §2/§3, A2)."""
import pytest

from app import parts

R = [[0, 0], [63.6, 0], [63.6, 42.4], [0, 42.4]]
BOX = [[60, 80], [120, 80], [120, 120], [60, 120]]
PLATE = [[50, 105], [130, 105], [130, 125], [50, 125]]


def data(poly, hidden=(), holes=()):
    ids = list(range(1, len(poly) + 1))
    return {"polygon": poly, "edge_ids": ids, "next_edge_id": len(ids) + 1, "hidden": list(hidden),
            "holes": [{"id": i + 1, **h} for i, h in enumerate(holes)]}


def test_rechteck_auto_masse():
    dims = {d["key"]: d for d in parts.auto_dims(data(R))}
    assert set(dims) == {"L", "B"}
    assert dims["L"]["raw"] == pytest.approx(63.6) and dims["B"]["raw"] == pytest.approx(42.4)
    assert dims["L"]["points"] == [[0, 0], [63.6, 0]] and dims["B"]["points"] == [[0, 42.4], [0, 0]]
    assert dims["L"]["name"] == "Länge" and dims["B"]["name"] == "Breite"


def test_rechteck_ungleiche_und_verdeckte_kante():
    poly = [[0, 0], [60, 0], [61.5, 40], [0, 40]]
    dims = {d["key"]: d for d in parts.auto_dims(data(poly))}
    assert "ungleich" in dims["L"]["warn"]
    dims = {d["key"]: d for d in parts.auto_dims(data(poly, hidden=[3]))}  # Kante 3 = oben
    assert dims["L"]["raw"] == pytest.approx(60) and dims["L"]["warn"] is None


def test_polygon_kanten_und_bohrung():
    L = [[0, 0], [40, 0], [40, 10], [10, 10], [10, 30], [0, 30]]
    dims = parts.auto_dims(data(L, hidden=[2], holes=[{"c": [5, 5], "d": 3}]))
    assert [d["key"] for d in dims] == ["E1", "E2", "E3", "E4", "E5", "E6", "H1"]
    assert dims[1]["warn"] == "verdeckt, geschätzt" and dims[0]["raw"] == pytest.approx(40)
    assert dims[0]["name"] == "Kante 1"
    assert dims[6]["kind"] == "diameter" and dims[6]["raw"] == pytest.approx(3) and len(dims[6]["points"]) == 3


def test_kennungen_einfuegen_loeschen_verschieben():
    old = [[0, 0], [60, 0], [60, 40], [0, 40]]
    five = [[0, 0], [45, 0], [60, 0], [60, 40], [0, 40]]
    assert parts.update_edge_ids(old, [1, 2, 3, 4], five, 5) == ([1, 5, 2, 3, 4], 6)   # 45 mm behaelt die 1
    assert parts.update_edge_ids(five, [1, 5, 2, 3, 4], old, 6) == ([1, 2, 3, 4], 6)   # zur laengeren verschmolzen
    assert parts.update_edge_ids(old, [1, 2, 3, 4], [[0, 0], [61, 0], [60, 40], [0, 40]], 5) == ([1, 2, 3, 4], 5)
    six = [[0, 0], [30, 0], [30, 5], [60, 5], [60, 40], [0, 40]]                          # kein Einfuegen/Loeschen -> uebertragen
    ids, nxt = parts.update_edge_ids(old, [1, 2, 3, 4], six, 5)
    assert len(ids) == 6 and 3 in ids and 4 in ids and nxt > 5


def test_kennungen_uebertragen():
    old = [[0, 0], [60, 0], [60, 40], [0, 40]]
    new = [[0.5, 40.2], [0.3, 0.1], [60.2, 0.2], [60.1, 40.1]]
    assert parts.transfer_ids(old, [1, 2, 3, 4], new, 5) == ([4, 1, 2, 3], 5)
    holes, nxt = parts.transfer_holes([{"id": 1, "c": [5, 5], "d": 3}], [{"c": [5.5, 5.2], "d": 3.1}, {"c": [30, 30], "d": 4}], 2)
    assert [h["id"] for h in holes] == [1, 2] and nxt == 3


SEGS = [{"id": "K1", "a": [60.1, 80.0], "b": [120.0, 80.1], "kind": "outline"},
        {"id": "K2", "a": [120.0, 80.1], "b": [120.0, 104.8], "kind": "outline"},
        {"id": "K3", "a": [60.1, 104.8], "b": [60.1, 80.0], "kind": "outline"},
        {"id": "K4", "a": [49.9, 104.8], "b": [129.8, 104.8], "kind": "inner"}]


def test_einrasten_mit_verdeckter_kante():
    poly, hidden = parts.snap_polygon([[61, 81], [119, 81], [119, 119], [61, 119]], SEGS)
    assert hidden == [False, False, True, False]
    assert poly[0] == pytest.approx([60.1, 80.0], abs=0.05) and poly[1] == pytest.approx([120.0, 80.1], abs=0.05)
    assert poly[2] == pytest.approx([120.0, 119.0], abs=0.05)


def test_einrasten_bevorzugt_genannte_kandidaten():
    segs = [{"id": "K1", "a": [0, 0.5], "b": [50, 0.5], "kind": "outline"},
            {"id": "K2", "a": [0, 2.0], "b": [50, 2.0], "kind": "inner"}]
    ki = [[0, 1.0], [50, 1.0], [50, 30], [0, 30]]
    assert parts.snap_polygon(ki, segs)[0][0][1] == pytest.approx(0.5)
    assert parts.snap_polygon(ki, segs, preferred=["K2"])[0][0][1] == pytest.approx(2.0)


def test_zuordnung_bei_ueberlappung():
    ps = [(1, BOX), (2, PLATE)]
    assert parts.assign([[70, 105], [110, 105]], ps) == 2      # Plattenkante ueber dem Quader
    assert parts.assign([[60, 85], [120, 85]], ps) == 1        # Quaderbreite
    assert parts.assign([[80, 110], [100, 110]], ps) == 2      # innen in beiden -> kleinere Flaeche
    assert parts.assign([[10, 10], [20, 10]], ps) is None


def test_zuordnung_mit_selbstueberschneidung():
    bow = [[0, 0], [40, 40], [40, 0], [0, 40]]
    assert parts.assign([[5, 20], [8, 20]], [(1, bow)]) in (1, None)


def test_massstab():
    k, good, bad, warn = parts.scale_of([(1, 60 / 63.6)])
    assert k == pytest.approx(0.9434, abs=1e-4) and good == [1] and bad == [] and warn is None
    _, _, _, warn = parts.scale_of([(1, 0.943), (2, 0.943 * 1.015)])
    assert warn and "widersprechen" in warn
    k, good, bad, _ = parts.scale_of([(1, 1.40)])
    assert k == 1.0 and bad == [1] and good == []


def test_nennmass():
    assert parts.nominal(60.12, 0.3) == 60.0
    assert parts.nominal(60.27, 0.05) is None
    assert parts.nominal(59.7, 0.5, caliper=60.02) == 60.02


def test_abgleich_ueber_ueberlappung():
    old = [(10, BOX), (11, PLATE)]
    new = [(0, [[50.4, 105.2], [130.1, 105], [130, 125.3], [50, 125]]), (1, [[61, 81], [119, 81], [119, 119], [61, 119]]),
           (2, [[0, 0], [10, 0], [10, 10]])]
    assert parts.match_parts(old, new) == {0: 11, 1: 10}


def test_bohrung_zum_kleinsten_teil():
    lst = [{"polygon": BOX}, {"polygon": PLATE}]
    parts.assign_holes(lst, [{"c": [90, 115], "d": 5}, {"c": [300, 300], "d": 2}])
    assert lst[0]["holes"] == [] and lst[1]["holes"] == [{"c": [90, 115], "d": 5}]


def test_ccw_dreht_kennzeichen_mit():
    cw = [[0, 0], [0, 40], [60, 40], [60, 0]]
    poly, flags = parts._ccw(cw, [False, True, False, False])  # Kante 1 (oben) verdeckt
    assert poly == [[60, 0], [60, 40], [0, 40], [0, 0]]
    i = flags.index(True)
    assert {tuple(poly[i]), tuple(poly[(i + 1) % 4])} == {(0, 40), (60, 40)}
