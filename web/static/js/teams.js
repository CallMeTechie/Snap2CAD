// Teams: eigene Teams, Einladungen, Mitglieder und Rollen (Spec Teams §3, §7) und Reiter „Teams“ der Benutzerverwaltung (§5)
import { api, h, clear, icon, dt, toast, fail, dialog, confirmDlg, plural } from "./lib.js";
import { S, go, refreshMe } from "./app.js";
import { ROLE_TEXT, saveScope } from "./rights.js";

const ROLES = ["leiter", "mitglied", "lesend"];
const memberName = m => (m.display_name && m.display_name !== m.username ? `${m.display_name} (${m.username})` : m.username);

function roleSelect(value, label, onchange) {
  return h("select", { class: "input", "aria-label": label, onchange, style: { width: "auto" } },
    ROLES.map(r => h("option", { value: r, selected: r === value }, ROLE_TEXT[r])));
}
function askName(title, value = "") {
  const inp = h("input", { class: "input", value, maxlength: 80, "aria-label": "Teamname", placeholder: "z. B. Werkstatt" });
  return dialog({ title, body: h("div", { class: "field" }, h("label", {}, "Teamname"), inp,
    h("span", { class: "hint" }, "1 bis 80 Zeichen. Teamnamen müssen nicht eindeutig sein.")),
  actions: [{ label: "Abbrechen", value: null }, { label: "Speichern", primary: true, submit: true, run: () => inp.value.trim() || false }] });
}
// Bibliothek mit diesem Team öffnen (gemerkter Bereich über rights.saveScope wie in library.js)
function openLibrary(tid) {
  saveScope(`team:${tid}`);
  go("/");
}

export default async function (main) {
  const open = Number(new URLSearchParams(location.search).get("team")) || null;
  const box = h("div", { style: { display: "flex", flexDirection: "column", gap: "24px" } });
  main.append(h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Teams"),
    h("p", { class: "lead" }, "Ein Team teilt eine Bibliothek: Alle Mitglieder sehen dieselben Projekte mit Fotos, Maßen und CAD-Aufträgen.")),
  h("button", { class: "btn primary", onclick: () => create().catch(fail) }, icon("plus"), "Team gründen")), box);

  async function create() {
    const name = await askName("Team gründen");
    if (!name) return;
    const t = await api("/api/teams", { method: "POST", body: { name } });
    toast(`Team „${t.name}“ gegründet – du bist Leiter`, "ok");
    go(`/teams?team=${t.id}`, true);
  }
  async function decide(i, what) {
    try {
      const r = await api(`/api/team-invites/${i.id}/${what}`, { method: "POST" });
      await refreshMe().catch(() => {});
      toast(what === "accept" ? `Willkommen im Team „${i.team_name}“` : "Einladung abgelehnt", "ok");
      go(what === "accept" ? `/teams?team=${r.id}` : "/teams", true);
    } catch (e) { fail(e); go("/teams", true); }
  }

  function invitesCard(list) {
    return h("section", { class: "card", "aria-labelledby": "ti-h" }, h("h2", { id: "ti-h" }, "Einladungen für dich"),
      list.map(i => h("div", { class: "chips tinvite", style: { justifyContent: "space-between" } },
        h("span", {}, h("strong", {}, i.team_name), ` · als ${ROLE_TEXT[i.role]} · von ${i.invited_by_name || "–"} · ${dt(i.created_at)}`),
        h("span", { class: "chips" },
          h("button", { class: "btn sm primary", onclick: () => decide(i, "accept") }, "Annehmen"),
          h("button", { class: "btn sm", onclick: () => decide(i, "decline") }, "Ablehnen")))));
  }

  function teamsCard(list) {
    if (!list.length) {
      return h("section", { class: "card empty" }, icon("users", 32), "Du bist noch in keinem Team.",
        h("button", { class: "btn sm primary", onclick: () => create().catch(fail) }, icon("plus", 16), "Team gründen"));
    }
    return h("section", { class: "card", style: { padding: "0", gap: "0" }, "aria-label": "Meine Teams" }, h("div", { class: "tablewrap" }, h("table", { class: "t" },
      h("thead", {}, h("tr", {}, h("th", {}, "Team"), h("th", {}, "Rolle"), h("th", {}, "Mitglieder"), h("th", {}, "Projekte"),
        h("th", {}, h("span", { class: "sr" }, "Aktionen")))),
      h("tbody", {}, list.map(t => h("tr", { "aria-current": t.id === open ? "true" : null },
        h("td", {}, h("strong", {}, t.name)), h("td", {}, ROLE_TEXT[t.my_role]),
        h("td", { class: "num" }, t.n_members), h("td", { class: "num" }, t.n_projects),
        h("td", { style: { textAlign: "right" } }, h("span", { class: "chips", style: { justifyContent: "flex-end" } },
          h("button", { class: "btn sm", onclick: () => openLibrary(t.id) }, "Bibliothek"),
          h("button", { class: "btn sm primary", onclick: () => go(`/teams?team=${t.id}`, true) }, "Verwalten")))))))));
  }

  function detailCard(t) {
    const lead = t.my_role === "leiter", me = S.me.id;
    const again = () => go(`/teams?team=${t.id}`, true);
    const run = fn => () => fn().catch(e => { fail(e); again(); });
    const user = h("input", { class: "input", maxlength: 64, autocapitalize: "none", spellcheck: "false", "aria-label": "Benutzername",
      placeholder: "Benutzername", style: { maxWidth: "240px" } });
    const role = roleSelect("mitglied", "Rolle");
    async function setRole(m, value) {
      await api(`/api/teams/${t.id}/members/${m.user_id}`, { method: "PATCH", body: { role: value } });
      toast(`${m.username} ist jetzt ${ROLE_TEXT[value]}`, "ok");
      again();
    }
    async function removeMember(m) {
      if (!await confirmDlg(`${m.username} entfernen?`, "Die Projekte, die diese Person im Team angelegt hat, bleiben im Team.", "Entfernen", true)) return;
      await api(`/api/teams/${t.id}/members/${m.user_id}`, { method: "DELETE" });
      toast(`${m.username} entfernt`, "ok");
      again();
    }
    async function invite() {
      const name = user.value.trim();
      if (!name) { user.focus(); toast("Bitte den Benutzernamen eingeben", "err"); return; }
      const r = await api(`/api/teams/${t.id}/invites`, { method: "POST", body: { username: name, role: role.value } });
      toast(`${r.username} ist eingeladen und muss die Einladung noch annehmen`, "ok");
      again();
    }
    async function revoke(i) {
      await api(`/api/teams/${t.id}/invites/${i.id}`, { method: "DELETE" });
      toast("Einladung zurückgezogen", "ok");
      again();
    }
    async function rename() {
      const name = await askName("Team umbenennen", t.name);
      if (!name || name === t.name) return;
      await api(`/api/teams/${t.id}`, { method: "PATCH", body: { name } });
      toast("Team umbenannt", "ok");
      again();
    }
    async function leave() {
      const last = t.members.length === 1;
      if (!await confirmDlg(`Team „${t.name}“ verlassen?`, last
        ? "Du bist das letzte Mitglied: Das Team wird dabei gelöscht. Das geht nur, wenn es keine Projekte mehr hat."
        : "Deine Projekte in diesem Team bleiben im Team; du siehst sie danach nicht mehr.", "Austreten", true)) return;
      const r = await api(`/api/teams/${t.id}/members/${me}`, { method: "DELETE" });
      toast(r.team_deleted ? "Team verlassen und aufgelöst" : "Team verlassen", "ok");
      go("/teams", true);
    }
    async function del() {
      if (t.n_projects) { toast(`Das Team hat noch ${plural(t.n_projects, "Projekt", "Projekte")} – erst löschen oder verschieben.`, "err"); return; }
      if (!await confirmDlg(`Team „${t.name}“ löschen?`, "Mitgliedschaften und offene Einladungen werden gelöscht.", "Löschen", true)) return;
      await api(`/api/teams/${t.id}`, { method: "DELETE" });
      toast("Team gelöscht", "ok");
      go("/teams", true);
    }
    const members = h("div", { class: "tablewrap" }, h("table", { class: "t tmembers" },
      h("thead", {}, h("tr", {}, h("th", {}, "Mitglied"), h("th", {}, "Rolle"), h("th", {}, "Seit"), h("th", {}, h("span", { class: "sr" }, "Aktionen")))),
      h("tbody", {}, t.members.map(m => h("tr", {},
        h("td", {}, memberName(m), m.user_id === me ? h("span", { class: "xs muted" }, " · du") : null),
        h("td", {}, lead ? roleSelect(m.role, `Rolle von ${m.username}`, e => run(() => setRole(m, e.target.value))()) : ROLE_TEXT[m.role]),
        h("td", {}, dt(m.joined_at, false)),
        h("td", { style: { textAlign: "right" } }, lead && m.user_id !== me
          ? h("button", { class: "btn sm danger", onclick: run(() => removeMember(m)) }, "Entfernen") : null))))));
    return h("section", { class: "card", "aria-labelledby": "td-h" },
      h("div", { class: "card-head" }, h("h2", { id: "td-h" }, t.name), h("span", { class: "badge info" }, ROLE_TEXT[t.my_role])),
      h("span", { class: "small muted" }, `${plural(t.members.length, "Mitglied", "Mitglieder")} · ${plural(t.n_projects, "Projekt", "Projekte")} · gegründet ${dt(t.created_at, false)}`),
      members,
      lead ? h("form", { class: "chips", "aria-label": "Mitglied einladen", onsubmit: ev => { ev.preventDefault(); run(invite)(); } },
        user, role, h("button", { class: "btn sm primary", type: "submit" }, "Einladen"),
        h("span", { class: "hint" }, "Genauer Benutzername; die Person nimmt die Einladung unter „Teams“ an.")) : null,
      lead && t.invites.length ? h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } }, h("h3", {}, "Offene Einladungen"),
        t.invites.map(i => h("div", { class: "chips" }, h("span", {}, `${i.username} · ${ROLE_TEXT[i.role]} · ${dt(i.created_at)}`),
          h("button", { class: "btn sm", onclick: run(() => revoke(i)) }, "Zurückziehen")))) : null,
      h("div", { class: "chips" },
        h("button", { class: "btn sm", onclick: () => openLibrary(t.id) }, icon("folder", 14), "Zur Bibliothek"),
        lead ? h("button", { class: "btn sm", onclick: run(rename) }, "Umbenennen …") : null,
        h("button", { class: "btn sm danger", onclick: run(leave) }, "Austreten …"),
        lead ? h("button", { class: "btn sm danger", onclick: run(del) }, "Team löschen …") : null));
  }

  const r = await api("/api/teams");
  let det = null;
  if (open) {
    try { det = await api(`/api/teams/${open}`); }
    catch (e) { if (e.status !== 404) throw e; toast("Dieses Team gibt es nicht mehr, oder du bist kein Mitglied.", "err"); }
  }
  if (!main.isConnected) return;
  clear(box, r.invites.length ? invitesCard(r.invites) : null, teamsCard(r.teams), det ? detailCard(det) : null);
}

// Reiter „Teams“ der Benutzerverwaltung: alle Teams, Rollen, Mitglieder, Einladungen, Löschen – keine Projektinhalte
export async function adminTab(main) {
  const sel = Number(new URLSearchParams(location.search).get("team")) || null;
  const list = await api("/api/admin/teams");
  const left = h("section", { class: "card", style: { padding: "0", gap: "0" }, "aria-label": "Alle Teams" });
  const right = h("aside", { style: { display: "flex", flexDirection: "column", gap: "16px" } });
  main.append(h("div", { class: "admin-layout" }, left, right));
  const pick = t => go(`/admin/teams?team=${t.id}`, true);
  clear(left, list.length ? h("div", { class: "tablewrap" }, h("table", { class: "t" },
    h("thead", {}, h("tr", {}, h("th", {}, "Team"), h("th", {}, "Leiter"), h("th", {}, "Mitglieder"), h("th", {}, "Projekte"), h("th", {}, "Angelegt"))),
    h("tbody", {}, list.map(t => h("tr", { "aria-current": t.id === sel ? "true" : null, tabindex: 0, style: { cursor: "pointer" },
      onclick: () => pick(t), onkeydown: e => { if (e.key === "Enter") pick(t); } },
      h("td", {}, h("strong", {}, t.name), t.no_leader ? h("span", { class: "badge warn", style: { marginLeft: "8px" } }, "ohne Leiter") : null),
      h("td", {}, t.leaders.join(", ") || "–"), h("td", { class: "num" }, t.n_members), h("td", { class: "num" }, t.n_projects),
      h("td", {}, dt(t.created_at, false))))))) : h("div", { class: "empty" }, "Noch keine Teams."));
  if (!sel) {
    right.append(h("p", { class: "hint" }, "Ein Team anklicken, um Rollen, Mitglieder und Einladungen zu verwalten. Inhalte der Team-Projekte sind hier nicht abrufbar."));
    return;
  }
  let t;
  try { t = await api(`/api/admin/teams/${sel}`); } catch (e) { fail(e); return; }
  const back = () => go(`/admin/teams?team=${t.id}`, true);
  const run = fn => () => fn().catch(e => { fail(e); back(); });
  async function setRole(m, value) {
    await api(`/api/admin/teams/${t.id}/members/${m.user_id}`, { method: "PATCH", body: { role: value } });
    toast(`${m.username} ist jetzt ${ROLE_TEXT[value]}`, "ok");
    back();
  }
  async function removeMember(m) {
    const last = t.members.length === 1;
    if (!await confirmDlg(`${m.username} aus „${t.name}“ entfernen?`, last && !t.n_projects
      ? "Das ist das letzte Mitglied: Das Team hat keine Projekte und wird dabei gelöscht."
      : "Die Projekte dieser Person bleiben im Team.", "Entfernen", true)) return;
    const r = await api(`/api/admin/teams/${t.id}/members/${m.user_id}`, { method: "DELETE" });
    if (r.team_deleted) { toast("Mitglied entfernt – das leere Team wurde gelöscht", "ok"); go("/admin/teams", true); return; }
    toast("Mitglied entfernt", "ok");
    back();
  }
  // Benutzer ohne Einladung aufnehmen (Spec §5), z. B. wenn das Team keine Mitglieder mehr hat
  const addUser = h("input", { class: "input", maxlength: 64, autocapitalize: "none", spellcheck: "false", "aria-label": "Benutzer aufnehmen",
    placeholder: "Benutzername", style: { maxWidth: "220px" } });
  const addRole = roleSelect(t.members.some(m => m.role === "leiter") ? "mitglied" : "leiter", "Rolle für neues Mitglied");
  async function addMember() {
    const name = addUser.value.trim();
    if (!name) { addUser.focus(); toast("Bitte den Benutzernamen eingeben", "err"); return; }
    await api(`/api/admin/teams/${t.id}/members`, { method: "POST", body: { username: name, role: addRole.value } });
    toast(`${name} ist jetzt ${ROLE_TEXT[addRole.value]} in „${t.name}“`, "ok");
    back();
  }
  async function revoke(i) {
    await api(`/api/admin/teams/${t.id}/invites/${i.id}`, { method: "DELETE" });
    toast("Einladung zurückgezogen", "ok");
    back();
  }
  async function delTeam() {
    const inp = h("input", { class: "input", "aria-label": "Teamname zur Bestätigung", autocomplete: "off" });
    const ok = await dialog({ title: `Team „${t.name}“ löschen?`, body: h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } },
      h("p", {}, t.n_projects
        ? `Das Team hat ${plural(t.n_projects, "Projekt", "Projekte")}. Sie werden mit Fotos, Messungen, Teilen und gemerkten Werten endgültig gelöscht; CAD-Aufträge bleiben bei ihren Erstellern ohne Projekt, Aufträge gelöschter Benutzer werden mitgelöscht.`
        : "Das Team hat keine Projekte. Mitgliedschaften und Einladungen werden gelöscht."),
      h("div", { class: "field" }, h("label", {}, "Zur Bestätigung den Teamnamen eingeben"), inp)),
    actions: [{ label: "Abbrechen", value: null }, { label: "Endgültig löschen", danger: true, submit: true,
      run: () => { if (inp.value.trim() === t.name) return true; toast("Der Name stimmt nicht.", "err"); return false; } }] });
    if (!ok) return;
    const r = await api(`/api/admin/teams/${t.id}?confirm=${encodeURIComponent(inp.value.trim())}`, { method: "DELETE" });
    toast(`Team gelöscht (${plural(r.projects, "Projekt", "Projekte")})`, "ok");
    go("/admin/teams", true);
  }
  right.append(h("section", { class: "card", "aria-labelledby": "at-h" },
    h("div", { class: "card-head" }, h("h2", { id: "at-h" }, t.name),
      t.members.some(m => m.role === "leiter") ? null : h("span", { class: "badge warn" }, "ohne Leiter")),
    h("span", { class: "small muted" }, `${plural(t.members.length, "Mitglied", "Mitglieder")} · ${plural(t.n_projects, "Projekt", "Projekte")} · angelegt ${dt(t.created_at, false)}`),
    t.members.length ? h("table", { class: "t tmembers" }, h("tbody", {}, t.members.map(m => h("tr", {},
      h("td", {}, memberName(m)),
      h("td", {}, roleSelect(m.role, `Rolle von ${m.username}`, e => run(() => setRole(m, e.target.value))())),
      h("td", { style: { textAlign: "right" } }, h("button", { class: "btn sm danger", onclick: run(() => removeMember(m)) }, "Entfernen"))))))
      : h("p", { class: "hint" }, "Keine Mitglieder."),
    h("form", { class: "chips", "aria-label": "Benutzer direkt aufnehmen", onsubmit: ev => { ev.preventDefault(); run(addMember)(); } },
      addUser, addRole, h("button", { class: "btn sm primary", type: "submit" }, "Aufnehmen"),
      h("span", { class: "hint" }, "Ohne Einladung, mit genauem Benutzernamen – z. B. wenn das Team keine Mitglieder mehr hat.")),
    t.invites.length ? h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } }, h("h3", {}, "Offene Einladungen"),
      t.invites.map(i => h("div", { class: "chips" }, h("span", {}, `${i.username} · ${ROLE_TEXT[i.role]} · von ${i.invited_by_name || "–"}`),
        h("button", { class: "btn sm", onclick: run(() => revoke(i)) }, "Zurückziehen")))) : null,
    h("div", {}, h("button", { class: "btn danger", onclick: run(delTeam) }, "Team löschen …"))));
}
