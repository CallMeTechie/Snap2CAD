// 3D-Ansicht: drehbar, zoombar, verschiebbar (three.js + OrbitControls)
import * as THREE from "../vendor/three/three.module.js";
import { OrbitControls } from "../vendor/three/OrbitControls.js";
import { STLLoader } from "../vendor/three/STLLoader.js";
import { num } from "./lib.js";

const VIEWS = {
  iso: { dir: [1, -1.25, 0.95], up: [0, 0, 1] },
  top: { dir: [0, 0, 1], up: [0, 1, 0] },
  front: { dir: [0, -1, 0], up: [0, 0, 1] },
  side: { dir: [1, 0, 0], up: [0, 0, 1] },
};

export async function loadSTL(url) {
  const r = await fetch(url, { credentials: "same-origin" });
  if (!r.ok) throw new Error("STL konnte nicht geladen werden");
  const geo = new STLLoader().parse(await r.arrayBuffer());
  geo.computeVertexNormals();
  geo.computeBoundingBox();
  return geo;
}

function buildScene(geo) {
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
  const ext = Math.max(size.x, size.y, 10);
  const step = ext > 200 ? 20 : ext > 60 ? 10 : 5;
  const n = Math.ceil(ext * 1.6 / step) * 2;
  const grid = new THREE.GridHelper(n * step, n, 0xb8c2cc, 0xdde1e4);
  grid.rotation.x = Math.PI / 2; grid.position.set(Math.round(center.x / step) * step, Math.round(center.y / step) * step, bb.min.z - 0.01);
  grid.material.transparent = true; grid.material.opacity = 0.8;
  scene.add(grid);
  // Masslinien
  const dims = new THREE.Group();
  const dimMat = new THREE.LineBasicMaterial({ color: 0x1f6fb2 });
  const off = Math.max(size.x, size.y, size.z) * 0.08 + 2;
  const line = pts => new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(p => new THREE.Vector3(...p))), dimMat);
  const { min, max } = bb;
  const yD = min.y - off, xD = max.x + off;
  dims.add(line([[min.x, min.y, min.z], [min.x, yD - 2, min.z]]), line([[max.x, min.y, min.z], [max.x, yD - 2, min.z]]), line([[min.x, yD, min.z], [max.x, yD, min.z]]));
  dims.add(line([[max.x, min.y, min.z], [xD + 2, min.y, min.z]]), line([[max.x, max.y, min.z], [xD + 2, max.y, min.z]]), line([[xD, min.y, min.z], [xD, max.y, min.z]]));
  dims.add(line([[max.x, min.y, min.z], [xD + 2, min.y - 0, min.z]]), line([[max.x, min.y, max.z], [xD + 2, min.y, max.z]]), line([[xD, min.y, min.z], [xD, min.y, max.z]]));
  scene.add(dims);
  const labels = [
    { pos: new THREE.Vector3((min.x + max.x) / 2, yD, min.z), text: num(size.x, 2, false) },
    { pos: new THREE.Vector3(xD, (min.y + max.y) / 2, min.z), text: num(size.y, 2, false) },
    { pos: new THREE.Vector3(xD, min.y, (min.z + max.z) / 2), text: num(size.z, 2, false) },
  ];
  return { scene, group, front, back, backMesh, edges, grid, dims, labels, clip, size, center, bb };
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

export async function createViewer(box, url) {
  const geo = await loadSTL(url);
  const S = buildScene(geo);
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
  const labelEls = S.labels.map(l => { const e = document.createElement("span"); e.className = "dimlabel"; e.textContent = l.text; box.append(e); return e; });
  const state = { dims: true, edges: false, section: false };
  let w = 1, hgt = 1, frame = 0;

  function render() {
    renderer.render(S.scene, camera);
    const v = new THREE.Vector3();
    S.labels.forEach((l, i) => {
      v.copy(l.pos).project(camera);
      const show = state.dims && v.z < 1;
      labelEls[i].hidden = !show;
      if (show) { labelEls[i].style.left = `${(v.x + 1) / 2 * w}px`; labelEls[i].style.top = `${(1 - v.y) / 2 * hgt}px`; }
    });
  }
  const req = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); }); };
  controls.addEventListener("change", req);
  function resize() {
    const r = box.getBoundingClientRect(); w = Math.max(1, r.width); hgt = Math.max(1, r.height);
    renderer.setSize(w, hgt, false); renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camera.aspect = w / hgt; camera.updateProjectionMatrix(); req();
  }
  const ro = new ResizeObserver(resize); ro.observe(box);
  resize();
  place(camera, controls, w, "iso", S.size, S.center);
  req();

  function setSection(on) {
    state.section = on;
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
    setDims(on) { state.dims = on; S.dims.visible = on; req(); },
    setEdges(on) { state.edges = on; S.edges.visible = on; req(); },
    setSection,
    snapshots(views = ["top", "front", "side"], W = 480, H = 360) {
      const r2 = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      r2.setSize(W, H, false); r2.localClippingEnabled = true;
      const cam = new THREE.PerspectiveCamera(20, W / H, 1, 1000);
      const dimsVis = S.dims.visible, edgesVis = S.edges.visible;
      S.dims.visible = false; S.edges.visible = true;
      const out = {};
      for (const v of views) { place(cam, null, W, v, S.size, S.center); r2.render(S.scene, cam); out[v] = r2.domElement.toDataURL("image/png"); }
      S.dims.visible = dimsVis; S.edges.visible = edgesVis;
      r2.dispose(); r2.forceContextLoss?.();
      return out;
    },
    dispose() { ro.disconnect(); controls.dispose(); renderer.dispose(); renderer.forceContextLoss?.(); geo.dispose(); renderer.domElement.remove(); labelEls.forEach(e => e.remove()); },
  };
}
