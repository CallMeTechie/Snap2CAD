# Prompt: Vermessen → CAD → STEP/STL

Diesen Prompt zusammen mit den Fotos an eine KI mit Code-Ausführung geben (z. B. Claude mit Dateitools oder ChatGPT mit Code Interpreter). Den Abschnitt **AUFTRAG** am Ende ausfüllen.

Ohne Code-Ausführung liefert die KI nur Schätzwerte vom Raster und ein Modellierungsskript, aber keine geprüften Dateien.

```text
Du vermisst ein Objekt anhand von Fotos auf einer gedruckten Messunterlage und erstellst danach ein fertigungsgerechtes CAD-Modell als STEP und STL für 3D-Druck oder CNC-Fräsen.
Arbeite präzise, rechne nach und gib zu jedem Maß an, wie sicher es ist. Erfinde keine Werte: Fehlt etwas, sag es und nenne das Foto oder Maß, das fehlt.

# TEIL A – VERMESSUNG

## Die Messunterlage
- 1-mm-Raster, dicke Linien alle 10 mm, beschriftet unten und links.
- Ursprung 0/0 = untere linke Rasterecke, X nach rechts, Y nach oben, Einheit mm.
- 8 ArUco-Marker DICT_4X4_50, aufrecht gedruckt (Markeroberkante zeigt zum oberen Blattrand).
- Die Variante steht oben links auf dem Blatt ("Messunterlage A4/A3/Mini").

A4: Raster 190 × 230 mm, Markerkante 20 mm. Markermitten (X|Y):
ID0 13|13 · ID1 177|13 · ID2 177|217 · ID3 13|217 · ID4 95|13 · ID5 177|115 · ID6 95|217 · ID7 13|115

A3: Raster 270 × 360 mm, Markerkante 25 mm. Markermitten (X|Y):
ID0 15,5|15,5 · ID1 254,5|15,5 · ID2 254,5|344,5 · ID3 15,5|344,5 · ID4 135|15,5 · ID5 254,5|180 · ID6 135|344,5 · ID7 15,5|180

Mini (kleine Teile, ausgeschnittene Karte): Raster 80 × 60 mm mit 0,5-mm-Teilung (dicke Linien alle 5 und 10 mm), Markerkante 7 mm, eigene IDs 20–27. Markermitten (X|Y):
ID20 5,5|5,5 · ID21 74,5|5,5 · ID22 74,5|54,5 · ID23 5,5|54,5 · ID24 40|5,5 · ID25 74,5|30 · ID26 40|54,5 · ID27 5,5|30

Markerecken in OpenCV-Reihenfolge (oben links, oben rechts, unten rechts, unten links), Mitte (cx|cy), halbe Kante h:
(cx−h | cy+h), (cx+h | cy+h), (cx+h | cy−h), (cx−h | cy−h)

Kontrollfeld unten rechts (handschriftlich):
- "Gemessen (0–100)" → Faktor X = Wert / 100
- "Gemessen Raster 0–230 bzw. 0–360 (Mini: 0–60) vertikal" → Faktor Y = Wert / Sollwert
Alle Ergebnisse mit diesen Faktoren korrigieren. Ist das Feld leer, Faktor 1 annehmen und das sagen.

Höhenlehre (optional): aufgestellter Streifen, 45 mm breit, 0 = Falz = Tischebene, direkt neben das Objekt gestellt (alle drei Marker im Bild). Marker DICT_4X4_50, Kante 18 mm, horizontal mittig (x = 0).
- Streifen A: IDs 10, 11, 14 · Streifen B: IDs 12, 13, 15.
- A4: Markermitten ID10/ID12 auf 208 mm, ID11/ID13 auf 180 mm, ID14/ID15 auf 30 mm über dem Falz.
- A3: Markermitten ID10/ID12 auf 328 mm, ID11/ID13 auf 300 mm, ID14/ID15 auf 30 mm über dem Falz.
- Mini: Streifen 24 mm breit, Kante 6 mm, Streifen A: IDs 30, 31, 34 · B: IDs 32, 33, 35. Markermitten ID30/ID32 auf 45,5 mm, ID31/ID33 auf 36,5 mm, ID34/ID35 auf 8 mm über dem Falz.

## Messverfahren (Python + OpenCV)
1. Marker erkennen. Homographie Bild → Tischebene in mm aus allen Markerecken der IDs 0–7 (Mini: 20–27, mindestens 4 Marker).
2. Leave-one-out-Restfehler je Marker angeben. Über 1 mm (Mini: 0,4 mm) gilt das Foto als unsicher.
3. Draufsicht entzerren (≥10 px/mm, Mini ≥20 px/mm), Kanten und Bohrungen messen. Bohrungen per Kreis-Fit (Durchmesser + Mittelpunkt), Lochabstände von Mitte zu Mitte.
4. Höhen aus einer Draufsicht des gekippten Objekts oder per Homographie auf der Höhenlehre (alle Ecken der drei Marker eines Streifens; der untere Marker 14/15 stützt den Bereich nahe der Tischebene). Gemessen wird in der Ebene der Lehre – das Objekt muss direkt daneben stehen.
5. Parallaxe beachten: Die Homographie gilt nur für die Tischebene. Fehler ≈ Maß × Höhe über Tisch ÷ Kameraabstand. An der Auflagekante messen oder umrechnen und das kennzeichnen.
6. Entzerrtes Bild mit eingezeichneten Messlinien beilegen.

Ohne Code-Ausführung: Maße nur am Raster schätzen (typisch ±2–5 mm), klar als Schätzung kennzeichnen. In diesem Fall in Teil B keine Dateien behaupten, sondern nur das Modellierungsskript liefern.

## Ergebnis Teil A – dann STOPP
Maßtabelle: ID | Merkmal | Messwert mm | Unsicherheit ± mm | Quelle (Foto/Methode) | Vorschlag Nennmaß | kritisch? (Passung/Funktion)
- Nennmaß: Nur runden, wenn es eindeutig Konstruktionsabsicht ist (z. B. 24,93 → 25,0, 6,38 → Ø6,4 Durchgangsloch M6). Jede Rundung begründen.
- Kritische Maße (Passungen, Bohrungen für Wellen oder Lager, Gewinde, Anschlussmaße) ausdrücklich markieren und um Messschieber-Werte bitten. Photogrammetrie mit ±0,5 mm reicht für Passungen nicht.
- Offene Fragen stellen: Fertigungsverfahren, Material, Gegenstücke, Gewinde, Toleranzen, Funktionsflächen.
Erst nach meiner Bestätigung der Maßtabelle mit Teil B beginnen.

# TEIL B – CAD-MODELL, STEP und STL

## Werkzeug
Python mit build123d (pip install build123d), alternativ CadQuery. Beide nutzen OpenCascade und exportieren echtes B-Rep-STEP.

## Modellierung
- Parametrisch: Alle Maße als benannte Variablen oben im Skript, je mit Kommentar zur Herkunft (Maß-ID aus Tabelle A).
- Einheit mm, Z nach oben, Auflagefläche auf XY, sinnvoller Ursprung (Bohrungsmitte oder Bauteilecke) – im Skript dokumentieren.
- Konstruktionsabsicht abbilden: Bohrungen als Bohrungen, Fasen und Radien als Features, Symmetrie nutzen. Keine Freiformflächen aus der Silhouette, wenn Regelgeometrie gemeint ist.
- Nicht sichtbare Bereiche (Rückseite, Innenkonturen) nicht erfinden. Annahme treffen, im Skript als ANNAHME markieren und in der Antwort auflisten.

## Fertigungsgerecht – Verfahren abfragen, dann anwenden
3D-Druck (FDM):
- Ausgleichsparameter für Bohrungen und Passungen vorsehen (Startwert +0,2 mm auf Innendurchmesser, je nach Drucker anpassbar).
- Mindestwandstärke ca. 1,2 mm.
- Überhänge über 45° vermeiden oder benennen.
- Druckausrichtung vorschlagen.
- Gewinde: Kernloch für Einschmelzmutter oder Gewindeformer statt gedrucktem Gewinde, sofern nicht anders gewünscht.

CNC-Fräsen:
- Innenecken mit Radius ≥ Werkzeugradius + Zugabe (Werkzeug abfragen; ohne Angabe R ≥ 3 mm und markieren).
- Keine Hinterschnitte ohne Rückfrage, Bearbeitung aus möglichst wenigen Aufspannungen.
- Bohrungen in Normdurchmessern.
- Gewinde als Kernloch modellieren und in der Maßtabelle als "M6 × 1, Tiefe x" vermerken, nicht als Gewindegeometrie.

Toleranzen und Passungen aus Teil A in die Bemerkungen übernehmen. Das STEP enthält Nennmaße.

## Export
- STEP (export_step) = Master-Datei.
- STL in mm, fein tesseliert (z. B. tolerance=0.01, angular_tolerance=0.1). Bei FDM mit eingerechnetem Bohrungsausgleich, im Dateinamen kennzeichnen.
- Dateinamen: <Teilname>_v<Version>.step / .stl / .py

## Prüfung vor Abgabe (Pflicht)
1. STEP neu importieren: Bounding Box und Volumen gegen die Maßtabelle prüfen.
2. STL: wasserdicht (z. B. trimesh is_watertight), keine degenerierten Dreiecke, Bounding Box = STEP.
3. Modell-Silhouette in die entzerrte Draufsicht des Fotos einblenden und Abweichungen in mm angeben.
4. Vorschaubilder: Isometrie + Draufsicht + Front + Seite, Hauptmaße eingetragen.

## Ausgabe Teil B
- STEP, STL, Python-Skript, Maßtabelle (CSV oder Markdown) und Vorschaubilder.
- Liste aller Annahmen und nicht gemessener Maße.
- Prüfergebnisse aus dem Pflichtschritt.
- Hinweis, welche Maße vor der Fertigung noch mit dem Messschieber bestätigt werden sollten.

# AUFTRAG
Teil / Zweck: [z. B. Halter für …, Ersatzteil für …]
Fertigung: [FDM / SLA / CNC], Material: [z. B. PETG, PA12, Alu 6082]
Gesuchte bzw. kritische Maße: [z. B. Lochabstand, Wellendurchmesser, Gesamthöhe]
Messschieber-Werte (falls vorhanden): [Merkmal = Wert]
```
