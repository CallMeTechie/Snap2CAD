// Reine Geometrie der Messflaeche (web/static/js/geom.js) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { r3, segDist, inPoly, polyArea, unassignedSegments, pickPolygon } from "../../web/static/js/geom.js";

const SQ = [[0, 0], [10, 0], [10, 10], [0, 10]];

test("r3 rundet auf drei Nachkommastellen", () => {
  assert.equal(r3(1.23456), 1.235);
  assert.equal(r3(-1.23456), -1.235);
});

test("segDist: Lot, Endpunkte und entartete Strecke", () => {
  assert.equal(segDist([5, 3], [0, 0], [10, 0]), 3);
  assert.equal(segDist([13, 4], [0, 0], [10, 0]), 5);
  assert.equal(segDist([3, 4], [0, 0], [0, 0]), 5);
});

test("inPoly: innen, aussen und konkave Ecke", () => {
  assert.equal(inPoly([5, 5], SQ), true);
  assert.equal(inPoly([15, 5], SQ), false);
  const L = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]];
  assert.equal(inPoly([2, 8], L), true);
  assert.equal(inPoly([8, 8], L), false);
});

test("polyArea unabhaengig vom Umlaufsinn", () => {
  assert.equal(polyArea(SQ), 100);
  assert.equal(polyArea([...SQ].reverse()), 100);
});

test("unassignedSegments: nur innere Kanten, die auf keiner Teilekante liegen", () => {
  const segs = [
    { kind: "inner", a: [0.5, 0.4], b: [9.5, 0.6] },   // liegt auf der Unterkante
    { kind: "inner", a: [2, 5], b: [8, 5] },            // quer durch das Teil
    { kind: "outline", a: [20, 0], b: [30, 0] },        // Umriss: nie grau
  ];
  assert.deepEqual(unassignedSegments(segs, [SQ]), [segs[1]]);
  assert.deepEqual(unassignedSegments(segs, []), segs.slice(0, 2));
  const half = { kind: "inner", a: [0.5, 0.5], b: [5, 5] };  // nur ein Ende auf der Kante: bleibt grau
  assert.deepEqual(unassignedSegments([half], [SQ]), [half]);
});

test("pickPolygon: Kante schlaegt Flaeche, sonst das kleinste umschliessende", () => {
  const big = [[0, 0], [100, 0], [100, 100], [0, 100]], small = [[40, 40], [60, 40], [60, 60], [40, 60]];
  assert.equal(pickPolygon([50, 50], [big, small]), 1);
  assert.equal(pickPolygon([50, 35], [big, small]), 1);   // 5 px vor der Kante des kleinen, nur im grossen
  assert.equal(pickPolygon([50, -3], [big]), 0);          // ausserhalb, aber Kante in Reichweite
  assert.equal(pickPolygon([150, 150], [big, small]), -1);
});

test("pickPolygon: bei zwei Kanten in Reichweite gewinnt die naehere", () => {
  const body = [[0, 0], [100, 0], [100, 40], [0, 40]], plate = [[-6, 10], [106, 10], [106, 30], [-6, 30]];
  assert.equal(pickPolygon([-5, 20], [body, plate]), 1);  // 1 px neben der Plattenkante, 5 px neben dem Koerper
  assert.equal(pickPolygon([1, 20], [plate, body]), 1);   // umgekehrt: 1 px neben dem Koerper
});
