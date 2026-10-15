"""Marker erkennen, Format bestimmen, Fotos auf die Tischebene (bzw. Hoehenlehre) entzerren."""
from __future__ import annotations

import io
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageOps

try:  # HEIC/HEIF von iPhones
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    pass

from .matgen import FORMATS, layout

PX_PER_MM = 10.0
Image.init()  # alle Format-Plugins registrieren, damit die Auswahl unten aufgeloest werden kann
UPLOAD_FORMATS = tuple(f for f in ("JPEG", "MPO", "PNG", "WEBP", "HEIF", "AVIF") if f in Image.OPEN)
GAUGE_MARKER_MM = 18.0
GAUGE_STRIPS = {"A": (10, 11, 14), "B": (12, 13, 15)}
GAUGE_X_RANGE = (-100.0, 100.0)

_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def _detector():
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(_DICT, p)


@lru_cache(maxsize=4)
def spec(fmt: str) -> dict:
    return layout(fmt)


def load_image(data: bytes) -> np.ndarray:
    """Bild laden, EXIF-Drehung anwenden, als BGR zurueckgeben."""
    # Nur Kamera-Formate dekodieren: verkleinert die Angriffsflaeche der Bild-Decoder deutlich.
    im = Image.open(io.BytesIO(data), formats=UPLOAD_FORMATS)
    im = ImageOps.exif_transpose(im).convert("RGB")
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def detect(img: np.ndarray) -> dict[int, np.ndarray]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    corners, ids, _ = _detector().detectMarkers(gray)
    if ids is None:
        return {}
    return {int(i): c[0].astype(np.float32) for i, c in zip(ids.flatten(), corners, strict=True)}


def _square(cx: float, cy: float, s: float) -> np.ndarray:
    h = s / 2
    # OpenCV-Eckreihenfolge (oben links, oben rechts, unten rechts, unten links), Y nach oben
    return np.array([[cx - h, cy + h], [cx + h, cy + h], [cx + h, cy - h], [cx - h, cy - h]], np.float32)


def mat_object_points(fmt: str) -> dict[int, np.ndarray]:
    sp = spec(fmt)
    s = sp["marker_size_mm"]
    return {int(k): _square(v[0], v[1], s) for k, v in sp["centers_mm"].items()}


def gauge_object_points(fmt: str, strip: str) -> dict[int, np.ndarray]:
    ys = spec(fmt)["height_gauge"]["centers_above_fold_mm"]
    return {i: _square(0.0, float(ys[i] if i in ys else ys[str(i)]), GAUGE_MARKER_MM) for i in GAUGE_STRIPS[strip]}


def _fit(found: dict, obj: dict, ids: list[int]):
    src = np.vstack([found[i] for i in ids])
    dst = np.vstack([obj[i] for i in ids])
    H, _ = cv2.findHomography(src, dst, 0)
    return H


def _project(H, pts):
    return cv2.perspectiveTransform(pts.reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2)


def _rms(H, found, obj, ids):
    err = np.vstack([_project(H, found[i]) - obj[i] for i in ids])
    return float(np.sqrt((err ** 2).sum(axis=1).mean()))


def _loo(found, obj, ids) -> dict[int, float]:
    out = {}
    if len(ids) < 4:
        return out
    for i in ids:
        rest = [j for j in ids if j != i]
        Hk = _fit(found, obj, rest)
        out[i] = float(np.abs(_project(Hk, found[i]) - obj[i]).max())
    return out


def verdict(n_markers: int, max_err: float | None) -> str:
    if n_markers < 4 or max_err is None:
        return "nicht_auswertbar"
    if max_err <= 0.5:
        return "gut"
    if max_err <= 1.0:
        return "brauchbar"
    return "unsicher"


def analyze(img: np.ndarray, fmt: str | None = None) -> dict:
    """Komplette Auswertung eines Fotos. fmt=None -> A4/A3 automatisch."""
    found = detect(img)
    h, w = img.shape[:2]
    res: dict = {"width": w, "height": h, "found_ids": sorted(found)}
    mat_ids = sorted(i for i in found if 0 <= i <= 7)
    res["mat_ids"] = mat_ids
    res["missing_ids"] = [i for i in range(8) if i not in found]

    if len(mat_ids) >= 4:
        cands = [fmt] if fmt in FORMATS else list(FORMATS)
        scored = []
        for f in cands:
            obj = mat_object_points(f)
            H = _fit(found, obj, mat_ids)
            scored.append((_rms(H, found, obj, mat_ids), f, H, obj))
        rms, f, H, obj = min(scored, key=lambda t: t[0])
        loo = _loo(found, obj, mat_ids)
        max_err = max(loo.values()) if loo else rms
        res.update(format=f, format_auto=fmt not in FORMATS, homography=H.tolist(), rms_mm=round(rms, 3),
                   loo_mm={str(k): round(v, 3) for k, v in loo.items()}, max_err_mm=round(max_err, 3))
    else:
        res.update(format=fmt if fmt in FORMATS else None, homography=None, rms_mm=None, loo_mm={}, max_err_mm=None)
    res["status"] = verdict(len(mat_ids), res["max_err_mm"])

    # Hoehenlehre
    g = None
    f = res["format"] or "A4"
    for strip, ids in GAUGE_STRIPS.items():
        have = [i for i in ids if i in found]
        if have and (g is None or len(have) > len(g["ids"])):
            g = {"strip": strip, "ids": have}
    if g:
        obj = gauge_object_points(f, g["strip"])
        Hg = _fit(found, obj, g["ids"])
        g["homography"] = Hg.tolist()
        g["rms_mm"] = round(_rms(Hg, found, obj, g["ids"]), 3)
        g["vlen_mm"] = spec(f)["height_gauge"]["vlen_mm"]
    res["gauge"] = g
    return res


def _px_matrix(pxmm: float, h_mm: float) -> np.ndarray:
    """mm (y nach oben) -> Pixel (y nach unten), wie rectify_mat."""
    return np.array([[pxmm, 0, 0], [0, -pxmm, h_mm * pxmm], [0, 0, 1]], np.float64)


def rectify_mat(img: np.ndarray, H, fmt: str, pxmm: float = PX_PER_MM) -> np.ndarray:
    gw, gh = spec(fmt)["grid_mm"]
    to_px = _px_matrix(pxmm, gh)
    return cv2.warpPerspective(img, to_px @ np.asarray(H), (int(gw * pxmm), int(gh * pxmm)),
                               flags=cv2.INTER_CUBIC, borderValue=(235, 236, 236))


def rectify_gauge(img: np.ndarray, gauge: dict, pxmm: float = PX_PER_MM):
    """Senkrechte Ebene der Hoehenlehre. Rueckgabe (Bild, Bereich in mm: x0, x1, y0, y1)."""
    x0, x1 = GAUGE_X_RANGE
    y0, y1 = -10.0, gauge["vlen_mm"] + 10.0
    to_px = np.array([[pxmm, 0, -x0 * pxmm], [0, -pxmm, y1 * pxmm], [0, 0, 1]], np.float64)
    size = (int((x1 - x0) * pxmm), int((y1 - y0) * pxmm))
    out = cv2.warpPerspective(img, to_px @ np.asarray(gauge["homography"]), size,
                              flags=cv2.INTER_CUBIC, borderValue=(235, 236, 236))
    return out, (x0, x1, y0, y1)


# ------------------------------------------------------------------ Unteransicht (Spec 2026-10-15 §1)

LAGEN = (0, 90, 180, 270)
ALIGN_MIN_IOU = 0.6
ALIGN_MIN_GAP = 0.05


def lage_matrix(rot: int, dx: float, dy: float, w: float, h: float) -> np.ndarray:
    """Lage einer Unteransicht in Draufsicht-Koordinaten (mm, y nach oben): Spiegelung x -> w - x,
    Drehung um rot Grad gegen den Uhrzeigersinn um die Bildmitte (w/2, h/2), Verschiebung (dx, dy)."""
    if rot not in LAGEN:
        raise ValueError(f"rot muss in {LAGEN} liegen")
    mirror = np.array([[-1, 0, w], [0, 1, 0], [0, 0, 1]], np.float64)
    a = np.deg2rad(rot)
    c, s = np.cos(a), np.sin(a)
    to_c = np.array([[1, 0, -w / 2], [0, 1, -h / 2], [0, 0, 1]], np.float64)
    rotm = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)
    from_c = np.array([[1, 0, w / 2], [0, 1, h / 2], [0, 0, 1]], np.float64)
    shift = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], np.float64)
    return shift @ from_c @ rotm @ to_c @ mirror


def apply_lage(M: np.ndarray, pts) -> list[list[float]]:
    P = np.asarray(pts, np.float64).reshape(-1, 2)
    Q = (M @ np.hstack([P, np.ones((len(P), 1))]).T).T
    return [[round(float(x), 3), round(float(y), 3)] for x, y, _ in Q]


def align_bottom(top_outline, bottom_outline, bot_w: float, bot_h: float, rot: int | None = None) -> dict:
    """Beste Lage der Unteransicht zur Draufsicht: IoU je Lage nach Schwerpunkt-Verschiebung.
    rot=None: alle vier Lagen; sonst nur diese (iou_next = beste der uebrigen drei)."""
    from shapely.geometry import Polygon  # nur hier: core/ bleibt ohne harte shapely-Abhaengigkeit

    def valid(p):
        if len(p) < 3:
            return Polygon()
        g = Polygon(p)
        return g if g.is_valid else g.buffer(0)
    unsure = {"rot": rot or 0, "dx": 0.0, "dy": 0.0, "iou": 0.0, "iou_next": 0.0, "unsure": True}
    T = valid(top_outline)
    if T.is_empty or T.area < 1.0:
        return unsure
    scores = {}
    for r in LAGEN:
        P = valid(apply_lage(lage_matrix(r, 0, 0, bot_w, bot_h), bottom_outline))
        if P.is_empty or P.area < 1.0:
            scores[r] = (0.0, 0.0, 0.0)
            continue
        dx, dy = T.centroid.x - P.centroid.x, T.centroid.y - P.centroid.y
        Q = valid(apply_lage(lage_matrix(r, dx, dy, bot_w, bot_h), bottom_outline))
        union = T.union(Q).area
        scores[r] = (T.intersection(Q).area / union if union > 0 else 0.0, dx, dy)
    best = rot if rot is not None else max(LAGEN, key=lambda r: (round(scores[r][0], 4), -r))
    iou, dx, dy = scores[best]
    if iou == 0.0:
        return unsure
    iou_next = max(scores[r][0] for r in LAGEN if r != best)
    return {"rot": best, "dx": round(dx, 3), "dy": round(dy, 3), "iou": round(iou, 4), "iou_next": round(iou_next, 4),
            "unsure": bool(iou < ALIGN_MIN_IOU or iou - iou_next < ALIGN_MIN_GAP)}


def bottom_warp_matrix(analysis_bot: dict, analysis_top: dict | None, pxmm_out: float = PX_PER_MM) -> np.ndarray:
    """3x3-Pixelabbildung rect.jpg (Unteransicht) -> Draufsicht-Raster: S_top · lage_matrix · S_bot^-1."""
    rb = analysis_bot["rect"]
    al = analysis_bot.get("bottom_align") or {"rot": 0, "dx": 0.0, "dy": 0.0}
    rt = (analysis_top or analysis_bot)["rect"]
    L = lage_matrix(al["rot"], al["dx"], al["dy"], rb["w_mm"], rb["h_mm"])
    return _px_matrix(pxmm_out, rt["h_mm"]) @ L @ np.linalg.inv(_px_matrix(rb["pxmm"], rb["h_mm"]))


def bottom_warp(rect_bot: np.ndarray, analysis_bot: dict, analysis_top: dict | None = None,
                pxmm_out: float = PX_PER_MM) -> np.ndarray:
    rt = (analysis_top or analysis_bot)["rect"]
    M = bottom_warp_matrix(analysis_bot, analysis_top, pxmm_out)
    return cv2.warpAffine(rect_bot, M[:2], (int(rt["w_mm"] * pxmm_out), int(rt["h_mm"] * pxmm_out)),
                          flags=cv2.INTER_LINEAR, borderValue=(235, 236, 236))


def draw_outlines(img: np.ndarray, polys_mm: list, colors: list, pxmm: float, h_mm: float) -> np.ndarray:
    """Umrisse (mm, y nach oben) in ein Bild zeichnen (fuer align.jpg)."""
    for poly, col in zip(polys_mm, colors, strict=True):
        if poly:
            pts = np.array([[int(x * pxmm), int((h_mm - y) * pxmm)] for x, y in poly], np.int32)
            cv2.polylines(img, [pts], True, col, 2, cv2.LINE_AA)
    return img


def overlay(img: np.ndarray, max_w: int = 1600) -> np.ndarray:
    """Originalfoto mit eingezeichneten Markern (blau) und IDs."""
    found = detect(img)
    ov = img.copy()
    t = max(2, int(max(img.shape[:2]) / 700))
    blue, orange = (178, 111, 31), (12, 85, 194)
    for i, c in found.items():
        pts = c.astype(int)
        cv2.polylines(ov, [pts], True, blue, t * 2, cv2.LINE_AA)
        cv2.circle(ov, tuple(pts[0]), t * 3, orange, -1, cv2.LINE_AA)
        lab = f"ID {i}"
        fs = t * 0.45
        (tw, th), _ = cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, fs, t)
        x = int(pts[:, 0].mean() - tw / 2)
        y = int(pts[:, 1].max() + th + 6 * t)
        cv2.rectangle(ov, (x - 4 * t, y - th - 4 * t), (x + tw + 4 * t, y + 4 * t), blue, -1)
        cv2.putText(ov, lab, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), t, cv2.LINE_AA)
    s = min(1.0, max_w / max(ov.shape[:2]))
    return cv2.resize(ov, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else ov


def thumbnail(img: np.ndarray, max_side: int = 320) -> np.ndarray:
    s = min(1.0, max_side / max(img.shape[:2]))
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img


def encode_jpg(img: np.ndarray, q: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        raise ValueError("JPEG-Kodierung fehlgeschlagen")
    return buf.tobytes()
