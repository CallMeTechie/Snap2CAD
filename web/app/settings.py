"""Laufzeit-Einstellungen: Umgebungsvariable hat Vorrang, sonst Wert aus der Datenbank.

Geheime Werte (der API-Schluessel) werden verschluesselt gespeichert, wenn SECRET_KEY gesetzt ist. Der
Hauptschluessel liegt dann ausserhalb des Daten-Volumes; eine Kopie der Datenbank allein verraet nichts."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from . import config, db

SECRET = ("anthropic_api_key",)
_PREFIX = "enc:v1:"


def _fernet() -> Fernet | None:
    if not config.SECRET_KEY:
        return None
    k = hashlib.sha256(b"snap2cad-settings-v1:" + config.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(k))


def _raw(key: str) -> str | None:
    r = db.q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else None


def get(key: str) -> str | None:
    """Klartext; None, wenn nicht gesetzt oder nicht entschluesselbar (SECRET_KEY fehlt oder falsch)."""
    v = _raw(key)
    if v is None or not v.startswith(_PREFIX):
        return v
    f = _fernet()
    if not f:
        return None
    try:
        return f.decrypt(v[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return None


def put(key: str, value: str | None, user_id: int | None = None):
    if value is None:
        db.ex("DELETE FROM settings WHERE key=?", (key,))
        return
    f = _fernet() if key in SECRET else None
    if f:
        value = _PREFIX + f.encrypt(value.encode()).decode()
    db.ex("""INSERT INTO settings(key,value,updated_at,updated_by) VALUES (?,?,?,?)
             ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at,
             updated_by=excluded.updated_by""", (key, value, db.now(), user_id))


def check_secret_key():
    """Beim Start: zu kurzer Hauptschluessel ist ein Konfigurationsfehler."""
    if config.SECRET_KEY and len(config.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY ist zu kurz (mindestens 32 Zeichen, z. B. aus `openssl rand -base64 48`).")


def encrypt_stored() -> int:
    """Beim Start: unverschluesselt gespeicherte Geheimnisse verschluesseln, sobald SECRET_KEY gesetzt ist."""
    if not _fernet():
        return 0
    n = 0
    for key in SECRET:
        v = _raw(key)
        if v is not None and not v.startswith(_PREFIX):
            r = db.q1("SELECT updated_by FROM settings WHERE key=?", (key,))
            put(key, v, r["updated_by"] if r else None)
            n += 1
    return n


def api_key() -> str:
    return config.ANTHROPIC_API_KEY or (get("anthropic_api_key") or "")


def api_key_source() -> str:
    """env | db | locked (gespeichert, aber nicht entschluesselbar) | none"""
    if config.ANTHROPIC_API_KEY:
        return "env"
    if get("anthropic_api_key"):
        return "db"
    return "locked" if _raw("anthropic_api_key") else "none"


def api_key_encrypted() -> bool:
    return (_raw("anthropic_api_key") or "").startswith(_PREFIX)


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
