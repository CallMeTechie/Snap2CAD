"""Kanten eines Objekts auf der entzerrten Draufsicht finden – ohne KI.

Eingabe: rect.jpg (Massstab aus dem Profil, genau die Feldflaeche). Ausgabe in mm der Rasterflaeche
(Ursprung unten links, x nach rechts, y nach oben), siehe Spec 2026-10-14-kanten-und-teile §1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .vision import spec

WORK_PXMM = 4.0        # Aufloesung fuer die Objektmaske
MIN_AREA_MM2 = 25.0
APPROX_MM = 0.8
SEARCH_MM = 1.5        # Suchweite der Kantenverfeinerung entlang der Normalen
MAX_SHIFT_MM = 2.0
MIN_SEG_MM = 8.0
MAX_SEGMENTS = 40
MAX_OUTLINES = 6
MAX_VERTS = 64
GRID_WIN_MM = 6.0      # phasenrichtiges Mittelungsfenster des Rasterkriteriums
GRID_SMOOTH_MM = 6.0   # Glaettung danach (gleicht die dickeren 5-/10-mm-Linien aus)
GRID_PAPER = 0.6       # Anteil der Papier-Rasterstaerke: darueber sicher Papier
GRID_OBJECT = 0.35     # darunter Objektinneres
FILL_MM2 = 300.0       # Inseln (Schraubenkoepfe) im Rasterkriterium bis zu dieser Flaeche fuellen
HOLE_MAX_MM2 = 2000.0  # groessere runde Luecken gelten nicht als Bohrung
COLOR_MIN_DIFF = 18.0  # Mindest-Farbabstand zum Papier (uint8-Skala), falls Otsu sehr niedrig liegt
GRID_FINE_MM = 2.0     # feines Fenster (Mittelung und Glaettung) fuer das Schatten-Veto: Raster dicht an der Objektkante
SHADOW_CHROMA = 6.0    # bis zu diesem Farbabstand (a/b) gilt ein Unterschied als reiner Helligkeitsunterschied (Schatten)
TRANSP_MIN_DIFF = 9.0  # Mindest-Farbabstand bei transparent = 2 (durchsichtiges Teil: Raster scheint durch)
TRANSP_DIFF_FACTOR = 0.5   # transparent = 2: Anteil der Otsu-Schwelle fuer den Farbabstand
TRANSP_CLOSE_MM = 3.0      # transparent = 2: Luecken der Farbmaske bis zu dieser Breite schliessen
PART_TRANSP_GRID_FACTOR = 0.5  # transparent = 1: Rasterkriterium strenger (Raster scheint teilweise durch)
LIGHT_DIFF_FACTOR = 0.6    # light: Anteil der Otsu-Schwelle fuer den Farbabstand (helles Teil, wenig Kontrast)
LIGHT_MIN_DIFF = 12.0      # light: Mindest-Farbabstand statt COLOR_MIN_DIFF
LIGHT_GRID_FACTOR = 1.3    # light: Rasterkriterium grosszuegiger (schwaches Raster gilt schon als Objekt)


@dataclass(frozen=True)
class Scale:
    """Massstab eines Messformats (Spec Kleinteile §3): Laengen in mm mal k, Flaechen mal k²."""
    pxmm: float       # Rechteckbild px/mm
    work: float       # Arbeitsaufloesung der Maske px/mm (WORK_PXMM / k)
    k: float          # Kantenmassstab
    field: str        # grid | plain_light | plain_dark
    hole_max: float   # groesste Bohrung in mm²
    frame: bool       # Marker im Rahmen ausserhalb des Feldes


def scale_for(fmt: str) -> Scale:
    sp = spec(fmt)
    k = float(sp["edge_scale"])
    return Scale(float(sp["pxmm"]), WORK_PXMM / k, k, sp["field"], float(sp["hole_max_mm2"]), sp["marker_pos"] == "frame")


def _odd(n: float) -> int:
    return max(3, int(round(n)) | 1)


def _marker_mask(fmt: str, shape, sc: Scale) -> np.ndarray:
    """255 = auswertbar, 0 = Markerfeld (alle Marker liegen innerhalb der Rasterflaeche)."""
    if sc.frame:  # Marker liegen ausserhalb des Feldes
        return np.full(shape, 255, np.uint8)
    sp = spec(fmt)
    gh = sp["grid_mm"][1]
    valid = np.full(shape, 255, np.uint8)
    half = sp["marker_size_mm"] / 2 + 2 * sc.k
    for cx, cy in sp["centers_mm"].values():
        x0, x1 = int((cx - half) * sc.work), int(math.ceil((cx + half) * sc.work))
        y0, y1 = int((gh - cy - half) * sc.work), int(math.ceil((gh - cy + half) * sc.work))
        valid[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = 0
    return valid


def _drop_small(mask: np.ndarray, sc: Scale) -> np.ndarray:
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] / sc.work ** 2 >= MIN_AREA_MM2 * sc.k ** 2:
            keep[lbl == i] = 255
    return keep


def _grabcut(mask: np.ndarray, img: np.ndarray, sure_fg: np.ndarray, sure_bg: np.ndarray, sc: Scale) -> np.ndarray:
    """GrabCut nur im Begrenzungsrahmen der Maske plus 10 mm (Spec §1.4). sure_fg/sure_bg: feste Vorgaben
    aus dem Rasterkriterium, damit helle, papierfarbene Flaechen (Blech) nicht als Papier enden."""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return mask
    h, w = mask.shape
    m = int(10 * sc.k * sc.work)
    x0, y0 = max(0, int(xs.min()) - m), max(0, int(ys.min()) - m)
    x1, y1 = min(w, int(xs.max()) + m + 1), min(h, int(ys.max()) + m + 1)
    sub = mask[y0:y1, x0:x1]
    gc = np.full(sub.shape, cv2.GC_PR_BGD, np.uint8)
    gc[sub > 0] = cv2.GC_PR_FGD
    gc[(cv2.erode(sub, np.ones((5, 5), np.uint8)) > 0) | sure_fg[y0:y1, x0:x1]] = cv2.GC_FGD
    gc[sure_bg[y0:y1, x0:x1]] = cv2.GC_BGD
    if not ((gc == cv2.GC_PR_BGD) | (gc == cv2.GC_BGD)).any():
        return mask
    try:
        cv2.grabCut(np.ascontiguousarray(img[y0:y1, x0:x1]), gc, None, np.zeros((1, 65)), np.zeros((1, 65)), 3,
                    cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return mask
    out = mask.copy()
    out[y0:y1, x0:x1] = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    out[sure_bg] = 0
    out = _drop_small(out, sc)
    return out if int(out.sum()) >= 0.5 * int(mask.sum()) else mask


def _grid_demod(rect: np.ndarray, sc: Scale) -> list[tuple[np.ndarray, np.ndarray]]:
    """Gabor-Antwort auf das 1-mm-Raster, mit der Rasterperiode demoduliert: (Real, Imaginaer) je Richtung.

    In der entzerrten Draufsicht liegen die Rasterlinien an festen Positionen (Periode sc.pxmm px). Beim
    Papier bleibt die Phase der demodulierten Antwort konstant, bei Metall-, Holz- oder Kunststofftextur
    wechselt sie und loescht sich beim Mitteln aus (siehe _grid_energy)."""
    g = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY).astype(np.float32)
    H, W = g.shape
    n = _odd(4 * sc.pxmm)
    t = np.arange(n, dtype=np.float32) - n // 2
    win = np.hanning(n).astype(np.float32)
    kc = np.cos(2 * np.pi * t / sc.pxmm) * win
    ks = np.sin(2 * np.pi * t / sc.pxmm) * win
    out = []
    for horiz in (True, False):
        c = cv2.filter2D(g, -1, kc[None, :] if horiz else kc[:, None])
        s_ = cv2.filter2D(g, -1, ks[None, :] if horiz else ks[:, None])
        pos = (np.arange(W, dtype=np.float32)[None, :] if horiz else np.arange(H, dtype=np.float32)[:, None])
        ph = 2 * np.pi * pos / sc.pxmm
        out.append((c * np.cos(ph) - s_ * np.sin(ph), c * np.sin(ph) + s_ * np.cos(ph)))
    return out


def _grid_energy(rect: np.ndarray, sc: Scale, win_mm: float = GRID_WIN_MM, smooth_mm: float = GRID_SMOOTH_MM,
                 demod: list | None = None) -> np.ndarray:
    """Staerke des 1-mm-Rasters je Ort (auf sc.work), phasenrichtig gemittelt. Papier ~ hoch, Objekt ~ 0.

    Die demodulierte Gabor-Antwort (_grid_demod) wird ueber win_mm flaechig gemittelt und danach ueber
    smooth_mm geglaettet. So bleiben auch helle, papierfarbene Flaechen (Blech) als Objekt erkennbar.
    demod: bereits berechnetes _grid_demod(rect), wenn mehrere Fenster auf dasselbe Bild angewandt werden."""
    H, W = rect.shape[:2]
    box = _odd(win_mm * sc.k * sc.pxmm)
    mags = [cv2.magnitude(cv2.boxFilter(re, -1, (box, box)), cv2.boxFilter(im, -1, (box, box)))
            for re, im in (demod or _grid_demod(rect, sc))]
    e = np.minimum(*mags)  # Papier hat Linien in beiden Richtungen, eine einzelne Kante nur in einer
    small = cv2.resize(e, (int(round(W * sc.work / sc.pxmm)), int(round(H * sc.work / sc.pxmm))),
                       interpolation=cv2.INTER_AREA)
    k = _odd(smooth_mm * sc.k * sc.work)
    return cv2.boxFilter(small, -1, (k, k))


def _fill_small(mask: np.ndarray, max_mm2: float, sc: Scale) -> np.ndarray:
    """Eingeschlossene Luecken bis max_mm2 fuellen (z. B. glaenzende Schraubenkoepfe im Rasterkriterium)."""
    inv = cv2.bitwise_not(mask)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(inv)
    h, w = mask.shape
    out = mask.copy()
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area / sc.work ** 2 <= max_mm2 and x > 0 and y > 0 and x + bw < w and y + bh < h:
            out[lbl == i] = 255
    return out


def _paper_fit(lab: np.ndarray, sample: np.ndarray) -> np.ndarray:
    """Papierfarbe je Ort als glatte quadratische Flaeche (gleicht Helligkeitsverlauf und Schatten auf dem Papier aus)."""
    h, w = sample.shape
    ys, xs = np.nonzero(sample)
    if len(xs) < 50:
        return np.broadcast_to(np.median(lab.reshape(-1, 3), axis=0), lab.shape).astype(np.float32)
    step = max(1, len(xs) // 20000)
    xs, ys = xs[::step], ys[::step]

    def design(x, y):
        x, y = x / w - 0.5, y / h - 0.5
        return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1)
    coef, *_ = np.linalg.lstsq(design(xs.astype(np.float32), ys.astype(np.float32)), lab[ys, xs], rcond=None)
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    return (design(gx, gy) @ coef).astype(np.float32)


def _prep(rect: np.ndarray, sc: Scale) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gemeinsamer Anfang von _mask und _mask_plain: Bild auf sc.work verkleinern, feine Linien schliessen
    (closed, BGR), dasselbe in Lab (float32) und der Randstreifen von 8 mm · k (band, bool)."""
    s = sc.work / sc.pxmm
    small = cv2.resize(rect, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    k = _odd(1.5 * sc.k * sc.work)
    closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    lab = cv2.cvtColor(closed, cv2.COLOR_BGR2LAB).astype(np.float32)
    b = int(8 * sc.k * sc.work)
    band = np.zeros((h, w), bool)
    band[:b] = True
    band[-b:] = True
    band[:, :b] = True
    band[:, -b:] = True
    return closed, lab, band


def _mask_plain(rect: np.ndarray, hints: dict, sc: Scale) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Objektmaske auf einem Feld ohne Raster (Spec Kleinteile §3 „Feldfarbe“): Feldfarbe aus dem Randstreifen,
    Farbabstand beidseitig (hell auf dunkel und dunkel auf hell). Kein Rasterkriterium, kein Schatten-Veto.
    Rueckgabe wie _mask."""
    t = hints.get("transparent", 0)
    light = bool(hints.get("light", False))
    closed, lab, band = _prep(rect, sc)
    valid = np.full(band.shape, 255, np.uint8)
    field = _paper_fit(lab, band)
    # zweite Anpassung ohne Ausreisser: ein Teil im Randstreifen soll die Feldfarbe nicht verschieben
    r0 = np.abs(lab[..., 0] - field[..., 0]) + 2 * np.hypot(lab[..., 1] - field[..., 1], lab[..., 2] - field[..., 2])
    keep = band & (r0 < max(3.0 * float(np.median(r0[band])), COLOR_MIN_DIFF))
    if keep.sum() >= 0.5 * band.sum():
        field = _paper_fit(lab, keep)
    else:
        keep = band
    dl = np.abs(field[..., 0] - lab[..., 0])
    dc = np.hypot(lab[..., 1] - field[..., 1], lab[..., 2] - field[..., 2])
    diff = np.clip(dl + 2 * dc, 0, 255).astype(np.uint8)
    th, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if t == 2:
        color = diff > max(TRANSP_DIFF_FACTOR * th, TRANSP_MIN_DIFF)
        return _mask_transparent(color, valid, sc), np.where(color, 255, 0).astype(np.uint8), diff
    if t == 1:
        thr = max(TRANSP_DIFF_FACTOR * th, TRANSP_MIN_DIFF)
    elif light:
        thr = max(LIGHT_DIFF_FACTOR * th, LIGHT_MIN_DIFF)
    else:
        thr = max(th, COLOR_MIN_DIFF)
    color = diff > thr
    mask = np.where(color, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    sure_fg = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    out = _grabcut(_drop_small(mask, sc), closed, sure_fg, keep, sc)   # sicher Feld: Randstreifen ohne Teile
    return _fill_unround(out, valid, sc), np.where(color, 255, 0).astype(np.uint8), diff


def _mask(rect: np.ndarray, fmt: str, hints: dict, sc: Scale) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Objektmaske auf sc.work (255 = Objekt), Spec §1.1–1.4: Farbabstand zum Papier plus Rasterkriterium.
    Zweiter Rueckgabewert: reine Farbmaske (fuer Bohrungen; das Rasterkriterium fuellt kleine Loecher auf),
    dritter: Farbabstand zum Papier (uint8, fuer den Kontrastwert).

    hints: {"transparent": 0|1|2, "light": bool}. Ohne Transparenz-Hinweis wird das Rasterkriterium auf die
    oertliche Helligkeit normiert und ein Schatten-Veto angewandt: Papier, das nur dunkler ist (kaum Farbabstand)
    und dessen Raster im feinen Fenster sichtbar bleibt, ist Schlagschatten und kein Objekt."""
    if sc.field != "grid":
        return _mask_plain(rect, hints, sc)
    t = hints.get("transparent", 0)
    light = bool(hints.get("light", False))
    closed, lab, band = _prep(rect, sc)
    h, w = band.shape
    valid = _marker_mask(fmt, (h, w), sc)
    band &= valid > 0
    # sicher Papier erst eine Fensterbreite vom Objekt entfernt (an Objektecken sieht das Fenster viel Papier)
    k_bg = _odd((GRID_WIN_MM + GRID_SMOOTH_MM) * sc.k * sc.work)
    demod = _grid_demod(rect, sc)
    en_raw = _grid_energy(rect, sc, demod=demod)[:h, :w]
    if t == 0:
        # Helligkeitsnormierung: im Schatten ist das Raster dunkler und schwaecher, gemessen wird relativ zur Umgebung
        lloc = cv2.boxFilter(lab[..., 0], -1, (k_bg, k_bg))
        gain = float(np.median(lloc[band])) / np.maximum(lloc, 1)
        fine = _grid_energy(rect, sc, GRID_FINE_MM, GRID_FINE_MM, demod)[:h, :w] * gain
        ref_f = float(np.median(fine[band])) or 1.0

    def attempt(veto: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Ein Durchlauf; veto = Helligkeitsnormierung und Schatten-Veto anwenden (nur bei t == 0 moeglich)."""
        en = en_raw * gain if veto else en_raw
        ref = float(np.median(en[band])) or 1.0
        paperish = (en > GRID_PAPER * ref) & (valid > 0)          # Raster deutlich sichtbar: Papier
        paper = _paper_fit(lab, paperish | band)
        dl = np.clip(paper[..., 0] - lab[..., 0], 0, None)
        dc = np.hypot(lab[..., 1] - paper[..., 1], lab[..., 2] - paper[..., 2])
        diff = np.clip(dl + 2 * dc, 0, 255).astype(np.uint8)
        diff[valid == 0] = 0
        th, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        if t == 2:  # nur Farbabstand: ohne Rasterkriterium, ohne sicheres Papier, ohne Schatten-Veto
            color = diff > max(TRANSP_DIFF_FACTOR * th, TRANSP_MIN_DIFF)
            return _mask_transparent(color, valid, sc), np.where(color, 255, 0).astype(np.uint8), diff
        color = diff > (max(LIGHT_DIFF_FACTOR * th, LIGHT_MIN_DIFF) if light else max(th, COLOR_MIN_DIFF))
        if veto:  # Schatten-Veto: nur dunkler (kaum Farbabstand), Raster im feinen Fenster sichtbar -> Papier
            color &= ~((dc < SHADOW_CHROMA) & (fine > GRID_PAPER * ref_f))
        sure_bg = cv2.erode(paperish.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_bg, k_bg))) > 0
        # Rasterkriterium nur, wo das Mittelungsfenster ganz auf der freien Messflaeche liegt (nicht an Rand/Markern)
        inner = cv2.erode(np.pad(valid, 1), cv2.getStructuringElement(cv2.MORPH_RECT, (k_bg, k_bg)))[1:-1, 1:-1] > 0
        grid_obj = GRID_OBJECT * (PART_TRANSP_GRID_FACTOR if t == 1 else 1.0) * (LIGHT_GRID_FACTOR if light else 1.0)
        nogrid = np.where((en < grid_obj * ref) & inner, 255, 0).astype(np.uint8)
        nogrid = _fill_small(_drop_small(nogrid, sc), FILL_MM2 * sc.k ** 2, sc)
        mask = np.where((color & ~sure_bg) | (nogrid > 0), 255, 0).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        sure_fg = cv2.erode(nogrid, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
        out = _grabcut(_drop_small(mask, sc), closed, sure_fg, sure_bg, sc)
        return _fill_unround(out, valid, sc), np.where(color, 255, 0).astype(np.uint8), diff

    res = attempt(t == 0)
    if t == 0 and not light and not _drop_small(res[0], sc).any():
        res = attempt(False)  # Rueckfall ohne Hinweise: Verhalten vor Normierung und Schatten-Veto
    return res


def _mask_transparent(color: np.ndarray, valid: np.ndarray, sc: Scale) -> np.ndarray:
    """Maske fuer durchsichtige Teile (transparent = 2): Farbmaske schliessen, Luecken fuellen, groesste
    Komponente. Kein GrabCut, weil das durchscheinende Raster dort Papier vortaeuscht."""
    k = _odd(TRANSP_CLOSE_MM * sc.k * sc.work)
    m = cv2.morphologyEx(np.where(color, 255, 0).astype(np.uint8), cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    m = _fill_unround(m, valid, sc)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return m
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(lbl == i, 255, 0).astype(np.uint8)


def _fill_unround(mask: np.ndarray, valid: np.ndarray, sc: Scale) -> np.ndarray:
    """Luecken im Objekt fuellen, die keine runden Bohrungen sind (spiegelndes Blech, Schatten auf der Platte).
    Markerfelder zaehlen dabei als geschlossen, damit ein Objekt neben einem Marker nicht 'ausläuft'."""
    probe = np.where((mask > 0) | (valid == 0), 255, 0).astype(np.uint8)
    cnts, hier = cv2.findContours(probe, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = mask.copy()
    if hier is None:
        return out
    for i, c in enumerate(cnts):
        if hier[0][i][3] < 0:
            continue
        area = cv2.contourArea(c) / sc.work ** 2
        per = cv2.arcLength(c, True) / sc.work
        round_ = per > 0 and 4 * math.pi * area / per ** 2 >= 0.85 and area <= sc.hole_max
        if not round_:
            cv2.drawContours(out, [c], -1, 255, -1)
    out[valid == 0] = 0
    return out


def _refine(poly: list, gx: np.ndarray, gy: np.ndarray, gh: float, sc: Scale) -> list:
    """Polygonseiten auf dem vollen Bild an den staerksten Gradienten legen (Spec §1.5)."""
    px = sc.pxmm
    H, W = gx.shape
    P = [np.array([x * px - 0.5, (gh - y) * px - 0.5]) for x, y in poly]
    n = len(P)
    offs = np.arange(-SEARCH_MM * sc.k * px, SEARCH_MM * sc.k * px + 0.01, 0.5)
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        L = float(np.linalg.norm(b - a))
        if L < 5 * sc.k * px:
            lines.append(None)
            continue
        t = (b - a) / L
        nrm = np.array([-t[1], t[0]])
        pts = []
        for s in np.arange(2 * sc.k * px, L - 2 * sc.k * px, sc.k * px / 2):
            q = a + t * s + nrm[None, :] * offs[:, None]
            xi = np.clip(np.rint(q[:, 0]).astype(int), 0, W - 1)
            yi = np.clip(np.rint(q[:, 1]).astype(int), 0, H - 1)
            v = np.abs(gx[yi, xi] * nrm[0] + gy[yi, xi] * nrm[1])
            k = int(v.argmax())
            if v[k] < 40:
                continue
            sub = 0.0
            if 0 < k < len(v) - 1:
                den = v[k - 1] - 2 * v[k] + v[k + 1]
                sub = float(0.5 * (v[k - 1] - v[k + 1]) / den) if den else 0.0
            pts.append(a + t * s + nrm * (offs[k] + sub * 0.5))
        if len(pts) < 4:
            lines.append(None)
            continue
        vx, vy, x0, y0 = cv2.fitLine(np.array(pts, np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines.append((np.array([x0, y0], float), np.array([vx, vy], float)))
    out = []
    for i in range(n):
        v = P[i]
        l1, l2 = lines[i - 1], lines[i]
        if l1 is not None and l2 is not None:
            (p1, d1), (p2, d2) = l1, l2
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) > math.sin(math.radians(10)):
                tt = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
                q = p1 + d1 * tt
                if np.linalg.norm(q - v) <= MAX_SHIFT_MM * sc.k * px:
                    v = q
        out.append([round(float((v[0] + 0.5) / px), 3), round(float(gh - (v[1] + 0.5) / px), 3)])
    return out


def _refine_hole(c: tuple, d0: float, gray: np.ndarray, gh: float, sc: Scale) -> dict | None:
    """Bohrung auf dem vollen Bild: Schwelle zwischen Innen- und Ringhelligkeit, Ellipse anpassen (Spec §1.6)."""
    px = sc.pxmm
    cx, cy = c[0] * px - 0.5, (gh - c[1]) * px - 0.5
    r = d0 / 2 * px
    R = int(math.ceil(1.8 * r)) + 2
    x0, y0 = max(0, int(cx) - R), max(0, int(cy) - R)
    roi = gray[y0:int(cy) + R + 1, x0:int(cx) + R + 1]
    if roi.size == 0:
        return None
    yy, xx = np.mgrid[y0:y0 + roi.shape[0], x0:x0 + roi.shape[1]]
    dist = np.hypot(xx - cx, yy - cy)
    inner, ring = roi[dist <= 0.6 * r], roi[(dist >= 1.3 * r) & (dist <= 1.6 * r)]
    if not len(inner) or not len(ring):
        return None
    mi, mr = float(np.median(inner)), float(np.median(ring))
    thr = (mi + mr) / 2
    bw = (((roi > thr) if mi > mr else (roi < thr)) & (dist <= 1.3 * r)).astype(np.uint8)
    _, lbl = cv2.connectedComponents(bw)
    iy, ix = int(round(cy)) - y0, int(round(cx)) - x0
    if not (0 <= iy < lbl.shape[0] and 0 <= ix < lbl.shape[1]) or lbl[iy, ix] == 0:
        return None
    cnts, _ = cv2.findContours((lbl == lbl[iy, ix]).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c2 = max(cnts, key=cv2.contourArea)
    if len(c2) < 5:
        return None
    (ex, ey), (ma, mb), _ = cv2.fitEllipse(c2)
    d = (ma + mb) / 2 / px
    if not 0.7 * d0 <= d <= 1.3 * d0:
        return None
    return {"c": [round((x0 + ex + 0.5) / px, 3), round(gh - (y0 + ey + 0.5) / px, 3)], "d": round(float(d), 3)}


def _holes(cnts, hier, gray: np.ndarray, gh: float, sc: Scale) -> list[dict]:
    out = []
    for i, c in enumerate(cnts):
        if hier[i][3] < 0:
            continue
        area = cv2.contourArea(c) / sc.work ** 2
        per = cv2.arcLength(c, True) / sc.work
        if per <= 0 or area < math.pi * sc.k ** 2 or 4 * math.pi * area / per ** 2 < 0.85:  # Ø < 2 mm · k oder nicht rund
            continue
        (cx, cy), _ = cv2.minEnclosingCircle(c)
        c_mm = ((cx + 0.5) / sc.work, gh - (cy + 0.5) / sc.work)
        d0 = 2 * math.sqrt(area / math.pi)
        out.append(_refine_hole(c_mm, d0, gray, gh, sc) or
                   {"c": [round(float(c_mm[0]), 3), round(float(c_mm[1]), 3)], "d": round(float(d0), 3)})
    return out


def _try_merge(a: list, b: list, sc: Scale) -> list | None:
    """Kollineare Stuecke zusammenfassen: Winkel < 3°, Abstand < 1 mm, Luecke < 2 mm (Spec §1.7)."""
    ax, ay, bx, by = a
    L = math.hypot(bx - ax, by - ay)
    if L < 1e-9:
        return None
    ux, uy = (bx - ax) / L, (by - ay) / L
    d = abs(math.degrees(math.atan2(uy, ux) - math.atan2(b[3] - b[1], b[2] - b[0]))) % 180
    if min(d, 180 - d) >= 3:
        return None
    for qx, qy in ((b[0], b[1]), (b[2], b[3])):
        if abs((qx - ax) * uy - (qy - ay) * ux) >= 1.0 * sc.k:
            return None
    t = [0.0, L, (b[0] - ax) * ux + (b[1] - ay) * uy, (b[2] - ax) * ux + (b[3] - ay) * uy]
    lo_b, hi_b = sorted(t[2:])
    if lo_b > L + 2 * sc.k or hi_b < -2 * sc.k:
        return None
    lo, hi = min(t), max(t)
    return [ax + ux * lo, ay + uy * lo, ax + ux * hi, ay + uy * hi]


def _merge(segs: list, sc: Scale) -> list:
    segs = [list(s) for s in segs]
    changed = True
    while changed:
        changed = False
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                m = _try_merge(segs[i], segs[j], sc)
                if m:
                    segs[i] = m
                    del segs[j]
                    changed = True
                    break
            if changed:
                break
    return segs


def _seg_len(s) -> float:
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _segments(gray: np.ndarray, mask_full: np.ndarray, gh: float, sc: Scale) -> list:
    """Gerade Innenkanten mit LSD (ohne Canny) innerhalb der um 1,5 mm erodierten Maske (Spec §1.7)."""
    px = sc.pxmm
    k = _odd(3 * sc.k * px)
    inner = cv2.erode(mask_full, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    found = cv2.createLineSegmentDetector().detect(gray)[0]
    if found is None:
        return []
    H, W = gray.shape
    segs = []
    ts = np.linspace(0, 1, 5)
    for row in found.reshape(-1, 4):
        x1, y1, x2, y2 = (float(v) for v in row)
        if math.hypot(x2 - x1, y2 - y1) < 2 * sc.k * px:
            continue
        xs = np.clip(np.rint(x1 + (x2 - x1) * ts).astype(int), 0, W - 1)
        ys = np.clip(np.rint(y1 + (y2 - y1) * ts).astype(int), 0, H - 1)
        if int((inner[ys, xs] > 0).sum()) >= 3:
            segs.append([(x1 + 0.5) / px, gh - (y1 + 0.5) / px, (x2 + 0.5) / px, gh - (y2 + 0.5) / px])
    segs = sorted(segs, key=_seg_len, reverse=True)[:300]
    segs = [s for s in _merge(segs, sc) if _seg_len(s) >= MIN_SEG_MM * sc.k]
    return sorted(segs, key=_seg_len, reverse=True)[:MAX_SEGMENTS]


def detect(rect: np.ndarray, fmt: str, hints: dict | None = None) -> dict:
    """Umrisse, Bohrungen und Kanten-Kandidaten (Spec §1). Leere Listen, wenn kein Objekt gefunden wurde.

    hints: {"transparent": 0|1|2, "light": bool} (Materialhinweise des Nutzers, siehe _mask). Zusaetzlich
    zurueck: contrast (mittlerer Farbabstand im Objekt, 0–100; None ohne Umriss) und die verwendeten hints."""
    hints = hints or {}
    sc = scale_for(fmt)
    # GrabCut zieht aus cv::theRNG – ohne Seed haengt das Ergebnis von frueheren Aufrufen ab (Ruling R1)
    cv2.setRNGSeed(12345)
    gh = float(spec(fmt)["grid_mm"][1])
    mask, color, diff = _mask(rect, fmt, hints, sc)
    gray = cv2.morphologyEx(cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outlines, holes = [], []
    if cnts:
        hier = hier[0]
        for i, c in enumerate(cnts):
            if hier[i][3] >= 0:
                continue
            area = cv2.contourArea(c) / sc.work ** 2
            if area < MIN_AREA_MM2 * sc.k ** 2:
                continue
            eps = APPROX_MM * sc.k * sc.work
            ap = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
            while len(ap) > MAX_VERTS and eps < 8 * sc.k * sc.work:  # sehr unruhige Umrisse vereinfachen
                eps *= 1.5
                ap = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
            if not 3 <= len(ap) <= MAX_VERTS:
                continue
            coarse = [[(float(x) + 0.5) / sc.work, gh - (float(y) + 0.5) / sc.work] for x, y in ap]
            outlines.append({"polygon": _refine(coarse, gx, gy, gh, sc), "area": round(float(area), 1)})
        hc, hh = cv2.findContours(color, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        if hc:
            # Raster-Weg: das Rasterkriterium fuellt Bohrungen in der Maske; ohne Raster bleiben sie offen
            member = mask if sc.field == "grid" else _fill_small(mask, sc.hole_max, sc)
            inside = [h for h in _holes(hc, hh[0], gray, gh, sc)
                      if member[min(member.shape[0] - 1, int((gh - h["c"][1]) * sc.work)),
                                min(member.shape[1] - 1, int(h["c"][0] * sc.work))] > 0]
            holes = inside
    outlines.sort(key=lambda o: -o["area"])
    del outlines[MAX_OUTLINES:]
    segs = []
    if outlines:
        full = cv2.resize(mask, (rect.shape[1], rect.shape[0]), interpolation=cv2.INTER_NEAREST)
        segs = _segments(gray, full, gh, sc)
    segments, n = [], 0
    for o in outlines:
        P = o["polygon"]
        for i in range(len(P)):
            n += 1
            segments.append({"id": f"K{n}", "a": P[i], "b": P[(i + 1) % len(P)], "kind": "outline"})
    for x1, y1, x2, y2 in segs:
        n += 1
        segments.append({"id": f"K{n}", "a": [round(x1, 3), round(y1, 3)], "b": [round(x2, 3), round(y2, 3)], "kind": "inner"})
    # Kontrast: Farbabstand von uint8 (0–255) auf 0–100 umgerechnet
    contrast = round(float(np.mean(diff[mask > 0])) * 100 / 255, 1) if outlines else None
    return {"outlines": outlines, "holes": holes if outlines else [], "segments": segments, "px_per_mm": sc.pxmm,
            "edge_scale": sc.k, "contrast": contrast, "hints": hints}


def draw_candidates(rect: np.ndarray, res: dict) -> np.ndarray:
    """Draufsicht mit eingezeichneten, nummerierten Kandidaten (Bildvorlage fuer die KI-Zuordnung)."""
    img = rect.copy()
    px = res["px_per_mm"]
    gh = img.shape[0] / px
    colors = [(178, 111, 31), (12, 85, 194), (46, 125, 79), (150, 40, 160)]

    def P(q):
        return int(round(q[0] * px)), int(round((gh - q[1]) * px))
    for i, s in enumerate(res["segments"]):
        a, b, col = P(s["a"]), P(s["b"]), colors[i % len(colors)]
        cv2.line(img, a, b, col, 4, cv2.LINE_AA)
        mid = ((a[0] + b[0]) // 2 + 6, (a[1] + b[1]) // 2 - 6)
        cv2.putText(img, s["id"], mid, cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 5, cv2.LINE_AA)
        cv2.putText(img, s["id"], mid, cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, 2, cv2.LINE_AA)
    return img
