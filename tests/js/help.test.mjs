// Tastenkürzel der Anleitung und Kurzhilfe (web/static/js/help.js) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { SHORTCUTS, TOOL_KEYS, SECTIONS, groupsFor } from "../../web/static/js/help.js";

const GROUPS = ["messen", "kanten", "fotos", "modell", "ueberall"];

test("jede Gruppe vorhanden und nicht leer, jeder Eintrag mit Tasten und Text", () => {
  assert.deepEqual(Object.keys(SHORTCUTS).sort(), [...GROUPS].sort());
  for (const g of GROUPS) {
    assert.ok(SHORTCUTS[g].length > 0, g);
    for (const s of SHORTCUTS[g]) {
      assert.ok(Array.isArray(s.keys) && s.keys.length > 0, `${g}: keys`);
      assert.ok(s.keys.every(k => typeof k === "string" && k.trim() !== ""), `${g}: ${s.keys}`);
      assert.ok(typeof s.text === "string" && s.text.trim() !== "", `${g}: text`);
    }
  }
});

test("keine doppelten Tasten je Gruppe", () => {
  for (const g of GROUPS) {
    const seen = SHORTCUTS[g].map(s => s.keys.join("|"));
    assert.equal(new Set(seen).size, seen.length, `${g}: ${seen}`);
  }
});

test("alle Werkzeugtasten stehen in der Gruppe Messen", () => {
  const keys = new Set(SHORTCUTS.messen.filter(s => s.keys.length === 1).map(s => s.keys[0]));
  assert.deepEqual(Object.keys(TOOL_KEYS).sort(), ["a", "c", "e", "l", "p", "v"]);
  for (const k of Object.keys(TOOL_KEYS)) assert.ok(keys.has(k.toUpperCase()), k);
});

test("Texte ohne Markennamen", () => {
  const all = JSON.stringify({ SHORTCUTS, SECTIONS });
  assert.doesNotMatch(all, /Claude|Anthropic/i);
});

test("Abschnitte und Kurzhilfe je Seite", () => {
  assert.deepEqual(SECTIONS.map(s => s[0]),
    ["ablauf", "unterlage", "fotografieren", "fotos", "messen", "kanten", "cad", "bemassung", "tastatur", "probleme"]);
  assert.deepEqual(groupsFor("/messen"), ["messen", "kanten", "ueberall"]);
  assert.deepEqual(groupsFor("/fotos"), ["fotos", "ueberall"]);
  assert.deepEqual(groupsFor("/cad/12"), ["modell", "ueberall"]);
  assert.deepEqual(groupsFor("/cad"), ["modell", "ueberall"]);
  assert.deepEqual(groupsFor("/"), ["ueberall"]);
});
