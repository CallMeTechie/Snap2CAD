"""CAD-Auftraege: KI -> Code -> Sandbox -> Pruefung -> ggf. Selbstkorrektur."""
from __future__ import annotations

import os
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from fastapi import HTTPException

from . import ai, auth, config, db, sandbox, settings
from .parts import cad_text, reference_top, to_top

_pool = ThreadPoolExecutor(max_workers=max(1, config.MAX_CONCURRENT_JOBS), thread_name_prefix="job")
_cancel: dict[int, threading.Event] = {}
_lock = threading.RLock()

PROCESSES = {
    "fdm": "3D-Druck FDM (Düse 0.4 mm, Schichthöhe 0.2 mm)",
    "sla": "3D-Druck Harz (SLA/MSLA)",
    "cnc": "CNC-Fräsen 3-Achs",
    "other": "nicht festgelegt",
}
SOURCE_LABEL = {"claude": "KI", "auto": "automatisch", "user": "Foto", "manual": "manuell"}


def job_dir(job_id: int) -> Path:
    return config.DATA_DIR / "jobs" / str(job_id)


def version_dir(job_id: int, version: int) -> Path:
    return job_dir(job_id) / f"v{version}"


def log(job_id: int, msg: str, level: str = "info"):
    db.ex("INSERT INTO job_log(job_id,ts,level,msg) VALUES (?,?,?,?)", (job_id, db.now(), level, msg[:1000]))


def _set(job_id: int, **kw):
    kw["updated_at"] = db.now()
    cols = ", ".join(f"{k}=?" for k in kw)
    db.ex(f"UPDATE jobs SET {cols} WHERE id=?", (*kw.values(), job_id))


# ------------------------------------------------------------------ Eingabe fuer Claude

def _fmt(v, nd=2):
    return "–" if v is None else f"{v:.{nd}f}".rstrip("0").rstrip(".")


def top_points(m: dict, d: dict, photos: dict) -> tuple[str, list]:
    """Punkte einer Messung fuer Tabelle und CSV; Unteransicht in Draufsicht-Koordinaten mit Vermerk."""
    pts = d.get("points") or []
    if d.get("view") != "bottom" or not pts or m["photo_id"] not in photos:
        return "", pts
    ph = photos[m["photo_id"]]
    tag = "(unten)" if (db.jload(ph["analysis"], {}) or {}).get("bottom_align") else \
        "(unten, nicht ausgerichtet, links-rechts gespiegelt)"
    return tag, to_top(ph, pts)


def measurement_table(project_id: int, part_id: int | None = None) -> tuple[str, list[dict]]:
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY seq", (project_id,))
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}
    if part_id is not None:
        linked = {r["id"] for r in db.q("SELECT id, data FROM parts WHERE project_id=?", (project_id,))
                  if (db.jload(r["data"], {}) or {}).get("same_as") == part_id}
        rows = [m for m in rows if m["part_id"] in (part_id, None) or m["part_id"] in linked]
    seq = {t["id"]: t["seq"] for t in db.q("SELECT id, seq FROM parts WHERE project_id=?", (project_id,))}
    lines = ["| ID | Bezeichnung | Teil | Art | Wert | ± | Messschieber | Nennmaß | kritisch | Passung | Quelle "
             "| Ansicht/Punkte (mm) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in rows:
        d = db.jload(m["data"], {}) or {}
        tag, pts = top_points(m, d, photos)
        where = (f"{d.get('view', '')} {tag} " + " ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in pts[:3])).strip()
        teil = f"T{seq[m['part_id']]}" if m["part_id"] in seq else ""
        lines.append(f"| M{m['seq']} | {m['label']} | {teil} | {m['kind']} | {_fmt(m['value'])} {m['unit']} | "
                     f"{_fmt(m['unc'])} | {_fmt(m['caliper'])} | {_fmt(d.get('nominal'))} | {'ja' if m['critical'] else ''} | "
                     f"{m['fit'] or ''} | {SOURCE_LABEL.get(m['source'], m['source'])} | {where} |")
    return "\n".join(lines), rows


TRANSPARENT_TEXT = {0: "nein", 1: "teilweise", 2: "ja"}


def material_line(project: dict) -> str:
    tr = project.get("transparent")
    bits = [project.get("color"), project.get("material"),
            f"transparent: {TRANSPARENT_TEXT[tr]}" if tr in TRANSPARENT_TEXT else None, project.get("finish")]
    bits = [b for b in bits if b]
    return f"Fotografiertes Original (nicht das Fertigungsmaterial): {', '.join(bits)}" if bits else ""


def _write_atomic(path: Path, data: bytes):
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _small(pdir: Path) -> Path | None:
    out = pdir / "small.jpg"
    if not out.is_file():
        if not (pdir / "orig.jpg").is_file():
            return None
        _write_atomic(out, ai.prepare_image(pdir / "orig.jpg")[0])
    return out


def _rect_top(ph: dict, top: dict | None) -> Path | None:
    """Unteransicht in Draufsicht-Koordinaten, bei jedem Aufbau neu (kein veralteter Zwischenspeicher)."""
    from core import vision  # spaet: main.py setzt sys.path erst nach den App-Importen
    pdir = config.DATA_DIR / "photos" / str(ph["id"])
    img = cv2.imread(str(pdir / "rect.jpg"))
    if img is None:
        return None
    a = db.jload(ph["analysis"], {}) or {}
    tid = (a.get("bottom_align") or {}).get("top_photo_id")
    ref = db.q1("SELECT analysis FROM photos WHERE id=?", (tid,)) if tid else None
    at = db.jload(ref["analysis"], {}) if ref else None   # Referenz aus der Ausrichtung; sonst nur gespiegelt
    out = pdir / "rect_top.jpg"
    _write_atomic(out, vision.encode_jpg(vision.bottom_warp(img, a, at), 90))
    return out


def pick_images(project_id: int, photo_ids: list[int] | None) -> list[dict]:
    """Bilder fuer die KI (Spec §2.2): Draufsicht, Unteransicht, Hoehenlehre, Schraegfotos; hoechstens 6."""
    from core import vision  # spaet: siehe oben
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (project_id,))
              if photo_ids is None or p["id"] in photo_ids]
    top = reference_top(project_id)
    groups: dict[str, list[dict]] = {"top": [], "bottom": [], "gauge": [], "tilted": []}
    for p in photos:
        pdir = config.DATA_DIR / "photos" / str(p["id"])
        a = db.jload(p["analysis"], {}) or {}
        if p["view"] == "top" and (pdir / "rect.jpg").is_file():
            cap = ai.scaled_caption(pdir / "rect.jpg", f"Foto {p['id']} (Draufsicht), entzerrt auf die Unterlage",
                                    vision.PX_PER_MM)
            groups["top"].append({"photo_id": p["id"], "kind": "top", "path": pdir / "rect.jpg", "caption": cap})
        elif p["view"] == "bottom" and a.get("rect"):
            path = _rect_top(p, top)
            if path:
                tag = ("entzerrt und gespiegelt auf Draufsicht-Koordinaten – Bohrungen von unten und oben liegen übereinander"
                       if a.get("bottom_align") else "entzerrt, nicht ausgerichtet, links-rechts gespiegelt")
                cap = ai.scaled_caption(path, f"Foto {p['id']} (von unten), {tag}", vision.PX_PER_MM)
                groups["bottom"].append({"photo_id": p["id"], "kind": "bottom", "path": path, "caption": cap})
        elif p["view"] in ("tilted", "overview"):
            path = _small(pdir)
            if path:
                cap = (f"Foto {p['id']}, Schrägansicht – nicht entzerrt, kein Maßstab; "
                       "nur für Form, Seitenflächen und Höhenverhältnis.")
                groups["tilted"].append({"photo_id": p["id"], "kind": "tilted", "path": path, "caption": cap})
        if (pdir / "gauge.jpg").is_file():
            cap = ai.scaled_caption(pdir / "gauge.jpg", f"Foto {p['id']}, entzerrte Höhenlehre (x −100…100 mm, y ab −10 mm)",
                                    vision.PX_PER_MM)
            groups["gauge"].append({"photo_id": p["id"], "kind": "gauge", "path": pdir / "gauge.jpg", "caption": cap})
    return (groups["top"] + groups["bottom"] + groups["gauge"] + groups["tilted"])[:6]


def build_initial_message(project: dict, request_text: str, options: dict) -> list[dict]:
    chk = bool(options.get("for_check"))
    table, rows = measurement_table(project["id"], options.get("part_id"))
    proc = PROCESSES.get(options.get("process"), options.get("process") or "nicht festgelegt")
    fx = (project.get("ctrl_x") or 100) / 100
    parts = [f"# Auftrag: {options.get('name') or 'Bauteil'}"]
    if not chk:
        parts.append(f"Fertigung: {proc}" + (f", Material: {options['material']}" if options.get("material") else ""))
    ml = material_line(project)
    if ml and (not chk or project.get("material_user")):   # KI-Schaetzung nicht als Tatsache zurueckfuettern
        parts.append(ml)
    parts += [f"Korrekturfaktoren aus dem Kontrollmaß sind bereits in den Werten enthalten (X {fx:.4f}).",
              "", "## Messwerte", table if rows else "(keine Messwerte – nur aus den Fotos ableiten)"]
    teile = cad_text(project["id"], options.get("part_id"))
    if teile:
        parts[parts.index("## Messwerte") + 1:parts.index("## Messwerte") + 1] = [teile]
    if not chk:
        parts += ["", "## Wunsch des Nutzers", request_text.strip() or "Bauteil möglichst originalgetreu nachbilden."]
    if options.get("check_items"):
        parts += ["", "## Offene Punkte der Prüfung", *[f"- [{i['severity']}] {i['text']}" for i in options["check_items"]]]
    if not chk:
        if options.get("process") == "cnc":
            cd = options.get("cutter_d")
            if cd:
                parts.append(f"Kleinster Fräser: Ø {cd:g} mm → Innenradien ≥ {cd / 2 + 0.2:g} mm")
            if options.get("setups"):
                parts.append(f"Aufspannungen: {options['setups']}")
        if options.get("fits"):
            parts.append("Passungen: " + "; ".join(
                f"{f['id']} {f['fit']}" + (f" ({f['depth']})" if f.get("depth") else "")
                for f in options["fits"] if f.get("fit")))
        if options.get("tolerance"):
            parts.append(f"Allgemeintoleranz: {options['tolerance']}")
        if options.get("extra"):
            parts.append(f"Zusatzwünsche: {options['extra']}")
    content: list[dict] = [{"type": "text", "text": "\n".join(parts)}]
    imgs = options["images"] if "images" in options else pick_images(project["id"], options.get("photo_ids"))
    for im in imgs:
        content += ai.image_ref(im["path"], im["caption"])
    return [{"role": "user", "content": content}]


# ------------------------------------------------------------------ Pruefungen

def _de(v: float, nd: int = 2) -> str:
    return f"{v:.{nd}f}".replace(".", ",")


def compute_checks(result: dict, meta: dict, project_id: int | None) -> list[dict]:
    checks = []
    checks.append({"id": "valid", "label": "Gültiger Volumenkörper (B-Rep)",
                   "state": "ok" if result.get("valid") else "fail",
                   "detail": "" if result.get("valid") else "OpenCascade meldet ungültige Geometrie"})
    n = result.get("solids", 0)
    checks.append({"id": "solids", "label": "Genau ein Körper", "state": "ok" if n == 1 else ("warn" if n > 1 else "fail"),
                   "detail": f"{n} Körper"})
    stl = result.get("stl") or {}
    checks.append({"id": "watertight", "label": "STL wasserdicht", "state": "ok" if stl.get("watertight") else "fail",
                   "detail": f"{stl.get('triangles', 0)} Dreiecke"})
    exp = meta.get("bbox_expected")
    bb = result.get("bbox")
    if isinstance(exp, list) and len(exp) == 3 and bb:
        try:
            e = [float(v) for v in exp]
            dev = max(abs(a - b) for a, b in zip(bb, e, strict=True))
            dev_sorted = max(abs(a - b) for a, b in zip(sorted(bb), sorted(e), strict=True))
            lim = max(1.0, 0.03 * max(e))
            if dev <= 0.2:
                st, det = "ok", f"Abweichung {_de(dev)} mm"
            elif dev_sorted <= 0.2:
                st, det = "warn", "Maße stimmen, aber andere Achsenlage als angegeben"
            elif dev_sorted <= lim:
                st, det = "warn", f"Abweichung {_de(dev_sorted)} mm"
            else:
                st, det = "fail", (f"Abweichung {_de(dev_sorted)} mm (erwartet {' × '.join(_de(v, 1) for v in e)}, "
                                   f"erzeugt {' × '.join(_de(v, 1) for v in bb)})")
            checks.append({"id": "bbox", "label": "Hüllquader wie angekündigt", "state": st, "detail": det})
        except (TypeError, ValueError):
            pass
    if project_id:
        crit = db.q("SELECT seq,label,value,caliper,unc FROM measurements WHERE project_id=? AND accepted=1 AND critical=1",
                    (project_id,))
        dims = {str(d.get("id", "")).upper(): d for d in meta.get("dimensions", []) if isinstance(d, dict)}
        missing = [f"M{c['seq']}" for c in crit if f"M{c['seq']}" not in dims]
        far = []
        for c in crit:
            d = dims.get(f"M{c['seq']}")
            ref = c["caliper"] if c["caliper"] is not None else c["value"]
            try:
                if d and ref is not None and abs(float(d.get("nominal")) - ref) > max(2 * (c["unc"] or 0.5), 0.3):
                    far.append(f"M{c['seq']} {_de(ref)} → {_de(float(d['nominal']))}")
            except (TypeError, ValueError):
                pass
        if crit:
            st = "warn" if (missing or far) else "ok"
            det = []
            if missing:
                det.append("nicht ausgewiesen: " + ", ".join(missing))
            if far:
                det.append("stark gerundet: " + ", ".join(far))
            checks.append({"id": "critical", "label": "Kritische Maße übernommen", "state": st,
                           "detail": "; ".join(det) or f"{len(crit)} geprüft"})
    return checks


def _fix_prompt(error: dict | None, checks: list[dict]) -> str:
    if error:
        loc = f" in Zeile {error['line']}: `{error.get('code') or ''}`" if error.get("line") else ""
        return (f"Der Code ist in der Sandbox fehlgeschlagen ({error.get('stage')}, {error.get('type')}){loc}.\n"
                f"Fehlermeldung: {error.get('message')}\n\n"
                "Korrigiere das Modell und antworte wieder im gleichen Format (JSON-Block + vollständiger Python-Block).")
    bad = [f"- {c['label']}: {c['detail']}" for c in checks if c["state"] == "fail"]
    return ("Das Modell wurde erzeugt, besteht aber die Prüfung nicht:\n" + "\n".join(bad) +
            "\n\nKorrigiere das Modell und antworte wieder im gleichen Format (JSON-Block + vollständiger Python-Block).")


# ------------------------------------------------------------------ Ablauf

def _check_quota(user: dict):
    q = auth.quota_of(user)
    if q is not None and auth.usage_this_month(user["id"]) >= q:
        raise HTTPException(429, f"Monatskontingent erreicht ({q} CAD-Generierungen). Bitte den Administrator fragen.")


def _check_ready():
    if not settings.ai_enabled():
        raise HTTPException(503, "KI ist nicht eingerichtet (Verwaltung → Einstellungen).")
    if not sandbox.worker_alive():
        raise HTTPException(503, "Die CAD-Sandbox läuft nicht (Dienst „sandbox“ prüfen).")


def create(user: dict, project: dict | None, name: str, request_text: str, options: dict) -> int:
    _check_ready()
    _check_quota(user)
    with _lock:
        running = db.q1("SELECT COUNT(*) n FROM jobs WHERE user_id=? AND status IN ('queued','running')", (user["id"],))
        if running["n"] >= 3:
            raise HTTPException(429, "Es laufen bereits drei Aufträge. Bitte warten.")
        options = {**options, "name": name}
        msgs = build_initial_message(project, request_text, options) if project else \
            [{"role": "user", "content": [{"type": "text", "text": request_text}]}]
        jid = db.ex("""INSERT INTO jobs(user_id,project_id,name,request,status,messages,created_at,updated_at)
                       VALUES (?,?,?,?, 'queued', ?, ?, ?)""",
                    (user["id"], project["id"] if project else None, name[:120], db.jdump(options | {"text": request_text}),
                     db.jdump(msgs), db.now(), db.now()))
    log(jid, "Auftrag angelegt")
    db.audit("cad_create", f"Auftrag {jid} „{name[:60]}“", user_id=user["id"], actor=user["username"])
    _submit(jid, "create", request_text)
    return jid


def iterate(user: dict, job: dict, text: str):
    with _lock:  # Statuswechsel atomar: kein zweiter Lauf auf demselben Auftrag
        job = db.q1("SELECT * FROM jobs WHERE id=?", (job["id"],))
        if not job or job["status"] in ("queued", "running"):
            raise HTTPException(409, "Der Auftrag läuft noch.")
        _iterate_locked(user, job, text)


def _iterate_locked(user: dict, job: dict, text: str):
    base = job["current_version"] or db.q1("SELECT MAX(version) v FROM job_versions WHERE job_id=?", (job["id"],))["v"]
    if not base:
        raise HTTPException(409, "Es gibt noch keine Version, auf der aufgebaut werden kann.")
    _check_ready()
    _check_quota(user)
    msgs = db.jload(job["messages"], [])
    # Gespraech auf die aktuelle Version zurueckschneiden ist nicht noetig: Claude sieht den Verlauf.
    cur = db.q1("SELECT code FROM job_versions WHERE job_id=? AND version=?", (job["id"], base))
    msgs.append({"role": "user", "content": [{"type": "text", "text":
                 f"Änderungswunsch zu Version {base}:\n{text.strip()}\n\n"
                 "Ausgangspunkt ist dieser Code:\n```python\n" + (cur["code"] if cur else "") + "```\n"
                 "Antworte wieder im gleichen Format (JSON-Block + vollständiger Python-Block)."}]})
    _set(job["id"], messages=db.jdump(msgs), status="queued", error=None)
    log(job["id"], f"Änderungswunsch: {text.strip()[:200]}")
    _submit(job["id"], "iterate", text)


def cancel(job: dict):
    with _lock:
        ev = _cancel.get(job["id"])
        if ev:
            ev.set()
        cur = db.q1("SELECT status FROM jobs WHERE id=?", (job["id"],))
        if cur and cur["status"] in ("queued", "running"):
            _set(job["id"], status="cancelled", error="Abgebrochen")
            log(job["id"], "Abbruch angefordert", "warn")


def _submit(job_id: int, trigger: str, request_text: str):
    ev = threading.Event()
    with _lock:
        _cancel[job_id] = ev
    _pool.submit(_run_safe, job_id, trigger, request_text, ev)


def _current(job_id: int, ev: threading.Event) -> bool:
    """Gehoert dieser Thread noch zum aktuellen Lauf des Auftrags?"""
    return _cancel.get(job_id) is ev and not ev.is_set()


def _run_safe(job_id, trigger, request_text, ev):
    try:
        _run(job_id, trigger, request_text, ev)
    except (ai.Cancelled, sandbox.Cancelled):
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND status='running'", (job_id,))
        log(job_id, "Abgebrochen", "warn")
    except ai.AIError as e:
        if _current(job_id, ev):
            _set(job_id, status="failed", error=str(e))
        log(job_id, str(e), "error")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        if _current(job_id, ev):
            _set(job_id, status="failed", error=f"Interner Fehler: {type(e).__name__}: {e}")
        log(job_id, f"Interner Fehler: {type(e).__name__}: {e}", "error")
    finally:
        with _lock:
            if _cancel.get(job_id) is ev:
                _cancel.pop(job_id, None)


def _new_version(job_id: int, trigger: str, request_text: str, text: str, usage: dict) -> int:
    """Versionsnummer vergeben und Zeile sofort anlegen (unter Sperre, ohne Doppelvergabe)."""
    with _lock:
        v = db.q1("SELECT COALESCE(MAX(version),0)+1 v FROM job_versions WHERE job_id=?", (job_id,))["v"]
        db.ex("""INSERT INTO job_versions(job_id,version,trigger,request_text,claude_text,status,usage,created_at)
                 VALUES (?,?,?,?,?, 'running', ?, ?)""", (job_id, v, trigger, request_text, text, db.jdump(usage), db.now()))
    return v


def _run(job_id: int, trigger: str, request_text: str, ev: threading.Event):
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job or job["status"] == "cancelled" or ev.is_set():
        return
    _set(job_id, status="running")
    msgs = db.jload(job["messages"], [])
    fixes = 0
    while True:
        if ev.is_set():
            raise ai.Cancelled()
        if not db.q1("SELECT id FROM jobs WHERE id=?", (job_id,)):
            return  # Auftrag wurde geloescht
        log(job_id, "KI erstellt das Modell …" if trigger != "autofix" else "KI korrigiert den Code …")
        text, usage = ai.call(ai.CAD_SYSTEM, msgs, cancel=ev,
                              on_progress=lambda n: None)
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
        _set(job_id, messages=db.jdump(msgs))
        if ev.is_set():
            raise ai.Cancelled()
        version = _new_version(job_id, trigger, request_text, text, usage)
        vdir = version_dir(job_id, version)
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "claude.txt").write_text(text, encoding="utf-8")
        try:
            meta, code = ai.parse_cad(text)
        except ai.AIError as e:
            meta, code = {}, ""
            err = {"stage": "antwort", "type": "FormatError", "message": str(e), "line": None, "code": None}
            db.ex("UPDATE job_versions SET code=?, meta=?, status='failed', error=? WHERE job_id=? AND version=?",
                  (code, db.jdump(meta), db.jdump(err), job_id, version))
            log(job_id, f"Version {version}: Antwort im falschen Format", "warn")
            result, checks = None, []
        else:
            (vdir / "model.py").write_text(code, encoding="utf-8")
            db.ex("UPDATE job_versions SET code=?, meta=? WHERE job_id=? AND version=?",
                  (code, db.jdump(meta), job_id, version))
            log(job_id, f"Version {version}: Code erhalten ({len(code.splitlines())} Zeilen), Sandbox rechnet …")
            res = sandbox.run(code, vdir, cancel=ev)
            if not db.q1("SELECT id FROM jobs WHERE id=?", (job_id,)):
                shutil.rmtree(job_dir(job_id), ignore_errors=True)
                return
            err = None if res["ok"] else res["error"]
            result = res.get("result")
            checks = compute_checks(result, meta, job["project_id"]) if result else []
            failed = err is not None or any(c["state"] == "fail" for c in checks)
            db.ex("UPDATE job_versions SET status=?, error=?, result=?, checks=?, seconds=? WHERE job_id=? AND version=?",
                  ("failed" if failed else "ok", db.jdump(err) if err else None, db.jdump(result) if result else None,
                   db.jdump(checks), res.get("seconds"), job_id, version))
            if not failed:
                warn = sum(1 for c in checks if c["state"] == "warn")
                bb = result["bbox"]
                log(job_id, f"Version {version} fertig: {_de(bb[0])} × {_de(bb[1])} × {_de(bb[2])} mm, "
                            f"{result['stl']['triangles']} Dreiecke, {_de(res['seconds'], 1)} s"
                            + (f", {warn} Hinweis(e)" if warn else ""), "ok")
                if _current(job_id, ev):
                    _set(job_id, status="done", current_version=version, error=None)
                return
            if err:
                where = f" (Zeile {err['line']})" if err.get("line") else ""
                log(job_id, f"Version {version}: {err.get('type')}{where}: {str(err.get('message'))[:200]}", "warn")
            else:
                log(job_id, f"Version {version}: Prüfung nicht bestanden – " +
                    "; ".join(c["label"] for c in checks if c["state"] == "fail"), "warn")
        if fixes >= config.MAX_AUTOFIX:
            msg = "Auch nach automatischer Korrektur kein gültiges Modell."
            if _current(job_id, ev):
                _set(job_id, status="failed", error=msg)
            log(job_id, msg + " Bitte Änderungswunsch formulieren oder Maße prüfen.", "error")
            return
        fixes += 1
        trigger = "autofix"
        msgs.append({"role": "user", "content": [{"type": "text", "text": _fix_prompt(err, checks)}]})
        _set(job_id, messages=db.jdump(msgs))
        log(job_id, f"Automatische Korrektur {fixes}/{config.MAX_AUTOFIX}")


def startup():
    n = db.q1("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")["n"]
    if n:
        db.ex("UPDATE jobs SET status='failed', error='Server wurde neu gestartet', updated_at=? "
              "WHERE status IN ('queued','running')", (db.now(),))
        db.ex("UPDATE job_versions SET status='failed' WHERE status='running'")


def delete(job: dict):
    cancel(job)
    db.ex("DELETE FROM jobs WHERE id=?", (job["id"],))
    shutil.rmtree(job_dir(job["id"]), ignore_errors=True)


def version_files(job_id: int, version: int) -> dict:
    d = version_dir(job_id, version)
    return {n: (d / n).stat().st_size for n in ("model.step", "model.stl", "model.py", "outline.json") if (d / n).is_file()}


def job_public(job: dict, detail: bool = False) -> dict:
    out = {k: job[k] for k in ("id", "user_id", "project_id", "name", "status", "current_version", "error",
                               "created_at", "updated_at")}
    req = db.jload(job["request"], {})
    out["request"] = req
    cur = None
    if job["current_version"]:
        cur = db.q1("SELECT result FROM job_versions WHERE job_id=? AND version=?", (job["id"], job["current_version"]))
    r = db.jload(cur["result"], {}) if cur else {}
    out["bbox"] = r.get("bbox")
    out["n_versions"] = db.q1("SELECT COUNT(*) n FROM job_versions WHERE job_id=?", (job["id"],))["n"]
    if detail:
        vs = db.q("SELECT * FROM job_versions WHERE job_id=? ORDER BY version", (job["id"],))
        out["versions"] = [{
            "version": v["version"], "trigger": v["trigger"], "request_text": v["request_text"], "status": v["status"],
            "code": v["code"], "claude_text": v["claude_text"], "meta": db.jload(v["meta"], {}), "error": db.jload(v["error"]),
            "result": db.jload(v["result"]), "checks": db.jload(v["checks"], []), "usage": db.jload(v["usage"], {}),
            "seconds": v["seconds"], "created_at": v["created_at"], "files": version_files(job["id"], v["version"]),
        } for v in vs]
        out["log"] = db.q("SELECT ts,level,msg FROM job_log WHERE job_id=? ORDER BY id", (job["id"],))
    return out
