// Reine 2D-Geometrie fuer Messen und Kanten-Werkzeug, ohne DOM (geprueft mit node --test tests/js/*.test.mjs)

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
