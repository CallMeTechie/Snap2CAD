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
| A1 | Synthetische Draufsicht und Unteransicht eines L-förmigen Teils 60 × 40 mm (Schenkel 15 mm) mit einer Bohrung; Unteransicht in jeder der vier Lagen `rot` ∈ {0, 90, 180, 270} mit Versatz ≥ 20 mm erzeugt: `vision.align_bottom` liefert genau dieses `rot`, IoU ≥ 0,9, `iou − iou_next ≥ 0,2`, `unsure=false`; die Bohrungsmitte der Unteransicht landet nach `parts.to_top` ± 0,5 mm auf der Draufsicht-Position. Die Unteransicht entsteht mit `bottom_of(objects, rot, dx, dy)` = Umkehrung von `lage_matrix(rot, dx, dy, W, H)` auf die Draufsicht-Objekte. Festwert: `vision.lage_matrix(90, 0, 0, 190, 230)` bildet (10, 20) auf (190, 200) ab, mit `dx=−30, dy=5` auf (160, 205); `bottom_warp` bildet bei p=10 das Pixel (100, 2100) auf (1900, 300) ab ± 1 px. Rechteck 60 × 40 mm ohne Merkmale in Lage 0 → `unsure=true`, `rot ∈ {0, 180}`; dasselbe quer (Lage 90) → `unsure=true`, `rot ∈ {90, 270}` | `pytest tests/test_align.py -v` |
| A2 | Kantenerkennung: Quader 60 × 40 mm (Grau 150) mit Schlagschatten (Papier 20 % dunkler, 8 mm breit, an zwei Seiten, Raster sichtbar) → genau ein Umriss mit 4 Ecken, jede Ecke ± 0,5 mm. Halbtransparenter Quader (`synthetic_photo`-Objekt `{"rect": [...], "gray": 200, "alpha": 0.5}`: Pixel = 0,5 · 200 + 0,5 · Blatt, Raster scheint mit halbem Kontrast durch) mit `hints={"transparent": 2}` → ein Umriss, Ecken ± 1,0 mm | `pytest tests/test_edges.py -k "schatten or transparent" -v` |
| A3 | `POST /api/projects/{pid}/cad-check` im Testmodus → `items` mit zwei Punkten (`height` block, `bottom` warn) und `material`; Werkstück-Felder werden gesetzt, von Hand gesetzte Felder (`material_user=1`) nicht überschrieben; zweiter Aufruf ohne Änderung liefert das gespeicherte Ergebnis ohne KI-Aufruf; Tageslimit → 429 bei neuem Hash, 200 mit gespeichertem Ergebnis bei gleichem Hash | `pytest tests/test_check.py -v` |
| A4 | Auftragsnachricht: gekipptes Foto geht als verkleinertes Original (`small.jpg`) mit Beschriftung „Schrägansicht“, Draufsicht als `rect.jpg`, Unteransicht als `rect_top.jpg` mit Hinweis „gespiegelt auf Draufsicht-Koordinaten“; höchstens 6 Bilder in der Reihenfolge Draufsicht, Unteransicht, Höhenlehre, Schrägfotos; bei „Alle Teile“ steht je Teil das Polygon in mm; die Prüfpunkte stehen im Auftragstext; Zeile „Fotografiertes Original“ vorhanden | `pytest tests/test_edges_api.py tests/test_check.py -k "auftrag or nachricht" -v` |
| A5 | Maßtabelle: Punkte einer Messung mit `view=bottom` (auch Auto-Maße eines Unteransicht-Teils) erscheinen in Draufsicht-Koordinaten mit Vermerk „(unten)“; Einzelteil-Auftrag für T1 enthält die Maße des verknüpften Unteransicht-Teils | `pytest tests/test_check.py -k tabelle -v` |
| A6 | Migration: alte Datenbank (Schema vor dieser Stufe) startet, `projects` hat danach `color, material, transparent, finish, material_user, cad_check`; ein zweiter Start ändert nichts | `pytest tests/test_parts_api.py -k migration_werkstueck -v` |
| A7 | Bestehende Tests grün, Node-Tests grün | CI |
| A8 | Manuell auf der DS918+ mit dem Kühlkörperblock: Unteransicht hochladen, Ausrichtung prüfen, Prüfkasten zeigt „Höhe unbekannt“, Auftrag mit erkanntem Umriss. Derselbe Auftrag wird dreimal gestartet; je Lauf notiert: Fasen x/2, Stufen x/2, Bohrungen x/12 (kein Stopp-Kriterium) | Browser |
| A9 | `ai.call` übergibt **keinen** `temperature`-Wert (geändert bei der Abnahme am 15.10.2026: Claude Opus 5.5 und Sonnet 5.5 lehnen jeden Wert außer dem Standard mit 400 ab, das Python-SDK ≥ 1.0 kennt den Parameter nicht mehr; die Streuung lässt sich nur über Ausgabeformat und Beispiele verringern – Folgearbeit); `CAD_SYSTEM` enthält die neue Regel 8 („… ist verbindlich“) und Regel 9 („durchscheinende Strukturen … Innenbohrungen“). A9 prüft die Einstellung, nicht die Wirkung | `pytest tests/test_check.py -k "temperature or prompt" -v` |

## Entscheidungen des Nutzers (15.10.2026)

- Alle vier Bausteine (Unteransicht, Rückfragen, Material, Textur) sind gewollt; Schnitt in zwei Stufen, Textur in Stufe B.
- Rückfrage als **Prüfung vor dem Auftrag** (nicht als anhaltender Auftrag).
- Unteransicht: **Umriss-Abgleich mit Wahl zum Korrigieren** (vier Lagen, Überlagerung, Handwahl).
- Material: **KI schätzt, der Nutzer korrigiert**; Handeingaben überschreibt die KI nicht.
- Textur (Stufe B): Foto-Projektion auf Ober- und Unterseite, Vorschau im Viewer, GLB-Download.
- Nach dem Preflight: Unteransicht-Teile werden **automatisch über die Überlappung** mit Draufsicht-Teilen verknüpft; Materialhinweise erreichen die Kantenerkennung über die **Handeingabe vor dem Erkennen** (KI-Schätzung erst in der Prüfung); die Prüfung läuft **automatisch, sobald sie veraltet ist**; eine neue KI-Schätzung **ersetzt** eine frühere KI-Schätzung (Handeingaben bleiben geschützt).

## Nicht im Umfang

- Textur und GLB (Stufe B).
- Automatische Zuordnung „Bohrung unten = Bohrung oben“ als Maßregel; das macht die KI anhand der überlagerten Koordinaten.
- Höhen aus Schrägfotos; die Höhenlehre und manuelle Maße bleiben der Weg.
- Ein anhaltender Auftrag mit Rückfragen während des Laufs.
- Materialschätzung beim Hochladen oder in der Teile-Zuordnung (Vormerkung).

## Begriffe

- **Draufsicht** (`top`): Teil liegt auf der Unterlage, Foto von oben, entzerrt auf `rect.jpg`, Ursprung unten links, mm.
- **Unteransicht** (`bottom`): Teil liegt umgedreht auf der Unterlage, Foto von oben, entzerrt wie die Draufsicht. `rect.jpg` zeigt, was die Kamera sah (nicht gespiegelt).
- **Lage:** Wie das umgedrehte Teil auf der Unterlage liegt. Umdrehen spiegelt immer; danach kann das Teil gedreht liegen. Vier Lagen `rot` ∈ {0, 90, 180, 270}: Punkt (x, y) der Unteransicht in mm wird an der senkrechten Mittellinie der Unteransicht gespiegelt (x → W − x, W = `rect.w_mm` der Unteransicht), dann um `rot` Grad gegen den Uhrzeigersinn (y nach oben) um deren Bildmitte (W/2, H/2) gedreht, dann um (dx, dy) verschoben. `rot` ist der Winkel, um den das seitlich umgedrehte Teil von oben gesehen gegen den Uhrzeigersinn gedreht liegt; nach vorn umgedreht entspricht `rot + 180`. Eine Spiegelung an der waagrechten Linie ist dasselbe wie `rot=180` und wird nicht getrennt geführt. Alle Lage-Berechnungen nutzen **eine** Funktion `vision.lage_matrix(rot, dx, dy, w_mm, h_mm) -> np.ndarray (3×3)` = `Verschiebung(dx, dy) · Drehung(rot, um (w/2, h/2), gegen den Uhrzeigersinn) · Spiegelung(x → w − x)`.
- **Draufsicht-Koordinaten der Unteransicht:** `parts.to_top(photo, x, y)` wendet `lage_matrix` an; es liest `w_mm`, `h_mm` aus `photo.analysis.rect` und die Lage aus `photo.analysis.bottom_align`. `T` bezeichnet diese Abbildung.
- **Referenz-Draufsicht:** das Foto des Projekts mit `view='top'`, vorhandenem `rect.jpg` und `status IN ('gut', 'brauchbar')` mit kleinster `id`.
- **Prüfpunkt:** Ergebnis der Prüfung vor dem Auftrag: `kind`, `text`, `severity` (`block` = das Modell wird ohne diese Angabe geraten, `warn` = Genauigkeit leidet).
- **Werkstück:** Farbe, Material, Transparenz (0 nein, 1 teilweise, 2 ja), Oberfläche (`matt`/`glaenzend`) des fotografierten Teils, am Projekt. In der Oberfläche heißt es „Werkstück“, im KI-Text „Fotografiertes Original“, damit es nicht mit dem Fertigungsmaterial (`JobIn.material`, „Fertigung: …, Material: PETG“) verwechselt wird.

## 1. Unteransicht (`core/vision.py`, `web/app/main.py`, `web/app/parts.py`, `web/static/js/photos.js`, `measure.js`)

- `VIEWS` (main.py) bekommt `bottom`; `VIEW_LABEL.bottom = "Von unten"`. Beim Hochladen gibt es neu eine Ansichtswahl (bisher sendet photos.js fest `top`), in „Fotos prüfen“ steht `bottom` im vorhandenen `<select>`. Entzerrung, Marker-Prüfung und Höhenlehre laufen wie bisher (`_analyze_store`).
- **Umriss je Foto:** `_analyze_store` rechnet einmal `edges.detect(rect, fmt, hints)` mit den Projekt-Hinweisen (§3) und speichert den größten Umriss als `analysis.outline_mm` (Polygon in mm) und den Kontrastwert `analysis.contrast` (§3). Fehlt `outline_mm` (ältere Fotos), berechnet die Ausrichtung ihn nach: `edges.detect` unter `_detect_lock`, blockierend mit Zeitlimit 30 s; bei Zeitüberschreitung `bottom_align: null`, `align_note` „Ausrichtung nicht berechnet – erneut versuchen“; `PATCH bottom_align: null` stößt sie erneut an.
- **Ausrichtung** (`vision.align_bottom(top_outline, bottom_outline, bot_w, bot_h, rot=None) -> dict`, shapely lokal importiert, weil `core/` ohne das Web-Image genutzt wird): `align_bottom`, `parts.to_top` und `vision.bottom_warp` rufen `lage_matrix` auf (keine shapely-Voreinstellung `origin='center'`). Für jede Lage (bei `rot` gesetzt nur diese) wird `lage_matrix(rot, 0, 0, bot_w, bot_h)` auf das Unteransicht-Polygon angewandt, `dx, dy` = Schwerpunkt(Draufsicht) − Schwerpunkt(abgebildet), IoU berechnet. Rückgabe `{"rot": 0|90|180|270, "dx": float, "dy": float, "iou": float, "iou_next": float, "unsure": bool}`; `iou_next` = beste IoU der übrigen drei Lagen (auch bei vorgegebenem `rot`). `auto` und `top_photo_id` ergänzt der Aufrufer in main.py.
- **Pixelabbildung** (`vision.bottom_warp(rect_bot, analysis_bot, analysis_top=None, pxmm_out=PX_PER_MM)`): `M = S_top · lage_matrix(…) · S_bot⁻¹` (3×3 homogen, an `cv2.warpAffine` die oberen zwei Zeilen) mit `S(p, H) = [[p, 0, 0], [0, −p, H·p], [0, 0, 1]]` wie in `rectify_mat`; `S_bot` mit `p = rect.pxmm`, `H = rect.h_mm` der Unteransicht, `S_top` mit `p = pxmm_out`, `H = rect.h_mm` der Referenz-Draufsicht; Zielgröße `(int(w_mm·pxmm_out), int(h_mm·pxmm_out))` der Referenz, Randfarbe wie `rectify_mat`. `rect_top.jpg` mit `pxmm_out = 10`, `align.jpg` mit `4`. Ohne `bottom_align` oder ohne Referenz: `rot=0, dx=dy=0`, Ziel = eigenes Raster (reine Links-rechts-Spiegelung).
- **Wann:** Neu berechnet wird (a) eine Unteransicht nach Hochladen, nach Formatwechsel und nach Umschalten auf `bottom`; (b) jede Unteransicht, wenn sich die Referenz-Draufsicht ändert (Hochladen, Umschalten von oder auf `top`, Formatwechsel, Löschen der Draufsicht). Bei Handwahl (`auto=false`) bleibt `rot`, nur `dx, dy, iou, iou_next, top_photo_id` werden neu berechnet. Wird eine Unteransicht auf eine andere Ansicht umgeschaltet, entfällt `bottom_align`. Ohne Referenz oder ohne Umriss: `bottom_align: null`, `align_note` „Draufsicht fehlt“ bzw. „Umriss nicht erkennbar“; eine Handwahl bleibt in `analysis.bottom_rot_user` erhalten und gilt wieder, sobald eine Referenz da ist. Ergebnis in `photos.analysis.bottom_align`.
- **Unsicher:** IoU < 0,6 **oder** `iou − iou_next < 0,05` (symmetrischer Umriss) → `unsure = true`; es bleibt die Lage mit der größten IoU (bei Gleichstand die kleinste `rot`), Versatz aus den Schwerpunkten. `rot=0` ohne Versatz nur, wenn kein Umriss vorliegt. Die Oberfläche zeigt „Ausrichtung unsicher – bitte prüfen“.
- **Handwahl:** `PATCH /api/photos/{phid}` mit `bottom_align: {"rot": 0|90|180|270}` setzt `bottom_rot_user`; danach `align_bottom(…, rot=bottom_rot_user)` → `dx, dy, iou, iou_next` (beste der übrigen drei), `auto=false`, `unsure=false`. Ohne Referenz: 200, `bottom_align: null`, `bottom_rot_user` gespeichert. Maßgeblich ist immer `bottom_rot_user`; `auto = bottom_rot_user is None`. Eine spätere automatische Ausrichtung überschreibt `auto=false` nicht. `bottom_align: null` setzt auf automatisch zurück und löscht `bottom_rot_user`; `bottom_align: {}` berechnet mit unveränderter Handwahl neu (z. B. nach einer Zeitüberschreitung). Wird eine Unteransicht auf eine andere Ansicht umgeschaltet, bleibt `bottom_rot_user` für ein Zurückschalten erhalten.
- **Überlagerungsbild** `GET /api/photos/{phid}/align.jpg`: Unteransicht per `bottom_warp` in Draufsicht-Koordinaten (4 px/mm), darüber der Draufsicht-Umriss in Orange und der eigene Umriss in Blau. Wird bei jedem Abruf erzeugt (keine Datei), `Cache-Control: no-store`. Die Route wird **vor** `/api/photos/{phid}/{kind}.jpg` registriert, weil deren Whitelist sonst 404 liefert.
- **Oberfläche „Fotos prüfen“:** Detailansicht einer Unteransicht zeigt `align.jpg`, darunter vier Schaltflächen „seitlich umgedreht“ (0), „nach vorn umgedreht“ (180), „seitlich umgedreht, ¼ gegen den Uhrzeigersinn gedreht“ (90), „seitlich umgedreht, ¼ im Uhrzeigersinn gedreht“ (270), mit Markierung der aktiven Lage, dazu „Überlappung 87 %“. Ohne Draufsicht: Hinweis statt Bild.
- **Messen:** Die Messseite listet Unteransichten als eigene Quellen (`sources` mit `view="bottom"`, Label „… · Von unten“; bisher wird jedes Foto mit `rect` als `top` eingetragen). Gemessen wird im Bild; `data.view = "bottom"` (Server erlaubt `top|gauge|bottom`, `default_unc(photo, "bottom")` wie `top`). Kanten erkennen, Teile, Auto-Maße, Maßstab: wie bei `top`; `parts._sync_auto` schreibt als `view` die Ansicht des Fotos (`top` oder `bottom`); in `refresh` gilt überall `view in ("top", "bottom")` statt `== "top"`. Zuordnung und Maßstab bleiben je Foto getrennt (Teile hängen am Foto). Teile einer Unteransicht tragen in der Seitenleiste den Zusatz „unten“.
- **Verknüpfung der Teile:** Nach jeder Ausrichtung und nach jeder Teileänderung setzt `parts.link_bottom(project)` an jedem Unteransicht-Teil `data.same_as` = id des Draufsicht-Teils (Referenz-Draufsicht) mit der größten IoU ≥ 0,5 nach `to_top` (`match_parts`), sonst `null`; ohne `bottom_align` überall `null` (keine Verknüpfung über die reine Spiegelung). `part_public` liefert `same_as`; die Seitenleiste zeigt „= T1“. `measurement_table(project_id, part_id)` nimmt bei einem Einzelteil-Auftrag auch Messungen der Teile mit `same_as == part_id` mit.
- **Koordinaten für KI und Tabelle:** Maßtabelle (§2) und CSV zeigen Punkte einer `bottom`-Messung über `parts.to_top` mit „(unten)“ vor den Punkten. Ohne `bottom_align` wendet `to_top` die Lage `rot=0, dx=dy=0` an (nur Spiegelung, passend zu `rect_top.jpg`), Vermerk „(unten, nicht ausgerichtet, links-rechts gespiegelt)“. `to_top` dient nur der Anzeige und der KI: Messwerte (`geom.compute`, Auto-Maße, Maßstab) werden auf den Rohpunkten der Unteransicht berechnet, weil `fx`/`fy` an die Achsen der Unterlage gebunden sind.
- `/suggest` nimmt als Bild nur Fotos mit `view='top'`.

## 2. Prüfung vor dem Auftrag, Schrägfotos, verbindlicher Umriss (`web/app/jobs.py`, `web/app/ai.py`, `web/static/js/cad.js`)

### 2.1 Prüfung

- `POST /api/projects/{pid}/cad-check` mit `{"photo_ids": [...] | null, "part_id": int | null, "force": false}`. Nachricht = `build_initial_message(project, "", {"photo_ids": …, "part_id": …, "for_check": True})`, also ohne Wunschtext, Fertigungsverfahren, Fertigungsmaterial, Toleranz, Passungen und Zusatzwünsche. `photo_ids` und `part_id` werden in `cad_check` gespeichert; das Formular behandelt eine Prüfung mit anderer Auswahl als veraltet. Bei `for_check` steht die Zeile „Fotografiertes Original“ nur bei `material_user=1` in der Nachricht (wie im Hash), damit die KI nicht auf ihre eigene frühere Schätzung hin schätzt. Je Projekt eine Sperre um den KI-Aufruf: eine zweite gleichzeitige Prüfung desselben Projekts wartet nicht, sondern bekommt 409 „Prüfung läuft bereits“; das Formular wiederholt nach 3 s ohne `force` und erhält dann das gespeicherte Ergebnis.
- **Idempotent:** Stimmt der neu berechnete `hash` mit `cad_check.hash` überein und ist `force` falsch, liefert der Endpunkt das gespeicherte Ergebnis ohne KI-Aufruf und ohne Audit. „Erneut prüfen“ sendet `force: true`.
- **Reihenfolge:** Hash berechnen → Treffer und nicht `force` → gespeichertes Ergebnis (200, auch bei erreichtem Limit) → Limit prüfen (429) → Audit → KI-Aufruf.
- **Tageslimit:** `_ai_uses_today` zählt künftig `action IN ('suggest', 'edges_ai', 'cad_check')`; das Audit `cad_check` wird vor dem KI-Aufruf geschrieben (wie bei `suggest`). 429 beim Limit (Admins ausgenommen, wie bisher), 503 ohne KI.
- Eingabe an die KI (`ai.CHECK_SYSTEM`); Antwort als JSON:
  ```json
  {"items": [{"kind": "height", "severity": "block", "text": "Höhe des Grundkörpers unbekannt – Höhenlehre fotografieren oder Höhe als Maß eingeben."}],
   "material": {"color": "silber", "material": "Aluminium", "transparent": 1, "finish": "matt", "note": "Block halbdurchsichtig, Platte metallisch"}}
  ```
  `kind` ∈ `height, bottom, photo, measure, sharpness, other`; `severity` ∈ `block, warn`; höchstens 8 Punkte, Texte ≤ 200 Zeichen. `ai.parse_check` liest defensiv (wie `parse_parts`): unbekannte `kind` → `other`, fehlende `severity` → `warn`, Nicht-Strings verworfen, `transparent` nur 0–2, `finish` nur aus der Liste.
- **Hash:** SHA-256 über die kanonische JSON-Darstellung (`sort_keys=True`, Floats auf 0,01 gerundet) von: den **aufgelösten** Foto-IDs (`photo_ids: null` = alle Fotos des Projekts zum Zeitpunkt der Berechnung) mit `view`, `format`, `status`, `bottom_align.rot/dx/dy`; allen akzeptierten Messungen des Projekts (`id, kind, value, caliper, unc, part_id, data.view, data.points`); Teilen (`id, label, role, polygon, hidden, holes, same_as`); `part_id`; den Werkstück-Feldern **nur bei `material_user=1`** (sonst würde die Prüfung sich durch ihre eigene Schätzung veralten). Berechnet vor dem KI-Aufruf; `GET /api/projects/{pid}` berechnet ihn für die gespeicherte Auswahl neu und liefert `cad_check.stale`.
- Ergebnis mit `hash`, `checked_at`, `photo_ids`, `part_id`, `images` (gewählte Bildliste nach §2.2) in `projects.cad_check` (JSON-Text); `_project_public` liefert es aufbereitet mit `stale`.
- **Materialschätzung:** Bei `material_user=0` werden alle vier Werkstück-Felder durch die Schätzung ersetzt; fehlende oder ungültige Einzelwerte werden `NULL`; fehlt `material` in der Antwort ganz, bleiben die Felder unverändert. Bei `material_user=1` bleiben sie unverändert. `note` hat keine eigene Spalte; sie steht nur in `cad_check.material.note`.
- Testmodus (`_fake`, neuer Zweig für `CHECK_SYSTEM`): feste Antwort mit `height` (block), `bottom` (warn) und Material „Aluminium, silber, transparent 0, matt“.

### 2.2 Bilder und Text im Auftrag (`build_initial_message`, auch für die Prüfung)

- Ein **Bild** ist ein Bildverweis in der Nachricht. Je Foto: `top` → `rect.jpg` (Gruppe Draufsichten); `bottom` → `rect_top.jpg` (Gruppe Unteransichten); jedes Foto mit `gauge.jpg`, gleich welcher Ansicht → `gauge.jpg` (Gruppe Höhenlehren); `tilted`/`overview` → `small.jpg` (Gruppe Schrägfotos). Das `rect.jpg` von `gauge`-, `tilted`- und `overview`-Fotos geht nicht mehr mit (bisher ging es für jedes Foto mit, Grenze 4). Gruppen in dieser Reihenfolge, innerhalb nach Foto-`id`; nach dem 6. Bild ist Schluss. Die Regel steht einmal in `jobs.pick_images(project_id, photo_ids)`; die Prüfung liefert die gewählte Liste als `cad_check.images`.
- `top`: Beschriftung wie bisher. `bottom`: `rect_top.jpg` wird bei jedem Aufbau der Nachricht (Auftrag und Prüfung) per `bottom_warp` aus `rect.jpg` und `bottom_align` neu geschrieben (kein Zwischenspeicher; ein `warpAffine` dauert Millisekunden, ein veralteter Cache kostet ein falsches Modell); Beschriftung „Foto N (von unten), entzerrt und gespiegelt auf Draufsicht-Koordinaten – Bohrungen von unten und oben liegen übereinander“. Ohne Ausrichtung: `rect_top.jpg` = `rect.jpg` an der senkrechten Mittellinie gespiegelt (Lage `rot=0` ohne Versatz), Beschriftung „(von unten, nicht ausgerichtet, links-rechts gespiegelt)“.
- `tilted`/`overview`: `small.jpg` = `orig.jpg` verkleinert (längste Seite `MAX_IMG_SIDE`), beim ersten Aufbau einer Nachricht erzeugt (hängt nur am unveränderten `orig.jpg`); `rect_top.jpg` und `small.jpg` werden über eine temporäre Datei und `os.replace` geschrieben, weil ein laufender Auftrag sie in jeder Korrekturrunde liest. Beschriftung „Foto N, Schrägansicht – nicht entzerrt, kein Maßstab; nur für Form, Seitenflächen und Höhenverhältnis“. (`_materialize` decodiert Bilder bei jedem Aufruf neu, auch in jeder Selbstkorrektur-Runde; `orig.jpg` kann 8000 px groß sein.)
- `gauge.jpg` wie bisher.
- Neue Textzeilen vor „## Messwerte“: `Fotografiertes Original (nicht das Fertigungsmaterial): <Farbe>, <Material>, transparent: <nein/teilweise/ja>, <Oberfläche>` (nur gesetzte Felder) und, wenn Prüfpunkte mitgegeben sind, „## Offene Punkte der Prüfung“ mit je einer Zeile `- [block] …`.
- **`check_items`:** Alle Punkte der zuletzt angezeigten Prüfung (block und warn) gehen mit, auch wenn die Prüfung veraltet ist; ohne Prüfergebnis `check_items: []`. Validierung: `CheckItem(kind: Literal["height","bottom","photo","measure","sharpness","other"], severity: Literal["block","warn"], text: str = Field(max_length=200))`, `JobIn.check_items: list[CheckItem] = Field(default=[], max_length=8)`.
- **Verbindlicher Umriss:** `parts.cad_text` ohne `part_id` liefert je Teil: `T1 „Quader“ (Grundkörper, Draufsicht): Umriss (mm) (x, y) …; verdeckte Kanten: K3–K4; Bohrungen: Ø 5,0 bei (x, y)` (bisher nur die Namensliste; der bestehende Test auf „Teile im Foto: …“ wird angepasst). Teile einer Unteransicht: „(von unten, in Draufsicht-Koordinaten; derselbe Körper wie T1, kein zusätzliches Teil)“ bei `same_as`, sonst „(von unten, in Draufsicht-Koordinaten)“; Polygon und Bohrungen über `to_top`.
- Im Formular zeigt „Grundlage für das Modell“ die Bilder aus `cad_check.images` in der Reihenfolge, Schrägfotos mit „Original“ markiert; ergeben die gewählten Fotos mehr als 6 Bilder → „Nur die ersten 6 Bilder gehen mit“.

### 2.3 Prompt (`ai.CAD_SYSTEM`)

- Eingaben: Unteransicht („gespiegelt auf Draufsicht-Koordinaten“), Schrägansichten („ohne Maßstab“), Zeile „Fotografiertes Original“, offene Punkte.
- Regel 8 wird ersetzt: „Der Umriss aus der Draufsicht (Teile-Polygone) ist verbindlich: Fasen, Stufen, Absätze und Bohrungen daraus nachbilden. Fehlt ein Maß (z. B. die Höhe einer Stufe), schätze es, kennzeichne es als Annahme und nenne es in `check_before_manufacturing`. Weglassen ist nur erlaubt, was kleiner als 0,5 mm ist. Laufzeit unter 60 Sekunden.“ (Keine Ausweichklausel bei Widerspruch zwischen Foto und Polygon: genau solche Klauseln haben das Weglassen verursacht; der Nutzer sieht die Teile in der Seitenleiste und korrigiert sie dort.)
- Neue Regel 9: „Bei transparenten oder teiltransparenten Teilen sind durchscheinende Strukturen Innenbohrungen oder Innenkonturen, keine Rillen oder Nuten der Oberfläche. Bohrungen von unten und oben an derselben Stelle sind in der Regel ein Loch (ggf. Stufenloch).“
- Offene Punkte: „Zu jedem offenen Punkt steht in `assumptions`, was angenommen wurde.“
- `ai.call` übergibt keinen `temperature`-Wert (ursprünglich war `0.0` für CAD-Auftrag und Prüfung vorgesehen; die 5.5-Modelle lehnen den Parameter ab, siehe A9).

### 2.4 Oberfläche (`cad.js`)

- Kasten „Vor dem Modellieren“ über dem Startknopf: Punkte mit Symbol (block rot, warn gelb), Materialzeile, Zeitpunkt, Knopf „Erneut prüfen“ (`force: true`). Beim Öffnen des Formulars und bei Änderung der Fotoauswahl oder des Teils läuft die Prüfung automatisch, wenn `cad_check` fehlt oder `stale` ist (durch die Idempotenz entstehen Kosten nur bei echten Änderungen). Während der Prüfung: Spinner im Kasten, Startknopf bleibt bedienbar.
- Mit `block`-Punkten heißt der Startknopf „Trotzdem erzeugen“; die Punkte gehen als `check_items` mit.
- Fehler oder 429: Meldung im Kasten („Prüfung nicht möglich: …“), Start bleibt möglich, `check_items: []`.

## 3. Material und Kontrast (`core/edges.py`, `web/app/main.py`, `web/static/js/photos.js`, `measure.js`)

- **Felder** (`projects`): `color TEXT`, `material TEXT`, `transparent INTEGER` (0/1/2), `finish TEXT` (`matt`/`glaenzend`), `material_user INTEGER DEFAULT 0`. `PATCH /api/projects/{pid}` nimmt sie an (Texte ≤ 40 Zeichen, `transparent` 0–2, `finish` aus der Liste) und setzt `material_user=1`; `clear_material: true` leert alles und setzt `material_user=0`.
- **Oberfläche „Fotos prüfen“:** Kasten „Werkstück“ über der Fotoliste mit vier Feldern und dem Hinweis „von der KI geschätzt“ bzw. „von Hand gesetzt · Zurücksetzen“, dazu der Satz „Vor „Kanten erkennen“ setzen – die Erkennung nutzt diese Angaben“.
- **Kantenerkennung** (`edges.detect(rect, fmt, hints=None)`, `hints = {"transparent": 0|1|2, "light": bool}`; `light` kommt nur aus dem Projekt: wahr, wenn `color` (kleingeschrieben) in `LIGHT_COLORS = {"weiß", "weiss", "silber", "hellgrau", "beige", "natur"}` liegt; keine Ableitung aus der Kontrastmessung):
  - *Schatten* (nur bei `transparent = 0`): In der Objektmaske zählt ein Bereich nur dann als Objekt, wenn er dunkler/andersfarbig ist **und** das feine Rasterkriterium (2-mm-Fenster) nicht „sicher Papier“ meldet (`GRID_PAPER`); das Veto gilt nur für reine Helligkeitsunterschiede (Farbabstand < 6). Liefert die Maske ohne Hinweise kein Objekt, wird sie einmal ohne Normierung und Veto wiederholt (Verhalten vor dieser Stufe), damit halbtransparente Teile ohne Hinweis nicht schlechter erkannt werden. Das Rasterkriterium wird dafür auf dunklerem Papier normiert (lokale Helligkeit), weil die Rasterenergie im Schatten knapp über der Schwelle liegt (gemessen 0,62 bei Schwelle 0,6).
  - *transparent = 2:* Rasterkriterium abgeschaltet (`nogrid` und `sure_bg` leer); Farbmaske mit Schwelle `max(th, TRANSP_MIN_DIFF)`, `TRANSP_MIN_DIFF = 9` (halbe Untergrenze 18 aus `_mask`); danach `MORPH_CLOSE` mit 3-mm-Kern, `_fill_unround`, größte Komponente; die Seiten legt wie bisher `_refine` an die Gradienten. Reicht das für A2 nicht, wird ein Schritt „äußere Kantenkette“ im Plan eigens spezifiziert. *transparent = 1:* Rasterkriterium mit halbem Gewicht.
  - *light:* Farbabstand-Schwelle 60 % der Standardschwelle, Rastergewicht erhöht.
  - Alle Schwellen als Konstanten mit Kommentar; Gegenprobe mit den vier echten Fotos im Scratchpad (nicht im Repo) und den synthetischen Fotos (A2).
- **Veraltete Kanten:** `hints` werden nur aus Feldern mit `material_user=1` gebildet; KI-Schätzungen ändern `hints` nicht und lösen „Werkstück geändert“ nicht aus. Ändert eine Handeingabe die Hinweise, werden `outline_mm` und die Ausrichtung der Unteransichten neu berechnet (`analysis.outline_hints`). `edges.json` speichert die verwendeten `hints`; weichen die aktuellen Projekt-Hinweise davon ab, zeigt die Messseite beim Foto „Werkstück geändert – Kanten neu erkennen“ (keine automatische Neuerkennung).
- **Kontrastmessung:** `detect(...)["contrast"]` (mittlerer Farbabstand Objekt/Papier aus der Maske, auf 0–100 skaliert, `None` ohne Umriss), aus demselben `detect`-Lauf in `_analyze_store` (§1, nur für Draufsicht und Unteransicht, unter `_detect_lock`), in `analysis.contrast`; `_photo_public` liefert `contrast` und `low_contrast` (< 12). „Fotos prüfen“ zeigt „Geringer Kontrast zur Unterlage“ mit Tipps: Licht seitlich, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen.
- **An die KI:** Zeile „Fotografiertes Original“ (§2.2) auch in der Teile-Zuordnung (`PARTS_SYSTEM`-Aufruf), dort mit dem Hinweis zu durchscheinenden Strukturen.

## 4. Datenmodell und API

- Migration in `db.py` (wie `part_id`): `ALTER TABLE projects ADD COLUMN …` für `color, material, transparent, finish, material_user, cad_check`.
- `photos.analysis`: `outline_mm`, `contrast`, `bottom_align`, `bottom_rot_user`. Dateien im Fotoordner: zusätzlich `small.jpg`, `rect_top.jpg` (atomar geschrieben; `rect_top.jpg` bei jedem Aufbau neu). `photos.analysis` zusätzlich `outline_hints` (Hinweise, mit denen `outline_mm` entstand) und `edges_hints` (Hinweise des letzten „Kanten erkennen“); `_photo_public` liefert `edges_stale` (Vergleich `edges_hints` gegen die aktuellen Hinweise) und `bottom_rot_user`.
- `GET /api/projects/{pid}`: zusätzlich `color, material, transparent, finish, material_user, cad_check` (aufbereitet, mit `stale`); Fotos mit `bottom_align, align_note, contrast, low_contrast`; Teile mit `same_as`.
- `POST /api/projects/{pid}/cad-check` (§2.1); `PATCH /api/photos/{phid}` mit `bottom_align`; `GET /api/photos/{phid}/align.jpg` (vor der `{kind}.jpg`-Route); `POST /api/jobs` mit `check_items`.
- `POST /api/projects/{pid}/measurements`: `view` erlaubt `bottom`.
- `_ai_uses_today` zählt `cad_check` mit.
- Hinweis: `jobs.messages` speichern Bildpfade; spätere Änderungswünsche (`iterate`) lesen die aktuelle Datei. Bei `rect_top.jpg` und `small.jpg` gilt das wie heute bei `rect.jpg` (keine Änderung in dieser Stufe).

## 5. Fehlerfälle

- Unteransicht ohne Draufsicht: messbar, `bottom_align: null`, Hinweis; im Auftrag links-rechts gespiegelt mit Vermerk.
- Umriss nicht erkennbar: `rot=0` ohne Versatz, `align_note`. IoU < 0,6 oder Lagen kaum unterscheidbar: beste Lage, `unsure`, Handwahl.
- Referenz-Draufsicht gelöscht oder umgeschaltet: nächste brauchbare Draufsicht wird Referenz (§1 „Wann“); gibt es keine, `bottom_align: null` mit „Draufsicht fehlt“.
- Draufsicht wird später hochgeladen oder gewechselt: alle `auto`-Ausrichtungen neu berechnet; Handwahlen behalten `rot`.
- Formatwechsel einer Unteransicht: `rot` einer Handwahl wird in die neue Analyse übernommen (`auto=false` bleibt), `dx, dy, iou` werden neu berechnet (heute ersetzt `photo_patch` die Analyse vollständig).
- Ausrichtung nicht berechnet (Zeitlimit): `align_note`, erneut anstoßbar.
- Prüfung fehlgeschlagen, Tageslimit, kein Schlüssel: Kasten zeigt Meldung, Start möglich, `check_items` leer.
- `check_items` älter als der Projektstand: werden trotzdem übernommen (sie sind nur Text für die KI).
- Mehr als 6 Bilder: erste 6 nach Reihenfolge, Hinweis im Formular.

## 6. Tests

- `tests/conftest.py`: `synthetic_photo` bekommt `shadow` (Breite mm, Seiten, Dunkelfaktor) und für Objekte `alpha` (0–1, Raster scheint durch) sowie `polygon` (L-Form). Eine Hilfsfunktion `bottom_of(objects, rot)` spiegelt und dreht Objekte für die Unteransicht.
- `tests/test_align.py`: A1 (vier Lagen, Punktprobe), `unsure` bei Rechteck und bei zwei verschiedenen Teilen, Handwahl über die API, Neuberechnung bei Draufsicht-Wechsel und -Löschung, Handwahl nach Formatwechsel, `align.jpg` 200, `same_as`.
- `tests/test_edges.py`: A2 (Schatten, transparent, hell), Kontrastwert, `hints` in `edges.json`.
- `tests/test_check.py`: A3, A4, A5, A9; `parse_check` defensiv; `hash`/`stale`/Idempotenz; Testmodus-Antwort; Werkstück-Felder, `material_user`, Ersetzen der KI-Schätzung; `pick_images`; `/suggest` nur Draufsicht.
- `tests/test_parts_api.py`: A6 (`test_migration_werkstueck`), `bottom` in `refresh` und `_sync_auto`.
- Browser-Durchlauf (Playwright im Scratchpad): Unteransicht hochladen, Lage wechseln, Werkstück setzen, Prüfkasten, „Trotzdem erzeugen“.

## 7. Auslieferung

Umsetzung in drei Wellen in einem Plan, je mit grüner CI auf dem Branch: W1 Unteransicht, Ausrichtung, Verknüpfung, Messen und Tabelle (A1, A5); W2 Prüfung, Werkstück-Felder, Auftragsnachricht, Prompt, Temperatur (A3, A4, A6, A9); W3 Kantenerkennung mit Hinweisen und Kontrast (A2). Danach: Branch `unteransicht-pruefung-material` → CI grün → Merge nach `main` → CI auf `main` grün (Image auf ghcr.io) → DS918+: Sicherung des Volumes, `docker compose pull && up -d` (eigene Compose-Datei) → Gesundheit prüfen → A8 mit dem Kühlkörperblock.
