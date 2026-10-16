"""Modellbild (preview.png) aus der STL: orthografisch, iso wie im Viewer, Lambert-Schattierung, Maler-Algorithmus.

Nur numpy und OpenCV; keine Ausnahme nach aussen (kaputte Datei -> False)."""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import cv2
import numpy as np

MAX_TRIS = 300_000
VIEW_DIR = (1.0, -1.25, 0.95)   # vom Modell zur Kamera, wie im Viewer
COLOR_RGB = (0x9f, 0xb6, 0xcb)
BG_RGB = (0xf3, 0xf5, 0xf7)
AMBIENT = 0.35
FILL = 0.85
SSAA = 2

_lock = threading.RLock()
_VERTEX = re.compile(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", re.I)


def _read_stl(path: Path) -> np.ndarray:
    """Dreiecke als float32-Feld (n, 3, 3); leeres Feld bei Fehlern."""
    data = path.read_bytes()
    if len(data) >= 84:
        n = int.from_bytes(data[80:84], "little")
        if 84 + 50 * n == len(data):
            rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
            return rec["v"].astype(np.float32)
    if data.lstrip()[:5].lower() == b"solid":
        vals = _VERTEX.findall(data)
        if vals and len(vals) % 3 == 0:
            return np.array(vals, dtype=np.float64).astype(np.float32).reshape(-1, 3, 3)
    return np.zeros((0, 3, 3), np.float32)


def _render(tris: np.ndarray, w: int, h: int) -> np.ndarray | None:
    tris = tris.astype(np.float64)
    tris = tris[np.isfinite(tris).all(axis=(1, 2))]
    if len(tris) == 0:
        return None
    if len(tris) > MAX_TRIS:
        tris = tris[::-(-len(tris) // MAX_TRIS)]
    d = np.array(VIEW_DIR) / np.linalg.norm(VIEW_DIR)
    right = np.cross([0.0, 0.0, 1.0], d)
    right /= np.linalg.norm(right)
    up = np.cross(d, right)
    light = d + 0.5 * up - 0.35 * right
    light /= np.linalg.norm(light)

    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = (ln > 1e-12) & (n @ d > 0)          # Rueckseiten und entartete Dreiecke weglassen
    if not keep.any():
        return None
    tris, n, ln = tris[keep], n[keep], ln[keep]
    n /= ln[:, None]

    ctr = (tris.reshape(-1, 3).min(axis=0) + tris.reshape(-1, 3).max(axis=0)) / 2
    rel = tris - ctr
    sx, sy, depth = rel @ right, rel @ up, rel @ d
    ext_x, ext_y = np.ptp(sx), np.ptp(sy)
    if max(ext_x, ext_y) < 1e-9:
        return None
    sw, sh = w * SSAA, h * SSAA
    scale = FILL * min(sw / max(ext_x, 1e-9), sh / max(ext_y, 1e-9))
    mx, my = (sx.min() + sx.max()) / 2, (sy.min() + sy.max()) / 2
    px = np.rint((sx - mx) * scale + sw / 2).astype(np.int32)
    py = np.rint(sh / 2 - (sy - my) * scale).astype(np.int32)
    pts = np.stack([px, py], axis=2)            # (n, 3, 2)

    lam = np.clip(n @ light, 0, 1)
    inten = AMBIENT + (1 - AMBIENT) * lam
    col = np.clip(np.array(COLOR_RGB[::-1], float)[None, :] * inten[:, None], 0, 255).astype(np.uint8)
    order = np.argsort(depth.mean(axis=1), kind="stable")     # fern zuerst
    img = np.empty((sh, sw, 3), np.uint8)
    img[:] = BG_RGB[::-1]
    for i, c in zip(pts[order].tolist(), col[order].tolist(), strict=True):
        cv2.fillConvexPoly(img, np.array(i, np.int32), c)
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def render_stl_png(stl_path: Path, out_path: Path, w: int = 480, h: int = 360) -> bool:
    """STL (binaer oder ASCII) als PNG rendern; False bei leerer oder kaputter Datei."""
    tmp = Path(str(out_path) + ".tmp")
    try:
        with _lock:
            tris = _read_stl(Path(stl_path))
            img = _render(tris, w, h)
            if img is None:
                return False
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                return False
            tmp.write_bytes(buf.tobytes())
            os.replace(tmp, out_path)
            return True
    except Exception:
        return False
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def ensure_png(stl_path: Path, out_path: Path) -> bool:
    """Vorhandenes Bild verwenden, sonst einmal rendern (parallele Anfragen warten auf den Lock)."""
    with _lock:
        if out_path.is_file():
            return True
        return render_stl_png(stl_path, out_path)
