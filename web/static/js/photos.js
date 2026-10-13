// Schritt 2: Fotos pruefen
import { api, upload, h, clear, icon, num, parseNum, toast, fail, dialog, confirmDlg } from "./lib.js";
import { S, ensureProject, reloadProject, projectPicker, go, onLeave } from "./app.js";

export const VIEW_LABEL = { top: "Draufsicht", tilted: "Gekippt (Höhe)", gauge: "Höhenlehre", overview: "Übersicht" };
export const STATUS = {
  gut: ["gut", "ok"], brauchbar: ["brauchbar", "warn"], unsicher: ["unsicher – wiederholen", "err"],
  nicht_auswertbar: ["nicht auswertbar", "err"],
};

export function photoStatusLine(p) {
  const a = p.analysis || {};
  const n = (a.mat_ids || []).length;
  const [t, k] = STATUS[p.status] || [p.status, "off"];
  const parts = [`${n}/8 Marker`];
  if (p.max_err != null) parts.push(`${num(p.max_err, 2)} mm`);
  parts.push(t);
  return h("span", { class: "st" }, h("span", { class: `dot ${k === "ok" ? "" : k}` }), parts.join(" · "));
}

export function tipsDialog() {
  const li = (t, s) => h("li", {}, h("strong", {}, t), " – ", s);
  return dialog({ title: "Fototipps", body: h("ul", { class: "ul" },
    li("Senkrecht von oben", "Handy parallel zur Unterlage, Objekt in der Bildmitte."),
    li("Abstand 50–70 cm, 2×-Zoom", "weniger perspektivische Verzerrung als nah mit Weitwinkel."),
    li("Alle 8 Marker sichtbar", "mindestens 4 sind nötig, mehr erhöhen die Genauigkeit."),
    li("Kein Blitz, kein Schlagschatten", "diffuses Licht, Marker dürfen nicht spiegeln."),
    li("Unterlage flach", "Ecken festkleben, keine Wellen im Papier."),
    li("Höhen", "Höhenlehre direkt neben das Objekt stellen – alle drei Marker im Bild, Kamera auf Höhe der Objektmitte.")),
  actions: [{ label: "Verstanden", primary: true, value: true }] });
}

export default async function (main) {
  await ensureProject();
  let selected = null, mode = "both";
  let fmt = "";
  const fmtSel = h("select", { class: "input", style: { minWidth: "200px" }, "aria-label": "Unterlage" },
    h("option", { value: "" }, "Automatisch erkennen"), h("option", { value: "A4" }, "A4"), h("option", { value: "A3" }, "A3"));
  fmtSel.addEventListener("change", async () => {
    fmt = fmtSel.value;
    const p = cur();
    if (p && fmt && p.format !== fmt) {
      try { await api(`/api/photos/${p.id}`, { method: "PATCH", body: { format: fmt } }); await reloadProject(); draw(); }
      catch (e) { fail(e); }
    }
  });
  const fileIn = h("input", { type: "file", accept: "image/*,.heic,.heif", multiple: true, hidden: true });
  const camIn = h("input", { type: "file", accept: "image/*", capture: "environment", hidden: true });
  const drop = h("div", { class: "drop" }, icon("upload", 26),
    h("strong", {}, "Fotos hierher ziehen"),
    h("div", { class: "chips", style: { justifyContent: "center" } },
      h("button", { class: "btn primary", type: "button", onclick: () => fileIn.click() }, "Dateien auswählen"),
      h("button", { class: "btn", type: "button", onclick: () => camIn.click() }, icon("camera"), "Foto aufnehmen")),
    h("span", { class: "hint" }, `JPG, PNG, HEIC · Originalauflösung · bis ${S.status?.max_upload_mb || 25} MB`), fileIn, camIn);
  const list = h("ul", { class: "plist" });
  const detail = h("section", { class: "card", "aria-labelledby": "det-h" });
  const pending = [];

  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "Fotos prüfen"),
      h("p", { class: "lead" }, "Marker werden erkannt, das Foto wird auf die Tischebene entzerrt. Nur Fotos mit grünem oder gelbem Status gehen in die Messung.")),
    h("div", { class: "chips", style: { alignItems: "flex-end" } }, projectPicker(() => { selected = null; draw(); }),
      h("label", { class: "field", style: { gap: "4px" } }, h("span", { class: "label" }, "Unterlage"), fmtSel))),
    h("div", { class: "photos-layout" },
      h("aside", { "aria-label": "Hochgeladene Fotos", style: { display: "flex", flexDirection: "column", gap: "12px" } }, drop, list,
        h("button", { class: "btn ghost sm", style: { alignSelf: "flex-start" }, onclick: tipsDialog }, icon("info", 16), "Fototipps")),
      detail));

  ["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => send([...e.dataTransfer.files]));
  fileIn.addEventListener("change", () => { send([...fileIn.files]); fileIn.value = ""; });
  camIn.addEventListener("change", () => { send([...camIn.files]); camIn.value = ""; });
  // Einfuegen aus der Zwischenablage
  const onPaste = e => { const f = [...(e.clipboardData?.files || [])].filter(x => x.type.startsWith("image/")); if (f.length) send(f); };
  document.addEventListener("paste", onPaste);
  onLeave(() => document.removeEventListener("paste", onPaste));

  const cur = () => S.project.photos.find(p => p.id === selected);

  async function send(files) {
    files = files.filter(f => f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name));
    const max = (S.status?.max_upload_mb || 25) * 1048576;
    for (const f of files) {
      if (f.size > max) { toast(`${f.name}: zu groß`, "err"); continue; }
      const item = { name: f.name, progress: 0 };
      pending.push(item); drawList();
      const form = new FormData();
      form.append("file", f); form.append("view", S.project.photos.length ? "top" : "top"); form.append("format", fmt);
      try {
        const ph = await upload(`/api/projects/${S.project.id}/photos`, form, p => { item.progress = p; drawList(); });
        selected = ph.id;
        await reloadProject();
        if (ph.status === "nicht_auswertbar") toast(`${f.name}: zu wenige Marker erkannt`, "err");
      } catch (e) { fail(e); }
      pending.splice(pending.indexOf(item), 1);
      draw();
    }
  }

  function drawList() {
    const ps = S.project.photos;
    clear(list, ps.map(p => {
      const bad = p.status === "nicht_auswertbar";
      const sel = h("select", { "aria-label": `Ansicht für ${p.filename}`, onclick: e => e.stopPropagation(), onchange: async e => {
        try { await api(`/api/photos/${p.id}`, { method: "PATCH", body: { view: e.target.value } }); await reloadProject(); draw(); } catch (er) { fail(er); }
      } }, Object.entries(VIEW_LABEL).map(([k, v]) => h("option", { value: k, selected: p.view === k }, v)));
      const missing = (p.analysis?.missing_ids || []);
      return h("li", { class: "pitem", "aria-current": String(p.id === selected), tabindex: 0,
        onclick: () => { selected = p.id; draw(); }, onkeydown: e => { if (e.key === "Enter") { selected = p.id; draw(); } } },
        p.files.includes("thumb") ? h("img", { src: `/api/photos/${p.id}/thumb.jpg`, alt: "" }) : h("div", { class: "ph" }, icon("image")),
        h("div", { style: { display: "flex", flexDirection: "column", gap: "4px", minWidth: 0 } },
          h("span", { class: "nm", title: p.filename }, p.filename), bad ? null : sel, photoStatusLine(p),
          p.gauge ? h("span", { class: "xs muted" }, `Höhenlehre ${p.gauge.strip} · ${p.gauge.ids.length}/3 Marker`) : null,
          bad ? h("span", { class: "xs", style: { color: "var(--err)" } }, `Mindestens 4 Marker nötig. ${missing.length ? `Marker ID ${missing.join(", ")} verdeckt oder unscharf.` : ""}`) : null,
          bad ? h("div", { class: "acts" }, h("button", { class: "btn sm", onclick: e => { e.stopPropagation(); tipsDialog(); } }, "Fototipps"),
            h("button", { class: "btn sm danger", onclick: e => { e.stopPropagation(); del(p); } }, "Entfernen")) : null));
    }), pending.map(it => h("li", { class: "pitem", "aria-busy": "true" }, h("div", { class: "ph" }, h("span", { class: "spin" })),
      h("div", {}, h("span", { class: "nm" }, it.name), h("br"),
        h("span", { class: "small muted" }, it.progress < 1 ? `Hochladen … ${Math.round(it.progress * 100)} %` : "Marker werden erkannt …")))));
  }

  async function del(p) {
    if (!await confirmDlg("Foto entfernen?", `${p.filename} und alle Maße darauf werden aus dem Projekt entfernt.`, "Entfernen", true)) return;
    try { await api(`/api/photos/${p.id}`, { method: "DELETE" }); if (selected === p.id) selected = null; await reloadProject(); draw(); } catch (e) { fail(e); }
  }

  function draw() {
    if (!S.project.photos.some(p => p.id === selected)) selected = (S.project.photos.find(p => p.status !== "nicht_auswertbar") || S.project.photos[0])?.id ?? null;
    drawList();
    drawDetail();
  }

  function drawDetail() {
    const p = cur();
    if (!p) {
      clear(detail, h("div", { class: "empty" }, icon("camera", 34), h("strong", {}, "Noch keine Fotos in diesem Projekt"),
        h("span", {}, "Unterlage ausdrucken, Teil auflegen, senkrecht fotografieren und hier hochladen."),
        h("a", { href: "/", class: "small" }, "Unterlage erzeugen")));
      return;
    }
    const a = p.analysis || {};
    const hasRect = p.files.includes("rect"), hasGauge = p.files.includes("gauge");
    if (mode === "gauge" && !hasGauge) mode = "both";
    if ((mode === "rect" || mode === "both") && !hasRect) mode = hasGauge ? "gauge" : "orig";
    const segBtn = (k, t) => h("button", { "aria-pressed": String(mode === k), onclick: () => { mode = k; drawDetail(); } }, t);
    const figs = [];
    const fig = (src, alt, cap) => h("figure", {}, h("a", { href: src, target: "_blank", rel: "noopener" }, h("img", { src, alt })), h("figcaption", {}, cap));
    if (mode === "orig" || mode === "both") figs.push(fig(`/api/photos/${p.id}/overlay.jpg`, "Originalfoto mit erkannten Markern",
      ["Original · ", h("strong", {}, `${(a.mat_ids || []).length} von 8 Markern`), " erkannt"]));
    if ((mode === "rect" || mode === "both") && hasRect) figs.push(fig(`/api/photos/${p.id}/rect.jpg`, "Entzerrte Draufsicht",
      ["Entzerrt · ", h("span", { class: "mono" }, "10 px/mm"), " · Ursprung unten links"]));
    if (mode === "gauge" && hasGauge) figs.push(fig(`/api/photos/${p.id}/gauge.jpg`, "Entzerrte Höhenlehre",
      [`Höhenlehre ${p.gauge.strip} · `, h("span", { class: "mono" }, `${num(p.gauge.rms_mm, 2)} mm`), " Restfehler · Nullpunkt = Tischebene"]));

    const loo = a.loo_mm || {};
    const bars = h("div", { class: "bars" }, Object.keys(loo).sort((x, y) => x - y).map(id => {
      const v = loo[id], w = Math.min(100, v * 100);
      return [h("span", { class: "mono" }, `ID ${id}`), h("span", { class: "bar" }, h("i", { class: v > 1 ? "err" : v > 0.5 ? "warn" : "", style: { width: `${w}%` } }), h("b")),
        h("span", { class: "mono", style: { textAlign: "right" } }, num(v, 2, false))];
    }));
    const [st, sk] = STATUS[p.status] || [p.status, "off"];

    const gridH = S.project.grid_h || (p.format === "A3" ? 360 : 230);
    const cx = h("input", { inputmode: "decimal", value: S.project.ctrl_x != null ? num(S.project.ctrl_x, 2) : "", placeholder: "100,0", "aria-label": "Kontrollmaß 0–100 gemessen" });
    const cy = h("input", { inputmode: "decimal", value: S.project.ctrl_y != null ? num(S.project.ctrl_y, 2) : "", placeholder: num(gridH, 1, false), "aria-label": `Raster 0–${gridH} vertikal gemessen` });
    const fac = S.project.factors || [1, 1];
    const saveCtrl = async () => {
      const x = parseNum(cx.value), y = parseNum(cy.value);
      if (Number.isNaN(x) || Number.isNaN(y)) { toast("Bitte eine Zahl eingeben", "err"); return; }
      const body = { clear_ctrl: true, ...(x != null ? { ctrl_x: x } : {}), ...(y != null ? { ctrl_y: y } : {}) };
      try {
        S.project = await api(`/api/projects/${S.project.id}`, { method: "PATCH", body });
        drawDetail();
        toast("Korrekturfaktoren übernommen", "ok");
      } catch (e) { fail(e); }
    };
    [cx, cy].forEach(i => i.addEventListener("change", saveCtrl));

    clear(detail,
      h("div", { class: "card-head", style: { alignItems: "flex-start" } },
        h("div", {}, h("h2", { id: "det-h" }, `${p.filename} · ${VIEW_LABEL[p.view] || p.view}`),
          h("span", { class: "small muted" }, [`${a.width} × ${a.height} px`, p.format ? `${p.format}${a.format_auto ? " (automatisch)" : ""}` : null,
            (a.mat_ids || []).length >= 4 ? `Homographie aus ${(a.mat_ids || []).length * 4} Ecken` : null].filter(Boolean).join(" · "))),
        h("div", { class: "seg", role: "group", "aria-label": "Ansicht" }, segBtn("orig", "Original"), hasRect ? segBtn("rect", "Entzerrt") : null,
          hasRect ? segBtn("both", "Beide") : null, hasGauge ? segBtn("gauge", "Höhenlehre") : null)),
      p.status === "nicht_auswertbar" ? h("div", { class: "note err" }, icon("warn"), h("span", {}, `Nur ${(a.mat_ids || []).length} Marker der Unterlage erkannt – mindestens 4 sind nötig. `,
        (a.missing_ids || []).length ? `Fehlend: ID ${a.missing_ids.join(", ")}. ` : "", "Foto mit allen Markern im Bild wiederholen.")) : null,
      p.status === "unsicher" ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, "Restfehler über 1 mm. Unterlage liegt vermutlich nicht flach oder das Foto ist unscharf – besser wiederholen.")) : null,
      h("div", { class: `duo ${figs.length === 1 ? "one" : ""}` }, figs),
      h("div", { class: "grid2", style: { gap: "24px", alignItems: "start" } },
        h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } },
          h("div", { class: "card-head" }, h("h3", {}, "Restfehler je Marker"),
            p.max_err != null ? h("span", { class: `badge ${sk}` }, `Max. ${num(p.max_err, 2)} mm · ${st}`) : h("span", { class: `badge ${sk}` }, st)),
          Object.keys(loo).length ? bars : h("p", { class: "hint" }, "Zu wenige Marker für eine Fehlerabschätzung."),
          h("span", { class: "xs muted" }, "Skala 0–1 mm · Linie bei 0,5 mm = Grenze „gut“ · über 1 mm Foto wiederholen")),
        h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } },
          h("h3", {}, "Kontrollmaß vom Ausdruck"),
          h("div", { class: "ctrl" },
            h("label", { class: "field" }, h("span", { class: "small", style: { fontWeight: 600 } }, "0–100 gemessen"), h("span", { class: "unit" }, cx, h("span", {}, "mm"))),
            h("label", { class: "field" }, h("span", { class: "small", style: { fontWeight: 600 } }, `Raster 0–${gridH} vertikal`), h("span", { class: "unit" }, cy, h("span", {}, "mm")))),
          h("div", { class: "chips small" }, h("span", {}, "Faktor X ", h("strong", { class: "mono" }, num(fac[0], 4, false))),
            h("span", {}, "Faktor Y ", h("strong", { class: "mono" }, num(fac[1], 4, false)))),
          h("span", { class: "xs muted" }, "Gilt für alle Fotos dieses Projekts. Leer lassen = Faktor 1."))),
      h("div", { class: "chips", style: { justifyContent: "space-between" } },
        h("div", { class: "chips" },
          hasRect ? h("a", { class: "btn", href: `/api/photos/${p.id}/rect.jpg`, download: `${p.filename.replace(/\.\w+$/, "")}_entzerrt.jpg` }, icon("download"), "Draufsicht herunterladen") : null,
          h("button", { class: "btn danger", onclick: () => del(p) }, icon("trash", 16), "Entfernen")),
        h("a", { class: `btn primary`, href: "/messen", "aria-disabled": S.project.photos.some(x => x.files.includes("rect")) ? null : "true" }, "Weiter zum Messen", icon("right"))));
  }

  draw();
  void go;
}
