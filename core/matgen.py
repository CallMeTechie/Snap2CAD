"""Messunterlage mit mm-Raster, ArUco-Markern, Kontrollmass, Hoehenlehre und Anleitung."""
import io
import json
import sys
import threading

import cv2
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A3, A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph, Spacer, Table, TableStyle

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

C05 = HexColor("#E2E8EE")  # 0,5 mm (nur Mini)
C1 = HexColor("#D3DCE5")   # 1 mm
C5 = HexColor("#9FB0C1")   # 5 mm
C10 = HexColor("#5F7387")  # 10 mm
INK = HexColor("#1B2733")
MUTED = HexColor("#5B6875")
ACCENT = HexColor("#1F6FB2")


def marker(c, mid, cx, cy, s):
    """ArUco-Marker als Vektor zeichnen, Mittelpunkt (cx, cy) in mm, Kantenlaenge s in mm."""
    img = cv2.aruco.generateImageMarker(DICT, mid, 6)
    cell = s / 6.0
    x0, y0 = cx - s / 2, cy - s / 2
    c.setFillColor(black)
    for r in range(6):
        for col in range(6):
            if img[r, col] == 0:
                c.rect((x0 + col * cell) * mm, (y0 + (5 - r) * cell) * mm,
                       cell * mm + 0.05, cell * mm + 0.05, stroke=0, fill=1)


def white_box(c, cx, cy, s, pad):
    c.setFillColor(white)
    c.rect((cx - s / 2 - pad) * mm, (cy - s / 2 - pad) * mm,
           (s + 2 * pad) * mm, (s + 2 * pad) * mm, stroke=0, fill=1)


def fmt(v):
    return f"{v:g}".replace(".", ",")


SHEET_IDS = (0, 1, 2, 3, 4, 5, 6, 7)
MINI_IDS = (20, 21, 22, 23, 24, 25, 26, 27)
POS_NAMES = ("unten links", "unten rechts", "oben rechts", "oben links",
             "unten Mitte", "rechts Mitte", "oben Mitte", "links Mitte")


def _grid(c, gx, gy, gw, gh, levels):
    """Raster mit mehreren Linienstaerken. levels aufsteigend: (Teilung mm, Farbe, Linienbreite pt).
    Jede Linie bekommt die Staerke der groebsten Teilung, auf der sie liegt."""
    fine = levels[0][0]

    def level(v):
        return max(k for k, (st, _, _) in enumerate(levels) if abs(v / st - round(v / st)) < 1e-6)
    for k, (_, col, lw) in enumerate(levels):
        c.setStrokeColor(col)
        c.setLineWidth(lw)
        for i in range(int(round(gw / fine)) + 1):
            v = i * fine
            if level(v) == k and 0 < v < gw or (k == len(levels) - 1 and v in (0, gw)):
                c.line((gx + v) * mm, gy * mm, (gx + v) * mm, (gy + gh) * mm)
        for j in range(int(round(gh / fine)) + 1):
            v = j * fine
            if level(v) == k and 0 < v < gh or (k == len(levels) - 1 and v in (0, gh)):
                c.line(gx * mm, (gy + v) * mm, (gx + gw) * mm, (gy + v) * mm)


def _hits(x0, y0, x1, y1, avoid):
    return any(x0 < b[2] and b[0] < x1 and y0 < b[3] and b[1] < y1 for b in avoid or ())


def _axis_labels(c, gx, gy, gw, gh, every, size, box, avoid=None):
    """Achsbeschriftung (unten + links) auf weissem Hinterlegungsfeld. box = (Breite x, Hoehe, Breite y) in mm.
    avoid: Rechtecke (x0, y0, x1, y1) relativ zum Rasterursprung, in denen keine Beschriftung stehen soll."""
    bw, bh, bwy = box
    c.setFont("Helvetica", size)
    for i in range(every, gw, every):
        if _hits(i - bw / 2, bh / 4, i + bw / 2, bh / 4 + bh, avoid):
            continue
        c.setFillColor(white)
        c.rect((gx + i - bw / 2) * mm, (gy + bh / 4) * mm, bw * mm, bh * mm, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.drawCentredString((gx + i) * mm, (gy + bh / 4 + bh * 5 / 24) * mm, str(i))
    for j in range(every, gh, every):
        if _hits(bh / 4, j - bh / 2, bh / 4 + bwy, j + bh / 2, avoid):
            continue
        c.setFillColor(white)
        c.rect((gx + bh / 4) * mm, (gy + j - bh / 2) * mm, bwy * mm, bh * mm, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.drawString((gx + bh * 0.375) * mm, (gy + j - bh * 7 / 24) * mm, str(j))


def _center_cross(c, cx, cy, arm, r, lw):
    c.setStrokeColor(ACCENT)
    c.setLineWidth(lw)
    c.line((cx - arm) * mm, cy * mm, (cx + arm) * mm, cy * mm)
    c.line(cx * mm, (cy - arm) * mm, cx * mm, (cy + arm) * mm)
    c.circle(cx * mm, cy * mm, r * mm, stroke=1, fill=0)


def _frame(c, gx, gy, gw, gh, lw):
    c.setStrokeColor(INK)
    c.setLineWidth(lw)
    c.rect(gx * mm, gy * mm, gw * mm, gh * mm, stroke=1, fill=0)


def _marker_places(gw, gh, s, q):
    k = q + s / 2
    return [(k, k), (gw - k, k), (gw - k, gh - k), (k, gh - k),
            (gw / 2, k), (gw - k, gh / 2), (gw / 2, gh - k), (k, gh / 2)]


def _markers(c, gx, gy, gw, gh, s, q, ids, font, label_off):
    """8 Marker: Ecken (unten links, gegen den Uhrzeigersinn) und Kantenmitten. Koordinaten relativ zum
    Rasterursprung unten links. label_off = (Abstand unten, Abstand oben) der Beschriftung."""
    pos = dict(zip(ids, _marker_places(gw, gh, s, q), strict=True))
    for mid, (px, py) in pos.items():
        white_box(c, gx + px, gy + py, s, q - 0.5)
        marker(c, mid, gx + px, gy + py, s)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", font)
        # Beschriftung ausserhalb der Ruhezone, Richtung Rastermitte
        ty = gy + py + (s / 2 + q + label_off[0] if py < gh / 2 else -(s / 2 + q + label_off[1]))
        c.drawCentredString((gx + px) * mm, ty * mm, f"ID {mid}")
    return pos


def _control(c, bx, by, fx, fw, gh):
    """Kontrollmass 100 mm ab (bx, by) und Feld zum Eintragen ab fx mit Breite fw (alles mm)."""
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.line(bx * mm, by * mm, (bx + 100) * mm, by * mm)
    for i in range(0, 101):
        ln = 4 if i % 10 == 0 else (2.6 if i % 5 == 0 else 1.6)
        c.setLineWidth(0.4 if i % 10 == 0 else 0.25)
        c.line((bx + i) * mm, by * mm, (bx + i) * mm, (by + ln) * mm)
    c.setFont("Helvetica", 5.5)
    c.setFillColor(INK)
    for i in range(0, 101, 10):
        c.drawCentredString((bx + i) * mm, (by + 4.8) * mm, str(i))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(bx * mm, (by - 4) * mm, "Kontrollmaß 100 mm – mit Lineal prüfen")

    # Feld zum Eintragen
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    c.rect(fx * mm, (by - 5) * mm, fw * mm, 12 * mm, stroke=1, fill=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(MUTED)
    c.drawString((fx + 2) * mm, (by + 4) * mm, "Gemessen (0–100):")
    c.drawString((fx + 2) * mm, (by - 3.2) * mm, "Gemessen Raster 0–" + str(gh) + " vertikal:")
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.3)
    c.line((fx + 24) * mm, (by + 3.6) * mm, (fx + fw - 9) * mm, (by + 3.6) * mm)
    c.line((fx + 41) * mm, (by - 3.6) * mm, (fx + fw - 9) * mm, (by - 3.6) * mm)
    c.drawString((fx + fw - 7.5) * mm, (by + 4) * mm, "mm")
    c.drawString((fx + fw - 7.5) * mm, (by - 3.2) * mm, "mm")


def mat_page(c, W, H, label, s):
    m = 10.0
    header, footer = 14.0, 26.0
    gw = int((W - 2 * m) // 10) * 10
    gh = int((H - 2 * m - header - footer) // 10) * 10
    gx = (W - gw) / 2
    gy = m + footer + ((H - 2 * m - header - footer) - gh) / 2

    _grid(c, gx, gy, gw, gh, ((1, C1, 0.15), (5, C5, 0.3), (10, C10, 0.5)))
    _axis_labels(c, gx, gy, gw, gh, 10, 5.5, (4.4, 2.4, 4.6))
    _center_cross(c, gx + gw / 2, gy + gh / 2, 6, 3, 0.6)
    _frame(c, gx, gy, gw, gh, 0.9)
    pos = _markers(c, gx, gy, gw, gh, s, 3.0, SHEET_IDS, 5, (1.0, 2.6))

    # Kopfzeile
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(gx * mm, (H - m - 6) * mm, _title(f"Messunterlage {label}"))
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(gx * mm, (H - m - 10.5) * mm,
                 f"Raster 1 mm  ·  Feld {gw} × {gh} mm  ·  Ursprung 0/0 unten links  ·  Version 1")
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString((gx + gw) * mm, (H - m - 6) * mm, "Drucken mit 100 % / Tatsächliche Größe")
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawRightString((gx + gw) * mm, (H - m - 10.5) * mm, "nicht „An Seite anpassen“ · Papier plan auflegen")

    # Fusszeile: Kontrollmass 100 mm
    _control(c, gx, m + 13, gx + 112, gw - 112, gh)

    # Selbstbeschreibende Spezifikation
    spec = "  ".join(f"ID{i} ({fmt(px)}|{fmt(py)})" for i, (px, py) in pos.items())
    c.setFont("Helvetica", 4.6)
    c.setFillColor(MUTED)
    c.drawString(gx * mm, (m - 0.5) * mm,
                 f"ArUco DICT_4X4_50 · Kante {fmt(s)} mm · Mittelpunkte in mm ab Rasterursprung: {spec}")
    return {"grid_mm": [gw, gh], "marker_size_mm": s, "centers_mm": {str(k): v for k, v in pos.items()},
            "grid_origin_on_page_mm": [gx, gy]}


def strip(c, x, y_fold, vlen, foot, ids, name, bottom_id=None, s=18.0, w=45.0):
    # Hilfslinien
    c.setStrokeColor(C1)
    c.setLineWidth(0.3)
    for j in range(10, int(vlen) + 1, 10):
        c.line(x * mm, (y_fold + j) * mm, (x + w) * mm, (y_fold + j) * mm)
    # Teilungen links und rechts
    c.setStrokeColor(INK)
    for j in range(0, int(vlen) + 1):
        ln = 6 if j % 10 == 0 else (3.5 if j % 5 == 0 else 2)
        c.setLineWidth(0.4 if j % 10 == 0 else 0.25)
        c.line(x * mm, (y_fold + j) * mm, (x + ln) * mm, (y_fold + j) * mm)
        c.line((x + w) * mm, (y_fold + j) * mm, (x + w - ln) * mm, (y_fold + j) * mm)
    c.setFont("Helvetica", 6)
    c.setFillColor(INK)
    for j in range(0, int(vlen), 10):
        c.drawString((x + 7) * mm, (y_fold + j - 0.8) * mm, str(j))
    # Marker oben
    centers = {}
    cx = x + w / 2
    for n, mid in enumerate(ids):
        cy = y_fold + vlen - 3 - s / 2 - n * (s + 10)
        white_box(c, cx, cy, s, 2.5)
        marker(c, mid, cx, cy, s)
        centers[mid] = cy - y_fold
        c.setFont("Helvetica", 5)
        c.setFillColor(MUTED)
        c.drawCentredString(cx * mm, (cy - s / 2 - 5.3) * mm, f"ID {mid} · {fmt(cy - y_fold)} mm")
    # Marker unten: stabilisiert die Entzerrung ueber die ganze Hoehe
    if bottom_id is not None:
        cy = y_fold + 30.0
        white_box(c, cx, cy, s, 2.5)
        marker(c, bottom_id, cx, cy, s)
        centers[bottom_id] = 30.0
        c.setFont("Helvetica", 5)
        c.setFillColor(MUTED)
        c.drawCentredString(cx * mm, (cy + s / 2 + 3.4) * mm, f"ID {bottom_id} · 30 mm")
    # Schnittkontur
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.rect(x * mm, (y_fold - foot) * mm, w * mm, (vlen + foot) * mm, stroke=1, fill=0)
    # Falzlinie
    c.setDash(3, 2)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.7)
    c.line((x - 4) * mm, y_fold * mm, (x + w + 4) * mm, y_fold * mm)
    c.setDash()
    # Fuss
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString((x + w / 2) * mm, (y_fold - 5) * mm, "Falz – 90° nach hinten")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString((x + w / 2) * mm, (y_fold - 14) * mm, f"Höhenlehre {name}")
    c.setFont("Helvetica", 6)
    c.setFillColor(MUTED)
    for n, t in enumerate(["Fuß flach auf die Unterlage,", "mit Klebeband fixieren.",
                           "Skala 0 = Tischebene."]):
        c.drawCentredString((x + w / 2) * mm, (y_fold - 20 - n * 3.2) * mm, t)
    return centers


def strip_page(c, W, H, label):
    m = 10.0
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(m * mm, (H - m - 6) * mm, _title(f"Höhenlehre zum Aufstellen ({label})"))
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (H - m - 10.5) * mm,
                 "Ausschneiden, auf Karton kleben, an der blauen Linie falzen und direkt neben das Objekt "
                 "stellen – alle drei Marker sichtbar.")
    foot = 36.0
    vlen = int((H - 2 * m - 18 - foot) // 10) * 10
    y_fold = m + foot + 2
    gap = 20.0
    w = 45.0
    total = 2 * w + gap
    x0 = (W - total) / 2
    a = strip(c, x0, y_fold, vlen, foot, (10, 11), "A", bottom_id=14)
    b = strip(c, x0 + w + gap, y_fold, vlen, foot, (12, 13), "B", bottom_id=15)
    c.setFont("Helvetica", 4.6)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (m - 0.5) * mm,
                 "ArUco DICT_4X4_50 · Kante 18 mm · Markermitten über Falz: " +
                 "  ".join(f"ID{k} {fmt(v)} mm" for k, v in {**a, **b}.items()) +
                 " · Markermitte horizontal = Streifenmitte")
    return {"vlen_mm": vlen, "centers_above_fold_mm": {**a, **b}}


def guide_page(c, W, H, label, spec):
    m = 18 * mm
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK, spaceAfter=4)
    st_s = ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=ACCENT,
                          spaceBefore=9, spaceAfter=3)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=12.6, textColor=INK, spaceAfter=3)
    st_n = ParagraphStyle("n", parent=st_p, leftIndent=12, bulletIndent=0)
    st_small = ParagraphStyle("sm", parent=st_p, fontSize=7.5, leading=10, textColor=MUTED)

    def b(t):
        return Paragraph(t, st_n, bulletText="•")

    gw, gh = spec["grid_mm"]
    story = _mini_story(spec) if spec.get("kind") == "mini" else [
        Paragraph("Anleitung: Objekt fotografieren und vermessen lassen", st_h),
        Paragraph(f"Für die Messunterlage {label} ({gw} × {gh} mm Raster). Aus den Fotos werden die "
                  "Marker erkannt, die Perspektive auf die Tischebene entzerrt und die Kanten in mm "
                  "ausgemessen.", st_p),

        Paragraph("1  Drucken und prüfen", st_s),
        b("Drucken mit <b>100 % / Tatsächliche Größe</b>, nicht „An Seite anpassen“. Mattes Papier, keine Glanzfolie."),
        b("Kontrollmaß 0–100 mit einem Stahllineal nachmessen und den Wert ins Feld eintragen. "
          "Steht er auf dem Foto, wird eine Druckabweichung automatisch herausgerechnet."),
        b("Unterlage plan auf einen festen Tisch legen, Ecken mit Klebeband fixieren. Wellen im Papier verfälschen das Maß."),

        Paragraph("2  Objekt platzieren", st_s),
        b("Objekt etwa mittig auf das Kreuz legen, Kanten möglichst parallel zum Raster."),
        b("Alle 8 Marker frei lassen. Mindestens 4 müssen vollständig sichtbar sein, sonst ist keine Entzerrung möglich."),
        b("Nichts über die weißen Felder um die Marker legen, auch keine Schatten."),

        Paragraph("3  Fotos", st_s),
        b("<b>Draufsicht (Pflicht):</b> Kamera möglichst senkrecht über der Mitte, 50–70 cm Abstand, "
          "2×- oder 3×-Zoom statt Weitwinkel. Die ganze Unterlage muss im Bild sein."),
        b("<b>Höhe, Variante A (am genauesten):</b> Objekt auf die Seite bzw. auf die Stirnseite legen und je "
          "eine weitere Draufsicht machen. So wird jede Abmessung einmal flach auf der Unterlage gemessen."),
        b("<b>Höhe, Variante B:</b> Höhenlehre (Seite 2) aufstellen, direkt an das Objekt. Kamera auf "
          "Höhe der Objektmitte, waagerecht und frontal, Lehre und Objekt scharf im Bild."),
        b("<b>Optional:</b> eine 45°-Schrägansicht, damit klar ist, welche Kante welche ist."),
        b("Licht diffus (Tageslicht, Deckenlicht), kein Blitz, keine harten Schatten an den Messkanten."),

        Paragraph("4  Senden", st_s),
        b("Originalfoto in voller Auflösung schicken – nicht über Messenger komprimiert."),
        b("Dazu sagen, welche Maße gebraucht werden (z. B. „Außenmaß Flansch, Lochabstand, Höhe bis Schulter“)."),

        Paragraph("Genauigkeit – realistisch", st_s),
        Paragraph("Flache Teile und Kanten, die auf der Unterlage aufliegen: etwa ±0,5 mm. Bei höheren "
                  "Objekten entsteht Parallaxe: Alles, was über der Tischebene liegt, ist näher an der Kamera "
                  "und erscheint größer. Faustregel: Fehler ≈ Maß × Objekthöhe ÷ Kameraabstand. "
                  "Beispiel: 100 mm breite Oberkante, 50 mm hoch, 500 mm Abstand → Oberkante wirkt ca. "
                  "10 mm zu breit. Deshalb an der Auflagekante messen, mit Zoom aus größerem Abstand "
                  "fotografieren oder das Objekt kippen (Variante A).", st_p),
        Paragraph("Für Passmaße mit Toleranzen unter 0,2 mm ersetzt die Unterlage keinen Messschieber.", st_p),
        Spacer(1, 6),
    ]
    rows = [["Marker", "Position", "Mitte X (mm)", "Mitte Y (mm)"]]
    for n, (k, (px, py)) in enumerate(spec["centers_mm"].items()):
        rows.append([f"ID {k}", POS_NAMES[n], fmt(px), fmt(py)])
    t = Table(rows, colWidths=[22 * mm, 34 * mm, 28 * mm, 28 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, C1),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    story += [Paragraph("Marker-Referenz (ArUco DICT_4X4_50, Kante "
                        f"{fmt(spec['marker_size_mm'])} mm, Ursprung = Rasterecke unten links)", st_small),
              t]
    Frame(m, m, W * mm - 2 * m, H * mm - 2 * m, showBoundary=0).addFromList(story, c)


# ------------------------------------------------------------------ Mini: kleine Teile (ca. 1–40 mm)

MINI_GRID = (80, 60)       # Rasterflaeche in mm (4:3 wie ein Handyfoto)
MINI_MARKER = 7.0          # Markerkante in mm
MINI_Q = 2.0               # Rand vom Raster zum Marker (Ruhezone = MINI_Q - 0,5 mm)
MINI_GAUGE = {"A": (30, 31, 34), "B": (32, 33, 35)}
MINI_GAUGE_MARKER = 6.0
MINI_GAUGE_VLEN = 50
MINI_GAUGE_W = 24.0


def _para(text, size=8, lead=11, color=INK, bold=False, space=2, indent=0, bullet=None):
    st = ParagraphStyle("x", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size, leading=lead,
                        textColor=color, spaceAfter=space, leftIndent=indent, bulletIndent=0)
    return Paragraph(text, st, bulletText=bullet)


def mini_page(c, W, H, label):
    """Seite 1 im Format Mini: Messkarte zum Ausschneiden, Kontrollmass 100 mm, Kurzanleitung."""
    m = 10.0
    gw, gh = MINI_GRID
    s, q = MINI_MARKER, MINI_Q

    # Kopfzeile
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(m * mm, (H - m - 6) * mm, _title(f"Messunterlage {label} – für kleine Teile"))
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (H - m - 10.5) * mm,
                 f"Raster 0,5 mm  ·  Feld {gw} × {gh} mm  ·  Teile von ca. 1 bis 40 mm  ·  Version 1")
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString((W - m) * mm, (H - m - 6) * mm, "Drucken mit 100 % / Tatsächliche Größe")
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawRightString((W - m) * mm, (H - m - 10.5) * mm, "Karte ausschneiden und auf festen Karton kleben")

    # Karte: Raster mit Rand, unten Platz fuer die Kennung
    cw, ch = gw + 10, gh + 14
    cx0, cy1 = (W - cw) / 2, H - m - 22
    cy0 = cy1 - ch
    gx, gy = cx0 + 5, cy0 + 9
    # Schnittlinie mit Eckmarken ausserhalb
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.4)
    c.setDash(2, 1.5)
    c.rect(cx0 * mm, cy0 * mm, cw * mm, ch * mm, stroke=1, fill=0)
    c.setDash()
    c.setLineWidth(0.3)
    for x, y, dx, dy in ((cx0, cy0, -1, -1), (cx0 + cw, cy0, 1, -1), (cx0 + cw, cy1, 1, 1), (cx0, cy1, -1, 1)):
        c.line((x + dx * 1.5) * mm, y * mm, (x + dx * 6) * mm, y * mm)
        c.line(x * mm, (y + dy * 1.5) * mm, x * mm, (y + dy * 6) * mm)
    c.setFont("Helvetica", 5.5)
    c.setFillColor(MUTED)
    c.drawString((cx0 + cw + 3) * mm, (cy1 - 3) * mm, "an der")
    c.drawString((cx0 + cw + 3) * mm, (cy1 - 5.4) * mm, "gestrichelten")
    c.drawString((cx0 + cw + 3) * mm, (cy1 - 7.8) * mm, "Linie")
    c.drawString((cx0 + cw + 3) * mm, (cy1 - 10.2) * mm, "ausschneiden")

    avoid = [(px - s / 2 - q + 0.5, py - s / 2 - q + 0.5, px + s / 2 + q - 0.5, py + s / 2 + q - 0.5)
             for px, py in _marker_places(gw, gh, s, q)]
    _grid(c, gx, gy, gw, gh, ((0.5, C05, 0.12), (1, C1, 0.18), (5, C5, 0.2), (10, C10, 0.25)))
    _axis_labels(c, gx, gy, gw, gh, 10, 4.2, (3.4, 1.9, 3.2), avoid)
    _center_cross(c, gx + gw / 2, gy + gh / 2, 3, 1.5, 0.4)
    _frame(c, gx, gy, gw, gh, 0.6)
    pos = _markers(c, gx, gy, gw, gh, s, q, MINI_IDS, 3.6, (0.6, 1.9))
    c.setFont("Helvetica-Bold", 5.5)
    c.setFillColor(INK)
    c.drawString(gx * mm, (cy0 + 3.6) * mm, "Snap2CAD Mini")
    c.setFont("Helvetica", 4.4)
    c.setFillColor(MUTED)
    c.drawRightString((gx + gw) * mm, (cy0 + 3.6) * mm,
                      f"Raster 0,5 mm · {gw} × {gh} mm · ArUco 4X4_50 · ID {MINI_IDS[0]}–{MINI_IDS[-1]} · Kante {fmt(s)} mm")

    # Kontrollmass (gilt fuer den ganzen Ausdruck, also auch fuer die Karte)
    by = cy0 - 16
    bx = (W - 182) / 2
    _control(c, bx, by, bx + 112, 70, gh)

    # Kurzanleitung
    b = "•"
    story = [
        _para("So geht’s", 10.5, 14, ACCENT, True, 3),
        _para("<b>Ausdrucken</b> mit 100 %, Kontrollmaß mit Stahllineal nachmessen und den Wert eintragen "
              "(in der App unter „Fotos prüfen“ → „Kontrollmaß vom Ausdruck“).", bullet=b, indent=10),
        _para("<b>Karte ausschneiden</b> und vollflächig auf festen, planen Karton oder ein Stück Kunststoff kleben. "
              "Bei so kleinen Maßen zählt jede Welle im Papier.", bullet=b, indent=10),
        _para("<b>Teil mittig</b> auf das Kreuz legen. Die 8 Marker und ihre weißen Felder frei lassen, "
              "mindestens 4 müssen ganz im Bild sein.", bullet=b, indent=10),
        _para("<b>Fotografieren:</b> Hauptkamera oder Tele mit 2×/3×-Zoom aus 20–30 cm, senkrecht von oben, die "
              "ganze Karte formatfüllend im Bild. Die automatische Makro-Funktion (Ultraweitwinkel) ausschalten – "
              "ihre Verzeichnung lässt sich mit den Markern nicht herausrechnen.", bullet=b, indent=10),
        _para("<b>Licht</b> diffus und von der Seite, kein Blitz. Gegen den Hintergrund helle oder glänzende Teile "
              "notfalls auf ein Stück dunkles Papier über der Rastermitte legen – Marker frei lassen.",
              bullet=b, indent=10),
        _para("<b>Höhe:</b> Teil auf die Seite legen und eine zweite Draufsicht machen, oder die Mini-Höhenlehre "
              "(Seite 2) daneben stellen.", bullet=b, indent=10),
        _para("Genauigkeit", 10.5, 14, ACCENT, True, 3),
        _para("Flache Teile, die auf der Karte aufliegen: etwa ±0,1 mm. Was über der Karte liegt, erscheint "
              "größer (Parallaxe): Fehler ≈ Maß × Höhe ÷ Kameraabstand, z. B. 20 mm breite Oberkante, 5 mm hoch, "
              "250 mm Abstand → 0,4 mm zu breit. Deshalb an der Auflagekante messen oder aus größerem Abstand mit "
              "Zoom fotografieren. Bei Passungen unter 0,05 mm Messschieber oder Bügelmessschraube verwenden.",
              8, 11, INK),
    ]
    Frame(m * mm, (m + 4) * mm, (W - 2 * m) * mm, (by - 9 - m - 4) * mm, showBoundary=0,
          leftPadding=0, rightPadding=0).addFromList(story, c)

    spec = "  ".join(f"ID{i} ({fmt(px)}|{fmt(py)})" for i, (px, py) in pos.items())
    c.setFont("Helvetica", 4.6)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (m - 0.5) * mm,
                 f"ArUco DICT_4X4_50 · Kante {fmt(s)} mm · Mittelpunkte in mm ab Rasterursprung: {spec}")
    return {"grid_mm": [gw, gh], "marker_size_mm": s, "centers_mm": {str(k): v for k, v in pos.items()},
            "grid_origin_on_page_mm": [gx, gy]}


def mini_strip(c, x, y_fold, ids, bottom_id, name):
    """Kleine Hoehenlehre: Teilung 0,5 mm, Beschriftung alle 5 mm, zwei Marker oben, einer unten."""
    s, w, vlen, foot = MINI_GAUGE_MARKER, MINI_GAUGE_W, MINI_GAUGE_VLEN, 24.0
    c.setStrokeColor(C1)
    c.setLineWidth(0.2)
    for j in range(5, vlen + 1, 5):
        c.line(x * mm, (y_fold + j) * mm, (x + w) * mm, (y_fold + j) * mm)
    c.setStrokeColor(INK)
    for k in range(0, 2 * vlen + 1):
        j = k / 2
        ln = 4 if j % 5 == 0 else (2.4 if j == int(j) else 1.3)
        c.setLineWidth(0.35 if j % 5 == 0 else 0.18)
        c.line(x * mm, (y_fold + j) * mm, (x + ln) * mm, (y_fold + j) * mm)
        c.line((x + w) * mm, (y_fold + j) * mm, (x + w - ln) * mm, (y_fold + j) * mm)
    c.setFont("Helvetica", 4.2)
    c.setFillColor(INK)
    for j in range(0, vlen, 5):
        c.drawString((x + 4.6) * mm, (y_fold + j - 0.6) * mm, str(j))
    centers = {}
    cx = x + w / 2 + 1.5
    for n, mid in enumerate(ids):
        cy = y_fold + vlen - 1.5 - s / 2 - n * (s + 3)
        white_box(c, cx, cy, s, 1.2)
        marker(c, mid, cx, cy, s)
        centers[mid] = cy - y_fold
    cy = y_fold + 8.0
    white_box(c, cx, cy, s, 1.2)
    marker(c, bottom_id, cx, cy, s)
    centers[bottom_id] = 8.0
    c.setStrokeColor(INK)
    c.setLineWidth(0.4)
    c.rect(x * mm, (y_fold - foot) * mm, w * mm, (vlen + foot) * mm, stroke=1, fill=0)
    c.setDash(2, 1.5)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.6)
    c.line((x - 3) * mm, y_fold * mm, (x + w + 3) * mm, y_fold * mm)
    c.setDash()
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 5)
    c.drawCentredString((x + w / 2) * mm, (y_fold - 3.8) * mm, "Falz – 90° nach hinten")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString((x + w / 2) * mm, (y_fold - 9.5) * mm, f"Mini-Lehre {name}")
    c.setFont("Helvetica", 4.6)
    c.setFillColor(MUTED)
    for n, t in enumerate(["Fuß flach auf die Karte,", "mit Klebeband fixieren.", "0 = Auflageebene"]):
        c.drawCentredString((x + w / 2) * mm, (y_fold - 14 - n * 2.6) * mm, t)
    return centers


def mini_strip_page(c, W, H, label):
    m = 10.0
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(m * mm, (H - m - 6) * mm, _title(f"Höhenlehre zum Aufstellen ({label})"))
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (H - m - 10.5) * mm,
                 "Ausschneiden, auf dünnen Karton kleben, an der blauen Linie falzen und direkt neben das Teil "
                 "stellen – alle drei Marker sichtbar.")
    y_fold = H - m - 22 - MINI_GAUGE_VLEN
    gap = 16.0
    x0 = (W - 2 * MINI_GAUGE_W - gap) / 2
    a = mini_strip(c, x0, y_fold, MINI_GAUGE["A"][:2], MINI_GAUGE["A"][2], "A")
    b = mini_strip(c, x0 + MINI_GAUGE_W + gap, y_fold, MINI_GAUGE["B"][:2], MINI_GAUGE["B"][2], "B")
    story = [
        _para("Wann die Höhenlehre?", 10.5, 14, ACCENT, True, 3),
        _para("Genauer ist fast immer, das Teil auf die Seite zu legen und eine zweite Draufsicht auf der "
              "Mini-Karte zu machen. Die Lehre hilft bei Teilen, die nicht kippen dürfen oder rund sind.",
              bullet="•", indent=10),
        _para("Kamera auf Höhe der Teilmitte, waagerecht und frontal, Lehre und Teil gleich weit entfernt und "
              "scharf. Zwei Lehren (A und B) erlauben Aufnahmen von zwei Seiten, ohne umzustellen.",
              bullet="•", indent=10),
    ]
    Frame(m * mm, (m + 4) * mm, (W - 2 * m) * mm, (y_fold - 30 - m - 4) * mm, showBoundary=0,
          leftPadding=0, rightPadding=0).addFromList(story, c)
    c.setFont("Helvetica", 4.6)
    c.setFillColor(MUTED)
    c.drawString(m * mm, (m - 0.5) * mm,
                 f"ArUco DICT_4X4_50 · Kante {fmt(MINI_GAUGE_MARKER)} mm · Markermitten über Falz: " +
                 "  ".join(f"ID{k} {fmt(v)} mm" for k, v in {**a, **b}.items()) +
                 " · Markermitte horizontal = Streifenmitte + 1,5 mm")
    return {"vlen_mm": MINI_GAUGE_VLEN, "centers_above_fold_mm": {**a, **b}}


def _mini_story(spec):
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK, spaceAfter=4)
    st_s = ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=ACCENT,
                          spaceBefore=9, spaceAfter=3)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=12.6, textColor=INK, spaceAfter=3)
    st_n = ParagraphStyle("n", parent=st_p, leftIndent=12, bulletIndent=0)

    def b(t):
        return Paragraph(t, st_n, bulletText="•")
    gw, gh = spec["grid_mm"]
    return [
        Paragraph("Anleitung: kleine Teile fotografieren und vermessen", st_h),
        Paragraph(f"Für die Messunterlage Mini ({gw} × {gh} mm, Raster 0,5 mm) – Schrauben, Federn, Clips, "
                  "Zahnräder, Platinenteile von etwa 1 mm bis 40 mm. Die Marker liegen dicht am Teil, damit das "
                  "Foto aus der Nähe gemacht werden kann und jeder Millimeter viele Bildpunkte bekommt.", st_p),

        Paragraph("1  Vorbereiten", st_s),
        b("Mit <b>100 % / Tatsächlicher Größe</b> drucken, möglichst Laserdrucker, mattes Papier."),
        b("Kontrollmaß 0–100 auf dem Ausdruck mit einem Stahllineal nachmessen. Den Wert in der App unter "
          "„Fotos prüfen“ eintragen – die Abweichung des Druckers wird dann herausgerechnet."),
        b("Karte ausschneiden und vollflächig auf Karton, Kunststoff oder eine Fliese kleben. Plan ist hier "
          "wichtiger als beim großen Blatt: 0,2 mm Wölbung sind bei einem 5-mm-Teil schon 4 %."),

        Paragraph("2  Teil auflegen", st_s),
        b("Teil mittig auf das Kreuz, Kanten parallel zum Raster. Kleine Teile rollen gern – ein Krümel "
          "Knetmasse unter dem Teil hilft, solange er nicht übersteht."),
        b("Die 8 Marker und ihre weißen Felder frei lassen, auch von Pinzette, Fingern und Schatten."),
        b("Sehr helle, glänzende oder durchsichtige Teile heben sich schlecht vom weißen Papier ab. Dann in der "
          "App bei „Material“ hell bzw. transparent angeben."),

        Paragraph("3  Fotografieren", st_s),
        b("<b>Hauptkamera mit 2×- oder Tele mit 3×-Zoom</b>, 20–30 cm über der Karte, senkrecht von oben. Die "
          "Karte soll das Bild möglichst füllen."),
        b("<b>Kein Makro-Modus</b> und kein Ultraweitwinkel: Diese Objektive verzeichnen stark, das lässt sich "
          "mit acht Markern am Rand nicht korrigieren. Am iPhone „Makro-Steuerung“ ausschalten, bei Android "
          "den Makro-Vorschlag ablehnen."),
        b("Scharfstellen durch Tippen auf das Teil, dann ruhig halten oder Selbstauslöser verwenden."),
        b("Licht diffus und flach von der Seite, kein Blitz. Spiegelnde Teile mit Butterbrotpapier vor der "
          "Lampe entschärfen."),
        b("<b>Höhe:</b> Teil auf die Seite legen und eine zweite Draufsicht machen. Alternativ die Mini-Höhenlehre "
          "(Seite 2) direkt neben das Teil stellen."),

        Paragraph("Genauigkeit – realistisch", st_s),
        Paragraph("Die Auflösung der entzerrten Draufsicht beträgt 20 Bildpunkte pro Millimeter. Flache Teile, die "
                  "auf der Karte aufliegen: etwa ±0,1 mm, bei guter Aufnahme besser. Was höher liegt, ist näher an "
                  "der Kamera und erscheint größer: Fehler ≈ Maß × Höhe ÷ Kameraabstand. Beispiel: 20 mm breite "
                  "Oberkante, 5 mm über der Karte, 250 mm Abstand → etwa 0,4 mm zu breit. Deshalb an der "
                  "Auflagekante messen, aus größerem Abstand mit Zoom fotografieren oder das Teil kippen.", st_p),
        Paragraph("Die automatische Kantenerkennung findet Teile ab etwa 2 × 2 mm. Kleinere Details lassen sich in "
                  "der App von Hand messen. Für Passungen unter 0,05 mm ersetzt die Unterlage keinen Messschieber.",
                  st_p),
        Spacer(1, 6),
    ]


# kind "sheet": ganzes Blatt ist die Unterlage; "mini": ausschneidbare Karte auf A4
FORMATS = {
    "A4": {"page": A4, "marker": 20.0, "kind": "sheet"},
    "A3": {"page": A3, "marker": 25.0, "kind": "sheet"},
    "Mini": {"page": A4, "marker": MINI_MARKER, "kind": "mini"},
}
PAGES = ("mat", "gauge", "guide")
PX_PER_UNIT = 10.0   # entzerrte Draufsicht: Bildpunkte je feinster Rasterteilung (1 mm bzw. 0,5 mm)
_LOCK = threading.Lock()
_HEADER = ""


def _title(base):
    return f"{base}  ·  {_HEADER}" if _HEADER else base


def _page(c, fmt, kind, W, H):
    f = FORMATS[fmt]
    if kind == "mat":
        return mini_page(c, W, H, fmt) if f["kind"] == "mini" else mat_page(c, W, H, fmt, f["marker"])
    return mini_strip_page(c, W, H, fmt) if f["kind"] == "mini" else strip_page(c, W, H, fmt)


def _spec(fmt):
    f = FORMATS[fmt]
    W, H = (v / mm for v in f["page"])
    c = canvas.Canvas(io.BytesIO(), pagesize=f["page"])
    spec = _page(c, fmt, "mat", W, H)
    c.showPage()
    spec["height_gauge"] = _page(c, fmt, "gauge", W, H)
    mini = f["kind"] == "mini"
    unit = 0.5 if mini else 1.0
    # Ampel: groesster Restfehler fuer "gut" / "brauchbar" (Mini: gleiche Grenzen relativ zur Feldgroesse)
    spec.update(kind=f["kind"], ids=list(MINI_IDS if mini else SHEET_IDS), grid_unit_mm=unit,
                px_per_mm=PX_PER_UNIT / unit, ctrl_mm=100.0, verdict_mm=[0.2, 0.4] if mini else [0.5, 1.0])
    spec["height_gauge"].update(
        strips={k: list(v) for k, v in (MINI_GAUGE if mini else {"A": (10, 11, 14), "B": (12, 13, 15)}).items()},
        marker_size_mm=MINI_GAUGE_MARKER if mini else 18.0, x_range_mm=[-40.0, 40.0] if mini else [-100.0, 100.0],
        y_margin_mm=5.0 if mini else 10.0, px_per_mm=PX_PER_UNIT / unit)
    return spec


def layout(fmt):
    """Markerlayout eines Formats (ohne PDF zu speichern)."""
    with _LOCK:
        return _spec(fmt)


def build(out, fmt="A4", pages=PAGES, header=""):
    """PDF erzeugen. out = Pfad oder Datei-Objekt. Gibt das Markerlayout zurueck."""
    global _HEADER
    if fmt not in FORMATS:
        raise ValueError("Format muss " + ", ".join(FORMATS) + " sein")
    pages = [p for p in PAGES if p in pages] or list(PAGES)
    size = FORMATS[fmt]["page"]
    W, H = (v / mm for v in size)
    with _LOCK:
        _HEADER = (header or "").strip()[:60]
        try:
            spec = _spec(fmt)
            c = canvas.Canvas(out, pagesize=size)
            c.setTitle(f"Messunterlage {fmt}")
            for p in pages:
                if p in ("mat", "gauge"):
                    _page(c, fmt, p, W, H)
                else:
                    guide_page(c, W, H, fmt, spec)
                c.showPage()
            c.save()
        finally:
            _HEADER = ""
    return spec


if __name__ == "__main__":
    out = sys.argv[1]
    specs = {f: build(f"{out}/Messunterlage_{f}.pdf", f) for f in FORMATS}
    print(json.dumps(specs, indent=1))
