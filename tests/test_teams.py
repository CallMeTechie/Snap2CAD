"""Teams mit gemeinsamen Bibliotheken (Spec 2026-10-16, T1–T8)."""
import itertools
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import H

FIXTURE = Path(__file__).parent / "fixtures" / "schema_c408b93.sql"
TS = datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ T1: Migration

def _legacy_db(path):
    """Bestandsdatenbank im Stand c408b93: Projekte, Fotos, Teile, Messungen, Auftraege, Versionen, Protokoll, Werte,
    ein geloeschtes letztes Projekt und ein geloeschter letzter Auftrag (sqlite_sequence > MAX(id)), eine leere frueher
    benutzte AUTOINCREMENT-Tabelle (resets) und ein Altverstoss (Foto 2 verweist auf das fehlende Projekt 999)."""
    c = sqlite3.connect(str(path))
    c.executescript(FIXTURE.read_text(encoding="utf-8"))
    c.executescript(f"""
INSERT INTO users(id,username,pw_hash,role,created_at) VALUES (1,'alice','x','admin','{TS}'), (2,'bob','x','user','{TS}');
INSERT INTO projects(id,user_id,name,created_at,ctrl_x,material_user) VALUES
  (1,1,'Platte','{TS}',100.2,0), (2,2,'Winkel','{TS}',NULL,1), (3,2,'weg','{TS}',NULL,0);
DELETE FROM projects WHERE id=3;
INSERT INTO photos(id,project_id,filename,view,format,status,analysis,created_at) VALUES
  (1,1,'a.jpg','top','A4','gut','{{"rect": {{"w_mm": 190}}}}','{TS}'), (2,999,'alt.jpg','top',NULL,NULL,NULL,'{TS}');
INSERT INTO parts(id,project_id,photo_id,seq,label,data,created_at) VALUES
  (1,1,1,1,'Platte','{{"polygon": [[0, 0], [1, 0], [1, 1]]}}','{TS}');
INSERT INTO measurements(id,project_id,photo_id,part_id,seq,label,kind,value,data,created_at) VALUES
  (1,1,1,1,1,'Länge','length',80.0,'{{}}','{TS}');
INSERT INTO jobs(id,user_id,project_id,name,request,status,messages,current_version,created_at,updated_at) VALUES
  (1,1,1,'J1','{{}}','done','[]',1,'{TS}','{TS}'), (2,2,NULL,'J2','{{}}','failed','[]',NULL,'{TS}','{TS}'),
  (3,2,2,'weg','{{}}','done','[]',NULL,'{TS}','{TS}');
DELETE FROM jobs WHERE id=3;
INSERT INTO job_versions(id,job_id,version,trigger,status,created_at) VALUES
  (1,1,1,'create','ok','{TS}'), (2,1,2,'iterate','failed','{TS}'), (3,2,1,'create','failed','{TS}');
INSERT INTO job_log(id,job_id,ts,msg) VALUES (1,1,'{TS}','Auftrag angelegt');
INSERT INTO model_dims(id,project_id,label,label_norm,grp,value,job_id,dim_id,created_at) VALUES
  (1,1,'Höhe','höhe','aussen',45.0,1,'D2','{TS}');
INSERT INTO resets(id,token_hash,user_id,created_at,expires_at) VALUES (1,'h',2,'{TS}','{TS}');
DELETE FROM resets;
""")
    c.commit()
    c.close()


def _plain(path):
    return sqlite3.connect(str(path))


def _dump(path):
    c = _plain(path)
    try:
        return list(c.iterdump())
    finally:
        c.close()


def _tables(c):
    return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                    "ORDER BY name")]


def _snapshot(path):
    c = _plain(path)
    try:
        out = {"rows": {}, "fks": {}}
        for t in _tables(c):
            cols = [r[1] for r in c.execute(f'PRAGMA table_info("{t}")')]
            out["rows"][t] = (cols, [tuple(r) for r in c.execute(f'SELECT * FROM "{t}" ORDER BY rowid')])
            out["fks"][t] = [tuple(r) for r in c.execute(f'PRAGMA foreign_key_list("{t}")')]
        out["seq"] = sorted(tuple(r) for r in c.execute("SELECT name, seq FROM sqlite_sequence"))
        out["fk"] = Counter(tuple(r[:3]) for r in c.execute("PRAGMA foreign_key_check"))
        return out
    finally:
        c.close()


def _old_rows(path, table, cols):
    c = _plain(path)
    try:
        return [tuple(r) for r in c.execute(f'SELECT {", ".join(cols)} FROM "{table}" ORDER BY rowid')]
    finally:
        c.close()


def test_migration_bestand_unveraendert(tmp_path):
    from app import db
    p = tmp_path / "bestand.db"
    _legacy_db(p)
    vor = _snapshot(p)
    assert vor["fk"] == Counter({("photos", 2, "projects"): 1})                 # Altverstoss wird geduldet (F-2)
    assert dict(vor["seq"]) == {"users": 2, "projects": 3, "photos": 2, "parts": 1, "measurements": 1, "jobs": 3,
                                "job_versions": 3, "job_log": 1, "model_dims": 1, "resets": 1}
    c = db._open(p)
    try:
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        c.close()
    nach = _snapshot(p)
    for t, (cols, rows) in vor["rows"].items():                                # alle Zeilen unveraendert
        assert _old_rows(p, t, cols) == rows, t
    for t in vor["fks"]:                                                      # Fremdschluessel der uebrigen Tabellen
        if t not in ("projects", "jobs", "job_versions"):
            assert nach["fks"][t] == vor["fks"][t], t
    assert {(r[3], r[2], r[6]) for r in nach["fks"]["job_versions"]} == \
        {("job_id", "jobs", "CASCADE"), ("user_id", "users", "SET NULL")}
    assert nach["seq"] == vor["seq"]
    assert not (nach["fk"] - vor["fk"]) and sum(nach["fk"].values()) <= sum(vor["fk"].values())
    q = _plain(p)
    try:
        assert q.execute("SELECT COUNT(*) FROM projects WHERE team_id IS NOT NULL").fetchone()[0] == 0   # alle privat
        assert q.execute("SELECT COUNT(*) FROM jobs WHERE run_by IS NOT NULL").fetchone()[0] == 0
        assert q.execute("SELECT v.id, v.user_id, j.user_id FROM job_versions v JOIN jobs j ON j.id=v.job_id "
                         "ORDER BY v.id").fetchall() == [(1, 1, 1), (2, 1, 1), (3, 2, 2)]
        idx = {r[0] for r in q.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"ix_projects_team", "ix_projects_user", "ix_jobs_user", "ix_jobs_project", "ux_team_invite_open",
                "ix_team_members_user", "ix_meas_part"} <= idx
        assert {(r[3], r[2], r[6]) for r in q.execute("PRAGMA foreign_key_list(projects)")} == \
            {("user_id", "users", "SET NULL"), ("team_id", "teams", "NO ACTION")}
        assert {(r[3], r[2], r[6]) for r in q.execute("PRAGMA foreign_key_list(jobs)")} == \
            {("user_id", "users", "SET NULL"), ("project_id", "projects", "SET NULL"), ("run_by", "users", "SET NULL")}
        notnull = {(t, r[1]): r[3] for t in ("projects", "jobs") for r in q.execute(f"PRAGMA table_info({t})")}
        assert notnull[("projects", "user_id")] == 0 and notnull[("jobs", "user_id")] == 0
    finally:
        q.close()
    erst = _dump(p)
    db._open(p).close()                                                        # zweiter Start aendert nichts
    assert _dump(p) == erst


def test_migration_neue_datenbank(tmp_path):
    from app import db
    c = db._open(tmp_path / "neu.db")
    try:
        idx = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"ix_projects_team", "ix_projects_user", "ux_team_invite_open", "ix_team_members_user"} <= idx
        cols = {t: {r[1] for r in c.execute(f"PRAGMA table_info({t})")} for t in ("projects", "jobs", "job_versions")}
        assert "team_id" in cols["projects"] and "run_by" in cols["jobs"] and "user_id" in cols["job_versions"]
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        c.close()
    assert db.PROJECTS_DDL in db.SCHEMA and db.JOBS_DDL in db.SCHEMA            # dieselbe DDL-Konstante
    assert all(sqlite3.complete_statement(s + ";") for s in db._statements(db.SCHEMA))   # Umbau zerlegt sauber


def test_migration_sequenz_leere_tabellen(tmp_path):
    """jobs frueher benutzt und leer (Stand 5 bleibt), projects nie benutzt (kein Eintrag entsteht)."""
    from app import db
    p = tmp_path / "leer.db"
    c = _plain(p)
    c.executescript(FIXTURE.read_text(encoding="utf-8"))
    c.execute("INSERT INTO users(id,username,pw_hash,created_at) VALUES (1,'carla','x',?)", (TS,))
    for i in range(1, 6):
        c.execute("INSERT INTO jobs(id,user_id,name,request,status,created_at,updated_at) VALUES (?,1,'j','{}','done',?,?)",
                  (i, TS, TS))
    c.execute("DELETE FROM jobs")
    c.commit()
    c.close()
    assert dict(_snapshot(p)["seq"]) == {"users": 1, "jobs": 5}
    m = db._open(p)
    try:
        assert dict(m.execute("SELECT name, seq FROM sqlite_sequence").fetchall()) == {"users": 1, "jobs": 5}
        jid = m.execute("INSERT INTO jobs(user_id,name,request,status,created_at,updated_at) VALUES (1,'n','{}','done',?,?)",
                        (TS, TS)).lastrowid
        pid = m.execute("INSERT INTO projects(user_id,name,created_at) VALUES (1,'n',?)", (TS,)).lastrowid
        assert (jid, pid) == (6, 1)
    finally:
        m.close()


class _BoomRename(sqlite3.Connection):
    """Wirft beim RENAME von jobs_new – nach DROP TABLE jobs (T1: erzwungener Fehler)."""

    def execute(self, sql, *args):
        if sql.startswith("ALTER TABLE jobs_new RENAME"):
            raise sqlite3.OperationalError("Testfehler beim Umbenennen")
        return super().execute(sql, *args)


class _BoomViolation(sqlite3.Connection):
    """Legt vor dem Index ix_jobs_project einen neuen Fremdschluessel-Verstoss an."""

    def execute(self, sql, *args):
        if sql.startswith("CREATE INDEX IF NOT EXISTS ix_jobs_project"):
            super().execute("INSERT INTO photos(project_id,filename,view,created_at) VALUES (4242,'neu.jpg','top','x')")
        return super().execute(sql, *args)


@pytest.mark.parametrize("factory", [_BoomRename, _BoomViolation], ids=["rename", "neuer_verstoss"])
def test_migration_abbruch_rollt_zurueck(tmp_path, factory):
    from app import db
    p = tmp_path / "abbruch.db"
    _legacy_db(p)
    vor = _dump(p)
    with pytest.raises(RuntimeError, match="Migration abgebrochen"):
        db._open(p, factory=factory)
    assert _dump(p) == vor                                                      # vollstaendig zurueckgerollt
    c = db._open(p)                                                             # folgender normaler Start migriert
    try:
        assert "team_id" in {r[1] for r in c.execute("PRAGMA table_info(projects)")}
    finally:
        c.close()


def test_migration_verwaister_ersteller(tmp_path):
    """Auftrag 2 verweist auf den fehlenden Benutzer 77 (Altverstoss, F-2): seine Versionen bleiben ohne user_id."""
    from app import db
    p = tmp_path / "verwaist.db"
    c = _plain(p)                                                               # foreign_keys ist hier aus
    c.executescript(FIXTURE.read_text(encoding="utf-8"))
    c.executescript(f"""
INSERT INTO users(id,username,pw_hash,created_at) VALUES (1,'dora','x','{TS}');
INSERT INTO jobs(id,user_id,name,request,status,created_at,updated_at) VALUES
  (1,1,'J1','{{}}','done','{TS}','{TS}'), (2,77,'J2','{{}}','done','{TS}','{TS}');
INSERT INTO job_versions(id,job_id,version,trigger,status,created_at) VALUES
  (1,1,1,'create','ok','{TS}'), (2,2,1,'create','ok','{TS}'), (3,2,2,'iterate','ok','{TS}');
""")
    c.commit()
    c.close()
    vor = _snapshot(p)["fk"]
    assert vor == Counter({("jobs", 2, "users"): 1})
    db._open(p).close()
    nach = _snapshot(p)["fk"]
    assert not (nach - vor) and sum(nach.values()) <= sum(vor.values())
    q = _plain(p)
    try:
        assert q.execute("SELECT id, user_id FROM job_versions ORDER BY id").fetchall() == [(1, 1), (2, None), (3, None)]
        assert "team_id" in {r[1] for r in q.execute("PRAGMA table_info(projects)")}
    finally:
        q.close()


class _BoomCleanup(sqlite3.Connection):
    """Wie _BoomRename; danach scheitern auch ROLLBACK und das Wiedereinschalten der Fremdschluessel."""

    boom = False

    def execute(self, sql, *args):
        if sql.startswith("ALTER TABLE jobs_new RENAME"):
            self.boom = True
            raise sqlite3.OperationalError("Testfehler beim Umbenennen")
        if self.boom and sql in ("ROLLBACK", "PRAGMA foreign_keys=ON"):
            raise sqlite3.OperationalError(f"Testfehler bei {sql}")
        return super().execute(sql, *args)


def test_migration_abbruch_behaelt_ursache(tmp_path):
    from app import db
    p = tmp_path / "ursache.db"
    _legacy_db(p)
    vor = _dump(p)
    with pytest.raises(RuntimeError, match="Migration abgebrochen: Testfehler beim Umbenennen"):
        db._open(p, factory=_BoomCleanup)
    assert _dump(p) == vor                                                      # Schliessen verwirft die Transaktion


# ------------------------------------------------------------------ Hilfen

_seq = itertools.count(1)
POLY = [[0, 0], [10, 0], [10, 10]]
CODE = "BLOCK_L = 40.0\npart = Box(BLOCK_L, BLOCK_L, 10)\n"
META = {"dimensions": [{"id": "D1", "label": "Länge", "group": "aussen", "var": "BLOCK_L", "value": 40.0,
                        "assumed": False, "editable": True}]}


def _client(app, admin, name):
    """Neuer Benutzer per Einladung, angemeldet; .username, .uid und .display (Anzeigename) gesetzt."""
    from fastapi.testclient import TestClient

    from app import db
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    c = TestClient(app)
    username = f"tm{next(_seq)}{name}"[:32]
    r = c.post(f"/api/invite/{tok}", json={"username": username, "display_name": name.title(),
                                           "password": "Schieblehre-Messing-7"}, headers=H)
    assert r.status_code == 200, r.text
    c.username, c.display = username, name.title()
    c.uid = db.q1("SELECT id FROM users WHERE username=?", (username,))["id"]
    return c


def _mk(app, admin, *names):
    return [_client(app, admin, n) for n in names]


def _team(name, members):
    """Team direkt in der Datenbank; members = {uid: rolle} in Beitrittsreihenfolge (joined_at aufsteigend)."""
    from app import db
    tid = db.ex("INSERT INTO teams(name,created_by,created_at) VALUES (?,?,?)", (name, next(iter(members)), db.now()))
    for i, (uid, role) in enumerate(members.items()):
        db.ex("INSERT INTO team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?)",
              (tid, uid, role, f"2026-10-16T10:{i // 60:02d}:{i % 60:02d}+00:00"))
    return tid


def _project(uid, team_id=None, name="P"):
    from app import db
    return db.ex("INSERT INTO projects(user_id,team_id,name,created_at) VALUES (?,?,?,?)", (uid, team_id, name, db.now()))


def _photo(pid):
    """Foto ohne Entzerrung, mit thumb.jpg und edges.json im Ordner."""
    from app import config, db
    phid = db.ex("INSERT INTO photos(project_id,filename,view,status,created_at) VALUES (?,?,?,?,?)",
                 (pid, "f.jpg", "top", "gut", db.now()))
    d = config.DATA_DIR / "photos" / str(phid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "thumb.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (d / "edges.json").write_text('{"segments": []}', encoding="utf-8")
    return phid


def _meas(pid, photo_id=None):
    from app import db
    seq = db.q1("SELECT COALESCE(MAX(seq),0)+1 s FROM measurements WHERE project_id=?", (pid,))["s"]
    return db.ex("INSERT INTO measurements(project_id,photo_id,seq,label,kind,value,unit,data,source,created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)", (pid, photo_id, seq, "M", "length", 5.0, "mm", "{}", "manual", db.now()))


def _job(uid, pid, version_status="ok", stl=False):
    """Auftrag mit Version 1 (Trigger create, Ausloeser = Ersteller) direkt in der Datenbank; model.py im Versionsordner."""
    from app import config, db
    jid = db.ex("INSERT INTO jobs(user_id,project_id,name,request,status,messages,current_version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (uid, pid, "Teil", "{}", "done", "[]", 1, db.now(), db.now()))
    db.ex("INSERT INTO job_versions(job_id,version,trigger,request_text,code,claude_text,meta,status,result,checks,usage,"
          "created_at,user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (jid, 1, "create", "", CODE, "", db.jdump(META), version_status, "{}", "[]", "{}", db.now(), uid))
    d = config.DATA_DIR / "jobs" / str(jid) / "v1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.py").write_text(CODE, encoding="utf-8")
    if stl:
        from test_library import _cube_tris, _write_bin
        _write_bin(d / "model.stl", _cube_tris())
    return jid


@pytest.fixture(scope="module")
def welt(app, admin):
    """L, M, R im Team tid (Leiter, Mitglied, Lesend); F aussen und Leiter von t2; X, Y fuer Team-Routen; A = Admin."""
    from app import db
    L, M, R, F, X, Y = _mk(app, admin, "leiter", "mitglied", "lesend", "aussen", "extra", "gast")
    admin.uid = db.q1("SELECT id FROM users WHERE username='admin'")["id"]
    w = SimpleNamespace(L=L, M=M, R=R, F=F, X=X, Y=Y, A=admin)
    w.tid = _team("Rechte", {L.uid: "leiter", M.uid: "mitglied", R.uid: "lesend"})
    w.t2 = _team("Eigenes", {F.uid: "leiter"})
    return w


# ------------------------------------------------------------------ T2: Rechte

# Jede Route unter diesen Praefixen hat genau einen Eintrag in RIGHTS (Spec §10 T2)
PREFIXES = ("/api/projects", "/api/photos", "/api/measurements", "/api/parts", "/api/jobs", "/api/teams",
            "/api/team-invites")
# Route -> (need, Body, Status mit Recht, Teiltext der Antwort mit Recht). Body: dict, Funktion(o) oder "UPLOAD".
# Status mit Recht ist 200, wo die Route mit wenig Aufbau gelingt; sonst ein Fehler nach der Rechtepruefung (400/404/422).
MATRIX = {
    ("GET", "/api/projects/{pid}"): ("read", None, 200, None),
    ("PATCH", "/api/projects/{pid}"): ("write", {"name": "neu"}, 200, None),
    ("DELETE", "/api/projects/{pid}"): ("delete", None, 200, None),
    ("DELETE", "/api/projects/{pid}/model-dims/{mid}"): ("write", None, 200, None),
    ("POST", "/api/projects/{pid}/photos"): ("write", "UPLOAD", 400, "Bild konnte nicht gelesen werden"),
    ("POST", "/api/projects/{pid}/measurements"): ("write", {"kind": "length", "value": 5, "label": "x"}, 200, None),
    ("POST", "/api/projects/{pid}/measurements/accept-all"): ("write", None, 200, None),
    ("POST", "/api/projects/{pid}/measurements/discard-suggestions"): ("write", None, 200, None),
    ("POST", "/api/projects/{pid}/parts"): ("write", lambda o: {"photo_id": o["phid"], "polygon": POLY}, 400,
                                            "keine entzerrte Draufsicht"),
    ("POST", "/api/projects/{pid}/cad-check"): ("write", {"part_id": 999999}, 400, "Teil gehört nicht"),
    ("POST", "/api/projects/{pid}/suggest"): ("write", {}, 400, "Kein auswertbares Foto"),
    ("GET", "/api/projects/{pid}/measurements.csv"): ("read", None, 200, None),
    ("PATCH", "/api/photos/{phid}"): ("write", {}, 200, None),
    ("DELETE", "/api/photos/{phid}"): ("write", None, 200, None),
    ("GET", "/api/photos/{phid}/align.jpg"): ("read", None, 404, "Keine Ausrichtung"),
    ("GET", "/api/photos/{phid}/{kind}.jpg"): ("read", None, 200, None),
    ("POST", "/api/photos/{phid}/edges"): ("write", {"use_ai": False}, 400, "keine entzerrte Draufsicht"),
    ("GET", "/api/photos/{phid}/edges.json"): ("read", None, 200, None),
    ("PATCH", "/api/measurements/{mid}"): ("write", {"label": "y"}, 200, None),
    ("DELETE", "/api/measurements/{mid}"): ("write", None, 200, None),
    ("PATCH", "/api/parts/{part_id}"): ("write", {"polygon": [[0, 0], [1, 0], [1, 1]]}, 400, "keine entzerrte Draufsicht"),
    ("DELETE", "/api/parts/{part_id}"): ("write", None, 200, None),
    ("POST", "/api/jobs"): ("write", lambda o: {"project_id": o["pid"], "request": "x", "part_id": 999999}, 400,
                            "Teil gehört nicht"),
    ("GET", "/api/jobs/{jid}"): ("read", None, 200, None),
    ("POST", "/api/jobs/{jid}/iterate"): ("write", {"text": " "}, 400, "Änderungswunsch"),
    ("POST", "/api/jobs/{jid}/param"): ("write", {"values": [{"id": "D1", "value": 0.0}]}, 422, "größer als 0"),
    ("POST", "/api/jobs/{jid}/cancel"): ("write", None, 200, None),
    ("DELETE", "/api/jobs/{jid}"): ("job_delete", None, 200, None),
    ("GET", "/api/jobs/{jid}/v/{ver}/preview.png"): ("read", None, 404, "Kein Modellbild"),
    ("GET", "/api/jobs/{jid}/v/{ver}/{name}"): ("read", None, 200, None),
}
# Routen ohne einzelnes Projekt: eigene Tests (Bereiche, Anlegen, current, Auftragslisten)
OTHER = {
    ("GET", "/api/projects"): "liste",
    ("POST", "/api/projects"): "anlegen",
    ("GET", "/api/projects/current"): "privat",
    ("GET", "/api/jobs"): "liste",
}
RIGHTS = {**{k: v[0] for k, v in MATRIX.items()}, **OTHER}
# Fall -> (Akteur, Ersteller des Projekts und Auftrags, Team-Projekt?)
CASES = {
    "besitzer": ("F", "F", False), "admin": ("A", "F", False), "leiter": ("L", "M", True),
    "mitglied_selbst": ("M", "M", True), "mitglied_fremd": ("M", "L", True), "lesend": ("R", "L", True),
    "aussen": ("F", "L", True), "admin_team": ("A", "L", True),
}
EXPECT = {   # need -> Faelle mit Recht (Spec §2); ohne Lesen 404, sonst 403
    "read": {"besitzer", "admin", "leiter", "mitglied_selbst", "mitglied_fremd", "lesend"},
    "write": {"besitzer", "admin", "leiter", "mitglied_selbst", "mitglied_fremd"},
    "delete": {"besitzer", "admin", "leiter", "mitglied_selbst"},
    "move": {"besitzer", "leiter", "mitglied_selbst"},
    "copy": {"besitzer", "leiter", "mitglied_selbst", "mitglied_fremd"},
    "job_delete": {"besitzer", "admin", "leiter", "mitglied_selbst"},
}
NO_READ = {"aussen", "admin_team"}


def _call(w, key, case):
    """Frisches Projekt (und Foto, Teil, Mass, Wert, Auftrag nach Bedarf) fuer den Fall anlegen und die Route aufrufen."""
    from app import db, parts
    _, body, _, _ = MATRIX[key]
    actor, creator, in_team = CASES[case]
    cu = getattr(w, creator).uid
    pid = _project(cu, w.tid if in_team else None)
    o = {"pid": pid, "target": None if in_team else w.t2, "kind": "thumb", "ver": 1, "name": "model.py"}
    method, path = key
    if "{phid}" in path or "{part_id}" in path or path == "/api/projects/{pid}/parts":
        o["phid"] = _photo(pid)
    if "{part_id}" in path:
        o["part_id"] = parts.create_part(pid, o["phid"], "T", "body", POLY)
    if path.startswith("/api/measurements/"):
        o["mid"] = _meas(pid)
    if "/model-dims/" in path:
        o["mid"] = db.ex("INSERT INTO model_dims(project_id,label,label_norm,grp,value,created_at) VALUES (?,?,?,?,?,?)",
                         (pid, "Höhe", "höhe", "aussen", 45.0, db.now()))
    if "{jid}" in path:
        o["jid"] = _job(cu, pid)
    kw = {"headers": H}
    if body == "UPLOAD":
        kw["files"] = {"file": ("x.jpg", b"kein bild", "image/jpeg")}
    elif callable(body):
        kw["json"] = body(o)
    elif body is not None:
        kw["json"] = body
    return getattr(w, actor).request(method, path.format(**o), **kw)


def _routes(app):
    """(Methode, Pfad) aller Routen, auch aus include_router (FastAPI 0.143 fasst sie als _IncludedRouter zusammen)."""
    out, todo = set(), [("", r) for r in app.routes]
    while todo:
        pre, r = todo.pop()
        sub = getattr(r, "original_router", None)
        if sub is not None:
            p = pre + (getattr(getattr(r, "include_context", None), "prefix", "") or "")
            todo += [(p, x) for x in sub.routes]
        elif getattr(r, "methods", None) and hasattr(r, "path"):
            out |= {(m, pre + r.path) for m in r.methods if m != "HEAD"}
    return out


def test_rechte_vollstaendig(app):
    """Jede Route unter PREFIXES hat genau einen Eintrag; eine neue Route ohne Eintrag laesst den Test fehlschlagen."""
    have = {(m, path) for m, path in _routes(app) if path.startswith(PREFIXES)}
    assert have == set(RIGHTS), (sorted(have - set(RIGHTS)), sorted(set(RIGHTS) - have))


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("key", list(MATRIX), ids=lambda k: f"{k[0]} {k[1]}")
def test_rechte_matrix(welt, key, case):
    from app import access
    need, _, ok, ok_text = MATRIX[key]
    r = _call(welt, key, case)
    if case in EXPECT[need]:
        assert r.status_code == ok, r.text
        if ok_text:
            assert ok_text in r.text, r.text
    elif case in NO_READ:
        assert r.status_code == 404 and "nicht gefunden" in r.json()["detail"], r.text
    else:
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == (access.DENY_WRITE if case == "lesend" else access.DENY_OWNER)


def test_rechte_admin_als_mitglied(welt):
    """Ist der Admin Mitglied, gilt seine Team-Rolle; "admin" nur fuer private Projekte anderer."""
    from app import access, db
    w = welt
    pid = _project(w.L.uid, w.tid)
    assert w.A.get(f"/api/projects/{pid}").status_code == 404
    db.ex("INSERT INTO team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?)", (w.tid, w.A.uid, "lesend", db.now()))
    try:
        assert w.A.get(f"/api/projects/{pid}").status_code == 200
        r = w.A.patch(f"/api/projects/{pid}", json={"name": "x"}, headers=H)
        assert r.status_code == 403 and r.json()["detail"] == access.DENY_WRITE
        me = db.q1("SELECT * FROM users WHERE id=?", (w.A.uid,))
        assert access.project_role(me, db.q1("SELECT * FROM projects WHERE id=?", (pid,))) == "lesend"
        assert access.project_role(me, {"team_id": None, "user_id": w.F.uid}) == "admin"
    finally:
        db.ex("DELETE FROM team_members WHERE team_id=? AND user_id=?", (w.tid, w.A.uid))


def test_rechte_auftrag_ohne_projekt(welt):
    """Auftraege ohne Projekt gehoeren nur dem Ersteller und dem Admin."""
    w = welt
    jid = _job(w.M.uid, None)
    assert w.M.get(f"/api/jobs/{jid}").status_code == 200
    assert w.A.get(f"/api/jobs/{jid}").status_code == 200
    assert w.L.get(f"/api/jobs/{jid}").status_code == 404
    assert w.L.delete(f"/api/jobs/{jid}", headers=H).status_code == 404
    assert w.A.delete(f"/api/jobs/{jid}", headers=H).status_code == 200
