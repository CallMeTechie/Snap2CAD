"""Messgeometrie (identisch zur Berechnung im Browser)."""
from __future__ import annotations

import math

KINDS = ("length", "height", "diameter", "radius", "angle", "point")
NEEDED = {"length": 2, "height": 2, "diameter": 3, "radius": 3, "angle": 3, "point": 1}


def circle3(p1, p2, p3):
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy, math.hypot(ax - ux, ay - uy)


def compute(kind: str, points: list, fx: float = 1.0, fy: float = 1.0) -> float | None:
    """Wert in mm bzw. Grad aus Rohpunkten (mm) mit Korrekturfaktoren."""
    if kind not in NEEDED or not points or len(points) < NEEDED[kind]:
        return None
    pts = [(float(x) * fx, float(y) * fy) for x, y in points]
    if kind in ("length", "height"):
        (ax, ay), (bx, by) = pts[:2]
        return round(math.hypot(bx - ax, by - ay), 3)
    if kind in ("diameter", "radius"):
        c = circle3(*pts[:3])
        if not c:
            return None
        return round(c[2] * (2 if kind == "diameter" else 1), 3)
    if kind == "angle":
        (ax, ay), (vx, vy), (bx, by) = pts[:3]
        a1 = math.atan2(ay - vy, ax - vx)
        a2 = math.atan2(by - vy, bx - vx)
        d = abs(math.degrees(a1 - a2)) % 360
        return round(360 - d if d > 180 else d, 2)
    return None


def factors(project: dict, ctrl_ref: float | None, grid_h: float | None) -> tuple[float, float]:
    """Korrekturfaktoren aus dem Kontrollmass: ctrl_ref = waagerechter Bezug des Profils (A4/A3 100, Kleinteile 50).
    Gespeicherte Werte ausserhalb ±10 % des aktuellen Bezugs (Unterlage gewechselt) gelten nicht: Faktor 1 (Spec §7 F5)."""
    ref = ctrl_ref or 100.0
    cx, cy = project.get("ctrl_x"), project.get("ctrl_y")
    if cx and not 0.9 * ref <= cx <= 1.1 * ref:
        cx = None
    if cy and grid_h and not 0.9 * grid_h <= cy <= 1.1 * grid_h:
        cy = None
    fx = (cx or ref) / ref
    fy = 1.0
    if cy and grid_h:
        fy = cy / grid_h
    elif cx:
        fy = fx
    return fx, fy


def ctrl_stale(project: dict, ctrl_ref: float | None, grid_h: float | None) -> bool:
    """Ein gespeichertes Kontrollmass passt nicht zum aktuellen Bezug (wird von factors ignoriert)."""
    ref = ctrl_ref or 100.0
    cx, cy = project.get("ctrl_x"), project.get("ctrl_y")
    return bool((cx and not 0.9 * ref <= cx <= 1.1 * ref) or (cy and grid_h and not 0.9 * grid_h <= cy <= 1.1 * grid_h))
