"""Benutzer, Sitzungen, Einladungen, Passwort-Regeln."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response

from . import config, db

PH = PasswordHasher()
COOKIE = "mu_session"
ROLES = ("user", "admin")

_COMMON = {
    "passwort", "password", "123456789012", "passwort1234", "password1234", "qwertzuiopü", "qwertyuiop12",
    "hallo1234567", "000000000000", "111111111111", "123456123456", "letmein12345", "admin1234567",
    "administrator", "messunterlage", "snap2cad1234", "willkommen123", "welcome12345", "sommer2024!!", "winter2024!!",
    "iloveyou1234", "abc123abc123", "qwertz123456", "passwort123!", "password123!", "changeme1234",
}


# ---------------------------------------------------------------- Hilfen

def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _future(**kw) -> str:
    return _utc(datetime.now(timezone.utc) + timedelta(**kw))


def _expired(ts: str | None) -> bool:
    if not ts:
        return True
    return datetime.fromisoformat(ts) <= datetime.now(timezone.utc)


def forwarded(request: Request, name: str, default: str) -> str:
    """Erster Eintrag eines X-Forwarded-*-Headers. Bei mehreren Proxys hintereinander (z. B. Cloudflare +
    Synology-Reverse-Proxy) haengt jeder seinen Wert an ("https,http"); der erste ist der des Browsers."""
    v = (request.headers.get(name) or "").split(",", 1)[0].strip()
    return v or default


def public_proto(request: Request) -> str:
    p = forwarded(request, "x-forwarded-proto", request.url.scheme).lower()
    return p if p in ("http", "https") else request.url.scheme


def public_host(request: Request) -> str:
    return forwarded(request, "x-forwarded-host", request.headers.get("host", "localhost"))


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def hash_pw(pw: str) -> str:
    return PH.hash(pw)


def verify_pw(pw_hash: str | None, pw: str) -> bool:
    if not pw_hash:
        return False
    try:
        return PH.verify(pw_hash, pw)
    except (VerificationError, InvalidHashError):
        return False


_DUMMY_HASH = PH.hash(secrets.token_hex(16))


def check_policy(pw: str, username: str = "", initial_hash: str | None = None) -> list[str]:
    """Liefert eine Liste verletzter Regeln (leer = ok)."""
    problems = []
    if len(pw) < 12:
        problems.append("mindestens 12 Zeichen")
    if len(pw) > 256:
        problems.append("höchstens 256 Zeichen")
    if username and len(username) >= 3 and username.lower() in pw.lower():
        problems.append("darf den Benutzernamen nicht enthalten")
    if pw.lower() in _COMMON or len(set(pw)) < 4:
        problems.append("zu einfach (häufiges Passwort)")
    if initial_hash and verify_pw(initial_hash, pw):
        problems.append("darf nicht das Initialpasswort sein")
    return problems


def public_user(u: dict) -> dict:
    return {k: u.get(k) for k in ("id", "username", "email", "display_name", "role", "status",
                                  "must_change_pw", "cad_quota", "created_at", "last_login")}


def quota_of(u: dict) -> int | None:
    """None = unbegrenzt."""
    if u.get("cad_quota") is not None:
        return None if u["cad_quota"] < 0 else u["cad_quota"]
    if u.get("role") == "admin":
        return None
    d = str(config.DEFAULT_QUOTA).strip().lower()
    if d in ("", "0", "none", "unbegrenzt", "-1"):
        return None if d != "0" else 0
    try:
        return int(d)
    except ValueError:
        return 20


def usage_this_month(user_id: int) -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    r = db.q1("""SELECT COUNT(*) n FROM job_versions v JOIN jobs j ON j.id=v.job_id
                 WHERE j.user_id=? AND v.trigger IN ('create','iterate') AND substr(v.created_at,1,7)=?""",
              (user_id, month))
    return r["n"] if r else 0


# ---------------------------------------------------------------- Ersteinrichtung

def ensure_admin():
    """Nur fuer automatisierte Installationen (ADMIN_INITIAL_PASSWORD gesetzt): Konto 'admin' anlegen.
    Ohne die Variable bleibt die Datenbank leer und der Einrichtungsassistent im Browser legt das erste
    Admin-Konto an."""
    if not config.ADMIN_INITIAL_PASSWORD or db.q1("SELECT id FROM users LIMIT 1"):
        return
    h = hash_pw(config.ADMIN_INITIAL_PASSWORD)
    db.ex("""INSERT INTO users(username,display_name,pw_hash,role,status,must_change_pw,initial_pw_hash,created_at)
             VALUES ('admin','Administrator',?,'admin','active',1,?,?)""", (h, h, db.now()))
    db.audit("admin_created", "Konto „admin“ aus ADMIN_INITIAL_PASSWORD angelegt", actor="system")
    print("Admin-Konto 'admin' aus ADMIN_INITIAL_PASSWORD angelegt (Passwort muss beim ersten Login geändert werden).",
          flush=True)


def setup_required() -> bool:
    return db.q1("SELECT id FROM users LIMIT 1") is None


def setup_ip_allowed(ip: str) -> bool:
    if config.SETUP_ALLOW_PUBLIC:
        return True
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    # alles, was nicht aus dem oeffentlichen Internet kommt: LAN, Loopback, Docker, VPN/CGNAT (Tailscale)
    return not a.is_global and not a.is_multicast and not a.is_unspecified


def check_username(username: str):
    if not (3 <= len(username) <= 32) or not set(username.lower()) <= USERNAME_OK:
        raise HTTPException(400, "Benutzername: 3–32 Zeichen, nur Buchstaben a–z, Ziffern, Punkt, Minus, Unterstrich.")


def create_first_admin(username: str, display_name: str, email: str | None, password: str, ip: str) -> dict:
    """Legt das erste Konto an – nur solange noch kein Benutzer existiert (atomar gegen parallele Aufrufe)."""
    with db._lock:
        if not setup_required():
            raise HTTPException(409, "Snap2CAD ist bereits eingerichtet. Bitte anmelden.")
        uid = db.ex("""INSERT INTO users(username,email,display_name,pw_hash,role,status,must_change_pw,created_at)
                       VALUES (?,?,?,?,'admin','active',0,?)""",
                    (username, email, (display_name or "").strip()[:80] or username, hash_pw(password), db.now()))
    db.audit("setup", f"Ersteinrichtung: Administrator „{username}“ angelegt", user_id=uid, actor=username, ip=ip)
    return db.q1("SELECT * FROM users WHERE id=?", (uid,))


# ---------------------------------------------------------------- Login-Sperre

class _Limiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.fails: dict[str, list[float]] = {}
        self.locked: dict[str, float] = {}

    def _key(self, username, ip):
        return f"{username.lower()}|{ip}"

    def locked_for(self, username, ip) -> int:
        with self.lock:
            for k in (self._key(username, ip), f"*|{ip}", f"{username.lower()}|*"):
                until = self.locked.get(k, 0)
                if until > time.time():
                    return int(until - time.time()) + 1
        return 0

    def fail(self, username, ip):
        now = time.time()
        window = config.LOGIN_LOCK_MINUTES * 60
        with self.lock:
            # je Konto+IP, je IP und je Konto ueber alle IPs (gegen gefaelschte/rotierende Adressen)
            for k, limit in ((self._key(username, ip), config.LOGIN_MAX_FAILS),
                             (f"*|{ip}", config.LOGIN_MAX_FAILS * 6),
                             (f"{username.lower()}|*", config.LOGIN_MAX_FAILS * 4)):
                lst = [t for t in self.fails.get(k, []) if now - t < window] + [now]
                self.fails[k] = lst
                if len(lst) >= limit:
                    self.locked[k] = now + window
                    self.fails[k] = []

    def remaining(self, username, ip) -> int:
        if self.locked_for(username, ip):
            return 0
        with self.lock:
            return config.LOGIN_MAX_FAILS - len(self.fails.get(self._key(username, ip), []))

    def ok(self, username, ip):
        with self.lock:
            self.fails.pop(self._key(username, ip), None)


LIMITER = _Limiter()


# ---------------------------------------------------------------- Sitzungen

def _secure(request: Request) -> bool:
    if config.COOKIE_SECURE == "true":
        return True
    if config.COOKIE_SECURE == "false":
        return False
    return public_proto(request) == "https"


def create_session(response: Response, request: Request, user: dict, remember: bool):
    token = secrets.token_urlsafe(32)
    life = timedelta(days=config.SESSION_DAYS) if remember else timedelta(hours=config.SESSION_HOURS_SHORT)
    expires = datetime.now(timezone.utc) + life
    db.ex("INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen,ip,ua) VALUES (?,?,?,?,?,?,?)",
          (_sha(token), user["id"], db.now(), _utc(expires), db.now(), client_ip(request),
           (request.headers.get("user-agent") or "")[:200]))
    response.set_cookie(COOKIE, token, max_age=int(life.total_seconds()) if remember else None,
                        httponly=True, samesite="lax", secure=_secure(request), path="/")


def destroy_session(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        db.ex("DELETE FROM sessions WHERE token_hash=?", (_sha(token),))
    response.delete_cookie(COOKIE, path="/")


def end_sessions(user_id: int, keep_token: str | None = None):
    if keep_token:
        db.ex("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, _sha(keep_token)))
    else:
        db.ex("DELETE FROM sessions WHERE user_id=?", (user_id,))


def purge_expired():
    db.ex("DELETE FROM sessions WHERE expires_at<=?", (db.now(),))


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    s = db.q1("SELECT * FROM sessions WHERE token_hash=?", (_sha(token),))
    if not s or _expired(s["expires_at"]):
        return None
    u = db.q1("SELECT * FROM users WHERE id=?", (s["user_id"],))
    if not u or u["status"] != "active":
        return None
    # last_seen hoechstens einmal pro Minute schreiben
    if not s["last_seen"] or (datetime.now(timezone.utc) - datetime.fromisoformat(s["last_seen"])).total_seconds() > 60:
        db.ex("UPDATE sessions SET last_seen=? WHERE token_hash=?", (db.now(), s["token_hash"]))
    request.state.user = u
    return u


def optional_user(request: Request) -> dict | None:
    return current_user(request)


def require_login(request: Request) -> dict:
    """Angemeldet, auch wenn das Passwort noch geaendert werden muss."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Nicht angemeldet")
    return u


def require_user(u: dict = Depends(require_login)) -> dict:
    if u["must_change_pw"]:
        raise HTTPException(403, "Passwort muss zuerst geändert werden")
    return u


def require_admin(u: dict = Depends(require_user)) -> dict:
    if u["role"] != "admin":
        raise HTTPException(403, "Nur für Administratoren")
    return u


# ---------------------------------------------------------------- Login

def login(username: str, password: str, ip: str) -> dict:
    username = (username or "").strip()
    wait = LIMITER.locked_for(username, ip)
    if wait:
        raise HTTPException(429, f"Zu viele Fehlversuche. Bitte in {max(1, wait // 60)} Minuten erneut versuchen.")
    u = db.q1("SELECT * FROM users WHERE username=?", (username,))
    if not u and "@" in username:
        u = db.q1("SELECT * FROM users WHERE email=?", (username,))
    if u:
        ok = verify_pw(u["pw_hash"], password)
    else:
        verify_pw(_DUMMY_HASH, password)  # gleiche Laufzeit, kein Hinweis auf existierende Namen
        ok = False
    if not u or not ok or u["status"] != "active":
        LIMITER.fail(username, ip)
        db.audit("login_failed", f"Benutzer „{username[:60]}“", user_id=u["id"] if u else None,
                 actor=username[:60], ip=ip)
        if u and ok and u["status"] != "active":
            raise HTTPException(403, "Dieses Konto ist gesperrt.")
        left = LIMITER.remaining(username, ip)
        if left <= 0:
            raise HTTPException(429, f"Zu viele Fehlversuche. Anmeldung für {config.LOGIN_LOCK_MINUTES} Minuten gesperrt.")
        hint = f" Nach {left} weiteren Fehlversuch{'en' if left != 1 else ''} wird die Anmeldung für " \
               f"{config.LOGIN_LOCK_MINUTES} Minuten gesperrt." if left <= 3 else ""
        raise HTTPException(401, "Benutzername oder Passwort falsch." + hint)
    LIMITER.ok(username, ip)
    if PH.check_needs_rehash(u["pw_hash"]):
        db.ex("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(password), u["id"]))
    db.ex("UPDATE users SET last_login=? WHERE id=?", (db.now(), u["id"]))
    db.audit("login", "", user_id=u["id"], actor=u["username"], ip=ip)
    return u


def change_password(u: dict, current: str, new: str, ip: str, keep_token: str | None):
    if not verify_pw(u["pw_hash"], current):
        db.audit("pw_change_failed", "aktuelles Passwort falsch", user_id=u["id"], actor=u["username"], ip=ip)
        raise HTTPException(400, "Das aktuelle Passwort ist falsch.")
    problems = check_policy(new, u["username"], u["initial_pw_hash"])
    if verify_pw(u["pw_hash"], new):
        problems.append("muss sich vom bisherigen Passwort unterscheiden")
    if problems:
        raise HTTPException(400, "Passwort: " + ", ".join(problems) + ".")
    db.ex("UPDATE users SET pw_hash=?, must_change_pw=0, initial_pw_hash=NULL WHERE id=?", (hash_pw(new), u["id"]))
    end_sessions(u["id"], keep_token)
    db.audit("pw_changed", "", user_id=u["id"], actor=u["username"], ip=ip)


# ---------------------------------------------------------------- Einladungen & Zuruecksetzen

def link(kind: str, token: str, request: Request | None = None) -> str:
    base = config.PUBLIC_URL
    if not base and request is not None:
        base = f"{public_proto(request)}://{public_host(request)}"
    return f"{base}/{kind}/{token}"


def create_invite(admin: dict, email: str | None, role: str, quota: int | None, days: int) -> tuple[dict, str]:
    if role not in ROLES:
        raise HTTPException(400, "Unbekannte Rolle")
    days = max(1, min(int(days or 7), 30))
    email = clean_email(email)
    if email and db.q1("SELECT id FROM users WHERE email=?", (email,)):
        raise HTTPException(400, "Für diese E-Mail-Adresse gibt es bereits ein Konto.")
    token = secrets.token_urlsafe(24)
    iid = db.ex("""INSERT INTO invites(token_hash,email,role,cad_quota,created_by,created_at,expires_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (_sha(token), email, role, quota, admin["id"], db.now(), _future(days=days)))
    db.audit("invite_created", f"{email or 'ohne E-Mail'} · {role} · {days} Tage", user_id=admin["id"],
             actor=admin["username"])
    return db.q1("SELECT * FROM invites WHERE id=?", (iid,)), token


def invite_state(inv: dict) -> str:
    if inv["revoked_at"]:
        return "widerrufen"
    if inv["used_at"]:
        return "angenommen"
    if _expired(inv["expires_at"]):
        return "abgelaufen"
    return "offen"


def find_invite(token: str) -> dict:
    inv = db.q1("SELECT * FROM invites WHERE token_hash=?", (_sha(token or ""),))
    if not inv or invite_state(inv) != "offen":
        raise HTTPException(404, "Diese Einladung ist ungültig, abgelaufen oder wurde bereits verwendet.")
    return inv


USERNAME_OK = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def clean_email(e: str | None) -> str | None:
    """Leer -> None; sonst muss es wie eine E-Mail-Adresse aussehen."""
    e = (e or "").strip()
    if not e:
        return None
    if len(e) > 200 or not _EMAIL.match(e):
        raise HTTPException(400, "Bitte eine gültige E-Mail-Adresse eingeben.")
    return e


def accept_invite(token: str, username: str, display_name: str, email: str | None, password: str,
                  ip: str) -> dict:
    inv = find_invite(token)
    username = (username or "").strip()
    check_username(username)
    if db.q1("SELECT id FROM users WHERE username=?", (username,)):
        raise HTTPException(400, "Dieser Benutzername ist vergeben.")
    email = inv["email"] or clean_email(email)
    if email and db.q1("SELECT id FROM users WHERE email=?", (email,)):
        raise HTTPException(400, "Für diese E-Mail-Adresse gibt es bereits ein Konto.")
    problems = check_policy(password, username)
    if problems:
        raise HTTPException(400, "Passwort: " + ", ".join(problems) + ".")
    with db._lock:  # Einladung atomar verbrauchen
        fresh = db.q1("SELECT used_at, revoked_at FROM invites WHERE id=?", (inv["id"],))
        if fresh["used_at"] or fresh["revoked_at"]:
            raise HTTPException(404, "Diese Einladung wurde bereits verwendet.")
        uid = db.ex("""INSERT INTO users(username,email,display_name,pw_hash,role,status,must_change_pw,cad_quota,created_at)
                       VALUES (?,?,?,?,?,'active',0,?,?)""",
                    (username, email, (display_name or "").strip()[:80] or username, hash_pw(password), inv["role"],
                     inv["cad_quota"], db.now()))
        db.ex("UPDATE invites SET used_at=?, used_by=? WHERE id=?", (db.now(), uid, inv["id"]))
    db.audit("invite_accepted", f"Konto „{username}“ angelegt", user_id=uid, actor=username, ip=ip)
    return db.q1("SELECT * FROM users WHERE id=?", (uid,))


def create_reset(admin: dict | None, user: dict) -> str:
    """admin=None: von der Kommandozeile im Container erstellt (Notfallzugang)."""
    token = secrets.token_urlsafe(24)
    db.ex("UPDATE resets SET used_at=? WHERE user_id=? AND used_at IS NULL", (db.now(), user["id"]))
    db.ex("INSERT INTO resets(token_hash,user_id,created_by,created_at,expires_at) VALUES (?,?,?,?,?)",
          (_sha(token), user["id"], admin["id"] if admin else None, db.now(), _future(hours=48)))
    db.audit("reset_created", f"für „{user['username']}“" + ("" if admin else " (Kommandozeile)"),
             user_id=admin["id"] if admin else user["id"], actor=admin["username"] if admin else "konsole")
    return token


def find_reset(token: str) -> tuple[dict, dict]:
    r = db.q1("SELECT * FROM resets WHERE token_hash=?", (_sha(token or ""),))
    if not r or r["used_at"] or _expired(r["expires_at"]):
        raise HTTPException(404, "Dieser Link ist ungültig oder abgelaufen.")
    u = db.q1("SELECT * FROM users WHERE id=?", (r["user_id"],))
    if not u or u["status"] != "active":
        raise HTTPException(404, "Dieser Link ist ungültig oder abgelaufen.")
    return r, u


def use_reset(token: str, password: str, ip: str) -> dict:
    r, u = find_reset(token)
    problems = check_policy(password, u["username"], u["initial_pw_hash"])
    if problems:
        raise HTTPException(400, "Passwort: " + ", ".join(problems) + ".")
    db.tx([("UPDATE users SET pw_hash=?, must_change_pw=0, initial_pw_hash=NULL WHERE id=?", (hash_pw(password), u["id"])),
           ("UPDATE resets SET used_at=? WHERE id=?", (db.now(), r["id"])),
           ("DELETE FROM sessions WHERE user_id=?", (u["id"],))])
    db.audit("pw_reset", "über Link", user_id=u["id"], actor=u["username"], ip=ip)
    return db.q1("SELECT * FROM users WHERE id=?", (u["id"],))


def active_admins() -> int:
    return db.q1("SELECT COUNT(*) n FROM users WHERE role='admin' AND status='active'")["n"]
