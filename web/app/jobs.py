"""CAD-Auftraege: KI -> Code -> Sandbox -> Pruefung -> ggf. Selbstkorrektur."""
from __future__ import annotations

import math
import os
import re
import shutil
import threading
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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
GROUP_TEXT = {"aussen": "außen", "bohrung": "Bohrung", "tiefe": "Tiefe", "fase": "Fase", "platte": "Platte",
              "sonst": "sonstige"}
MODEL_DIMS_HEADING = "## Messschieber am Modell (verbindlich)"


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


# ------------------------------------------------------------------ Gelernte Werte (Spec Stufe B §4)

def label_norm(label: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", label.casefold()).split())


def _norm_of(d: dict) -> str:
    """label_norm eines Masses; ohne Buchstaben/Ziffern im Label die D-Nummer (sonst ueberschreiben sie sich)."""
    return label_norm(str(d.get("label") or "")) or str(d.get("id") or "").casefold()


def learn_dims(project_id: int, job_id: int | None, dims: list[dict]):
    """Je Mass ein Eintrag; gleiche label_norm im Projekt ersetzt den alten Wert (UPSERT)."""
    for d in dims:
        db.ex("""INSERT INTO model_dims(project_id,label,label_norm,grp,value,job_id,dim_id,note,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(project_id,label_norm) DO UPDATE SET label=excluded.label, grp=excluded.grp,
                   value=excluded.value, job_id=excluded.job_id, dim_id=excluded.dim_id, note=excluded.note,
                   created_at=excluded.created_at""",
              (project_id, str(d.get("label") or d.get("id")), _norm_of(d), d.get("group") or "sonst", float(d["value"]),
               job_id, d.get("id"), None, db.now()))


def learned_dims(project_id: int) -> list[dict]:
    return db.q("SELECT * FROM model_dims WHERE project_id=? ORDER BY id", (project_id,))


def model_dims_section(project_id: int | None) -> str:
    rows = learned_dims(project_id) if project_id else []
    if not rows:
        return ""
    lines = [MODEL_DIMS_HEADING]
    for r in rows:
        where = f"gemessen am Auftrag {r['job_id']}" if r["job_id"] else "gemessen am Modell"
        lines.append(f"- {r['label']}: {_fmt(r['value'], 3)} mm (Gruppe {GROUP_TEXT.get(r['grp'], r['grp'])}, {where})")
    return "\n".join(lines)


def _de_num(v: float) -> str:
    return _fmt(v, 3).replace(".", ",")


def reconcile_learned(meta: dict, project_id: int | None, job_id: int) -> dict | None:
    """Nach jedem KI-Lauf (nicht param): gelernter Wert getroffen -> user_set; sonst Warnung, nie Zurueckschreiben."""
    rows = learned_dims(project_id) if project_id else []
    if not rows:
        return None
    dims = [d for d in meta.get("dimensions", []) if isinstance(d, dict) and isinstance(d.get("value"), (int, float))]
    by_norm: dict[str, dict] = {}
    for d in dims:
        by_norm.setdefault(_norm_of(d), d)
    by_id = {d.get("id"): d for d in dims}
    hit, far = 0, []
    for r in rows:
        d = by_norm.get(r["label_norm"])
        if d is None and r["job_id"] == job_id and r["dim_id"]:
            d = by_id.get(r["dim_id"])       # Label umbenannt, D-Nummer im selben Auftrag stabil (Regel 12)
        if d is None:
            if r["job_id"] == job_id:        # nachgemessenes Mass dieses Auftrags fehlt in der neuen Antwort
                far.append(f"{r['label']}: {_de_num(r['value'])} → fehlt")
            continue
        if abs(d["value"] - r["value"]) <= 0.01 + 1e-9:
            d["user_set"], d["assumed"] = True, False
            hit += 1
        else:
            far.append(f"{r['label']}: {_de_num(r['value'])} → {_de_num(d['value'])}")
    label = "Messschieber am Modell übernommen"
    if far:
        return {"id": "model_dims", "label": label, "state": "warn", "detail": "; ".join(far)}
    return {"id": "model_dims", "label": label, "state": "ok", "detail": f"{hit} übernommen"} if hit else None


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


CHECK_ITEMS_HEADING = "## Hinweise der Prüfung (nicht verbindlich – Umriss, Unteransicht und Regel 9 gehen vor)"
CAD_MAX_TOKENS = 32000   # Opus denkt mit; 16000 schnitt die Antwort ab (A8)
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
    if ml:   # auch die KI-Schaetzung: Pruefung und Konstruktion brauchen sie (Regel 9); Kantenhinweise nur aus Handeingabe
        parts.append(ml)
    parts += [f"Korrekturfaktoren aus dem Kontrollmaß sind bereits in den Werten enthalten (X {fx:.4f}).",
              "", "## Messwerte", table if rows else "(keine Messwerte – nur aus den Fotos ableiten)"]
    teile = cad_text(project["id"], options.get("part_id"))
    if teile:
        parts[parts.index("## Messwerte") + 1:parts.index("## Messwerte") + 1] = [teile]
    sec = model_dims_section(project["id"])   # Spec §4: Erstauftrag und Pruefung bekommen den Abschnitt nach der Tabelle
    if sec:
        parts += ["", sec]
    if not chk:
        parts += ["", "## Wunsch des Nutzers", request_text.strip() or "Bauteil möglichst originalgetreu nachbilden."]
    if options.get("check_items"):
        parts += ["", CHECK_ITEMS_HEADING, *[f"- [{i['severity']}] {i['text']}" for i in options["check_items"]]]
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


# ------------------------------------------------------------------ Masse am Modell (Spec Stufe B §1, §2)

def _meas_ids(project_id: int | None) -> set[str]:
    """M-Nummern der uebernommenen Messungen: nur diese duerfen als ref stehen."""
    if not project_id:
        return set()
    return {f"M{r['seq']}" for r in db.q("SELECT seq FROM measurements WHERE project_id=? AND accepted=1", (project_id,))}


def _const_re(var: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(var)}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(#.*)?$", re.M)


def _add_note(note: str | None, add: str) -> str:
    return note if note and add in note else (f"{note}; {add}" if note else add)


def mark_editable(meta: dict, code: str):
    """editable nur bei genau einer Zeile `VAR =` im Muster der Spec und genau einem Mass mit dieser var;
    Codewert gilt ab Abweichung > 0,01."""
    dims = [d for d in meta.get("dimensions", []) if isinstance(d, dict)]
    used = Counter(d.get("var") for d in dims if d.get("var"))
    for d in dims:
        var, value = d.get("var"), d.get("value")
        d["editable"] = False
        if not isinstance(var, str) or not ai._VAR.fullmatch(var) or not isinstance(value, (int, float)):
            continue
        if used[var] > 1 or len(re.findall(rf"^{re.escape(var)}\s*=", code, re.M)) > 1:
            d["note"] = _add_note(d.get("note"), "Konstante mehrfach belegt")
            continue
        m = _const_re(var).search(code)
        if not m:
            continue
        d["editable"] = True
        v = float(m.group(1))
        if abs(v - value) > 0.01:
            d["value"] = v
            d["note"] = _add_note(d.get("note"), "Wert aus dem Code")


def _filter_anchors(result: dict | None):
    """dim_anchors serverseitig erneut filtern (Spec Regel 13): der Laeufer teilt den Prozess mit dem Modellcode und
    ist keine Vertrauensgrenze. Nur gefilterte Eintraege werden gespeichert und an den Browser geliefert."""
    if not isinstance(result, dict) or "dim_anchors" not in result:
        return
    raw = result.pop("dim_anchors")
    if not isinstance(raw, dict):
        return
    out = {}
    for k, v in raw.items():
        if len(out) >= ai.MAX_DIMS:
            break
        if type(k) is not str or not ai._DIM_ID.fullmatch(k) or not isinstance(v, (list, tuple)) or len(v) != 2:
            continue
        a, b = ai.point3(v[0]), ai.point3(v[1])
        if a and b:
            out[k] = [[round(x, 4) for x in a], [round(x, 4) for x in b]]
    result["dim_anchors"] = out


def _stretch(a: list[float], b: list[float], value: float) -> tuple[list[float], list[float]]:
    """Anker entlang a->b auf die neue Laenge strecken (Rueckfall ohne DIM_ANCHORS-Eintrag)."""
    n = math.dist(a, b)
    return (a, b) if n <= 1e-9 else (a, [a[i] + (b[i] - a[i]) * value / n for i in range(3)])


def _apply_anchors(meta: dict, result: dict | None, changed: set[str] | None = None):
    """Je Mass zuerst dim_anchors (Regel 13), sonst a/b; gelten nur bei Abstand = Wert ± max(0,1 mm; 1 %).
    changed (Param-Lauf): geaendertes Mass ohne Eintrag wird gestreckt, jedes andere ohne Eintrag ist anchors_stale."""
    da = (result or {}).get("dim_anchors")
    da = da if isinstance(da, dict) else {}
    for d in meta.get("dimensions", []):
        if not isinstance(d, dict):
            continue
        value, src = d.get("value"), da.get(d.get("id"))
        a = b = None
        if isinstance(src, (list, tuple)) and len(src) == 2:
            a, b = ai.point3(src[0]), ai.point3(src[1])
        stale = False
        if not (a and b):
            a, b = ai.point3(d.get("a")), ai.point3(d.get("b"))
            if changed is not None and a and b:
                if d.get("id") in changed:
                    a, b = _stretch(a, b, value)
                    stale = d.get("anchors_stale") is True
                else:
                    stale = True
        ok = bool(d.get("var") and isinstance(value, (int, float)) and a and b
                  and abs(math.dist(a, b) - value) <= max(0.1, 0.01 * value))
        d.pop("anchors_stale", None)
        if ok:
            d["a"], d["b"] = [round(x, 4) for x in a], [round(x, 4) for x in b]
            if stale:
                d["anchors_stale"] = True
        else:
            d.pop("a", None)
            d.pop("b", None)


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
        # Stufe B: Modellmasse (D-Nummern) zeigen ueber ref auf die Messung und tragen value; alte Versionen: id = M-Nummer
        by_m: dict[str, tuple[dict, str]] = {}
        for d in meta.get("dimensions", []):
            if not isinstance(d, dict):
                continue
            did = str(d.get("id", "")).upper()
            if did.startswith("D"):
                if d.get("ref"):
                    by_m.setdefault(str(d["ref"]).upper(), (d, "value"))
            else:
                by_m.setdefault(did, (d, "nominal"))
        missing = [f"M{c['seq']}" for c in crit if f"M{c['seq']}" not in by_m]
        far = []
        for c in crit:
            hit = by_m.get(f"M{c['seq']}")
            ref = c["caliper"] if c["caliper"] is not None else c["value"]
            try:
                if hit and ref is not None:
                    v = float(hit[0].get(hit[1]))
                    if abs(v - ref) > max(2 * (c["unc"] or 0.5), 0.3):
                        far.append(f"M{c['seq']} {_de(ref)} → {_de(v)}")
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


def _check_sandbox():
    if not sandbox.worker_alive():
        raise HTTPException(503, "Die CAD-Sandbox läuft nicht (Dienst „sandbox“ prüfen).")


def _check_ready():
    if not settings.ai_enabled():
        raise HTTPException(503, "KI ist nicht eingerichtet (Verwaltung → Einstellungen).")
    _check_sandbox()


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
    sec = model_dims_section(job["project_id"])   # Spec §4: gelernte Werte an jeden Aenderungswunsch
    msgs.append({"role": "user", "content": [{"type": "text", "text":
                 f"Änderungswunsch zu Version {base}:\n{text.strip()}\n\n" + (f"{sec}\n\n" if sec else "") +
                 "Ausgangspunkt ist dieser Code:\n```python\n" + (cur["code"] if cur else "") + "```\n"
                 "Antworte wieder im gleichen Format (JSON-Block + vollständiger Python-Block)."}]})
    _set(job["id"], messages=db.jdump(msgs), status="queued", error=None)
    log(job["id"], f"Änderungswunsch: {text.strip()[:200]}")
    _submit(job["id"], "iterate", text)


# ------------------------------------------------------------------ Parametrischer Neuaufbau (Spec Stufe B §2)

PARAM_MAX = 20


def set_const(code: str, var: str, value: float) -> tuple[str, int]:
    """Zahl der Zeile `VAR = alt` ersetzen; Abstaende und Kommentar bleiben."""
    if not isinstance(var, str) or not ai._VAR.fullmatch(var):
        return code, 0
    pat = re.compile(rf"^({re.escape(var)}\s*=\s*)([0-9]+(?:\.[0-9]+)?)(\s*(?:#.*)?)$", re.M)
    return pat.subn(lambda m: m.group(1) + _fmt(value, 3) + m.group(3), code, count=1)


def _param_limits(user: dict):
    """Unter _lock: hoechstens ein laufender Neuaufbau je Nutzer und PARAM_PER_HOUR je Stunde (Pool ist geteilt)."""
    busy = db.q1("SELECT COUNT(*) n FROM job_versions v JOIN jobs j ON j.id=v.job_id WHERE j.user_id=? "
                 "AND v.trigger='param' AND v.status='running' AND j.status IN ('queued','running')", (user["id"],))
    if busy["n"]:
        raise HTTPException(429, "Es läuft bereits ein Neuaufbau. Bitte warten.")
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    hour = db.q1("SELECT COUNT(*) n FROM job_versions v JOIN jobs j ON j.id=v.job_id WHERE j.user_id=? "
                 "AND v.trigger='param' AND v.created_at>=?", (user["id"], since))
    if hour["n"] >= config.PARAM_PER_HOUR:
        raise HTTPException(429, f"Höchstens {config.PARAM_PER_HOUR} Neuaufbauten je Stunde – "
                                 "bitte später erneut versuchen.")


def param(user: dict, job: dict, values: list[dict], base: int | None = None) -> dict:
    """Konstanten der aktuellen Version ersetzen und ohne KI neu bauen. Pruefen, Lernen, Version anlegen und
    status=queued in einem Block unter _lock; die Sandbox laeuft danach im Pool (Abbrechen wie bisher)."""
    if auth.quota_of(user) == 0:
        raise HTTPException(403, "CAD ist für dieses Konto gesperrt.")
    _check_sandbox()
    with _lock:
        job = db.q1("SELECT * FROM jobs WHERE id=?", (job["id"],))
        if not job or job["status"] in ("queued", "running"):
            raise HTTPException(409, "Der Auftrag läuft noch.")
        _param_limits(user)
        cur = job["current_version"]
        bv = db.q1("SELECT code, meta FROM job_versions WHERE job_id=? AND version=?", (job["id"], cur)) if cur else None
        if not bv:
            raise HTTPException(409, "Es gibt noch keine Version, auf der aufgebaut werden kann.")
        if base is not None and base != cur:
            raise HTTPException(409, f"Version {base} ist nicht mehr aktuell (aktuell: Version {cur}) – bitte neu laden.")
        code, meta = bv["code"] or "", db.jload(bv["meta"], {}) or {}
        dims = {d.get("id"): d for d in meta.get("dimensions", []) if isinstance(d, dict)}
        changed: dict[str, float] = {}
        for it in values:
            d, new = dims.get(it["id"]), round(float(it["value"]), 3)
            if not d or not d.get("editable") or not d.get("var"):
                raise HTTPException(400, f"Maß {it['id']} ist nicht editierbar")
            if new <= 0:
                raise HTTPException(400, f"Maß {it['id']}: Der Wert muss größer als 0 sein.")
            code, n = set_const(code, d["var"], new)
            if not n:
                raise HTTPException(400, f"Maß {it['id']} ist nicht editierbar")
            d.update(value=new, assumed=False, user_set=True, derived_from=None)   # gleicher Wert: Annahme bestaetigt
            changed[d["id"]] = new
        req = ", ".join(f"{k} = {_fmt(v, 3)} mm" for k, v in changed.items())
        meta["param_ids"] = list(changed)  # einzige Quelle fuer „geaendert“ (_run_param, pending_param, cad.js)
        meta.pop("bbox_expected", None)   # Erwartung der KI galt fuer die alten Werte: Hüllquader-Pruefung entfaellt
        if job["project_id"]:                       # §2.4: gemessen ist gemessen, unabhaengig vom Erfolg
            cnt = Counter(_norm_of(x) for x in dims.values())   # gleiche Bezeichnung zweimal: D-Nummer anhaengen
            learn_dims(job["project_id"], job["id"],
                       [{**dims[k], "label": f"{dims[k].get('label')} ({k})"} if cnt[_norm_of(dims[k])] > 1 else dims[k]
                        for k in changed])
        version = _new_version(job["id"], "param", req, "", {})
        db.ex("UPDATE job_versions SET code=?, meta=? WHERE job_id=? AND version=?",
              (code, db.jdump(meta), job["id"], version))
        _set(job["id"], status="queued", error=None)
        log(job["id"], f"Neuaufbau mit {req} …")
        db.audit("cad_param", f"Auftrag {job['id']}: {req}"[:500], user_id=user["id"], actor=user["username"])
        _submit(job["id"], "param", str(version))   # der Pool-Lauf baut genau diese Version
    return {"version": version} if job["project_id"] else {"version": version, "learned": False}


def _run_param(job_id: int, version: int, ev: threading.Event):
    """Sandbox-Lauf genau der Param-Version `version`: kein KI-Aufruf, kein Autofix; Fehler -> failed, Basis bleibt."""
    v = db.q1("SELECT * FROM job_versions WHERE job_id=? AND version=?", (job_id, version))
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        return
    if not v or v["status"] != "running":       # Version wurde zwischenzeitlich beendet: Auftrag nicht queued lassen
        if _current(job_id, ev):
            _set(job_id, status="failed", error="Neuaufbau abgebrochen.")
        return
    if job["status"] == "cancelled" or ev.is_set():
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND version=?", (job_id, version))
        return
    _set(job_id, status="running")
    code, req = v["code"] or "", v["request_text"] or ""
    meta = db.jload(v["meta"], {}) or {}
    vdir = version_dir(job_id, version)
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "model.py").write_text(code, encoding="utf-8")
    try:
        res = sandbox.run(code, vdir, cancel=ev)
    except sandbox.Cancelled:                    # nur diese Version; _run_safe fasst Param-Versionen nicht an
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND version=?", (job_id, version))
        log(job_id, "Abgebrochen", "warn")
        return
    if not db.q1("SELECT id FROM jobs WHERE id=?", (job_id,)):
        shutil.rmtree(job_dir(job_id), ignore_errors=True)
        return
    err = None if res["ok"] else res["error"]
    result = res.get("result")
    _filter_anchors(result)                     # Spec Regel 13: nur gefilterte Anker speichern
    if result:
        _apply_anchors(meta, result, changed=set(meta.get("param_ids") or []))
    checks = compute_checks(result, meta, job["project_id"]) if result else []
    failed = err is not None or any(c["state"] == "fail" for c in checks)
    with _lock:   # cancel() setzt ev unter _lock: nach einem Abbruch wird die Version nie ok/failed (O-2)
        if ev.is_set():
            db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND version=?", (job_id, version))
            log(job_id, "Abgebrochen", "warn")
            return
        db.ex("UPDATE job_versions SET status=?, error=?, result=?, checks=?, seconds=?, meta=? "
              "WHERE job_id=? AND version=?",
              ("failed" if failed else "ok", db.jdump(err) if err else None, db.jdump(result) if result else None,
               db.jdump(checks), res.get("seconds"), db.jdump(meta), job_id, version))
    if failed:
        if err:
            where = f" (Zeile {err['line']})" if err.get("line") else ""
            why = f"{err.get('type')}{where}: {str(err.get('message'))[:200]}"
        else:
            why = "Prüfung nicht bestanden – " + "; ".join(c["label"] for c in checks if c["state"] == "fail")
        log(job_id, f"Version {version}: Neuaufbau mit {req} fehlgeschlagen – {why}", "warn")
        if _current(job_id, ev):
            _set(job_id, status="failed", error=f"Neuaufbau mit {req} fehlgeschlagen – {why}")
        return
    bb = result["bbox"]
    log(job_id, f"Version {version} fertig (Neuaufbau ohne KI): {_de(bb[0])} × {_de(bb[1])} × {_de(bb[2])} mm, "
                f"{_de(res['seconds'], 1)} s", "ok")
    with _lock:   # Gespraechszeile nur bei Erfolg und nur fuer den aktuellen Lauf: spaetere KI-Aenderungen kennen den Stand
        if not _current(job_id, ev):
            return
        row = db.q1("SELECT messages FROM jobs WHERE id=?", (job_id,))
        msgs = db.jload(row["messages"], []) if row else []
        msgs.append({"role": "user", "content": [{"type": "text", "text": f"Parametrisch geändert: {req} (Version {version})"}]})
        _set(job_id, messages=db.jdump(msgs), status="done", current_version=version, error=None)


def pending_param(job_id: int) -> list[dict]:
    """§5: Masse aus erfolgreichen Param-Versionen (meta["param_ids"]) nach der letzten erfolgreichen KI-Version."""
    vs = db.q("SELECT version, trigger, status, meta FROM job_versions WHERE job_id=? ORDER BY version", (job_id,))
    ai_ok = [v for v in vs if v["trigger"] != "param" and v["status"] == "ok"]
    if not ai_ok:
        return []
    last = ai_ok[-1]
    old = {d.get("id"): d for d in (db.jload(last["meta"], {}) or {}).get("dimensions", []) if isinstance(d, dict)}
    out: dict[str, dict] = {}
    for v in vs:
        if v["trigger"] != "param" or v["status"] != "ok" or v["version"] < last["version"]:
            continue
        meta = db.jload(v["meta"], {}) or {}
        dims = {d.get("id"): d for d in meta.get("dimensions", []) if isinstance(d, dict)}
        for i in meta.get("param_ids") or []:
            if i in dims:
                o = old.get(i) or {}
                out[i] = {"id": i, "label": dims[i].get("label"), "value": dims[i].get("value"), "old": o.get("value"),
                          "old_assumed": bool(o.get("assumed"))}
    return list(out.values())


def cancel(job: dict):
    with _lock:
        ev = _cancel.get(job["id"])
        if ev:
            ev.set()
        cur = db.q1("SELECT status FROM jobs WHERE id=?", (job["id"],))
        if cur and cur["status"] in ("queued", "running"):
            _set(job["id"], status="cancelled", error="Abgebrochen")
            log(job["id"], "Abbruch angefordert", "warn")
        # Neuaufbau noch in der Warteschlange: die Version nicht running lassen (_run_param prueft den Status)
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND status='running' AND trigger='param'",
              (job["id"],))


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
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND status='running' AND trigger!='param'",
              (job_id,))
        log(job_id, "Abgebrochen", "warn")
    except ai.AIError as e:
        if _current(job_id, ev):
            _set(job_id, status="failed", error=str(e))
        log(job_id, str(e), "error")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        if trigger == "param":   # nur die eigene Param-Version; ein paralleler KI-Lauf bleibt unberuehrt
            db.ex("UPDATE job_versions SET status='failed' WHERE job_id=? AND version=? AND status='running'",
                  (job_id, int(request_text)))
        else:
            db.ex("UPDATE job_versions SET status='failed' WHERE job_id=? AND status='running' AND trigger!='param'",
                  (job_id,))
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
    if trigger == "param":   # Spec Stufe B §2: Neuaufbau ohne KI und ohne Autofix; request_text = Versionsnummer
        _run_param(job_id, int(request_text), ev)
        return
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
        text, usage = ai.call(ai.CAD_SYSTEM, msgs, max_tokens=CAD_MAX_TOKENS, cancel=ev,
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
            meta, code = ai.parse_cad(text, _meas_ids(job["project_id"]))
        except ai.AIError as e:
            meta, code = {}, ""
            err = {"stage": "antwort", "type": "FormatError", "message": str(e), "line": None, "code": None}
            db.ex("UPDATE job_versions SET code=?, meta=?, status='failed', error=? WHERE job_id=? AND version=?",
                  (code, db.jdump(meta), db.jdump(err), job_id, version))
            log(job_id, f"Version {version}: Antwort im falschen Format", "warn")
            result, checks = None, []
        else:
            mark_editable(meta, code)
            learned_chk = reconcile_learned(meta, job["project_id"], job_id)   # Spec §4: nur nach KI-Laeufen
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
            _filter_anchors(result)                 # Spec Regel 13: nur gefilterte Anker speichern
            if result:
                _apply_anchors(meta, result)
            checks = compute_checks(result, meta, job["project_id"]) if result else []
            if result and learned_chk:
                checks.append(learned_chk)
            failed = err is not None or any(c["state"] == "fail" for c in checks)
            db.ex("UPDATE job_versions SET status=?, error=?, result=?, checks=?, seconds=?, meta=? "
                  "WHERE job_id=? AND version=?",
                  ("failed" if failed else "ok", db.jdump(err) if err else None, db.jdump(result) if result else None,
                   db.jdump(checks), res.get("seconds"), db.jdump(meta), job_id, version))
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
        out["pending_param"] = pending_param(job["id"])
    return out
