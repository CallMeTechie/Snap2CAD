"""Bemaßung am Modell (Spec 2026-10-15 Stufe B, B1–B4)."""
import copy
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


def test_parse_var_ohne_value_nicht_editierbar():
    """Spec §1: fehlt value, bleibt das Mass auch mit var und nominal-Rueckfall nicht editierbar und ohne Anker."""
    from app import ai, jobs
    meta, code = ai.parse_cad(_answer([{"id": "D1", "label": "Länge", "var": "LENGTH", "nominal": 80,
                                        "a": [0, 0, 0], "b": [80, 0, 0]}]))
    jobs.mark_editable(meta, "LENGTH = 80\n" + code)
    d = meta["dimensions"][0]
    assert (d["var"], d["value"], d["editable"]) == (None, 80.0, False) and "a" not in d


def test_parse_nur_m_nummern_bleibt_alte_form():
    """Alte Auftraege: Antwort nur mit M-Nummern behaelt die Tabelle in alter Form (nicht editierbar)."""
    from app import ai, jobs
    meta, _ = ai.parse_cad(_answer([{"id": "m1", "label": "Länge", "measured": 79.8, "nominal": 80.0, "note": "gerundet"},
                                    {"id": "M1", "label": "doppelt", "nominal": 1},
                                    {"id": "M2", "label": "Breite", "var": "WIDTH", "value": 50, "a": [0, 0, 0]},
                                    {"id": "X9", "label": "fremd"}, "kein dict"]))
    assert meta["dimensions"] == [
        {"id": "M1", "label": "Länge", "measured": 79.8, "nominal": 80.0, "note": "gerundet", "editable": False},
        {"id": "M2", "label": "Breite", "measured": None, "nominal": None, "note": "", "editable": False}]
    jobs.mark_editable(meta, "WIDTH = 50\n")
    assert not any(d["editable"] for d in meta["dimensions"])
    mixed, _ = ai.parse_cad(_answer([{"id": "D1", "label": "Länge", "var": "LENGTH", "value": 80},
                                     {"id": "M1", "label": "alt", "nominal": 80}]))
    assert [d["id"] for d in mixed["dimensions"]] == ["D1"]        # mit D-Nummern gilt nur die neue Form


def test_ki_lauf_nur_m_nummern_tabelle_und_pruefpunkt(user, monkeypatch):
    from app import ai
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    _meas(user, pid, "Länge", 80.0, critical=True)                                   # M1
    monkeypatch.setattr(ai, "call", lambda *a, **k: (_answer([{"id": "M1", "label": "Länge", "measured": 79.8,
                                                                 "nominal": 80.0}]), {}))
    r = user.post("/api/jobs", json={"project_id": pid, "name": "Alt", "request": "x"}, headers=H)
    j = _wait(user, r.json()["id"])
    v = j["versions"][-1]
    assert j["status"] == "done" and v["status"] == "ok", j
    assert [(d["id"], d["nominal"], d["editable"]) for d in v["meta"]["dimensions"]] == [("M1", 80.0, False)]
    assert next(c for c in v["checks"] if c["id"] == "critical")["state"] == "ok"
    assert any(x["msg"] == f"Version {v['version']}: 1 Maß ohne D-Nummer (altes Format) – am Modell nicht änderbar"
               for x in j["log"])


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


# ------------------------------------------------------------------ B4: gelernte Werte

def test_lernen_label_norm():
    from app import jobs
    assert jobs.label_norm("Höhe  Block (außen)–Ø 6") == "höhe block aussen ø 6"
    assert jobs.label_norm("T2 Dicke") == "t2 dicke" and jobs.label_norm(" – ") == ""


def test_lernen_upsert_und_tabelle(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "Höhe Block", "group": "aussen", "value": 75.0}])
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "höhe  Block!", "group": "aussen", "value": 45.0}])
    rows = jobs.learned_dims(pid)
    assert [(r["label_norm"], r["label"], r["value"], r["dim_id"], r["job_id"], r["grp"]) for r in rows] == \
        [("höhe block", "höhe  Block!", 45.0, "D3", jid, "aussen")]
    assert jobs.model_dims_section(pid) == \
        f"## Messschieber am Modell (verbindlich)\n- höhe  Block!: 45 mm (Gruppe außen, gemessen am Auftrag {jid})"
    assert "Messschieber am Modell" not in jobs.measurement_table(pid)[0]      # /suggest bekommt den Abschnitt nicht


def test_lernen_label_leer_nutzt_id(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D1", "label": "–", "group": "sonst", "value": 1.0},
                               {"id": "D2", "label": "—", "group": "sonst", "value": 2.0}])
    assert sorted(r["label_norm"] for r in jobs.learned_dims(pid)) == ["d1", "d2"]


def test_lernen_in_auftrag_pruefung_und_aenderung(user, monkeypatch):
    from app import db, jobs
    pid = _proj(user)
    jid = _job(user, pid, "BLOCK_H = 75.0\n", {"dimensions": []})
    p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    txt = jobs.build_initial_message(p, "x", {"images": []})[0]["content"][0]["text"]
    assert "## Messschieber am Modell" not in txt
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    txt = jobs.build_initial_message(p, "x", {"images": []})[0]["content"][0]["text"]
    assert "## Messwerte\n(keine Messwerte – nur aus den Fotos ableiten)\n\n## Messschieber am Modell (verbindlich)" in txt
    assert f"- Höhe Block: 45 mm (Gruppe außen, gemessen am Auftrag {jid})" in txt
    chk = jobs.build_initial_message(p, "", {"images": [], "for_check": True})[0]["content"][0]["text"]
    assert "## Messschieber am Modell (verbindlich)" in chk
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    jobs.iterate(_user_row(user), db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), "Bohrung größer")
    last = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"])[-1]["content"][0]["text"]
    assert last.index("Bohrung größer") < last.index("## Messschieber am Modell") < last.index("Ausgangspunkt")


def test_lernen_ohne_werte_kein_abschnitt_in_aenderung(user, monkeypatch):
    from app import db, jobs
    pid = _proj(user)
    jid = _job(user, pid, "BLOCK_H = 75.0\n", {"dimensions": []})
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    jobs.iterate(_user_row(user), db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), "Bohrung größer")
    last = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"])[-1]["content"][0]["text"]
    assert "Messschieber am Modell" not in last


def test_lernen_abgleich(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jid2 = _job(user, pid, "X = 1\n", {"dimensions": []})
    assert jobs.reconcile_learned({"dimensions": [{"id": "D1", "label": "x", "value": 1.0}]}, pid, jid) is None
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "Höhe Block", "group": "aussen", "value": 45.0},
                               {"id": "D4", "label": "Bohrung", "group": "bohrung", "value": 6.2}])
    meta = {"dimensions": [{"id": "D3", "label": "Höhe Block", "value": 45.005, "assumed": True},
                           {"id": "D4", "label": "bohrung", "value": 6.5, "assumed": False}]}
    chk = jobs.reconcile_learned(meta, pid, jid)
    assert meta["dimensions"][0]["user_set"] is True and meta["dimensions"][0]["assumed"] is False
    assert "user_set" not in meta["dimensions"][1]
    assert chk == {"id": "model_dims", "label": "Messschieber am Modell übernommen", "state": "warn",
                   "detail": "Bohrung: 6,2 → 6,5"}
    ok = jobs.reconcile_learned({"dimensions": [{"id": "D3", "label": "Höhe Block", "value": 45.0}]}, pid, jid2)
    assert ok == {"id": "model_dims", "label": "Messschieber am Modell übernommen", "state": "ok", "detail": "1 übernommen"}


def test_lernen_abgleich_mass_entfernt(user):
    """KI entfernt ein im selben Auftrag nachgemessenes Mass: Warnung statt stiller Verlust."""
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    chk = jobs.reconcile_learned({"dimensions": [{"id": "D1", "label": "Länge", "value": 40.0}]}, pid, jid)
    assert chk == {"id": "model_dims", "label": "Messschieber am Modell übernommen", "state": "warn",
                   "detail": "Höhe Block: 45 → fehlt"}


def test_lernen_projekte_getrennt(user):
    """Spec §6: Werte eines anderen Projekts werden nie gemischt."""
    from app import jobs
    pid_a, pid_b = _proj(user), _proj(user)
    jid_a = _job(user, pid_a, "X = 1\n", {"dimensions": []})
    jid_b = _job(user, pid_b, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid_a, jid_a, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    assert jobs.model_dims_section(pid_b) == "" and jobs.learned_dims(pid_b) == []
    meta = {"dimensions": [{"id": "D2", "label": "Höhe Block", "value": 75.0, "assumed": True}]}
    assert jobs.reconcile_learned(meta, pid_b, jid_b) is None and "user_set" not in meta["dimensions"][0]


def test_lernen_abgleich_ueber_dim_id(user):
    """KI benennt ein nachgemessenes Mass um (gleiche D-Nummer) und setzt den Wert zurueck: trotzdem Warnung."""
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jid2 = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    meta = {"dimensions": [{"id": "D3", "label": "Blockhöhe", "value": 75.0, "assumed": True}]}
    assert jobs.reconcile_learned(meta, pid, jid)["detail"] == "Höhe Block: 45 → 75"
    assert jobs.reconcile_learned(copy.deepcopy(meta), pid, jid2) is None      # anderer Auftrag: D-Nummer gilt nicht


def test_lernen_migration_legt_tabelle_an():
    import sqlite3

    from app import db
    c = sqlite3.connect(":memory:")
    c.executescript(db.SCHEMA.replace("CREATE TABLE IF NOT EXISTS model_dims", "CREATE TABLE IF NOT EXISTS _alt_model_dims"))
    assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='model_dims'").fetchone()
    c.executescript(db.SCHEMA)
    db._migrate(c)
    cols = [r[1] for r in c.execute("PRAGMA table_info(model_dims)")]
    assert cols == ["id", "project_id", "label", "label_norm", "grp", "value", "job_id", "dim_id", "note", "created_at"]


# ------------------------------------------------------------------ B1: Editierbarkeit, Anker, Pruefpunkt

def test_parse_editable_nach_codepruefung():
    from app import jobs
    code = "LENGTH = 80.0  # M1\nWIDTH = 2 * 25\nHOLE_D = 4.5\nHOLE_D = 5.0\nTHICKNESS = 6.5\nLENGTH_X = 3\n"
    meta = {"dimensions": [
        {"id": "D1", "var": "LENGTH", "value": 80.0, "note": ""},
        {"id": "D2", "var": "WIDTH", "value": 50.0, "note": ""},
        {"id": "D3", "var": "HOLE_D", "value": 4.5, "note": ""},
        {"id": "D4", "var": "THICKNESS", "value": 6.0, "note": "Annahme"},
        {"id": "D5", "var": "MISSING", "value": 1.0, "note": ""},
        {"id": "D6", "var": None, "value": 3.0, "note": ""}]}
    jobs.mark_editable(meta, code)
    d = {x["id"]: x for x in meta["dimensions"]}
    assert [d[k]["editable"] for k in ("D1", "D2", "D3", "D4", "D5", "D6")] == [True, False, False, True, False, False]
    assert d["D3"]["note"] == "Konstante mehrfach belegt" and d["D1"]["value"] == 80.0
    assert d["D4"]["value"] == 6.5 and d["D4"]["note"] == "Annahme; Wert aus dem Code"
    jobs.mark_editable(meta, code)
    assert d["D4"]["note"] == "Annahme; Wert aus dem Code" and d["D3"]["note"] == "Konstante mehrfach belegt"


def test_parse_editable_var_doppelt():
    """Zwei Masse mit derselben Konstante: beide nicht editierbar, sonst widerspraechen sie sich nach dem Neuaufbau."""
    from app import jobs
    meta = {"dimensions": [{"id": "D1", "var": "LENGTH", "value": 80.0, "note": ""},
                           {"id": "D2", "var": "LENGTH", "value": 80.0, "note": "Kante"},
                           {"id": "D3", "var": "WIDTH", "value": 50.0, "note": ""},
                           {"id": "D4", "var": "WIDTH)|(.*", "value": 50.0, "note": ""}]}
    jobs.mark_editable(meta, "LENGTH = 80.0\nWIDTH = 50.0\n")
    d = {x["id"]: x for x in meta["dimensions"]}
    assert [d[k]["editable"] for k in ("D1", "D2", "D3", "D4")] == [False, False, True, False]
    assert d["D1"]["note"] == "Konstante mehrfach belegt" and d["D2"]["note"] == "Kante; Konstante mehrfach belegt"


def test_anker_aus_dim_anchors_vor_ab_und_abstand():
    from app import jobs
    meta = {"dimensions": [
        {"id": "D1", "var": "A", "value": 10.0, "a": [0, 0, 0], "b": [5, 0, 0]},
        {"id": "D2", "var": "B", "value": 5.0, "a": [0, 0, 0], "b": [0, 5, 0]},
        {"id": "D3", "var": "C", "value": 5.0, "a": [0, 0, 0], "b": [0, 7, 0]},
        {"id": "D4", "var": "DD", "value": 100.0, "a": [0, 0, 0], "b": [100.9, 0, 0]},
        {"id": "D5", "var": "EE", "value": 100.0, "a": [0, 0, 0], "b": [101.1, 0, 0]},
        {"id": "D6", "var": "FF", "value": 5.0, "a": [0, 0, 0], "b": [5.09, 0, 0]},
        {"id": "D7", "var": "GG", "value": 5.0},
        {"id": "D8", "var": None, "value": 5.0, "a": [0, 0, 0], "b": [5, 0, 0]},
        {"id": "D9", "var": "HH", "value": 5.0, "anchors_stale": True, "a": [0, 0, 0], "b": [5, 0, 0]}]}
    result = {"dim_anchors": {"D1": [[0, 0, 0], [10, 0, 0]], "D7": [[0, 0, 0], [0, 0]], "D9": [[1, 1, 1], [1, 1, 6]]}}
    jobs._apply_anchors(meta, result)
    d = {x["id"]: x for x in meta["dimensions"]}
    assert (d["D1"]["a"], d["D1"]["b"]) == ([0.0, 0.0, 0.0], [10.0, 0.0, 0.0])
    assert d["D2"]["b"] == [0.0, 5.0, 0.0] and "a" in d["D4"] and "a" in d["D6"]
    assert [k for k in ("D3", "D5", "D7", "D8") if "a" in d[k] or "b" in d[k]] == []
    assert d["D9"]["b"] == [1.0, 1.0, 6.0] and "anchors_stale" not in d["D9"]


def test_anker_server_filtert():
    """dim_anchors kommt aus dem Prozess des Modellcodes: der Server filtert erneut und speichert nur Gueltiges."""
    from app import jobs
    raw = {"D1": [[0, 0, 0], [1.23456, 0, 0]], "D1\n": [[0, 0, 0], [1, 0, 0]], "M1": [[0, 0, 0], [1, 0, 0]],
           "D2": [[0, 0, "1"], [1, 0, 0]], "D3": [[0, 0, 0]], "D4": "kaputt", "D5": [[0, 0, 0], [0, 0, True]],
           "<img src=x>": [[0, 0, 0], [1, 0, 0]], "D6": [[0, 0, 0], [0, 2, 0]]}
    raw.update({f"D{i}": [[0, 0, 0], [i, 0, 0]] for i in range(100, 400)})
    result = {"bbox": [1, 2, 3], "dim_anchors": raw}
    jobs._filter_anchors(result)
    da = result["dim_anchors"]
    assert da["D1"] == [[0.0, 0.0, 0.0], [1.2346, 0.0, 0.0]] and da["D6"] == [[0.0, 0.0, 0.0], [0.0, 2.0, 0.0]]
    assert not {"D1\n", "M1", "D2", "D3", "D4", "D5", "<img src=x>"} & set(da) and len(da) == 200
    for bad in ([1, 2], None, "D1"):
        r = {"bbox": [1, 2, 3], "dim_anchors": bad}
        jobs._filter_anchors(r)
        assert r == {"bbox": [1, 2, 3]}
    jobs._filter_anchors(None)


def test_anker_rueckfall_param_gestreckt_und_stale():
    from app import jobs
    meta = {"dimensions": [
        {"id": "D1", "var": "H", "value": 45.0, "a": [0, 0, 0], "b": [0, 0, 75]},
        {"id": "D2", "var": "W", "value": 40.0, "a": [0, 0, 0], "b": [40, 0, 0]},
        {"id": "D3", "var": "DD", "value": 6.0, "a": [0, 0, 0], "b": [6, 0, 0], "anchors_stale": True}]}
    jobs._apply_anchors(meta, {"dim_anchors": {"D3": [[1, 0, 0], [7, 0, 0]]}}, changed={"D1"})
    d = {x["id"]: x for x in meta["dimensions"]}
    assert d["D1"]["b"] == [0.0, 0.0, 45.0] and "anchors_stale" not in d["D1"]
    assert d["D2"]["anchors_stale"] is True and d["D2"]["b"] == [40.0, 0.0, 0.0]
    assert "anchors_stale" not in d["D3"] and d["D3"]["a"] == [1.0, 0.0, 0.0]


def test_pruefpunkt_kritisch_ueber_ref(user):
    from app import jobs
    pid = _proj(user)
    _meas(user, pid, "Länge", 80.0, critical=True)                                   # M1
    res = {"valid": True, "solids": 1, "stl": {"watertight": True, "triangles": 12}}

    def crit(dims):
        return next(c for c in jobs.compute_checks(res, {"dimensions": dims}, pid) if c["id"] == "critical")
    assert crit([{"id": "D1", "ref": "M1", "value": 80.1}])["state"] == "ok"
    far = crit([{"id": "D1", "ref": "M1", "value": 85.0}])
    assert far["state"] == "warn" and far["detail"] == "stark gerundet: M1 80,00 → 85,00"
    assert crit([{"id": "D1", "ref": None, "value": 80.0}])["detail"] == "nicht ausgewiesen: M1"
    assert crit([{"id": "M1", "nominal": 80.0}])["state"] == "ok"                      # alte Version


def test_anker_nach_ki_lauf(user):
    pid = _proj(user)
    _meas(user, pid, "Länge", 80.0)                                                   # M1
    r = user.post("/api/jobs", json={"project_id": pid, "name": "Platte", "request": "x"}, headers=H)
    j = _wait(user, r.json()["id"])
    v = j["versions"][-1]
    assert j["status"] == "done" and v["status"] == "ok", j
    d = {x["id"]: x for x in v["meta"]["dimensions"]}
    assert set(v["result"]["dim_anchors"]) == {"D1", "D2", "D3", "D4", "D5", "D6"}
    assert d["D1"]["ref"] == "M1" and d["D2"]["ref"] is None
    assert (d["D3"]["a"], d["D3"]["b"]) == ([40.0, 25.0, 0.0], [40.0, 25.0, 6.0]) and d["D4"]["a"][2] == 6.0
    assert (d["D7"]["a"], d["D7"]["b"]) == ([0.0, -4.0, 6.0], [0.0, 4.0, 6.0]) and "anchors_stale" not in d["D7"]
    assert "a" not in d["D8"] and all(x["editable"] for k, x in d.items() if k != "D9")
    assert d["D9"]["editable"] is False and (d["D9"]["a"], d["D9"]["b"]) == ([15.0, 0.0, 6.0], [40.0, 0.0, 6.0])


# ------------------------------------------------------------------ B2/B3: Param-Neuaufbau

BLOCK = '''BLOCK_L = 40.0  # Laenge
BLOCK_H = 75.0  # Hoehe, Annahme
HOLE_D = 6.0
part = Box(BLOCK_L, BLOCK_L, BLOCK_H, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Cylinder(
    HOLE_D / 2, BLOCK_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
DIM_ANCHORS = {"D1": ((-BLOCK_L / 2, -BLOCK_L / 2, 0), (BLOCK_L / 2, -BLOCK_L / 2, 0)),
               "D2": ((BLOCK_L / 2, -BLOCK_L / 2, 0), (BLOCK_L / 2, -BLOCK_L / 2, BLOCK_H))}
'''
BLOCK_META = {"dimensions": [
    {"id": "D1", "label": "Länge", "group": "aussen", "var": "BLOCK_L", "value": 40.0, "assumed": False, "editable": True,
     "a": [-20.0, -20.0, 0.0], "b": [20.0, -20.0, 0.0]},
    {"id": "D2", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "assumed": True,
     "editable": True, "a": [20.0, -20.0, 0.0], "b": [20.0, -20.0, 75.0]},
    {"id": "D3", "label": "Bohrung", "group": "bohrung", "var": "HOLE_D", "value": 6.0, "assumed": False, "editable": True,
     "a": [-3.0, 0.0, 75.0], "b": [3.0, 0.0, 75.0]},
    {"id": "D4", "label": "Fase", "group": "fase", "var": None, "value": 1.0, "assumed": True, "editable": False}]}


def _fake_sandbox(monkeypatch, ok=True, anchors=None, block=False):
    from app import sandbox
    seen = []

    def run(code, dest, cancel=None):
        seen.append(code)
        dest.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while block and not cancel.is_set() and time.time() - t0 < 10:
            time.sleep(0.05)
        if block:
            raise sandbox.Cancelled()
        if not ok:
            return {"ok": False, "seconds": 0.1, "error": {"stage": "model", "type": "ValueError", "message": "kaputt",
                                                         "line": 3, "code": "x", "traceback": ""}}
        res = {"valid": True, "solids": 1, "bbox": [40.0, 40.0, 45.0], "stl": {"triangles": 12, "watertight": True}}
        if anchors is not None:
            res["dim_anchors"] = anchors
        return {"ok": True, "seconds": 0.1, "result": res}
    monkeypatch.setattr(sandbox, "run", run)
    return seen


def test_param_ersetzung_mit_kommentar():
    from app import jobs
    assert jobs.set_const("VAR = 75.0  # Kommentar\nB = 2\n", "VAR", 45.0) == ("VAR = 45  # Kommentar\nB = 2\n", 1)
    assert jobs.set_const("VAR=1\n", "VAR", 12.3456) == ("VAR=12.346\n", 1)
    assert jobs.set_const("VAR = 2 * B\n", "VAR", 3.0) == ("VAR = 2 * B\n", 0)
    assert jobs.set_const("VAR_X = 1\n", "VAR", 3.0)[1] == 0
    assert jobs.set_const("WIDTH = 50.0\n", "WIDTH)|(.*", 3.0) == ("WIDTH = 50.0\n", 0)     # var ausserhalb ai._VAR


def test_param_version_ohne_ki_mit_ankern(user, monkeypatch):
    from app import ai, db, jobs
    calls, real = [], ai.call
    monkeypatch.setattr(ai, "call", lambda *a, **k: (calls.append(a[0]), real(*a, **k))[1])
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert r.status_code == 200 and r.json() == {"version": 2}, r.text
    j = _wait(user, jid)
    v = j["versions"][-1]
    assert calls == [] and j["status"] == "done" and j["current_version"] == 2, j
    assert (v["trigger"], v["request_text"], v["claude_text"], v["status"]) == ("param", "D2 = 45 mm", "", "ok")
    assert "BLOCK_H = 45  # Hoehe, Annahme\n" in v["code"] and v["result"]["bbox"] == [40.0, 40.0, 45.0]
    d = {x["id"]: x for x in v["meta"]["dimensions"]}
    assert (d["D2"]["value"], d["D2"]["assumed"], d["D2"]["user_set"], d["D2"]["derived_from"]) == (45.0, False, True, None)
    assert v["result"]["dim_anchors"]["D2"] == [[20.0, -20.0, 0.0], [20.0, -20.0, 45.0]]
    assert d["D2"]["b"] == [20.0, -20.0, 45.0] and "anchors_stale" not in d["D1"] and d["D3"]["anchors_stale"] is True
    assert v["meta"]["param_ids"] == ["D2"] and 0 < v["seconds"] < 30
    assert db.q1("SELECT detail FROM audit WHERE action='cad_param' ORDER BY id DESC LIMIT 1")["detail"] == \
        f"Auftrag {jid}: D2 = 45 mm"
    assert j["pending_param"] == [{"id": "D2", "label": "Höhe Block", "value": 45.0, "old": 75.0, "old_assumed": True}]
    msgs = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"])
    assert msgs[-1]["content"][0]["text"] == "Parametrisch geändert: D2 = 45 mm (Version 2)"
    assert [(x["label"], x["value"], x["dim_id"], x["job_id"]) for x in jobs.learned_dims(pid)] == \
        [("Höhe Block", 45.0, "D2", jid)]


def test_param_mehrere_werte_und_fehler(user, monkeypatch):
    from app import db, sandbox
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    r = user.post(url, json={"values": [{"id": "D4", "value": 2}]}, headers=H)
    assert r.status_code == 400 and r.json()["detail"] == "Maß D4 ist nicht editierbar"
    assert user.post(url, json={"values": [{"id": "D9", "value": 2}]}, headers=H).status_code == 400
    assert user.post(url, json={"values": [{"id": "D1", "value": 1}] * 21}, headers=H).status_code == 422
    assert user.post(url, json={"values": []}, headers=H).status_code == 422
    monkeypatch.setattr(sandbox, "worker_alive", lambda: False)
    assert user.post(url, json={"values": [{"id": "D1", "value": 41}]}, headers=H).status_code == 503
    monkeypatch.setattr(sandbox, "worker_alive", lambda: True)
    db.ex("UPDATE jobs SET status='running' WHERE id=?", (jid,))
    r = user.post(url, json={"values": [{"id": "D1", "value": 41}]}, headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Der Auftrag läuft noch."
    db.ex("UPDATE jobs SET status='done' WHERE id=?", (jid,))
    assert db.q1("SELECT COUNT(*) n FROM job_versions WHERE job_id=?", (jid,))["n"] == 1   # Fehlversuche: keine Version
    r = user.post(url, json={"values": [{"id": "D1", "value": 41}, {"id": "D3", "value": 6.5}]}, headers=H)
    assert r.status_code == 200
    v = _wait(user, jid)["versions"][-1]
    assert v["request_text"] == "D1 = 41 mm, D3 = 6.5 mm" and v["status"] == "ok"
    assert "BLOCK_L = 41  # Laenge\n" in v["code"] and "\nHOLE_D = 6.5\n" in v["code"]


def test_param_ungueltige_werte(user, monkeypatch):
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    for bad in (0, -1, 5000.5, "abc", None, True, "45"):           # strict: kein bool, kein Zahlentext
        assert user.post(url, json={"values": [{"id": "D1", "value": bad}]}, headers=H).status_code == 422, bad
    for raw in ('{"values": [{"id": "D1", "value": NaN}]}', '{"values": [{"id": "D1", "value": Infinity}]}'):
        r = user.post(url, content=raw, headers={**H, "Content-Type": "application/json"})
        assert r.status_code == 422, raw
    assert user.post(url, json={"values": [{"id": "d1", "value": 2}]}, headers=H).status_code == 422
    r = user.post(url, json={"values": [{"id": "D1", "value": 0.0001}]}, headers=H)
    assert r.status_code == 400 and "größer als 0" in r.json()["detail"]


def test_param_basis_veraltet(user, monkeypatch):
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    r = user.post(url, json={"values": [{"id": "D1", "value": 41}], "base": 7}, headers=H)
    assert r.status_code == 409 and "nicht mehr aktuell" in r.json()["detail"]
    assert user.post(url, json={"values": [{"id": "D1", "value": 41}], "base": 1}, headers=H).status_code == 200
    _wait(user, jid)
    r = user.post(url, json={"values": [{"id": "D1", "value": 42}], "base": 1}, headers=H)     # zweiter Tab, alter Stand
    assert r.status_code == 409


def test_version_rueckfall_gestreckt_und_stale(user, monkeypatch):
    _fake_sandbox(monkeypatch)                                         # Ergebnis ohne dim_anchors
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    d = {x["id"]: x for x in _wait(user, jid)["versions"][-1]["meta"]["dimensions"]}
    assert d["D2"]["b"] == [20.0, -20.0, 45.0] and "anchors_stale" not in d["D2"]
    assert d["D1"]["anchors_stale"] is True and d["D3"]["anchors_stale"] is True and "a" not in d["D4"]


def test_version_huellquader_ohne_ki_erwartung(user, monkeypatch):
    """bbox_expected der KI gilt fuer den alten Wert: ohne Entfernen scheiterte jeder groessere Neuaufbau (75 -> 45)."""
    _fake_sandbox(monkeypatch)                                         # Ergebnis 40 x 40 x 45
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, {**copy.deepcopy(BLOCK_META), "bbox_expected": [40.0, 40.0, 75.0]})
    user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    j = _wait(user, jid)
    v = j["versions"][-1]
    assert j["status"] == "done" and v["status"] == "ok", v["checks"]
    assert "bbox_expected" not in v["meta"] and "bbox" not in {c["id"] for c in v["checks"]}


def test_version_sandbox_fehler_basis_bleibt(user, monkeypatch):
    from app import db, jobs
    _fake_sandbox(monkeypatch, ok=False)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    assert user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 200
    j = _wait(user, jid)
    assert j["status"] == "failed" and j["current_version"] == 1 and j["versions"][-1]["status"] == "failed"
    assert any(x["msg"] == "Version 2: Neuaufbau mit D2 = 45 mm fehlgeschlagen – ValueError (Zeile 3): kaputt"
               for x in j["log"]), j["log"]
    assert j["pending_param"] == [] and [x["value"] for x in jobs.learned_dims(pid)] == [45.0]   # §2.4: Wert bleibt
    assert db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"]) == []


def test_version_abbrechen(user, monkeypatch):
    _fake_sandbox(monkeypatch, block=True)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert user.post(f"/api/jobs/{jid}/cancel", headers=H).status_code == 200
    j = _wait(user, jid)
    assert j["status"] == "cancelled" and j["current_version"] == 1
    time.sleep(0.5)
    assert user.get(f"/api/jobs/{jid}").json()["versions"][-1]["status"] == "cancelled"


def test_param_ohne_projekt(user, monkeypatch):
    from app import db
    _fake_sandbox(monkeypatch)
    jid = _job(user, None, BLOCK, copy.deepcopy(BLOCK_META))
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert r.json() == {"version": 2, "learned": False}
    assert _wait(user, jid)["status"] == "done"
    assert db.q1("SELECT COUNT(*) n FROM model_dims WHERE job_id=?", (jid,))["n"] == 0


def test_param_fremder_nutzer(user, app, admin, monkeypatch):
    from fastapi.testclient import TestClient
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremdb{jid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 404
    for bad in (0, 9999):                       # Besitz vor Wertebereich: fremder Auftrag bleibt 404, nicht 422
        assert f.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": bad}]},
                      headers=H).status_code == 404
    assert user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 0}]}, headers=H).status_code == 422


def test_version_pending_param_reihenfolge(user):
    from app import db, jobs
    pid = _proj(user)
    m = copy.deepcopy(BLOCK_META)
    jid = _job(user, pid, BLOCK, m)

    def meta(*ids, **vals):
        """Meta wie BLOCK_META mit gesetzten Werten; ids = param_ids einer Param-Version."""
        out = copy.deepcopy(m)
        for d in out["dimensions"]:
            if d["id"] in vals:
                d.update(value=vals[d["id"]], assumed=False, user_set=True)
        if ids:
            out["param_ids"] = list(ids)
        return out
    def ver(n, trigger, status, mt, req=""):
        """Version anlegen; eine ok-Version wird wie im echten Lauf aktuell."""
        _version(jid, n, trigger, status, mt, req)
        if status == "ok":
            db.ex("UPDATE jobs SET current_version=? WHERE id=?", (n, jid))
    ver(2, "param", "ok", meta("D2", D2=45.0), "D2 = 45 mm")
    ver(3, "param", "failed", meta("D1", D2=45.0, D1=50.0), "D1 = 50 mm")
    ver(4, "param", "ok", meta("D1", D2=45.0, D1=41.0), "D1 = 41 mm")
    assert jobs.pending_param(jid) == [
        {"id": "D2", "label": "Höhe Block", "value": 45.0, "old": 75.0, "old_assumed": True},
        {"id": "D1", "label": "Länge", "value": 41.0, "old": 40.0, "old_assumed": False}]
    ver(5, "iterate", "failed", meta())          # fehlgeschlagene KI-Version setzt nichts zurueck
    assert [p["id"] for p in jobs.pending_param(jid)] == ["D2", "D1"]
    _version(jid, 6, "iterate", "ok", meta(D2=45.0, D1=41.0))   # ok, aber durch Abbruch nie aktuell geworden
    assert [p["id"] for p in jobs.pending_param(jid)] == ["D2", "D1"]
    db.ex("UPDATE jobs SET current_version=6 WHERE id=?", (jid,))
    assert jobs.pending_param(jid) == []
    ver(7, "param", "ok", meta("D3", D2=45.0, D1=41.0, D3=6.5), "D3 = 6.5 mm")
    assert jobs.pending_param(jid) == [{"id": "D3", "label": "Bohrung", "value": 6.5, "old": 6.0, "old_assumed": False}]
    ver(8, "param", "ok", meta(D2=45.0, D1=41.0, D3=7.0), "D3 = 7 mm")       # ohne param_ids: zaehlt nicht
    assert [p["value"] for p in jobs.pending_param(jid)] == [6.5]


def test_param_ohne_kontingent_und_ki(user, monkeypatch):
    """Kein _check_quota, kein _check_ready: Neuaufbau geht auch bei erschoepftem Kontingent und ohne KI."""
    from fastapi import HTTPException

    from app import jobs
    _fake_sandbox(monkeypatch)

    def boom(*a, **k):
        raise HTTPException(429, "darf nicht aufgerufen werden")
    monkeypatch.setattr(jobs, "_check_quota", boom)
    monkeypatch.setattr(jobs, "_check_ready", boom)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert r.status_code == 200, r.text
    assert _wait(user, jid)["status"] == "done"


def test_param_cad_gesperrt(user, monkeypatch):
    from app import db
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    db.ex("UPDATE users SET cad_quota=0 WHERE username=?", (user.username,))
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert r.status_code == 403 and r.json()["detail"] == "CAD ist für dieses Konto gesperrt."
    assert db.q1("SELECT COUNT(*) n FROM job_versions WHERE job_id=?", (jid,))["n"] == 1


def test_param_grenzen(user, monkeypatch):
    """Hoechstens PARAM_PER_HOUR Neuaufbauten je Stunde und ein laufender je Nutzer (Pool ist geteilt)."""
    from app import config, db
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    monkeypatch.setattr(config, "PARAM_PER_HOUR", 1)
    assert user.post(url, json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 200
    _wait(user, jid)
    r = user.post(url, json={"values": [{"id": "D2", "value": 46}]}, headers=H)
    assert r.status_code == 429 and "je Stunde" in r.json()["detail"]
    monkeypatch.setattr(config, "PARAM_PER_HOUR", 30)
    jid2 = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    _version(jid2, 2, "param", "running", copy.deepcopy(BLOCK_META), "D2 = 50 mm")
    db.ex("UPDATE jobs SET status='running' WHERE id=?", (jid2,))
    r = user.post(url, json={"values": [{"id": "D2", "value": 46}]}, headers=H)
    assert r.status_code == 429 and r.json()["detail"] == "Es läuft bereits ein Neuaufbau. Bitte warten."
    db.ex("UPDATE jobs SET status='cancelled' WHERE id=?", (jid2,))   # abgebrochener Auftrag zaehlt nicht mehr
    assert user.post(url, json={"values": [{"id": "D2", "value": 46}]}, headers=H).status_code == 200
    _wait(user, jid)


def test_param_annahme_bestaetigen(user, monkeypatch):
    """Spec §3: Enter mit unveraendertem Wert bestaetigt eine Annahme als nachgemessen."""
    from app import jobs
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    assert user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 75}]}, headers=H).status_code == 200
    v = _wait(user, jid)["versions"][-1]
    d = {x["id"]: x for x in v["meta"]["dimensions"]}
    assert v["status"] == "ok" and "BLOCK_H = 75  # Hoehe, Annahme\n" in v["code"]
    assert (d["D2"]["value"], d["D2"]["assumed"], d["D2"]["user_set"]) == (75.0, False, True)
    assert [x["value"] for x in jobs.learned_dims(pid)] == [75.0]


def test_version_zweiter_param_baut_eigene_version(user, monkeypatch):
    """Abbrechen und sofort neu anfordern: jeder Pool-Lauf baut seine Version, der abgebrochene nur seine."""
    import threading

    from app import jobs
    subs = []
    monkeypatch.setattr(jobs, "_submit", lambda *a: subs.append(a))
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    assert user.post(url, json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 200
    assert user.post(f"/api/jobs/{jid}/cancel", headers=H).status_code == 200
    assert user.post(url, json={"values": [{"id": "D2", "value": 50}]}, headers=H).json() == {"version": 3}
    assert subs == [(jid, "param", "2"), (jid, "param", "3")]
    _fake_sandbox(monkeypatch)
    ev1 = threading.Event()
    ev1.set()                                                          # Lauf 1 wurde abgebrochen
    jobs._run_safe(jid, "param", "2", ev1)
    ev2 = threading.Event()
    jobs._cancel[jid] = ev2
    jobs._run_safe(jid, "param", "3", ev2)
    j = user.get(f"/api/jobs/{jid}").json()
    assert (j["status"], j["current_version"]) == ("done", 3), j
    assert "BLOCK_H = 50  # Hoehe, Annahme\n" in j["versions"][-1]["code"] and j["versions"][-1]["status"] == "ok"
    assert j["versions"][1]["status"] == "cancelled"


def test_version_param_fehlt_nicht_queued(user, monkeypatch):
    """Ist die Param-Version vor dem Lauf nicht mehr running, bleibt der Auftrag nicht fuer immer queued."""
    import threading

    from app import db, jobs
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    assert user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 200
    db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND version=2", (jid,))
    ev = threading.Event()
    jobs._cancel[jid] = ev
    jobs._run_safe(jid, "param", "2", ev)
    j = user.get(f"/api/jobs/{jid}").json()
    assert (j["status"], j["error"], j["current_version"]) == ("failed", "Neuaufbau abgebrochen.", 1)


def test_lernen_gleiche_bezeichnung_zwei_masse(user, monkeypatch):
    """Zwei Masse mit gleicher Bezeichnung im Auftrag ueberschreiben sich beim Lernen nicht (UPSERT je label_norm)."""
    from app import jobs
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    meta = {"dimensions": [
        {"id": "D3", "label": "Bohrung", "group": "bohrung", "var": "HOLE_D", "value": 6.0, "assumed": False, "editable": True},
        {"id": "D5", "label": "Bohrung", "group": "bohrung", "var": "HOLE_E", "value": 4.0, "assumed": False,
         "editable": True}]}
    jid = _job(user, pid, "HOLE_D = 6.0\nHOLE_E = 4.0\npart = Box(1, 1, 1)\n", meta)
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D3", "value": 6.5}, {"id": "D5", "value": 4.2}]},
                  headers=H)
    assert r.status_code == 200, r.text
    assert _wait(user, jid)["versions"][-1]["meta"]["dimensions"][0]["label"] == "Bohrung"     # Meta behaelt das Label
    assert [(x["label"], x["value"], x["dim_id"]) for x in jobs.learned_dims(pid)] == \
        [("Bohrung (D3)", 6.5, "D3"), ("Bohrung (D5)", 4.2, "D5")]


# ------------------------------------------------------------------ B4: Pruefsumme, API, CSV

def test_hash_ohne_gelernte_werte_unveraendert(user):
    """Bestehende Projekte: Pruefsumme ohne model_dims-Schluessel, sonst waere jede gespeicherte Pruefung veraltet."""
    import hashlib

    from app import check, db
    pid = _proj(user)
    p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    blob = check.hash_blob(p, None, None)
    assert set(blob) == {"photos", "meas", "parts", "part_id", "material"}
    assert check.cad_hash(p, None, None) == hashlib.sha256(
        json.dumps(blob, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def test_lernen_hash_veraltet_und_loeschen(user):
    from app import check, db, jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})

    def h():
        return check.cad_hash(db.q1("SELECT * FROM projects WHERE id=?", (pid,)), None, None)
    h0 = h()
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    assert h() != h0
    md = user.get(f"/api/projects/{pid}").json()["model_dims"]
    assert [(m["label"], m["value"], m["grp"], m["dim_id"], m["job_id"]) for m in md] == \
        [("Höhe Block", 45.0, "aussen", "D2", jid)]
    assert set(md[0]) == {"id", "label", "grp", "value", "job_id", "dim_id", "created_at"}
    assert user.delete(f"/api/projects/{pid}/model-dims/{md[0]['id']}", headers=H).json() == {"ok": True}
    assert user.get(f"/api/projects/{pid}").json()["model_dims"] == [] and h() == h0
    assert db.q1("SELECT detail FROM audit WHERE action='model_dim_delete' ORDER BY id DESC LIMIT 1")["detail"] == \
        f"Projekt {pid}: Höhe Block"
    assert user.delete(f"/api/projects/{pid}/model-dims/{md[0]['id']}", headers=H).status_code == 404


def test_lernen_loeschen_fremd(user, app, admin):
    from fastapi.testclient import TestClient

    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    mid = jobs.learned_dims(pid)[0]["id"]
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    f.post(f"/api/invite/{tok}", json={"username": f"fremdm{pid}", "display_name": "Fremd",
                                       "password": "Schieblehre-Messing-7"}, headers=H)
    own = f.post("/api/projects", json={"name": "f"}, headers=H).json()["id"]
    assert f.delete(f"/api/projects/{pid}/model-dims/{mid}", headers=H).status_code == 404
    assert f.delete(f"/api/projects/{own}/model-dims/{mid}", headers=H).status_code == 404
    assert len(jobs.learned_dims(pid)) == 1


def test_lernen_csv_modell_zeilen(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "=Höhe", "group": "aussen", "value": 45.5}])
    csv = user.get(f"/api/projects/{pid}/measurements.csv").text
    assert f"\r\nD2;'=Höhe;außen;45,5;mm;;45,5;;;Modell;Auftrag {jid};;;\r\n" in csv
