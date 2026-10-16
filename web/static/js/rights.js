// Rechte und Bereiche der Bibliothek ohne DOM (Spec Teams §2, §7) – auch für node --test.
// Nur Komfort für die Oberfläche: der Server prüft jede Aktion selbst (web/app/access.py).

export const ROLE_TEXT = Object.freeze({ besitzer: "Besitzer", admin: "Administrator", leiter: "Leiter", mitglied: "Mitglied", lesend: "Lesend" });

// Was die Oberfläche für ein Projekt anbietet: p.rights kommt vom Server (access.allowed, dieselbe Regel wie die
// Routen); ohne Angabe wird nichts angeboten
export function projectRights(p) {
  const r = p?.rights || {};
  return { write: !!r.write, delete: !!r.delete, move: !!r.move, copy: !!r.copy };
}

// Gemerkter Bereich der Bibliothek in diesem Browser; library.js und teams.js lesen und schreiben ihn nur hierüber
export const SCOPE_KEY = "lib.scope";
export function loadScope() { try { return localStorage.getItem(SCOPE_KEY) || "private"; } catch { return "private"; } }
export function saveScope(v) { try { localStorage.setItem(SCOPE_KEY, v); } catch { /* */ } }

// Gemerkter Bereich (lib.scope): "private" oder "team:<id>" eines eigenen Teams; alles andere wird "private"
export function validScope(stored, teams) {
  const m = /^team:([1-9][0-9]*)$/.exec(String(stored ?? ""));
  return m && (teams || []).some(t => t.id === Number(m[1])) ? `team:${Number(m[1])}` : "private";
}

// Team-ID aus einem Bereich: "team:<id>" -> Zahl, sonst null (privat)
export function teamIdOf(scope) {
  const m = /^team:([1-9][0-9]*)$/.exec(String(scope ?? ""));
  return m ? Number(m[1]) : null;
}

// Zeile unter dem Namen einer Team-Karte; gelöschte und ausgetretene Ersteller heißen „ehemaliges Mitglied“
export function creatorText(p) {
  if (p?.team_id == null) return "";
  return p.creator && p.creator_is_member ? `von ${p.creator.name}` : "von ehemaligem Mitglied";
}

// Projektauswahl: Gruppe „Privat“ zuerst, dann je Team nach Name; die Reihenfolge der Projekte bleibt
export function groupProjects(list) {
  const priv = { key: "private", label: "Privat", items: [] }, byTeam = new Map();
  for (const p of list || []) {
    if (p.team_id == null) { priv.items.push(p); continue; }
    if (!byTeam.has(p.team_id)) byTeam.set(p.team_id, { key: `team:${p.team_id}`, label: p.team_name || `Team ${p.team_id}`, items: [] });
    byTeam.get(p.team_id).items.push(p);
  }
  const teams = [...byTeam.values()].sort((a, b) => a.label.localeCompare(b.label, "de") || a.key.localeCompare(b.key));
  return [priv, ...teams].filter(g => g.items.length);
}

// Rolle „Lesend“: Fotos, Messen und CAD nur ansehen (Spec Teams §7)
export const isReadOnly = p => p?.my_role === "lesend";
export const readOnlyText = p => `Nur ansehen – Rolle Lesend im Team ${p?.team_name || ""}`.trim();

// Betrifft eine 404-Antwort auf `path` das offene Projekt (projectId) bzw. den offenen Auftrag (jobId)? Nur dann ist der
// Zugriff darauf verloren; ein 404 auf ein anderes Projekt (Projektwahl, veraltete Merkung) darf die Seite nicht verlassen.
export function notFoundConcerns(path, projectId, jobId) {
  const p = String(path || "").split("?")[0];
  const under = base => p === base || p.startsWith(`${base}/`);
  if (jobId != null && under(`/api/jobs/${jobId}`)) return "job";
  if (projectId != null && under(`/api/projects/${projectId}`)) return "project";
  return null;
}
