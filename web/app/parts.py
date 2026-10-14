"""Teile im Foto: Kanten-Kennungen, Auto-Masse, Zuordnung und Massstab je Teil.

Siehe Spec docs/superpowers/specs/2026-10-14-kanten-und-teile-design.md §2–§3.
"""
from __future__ import annotations

import math
import statistics

from shapely.geometry import LinearRing, Point, Polygon

from . import geom

RECT_TOL_DEG = 4.0
EDGE_DIFF_MM = 1.0
ON_EDGE_MM = 1.5
SCALE_RANGE = (0.75, 1.25)
SPREAD_MAX = 0.01
SCALED_KINDS = ("length", "diameter", "radius")
MM_KINDS = ("length", "height", "diameter", "radius")
ROLE_TEXT = {"body": "Grundkörper", "mounted": "montiertes Teil"}


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
        for key, name, pi in (("L", "Länge", first), ("B", "Breite", 1 - first)):
            use = picks[pi]
            horiz = _angle_diff(_angle(*E[use[0]]), 0.0) < 45
            side = min(use, key=lambda k: _mid(E[k])[1] if horiz else _mid(E[k])[0])
            out.append({"key": key, "kind": "length", "name": name, "raw": round(raws[pi], 3),
                        "points": [list(E[side][0]), list(E[side][1])], "warn": warns[pi]})
    else:
        for (a, b), eid in zip(E, ids, strict=True):
            out.append({"key": f"E{eid}", "kind": "length", "name": f"Kante {eid}", "raw": geom.compute("length", [a, b], fx, fy),
                        "points": [list(a), list(b)], "warn": "verdeckt, geschätzt" if eid in hidden else None})
    for hole in data.get("holes") or []:
        out.append({"key": f"H{hole['id']}", "kind": "diameter", "name": f"Bohrung {hole['id']}",
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
