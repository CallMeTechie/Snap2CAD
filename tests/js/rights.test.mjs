// Rechte und Bereiche der Bibliothek (web/static/js/rights.js) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { ROLE_TEXT, SCOPE_KEY, creatorText, groupProjects, isReadOnly, loadScope, projectRights, readOnlyText, saveScope, teamIdOf, validScope } from "../../web/static/js/rights.js";
import { api, plural } from "../../web/static/js/lib.js";

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

test("teamIdOf: Bereich zur Team-ID, privat und Ungültiges = null", () => {
  assert.equal(teamIdOf("team:12"), 12);
  for (const bad of ["private", "", null, undefined, "team:", "team:0", "team:x", "all"]) assert.equal(teamIdOf(bad), null, String(bad));
});

test("api meldet 404 an onNotFound (Spec §8: Zugriff verloren -> Bibliothek)", async () => {
  const seen = [], old = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Projekt nicht gefunden" }),
    { status: 404, headers: { "content-type": "application/json" } });
  api.onNotFound = m => seen.push(m);
  try { await assert.rejects(api("/api/projects/7"), e => e.status === 404 && e.message === "Projekt nicht gefunden"); }
  finally { globalThis.fetch = old; api.onNotFound = null; }
  assert.deepEqual(seen, ["Projekt nicht gefunden"]);
});

test("api meldet 403 „Nur lesender Zugriff“ an onReadOnly (Rolle inzwischen Lesend)", async () => {
  let n = 0;
  const old = globalThis.fetch;
  const answer = detail => async () => new Response(JSON.stringify({ detail }), { status: 403, headers: { "content-type": "application/json" } });
  api.onReadOnly = () => { n++; };
  try {
    globalThis.fetch = answer("Nur lesender Zugriff");
    await assert.rejects(api("/api/projects/7", { method: "PATCH", body: { name: "x" } }), e => e.status === 403);
    globalThis.fetch = answer("Nur der Ersteller oder ein Team-Leiter darf das");   // anderes 403: kein Neuzeichnen
    await assert.rejects(api("/api/projects/7", { method: "DELETE" }), e => e.status === 403);
  } finally { globalThis.fetch = old; api.onReadOnly = null; }
  assert.equal(n, 1);
});

test("isReadOnly und readOnlyText: nur die Rolle Lesend", () => {
  assert.equal(isReadOnly({ my_role: "lesend" }), true);
  for (const r of ["besitzer", "admin", "leiter", "mitglied", null]) assert.equal(isReadOnly({ my_role: r }), false, String(r));
  assert.equal(isReadOnly(null), false);
  assert.equal(readOnlyText({ team_name: "Werkstatt" }), "Nur ansehen – Rolle Lesend im Team Werkstatt");
  assert.equal(readOnlyText({}), "Nur ansehen – Rolle Lesend im Team");
});
