"""Laufzeit-Einstellungen: Umgebungsvariable hat Vorrang, sonst Wert aus der Datenbank."""
from __future__ import annotations

from . import config, db


def get(key: str) -> str | None:
    r = db.q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else None


def put(key: str, value: str | None, user_id: int | None = None):
    if value is None:
        db.ex("DELETE FROM settings WHERE key=?", (key,))
    else:
        db.ex("""INSERT INTO settings(key,value,updated_at,updated_by) VALUES (?,?,?,?)
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at,
                 updated_by=excluded.updated_by""", (key, value, db.now(), user_id))


def api_key() -> str:
    return config.ANTHROPIC_API_KEY or (get("anthropic_api_key") or "")


def api_key_source() -> str:
    """env | db | none"""
    if config.ANTHROPIC_API_KEY:
        return "env"
    return "db" if get("anthropic_api_key") else "none"


def api_key_hint() -> str | None:
    k = api_key()
    return f"…{k[-4:]}" if len(k) >= 12 else None


def model() -> str:
    return config.ANTHROPIC_MODEL or get("anthropic_model") or config.DEFAULT_MODEL


def model_source() -> str:
    if config.ANTHROPIC_MODEL:
        return "env"
    return "db" if get("anthropic_model") else "default"


def ai_enabled() -> bool:
    return config.AI_FAKE or bool(api_key())
