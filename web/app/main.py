"""Snap2CAD – Web-App (FastAPI)."""
from __future__ import annotations

import io
from contextlib import asynccontextmanager
import json
import os
import shutil
import sys
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import cv2
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import access, ai, auth, check, config, db, geom, jobs, parts, preview, projcopy, projects, sandbox, settings, teams

sys.path.insert(0, str(config.ROOT))
from core import edges, matgen, vision  # noqa: E402

VERSION = os.environ.get("SNAP2CAD_VERSION", "0.1.0")  # im Image vom Git-Tag gesetzt
STATIC = Path(__file__).resolve().parent.parent / "static"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


# ------------------------------------------------------------------ Start

def _startup():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "photos").mkdir(exist_ok=True)
    (config.DATA_DIR / "jobs").mkdir(exist_ok=True)
    settings.check_secret_key()
    db.conn()
    if settings.encrypt_stored():
        db.audit("settings_changed", "API-Schlüssel mit SECRET_KEY verschlüsselt", actor="system")
        print("Gespeicherten API-Schlüssel mit SECRET_KEY verschlüsselt.", flush=True)
    auth.ensure_admin()
    auth.purge_expired()
    jobs.startup()
    projcopy.cleanup_tmp()   # Reste abgebrochener Kopien (Spec Teams §4)
    projects.sweep()   # Auftraege ohne Ersteller und Projekt, Fotoordner ohne Zeile (Plan, Lueckenfuellung 22)
    ki = "Testmodus" if config.AI_FAKE else {"env": "an (Umgebung)", "db": "an", "none": "aus",
                                             "locked": "aus (Schlüssel nicht entschlüsselbar)"}[settings.api_key_source()]
    print(f"Snap2CAD {VERSION} · KI: {ki} · Modell {settings.model()} · Sandbox {config.SANDBOX_MODE}", flush=True)
    if settings.api_key_source() == "locked":
        print("WARNUNG: Der gespeicherte API-Schlüssel lässt sich nicht entschlüsseln – SECRET_KEY fehlt oder ist"
              " falsch. Richtigen SECRET_KEY setzen oder den Schlüssel in der Verwaltung neu eingeben.", flush=True)
    elif settings.api_key_source() == "db" and not settings.api_key_encrypted():
        print("Hinweis: Der API-Schlüssel liegt unverschlüsselt in der Datenbank. SECRET_KEY in der .env setzen,"
              " dann wird er beim nächsten Start verschlüsselt.", flush=True)
    if auth.setup_required():
        print("Noch nicht eingerichtet: Snap2CAD im Browser öffnen – der Einrichtungsassistent legt das erste"
              " Admin-Konto an.", flush=True)


@asynccontextmanager
async def lifespan(_app):
    _startup()
    yield


app = FastAPI(title="Snap2CAD", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(teams.router)   # Teams (Spec Teams §3, §5)


# ------------------------------------------------------------------ Middleware

class BodyLimit:
    """Begrenzt die Groesse jedes Request-Bodys beim Lesen (auch ohne Content-Length / chunked)."""

    def __init__(self, app_, limit: int):
        self.app, self.limit = app_, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total, started = 0, False

        class TooLarge(Exception):
            pass

        async def rcv():
            nonlocal total
            msg = await receive()
            if msg["type"] == "http.request":
                total += len(msg.get("body", b""))
                if total > self.limit:
                    raise TooLarge()
            return msg

        async def snd(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, rcv, snd)
        except TooLarge:
            if not started:
                body = json.dumps({"detail": f"Anfrage zu groß (max. {config.MAX_UPLOAD_MB} MB)"}).encode()
                await send({"type": "http.response.start", "status": 413,
                            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})


app.add_middleware(BodyLimit, limit=(config.MAX_UPLOAD_MB + 1) * 1024 * 1024)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'none'")


@app.middleware("http")
async def security(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and request.method in UNSAFE:
        if request.headers.get("x-requested-with") != "fetch":
            return JSONResponse({"detail": "CSRF-Prüfung fehlgeschlagen"}, status_code=403)
        origin = request.headers.get("origin")
        if origin:
            host = auth.public_host(request)
            if origin.split("://", 1)[-1] != host:
                return JSONResponse({"detail": "Fremde Herkunft abgelehnt"}, status_code=403)
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > (config.MAX_UPLOAD_MB + 1) * 1024 * 1024:
            return JSONResponse({"detail": f"Datei zu groß (max. {config.MAX_UPLOAD_MB} MB)"}, status_code=413)
        # Uploads nur mit gueltiger Sitzung annehmen, bevor der Body gelesen wird
        if path.endswith("/photos") and not auth.current_user(request):
            return JSONResponse({"detail": "Nicht angemeldet"}, status_code=401)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if not path.startswith("/api/mat/preview"):
        resp.headers.setdefault("Content-Security-Policy", CSP)
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    elif path.startswith("/static/"):  # nach einem Update keine alten JS-Module neben neuen (ETag macht es billig)
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


# ------------------------------------------------------------------ Hilfen

def _ascii_name(s: str, fallback: str, n: int = 40) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    t = "".join(c if c.isalnum() or c in "-_" else "_" for c in t).strip("_")[:n]
    return t or fallback


def _disposition(filename: str) -> str:
    from urllib.parse import quote
    ascii_fn = filename.encode("ascii", "ignore").decode().replace('"', "") or "download"
    return f"attachment; filename=\"{ascii_fn}\"; filename*=UTF-8''{quote(filename)}"


def _own_project(pid: int, user: dict, need: str = "write") -> dict:
    """Spec Teams §2: Rechte ueber access (need read | write | delete | move | copy); Standard write."""
    return access.require_project(user, pid, need)


def _own_photo(phid: int, user: dict, need: str = "write") -> tuple[dict, dict]:
    return access.require_photo(user, phid, need)


def _own_meas(mid: int, user: dict, need: str = "write") -> tuple[dict, dict]:
    return access.require_meas(user, mid, need)


def _own_part(part_id: int, user: dict, need: str = "write") -> tuple[dict, dict]:
    return access.require_part(user, part_id, need)


def _refresh(p: dict):
    with db.atomic():
        parts.refresh(p, *_factors(p))


def _own_job(jid: int, user: dict, need: str = "write") -> dict:
    """Auftraege folgen ihrem Projekt (access.require_job); need read | write | delete. Vor jobs.delete aufrufen."""
    return access.require_job(user, jid, need)


def _photo_dir(phid: int) -> Path:
    return projects.photo_dir(phid)   # eine Stelle fuer den Fotoordner (web/app/projects.py)


def _photo_public(ph: dict, hints: dict | None = None) -> dict:
    a = db.jload(ph["analysis"], {}) or {}
    d = _photo_dir(ph["id"])
    has_edges = (d / "edges.json").is_file()
    return {"id": ph["id"], "project_id": ph["project_id"], "filename": ph["filename"], "view": ph["view"],
            "format": ph["format"], "status": ph["status"], "max_err": ph["max_err"], "created_at": ph["created_at"],
            "analysis": {k: a.get(k) for k in ("width", "height", "found_ids", "mat_ids", "missing_ids", "format_auto",
                                               "rms_mm", "loo_mm", "max_err_mm")},
            "gauge": ({k: a["gauge"].get(k) for k in ("strip", "ids", "rms_mm", "vlen_mm")} if a.get("gauge") else None),
            "rect": a.get("rect"), "gauge_rect": a.get("gauge_rect"),
            "files": [n[:-4] for n in ("orig.jpg", "overlay.jpg", "rect.jpg", "gauge.jpg", "thumb.jpg")
                      if (d / n).is_file()],
            "has_edges": has_edges,
            "edges_stale": hints is not None and has_edges and (a.get("edges_hints") or {}) != hints,
            "contrast": a.get("contrast"), "low_contrast": a.get("contrast") is not None and a["contrast"] < 12,
            "bottom_align": a.get("bottom_align") if ph["view"] == "bottom" else None,
            "align_note": a.get("align_note") if ph["view"] == "bottom" else None,
            "bottom_rot_user": a.get("bottom_rot_user")}


def _grid_h(fmt: str | None) -> float | None:
    if fmt not in matgen.FORMATS:
        return None
    return float(vision.spec(fmt)["grid_mm"][1])


def _project_format(pid: int) -> str | None:
    r = db.q1("SELECT format FROM photos WHERE project_id=? AND format IS NOT NULL ORDER BY id LIMIT 1", (pid,))
    return r["format"] if r else None


def _factors(project: dict) -> tuple[float, float]:
    fmt = _project_format(project["id"])
    return geom.factors(project, fmt, _grid_h(fmt))


def _meas_public(m: dict) -> dict:
    out = dict(m)
    out["data"] = db.jload(m["data"], {}) or {}
    out["id_label"] = f"M{m['seq']}"
    return out


def _usage(user: dict) -> dict:
    q = auth.quota_of(user)
    return {"quota": q, "used": auth.usage_this_month(user["id"])}


AI_DAILY_LIMIT = 30
_detect_lock = threading.Semaphore(1)  # nur um den OpenCV-Teil, nicht um den KI-Aufruf (Spec §7)
DETECT_WAIT_S = 30   # so lange wartet eine Umrissberechnung auf _detect_lock


def _ai_uses_today(u: dict) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return db.q1("SELECT COUNT(*) n FROM audit WHERE user_id=? AND action IN ('suggest','edges_ai','cad_check')"
                 " AND substr(ts,1,10)=?", (u["id"], today))["n"]


# ------------------------------------------------------------------ Status & Auth

@app.get("/api/me")
def me(request: Request):
    u = auth.current_user(request)
    if not u:
        # ohne Anmeldung keine Angaben zu Version, Modell oder Sandbox
        out = {"user": None}
        if auth.setup_required():
            out["setup"] = _setup_info(request)
        return out
    out = {"version": VERSION, "ai": settings.ai_enabled(), "ai_fake": config.AI_FAKE, "model": settings.model(),
           "sandbox": sandbox.worker_alive(), "user": None, "max_upload_mb": config.MAX_UPLOAD_MB,
           "limits": {"timeout_s": config.SANDBOX_TIMEOUT, "mem_mb": config.SANDBOX_MEM_MB, "autofix": config.MAX_AUTOFIX,
                      "sandbox_mode": config.SANDBOX_MODE}}
    out["user"] = auth.public_user(u)
    out["usage"] = _usage(u)
    out["team_invites"] = db.q1("SELECT COUNT(*) n FROM team_invites WHERE user_id=? AND status='offen'",
                                (u["id"],))["n"]
    return out


def _setup_info(request: Request) -> dict:
    return {"required": True, "key_from_env": settings.api_key_source() == "env",
            "key_optional": config.AI_FAKE or settings.api_key_source() == "env",
            "allowed": auth.setup_ip_allowed(auth.client_ip(request))}


class SetupIn(BaseModel):
    username: str = Field(max_length=64)
    display_name: str = Field(default="", max_length=80)
    email: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=300)
    api_key: str = Field(default="", max_length=400)


@app.post("/api/setup")
def setup(body: SetupIn, request: Request, response: Response):
    """Ersteinrichtung: legt das erste Admin-Konto an und speichert den API-Schluessel.
    Nur solange es noch keinen Benutzer gibt und (standardmaessig) nur aus privaten Netzen."""
    ip = auth.client_ip(request)
    if not auth.setup_required():
        raise HTTPException(409, "Snap2CAD ist bereits eingerichtet. Bitte anmelden.")
    if not auth.setup_ip_allowed(ip):
        db.audit("setup_denied", "Einrichtung aus öffentlichem Netz abgelehnt", ip=ip)
        raise HTTPException(403, "Die Einrichtung ist nur aus dem lokalen Netz möglich (oder SETUP_ALLOW_PUBLIC=1 setzen).")
    username = body.username.strip()
    auth.check_username(username)
    email = auth.clean_email(body.email)
    problems = auth.check_policy(body.password, username)
    if problems:
        raise HTTPException(400, "Passwort: " + ", ".join(problems) + ".")
    key = body.api_key.strip()
    if settings.api_key_source() == "env":
        key = ""  # Schluessel kommt aus der Umgebung
    elif key:
        err = ai.verify(key)
        if err:
            raise HTTPException(400, err)
    elif not config.AI_FAKE:
        raise HTTPException(400, "Bitte den Anthropic-API-Schlüssel eingeben.")
    u = auth.create_first_admin(username, body.display_name, email, body.password, ip)
    if key:
        settings.put("anthropic_api_key", key, u["id"])
        db.audit("settings_changed", f"API-Schlüssel hinterlegt (…{key[-4:]})", user_id=u["id"], actor=u["username"], ip=ip)
    db.ex("UPDATE users SET last_login=? WHERE id=?", (db.now(), u["id"]))
    auth.create_session(response, request, u, False)
    return {"user": auth.public_user(u)}


class LoginIn(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=300)
    remember: bool = False


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    u = auth.login(body.username, body.password, auth.client_ip(request))
    auth.create_session(response, request, u, body.remember)
    return {"user": auth.public_user(u)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    u = auth.current_user(request)
    auth.destroy_session(request, response)
    if u:
        db.audit("logout", "", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
    return {"ok": True}


class PwIn(BaseModel):
    current: str = Field(max_length=300)
    new: str = Field(max_length=300)
    email: str | None = Field(default=None, max_length=200)


@app.post("/api/auth/change-password")
def change_password(body: PwIn, request: Request, u: dict = Depends(auth.require_login)):
    e = auth.clean_email(body.email)
    if e and db.q1("SELECT id FROM users WHERE email=? AND id<>?", (e, u["id"])):
        raise HTTPException(400, "Diese E-Mail-Adresse ist ungültig oder wird bereits verwendet.")
    auth.change_password(u, body.current, body.new, auth.client_ip(request), request.cookies.get(auth.COOKIE))
    if e:
        db.ex("UPDATE users SET email=? WHERE id=?", (e, u["id"]))
    return {"user": auth.public_user(db.q1("SELECT * FROM users WHERE id=?", (u["id"],)))}


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=200)


@app.patch("/api/me")
def update_me(body: ProfileIn, u: dict = Depends(auth.require_user)):
    if body.email is not None:
        e = auth.clean_email(body.email)
        if e and db.q1("SELECT id FROM users WHERE email=? AND id<>?", (e, u["id"])):
            raise HTTPException(400, "Diese E-Mail-Adresse wird bereits verwendet.")
        db.ex("UPDATE users SET email=? WHERE id=?", (e, u["id"]))
    if body.display_name is not None:
        db.ex("UPDATE users SET display_name=? WHERE id=?", (body.display_name.strip() or u["username"], u["id"]))
    return {"user": auth.public_user(db.q1("SELECT * FROM users WHERE id=?", (u["id"],)))}


@app.get("/api/password-policy")
def policy():
    return {"min_length": 12, "rules": ["mindestens 12 Zeichen", "nicht der Benutzername",
                                        "kein häufiges Passwort", "nicht das Initialpasswort"]}


@app.post("/api/password-check")
def password_check(body: dict, request: Request):
    pw = str(body.get("password", ""))[:300]
    user = auth.current_user(request)
    name = str(body.get("username") or (user["username"] if user else ""))[:64]
    return {"problems": auth.check_policy(pw, name, user["initial_pw_hash"] if user else None)}


@app.get("/api/invite/{token}")
def invite_info(token: str):
    inv = auth.find_invite(token)
    by = db.q1("SELECT username FROM users WHERE id=?", (inv["created_by"],)) if inv["created_by"] else None
    q = auth.quota_of({"cad_quota": inv["cad_quota"], "role": inv["role"]})
    return {"email": inv["email"], "role": inv["role"], "expires_at": inv["expires_at"],
            "invited_by": by["username"] if by else None, "quota": q}


@app.get("/api/invite/{token}/username")
def invite_username(token: str, u: str = ""):
    auth.find_invite(token)
    u = u.strip()
    ok = 3 <= len(u) <= 32 and set(u.lower()) <= auth.USERNAME_OK
    taken = bool(db.q1("SELECT id FROM users WHERE username=?", (u,))) if ok else False
    return {"valid": ok, "available": ok and not taken}


class AcceptIn(BaseModel):
    username: str = Field(max_length=64)
    display_name: str = Field(default="", max_length=80)
    email: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=300)


@app.post("/api/invite/{token}")
def invite_accept(token: str, body: AcceptIn, request: Request, response: Response):
    u = auth.accept_invite(token, body.username, body.display_name, body.email, body.password, auth.client_ip(request))
    auth.create_session(response, request, u, False)
    return {"user": auth.public_user(u)}


@app.get("/api/reset/{token}")
def reset_info(token: str):
    _, u = auth.find_reset(token)
    return {"username": u["username"]}


class ResetIn(BaseModel):
    password: str = Field(max_length=300)


@app.post("/api/reset/{token}")
def reset_use(token: str, body: ResetIn, request: Request, response: Response):
    u = auth.use_reset(token, body.password, auth.client_ip(request))
    auth.create_session(response, request, u, False)
    return {"user": auth.public_user(u)}


# ------------------------------------------------------------------ Admin

@app.get("/api/admin/users")
def admin_users(a: dict = Depends(auth.require_admin)):
    users = db.q("SELECT * FROM users ORDER BY username")
    out = []
    for u in users:
        pu = auth.public_user(u)
        pu["usage"] = _usage(u)
        pu["jobs"] = db.q1("SELECT COUNT(*) n FROM jobs WHERE user_id=?", (u["id"],))["n"]   # nur selbst angelegte, nur Zahl
        pu["team_projects"] = db.q1("SELECT COUNT(*) n FROM projects WHERE user_id=? AND team_id IS NOT NULL",
                                    (u["id"],))["n"]   # bleiben beim Loeschen im Team (Spec Teams §5)
        pu["pending_reset"] = bool(db.q1("SELECT id FROM resets WHERE user_id=? AND used_at IS NULL AND expires_at>?",
                                         (u["id"], db.now())))
        pu["sessions"] = db.q1("SELECT COUNT(*) n FROM sessions WHERE user_id=? AND expires_at>?", (u["id"], db.now()))["n"]
        out.append(pu)
    return out


class UserPatch(BaseModel):
    role: str | None = None
    status: str | None = None
    cad_quota: int | None = None
    quota_default: bool = False
    display_name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=200)


@app.patch("/api/admin/users/{uid}")
def admin_user_patch(uid: int, body: UserPatch, request: Request, a: dict = Depends(auth.require_admin)):
    with db._lock:  # Pruefungen (letzter Admin) und Aenderungen ohne Wettlauf
        return _admin_user_patch(uid, body, request, a)


def _admin_user_patch(uid: int, body: "UserPatch", request: Request, a: dict):
    u = db.q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    changes = []
    if body.role is not None and body.role != u["role"]:
        if body.role not in auth.ROLES:
            raise HTTPException(400, "Unbekannte Rolle")
        if u["id"] == a["id"]:
            raise HTTPException(400, "Die eigene Rolle kann nicht geändert werden.")
        if u["role"] == "admin" and auth.active_admins() <= 1:
            raise HTTPException(400, "Der letzte Administrator kann nicht herabgestuft werden.")
        db.ex("UPDATE users SET role=? WHERE id=?", (body.role, uid))
        changes.append(f"Rolle {body.role}")
    if body.status is not None and body.status != u["status"]:
        if body.status not in ("active", "disabled"):
            raise HTTPException(400, "Unbekannter Status")
        if u["id"] == a["id"]:
            raise HTTPException(400, "Das eigene Konto kann nicht gesperrt werden.")
        if u["role"] == "admin" and body.status == "disabled" and auth.active_admins() <= 1:
            raise HTTPException(400, "Der letzte Administrator kann nicht gesperrt werden.")
        db.ex("UPDATE users SET status=? WHERE id=?", (body.status, uid))
        if body.status == "disabled":
            auth.end_sessions(uid)
        changes.append("gesperrt" if body.status == "disabled" else "entsperrt")
    if body.quota_default:
        db.ex("UPDATE users SET cad_quota=NULL WHERE id=?", (uid,))
        changes.append("Kontingent Standard")
    elif body.cad_quota is not None:
        db.ex("UPDATE users SET cad_quota=? WHERE id=?", (body.cad_quota, uid))
        changes.append(f"Kontingent {'unbegrenzt' if body.cad_quota < 0 else body.cad_quota}")
    if body.display_name is not None:
        db.ex("UPDATE users SET display_name=? WHERE id=?", (body.display_name.strip() or u["username"], uid))
    if body.email is not None:
        e = auth.clean_email(body.email)
        if e and db.q1("SELECT id FROM users WHERE email=? AND id<>?", (e, uid)):
            raise HTTPException(400, "Diese E-Mail-Adresse wird bereits verwendet.")
        db.ex("UPDATE users SET email=? WHERE id=?", (e, uid))
    if changes:
        db.audit("user_changed", f"„{u['username']}“: " + ", ".join(changes), user_id=a["id"], actor=a["username"],
                 ip=auth.client_ip(request))
    return auth.public_user(db.q1("SELECT * FROM users WHERE id=?", (uid,)))


@app.post("/api/admin/users/{uid}/reset")
def admin_user_reset(uid: int, request: Request, a: dict = Depends(auth.require_admin)):
    u = db.q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    token = auth.create_reset(a, u)
    return {"link": auth.link("reset", token, request), "valid_hours": 48}


@app.post("/api/admin/users/{uid}/logout")
def admin_user_logout(uid: int, a: dict = Depends(auth.require_admin)):
    u = db.q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    auth.end_sessions(uid)
    db.audit("sessions_ended", f"„{u['username']}“ abgemeldet", user_id=a["id"], actor=a["username"])
    return {"ok": True}


@app.delete("/api/admin/users/{uid}")
def admin_user_delete(uid: int, request: Request, a: dict = Depends(auth.require_admin)):
    """Spec Teams §5: Aufträge ohne Projekt und in privaten Projekten sowie die privaten Projekte samt Dateien weg;
    Team-Projekte und deren Aufträge bleiben (Ersteller leer); Mitgliedschaften und Einladungen per Kaskade;
    Leiter-Nachfolge in derselben Transaktion wie DELETE FROM users."""
    u = db.q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    if u["id"] == a["id"]:
        raise HTTPException(400, "Das eigene Konto kann nicht gelöscht werden.")
    with db._lock:
        if u["role"] == "admin" and auth.active_admins() <= 1:
            raise HTTPException(400, "Der letzte Administrator kann nicht gelöscht werden.")
        db.ex("UPDATE users SET status='disabled' WHERE id=?", (uid,))
    auth.end_sessions(uid)
    for j in db.q("SELECT j.* FROM jobs j LEFT JOIN projects p ON p.id=j.project_id WHERE j.user_id=? AND p.team_id IS NULL",
                  (uid,)):
        jobs.delete(j)   # ohne Projekt oder in privaten Projekten; nie in db.atomic()
    private = [r["id"] for r in db.q("SELECT id FROM projects WHERE user_id=? AND team_id IS NULL", (uid,))]
    kept = db.q1("SELECT COUNT(*) n FROM projects WHERE user_id=? AND team_id IS NOT NULL", (uid,))["n"]

    late: dict[str, list[int]] = {"jobs": [], "photos": []}

    def drop_user():
        # Gesamtreview S-2: private Projekte, die nach dem Lesen der Liste noch angelegt wurden, ebenfalls loeschen,
        # sonst bliebe ein Projekt ohne Besitzer und ohne Team; ihre Auftraege und Fotoordner nach dem COMMIT
        extra = [r["id"] for r in db.q("SELECT id FROM projects WHERE user_id=? AND team_id IS NULL", (uid,))]
        marks = ",".join("?" * len(extra)) or "NULL"
        late["jobs"] = [r["id"] for r in db.q(
            f"SELECT id FROM jobs WHERE (user_id=? AND (project_id IS NULL OR project_id IN ({marks}))) "
            f"OR (user_id IS NULL AND project_id IN ({marks}))", (uid, *extra, *extra))]
        if extra:
            late["photos"] = [r["id"] for r in db.q(f"SELECT id FROM photos WHERE project_id IN ({marks})", tuple(extra))]
            db.ex(f"DELETE FROM projects WHERE id IN ({marks})", tuple(extra))
        teams.succeed_leaders(uid, a)
        db.ex("DELETE FROM users WHERE id=?", (uid,))
    projects.delete_projects(private, then=drop_user)
    for jid in late["jobs"]:   # nach dem COMMIT, nie in db.atomic()
        j = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
        if j:
            jobs.delete(j)
    for phid in late["photos"]:
        shutil.rmtree(projects.photo_dir(phid), ignore_errors=True)
    db.audit("user_deleted", f"„{u['username']}“ mit allen privaten Daten gelöscht, "
                             f"{teams.plural(kept, 'Team-Projekt bleibt', 'Team-Projekte bleiben')}",
             user_id=a["id"], actor=a["username"], ip=auth.client_ip(request))
    return {"ok": True, "team_projects_kept": kept}


@app.get("/api/admin/invites")
def admin_invites(a: dict = Depends(auth.require_admin)):
    rows = db.q("""SELECT i.*, c.username created_by_name, u.username used_by_name FROM invites i
                   LEFT JOIN users c ON c.id=i.created_by LEFT JOIN users u ON u.id=i.used_by
                   ORDER BY i.id DESC LIMIT 200""")
    return [{"id": r["id"], "email": r["email"], "role": r["role"], "cad_quota": r["cad_quota"],
             "created_at": r["created_at"], "expires_at": r["expires_at"], "used_at": r["used_at"],
             "used_by": r["used_by_name"], "created_by": r["created_by_name"], "state": auth.invite_state(r)}
            for r in rows]


class InviteIn(BaseModel):
    email: str | None = Field(default=None, max_length=200)
    role: str = "user"
    cad_quota: int | None = None
    days: int = 7


@app.post("/api/admin/invites")
def admin_invite_create(body: InviteIn, request: Request, a: dict = Depends(auth.require_admin)):
    inv, token = auth.create_invite(a, body.email, body.role, body.cad_quota, body.days)
    return {"id": inv["id"], "link": auth.link("einladung", token, request), "expires_at": inv["expires_at"]}


@app.delete("/api/admin/invites/{iid}")
def admin_invite_revoke(iid: int, a: dict = Depends(auth.require_admin)):
    inv = db.q1("SELECT * FROM invites WHERE id=?", (iid,))
    if not inv:
        raise HTTPException(404, "Einladung nicht gefunden")
    if auth.invite_state(inv) == "offen":
        db.ex("UPDATE invites SET revoked_at=? WHERE id=?", (db.now(), iid))
        db.audit("invite_revoked", f"Einladung {iid} ({inv['email'] or 'ohne E-Mail'})", user_id=a["id"],
                 actor=a["username"])
    return {"ok": True}


@app.get("/api/admin/audit")
def admin_audit(limit: int = 300, action: str = "", a: dict = Depends(auth.require_admin)):
    limit = max(1, min(limit, 2000))
    if action:
        return db.q("SELECT * FROM audit WHERE action LIKE ? ORDER BY id DESC LIMIT ?", (action + "%", limit))
    return db.q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))


@app.get("/api/admin/status")
def admin_status(a: dict = Depends(auth.require_admin)):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    tok = db.q("SELECT usage FROM job_versions WHERE substr(created_at,1,7)=?", (month,))
    tin = sum((db.jload(t["usage"], {}) or {}).get("input_tokens", 0) for t in tok)
    tout = sum((db.jload(t["usage"], {}) or {}).get("output_tokens", 0) for t in tok)
    return {"version": VERSION, "ai": settings.ai_enabled(), "ai_fake": config.AI_FAKE, "model": settings.model(),
            "sandbox": sandbox.worker_alive(), "sandbox_mode": config.SANDBOX_MODE,
            "sandbox_limits": {"timeout_s": config.SANDBOX_TIMEOUT, "mem_mb": config.SANDBOX_MEM_MB},
            "default_quota": config.DEFAULT_QUOTA, "users": db.q1("SELECT COUNT(*) n FROM users")["n"],
            "jobs_month": db.q1("SELECT COUNT(*) n FROM jobs WHERE substr(created_at,1,7)=?", (month,))["n"],
            "tokens_month": {"input": tin, "output": tout}}


def _settings_public() -> dict:
    return {"api_key": {"source": settings.api_key_source(), "hint": settings.api_key_hint(),
                        "encrypted": settings.api_key_encrypted(), "secret_key_set": bool(config.SECRET_KEY)},
            "model": {"value": settings.model(), "source": settings.model_source(), "default": config.DEFAULT_MODEL},
            "ai_fake": config.AI_FAKE}


@app.get("/api/admin/settings")
def admin_settings(a: dict = Depends(auth.require_admin)):
    return _settings_public()


class SettingsIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=400)
    clear_api_key: bool = False
    model: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, max_length=300)


@app.put("/api/admin/settings")
def admin_settings_put(body: SettingsIn, request: Request, a: dict = Depends(auth.require_admin)):
    ip = auth.client_ip(request)
    key = (body.api_key or "").strip()
    model = (body.model or "").strip() if body.model is not None else None
    if (key or body.clear_api_key) and settings.api_key_source() == "env":
        raise HTTPException(400, "Der API-Schlüssel ist per Umgebungsvariable ANTHROPIC_API_KEY gesetzt und "
                                 "kann hier nicht geändert werden.")
    if model is not None and settings.model_source() == "env":
        raise HTTPException(400, "Das Modell ist per Umgebungsvariable ANTHROPIC_MODEL festgelegt.")
    if key or body.clear_api_key:
        auth.confirm_password(a, body.password or "", ip)
    if model == config.DEFAULT_MODEL:
        model = ""
    # Pruefen, bevor irgendetwas gespeichert wird
    check_key = key or (settings.api_key() if not body.clear_api_key else "")
    if key or (model and check_key):
        err = ai.verify(check_key, model or None)
        if err:
            raise HTTPException(400, err)
    elif model:
        err = ai.check_model_format(model)
        if err:
            raise HTTPException(400, err)
    if key:
        settings.put("anthropic_api_key", key, a["id"])
        db.audit("settings_changed", f"API-Schlüssel ersetzt (…{key[-4:]})", user_id=a["id"], actor=a["username"], ip=ip)
    elif body.clear_api_key:
        settings.put("anthropic_api_key", None)
        db.audit("settings_changed", "API-Schlüssel entfernt", user_id=a["id"], actor=a["username"], ip=ip)
    if model is not None:
        settings.put("anthropic_model", model or None, a["id"])
        db.audit("settings_changed", f"Modell: {model or config.DEFAULT_MODEL}", user_id=a["id"], actor=a["username"], ip=ip)
    return _settings_public()


# ------------------------------------------------------------------ Messunterlage

_preview_cache: dict = {}
_preview_lock = threading.Lock()  # schuetzt Cache und pdfium


def _pdf_bytes(fmt: str, pages: list[str], header: str) -> bytes:
    buf = io.BytesIO()
    matgen.build(buf, fmt, pages, header)
    return buf.getvalue()


def _pages(pages: str) -> list[str]:
    p = [x for x in (pages or "").split(",") if x in matgen.PAGES]
    return p or list(matgen.PAGES)


@app.get("/api/mat.pdf")
def mat_pdf(format: str = "A4", pages: str = "", header: str = "", u: dict = Depends(auth.require_user)):
    if format not in matgen.FORMATS:
        raise HTTPException(400, "Format muss A4 oder A3 sein")
    data = _pdf_bytes(format, _pages(pages), header[:60])
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Messunterlage_{format}.pdf"'})


@app.get("/api/mat/preview.png")
def mat_preview(format: str = "A4", page: int = 0, header: str = "", u: dict = Depends(auth.require_user)):
    if format not in matgen.FORMATS or page not in (0, 1, 2):
        raise HTTPException(400, "Ungültige Parameter")
    key = (format, page, header[:60])
    # pdfium ist nicht threadsicher -> Rendern komplett unter der Sperre
    with _preview_lock:
        png = _preview_cache.get(key)
        if png is None:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(_pdf_bytes(format, list(matgen.PAGES), header[:60]))
            try:
                for i in range(len(pdf)):
                    img = pdf[i].render(scale=110 / 72).to_pil()
                    b = io.BytesIO()
                    img.save(b, "PNG", optimize=True)
                    if len(_preview_cache) > 30:
                        _preview_cache.clear()
                    _preview_cache[(format, i, header[:60])] = b.getvalue()
            finally:
                pdf.close()
            png = _preview_cache[key]
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/mat/layout")
def mat_layout(format: str = "A4", u: dict = Depends(auth.require_user)):
    if format not in matgen.FORMATS:
        raise HTTPException(400, "Format muss A4 oder A3 sein")
    return vision.spec(format)




# ------------------------------------------------------------------ Projekte

def _project_public(p: dict, u: dict, detail: bool = False) -> dict:
    out = dict(p)
    out.update(access.project_fields(u, p))   # team_id, team_name, my_role, creator, creator_is_member (Spec Teams §4)
    out["cad_check"] = check.public_check(p) if detail else None
    out["n_photos"] = db.q1("SELECT COUNT(*) n FROM photos WHERE project_id=?", (p["id"],))["n"]
    out["n_measurements"] = db.q1("SELECT COUNT(*) n FROM measurements WHERE project_id=? AND accepted=1", (p["id"],))["n"]
    fmt = _project_format(p["id"])
    out["format"] = fmt
    out["factors"] = _factors(p)
    if detail:
        hp = _hints(p)
        out["photos"] = [_photo_public(ph, hp) for ph in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (p["id"],))]
        out["measurements"] = [_meas_public(m) for m in
                               db.q("SELECT * FROM measurements WHERE project_id=? ORDER BY seq", (p["id"],))]
        out["grid_h"] = _grid_h(fmt)
        out["parts"] = parts.public_list(p["id"])
        out["model_dims"] = [{k: r[k] for k in ("id", "label", "grp", "value", "job_id", "dim_id", "created_at")}
                             for r in jobs.learned_dims(p["id"])]
    return out


def _library_fields(p: dict) -> dict:
    """Bibliotheksfelder der Projektliste: letzter Auftrag, Vorschaubild, letzte Aenderung."""
    pid = p["id"]
    lj = db.q1("SELECT id,name,status,current_version,updated_at FROM jobs WHERE project_id=? "
               "ORDER BY updated_at DESC, id DESC LIMIT 1", (pid,))
    mj = db.q1("SELECT j.id, j.current_version FROM jobs j JOIN job_versions v "
               "ON v.job_id=j.id AND v.version=j.current_version "
               "WHERE j.project_id=? AND v.status='ok' ORDER BY j.updated_at DESC, j.id DESC LIMIT 1", (pid,))
    thumb = None
    if mj:
        thumb = {"kind": "model", "url": f"/api/jobs/{mj['id']}/v/{mj['current_version']}/preview.png"}
    else:
        for ph in db.q("SELECT id FROM photos WHERE project_id=? ORDER BY (view='top') DESC, id", (pid,)):
            if (_photo_dir(ph["id"]) / "thumb.jpg").is_file():
                thumb = {"kind": "photo", "url": f"/api/photos/{ph['id']}/thumb.jpg"}
                break
    stamps = db.q1("SELECT (SELECT MAX(created_at) FROM photos WHERE project_id=?) ph, "
                   "(SELECT MAX(created_at) FROM measurements WHERE project_id=?) me", (pid, pid))
    updated = max(x for x in (p["created_at"], stamps["ph"], stamps["me"], lj["updated_at"] if lj else None) if x)
    return {"last_job": lj, "thumb": thumb, "updated_at": updated}


@app.get("/api/projects")
def project_list(scope: str = "private", u: dict = Depends(auth.require_user)):
    """Spec Teams §4: private (Standard), team:<id> (nur Mitglieder) oder all (privat und alle eigenen Teams)."""
    if scope == "private":
        rows = db.q("SELECT * FROM projects WHERE user_id=? AND team_id IS NULL ORDER BY archived, id DESC", (u["id"],))
    elif scope == "all":
        rows = db.q("SELECT p.* FROM projects p LEFT JOIN team_members m ON m.team_id=p.team_id AND m.user_id=? "
                    "WHERE (p.team_id IS NULL AND p.user_id=?) OR m.user_id IS NOT NULL ORDER BY p.archived, p.id DESC",
                    (u["id"], u["id"]))
    elif _team_scope(scope) is not None:
        tid = _team_scope(scope)
        access.require_team(u, tid, "lesend")
        rows = db.q("SELECT * FROM projects WHERE team_id=? ORDER BY archived, id DESC", (tid,))
    else:
        raise HTTPException(400, "Unbekannter Bereich")
    return [{**_project_public(p, u), **_library_fields(p)} for p in rows]


def _team_scope(scope: str) -> int | None:
    """team:<id> mit hoechstens 24 Zeichen und id < 2**63 (sonst kein gueltiger Bereich, 400 statt SQLite-Ueberlauf)."""
    s = scope[5:] if scope.startswith("team:") and len(scope) <= 24 else ""
    return int(s) if s.isascii() and s.isdigit() and int(s) < 2**63 else None


class ProjectIn(BaseModel):
    name: str = Field(default="", max_length=120)
    team_id: int | None = Field(default=None, ge=1, le=2**63 - 1)   # sonst 422 statt eines Ueberlaufs in SQLite


@app.post("/api/projects")
def project_new(body: ProjectIn, u: dict = Depends(auth.require_user)):
    name = body.name.strip() or f"Projekt {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    with db.atomic():   # Rechte und Anlegen ohne Wettlauf mit einem gleichzeitigen Austritt (Lueckenfuellung 20)
        if body.team_id is not None:
            access.require_team(u, body.team_id, "mitglied")    # Spec Teams §4: nur Leiter/Mitglied (sonst 403/404)
        pid = db.ex("INSERT INTO projects(user_id,team_id,name,created_at) VALUES (?,?,?,?)",
                    (u["id"], body.team_id, name, db.now()))
    return _project_public(db.q1("SELECT * FROM projects WHERE id=?", (pid,)), u, True)


@app.get("/api/projects/current")
def project_current(u: dict = Depends(auth.require_user)):
    """Bleibt privat (Spec Teams §4); legt bei leerem privatem Bereich ein privates Projekt an."""
    p = db.q1("SELECT * FROM projects WHERE user_id=? AND team_id IS NULL AND archived=0 ORDER BY id DESC LIMIT 1",
              (u["id"],))
    if not p:
        pid = db.ex("INSERT INTO projects(user_id,name,created_at) VALUES (?,?,?)",
                    (u["id"], f"Projekt {datetime.now().strftime('%d.%m.%Y')}", db.now()))
        p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    return _project_public(p, u, True)


@app.get("/api/projects/{pid}")
def project_get(pid: int, u: dict = Depends(auth.require_user)):
    return _project_public(_own_project(pid, u, "read"), u, True)


LIGHT_COLORS = {"weiß", "weiss", "silber", "hellgrau", "beige", "natur"}


def _hints(project: dict) -> dict:
    """Hinweise fuer die Kantenerkennung nur aus Handeingaben (Spec §3); KI-Schaetzungen wirken nicht."""
    if not project.get("material_user"):
        return {}
    h = {"transparent": project.get("transparent") or 0,
         "light": (project.get("color") or "").strip().lower() in LIGHT_COLORS}
    # ohne relevante Werte wirkt die Handeingabe wie keine: gleich normalisieren, sonst false-positive edges_stale
    return h if h["transparent"] or h["light"] else {}


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    ctrl_x: float | None = None
    ctrl_y: float | None = None
    clear_ctrl: bool = False
    archived: bool | None = None
    color: str | None = Field(default=None, max_length=40)
    material: str | None = Field(default=None, max_length=40)
    transparent: int | None = Field(default=None, ge=0, le=2)
    finish: str | None = Field(default=None, max_length=20)
    clear_material: bool = False


@app.patch("/api/projects/{pid}")
def project_patch(pid: int, body: ProjectPatch, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    for k in ("ctrl_x", "ctrl_y"):
        v = getattr(body, k)
        ref = 100.0 if k == "ctrl_x" else (_grid_h(_project_format(pid)) or 230.0)
        if v is not None and not (0.9 * ref <= v <= 1.1 * ref):
            raise HTTPException(400, f"Kontrollwert {v:g} mm ist unplausibel (erwartet um {ref:g} mm).")
    _finite(body.ctrl_x, "Kontrollwert"); _finite(body.ctrl_y, "Kontrollwert")  # noqa: E702
    before = _hints(p)
    if body.finish is not None and body.finish not in ai.FINISHES:
        raise HTTPException(400, "Oberfläche: matt oder glaenzend")
    with db.atomic():
        if body.name is not None and body.name.strip():
            db.ex("UPDATE projects SET name=? WHERE id=?", (body.name.strip(), pid))
        if body.archived is not None:
            db.ex("UPDATE projects SET archived=? WHERE id=?", (int(body.archived), pid))
        if body.clear_ctrl:
            db.ex("UPDATE projects SET ctrl_x=NULL, ctrl_y=NULL WHERE id=?", (pid,))
        for k in ("ctrl_x", "ctrl_y"):
            v = getattr(body, k)
            if v is not None:
                db.ex(f"UPDATE projects SET {k}=? WHERE id=?", (v, pid))
        if body.clear_material:
            db.ex("UPDATE projects SET color=NULL, material=NULL, transparent=NULL, finish=NULL, material_user=0 "
                  "WHERE id=?", (pid,))
        for k in ("color", "material", "transparent", "finish"):                  # feste Spaltenliste
            v = getattr(body, k)
            if v is not None:
                v = (v.strip() or None) if isinstance(v, str) else v
                db.ex(f"UPDATE projects SET {k}=?, material_user=1 WHERE id=?", (v, pid))
        p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
        _refresh(p)
    if _hints(p) != before and db.q1("SELECT 1 FROM photos WHERE project_id=? AND view='bottom'", (pid,)):
        _realign_project(pid)   # rechnet die Umrisse mit den neuen Hinweisen nach (nie in db.atomic())
    return _project_public(p, u, True)


@app.delete("/api/projects/{pid}")
def project_delete(pid: int, u: dict = Depends(auth.require_user)):
    """Spec Teams §4: Fotos, Messungen, Teile, Werte weg; Aufträge bleiben beim Ersteller ohne Projekt, Aufträge
    ohne Ersteller werden mitgelöscht. Das Recht wird in der Transaktion wiederholt (guard, Lückenfüllung 20)."""
    _own_project(pid, u, "delete")
    projects.delete_projects([pid], guard=lambda: _own_project(pid, u, "delete"))
    return {"ok": True}


MOVE_FOREIGN = "Das Projekt enthält Aufträge anderer Mitglieder – bitte „In privat kopieren“ verwenden"
SAME_AREA = "Das Projekt liegt bereits in diesem Bereich."
TEAM_TO_TEAM = "Zwischen zwei Teams geht es nur über „In privat kopieren“ und „In Team kopieren“."


class MoveIn(BaseModel):
    team_id: int | None = Field(default=None, ge=1, le=2**63 - 1)


def _area(team_id: int | None) -> str:
    """Audit-Text eines Bereichs: „privat“ oder teams.team_text (Team 3 „Werkstatt“)."""
    if team_id is None:
        return "privat"
    t = db.q1("SELECT id, name FROM teams WHERE id=?", (team_id,))
    return teams.team_text(t) if t else f"Team {team_id}"


def _check_move(pid: int, team_id: int | None, u: dict) -> dict:
    """Recht move an der Quelle, Ziel-Bereich und Mitgliedschaft im Ziel-Team – vor der Transaktion als schnelle
    Antwort und in der Transaktion erneut (Wettlauf mit Austritt oder Verschieben, Lückenfüllung 20)."""
    p = _own_project(pid, u, "move")
    if team_id == p["team_id"]:
        raise HTTPException(400, SAME_AREA)
    if team_id is not None and p["team_id"] is not None:
        raise HTTPException(400, TEAM_TO_TEAM)
    if team_id is not None:
        access.require_team(u, team_id, "mitglied")
    return p


@app.post("/api/projects/{pid}/move")
def project_move(pid: int, body: MoveIn, request: Request, u: dict = Depends(auth.require_user)):
    """Spec Teams §4: privat ↔ Team samt Aufträgen. Nach privat gehört das Projekt dem Verschiebenden und geht nur
    ohne Aufträge anderer (auch gelöschter) Ersteller (F-1)."""
    _check_move(pid, body.team_id, u)
    with db.atomic():
        p = _check_move(pid, body.team_id, u)
        if body.team_id is None:
            n = db.q1("SELECT COUNT(*) n FROM jobs WHERE project_id=? AND (user_id IS NULL OR user_id<>?)",
                      (pid, u["id"]))["n"]
            if n:
                raise HTTPException(409, MOVE_FOREIGN)
            db.ex("UPDATE projects SET team_id=NULL, user_id=? WHERE id=?", (u["id"], pid))
        else:
            db.ex("UPDATE projects SET team_id=? WHERE id=?", (body.team_id, pid))
        db.audit("project_move", f"Projekt {pid}: {_area(p['team_id'])} → {_area(body.team_id)}", user_id=u["id"],
                 actor=u["username"], ip=auth.client_ip(request))
    return _project_public(db.q1("SELECT * FROM projects WHERE id=?", (pid,)), u, True)


class CopyIn(BaseModel):
    team_id: int | None = Field(default=None, ge=1, le=2**63 - 1)
    name: str = Field(default="", max_length=120)


@app.post("/api/projects/{pid}/copy")
def project_copy(pid: int, body: CopyIn, request: Request, u: dict = Depends(auth.require_user)):
    """Spec Teams §4: Kopie mit allen Bestandteilen und der aktuellen gültigen Version jedes CAD-Auftrags; Recht
    „Kopieren“ an der Quelle, Leiter/Mitglied im Ziel-Team bzw. eigener privater Bereich. Kein KI-Aufruf, kein Kontingent."""

    def guard():   # vor dem Kopieren und erneut in der Transaktion (Wettlauf mit einem Austritt, Lückenfüllung 20)
        p = _own_project(pid, u, "copy")
        if body.team_id is not None and p["team_id"] is not None:
            raise HTTPException(400, TEAM_TO_TEAM)
        if body.team_id is not None:
            access.require_team(u, body.team_id, "mitglied")
    guard()
    new = projcopy.copy_project(u, pid, body.team_id, body.name, guard)
    db.audit("project_copy", f"Projekt {pid} → Projekt {new} ({_area(body.team_id)})", user_id=u["id"], actor=u["username"],
             ip=auth.client_ip(request))
    return _project_public(db.q1("SELECT * FROM projects WHERE id=?", (new,)), u, True)


@app.delete("/api/projects/{pid}/model-dims/{mid}")
def model_dim_delete(pid: int, mid: int, u: dict = Depends(auth.require_user)):
    """Spec Stufe B §4: gelernten Messschieberwert loeschen (die Pruefung wird damit veraltet)."""
    _own_project(pid, u)
    row = db.q1("SELECT id, label FROM model_dims WHERE id=? AND project_id=?", (mid, pid))
    if not row:
        raise HTTPException(404, "Messschieberwert nicht gefunden")
    db.ex("DELETE FROM model_dims WHERE id=?", (mid,))
    db.audit("model_dim_delete", f"Projekt {pid}: {row['label']}"[:500], user_id=u["id"], actor=u["username"])
    return {"ok": True}


# ------------------------------------------------------------------ Fotos

VIEWS = ("top", "bottom", "tilted", "gauge", "overview")
PLANAR = ("top", "bottom")
ALIGN_PXMM = 4.0


def _analyze_store(phid: int, img, fmt: str | None, view: str, hints: dict | None = None) -> dict:
    d = _photo_dir(phid)
    a = vision.analyze(img, fmt)
    for n in ("rect.jpg", "gauge.jpg"):
        (d / n).unlink(missing_ok=True)
    vision_ov = vision.overlay(img)
    (d / "overlay.jpg").write_bytes(vision.encode_jpg(vision_ov, 85))
    if a.get("homography") and a.get("format"):
        rect = vision.rectify_mat(img, a["homography"], a["format"])
        (d / "rect.jpg").write_bytes(vision.encode_jpg(rect, 90))
        gw, gh = vision.spec(a["format"])["grid_mm"]
        a["rect"] = {"pxmm": matgen.PROFILES[a["format"]]["pxmm"], "w_mm": gw, "h_mm": gh, "w": rect.shape[1], "h": rect.shape[0]}
    if a.get("gauge") and len(a["gauge"]["ids"]) >= 2:
        g, (x0, x1, y0, y1) = vision.rectify_gauge(img, a["gauge"])
        (d / "gauge.jpg").write_bytes(vision.encode_jpg(g, 90))
        a["gauge_rect"] = {"pxmm": vision.PX_PER_MM, "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                           "w": g.shape[1], "h": g.shape[0]}
    if a.get("rect") and view in PLANAR and _detect_lock.acquire(timeout=DETECT_WAIT_S):
        try:
            res = edges.detect(rect, a["format"], hints)
            a["outline_mm"] = res["outlines"][0]["polygon"] if res["outlines"] else None
            a["contrast"] = res["contrast"]
            a["outline_hints"] = hints or {}
        except Exception:  # noqa: BLE001 – Umriss ist optional
            a["outline_mm"], a["outline_hints"] = None, hints or {}
        finally:
            _detect_lock.release()
    return a


def _set_analysis(phid: int, a: dict):
    db.ex("UPDATE photos SET analysis=? WHERE id=?", (db.jdump(a), phid))


def _outline_of(ph: dict):
    """Umriss (mm) aus analysis.outline_mm; sonst nachrechnen (unter _detect_lock). None = keiner, "timeout" = spaeter."""
    a = db.jload(ph["analysis"], {}) or {}
    project = db.q1("SELECT * FROM projects WHERE id=?", (ph["project_id"],))
    hints = _hints(project or {})
    if a.get("outline_mm") == "timeout":   # Marke aus _realign_project: Referenz war nicht berechenbar, nicht erneut warten
        return "timeout"
    if "outline_mm" in a and a.get("outline_hints") == hints:
        return a["outline_mm"]
    rect_path = _photo_dir(ph["id"]) / "rect.jpg"
    if not a.get("rect") or not rect_path.is_file():
        return None
    if not _detect_lock.acquire(timeout=DETECT_WAIT_S):
        return "timeout"
    try:
        img = cv2.imread(str(rect_path))
        res = edges.detect(img, ph["format"], hints) if img is not None else {"outlines": [], "contrast": None}
    except Exception:  # noqa: BLE001 – Umriss ist optional
        res = {"outlines": [], "contrast": None}
    finally:
        _detect_lock.release()
    outline = res["outlines"][0]["polygon"] if res["outlines"] else None
    with db.atomic():  # frisch lesen: ein paralleler Formatwechsel darf nicht ueberschrieben werden
        cur = db.q1("SELECT format, analysis FROM photos WHERE id=?", (ph["id"],))
        if not cur or cur["format"] != ph["format"]:
            return None
        a2 = db.jload(cur["analysis"], {}) or {}
        a2["outline_mm"], a2["contrast"], a2["outline_hints"] = outline, res["contrast"], hints
        _set_analysis(ph["id"], a2)
        ph["analysis"] = db.jdump(a2)
    return outline


def _align_photo(ph: dict, top: dict | None):
    """bottom_align einer Unteransicht neu berechnen (Spec §1 „Wann“); Handwahl (bottom_rot_user) bleibt."""
    ot = _outline_of(top) if top is not None and ph["view"] == "bottom" else None
    ob = _outline_of(ph) if ph["view"] == "bottom" else None
    with db.atomic():
        cur = db.q1("SELECT * FROM photos WHERE id=?", (ph["id"],))
        if not cur or cur["format"] != ph["format"]:
            return   # geloescht oder paralleler Formatwechsel (der rechnet selbst neu)
        a = db.jload(cur["analysis"], {}) or {}
        user_rot = a.get("bottom_rot_user")
        a.pop("bottom_align", None)
        a.pop("align_note", None)
        if cur["view"] == "bottom" and a.get("rect"):
            if top is None:
                a["align_note"] = "Draufsicht fehlt"
            elif ot == "timeout" or ob == "timeout":
                a["align_note"] = "Ausrichtung nicht berechnet – erneut versuchen"
            elif not ot or not ob:
                a["align_note"] = "Umriss nicht erkennbar"   # bottom_align bleibt null: to_top nutzt rot=0 ohne Versatz
            else:
                r = a["rect"]
                al = vision.align_bottom(ot, ob, r["w_mm"], r["h_mm"], rot=user_rot)
                if user_rot is not None:
                    al["unsure"] = False
                a["bottom_align"] = {**al, "auto": user_rot is None, "top_photo_id": top["id"]}
        _set_analysis(cur["id"], a)


def _realign_project(pid: int):
    """Alle Unteransichten eines Projekts neu ausrichten, danach die Teile verknuepfen. Nie in db.atomic()."""
    top = parts.reference_top(pid)
    if top is not None and _outline_of(top) == "timeout":
        top = {**top, "analysis": db.jdump({**(db.jload(top["analysis"], {}) or {}), "outline_mm": "timeout"})}
        # Referenz nicht berechenbar: jede Unteransicht bekommt den Hinweis, ohne erneut zu warten
    for ph in db.q("SELECT * FROM photos WHERE project_id=? AND view='bottom'", (pid,)):
        _align_photo(ph, top)
    with db.atomic():
        parts.link_bottom(pid)


@app.post("/api/projects/{pid}/photos")
def photo_upload(pid: int, file: UploadFile = File(...), view: str = Form("top"), format: str = Form(""),
                 u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if db.q1("SELECT COUNT(*) n FROM photos WHERE project_id=?", (pid,))["n"] >= 30:
        raise HTTPException(400, "Höchstens 30 Fotos pro Projekt.")
    data = file.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Datei zu groß (max. {config.MAX_UPLOAD_MB} MB)")
    try:
        img = vision.load_image(data)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Bild konnte nicht gelesen werden (JPEG, PNG, HEIC).") from None
    if max(img.shape[:2]) > 8000:
        s = 8000 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    view = view if view in VIEWS else "top"
    phid = db.ex("INSERT INTO photos(project_id,filename,view,created_at) VALUES (?,?,?,?)",
                 (pid, (file.filename or "foto.jpg")[:120], view, db.now()))
    d = _photo_dir(phid)
    d.mkdir(parents=True, exist_ok=True)
    try:
        (d / "orig.jpg").write_bytes(vision.encode_jpg(img, 92))
        (d / "thumb.jpg").write_bytes(vision.encode_jpg(vision.thumbnail(img, 360), 82))
        a = _analyze_store(phid, img, format if format in matgen.FORMATS else None, view, _hints(p))
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(d, ignore_errors=True)
        db.ex("DELETE FROM photos WHERE id=?", (phid,))
        raise HTTPException(400, f"Auswertung fehlgeschlagen: {e}") from None
    db.ex("UPDATE photos SET format=?, status=?, max_err=?, analysis=? WHERE id=?",
          (a.get("format"), a["status"], a.get("max_err_mm"), db.jdump(a), phid))
    if view in PLANAR:
        _realign_project(pid)
    return _photo_public(db.q1("SELECT * FROM photos WHERE id=?", (phid,)), _hints(p))


class AlignIn(BaseModel):
    rot: Literal[0, 90, 180, 270] | None = None


class PhotoPatch(BaseModel):
    view: str | None = None
    format: str | None = None
    bottom_align: AlignIn | None = None


@app.patch("/api/photos/{phid}")
def photo_patch(phid: int, body: PhotoPatch, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u)
    new_view = body.view if body.view in VIEWS else ph["view"]
    if "bottom_align" in body.model_fields_set and new_view != "bottom":
        raise HTTPException(400, "Nur für Fotos der Ansicht „Von unten“")   # vor jeder Aenderung pruefen
    realign = False
    if body.view in VIEWS and body.view != ph["view"]:
        with db.atomic():
            db.ex("UPDATE photos SET view=? WHERE id=?", (body.view, phid))
            if (ph["view"] == "bottom") != (body.view == "bottom"):   # Nutzer-Messungen folgen top <-> bottom
                nv, ov = ("bottom", "top") if body.view == "bottom" else ("top", "bottom")
                for m in db.q("SELECT id, data FROM measurements WHERE photo_id=?", (phid,)):
                    d = db.jload(m["data"], {}) or {}
                    if d.get("view", "top") == ov:
                        d["view"] = nv
                        db.ex("UPDATE measurements SET data=? WHERE id=?", (db.jdump(d), m["id"]))
        realign = body.view in PLANAR or ph["view"] in PLANAR
        if ph["view"] == "bottom":   # bottom_align/align_note entfernen; bottom_rot_user bleibt fuer ein Zurueckschalten
            _align_photo(db.q1("SELECT * FROM photos WHERE id=?", (phid,)), None)
        ph = db.q1("SELECT * FROM photos WHERE id=?", (phid,))
        _refresh(p)   # Auto-Masse bekommen die neue Ansicht (_refresh ist selbst atomar)
    if body.format is not None and body.format != ph["format"]:
        img = vision.load_image((_photo_dir(phid) / "orig.jpg").read_bytes())
        a = _analyze_store(phid, img, body.format if body.format in matgen.FORMATS else None, ph["view"],
                           _hints(p))
        with db.atomic():
            old = db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (phid,))["analysis"], {}) or {}
            if old.get("bottom_rot_user") is not None:
                a["bottom_rot_user"] = old["bottom_rot_user"]   # Handwahl ueberlebt den Formatwechsel
            db.ex("UPDATE photos SET format=?, status=?, max_err=?, analysis=? WHERE id=?",
                  (a.get("format"), a["status"], a.get("max_err_mm"), db.jdump(a), phid))
            parts.delete_photo_parts(phid)
            _refresh(p)
            for n in ("edges.json", "edges_ki.jpg"):  # in der Transaktion: wie photo_edges beim Schreiben
                (_photo_dir(phid) / n).unlink(missing_ok=True)
        realign = realign or ph["view"] in PLANAR
    if "bottom_align" in body.model_fields_set:
        with db.atomic():
            a = db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (phid,))["analysis"], {}) or {}
            if body.bottom_align is None or ("rot" in body.bottom_align.model_fields_set and body.bottom_align.rot is None):
                a.pop("bottom_rot_user", None)                       # zurueck auf automatisch
            elif "rot" in body.bottom_align.model_fields_set:
                a["bottom_rot_user"] = body.bottom_align.rot        # Handwahl ({} = nur neu rechnen)
            _set_analysis(phid, a)
        realign = True
    if realign:
        _realign_project(p["id"])
    return _photo_public(db.q1("SELECT * FROM photos WHERE id=?", (phid,)), _hints(p))


@app.delete("/api/photos/{phid}")
def photo_delete(phid: int, u: dict = Depends(auth.require_user)):
    _, p = _own_photo(phid, u)
    with db.atomic():
        parts.delete_photo_parts(phid)
        db.ex("DELETE FROM photos WHERE id=?", (phid,))
        _refresh(p)
    shutil.rmtree(_photo_dir(phid), ignore_errors=True)
    _realign_project(p["id"])   # Referenz-Draufsicht kann weggefallen sein
    return {"ok": True}


@app.get("/api/photos/{phid}/align.jpg")
def photo_align_jpg(phid: int, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u, "read")
    a = db.jload(ph["analysis"], {}) or {}
    tid = (a.get("bottom_align") or {}).get("top_photo_id")
    top = db.q1("SELECT * FROM photos WHERE id=?", (tid,)) if tid else parts.reference_top(p["id"])
    img = cv2.imread(str(_photo_dir(phid) / "rect.jpg")) if a.get("rect") else None
    if ph["view"] != "bottom" or img is None or not top:
        raise HTTPException(404, "Keine Ausrichtung vorhanden")
    at = db.jload(top["analysis"], {}) or {}
    out = vision.bottom_warp(img, a, at, ALIGN_PXMM)
    own = parts.to_top(ph, a["outline_mm"]) if a.get("outline_mm") else []
    vision.draw_outlines(out, [at.get("outline_mm"), own], [(12, 65, 194), (178, 60, 20)], ALIGN_PXMM, at["rect"]["h_mm"])
    return Response(vision.encode_jpg(out, 85), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/photos/{phid}/{kind}.jpg")
def photo_file(phid: int, kind: str, u: dict = Depends(auth.require_user)):
    _own_photo(phid, u, "read")
    if kind not in ("orig", "overlay", "rect", "gauge", "thumb"):
        raise HTTPException(404, "Unbekannte Datei")
    p = _photo_dir(phid) / f"{kind}.jpg"
    if not p.is_file():
        raise HTTPException(404, "Datei nicht vorhanden")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


class EdgesIn(BaseModel):
    use_ai: bool = True


@app.post("/api/photos/{phid}/edges")
def photo_edges(phid: int, body: EdgesIn, request: Request, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u)
    d = _photo_dir(phid)
    rect = (db.jload(ph["analysis"], {}) or {}).get("rect")
    if not rect or not (d / "rect.jpg").is_file() or ph["format"] not in matgen.FORMATS:
        raise HTTPException(400, "Für dieses Foto gibt es keine entzerrte Draufsicht.")
    img = cv2.imread(str(d / "rect.jpg"))
    if img is None:
        raise HTTPException(400, "Die Draufsicht ist nicht lesbar.")
    hints = _hints(p)
    if not _detect_lock.acquire(blocking=False):
        raise HTTPException(429, "Kantenerkennung ist gerade belegt – bitte gleich erneut versuchen.")
    try:
        res = edges.detect(img, ph["format"], hints)
    finally:
        _detect_lock.release()
    if not res["outlines"]:
        raise HTTPException(422, "Kein Objekt erkannt – Teil von Hand zeichnen.")

    mg = _margin_mm(ph)

    def inside(poly):
        return all(-mg <= q[0] <= rect["w_mm"] + mg and -mg <= q[1] <= rect["h_mm"] + mg for q in poly)
    notice, detected = "", []
    if body.use_ai and settings.ai_enabled():
        if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
            notice = f"Tageslimit für KI erreicht ({AI_DAILY_LIMIT}) – Teile nur aus dem Umriss."
        else:
            db.audit("edges_ai", f"Foto {phid}", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
            try:
                detected = [x for x in parts.ai_parts(d, res, jobs.material_line(p)) if inside(x["polygon"])]
                if not detected:
                    notice = "Die KI hat keine Teile erkannt – Teile nur aus dem Umriss."
            except ai.AIError as e:
                notice = f"KI-Zuordnung fehlgeschlagen: {e} – Teile nur aus dem Umriss."
    with db.atomic():
        cur = db.q1("SELECT format FROM photos WHERE id=?", (phid,))
        if not cur or cur["format"] != ph["format"]:
            raise HTTPException(409, "Das Foto wurde während der Erkennung geändert – bitte erneut erkennen.")
        has_parts = bool(db.q1("SELECT 1 FROM parts WHERE photo_id=? AND source!='user'", (phid,)))
        if not detected and has_parts:
            # ohne KI-Ergebnis vorhandene Teile nicht durch den Gesamtumriss ersetzen (sonst zerfaellt z. B. Quader + Platte)
            notice = notice.replace("Teile nur aus dem Umriss.", "vorhandene Teile bleiben unverändert.") if notice \
                else "Ohne KI wurden nur die Kanten aktualisiert; vorhandene Teile bleiben unverändert."
        else:
            skipped = parts.replace_detected(p["id"], phid, detected or parts.outline_parts(res))
            if skipped:
                more = "1 erkanntes Teil nicht übernommen" if skipped == 1 else f"{skipped} erkannte Teile nicht übernommen"
                notice = f"{notice} {more} – höchstens {parts.MAX_PARTS_PER_PHOTO} Teile je Foto.".strip()
        _refresh(p)
        a2 = db.jload(db.q1("SELECT analysis FROM photos WHERE id=?", (phid,))["analysis"], {}) or {}
        a2["outline_mm"] = res["outlines"][0]["polygon"]
        a2["contrast"], a2["outline_hints"], a2["edges_hints"] = res["contrast"], hints, hints
        _set_analysis(phid, a2)
        tmp = d / "edges.json.tmp"  # innerhalb von atomic: kein zweiter Lauf und kein Loeschen dazwischen
        tmp.write_text(json.dumps(res), encoding="utf-8")
        os.replace(tmp, d / "edges.json")
    if ph["view"] in PLANAR:
        _realign_project(p["id"])
    return {"parts": [t for t in parts.public_list(p["id"]) if t["photo_id"] == phid], "segments": res["segments"],
            "notice": notice}


@app.get("/api/photos/{phid}/edges.json")
def photo_edges_get(phid: int, u: dict = Depends(auth.require_user)):
    _own_photo(phid, u, "read")
    f = _photo_dir(phid) / "edges.json"
    if not f.is_file():
        raise HTTPException(404, "Noch keine Kanten erkannt")
    return json.loads(f.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Masse

def _points(pts):
    import math
    if pts is None:
        return None
    out = []
    for p in pts[:8]:
        if len(p) != 2 or not all(math.isfinite(v) and abs(v) < 1e5 for v in p):
            raise HTTPException(400, "Ungültige Punkte")
        out.append([float(p[0]), float(p[1])])
    return out


def _finite(v, name="Wert"):
    import math
    if v is not None and (not math.isfinite(v) or abs(v) > 1e6):
        raise HTTPException(400, f"{name} ist ungültig")
    return v


class MeasIn(BaseModel):
    photo_id: int | None = None
    label: str = Field(default="", max_length=80)
    kind: str = "length"
    view: str = "top"
    points: list[list[float]] | None = None
    value: float | None = None
    unc: float | None = None
    critical: bool = False
    caliper: float | None = None
    fit: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=300)


class MeasPatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    points: list[list[float]] | None = None
    value: float | None = None
    unc: float | None = None
    critical: bool | None = None
    caliper: float | None = None
    clear_caliper: bool = False
    fit: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=300)
    accepted: bool | None = None
    kind: str | None = None
    part_id: int | None = None
    ref: bool | None = None


KIND_LABEL = {"length": "Länge", "height": "Höhe", "diameter": "Durchmesser", "radius": "Radius",
              "angle": "Winkel", "point": "Punkt"}


def _next_seq(pid: int) -> int:
    return db.q1("SELECT COALESCE(MAX(seq),0)+1 s FROM measurements WHERE project_id=?", (pid,))["s"]


@app.post("/api/projects/{pid}/measurements")
def meas_create(pid: int, body: MeasIn, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if body.kind not in geom.KINDS:
        raise HTTPException(400, "Unbekannte Messart")
    photo = None
    if body.photo_id is not None:
        photo, pp = _own_photo(body.photo_id, u, "read")
        if pp["id"] != pid:
            raise HTTPException(400, "Foto gehört zu einem anderen Projekt")
    pts = _points(body.points) or []
    for v in (body.value, body.unc, body.caliper):
        _finite(v)
    source = "user"
    if pts:
        fx, fy = _factors(p)
        value = geom.compute(body.kind, pts, fx, fy)
        if value is None and body.kind != "point":
            raise HTTPException(400, "Aus diesen Punkten lässt sich kein Maß berechnen.")
    else:
        value, source = body.value, "manual"
        if value is None:
            raise HTTPException(400, "Wert fehlt")
    unc = body.unc if body.unc is not None else (parts.default_unc(photo, body.view) if source == "user" else 0.1)
    unit = "°" if body.kind == "angle" else "mm"
    bottom_ok = body.view == "bottom" and photo is not None and photo["view"] == "bottom"
    data = {"view": body.view if body.view in ("top", "gauge") or bottom_ok else "top", "points": pts, "note": body.note}
    with db.atomic():
        seq = _next_seq(pid)
        mid = db.ex("""INSERT INTO measurements(project_id,photo_id,seq,label,kind,value,unit,unc,data,critical,caliper,fit,
                       source,accepted,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                    (pid, body.photo_id, seq, body.label.strip() or KIND_LABEL[body.kind], body.kind, value, unit, unc,
                     db.jdump(data), int(body.critical), body.caliper, body.fit, source, db.now()))
        _refresh(p)
    return _meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,)))


@app.patch("/api/measurements/{mid}")
def meas_patch(mid: int, body: MeasPatch, u: dict = Depends(auth.require_user)):
    _, p = _own_meas(mid, u)
    with db.atomic():  # frisch lesen: kein verlorenes Update bei parallelem PATCH, 404 wenn inzwischen geloescht
        m = db.q1("SELECT * FROM measurements WHERE id=?", (mid,))
        if not m:
            raise HTTPException(404, "Maß nicht gefunden")
        return _meas_patch(m, p, body)


def _meas_patch(m: dict, p: dict, body: MeasPatch):
    mid = m["id"]
    body.points = _points(body.points)
    for v in (body.value, body.unc, body.caliper):
        _finite(v)
    sets: dict = {}
    d = db.jload(m["data"], {}) or {}
    if body.label is not None:
        sets["label"] = body.label.strip() or KIND_LABEL.get(m["kind"], "Maß")
    if body.kind is not None and body.kind != m["kind"]:
        pairs = ({"diameter", "radius"}, {"length", "height"})
        if not any({body.kind, m["kind"]} <= pr for pr in pairs):
            raise HTTPException(400, "Diese Messart kann nicht umgestellt werden.")
        old_label = KIND_LABEL.get(m["kind"])
        m["kind"] = sets["kind"] = body.kind
        if m["label"] == old_label and body.label is None:
            sets["label"] = KIND_LABEL[body.kind]
        if d.get("points") and body.points is None:
            fx, fy = _factors(p)
            sets["value"] = geom.compute(body.kind, d["points"], fx, fy)
        elif m["value"] is not None:
            factor = (0.5 if body.kind == "radius" else 2.0) if body.kind in ("radius", "diameter") else 1.0
            sets["value"] = m["value"] * factor
    if body.points is not None:
        fx, fy = _factors(p)
        v = geom.compute(m["kind"], body.points[:8], fx, fy)
        if v is None and m["kind"] != "point":
            raise HTTPException(400, "Aus diesen Punkten lässt sich kein Maß berechnen.")
        d["points"] = body.points[:8]
        d.pop("ai_value", None)
        sets["value"] = v
        if m["source"] == "manual":
            sets["source"] = "user"
    elif body.value is not None:
        sets["value"] = body.value
        if m["source"] == "user":
            sets["source"] = "manual"
    drop = None
    if m["source"] == "auto" and (body.points is not None or body.value is not None or "kind" in sets):
        key = d.pop("auto_key", None)
        d.pop("auto_raw", None)
        sets["source"] = "manual" if body.value is not None and body.points is None else "user"
        drop = (m["part_id"], key) if m["part_id"] else None
    if "part_id" in body.model_fields_set:
        if m["source"] == "auto" and "source" not in sets:
            raise HTTPException(400, "Automatische Maße gehören fest zu ihrem Teil.")
        if body.part_id == -1:
            d.pop("part_fixed", None)
        else:
            if body.part_id is not None and not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?",
                                                      (body.part_id, p["id"])):
                raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
            sets["part_id"] = body.part_id
            d["part_fixed"] = True
    if body.ref is not None:
        d["ref"] = bool(body.ref)
    if body.unc is not None:
        sets["unc"] = max(0.0, body.unc)
    if body.critical is not None:
        sets["critical"] = int(body.critical)
    if body.clear_caliper:
        sets["caliper"] = None
        d.pop("ref", None)
    elif body.caliper is not None:
        sets["caliper"] = body.caliper
        d.pop("ref", None)
    if body.fit is not None:
        sets["fit"] = body.fit or None
    if body.note is not None:
        d["note"] = body.note
    if body.accepted is not None:
        sets["accepted"] = int(body.accepted)
    sets["data"] = db.jdump(d)
    cols = ", ".join(f"{k}=?" for k in sets)
    with db.atomic():
        if drop:
            parts.drop_key(*drop)  # erst hier: ein abgelehnter PATCH (400 oben) hinterlaesst nichts
        db.ex(f"UPDATE measurements SET {cols} WHERE id=?", (*sets.values(), mid))
        _refresh(p)
    return _meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,)))


@app.delete("/api/measurements/{mid}")
def meas_delete(mid: int, u: dict = Depends(auth.require_user)):
    m, p = _own_meas(mid, u)
    with db.atomic():
        if m["source"] == "auto" and m["part_id"]:
            parts.drop_key(m["part_id"], (db.jload(m["data"], {}) or {}).get("auto_key"))
        db.ex("DELETE FROM measurements WHERE id=?", (mid,))
        _refresh(p)
    return {"ok": True}


@app.post("/api/projects/{pid}/measurements/accept-all")
def meas_accept_all(pid: int, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    with db.atomic():
        db.ex("UPDATE measurements SET accepted=1 WHERE project_id=? AND source='claude'", (pid,))
        _refresh(p)
    return {"ok": True}


@app.post("/api/projects/{pid}/measurements/discard-suggestions")
def meas_discard(pid: int, u: dict = Depends(auth.require_user)):
    _own_project(pid, u)
    db.ex("DELETE FROM measurements WHERE project_id=? AND source='claude' AND accepted=0", (pid,))
    return {"ok": True}


class PartIn(BaseModel):
    photo_id: int
    label: str = Field(default="", max_length=80)
    role: str = "body"
    polygon: list[list[float]] = Field(min_length=3, max_length=64)


class PartPatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    role: str | None = None
    polygon: list[list[float]] | None = Field(default=None, min_length=3, max_length=64)
    reset_scale: bool = False


def _margin_mm(photo: dict) -> float:
    """Spielraum fuer Eckpunkte ausserhalb des Feldes: 10 mm · k (A4/A3 10 mm, Kleinteile 2,5 mm)."""
    return 10.0 * matgen.edge_scale(photo.get("format"))


def _polygon(pts: list, photo: dict) -> list:
    import math
    a = db.jload(photo["analysis"], {}) or {}
    r = a.get("rect")
    if not r:
        raise HTTPException(400, "Für dieses Foto gibt es keine entzerrte Draufsicht.")
    if not 3 <= len(pts) <= 64:
        raise HTTPException(400, "Ein Teil braucht 3 bis 64 Eckpunkte.")
    mg = _margin_mm(photo)
    for q in pts:
        if len(q) != 2 or not all(math.isfinite(v) for v in q) \
                or not (-mg <= q[0] <= r["w_mm"] + mg and -mg <= q[1] <= r["h_mm"] + mg):
            raise HTTPException(400, "Eckpunkt außerhalb der Messfläche")
    return [[float(q[0]), float(q[1])] for q in pts]


@app.post("/api/projects/{pid}/parts")
def part_create(pid: int, body: PartIn, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    ph, pp = _own_photo(body.photo_id, u, "read")
    if pp["id"] != pid:
        raise HTTPException(400, "Foto gehört zu einem anderen Projekt")
    poly = _polygon(body.polygon, ph)
    with db.atomic():
        if db.q1("SELECT COUNT(*) n FROM parts WHERE photo_id=?", (ph["id"],))["n"] >= parts.MAX_PARTS_PER_PHOTO:
            raise HTTPException(400, f"Höchstens {parts.MAX_PARTS_PER_PHOTO} Teile je Foto.")
        tid = parts.create_part(pid, ph["id"], body.label, body.role, poly)
        _refresh(p)
    return parts.part_public(db.q1("SELECT * FROM parts WHERE id=?", (tid,)))


@app.patch("/api/parts/{part_id}")
def part_patch(part_id: int, body: PartPatch, u: dict = Depends(auth.require_user)):
    t, p = _own_part(part_id, u)
    poly = None
    if body.polygon is not None:
        poly = _polygon(body.polygon, db.q1("SELECT * FROM photos WHERE id=?", (t["photo_id"],)))
    with db.atomic():
        t = db.q1("SELECT * FROM parts WHERE id=?", (part_id,))  # frisch lesen: kein Wettlauf mit parallelem PATCH
        if not t:
            raise HTTPException(404, "Teil nicht gefunden")
        if poly is not None:
            parts.set_polygon(t, poly)
        if body.label is not None:
            parts.rename(t, body.label)
        if body.role in parts.ROLE_TEXT:
            db.ex("UPDATE parts SET role=? WHERE id=?", (body.role, part_id))
        if body.reset_scale:
            parts.reset_scale(part_id)
        _refresh(p)
    return parts.part_public(db.q1("SELECT * FROM parts WHERE id=?", (part_id,)))


@app.delete("/api/parts/{part_id}")
def part_delete(part_id: int, u: dict = Depends(auth.require_user)):
    t, p = _own_part(part_id, u)
    with db.atomic():
        parts.delete_part(t)
        _refresh(p)
    return {"ok": True}


class SuggestIn(BaseModel):
    photo_id: int | None = None
    hint: str = Field(default="", max_length=500)


class CheckIn(BaseModel):
    photo_ids: list[int] | None = Field(default=None, max_length=30)
    part_id: int | None = None
    force: bool = False


@app.post("/api/projects/{pid}/cad-check")
def cad_check(pid: int, body: CheckIn, request: Request, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if body.part_id is not None and not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?", (body.part_id, pid)):
        raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
    photo_ids = body.photo_ids
    if photo_ids is not None:
        own = {r["id"] for r in db.q("SELECT id FROM photos WHERE project_id=?", (pid,))}
        photo_ids = sorted(set(photo_ids) & own)
    lock = check.lock_for(pid)
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "Prüfung läuft bereits – Ergebnis folgt gleich.")
    try:
        p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
        h = check.cad_hash(p, photo_ids, body.part_id)
        s = check.stored(p)
        if s and s.get("hash") == h and not body.force:
            if s.get("photo_ids") != photo_ids:   # gleiche Auswahl in anderer Schreibweise: speichern, sonst bleibt stale
                s["photo_ids"] = photo_ids
                db.ex("UPDATE projects SET cad_check=? WHERE id=?", (db.jdump(s), pid))
            return {**s, "stale": False}
        if not settings.ai_enabled():
            raise HTTPException(503, "KI ist nicht eingerichtet (Verwaltung → Einstellungen).")
        with db.atomic():
            if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
                raise HTTPException(429, f"Tageslimit für KI-Funktionen erreicht ({AI_DAILY_LIMIT}).")
            db.audit("cad_check", f"Projekt {pid}", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
        try:
            out = check.run_check(p, photo_ids, body.part_id, h)
        except ai.AIError as e:
            raise HTTPException(502, str(e)) from None
    finally:
        lock.release()
    return {**out, "stale": False}


@app.post("/api/projects/{pid}/suggest")
def meas_suggest(pid: int, body: SuggestIn, request: Request, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if not settings.ai_enabled():
        raise HTTPException(503, "KI ist nicht eingerichtet (Verwaltung → Einstellungen).")
    if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
        raise HTTPException(429, f"Tageslimit für KI-Funktionen erreicht ({AI_DAILY_LIMIT}).")
    photos = db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,))
    if body.photo_id:
        photos = [ph for ph in photos if ph["id"] == body.photo_id] + [ph for ph in photos if ph["id"] != body.photo_id]
    content: list[dict] = []
    used_photo = None
    n_img = 0
    for ph in photos:
        d = _photo_dir(ph["id"])
        if used_photo is None and ph["view"] == "top" and (d / "rect.jpg").is_file():
            used_photo = ph
            content += ai.image_ref(d / "rect.jpg", ai.scaled_caption(
                d / "rect.jpg", f"Draufsicht (Foto {ph['id']}), Ansicht \"top\"", vision.PX_PER_MM))
            n_img += 1
        if (d / "gauge.jpg").is_file() and n_img < 3:
            content += ai.image_ref(d / "gauge.jpg", ai.scaled_caption(
                d / "gauge.jpg", f"Höhenlehre (Foto {ph['id']}), Ansicht \"gauge\" (x −100…100 mm, y ab −10 mm)",
                vision.PX_PER_MM))
            n_img += 1
    if used_photo is None:
        raise HTTPException(400, "Kein auswertbares Foto (mindestens 4 Marker der Unterlage nötig).")
    have, _ = jobs.measurement_table(pid)
    content.append({"type": "text", "text": "Bereits gemessen:\n" + have +
                    (f"\n\nHinweis des Nutzers: {body.hint.strip()}" if body.hint.strip() else "")})
    db.audit("suggest", f"Projekt {pid}", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
    try:
        text, usage = ai.call(ai.SUGGEST_SYSTEM, [{"role": "user", "content": content}], max_tokens=4000)
        items = ai.parse_suggestions(text)
    except ai.AIError as e:
        raise HTTPException(502, str(e)) from None
    fx, fy = _factors(p)
    f = (fx + fy) / 2
    out = []
    with db.atomic():  # M-Nummern gemeinsam mit parallelen Auto-Massen vergeben
        db.ex("DELETE FROM measurements WHERE project_id=? AND source='claude' AND accepted=0", (pid,))
        mids = [_suggest_insert(pid, used_photo["id"], it, f) for it in items]
    for mid in mids:
        out.append(_meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,))))
    return {"suggestions": out, "usage": usage}


def _suggest_insert(pid: int, photo_id: int, it: dict, f: float) -> int:
    seq = _next_seq(pid)
    kind = it["kind"] if it["kind"] in geom.KINDS else "length"
    value = it["value"] if kind == "angle" else round(it["value"] * f, 3)
    data = {"view": it["view"], "points": it["points"] or [], "reason": it["reason"], "unsure": it["unsure"],
            "ai_value": True}
    return db.ex("""INSERT INTO measurements(project_id,photo_id,seq,label,kind,value,unit,unc,data,source,accepted,
                   reason,created_at) VALUES (?,?,?,?,?,?,?,?,?,'claude',0,?,?)""",
                 (pid, photo_id, seq, it["label"], kind, value, it["unit"], it["unc"], db.jdump(data),
                  it["reason"], db.now()))


def _csv(pid: int) -> str:
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY seq", (pid,))

    def n(v):
        return "" if v is None else f"{v:.3f}".rstrip("0").rstrip(".").replace(".", ",")

    def safe_txt(t: str) -> str:   # keine Formeln in Tabellenprogrammen
        return ("'" + t) if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t

    def cell(c) -> str:
        s = str(c)
        return '"' + s.replace('"', '""') + '"' if any(x in s for x in ';"\n') else s

    lines = ["ID;Bezeichnung;Art;Wert;Einheit;Unsicherheit;Messschieber;kritisch;Passung;Quelle;Ansicht;Punkte (mm);Teil;Nennmaß"]
    seq = {t["id"]: t["seq"] for t in db.q("SELECT id, seq FROM parts WHERE project_id=?", (pid,))}
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (pid,))}
    for m in rows:
        d = db.jload(m["data"], {}) or {}
        tag, tpts = jobs.top_points(m, d, photos)
        pts = " ".join(f"{p[0]:.2f}/{p[1]:.2f}" for p in tpts)
        cells = [f"M{m['seq']}", safe_txt(m["label"]), KIND_LABEL.get(m["kind"], m["kind"]), n(m["value"]), m["unit"],
                 n(m["unc"]),
                 n(m["caliper"]), "ja" if m["critical"] else "", safe_txt(m["fit"] or ""),
                 jobs.SOURCE_LABEL.get(m["source"], m["source"]), f"{d.get('view', '')} {tag}".strip(), pts,
                 f"T{seq[m['part_id']]}" if m["part_id"] in seq else "", n(d.get("nominal"))]
        lines.append(";".join(cell(c) for c in cells))
    for r in jobs.learned_dims(pid):   # Stufe B §4: Messschieber am Modell, Quelle „Modell“
        cells = [r["dim_id"] or "", safe_txt(r["label"]), jobs.GROUP_TEXT.get(r["grp"], r["grp"]), n(r["value"]), "mm", "",
                 n(r["value"]), "", "", "Modell", f"Auftrag {r['job_id']}" if r["job_id"] else "", "", "", ""]
        lines.append(";".join(cell(c) for c in cells))
    return "﻿" + "\r\n".join(lines) + "\r\n"


@app.get("/api/projects/{pid}/measurements.csv")
def meas_csv(pid: int, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u, "read")
    safe = _ascii_name(p["name"], "Projekt")
    return Response(_csv(pid), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": _disposition(f"{safe}_Masse.csv")})


# ------------------------------------------------------------------ CAD-Auftraege

class CheckItem(BaseModel):
    kind: Literal[*ai.CHECK_KINDS]
    severity: Literal["block", "warn"]
    text: str = Field(max_length=200)

    @field_validator("text")
    @classmethod
    def _einzeilig(cls, v: str) -> str:
        return " ".join(v.split())


class JobIn(BaseModel):
    project_id: int | None = None
    name: str = Field(default="", max_length=120)
    request: str = Field(default="", max_length=6000)
    process: str = "fdm"
    material: str = Field(default="", max_length=80)
    tolerance: str = Field(default="", max_length=80)
    photo_ids: list[int] | None = Field(default=None, max_length=30)
    check_items: list[CheckItem] = Field(default=[], max_length=8)
    cutter_d: float | None = None
    setups: str = Field(default="", max_length=40)
    fits: list[dict] | None = None
    extra: str = Field(default="", max_length=2000)
    part_id: int | None = None


@app.post("/api/jobs")
def job_create(body: JobIn, u: dict = Depends(auth.require_user)):
    project = _own_project(body.project_id, u) if body.project_id else None
    if body.part_id is not None and (not project or not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?",
                                                              (body.part_id, project["id"]))):
        raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
    if not project and not body.request.strip():
        raise HTTPException(400, "Ohne Projekt braucht der Auftrag eine Beschreibung.")
    name = body.name.strip() or (project["name"] if project else "CAD-Auftrag")
    fits = [{"id": str(f.get("id", ""))[:8], "fit": str(f.get("fit", ""))[:20], "depth": str(f.get("depth", ""))[:30]}
            for f in (body.fits or [])[:30] if isinstance(f, dict)]
    jid = jobs.create(u, project, name, body.request, {
        "process": body.process, "material": body.material.strip(), "tolerance": body.tolerance.strip(),
        "photo_ids": body.photo_ids, "part_id": body.part_id, "cutter_d": body.cutter_d, "setups": body.setups.strip(),
        "fits": fits, "check_items": [i.model_dump() for i in body.check_items],
        "extra": body.extra.strip()})
    return jobs.job_public(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), True)


@app.get("/api/jobs")
def job_list(all: int = 0, team: int | None = Query(None, ge=1, le=2**63 - 1), u: dict = Depends(auth.require_user)):
    """Meine (selbst angelegt und noch lesbar: ohne Projekt, eigenes privates Projekt – beim Admin jedes private –,
    Team mit Mitgliedschaft), team=<id> (Mitglied: Aufträge der Team-Projekte), all=1 (Admin: ohne Projekt, privat,
    Teams mit Mitgliedschaft). Ersteller per LEFT JOIN users: leer = gelöschter Benutzer (Spec Teams §2, §5)."""
    if team is not None:
        access.require_team(u, team, "lesend")
        rows = db.q("SELECT j.*, us.username FROM jobs j JOIN projects p ON p.id=j.project_id "
                    "LEFT JOIN users us ON us.id=j.user_id WHERE p.team_id=? ORDER BY j.id DESC LIMIT 500", (team,))
    elif all and u["role"] == "admin":
        rows = db.q("SELECT j.*, us.username FROM jobs j LEFT JOIN users us ON us.id=j.user_id "
                    "LEFT JOIN projects p ON p.id=j.project_id WHERE p.id IS NULL OR p.team_id IS NULL "
                    "OR p.team_id IN (SELECT team_id FROM team_members WHERE user_id=?) ORDER BY j.id DESC LIMIT 500",
                    (u["id"],))
    else:   # nach einem Austritt verschwinden eigene Auftraege in Team-Projekten (Name, Status, Masse)
        rows = db.q("SELECT j.*, ? AS username FROM jobs j LEFT JOIN projects p ON p.id=j.project_id WHERE j.user_id=? "
                    "AND (p.id IS NULL OR (p.team_id IS NULL AND (p.user_id=? OR ?)) "
                    "OR p.team_id IN (SELECT team_id FROM team_members WHERE user_id=?)) ORDER BY j.id DESC LIMIT 500",
                    (u["username"], u["id"], u["id"], int(u["role"] == "admin"), u["id"]))
    return [{**jobs.job_public(r), "username": r["username"]} for r in rows]


@app.get("/api/jobs/{jid}")
def job_get(jid: int, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u, "read")
    return {**jobs.job_public(j, True), **access.job_fields(u, j)}   # my_role, team_id, team_name (Lesend-Modus)


class IterIn(BaseModel):
    text: str = Field(max_length=4000)


@app.post("/api/jobs/{jid}/iterate")
def job_iterate(jid: int, body: IterIn, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u)
    if not body.text.strip():
        raise HTTPException(400, "Bitte den Änderungswunsch beschreiben.")
    jobs.iterate(u, j, body.text)
    return jobs.job_public(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), True)


class ParamValue(BaseModel):
    id: str = Field(pattern=r"^D[0-9]{1,4}$")
    # strict: true und "45" -> 422; Bereich im Endpunkt: ein Pydantic-Fehler mit NaN liesse sich nicht als JSON melden
    value: float = Field(strict=True)


class ParamIn(BaseModel):
    values: list[ParamValue] = Field(min_length=1, max_length=jobs.PARAM_MAX)
    base: int | None = None


@app.post("/api/jobs/{jid}/param")
def job_param(jid: int, body: ParamIn, u: dict = Depends(auth.require_user)):
    """Spec Stufe B §2: Messschieberwerte in die Konstanten einsetzen, neue Version ohne KI."""
    j = _own_job(jid, u)   # zuerst Rechte (write): ein fremder Auftrag ist 404, gleich welche Werte
    for v in body.values:
        if not 0 < v.value <= 5000:            # faengt auch NaN und Unendlich ab
            raise HTTPException(422, f"Maß {v.id}: Der Wert muss größer als 0 und höchstens 5000 mm sein.")
    return jobs.param(u, j, [v.model_dump() for v in body.values], base=body.base)


@app.post("/api/jobs/{jid}/cancel")
def job_cancel(jid: int, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u)
    jobs.cancel(j)
    return jobs.job_public(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), True)


@app.delete("/api/jobs/{jid}")
def job_delete(jid: int, u: dict = Depends(auth.require_user)):
    jobs.delete(_own_job(jid, u, "delete"))   # Rechte vor jobs.delete (prueft selbst nicht)
    return {"ok": True}


FILE_TYPES = {"model.step": "application/step", "model.stl": "model/stl", "model.py": "text/x-python; charset=utf-8",
              "outline.json": "application/json"}


def _file_base(j: dict) -> str:
    return _ascii_name(j["name"], f"auftrag_{j['id']}")


@app.get("/api/jobs/{jid}/v/{ver}/preview.png")
def job_preview(jid: int, ver: int, u: dict = Depends(auth.require_user)):
    _own_job(jid, u, "read")
    v = db.q1("SELECT status FROM job_versions WHERE job_id=? AND version=?", (jid, ver))
    d = jobs.version_dir(jid, ver)
    stl = d / "model.stl"
    if not v or v["status"] != "ok" or not stl.is_file() or not preview.ensure_png(stl, d / "preview.png"):
        raise HTTPException(404, "Kein Modellbild")
    return FileResponse(d / "preview.png", media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/jobs/{jid}/v/{ver}/{name}")
def job_file(jid: int, ver: int, name: str, download: int = 0, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u, "read")
    if name == "bundle.zip":
        return _bundle(j, ver)
    if name not in FILE_TYPES:
        raise HTTPException(404, "Unbekannte Datei")
    p = jobs.version_dir(jid, ver) / name
    if not p.is_file():
        raise HTTPException(404, "Datei nicht vorhanden")
    ext = name.split(".")[1]
    fname = f"{_file_base(j)}_v{ver}.{ext}"
    if download:
        return FileResponse(p, media_type=FILE_TYPES[name], filename=fname)
    return FileResponse(p, media_type=FILE_TYPES[name])


def _bundle(j: dict, ver: int) -> Response:
    v = db.q1("SELECT * FROM job_versions WHERE job_id=? AND version=?", (j["id"], ver))
    if not v:
        raise HTTPException(404, "Version nicht gefunden")
    d = jobs.version_dir(j["id"], ver)
    base = f"{_file_base(j)}_v{ver}"
    meta = db.jload(v["meta"], {}) or {}
    result = db.jload(v["result"], {}) or {}
    checks = db.jload(v["checks"], []) or []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in ("model.step", "model.stl", "model.py"):
            if (d / n).is_file():
                z.write(d / n, f"{base}.{n.split('.')[1]}")
        if j["project_id"]:
            z.writestr(f"{base}_Masse.csv", _csv(j["project_id"]))
        info = {"auftrag": j["name"], "version": ver, "erstellt": v["created_at"], "anfrage": db.jload(j["request"], {}),
                "ki": meta, "pruefung": checks, "ergebnis": result}
        z.writestr(f"{base}_info.json", json.dumps(info, ensure_ascii=False, indent=2))
        lines = [f"{j['name']} – Version {ver}", "=" * 40, "", meta.get("summary", ""), ""]
        if result.get("bbox"):
            b = result["bbox"]
            lines.append(f"Abmessungen: {b[0]:g} × {b[1]:g} × {b[2]:g} mm, Volumen {result.get('volume_mm3', 0) / 1000:.2f} cm³")
        if meta.get("assumptions"):
            lines += ["", "Annahmen:"] + [f"- {a}" for a in meta["assumptions"]]
        if meta.get("check_before_manufacturing"):
            lines += ["", "Vor dem Fertigen prüfen:"] + [f"- {a}" for a in meta["check_before_manufacturing"]]
        if checks:
            lines += ["", "Automatische Prüfung:"] + [f"- [{c['state']}] {c['label']} {c.get('detail', '')}" for c in checks]
        lines += ["", "Die .py-Datei ist build123d-Code und lässt sich mit Python + build123d erneut ausführen."]
        z.writestr("LIESMICH.txt", "\r\n".join(lines))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": _disposition(f"{base}.zip")})


# ------------------------------------------------------------------ Frontend

@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(404)
async def spa_fallback(request: Request, exc):
    path = request.url.path
    if request.method == "GET" and not path.startswith(("/api/", "/static/")) and (STATIC / "index.html").is_file():
        return FileResponse(STATIC / "index.html", media_type="text/html",
                            headers={"Cache-Control": "no-cache", "Content-Security-Policy": CSP})
    detail = getattr(exc, "detail", "Nicht gefunden")
    return JSONResponse({"detail": detail}, status_code=404)
