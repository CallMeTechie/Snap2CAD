// Schritt 1: Projektbibliothek – private und Team-Bibliotheken mit Vorschaubild, Start für neue Projekte
import { api, h, clear, icon, dt, toast, fail, dialog, confirmDlg, debounce, plural } from "./lib.js";
import { S, go, onLeave, rememberProject, rememberedProjectId, forgetProject, jobBadge } from "./app.js";
import { ROLE_TEXT, creatorText, loadScope, projectRights, saveScope, teamIdOf, validScope } from "./rights.js";

const SORTS = { updated: "Zuletzt geändert", name: "Name", created: "Angelegt" };
const COLL = new Intl.Collator("de", { sensitivity: "base" });

function loadView() {
  try {
    const v = JSON.parse(localStorage.getItem("lib.view") || "{}");
    return { sort: Object.hasOwn(SORTS, v.sort) ? v.sort : "updated", archived: v.archived === true };
  } catch { return { sort: "updated", archived: false }; }
}
function saveView(v) { try { localStorage.setItem("lib.view", JSON.stringify(v)); } catch { /* */ } }
// Bereich der Bibliothek (Spec Teams §7): "private" oder "team:<id>", gemerkt über rights.loadScope/saveScope

// Neues Projekt: leerer Name ist erlaubt, der Server vergibt dann Datum und Uhrzeit; teamId = im Team anlegen.
// Ergebnis: true = angelegt, false = abgebrochen, null = Anlegen gescheitert (Fehler ist schon gemeldet)
export async function newProject(teamId = null) {
  const inp = h("input", { class: "input", placeholder: "z. B. Halteplatte Lagersitz", maxlength: 120, "aria-label": "Name" });
  const r = await dialog({ title: "Neues Projekt",
    body: h("div", { class: "field" }, h("label", {}, "Name"), inp, h("span", { class: "hint" }, "Leer lassen = Name aus Datum und Uhrzeit.")),
    actions: [{ label: "Abbrechen", value: null }, { label: "Anlegen", primary: true, submit: true, run: () => ({ name: inp.value.trim() }) }] });
  if (!r) return false;
  const at = location.pathname + location.search;
  try {
    S.project = await api("/api/projects", { method: "POST", body: teamId ? { name: r.name, team_id: teamId } : { name: r.name } });
    rememberProject();
    if (location.pathname + location.search === at) go("/fotos");   // inzwischen weitergeklickt: dort bleiben
    return true;
  } catch (e) { fail(e); return null; }
}

export default async function (main) {
  const view = loadView();
  let list = [], teams = [], scope = loadScope(), shownScope = "private", query = "", loadSeq = 0, opening = false;
  let cards = new Map(), lower = new Map();   // je Projekt-ID Karte und kleingeschriebener Name, je load() einmal gebaut
  const search = h("input", { class: "input", type: "search", placeholder: "Projekt suchen …", "aria-label": "Projekte durchsuchen", maxlength: 120 });
  const sortSel = h("select", { class: "input", "aria-label": "Sortierung" },
    Object.entries(SORTS).map(([k, t]) => h("option", { value: k, selected: k === view.sort }, t)));
  const archCb = h("input", { type: "checkbox", checked: view.archived });
  const grid = h("div", { class: "libgrid" });
  const tools = h("div", { class: "libtools" },
    h("div", { class: "libsearch" }, icon("search", 16), search),
    h("label", { class: "chips small" }, h("span", { class: "muted" }, "Sortieren"), sortSel),
    h("label", { class: "check small" }, archCb, "Archivierte zeigen"));
  const scopeBar = h("div", { class: "chips libscope", role: "group", "aria-label": "Bibliothek wählen", hidden: true });
  // scheitert das Anlegen (z. B. Rolle inzwischen Lesend), bleibt die Seite: Bereiche und Knopf neu laden
  // (nur nach einem gescheiterten Anlegen; Abbrechen und Erfolg laden nichts neu); angelegt wird im angezeigten Bereich
  async function createHere(teamId = teamIdOf(shownScope)) {
    if (await newProject(teamId) === null && main.isConnected) reload();
  }
  const newBtn = h("button", { class: "btn primary", onclick: () => createHere() }, icon("plus"), "Neues Projekt");
  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Projekte"),
      h("p", { class: "lead" }, "Alle Werkstücke mit Fotos, Maßen und CAD-Modellen – privat oder gemeinsam im Team. Von hier aus beginnt jedes neue Projekt.")),
    newBtn),
    h("div", { class: "chips", style: { justifyContent: "space-between" } }, scopeBar,
      h("a", { class: "small", href: "/teams" }, icon("users", 16), " Teams verwalten")),
    tools, grid);

  search.addEventListener("input", debounce(() => { query = search.value.trim().toLowerCase(); if (main.isConnected) draw(); }, 150));
  sortSel.addEventListener("change", () => { view.sort = sortSel.value; saveView(view); draw(); });
  archCb.addEventListener("change", () => { view.archived = archCb.checked; saveView(view); draw(); });

  // offenes Menü „…“: eines zur Zeit, Klick daneben schließt
  let menuClose = null;
  const outside = () => menuClose?.();
  document.addEventListener("click", outside);
  onLeave(() => document.removeEventListener("click", outside));

  // nur die juengste Antwort uebernehmen; Karten (mit Vorschaubild) nur hier neu bauen, damit Suchen
  // und Sortieren laufende Bildladevorgaenge nicht abbrechen
  async function load() {
    const n = ++loadSeq, stale = () => n !== loadSeq || !main.isConnected;   // nach jedem await prüfen, veraltet = still
    let t = { teams: [] }, teamsOk = true;
    try { t = await api("/api/teams"); } catch { teamsOk = false; }   // ohne Teams-Liste: privat statt kaputter Seite
    if (stale()) return;
    const sc = validScope(scope, t.teams);
    let l;
    try { l = await api(`/api/projects?scope=${encodeURIComponent(sc)}`); }
    catch (e) {   // Team inzwischen verlassen oder gelöscht: still zur privaten Bibliothek (Review Focus 3)
      if (stale()) return;
      if (e.status === 404 && sc !== "private") { scope = "private"; saveScope(scope); return load(); }
      throw e;
    }
    if (stale()) return;
    teams = t.teams;
    shownScope = sc;
    scope = sc;
    if (teamsOk) saveScope(sc);   // gemerkt wird nur ein geladener Bereich; er bleibt, wenn nur die Teams-Liste fehlte
    menuClose?.();
    list = l;
    drawScopes();
    const cur = rememberedProjectId();
    cards = new Map(list.map(p => [p.id, card(p, p.id === cur)]));
    lower = new Map(list.map(p => [p.id, p.name.toLowerCase()]));
    draw();
  }
  // gescheitert: wieder der angezeigte Bereich, damit derselbe Chip erneut klickbar ist
  const reload = () => load().catch(e => { scope = shownScope; fail(e); });

  function drawScopes() {
    const chip = (sc, label) => h("button", { class: "chip", type: "button", "aria-pressed": String(sc === shownScope),
      onclick: () => { if (sc === scope) return; scope = sc; reload(); } }, label);
    const hadFocus = scopeBar.contains(document.activeElement);
    clear(scopeBar, chip("private", "Privat"), teams.map(t => chip(`team:${t.id}`, t.name)));
    scopeBar.hidden = !teams.length;   // ohne Team wie bisher nur die private Bibliothek
    if (hadFocus) scopeBar.querySelector("[aria-pressed=true]")?.focus();   // Tastaturfokus bleibt im Schalter
    const t = teams.find(x => `team:${x.id}` === shownScope);
    newBtn.disabled = t?.my_role === "lesend";
    newBtn.title = newBtn.disabled ? "Mit der Rolle Lesend lassen sich keine Projekte anlegen" : "";
  }

  async function open(p, path) {
    if (opening) return;   // Doppelklick: nur einmal laden
    opening = true;
    try {
      const proj = await api(`/api/projects/${p.id}`);
      if (!main.isConnected) return;   // inzwischen andere Seite
      S.project = proj;
      rememberProject();
      go(path);
    } catch (e) { fail(e); if (main.isConnected) reload(); }
    finally { opening = false; }
  }

  function sorted() {
    const out = list.filter(p => (view.archived || !p.archived) && (!query || lower.get(p.id).includes(query)));
    const by = { updated: (a, b) => String(b.updated_at).localeCompare(String(a.updated_at)) || b.id - a.id,
      created: (a, b) => String(b.created_at).localeCompare(String(a.created_at)) || b.id - a.id,
      name: (a, b) => COLL.compare(a.name, b.name) || b.id - a.id }[view.sort];
    return out.sort(by);
  }

  function draw() {
    menuClose?.();
    tools.hidden = !list.length;
    if (!list.length) { clear(grid, emptyState()); grid.classList.add("one"); return; }
    grid.classList.remove("one");
    const shown = sorted();
    if (!shown.length) {
      const onlyArchived = !query && !view.archived && list.every(p => p.archived);
      clear(grid, h("div", { class: "empty card" }, icon("folder", 32),
        onlyArchived ? "Alle Projekte sind archiviert. „Archivierte zeigen“ blendet sie ein." : "Kein Projekt passt zur Suche."));
      grid.classList.add("one");
      return;
    }
    grid.replaceChildren(...shown.map(p => cards.get(p.id)));
  }

  function emptyState() {
    const t = teams.find(x => `team:${x.id}` === shownScope);
    if (t) {
      return h("section", { class: "empty card" }, icon("folder", 32), `Im Team „${t.name}“ gibt es noch keine Projekte.`,
        t.my_role === "lesend" ? null : h("button", { class: "btn sm primary", onclick: () => createHere(t.id) }, icon("plus", 16), "Neues Projekt"));
    }
    const st = (n, title, body) => h("li", {}, h("span", { class: "num" }, n), h("span", {}, h("strong", {}, title), h("br"), body));
    return h("section", { class: "card", "aria-labelledby": "start-h" },
      h("h2", { id: "start-h" }, "So geht es los"),
      h("ol", { class: "nextsteps libstart" },
        st("1", "Messunterlage drucken", h("a", { href: "/anleitung#unterlage", class: "small" }, "PDF erzeugen und richtig drucken")),
        st("2", "Werkstück fotografieren", h("a", { href: "/anleitung#fotografieren", class: "small" }, "Tipps zum Fotografieren")),
        st("3", "Neues Projekt anlegen", h("button", { class: "btn sm primary", style: { marginTop: "6px" }, onclick: () => createHere(null) }, icon("plus", 16), "Neues Projekt"))));
  }

  function thumb(p) {
    const ph = () => h("div", { class: "ph" }, icon("camera", 30), h("span", { class: "small" }, "Noch keine Fotos"));
    if (!p.thumb?.url) return h("div", { class: "pthumb" }, ph());
    const img = h("img", { src: p.thumb.url, alt: "", loading: "lazy", decoding: "async" });
    const box = h("div", { class: "pthumb" }, img,
      p.thumb.kind === "model" ? h("span", { class: "badge3d", title: "Bild des 3D-Modells" }, icon("cube", 14), "3D") : null);
    img.addEventListener("error", () => clear(box, ph()), { once: true });   // Bild fehlt: Platzhalter
    return box;
  }

  // Einträge im Menü „…“ nach den Rechten am Projekt (p.rights vom Server, Spec Teams §7); nicht erlaubte Einträge fehlen
  function menuItems(p, item) {
    const r = projectRights(p), targets = writableTeams();
    return [
      r.write ? item("Umbenennen …", () => rename(p)) : null,
      r.write ? item(p.archived ? "Wiederherstellen" : "Archivieren", () => archive(p)) : null,
      r.move && p.team_id == null && targets.length ? item("In Team verschieben …", () => moveToTeam(p)) : null,
      r.move && p.team_id != null ? item("In privat verschieben", () => moveToPrivate(p)) : null,
      r.copy && p.team_id == null && targets.length ? item("In Team kopieren …", () => copyToTeam(p)) : null,
      r.copy && p.team_id != null ? item("In privat kopieren", () => copyToPrivate(p)) : null,
      r.delete ? h("div", { class: "sep" }) : null,
      r.delete ? item("Löschen …", () => remove(p), "danger") : null,
    ];
  }

  function card(p, isCur) {
    const lj = p.last_job;
    const menuBtn = h("button", { class: "iconbtn", type: "button", "aria-label": `Weitere Aktionen für ${p.name}`, "aria-haspopup": "menu", "aria-expanded": "false" }, icon("dots"));
    const menu = h("div", { class: "menu", role: "menu", hidden: true });
    const item = (label, fn, cls = "") => h("button", { role: "menuitem", class: cls, type: "button", tabindex: "-1",
      onclick: async ev => { ev.stopPropagation(); closeMenu(false); try { await fn(); } catch (e) { fail(e); } } }, label);
    const entries = menuItems(p, item);
    clear(menu, entries);
    const items = () => [...menu.querySelectorAll("[role=menuitem]")];
    function closeMenu(focusBtn = true) {
      if (menu.hidden) return;
      menu.hidden = true; menuBtn.setAttribute("aria-expanded", "false");
      if (menuClose === close) menuClose = null;
      if (focusBtn) menuBtn.focus();
    }
    const close = () => closeMenu(false);
    function openMenu(focusIdx = 0) {
      menuClose?.();
      menu.hidden = false; menuBtn.setAttribute("aria-expanded", "true");
      menuClose = close;
      items()[focusIdx]?.focus();
    }
    menuBtn.addEventListener("click", ev => { ev.stopPropagation(); if (menu.hidden) openMenu(); else closeMenu(); });
    menuBtn.addEventListener("keydown", ev => {
      if (ev.key === "ArrowDown") { ev.preventDefault(); openMenu(0); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); openMenu(items().length - 1); }
    });
    menu.addEventListener("click", ev => ev.stopPropagation());
    menu.addEventListener("keydown", ev => {
      const it = items(), i = it.indexOf(document.activeElement);
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeMenu(); }
      else if (ev.key === "ArrowDown") { ev.preventDefault(); it[(i + 1) % it.length].focus(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); it[(i - 1 + it.length) % it.length].focus(); }
      else if (ev.key === "Home") { ev.preventDefault(); it[0].focus(); }
      else if (ev.key === "End") { ev.preventDefault(); it[it.length - 1].focus(); }
      else if (ev.key === "Tab") closeMenu(false);
    });

    const badges = [isCur ? h("span", { class: "badge info" }, "Zuletzt geöffnet") : null,
      p.archived ? h("span", { class: "badge off" }, "archiviert") : null,
      p.my_role === "lesend" ? h("span", { class: "badge off" }, ROLE_TEXT.lesend) : null].filter(Boolean);
    const stop = fn => ev => { ev.stopPropagation(); fn(); };
    const el = h("article", { class: `pcard${p.archived ? " archived" : ""}${isCur ? " current" : ""}`, "aria-label": p.name,
      onclick: ev => { if (!ev.target.closest("button,a,.menu")) open(p, "/fotos"); } },
      thumb(p),
      h("div", { class: "pbody" },
        badges.length ? h("div", { class: "chips" }, badges) : null,
        h("h2", { class: "pname", title: p.name }, p.name),
        p.team_id != null ? h("span", { class: "small muted pcreator" }, creatorText(p)) : null,
        h("span", { class: "small muted" }, `${plural(p.n_photos, "Foto", "Fotos")} · ${plural(p.n_measurements, "Maß", "Maße")}`),
        h("span", { class: "small muted" }, `Zuletzt geändert ${dt(p.updated_at)}`),
        lj ? h("span", { class: "pjob small" }, jobBadge(lj.status),
          h("span", { class: "pjobname" }, `Auftrag ${lj.name}${lj.current_version ? ` · v${lj.current_version}` : ""}`)) : null),
      h("div", { class: "pacts" },
        h("button", { class: "btn sm primary", type: "button", onclick: stop(() => open(p, "/fotos")) }, "Öffnen"),
        h("button", { class: "btn sm", type: "button", onclick: stop(() => open(p, "/messen")) }, "Messen"),
        lj ? h("button", { class: "btn sm", type: "button", onclick: stop(() => open(p, `/cad/${lj.id}`)) }, icon("cube", 14), "Modell") : null,
        entries.some(Boolean) ? h("div", { class: "rel", style: { marginLeft: "auto" } }, menuBtn, menu) : null));
    return el;
  }

  const writableTeams = () => teams.filter(t => t.my_role === "leiter" || t.my_role === "mitglied");
  function pickTeam(title, label) {
    const sel = h("select", { class: "input", "aria-label": "Team" }, writableTeams().map(t => h("option", { value: t.id }, t.name)));
    return dialog({ title, body: h("div", { class: "field" }, h("label", {}, "Team"), sel,
      h("span", { class: "hint" }, "Nur Teams, in denen du Leiter oder Mitglied bist.")),
    actions: [{ label: "Abbrechen", value: null }, { label, primary: true, submit: true, run: () => Number(sel.value) || false }] });
  }

  async function rename(p) {
    const inp = h("input", { class: "input", value: p.name, maxlength: 120, "aria-label": "Name" });
    const name = await dialog({ title: "Projekt umbenennen", body: h("div", { class: "field" }, h("label", {}, "Name"), inp),
      actions: [{ label: "Abbrechen", value: null }, { label: "Speichern", primary: true, submit: true, run: () => inp.value.trim() || false }] });
    if (!name || name === p.name) return;
    const r = await api(`/api/projects/${p.id}`, { method: "PATCH", body: { name } });
    if (S.project?.id === p.id) S.project = r;
    toast("Projekt umbenannt", "ok");
    await reload();
  }
  async function archive(p) {
    const r = await api(`/api/projects/${p.id}`, { method: "PATCH", body: { archived: !p.archived } });
    if (S.project?.id === p.id) S.project = r;
    toast(p.archived ? "Projekt wiederhergestellt" : "Projekt archiviert", "ok");
    await reload();
  }
  async function moveToTeam(p) {
    const tid = await pickTeam(`„${p.name}“ in ein Team verschieben`, "Verschieben");
    if (!tid) return;
    const r = await api(`/api/projects/${p.id}/move`, { method: "POST", body: { team_id: tid } });
    if (S.project?.id === p.id) S.project = r;
    toast(`In „${r.team_name}“ verschoben – die CAD-Aufträge sind mitgekommen`, "ok");
    await reload();
  }
  async function moveToPrivate(p) {
    if (!await confirmDlg(`„${p.name}“ in privat verschieben?`,
      "Das Projekt verlässt das Team und gehört danach dir; die CAD-Aufträge kommen mit. Die anderen Mitglieder sehen es nicht mehr.",
      "In privat verschieben")) return;
    const r = await api(`/api/projects/${p.id}/move`, { method: "POST", body: { team_id: null } });
    if (S.project?.id === p.id) S.project = r;
    toast("In die private Bibliothek verschoben", "ok");
    await reload();
  }
  // Kopieren (Spec Teams §4): danach zeigt die Bibliothek den Zielbereich mit der Kopie
  async function copyTo(p, teamId) {
    const r = await api(`/api/projects/${p.id}/copy`, { method: "POST", body: { team_id: teamId } });
    scope = teamId ? `team:${teamId}` : "private";
    saveScope(scope);
    toast(`Kopie „${r.name}“ ${teamId ? `in „${r.team_name}“` : "in der privaten Bibliothek"} angelegt – mit Fotos, Maßen und der gültigen Version jedes CAD-Auftrags`, "ok");
    await reload();
  }
  async function copyToTeam(p) {
    const tid = await pickTeam(`„${p.name}“ in ein Team kopieren`, "Kopieren");
    if (tid) await copyTo(p, tid);
  }
  async function copyToPrivate(p) {
    if (!await confirmDlg(`„${p.name}“ in privat kopieren?`,
      "Die Kopie enthält Fotos, Messungen, Teile, gemerkte Werte und von jedem fertigen CAD-Auftrag die aktuelle Version; sie gehört dir. Das Original bleibt im Team.",
      "In privat kopieren")) return;
    await copyTo(p, null);
  }
  async function remove(p) {
    const who = p.team_id != null ? `für alle Mitglieder von „${p.team_name}“ ` : "";
    if (!await confirmDlg(`„${p.name}“ löschen?`,
      `Fotos, Messungen, Teile und die am Modell gemerkten Messschieberwerte dieses Projekts werden ${who}endgültig gelöscht. `
      + "Die CAD-Aufträge bleiben unter „Meine Aufträge“ ihrer Ersteller erhalten, aber ohne Fotos für den Foto-Abgleich.", "Endgültig löschen", true)) return;
    await api(`/api/projects/${p.id}`, { method: "DELETE" });
    if (rememberedProjectId() === p.id) forgetProject();
    if (S.project?.id === p.id) S.project = null;
    toast("Projekt gelöscht", "ok");
    await reload();
  }

  await load();
}
