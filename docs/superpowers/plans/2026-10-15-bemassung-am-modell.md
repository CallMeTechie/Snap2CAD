# Bemaßung am Modell – Umsetzungsplan (Stufe B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Im 3D-Viewer eines Auftrags erscheinen die Maße des Modells als schaltbare Bemaßungslinien; ein eingetragener Messschieberwert baut das Modell sofort ohne KI neu, wird am Projekt gelernt, und „Schlüsse ziehen“ lässt die KI abhängige Maße daraus ableiten.

**Architecture:** Drei Wellen auf dem Branch `bemassung-am-modell`. W1 (Tasks 1–6, Server): neues Maßformat in `ai.py` (D-Nummern, `ref`, `var`, Regeln 11–13, Testmodus mit `DIM_ANCHORS`), Ankerauswertung im Läufer, Tabelle `model_dims` mit Lernen und Abschnitt in der Messtabelle, Anker/Editierbarkeit/Prüfpunkt in `jobs._run`, parametrischer Neuaufbau `jobs.param` mit Endpunkt und `pending_param`, gelernte Werte in Prüfsumme, Projekt-API und CSV. W2 (Tasks 7–10, Oberfläche): reine Funktionen in `geom.js`, Viewer mit Linien, Gruppen und Eingabe, Auftragsseite mit Tabelle, Banner und „Schlüsse ziehen“, Liste auf der Messseite. W3 (Task 11): Browser-Durchlauf, README, Gesamtreview, Auslieferung und B8.

**Tech Stack:** Python 3.13, FastAPI, SQLite, build123d (nur im Läufer/Sandbox), Vanilla-JS-Module, three.js; pytest, `node --test`, Playwright (nur Scratchpad).

**Spec:** `docs/superpowers/specs/2026-10-15-bemassung-am-modell-design.md`

## Global Constraints

- Entscheidungen des Nutzers (Spec „Ziel“) sind gesetzt: sofort parametrisch (neue Version ohne KI-Aufruf); KI folgert nur gebündelt auf Klick „Schlüsse ziehen“; alle Maße der KI mit Gruppen-Schaltern; gelernte Werte gelten projektweit; Modellmaße haben den eigenen Nummernkreis D1, D2 … mit Verweis `ref` auf die Foto-Messung (M-Nummer); Anker kommen aus dem Code (`DIM_ANCHORS`, Regel 13), `a`/`b` im JSON nur als Rückfall; nicht übernommene gelernte Werte lösen eine Warnung aus, Snap2CAD schreibt die Konstante nie selbst zurück. Textur/GLB ist Stufe C (§7).
- Feldnamen wörtlich wie in der Spec: `id` (`D<n>`), `ref`, `label`, `group`, `var`, `value`, `assumed`, `a`, `b`, `derived_from`, `note`, `editable`, `user_set`, `anchors_stale`; `result.json["dim_anchors"]`; `GET /api/jobs/{jid}` → `pending_param` (`{id, label, value, old, old_assumed}`); `GET /api/projects/{pid}` → `model_dims`; Tabelle `model_dims` mit `label_norm`, `grp`, `dim_id`; Trigger `param`; `localStorage`-Schlüssel `dims.groups`.
- Gruppen genau `aussen | bohrung | tiefe | fase | platte | sonst`; unbekannt → `sonst`.
- Zahlen: Ankerabstand darf um höchstens max(0,1 mm; 1 %) vom Codewert abweichen; Codewert gilt ab Abweichung > 0,01; gelernter Wert gilt als übernommen bei Abweichung ≤ 0,01 mm; Banner ab > 10 % Abweichung oder `assumed`; Param-Aufruf 1–20 Werte, 0 < Wert ≤ 5000, im Code mit bis zu 3 Nachkommastellen; `DIM_ANCHORS` höchstens 200 Einträge mit Schlüssel `^D[0-9]{1,4}$`, Punkte auf 4 Nachkommastellen gerundet; Hilfslinienversatz 8 % der Modellgröße, mindestens 2 mm; Label-Wert mit 1 Nachkommastelle ohne Einheit.
- Konstantenmuster wörtlich: `re.search(rf"^{var}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(#.*)?$", code, re.M)`; `editable: true` nur bei genau einer Zeile `^VAR\s*=`.
- `label_norm` wörtlich: `" ".join(re.sub(r"[^\w]+", " ", label.casefold()).split())`.
- Farben: Annahme `#b42318`, vom Nutzer gesetzt `#1a7f37`, abgeleitet blau gestrichelt, sonst `#1f6fb2`, veraltete Anker grau gestrichelt.
- `web/app/sandbox.py` bleibt unverändert (`_collect` reicht `dim_anchors` durch).
- Param-Neuaufbau: kein KI-Aufruf, kein Autofix, kein `_check_quota`, kein `_check_ready` auf die KI; die Sandbox muss laufen (503). Kontingent zählt weiter nur `create`/`iterate` (`auth.usage_this_month`).
- In `web/app/jobs.py`, `web/app/parts.py` und `web/app/check.py` wird `core.vision` **nur funktionslokal** importiert (Muster `jobs._rect_top`).
- Sandbox und KI laufen **nie innerhalb von `db.atomic()`** und nie unter `jobs._lock` (Sandbox nur im Pool über `_submit`). `jobs._lock` ist ein `RLock`; Statuswechsel und Versionsanlage geschehen unter `_lock`.
- Höchstens 6 Bilder je Nachricht, `jobs.pick_images` bleibt unverändert. Keine `temperature` an die API (`tests/test_check.py::test_kein_temperature_an_sdk`).
- Texte der Oberfläche deutsch, im `h()`-Stil, ohne „Claude“/„Anthropic“ (`tests/test_texts.py`); KI-Aktionen heißen „KI“.
- Zeilenlänge 130 (ruff E501); Variablennamen nicht `l` (E741); keine unbenutzten Zuweisungen (F841). Code-Snippets im Plan, die länger sind, beim Übernehmen an Wortgrenzen umbrechen. Jeder Task endet mit `ruff check` auf den geänderten Python-Dateien bzw. `node --check` auf den geänderten JS-Dateien.
- Commits ohne jede Claude-Attribution (keine `Co-Authored-By`-Zeile, kein „Generated with“ in PR-Texten) – Nutzerregel geht vor.
- Echte Fotos und Protokolle nur im Scratchpad (`/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad/`), nie im Repo. Protokoll dieser Stufe: `scratchpad/stufe-b-protokoll.md`.
- Jede Welle endet mit grüner lokaler Suite **und** grüner CI. Die CI läuft nur für `pull_request` und `main`; der Entwurfs-PR entsteht deshalb am Ende von W1 (Task 6 Step 5) vor dem ersten CI-Lauf. Lokal: `source /root/Snap2CAD-venv/bin/activate && cd /root/Snap2CAD && ruff check . && python -m pytest -q -p no:cacheprovider && node --test tests/js/*.test.mjs && for f in web/static/js/*.js; do node --check "$f"; done`. CI (auf den gepushten Stand warten, nicht auf einen älteren Lauf): `git push origin bemassung-am-modell && H=$(git rev-parse HEAD) && until gh run list -b bemassung-am-modell -L5 --json databaseId,headSha -q ".[] | select(.headSha==\"$H\") | .databaseId" | grep -q .; do sleep 5; done && gh run watch --exit-status $(gh run list -b bemassung-am-modell -L5 --json databaseId,headSha -q ".[] | select(.headSha==\"$H\") | .databaseId" | head -1)`.

## Review Focus

1. Eingabe im Label oder in der Tabelle mit Komma, Leerzeichen, leer, Text, `0x10`, 0 oder über 5000: „45,5“ gilt als 45,5 mm, alles Ungültige zeigt einen Hinweis und sendet nichts (Task 7 `parseDimInput: Komma, Leerzeichen, Unsinn und Grenzen`).
2. Wert in einer älteren Version oder in einem zweiten Tab nach einem Neuaufbau eingetragen: Der Server lehnt mit 409 ab, statt still die aktuelle Version zu ändern (Task 5 `test_param_basis_veraltet`).
3. Ein Maß wird stark geändert (Höhe 75 → 45): Die Hüllquader-Erwartung der KI gilt für den alten Wert und darf den Neuaufbau nicht scheitern lassen; die Version ist `ok` ohne Prüfpunkt „Hüllquader“ (Task 5 `test_version_huellquader_ohne_ki_erwartung`).
4. KI benennt beim „Schlüsse ziehen“ ein nachgemessenes Maß um (gleiche D-Nummer, anderes Label) und setzt dabei den Wert zurück: Die Warnung „Messschieber am Modell übernommen“ erscheint trotzdem (Task 3 `test_lernen_abgleich_ueber_dim_id`).
5. Bestehende Projekte ohne gelernte Werte: Die gespeicherte Prüfung bleibt nach dem Update aktuell (Prüfsumme unverändert), sonst startet die Auftragsseite für jedes Projekt einen KI-Lauf (Task 6 `test_hash_ohne_gelernte_werte_unveraendert`).

## Dateien

| Datei | Verantwortung | Tasks |
|---|---|---|
| `web/app/ai.py` | Maßformat lesen (`parse_dims`, `point3`), Regeln 11–13, Testmodus | 1 |
| `web/app/runner/cad_runner.py` | `DIM_ANCHORS` auswerten → `result.json["dim_anchors"]` | 2 |
| `web/app/db.py` | Tabelle `model_dims` | 3 |
| `web/app/jobs.py` | Lernen, Messtabelle, Abgleich, Anker, Editierbarkeit, Prüfpunkt, `param`, `pending_param` | 3, 4, 5 |
| `web/app/main.py` | `POST /api/jobs/{jid}/param`, `model_dims` am Projekt, Löschen, CSV | 5, 6 |
| `web/app/check.py` | Prüfsumme mit gelernten Werten | 6 |
| `web/static/js/geom.js` | reine Funktionen der Bemaßung | 7 |
| `web/static/js/viewer.js` | Linien, Labels, Gruppen, Eingabe, Hervorheben | 8 |
| `web/static/css/app.css` | Label- und Tabellenstile, Liste der Messseite | 8, 10 |
| `web/static/js/cad.js` | Auftragsseite: Gruppen-Schalter, Tabelle, Banner, „Schlüsse ziehen“ | 9 |
| `web/static/js/measure.js` | Liste „Messschieber am Modell“ | 10 |
| `tests/test_dims.py` (neu) | B1–B4 | 1, 3, 4, 5, 6 |
| `tests/test_sandbox.py` | B3 Läufer | 2 |
| `tests/js/dims.test.mjs` (neu) | B5 | 7 |

---

## Welle 1 – Server

### Task 1: Maßformat in `ai.py`: `parse_dims`, Regeln 11–13, Testmodus mit `DIM_ANCHORS`

**Files:**
- Modify: `web/app/ai.py` (`CAD_SYSTEM` Z. 21–78, neue Helfer nach `_text` Z. 360, `parse_cad` Z. 321–339, `_FAKE_V1`/`_FAKE_V2` Z. 449–486, `_fake_meta` Z. 489–499)
- Create: `tests/test_dims.py`

**Interfaces:**
- Consumes: `ai._text(v, n, default="")`, `ai._BLOCK`.
- Produces:
  - `ai.DIM_GROUPS = ("aussen", "bohrung", "tiefe", "fase", "platte", "sonst")`
  - `ai.point3(v) -> list[float] | None` – genau drei endliche Zahlen (kein `bool`, kein Text), sonst `None`.
  - `ai.parse_dims(raw, meas_ids=frozenset()) -> list[dict]` – je Eintrag genau die Schlüssel `id, label, group, var, value, ref, assumed, derived_from, note, editable` (immer `False`, `jobs.mark_editable` setzt ihn) und optional beide `a`, `b`; höchstens 200 Einträge.
  - `ai.parse_cad(text, meas_ids=frozenset()) -> tuple[dict, str]` – wie bisher, `meta["dimensions"]` ist das Ergebnis von `parse_dims`.
  - Testmodus: `_fake_meta(t)` liefert D1–D8 (`LENGTH`, `WIDTH`, `THICKNESS` mit `assumed: true`, `HOLE_D`, `HOLE_DX`, `SLOT_L` mit `assumed: true`, `SLOT_W` nur mit `a`/`b`, `CORNER_R` mit `assumed: true` ohne Anker); `_FAKE_V1` und `_FAKE_V2` enden mit `DIM_ANCHORS` für D1–D6.
  - `tests/test_dims.py` Helfer (für Tasks 3–6): `_proj(c) -> int`, `_meas(c, pid, label, value, critical=False) -> dict`, `_user_row(c) -> dict`, `_job(c, pid, code, meta, result=None) -> int` (Auftrag mit Version 1, `trigger="create"`, Status `ok`, `current_version=1`), `_version(jid, version, trigger, status, meta, request_text="")`, `_wait(c, jid, timeout=120) -> dict`.

- [ ] **Step 1: Failing tests schreiben**

`tests/test_dims.py` neu:

```python
"""Bemaßung am Modell (Spec 2026-10-15 Stufe B, B1–B4)."""
import json
import math
import time

import pytest

from conftest import H


def _proj(c):
    return c.post("/api/projects", json={"name": "Stufe B"}, headers=H).json()["id"]


def _meas(c, pid, label, value, critical=False):
    r = c.post(f"/api/projects/{pid}/measurements", json={"kind": "length", "value": value, "label": label,
                                                         "critical": critical}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _user_row(c):
    from app import db
    return db.q1("SELECT * FROM users WHERE username=?", (c.username,))


def _job(c, pid, code, meta, result=None):
    """Auftrag mit einer fertigen Version 1 direkt in der Datenbank (ohne KI und Sandbox)."""
    from app import db
    jid = db.ex("INSERT INTO jobs(user_id,project_id,name,request,status,messages,current_version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (_user_row(c)["id"], pid, "Block", "{}", "done", "[]", 1, db.now(), db.now()))
    _version(jid, 1, "create", "ok", meta, code=code, result=result)
    return jid


def _version(jid, version, trigger, status, meta, request_text="", code="X = 1\n", result=None):
    from app import db
    db.ex("INSERT INTO job_versions(job_id,version,trigger,request_text,code,claude_text,meta,status,result,checks,usage,"
          "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
          (jid, version, trigger, request_text, code, "", db.jdump(meta), status, db.jdump(result or {}), "[]", "{}",
           db.now()))


def _wait(c, jid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.2)
    raise AssertionError(f"Auftrag {jid} nicht fertig")


# ------------------------------------------------------------------ B1: parse_cad

def _answer(dims):
    return ("Text\n```json\n" + json.dumps({"summary": "x", "dimensions": dims}, ensure_ascii=False)
            + "\n```\n```python\npart = Box(1, 1, 1)\n```\n")


def test_parse_dims_bereinigt():
    from app import ai
    meta, _ = ai.parse_cad(_answer([
        {"id": "D3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "ref": "m1",
         "assumed": True, "a": [0, 0, 0], "b": [0, 0, 75.0], "derived_from": None, "note": "Annahme: Höhe ≈ Breite"},
        {"id": "D3", "label": "doppelt", "var": "X_Y", "value": 1},
        {"id": "M1", "label": "alte Nummer", "var": "LENGTH", "value": 80},
        {"id": "d4", "label": "Bohrung\n Ø", "group": "loch", "var": "HOLE_D", "value": 6.5, "ref": "M2",
         "derived_from": "D3"},
        {"id": "D5", "label": "Fase", "nominal": 1.5, "a": [0, 0, 0], "b": [1.5, 0, 0], "derived_from": "D5"},
        {"id": "D6", "label": "", "var": "lower", "value": 2, "assumed": "ja", "derived_from": "D99"},
        "kein dict"]), {"M1"})
    d = {x["id"]: x for x in meta["dimensions"]}
    assert list(d) == ["D3", "D4", "D5", "D6"]
    assert d["D3"] == {"id": "D3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "ref": "M1",
                       "assumed": True, "derived_from": None, "note": "Annahme: Höhe ≈ Breite", "editable": False,
                       "a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 75.0]}
    assert (d["D4"]["label"], d["D4"]["group"], d["D4"]["ref"], d["D4"]["derived_from"]) == ("Bohrung Ø", "sonst", None, "D3")
    assert (d["D5"]["var"], d["D5"]["value"], d["D5"]["derived_from"]) == (None, 1.5, None) and "a" not in d["D5"]
    assert (d["D6"]["label"], d["D6"]["var"], d["D6"]["assumed"], d["D6"]["derived_from"]) == ("D6", None, False, None)


def test_parse_wert_als_text():
    from app import ai
    meta, _ = ai.parse_cad(_answer([
        {"id": "D1", "label": "Länge", "var": "LENGTH", "value": "75.0", "a": ["0", 0, 0], "b": [75, 0, 0]},
        {"id": "D2", "label": "Breite", "var": "WIDTH", "value": "breit"},
        {"id": "D3", "label": "Dicke", "var": "THICK", "value": True},
        {"id": "D4", "label": "Tiefe", "var": "DEPTH", "value": float("nan")}]))
    d = {x["id"]: x for x in meta["dimensions"]}
    assert d["D1"]["value"] == 75.0 and "a" not in d["D1"] and "b" not in d["D1"]      # nie ein halber Anker
    assert d["D2"]["value"] is None and d["D3"]["value"] is None and d["D4"]["value"] is None


def test_parse_hoechstens_200_und_ohne_liste():
    from app import ai
    meta, _ = ai.parse_cad(_answer([{"id": f"D{i}", "label": "x", "var": "XX", "value": 1} for i in range(1, 260)]))
    assert len(meta["dimensions"]) == 200
    meta, _ = ai.parse_cad("```json\n{\"dimensions\": {\"D1\": 1}}\n```\n```python\npart = Box(1, 1, 1)\n```\n")
    assert meta["dimensions"] == []


def test_parse_prompt_regeln_11_bis_13():
    from app import ai
    s = ai.CAD_SYSTEM
    assert "DIM_ANCHORS" in s and '"id": "D3"' in s and '"var": "BLOCK_H"' in s and '"ref": null' in s
    assert "Werte aus „Messschieber am Modell“ sind verbindlich und nie Annahmen." in " ".join(s.split())
    assert '"measured"' not in s and '"nominal"' not in s
    assert all(f"\n{n}. " in s for n in range(1, 14))


@pytest.mark.parametrize("t", [6.0, 8.0])
def test_parse_testmodus_anker_passen_zum_code(t):
    """Fake-Konstanten und DIM_ANCHORS ohne build123d auswerten: Abstand = value (B6)."""
    from app import ai
    code = ai._FAKE_V2.format(t=f"{t:.1f}")
    ns = {}
    exec(code.split("with BuildPart()")[0] + code[code.index("DIM_ANCHORS"):], ns)
    meta = ai._fake_meta(t)
    dims = {d["id"]: d for d in meta["dimensions"]}
    assert set(ns["DIM_ANCHORS"]) == {"D1", "D2", "D3", "D4", "D5", "D6"}
    for k, (a, b) in ns["DIM_ANCHORS"].items():
        assert math.dist(a, b) == pytest.approx(dims[k]["value"]), k
    assert ns["THICKNESS"] == t and dims["D3"]["assumed"] is True and dims["D3"]["value"] == t
    assert math.dist(dims["D7"]["a"], dims["D7"]["b"]) == dims["D7"]["value"] and dims["D7"]["a"][2] == t
    assert "a" not in dims["D8"] and "DIM_ANCHORS = {" in ai._FAKE_V1
    parsed, _ = ai.parse_cad("```json\n" + json.dumps(meta) + "\n```\n```python\n" + code + "```\n", {"M1"})
    assert [d["id"] for d in parsed["dimensions"]] == [f"D{i}" for i in range(1, 9)]
    assert parsed["dimensions"][0]["ref"] == "M1" and parsed["dimensions"][1]["ref"] is None
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `source /root/Snap2CAD-venv/bin/activate && cd /root/Snap2CAD && python -m pytest -q -p no:cacheprovider tests/test_dims.py`
Expected: FAIL – `TypeError: parse_cad() takes 1 positional argument but 2 were given` bzw. `AssertionError` in `test_parse_prompt_regeln_11_bis_13`.

- [ ] **Step 3: Implementierung in `web/app/ai.py`**

`CAD_SYSTEM`: unter „Eingaben“ nach der Zeile „Fertigungsverfahren, Material und Wünsche des Nutzers.“ einfügen:

```
- Ggf. ein Abschnitt „Messschieber am Modell (verbindlich)“: am 3D-Modell nachgemessene Werte (Regel 11).
```

Nach Regel 10 (Zeile „und Regel 9.“) anfügen:

```
11. Jedes Maß, das die Form bestimmt (Außenmaße, Bohrungsdurchmesser, Tiefen, Fasen, Plattendicke, Rasterabstände),
   steht als benannte Konstante `NAME = Zahl` am Anfang des Codes und als Eintrag in `dimensions` mit `var = NAME`.
   Keine zwei Einträge teilen eine Konstante. Die Maße heißen D1, D2 … (eigener Nummernkreis, nie die M-Nummer einer
   Messung); `group` ist aussen, bohrung, tiefe, fase, platte oder sonst; `assumed: true` heißt Annahme ohne
   Messgrundlage. Die Ankerpunkte stehen in `DIM_ANCHORS` (Regel 13) so, dass ihr Abstand `value` ist (bei
   Durchmessern: zwei gegenüberliegende Punkte des Kreises; bei Tiefen: Beginn und Ende der Bohrung); `a`/`b` im JSON
   sind optional und nur der Rückfall für Maße ohne Eintrag in `DIM_ANCHORS`. `ref` nennt die Messung der Messtabelle
   (M-Nummer), aus der der Wert stammt; Maße ohne Messgrundlage haben `ref: null`. Werte aus „Messschieber am Modell“
   sind verbindlich und nie Annahmen.
12. Bei Änderungswünschen und Schlussfolgerungen behalten bestehende Maße `id` und `var`; neue Maße bekommen neue
   IDs. Ein Maß, dessen Wert aus einem nachgemessenen Maß folgt, trägt `derived_from` und eine `note`. Hat das Projekt
   mehrere Teile, beginnt `label` mit der Teilnummer („T2 Dicke“).
13. Am Ende des Codes steht ein Dict `DIM_ANCHORS = {"D3": ((0, 0, 0), (0, 0, BLOCK_H)), …}` mit den Ankerpunkten
   jedes Maßes als Ausdrücke der Konstanten (Modellraum, mm; Punkte als Tupel von drei Zahlen). Fehlt ein Eintrag,
   gelten `a`/`b` aus dem JSON als Rückfall.
```

Im Antwortformat die Zeile `"dimensions": [{"id": "M1", …}],` und den Kommentar des Python-Blocks ersetzen:

```
  "dimensions": [{"id": "D3", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "ref": null,
                  "assumed": true, "a": [0, 0, 0], "b": [0, 0, 75.0], "derived_from": null, "note": "Annahme: Höhe ≈ Breite"}],
```
```
# build123d-Code, Ergebnis in `part`, am Ende DIM_ANCHORS (Regel 13)
```

Nach `_text` (vor `parse_check`) einfügen:

```python
DIM_GROUPS = ("aussen", "bohrung", "tiefe", "fase", "platte", "sonst")
_DIM_ID = re.compile(r"^D[0-9]{1,4}$")
_VAR = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")
MAX_DIMS = 200


def _pos_num(v) -> float | None:
    """Zahl > 0 und endlich; Text wie "75.0" zaehlt, bool nicht."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return f if math.isfinite(f) and f > 0 else None


def point3(v) -> list[float] | None:
    """Ankerpunkt: genau drei endliche Zahlen (mm), sonst None."""
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in v):
        return None
    p = [float(x) for x in v]
    return p if all(math.isfinite(x) for x in p) else None


def _upper(v) -> str | None:
    return v.strip().upper() if isinstance(v, str) else None


def parse_dims(raw, meas_ids=frozenset()) -> list[dict]:
    """Masse der KI bereinigen (Spec Stufe B §1): D-Nummer Pflicht, erste gewinnt; ohne var/value nicht editierbar
    und ohne Anker; ref nur mit vorhandener Messung; derived_from nur auf ein anderes Mass der Liste."""
    out, seen = [], set()
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        did = _upper(it.get("id")) or ""
        if not _DIM_ID.match(did) or did in seen:
            continue
        seen.add(did)
        var = it["var"] if isinstance(it.get("var"), str) and _VAR.match(it["var"]) else None
        value = _pos_num(it.get("value"))
        ref = _upper(it.get("ref"))
        d = {"id": did, "label": " ".join(_text(it.get("label"), 200).split())[:60] or did,
             "group": it.get("group") if it.get("group") in DIM_GROUPS else "sonst", "var": var,
             "value": value if value is not None else _pos_num(it.get("nominal")),
             "ref": ref if ref in meas_ids else None, "assumed": it.get("assumed") is True,
             "derived_from": _upper(it.get("derived_from")),
             "note": " ".join(_text(it.get("note"), 400).split())[:120], "editable": False}
        if var and value is not None:
            pa, pb = point3(it.get("a")), point3(it.get("b"))
            if pa and pb:
                d["a"], d["b"] = pa, pb
        out.append(d)
        if len(out) == MAX_DIMS:
            break
    ids = {d["id"] for d in out}
    for d in out:
        if d["derived_from"] not in ids or d["derived_from"] == d["id"]:
            d["derived_from"] = None
    return out
```

`parse_cad` vollständig ersetzen:

```python
def parse_cad(text: str, meas_ids=frozenset()) -> tuple[dict, str]:
    meta, code = None, None
    for lang, body in _BLOCK.findall(text):
        lang = (lang or "").lower()
        if lang == "json" and meta is None:
            try:
                meta = json.loads(body)
            except ValueError:
                pass
        elif lang in ("python", "py") or (not lang and "part" in body and code is None):
            code = body.strip() + "\n"
    if code is None:
        raise AIError("Die Antwort enthielt keinen Python-Codeblock.")
    meta = meta if isinstance(meta, dict) else {}
    for k in ("assumptions", "check_before_manufacturing", "dimensions"):
        if not isinstance(meta.get(k), list):
            meta[k] = []
    meta["dimensions"] = parse_dims(meta["dimensions"], meas_ids)
    return meta, code
```

`_FAKE_V1`: nach `part = p.part` (vor dem schließenden `'''`) anfügen – die Zeilennummer des absichtlichen Fehlers (Z. 15, `tests/test_api.py`) bleibt gleich:

```python

DIM_ANCHORS = {
    "D1": ((-LENGTH / 2, -WIDTH / 2, 0), (LENGTH / 2, -WIDTH / 2, 0)),
    "D2": ((LENGTH / 2, -WIDTH / 2, 0), (LENGTH / 2, WIDTH / 2, 0)),
    "D3": ((LENGTH / 2, WIDTH / 2, 0), (LENGTH / 2, WIDTH / 2, THICKNESS)),
    "D4": ((HOLE_DX / 2 - HOLE_D / 2, HOLE_DY / 2, THICKNESS), (HOLE_DX / 2 + HOLE_D / 2, HOLE_DY / 2, THICKNESS)),
    "D5": ((-HOLE_DX / 2, HOLE_DY / 2, THICKNESS), (HOLE_DX / 2, HOLE_DY / 2, THICKNESS)),
}
```

`_FAKE_V2`: nach `part = p.part` anfügen (doppelte Klammern wegen `.format`):

```python

DIM_ANCHORS = {{
    "D1": ((-LENGTH / 2, -WIDTH / 2, 0), (LENGTH / 2, -WIDTH / 2, 0)),
    "D2": ((LENGTH / 2, -WIDTH / 2, 0), (LENGTH / 2, WIDTH / 2, 0)),
    "D3": ((LENGTH / 2, WIDTH / 2, 0), (LENGTH / 2, WIDTH / 2, THICKNESS)),
    "D4": ((HOLE_DX / 2 - HOLE_D / 2, HOLE_DY / 2, THICKNESS), (HOLE_DX / 2 + HOLE_D / 2, HOLE_DY / 2, THICKNESS)),
    "D5": ((-HOLE_DX / 2, HOLE_DY / 2, THICKNESS), (HOLE_DX / 2, HOLE_DY / 2, THICKNESS)),
    "D6": ((-SLOT_L / 2, 0, THICKNESS), (SLOT_L / 2, 0, THICKNESS)),
}}
```

`_fake_meta` vollständig ersetzen:

```python
def _fake_meta(t):
    dims = [
        {"id": "D1", "label": "Länge", "group": "aussen", "var": "LENGTH", "value": 80.0, "ref": "M1", "assumed": False,
         "note": "gerundet"},
        {"id": "D2", "label": "Breite", "group": "aussen", "var": "WIDTH", "value": 50.0, "ref": "M2", "assumed": False,
         "note": "gerundet"},
        {"id": "D3", "label": "Dicke", "group": "platte", "var": "THICKNESS", "value": t, "ref": None, "assumed": True,
         "note": "Annahme ohne Höhenlehre"},
        {"id": "D4", "label": "Bohrung Ø", "group": "bohrung", "var": "HOLE_D", "value": 4.5, "ref": "M3", "assumed": False},
        {"id": "D5", "label": "Lochabstand x", "group": "sonst", "var": "HOLE_DX", "value": 64.0, "ref": "M4",
         "assumed": False},
        {"id": "D6", "label": "Langloch Länge", "group": "sonst", "var": "SLOT_L", "value": 30.0, "ref": None,
         "assumed": True, "note": "Annahme: mittig"},
        {"id": "D7", "label": "Langloch Breite", "group": "sonst", "var": "SLOT_W", "value": 8.0, "ref": None,
         "assumed": False, "a": [0.0, -4.0, t], "b": [0.0, 4.0, t], "note": "Anker nur im JSON"},
        {"id": "D8", "label": "Eckenradius", "group": "fase", "var": "CORNER_R", "value": 5.0, "ref": None,
         "assumed": True, "note": "am Original prüfen"}]
    return {"summary": f"Montageplatte 80 × 50 × {t:g} mm mit vier Bohrungen und Langloch (Testmodus).",
            "assumptions": ["Bohrungen sind Durchgangsbohrungen", "Langloch mittig, gleiche Tiefe wie die Platte"],
            "check_before_manufacturing": ["Bohrungsdurchmesser mit Schieblehre nachmessen",
                                           "Eckenradius am Original prüfen"],
            "dimensions": dims, "bbox_expected": [80.0, 50.0, t], "orientation": "Unterseite auf XY, Ursprung Mitte"}
```

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py tests/test_check.py tests/test_texts.py && python -m pytest -q -p no:cacheprovider tests/test_api.py -k autofix && ruff check web/app/ai.py tests/test_dims.py`
Expected: PASS (der Autofix-Test bestätigt: `_FAKE_V1` scheitert weiter in Zeile 15, `_FAKE_V2` baut).

- [ ] **Step 5: Commit**

```bash
git add web/app/ai.py tests/test_dims.py
git commit -m "KI: Masse mit D-Nummern, ref, var und Ankern (Regeln 11-13), Testmodus mit DIM_ANCHORS"
```

### Task 2: Läufer wertet `DIM_ANCHORS` aus (`cad_runner.py`)

**Files:**
- Modify: `web/app/runner/cad_runner.py:152-196` (Abschnitt „5) Export und Pruefung“, neue Funktionen vor Abschnitt 4)
- Modify: `tests/test_sandbox.py` (am Ende anfügen; braucht build123d wie die übrigen Sandbox-Tests, läuft in der CI über `web/requirements.txt`)

**Interfaces:**
- Consumes: Namensraum `ns` des ausgeführten Modellcodes (`ns.get("DIM_ANCHORS")`).
- Produces: `result.json["dim_anchors"] = {"D3": [[x, y, z], [x, y, z]], …}` (Werte auf 4 Nachkommastellen); Schlüssel fehlt, wenn `DIM_ANCHORS` fehlt, kein `dict` ist oder die Auswertung wirft. `sandbox.run(...)["result"]` reicht das Feld unverändert durch.

- [ ] **Step 1: Failing tests** (an `tests/test_sandbox.py` anhängen)

```python
def test_dim_anchors_tupel_vector_und_ungueltige(tmp_path):
    code = ("B = 10\npart = Box(B, B, B)\nDIM_ANCHORS = {\n"
            "    'D1': ((0, 0, 0), (0, 0, B)),\n"
            "    'D2': (Vector(0, 0, 0), Vector(1.23456, 0, 0)),\n"
            "    'D3': ((0, 0, float('nan')), (0, 0, 1)),\n"
            "    'M1': ((0, 0, 0), (1, 0, 0)),\n"
            "    'D4': ((0, 0, 0),),\n"
            "    'D5': ((0, 0, 0), ('x', 0, 0)),\n"
            "    'D12345': ((0, 0, 0), (1, 0, 0)),\n"
            "    7: ((0, 0, 0), (1, 0, 0)),\n"
            "    'D6': [[0, 0, 0], [0, 2, 0]],\n"
            "}\n")
    r = run(code, tmp_path)
    assert r["ok"], r
    assert r["result"]["dim_anchors"] == {"D1": [[0, 0, 0], [0, 0, 10]], "D2": [[0, 0, 0], [1.2346, 0, 0]],
                                          "D6": [[0, 0, 0], [0, 2, 0]]}
    assert not (tmp_path / "out" / "error.json").exists()


@pytest.mark.parametrize("anchors", ["[1, 2]", "None", "'D1'"])
def test_dim_anchors_kein_dict(tmp_path, anchors):
    r = run(f"part = Box(5, 5, 5)\nDIM_ANCHORS = {anchors}\n", tmp_path)
    assert r["ok"], r
    assert "dim_anchors" not in r["result"]


def test_dim_anchors_fehlt_oder_wirft(tmp_path):
    r = run(OK, tmp_path)
    assert r["ok"] and "dim_anchors" not in r["result"]
    code = ("class X(dict):\n    def items(self):\n        raise RuntimeError('kaputt')\n"
            "part = Box(5, 5, 5)\nDIM_ANCHORS = X(D1=((0, 0, 0), (1, 0, 0)))\n")
    r = run(code, tmp_path / "zwei")
    assert r["ok"], r
    assert "dim_anchors" not in r["result"] and not (tmp_path / "zwei" / "out" / "error.json").exists()


def test_dim_anchors_hoechstens_200(tmp_path):
    code = "part = Box(5, 5, 5)\nDIM_ANCHORS = {f'D{i}': ((0, 0, 0), (i, 0, 0)) for i in range(1, 251)}\n"
    r = run(code, tmp_path)
    assert r["ok"], r
    assert len(r["result"]["dim_anchors"]) == 200 and r["result"]["dim_anchors"]["D200"] == [[0, 0, 0], [200, 0, 0]]
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_sandbox.py -k anchors`
Expected: FAIL – `KeyError: 'dim_anchors'` in `test_dim_anchors_tupel_vector_und_ungueltige` und `test_dim_anchors_hoechstens_200`.

- [ ] **Step 3: Implementierung**

In `cad_runner.py` vor `with open("model.py", encoding="utf-8") as f:` (Abschnitt 4) einfügen. Kein `re`: der Läufer belegt den Namen `re` später mit dem STEP-Re-Import.

```python
MAX_ANCHORS = 200


def _dim_key(k) -> bool:
    """Schluessel wie ^D[0-9]{1,4}$ (ohne re: der Name re ist unten der STEP-Re-Import)."""
    return isinstance(k, str) and 2 <= len(k) <= 5 and k[0] == "D" and k[1:].isascii() and k[1:].isdigit()


def _anchor_point(p):
    """Folge von drei Werten oder Objekt mit X, Y, Z (build123d Vector); jeder Wert float()-bar und endlich."""
    if all(hasattr(p, a) for a in ("X", "Y", "Z")):
        vals = (p.X, p.Y, p.Z)
    elif isinstance(p, (list, tuple)) and len(p) == 3:
        vals = p
    else:
        return None
    out = [float(v) for v in vals]
    return [round(v, 4) for v in out] if all(math.isfinite(v) for v in out) else None


def _dim_anchors(d):
    """DIM_ANCHORS (Regel 13) -> {id: [[x, y, z], [x, y, z]]}; ungueltige Eintraege werden uebersprungen."""
    if not isinstance(d, dict):
        return None
    out = {}
    for k, v in d.items():
        if len(out) >= MAX_ANCHORS:
            break
        if not _dim_key(k) or not isinstance(v, (list, tuple)) or len(v) != 2:
            continue
        try:
            a, b = _anchor_point(v[0]), _anchor_point(v[1])
        except Exception:  # noqa: BLE001  float() eines fremden Objekts: Eintrag ueberspringen
            continue
        if a is not None and b is not None:
            out[k] = [a, b]
    return out
```

Abschnitt 5 ab `result = {` bis Dateiende vollständig ersetzen (das Ergebnis wird erst nach der Ankerauswertung geschrieben):

```python
    result = {
        "valid": valid,
        "solids": len(re.solids()),
        "faces": len(re.faces()),
        "bbox": [round(bb.size.X, 4), round(bb.size.Y, 4), round(bb.size.Z, 4)],
        "bbox_min": [round(bb.min.X, 4), round(bb.min.Y, 4), round(bb.min.Z, 4)],
        "volume_mm3": round(float(re.volume), 3),
        "seccomp": SECCOMP,
        "step_bytes": os.path.getsize("model.step"),
        "stl": {"triangles": int(len(mesh.faces)), "watertight": bool(mesh.is_watertight),
                "winding_consistent": bool(mesh.is_winding_consistent),
                "volume_mm3": round(float(mesh.volume), 3), "bytes": os.path.getsize("model.stl"),
                "bbox": [round(float(v), 4) for v in mesh.extents]},
    }
    with open("outline.json", "w") as f:
        json.dump(outline, f)
except BaseException as e:  # noqa: BLE001
    _write("error.json", {"stage": "export", **_model_error(e)})
    sys.exit(1)

# 6) Ankerpunkte der Masse (Regel 13): eigener Schritt, laesst den Lauf nie scheitern
try:
    anchors = _dim_anchors(ns.get("DIM_ANCHORS"))
    if anchors is not None:
        result["dim_anchors"] = anchors
except BaseException:  # noqa: BLE001
    pass
_write("result.json", result)
```

Den Docstring oben um eine Zeile ergänzen: `Optional: DIM_ANCHORS im Modellcode -> result.json["dim_anchors"] (Regel 13).`

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_sandbox.py && ruff check web/app/runner/cad_runner.py tests/test_sandbox.py`
Expected: PASS (alle bisherigen Sandbox-Tests unverändert grün).

- [ ] **Step 5: Commit**

```bash
git add web/app/runner/cad_runner.py tests/test_sandbox.py
git commit -m "Laeufer: DIM_ANCHORS auswerten und als dim_anchors in result.json schreiben"
```

### Task 3: Tabelle `model_dims`, Lernen, Abschnitt in der Messtabelle, Abgleich nach KI-Läufen

**Files:**
- Modify: `web/app/db.py:97-111` (`SCHEMA`: Tabelle nach `parts`)
- Modify: `web/app/jobs.py` (Importe Z. 4–9; neue Konstanten und Funktionen nach `SOURCE_LABEL` Z. 27 bzw. nach `measurement_table` Z. 65–84; `measurement_table`, `build_initial_message` Z. 165–204, `_iterate_locked` Z. 324–339)
- Test: `tests/test_dims.py`

**Interfaces:**
- Consumes: `jobs._fmt(v, nd=2)`, `jobs._iterate_locked`, `jobs.build_initial_message` (bestehend).
- Produces:
  - Tabelle `model_dims(id, project_id, label, label_norm, grp, value, job_id, dim_id, note, created_at, UNIQUE(project_id, label_norm))`.
  - `jobs.label_norm(label: str) -> str`; `jobs.GROUP_TEXT: dict[str, str]` (`aussen → außen`, …); `jobs.MODEL_DIMS_HEADING = "## Messschieber am Modell (verbindlich)"`; `jobs.NO_MEAS = "(keine Messwerte – nur aus den Fotos ableiten)"`.
  - `jobs.learn_dims(project_id: int, job_id: int | None, dims: list[dict]) -> None` – je Maß (`id`, `label`, `group`, `value`) ein UPSERT auf `label_norm` (leere Norm → `id.casefold()`).
  - `jobs.learned_dims(project_id: int) -> list[dict]` – Zeilen von `model_dims`, `ORDER BY id`.
  - `jobs.model_dims_section(project_id: int | None) -> str` – `""` ohne Werte.
  - `jobs.measurement_table(project_id, part_id=None, empty: str | None = None) -> tuple[str, list[dict]]` – hängt den Abschnitt an; `empty` ersetzt die leere Tabelle.
  - `jobs.reconcile_learned(meta: dict, project_id: int | None, job_id: int) -> dict | None` – setzt `user_set`/`assumed` und liefert den Prüfpunkt `{"id": "model_dims", "label": "Messschieber am Modell übernommen", "state": "warn"|"ok", "detail": str}` oder `None`.

- [ ] **Step 1: Failing tests** (an `tests/test_dims.py` anhängen; oben `import copy` vor `import json` ergänzen)

```python
# ------------------------------------------------------------------ B4: gelernte Werte

def test_lernen_label_norm():
    from app import jobs
    assert jobs.label_norm("Höhe  Block (außen)–Ø 6") == "höhe block aussen ø 6"
    assert jobs.label_norm("T2 Dicke") == "t2 dicke" and jobs.label_norm(" – ") == ""


def test_lernen_upsert_und_tabelle(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "Höhe Block", "group": "aussen", "value": 75.0}])
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "höhe  Block!", "group": "aussen", "value": 45.0}])
    rows = jobs.learned_dims(pid)
    assert [(r["label_norm"], r["label"], r["value"], r["dim_id"], r["job_id"], r["grp"]) for r in rows] == \
        [("höhe block", "höhe  Block!", 45.0, "D3", jid, "aussen")]
    table, _ = jobs.measurement_table(pid)
    assert f"## Messschieber am Modell (verbindlich)\n- höhe  Block!: 45 mm (Gruppe außen, gemessen am Auftrag {jid})" in table


def test_lernen_label_leer_nutzt_id(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D1", "label": "–", "group": "sonst", "value": 1.0},
                               {"id": "D2", "label": "—", "group": "sonst", "value": 2.0}])
    assert sorted(r["label_norm"] for r in jobs.learned_dims(pid)) == ["d1", "d2"]


def test_lernen_in_auftrag_pruefung_und_aenderung(user, monkeypatch):
    from app import db, jobs
    pid = _proj(user)
    jid = _job(user, pid, "BLOCK_H = 75.0\n", {"dimensions": []})
    p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    txt = jobs.build_initial_message(p, "x", {"images": []})[0]["content"][0]["text"]
    assert "## Messschieber am Modell" not in txt
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    txt = jobs.build_initial_message(p, "x", {"images": []})[0]["content"][0]["text"]
    assert "## Messwerte\n(keine Messwerte – nur aus den Fotos ableiten)\n\n## Messschieber am Modell (verbindlich)" in txt
    assert f"- Höhe Block: 45 mm (Gruppe außen, gemessen am Auftrag {jid})" in txt
    chk = jobs.build_initial_message(p, "", {"images": [], "for_check": True})[0]["content"][0]["text"]
    assert "## Messschieber am Modell (verbindlich)" in chk
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    jobs.iterate(_user_row(user), db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), "Bohrung größer")
    last = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"])[-1]["content"][0]["text"]
    assert last.index("Bohrung größer") < last.index("## Messschieber am Modell") < last.index("Ausgangspunkt")


def test_lernen_ohne_werte_kein_abschnitt_in_aenderung(user, monkeypatch):
    from app import db, jobs
    pid = _proj(user)
    jid = _job(user, pid, "BLOCK_H = 75.0\n", {"dimensions": []})
    monkeypatch.setattr(jobs, "_submit", lambda *a: None)
    jobs.iterate(_user_row(user), db.q1("SELECT * FROM jobs WHERE id=?", (jid,)), "Bohrung größer")
    last = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"])[-1]["content"][0]["text"]
    assert "Messschieber am Modell" not in last


def test_lernen_abgleich(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    assert jobs.reconcile_learned({"dimensions": [{"id": "D1", "label": "x", "value": 1.0}]}, pid, jid) is None
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "Höhe Block", "group": "aussen", "value": 45.0},
                               {"id": "D4", "label": "Bohrung", "group": "bohrung", "value": 6.2}])
    meta = {"dimensions": [{"id": "D3", "label": "Höhe Block", "value": 45.005, "assumed": True},
                           {"id": "D4", "label": "bohrung", "value": 6.5, "assumed": False}]}
    chk = jobs.reconcile_learned(meta, pid, jid)
    assert meta["dimensions"][0]["user_set"] is True and meta["dimensions"][0]["assumed"] is False
    assert "user_set" not in meta["dimensions"][1]
    assert chk == {"id": "model_dims", "label": "Messschieber am Modell übernommen", "state": "warn",
                   "detail": "Bohrung: 6,2 → 6,5"}
    ok = jobs.reconcile_learned({"dimensions": [{"id": "D3", "label": "Höhe Block", "value": 45.0}]}, pid, jid)
    assert ok == {"id": "model_dims", "label": "Messschieber am Modell übernommen", "state": "ok", "detail": "1 übernommen"}


def test_lernen_abgleich_ueber_dim_id(user):
    """KI benennt ein nachgemessenes Mass um (gleiche D-Nummer) und setzt den Wert zurueck: trotzdem Warnung."""
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jid2 = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D3", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    meta = {"dimensions": [{"id": "D3", "label": "Blockhöhe", "value": 75.0, "assumed": True}]}
    assert jobs.reconcile_learned(meta, pid, jid)["detail"] == "Höhe Block: 45 → 75"
    assert jobs.reconcile_learned(copy.deepcopy(meta), pid, jid2) is None      # anderer Auftrag: D-Nummer gilt nicht


def test_lernen_migration_legt_tabelle_an():
    import sqlite3

    from app import db
    c = sqlite3.connect(":memory:")
    c.executescript(db.SCHEMA.replace("CREATE TABLE IF NOT EXISTS model_dims", "CREATE TABLE IF NOT EXISTS _alt_model_dims"))
    assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='model_dims'").fetchone()
    c.executescript(db.SCHEMA)
    db._migrate(c)
    cols = [r[1] for r in c.execute("PRAGMA table_info(model_dims)")]
    assert cols == ["id", "project_id", "label", "label_norm", "grp", "value", "job_id", "dim_id", "note", "created_at"]
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py -k lernen`
Expected: FAIL – `AttributeError: module 'app.jobs' has no attribute 'label_norm'` und `AssertionError` in `test_lernen_migration_legt_tabelle_an` (Spaltenliste leer).

- [ ] **Step 3: Implementierung**

`web/app/db.py`, in `SCHEMA` nach der Tabelle `parts` (vor den `CREATE INDEX`-Zeilen); `conn()` führt `SCHEMA` bei jedem Start aus, damit bekommen alte Datenbanken die Tabelle ohne weitere Migration (`job_versions` braucht keine Spalte, Spec §6):

```sql
CREATE TABLE IF NOT EXISTS model_dims(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label TEXT NOT NULL, label_norm TEXT NOT NULL,
  grp TEXT NOT NULL, value REAL NOT NULL, job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL, dim_id TEXT,
  note TEXT, created_at TEXT NOT NULL,
  UNIQUE(project_id, label_norm));
```

`web/app/jobs.py` – `import re` zwischen `import os` und `import shutil` ergänzen. Nach `SOURCE_LABEL` einfügen:

```python
GROUP_TEXT = {"aussen": "außen", "bohrung": "Bohrung", "tiefe": "Tiefe", "fase": "Fase", "platte": "Platte",
              "sonst": "sonstige"}
MODEL_DIMS_HEADING = "## Messschieber am Modell (verbindlich)"
NO_MEAS = "(keine Messwerte – nur aus den Fotos ableiten)"
```

Nach `top_points` einfügen:

```python
# ------------------------------------------------------------------ Gelernte Werte (Spec Stufe B §4)

def label_norm(label: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", label.casefold()).split())


def _norm_of(d: dict) -> str:
    """label_norm eines Masses; ohne Buchstaben/Ziffern im Label die D-Nummer (sonst ueberschreiben sie sich)."""
    return label_norm(str(d.get("label") or "")) or str(d.get("id") or "").casefold()


def learn_dims(project_id: int, job_id: int | None, dims: list[dict]):
    """Je Mass ein Eintrag; gleiche label_norm im Projekt ersetzt den alten Wert (UPSERT)."""
    for d in dims:
        db.ex("""INSERT INTO model_dims(project_id,label,label_norm,grp,value,job_id,dim_id,note,created_at)
                 VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(project_id,label_norm) DO UPDATE SET label=excluded.label, grp=excluded.grp,
                   value=excluded.value, job_id=excluded.job_id, dim_id=excluded.dim_id, note=excluded.note,
                   created_at=excluded.created_at""",
              (project_id, str(d.get("label") or d.get("id")), _norm_of(d), d.get("group") or "sonst", float(d["value"]),
               job_id, d.get("id"), None, db.now()))


def learned_dims(project_id: int) -> list[dict]:
    return db.q("SELECT * FROM model_dims WHERE project_id=? ORDER BY id", (project_id,))


def model_dims_section(project_id: int | None) -> str:
    rows = learned_dims(project_id) if project_id else []
    if not rows:
        return ""
    lines = [MODEL_DIMS_HEADING]
    for r in rows:
        where = f"gemessen am Auftrag {r['job_id']}" if r["job_id"] else "gemessen am Modell"
        lines.append(f"- {r['label']}: {_fmt(r['value'], 3)} mm (Gruppe {GROUP_TEXT.get(r['grp'], r['grp'])}, {where})")
    return "\n".join(lines)


def _de_num(v: float) -> str:
    return _fmt(v, 3).replace(".", ",")


def reconcile_learned(meta: dict, project_id: int | None, job_id: int) -> dict | None:
    """Nach jedem KI-Lauf (nicht param): gelernter Wert getroffen -> user_set; sonst Warnung, nie Zurueckschreiben."""
    rows = learned_dims(project_id) if project_id else []
    if not rows:
        return None
    dims = [d for d in meta.get("dimensions", []) if isinstance(d, dict) and isinstance(d.get("value"), (int, float))]
    by_norm: dict[str, dict] = {}
    for d in dims:
        by_norm.setdefault(_norm_of(d), d)
    by_id = {d.get("id"): d for d in dims}
    hit, far = 0, []
    for r in rows:
        d = by_norm.get(r["label_norm"])
        if d is None and r["job_id"] == job_id and r["dim_id"]:
            d = by_id.get(r["dim_id"])       # Label umbenannt, D-Nummer im selben Auftrag stabil (Regel 12)
        if d is None:
            continue
        if abs(d["value"] - r["value"]) <= 0.01 + 1e-9:
            d["user_set"], d["assumed"] = True, False
            hit += 1
        else:
            far.append(f"{r['label']}: {_de_num(r['value'])} → {_de_num(d['value'])}")
    label = "Messschieber am Modell übernommen"
    if far:
        return {"id": "model_dims", "label": label, "state": "warn", "detail": "; ".join(far)}
    return {"id": "model_dims", "label": label, "state": "ok", "detail": f"{hit} übernommen"} if hit else None
```

`measurement_table` vollständig ersetzen:

```python
def measurement_table(project_id: int, part_id: int | None = None, empty: str | None = None) -> tuple[str, list[dict]]:
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY seq", (project_id,))
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (project_id,))}
    if part_id is not None:
        linked = {r["id"] for r in db.q("SELECT id, data FROM parts WHERE project_id=?", (project_id,))
                  if (db.jload(r["data"], {}) or {}).get("same_as") == part_id}
        rows = [m for m in rows if m["part_id"] in (part_id, None) or m["part_id"] in linked]
    seq = {t["id"]: t["seq"] for t in db.q("SELECT id, seq FROM parts WHERE project_id=?", (project_id,))}
    lines = ["| ID | Bezeichnung | Teil | Art | Wert | ± | Messschieber | Nennmaß | kritisch | Passung | Quelle "
             "| Ansicht/Punkte (mm) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in rows:
        d = db.jload(m["data"], {}) or {}
        tag, pts = top_points(m, d, photos)
        where = (f"{d.get('view', '')} {tag} " + " ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in pts[:3])).strip()
        teil = f"T{seq[m['part_id']]}" if m["part_id"] in seq else ""
        lines.append(f"| M{m['seq']} | {m['label']} | {teil} | {m['kind']} | {_fmt(m['value'])} {m['unit']} | "
                     f"{_fmt(m['unc'])} | {_fmt(m['caliper'])} | {_fmt(d.get('nominal'))} | {'ja' if m['critical'] else ''} | "
                     f"{m['fit'] or ''} | {SOURCE_LABEL.get(m['source'], m['source'])} | {where} |")
    text = "\n".join(lines) if rows or empty is None else empty
    sec = model_dims_section(project_id)       # Spec §4: Erstauftrag und Pruefung bekommen den Abschnitt hierueber
    return (f"{text}\n\n{sec}" if sec else text), rows
```

`build_initial_message`: die beiden Zeilen

```python
    table, rows = measurement_table(project["id"], options.get("part_id"))
```
```python
              "", "## Messwerte", table if rows else "(keine Messwerte – nur aus den Fotos ableiten)"]
```

ersetzen durch

```python
    table, _ = measurement_table(project["id"], options.get("part_id"), empty=NO_MEAS)
```
```python
              "", "## Messwerte", table]
```

`_iterate_locked` vollständig ersetzen:

```python
def _iterate_locked(user: dict, job: dict, text: str):
    base = job["current_version"] or db.q1("SELECT MAX(version) v FROM job_versions WHERE job_id=?", (job["id"],))["v"]
    if not base:
        raise HTTPException(409, "Es gibt noch keine Version, auf der aufgebaut werden kann.")
    _check_ready()
    _check_quota(user)
    msgs = db.jload(job["messages"], [])
    # Gespraech auf die aktuelle Version zurueckschneiden ist nicht noetig: Claude sieht den Verlauf.
    cur = db.q1("SELECT code FROM job_versions WHERE job_id=? AND version=?", (job["id"], base))
    sec = model_dims_section(job["project_id"])   # Spec §4: gelernte Werte an jeden Aenderungswunsch
    msgs.append({"role": "user", "content": [{"type": "text", "text":
                 f"Änderungswunsch zu Version {base}:\n{text.strip()}\n\n" + (f"{sec}\n\n" if sec else "") +
                 "Ausgangspunkt ist dieser Code:\n```python\n" + (cur["code"] if cur else "") + "```\n"
                 "Antworte wieder im gleichen Format (JSON-Block + vollständiger Python-Block)."}]})
    _set(job["id"], messages=db.jdump(msgs), status="queued", error=None)
    log(job["id"], f"Änderungswunsch: {text.strip()[:200]}")
    _submit(job["id"], "iterate", text)
```

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py tests/test_check.py tests/test_api.py && ruff check web/app/db.py web/app/jobs.py tests/test_dims.py`
Expected: PASS (`test_check.py` deckt Auftragsnachricht und Prüfung ohne gelernte Werte ab, `test_api.py` den Vorschlags-Weg über `measurement_table` ohne `empty`).

- [ ] **Step 5: Commit**

```bash
git add web/app/db.py web/app/jobs.py tests/test_dims.py
git commit -m "Gelernte Werte: Tabelle model_dims, Abschnitt in Messtabelle und Aenderungswunsch, Abgleich nach KI-Laeufen"
```

### Task 4: Anker, Editierbarkeit und Prüfpunkt in `jobs._run`

**Files:**
- Modify: `web/app/jobs.py` (Import `math`; neue Funktionen nach `_de` Z. 209–210; `compute_checks` Z. 213–267; `_run` Z. 395–468)
- Test: `tests/test_dims.py`

**Interfaces:**
- Consumes: `ai.parse_cad(text, meas_ids)`, `ai.point3(v)`, `jobs.reconcile_learned(meta, project_id, job_id)` (Task 3), `result["dim_anchors"]` (Task 2).
- Produces:
  - `jobs._meas_ids(project_id: int | None) -> set[str]` – M-Nummern der übernommenen Messungen.
  - `jobs._const_re(var: str) -> re.Pattern` – das Spec-Muster `^VAR\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(#.*)?$` (re.M).
  - `jobs.mark_editable(meta: dict, code: str) -> None` – setzt `editable`, übernimmt den Codewert (`note` „Wert aus dem Code“), markiert „Konstante mehrfach belegt“; idempotent.
  - `jobs._apply_anchors(meta: dict, result: dict | None, changed: set[str] | None = None) -> None` – schreibt die geltenden `a`/`b` (gerundet 4 Stellen) und `anchors_stale`; `changed=None` = KI-Lauf, sonst Param-Lauf mit den geänderten D-Nummern.
  - `jobs.compute_checks(result, meta, project_id)` – Prüfpunkt „Kritische Maße übernommen“ über `ref`/`value` (neue Einträge) bzw. `id`/`nominal` (alte Einträge).
  - `_run` speichert die Meta nach dem Sandbox-Lauf erneut (mit Ankern) und hängt den Prüfpunkt `model_dims` an.

- [ ] **Step 1: Failing tests** (an `tests/test_dims.py` anhängen)

```python
# ------------------------------------------------------------------ B1: Editierbarkeit, Anker, Pruefpunkt

def test_parse_editable_nach_codepruefung():
    from app import jobs
    code = "LENGTH = 80.0  # M1\nWIDTH = 2 * 25\nHOLE_D = 4.5\nHOLE_D = 5.0\nTHICKNESS = 6.5\nLENGTH_X = 3\n"
    meta = {"dimensions": [
        {"id": "D1", "var": "LENGTH", "value": 80.0, "note": ""},
        {"id": "D2", "var": "WIDTH", "value": 50.0, "note": ""},
        {"id": "D3", "var": "HOLE_D", "value": 4.5, "note": ""},
        {"id": "D4", "var": "THICKNESS", "value": 6.0, "note": "Annahme"},
        {"id": "D5", "var": "MISSING", "value": 1.0, "note": ""},
        {"id": "D6", "var": None, "value": 3.0, "note": ""}]}
    jobs.mark_editable(meta, code)
    d = {x["id"]: x for x in meta["dimensions"]}
    assert [d[k]["editable"] for k in ("D1", "D2", "D3", "D4", "D5", "D6")] == [True, False, False, True, False, False]
    assert d["D3"]["note"] == "Konstante mehrfach belegt" and d["D1"]["value"] == 80.0
    assert d["D4"]["value"] == 6.5 and d["D4"]["note"] == "Annahme; Wert aus dem Code"
    jobs.mark_editable(meta, code)
    assert d["D4"]["note"] == "Annahme; Wert aus dem Code" and d["D3"]["note"] == "Konstante mehrfach belegt"


def test_anker_aus_dim_anchors_vor_ab_und_abstand():
    from app import jobs
    meta = {"dimensions": [
        {"id": "D1", "var": "A", "value": 10.0, "a": [0, 0, 0], "b": [5, 0, 0]},
        {"id": "D2", "var": "B", "value": 5.0, "a": [0, 0, 0], "b": [0, 5, 0]},
        {"id": "D3", "var": "C", "value": 5.0, "a": [0, 0, 0], "b": [0, 7, 0]},
        {"id": "D4", "var": "DD", "value": 100.0, "a": [0, 0, 0], "b": [100.9, 0, 0]},
        {"id": "D5", "var": "EE", "value": 100.0, "a": [0, 0, 0], "b": [101.1, 0, 0]},
        {"id": "D6", "var": "FF", "value": 5.0, "a": [0, 0, 0], "b": [5.09, 0, 0]},
        {"id": "D7", "var": "GG", "value": 5.0},
        {"id": "D8", "var": None, "value": 5.0, "a": [0, 0, 0], "b": [5, 0, 0]},
        {"id": "D9", "var": "HH", "value": 5.0, "anchors_stale": True, "a": [0, 0, 0], "b": [5, 0, 0]}]}
    result = {"dim_anchors": {"D1": [[0, 0, 0], [10, 0, 0]], "D7": [[0, 0, 0], [0, 0]], "D9": [[1, 1, 1], [1, 1, 6]]}}
    jobs._apply_anchors(meta, result)
    d = {x["id"]: x for x in meta["dimensions"]}
    assert (d["D1"]["a"], d["D1"]["b"]) == ([0.0, 0.0, 0.0], [10.0, 0.0, 0.0])
    assert d["D2"]["b"] == [0.0, 5.0, 0.0] and "a" in d["D4"] and "a" in d["D6"]
    assert [k for k in ("D3", "D5", "D7", "D8") if "a" in d[k] or "b" in d[k]] == []
    assert d["D9"]["b"] == [1.0, 1.0, 6.0] and "anchors_stale" not in d["D9"]


def test_anker_rueckfall_param_gestreckt_und_stale():
    from app import jobs
    meta = {"dimensions": [
        {"id": "D1", "var": "H", "value": 45.0, "a": [0, 0, 0], "b": [0, 0, 75]},
        {"id": "D2", "var": "W", "value": 40.0, "a": [0, 0, 0], "b": [40, 0, 0]},
        {"id": "D3", "var": "DD", "value": 6.0, "a": [0, 0, 0], "b": [6, 0, 0], "anchors_stale": True}]}
    jobs._apply_anchors(meta, {"dim_anchors": {"D3": [[1, 0, 0], [7, 0, 0]]}}, changed={"D1"})
    d = {x["id"]: x for x in meta["dimensions"]}
    assert d["D1"]["b"] == [0.0, 0.0, 45.0] and "anchors_stale" not in d["D1"]
    assert d["D2"]["anchors_stale"] is True and d["D2"]["b"] == [40.0, 0.0, 0.0]
    assert "anchors_stale" not in d["D3"] and d["D3"]["a"] == [1.0, 0.0, 0.0]


def test_pruefpunkt_kritisch_ueber_ref(user):
    from app import jobs
    pid = _proj(user)
    _meas(user, pid, "Länge", 80.0, critical=True)                                   # M1
    res = {"valid": True, "solids": 1, "stl": {"watertight": True, "triangles": 12}}

    def crit(dims):
        return next(c for c in jobs.compute_checks(res, {"dimensions": dims}, pid) if c["id"] == "critical")
    assert crit([{"id": "D1", "ref": "M1", "value": 80.1}])["state"] == "ok"
    far = crit([{"id": "D1", "ref": "M1", "value": 85.0}])
    assert far["state"] == "warn" and far["detail"] == "stark gerundet: M1 80,00 → 85,00"
    assert crit([{"id": "D1", "ref": None, "value": 80.0}])["detail"] == "nicht ausgewiesen: M1"
    assert crit([{"id": "M1", "nominal": 80.0}])["state"] == "ok"                      # alte Version


def test_anker_nach_ki_lauf(user):
    pid = _proj(user)
    _meas(user, pid, "Länge", 80.0)                                                   # M1
    r = user.post("/api/jobs", json={"project_id": pid, "name": "Platte", "request": "x"}, headers=H)
    j = _wait(user, r.json()["id"])
    v = j["versions"][-1]
    assert j["status"] == "done" and v["status"] == "ok", j
    d = {x["id"]: x for x in v["meta"]["dimensions"]}
    assert set(v["result"]["dim_anchors"]) == {"D1", "D2", "D3", "D4", "D5", "D6"}
    assert d["D1"]["ref"] == "M1" and d["D2"]["ref"] is None
    assert (d["D3"]["a"], d["D3"]["b"]) == ([40.0, 25.0, 0.0], [40.0, 25.0, 6.0]) and d["D4"]["a"][2] == 6.0
    assert (d["D7"]["a"], d["D7"]["b"]) == ([0.0, -4.0, 6.0], [0.0, 4.0, 6.0]) and "anchors_stale" not in d["D7"]
    assert "a" not in d["D8"] and all(x["editable"] for x in d.values())
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py -k "parse_editable or anker or pruefpunkt"`
Expected: FAIL – `AttributeError: module 'app.jobs' has no attribute 'mark_editable'` / `_apply_anchors`; `test_pruefpunkt_kritisch_ueber_ref` scheitert mit „nicht ausgewiesen: M1“ statt `ok`.

- [ ] **Step 3: Implementierung in `web/app/jobs.py`**

`import math` vor `import os` ergänzen. Nach `_de` einfügen:

```python
# ------------------------------------------------------------------ Masse am Modell (Spec Stufe B §1, §2)

def _meas_ids(project_id: int | None) -> set[str]:
    """M-Nummern der uebernommenen Messungen: nur diese duerfen als ref stehen."""
    if not project_id:
        return set()
    return {f"M{r['seq']}" for r in db.q("SELECT seq FROM measurements WHERE project_id=? AND accepted=1", (project_id,))}


def _const_re(var: str) -> re.Pattern:
    return re.compile(rf"^{var}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(#.*)?$", re.M)


def _add_note(note: str | None, add: str) -> str:
    return note if note and add in note else (f"{note}; {add}" if note else add)


def mark_editable(meta: dict, code: str):
    """editable nur bei genau einer Zeile `VAR =` im Muster der Spec; Codewert gilt ab Abweichung > 0,01."""
    for d in meta.get("dimensions", []):
        if not isinstance(d, dict):
            continue
        var, value = d.get("var"), d.get("value")
        d["editable"] = False
        if not var or not isinstance(value, (int, float)):
            continue
        if len(re.findall(rf"^{var}\s*=", code, re.M)) > 1:
            d["note"] = _add_note(d.get("note"), "Konstante mehrfach belegt")
            continue
        m = _const_re(var).search(code)
        if not m:
            continue
        d["editable"] = True
        v = float(m.group(1))
        if abs(v - value) > 0.01:
            d["value"] = v
            d["note"] = _add_note(d.get("note"), "Wert aus dem Code")


def _stretch(a: list[float], b: list[float], value: float) -> tuple[list[float], list[float]]:
    """Anker entlang a->b auf die neue Laenge strecken (Rueckfall ohne DIM_ANCHORS-Eintrag)."""
    n = math.dist(a, b)
    return (a, b) if n <= 1e-9 else (a, [a[i] + (b[i] - a[i]) * value / n for i in range(3)])


def _apply_anchors(meta: dict, result: dict | None, changed: set[str] | None = None):
    """Je Mass zuerst dim_anchors (Regel 13), sonst a/b; gelten nur bei Abstand = Wert ± max(0,1 mm; 1 %).
    changed (Param-Lauf): geaendertes Mass ohne Eintrag wird gestreckt, jedes andere ohne Eintrag ist anchors_stale."""
    da = (result or {}).get("dim_anchors")
    da = da if isinstance(da, dict) else {}
    for d in meta.get("dimensions", []):
        if not isinstance(d, dict):
            continue
        value, src = d.get("value"), da.get(d.get("id"))
        a = b = None
        if isinstance(src, (list, tuple)) and len(src) == 2:
            a, b = ai.point3(src[0]), ai.point3(src[1])
        stale = False
        if not (a and b):
            a, b = ai.point3(d.get("a")), ai.point3(d.get("b"))
            if changed is not None and a and b:
                if d.get("id") in changed:
                    a, b = _stretch(a, b, value)
                    stale = d.get("anchors_stale") is True
                else:
                    stale = True
        ok = bool(d.get("var") and isinstance(value, (int, float)) and a and b
                  and abs(math.dist(a, b) - value) <= max(0.1, 0.01 * value))
        d.pop("anchors_stale", None)
        if ok:
            d["a"], d["b"] = [round(x, 4) for x in a], [round(x, 4) for x in b]
            if stale:
                d["anchors_stale"] = True
        else:
            d.pop("a", None)
            d.pop("b", None)
```

`compute_checks` vollständig ersetzen:

```python
def compute_checks(result: dict, meta: dict, project_id: int | None) -> list[dict]:
    checks = []
    checks.append({"id": "valid", "label": "Gültiger Volumenkörper (B-Rep)",
                   "state": "ok" if result.get("valid") else "fail",
                   "detail": "" if result.get("valid") else "OpenCascade meldet ungültige Geometrie"})
    n = result.get("solids", 0)
    checks.append({"id": "solids", "label": "Genau ein Körper", "state": "ok" if n == 1 else ("warn" if n > 1 else "fail"),
                   "detail": f"{n} Körper"})
    stl = result.get("stl") or {}
    checks.append({"id": "watertight", "label": "STL wasserdicht", "state": "ok" if stl.get("watertight") else "fail",
                   "detail": f"{stl.get('triangles', 0)} Dreiecke"})
    exp = meta.get("bbox_expected")
    bb = result.get("bbox")
    if isinstance(exp, list) and len(exp) == 3 and bb:
        try:
            e = [float(v) for v in exp]
            dev = max(abs(a - b) for a, b in zip(bb, e, strict=True))
            dev_sorted = max(abs(a - b) for a, b in zip(sorted(bb), sorted(e), strict=True))
            lim = max(1.0, 0.03 * max(e))
            if dev <= 0.2:
                st, det = "ok", f"Abweichung {_de(dev)} mm"
            elif dev_sorted <= 0.2:
                st, det = "warn", "Maße stimmen, aber andere Achsenlage als angegeben"
            elif dev_sorted <= lim:
                st, det = "warn", f"Abweichung {_de(dev_sorted)} mm"
            else:
                st, det = "fail", (f"Abweichung {_de(dev_sorted)} mm (erwartet {' × '.join(_de(v, 1) for v in e)}, "
                                   f"erzeugt {' × '.join(_de(v, 1) for v in bb)})")
            checks.append({"id": "bbox", "label": "Hüllquader wie angekündigt", "state": st, "detail": det})
        except (TypeError, ValueError):
            pass
    if project_id:
        crit = db.q("SELECT seq,label,value,caliper,unc FROM measurements WHERE project_id=? AND accepted=1 AND critical=1",
                    (project_id,))
        # Stufe B: Modellmasse (D-Nummern) zeigen ueber ref auf die Messung und tragen value; alte Versionen: id = M-Nummer
        by_m: dict[str, tuple[dict, str]] = {}
        for d in meta.get("dimensions", []):
            if not isinstance(d, dict):
                continue
            did = str(d.get("id", "")).upper()
            if did.startswith("D"):
                if d.get("ref"):
                    by_m.setdefault(str(d["ref"]).upper(), (d, "value"))
            else:
                by_m.setdefault(did, (d, "nominal"))
        missing = [f"M{c['seq']}" for c in crit if f"M{c['seq']}" not in by_m]
        far = []
        for c in crit:
            hit = by_m.get(f"M{c['seq']}")
            ref = c["caliper"] if c["caliper"] is not None else c["value"]
            try:
                if hit and ref is not None:
                    v = float(hit[0].get(hit[1]))
                    if abs(v - ref) > max(2 * (c["unc"] or 0.5), 0.3):
                        far.append(f"M{c['seq']} {_de(ref)} → {_de(v)}")
            except (TypeError, ValueError):
                pass
        if crit:
            st = "warn" if (missing or far) else "ok"
            det = []
            if missing:
                det.append("nicht ausgewiesen: " + ", ".join(missing))
            if far:
                det.append("stark gerundet: " + ", ".join(far))
            checks.append({"id": "critical", "label": "Kritische Maße übernommen", "state": st,
                           "detail": "; ".join(det) or f"{len(crit)} geprüft"})
    return checks
```

`_run` vollständig ersetzen:

```python
def _run(job_id: int, trigger: str, request_text: str, ev: threading.Event):
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job or job["status"] == "cancelled" or ev.is_set():
        return
    _set(job_id, status="running")
    msgs = db.jload(job["messages"], [])
    fixes = 0
    while True:
        if ev.is_set():
            raise ai.Cancelled()
        if not db.q1("SELECT id FROM jobs WHERE id=?", (job_id,)):
            return  # Auftrag wurde geloescht
        log(job_id, "KI erstellt das Modell …" if trigger != "autofix" else "KI korrigiert den Code …")
        text, usage = ai.call(ai.CAD_SYSTEM, msgs, max_tokens=CAD_MAX_TOKENS, cancel=ev,
                              on_progress=lambda n: None)
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
        _set(job_id, messages=db.jdump(msgs))
        if ev.is_set():
            raise ai.Cancelled()
        version = _new_version(job_id, trigger, request_text, text, usage)
        vdir = version_dir(job_id, version)
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "claude.txt").write_text(text, encoding="utf-8")
        try:
            meta, code = ai.parse_cad(text, _meas_ids(job["project_id"]))
        except ai.AIError as e:
            meta, code = {}, ""
            err = {"stage": "antwort", "type": "FormatError", "message": str(e), "line": None, "code": None}
            db.ex("UPDATE job_versions SET code=?, meta=?, status='failed', error=? WHERE job_id=? AND version=?",
                  (code, db.jdump(meta), db.jdump(err), job_id, version))
            log(job_id, f"Version {version}: Antwort im falschen Format", "warn")
            result, checks = None, []
        else:
            mark_editable(meta, code)
            learned_chk = reconcile_learned(meta, job["project_id"], job_id)   # Spec §4: nur nach KI-Laeufen
            (vdir / "model.py").write_text(code, encoding="utf-8")
            db.ex("UPDATE job_versions SET code=?, meta=? WHERE job_id=? AND version=?",
                  (code, db.jdump(meta), job_id, version))
            log(job_id, f"Version {version}: Code erhalten ({len(code.splitlines())} Zeilen), Sandbox rechnet …")
            res = sandbox.run(code, vdir, cancel=ev)
            if not db.q1("SELECT id FROM jobs WHERE id=?", (job_id,)):
                shutil.rmtree(job_dir(job_id), ignore_errors=True)
                return
            err = None if res["ok"] else res["error"]
            result = res.get("result")
            if result:
                _apply_anchors(meta, result)
            checks = compute_checks(result, meta, job["project_id"]) if result else []
            if result and learned_chk:
                checks.append(learned_chk)
            failed = err is not None or any(c["state"] == "fail" for c in checks)
            db.ex("UPDATE job_versions SET status=?, error=?, result=?, checks=?, seconds=?, meta=? "
                  "WHERE job_id=? AND version=?",
                  ("failed" if failed else "ok", db.jdump(err) if err else None, db.jdump(result) if result else None,
                   db.jdump(checks), res.get("seconds"), db.jdump(meta), job_id, version))
            if not failed:
                warn = sum(1 for c in checks if c["state"] == "warn")
                bb = result["bbox"]
                log(job_id, f"Version {version} fertig: {_de(bb[0])} × {_de(bb[1])} × {_de(bb[2])} mm, "
                            f"{result['stl']['triangles']} Dreiecke, {_de(res['seconds'], 1)} s"
                            + (f", {warn} Hinweis(e)" if warn else ""), "ok")
                if _current(job_id, ev):
                    _set(job_id, status="done", current_version=version, error=None)
                return
            if err:
                where = f" (Zeile {err['line']})" if err.get("line") else ""
                log(job_id, f"Version {version}: {err.get('type')}{where}: {str(err.get('message'))[:200]}", "warn")
            else:
                log(job_id, f"Version {version}: Prüfung nicht bestanden – " +
                    "; ".join(c["label"] for c in checks if c["state"] == "fail"), "warn")
        if fixes >= config.MAX_AUTOFIX:
            msg = "Auch nach automatischer Korrektur kein gültiges Modell."
            if _current(job_id, ev):
                _set(job_id, status="failed", error=msg)
            log(job_id, msg + " Bitte Änderungswunsch formulieren oder Maße prüfen.", "error")
            return
        fixes += 1
        trigger = "autofix"
        msgs.append({"role": "user", "content": [{"type": "text", "text": _fix_prompt(err, checks)}]})
        _set(job_id, messages=db.jdump(msgs))
        log(job_id, f"Automatische Korrektur {fixes}/{config.MAX_AUTOFIX}")
```

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py tests/test_api.py tests/test_check.py && ruff check web/app/jobs.py tests/test_dims.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/jobs.py tests/test_dims.py
git commit -m "Auftrag: editierbare Konstanten, Anker aus dim_anchors mit Abstandspruefung, kritische Masse ueber ref"
```

### Task 5: Parametrischer Neuaufbau `jobs.param`, Endpunkt, `pending_param`

**Files:**
- Modify: `web/app/jobs.py` (neue Funktionen nach `_iterate_locked`; `_run_safe` Z. 365–383; Anfang von `_run`; `job_public` Z. 490–510)
- Modify: `web/app/main.py` (Modelle und Route nach `job_iterate` Z. 1693–1699)
- Test: `tests/test_dims.py`

**Interfaces:**
- Consumes: `jobs._apply_anchors(meta, result, changed)`, `jobs.compute_checks`, `jobs.learn_dims` (Task 3), `jobs._new_version`, `jobs._submit`, `jobs._current`, `sandbox.run`, `sandbox.worker_alive`.
- Produces:
  - `jobs.PARAM_MAX = 20`; `jobs._num(v: float) -> str` (bis 3 Nachkommastellen, ohne Nullen: `45.0 → "45"`).
  - `jobs.set_const(code: str, var: str, value: float) -> tuple[str, int]` – ersetzt die Zahl der einen Zeile `VAR = alt`, Kommentar und Abstände bleiben; zweiter Wert = Anzahl Ersetzungen (0 oder 1).
  - `jobs.param(user: dict, job: dict, values: list[dict], base: int | None = None) -> dict` – `values` = `[{"id": "D3", "value": 45.0}]`; Antwort `{"version": n}` bzw. ohne Projekt `{"version": n, "learned": False}`; Fehler 400/409/503 als `HTTPException`.
  - `jobs._run_param(job_id: int, ev: threading.Event) -> None` (über `_submit(job_id, "param", request_text)` → `_run`).
  - `jobs._param_ids(text: str | None) -> list[str]`; `jobs.pending_param(job_id: int) -> list[dict]` mit `{"id", "label", "value", "old", "old_assumed"}`.
  - `POST /api/jobs/{jid}/param` Body `{"values": [{"id": "D3", "value": 45.0}], "base": 3}` (`base` optional: Version, die der Nutzer sieht); `GET /api/jobs/{jid}` liefert zusätzlich `pending_param`.
  - Neue Version: `trigger = "param"`, `request_text = "D3 = 45 mm, D7 = 12.5 mm"`, `claude_text = ""`, `usage = {}`; Meta je geändertem Maß `value`, `assumed: false`, `user_set: true`, `derived_from: null`; `bbox_expected` der Basis wird entfernt (die Hüllquader-Prüfung der KI gilt für die alten Werte).
  - Gesprächszeile (nur bei Erfolg): `{"role": "user", "content": [{"type": "text", "text": "Parametrisch geändert: D3 = 45 mm (Version n)"}]}`.

- [ ] **Step 1: Failing tests** (an `tests/test_dims.py` anhängen)

```python
# ------------------------------------------------------------------ B2/B3: Param-Neuaufbau

BLOCK = '''BLOCK_L = 40.0  # Laenge
BLOCK_H = 75.0  # Hoehe, Annahme
HOLE_D = 6.0
part = Box(BLOCK_L, BLOCK_L, BLOCK_H, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Cylinder(
    HOLE_D / 2, BLOCK_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
DIM_ANCHORS = {"D1": ((-BLOCK_L / 2, -BLOCK_L / 2, 0), (BLOCK_L / 2, -BLOCK_L / 2, 0)),
               "D2": ((BLOCK_L / 2, -BLOCK_L / 2, 0), (BLOCK_L / 2, -BLOCK_L / 2, BLOCK_H))}
'''
BLOCK_META = {"dimensions": [
    {"id": "D1", "label": "Länge", "group": "aussen", "var": "BLOCK_L", "value": 40.0, "assumed": False, "editable": True,
     "a": [-20.0, -20.0, 0.0], "b": [20.0, -20.0, 0.0]},
    {"id": "D2", "label": "Höhe Block", "group": "aussen", "var": "BLOCK_H", "value": 75.0, "assumed": True,
     "editable": True, "a": [20.0, -20.0, 0.0], "b": [20.0, -20.0, 75.0]},
    {"id": "D3", "label": "Bohrung", "group": "bohrung", "var": "HOLE_D", "value": 6.0, "assumed": False, "editable": True,
     "a": [-3.0, 0.0, 75.0], "b": [3.0, 0.0, 75.0]},
    {"id": "D4", "label": "Fase", "group": "fase", "var": None, "value": 1.0, "assumed": True, "editable": False}]}


def _fake_sandbox(monkeypatch, ok=True, anchors=None, block=False):
    from app import sandbox
    seen = []

    def run(code, dest, cancel=None):
        seen.append(code)
        dest.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while block and not cancel.is_set() and time.time() - t0 < 10:
            time.sleep(0.05)
        if block:
            raise sandbox.Cancelled()
        if not ok:
            return {"ok": False, "seconds": 0.1, "error": {"stage": "model", "type": "ValueError", "message": "kaputt",
                                                         "line": 3, "code": "x", "traceback": ""}}
        res = {"valid": True, "solids": 1, "bbox": [40.0, 40.0, 45.0], "stl": {"triangles": 12, "watertight": True}}
        if anchors is not None:
            res["dim_anchors"] = anchors
        return {"ok": True, "seconds": 0.1, "result": res}
    monkeypatch.setattr(sandbox, "run", run)
    return seen


def test_param_ersetzung_mit_kommentar():
    from app import jobs
    assert jobs.set_const("VAR = 75.0  # Kommentar\nB = 2\n", "VAR", 45.0) == ("VAR = 45  # Kommentar\nB = 2\n", 1)
    assert jobs.set_const("VAR=1\n", "VAR", 12.3456) == ("VAR=12.346\n", 1)
    assert jobs.set_const("VAR = 2 * B\n", "VAR", 3.0) == ("VAR = 2 * B\n", 0)
    assert jobs.set_const("VAR_X = 1\n", "VAR", 3.0)[1] == 0


def test_param_version_ohne_ki_mit_ankern(user, monkeypatch):
    from app import ai, db, jobs
    calls, real = [], ai.call
    monkeypatch.setattr(ai, "call", lambda *a, **k: (calls.append(a[0]), real(*a, **k))[1])
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert r.status_code == 200 and r.json() == {"version": 2}, r.text
    j = _wait(user, jid)
    v = j["versions"][-1]
    assert calls == [] and j["status"] == "done" and j["current_version"] == 2, j
    assert (v["trigger"], v["request_text"], v["claude_text"], v["status"]) == ("param", "D2 = 45 mm", "", "ok")
    assert "BLOCK_H = 45  # Hoehe, Annahme\n" in v["code"] and v["result"]["bbox"] == [40.0, 40.0, 45.0]
    d = {x["id"]: x for x in v["meta"]["dimensions"]}
    assert (d["D2"]["value"], d["D2"]["assumed"], d["D2"]["user_set"], d["D2"]["derived_from"]) == (45.0, False, True, None)
    assert v["result"]["dim_anchors"]["D2"] == [[20.0, -20.0, 0.0], [20.0, -20.0, 45.0]]
    assert d["D2"]["b"] == [20.0, -20.0, 45.0] and "anchors_stale" not in d["D1"] and d["D3"]["anchors_stale"] is True
    assert 0 < v["seconds"] < 30
    assert j["pending_param"] == [{"id": "D2", "label": "Höhe Block", "value": 45.0, "old": 75.0, "old_assumed": True}]
    msgs = db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"])
    assert msgs[-1]["content"][0]["text"] == "Parametrisch geändert: D2 = 45 mm (Version 2)"
    assert [(x["label"], x["value"], x["dim_id"], x["job_id"]) for x in jobs.learned_dims(pid)] == \
        [("Höhe Block", 45.0, "D2", jid)]


def test_param_mehrere_werte_und_fehler(user, monkeypatch):
    from app import db, sandbox
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    r = user.post(url, json={"values": [{"id": "D4", "value": 2}]}, headers=H)
    assert r.status_code == 400 and r.json()["detail"] == "Maß D4 ist nicht editierbar"
    assert user.post(url, json={"values": [{"id": "D9", "value": 2}]}, headers=H).status_code == 400
    assert user.post(url, json={"values": [{"id": "D1", "value": 1}] * 21}, headers=H).status_code == 422
    assert user.post(url, json={"values": []}, headers=H).status_code == 422
    monkeypatch.setattr(sandbox, "worker_alive", lambda: False)
    assert user.post(url, json={"values": [{"id": "D1", "value": 41}]}, headers=H).status_code == 503
    monkeypatch.setattr(sandbox, "worker_alive", lambda: True)
    db.ex("UPDATE jobs SET status='running' WHERE id=?", (jid,))
    r = user.post(url, json={"values": [{"id": "D1", "value": 41}]}, headers=H)
    assert r.status_code == 409 and r.json()["detail"] == "Der Auftrag läuft noch."
    db.ex("UPDATE jobs SET status='done' WHERE id=?", (jid,))
    assert db.q1("SELECT COUNT(*) n FROM job_versions WHERE job_id=?", (jid,))["n"] == 1   # Fehlversuche: keine Version
    r = user.post(url, json={"values": [{"id": "D1", "value": 41}, {"id": "D3", "value": 6.5}]}, headers=H)
    assert r.status_code == 200
    v = _wait(user, jid)["versions"][-1]
    assert v["request_text"] == "D1 = 41 mm, D3 = 6.5 mm" and v["status"] == "ok"
    assert "BLOCK_L = 41  # Laenge\n" in v["code"] and "\nHOLE_D = 6.5\n" in v["code"]


def test_param_ungueltige_werte(user, monkeypatch):
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    for bad in (0, -1, 5000.5, "abc", None):
        assert user.post(url, json={"values": [{"id": "D1", "value": bad}]}, headers=H).status_code == 422, bad
    for raw in ('{"values": [{"id": "D1", "value": NaN}]}', '{"values": [{"id": "D1", "value": Infinity}]}'):
        r = user.post(url, content=raw, headers={**H, "Content-Type": "application/json"})
        assert r.status_code == 422, raw
    assert user.post(url, json={"values": [{"id": "d1", "value": 2}]}, headers=H).status_code == 422
    r = user.post(url, json={"values": [{"id": "D1", "value": 0.0001}]}, headers=H)
    assert r.status_code == 400 and "größer als 0" in r.json()["detail"]


def test_param_basis_veraltet(user, monkeypatch):
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    url = f"/api/jobs/{jid}/param"
    r = user.post(url, json={"values": [{"id": "D1", "value": 41}], "base": 7}, headers=H)
    assert r.status_code == 409 and "nicht mehr aktuell" in r.json()["detail"]
    assert user.post(url, json={"values": [{"id": "D1", "value": 41}], "base": 1}, headers=H).status_code == 200
    _wait(user, jid)
    r = user.post(url, json={"values": [{"id": "D1", "value": 42}], "base": 1}, headers=H)     # zweiter Tab, alter Stand
    assert r.status_code == 409


def test_version_rueckfall_gestreckt_und_stale(user, monkeypatch):
    _fake_sandbox(monkeypatch)                                         # Ergebnis ohne dim_anchors
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    d = {x["id"]: x for x in _wait(user, jid)["versions"][-1]["meta"]["dimensions"]}
    assert d["D2"]["b"] == [20.0, -20.0, 45.0] and "anchors_stale" not in d["D2"]
    assert d["D1"]["anchors_stale"] is True and d["D3"]["anchors_stale"] is True and "a" not in d["D4"]


def test_version_huellquader_ohne_ki_erwartung(user, monkeypatch):
    """bbox_expected der KI gilt fuer den alten Wert: ohne Entfernen scheiterte jeder groessere Neuaufbau (75 -> 45)."""
    _fake_sandbox(monkeypatch)                                         # Ergebnis 40 x 40 x 45
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, {**copy.deepcopy(BLOCK_META), "bbox_expected": [40.0, 40.0, 75.0]})
    user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    j = _wait(user, jid)
    v = j["versions"][-1]
    assert j["status"] == "done" and v["status"] == "ok", v["checks"]
    assert "bbox_expected" not in v["meta"] and "bbox" not in {c["id"] for c in v["checks"]}


def test_version_sandbox_fehler_basis_bleibt(user, monkeypatch):
    from app import db, jobs
    _fake_sandbox(monkeypatch, ok=False)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    assert user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 200
    j = _wait(user, jid)
    assert j["status"] == "failed" and j["current_version"] == 1 and j["versions"][-1]["status"] == "failed"
    assert any(x["msg"] == "Version 2: Neuaufbau mit D2 = 45 mm fehlgeschlagen – ValueError (Zeile 3): kaputt"
               for x in j["log"]), j["log"]
    assert j["pending_param"] == [] and [x["value"] for x in jobs.learned_dims(pid)] == [45.0]   # §2.4: Wert bleibt
    assert db.jload(db.q1("SELECT messages FROM jobs WHERE id=?", (jid,))["messages"]) == []


def test_version_abbrechen(user, monkeypatch):
    _fake_sandbox(monkeypatch, block=True)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert user.post(f"/api/jobs/{jid}/cancel", headers=H).status_code == 200
    j = _wait(user, jid)
    assert j["status"] == "cancelled" and j["current_version"] == 1
    time.sleep(0.5)
    assert user.get(f"/api/jobs/{jid}").json()["versions"][-1]["status"] == "cancelled"


def test_param_ohne_projekt(user, monkeypatch):
    from app import db
    _fake_sandbox(monkeypatch)
    jid = _job(user, None, BLOCK, copy.deepcopy(BLOCK_META))
    r = user.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H)
    assert r.json() == {"version": 2, "learned": False}
    assert _wait(user, jid)["status"] == "done"
    assert db.q1("SELECT COUNT(*) n FROM model_dims WHERE job_id=?", (jid,))["n"] == 0


def test_param_fremder_nutzer(user, app, admin, monkeypatch):
    from fastapi.testclient import TestClient
    _fake_sandbox(monkeypatch)
    pid = _proj(user)
    jid = _job(user, pid, BLOCK, copy.deepcopy(BLOCK_META))
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremdb{jid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.post(f"/api/jobs/{jid}/param", json={"values": [{"id": "D2", "value": 45}]}, headers=H).status_code == 404


def test_version_pending_param_reihenfolge(user):
    from app import jobs
    pid = _proj(user)
    m = copy.deepcopy(BLOCK_META)
    jid = _job(user, pid, BLOCK, m)

    def meta(**vals):
        out = copy.deepcopy(m)
        for d in out["dimensions"]:
            if d["id"] in vals:
                d.update(value=vals[d["id"]], assumed=False, user_set=True)
        return out
    _version(jid, 2, "param", "ok", meta(D2=45.0), "D2 = 45 mm")
    _version(jid, 3, "param", "failed", meta(D2=45.0, D1=50.0), "D1 = 50 mm")
    _version(jid, 4, "param", "ok", meta(D2=45.0, D1=41.0), "D1 = 41 mm")
    assert jobs.pending_param(jid) == [
        {"id": "D2", "label": "Höhe Block", "value": 45.0, "old": 75.0, "old_assumed": True},
        {"id": "D1", "label": "Länge", "value": 41.0, "old": 40.0, "old_assumed": False}]
    _version(jid, 5, "iterate", "ok", meta(D2=45.0, D1=41.0))
    _version(jid, 6, "iterate", "failed", meta())
    assert jobs.pending_param(jid) == []
    _version(jid, 7, "param", "ok", meta(D2=45.0, D1=41.0, D3=6.5), "D3 = 6.5 mm")
    assert jobs.pending_param(jid) == [{"id": "D3", "label": "Bohrung", "value": 6.5, "old": 6.0, "old_assumed": False}]
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py -k "param or version"`
Expected: FAIL – `AttributeError: module 'app.jobs' has no attribute 'set_const'`; die API-Tests mit 404 (Route fehlt).

- [ ] **Step 3: Implementierung**

`web/app/jobs.py` – nach `_iterate_locked` einfügen:

```python
# ------------------------------------------------------------------ Parametrischer Neuaufbau (Spec Stufe B §2)

PARAM_MAX = 20


def _num(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def set_const(code: str, var: str, value: float) -> tuple[str, int]:
    """Zahl der Zeile `VAR = alt` ersetzen; Abstaende und Kommentar bleiben."""
    pat = re.compile(rf"^({var}\s*=\s*)([0-9]+(?:\.[0-9]+)?)(\s*(?:#.*)?)$", re.M)
    return pat.subn(lambda m: m.group(1) + _num(value) + m.group(3), code, count=1)


def _param_ids(text: str | None) -> list[str]:
    return re.findall(r"\b(D[0-9]{1,4}) = ", text or "")


def param(user: dict, job: dict, values: list[dict], base: int | None = None) -> dict:
    """Konstanten der aktuellen Version ersetzen und ohne KI neu bauen. Pruefen, Lernen, Version anlegen und
    status=queued in einem Block unter _lock; die Sandbox laeuft danach im Pool (Abbrechen wie bisher)."""
    if not sandbox.worker_alive():
        raise HTTPException(503, "Die CAD-Sandbox läuft nicht (Dienst „sandbox“ prüfen).")
    with _lock:
        job = db.q1("SELECT * FROM jobs WHERE id=?", (job["id"],))
        if not job or job["status"] in ("queued", "running"):
            raise HTTPException(409, "Der Auftrag läuft noch.")
        cur = job["current_version"]
        bv = db.q1("SELECT code, meta FROM job_versions WHERE job_id=? AND version=?", (job["id"], cur)) if cur else None
        if not bv:
            raise HTTPException(409, "Es gibt noch keine Version, auf der aufgebaut werden kann.")
        if base is not None and base != cur:
            raise HTTPException(409, f"Version {base} ist nicht mehr aktuell (aktuell: Version {cur}) – bitte neu laden.")
        code, meta = bv["code"] or "", db.jload(bv["meta"], {}) or {}
        dims = {d.get("id"): d for d in meta.get("dimensions", []) if isinstance(d, dict)}
        changed: dict[str, float] = {}
        for it in values:
            d, new = dims.get(it["id"]), round(float(it["value"]), 3)
            if not d or not d.get("editable") or not d.get("var"):
                raise HTTPException(400, f"Maß {it['id']} ist nicht editierbar")
            if new <= 0:
                raise HTTPException(400, f"Maß {it['id']}: Der Wert muss größer als 0 sein.")
            code, n = set_const(code, d["var"], new)
            if not n:
                raise HTTPException(400, f"Maß {it['id']} ist nicht editierbar")
            d.update(value=new, assumed=False, user_set=True, derived_from=None)
            changed[d["id"]] = new
        req = ", ".join(f"{k} = {_num(v)} mm" for k, v in changed.items())
        meta.pop("bbox_expected", None)   # Erwartung der KI galt fuer die alten Werte: Hüllquader-Pruefung entfaellt
        if job["project_id"]:                       # §2.4: gemessen ist gemessen, unabhaengig vom Erfolg
            learn_dims(job["project_id"], job["id"], [dims[k] for k in changed])
        version = _new_version(job["id"], "param", req, "", {})
        db.ex("UPDATE job_versions SET code=?, meta=? WHERE job_id=? AND version=?",
              (code, db.jdump(meta), job["id"], version))
        _set(job["id"], status="queued", error=None)
        log(job["id"], f"Neuaufbau mit {req} …")
        db.audit("cad_param", f"Auftrag {job['id']}: {req}"[:500], user_id=user["id"], actor=user["username"])
        _submit(job["id"], "param", req)
    return {"version": version} if job["project_id"] else {"version": version, "learned": False}


def _run_param(job_id: int, ev: threading.Event):
    """Sandbox-Lauf der Param-Version: kein KI-Aufruf, kein Autofix; Fehler -> failed, Basis bleibt aktuell."""
    v = db.q1("SELECT * FROM job_versions WHERE job_id=? AND trigger='param' AND status='running' "
              "ORDER BY version DESC LIMIT 1", (job_id,))
    job = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not v:
        return
    if not job or job["status"] == "cancelled" or ev.is_set():
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND version=?", (job_id, v["version"]))
        return
    _set(job_id, status="running")
    version, code, req = v["version"], v["code"] or "", v["request_text"] or ""
    meta = db.jload(v["meta"], {}) or {}
    vdir = version_dir(job_id, version)
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "model.py").write_text(code, encoding="utf-8")
    res = sandbox.run(code, vdir, cancel=ev)
    if not db.q1("SELECT id FROM jobs WHERE id=?", (job_id,)):
        shutil.rmtree(job_dir(job_id), ignore_errors=True)
        return
    err = None if res["ok"] else res["error"]
    result = res.get("result")
    if result:
        _apply_anchors(meta, result, changed=set(_param_ids(req)))
    checks = compute_checks(result, meta, job["project_id"]) if result else []
    failed = err is not None or any(c["state"] == "fail" for c in checks)
    db.ex("UPDATE job_versions SET status=?, error=?, result=?, checks=?, seconds=?, meta=? WHERE job_id=? AND version=?",
          ("failed" if failed else "ok", db.jdump(err) if err else None, db.jdump(result) if result else None,
           db.jdump(checks), res.get("seconds"), db.jdump(meta), job_id, version))
    if failed:
        if err:
            where = f" (Zeile {err['line']})" if err.get("line") else ""
            why = f"{err.get('type')}{where}: {str(err.get('message'))[:200]}"
        else:
            why = "Prüfung nicht bestanden – " + "; ".join(c["label"] for c in checks if c["state"] == "fail")
        log(job_id, f"Version {version}: Neuaufbau mit {req} fehlgeschlagen – {why}", "warn")
        if _current(job_id, ev):
            _set(job_id, status="failed", error=f"Neuaufbau mit {req} fehlgeschlagen – {why}")
        return
    bb = result["bbox"]
    log(job_id, f"Version {version} fertig (Neuaufbau ohne KI): {_de(bb[0])} × {_de(bb[1])} × {_de(bb[2])} mm, "
                f"{_de(res['seconds'], 1)} s", "ok")
    with _lock:   # Gespraechszeile nur bei Erfolg: spaetere KI-Aenderungen kennen den Stand
        row = db.q1("SELECT messages FROM jobs WHERE id=?", (job_id,))
        msgs = db.jload(row["messages"], []) if row else []
        msgs.append({"role": "user", "content": [{"type": "text", "text": f"Parametrisch geändert: {req} (Version {version})"}]})
        _set(job_id, messages=db.jdump(msgs))
    if _current(job_id, ev):
        _set(job_id, status="done", current_version=version, error=None)


def pending_param(job_id: int) -> list[dict]:
    """§5: Masse aus erfolgreichen Param-Versionen nach der letzten erfolgreichen KI-Version."""
    vs = db.q("SELECT version, trigger, status, request_text, meta FROM job_versions WHERE job_id=? ORDER BY version",
              (job_id,))
    ai_ok = [v for v in vs if v["trigger"] != "param" and v["status"] == "ok"]
    if not ai_ok:
        return []
    last = ai_ok[-1]
    old = {d.get("id"): d for d in (db.jload(last["meta"], {}) or {}).get("dimensions", []) if isinstance(d, dict)}
    out: dict[str, dict] = {}
    for v in vs:
        if v["trigger"] != "param" or v["status"] != "ok" or v["version"] < last["version"]:
            continue
        dims = {d.get("id"): d for d in (db.jload(v["meta"], {}) or {}).get("dimensions", []) if isinstance(d, dict)}
        for i in _param_ids(v["request_text"]):
            if i in dims:
                o = old.get(i) or {}
                out[i] = {"id": i, "label": dims[i].get("label"), "value": dims[i].get("value"), "old": o.get("value"),
                          "old_assumed": bool(o.get("assumed"))}
    return list(out.values())
```

`_run` – am Anfang der Funktion vor `job = db.q1(...)` einfügen:

```python
    if trigger == "param":   # Spec Stufe B §2: Neuaufbau ohne KI und ohne Autofix
        _run_param(job_id, ev)
        return
```

`_run_safe` vollständig ersetzen (eine Version, die bei einem internen Fehler noch `running` ist, wird `failed`):

```python
def _run_safe(job_id, trigger, request_text, ev):
    try:
        _run(job_id, trigger, request_text, ev)
    except (ai.Cancelled, sandbox.Cancelled):
        db.ex("UPDATE job_versions SET status='cancelled' WHERE job_id=? AND status='running'", (job_id,))
        log(job_id, "Abgebrochen", "warn")
    except ai.AIError as e:
        if _current(job_id, ev):
            _set(job_id, status="failed", error=str(e))
        log(job_id, str(e), "error")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        db.ex("UPDATE job_versions SET status='failed' WHERE job_id=? AND status='running'", (job_id,))
        if _current(job_id, ev):
            _set(job_id, status="failed", error=f"Interner Fehler: {type(e).__name__}: {e}")
        log(job_id, f"Interner Fehler: {type(e).__name__}: {e}", "error")
    finally:
        with _lock:
            if _cancel.get(job_id) is ev:
                _cancel.pop(job_id, None)
```

`job_public` vollständig ersetzen:

```python
def job_public(job: dict, detail: bool = False) -> dict:
    out = {k: job[k] for k in ("id", "user_id", "project_id", "name", "status", "current_version", "error",
                               "created_at", "updated_at")}
    req = db.jload(job["request"], {})
    out["request"] = req
    cur = None
    if job["current_version"]:
        cur = db.q1("SELECT result FROM job_versions WHERE job_id=? AND version=?", (job["id"], job["current_version"]))
    r = db.jload(cur["result"], {}) if cur else {}
    out["bbox"] = r.get("bbox")
    out["n_versions"] = db.q1("SELECT COUNT(*) n FROM job_versions WHERE job_id=?", (job["id"],))["n"]
    if detail:
        vs = db.q("SELECT * FROM job_versions WHERE job_id=? ORDER BY version", (job["id"],))
        out["versions"] = [{
            "version": v["version"], "trigger": v["trigger"], "request_text": v["request_text"], "status": v["status"],
            "code": v["code"], "claude_text": v["claude_text"], "meta": db.jload(v["meta"], {}), "error": db.jload(v["error"]),
            "result": db.jload(v["result"]), "checks": db.jload(v["checks"], []), "usage": db.jload(v["usage"], {}),
            "seconds": v["seconds"], "created_at": v["created_at"], "files": version_files(job["id"], v["version"]),
        } for v in vs]
        out["log"] = db.q("SELECT ts,level,msg FROM job_log WHERE job_id=? ORDER BY id", (job["id"],))
        out["pending_param"] = pending_param(job["id"])
    return out
```

`web/app/main.py` – nach `job_iterate` einfügen:

```python
class ParamValue(BaseModel):
    id: str = Field(pattern=r"^D[0-9]{1,4}$")
    value: float   # Bereich im Endpunkt: ein Pydantic-Fehler mit NaN im Eingabewert liesse sich nicht als JSON melden


class ParamIn(BaseModel):
    values: list[ParamValue] = Field(min_length=1, max_length=jobs.PARAM_MAX)
    base: int | None = None


@app.post("/api/jobs/{jid}/param")
def job_param(jid: int, body: ParamIn, u: dict = Depends(auth.require_user)):
    """Spec Stufe B §2: Messschieberwerte in die Konstanten einsetzen, neue Version ohne KI."""
    for v in body.values:
        if not 0 < v.value <= 5000:            # faengt auch NaN und Unendlich ab
            raise HTTPException(422, f"Maß {v.id}: Der Wert muss größer als 0 und höchstens 5000 mm sein.")
    j = _own_job(jid, u)
    return jobs.param(u, j, [v.model_dump() for v in body.values], base=body.base)
```

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py tests/test_api.py tests/test_texts.py && ruff check web/app/jobs.py web/app/main.py tests/test_dims.py`
Expected: PASS (`test_texts.py` prüft die neuen `HTTPException`/`log`-Texte auf Markennamen).

- [ ] **Step 5: Commit**

```bash
git add web/app/jobs.py web/app/main.py tests/test_dims.py
git commit -m "Parametrischer Neuaufbau ohne KI: POST /api/jobs/{jid}/param, Gespraechszeile, pending_param"
```

### Task 6: Gelernte Werte in Prüfsumme, Projekt-API, Löschen und CSV

**Files:**
- Modify: `web/app/check.py:23-47` (`cad_hash` → `hash_blob` + `cad_hash`)
- Modify: `web/app/main.py` (`_project_public` Z. 746–761; neue Route nach `project_delete` Z. 865–870; `_csv` Z. 1594–1615)
- Test: `tests/test_dims.py`

**Interfaces:**
- Consumes: `jobs.learned_dims(project_id)`, `jobs.GROUP_TEXT` (Task 3).
- Produces:
  - `check.hash_blob(project: dict, photo_ids: list[int] | None, part_id: int | None) -> dict` – Schlüssel `photos, meas, parts, part_id, material` und nur bei gelernten Werten zusätzlich `model_dims` (`[[label_norm, value], …]`); `check.cad_hash(...)` = SHA-256 über `json.dumps(hash_blob(...), sort_keys=True, ensure_ascii=False)` (unverändert für Projekte ohne gelernte Werte).
  - `GET /api/projects/{pid}` → `model_dims: [{"id", "label", "grp", "value", "job_id", "dim_id", "created_at"}]`.
  - `DELETE /api/projects/{pid}/model-dims/{mid}` → `{"ok": true}`; 404 bei fremdem Projekt oder fremder Zeile.
  - CSV (`measurements.csv` und ZIP): je gelerntem Wert eine Zeile `D2;Höhe Block;außen;45;mm;;45;;;Modell;Auftrag 7;;;`.

- [ ] **Step 1: Failing tests** (an `tests/test_dims.py` anhängen)

```python
# ------------------------------------------------------------------ B4: Pruefsumme, API, CSV

def test_hash_ohne_gelernte_werte_unveraendert(user):
    """Bestehende Projekte: Pruefsumme ohne model_dims-Schluessel, sonst waere jede gespeicherte Pruefung veraltet."""
    import hashlib

    from app import check, db
    pid = _proj(user)
    p = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    blob = check.hash_blob(p, None, None)
    assert set(blob) == {"photos", "meas", "parts", "part_id", "material"}
    assert check.cad_hash(p, None, None) == hashlib.sha256(
        json.dumps(blob, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def test_lernen_hash_veraltet_und_loeschen(user):
    from app import check, db, jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})

    def h():
        return check.cad_hash(db.q1("SELECT * FROM projects WHERE id=?", (pid,)), None, None)
    h0 = h()
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    assert h() != h0
    md = user.get(f"/api/projects/{pid}").json()["model_dims"]
    assert [(m["label"], m["value"], m["grp"], m["dim_id"], m["job_id"]) for m in md] == \
        [("Höhe Block", 45.0, "aussen", "D2", jid)]
    assert set(md[0]) == {"id", "label", "grp", "value", "job_id", "dim_id", "created_at"}
    assert user.delete(f"/api/projects/{pid}/model-dims/{md[0]['id']}", headers=H).json() == {"ok": True}
    assert user.get(f"/api/projects/{pid}").json()["model_dims"] == [] and h() == h0
    assert user.delete(f"/api/projects/{pid}/model-dims/{md[0]['id']}", headers=H).status_code == 404


def test_lernen_loeschen_fremd(user, app, admin):
    from fastapi.testclient import TestClient

    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "Höhe Block", "group": "aussen", "value": 45.0}])
    mid = jobs.learned_dims(pid)[0]["id"]
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    f.post(f"/api/invite/{tok}", json={"username": f"fremdm{pid}", "display_name": "Fremd",
                                       "password": "Schieblehre-Messing-7"}, headers=H)
    own = f.post("/api/projects", json={"name": "f"}, headers=H).json()["id"]
    assert f.delete(f"/api/projects/{pid}/model-dims/{mid}", headers=H).status_code == 404
    assert f.delete(f"/api/projects/{own}/model-dims/{mid}", headers=H).status_code == 404
    assert len(jobs.learned_dims(pid)) == 1


def test_lernen_csv_modell_zeilen(user):
    from app import jobs
    pid = _proj(user)
    jid = _job(user, pid, "X = 1\n", {"dimensions": []})
    jobs.learn_dims(pid, jid, [{"id": "D2", "label": "=Höhe", "group": "aussen", "value": 45.5}])
    csv = user.get(f"/api/projects/{pid}/measurements.csv").text
    assert f"\r\nD2;'=Höhe;außen;45,5;mm;;45,5;;;Modell;Auftrag {jid};;;\r\n" in csv
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py -k "hash or lernen_hash or loeschen or csv"`
Expected: FAIL – `AttributeError: module 'app.check' has no attribute 'hash_blob'`, `KeyError: 'model_dims'`.

- [ ] **Step 3: Implementierung**

`web/app/check.py` – `cad_hash` vollständig ersetzen durch:

```python
def hash_blob(project: dict, photo_ids: list[int] | None, part_id: int | None) -> dict:
    """Inhalt der Pruefsumme; photo_ids=None = alle Fotos zum Zeitpunkt der Berechnung (Spec §2.1)."""
    pid = project["id"]
    photos = [p for p in db.q("SELECT * FROM photos WHERE project_id=? ORDER BY id", (pid,))
              if photo_ids is None or p["id"] in photo_ids]
    al = []
    for p in photos:
        b = (db.jload(p["analysis"], {}) or {}).get("bottom_align") or {}
        al.append([p["id"], p["view"], p["format"], p["status"], b.get("rot"), _r(b.get("dx")), _r(b.get("dy")),
                   *([_r(b["phi"])] if b.get("phi") else [])])   # phi nur wenn gesetzt: Hash alter Datensaetze bleibt gleich
    ms = []
    for m in db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY id", (pid,)):
        d = db.jload(m["data"], {}) or {}
        ms.append([m["id"], m["kind"], _r(m["value"]), _r(m["caliper"]), _r(m["unc"]), m["part_id"], d.get("view"),
                   [[_r(x), _r(y)] for x, y in d.get("points") or []]])
    ps = []
    for t in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY id", (pid,)):
        d = db.jload(t["data"], {}) or {}
        ps.append([t["id"], t["label"], t["role"], [[_r(x), _r(y)] for x, y in d["polygon"]], d.get("hidden"),
                   d.get("holes"), d.get("same_as")])
    mat = ([project.get("color"), project.get("material"), project.get("transparent"), project.get("finish")]
           if project.get("material_user") else None)
    blob = {"photos": al, "meas": ms, "parts": ps, "part_id": part_id, "material": mat}
    md = [[r["label_norm"], _r(r["value"])] for r in jobs.learned_dims(pid)]
    if md:   # Stufe B §4: neuer oder geloeschter Messschieberwert macht die Pruefung veraltet; ohne Werte Hash wie bisher
        blob["model_dims"] = md
    return blob


def cad_hash(project: dict, photo_ids: list[int] | None, part_id: int | None) -> str:
    """Pruefsumme des Projektstands (Spec §2.1)."""
    blob = json.dumps(hash_blob(project, photo_ids, part_id), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()
```

`web/app/main.py` – in `_project_public` im `if detail:`-Block nach `out["parts"] = parts.public_list(p["id"])` einfügen:

```python
        out["model_dims"] = [{k: r[k] for k in ("id", "label", "grp", "value", "job_id", "dim_id", "created_at")}
                             for r in jobs.learned_dims(p["id"])]
```

Nach `project_delete` einfügen:

```python
@app.delete("/api/projects/{pid}/model-dims/{mid}")
def model_dim_delete(pid: int, mid: int, u: dict = Depends(auth.require_user)):
    """Spec Stufe B §4: gelernten Messschieberwert loeschen (die Pruefung wird damit veraltet)."""
    _own_project(pid, u)
    if not db.q1("SELECT id FROM model_dims WHERE id=? AND project_id=?", (mid, pid)):
        raise HTTPException(404, "Messschieberwert nicht gefunden")
    db.ex("DELETE FROM model_dims WHERE id=?", (mid,))
    return {"ok": True}
```

`_csv` vollständig ersetzen:

```python
def _csv(pid: int) -> str:
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY seq", (pid,))

    def n(v):
        return "" if v is None else f"{v:.3f}".rstrip("0").rstrip(".").replace(".", ",")

    def safe_txt(t: str) -> str:   # keine Formeln in Tabellenprogrammen
        return ("'" + t) if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t

    def cell(c) -> str:
        s = str(c)
        return '"' + s.replace('"', '""') + '"' if any(x in s for x in ';"\n') else s

    lines = ["ID;Bezeichnung;Art;Wert;Einheit;Unsicherheit;Messschieber;kritisch;Passung;Quelle;Ansicht;Punkte (mm);Teil;Nennmaß"]
    seq = {t["id"]: t["seq"] for t in db.q("SELECT id, seq FROM parts WHERE project_id=?", (pid,))}
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (pid,))}
    for m in rows:
        d = db.jload(m["data"], {}) or {}
        tag, tpts = jobs.top_points(m, d, photos)
        pts = " ".join(f"{p[0]:.2f}/{p[1]:.2f}" for p in tpts)
        cells = [f"M{m['seq']}", safe_txt(m["label"]), KIND_LABEL.get(m["kind"], m["kind"]), n(m["value"]), m["unit"],
                 n(m["unc"]),
                 n(m["caliper"]), "ja" if m["critical"] else "", safe_txt(m["fit"] or ""),
                 jobs.SOURCE_LABEL.get(m["source"], m["source"]), f"{d.get('view', '')} {tag}".strip(), pts,
                 f"T{seq[m['part_id']]}" if m["part_id"] in seq else "", n(d.get("nominal"))]
        lines.append(";".join(cell(c) for c in cells))
    for r in jobs.learned_dims(pid):   # Stufe B §4: Messschieber am Modell, Quelle „Modell“
        cells = [r["dim_id"] or "", safe_txt(r["label"]), jobs.GROUP_TEXT.get(r["grp"], r["grp"]), n(r["value"]), "mm", "",
                 n(r["value"]), "", "", "Modell", f"Auftrag {r['job_id']}" if r["job_id"] else "", "", "", ""]
        lines.append(";".join(cell(c) for c in cells))
    return "﻿" + "\r\n".join(lines) + "\r\n"
```

(Der String vor dem ersten `+` in der `return`-Zeile ist wie bisher die BOM U+FEFF: die bestehende `return`-Zeile beim Übernehmen unverändert lassen.)

- [ ] **Step 4: Tests grün, ruff**

Run: `python -m pytest -q -p no:cacheprovider tests/test_dims.py tests/test_check.py tests/test_api.py && ruff check web/app/check.py web/app/main.py tests/test_dims.py`
Expected: PASS (`test_check.py` deckt Idempotenz und `stale` der Prüfung ohne gelernte Werte ab).

- [ ] **Step 5: Commit und Wellenabschluss** (lokale Suite und CI, siehe Global Constraints)

```bash
git add web/app/check.py web/app/main.py tests/test_dims.py
git commit -m "Gelernte Werte: Pruefsumme, model_dims am Projekt, Loeschen, CSV mit Quelle Modell"
```

Danach die lokale Suite aus den Global Constraints, dann den Branch pushen und den Entwurfs-PR öffnen (wie Stufe A nach W1; erst der PR startet die CI), danach den CI-Teil des Wellenabschlusses (Warten auf den Lauf zum gepushten Stand):

```bash
cat > /tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad/stufe_b/pr.md <<'EOF'
Stufe B: Bemaßung am Modell (Spec docs/superpowers/specs/2026-10-15-bemassung-am-modell-design.md,
Plan docs/superpowers/plans/2026-10-15-bemassung-am-modell.md).

Welle 1 (Server): Maße mit D-Nummern, ref und var, DIM_ANCHORS im Läufer, editierbare Konstanten und Anker,
parametrischer Neuaufbau ohne KI (POST /api/jobs/{jid}/param), gelernte Werte am Projekt (model_dims) in Messtabelle,
Änderungswunsch, Prüfsumme und CSV, pending_param.
Welle 2 (Oberfläche) und Welle 3 (Browser-Durchlauf, Abnahme) folgen auf diesem Branch.
EOF
git push -u origin bemassung-am-modell
gh pr create --draft --base main --head bemassung-am-modell --title "Stufe B: Bemaßung am Modell" \
  --body-file /tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad/stufe_b/pr.md
```

---

## Welle 2 – Oberfläche

### Task 7: Reine Funktionen der Bemaßung in `geom.js`

**Files:**
- Modify: `web/static/js/geom.js` (Kopfkommentar Z. 1; neue Funktionen am Dateiende)
- Create: `tests/js/dims.test.mjs`

**Interfaces:**
- Consumes: Maßeinträge der Meta (`id`, `label`, `group`, `value`, `assumed`, `user_set`, `derived_from`, `anchors_stale`, `a`, `b`) und `pending_param` (`{id, label, value, old, old_assumed}`).
- Produces (alle ohne DOM):
  - `DIM_GROUP_KEYS = ["aussen", "bohrung", "tiefe", "fase", "platte", "sonst"]`
  - `DEFAULT_SEL = { aussen: true, bohrung: false, tiefe: false, fase: false, platte: false, sonst: false, annahmen: true, nur_annahmen: false }` (eingefroren)
  - `dimSel(raw: string | null) -> sel` – gespeicherte Auswahl (`localStorage` `dims.groups`) lesen, nur bekannte Schlüssel mit Wahrheitswert
  - `visibleDims(dims, sel) -> dims` – Gruppenregel der Spec §3
  - `hasAnchors(d) -> boolean`
  - `dimGeometry(a, b, center, size) -> { line: [p, q], ext: [[a, a2], [b, b2]], label: [x, y, z], off } | null`
  - `DIM_COLORS`, `dimStyle(d) -> { color, dashed }`, `dimState(d) -> string`
  - `de(v) -> string` (bis 3 Nachkommastellen, Dezimalkomma, ohne Tausenderpunkt – für Eingabefelder)
  - `parseDimInput(s) -> { value } | { error }`
  - `paramIds(text) -> string[]`, `paramBanner(list) -> string`, `conclusionText(list) -> string`

- [ ] **Step 1: Failing tests** – `tests/js/dims.test.mjs` neu:

```js
// Bemaßung am Modell (web/static/js/geom.js, Spec Stufe B §3/§5, B5) – Aufruf: node --test tests/js/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_SEL, dimSel, visibleDims, hasAnchors, dimGeometry, dimStyle, dimState, de, parseDimInput, paramIds,
  paramBanner, conclusionText } from "../../web/static/js/geom.js";

const near = (act, exp) => {   // flach vergleichen; -0 und Rundungsreste zaehlen nicht
  const a = act.flat(Infinity), e = exp.flat(Infinity);
  assert.equal(a.length, e.length);
  a.forEach((v, i) => assert.ok(Math.abs(v - e[i]) < 1e-9, `${JSON.stringify(act)} != ${JSON.stringify(exp)}`));
};

test("dimGeometry: Versatz 8 % weg vom Modell, Hilfslinien mit Überstand", () => {
  const g = dimGeometry([0, 0, 0], [10, 0, 0], [5, 5, 0], 100);
  near(g.line, [[0, -8, 0], [10, -8, 0]]);
  near(g.ext, [[[0, 0, 0], [0, -10, 0]], [[10, 0, 0], [10, -10, 0]]]);
  near(g.label, [5, -8, 0]);
  assert.equal(g.off, 8);
});

test("dimGeometry: mindestens 2 mm Versatz bei kleinen Modellen", () => {
  const g = dimGeometry([0, 0, 0], [10, 0, 0], [5, 5, 0], 10);
  near(g.line, [[0, -2, 0], [10, -2, 0]]);
  assert.equal(g.off, 2);
});

test("dimGeometry: Mitte auf der Linie -> Z, bei senkrechter Linie X; Nulllänge -> null", () => {
  near(dimGeometry([-5, 0, 0], [5, 0, 0], [0, 0, 0], 100).line, [[-5, 0, 8], [5, 0, 8]]);
  near(dimGeometry([0, 0, 0], [0, 0, 10], [0, 0, 5], 100).line, [[8, 0, 0], [8, 0, 10]]);
  assert.equal(dimGeometry([1, 1, 1], [1, 1, 1], [0, 0, 0], 100), null);
});

test("visibleDims: Gruppen, Annahmen, Nur Annahmen, unbekannte Gruppe = sonst", () => {
  const dims = [{ id: "D1", group: "aussen" }, { id: "D2", group: "bohrung", assumed: true }, { id: "D3", group: "bohrung" },
    { id: "D4", group: "komisch" }, { id: "D5" }];
  const ids = sel => visibleDims(dims, sel).map(d => d.id);
  assert.deepEqual(ids(DEFAULT_SEL), ["D1", "D2"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, annahmen: false }), ["D1"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, nur_annahmen: true }), ["D2"]);
  assert.deepEqual(ids({ ...DEFAULT_SEL, aussen: false, annahmen: false, sonst: true }), ["D4", "D5"]);
});

test("dimSel: Müll im Speicher ergibt die Standardwahl", () => {
  for (const raw of [null, undefined, "", "kein json", "5", "[true]", "null"]) assert.deepEqual(dimSel(raw), { ...DEFAULT_SEL });
  assert.deepEqual(dimSel('{"bohrung":true,"aussen":"ja","x":true}'), { ...DEFAULT_SEL, bohrung: true });
});

test("hasAnchors: nur je drei endliche Zahlen", () => {
  assert.equal(hasAnchors({ a: [0, 0, 0], b: [1, 0, 0] }), true);
  assert.equal(hasAnchors({ a: [0, 0], b: [1, 0, 0] }), false);
  assert.equal(hasAnchors({ a: [0, 0, "1"], b: [1, 0, 0] }), false);
  assert.equal(hasAnchors({ a: [0, 0, NaN], b: [1, 0, 0] }), false);
  assert.equal(hasAnchors({}), false);
});

test("dimStyle und dimState", () => {
  assert.deepEqual(dimStyle({ anchors_stale: true, assumed: true }), { color: "#8a939b", dashed: true });
  assert.deepEqual(dimStyle({ assumed: true }), { color: "#b42318", dashed: false });
  assert.deepEqual(dimStyle({ user_set: true }), { color: "#1a7f37", dashed: false });
  assert.deepEqual(dimStyle({ derived_from: "D3" }), { color: "#1f6fb2", dashed: true });
  assert.deepEqual(dimStyle({}), { color: "#1f6fb2", dashed: false });
  assert.equal(dimState({ assumed: true }), "Annahme");
  assert.equal(dimState({ user_set: true }), "nachgemessen");
  assert.equal(dimState({ derived_from: "D3" }), "abgeleitet von D3");
  assert.equal(dimState({}), "");
});

test("de: Dezimalkomma, höchstens drei Stellen, kein Tausenderpunkt", () => {
  assert.equal(de(45), "45");
  assert.equal(de(12.3456), "12,346");
  assert.equal(de(0.1 + 0.2), "0,3");
  assert.equal(de(1234.5), "1234,5");
});

test("parseDimInput: Komma, Leerzeichen, Unsinn und Grenzen", () => {
  assert.deepEqual(parseDimInput("45,5"), { value: 45.5 });
  assert.deepEqual(parseDimInput(" 45 "), { value: 45 });
  assert.deepEqual(parseDimInput("45.5"), { value: 45.5 });
  assert.deepEqual(parseDimInput("12,34567"), { value: 12.346 });
  for (const s of ["", "  ", null]) assert.equal(parseDimInput(s).error, "Bitte einen Wert eingeben.");
  for (const s of ["abc", "4 5", "0x10", "1e3", "-5", "1.234,5", "45 mm"]) assert.match(parseDimInput(s).error, /Kein gültiger Wert/);
  for (const s of ["0", "0,0001", "5000,1"]) assert.match(parseDimInput(s).error, /größer als 0 und höchstens 5000/);
  assert.deepEqual(parseDimInput("5000"), { value: 5000 });
});

test("paramIds, paramBanner, conclusionText", () => {
  assert.deepEqual(paramIds("D3 = 45 mm, D12 = 6.5 mm"), ["D3", "D12"]);
  assert.deepEqual(paramIds(null), []);
  const p3 = { id: "D3", label: "Dicke", value: 8, old: 6, old_assumed: true };
  const p4 = { id: "D4", label: "Bohrung Ø", value: 4.7, old: 4.5, old_assumed: false };
  assert.equal(paramBanner([p3]), "8 mm ersetzt eine Annahme (6 mm) – Schlüsse auf abhängige Maße ziehen?");
  assert.equal(paramBanner([p4]), "");                                                     // 4,4 %: kein Banner
  assert.equal(paramBanner([{ ...p4, value: 5.5 }]), "5,5 mm statt 4,5 mm (Bohrung Ø) – Schlüsse auf abhängige Maße ziehen?");
  assert.equal(paramBanner([]), "");
  assert.equal(conclusionText([p3, p4]), "Nachgemessen mit dem Messschieber: D3 Dicke = 8 mm (vorher Annahme 6); "
    + "D4 Bohrung Ø = 4,7 mm (vorher 4,5). Leite daraus abhängige Maße ab (Tiefen, Dicken, Abstände, die an diesen Maßen "
    + "hängen), trage bei jedem geänderten Maß derived_from und eine kurze Begründung ein und ändere sonst nichts.");
  assert.equal(conclusionText([{ ...p3, old: null, old_assumed: false }]).startsWith("Nachgemessen mit dem Messschieber: D3 Dicke = 8 mm. "), true);
  assert.equal(conclusionText([]), "");
});
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `cd /root/Snap2CAD && node --test tests/js/dims.test.mjs`
Expected: FAIL – `SyntaxError: The requested module '../../web/static/js/geom.js' does not provide an export named 'DEFAULT_SEL'`.

- [ ] **Step 3: Implementierung** – `web/static/js/geom.js`: Kopfkommentar ersetzen durch `// Reine Geometrie fuer Messen, Kanten-Werkzeug und Bemaßung am Modell, ohne DOM (geprueft mit node --test tests/js/*.test.mjs)` und am Dateiende anfügen:

```js
// ------------------------------------------------------------------ Bemaßung am Modell (Spec Stufe B §3/§5, B5)

export const DIM_GROUP_KEYS = ["aussen", "bohrung", "tiefe", "fase", "platte", "sonst"];
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
// sichtbar: Gruppe an oder (Annahme und „Annahmen“ an); „Nur Annahmen“: nur Annahmen, gleich welche Gruppe
export function visibleDims(dims, sel) {
  if (sel.nur_annahmen) return dims.filter(d => d.assumed === true);
  return dims.filter(d => sel[groupOf(d)] === true || (d.assumed === true && sel.annahmen === true));
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
// liegt die Mitte auf der Linie, zeigt der Versatz nach +Z, bei senkrechter Linie nach +X
export function dimGeometry(a, b, center, size) {
  const ab = vsub(b, a), n = vlen(ab);
  if (!(n > 1e-9)) return null;
  const u = vmul(ab, 1 / n), m = vmul(vadd(a, b), 0.5);
  const off = Math.max(0.08 * size, 2), over = off * 0.25;
  let w = vperp(vsub(m, center), u);
  if (vlen(w) < 1e-6 * Math.max(1, size)) {
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

export const de = v => String(Math.round(v * 1000) / 1000).replace(".", ",");

// Eingabe im Label oder in der Tabelle: Ziffern mit Komma oder Punkt, 0 < Wert <= 5000 mm, auf 3 Stellen gerundet
export function parseDimInput(s) {
  const t = String(s ?? "").trim();
  if (!t) return { error: "Bitte einen Wert eingeben." };
  if (!/^\d+(?:[.,]\d+)?$/.test(t)) return { error: "Kein gültiger Wert – z. B. 45 oder 45,5." };
  const v = Math.round(Number(t.replace(",", ".")) * 1000) / 1000;
  if (!(v > 0 && v <= 5000)) return { error: "Der Wert muss größer als 0 und höchstens 5000 mm sein." };
  return { value: v };
}

export function paramIds(text) { return [...String(text || "").matchAll(/\b(D\d{1,4}) = /g)].map(m => m[1]); }

const BANNER_TAIL = " – Schlüsse auf abhängige Maße ziehen?";
// Hinweis nach einem Neuaufbau: Mass war Annahme oder neuer Wert weicht mehr als 10 % vom alten ab
export function paramBanner(list) {
  const parts = list.filter(p => p.old_assumed || (p.old > 0 && Math.abs(p.value - p.old) > 0.1 * p.old))
    .map(p => (p.old_assumed ? `${de(p.value)} mm ersetzt eine Annahme (${de(p.old)} mm)` : `${de(p.value)} mm statt ${de(p.old)} mm (${p.label})`));
  return parts.length ? parts.join("; ") + BANNER_TAIL : "";
}

// Text des Aenderungswunsches fuer „Schluesse ziehen“ (Spec §5)
export function conclusionText(list) {
  if (!list.length) return "";
  const items = list.map(p => `${p.id} ${p.label} = ${de(p.value)} mm`
    + (p.old == null ? "" : ` (vorher ${p.old_assumed ? "Annahme " : ""}${de(p.old)})`));
  return `Nachgemessen mit dem Messschieber: ${items.join("; ")}. Leite daraus abhängige Maße ab (Tiefen, Dicken, Abstände, `
    + "die an diesen Maßen hängen), trage bei jedem geänderten Maß derived_from und eine kurze Begründung ein und ändere sonst nichts.";
}
```

- [ ] **Step 4: Tests grün**

Run: `node --test tests/js/*.test.mjs && node --check web/static/js/geom.js`
Expected: PASS (auch die bestehenden `geom.test.mjs` und `lib.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git add web/static/js/geom.js tests/js/dims.test.mjs
git commit -m "Viewer-Geometrie: Masslinien, Gruppenfilter, Eingabe und Texte als reine Funktionen"
```

### Task 8: Viewer mit Bemaßungslinien, Gruppen, Eingabe und Hervorheben (`viewer.js`, `app.css`)

**Files:**
- Modify: `web/static/js/viewer.js` (vollständig ersetzt, unten)
- Modify: `web/static/css/app.css:262` (nach `.dimlabel`)

**Interfaces:**
- Consumes: aus `geom.js` `DEFAULT_SEL, de, dimGeometry, dimStyle, hasAnchors, parseDimInput, visibleDims`; aus `lib.js` `num, toast`.
- Produces: `createViewer(box, url, dims = [], hooks = {}) -> Promise<viewer>`; `hooks.onSubmit(values: [{id, value}]) -> Promise<boolean>` (true = gesendet, Viewer wird danach von außen neu gebaut). Rückgabe: `{ size, setView(v), fit(), zoom(f), setGroups(sel), setLocked(on, text), highlight(id), setEdges(on), setSection(on), snapshots(views, W, H), dispose() }`. DOM: Hauptmaß-Labels `span.dimlabel` ohne `data-dim`; Maß-Labels `span.dimlabel.edit` (editierbar) bzw. `span.dimlabel.info` (nicht editierbar) mit `data-dim="D3"`; im Bearbeiten ein `input[inputmode=decimal]` im Label. Die Methode `setDims` entfällt (Task 9 ersetzt den Schalter „Hauptmaße“).

- [ ] **Step 1: `web/static/js/viewer.js` vollständig ersetzen**

```js
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
  const state = { edges: false, section: false, locked: false, lockedText: "", sel: { ...DEFAULT_SEL }, hl: null };
  const mkLabel = (cls, text) => { const e = document.createElement("span"); e.className = cls; e.textContent = text; box.append(e); return e; };
  const mainEls = S.mainLabels.map(l => mkLabel("dimlabel", l.text));
  const itemEls = S.items.map(it => {
    const e = mkLabel(`dimlabel ${it.d.editable ? "edit" : "info"}`, num(it.d.value, 1, false));
    e.dataset.dim = it.d.id;
    e.title = `${it.d.id} · ${it.d.label || ""}`;
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
    setGroups(sel) { state.sel = { ...DEFAULT_SEL, ...sel }; applyGroups(); },
    setLocked(on, text = "") { state.locked = !!on; state.lockedText = text; },
    highlight,
    setEdges(on) { state.edges = on; S.edges.visible = on; req(); },
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
      S.items.forEach(it => { it.mat.dispose(); it.grp.children.forEach(ln => ln.geometry.dispose()); });
      renderer.domElement.remove(); mainEls.forEach(e => e.remove()); itemEls.forEach(e => e.remove());
    },
  };
}
```

- [ ] **Step 2: `web/static/css/app.css`** – nach der Zeile `.dimlabel{…}` (Z. 262) einfügen:

```css
.dimlabel.edit,.dimlabel.info{pointer-events:auto;cursor:pointer}
.dimlabel.info{cursor:help}
.dimlabel.hl{z-index:2;font-size:14px;box-shadow:0 0 0 3px rgba(31,111,178,.25)}
.dimlabel input{width:7ch;border:0;padding:0;margin:0;background:transparent;font:inherit;color:inherit;text-align:center;outline:none}
.dimbar{display:flex;flex-wrap:wrap;align-items:center;gap:2px 14px}
.dimin{width:9ch;min-height:32px;padding:4px 8px;text-align:right}
```

- [ ] **Step 3: Prüfen**

Run: `node --check web/static/js/viewer.js && node --test tests/js/*.test.mjs && python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: keine Fehler. (Der Schalter „Hauptmaße“ in `cad.js` ruft bis Task 9 noch `setDims`; Task 9 ersetzt ihn im selben Wellenabschnitt.)

- [ ] **Step 4: Commit**

```bash
git add web/static/js/viewer.js web/static/css/app.css
git commit -m "Viewer: Bemassungslinien je Mass mit Farben, Gruppen, Eingabe im Label und Hervorheben"
```

### Task 9: Auftragsseite: Gruppen-Schalter, Maßtabelle mit Eingabe, Banner, „Schlüsse ziehen“ (`cad.js`)

**Files:**
- Modify: `web/static/js/cad.js` (Importe Z. 2–4; Konstanten nach `CHIPS` Z. 13–14; `job()`: Z. 211, 215–216, `draw` Z. 244–248, `drawResult` Z. 297–376, `draw3d` Z. 378–406 vollständig, `iterateBox` Z. 479–515)

**Interfaces:**
- Consumes: `createViewer(box, url, dims, { onSubmit })` mit `setGroups`, `setLocked`, `highlight` (Task 8); aus `geom.js` `DEFAULT_SEL, conclusionText, de, dimSel, dimState, hasAnchors, paramBanner, paramIds, parseDimInput` (Task 7); `POST /api/jobs/{jid}/param` (`{"values", "base"}` → `{"version"}` bzw. `{"version", "learned": false}`), `J.pending_param`, `POST /api/jobs/{jid}/iterate` (Task 5).
- Produces: Auftragsseite mit Kontrollkästchen `Außenmaße`, `Bohrungen`, `Tiefen`, `Fasen`, `Platten`, `Sonstige`, `Annahmen`, `Nur Annahmen` (Auswahl in `localStorage` `dims.groups`), Knopf „Schlüsse ziehen“, Banner `.note.info`, Status-Badge „Neuaufbau mit D3 = 45 mm …“, Tabelle „Maße im Modell“ mit Spalten ID, Merkmal, Gruppe, Wert, Zustand und Knopf „Werte übernehmen“.

- [ ] **Step 1: Importe und Konstanten**

Nach `import { VIEW_LABEL } from "./photos.js";` einfügen:

```js
import { DEFAULT_SEL, conclusionText, de, dimSel, dimState, hasAnchors, paramBanner, paramIds, parseDimInput } from "./geom.js";
```

Nach der `CHIPS`-Konstante einfügen:

```js
// Gruppen der Bemaßung: Schlüssel, Schalter über dem Viewer, Spalte „Gruppe“ der Tabelle (Spec Stufe B §3)
const DIM_GROUPS = [["aussen", "Außenmaße", "außen"], ["bohrung", "Bohrungen", "Bohrung"], ["tiefe", "Tiefen", "Tiefe"],
  ["fase", "Fasen", "Fase"], ["platte", "Platten", "Platte"], ["sonst", "Sonstige", "sonstige"]];
const GROUP_SHORT = Object.fromEntries(DIM_GROUPS.map(([k, , s]) => [k, s]));
```

- [ ] **Step 2: Zustand, Signatur und `draw` in `job()`**

Zeile
```js
  let ver = null, tab = "3d", viewer = null, timer = null, inflight = false, gone = false, fails = 0, jv = 0, liveCode = false, lastSig = "";
```
ersetzen durch
```js
  let ver = null, tab = "3d", viewer = null, timer = null, inflight = false, gone = false, fails = 0, jv = 0, liveCode = false, lastSig = "",
    followLatest = false;   // nach einem Neuaufbau: am Ende die neue aktuelle Version zeigen
```

Zeilen
```js
  const running = () => J.status === "queued" || J.status === "running";
  const sig = () => `${J.status}|${(J.log || []).length}|${J.versions.length}`;
```
ersetzen durch
```js
  const running = () => J.status === "queued" || J.status === "running";
  // Neuaufbau ohne KI (Spec Stufe B §2): die Ergebnisansicht bleibt stehen, Felder gesperrt; Signatur ohne Protokollzeilen
  const paramRunning = () => running() && J.versions[J.versions.length - 1]?.trigger === "param";
  const sig = () => (paramRunning() ? `p|${J.versions.length}` : `${J.status}|${(J.log || []).length}|${J.versions.length}`);
  const canEdit = V => !!V && V.status === "ok" && V.version === J.current_version && !running();
  const lockText = () => (running() ? "Der Auftrag läuft – bitte warten." : "Werte sind nur in der aktuellen Version änderbar.");
```

`draw` vollständig ersetzen:
```js
  function draw() {
    lastSig = sig();
    viewer?.dispose(); viewer = null;
    if (running() && !paramRunning()) drawRun(); else drawResult();
    if (running()) startPoll();
  }
```

- [ ] **Step 3: `drawResult` anpassen** (vier Stellen)

(a) Die ersten zwei Zeilen von `drawResult`
```js
  function drawResult() {
    const vers = J.versions;
```
ersetzen durch
```js
  function drawResult() {
    const vers = J.versions;
    if (followLatest && !running()) { ver = null; followLatest = false; }
```

(b) In der Optionsbeschriftung von `verSel` den Ausdruck
```js
${v.status === "ok" ? "geprüft" : v.status === "cancelled" ? "abgebrochen" : v.error ? "Sandbox-Fehler" : "fehlgeschlagen"}
```
ersetzen durch
```js
${v.status === "ok" ? "geprüft" : v.status === "running" ? "läuft" : v.status === "cancelled" ? "abgebrochen" : v.error ? "Sandbox-Fehler" : "fehlgeschlagen"}
```

(c) In `head` die Zeile
```js
      h("div", { class: "chips" }, vers.length ? h("label", { class: "chips small" }, "Version", verSel) : null, summary, jobBadge(J.status),
```
ersetzen durch
```js
      h("div", { class: "chips" }, vers.length ? h("label", { class: "chips small" }, "Version", verSel) : null, summary, jobBadge(J.status),
        paramRunning() ? h("span", { class: "badge info", role: "status" }, h("span", { class: "spin", style: { width: "12px", height: "12px" } }),
          `Neuaufbau mit ${vers[vers.length - 1].request_text} …`) : null,
```

(d) Den Block
```js
    if (meta.dimensions?.length) {
      right.append(h("section", { class: "card", style: { gap: "10px" } }, h("h2", {}, "Maße im Modell"),
        h("table", { class: "t" }, h("thead", {}, h("tr", {}, h("th", {}, "ID"), h("th", {}, "Merkmal"), h("th", { style: { textAlign: "right" } }, "gemessen"), h("th", { style: { textAlign: "right" } }, "Nennmaß"))),
          h("tbody", {}, meta.dimensions.map(d => h("tr", { title: d.note || "" }, h("td", { class: "mono" }, d.id || ""), h("td", {}, d.label || "", d.note ? h("div", { class: "xs muted" }, d.note) : null),
            h("td", { class: "num" }, typeof d.measured === "number" ? num(d.measured, 2) : String(d.measured ?? "–")), h("td", { class: "num", style: { fontWeight: 600 } }, typeof d.nominal === "number" ? num(d.nominal, 2) : String(d.nominal ?? "–"))))))));
    }
```
ersetzen durch
```js
    if (meta.dimensions?.length) right.append(dimTable(V, meta.dimensions));
```

- [ ] **Step 4: Neue Funktionen in `job()` vor `function draw3d`**

```js
  // ---------------------------------------------------------------- Bemaßung am Modell (Spec Stufe B §2, §3, §5)
  async function sendParam(values) {
    if (values.length > 20) { toast("Höchstens 20 Werte auf einmal.", "err"); return false; }
    try {
      const r = await api(`/api/jobs/${id}/param`, { method: "POST", body: { values, base: J.current_version } });
      if (r.learned === false) toast("Ohne Projekt – der Wert wird nicht gemerkt.");
      const j = await api(`/api/jobs/${id}`);
      if (gone) return true;
      J = j; jv++; ver = null; followLatest = true; draw();
      return true;
    } catch (e) { fail(e); return false; }
  }
  async function conclude() {
    const text = conclusionText(J.pending_param || []);
    if (!text || running()) return;
    try { J = await api(`/api/jobs/${id}/iterate`, { method: "POST", body: { text } }); refreshMe().catch(() => {}); if (gone) return; jv++; ver = null; draw(); }
    catch (e) { fail(e); }
  }
  function dimTable(V, list) {
    const edit = canEdit(V), inputs = [];
    const btn = h("button", { class: "btn sm", onclick: () => send(null) }, "Werte übernehmen");
    async function send(only) {   // only = ein Feld (Enter), sonst alle geänderten Felder
      const vals = [];
      for (const [d, inp] of inputs) {
        if (only && inp !== only) continue;
        if (!only && inp.value.trim() === de(d.value)) continue;
        const r = parseDimInput(inp.value);
        if (r.error) { toast(`${d.id}: ${r.error}`, "err"); inp.focus(); return; }
        if (Math.abs(r.value - d.value) >= 0.0005) vals.push({ id: d.id, value: r.value });
      }
      if (!vals.length) { toast("Keine geänderten Werte."); return; }
      const lock = on => { btn.disabled = on; inputs.forEach(([, inp]) => { inp.disabled = on; }); };
      lock(true);
      if (!await sendParam(vals)) lock(false);
    }
    const rows = list.map(d => {
      const old = !/^D\d+$/.test(d.id || "");          // Version vor Stufe B: measured/nominal, nicht editierbar
      const val = typeof d.value === "number" ? d.value : typeof d.nominal === "number" ? d.nominal : null;
      let cell = h("td", { class: "num", style: { fontWeight: 600 } }, val === null ? "–" : num(val, 2));
      if (edit && d.editable && typeof d.value === "number") {
        const inp = h("input", { class: "input mono dimin", inputmode: "decimal", value: de(d.value), "aria-label": `${d.id} ${d.label || ""}`,
          onclick: e => e.stopPropagation(), onkeydown: e => { if (e.key === "Enter") { e.preventDefault(); send(inp); } } });
        inputs.push([d, inp]);
        cell = h("td", { class: "num" }, inp);
      }
      const zustand = old ? (typeof d.measured === "number" ? `gemessen ${num(d.measured, 2)}` : "") : dimState(d);
      return h("tr", { title: d.note || "", style: hasAnchors(d) ? { cursor: "pointer" } : {}, onclick: () => viewer?.highlight(d.id) },
        h("td", { class: "mono" }, d.id || ""), h("td", {}, d.label || "", d.note ? h("div", { class: "xs muted" }, d.note) : null),
        h("td", { class: "small" }, GROUP_SHORT[d.group] || "–"), cell, h("td", { class: "small" }, zustand));
    });
    return h("section", { class: "card", style: { gap: "10px" } }, h("h2", {}, "Maße im Modell"),
      h("table", { class: "t" }, h("thead", {}, h("tr", {}, h("th", {}, "ID"), h("th", {}, "Merkmal"), h("th", {}, "Gruppe"),
        h("th", { style: { textAlign: "right" } }, "Wert"), h("th", {}, "Zustand"))), h("tbody", {}, rows)),
      inputs.length ? h("div", { class: "chips" }, btn, h("span", { class: "xs muted" }, "Enter im Feld übernimmt nur diesen Wert · höchstens 20 auf einmal"))
        : V.version !== J.current_version && list.some(d => d.editable) ? h("span", { class: "xs muted" }, "Werte sind nur in der aktuellen Version änderbar.") : null);
  }
```

- [ ] **Step 5: `draw3d` vollständig ersetzen**

```js
  function draw3d(panel, V) {
    const box = h("div", { class: "viewer" });
    const viewBtns = {};
    const vb = (k, t) => (viewBtns[k] = h("button", { "aria-pressed": String(k === "iso"), onclick: () => { viewer?.setView(k); Object.entries(viewBtns).forEach(([q, b]) => b.setAttribute("aria-pressed", String(q === k))); } }, t));
    const views3 = h("div", { class: "views3" });
    const dims = Array.isArray(V.meta?.dimensions) ? V.meta.dimensions : [];
    let sel = { ...DEFAULT_SEL };
    try { sel = dimSel(localStorage.getItem("dims.groups")); } catch { /* Speicher gesperrt: Standard */ }
    const setSel = (k, on) => {
      sel = { ...sel, [k]: on };
      try { localStorage.setItem("dims.groups", JSON.stringify(sel)); } catch { /* */ }
      viewer?.setGroups(sel);
    };
    const cb = (k, t) => h("label", { class: "check small" }, h("input", { type: "checkbox", checked: sel[k], onchange: e => setSel(k, e.target.checked) }), t);
    const pending = J.pending_param || [];
    const conclBtn = () => h("button", { class: "btn claude sm", disabled: !pending.length || running(),
      title: pending.length ? "Die KI leitet abhängige Maße aus den nachgemessenen Werten ab" : "Erst einen Wert am Modell eintragen", onclick: conclude },
    icon("sparkle", 14), "Schlüsse ziehen");
    const bar = h("div", { class: "dimbar", role: "group", "aria-label": "Maße anzeigen" },
      DIM_GROUPS.map(([k, t]) => cb(k, t)), cb("annahmen", "Annahmen"), cb("nur_annahmen", "Nur Annahmen"), h("span", { style: { flex: "1" } }), conclBtn());
    const ids = V.trigger === "param" ? paramIds(V.request_text) : [];
    const btext = V.version === J.current_version ? paramBanner(pending.filter(p => ids.includes(p.id))) : "";
    const banner = btext ? h("div", { class: "note info", role: "status" }, icon("info"), h("span", { style: { flex: "1" } }, btext), conclBtn()) : null;
    const noProject = !J.project_id && dims.some(d => d.editable) ? h("span", { class: "xs muted" }, "Ohne Projekt – der Wert wird nicht gemerkt.") : null;
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
      if (!box.isConnected) { v.dispose(); return; }
      viewer = v;
      v.setGroups(sel);
      v.setLocked(!canEdit(V), lockText());
      const snaps = v.snapshots(["top", "front", "side"]);
      clear(views3, [["top", "Oben"], ["front", "Vorn"], ["side", "Seite"]].map(([k, t]) => h("figure", { onclick: () => viewBtns[k].click() },
        h("img", { src: snaps[k], alt: `${t}-Ansicht` }), h("figcaption", {}, t))));
    }).catch(e => { clear(loading, icon("warn"), `3D-Ansicht nicht verfügbar: ${e.message}`); });
  }
```

- [ ] **Step 6: `iterateBox`** (zwei Stellen)

(a) `const btn = h("button", { class: "btn primary", onclick: async () => {` ersetzen durch `const btn = h("button", { class: "btn primary", disabled: running(), onclick: async () => {`.

(b) Im Verlauf den Ausdruck
```js
v.trigger === "create" ? "Erster Entwurf" : v.trigger === "autofix" ? "Automatische Korrektur" : `Änderung: ${(v.request_text || "").slice(0, 80)}`
```
ersetzen durch
```js
v.trigger === "create" ? "Erster Entwurf" : v.trigger === "autofix" ? "Automatische Korrektur"
              : v.trigger === "param" ? `Neuaufbau: ${v.request_text || ""}` : `Änderung: ${(v.request_text || "").slice(0, 80)}`
```

- [ ] **Step 7: Prüfen**

Run: `node --check web/static/js/cad.js && node --test tests/js/*.test.mjs && python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: keine Fehler.

Browser-Probe (Scratchpad): lokalen Server starten (`cd /root/Snap2CAD/web && DATA_DIR=$SP/stufe_b/data RUNS_DIR=$SP/stufe_b/runs SANDBOX_MODE=local AI_FAKE=1 uvicorn app.main:app --port 8765` im Hintergrund, `SP=/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad`), im Browser einrichten, ein Projekt mit einer Messung „Länge 80“ anlegen, einen Auftrag erzeugen (Testmodus), `/cad/<id>` öffnen → Linien D1, D2, D3, D6 sichtbar, „Bohrungen“ an → D4 dazu; Klick auf das rote Label „6,0“ → Feld, `8` + Enter → Badge „Neuaufbau mit D3 = 8 mm …“, danach v3 aktuell, Banner „8 mm ersetzt eine Annahme (6 mm) – …“; Tabelle: Feld D1 auf `81` und „Werte übernehmen“ → v4; ältere Version wählen → Felder weg, Hinweis „Werte sind nur in der aktuellen Version änderbar.“; Konsole ohne Fehler.

- [ ] **Step 8: Commit**

```bash
git add web/static/js/cad.js
git commit -m "Auftragsseite: Gruppen-Schalter, Masstabelle mit Eingabe, Neuaufbau-Status, Banner und Schluesse ziehen"
```

### Task 10: Liste „Messschieber am Modell“ auf der Messseite (`measure.js`, `app.css`)

**Files:**
- Modify: `web/static/js/measure.js` (DOM nach `suggBox` Z. 72; Seitenleiste Z. 101; `renderList` Z. 544–591; neue Funktionen nach `renderList`)
- Modify: `web/static/css/app.css` (nach `.mlist`/`.mitem` Z. 198–205)

**Interfaces:**
- Consumes: `S.project.model_dims` (`{id, label, grp, value, job_id, dim_id, created_at}`), `DELETE /api/projects/{pid}/model-dims/{mid}` (Task 6), `reloadProject()`, `confirmDlg(title, text, label, danger)`.
- Produces: Abschnitt `section.mdims` mit Zeilen `li.mdrow` unter der Maßtabelle; Löschen je Zeile mit Rückfrage.

- [ ] **Step 1: measure.js**

Auf Modulebene nach den Importen (vor `export function circle3`) einfügen – Modulebene, damit `renderList` die Konstante bei jedem Aufruf schon kennt:

```js
const MD_GROUP = { aussen: "außen", bohrung: "Bohrung", tiefe: "Tiefe", fase: "Fase", platte: "Platte", sonst: "sonstige" };
```

Nach `const suggBox = h("section", { class: "sugg", "aria-labelledby": "ki-h", hidden: true });` einfügen:

```js
  const mdBox = h("section", { class: "mdims", "aria-labelledby": "md-h", hidden: true });
```

In `clear(main, …)` die Zeile `        listBox, suggBox,` ersetzen durch `        listBox, mdBox, suggBox,`.

Am Ende von `renderList` (nach dem `if (sugg.length) { … }`-Block, vor der schließenden Klammer von `renderList`) einfügen:

```js
    renderModelDims();
```

Nach `renderList` einfügen:

```js
  // Spec Stufe B §4: am 3D-Modell eingetragene Messschieberwerte, gelten für alle Aufträge des Projekts
  function renderModelDims() {
    const md = S.project.model_dims || [];
    mdBox.hidden = !md.length;
    if (!md.length) { mdBox.replaceChildren(); return; }
    clear(mdBox,
      h("div", { class: "card-head" }, h("h3", { id: "md-h" }, "Messschieber am Modell ", h("span", { style: { fontWeight: 400 } }, `(${md.length})`)),
        h("span", { class: "xs muted" }, "am 3D-Modell eingetragen · gilt für alle Aufträge")),
      h("ul", { class: "mlist" }, md.map(r => h("li", { class: "mdrow" },
        h("span", { class: "mid" }, r.dim_id || "–"),
        h("span", { class: "mdl" }, r.label, h("span", { class: "xs muted" }, ` · ${MD_GROUP[r.grp] || r.grp}${r.job_id ? ` · Auftrag ${r.job_id}` : ""}`)),
        h("span", { class: "mval" }, `${num(r.value, 2)} mm`),
        h("button", { class: "iconbtn", style: { width: "34px", height: "34px" }, "aria-label": `${r.label} löschen`, onclick: () => delModelDim(r) }, icon("x", 16))))),
      h("span", { class: "xs muted" }, "Diese Werte gehen bei jedem Auftrag und jeder Änderung als verbindlich an die KI."));
  }
  async function delModelDim(r) {
    if (!await confirmDlg("Messschieberwert löschen?", `${r.label}: ${num(r.value, 2)} mm geht danach nicht mehr an die KI.`, "Löschen", true)) return;
    try { await api(`/api/projects/${S.project.id}/model-dims/${r.id}`, { method: "DELETE" }); await reloadProject(); renderList(); }
    catch (e) { fail(e); }
  }
```

- [ ] **Step 2: app.css** – nach `.msub{…}` einfügen:

```css
.mdims{display:flex;flex-direction:column;gap:8px}
.mdrow{display:grid;grid-template-columns:40px minmax(0,1fr) auto auto;gap:10px;align-items:center;padding:6px 8px 6px 12px;border:1px solid var(--line);border-radius:var(--r2)}
.mdl{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
```

- [ ] **Step 3: Prüfen**

Run: `node --check web/static/js/measure.js && node --test tests/js/*.test.mjs && python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: keine Fehler. Browser-Probe: nach einem Param-Lauf aus Task 9 `/messen` öffnen → Liste mit „Dicke · Platte · Auftrag n · 8 mm“; Löschen → Rückfrage → Liste weg; CSV-Export ohne die Zeile.

- [ ] **Step 4: Commit und Wellenabschluss** (lokale Suite und CI, siehe Global Constraints)

```bash
git add web/static/js/measure.js web/static/css/app.css
git commit -m "Messseite: Liste Messschieber am Modell mit Loeschen"
```

---

## Welle 3 – Browser-Durchlauf, Review, Auslieferung

### Task 11: Browser-Durchlauf (B6, B7), README, Gesamtreview, Auslieferung und B8

**Files:**
- Scratchpad: `pw/stufe_b.mjs` (Playwright, nicht im Repo), `stufe_b/b8_check.py`, `stufe-b-protokoll.md`
- Modify: `README.md:34` (ein Absatz nach den Ergänzungen der Stufe A)

**Interfaces:**
- Consumes: alles aus W1/W2; lokaler Server mit `AI_FAKE=1 SANDBOX_MODE=local` auf Port 8765.
- Produces: Prüfpunkte B6/B7 als `ergebnis.json` und Bildschirmfotos im Scratchpad, README-Absatz, gemergter PR, NAS auf neuer Revision, Handlungsauftrag B8.

- [ ] **Step 1: Lokalen Server starten** (im Hintergrund, `run_in_background`)

```bash
SP=/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad
rm -rf $SP/stufe_b/data $SP/stufe_b/runs $SP/stufe_b/shots && mkdir -p $SP/stufe_b
cd /root/Snap2CAD/web && source /root/Snap2CAD-venv/bin/activate && \
  DATA_DIR=$SP/stufe_b/data RUNS_DIR=$SP/stufe_b/runs SANDBOX_MODE=local AI_FAKE=1 \
  uvicorn app.main:app --port 8765 > $SP/stufe_b/server.log 2>&1
```

- [ ] **Step 2: Playwright-Skript** `$SP/pw/stufe_b.mjs` (nutzt `playwright-core` aus `$SP/pw/node_modules` wie `stufe_a.mjs`):

```js
// Stufe B – Browser-Durchlauf B6/B7 und Messseite gegen lokalen Server (AI_FAKE=1, SANDBOX_MODE=local)
import { chromium } from "playwright-core";
import fs from "fs";
import { execFileSync } from "child_process";
const [B, OUT, DB] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const H = { "X-Requested-With": "fetch" };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
const page = await ctx.newPage();
const errs = [], failed = [], iterBodies = [];
page.on("console", m => { if (m.type() === "error") errs.push(`[${new URL(page.url()).pathname}] ${m.text()}`); });
page.on("pageerror", e => errs.push(`pageerror: ${e.message}`));
page.on("response", r => { if (r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });
page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/iterate")) iterBodies.push(r.postDataJSON()); });
const C = {}, N = {};
const api = async (method, path, data) => {
  const r = await ctx.request.fetch(B + path, { method, headers: H, data });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; }
  if (!r.ok()) throw new Error(`${method} ${path} ${r.status()} ${t.slice(0, 200)}`);
  return j;
};
const step = async (name, fn) => { try { await fn(); } catch (e) { N[`${name}_FEHLER`] = String(e.stack || e).slice(0, 600); } };
const waitJob = async jid => { let J; for (let i = 0; i < 120; i++) { J = await api("GET", `/api/jobs/${jid}`); if (!["queued", "running"].includes(J.status)) return J; await sleep(1000); } return J; };
const shownIds = () => page.locator(".viewer .dimlabel[data-dim]:not([hidden])").evaluateAll(es => es.map(e => e.dataset.dim));
const label = id => page.locator(`.viewer .dimlabel[data-dim="${id}"]`);
const byId = v => Object.fromEntries(v.meta.dimensions.map(x => [x.id, x]));

await api("POST", "/api/setup", { username: "admin", display_name: "Admin", password: "Messschieber-Lang-12345", api_key: "" });
const uid = (await api("GET", "/api/me")).user.id;
const proj = await api("POST", "/api/projects", { name: "Stufe B" });
await api("POST", `/api/projects/${proj.id}/measurements`, { kind: "length", value: 80, label: "Länge" });
const job = await api("POST", "/api/jobs", { project_id: proj.id, name: "Platte", request: "Montageplatte" });
let J = await waitJob(job.id);
C.ki_lauf_fertig = J.status === "done";
await page.goto(B + "/"); await sleep(1500);
await page.evaluate(([u, p]) => { localStorage.setItem(`mu.project.${u}`, p); localStorage.removeItem("dims.groups"); }, [uid, proj.id]);

await step("linien", async () => {
  await page.goto(`${B}/cad/${job.id}`); await page.waitForSelector(".viewer canvas", { timeout: 20000 }); await sleep(2500);
  N.sichtbar_standard = await shownIds();
  C.standard_aussen_und_annahmen = ["D1", "D2", "D3", "D6"].every(i => N.sichtbar_standard.includes(i)) && !N.sichtbar_standard.includes("D4");
  C.edit_klasse = (await page.locator(".viewer .dimlabel.edit").count()) === 7;
  C.keine_hauptmasse_bei_ankern = (await page.locator(".viewer .dimlabel:not([data-dim]):not([hidden])").count()) === 0;
  await page.getByLabel("Bohrungen").check(); await sleep(500);
  C.gruppe_bohrungen_an = (await shownIds()).includes("D4");
  await page.getByLabel("Nur Annahmen").check(); await sleep(500);
  N.nur_annahmen = await shownIds();
  C.nur_annahmen = N.nur_annahmen.length > 0 && N.nur_annahmen.every(i => ["D3", "D6"].includes(i));
  await page.getByLabel("Nur Annahmen").uncheck(); await sleep(300);
  await page.reload(); await page.waitForSelector(".viewer canvas"); await sleep(2500);
  C.wahl_bleibt_nach_neuladen = await page.getByLabel("Bohrungen").isChecked();
  await page.screenshot({ path: `${OUT}/linien.png` });
});

await step("eingabe", async () => {
  await label("D3").click(); await sleep(300);
  const inp = page.locator('.viewer .dimlabel[data-dim="D3"] input');
  C.label_wird_eingabe = (await inp.count()) === 1 && (await inp.inputValue()) === "6";
  await inp.press("Escape"); await sleep(200);
  C.esc_bricht_ab = (await page.locator('.viewer .dimlabel[data-dim="D3"] input').count()) === 0;
  await label("D3").click(); await sleep(200);
  await inp.fill("8"); await inp.press("Enter");
  C.status_neuaufbau = await page.locator(".badge.info", { hasText: "Neuaufbau mit D3 = 8 mm" }).waitFor({ timeout: 5000 }).then(() => true, () => false);
  J = await waitJob(job.id);
  const v = J.versions[J.versions.length - 1], d = byId(v);
  N.param = { trigger: v.trigger, status: v.status, seconds: v.seconds, request: v.request_text, anchors: v.result?.dim_anchors };
  C.param_version_ok = v.trigger === "param" && v.status === "ok" && J.current_version === v.version;
  C.geaenderte_linie_am_wert = Math.abs(v.result.dim_anchors.D3[1][2] - 8) < 0.1 && d.D3.user_set === true;
  C.abhaengige_linie_am_wert = Math.abs(d.D4.a[2] - 8) < 0.1;
  C.rueckfall_grau = d.D7.anchors_stale === true;
  await sleep(2500);
  N.banner = await page.locator(".note.info").first().textContent().catch(() => "");
  C.banner = /8 mm ersetzt eine Annahme \(6 mm\)/.test(N.banner);
  C.label_gruen = (await label("D3").evaluate(e => getComputedStyle(e).color)) === "rgb(26, 127, 55)";
  await page.screenshot({ path: `${OUT}/param.png` });
});

await step("schluesse", async () => {
  await page.getByRole("button", { name: "Schlüsse ziehen" }).first().click(); await sleep(1500);
  N.iterate_text = iterBodies[iterBodies.length - 1]?.text;
  C.text_mit_wert = /D3 Dicke = 8 mm \(vorher Annahme 6\)/.test(N.iterate_text || "");
  J = await waitJob(job.id);
  const v = J.versions[J.versions.length - 1], d = byId(v);
  C.ki_lauf_nach_schluessen = J.status === "done" && v.trigger === "iterate" && d.D3.value === 8 && d.D3.user_set === true;
  C.pending_leer = (J.pending_param || []).length === 0;
  C.pruefpunkt_model_dims_ok = v.checks.some(c => c.id === "model_dims" && c.state === "ok");
});

await step("messseite", async () => {
  await page.goto(`${B}/messen`); await sleep(2500);
  const rows = page.locator(".mdims .mdrow");
  C.liste_sichtbar = (await rows.count()) === 1 && /Dicke/.test(await rows.first().textContent());
  const csv = await (await ctx.request.get(`${B}/api/projects/${proj.id}/measurements.csv`)).text();
  C.csv_modell = /;Modell;/.test(csv);
  await rows.first().getByRole("button").click(); await sleep(300);
  await page.getByRole("button", { name: "Löschen", exact: true }).click(); await sleep(1500);
  C.loeschen = (await page.locator(".mdims .mdrow").count()) === 0 && (await api("GET", `/api/projects/${proj.id}`)).model_dims.length === 0;
});

await step("alte_version", async () => {
  const j2 = await api("POST", "/api/jobs", { project_id: proj.id, name: "Alt", request: "x" });
  const J2 = await waitJob(j2.id);
  const old = JSON.stringify({ summary: "alt", assumptions: [], check_before_manufacturing: [], bbox_expected: [80, 50, 6],
    dimensions: [{ id: "M1", label: "Länge", measured: 79.8, nominal: 80.0, note: "gerundet" }] });
  execFileSync("python3", ["-c", "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE job_versions SET meta=? WHERE job_id=? AND version=?',(sys.argv[2],int(sys.argv[3]),int(sys.argv[4])));c.commit()",
    DB, old, String(j2.id), String(J2.current_version)]);
  const e0 = errs.length;
  await page.goto(`${B}/cad/${j2.id}`); await page.waitForSelector(".viewer canvas", { timeout: 20000 }); await sleep(2500);
  C.alt_nur_hauptmasse = (await page.locator(".viewer .dimlabel:not([hidden])").count()) === 3 && (await page.locator(".viewer .dimlabel[data-dim]").count()) === 0;
  C.alt_tabelle_gemessen = /gemessen 79,8/.test(await page.locator("table.t").last().textContent());
  C.alt_ohne_konsolenfehler = errs.length === e0;
  await page.screenshot({ path: `${OUT}/alt.png` });
});

C.konsolenfehler_leer = errs.length === 0;
fs.writeFileSync(OUT + "/ergebnis.json", JSON.stringify({ C, N, errs, failed }, null, 1));
console.log(JSON.stringify({ C, N, errs, failed }, null, 1));
await browser.close();
```

Run: `cd $SP/pw && node stufe_b.mjs http://127.0.0.1:8765 $SP/stufe_b/shots $SP/stufe_b/data/snap2cad.db`
Expected: alle Werte in `C` sind `true`, `errs == []`, in `failed` nur die erwarteten 4xx-Antworten (keine). Ergebnis und Bildschirmfotos ins Protokoll `$SP/stufe-b-protokoll.md` (Abschnitt „Task 11 – Browser-Durchlauf“). Ein `false` ist ein Befund: Ursache beheben (TDD im zuständigen Task-Bereich), Suite grün, Durchlauf wiederholen.

- [ ] **Step 3: README** – nach dem Absatz „In der Web-App gibt es dazu drei Ergänzungen. …“ (Z. 34) einfügen:

```markdown
Im 3D-Viewer eines Auftrags stehen die Maße des Modells als Bemaßungslinien, gruppenweise ein- und ausschaltbar (Außenmaße, Bohrungen, Tiefen, Fasen, Platten, Sonstige, Annahmen). Ein Klick auf ein Maß nimmt einen Messschieberwert an: Das Modell wird sofort ohne KI neu gebaut, der Wert gilt als „Messschieber am Modell“ für das ganze Projekt, und „Schlüsse ziehen“ lässt die KI die abhängigen Maße daraus ableiten. Die Liste der gemerkten Werte steht auf der Messseite und lässt sich dort löschen.
```

Run: `python -m pytest -q -p no:cacheprovider tests/test_texts.py`
Expected: PASS.

```bash
git add README.md
git commit -m "README: Bemassung am Modell"
```

- [ ] **Step 4: Gesamtreview** (whole-branch wie bei PR #5/#6): ein Server-Reviewer über `git diff main...bemassung-am-modell -- web/app tests` (Schwerpunkte: Sperren in `jobs.param`/`_run_param`, Anker-Toleranzen, Prüfsumme) und die JS-Kette (`footgun:footgun` auf `web/static/js/geom.js viewer.js cad.js measure.js`). Befunde beheben, je Befund ein Commit, danach Wellenabschluss-Befehl (Suite + CI) grün.

- [ ] **Step 5: Auslieferung** (Spec „Auslieferung“)

```bash
cd /root/Snap2CAD && gh pr ready && gh pr checks --watch
gh pr merge --merge
git checkout main && git pull --ff-only origin main
H=$(git rev-parse HEAD)
until gh run list -b main -L5 --json databaseId,headSha -q ".[] | select(.headSha==\"$H\") | .databaseId" | grep -q .; do sleep 5; done
gh run watch --exit-status $(gh run list -b main -L5 --json databaseId,headSha -q ".[] | select(.headSha==\"$H\") | .databaseId" | head -1)
SP=/tmp/claude-0/-root/13c1f9d5-7997-460c-8690-80c2d3b5962a/scratchpad
sed 's/-c\.tgz/-stufe-b.tgz/' $SP/nas_update.sh > $SP/stufe_b/nas_update.sh
ssh -i ~/.ssh/id_ed25519_nas ma.backes@192.168.2.151 'sh -s' < $SP/stufe_b/nas_update.sh
```

Expected: Sicherung `backup-data-<datum>-stufe-b.tgz` mit Größe > 0 gelistet, `app-1` und `sandbox-1` `Up (healthy)`, Revision = Merge-Commit auf `main`, `health=200` oder `root=200`. Werte ins Protokoll. Schlägt ein Schritt fehl: nicht weiter, Befund ins Protokoll und dem Nutzer melden.

- [ ] **Step 6: Prüfskript für B8** `$SP/stufe_b/b8_check.py` anlegen (liest nur, Aufruf nach Marcs Rückmeldung):

```python
"""B8: Versionen eines Auftrags mit Massen, Ankern und Laufzeit (nur lesend)."""
import json
import sqlite3
import sys

jid = int(sys.argv[1])
c = sqlite3.connect("file:/data/snap2cad.db?mode=ro", uri=True)
for v, trig, st, req, sec, meta, res in c.execute("SELECT version, trigger, status, request_text, seconds, meta, result "
                                                  "FROM job_versions WHERE job_id=? ORDER BY version", (jid,)):
    m, r = json.loads(meta or "{}"), json.loads(res or "{}")
    print(f"v{v} {trig} {st} {sec} s · {req or ''}")
    for d in m.get("dimensions", []):
        print("   ", d.get("id"), d.get("label"), d.get("value"), d.get("group"), "Annahme" if d.get("assumed") else "",
              "nachgemessen" if d.get("user_set") else "", f"von {d['derived_from']}" if d.get("derived_from") else "",
              (r.get("dim_anchors") or {}).get(d.get("id")), d.get("note") or "")
```

Aufruf: `ssh -i ~/.ssh/id_ed25519_nas ma.backes@192.168.2.151 "sudo -n /usr/local/bin/docker exec -i snap2cad-app-1 python - <AUFTRAG>" < $SP/stufe_b/b8_check.py`

- [ ] **Step 7: Handlungsauftrag B8 an Marc** (gebündelt, als eine Nachricht; danach auf die Rückmeldung warten)

> **B8 – Bemaßung am Modell mit dem Kühlkörperblock** (Stand: Snap2CAD auf der DS918+ mit dem Merge dieser Stufe, https://snap2cad.collabtive.cloud)
>
> **Ziel:** Höhe und Bohrungs-Ø am Modell eintragen, das Modell folgt in unter 30 s; „Schlüsse ziehen“ passt Bohrtiefe und Plattendicke mit Begründung an.
>
> **Voraussetzungen:** Kühlkörperblock, Messschieber, dein Konto in Snap2CAD, das Projekt mit den Fotos des Blocks (das aus A8), ein freier CAD-Lauf im Monatskontingent (zwei Läufe werden gebraucht: Schritt 2 und Schritt 7).
>
> 1. https://snap2cad.collabtive.cloud öffnen und anmelden. Oben „Meine Aufträge“ → den Auftrag des Kühlkörperblocks aus der A8-Wiederholung öffnen (Auftrag 7).
> 2. Unten im Feld „Änderung anfordern“ genau diesen Text eintragen: `Modell unverändert neu ausgeben, im aktuellen Antwortformat mit D-Nummern und DIM_ANCHORS.` → Knopf „v… erzeugen“. Warten, bis „Alle Prüfungen bestanden“ oder „… Hinweise“ erscheint (2–4 Minuten). Grund: ältere Versionen haben noch keine Bemaßungslinien.
> 3. Im Tab „3D-Ansicht“ über dem Modell die Kontrollkästchen setzen: „Außenmaße“ an, „Annahmen“ an, zusätzlich „Bohrungen“, „Tiefen“ und „Platten“ an; „Nur Annahmen“ aus.
> 4. Die Gesamthöhe des Blocks mit dem Messschieber messen (auf 0,1 mm). Im Viewer auf das Label der Höhenlinie klicken (Tabelle „Maße im Modell“ rechts: Merkmal mit „Höhe“, Gruppe „außen“, Zustand „Annahme“ – Label rot). Den Messwert mit Komma eintragen, z. B. `52,4`, dann Enter. Oben erscheint „Neuaufbau mit D… = … mm …“; warten, bis es verschwindet. Die Linie wird grün.
> 5. Ein Bildschirmfoto der 3D-Ansicht machen, auf dem Höhen- und Bohrtiefenlinie zu sehen sind (bei Bedarf „Vorn“ wählen).
> 6. Den Durchmesser der großen Bohrung messen, das Label der Bohrungslinie anklicken (Gruppe „Bohrung“), Wert eintragen, Enter, warten wie in Schritt 4.
> 7. Im blauen Hinweis „… ersetzt eine Annahme … – Schlüsse auf abhängige Maße ziehen?“ (oder über dem Viewer) auf „Schlüsse ziehen“ klicken. Warten, bis die neue Version fertig ist (2–4 Minuten).
> 8. In der Tabelle „Maße im Modell“ prüfen: Bohrtiefe und Plattendicke stehen mit Zustand „abgeleitet von D…“ und einer kurzen Begründung darunter.
>
> **Nicht tun:** während „Neuaufbau mit …“ nicht „Abbrechen“ klicken; keine Werte eintragen, solange oben eine ältere Version gewählt ist (Versionswahl auf „aktuell“ lassen); keinen neuen Auftrag anlegen; die Liste „Messschieber am Modell“ auf der Messseite nicht löschen, bevor ich das Protokoll gezogen habe; keine Werte in Zoll oder mit Einheit („52,4 mm“) eintragen – nur die Zahl.
>
> **Zurück an mich (hier im Chat):** (1) die Nummer des Auftrags (Zahl in der Adresszeile nach `/cad/`), (2) die zwei gemessenen Werte in mm mit einer Nachkommastelle, (3) das Bildschirmfoto aus Schritt 5 als PNG, (4) ob in Schritt 8 Bohrtiefe und Plattendicke angepasst wurden (ja/nein).
>
> **Erfolgskontrolle:** Nach Schritt 4 und 6 ist die Linie grün und das Label zeigt deinen Wert; nach Schritt 7 ist „Schlüsse ziehen“ ausgegraut und die Prüfung zeigt „Messschieber am Modell übernommen“.

- [ ] **Step 8: B8-Protokoll** nach Marcs Rückmeldung: `b8_check.py` mit der Auftragsnummer ausführen und ins Protokoll übernehmen: `seconds` beider Param-Versionen (< 30 s), Endpunkt der Höhenlinie in `dim_anchors` (z = Messwert ± 0,1 mm), `derived_from` und `note` von Bohrtiefe und Plattendicke in der Version nach „Schlüsse ziehen“, Bildschirmfoto im Scratchpad ablegen (`$SP/stufe_b/b8.png`). Abweichungen sind Befunde (Protokoll, an den Nutzer melden), keine stillen Nachbesserungen.
