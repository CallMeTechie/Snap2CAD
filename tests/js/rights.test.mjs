// Rechte und Bereiche der Bibliothek (web/static/js/rights.js) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { ROLE_TEXT, SCOPE_KEY, creatorText, groupProjects, isReadOnly, loadScope, notFoundConcerns, projectRights, readOnlyRedraw, readOnlyText, saveScope, teamIdOf, teamQuery, validScope } from "../../web/static/js/rights.js";
import { api, menuLabel, plural, upload } from "../../web/static/js/lib.js";

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

test("notFoundConcerns: nur Pfade des offenen Projekts bzw. Auftrags (nicht das 404 eines anderen Projekts)", () => {
  assert.equal(notFoundConcerns("/api/projects/7", 7, null), "project");
  assert.equal(notFoundConcerns("/api/projects/7/photos", 7, null), "project");
  assert.equal(notFoundConcerns("/api/projects/7?x=1", 7, null), "project");
  assert.equal(notFoundConcerns("/api/projects/8", 7, null), null);       // Projektwahl auf ein gelöschtes Projekt
  assert.equal(notFoundConcerns("/api/projects/70", 7, null), null);      // Präfix ist kein Treffer
  assert.equal(notFoundConcerns("/api/projects/7", null, null), null);
  assert.equal(notFoundConcerns("/api/jobs/12", 7, 12), "job");
  assert.equal(notFoundConcerns("/api/jobs/12/param", 7, 12), "job");
  assert.equal(notFoundConcerns("/api/jobs/13", 7, 12), null);
  assert.equal(notFoundConcerns("/api/jobs/12", 7, null), null);
  assert.equal(notFoundConcerns(undefined, 7, 12), null);
});

test("readOnlyRedraw: nur dieselbe Seite mit demselben Projekt und Rolle Lesend wird neu gezeichnet", () => {
  const start = { path: "/messen", projectId: 7 }, ro = { id: 7, my_role: "lesend" };
  assert.equal(readOnlyRedraw(start, { path: "/messen", projectId: 7 }, ro), true);
  assert.equal(readOnlyRedraw(start, { path: "/fotos", projectId: 7 }, ro), false);                 // Seite gewechselt
  assert.equal(readOnlyRedraw(start, { path: "/messen", projectId: 8 }, { id: 8, my_role: "lesend" }), false);   // Projekt gewechselt
  assert.equal(readOnlyRedraw(start, { path: "/messen", projectId: null }, null), false);            // Zugriff verloren
  assert.equal(readOnlyRedraw(start, { path: "/messen", projectId: 7 }, { id: 7, my_role: "mitglied" }), false);
  assert.equal(readOnlyRedraw(start, { path: "/messen", projectId: 7 }, { id: 9, my_role: "lesend" }), false);
  assert.equal(readOnlyRedraw(null, { path: "/messen", projectId: 7 }, ro), false);
});

test("api: onNotFound bekommt den Pfad; true markiert den Fehler als gemeldet (kein zweiter Toast)", async () => {
  const old = globalThis.fetch, seen = [];
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Projekt nicht gefunden" }),
    { status: 404, headers: { "content-type": "application/json" } });
  api.onNotFound = (m, p) => { seen.push([m, p]); return true; };
  try { await assert.rejects(api("/api/projects/7/photos"), e => e.handled === true); }
  finally { globalThis.fetch = old; api.onNotFound = null; }
  assert.deepEqual(seen, [["Projekt nicht gefunden", "/api/projects/7/photos"]]);
});

test("upload meldet 404 und 403 „Nur lesender Zugriff“ an dieselben Hooks wie api", async () => {
  const old = globalThis.XMLHttpRequest;
  let status = 404, text = "";
  globalThis.XMLHttpRequest = class {
    constructor() { this.upload = {}; }
    open() {} setRequestHeader() {}
    send() { this.status = status; this.responseText = text; this.onload(); }
  };
  const seen = []; let ro = 0;
  api.onNotFound = (m, p) => { seen.push([m, p]); return true; };
  api.onReadOnly = () => { ro++; };
  try {
    text = JSON.stringify({ detail: "Projekt nicht gefunden" });
    await assert.rejects(upload("/api/projects/7/photos", {}), e => e.status === 404 && e.handled === true);
    status = 403; text = JSON.stringify({ detail: "Nur lesender Zugriff" });
    await assert.rejects(upload("/api/projects/7/photos", {}), e => e.status === 403 && !e.handled);
  } finally { globalThis.XMLHttpRequest = old; api.onNotFound = null; api.onReadOnly = null; }
  assert.deepEqual(seen, [["Projekt nicht gefunden", "/api/projects/7/photos"]]);
  assert.equal(ro, 1);
});

test("teamQuery: nur reine Ziffern als Team-Nummer, alles andere null", () => {
  assert.equal(teamQuery("?team=7"), 7);
  assert.equal(teamQuery("?x=1&team=42"), 42);
  for (const bad of ["", "?team=", "?team=0", "?team=1.5", "?team=-3", "?team=abc", "?team=1e3", "?team=%207",
    "?team=9223372036854775808", "?team=1234567890123456789"]) assert.equal(teamQuery(bad), null, bad);
  assert.equal(teamQuery(undefined), null);
});

test("menuLabel: Einladungszahl nur wenn vorhanden, Einzahl bei 1", () => {
  assert.equal(menuLabel({ username: "anna" }), "Benutzermenü: anna");
  assert.equal(menuLabel({ username: "anna", role: "admin" }, 0), "Benutzermenü: anna, Administrator");
  assert.equal(menuLabel({ username: "anna" }, 1), "Benutzermenü: anna, 1 Team-Einladung");
  assert.equal(menuLabel({ username: "anna", role: "admin" }, 3), "Benutzermenü: anna, Administrator, 3 Team-Einladungen");
});
