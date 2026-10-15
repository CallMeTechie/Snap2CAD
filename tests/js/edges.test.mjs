// Kanten-Editor: Rechtsklick auf Kante und Einfuegen von Eckpunkten (web/static/js/geom.js) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { nearestOnPolygonEdge, insertVertex } from "../../web/static/js/geom.js";

const SQ = [[0, 0], [10, 0], [10, 10], [0, 10]];

test("nearestOnPolygonEdge: Fusspunkt, Abstand und Kante", () => {
  const r = nearestOnPolygonEdge([4, -2], SQ, 3);
  assert.equal(r.i, 0);
  assert.deepEqual(r.p, [4, 0]);
  assert.equal(r.d, 2);
  assert.equal(r.t, 0.4);
});

test("nearestOnPolygonEdge: schliessende Kante n-1 -> 0", () => {
  const r = nearestOnPolygonEdge([-1, 7], SQ, 3);
  assert.equal(r.i, 3);
  assert.deepEqual(r.p, [0, 7]);
  assert.equal(r.d, 1);
  assert.equal(r.t, 0.3);
});

test("nearestOnPolygonEdge: naechste Kante gewinnt", () => {
  assert.equal(nearestOnPolygonEdge([9, 4], SQ, 3).i, 1);
  assert.equal(nearestOnPolygonEdge([5, 9.5], SQ, 3).i, 2);
});

test("nearestOnPolygonEdge: Toleranz (Grenze zaehlt noch)", () => {
  assert.equal(nearestOnPolygonEdge([5, -3.5], SQ, 3), null);
  assert.equal(nearestOnPolygonEdge([5, -3], SQ, 3).d, 3);
  assert.equal(nearestOnPolygonEdge([5, 5], SQ, 3), null);  // Flaechenmitte
});

test("nearestOnPolygonEdge: Punkt auf oder hinter einem Eckpunkt zaehlt als Eckpunkt", () => {
  assert.equal(nearestOnPolygonEdge([10, 0], SQ, 3), null);
  assert.equal(nearestOnPolygonEdge([0, 10], SQ, 3), null);
  assert.equal(nearestOnPolygonEdge([11, -1], SQ, 3), null);  // Fusspunkt beider Kanten ist die Ecke
});

test("nearestOnPolygonEdge: entartete Eingaben", () => {
  assert.equal(nearestOnPolygonEdge([0, 0], [], 3), null);
  assert.equal(nearestOnPolygonEdge([0, 0], [[0, 0]], 3), null);
  assert.equal(nearestOnPolygonEdge([1, 1], [[1, 1], [1, 1], [5, 1]], 3), null);  // doppelte Ecke, Punkt darauf
});

test("insertVertex: nach Index i, ohne das Original zu aendern", () => {
  const out = insertVertex(SQ, 0, [5, 0]);
  assert.deepEqual(out, [[0, 0], [5, 0], [10, 0], [10, 10], [0, 10]]);
  assert.equal(SQ.length, 4);
  out[0][0] = 99;
  assert.equal(SQ[0][0], 0);  // Punkte sind Kopien
});

test("insertVertex: auf der schliessenden Kante ans Ende", () => {
  assert.deepEqual(insertVertex(SQ, 3, [0, 5]), [[0, 0], [10, 0], [10, 10], [0, 10], [0, 5]]);
});
