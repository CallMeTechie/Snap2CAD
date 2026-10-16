"""Projekt kopieren: Zeilen, Dateien und je CAD-Auftrag die aktuelle gueltige Version (Spec Teams §4).

Ablauf: (1) ohne Sperre zuerst die Quellzeilen lesen, danach die Ordner nach DATA_DIR/tmp/copy-<zufall>/ kopieren
(DATA_DIR/tmp liegt auf dem Daten-Volume, rename ist atomar); (2) in einer Transaktion erneut lesen und vergleichen,
Zeilen anlegen und ids umschreiben – kein jobs._lock, kein jobs.delete, keine KI; (3) nach dem COMMIT die Ordner per
rename an ihren Platz, bei Fehler Rueckbau. tmp/copy-* wird bei jedem Fehler und beim Serverstart entfernt.
Die Rechte prueft der Aufrufer vorher und ueber guard erneut in der Transaktion (Wettlauf mit einem Austritt)."""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException

from . import config, db, jobs, projects

CHANGED = "Projekt wurde während des Kopierens geändert – bitte erneut kopieren"
FAILED = "Kopieren fehlgeschlagen – bitte erneut versuchen."
_photo_dir = projects.photo_dir   # eine Stelle fuer den Fotoordner


def tmp_root() -> Path:
    return config.DATA_DIR / "tmp"


def cleanup_tmp() -> None:
    """Reste abgebrochener Kopien entfernen (Serverstart)."""
    for d in tmp_root().glob("copy-*"):
        shutil.rmtree(d, ignore_errors=True)


def _no_tmp(_dir, names):
    """copytree-Filter: halbe Dateien (*.tmp) und symbolische Links (koennten aus dem Fotoordner hinauszeigen)."""
    return [n for n in names if n.endswith(".tmp") or (Path(_dir) / n).is_symlink()]


def _snapshot(pid: int) -> dict | None:
    """Vergleichsstand: Fotos (id, analysis, format, view) und Auftraege (id, current_version, deren Status)."""
    if not db.q1("SELECT id FROM projects WHERE id=?", (pid,)):
        return None
    photos = [tuple(r.values()) for r in db.q("SELECT id, analysis, format, view FROM photos WHERE project_id=? ORDER BY id",
                                              (pid,))]
    js = [tuple(r.values()) for r in db.q("SELECT j.id, j.current_version, v.status FROM jobs j LEFT JOIN job_versions v "
                                          "ON v.job_id=j.id AND v.version=j.current_version WHERE j.project_id=? "
                                          "ORDER BY j.id", (pid,))]
    return {"photos": photos, "jobs": js}


def _copy_dir(src: Path, dst: Path):
    """Ordner ohne *.tmp und ohne symbolische Links kopieren; fehlt er (oder ist er selbst ein Link), leer anlegen."""
    if src.is_dir() and not src.is_symlink():
        shutil.copytree(src, dst, ignore=_no_tmp)
    else:
        dst.mkdir(parents=True)


def _stage(tmp: Path, snap: dict):
    """(1) Dateien der Quelle nach tmp/copy-<zufall>/photos/<alt>/ und …/jobs/<alt>/v<n>/."""
    (tmp / "photos").mkdir(parents=True)
    (tmp / "jobs").mkdir()
    for phid, *_ in snap["photos"]:
        _copy_dir(_photo_dir(phid), tmp / "photos" / str(phid))
    for jid, cur, status in snap["jobs"]:
        if cur and status == "ok":
            _copy_dir(jobs.version_dir(jid, cur), tmp / "jobs" / str(jid) / f"v{cur}")


def _photo_of(path) -> int | None:
    """Alte Foto-id eines Bildverweises DATA_DIR/photos/<id>/<datei>, sonst None."""
    try:
        p = Path(path)
    except TypeError:
        return None
    name = p.parent.name
    if p.parent.parent != config.DATA_DIR / "photos" or not (name.isascii() and name.isdigit()):
        return None
    return int(name)


def _messages(raw: str, photo_map: dict[int, int]) -> list[dict]:
    """Erste Nutzernachricht der Quelle: image_ref.path auf die neuen Fotoordner, Beschriftung „Foto <id>“ direkt
    nach dem Bild auf die neue id; Bilder nicht mehr vorhandener Fotos entfallen samt Beschriftung."""
    msgs = db.jload(raw, []) or []
    first = next((m for m in msgs if isinstance(m, dict) and m.get("role") == "user"), None) if isinstance(msgs, list) else None
    if first is None:
        return []
    content = first.get("content")
    if not isinstance(content, list):
        return [{"role": "user", "content": content}]
    out, after = [], None          # after: alte id des vorigen Bildes (Beschriftung folgt); False = Bild entfallen
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "image_ref":
            old = _photo_of(b.get("path"))
            if old in photo_map:
                out.append({**b, "path": str(_photo_dir(photo_map[old]) / Path(b["path"]).name)})
                after = old
            else:
                after = False
            continue
        if after is False and b.get("type") == "text":
            after = None           # Beschriftung des entfallenen Bildes
            continue
        if after and b.get("type") == "text":
            b = {**b, "text": re.sub(rf"\bFoto {after}\b", f"Foto {photo_map[after]}", b.get("text") or "")}
        after = None
        out.append(b)
    return [{"role": "user", "content": out}]


def _insert(user: dict, src_pid: int, team_id: int | None, name: str | None):
    """(2) in db.atomic: Zeilen aus dem zweiten Lesen anlegen und alle ids umschreiben."""
    p = db.q1("SELECT * FROM projects WHERE id=?", (src_pid,))
    title = ((name or "").strip() or f"{p['name']} (Kopie)")[:120]
    new_pid = db.ex("""INSERT INTO projects(user_id,team_id,name,created_at,ctrl_x,ctrl_y,color,material,transparent,finish,
                       material_user) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (user["id"], team_id, title, db.now(), p["ctrl_x"], p["ctrl_y"], p["color"], p["material"],
                     p["transparent"], p["finish"], p["material_user"]))
    photos = db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (src_pid,))
    photo_map = {}
    for ph in photos:
        photo_map[ph["id"]] = db.ex("INSERT INTO photos(project_id,filename,view,format,status,max_err,analysis,created_at) "
                                    "VALUES (?,?,?,?,?,?,?,?)", (new_pid, ph["filename"], ph["view"], ph["format"],
                                                                 ph["status"], ph["max_err"], ph["analysis"], ph["created_at"]))
    for ph in photos:   # bottom_align.top_photo_id auf die neue id
        a = db.jload(ph["analysis"], None)
        al = a.get("bottom_align") if isinstance(a, dict) else None
        if isinstance(al, dict) and al.get("top_photo_id") is not None:
            al["top_photo_id"] = photo_map.get(al["top_photo_id"])
            db.ex("UPDATE photos SET analysis=? WHERE id=?", (db.jdump(a), photo_map[ph["id"]]))
    part_rows = [t for t in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY id", (src_pid,)) if t["photo_id"] in photo_map]
    part_map = {}
    for t in part_rows:
        part_map[t["id"]] = db.ex("INSERT INTO parts(project_id,photo_id,seq,label,role,data,source,scale,created_at) "
                                  "VALUES (?,?,?,?,?,?,?,?,?)", (new_pid, photo_map[t["photo_id"]], t["seq"], t["label"],
                                                                 t["role"], t["data"], t["source"], t["scale"], t["created_at"]))
    meas_map = {}
    for m in db.q("SELECT * FROM measurements WHERE project_id=? ORDER BY id", (src_pid,)):
        meas_map[m["id"]] = db.ex(
            """INSERT INTO measurements(project_id,photo_id,part_id,seq,label,kind,value,unit,unc,data,critical,caliper,fit,
               source,accepted,reason,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_pid, photo_map.get(m["photo_id"]), part_map.get(m["part_id"]), m["seq"], m["label"], m["kind"], m["value"],
             m["unit"], m["unc"], m["data"], m["critical"], m["caliper"], m["fit"], m["source"], m["accepted"], m["reason"],
             m["created_at"]))
    for t in part_rows:   # data.same_as auf neue Teil-ids, data.refs auf neue Mess-ids
        d = db.jload(t["data"], {}) or {}
        if not isinstance(d, dict):
            continue
        if "same_as" in d:
            d["same_as"] = part_map.get(d["same_as"])
        if "refs" in d:
            d["refs"] = [meas_map[i] for i in d.get("refs") or [] if i in meas_map]
        db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), part_map[t["id"]]))
    job_map = {}
    for j in db.q("SELECT * FROM jobs WHERE project_id=? ORDER BY id", (src_pid,)):
        v = db.q1("SELECT * FROM job_versions WHERE job_id=? AND version=?", (j["id"], j["current_version"])) \
            if j["current_version"] else None
        if not v or v["status"] != "ok":
            continue                                  # laufende oder fehlerhafte aktuelle Version: nicht kopieren
        req = db.jload(j["request"], {}) or {}
        if not isinstance(req, dict):
            req = {}
        if isinstance(req.get("photo_ids"), list):
            req["photo_ids"] = [photo_map[i] for i in req["photo_ids"] if i in photo_map]
        if req.get("part_id") is not None:
            req["part_id"] = part_map.get(req["part_id"])
        now = db.now()
        nj = db.ex("""INSERT INTO jobs(user_id,project_id,name,request,status,messages,current_version,created_at,updated_at,
                      run_by) VALUES (?,?,?,?,'done',?,1,?,?,?)""",
                   (user["id"], new_pid, j["name"], db.jdump(req), db.jdump(_messages(j["messages"], photo_map)), now, now,
                    user["id"]))
        text = f"Kopie von Auftrag {j['id']}, Version {v['version']}"
        db.ex("""INSERT INTO job_versions(job_id,version,trigger,request_text,code,meta,status,result,checks,usage,seconds,
                 created_at,user_id) VALUES (?,1,'copy',?,?,?,'ok',?,?,'{}',?,?,?)""",
              (nj, text, v["code"], v["meta"], v["result"], v["checks"], v["seconds"], now, user["id"]))
        jobs.log(nj, text)
        job_map[j["id"]] = (nj, v["version"])
    for r in db.q("SELECT * FROM model_dims WHERE project_id=? ORDER BY id", (src_pid,)):
        db.ex("INSERT INTO model_dims(project_id,label,label_norm,grp,value,job_id,dim_id,note,created_at) "
              "VALUES (?,?,?,?,?,?,?,?,?)",
              (new_pid, r["label"], r["label_norm"], r["grp"], r["value"],
               job_map[r["job_id"]][0] if r["job_id"] in job_map else None, r["dim_id"], r["note"], r["created_at"]))
    return new_pid, photo_map, job_map


def _place(tmp: Path, photo_map: dict, job_map: dict):
    """(3) nach dem COMMIT: Ordner per rename an ihren Platz (selbes Volume)."""
    for old, new in photo_map.items():
        os.rename(tmp / "photos" / str(old), _photo_dir(new))
    for old, (new, ver) in job_map.items():
        jobs.job_dir(new).mkdir(parents=True, exist_ok=True)
        os.rename(tmp / "jobs" / str(old) / f"v{ver}", jobs.version_dir(new, 1))


def _undo(new_pid: int, job_map: dict):
    """Rueckbau nach einem Fehler in (3): die neuen Auftraege per jobs.delete (ausserhalb von db.atomic; sie haben
    einen Ersteller und blieben sonst ohne Projekt stehen), dann Projektzeilen und Fotoordner wie beim Projekt-Loeschen."""
    for new, _ in job_map.values():
        j = db.q1("SELECT * FROM jobs WHERE id=?", (new,))
        if j:
            jobs.delete(j)
    projects.delete_projects([new_pid])


def copy_project(user: dict, src_pid: int, team_id: int | None, name: str | None,
                 guard: Callable[[], None] | None = None) -> int:
    """Kopie in team_id (None = privat des Kopierenden); Rechte prueft der Aufrufer vorher und ueber guard erneut als
    erste Zeile in der Transaktion. Rueckgabe: neue Projekt-id."""
    snap = _snapshot(src_pid)
    if snap is None:
        raise HTTPException(409, CHANGED)
    tmp = tmp_root() / f"copy-{secrets.token_hex(8)}"
    try:
        try:
            _stage(tmp, snap)
        except OSError:
            raise HTTPException(500, FAILED) from None
        with db.atomic():
            if guard is not None:
                guard()
            if _snapshot(src_pid) != snap:
                raise HTTPException(409, CHANGED)
            new_pid, photo_map, job_map = _insert(user, src_pid, team_id, name)
        try:
            _place(tmp, photo_map, job_map)
        except Exception as e:
            try:
                _undo(new_pid, job_map)
            except Exception as u:   # Rueckbau unvollstaendig: Kopie ohne (alle) Dateien bleibt loeschbar (Spec §8)
                print(f"Kopie {new_pid}: Rückbau fehlgeschlagen ({u})", file=sys.stderr, flush=True)
            print(f"Kopie von Projekt {src_pid} fehlgeschlagen: {e}", file=sys.stderr, flush=True)
            raise HTTPException(500, FAILED) from None
        return new_pid
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
