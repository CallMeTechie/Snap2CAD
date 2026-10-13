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


def mat_page(c, W, H, label, s):
    m = 10.0
    header, footer = 14.0, 26.0
    gw = int((W - 2 * m) // 10) * 10
    gh = int((H - 2 * m - header - footer) // 10) * 10
    gx = (W - gw) / 2
    gy = m + footer + ((H - 2 * m - header - footer) - gh) / 2

    # Raster
    for step, col, lw in ((1, C1, 0.15), (5, C5, 0.3), (10, C10, 0.5)):
        c.setStrokeColor(col)
        c.setLineWidth(lw)
        for i in range(0, gw + 1, step):
            if step < 10 and i % 10 == 0:
                continue
            if step == 1 and i % 5 == 0:
                continue
            c.line((gx + i) * mm, gy * mm, (gx + i) * mm, (gy + gh) * mm)
        for j in range(0, gh + 1, step):
            if step < 10 and j % 10 == 0:
                continue
            if step == 1 and j % 5 == 0:
                continue
            c.line(gx * mm, (gy + j) * mm, (gx + gw) * mm, (gy + j) * mm)

    # Achsbeschriftung alle 10 mm (unten + links), auf weissem Hinterlegungsfeld
    c.setFont("Helvetica", 5.5)
    for i in range(10, gw, 10):
        c.setFillColor(white)
        c.rect((gx + i - 2.2) * mm, (gy + 0.6) * mm, 4.4 * mm, 2.4 * mm, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.drawCentredString((gx + i) * mm, (gy + 1.1) * mm, str(i))
    for j in range(10, gh, 10):
        c.setFillColor(white)
        c.rect((gx + 0.6) * mm, (gy + j - 1.2) * mm, 4.6 * mm, 2.4 * mm, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.drawString((gx + 0.9) * mm, (gy + j - 0.7) * mm, str(j))

    # Mittelkreuz
    cxm, cym = gx + gw / 2, gy + gh / 2
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.6)
    c.line((cxm - 6) * mm, cym * mm, (cxm + 6) * mm, cym * mm)
    c.line(cxm * mm, (cym - 6) * mm, cxm * mm, (cym + 6) * mm)
    c.circle(cxm * mm, cym * mm, 3 * mm, stroke=1, fill=0)

    # Rahmen
    c.setStrokeColor(INK)
    c.setLineWidth(0.9)
    c.rect(gx * mm, gy * mm, gw * mm, gh * mm, stroke=1, fill=0)

    # Marker (Koordinaten relativ zum Rasterursprung unten links)
    q = 3.0
    k = q + s / 2
    pos = {
        0: (k, k), 1: (gw - k, k), 2: (gw - k, gh - k), 3: (k, gh - k),
        4: (gw / 2, k), 5: (gw - k, gh / 2), 6: (gw / 2, gh - k), 7: (k, gh / 2),
    }
    for mid, (px, py) in pos.items():
        white_box(c, gx + px, gy + py, s, q - 0.5)
        marker(c, mid, gx + px, gy + py, s)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 5)
        # Beschriftung ausserhalb der Ruhezone, Richtung Rastermitte
        ty = gy + py + (s / 2 + q + 1.0 if py < gh / 2 else -(s / 2 + q + 2.6))
        c.drawCentredString((gx + px) * mm, ty * mm, f"ID {mid}")

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
    by = m + 13
    bx = gx
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
    fx = bx + 112
    fw = gw - 112
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
                 "Ausschneiden, auf Karton kleben, an der blauen Linie falzen und direkt neben das Objekt stellen – alle drei Marker sichtbar.")
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
                 f"ArUco DICT_4X4_50 · Kante 18 mm · Markermitten über Falz: " +
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
    story = [
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
    names = {0: "unten links", 1: "unten rechts", 2: "oben rechts", 3: "oben links",
             4: "unten Mitte", 5: "rechts Mitte", 6: "oben Mitte", 7: "links Mitte"}
    for k, (px, py) in spec["centers_mm"].items():
        rows.append([f"ID {k}", names[int(k)], fmt(px), fmt(py)])
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


FORMATS = {"A4": (A4, 20.0), "A3": (A3, 25.0)}
PAGES = ("mat", "gauge", "guide")
_LOCK = threading.Lock()
_HEADER = ""


def _title(base):
    return f"{base}  ·  {_HEADER}" if _HEADER else base


def _spec(fmt):
    size, s = FORMATS[fmt]
    W, H = (v / mm for v in size)
    c = canvas.Canvas(io.BytesIO(), pagesize=size)
    spec = mat_page(c, W, H, fmt, s)
    c.showPage()
    spec["height_gauge"] = strip_page(c, W, H, fmt)
    return spec


def layout(fmt):
    """Markerlayout eines Formats (ohne PDF zu speichern)."""
    with _LOCK:
        return _spec(fmt)


def build(out, fmt="A4", pages=PAGES, header=""):
    """PDF erzeugen. out = Pfad oder Datei-Objekt. Gibt das Markerlayout zurueck."""
    global _HEADER
    if fmt not in FORMATS:
        raise ValueError("Format muss A4 oder A3 sein")
    pages = [p for p in PAGES if p in pages] or list(PAGES)
    size, s = FORMATS[fmt]
    W, H = (v / mm for v in size)
    with _LOCK:
        _HEADER = (header or "").strip()[:60]
        try:
            spec = _spec(fmt)
            c = canvas.Canvas(out, pagesize=size)
            c.setTitle(f"Messunterlage {fmt}")
            for p in pages:
                if p == "mat":
                    mat_page(c, W, H, fmt, s)
                elif p == "gauge":
                    strip_page(c, W, H, fmt)
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
