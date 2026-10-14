"""Kantenerkennung ueber die API (Spec 2026-10-14-kanten-und-teile §2, A3/A4)."""
import json

import pytest

from conftest import H, synthetic_photo

BOX = {"rect": [60, 80, 60, 40], "gray": 150}
PLATE = {"rect": [50, 105, 80, 20], "gray": 90}
HOLE = {"circle": [90, 115, 5], "gray": 235}
KI_ZWEI = json.dumps([
    {"label": "Quader", "role": "body", "polygon": [[60.5, 80.5], [119.5, 80.5], [119.5, 119.8], [60.5, 119.8]], "edges": []},
    {"label": "Platte", "role": "mounted", "polygon": [[50.5, 105.5], [129.5, 105.5], [129.5, 124.5], [50.5, 124.5]],
     "edges": []}])


def _upload(c, objects):
    pid = c.post("/api/projects", json={"name": "Kanten"}, headers=H).json()["id"]
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("k.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": "top"}, headers=H)
    assert r.status_code == 200, r.text
    return pid, r.json()["id"]


@pytest.fixture()
def two(user):
    pid, phid = _upload(user, [BOX, PLATE, HOLE])
    return user, pid, phid


def _ki(monkeypatch, text):
    from app import ai
    monkeypatch.setattr(ai, "call", lambda system, messages, **kw: (text, {}))


def test_erkennung_testmodus(two):
    c, pid, phid = two
    r = c.post(f"/api/photos/{phid}/edges", json={}, headers=H)
    assert r.status_code == 200, r.text
    res = r.json()
    assert [p["label"] for p in res["parts"]] == ["Quader"] and res["notice"] == ""
    assert any(s["kind"] == "inner" for s in res["segments"])
    assert c.get(f"/api/photos/{phid}/edges.json").json()["segments"] == res["segments"]


def test_zwei_teile(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    q, pl = res["parts"]
    assert (q["label"], pl["label"], pl["role"]) == ("Quader", "Platte", "mounted")
    assert q["rect"] and q["size"] == pytest.approx([60, 40], abs=0.6) and len(q["hidden"]) == 1
    assert pl["rect"] and pl["size"] == pytest.approx([80, 20], abs=0.6) and len(pl["holes"]) == 1
    p = c.get(f"/api/projects/{pid}").json()
    assert {m["part_id"] for m in p["measurements"] if m["source"] == "auto"} == {q["id"], pl["id"]}


def test_erneute_erkennung_ohne_ki_laesst_teile(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    first = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()["parts"]
    _ki(monkeypatch, "kein json")
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert [p["id"] for p in res["parts"]] == [p["id"] for p in first] and "unverändert" in res["notice"]
    res = c.post(f"/api/photos/{phid}/edges", json={"use_ai": False}, headers=H).json()
    assert [p["id"] for p in res["parts"]] == [p["id"] for p in first]


def test_ohne_ki_und_handteil_bleibt(two):
    c, pid, phid = two
    hand = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "label": "Hand",
                                                      "polygon": [[5, 150], [30, 150], [30, 170]]}, headers=H).json()
    res = c.post(f"/api/photos/{phid}/edges", json={"use_ai": False}, headers=H).json()
    assert sorted(p["label"] for p in res["parts"]) == ["Hand", "Teil"] and res["notice"] == ""
    assert hand["id"] in [p["id"] for p in res["parts"]]


def test_erkennung_belegt_429(two):
    c, pid, phid = two
    from app import main
    assert main._detect_lock.acquire(blocking=False)
    try:
        r = c.post(f"/api/photos/{phid}/edges", json={}, headers=H)
        assert r.status_code == 429 and "belegt" in r.json()["detail"]
    finally:
        main._detect_lock.release()


def test_fremder_nutzer_keine_erkennung(two, app, admin):
    from fastapi.testclient import TestClient
    c, pid, phid = two
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremdk{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.post(f"/api/photos/{phid}/edges", json={}, headers=H).status_code == 404
    assert f.get(f"/api/photos/{phid}/edges.json").status_code == 404


def test_erneute_erkennung_behaelt_massstab(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    q = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()["parts"][0]
    L = next(m for m in c.get(f"/api/projects/{pid}").json()["measurements"]
             if m["part_id"] == q["id"] and m["data"].get("auto_key") == "L")
    c.patch(f"/api/measurements/{L['id']}", json={"caliper": round(L["value"] * 0.943, 3)}, headers=H)
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    q2 = next(p for p in res["parts"] if p["label"] == "Quader")
    assert q2["id"] == q["id"] and q2["scale"] == pytest.approx(0.943, abs=1e-3)
    labels = [m["label"] for m in c.get(f"/api/projects/{pid}").json()["measurements"] if m["part_id"] == q["id"]]
    assert labels.count("Quader Länge") == 1


def test_ki_unbrauchbar(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, 'Hier: [{"label": "x", "polygon": [[1, 2], [3, "a"]]}, 5, {"polygon": [[0, 0], [1, 1]]}]')
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert [p["label"] for p in res["parts"]] == ["Teil"] and "keine Teile" in res["notice"]
    _ki(monkeypatch, json.dumps([{"label": "riesig", "polygon": [[0, 0], [5000, 0], [0, 5000]]}]))
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert [p["label"] for p in res["parts"]] == ["Teil"] and "keine Teile" in res["notice"]


def test_ki_fehler_beim_ersten_lauf(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, "kein json")
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert "KI-Zuordnung fehlgeschlagen" in res["notice"] and len(res["parts"]) == 1


def test_parse_parts_defensiv():
    from app import ai
    items = ai.parse_parts('```json\n[{"label": "' + "x" * 100 + '", "role": "egal", "polygon": [[0,0],[10,0],[10,10]], '
                           '"edges": ["K1", 3, null]}, {"polygon": [[0,0],[NaN,0],[1,1]]}]\n```')
    assert len(items) == 1 and items[0]["role"] == "body" and len(items[0]["label"]) == 80 and items[0]["edges"] == ["K1", "3"]


def test_leeres_foto_422(user):
    pid, phid = _upload(user, [])
    r = user.post(f"/api/photos/{phid}/edges", json={}, headers=H)
    assert r.status_code == 422 and "Kein Objekt" in r.json()["detail"]


def test_tageslimit_ohne_ki(two):
    c, pid, phid = two
    from app import db
    uid = c.get("/api/me").json()["user"]["id"]
    for _ in range(30):
        db.audit("suggest", "Test", user_id=uid)
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert "Tageslimit" in res["notice"] and [p["label"] for p in res["parts"]] == ["Teil"]
    assert c.post(f"/api/projects/{pid}/suggest", json={}, headers=H).status_code == 429


def test_cad_auftrag_fuer_ein_teil(two, monkeypatch, user):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    q, pl = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()["parts"]
    from app import db, jobs
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    msg = jobs.build_initial_message(project, "Platte nachbauen", {"part_id": pl["id"], "name": "P"})
    text = msg[0]["content"][0]["text"]
    assert "Modelliert wird nur Teil T2 „Platte“ (montiertes Teil)" in text
    assert "| Teil |" in text and "| Messschieber |" in text
    alle = jobs.build_initial_message(project, "alles", {"name": "A"})[0]["content"][0]["text"]
    assert "Teile im Foto: T1 Quader (Grundkörper), T2 Platte (montiertes Teil)" in alle
    _, rows = jobs.measurement_table(pid, pl["id"])
    assert rows and all(m["part_id"] != q["id"] for m in rows)
    other = user.post("/api/projects", json={"name": "x"}, headers=H).json()["id"]
    bad = c.post("/api/jobs", json={"project_id": other, "name": "x", "request": "x", "part_id": pl["id"]}, headers=H)
    assert bad.status_code == 400
    r = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "Platte", "part_id": pl["id"]}, headers=H)
    assert r.status_code == 200, r.text
    t = json.loads(db.q1("SELECT messages FROM jobs WHERE id=?", (r.json()["id"],))["messages"])[0]["content"][0]["text"]
    assert "Modelliert wird nur Teil T2" in t and "| T1 |" not in t
