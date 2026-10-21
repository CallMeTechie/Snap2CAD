// Anleitung: Ablauf, Messunterlage (mit Generator), Fotografieren, Bedienung je Seite, Tastatur und Maus, Probleme
import { h, icon } from "./lib.js";
import { SECTIONS, SHORTCUTS, KEY_OF } from "./help.js";
import { matGenerator } from "./mat.js";
import { shortcutTable } from "./kurzhilfe.js";

const P = (...k) => h("p", {}, ...k);
const UL = items => h("ul", { class: "ul" }, items.map(i => h("li", {}, ...[i].flat())));
const B = t => h("strong", {}, t);
const K = t => h("kbd", {}, t);
const A = (href, t) => h("a", { href }, t);
const NOTE = (kind, ...k) => h("div", { class: `note ${kind}` }, icon(kind === "warn" ? "warn" : "info", 18), h("div", {}, ...k));

function section(id, ...body) {
  const title = SECTIONS.find(s => s[0] === id)[1];
  return h("section", { class: "gsec", id, "aria-labelledby": `${id}-h` }, h("h2", { id: `${id}-h` }, title), ...body);
}
const card = (...k) => h("div", { class: "card gtext" }, ...k);

function ablauf() {
  const st = (n, href, t, txt) => h("li", {}, h("span", { class: "num" }, n), h("div", {}, h("a", { href }, B(t)), h("br"), h("span", { class: "small" }, txt)));
  return section("ablauf", card(
    h("ol", { class: "gsteps" },
      st("1", "/", "Projekte", "Jedes Werkstück ist ein Projekt mit eigenen Fotos, Maßen und CAD-Aufträgen. In der Projektbibliothek wird ein neues Projekt angelegt oder ein vorhandenes geöffnet."),
      st("2", "/fotos", "Fotos prüfen", "Fotos des Werkstücks auf der Messunterlage hochladen. Die Marker werden erkannt und jedes Foto auf die Tischebene entzerrt. Nur auswertbare Fotos (mindestens vier Marker erkannt) werden Messquellen; Fotos mit „unsicher“ besser wiederholen. Für den CAD-Auftrag wählt Snap2CAD „unsichere“ Fotos nicht von selbst aus."),
      st("3", "/messen", "Messen", "Auf der entzerrten Draufsicht Strecken, Kreise, Punkte und Winkel setzen und Kanten erkennen lassen. Messschieberwerte machen kritische Maße verbindlich, die KI kann weitere Maße vorschlagen."),
      st("4", "/cad", "CAD-Modell", "Aus Maßen, Fotos und Beschreibung schreibt die KI ein parametrisches Modell, das eine abgeschottete Sandbox als STEP und STL erzeugt und prüft. Änderungen und nachgemessene Werte ergeben neue Versionen.")),
    P("Die Anleitung ist jederzeit über das Fragezeichen oben rechts erreichbar. Die Taste ", K("?"), " (oder ", K("F1"), ") zeigt auf jeder Seite die passenden Tastenkürzel.")));
}

function unterlage() {
  const gen = h("div", { class: "matgen" });
  matGenerator(gen);
  return section("unterlage",
    card(
      P("Die Messunterlage ist ein PDF mit 1-mm-Raster und acht ArUco-Markern, dazu auf Wunsch die Höhenlehre zum Aufstellen und eine Kurzanleitung. Ein Ausdruck reicht für beliebig viele Messungen."),
      P(B("Für kleine Teile (etwa 1–40 mm) gibt es das Format „Mini“:"), " eine Karte von 80 × 60 mm mit 0,5-mm-Raster und kleinen Markern dicht am Teil. Die Karte ausschneiden, plan auf Karton kleben und aus 20–30 cm mit 2×/3×-Zoom fotografieren – nicht im Makro-Modus, dessen Verzeichnung lässt sich nicht herausrechnen. Die entzerrte Draufsicht hat dann 20 statt 10 Bildpunkte pro Millimeter."),
      UL([
        [B("Mit 100 % bzw. „Tatsächliche Größe“ drucken"), " – nie „An Seite anpassen“, sonst stimmt der Maßstab nicht."],
        [B("Kontrollmaß prüfen:"), " die 100-mm-Skala unten links mit einem Stahllineal nachmessen und den Wert ins Feld unten rechts auf dem Blatt schreiben. Denselben Wert auf „Fotos prüfen“ unter „Kontrollmaß vom Ausdruck“ eintragen; daraus entstehen die Korrekturfaktoren für X und Y."],
        [B("Mattes Papier"), " verwenden: Glanz und Blitz überstrahlen die Marker."],
        [B("Plan fixieren:"), " die Unterlage auf eine Glasplatte oder einen festen Karton kleben, die Ecken mit Klebeband sichern. Welliges Papier ist die häufigste Fehlerquelle."],
      ])),
    gen);
}

function fotografieren() {
  return section("fotografieren", card(
    UL([
      [B("Senkrecht von oben:"), " Handy parallel zur Unterlage, Werkstück mittig."],
      [B("Abstand 50–70 cm mit 2×- oder 3×-Zoom"), " statt nah mit Weitwinkel – das verringert die perspektivische Verzerrung."],
      [B("Alle acht Marker frei lassen."), " Vier reichen für die Entzerrung, mehr machen sie robuster, falls das Werkstück einen Marker verdeckt."],
      [B("Kein Blitz, kein Glanz, kein Schlagschatten:"), " diffuses Licht, bei hellen oder glänzenden Teilen von der Seite. Dunkle Teile auf heller Unterlage sind ideal."],
      [B("Originaldatei hochladen."), " Messenger komprimieren die Fotos und verschlechtern die Kantenerkennung."],
    ]),
    h("h3", {}, "Unteransicht"),
    P("Das Teil umdrehen, wieder senkrecht von oben fotografieren und beim Hochladen die Ansicht „Von unten“ wählen. Die Unteransicht wird am Umriss an der Draufsicht ausgerichtet."),
    h("h3", {}, "Höhe"),
    P("Entweder das Teil kippen und erneut von oben fotografieren (Ansicht „Gekippt (Höhe)“), oder die Höhenlehre direkt neben das Teil stellen – alle drei Marker im Bild, Kamera etwa auf Höhe der Objektmitte – und von der Seite fotografieren. Die Höhenlehre wird erkannt und als eigene Ansicht zum Messen entzerrt (Nullpunkt = Tischebene)."),
    h("h3", {}, "Parallaxe"),
    P("Die Entzerrung gilt exakt nur für die Tischebene. Was höher liegt, ist näher an der Kamera und erscheint größer. Faustregel:"),
    h("p", { class: "formula" }, "Fehler ≈ Maß × Höhe über Tisch ÷ Kameraabstand"),
    P("Beispiel: Eine 100 mm breite Oberkante in 50 mm Höhe, fotografiert aus 500 mm, wirkt etwa 10 mm zu breit. Deshalb an der Auflagekante messen, aus größerem Abstand mit Zoom fotografieren oder das Teil kippen."),
    NOTE("info", B("Passmaße mit dem Messschieber nachmessen."), " Lagersitze, Wellen, Gewinde und Anschlussmaße brauchen mehr Genauigkeit, als ein Foto liefert. Fotos liefern Geometrie und Lage, keine Passmaßgenauigkeit.")));
}

function fotos() {
  return section("fotos", card(
    UL([
      [B("Hochladen:"), " Fotos auf die Fläche ziehen, „Dateien auswählen“, am Handy „Foto aufnehmen“ oder ein Bild aus der Zwischenablage mit ", K("Strg"), " + ", K("V"), " einfügen. JPG, PNG und HEIC in Originalauflösung."],
      [B("Ansicht:"), " oben unter „Ansicht“ festlegen, wofür die nächsten Fotos stehen (Draufsicht, Von unten, Gekippt (Höhe), Höhenlehre, Übersicht). In der Fotoliste lässt sich die Ansicht je Foto nachträglich ändern. „Unterlage“ erkennt A4, A3 oder Mini automatisch oder legt das Format fest."],
      [B("Ampel und Restfehler:"), " je Foto stehen die erkannten Marker und der größte Restfehler der Entzerrung. Bis 0,5 mm ist das Foto „gut“ (grün), bis 1 mm „brauchbar“ (gelb), darüber „unsicher – wiederholen“ (rot); bei Mini gelten 0,2 und 0,4 mm. Unter vier Markern ist es „nicht auswertbar“. Die Balken zeigen den Restfehler je Marker."],
      [B("Original, Entzerrt, Beide, Höhenlehre:"), " schaltet die Bilder darunter um; ein Klick auf ein Bild öffnet es in größerer Ansicht in einem neuen Tab."],
      [B("Lage der Unteransicht:"), " bei Fotos „Von unten“ zeigt der Kasten „Lage zur Draufsicht“ die Überlagerung. Steht dort „Ausrichtung unsicher“ oder passt die Überlagerung nicht, die richtige Lage wählen (z. B. „seitlich umgedreht“ oder „nach vorn umgedreht“); „Wieder automatisch“ setzt die Wahl zurück."],
      [B("Kontrollmaß vom Ausdruck:"), " den gemessenen Wert der 100-mm-Skala eintragen, auf Wunsch auch das Raster senkrecht (230 mm bei A4, 360 mm bei A3, 60 mm bei Mini). Die Faktoren X und Y gelten für alle Fotos des Projekts; leer = Faktor 1."],
      [B("Kasten „Werkstück“:"), " Farbe, Material, Transparenz und Oberfläche vor „Kanten erkennen“ setzen. Nur diese Handeingaben steuern die Kantenerkennung (z. B. helle oder durchscheinende Teile); eine Schätzung der KI wirkt dort nicht. „Zurücksetzen“ entfernt die Handeingaben."],
      [B("Kontrastwarnung:"), " „Geringer Kontrast zur Unterlage“ heißt: Licht von der Seite, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen."],
    ])));
}

function messen() {
  return section("messen", card(
    UL([
      [B("Quelle:"), " oben links unter „Foto“ die entzerrte Ansicht wählen – Draufsicht, Unteransicht oder Höhenlehre eines Fotos."],
      [B("Werkzeuge:"), " Verschieben (", K(KEY_OF.pan), "), Strecke (", K(KEY_OF.length), "; auf der Höhenlehre die Höhe ab der Tischkante), Kreis aus 3 Punkten auf dem Rand (", K(KEY_OF.circle), "; Durchmesser, in der Messung auf Radius umschaltbar), Punkt mit Koordinate (", K(KEY_OF.point), "; Ursprung unten links), Winkel (", K(KEY_OF.angle), "; Schenkel, Scheitel, Schenkel) und Kanten (", K(KEY_OF.edges), ")."],
      [B("Punkte setzen:"), " im Bild klicken; mit dem letzten Punkt wird die Messung gespeichert. ", K("Shift"), " richtet eine Strecke waagerecht oder senkrecht aus, ", K("Esc"), " verwirft die gesetzten Punkte, ", K("Rücktaste"), " nimmt den letzten zurück."],
      [B("Kantenfang und Lupe:"), " der Kantenfang rastet Punkte auf die deutlichste Kante in der Nähe ein (grüner Kreis = gefangen, im Werkzeug Verschieben aus). Die Lupe zeigt den Bereich unter dem Zeiger vergrößert (nicht bei Touch). Beides lässt sich in der Werkzeugleiste abschalten."],
      [B("Messung anklicken und benennen:"), " im Werkzeug Verschieben im Bild oder in der Liste rechts. Die Messung klappt auf: Bezeichnung, Unsicherheit, Messschieber, Teil, Passung, Notiz, „Kritisches Maß“ und Löschen."],
      [B("Messschieberwert:"), " ersetzt für das CAD-Modell den Fotowert. Gehört die Messung zu einem Teil, wird der Wert zur Referenz und alle Maße des Teils werden angepasst."],
      [B("Kritisch und Passung:"), " kritische Maße erscheinen im CAD-Auftrag unter „Passungen aus kritischen Maßen“, dort mit Passung und Tiefe."],
      [B("Manuell:"), " Maße ohne Foto, z. B. direkt vom Messschieber."],
      [B("KI-Vorschläge:"), " die KI schätzt weitere Maße aus dem entzerrten Foto. Vorschläge erscheinen orange gestrichelt mit K-Nummer und lassen sich einzeln oder alle übernehmen bzw. verwerfen."],
      [B("Kanten erkennen:"), " erkennt Kanten und Teile auf einer Draufsicht oder Unteransicht. Bei erneuter Erkennung behalten wiedergefundene Teile Bezeichnung und Messschieber-Referenzen. Der Hinweis „Werkstück geändert – Kanten neu erkennen“ erscheint, wenn sich die Angaben im Kasten „Werkstück“ geändert haben."],
      [B("Messschieber am Modell:"), " am 3D-Modell eingetragene Werte stehen in einer eigenen Liste, gelten für alle Aufträge des Projekts und lassen sich dort löschen."],
      [B("Weiter:"), " „CSV exportieren“ lädt die Maßtabelle, „An CAD übergeben“ öffnet den Auftrag."],
    ]),
    NOTE("warn", "Maße gelten für die Tischebene. Hoch liegende Kanten wirken größer – an der Auflagekante setzen.")));
}

function kanten() {
  return section("kanten", card(
    P("Teile sind Umrisse auf einer Draufsicht oder Unteransicht (T1, T2 …) mit Bezeichnung und Rolle (Grundkörper oder montiertes Teil). Aus ihnen entstehen automatische Maße. Die Teileliste steht rechts über den Messungen; ein Klick wählt ein Teil und schaltet auf das Werkzeug Kanten."),
    UL([
      [B("Eckpunkte ziehen:"), " in jedem Werkzeug. Im Werkzeug Kanten zeigt das ausgewählte Teil große Griffe; sonst tragen alle Teile kleine Punkte."],
      [B("Punkte einfügen:"), " im Werkzeug Kanten den Griff „+“ in der Kantenmitte des ausgewählten Teils anklicken oder ziehen. In jedem Werkzeug setzt ein Rechtsklick auf eine Kante dort einen Punkt; rechts ziehen von einer Kante oder einem Eckpunkt fügt einen Punkt ein und zieht ihn mit. Höchstens 64 Eckpunkte je Teil."],
      [B("Punkte löschen:"), " im Werkzeug Kanten den Eckpunkt anklicken, dann ", K("Entf"), " oder ", K("Rücktaste"), ". Ein Teil behält mindestens drei Eckpunkte."],
      [B("Neues Teil zeichnen:"), " „Neues Teil“ in der Teileliste oder rechts ziehen im Leerraum neben den Teilen. Punkte per Klick setzen; abschließen mit Doppelklick, ", K("Enter"), " oder Klick auf den ersten Punkt (ab drei Punkten). ", K("Esc"), " verwirft das Teil, ", K("Rücktaste"), " entfernt den letzten Punkt."],
      [B("Teil löschen:"), " das Teil in der Teileliste auswählen und „Teil löschen“. Seine automatischen Maße werden entfernt, Maße mit Messschieberwert bleiben als normale Messung."],
      [B("Darstellung:"), " im Werkzeug Kanten zeigen grau gestrichelte Linien erkannte Kanten, die zu keinem Teil gehören; gestrichelte Teilkanten sind verdeckte Kanten."],
      [B("Unteransicht:"), " Teile eines Fotos „Von unten“ tragen in der Liste den Zusatz „unten“. „unten = T1“ heißt: es ist dasselbe Teil wie T1 der Draufsicht; die Maße beider gehen gemeinsam in den Auftrag für dieses Teil."],
      [B("Maßstab:"), " ein Teil mit Messschieber-Referenz zeigt „Maßstab × …“; „Zurücksetzen“ hebt die Anpassung auf."],
    ]),
    NOTE("info", "Weiße Teile auf weißem Papier und harte Schlagschatten verfälschen den Umriss – dann die Eckpunkte von Hand korrigieren.")));
}

function cad() {
  return section("cad", card(
    UL([
      [B("Auftrag:"), " Bezeichnung, „Modell für“ (alle Teile als ein Körper oder ein einzelnes Teil), Zweck und Funktion, Fertigung (3D-Druck FDM, SLA oder CNC-Fräsen mit Material, kleinstem Fräser und Aufspannungen), Passungen aus kritischen Maßen und Zusatzwünsche. Rechts stehen die Fotos zum An- und Abwählen (höchstens sechs Bilder gehen mit) und die Maßtabelle."],
      [B("Prüfkasten „Vor dem Modellieren“:"), " prüft automatisch, ob Fotos und Maße für ein vollständiges Modell reichen, und nennt Rückfragen oder fehlende Fotos. „Erneut prüfen“ startet die Prüfung neu. Gibt es blockierende Punkte, heißt der Knopf „Trotzdem erzeugen“."],
      [B("Auftrag ansehen:"), " Fortschritt und Protokoll, auf Wunsch „Code live mitlesen“. Die Seite darf verlassen werden; der Auftrag läuft weiter und steht unter „Meine Aufträge“. „Abbrechen“ beendet den laufenden Schritt, fertige Versionen bleiben erhalten."],
      [B("Ergebnis:"), " Reiter 3D-Ansicht, Code, KI-Antwort und Foto-Abgleich. In der 3D-Ansicht stellen Iso, Oben, Vorn und Seite die Kamera, „Kanten“ zeichnet die Modellkanten, „Schnitt“ schneidet das Modell in halber Höhe auf. Dazu Zoom, „Einpassen“ und Vollbild."],
      [B("Foto-Abgleich:"), " den Umriss des Modells (Draufsicht, 1:1) mit Maus oder Finger auf das Bauteil im Foto schieben, mit Drehung, „+90°“, „Spiegeln“ und „Zentrieren“. Wo Umriss und Kante auseinanderliegen, stimmt das Modell nicht."],
      [B("Versionen:"), " oben unter „Version“ oder im Verlauf unten wählen. Schlägt eine Version fehl, steht der Fehler im Reiter Code; die Sandbox lässt Fehler automatisch korrigieren."],
      [B("Änderung anfordern:"), " den Wunsch beschreiben (Vorschläge helfen) und die nächste Version erzeugen. Jede Änderung zählt als CAD-Lauf."],
      [B("Downloads:"), " STEP (Master für CAD/CAM), STL, das parametrische Python-Modell, die Maßtabelle als CSV und alles zusammen als ZIP."],
    ])));
}

function bemassung() {
  const sw = (col, dash, t) => h("li", {}, h("span", { class: `swatch${dash ? " dash" : ""}`, style: { borderColor: col } }), t);
  return section("bemassung", card(
    P("Im 3D-Viewer stehen die Maße des Modells als Bemaßungslinien. Die Schalter über dem Viewer blenden Gruppen ein und aus: Außenmaße, Bohrungen, Tiefen, Fasen, Platten und Sonstige, dazu „Annahmen & nachgemessen“ und „Nur Annahmen“. Die Wahl bleibt in diesem Browser gespeichert."),
    h("ul", { class: "swatches" },
      sw("#b42318", false, "Rot: Annahme der KI"),
      sw("#1a7f37", false, "Grün: selbst nachgemessen"),
      sw("#1f6fb2", false, "Blau: Maß aus dem Modell"),
      sw("#1f6fb2", true, "Blau gestrichelt: von einem anderen Maß abgeleitet"),
      sw("#8a939b", true, "Grau gestrichelt: veraltet, die Linie passt nicht mehr zur Geometrie")),
    UL([
      [B("Wert eintragen:"), " ein Maß anklicken (oder mit ", K("Tab"), " ansteuern und ", K("Enter"), " drücken). ", K("Enter"), " sendet nur diesen Wert, ", K("Esc"), " bricht ab. Erlaubt sind Werte über 0 bis 5000 mm, mit Komma oder Punkt. Maße, die im Code keine Konstante sind, zeigen einen Hinweis – dann einen Änderungswunsch formulieren. Eintragen geht nur in der aktuellen Version und nicht, solange ein Lauf aktiv ist."],
      [B("Tabelle „Maße im Modell“:"), " Werte in den Feldern ändern und „Werte übernehmen“ sendet alle geänderten (höchstens 20 auf einmal); ", K("Enter"), " in einem Feld sendet nur diesen, auch unverändert – so lässt sich eine Annahme bestätigen. Ein Klick auf eine Zeile hebt die Linie im Modell kurz hervor."],
      [B("Neuaufbau ohne KI:"), " das Modell wird sofort mit dem neuen Wert neu gebaut (Plakette „Neuaufbau mit …“, abbrechbar). Je Benutzer läuft höchstens ein Neuaufbau zur Zeit."],
      [B("Messschieber am Modell:"), " jeder eingetragene Wert wird für das ganze Projekt gemerkt und geht bei jedem Auftrag und jeder Änderung als verbindlich an die KI. Die Liste steht auf der Messseite und lässt sich dort löschen. Aufträge ohne Projekt merken nichts."],
      [B("Banner und „Schlüsse ziehen“:"), " ersetzt ein Wert eine Annahme oder weicht er um mehr als 10 % ab, erscheint ein Hinweis. „Schlüsse ziehen“ schickt die nachgemessenen Werte als Änderungswunsch an die KI, die abhängige Maße daraus ableitet (neue Version, zählt als CAD-Lauf)."],
    ])));
}

function teams() {
  const row = (r, ...c) => h("tr", {}, h("th", { scope: "row" }, r), ...c.map(x => h("td", {}, x)));
  return section("teams", card(
    P("Jedes Konto hat eine private Bibliothek. Ein Team hat zusätzlich eine gemeinsame Bibliothek: Alle Mitglieder sehen deren Projekte mit Fotos, Maßen, Teilen, Werkstück-Angaben, gemerkten Messschieberwerten und CAD-Aufträgen. Ein Konto kann in mehreren Teams sein."),
    UL([
      [B("Bereich wählen:"), " oben in der Projektbibliothek „Privat“ oder ein Team anklicken; die Wahl bleibt in diesem Browser gespeichert. „Neues Projekt“ legt im gewählten Bereich an. Team-Karten zeigen, wer das Projekt angelegt hat."],
      [B("Projektauswahl:"), " auf den Seiten Fotos prüfen und Messen ist die Liste nach „Privat“ und Teams gruppiert."],
      [B("Team gründen und einladen:"), " im Benutzermenü „Teams“ → „Team gründen“; wer gründet, wird Leiter. Eingeladen wird mit dem genauen Benutzernamen (Groß- und Kleinschreibung egal) und einer Rolle; höchstens 20 Einladungsversuche je Stunde."],
      [B("Einladung annehmen:"), " offene Einladungen zeigen ein Abzeichen am Benutzermenü und den Eintrag „Team-Einladungen“. Unter „Teams“ annehmen oder ablehnen; erst danach sind Mitglieder und Projekte sichtbar."],
      [B("Verschieben:"), " im Menü „…“ einer Karte „In Team verschieben …“ bzw. „In privat verschieben“; die CAD-Aufträge kommen mit. Nach privat geht es nicht, wenn das Projekt Aufträge anderer Mitglieder enthält."],
      [B("Kopieren:"), " „In Team kopieren …“ bzw. „In privat kopieren“ legt eine Kopie mit Fotos, Messungen, Teilen, gemerkten Werten und von jedem fertigen CAD-Auftrag der aktuellen Version an (laufende oder fehlgeschlagene Aufträge ohne fertige Version entfallen); die Kopie gehört dem, der kopiert, und verbraucht kein Kontingent. Das ist auch der Weg, wenn sich ein Projekt mit Aufträgen anderer nicht nach privat verschieben lässt. Zwischen zwei Teams geht es über „In privat kopieren“ und danach „In Team kopieren“."],
      [B("Austreten:"), " unter „Teams“ beim Team „Austreten …“. Die eigenen Team-Projekte bleiben im Team und zeigen „von ehemaligem Mitglied“. Der letzte Leiter bestimmt vorher einen anderen Leiter; das letzte Mitglied kann nur ein leeres Team verlassen, das dabei gelöscht wird."],
      [B("Kontingent:"), " jeder CAD-Lauf zählt zum Monatskontingent dessen, der ihn auslöst, ein Neuaufbau zu dessen Stundengrenze – auch am Auftrag eines anderen Mitglieds. „Meine Aufträge“ filtert nach Team."],
    ]),
    h("div", { class: "tablewrap" }, h("table", { class: "t" },
      h("thead", {}, h("tr", {}, h("th", {}, "Recht"), h("th", {}, "Leiter"), h("th", {}, "Mitglied"), h("th", {}, "Lesend"))),
      h("tbody", {},
        row("Projekte ansehen, Dateien und CSV laden", "ja", "ja", "ja"),
        row("Fotos, Messen, Kanten, Werkstück, KI und CAD", "ja", "ja", "nein"),
        row("Projekt umbenennen und archivieren", "ja", "ja", "nein"),
        row("Projekt löschen und verschieben", "jedes", "nur selbst angelegte", "nein"),
        row("Projekt kopieren", "ja", "ja", "nein"),
        row("Mitglieder einladen, Rollen ändern, entfernen, Team umbenennen und löschen", "ja", "nein", "nein")))),
    NOTE("info", "Mit der Rolle Lesend steht auf Fotos prüfen, Messen und CAD-Modell oben „Nur ansehen“; Bearbeiten ist dort gesperrt.")));
}

function tastatur() {
  return section("tastatur", card(
    P("Tastenkürzel wirken nicht, solange der Fokus in einem Eingabefeld liegt; auf der Messseite auch nicht mit gedrückter ", K("Strg"), "-, ", K("Alt"), "- oder Befehlstaste. ", K("?"), " oder ", K("F1"), " zeigt die Tabellen der aktuellen Seite als Kurzhilfe. In Eingabefeldern öffnen ", K("?"), " und ", K("F1"), " die Kurzhilfe nicht."),
    Object.keys(SHORTCUTS).map(g => shortcutTable(g))));
}

function probleme() {
  const q = (t, ...a) => h("div", { class: "faq" }, h("h3", {}, t), P(...a));
  return section("probleme", card(
    q("Marker werden nicht erkannt", "Alle acht Marker frei lassen, kein Blitz und kein Glanz, Foto scharf und die Unterlage vollständig im Bild. Auf „Fotos prüfen“ nennt „Fehlend: ID …“ die verdeckten Marker; mindestens vier sind nötig."),
    q("Foto „unsicher – wiederholen“", "Der Restfehler liegt über 1 mm. Meist liegt die Unterlage nicht flach oder das Foto ist unscharf: Papier fixieren und neu fotografieren."),
    q("Kanten mit Schatten oder falschem Umriss", "Diffuses Licht von der Seite verwenden, im Kasten „Werkstück“ Farbe und Transparenz angeben und „Kanten erkennen“ erneut starten. Danach die Eckpunkte von Hand korrigieren. Beim Messen hilft die Lupe; der Kantenfang lässt sich abschalten, wenn er auf den Schatten springt."),
    q("Unteransicht falsch ausgerichtet", "Auf „Fotos prüfen“ das Foto „Von unten“ wählen und im Kasten „Lage zur Draufsicht“ die richtige Lage anklicken."),
    q("„Anfrage blockiert“ hinter einem Reverse-Proxy", "Umbenennen, Löschen, Eckpunkte, Messungen und Werkstück-Angaben nutzen die HTTP-Methoden PATCH und DELETE. Eine Firewall oder ein Proxy vor Snap2CAD muss beide durchlassen. Funktioniert es im lokalen Netz, liegt die Sperre im Proxy."),
    q("KI nicht eingerichtet", "Ohne API-Schlüssel funktionieren Unterlage, Fotos und Messen; KI-Vorschläge, Prüfkasten und CAD-Aufträge sind aus. Administratoren hinterlegen den Schlüssel im Benutzermenü unter Benutzerverwaltung → Einstellungen."),
    q("Neuaufbau abgelehnt", "Neuaufbauten ohne KI sind auf 30 je Stunde und Benutzer begrenzt (Voreinstellung), und es läuft höchstens einer zur Zeit. Später erneut versuchen oder mehrere Werte gemeinsam über „Werte übernehmen“ senden.")));
}

// Inhalt in der Reihenfolge von SECTIONS (dieselbe Liste wie das Inhaltsverzeichnis)
const BUILD = { ablauf, unterlage, fotografieren, fotos, messen, kanten, cad, bemassung, teams, tastatur, probleme };

export default function (main) {
  const toc = h("nav", { class: "gtoc", "aria-label": "Inhalt der Anleitung" },
    h("span", { class: "label" }, "Inhalt"),
    h("ol", {}, SECTIONS.map(([id, t]) => h("li", {}, h("a", { href: `#${id}` }, t)))));
  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Anleitung"),
      h("p", { class: "lead" }, "Vom Ausdruck der Messunterlage bis zum CAD-Modell, mit allen Tastenkürzeln und Mausbefehlen."))),
    h("div", { class: "guide-layout" }, toc,
      h("div", { class: "gmain" }, SECTIONS.map(([id]) => BUILD[id]()))));
}
