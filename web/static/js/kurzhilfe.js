// Kurzhilfe (Taste ? oder F1) und Tabellen der Tastenkürzel – beide aus help.js
import { h, icon } from "./lib.js";
import { onLeave } from "./app.js";
import { SHORTCUTS, GROUP_TITLE, SEPARATORS, isKey, groupsFor } from "./help.js";

// „Shift + Klick“, „+ oder =“, „Tab dann Enter“: Tasten als <kbd>, Mausbefehle als Text
export function keyCell(keys) {
  const out = [];
  keys.forEach((k, i) => {
    if (SEPARATORS[k]) { out.push(SEPARATORS[k]); return; }
    if (i > 0 && !SEPARATORS[keys[i - 1]]) out.push(" + ");
    out.push(isKey(k) ? h("kbd", {}, k) : h("span", { class: "mouse" }, k));
  });
  return out;
}

export function shortcutTable(group, idPrefix = "keys") {
  const id = `${idPrefix}-${group}`;
  return h("div", { class: "keytable" },
    h("h3", { id }, GROUP_TITLE[group]),
    h("table", { class: "t keys", "aria-labelledby": id },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Taste / Maus"), h("th", { scope: "col" }, "Wirkung"))),
      h("tbody", {}, SHORTCUTS[group].map(s => h("tr", {}, h("td", { class: "kc" }, keyCell(s.keys)), h("td", {}, s.text))))));
}

let open = null;   // { dlg, back }
let leaveHooked = false;   // Seitenwechsel schliesst die Kurzhilfe; je Seite nur einmal angemeldet

export function closeShortcuts() {
  if (!open) return;
  const { dlg, back } = open;
  open = null;
  if (dlg.open) dlg.close();
  dlg.remove();
  if (back?.isConnected) back.focus();
}

export function toggleShortcuts(path) {
  if (open) { closeShortcuts(); return; }
  const back = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const closeBtn = h("button", { class: "iconbtn", type: "button", "aria-label": "Kurzhilfe schließen", onclick: closeShortcuts }, icon("x"));
  const dlg = h("dialog", { class: "keysdlg", role: "dialog", "aria-modal": "true", "aria-labelledby": "kh-t" },
    h("div", { class: "kh" },
      h("div", { class: "card-head" }, h("h2", { id: "kh-t" }, "Tastenkürzel und Maus"), closeBtn),
      groupsFor(path).map(g => shortcutTable(g, "kh")),
      h("p", { class: "small muted" }, "Tastenkürzel wirken nicht, solange der Fokus in einem Eingabefeld liegt."),
      h("a", { href: "/anleitung#tastatur", onclick: () => closeShortcuts() }, "Ganze Anleitung", icon("right", 16))));
  // Tasten nicht an die Seite dahinter weiterreichen (z. B. Werkzeugtasten der Messseite); Esc schließt
  dlg.addEventListener("keydown", e => {
    e.stopPropagation();
    if (e.key === "Escape" || e.key === "?" || e.key === "F1") { e.preventDefault(); closeShortcuts(); }
  });
  dlg.addEventListener("cancel", e => { e.preventDefault(); closeShortcuts(); });
  // Klick auf den Hintergrund schliesst; Klicks im Dialogrechteck (auch auf seine Bildlaufleiste) nicht
  dlg.addEventListener("click", e => {
    if (e.target !== dlg) return;
    const r = dlg.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) closeShortcuts();
  });
  document.body.append(dlg);
  dlg.showModal();
  open = { dlg, back };
  closeBtn.focus();
  if (!leaveHooked) {
    leaveHooked = true;
    onLeave(() => { leaveHooked = false; closeShortcuts(); });
  }
}
