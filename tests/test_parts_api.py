"""Teile und Massstab ueber die API (Spec 2026-10-14-kanten-und-teile §3, §7)."""
import sqlite3

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
