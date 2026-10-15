# Unteransicht, Prüfung vor dem Auftrag, Material und Kontrast – Design (Stufe A)

Stand: 15.10.2026 · Branch `unteransicht-pruefung-material`

## Ziel

Die CAD-KI soll ein fotografiertes Teil vollständig nachbilden, statt sichtbare Merkmale wegzulassen oder zu raten. Auslöser: Ein halbdurchsichtiger Kühlkörperblock mit aufgeschraubter Platte (Fasen an zwei Ecken, Stufen an der Gegenseite, 12 Innenbohrungen 12 mm unten / 4,5 mm oben) wurde dreimal mit derselben Eingabe modelliert – einmal mit Fasen und Absatz, einmal nur mit Fasen, einmal als glatter Quader. In allen drei Antworten schrieb die KI, sie habe Fasen, Stufen und „Längsnuten“ weggelassen. Die „Nuten“ waren durchscheinende Innenbohrungen.

Vier Lücken, die diese Stufe schließt:

1. **Unteransicht:** Es gibt keine Fotoart „von unten“. Die Unterseite (Bohrungen, Stufenlöcher) ist für die KI unsichtbar.
2. **Raten statt fragen:** Fehlen Höhe, Unterseite oder eine scharfe Kante, nimmt die KI stillschweigend Werte an. Künftig prüft Snap2CAD vor dem Auftrag, was fehlt, und fordert es an. Schrägfotos gehen im Original mit, nicht als verzerrte Entzerrung. Erkannte Umrisse (Fasen, Stufen) sind für die KI verbindlich.
3. **Material und Kontrast:** Farbe, Material und Transparenz des Werkstücks sind unbekannt. Die Kantenerkennung hält Schlagschatten für Objekt und durchscheinendes Raster für Papier; die KI hält Innenbohrungen für Rillen.
4. **Streuung:** Gleiche Eingaben liefern verschieden vollständige Modelle.

Stufe B (eigene Spec): Textur aus den Fotos auf das Modell, GLB-Export.

## Abnahmekriterien

| Nr. | Kriterium | Nachweis |
|---|---|---|
| A1 | Synthetische Draufsicht und Unteransicht eines L-förmigen Teils 60 × 40 mm (Schenkel 15 mm), Unteransicht in jeder der vier Kipp-Lagen erzeugt: `vision.align_bottom` liefert `flip` und `rot` der erzeugten Lage, IoU ≥ 0,9, Versatz ± 0,5 mm | `pytest tests/test_align.py -v` |
| A2 | Kantenerkennung: Quader 60 × 40 mm mit Schlagschatten (Papier 20 % dunkler, 8 mm breit, an zwei Seiten, Raster sichtbar) → genau ein Umriss mit 4 Ecken, jede Ecke ± 0,5 mm. Halbtransparenter Quader (Raster durchscheinend mit 50 % Kontrast, Farbabstand gering) mit Hinweis `transparent=2` → ein Umriss, Ecken ± 1,0 mm | `pytest tests/test_edges.py -k "schatten or transparent"` |
| A3 | `POST /api/projects/{pid}/cad-check` im Testmodus → `items` mit zwei Punkten (`height` block, `bottom` warn) und `material`; Felder am Projekt werden gefüllt, von Hand gesetzte Felder (`material_user=1`) nicht überschrieben; Tageslimit → 429 | `pytest tests/test_check.py -v` |
| A4 | Auftragsnachricht: gekipptes Foto geht als `orig.jpg` mit Beschriftung „Schrägansicht“, Draufsicht und Unteransicht als `rect.jpg`; Unteransicht mit Hinweis „gespiegelt auf Draufsicht-Koordinaten“; höchstens 6 Bilder in der Reihenfolge Draufsicht, Unteransicht, Höhenlehre, Schrägfotos; bei „Alle Teile“ steht je Teil das Polygon in mm; offene Prüfpunkte stehen im Auftragstext; Werkstück-Zeile vorhanden | `pytest tests/test_edges_api.py -k auftrag tests/test_check.py -k nachricht` |
| A5 | Maßtabelle: Punkte einer Messung mit `view=bottom` erscheinen in Draufsicht-Koordinaten mit Vermerk „(unten)“ | `pytest tests/test_check.py -k tabelle` |
| A6 | Migration: alte Datenbank ohne die neuen Spalten startet, `projects` hat `color, material, transparent, finish, material_user, cad_check` | `pytest tests/test_parts_api.py -k migration` |
| A7 | Bestehende Tests grün, Node-Tests grün | CI |
| A8 | Manuell auf der DS918+ mit dem Kühlkörperblock: Unteransicht hochladen, Ausrichtung prüfen, Prüfkasten zeigt „Höhe unbekannt“, Auftrag mit erkanntem Umriss → Modell hat beide Fasen und beide Stufen (kein Stopp-Kriterium, Ergebnis wird notiert) | Browser |

## Entscheidungen des Nutzers (15.10.2026)

- Alle vier Bausteine (Unteransicht, Rückfragen, Material, Textur) sind gewollt; Schnitt in zwei Stufen, Textur in Stufe B.
- Rückfrage als **Prüfung vor dem Auftrag** (nicht als anhaltender Auftrag).
- Unteransicht: **Umriss-Abgleich mit Wahl zum Korrigieren** (vier Kipp-Lagen, Überlagerung, Handwahl).
- Material: **KI schätzt, der Nutzer korrigiert**; Handeingaben überschreibt die KI nicht.
- Textur (Stufe B): Foto-Projektion auf Ober- und Unterseite, Vorschau im Viewer, GLB-Download.

## Nicht im Umfang

- Textur und GLB (Stufe B).
- Automatische Zuordnung „Bohrung unten = Bohrung oben“ als Maßregel; das macht die KI anhand der überlagerten Koordinaten.
- Höhen aus Schrägfotos; die Höhenlehre und manuelle Maße bleiben der Weg.
- Ein anhaltender Auftrag mit Rückfragen während des Laufs.

## Begriffe

- **Draufsicht** (`top`): Teil liegt auf der Unterlage, Foto von oben, entzerrt auf `rect.jpg`, Ursprung unten links, mm.
- **Unteransicht** (`bottom`): Teil liegt umgedreht auf der Unterlage, Foto von oben, entzerrt wie die Draufsicht. `rect.jpg` zeigt, was die Kamera sah (nicht gespiegelt).
- **Kipp-Lage:** Wie das Teil umgedreht wurde. Vier Möglichkeiten: um die x-Achse gekippt (`flip="x"`: y wird gespiegelt) oder um die y-Achse (`flip="y"`: x wird gespiegelt), jeweils zusätzlich um 180° gedreht (`rot=0|180`).
- **Draufsicht-Koordinaten der Unteransicht:** Punkt `(x, y)` der Unteransicht → `T(x, y)` in der Draufsicht, mit Spiegelung, Drehung und Versatz `(dx, dy)` aus der Ausrichtung.
- **Prüfpunkt:** Ergebnis der Prüfung vor dem Auftrag: `kind`, `text`, `severity` (`block` = das Modell wird ohne diese Angabe geraten, `warn` = Genauigkeit leidet).
- **Werkstück:** Farbe, Material, Transparenz (0 nein, 1 teilweise, 2 ja), Oberfläche (`matt`/`glaenzend`) des fotografierten Teils, am Projekt.

## 1. Unteransicht (`core/vision.py`, `web/app/main.py`, `web/static/js/photos.js`)

- `VIEWS` bekommt `bottom`; `VIEW_LABEL.bottom = "Von unten"`. Beim Hochladen und in „Fotos prüfen“ wählbar. Entzerrung, Marker-Prüfung und Höhenlehre laufen wie bisher (`_analyze_store`).
- **Ausrichtung** (`vision.align_bottom(top_outline, bottom_outline, w_mm, h_mm) -> dict`): Eingabe sind die größten Umrisse (`core.edges.detect` ohne KI) der Draufsicht und der Unteransicht als Polygone in mm. Für jede der vier Kipp-Lagen wird das Unteransicht-Polygon transformiert (Spiegelung an der Bildmitte, Drehung um 180° um die Bildmitte), auf den Schwerpunkt des Draufsicht-Polygons verschoben und die IoU (shapely) berechnet. Rückgabe `{"flip": "x"|"y", "rot": 0|180, "dx": float, "dy": float, "iou": float, "auto": true}`. `dx, dy` ist der Versatz nach Spiegelung/Drehung, der die Schwerpunkte zur Deckung bringt.
- **Wann:** nach `_analyze_store` einer Unteransicht, wenn das Projekt eine brauchbare Draufsicht hat (erste nach `id`); außerdem beim Hochladen oder Umschalten einer Draufsicht für alle Unteransichten des Projekts, deren Ausrichtung `auto` ist. Ergebnis in `photos.analysis.bottom_align`. Ohne Draufsicht oder ohne Umriss: kein Eintrag, Hinweis „Draufsicht fehlt“ bzw. „Umriss nicht erkennbar“ in `_photo_public` (`bottom_align: null`, `align_note`).
- **Unsicher:** IoU < 0,6 → `bottom_align.unsure = true`, Standardlage `flip="x", rot=0`, Versatz aus den Schwerpunkten. Die Oberfläche zeigt „Ausrichtung unsicher – bitte prüfen“.
- **Handwahl:** `PATCH /api/photos/{phid}` mit `bottom_align: {"flip": "x"|"y", "rot": 0|180}` → `dx, dy` werden für diese Lage neu berechnet, `auto=false`, `unsure=false`. Eine spätere automatische Ausrichtung überschreibt `auto=false` nicht. `bottom_align: null` setzt auf automatisch zurück.
- **Überlagerungsbild** `GET /api/photos/{phid}/align.jpg`: Unteransicht transformiert in Draufsicht-Koordinaten (mit `cv2.warpAffine`, 4 px/mm), darüber der Draufsicht-Umriss in Orange und der eigene Umriss in Blau. Wird bei jedem Abruf erzeugt (keine Datei), `Cache-Control: no-store`.
- **Oberfläche „Fotos prüfen“:** Detailansicht einer Unteransicht zeigt `align.jpg`, darunter vier Schaltflächen „um lange Kante“, „um kurze Kante“, jeweils „gedreht“, mit Markierung der aktiven Lage, dazu IoU als „Überlappung 87 %“. Ohne Draufsicht: Hinweis statt Bild.
- **Messen:** Die Messseite listet Unteransichten wie Draufsichten (`sources` mit `view="bottom"`, Label „… · Von unten“). Gemessen wird im Bild; `data.view = "bottom"` (Server erlaubt `top|gauge|bottom`). Kanten erkennen, Teile, Auto-Maße, Maßstab: wie bei `top`; `parts.refresh` behandelt `bottom` wie `top`, aber Zuordnung und Maßstab bleiben je Foto getrennt (Teile hängen am Foto). Teile einer Unteransicht tragen in der Seitenleiste und im CAD-Text den Zusatz „unten“.
- **Koordinaten für KI und Tabelle:** `parts.to_top(photo, x, y)` wendet `bottom_align` an. Maßtabelle (§2 Auftrag) und CSV zeigen Punkte einer `bottom`-Messung in Draufsicht-Koordinaten mit „(unten)“ vor den Punkten; ist keine Ausrichtung vorhanden, bleiben die Rohkoordinaten mit „(unten, nicht ausgerichtet)“.

## 2. Prüfung vor dem Auftrag, Schrägfotos, verbindlicher Umriss (`web/app/jobs.py`, `web/app/ai.py`, `web/static/js/cad.js`)

### 2.1 Prüfung

- `POST /api/projects/{pid}/cad-check` mit `{"photo_ids": [...]}`. Zählt zum Tageslimit (`_ai_uses_today`, Audit `cad_check`), 429 beim Limit, 503 ohne KI.
- Eingabe an die KI (`ai.CHECK_SYSTEM`): dieselbe Nachricht wie der Auftrag (Maßtabelle, Teile, Fotos nach §2.2, Werkstück-Zeile), ohne Wunschtext. Antwort als JSON:
  ```json
  {"items": [{"kind": "height", "severity": "block", "text": "Höhe des Grundkörpers unbekannt – Höhenlehre fotografieren oder Höhe als Maß eingeben."}],
   "material": {"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt", "note": "Block halbdurchsichtig, Platte metallisch"}}
  ```
  `kind` ∈ `height, bottom, photo, measure, sharpness, other`; `severity` ∈ `block, warn`; höchstens 8 Punkte, Texte ≤ 200 Zeichen. `ai.parse_check` liest defensiv (wie `parse_parts`): unbekannte `kind` → `other`, fehlende `severity` → `warn`, Nicht-Strings verworfen.
- Ergebnis wird mit `hash` (SHA-256 über Foto-IDs mit `view`/`format`/`bottom_align`, Messungen (id, value, caliper, part_id), Teile (id, polygon), Werkstück-Felder) und `checked_at` in `projects.cad_check` gespeichert und im `GET /api/projects/{pid}` als `cad_check` geliefert.
- Materialschätzung: füllt leere Werkstück-Felder; bei `material_user=1` nur `note` aktualisieren.
- Testmodus: feste Antwort mit `height` (block), `bottom` (warn) und Material „Aluminium, silber, transparent 0, matt“.

### 2.2 Bilder und Text im Auftrag (`build_initial_message`, auch für die Prüfung)

- Reihenfolge: Draufsichten, Unteransichten, Höhenlehren, dann Schrägfotos (`tilted`, `overview`); höchstens **6** Bilder. Innerhalb einer Gruppe nach `id`.
- `top`: `rect.jpg`, Beschriftung wie bisher. `bottom`: `rect.jpg` **transformiert** in Draufsicht-Koordinaten (warpAffine nach `bottom_align`, Datei `rect_top.jpg` im Fotoordner, beim Ändern der Ausrichtung neu erzeugt), Beschriftung „Foto N (von unten), entzerrt und gespiegelt auf Draufsicht-Koordinaten – Bohrungen von unten und oben liegen übereinander“. Ohne Ausrichtung: `rect.jpg` mit Beschriftung „(von unten, nicht ausgerichtet, x gespiegelt)“ und gespiegeltem Bild.
- `tilted`/`overview`: `orig.jpg` verkleinert (längste Seite `MAX_IMG_SIDE`, Datei `small.jpg`), Beschriftung „Foto N, Schrägansicht – nicht entzerrt, kein Maßstab; nur für Form, Seitenflächen und Höhenverhältnis“. Die Entzerrung dieser Fotos wird nicht mehr geschickt.
- `gauge.jpg` wie bisher.
- Neue Textzeilen vor „## Messwerte“: `Werkstück: <Farbe>, <Material>, <transparent: nein/teilweise/ja>, <Oberfläche>` (nur gesetzte Felder) und, wenn Prüfpunkte offen sind, „## Offene Punkte der Prüfung“ mit je einer Zeile `- [block] …`. Die Punkte kommen aus `JobIn.check_items` (Liste wie oben, Pydantic-validiert, ≤ 8).
- **Verbindlicher Umriss:** `parts.cad_text` ohne `part_id` liefert je Teil: `T1 „Quader“ (Grundkörper, Draufsicht): Umriss (mm) (x, y) …; verdeckte Kanten: K3–K4; Bohrungen: Ø 5,0 bei (x, y)`. Teile einer Unteransicht: „(von unten, in Draufsicht-Koordinaten)“.
- Im Formular zeigt „Grundlage für das Modell“ die 6 gewählten Bilder in der Reihenfolge und markiert Schrägfotos mit „Original“; mehr als 6 gewählt → Hinweis „Nur die ersten 6 gehen mit“.

### 2.3 Prompt (`ai.CAD_SYSTEM`)

- Eingaben: Unteransicht („gespiegelt auf Draufsicht-Koordinaten“), Schrägansichten („ohne Maßstab“), Werkstück-Zeile, offene Punkte.
- Regel 8 wird ersetzt: „Der Umriss aus der Draufsicht (Teile-Polygone) ist verbindlich: Fasen, Stufen, Absätze und Bohrungen daraus nachbilden. Fehlt ein Maß (z. B. die Höhe einer Stufe), schätze es, kennzeichne es als Annahme und nenne es in `check_before_manufacturing`. Weglassen ist nur erlaubt, was kleiner als 0,5 mm ist. Laufzeit unter 60 Sekunden.“
- Neue Regel 9: „Bei transparenten oder teiltransparenten Teilen sind durchscheinende Strukturen Innenbohrungen oder Innenkonturen, keine Rillen oder Nuten der Oberfläche. Bohrungen von unten und oben an derselben Stelle sind in der Regel ein Loch (ggf. Stufenloch).“
- Offene Punkte: „Zu jedem offenen Punkt steht in `assumptions`, was angenommen wurde.“
- `ai.call` bekommt `temperature: float | None = None`; CAD- und Prüf-Aufrufe nutzen `0.0`.

### 2.4 Oberfläche (`cad.js`)

- Kasten „Vor dem Modellieren“ über dem Startknopf: Punkte mit Symbol (block rot, warn gelb), Materialzeile, Zeitpunkt, Knopf „Erneut prüfen“. Beim Öffnen des Formulars läuft die Prüfung automatisch, wenn `cad_check` fehlt oder sein `hash` nicht zum aktuellen Projektstand passt (der Server liefert `cad_check.stale`). Während der Prüfung: Spinner im Kasten, Startknopf bleibt bedienbar.
- Mit `block`-Punkten heißt der Startknopf „Trotzdem erzeugen“; die offenen Punkte gehen als `check_items` mit.
- Fehler oder 429: Meldung im Kasten („Prüfung nicht möglich: …“), Start bleibt möglich.

## 3. Material und Kontrast (`core/edges.py`, `web/app/main.py`, `web/static/js/photos.js`)

- **Felder** (`projects`): `color TEXT`, `material TEXT`, `transparent INTEGER` (0/1/2), `finish TEXT` (`matt`/`glaenzend`), `material_user INTEGER DEFAULT 0`. `PATCH /api/projects/{pid}` nimmt sie an (Texte ≤ 40 Zeichen, `transparent` 0–2, `finish` aus der Liste) und setzt `material_user=1`; `clear_material: true` leert alles und setzt `material_user=0`.
- **Oberfläche „Fotos prüfen“:** Kasten „Werkstück“ über der Fotoliste mit vier Feldern und dem Hinweis „von der KI geschätzt“ bzw. „von Hand gesetzt · Zurücksetzen“.
- **Kantenerkennung** (`edges.detect(rect, fmt, hints=None)`, `hints = {"transparent": 0|1|2, "light": bool}`; `light` = Werkstück heller als 70 % des Papierwerts, aus `color`/Schätzung, Standard aus der Kontrastmessung):
  - *Schatten:* In der Objektmaske zählt ein Bereich nur dann als Objekt, wenn er dunkler/andersfarbig ist **und** das Rasterkriterium nicht „sicher Papier“ meldet (`GRID_PAPER`). Schlagschatten (Raster sichtbar) fällt damit heraus. Das Rasterkriterium wird dafür auf dunklerem Papier normiert (lokale Helligkeit).
  - *transparent = 2:* Rasterkriterium abgeschaltet (es scheint durch); Maske aus Farb-/Helligkeitsabstand mit niedrigerer Schwelle und Schließen der Lücken über die äußeren LSD-Kanten (Objektgrenze = längste geschlossene Kantenkette). *transparent = 1:* Rasterkriterium mit halbem Gewicht.
  - *light:* Farbabstand-Schwelle 60 % der Standardschwelle, Rastergewicht erhöht.
  - Alle Schwellen als Konstanten mit Kommentar; Gegenprobe mit den vier echten Fotos im Scratchpad (nicht im Repo) und den synthetischen Fotos (A2).
- **Kontrastmessung:** `edges.contrast(rect, fmt) -> float` (mittlerer Lab-Abstand Objekt/Papier aus der Maske, 0–100). Bei `_analyze_store` in `analysis.contrast`; `_photo_public` liefert `contrast` und `low_contrast` (< 12). „Fotos prüfen“ zeigt „Geringer Kontrast zur Unterlage“ mit Tipps: Licht seitlich, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen.
- **An die KI:** Werkstück-Zeile (§2.2) auch in der Teile-Zuordnung (`PARTS_SYSTEM`-Aufruf), dort mit dem Hinweis zu durchscheinenden Strukturen.

## 4. Datenmodell und API

- Migration in `db.py` (wie `part_id`): `ALTER TABLE projects ADD COLUMN …` für `color, material, transparent, finish, material_user, cad_check`.
- `photos.analysis`: `bottom_align`, `contrast`. Dateien im Fotoordner: zusätzlich `small.jpg` (Schrägfoto verkleinert), `rect_top.jpg` (Unteransicht transformiert).
- `GET /api/projects/{pid}`: zusätzlich `color, material, transparent, finish, material_user, cad_check` (mit `stale`); Fotos mit `bottom_align, align_note, contrast, low_contrast`.
- `POST /api/projects/{pid}/cad-check` (§2.1); `PATCH /api/photos/{phid}` mit `bottom_align`; `GET /api/photos/{phid}/align.jpg`; `POST /api/jobs` mit `check_items`.
- `POST /api/projects/{pid}/measurements`: `view` erlaubt `bottom`; `default_unc` für `bottom` wie `top`.

## 5. Fehlerfälle

- Unteransicht ohne Draufsicht: messbar, `bottom_align: null`, Hinweis; im Auftrag gespiegelt mit Vermerk.
- Umriss nicht erkennbar oder IoU < 0,6: Standardlage, `unsure`, Handwahl.
- Draufsicht wird später hochgeladen oder gewechselt: alle `auto`-Ausrichtungen neu berechnet; Handwahlen bleiben.
- Prüfung fehlgeschlagen, Tageslimit, kein Schlüssel: Kasten zeigt Meldung, Start möglich, `check_items` leer.
- `check_items` älter als der Projektstand: werden trotzdem übernommen (sie sind nur Text für die KI).
- Mehr als 6 Bilder: erste 6 nach Reihenfolge, Hinweis im Formular.
- `rect_top.jpg` fehlt (Ausrichtung geändert, Datei noch nicht erzeugt): beim Aufbau der Nachricht erzeugen.

## 6. Tests

- `tests/conftest.py`: `synthetic_photo` bekommt `shadow` (Breite mm, Seiten, Dunkelfaktor) und für Objekte `alpha` (0–1, Raster scheint durch) sowie `polygon` (L-Form). Eine Hilfsfunktion `bottom_of(objects, flip, rot)` spiegelt Objekte für die Unteransicht.
- `tests/test_align.py`: A1 (vier Lagen), Ausrichtung mit Versatz, `unsure` bei zwei verschiedenen Teilen (IoU klein), Handwahl über die API, Neuberechnung beim Draufsicht-Wechsel, `align.jpg` 200.
- `tests/test_edges.py`: A2 (Schatten, transparent, hell), Kontrastwert.
- `tests/test_check.py`: A3, A4, A5; `parse_check` defensiv; `hash`/`stale`; Testmodus-Antwort; Material-Felder und `material_user`.
- `tests/test_parts_api.py`: A6 (Migration), `bottom` in `refresh`.
- Browser-Durchlauf (Playwright im Scratchpad): Unteransicht hochladen, Lage wechseln, Prüfkasten, „Trotzdem erzeugen“.

## 7. Auslieferung

Branch `unteransicht-pruefung-material` → CI grün → Merge nach `main` → CI auf `main` grün (Image auf ghcr.io) → DS918+: Sicherung des Volumes, `docker compose pull && up -d` (eigene Compose-Datei) → Gesundheit prüfen → A8 mit dem Kühlkörperblock.
