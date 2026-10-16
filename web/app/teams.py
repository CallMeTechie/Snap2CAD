"""Teams mit gemeinsamen Bibliotheken: Verwaltung, Einladungen, Rollen und Austritt (Spec Teams §3)."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import access, auth, db

router = APIRouter()
ROLES = ("leiter", "mitglied", "lesend")
ROLE_TEXT = {"leiter": "Leiter", "mitglied": "Mitglied", "lesend": "Lesend"}
INVITES_PER_HOUR = 20


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def team_text(t: dict) -> str:
    return f"Team {t['id']} „{t['name']}“"


def _audit(action: str, detail: str, u: dict, request: Request | None = None):
    db.audit(action, detail, user_id=u["id"], actor=u["username"], ip=auth.client_ip(request) if request else None)


def _clean_name(raw: str) -> str:
    name = (raw or "").strip()
    if not 1 <= len(name) <= 80:
        raise HTTPException(400, "Der Teamname muss 1 bis 80 Zeichen lang sein.")
    # Steuerzeichen (Zeilenumbruch, Tab, NUL …), Format- (Richtung, Nullbreite) und Zeilen-/Absatztrenner
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in name):
        raise HTTPException(400, "Der Teamname enthält unzulässige Zeichen.")
    return name


def _role(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(400, "Unbekannte Rolle")
    return role


def n_projects(tid: int) -> int:
    return db.q1("SELECT COUNT(*) n FROM projects WHERE team_id=?", (tid,))["n"]


def _leaders(tid: int) -> int:
    return db.q1("SELECT COUNT(*) n FROM team_members WHERE team_id=? AND role='leiter'", (tid,))["n"]


def _members(tid: int) -> list[dict]:
    return db.q("""SELECT m.user_id, u.username, u.display_name, m.role, m.joined_at FROM team_members m
                   JOIN users u ON u.id=m.user_id WHERE m.team_id=? ORDER BY m.joined_at, m.user_id""", (tid,))


def _open_invites(tid: int) -> list[dict]:
    return db.q("""SELECT i.id, i.user_id, u.username, i.role, b.username invited_by_name, i.created_at
                   FROM team_invites i JOIN users u ON u.id=i.user_id LEFT JOIN users b ON b.id=i.invited_by
                   WHERE i.team_id=? AND i.status='offen' ORDER BY i.id""", (tid,))


def detail(t: dict, my_role: str | None, with_invites: bool) -> dict:
    """Team mit Mitgliedern; offene Einladungen nur fuer Leiter und Admin. Keine Projektinhalte (Spec §5, §8)."""
    return {"id": t["id"], "name": t["name"], "created_at": t["created_at"], "my_role": my_role,
            "n_projects": n_projects(t["id"]), "members": _members(t["id"]),
            "invites": _open_invites(t["id"]) if with_invites else []}


def _member(tid: int, uid: int) -> dict:
    m = db.q1("""SELECT m.*, u.username FROM team_members m JOIN users u ON u.id=m.user_id
                 WHERE m.team_id=? AND m.user_id=?""", (tid, uid))
    if not m:
        raise HTTPException(404, "Mitglied nicht gefunden")
    return m


def _revoke(t: dict, iid: int, u: dict, request: Request):
    with db.atomic():
        inv = db.q1("SELECT i.*, x.username FROM team_invites i JOIN users x ON x.id=i.user_id WHERE i.id=? AND i.team_id=?",
                    (iid, t["id"]))
        if not inv:
            raise HTTPException(404, "Einladung nicht gefunden")
        if inv["status"] != "offen":
            raise HTTPException(409, "Einladung nicht mehr offen")
        db.ex("UPDATE team_invites SET status='zurueckgezogen', decided_at=? WHERE id=?", (db.now(), iid))
        _audit("team_invite_revoked", f"{team_text(t)}: Einladung an {inv['username']} zurückgezogen", u, request)
    return {"ok": True}


def _drop_invites_of(tid: int, uid: int):
    """Offene Einladungen, die uid in diesem Team ausgesprochen hat, zurueckziehen – wenn uid nicht mehr Leiter oder
    nicht mehr Mitglied ist (herabgestuft, entfernt, ausgetreten). Laeuft in der Transaktion des Aufrufers."""
    db.ex("UPDATE team_invites SET status='zurueckgezogen', decided_at=? WHERE team_id=? AND invited_by=? AND status='offen'",
          (db.now(), tid, uid))


def _my_invite(iid: int, u: dict) -> dict:
    """Nur der Eingeladene; fremde Einladungen sind nicht erkennbar (404)."""
    inv = db.q1("SELECT * FROM team_invites WHERE id=? AND user_id=?", (iid, u["id"]))
    if not inv:
        raise HTTPException(404, "Einladung nicht gefunden")
    if inv["status"] != "offen":
        raise HTTPException(409, "Einladung nicht mehr offen")
    return inv


class TeamIn(BaseModel):
    name: str = Field(max_length=200)


class TeamInviteIn(BaseModel):
    username: str = Field(max_length=64)
    role: str = "mitglied"


class RoleIn(BaseModel):
    role: str = Field(max_length=20)


@router.get("/api/teams")
def teams_list(u: dict = Depends(auth.require_user)):
    """Meine Teams mit Rolle, Mitglieder- und Projektzahl; dazu meine offenen Einladungen."""
    rows = db.q("""SELECT t.id, t.name, t.created_at, m.role my_role,
                   (SELECT COUNT(*) FROM team_members x WHERE x.team_id=t.id) n_members,
                   (SELECT COUNT(*) FROM projects p WHERE p.team_id=t.id) n_projects
                   FROM teams t JOIN team_members m ON m.team_id=t.id AND m.user_id=?
                   ORDER BY t.name COLLATE NOCASE, t.id""", (u["id"],))
    invites = db.q("""SELECT i.id, i.team_id, t.name team_name, i.role, b.username invited_by_name, i.created_at
                      FROM team_invites i JOIN teams t ON t.id=i.team_id LEFT JOIN users b ON b.id=i.invited_by
                      WHERE i.user_id=? AND i.status='offen' ORDER BY i.id""", (u["id"],))
    return {"teams": rows, "invites": invites}


@router.post("/api/teams")
def team_create(body: TeamIn, request: Request, u: dict = Depends(auth.require_user)):
    name = _clean_name(body.name)
    with db.atomic():
        tid = db.ex("INSERT INTO teams(name,created_by,created_at) VALUES (?,?,?)", (name, u["id"], db.now()))
        db.ex("INSERT INTO team_members(team_id,user_id,role,joined_at) VALUES (?,?,'leiter',?)", (tid, u["id"], db.now()))
        t = db.q1("SELECT * FROM teams WHERE id=?", (tid,))
        _audit("team_created", f"{team_text(t)} gegründet", u, request)
    return detail(t, "leiter", True)


@router.get("/api/teams/{tid}")
def team_get(tid: int, u: dict = Depends(auth.require_user)):
    t = access.require_team(u, tid, "lesend")
    return detail(t, t["my_role"], t["my_role"] == "leiter")


@router.patch("/api/teams/{tid}")
def team_rename(tid: int, body: TeamIn, request: Request, u: dict = Depends(auth.require_user)):
    access.require_team(u, tid, "leiter")
    name = _clean_name(body.name)
    with db.atomic():   # Leiter in der Transaktion erneut pruefen: kein Wettlauf mit Herabstufen oder Austritt
        t = access.require_team(u, tid, "leiter")
        if name != t["name"]:
            db.ex("UPDATE teams SET name=? WHERE id=?", (name, tid))
            _audit("team_renamed", f"Team {tid}: „{t['name']}“ → „{name}“", u, request)
        t = access.require_team(u, tid, "leiter")
    return detail(t, t["my_role"], True)


@router.delete("/api/teams/{tid}")
def team_delete(tid: int, request: Request, u: dict = Depends(auth.require_user)):
    """Nur ein leeres Team (Spec §3); mit Inhalt loescht nur der Admin (teams.admin_team_delete)."""
    with db.atomic():
        t = access.require_team(u, tid, "leiter")
        n = n_projects(tid)
        if n:
            raise HTTPException(409, f"Das Team hat noch {plural(n, 'Projekt', 'Projekte')}")
        db.ex("DELETE FROM teams WHERE id=?", (tid,))
        _audit("team_deleted", f"{team_text(t)} gelöscht (0 Projekte)", u, request)
    return {"ok": True}


@router.post("/api/teams/{tid}/invites")
def team_invite(tid: int, body: TeamInviteIn, request: Request, u: dict = Depends(auth.require_user)):
    """Einladung ueber den exakten Benutzernamen (Gross/klein egal). Hoechstens 20 Versuche je Benutzer und Stunde,
    gezaehlt ueber team_invite und team_invite_failed – auch abgewiesene, damit Namen nicht durchprobiert werden."""
    role = _role(body.role)
    name = body.username.strip()
    with db._lock:   # Zaehlen, Pruefen und Eintragen ohne Wettlauf; ein abgewiesener Versuch bleibt protokolliert
        t = access.require_team(u, tid, "leiter")   # unter der Sperre: kein Wettlauf mit Herabstufen oder Austritt
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
        n = db.q1("SELECT COUNT(*) n FROM audit WHERE user_id=? AND action IN ('team_invite','team_invite_failed') "
                  "AND ts>=?", (u["id"], since))["n"]
        if n >= INVITES_PER_HOUR:
            raise HTTPException(429, f"Zu viele Einladungen – höchstens {INVITES_PER_HOUR} je Stunde.")
        target = db.q1("SELECT * FROM users WHERE username=?", (name,)) if name else None   # Spalte COLLATE NOCASE
        problem = None
        if not target or target["status"] != "active":
            problem = (404, "Benutzer nicht gefunden", "unbekannt" if not target else "deaktiviert")
        elif target["id"] == u["id"]:
            problem = (400, "Du kannst dich nicht selbst einladen.", "sich selbst")
        elif access.team_role(target["id"], tid):
            problem = (409, "Ist bereits Mitglied dieses Teams.", "schon Mitglied")
        elif db.q1("SELECT id FROM team_invites WHERE team_id=? AND user_id=? AND status='offen'", (tid, target["id"])):
            problem = (409, "Es gibt schon eine offene Einladung für diesen Benutzer.", "doppelt")
        if problem:
            _audit("team_invite_failed", f"{team_text(t)}: {name[:64]} – {problem[2]}", u, request)
            raise HTTPException(problem[0], problem[1])
        with db.atomic():
            iid = db.ex("INSERT INTO team_invites(team_id,user_id,role,invited_by,created_at) VALUES (?,?,?,?,?)",
                        (tid, target["id"], role, u["id"], db.now()))
            _audit("team_invite", f"{team_text(t)}: {target['username']} als {ROLE_TEXT[role]} eingeladen", u, request)
    return {"id": iid, "user_id": target["id"], "username": target["username"], "role": role, "status": "offen"}


@router.delete("/api/teams/{tid}/invites/{iid}")
def team_invite_revoke(tid: int, iid: int, request: Request, u: dict = Depends(auth.require_user)):
    return _revoke(access.require_team(u, tid, "leiter"), iid, u, request)


@router.post("/api/team-invites/{iid}/accept")
def team_invite_accept(iid: int, request: Request, u: dict = Depends(auth.require_user)):
    with db.atomic():   # nur bei Status offen, in einer Transaktion (Spec §3)
        inv = _my_invite(iid, u)
        t = db.q1("SELECT * FROM teams WHERE id=?", (inv["team_id"],))
        db.ex("UPDATE team_invites SET status='angenommen', decided_at=? WHERE id=?", (db.now(), iid))
        have = access.team_role(u["id"], t["id"])
        if have:      # schon Mitglied (z. B. vom Admin direkt aufgenommen): Rolle bleibt, die Einladung ist erledigt
            text = f"hat angenommen, war bereits Mitglied ({ROLE_TEXT[have]})"
        else:
            db.ex("INSERT INTO team_members(team_id,user_id,role,joined_at) VALUES (?,?,?,?)",
                  (t["id"], u["id"], inv["role"], db.now()))
            text = f"ist beigetreten ({ROLE_TEXT[inv['role']]})"
        _audit("team_invite_accepted", f"{team_text(t)}: {u['username']} {text}", u, request)
    t = access.require_team(u, inv["team_id"], "lesend")
    return detail(t, t["my_role"], t["my_role"] == "leiter")


@router.post("/api/team-invites/{iid}/decline")
def team_invite_decline(iid: int, request: Request, u: dict = Depends(auth.require_user)):
    with db.atomic():
        inv = _my_invite(iid, u)
        t = db.q1("SELECT * FROM teams WHERE id=?", (inv["team_id"],))
        db.ex("UPDATE team_invites SET status='abgelehnt', decided_at=? WHERE id=?", (db.now(), iid))
        _audit("team_invite_declined", f"{team_text(t)}: {u['username']} hat abgelehnt", u, request)
    return {"ok": True}


@router.patch("/api/teams/{tid}/members/{uid}")
def team_member_role(tid: int, uid: int, body: RoleIn, request: Request, u: dict = Depends(auth.require_user)):
    role = _role(body.role)
    with db.atomic():
        t = access.require_team(u, tid, "leiter")
        m = _member(tid, uid)
        if m["role"] == "leiter" and role != "leiter" and _leaders(tid) <= 1:
            raise HTTPException(409, "Erst einen anderen Leiter bestimmen")
        if role != m["role"]:
            db.ex("UPDATE team_members SET role=? WHERE team_id=? AND user_id=?", (role, tid, uid))
            if role != "leiter":
                _drop_invites_of(tid, uid)          # kein Leiter mehr: seine offenen Einladungen gelten nicht weiter
            _audit("team_role", f"{team_text(t)}: {m['username']} → {ROLE_TEXT[role]}", u, request)
    t = access.require_team(u, tid, "lesend")   # hat sich der Leiter selbst herabgestuft, gilt die neue Rolle
    return detail(t, t["my_role"], t["my_role"] == "leiter")


@router.delete("/api/teams/{tid}/members/{uid}")
def team_member_remove(tid: int, uid: int, request: Request, u: dict = Depends(auth.require_user)):
    """Leiter entfernen andere; jeder kann austreten. Team-Projekte bleiben im Team (Spec §3)."""
    with db.atomic():
        t = access.require_team(u, tid, "lesend")
        if uid != u["id"] and t["my_role"] != "leiter":
            raise HTTPException(403, access.DENY_LEADER)
        m = _member(tid, uid)
        others = db.q1("SELECT COUNT(*) n FROM team_members WHERE team_id=? AND user_id<>?", (tid, uid))["n"]
        if others == 0:      # letztes Mitglied: nur ein leeres Team, das dabei geloescht wird
            n = n_projects(tid)
            if n:
                raise HTTPException(409, f"Das Team hat noch {plural(n, 'Projekt', 'Projekte')} – erst löschen oder verschieben")
            db.ex("DELETE FROM teams WHERE id=?", (tid,))
            _audit("team_left", f"{team_text(t)}: {m['username']} ausgetreten", u, request)
            _audit("team_deleted", f"{team_text(t)} gelöscht (letztes Mitglied ausgetreten, 0 Projekte)", u, request)
            return {"ok": True, "team_deleted": True}
        if m["role"] == "leiter" and _leaders(tid) <= 1:
            raise HTTPException(409, "Erst einen anderen Leiter bestimmen")
        db.ex("DELETE FROM team_members WHERE team_id=? AND user_id=?", (tid, uid))
        _drop_invites_of(tid, uid)                  # entfernt oder ausgetreten: offene Einladungen zurueckziehen
        if uid == u["id"]:
            _audit("team_left", f"{team_text(t)}: {m['username']} ausgetreten", u, request)
        else:
            _audit("team_member_removed", f"{team_text(t)}: {m['username']} entfernt", u, request)
    return {"ok": True, "team_deleted": False}
