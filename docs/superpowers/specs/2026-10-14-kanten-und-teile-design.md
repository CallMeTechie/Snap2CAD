# Kanten, Teile und mitdenkende Bemaßung – Design

Stand: 14.10.2026 · Branch `kanten-und-teile`

## Ziel

Fotografierte Objekte sollen sich schneller und richtiger vermessen lassen:

1. Snap2CAD erkennt die Kanten eines Objekts auf der entzerrten Draufsicht selbst, zeichnet sie ein, und der Nutzer kann sie bearbeiten.
2. Snap2CAD erkennt, aus welchen Teilen ein Objekt besteht (Beispiel: Quader mit aufgeschraubter, seitlich überstehender Platte), und bemaßt jedes Teil für sich.
3. Korrigiert der Nutzer eine Länge (Messschieber-Wert), schließt Snap2CAD daraus auf den Maßstab des Teils und passt alle anderen Maße dieses Teils an. Diese Schlussfolgerung bleibt gespeichert.
4. Die Oberfläche nennt Claude nicht mehr beim Namen; der Button „Prompt herunterladen“ entfällt.

Erfolgskriterium (Beispiel aus dem Auftrag): Quader 60 × 40 × 30 mm, Draufsicht. Kanten werden erkannt, der Fotowert der Länge ist wegen Parallaxe z. B. 63,6 mm. Der Nutzer trägt bei der Länge 60,00 als Messschieber-Wert ein → die Breite springt von 42,4 auf 40,0 mm, ohne dass er sie anfasst. Bei Quader + Platte erscheinen zwei Teile mit je eigenen Kanten und Maßen.

## Abnahmekriterien

| Nr. | Kriterium | Nachweis |
|---|---|---|
| A1 | Synthetische A4-Draufsicht, Quader 60 × 40 mm: genau ein Umriss mit 4 Ecken, jede Ecke ± 0,5 mm. Variante Quader + Platte 80 × 20 mm (dunklerer Grauton als der Quader) + Bohrung Ø 5 mm in der Platte: Bohrung Mittelpunkt und Ø ± 0,3 mm; mindestens ein `inner`-Segment liegt auf einer Plattenkante über dem Quader (Winkel < 3°, Abstand < 1 mm) | `pytest tests/test_edges.py -v` |
| A2 | Teil-Maßstab: L Foto 63,60, Messschieber 60,00 → B Foto 42,40 wird 40,00 ± 0,01 ohne Änderung an B; zweite Referenz mit 1,5 % Abweichung → Warnung am Teil; Verhältnis 1,40 → keine Referenz, Hinweis an der Messung | `pytest tests/test_parts.py tests/test_parts_api.py -k "massstab or referenz"` |
| A3 | Zwei Teile: `ai.call` per Monkeypatch mit fester Antwort „Quader“ (body) + „Platte“ (mounted) → `POST /api/photos/{phid}/edges` liefert 2 Teile mit je eigenen Auto-Maßen; CAD-Auftrag mit `part_id` von T2 → Maßtabelle enthält keine Messung von T1 | `pytest tests/test_edges_api.py -k "zwei_teile or cad_auftrag"` |
| A4 | Erneute Erkennung erhält den Maßstab: nach Messschieber 60,00 an L und zweitem `POST …/edges` hat das Teil dieselbe id, k = 0,943 ± 0,001 und genau eine Messung „Länge“ | `pytest tests/test_edges_api.py -k erneute` |
| A5 | Oberfläche ohne „Claude“: kein Treffer für „Claude“ in `web/static` außerhalb von `//`-Kommentaren; „Anthropic“ nur in Einrichtung und Verwaltung (app.js); in `web/app/main.py`, `web/app/jobs.py` und `web/app/ai.py` nennt keine Nutzermeldung Claude oder Anthropic außer den Einrichtungs-/Verwaltungsmeldungen (`ai.verify`, „Bitte den Anthropic-API-Schlüssel eingeben.“) | `pytest tests/test_texts.py -v` (durchsucht die Dateien) |
| A6 | `GET /api/prompt.md` → 404 | `pytest tests/test_api.py -k mat_pdf`; Docker-Smoke-Test |
| A7 | Bestehende Tests grün | CI (`pytest -v`) |
| A8 | Manuell nach dem Deployment auf der DS918+: echtes Foto Quader + Platte → zwei Teile; Dauer eines Erkennungslaufs (A4, mit KI) wird notiert (kein Stopp-Kriterium) | Browser, Zeit aus dem Netzwerk-Tab |

## Entscheidungen des Nutzers (14.10.2026)

| Frage | Entscheidung |
|---|---|
| Erkennung | Hybrid: OpenCV findet Kanten pixelgenau, die KI ordnet sie Teilen zu |
| Schlussfolgerung | Maßstab pro Teil aus Referenzmaßen, dazu Geometrie-Regeln und Nennmaß-Hinweis; im Projekt gespeichert, rücknehmbar |
| CAD mit mehreren Teilen | Teil wählbar (oder alle als ein Körper wie heute); Prüfkette und Sandbox unverändert |
| Claude in der Oberfläche | Ganze App neutral („KI“); nur Einrichtung und Verwaltung nennen „Anthropic-API-Schlüssel“ und den Console-Link; README bleibt. Der Hinweis „… an die Anthropic-API übertragen“ entfällt ersatzlos (ausdrücklicher Wunsch) |
| Erneute Erkennung | Alte und neue Teile über die Überlappung abgleichen; wiedergefundene Teile behalten Nummer, Bezeichnung, Referenzen |
| Höhenmaße | Nie automatisch zugeordnet und nie skaliert; von Hand einem Teil zuordenbar |
| Tageslimit erreicht | Erkennung läuft ohne KI weiter, mit Hinweis |

## Nicht im Umfang

- Höhen aus der Draufsicht ableiten (Kameraabstand unbekannt). Höhen kommen weiter aus Höhenlehre, gekipptem Foto oder manueller Eingabe.
- Kantenerkennung auf der Höhenlehre.
- Projektübergreifendes Lernen.
- CAD als Baugruppe mit mehreren Körpern.

## Begriffe

- **Teil** (`T1`, `T2` …): ein Körper im Foto mit Bezeichnung, Rolle (`body` = Grundkörper, `mounted` = montiertes Teil) und einem geschlossenen Polygon in mm der Draufsicht. Teile dürfen sich überlappen (Platte liegt auf dem Quader).
- **Kante**: eine Seite eines Teil-Polygons mit fester Kennung (siehe §3). Eine Kante kann `hidden` sein (verdeckt/geschätzt, z. B. Quaderkante unter der Platte).
- **Kandidat**: eine von OpenCV gefundene Kante (Umrissseite oder gerades Segment im Objekt), noch keinem Teil zugeordnet.
- **Auto-Maß**: Messung, die Snap2CAD aus einem Teil-Polygon erzeugt (`source = 'auto'`).
- **Referenz**: Messung eines Teils mit Messschieber-Wert, die den Maßstab des Teils bestimmt.
- **Maßstab k** eines Teils: Median über alle Referenzen von `Messschieber-Wert / Fotowert`. Ohne Referenz ist k = 1.

## 1. Kantenerkennung (`core/edges.py`, ohne KI)

Eingabe: entzerrte Draufsicht `rect.jpg` (10 px/mm, deckt genau die Rasterfläche des Formats ab, Ursprung unten links) und das Format. Ausgabe in mm, gleiche Koordinaten wie die Messungen (x nach rechts, y nach oben).

Ablauf:

1. **Arbeitsbild** auf 4 px/mm verkleinern. Alle 8 Markerquadrate liegen innerhalb der Rasterfläche; sie werden aus `spec(fmt)` (`centers_mm`, `marker_size_mm`, plus 2 mm Rand) maskiert.
2. **Raster entfernen**: morphologisches Schließen je Farbkanal (BGR, Kern ≈ 1,5 mm) entfernt die dünnen blaugrauen Rasterlinien, Achsbeschriftungen und das Mittelkreuz.
3. **Papier vom Objekt trennen**: auf dem geschlossenen Bild Abstand jedes Pixels zur Papierfarbe in Lab (Helligkeitsabfall und Farbabweichung). Die Papierfarbe wird robust aus dem Randstreifen der Rasterfläche geschätzt (Median, Markerfelder ausgenommen). Schwelle per Otsu mit Untergrenze.
4. **Maske säubern**: Öffnen/Schließen, Komponenten unter 25 mm² verwerfen. Danach GrabCut nur im Begrenzungsrahmen der Maske plus 10 mm Rand (sicher Vordergrund innen, wahrscheinlich Hintergrund am Rand, 3 Iterationen); außerhalb bleibt die Maske unverändert.
5. **Umriss**: äußere Konturen (≥ 25 mm²) → `approxPolyDP` mit 0,8 mm Toleranz. Jede Polygonseite wird auf dem vollen Bild (10 px/mm) verfeinert: entlang der Normalen den stärksten Gradienten suchen und eine Gerade durch diese Punkte legen; benachbarte Geraden werden geschnitten → Eckpunkte. Weicht ein Eckpunkt mehr als 2 mm vom groben Polygon ab, bleibt der grobe Punkt.
6. **Bohrungen**: innere Konturen mit Kreisförmigkeit ≥ 0,85 und Ø ≥ 2 mm → Kreis (Mittelpunkt, Durchmesser) per Kleinste-Quadrate-Anpassung.
7. **Innenkanten**: `cv2.createLineSegmentDetector` auf dem Graubild (volle Auflösung) innerhalb der um 1,5 mm erodierten Maske (kein Canny davor), kollineare Stücke zusammenfassen (Winkel < 3°, Lücke < 2 mm), Länge ≥ 8 mm, höchstens 40 Segmente (längste zuerst).

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

**Einrasten** (`snap_polygon(polygon, segments, preferred)`): Für jede Polygonseite wird der passende Kandidat gesucht (Winkelabweichung < 6°, mittlerer Abstand der Kandidaten-Endpunkte zur Seite < 3 mm, Überlappung in Längsrichtung ≥ 30 % der Kandidatenlänge; bester = kleinster Abstand). Kandidaten, die die KI im Feld `edges` des Teils nennt (`preferred`), werden zuerst geprüft; nur ohne Treffer unter ihnen alle übrigen. Treffer → die Seite übernimmt die Gerade des Kandidaten. Kein Treffer → Seite bleibt, wird `hidden`. Neue Eckpunkte = Schnitt benachbarter Geraden; bei fast parallelen Geraden (< 10°) oder Verschiebung > 8 mm bleibt der KI-Punkt.

**Ohne KI** (kein Schlüssel, KI-Fehler, Tageslimit erreicht oder `use_ai = false`): jedes Umriss-Polygon wird ein Teil („Teil“, `body`), Innenkanten bleiben unzugeordnet und werden gestrichelt grau angezeigt. Bei KI-Fehler oder Tageslimit steht der Grund in `notice` („KI-Zuordnung fehlgeschlagen: … – Teile nur aus dem Umriss.“ bzw. „Tageslimit für KI erreicht (30) – Teile nur aus dem Umriss.“), die Teile aus dem Umriss entstehen trotzdem.

**Bohrungen** werden dem kleinsten Teil zugeordnet, dessen Polygon den Mittelpunkt enthält.

**Testmodus (`AI_FAKE`)**: liefert deterministisch ein Teil „Quader“ aus dem ersten Umriss der Kandidatenliste.

**Erneute Erkennung** desselben Fotos: Alte und neue Teile werden über die Überlappung abgeglichen (IoU der Polygone mit shapely ≥ 0,5, beste Paare zuerst, jedes Teil höchstens einmal). Ein wiedergefundenes Teil behält id, Nummer, Bezeichnung, Rolle und `dropped`; die neue Erkennung wirkt wie eine Polygonänderung (§3, Kanten-Kennungen werden übertragen). Nicht wiedergefundene alte Teile werden wie bei `DELETE /api/parts/{id}` entfernt, nicht zugeordnete neue Teile neu angelegt, solange das Foto dabei höchstens 12 Teile hat (Handteile mitgezählt); neue Teile darüber hinaus werden nicht angelegt und im Hinweis genannt.

## 3. Bemaßung und Schlussfolgerung (`web/app/parts.py`)

Eine zentrale Funktion `refresh(project_id)` hält alles konsistent und ersetzt `_recompute`. Aufgerufen von: `project_patch`, `meas_create`, `meas_patch`, `meas_delete`, `meas_accept_all`, allen Teil-Endpunkten, dem Erkennungs-Endpunkt und den Foto-Endpunkten (Formatwechsel, Löschen). Sie übernimmt die Regeln von `_recompute`: Messungen mit `source = 'manual'` oder `data.ai_value` werden nicht neu berechnet; nur `accepted = 1` wird zugeordnet und skaliert.

**Zuordnung Messung → Teil** (nur Draufsicht-Messungen mit Punkten auf demselben Foto, ohne `data.part_fixed`): Für jedes Teil zählt, wie viele Punkte auf seinem Rand liegen (≤ 1,5 mm) und ob alle Punkte innerhalb oder auf dem Rand liegen. Gewinner: meiste Randpunkte, bei Gleichstand das Teil mit der kleinsten Polygonfläche. Liegt nicht jeder Punkt in oder an einem Teil → keine Zuordnung. Höhenlehre-Messungen und manuelle Messungen werden nie automatisch zugeordnet. Der Nutzer legt die Zuordnung im Bearbeiten-Feld fest (`part_fixed = true`, auch „keins“); „automatisch“ hebt die Festlegung auf.

**Kanten-Kennungen** sind fest: Jede Polygonseite hat eine Kennung in `data.edge_ids` (fortlaufend je Teil, `data.next_edge_id`, wird nie neu vergeben). Punkt einfügen teilt eine Kante – die längere Hälfte behält die Kennung, die kürzere bekommt eine neue; Punkt löschen verschmilzt zwei Kanten zur Kennung der längeren. Bei einem ganz neuen Polygon (erneute Erkennung, PATCH mit anderer Punktzahl ohne erkennbares Einfügen/Löschen) übernimmt jede neue Kante die Kennung der nächstgelegenen alten Kante (Winkel < 6°, Mittelpunktabstand < 3 mm), sonst eine neue. Bohrungen haben ebenso feste Kennungen (Übernahme bei Mittelpunktabstand ≤ 2 mm).

**Auto-Maße** (je Teil, mit Schlüssel `data.auto_key`):

- Rechteck (4 Ecken, alle Innenwinkel 90° ± 4°): `L` Länge (längeres Seitenpaar, Mittelwert beider Seiten), `B` Breite. Unterscheiden sich gegenüberliegende Seiten um mehr als 1 mm, bekommt das Maß den Hinweis „gegenüberliegende Kanten ungleich – Kante prüfen“.
- Sonst: `E<Kennung>` je Kante; verdeckte Kanten bekommen den Hinweis „verdeckt, geschätzt“.
- Bohrungen: `H<Kennung>` als Durchmesser.
- Bezeichnung z. B. „Quader Länge“, „Platte Kante 3“, „Quader Bohrung 1“ (Zahl = Kennung, nicht Position).

Auto-Maße werden aus dem Polygon berechnet (Eckpunkte mit `fx`/`fy` wie in `geom.compute`), nie aus ihren Punkten. Punkte (nur für Anzeige und Auswahl): Länge/Breite/Kante = Endpunkte einer der Kanten; Bohrung = drei Punkte bei 0°, 120°, 240° auf dem Kreis. `unc` = `_default_unc(photo, 'top')`, `accepted = 1`. Ändert der Nutzer Punkte oder Wert eines Auto-Maßes per PATCH, wird es zu `source = 'user'` (bzw. `'manual'` bei Wert) und sein Schlüssel kommt in `data.dropped` des Teils.

Bei Änderung des Polygons werden Auto-Maße mit gleichem Schlüssel aktualisiert (Bezeichnung, Messschieber-Wert, kritisch, Passung, Notiz bleiben), fehlende ergänzt; überzählige ohne Messschieber-Wert gelöscht, überzählige mit Messschieber-Wert werden zu normalen Messungen (`source = 'user'`, Punkte bleiben) und behalten ihre Zuordnung. Löscht der Nutzer ein Auto-Maß, merkt sich das Teil den Schlüssel (`data.dropped`) und erzeugt es nicht neu.

**Maßstab k je Teil:**

- Referenzen = Messungen des Teils mit Messschieber-Wert, Art Länge/Durchmesser/Radius, `data.ref` nicht `false`. Verhältnis = Messschieber-Wert / Fotowert ohne Teil-Maßstab (aber mit Kontrollmaß-Faktoren).
- Verhältnis außerhalb 0,75–1,25 → diese Messung zählt nicht als Referenz, Hinweis „Abweichung zu groß – falsches Maß oder falsches Teil?“ in `data.warn` der Messung. Der Messschieber-Wert selbst bleibt gültig.
- k = Median der gültigen Verhältnisse. Ist (größtes − kleinstes Verhältnis) / k > 0,01 → Warnung am Teil (`data.warn`) „Referenzen widersprechen sich (…)“.
- Werte: Länge/Durchmesser/Radius des Teils = Fotowert × k. Winkel und Punktkoordinaten bleiben unverändert. Höhenmaße werden nie mit k skaliert, auch wenn sie von Hand einem Teil zugeordnet sind.
- `data.raw` speichert den Fotowert ohne k, damit die Anzeige „Foto 63,60 → 60,00 (× 0,943)“ möglich ist.
- „Maßstab zurücksetzen“ setzt `data.ref = false` bei allen Referenzen des Teils; Messschieber-Werte bleiben.

**Nennmaß-Hinweis:** für Längen und Durchmesser `nominal = round(v × 2) / 2`, wenn `|v − nominal| ≤ max(unc, 0,2)` (`unc` = Unsicherheit der Messung); bei Messschieber-Wert ist das Nennmaß der Messschieber-Wert. Gespeichert in `data.nominal`. Anzeige „≈ 60“, Übergabe an CAD.

**Gespeichert** wird die Schlussfolgerung in den Referenzmessungen selbst; k wird am Teil nur zwischengespeichert. Bei erneuter Erkennung bleiben wiedergefundene Teile samt Auto-Maßen und Referenzen erhalten (§2).

## 4. Oberfläche „Messen“ (`web/static/js/edges.js`, Anbindung in `measure.js`)

- Werkzeugleiste: Button **„Kanten erkennen“**. Vorhandene Teile auf diesem Foto → Rückfrage „Teile dieses Fotos werden neu erkannt. Wiedergefundene Teile behalten Bezeichnung und Messschieber-Referenzen.“ Während des Laufs Spinner im Button („Kanten werden erkannt …“). Ein `notice` aus der Antwort erscheint als Toast.
- Neues Werkzeug **„Kanten“** (Taste E): Teile werden farbig gezeichnet (eigene Palette, verschieden von Blau = Messung und Orange = KI-Vorschlag), verdeckte Kanten gestrichelt, unzugeordnete Kandidaten grau gestrichelt.
  - Eckpunkt ziehen (Kantenfang gilt), Griff „+“ an der Kantenmitte fügt einen Punkt ein, Eckpunkt anklicken und Entf löscht ihn (mindestens 3 bleiben).
  - Klick auf ein Teil wählt es aus. „Neues Teil“ in der Seitenleiste startet das Zeichnen: Punkte setzen, Klick auf den ersten Punkt oder Enter schließt, Esc bricht ab.
  - Tasten nur im Werkzeug „Kanten“: Entf/Backspace löscht den ausgewählten Eckpunkt (nicht die ausgewählte Messung), Enter schließt, Esc bricht ab. In allen anderen Werkzeugen bleibt die Belegung aus measure.js unverändert. Das „+“ an der Kantenmitte ist ein anklickbarer Griff; die Taste „+“ zoomt weiter.
  - Änderungen werden beim Loslassen gespeichert (PATCH), danach werden Teile und Messungen neu geladen.
- Seitenleiste, Bereich **„Teile“** über den Messungen: je Teil `T1`, Bezeichnung, Rolle, Kurzmaß („60,00 × 40,00 mm“ beim Rechteck, sonst „6 Kanten“), Maßstab-Chip „× 0,943 aus M3“ mit „Zurücksetzen“, Warnungen. Ausgewählt: Bezeichnung, Rolle, Löschen.
- Messungsliste: Chip `T1` bei zugeordneten Messungen, „≈ 60“ beim Nennmaß, bei skalierten Werten Titel „Foto 63,60 mm × 0,943“, Warnung aus `data.warn`. Herkunft „automatisch aus T1“ bei Auto-Maßen.
- Bearbeiten-Feld einer Messung: Auswahl „Teil“ (automatisch / T1 / T2 / keins; bei Höhen- und manuellen Maßen ohne „automatisch“), Kästchen „Als Referenz für T1“ (nur bei Messschieber-Wert und Teil), Hinweistext unter dem Messschieber-Feld „Wird zur Referenz für T1 – alle Maße des Teils werden angepasst“.
- Hinweisleiste beim Werkzeug: „Kanten: Eckpunkt ziehen · Griff + an der Kantenmitte = Punkt einfügen · Entf = Punkt löschen · Esc = abbrechen“.

## 5. CAD-Schritt

- Formular: Auswahl **„Modell für“** – „Alle Teile (ein Körper)“ (Standard) oder je Teil. Nur sichtbar, wenn das Projekt Teile hat.
- `JobIn.part_id` (optional, muss zum Projekt gehören). `measurement_table(project_id, part_id=None)` bekommt die Spalten „Teil“ und „Nennmaß“. Mit `part_id`: nur Messungen dieses Teils und Messungen ohne Teil; dazu der Text „Modelliert wird nur Teil T2 „Platte“ (montiertes Teil). Umriss in der Draufsicht (mm): …“. Ohne `part_id`, aber mit Teilen: „Teile im Foto: T1 Quader (Grundkörper), T2 Platte (montiert). Alle Teile als ein Körper modellieren.“
- Die Übersicht „Grundlage für das Modell“ zeigt nur die Maße, die wirklich übergeben werden.

## 6. Texte ohne Claude

Oberfläche (Nutzerseiten) neutral, intern bleibt `source = 'claude'` und die CSS-Klassen:

| Stelle | Neu |
|---|---|
| Schritt 1 | Button „Prompt herunterladen (PROMPT.md)“ (mat.js:40) entfällt, ebenso `GET /api/prompt.md` und `PROMPT.md` im Docker-Image (`COPY` im Dockerfile; bleibt im Repo) |
| Kopfzeile | Badge „Claude verbunden · Modell“ (app.js:69) entfällt; Warnungen „KI nicht eingerichtet“, „Testmodus (AI_FAKE)“, „Sandbox offline“ bleiben |
| Navigation | „CAD mit Claude“ (app.js:63) → „CAD-Modell“ |
| Anmelde-/Einrichtungsseite | „Bauteile per Foto vermessen · CAD mit Claude“ (app.js:229, 316) → „Bauteile per Foto vermessen und als CAD-Modell nachbauen“; „verbinde Claude“ (app.js:272) → „verbinde die KI“; „2 · Claude verbinden“ (app.js:281) → „2 · KI verbinden“ |
| CAD-Seite | Überschrift „CAD-Modell mit Claude“ (cad.js:74) → „CAD-Modell erzeugen“; Einleitung „Claude schreibt …“ (cad.js:75) → „Aus Maßen und Fotos entsteht ein parametrisches build123d-Modell. Der Code läuft abgeschottet auf dem Server und liefert STEP und STL.“; „trifft Claude“ (cad.js:94) → „trifft die KI“; „Wird an Claude gesendet“ (cad.js:107) → „Grundlage für das Modell“; Hinweis „Fotos, Maße und Beschreibung werden an die Anthropic-API übertragen.“ (cad.js:122) entfällt ersatzlos; „Claude arbeitet dann nur …“ (cad.js:65) → „Das Modell entsteht dann nur aus Maßen und Beschreibung.“; Tab „Claude-Antwort“ (cad.js:237) → „KI-Antwort“; „Annahmen von Claude“ (cad.js:281) → „Annahmen der KI“ |
| Auftragsprotokoll | jobs.py:306 „Claude erstellt das Modell …“ → „KI erstellt das Modell …“; „Claude korrigiert den Code …“ → „KI korrigiert den Code …“ |
| Messen | „Claude vorschlagen“ (measure.js:73) → „KI-Vorschläge“; „Claude analysiert …“ (567) → „KI analysiert …“; „Vorschläge von Claude“ (526) → „KI-Vorschläge“; Herkunft-Chip „Claude“ (515) → „KI“; `Claude: ${m.reason}` (499) → `KI: ${m.reason}`; Toasts (574) entsprechend; „Claude bekommt die entzerrten Fotos … Herkunft „Claude““ (539) → „Die KI bekommt die entzerrten Fotos … Herkunft „KI““ |
| Verwaltung | „Claude-Modell“ (app.js:726) → „KI-Modell“; app.js:703 „… CAD mit Claude sind deaktiviert“ → „Kein Schlüssel hinterlegt – KI-Funktionen sind deaktiviert.“; Rückfrage app.js:719 → „KI-Funktionen sind danach deaktiviert, bis ein neuer Schlüssel hinterlegt ist.“; „Anthropic-API-Schlüssel“ und Console-Link bleiben |
| Fehlermeldungen an Nutzer | ai.py:247 „Anthropic-Ratenlimit erreicht …“ → „KI-Dienst: Ratenlimit erreicht – bitte später erneut versuchen.“; ai.py:249 „Anthropic-API-Fehler …“ → „KI-Dienst: Fehler {status} …“; ai.py:251 → „Keine Verbindung zum KI-Dienst.“; main.py:1105 und jobs.py:190 „KI ist nicht eingerichtet: Anthropic-API-Schlüssel fehlt (Verwaltung → Einstellungen).“ → „KI ist nicht eingerichtet (Verwaltung → Einstellungen).“; ai.py:218 → „KI ist nicht eingerichtet – KI-Funktionen sind deaktiviert.“. Die Meldungen in `ai.verify()` und main.py:301 bleiben (Einrichtung/Verwaltung) |
| Downloads | CSV-Spalte „Quelle“ zeigt „KI“ statt `claude` und „automatisch“ statt `auto`; Spalte „Schieblehre“ heißt in CSV und `measurement_table` künftig „Messschieber“; im ZIP heißt der Schlüssel `ki` statt `claude` |

## 7. Datenmodell und API

**Datenbank** (`db.py`):

```sql
CREATE TABLE IF NOT EXISTS parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, label TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'body',
  data TEXT NOT NULL,   -- {"polygon", "edge_ids", "next_edge_id", "hidden", "holes", "dropped", "warn", "note"}
  source TEXT NOT NULL DEFAULT 'auto',   -- auto | ki | user
  scale REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_parts_photo ON parts(photo_id);
```

Migration in `db.conn()` direkt nach `executescript(SCHEMA)`: `PRAGMA table_info(measurements)`; fehlt `part_id`, wird `ALTER TABLE measurements ADD COLUMN part_id INTEGER REFERENCES parts(id) ON DELETE SET NULL` ausgeführt. Test: alte DB ohne Spalte → nach `conn()` Spalte vorhanden.

**Endpunkte** (alle mit Eigentümerprüfung wie bei Messungen):

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/api/photos/{phid}/edges` | Body `{use_ai: true}`. Erkennung + Zuordnung + Abgleich mit vorhandenen Teilen (§2). Antwort `{parts, segments, notice}` |
| GET | `/api/photos/{phid}/edges.json` | gespeichertes `EdgeResult` (404, wenn noch nicht erkannt) |
| POST | `/api/projects/{pid}/parts` | Teil von Hand: `{photo_id, label, role, polygon}` |
| PATCH | `/api/parts/{id}` | `{label?, role?, polygon?, reset_scale?}` |
| DELETE | `/api/parts/{id}` | Auto-Maße ohne Messschieber-Wert löschen, mit Wert → `source = 'user'`; übrige Messungen `part_id = NULL` |
| PATCH | `/api/measurements/{mid}` | neu: `part_id` (Zahl = festes Teil, `null` = keins, `-1` = automatisch; nur ausgewertet, wenn im Body vorhanden – `model_fields_set`), `ref` (bool). Zahl → `part_id` = Zahl, `data.part_fixed = true` (Teil muss zum selben Projekt gehören, sonst 400); `null` → `part_id = NULL`, `part_fixed = true`; `-1` → `part_fixed` entfernt, `refresh` ordnet zu |

`GET /api/projects/{pid}` liefert zusätzlich `parts`. Polygone: 3–64 Punkte, endliche Zahlen, innerhalb der Rasterfläche ± 10 mm. Erkennung nur für Fotos mit `rect.jpg`, sonst 400. Nichts erkannt → 422 „Kein Objekt erkannt – Teil von Hand zeichnen.“

**Lebenszyklus:** Ändert `PATCH /api/photos/{phid}` das Format (neue `rect.jpg`), werden `edges.json` gelöscht und alle Teile des Fotos wie bei `DELETE /api/parts/{id}` entfernt; danach `refresh`. `DELETE /api/photos/{phid}` wendet vor dem Löschen dieselbe Teil-Löschlogik an (Auto-Maße ohne Messschieber-Wert weg, mit Wert → `source = 'user'`).

**Grenzen:** Ein Erkennungslauf mit KI zählt zum bestehenden Tageslimit von 30 (nur Nicht-Admins, wie bisher): beide Endpunkte zählen `action IN ('suggest', 'edges_ai')`; `edges_ai` wird nur geschrieben, wenn die KI tatsächlich aufgerufen wird. Meldung bei `suggest`: „Tageslimit für KI-Funktionen erreicht (30).“ Bei der Erkennung läuft es ohne KI weiter (§2). Höchstens ein Erkennungslauf gleichzeitig pro Prozess (Semaphore nur um den OpenCV-Teil, nicht um den KI-Aufruf); ein zweiter wartet.

## 8. Tests

- `tests/conftest.py`: `synthetic_photo` bekommt den Parameter `objects: list[dict] | None = None`. `None` = bisheriges dunkles Rechteck; Liste = nur diese Objekte, in mm der Rasterfläche (Ursprung unten links, Umrechnung über `matgen`-Layout auf Seitenpixel): `{"rect": [x, y, w, h], "gray": 150}`, `{"circle": [cx, cy, d], "gray": 235}`.
- `tests/test_edges.py`: Quader 60 × 40 mm (Grau 150); Variante mit überlappender Platte 80 × 20 mm (Grau 90) und Bohrung Ø 5 mm (Papierfarbe); über `synthetic_photo(objects=…)` verzerrt, mit `vision.analyze` + `rectify_mat` entzerrt, dann `edges.detect`. Erwartungen wie A1.
- `tests/test_parts.py`: Rechteckerkennung und Auto-Maße, Einrasten (Treffer, `preferred`, verdeckte Kante, Fallback), Kanten-Kennungen bei Einfügen/Löschen, Zuordnung Messung → Teil bei Überlappung, Maßstab (A2), Nennmaß, `dropped`, überzählige Auto-Maße mit Messschieber-Wert, Abgleich bei erneuter Erkennung (IoU).
- `tests/test_api.py`: Ablauf im Testmodus – Foto hochladen, Kanten erkennen, Teil bearbeiten, Messschieber setzen, Werte prüfen, Teil löschen, CAD-Auftrag mit `part_id` (A3, A4); Formatwechsel entfernt Teile; Migration. Die bestehende Prüfung `/api/prompt.md` → 200 (test_api.py:36) wird zu → 404.
- `tests/test_texts.py`: A5.
- Docker-Smoke-Test (`tests/docker/smoke_api.py`): nur eine zusätzliche Prüfung `GET /api/prompt.md` → 404. Keine Kantenerkennung im Smoke-Test (CI-pytest und Image nutzen dieselbe `web/requirements.txt`).

## 9. Auslieferung

Branch `kanten-und-teile` → CI grün → Merge nach `main` → CI auf `main` grün (inkl. Image auf ghcr.io) → auf der DS918+ in `/volume1/docker/snap2cad` `docker compose pull && docker compose up -d` (eigene Compose-Datei, nicht die aus dem Repo) → Gesundheit prüfen → A8.
