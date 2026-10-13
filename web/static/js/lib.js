// Gemeinsame Hilfen: API, DOM, Formatierung, Toasts, Dialoge, Symbole

export class ApiError extends Error {
  constructor(status, detail) { super(detail); this.status = status; }
}

function detailText(d) {
  if (!d) return "Unbekannter Fehler";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map(x => x.msg || JSON.stringify(x)).join("; ");
  return d.detail ? detailText(d.detail) : JSON.stringify(d);
}

export async function api(path, { method = "GET", body, form, signal } = {}) {
  const opt = { method, headers: { "X-Requested-With": "fetch" }, credentials: "same-origin", signal };
  if (form) opt.body = form;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  let r;
  try { r = await fetch(path, opt); }
  catch (e) { if (e.name === "AbortError") throw e; throw new ApiError(0, "Server nicht erreichbar"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json().catch(() => null) : await r.text();
  if (!r.ok) {
    const err = new ApiError(r.status, detailText(data && data.detail !== undefined ? data.detail : data));
    if (r.status === 401 && !path.startsWith("/api/auth/") && api.onUnauthorized) api.onUnauthorized();
    if (r.status === 403 && err.message.startsWith("Passwort muss") && api.onMustChange) api.onMustChange();
    throw err;
  }
  return data;
}

export function upload(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", path);
    x.setRequestHeader("X-Requested-With", "fetch");
    x.upload.onprogress = e => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
    x.onload = () => {
      let d = null; try { d = JSON.parse(x.responseText); } catch { /* */ }
      if (x.status >= 200 && x.status < 300) resolve(d);
      else reject(new ApiError(x.status, detailText(d && d.detail !== undefined ? d.detail : x.statusText)));
    };
    x.onerror = () => reject(new ApiError(0, "Upload fehlgeschlagen"));
    x.send(form);
  });
}

// DOM ------------------------------------------------------------------
export function h(tag, attrs, ...kids) {
  const el = document.createElementNS(tag === "svg" || attrs?.__svg ? "http://www.w3.org/2000/svg" : "http://www.w3.org/1999/xhtml", tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false || k === "__svg") continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "html") el.innerHTML = v; // nur fuer konstante Inhalte (Symbole)
    else if (k === "value" && "value" in el) el.value = v;
    else if ((k === "checked" || k === "selected" || k === "disabled") && k in el) el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const c of kids) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}
export const $ = (sel, root = document) => root.querySelector(sel);
export function clear(el, ...kids) { el.replaceChildren(); append(el, kids); return el; }

export function icon(name, size = 18) {
  const s = h("span", { class: "ico", "aria-hidden": "true", style: { display: "inline-flex" } });
  s.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
  return s;
}
export const ICONS = {
  download: '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8M8 17h5"/>',
  printer: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
  upload: '<path d="M12 21V9"/><path d="M7 14l5-5 5 5"/><path d="M4 3h16"/>',
  camera: '<path d="M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="4"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>', right: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  check: '<path d="M5 12l5 5 9-10"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>', warn: '<path d="M12 3l10 18H2z"/><path d="M12 10v5"/><path d="M12 18h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5h.01"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3 3.8M6.1 6.1C3.6 7.8 2 12 2 12s4 7 10 7a9.6 9.6 0 0 0 5.2-1.5"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  pan: '<path d="M12 2v20M2 12h20"/><path d="M9 5l3-3 3 3M9 19l3 3 3-3M5 9l-3 3 3 3M19 9l3 3-3 3"/>',
  line: '<circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/><path d="M6.5 17.5l11-11"/>',
  circle: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="4" r="1.6" fill="currentColor"/><circle cx="5" cy="15" r="1.6" fill="currentColor"/><circle cx="19" cy="15" r="1.6" fill="currentColor"/>',
  point: '<path d="M12 3v6M12 15v6M3 12h6M15 12h6"/><circle cx="12" cy="12" r="2"/>',
  angle: '<path d="M4 20h16"/><path d="M4 20L16 5"/><path d="M10 20a6 6 0 0 0-2-4.5"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 3v4M17 5h4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>', trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>', full: '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>',
  cube: '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 22V12M21 7l-9 5-9-5"/>', users: '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>', key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>', copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>', refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  zip: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M10 3v2M10 7v2M10 11v2"/><rect x="9" y="14" width="3" height="4" rx="1"/>',
  folder: '<path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
};

export const LOGO = () => {
  const s = h("span", { "aria-hidden": "true", style: { display: "inline-flex" } });
  s.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="#17212B" stroke-width="1.6"><rect x="2" y="2" width="24" height="24" rx="3"/><path d="M9 2v24M16 2v24M2 9h24M2 16h24" stroke="#9FB0C1"/><rect x="4.5" y="4.5" width="6" height="6" fill="#17212B" stroke="none"/><rect x="17.5" y="17.5" width="6" height="6" fill="#17212B" stroke="none"/></svg>';
  return s;
};

// Formatierung -----------------------------------------------------------
const nf = {};
export function num(v, d = 2, trim = true) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const key = d + (trim ? "t" : "");
  nf[key] ||= new Intl.NumberFormat("de-DE", { minimumFractionDigits: trim ? 0 : d, maximumFractionDigits: d });
  return nf[key].format(v);
}
export function parseNum(s) {
  if (s === null || s === undefined) return null;
  const t = String(s).trim().replace(/\s/g, "").replace(",", ".");
  if (!t) return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : NaN;
}
export function dt(iso, withTime = true) {
  if (!iso) return "–";
  const d = new Date(iso), now = new Date();
  const t = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const day = 864e5, d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (d >= d0) return withTime ? `heute ${t}` : "heute";
  if (d >= d0 - day) return withTime ? `gestern ${t}` : "gestern";
  const ds = d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  return withTime ? `${ds}, ${t}` : ds;
}
export function until(iso) {
  const ms = new Date(iso) - new Date();
  if (ms <= 0) return "abgelaufen";
  const hrs = ms / 36e5;
  if (hrs < 24) return `läuft in ${Math.max(1, Math.round(hrs))} Std. ab`;
  const days = Math.round(hrs / 24);
  return days === 1 ? "läuft morgen ab" : `läuft in ${days} Tagen ab`;
}
export function bytes(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${num(n / 1024, 0)} KB`;
  return `${num(n / 1048576, 1)} MB`;
}
export function initials(u) {
  const n = (u.display_name || u.username || "?").trim();
  const p = n.split(/[\s._-]+/).filter(Boolean);
  return ((p[0]?.[0] || "?") + (p[1]?.[0] || p[0]?.[1] || "")).toUpperCase();
}
export function mmss(sec) {
  sec = Math.max(0, Math.floor(sec));
  return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
}

// Toast & Dialog -----------------------------------------------------------
export function toast(msg, kind = "") {
  const box = document.getElementById("toasts");
  const t = h("div", { class: `toast ${kind}` }, msg);
  box.append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}
export function fail(e) {
  if (e && e.name === "AbortError") return;
  console.error(e);
  toast(e?.message || String(e), "err");
}

export function dialog({ title, body, actions }) {
  return new Promise(resolve => {
    const d = h("dialog", { "aria-labelledby": "dlg-t" });
    const close = v => { d.close(); d.remove(); resolve(v); };
    const acts = (actions || [{ label: "OK", value: true, primary: true }]).map(a =>
      h("button", { type: a.submit ? "submit" : "button", class: `btn ${a.primary ? "primary" : ""} ${a.danger ? "danger" : ""}`,
        onclick: async ev => {
          if (a.submit) return;
          ev.preventDefault();
          if (a.run) { const v = await a.run(d); if (v === false) return; close(v); } else close(a.value);
        } }, a.label));
    const form = h("form", { class: "dlg", method: "dialog", onsubmit: async ev => {
      ev.preventDefault();
      const a = (actions || []).find(x => x.submit);
      if (!a) return;
      const v = a.run ? await a.run(d) : a.value;
      if (v !== false) close(v);
    } }, h("h2", { id: "dlg-t" }, title), body, h("div", { class: "dlg-actions" }, acts));
    d.append(form);
    d.addEventListener("cancel", ev => { ev.preventDefault(); close(undefined); });
    document.body.append(d);
    d.showModal();
    const first = d.querySelector("input,textarea,select");
    if (first) first.focus();
  });
}
export function confirmDlg(title, text, label = "Bestätigen", danger = false) {
  return dialog({ title, body: h("p", {}, text), actions: [
    { label: "Abbrechen", value: false }, { label, value: true, primary: !danger, danger } ] });
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// Passwortstaerke (grob, nur Anzeige)
export function strength(pw) {
  if (!pw) return 0;
  let classes = 0;
  if (/[a-z]/.test(pw)) classes++; if (/[A-Z]/.test(pw)) classes++;
  if (/\d/.test(pw)) classes++; if (/[^\w]/.test(pw)) classes++;
  const uniq = new Set(pw).size;
  let s = pw.length * (1 + classes * 0.35) * Math.min(1, uniq / 6);
  if (s < 12) return 1; if (s < 20) return 2; if (s < 30) return 3; return 4;
}
export const STRENGTH_TEXT = ["", "Schwach", "Mittel", "Gut", "Stark"];
