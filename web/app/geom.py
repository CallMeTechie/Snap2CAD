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


def factors(project: dict, fmt: str | None, grid_h: float | None) -> tuple[float, float]:
    fx = (project.get("ctrl_x") or 100.0) / 100.0
    fy = 1.0
    if project.get("ctrl_y") and grid_h:
        fy = project["ctrl_y"] / grid_h
    elif project.get("ctrl_x"):
        fy = fx
    return fx, fy
