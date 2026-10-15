# Stufe B: Bemaßung am Modell – Design

Stand 15.10.2026. Vorgänger: Stufe A (`2026-10-15-unteransicht-pruefung-material-design.md`, ausgeliefert als main b3723a6 + Nacharbeit 28cf239).

## Ziel

Im 3D-Viewer eines Auftrags erscheinen die Maße des Modells als Bemaßungslinien, gruppenweise ein- und ausschaltbar.
Ein Klick auf ein Maß öffnet ein Eingabefeld; der eingetragene Messschieberwert wird sofort in das Modell eingesetzt
(neue Version ohne KI-Aufruf) und am Projekt als „Messschieber am Modell“ gemerkt. Auf Klick zieht die KI aus allen
neuen Werten Schlüsse auf abhängige Maße. Die Arbeit gilt Snap2CAD als Produkt; das Testwerkstück (Kühlkörperblock)
dient nur der Abnahme.

Nutzerentscheidungen (Marc, 15.10.2026): sofort parametrisch, KI folgert gebündelt auf Klick mit Hinweis; alle Maße
der KI mit Gruppen-Schaltern; gelernte Werte gelten projektweit; Textur/GLB wird Stufe C.

## Begriffe

- **Maß (dimension):** ein Eintrag der KI-Liste `dimensions` zu einer Version. Hat eine stabile `id` (M1, M2, …),
  eine Konstante im Code (`var`) und zwei Ankerpunkte im Modellraum.
- **Version:** wie bisher eine Zeile in `job_versions`. Neuer Auslöser (`trigger`) `param` für den parametrischen
  Neuaufbau ohne KI.
- **Gelernter Wert:** ein vom Nutzer eingetragener Messschieberwert, am Projekt gespeichert (Tabelle `model_dims`).

## §1 Maße aus der KI

### Antwortformat (`ai.CAD_SYSTEM`)

Der JSON-Block der Antwort enthält `dimensions` als Liste von Objekten:

```json
{"id": "M3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0,
 "assumed": true, "a": [0, 0, 0], "b": [0, 0, 75.0], "derived_from": null, "note": "Annahme: Höhe ≈ Breite"}
```

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `id` | `M<n>` | ja | stabil über alle Versionen eines Auftrags |
| `label` | str ≤ 60 | ja | Bezeichnung |
| `group` | `aussen` \| `bohrung` \| `tiefe` \| `fase` \| `platte` \| `sonst` | ja | Gruppe für die Schalter |
| `var` | `[A-Z][A-Z0-9_]{1,30}` | ja | Konstante im Code, genau eine Zeile `VAR = <Zahl>` auf Modulebene |
| `value` | Zahl > 0 | ja | im Code verwendeter Wert (mm) |
| `assumed` | bool | ja | `true` = Annahme ohne Messgrundlage |
| `a`, `b` | je 3 Zahlen (mm) | ja | Ankerpunkte im Modellraum (Koordinaten wie `bbox_min`/`orientation`) |
| `derived_from` | `M<n>` oder null | nein | von welchem Maß die KI diesen Wert abgeleitet hat |
| `note` | str ≤ 120 | nein | Begründung |

Neue Regeln im `CAD_SYSTEM`:

11. Jedes Maß, das die Form bestimmt (Außenmaße, Bohrungsdurchmesser, Tiefen, Fasen, Plattendicke, Rasterabstände),
    steht als benannte Konstante `NAME = Zahl` am Anfang des Codes und als Eintrag in `dimensions` mit `var = NAME`.
    Keine zwei Einträge teilen eine Konstante. `a` und `b` liegen auf dem Modell, so dass ihr Abstand `value` ist
    (bei Durchmessern: zwei gegenüberliegende Punkte des Kreises; bei Tiefen: Beginn und Ende der Bohrung).
12. Bei Änderungswünschen und Schlussfolgerungen behalten bestehende Maße `id` und `var`; neue Maße bekommen neue
    IDs. Ein Maß, dessen Wert aus einem nachgemessenen Maß folgt, trägt `derived_from` und eine `note`.

Die bisherigen Felder `measured`/`nominal` entfallen; `measured` wird, wenn vorhanden, in `note` übernommen
(Rückwärtskompatibilität alter Versionen in `parse_cad`: fehlende Pflichtfelder → Eintrag ohne Anker, siehe §1.3).

### Serverseitige Prüfung (`ai.parse_cad` → `jobs._run`)

`ai.parse_cad` liefert `meta["dimensions"]` als bereinigte Liste: Einträge ohne gültige `id`/`var`/`value` werden
verworfen; `group` außerhalb der Liste → `sonst`; `assumed` fehlt → `false`. Nach dem Parsen prüft `jobs._run`
jede Konstante gegen den Code mit `re.search(rf"^{var}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(#.*)?$", code, re.M)`; Treffer
→ `editable: true`, sonst `editable: false` (Linie ohne Eingabe). Weicht die Zahl im Code um mehr als 0,01 vom `value`
ab, gilt der Codewert, und `note` bekommt „Wert aus dem Code“.

### Alte Versionen

Versionen ohne Anker (`a`/`b` fehlen) zeigen nur die drei Hauptmaße der Bounding-Box wie bisher. Die Maßtabelle unter
dem Viewer zeigt die Liste trotzdem.

## §2 Parametrischer Neuaufbau

`POST /api/jobs/{jid}/param` – Body `{"values": [{"id": "M3", "value": 45.0}]}` (1–20 Einträge, Zahl > 0, ≤ 5000).

Ablauf (in `jobs.param(user, job, values)`):

1. Unter `jobs._lock`: Auftrag muss `done`/`failed` sein (sonst 409 „Der Auftrag läuft noch.“); Basis ist
   `current_version` (sonst 409 „keine Version“). Kein `_check_quota`, kein `_check_ready` auf die KI; die Sandbox
   muss laufen (sonst 503 wie beim Auftrag).
2. Für jede `id`: Maß in `meta["dimensions"]` der Basisversion mit `editable` suchen (sonst 400 „Maß M9 ist nicht
   editierbar“); Zeile `VAR = alt` im Code durch `VAR = neu` ersetzen (Zahl mit bis zu 3 Nachkommastellen, Kommentar
   bleibt); `meta["dimensions"][i]` bekommt `value = neu`, `assumed = false`, `user_set = true`, `derived_from = null`.
3. Neue Version mit `trigger = "param"`, `request_text = "M3 = 45 mm"` (Komma-Liste), `claude_text = ""`, Code und Meta
   wie oben; `sandbox.run`; Status/Checks/Result wie in `_run`, aber **kein Autofix** und kein KI-Aufruf. Bei Fehler
   bleibt `current_version` die Basis; `log`: „Version n: Neuaufbau mit M3 = 45 fehlgeschlagen – …“.
4. Gelernte Werte (§4) werden **vor** dem Sandbox-Lauf gespeichert (der Wert ist gemessen, unabhängig vom Erfolg).
5. Die Gesprächs-`messages` des Auftrags bekommen eine Nutzerzeile „Parametrisch geändert: M3 = 45 mm (Version n)“
   ohne Antwort, damit spätere KI-Änderungen den Stand kennen; der Code der Basis für `iterate` ist wie bisher der
   Code der `current_version`.

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
  `Sonstige` als Kontrollkästchen, dazu `Nur Annahmen` (blendet alle Gruppen aus bis auf Maße mit `assumed`). Standard:
  Außenmaße und Annahmen ein, Rest aus; die Wahl liegt in `localStorage` (`dims.groups`).
- Klick auf ein Label: Label wird zum Eingabefeld (`<input inputmode="decimal">`, vorbelegt mit dem Wert); Enter
  sendet §2 (nur dieses Maß), Esc bricht ab; während des Laufs ist das Feld gesperrt und der Auftragsstatus zeigt
  „Neuaufbau mit M3 = 45 …“. Nicht editierbare Maße (`editable: false`) zeigen beim Klick den Hinweis „Dieses Maß ist
  im Code keine Konstante – Änderungswunsch formulieren.“
- Maßtabelle unter dem Viewer (bestehende Tabelle `meta.dimensions`) bekommt Spalten Gruppe, Wert, Zustand
  (Annahme / nachgemessen / abgeleitet von …) und ein Eingabefeld je editierbarem Maß; Klick auf eine Zeile hebt die
  Linie im Viewer hervor (dicker, 1,5 s).
- Versionswechsel im Auftrag lädt die Maße der gewählten Version.

## §4 Lernen (gelernte Werte am Projekt)

Neue Tabelle `model_dims`:

```sql
CREATE TABLE IF NOT EXISTS model_dims(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, label TEXT NOT NULL, label_norm TEXT NOT NULL,
  grp TEXT NOT NULL, value REAL NOT NULL, job_id INTEGER, dim_id TEXT, note TEXT, created_at TEXT NOT NULL,
  UNIQUE(project_id, label_norm))
```

- `label_norm` = Bezeichnung klein, ohne Mehrfach-Leerzeichen, ohne Satzzeichen. Ein neuer Wert mit gleicher
  `label_norm` ersetzt den alten (UPSERT).
- Beim Param-Aufruf (§2) wird je Maß ein Eintrag geschrieben (`job_id`, `dim_id` = M-Nummer).
- `jobs.measurement_table` bekommt nach der bisherigen Tabelle einen Abschnitt
  `## Messschieber am Modell (verbindlich)` mit Zeilen `- Höhe Block: 45 mm (Gruppe außen, gemessen am Auftrag 7)`;
  er geht in jede Auftragsnachricht, jeden Änderungswunsch und jede Prüfung. `CAD_SYSTEM` Regel 11 ergänzt:
  „Werte aus „Messschieber am Modell“ sind verbindlich und nie Annahmen.“
- Oberfläche: Im Viewer zeigt ein Maß, dessen `label_norm` einen gelernten Wert hat, „✓ nachgemessen“ im Label-Titel;
  auf der Messseite erscheint unter der Maßtabelle eine Liste „Messschieber am Modell“ mit Löschen je Zeile
  (`DELETE /api/projects/{pid}/model-dims/{id}`), `GET /api/projects/{pid}` liefert `model_dims`.
- CSV-Export der Messseite bekommt die gelernten Werte als Zeilen mit Quelle „Modell“.

## §5 Schlüsse ziehen

- Knopf „Schlüsse ziehen“ über dem Viewer, aktiv, wenn seit der letzten KI-Version (`trigger` ≠ `param`) mindestens
  ein `user_set`-Maß dazugekommen ist (Vergleich der Versionen im Client).
- Aufruf: `POST /api/jobs/{jid}/iterate` mit generiertem Text:
  `Nachgemessen mit dem Messschieber: M3 Höhe Block = 45 mm (vorher Annahme 75); M7 … . Leite daraus abhängige Maße
  ab (Tiefen, Dicken, Abstände, die an diesen Maßen hängen), trage bei jedem geänderten Maß derived_from und eine
  kurze Begründung ein und ändere sonst nichts.` – also der bestehende Änderungsweg, Kontingent wie bisher.
- Hinweis-Banner im Viewer nach einem Param-Lauf, wenn das Maß `assumed` war oder der neue Wert um mehr als 10 % vom
  alten abweicht: „45 mm ersetzt eine Annahme (75 mm) – Schlüsse auf abhängige Maße ziehen?“ mit dem Knopf.

## §6 Fehlerfälle und Grenzen

- KI liefert keine oder ungültige Anker → nur Hauptmaße (§1.3), Tabelle editierbar, wo `editable`.
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
| B1 | `parse_cad` übernimmt gültige Maße, verwirft Einträge ohne `var`/`value`, ergänzt `group=sonst`, `assumed=false`; `editable` nach Codeprüfung | `pytest tests/test_dims.py -k parse` |
| B2 | Param-Ersetzung: `VAR = 75.0  # Kommentar` → `VAR = 45  # Kommentar`; mehrere Werte; nicht editierbares Maß → 400; laufender Auftrag → 409 | `pytest tests/test_dims.py -k param` |
| B3 | Param-Version ohne KI-Aufruf (Fake-Zähler bleibt), `trigger=param`, Meta mit `user_set`; Sandbox-Fehler → `failed`, Basis bleibt | `pytest tests/test_dims.py -k version` |
| B4 | Gelernte Werte: UPSERT je `label_norm`, in `measurement_table` als Abschnitt, in Auftrag/Prüfung/Änderung enthalten, Löschen | `pytest tests/test_dims.py -k lernen` |
| B5 | Viewer-Geometrie: Hilfslinienversatz, Labelposition, Gruppenfilter (reine Funktionen in `geom.js`) | `node --test tests/js/dims.test.mjs` |
| B6 | Browser: Linien sichtbar, Gruppen schalten, Klick → Eingabe → neue Version (Testmodus), Banner, „Schlüsse ziehen“ erzeugt Änderungswunsch mit den Werten, Konsole ohne Fehler | Playwright `pw/stufe_b.mjs` |
| B7 | Alte Version ohne Anker → nur Hauptmaße, keine Konsolenfehler | Playwright |
| B8 | Abnahme auf der DS918+ mit dem Kühlkörperblock: Höhe und Bohrungs-Ø nachmessen und eintragen (Marc), Modell folgt in < 30 s, „Schlüsse ziehen“ passt Bohrtiefe/Plattendicke mit Begründung an | Protokoll |

## Auslieferung

Branch `bemassung-am-modell` → PR → CI grün → Merge → CI auf `main` → DS918+ mit Sicherung (`backup-data-<datum>.tgz`
bei gestoppten Containern) → `compose pull && up -d` → Gesundheit → B8.
