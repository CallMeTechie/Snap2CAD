// 3D-Ansicht: drehbar, zoombar, verschiebbar (three.js + OrbitControls), mit Bemaßung am Modell (Spec Stufe B §3)
import * as THREE from "../vendor/three/three.module.js";
import { OrbitControls } from "../vendor/three/OrbitControls.js";
import { STLLoader } from "../vendor/three/STLLoader.js";
import { num, toast } from "./lib.js";
import { DEFAULT_SEL, de, dimGeometry, dimStyle, hasAnchors, parseDimInput, visibleDims } from "./geom.js";

const VIEWS = {
  iso: { dir: [1, -1.25, 0.95], up: [0, 0, 1] },
  top: { dir: [0, 0, 1], up: [0, 1, 0] },
  front: { dir: [0, -1, 0], up: [0, 0, 1] },
  side: { dir: [1, 0, 0], up: [0, 0, 1] },
};
const NOT_EDITABLE = "Dieses Maß ist im Code keine Konstante – Änderungswunsch formulieren.";

export async function loadSTL(url) {
  const r = await fetch(url, { credentials: "same-origin" });
  if (!r.ok) throw new Error("STL konnte nicht geladen werden");
  const geo = new STLLoader().parse(await r.arrayBuffer());
  geo.computeVertexNormals();
  geo.computeBoundingBox();
  return geo;
}

function line(pts, mat) {
  const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(p => new THREE.Vector3(...p))), mat);
  if (mat.isLineDashedMaterial) ln.computeLineDistances();
  return ln;
}

function buildScene(geo, dims) {
  const scene = new THREE.Scene();
  const bb = geo.boundingBox;
  const size = new THREE.Vector3(); bb.getSize(size);
  const center = new THREE.Vector3(); bb.getCenter(center);
  const clip = new THREE.Plane(new THREE.Vector3(0, 0, -1), center.z);
  const front = new THREE.MeshStandardMaterial({ color: 0x9fb6cb, metalness: 0.12, roughness: 0.55, side: THREE.FrontSide, clippingPlanes: [] });
  const back = new THREE.MeshBasicMaterial({ color: 0xc2410c, side: THREE.BackSide, clippingPlanes: [] });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(geo, front));
  const backMesh = new THREE.Mesh(geo, back); group.add(backMesh);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 28), new THREE.LineBasicMaterial({ color: 0x17212b, transparent: true, opacity: 0.55, clippingPlanes: [] }));
  edges.visible = false; group.add(edges);
  scene.add(group);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
  const d1 = new THREE.DirectionalLight(0xffffff, 1.7); d1.position.set(1, -2, 3); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.6); d2.position.set(-2, 1, 1); scene.add(d2);
  const extXY = Math.max(size.x, size.y, 10);
  const step = extXY > 200 ? 20 : extXY > 60 ? 10 : 5;
  const n = Math.ceil(extXY * 1.6 / step) * 2;
  const grid = new THREE.GridHelper(n * step, n, 0xb8c2cc, 0xdde1e4);
  grid.rotation.x = Math.PI / 2; grid.position.set(Math.round(center.x / step) * step, Math.round(center.y / step) * step, bb.min.z - 0.01);
  grid.material.transparent = true; grid.material.opacity = 0.8;
  scene.add(grid);
  // Hauptmaße der Bounding-Box: Rückfall der Gruppe „aussen“ (nur ohne verankertes Außenmaß, Spec §3)
  const ext = Math.max(size.x, size.y, size.z);
  const main = new THREE.Group();
  const dimMat = new THREE.LineBasicMaterial({ color: 0x1f6fb2 });
  const off = ext * 0.08 + 2;
  const L = pts => line(pts, dimMat);
  const { min, max } = bb;
  const yD = min.y - off, xD = max.x + off;
  main.add(L([[min.x, min.y, min.z], [min.x, yD - 2, min.z]]), L([[max.x, min.y, min.z], [max.x, yD - 2, min.z]]), L([[min.x, yD, min.z], [max.x, yD, min.z]]));
  main.add(L([[max.x, min.y, min.z], [xD + 2, min.y, min.z]]), L([[max.x, max.y, min.z], [xD + 2, max.y, min.z]]), L([[xD, min.y, min.z], [xD, max.y, min.z]]));
  main.add(L([[max.x, min.y, max.z], [xD + 2, min.y, max.z]]), L([[xD, min.y, min.z], [xD, min.y, max.z]]));
  scene.add(main);
  const mainLabels = [
    { pos: new THREE.Vector3((min.x + max.x) / 2, yD, min.z), text: num(size.x, 2, false) },
    { pos: new THREE.Vector3(xD, (min.y + max.y) / 2, min.z), text: num(size.y, 2, false) },
    { pos: new THREE.Vector3(xD, min.y, (min.z + max.z) / 2), text: num(size.z, 2, false) },
  ];
  // Maße der KI mit Ankern; alte Versionen ohne a/b zeigen nur die Hauptmaße
  const c = [center.x, center.y, center.z];
  const items = [];
  for (const d of dims) {
    if (!hasAnchors(d)) continue;
    const g = dimGeometry(d.a, d.b, c, ext);
    if (!g) continue;
    const st = dimStyle(d);
    const mat = st.dashed
      ? new THREE.LineDashedMaterial({ color: st.color, dashSize: Math.max(ext * 0.02, 0.8), gapSize: Math.max(ext * 0.012, 0.5) })
      : new THREE.LineBasicMaterial({ color: st.color });
    const grp = new THREE.Group();
    for (const seg of [g.line, ...g.ext]) grp.add(line(seg, mat));
    scene.add(grp);
    items.push({ d, g, st, grp, mat, pos: new THREE.Vector3(...g.label) });
  }
  const mainFallback = !items.some(it => it.d.group === "aussen");
  return { scene, group, front, back, backMesh, edges, grid, main, mainLabels, items, mainFallback, clip, size, center, bb, ext };
}

function place(camera, controls, w, view, size, center) {
  const v = VIEWS[view] || VIEWS.iso;
  const r = Math.max(size.length() / 2, 1);
  const dist = r / Math.sin((camera.fov * Math.PI / 180) / 2) * 1.08;
  const dir = new THREE.Vector3(...v.dir).normalize();
  camera.up.set(...v.up);
  camera.position.copy(center).addScaledVector(dir, dist);
  camera.near = dist / 100; camera.far = dist * 20; camera.updateProjectionMatrix();
  if (controls) { controls.target.copy(center); controls.update(); } else camera.lookAt(center);
}

export async function createViewer(box, url, dims = [], hooks = {}) {
  const geo = await loadSTL(url);
  const S = buildScene(geo, Array.isArray(dims) ? dims : []);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.localClippingEnabled = true;
  box.prepend(renderer.domElement);
  renderer.domElement.setAttribute("aria-label", "3D-Modell. Ziehen dreht, Mausrad zoomt, rechte Maustaste verschiebt.");
  renderer.domElement.setAttribute("role", "img");
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.screenSpacePanning = true;
  controls.zoomToCursor = true;
  const state = { locked: false, lockedText: "", sel: { ...DEFAULT_SEL }, hl: null };
  const mkLabel = (cls, text) => { const e = document.createElement("span"); e.className = cls; e.textContent = text; box.append(e); return e; };
  const mainEls = S.mainLabels.map(l => mkLabel("dimlabel", l.text));
  const itemEls = S.items.map(it => {
    const e = mkLabel(`dimlabel ${it.d.editable ? "edit" : "info"}`, num(it.d.value, 1, false));
    e.dataset.dim = it.d.id;
    e.title = `${it.d.id} · ${it.d.label || ""}${it.d.editable ? "" : ` – ${NOT_EDITABLE}`}`;
    e.tabIndex = 0; e.setAttribute("role", "button");
    e.addEventListener("keydown", ev => { if (ev.key === "Enter" && ev.target === e) { ev.preventDefault(); startEdit(it, e); } });
    e.style.color = it.st.color; e.style.borderColor = it.st.color;
    if (it.st.dashed) e.style.borderStyle = "dashed";
    e.addEventListener("click", () => startEdit(it, e));
    return e;
  });
  let w = 1, hgt = 1, frame = 0, hlDone = null;

  function render() {
    renderer.render(S.scene, camera);
    const v = new THREE.Vector3();
    const put = (el, pos, show) => {
      v.copy(pos).project(camera);
      const on = show && v.z < 1;
      el.hidden = !on;
      if (on) { el.style.left = `${(v.x + 1) / 2 * w}px`; el.style.top = `${(1 - v.y) / 2 * hgt}px`; }
    };
    S.mainLabels.forEach((l, i) => put(mainEls[i], l.pos, S.main.visible));
    S.items.forEach((it, i) => put(itemEls[i], it.pos, it.grp.visible));
  }
  const req = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); }); };
  controls.addEventListener("change", req);
  function resize() {
    const r = box.getBoundingClientRect(); w = Math.max(1, r.width); hgt = Math.max(1, r.height);
    renderer.setSize(w, hgt, false); renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camera.aspect = w / hgt; camera.updateProjectionMatrix(); req();
  }
  function applyGroups() {
    const shown = new Set(visibleDims(S.items.map(it => it.d), state.sel).map(d => d.id));
    S.items.forEach(it => { it.grp.visible = shown.has(it.d.id) || state.hl === it.d.id; });
    S.main.visible = S.mainFallback && state.sel.aussen && !state.sel.nur_annahmen;
    req();
  }
  // Klick auf ein Label: Eingabefeld; Enter sendet nur dieses Maß, Esc bricht ab (Spec §3)
  function startEdit(it, el) {
    if (!it.d.editable) { toast(NOT_EDITABLE); return; }
    if (state.locked || !hooks.onSubmit) { toast(state.lockedText || "Gerade nicht änderbar."); return; }
    if (el.querySelector("input")) return;
    const inp = document.createElement("input");
    inp.inputMode = "decimal"; inp.value = de(it.d.value);
    inp.setAttribute("aria-label", `${it.d.id} ${it.d.label || ""}`.trim());
    el.replaceChildren(inp); inp.focus(); inp.select();
    const reset = () => el.replaceChildren(num(it.d.value, 1, false));
    inp.addEventListener("keydown", async e => {
      e.stopPropagation();
      if (e.key === "Escape") { reset(); return; }
      if (e.key !== "Enter") return;
      const r = parseDimInput(inp.value);
      if (r.error) { toast(r.error, "err"); return; }
      inp.disabled = true;
      const ok = await hooks.onSubmit([{ id: it.d.id, value: r.value }]);
      if (!ok && inp.isConnected) { inp.disabled = false; inp.focus(); }
    });
    inp.addEventListener("blur", () => { if (!inp.disabled) reset(); });
  }
  // Zeile der Tabelle angeklickt: Linie 1,5 s dicker (Zylinder, weil WebGL-Linien immer 1 px breit sind)
  function highlight(id) {
    const i = S.items.findIndex(x => x.d.id === id);
    if (i < 0) return;
    hlDone?.();
    const it = S.items[i], el = itemEls[i];
    const [p, q] = it.g.line.map(x => new THREE.Vector3(...x));
    const dir = q.clone().sub(p);
    const r = Math.max(S.ext * 0.006, 0.3);
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, dir.length(), 10), new THREE.MeshBasicMaterial({ color: it.st.color }));
    mesh.position.copy(p).add(q).multiplyScalar(0.5);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
    S.scene.add(mesh); el.classList.add("hl"); state.hl = id; applyGroups();
    const t = setTimeout(() => hlDone?.(), 1500);
    hlDone = () => {
      clearTimeout(t); S.scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose();
      el.classList.remove("hl"); state.hl = null; hlDone = null; applyGroups();
    };
  }
  const ro = new ResizeObserver(resize); ro.observe(box);
  resize();
  place(camera, controls, w, "iso", S.size, S.center);
  applyGroups();

  function setSection(on) {
    const planes = on ? [S.clip] : [];
    S.front.clippingPlanes = planes; S.back.clippingPlanes = planes; S.edges.material.clippingPlanes = planes;
    [S.front, S.back, S.edges.material].forEach(m => { m.needsUpdate = true; });
    req();
  }
  return {
    size: S.size,
    setView(v) { place(camera, controls, w, v, S.size, S.center); req(); },
    fit() { const dir = camera.position.clone().sub(controls.target).normalize(); const r = Math.max(S.size.length() / 2, 1);
      const dist = r / Math.sin((camera.fov * Math.PI / 180) / 2) * 1.08; controls.target.copy(S.center); camera.position.copy(S.center).addScaledVector(dir, dist); controls.update(); req(); },
    zoom(f) { const d = camera.position.clone().sub(controls.target); camera.position.copy(controls.target).addScaledVector(d, 1 / f); controls.update(); req(); },
    setGroups(sel) { state.sel = { ...DEFAULT_SEL, ...sel }; applyGroups(); },
    setLocked(on, text = "") { state.locked = !!on; state.lockedText = text; },
    highlight,
    setEdges(on) { S.edges.visible = on; req(); },
    setSection,
    snapshots(views = ["top", "front", "side"], W = 480, H = 360) {
      const r2 = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      r2.setSize(W, H, false); r2.localClippingEnabled = true;
      const cam = new THREE.PerspectiveCamera(20, W / H, 1, 1000);
      const vis = [S.main.visible, ...S.items.map(it => it.grp.visible)], edgesVis = S.edges.visible;
      S.main.visible = false; S.items.forEach(it => { it.grp.visible = false; }); S.edges.visible = true;
      const out = {};
      for (const v of views) { place(cam, null, W, v, S.size, S.center); r2.render(S.scene, cam); out[v] = r2.domElement.toDataURL("image/png"); }
      S.main.visible = vis[0]; S.items.forEach((it, i) => { it.grp.visible = vis[i + 1]; }); S.edges.visible = edgesVis;
      r2.dispose(); r2.forceContextLoss?.();
      return out;
    },
    dispose() {
      hlDone?.(); cancelAnimationFrame(frame); frame = -1;   // -1: keine neuen Bilder nach dem Abbau
      ro.disconnect(); controls.dispose(); renderer.dispose(); renderer.forceContextLoss?.(); geo.dispose();
      const gone = new Set();   // alle Geometrien und Materialien der Szene (Linien, Raster, Kanten), jedes einmal
      S.scene.traverse(o => { for (const x of [o.geometry, ...[o.material].flat()]) if (x?.dispose && !gone.has(x)) { gone.add(x); x.dispose(); } });
      renderer.domElement.remove(); mainEls.forEach(e => e.remove()); itemEls.forEach(e => e.remove());
    },
  };
}
