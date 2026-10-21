# Kleinteile-Unterlage – Design

Stand 21.10.2026. Vorgänger: Teams (`2026-10-16-teams-design.md`, ausgeliefert als main ff95d9b). Danach folgen B8
(Messschieberwerte am Modell durch Marc) und Stufe C (Textur/GLB).

## Ziel

Snap2CAD vermisst Kleinteile von wenigen Millimetern bis etwa 50 mm. Dafür gibt es eine neue Messunterlage „Kleinteile“
mit einem Messfeld von 60 × 80 mm in einer hellen und einer dunklen Variante. Entzerrung, Kantenerkennung, Kontrollmaß,
Oberfläche und Anleitung werden dafür an das Format gebunden statt an feste Konstanten. A4 und A3 verhalten sich danach
exakt wie vorher.

Nutzerentscheidungen (Marc, 21.10.2026): Messfeld 60 × 80 mm; helle und dunkle Variante; Umsetzung vor B8 und Stufe C;
Ansatz „Formatprofile“; je Variante ein eigenes A4-Blatt, Feld ohne Raster, Skala und 8 Marker à 8 mm im weißen Rahmen,
IDs 20–27 hell / 30–37 dunkel, Kontrollmaß 50 mm, 30 px/mm, keine Höhenlehre; gemischte Projekte werden nicht gesperrt,
sondern mit Hinweis versehen.

## Erfolgskriterien

1. Auf einem synthetischen Foto der Kleinteile-Unterlage werden ein Teil von 3 × 3 mm und eine Bohrung von 1 mm
   Durchmesser erkannt; Außenmaße liegen innerhalb von ±0,1 mm, der Bohrungsdurchmesser innerhalb von ±0,1 mm.
2. Ein helles Teil auf dem dunklen Feld und ein durchscheinendes Teil (Hinweis „transparent“) auf dem dunklen Feld werden
   mit derselben Toleranz erkannt.
3. Für A4 und A3 liefern Analyse und Kantenerkennung auf den bestehenden synthetischen Testfotos dieselben Ergebnisse wie
   main ff95d9b (Goldwerte, Abweichung 0).
4. Bestehende Projekte (Fotos mit Format A4/A3) laufen ohne Migration weiter.

## Begriffe

- **Druckformat:** was die Unterlagen-Seite als PDF erzeugt: `A4`, `A3`, `K60`.
- **Messformat:** was die Analyse eines Fotos erkennt und am Foto speichert (`photos.format`): `A4`, `A3`, `K60H`
  (Kleinteile hell), `K60D` (Kleinteile dunkel). Das Druckformat `K60` erzeugt die Blätter für `K60H` und `K60D`.
- **Profil:** die Eigenschaften eines Messformats (§1).
- **Feldart:** `grid` (1-mm-Raster wie heute), `plain_light` (helles Feld ohne Raster), `plain_dark` (dunkles Feld ohne
  Raster).
- **Kantenmaßstab `k`:** Faktor für alle Längen-Konstanten der Kantenerkennung; Flächen-Konstanten mit `k²`.

## §1 Formatprofile (`core/matgen.py`)

Jedes Messformat hat ein Profil. Die Werte für A4 und A3 sind exakt die heutigen.

| Feld | A4 | A3 | K60H | K60D |
|---|---|---|---|---|
| Seite | A4 hoch | A3 hoch | A4 hoch | A4 hoch |
| Messfeld (mm) | 190 × 230 | 270 × 360 | 60 × 80 | 60 × 80 |
| Feldart | grid | grid | plain_light | plain_dark |
| Marker-Kante (mm) | 20 | 25 | 8 | 8 |
| Marker-IDs | 0–7 | 0–7 | 20–27 | 30–37 |
| Marker-Lage | im Raster (wie heute) | im Raster (wie heute) | im Rahmen außerhalb des Feldes | im Rahmen außerhalb des Feldes |
| Entzerrung `pxmm` | 10 | 10 | 30 | 30 |
| Kantenmaßstab `k` | 1 | 1 | 0,25 | 0,25 |
| Kontrollmaß waagerecht (mm) | 100 | 100 | 50 | 50 |
| Kontrollbezug senkrecht (mm) | 230 | 360 | 80 | 80 |
| Höhenlehre | ja | ja | nein | nein |

- Die Menge der Messformate (`FORMATS`) und die Druckformate (`PRINT_FORMATS = {"A4": ["A4"], "A3": ["A3"], "K60":
  ["K60H", "K60D"]}`) sind getrennt. Alle bestehenden Prüfungen `fmt in matgen.FORMATS` gelten für Messformate; die
  Unterlagen-Endpunkte prüfen gegen die Druckformate.
- `layout(fmt)` liefert wie heute `grid_mm`, `marker_size_mm`, `centers_mm`, `grid_origin_on_page_mm` und bei A4/A3
  `height_gauge`; zusätzlich das Profil (`pxmm`, `edge_scale`, `field`, `ids`, `ctrl_mm`). Marker-Mitten werden in mm ab
  der linken unteren Feldecke angegeben; bei K60 liegen sie außerhalb des Feldes (negative Werte bzw. größer als die
  Feldmaße).

### Blatt K60H / K60D

- Weißer Rahmen um das Feld, Rahmenbreite so, dass die Marker mit ihrer Ruhezone (mindestens eine Markerzelle) Platz
  haben und das Feld nicht berühren. 8 Marker: vier Ecken, vier Seitenmitten.
- Millimeterskala auf dem Rahmen an allen vier Feldkanten (Teilstriche 1 mm, längere bei 5 und 10 mm, Beschriftung alle
  10 mm). Das Feld selbst ist einfarbig: K60H Weiß, K60D ein tiefes, mattes Schwarzgrau (Farbwert im Plan festgelegt).
- Kopfzeile wie bei A4 („Messunterlage Kleinteile hell/dunkel“, Druckhinweis 100 %), Kontrollmaß 0–50 mm mit
  Eintragsfeld für waagerecht (0–50) und senkrecht (Skala 0–80), selbstbeschreibende Spezifikationszeile (IDs, Kante,
  Mitten).
- Die Kopfzeilen-Option der Unterlagen-Seite gilt auch hier.

### PDF-Seiten

- A4/A3: unverändert `mat`, `gauge`, `guide`.
- K60: `mat` (helles Blatt), `dark` (dunkles Blatt), `guide` (Anleitung Kleinteile). `gauge` gibt es nicht; eine
  Anfrage mit `pages=gauge` bei K60 fällt wie heute auf „alle Seiten“ zurück.
- `/api/mat.pdf`, `/api/mat/preview.png` und `/api/mat/layout` nehmen `format=K60` an. `layout` liefert bei K60 beide
  Messformate (`{"K60H": …, "K60D": …}`), bei A4/A3 unverändert das bisherige Objekt.

## §2 Erkennung und Entzerrung (`core/vision.py`)

- **Formaterkennung:** Für jede Marker-Familie (A4/A3: 0–7, K60H: 20–27, K60D: 30–37) werden die sichtbaren IDs gezählt.
  Kandidaten sind Familien mit mindestens 4 sichtbaren Markern. Sind Kleinteile-Familien darunter, gewinnt die
  Kleinteile-Familie mit den meisten Markern (bei Gleichstand der kleinere RMS-Fehler) – ein kleines Blatt auf der
  A4-Unterlage ist Absicht. Innerhalb der Familie 0–7 entscheidet wie heute der RMS-Fehler zwischen A4 und A3. Ein
  explizit gewähltes Format (`fmt`) gilt wie heute; passt keine ID seiner Familie, ist das Foto „nicht auswertbar“.
- `mat_ids` und `missing_ids` beziehen sich auf die Familie des gewählten Formats (bei keinem Format: 0–7 wie heute).
- **Entzerrung:** `rectify_mat` nutzt `pxmm` des Profils. Das Rechteckbild deckt genau das Messfeld ab.
  `a["rect"]["pxmm"]` speichert diesen Wert (wie heute, nur nicht mehr konstant).
- **Höhenlehre:** Bei K60H/K60D wird keine Höhenlehre ausgewertet (`gauge = None`), auch wenn Lehren-Marker sichtbar
  sind. Ein Foto mit Ansicht „Höhenlehre“ auf K60 bekommt den Hinweis „Höhenlehre gibt es bei Kleinteilen nicht – Teil
  kippen und als ‚Gekippt (Höhe)‘ fotografieren“.
- Alle Stellen, die heute `vision.PX_PER_MM` als Maßstab eines Rechteckbilds annehmen (`web/app/jobs.py`,
  `web/app/main.py` Bildbeschriftungen für die KI), lesen `rect["pxmm"]` des Fotos. `PX_PER_MM = 10` bleibt als Wert der
  A4/A3-Profile und als Rückfall für Fotos ohne gespeichertes `pxmm`.
- Ausrichtung der Unteransicht: `ALIGN_PXMM` (4 px/mm für align.jpg) wird mit `1/k` skaliert (K60: 16 px/mm).
  `align_bottom` arbeitet in mm und bleibt unverändert; die Flächenschwelle `area < 1.0` mm² gilt weiter.

## §3 Kantenerkennung (`core/edges.py`)

### Maßstab

- `detect(rect, fmt, hints)` liest `pxmm` und `k` aus dem Profil. Alle Längen in mm (Modulkonstanten wie `APPROX_MM`,
  `SEARCH_MM`, `MAX_SHIFT_MM`, `MIN_SEG_MM`, `GRID_*_MM`, `TRANSP_CLOSE_MM` und feste mm-Werte in Funktionen, z. B. der
  8-mm-Randstreifen, der 10-mm-Rand von GrabCut, die 5-mm-Mindestlänge und der 2-mm-Rand in `_refine`) werden mit `k`
  multipliziert, Flächen (`MIN_AREA_MM2`, `FILL_MM2`, `HOLE_MAX_MM2`) mit `k²`. `WORK_PXMM` wird mit `1/k` multipliziert
  (K60: 16 px/mm). Pixelgrößen von Kernen, die heute fest sind (3×3, 5×5, 9×9), bleiben fest, weil sie relativ zur
  Arbeitsauflösung gemeint sind.
- Für A4/A3 (`k = 1`, `pxmm = 10`) ergeben sich exakt die heutigen Zahlen. Das sichert ein Goldwert-Test (§6).
- Ausgabe `px_per_mm` ist das `pxmm` des Profils.

### Weg „Feldfarbe“ (Feldart `plain_light`, `plain_dark`)

- Kein Rasterkriterium, kein Gabor-Demodulator, kein Schatten-Veto, kein `sure_bg` aus dem Raster.
- Feldfarbe: aus dem Randstreifen des Feldes (Breite 8 mm · k) wie heute über `_paper_fit` (Ebene im Lab-Raum).
- Farbabstand: `diff = |L − L_feld| + 2 · Chroma-Abstand`, beidseitig (auf dem dunklen Feld heben sich Teile durch
  Helligkeit ab, auf dem hellen durch Dunkelheit). Schwelle wie heute Otsu mit Mindestwert `COLOR_MIN_DIFF`; Hinweis
  „hell“ senkt sie wie heute (`LIGHT_DIFF_FACTOR`, `LIGHT_MIN_DIFF`).
- Hinweis „transparent = 2“: wie heute nur Farbmaske, geschlossen über `TRANSP_CLOSE_MM · k`, größte Komponente.
  „transparent = 1“: Schwelle mit `TRANSP_DIFF_FACTOR`, sonst wie der Normalfall.
- GrabCut wie heute, mit `sure_fg` = erodierte Farbmaske und `sure_bg` = Randstreifen.
- Bohrungen: wie heute aus der Farbmaske (eine Bohrung zeigt das Feld). `_fill_unround` gilt unverändert.
- Der Kontrastwert (`contrast`) wird wie heute aus `diff` berechnet; der Hinweis „wenig Kontrast“ (< 12) nennt bei K60
  zusätzlich: „andere Variante probieren (helles Teil auf dunkles Feld, dunkles Teil auf helles Feld)“.

## §4 Kontrollmaß (`web/app/geom.py`, `web/app/main.py`)

- `geom.factors(project, ctrl_ref, grid_h)`: `fx = ctrl_x / ctrl_ref` (statt fest `/ 100`), `fy` wie heute über
  `grid_h`. `ctrl_ref` und `grid_h` kommen aus dem Profil des Projektformats (erstes Foto mit Format wie heute);
  ohne Format: 100 / keiner wie heute.
- `PATCH /api/projects/{pid}`: Plausibilität ±10 % um `ctrl_ref` (waagerecht) bzw. `grid_h` (senkrecht) des
  Projektformats; Fehlermeldung nennt den erwarteten Wert wie heute.
- **Gemischte Projekte:** Enthält ein Projekt Fotos mit Messformaten aus verschiedenen Druckformaten (A4, A3, K60 –
  K60H und K60D zählen als ein Druckformat), liefert die Projekt-API `mixed_formats: true`. Der Messen-Tab zeigt dann
  den Hinweis „Fotos auf verschiedenen Unterlagen – das Kontrollmaß gilt für die Unterlage des ersten Fotos (<Format>)“.
  Nichts wird gesperrt.

## §5 Oberfläche und Anleitung

- **Unterlagen-Seite (`mat.js`):** Formatwahl A4 / A3 / Kleinteile („Feld 60 × 80 mm, hell + dunkel“). Bei Kleinteilen
  heißen die Seiten „Blatt hell“, „Blatt dunkel“, „Anleitung“; Vorschau und Seitenwahl folgen. Druckhinweis und „Nach
  dem Drucken“ nennen bei Kleinteilen 50 mm Kontrollmaß und „2×/3×-Zoom aus 25–30 cm, kein Makro“.
- **Fotos (`photos.js`):** Formatauswahl „Automatisch erkennen“, A4, A3, „Kleinteile hell“, „Kleinteile dunkel“. Die
  Anzeige „10 px/mm“ kommt aus `rect.pxmm`. Der Fallback für die Rasterhöhe (`grid_h`) kommt aus der API statt aus
  festen 230/360.
- **Messen:** Kontrollmaß-Eingabe nennt den Bezug aus dem Profil (50/80 bzw. 100/230/360); Hinweis bei gemischten
  Projekten (§4).
- **KI-Text (`ai.py`):** „Ursprung der Draufsicht: linke untere Ecke des Rasters“ wird zu „… des Rasters bzw.
  Messfelds“.
- **Anleitung (`guide.js`) und PDF-Anleitung K60:** neuer Abschnitt „Kleinteile“:
  - Variante wählen: dunkles oder buntes Teil → helles Blatt; helles, blankes, weißes oder durchsichtiges Teil →
    dunkles Blatt.
  - Drucken mit 100 %; das dunkle Blatt möglichst mit Tintenstrahl auf mattem Papier (Laser-Toner glänzt auf großen
    dunklen Flächen). Kontrollmaß 50 mm nachmessen.
  - Teil mittig ins Feld, Marker frei lassen. Diffuses Licht, keine harten Schatten (es gibt kein Raster, das Schatten
    von Kanten unterscheidet).
  - Kamera senkrecht, 2×- oder 3×-Zoom aus 25–30 cm, Rahmen füllt das Bild; kein Makro-Modus (Parallaxe:
    Fehler ≈ Maß × Höhe ÷ Abstand, Beispiel 20 mm Breite, 10 mm Höhe: 0,8 mm bei 25 cm, 2,5 mm bei 8 cm).
  - Höhe: Teil kippen und erneut als Draufsicht bzw. „Gekippt (Höhe)“ fotografieren; keine Höhenlehre.
  - Genauigkeit realistisch: ±0,2–0,3 mm ohne, ±0,1–0,2 mm mit Messschieber-Nachmessung.
- Shortcuts und Mausbefehle ändern sich nicht.

## §6 Tests

- **Goldwerte A4/A3:** Vor der ersten Code-Änderung werden auf main ff95d9b `vision.analyze` und `edges.detect` für die
  bestehenden synthetischen Fotos (`photo_a4`, `photo_a3`, `photo_gauge` und die Objekt-Varianten aus `test_edges.py`)
  ausgeführt und als JSON unter `tests/fixtures/` abgelegt. Ein Test vergleicht danach exakt (Abweichung 0 nach Rundung
  auf 3 Stellen).
- **Synthetische Kleinteile-Fotos:** `synthetic_photo` bekommt die Druckformate K60H/K60D (Blatt gerendert mit mindestens
  30 px/mm, perspektivisch verzerrt, leicht unscharf, JPEG). Fälle: Quadrat 3 × 3 mm; Platte 20 × 12 mm mit Bohrung
  1 mm; helles Teil (Grauwert 230) auf K60D; durchscheinendes Teil (alpha 0,5, Hinweis transparent = 2) auf K60D;
  dunkles Teil auf K60H. Erwartung: Maße ±0,1 mm (§Erfolgskriterien).
- **Formaterkennung:** je Familie ein Foto; K60-Blatt auf A4-Unterlage → K60; nur 3 Marker → nicht auswertbar;
  explizites Format ohne passende IDs → nicht auswertbar.
- **Kontrollmaß:** `geom.factors` mit `ctrl_ref` 50/100; PATCH-Plausibilität für K60 (50 ± 5, 80 ± 8); `mixed_formats`.
- **Generator:** PDF für K60 hat 3 Seiten, Marker-IDs im Render erkennbar, Spezifikationszeile stimmt mit `layout`
  überein; `pages=gauge` bei K60 fällt auf alle Seiten zurück.
- **Oberfläche:** node-Tests für Formatwahl und Seitennamen; Browser-Durchlauf: Unterlage K60 erzeugen, synthetisches
  K60-Foto hochladen, Kanten im Messen-Tab, eine Messung, CAD-Auftrag anlegen.
- **Echtfoto (nur mit Marc):** Nach der Auslieferung ein Foto eines Kleinteils auf dem echten Ausdruck mit
  Messschieber-Vergleich; Ergebnis kommt ins Protokoll. Echte Fotos bleiben außerhalb des Repos.

## Nicht in dieser Stufe

- Höhenlehre für Kleinteile.
- Weitere Feldgrößen (z. B. 40 × 50 mm).
- Automatische Parallaxenkorrektur.
- Sperre gemischter Projekte.
