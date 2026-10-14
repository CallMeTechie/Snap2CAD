# Kanten, Teile und mitdenkende Bemaßung – Design

Stand: 14.10.2026 · Branch `kanten-und-teile`

## Ziel

Fotografierte Objekte sollen sich schneller und richtiger vermessen lassen:

1. Snap2CAD erkennt die Kanten eines Objekts auf der entzerrten Draufsicht selbst, zeichnet sie ein, und der Nutzer kann sie bearbeiten.
2. Snap2CAD erkennt, aus welchen Teilen ein Objekt besteht (Beispiel: Quader mit aufgeschraubter, seitlich überstehender Platte), und bemaßt jedes Teil für sich.
3. Korrigiert der Nutzer eine Länge (Messschieber-Wert), schließt Snap2CAD daraus auf den Maßstab des Teils und passt alle anderen Maße dieses Teils an. Diese Schlussfolgerung bleibt gespeichert.
4. Die Oberfläche nennt Claude nicht mehr beim Namen; der Button „Prompt herunterladen“ entfällt.

Erfolgskriterium (Beispiel aus dem Auftrag): Quader 60 × 40 × 30 mm, Draufsicht. Kanten werden erkannt, der Fotowert der Länge ist wegen Parallaxe z. B. 63,6 mm. Der Nutzer trägt bei der Länge 60,00 als Messschieber-Wert ein → die Breite springt von 42,4 auf 40,0 mm, ohne dass er sie anfasst. Bei Quader + Platte erscheinen zwei Teile mit je eigenen Kanten und Maßen.

## Entscheidungen des Nutzers (14.10.2026)

| Frage | Entscheidung |
|---|---|
| Erkennung | Hybrid: OpenCV findet Kanten pixelgenau, die KI ordnet sie Teilen zu |
| Schlussfolgerung | Maßstab pro Teil aus Referenzmaßen, dazu Geometrie-Regeln und Nennmaß-Hinweis; im Projekt gespeichert, rücknehmbar |
| CAD mit mehreren Teilen | Teil wählbar (oder alle als ein Körper wie heute); Prüfkette und Sandbox unverändert |
| Claude in der Oberfläche | Ganze App neutral („KI“); nur Einrichtung und Verwaltung nennen „Anthropic-API-Schlüssel“ und den Console-Link; README bleibt |

## Nicht im Umfang

- Höhen aus der Draufsicht ableiten (Kameraabstand unbekannt). Höhen kommen weiter aus Höhenlehre, gekipptem Foto oder manueller Eingabe.
- Kantenerkennung auf der Höhenlehre.
- Projektübergreifendes Lernen.
- CAD als Baugruppe mit mehreren Körpern.

## Begriffe

- **Teil** (`T1`, `T2` …): ein Körper im Foto mit Bezeichnung, Rolle (`body` = Grundkörper, `mounted` = montiertes Teil) und einem geschlossenen Polygon in mm der Draufsicht. Teile dürfen sich überlappen (Platte liegt auf dem Quader).
- **Kante**: eine Seite eines Teil-Polygons. Eine Kante kann `hidden` sein (verdeckt/geschätzt, z. B. Quaderkante unter der Platte).
- **Kandidat**: eine von OpenCV gefundene Kante (Umrissseite oder gerades Segment im Objekt), noch keinem Teil zugeordnet.
- **Auto-Maß**: Messung, die Snap2CAD aus einem Teil-Polygon erzeugt (`source = 'auto'`).
- **Referenz**: Messung eines Teils mit Messschieber-Wert, die den Maßstab des Teils bestimmt.
- **Maßstab k** eines Teils: Median über alle Referenzen von `Messschieber-Wert / Fotowert`. Ohne Referenz ist k = 1.

## 1. Kantenerkennung (`core/edges.py`, ohne KI)

Eingabe: entzerrte Draufsicht `rect.jpg` (10 px/mm, deckt genau die Rasterfläche des Formats ab, Ursprung unten links) und das Format. Ausgabe in mm, gleiche Koordinaten wie die Messungen (x nach rechts, y nach oben).

Ablauf:

1. **Arbeitsbild** auf 4 px/mm verkleinern. Markerquadrate, die in die Rasterfläche ragen, werden aus `spec(fmt)` maskiert.
2. **Raster entfernen**: morphologisches Schließen (Graustufen, Kern ≈ 1,5 mm) entfernt die dunklen dünnen Rasterlinien.
3. **Papier vom Objekt trennen**: Abstand jedes Pixels zur Papierfarbe in Lab (Helligkeitsabfall und Farbabweichung). Die Papierfarbe wird robust aus dem Randstreifen der Rasterfläche geschätzt (Median). Schwelle per Otsu mit Untergrenze.
4. **Maske säubern**: Öffnen/Schließen, Komponenten unter 25 mm² verwerfen. Danach GrabCut mit dieser Maske als Startwert (sicher Vordergrund innen, wahrscheinlich Hintergrund am Rand, 3 Iterationen).
5. **Umriss**: äußere Konturen (≥ 25 mm²) → `approxPolyDP` mit 0,8 mm Toleranz. Jede Polygonseite wird auf dem vollen Bild (10 px/mm) verfeinert: entlang der Normalen den stärksten Gradienten suchen und eine Gerade durch diese Punkte legen; benachbarte Geraden werden geschnitten → Eckpunkte. Weicht ein Eckpunkt mehr als 2 mm vom groben Polygon ab, bleibt der grobe Punkt.
6. **Bohrungen**: innere Konturen mit Kreisförmigkeit ≥ 0,85 und Ø ≥ 2 mm → Kreis (Mittelpunkt, Durchmesser) per Kleinste-Quadrate-Anpassung.
7. **Innenkanten**: Canny auf dem vollen Bild innerhalb der um 1,5 mm erodierten Maske, Liniensegmente per `cv2.createLineSegmentDetector`, kollineare Stücke zusammenfassen, Länge ≥ 8 mm, höchstens 40 Segmente (längste zuerst).

Ergebnis (`EdgeResult`, als `edges.json` im Fotoordner gespeichert):

```json
{"outlines": [{"polygon": [[x, y], …], "area": 2400.0}],
 "holes": [{"c": [x, y], "d": 4.5}],
 "segments": [{"id": "K1", "a": [x, y], "b": [x, y], "kind": "outline|inner"}],
 "px_per_mm": 10.0}
```

Kandidaten `K…` sind alle Umrissseiten (`outline`) und alle Innenkanten (`inner`), fortlaufend nummeriert.

Bekannte Grenzen (stehen auch im Hinweis der Oberfläche): weiße Teile auf weißem Papier und harte Schlagschatten verfälschen den Umriss. Der Nutzer korrigiert dann die Eckpunkte.

## 2. Teile-Zuordnung (KI) und Einrasten (`web/app/parts.py`)

**Mit KI:** Die KI bekommt die Draufsicht mit eingezeichneten, nummerierten Kandidaten (farbig, Nummer an der Kantenmitte) und die Kandidatenliste als Text (`K3: (12.0, 40.5) → (72.4, 40.6), 60.4 mm, Umriss`). Neuer Systemprompt `PARTS_SYSTEM` in `ai.py`. Antwort ausschließlich JSON:

```json
[{"label": "Quader", "role": "body", "polygon": [[x, y], …], "edges": ["K1", "K4"], "note": "…"}]
```

Höchstens 6 Teile, je 3–32 Punkte. `parse_parts` prüft defensiv wie `parse_suggestions` (Typen, endliche Zahlen, Rolle aus {body, mounted}, Bezeichnung ≤ 80 Zeichen).

**Einrasten** (`snap_polygon(polygon, segments)`): Für jede Polygonseite wird der passende Kandidat gesucht (Winkelabweichung < 6°, mittlerer Abstand der Kandidaten-Endpunkte zur Seite < 3 mm, Überlappung in Längsrichtung ≥ 30 % der Kandidatenlänge; bester = kleinster Abstand). Treffer → die Seite übernimmt die Gerade des Kandidaten. Kein Treffer → Seite bleibt, wird `hidden`. Neue Eckpunkte = Schnitt benachbarter Geraden; bei fast parallelen Geraden (< 10°) oder Verschiebung > 8 mm bleibt der KI-Punkt.

**Ohne KI** (kein Schlüssel, KI-Fehler oder `use_ai = false`): jedes Umriss-Polygon wird ein Teil („Teil“, `body`), Innenkanten bleiben unzugeordnet und werden gestrichelt grau angezeigt. Bei KI-Fehler wird die Fehlermeldung als Hinweis zurückgegeben, die Teile aus dem Umriss entstehen trotzdem.

**Bohrungen** werden dem kleinsten Teil zugeordnet, dessen Polygon den Mittelpunkt enthält.

**Testmodus (`AI_FAKE`)**: liefert deterministisch ein Teil „Quader“ aus dem ersten Umriss der Kandidatenliste.

## 3. Bemaßung und Schlussfolgerung (`web/app/parts.py`)

Eine zentrale Funktion `refresh(project_id)` hält alles konsistent. Sie läuft nach jeder Änderung an Teilen, Messungen mit Punkten, Messschieber-Werten oder Kontrollmaß (ersetzt `_recompute`).

**Zuordnung Messung → Teil** (nur Draufsicht-Messungen mit Punkten auf demselben Foto, ohne `data.part_fixed`): Für jedes Teil zählt, wie viele Punkte auf seinem Rand liegen (≤ 1,5 mm) und ob alle Punkte innerhalb oder auf dem Rand liegen. Gewinner: meiste Randpunkte, bei Gleichstand das kleinste Teil. Liegt nicht jeder Punkt in oder an einem Teil → keine Zuordnung. Der Nutzer kann die Zuordnung im Bearbeiten-Feld festlegen (`part_fixed = true`).

**Auto-Maße** (je Teil, mit Schlüssel `data.auto_key`):

- Rechteck (4 Ecken, alle Innenwinkel 90° ± 4°): `L` Länge (längeres Seitenpaar, Mittelwert beider Seiten), `B` Breite. Unterscheiden sich gegenüberliegende Seiten um mehr als 1 mm, bekommt das Maß den Hinweis „gegenüberliegende Kanten ungleich – Kante prüfen“.
- Sonst: `E1 … En` je Kante; verdeckte Kanten bekommen den Hinweis „verdeckt, geschätzt“.
- Bohrungen: `H1 …` als Durchmesser.
- Bezeichnung z. B. „Quader Länge“, „Platte Kante 3“, „Quader Bohrung 1“. Punkte des Maßes = Endpunkte der Kante (für die Anzeige).

Bei Änderung des Polygons werden Auto-Maße mit gleichem Schlüssel aktualisiert (Bezeichnung, Messschieber-Wert, kritisch, Passung, Notiz bleiben), fehlende ergänzt, überzählige gelöscht. Löscht der Nutzer ein Auto-Maß, merkt sich das Teil den Schlüssel (`data.dropped`) und erzeugt es nicht neu.

**Maßstab k je Teil:**

- Referenzen = Messungen des Teils mit Messschieber-Wert, Art Länge/Durchmesser/Radius, `data.ref` nicht `false`. Verhältnis = Messschieber-Wert / Fotowert ohne Teil-Maßstab (aber mit Kontrollmaß-Faktoren).
- Verhältnis außerhalb 0,75–1,25 → diese Messung zählt nicht als Referenz, Hinweis „Abweichung zu groß – falsches Maß oder falsches Teil?“. Der Messschieber-Wert selbst bleibt gültig.
- k = Median der gültigen Verhältnisse. Weichen sie um mehr als 1 % voneinander ab → Warnung am Teil „Referenzen widersprechen sich (…)“.
- Werte: Länge/Höhe/Durchmesser/Radius des Teils = Fotowert × k. Winkel und Punktkoordinaten bleiben unverändert. Höhenlehre-Messungen gehören keinem Teil.
- `data.raw` speichert den Fotowert ohne k, damit die Anzeige „Foto 63,60 → 60,00 (× 0,943)“ möglich ist.
- „Maßstab zurücksetzen“ setzt `data.ref = false` bei allen Referenzen des Teils; Messschieber-Werte bleiben.

**Nennmaß-Hinweis:** für Längen und Durchmesser `nominal = round(v × 2) / 2`, wenn `|v − nominal| ≤ max(unc, 0,2)`; bei Messschieber-Wert ist das Nennmaß der Messschieber-Wert. Anzeige „≈ 60“, Übergabe an CAD.

**Gespeichert** wird die Schlussfolgerung in den Referenzmessungen selbst; k wird am Teil nur zwischengespeichert. Eine neue Kantenerkennung für dasselbe Foto löscht die alten Teile; Auto-Maße mit Messschieber-Wert werden dabei zu normalen Messungen (`source = 'user'`, Punkte bleiben) und landen per Zuordnung im neuen Teil → der Maßstab bleibt erhalten.

## 4. Oberfläche „Messen“ (`web/static/js/edges.js`, Anbindung in `measure.js`)

- Werkzeugleiste: Button **„Kanten erkennen“**. Vorhandene Teile auf diesem Foto → Rückfrage „Teile dieses Fotos werden neu erkannt. Messschieber-Referenzen bleiben erhalten.“ Während des Laufs Spinner im Button („Kanten werden erkannt …“).
- Neues Werkzeug **„Kanten“** (Taste E): Teile werden farbig gezeichnet (eigene Palette, verschieden von Blau = Messung und Orange = KI-Vorschlag), verdeckte Kanten gestrichelt, unzugeordnete Kandidaten grau gestrichelt.
  - Eckpunkt ziehen (Kantenfang gilt), „+“ an der Kantenmitte fügt einen Punkt ein, Eckpunkt anklicken und Entf löscht ihn (mindestens 3 bleiben).
  - Klick auf ein Teil wählt es aus. „Neues Teil“ in der Seitenleiste startet das Zeichnen: Punkte setzen, Klick auf den ersten Punkt oder Enter schließt, Esc bricht ab.
  - Änderungen werden beim Loslassen gespeichert (PATCH), danach werden Teile und Messungen neu geladen.
- Seitenleiste, Bereich **„Teile“** über den Messungen: je Teil `T1`, Bezeichnung, Rolle, Kurzmaß („60,00 × 40,00 mm“ beim Rechteck, sonst „6 Kanten“), Maßstab-Chip „× 0,943 aus M3“ mit „Zurücksetzen“, Warnungen. Ausgewählt: Bezeichnung, Rolle, Löschen.
- Messungsliste: Chip `T1` bei zugeordneten Messungen, „≈ 60“ beim Nennmaß, bei skalierten Werten Titel „Foto 63,60 mm × 0,943“. Herkunft „automatisch aus T1“ bei Auto-Maßen.
- Bearbeiten-Feld einer Messung: Auswahl „Teil“ (automatisch / T1 / T2 / keins), Kästchen „Als Referenz für T1“ (nur bei Messschieber-Wert und Teil), Hinweistext unter dem Messschieber-Feld „Wird zur Referenz für T1 – alle Maße des Teils werden angepasst“.
- Hinweisleiste beim Werkzeug: „Kanten: Eckpunkt ziehen · + an der Kantenmitte = Punkt einfügen · Entf = Punkt löschen · Esc = abbrechen“.

## 5. CAD-Schritt

- Formular: Auswahl **„Modell für“** – „Alle Teile (ein Körper)“ (Standard) oder je Teil. Nur sichtbar, wenn das Projekt Teile hat.
- `JobIn.part_id` (optional). `measurement_table(project_id, part_id=None)` bekommt die Spalten „Teil“ und „Nennmaß“. Mit `part_id`: nur Messungen dieses Teils und Messungen ohne Teil; dazu der Text „Modelliert wird nur Teil T2 „Platte“ (montiertes Teil). Umriss in der Draufsicht (mm): …“. Ohne `part_id`, aber mit Teilen: „Teile im Foto: T1 Quader (Grundkörper), T2 Platte (montiert). Alle Teile als ein Körper modellieren.“
- Die Übersicht „Grundlage für das Modell“ zeigt nur die Maße, die wirklich übergeben werden.

## 6. Texte ohne Claude

Oberfläche (Nutzerseiten) neutral, intern bleibt `source = 'claude'` und die CSS-Klassen:

| Stelle | Neu |
|---|---|
| Schritt 1 | Button „Prompt herunterladen (PROMPT.md)“ entfällt, ebenso `GET /api/prompt.md` und `PROMPT.md` im Docker-Image (bleibt im Repo) |
| Kopfzeile | Badge „Claude verbunden · Modell“ entfällt; Warnungen „KI nicht eingerichtet“, „Testmodus (AI_FAKE)“, „Sandbox offline“ bleiben |
| Navigation | „CAD mit Claude“ → „CAD-Modell“ |
| Anmelde-/Einrichtungsseite | „Bauteile per Foto vermessen · CAD mit Claude“ → „Bauteile per Foto vermessen und als CAD-Modell nachbauen“; „verbinde Claude“ → „verbinde die KI“; „2 · Claude verbinden“ → „2 · KI verbinden“ |
| CAD-Seite | Überschrift „CAD-Modell erzeugen“; Einleitung „Aus Maßen und Fotos entsteht ein parametrisches build123d-Modell. …“; „trifft Claude“ → „trifft die KI“; „Wird an Claude gesendet“ → „Grundlage für das Modell“; Hinweis „Fotos, Maße und Beschreibung werden an die Anthropic-API übertragen.“ entfällt; „Claude arbeitet dann nur …“ → „Das Modell entsteht dann nur aus Maßen und Beschreibung.“; Tab „Claude-Antwort“ → „KI-Antwort“; „Annahmen von Claude“ → „Annahmen der KI“ |
| Messen | „Claude vorschlagen“ → „KI-Vorschläge“; „Claude analysiert …“ → „KI analysiert …“; „Vorschläge von Claude“ → „KI-Vorschläge“; Herkunft-Chip „Claude“ → „KI“; „Claude: Begründung“ → „KI: Begründung“; Toasts entsprechend |
| Verwaltung | „Claude-Modell“ → „KI-Modell“; „Maßvorschläge und CAD mit Claude sind deaktiviert“ → „KI-Funktionen sind deaktiviert“; „Anthropic-API-Schlüssel“ und Console-Link bleiben |
| Fehlermeldungen an Nutzer | „Anthropic-Ratenlimit erreicht“ → „KI-Dienst: Ratenlimit erreicht“; „Anthropic-API-Fehler …“ → „KI-Dienst: Fehler …“; „Keine Verbindung zur Anthropic-API.“ → „Keine Verbindung zum KI-Dienst.“ (Prüfmeldungen beim Hinterlegen des Schlüssels in der Verwaltung dürfen Anthropic nennen) |
| Downloads | CSV-Spalte „Quelle“ zeigt „KI“ statt `claude`; im ZIP heißt der Schlüssel `ki` statt `claude` |

## 7. Datenmodell und API

**Datenbank** (`db.py`):

```sql
CREATE TABLE IF NOT EXISTS parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, label TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'body',
  data TEXT NOT NULL,              -- {"polygon", "hidden", "holes", "dropped", "warn", "note"}
  source TEXT NOT NULL DEFAULT 'auto',   -- auto | ki | user
  scale REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL
);
```

Migration beim Start: fehlt `measurements.part_id`, wird `ALTER TABLE measurements ADD COLUMN part_id INTEGER REFERENCES parts(id) ON DELETE SET NULL` ausgeführt.

**Endpunkte** (alle mit Eigentümerprüfung wie bei Messungen):

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/api/photos/{phid}/edges` | Body `{use_ai: true}`. Erkennung + Zuordnung, ersetzt die Teile des Fotos. Antwort `{parts, segments, notice}` |
| GET | `/api/photos/{phid}/edges.json` | gespeichertes `EdgeResult` |
| POST | `/api/projects/{pid}/parts` | Teil von Hand: `{photo_id, label, role, polygon}` |
| PATCH | `/api/parts/{id}` | `{label?, role?, polygon?, reset_scale?}` |
| DELETE | `/api/parts/{id}` | Auto-Maße ohne Messschieber-Wert löschen, mit Wert → `source = 'user'`; übrige Messungen `part_id = NULL` |
| PATCH | `/api/measurements/{mid}` | neu: `part_id` (Zahl oder `null` = keins, `-1` = automatisch), `ref` (bool) |

`GET /api/projects/{pid}` liefert zusätzlich `parts`. Polygone: 3–64 Punkte, endliche Zahlen, innerhalb der Rasterfläche ± 10 mm. Erkennung nur für Fotos mit `rect.jpg`, sonst 400. Nichts erkannt → 422 „Kein Objekt erkannt – Teil von Hand zeichnen.“

**Grenzen:** Ein Erkennungslauf mit KI zählt zum bestehenden Tageslimit von 30 KI-Vorschlägen (Audit-Aktionen `suggest` und `edges_ai`). Höchstens ein Erkennungslauf gleichzeitig pro Prozess (Semaphore), um die NAS-CPU zu schonen; ein zweiter wartet.

## 8. Tests

- `tests/test_edges.py`: synthetische Draufsicht (gerenderte Unterlage, darauf gezeichnet: grauer Quader 60 × 40 mm; Variante mit überlappender Platte 80 × 20 mm und Bohrung Ø 5 mm), über `synthetic_photo` verzerrt und wieder entzerrt. Erwartung: Umriss-Ecken ± 0,5 mm, Bohrung ± 0,3 mm, Innenkante der Platte als Segment gefunden.
- `tests/test_parts.py`: Rechteckerkennung und Auto-Maße, Einrasten (Treffer, verdeckte Kante, Fallback), Zuordnung Messung → Teil bei Überlappung, Maßstab (eine Referenz → Breite 42,4 → 40,0; zwei widersprüchliche → Warnung; Verhältnis 1,4 → keine Referenz), Nennmaß, `dropped`.
- `tests/test_api.py`: Ablauf im Testmodus – Foto hochladen, Kanten erkennen, Teil bearbeiten, Messschieber setzen, Werte prüfen, Teil löschen, CAD-Auftrag mit `part_id` (Maßtabelle enthält nur das Teil), `/api/prompt.md` liefert 404.
- Docker-Smoke-Test (`tests/docker/smoke_api.py`) ruft die Kantenerkennung einmal auf.

## 9. Auslieferung

Branch `kanten-und-teile` → CI grün → Merge nach `main` → CI auf `main` grün (inkl. Image auf ghcr.io) → auf der DS918+ in `/volume1/docker/snap2cad` `docker compose pull && docker compose up -d` (eigene Compose-Datei, nicht die aus dem Repo) → Gesundheit prüfen.
