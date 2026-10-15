// Schritt 3: Messen auf der entzerrten Draufsicht bzw. Hoehenlehre
import { api, h, clear, icon, num, parseNum, toast, fail, dialog, confirmDlg, drawTag, fmtValue } from "./lib.js";
import { S, ensureProject, reloadProject, projectPicker, onLeave } from "./app.js";
import { VIEW_LABEL } from "./photos.js";
import { createPartsLayer, partsPanel, partColor } from "./edges.js";
import { DIM_GROUP_TEXT, r3, segDist } from "./geom.js";

const KIND = { length: "Strecke", height: "Höhe", diameter: "Durchmesser", radius: "Radius", angle: "Winkel", point: "Punkt" };
const NEED = { length: 2, height: 2, diameter: 3, radius: 3, angle: 3, point: 1 };
const TOOLS = [
  ["pan", "Verschieben", "V", "pan"], ["length", "Strecke", "L", "line"], ["circle", "Kreis aus 3 Punkten", "C", "circle"],
  ["point", "Punkt mit Koordinate", "P", "point"], ["angle", "Winkel", "A", "angle"], ["edges", "Kanten", "E", "edges"],
];
const BLUE = "#1F6FB2", ORANGE = "#C2410C", DARK = "#17212B";
const planar = v => v === "top" || v === "bottom";

// ------------------------------------------------------------------ Geometrie (wie app/geom.py)
export function circle3(a, b, c) {
  const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
  if (Math.abs(d) < 1e-9) return null;
  const s = p => p[0] * p[0] + p[1] * p[1];
  const ux = (s(a) * (b[1] - c[1]) + s(b) * (c[1] - a[1]) + s(c) * (a[1] - b[1])) / d;
  const uy = (s(a) * (c[0] - b[0]) + s(b) * (a[0] - c[0]) + s(c) * (b[0] - a[0])) / d;
  return [ux, uy, Math.hypot(a[0] - ux, a[1] - uy)];
}
export function compute(kind, pts, fx = 1, fy = 1) {
  if (!pts || pts.length < NEED[kind]) return null;
  const p = pts.map(([x, y]) => [x * fx, y * fy]);
  if (kind === "length" || kind === "height") return Math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]);
  if (kind === "diameter" || kind === "radius") { const c = circle3(p[0], p[1], p[2]); return c ? c[2] * (kind === "diameter" ? 2 : 1) : null; }
  if (kind === "angle") {
    const a1 = Math.atan2(p[0][1] - p[1][1], p[0][0] - p[1][0]), a2 = Math.atan2(p[2][1] - p[1][1], p[2][0] - p[1][0]);
    let d = Math.abs((a1 - a2) * 180 / Math.PI) % 360; return d > 180 ? 360 - d : d;
  }
  return null;
}

export default async function (main) {
  await ensureProject();
  if (!main.isConnected) return;  // waehrend des Ladens weg navigiert: keine Listener fuer eine fremde Seite
  main.className = "measure-layout";
  main.removeAttribute("style");

  // ---------------------------------------------------------------- Zustand
  let sources = [], src = null, img = null, pixels = null;
  let tool = "length", pts = [], cursor = null, snapOn = true, loupeOn = true, selId = null, shift = false;
  let s = 1, tx = 0, ty = 0, dirty = true, busy = false;
  let pointers = new Map(), dragStart = null, pinch = null;
  try { const st = JSON.parse(localStorage.getItem("mu.measure") || "{}"); snapOn = st.snap ?? true; loupeOn = st.loupe ?? true; } catch { /* */ }
  const saveOpts = () => { try { localStorage.setItem("mu.measure", JSON.stringify({ snap: snapOn, loupe: loupeOn })); } catch { /* */ } };

  // ---------------------------------------------------------------- DOM
  const photoSel = h("select", { "aria-label": "Foto" });
  const toolBtns = Object.fromEntries(TOOLS.map(([k, t, key, ic]) => [k, h("button", { class: "iconbtn", "aria-label": `${t} (${key})`, title: `${t} (${key})`,
    "aria-pressed": String(tool === k), onclick: () => setTool(k) }, icon(ic, 20))]));
  const snapCb = h("input", { type: "checkbox", checked: snapOn, onchange: e => { snapOn = e.target.checked; saveOpts(); upStatus(); } });
  const loupeCb = h("input", { type: "checkbox", checked: loupeOn, onchange: e => { loupeOn = e.target.checked; saveOpts(); } });
  const zoomTxt = h("span", { class: "mono small", style: { minWidth: "52px", textAlign: "center" } }, "100 %");
  const canvas = h("canvas", { role: "img", "aria-label": "Entzerrte Ansicht mit Messungen" });
  const hint = h("div", { class: "hintbar" });
  const loupeCv = h("canvas", { width: 150, height: 150 });
  const loupe = h("div", { class: "loupe", hidden: true }, loupeCv);
  const stage = h("div", { class: "stage" }, canvas, hint, loupe);
  // feste Mindestbreiten (Monospace): wechselnde Texte lassen die Leiste nicht umbrechen und die Flaeche nicht springen
  const stSpan = ch => h("span", { style: { minWidth: `${ch}ch`, whiteSpace: "nowrap" } });
  const stX = stSpan(12), stY = stSpan(12), stZoom = stSpan(11), stFac = stSpan(0), stSnap = stSpan(16), stSrc = stSpan(0);
  const status = h("div", { class: "statusbar", "aria-live": "off" }, stX, stY, stZoom, stFac, stSnap, stSrc);
  const listBox = h("ul", { class: "mlist" });
  const countEl = h("span", { class: "muted", style: { fontWeight: 400 } });
  const suggBox = h("section", { class: "sugg", "aria-labelledby": "ki-h", hidden: true });
  const mdBox = h("section", { class: "mdims", "aria-labelledby": "md-h", hidden: true });
  const suggBtn = h("button", { class: "btn claude sm", onclick: suggest, disabled: !S.status?.ai, title: S.status?.ai ? "" : "KI nicht eingerichtet" }, icon("sparkle", 16), "KI-Vorschläge");
  const edgeBtn = h("button", { class: "btn sm", onclick: detectEdges, title: "Kanten und Teile auf diesem Foto erkennen" }, icon("edges", 16), "Kanten erkennen");
  const staleEl = h("span", { class: "xs", style: { color: "var(--warn)" }, hidden: true }, "Werkstück geändert – Kanten neu erkennen");
  const upStale = () => { staleEl.hidden = !(src && planar(src.view) && S.project.photos.find(p => p.id === src.photo.id)?.edges_stale); };
  const partsBox = h("div");
  let edgeDrag = false;

  const picker = projectPicker(() => { selId = null; init(); });
  let pickerT = 0;
  const refreshPicker = () => { if (!main.isConnected) return; clearTimeout(pickerT); pickerT = setTimeout(() => picker.refresh(), 800); };
  clear(main,
    h("section", { class: "mcanvas", "aria-label": "Messfläche" },
      h("div", { class: "toolbar", "aria-label": "Werkzeuge" },
        h("label", { class: "grp" }, h("span", { class: "small muted" }, "Foto"), photoSel),
        h("div", { class: "grp", role: "toolbar" }, Object.values(toolBtns)),
        edgeBtn, staleEl,
        h("label", { class: "check small" }, snapCb, "Kantenfang"),
        h("label", { class: "check small" }, loupeCb, "Lupe"),
        h("div", { class: "grp" },
          h("button", { class: "iconbtn", "aria-label": "Verkleinern", onclick: () => zoomAt(1 / 1.25) }, icon("minus")), zoomTxt,
          h("button", { class: "iconbtn", "aria-label": "Vergrößern", onclick: () => zoomAt(1.25) }, icon("plus")),
          h("button", { class: "btn sm", onclick: fit }, "Einpassen"))),
      stage, status),
    h("aside", { class: "mside", "aria-labelledby": "m-h" },
      h("div", { class: "scroll" },
        h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, picker),
        partsBox,
        h("div", { class: "card-head" }, h("h2", { id: "m-h" }, "Messungen ", countEl),
          h("div", { class: "chips" }, h("button", { class: "btn sm", onclick: manual }, icon("plus", 16), "Manuell"), suggBtn)),
        listBox, mdBox, suggBox,
        h("div", { class: "note warn", style: { fontSize: "13px" } }, icon("info", 18),
          h("span", {}, "Maße gelten für die Tischebene. Hoch liegende Kanten wirken größer – an der Auflagekante setzen. Kritische Maße mit dem Messschieber bestätigen."))),
      h("div", { class: "foot" },
        h("a", { class: "btn", href: `/api/projects/${S.project.id}/measurements.csv`, download: "", id: "csv" }, icon("download", 16), "CSV exportieren"),
        h("a", { class: "btn primary", href: "/cad", style: { marginLeft: "auto" } }, "An CAD übergeben", icon("right")))));
  const ctx = canvas.getContext("2d");
  const layer = createPartsLayer({
    ctx: () => ctx, scr: (ix, iy) => scr(ix, iy), toPX: (X, Y) => src.toPX(X, Y), cursorMM: () => cursor?.mm || null,
    photoId: () => (src && planar(src.view) ? src.photo.id : null), active: () => tool === "edges",
    redraw: () => { dirty = true; }, changed: () => { renderList(); dirty = true; }, selectPart: () => renderList(),
  });

  // ---------------------------------------------------------------- Quellen
  function buildSources() {
    sources = [];
    for (const p of S.project.photos) {
      const view = p.view === "bottom" ? "bottom" : "top";
      if (p.files.includes("rect") && p.rect) sources.push({ key: `${p.id}:${view}`, photo: p, view, url: `/api/photos/${p.id}/rect.jpg`,
        label: `${p.filename.replace(/\.\w+$/, "")} · ${VIEW_LABEL[p.view] || "Draufsicht"}`,
        toMM: (x, y) => [x / p.rect.pxmm, p.rect.h_mm - y / p.rect.pxmm], toPX: (X, Y) => [X * p.rect.pxmm, (p.rect.h_mm - Y) * p.rect.pxmm] });
      if (p.files.includes("gauge") && p.gauge_rect) { const g = p.gauge_rect; sources.push({ key: `${p.id}:gauge`, photo: p, view: "gauge", url: `/api/photos/${p.id}/gauge.jpg`,
        label: `${p.filename.replace(/\.\w+$/, "")} · Höhenlehre`,
        toMM: (x, y) => [g.x0 + x / g.pxmm, g.y1 - y / g.pxmm], toPX: (X, Y) => [(X - g.x0) * g.pxmm, (g.y1 - Y) * g.pxmm] }); }
    }
    clear(photoSel, sources.map(x => h("option", { value: x.key }, x.label)));
  }
  photoSel.addEventListener("change", () => loadSource(sources.find(x => x.key === photoSel.value)));

  async function loadSource(x, keepView = false) {
    src = x; pts = []; pixels = null; img = null;  // kein Messen auf dem alten Bild, solange das neue laedt
    layer.reset();
    renderList();
    upStale();
    if (!x) { dirty = true; return; }
    photoSel.value = x.key;
    const im = new Image();
    im.decoding = "async";
    im.src = x.url;
    try { await im.decode(); } catch { if (src === x) { dirty = true; toast("Bild konnte nicht geladen werden", "err"); } return; }
    if (src !== x) return;
    img = im;
    if (!keepView) fit();
    setTool(tool);
    const cur = S.project.photos.find(p => p.id === x.photo.id);  // aktueller Stand: x.photo stammt aus init()
    if (planar(x.view) && cur?.has_edges) api(`/api/photos/${x.photo.id}/edges.json`)
      .then(r => { if (src === x) layer.setSegments(r.segments); }).catch(e => { if (src === x && e.status !== 404) fail(e); });
    // Graustufen fuer den Kantenfang im Hintergrund vorbereiten (1 Byte je Pixel statt RGBA)
    setTimeout(() => {
      if (src !== x) return;
      const oc = document.createElement("canvas"); oc.width = im.naturalWidth; oc.height = im.naturalHeight;
      const c = oc.getContext("2d", { willReadFrequently: true }); c.drawImage(im, 0, 0);
      try {
        const d = c.getImageData(0, 0, oc.width, oc.height).data, g = new Uint8ClampedArray(oc.width * oc.height);
        for (let i = 0, j = 0; j < g.length; i += 4, j++) g[j] = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        pixels = { w: oc.width, h: oc.height, g };
      } catch { pixels = null; }
      oc.width = oc.height = 0;
    }, 30);
    dirty = true;
  }

  // ---------------------------------------------------------------- Ansicht
  function resize() {
    const r = stage.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(r.width * dpr)); canvas.height = Math.max(1, Math.round(r.height * dpr));
    dirty = true;
  }
  function fit() {
    if (!img) return;
    const r = stage.getBoundingClientRect();
    s = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight) * 0.96;
    tx = (r.width - img.naturalWidth * s) / 2; ty = (r.height - img.naturalHeight * s) / 2;
    dirty = true; upStatus();
  }
  function zoomAt(f, sx, sy) {
    const r = stage.getBoundingClientRect();
    if (sx === undefined) { sx = r.width / 2; sy = r.height / 2; }
    const ns = Math.min(40, Math.max(0.05, s * f));
    tx = sx - (sx - tx) * ns / s; ty = sy - (sy - ty) * ns / s; s = ns;
    dirty = true; upStatus();
  }
  function centerOn(mmPts) {
    if (!src || !img || !mmPts?.length) return;
    const px = mmPts.map(p => src.toPX(p[0], p[1]));
    const xs = px.map(p => p[0]), ys = px.map(p => p[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const r = stage.getBoundingClientRect();
    tx = r.width / 2 - cx * s; ty = r.height / 2 - cy * s; dirty = true;
  }
  const scr = (ix, iy) => [ix * s + tx, iy * s + ty];
  const imgPt = (sx, sy) => [(sx - tx) / s, (sy - ty) / s];

  // ---------------------------------------------------------------- Kantenfang
  function snap(ix, iy) {
    if (!snapOn || !pixels || tool === "pan") return [ix, iy, false];
    const r = Math.round(Math.min(25, Math.max(2, 7 / s)));
    const { w, h: H, g: G } = pixels;
    const g = (x, y) => G[y * w + x];
    const x0 = Math.round(ix), y0 = Math.round(iy);
    let best = 0, bx = ix, by = iy;
    for (let y = Math.max(1, y0 - r); y <= Math.min(H - 2, y0 + r); y++) {
      for (let x = Math.max(1, x0 - r); x <= Math.min(w - 2, x0 + r); x++) {
        const dist = Math.hypot(x - ix, y - iy);
        if (dist > r) continue;
        const gx = g(x + 1, y - 1) + 2 * g(x + 1, y) + g(x + 1, y + 1) - g(x - 1, y - 1) - 2 * g(x - 1, y) - g(x - 1, y + 1);
        const gy = g(x - 1, y + 1) + 2 * g(x, y + 1) + g(x + 1, y + 1) - g(x - 1, y - 1) - 2 * g(x, y - 1) - g(x + 1, y - 1);
        const m = Math.hypot(gx, gy) * (1 - 0.35 * dist / r);
        if (m > best) { best = m; bx = x; by = y; }
      }
    }
    return best > 120 ? [bx, by, true] : [ix, iy, false];
  }

  // ---------------------------------------------------------------- Zeichnen
  const fac = () => S.project.factors || [1, 1];
  function shown() {
    if (!src) return [];
    return S.project.measurements.filter(m => m.photo_id === src.photo.id && (m.data?.view || "top") === src.view && m.data?.points?.length);
  }
  function shape(kind, mmPts, color, { sel = false, dash = false, text = "", live = false } = {}) {
    const P = mmPts.map(p => scr(...src.toPX(p[0], p[1])));
    ctx.save();
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = sel ? 2.5 : 1.8;
    if (dash) ctx.setLineDash([6, 4]);
    const dot = p => { ctx.beginPath(); ctx.arc(p[0], p[1], sel ? 4 : 3, 0, 7); ctx.fill(); };
    const cross = p => { ctx.beginPath(); ctx.moveTo(p[0] - 7, p[1]); ctx.lineTo(p[0] + 7, p[1]); ctx.moveTo(p[0], p[1] - 7); ctx.lineTo(p[0], p[1] + 7); ctx.stroke(); };
    let lp = P[0];
    if ((kind === "length" || kind === "height") && P.length >= 2) {
      ctx.beginPath(); ctx.moveTo(...P[0]); ctx.lineTo(...P[1]); ctx.stroke();
      const a = Math.atan2(P[1][1] - P[0][1], P[1][0] - P[0][0]) + Math.PI / 2;
      for (const p of P.slice(0, 2)) { ctx.beginPath(); ctx.moveTo(p[0] - 7 * Math.cos(a), p[1] - 7 * Math.sin(a)); ctx.lineTo(p[0] + 7 * Math.cos(a), p[1] + 7 * Math.sin(a)); ctx.stroke(); }
      lp = [(P[0][0] + P[1][0]) / 2 - 16 * Math.cos(a), (P[0][1] + P[1][1]) / 2 - 16 * Math.sin(a)];
    } else if ((kind === "diameter" || kind === "radius") && P.length >= 3) {
      const c = circle3(mmPts[0], mmPts[1], mmPts[2]);
      P.forEach(dot);
      if (c) {
        const C = scr(...src.toPX(c[0], c[1])); const R = c[2] * (src.view === "gauge" ? src.photo.gauge_rect.pxmm : src.photo.rect.pxmm) * s;
        ctx.beginPath(); ctx.arc(C[0], C[1], R, 0, 7); ctx.stroke(); cross(C);
        if (kind === "radius") { ctx.beginPath(); ctx.moveTo(...C); ctx.lineTo(...P[0]); ctx.stroke(); }
        lp = [C[0], C[1] - R - 16];
      }
    } else if (kind === "angle" && P.length >= 3) {
      ctx.beginPath(); ctx.moveTo(...P[0]); ctx.lineTo(...P[1]); ctx.lineTo(...P[2]); ctx.stroke(); P.forEach(dot);
      const a1 = Math.atan2(P[0][1] - P[1][1], P[0][0] - P[1][0]), a2 = Math.atan2(P[2][1] - P[1][1], P[2][0] - P[1][0]);
      let d = a2 - a1; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI;
      ctx.beginPath(); ctx.arc(P[1][0], P[1][1], 24, a1, a1 + d, d < 0); ctx.stroke();
      lp = [P[1][0] + 44 * Math.cos(a1 + d / 2), P[1][1] + 44 * Math.sin(a1 + d / 2)];
    } else if (kind === "point") {
      cross(P[0]); dot(P[0]); lp = [P[0][0], P[0][1] - 18];
    } else {
      P.forEach(dot);
      if (P.length === 2 && !live) { ctx.beginPath(); ctx.moveTo(...P[0]); ctx.lineTo(...P[1]); ctx.stroke(); }
    }
    ctx.restore();
    if (text) drawTag(ctx, lp[0], lp[1], text, color, { sel, mono: true });
  }
  function draw() {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = canvas.width / dpr, H = canvas.height / dpr;
    ctx.clearRect(0, 0, W, H);
    if (!img) { ctx.fillStyle = "#5A6672"; ctx.font = "15px 'IBM Plex Sans', sans-serif"; ctx.textAlign = "center"; ctx.fillText(sources.length ? "Bild wird geladen …" : "", W / 2, H / 2); return; }
    ctx.imageSmoothingEnabled = s < 3; ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, tx, ty, img.naturalWidth * s, img.naturalHeight * s);
    layer.draw();
    for (const m of shown()) {
      const isS = m.source === "claude" && !m.accepted;
      shape(m.kind, m.data.points, isS ? ORANGE : BLUE, { sel: m.id === selId, dash: isS, text: `${isS ? "K" : "M"}${m.seq} ${shortVal(m)}` });
    }
    if (tool !== "pan" && tool !== "edges" && pts.length) {
      const k = toolKind();
      const live = cursor ? [...pts, cursor.mm] : pts;
      const v = compute(k, live, ...fac());
      shape(live.length >= NEED[k] ? k : "partial", live, DARK, { sel: false, live: true, text: v != null && live.length >= NEED[k] ? shortVal({ kind: k, value: v }) : "" });
    }
    if (cursor && tool !== "pan") {
      const [x, y] = scr(cursor.ix, cursor.iy);
      ctx.strokeStyle = cursor.snapped ? "#2E7D4F" : DARK; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(x, y, 6, 0, 7); ctx.stroke();
    }
  }
  function shortVal(m) {
    if (m.kind === "diameter") return `Ø${num(m.value, 2)}`;
    if (m.kind === "radius") return `R${num(m.value, 2)}`;
    if (m.kind === "angle") return `${num(m.value, 1)}°`;
    if (m.kind === "point") return "";
    return num(m.value, 2);
  }
  function drawLoupe(sx, sy) {
    const r = stage.getBoundingClientRect();
    if (!loupeOn || !img || tool === "pan" || !cursor || cursor.touch) { loupe.hidden = true; return; }
    loupe.hidden = false;
    let lx = sx + 24, ly = sy + 24;
    if (lx + 150 > r.width) lx = sx - 174; if (ly + 150 > r.height) ly = sy - 174;
    loupe.style.left = `${lx}px`; loupe.style.top = `${ly}px`;
    const L = loupeCv.getContext("2d"), z = Math.max(4, s * 4);
    L.setTransform(1, 0, 0, 1, 0, 0); L.fillStyle = "#fff"; L.fillRect(0, 0, 150, 150);
    L.imageSmoothingEnabled = false;
    L.drawImage(img, cursor.ix - 75 / z, cursor.iy - 75 / z, 150 / z, 150 / z, 0, 0, 150, 150);
    L.strokeStyle = cursor.snapped ? "#2E7D4F" : "#C2410C"; L.lineWidth = 1;
    L.beginPath(); L.moveTo(75, 0); L.lineTo(75, 150); L.moveTo(0, 75); L.lineTo(150, 75); L.stroke();
    L.beginPath(); L.arc(75, 75, 5, 0, 7); L.stroke();
  }
  const loop = () => { if (dirty) { dirty = false; draw(); } raf = requestAnimationFrame(loop); };
  let raf = requestAnimationFrame(loop);

  // ---------------------------------------------------------------- Werkzeuge
  function toolKind() {
    if (tool === "length") return src?.view === "gauge" ? "height" : "length";
    if (tool === "circle") return "diameter";
    return tool;
  }
  const HINTS = {
    pan: "Ziehen = verschieben · Rad = zoomen · Messung anklicken = auswählen",
    length: "Strecke: 2 Punkte setzen · Shift = waagerecht/senkrecht · Esc = abbrechen · Ziehen = verschieben",
    height: "Höhe: Fußpunkt auf der Tischkante (0) und Oberkante setzen · Shift = senkrecht",
    circle: "Kreis: 3 Punkte auf dem Rand setzen · Backspace = letzten Punkt zurück",
    point: "Punkt: Klick setzt eine Koordinate (Ursprung unten links)",
    edges: "Kanten: Teil anklicken · Eckpunkt ziehen · Griff + an der Kantenmitte = Punkt einfügen · Entf = Punkt löschen · Esc = abbrechen",
    angle: "Winkel: Punkt auf Schenkel 1, Scheitel, Punkt auf Schenkel 2",
  };
  function setTool(k) {
    if (k !== "edges") layer.cancel();
    tool = k; pts = []; hint.hidden = false;
    for (const [t, b] of Object.entries(toolBtns)) b.setAttribute("aria-pressed", String(t === k));
    hint.textContent = HINTS[k === "length" && src?.view === "gauge" ? "height" : k];
    stage.style.cursor = k === "pan" ? "grab" : "crosshair";
    dirty = true; upStatus();
  }
  const setText = (el, t) => { if (el.textContent !== t) el.textContent = t; };
  function upStatus() {  // bei jeder Zeigerbewegung: nur Texte setzen, kein DOM-Umbau
    const f = fac();
    setText(zoomTxt, `${Math.round(s * 100)} %`);
    setText(stX, cursor ? `X ${num(cursor.mm[0] * f[0], 2, false)} mm` : "X –");
    setText(stY, cursor ? `Y ${num(cursor.mm[1] * f[1], 2, false)} mm` : "Y –");
    setText(stZoom, `Zoom ${Math.round(s * 100)} %`);
    setText(stFac, `Faktoren X ${num(f[0], 3, false)} · Y ${num(f[1], 3, false)}`);
    setText(stSnap, snapOn ? (cursor?.snapped ? "Kante gefangen" : "Kantenfang aktiv") : "Kantenfang aus");
    stSrc.hidden = !src;
    if (src) setText(stSrc, `${src.photo.format || ""} · Restfehler ${num(src.photo.max_err, 2)} mm`);
  }

  function evPos(e) { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  function updateCursor(e) {
    if (!img) return;
    const [sx, sy] = evPos(e);
    let [ix, iy] = imgPt(sx, sy);
    let snapped = false;
    [ix, iy, snapped] = snap(ix, iy);
    let mm = src.toMM(ix, iy);
    if (e.shiftKey && pts.length && (tool === "length")) {
      const p0 = pts[pts.length - 1];
      if (Math.abs(mm[0] - p0[0]) > Math.abs(mm[1] - p0[1])) mm = [mm[0], p0[1]]; else mm = [p0[0], mm[1]];
      [ix, iy] = src.toPX(...mm);
    }
    cursor = { ix, iy, mm, snapped, touch: e.pointerType === "touch" };
    dirty = true; upStatus(); drawLoupe(sx, sy);
  }
  stage.addEventListener("pointerdown", e => {
    if (e.pointerType === "touch") hint.hidden = true;
    stage.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, evPos(e));
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), s, cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2, tx, ty };
      if (edgeDrag) { edgeDrag = false; layer.cancel(); }
      dragStart = null; return;
    }
    if (tool === "edges" && e.button === 0) { updateCursor(e); if (layer.down(...evPos(e))) { edgeDrag = true; return; } }
    dragStart = { x: e.clientX, y: e.clientY, tx, ty, moved: false, btn: e.button };
    if (tool === "pan" || e.button !== 0) stage.style.cursor = "grabbing";
  });
  stage.addEventListener("pointermove", e => {
    if (pointers.has(e.pointerId)) pointers.set(e.pointerId, evPos(e));
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a[0] - b[0], a[1] - b[1]), cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
      const ns = Math.min(40, Math.max(0.05, pinch.s * d / pinch.d));
      tx = cx - (pinch.cx - pinch.tx) * ns / pinch.s; ty = cy - (pinch.cy - pinch.ty) * ns / pinch.s; s = ns;
      dirty = true; upStatus(); return;
    }
    if (edgeDrag) { updateCursor(e); layer.move(...evPos(e)); return; }
    if (dragStart) {
      const dx = e.clientX - dragStart.x, dy = e.clientY - dragStart.y;
      if (dragStart.moved || Math.hypot(dx, dy) > 5) {
        dragStart.moved = true; tx = dragStart.tx + dx; ty = dragStart.ty + dy; dirty = true;
        loupe.hidden = true; return;
      }
    }
    updateCursor(e);
  });
  const endPointer = e => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (edgeDrag) { edgeDrag = false; if (e.type === "pointercancel") layer.cancel(); else layer.up(); return; }
    const d = dragStart; dragStart = null;
    stage.style.cursor = tool === "pan" ? "grab" : "crosshair";
    if (!d || d.moved || d.btn !== 0 || e.type === "pointercancel") return;
    updateCursor(e);
    click(e);
  };
  stage.addEventListener("pointerup", endPointer);
  stage.addEventListener("pointercancel", endPointer);
  stage.addEventListener("pointerleave", () => { if (!dragStart) { cursor = null; loupe.hidden = true; dirty = true; upStatus(); } });
  stage.addEventListener("wheel", e => { e.preventDefault(); const [sx, sy] = evPos(e); zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), sx, sy); updateCursor(e); }, { passive: false });
  stage.addEventListener("contextmenu", e => e.preventDefault());

  function hit(sx, sy) {
    let best = null, bd = 12;
    for (const m of shown()) {
      const P = m.data.points.map(p => scr(...src.toPX(p[0], p[1])));
      let d = Infinity;
      if (P.length >= 2 && (m.kind === "length" || m.kind === "height" || m.kind === "angle")) {
        for (let i = 0; i + 1 < P.length; i++) d = Math.min(d, segDist([sx, sy], P[i], P[i + 1]));
      } else if ((m.kind === "diameter" || m.kind === "radius") && P.length >= 3) {
        const c = circle3(P[0], P[1], P[2]); if (c) d = Math.abs(Math.hypot(sx - c[0], sy - c[1]) - c[2]);
      } else d = Math.hypot(sx - P[0][0], sy - P[0][1]);
      if (d < bd) { bd = d; best = m; }
    }
    return best;
  }
  async function click(e) {
    if (!img || !cursor) return;
    if (tool === "edges") { layer.click(...evPos(e)); return; }
    if (tool === "pan") { const m = hit(...evPos(e)); select(m ? m.id : null); return; }
    pts.push(cursor.mm);
    const k = toolKind();
    dirty = true;
    if (pts.length < NEED[k]) return;
    if (busy) { pts.pop(); toast("Die vorige Messung wird noch gespeichert – den letzten Punkt gleich noch einmal setzen"); return; }
    const points = pts.map(p => [r3(p[0]), r3(p[1])]);
    pts = [];
    if (k !== "point" && compute(k, points) == null) { toast("Die Punkte liegen auf einer Linie – kein Kreis möglich", "err"); return; }
    busy = true;
    try {
      const m = await api(`/api/projects/${S.project.id}/measurements`, { method: "POST", body: { photo_id: src.photo.id, kind: k, view: src.view, points } });
      await reloadProject();
      selId = m.id; renderList(true);
    } catch (er) { fail(er); } finally { busy = false; dirty = true; }
  }

  const onKey = e => {
    if (e.target.closest("input,textarea,select,[contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (tool === "edges") {
      if (layer.key(e)) { e.preventDefault(); return; }
      if (k === "delete" || k === "backspace" || k === "enter") return;
    }
    const map = { v: "pan", l: "length", c: "circle", p: "point", a: "angle", e: "edges" };
    if (map[k]) { setTool(map[k]); e.preventDefault(); }
    else if (k === "escape") { pts = []; dirty = true; }
    else if (k === "backspace" && pts.length) { pts.pop(); dirty = true; e.preventDefault(); }
    else if (k === "+" || k === "=") zoomAt(1.25);
    else if (k === "-") zoomAt(0.8);
    else if (k === "0") fit();
    else if ((k === "delete" || k === "backspace") && selId) { const m = S.project.measurements.find(x => x.id === selId); if (m) del(m); }
  };
  document.addEventListener("keydown", onKey);
  const ro = new ResizeObserver(() => { const first = canvas.width <= 1; resize(); if (first) fit(); draw(); dirty = false; });  // sonst ein leerer Frame
  ro.observe(stage);
  onLeave(() => { document.removeEventListener("keydown", onKey); ro.disconnect(); cancelAnimationFrame(raf); clearTimeout(pickerT); src = null; });

  // ---------------------------------------------------------------- Liste
  function select(id, focusSource = true) {
    selId = id;
    const m = S.project.measurements.find(x => x.id === id);
    if (m && focusSource && m.data?.points?.length && m.photo_id) {
      const key = `${m.photo_id}:${m.data.view || "top"}`;
      if (!src || src.key !== key) {
        const x = sources.find(q => q.key === key);
        if (x) loadSource(x, false).then(() => {  // inzwischen kann eine andere Messung gewaehlt sein
          const cur = S.project.measurements.find(q => q.id === selId);
          if (src === x && img && cur?.data?.points?.length && `${cur.photo_id}:${cur.data.view || "top"}` === x.key) centerOn(cur.data.points);
        }).catch(fail);
      } else centerOn(m.data.points);
    }
    renderList(); dirty = true;
  }
  async function patch(m, body) {
    try {
      await api(`/api/measurements/${m.id}`, { method: "PATCH", body });
      await reloadProject(); renderList(); dirty = true;
    } catch (e) { fail(e); }
  }
  async function del(m) {
    try {
      await api(`/api/measurements/${m.id}`, { method: "DELETE" });
      await reloadProject();
      if (selId === m.id) selId = null;
      renderList(); dirty = true;
    } catch (e) { fail(e); }
  }
  function sourceText(m) {
    if (m.source === "auto") { const t = (S.project.parts || []).find(p => p.id === m.part_id); return `${KIND[m.kind]} · automatisch aus ${t ? t.id_label : "Teil"}`; }
    const ph = S.project.photos.find(p => p.id === m.photo_id);
    if (m.source === "manual") return `${KIND[m.kind]} · manuell eingegeben`;
    const v = m.data?.view === "gauge" ? "Höhenlehre" : VIEW_LABEL[ph?.view] || "Draufsicht";
    return `${KIND[m.kind]} · ${ph ? ph.filename.replace(/\.\w+$/, "") + " " : ""}${v}`;
  }
  function editPanel(m) {
    const lbl = h("input", { class: "input", value: m.label, maxlength: 80, "aria-label": `Name von M${m.seq}` });
    lbl.addEventListener("change", () => patch(m, { label: lbl.value }));
    lbl.addEventListener("keydown", e => { if (e.key === "Enter") lbl.blur(); });
    const unc = h("input", { inputmode: "decimal", value: m.unc != null ? num(m.unc, 2) : "" });
    unc.addEventListener("change", () => { const v = parseNum(unc.value); if (v != null && !Number.isNaN(v)) patch(m, { unc: v }); });
    const cal = h("input", { inputmode: "decimal", value: m.caliper != null ? num(m.caliper, 3) : "", placeholder: "–" });
    cal.addEventListener("change", () => { const v = parseNum(cal.value); if (v == null) patch(m, { clear_caliper: true }); else if (!Number.isNaN(v)) patch(m, { caliper: v }); });
    const fitIn = h("input", { class: "input", value: m.fit || "", placeholder: "z. B. H7, Spiel, Press", maxlength: 40 });
    fitIn.addEventListener("change", () => patch(m, { fit: fitIn.value.trim() }));
    const note = h("input", { class: "input", value: m.data?.note || "", placeholder: "z. B. 2×, durchgehend", maxlength: 300 });
    note.addEventListener("change", () => patch(m, { note: note.value }));
    const val = m.source === "manual" ? h("input", { inputmode: "decimal", value: num(m.value, 3) }) : null;
    if (val) val.addEventListener("change", () => { const v = parseNum(val.value); if (v != null && !Number.isNaN(v)) patch(m, { value: v }); });
    const kindSw = (m.kind === "diameter" || m.kind === "radius") && m.data?.points?.length ? h("div", { class: "seg" },
      ["diameter", "radius"].map(k => h("button", { type: "button", "aria-pressed": String(m.kind === k), onclick: () => patch(m, { kind: k }) }, KIND[k]))) : null;
    const allParts = S.project.parts || [];
    const own = allParts.find(p => p.id === m.part_id);
    const autoOk = m.source !== "manual" && planar(m.data?.view || "top") && m.kind !== "height";
    const partSel = m.source === "auto" ? null : h("select", { class: "input", "aria-label": "Teil", onchange: e => {
      const v = e.target.value; patch(m, { part_id: v === "auto" ? -1 : v === "none" ? null : Number(v) }); } },
      autoOk ? h("option", { value: "auto", selected: !m.data?.part_fixed }, "automatisch") : null,
      allParts.map(p => h("option", { value: String(p.id), selected: !!m.data?.part_fixed && m.part_id === p.id }, `${p.id_label} · ${p.label}`)),
      h("option", { value: "none", selected: (!!m.data?.part_fixed || !autoOk) && m.part_id == null }, "keins"));
    const refBox = m.caliper != null && own && ["length", "diameter", "radius"].includes(m.kind)
      ? h("label", { class: "check small" }, h("input", { type: "checkbox", checked: m.data?.ref !== false, onchange: e => patch(m, { ref: e.target.checked }) }), `Als Referenz für ${own.id_label}`) : null;
    const panel = h("div", { class: "medit", onclick: e => e.stopPropagation() },
      h("div", { class: "field" }, h("label", {}, "Bezeichnung"), lbl),
      kindSw,
      h("div", { class: "grid2" },
        val ? h("div", { class: "field" }, h("label", {}, "Wert"), h("span", { class: "unit" }, val, h("span", {}, m.unit))) : null,
        h("div", { class: "field" }, h("label", {}, "Unsicherheit ±"), h("span", { class: "unit" }, unc, h("span", {}, m.unit))),
        h("div", { class: "field" }, h("label", {}, "Messschieber"), h("span", { class: "unit" }, cal, h("span", {}, "mm")))),
      own && m.caliper == null && ["length", "diameter", "radius"].includes(m.kind) ? h("span", { class: "xs muted" }, `Messschieber-Wert wird zur Referenz für ${own.id_label} – alle Maße des Teils werden angepasst`) : null,
      refBox,
      partSel ? h("div", { class: "field" }, h("label", {}, "Teil"), partSel) : h("span", { class: "xs muted" }, `Gehört automatisch zu ${own ? own.id_label : "einem Teil"}`),
      h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", {}, "Passung"), fitIn), h("div", { class: "field" }, h("label", {}, "Notiz"), note)),
      h("div", { class: "chips", style: { justifyContent: "space-between" } },
        h("label", { class: "check small" }, h("input", { type: "checkbox", checked: !!m.critical, onchange: e => patch(m, { critical: e.target.checked }) }), "Kritisches Maß (für Passungen)"),
        h("button", { class: "btn sm danger", onclick: () => del(m) }, icon("trash", 14), "Löschen")),
      m.caliper != null ? h("span", { class: "xs", style: { color: "var(--ok)" } }, "Messschieber-Wert wird für CAD verwendet") : null,
      m.source === "claude" && m.reason ? h("span", { class: "xs muted" }, `KI: ${m.reason}`) : null);
    return { panel, focus: () => { lbl.focus(); lbl.select(); } };
  }
  function renderList(focusNew = false) {
    clear(partsBox, partsPanel({ photoId: src && planar(src.view) ? src.photo.id : null, selected: layer.selected,
      onSelect: id => { if (id) setTool("edges"); layer.select(id); }, onNew: () => { setTool("edges"); layer.startNew(); },
      onChanged: () => { renderList(); dirty = true; } }));
    const partOf = m => (S.project.parts || []).find(p => p.id === m.part_id);
    const acc = S.project.measurements.filter(m => m.accepted);
    const sugg = S.project.measurements.filter(m => !m.accepted);
    countEl.textContent = `(${acc.length})`;
    refreshPicker();
    let focusFn = null;
    clear(listBox, acc.length ? acc.map(m => {
      const sel = m.id === selId;
      const ed = sel ? editPanel(m) : null;
      if (sel && focusNew) focusFn = ed.focus;
      return h("li", { class: "mitem", "aria-current": String(sel), tabindex: 0, onclick: () => select(sel ? null : m.id), onkeydown: e => { if (e.key === "Enter" && e.target === e.currentTarget) select(sel ? null : m.id); } },
        h("span", { class: "mid" }, `M${m.seq}`),
        h("span", { style: { fontWeight: 500, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, m.label,
          m.critical ? h("span", { class: "crit" }, "kritisch") : null, m.source === "claude" ? h("span", { class: "src-claude" }, "KI") : null,
          partOf(m) ? h("span", { class: "src-part", style: { background: partColor(partOf(m)) } }, partOf(m).id_label) : null),
        h("span", { class: "mval", title: m.data?.raw != null && Math.abs(m.data.raw - m.value) > 0.004 ? `Foto ${num(m.data.raw, 2)} mm × ${num(partOf(m)?.scale ?? 1, 3)}` : "" },
          m.caliper != null ? h("span", { title: `Foto: ${fmtValue(m)}` }, `${m.kind === "diameter" ? "Ø " : ""}${num(m.caliper, 2)} mm`) : fmtValue(m),
          m.data?.nominal != null && Math.abs(m.data.nominal - (m.caliper ?? m.value)) > 0.004 ? h("span", { class: "xs muted" }, ` ≈ ${num(m.data.nominal, 1)}`) : null),
        h("span", { class: "msub" }, sourceText(m)),
        m.data?.ref_warn || m.data?.warn ? h("span", { class: "msub", style: { color: "var(--warn)" } }, m.data.ref_warn || m.data.warn) : null,
        h("span", { class: "munc" }, m.caliper != null ? "MS" : m.kind === "point" ? "" : `±${num(m.unc, 1)}`),
        ed ? ed.panel : null);
    }) : h("li", { class: "empty small", style: { padding: "20px" } }, sources.length ? "Noch keine Messungen. Werkzeug wählen und Punkte im Bild setzen." : "Keine auswertbaren Fotos."));
    if (focusFn) setTimeout(focusFn, 30);
    // Vorschlaege
    suggBox.hidden = !sugg.length;
    if (sugg.length) {
      clear(suggBox,
        h("div", { class: "card-head" }, h("h3", { id: "ki-h", style: { color: "var(--claude)" } }, "KI-Vorschläge ", h("span", { style: { fontWeight: 400 } }, `(${sugg.length})`)),
          h("span", { class: "xs muted" }, "aus Fotos geschätzt · noch nicht übernommen")),
        sugg.map(m => h("div", { class: "sitem", "aria-current": String(m.id === selId), onclick: () => select(m.id) },
          h("span", { class: "mid k" }, `K${m.seq}`),
          h("span", { style: { fontWeight: 500 } }, m.label, m.data?.unsure ? h("span", { class: "crit" }, "unsicher") : null),
          h("span", { class: "acts" },
            h("button", { class: "btn sm", onclick: e => { e.stopPropagation(); patch(m, { accepted: true }); } }, "Übernehmen"),
            h("button", { class: "iconbtn", style: { width: "34px", height: "34px" }, "aria-label": `K${m.seq} verwerfen`, onclick: e => { e.stopPropagation(); del(m); } }, icon("x", 16))),
          h("span", { class: "xs muted", style: { gridColumn: "2" } }, h("strong", { class: "mono", style: { color: "var(--text)" } }, `≈ ${fmtValue(m)}`),
            ` · ±${num(m.unc, 1)}${m.reason ? ` · ${m.reason}` : ""}`))),
        h("div", { class: "chips" },
          h("button", { class: "btn sm", onclick: async () => { try { await api(`/api/projects/${S.project.id}/measurements/accept-all`, { method: "POST" }); await reloadProject(); renderList(); dirty = true; } catch (e) { fail(e); } } }, "Alle übernehmen"),
          h("button", { class: "btn sm ghost", onclick: async () => { try { await api(`/api/projects/${S.project.id}/measurements/discard-suggestions`, { method: "POST" }); await reloadProject(); renderList(); dirty = true; } catch (e) { fail(e); } } }, "Alle verwerfen")),
        h("span", { class: "xs muted" }, "Die KI bekommt die entzerrten Fotos und deine Messungen. Übernommene Vorschläge erscheinen als normale Messung mit Herkunft „KI“."));
    }    renderModelDims();
  }

  // Spec Stufe B §4: am 3D-Modell eingetragene Messschieberwerte, gelten für alle Aufträge des Projekts
  function renderModelDims() {
    const md = S.project.model_dims || [];
    mdBox.hidden = !md.length;
    if (!md.length) { mdBox.replaceChildren(); return; }
    clear(mdBox,
      h("div", { class: "card-head" }, h("h3", { id: "md-h" }, "Messschieber am Modell ", h("span", { style: { fontWeight: 400 } }, `(${md.length})`)),
        h("span", { class: "xs muted" }, "am 3D-Modell eingetragen · gilt für alle Aufträge")),
      h("ul", { class: "mlist" }, md.map(r => h("li", { class: "mdrow" },
        h("span", { class: "mid" }, r.dim_id || "–"),
        h("span", { class: "mdl" }, r.label, h("span", { class: "xs muted" }, ` · ${DIM_GROUP_TEXT[r.grp] || r.grp}${r.job_id ? ` · Auftrag ${r.job_id}` : ""}`)),
        h("span", { class: "mval" }, `${num(r.value, 2)} mm`),
        h("button", { class: "iconbtn", style: { width: "34px", height: "34px" }, "aria-label": `${r.label} löschen`, onclick: () => delModelDim(r) }, icon("x", 16))))),
      h("span", { class: "xs muted" }, "Diese Werte gehen bei jedem Auftrag und jeder Änderung als verbindlich an die KI."));
  }
  async function delModelDim(r) {
    if (!await confirmDlg("Messschieberwert löschen?", `${r.label}: ${num(r.value, 2)} mm geht danach nicht mehr an die KI.`, "Löschen", true)) return;
    try { await api(`/api/projects/${S.project.id}/model-dims/${r.id}`, { method: "DELETE" }); await reloadProject(); renderList(); }
    catch (e) { fail(e); }
  }

  async function manual() {
    const lbl = h("input", { class: "input", placeholder: "z. B. Dicke", maxlength: 80 });
    const kind = h("select", { class: "input" }, ["length", "height", "diameter", "radius", "angle"].map(k => h("option", { value: k }, KIND[k])));
    const val = h("input", { class: "input mono", inputmode: "decimal", required: true, placeholder: "0,00" });
    const unc = h("input", { class: "input mono", inputmode: "decimal", value: "0,05" });
    const crit = h("input", { type: "checkbox" });
    const r = await dialog({ title: "Maß manuell eingeben", body: h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } },
      h("p", { class: "hint" }, "Für Werte vom Messschieber oder Maße, die auf keinem Foto zu sehen sind."),
      h("div", { class: "field" }, h("label", {}, "Bezeichnung"), lbl),
      h("div", { class: "grid3" }, h("div", { class: "field" }, h("label", {}, "Art"), kind), h("div", { class: "field" }, h("label", {}, "Wert"), val),
        h("div", { class: "field" }, h("label", {}, "± Unsicherheit"), unc)),
      h("label", { class: "check" }, crit, "Kritisches Maß")),
    actions: [{ label: "Abbrechen", value: null }, { label: "Hinzufügen", primary: true, submit: true, run: () => {
      const v = parseNum(val.value), u = parseNum(unc.value);
      if (v == null || Number.isNaN(v)) { val.setAttribute("aria-invalid", "true"); val.focus(); return false; }
      return { label: lbl.value, kind: kind.value, value: v, unc: Number.isNaN(u) ? null : u, critical: crit.checked };
    } }] });
    if (!r) return;
    try { const m = await api(`/api/projects/${S.project.id}/measurements`, { method: "POST", body: r }); await reloadProject(); selId = m.id; renderList(); } catch (e) { fail(e); }
  }

  async function detectEdges() {
    if (!src || !planar(src.view)) { toast("Kanten lassen sich nur auf einer Draufsicht erkennen", "err"); return; }
    if ((S.project.parts || []).some(p => p.photo_id === src.photo.id) &&
      !await confirmDlg("Kanten neu erkennen?", "Teile dieses Fotos werden neu erkannt. Wiedergefundene Teile behalten Bezeichnung und Messschieber-Referenzen.", "Neu erkennen")) return;
    const old = [...edgeBtn.childNodes], phid = src.photo.id;
    clear(edgeBtn, h("span", { class: "spin" }), "Kanten werden erkannt …"); edgeBtn.disabled = true;
    try {
      const r = await api(`/api/photos/${phid}/edges`, { method: "POST", body: { use_ai: true } });
      await reloadProject();
      upStale();
      if (src?.photo.id === phid) { layer.setSegments(r.segments); setTool("edges"); }
      renderList(); dirty = true;
      toast(r.notice || `${r.parts.length} Teil${r.parts.length === 1 ? "" : "e"} erkannt`, r.notice ? "" : "ok");
    } catch (e) { fail(e); } finally { clear(edgeBtn, ...old); edgeBtn.disabled = false; }
  }

  async function suggest() {
    if (!src) { toast("Erst ein auswertbares Foto hochladen", "err"); return; }
    const old = [...suggBtn.childNodes];
    clear(suggBtn, h("span", { class: "spin" }), "KI analysiert …");
    suggBtn.disabled = true;
    try {
      await api(`/api/projects/${S.project.id}/suggest`, { method: "POST", body: { photo_id: src.photo.id } });
      await reloadProject();
      renderList(); dirty = true;
      const n = S.project.measurements.filter(m => !m.accepted).length;
      toast(n ? `${n} KI-Vorschläge` : "Die KI hat keine weiteren Maße gefunden", n ? "ok" : "");
    } catch (e) { fail(e); } finally { clear(suggBtn, ...old); suggBtn.disabled = !S.status?.ai; }
  }

  // ---------------------------------------------------------------- Start
  async function init() {
    buildSources();
    document.getElementById("csv")?.setAttribute("href", `/api/projects/${S.project.id}/measurements.csv`);
    renderList();
    if (!sources.length) {
      img = null; src = null; dirty = true;
      hint.textContent = "Keine entzerrten Fotos – zuerst unter „Fotos prüfen“ hochladen.";
      return;
    }
    let pref = null;
    try { pref = sessionStorage.getItem("mu.src"); } catch { /* */ }
    await loadSource(sources.find(x => x.key === pref) || sources.find(x => planar(x.photo.view)) || sources[0]);
  }
  photoSel.addEventListener("change", () => { try { sessionStorage.setItem("mu.src", photoSel.value); } catch { /* */ } });
  resize();
  await init();
  setTool(tool);
}
