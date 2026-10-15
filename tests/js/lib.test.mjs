// Formatierung aus web/static/js/lib.js (ohne DOM) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { fmtValue } from "../../web/static/js/lib.js";

test("fmtValue mit und ohne Einheit", () => {
  assert.equal(fmtValue({ kind: "length", value: 60.004 }), "60 mm");
  assert.equal(fmtValue({ kind: "diameter", value: 22.5 }), "Ø 22,5 mm");
  assert.equal(fmtValue({ kind: "radius", value: 3.25 }, false), "R 3,25");
  assert.equal(fmtValue({ kind: "length", value: 42.4 }, false), "42,4");
  assert.equal(fmtValue({ kind: "angle", value: 90 }, false), "90°");
  assert.equal(fmtValue({ kind: "point", value: null, data: { points: [[12.34, 5]] } }), "X 12,3 · Y 5");
  assert.equal(fmtValue({ kind: "length", value: null }), "–");
});
