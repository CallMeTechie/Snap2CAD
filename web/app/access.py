"""Rechte fuer Projekte, Fotos, Messungen, Teile, Auftraege und Teams – eine Stelle fuer alle Zugriffe (Spec Teams §2)."""
from __future__ import annotations

from fastapi import HTTPException

from . import db

ROLE_RANK = {"lesend": 1, "mitglied": 2, "leiter": 3}
DENY_WRITE = "Nur lesender Zugriff"
DENY_OWNER = "Nur der Ersteller oder ein Team-Leiter darf das"
DENY_LEADER = "Nur ein Team-Leiter darf das"
# Rechte je Rolle; Mitglieder duerfen delete/move zusaetzlich bei selbst angelegten Projekten (allowed).
# copy = „Kopieren aus diesem Projekt“ (Spec §2-Tabelle); manage aus Spec §2 entfaellt (keine Route braucht es)
_RIGHTS = {
    "besitzer": frozenset({"read", "write", "delete", "move", "copy"}),
    "leiter": frozenset({"read", "write", "delete", "move", "copy"}),
    "mitglied": frozenset({"read", "write", "copy"}),
    "lesend": frozenset({"read"}),
    "admin": frozenset({"read", "write", "delete"}),
}
NEEDS = frozenset().union(*_RIGHTS.values())


def team_role(user_id: int | None, team_id: int | None) -> str | None:
    if user_id is None or team_id is None:
        return None
    r = db.q1("SELECT role FROM team_members WHERE team_id=? AND user_id=?", (team_id, user_id))
    return r["role"] if r else None


def project_role(user: dict, project: dict) -> str | None:
    """"besitzer" | "leiter" | "mitglied" | "lesend" | "admin" | None. "admin" nur fuer private Projekte anderer;
    in Team-Projekten gilt fuer einen Admin seine Team-Rolle (ohne Mitgliedschaft: None)."""
    if project.get("team_id") is None:
        if project.get("user_id") is not None and project["user_id"] == user["id"]:
            return "besitzer"
        return "admin" if user.get("role") == "admin" else None
    return team_role(user["id"], project["team_id"])


def allowed(user: dict, project: dict, need: str, role: str | None = None) -> bool:
    role = role if role is not None else project_role(user, project)
    if role is None:
        return False
    if need in _RIGHTS[role]:
        return True
    return role == "mitglied" and need in ("delete", "move") and project.get("user_id") == user["id"]


def _deny(role: str) -> HTTPException:
    return HTTPException(403, DENY_WRITE if role == "lesend" else DENY_OWNER)


def require_project(user: dict, project_id: int, need: str) -> dict:
    """Kein read -> 404 (fremde Projekte bleiben unsichtbar); read ohne das noetige Recht -> 403."""
    if need not in NEEDS:
        raise ValueError(need)
    p = db.q1("SELECT * FROM projects WHERE id=?", (project_id,))
    role = project_role(user, p) if p else None
    if role is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    if not allowed(user, p, need, role):
        raise _deny(role)
    return p


def require_photo(user: dict, photo_id: int, need: str) -> tuple[dict, dict]:
    ph = db.q1("SELECT * FROM photos WHERE id=?", (photo_id,))
    if not ph:
        raise HTTPException(404, "Foto nicht gefunden")
    return ph, require_project(user, ph["project_id"], need)


def require_meas(user: dict, mid: int, need: str) -> tuple[dict, dict]:
    m = db.q1("SELECT * FROM measurements WHERE id=?", (mid,))
    if not m:
        raise HTTPException(404, "Maß nicht gefunden")
    return m, require_project(user, m["project_id"], need)


def require_part(user: dict, part_id: int, need: str) -> tuple[dict, dict]:
    t = db.q1("SELECT * FROM parts WHERE id=?", (part_id,))
    if not t:
        raise HTTPException(404, "Teil nicht gefunden")
    return t, require_project(user, t["project_id"], need)


def job_role(user: dict, job: dict) -> str | None:
    """Auftraege folgen ihrem Projekt; ohne Projekt gehoeren sie dem Ersteller ("besitzer") und dem Admin."""
    p = db.q1("SELECT * FROM projects WHERE id=?", (job["project_id"],)) if job.get("project_id") else None
    if p is None:
        if job.get("user_id") is not None and job["user_id"] == user["id"]:
            return "besitzer"
        return "admin" if user.get("role") == "admin" else None
    return project_role(user, p)


def require_job(user: dict, job_id: int, need: str) -> dict:
    """read/write wie am Projekt. delete: Ersteller mit write, Leiter, Besitzer des privaten Projekts, Admin bei
    privaten und projektlosen Auftraegen. Vor jobs.delete aufrufen (jobs.delete prueft selbst nicht)."""
    if need not in ("read", "write", "delete"):
        raise ValueError(need)
    j = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    role = job_role(user, j) if j else None
    if role is None:
        raise HTTPException(404, "Auftrag nicht gefunden")
    # eine Rechtetabelle fuer Projekte und Auftraege; Mitglieder loeschen nur selbst angelegte Auftraege
    ok = need in _RIGHTS[role] or (need == "delete" and role == "mitglied" and j["user_id"] == user["id"])
    if not ok:
        raise _deny(role)
    return j


def require_team(user: dict, team_id: int, need: str) -> dict:
    """need = Mindestrolle "lesend" | "mitglied" | "leiter". Kein Mitglied -> 404 „Team nicht gefunden“."""
    if need not in ROLE_RANK:
        raise ValueError(need)
    t = db.q1("SELECT * FROM teams WHERE id=?", (team_id,))
    role = team_role(user["id"], team_id) if t else None
    if role is None:
        raise HTTPException(404, "Team nicht gefunden")
    if ROLE_RANK[role] < ROLE_RANK[need]:
        raise HTTPException(403, DENY_LEADER if need == "leiter" else DENY_WRITE)
    return {**t, "my_role": role}


def project_fields(user: dict, project: dict) -> dict:
    """Spec Teams §4: team_id, team_name, my_role, creator ({id, name} oder None = geloeschter Benutzer) und
    creator_is_member (nur bei Team-Projekten, sonst None); rights = was die Oberflaeche anbietet, aus allowed –
    dieselbe Regel wie die Routen (Plan, Lueckenfuellung 19)."""
    role = project_role(user, project)
    out = {"team_id": project.get("team_id"), "team_name": None, "my_role": role,
           "creator": None, "creator_is_member": None,
           "rights": {n: allowed(user, project, n, role) for n in ("write", "delete", "move", "copy")}}
    if project.get("user_id") is not None:
        c = db.q1("SELECT id, username, display_name FROM users WHERE id=?", (project["user_id"],))
        if c:
            out["creator"] = {"id": c["id"], "name": c["display_name"] or c["username"]}
    if project.get("team_id") is not None:
        t = db.q1("SELECT name FROM teams WHERE id=?", (project["team_id"],))
        out["team_name"] = t["name"] if t else None
        out["creator_is_member"] = team_role(project.get("user_id"), project["team_id"]) is not None
    return out


def job_fields(user: dict, job: dict) -> dict:
    """GET /api/jobs/{jid}: Rolle und Team des Projekts (Lesend-Modus der Auftragsseite)."""
    p = db.q1("SELECT team_id FROM projects WHERE id=?", (job["project_id"],)) if job.get("project_id") else None
    tid = p["team_id"] if p else None
    t = db.q1("SELECT name FROM teams WHERE id=?", (tid,)) if tid is not None else None
    return {"my_role": job_role(user, job), "team_id": tid, "team_name": t["name"] if t else None}
