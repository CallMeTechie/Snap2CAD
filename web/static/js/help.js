// Anleitung und Kurzhilfe: einzige Quelle der Tastenkürzel und Mausbefehle (ohne DOM, auch für node --test)
// Jede Zeile ist im Code belegt: measure.js (onKey, Zeiger), edges.js (key, down/downRight/click/dbl), photos.js,
// viewer.js (OrbitControls, Labels), cad.js, app.js (Kurzhilfe), library.js (Menü „…“).

// Werkzeugtasten der Messseite; measure.js liest sie von hier
export const TOOL_KEYS = Object.freeze({ v: "pan", l: "length", c: "circle", p: "point", a: "angle", e: "edges" });
// Umkehrtabelle Werkzeug → Taste (Großbuchstabe), für Anleitung, Kurzhilfe und Werkzeugleiste
export const KEY_OF = Object.freeze(Object.fromEntries(Object.entries(TOOL_KEYS).map(([k, t]) => [t, k.toUpperCase()])));

// Abschnitte der Anleitung (Sprungmarken /anleitung#id)
export const SECTIONS = Object.freeze([
  ["ablauf", "Ablauf"], ["unterlage", "Messunterlage drucken"], ["fotografieren", "Fotografieren"], ["fotos", "Fotos prüfen"],
  ["messen", "Messen"], ["kanten", "Kanten und Teile"], ["cad", "CAD-Modell"], ["bemassung", "Bemaßung am Modell"],
  ["teams", "Teams"], ["tastatur", "Tastatur und Maus"], ["probleme", "Häufige Probleme"],
]);

export const GROUP_TITLE = Object.freeze({
  messen: "Messen", kanten: "Kanten und Teile (Messseite)", fotos: "Fotos prüfen", modell: "3D-Ansicht und Auftrag", ueberall: "Überall",
});

// keys: Tasten und Mausbefehle; „oder“ und „dann“ trennen Alternativen bzw. Folgen, sonst gilt „gleichzeitig“ (+)
export const SHORTCUTS = Object.freeze({
  messen: [
    { keys: [KEY_OF.pan], text: "Werkzeug Verschieben: Bild ziehen, Messung im Bild anklicken = auswählen" },
    { keys: [KEY_OF.length], text: "Werkzeug Strecke (2 Punkte); auf der Höhenlehre misst es die Höhe" },
    { keys: [KEY_OF.circle], text: "Werkzeug Kreis aus 3 Punkten auf dem Rand (Durchmesser, in der Messung auf Radius umschaltbar)" },
    { keys: [KEY_OF.point], text: "Werkzeug Punkt mit Koordinate (Ursprung unten links)" },
    { keys: [KEY_OF.angle], text: "Werkzeug Winkel: Punkt auf Schenkel 1, Scheitel, Punkt auf Schenkel 2" },
    { keys: [KEY_OF.edges], text: "Werkzeug Kanten: Teile auswählen und bearbeiten" },
    { keys: ["Klick"], text: "Punkt setzen; die Messung wird mit dem letzten Punkt gespeichert. Im Werkzeug Verschieben: Messung auswählen" },
    { keys: ["Shift", "Klick"], text: "Strecke oder Höhe: Punkt waagerecht oder senkrecht zum vorigen Punkt ausrichten" },
    { keys: ["Esc"], text: "Gesetzte Punkte der laufenden Messung verwerfen; beim Ziehen eines Eckpunkts das Ziehen abbrechen" },
    { keys: ["Rücktaste"], text: "Letzten gesetzten Punkt zurücknehmen; ohne gesetzte Punkte die ausgewählte Messung löschen (nicht im Werkzeug Kanten)" },
    { keys: ["Entf"], text: "Ausgewählte Messung löschen, ohne Rückfrage (nicht im Werkzeug Kanten)" },
    { keys: ["+", "oder", "="], text: "Vergrößern" },
    { keys: ["-"], text: "Verkleinern" },
    { keys: ["0"], text: "Bild einpassen" },
    { keys: ["Mausrad"], text: "Zoomen zum Mauszeiger" },
    { keys: ["Strg", "Mausrad"], text: "In großen Schritten zoomen (auch Zwei-Finger-Geste auf dem Touchpad)" },
    { keys: ["Maus links ziehen"], text: "Bild verschieben, in jedem Werkzeug (ab 5 Pixel Weg, sonst zählt es als Klick)" },
    { keys: ["Maus Mitte ziehen"], text: "Bild verschieben" },
    { keys: ["Maus rechts ziehen"], text: "Bild verschieben – auf der Höhenlehre und in einer Teilfläche abseits von Kante und Eckpunkt" },
    { keys: ["Zwei Finger"], text: "Touch: zoomen und verschieben" },
    { keys: ["Enter"], text: "Fokussierte Messung in der Liste öffnen oder schließen; im Feld „Bezeichnung“ den Namen übernehmen" },
  ],
  kanten: [
    { keys: ["Maus links auf Eckpunkt ziehen"], text: "Eckpunkt eines Teils verschieben – in jedem Werkzeug; im Werkzeug Kanten wird das Teil dabei ausgewählt" },
    { keys: ["Klick"], text: "Werkzeug Kanten: Teil auswählen, Klick daneben hebt die Auswahl auf. Beim Zeichnen eines neuen Teils: Punkt setzen, Klick auf den ersten Punkt schließt ab 3 Punkten" },
    { keys: ["Klick auf Griff +"], text: "Werkzeug Kanten, ausgewähltes Teil: Punkt in der Kantenmitte einfügen (ziehen verschiebt ihn gleich)" },
    { keys: ["Rechtsklick auf Kante"], text: "Punkt an dieser Stelle der Kante einfügen – in jedem Werkzeug" },
    { keys: ["Maus rechts von Kante ziehen"], text: "Punkt auf der Kante einfügen und an die Zielstelle ziehen" },
    { keys: ["Maus rechts von Eckpunkt ziehen"], text: "Neuen Punkt hinter dem Eckpunkt einfügen und ziehen (neue Linie vom Eckpunkt aus)" },
    { keys: ["Maus rechts im Leerraum ziehen"], text: "Neues Teil beginnen: Start und Ziel sind die ersten zwei Punkte, das Werkzeug wechselt auf Kanten" },
    { keys: ["Doppelklick"], text: "Neues Teil abschließen" },
    { keys: ["Enter"], text: "Neues Teil abschließen (mindestens 3 Punkte); in der Teileliste: fokussiertes Teil auswählen" },
    { keys: ["Entf", "oder", "Rücktaste"], text: "Beim Zeichnen den letzten Punkt entfernen, sonst den angeklickten Eckpunkt löschen (ein Teil behält mindestens 3)" },
    { keys: ["Esc"], text: "Ziehen abbrechen (Umriss bleibt unverändert), neues Teil verwerfen oder Auswahl aufheben" },
  ],
  fotos: [
    { keys: ["Dateien auf die Fläche ziehen"], text: "Fotos hochladen (Ziehen und Ablegen)" },
    { keys: ["Strg", "V"], text: "Bild aus der Zwischenablage einfügen und hochladen" },
    { keys: ["Klick"], text: "Foto in der Liste anzeigen" },
    { keys: ["Enter"], text: "Fokussiertes Foto in der Liste anzeigen" },
    { keys: ["Klick auf das große Bild"], text: "Bild in größerer Ansicht in einem neuen Tab öffnen" },
  ],
  modell: [
    { keys: ["Maus links ziehen"], text: "Modell drehen" },
    { keys: ["Mausrad"], text: "Zoomen zum Mauszeiger" },
    { keys: ["Maus Mitte ziehen"], text: "Zoomen" },
    { keys: ["Maus rechts ziehen"], text: "Modell verschieben" },
    { keys: ["Shift", "oder", "Strg", "Maus links ziehen"], text: "Modell verschieben" },
    { keys: ["Ein Finger"], text: "Touch: drehen" },
    { keys: ["Zwei Finger"], text: "Touch: zoomen und verschieben" },
    { keys: ["Klick auf ein Maß"], text: "Eingabefeld für einen Messschieberwert öffnen (nur aktuelle Version, nicht während eines Laufs)" },
    { keys: ["Tab", "dann", "Enter"], text: "Maßbeschriftung im Modell ansteuern und das Eingabefeld öffnen" },
    { keys: ["Enter"], text: "Im Eingabefeld eines Maßes (Modell oder Tabelle „Maße im Modell“): nur diesen Wert übernehmen, das Modell wird ohne KI neu gebaut. Auf einer fokussierten Tabellenzeile: Maßlinie hervorheben" },
    { keys: ["Esc"], text: "Eingabefeld am Modell schließen, ohne zu senden; im Vollbild das Vollbild verlassen" },
    { keys: ["Klick auf eine Tabellenzeile"], text: "Maßlinie im Modell 1,5 Sekunden hervorheben" },
    { keys: ["Klick auf Oben, Vorn oder Seite"], text: "Kleine Ansicht unter dem Modell: Kamera in diese Ansicht drehen" },
    { keys: ["Klick auf eine Version"], text: "Verlauf: diese Version anzeigen" },
    { keys: ["Umriss ziehen"], text: "Foto-Abgleich: Umriss des Modells mit Maus oder Finger auf das Bauteil schieben" },
  ],
  ueberall: [
    { keys: ["?", "oder", "F1"], text: "Diese Kurzhilfe öffnen (nicht, solange der Fokus in einem Eingabefeld liegt)" },
    { keys: ["Esc"], text: "Kurzhilfe, Dialog oder das Menü „…“ einer Projektkarte schließen" },
    { keys: ["Tab"], text: "Zum nächsten Bedienelement, mit Shift zurück; schließt das Menü „…“ einer Projektkarte" },
    { keys: ["Enter"], text: "Im Dialog: Eingabe bestätigen (z. B. Speichern)" },
    { keys: ["Pfeil ab", "oder", "Pfeil auf"], text: "Auf dem Knopf „…“ einer Projektkarte: Menü öffnen (beim ersten bzw. letzten Eintrag); im Menü: Eintrag wechseln" },
    { keys: ["Pos1", "oder", "Ende"], text: "Im Menü „…“ einer Projektkarte: erster bzw. letzter Eintrag" },
  ],
});

// Benannte Tasten (als <kbd> gezeigt); alles andere mit mehr als einem Zeichen ist ein Mausbefehl (Text)
const KEY_NAMES = new Set(["Strg", "Shift", "Alt", "Esc", "Enter", "Entf", "Rücktaste", "Tab", "F1", "Pfeil ab", "Pfeil auf", "Pos1", "Ende"]);
export const SEPARATORS = Object.freeze({ oder: " oder ", dann: " dann " });
export const isKey = k => k.length === 1 || KEY_NAMES.has(k);

// Gruppen der Kurzhilfe je Seite
export function groupsFor(path) {
  if (path === "/messen") return ["messen", "kanten", "ueberall"];
  if (path === "/fotos") return ["fotos", "ueberall"];
  if (path === "/cad" || path.startsWith("/cad/")) return ["modell", "ueberall"];
  return ["ueberall"];
}
