"""Pruefung vor dem CAD-Auftrag (Spec 2026-10-15 §2.1)."""
from __future__ import annotations

import hashlib
import json
import threading

from . import ai, db, jobs

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def lock_for(pid: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.Lock())


def _r(v):
    return round(v, 2) if isinstance(v, float) else v


def cad_hash(project: dict, photo_ids: list[int] | None, part_id: int | None) -> str:
    """Pruefsumme des Projektstands; photo_ids=None = alle Fotos zum Zeitpunkt der Berechnung (Spec §2.1)."""
    pid = project["id"]
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,))
              if photo_ids is None or p["id"] in photo_ids]
    al = []
    for p in photos:
        b = (db.jload(p["analysis"], {}) or {}).get("bottom_align") or {}
        al.append([p["id"], p["view"], p["format"], p["status"], b.get("rot"), _r(b.get("dx")), _r(b.get("dy"))])
    ms = []
    for m in db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY id", (pid,)):
        d = db.jload(m["data"], {}) or {}
        ms.append([m["id"], m["kind"], _r(m["value"]), _r(m["caliper"]), _r(m["unc"]), m["part_id"], d.get("view"),
                   [[_r(x), _r(y)] for x, y in d.get("points") or []]])
    ps = []
    for t in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY id", (pid,)):
        d = db.jload(t["data"], {}) or {}
        ps.append([t["id"], t["label"], t["role"], [[_r(x), _r(y)] for x, y in d["polygon"]], d.get("hidden"),
                   d.get("holes"), d.get("same_as")])
    mat = ([project.get("color"), project.get("material"), project.get("transparent"), project.get("finish")]
           if project.get("material_user") else None)
    blob = json.dumps({"photos": al, "meas": ms, "parts": ps, "part_id": part_id, "material": mat}, sort_keys=True,
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def stored(project: dict) -> dict | None:
    return db.jload(project.get("cad_check"), None)


def public_check(project: dict) -> dict | None:
    s = stored(project)
    if not s:
        return None
    return {**s, "stale": cad_hash(project, s.get("photo_ids"), s.get("part_id")) != s.get("hash")}


def run_check(project: dict, photo_ids: list[int] | None, part_id: int | None, h: str) -> dict:
    """KI-Aufruf, Ergebnis speichern, Material uebernehmen (nur solange material_user=0 – auch wenn die
    Handeingabe waehrend des Aufrufs kam)."""
    pid = project["id"]
    picked = jobs.pick_images(pid, photo_ids)
    msgs = jobs.build_initial_message(project, "", {"photo_ids": photo_ids, "part_id": part_id, "for_check": True,
                                                    "images": picked})
    text, usage = ai.call(ai.CHECK_SYSTEM, msgs, max_tokens=6000)
    if usage.get("stop_reason") == "max_tokens" or ai._json_span(text, "{", "}") is None:
        raise ai.AIError("KI-Antwort unvollständig – bitte erneut prüfen.")
    res = ai.parse_check(text)
    out = {"items": res["items"], "material": res["material"],
           "images": [{"photo_id": i["photo_id"], "kind": i["kind"]} for i in picked],
           "photo_ids": photo_ids, "part_id": part_id, "hash": h, "checked_at": db.now()}
    with db.atomic():
        if res["material"]:
            m = res["material"]
            db.ex("UPDATE projects SET color=?, material=?, transparent=?, finish=? WHERE id=? AND material_user=0",
                  (m["color"], m["material"], m["transparent"], m["finish"], pid))
        db.ex("UPDATE projects SET cad_check=? WHERE id=?", (db.jdump(out), pid))
    return out
