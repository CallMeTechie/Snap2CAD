"""Anbindung an die Anthropic-API: Massvorschlaege und CAD-Code.

Nachrichten werden mit Bildverweisen ({"type": "image_ref", "path": ...}) gespeichert und vor jedem
Aufruf neu aufgebaut, damit die Datenbank keine Bilddaten enthaelt.
"""
from __future__ import annotations

import base64
import json
import math
import re
import threading
import time
from pathlib import Path

import cv2

from . import config, settings

MAX_IMG_SIDE = 1568

CAD_SYSTEM = """Du bist CAD-Konstrukteur. Du erzeugst aus Messwerten und entzerrten Fotos ein fertigungsreifes
Volumenmodell mit der Python-Bibliothek build123d. Einheit ist immer Millimeter.

Eingaben
- Eine Messtabelle (IDs M1, M2 …) mit Messwert, Unsicherheit, optionalem Messschieber-Wert, Nennmaß-Vorschlag,
  Teil (T1, T2 …), Passung und Kennzeichnung „kritisch“. Ein Messschieber-Wert hat immer Vorrang vor dem Fotowert;
  das Nennmaß ist nur ein Vorschlag, Regel 2 gilt weiter.
- Entzerrte Fotos der Messunterlage (Draufsicht) und ggf. der Höhenlehre (Seitenansicht). Der Maßstab steht
  jeweils dabei. Ursprung der Draufsicht: linke untere Ecke des Rasters, x nach rechts, y nach oben.
- Ggf. eine Unteransicht (entzerrt, gespiegelt auf Draufsicht-Koordinaten: Bohrungen von unten und oben liegen
  übereinander) und Schrägansichten ohne Maßstab (nur für Form, Seitenflächen und Höhenverhältnis).
- Eine Zeile „Fotografiertes Original“ (Farbe, Material, Transparenz, Oberfläche des Teils – nicht das
  Fertigungsmaterial) und ggf. „Hinweise der Prüfung“.
- Fertigungsverfahren, Material und Wünsche des Nutzers.

Regeln für den Code
1. Alle Maße stehen als benannte Konstanten in GROSSBUCHSTABEN am Anfang, jeweils mit Kommentar zur Herkunft
   (z. B. `# M3 gemessen 4.93 -> Nennmaß 5.0`). Keine Zahlen „magisch“ im Modellcode.
2. Runde Messwerte auf plausible Nennmaße (ganze/halbe mm, Normgrößen wie M3-Durchgangsbohrung 3.4, Lager 22×8×7),
   wenn die Abweichung innerhalb der Messunsicherheit liegt. Erkläre jede Rundung in `dimensions`.
3. Berücksichtige das Fertigungsverfahren: Spiel für Passungen (FDM Bohrungen +0.2…0.3 mm, Spielpassung +0.3 mm,
   Presspassung −0.1 mm; CNC nach ISO-Passung), keine unfräsbaren Innenecken bei CNC (Radius ≥ Werkzeugradius),
   druckbare Überhänge bei FDM.
4. Das Teil liegt mit seiner größten ebenen Auflagefläche auf der XY-Ebene, Unterseite bei Z = 0.
5. Das fertige Teil MUSS der Variablen `part` zugewiesen werden (build123d Part/Solid/Compound, genau ein Körper).
6. `from build123d import *` und `import math` sind bereits ausgeführt. Keine weiteren Imports, kein Datei-Zugriff,
   kein Export, kein print, keine Netzwerkzugriffe – der Code läuft in einer Sandbox, die das blockiert.
7. Verrundungen und Fasen zuletzt und nur dort, wo sie sicher gelingen (Radius kleiner als angrenzende Wände).
8. Der Umriss aus der Draufsicht (Teile-Polygone) ist verbindlich: Fasen, Stufen, Absätze und Bohrungen daraus
   nachbilden. Fehlt ein Maß (z. B. die Höhe einer Stufe), schätze es, kennzeichne es als Annahme und nenne es in
   `check_before_manufacturing`. Weglassen ist nur erlaubt, was kleiner als 0,5 mm ist. Laufzeit unter 60 Sekunden.
9. Bei transparenten oder teiltransparenten Teilen sind durchscheinende Strukturen Innenbohrungen oder Innenkonturen,
   keine Rillen oder Nuten der Oberfläche. Bohrungen von unten und oben an derselben Stelle sind in der Regel ein
   Loch (ggf. Stufenloch).
10. Zu jedem offenen Punkt der Prüfung steht in `assumptions`, was angenommen wurde. Die Prüfung deutet Geometrie
   nicht verbindlich: Was ihr wie eine Nut, Rille oder Stufe erscheint, prüfst du selbst gegen Umriss, Unteransicht
   und Regel 9.

Antwortformat – genau zwei Codeblöcke, sonst höchstens zwei kurze Sätze:
```json
{
  "summary": "Ein Satz, was modelliert wurde",
  "assumptions": ["Annahme 1", "…"],
  "check_before_manufacturing": ["Was der Nutzer vor dem Fertigen prüfen sollte"],
  "dimensions": [{"id": "M1", "label": "Länge", "measured": 79.8, "nominal": 80.0, "note": "gerundet"}],
  "bbox_expected": [80.0, 50.0, 6.0],
  "orientation": "Unterseite auf XY, Ursprung Mitte"
}
```
```python
# build123d-Code, Ergebnis in `part`
```
"""

SUGGEST_SYSTEM = """Du hilfst beim Vermessen von Bauteilen auf einer entzerrten Messunterlage. Du bekommst
entzerrte Fotos mit bekanntem Maßstab (Pixel pro Millimeter steht dabei). Ursprung der Draufsicht ist die linke
untere Ecke des Bildes, x nach rechts, y nach oben (in mm). Bei der Höhenlehre ist x = 0 die Mitte des Streifens,
y die Höhe über der Unterlage.

Schlage die Maße vor, die man zum Nachkonstruieren des Teils braucht (Außenmaße, Bohrungen, Abstände, Radien,
Höhen). Lies die Werte aus den Pixeln ab und gib eine ehrliche Unsicherheit an (in der Regel 0.3–1.0 mm,
mehr bei unscharfen oder verdeckten Kanten). Wiederhole keine Maße, die schon gemessen wurden.

Antworte ausschließlich mit einem JSON-Array, ohne Text davor oder danach:
[{"label": "Bohrung links", "kind": "diameter", "value": 4.5, "unit": "mm", "unc": 0.3,
  "view": "top", "points": [[x1, y1], [x2, y2]], "reason": "Woran du den Wert abliest", "unsure": false}]
kind ist eines von: length, diameter, radius, height, angle (angle in Grad, unit "°").
points (optional, in mm der jeweiligen Ansicht): bei length/height die zwei Endpunkte, bei diameter/radius
[Mittelpunkt, Punkt auf dem Rand]. Höchstens 12 Vorschläge."""

PARTS_SYSTEM = """Du hilfst beim Vermessen von Bauteilen auf einer entzerrten Messunterlage (Draufsicht, Maßstab steht dabei).
Ursprung ist die linke untere Ecke des Bildes, x nach rechts, y nach oben, alles in mm.

Im Bild sind Kanten-Kandidaten eingezeichnet und nummeriert (K1, K2 …); die Liste mit Koordinaten steht im Text.
Sie stammen aus einer automatischen Kantenerkennung: Umrisskanten und gerade Kanten innerhalb des Objekts.

Aufgabe: Erkenne, aus welchen einzelnen Teilen das Objekt besteht. Beispiel: Ein Quader mit einer aufgeschraubten Platte,
die seitlich übersteht, sind zwei Teile – der Quader (role "body") und die Platte (role "mounted"). Ein einzelnes Teil
bleibt ein Teil. Gib für jedes Teil seinen vollständigen Umriss in der Draufsicht als Polygon an, auch dort, wo es von
einem anderen Teil verdeckt ist (verdeckte Kanten sinnvoll ergänzen, z. B. ein Rechteck vervollständigen). Nutze die
Koordinaten der Kandidaten, wo sie passen. Bohrungen gehören nicht in das Polygon.

Antworte ausschließlich mit einem JSON-Array, ohne Text davor oder danach:
[{"label": "Quader", "role": "body", "polygon": [[x1, y1], [x2, y2], [x3, y3]], "edges": ["K1", "K4"],
  "note": "kurz, woran erkannt"}]
role ist "body" (Grundkörper) oder "mounted" (montiertes Teil). edges = die Kandidaten, die zu diesem Teil gehören.
Höchstens 6 Teile, je 3 bis 32 Punkte."""

CHECK_SYSTEM = """Du prüfst vor dem CAD-Modellieren, ob die Unterlagen reichen. Du bekommst dieselben Fotos und Maße
wie der Konstrukteur: entzerrte Draufsicht (Maßstab steht dabei), ggf. Unteransicht (gespiegelt auf
Draufsicht-Koordinaten), Höhenlehre, Schrägansichten ohne Maßstab, Messtabelle, Teile-Umrisse.

Nenne, was zum vollständigen Nachbilden fehlt oder unsicher ist, je Punkt mit Art und Stufe:
kind: height (Höhe/Dicke unbekannt), bottom (Unterseite fehlt oder unklar), photo (weiteres Foto nötig, z. B.
Seite), measure (ein Maß fehlt oder widerspricht), sharpness (Kante unscharf, verdeckt oder im Schatten), other.
severity: block = ohne diese Angabe wird das Modell geraten; warn = die Genauigkeit leidet.
Jeder Text sagt, was der Nutzer tun soll (z. B. „Höhenlehre fotografieren oder Höhe als Maß eingeben“).
Höchstens 8 Punkte, keine Punkte zu Dingen, die schon in der Messtabelle stehen.
Bei transparenten oder teiltransparenten Teilen (siehe Zeile „Fotografiertes Original“) sind durchscheinende
Strukturen Innenbohrungen oder Innenkonturen, keine Nuten, Rillen oder Stufen – dafür keinen Punkt und kein
weiteres Foto verlangen.

Schätze außerdem das fotografierte Teil: color (ein Wort, z. B. silber, schwarz, weiß), material (z. B. Aluminium,
Stahl, Kunststoff, Holz, Glas), transparent (0 nein, 1 teilweise, 2 ja), finish (matt oder glaenzend), note (ein Satz).

Antworte ausschließlich mit einem JSON-Objekt:
{"items": [{"kind": "height", "severity": "block", "text": "…"}],
 "material": {"color": "…", "material": "…", "transparent": 0, "finish": "matt", "note": "…"}}"""

CHECK_KINDS = ("height", "bottom", "photo", "measure", "sharpness", "other")
FINISHES = ("matt", "glaenzend")                                    # zulaessige Oberflaechen am Werkstueck


class AIError(Exception):
    pass


class Cancelled(Exception):
    pass


_client = None
_client_key = ""
_client_lock = threading.Lock()


def client():
    """Gemeinsamer Client; wird neu gebaut, sobald der Schluessel in der Verwaltung geaendert wurde."""
    global _client, _client_key
    key = settings.api_key()
    with _client_lock:
        if _client is None or key != _client_key:
            import anthropic
            _client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=600)
            _client_key = key
        return _client


_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{20,300}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@\-]{2,99}$")


def check_key_format(key: str) -> str | None:
    if not _KEY_RE.match(key or ""):
        return "Das sieht nicht wie ein API-Schlüssel aus (erwartet z. B. „sk-ant-…“, ohne Leerzeichen)."
    return None


def check_model_format(model: str) -> str | None:
    if not _MODEL_RE.match(model or ""):
        return "Ungültiger Modellname (z. B. „claude-sonnet-5-5“)."
    return None


def verify(key: str, model: str | None = None) -> str | None:
    """Prueft Schluessel (und optional Modell) mit einem kostenlosen API-Aufruf. None = in Ordnung,
    sonst eine Fehlermeldung fuer die Oberflaeche. Es werden keine Token verbraucht."""
    err = check_key_format(key) or (check_model_format(model) if model else None)
    if err:
        return err
    if config.AI_FAKE:
        return None
    import anthropic
    c = anthropic.Anthropic(api_key=key, max_retries=1, timeout=20)
    try:
        if model:
            c.models.retrieve(model)
        else:
            c.models.list(limit=1)
    except anthropic.AuthenticationError:
        return "Anthropic lehnt diesen API-Schlüssel ab. Bitte in der Anthropic Console prüfen."
    except anthropic.PermissionDeniedError:
        return "Dieser API-Schlüssel hat keine Berechtigung für die Anthropic-API."
    except anthropic.NotFoundError:
        return f"Das Modell „{model}“ ist mit diesem Schlüssel nicht verfügbar."
    except anthropic.RateLimitError:
        return None  # Schluessel ist gueltig, nur gerade ausgelastet
    except anthropic.APIConnectionError:
        return "Keine Verbindung zur Anthropic-API (api.anthropic.com). Hat der Server Internetzugang?"
    except anthropic.APIStatusError as e:
        return f"Anthropic-API antwortet mit Fehler {e.status_code}. Bitte später erneut versuchen."
    finally:
        c.close()
    return None


# ------------------------------------------------------------------ Bilder

def prepare_image(path: Path, max_side: int = MAX_IMG_SIDE) -> tuple[bytes, float]:
    """JPEG fuer die API, verkleinert. Rueckgabe (bytes, Skalierungsfaktor)."""
    img = cv2.imread(str(path))
    if img is None:
        raise AIError(f"Bild fehlt: {path.name}")
    s = min(1.0, max_side / max(img.shape[:2]))
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buf.tobytes(), s


def image_ref(path: Path, caption: str) -> list[dict]:
    """Bildverweis + Beschriftung (Massstab nach Verkleinerung)."""
    return [{"type": "image_ref", "path": str(path)}, {"type": "text", "text": caption}]


def scaled_caption(path: Path, base: str, pxmm: float) -> str:
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    s = min(1.0, MAX_IMG_SIDE / max(h, w))
    return (f"{base} – Bild {round(w * s)}×{round(h * s)} px, Maßstab {pxmm * s:.3f} px/mm "
            f"(Bildbreite = {w / pxmm:.1f} mm, Bildhöhe = {h / pxmm:.1f} mm).")


def _materialize(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        blocks = []
        for b in content:
            if b.get("type") == "image_ref":
                data, _ = prepare_image(Path(b["path"]))
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                           "data": base64.b64encode(data).decode()}})
            else:
                blocks.append({k: v for k, v in b.items() if k in ("type", "text")})
        out.append({"role": m["role"], "content": blocks})
    # aufeinanderfolgende Nachrichten derselben Rolle zusammenfassen (z. B. nach API-Fehler)
    merged: list[dict] = []
    for m in out:
        c = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"].extend(c)
        else:
            merged.append({"role": m["role"], "content": list(c)})
    # Cache-Marke hinter der ersten Nutzernachricht (Fotos + Masstabelle): Korrekturen und
    # Aenderungswuensche lesen diesen grossen Block dann aus dem Prompt-Cache.
    if len(merged) > 1 and merged[0]["role"] == "user" and merged[0]["content"]:
        merged[0]["content"][-1] = {**merged[0]["content"][-1], "cache_control": {"type": "ephemeral"}}
    return merged


# ------------------------------------------------------------------ Aufruf

def call(system: str, messages: list[dict], max_tokens: int = 16000, cancel: threading.Event | None = None,
         on_progress=None) -> tuple[str, dict]:
    """Ruft Claude auf. Rueckgabe (Text, usage)."""
    if config.AI_FAKE:
        return _fake(system, messages, cancel)
    if not settings.api_key():
        raise AIError("KI ist nicht eingerichtet – KI-Funktionen sind deaktiviert.")
    import anthropic
    try:
        text, last = [], time.time()
        with client().messages.stream(
                model=settings.model(), max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=_materialize(messages)) as stream:
            n = 0
            for chunk in stream.text_stream:
                text.append(chunk)
                n += len(chunk)
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                if on_progress and time.time() - last > 3:
                    on_progress(n)
                    last = time.time()
            final = stream.get_final_message()
        u = final.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
                 "model": final.model, "stop_reason": final.stop_reason}
        return "".join(text), usage
    except Cancelled:
        raise
    except anthropic.AuthenticationError as e:
        raise AIError("API-Schlüssel ungültig (Verwaltung → Einstellungen prüfen).") from e
    except anthropic.RateLimitError as e:
        raise AIError("KI-Dienst: Ratenlimit erreicht – bitte später erneut versuchen.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"KI-Dienst: Fehler {e.status_code}: {getattr(e, 'message', e)}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Keine Verbindung zum KI-Dienst.") from e


# ------------------------------------------------------------------ Antworten zerlegen

_BLOCK = re.compile(r"```(\w+)?\s*\n(.*?)```", re.S)


def parse_cad(text: str) -> tuple[dict, str]:
    meta, code = None, None
    for lang, body in _BLOCK.findall(text):
        lang = (lang or "").lower()
        if lang == "json" and meta is None:
            try:
                meta = json.loads(body)
            except ValueError:
                pass
        elif lang in ("python", "py") or (not lang and "part" in body and code is None):
            code = body.strip() + "\n"
    if code is None:
        raise AIError("Die Antwort enthielt keinen Python-Codeblock.")
    meta = meta if isinstance(meta, dict) else {}
    for k in ("assumptions", "check_before_manufacturing", "dimensions"):
        if not isinstance(meta.get(k), list):
            meta[k] = []
    return meta, code


def _json_span(text: str, lo: str, hi: str) -> str | None:
    """Teilstring von erstem lo bis letztem hi (auch in einem Codeblock oder mit Text drumherum)."""
    t = text.strip()
    m = _BLOCK.search(t)
    if m:
        t = m.group(2)
    i, j = t.find(lo), t.rfind(hi)
    return t[i:j + 1] if i >= 0 and j >= i else None


def _json_array(text: str, what: str) -> list:
    """JSON-Array aus einer KI-Antwort."""
    span = _json_span(text, "[", "]")
    if span is None:
        raise AIError(f"Die Antwort enthielt keine {what}.")
    try:
        return json.loads(span)
    except ValueError as e:
        raise AIError(f"Die {what} war kein gültiges JSON.") from e


def _json_object(text: str) -> dict | None:
    span = _json_span(text, "{", "}")
    try:
        o = json.loads(span) if span else None
    except (ValueError, RecursionError):
        return None
    return o if isinstance(o, dict) else None


def _text(v, n: int, default: str = "") -> str:
    """Nur echte Texte uebernehmen: str() wuerde aus einer Liste oder Zahl der KI ein Label wie "['x']" machen."""
    return (v.strip()[:n] or default) if isinstance(v, str) else default


def parse_check(text: str) -> dict:
    """Pruefergebnis defensiv lesen (Spec §2.1): unbekannte Art -> other, fehlende Stufe -> warn, Texte einzeilig."""
    o = _json_object(text) or {}
    items = []
    for it in o.get("items") if isinstance(o.get("items"), list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("text"), str) or not it["text"].strip():
            continue
        items.append({"kind": it.get("kind") if it.get("kind") in CHECK_KINDS else "other",
                      "severity": it.get("severity") if it.get("severity") in ("block", "warn") else "warn",
                      "text": " ".join(it["text"].split())[:200]})
        if len(items) == 8:
            break
    mat, material = o.get("material"), None
    if isinstance(mat, dict):
        tr = mat.get("transparent")
        material = {"color": _text(mat.get("color"), 40) or None, "material": _text(mat.get("material"), 40) or None,
                    "transparent": tr if tr in (0, 1, 2) else None,
                    "finish": mat.get("finish") if mat.get("finish") in FINISHES else None,
                    "note": _text(mat.get("note"), 300)}
    return {"items": items, "material": material}


def parse_suggestions(text: str) -> list[dict]:
    items = _json_array(text, "Vorschlagsliste")
    out = []
    kinds = {"length", "diameter", "radius", "height", "angle"}
    for it in items[:12]:
        if not isinstance(it, dict):
            continue
        try:
            value = float(it.get("value"))
        except (TypeError, ValueError):
            continue
        kind = it.get("kind") if it.get("kind") in kinds else "length"
        pts = it.get("points")
        if not (isinstance(pts, list) and all(isinstance(p, list) and len(p) == 2 for p in pts)):
            pts = None
        out.append({"label": _text(it.get("label"), 80, "Maß"), "kind": kind, "value": round(value, 2),
                    "unit": "°" if kind == "angle" else "mm",
                    "unc": round(float(it.get("unc") or 0.5), 2) if str(it.get("unc", "")).strip() else 0.5,
                    "view": it.get("view") if it.get("view") in ("top", "gauge") else "top",
                    "points": pts, "reason": _text(it.get("reason"), 300), "unsure": bool(it.get("unsure"))})
    return out


def parse_parts(text: str) -> list[dict]:
    """Teileliste der KI defensiv lesen (Spec §2): unbrauchbare Eintraege werden verworfen."""
    items = _json_array(text, "Teileliste")
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        pts = it.get("polygon")
        if not isinstance(pts, list) or not 3 <= len(pts) <= 32:
            continue
        try:
            poly = [[float(p[0]), float(p[1])] for p in pts if isinstance(p, list) and len(p) == 2]
        except (TypeError, ValueError):
            continue
        if len(poly) != len(pts) or not all(math.isfinite(v) and abs(v) < 1e4 for p in poly for v in p):
            continue
        raw_edges = it.get("edges") if isinstance(it.get("edges"), list) else []
        out.append({"label": _text(it.get("label"), 80, "Teil"),
                    "role": it.get("role") if it.get("role") in ("body", "mounted") else "body",
                    "polygon": poly, "edges": [str(e)[:8] for e in raw_edges
                                               if isinstance(e, (str, int)) and not isinstance(e, bool)][:64],
                    "note": _text(it.get("note"), 300)})
        if len(out) == 6:
            break
    return out


# ------------------------------------------------------------------ Testmodus (AI_FAKE=1)

_FAKE_V1 = '''# Montageplatte – Testmodus (AI_FAKE)
LENGTH = 80.0        # M1 gemessen 79.8 -> 80.0
WIDTH = 50.0         # M2 gemessen 50.1 -> 50.0
THICKNESS = 6.0      # M5 Höhe 6.1 -> 6.0
HOLE_D = 4.5         # M3 Bohrung (FDM +0.2 -> 4.7 wäre Spiel)
HOLE_DX = 64.0       # M4 Lochabstand x
HOLE_DY = 34.0       # Lochabstand y
CORNER_R = 30.0      # Eckenradius – absichtlich zu groß (Test für Selbstkorrektur)

with BuildPart() as p:
    Box(LENGTH, WIDTH, THICKNESS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((0, 0, THICKNESS)):
        with GridLocations(HOLE_DX, HOLE_DY, 2, 2):
            Hole(HOLE_D / 2)
    fillet(p.edges().filter_by(Axis.Z), radius=CORNER_R)
part = p.part
'''

_FAKE_V2 = '''# Montageplatte – Testmodus (AI_FAKE)
LENGTH = 80.0        # M1 gemessen 79.8 -> 80.0
WIDTH = 50.0         # M2 gemessen 50.1 -> 50.0
THICKNESS = {t}       # M5 Höhe
HOLE_D = 4.5         # M3 Bohrung
HOLE_DX = 64.0       # M4 Lochabstand x
HOLE_DY = 34.0       # Lochabstand y
CORNER_R = 5.0       # Eckenradius (korrigiert, < halbe Breite)
SLOT_L = 30.0        # Langloch Länge
SLOT_W = 8.0         # Langloch Breite

with BuildPart() as p:
    Box(LENGTH, WIDTH, THICKNESS, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(p.edges().filter_by(Axis.Z), radius=CORNER_R)
    with Locations((0, 0, THICKNESS)):
        with GridLocations(HOLE_DX, HOLE_DY, 2, 2):
            Hole(HOLE_D / 2)
    with BuildSketch(Plane.XY.offset(THICKNESS)):
        SlotCenterToCenter(SLOT_L - SLOT_W, SLOT_W)
    extrude(amount=-THICKNESS, mode=Mode.SUBTRACT)
part = p.part
'''


def _fake_meta(t):
    return {"summary": f"Montageplatte 80 × 50 × {t:g} mm mit vier Bohrungen und Langloch (Testmodus).",
            "assumptions": ["Bohrungen sind Durchgangsbohrungen", "Langloch mittig, gleiche Tiefe wie die Platte"],
            "check_before_manufacturing": ["Bohrungsdurchmesser mit Schieblehre nachmessen",
                                           "Eckenradius am Original prüfen"],
            "dimensions": [{"id": "M1", "label": "Länge", "measured": 79.8, "nominal": 80.0, "note": "gerundet"},
                           {"id": "M2", "label": "Breite", "measured": 50.1, "nominal": 50.0, "note": "gerundet"},
                           {"id": "M5", "label": "Dicke", "measured": 6.1, "nominal": t, "note": ""}],
            "bbox_expected": [80.0, 50.0, t], "orientation": "Unterseite auf XY, Ursprung Mitte"}


def _fake(system, messages, cancel):
    for _ in range(10):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        time.sleep(0.1)
    usage = {"input_tokens": 4200, "output_tokens": 900, "cache_read": 0, "cache_write": 0,
             "model": "fake", "stop_reason": "end_turn"}
    if system == PARTS_SYSTEM:
        last = messages[-1]["content"]
        txt = " ".join(b.get("text", "") for b in last if isinstance(b, dict))
        m = re.search(r"Umriss 1: (.*)", txt)
        pts = [[float(a), float(b)] for a, b in re.findall(r"\((-?[\d.]+), (-?[\d.]+)\)", m.group(1))] if m else []
        return json.dumps([{"label": "Quader", "role": "body", "polygon": pts, "edges": [], "note": "Testmodus"}]), usage
    if system == CHECK_SYSTEM:
        return json.dumps({"items": [
            {"kind": "height", "severity": "block",
             "text": "Höhe des Grundkörpers unbekannt – Höhenlehre fotografieren oder Höhe als Maß eingeben."},
            {"kind": "bottom", "severity": "warn", "text": "Unterseite fehlt – Teil umdrehen und als „Von unten“ hochladen."}],
            "material": {"color": "silber", "material": "Aluminium", "transparent": 0, "finish": "matt", "note": "Testmodus"}},
            ensure_ascii=False), usage
    if system == SUGGEST_SYSTEM:
        return json.dumps([
            {"label": "Gesamtlänge", "kind": "length", "value": 79.8, "unc": 0.4, "view": "top",
             "points": [[55, 90], [134.8, 90]], "reason": "Außenkanten links/rechts klar erkennbar", "unsure": False},
            {"label": "Bohrung oben links", "kind": "diameter", "value": 4.5, "unc": 0.3, "view": "top",
             "points": [[63, 107], [65.25, 107]], "reason": "Kreisrand scharf", "unsure": False},
            {"label": "Eckenradius", "kind": "radius", "value": 5.0, "unc": 1.0, "view": "top",
             "points": [[60, 70], [55, 70]], "reason": "Rundung schwach erkennbar", "unsure": True},
        ], ensure_ascii=False), usage
    last = messages[-1]["content"]
    last_text = last if isinstance(last, str) else " ".join(b.get("text", "") for b in last)
    n_assist = sum(1 for m in messages if m["role"] == "assistant")
    if n_assist == 0:
        code, t = _FAKE_V1, 6.0
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", last_text) if "Änderungswunsch" in last_text else None
        t = float(m.group(1).replace(",", ".")) if m else 6.0
        t = t if 1 <= t <= 40 else 6.0
        code = _FAKE_V2.format(t=f"{t:.1f}")
    text = ("Hier ist das Modell.\n```json\n" + json.dumps(_fake_meta(t), ensure_ascii=False, indent=1)
            + "\n```\n```python\n" + code + "```\n")
    return text, usage
