"""SQLite-Datenbank (eine Datei im Daten-Volume)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

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
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, created_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
  ctrl_x REAL, ctrl_y REAL
);
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
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  name TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL,
  messages TEXT NOT NULL DEFAULT '[]', current_version INTEGER, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, trigger TEXT NOT NULL, request_text TEXT,
  code TEXT, claude_text TEXT, meta TEXT, status TEXT NOT NULL,
  error TEXT, result TEXT, checks TEXT, usage TEXT, seconds REAL, created_at TEXT NOT NULL,
  UNIQUE(job_id, version)
);
CREATE TABLE IF NOT EXISTS job_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'info', msg TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_photos_project ON photos(project_id);
CREATE INDEX IF NOT EXISTS ix_meas_project ON measurements(project_id);
CREATE INDEX IF NOT EXISTS ix_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS ix_log_job ON job_log(job_id);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(config.DB_PATH, check_same_thread=False, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=5000")
        c.executescript(SCHEMA)
        _conn = c
    return _conn


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
