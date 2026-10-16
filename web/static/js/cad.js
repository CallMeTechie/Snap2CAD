// Schritt 4: CAD-Modell – Auftrag, Fortschritt, Ergebnis
import { api, h, clear, icon, num, bytes, toast, fail, mmss, dt, confirmDlg, copyText, fmtValue } from "./lib.js";
import { S, ensureProject, reloadProject, go, onLeave, refreshMe, jobBadge, readOnlyNote } from "./app.js";
import { isReadOnly, readOnlyText } from "./rights.js";
import { VIEW_LABEL } from "./photos.js";
import { DEFAULT_SEL, DIM_GROUP_KEYS, DIM_GROUP_LABEL, conclusionText, de, dimSel, dimState, groupText, hasAnchors, paramBanner, parseDimInput,
  r3 } from "./geom.js";

const PROC = {
  fdm: ["3D-Druck FDM", "Bohrungsausgleich, Wandstärke, Druckrichtung", "PETG"],
  sla: ["3D-Druck SLA", "Feine Details, Entlüftung, Stützen", "Standard-Harz"],
  cnc: ["CNC-Fräsen", "Innenradien, Aufspannungen, Normbohrungen", "Alu 6082"],
};
const RULES = { fdm: "FDM: Bohrungen +0,2–0,3 mm, Wandstärke ≥ 1,2 mm, druckbare Überhänge", sla: "SLA: feine Details, Entlüftungslöcher, Wandstärke ≥ 0,8 mm",
  cnc: "CNC: Innenradien, Normbohrungen, keine Hinterschnitte" };
const CHIPS = { fdm: ["Bohrungen +0,2 mm für Schrauben", "Wandstärke 2 mm", "Ohne Stützen druckbar machen", "Fase 0,5 mm an der Unterseite"],
  sla: ["Hohl mit 2 mm Wand und Entlüftung", "Kanten 0,3 mm verrunden"], cnc: ["Bohrungen als Senkung M6", "Innenradien vergrößern", "Für FDM aufbereiten"] };
// Gruppen der Bemaßung: Schlüssel und Schalter über dem Viewer (Spec Stufe B §3); Spalte „Gruppe“ über groupText
const DIM_GROUPS = DIM_GROUP_KEYS.map(k => [k, DIM_GROUP_LABEL[k]]);
const MAX_PARAM = 20;   // Werte je Neuaufbau (jobs.PARAM_MAX)
const LOCK_VER = "Werte sind nur in der aktuellen Version änderbar.", LOCK_RUN = "Der Auftrag läuft – bitte warten.", LOCK_RO = "Nur ansehen – Rolle Lesend";

function flow(stage) {
  const it = (n, t, st) => h("li", { class: st }, h("span", { class: "n" }, st === "dn" ? "✓" : n), t);
  const s = i => (i < stage ? "dn" : i === stage ? "on" : "");
  return h("ol", { class: "flow", "aria-label": "Ablauf" }, it("a", "Auftrag", s(0)), h("li", { class: "ln" }), it("b", "Erzeugen", s(1)), h("li", { class: "ln" }), it("c", "Ergebnis", s(2)));
}
function procOf(job) { return job?.request?.process || "fdm"; }

// ================================================================== Auftrag
export async function form(main) {
  await ensureProject(true);
  const P = S.project, st = S.status || {}, readOnly = isReadOnly(P);   // Rolle Lesend (Spec Teams §7)
  const meas = P.measurements.filter(m => m.accepted);
  const crit = meas.filter(m => m.critical);
  const partsList = P.parts || [];
  let partSel = "";
  const partBox = partsList.length ? h("select", { id: "part", class: "input", onchange: e => { partSel = e.target.value; drawMeas(); onSel(); } },
    h("option", { value: "" }, "Alle Teile (ein Körper)"),
    partsList.map(t => h("option", { value: String(t.id) }, `${t.id_label} · ${t.label}${t.view === "bottom" ? " (unten)" : ""}`))) : null;
  // wie jobs.measurement_table: Maße ohne Teil, des Teils selbst und der Teile, die als dasselbe Teil verknüpft sind (same_as)
  const sentMeas = () => {
    if (!partSel) return meas;
    const id = Number(partSel), linked = new Set(partsList.filter(t => t.same_as === id).map(t => t.id));
    return meas.filter(m => m.part_id == null || m.part_id === id || linked.has(m.part_id));
  };
  const measBox = h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } });
  function drawMeas() {
    const list = sentMeas();
    clear(measBox, h("span", { class: "label" }, `Maßtabelle · ${list.length}`),
      list.length ? h("table", { class: "t" }, h("thead", {}, h("tr", {}, h("th", {}, "ID"), h("th", {}, "Merkmal"), h("th", { style: { textAlign: "right" } }, "Wert"), h("th", { style: { textAlign: "right" } }, "±"))),
        h("tbody", {}, list.map(m => h("tr", {}, h("td", { class: "mono" }, `M${m.seq}`), h("td", {}, m.label, m.critical ? " ★" : ""),
          h("td", { class: "num" }, m.caliper != null ? `${m.kind === "diameter" ? "Ø " : ""}${num(m.caliper, 2)}` : fmtValue(m, false)),
          h("td", { class: "num" }, m.caliper != null ? "MS" : num(m.unc, 1))))))
        : h("div", { class: "note warn" }, icon("warn"), h("span", {}, "Noch keine Maße. ", h("a", { href: "/messen" }, "Jetzt messen"), " – oder alles im Feld „Zweck und Funktion“ beschreiben.")),
      list.length ? h("span", { class: "xs muted" }, "★ kritisch · MS = Messschieber-Wert") : null);
  }
  let proc = "fdm";
  try { const v = localStorage.getItem("mu.proc"); if (Object.hasOwn(PROC, v)) proc = v; } catch { /* */ }
  const name = h("input", { id: "name", class: "input", value: P.name, maxlength: 120, required: true });
  const zweck = h("textarea", { id: "zweck", class: "input", rows: 3, maxlength: 6000, placeholder: "z. B. Ersatz für eine gebrochene Halteplatte. Nimmt ein Kugellager 608 (Ø 22 mm) auf und wird mit 2× M6 verschraubt." });
  const material = h("input", { class: "input", value: PROC[proc][2], maxlength: 80 });
  const cutter = h("input", { inputmode: "decimal", value: "6" });
  const cutterHint = h("span", { class: "xs muted" });
  const setups = h("select", { class: "input" }, ["1 · nur von oben", "2 · oben + unten", "4-Achs"].map(t => h("option", {}, t)));
  const extra = h("textarea", { id: "extra", class: "input", rows: 2, maxlength: 2000, placeholder: "z. B. Oberkanten 0,5 mm fasen." });
  const cncBox = h("div", { class: "grid3" },
    h("label", { class: "field" }, h("span", { class: "flabel" }, "Material"), material),
    h("label", { class: "field cnc" }, h("span", { class: "flabel" }, "Kleinster Fräser"), h("span", { class: "unit" }, h("span", {}, "Ø"), cutter, h("span", {}, "mm")), cutterHint),
    h("label", { class: "field cnc" }, h("span", { class: "flabel" }, "Aufspannungen"), setups));
  const updCutter = () => { const d = parseFloat(cutter.value.replace(",", ".")); cutterHint.textContent = d > 0 ? `→ Innenradien ≥ ${num(d / 2 + 0.2, 1)} mm` : ""; };
  cutter.addEventListener("input", updCutter); updCutter();
  const fits = crit.map(m => ({ m, fit: h("input", { class: "input", value: m.fit || "", placeholder: proc === "cnc" ? "H7" : "Spiel", maxlength: 20, style: { minHeight: "38px" } }),
    depth: h("select", { class: "input", style: { minHeight: "38px" } }, h("option", {}, "durch"), h("option", {}, "Sackloch"), h("option", {}, "–")) }));
  const procRadio = k => h("label", { class: "choice" },
    h("span", { class: "c1" }, h("input", { type: "radio", name: "proc", value: k, checked: k === proc, onchange: () => setProc(k) }), PROC[k][0]),
    h("span", { class: "c2" }, PROC[k][1]));
  function setProc(k) {
    const prevDefault = PROC[proc][2];
    proc = k; try { localStorage.setItem("mu.proc", k); } catch { /* */ }
    if (!material.value || material.value === prevDefault) material.value = PROC[k][2];
    cncBox.querySelectorAll(".cnc").forEach(e => { e.hidden = k !== "cnc"; });
    rules.textContent = RULES[k];
  }
  // Fotos
  const usable = P.photos.filter(p => p.files.includes("rect") || p.files.includes("gauge") || ((p.view === "tilted" || p.view === "overview") && p.files.includes("orig")));
  const picked = new Set(usable.filter(p => p.status !== "unsicher").slice(0, 6).map(p => p.id));
  const photoFigs = h("div", { class: "thumbs" });
  const imgBox = h("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } });
  const checkBox = h("section", { class: "card" });
  const drawPhotos = () => clear(photoFigs, usable.length ? usable.map(p => h("figure", {},
    h("label", { style: { cursor: "pointer", display: "flex", flexDirection: "column", gap: "4px" } },
      h("img", { src: `/api/photos/${p.id}/${p.files.includes("rect") ? "rect" : p.files.includes("gauge") ? "gauge" : "thumb"}.jpg`, alt: p.filename, style: { opacity: picked.has(p.id) ? 1 : 0.35 } }),
      h("span", { class: "check xs", style: { minHeight: "auto" } }, h("input", { type: "checkbox", checked: picked.has(p.id), onchange: e => { e.target.checked ? picked.add(p.id) : picked.delete(p.id); drawPhotos(); onSel(); } }),
        `${p.filename.replace(/\.\w+$/, "")} · ${VIEW_LABEL[p.view]}${p.files.includes("gauge") && p.view !== "tilted" && p.view !== "gauge" ? " + Höhe" : ""}`))))
    : h("p", { class: "hint" }, "Keine entzerrten Fotos – das Modell entsteht dann nur aus Maßen und Beschreibung."));
  drawPhotos();
  const rules = h("dd", {}, RULES[proc]);
  const us = st.usage || {};
  const blocked = readOnly ? `${readOnlyText(P)}: keine CAD-Aufträge.` : !st.ai ? "KI ist nicht eingerichtet (Verwaltung → Einstellungen)." : !st.sandbox ? "Die CAD-Sandbox läuft nicht." :
    (us.quota != null && us.used >= us.quota) ? `Monatskontingent erreicht (${us.used} / ${us.quota}).` : "";
  const submit = h("button", { class: "btn primary big wide", type: "submit", form: "cadform", disabled: !!blocked }, icon("cube"), "CAD-Modell erzeugen");

  // Pruefung vor dem Modellieren (Spec Stufe A): laeuft automatisch, solange sich die Grundlage geaendert hat
  let chk = P.cad_check, checking = false, again = false, retryTimer = null, selTimer = null;
  onLeave(() => { clearTimeout(retryTimer); clearTimeout(selTimer); });
  const sel = () => ({ photo_ids: [...picked], part_id: partSel ? Number(partSel) : null });
  const same = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());
  const needCheck = () => !chk || chk.error || chk.stale || !same(chk.photo_ids, sel().photo_ids) || (chk.part_id ?? null) !== sel().part_id;
  // Auswahl geaendert: laeuft gerade eine Pruefung, danach in jedem Fall neu vergleichen (needCheck prueft dort gegen das neue Ergebnis)
  // Mehrfachklicks (Fotos abhaken) zu einer Pruefung zusammenfassen
  function onSel() {
    if (!st.ai || readOnly) return;
    clearTimeout(selTimer);
    selTimer = setTimeout(() => { if (!main.isConnected) return; if (checking) again = true; else if (needCheck()) runCheck(); }, 700);
  }
  async function runCheck(force = false) {
    if (checking) { again = true; return; }
    clearTimeout(retryTimer);
    checking = true; drawCheck();
    try { chk = await api(`/api/projects/${P.id}/cad-check`, { method: "POST", body: { ...sel(), force } }); await reloadProject().catch(() => {}); }
    catch (e) {
      if (e.status === 409) { again = false; clearTimeout(retryTimer); retryTimer = setTimeout(() => { if (main.isConnected) runCheck(false); }, 3000); return; }
      chk = { error: e.message, items: [], images: [] };
    } finally {
      checking = false; drawCheck();
      const rerun = again && !chk?.error; again = false;
      if (rerun && main.isConnected && needCheck()) runCheck();
    }
  }
  const IMG_KIND = { top: "Draufsicht", bottom: "Von unten", gauge: "Höhenlehre", tilted: "Schrägfoto (Original)" };
  function imgCount() {   // wie jobs.pick_images: je Foto ein Bild nach Ansicht, dazu die Höhenlehre
    let n = 0;
    for (const p of usable) if (picked.has(p.id)) n += (p.view === "tilted" || p.view === "overview" || ((p.view === "top" || p.view === "bottom") && p.files.includes("rect")) ? 1 : 0) + (p.files.includes("gauge") ? 1 : 0);
    return n;
  }
  function drawCheck() {
    const blocks = (chk?.items || []).filter(i => i.severity === "block").length;
    submit.replaceChildren(icon("cube"), blocks ? "Trotzdem erzeugen" : "CAD-Modell erzeugen");
    submit.disabled = checking || !!blocked;
    const byHand = !!P.material_user;
    const mat = (byHand ? [P.color, P.material, P.finish] : chk?.material ? [chk.material.color, chk.material.material, chk.material.finish] : []).filter(Boolean).join(", ");
    clear(checkBox, h("div", { class: "card-head" }, h("h2", {}, "Vor dem Modellieren"),
        h("button", { class: "btn sm", type: "button", disabled: checking || readOnly, onclick: () => runCheck(true) }, checking ? h("span", { class: "spin" }) : icon("refresh", 14), "Erneut prüfen")),
      chk?.error ? h("div", { class: "note warn" }, icon("warn"), h("span", {}, `Prüfung nicht möglich: ${chk.error}`)) : null,
      chk && !chk.error ? (chk.items.length ? h("ul", { class: "checks" }, chk.items.map(i => h("li", {}, stateIcon(i.severity === "block" ? "fail" : "warn"), h("span", {}, i.text))))
        : h("div", { class: "note ok" }, icon("check"), h("span", {}, "Die Unterlagen reichen für ein vollständiges Modell."))) : null,
      mat ? h("span", { class: "xs muted" }, `Werkstück (${byHand ? "von Hand" : "geschätzt"}): ${mat} – unter „Fotos prüfen“ änderbar`) : null,
      chk?.checked_at ? h("span", { class: "xs muted" }, `Geprüft ${dt(chk.checked_at)}${chk.stale ? " · veraltet" : ""}`) : null);
    const imgs = chk?.images || [], fname = id => (P.photos.find(p => p.id === id)?.filename || `Foto ${id}`);
    clear(imgBox, h("span", { class: "label" }, `Bilder für die KI · ${imgs.length}`),
      imgs.map(i => h("span", { class: "small" }, `${fname(i.photo_id)} · ${IMG_KIND[i.kind] || i.kind}`)),
      imgCount() > 6 ? h("span", { class: "xs", style: { color: "var(--warn)" } }, "Nur die ersten 6 Bilder gehen mit") : null);
  }

  main.append(
    h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, "CAD-Modell erzeugen"),
      h("p", { class: "lead" }, "Aus Maßen und Fotos entsteht ein parametrisches build123d-Modell. Der Code läuft abgeschottet auf dem Server und liefert STEP und STL.")),
    flow(0)),
    readOnly ? readOnlyNote(P) : null,
    h("div", { class: "cad-layout" },
      h("form", { id: "cadform", class: "card", "aria-labelledby": "f-h", onsubmit: async ev => {
        ev.preventDefault();
        submit.disabled = true;
        try {
          const job = await api("/api/jobs", { method: "POST", body: {
            project_id: P.id, name: name.value.trim(), request: zweck.value.trim(), process: proc, material: material.value.trim(),
            cutter_d: proc === "cnc" ? parseFloat(cutter.value.replace(",", ".")) || null : null, setups: proc === "cnc" ? setups.value : "",
            fits: fits.map(f => ({ id: `M${f.m.seq}`, fit: f.fit.value.trim(), depth: f.depth.value === "–" ? "" : f.depth.value })),
            extra: extra.value.trim(), photo_ids: [...picked], part_id: partSel ? Number(partSel) : null,
            check_items: (chk?.items || []).map(i => ({ kind: i.kind, severity: i.severity, text: i.text })) } });
          refreshMe().catch(() => {});
          go(`/cad/${job.id}`);
        } catch (e) { fail(e); submit.disabled = false; }
      } },
      h("h2", { id: "f-h" }, "Auftrag"),
      h("div", { class: "field" }, h("label", { for: "name" }, "Bezeichnung"), name),
      partBox ? h("div", { class: "field" }, h("label", { for: "part" }, "Modell für"), partBox,
        h("span", { class: "hint" }, "Bei einem einzelnen Teil gehen nur dessen Maße und Maße ohne Teil in den Auftrag.")) : null,
      h("div", { class: "field" }, h("label", { for: "zweck" }, "Zweck und Funktion"), zweck,
        h("span", { class: "hint" }, "Je klarer die Funktion, desto besser trifft die KI Konstruktionsabsicht und Nennmaße.")),
      h("fieldset", {}, h("legend", {}, "Fertigung"), h("div", { class: "grid3" }, Object.keys(PROC).map(procRadio))),
      cncBox,
      crit.length ? h("fieldset", {}, h("legend", {}, "Passungen aus kritischen Maßen"),
        fits.map(f => h("div", { style: { display: "grid", gridTemplateColumns: "48px minmax(0,1fr) 110px 120px", gap: "10px", alignItems: "center" } },
          h("span", { class: "mid" }, `M${f.m.seq}`),
          h("span", { class: "small" }, `${f.m.label} · `, h("span", { class: "mono" }, f.m.caliper != null ? `${num(f.m.caliper, 2)}` : fmtValue(f.m)),
            f.m.caliper != null ? h("span", { class: "muted" }, " (Messschieber)") : null),
          h("label", { class: "field", style: { gap: "2px" } }, h("span", { class: "xs muted" }, "Passung"), f.fit),
          h("label", { class: "field", style: { gap: "2px" } }, h("span", { class: "xs muted" }, "Tiefe"), f.depth))))
        : h("p", { class: "hint" }, "Tipp: Maße unter „Messen“ als kritisch markieren, dann lassen sich hier Passungen festlegen."),
      h("div", { class: "field" }, h("label", { for: "extra" }, "Zusatzwünsche ", h("span", { class: "muted", style: { fontWeight: 400 } }, "(optional)")), extra)),
      h("aside", { class: "card", "aria-labelledby": "s-h" },
        h("h2", { id: "s-h" }, "Grundlage für das Modell"),
        h("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } }, h("span", { class: "label" }, `Entzerrte Fotos · ${picked.size}`), photoFigs),
        measBox,
        imgBox,
        h("dl", { class: "kv" },
          h("dt", {}, "Modell"), h("dd", { class: "mono small" }, st.ai_fake ? "Testmodus (AI_FAKE)" : `${st.model} · Server-Key`),
          h("dt", {}, "Regeln"), rules,
          h("dt", {}, "Sandbox"), h("dd", {}, `kein Netz · max. ${st.limits?.timeout_s ?? 120} s · ${num((st.limits?.mem_mb ?? 3072) / 1024, 1)} GB · eigener Benutzer`),
          h("dt", {}, "Korrektur"), h("dd", {}, `bei Fehler bis zu ${st.limits?.autofix ?? 2} automatische Versuche`),
          h("dt", {}, "Kontingent"), h("dd", {}, us.quota == null ? `${us.used ?? 0} Läufe diesen Monat (unbegrenzt)` : `${us.used} von ${us.quota} Läufen diesen Monat`)),
        blocked ? h("div", { class: "note err" }, icon("warn"), h("span", {}, blocked)) : null,
        checkBox,
        submit,
        h("a", { href: "/auftraege", class: "small", style: { textAlign: "center" } }, "Frühere Aufträge ansehen"))));
  drawMeas();
  setProc(proc);
  drawCheck();
  if (st.ai && !readOnly && needCheck()) runCheck();
  zweck.focus();
}

// ================================================================== Auftrag ansehen
export async function job(main, id) {
  let J = await api(`/api/jobs/${id}`);
  if (!main.isConnected) return;  // waehrend des Ladens weg navigiert: keine Uhr und keine Abfrage starten
  const readOnly = isReadOnly(J);   // Rolle Lesend: alles sehen, nichts ändern (Spec Teams §7)
  let ver = null, tab = "3d", viewer = null, timer = null, inflight = false, gone = false, fails = 0, jv = 0, liveCode = false, lastSig = "",
    followLatest = false,   // nach einem Neuaufbau: am Ende die neue aktuelle Version zeigen
    view3 = null, view3Used = false;   // 3D-Ansicht { version, box, views3 }: bleibt bei gleicher Version stehen (kein neuer Viewer)
  const root = h("div", { style: { display: "contents" } });
  main.append(root);
  onLeave(() => { gone = true; clearTimeout(timer); clearInterval(clock); dropViewer(); photoCache = null; });
  const running = () => J.status === "queued" || J.status === "running";
  // Neuaufbau ohne KI (Spec Stufe B §2): die Ergebnisansicht bleibt stehen, Felder gesperrt; Signatur ohne Protokollzeilen.
  // Nur wenn die letzte Version selbst eine laufende Param-Version ist: ein KI-Lauf nach einem Neuaufbau legt seine
  // Version erst nach der Antwort an und zeigt bis dahin den Fortschritt (drawRun).
  const paramRunning = () => { const L = J.versions[J.versions.length - 1]; return running() && L?.trigger === "param" && L.status === "running"; };
  const sig = () => (paramRunning() ? `p|${J.versions.length}` : `${J.status}|${(J.log || []).length}|${J.versions.length}`);
  const canEdit = V => !readOnly && !!V && V.status === "ok" && V.version === J.current_version && !running();
  const lockText = () => (readOnly ? LOCK_RO : running() ? LOCK_RUN : LOCK_VER);
  function dropViewer() { viewer?.dispose(); viewer = null; view3 = null; }

  function runStart() {
    const L = J.log || [];
    for (let i = L.length - 1; i >= 0; i--) if (/^(Auftrag angelegt|Änderungswunsch)/.test(L[i].msg)) return new Date(L[i].ts);
    return new Date(J.created_at);
  }
  const clockEl = h("span", { class: "mono" });
  const clock = setInterval(() => { if (running()) clockEl.textContent = mmss((Date.now() - runStart()) / 1000); }, 1000);

  // Abfrage als setTimeout-Kette: hoechstens eine Anfrage unterwegs. jv zaehlt Nutzeraktionen (Abbrechen,
  // Aenderung): eine Antwort, die davor losgeschickt wurde, ueberschreibt deren Stand nicht.
  async function poll() {
    timer = null; inflight = true;
    const v = jv;
    let j = null, err = null;
    try { j = await api(`/api/jobs/${id}`); } catch (e) { err = e; } finally { inflight = false; }
    if (gone) return;
    if (err?.status === 404) { if (!err.handled) go("/auftraege"); return; }   // der Hook zeigt die Meldung und navigiert
    if (err) { if (++fails === 3) fail(err); }  // Netz oder Server: weiter versuchen, nach dem dritten Fehlschlag einmal melden
    else {
      fails = 0;
      if (v === jv) { J = j; if (sig() !== lastSig) { try { draw(); } catch (e) { fail(e); } } }
    }
    if (running()) startPoll(); else refreshMe().catch(() => {});
  }
  function startPoll() { if (!timer && !inflight && !gone) timer = setTimeout(poll, 1500); }

  function draw() {
    lastSig = sig();
    conclBtns = []; tableLock = null; view3Used = false;
    if (running() && !paramRunning()) drawRun(); else drawResult();
    if (!view3Used) dropViewer();   // 3D-Ansicht nicht mehr gezeigt (anderer Tab, Fortschritt): Viewer abbauen
    if (running()) startPoll();
  }
  async function cancelJob() {
    if (!await confirmDlg("Auftrag abbrechen?", "Der laufende Schritt wird beendet. Bereits fertige Versionen bleiben erhalten.", "Abbrechen", true)) return;
    try { J = await api(`/api/jobs/${id}/cancel`, { method: "POST" }); if (gone) return; jv++; draw(); } catch (e) { if (!gone) fail(e); }
  }

  // ---------------------------------------------------------------- Fortschritt
  function drawRun() {
    const start = runStart();
    const rel = ts => mmss((new Date(ts) - start) / 1000);
    const L = (J.log || []).filter(l => new Date(l.ts) >= start);
    const vers = J.versions;
    const items = L.map((l, i) => {
      const last = i === L.length - 1;
      let cls = l.level === "ok" ? "ok" : l.level === "error" ? "err" : l.level === "warn" ? "warn" : last ? "run" : "ok";
      let extra = null;
      if (l.level === "warn" && /^Version (\d+)/.test(l.msg)) {
        const vn = Number(l.msg.match(/^Version (\d+)/)[1]); const v = vers.find(x => x.version === vn);
        if (v?.error) extra = h("code", {}, `${v.error.line ? `Zeile ${v.error.line} · ${v.error.code || ""}\n` : ""}${v.error.type}: ${String(v.error.message).slice(0, 400)}`);
      }
      return h("li", { "aria-current": last ? "step" : null },
        h("span", { class: `ic ${cls}` }, cls === "run" ? h("span", { class: "spin", style: { width: "12px", height: "12px" } }) : cls === "ok" ? icon("check", 13) : cls === "err" ? icon("x", 13) : "!"),
        h("span", {}, h("strong", { style: { fontWeight: last ? 600 : 500 } }, l.msg), extra),
        h("span", { class: "tm" }, rel(l.ts)));
    });
    const pending = ["Prüfung · STEP-Re-Import, STL wasserdicht, Hüllquader", "Vorschau und Downloads · Iso, Oben, Vorn, Seite"].map(t =>
      h("li", { style: { opacity: 0.5 } }, h("span", { class: "ic" }), h("span", {}, h("strong", { style: { fontWeight: 500 } }, t.split(" · ")[0]), h("br"), h("span", { class: "small muted" }, t.split(" · ")[1])), h("span", { class: "tm" })));
    const logPre = h("pre", { class: "log", "aria-live": "off" }, L.map(l => h("span", { class: l.level === "error" ? "e" : l.level === "warn" ? "w" : l.level === "ok" ? "o" : "" }, `${rel(l.ts)}  ${l.msg}\n`)),
      h("span", {}, "▍"));
    const lastV = vers[vers.length - 1];
    const codeBox = liveCode && lastV?.code ? codeView(lastV.code, null) : null;
    clockEl.textContent = mmss((Date.now() - start) / 1000);
    clear(root,
      h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, `${J.name} wird erzeugt`),
        h("p", { class: "lead" }, "Laufzeit ", clockEl, " · üblich 30 s bis 2 min")), flow(1)),
      readOnly ? readOnlyNote({ team_name: J.team_name }) : null,
      h("div", { class: "row" },
        h("section", { class: "card", style: { flex: "1 1 420px" }, "aria-labelledby": "t-h" }, h("h2", { id: "t-h" }, "Fortschritt"),
          h("ol", { class: "timeline" }, items, pending)),
        h("section", { class: "card", style: { flex: "1 1 420px" }, "aria-labelledby": "l-h" },
          h("div", { class: "card-head" }, h("h2", { id: "l-h" }, "Protokoll"),
            h("label", { class: "check small" }, h("input", { type: "checkbox", checked: liveCode, onchange: e => { liveCode = e.target.checked; draw(); } }), "Code live mitlesen")),
          logPre, codeBox,
          h("div", { class: "chips", style: { justifyContent: "space-between" } },
            h("span", { class: "small muted" }, "Du kannst die Seite verlassen. Der Auftrag läuft weiter und erscheint unter „Meine Aufträge“."),
            readOnly ? null : h("button", { class: "btn danger", onclick: cancelJob }, "Abbrechen")))));
    logPre.scrollTop = logPre.scrollHeight;
    startPoll();
  }

  // ---------------------------------------------------------------- Ergebnis
  function drawResult() {
    const vers = J.versions;
    if (followLatest && !running()) { ver = null; followLatest = false; }
    if (ver === null || !vers.find(v => v.version === ver)) ver = J.current_version || vers[vers.length - 1]?.version || null;
    const V = vers.find(v => v.version === ver);
    const ok = V && V.status === "ok";
    const checks = V?.checks || [];
    const nWarn = checks.filter(c => c.state === "warn").length, nFail = checks.filter(c => c.state === "fail").length;
    const verSel = h("select", { class: "input", style: { minHeight: "38px", width: "auto" }, onchange: e => { ver = Number(e.target.value); draw(); } },
      [...vers].reverse().map(v => h("option", { value: v.version, selected: v.version === ver, disabled: v.status === "running" },
        `v${v.version} · ${v.version === J.current_version ? "aktuell · " : ""}${v.status === "ok" ? "geprüft" : v.status === "running" ? "läuft" : v.status === "cancelled" ? "abgebrochen" : v.error ? "Sandbox-Fehler" : "fehlgeschlagen"}`)));
    const summary = !V ? h("span", { class: "badge off" }, "keine Version")
      : !ok ? h("span", { class: "badge err" }, "Version fehlerhaft")
        : nFail ? h("span", { class: "badge err" }, `${nFail} Prüfung(en) nicht bestanden`)
          : nWarn ? h("span", { class: "badge warn" }, `${nWarn} Hinweis${nWarn > 1 ? "e" : ""}`) : h("span", { class: "badge ok" }, icon("check", 12), "Alle Prüfungen bestanden");

    const head = h("div", { class: "head" }, h("div", { class: "t" }, h("h1", {}, J.name),
      h("div", { class: "chips" }, vers.length ? h("label", { class: "chips small" }, "Version", verSel) : null, summary, jobBadge(J.status),
        paramRunning() ? h("span", { class: "badge info", role: "status" }, h("span", { class: "spin", style: { width: "12px", height: "12px" } }),
          `Neuaufbau mit ${vers[vers.length - 1].request_text} …`) : null,
        paramRunning() && !readOnly ? h("button", { class: "btn sm danger", onclick: cancelJob }, "Abbrechen") : null,
        S.me.role === "admin" && J.user_id !== S.me.id ? h("span", { class: "badge info" }, "Auftrag eines anderen Benutzers") : null)),
    flow(ok ? 3 : 2));

    const errNote = J.status === "failed" || J.status === "cancelled" ? h("div", { class: `note ${J.status === "failed" ? "err" : "warn"}` }, icon("warn"),
      h("div", {}, h("strong", {}, J.status === "failed" ? "Auftrag fehlgeschlagen. " : "Auftrag abgebrochen. "), J.error || "",
        J.current_version ? ` Die letzte gültige Version ist v${J.current_version}.` : "",
        J.project_id && vers[vers.length - 1]?.trigger === "param" && vers[vers.length - 1].status !== "ok"
          ? " Der Wert ist trotzdem als Messschieberwert gemerkt (Messseite → löschen)." : "")) : null;

    // Tabs
    const tabs = [["3d", "3D-Ansicht", ok], ["code", `Code`, !!V?.code], ["claude", "KI-Antwort", !!V?.claude_text], ["foto", "Foto-Abgleich", ok && V.files["outline.json"] > 2]];
    if (!tabs.find(t => t[0] === tab && t[2])) tab = (tabs.find(t => t[2]) || ["code"])[0];
    const panel = h("div", { style: { display: "flex", flexDirection: "column", gap: "16px" } });
    const tabBar = h("div", { class: "seg", role: "tablist", "aria-label": "Ansicht" }, tabs.filter(t => t[2]).map(([k, t]) =>
      h("button", { role: "tab", "aria-selected": String(tab === k), onclick: () => { tab = k; draw(); } }, t,
        k === "code" && V?.code ? h("span", { class: "xs muted", style: { marginLeft: "6px" } }, `${V.code.trim().split("\n").length} Z.`) : null)));
    const left = h("section", { class: "card", style: { gap: "16px" }, "aria-label": "Modellansicht" }, tabBar, panel);
    const right = h("div", { style: { display: "flex", flexDirection: "column", gap: "24px" } });

    clear(root, head, readOnly ? readOnlyNote({ team_name: J.team_name }) : null, errNote, h("div", { class: "cad-layout" }, left, right), iterateBox());

    if (tab === "3d" && ok) draw3d(panel, V);
    else if (tab === "code" && V) clear(panel, V.error ? errorBox(V.error) : null, codeView(V.code, V.error?.line),
      h("div", { class: "chips" }, h("button", { class: "btn sm", onclick: () => copy(V.code) }, icon("copy", 14), "Code kopieren"),
        V.files["model.py"] ? h("a", { class: "btn sm", href: `/api/jobs/${id}/v/${V.version}/model.py?download=1` }, icon("download", 14), "model.py") : null));
    else if (tab === "claude" && V) clear(panel, h("pre", { class: "codebox", style: { whiteSpace: "pre-wrap" } }, V.claude_text),
      V.usage?.input_tokens ? h("span", { class: "xs muted" }, `${num(V.usage.input_tokens, 0)} Token Eingabe · ${num(V.usage.output_tokens, 0)} Token Ausgabe · ${V.usage.model || ""}`) : null);
    else if (tab === "foto" && ok) drawOverlay(panel, V).catch(e => clear(panel, h("div", { class: "note err" }, icon("warn"), h("span", {}, `Foto-Abgleich nicht verfügbar: ${e.message}`))));

    // rechte Spalte
    if (V && ok) {
      const r = V.result, base = `/api/jobs/${id}/v/${V.version}`;
      right.append(h("section", { class: "card", "aria-labelledby": "dl-h", style: { gap: "12px" } }, h("h2", { id: "dl-h" }, "Downloads"),
        dlLink(`${base}/model.step?download=1`, "STEP", "", `${slug(J.name)}_v${V.version}.step`, `Master für CAD/CAM · ${bytes(V.files["model.step"])}`),
        dlLink(`${base}/model.stl?download=1`, "STL", "stl", `${slug(J.name)}_v${V.version}.stl`, `${num(r.stl.triangles, 0)} Dreiecke · ${bytes(V.files["model.stl"])}`),
        dlLink(`${base}/model.py?download=1`, "PY", "py", `${slug(J.name)}_v${V.version}.py`, "Parametrisch · build123d"),
        h("div", { class: "chips" }, J.project_id ? h("a", { class: "btn sm", href: `/api/projects/${J.project_id}/measurements.csv`, download: "" }, icon("download", 14), "Maßtabelle CSV") : null,
          h("a", { class: "btn sm", href: `${base}/bundle.zip`, download: "" }, icon("zip", 14), "Alles als ZIP"))));
      right.append(h("section", { class: "card", "aria-labelledby": "ck-h", style: { gap: "12px" } }, h("h2", { id: "ck-h" }, "Prüfung"),
        h("ul", { class: "checks" },
          checks.map(c => h("li", {}, stateIcon(c.state), h("span", {}, h("strong", {}, c.label), c.detail ? ` · ${c.detail}` : ""))),
          h("li", {}, stateIcon("ok"), h("span", {}, h("strong", {}, "Abmessungen "), h("span", { class: "mono" }, `${num(r.bbox[0], 2, false)} × ${num(r.bbox[1], 2, false)} × ${num(r.bbox[2], 2, false)}`),
            h("br"), h("span", { class: "small muted" }, `Volumen ${num(r.volume_mm3 / 1000, 2, false)} cm³ · ${r.faces} Flächen`))),
          h("li", {}, stateIcon("info"), h("span", {}, h("strong", {}, "Abgleich mit Foto"), " · im Tab „Foto-Abgleich“ den Umriss auf das Foto legen")))));
    } else if (V) {
      right.append(h("section", { class: "card", style: { gap: "12px" } }, h("h2", {}, `v${V.version} ist fehlgeschlagen`),
        h("p", { class: "small" }, V.error ? `${V.error.type}${V.error.line ? ` in Zeile ${V.error.line}` : ""} – Details im Tab „Code“.` : "Diese Version hat die Prüfung nicht bestanden."),
        checks.length ? h("ul", { class: "checks" }, checks.map(c => h("li", {}, stateIcon(c.state), h("span", {}, h("strong", {}, c.label), c.detail ? ` · ${c.detail}` : "")))) : null,
        J.current_version && J.current_version !== V.version ? h("button", { class: "btn", onclick: () => { ver = J.current_version; draw(); } }, `Zur gültigen Version v${J.current_version}`) : null));
    }
    const meta = V?.meta || {};
    if (meta.summary || meta.assumptions?.length || meta.check_before_manufacturing?.length) {
      right.append(h("section", { class: "card", "aria-labelledby": "as-h", style: { gap: "12px" } }, h("h2", { id: "as-h" }, "Annahmen der KI"),
        meta.summary ? h("p", { class: "small" }, meta.summary) : null,
        meta.assumptions?.length ? h("ul", { class: "ul" }, meta.assumptions.map(a => h("li", {}, String(a)))) : null,
        meta.check_before_manufacturing?.length ? h("div", { class: "note warn", style: { flexDirection: "column", gap: "4px" } }, h("strong", {}, "Vor der Fertigung:"),
          h("ul", { class: "ul", style: { paddingLeft: "16px" } }, meta.check_before_manufacturing.map(a => h("li", {}, String(a))))) : null));
    }
    if (meta.dimensions?.length) right.append(dimTable(V, meta.dimensions));
  }

  // ---------------------------------------------------------------- Bemaßung am Modell (Spec Stufe B §2, §3, §5)
  // Tabelle und Labels im Viewer teilen eine Sperre: höchstens ein POST /param unterwegs (paramBusy)
  let paramBusy = false, tableLock = null;   // tableLock: Sperre der gerade gezeigten Maßtabelle
  function lockAll(on) {
    tableLock?.(on);
    const V = J.versions.find(v => v.version === view3?.version);
    viewer?.setLocked(on || !canEdit(V), on ? LOCK_RUN : lockText());
  }
  async function sendParam(values) {
    if (paramBusy) { toast(LOCK_RUN); return false; }
    if (values.length > MAX_PARAM) { toast(`Höchstens ${MAX_PARAM} Werte auf einmal.`, "err"); return false; }
    paramBusy = true; lockAll(true);
    let r;
    try { r = await api(`/api/jobs/${id}/param`, { method: "POST", body: { values, base: J.current_version } }); }
    catch (e) { paramBusy = false; if (!gone) { lockAll(false); fail(e); } return false; }
    paramBusy = false;
    if (gone) return true;
    if (r.learned === false) toast("Ohne Projekt – der Wert wird nicht gemerkt.");
    else if (J.project_id && S.project?.id === J.project_id) reloadProject().catch(() => {});   // Messseite: neue Werte
    // Neuaufbau angenommen: lokal als laufend markieren (Version wie auf dem Server: running), die Abfrage holt den Stand;
    // bei gleicher Version bleibt der Viewer stehen, Tabelle und Labels sind über running() gesperrt
    const req = values.map(v => `${v.id} = ${String(r3(v.value))} mm`).join(", ");
    J = { ...J, status: "queued", error: null,
      versions: [...J.versions, { version: r.version, trigger: "param", status: "running", request_text: req, meta: {}, files: {}, checks: [] }] };
    jv++; followLatest = true; ver = null;
    try { draw(); } catch (e) { fail(e); }
    startPoll();
    return true;
  }
  // Änderungswunsch senden („Änderung anfordern“ und „Schlüsse ziehen“); true = angenommen
  async function submitIterate(text) {
    try {
      J = await api(`/api/jobs/${id}/iterate`, { method: "POST", body: { text } });
      refreshMe().catch(() => {});
      if (!gone) { jv++; ver = null; draw(); }
      return true;
    } catch (e) { if (!gone) fail(e); return false; }
  }
  // „Schlüsse ziehen“: bis zur Antwort gesperrt (Doppelklick), Knöpfe der aktuellen Ansicht in conclBtns
  let concluding = false, conclBtns = [];
  const conclOff = () => readOnly || concluding || !(J.pending_param || []).length || running() || !S.status?.ai;
  async function conclude() {
    const text = conclusionText(J.pending_param || []);
    if (concluding || !text || running() || !S.status?.ai) return;
    concluding = true; conclBtns.forEach(b => { b.disabled = true; });
    try { await submitIterate(text); }
    finally { concluding = false; conclBtns.forEach(b => { b.disabled = conclOff(); }); }
  }
  function dimTable(V, list) {
    const edit = canEdit(V), inputs = [];
    const btn = h("button", { class: "btn sm", onclick: () => send(null) }, "Werte übernehmen");
    // only = ein Feld (Enter): sendet dieses Maß immer, auch unverändert („Annahme bestätigen“, Spec §3);
    // sonst („Werte übernehmen“) alle geänderten Felder
    async function send(only) {
      const vals = [];
      for (const [d, inp] of inputs) {
        if (only && inp !== only) continue;
        if (!only && inp.value.trim() === de(d.value)) continue;
        const r = parseDimInput(inp.value);
        if (r.error) { toast(`${d.id}: ${r.error}`, "err"); inp.focus(); return; }
        if (only || Math.abs(r.value - d.value) >= 0.0005) vals.push({ id: d.id, value: r.value });
      }
      if (!vals.length) { toast("Keine geänderten Werte."); return; }
      await sendParam(vals);   // sperrt und entsperrt die Tabelle selbst (tableLock), auch beim Senden aus dem Viewer
    }
    if (edit) tableLock = on => { btn.disabled = on; inputs.forEach(([, inp]) => { inp.disabled = on; }); };
    const rows = list.map(d => {
      const old = typeof d.value !== "number" && ("measured" in d || "nominal" in d);   // alte Form: measured/nominal, nie editierbar
      const val = typeof d.value === "number" ? d.value : typeof d.nominal === "number" ? d.nominal : null;
      let cell = h("td", { class: "num", style: { fontWeight: 600 } }, val === null ? "–" : num(val, 2));
      if (edit && d.editable && typeof d.value === "number") {
        const inp = h("input", { class: "input mono dimin", inputmode: "decimal", value: de(d.value), "aria-label": `${d.id} ${d.label || ""}`,
          onclick: e => e.stopPropagation(), onkeydown: e => { if (e.key === "Enter") { e.preventDefault(); send(inp); } } });
        inputs.push([d, inp]);
        cell = h("td", { class: "num" }, inp);
      }
      const zustand = old ? (typeof d.measured === "number" ? `gemessen ${num(d.measured, 2)}` : "") : dimState(d);
      const hl = hasAnchors(d);
      return h("tr", { title: d.note || "", style: hl ? { cursor: "pointer" } : {}, tabindex: hl ? "0" : null, role: hl ? "button" : null,
        onclick: () => viewer?.highlight(d.id), onkeydown: e => { if (e.key === "Enter" && e.target === e.currentTarget) viewer?.highlight(d.id); } },
        h("td", { class: "mono" }, d.id || ""), h("td", {}, d.label || "", d.note ? h("div", { class: "xs muted" }, d.note) : null),
        h("td", { class: "small" }, groupText(d.group)), cell, h("td", { class: "small" }, zustand));
    });
    return h("section", { class: "card", style: { gap: "10px" } }, h("h2", {}, "Maße im Modell"),
      h("table", { class: "t" }, h("thead", {}, h("tr", {}, h("th", {}, "ID"), h("th", {}, "Merkmal"), h("th", {}, "Gruppe"),
        h("th", { style: { textAlign: "right" } }, "Wert"), h("th", {}, "Zustand"))), h("tbody", {}, rows)),
      inputs.length ? h("div", { class: "chips" }, btn, h("span", { class: "xs muted" }, `Enter im Feld übernimmt nur diesen Wert · höchstens ${MAX_PARAM} auf einmal`))
        : V.version !== J.current_version && list.some(d => d.editable) ? h("span", { class: "xs muted" }, LOCK_VER) : null);
  }

  function draw3d(panel, V) {
    view3Used = true;
    const keep = view3?.version === V.version ? view3 : null;   // gleiche Version: Viewer (und WebGL-Kontext) behalten
    if (!keep) dropViewer();
    const box = keep ? keep.box : h("div", { class: "viewer" });
    const viewBtns = {};
    const vb = (k, t) => (viewBtns[k] = h("button", { "aria-pressed": String(k === "iso"), onclick: () => { viewer?.setView(k); Object.entries(viewBtns).forEach(([q, b]) => b.setAttribute("aria-pressed", String(q === k))); } }, t));
    const dims = Array.isArray(V.meta?.dimensions) ? V.meta.dimensions : [];
    const loadSel = () => { try { return dimSel(localStorage.getItem("dims.groups")); } catch { return { ...DEFAULT_SEL }; } };   // Speicher gesperrt
    let sel = loadSel();
    const setSel = (k, on) => {
      sel = { ...sel, [k]: on };
      try { localStorage.setItem("dims.groups", JSON.stringify(sel)); } catch { /* */ }
      viewer?.setGroups(sel);
    };
    const cb = (k, t) => h("label", { class: "check small" }, h("input", { type: "checkbox", checked: sel[k], onchange: e => setSel(k, e.target.checked) }), t);
    const pending = J.pending_param || [];
    const conclBtn = () => { const b = h("button", { class: "btn claude sm", disabled: conclOff(),
      title: !S.status?.ai ? "KI nicht eingerichtet" : pending.length ? "Die KI leitet abhängige Maße aus den nachgemessenen Werten ab" : "Erst einen Wert am Modell eintragen",
      onclick: conclude }, icon("sparkle", 14), "Schlüsse ziehen"); conclBtns.push(b); return b; };
    const bar = h("div", { class: "dimbar", role: "group", "aria-label": "Maße anzeigen" },
      DIM_GROUPS.map(([k, t]) => cb(k, t)), cb("annahmen", "Annahmen & nachgemessen"), cb("nur_annahmen", "Nur Annahmen"), h("span", { style: { flex: "1" } }), conclBtn());
    const ids = V.trigger === "param" && Array.isArray(V.meta?.param_ids) ? V.meta.param_ids : [];
    const btext = V.version === J.current_version ? paramBanner(pending.filter(p => ids.includes(p.id))) : "";
    const banner = btext ? h("div", { class: "note info", role: "status" }, icon("info"), h("span", { style: { flex: "1" } }, btext), conclBtn()) : null;
    const noProject = !J.project_id && dims.some(d => d.editable) ? h("span", { class: "xs muted" }, "Ohne Projekt – der Wert wird nicht gemerkt.") : null;
    if (keep) {
      clear(panel, bar, banner, noProject, box, keep.views3);
      viewer?.setLocked(!canEdit(V), lockText());   // noch ladend: setzt die Sperre nach dem Laden (unten)
      return;
    }
    const views3 = h("div", { class: "views3" });
    view3 = { version: V.version, box, views3 };
    box.append(
      h("div", { class: "vtl" }, h("div", { class: "seg" }, vb("iso", "Iso"), vb("top", "Oben"), vb("front", "Vorn"), vb("side", "Seite"))),
      h("div", { class: "vtr" },
        h("label", { class: "check" }, h("input", { type: "checkbox", onchange: e => viewer?.setEdges(e.target.checked) }), "Kanten"),
        h("label", { class: "check" }, h("input", { type: "checkbox", onchange: e => viewer?.setSection(e.target.checked) }), "Schnitt")),
      h("span", { class: "vbl" }, "Ziehen = drehen · Rad / Pinch = zoomen · Rechtsklick oder zwei Finger = verschieben · Klick auf ein Maß = Wert eintragen"),
      h("div", { class: "vbr", "aria-label": "Zoom" },
        h("button", { class: "iconbtn", "aria-label": "Verkleinern", onclick: () => viewer?.zoom(0.8) }, icon("minus")),
        h("button", { class: "iconbtn", "aria-label": "Vergrößern", onclick: () => viewer?.zoom(1.25) }, icon("plus")),
        h("button", { class: "btn sm", onclick: () => viewer?.fit() }, "Einpassen"),
        h("button", { class: "iconbtn", "aria-label": "Vollbild", onclick: () => document.fullscreenElement ? document.exitFullscreen() : box.requestFullscreen?.() }, icon("full"))));
    clear(panel, bar, banner, noProject, box, views3);
    const loading = h("div", { class: "empty", style: { position: "absolute", inset: 0, justifyContent: "center" } }, h("span", { class: "spin" }), "3D-Modell wird geladen …");
    box.append(loading);
    import("./viewer.js").then(({ createViewer }) => createViewer(box, `/api/jobs/${id}/v/${V.version}/model.stl`, dims, { onSubmit: sendParam })).then(v => {
      loading.remove();
      if (!box.isConnected || view3?.box !== box) { v.dispose(); return; }
      viewer = v;
      v.setGroups(loadSel());   // Schalter einer neu gezeichneten Leiste koennen sich waehrend des Ladens geaendert haben
      v.setLocked(!canEdit(V), lockText());
      const snaps = v.snapshots(["top", "front", "side"]);
      clear(views3, [["top", "Oben"], ["front", "Vorn"], ["side", "Seite"]].map(([k, t]) => h("figure", { onclick: () => viewBtns[k].click() },
        h("img", { src: snaps[k], alt: `${t}-Ansicht` }), h("figcaption", {}, t))));
    }).catch(e => { clear(loading, icon("warn"), `3D-Ansicht nicht verfügbar: ${e.message}`); });
  }

  async function drawOverlay(panel, V) {
    const photos = (await ensureProjectPhotos(J.project_id)).filter(p => p.files.includes("rect"));
    if (!photos.length) { clear(panel, h("p", { class: "hint" }, "Kein entzerrtes Foto im Projekt.")); return; }
    const outline = await api(`/api/jobs/${id}/v/${V.version}/outline.json`);
    let ph = photos.find(p => p.view === "top") || photos[0];
    const st = { x: 0, y: 0, rot: 0, mirror: false };
    const cv = h("canvas");
    const wrap = h("div", { class: "overlay-wrap" }, cv);
    const sel = h("select", { class: "input", style: { width: "auto", minHeight: "38px" } }, photos.map(p => h("option", { value: p.id, selected: p === ph }, p.filename)));
    const rot = h("input", { type: "range", min: -180, max: 180, step: 0.5, value: 0, style: { flex: 1 }, "aria-label": "Drehung" });
    const rotTxt = h("span", { class: "mono small", style: { minWidth: "52px" } }, "0°");
    const ctrl = h("div", { class: "chips" }, h("label", { class: "chips small" }, "Foto", sel),
      h("label", { class: "chips small", style: { flex: "1 1 220px" } }, "Drehung", rot, rotTxt),
      h("button", { class: "btn sm", onclick: () => { st.rot = (st.rot + 90) % 360; if (st.rot > 180) st.rot -= 360; rot.value = st.rot; paint(); } }, "+90°"),
      h("label", { class: "check small" }, h("input", { type: "checkbox", onchange: e => { st.mirror = e.target.checked; paint(); } }), "Spiegeln"),
      h("button", { class: "btn sm", onclick: () => { center(); paint(); } }, "Zentrieren"));
    clear(panel, ctrl, wrap, h("p", { class: "hint" }, "Umriss des Modells (Draufsicht, 1:1) mit der Maus oder dem Finger auf das Bauteil schieben. Wo Umriss und Kante auseinanderliegen, stimmt das Modell nicht."));
    let img = null, loadSeq = 0, frame = 0;
    const pxmm = () => ph.rect.pxmm;
    const all = outline.flatMap(o => o.exterior);
    const bx = [Math.min(...all.map(p => p[0])), Math.max(...all.map(p => p[0]))], by = [Math.min(...all.map(p => p[1])), Math.max(...all.map(p => p[1]))];
    const oc = [(bx[0] + bx[1]) / 2, (by[0] + by[1]) / 2];
    function center() { st.x = ph.rect.w_mm / 2; st.y = ph.rect.h_mm / 2; }
    async function load() {  // nur das zuletzt gewaehlte Foto zeigen; bis es da ist, nicht auf das alte zeichnen
      const n = ++loadSeq, im = new Image();
      img = null; im.src = `/api/photos/${ph.id}/rect.jpg`;
      try { await im.decode(); } catch {
        if (n === loadSeq && cv.isConnected) { cv.getContext("2d").clearRect(0, 0, cv.width, cv.height); toast("Foto konnte nicht geladen werden", "err"); }
        return;
      }
      if (n !== loadSeq || !cv.isConnected) return;
      img = im; cv.width = im.naturalWidth; cv.height = im.naturalHeight; center(); paint();
    }
    function tr([x, y]) {
      let X = x - oc[0], Y = y - oc[1];
      if (st.mirror) X = -X;
      const a = st.rot * Math.PI / 180;
      const rx = X * Math.cos(a) - Y * Math.sin(a), ry = X * Math.sin(a) + Y * Math.cos(a);
      return [(st.x + rx) * pxmm(), (ph.rect.h_mm - (st.y + ry)) * pxmm()];
    }
    const paintSoon = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(); }); };
    function paint() {
      if (!img) return;
      rotTxt.textContent = `${num(st.rot, 1)}°`;
      const c = cv.getContext("2d");
      c.drawImage(img, 0, 0);
      c.lineWidth = Math.max(2, cv.width / 700); c.strokeStyle = "#C2410C"; c.fillStyle = "rgba(194,65,12,.12)";
      for (const o of outline) {
        c.beginPath();
        for (const ring of [o.exterior, ...(o.holes || [])]) ring.forEach((p, i) => { const q = tr(p); i ? c.lineTo(...q) : c.moveTo(...q); });
        c.fill("evenodd"); c.stroke();
      }
    }
    let drag = null;
    cv.addEventListener("pointerdown", e => {
      cv.setPointerCapture(e.pointerId);
      drag = { x: e.clientX, y: e.clientY, sx: st.x, sy: st.y, k: cv.width / cv.getBoundingClientRect().width / pxmm() };
    });
    cv.addEventListener("pointermove", e => {
      if (!drag) return;
      st.x = drag.sx + (e.clientX - drag.x) * drag.k; st.y = drag.sy - (e.clientY - drag.y) * drag.k; paintSoon();
    });
    const endDrag = () => { drag = null; };
    cv.addEventListener("pointerup", endDrag);
    cv.addEventListener("pointercancel", endDrag);
    cv.style.cursor = "move"; cv.style.touchAction = "none";
    rot.addEventListener("input", () => { st.rot = Number(rot.value); paintSoon(); });
    sel.addEventListener("change", () => { ph = photos.find(p => p.id === Number(sel.value)); load(); });
    load();
  }

  function iterateBox() {
    if (!J.versions.length) {
      return h("section", { class: "card" }, h("h2", {}, "Noch keine Version"), h("p", {}, J.error || ""), h("pre", { class: "log" }, (J.log || []).map(l => `${dt(l.ts)}  ${l.msg}\n`)),
        h("div", {}, h("a", { class: "btn primary", href: "/cad" }, "Neuen Auftrag anlegen")));
    }
    const ta = h("textarea", { id: "chg", class: "input", rows: 3, maxlength: 4000, disabled: readOnly, placeholder: "z. B. Lagersitz als Sackloch 7 mm tief, Rest 1 mm Boden" });
    const next = Math.max(...J.versions.map(v => v.version)) + 1;
    const us = S.status?.usage || {};
    const btn = h("button", { class: "btn primary", disabled: readOnly || running(), onclick: async () => {
      if (!ta.value.trim()) { ta.focus(); toast("Bitte die Änderung beschreiben", "err"); return; }
      btn.disabled = true;
      if (!await submitIterate(ta.value)) btn.disabled = false;
    } }, `v${next} erzeugen`);
    return h("section", { class: "card", "aria-labelledby": "it-h" },
      h("div", { class: "row", style: { gap: "32px" } },
        h("div", { style: { flex: "1 1 280px", display: "flex", flexDirection: "column", gap: "10px" } },
          h("h2", { id: "it-h" }, "Verlauf"),
          h("ol", { class: "vers" }, J.versions.map(v => h("li", { "aria-current": String(v.version === ver),
            onclick: () => { if (v.status === "running") return; ver = v.version; draw(); } },   // laufende Version: noch nichts zu zeigen
            h("span", { class: "vn" }, `v${v.version}`),
            h("span", { class: "small" }, v.trigger === "create" ? "Erster Entwurf" : v.trigger === "autofix" ? "Automatische Korrektur"
              : v.trigger === "param" ? `Neuaufbau: ${v.request_text || ""}` : `Änderung: ${(v.request_text || "").slice(0, 80)}`,
              h("span", { class: "muted" }, ` · ${v.status === "ok" ? "geprüft" : v.error ? `Fehler (${v.error.type})` : v.status}`)),
            h("span", { class: "xs muted" }, v.seconds ? `${num(v.seconds, 0)} s` : "")))),
          h("a", { href: "/cad", class: "small" }, "Neuen Auftrag anlegen")),
        h("div", { style: { flex: "2 1 420px", display: "flex", flexDirection: "column", gap: "10px" } },
          h("label", { for: "chg", style: { fontWeight: 600 } }, "Änderung anfordern"), ta,
          h("div", { class: "chips" }, h("span", { class: "xs muted" }, "Vorschläge"),
            (CHIPS[procOf(J)] || []).map(t => h("button", { class: "chip", type: "button", disabled: readOnly, onclick: () => { ta.value = ta.value ? `${ta.value.trim()}\n${t}` : t; ta.focus(); } }, t)),
            h("span", { style: { flex: 1 } }), btn),
          h("span", { class: "xs muted" }, `Jede Änderung zählt als CAD-Lauf · ${us.quota == null ? `${us.used ?? 0} diesen Monat` : `${us.used} von ${us.quota} diesen Monat`}`))));
  }

  draw();
  if (running()) startPoll();
}

// ------------------------------------------------------------------ Hilfen
let photoCache = null;  // nur das zuletzt angesehene fremde Projekt: { pid, photos }
async function ensureProjectPhotos(pid) {
  if (!pid) return [];
  if (S.project?.id === pid) return S.project.photos;
  if (photoCache?.pid !== pid) photoCache = { pid, photos: (await api(`/api/projects/${pid}`)).photos };
  return photoCache.photos;
}
function slug(s) { return (s || "modell").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "modell"; }
function dlLink(href, ext, cls, name, sub) {
  return h("a", { class: "dl", href, download: name }, h("span", { class: `ext ${cls}` }, ext), h("span", { style: { minWidth: 0 } }, h("span", { class: "fn" }, name), h("span", { class: "small muted" }, sub)));
}
function stateIcon(st) {
  const map = { ok: ["check", "var(--ok)"], warn: ["warn", "#B07800"], fail: ["x", "var(--err)"], info: ["info", "var(--accent)"] };
  const [ic, col] = map[st] || map.info;
  const e = icon(ic, 18); e.style.color = col; return e;
}
function errorBox(e) {
  return h("div", { class: "note err", style: { flexDirection: "column", gap: "4px" } },
    h("strong", {}, `${e.type}${e.line ? ` in Zeile ${e.line}` : ""} (${e.stage})`),
    e.code ? h("code", { class: "small" }, e.code) : null, h("span", { class: "small", style: { whiteSpace: "pre-wrap" } }, String(e.message || "").slice(0, 1200)));
}
function codeView(code, errLine) {
  const pre = h("pre", { class: "codebox" });
  (code || "").replace(/\n$/, "").split("\n").forEach((ln, i) => pre.append(h("div", { class: i + 1 === errLine ? "err" : "" }, h("span", { class: "ln" }, i + 1), ln || " ")));
  return pre;
}
async function copy(t) { if (await copyText(t)) toast("Kopiert", "ok"); else toast("Kopieren nicht möglich", "err"); }
