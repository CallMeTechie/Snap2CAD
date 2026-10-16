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
    ("POST", "/api/projects/{pid}/move"): ("move", lambda o: {"team_id": o["target"]}, 200, None),
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


# ------------------------------------------------------------------ T6: Kontingent und Grenzen beim Ausloeser

def test_kontingent_beim_ausloeser(app, admin, monkeypatch):
    from app import auth, db, jobs
    L, M = _mk(app, admin, "kleiter", "kmitglied")
    tid = _team("Kontingent", {L.uid: "leiter", M.uid: "mitglied"})
    jid = _job(L.uid, _project(L.uid, tid))
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)      # kein Lauf; die Version legt sonst _run per _new_version an
    before = auth.usage_this_month(L.uid), auth.usage_this_month(M.uid)
    r = M.post(f"/api/jobs/{jid}/iterate", json={"text": "Dicke 8 mm"}, headers=H)
    assert r.status_code == 200, r.text
    assert db.q1("SELECT run_by, status FROM jobs WHERE id=?", (jid,)) == {"run_by": M.uid, "status": "queued"}
    v = jobs._new_version(jid, "iterate", "Dicke 8 mm", "", {})
    assert db.q1("SELECT user_id FROM job_versions WHERE job_id=? AND version=?", (jid, v))["user_id"] == M.uid
    assert (auth.usage_this_month(L.uid), auth.usage_this_month(M.uid)) == (before[0], before[1] + 1)
    v2 = jobs._new_version(jid, "autofix", "", "", {})                  # Autofix-Version desselben Laufs
    assert db.q1("SELECT user_id FROM job_versions WHERE job_id=? AND version=?", (jid, v2))["user_id"] == M.uid
    v3 = jobs._new_version(jid, "autofix", "", "", {}, by=L.uid)        # ausdruecklicher Ausloeser geht vor
    assert db.q1("SELECT user_id FROM job_versions WHERE job_id=? AND version=?", (jid, v3))["user_id"] == L.uid
    db.ex("UPDATE jobs SET status='done' WHERE id=?", (jid,))


def test_kontingent_altversionen_beim_ersteller(tmp_path):
    """Nach der Migration zaehlen die Altversionen beim Ersteller (job_versions.user_id = jobs.user_id)."""
    from app import auth, db
    p = tmp_path / "alt.db"
    _legacy_db(p)
    db._open(p).close()
    c = _plain(p)
    try:
        n = {uid: c.execute(auth.USAGE_SQL, (uid, TS[:7])).fetchone()[0] for uid in (1, 2)}
    finally:
        c.close()
    assert n == {1: 2, 2: 1}          # alice: create + iterate an Auftrag 1, bob: create an Auftrag 2


def test_kontingent_laufende_beim_ausloeser(app, admin, monkeypatch):
    """Mitglied laesst drei Auftraege des Leiters aendern: der Leiter kann trotzdem neu anlegen, das Mitglied nicht."""
    from app import db, jobs
    L, M = _mk(app, admin, "klauf", "klaufm")
    tid = _team("Laufend", {L.uid: "leiter", M.uid: "mitglied"})
    db.ex("UPDATE users SET cad_quota=-1 WHERE id IN (?,?)", (L.uid, M.uid))
    pid = _project(L.uid, tid)
    jids = [_job(L.uid, pid) for _ in range(3)]
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    try:
        for j in jids:
            assert M.post(f"/api/jobs/{j}/iterate", json={"text": "anders"}, headers=H).status_code == 200
        r = L.post("/api/jobs", json={"project_id": pid, "name": "neu", "request": "Platte"}, headers=H)
        assert r.status_code == 200, r.text
        jids.append(r.json()["id"])
        r = M.post("/api/jobs", json={"project_id": pid, "name": "vier", "request": "Platte"}, headers=H)
        assert r.status_code == 429 and r.json()["detail"] == "Es laufen bereits drei Aufträge. Bitte warten."
    finally:
        db.ex(f"UPDATE jobs SET status='failed' WHERE id IN ({','.join('?' * len(jids))})", tuple(jids))


def test_kontingent_geloeschter_ausloeser(app, admin, monkeypatch):
    """Wird ein Mitglied geloescht, das am Auftrag des Leiters Versionen ausgeloest hat, bleibt die Zaehlung des Leiters."""
    from app import auth, db, jobs
    L, M = _mk(app, admin, "kgel", "kgelm")
    tid = _team("Weg", {L.uid: "leiter", M.uid: "mitglied"})
    jid = _job(L.uid, _project(L.uid, tid))
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    before_l = auth.usage_this_month(L.uid)                    # vor dem Aendern durch M (die Version aus _job zaehlt)
    assert M.post(f"/api/jobs/{jid}/iterate", json={"text": "x 7 mm"}, headers=H).status_code == 200
    jobs._new_version(jid, "iterate", "x 7 mm", "", {})
    db.ex("UPDATE jobs SET status='done' WHERE id=?", (jid,))
    assert auth.usage_this_month(L.uid) == before_l            # M's Version zaehlt nicht beim Leiter
    assert admin.delete(f"/api/admin/users/{M.uid}", headers=H).status_code == 200
    assert auth.usage_this_month(L.uid) == before_l
    assert db.q1("SELECT COUNT(*) n FROM job_versions WHERE job_id=? AND user_id IS NULL", (jid,))["n"] == 1
    assert db.q1("SELECT run_by FROM jobs WHERE id=?", (jid,))["run_by"] is None


def test_kontingent_param_grenzen_beim_ausloeser(app, admin, monkeypatch):
    from app import config, db, jobs
    L, M = _mk(app, admin, "kpar", "kparm")
    tid = _team("Param", {L.uid: "leiter", M.uid: "mitglied"})
    pid = _project(L.uid, tid)
    j1, j2, j3 = (_job(L.uid, pid) for _ in range(3))
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)       # Param-Version bleibt running, Auftrag queued
    monkeypatch.setattr(config, "PARAM_PER_HOUR", 1)
    body = {"values": [{"id": "D1", "value": 41.0}]}
    try:
        assert M.post(f"/api/jobs/{j1}/param", json=body, headers=H).status_code == 200
        assert db.q1("SELECT user_id FROM job_versions WHERE job_id=? AND trigger='param'", (j1,))["user_id"] == M.uid
        assert db.q1("SELECT run_by FROM jobs WHERE id=?", (j1,))["run_by"] == M.uid
        assert M.post(f"/api/jobs/{j2}/param", json=body, headers=H).status_code == 429     # Grenze beim Ausloeser
        assert L.post(f"/api/jobs/{j3}/param", json=body, headers=H).status_code == 200      # der Leiter ist frei
    finally:
        db.ex("UPDATE jobs SET status='done' WHERE id IN (?,?,?)", (j1, j2, j3))
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id IN (?,?,?) AND status='running'", (j1, j2, j3))


def test_kontingent_ausloeser_geloescht_waehrend_lauf(app, admin):
    """Wird der Ausloeser geloescht, waehrend sein Lauf am Auftrag des Leiters noch Versionen anlegt, wird user_id NULL
    (zaehlt bei niemandem) statt eines Fremdschluessel-Fehlers, der den Auftrag des Leiters scheitern liesse."""
    from app import auth, db, jobs
    L, M = _mk(app, admin, "klaufg", "klaufgm")
    tid = _team("LaufWeg", {L.uid: "leiter", M.uid: "mitglied"})
    jid = _job(L.uid, _project(L.uid, tid))
    before_l = auth.usage_this_month(L.uid)
    db.ex("UPDATE jobs SET run_by=? WHERE id=?", (M.uid, jid))   # Lauf von M, "by" wurde beim Start gemerkt
    assert admin.delete(f"/api/admin/users/{M.uid}", headers=H).status_code == 200
    v = jobs._new_version(jid, "iterate", "x", "", {}, by=M.uid)   # by zeigt auf den geloeschten Benutzer
    v2 = jobs._new_version(jid, "autofix", "", "", {}, by=M.uid)
    for ver in (v, v2):
        assert db.q1("SELECT user_id FROM job_versions WHERE job_id=? AND version=?", (jid, ver))["user_id"] is None
    assert auth.usage_this_month(L.uid) == before_l


def test_kontingent_lauf_uebernimmt_ausloeser_in_autofix(app, admin, monkeypatch):
    """Echter _run (KI im Testmodus): M aendert den Auftrag des Leiters, die erste Antwort ist fehlerhaft, ein Autofix
    folgt. Beide Versionen dieses Laufs gehoeren M, auch wenn jobs.run_by waehrenddessen nicht mehr auf M zeigt
    (der Lauf haelt den beim Start gemerkten Ausloeser, nicht den Rueckgriff auf jobs.run_by)."""
    from app import ai, auth, db
    from test_api import wait_job
    L, M = _mk(app, admin, "krun", "krunm")
    tid = _team("Lauf", {L.uid: "leiter", M.uid: "mitglied"})
    jid = _job(L.uid, _project(L.uid, tid))            # messages=[]: die Testmodus-KI liefert zuerst den fehlerhaften Code
    before = auth.usage_this_month(L.uid), auth.usage_this_month(M.uid)
    real_call = ai.call

    def call(*a, **kw):
        db.ex("UPDATE jobs SET run_by=NULL WHERE id=?", (jid,))
        return real_call(*a, **kw)

    monkeypatch.setattr(ai, "call", call)
    assert M.post(f"/api/jobs/{jid}/iterate", json={"text": "Dicke 8 mm"}, headers=H).status_code == 200
    wait_job(M, jid)
    rows = db.q("SELECT trigger, user_id FROM job_versions WHERE job_id=? AND version>1 ORDER BY version", (jid,))
    assert [r["trigger"] for r in rows] == ["iterate", "autofix"]
    assert [r["user_id"] for r in rows] == [M.uid, M.uid]
    assert (auth.usage_this_month(L.uid), auth.usage_this_month(M.uid)) == (before[0], before[1] + 1)


# ------------------------------------------------------------------ T3: Teams verwalten

def _join(leader, member, tid, role="mitglied"):
    """Einladen und annehmen ueber die API."""
    r = leader.post(f"/api/teams/{tid}/invites", json={"username": member.username, "role": role}, headers=H)
    assert r.status_code == 200, r.text
    r = member.post(f"/api/team-invites/{r.json()['id']}/accept", headers=H)
    assert r.status_code == 200, r.text


def _new_team(c, name="Team"):
    r = c.post("/api/teams", json={"name": name}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _last_audit(action):
    from app import db
    return db.q1("SELECT * FROM audit WHERE action=? ORDER BY id DESC LIMIT 1", (action,))


TEAM_MATRIX = {
    ("GET", "/api/teams"): ("angemeldet", None),
    ("POST", "/api/teams"): ("angemeldet", {"name": "Neu"}),
    ("GET", "/api/teams/{tid}"): ("team:lesend", None),
    ("PATCH", "/api/teams/{tid}"): ("team:leiter", {"name": "Umbenannt"}),
    ("DELETE", "/api/teams/{tid}"): ("team:leiter", None),
    ("POST", "/api/teams/{tid}/invites"): ("team:leiter", "EINLADEN"),
    ("DELETE", "/api/teams/{tid}/invites/{iid}"): ("team:leiter", None),
    ("PATCH", "/api/teams/{tid}/members/{uid}"): ("team:leiter", {"role": "lesend"}),
    ("DELETE", "/api/teams/{tid}/members/{uid}"): ("team:leiter", None),   # andere entfernen; Austritt: eigener Test
    ("POST", "/api/team-invites/{iid}/accept"): ("einladung", None),
    ("POST", "/api/team-invites/{iid}/decline"): ("einladung", None),
}
RIGHTS.update({k: v[0] for k, v in TEAM_MATRIX.items()})
TEAM_CASES = {"leiter": "L", "mitglied": "M", "lesend": "R", "aussen": "F", "admin": "A", "eingeladen": "Y"}
TEAM_EXPECT = {"angemeldet": set(TEAM_CASES), "team:lesend": {"leiter", "mitglied", "lesend"}, "team:leiter": {"leiter"},
               "einladung": {"eingeladen"}}


@pytest.mark.parametrize("case", list(TEAM_CASES))
@pytest.mark.parametrize("key", list(TEAM_MATRIX), ids=lambda k: f"{k[0]} {k[1]}")
def test_rechte_team_routen(welt, key, case):
    """Frisches Team je Aufruf: L Leiter, M Mitglied, R Lesend, X Mitglied (Ziel), offene Einladung an Y."""
    from app import db
    w = welt
    need, body = TEAM_MATRIX[key]
    tid = _team("Matrix", {w.L.uid: "leiter", w.M.uid: "mitglied", w.R.uid: "lesend", w.X.uid: "mitglied"})
    iid = None
    if "{iid}" in key[1]:
        iid = db.ex("INSERT INTO team_invites(team_id,user_id,role,invited_by,created_at) VALUES (?,?,?,?,?)",
                    (tid, w.Y.uid, "mitglied", w.L.uid, db.now()))
    kw = {"headers": H}
    if body == "EINLADEN":
        kw["json"] = {"username": w.Y.username, "role": "mitglied"}
    elif body is not None:
        kw["json"] = body
    r = getattr(w, TEAM_CASES[case]).request(key[0], key[1].format(tid=tid, iid=iid, uid=w.X.uid), **kw)
    if case in TEAM_EXPECT[need]:
        assert r.status_code == 200, r.text
    elif need == "einladung" or case in ("aussen", "admin", "eingeladen"):
        assert r.status_code == 404, r.text
    else:
        assert r.status_code == 403 and r.json()["detail"] == "Nur ein Team-Leiter darf das", r.text


def test_verwaltung_anlegen_und_liste(app, admin):
    (L,) = _mk(app, admin, "vgruender")
    r = L.post("/api/teams", json={"name": "  Werkstatt  "}, headers=H)
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["name"], t["my_role"], t["n_projects"]) == ("Werkstatt", "leiter", 0)
    assert [(m["user_id"], m["role"]) for m in t["members"]] == [(L.uid, "leiter")]
    assert set(t["members"][0]) == {"user_id", "username", "display_name", "role", "joined_at"}
    lst = L.get("/api/teams").json()
    assert [(x["id"], x["my_role"], x["n_members"], x["n_projects"]) for x in lst["teams"]] == [(t["id"], "leiter", 1, 0)]
    assert lst["invites"] == []
    a = _last_audit("team_created")
    assert a["detail"] == f"Team {t['id']} „Werkstatt“ gegründet" and a["actor"] == L.username


def test_verwaltung_teamname_grenzen(app, admin):
    (L,) = _mk(app, admin, "vname")
    assert L.post("/api/teams", json={"name": "   "}, headers=H).status_code == 400
    assert L.post("/api/teams", json={"name": "x" * 81}, headers=H).status_code == 400
    tid = _new_team(L, "y" * 80)
    assert L.patch(f"/api/teams/{tid}", json={"name": " "}, headers=H).status_code == 400
    r = L.patch(f"/api/teams/{tid}", json={"name": " Halle 2 "}, headers=H)
    assert r.status_code == 200 and r.json()["name"] == "Halle 2"
    assert _last_audit("team_renamed")["detail"] == f"Team {tid}: „{'y' * 80}“ → „Halle 2“"
    for bad in ("A\x07B", "Zeile\nzwei", "Null\x00"):                               # Steuerzeichen
        r = L.post("/api/teams", json={"name": bad}, headers=H)
        assert r.status_code == 400 and r.json()["detail"] == "Der Teamname enthält unzulässige Zeichen.", bad
    assert L.patch(f"/api/teams/{tid}", json={"name": "Tab\tname"}, headers=H).status_code == 400
    for bad in ("A\u202eB", "A\u200bB", "A\u2028B", "A\u2029B", "A\ufeffB"):   # Richtungs-, Nullbreiten-, Zeilentrenner
        r = L.post("/api/teams", json={"name": bad}, headers=H)
        assert r.status_code == 400 and r.json()["detail"] == "Der Teamname enthält unzulässige Zeichen.", repr(bad)
    r = L.patch(f"/api/teams/{tid}", json={"name": "Halle\u202e3"}, headers=H)
    assert r.status_code == 400 and r.json()["detail"] == "Der Teamname enthält unzulässige Zeichen."
    assert L.get(f"/api/teams/{tid}").json()["name"] == "Halle 2"


def test_verwaltung_einladen_annehmen(app, admin):
    from app import db
    L, M = _mk(app, admin, "veinl", "veing")
    tid = _new_team(L, "Halle")
    r = L.post(f"/api/teams/{tid}/invites", json={"username": M.username, "role": "lesend"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "offen"
    assert M.get(f"/api/teams/{tid}").status_code == 404                 # Mitglieder erst nach der Annahme sichtbar
    inv = M.get("/api/teams").json()["invites"]
    assert [(i["team_id"], i["team_name"], i["role"], i["invited_by_name"]) for i in inv] == [(tid, "Halle", "lesend",
                                                                                                L.username)]
    assert set(inv[0]) == {"id", "team_id", "team_name", "role", "invited_by_name", "created_at"}
    assert M.get("/api/me").json()["team_invites"] == 1
    assert [i["username"] for i in L.get(f"/api/teams/{tid}").json()["invites"]] == [M.username]
    r = M.post(f"/api/team-invites/{inv[0]['id']}/accept", headers=H)
    assert r.status_code == 200 and r.json()["my_role"] == "lesend" and r.json()["invites"] == []
    r = M.post(f"/api/team-invites/{inv[0]['id']}/accept", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Einladung nicht mehr offen"
    assert M.get("/api/me").json()["team_invites"] == 0
    acts = [x["action"] for x in db.q("SELECT action FROM audit WHERE detail LIKE ? ORDER BY id", (f"Team {tid} %",))]
    assert acts == ["team_created", "team_invite", "team_invite_accepted"]


def test_verwaltung_einladen_fehler(app, admin):
    from app import db
    L, M, D = _mk(app, admin, "vfehl", "vfmit", "vfaus")
    tid = _new_team(L, "Fehler")
    db.ex("UPDATE users SET status='disabled' WHERE id=?", (D.uid,))

    def inv(name):
        return L.post(f"/api/teams/{tid}/invites", json={"username": name, "role": "mitglied"}, headers=H)
    r1, r2 = inv("gibtesnicht"), inv(D.username)
    assert r1.status_code == r2.status_code == 404 and r1.json() == r2.json() == {"detail": "Benutzer nicht gefunden"}
    assert inv(L.username).status_code == 400
    ok = inv(M.username)
    assert ok.status_code == 200
    r = inv(M.username)
    assert r.status_code == 409 and "offene Einladung" in r.json()["detail"]
    assert M.post(f"/api/team-invites/{ok.json()['id']}/accept", headers=H).status_code == 200
    r = inv(M.username)
    assert r.status_code == 409 and "bereits Mitglied" in r.json()["detail"]
    assert inv(M.username.upper()).status_code == 409
    rows = db.q("SELECT detail FROM audit WHERE action='team_invite_failed' AND user_id=? ORDER BY id", (L.uid,))
    assert [x["detail"].rsplit(" – ", 1)[1] for x in rows] == ["unbekannt", "deaktiviert", "sich selbst", "doppelt",
                                                               "schon Mitglied", "schon Mitglied"]
    assert L.post(f"/api/teams/{tid}/invites", json={"username": M.username, "role": "chef"}, headers=H).status_code == 400


def test_verwaltung_einladen_schreibweise(app, admin):
    """Review Focus 1: Gross/klein egal, Leerzeichen am Rand werden entfernt."""
    L, M = _mk(app, admin, "vschr", "vschrb")
    tid = _new_team(L, "Schreibweise")
    r = L.post(f"/api/teams/{tid}/invites", json={"username": f"  {M.username.upper()} ", "role": "mitglied"}, headers=H)
    assert r.status_code == 200, r.text
    assert (r.json()["user_id"], r.json()["username"]) == (M.uid, M.username)


def test_verwaltung_erneut_einladen(app, admin):
    """Review Focus 2: nach Ablehnen und nach Zurueckziehen entsteht eine neue Einladung."""
    from app import db
    L, M = _mk(app, admin, "verneut", "verneutm")
    tid = _new_team(L, "Nochmal")
    first = L.post(f"/api/teams/{tid}/invites", json={"username": M.username}, headers=H).json()["id"]
    assert M.post(f"/api/team-invites/{first}/decline", headers=H).json() == {"ok": True}
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (first,))["status"] == "abgelehnt"
    second = L.post(f"/api/teams/{tid}/invites", json={"username": M.username}, headers=H)
    assert second.status_code == 200 and second.json()["id"] != first
    assert L.delete(f"/api/teams/{tid}/invites/{second.json()['id']}", headers=H).json() == {"ok": True}
    third = L.post(f"/api/teams/{tid}/invites", json={"username": M.username}, headers=H)
    assert third.status_code == 200
    assert [i["id"] for i in M.get("/api/teams").json()["invites"]] == [third.json()["id"]]
    assert [a["action"] for a in db.q("SELECT action FROM audit WHERE action LIKE 'team_invite_%' AND detail LIKE ? "
                                      "ORDER BY id", (f"Team {tid} %",))] == ["team_invite_declined", "team_invite_revoked"]


def test_verwaltung_zurueckziehen_und_fremde_einladung(app, admin):
    L, M, F = _mk(app, admin, "vzur", "vzurm", "vzuro")
    tid = _new_team(L, "Zurueck")
    iid = L.post(f"/api/teams/{tid}/invites", json={"username": M.username}, headers=H).json()["id"]
    assert F.post(f"/api/team-invites/{iid}/accept", headers=H).status_code == 404       # fremde Einladung
    assert F.post(f"/api/team-invites/{iid}/decline", headers=H).status_code == 404
    assert L.delete(f"/api/teams/{tid}/invites/{iid}", headers=H).status_code == 200
    r = L.delete(f"/api/teams/{tid}/invites/{iid}", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Einladung nicht mehr offen"
    assert M.post(f"/api/team-invites/{iid}/accept", headers=H).status_code == 409
    assert M.get("/api/teams").json()["invites"] == []
    assert _last_audit("team_invite_revoked")["detail"] == f"Team {tid} „Zurueck“: Einladung an {M.username} zurückgezogen"


def test_verwaltung_einladen_grenze(app, admin):
    """Hoechstens 20 Versuche je Stunde ueber alle Teams; abgewiesene Versuche zaehlen mit."""
    from app import db
    (L,) = _mk(app, admin, "vgrenz")
    t1, t2 = _new_team(L, "A"), _new_team(L, "B")
    for i in range(10):
        assert L.post(f"/api/teams/{t1}/invites", json={"username": f"niemand{i}"}, headers=H).status_code == 404
        assert L.post(f"/api/teams/{t2}/invites", json={"username": f"keiner{i}"}, headers=H).status_code == 404
    r = L.post(f"/api/teams/{t1}/invites", json={"username": "niemand99"}, headers=H)
    assert r.status_code == 429 and "20 je Stunde" in r.json()["detail"]
    assert db.q1("SELECT COUNT(*) n FROM audit WHERE user_id=? AND action='team_invite_failed'", (L.uid,))["n"] == 20


def test_verwaltung_rollen_letzter_leiter(app, admin):
    L, M = _mk(app, admin, "vrolle", "vrollem")
    tid = _new_team(L, "Rollen")
    _join(L, M, tid)
    r = L.patch(f"/api/teams/{tid}/members/{L.uid}", json={"role": "mitglied"}, headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Erst einen anderen Leiter bestimmen"
    assert L.patch(f"/api/teams/{tid}/members/{M.uid}", json={"role": "leiter"}, headers=H).status_code == 200
    r = L.patch(f"/api/teams/{tid}/members/{L.uid}", json={"role": "mitglied"}, headers=H)
    assert r.status_code == 200 and r.json()["my_role"] == "mitglied"
    assert L.patch(f"/api/teams/{tid}/members/{M.uid}", json={"role": "lesend"}, headers=H).status_code == 403
    assert M.patch(f"/api/teams/{tid}/members/{L.uid}", json={"role": "chef"}, headers=H).status_code == 400
    assert M.patch(f"/api/teams/{tid}/members/999999", json={"role": "lesend"}, headers=H).status_code == 404
    assert _last_audit("team_role")["detail"] == f"Team {tid} „Rollen“: {L.username} → Mitglied"


def test_verwaltung_entfernen_und_austreten(app, admin):
    L, M, R = _mk(app, admin, "vent", "ventm", "ventr")
    tid = _new_team(L, "Raus")
    _join(L, M, tid)
    _join(L, R, tid, "lesend")
    assert M.delete(f"/api/teams/{tid}/members/{R.uid}", headers=H).status_code == 403
    assert L.delete(f"/api/teams/{tid}/members/{R.uid}", headers=H).json() == {"ok": True, "team_deleted": False}
    assert R.get(f"/api/teams/{tid}").status_code == 404
    assert _last_audit("team_member_removed")["detail"] == f"Team {tid} „Raus“: {R.username} entfernt"
    assert M.delete(f"/api/teams/{tid}/members/{M.uid}", headers=H).json() == {"ok": True, "team_deleted": False}
    assert _last_audit("team_left")["detail"] == f"Team {tid} „Raus“: {M.username} ausgetreten"
    assert L.delete(f"/api/teams/{tid}/members/999999", headers=H).status_code == 404


def test_verwaltung_einladungen_ehemaliger_leiter(app, admin):
    """Offene Einladungen eines Leiters, der herabgestuft oder entfernt wird, werden zurueckgezogen."""
    from app import db
    L, B, Y, Z = _mk(app, admin, "veleiter", "vezweit", "vegast", "vegastz")
    tid = _new_team(L, "Einladende")
    _join(L, B, tid, "leiter")
    i1 = L.post(f"/api/teams/{tid}/invites", json={"username": Y.username}, headers=H).json()["id"]
    i2 = B.post(f"/api/teams/{tid}/invites", json={"username": Z.username}, headers=H).json()["id"]
    assert B.patch(f"/api/teams/{tid}/members/{L.uid}", json={"role": "mitglied"}, headers=H).status_code == 200
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (i1,))["status"] == "zurueckgezogen"
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (i2,))["status"] == "offen"
    r = Y.post(f"/api/team-invites/{i1}/accept", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Einladung nicht mehr offen"
    assert B.patch(f"/api/teams/{tid}/members/{L.uid}", json={"role": "leiter"}, headers=H).status_code == 200
    assert L.delete(f"/api/teams/{tid}/members/{B.uid}", headers=H).status_code == 200                # B entfernt
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (i2,))["status"] == "zurueckgezogen"
    assert Z.get("/api/teams").json()["invites"] == []


def test_verwaltung_letzter_leiter_austritt(app, admin):
    from app import db
    L, M = _mk(app, admin, "vletzt", "vletztm")
    tid = _new_team(L, "Letzter")
    _join(L, M, tid)
    r = L.delete(f"/api/teams/{tid}/members/{L.uid}", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Erst einen anderen Leiter bestimmen"
    assert M.delete(f"/api/teams/{tid}/members/{M.uid}", headers=H).status_code == 200
    pid = _project(L.uid, tid)
    r = L.delete(f"/api/teams/{tid}/members/{L.uid}", headers=H)
    assert r.status_code == 409 and r.json()["detail"].startswith("Das Team hat noch 1 Projekt")
    db.ex("DELETE FROM projects WHERE id=?", (pid,))
    assert L.delete(f"/api/teams/{tid}/members/{L.uid}", headers=H).json() == {"ok": True, "team_deleted": True}
    assert db.q1("SELECT id FROM teams WHERE id=?", (tid,)) is None
    assert _last_audit("team_deleted")["detail"].startswith(f"Team {tid} „Letzter“ gelöscht")


def test_verwaltung_loeschen_leer_und_nicht_leer(app, admin):
    from app import db
    L, M = _mk(app, admin, "vloe", "vloem")
    tid = _new_team(L, "Loeschen")
    _join(L, M, tid)
    assert M.delete(f"/api/teams/{tid}", headers=H).status_code == 403
    p1 = _project(L.uid, tid)
    r = L.delete(f"/api/teams/{tid}", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Das Team hat noch 1 Projekt"
    p2 = _project(M.uid, tid)
    assert L.delete(f"/api/teams/{tid}", headers=H).json()["detail"] == "Das Team hat noch 2 Projekte"
    db.ex("DELETE FROM projects WHERE id IN (?,?)", (p1, p2))
    assert L.delete(f"/api/teams/{tid}", headers=H).json() == {"ok": True}
    assert db.q1("SELECT COUNT(*) n FROM team_members WHERE team_id=?", (tid,))["n"] == 0
    assert L.get("/api/teams").json()["teams"] == []
    assert _last_audit("team_deleted")["detail"] == f"Team {tid} „Loeschen“ gelöscht (0 Projekte)"


def test_verwaltung_annehmen_bei_bestehender_mitgliedschaft(app, admin):
    """Ist der Eingeladene schon Mitglied (z. B. direkt aufgenommen), bleibt seine Rolle; das Audit sagt das wahrheitsgemaess."""
    from app import db
    L, M = _mk(app, admin, "vschon", "vschonm")
    tid = _new_team(L, "Schon")
    iid = L.post(f"/api/teams/{tid}/invites", json={"username": M.username, "role": "leiter"}, headers=H).json()["id"]
    db.ex("INSERT INTO team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?)", (tid, M.uid, "lesend", db.now()))
    r = M.post(f"/api/team-invites/{iid}/accept", headers=H)
    assert r.status_code == 200 and r.json()["my_role"] == "lesend", r.text
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (iid,))["status"] == "angenommen"
    assert db.q1("SELECT COUNT(*) n FROM team_members WHERE team_id=? AND user_id=?", (tid, M.uid))["n"] == 1
    a = _last_audit("team_invite_accepted")
    assert a["detail"] == f"Team {tid} „Schon“: {M.username} hat angenommen, war bereits Mitglied (Lesend)", a["detail"]
    assert "beigetreten" not in a["detail"]


# ------------------------------------------------------------------ T4: Bereiche, Anlegen, Verschieben

def _ids(c, scope=None):
    r = c.get("/api/projects" + (f"?scope={scope}" if scope is not None else ""))
    assert r.status_code == 200, r.text
    return [p["id"] for p in r.json()]


def test_rechte_bereiche_liste(app, admin):
    from app import db
    L, M, F = _mk(app, admin, "bleiter", "bmitgl", "baussen")
    tid = _team("Bereich", {L.uid: "leiter", M.uid: "mitglied"})
    priv = L.post("/api/projects", json={"name": "Privat"}, headers=H).json()
    tp = L.post("/api/projects", json={"name": "Team", "team_id": tid}, headers=H).json()
    assert (tp["team_id"], tp["team_name"], tp["my_role"], tp["creator_is_member"]) == (tid, "Bereich", "leiter", True)
    assert tp["creator"] == {"id": L.uid, "name": L.display}
    assert (priv["team_id"], priv["team_name"], priv["my_role"], priv["creator_is_member"]) == (None, None, "besitzer", None)
    alle = {"write": True, "delete": True, "move": True, "copy": True}
    assert tp["rights"] == priv["rights"] == alle
    assert _ids(L) == _ids(L, "private") == [priv["id"]]
    assert _ids(L, f"team:{tid}") == [tp["id"]]
    assert set(_ids(L, "all")) == {priv["id"], tp["id"]}
    assert _ids(M, "all") == [tp["id"]] and _ids(M, "private") == []
    entry = M.get(f"/api/projects?scope=team:{tid}").json()[0]
    assert entry["my_role"] == "mitglied" and {"thumb", "last_job", "updated_at"} <= set(entry)
    assert entry["rights"] == {"write": True, "delete": False, "move": False, "copy": True}         # fremd angelegt
    assert F.get(f"/api/projects?scope=team:{tid}").status_code == 404
    assert L.get("/api/projects?scope=quatsch").status_code == 400
    assert L.get("/api/projects?scope=team:²").status_code == 400
    for big in ("9" * 19, "9" * 20):                                                   # Ueberlauf und Laenge > 24
        assert L.get(f"/api/projects?scope=team:{big}").status_code == 400
    mp = M.post("/api/projects", json={"name": "von M", "team_id": tid}, headers=H).json()["id"]
    db.ex("DELETE FROM team_members WHERE team_id=? AND user_id=?", (tid, M.uid))       # M ist ehemaliges Mitglied
    e = next(p for p in L.get(f"/api/projects?scope=team:{tid}").json() if p["id"] == mp)
    assert e["creator"] == {"id": M.uid, "name": M.display} and e["creator_is_member"] is False
    db.ex("UPDATE projects SET user_id=NULL WHERE id=?", (mp,))                          # geloeschter Ersteller
    e = next(p for p in L.get(f"/api/projects?scope=team:{tid}").json() if p["id"] == mp)
    assert e["creator"] is None and e["creator_is_member"] is False


def test_rechte_anlegen_im_team(app, admin):
    from app import access
    L, M, R, F = _mk(app, admin, "aleiter", "amitgl", "alesend", "aaussen")
    tid = _team("Anlegen", {L.uid: "leiter", M.uid: "mitglied", R.uid: "lesend"})
    assert M.post("/api/projects", json={"name": "x", "team_id": tid}, headers=H).status_code == 200
    r = R.post("/api/projects", json={"name": "x", "team_id": tid}, headers=H)
    assert r.status_code == 403 and r.json()["detail"] == access.DENY_WRITE
    assert F.post("/api/projects", json={"name": "x", "team_id": tid}, headers=H).status_code == 404
    assert L.post("/api/projects", json={"name": "y", "team_id": 999999}, headers=H).status_code == 404
    for bad in (10**20, 0, -1):                                                        # Ueberlauf und Unsinn: 422
        assert L.post("/api/projects", json={"name": "z", "team_id": bad}, headers=H).status_code == 422


@pytest.mark.parametrize("case", [c for c in CASES if c not in NO_READ])
def test_rechte_feld_rights_wie_matrix(welt, case):
    """Lueckenfuellung 19: das Feld rights je Projekt (Menue der Bibliothek) folgt derselben Regel wie die Routen."""
    actor, creator, in_team = CASES[case]
    pid = _project(getattr(welt, creator).uid, welt.tid if in_team else None)
    r = getattr(welt, actor).get(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    assert r.json()["rights"] == {n: case in EXPECT[n] for n in ("write", "delete", "move", "copy")}


def test_rechte_current_bleibt_privat(app, admin):
    (L,) = _mk(app, admin, "cleiter")
    tid = _team("Current", {L.uid: "leiter"})
    tp = L.post("/api/projects", json={"name": "Team", "team_id": tid}, headers=H).json()["id"]
    cur = L.get("/api/projects/current").json()
    assert cur["team_id"] is None and cur["id"] != tp and cur["user_id"] == L.uid
    assert L.get("/api/projects/current").json()["id"] == cur["id"]


def test_rechte_nach_austritt_404_und_current(app, admin):
    """Review Focus 4: Mitgliedschaft weg, Seite noch offen -> naechste Anfrage 404, current liefert privat."""
    L, M = _mk(app, admin, "nleiter", "nmitgl")
    tid = _team("Austritt", {L.uid: "leiter", M.uid: "mitglied"})
    tp = M.post("/api/projects", json={"name": "Meins", "team_id": tid}, headers=H).json()["id"]
    jid = _job(M.uid, tp)
    assert M.get(f"/api/projects/{tp}").status_code == 200
    assert L.delete(f"/api/teams/{tid}/members/{M.uid}", headers=H).status_code == 200
    r = M.get(f"/api/projects/{tp}")
    assert r.status_code == 404 and r.json()["detail"] == "Projekt nicht gefunden"
    assert M.get(f"/api/jobs/{jid}").status_code == 404
    assert M.get("/api/projects/current").json()["team_id"] is None
    assert L.get(f"/api/projects/{tp}").json()["creator_is_member"] is False        # Projekt bleibt im Team


def test_rechte_auftrag_felder(app, admin):
    L, R = _mk(app, admin, "fleiter", "flesend")
    tid = _team("Felder", {L.uid: "leiter", R.uid: "lesend"})
    jid = _job(L.uid, _project(L.uid, tid))
    j = R.get(f"/api/jobs/{jid}").json()
    assert (j["my_role"], j["team_id"], j["team_name"]) == ("lesend", tid, "Felder")
    assert L.get(f"/api/jobs/{_job(L.uid, _project(L.uid))}").json()["my_role"] == "besitzer"
    j3 = L.get(f"/api/jobs/{_job(L.uid, None)}").json()
    assert (j3["my_role"], j3["team_id"], j3["team_name"]) == ("besitzer", None, None)


def test_verschieben_privat_ins_team_mit_auftraegen(app, admin):
    from app import db
    L, M = _mk(app, admin, "vsleiter", "vsmitgl")
    tid = _team("Ziel", {L.uid: "leiter", M.uid: "mitglied"})
    pid = L.post("/api/projects", json={"name": "Wandert"}, headers=H).json()["id"]
    jid = _job(L.uid, pid)
    assert M.get(f"/api/jobs/{jid}").status_code == 404
    r = L.post(f"/api/projects/{pid}/move", json={"team_id": tid}, headers=H)
    assert r.status_code == 200, r.text
    assert (r.json()["team_id"], r.json()["user_id"], r.json()["team_name"]) == (tid, L.uid, "Ziel")
    assert M.get(f"/api/projects/{pid}").status_code == 200 and M.get(f"/api/jobs/{jid}").status_code == 200
    assert db.q1("SELECT project_id FROM jobs WHERE id=?", (jid,))["project_id"] == pid      # Auftrag folgt dem Projekt
    a = _last_audit("project_move")
    assert a["detail"] == f"Projekt {pid}: privat → Team {tid} „Ziel“" and a["actor"] == L.username


def test_verschieben_team_nach_privat(app, admin):
    L, M = _mk(app, admin, "vpleiter", "vpmitgl")
    tid = _team("Zurueck", {L.uid: "leiter", M.uid: "mitglied"})
    pid = M.post("/api/projects", json={"name": "von M", "team_id": tid}, headers=H).json()["id"]
    _job(L.uid, pid)                                              # nur Auftraege des Verschiebenden
    r = L.post(f"/api/projects/{pid}/move", json={"team_id": None}, headers=H)
    assert r.status_code == 200, r.text
    assert (r.json()["team_id"], r.json()["user_id"], r.json()["my_role"]) == (None, L.uid, "besitzer")
    assert M.get(f"/api/projects/{pid}").status_code == 404
    assert _last_audit("project_move")["detail"] == f"Projekt {pid}: Team {tid} „Zurueck“ → privat"


def test_verschieben_fremder_auftrag_409(app, admin):
    from app import db
    L, M = _mk(app, admin, "vfleiter", "vfmitgl")
    tid = _team("Fremd", {L.uid: "leiter", M.uid: "mitglied"})
    pid = _project(L.uid, tid)
    _job(L.uid, pid)
    _job(M.uid, pid)
    r = L.post(f"/api/projects/{pid}/move", json={"team_id": None}, headers=H)
    assert r.status_code == 409
    assert r.json()["detail"] == "Das Projekt enthält Aufträge anderer Mitglieder – bitte „In privat kopieren“ verwenden"
    assert db.q1("SELECT team_id FROM projects WHERE id=?", (pid,))["team_id"] == tid


def test_verschieben_geloeschter_ersteller_409(app, admin):
    from app import db
    (L,) = _mk(app, admin, "vgleiter")
    tid = _team("Geloescht", {L.uid: "leiter"})
    pid = _project(L.uid, tid)
    jid = _job(L.uid, pid)
    db.ex("UPDATE jobs SET user_id=NULL WHERE id=?", (jid,))
    assert L.post(f"/api/projects/{pid}/move", json={"team_id": None}, headers=H).status_code == 409


def test_verschieben_rechte_und_ziele(app, admin):
    from app import access
    L, M, R, F = _mk(app, admin, "vrleiter", "vrmitgl", "vrlesend", "vraussen")
    tid = _team("Start", {L.uid: "leiter", M.uid: "mitglied", R.uid: "lesend"})
    t_o = _team("Fremdes", {F.uid: "leiter"})
    t_ro = _team("Nur lesen", {L.uid: "lesend"})
    t_l = _team("Zweites", {L.uid: "leiter"})
    tp_l, tp_m, priv = _project(L.uid, tid), _project(M.uid, tid), _project(L.uid)
    assert M.post(f"/api/projects/{tp_l}/move", json={"team_id": None}, headers=H).status_code == 403   # fremd angelegt
    r = R.post(f"/api/projects/{tp_m}/move", json={"team_id": None}, headers=H)
    assert r.status_code == 403 and r.json()["detail"] == access.DENY_WRITE
    assert F.post(f"/api/projects/{tp_l}/move", json={"team_id": None}, headers=H).status_code == 404
    assert L.post(f"/api/projects/{priv}/move", json={"team_id": t_o}, headers=H).status_code == 404   # kein Mitglied
    r = L.post(f"/api/projects/{priv}/move", json={"team_id": t_ro}, headers=H)
    assert r.status_code == 403 and r.json()["detail"] == access.DENY_WRITE                           # Ziel nur lesend
    r = L.post(f"/api/projects/{priv}/move", json={"team_id": None}, headers=H)
    assert r.status_code == 400 and r.json()["detail"] == "Das Projekt liegt bereits in diesem Bereich."
    assert L.post(f"/api/projects/{tp_l}/move", json={"team_id": tid}, headers=H).status_code == 400
    r = L.post(f"/api/projects/{tp_l}/move", json={"team_id": t_l}, headers=H)
    assert r.status_code == 400 and "In privat kopieren" in r.json()["detail"]                         # Team -> Team
    r = admin.post(f"/api/projects/{_project(F.uid)}/move", json={"team_id": t_o}, headers=H)
    assert r.status_code == 403 and r.json()["detail"] == access.DENY_OWNER                            # Admin: nie move
    assert L.post(f"/api/projects/{priv}/move", json={"team_id": 10**20}, headers=H).status_code == 422   # Ueberlauf


def test_verschieben_mitgliedschaft_weg_vor_transaktion(app, admin, monkeypatch):
    """Rechte in der Transaktion wiederholt: faellt die Mitgliedschaft im Ziel-Team nach der ersten Pruefung weg,
    bleibt das Projekt privat (404)."""
    from app import access, db
    (L,) = _mk(app, admin, "vtleiter")
    tid = _team("Weg davor", {L.uid: "leiter"})
    pid = _project(L.uid)
    real, calls = access.require_team, []

    def require_team(user, team_id, need):
        out = real(user, team_id, need)
        if not calls:                                       # nach der ersten Pruefung: Austritt dazwischen
            calls.append(1)
            db.ex("DELETE FROM team_members WHERE team_id=? AND user_id=?", (team_id, user["id"]))
        return out
    monkeypatch.setattr(access, "require_team", require_team)
    r = L.post(f"/api/projects/{pid}/move", json={"team_id": tid}, headers=H)
    assert r.status_code == 404 and r.json()["detail"] == "Team nicht gefunden", r.text
    assert db.q1("SELECT team_id FROM projects WHERE id=?", (pid,))["team_id"] is None
    assert len(calls) == 1


def test_benutzer_teamprojekt_loeschen_auftraege_ohne_ersteller(app, admin):
    """Spec §4: Aufträge bleiben beim Ersteller ohne Projekt; Aufträge ohne Ersteller werden mitgelöscht."""
    from app import config, db
    L, M = _mk(app, admin, "lleiter", "lmitgl")
    tid = _team("Loeschen", {L.uid: "leiter", M.uid: "mitglied"})
    pid = _project(M.uid, tid)
    phid = _photo(pid)
    j_l, j_x = _job(L.uid, pid), _job(M.uid, pid)
    db.ex("UPDATE jobs SET user_id=NULL WHERE id=?", (j_x,))
    assert L.delete(f"/api/projects/{pid}", headers=H).json() == {"ok": True}
    assert db.q1("SELECT project_id FROM jobs WHERE id=?", (j_l,))["project_id"] is None
    assert L.get(f"/api/jobs/{j_l}").status_code == 200
    assert db.q1("SELECT id FROM jobs WHERE id=?", (j_x,)) is None
    assert not (config.DATA_DIR / "jobs" / str(j_x)).exists()
    assert not (config.DATA_DIR / "photos" / str(phid)).exists()


def test_benutzer_loeschen_projekt_inzwischen_verschoben(app, admin, monkeypatch):
    """Rechte beim Loeschen in der Transaktion wiederholt (guard): verschiebt der Leiter das Projekt zwischen Pruefung
    und Loeschen nach privat, loescht das Mitglied es nicht (404)."""
    from app import db, main
    L, M = _mk(app, admin, "bvleiter", "bvmitgl")
    tid = _team("Inzwischen", {L.uid: "leiter", M.uid: "mitglied"})
    pid = _project(M.uid, tid)
    jx = _job(None, pid)                                    # Auftrag ohne Ersteller: darf bei 404 nicht verschwinden
    real, calls = main._own_project, []

    def own(p, user, need="write"):
        out = real(p, user, need)
        if not calls:                                       # nach der ersten Pruefung: Leiter verschiebt nach privat
            calls.append(1)
            db.ex("UPDATE projects SET team_id=NULL, user_id=? WHERE id=?", (L.uid, p))
        return out
    monkeypatch.setattr(main, "_own_project", own)
    r = M.delete(f"/api/projects/{pid}", headers=H)
    assert r.status_code == 404 and r.json()["detail"] == "Projekt nicht gefunden", r.text
    assert db.q1("SELECT team_id, user_id FROM projects WHERE id=?", (pid,)) == {"team_id": None, "user_id": L.uid}
    assert db.q1("SELECT id FROM jobs WHERE id=?", (jx,)) is not None


def test_verschieben_auftrag_anlegen_waehrend_verschieben(app, admin, monkeypatch):
    """Review Minor 1: verschiebt der Leiter das Projekt nach privat, waehrend das Mitglied einen Auftrag anlegt
    (nach der ersten Rechtepruefung), landet kein fremder Auftrag im privaten Projekt (F-1); das Mitglied bekommt 404."""
    from app import db, jobs
    L, M = _mk(app, admin, "valeiter", "vamitgl")
    tid = _team("Anlegen dazwischen", {L.uid: "leiter", M.uid: "mitglied"})
    db.ex("UPDATE users SET cad_quota=-1 WHERE id=?", (M.uid,))
    pid = _project(L.uid, tid)
    real, calls = jobs.build_initial_message, []

    def build(project, request_text, options):
        if not calls:                                       # nach der ersten Pruefung: Leiter verschiebt nach privat
            calls.append(1)
            assert L.post(f"/api/projects/{pid}/move", json={"team_id": None}, headers=H).status_code == 200
        return real(project, request_text, options)
    monkeypatch.setattr(jobs, "build_initial_message", build)
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    r = M.post("/api/jobs", json={"project_id": pid, "name": "dazwischen", "request": "Platte"}, headers=H)
    assert r.status_code == 404 and r.json()["detail"] == "Projekt nicht gefunden", r.text
    assert calls == [1]
    assert db.q1("SELECT COUNT(*) n FROM jobs WHERE project_id=?", (pid,))["n"] == 0
    assert db.q1("SELECT team_id, user_id FROM projects WHERE id=?", (pid,)) == {"team_id": None, "user_id": L.uid}


def test_benutzer_loeschen_nicht_in_transaktion(app, admin):
    """Review Minor 2: delete_projects innerhalb von db.atomic -> RuntimeError, nichts geloescht."""
    from app import db, projects
    (L,) = _mk(app, admin, "ntleiter")
    pid = _project(L.uid)
    with db.atomic():
        with pytest.raises(RuntimeError, match="nicht innerhalb von db.atomic"):
            projects.delete_projects([pid])
    assert db.q1("SELECT id FROM projects WHERE id=?", (pid,)) is not None


def test_rechte_bereich_all_ohne_fremde(app, admin):
    """Review Minor 4: scope=all eines Nicht-Mitglieds (auch des Admins) enthaelt keine fremden Team- und keine
    fremden privaten Projekte; team:<id> fuer den Admin ohne Mitgliedschaft -> 404."""
    L, F = _mk(app, admin, "baleiter", "baaussen")
    tid = _team("Fremd fuer alle", {L.uid: "leiter"})
    tp = L.post("/api/projects", json={"name": "Team", "team_id": tid}, headers=H).json()["id"]
    priv = L.post("/api/projects", json={"name": "Privat"}, headers=H).json()["id"]
    own = F.post("/api/projects", json={"name": "Eigen"}, headers=H).json()["id"]
    assert _ids(F, "all") == [own]
    a_all = set(_ids(admin, "all"))
    assert not a_all & {tp, priv, own}
    r = admin.get(f"/api/projects?scope=team:{tid}")
    assert r.status_code == 404 and r.json()["detail"] == "Team nicht gefunden"


# ------------------------------------------------------------------ T7/T8: Benutzer loeschen, Admin-Reiter

def test_admin_teams_liste(app, admin, user):
    L, M = _mk(app, admin, "adleiter", "admitgl")
    tid = _team("Sichtbar", {L.uid: "leiter", M.uid: "mitglied"})
    ohne = _team("Verwaist", {M.uid: "mitglied"})
    _project(L.uid, tid)
    rows = {t["id"]: t for t in admin.get("/api/admin/teams").json()}
    assert (rows[tid]["leaders"], rows[tid]["n_members"], rows[tid]["n_projects"], rows[tid]["no_leader"]) == \
        ([L.username], 2, 1, False)
    assert rows[ohne]["no_leader"] is True and rows[ohne]["leaders"] == []
    assert user.get("/api/admin/teams").status_code == 403
    d = admin.get(f"/api/admin/teams/{tid}").json()
    assert set(d) == {"id", "name", "created_at", "my_role", "n_projects", "members", "invites"} and d["my_role"] is None
    assert admin.get("/api/admin/teams/999999").status_code == 404


def test_admin_rollen_entfernen_einladung(app, admin):
    from app import db
    L, M, Y, Z = _mk(app, admin, "arleiter", "armitgl", "argast", "argastz")
    tid = _team("Eingriff", {L.uid: "leiter", M.uid: "mitglied"})
    iid = L.post(f"/api/teams/{tid}/invites", json={"username": Y.username}, headers=H).json()["id"]
    r = admin.patch(f"/api/admin/teams/{tid}/members/{M.uid}", json={"role": "leiter"}, headers=H)
    assert r.status_code == 200 and {m["user_id"]: m["role"] for m in r.json()["members"]}[M.uid] == "leiter"
    assert _last_audit("team_role")["detail"] == f"Team {tid} „Eingriff“: {M.username} → Leiter (Administrator)"
    j2 = M.post(f"/api/teams/{tid}/invites", json={"username": Z.username}, headers=H).json()["id"]    # M ist Leiter
    r = admin.delete(f"/api/admin/teams/{tid}/members/{L.uid}", headers=H)
    assert r.status_code == 200 and [m["user_id"] for m in r.json()["members"]] == [M.uid]
    assert r.json()["team_deleted"] is False
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (iid,))["status"] == "zurueckgezogen"   # von L
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (j2,))["status"] == "offen"
    assert admin.delete(f"/api/admin/teams/{tid}/invites/{j2}", headers=H).json() == {"ok": True}
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (j2,))["status"] == "zurueckgezogen"
    assert admin.patch(f"/api/admin/teams/{tid}/members/{L.uid}", json={"role": "lesend"}, headers=H).status_code == 404
    assert admin.patch(f"/api/admin/teams/{tid}/members/{M.uid}", json={"role": "chef"}, headers=H).status_code == 400


def test_admin_mitglied_direkt_aufnehmen(app, admin):
    """Team ohne Mitglieder mit Projekt: der Admin nimmt R direkt als Leiter auf, R sieht das Projekt (Spec §5, §8)."""
    from app import db
    L, R, D = _mk(app, admin, "amleiter", "amneu", "amaus")
    tid = _team("Verwaist", {L.uid: "leiter"})
    pid = _project(L.uid, tid)
    iid = db.ex("INSERT INTO team_invites(team_id,user_id,role,invited_by,created_at) VALUES (?,?,?,?,?)",
                (tid, R.uid, "lesend", L.uid, db.now()))
    db.ex("DELETE FROM team_members WHERE team_id=?", (tid,))                   # letztes Mitglied weg, Projekt bleibt
    assert R.get(f"/api/projects/{pid}").status_code == 404
    r = admin.post(f"/api/admin/teams/{tid}/members", json={"username": f" {R.username.upper()} ", "role": "leiter"},
                   headers=H)
    assert r.status_code == 200, r.text
    assert [(m["user_id"], m["role"]) for m in r.json()["members"]] == [(R.uid, "leiter")]
    assert R.get(f"/api/projects/{pid}").json()["my_role"] == "leiter"
    assert db.q1("SELECT status FROM team_invites WHERE id=?", (iid,))["status"] == "zurueckgezogen"
    assert _last_audit("team_member_added_admin")["detail"] == \
        f"Team {tid} „Verwaist“: {R.username} als Leiter aufgenommen (Administrator)"
    r = admin.post(f"/api/admin/teams/{tid}/members", json={"username": R.username, "role": "mitglied"}, headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Ist bereits Mitglied dieses Teams."
    db.ex("UPDATE users SET status='disabled' WHERE id=?", (D.uid,))
    for name in ("gibtesnicht", D.username, "  "):
        r = admin.post(f"/api/admin/teams/{tid}/members", json={"username": name, "role": "mitglied"}, headers=H)
        assert r.status_code == 404 and r.json()["detail"] == "Benutzer nicht gefunden", name
    assert admin.post(f"/api/admin/teams/{tid}/members", json={"username": L.username, "role": "chef"},
                      headers=H).status_code == 400
    assert admin.post("/api/admin/teams/999999/members", json={"username": L.username}, headers=H).status_code == 404


def test_admin_letztes_mitglied_entfernen(app, admin):
    """Entfernt der Admin das letzte Mitglied: ein Team ohne Projekte wird geloescht, eines mit Projekten bleibt."""
    from app import db
    L, M = _mk(app, admin, "aeleiter", "aemitgl")
    leer, voll = _team("Leer", {L.uid: "leiter"}), _team("Voll", {M.uid: "leiter"})
    pid = _project(M.uid, voll)
    assert admin.delete(f"/api/admin/teams/{leer}/members/{L.uid}", headers=H).json() == {"ok": True, "team_deleted": True}
    assert db.q1("SELECT id FROM teams WHERE id=?", (leer,)) is None
    assert _last_audit("team_deleted")["detail"] == \
        f"Team {leer} „Leer“ gelöscht (letztes Mitglied entfernt, Administrator, 0 Projekte)"
    r = admin.delete(f"/api/admin/teams/{voll}/members/{M.uid}", headers=H)
    assert r.status_code == 200 and r.json()["members"] == [] and r.json()["team_deleted"] is False
    assert db.q1("SELECT team_id FROM projects WHERE id=?", (pid,))["team_id"] == voll


def test_admin_routen_nur_admin(app, welt):
    """Alle Routen unter /api/admin/teams verlangen den Administrator (403 auch fuer einen Team-Leiter)."""
    ks = sorted(k for k in _routes(app) if k[1].startswith("/api/admin/teams"))
    assert len(ks) == 7, ks
    for m, p in ks:
        r = welt.L.request(m, p.format(tid=welt.tid, uid=welt.M.uid, iid=1),
                           json={"role": "lesend", "username": welt.X.username}, headers=H)
        assert r.status_code == 403 and r.json()["detail"] == "Nur für Administratoren", (m, p, r.text)


def test_admin_team_loeschen_mit_projekten(app, admin):
    from app import config, db
    L, M = _mk(app, admin, "atleiter", "atmitgl")
    tid = _team("Abriss", {L.uid: "leiter", M.uid: "mitglied"})
    p1, p2 = _project(L.uid, tid), _project(M.uid, tid)
    ph = _photo(p1)
    j_l, j_x = _job(L.uid, p1), _job(M.uid, p2)
    db.ex("UPDATE jobs SET user_id=NULL WHERE id=?", (j_x,))
    r = admin.delete(f"/api/admin/teams/{tid}", headers=H)
    assert r.status_code == 409 and r.json()["detail"].startswith("Das Team hat noch 2 Projekte")
    assert admin.delete(f"/api/admin/teams/{tid}?confirm=Falsch", headers=H).status_code == 409
    r = admin.delete(f"/api/admin/teams/{tid}?confirm=Abriss", headers=H)
    assert r.json() == {"ok": True, "projects": 2}
    assert db.q1("SELECT id FROM teams WHERE id=?", (tid,)) is None
    assert db.q1("SELECT COUNT(*) n FROM projects WHERE id IN (?,?)", (p1, p2))["n"] == 0
    assert not (config.DATA_DIR / "photos" / str(ph)).exists()
    assert db.q1("SELECT project_id, user_id FROM jobs WHERE id=?", (j_l,)) == {"project_id": None, "user_id": L.uid}
    assert db.q1("SELECT id FROM jobs WHERE id=?", (j_x,)) is None
    assert "2 Projekte" in _last_audit("team_deleted")["detail"]
    t2 = _team("Leer", {L.uid: "leiter"})
    assert admin.delete(f"/api/admin/teams/{t2}", headers=H).json() == {"ok": True, "projects": 0}


def test_admin_team_loeschen_verschobenes_projekt_bleibt(app, admin, monkeypatch):
    """Wird ein Projekt zwischen Zaehlen und Loeschen aus dem Team verschoben, loescht der Admin es nicht mit (409)."""
    from app import db, teams
    (L,) = _mk(app, admin, "atvleiter")
    tid = _team("Wettlauf", {L.uid: "leiter"})
    p1, p2 = _project(L.uid, tid), _project(L.uid, tid)
    real = teams.projects.delete_projects

    def racy(pids, then=None, guard=None):
        db.ex("UPDATE projects SET team_id=NULL WHERE id=?", (p2,))            # gleichzeitig nach privat verschoben
        return real(pids, then=then, guard=guard)
    monkeypatch.setattr(teams.projects, "delete_projects", racy)
    r = admin.delete(f"/api/admin/teams/{tid}?confirm=Wettlauf", headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Im Team hat sich gerade etwas geändert – bitte erneut löschen."
    assert db.q1("SELECT team_id FROM projects WHERE id=?", (p2,))["team_id"] is None              # Projekt existiert
    assert db.q1("SELECT team_id FROM projects WHERE id=?", (p1,))["team_id"] == tid               # nichts geloescht
    assert db.q1("SELECT id FROM teams WHERE id=?", (tid,))


def test_admin_kein_inhalt_ohne_mitgliedschaft(app, admin):
    from app import db
    (L,) = _mk(app, admin, "akleiter")
    tid = _team("Privatsache", {L.uid: "leiter"})
    pid = _project(L.uid, tid)
    jid = _job(L.uid, pid)
    admin_uid = db.q1("SELECT id FROM users WHERE username='admin'")["id"]
    assert admin.get(f"/api/projects/{pid}").status_code == 404
    assert admin.get(f"/api/jobs/{jid}").status_code == 404
    assert jid not in [j["id"] for j in admin.get("/api/jobs?all=1").json()]
    db.ex("INSERT INTO team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?)", (tid, admin_uid, "lesend", db.now()))
    try:
        assert admin.get(f"/api/projects/{pid}").json()["my_role"] == "lesend"
        assert admin.patch(f"/api/projects/{pid}", json={"name": "x"}, headers=H).status_code == 403
        assert jid in [j["id"] for j in admin.get("/api/jobs?all=1").json()]
    finally:
        db.ex("DELETE FROM team_members WHERE team_id=? AND user_id=?", (tid, admin_uid))


def test_admin_auftraege_alle(app, admin):
    from app import db
    (L,) = _mk(app, admin, "aaleiter")
    admin_uid = db.q1("SELECT id FROM users WHERE username='admin'")["id"]
    j_priv, j_none = _job(L.uid, _project(L.uid)), _job(L.uid, None)
    j_team = _job(L.uid, _project(L.uid, _team("Fremd", {L.uid: "leiter"})))
    t_adm = _team("Mit Admin", {L.uid: "leiter", admin_uid: "mitglied"})
    j_del = _job(L.uid, _project(L.uid, t_adm))
    db.ex("UPDATE jobs SET user_id=NULL WHERE id=?", (j_del,))
    rows = {j["id"]: j for j in admin.get("/api/jobs?all=1").json()}
    assert j_priv in rows and j_none in rows and j_team not in rows
    assert rows[j_priv]["username"] == L.username
    assert rows[j_del]["username"] is None and rows[j_del]["user_id"] is None        # LEFT JOIN: geloeschter Benutzer


def test_admin_benutzerliste_zahlen(app, admin):
    (L,) = _mk(app, admin, "azleiter")
    tid = _team("Zahl", {L.uid: "leiter"})
    _project(L.uid, tid)
    _project(L.uid, tid)
    _job(L.uid, None)
    u = next(x for x in admin.get("/api/admin/users").json() if x["id"] == L.uid)
    assert (u["team_projects"], u["jobs"]) == (2, 1)


def test_benutzer_loeschen_private_weg_team_bleibt(app, admin):
    from app import config, db
    L, M = _mk(app, admin, "buleiter", "bumitgl")
    tid = _team("Bleibt", {L.uid: "leiter", M.uid: "mitglied"})
    t2 = _team("Andere", {L.uid: "leiter"})
    priv = _project(M.uid)
    ph = _photo(priv)
    j_priv, j_none = _job(M.uid, priv), _job(M.uid, None)
    j_l_in_priv = _job(L.uid, priv)
    tp = _project(M.uid, tid)
    j_team = _job(M.uid, tp)
    db.ex("INSERT INTO team_invites(team_id,user_id,role,invited_by,created_at) VALUES (?,?,?,?,?)",
          (t2, M.uid, "mitglied", L.uid, db.now()))
    r = admin.delete(f"/api/admin/users/{M.uid}", headers=H)
    assert r.json() == {"ok": True, "team_projects_kept": 1}
    assert db.q1("SELECT id FROM projects WHERE id=?", (priv,)) is None
    assert not (config.DATA_DIR / "photos" / str(ph)).exists()
    for j in (j_priv, j_none):
        assert db.q1("SELECT id FROM jobs WHERE id=?", (j,)) is None and not (config.DATA_DIR / "jobs" / str(j)).exists()
    assert db.q1("SELECT project_id, user_id FROM jobs WHERE id=?", (j_l_in_priv,)) == {"project_id": None, "user_id": L.uid}
    assert db.q1("SELECT user_id, team_id FROM projects WHERE id=?", (tp,)) == {"user_id": None, "team_id": tid}
    assert db.q1("SELECT user_id, project_id FROM jobs WHERE id=?", (j_team,)) == {"user_id": None, "project_id": tp}
    assert db.q1("SELECT COUNT(*) n FROM team_members WHERE user_id=?", (M.uid,))["n"] == 0
    assert db.q1("SELECT COUNT(*) n FROM team_invites WHERE user_id=?", (M.uid,))["n"] == 0
    e = next(p for p in L.get(f"/api/projects?scope=team:{tid}").json() if p["id"] == tp)
    assert e["creator"] is None and e["creator_is_member"] is False
    assert "1 Team-Projekt bleibt" in _last_audit("user_deleted")["detail"]


def test_benutzer_leiter_nachfolge(app, admin):
    from app import db
    L, A1, A2, B = _mk(app, admin, "blleiter", "blaelt", "bljung", "blzweit")
    erbe = _team("Erbe", {L.uid: "leiter", A1.uid: "mitglied", A2.uid: "lesend"})
    zwei = _team("Zwei Leiter", {L.uid: "leiter", B.uid: "leiter", A1.uid: "mitglied"})
    solo = _team("Allein", {L.uid: "leiter"})                                  # ohne Projekte: wird mit geloescht
    rest = _team("Allein mit Projekt", {L.uid: "leiter"})
    _project(L.uid, rest)
    assert admin.delete(f"/api/admin/users/{L.uid}", headers=H).status_code == 200
    roles = {r["user_id"]: r["role"] for r in db.q("SELECT user_id, role FROM team_members WHERE team_id=?", (erbe,))}
    assert roles == {A1.uid: "leiter", A2.uid: "lesend"}                       # aeltestes verbleibendes Mitglied
    roles2 = {r["user_id"]: r["role"] for r in db.q("SELECT user_id, role FROM team_members WHERE team_id=?", (zwei,))}
    assert roles2 == {B.uid: "leiter", A1.uid: "mitglied"}                     # anderer Leiter da: keine Nachfolge
    autos = db.q("SELECT detail FROM audit WHERE action='team_leader_auto' AND detail LIKE ?",
                 (f"%(Nachfolge für {L.username})",))
    assert [a["detail"] for a in autos] == [f"Team {erbe} „Erbe“: {A1.username} ist jetzt Leiter (Nachfolge für {L.username})"]
    assert db.q1("SELECT id FROM teams WHERE id=?", (solo,)) is None           # leer und ohne Projekte: geloescht
    assert db.q1("SELECT detail FROM audit WHERE action='team_deleted' AND detail LIKE ?", (f"Team {solo} %",))["detail"] \
        == f"Team {solo} „Allein“ gelöscht (letztes Mitglied {L.username} gelöscht, 0 Projekte)"
    assert db.q1("SELECT id FROM teams WHERE id=?", (rest,))                   # ohne Mitglieder, mit Projekt: bleibt
    assert next(t for t in admin.get("/api/admin/teams").json() if t["id"] == rest)["no_leader"] is True


def test_benutzer_auftragsliste_team_filter(app, admin):
    L, M, F = _mk(app, admin, "bfleiter", "bfmitgl", "bfaussen")
    tid = _team("Filter", {L.uid: "leiter", M.uid: "mitglied"})
    tp = _project(L.uid, tid)
    jl, jm = _job(L.uid, tp), _job(M.uid, tp)
    jo = _job(M.uid, None)
    rows = M.get(f"/api/jobs?team={tid}").json()
    assert [(r["id"], r["username"]) for r in rows] == [(jm, M.username), (jl, L.username)]
    assert F.get(f"/api/jobs?team={tid}").status_code == 404
    assert [r["id"] for r in M.get("/api/jobs").json()] == [jo, jm]             # „Meine“ = selbst angelegt
    for bad in ("9" * 20, "0"):                                               # Ueberlauf und Unsinn: 422
        assert M.get(f"/api/jobs?team={bad}").status_code == 422


def test_benutzer_auftragsliste_nach_austritt(app, admin):
    """Nach dem Austritt listet „Meine Auftraege“ den eigenen Auftrag im Team-Projekt nicht mehr (Name, Status, Masse)."""
    L, M = _mk(app, admin, "baleiter", "bamitgl")
    tid = _team("Austritt Liste", {L.uid: "leiter", M.uid: "mitglied"})
    jm = _job(M.uid, _project(L.uid, tid))
    jo = _job(M.uid, None)
    assert [j["id"] for j in M.get("/api/jobs").json()] == [jo, jm]
    assert L.delete(f"/api/teams/{tid}/members/{M.uid}", headers=H).status_code == 200
    assert [j["id"] for j in M.get("/api/jobs").json()] == [jo]
    assert M.get(f"/api/jobs/{jm}").status_code == 404


def test_benutzer_startup_raeumt_waisen(app, admin):
    """Start: Auftraege ohne Ersteller und ohne Projekt sowie Fotoordner ohne Zeile werden entfernt (Lueckenfuellung 22)."""
    import inspect

    from app import config, db, main, projects
    (L,) = _mk(app, admin, "bwaise")
    waise, bleibt = _job(None, None), _job(L.uid, None)
    ohne_zeile = config.DATA_DIR / "photos" / "987654321"
    ohne_zeile.mkdir(parents=True, exist_ok=True)
    (ohne_zeile / "thumb.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    mit_zeile = _photo(_project(L.uid))
    projects.sweep()
    assert db.q1("SELECT id FROM jobs WHERE id=?", (waise,)) is None
    assert not (config.DATA_DIR / "jobs" / str(waise)).exists()
    assert db.q1("SELECT id FROM jobs WHERE id=?", (bleibt,))
    assert not ohne_zeile.exists() and (config.DATA_DIR / "photos" / str(mit_zeile)).is_dir()
    assert "projects.sweep()" in inspect.getsource(main._startup)
