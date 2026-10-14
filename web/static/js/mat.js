// Schritt 1: Messunterlage erzeugen
import { api, h, clear, icon, num, debounce, fail } from "./lib.js";
import { onLeave } from "./app.js";

const PAGE_NAMES = { mat: "Messunterlage", gauge: "Höhenlehre zum Aufstellen", guide: "Anleitung" };
const CAPTIONS = ["Messunterlage", "Höhenlehre", "Anleitung"];

export default async function (main) {
  let fmt = "A4";
  try { fmt = localStorage.getItem("mu.fmt") || "A4"; } catch { /* */ }
  const pages = { mat: true, gauge: true, guide: true };
  const hdr = h("input", { id: "hdr", class: "input", placeholder: "z. B. Werkstatt oder Firmenname", maxlength: 60 });

  const choice = f => h("label", { class: "choice" },
    h("span", { class: "c1" }, h("input", { type: "radio", name: "fmt", value: f, checked: f === fmt, onchange: () => { fmt = f; try { localStorage.setItem("mu.fmt", f); } catch { /* */ } update(); } }), f),
    h("span", { class: "c2" }, f === "A4" ? "Feld 190 × 230 mm" : "Feld 270 × 360 mm"));

  const pdfBtn = h("a", { class: "btn primary big", download: "" }, icon("download"), "PDF erzeugen und herunterladen");
  const previewHead = h("h2", { id: "prev-h" });
  const figs = [0, 1, 2].map(i => {
    const img = h("img", { alt: "", loading: "lazy", width: 210, height: 297 });
    return { img, fig: h("figure", {}, img, h("figcaption", { class: "small", style: { color: "var(--text2)" } }, h("strong", {}, i + 1), ` · ${CAPTIONS[i]}`)) };
  });
  const facts = h("dl", { class: "facts" });

  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Messunterlage erzeugen"),
      h("p", { class: "lead" }, "Druckfertiges PDF mit 1-mm-Raster und acht ArUco-Markern. Ein Ausdruck reicht für beliebig viele Messungen."))),
    h("div", { class: "row" },
      h("section", { class: "card", style: { flex: "1 1 380px", maxWidth: "460px", gap: "22px" }, "aria-labelledby": "opt-h" },
        h("h2", { id: "opt-h" }, "Optionen"),
        h("fieldset", {}, h("legend", {}, "Format"), h("div", { class: "grid2" }, choice("A4"), choice("A3"))),
        h("fieldset", {}, h("legend", {}, "Seiten im PDF"), Object.entries(PAGE_NAMES).map(([k, t]) =>
          h("label", { class: "check" }, h("input", { type: "checkbox", checked: true, onchange: e => { pages[k] = e.target.checked; update(); } }), t))),
        h("div", { class: "field" }, h("label", { for: "hdr", class: "label" }, "Kopfzeile (optional)"), hdr,
          h("span", { class: "hint" }, "Erscheint oben rechts auf jeder Seite. Raster und Marker bleiben unverändert.")),
        h("div", { class: "note warn", role: "note" }, icon("printer", 20),
          h("div", {}, h("strong", {}, "Mit 100 % / Tatsächlicher Größe drucken."), " Nicht „An Seite anpassen“. Danach das 100-mm-Kontrollmaß mit dem Lineal prüfen.")),
        h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, pdfBtn)),
      h("section", { class: "card", style: { flex: "999 1 560px" }, "aria-labelledby": "prev-h" },
        h("div", { class: "card-head" }, previewHead, h("span", { class: "small muted" }, "Wird bei jeder Änderung neu erzeugt")),
        h("div", { class: "previews" }, figs.map(f => f.fig)),
        facts)),
    h("section", { class: "card tight", "aria-labelledby": "next-h" },
      h("h2", { id: "next-h", style: { fontSize: "15px" } }, "Nach dem Drucken"),
      h("ol", { class: "nextsteps" },
        step("01", "Kontrollmaß messen", "Wert ins Feld unten rechts schreiben"),
        step("02", "Plan fixieren", "Ecken festkleben, Teil mittig auflegen"),
        step("03", "Fotografieren", "Senkrecht, 50–70 cm, 2×-Zoom"),
        h("li", {}, h("span", { class: "num" }, "04"), h("span", {}, h("strong", {}, "Hochladen"), h("br"), h("a", { href: "/fotos", class: "small" }, "Weiter zu „Fotos prüfen“"))))));

  const ctrl = { abort: null };
  async function update() {
    const sel = Object.keys(pages).filter(k => pages[k]);
    const header = hdr.value.trim();
    pdfBtn.href = `/api/mat.pdf?format=${fmt}&pages=${sel.join(",")}&header=${encodeURIComponent(header)}`;
    pdfBtn.setAttribute("download", `Messunterlage_${fmt}.pdf`);
    pdfBtn.toggleAttribute("aria-disabled", !sel.length);
    previewHead.textContent = `Vorschau · ${fmt} · ${sel.length} ${sel.length === 1 ? "Seite" : "Seiten"}`;
    ["mat", "gauge", "guide"].forEach((k, i) => {
      const f = figs[i];
      f.fig.hidden = !pages[k];
      const src = `/api/mat/preview.png?format=${fmt}&page=${i}&header=${encodeURIComponent(header)}`;
      if (f.img.getAttribute("src") !== src) {
        f.img.classList.add("loading");
        f.img.onload = () => f.img.classList.remove("loading");
        f.img.src = src;
        f.img.alt = `Seite ${i + 1}: ${CAPTIONS[i]} (${fmt})`;
      }
    });
    try {
      ctrl.abort?.abort(); ctrl.abort = new AbortController();
      const sp = await api(`/api/mat/layout?format=${fmt}`, { signal: ctrl.abort.signal });
      const g = sp.height_gauge || {};
      clear(facts,
        fact("Raster", `${num(sp.grid_mm[0], 0)} × ${num(sp.grid_mm[1], 0)} mm`),
        fact("Marker", `8 × ${num(sp.marker_size_mm, 0)} mm`),
        fact("Wörterbuch", "4X4_50 · ID 0–7"),
        fact("Höhenlehre", `0–${num(g.vlen_mm, 0)} mm`));
    } catch (e) { fail(e); }
  }
  const later = debounce(update, 450);
  hdr.addEventListener("input", later);
  onLeave(() => ctrl.abort?.abort());
  update();
}

function step(n, t, s) {
  return h("li", {}, h("span", { class: "num" }, n), h("span", {}, h("strong", {}, t), h("br"), h("span", { class: "small muted" }, s)));
}
function fact(k, v) { return h("div", {}, h("dt", {}, k), h("dd", {}, v)); }
