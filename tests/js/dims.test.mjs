// Bemaßung am Modell (web/static/js/geom.js, Spec Stufe B §3/§5, B5) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_SEL, DIM_GROUP_KEYS, DIM_GROUP_LABEL, DIM_GROUP_TEXT, ITER_MAX, dimSel, visibleDims, hasAnchors, dimGeometry,
  dimStyle, dimState, de, groupText, parseDimInput, paramBanner, conclusionText } from "../../web/static/js/geom.js";

const near = (act, exp) => {   // flach vergleichen; -0 und Rundungsreste zaehlen nicht
  const a = act.flat(Infinity), e = exp.flat(Infinity);
  assert.equal(a.length, e.length);
  a.forEach((v, i) => assert.ok(Math.abs(v - e[i]) < 1e-9, `${JSON.stringify(act)} != ${JSON.stringify(exp)}`));
};

test("dimGeometry: Versatz 8 % weg vom Modell, Hilfslinien mit Überstand", () => {
  const g = dimGeometry([0, 0, 0], [10, 0, 0], [5, 5, 0], 100);
  near(g.line, [[0, -8, 0], [10, -8, 0]]);
  near(g.ext, [[[0, 0, 0], [0, -10, 0]], [[10, 0, 0], [10, -10, 0]]]);
  near(g.label, [5, -8, 0]);
  assert.equal(g.off, 8);
});

test("dimGeometry: mindestens 2 mm Versatz bei kleinen Modellen", () => {
  const g = dimGeometry([0, 0, 0], [10, 0, 0], [5, 5, 0], 10);
  near(g.line, [[0, -2, 0], [10, -2, 0]]);
  assert.equal(g.off, 2);
});

test("dimGeometry: Mitte auf der Linie -> Z, bei senkrechter Linie X; Nulllänge -> null", () => {
  near(dimGeometry([-5, 0, 0], [5, 0, 0], [0, 0, 0], 100).line, [[-5, 0, 8], [5, 0, 8]]);
  near(dimGeometry([0, 0, 0], [0, 0, 10], [0, 0, 5], 100).line, [[8, 0, 0], [8, 0, 10]]);
  assert.equal(dimGeometry([1, 1, 1], [1, 1, 1], [0, 0, 0], 100), null);
});

test("visibleDims: Gruppen, Annahmen, Nur Annahmen, unbekannte Gruppe = sonst", () => {
  const dims = [{ id: "D1", group: "aussen" }, { id: "D2", group: "bohrung", assumed: true }, { id: "D3", group: "bohrung" },
    { id: "D4", group: "komisch" }, { id: "D5" }];
  const ids = sel => visibleDims(dims, sel).map(d => d.id);
  assert.deepEqual(ids(DEFAULT_SEL), ["D1", "D2"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, annahmen: false }), ["D1"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, nur_annahmen: true }), ["D2"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, aussen: false, annahmen: false, sonst: true }), ["D4", "D5"]);
});

test("visibleDims: vom Nutzer gesetztes Maß gilt wie eine Annahme", () => {
  const dims = [{ id: "D1", group: "aussen" }, { id: "D3", group: "platte", user_set: true }, { id: "D4", group: "platte" }];
  const ids = sel => visibleDims(dims, sel).map(d => d.id);
  assert.deepEqual(ids(DEFAULT_SEL), ["D1", "D3"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, annahmen: false }), ["D1"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, nur_annahmen: true }), ["D3"]);
});

test("DIM_GROUP_TEXT: ein Text je Gruppe, wie jobs.GROUP_TEXT", () => {
  assert.deepEqual(Object.keys(DIM_GROUP_TEXT), DIM_GROUP_KEYS);
  assert.equal(DIM_GROUP_TEXT.aussen, "außen");
  assert.equal(DIM_GROUP_TEXT.sonst, "sonstige");
  assert.ok(Object.isFrozen(DIM_GROUP_TEXT));
});

test("dimSel: Müll im Speicher ergibt die Standardwahl", () => {
  for (const raw of [null, undefined, "", "kein json", "5", "[true]", "null"]) assert.deepEqual(dimSel(raw), { ...DEFAULT_SEL });
  assert.deepEqual(dimSel('{"bohrung":true,"aussen":"ja","x":true}'), { ...DEFAULT_SEL, bohrung: true });
});

test("hasAnchors: nur je drei endliche Zahlen", () => {
  assert.equal(hasAnchors({ a: [0, 0, 0], b: [1, 0, 0] }), true);
  assert.equal(hasAnchors({ a: [0, 0], b: [1, 0, 0] }), false);
  assert.equal(hasAnchors({ a: [0, 0, "1"], b: [1, 0, 0] }), false);
  assert.equal(hasAnchors({ a: [0, 0, NaN], b: [1, 0, 0] }), false);
  assert.equal(hasAnchors({}), false);
});

test("dimStyle und dimState", () => {
  assert.deepEqual(dimStyle({ anchors_stale: true, assumed: true }), { color: "#8a939b", dashed: true });
  assert.deepEqual(dimStyle({ assumed: true }), { color: "#b42318", dashed: false });
  assert.deepEqual(dimStyle({ user_set: true }), { color: "#1a7f37", dashed: false });
  assert.deepEqual(dimStyle({ derived_from: "D3" }), { color: "#1f6fb2", dashed: true });
  assert.deepEqual(dimStyle({}), { color: "#1f6fb2", dashed: false });
  assert.equal(dimState({ assumed: true }), "Annahme");
  assert.equal(dimState({ user_set: true }), "nachgemessen");
  assert.equal(dimState({ derived_from: "D3" }), "abgeleitet von D3");
  assert.equal(dimState({}), "");
});

test("de: Dezimalkomma, höchstens drei Stellen, kein Tausenderpunkt", () => {
  assert.equal(de(45), "45");
  assert.equal(de(12.3456), "12,346");
  assert.equal(de(0.1 + 0.2), "0,3");
  assert.equal(de(1234.5), "1234,5");
});

test("parseDimInput: Komma, Leerzeichen, Unsinn und Grenzen", () => {
  assert.deepEqual(parseDimInput("45,5"), { value: 45.5 });
  assert.deepEqual(parseDimInput(" 45 "), { value: 45 });
  assert.deepEqual(parseDimInput("45.5"), { value: 45.5 });
  assert.deepEqual(parseDimInput("12,34567"), { value: 12.346 });
  for (const s of ["", "  ", null]) assert.equal(parseDimInput(s).error, "Bitte einen Wert eingeben.");
  for (const s of ["abc", "4 5", "0x10", "1e3", "-5", "1.234,5", "45 mm"]) assert.match(parseDimInput(s).error, /Kein gültiger Wert/);
  for (const s of ["0", "0,0001", "5000,1"]) assert.match(parseDimInput(s).error, /größer als 0 und höchstens 5000/);
  assert.deepEqual(parseDimInput("5000"), { value: 5000 });
});

test("paramBanner, conclusionText", () => {
  const p3 = { id: "D3", label: "Dicke", value: 8, old: 6, old_assumed: true };
  const p4 = { id: "D4", label: "Bohrung Ø", value: 4.7, old: 4.5, old_assumed: false };
  assert.equal(paramBanner([p3]), "8 mm ersetzt eine Annahme (6 mm) – Schlüsse auf abhängige Maße ziehen?");
  assert.equal(paramBanner([p4]), "");                                                     // 4,4 %: kein Banner
  assert.equal(paramBanner([{ ...p4, value: 5.5 }]), "5,5 mm statt 4,5 mm (Bohrung Ø) – Schlüsse auf abhängige Maße ziehen?");
  assert.equal(paramBanner([]), "");
  assert.equal(conclusionText([p3, p4]), "Nachgemessen mit dem Messschieber: D3 Dicke = 8 mm (vorher Annahme 6); "
    + "D4 Bohrung Ø = 4,7 mm (vorher 4,5). Leite daraus abhängige Maße ab (Tiefen, Dicken, Abstände, die an diesen Maßen "
    + "hängen), trage bei jedem geänderten Maß derived_from und eine kurze Begründung ein und ändere sonst nichts.");
  assert.equal(conclusionText([{ ...p3, old: null, old_assumed: false }]).startsWith("Nachgemessen mit dem Messschieber: D3 Dicke = 8 mm. "), true);
  assert.equal(conclusionText([]), "");
});

test("DIM_GROUP_LABEL: Schalter je Gruppe, Schlüssel wie DIM_GROUP_KEYS; groupText nur eigene Schlüssel", () => {
  assert.deepEqual(Object.keys(DIM_GROUP_LABEL), DIM_GROUP_KEYS);
  assert.ok(Object.isFrozen(DIM_GROUP_LABEL));
  assert.equal(groupText("bohrung"), "Bohrung");
  assert.equal(groupText("constructor"), "–");
  assert.equal(groupText("__proto__", "x"), "x");
  assert.equal(groupText(undefined), "–");
});

test("dimGeometry: Mitte bis auf Rundungsrauschen auf der Linie -> Rückfall +Z statt Rauschrichtung", () => {
  // Anker auf 1e-3 gerundet: Mitte liegt 0,0004 mm neben der Linie (nach -Z) – der Versatz zeigt trotzdem nach +Z
  near(dimGeometry([-5, 0, 0.0004], [5, 0, 0.0004], [0, 0, 0.0008], 100).line, [[-5, 0, 8.0004], [5, 0, 8.0004]]);
  // echter Abstand (1 % der Größe) bestimmt weiter die Richtung
  near(dimGeometry([-5, 0, 0], [5, 0, 0], [0, 0, 1], 100).line, [[-5, 0, -8], [5, 0, -8]]);
});

test("conclusionText: bleibt unter der Grenze des Änderungswunsches, Rest als „n weitere“", () => {
  const list = Array.from({ length: 200 }, (_, i) => ({ id: `D${i + 1}`, label: "Bohrung Lagersitz unten links".padEnd(60, "x"),
    value: 45.125 + i, old: 40.5, old_assumed: true }));
  const t = conclusionText(list);
  assert.ok(t.length <= ITER_MAX, String(t.length));
  assert.equal(ITER_MAX, 4000);
  const m = t.match(/; und (\d+) weitere \(siehe „Parametrisch geändert“ im Verlauf\)\. Leite daraus/);
  assert.ok(m, t.slice(-300));
  const shown = (t.match(/; D\d+ /g) || []).length + 1;
  assert.equal(shown + Number(m[1]), 200);
  assert.ok(t.endsWith("ändere sonst nichts."));
  assert.equal(conclusionText(list.slice(0, 3)).includes("weitere"), false);
  assert.ok(conclusionText(list, 500).length <= 500);
});
