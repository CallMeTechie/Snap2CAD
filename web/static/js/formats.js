// Formate der Messunterlage: Druckformate (PDF) und Messformate (am Foto) – Daten und Texte ohne DOM (Spec Kleinteile §5)
import { de } from "./geom.js";

export const FORMAT_LABEL = Object.freeze({ A4: "A4", A3: "A3", K60H: "Kleinteile hell", K60D: "Kleinteile dunkel" });

const PAGES_BIG = Object.freeze([["mat", "Messunterlage"], ["gauge", "Höhenlehre zum Aufstellen"], ["guide", "Anleitung"]]);
const PHOTO_BIG = "Senkrecht, 50–70 cm, 2×-Zoom";
export const PRINT = Object.freeze({
  A4: Object.freeze({ title: "A4", field: "Feld 190 × 230 mm", ctrl: 100, photo: PHOTO_BIG, pages: PAGES_BIG }),
  A3: Object.freeze({ title: "A3", field: "Feld 270 × 360 mm", ctrl: 100, photo: PHOTO_BIG, pages: PAGES_BIG }),
  K60: Object.freeze({ title: "Kleinteile", field: "Feld 60 × 80 mm, hell + dunkel", ctrl: 50,
    photo: "Senkrecht, 2×/3×-Zoom aus 25–30 cm, kein Makro",
    pages: Object.freeze([["mat", "Blatt hell"], ["dark", "Blatt dunkel"], ["guide", "Anleitung"]]) }),
});

const span = ids => `${Math.min(...ids)}–${Math.max(...ids)}`;

export function isSmall(fmt) { return fmt === "K60H" || fmt === "K60D"; }
export function barClass(v, q) { return v > q[1] ? "err" : v > q[0] ? "warn" : ""; }
export function barWidth(v, q) { return Math.min(100, (v / q[1]) * 100); }
export function qualityLegend(q) {
  return `Skala 0–${de(q[1])} mm · Linie bei ${de(q[0])} mm = Grenze „gut“ · über ${de(q[1])} mm Foto wiederholen`;
}
export function unsureText(q) {
  return `Restfehler über ${de(q[1])} mm. Unterlage liegt vermutlich nicht flach oder das Foto ist unscharf – besser wiederholen.`;
}
export function lowContrastText(fmt) {
  const base = "Geringer Kontrast zur Unterlage – Licht seitlich, Schatten vermeiden, bei Glas oder Klarsicht ein Blatt Papier unterlegen.";
  return isSmall(fmt) ? `${base} Oder die andere Variante probieren: helles Teil auf das dunkle Blatt, dunkles Teil auf das helle Blatt.` : base;
}
export function ctrlLabels(ref, gridH, small) {
  const y = small ? `Skala 0–${de(gridH)} senkrecht` : `Raster 0–${de(gridH)} vertikal`;
  return { x: `0–${de(ref)} gemessen`, xPlaceholder: `${de(ref)},0`, xAria: `Kontrollmaß 0–${de(ref)} gemessen`, y, yAria: `${y} gemessen` };
}
export function mixedText(fmt) {
  return `Fotos auf verschiedenen Unterlagen – das Kontrollmaß gilt für die Unterlage des ersten Fotos (${FORMAT_LABEL[fmt] || fmt}).`;
}
export function layoutFacts(fmt, sp) {
  if (fmt === "K60") {
    const h = sp.K60H, d = sp.K60D;
    return [["Feld", `${h.grid_mm[0]} × ${h.grid_mm[1]} mm`], ["Marker", `8 × ${de(h.marker_size_mm)} mm`],
      ["Wörterbuch", `4X4_50 · ID ${span(h.ids)} / ${span(d.ids)}`], ["Höhenlehre", "keine – Teil kippen"]];
  }
  return [["Raster", `${sp.grid_mm[0]} × ${sp.grid_mm[1]} mm`], ["Marker", `8 × ${de(sp.marker_size_mm)} mm`],
    ["Wörterbuch", `4X4_50 · ID ${span(sp.ids)}`], ["Höhenlehre", `0–${de((sp.height_gauge || {}).vlen_mm)} mm`]];
}

// Fototipps als [Titel, Text]; Kleinteile: kurzer Abstand und keine Höhenlehre (Spec Kleinteile §5)
export function photoTips(fmt) {
  const small = isSmall(fmt);
  return [
    ["Senkrecht von oben", "Handy parallel zur Unterlage, Objekt in der Bildmitte."],
    small ? ["2×- oder 3×-Zoom aus 25–30 cm, kein Makro", "der Rahmen füllt das Bild."]
      : ["Abstand 50–70 cm, 2×-Zoom", "weniger perspektivische Verzerrung als nah mit Weitwinkel."],
    ["Alle 8 Marker sichtbar", "mindestens 4 sind nötig, mehr erhöhen die Genauigkeit."],
    ["Kein Blitz, kein Schlagschatten", "diffuses Licht, Marker dürfen nicht spiegeln."],
    ["Unterlage flach", "Ecken festkleben, keine Wellen im Papier."],
    small ? ["Teil kippen und als ‚Gekippt (Höhe)‘ fotografieren", "für Kleinteile gibt es keine Höhenlehre."]
      : ["Höhen", "Höhenlehre direkt neben das Objekt stellen – alle drei Marker im Bild, Kamera auf Höhe der Objektmitte."],
  ];
}
