"""Teams mit gemeinsamen Bibliotheken (Spec 2026-10-16, T1–T8)."""
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
