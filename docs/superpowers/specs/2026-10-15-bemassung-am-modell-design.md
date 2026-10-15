# Stufe B: Bemaßung am Modell – Design

Stand 15.10.2026. Vorgänger: Stufe A (`2026-10-15-unteransicht-pruefung-material-design.md`, ausgeliefert als main
b3723a6 + Nacharbeit 28cf239).

## Ziel

Im 3D-Viewer eines Auftrags erscheinen die Maße des Modells als Bemaßungslinien, gruppenweise ein- und ausschaltbar.
Ein Klick auf ein Maß öffnet ein Eingabefeld; der eingetragene Messschieberwert wird sofort in das Modell eingesetzt
(neue Version ohne KI-Aufruf) und am Projekt als „Messschieber am Modell“ gemerkt. Auf Klick zieht die KI aus allen
neuen Werten Schlüsse auf abhängige Maße. Die Arbeit gilt Snap2CAD als Produkt; das Testwerkstück (Kühlkörperblock)
dient nur der Abnahme.

Nutzerentscheidungen (Marc, 15.10.2026): sofort parametrisch, KI folgert gebündelt auf Klick mit Hinweis; alle Maße
der KI mit Gruppen-Schaltern; gelernte Werte gelten projektweit; Textur/GLB wird Stufe C. Preflight-Gabelungen (Marc,
15.10.2026): Modellmaße haben einen eigenen Nummernkreis D1, D2 … mit Verweis `ref` auf die Foto-Messung; Anker werden
aus dem Code berechnet (`DIM_ANCHORS`, Regel 13), Strecken nur als Rückfall; nicht übernommene gelernte Werte lösen eine
Warnung aus, kein automatisches Zurückschreiben.

## Begriffe

- **Maß (dimension):** ein Eintrag der KI-Liste `dimensions` zu einer Version. Hat eine stabile `id` (D1, D2, …; die
  Foto-Messungen behalten M1, M2, …),
  eine Konstante im Code (`var`) und zwei Ankerpunkte im Modellraum.
- **Version:** wie bisher eine Zeile in `job_versions`. Neuer Auslöser (`trigger`) `param` für den parametrischen
  Neuaufbau ohne KI.
- **Gelernter Wert:** ein vom Nutzer eingetragener Messschieberwert, am Projekt gespeichert (Tabelle `model_dims`).

## §1 Maße aus der KI

### Antwortformat (`ai.CAD_SYSTEM`)

Der JSON-Block der Antwort enthält `dimensions` als Liste von Objekten:

```json
{"id": "D3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "ref": null,
 "assumed": true, "a": [0, 0, 0], "b": [0, 0, 75.0], "derived_from": null, "note": "Annahme: Höhe ≈ Breite"}
```

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `id` | `D<n>` | ja | stabil über alle Versionen eines Auftrags; eigener Nummernkreis, nie die M-Nummer einer Messung |
| `ref` | `M<n>` oder null | nein | Foto-Messung aus der Messtabelle, aus der der Wert stammt (für den Prüfpunkt „Kritische Maße übernommen“) |
| `label` | str ≤ 60 | ja | Bezeichnung |
| `group` | `aussen` \| `bohrung` \| `tiefe` \| `fase` \| `platte` \| `sonst` | ja | Gruppe für die Schalter |
| `var` | `[A-Z][A-Z0-9_]{1,30}` | ja | Konstante im Code, genau eine Zeile `VAR = <Zahl>` auf Modulebene |
| `value` | Zahl > 0 | ja | im Code verwendeter Wert (mm) |
| `assumed` | bool | ja | `true` = Annahme ohne Messgrundlage |
| `a`, `b` | je 3 Zahlen (mm) | nein | Rückfall-Anker im Modellraum, falls `DIM_ANCHORS` (Regel 13) fehlt; sonst kommen die Anker aus dem Code |
| `derived_from` | `D<n>` oder null | nein | von welchem Maß die KI diesen Wert abgeleitet hat |
| `note` | str ≤ 120 | nein | Begründung |

Neue Regeln im `CAD_SYSTEM`:

11. Jedes Maß, das die Form bestimmt (Außenmaße, Bohrungsdurchmesser, Tiefen, Fasen, Plattendicke, Rasterabstände),
    steht als benannte Konstante `NAME = Zahl` am Anfang des Codes und als Eintrag in `dimensions` mit `var = NAME`.
    Keine zwei Einträge teilen eine Konstante. Die Ankerpunkte stehen in `DIM_ANCHORS` (Regel 13) so, dass ihr
    Abstand `value` ist (bei Durchmessern: zwei gegenüberliegende Punkte des Kreises; bei Tiefen: Beginn und Ende der
    Bohrung); `a`/`b` im JSON sind optional und nur der Rückfall für Maße ohne Eintrag in `DIM_ANCHORS`. `ref` nennt
    die Messung der Messtabelle (M-Nummer), aus der der Wert stammt; Maße ohne Messgrundlage haben `ref: null`.
12. Bei Änderungswünschen und Schlussfolgerungen behalten bestehende Maße `id` und `var`; neue Maße bekommen neue
    IDs. Ein Maß, dessen Wert aus einem nachgemessenen Maß folgt, trägt `derived_from` und eine `note`. Hat das Projekt
    mehrere Teile, beginnt `label` mit der Teilnummer („T2 Dicke“).
13. Am Ende des Codes steht ein Dict `DIM_ANCHORS = {"D3": ((0, 0, 0), (0, 0, BLOCK_H)), …}` mit den Ankerpunkten
    jedes Maßes als Ausdrücke der Konstanten (Modellraum, mm; Punkte als Tupel von drei Zahlen). Fehlt ein Eintrag,
    gelten `a`/`b` aus dem JSON als Rückfall. (Bis hier Prompttext; das Folgende ist Vorgabe für den Läufer.) Der
    Läufer `web/app/runner/cad_runner.py` liest nach dem Ausführen `ns.get("DIM_ANCHORS")` und schreibt
    `dim_anchors` (`{id: [[x, y, z], [x, y, z]]}`, auf 4 Nachkommastellen gerundet) in `result.json`; `sandbox.py`
    bleibt unverändert, `_collect` reicht das Feld durch. `DIM_ANCHORS` ist optional. Aufgenommen werden höchstens
    200 Einträge mit Schlüssel `^D[0-9]{1,4}$`, deren Wert genau zwei Punkte ist; ein Punkt ist eine Folge von drei
    Werten oder ein Objekt mit `X`, `Y`, `Z` (build123d `Vector`), jeder Wert mit `float()` wandelbar und endlich.
    Ungültige Einträge werden übersprungen; ist `DIM_ANCHORS` kein dict oder wirft die Auswertung, fehlt
    `dim_anchors`. Die Auswertung steht in einem eigenen `try` außerhalb von Export und Prüfung und lässt den Lauf
    nie scheitern. Der Server filtert `dim_anchors` erneut; nur gefilterte Einträge werden gespeichert. So sitzen
    die Linien nach jedem Neuaufbau, auch nach §2, auf dem Modell.

Die bisherigen Felder `measured`/`nominal` entfallen im Antwortformat. Gespeicherte Versionen behalten ihre Meta
unverändert; `parse_cad` betrifft nur neue Antworten. Viewer und Tabelle lesen alte Einträge (ohne `var`/`a`/`b`) als
nicht editierbar und ohne Anker und zeigen `measured`/`nominal`, wo vorhanden (siehe „Alte Versionen“).

`jobs.compute_checks` (Prüfpunkt „Kritische Maße übernommen“) ordnet die Messung über `ref` zu und vergleicht `value`
statt `nominal` (für alte Versionen weiter `id` als M-Nummer und `nominal`); die Auftragstabelle in `cad.js` zeigt
statt Messwert/Nennmaß die Spalten Gruppe, Wert,
Zustand; `ai._fake_meta` und die Beispielzeile in `CAD_SYSTEM` bekommen das neue Format.

### Serverseitige Prüfung (`ai.parse_cad` → `jobs._run`)

`ai.parse_cad` liefert `meta["dimensions"]` als bereinigte Liste: Einträge ohne gültige `id` werden verworfen; fehlen
`var` oder `value`, bleibt der Eintrag als nicht editierbar ohne Anker (`value` = `nominal`, falls vorhanden). `group`
außerhalb der Liste → `sonst`; `assumed` fehlt → `false`; `ref` nur, wenn es eine Messung des Projekts mit dieser
M-Nummer gibt, sonst null. Doppelte `id` → nur der erste Eintrag bleibt. `derived_from` nur, wenn es die `id` eines
anderen Eintrags derselben Liste ist, sonst null. Anker setzt nicht `parse_cad`, sondern
`jobs._apply_anchors(meta, result)` nach jedem erfolgreichen Sandbox-Lauf (in `_run` und `param`, vor
`compute_checks`): je Maß zuerst `result["dim_anchors"][id]` (Regel 13), sonst `a`/`b` aus dem JSON. Sie gelten
nur, wenn beide Punkte je drei endliche Zahlen sind und ihr Abstand um höchstens max(0,1 mm; 1 %) vom Codewert
abweicht; sonst werden die Anker entfernt und das Maß erscheint nur in der Tabelle. Die geltenden Anker stehen
danach als `a`/`b` in der Meta, die zusammen mit `result` erneut in `job_versions` gespeichert wird; Viewer und
Tabelle lesen nur `a`/`b` der Meta. Nach dem Parsen prüft `jobs._run` jede Konstante gegen den Code mit
`re.search(rf"^{var}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(#.*)?$", code, re.M)`; Treffer → `editable: true`, sonst
`editable: false` (Linie ohne Eingabe). `editable: true` nur, wenn genau eine Zeile `^VAR\s*=` im Code steht und sie
dem Muster entspricht; bei mehreren Zeilen `editable: false` und `note` „Konstante mehrfach belegt“. Weicht die Zahl im
Code um mehr als 0,01 vom `value` ab, gilt der Codewert, und `note` bekommt „Wert aus dem Code“.

### Alte Versionen

Versionen ohne Anker (`a`/`b` fehlen) zeigen nur die drei Hauptmaße der Bounding-Box wie bisher. Die Maßtabelle unter
dem Viewer zeigt die Liste trotzdem.

## §2 Parametrischer Neuaufbau

`POST /api/jobs/{jid}/param` – Body `{"values": [{"id": "D3", "value": 45.0}]}` (1–20 Einträge, Zahl > 0, ≤ 5000).

Ablauf (in `jobs.param(user, job, values)`):

1. Unter `jobs._lock`: Auftrag darf nicht `queued`/`running` sein (sonst 409 „Der Auftrag läuft noch.“), wie bei
   `iterate`. Basis ist `current_version` (sonst 409 „keine Version“). Kein `_check_quota`, kein `_check_ready` auf
   die KI; die Sandbox muss laufen (sonst 503 wie beim Auftrag). Ein Konto mit gesperrtem CAD (`cad_quota` 0) bekommt
   403 „CAD ist für dieses Konto gesperrt.“. Grenzen statt Kontingent: höchstens ein laufender Neuaufbau je Nutzer
   und höchstens `PARAM_PER_HOUR` (30) Neuaufbauten je Nutzer und Stunde, sonst 429.
2. Für jede `id`: Maß in `meta["dimensions"]` der Basisversion mit `editable` suchen (sonst 400 „Maß D9 ist nicht
   editierbar“); Zeile `VAR = alt` im Code durch `VAR = neu` ersetzen (Zahl mit bis zu 3 Nachkommastellen, Kommentar
   bleibt); `meta["dimensions"][i]` bekommt `value = neu`, `assumed = false`, `user_set = true`, `derived_from = null`;
   `meta["param_ids"]` listet die geänderten D-Nummern (`["D3"]`), daraus lesen der Lauf, `pending_param` und der
   Viewer, welche Maße geändert wurden.
   Die Anker kommen nach dem Bau aus `dim_anchors` (Regel 13, über `jobs._apply_anchors`). Rückfall je Maß ohne
   Eintrag in `dim_anchors`: Ein geändertes Maß bekommt seine Anker entlang a→b auf den neuen Wert gestreckt; jedes
   andere Maß ohne Eintrag behält seine Anker und wird grau gestrichelt gezeichnet (`anchors_stale: true`), bis ein
   Lauf für dieses Maß einen Eintrag in `dim_anchors` liefert oder der nächste KI-Lauf es neu setzt; sein Label
   bleibt bedienbar. Maße mit Eintrag in `dim_anchors` sind nie `anchors_stale`.
3. Neue Version mit `trigger = "param"`, `request_text = "D3 = 45 mm"` (Komma-Liste), `claude_text = ""`, Code und Meta
   wie oben; `sandbox.run`; Status/Checks/Result wie in `_run`, aber **kein Autofix** und kein KI-Aufruf. Bei Fehler
   bleibt `current_version` die Basis; `log`: „Version n: Neuaufbau mit D3 = 45 fehlgeschlagen – …“.
   3a. Schritte 1–2, das Anlegen der Version (`_new_version`, Status `running`) und `status = queued` geschehen in
   einem Block unter `_lock`; der Sandbox-Lauf läuft über `_submit`/`_pool` mit Abbruch-Event, „Abbrechen“ wirkt wie
   bisher. Ende: `done` mit `current_version = n`, sonst `failed` mit unveränderter Basis.
4. Gelernte Werte (§4) werden **vor** dem Sandbox-Lauf gespeichert (der Wert ist gemessen, unabhängig vom Erfolg).
   Hat der Auftrag kein Projekt (`jobs.project_id` ist leer), läuft der Neuaufbau trotzdem; Schritt 4 entfällt, die
   Antwort ist `{"version": n, "learned": false}`, und der Viewer zeigt „Ohne Projekt – der Wert wird nicht gemerkt.“
5. Die Gesprächs-`messages` des Auftrags bekommen eine Nutzerzeile „Parametrisch geändert: D3 = 45 mm (Version n)“
   ohne Antwort, damit spätere KI-Änderungen den Stand kennen; der Code der Basis für `iterate` ist wie bisher der
   Code der `current_version`. (aufeinanderfolgende Nutzerzeilen fasst `ai._materialize` zusammen)

Antwort: `{"version": n}`; der Client pollt den Auftrag wie bisher.

## §3 Viewer (`web/static/js/viewer.js`, `cad.js`)

- `createViewer(box, url, dims)` bekommt die Maßliste. Je Maß mit Anker: Maßlinie a→b, zwei Hilfslinien senkrecht
  zur Linie (Versatz 8 % der Modellgröße, mindestens 2 mm) und ein Label (`<span class="dimlabel">`) in der Mitte mit
  Wert (1 Nachkommastelle, ohne Einheit) – Labels wie die heutigen Hauptmaß-Labels projiziert.
- Die drei Hauptmaße der Bounding-Box bleiben als Gruppe `aussen`-Rückfall nur, wenn kein Maß der Gruppe `aussen`
  Anker hat.
- Farben: Annahme (`assumed`) rot `#b42318`; vom Nutzer gesetzt (`user_set`) grün `#1a7f37`; abgeleitet
  (`derived_from`) blau gestrichelt; sonst blau `#1f6fb2` wie heute.
- Schalter über dem Viewer (statt „Hauptmaße“): Gruppen `Außenmaße`, `Bohrungen`, `Tiefen`, `Fasen`, `Platten`,
  `Sonstige` und `Annahmen` als Kontrollkästchen. Ein Maß ist sichtbar, wenn seine Gruppe an ist oder es `assumed` ist
  und `Annahmen` an ist. `Nur Annahmen` als Kontrollkästchen: wenn an, sind nur Maße mit `assumed` sichtbar, gleich
  welche Gruppe; aus → die Gruppenregel gilt wieder unverändert. Standard: `Außenmaße` und `Annahmen` an, Rest aus; die
  Wahl liegt in `localStorage` (`dims.groups`). Die Regel ist die reine Funktion `visibleDims(dims, sel)` in `geom.js`
  (B5). Vom Nutzer gesetzte Maße (`user_set`) gelten für die Sichtbarkeit wie Annahmen.
- Klick auf ein Label: Label wird zum Eingabefeld (`<input inputmode="decimal">`, vorbelegt mit dem Wert); Enter
  sendet §2 (nur dieses Maß, auch mit unverändertem Wert: das bestätigt eine Annahme als nachgemessen), Esc bricht
  ab; während des Laufs ist das Feld gesperrt und der Auftragsstatus zeigt
  „Neuaufbau mit D3 = 45 …“. Nicht editierbare Maße (`editable: false`) zeigen beim Klick den Hinweis „Dieses Maß ist
  im Code keine Konstante – Änderungswunsch formulieren.“ Labels editierbarer Maße tragen die Klasse `dimlabel edit`
  mit `pointer-events:auto; cursor:pointer`; Hauptmaß-Labels bleiben `pointer-events:none`, damit sie das Drehen nicht
  stören.
- Maßtabelle unter dem Viewer (bestehende Tabelle `meta.dimensions`) bekommt Spalten Gruppe, Wert, Zustand
  (Annahme / nachgemessen / abgeleitet von …) und ein Eingabefeld je editierbarem Maß; Klick auf eine Zeile hebt die
  Linie im Viewer hervor (dicker, 1,5 s). Ein Knopf „Werte übernehmen“ unter der Tabelle sendet alle geänderten Felder
  in einem Aufruf nach §2 (höchstens 20); Enter in einem Feld sendet nur dieses, auch unverändert („Annahme
  bestätigen“).
- Versionswechsel im Auftrag lädt die Maße der gewählten Version.

## §4 Lernen (gelernte Werte am Projekt)

Neue Tabelle `model_dims`:

```sql
CREATE TABLE IF NOT EXISTS model_dims(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label TEXT NOT NULL, label_norm TEXT NOT NULL,
  grp TEXT NOT NULL, value REAL NOT NULL, job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL, dim_id TEXT,
  note TEXT, created_at TEXT NOT NULL,
  UNIQUE(project_id, label_norm))
```

- `label_norm` = `" ".join(re.sub(r"[^\w]+", " ", label.casefold()).split())` (Buchstaben inkl. Umlauten und Ziffern
  bleiben, alles andere wird Trennzeichen). Ein neuer Wert mit gleicher `label_norm` ersetzt den alten (UPSERT).

Nach jedem KI-Lauf (`jobs._run`, nicht `param`) gilt für jedes Maß, dessen `label_norm` einen gelernten Wert hat:
weicht `value` höchstens 0,01 mm ab → `user_set = true`, `assumed = false`; sonst Prüfpunkt `model_dims`
„Messschieber am Modell übernommen“ mit Zustand `warn` und Detail „Höhe Block: 45 → 75“. Grün im Viewer heißt
„entspricht dem gelernten Wert“; der eigene Titel „✓ nachgemessen“ entfällt. Snap2CAD schreibt die Konstante nie
selbst auf den gelernten Wert zurück (Marc, 15.10.2026: warnen, nicht erzwingen).

- Beim Param-Aufruf (§2) wird je Maß ein Eintrag geschrieben (`job_id`, `dim_id` = D-Nummer).
- Ein Abschnitt `## Messschieber am Modell (verbindlich)` mit Zeilen
  `- Höhe Block: 45 mm (Gruppe außen, gemessen am Auftrag 7)` geht an die KI: `jobs.build_initial_message` hängt ihn
  nach der Messtabelle an (Erstauftrag und Prüfung), `jobs.measurement_table` bleibt unverändert (Vorschläge über
  `/suggest` bekommen den Abschnitt nicht); `_iterate_locked` hängt ihn an den Text jedes Änderungswunsches an, wenn
  das Projekt des Auftrags gelernte Werte hat. `CAD_SYSTEM` Regel 11 ergänzt:
  „Werte aus „Messschieber am Modell“ sind verbindlich und nie Annahmen.“
- `check.cad_hash` bezieht die gelernten Werte des Projekts ein; ein neuer oder gelöschter Messschieberwert macht die
  Prüfung veraltet.
- Oberfläche: Auf der Messseite erscheint unter der Maßtabelle eine Liste „Messschieber am Modell“ mit Löschen je Zeile
  (`DELETE /api/projects/{pid}/model-dims/{id}`), `GET /api/projects/{pid}` liefert `model_dims`.
- CSV-Export der Messseite bekommt die gelernten Werte als Zeilen mit Quelle „Modell“.

## §5 Schlüsse ziehen

- Knopf „Schlüsse ziehen“ über dem Viewer. `GET /api/jobs/{jid}` liefert `pending_param`: für jedes Maß, das in einer
  Version mit `trigger = param` und Status `done` nach der letzten Version mit `trigger` ≠ `param` gesetzt wurde,
  `{id, label, value, old, old_assumed}` – `value` aus der jüngsten Param-Version, `old`/`old_assumed` aus der letzten
  KI-Version. Fehlgeschlagene Param-Versionen zählen nicht. Der Knopf ist aktiv, wenn `pending_param` nicht leer ist;
  der Text des Änderungswunsches wird daraus gebaut.
- Aufruf: `POST /api/jobs/{jid}/iterate` mit generiertem Text:
  `Nachgemessen mit dem Messschieber: D3 Höhe Block = 45 mm (vorher Annahme 75); D7 … . Leite daraus abhängige Maße
  ab (Tiefen, Dicken, Abstände, die an diesen Maßen hängen), trage bei jedem geänderten Maß derived_from und eine
  kurze Begründung ein und ändere sonst nichts.` – also der bestehende Änderungsweg, Kontingent wie bisher.
- Hinweis-Banner im Viewer nach einem Param-Lauf, wenn das Maß `assumed` war oder der neue Wert um mehr als 10 % vom
  alten abweicht: „45 mm ersetzt eine Annahme (75 mm) – Schlüsse auf abhängige Maße ziehen?“ mit dem Knopf.

## §6 Fehlerfälle und Grenzen

- Weder `dim_anchors` noch gültige `a`/`b` → nur Hauptmaße („Alte Versionen“ (§1)), Tabelle editierbar, wo `editable`.
- Konstante fehlt im Code → `editable: false`, Hinweis beim Klick (§3).
- Sandbox-Fehler nach Param → Version `failed`, Basis bleibt aktuell, gelernter Wert bleibt (§2.4).
- Auftrag läuft → 409; Auftrag eines anderen Nutzers → 404 (`_own_job`).
- Mehr als 20 Werte je Aufruf → 422.
- Werte eines anderen Projekts werden nie gemischt (`project_id` am Auftrag).
- Alte Datenbanken: Migration legt `model_dims` an; `job_versions` braucht keine Spalte (Meta ist JSON).

## §7 Nicht im Umfang

Textur aus dem Original und GLB-Download (Stufe C); eigene Linien ziehen; Toleranzen/Passungen am Modell;
automatische KI-Folgerung ohne Klick; Bemaßung im Foto-Abgleich.

## §8 Abnahme

| Nr. | Prüfung | Nachweis |
|---|---|---|
| B1 | `parse_cad` übernimmt gültige Maße (D-Nummern, `ref` nur mit vorhandener Messung, doppelte `id` verworfen, `derived_from` nur auf eine `id` der Liste), behält Einträge ohne `var`/`value` als nicht editierbar, ergänzt `group=sonst`, `assumed=false`; `editable` nach Codeprüfung, mehrfach belegte Konstante → `editable: false`; `_apply_anchors`: Anker aus `dim_anchors` vor `a`/`b`, Abstandsprüfung, ungültige Anker entfernt, Meta erneut gespeichert | `pytest tests/test_dims.py -k "parse or anker"` |
| B2 | Param-Ersetzung: `VAR = 75.0  # Kommentar` → `VAR = 45  # Kommentar`; mehrere Werte; nicht editierbares Maß → 400; laufender Auftrag → 409 | `pytest tests/test_dims.py -k param` |
| B3 | Param-Version ohne KI-Aufruf (`monkeypatch` von `ai.call` mit Aufrufliste – Liste bleibt leer), `trigger=param`, Meta mit `user_set`, Anker nach dem Bau aus `dim_anchors` auf dem neuen Wert; ohne `dim_anchors`: geändertes Maß gestreckt, übrige `anchors_stale: true`; `pending_param`; Sandbox-Fehler → `failed`, Basis bleibt. Läufer: `DIM_ANCHORS` → `result.json["dim_anchors"]`; kein dict, `Vector`-Punkte, NaN, falscher Schlüssel, mehr als 200 Einträge → Lauf `ok`, nur gültige Einträge, kein `error.json` | `pytest tests/test_dims.py -k version` und `pytest tests/test_sandbox.py -k anchors` (braucht build123d; läuft in der CI über `web/requirements.txt`) |
| B4 | Gelernte Werte: UPSERT je `label_norm`, als Abschnitt über `build_initial_message` und `_iterate_locked`, in Auftrag/Prüfung/Änderung enthalten, nicht in `measurement_table`, Löschen | `pytest tests/test_dims.py -k lernen` |
| B5 | Viewer-Geometrie: Hilfslinienversatz, Labelposition, Gruppenfilter (reine Funktionen in `geom.js`) | `node --test tests/js/dims.test.mjs` |
| B6 | Browser: Linien sichtbar, Gruppen schalten, Klick → Eingabe → neue Version (Testmodus), Banner, „Schlüsse ziehen“ erzeugt Änderungswunsch mit den Werten, Konsole ohne Fehler; nach dem Neuaufbau liegen die geänderte und eine abhängige Linie am neuen Wert | Playwright-Skript im Scratchpad (wie Stufe A), gegen lokalen Server mit `AI_FAKE`; dafür liefert `ai._fake_meta` `dimensions` mit `var`, `group`, `a`, `b` zu den Fake-Konstanten (`LENGTH`, `WIDTH`, `THICKNESS`, `HOLE_D`, …), mindestens ein Maß mit `assumed: true`. `_FAKE_V1` und `_FAKE_V2` enden mit `DIM_ANCHORS` zu diesen Maßen (in `_FAKE_V2` wegen `.format` mit `{{ }}`); geprüft über `dim_anchors` der Param-Version. |
| B7 | Alte Version ohne Anker → nur Hauptmaße, keine Konsolenfehler | Playwright-Skript im Scratchpad (wie B6) |
| B8 | Abnahme auf der DS918+ mit dem Kühlkörperblock: Höhe und Bohrungs-Ø nachmessen und eintragen (Marc), Modell folgt in < 30 s bei freiem Pool, also ohne gleichzeitig laufenden anderen Auftrag (Feld `seconds` der Param-Version), „Schlüsse ziehen“ passt Bohrtiefe/Plattendicke mit Begründung an; nach dem Eintragen der Höhe liegen Höhen- und Bohrtiefenlinie auf dem Modell (Protokoll: `dim_anchors` der Param-Version, Endpunkt Höhe = Messwert ± 0,1 mm, und Bildschirmfoto) | Protokoll |

## Auslieferung

Branch `bemassung-am-modell` → PR → CI grün → Merge → CI auf `main` → DS918+ mit Sicherung (`backup-data-<datum>.tgz`
bei gestoppten Containern) → `compose pull && up -d` → Gesundheit → B8.
