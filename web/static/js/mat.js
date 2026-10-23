// Messunterlage erzeugen: Generator als Baustein der Anleitung (/anleitung#unterlage)
import { api, h, clear, icon, debounce, fail } from "./lib.js";
import { onLeave } from "./app.js";
import { PRINT, layoutFacts } from "./formats.js";

// Optionen, Vorschau, PDF-Knopf und „Nach dem Drucken“ in container; räumt beim Seitenwechsel per onLeave auf
export function matGenerator(container) {
  let fmt = "A4";
  try { const v = localStorage.getItem("mu.fmt"); if (Object.hasOwn(PRINT, v)) fmt = v; } catch { /* */ }
  let pages = {};
  const pagesBox = h("div");
  const hdr = h("input", { id: "hdr", class: "input", placeholder: "z. B. Werkstatt oder Firmenname", maxlength: 60 });

  const choice = f => h("label", { class: "choice" },
    h("span", { class: "c1" }, h("input", { type: "radio", name: "fmt", value: f, checked: f === fmt, onchange: () => { fmt = f; try { localStorage.setItem("mu.fmt", f); } catch { /* */ } drawPages(); update(); } }), PRINT[f].title),
    h("span", { class: "c2" }, PRINT[f].field));

  function drawPages() {
    pages = Object.fromEntries(PRINT[fmt].pages.map(([k]) => [k, true]));
    clear(pagesBox, PRINT[fmt].pages.map(([k, t]) =>
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: true, onchange: e => { pages[k] = e.target.checked; update(); } }), t)));
  }

  const pdfBtn = h("a", { class: "btn primary big", download: "" }, icon("download"), "PDF erzeugen und herunterladen");
  const previewHead = h("h2", { id: "prev-h" });
  const figs = [0, 1, 2].map(i => {
    const img = h("img", { alt: "", loading: "lazy", width: 210, height: 297 });
    const name = h("span");
    return { img, name, fig: h("figure", {}, img, h("figcaption", { class: "small", style: { color: "var(--text2)" } }, h("strong", {}, i + 1), name)) };
  });
  const facts = h("dl", { class: "facts" });
  const printTail = h("span");
  const sub = t => h("span", { class: "small muted" }, t);
  const writeHint = sub(""), photoHint = sub("");

  container.append(
    h("div", { class: "row" },
      h("section", { class: "card", style: { flex: "1 1 380px", maxWidth: "460px", gap: "22px" }, "aria-labelledby": "opt-h" },
        h("h2", { id: "opt-h" }, "Optionen"),
        h("fieldset", {}, h("legend", {}, "Format"), h("div", { class: "grid1" }, choice("A4"), choice("A3"), choice("K60"))),
        h("fieldset", {}, h("legend", {}, "Seiten im PDF"), pagesBox),
        h("div", { class: "field" }, h("label", { for: "hdr", class: "label" }, "Kopfzeile (optional)"), hdr,
          h("span", { class: "hint" }, "Erscheint oben rechts auf jeder Seite. Messfeld und Marker bleiben unverändert.")),
        h("div", { class: "note warn", role: "note" }, icon("printer", 20),
          h("div", {}, h("strong", {}, "Mit 100 % / Tatsächlicher Größe drucken."), printTail)),
        h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, pdfBtn)),
      h("section", { class: "card", style: { flex: "999 1 560px" }, "aria-labelledby": "prev-h" },
        h("div", { class: "card-head" }, previewHead, h("span", { class: "small muted" }, "Wird bei jeder Änderung neu erzeugt")),
        h("div", { class: "previews" }, figs.map(f => f.fig)),
        facts)),
    h("section", { class: "card tight", "aria-labelledby": "next-h" },
      h("h2", { id: "next-h", style: { fontSize: "15px" } }, "Nach dem Drucken"),
      h("ol", { class: "nextsteps" },
        step("01", "Kontrollmaß messen", writeHint),
        step("02", "Plan fixieren", sub("Ecken festkleben, Teil mittig auflegen")),
        step("03", "Fotografieren", photoHint),
        h("li", {}, h("span", { class: "num" }, "04"), h("span", {}, h("strong", {}, "Hochladen"), h("br"), h("a", { href: "/fotos", class: "small" }, "Weiter zu „Fotos prüfen“"))))));

  const ctrl = { abort: null };
  async function update() {
    const keys = PRINT[fmt].pages.map(([k]) => k);
    const sel = keys.filter(k => pages[k]);
    const header = hdr.value.trim();
    pdfBtn.href = `/api/mat.pdf?format=${encodeURIComponent(fmt)}&pages=${sel.join(",")}&header=${encodeURIComponent(header)}`;
    pdfBtn.setAttribute("download", `Messunterlage_${fmt}.pdf`);
    pdfBtn.toggleAttribute("aria-disabled", !sel.length);
    printTail.textContent = ` Nicht „An Seite anpassen“. Danach das ${PRINT[fmt].ctrl}-mm-Kontrollmaß mit dem Lineal prüfen.`;
    writeHint.textContent = fmt === "K60" ? "Wert ins Feld unter dem Messfeld schreiben" : "Wert ins Feld unten rechts schreiben";
    photoHint.textContent = PRINT[fmt].photo;
    previewHead.textContent = `Vorschau · ${PRINT[fmt].title} · ${sel.length} ${sel.length === 1 ? "Seite" : "Seiten"}`;
    keys.forEach((k, i) => {
      const f = figs[i], name = PRINT[fmt].pages[i][1];
      f.fig.hidden = !pages[k];
      f.name.textContent = ` · ${name}`;
      const src = `/api/mat/preview.png?format=${encodeURIComponent(fmt)}&page=${i}&header=${encodeURIComponent(header)}`;
      if (f.img.getAttribute("src") !== src) {
        f.img.classList.add("loading");
        f.img.onload = () => f.img.classList.remove("loading");
        f.img.src = src;
        f.img.alt = `Seite ${i + 1}: ${name} (${PRINT[fmt].title})`;
      }
    });
    clear(facts);
    try {
      ctrl.abort?.abort(); ctrl.abort = new AbortController();
      const sp = await api(`/api/mat/layout?format=${encodeURIComponent(fmt)}`, { signal: ctrl.abort.signal });
      clear(facts, layoutFacts(fmt, sp).map(([k, v]) => fact(k, v)));
    } catch (e) { fail(e); }
  }
  const later = debounce(update, 450);
  drawPages();
  hdr.addEventListener("input", later);
  onLeave(() => ctrl.abort?.abort());
  update();
}

function step(n, t, s) {
  return h("li", {}, h("span", { class: "num" }, n), h("span", {}, h("strong", {}, t), h("br"), s));
}
function fact(k, v) { return h("div", {}, h("dt", {}, k), h("dd", {}, v)); }
