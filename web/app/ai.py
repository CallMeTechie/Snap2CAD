"""Anbindung an die Anthropic-API: Massvorschlaege und CAD-Code.

Nachrichten werden mit Bildverweisen ({"type": "image_ref", "path": ...}) gespeichert und vor jedem
Aufruf neu aufgebaut, damit die Datenbank keine Bilddaten enthaelt.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from . import config

MAX_IMG_SIDE = 1568

CAD_SYSTEM = """Du bist CAD-Konstrukteur. Du erzeugst aus Messwerten und entzerrten Fotos ein fertigungsreifes
Volumenmodell mit der Python-Bibliothek build123d. Einheit ist immer Millimeter.

Eingaben
- Eine Messtabelle (IDs M1, M2 …) mit Messwert, Unsicherheit, optionalem Schieblehren-Wert, Passung und
  Kennzeichnung „kritisch“. Ein Schieblehren-Wert hat immer Vorrang vor dem Fotowert.
- Entzerrte Fotos der Messunterlage (Draufsicht) und ggf. der Höhenlehre (Seitenansicht). Der Maßstab steht
  jeweils dabei. Ursprung der Draufsicht: linke untere Ecke des Rasters, x nach rechts, y nach oben.
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
8. Halte das Modell so einfach wie möglich, aber vollständig. Laufzeit unter 60 Sekunden.

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


class AIError(Exception):
    pass


class Cancelled(Exception):
    pass


_client = None
_client_lock = threading.Lock()


def client():
    global _client
    with _client_lock:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=3, timeout=600)
        return _client


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
    if not config.ANTHROPIC_API_KEY:
        raise AIError("Kein ANTHROPIC_API_KEY gesetzt – KI-Funktionen sind deaktiviert.")
    import anthropic
    try:
        text, last = [], time.time()
        with client().messages.stream(
                model=config.ANTHROPIC_MODEL, max_tokens=max_tokens,
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
        raise AIError("API-Schlüssel ungültig (ANTHROPIC_API_KEY prüfen).") from e
    except anthropic.RateLimitError as e:
        raise AIError("Anthropic-Ratenlimit erreicht – bitte später erneut versuchen.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Anthropic-API-Fehler {e.status_code}: {getattr(e, 'message', e)}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Keine Verbindung zur Anthropic-API.") from e


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


def parse_suggestions(text: str) -> list[dict]:
    t = text.strip()
    m = _BLOCK.search(t)
    if m:
        t = m.group(2)
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j < i:
        raise AIError("Die Antwort enthielt keine Vorschlagsliste.")
    try:
        items = json.loads(t[i:j + 1])
    except ValueError as e:
        raise AIError("Die Vorschlagsliste war kein gültiges JSON.") from e
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
        out.append({"label": str(it.get("label") or "Maß")[:80], "kind": kind, "value": round(value, 2),
                    "unit": "°" if kind == "angle" else "mm",
                    "unc": round(float(it.get("unc") or 0.5), 2) if str(it.get("unc", "")).strip() else 0.5,
                    "view": it.get("view") if it.get("view") in ("top", "gauge") else "top",
                    "points": pts, "reason": str(it.get("reason") or "")[:300], "unsure": bool(it.get("unsure"))})
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
