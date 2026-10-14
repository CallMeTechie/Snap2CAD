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

import cv2
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, auth, config, db, geom, jobs, sandbox, settings

sys.path.insert(0, str(config.ROOT))
from core import matgen, vision  # noqa: E402

VERSION = os.environ.get("SNAP2CAD_VERSION", "0.1.0")  # im Image vom Git-Tag gesetzt
STATIC = Path(__file__).resolve().parent.parent / "static"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


# ------------------------------------------------------------------ Start

def _startup():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "photos").mkdir(exist_ok=True)
    (config.DATA_DIR / "jobs").mkdir(exist_ok=True)
    db.conn()
    auth.ensure_admin()
    auth.purge_expired()
    jobs.startup()
    ki = "Testmodus" if config.AI_FAKE else {"env": "an (Umgebung)", "db": "an", "none": "aus"}[settings.api_key_source()]
    print(f"Snap2CAD {VERSION} · KI: {ki} · Modell {settings.model()} · Sandbox {config.SANDBOX_MODE}", flush=True)
    if auth.setup_required():
        print("Noch nicht eingerichtet: Snap2CAD im Browser öffnen – der Einrichtungsassistent legt das erste"
              " Admin-Konto an.", flush=True)


@asynccontextmanager
async def lifespan(_app):
    _startup()
    yield


app = FastAPI(title="Snap2CAD", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


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


def _own_project(pid: int, user: dict) -> dict:
    p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    if not p or (p["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "Projekt nicht gefunden")
    return p


def _own_photo(phid: int, user: dict) -> tuple[dict, dict]:
    ph = db.q1("SELECT * FROM photos WHERE id=?", (phid,))
    if not ph:
        raise HTTPException(404, "Foto nicht gefunden")
    return ph, _own_project(ph["project_id"], user)


def _own_meas(mid: int, user: dict) -> tuple[dict, dict]:
    m = db.q1("SELECT * FROM measurements WHERE id=?", (mid,))
    if not m:
        raise HTTPException(404, "Maß nicht gefunden")
    return m, _own_project(m["project_id"], user)


def _own_job(jid: int, user: dict) -> dict:
    j = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
    if not j or (j["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "Auftrag nicht gefunden")
    return j


def _photo_dir(phid: int) -> Path:
    return config.DATA_DIR / "photos" / str(phid)


def _photo_public(ph: dict) -> dict:
    a = db.jload(ph["analysis"], {}) or {}
    d = _photo_dir(ph["id"])
    return {"id": ph["id"], "project_id": ph["project_id"], "filename": ph["filename"], "view": ph["view"],
            "format": ph["format"], "status": ph["status"], "max_err": ph["max_err"], "created_at": ph["created_at"],
            "analysis": {k: a.get(k) for k in ("width", "height", "found_ids", "mat_ids", "missing_ids", "format_auto",
                                               "rms_mm", "loo_mm", "max_err_mm")},
            "gauge": ({k: a["gauge"].get(k) for k in ("strip", "ids", "rms_mm", "vlen_mm")} if a.get("gauge") else None),
            "rect": a.get("rect"), "gauge_rect": a.get("gauge_rect"),
            "files": [n[:-4] for n in ("orig.jpg", "overlay.jpg", "rect.jpg", "gauge.jpg", "thumb.jpg")
                      if (d / n).is_file()]}


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


def _default_unc(photo: dict | None, view: str) -> float:
    if not photo:
        return 0.5
    a = db.jload(photo["analysis"], {}) or {}
    if view == "gauge" and a.get("gauge"):
        return round((a["gauge"].get("rms_mm") or 0.3) * 2 + 0.3, 2)
    return round((photo["max_err"] or 0.3) + 0.2, 2)


def _usage(user: dict) -> dict:
    q = auth.quota_of(user)
    return {"quota": q, "used": auth.usage_this_month(user["id"])}


# ------------------------------------------------------------------ Status & Auth

@app.get("/api/me")
def me(request: Request):
    u = auth.current_user(request)
    out = {"version": VERSION, "ai": settings.ai_enabled(), "ai_fake": config.AI_FAKE, "model": settings.model(),
           "sandbox": sandbox.worker_alive(), "user": None, "max_upload_mb": config.MAX_UPLOAD_MB,
           "limits": {"timeout_s": config.SANDBOX_TIMEOUT, "mem_mb": config.SANDBOX_MEM_MB, "autofix": config.MAX_AUTOFIX,
                      "sandbox_mode": config.SANDBOX_MODE}}
    if auth.setup_required():
        out["setup"] = {"required": True, "key_from_env": settings.api_key_source() == "env",
                        "key_optional": config.AI_FAKE or settings.api_key_source() == "env",
                        "allowed": auth.setup_ip_allowed(auth.client_ip(request))}
    if u:
        out["user"] = auth.public_user(u)
        out["usage"] = _usage(u)
    return out


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
        pu["jobs"] = db.q1("SELECT COUNT(*) n FROM jobs WHERE user_id=?", (u["id"],))["n"]
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
    for j in db.q("SELECT * FROM jobs WHERE user_id=?", (uid,)):
        jobs.delete(j)
    for p in db.q("SELECT id FROM projects WHERE user_id=?", (uid,)):
        _delete_project_files(p["id"])
    db.ex("DELETE FROM users WHERE id=?", (uid,))
    db.audit("user_deleted", f"„{u['username']}“ mit allen Daten gelöscht", user_id=a["id"], actor=a["username"],
             ip=auth.client_ip(request))
    return {"ok": True}


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
    return {"api_key": {"source": settings.api_key_source(), "hint": settings.api_key_hint()},
            "model": {"value": settings.model(), "source": settings.model_source(), "default": config.DEFAULT_MODEL},
            "ai_fake": config.AI_FAKE}


@app.get("/api/admin/settings")
def admin_settings(a: dict = Depends(auth.require_admin)):
    return _settings_public()


class SettingsIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=400)
    clear_api_key: bool = False
    model: str | None = Field(default=None, max_length=100)


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


@app.get("/api/prompt.md")
def prompt_md(u: dict = Depends(auth.require_user)):
    p = config.ROOT / "PROMPT.md"
    if not p.is_file():
        raise HTTPException(404, "PROMPT.md fehlt")
    return FileResponse(p, media_type="text/markdown; charset=utf-8", filename="PROMPT.md")


# ------------------------------------------------------------------ Projekte

def _project_public(p: dict, detail: bool = False) -> dict:
    out = dict(p)
    out["n_photos"] = db.q1("SELECT COUNT(*) n FROM photos WHERE project_id=?", (p["id"],))["n"]
    out["n_measurements"] = db.q1("SELECT COUNT(*) n FROM measurements WHERE project_id=? AND accepted=1", (p["id"],))["n"]
    fmt = _project_format(p["id"])
    out["format"] = fmt
    out["factors"] = _factors(p)
    if detail:
        out["photos"] = [_photo_public(ph) for ph in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (p["id"],))]
        out["measurements"] = [_meas_public(m) for m in
                               db.q("SELECT * FROM measurements WHERE project_id=? ORDER BY seq", (p["id"],))]
        out["grid_h"] = _grid_h(fmt)
    return out


@app.get("/api/projects")
def projects(u: dict = Depends(auth.require_user)):
    return [_project_public(p) for p in
            db.q("SELECT * FROM projects WHERE user_id=? ORDER BY archived, id DESC", (u["id"],))]


class ProjectIn(BaseModel):
    name: str = Field(default="", max_length=120)


@app.post("/api/projects")
def project_new(body: ProjectIn, u: dict = Depends(auth.require_user)):
    name = body.name.strip() or f"Projekt {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    pid = db.ex("INSERT INTO projects(user_id,name,created_at) VALUES (?,?,?)", (u["id"], name, db.now()))
    return _project_public(db.q1("SELECT * FROM projects WHERE id=?", (pid,)), True)


@app.get("/api/projects/current")
def project_current(u: dict = Depends(auth.require_user)):
    p = db.q1("SELECT * FROM projects WHERE user_id=? AND archived=0 ORDER BY id DESC LIMIT 1", (u["id"],))
    if not p:
        pid = db.ex("INSERT INTO projects(user_id,name,created_at) VALUES (?,?,?)",
                    (u["id"], f"Projekt {datetime.now().strftime('%d.%m.%Y')}", db.now()))
        p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    return _project_public(p, True)


@app.get("/api/projects/{pid}")
def project_get(pid: int, u: dict = Depends(auth.require_user)):
    return _project_public(_own_project(pid, u), True)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    ctrl_x: float | None = None
    ctrl_y: float | None = None
    clear_ctrl: bool = False
    archived: bool | None = None


def _recompute(project: dict):
    fx, fy = _factors(project)
    for m in db.q("SELECT * FROM measurements WHERE project_id=?", (project["id"],)):
        d = db.jload(m["data"], {}) or {}
        if d.get("points") and m["source"] != "manual" and not d.get("ai_value"):
            v = geom.compute(m["kind"], d["points"], fx, fy)
            if v is not None:
                db.ex("UPDATE measurements SET value=? WHERE id=?", (v, m["id"]))


@app.patch("/api/projects/{pid}")
def project_patch(pid: int, body: ProjectPatch, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    for k in ("ctrl_x", "ctrl_y"):
        v = getattr(body, k)
        ref = 100.0 if k == "ctrl_x" else (_grid_h(_project_format(pid)) or 230.0)
        if v is not None and not (0.9 * ref <= v <= 1.1 * ref):
            raise HTTPException(400, f"Kontrollwert {v:g} mm ist unplausibel (erwartet um {ref:g} mm).")
    _finite(body.ctrl_x, "Kontrollwert"); _finite(body.ctrl_y, "Kontrollwert")  # noqa: E702
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
    p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    _recompute(p)
    return _project_public(p, True)


def _delete_project_files(pid: int):
    for ph in db.q("SELECT id FROM photos WHERE project_id=?", (pid,)):
        shutil.rmtree(_photo_dir(ph["id"]), ignore_errors=True)


@app.delete("/api/projects/{pid}")
def project_delete(pid: int, u: dict = Depends(auth.require_user)):
    _own_project(pid, u)
    _delete_project_files(pid)
    db.ex("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


# ------------------------------------------------------------------ Fotos

VIEWS = ("top", "tilted", "gauge", "overview")


def _analyze_store(phid: int, img, fmt: str | None) -> dict:
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
        a["rect"] = {"pxmm": vision.PX_PER_MM, "w_mm": gw, "h_mm": gh, "w": rect.shape[1], "h": rect.shape[0]}
    if a.get("gauge") and len(a["gauge"]["ids"]) >= 2:
        g, (x0, x1, y0, y1) = vision.rectify_gauge(img, a["gauge"])
        (d / "gauge.jpg").write_bytes(vision.encode_jpg(g, 90))
        a["gauge_rect"] = {"pxmm": vision.PX_PER_MM, "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                           "w": g.shape[1], "h": g.shape[0]}
    return a


@app.post("/api/projects/{pid}/photos")
def photo_upload(pid: int, file: UploadFile = File(...), view: str = Form("top"), format: str = Form(""),
                 u: dict = Depends(auth.require_user)):
    _own_project(pid, u)
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
        a = _analyze_store(phid, img, format if format in matgen.FORMATS else None)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(d, ignore_errors=True)
        db.ex("DELETE FROM photos WHERE id=?", (phid,))
        raise HTTPException(400, f"Auswertung fehlgeschlagen: {e}") from None
    db.ex("UPDATE photos SET format=?, status=?, max_err=?, analysis=? WHERE id=?",
          (a.get("format"), a["status"], a.get("max_err_mm"), db.jdump(a), phid))
    return _photo_public(db.q1("SELECT * FROM photos WHERE id=?", (phid,)))


class PhotoPatch(BaseModel):
    view: str | None = None
    format: str | None = None


@app.patch("/api/photos/{phid}")
def photo_patch(phid: int, body: PhotoPatch, u: dict = Depends(auth.require_user)):
    ph, _ = _own_photo(phid, u)
    if body.view in VIEWS:
        db.ex("UPDATE photos SET view=? WHERE id=?", (body.view, phid))
    if body.format is not None and body.format != ph["format"]:
        img = vision.load_image((_photo_dir(phid) / "orig.jpg").read_bytes())
        a = _analyze_store(phid, img, body.format if body.format in matgen.FORMATS else None)
        db.ex("UPDATE photos SET format=?, status=?, max_err=?, analysis=? WHERE id=?",
              (a.get("format"), a["status"], a.get("max_err_mm"), db.jdump(a), phid))
    return _photo_public(db.q1("SELECT * FROM photos WHERE id=?", (phid,)))


@app.delete("/api/photos/{phid}")
def photo_delete(phid: int, u: dict = Depends(auth.require_user)):
    _own_photo(phid, u)
    shutil.rmtree(_photo_dir(phid), ignore_errors=True)
    db.ex("DELETE FROM photos WHERE id=?", (phid,))
    return {"ok": True}


@app.get("/api/photos/{phid}/{kind}.jpg")
def photo_file(phid: int, kind: str, u: dict = Depends(auth.require_user)):
    _own_photo(phid, u)
    if kind not in ("orig", "overlay", "rect", "gauge", "thumb"):
        raise HTTPException(404, "Unbekannte Datei")
    p = _photo_dir(phid) / f"{kind}.jpg"
    if not p.is_file():
        raise HTTPException(404, "Datei nicht vorhanden")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


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
        photo, pp = _own_photo(body.photo_id, u)
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
    unc = body.unc if body.unc is not None else (_default_unc(photo, body.view) if source == "user" else 0.1)
    seq = _next_seq(pid)
    unit = "°" if body.kind == "angle" else "mm"
    data = {"view": body.view if body.view in ("top", "gauge") else "top", "points": pts, "note": body.note}
    mid = db.ex("""INSERT INTO measurements(project_id,photo_id,seq,label,kind,value,unit,unc,data,critical,caliper,fit,
                   source,accepted,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (pid, body.photo_id, seq, body.label.strip() or KIND_LABEL[body.kind], body.kind, value, unit, unc,
                 db.jdump(data), int(body.critical), body.caliper, body.fit, source, db.now()))
    return _meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,)))


@app.patch("/api/measurements/{mid}")
def meas_patch(mid: int, body: MeasPatch, u: dict = Depends(auth.require_user)):
    m, p = _own_meas(mid, u)
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
    if body.unc is not None:
        sets["unc"] = max(0.0, body.unc)
    if body.critical is not None:
        sets["critical"] = int(body.critical)
    if body.clear_caliper:
        sets["caliper"] = None
    elif body.caliper is not None:
        sets["caliper"] = body.caliper
    if body.fit is not None:
        sets["fit"] = body.fit or None
    if body.note is not None:
        d["note"] = body.note
    if body.accepted is not None:
        sets["accepted"] = int(body.accepted)
    sets["data"] = db.jdump(d)
    cols = ", ".join(f"{k}=?" for k in sets)
    db.ex(f"UPDATE measurements SET {cols} WHERE id=?", (*sets.values(), mid))
    return _meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,)))


@app.delete("/api/measurements/{mid}")
def meas_delete(mid: int, u: dict = Depends(auth.require_user)):
    _own_meas(mid, u)
    db.ex("DELETE FROM measurements WHERE id=?", (mid,))
    return {"ok": True}


@app.post("/api/projects/{pid}/measurements/accept-all")
def meas_accept_all(pid: int, u: dict = Depends(auth.require_user)):
    _own_project(pid, u)
    db.ex("UPDATE measurements SET accepted=1 WHERE project_id=? AND source='claude'", (pid,))
    return {"ok": True}


@app.post("/api/projects/{pid}/measurements/discard-suggestions")
def meas_discard(pid: int, u: dict = Depends(auth.require_user)):
    _own_project(pid, u)
    db.ex("DELETE FROM measurements WHERE project_id=? AND source='claude' AND accepted=0", (pid,))
    return {"ok": True}


class SuggestIn(BaseModel):
    photo_id: int | None = None
    hint: str = Field(default="", max_length=500)


@app.post("/api/projects/{pid}/suggest")
def meas_suggest(pid: int, body: SuggestIn, request: Request, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    if not settings.ai_enabled():
        raise HTTPException(503, "KI ist nicht eingerichtet: Anthropic-API-Schlüssel fehlt (Verwaltung → Einstellungen).")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = db.q1("SELECT COUNT(*) n FROM audit WHERE user_id=? AND action='suggest' AND substr(ts,1,10)=?",
              (u["id"], today))["n"]
    if u["role"] != "admin" and n >= 30:
        raise HTTPException(429, "Tageslimit für Maßvorschläge erreicht (30).")
    photos = db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,))
    if body.photo_id:
        photos = [ph for ph in photos if ph["id"] == body.photo_id] + [ph for ph in photos if ph["id"] != body.photo_id]
    content: list[dict] = []
    used_photo = None
    n_img = 0
    for ph in photos:
        d = _photo_dir(ph["id"])
        if used_photo is None and (d / "rect.jpg").is_file():
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
    db.ex("DELETE FROM measurements WHERE project_id=? AND source='claude' AND accepted=0", (pid,))
    out = []
    for it in items:
        seq = _next_seq(pid)
        kind = it["kind"] if it["kind"] in geom.KINDS else "length"
        value = it["value"] if kind == "angle" else round(it["value"] * f, 3)
        data = {"view": it["view"], "points": it["points"] or [], "reason": it["reason"], "unsure": it["unsure"],
                "ai_value": True}
        mid = db.ex("""INSERT INTO measurements(project_id,photo_id,seq,label,kind,value,unit,unc,data,source,accepted,
                       reason,created_at) VALUES (?,?,?,?,?,?,?,?,?,'claude',0,?,?)""",
                    (pid, used_photo["id"], seq, it["label"], kind, value, it["unit"], it["unc"], db.jdump(data),
                     it["reason"], db.now()))
        out.append(_meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,))))
    return {"suggestions": out, "usage": usage}


def _csv(pid: int) -> str:
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY seq", (pid,))

    def n(v):
        return "" if v is None else f"{v:.3f}".rstrip("0").rstrip(".").replace(".", ",")

    lines = ["ID;Bezeichnung;Art;Wert;Einheit;Unsicherheit;Schieblehre;kritisch;Passung;Quelle;Ansicht;Punkte (mm)"]
    for m in rows:
        d = db.jload(m["data"], {}) or {}
        pts = " ".join(f"{p[0]:.2f}/{p[1]:.2f}" for p in d.get("points") or [])
        safe_txt = lambda t: ("'" + t) if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t  # noqa: E731
        cells = [f"M{m['seq']}", safe_txt(m["label"]), KIND_LABEL.get(m["kind"], m["kind"]), n(m["value"]), m["unit"],
                 n(m["unc"]),
                 n(m["caliper"]), "ja" if m["critical"] else "", safe_txt(m["fit"] or ""), m["source"], d.get("view", ""), pts]
        lines.append(";".join('"' + str(c).replace('"', '""') + '"' if any(x in str(c) for x in ';"\n') else str(c)
                              for c in cells))
    return "﻿" + "\r\n".join(lines) + "\r\n"


@app.get("/api/projects/{pid}/measurements.csv")
def meas_csv(pid: int, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    safe = _ascii_name(p["name"], "Projekt")
    return Response(_csv(pid), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": _disposition(f"{safe}_Masse.csv")})


# ------------------------------------------------------------------ CAD-Auftraege

class JobIn(BaseModel):
    project_id: int | None = None
    name: str = Field(default="", max_length=120)
    request: str = Field(default="", max_length=6000)
    process: str = "fdm"
    material: str = Field(default="", max_length=80)
    tolerance: str = Field(default="", max_length=80)
    photo_ids: list[int] | None = None
    cutter_d: float | None = None
    setups: str = Field(default="", max_length=40)
    fits: list[dict] | None = None
    extra: str = Field(default="", max_length=2000)


@app.post("/api/jobs")
def job_create(body: JobIn, u: dict = Depends(auth.require_user)):
    project = _own_project(body.project_id, u) if body.project_id else None
    if not project and not body.request.strip():
        raise HTTPException(400, "Ohne Projekt braucht der Auftrag eine Beschreibung.")
    name = body.name.strip() or (project["name"] if project else "CAD-Auftrag")
    fits = [{"id": str(f.get("id", ""))[:8], "fit": str(f.get("fit", ""))[:20], "depth": str(f.get("depth", ""))[:30]}
            for f in (body.fits or [])[:30] if isinstance(f, dict)]
    jid = jobs.create(u, project, name, body.request, {
        "process": body.process, "material": body.material.strip(), "tolerance": body.tolerance.strip(),
        "photo_ids": body.photo_ids, "cutter_d": body.cutter_d, "setups": body.setups.strip(), "fits": fits,
        "extra": body.extra.strip()})
    return jobs.job_public(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), True)


@app.get("/api/jobs")
def job_list(all: int = 0, u: dict = Depends(auth.require_user)):
    if all and u["role"] == "admin":
        rows = db.q("SELECT j.*, u.username FROM jobs j JOIN users u ON u.id=j.user_id ORDER BY j.id DESC LIMIT 500")
    else:
        rows = db.q("SELECT j.*, ? AS username FROM jobs j WHERE user_id=? ORDER BY id DESC LIMIT 500",
                    (u["username"], u["id"]))
    return [{**jobs.job_public(r), "username": r["username"]} for r in rows]


@app.get("/api/jobs/{jid}")
def job_get(jid: int, u: dict = Depends(auth.require_user)):
    return jobs.job_public(_own_job(jid, u), True)


class IterIn(BaseModel):
    text: str = Field(max_length=4000)


@app.post("/api/jobs/{jid}/iterate")
def job_iterate(jid: int, body: IterIn, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u)
    if not body.text.strip():
        raise HTTPException(400, "Bitte den Änderungswunsch beschreiben.")
    jobs.iterate(u, j, body.text)
    return jobs.job_public(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), True)


@app.post("/api/jobs/{jid}/cancel")
def job_cancel(jid: int, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u)
    jobs.cancel(j)
    return jobs.job_public(db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), True)


@app.delete("/api/jobs/{jid}")
def job_delete(jid: int, u: dict = Depends(auth.require_user)):
    jobs.delete(_own_job(jid, u))
    return {"ok": True}


FILE_TYPES = {"model.step": "application/step", "model.stl": "model/stl", "model.py": "text/x-python; charset=utf-8",
              "outline.json": "application/json"}


def _file_base(j: dict) -> str:
    return _ascii_name(j["name"], f"auftrag_{j['id']}")


@app.get("/api/jobs/{jid}/v/{ver}/{name}")
def job_file(jid: int, ver: int, name: str, download: int = 0, u: dict = Depends(auth.require_user)):
    j = _own_job(jid, u)
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
                "claude": meta, "pruefung": checks, "ergebnis": result}
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
