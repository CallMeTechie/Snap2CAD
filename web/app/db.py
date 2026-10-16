"""SQLite-Datenbank (eine Datei im Daten-Volume)."""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

# Teams (Spec Teams §1): neue Tabellen; auf Bestandsdatenbanken legt sie die Umbau-Transaktion an
TEAMS_DDL = """
CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS team_members (
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('leiter','mitglied','lesend')), joined_at TEXT NOT NULL,
  PRIMARY KEY (team_id, user_id));
CREATE TABLE IF NOT EXISTS team_invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('leiter','mitglied','lesend')),
  invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen','angenommen','abgelehnt','zurueckgezogen')),
  decided_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_team_invite_open ON team_invites(team_id, user_id) WHERE status='offen';
CREATE INDEX IF NOT EXISTS ix_team_members_user ON team_members(user_id);
"""
# Feste neue Definitionen: dieselben Konstanten in SCHEMA und im Neuaufbau (_rebuild_table)
PROJECTS_DDL = """CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  name TEXT NOT NULL, created_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
  ctrl_x REAL, ctrl_y REAL,
  color TEXT, material TEXT, transparent INTEGER, finish TEXT, material_user INTEGER NOT NULL DEFAULT 0, cad_check TEXT,
  team_id INTEGER REFERENCES teams(id)
)"""
JOBS_DDL = """CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  name TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL,
  messages TEXT NOT NULL DEFAULT '[]', current_version INTEGER, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  run_by INTEGER REFERENCES users(id) ON DELETE SET NULL
)"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  email TEXT UNIQUE COLLATE NOCASE,
  display_name TEXT,
  pw_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'active',
  must_change_pw INTEGER NOT NULL DEFAULT 0,
  initial_pw_hash TEXT,
  cad_quota INTEGER,
  created_at TEXT NOT NULL,
  last_login TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen TEXT, ip TEXT, ua TEXT
);
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  email TEXT, role TEXT NOT NULL DEFAULT 'user', cad_quota INTEGER,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  used_at TEXT, used_by INTEGER REFERENCES users(id) ON DELETE SET NULL, revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS resets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_by INTEGER, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id INTEGER, actor TEXT, action TEXT NOT NULL,
  detail TEXT, ip TEXT
);
""" + TEAMS_DDL + PROJECTS_DDL + """;
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT, view TEXT NOT NULL DEFAULT 'top', format TEXT, status TEXT, max_err REAL,
  analysis TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER REFERENCES photos(id) ON DELETE SET NULL,
  seq INTEGER NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL,
  value REAL, unit TEXT NOT NULL DEFAULT 'mm', unc REAL, data TEXT,
  critical INTEGER NOT NULL DEFAULT 0, caliper REAL, fit TEXT,
  source TEXT NOT NULL DEFAULT 'user', accepted INTEGER NOT NULL DEFAULT 1, reason TEXT,
  created_at TEXT NOT NULL
);
""" + JOBS_DDL + """;
CREATE TABLE IF NOT EXISTS job_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, trigger TEXT NOT NULL, request_text TEXT,
  code TEXT, claude_text TEXT, meta TEXT, status TEXT NOT NULL,
  error TEXT, result TEXT, checks TEXT, usage TEXT, seconds REAL, created_at TEXT NOT NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  UNIQUE(job_id, version)
);
CREATE TABLE IF NOT EXISTS job_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'info', msg TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT, updated_at TEXT NOT NULL, updated_by INTEGER
);
CREATE TABLE IF NOT EXISTS parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, label TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'body',
  data TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'auto',
  scale REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_dims(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label TEXT NOT NULL, label_norm TEXT NOT NULL,
  grp TEXT NOT NULL, value REAL NOT NULL, job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL, dim_id TEXT,
  note TEXT, created_at TEXT NOT NULL,
  UNIQUE(project_id, label_norm));
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_photos_project ON photos(project_id);
CREATE INDEX IF NOT EXISTS ix_meas_project ON measurements(project_id);
CREATE INDEX IF NOT EXISTS ix_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS ix_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS ix_log_job ON job_log(job_id);
CREATE INDEX IF NOT EXISTS ix_parts_photo ON parts(photo_id);
"""
REBUILD = (("projects", PROJECTS_DDL), ("jobs", JOBS_DDL))

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = _open(config.DB_PATH)
    return _conn


def _open(path, factory=sqlite3.Connection) -> sqlite3.Connection:
    """Verbindung mit Schema und Migration; bei einer Ausnahme geschlossen und weitergegeben (der Start bricht ab)."""
    c = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, factory=factory)
    try:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=5000")
        if not _legacy(c):   # neue oder umgebaute Datenbank; im Bestand laeuft SCHEMA in der Umbau-Transaktion
            c.executescript(SCHEMA)
        _migrate(c)
    except BaseException:
        c.close()
        raise
    return c


def _legacy(c: sqlite3.Connection) -> bool:
    cols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    return bool(cols) and "team_id" not in cols


def _statements(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


def _migrate(c: sqlite3.Connection):
    """(a) Spalten nachruesten, (b) einmaliger Neuaufbau fuer Teams, (d) Indizes bei jedem Start (Spec Teams §1)."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(measurements)").fetchall()}
    if "part_id" not in cols:
        c.execute("ALTER TABLE measurements ADD COLUMN part_id INTEGER REFERENCES parts(id) ON DELETE SET NULL")
    c.execute("CREATE INDEX IF NOT EXISTS ix_meas_part ON measurements(part_id)")
    pcols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
    for col, typ in (("color", "TEXT"), ("material", "TEXT"), ("transparent", "INTEGER"), ("finish", "TEXT"),
                     ("material_user", "INTEGER NOT NULL DEFAULT 0"), ("cad_check", "TEXT")):
        if col not in pcols:
            c.execute(f"ALTER TABLE projects ADD COLUMN {col} {typ}")
    if "team_id" not in pcols:
        _rebuild_for_teams(c)
    c.execute("CREATE INDEX IF NOT EXISTS ix_projects_team ON projects(team_id)")   # nicht in SCHEMA: Bestand
    c.execute("CREATE INDEX IF NOT EXISTS ix_projects_user ON projects(user_id)")


def _fk_issues(c: sqlite3.Connection) -> Counter:
    """Verstoesse als (table, rowid, parent) – nicht fkid, das sich durch den neuen Fremdschluessel verschiebt."""
    return Counter((r[0], r[1], r[2]) for r in c.execute("PRAGMA foreign_key_check").fetchall())


def _rebuild_table(c: sqlite3.Connection, name: str, ddl: str):
    old = [r[1] for r in c.execute(f"PRAGMA table_info({name})").fetchall()]
    new_ddl = ddl.replace(f"CREATE TABLE IF NOT EXISTS {name} (", f"CREATE TABLE {name}_new (", 1)
    if f"CREATE TABLE {name}_new (" not in new_ddl:
        raise RuntimeError(f"Migration abgebrochen: keine feste Definition für {name}")
    c.execute(new_ddl)
    new = {r[1] for r in c.execute(f"PRAGMA table_info({name}_new)").fetchall()}
    unknown = [x for x in old if x not in new]
    if unknown:
        raise RuntimeError(f"Migration abgebrochen: {name}_new kennt die Spalte(n) {', '.join(unknown)} nicht")
    cols = ", ".join(f'"{x}"' for x in old)
    c.execute(f"INSERT INTO {name}_new ({cols}) SELECT {cols} FROM {name}")
    c.execute(f"DROP TABLE {name}")
    c.execute(f"ALTER TABLE {name}_new RENAME TO {name}")


def _rebuild_for_teams(c: sqlite3.Connection):
    """Spec Teams §1 (b)/(c): Neuaufbau von projects und jobs in einer Transaktion; Abbruch rollt alles zurueck."""
    c.execute("PRAGMA foreign_keys=OFF")          # ausserhalb einer Transaktion, sonst wirkungslos
    done = False
    try:
        before = _fk_issues(c)
        seq = {r[0]: r[1] for r in c.execute("SELECT name, seq FROM sqlite_sequence WHERE name IN ('projects','jobs')")}
        c.execute("BEGIN")
        try:
            for stmt in _statements(SCHEMA):        # Team-Tabellen in derselben Transaktion (ROLLBACK entfernt sie)
                c.execute(stmt)
            for name, ddl in REBUILD:
                _rebuild_table(c, name, ddl)
            for name in ("projects", "jobs"):       # sonst MAX(id) bzw. 0: geloeschte ids wuerden wieder vergeben
                c.execute("DELETE FROM sqlite_sequence WHERE name=?", (name,))
                if name in seq:
                    c.execute("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (name, seq[name]))
            vcols = {r[1] for r in c.execute("PRAGMA table_info(job_versions)").fetchall()}
            if "user_id" not in vcols:          # fehlte job_versions ganz, hat SCHEMA sie eben in neuer Form angelegt
                c.execute("ALTER TABLE job_versions ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
            # nur vorhandene Ersteller: ein verwaister jobs.user_id (Altverstoss, F-2) bliebe sonst als neuer Verstoss
            c.execute("UPDATE job_versions SET user_id=(SELECT j.user_id FROM jobs j JOIN users u ON u.id=j.user_id "
                      "WHERE j.id=job_versions.job_id) WHERE user_id IS NULL")
            c.execute("CREATE INDEX IF NOT EXISTS ix_jobs_user ON jobs(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_jobs_project ON jobs(project_id)")
            added = _fk_issues(c) - before
            if added:
                raise RuntimeError(f"Migration abgebrochen: {sum(added.values())} neue Fremdschlüssel-Verstöße, "
                                   f"z. B. {next(iter(added))}")
            c.execute("COMMIT")
        except BaseException as e:
            if c.in_transaction:
                _quiet(c, "ROLLBACK")
            if isinstance(e, Exception) and not str(e).startswith("Migration abgebrochen"):
                raise RuntimeError(f"Migration abgebrochen: {e}") from e
            raise
        done = True
    finally:                                     # (c) erst nach COMMIT/ROLLBACK
        if done:
            c.execute("PRAGMA foreign_keys=ON")
        else:                                    # die urspruengliche Ausnahme bleibt
            _quiet(c, "PRAGMA foreign_keys=ON")


def _quiet(c: sqlite3.Connection, sql: str):
    """Aufraeumen waehrend einer Ausnahme: ein Fehler hier darf die eigentliche Ausnahme nicht ersetzen."""
    try:
        c.execute(sql)
    except sqlite3.Error:
        pass


def q(sql: str, args=()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql: str, args=()) -> dict | None:
    with _lock:
        r = conn().execute(sql, args).fetchone()
        return dict(r) if r else None


def ex(sql: str, args=()) -> int:
    with _lock:
        cur = conn().execute(sql, args)
        return cur.lastrowid


def tx(statements: list[tuple[str, tuple]]):
    with _lock:
        c = conn()
        c.execute("BEGIN")
        try:
            for sql, args in statements:
                c.execute(sql, args)
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise



@contextmanager
def atomic():
    """Mehrere Lese-/Schreibschritte als eine Transaktion. Haelt _lock, damit parallele Anfragen (Threadpool)
    Aenderung + Neuberechnung nicht verschraenken. Verschachtelt = keine Savepoints: eine im inneren Block
    gefangene Ausnahme rollt nichts zurueck. Scheitert COMMIT, wird zurueckgerollt und der Fehler weitergegeben."""
    with _lock:
        c = conn()
        if c.in_transaction:
            yield c
            return
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        try:
            c.execute("COMMIT")
        except BaseException:
            # Gesamtreview S-3: sonst bliebe die Transaktion offen und jedes folgende atomic() liefe verschachtelt
            # ohne eigenes COMMIT; ein Fehler beim ROLLBACK verdeckt die eigentliche Ursache nicht
            try:
                if c.in_transaction:
                    c.execute("ROLLBACK")
            except Exception:
                pass
            raise
def jload(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False)


def audit(action: str, detail: str = "", user_id: int | None = None, actor: str | None = None, ip: str | None = None):
    ex("INSERT INTO audit(ts,user_id,actor,action,detail,ip) VALUES (?,?,?,?,?,?)",
       (now(), user_id, actor, action, detail[:500], ip))
