// Schritt 1: Projektbibliothek – alle Werkstücke mit Vorschaubild, Start für neue Projekte
import { api, h, clear, icon, dt, toast, fail, dialog, confirmDlg } from "./lib.js";
import { S, go, onLeave, rememberProject, jobBadge } from "./app.js";

const SORTS = { updated: "Zuletzt geändert", name: "Name", created: "Angelegt" };
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function loadView() {
  try {
    const v = JSON.parse(localStorage.getItem("lib.view") || "{}");
    return { sort: Object.hasOwn(SORTS, v.sort) ? v.sort : "updated", archived: v.archived === true };
  } catch { return { sort: "updated", archived: false }; }
}
function saveView(v) { try { localStorage.setItem("lib.view", JSON.stringify(v)); } catch { /* */ } }
const remKey = () => `mu.project.${S.me.id}`;
function remembered() { try { return Number(localStorage.getItem(remKey())) || null; } catch { return null; } }
function forget() { try { localStorage.removeItem(remKey()); } catch { /* */ } }

// Neues Projekt: leerer Name ist erlaubt, der Server vergibt dann Datum und Uhrzeit
export async function newProject() {
  const inp = h("input", { class: "input", placeholder: "z. B. Halteplatte Lagersitz", maxlength: 120, "aria-label": "Name" });
  const r = await dialog({ title: "Neues Projekt",
    body: h("div", { class: "field" }, h("label", {}, "Name"), inp, h("span", { class: "hint" }, "Leer lassen = Name aus Datum und Uhrzeit.")),
    actions: [{ label: "Abbrechen", value: null }, { label: "Anlegen", primary: true, submit: true, run: () => ({ name: inp.value.trim() }) }] });
  if (!r) return;
  try {
    S.project = await api("/api/projects", { method: "POST", body: { name: r.name } });
    rememberProject();
    go("/fotos");
  } catch (e) { fail(e); }
}

export default async function (main) {
  const view = loadView();
  let list = [], query = "";
  const search = h("input", { class: "input", type: "search", placeholder: "Projekt suchen …", "aria-label": "Projekte durchsuchen", maxlength: 120 });
  const sortSel = h("select", { class: "input", "aria-label": "Sortierung" },
    Object.entries(SORTS).map(([k, t]) => h("option", { value: k, selected: k === view.sort }, t)));
  const archCb = h("input", { type: "checkbox", checked: view.archived });
  const grid = h("div", { class: "libgrid" });
  const tools = h("div", { class: "libtools" },
    h("div", { class: "libsearch" }, icon("search", 16), search),
    h("label", { class: "chips small" }, h("span", { class: "muted" }, "Sortieren"), sortSel),
    h("label", { class: "check small" }, archCb, "Archivierte zeigen"));
  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Projekte"),
      h("p", { class: "lead" }, "Alle Werkstücke mit Fotos, Maßen und CAD-Modellen. Von hier aus beginnt jedes neue Projekt.")),
    h("button", { class: "btn primary", onclick: newProject }, icon("plus"), "Neues Projekt")),
    tools, grid);

  search.addEventListener("input", () => { query = search.value.trim().toLowerCase(); draw(); });
  sortSel.addEventListener("change", () => { view.sort = sortSel.value; saveView(view); draw(); });
  archCb.addEventListener("change", () => { view.archived = archCb.checked; saveView(view); draw(); });

  // offenes Menü „…“: eines zur Zeit, Klick daneben schließt
  let menuClose = null;
  const outside = () => menuClose?.();
  document.addEventListener("click", outside);
  onLeave(() => document.removeEventListener("click", outside));

  async function load() {
    list = await api("/api/projects");
    if (main.isConnected) draw();
  }
  const reload = () => load().catch(fail);

  async function open(p, path) {
    try {
      S.project = await api(`/api/projects/${p.id}`);
      rememberProject();
      go(path);
    } catch (e) { fail(e); reload(); }
  }

  function sorted() {
    const out = list.filter(p => (view.archived || !p.archived) && (!query || p.name.toLowerCase().includes(query)));
    const by = { updated: (a, b) => String(b.updated_at).localeCompare(String(a.updated_at)) || b.id - a.id,
      created: (a, b) => String(b.created_at).localeCompare(String(a.created_at)) || b.id - a.id,
      name: (a, b) => a.name.localeCompare(b.name, "de", { sensitivity: "base" }) || b.id - a.id }[view.sort];
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
    const cur = remembered();
    clear(grid, shown.map(p => card(p, p.id === cur)));
  }

  function emptyState() {
    const st = (n, title, body) => h("li", {}, h("span", { class: "num" }, n), h("span", {}, h("strong", {}, title), h("br"), body));
    return h("section", { class: "card", "aria-labelledby": "start-h" },
      h("h2", { id: "start-h" }, "So geht es los"),
      h("ol", { class: "nextsteps libstart" },
        st("1", "Messunterlage drucken", h("a", { href: "/anleitung#unterlage", class: "small" }, "PDF erzeugen und richtig drucken")),
        st("2", "Werkstück fotografieren", h("a", { href: "/anleitung#fotografieren", class: "small" }, "Tipps zum Fotografieren")),
        st("3", "Neues Projekt anlegen", h("button", { class: "btn sm primary", style: { marginTop: "6px" }, onclick: newProject }, icon("plus", 16), "Neues Projekt"))));
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

  function card(p, isCur) {
    const lj = p.last_job;
    const menuBtn = h("button", { class: "iconbtn", type: "button", "aria-label": `Weitere Aktionen für ${p.name}`, "aria-haspopup": "menu", "aria-expanded": "false" }, icon("dots"));
    const menu = h("div", { class: "menu", role: "menu", hidden: true });
    const item = (label, fn, cls = "") => h("button", { role: "menuitem", class: cls, type: "button", tabindex: "-1",
      onclick: async ev => { ev.stopPropagation(); closeMenu(false); try { await fn(); } catch (e) { fail(e); } } }, label);
    clear(menu,
      item("Umbenennen …", () => rename(p)),
      item(p.archived ? "Wiederherstellen" : "Archivieren", () => archive(p)),
      h("div", { class: "sep" }),
      item("Löschen …", () => remove(p), "danger"));
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

    const stop = fn => ev => { ev.stopPropagation(); fn(); };
    const el = h("article", { class: `pcard${p.archived ? " archived" : ""}${isCur ? " current" : ""}`, "aria-label": p.name,
      onclick: ev => { if (!ev.target.closest("button,a,.menu")) open(p, "/fotos"); } },
      thumb(p),
      h("div", { class: "pbody" },
        isCur || p.archived ? h("div", { class: "chips" }, isCur ? h("span", { class: "badge info" }, "Zuletzt geöffnet") : null,
          p.archived ? h("span", { class: "badge off" }, "archiviert") : null) : null,
        h("h2", { class: "pname", title: p.name }, p.name),
        h("span", { class: "small muted" }, `${plural(p.n_photos, "Foto", "Fotos")} · ${plural(p.n_measurements, "Maß", "Maße")}`),
        h("span", { class: "small muted" }, `Zuletzt geändert ${dt(p.updated_at)}`),
        lj ? h("span", { class: "pjob small" }, jobBadge(lj.status),
          h("span", { class: "pjobname" }, `Auftrag ${lj.name}${lj.current_version ? ` · v${lj.current_version}` : ""}`)) : null),
      h("div", { class: "pacts" },
        h("button", { class: "btn sm primary", type: "button", onclick: stop(() => open(p, "/fotos")) }, "Öffnen"),
        h("button", { class: "btn sm", type: "button", onclick: stop(() => open(p, "/messen")) }, "Messen"),
        lj ? h("button", { class: "btn sm", type: "button", onclick: stop(() => open(p, `/cad/${lj.id}`)) }, icon("cube", 14), "Modell") : null,
        h("div", { class: "rel", style: { marginLeft: "auto" } }, menuBtn, menu)));
    return el;
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
  async function remove(p) {
    if (!await confirmDlg(`„${p.name}“ löschen?`,
      "Fotos, Messungen, Teile und die am Modell gemerkten Messschieberwerte dieses Projekts werden endgültig gelöscht. "
      + "Die CAD-Aufträge bleiben unter „Meine Aufträge“ erhalten.", "Endgültig löschen", true)) return;
    await api(`/api/projects/${p.id}`, { method: "DELETE" });
    if (remembered() === p.id) forget();
    if (S.project?.id === p.id) S.project = null;
    toast("Projekt gelöscht", "ok");
    await reload();
  }

  await load();
}
