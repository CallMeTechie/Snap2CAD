"""Bemaßung am Modell (Spec 2026-10-15 Stufe B, B1–B4)."""
import json
import math
import time

import pytest

from conftest import H


def _proj(c):
    return c.post("/api/projects", json={"name": "Stufe B"}, headers=H).json()["id"]


def _meas(c, pid, label, value, critical=False):
    r = c.post(f"/api/projects/{pid}/measurements", json={"kind": "length", "value": value, "label": label,
                                                         "critical": critical}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _user_row(c):
    from app import db
    return db.q1("SELECT * FROM users WHERE username=?", (c.username,))


def _job(c, pid, code, meta, result=None):
    """Auftrag mit einer fertigen Version 1 direkt in der Datenbank (ohne KI und Sandbox)."""
    from app import db
    jid = db.ex("INSERT INTO jobs(user_id,project_id,name,request,status,messages,current_version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (_user_row(c)["id"], pid, "Block", "{}", "done", "[]", 1, db.now(), db.now()))
    _version(jid, 1, "create", "ok", meta, code=code, result=result)
    return jid


def _version(jid, version, trigger, status, meta, request_text="", code="X = 1\n", result=None):
    from app import db
    db.ex("INSERT INTO job_versions(job_id,version,trigger,request_text,code,claude_text,meta,status,result,checks,usage,"
          "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
          (jid, version, trigger, request_text, code, "", db.jdump(meta), status, db.jdump(result or {}), "[]", "{}",
           db.now()))


def _wait(c, jid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.2)
    raise AssertionError(f"Auftrag {jid} nicht fertig")


# ------------------------------------------------------------------ B1: parse_cad

def _answer(dims):
    return ("Text\n```json\n" + json.dumps({"summary": "x", "dimensions": dims}, ensure_ascii=False)
            + "\n```\n```python\npart = Box(1, 1, 1)\n```\n")


def test_parse_dims_bereinigt():
    from app import ai
    meta, _ = ai.parse_cad(_answer([
        {"id": "D3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "ref": "m1",
         "assumed": True, "a": [0, 0, 0], "b": [0, 0, 75.0], "derived_from": None, "note": "Annahme: Höhe ≈ Breite"},
        {"id": "D3", "label": "doppelt", "var": "X_Y", "value": 1},
        {"id": "M1", "label": "alte Nummer", "var": "LENGTH", "value": 80},
        {"id": "d4", "label": "Bohrung\n Ø", "group": "loch", "var": "HOLE_D", "value": 6.5, "ref": "M2",
         "derived_from": "D3"},
        {"id": "D5", "label": "Fase", "nominal": 1.5, "a": [0, 0, 0], "b": [1.5, 0, 0], "derived_from": "D5"},
        {"id": "D6", "label": "", "var": "lower", "value": 2, "assumed": "ja", "derived_from": "D99"},
        "kein dict"]), {"M1"})
    d = {x["id"]: x for x in meta["dimensions"]}
    assert list(d) == ["D3", "D4", "D5", "D6"]
    assert d["D3"] == {"id": "D3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "ref": "M1",
                       "assumed": True, "derived_from": None, "note": "Annahme: Höhe ≈ Breite", "editable": False,
                       "a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 75.0]}
    assert (d["D4"]["label"], d["D4"]["group"], d["D4"]["ref"], d["D4"]["derived_from"]) == ("Bohrung Ø", "sonst", None, "D3")
    assert (d["D5"]["var"], d["D5"]["value"], d["D5"]["derived_from"]) == (None, 1.5, None) and "a" not in d["D5"]
    assert (d["D6"]["label"], d["D6"]["var"], d["D6"]["assumed"], d["D6"]["derived_from"]) == ("D6", None, False, None)


def test_parse_wert_als_text():
    from app import ai
    meta, _ = ai.parse_cad(_answer([
        {"id": "D1", "label": "Länge", "var": "LENGTH", "value": "75.0", "a": ["0", 0, 0], "b": [75, 0, 0]},
        {"id": "D2", "label": "Breite", "var": "WIDTH", "value": "breit"},
        {"id": "D3", "label": "Dicke", "var": "THICK", "value": True},
        {"id": "D4", "label": "Tiefe", "var": "DEPTH", "value": float("nan")}]))
    d = {x["id"]: x for x in meta["dimensions"]}
    assert d["D1"]["value"] == 75.0 and "a" not in d["D1"] and "b" not in d["D1"]      # nie ein halber Anker
    assert d["D2"]["value"] is None and d["D3"]["value"] is None and d["D4"]["value"] is None


def test_parse_hoechstens_200_und_ohne_liste():
    from app import ai
    meta, _ = ai.parse_cad(_answer([{"id": f"D{i}", "label": "x", "var": "XX", "value": 1} for i in range(1, 260)]))
    assert len(meta["dimensions"]) == 200
    meta, _ = ai.parse_cad("```json\n{\"dimensions\": {\"D1\": 1}}\n```\n```python\npart = Box(1, 1, 1)\n```\n")
    assert meta["dimensions"] == []


def test_parse_prompt_regeln_11_bis_13():
    from app import ai
    s = ai.CAD_SYSTEM
    assert "DIM_ANCHORS" in s and '"id": "D3"' in s and '"var": "BLOCK_H"' in s and '"ref": null' in s
    assert "Werte aus „Messschieber am Modell“ sind verbindlich und nie Annahmen." in " ".join(s.split())
    assert '"measured"' not in s and '"nominal"' not in s
    assert all(f"\n{n}. " in s for n in range(1, 14))


@pytest.mark.parametrize("t", [6.0, 8.0])
def test_parse_testmodus_anker_passen_zum_code(t):
    """Fake-Konstanten und DIM_ANCHORS ohne build123d auswerten: Abstand = value (B6)."""
    from app import ai
    code = ai._FAKE_V2.format(t=f"{t:.1f}")
    ns = {}
    exec(code.split("with BuildPart()")[0] + code[code.index("DIM_ANCHORS"):], ns)
    meta = ai._fake_meta(t)
    dims = {d["id"]: d for d in meta["dimensions"]}
    assert set(ns["DIM_ANCHORS"]) == {"D1", "D2", "D3", "D4", "D5", "D6"}
    for k, (a, b) in ns["DIM_ANCHORS"].items():
        assert math.dist(a, b) == pytest.approx(dims[k]["value"]), k
    assert ns["THICKNESS"] == t and dims["D3"]["assumed"] is True and dims["D3"]["value"] == t
    assert math.dist(dims["D7"]["a"], dims["D7"]["b"]) == dims["D7"]["value"] and dims["D7"]["a"][2] == t
    assert "a" not in dims["D8"] and "DIM_ANCHORS = {" in ai._FAKE_V1
    assert math.dist(dims["D9"]["a"], dims["D9"]["b"]) == dims["D9"]["value"] and "SLOT_EDGE" not in code   # nicht editierbar
    parsed, _ = ai.parse_cad("```json\n" + json.dumps(meta) + "\n```\n```python\n" + code + "```\n", {"M1"})
    assert [d["id"] for d in parsed["dimensions"]] == [f"D{i}" for i in range(1, 10)]
    assert parsed["dimensions"][0]["ref"] == "M1" and parsed["dimensions"][1]["ref"] is None
