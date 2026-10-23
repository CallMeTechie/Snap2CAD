// Formate der Messunterlage (web/static/js/formats.js) – Aufruf: node --test tests/js/*.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { FORMAT_LABEL, PRINT, isSmall, barClass, barWidth, qualityLegend, unsureText, lowContrastText, ctrlLabels, mixedText, layoutFacts, photoTips }
  from "../../web/static/js/formats.js";

test("Anzeigenamen und Druckformate", () => {
  assert.equal(FORMAT_LABEL.K60H, "Kleinteile hell");
  assert.equal(FORMAT_LABEL.K60D, "Kleinteile dunkel");
  assert.deepEqual(Object.keys(PRINT), ["A4", "A3", "K60"]);
  assert.deepEqual(PRINT.K60.pages.map(p => p[0]), ["mat", "dark", "guide"]);
  assert.deepEqual(PRINT.A4.pages.map(p => p[0]), ["mat", "gauge", "guide"]);
  assert.equal(PRINT.K60.ctrl, 50);
  assert.ok(isSmall("K60D") && !isSmall("A4") && !isSmall(null));
});

test("Restfehler-Balken: A4 wie bisher, Kleinteile mit eigenen Schwellen", () => {
  const a4 = [0.5, 1.0], k = [0.125, 0.25];
  assert.equal(barWidth(0.3, a4), 30);          // bisher v * 100
  assert.equal(barWidth(2, a4), 100);
  assert.deepEqual([0.4, 0.6, 1.2].map(v => barClass(v, a4)), ["", "warn", "err"]);
  assert.equal(barWidth(0.125, k), 50);
  assert.deepEqual([0.1, 0.2, 0.3].map(v => barClass(v, k)), ["", "warn", "err"]);
  assert.equal(qualityLegend(a4), "Skala 0–1 mm · Linie bei 0,5 mm = Grenze „gut“ · über 1 mm Foto wiederholen");
  assert.equal(qualityLegend(k), "Skala 0–0,25 mm · Linie bei 0,125 mm = Grenze „gut“ · über 0,25 mm Foto wiederholen");
  assert.match(unsureText(k), /^Restfehler über 0,25 mm\./);
});

test("Kontrast, Kontrollmaß und gemischte Projekte", () => {
  assert.doesNotMatch(lowContrastText("A4"), /andere Variante/);
  assert.match(lowContrastText("K60D"), /andere Variante probieren: helles Teil auf das dunkle Blatt, dunkles Teil auf das helle Blatt/);
  assert.deepEqual(ctrlLabels(100, 230, false),
    { x: "0–100 gemessen", xPlaceholder: "100,0", xAria: "Kontrollmaß 0–100 gemessen", y: "Raster 0–230 vertikal", yAria: "Raster 0–230 vertikal gemessen" });
  assert.deepEqual(ctrlLabels(50, 80, true),
    { x: "0–50 gemessen", xPlaceholder: "50,0", xAria: "Kontrollmaß 0–50 gemessen", y: "Skala 0–80 senkrecht", yAria: "Skala 0–80 senkrecht gemessen" });
  assert.equal(mixedText("K60H"), "Fotos auf verschiedenen Unterlagen – das Kontrollmaß gilt für die Unterlage des ersten Fotos (Kleinteile hell).");
});

test("Kennzahlen der Unterlage", () => {
  const a4 = { grid_mm: [190, 230], marker_size_mm: 20, ids: [0, 1, 2, 3, 4, 5, 6, 7], height_gauge: { vlen_mm: 220 } };
  assert.deepEqual(layoutFacts("A4", a4), [["Raster", "190 × 230 mm"], ["Marker", "8 × 20 mm"], ["Wörterbuch", "4X4_50 · ID 0–7"], ["Höhenlehre", "0–220 mm"]]);
  const k = { K60H: { grid_mm: [60, 80], marker_size_mm: 8, ids: [20, 21, 22, 23, 24, 25, 26, 27] },
              K60D: { grid_mm: [60, 80], marker_size_mm: 8, ids: [30, 31, 32, 33, 34, 35, 36, 37] } };
  assert.deepEqual(layoutFacts("K60", k), [["Feld", "60 × 80 mm"], ["Marker", "8 × 8 mm"], ["Wörterbuch", "4X4_50 · ID 20–27 / 30–37"], ["Höhenlehre", "keine – Teil kippen"]]);
});

test("Fototipps: A4 unveraendert, Kleinteile mit eigenem Abstand und Kipp-Hinweis", () => {
  const big = photoTips("A4");
  assert.deepEqual(big[1], ["Abstand 50–70 cm, 2×-Zoom", "weniger perspektivische Verzerrung als nah mit Weitwinkel."]);
  assert.deepEqual(big[5],
    ["Höhen", "Höhenlehre direkt neben das Objekt stellen – alle drei Marker im Bild, Kamera auf Höhe der Objektmitte."]);
  assert.deepEqual(photoTips(""), big);
  assert.deepEqual(photoTips(null), big);
  const small = photoTips("K60D");
  assert.equal(small.length, big.length);
  const line = t => t.join(" – ");
  assert.equal(line(small[1]), "2×- oder 3×-Zoom aus 25–30 cm, kein Makro – der Rahmen füllt das Bild.");
  assert.equal(line(small[5]), "Teil kippen und als ‚Gekippt (Höhe)‘ fotografieren – für Kleinteile gibt es keine Höhenlehre.");
  assert.deepEqual(small.filter((_, i) => i !== 1 && i !== 5), big.filter((_, i) => i !== 1 && i !== 5));
  assert.doesNotMatch(JSON.stringify(small), /50–70 cm|Höhenlehre direkt/);
});
