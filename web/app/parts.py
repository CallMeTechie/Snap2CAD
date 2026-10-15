"""Teile im Foto: Kanten-Kennungen, Auto-Masse, Zuordnung und Massstab je Teil.

Siehe Spec docs/superpowers/specs/2026-10-14-kanten-und-teile-design.md §2–§3.
"""
from __future__ import annotations

import math
import statistics

import cv2
from shapely.geometry import LinearRing, Point, Polygon

from . import ai, db, geom

RECT_TOL_DEG = 4.0
EDGE_DIFF_MM = 1.0
ON_EDGE_MM = 1.5
SCALE_RANGE = (0.75, 1.25)
SPREAD_MAX = 0.01
SCALED_KINDS = ("length", "diameter", "radius")
MM_KINDS = ("length", "height", "diameter", "radius")
ROLE_TEXT = {"body": "Grundkörper", "mounted": "montiertes Teil"}
MAX_PARTS_PER_PHOTO = 12


# ------------------------------------------------------------------ Geometrie (ohne Datenbank)

def edges_of(poly):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


def _seg_len(a, b, fx=1.0, fy=1.0):
    return math.hypot((b[0] - a[0]) * fx, (b[1] - a[1]) * fy)


def _mid(e):
    (a, b) = e
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _angle(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _angle_diff(a1, a2):
    """Winkel zwischen zwei Geraden ohne Richtung, 0..90 Grad."""
    d = abs(math.degrees(a1 - a2)) % 180
    return min(d, 180 - d)


def _valid(poly):
    P = Polygon(poly)
    return P if P.is_valid else P.buffer(0)


def _ccw(poly, flags=None):
    """Polygon gegen den Uhrzeigersinn; Kanten-Kennzeichen (je Kante) werden mitgedreht."""
    pts = [[round(float(x), 3), round(float(y), 3)] for x, y in poly]
    try:
        is_ccw = LinearRing(pts).is_ccw
    except ValueError:
        is_ccw = True
    if is_ccw:
        return pts, (list(flags) if flags is not None else None)
    n = len(pts)
    return pts[::-1], ([flags[(n - 2 - j) % n] for j in range(n)] if flags is not None else None)


def is_rect(poly):
    if len(poly) != 4:
        return False
    for i in range(4):
        a, v, b = poly[i - 1], poly[i], poly[(i + 1) % 4]
        u1, u2 = (a[0] - v[0], a[1] - v[1]), (b[0] - v[0], b[1] - v[1])
        n1, n2 = math.hypot(*u1), math.hypot(*u2)
        if n1 < 1e-6 or n2 < 1e-6:
            return False
        c = max(-1.0, min(1.0, (u1[0] * u2[0] + u1[1] * u2[1]) / (n1 * n2)))
        if abs(math.degrees(math.acos(c)) - 90) > RECT_TOL_DEG:
            return False
    return True


def circle_points(c, d):
    r = d / 2
    return [[round(c[0] + r * math.cos(a), 3), round(c[1] + r * math.sin(a), 3)] for a in (0, 2 * math.pi / 3, 4 * math.pi / 3)]


def auto_name(key):
    """Name eines Auto-Masses aus seinem Schluessel: L, B, E<Kante>, H<Bohrung>."""
    return {"L": "Länge", "B": "Breite"}.get(key) or f"{'Kante' if key[:1] == 'E' else 'Bohrung'} {key[1:]}"


def auto_label(part_label, key):
    """Label eines Auto-Masses; bei langen Teilnamen auf 80 Zeichen gekuerzt."""
    return f"{part_label} {auto_name(key)}"[:80]


def auto_dims(data, fx=1.0, fy=1.0):
    """Auto-Masse eines Teils (Spec §3). raw = Fotowert ohne Teil-Massstab, mit Kontrollmass-Faktoren."""
    poly, ids, hidden = data["polygon"], data["edge_ids"], set(data.get("hidden") or [])
    E = edges_of(poly)
    out = []
    if is_rect(poly):
        lens = [geom.compute("length", [a, b], fx, fy) for a, b in E]
        raws, picks, warns = [], [], []
        for i, j in ((0, 2), (1, 3)):
            vis = [k for k in (i, j) if ids[k] not in hidden]
            use = vis or [i, j]
            raws.append(sum(lens[k] for k in use) / len(use))
            picks.append(use)
            if not vis:
                warns.append("verdeckt, geschätzt")
            elif len(vis) == 2 and abs(lens[i] - lens[j]) > EDGE_DIFF_MM:
                warns.append("gegenüberliegende Kanten ungleich – Kante prüfen")
            else:
                warns.append(None)
        first = 0 if raws[0] >= raws[1] else 1
        for key, pi in (("L", first), ("B", 1 - first)):
            use = picks[pi]
            horiz = _angle_diff(_angle(*E[use[0]]), 0.0) < 45
            side = min(use, key=lambda k: _mid(E[k])[1] if horiz else _mid(E[k])[0])
            out.append({"key": key, "kind": "length", "name": auto_name(key), "raw": round(raws[pi], 3),
                        "points": [list(E[side][0]), list(E[side][1])], "warn": warns[pi]})
    else:
        for (a, b), eid in zip(E, ids, strict=True):
            out.append({"key": f"E{eid}", "kind": "length", "name": auto_name(f"E{eid}"),
                        "raw": geom.compute("length", [a, b], fx, fy),
                        "points": [list(a), list(b)], "warn": "verdeckt, geschätzt" if eid in hidden else None})
    for hole in data.get("holes") or []:
        out.append({"key": f"H{hole['id']}", "kind": "diameter", "name": auto_name(f"H{hole['id']}"),
                    "raw": geom.compute("diameter", circle_points(hole["c"], hole["d"]), fx, fy),
                    "points": circle_points(hole["c"], hole["d"]), "warn": None})
    return out


def _same(p, q, tol=1e-3):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def update_edge_ids(old_poly, old_ids, new_poly, next_id):
    """Kanten-Kennungen nach einer Aenderung durch den Nutzer (Spec §3). Rueckgabe (ids, next_id)."""
    n, m = len(old_poly), len(new_poly)
    if m == n:
        return list(old_ids), next_id
    if m == n + 1:
        for k in range(m):
            if all(_same(a, b) for a, b in zip(new_poly[:k] + new_poly[k + 1:], old_poly, strict=True)):
                e = (k - 1) % n  # geteilte alte Kante old[k-1] -> old[k]
                a = _seg_len(new_poly[k - 1], new_poly[k])
                b = _seg_len(new_poly[k], new_poly[(k + 1) % m])
                first, second = (old_ids[e], next_id) if a >= b else (next_id, old_ids[e])
                ids = []
                for j in range(m):
                    if j == (k - 1) % m:
                        ids.append(first)
                    elif j == k:
                        ids.append(second)
                    else:
                        ids.append(old_ids[(j if j < k else j - 1) % n])
                return ids, next_id + 1
    if m == n - 1:
        for k in range(n):
            if all(_same(a, b) for a, b in zip(old_poly[:k] + old_poly[k + 1:], new_poly, strict=True)):
                e1, e2 = (k - 1) % n, k % n
                l1 = _seg_len(old_poly[e1], old_poly[(e1 + 1) % n])
                l2 = _seg_len(old_poly[e2], old_poly[(e2 + 1) % n])
                ids = []
                for j in range(m):
                    if j == (k - 1) % m:
                        ids.append(old_ids[e1] if l1 >= l2 else old_ids[e2])
                    else:
                        ids.append(old_ids[j if j < k else j + 1])
                return ids, next_id
    return transfer_ids(old_poly, old_ids, new_poly, next_id)


def transfer_ids(old_poly, old_ids, new_poly, next_id):
    """Neue Kanten uebernehmen die Kennung der naechsten alten Kante (Winkel < 6°, Mitte < 3 mm)."""
    old = [(_angle(a, b), _mid((a, b)), eid) for (a, b), eid in zip(edges_of(old_poly), old_ids, strict=True)]
    used, ids = set(), []
    for a, b in edges_of(new_poly):
        ang, mid = _angle(a, b), _mid((a, b))
        best = None
        for oa, om, eid in old:
            if eid in used or _angle_diff(ang, oa) >= 6:
                continue
            d = math.hypot(mid[0] - om[0], mid[1] - om[1])
            if d < 3 and (best is None or d < best[0]):
                best = (d, eid)
        if best:
            used.add(best[1])
            ids.append(best[1])
        else:
            ids.append(next_id)
            next_id += 1
    return ids, next_id


def transfer_holes(old_holes, new_holes, next_id):
    """Bohrungen behalten ihre Kennung bei Mittelpunktabstand <= 2 mm."""
    used, out = set(), []
    for h in new_holes:
        best = None
        for o in old_holes:
            if o["id"] in used:
                continue
            d = math.hypot(h["c"][0] - o["c"][0], h["c"][1] - o["c"][1])
            if d <= 2 and (best is None or d < best[0]):
                best = (d, o["id"])
        if best:
            used.add(best[1])
            hid = best[1]
        else:
            hid = next_id
            next_id += 1
        out.append({"id": hid, "c": h["c"], "d": h["d"]})
    return out, next_id


def _dist_to_line(p, a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L


def _overlap(seg, a, b):
    """Anteil der Kandidatenlaenge, der in Laengsrichtung innerhalb der Polygonseite a-b liegt."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    t = sorted((p[0] - a[0]) * ux + (p[1] - a[1]) * uy for p in seg)
    sl = t[1] - t[0]
    return max(0.0, min(L, t[1]) - max(0.0, t[0])) / sl if sl > 1e-9 else 0.0


def _line(seg):
    (ax, ay), (bx, by) = seg
    L = math.hypot(bx - ax, by - ay)
    return (ax, ay), ((bx - ax) / L, (by - ay) / L)


def _intersect(l1, l2):
    (p1, d1), (p2, d2) = l1, l2
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < math.sin(math.radians(10)):
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


def snap_polygon(poly, segments, preferred=()):
    """KI-Polygon auf OpenCV-Kandidaten einrasten (Spec §2). Rueckgabe (polygon, hidden-Kennzeichen je Kante)."""
    pref = set(preferred)
    groups = ([s for s in segments if s["id"] in pref], [s for s in segments if s["id"] not in pref])
    lines, hidden = [], []
    for a, b in edges_of(poly):
        if _seg_len(a, b) < 1e-6:
            lines.append(None)
            hidden.append(True)
            continue
        ang, best = _angle(a, b), None
        for group in groups:
            for s in group:
                seg = (s["a"], s["b"])
                if _seg_len(*seg) < 1e-6 or _angle_diff(_angle(*seg), ang) >= 6:
                    continue
                dist = (_dist_to_line(seg[0], a, b) + _dist_to_line(seg[1], a, b)) / 2
                if dist >= 3 or _overlap(seg, a, b) < 0.3:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, seg)
            if best:
                break
        lines.append(_line(best[1] if best else (a, b)))
        hidden.append(best is None)
    out = []
    for i, v in enumerate(poly):
        q = _intersect(lines[i - 1], lines[i]) if lines[i - 1] and lines[i] else None
        if q is None or math.hypot(q[0] - v[0], q[1] - v[1]) > 8:
            q = v
        out.append([round(float(q[0]), 3), round(float(q[1]), 3)])
    return out, hidden


def assign(points, parts):
    """Teil fuer eine Messung: alle Punkte in oder an dem Teil, meiste Randpunkte, dann kleinste Flaeche."""
    best = None
    pts = [Point(p) for p in points]
    for pid, poly in parts:
        P = _valid(poly)
        if P.is_empty or P.area <= 0:
            continue
        zone = P.buffer(ON_EDGE_MM)
        if not all(zone.covers(q) for q in pts):
            continue
        near = sum(1 for q in pts if P.boundary.distance(q) <= ON_EDGE_MM)
        key = (-near, P.area)
        if best is None or key < best[0]:
            best = (key, pid)
    return best[1] if best else None


def scale_of(ratios):
    """ratios = [(mid, Messschieber / Fotowert)]. Rueckgabe (k, gueltige mids, ungueltige mids, Warnung)."""
    good = [(m, r) for m, r in ratios if SCALE_RANGE[0] <= r <= SCALE_RANGE[1]]
    bad = [m for m, r in ratios if not SCALE_RANGE[0] <= r <= SCALE_RANGE[1]]
    if not good:
        return 1.0, [], bad, None
    rs = [r for _, r in good]
    k = statistics.median(rs)
    warn = None
    if (max(rs) - min(rs)) / k > SPREAD_MAX:
        warn = "Referenzen widersprechen sich (" + ", ".join(f"{r:.3f}".replace(".", ",") for r in rs) + ")"
    return k, [m for m, _ in good], bad, warn


def nominal(value, unc, caliper=None):
    if caliper is not None:
        return round(caliper, 3)
    if value is None:
        return None
    n = round(value * 2) / 2
    return n if abs(value - n) <= max(unc or 0, 0.2) else None


def match_parts(old, new, threshold=0.5):
    """Greedy-Abgleich ueber IoU >= threshold. Rueckgabe {new_key: old_key}."""
    pairs = []
    for ok_, op in old:
        A = _valid(op)
        for nk, np_ in new:
            B = _valid(np_)
            union = A.union(B).area
            if union > 0:
                iou = A.intersection(B).area / union
                if iou >= threshold:
                    pairs.append((iou, ok_, nk))
    pairs.sort(key=lambda t: -t[0])
    out, used = {}, set()
    for _, ok_, nk in pairs:
        if ok_ in used or nk in out:
            continue
        out[nk] = ok_
        used.add(ok_)
    return out


def assign_holes(parts_list, holes):
    """Bohrungen dem kleinsten Teil zuordnen, dessen Polygon den Mittelpunkt enthaelt."""
    for p in parts_list:
        p["holes"] = []
    for hole in holes:
        c = Point(hole["c"])
        cands = [(_valid(p["polygon"]).area, i) for i, p in enumerate(parts_list) if _valid(p["polygon"]).contains(c)]
        if cands:
            parts_list[min(cands)[1]]["holes"].append({"c": hole["c"], "d": hole["d"]})


# ------------------------------------------------------------------ Datenbank

def default_unc(photo, view):
    """Standard-Unsicherheit einer Fotomessung (vorher main._default_unc)."""
    if not photo:
        return 0.5
    a = db.jload(photo["analysis"], {}) or {}
    if view == "gauge" and a.get("gauge"):
        return round((a["gauge"].get("rms_mm") or 0.3) * 2 + 0.3, 2)
    return round((photo["max_err"] or 0.3) + 0.2, 2)


def _data(row):
    return db.jload(row["data"], {}) or {}


def _next_seq(table, project_id):
    return db.q1(f"SELECT COALESCE(MAX(seq),0)+1 s FROM {table} WHERE project_id=?", (project_id,))["s"]


def create_part(project_id, photo_id, label, role, polygon, *, hidden_flags=None, holes=(), source="user", note=""):
    poly, flags = _ccw(polygon, hidden_flags)
    ids = list(range(1, len(poly) + 1))
    hl = [{"id": i + 1, "c": h["c"], "d": h["d"]} for i, h in enumerate(holes)]
    data = {"polygon": poly, "edge_ids": ids, "next_edge_id": len(ids) + 1,
            "hidden": [e for e, f in zip(ids, flags or [False] * len(ids), strict=True) if f],
            "holes": hl, "next_hole_id": len(hl) + 1, "dropped": [], "warn": None, "refs": [], "note": note}
    return db.ex("""INSERT INTO parts(project_id,photo_id,seq,label,role,data,source,scale,created_at)
                    VALUES (?,?,?,?,?,?,?,1.0,?)""",
                 (project_id, photo_id, _next_seq("parts", project_id), (label or "Teil").strip()[:80] or "Teil",
                  role if role in ROLE_TEXT else "body", db.jdump(data), source, db.now()))


def set_polygon(part, polygon, *, hidden_flags=None, holes=None, redetect=False):
    """Neues Polygon fuer ein Teil. redetect=True: aus einer neuen Erkennung (Kennungen uebertragen)."""
    d = _data(part)
    if redetect:
        poly, flags = _ccw(polygon, hidden_flags)
        ids, nxt = transfer_ids(d["polygon"], d["edge_ids"], poly, d["next_edge_id"])
        d["hidden"] = [e for e, f in zip(ids, flags or [False] * len(ids), strict=True) if f]
    else:
        poly = [[round(float(x), 3), round(float(y), 3)] for x, y in polygon]
        ids, nxt = update_edge_ids(d["polygon"], d["edge_ids"], poly, d["next_edge_id"])
        old = {eid: e for e, eid in zip(edges_of(d["polygon"]), d["edge_ids"], strict=True)}
        moved = {eid for e, eid in zip(edges_of(poly), ids, strict=True)
                 if eid in old and not (_same(e[0], old[eid][0]) and _same(e[1], old[eid][1]))}
        d["hidden"] = [e for e in d.get("hidden") or [] if e in ids and e not in moved]  # vom Nutzer gesetzt = sichtbar
    d.update(polygon=poly, edge_ids=ids, next_edge_id=nxt)
    if holes is not None:
        d["holes"], d["next_hole_id"] = transfer_holes(d.get("holes") or [], holes, d.get("next_hole_id", 1))
    db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), part["id"]))


def _auto_to_user(m):
    d = _data(m)
    d.pop("auto_key", None)
    d.pop("auto_raw", None)
    d.pop("part_fixed", None)
    db.ex("UPDATE measurements SET source='user', data=? WHERE id=?", (db.jdump(d), m["id"]))


def delete_part(part):
    for m in db.q("SELECT * FROM measurements WHERE part_id=?", (part["id"],)):
        if m["source"] == "auto" and m["caliper"] is None:
            db.ex("DELETE FROM measurements WHERE id=?", (m["id"],))
            continue
        if m["source"] == "auto":
            _auto_to_user(m)
        d = _data(db.q1("SELECT data FROM measurements WHERE id=?", (m["id"],)))
        d.pop("part_fixed", None)
        db.ex("UPDATE measurements SET part_id=NULL, data=? WHERE id=?", (db.jdump(d), m["id"]))
    db.ex("DELETE FROM parts WHERE id=?", (part["id"],))


def delete_photo_parts(photo_id):
    for part in db.q("SELECT * FROM parts WHERE photo_id=?", (photo_id,)):
        delete_part(part)


def drop_key(part_id, key):
    part = db.q1("SELECT * FROM parts WHERE id=?", (part_id,))
    if not part or not key:
        return
    d = _data(part)
    if key not in d.setdefault("dropped", []):
        d["dropped"].append(key)
        db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), part_id))


def rename(part, label):
    label = (label or "").strip()[:80] or "Teil"
    old = part["label"]
    db.ex("UPDATE parts SET label=? WHERE id=?", (label, part["id"]))
    for m in db.q("SELECT id, label, data FROM measurements WHERE part_id=? AND source='auto'", (part["id"],)):
        key = _data(m).get("auto_key")
        if key and m["label"] == auto_label(old, key):  # unveraendert, auch wenn der alte Name gekuerzt wurde
            new = auto_label(label, key)
        elif m["label"].startswith(old + " "):  # vom Nutzer ergaenzt: nur den Teilnamen tauschen
            new = (label + m["label"][len(old):])[:80]
        else:
            continue
        db.ex("UPDATE measurements SET label=? WHERE id=?", (new, m["id"]))


def reset_scale(part_id):
    for m in db.q("SELECT id, data FROM measurements WHERE part_id=? AND caliper IS NOT NULL", (part_id,)):
        d = _data(m)
        d["ref"] = False
        db.ex("UPDATE measurements SET data=? WHERE id=?", (db.jdump(d), m["id"]))


def _sync_auto(part, photo, fx, fy):
    """Auto-Masse eines Teils an sein Polygon anpassen (Spec §3)."""
    d = _data(part)
    want = {x["key"]: x for x in auto_dims(d, fx, fy) if x["key"] not in (d.get("dropped") or [])}
    have = {}
    for m in db.q("SELECT * FROM measurements WHERE part_id=? AND source='auto' ORDER BY id", (part["id"],)):
        k = _data(m).get("auto_key")
        if k in have:  # Doppel (z. B. aus einem frueheren Wettlauf) bereinigen
            if m["caliper"] is None:
                db.ex("DELETE FROM measurements WHERE id=?", (m["id"],))
            else:
                _auto_to_user(m)
            continue
        have[k] = m
    for key, x in want.items():
        m = have.get(key)
        if m:
            md = _data(m)
            md.update(points=x["points"], auto_raw=x["raw"], warn=x["warn"])
            db.ex("UPDATE measurements SET kind=?, data=? WHERE id=?", (x["kind"], db.jdump(md), m["id"]))
        else:
            md = {"view": "top", "points": x["points"], "auto_key": key, "auto_raw": x["raw"], "warn": x["warn"], "note": None}
            db.ex("""INSERT INTO measurements(project_id,photo_id,part_id,seq,label,kind,value,unit,unc,data,critical,source,
                     accepted,created_at) VALUES (?,?,?,?,?,?,?,'mm',?,?,0,'auto',1,?)""",
                  (part["project_id"], part["photo_id"], part["id"], _next_seq("measurements", part["project_id"]),
                   auto_label(part["label"], key), x["kind"], x["raw"], default_unc(photo, "top"), db.jdump(md), db.now()))
    for key, m in have.items():
        if key in want:
            continue
        if m["caliper"] is None:
            db.ex("DELETE FROM measurements WHERE id=?", (m["id"],))
        else:
            _auto_to_user(m)


def _computed(m, d):
    """Wird der Wert aus Punkten bzw. dem Teil-Polygon berechnet (und damit auch skaliert)?"""
    return m["source"] == "auto" or (m["source"] != "manual" and not d.get("ai_value") and bool(d.get("points")))


def refresh(project, fx, fy):
    """Zuordnung, Auto-Masse, Massstab je Teil und alle berechneten Werte eines Projekts (Spec §3)."""
    pid = project["id"]
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (pid,))}
    parts = db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (pid,))
    for part in parts:
        _sync_auto(part, photos.get(part["photo_id"]), fx, fy)
    by_photo = {}
    for part in parts:
        by_photo.setdefault(part["photo_id"], []).append((part["id"], _data(part)["polygon"]))
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1", (pid,))
    datas = {m["id"]: _data(m) for m in rows}
    for m in rows:  # 1. Zuordnung
        d = datas[m["id"]]
        if m["source"] == "auto" or d.get("part_fixed"):
            continue
        new = None
        if m["source"] != "manual" and d.get("view", "top") == "top" and m["kind"] != "height" and d.get("points") \
                and m["photo_id"] in by_photo:
            new = assign(d["points"], by_photo[m["photo_id"]])
        if new != m["part_id"]:
            db.ex("UPDATE measurements SET part_id=? WHERE id=?", (new, m["id"]))
            m["part_id"] = new
    raw = {}
    for m in rows:  # 2. Fotowerte ohne Teil-Massstab
        d = datas[m["id"]]
        if m["source"] == "auto":
            raw[m["id"]] = d.get("auto_raw")
        elif _computed(m, d):
            raw[m["id"]] = geom.compute(m["kind"], d["points"], fx, fy)
    kmap, ref_warn = {}, {}
    for part in parts:  # 3. Massstab je Teil
        refs = [(m["id"], m["caliper"] / raw[m["id"]]) for m in rows
                if m["part_id"] == part["id"] and m["caliper"] is not None and m["kind"] in SCALED_KINDS
                and datas[m["id"]].get("ref") is not False and datas[m["id"]].get("view", "top") == "top" and raw.get(m["id"])]
        k, good, bad, warn = scale_of(refs)
        kmap[part["id"]] = k
        for mid in bad:
            ref_warn[mid] = "Abweichung zu groß – falsches Maß oder falsches Teil?"
        pd = _data(db.q1("SELECT data FROM parts WHERE id=?", (part["id"],)))
        pd.update(warn=warn, refs=good)
        db.ex("UPDATE parts SET scale=?, data=? WHERE id=?", (k, db.jdump(pd), part["id"]))
    for m in rows:  # 4. Werte, Hinweise, Nennmass
        d = dict(datas[m["id"]])
        r = raw.get(m["id"])
        value = m["value"]
        if _computed(m, d) and r is not None:
            k = kmap.get(m["part_id"], 1.0) if m["kind"] in SCALED_KINDS and d.get("view", "top") == "top" else 1.0
            value = round(r * k, 3)
            d["raw"] = round(r, 3)
        else:
            d.pop("raw", None)
        d["ref_warn"] = ref_warn.get(m["id"])
        d["nominal"] = nominal(value, m["unc"], m["caliper"]) if m["kind"] in MM_KINDS else None
        if value != m["value"] or d != datas[m["id"]]:
            db.ex("UPDATE measurements SET value=?, data=? WHERE id=?", (value, db.jdump(d), m["id"]))


def part_public(part):
    d = _data(part)
    poly = d["polygon"]
    ms = db.q("SELECT id, seq, value, data FROM measurements WHERE part_id=?", (part["id"],))
    by_key = {_data(x).get("auto_key"): x["value"] for x in ms}
    seq = {x["id"]: x["seq"] for x in ms}
    rect = is_rect(poly)
    return {"id": part["id"], "seq": part["seq"], "id_label": f"T{part['seq']}", "photo_id": part["photo_id"],
            "label": part["label"], "role": part["role"], "source": part["source"], "scale": part["scale"],
            "polygon": poly, "edge_ids": d["edge_ids"], "hidden": d.get("hidden") or [], "holes": d.get("holes") or [],
            "warn": d.get("warn"), "note": d.get("note") or "", "rect": rect,
            "size": [by_key["L"], by_key["B"]] if rect and "L" in by_key and "B" in by_key else None,
            "n_edges": len(poly), "refs": [f"M{seq[i]}" for i in d.get("refs") or [] if i in seq]}


def public_list(project_id):
    return [part_public(p) for p in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (project_id,))]


def replace_detected(project_id, photo_id, detected):
    """Ergebnis einer Erkennung uebernehmen: Abgleich ueber IoU (Spec §2), sonst neu bzw. loeschen.
    Rueckgabe: Zahl der neuen Teile, die wegen MAX_PARTS_PER_PHOTO nicht angelegt wurden."""
    old = db.q("SELECT * FROM parts WHERE photo_id=? AND source!='user' ORDER BY seq", (photo_id,))  # Handteile bleiben
    m = match_parts([(o["id"], _data(o)["polygon"]) for o in old], [(i, x["polygon"]) for i, x in enumerate(detected)])
    kept = set(m.values())
    for o in old:
        if o["id"] not in kept:
            delete_part(o)
    by_id = {o["id"]: o for o in old}
    room = MAX_PARTS_PER_PHOTO - db.q1("SELECT COUNT(*) n FROM parts WHERE photo_id=?", (photo_id,))["n"]
    skipped = 0
    for i, x in enumerate(detected):
        if i in m:
            set_polygon(by_id[m[i]], x["polygon"], hidden_flags=x.get("hidden"), holes=x.get("holes") or [], redetect=True)
        elif room > 0:
            create_part(project_id, photo_id, x["label"], x["role"], x["polygon"], hidden_flags=x.get("hidden"),
                        holes=x.get("holes") or [], source=x.get("source", "auto"), note=x.get("note", ""))
            room -= 1
        else:
            skipped += 1
    return skipped


def outline_parts(res):
    """Ohne KI: jeder Umriss wird ein Teil, Bohrungen zum kleinsten umgebenden Teil."""
    out = [{"label": "Teil", "role": "body", "polygon": o["polygon"], "hidden": [False] * len(o["polygon"]), "source": "auto"}
           for o in res["outlines"]]
    assign_holes(out, res["holes"])
    return out


def candidate_image(photo_dir, res):
    """Kandidatenbild fuer die KI als edges_ki.jpg im Fotoordner (Zeichnen in core.edges)."""
    from core import edges as core_edges  # spaet: main.py setzt sys.path erst nach den App-Importen
    img = core_edges.draw_candidates(cv2.imread(str(photo_dir / "rect.jpg")), res)
    out = photo_dir / "edges_ki.jpg"
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out


def candidate_text(res):
    lines = ["Kanten-Kandidaten (mm, Draufsicht):"]
    for s in res["segments"]:
        lines.append(f"{s['id']}: ({s['a'][0]:.1f}, {s['a'][1]:.1f}) → ({s['b'][0]:.1f}, {s['b'][1]:.1f}), "
                     f"{_seg_len(s['a'], s['b']):.1f} mm, {'Umriss' if s['kind'] == 'outline' else 'Innenkante'}")
    for i, o in enumerate(res["outlines"], 1):
        lines.append(f"Umriss {i}: " + " ".join(f"({x:.1f}, {y:.1f})" for x, y in o["polygon"]))
    for h in res["holes"]:
        lines.append(f"Bohrung: Mitte ({h['c'][0]:.1f}, {h['c'][1]:.1f}), Ø {h['d']:.1f} mm")
    return "\n".join(lines)


def plausible(poly, outlines, min_area=25.0):
    """KI-Teil nur uebernehmen, wenn es Flaeche hat und mindestens zur Haelfte im erkannten Objekt liegt."""
    P = _valid(poly)
    if P.is_empty or P.area < min_area or not outlines:
        return False
    U = _valid(outlines[0]["polygon"])
    for o in outlines[1:]:
        U = U.union(_valid(o["polygon"]))
    return P.intersection(U).area >= 0.5 * P.area


def ai_parts(photo_dir, res):
    """Teile per KI zuordnen und auf die Kandidaten einrasten. Leere Liste = KI hat nichts Brauchbares geliefert."""
    img = candidate_image(photo_dir, res)
    content = ai.image_ref(img, ai.scaled_caption(img, "Draufsicht mit nummerierten Kanten-Kandidaten", res["px_per_mm"]))
    content.append({"type": "text", "text": candidate_text(res)})
    text, _ = ai.call(ai.PARTS_SYSTEM, [{"role": "user", "content": content}], max_tokens=4000)
    out = []
    for it in ai.parse_parts(text):
        poly, hidden = snap_polygon(it["polygon"], res["segments"], it["edges"])
        if not plausible(poly, res["outlines"]):
            continue
        out.append({"label": it["label"], "role": it["role"], "polygon": poly, "hidden": hidden, "note": it["note"],
                    "source": "ki"})
    assign_holes(out, res["holes"])
    return out


def cad_text(project_id, part_id=None):
    """Hinweis fuer die CAD-KI, welche Teile es gibt und welches modelliert wird (Spec §5)."""
    rows = db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (project_id,))
    if not rows:
        return ""
    if part_id:
        t = next((r for r in rows if r["id"] == part_id), None)
        if not t:
            return ""
        pts = " ".join(f"({x:.1f}, {y:.1f})" for x, y in _data(t)["polygon"])
        return (f"Modelliert wird nur Teil T{t['seq']} „{t['label']}“ ({ROLE_TEXT[t['role']]}). "
                f"Umriss in der Draufsicht (mm): {pts}. Maße anderer Teile sind nicht enthalten.")
    names = ", ".join(f"T{r['seq']} {r['label']} ({ROLE_TEXT[r['role']]})" for r in rows)
    return f"Teile im Foto: {names}. Alle Teile als ein Körper modellieren."
