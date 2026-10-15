// Kanten und Teile auf der Messflaeche: Zeichnen, Bearbeiten, Seitenleiste (Spec 2026-10-14 §4)
import { api, h, icon, num, toast, fail, confirmDlg, drawTag } from "./lib.js";
import { S, reloadProject } from "./app.js";
import { r3, unassignedSegments, pickPolygon } from "./geom.js";

export const PART_COLORS = ["#0F766E", "#7C3AED", "#B45309", "#BE185D", "#4D7C0F", "#0369A1"];
export const partColor = p => PART_COLORS[(p.seq - 1) % PART_COLORS.length];
export const ROLE = { body: "Grundkörper", mounted: "montiertes Teil" };
const HANDLE = 7, DARK = "#17212B";

function plus(ctx, [x, y], col) {
  ctx.fillStyle = "#fff"; ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.setLineDash([]);
  ctx.beginPath(); ctx.arc(x, y, HANDLE - 1, 0, 7); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x - 3.5, y); ctx.lineTo(x + 3.5, y); ctx.moveTo(x, y - 3.5); ctx.lineTo(x, y + 3.5); ctx.stroke();
}

// env: { ctx(), scr(ix, iy), toPX(X, Y), cursorMM() -> [X, Y] | null, photoId() -> id | null, active() -> bool,
//        redraw(), changed(), selectPart(id) }
export function createPartsLayer(env) {
  let sel = null, vtx = null, drag = null, drawing = null, segments = [], busy = false;
  const list = () => (env.photoId() ? (S.project.parts || []).filter(p => p.photo_id === env.photoId()) : []);
  const P = q => env.scr(...env.toPX(q[0], q[1]));
  const selPart = () => list().find(p => p.id === sel) || null;

  let uc = null;  // unassigned() nur neu berechnen, wenn sich Kandidaten, Teile oder Foto aendern
  function unassigned() {
    const parts = S.project.parts, photo = env.photoId();
    if (uc?.segs !== segments || uc.parts !== parts || uc.photo !== photo)
      uc = { segs: segments, parts, photo, out: unassignedSegments(segments, list().map(p => p.polygon)) };
    return uc.out;
  }
  function draw() {
    if (!env.photoId()) return;
    const ctx = env.ctx(), act = env.active();
    ctx.save();
    if (act) {
      ctx.strokeStyle = "#8A96A3"; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
      for (const s of unassigned()) { ctx.beginPath(); ctx.moveTo(...P(s.a)); ctx.lineTo(...P(s.b)); ctx.stroke(); }
    }
    for (const part of list()) {
      const live = drag?.id === part.id;
      const pts = (live ? drag.poly : part.polygon).map(P);
      const col = partColor(part), isSel = part.id === sel;
      ctx.setLineDash([]); ctx.fillStyle = col + (isSel ? "22" : "12");
      ctx.beginPath(); pts.forEach((q, i) => (i ? ctx.lineTo(...q) : ctx.moveTo(...q))); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = isSel ? 2.6 : 1.8;
      pts.forEach((q, i) => {
        const hid = !live && part.hidden.includes(part.edge_ids[i]);
        ctx.setLineDash(hid ? [6, 5] : []);
        ctx.beginPath(); ctx.moveTo(...q); ctx.lineTo(...pts[(i + 1) % pts.length]); ctx.stroke();
      });
      const c = pts.reduce((a, q) => [a[0] + q[0] / pts.length, a[1] + q[1] / pts.length], [0, 0]);
      drawTag(ctx, c[0], c[1], `${part.id_label} ${part.label}`, col);
      if (act && isSel) {
        pts.forEach((q, i) => {
          ctx.setLineDash([]); ctx.fillStyle = i === vtx ? col : "#fff"; ctx.strokeStyle = col; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(q[0], q[1], HANDLE - 2, 0, 7); ctx.fill(); ctx.stroke();
        });
        if (!drag) pts.forEach((q, i) => { const r = pts[(i + 1) % pts.length]; plus(ctx, [(q[0] + r[0]) / 2, (q[1] + r[1]) / 2], col); });
      }
    }
    if (drawing) {
      const pts = drawing.map(P), cur = env.cursorMM();
      if (cur) pts.push(P(cur));
      ctx.setLineDash([]); ctx.strokeStyle = DARK; ctx.lineWidth = 1.8;
      ctx.beginPath(); pts.forEach((q, i) => (i ? ctx.lineTo(...q) : ctx.moveTo(...q))); ctx.stroke();
      ctx.fillStyle = DARK;
      drawing.map(P).forEach(q => { ctx.beginPath(); ctx.arc(q[0], q[1], 4, 0, 7); ctx.fill(); });
    }
    ctx.restore();
  }
  function hitVertex(sx, sy) {
    const part = selPart(); if (!part) return null;
    const i = part.polygon.findIndex(q => { const s = P(q); return Math.hypot(s[0] - sx, s[1] - sy) <= HANDLE + 2; });
    return i >= 0 ? { part, i } : null;
  }
  function hitPlus(sx, sy) {
    const part = selPart(); if (!part) return null;
    const pts = part.polygon.map(P);
    for (let i = 0; i < pts.length; i++) {
      const r = pts[(i + 1) % pts.length];
      if (Math.hypot((pts[i][0] + r[0]) / 2 - sx, (pts[i][1] + r[1]) / 2 - sy) <= HANDLE + 2) return { part, i };
    }
    return null;
  }
  function hitPart(sx, sy) {
    const ps = list(), i = pickPolygon([sx, sy], ps.map(p => p.polygon.map(P)));
    return i >= 0 ? ps[i] : null;
  }
  function select(id) { sel = id; vtx = null; env.selectPart?.(id); env.redraw(); }
  async function save(id, body) {  // busy: kein zweites Ziehen auf veraltetem Stand, bis neu geladen ist
    busy = true;
    try {
      try { await api(`/api/parts/${id}`, { method: "PATCH", body }); } catch (e) { fail(e); }
      await reloadProject().catch(fail);
    } finally { busy = false; }
    env.changed();
  }
  async function finishNew() {
    if (!drawing || drawing.length < 3) { toast("Mindestens 3 Punkte setzen", "err"); return; }
    const polygon = drawing; drawing = null;
    try {
      const p = await api(`/api/projects/${S.project.id}/parts`, { method: "POST", body: { photo_id: env.photoId(), label: "", role: "body", polygon } });
      await reloadProject(); sel = p.id; env.changed();
    } catch (e) { drawing = polygon; fail(e); env.redraw(); }  // Gezeichnetes nicht verlieren
  }

  // Zeiger: down() liefert true, wenn die Ebene das Ziehen uebernimmt (Eckpunkt oder Griff „+“)
  function down(sx, sy) {
    if (drawing || busy) return false;
    const v = hitVertex(sx, sy);
    if (v) { vtx = v.i; drag = { id: v.part.id, i: v.i, poly: v.part.polygon.map(q => [...q]), moved: false, sx, sy }; env.redraw(); return true; }
    const pl = hitPlus(sx, sy);
    if (pl) {
      const poly = pl.part.polygon.map(q => [...q]), a = poly[pl.i], b = poly[(pl.i + 1) % poly.length];
      poly.splice(pl.i + 1, 0, [r3((a[0] + b[0]) / 2), r3((a[1] + b[1]) / 2)]);
      vtx = pl.i + 1; drag = { id: pl.part.id, i: pl.i + 1, poly, moved: true, sx, sy }; env.redraw(); return true;
    }
    return false;
  }
  function move(sx, sy) {
    if (!drag) return false;
    if (!drag.moved && Math.hypot(sx - drag.sx, sy - drag.sy) < 3) return true;
    drag.moved = true;
    const mm = env.cursorMM(); if (mm) drag.poly[drag.i] = [r3(mm[0]), r3(mm[1])];
    env.redraw(); return true;
  }
  async function up() {
    const d = drag; drag = null;
    if (!d) return false;
    if (!d.moved) { env.redraw(); return true; }
    await save(d.id, { polygon: d.poly });
    return true;
  }
  async function click(sx, sy) {
    if (drawing) {
      const mm = env.cursorMM(); if (!mm) return;
      if (drawing.length >= 3) { const f = P(drawing[0]); if (Math.hypot(f[0] - sx, f[1] - sy) <= 10) { await finishNew(); return; } }
      drawing.push([r3(mm[0]), r3(mm[1])]); env.redraw(); return;
    }
    const p = hitPart(sx, sy); select(p ? p.id : null);
  }
  // Tasten nur im Werkzeug „Kanten“; true = verarbeitet
  function key(e) {
    const k = e.key;
    if (busy && (k === "Delete" || k === "Backspace")) return true;
    if (drawing) {
      if (k === "Escape") { drawing = null; env.redraw(); return true; }
      if (k === "Enter") { finishNew(); return true; }
      if (k === "Backspace" || k === "Delete") { drawing.pop(); env.redraw(); return true; }
      return false;
    }
    if ((k === "Delete" || k === "Backspace") && sel && vtx != null) {
      const part = selPart(); if (!part) return false;
      if (part.polygon.length <= 3) { toast("Ein Teil braucht mindestens 3 Eckpunkte", "err"); return true; }
      const poly = part.polygon.filter((_, i) => i !== vtx); vtx = null;
      save(part.id, { polygon: poly }); return true;
    }
    if (k === "Escape" && sel) { select(null); return true; }
    return false;
  }
  return {
    draw, down, move, up, click, key, select,
    startNew() { drawing = []; sel = null; vtx = null; env.redraw(); },
    cancel() { drawing = null; drag = null; env.redraw(); },
    reset() { sel = null; vtx = null; drag = null; drawing = null; segments = []; },
    setSegments(s) { segments = s || []; env.redraw(); },
    get selected() { return sel; }, get drawing() { return !!drawing; },
  };
}

export function partsPanel({ photoId, selected, onSelect, onNew, onChanged }) {
  const ps = (S.project.parts || []).filter(p => p.photo_id === photoId);
  async function patchPart(p, body) {
    try { await api(`/api/parts/${p.id}`, { method: "PATCH", body }); await reloadProject(); onChanged(); } catch (e) { fail(e); }
  }
  async function delPart(p) {
    if (!await confirmDlg(`${p.id_label} löschen?`, "Automatische Maße des Teils werden entfernt. Maße mit Messschieber-Wert bleiben als normale Messung erhalten.", "Löschen", true)) return;
    try { await api(`/api/parts/${p.id}`, { method: "DELETE" }); await reloadProject(); onSelect(null); onChanged(); } catch (e) { fail(e); }
  }
  function editor(p) {
    const lbl = h("input", { class: "input", value: p.label, maxlength: 80, "aria-label": `Name von ${p.id_label}` });
    lbl.addEventListener("change", () => patchPart(p, { label: lbl.value }));
    lbl.addEventListener("keydown", e => { if (e.key === "Enter") lbl.blur(); });
    const role = h("select", { class: "input", "aria-label": "Rolle", onchange: e => patchPart(p, { role: e.target.value }) },
      Object.entries(ROLE).map(([k, t]) => h("option", { value: k, selected: k === p.role }, t)));
    return h("div", { class: "medit", onclick: e => e.stopPropagation() },
      h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", {}, "Bezeichnung"), lbl), h("div", { class: "field" }, h("label", {}, "Rolle"), role)),
      p.note ? h("span", { class: "xs muted" }, `KI: ${p.note}`) : null,
      h("div", { class: "chips", style: { justifyContent: "flex-end" } }, h("button", { class: "btn sm danger", onclick: () => delPart(p) }, icon("trash", 14), "Teil löschen")));
  }
  const items = ps.map(p => {
    const isSel = p.id === selected, col = partColor(p);
    const scaled = Math.abs(p.scale - 1) > 1e-6;
    return h("li", { class: "mitem", "aria-current": String(isSel), tabindex: 0, style: { borderLeft: `4px solid ${col}` },
      onclick: () => onSelect(isSel ? null : p.id), onkeydown: e => { if (e.key === "Enter" && e.target === e.currentTarget) onSelect(isSel ? null : p.id); } },
      h("span", { class: "mid", style: { color: col } }, p.id_label),
      h("span", { style: { fontWeight: 500, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, p.label),
      h("span", { class: "mval" }, p.rect && p.size ? `${num(p.size[0], 2)} × ${num(p.size[1], 2)} mm` : `${p.n_edges} Kanten`),
      h("span", { class: "msub" }, ROLE[p.role], p.view === "bottom" ? " · unten" + (p.same_as ? ` = T${(S.project.parts.find(q => q.id === p.same_as) || {}).seq ?? "?"}` : "") : "",
        scaled ? h("span", {}, ` · Maßstab × ${num(p.scale, 3)}${p.refs.length ? ` aus ${p.refs.join(", ")}` : ""} `,
          h("button", { class: "btn sm ghost", style: { minHeight: "24px", padding: "0 6px" }, onclick: e => { e.stopPropagation(); patchPart(p, { reset_scale: true }); } }, "Zurücksetzen")) : null),
      p.warn ? h("span", { class: "msub", style: { color: "var(--warn)" } }, p.warn) : null,
      isSel ? editor(p) : null);
  });
  return h("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } },
    h("div", { class: "card-head" }, h("h2", { id: "t-h" }, "Teile ", h("span", { class: "muted", style: { fontWeight: 400 } }, `(${ps.length})`)),
      h("button", { class: "btn sm", onclick: onNew, disabled: !photoId }, icon("plus", 16), "Neues Teil")),
    ps.length ? h("ul", { class: "mlist", "aria-labelledby": "t-h" }, items)
      : h("p", { class: "xs muted", style: { margin: 0 } }, photoId ? "Noch keine Teile. „Kanten erkennen“ oder „Neues Teil“ zeichnen." : "Teile gibt es nur auf einer Draufsicht."),
    photoId ? h("p", { class: "xs muted", style: { margin: 0 } }, "Grenzen: Weiße Teile auf weißem Papier und harte Schlagschatten verfälschen den Umriss – dann die Eckpunkte von Hand korrigieren.") : null);
}
