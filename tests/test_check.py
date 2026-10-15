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


def test_parse_check_defensiv():
    from app import ai
    txt = ('Hier: {"items": [{"kind": "hoehe", "text": "' + "x" * 300 + '"}, {"kind": "bottom", "severity": "block", "text": 5},'
           ' {"kind": "height", "severity": "block", "text": "Höhe\\n fehlt"}],'
           ' "material": {"color": "silber", "transparent": 7, "finish": "rau", "note": ["x"]}}')
    r = ai.parse_check(txt)
    assert r["items"] == [{"kind": "other", "severity": "warn", "text": "x" * 200},
                          {"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    assert r["material"] == {"color": "silber", "material": None, "transparent": None, "finish": None, "note": ""}
    assert ai.parse_check("[]")["items"] == [] and ai.parse_check("kein json")["material"] is None


def test_prompt_regeln():
    from app import ai
    assert "ist verbindlich" in ai.CAD_SYSTEM and "Innenbohrungen" in ai.CAD_SYSTEM
    assert "so einfach wie möglich" not in ai.CAD_SYSTEM
    assert "Fotografiertes Original" in ai.CAD_SYSTEM and "Punkt der Prüfung" in ai.CAD_SYSTEM
    assert "nicht verbindlich" in ai.CAD_SYSTEM
    assert "Innenbohrungen" in ai.CHECK_SYSTEM and "keine Nuten, Rillen oder Stufen" in ai.CHECK_SYSTEM


def test_kein_temperature_an_sdk(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from app import ai, config, settings
    seen = []

    class Stream:
        text_stream = iter(["ok"])

        def get_final_message(self):
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="m", stop_reason="end_turn")

    @contextmanager
    def stream(**kw):
        seen.append(kw)
        yield Stream()
    monkeypatch.setattr(config, "AI_FAKE", False)
    monkeypatch.setattr(settings, "api_key", lambda: "k")
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    ai.call("s", [{"role": "user", "content": "x"}])
    assert "temperature" not in seen[0]


def test_nachricht_bilder_und_text(proj):
    from app import db, jobs
    c, pid, t, b = proj
    g = _up(c, pid, TOP, "tilted")
    for _ in range(4):
        _up(c, pid, TOP, "top")
    c.patch(f"/api/projects/{pid}", headers=H,
            json={"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt"})
    imgs = jobs.pick_images(pid, None)
    # 5 Draufsichten + 1 unten + 1 gekippt -> 6, gekippt faellt weg
    assert [i["kind"] for i in imgs] == ["top"] * 5 + ["bottom"]
    imgs = jobs.pick_images(pid, [t["id"], b["id"], g["id"]])
    assert [i["kind"] for i in imgs] == ["top", "bottom", "tilted"]
    assert imgs[1]["path"].name == "rect_top.jpg" and "gespiegelt auf Draufsicht-Koordinaten" in imgs[1]["caption"]
    assert imgs[2]["path"].name == "small.jpg" and "Schrägansicht" in imgs[2]["caption"] and imgs[2]["path"].is_file()
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    items = [{"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    opts = {"photo_ids": [t["id"], b["id"], g["id"]], "name": "x", "check_items": items}
    text = jobs.build_initial_message(project, "Nachbauen", opts)[0]["content"][0]["text"]
    assert "Fotografiertes Original (nicht das Fertigungsmaterial): silber, Aluminium, transparent: teilweise, matt" in text
    assert ("## Hinweise der Prüfung (nicht verbindlich – Umriss, Unteransicht und Regel 9 gehen vor)\n"
            "- [block] Höhe fehlt") in text
    assert "Offene Punkte der Prüfung" not in text
    chk = jobs.build_initial_message(project, "", {"photo_ids": None, "part_id": None, "for_check": True,
                                                   "process": "cnc", "cutter_d": 6})
    assert "Fräser" not in chk[0]["content"][0]["text"] and "Wunsch des Nutzers" not in chk[0]["content"][0]["text"]
    db.ex("UPDATE projects SET material_user=0 WHERE id=?", (pid,))
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    chk = jobs.build_initial_message(project, "", {"photo_ids": None, "for_check": True})
    assert "Fotografiertes Original" in chk[0]["content"][0]["text"]                # KI-Schaetzung gehoert in die Pruefung
    assert "Fotografiertes Original" in jobs.build_initial_message(project, "x", {"photo_ids": None})[0]["content"][0]["text"]


def test_nachricht_ohne_draufsicht(user):
    from app import jobs
    pid = user.post("/api/projects", json={"name": "Nur unten"}, headers=H).json()["id"]
    _up(user, pid, bottom_of(TOP, 0), "bottom")
    imgs = jobs.pick_images(pid, None)
    assert [i["kind"] for i in imgs] == ["bottom"] and "nicht ausgerichtet, links-rechts gespiegelt" in imgs[0]["caption"]


def test_auftrag_mit_check_items(proj):
    from app import db
    c, pid, t, b = proj
    items = [{"kind": "height", "severity": "block", "text": "Höhe fehlt"}]
    r = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "x", "check_items": items}, headers=H)
    assert r.status_code == 200, r.text
    msgs = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (r.json()["id"],))["messages"])
    assert "- [block] Höhe fehlt" in msgs[0]["content"][0]["text"]
    bad = [{"kind": "x", "severity": "block", "text": "t"}]
    r = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "x", "check_items": bad}, headers=H)
    assert r.status_code == 422


def test_cad_check_testmodus(proj, monkeypatch):
    from app import ai
    c, pid, t, b = proj
    calls, orig = [], ai.call
    # nur Pruefaufrufe zaehlen: ein Job-Thread aus einem Vortest ruft ai.call sonst dazwischen auf
    monkeypatch.setattr(ai, "call", lambda s, *a, **k: (calls.append(k) if s == ai.CHECK_SYSTEM else None, orig(s, *a, **k))[1])
    r = c.post(f"/api/projects/{pid}/cad-check", json={"photo_ids": None, "part_id": None}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [(i["kind"], i["severity"]) for i in j["items"]] == [("height", "block"), ("bottom", "warn")]
    assert j["material"]["material"] == "Aluminium" and [i["kind"] for i in j["images"]] == ["top", "bottom"]
    assert "temperature" not in calls[-1] and j["stale"] is False
    p = c.get(f"/api/projects/{pid}").json()
    assert p["material"] == "Aluminium" and p["material_user"] == 0 and p["cad_check"]["stale"] is False
    n = len(calls)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()["hash"] == j["hash"] and len(calls) == n
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    assert len(calls) == n + 1
    assert c.get("/api/projects", headers=H).json()[0]["cad_check"] is None            # Liste ohne Hash-Rechnung


def test_idempotent_nach_schaetzung_und_handeingabe(proj):
    c, pid, t, b = proj
    j = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is False      # KI-Schaetzung veraltet die Pruefung nicht
    c.patch(f"/api/projects/{pid}", json={"material": "Stahl"}, headers=H)
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is True       # Handeingabe schon
    j2 = c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()
    assert j2["hash"] != j["hash"] and c.get(f"/api/projects/{pid}").json()["material"] == "Stahl"


def test_hash_aufgeloeste_fotos(proj):
    c, pid, t, b = proj
    j = c.post(f"/api/projects/{pid}/cad-check", json={"photo_ids": None}, headers=H).json()
    _up(c, pid, TOP, "top")
    assert c.get(f"/api/projects/{pid}").json()["cad_check"]["stale"] is True
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).json()["hash"] != j["hash"]


def test_cad_check_tageslimit(proj):
    from app import db
    c, pid, t, b = proj
    uid = c.get("/api/me").json()["user"]["id"]
    c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H)
    for _ in range(30):
        db.audit("cad_check", "Test", user_id=uid)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 200    # gleicher Hash: gespeichert
    _up(c, pid, TOP, "top")                                                                  # neuer Hash
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 429
    assert c.post(f"/api/projects/{pid}/suggest", json={}, headers=H).status_code == 429     # zaehlt mit


def test_ki_schaetzung_ersetzt_und_null(proj, monkeypatch):
    from app import ai
    c, pid, t, b = proj
    c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H)                              # Aluminium/silber
    monkeypatch.setattr(ai, "call", lambda *a, **k: ('{"items": [], "material": {"material": "Stahl", "transparent": 9}}', {}))
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    p = c.get(f"/api/projects/{pid}").json()
    assert (p["material"], p["color"], p["transparent"], p["finish"]) == ("Stahl", None, None, None)
    monkeypatch.setattr(ai, "call", lambda *a, **k: ('{"items": []}', {}))
    c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    assert c.get(f"/api/projects/{pid}").json()["material"] == "Stahl"                     # material fehlt -> unveraendert


def test_handeingabe_waehrend_pruefung_bleibt(proj, monkeypatch):
    from app import ai, db
    c, pid, t, b = proj
    orig = ai.call

    def call(*a, **k):
        db.ex("UPDATE projects SET material='Stahl', material_user=1 WHERE id=?", (pid,))
        return orig(*a, **k)
    monkeypatch.setattr(ai, "call", call)
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 200
    p = c.get(f"/api/projects/{pid}").json()
    assert p["material"] == "Stahl" and p["material_user"] == 1


def test_pruefung_laeuft_bereits(proj):
    from app import check
    c, pid, t, b = proj
    with check.lock_for(pid):
        assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 409


@pytest.mark.parametrize("text,stop", [('{"items": [{"kind": "height", "sev', "max_tokens"), ("", "end_turn"),
                                       ("keine Ahnung", "end_turn"), ('{"items": []}', "max_tokens")])
def test_unvollstaendige_antwort_ist_502_und_nichts_gespeichert(proj, monkeypatch, text, stop):
    from app import ai
    c, pid, t, b = proj
    assert c.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 200
    before = c.get(f"/api/projects/{pid}").json()["cad_check"]
    monkeypatch.setattr(ai, "call", lambda s, *a, **k: (text, {"stop_reason": stop}))
    r = c.post(f"/api/projects/{pid}/cad-check", json={"force": True}, headers=H)
    assert r.status_code == 502 and "unvollständig" in r.json()["detail"]
    assert c.get(f"/api/projects/{pid}").json()["cad_check"] == before


def test_fremder_nutzer_stufe_a(proj, app, admin):
    from fastapi.testclient import TestClient
    c, pid, t, b = proj
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremda{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.post(f"/api/projects/{pid}/cad-check", json={}, headers=H).status_code == 404
    assert f.patch(f"/api/projects/{pid}", json={"material": "x"}, headers=H).status_code == 404
    own = f.post("/api/projects", json={"name": "f"}, headers=H).json()["id"]
    r = f.post(f"/api/projects/{own}/cad-check", json={"photo_ids": [t["id"], b["id"]]}, headers=H).json()
    assert r["images"] == [] and r["photo_ids"] == []                                       # fremde Fotos ignoriert


def test_cad_auftrag_max_tokens_32000(proj, monkeypatch):
    import time

    from app import ai
    c, pid, t, b = proj
    real, seen = ai.call, []

    def spy(system, messages, max_tokens=16000, **kw):
        seen.append((system, max_tokens))
        return real(system, messages, max_tokens=max_tokens, **kw)
    monkeypatch.setattr(ai, "call", spy)
    jid = c.post("/api/jobs", json={"project_id": pid, "name": "x", "request": "y"}, headers=H).json()["id"]
    t0 = time.time()
    while c.get(f"/api/jobs/{jid}").json()["status"] in ("queued", "running") and time.time() - t0 < 120:
        time.sleep(0.3)
    assert seen and all(s == ai.CAD_SYSTEM and m == 32000 for s, m in seen), seen
