"""Einstellungen aus Umgebungsvariablen."""
import os
from pathlib import Path


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
RUNS_DIR = Path(os.environ.get("RUNS_DIR", "/runs"))
DB_PATH = DATA_DIR / "snap2cad.db"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip()
AI_FAKE = os.environ.get("AI_FAKE", "") == "1"  # nur fuer Entwicklung/Tests

ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "auto").lower()  # auto | true | false
SESSION_DAYS = _int("SESSION_DAYS", 30)
SESSION_HOURS_SHORT = _int("SESSION_HOURS_SHORT", 12)

SANDBOX_MODE = os.environ.get("SANDBOX_MODE", "worker").lower()  # worker | local
SANDBOX_TIMEOUT = _int("SANDBOX_TIMEOUT", 120)
SANDBOX_MEM_MB = _int("SANDBOX_MEM_MB", 3072)
SANDBOX_WORKERS = _int("SANDBOX_WORKERS", 2)
SANDBOX_UID = _int("SANDBOX_UID", 10002)
APP_UID = _int("APP_UID", 10001)
MAX_AUTOFIX = _int("MAX_AUTOFIX", 2)
MAX_CONCURRENT_JOBS = _int("MAX_CONCURRENT_JOBS", 2)
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 25)
DEFAULT_QUOTA = os.environ.get("DEFAULT_QUOTA", "20")

LOGIN_MAX_FAILS = 5
LOGIN_LOCK_MINUTES = 15

RUNNER = Path(__file__).resolve().parent / "runner" / "cad_runner.py"
ROOT = Path(__file__).resolve().parents[2]  # Repo-/Image-Wurzel (enthaelt core/, PROMPT.md)


def ai_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY) or AI_FAKE
