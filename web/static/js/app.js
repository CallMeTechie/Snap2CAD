// Snap2CAD – Einstieg, Router, Kopfzeile, Anmeldung, Konto, Verwaltung
import { api, h, clear, icon, LOGO, toast, fail, dialog, confirmDlg, dt, until, initials, num, debounce, strength,
  STRENGTH_TEXT, parseNum, copyText } from "./lib.js";
import { groupProjects } from "./rights.js";

export const S = { me: null, project: null, leave: [] };
const app = document.getElementById("app");

// ------------------------------------------------------------------ Router
const routes = [];
function route(re, fn, opts = {}) { routes.push({ re, fn, ...opts }); }

export function go(path, replace = false) {
  const u = new URL(path, location.href);
  if (u.pathname + u.search === location.pathname + location.search) {
    // dieselbe Seite: nur die Sprungmarke anpassen (ohne Marke = oben), nicht an die alte springen
    if (u.hash !== location.hash) history.replaceState({}, "", path);
    render();
    return;
  }
  history[replace ? "replaceState" : "pushState"]({}, "", path);
  render();
}
export function onLeave(fn) { S.leave.push(fn); }

// Sprungmarke (#abschnitt) der aktuellen Seite anspringen; false = keine passende Stelle
function jumpToHash() {
  let id = "";
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { /* kaputte Kodierung */ }
  const el = id ? document.getElementById(id) : null;
  if (el) el.scrollIntoView({ block: "start" });
  return !!el;
}
let shownPath = null;   // Pfad und Suche der gezeigten Seite: Zurueck zwischen Sprungmarken baut die Seite nicht neu auf
window.addEventListener("popstate", () => { if (location.pathname + location.search === shownPath) jumpToHash(); else render(); });
document.addEventListener("click", ev => {
  const a = ev.target.closest("a");
  if (!a || a.target || a.hasAttribute("download") || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith("/static/")) return;
  ev.preventDefault();
  if (url.hash && url.pathname + url.search === shownPath) {   // Sprungmarke auf derselben Seite
    if (url.hash !== location.hash) history.pushState({}, "", url.hash);
    jumpToHash();
    return;
  }
  go(url.pathname + url.search + url.hash);
});

let kurzhilfe = null, khLoading = false;   // Modul der Kurzhilfe als einmal geladenes Promise
// Kurzhilfe: ? oder F1 auf jeder angemeldeten Seite mit Kopfzeile, nicht in Eingabefeldern
document.addEventListener("keydown", ev => {
  if (ev.key !== "?" && ev.key !== "F1") return;
  if (ev.ctrlKey || ev.metaKey || ev.altKey || !S.me || !document.querySelector("header.top")) return;
  if (ev.target instanceof Element && ev.target.closest("input,textarea,select,[contenteditable]")) return;
  if (document.querySelector("dialog[open]")) return;   // anderer Dialog offen (die Kurzhilfe schliesst sich selbst)
  ev.preventDefault();
  if (khLoading) return;   // Modul laedt noch: weitere ? / F1 ignorieren
  khLoading = true;
  (kurzhilfe ??= import("./kurzhilfe.js"))
    .then(m => m.toggleShortcuts(location.pathname))
    .catch(e => { kurzhilfe = null; fail(e); })
    .finally(() => { khLoading = false; });
});

api.onUnauthorized = () => { S.me = null; if (!location.pathname.startsWith("/login")) go("/login", true); };
api.onMustChange = () => { if (S.me) S.me.must_change_pw = 1; go("/passwort", true); };

export async function refreshMe() {
  const r = await api("/api/me");
  S.status = r;
  S.me = r.user;
  return r;
}

let renderGen = 0;   // nur das juengste Rendern darf scrollen
async function render() {
  const gen = ++renderGen;
  for (const fn of S.leave.splice(0)) { try { fn(); } catch (e) { console.error(e); } }
  const path = location.pathname;
  shownPath = path + location.search;
  let m, r;
  for (r of routes) { m = path.match(r.re); if (m) break; m = null; }
  if (!m) { r = routes.find(x => x.notFound); m = []; }
  if (S.status?.setup?.required && path !== "/setup") { go("/setup", true); return; }
  if (!r.public && !S.me) { go("/login" + (path !== "/" ? `?next=${encodeURIComponent(path)}` : ""), true); return; }
  if (S.me && S.me.must_change_pw && !r.public && path !== "/passwort") { go("/passwort", true); return; }
  if (r.admin && S.me?.role !== "admin") { go("/", true); return; }
  try {
    if (r.public || r.bare) await r.fn(app, ...m.slice(1));
    else {
      const main = h("main", { class: "page", id: "main" });
      clear(app, header(r.step), main);
      await r.fn(main, ...m.slice(1));
    }
  } catch (e) {
    fail(e);
  }
  if (gen !== renderGen) return;
  if (!jumpToHash()) window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ Kopfzeile
const STEPS = [["/", "Projekte"], ["/fotos", "Fotos prüfen"], ["/messen", "Messen"], ["/cad", "CAD-Modell"]];

function statusPill() {
  const st = S.status || {};
  let pill = null;
  if (st.ai_fake) pill = h("span", { class: "pill" }, h("span", { class: "dot warn" }), "Testmodus (AI_FAKE)");
  else if (!st.ai) pill = h("span", { class: "pill" }, h("span", { class: "dot off" }), "KI nicht eingerichtet");
  const sb = st.sandbox ? null : h("span", { class: "pill" }, h("span", { class: "dot err" }), "Sandbox offline");
  return [pill, sb];
}

function header(step) {
  const u = S.me;
  const locked = !!u.must_change_pw;
  const nav = h("nav", { class: "steps", "aria-label": "Arbeitsschritte" }, STEPS.map(([href, lbl], i) =>
    h("a", { class: "step", href, "aria-current": step === i + 1 ? "page" : null, "aria-disabled": locked ? "true" : null },
      h("span", { class: "n" }, i + 1), h("span", { class: "lbl" }, lbl))));
  const menu = h("div", { class: "menu", hidden: true, role: "menu" });
  const btn = h("button", { class: "userbtn", "aria-haspopup": "menu", "aria-expanded": "false",
    "aria-label": `Benutzermenü: ${u.username}${u.role === "admin" ? ", Administrator" : ""}` },
    h("span", { class: "avatar" }, initials(u)), h("span", { class: "uname" }, u.username),
    u.role === "admin" ? h("span", { class: "tag" }, "ADMIN") : null, icon("chevron", 14));
  const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  btn.addEventListener("click", ev => {
    ev.stopPropagation();
    const open = menu.hidden;
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) buildMenu();
  });
  document.addEventListener("click", close);
  onLeave(() => document.removeEventListener("click", close));
  function buildMenu() {
    const us = S.status?.usage;
    clear(menu,
      h("div", { class: "info" }, h("strong", { style: { color: "var(--text)" } }, u.display_name || u.username),
        h("br"), us ? `CAD diesen Monat: ${us.used} / ${us.quota ?? "∞"}` : ""),
      h("div", { class: "sep" }),
      locked ? null : h("a", { href: "/auftraege", role: "menuitem" }, icon("list"), "Meine Aufträge"),
      locked ? null : h("a", { href: "/anleitung", role: "menuitem" }, icon("help"), "Anleitung"),
      locked ? null : h("a", { href: "/konto", role: "menuitem" }, icon("key"), "Konto und Passwort"),
      !locked && u.role === "admin" ? h("a", { href: "/admin", role: "menuitem" }, icon("users"), "Benutzerverwaltung") : null,
      h("div", { class: "sep" }),
      h("button", { role: "menuitem", onclick: logout }, icon("logout"), "Abmelden"));
  }
  const hdr = h("header", { class: "top" },
    h("a", { class: "brand", href: "/" }, LOGO(), "Snap2CAD"),
    nav,
    h("div", { class: "top-right" }, statusPill(),
      locked ? null : h("a", { class: "iconbtn helpbtn", href: "/anleitung", title: "Anleitung (Taste ?)", "aria-label": "Anleitung (Taste ?)" }, icon("help", 20)),
      h("div", { class: "usermenu" }, btn, menu)));
  return hdr;
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* */ }
  S.me = null; S.project = null;
  go("/login");
}

// ------------------------------------------------------------------ Projekt
export async function ensureProject(force = false) {
  if (S.project && !force) return S.project;
  const pid = rememberedProjectId();
  if (pid) {
    try { S.project = await api(`/api/projects/${pid}`); return S.project; } catch { /* weiter */ }
  }
  S.project = await api("/api/projects/current");
  rememberProject();
  return S.project;
}
let reloadSeq = 0;
export async function reloadProject() {
  // nur die juengste Antwort uebernehmen: mehrere Aenderungen kurz hintereinander laden parallel neu
  const n = ++reloadSeq, id = S.project.id;
  const p = await api(`/api/projects/${id}`);
  if (n === reloadSeq && S.project?.id === id) S.project = p;
  return S.project;
}
// zuletzt geoeffnetes Projekt je Benutzer im Browser
export const projectKey = () => `mu.project.${S.me.id}`;
export function rememberProject() {
  try { localStorage.setItem(projectKey(), S.project.id); } catch { /* */ }
}
export function rememberedProjectId() {
  try { return Number(localStorage.getItem(projectKey())) || null; } catch { return null; }
}
export function forgetProject() {
  try { localStorage.removeItem(projectKey()); } catch { /* */ }
}

export function projectPicker(onChange) {
  const sel = h("select", { class: "input", "aria-label": "Projekt", style: { minWidth: "220px", maxWidth: "320px" } });
  // gruppiert nach „Privat“ und je Team (Spec Teams §7), Projekte aus scope=all
  const fill = list => {
    const opt = p => h("option", { value: p.id, selected: p.id === S.project.id },
      `${p.name}${p.archived ? " (archiviert)" : ""} · ${p.n_photos} Fotos · ${p.n_measurements} Maße`);
    clear(sel, groupProjects(list).map(g => h("optgroup", { label: g.label }, g.items.map(opt))),
      h("option", { value: "new" }, "+ Neues Projekt …"), h("option", { value: "rename" }, "Projekt umbenennen …"));
  };
  const load = () => api("/api/projects?scope=all");
  load().then(fill).catch(fail);
  // data-ro="ok": bleibt in der Rolle Lesend bedienbar (Projekt wechseln)
  const wrap = h("label", { class: "field", style: { gap: "4px" }, "data-ro": "ok" }, h("span", { class: "label" }, "Projekt"), sel);
  wrap.refresh = () => load().then(fill).catch(() => {});
  sel.addEventListener("change", async () => {
    const v = sel.value;
    try {
      if (v === "new" || v === "rename") {
        const inp = h("input", { class: "input", value: v === "rename" ? S.project.name : "", placeholder: "z. B. Halteplatte Lagersitz", maxlength: 120 });
        const name = await dialog({ title: v === "new" ? "Neues Projekt" : "Projekt umbenennen",
          body: h("div", { class: "field" }, h("label", {}, "Name"), inp),
          actions: [{ label: "Abbrechen", value: null }, { label: "Speichern", primary: true, submit: true, run: () => inp.value.trim() || false }] });
        if (name) {
          if (v === "new") S.project = await api("/api/projects", { method: "POST", body: { name } });
          else S.project = await api(`/api/projects/${S.project.id}`, { method: "PATCH", body: { name } });
          rememberProject();
        }
      } else {
        S.project = await api(`/api/projects/${v}`);
        rememberProject();
      }
      onChange();
    } catch (e) { fail(e); }
    fill(await load());
  });
  return wrap;
}

// ------------------------------------------------------------------ Passwortfelder
export function pwInput(id, autocomplete, attrs = {}) {
  const input = h("input", { id, type: "password", autocomplete, required: true, maxlength: 256, ...attrs });
  const tog = h("button", { type: "button", "aria-label": "Passwort anzeigen", title: "Passwort anzeigen" }, icon("eye"));
  tog.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    clear(tog, icon(show ? "eyeoff" : "eye"));
    tog.setAttribute("aria-label", show ? "Passwort verbergen" : "Passwort anzeigen");
  });
  return { wrap: h("div", { class: "pw" }, input, tog), input };
}

function strengthUI(input, getUser, { initial = false } = {}) {
  const meter = h("div", { class: "meter", "aria-hidden": "true" }, h("span"), h("span"), h("span"), h("span"));
  const txt = h("span", { class: "hint" });
  const rules = [
    ["len", "Mindestens 12 Zeichen"],
    initial ? ["init", "Nicht das Startpasswort"] : null,
    ["user", "Enthält nicht den Benutzernamen"],
    ["common", "Nicht auf der Liste häufiger Passwörter"],
  ].filter(Boolean);
  const items = Object.fromEntries(rules.map(([k, t]) => [k, h("li", {}, icon("check", 14), t)]));
  const ul = h("ul", { class: "rules", id: `${input.id}-rules` }, Object.values(items));
  input.setAttribute("aria-describedby", ul.id);
  let server = [];
  const check = debounce(async () => {
    try {
      const r = await api("/api/password-check", { method: "POST", body: { password: input.value, username: getUser() } });
      server = r.problems; upd();
    } catch { /* */ }
  }, 350);
  function upd() {
    const pw = input.value, u = (getUser() || "").toLowerCase();
    const st = { len: pw.length >= 12, user: !(u.length >= 3 && pw.toLowerCase().includes(u)),
      common: !server.some(p => p.startsWith("zu einfach")), init: !server.some(p => p.includes("Initialpasswort")) };
    for (const [k, li] of Object.entries(items)) li.className = pw ? (st[k] ? "ok" : "bad") : "";
    const s = strength(pw);
    meter.className = `meter s${s}`;
    txt.textContent = pw ? (s <= 2 ? `${STRENGTH_TEXT[s]} · länger machen oder Wörter kombinieren` : STRENGTH_TEXT[s]) : "";
  }
  input.addEventListener("input", () => { upd(); check(); });
  return h("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } }, meter, txt, ul);
}

function errBox() { return h("div", { class: "note err", role: "alert", hidden: true }); }
function showErr(box, msg) { clear(box, icon("warn"), h("span", {}, msg)); box.hidden = !msg; }

// ------------------------------------------------------------------ Ersteinrichtung
route(/^\/setup$/, async root => {
  const st = S.status?.setup;
  if (!st?.required) { go(S.me ? "/" : "/login", true); return; }
  const page = h("div", { class: "auth-page" }, h("div", { class: "auth-brand" }, h("span", { class: "b" }, LOGO(), "Snap2CAD"),
    h("span", { class: "muted" }, "Bauteile per Foto vermessen und als CAD-Modell nachbauen")));
  clear(root, page);
  if (!st.allowed) {
    page.append(h("div", { class: "auth-card" }, h("h1", { style: { fontSize: "22px" } }, "Einrichtung gesperrt"),
      h("div", { class: "note err" }, icon("lock"), h("span", {}, "Snap2CAD ist noch nicht eingerichtet. Die Einrichtung ist aus Sicherheitsgründen nur aus dem lokalen Netz möglich. Bitte die Seite im Heimnetz oder per VPN öffnen.")),
      h("p", { class: "hint" }, "Wer die Einrichtung bewusst über das Internet durchführen will, setzt vorübergehend SETUP_ALLOW_PUBLIC=1.")));
    return;
  }
  const err = errBox();
  const dn = h("input", { id: "sdn", class: "input", autocomplete: "name", maxlength: 80, placeholder: "z. B. Max Mustermann" });
  const un = h("input", { id: "sun", class: "input", autocomplete: "username", required: true, maxlength: 32, autocapitalize: "none", spellcheck: "false", value: "admin" });
  const em = h("input", { id: "sem", class: "input", type: "email", autocomplete: "email", maxlength: 200, placeholder: "name@beispiel.de" });
  const pw = pwInput("spw", "new-password"), pw2 = pwInput("spw2", "new-password");
  const key = pwInput("skey", "off", { required: !st.key_optional, maxlength: 400, spellcheck: "false", autocapitalize: "none", placeholder: "sk-ant-…" });
  key.wrap.querySelector("button").setAttribute("aria-label", "Schlüssel anzeigen");
  dn.addEventListener("input", () => {
    if (!un.dataset.touched) un.value = dn.value.trim().toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss").replace(/\s+/g, ".").replace(/[^a-z0-9._-]/g, "").slice(0, 32) || "admin";
  });
  un.addEventListener("keydown", () => { un.dataset.touched = "1"; });
  const submit = h("button", { class: "btn primary big wide", type: "submit" }, "Einrichtung abschließen");
  const keyField = st.key_from_env
    ? h("div", { class: "note ok" }, icon("check"), h("span", {}, "Der API-Schlüssel ist bereits über die Umgebungsvariable ANTHROPIC_API_KEY gesetzt."))
    : h("div", { class: "field" }, h("label", { for: "skey" }, "Anthropic-API-Schlüssel", st.key_optional ? h("span", { class: "muted", style: { fontWeight: 400 } }, " (optional im Testmodus)") : null), key.wrap,
      h("span", { class: "hint" }, "Anlegen unter ", h("a", { href: "https://console.anthropic.com/settings/keys", target: "_blank", rel: "noopener noreferrer" }, "console.anthropic.com → API Keys"),
        ". Der Schlüssel wird vor dem Speichern bei Anthropic geprüft, liegt danach nur auf diesem Server und lässt sich unter Verwaltung → Einstellungen ändern."));
  page.append(h("form", { class: "auth-card w", "aria-labelledby": "s-h", onsubmit: async ev => {
    ev.preventDefault(); showErr(err, "");
    if (pw.input.value !== pw2.input.value) { showErr(err, "Die Passwörter stimmen nicht überein."); pw2.input.focus(); return; }
    submit.disabled = true;
    const label = submit.textContent;
    submit.textContent = key.input.value.trim() ? "Schlüssel wird geprüft …" : "Wird eingerichtet …";
    try {
      await api("/api/setup", { method: "POST", body: { username: un.value.trim(), display_name: dn.value.trim(), email: em.value.trim() || null,
        password: pw.input.value, api_key: st.key_from_env ? "" : key.input.value.trim() } });
      await refreshMe();
      toast("Snap2CAD ist eingerichtet. Willkommen!", "ok");
      go("/", true);
    } catch (e) {
      showErr(err, e.message);
      if (e.status === 409) { await refreshMe().catch(() => {}); go("/login", true); }
    } finally { submit.disabled = false; submit.textContent = label; }
  } },
  h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } }, h("h1", { id: "s-h", style: { fontSize: "24px" } }, "Snap2CAD einrichten"),
    h("p", { class: "lead" }, "Lege das Administrator-Konto an und verbinde die KI. Erst danach ist Snap2CAD nutzbar.")),
  err,
  h("h2", { style: { fontSize: "16px", margin: "4px 0 0" } }, "1 · Administrator-Konto"),
  h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", { for: "sdn" }, "Anzeigename"), dn),
    h("div", { class: "field" }, h("label", { for: "sun" }, "Benutzername"), un, h("span", { class: "hint" }, "3–32 Zeichen: a–z, 0–9, Punkt, Minus, Unterstrich"))),
  h("div", { class: "field" }, h("label", { for: "sem" }, "E-Mail ", h("span", { class: "muted", style: { fontWeight: 400 } }, "(optional)")), em,
    h("span", { class: "hint" }, "Damit kannst du dich auch per E-Mail anmelden.")),
  h("div", { class: "field" }, h("label", { for: "spw" }, "Passwort"), pw.wrap, strengthUI(pw.input, () => un.value)),
  h("div", { class: "field" }, h("label", { for: "spw2" }, "Passwort wiederholen"), pw2.wrap),
  h("h2", { style: { fontSize: "16px", margin: "8px 0 0" } }, "2 · KI verbinden"),
  keyField,
  submit,
  h("p", { class: "hint", style: { textAlign: "center" } }, "Diese Seite erscheint nur, solange noch kein Konto existiert.")));
  dn.focus();
}, { public: true });

// ------------------------------------------------------------------ Anmelden
route(/^\/login$/, async root => {
  if (S.me) { go("/", true); return; }
  const err = errBox();
  const user = h("input", { id: "u", class: "input", autocomplete: "username", required: true, maxlength: 200, autocapitalize: "none", spellcheck: "false" });
  const pw = pwInput("p", "current-password");
  const remember = h("input", { type: "checkbox" });
  const submit = h("button", { class: "btn primary big wide", type: "submit" }, "Anmelden");
  const form = h("form", { class: "auth-card", "aria-labelledby": "l-h", onsubmit: async ev => {
    ev.preventDefault();
    submit.disabled = true; showErr(err, "");
    try {
      await api("/api/auth/login", { method: "POST", body: { username: user.value, password: pw.input.value, remember: remember.checked } });
      await refreshMe();
      const next = new URLSearchParams(location.search).get("next");
      go(S.me.must_change_pw ? "/passwort" : (next && next.startsWith("/") && !next.startsWith("//") ? next : "/"), true);
    } catch (e) {
      showErr(err, e.message); pw.input.value = ""; pw.input.setAttribute("aria-invalid", "true"); pw.input.focus();
    } finally { submit.disabled = false; }
  } },
  h("h1", { id: "l-h", style: { fontSize: "24px" } }, "Anmelden"), err,
  h("div", { class: "field" }, h("label", { for: "u" }, "Benutzername oder E-Mail"), user),
  h("div", { class: "field" }, h("label", { for: "p" }, "Passwort"), pw.wrap),
  h("label", { class: "check" }, remember, "Angemeldet bleiben (30 Tage)"),
  submit,
  h("p", { class: "hint" }, "Passwort vergessen? Ein Administrator kann dir einen Link zum Zurücksetzen erstellen."));
  clear(root, h("div", { class: "auth-page" },
    h("div", { class: "auth-brand" }, h("span", { class: "b" }, LOGO(), "Snap2CAD"),
      h("span", { class: "muted" }, "Bauteile per Foto vermessen und als CAD-Modell nachbauen")),
    form,
    h("p", { class: "hint", style: { textAlign: "center" } }, "Noch kein Konto? Die Registrierung ist nur über einen Einladungslink möglich."),
    h("span", { class: "xs muted" }, "selbst gehostet")));
  user.focus();
}, { public: true });

// ------------------------------------------------------------------ Passwort aendern (erzwungen)
route(/^\/passwort$/, async root => {
  const forced = !!S.me.must_change_pw;
  const err = errBox();
  const cur = pwInput("cur", "current-password");
  const nw = pwInput("new", "new-password");
  const rep = pwInput("rep", "new-password");
  const mail = h("input", { id: "mail", class: "input", type: "email", autocomplete: "email", placeholder: "name@beispiel.de", value: S.me.email || "" });
  const submit = h("button", { class: "btn primary big wide", type: "submit" }, forced ? "Passwort speichern und fortfahren" : "Passwort speichern");
  const form = h("form", { class: "card", style: { maxWidth: "560px", margin: "0 auto", width: "100%", gap: "18px" }, "aria-labelledby": "pw-h",
    onsubmit: async ev => {
      ev.preventDefault(); showErr(err, "");
      if (nw.input.value !== rep.input.value) { showErr(err, "Die beiden neuen Passwörter stimmen nicht überein."); rep.input.focus(); return; }
      submit.disabled = true;
      try {
        await api("/api/auth/change-password", { method: "POST", body: { current: cur.input.value, new: nw.input.value, email: mail.value || null } });
        await refreshMe();
        toast("Passwort geändert", "ok");
        go("/", true);
      } catch (e) { showErr(err, e.message); } finally { submit.disabled = false; }
    } },
    h("div", { class: "t", style: { display: "flex", flexDirection: "column", gap: "6px" } },
      h("h1", { id: "pw-h", style: { fontSize: "24px" } }, "Neues Passwort festlegen"),
      h("p", { class: "lead" }, forced ? "Erste Anmeldung mit dem Startpasswort. Bevor du weiterarbeiten kannst, musst du ein eigenes Passwort setzen." : "")),
    forced ? h("div", { class: "note warn" }, icon("lock"), h("span", {}, "Alle anderen Seiten bleiben gesperrt, bis das Passwort geändert ist.")) : null,
    err,
    h("div", { class: "field" }, h("label", { for: "cur" }, forced ? "Aktuelles Passwort (Startpasswort)" : "Aktuelles Passwort"), cur.wrap),
    h("div", { class: "field" }, h("label", { for: "new" }, "Neues Passwort"), nw.wrap, strengthUI(nw.input, () => S.me.username, { initial: forced })),
    h("div", { class: "field" }, h("label", { for: "rep" }, "Neues Passwort wiederholen"), rep.wrap),
    h("div", { class: "field" }, h("label", { for: "mail" }, "E-Mail-Adresse ", h("span", { class: "muted", style: { fontWeight: 400 } }, "(empfohlen)")), mail,
      h("span", { class: "hint" }, "Damit kannst du dich auch per E-Mail anmelden.")),
    submit,
    h("p", { class: "hint" }, "Alle anderen Sitzungen dieses Kontos werden dabei abgemeldet."));
  root.append(form);
  cur.input.focus();
}, { step: 0 });

// ------------------------------------------------------------------ Einladung annehmen
route(/^\/einladung\/([\w-]+)$/, async (root, token) => {
  const page = h("div", { class: "auth-page" }, h("div", { class: "auth-brand" }, h("span", { class: "b" }, LOGO(), "Snap2CAD")));
  clear(root, page);
  let inv;
  try { inv = await api(`/api/invite/${token}`); }
  catch (e) {
    page.append(h("div", { class: "auth-card" }, h("h1", { style: { fontSize: "22px" } }, "Einladung ungültig"),
      h("div", { class: "note err" }, icon("warn"), h("span", {}, "Diese Einladung ist nicht mehr gültig. Bitte bei deinem Administrator einen neuen Link anfordern.")),
      h("a", { class: "btn wide", href: "/login" }, "Zur Anmeldung")));
    return;
  }
  const err = errBox();
  const dn = h("input", { id: "dn", class: "input", autocomplete: "name", maxlength: 80 });
  const un = h("input", { id: "un", class: "input", autocomplete: "username", required: true, maxlength: 32, autocapitalize: "none", spellcheck: "false" });
  const unHint = h("span", { class: "hint" }, "3–32 Zeichen: a–z, 0–9, Punkt, Minus, Unterstrich");
  const em = h("input", { id: "em", class: "input", type: "email", autocomplete: "email", value: inv.email || "", readonly: !!inv.email });
  const pw = pwInput("pw", "new-password"), pw2 = pwInput("pw2", "new-password");
  const checkUser = debounce(async () => {
    const v = un.value.trim();
    if (!v) { unHint.textContent = "3–32 Zeichen: a–z, 0–9, Punkt, Minus, Unterstrich"; unHint.style.color = ""; return; }
    try {
      const r = await api(`/api/invite/${token}/username?u=${encodeURIComponent(v)}`);
      unHint.textContent = !r.valid ? "Ungültig: 3–32 Zeichen, a–z, 0–9, . - _" : r.available ? "Verfügbar" : "Bereits vergeben";
      unHint.style.color = r.available ? "var(--ok)" : "var(--err)";
    } catch { /* */ }
  }, 300);
  un.addEventListener("input", checkUser);
  dn.addEventListener("input", () => {
    if (!un.dataset.touched) { un.value = dn.value.trim().toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss").replace(/\s+/g, ".").replace(/[^a-z0-9._-]/g, "").slice(0, 32); checkUser(); }
  });
  un.addEventListener("keydown", () => { un.dataset.touched = "1"; });
  const submit = h("button", { class: "btn primary big wide", type: "submit" }, "Konto erstellen");
  page.append(h("form", { class: "auth-card w", "aria-labelledby": "e-h", onsubmit: async ev => {
    ev.preventDefault(); showErr(err, "");
    if (pw.input.value !== pw2.input.value) { showErr(err, "Die Passwörter stimmen nicht überein."); return; }
    submit.disabled = true;
    try {
      await api(`/api/invite/${token}`, { method: "POST", body: { username: un.value.trim(), display_name: dn.value.trim(), email: em.value.trim() || null, password: pw.input.value } });
      await refreshMe();
      toast("Willkommen! Dein Konto ist angelegt.", "ok");
      go("/", true);
    } catch (e) { showErr(err, e.message); } finally { submit.disabled = false; }
  } },
  h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } }, h("h1", { id: "e-h", style: { fontSize: "24px" } }, "Einladung annehmen"),
    h("p", { class: "lead" }, "Lege dein Konto an. Der Link ist nur einmal verwendbar.")),
  h("dl", { class: "kv", style: { background: "var(--well)", padding: "14px 16px", borderRadius: "6px" } },
    h("dt", {}, "Eingeladen von"), h("dd", {}, inv.invited_by || "–"),
    h("dt", {}, "Rolle"), h("dd", {}, inv.role === "admin" ? "Administrator" : "Nutzer"),
    h("dt", {}, "CAD-Kontingent"), h("dd", {}, inv.quota == null ? "unbegrenzt" : `${inv.quota} Läufe pro Monat`),
    h("dt", {}, "Gültig bis"), h("dd", {}, new Date(inv.expires_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }))),
  err,
  h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", { for: "dn" }, "Anzeigename"), dn),
    h("div", { class: "field" }, h("label", { for: "un" }, "Benutzername"), un, unHint)),
  h("div", { class: "field" }, h("label", { for: "em" }, "E-Mail"), em,
    inv.email ? h("span", { class: "hint" }, "Die Einladung ist an diese Adresse gebunden.") : h("span", { class: "hint" }, "Optional – damit kannst du dich auch per E-Mail anmelden.")),
  h("div", { class: "field" }, h("label", { for: "pw" }, "Passwort"), pw.wrap, strengthUI(pw.input, () => un.value)),
  h("div", { class: "field" }, h("label", { for: "pw2" }, "Passwort wiederholen"), pw2.wrap),
  submit,
  h("p", { class: "hint", style: { textAlign: "center" } }, "Schon ein Konto? ", h("a", { href: "/login" }, "Anmelden"))));
  dn.focus();
}, { public: true });

// ------------------------------------------------------------------ Passwort zuruecksetzen
route(/^\/reset\/([\w-]+)$/, async (root, token) => {
  const page = h("div", { class: "auth-page" }, h("div", { class: "auth-brand" }, h("span", { class: "b" }, LOGO(), "Snap2CAD")));
  clear(root, page);
  let info;
  try { info = await api(`/api/reset/${token}`); }
  catch {
    page.append(h("div", { class: "auth-card" }, h("h1", { style: { fontSize: "22px" } }, "Link ungültig"),
      h("div", { class: "note err" }, icon("warn"), h("span", {}, "Dieser Link ist abgelaufen oder wurde bereits benutzt. Bitte einen neuen beim Administrator anfordern.")),
      h("a", { class: "btn wide", href: "/login" }, "Zur Anmeldung")));
    return;
  }
  const err = errBox(); const pw = pwInput("pw", "new-password"), pw2 = pwInput("pw2", "new-password");
  const submit = h("button", { class: "btn primary big wide", type: "submit" }, "Passwort speichern");
  page.append(h("form", { class: "auth-card", onsubmit: async ev => {
    ev.preventDefault(); showErr(err, "");
    if (pw.input.value !== pw2.input.value) { showErr(err, "Die Passwörter stimmen nicht überein."); return; }
    submit.disabled = true;
    try {
      await api(`/api/reset/${token}`, { method: "POST", body: { password: pw.input.value } });
      await refreshMe(); toast("Passwort gesetzt", "ok"); go("/", true);
    } catch (e) { showErr(err, e.message); } finally { submit.disabled = false; }
  } },
  h("h1", { style: { fontSize: "24px" } }, "Neues Passwort"),
  h("p", { class: "lead" }, "Konto: ", h("strong", {}, info.username)),
  err,
  h("input", { type: "text", autocomplete: "username", value: info.username, hidden: true, readonly: true }),
  h("div", { class: "field" }, h("label", { for: "pw" }, "Neues Passwort"), pw.wrap, strengthUI(pw.input, () => info.username, { initial: true })),
  h("div", { class: "field" }, h("label", { for: "pw2" }, "Wiederholen"), pw2.wrap), submit));
  pw.input.focus();
}, { public: true });

// ------------------------------------------------------------------ Konto
route(/^\/konto$/, async main => {
  const u = S.me;
  const dn = h("input", { class: "input", id: "kdn", value: u.display_name || "", maxlength: 80 });
  const em = h("input", { class: "input", id: "kem", type: "email", value: u.email || "", maxlength: 200 });
  const err = errBox();
  const cur = pwInput("cur", "current-password"), nw = pwInput("new", "new-password"), rep = pwInput("rep", "new-password");
  const us = S.status?.usage;
  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Konto"), h("p", { class: "lead" }, `Angemeldet als ${u.username} · ${u.role === "admin" ? "Administrator" : "Nutzer"}`))),
    h("div", { class: "row" },
      h("form", { class: "card", style: { flex: "1 1 360px", maxWidth: "520px" }, onsubmit: async ev => {
        ev.preventDefault();
        try { await api("/api/me", { method: "PATCH", body: { display_name: dn.value, email: em.value } }); await refreshMe(); toast("Gespeichert", "ok"); go("/konto", true); }
        catch (e) { fail(e); }
      } }, h("h2", {}, "Profil"),
      h("div", { class: "field" }, h("label", { for: "kdn" }, "Anzeigename"), dn),
      h("div", { class: "field" }, h("label", { for: "kem" }, "E-Mail"), em),
      h("dl", { class: "kv" }, h("dt", {}, "CAD-Läufe diesen Monat"), h("dd", { class: "mono" }, us ? `${us.used} / ${us.quota ?? "∞"}` : "–"),
        h("dt", {}, "Konto seit"), h("dd", {}, dt(u.created_at, false))),
      h("div", {}, h("button", { class: "btn primary", type: "submit" }, "Speichern"))),
      h("form", { class: "card", style: { flex: "1 1 360px", maxWidth: "520px" }, onsubmit: async ev => {
        ev.preventDefault(); showErr(err, "");
        if (nw.input.value !== rep.input.value) { showErr(err, "Die neuen Passwörter stimmen nicht überein."); return; }
        try { await api("/api/auth/change-password", { method: "POST", body: { current: cur.input.value, new: nw.input.value } }); toast("Passwort geändert, andere Sitzungen abgemeldet", "ok"); go("/konto", true); }
        catch (e) { showErr(err, e.message); }
      } }, h("h2", {}, "Passwort ändern"), err,
      h("div", { class: "field" }, h("label", { for: "cur" }, "Aktuelles Passwort"), cur.wrap),
      h("div", { class: "field" }, h("label", { for: "new" }, "Neues Passwort"), nw.wrap, strengthUI(nw.input, () => u.username)),
      h("div", { class: "field" }, h("label", { for: "rep" }, "Wiederholen"), rep.wrap),
      h("div", {}, h("button", { class: "btn primary", type: "submit" }, "Passwort ändern")))));
});

// ------------------------------------------------------------------ Meine Auftraege
const JOB_STATUS = { queued: ["Wartet", "off"], running: ["Läuft", "info"], done: ["Fertig", "ok"], failed: ["Fehlgeschlagen", "err"], cancelled: ["Abgebrochen", "off"] };
export function jobBadge(st) { const [t, k] = JOB_STATUS[st] || [st, "off"]; return h("span", { class: `badge ${k}` }, st === "running" ? h("span", { class: "spin", style: { width: "10px", height: "10px" } }) : null, t); }

route(/^\/auftraege$/, async main => {
  const isAdmin = S.me.role === "admin";
  let all = new URLSearchParams(location.search).get("alle") === "1" && isAdmin;
  const box = h("div", { class: "card", style: { padding: "0", gap: "0" } });
  main.append(h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, all ? "Alle Aufträge" : "Meine Aufträge"),
    h("p", { class: "lead" }, "CAD-Aufträge laufen auf dem Server weiter, auch wenn du die Seite verlässt.")),
  h("div", { class: "chips" }, isAdmin ? h("label", { class: "check" }, h("input", { type: "checkbox", checked: all, onchange: e => go(e.target.checked ? "/auftraege?alle=1" : "/auftraege") }), "Aufträge aller Benutzer") : null,
    h("a", { class: "btn primary", href: "/cad" }, icon("plus"), "Neuer Auftrag"))), box);
  const load = async () => {
    const list = await api(`/api/jobs${all ? "?all=1" : ""}`);
    if (!list.length) { clear(box, h("div", { class: "empty" }, icon("cube", 32), "Noch keine Aufträge.", h("a", { class: "btn", href: "/cad" }, "Ersten Auftrag anlegen"))); return list; }
    clear(box, h("div", { class: "tablewrap" }, h("table", { class: "t" },
      h("thead", {}, h("tr", {}, h("th", {}, "Auftrag"), all ? h("th", {}, "Benutzer") : null, h("th", {}, "Status"), h("th", {}, "Versionen"), h("th", {}, "Abmessungen"), h("th", {}, "Aktualisiert"), h("th", {}, h("span", { class: "sr" }, "Aktionen")))),
      h("tbody", {}, list.map(j => h("tr", {},
        h("td", {}, h("a", { href: `/cad/${j.id}`, style: { fontWeight: 600 } }, j.name), h("div", { class: "xs muted" }, `#${j.id} · ${({ fdm: "FDM", sla: "SLA", cnc: "CNC" })[j.request?.process] || ""}`)),
        all ? h("td", {}, j.username) : null,
        h("td", {}, jobBadge(j.status)),
        h("td", { class: "num" }, j.n_versions),
        h("td", { class: "num" }, j.bbox ? `${num(j.bbox[0], 1)} × ${num(j.bbox[1], 1)} × ${num(j.bbox[2], 1)}` : "–"),
        h("td", {}, dt(j.updated_at)),
        h("td", { style: { textAlign: "right" } }, h("button", { class: "btn sm ghost", "aria-label": `${j.name} löschen`, onclick: async () => {
          if (!await confirmDlg("Auftrag löschen?", `„${j.name}“ mit allen Versionen und Dateien löschen?`, "Löschen", true)) return;
          try { await api(`/api/jobs/${j.id}`, { method: "DELETE" }); load(); } catch (e) { fail(e); }
        } }, icon("trash", 16)))))))));
    return list;
  };
  const list = await load();
  if (list.some(j => j.status === "running" || j.status === "queued")) {
    const t = setInterval(() => load().then(l => { if (!l.some(j => j.status === "running" || j.status === "queued")) clearInterval(t); }).catch(() => {}), 3000);
    onLeave(() => clearInterval(t));
  }
});

// ------------------------------------------------------------------ Verwaltung
const ACTIONS = {
  login: "Anmeldung", login_failed: "Fehlgeschlagene Anmeldung", logout: "Abmeldung", pw_changed: "Passwort geändert",
  pw_change_failed: "Passwortänderung fehlgeschlagen", pw_reset: "Passwort zurückgesetzt", reset_created: "Reset-Link erstellt",
  invite_created: "Einladung erstellt", invite_accepted: "Einladung angenommen", invite_revoked: "Einladung widerrufen",
  user_changed: "Benutzer geändert", user_deleted: "Benutzer gelöscht", sessions_ended: "Sitzungen beendet",
  admin_created: "Admin angelegt", cad_create: "CAD-Auftrag", suggest: "Maßvorschläge",
  setup: "Ersteinrichtung", setup_denied: "Einrichtung abgelehnt", settings_changed: "Einstellungen geändert",
  confirm_failed: "Passwortbestätigung falsch",
};

route(/^\/admin(?:\/(einladungen|protokoll|einstellungen))?$/, async (main, tab = "benutzer") => {
  const [users, invites, status] = await Promise.all([api("/api/admin/users"), api("/api/admin/invites"), api("/api/admin/status")]);
  const open = invites.filter(i => i.state === "offen");
  const openBox = h("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } });
  const month = new Date().toLocaleDateString("de-DE", { month: "short" }).replace(".", "");
  main.append(h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Benutzerverwaltung"),
    h("p", { class: "lead" }, "Neue Nutzer kommen nur über Einladungslinks dazu. CAD-Läufe nutzen den Server-Key – Kontingente begrenzen die Kosten.")),
  h("div", { class: "pill" }, h("span", { class: `dot ${status.sandbox ? "" : "err"}` }), `Sandbox ${status.sandbox ? "läuft" : "offline"} · `,
    h("span", { class: "mono" }, `${num(status.tokens_month.input / 1000, 0)}k / ${num(status.tokens_month.output / 1000, 0)}k Token (${month})`))));
  const tabs = h("div", { class: "tabs", role: "tablist", "aria-label": "Bereiche" },
    [["benutzer", "Benutzer", users.length], ["einladungen", "Einladungen", open.length], ["protokoll", "Protokoll", null], ["einstellungen", "Einstellungen", null]].map(([k, t, c]) =>
      h("button", { role: "tab", "data-tab": k, "aria-selected": String(tab === k), onclick: () => go(k === "benutzer" ? "/admin" : `/admin/${k}`, true) }, t, c != null ? h("span", { class: "cnt" }, c) : null)));
  main.append(tabs);
  if (tab === "protokoll") return auditTab(main);
  if (tab === "einstellungen") return settingsTab(main);
  const left = h("section", { class: "card", style: { padding: "0", gap: "0" }, "aria-label": tab === "benutzer" ? "Benutzerliste" : "Einladungen" });
  main.append(h("div", { class: "admin-layout" }, left, inviteAside(open)));
  if (tab === "einladungen") {
    clear(left, h("div", { class: "tablewrap" }, h("table", { class: "t" },
      h("thead", {}, h("tr", {}, h("th", {}, "E-Mail"), h("th", {}, "Rolle"), h("th", {}, "Status"), h("th", {}, "Erstellt"), h("th", {}, "Angenommen von"), h("th", {}))),
      h("tbody", {}, invites.map(i => h("tr", {},
        h("td", {}, i.email || h("span", { class: "muted" }, "ohne E-Mail-Bindung")),
        h("td", {}, i.role === "admin" ? "Admin" : "Nutzer"),
        h("td", {}, h("span", { class: `badge ${({ offen: "info", angenommen: "ok", abgelaufen: "off", widerrufen: "off" })[i.state]}` }, i.state), i.state === "offen" ? h("div", { class: "xs muted" }, until(i.expires_at)) : null),
        h("td", {}, dt(i.created_at), h("div", { class: "xs muted" }, i.created_by || "")),
        h("td", {}, i.used_by || "–"),
        h("td", {}, i.state === "offen" ? h("button", { class: "btn sm danger", onclick: () => revoke(i) }, "Widerrufen") : null)))))));
    if (!invites.length) left.append(h("div", { class: "empty" }, "Noch keine Einladungen."));
    return;
  }
  clear(left, h("div", { class: "tablewrap" }, h("table", { class: "t" },
    h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Benutzer"), h("th", { scope: "col" }, "Rolle"), h("th", { scope: "col" }, "Status"),
      h("th", { scope: "col" }, "Letzte Anmeldung"), h("th", { scope: "col" }, `CAD ${month}.`), h("th", { scope: "col" }, h("span", { class: "sr" }, "Aktionen")))),
    h("tbody", {}, users.map(userRow)))));

  function userRow(u) {
    const me = u.id === S.me.id;
    const st = u.status === "disabled" ? ["gesperrt", "err"] : u.pending_reset ? ["Passwort-Reset offen", "warn"] : u.must_change_pw ? ["Startpasswort", "warn"] : ["aktiv", "ok"];
    const menu = h("div", { class: "menu", hidden: true });
    const btn = h("button", { class: "iconbtn", "aria-label": `Aktionen für ${u.username}`, "aria-expanded": "false", style: { border: "0" } }, "⋯");
    btn.addEventListener("click", ev => {
      ev.stopPropagation();
      document.querySelectorAll(".admin-layout .menu").forEach(m => { if (m !== menu) m.hidden = true; });
      menu.hidden = !menu.hidden; btn.setAttribute("aria-expanded", String(!menu.hidden));
    });
    document.addEventListener("click", () => { menu.hidden = true; });
    const act = (label, fn, cls = "") => h("button", { class: cls, onclick: async () => { menu.hidden = true; try { await fn(); } catch (e) { fail(e); } } }, label);
    clear(menu,
      act("Link zum Passwort-Zurücksetzen", async () => {
        const r = await api(`/api/admin/users/${u.id}/reset`, { method: "POST" });
        await showLink("Link zum Zurücksetzen", r.link, `Gültig 48 Stunden, einmalig. An ${u.display_name || u.username} weitergeben.`);
        go("/admin", true);
      }),
      me ? null : act(u.role === "admin" ? "Zum Nutzer machen" : "Zum Admin machen", async () => {
        await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: { role: u.role === "admin" ? "user" : "admin" } }); go("/admin", true);
      }),
      act("Kontingent ändern", async () => {
        const inp = h("input", { class: "input mono", value: u.cad_quota == null ? "" : (u.cad_quota < 0 ? "-1" : u.cad_quota), placeholder: `Standard (${status.default_quota})` });
        const v = await dialog({ title: `Kontingent für ${u.username}`, body: h("div", { class: "field" }, h("label", {}, "CAD-Läufe pro Monat"), inp,
          h("span", { class: "hint" }, "Leer = Standard aus der Konfiguration · −1 = unbegrenzt · Admins sind standardmäßig unbegrenzt.")),
          actions: [{ label: "Abbrechen", value: null }, { label: "Speichern", primary: true, submit: true, run: () => ({ v: inp.value.trim() }) }] });
        if (!v) return;
        const n = parseNum(v.v);
        await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: v.v === "" ? { quota_default: true } : { cad_quota: Math.round(n) } });
        go("/admin", true);
      }),
      act("Alle Sitzungen abmelden", async () => { await api(`/api/admin/users/${u.id}/logout`, { method: "POST" }); toast("Sitzungen beendet", "ok"); }),
      me ? null : act(u.status === "disabled" ? "Entsperren" : "Sperren", async () => {
        await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: { status: u.status === "disabled" ? "active" : "disabled" } }); go("/admin", true);
      }),
      me ? null : h("div", { class: "sep" }),
      me ? null : act("Löschen …", async () => {
        if (!await confirmDlg(`${u.username} löschen?`, "Das Konto wird mit allen Projekten, Fotos und CAD-Aufträgen endgültig gelöscht.", "Endgültig löschen", true)) return;
        await api(`/api/admin/users/${u.id}`, { method: "DELETE" }); go("/admin", true);
      }, "danger"));
    return h("tr", {},
      h("td", {}, h("div", { class: "ucell" }, h("span", { class: `avatar ${me ? "" : "s"}` }, initials(u)),
        h("span", {}, h("strong", {}, u.display_name || u.username), h("br"), h("span", { class: "small muted" }, [u.username, me ? "du" : null, u.email].filter(Boolean).join(" · "))))),
      h("td", {}, h("span", { class: `badge ${u.role === "admin" ? "info" : "off"}` }, u.role === "admin" ? "Admin" : "Nutzer")),
      h("td", {}, h("span", { class: `badge ${st[1]}` }, st[0])),
      h("td", {}, dt(u.last_login)),
      h("td", { class: "num" }, `${u.usage.used} / ${u.usage.quota ?? "∞"}`),
      h("td", { class: "rel", style: { textAlign: "right" } }, btn, menu));
  }

  async function revoke(i) {
    if (!await confirmDlg("Einladung widerrufen?", "Der Link funktioniert danach nicht mehr.", "Widerrufen", true)) return;
    try {
      await api(`/api/admin/invites/${i.id}`, { method: "DELETE" });
      toast("Einladung widerrufen", "ok");
      if (tab === "einladungen") go(location.pathname, true); else await refreshOpen();
    } catch (e) { fail(e); }
  }

  // Liste „Offene Einladungen“ und Zaehler im Reiter neu laden, ohne den gerade erzeugten Link zu verlieren
  function fillOpen(list) {
    clear(openBox, list.length ? list.map(i => h("div", { class: "inv" }, h("span", { style: { fontWeight: 500 } }, i.email || "ohne E-Mail-Bindung"),
      h("button", { class: "btn sm danger", onclick: () => revoke(i) }, "Widerrufen"),
      h("span", { class: "small muted" }, `${i.role === "admin" ? "Admin" : "Nutzer"} · ${until(i.expires_at)}`)))
      : h("p", { class: "hint" }, "Keine offenen Einladungen."));
    const cnt = tabs.querySelector('[data-tab="einladungen"] .cnt');
    if (cnt) cnt.textContent = list.length;
  }
  async function refreshOpen() {
    fillOpen((await api("/api/admin/invites")).filter(i => i.state === "offen"));
  }

  function inviteAside(openList) {
    const email = h("input", { id: "ie", class: "input", type: "email", placeholder: "name@beispiel.de", maxlength: 200 });
    const roleU = h("input", { type: "radio", name: "role", value: "user", checked: true });
    const roleA = h("input", { type: "radio", name: "role", value: "admin" });
    const days = h("select", { class: "input" }, h("option", { value: 7 }, "7 Tage"), h("option", { value: 1 }, "24 Stunden"), h("option", { value: 30 }, "30 Tage"));
    const quota = h("input", { class: "input mono", inputmode: "numeric", placeholder: `Standard (${status.default_quota})` });
    const out = h("div", { hidden: true, style: { display: "flex", flexDirection: "column", gap: "8px" } });
    return h("aside", { style: { display: "flex", flexDirection: "column", gap: "24px" } },
      h("form", { class: "card", "aria-labelledby": "inv-h", onsubmit: async ev => {
        ev.preventDefault();
        try {
          const q = quota.value.trim() === "" ? null : Math.round(parseNum(quota.value));
          const r = await api("/api/admin/invites", { method: "POST", body: { email: email.value.trim() || null, role: roleA.checked ? "admin" : "user", cad_quota: q, days: Number(days.value) } });
          const inp = h("input", { class: "input", readonly: true, value: r.link, "aria-label": "Einladungslink" });
          clear(out, h("span", { class: "small", style: { color: "var(--ok)", fontWeight: 600 } }, `Link erstellt · einmalig · gültig bis ${new Date(r.expires_at).toLocaleDateString("de-DE")}`),
            h("div", { class: "linkbox" }, inp, copyBtn(r.link)),
            h("span", { class: "hint" }, "Der Link wird nur jetzt vollständig angezeigt. Versand per Mail-Programm oder Messenger."));
          out.hidden = false; inp.select();
          email.value = ""; quota.value = "";
          refreshOpen().catch(() => {});
        } catch (e) { fail(e); }
      } },
      h("h2", { id: "inv-h" }, "Einladung erstellen"),
      h("div", { class: "field" }, h("label", { for: "ie" }, "E-Mail ", h("span", { class: "muted", style: { fontWeight: 400 } }, "(optional, bindet den Link)")), email),
      h("fieldset", {}, h("legend", {}, "Rolle"), h("div", { class: "grid2" }, h("label", { class: "check radio" }, roleU, "Nutzer"), h("label", { class: "check radio" }, roleA, "Admin"))),
      h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "flabel" }, "Gültig"), days),
        h("label", { class: "field" }, h("span", { class: "flabel" }, "CAD-Läufe / Monat"), quota)),
      h("button", { class: "btn primary", type: "submit" }, "Einladungslink erzeugen"), out),
      h("section", { class: "card", "aria-labelledby": "open-h", style: { gap: "4px" } }, h("h2", { id: "open-h", style: { marginBottom: "8px" } }, "Offene Einladungen"),
        (fillOpen(openList), openBox)));
  }
});

async function settingsTab(main) {
  const cfg = await api("/api/admin/settings");
  const k = cfg.api_key, md = cfg.model;
  const err = errBox();
  const key = pwInput("akey", "off", { required: false, maxlength: 400, spellcheck: "false", autocapitalize: "none", placeholder: "sk-ant-…" });
  key.wrap.querySelector("button").setAttribute("aria-label", "Schlüssel anzeigen");
  const cpw = pwInput("acpw", "current-password", { required: false, maxlength: 300 });
  const save = async (body, btn, msg) => {
    showErr(err, ""); btn.disabled = true;
    const label = btn.textContent; btn.textContent = "Wird geprüft …";
    try { await api("/api/admin/settings", { method: "PUT", body }); await refreshMe(); toast(msg, "ok"); go("/admin/einstellungen", true); }
    catch (e) { showErr(err, e.message); } finally { btn.disabled = false; btn.textContent = label; }
  };
  const keyBtn = h("button", { class: "btn primary", type: "submit" }, k.source === "none" ? "Schlüssel prüfen und speichern" : "Schlüssel ersetzen");
  const needPw = () => {
    if (cpw.input.value) return true;
    showErr(err, "Bitte zur Bestätigung dein Passwort eingeben."); cpw.input.focus(); return false;
  };
  const storage = k.source !== "db" ? null : k.encrypted
    ? h("div", { class: "note ok" }, icon("check"), h("span", {}, "Verschlüsselt gespeichert (SECRET_KEY)."))
    : h("div", { class: "note warn" }, icon("warn"), h("span", {}, "Unverschlüsselt in der Datenbank gespeichert. SECRET_KEY in der .env setzen (mindestens 32 Zeichen), dann wird der Schlüssel beim nächsten Start verschlüsselt."));
  const status = k.source === "locked"
    ? h("div", { class: "note err" }, icon("warn"), h("span", {}, "Der gespeicherte Schlüssel lässt sich nicht entschlüsseln – SECRET_KEY fehlt oder ist falsch. Richtigen SECRET_KEY setzen oder hier einen neuen Schlüssel eingeben."))
    : k.source === "env"
    ? h("div", { class: "note info" }, icon("info"), h("span", {}, `Gesetzt über die Umgebungsvariable ANTHROPIC_API_KEY (${k.hint || "…"}). Ändern nur in der .env-Datei; ist sie leer, gilt der hier hinterlegte Schlüssel.`))
    : k.source === "db"
      ? h("div", { class: "note ok" }, icon("check"), h("span", {}, "Hinterlegt: ", h("span", { class: "mono" }, k.hint || "…")))
      : h("div", { class: "note warn" }, icon("warn"), h("span", {}, cfg.ai_fake ? "Kein Schlüssel hinterlegt – der Testmodus (AI_FAKE) ist aktiv." : "Kein Schlüssel hinterlegt – KI-Funktionen sind deaktiviert."));
  const keyForm = h("form", { class: "card", style: { flex: "1 1 380px", maxWidth: "560px" }, "aria-labelledby": "k-h", onsubmit: ev => {
    ev.preventDefault();
    if (!key.input.value.trim()) { showErr(err, "Bitte einen API-Schlüssel eingeben."); key.input.focus(); return; }
    if (!needPw()) return;
    save({ api_key: key.input.value.trim(), password: cpw.input.value }, keyBtn, "API-Schlüssel gespeichert");
  } }, h("h2", { id: "k-h" }, "Anthropic-API-Schlüssel"), status, storage,
  k.source === "env" ? null : [
    h("div", { class: "field" }, h("label", { for: "akey" }, k.source === "none" ? "Schlüssel" : "Neuer Schlüssel"), key.wrap,
      h("span", { class: "hint" }, "Anlegen unter ", h("a", { href: "https://console.anthropic.com/settings/keys", target: "_blank", rel: "noopener noreferrer" }, "console.anthropic.com → API Keys"),
        ". Wird vor dem Speichern geprüft und nie wieder vollständig angezeigt.")),
    h("div", { class: "field" }, h("label", { for: "acpw" }, "Dein Passwort"), cpw.wrap,
      h("span", { class: "hint" }, "Zur Bestätigung, bevor der Schlüssel ersetzt oder entfernt wird.")),
    h("div", { class: "chips" }, keyBtn, k.source === "db" || k.source === "locked" ? h("button", { class: "btn danger", type: "button", onclick: async ev => {
      const btn = ev.currentTarget;
      if (!needPw()) return;
      if (!await confirmDlg("API-Schlüssel entfernen?", "KI-Funktionen sind danach deaktiviert, bis ein neuer Schlüssel hinterlegt ist.", "Entfernen", true)) return;
      save({ clear_api_key: true, password: cpw.input.value }, btn, "API-Schlüssel entfernt");
    } }, "Entfernen") : null)]);
  const mInp = h("input", { id: "amodel", class: "input mono", value: md.value, maxlength: 100, disabled: md.source === "env", spellcheck: "false", autocapitalize: "none" });
  const mBtn = h("button", { class: "btn primary", type: "submit", disabled: md.source === "env" }, "Modell speichern");
  const modelForm = h("form", { class: "card", style: { flex: "1 1 300px", maxWidth: "460px" }, "aria-labelledby": "m-h", onsubmit: ev => {
    ev.preventDefault(); save({ model: mInp.value.trim() }, mBtn, "Modell gespeichert");
  } }, h("h2", { id: "m-h" }, "KI-Modell"),
  h("div", { class: "field" }, h("label", { for: "amodel" }, "Modell-ID"), mInp,
    h("span", { class: "hint" }, md.source === "env" ? "Festgelegt über die Umgebungsvariable ANTHROPIC_MODEL." : `Leer lassen für den Standard (${md.default}). Wird mit dem hinterlegten Schlüssel geprüft.`)),
  h("div", {}, mBtn));
  main.append(err, h("div", { class: "row", style: { alignItems: "flex-start" } }, keyForm, modelForm));
}

async function auditTab(main) {
  const sel = h("select", { class: "input", style: { maxWidth: "280px" } }, h("option", { value: "" }, "Alle Ereignisse"),
    Object.entries(ACTIONS).map(([k, v]) => h("option", { value: k }, v)));
  const box = h("div", { class: "card", style: { padding: "0", gap: "0" } });
  main.append(h("div", { class: "chips" }, sel), box);
  const load = async () => {
    const rows = await api(`/api/admin/audit?limit=500&action=${encodeURIComponent(sel.value)}`);
    clear(box, rows.length ? h("div", { class: "tablewrap" }, h("table", { class: "t" },
      h("thead", {}, h("tr", {}, h("th", {}, "Zeit"), h("th", {}, "Ereignis"), h("th", {}, "Wer"), h("th", {}, "Details"), h("th", {}, "IP"))),
      h("tbody", {}, rows.map(r => h("tr", {}, h("td", { style: { whiteSpace: "nowrap" } }, dt(r.ts)),
        h("td", {}, h("span", { class: `badge ${r.action.includes("failed") ? "err" : r.action.startsWith("cad") || r.action === "suggest" ? "claude" : "off"}` }, ACTIONS[r.action] || r.action)),
        h("td", {}, r.actor || "–"), h("td", { class: "small" }, r.detail || ""), h("td", { class: "mono xs" }, r.ip || "")))))) : h("div", { class: "empty" }, "Keine Einträge."));
  };
  sel.addEventListener("change", () => load().catch(fail));
  await load();
}

function copyBtn(text) {
  const btn = h("button", { class: "btn", type: "button", onclick: async () => {
    if (await copyText(text)) { clear(btn, icon("check", 16), "Kopiert"); setTimeout(() => clear(btn, icon("copy", 16), "Kopieren"), 2000); }
    else toast("Kopieren nicht möglich – bitte den Link markieren und mit Strg+C kopieren", "err");
  } }, icon("copy", 16), "Kopieren");
  return btn;
}
async function showLink(title, link, text) {
  const inp = h("input", { class: "input mono", readonly: true, value: link });
  const p = dialog({ title, body: h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, h("div", { class: "linkbox" }, inp, copyBtn(link)), h("p", { class: "hint" }, text)),
    actions: [{ label: "Schließen", value: true, primary: true }] });
  setTimeout(() => inp.select(), 50);
  return p;
}

// ------------------------------------------------------------------ Arbeitsschritte (Module)
route(/^\/$/, async main => (await import("./library.js")).default(main), { step: 1 });
route(/^\/anleitung$/, async main => (await import("./guide.js")).default(main));
route(/^\/fotos$/, async main => (await import("./photos.js")).default(main), { step: 2 });
route(/^\/messen$/, async (main) => (await import("./measure.js")).default(main), { step: 3, bare: false });
route(/^\/cad$/, async main => (await import("./cad.js")).form(main), { step: 4 });
route(/^\/cad\/(\d+)$/, async (main, id) => (await import("./cad.js")).job(main, Number(id)), { step: 4 });
route(/.*/, async main => {
  main.append(h("div", { class: "empty" }, h("h1", {}, "Seite nicht gefunden"), h("a", { class: "btn", href: "/" }, "Zur Startseite")));
}, { notFound: true });

// ------------------------------------------------------------------ Start
(async () => {
  try { await refreshMe(); } catch (e) { S.status = {}; }
  render();
  setInterval(() => { if (S.me) refreshMe().then(() => {
    const top = document.querySelector(".top-right");
    if (top && S.status) { const pills = top.querySelectorAll(".pill"); pills.forEach(p => p.remove()); top.prepend(...statusPill().filter(Boolean)); }
  }).catch(() => {}); }, 60000);
})();
