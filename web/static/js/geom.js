// Reine Geometrie fuer Messen, Kanten-Werkzeug und Bemaßung am Modell, ohne DOM (geprueft mit node --test tests/js/*.test.mjs)

export const r3 = v => Math.round(v * 1000) / 1000;

export function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
  let t = l ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l : 0; t = Math.max(0, Math.min(1, t));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
export function inPoly(p, P) {
  let c = false;
  for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
    const [xi, yi] = P[i], [xj, yj] = P[j];
    if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c;
  }
  return c;
}
export function polyArea(P) { let a = 0; for (let i = 0; i < P.length; i++) { const q = P[i], r = P[(i + 1) % P.length]; a += q[0] * r[1] - r[0] * q[1]; } return Math.abs(a) / 2; }

// Naechste Kante eines geschlossenen Polygons (Kante i -> i+1, die letzte n-1 -> 0) in Reichweite tol:
// { i, p: Fusspunkt, d: Abstand, t: Anteil auf der Kante 0..1 } oder null. Liegt der naechste Punkt auf einem
// Eckpunkt (Fusspunkt am Kantenende), zaehlt das als Eckpunkt, nicht als Kante: null
export function nearestOnPolygonEdge(pt, poly, tol) {
  const n = poly?.length || 0;
  if (n < 2) return null;
  let best = null;
  for (let i = 0; i < n; i++) {
    const a = poly[i], b = poly[(i + 1) % n], dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / l)) : 0;
    const p = [a[0] + t * dx, a[1] + t * dy], d = Math.hypot(pt[0] - p[0], pt[1] - p[1]);
    const end = t <= 1e-9 || t >= 1 - 1e-9;
    // bei gleichem Abstand gewinnt ein Fusspunkt innerhalb einer Kante
    if (!best || d < best.d - 1e-12 || (Math.abs(d - best.d) <= 1e-12 && best.end && !end)) best = { i, p, d, t, end };
  }
  if (best.end || best.d > tol) return null;
  return { i: best.i, p: best.p, d: best.d, t: best.t };
}
// Neues Polygon mit Punkt p nach Index i (zwischen i und i+1); Punkte werden kopiert
export function insertVertex(poly, i, p) {
  const out = poly.map(q => [...q]);
  out.splice(i + 1, 0, [...p]);
  return out;
}

// Innere Kandidatenkanten, die auf keiner Teilekante liegen (beide Enden naeher als tol mm)
export function unassignedSegments(segments, polygons, tol = 1.5) {
  return segments.filter(s => s.kind === "inner" && !polygons.some(P => P.some((a, i) => {
    const b = P[(i + 1) % P.length];
    return segDist(s.a, a, b) < tol && segDist(s.b, a, b) < tol;
  })));
}

// Polygon unter dem Zeiger: eine Kante in Reichweite schlaegt jede Flaeche (die naechste Kante gewinnt),
// sonst gewinnt das kleinste umschliessende Polygon (Platte auf dem Grundkoerper). Rueckgabe: Index oder -1
export function pickPolygon(p, polygons, reach = 8) {
  let best = -1, bk = Infinity;
  polygons.forEach((P, i) => {
    const edge = Math.min(...P.map((q, j) => segDist(p, q, P[(j + 1) % P.length])));
    if (edge > reach && !inPoly(p, P)) return;
    const k = edge <= reach ? edge - reach - 1 : polyArea(P);  // Kante: immer < 0, Flaeche: >= 0
    if (k < bk) { bk = k; best = i; }
  });
  return best;
}

// ------------------------------------------------------------------ Bemaßung am Modell (Spec Stufe B §3/§5, B5)

export const DIM_GROUP_KEYS = ["aussen", "bohrung", "tiefe", "fase", "platte", "sonst"];
// Spalte „Gruppe“ der Masstabelle (cad.js) und Liste der Messseite (measure.js), gleich jobs.GROUP_TEXT
export const DIM_GROUP_TEXT = Object.freeze({ aussen: "außen", bohrung: "Bohrung", tiefe: "Tiefe", fase: "Fase", platte: "Platte",
  sonst: "sonstige" });
// Schalter über dem Viewer (cad.js), gleiche Schlüssel wie DIM_GROUP_KEYS
export const DIM_GROUP_LABEL = Object.freeze({ aussen: "Außenmaße", bohrung: "Bohrungen", tiefe: "Tiefen", fase: "Fasen",
  platte: "Platten", sonst: "Sonstige" });
// Text der Gruppe für Tabelle und Liste; nur eigene Schlüssel (kein „constructor“ o. Ä. aus dem Prototyp)
export const groupText = (g, fallback = "–") => (typeof g === "string" && Object.hasOwn(DIM_GROUP_TEXT, g) ? DIM_GROUP_TEXT[g] : fallback);
export const DEFAULT_SEL = Object.freeze({ aussen: true, bohrung: false, tiefe: false, fase: false, platte: false, sonst: false,
  annahmen: true, nur_annahmen: false });

// Gespeicherte Auswahl (localStorage „dims.groups“): nur bekannte Schluessel mit echtem Wahrheitswert
export function dimSel(raw) {
  let o = null;
  try { o = JSON.parse(raw); } catch { /* kein JSON: Standard */ }
  const out = { ...DEFAULT_SEL };
  if (o && typeof o === "object" && !Array.isArray(o)) for (const k of Object.keys(DEFAULT_SEL)) if (typeof o[k] === "boolean") out[k] = o[k];
  return out;
}

const groupOf = d => (DIM_GROUP_KEYS.includes(d.group) ? d.group : "sonst");
// sichtbar: Gruppe an oder (Annahme bzw. vom Nutzer gesetzt und „Annahmen & nachgemessen“ an);
// „Nur Annahmen“: nur Annahmen und vom Nutzer gesetzte Maße, gleich welche Gruppe
const flagged = d => d.assumed === true || d.user_set === true;
export function visibleDims(dims, sel) {
  if (sel.nur_annahmen) return dims.filter(flagged);
  return dims.filter(d => sel[groupOf(d)] === true || (flagged(d) && sel.annahmen === true));
}

const fin3 = p => Array.isArray(p) && p.length === 3 && p.every(v => typeof v === "number" && Number.isFinite(v));
export function hasAnchors(d) { return !!d && fin3(d.a) && fin3(d.b); }

const vsub = (a, b) => a.map((v, i) => v - b[i]);
const vadd = (a, b) => a.map((v, i) => v + b[i]);
const vmul = (a, k) => a.map(v => v * k);
const vdot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const vlen = a => Math.hypot(a[0], a[1], a[2]);
const vperp = (v, u) => vsub(v, vmul(u, vdot(v, u)));

// Masslinie a->b, versetzt senkrecht zur Linie und weg von der Modellmitte (8 % der Modellgroesse, mindestens 2 mm);
// liegt die Mitte auf der Linie (bis auf Rundungsrauschen der Anker, 1e-3 der Modellgroesse), zeigt der Versatz
// nach +Z, bei senkrechter Linie nach +X
export function dimGeometry(a, b, center, size) {
  const ab = vsub(b, a), n = vlen(ab);
  if (!(n > 1e-9)) return null;
  const u = vmul(ab, 1 / n), m = vmul(vadd(a, b), 0.5);
  const off = Math.max(0.08 * size, 2), over = off * 0.25;
  let w = vperp(vsub(m, center), u);
  if (vlen(w) < 1e-3 * Math.max(1, size)) {
    for (const ax of [[0, 0, 1], [1, 0, 0], [0, 1, 0]]) { w = vperp(ax, u); if (vlen(w) > 0.1) break; }
  }
  w = vmul(w, 1 / vlen(w));
  const o = vmul(w, off), oo = vmul(w, off + over);
  return { line: [vadd(a, o), vadd(b, o)], ext: [[a, vadd(a, oo)], [b, vadd(b, oo)]], label: vadd(m, o), off };
}

export const DIM_COLORS = Object.freeze({ assumed: "#b42318", user: "#1a7f37", base: "#1f6fb2", stale: "#8a939b" });
export function dimStyle(d) {
  if (d.anchors_stale) return { color: DIM_COLORS.stale, dashed: true };
  if (d.assumed) return { color: DIM_COLORS.assumed, dashed: false };
  if (d.user_set) return { color: DIM_COLORS.user, dashed: false };
  return { color: DIM_COLORS.base, dashed: !!d.derived_from };
}
export function dimState(d) {
  if (d.assumed) return "Annahme";
  if (d.user_set) return "nachgemessen";
  return d.derived_from ? `abgeleitet von ${d.derived_from}` : "";
}

// Wert für Eingabefelder und Texte: Dezimalkomma, höchstens drei Stellen, ohne Tausenderpunkt (Gegenstück zu parseDimInput)
export const de = v => String(r3(v)).replace(".", ",");

// Eingabe im Label oder in der Tabelle: Ziffern mit Komma oder Punkt, 0 < Wert <= 5000 mm, auf 3 Stellen gerundet
export function parseDimInput(s) {
  const t = String(s ?? "").trim();
  if (!t) return { error: "Bitte einen Wert eingeben." };
  if (!/^\d+(?:[.,]\d+)?$/.test(t)) return { error: "Kein gültiger Wert – z. B. 45 oder 45,5." };
  const v = r3(Number(t.replace(",", ".")));
  if (!(v > 0 && v <= 5000)) return { error: "Der Wert muss größer als 0 und höchstens 5000 mm sein." };
  return { value: v };
}

const BANNER_TAIL = " – Schlüsse auf abhängige Maße ziehen?";
// Hinweis nach einem Neuaufbau: Mass war Annahme oder neuer Wert weicht mehr als 10 % vom alten ab
export function paramBanner(list) {
  const parts = list.filter(p => p.old_assumed || (p.old > 0 && Math.abs(p.value - p.old) > 0.1 * p.old))
    .map(p => (p.old_assumed ? `${de(p.value)} mm ersetzt eine Annahme (${de(p.old)} mm)` : `${de(p.value)} mm statt ${de(p.old)} mm (${p.label})`));
  return parts.length ? parts.join("; ") + BANNER_TAIL : "";
}

// Obergrenze des Änderungswunsches (main.py IterIn.text max_length)
export const ITER_MAX = 4000;
const CONCL_HEAD = "Nachgemessen mit dem Messschieber: ";
const CONCL_TAIL = ". Leite daraus abhängige Maße ab (Tiefen, Dicken, Abstände, die an diesen Maßen hängen), trage bei jedem "
  + "geänderten Maß derived_from und eine kurze Begründung ein und ändere sonst nichts.";
// Text des Aenderungswunsches fuer „Schluesse ziehen“ (Spec §5); zu lang fuer max: die ersten Maße und „n weitere“
// (die KI kennt sie aus den Zeilen „Parametrisch geändert“ im Verlauf)
export function conclusionText(list, max = ITER_MAX) {
  if (!list.length) return "";
  const items = list.map(p => `${p.id} ${p.label} = ${de(p.value)} mm`
    + (p.old == null ? "" : ` (vorher ${p.old_assumed ? "Annahme " : ""}${de(p.old)})`));
  const text = n => CONCL_HEAD + items.slice(0, n).join("; ")
    + (n < items.length ? `; und ${items.length - n} weitere (siehe „Parametrisch geändert“ im Verlauf)` : "") + CONCL_TAIL;
  let n = items.length;
  while (n > 1 && text(n).length > max) n--;
  return text(n).slice(0, max);
}
