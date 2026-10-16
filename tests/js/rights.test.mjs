// Rechte und Bereiche der Bibliothek (web/static/js/rights.js) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { ROLE_TEXT, SCOPE_KEY, creatorText, groupProjects, loadScope, projectRights, saveScope, validScope } from "../../web/static/js/rights.js";
import { plural } from "../../web/static/js/lib.js";

test("projectRights reicht p.rights des Servers durch (eine Quelle: access.allowed)", () => {
  const none = { write: false, delete: false, move: false, copy: false };
  const r = { write: true, delete: false, move: false, copy: true };
  assert.deepEqual(projectRights({ my_role: "mitglied", rights: r }), r);
  assert.deepEqual(projectRights({ my_role: "besitzer", rights: { write: true, delete: true, move: true, copy: true } }),
    { write: true, delete: true, move: true, copy: true });
  assert.deepEqual(projectRights({ rights: { write: 1 } }), { ...none, write: true });   // fehlende Rechte = false
  assert.deepEqual(projectRights({ my_role: "leiter" }), none);                         // ohne Angabe nichts anbieten
  assert.deepEqual(projectRights(null), none);
});

test("Bereich merken: Schlüssel lib.scope, ohne localStorage kein Fehler", () => {
  assert.equal(SCOPE_KEY, "lib.scope");
  assert.doesNotThrow(() => saveScope("private"));
  assert.equal(loadScope(), "private");
});

test("plural (lib.js): Einzahl nur bei 1", () => {
  assert.equal(plural(1, "Projekt", "Projekte"), "1 Projekt");
  assert.equal(plural(0, "Projekt", "Projekte"), "0 Projekte");
  assert.equal(plural(3, "Foto", "Fotos"), "3 Fotos");
});

test("validScope: verlassenes oder gelöschtes Team fällt auf privat zurück", () => {
  const teams = [{ id: 3 }, { id: 12 }];
  assert.equal(validScope("team:12", teams), "team:12");
  assert.equal(validScope("team:5", teams), "private");
  assert.equal(validScope("team:12", []), "private");
  assert.equal(validScope("team:12", undefined), "private");
  for (const bad of [null, undefined, "", "all", "team:", "team:0", "team:012", "team:abc", "team:12x", " team:12"]) {
    assert.equal(validScope(bad, teams), "private", String(bad));
  }
  assert.equal(validScope("private", teams), "private");
});

test("creatorText: Ersteller, ehemaliges Mitglied, gelöschter Benutzer, privat", () => {
  assert.equal(creatorText({ team_id: 4, creator: { id: 2, name: "Anna" }, creator_is_member: true }), "von Anna");
  assert.equal(creatorText({ team_id: 4, creator: { id: 2, name: "Anna" }, creator_is_member: false }), "von ehemaligem Mitglied");
  assert.equal(creatorText({ team_id: 4, creator: null, creator_is_member: false }), "von ehemaligem Mitglied");
  assert.equal(creatorText({ team_id: null, creator: { id: 1, name: "Ich" } }), "");
});

test("groupProjects: Privat zuerst, dann Teams nach Name; leere Gruppen fehlen", () => {
  const list = [{ id: 9, team_id: 2, team_name: "Zeta" }, { id: 8, team_id: null }, { id: 7, team_id: 5, team_name: "Alpha" },
    { id: 6, team_id: 2, team_name: "Zeta" }];
  assert.deepEqual(groupProjects(list).map(g => [g.key, g.label, g.items.map(p => p.id)]),
    [["private", "Privat", [8]], ["team:5", "Alpha", [7]], ["team:2", "Zeta", [9, 6]]]);
  assert.deepEqual(groupProjects([{ id: 1, team_id: 3, team_name: "T" }]).map(g => g.key), ["team:3"]);
  assert.deepEqual(groupProjects([]), []);
});

test("Rollentexte vollständig und ohne Markennamen", () => {
  assert.deepEqual(Object.keys(ROLE_TEXT), ["besitzer", "admin", "leiter", "mitglied", "lesend"]);
  assert.doesNotMatch(JSON.stringify(ROLE_TEXT), /Claude|Anthropic/i);
});
