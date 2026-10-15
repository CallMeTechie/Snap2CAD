"""Teile und Massstab ueber die API (Spec 2026-10-14-kanten-und-teile §3, §7)."""
import sqlite3

import pytest

from conftest import H, synthetic_photo

OLD_MEAS = """CREATE TABLE measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, photo_id INTEGER,
  seq INTEGER NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL, value REAL, unit TEXT NOT NULL DEFAULT 'mm', unc REAL,
  data TEXT, critical INTEGER NOT NULL DEFAULT 0, caliper REAL, fit TEXT, source TEXT NOT NULL DEFAULT 'user',
  accepted INTEGER NOT NULL DEFAULT 1, reason TEXT, created_at TEXT NOT NULL);"""


def test_migration_ergaenzt_part_id(tmp_path, monkeypatch):
    from app import config, db
    path = tmp_path / "alt.db"
    con = sqlite3.connect(path)
    con.executescript(OLD_MEAS)
    con.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db, "_conn", None)
    try:
        cols = {r["name"] for r in db.q("PRAGMA table_info(measurements)")}
        assert "part_id" in cols
        assert db.q("SELECT name FROM sqlite_master WHERE type='table' AND name='parts'")
    finally:
        db._conn.close()


def test_atomic_rollback_und_verschachtelt():
    from app import db
    db.ex("CREATE TABLE IF NOT EXISTS t_atomic (v INTEGER)")
    try:
        with db.atomic():
            db.ex("INSERT INTO t_atomic VALUES (1)")
            with db.atomic():
                db.ex("INSERT INTO t_atomic VALUES (2)")
            raise RuntimeError("abbrechen")
    except RuntimeError:
        pass
    assert db.q("SELECT * FROM t_atomic") == []
    with db.atomic():
        db.ex("INSERT INTO t_atomic VALUES (3)")
    assert db.q("SELECT v FROM t_atomic") == [{"v": 3}]
    db.ex("DROP TABLE t_atomic")

BOX = {"rect": [60, 80, 60, 40], "gray": 150}
RECT = [[60, 80], [123.6, 80], [123.6, 122.4], [60, 122.4]]   # Fotowerte 63,6 × 42,4 (Parallaxe)


@pytest.fixture()
def proj(user):
    pid = user.post("/api/projects", json={"name": "Quader"}, headers=H).json()["id"]
    r = user.post(f"/api/projects/{pid}/photos", files={"file": ("q.jpg", synthetic_photo("A4", objects=[BOX]), "image/jpeg")},
                  data={"view": "top"}, headers=H)
    assert r.status_code == 200, r.text
    return user, pid, r.json()["id"]


def _p(c, pid):
    return c.get(f"/api/projects/{pid}").json()


def _auto(p, part_id, key):
    return next(m for m in p["measurements"] if m["part_id"] == part_id and m["data"].get("auto_key") == key)


def _part(c, pid, phid, poly=RECT, label="Quader"):
    r = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "label": label, "polygon": poly}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_teil_auto_masse_und_massstab(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid)
    assert part["id_label"] == "T1" and part["rect"] and part["size"] == pytest.approx([63.6, 42.4])
    p = _p(c, pid)
    L = _auto(p, part["id"], "L")
    assert L["label"] == "Quader Länge" and L["source"] == "auto"
    assert c.patch(f"/api/measurements/{L['id']}", json={"caliper": 60.0}, headers=H).status_code == 200
    p = _p(c, pid)
    assert _auto(p, part["id"], "B")["value"] == pytest.approx(40.0, abs=0.01)
    assert p["parts"][0]["scale"] == pytest.approx(0.9434, abs=1e-3) and p["parts"][0]["refs"] == [L["id_label"]]
    m = c.post(f"/api/projects/{pid}/measurements",
               json={"photo_id": phid, "kind": "length", "points": [[60, 100], [123.6, 100]]}, headers=H).json()
    assert m["part_id"] == part["id"] and m["value"] == pytest.approx(60.0, abs=0.01) and m["data"]["raw"] == pytest.approx(63.6)
    c.patch(f"/api/measurements/{_auto(p, part['id'], 'B')['id']}", json={"caliper": 40.6}, headers=H)  # 1,5 % Streuung
    assert "widersprechen" in _p(c, pid)["parts"][0]["warn"]
    c.patch(f"/api/parts/{part['id']}", json={"reset_scale": True}, headers=H)
    p = _p(c, pid)
    assert p["parts"][0]["scale"] == 1.0 and _auto(p, part["id"], "B")["value"] == pytest.approx(42.4)


def test_unplausible_referenz_polygon_bearbeiten_dropped(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid, label="Q")
    B = _auto(_p(c, pid), part["id"], "B")
    c.patch(f"/api/measurements/{B['id']}", json={"caliper": 59.36}, headers=H)         # 59,36 / 42,4 = 1,40
    p = _p(c, pid)
    assert p["parts"][0]["scale"] == 1.0 and "Abweichung zu groß" in _auto(p, part["id"], "B")["data"]["ref_warn"]
    r = c.patch(f"/api/parts/{part['id']}", json={"polygon": [RECT[0], [90, 80], *RECT[1:]]}, headers=H)
    assert r.status_code == 200, r.text
    p = _p(c, pid)
    assert sorted(m["data"]["auto_key"] for m in p["measurements"] if m["source"] == "auto") == ["E1", "E2", "E3", "E4", "E5"]
    kept = next(m for m in p["measurements"] if m["id"] == B["id"])
    assert kept["source"] == "user" and kept["caliper"] == 59.36
    e2 = next(m for m in p["measurements"] if m["data"].get("auto_key") == "E2")
    assert c.delete(f"/api/measurements/{e2['id']}", headers=H).status_code == 200
    e1 = next(m for m in p["measurements"] if m["data"].get("auto_key") == "E1")
    r = c.patch(f"/api/measurements/{e1['id']}", json={"points": [[60, 81], [90, 81]]}, headers=H).json()
    assert r["source"] == "user"
    e3 = next(m for m in p["measurements"] if m["data"].get("auto_key") == "E3")
    assert c.patch(f"/api/measurements/{e3['id']}", json={"kind": "height"}, headers=H).json()["source"] == "user"
    c.patch(f"/api/parts/{part['id']}", json={"label": "Quader"}, headers=H)
    p = _p(c, pid)
    keys = [m["data"].get("auto_key") for m in p["measurements"]]
    assert "E1" not in keys and "E2" not in keys and "E3" not in keys
    assert all(m["label"].startswith("Quader ") for m in p["measurements"] if m["source"] == "auto")
    bow = [[60, 80], [123.6, 122.4], [123.6, 80], [60, 122.4]]
    assert c.patch(f"/api/parts/{part['id']}", json={"polygon": bow}, headers=H).status_code == 200
    assert c.get(f"/api/projects/{pid}").status_code == 200



def test_umbenennen_nach_kuerzung(proj):
    """Auto-Masse heissen nach dem Umbenennen richtig, auch wenn der alte Name ihr Label auf 80 Zeichen gekuerzt hat."""
    c, pid, phid = proj
    part = _part(c, pid, phid, label="X" * 80)
    assert _auto(_p(c, pid), part["id"], "L")["label"] == "X" * 80
    for old, new in (("X" * 80, "Y" * 79), ("Y" * 79, "Quader")):
        assert c.patch(f"/api/parts/{part['id']}", json={"label": new}, headers=H).status_code == 200, old
    p = _p(c, pid)
    assert (_auto(p, part["id"], "L")["label"], _auto(p, part["id"], "B")["label"]) == ("Quader Länge", "Quader Breite")


def test_umbenennen_behaelt_eigene_labels(proj):
    """Ergaenzte Auto-Labels bekommen nur den neuen Teilnamen, frei vergebene bleiben unveraendert."""
    c, pid, phid = proj
    part = _part(c, pid, phid)
    p = _p(c, pid)
    c.patch(f"/api/measurements/{_auto(p, part['id'], 'L')['id']}", json={"label": "Quader Länge oben"}, headers=H)
    c.patch(f"/api/measurements/{_auto(p, part['id'], 'B')['id']}", json={"label": "Gesamt"}, headers=H)
    assert c.patch(f"/api/parts/{part['id']}", json={"label": "Platte"}, headers=H).status_code == 200
    p = _p(c, pid)
    assert (_auto(p, part["id"], "L")["label"], _auto(p, part["id"], "B")["label"]) == ("Platte Länge oben", "Gesamt")


def test_zuordnung_von_hand(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid)
    h = c.post(f"/api/projects/{pid}/measurements", json={"kind": "height", "value": 30.0, "label": "Höhe"}, headers=H).json()
    assert h["part_id"] is None
    assert c.patch(f"/api/measurements/{h['id']}", json={"part_id": part["id"]}, headers=H).json()["part_id"] == part["id"]
    m = c.post(f"/api/projects/{pid}/measurements",
               json={"photo_id": phid, "kind": "length", "points": [[60, 100], [123.6, 100]]}, headers=H).json()
    assert c.patch(f"/api/measurements/{m['id']}", json={"part_id": None}, headers=H).json()["part_id"] is None
    assert _p(c, pid)["measurements"][-1]["part_id"] is None                       # bleibt "keins"
    assert c.patch(f"/api/measurements/{m['id']}", json={"part_id": -1}, headers=H).json()["part_id"] == part["id"]
    assert c.patch(f"/api/measurements/{m['id']}", json={"part_id": 999999}, headers=H).status_code == 400
    L = _auto(_p(c, pid), part["id"], "L")
    assert c.patch(f"/api/measurements/{L['id']}", json={"part_id": None}, headers=H).status_code == 400


def test_formatwechsel_und_foto_loeschen_behalten_referenz(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid)
    L = _auto(_p(c, pid), part["id"], "L")
    c.patch(f"/api/measurements/{L['id']}", json={"caliper": 60.0}, headers=H)
    c.patch(f"/api/photos/{phid}", json={"format": "A3"}, headers=H)
    p = _p(c, pid)
    assert p["parts"] == [] and [(m["source"], m["caliper"]) for m in p["measurements"]] == [("user", 60.0)]
    c.patch(f"/api/photos/{phid}", json={"format": "A4"}, headers=H)
    _part(c, pid, phid)
    c.delete(f"/api/photos/{phid}", headers=H)
    p = _p(c, pid)
    assert p["parts"] == [] and [m["caliper"] for m in p["measurements"]] == [60.0]


def test_teil_validierung(proj, user):
    c, pid, phid = proj
    bad = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": [[0, 0], [1, 1]]}, headers=H)
    assert bad.status_code in (400, 422)                                              # Pydantic: min_length=3
    assert c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": [[0, 0], [1e6, 0], [0, 5]]},
                  headers=H).status_code == 400
    other = user.post("/api/projects", json={"name": "fremd"}, headers=H).json()["id"]
    assert c.post(f"/api/projects/{other}/parts", json={"photo_id": phid, "polygon": RECT}, headers=H).status_code == 400
    for _ in range(12):                                                               # MAX_PARTS_PER_PHOTO
        _part(c, pid, phid)
    assert c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": RECT}, headers=H).status_code == 400


def test_fremder_nutzer_kein_zugriff(proj, app, admin):
    from fastapi.testclient import TestClient
    c, pid, phid = proj
    part = _part(c, pid, phid)
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremd{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.patch(f"/api/parts/{part['id']}", json={"label": "x"}, headers=H).status_code == 404
    assert f.delete(f"/api/parts/{part['id']}", headers=H).status_code == 404
    assert f.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": RECT}, headers=H).status_code == 404
    own = f.post("/api/projects", json={"name": "f"}, headers=H).json()["id"]
    m = f.post(f"/api/projects/{own}/measurements", json={"kind": "height", "value": 1.0}, headers=H).json()
    assert f.patch(f"/api/measurements/{m['id']}", json={"part_id": part["id"]}, headers=H).status_code == 400


def test_parallel_keine_doppelten_auto_masse(proj):
    import threading
    from app import db, main, parts
    c, pid, phid = proj
    part = _part(c, pid, phid)
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    five = [RECT[0], [90, 80], *RECT[1:]]
    errs = []

    def job(i):
        try:
            if i == 0:
                assert c.patch(f"/api/parts/{part['id']}", json={"polygon": five}, headers=H).status_code == 200
            else:
                main._refresh(project)
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=job, args=(i,)) for i in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs
    parts.refresh(project, 1.0, 1.0)
    keys = [m["data"].get("auto_key") for m in _p(c, pid)["measurements"] if m["source"] == "auto"]
    assert len(keys) == len(set(keys)) == 5


def test_patch_auf_parallel_geloeschte_messung(proj, monkeypatch):
    """Final-Review #2: meas_patch liest die Zeile in der Transaktion neu; ist sie weg, 404 statt 500."""
    from app import db, main
    c, pid, phid = proj
    m = c.post(f"/api/projects/{pid}/measurements", json={"kind": "height", "value": 5.0}, headers=H).json()
    orig = main._own_meas

    def own_then_gone(mid, u):
        res = orig(mid, u)
        db.ex("DELETE FROM measurements WHERE id=?", (mid,))  # paralleler Loeschvorgang zwischen Pruefung und Schreiben
        return res
    monkeypatch.setattr(main, "_own_meas", own_then_gone)
    r = c.patch(f"/api/measurements/{m['id']}", json={"label": "neu"}, headers=H)
    assert r.status_code == 404
