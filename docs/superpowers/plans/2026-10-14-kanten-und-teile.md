# Kanten, Teile und mitdenkende Bemaßung – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Snap2CAD erkennt Kanten und Teile auf der entzerrten Draufsicht, lässt sie bearbeiten, leitet aus Messschieber-Werten einen Maßstab je Teil ab, übergibt wahlweise ein einzelnes Teil an die CAD-Erzeugung und nennt Claude in der Oberfläche nicht mehr.

**Architecture:** `core/edges.py` (OpenCV, ohne KI) liefert Umriss, Bohrungen und Kanten-Kandidaten in mm. `web/app/parts.py` hält Teile, Kanten-Kennungen, Auto-Maße, Zuordnung und Maßstab; eine zentrale Funktion `refresh(project, fx, fy)` ersetzt `_recompute`. `ai.py` bekommt einen Prompt für die Teile-Zuordnung; `main.py` neue Endpunkte. Im Browser zeichnet und bearbeitet `edges.js` die Teile, `measure.js` bindet es ein.

**Tech Stack:** Python 3.13, FastAPI, SQLite, OpenCV 5.0 (`opencv-python-headless==5.0.0.93`), shapely 2.2, numpy; Vanilla-JS-Module ohne Build.

**Spec:** `docs/superpowers/specs/2026-10-14-kanten-und-teile-design.md`

## Global Constraints

- Keine neuen Python- oder JS-Abhängigkeiten. shapely, numpy und OpenCV sind schon in `web/requirements.txt`.
- OpenCV 5: `cv2.createLineSegmentDetector().detect(gray)[0]` hat die Form `(N, 4)` oder ist `None`, nicht `(N, 1, 4)`.
- Koordinaten aller Teile und Messungen: mm der Rasterfläche, Ursprung unten links, x nach rechts, y nach oben. Bildpixel → mm: `x_mm = (px + 0.5) / 10`, `y_mm = h_mm − (py + 0.5) / 10`.
- Oberflächentexte Deutsch und neutral („KI“); „Claude“ steht nirgends in `web/static`, außer in `//`-Kommentaren. „Anthropic“ steht nur in Einrichtung und Verwaltung (`app.js`).
- Interne Werte bleiben: `source = 'claude'`, CSS-Klassen `.claude`, `--claude`.
- Ruff: Zeilenlänge 130, Regeln E, F, W, B (`pyproject.toml`). JS: `node --check` für jede Datei unter `web/static/js`.
- Tests: `cd /root/Snap2CAD && /root/Snap2CAD-venv/bin/pytest -q` (volle Suite, ca. 80 s; pytest-xdist ist nicht installiert, also kein `-n`); Lint: `/root/Snap2CAD-venv/bin/ruff check .`. Jeder Task endet mit voller Suite + ruff, nicht nur mit den eigenen Dateien.
- Nachweise der Abnahmekriterien (Spec-Tabelle wird beim Abschluss angeglichen): A1 = `pytest tests/test_edges.py`; A2 = `pytest tests/test_parts.py tests/test_parts_api.py -k "massstab or referenz"`; A3 = `pytest tests/test_edges_api.py -k "zwei_teile or cad_auftrag"`; A4 = `pytest tests/test_edges_api.py -k erneute`; A5 = `pytest tests/test_texts.py`; A6 = `pytest tests/test_api.py -k mat_pdf` + Docker-Smoke. Formatwechsel und Migration stehen in `tests/test_parts_api.py`.
- Nebenläufigkeit: Jede Änderung an Teilen/Messungen und das folgende `refresh` laufen zusammen in `with db.atomic():` (Task 2). Ein KI-Aufruf liegt nie innerhalb von `db.atomic()`.
- Commits ohne Co-Autor-Zeile und ohne Erwähnung von Claude (Nutzervorgabe). Branch `kanten-und-teile`.
- Abweichungen von der Spec (bewusst):
  - Referenz-Hinweise stehen in `data.ref_warn` der Messung, Geometrie-Hinweise der Auto-Maße in `data.warn`, damit sich beide nicht überschreiben.
  - KI-Schätzwerte (`data.ai_value`) und manuelle Werte werden nie mit k skaliert, weil ihr Wert nicht aus Punkten berechnet wird.
  - Rechteck mit verdeckter Kante: L/B nur aus der sichtbaren Seite, sind beide Seiten verdeckt, aus dem Mittelwert mit dem Hinweis „verdeckt, geschätzt“.
  - Auto-Maße lassen sich keinem anderen Teil zuordnen (PATCH `part_id` → 400). Wer Punkte, Wert oder Art eines Auto-Maßes ändert, macht es zur normalen Messung.
  - Die CSV bekommt zusätzlich die Spalten „Teil“ und „Nennmaß“. Der CAD-Text schreibt „(montiertes Teil)“ statt „(montiert)“.
  - Die Bohrung wird per `fitEllipse` angepasst statt per Kreis-Kleinste-Quadrate.
  - Zusätzliche Hinweise: „Die KI hat keine Teile erkannt – …“. Bei einer erneuten Erkennung ohne KI-Ergebnis bleiben vorhandene Teile unverändert. Von Hand gezeichnete Teile (`source='user'`) werden bei einer erneuten Erkennung nie gelöscht.
  - Ein zweiter, gleichzeitiger Erkennungslauf wartet nicht, sondern bekommt sofort 429 „Kantenerkennung ist gerade belegt …“, damit der Threadpool nicht vollläuft.
  - Grenzen: höchstens 6 Umrisse je Erkennung, 64 Ecken je Polygon, 12 Teile je Foto.

## Review Focus

1. **Selbstüberschneidendes Polygon** (ein Eckpunkt wird über eine andere Kante gezogen): Speichern liefert 200, Zuordnung, Auto-Maße und Projektabruf stürzen nicht ab. Test in Task 5.
2. **Leere Unterlage** ohne Objekt: `edges.detect` liefert keine Umrisse, der Endpunkt meldet 422 „Kein Objekt erkannt – Teil von Hand zeichnen.“ Tests in Task 3 und Task 6.
3. **Objekt berührt den Rasterrand:** wird trotzdem gefunden, alle Ecken liegen innerhalb der Fläche. Test in Task 3.
4. **Unbrauchbare KI-Antwort** (Text drumherum, 2 Punkte, NaN, Strings, gar kein JSON): Die Antwort wird verworfen, es gibt Teile aus dem Umriss und einen Hinweis. Tests in Task 6.
5. **Foto mit Teilen und Messschieber-Referenz wird gelöscht** oder bekommt ein anderes Format: Die Referenzmessung bleibt als normale Messung erhalten, die Teile verschwinden. Test in Task 5.
6. **Zwei Anfragen gleichzeitig** (zwei Tabs, Loslassen beim Ziehen und sofort Umbenennen): keine doppelten Auto-Maße. Test in Task 5 (Threads).
7. **Erneute Erkennung, wenn die KI ausfällt:** Die vorhandenen Teile bleiben unverändert. Test in Task 6.

---

### Task 1: Texte ohne Claude, Prompt-Download entfernen

**Files:**
- Modify: `web/static/js/mat.js:39-40`, `web/static/js/app.js:63-73,229,272,281,316,703,719,726`, `web/static/js/cad.js:1,65,69,74-75,94,107,122,237,281`, `web/static/js/measure.js:73,499,515,526,539,567,574`
- Modify: `web/app/ai.py:218,247,249,251`, `web/app/main.py:718-723,1105,1164,1299`, `web/app/jobs.py:1,52,62,190,306`, `web/app/config.py:52`, `Dockerfile:43`
- Modify: `tests/test_api.py:36`, `tests/docker/smoke_api.py`
- Create: `tests/test_texts.py`

**Interfaces:**
- Produces: `jobs.SOURCE_LABEL: dict[str, str]` = `{"claude": "KI", "auto": "automatisch"}` (Task 5 und 7 nutzen es). Die Spaltenüberschrift „Messschieber“ steht in `measurement_table` und CSV.

- [ ] **Step 1: Failing Test schreiben** – `tests/test_texts.py`:

```python
"""Oberflaeche ohne Markennamen (Spec 2026-10-14-kanten-und-teile, A5)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = [*(ROOT / "web/static/js").glob("*.js"), *(ROOT / "web/static/css").glob("*.css"), ROOT / "web/static/index.html"]


def _code_lines(path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s.startswith("//") or s.startswith("#"):
            continue
        yield n, line


def test_static_ohne_claude():
    hits = [f"{p.name}:{n}" for p in STATIC for n, line in _code_lines(p) if "Claude" in line]
    assert hits == []


def test_anthropic_nur_in_einrichtung_und_verwaltung():
    hits = [f"{p.name}:{n}" for p in STATIC if p.name != "app.js"
            for n, line in _code_lines(p) if re.search(r"anthropic", line, re.I)]
    assert hits == []


def test_python_meldungen_neutral():
    allowed = ("Bitte den Anthropic-API-Schlüssel eingeben.",)
    hits = []
    for name in ("main.py", "jobs.py"):
        for n, line in _code_lines(ROOT / "web/app" / name):
            if ("HTTPException(" in line or "log(" in line) and re.search(r"Claude|Anthropic", line) \
                    and not any(a in line for a in allowed):
                hits.append(f"{name}:{n}")
    assert hits == []


def test_ki_fehler_neutral():
    src = (ROOT / "web/app/ai.py").read_text(encoding="utf-8")
    body = src.split("def call(", 1)[1].split("\ndef ", 1)[0]
    assert not re.search(r"AIError\(f?\"[^\"]*(Claude|Anthropic)", body)
```

- [ ] **Step 2: Test laufen lassen, er muss scheitern**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_texts.py`
Expected: 4 failed (Treffer u. a. in `app.js:63`, `cad.js:74`, `jobs.py:306`, `ai.py:247`).

- [ ] **Step 3: Frontend-Texte ändern**

`web/static/js/mat.js` – die Zeilen 39–40

```js
        h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, pdfBtn,
          h("a", { class: "btn big", href: "/api/prompt.md", download: "PROMPT.md" }, icon("file"), "Prompt herunterladen (PROMPT.md)"))),
```

werden zu

```js
        h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, pdfBtn)),
```

`web/static/js/app.js`:
- Zeile 63: `["/cad", "CAD mit Claude"]` → `["/cad", "CAD-Modell"]`.
- `statusPill()` (Zeilen 65–73) komplett ersetzen:

```js
function statusPill() {
  const st = S.status || {};
  let pill = null;
  if (st.ai_fake) pill = h("span", { class: "pill" }, h("span", { class: "dot warn" }), "Testmodus (AI_FAKE)");
  else if (!st.ai) pill = h("span", { class: "pill" }, h("span", { class: "dot off" }), "KI nicht eingerichtet");
  const sb = st.sandbox ? null : h("span", { class: "pill" }, h("span", { class: "dot err" }), "Sandbox offline");
  return [pill, sb];
}
```

  `header()` (Zeile 112) hängt `statusPill()` als Kinderliste an, und `h()` überspringt `null`. Zeile 781 filtert schon mit `.filter(Boolean)`.
- Zeilen 229 und 316: `"Bauteile per Foto vermessen · CAD mit Claude"` → `"Bauteile per Foto vermessen und als CAD-Modell nachbauen"`.
- Zeile 272: `"Lege das Administrator-Konto an und verbinde Claude. Erst danach ist Snap2CAD nutzbar."` → `"Lege das Administrator-Konto an und verbinde die KI. Erst danach ist Snap2CAD nutzbar."`.
- Zeile 281: `"2 · Claude verbinden"` → `"2 · KI verbinden"`.
- Zeile 703: `"Kein Schlüssel hinterlegt – Maßvorschläge und CAD mit Claude sind deaktiviert."` → `"Kein Schlüssel hinterlegt – KI-Funktionen sind deaktiviert."`.
- Zeile 719: `"Maßvorschläge und CAD mit Claude sind danach deaktiviert, bis ein neuer Schlüssel hinterlegt ist."` → `"KI-Funktionen sind danach deaktiviert, bis ein neuer Schlüssel hinterlegt ist."`.
- Zeile 726: `"Claude-Modell"` → `"KI-Modell"`.

`web/static/js/cad.js`:
- Zeile 1: `// Schritt 4: CAD mit Claude – Auftrag, Fortschritt, Ergebnis` → `// Schritt 4: CAD-Modell – Auftrag, Fortschritt, Ergebnis`.
- Zeile 65: `"Keine entzerrten Fotos – Claude arbeitet dann nur mit Maßen und Beschreibung."` → `"Keine entzerrten Fotos – das Modell entsteht dann nur aus Maßen und Beschreibung."`.
- Zeile 69: `"KI ist nicht eingerichtet (ANTHROPIC_API_KEY fehlt)."` → `"KI ist nicht eingerichtet (Verwaltung → Einstellungen)."`.
- Zeile 74: `"CAD-Modell mit Claude"` → `"CAD-Modell erzeugen"`.
- Zeile 75: `"Claude schreibt aus Maßen und Fotos ein parametrisches build123d-Modell. Der Code läuft abgeschottet auf dem Server und liefert STEP und STL."` → `"Aus Maßen und Fotos entsteht ein parametrisches build123d-Modell. Der Code läuft abgeschottet auf dem Server und liefert STEP und STL."`.
- Zeile 94: `"Je klarer die Funktion, desto besser trifft Claude Konstruktionsabsicht und Nennmaße."` → `"Je klarer die Funktion, desto besser trifft die KI Konstruktionsabsicht und Nennmaße."`.
- Zeile 107: `"Wird an Claude gesendet"` → `"Grundlage für das Modell"`.
- Zeile 122: die ganze Zeile `h("p", { class: "xs muted" }, "Fotos, Maße und Beschreibung werden an die Anthropic-API übertragen."),` löschen.
- Zeile 237: `["claude", "Claude-Antwort", !!V?.claude_text]` → `["claude", "KI-Antwort", !!V?.claude_text]`.
- Zeile 281: `"Annahmen von Claude"` → `"Annahmen der KI"`.

`web/static/js/measure.js`:
- Zeile 73: `"Claude vorschlagen"` → `"KI-Vorschläge"`.
- Zeile 499: `` `Claude: ${m.reason}` `` → `` `KI: ${m.reason}` ``.
- Zeile 515: `h("span", { class: "src-claude" }, "Claude")` → `h("span", { class: "src-claude" }, "KI")`.
- Zeile 526: `"Vorschläge von Claude "` → `"KI-Vorschläge "`.
- Zeile 539: `"Claude bekommt die entzerrten Fotos und deine Messungen. Übernommene Vorschläge erscheinen als normale Messung mit Herkunft „Claude“."` → `"Die KI bekommt die entzerrten Fotos und deine Messungen. Übernommene Vorschläge erscheinen als normale Messung mit Herkunft „KI“."`.
- Zeile 567: `"Claude analysiert …"` → `"KI analysiert …"`.
- Zeile 574: `` toast(n ? `${n} Vorschläge von Claude` : "Claude hat keine weiteren Maße gefunden", n ? "ok" : ""); `` → `` toast(n ? `${n} KI-Vorschläge` : "Die KI hat keine weiteren Maße gefunden", n ? "ok" : ""); ``.

- [ ] **Step 4: Backend-Texte ändern, Prompt-Endpunkt entfernen**

`web/app/ai.py` in `call()`:
- Zeile 218: `"Kein Anthropic-API-Schlüssel hinterlegt – KI-Funktionen sind deaktiviert."` → `"KI ist nicht eingerichtet – KI-Funktionen sind deaktiviert."`.
- Zeile 247: `"Anthropic-Ratenlimit erreicht – bitte später erneut versuchen."` → `"KI-Dienst: Ratenlimit erreicht – bitte später erneut versuchen."`.
- Zeile 249: `f"Anthropic-API-Fehler {e.status_code}: {getattr(e, 'message', e)}"` → `f"KI-Dienst: Fehler {e.status_code}: {getattr(e, 'message', e)}"`.
- Zeile 251: `"Keine Verbindung zur Anthropic-API."` → `"Keine Verbindung zum KI-Dienst."`.
- Die Meldungen in `verify()` bleiben, sie gehören zu Einrichtung und Verwaltung.

`web/app/main.py`:
- Zeilen 718–723 (`@app.get("/api/prompt.md")` samt Funktion `prompt_md`) löschen.
- Zeile 1105: `"KI ist nicht eingerichtet: Anthropic-API-Schlüssel fehlt (Verwaltung → Einstellungen)."` → `"KI ist nicht eingerichtet (Verwaltung → Einstellungen)."`.
- In `_csv` die Kopfzeile `"ID;Bezeichnung;Art;Wert;Einheit;Unsicherheit;Schieblehre;kritisch;Passung;Quelle;Ansicht;Punkte (mm)"` → `"ID;Bezeichnung;Art;Wert;Einheit;Unsicherheit;Messschieber;kritisch;Passung;Quelle;Ansicht;Punkte (mm)"`, und in `cells` `m["source"]` → `jobs.SOURCE_LABEL.get(m["source"], m["source"])`.
- Zeile 1299: `"claude": meta,` → `"ki": meta,`.

`web/app/jobs.py`:
- Zeile 1: Docstring `"""CAD-Auftraege: Claude -> Code -> Sandbox -> Pruefung -> ggf. Selbstkorrektur."""` → `"""CAD-Auftraege: KI -> Code -> Sandbox -> Pruefung -> ggf. Selbstkorrektur."""`.
- Unter `PROCESSES` einfügen:

```python
SOURCE_LABEL = {"claude": "KI", "auto": "automatisch"}
```

- In `measurement_table` „Schieblehre“ in der Kopfzeile → „Messschieber“, und in der Datenzeile `{m['source']}` → `{SOURCE_LABEL.get(m['source'], m['source'])}`.
- Zeile 190: `"KI ist nicht eingerichtet: Anthropic-API-Schlüssel fehlt (Verwaltung → Einstellungen)."` → `"KI ist nicht eingerichtet (Verwaltung → Einstellungen)."`.
- Zeile 306: `log(job_id, "Claude erstellt das Modell …" if trigger != "autofix" else "Claude korrigiert den Code …")` → `log(job_id, "KI erstellt das Modell …" if trigger != "autofix" else "KI korrigiert den Code …")`.

`web/app/config.py` Zeile 52: Kommentar `(enthaelt core/, PROMPT.md)` → `(enthaelt core/)`.

`Dockerfile` Zeile 43: `COPY PROMPT.md README.md LICENSE* ./` → `COPY README.md LICENSE* ./`.

`tests/test_api.py` Zeile 36: `assert admin.get("/api/prompt.md").status_code == 200` → `assert admin.get("/api/prompt.md").status_code == 404`.

`tests/docker/smoke_api.py`: direkt nach `assert call("GET", "/api/mat.pdf?format=A4")[:4] == b"%PDF"` einfügen:

```python
try:
    call("GET", "/api/prompt.md")
    raise AssertionError("/api/prompt.md darf es nicht mehr geben")
except urllib.error.HTTPError as e:
    assert e.code == 404, e.code
```

- [ ] **Step 5: Tests und Lint**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check . && for f in web/static/js/*.js; do node --check "$f" || exit 1; done`
Expected: alles grün. Fällt `test_static_ohne_claude` noch durch, zeigt die Trefferliste Datei und Zeile.

- [ ] **Step 6: Commit**

```bash
git add -A web/static/js web/app tests Dockerfile
git commit -m "Oberfläche ohne Claude-Nennung, Prompt-Download entfernt"
```

---

### Task 2: Datenbank – Tabelle `parts`, Spalte `measurements.part_id`, Migration

**Files:**
- Modify: `web/app/db.py` (SCHEMA nach `job_log`, `conn()`)
- Create: `tests/test_parts_api.py` (nur Migrationstest, wird in Task 5 erweitert)

**Interfaces:**
- Produces: Tabelle `parts(id, project_id, photo_id, seq, label, role, data, source, scale, created_at)`, Spalte `measurements.part_id` (mit Index `ix_meas_part`), Funktion `db._migrate(c)`, Kontextmanager `db.atomic()` (eine Transaktion, verschachtelbar, hält `db._lock`).

- [ ] **Step 1: Failing Test** – `tests/test_parts_api.py`:

```python
"""Teile und Massstab ueber die API (Spec 2026-10-14-kanten-und-teile §3, §7)."""
import sqlite3

OLD_MEAS = """CREATE TABLE measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, photo_id INTEGER,
  seq INTEGER NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL, value REAL, unit TEXT NOT NULL DEFAULT 'mm', unc REAL,
  data TEXT, critical INTEGER NOT NULL DEFAULT 0, caliper REAL, fit TEXT, source TEXT NOT NULL DEFAULT 'user',
  accepted INTEGER NOT NULL DEFAULT 1, reason TEXT, created_at TEXT NOT NULL);"""


def test_migration_ergaenzt_part_id(tmp_path, monkeypatch):
    from app import config, db
    path = tmp_path / "alt.db"
    con = sqlite3.connect(path)
    con.executescript(OLD_MEAS)
    con.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db, "_conn", None)
    try:
        cols = {r["name"] for r in db.q("PRAGMA table_info(measurements)")}
        assert "part_id" in cols
        assert db.q("SELECT name FROM sqlite_master WHERE type='table' AND name='parts'")
    finally:
        db._conn.close()


def test_atomic_rollback_und_verschachtelt():
    from app import db
    db.ex("CREATE TABLE IF NOT EXISTS t_atomic (v INTEGER)")
    try:
        with db.atomic():
            db.ex("INSERT INTO t_atomic VALUES (1)")
            with db.atomic():
                db.ex("INSERT INTO t_atomic VALUES (2)")
            raise RuntimeError("abbrechen")
    except RuntimeError:
        pass
    assert db.q("SELECT * FROM t_atomic") == []
    with db.atomic():
        db.ex("INSERT INTO t_atomic VALUES (3)")
    assert db.q("SELECT v FROM t_atomic") == [{"v": 3}]
    db.ex("DROP TABLE t_atomic")
```

`monkeypatch` stellt `db._conn` und `config.DB_PATH` nach dem Test wieder her.

- [ ] **Step 2: Test scheitert**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_parts_api.py`
Expected: FAIL `assert 'part_id' in cols`.

- [ ] **Step 3: Implementieren** – in `web/app/db.py` im `SCHEMA` nach der Tabelle `job_log` (vor den `CREATE INDEX`-Zeilen) einfügen:

```sql
CREATE TABLE IF NOT EXISTS parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, label TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'body',
  data TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'auto',
  scale REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL
);
```

und bei den Indizes:

```sql
CREATE INDEX IF NOT EXISTS ix_parts_photo ON parts(photo_id);
```

In `conn()` nach `c.executescript(SCHEMA)` die Zeile `_migrate(c)` einfügen und darunter (auf Modulebene, nach `conn()`):

```python
def _migrate(c: sqlite3.Connection):
    """Spalten nachruesten, die CREATE TABLE IF NOT EXISTS bei bestehenden Datenbanken nicht anlegt."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(measurements)").fetchall()}
    if "part_id" not in cols:
        c.execute("ALTER TABLE measurements ADD COLUMN part_id INTEGER REFERENCES parts(id) ON DELETE SET NULL")
    c.execute("CREATE INDEX IF NOT EXISTS ix_meas_part ON measurements(part_id)")
```

Für neue Datenbanken ebenfalls über `_migrate`. Die Spalte steht bewusst nicht im `CREATE TABLE measurements`, damit es genau einen Weg gibt. Der Index auf `part_id` steht deshalb auch in `_migrate` und nicht im SCHEMA, sonst scheitert das SCHEMA auf alten Datenbanken.

Nach `tx()` einfügen, dazu oben `from contextlib import contextmanager`:

```python
@contextmanager
def atomic():
    """Mehrere Lese-/Schreibschritte als eine Transaktion. Haelt _lock, damit parallele Anfragen (Threadpool)
    Aenderung + Neuberechnung nicht verschraenken. Verschachtelt = keine Savepoints: eine im inneren Block
    gefangene Ausnahme rollt nichts zurueck."""
    with _lock:
        c = conn()
        if c.in_transaction:
            yield c
            return
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")
```

`isolation_level=None` (Autocommit) ist gesetzt, `BEGIN IMMEDIATE` ist also erlaubt, und `db.ex`/`db.q` nehmen innerhalb denselben `RLock`.

- [ ] **Step 4: Tests**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/db.py tests/test_parts_api.py
git commit -m "Datenbank: Tabelle parts und Spalte measurements.part_id mit Migration"
```

---

### Task 3: Kantenerkennung `core/edges.py`

**Files:**
- Create: `core/edges.py`, `tests/test_edges.py`
- Modify: `tests/conftest.py:99-117` (`synthetic_photo`)

**Interfaces:**
- Produces: `edges.detect(rect: np.ndarray, fmt: str) -> dict` mit `{"outlines": [{"polygon": [[x, y], …], "area": float}], "holes": [{"c": [x, y], "d": float}], "segments": [{"id": "K1", "a": [x, y], "b": [x, y], "kind": "outline"|"inner"}], "px_per_mm": 10.0}`. Umrisse sind nach Fläche absteigend sortiert (höchstens `MAX_OUTLINES = 6`, je höchstens `MAX_VERTS = 64` Ecken), Segment-IDs laufen fortlaufend: erst alle Umrissseiten, dann die Innenkanten. Alle Zahlen sind Python-`float`, also JSON-fähig.
- Produces: `edges.draw_candidates(rect: np.ndarray, res: dict) -> np.ndarray` (Kopie der Draufsicht mit nummerierten Kandidaten, für die KI).
- Produces: `conftest.synthetic_photo(fmt, page, tilt, blur, objects=None)`.

- [ ] **Step 1: `synthetic_photo` erweitern** – in `tests/conftest.py` die Funktion ersetzen:

```python
def synthetic_photo(fmt: str = "A4", page: int = 0, tilt: float = 0.06, blur: bool = True,
                    objects: list[dict] | None = None) -> bytes:
    """Gerendertes Blatt perspektivisch verzerrt auf grauem Grund – wie ein leicht schraeges Handyfoto.

    objects: Objekte in mm der Rasterflaeche (Ursprung unten links), z. B. {"rect": [x, y, w, h], "gray": 150}
    oder {"circle": [cx, cy, d], "gray": 235}. None = ein dunkles Rechteck mittig (bisheriges Verhalten)."""
    import cv2
    import numpy as np

    from core import matgen
    px = 6.0
    sheet = _render_page(fmt, page, px)
    h, w = sheet.shape[:2]
    if page == 0 and objects is None:  # ein dunkles "Bauteil" mittig auflegen
        cv2.rectangle(sheet, (int(w * 0.35), int(h * 0.42)), (int(w * 0.65), int(h * 0.56)), (40, 42, 45), -1)
    elif page == 0:
        ox, oy = matgen.layout(fmt)["grid_origin_on_page_mm"]
        page_h = h / px

        def P(x, y):
            return int(round((x + ox) * px)), int(round((page_h - (y + oy)) * px))
        for o in objects:
            g = (o["gray"],) * 3
            if "rect" in o:
                x, y, rw, rh = o["rect"]
                cv2.rectangle(sheet, P(x, y + rh), P(x + rw, y), g, -1)
            if "circle" in o:
                cx, cy, d = o["circle"]
                cv2.circle(sheet, P(cx, cy), int(round(d / 2 * px)), g, -1, cv2.LINE_AA)
    W, H_ = int(w * 1.3), int(h * 1.2)
    dx, dy = w * tilt, h * tilt * 0.5
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * 0.15 + dx, h * 0.1], [w * 1.15 - dx, h * 0.1 + dy], [w * 1.15, h * 1.1], [w * 0.15, h * 1.1 - dy]])
    M = cv2.getPerspectiveTransform(src, dst)
    photo = cv2.warpPerspective(sheet, M, (W, H_), borderValue=(110, 112, 115))
    if blur:
        photo = cv2.GaussianBlur(photo, (3, 3), 0.8)
    ok, data = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return data.tobytes()
```

- [ ] **Step 2: Failing Tests** – `tests/test_edges.py`:

```python
"""Kantenerkennung auf synthetischen Draufsichten (Spec 2026-10-14-kanten-und-teile §1, A1)."""
import json
import math

import pytest

from conftest import synthetic_photo
from core import edges, vision

BOX = {"rect": [60, 80, 60, 40], "gray": 150}
PLATE = {"rect": [50, 105, 80, 20], "gray": 90}
HOLE = {"circle": [90, 115, 5], "gray": 235}


def _rect(objects, fmt="A4"):
    img = vision.load_image(synthetic_photo(fmt, objects=objects))
    a = vision.analyze(img, fmt)
    return vision.rectify_mat(img, a["homography"], a["format"])


def _close(poly, expected, tol):
    for ex in expected:
        d = min(math.hypot(p[0] - ex[0], p[1] - ex[1]) for p in poly)
        assert d <= tol, (ex, poly)


@pytest.fixture(scope="module")
def box():
    return edges.detect(_rect([BOX]), "A4")


@pytest.fixture(scope="module")
def two():
    return edges.detect(_rect([BOX, PLATE, HOLE]), "A4")


def test_quader_umriss(box):
    assert len(box["outlines"]) == 1
    poly = box["outlines"][0]["polygon"]
    assert len(poly) == 4
    _close(poly, [(60, 80), (120, 80), (120, 120), (60, 120)], 0.5)
    assert box["holes"] == [] and box["px_per_mm"] == 10.0


def test_platte_bohrung_innenkante(two):
    assert len(two["outlines"]) == 1
    poly = two["outlines"][0]["polygon"]
    _close(poly, [(50, 105), (50, 125), (130, 125), (130, 105), (60, 105), (60, 80), (120, 80), (120, 105)], 0.5)
    assert len(two["holes"]) == 1
    h = two["holes"][0]
    assert math.hypot(h["c"][0] - 90, h["c"][1] - 115) <= 0.3 and abs(h["d"] - 5) <= 0.3
    inner = [s for s in two["segments"] if s["kind"] == "inner"]
    assert any(abs(s["a"][1] - 105) < 1 and abs(s["b"][1] - 105) < 1 and abs(s["a"][0] - s["b"][0]) > 40 for s in inner), inner


def test_kandidaten_nummeriert_und_json(two):
    ids = [s["id"] for s in two["segments"]]
    assert ids == [f"K{i}" for i in range(1, len(ids) + 1)]
    assert sum(s["kind"] == "outline" for s in two["segments"]) == len(two["outlines"][0]["polygon"])
    json.dumps(two)


def test_leere_unterlage():
    res = edges.detect(_rect([]), "A4")
    assert res["outlines"] == [] and res["segments"] == [] and res["holes"] == []


def test_viele_objekte_begrenzt():
    objs = [{"rect": [30 + 20 * i, 30 + 22 * j, 15, 15], "gray": 120} for i in range(6) for j in range(7)]
    res = edges.detect(_rect(objs), "A4")
    assert 1 <= len(res["outlines"]) <= edges.MAX_OUTLINES
    assert all(len(o["polygon"]) <= edges.MAX_VERTS for o in res["outlines"])


def test_kandidatenbild(two):
    img = _rect([BOX, PLATE, HOLE])
    out = edges.draw_candidates(img, two)
    assert out.shape == img.shape and (out != img).any()


def test_objekt_am_rand():
    res = edges.detect(_rect([{"rect": [0, 60, 50, 30], "gray": 120}]), "A4")
    assert len(res["outlines"]) == 1
    poly = res["outlines"][0]["polygon"]
    assert all(-0.5 <= x <= 190.5 and -0.5 <= y <= 230.5 for x, y in poly)
    _close(poly, [(50, 60), (50, 90)], 0.5)
```

- [ ] **Step 3: Tests scheitern**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_edges.py`
Expected: FAIL mit `ImportError: cannot import name 'edges'`.

- [ ] **Step 4: `core/edges.py` implementieren**

```python
"""Kanten eines Objekts auf der entzerrten Draufsicht finden – ohne KI.

Eingabe: rect.jpg (10 px/mm, genau die Rasterflaeche). Ausgabe in mm der Rasterflaeche
(Ursprung unten links, x nach rechts, y nach oben), siehe Spec 2026-10-14-kanten-und-teile §1.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .vision import PX_PER_MM, spec

WORK_PXMM = 4.0        # Aufloesung fuer die Objektmaske
MIN_AREA_MM2 = 25.0
APPROX_MM = 0.8
SEARCH_MM = 1.5        # Suchweite der Kantenverfeinerung entlang der Normalen
MAX_SHIFT_MM = 2.0
MIN_SEG_MM = 8.0
MAX_SEGMENTS = 40
MAX_OUTLINES = 6
MAX_VERTS = 64


def _odd(n: float) -> int:
    return max(3, int(round(n)) | 1)


def _marker_mask(fmt: str, shape, pxmm: float) -> np.ndarray:
    """255 = auswertbar, 0 = Markerfeld (alle Marker liegen innerhalb der Rasterflaeche)."""
    sp = spec(fmt)
    gh = sp["grid_mm"][1]
    valid = np.full(shape, 255, np.uint8)
    half = sp["marker_size_mm"] / 2 + 2
    for cx, cy in sp["centers_mm"].values():
        x0, x1 = int((cx - half) * pxmm), int(math.ceil((cx + half) * pxmm))
        y0, y1 = int((gh - cy - half) * pxmm), int(math.ceil((gh - cy + half) * pxmm))
        valid[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = 0
    return valid


def _drop_small(mask: np.ndarray, pxmm: float) -> np.ndarray:
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] / pxmm ** 2 >= MIN_AREA_MM2:
            keep[lbl == i] = 255
    return keep


def _grabcut(mask: np.ndarray, img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """GrabCut nur im Begrenzungsrahmen der Maske plus 10 mm (Spec §1.4)."""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return mask
    h, w = mask.shape
    m = int(10 * WORK_PXMM)
    x0, y0 = max(0, int(xs.min()) - m), max(0, int(ys.min()) - m)
    x1, y1 = min(w, int(xs.max()) + m + 1), min(h, int(ys.max()) + m + 1)
    sub = mask[y0:y1, x0:x1]
    gc = np.full(sub.shape, cv2.GC_PR_BGD, np.uint8)
    gc[sub > 0] = cv2.GC_PR_FGD
    gc[cv2.erode(sub, np.ones((5, 5), np.uint8)) > 0] = cv2.GC_FGD
    gc[valid[y0:y1, x0:x1] == 0] = cv2.GC_BGD
    if not (gc == cv2.GC_PR_BGD).any():
        return mask
    try:
        cv2.grabCut(np.ascontiguousarray(img[y0:y1, x0:x1]), gc, None, np.zeros((1, 65)), np.zeros((1, 65)), 3,
                    cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return mask
    out = mask.copy()
    out[y0:y1, x0:x1] = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    out[valid == 0] = 0
    out = _drop_small(out, WORK_PXMM)
    return out if int(out.sum()) >= 0.5 * int(mask.sum()) else mask


def _mask(rect: np.ndarray, fmt: str) -> np.ndarray:
    """Objektmaske auf WORK_PXMM (255 = Objekt), Spec §1.1–1.4."""
    s = WORK_PXMM / PX_PER_MM
    small = cv2.resize(rect, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    valid = _marker_mask(fmt, (h, w), WORK_PXMM)
    k = _odd(1.5 * WORK_PXMM)
    closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    lab = cv2.cvtColor(closed, cv2.COLOR_BGR2LAB).astype(np.float32)
    b = int(8 * WORK_PXMM)
    band = np.zeros((h, w), bool)
    band[:b] = True
    band[-b:] = True
    band[:, :b] = True
    band[:, -b:] = True
    band &= valid > 0
    paper = np.median(lab[band], axis=0)
    dl = np.clip(paper[0] - lab[..., 0], 0, None)
    dc = np.hypot(lab[..., 1] - paper[1], lab[..., 2] - paper[2])
    diff = np.clip(dl + 2 * dc, 0, 255).astype(np.uint8)
    diff[valid == 0] = 0
    th, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    mask = np.where(diff > max(th, 18.0), 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return _grabcut(_drop_small(mask, WORK_PXMM), closed, valid)


def _refine(poly: list, gx: np.ndarray, gy: np.ndarray, gh: float) -> list:
    """Polygonseiten auf dem vollen Bild an den staerksten Gradienten legen (Spec §1.5)."""
    px = PX_PER_MM
    H, W = gx.shape
    P = [np.array([x * px - 0.5, (gh - y) * px - 0.5]) for x, y in poly]
    n = len(P)
    offs = np.arange(-SEARCH_MM * px, SEARCH_MM * px + 0.01, 0.5)
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        L = float(np.linalg.norm(b - a))
        if L < 5 * px:
            lines.append(None)
            continue
        t = (b - a) / L
        nrm = np.array([-t[1], t[0]])
        pts = []
        for s in np.arange(2 * px, L - 2 * px, px / 2):
            q = a + t * s + nrm[None, :] * offs[:, None]
            xi = np.clip(np.rint(q[:, 0]).astype(int), 0, W - 1)
            yi = np.clip(np.rint(q[:, 1]).astype(int), 0, H - 1)
            v = np.abs(gx[yi, xi] * nrm[0] + gy[yi, xi] * nrm[1])
            k = int(v.argmax())
            if v[k] < 40:
                continue
            sub = 0.0
            if 0 < k < len(v) - 1:
                den = v[k - 1] - 2 * v[k] + v[k + 1]
                sub = float(0.5 * (v[k - 1] - v[k + 1]) / den) if den else 0.0
            pts.append(a + t * s + nrm * (offs[k] + sub * 0.5))
        if len(pts) < 4:
            lines.append(None)
            continue
        vx, vy, x0, y0 = cv2.fitLine(np.array(pts, np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines.append((np.array([x0, y0], float), np.array([vx, vy], float)))
    out = []
    for i in range(n):
        v = P[i]
        l1, l2 = lines[i - 1], lines[i]
        if l1 is not None and l2 is not None:
            (p1, d1), (p2, d2) = l1, l2
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) > math.sin(math.radians(10)):
                tt = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
                q = p1 + d1 * tt
                if np.linalg.norm(q - v) <= MAX_SHIFT_MM * px:
                    v = q
        out.append([round(float((v[0] + 0.5) / px), 3), round(float(gh - (v[1] + 0.5) / px), 3)])
    return out


def _refine_hole(c: tuple, d0: float, gray: np.ndarray, gh: float) -> dict | None:
    """Bohrung auf dem vollen Bild: Schwelle zwischen Innen- und Ringhelligkeit, Ellipse anpassen (Spec §1.6)."""
    px = PX_PER_MM
    cx, cy = c[0] * px - 0.5, (gh - c[1]) * px - 0.5
    r = d0 / 2 * px
    R = int(math.ceil(1.8 * r)) + 2
    x0, y0 = max(0, int(cx) - R), max(0, int(cy) - R)
    roi = gray[y0:int(cy) + R + 1, x0:int(cx) + R + 1]
    if roi.size == 0:
        return None
    yy, xx = np.mgrid[y0:y0 + roi.shape[0], x0:x0 + roi.shape[1]]
    dist = np.hypot(xx - cx, yy - cy)
    inner, ring = roi[dist <= 0.6 * r], roi[(dist >= 1.3 * r) & (dist <= 1.6 * r)]
    if not len(inner) or not len(ring):
        return None
    mi, mr = float(np.median(inner)), float(np.median(ring))
    thr = (mi + mr) / 2
    bw = (((roi > thr) if mi > mr else (roi < thr)) & (dist <= 1.3 * r)).astype(np.uint8)
    _, lbl = cv2.connectedComponents(bw)
    iy, ix = int(round(cy)) - y0, int(round(cx)) - x0
    if not (0 <= iy < lbl.shape[0] and 0 <= ix < lbl.shape[1]) or lbl[iy, ix] == 0:
        return None
    cnts, _ = cv2.findContours((lbl == lbl[iy, ix]).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c2 = max(cnts, key=cv2.contourArea)
    if len(c2) < 5:
        return None
    (ex, ey), (ma, mb), _ = cv2.fitEllipse(c2)
    d = (ma + mb) / 2 / px
    if not 0.7 * d0 <= d <= 1.3 * d0:
        return None
    return {"c": [round((x0 + ex + 0.5) / px, 3), round(gh - (y0 + ey + 0.5) / px, 3)], "d": round(float(d), 3)}


def _holes(cnts, hier, gray: np.ndarray, gh: float) -> list[dict]:
    out = []
    for i, c in enumerate(cnts):
        if hier[i][3] < 0:
            continue
        area = cv2.contourArea(c) / WORK_PXMM ** 2
        per = cv2.arcLength(c, True) / WORK_PXMM
        if per <= 0 or area < math.pi or 4 * math.pi * area / per ** 2 < 0.85:  # Ø < 2 mm oder nicht rund
            continue
        (cx, cy), _ = cv2.minEnclosingCircle(c)
        c_mm = ((cx + 0.5) / WORK_PXMM, gh - (cy + 0.5) / WORK_PXMM)
        d0 = 2 * math.sqrt(area / math.pi)
        out.append(_refine_hole(c_mm, d0, gray, gh) or
                   {"c": [round(float(c_mm[0]), 3), round(float(c_mm[1]), 3)], "d": round(float(d0), 3)})
    return out


def _try_merge(a: list, b: list) -> list | None:
    """Kollineare Stuecke zusammenfassen: Winkel < 3°, Abstand < 1 mm, Luecke < 2 mm (Spec §1.7)."""
    ax, ay, bx, by = a
    L = math.hypot(bx - ax, by - ay)
    if L < 1e-9:
        return None
    ux, uy = (bx - ax) / L, (by - ay) / L
    d = abs(math.degrees(math.atan2(uy, ux) - math.atan2(b[3] - b[1], b[2] - b[0]))) % 180
    if min(d, 180 - d) >= 3:
        return None
    for qx, qy in ((b[0], b[1]), (b[2], b[3])):
        if abs((qx - ax) * uy - (qy - ay) * ux) >= 1.0:
            return None
    t = [0.0, L, (b[0] - ax) * ux + (b[1] - ay) * uy, (b[2] - ax) * ux + (b[3] - ay) * uy]
    lo_b, hi_b = sorted(t[2:])
    if lo_b > L + 2 or hi_b < -2:
        return None
    lo, hi = min(t), max(t)
    return [ax + ux * lo, ay + uy * lo, ax + ux * hi, ay + uy * hi]


def _merge(segs: list) -> list:
    segs = [list(s) for s in segs]
    changed = True
    while changed:
        changed = False
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                m = _try_merge(segs[i], segs[j])
                if m:
                    segs[i] = m
                    del segs[j]
                    changed = True
                    break
            if changed:
                break
    return segs


def _seg_len(s) -> float:
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _segments(gray: np.ndarray, mask_full: np.ndarray, gh: float) -> list:
    """Gerade Innenkanten mit LSD (ohne Canny) innerhalb der um 1,5 mm erodierten Maske (Spec §1.7)."""
    px = PX_PER_MM
    k = _odd(3 * px)
    inner = cv2.erode(mask_full, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    found = cv2.createLineSegmentDetector().detect(gray)[0]
    if found is None:
        return []
    H, W = gray.shape
    segs = []
    ts = np.linspace(0, 1, 5)
    for row in found.reshape(-1, 4):
        x1, y1, x2, y2 = (float(v) for v in row)
        if math.hypot(x2 - x1, y2 - y1) < 2 * px:
            continue
        xs = np.clip(np.rint(x1 + (x2 - x1) * ts).astype(int), 0, W - 1)
        ys = np.clip(np.rint(y1 + (y2 - y1) * ts).astype(int), 0, H - 1)
        if int((inner[ys, xs] > 0).sum()) >= 3:
            segs.append([(x1 + 0.5) / px, gh - (y1 + 0.5) / px, (x2 + 0.5) / px, gh - (y2 + 0.5) / px])
    segs = sorted(segs, key=_seg_len, reverse=True)[:300]
    segs = [s for s in _merge(segs) if _seg_len(s) >= MIN_SEG_MM]
    return sorted(segs, key=_seg_len, reverse=True)[:MAX_SEGMENTS]


def detect(rect: np.ndarray, fmt: str) -> dict:
    """Umrisse, Bohrungen und Kanten-Kandidaten (Spec §1). Leere Listen, wenn kein Objekt gefunden wurde."""
    gh = float(spec(fmt)["grid_mm"][1])
    mask = _mask(rect, fmt)
    gray = cv2.morphologyEx(cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outlines, holes = [], []
    if cnts:
        hier = hier[0]
        for i, c in enumerate(cnts):
            if hier[i][3] >= 0:
                continue
            area = cv2.contourArea(c) / WORK_PXMM ** 2
            if area < MIN_AREA_MM2:
                continue
            eps = APPROX_MM * WORK_PXMM
            ap = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
            while len(ap) > MAX_VERTS and eps < 8 * WORK_PXMM:  # sehr unruhige Umrisse vereinfachen
                eps *= 1.5
                ap = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
            if not 3 <= len(ap) <= MAX_VERTS:
                continue
            coarse = [[(float(x) + 0.5) / WORK_PXMM, gh - (float(y) + 0.5) / WORK_PXMM] for x, y in ap]
            outlines.append({"polygon": _refine(coarse, gx, gy, gh), "area": round(float(area), 1)})
        holes = _holes(cnts, hier, gray, gh)
    outlines.sort(key=lambda o: -o["area"])
    del outlines[MAX_OUTLINES:]
    segs = []
    if outlines:
        full = cv2.resize(mask, (rect.shape[1], rect.shape[0]), interpolation=cv2.INTER_NEAREST)
        segs = _segments(gray, full, gh)
    segments, n = [], 0
    for o in outlines:
        P = o["polygon"]
        for i in range(len(P)):
            n += 1
            segments.append({"id": f"K{n}", "a": P[i], "b": P[(i + 1) % len(P)], "kind": "outline"})
    for x1, y1, x2, y2 in segs:
        n += 1
        segments.append({"id": f"K{n}", "a": [round(x1, 3), round(y1, 3)], "b": [round(x2, 3), round(y2, 3)], "kind": "inner"})
    return {"outlines": outlines, "holes": holes if outlines else [], "segments": segments, "px_per_mm": PX_PER_MM}


def draw_candidates(rect: np.ndarray, res: dict) -> np.ndarray:
    """Draufsicht mit eingezeichneten, nummerierten Kandidaten (Bildvorlage fuer die KI-Zuordnung)."""
    img = rect.copy()
    px = res["px_per_mm"]
    gh = img.shape[0] / px
    colors = [(178, 111, 31), (12, 85, 194), (46, 125, 79), (150, 40, 160)]

    def P(q):
        return int(round(q[0] * px)), int(round((gh - q[1]) * px))
    for i, s in enumerate(res["segments"]):
        a, b, col = P(s["a"]), P(s["b"]), colors[i % len(colors)]
        cv2.line(img, a, b, col, 4, cv2.LINE_AA)
        mid = ((a[0] + b[0]) // 2 + 6, (a[1] + b[1]) // 2 - 6)
        cv2.putText(img, s["id"], mid, cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 5, cv2.LINE_AA)
        cv2.putText(img, s["id"], mid, cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, 2, cv2.LINE_AA)
    return img
```

- [ ] **Step 5: Tests grün**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check .`
Expected: PASS. Wenn `test_leere_unterlage` einen Umriss findet: prüfen, ob Achsbeschriftungen oder Rasterlinien die Maske erreichen (`diff` und Schwelle ausgeben). Gegenmittel: Untergrenze 18 → 24 anheben, nicht den Schließkern vergrößern.

- [ ] **Step 5b: Gegenprobe mit echten Fotos (blockiert die synthetischen Tests nicht)**

Falls auf der DS918+ schon Fotos liegen: 2–3 `rect.jpg` aus dem Volume `snap2cad_data` (`/data/photos/<id>/rect.jpg` im Container) ins Scratchpad kopieren, z. B. `ssh <nas> 'cd /volume1/docker/snap2cad && sudo -n /usr/local/bin/docker compose exec -T app cat /data/photos/<id>/rect.jpg' > $SCRATCH/real_<id>.jpg`. Den Pfad im Container vorher mit `ls` prüfen, den SSH-Zugang beschreibt die Memory `snap2cad-nas`. Dann `edges.detect` mit dem Format des Fotos laufen lassen und notieren: Umrisszahl, Eckenzahl je Umriss, Segmentzahl, Laufzeit.

Die Fotos sind Nutzerdaten: Sie bleiben im Scratchpad und kommen nie ins Repo oder in Tests. Wird kein Umriss gefunden oder bekommt ein Quader mehr als 8 Ecken, `APPROX_MM` bzw. die Schwelle 18 nachstellen und den Grund im Commit nennen. Gibt es keine Fotos, wird das vermerkt, und A8 (Task 9) übernimmt die Gegenprobe.

- [ ] **Step 6: Commit**

```bash
git add core/edges.py tests/test_edges.py tests/conftest.py
git commit -m "Kantenerkennung: Umriss, Bohrungen und Kanten-Kandidaten auf der Draufsicht"
```

---

### Task 4: `web/app/parts.py` – reine Geometrie

**Files:**
- Create: `web/app/parts.py` (erster Teil: Geometrie ohne Datenbank), `tests/test_parts.py`

**Interfaces:**
- Produces (alle in `app.parts`):
  - `edges_of(poly) -> list[tuple]`, `is_rect(poly) -> bool`, `circle_points(c, d) -> list`
  - `auto_dims(data: dict, fx=1.0, fy=1.0) -> list[{"key", "kind", "name", "raw", "points", "warn"}]`. `data` braucht `polygon`, `edge_ids`, `hidden` (Kanten-IDs) und `holes` (`[{"id", "c", "d"}]`).
  - `update_edge_ids(old_poly, old_ids, new_poly, next_id) -> (ids, next_id)`, `transfer_ids(old_poly, old_ids, new_poly, next_id) -> (ids, next_id)`, `transfer_holes(old_holes, new_holes, next_id) -> (holes, next_id)`
  - `snap_polygon(poly, segments, preferred=()) -> (polygon, hidden_flags: list[bool])`
  - `assign(points, parts: list[(id, polygon)]) -> id | None`
  - `scale_of(ratios: list[(mid, ratio)]) -> (k, good_mids, bad_mids, warn)`
  - `nominal(value, unc, caliper=None) -> float | None`
  - `match_parts(old: list[(key, poly)], new: list[(key, poly)], threshold=0.5) -> {new_key: old_key}`
  - `assign_holes(parts_list: list[dict], holes: list[dict]) -> None` (setzt `holes` in jedem Eintrag)
  - `_ccw(poly, flags=None) -> (poly, flags)`

- [ ] **Step 1: Failing Tests** – `tests/test_parts.py`:

```python
"""Teile: Geometrie, Kanten-Kennungen, Massstab (Spec 2026-10-14-kanten-und-teile §2/§3, A2)."""
import pytest

from app import parts

R = [[0, 0], [63.6, 0], [63.6, 42.4], [0, 42.4]]
BOX = [[60, 80], [120, 80], [120, 120], [60, 120]]
PLATE = [[50, 105], [130, 105], [130, 125], [50, 125]]


def data(poly, hidden=(), holes=()):
    ids = list(range(1, len(poly) + 1))
    return {"polygon": poly, "edge_ids": ids, "next_edge_id": len(ids) + 1, "hidden": list(hidden),
            "holes": [{"id": i + 1, **h} for i, h in enumerate(holes)]}


def test_rechteck_auto_masse():
    dims = {d["key"]: d for d in parts.auto_dims(data(R))}
    assert set(dims) == {"L", "B"}
    assert dims["L"]["raw"] == pytest.approx(63.6) and dims["B"]["raw"] == pytest.approx(42.4)
    assert dims["L"]["points"] == [[0, 0], [63.6, 0]] and dims["B"]["points"] == [[0, 42.4], [0, 0]]
    assert dims["L"]["name"] == "Länge" and dims["B"]["name"] == "Breite"


def test_rechteck_ungleiche_und_verdeckte_kante():
    poly = [[0, 0], [60, 0], [61.5, 40], [0, 40]]
    dims = {d["key"]: d for d in parts.auto_dims(data(poly))}
    assert "ungleich" in dims["L"]["warn"]
    dims = {d["key"]: d for d in parts.auto_dims(data(poly, hidden=[3]))}  # Kante 3 = oben
    assert dims["L"]["raw"] == pytest.approx(60) and dims["L"]["warn"] is None


def test_polygon_kanten_und_bohrung():
    L = [[0, 0], [40, 0], [40, 10], [10, 10], [10, 30], [0, 30]]
    dims = parts.auto_dims(data(L, hidden=[2], holes=[{"c": [5, 5], "d": 3}]))
    assert [d["key"] for d in dims] == ["E1", "E2", "E3", "E4", "E5", "E6", "H1"]
    assert dims[1]["warn"] == "verdeckt, geschätzt" and dims[0]["raw"] == pytest.approx(40)
    assert dims[0]["name"] == "Kante 1"
    assert dims[6]["kind"] == "diameter" and dims[6]["raw"] == pytest.approx(3) and len(dims[6]["points"]) == 3


def test_kennungen_einfuegen_loeschen_verschieben():
    old = [[0, 0], [60, 0], [60, 40], [0, 40]]
    five = [[0, 0], [45, 0], [60, 0], [60, 40], [0, 40]]
    assert parts.update_edge_ids(old, [1, 2, 3, 4], five, 5) == ([1, 5, 2, 3, 4], 6)   # 45 mm behaelt die 1
    assert parts.update_edge_ids(five, [1, 5, 2, 3, 4], old, 6) == ([1, 2, 3, 4], 6)   # zur laengeren verschmolzen
    assert parts.update_edge_ids(old, [1, 2, 3, 4], [[0, 0], [61, 0], [60, 40], [0, 40]], 5) == ([1, 2, 3, 4], 5)
    six = [[0, 0], [30, 0], [30, 5], [60, 5], [60, 40], [0, 40]]                          # kein Einfuegen/Loeschen -> uebertragen
    ids, nxt = parts.update_edge_ids(old, [1, 2, 3, 4], six, 5)
    assert len(ids) == 6 and 3 in ids and 4 in ids and nxt > 5


def test_kennungen_uebertragen():
    old = [[0, 0], [60, 0], [60, 40], [0, 40]]
    new = [[0.5, 40.2], [0.3, 0.1], [60.2, 0.2], [60.1, 40.1]]
    assert parts.transfer_ids(old, [1, 2, 3, 4], new, 5) == ([4, 1, 2, 3], 5)
    holes, nxt = parts.transfer_holes([{"id": 1, "c": [5, 5], "d": 3}], [{"c": [5.5, 5.2], "d": 3.1}, {"c": [30, 30], "d": 4}], 2)
    assert [h["id"] for h in holes] == [1, 2] and nxt == 3


SEGS = [{"id": "K1", "a": [60.1, 80.0], "b": [120.0, 80.1], "kind": "outline"},
        {"id": "K2", "a": [120.0, 80.1], "b": [120.0, 104.8], "kind": "outline"},
        {"id": "K3", "a": [60.1, 104.8], "b": [60.1, 80.0], "kind": "outline"},
        {"id": "K4", "a": [49.9, 104.8], "b": [129.8, 104.8], "kind": "inner"}]


def test_einrasten_mit_verdeckter_kante():
    poly, hidden = parts.snap_polygon([[61, 81], [119, 81], [119, 119], [61, 119]], SEGS)
    assert hidden == [False, False, True, False]
    assert poly[0] == pytest.approx([60.1, 80.0], abs=0.05) and poly[1] == pytest.approx([120.0, 80.1], abs=0.05)
    assert poly[2] == pytest.approx([120.0, 119.0], abs=0.05)


def test_einrasten_bevorzugt_genannte_kandidaten():
    segs = [{"id": "K1", "a": [0, 0.5], "b": [50, 0.5], "kind": "outline"},
            {"id": "K2", "a": [0, 2.0], "b": [50, 2.0], "kind": "inner"}]
    ki = [[0, 1.0], [50, 1.0], [50, 30], [0, 30]]
    assert parts.snap_polygon(ki, segs)[0][0][1] == pytest.approx(0.5)
    assert parts.snap_polygon(ki, segs, preferred=["K2"])[0][0][1] == pytest.approx(2.0)


def test_zuordnung_bei_ueberlappung():
    ps = [(1, BOX), (2, PLATE)]
    assert parts.assign([[70, 105], [110, 105]], ps) == 2      # Plattenkante ueber dem Quader
    assert parts.assign([[60, 85], [120, 85]], ps) == 1        # Quaderbreite
    assert parts.assign([[80, 110], [100, 110]], ps) == 2      # innen in beiden -> kleinere Flaeche
    assert parts.assign([[10, 10], [20, 10]], ps) is None


def test_zuordnung_mit_selbstueberschneidung():
    bow = [[0, 0], [40, 40], [40, 0], [0, 40]]
    assert parts.assign([[5, 20], [8, 20]], [(1, bow)]) in (1, None)


def test_massstab():
    k, good, bad, warn = parts.scale_of([(1, 60 / 63.6)])
    assert k == pytest.approx(0.9434, abs=1e-4) and good == [1] and bad == [] and warn is None
    _, _, _, warn = parts.scale_of([(1, 0.943), (2, 0.943 * 1.015)])
    assert warn and "widersprechen" in warn
    k, good, bad, _ = parts.scale_of([(1, 1.40)])
    assert k == 1.0 and bad == [1] and good == []


def test_nennmass():
    assert parts.nominal(60.12, 0.3) == 60.0
    assert parts.nominal(60.27, 0.05) is None
    assert parts.nominal(59.7, 0.5, caliper=60.02) == 60.02


def test_abgleich_ueber_ueberlappung():
    old = [(10, BOX), (11, PLATE)]
    new = [(0, [[50.4, 105.2], [130.1, 105], [130, 125.3], [50, 125]]), (1, [[61, 81], [119, 81], [119, 119], [61, 119]]),
           (2, [[0, 0], [10, 0], [10, 10]])]
    assert parts.match_parts(old, new) == {0: 11, 1: 10}


def test_bohrung_zum_kleinsten_teil():
    lst = [{"polygon": BOX}, {"polygon": PLATE}]
    parts.assign_holes(lst, [{"c": [90, 115], "d": 5}, {"c": [300, 300], "d": 2}])
    assert lst[0]["holes"] == [] and lst[1]["holes"] == [{"c": [90, 115], "d": 5}]


def test_ccw_dreht_kennzeichen_mit():
    cw = [[0, 0], [0, 40], [60, 40], [60, 0]]
    poly, flags = parts._ccw(cw, [False, True, False, False])  # Kante 1 (oben) verdeckt
    assert poly == [[60, 0], [60, 40], [0, 40], [0, 0]]
    i = flags.index(True)
    assert {tuple(poly[i]), tuple(poly[(i + 1) % 4])} == {(0, 40), (60, 40)}
```

- [ ] **Step 2: Tests scheitern**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_parts.py`
Expected: FAIL `ImportError: cannot import name 'parts'`.

- [ ] **Step 3: Implementieren** – `web/app/parts.py`:

```python
"""Teile im Foto: Kanten-Kennungen, Auto-Masse, Zuordnung und Massstab je Teil.

Siehe Spec docs/superpowers/specs/2026-10-14-kanten-und-teile-design.md §2–§3.
"""
from __future__ import annotations

import math
import statistics

from shapely.geometry import LinearRing, Point, Polygon

from . import geom

RECT_TOL_DEG = 4.0
EDGE_DIFF_MM = 1.0
ON_EDGE_MM = 1.5
SCALE_RANGE = (0.75, 1.25)
SPREAD_MAX = 0.01
SCALED_KINDS = ("length", "diameter", "radius")
MM_KINDS = ("length", "height", "diameter", "radius")
ROLE_TEXT = {"body": "Grundkörper", "mounted": "montiertes Teil"}


# ------------------------------------------------------------------ Geometrie (ohne Datenbank)

def edges_of(poly):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


def _seg_len(a, b, fx=1.0, fy=1.0):
    return math.hypot((b[0] - a[0]) * fx, (b[1] - a[1]) * fy)


def _mid(e):
    (a, b) = e
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _angle(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _angle_diff(a1, a2):
    """Winkel zwischen zwei Geraden ohne Richtung, 0..90 Grad."""
    d = abs(math.degrees(a1 - a2)) % 180
    return min(d, 180 - d)


def _valid(poly):
    P = Polygon(poly)
    return P if P.is_valid else P.buffer(0)


def _ccw(poly, flags=None):
    """Polygon gegen den Uhrzeigersinn; Kanten-Kennzeichen (je Kante) werden mitgedreht."""
    pts = [[round(float(x), 3), round(float(y), 3)] for x, y in poly]
    try:
        is_ccw = LinearRing(pts).is_ccw
    except ValueError:
        is_ccw = True
    if is_ccw:
        return pts, (list(flags) if flags is not None else None)
    n = len(pts)
    return pts[::-1], ([flags[(n - 2 - j) % n] for j in range(n)] if flags is not None else None)


def is_rect(poly):
    if len(poly) != 4:
        return False
    for i in range(4):
        a, v, b = poly[i - 1], poly[i], poly[(i + 1) % 4]
        u1, u2 = (a[0] - v[0], a[1] - v[1]), (b[0] - v[0], b[1] - v[1])
        n1, n2 = math.hypot(*u1), math.hypot(*u2)
        if n1 < 1e-6 or n2 < 1e-6:
            return False
        c = max(-1.0, min(1.0, (u1[0] * u2[0] + u1[1] * u2[1]) / (n1 * n2)))
        if abs(math.degrees(math.acos(c)) - 90) > RECT_TOL_DEG:
            return False
    return True


def circle_points(c, d):
    r = d / 2
    return [[round(c[0] + r * math.cos(a), 3), round(c[1] + r * math.sin(a), 3)] for a in (0, 2 * math.pi / 3, 4 * math.pi / 3)]


def auto_dims(data, fx=1.0, fy=1.0):
    """Auto-Masse eines Teils (Spec §3). raw = Fotowert ohne Teil-Massstab, mit Kontrollmass-Faktoren."""
    poly, ids, hidden = data["polygon"], data["edge_ids"], set(data.get("hidden") or [])
    E = edges_of(poly)
    out = []
    if is_rect(poly):
        lens = [geom.compute("length", [a, b], fx, fy) for a, b in E]
        raws, picks, warns = [], [], []
        for i, j in ((0, 2), (1, 3)):
            vis = [k for k in (i, j) if ids[k] not in hidden]
            use = vis or [i, j]
            raws.append(sum(lens[k] for k in use) / len(use))
            picks.append(use)
            if not vis:
                warns.append("verdeckt, geschätzt")
            elif len(vis) == 2 and abs(lens[i] - lens[j]) > EDGE_DIFF_MM:
                warns.append("gegenüberliegende Kanten ungleich – Kante prüfen")
            else:
                warns.append(None)
        first = 0 if raws[0] >= raws[1] else 1
        for key, name, pi in (("L", "Länge", first), ("B", "Breite", 1 - first)):
            use = picks[pi]
            horiz = _angle_diff(_angle(*E[use[0]]), 0.0) < 45
            side = min(use, key=lambda k: _mid(E[k])[1] if horiz else _mid(E[k])[0])
            out.append({"key": key, "kind": "length", "name": name, "raw": round(raws[pi], 3),
                        "points": [list(E[side][0]), list(E[side][1])], "warn": warns[pi]})
    else:
        for (a, b), eid in zip(E, ids, strict=True):
            out.append({"key": f"E{eid}", "kind": "length", "name": f"Kante {eid}", "raw": geom.compute("length", [a, b], fx, fy),
                        "points": [list(a), list(b)], "warn": "verdeckt, geschätzt" if eid in hidden else None})
    for hole in data.get("holes") or []:
        out.append({"key": f"H{hole['id']}", "kind": "diameter", "name": f"Bohrung {hole['id']}",
                    "raw": geom.compute("diameter", circle_points(hole["c"], hole["d"]), fx, fy),
                    "points": circle_points(hole["c"], hole["d"]), "warn": None})
    return out


def _same(p, q, tol=1e-3):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def update_edge_ids(old_poly, old_ids, new_poly, next_id):
    """Kanten-Kennungen nach einer Aenderung durch den Nutzer (Spec §3). Rueckgabe (ids, next_id)."""
    n, m = len(old_poly), len(new_poly)
    if m == n:
        return list(old_ids), next_id
    if m == n + 1:
        for k in range(m):
            if all(_same(a, b) for a, b in zip(new_poly[:k] + new_poly[k + 1:], old_poly, strict=True)):
                e = (k - 1) % n  # geteilte alte Kante old[k-1] -> old[k]
                a = _seg_len(new_poly[k - 1], new_poly[k])
                b = _seg_len(new_poly[k], new_poly[(k + 1) % m])
                first, second = (old_ids[e], next_id) if a >= b else (next_id, old_ids[e])
                ids = []
                for j in range(m):
                    if j == (k - 1) % m:
                        ids.append(first)
                    elif j == k:
                        ids.append(second)
                    else:
                        ids.append(old_ids[(j if j < k else j - 1) % n])
                return ids, next_id + 1
    if m == n - 1:
        for k in range(n):
            if all(_same(a, b) for a, b in zip(old_poly[:k] + old_poly[k + 1:], new_poly, strict=True)):
                e1, e2 = (k - 1) % n, k % n
                l1 = _seg_len(old_poly[e1], old_poly[(e1 + 1) % n])
                l2 = _seg_len(old_poly[e2], old_poly[(e2 + 1) % n])
                ids = []
                for j in range(m):
                    if j == (k - 1) % m:
                        ids.append(old_ids[e1] if l1 >= l2 else old_ids[e2])
                    else:
                        ids.append(old_ids[j if j < k else j + 1])
                return ids, next_id
    return transfer_ids(old_poly, old_ids, new_poly, next_id)


def transfer_ids(old_poly, old_ids, new_poly, next_id):
    """Neue Kanten uebernehmen die Kennung der naechsten alten Kante (Winkel < 6°, Mitte < 3 mm)."""
    old = [(_angle(a, b), _mid((a, b)), eid) for (a, b), eid in zip(edges_of(old_poly), old_ids, strict=True)]
    used, ids = set(), []
    for a, b in edges_of(new_poly):
        ang, mid = _angle(a, b), _mid((a, b))
        best = None
        for oa, om, eid in old:
            if eid in used or _angle_diff(ang, oa) >= 6:
                continue
            d = math.hypot(mid[0] - om[0], mid[1] - om[1])
            if d < 3 and (best is None or d < best[0]):
                best = (d, eid)
        if best:
            used.add(best[1])
            ids.append(best[1])
        else:
            ids.append(next_id)
            next_id += 1
    return ids, next_id


def transfer_holes(old_holes, new_holes, next_id):
    """Bohrungen behalten ihre Kennung bei Mittelpunktabstand <= 2 mm."""
    used, out = set(), []
    for h in new_holes:
        best = None
        for o in old_holes:
            if o["id"] in used:
                continue
            d = math.hypot(h["c"][0] - o["c"][0], h["c"][1] - o["c"][1])
            if d <= 2 and (best is None or d < best[0]):
                best = (d, o["id"])
        if best:
            used.add(best[1])
            hid = best[1]
        else:
            hid = next_id
            next_id += 1
        out.append({"id": hid, "c": h["c"], "d": h["d"]})
    return out, next_id


def _dist_to_line(p, a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L


def _overlap(seg, a, b):
    """Anteil der Kandidatenlaenge, der in Laengsrichtung innerhalb der Polygonseite a-b liegt."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    t = sorted((p[0] - a[0]) * ux + (p[1] - a[1]) * uy for p in seg)
    sl = t[1] - t[0]
    return max(0.0, min(L, t[1]) - max(0.0, t[0])) / sl if sl > 1e-9 else 0.0


def _line(seg):
    (ax, ay), (bx, by) = seg
    L = math.hypot(bx - ax, by - ay)
    return (ax, ay), ((bx - ax) / L, (by - ay) / L)


def _intersect(l1, l2):
    (p1, d1), (p2, d2) = l1, l2
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < math.sin(math.radians(10)):
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


def snap_polygon(poly, segments, preferred=()):
    """KI-Polygon auf OpenCV-Kandidaten einrasten (Spec §2). Rueckgabe (polygon, hidden-Kennzeichen je Kante)."""
    pref = set(preferred)
    groups = ([s for s in segments if s["id"] in pref], [s for s in segments if s["id"] not in pref])
    lines, hidden = [], []
    for a, b in edges_of(poly):
        if _seg_len(a, b) < 1e-6:
            lines.append(None)
            hidden.append(True)
            continue
        ang, best = _angle(a, b), None
        for group in groups:
            for s in group:
                seg = (s["a"], s["b"])
                if _seg_len(*seg) < 1e-6 or _angle_diff(_angle(*seg), ang) >= 6:
                    continue
                dist = (_dist_to_line(seg[0], a, b) + _dist_to_line(seg[1], a, b)) / 2
                if dist >= 3 or _overlap(seg, a, b) < 0.3:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, seg)
            if best:
                break
        lines.append(_line(best[1] if best else (a, b)))
        hidden.append(best is None)
    out = []
    for i, v in enumerate(poly):
        q = _intersect(lines[i - 1], lines[i]) if lines[i - 1] and lines[i] else None
        if q is None or math.hypot(q[0] - v[0], q[1] - v[1]) > 8:
            q = v
        out.append([round(float(q[0]), 3), round(float(q[1]), 3)])
    return out, hidden


def assign(points, parts):
    """Teil fuer eine Messung: alle Punkte in oder an dem Teil, meiste Randpunkte, dann kleinste Flaeche."""
    best = None
    pts = [Point(p) for p in points]
    for pid, poly in parts:
        P = _valid(poly)
        if P.is_empty or P.area <= 0:
            continue
        zone = P.buffer(ON_EDGE_MM)
        if not all(zone.covers(q) for q in pts):
            continue
        near = sum(1 for q in pts if P.boundary.distance(q) <= ON_EDGE_MM)
        key = (-near, P.area)
        if best is None or key < best[0]:
            best = (key, pid)
    return best[1] if best else None


def scale_of(ratios):
    """ratios = [(mid, Messschieber / Fotowert)]. Rueckgabe (k, gueltige mids, ungueltige mids, Warnung)."""
    good = [(m, r) for m, r in ratios if SCALE_RANGE[0] <= r <= SCALE_RANGE[1]]
    bad = [m for m, r in ratios if not SCALE_RANGE[0] <= r <= SCALE_RANGE[1]]
    if not good:
        return 1.0, [], bad, None
    rs = [r for _, r in good]
    k = statistics.median(rs)
    warn = None
    if (max(rs) - min(rs)) / k > SPREAD_MAX:
        warn = "Referenzen widersprechen sich (" + ", ".join(f"{r:.3f}".replace(".", ",") for r in rs) + ")"
    return k, [m for m, _ in good], bad, warn


def nominal(value, unc, caliper=None):
    if caliper is not None:
        return round(caliper, 3)
    if value is None:
        return None
    n = round(value * 2) / 2
    return n if abs(value - n) <= max(unc or 0, 0.2) else None


def match_parts(old, new, threshold=0.5):
    """Greedy-Abgleich ueber IoU >= threshold. Rueckgabe {new_key: old_key}."""
    pairs = []
    for ok_, op in old:
        A = _valid(op)
        for nk, np_ in new:
            B = _valid(np_)
            union = A.union(B).area
            if union > 0:
                iou = A.intersection(B).area / union
                if iou >= threshold:
                    pairs.append((iou, ok_, nk))
    pairs.sort(key=lambda t: -t[0])
    out, used = {}, set()
    for _, ok_, nk in pairs:
        if ok_ in used or nk in out:
            continue
        out[nk] = ok_
        used.add(ok_)
    return out


def assign_holes(parts_list, holes):
    """Bohrungen dem kleinsten Teil zuordnen, dessen Polygon den Mittelpunkt enthaelt."""
    for p in parts_list:
        p["holes"] = []
    for hole in holes:
        c = Point(hole["c"])
        cands = [(_valid(p["polygon"]).area, i) for i, p in enumerate(parts_list) if _valid(p["polygon"]).contains(c)]
        if cands:
            parts_list[min(cands)[1]]["holes"].append({"c": hole["c"], "d": hole["d"]})
```

Hinweis zum vierten Fall in `test_kennungen_einfuegen_loeschen_verschieben`: Aus 4 werden 6 Ecken. Das ist kein einzelnes Einfügen, deshalb greift `transfer_ids`. Die obere und die linke Kante (3 und 4) liegen unverändert und behalten ihre Kennung.

- [ ] **Step 4: Tests grün**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/parts.py tests/test_parts.py
git commit -m "Teile: Geometrie, Kanten-Kennungen, Einrasten, Zuordnung und Maßstab"
```

---

### Task 5: Teile in der Datenbank, `refresh`, Teil-Endpunkte und Anbindung der Messungen

**Files:**
- Modify: `web/app/parts.py` (Datenbankschicht anhängen)
- Modify: `web/app/main.py` (`_default_unc`, `_project_public`, `_recompute` entfernen, `project_patch`, `photo_patch`, `photo_delete`, `MeasPatch`, `meas_create`, `meas_patch`, `meas_delete`, `meas_accept_all`, neue Teil-Endpunkte, `_csv`)
- Test: `tests/test_parts_api.py` (erweitern)

**Interfaces:**
- Consumes: alles aus Task 4, `jobs.SOURCE_LABEL` aus Task 1.
- Produces (in `app.parts`): `default_unc(photo, view) -> float`, `create_part(project_id, photo_id, label, role, polygon, *, hidden_flags=None, holes=(), source="user", note="") -> int`, `set_polygon(part, polygon, *, hidden_flags=None, holes=None, redetect=False)`, `delete_part(part)`, `delete_photo_parts(photo_id)`, `drop_key(part_id, key)`, `rename(part, label)`, `reset_scale(part_id)`, `refresh(project, fx, fy)`, `part_public(part) -> dict`, `public_list(project_id) -> list[dict]`, `replace_detected(project_id, photo_id, detected: list[dict])`.
- Produces (API): `POST /api/projects/{pid}/parts`, `PATCH /api/parts/{id}`, `DELETE /api/parts/{id}`, `GET /api/projects/{pid}` mit `parts`, `PATCH /api/measurements/{mid}` mit `part_id`/`ref`.
- Teil (öffentlich): `{"id", "seq", "id_label": "T1", "photo_id", "label", "role", "source", "scale", "polygon", "edge_ids", "hidden", "holes", "warn", "note", "rect": bool, "size": [L, B] | None, "n_edges", "refs": ["M3", …]}`.
- Messung (`data`, neu): `auto_key`, `auto_raw`, `warn`, `ref_warn`, `ref`, `part_fixed`, `raw`, `nominal`.

- [ ] **Step 1: Failing Tests** – an `tests/test_parts_api.py` anhängen:

```python
import pytest

from conftest import H, synthetic_photo

BOX = {"rect": [60, 80, 60, 40], "gray": 150}
RECT = [[60, 80], [123.6, 80], [123.6, 122.4], [60, 122.4]]   # Fotowerte 63,6 × 42,4 (Parallaxe)


@pytest.fixture()
def proj(user):
    pid = user.post("/api/projects", json={"name": "Quader"}, headers=H).json()["id"]
    r = user.post(f"/api/projects/{pid}/photos", files={"file": ("q.jpg", synthetic_photo("A4", objects=[BOX]), "image/jpeg")},
                  data={"view": "top"}, headers=H)
    assert r.status_code == 200, r.text
    return user, pid, r.json()["id"]


def _p(c, pid):
    return c.get(f"/api/projects/{pid}").json()


def _auto(p, part_id, key):
    return next(m for m in p["measurements"] if m["part_id"] == part_id and m["data"].get("auto_key") == key)


def _part(c, pid, phid, poly=RECT, label="Quader"):
    r = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "label": label, "polygon": poly}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_teil_auto_masse_und_massstab(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid)
    assert part["id_label"] == "T1" and part["rect"] and part["size"] == pytest.approx([63.6, 42.4])
    p = _p(c, pid)
    L = _auto(p, part["id"], "L")
    assert L["label"] == "Quader Länge" and L["source"] == "auto"
    assert c.patch(f"/api/measurements/{L['id']}", json={"caliper": 60.0}, headers=H).status_code == 200
    p = _p(c, pid)
    assert _auto(p, part["id"], "B")["value"] == pytest.approx(40.0, abs=0.01)
    assert p["parts"][0]["scale"] == pytest.approx(0.9434, abs=1e-3) and p["parts"][0]["refs"] == [L["id_label"]]
    m = c.post(f"/api/projects/{pid}/measurements",
               json={"photo_id": phid, "kind": "length", "points": [[60, 100], [123.6, 100]]}, headers=H).json()
    assert m["part_id"] == part["id"] and m["value"] == pytest.approx(60.0, abs=0.01) and m["data"]["raw"] == pytest.approx(63.6)
    c.patch(f"/api/measurements/{_auto(p, part['id'], 'B')['id']}", json={"caliper": 40.6}, headers=H)  # 1,5 % Streuung
    assert "widersprechen" in _p(c, pid)["parts"][0]["warn"]
    c.patch(f"/api/parts/{part['id']}", json={"reset_scale": True}, headers=H)
    p = _p(c, pid)
    assert p["parts"][0]["scale"] == 1.0 and _auto(p, part["id"], "B")["value"] == pytest.approx(42.4)


def test_unplausible_referenz_polygon_bearbeiten_dropped(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid, label="Q")
    B = _auto(_p(c, pid), part["id"], "B")
    c.patch(f"/api/measurements/{B['id']}", json={"caliper": 59.36}, headers=H)         # 59,36 / 42,4 = 1,40
    p = _p(c, pid)
    assert p["parts"][0]["scale"] == 1.0 and "Abweichung zu groß" in _auto(p, part["id"], "B")["data"]["ref_warn"]
    r = c.patch(f"/api/parts/{part['id']}", json={"polygon": [RECT[0], [90, 80], *RECT[1:]]}, headers=H)
    assert r.status_code == 200, r.text
    p = _p(c, pid)
    assert sorted(m["data"]["auto_key"] for m in p["measurements"] if m["source"] == "auto") == ["E1", "E2", "E3", "E4", "E5"]
    kept = next(m for m in p["measurements"] if m["id"] == B["id"])
    assert kept["source"] == "user" and kept["caliper"] == 59.36
    e2 = next(m for m in p["measurements"] if m["data"].get("auto_key") == "E2")
    assert c.delete(f"/api/measurements/{e2['id']}", headers=H).status_code == 200
    e1 = next(m for m in p["measurements"] if m["data"].get("auto_key") == "E1")
    r = c.patch(f"/api/measurements/{e1['id']}", json={"points": [[60, 81], [90, 81]]}, headers=H).json()
    assert r["source"] == "user"
    e3 = next(m for m in p["measurements"] if m["data"].get("auto_key") == "E3")
    assert c.patch(f"/api/measurements/{e3['id']}", json={"kind": "height"}, headers=H).json()["source"] == "user"
    c.patch(f"/api/parts/{part['id']}", json={"label": "Quader"}, headers=H)
    p = _p(c, pid)
    keys = [m["data"].get("auto_key") for m in p["measurements"]]
    assert "E1" not in keys and "E2" not in keys and "E3" not in keys
    assert all(m["label"].startswith("Quader ") for m in p["measurements"] if m["source"] == "auto")
    bow = [[60, 80], [123.6, 122.4], [123.6, 80], [60, 122.4]]
    assert c.patch(f"/api/parts/{part['id']}", json={"polygon": bow}, headers=H).status_code == 200
    assert c.get(f"/api/projects/{pid}").status_code == 200


def test_zuordnung_von_hand(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid)
    h = c.post(f"/api/projects/{pid}/measurements", json={"kind": "height", "value": 30.0, "label": "Höhe"}, headers=H).json()
    assert h["part_id"] is None
    assert c.patch(f"/api/measurements/{h['id']}", json={"part_id": part["id"]}, headers=H).json()["part_id"] == part["id"]
    m = c.post(f"/api/projects/{pid}/measurements",
               json={"photo_id": phid, "kind": "length", "points": [[60, 100], [123.6, 100]]}, headers=H).json()
    assert c.patch(f"/api/measurements/{m['id']}", json={"part_id": None}, headers=H).json()["part_id"] is None
    assert _p(c, pid)["measurements"][-1]["part_id"] is None                       # bleibt "keins"
    assert c.patch(f"/api/measurements/{m['id']}", json={"part_id": -1}, headers=H).json()["part_id"] == part["id"]
    assert c.patch(f"/api/measurements/{m['id']}", json={"part_id": 999999}, headers=H).status_code == 400
    L = _auto(_p(c, pid), part["id"], "L")
    assert c.patch(f"/api/measurements/{L['id']}", json={"part_id": None}, headers=H).status_code == 400


def test_formatwechsel_und_foto_loeschen_behalten_referenz(proj):
    c, pid, phid = proj
    part = _part(c, pid, phid)
    L = _auto(_p(c, pid), part["id"], "L")
    c.patch(f"/api/measurements/{L['id']}", json={"caliper": 60.0}, headers=H)
    c.patch(f"/api/photos/{phid}", json={"format": "A3"}, headers=H)
    p = _p(c, pid)
    assert p["parts"] == [] and [(m["source"], m["caliper"]) for m in p["measurements"]] == [("user", 60.0)]
    c.patch(f"/api/photos/{phid}", json={"format": "A4"}, headers=H)
    _part(c, pid, phid)
    c.delete(f"/api/photos/{phid}", headers=H)
    p = _p(c, pid)
    assert p["parts"] == [] and [m["caliper"] for m in p["measurements"]] == [60.0]


def test_teil_validierung(proj, user):
    c, pid, phid = proj
    bad = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": [[0, 0], [1, 1]]}, headers=H)
    assert bad.status_code in (400, 422)                                              # Pydantic: min_length=3
    assert c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": [[0, 0], [1e6, 0], [0, 5]]},
                  headers=H).status_code == 400
    other = user.post("/api/projects", json={"name": "fremd"}, headers=H).json()["id"]
    assert c.post(f"/api/projects/{other}/parts", json={"photo_id": phid, "polygon": RECT}, headers=H).status_code == 400
    for _ in range(12):                                                               # MAX_PARTS_PER_PHOTO
        _part(c, pid, phid)
    assert c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": RECT}, headers=H).status_code == 400


def test_fremder_nutzer_kein_zugriff(proj, app, admin):
    from fastapi.testclient import TestClient
    c, pid, phid = proj
    part = _part(c, pid, phid)
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremd{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.patch(f"/api/parts/{part['id']}", json={"label": "x"}, headers=H).status_code == 404
    assert f.delete(f"/api/parts/{part['id']}", headers=H).status_code == 404
    assert f.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "polygon": RECT}, headers=H).status_code == 404
    own = f.post("/api/projects", json={"name": "f"}, headers=H).json()["id"]
    m = f.post(f"/api/projects/{own}/measurements", json={"kind": "height", "value": 1.0}, headers=H).json()
    assert f.patch(f"/api/measurements/{m['id']}", json={"part_id": part["id"]}, headers=H).status_code == 400


def test_parallel_keine_doppelten_auto_masse(proj):
    import threading
    from app import db, main, parts
    c, pid, phid = proj
    part = _part(c, pid, phid)
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    five = [RECT[0], [90, 80], *RECT[1:]]
    errs = []

    def job(i):
        try:
            if i == 0:
                assert c.patch(f"/api/parts/{part['id']}", json={"polygon": five}, headers=H).status_code == 200
            else:
                main._refresh(project)
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=job, args=(i,)) for i in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs
    parts.refresh(project, 1.0, 1.0)
    keys = [m["data"].get("auto_key") for m in _p(c, pid)["measurements"] if m["source"] == "auto"]
    assert len(keys) == len(set(keys)) == 5
```

Der Migrationstest aus Task 2 bleibt oben in der Datei. Die Importe `import pytest` und `from conftest import H, synthetic_photo` an den Dateianfang zu `import sqlite3` stellen, damit ruff nicht über E402 klagt. (E402 ist ohnehin abgeschaltet, sauber ist es trotzdem.)

- [ ] **Step 2: Tests scheitern**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_parts_api.py`
Expected: FAIL (404 auf `/api/projects/{pid}/parts`).

- [ ] **Step 3: Datenbankschicht in `web/app/parts.py` anhängen**

Die Importzeile `from . import geom` wird zu:

```python
from . import db, geom
```

Am Dateiende anhängen:

```python
# ------------------------------------------------------------------ Datenbank

def default_unc(photo, view):
    """Standard-Unsicherheit einer Fotomessung (vorher main._default_unc)."""
    if not photo:
        return 0.5
    a = db.jload(photo["analysis"], {}) or {}
    if view == "gauge" and a.get("gauge"):
        return round((a["gauge"].get("rms_mm") or 0.3) * 2 + 0.3, 2)
    return round((photo["max_err"] or 0.3) + 0.2, 2)


def _data(row):
    return db.jload(row["data"], {}) or {}


def _next_seq(table, project_id):
    return db.q1(f"SELECT COALESCE(MAX(seq),0)+1 s FROM {table} WHERE project_id=?", (project_id,))["s"]


def create_part(project_id, photo_id, label, role, polygon, *, hidden_flags=None, holes=(), source="user", note=""):
    poly, flags = _ccw(polygon, hidden_flags)
    ids = list(range(1, len(poly) + 1))
    hl = [{"id": i + 1, "c": h["c"], "d": h["d"]} for i, h in enumerate(holes)]
    data = {"polygon": poly, "edge_ids": ids, "next_edge_id": len(ids) + 1,
            "hidden": [e for e, f in zip(ids, flags or [False] * len(ids), strict=True) if f],
            "holes": hl, "next_hole_id": len(hl) + 1, "dropped": [], "warn": None, "refs": [], "note": note}
    return db.ex("""INSERT INTO parts(project_id,photo_id,seq,label,role,data,source,scale,created_at)
                    VALUES (?,?,?,?,?,?,?,1.0,?)""",
                 (project_id, photo_id, _next_seq("parts", project_id), (label or "Teil").strip()[:80] or "Teil",
                  role if role in ROLE_TEXT else "body", db.jdump(data), source, db.now()))


def set_polygon(part, polygon, *, hidden_flags=None, holes=None, redetect=False):
    """Neues Polygon fuer ein Teil. redetect=True: aus einer neuen Erkennung (Kennungen uebertragen)."""
    d = _data(part)
    if redetect:
        poly, flags = _ccw(polygon, hidden_flags)
        ids, nxt = transfer_ids(d["polygon"], d["edge_ids"], poly, d["next_edge_id"])
        d["hidden"] = [e for e, f in zip(ids, flags or [False] * len(ids), strict=True) if f]
    else:
        poly = [[round(float(x), 3), round(float(y), 3)] for x, y in polygon]
        ids, nxt = update_edge_ids(d["polygon"], d["edge_ids"], poly, d["next_edge_id"])
        old = {eid: e for e, eid in zip(edges_of(d["polygon"]), d["edge_ids"], strict=True)}
        moved = {eid for e, eid in zip(edges_of(poly), ids, strict=True)
                 if eid in old and not (_same(e[0], old[eid][0]) and _same(e[1], old[eid][1]))}
        d["hidden"] = [e for e in d.get("hidden") or [] if e in ids and e not in moved]  # vom Nutzer gesetzt = sichtbar
    d.update(polygon=poly, edge_ids=ids, next_edge_id=nxt)
    if holes is not None:
        d["holes"], d["next_hole_id"] = transfer_holes(d.get("holes") or [], holes, d.get("next_hole_id", 1))
    db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), part["id"]))


def _auto_to_user(m):
    d = _data(m)
    d.pop("auto_key", None)
    d.pop("auto_raw", None)
    d.pop("part_fixed", None)
    db.ex("UPDATE measurements SET source='user', data=? WHERE id=?", (db.jdump(d), m["id"]))


def delete_part(part):
    for m in db.q("SELECT * FROM measurements WHERE part_id=?", (part["id"],)):
        if m["source"] == "auto" and m["caliper"] is None:
            db.ex("DELETE FROM measurements WHERE id=?", (m["id"],))
            continue
        if m["source"] == "auto":
            _auto_to_user(m)
        d = _data(db.q1("SELECT data FROM measurements WHERE id=?", (m["id"],)))
        d.pop("part_fixed", None)
        db.ex("UPDATE measurements SET part_id=NULL, data=? WHERE id=?", (db.jdump(d), m["id"]))
    db.ex("DELETE FROM parts WHERE id=?", (part["id"],))


def delete_photo_parts(photo_id):
    for part in db.q("SELECT * FROM parts WHERE photo_id=?", (photo_id,)):
        delete_part(part)


def drop_key(part_id, key):
    part = db.q1("SELECT * FROM parts WHERE id=?", (part_id,))
    if not part or not key:
        return
    d = _data(part)
    if key not in d.setdefault("dropped", []):
        d["dropped"].append(key)
        db.ex("UPDATE parts SET data=? WHERE id=?", (db.jdump(d), part_id))


def rename(part, label):
    label = (label or "").strip()[:80] or "Teil"
    old = part["label"]
    db.ex("UPDATE parts SET label=? WHERE id=?", (label, part["id"]))
    for m in db.q("SELECT id, label FROM measurements WHERE part_id=? AND source='auto'", (part["id"],)):
        if m["label"].startswith(old + " "):
            db.ex("UPDATE measurements SET label=? WHERE id=?", ((label + m["label"][len(old):])[:80], m["id"]))


def reset_scale(part_id):
    for m in db.q("SELECT id, data FROM measurements WHERE part_id=? AND caliper IS NOT NULL", (part_id,)):
        d = _data(m)
        d["ref"] = False
        db.ex("UPDATE measurements SET data=? WHERE id=?", (db.jdump(d), m["id"]))


def _sync_auto(part, photo, fx, fy):
    """Auto-Masse eines Teils an sein Polygon anpassen (Spec §3)."""
    d = _data(part)
    want = {x["key"]: x for x in auto_dims(d, fx, fy) if x["key"] not in (d.get("dropped") or [])}
    have = {}
    for m in db.q("SELECT * FROM measurements WHERE part_id=? AND source='auto' ORDER BY id", (part["id"],)):
        k = _data(m).get("auto_key")
        if k in have:  # Doppel (z. B. aus einem frueheren Wettlauf) bereinigen
            if m["caliper"] is None:
                db.ex("DELETE FROM measurements WHERE id=?", (m["id"],))
            else:
                _auto_to_user(m)
            continue
        have[k] = m
    for key, x in want.items():
        m = have.get(key)
        if m:
            md = _data(m)
            md.update(points=x["points"], auto_raw=x["raw"], warn=x["warn"])
            db.ex("UPDATE measurements SET kind=?, data=? WHERE id=?", (x["kind"], db.jdump(md), m["id"]))
        else:
            md = {"view": "top", "points": x["points"], "auto_key": key, "auto_raw": x["raw"], "warn": x["warn"], "note": None}
            db.ex("""INSERT INTO measurements(project_id,photo_id,part_id,seq,label,kind,value,unit,unc,data,critical,source,
                     accepted,created_at) VALUES (?,?,?,?,?,?,?,'mm',?,?,0,'auto',1,?)""",
                  (part["project_id"], part["photo_id"], part["id"], _next_seq("measurements", part["project_id"]),
                   f"{part['label']} {x['name']}"[:80], x["kind"], x["raw"], default_unc(photo, "top"), db.jdump(md), db.now()))
    for key, m in have.items():
        if key in want:
            continue
        if m["caliper"] is None:
            db.ex("DELETE FROM measurements WHERE id=?", (m["id"],))
        else:
            _auto_to_user(m)


def _computed(m, d):
    """Wird der Wert aus Punkten bzw. dem Teil-Polygon berechnet (und damit auch skaliert)?"""
    return m["source"] == "auto" or (m["source"] != "manual" and not d.get("ai_value") and bool(d.get("points")))


def refresh(project, fx, fy):
    """Zuordnung, Auto-Masse, Massstab je Teil und alle berechneten Werte eines Projekts (Spec §3)."""
    pid = project["id"]
    photos = {p["id"]: p for p in db.q("SELECT * FROM photos WHERE project_id=?", (pid,))}
    parts = db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (pid,))
    for part in parts:
        _sync_auto(part, photos.get(part["photo_id"]), fx, fy)
    by_photo = {}
    for part in parts:
        by_photo.setdefault(part["photo_id"], []).append((part["id"], _data(part)["polygon"]))
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1", (pid,))
    datas = {m["id"]: _data(m) for m in rows}
    for m in rows:  # 1. Zuordnung
        d = datas[m["id"]]
        if m["source"] == "auto" or d.get("part_fixed"):
            continue
        new = None
        if m["source"] != "manual" and d.get("view", "top") == "top" and m["kind"] != "height" and d.get("points") \
                and m["photo_id"] in by_photo:
            new = assign(d["points"], by_photo[m["photo_id"]])
        if new != m["part_id"]:
            db.ex("UPDATE measurements SET part_id=? WHERE id=?", (new, m["id"]))
            m["part_id"] = new
    raw = {}
    for m in rows:  # 2. Fotowerte ohne Teil-Massstab
        d = datas[m["id"]]
        if m["source"] == "auto":
            raw[m["id"]] = d.get("auto_raw")
        elif _computed(m, d):
            raw[m["id"]] = geom.compute(m["kind"], d["points"], fx, fy)
    kmap, ref_warn = {}, {}
    for part in parts:  # 3. Massstab je Teil
        refs = [(m["id"], m["caliper"] / raw[m["id"]]) for m in rows
                if m["part_id"] == part["id"] and m["caliper"] is not None and m["kind"] in SCALED_KINDS
                and datas[m["id"]].get("ref") is not False and datas[m["id"]].get("view", "top") == "top" and raw.get(m["id"])]
        k, good, bad, warn = scale_of(refs)
        kmap[part["id"]] = k
        for mid in bad:
            ref_warn[mid] = "Abweichung zu groß – falsches Maß oder falsches Teil?"
        pd = _data(db.q1("SELECT data FROM parts WHERE id=?", (part["id"],)))
        pd.update(warn=warn, refs=good)
        db.ex("UPDATE parts SET scale=?, data=? WHERE id=?", (k, db.jdump(pd), part["id"]))
    for m in rows:  # 4. Werte, Hinweise, Nennmass
        d = dict(datas[m["id"]])
        r = raw.get(m["id"])
        value = m["value"]
        if _computed(m, d) and r is not None:
            k = kmap.get(m["part_id"], 1.0) if m["kind"] in SCALED_KINDS and d.get("view", "top") == "top" else 1.0
            value = round(r * k, 3)
            d["raw"] = round(r, 3)
        else:
            d.pop("raw", None)
        d["ref_warn"] = ref_warn.get(m["id"])
        d["nominal"] = nominal(value, m["unc"], m["caliper"]) if m["kind"] in MM_KINDS else None
        if value != m["value"] or d != datas[m["id"]]:
            db.ex("UPDATE measurements SET value=?, data=? WHERE id=?", (value, db.jdump(d), m["id"]))


def part_public(part):
    d = _data(part)
    poly = d["polygon"]
    ms = db.q("SELECT id, seq, value, data FROM measurements WHERE part_id=?", (part["id"],))
    by_key = {_data(x).get("auto_key"): x["value"] for x in ms}
    seq = {x["id"]: x["seq"] for x in ms}
    rect = is_rect(poly)
    return {"id": part["id"], "seq": part["seq"], "id_label": f"T{part['seq']}", "photo_id": part["photo_id"],
            "label": part["label"], "role": part["role"], "source": part["source"], "scale": part["scale"],
            "polygon": poly, "edge_ids": d["edge_ids"], "hidden": d.get("hidden") or [], "holes": d.get("holes") or [],
            "warn": d.get("warn"), "note": d.get("note") or "", "rect": rect,
            "size": [by_key["L"], by_key["B"]] if rect and "L" in by_key and "B" in by_key else None,
            "n_edges": len(poly), "refs": [f"M{seq[i]}" for i in d.get("refs") or [] if i in seq]}


def public_list(project_id):
    return [part_public(p) for p in db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (project_id,))]


def replace_detected(project_id, photo_id, detected):
    """Ergebnis einer Erkennung uebernehmen: Abgleich ueber IoU (Spec §2), sonst neu bzw. loeschen."""
    old = db.q("SELECT * FROM parts WHERE photo_id=? AND source!='user' ORDER BY seq", (photo_id,))  # Handteile bleiben
    m = match_parts([(o["id"], _data(o)["polygon"]) for o in old], [(i, x["polygon"]) for i, x in enumerate(detected)])
    kept = set(m.values())
    for o in old:
        if o["id"] not in kept:
            delete_part(o)
    by_id = {o["id"]: o for o in old}
    for i, x in enumerate(detected):
        if i in m:
            set_polygon(by_id[m[i]], x["polygon"], hidden_flags=x.get("hidden"), holes=x.get("holes") or [], redetect=True)
        else:
            create_part(project_id, photo_id, x["label"], x["role"], x["polygon"], hidden_flags=x.get("hidden"),
                        holes=x.get("holes") or [], source=x.get("source", "auto"), note=x.get("note", ""))
```

- [ ] **Step 4: `main.py` anbinden**

Importzeile `from . import …` um `parts` ergänzen (alphabetisch einordnen).

`_default_unc` (Zeile 229) löschen; die einzige Aufrufstelle (`meas_create`, Zeile 1006) ruft `parts.default_unc(photo, body.view)` auf.

`_project_public`, im `if detail:`-Block ergänzen:

```python
        out["parts"] = parts.public_list(p["id"])
```

`_recompute` (Zeilen 783–790) löschen. In `project_patch` `_recompute(p)` → `parts.refresh(p, *_factors(p))`.

Hilfsfunktionen unter `_own_meas` einfügen:

```python
def _own_part(part_id: int, user: dict) -> tuple[dict, dict]:
    t = db.q1("SELECT * FROM parts WHERE id=?", (part_id,))
    if not t:
        raise HTTPException(404, "Teil nicht gefunden")
    return t, _own_project(t["project_id"], user)


def _refresh(p: dict):
    with db.atomic():
        parts.refresh(p, *_factors(p))
```

**Transaktionen:** In `part_create`, `part_patch`, `part_delete`, `photo_patch`, `photo_delete`, `meas_create`, `meas_patch`, `meas_delete` und `meas_accept_all` stehen die schreibenden Schritte und `_refresh(p)` zusammen in einem `with db.atomic():`. Weil `atomic` verschachtelbar ist, darf `_refresh` darin selbst `atomic` öffnen. Die Lesezugriffe zur Eigentümerprüfung (`_own_*`) bleiben davor. Die Codeblöcke unten zeigen das.

`photo_patch` ersetzen (Teile erst löschen, wenn die neue Auswertung geklappt hat):

```python
@app.patch("/api/photos/{phid}")
def photo_patch(phid: int, body: PhotoPatch, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u)
    if body.view in VIEWS:
        db.ex("UPDATE photos SET view=? WHERE id=?", (body.view, phid))
    if body.format is not None and body.format != ph["format"]:
        img = vision.load_image((_photo_dir(phid) / "orig.jpg").read_bytes())
        a = _analyze_store(phid, img, body.format if body.format in matgen.FORMATS else None)
        with db.atomic():
            db.ex("UPDATE photos SET format=?, status=?, max_err=?, analysis=? WHERE id=?",
                  (a.get("format"), a["status"], a.get("max_err_mm"), db.jdump(a), phid))
            parts.delete_photo_parts(phid)
            _refresh(p)
        for n in ("edges.json", "edges_ki.jpg"):
            (_photo_dir(phid) / n).unlink(missing_ok=True)
    return _photo_public(db.q1("SELECT * FROM photos WHERE id=?", (phid,)))
```

`photo_delete` ersetzen:

```python
@app.delete("/api/photos/{phid}")
def photo_delete(phid: int, u: dict = Depends(auth.require_user)):
    _, p = _own_photo(phid, u)
    with db.atomic():
        parts.delete_photo_parts(phid)
        db.ex("DELETE FROM photos WHERE id=?", (phid,))
        _refresh(p)
    shutil.rmtree(_photo_dir(phid), ignore_errors=True)
    return {"ok": True}
```

`MeasPatch` um zwei Felder ergänzen:

```python
    part_id: int | None = None
    ref: bool | None = None
```

`meas_create`: Das `mid = db.ex("""INSERT INTO measurements…""", …)` und ein anschließendes `_refresh(p)` kommen zusammen in `with db.atomic():`, danach unverändert `return _meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,)))`.

`meas_patch`: direkt vor `if body.unc is not None:` einfügen:

```python
    drop = None
    if m["source"] == "auto" and (body.points is not None or body.value is not None or "kind" in sets):
        key = d.pop("auto_key", None)
        d.pop("auto_raw", None)
        sets["source"] = "manual" if body.value is not None and body.points is None else "user"
        drop = (m["part_id"], key) if m["part_id"] else None
    if "part_id" in body.model_fields_set:
        if m["source"] == "auto" and "source" not in sets:
            raise HTTPException(400, "Automatische Maße gehören fest zu ihrem Teil.")
        if body.part_id == -1:
            d.pop("part_fixed", None)
        else:
            if body.part_id is not None and not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?",
                                                      (body.part_id, p["id"])):
                raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
            sets["part_id"] = body.part_id
            d["part_fixed"] = True
    if body.ref is not None:
        d["ref"] = bool(body.ref)
```

Die bestehende Zeile `if m["source"] == "manual": sets["source"] = "user"` im Punkte-Zweig bleibt. Bei Auto-Maßen setzt der neue Block `sets["source"]` danach ohnehin. Im bestehenden `if body.clear_caliper:`-Zweig und im `elif body.caliper is not None:`-Zweig jeweils zusätzlich `d.pop("ref", None)`: Ein neuer oder geänderter Messschieber-Wert ist wieder Referenz, auch nach „Maßstab zurücksetzen“. Am Ende:

```python
    with db.atomic():
        if drop:
            parts.drop_key(*drop)  # erst hier: ein abgelehnter PATCH (400 oben) hinterlaesst nichts
        db.ex(f"UPDATE measurements SET {cols} WHERE id=?", (*sets.values(), mid))
        _refresh(p)
    return _meas_public(db.q1("SELECT * FROM measurements WHERE id=?", (mid,)))
```

`meas_delete` ersetzen:

```python
@app.delete("/api/measurements/{mid}")
def meas_delete(mid: int, u: dict = Depends(auth.require_user)):
    m, p = _own_meas(mid, u)
    with db.atomic():
        if m["source"] == "auto" and m["part_id"]:
            parts.drop_key(m["part_id"], (db.jload(m["data"], {}) or {}).get("auto_key"))
        db.ex("DELETE FROM measurements WHERE id=?", (mid,))
        _refresh(p)
    return {"ok": True}
```

`meas_accept_all`: `p = _own_project(pid, u)` statt `_own_project(pid, u)`. Das `UPDATE` und `_refresh(p)` stehen zusammen in `with db.atomic():`.

Neue Endpunkte nach `meas_discard`:

```python
class PartIn(BaseModel):
    photo_id: int
    label: str = Field(default="", max_length=80)
    role: str = "body"
    polygon: list[list[float]] = Field(min_length=3, max_length=64)


class PartPatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    role: str | None = None
    polygon: list[list[float]] | None = Field(default=None, min_length=3, max_length=64)
    reset_scale: bool = False


MAX_PARTS_PER_PHOTO = 12


def _polygon(pts: list, photo: dict) -> list:
    import math
    a = db.jload(photo["analysis"], {}) or {}
    r = a.get("rect")
    if not r:
        raise HTTPException(400, "Für dieses Foto gibt es keine entzerrte Draufsicht.")
    if not 3 <= len(pts) <= 64:
        raise HTTPException(400, "Ein Teil braucht 3 bis 64 Eckpunkte.")
    for q in pts:
        if len(q) != 2 or not all(math.isfinite(v) for v in q) \
                or not (-10 <= q[0] <= r["w_mm"] + 10 and -10 <= q[1] <= r["h_mm"] + 10):
            raise HTTPException(400, "Eckpunkt außerhalb der Messfläche")
    return [[float(q[0]), float(q[1])] for q in pts]


@app.post("/api/projects/{pid}/parts")
def part_create(pid: int, body: PartIn, u: dict = Depends(auth.require_user)):
    p = _own_project(pid, u)
    ph, pp = _own_photo(body.photo_id, u)
    if pp["id"] != pid:
        raise HTTPException(400, "Foto gehört zu einem anderen Projekt")
    poly = _polygon(body.polygon, ph)
    with db.atomic():
        if db.q1("SELECT COUNT(*) n FROM parts WHERE photo_id=?", (ph["id"],))["n"] >= MAX_PARTS_PER_PHOTO:
            raise HTTPException(400, f"Höchstens {MAX_PARTS_PER_PHOTO} Teile je Foto.")
        tid = parts.create_part(pid, ph["id"], body.label, body.role, poly)
        _refresh(p)
    return parts.part_public(db.q1("SELECT * FROM parts WHERE id=?", (tid,)))


@app.patch("/api/parts/{part_id}")
def part_patch(part_id: int, body: PartPatch, u: dict = Depends(auth.require_user)):
    t, p = _own_part(part_id, u)
    poly = None
    if body.polygon is not None:
        poly = _polygon(body.polygon, db.q1("SELECT * FROM photos WHERE id=?", (t["photo_id"],)))
    with db.atomic():
        t = db.q1("SELECT * FROM parts WHERE id=?", (part_id,))  # frisch lesen: kein Wettlauf mit parallelem PATCH
        if not t:
            raise HTTPException(404, "Teil nicht gefunden")
        if poly is not None:
            parts.set_polygon(t, poly)
        if body.label is not None:
            parts.rename(t, body.label)
        if body.role in parts.ROLE_TEXT:
            db.ex("UPDATE parts SET role=? WHERE id=?", (body.role, part_id))
        if body.reset_scale:
            parts.reset_scale(part_id)
        _refresh(p)
    return parts.part_public(db.q1("SELECT * FROM parts WHERE id=?", (part_id,)))


@app.delete("/api/parts/{part_id}")
def part_delete(part_id: int, u: dict = Depends(auth.require_user)):
    t, p = _own_part(part_id, u)
    with db.atomic():
        parts.delete_part(t)
        _refresh(p)
    return {"ok": True}
```

Achtung bei `part_patch`: `parts.rename` braucht das *alte* Label aus `t`. `set_polygon` ändert nur `data`, deshalb ist `t["label"]` noch aktuell.

`_csv`: Kopfzeile um `;Teil;Nennmaß` erweitern (Ende). Vor der Schleife einfügen:

```python
    seq = {t["id"]: t["seq"] for t in db.q("SELECT id, seq FROM parts WHERE project_id=?", (pid,))}
```

und `cells` am Ende um `f"T{seq[m['part_id']]}" if m["part_id"] in seq else "", n(d.get("nominal"))` ergänzen.

- [ ] **Step 5: Tests grün**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check .`
Expected: PASS. `test_measurements_and_factors` deckt ab, dass sich nach dem Wegfall von `_recompute` beim Kontrollmaß nichts ändert.

- [ ] **Step 6: Commit**

```bash
git add web/app/parts.py web/app/main.py tests/test_parts_api.py
git commit -m "Teile speichern, Auto-Maße und Maßstab je Teil, Teil-Endpunkte"
```

---

### Task 6: KI-Teile-Zuordnung und Erkennungs-Endpunkt

**Files:**
- Modify: `web/app/ai.py` (`import math`, `PARTS_SYSTEM`, `parse_parts`, `_fake`)
- Modify: `web/app/parts.py` (`candidate_text`, `ai_parts`, `outline_parts`)
- Modify: `web/app/main.py` (`_ai_uses_today`, `meas_suggest`, `POST /api/photos/{phid}/edges`, `GET /api/photos/{phid}/edges.json`)
- Create: `tests/test_edges_api.py`

**Interfaces:**
- Consumes: `edges.detect`, `parts.snap_polygon`, `parts.assign_holes`, `parts.replace_detected`, `parts.refresh`, `parts.public_list`.
- Consumes: `edges.draw_candidates` (Task 3).
- Produces: `ai.PARTS_SYSTEM: str`, `ai.parse_parts(text) -> list[{"label", "role", "polygon", "edges", "note"}]`, `ai._json_array(text, what) -> list` (gemeinsam mit `parse_suggestions`); `parts.ai_parts(photo_dir: Path, res: dict) -> list[dict]`, `parts.outline_parts(res) -> list[dict]`; `main._detect_lock: threading.Semaphore`; `POST /api/photos/{phid}/edges` → `{"parts": [...], "segments": [...], "notice": str}` (409 bei Fotoänderung während der Erkennung, 422 ohne Objekt, 429 wenn belegt).

- [ ] **Step 1: Failing Tests** – `tests/test_edges_api.py`:

```python
"""Kantenerkennung ueber die API (Spec 2026-10-14-kanten-und-teile §2, A3/A4)."""
import json

import pytest

from conftest import H, synthetic_photo

BOX = {"rect": [60, 80, 60, 40], "gray": 150}
PLATE = {"rect": [50, 105, 80, 20], "gray": 90}
HOLE = {"circle": [90, 115, 5], "gray": 235}
KI_ZWEI = json.dumps([
    {"label": "Quader", "role": "body", "polygon": [[60.5, 80.5], [119.5, 80.5], [119.5, 119.8], [60.5, 119.8]], "edges": []},
    {"label": "Platte", "role": "mounted", "polygon": [[50.5, 105.5], [129.5, 105.5], [129.5, 124.5], [50.5, 124.5]],
     "edges": []}])


def _upload(c, objects):
    pid = c.post("/api/projects", json={"name": "Kanten"}, headers=H).json()["id"]
    r = c.post(f"/api/projects/{pid}/photos", files={"file": ("k.jpg", synthetic_photo("A4", objects=objects), "image/jpeg")},
               data={"view": "top"}, headers=H)
    assert r.status_code == 200, r.text
    return pid, r.json()["id"]


@pytest.fixture()
def two(user):
    pid, phid = _upload(user, [BOX, PLATE, HOLE])
    return user, pid, phid


def _ki(monkeypatch, text):
    from app import ai
    monkeypatch.setattr(ai, "call", lambda system, messages, **kw: (text, {}))


def test_erkennung_testmodus(two):
    c, pid, phid = two
    r = c.post(f"/api/photos/{phid}/edges", json={}, headers=H)
    assert r.status_code == 200, r.text
    res = r.json()
    assert [p["label"] for p in res["parts"]] == ["Quader"] and res["notice"] == ""
    assert any(s["kind"] == "inner" for s in res["segments"])
    assert c.get(f"/api/photos/{phid}/edges.json").json()["segments"] == res["segments"]


def test_zwei_teile(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    q, pl = res["parts"]
    assert (q["label"], pl["label"], pl["role"]) == ("Quader", "Platte", "mounted")
    assert q["rect"] and q["size"] == pytest.approx([60, 40], abs=0.6) and len(q["hidden"]) == 1
    assert pl["rect"] and pl["size"] == pytest.approx([80, 20], abs=0.6) and len(pl["holes"]) == 1
    p = c.get(f"/api/projects/{pid}").json()
    assert {m["part_id"] for m in p["measurements"] if m["source"] == "auto"} == {q["id"], pl["id"]}


def test_erneute_erkennung_ohne_ki_laesst_teile(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    first = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()["parts"]
    _ki(monkeypatch, "kein json")
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert [p["id"] for p in res["parts"]] == [p["id"] for p in first] and "unverändert" in res["notice"]
    res = c.post(f"/api/photos/{phid}/edges", json={"use_ai": False}, headers=H).json()
    assert [p["id"] for p in res["parts"]] == [p["id"] for p in first]


def test_ohne_ki_und_handteil_bleibt(two):
    c, pid, phid = two
    hand = c.post(f"/api/projects/{pid}/parts", json={"photo_id": phid, "label": "Hand",
                                                      "polygon": [[5, 150], [30, 150], [30, 170]]}, headers=H).json()
    res = c.post(f"/api/photos/{phid}/edges", json={"use_ai": False}, headers=H).json()
    assert sorted(p["label"] for p in res["parts"]) == ["Hand", "Teil"] and res["notice"] == ""
    assert hand["id"] in [p["id"] for p in res["parts"]]


def test_erkennung_belegt_429(two):
    c, pid, phid = two
    from app import main
    assert main._detect_lock.acquire(blocking=False)
    try:
        r = c.post(f"/api/photos/{phid}/edges", json={}, headers=H)
        assert r.status_code == 429 and "belegt" in r.json()["detail"]
    finally:
        main._detect_lock.release()


def test_fremder_nutzer_keine_erkennung(two, app, admin):
    from fastapi.testclient import TestClient
    c, pid, phid = two
    tok = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
    f = TestClient(app)
    assert f.post(f"/api/invite/{tok}", json={"username": f"fremdk{pid}", "display_name": "Fremd",
                                              "password": "Schieblehre-Messing-7"}, headers=H).status_code == 200
    assert f.post(f"/api/photos/{phid}/edges", json={}, headers=H).status_code == 404
    assert f.get(f"/api/photos/{phid}/edges.json").status_code == 404


def test_erneute_erkennung_behaelt_massstab(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    q = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()["parts"][0]
    L = next(m for m in c.get(f"/api/projects/{pid}").json()["measurements"]
             if m["part_id"] == q["id"] and m["data"].get("auto_key") == "L")
    c.patch(f"/api/measurements/{L['id']}", json={"caliper": round(L["value"] * 0.943, 3)}, headers=H)
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    q2 = next(p for p in res["parts"] if p["label"] == "Quader")
    assert q2["id"] == q["id"] and q2["scale"] == pytest.approx(0.943, abs=1e-3)
    labels = [m["label"] for m in c.get(f"/api/projects/{pid}").json()["measurements"] if m["part_id"] == q["id"]]
    assert labels.count("Quader Länge") == 1


def test_ki_unbrauchbar(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, 'Hier: [{"label": "x", "polygon": [[1, 2], [3, "a"]]}, 5, {"polygon": [[0, 0], [1, 1]]}]')
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert [p["label"] for p in res["parts"]] == ["Teil"] and "keine Teile" in res["notice"]
    _ki(monkeypatch, json.dumps([{"label": "riesig", "polygon": [[0, 0], [5000, 0], [0, 5000]]}]))
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert [p["label"] for p in res["parts"]] == ["Teil"] and "keine Teile" in res["notice"]


def test_ki_fehler_beim_ersten_lauf(two, monkeypatch):
    c, pid, phid = two
    _ki(monkeypatch, "kein json")
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert "KI-Zuordnung fehlgeschlagen" in res["notice"] and len(res["parts"]) == 1


def test_parse_parts_defensiv():
    from app import ai
    items = ai.parse_parts('```json\n[{"label": "' + "x" * 100 + '", "role": "egal", "polygon": [[0,0],[10,0],[10,10]], '
                           '"edges": ["K1", 3, null]}, {"polygon": [[0,0],[NaN,0],[1,1]]}]\n```')
    assert len(items) == 1 and items[0]["role"] == "body" and len(items[0]["label"]) == 80 and items[0]["edges"] == ["K1", "3"]


def test_leeres_foto_422(user):
    pid, phid = _upload(user, [])
    r = user.post(f"/api/photos/{phid}/edges", json={}, headers=H)
    assert r.status_code == 422 and "Kein Objekt" in r.json()["detail"]


def test_tageslimit_ohne_ki(two):
    c, pid, phid = two
    from app import db
    uid = c.get("/api/me").json()["user"]["id"]
    for _ in range(30):
        db.audit("suggest", "Test", user_id=uid)
    res = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()
    assert "Tageslimit" in res["notice"] and [p["label"] for p in res["parts"]] == ["Teil"]
    assert c.post(f"/api/projects/{pid}/suggest", json={}, headers=H).status_code == 429
```

- [ ] **Step 2: Tests scheitern**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_edges_api.py`
Expected: FAIL (405/404 auf `/api/photos/{phid}/edges`).

- [ ] **Step 3: `ai.py` erweitern**

`import math` zu den Importen. Nach `SUGGEST_SYSTEM` einfügen:

```python
PARTS_SYSTEM = """Du hilfst beim Vermessen von Bauteilen auf einer entzerrten Messunterlage (Draufsicht, Maßstab steht dabei).
Ursprung ist die linke untere Ecke des Bildes, x nach rechts, y nach oben, alles in mm.

Im Bild sind Kanten-Kandidaten eingezeichnet und nummeriert (K1, K2 …); die Liste mit Koordinaten steht im Text.
Sie stammen aus einer automatischen Kantenerkennung: Umrisskanten und gerade Kanten innerhalb des Objekts.

Aufgabe: Erkenne, aus welchen einzelnen Teilen das Objekt besteht. Beispiel: Ein Quader mit einer aufgeschraubten Platte,
die seitlich übersteht, sind zwei Teile – der Quader (role "body") und die Platte (role "mounted"). Ein einzelnes Teil
bleibt ein Teil. Gib für jedes Teil seinen vollständigen Umriss in der Draufsicht als Polygon an, auch dort, wo es von
einem anderen Teil verdeckt ist (verdeckte Kanten sinnvoll ergänzen, z. B. ein Rechteck vervollständigen). Nutze die
Koordinaten der Kandidaten, wo sie passen. Bohrungen gehören nicht in das Polygon.

Antworte ausschließlich mit einem JSON-Array, ohne Text davor oder danach:
[{"label": "Quader", "role": "body", "polygon": [[x1, y1], [x2, y2], [x3, y3]], "edges": ["K1", "K4"],
  "note": "kurz, woran erkannt"}]
role ist "body" (Grundkörper) oder "mounted" (montiertes Teil). edges = die Kandidaten, die zu diesem Teil gehören.
Höchstens 6 Teile, je 3 bis 32 Punkte."""
```

Vor `parse_suggestions` einen gemeinsamen Helfer einfügen und `parse_suggestions` darauf umstellen. Dessen ersten Block (`t = text.strip()` bis `raise AIError("Die Vorschlagsliste war kein gültiges JSON.") from e`) durch `items = _json_array(text, "Vorschlagsliste")` ersetzen; die Meldungen bleiben gleich:

```python
def _json_array(text: str, what: str) -> list:
    """JSON-Array aus einer KI-Antwort (auch in einem Codeblock oder mit Text drumherum)."""
    t = text.strip()
    m = _BLOCK.search(t)
    if m:
        t = m.group(2)
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j < i:
        raise AIError(f"Die Antwort enthielt keine {what}.")
    try:
        return json.loads(t[i:j + 1])
    except ValueError as e:
        raise AIError(f"Die {what} war kein gültiges JSON.") from e
```

Nach `parse_suggestions` einfügen:

```python
def parse_parts(text: str) -> list[dict]:
    """Teileliste der KI defensiv lesen (Spec §2): unbrauchbare Eintraege werden verworfen."""
    items = _json_array(text, "Teileliste")
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        pts = it.get("polygon")
        if not isinstance(pts, list) or not 3 <= len(pts) <= 32:
            continue
        try:
            poly = [[float(p[0]), float(p[1])] for p in pts if isinstance(p, list) and len(p) == 2]
        except (TypeError, ValueError):
            continue
        if len(poly) != len(pts) or not all(math.isfinite(v) and abs(v) < 1e4 for p in poly for v in p):
            continue
        raw_edges = it.get("edges") if isinstance(it.get("edges"), list) else []
        out.append({"label": str(it.get("label") or "Teil")[:80],
                    "role": it.get("role") if it.get("role") in ("body", "mounted") else "body",
                    "polygon": poly, "edges": [str(e)[:8] for e in raw_edges if isinstance(e, (str, int))][:64],
                    "note": str(it.get("note") or "")[:300]})
        if len(out) == 6:
            break
    return out
```

In `_fake` vor `if system == SUGGEST_SYSTEM:` einfügen:

```python
    if system == PARTS_SYSTEM:
        last = messages[-1]["content"]
        txt = " ".join(b.get("text", "") for b in last if isinstance(b, dict))
        m = re.search(r"Umriss 1: (.*)", txt)
        pts = [[float(a), float(b)] for a, b in re.findall(r"\((-?[\d.]+), (-?[\d.]+)\)", m.group(1))] if m else []
        return json.dumps([{"label": "Quader", "role": "body", "polygon": pts, "edges": [], "note": "Testmodus"}]), usage
```

- [ ] **Step 4: `parts.py` erweitern** – Importe ergänzen (`import cv2`, Importzeile `from . import ai, db, geom`; `core` wird erst in `candidate_image` importiert, weil `main.py` `sys.path` erst nach den App-Importen setzt) und anhängen:

```python
def outline_parts(res):
    """Ohne KI: jeder Umriss wird ein Teil, Bohrungen zum kleinsten umgebenden Teil."""
    out = [{"label": "Teil", "role": "body", "polygon": o["polygon"], "hidden": [False] * len(o["polygon"]), "source": "auto"}
           for o in res["outlines"]]
    assign_holes(out, res["holes"])
    return out


def candidate_image(photo_dir, res):
    """Kandidatenbild fuer die KI als edges_ki.jpg im Fotoordner (Zeichnen in core.edges)."""
    from core import edges as core_edges  # spaet: main.py setzt sys.path erst nach den App-Importen
    img = core_edges.draw_candidates(cv2.imread(str(photo_dir / "rect.jpg")), res)
    out = photo_dir / "edges_ki.jpg"
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out


def candidate_text(res):
    lines = ["Kanten-Kandidaten (mm, Draufsicht):"]
    for s in res["segments"]:
        lines.append(f"{s['id']}: ({s['a'][0]:.1f}, {s['a'][1]:.1f}) → ({s['b'][0]:.1f}, {s['b'][1]:.1f}), "
                     f"{_seg_len(s['a'], s['b']):.1f} mm, {'Umriss' if s['kind'] == 'outline' else 'Innenkante'}")
    for i, o in enumerate(res["outlines"], 1):
        lines.append(f"Umriss {i}: " + " ".join(f"({x:.1f}, {y:.1f})" for x, y in o["polygon"]))
    for h in res["holes"]:
        lines.append(f"Bohrung: Mitte ({h['c'][0]:.1f}, {h['c'][1]:.1f}), Ø {h['d']:.1f} mm")
    return "\n".join(lines)


def ai_parts(photo_dir, res):
    """Teile per KI zuordnen und auf die Kandidaten einrasten. Leere Liste = KI hat nichts Brauchbares geliefert."""
    img = candidate_image(photo_dir, res)
    content = ai.image_ref(img, ai.scaled_caption(img, "Draufsicht mit nummerierten Kanten-Kandidaten", res["px_per_mm"]))
    content.append({"type": "text", "text": candidate_text(res)})
    text, _ = ai.call(ai.PARTS_SYSTEM, [{"role": "user", "content": content}], max_tokens=4000)
    out = []
    for it in ai.parse_parts(text):
        poly, hidden = snap_polygon(it["polygon"], res["segments"], it["edges"])
        out.append({"label": it["label"], "role": it["role"], "polygon": poly, "hidden": hidden, "note": it["note"],
                    "source": "ki"})
    assign_holes(out, res["holes"])
    return out
```

- [ ] **Step 5: `main.py` – Tageslimit und Endpunkte**

Die bestehende Zeile `from core import matgen, vision  # noqa: E402` wird zu `from core import edges, matgen, vision  # noqa: E402`. `json`, `cv2`, `threading` (falls nicht vorhanden, ergänzen; `_preview_lock` deutet darauf hin), `datetime` und `timezone` sind schon importiert. Unter `_usage` einfügen:

```python
AI_DAILY_LIMIT = 30
_detect_lock = threading.Semaphore(1)  # nur um den OpenCV-Teil, nicht um den KI-Aufruf (Spec §7)


def _ai_uses_today(u: dict) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return db.q1("SELECT COUNT(*) n FROM audit WHERE user_id=? AND action IN ('suggest','edges_ai') AND substr(ts,1,10)=?",
                 (u["id"], today))["n"]
```

In `meas_suggest` die Zeilen

```python
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = db.q1("SELECT COUNT(*) n FROM audit WHERE user_id=? AND action='suggest' AND substr(ts,1,10)=?",
              (u["id"], today))["n"]
    if u["role"] != "admin" and n >= 30:
        raise HTTPException(429, "Tageslimit für Maßvorschläge erreicht (30).")
```

ersetzen durch

```python
    if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
        raise HTTPException(429, f"Tageslimit für KI-Funktionen erreicht ({AI_DAILY_LIMIT}).")
```

Nach `photo_file` einfügen. Die Route `/edges.json` muss vor `/{kind}.jpg` stehen oder kollisionsfrei sein. Sie ist kollisionsfrei, weil `{kind}.jpg` auf `.jpg` endet.

```python
class EdgesIn(BaseModel):
    use_ai: bool = True


@app.post("/api/photos/{phid}/edges")
def photo_edges(phid: int, body: EdgesIn, request: Request, u: dict = Depends(auth.require_user)):
    ph, p = _own_photo(phid, u)
    d = _photo_dir(phid)
    rect = (db.jload(ph["analysis"], {}) or {}).get("rect")
    if not rect or not (d / "rect.jpg").is_file() or ph["format"] not in matgen.FORMATS:
        raise HTTPException(400, "Für dieses Foto gibt es keine entzerrte Draufsicht.")
    img = cv2.imread(str(d / "rect.jpg"))
    if img is None:
        raise HTTPException(400, "Die Draufsicht ist nicht lesbar.")
    if not _detect_lock.acquire(blocking=False):
        raise HTTPException(429, "Kantenerkennung ist gerade belegt – bitte gleich erneut versuchen.")
    try:
        res = edges.detect(img, ph["format"])
    finally:
        _detect_lock.release()
    if not res["outlines"]:
        raise HTTPException(422, "Kein Objekt erkannt – Teil von Hand zeichnen.")

    def inside(poly):
        return all(-10 <= q[0] <= rect["w_mm"] + 10 and -10 <= q[1] <= rect["h_mm"] + 10 for q in poly)
    notice, detected, ai_failed = "", [], False
    if body.use_ai and settings.ai_enabled():
        if u["role"] != "admin" and _ai_uses_today(u) >= AI_DAILY_LIMIT:
            notice, ai_failed = f"Tageslimit für KI erreicht ({AI_DAILY_LIMIT}) – Teile nur aus dem Umriss.", True
        else:
            db.audit("edges_ai", f"Foto {phid}", user_id=u["id"], actor=u["username"], ip=auth.client_ip(request))
            try:
                detected = [x for x in parts.ai_parts(d, res) if inside(x["polygon"])]
                if not detected:
                    notice, ai_failed = "Die KI hat keine Teile erkannt – Teile nur aus dem Umriss.", True
            except ai.AIError as e:
                notice, ai_failed = f"KI-Zuordnung fehlgeschlagen: {e} – Teile nur aus dem Umriss.", True
    with db.atomic():
        cur = db.q1("SELECT format FROM photos WHERE id=?", (phid,))
        if not cur or cur["format"] != ph["format"]:
            raise HTTPException(409, "Das Foto wurde während der Erkennung geändert – bitte erneut erkennen.")
        has_parts = bool(db.q1("SELECT 1 FROM parts WHERE photo_id=? AND source!='user'", (phid,)))
        if not detected and has_parts:
            # ohne KI-Ergebnis vorhandene Teile nicht durch den Gesamtumriss ersetzen (sonst zerfaellt z. B. Quader + Platte)
            notice = notice.replace("Teile nur aus dem Umriss.", "vorhandene Teile bleiben unverändert.") if notice \
                else "Ohne KI wurden nur die Kanten aktualisiert; vorhandene Teile bleiben unverändert."
        else:
            parts.replace_detected(p["id"], phid, detected or parts.outline_parts(res))
        _refresh(p)
        tmp = d / "edges.json.tmp"  # innerhalb von atomic: kein zweiter Lauf und kein Loeschen dazwischen
        tmp.write_text(json.dumps(res), encoding="utf-8")
        os.replace(tmp, d / "edges.json")
    return {"parts": [t for t in parts.public_list(p["id"]) if t["photo_id"] == phid], "segments": res["segments"],
            "notice": notice}


@app.get("/api/photos/{phid}/edges.json")
def photo_edges_get(phid: int, u: dict = Depends(auth.require_user)):
    _own_photo(phid, u)
    f = _photo_dir(phid) / "edges.json"
    if not f.is_file():
        raise HTTPException(404, "Noch keine Kanten erkannt")
    return json.loads(f.read_text(encoding="utf-8"))
```

`os` und `threading` sind in `main.py` schon importiert.

Hinweis zu `test_erneute_erkennung_ohne_ki_laesst_teile`: Der dritte Lauf mit `use_ai: false` findet Teile vor und lässt sie stehen; der Hinweis ist „Ohne KI wurden nur die Kanten aktualisiert …“. `test_ohne_ki_und_handteil_bleibt`: Ein Handteil zählt nicht als „vorhandene Teile“ (`source!='user'`), also entsteht das Umriss-Teil, und das Handteil bleibt (Task 5, `replace_detected`).

- [ ] **Step 6: Tests grün**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check .`
Expected: PASS. `test_claude_suggestions` muss weiter grün sein, also bleibt das Tageslimit für Vorschläge gleich.

- [ ] **Step 7: Commit**

```bash
git add web/app/ai.py web/app/parts.py web/app/main.py tests/test_edges_api.py
git commit -m "Kanten erkennen: OpenCV-Kandidaten, KI-Teile-Zuordnung mit Einrasten, Rückfall ohne KI"
```

---

### Task 7: CAD für ein gewähltes Teil

**Files:**
- Modify: `web/app/jobs.py` (`measurement_table`, `build_initial_message`)
- Modify: `web/app/ai.py:25-26` (`CAD_SYSTEM`, Abschnitt „Eingaben“)
- Modify: `web/app/parts.py` (`cad_text`)
- Modify: `web/app/main.py` (`JobIn`, `job_create`)
- Modify: `web/static/js/cad.js` (`form`)
- Test: `tests/test_edges_api.py` (erweitern)

**Interfaces:**
- Consumes: `jobs.SOURCE_LABEL` (Task 1), Teile aus Task 5/6.
- Produces: `jobs.measurement_table(project_id, part_id=None) -> (str, rows)` mit den Spalten `| ID | Bezeichnung | Teil | Art | Wert | ± | Messschieber | Nennmaß | kritisch | Passung | Quelle | Ansicht/Punkte (mm) |`; `parts.cad_text(project_id, part_id=None) -> str`; `JobIn.part_id`.

- [ ] **Step 1: Failing Test** – an `tests/test_edges_api.py` anhängen:

```python
def test_cad_auftrag_fuer_ein_teil(two, monkeypatch, user):
    c, pid, phid = two
    _ki(monkeypatch, KI_ZWEI)
    q, pl = c.post(f"/api/photos/{phid}/edges", json={}, headers=H).json()["parts"]
    from app import db, jobs
    project = db.q1("SELECT * FROM projects WHERE id=?", (pid,))
    msg = jobs.build_initial_message(project, "Platte nachbauen", {"part_id": pl["id"], "name": "P"})
    text = msg[0]["content"][0]["text"]
    assert "Modelliert wird nur Teil T2 „Platte“ (montiertes Teil)" in text
    assert "| Teil |" in text and "| Messschieber |" in text
    alle = jobs.build_initial_message(project, "alles", {"name": "A"})[0]["content"][0]["text"]
    assert "Teile im Foto: T1 Quader (Grundkörper), T2 Platte (montiertes Teil)" in alle
    _, rows = jobs.measurement_table(pid, pl["id"])
    assert rows and all(m["part_id"] != q["id"] for m in rows)
    other = user.post("/api/projects", json={"name": "x"}, headers=H).json()["id"]
    bad = c.post("/api/jobs", json={"project_id": other, "name": "x", "request": "x", "part_id": pl["id"]}, headers=H)
    assert bad.status_code == 400
    r = c.post("/api/jobs", json={"project_id": pid, "name": "P", "request": "Platte", "part_id": pl["id"]}, headers=H)
    assert r.status_code == 200, r.text
    t = json.loads(db.q1("SELECT messages FROM jobs WHERE id=?", (r.json()["id"],))["messages"])[0]["content"][0]["text"]
    assert "Modelliert wird nur Teil T2" in t and "| T1 |" not in t
```

Achtung: `user` und `two` sind dieselbe Fixture-Instanz (`two` nutzt `user`). `other` gehört also demselben Nutzer und ist trotzdem ein anderes Projekt.

- [ ] **Step 2: Test scheitert**

Run: `/root/Snap2CAD-venv/bin/pytest -q tests/test_edges_api.py -k cad`
Expected: FAIL (`TypeError` bei `measurement_table` oder der Text fehlt).

- [ ] **Step 3: Implementieren**

`web/app/parts.py` anhängen:

```python
def cad_text(project_id, part_id=None):
    """Hinweis fuer die CAD-KI, welche Teile es gibt und welches modelliert wird (Spec §5)."""
    rows = db.q("SELECT * FROM parts WHERE project_id=? ORDER BY seq", (project_id,))
    if not rows:
        return ""
    if part_id:
        t = next((r for r in rows if r["id"] == part_id), None)
        if not t:
            return ""
        pts = " ".join(f"({x:.1f}, {y:.1f})" for x, y in _data(t)["polygon"])
        return (f"Modelliert wird nur Teil T{t['seq']} „{t['label']}“ ({ROLE_TEXT[t['role']]}). "
                f"Umriss in der Draufsicht (mm): {pts}. Maße anderer Teile sind nicht enthalten.")
    names = ", ".join(f"T{r['seq']} {r['label']} ({ROLE_TEXT[r['role']]})" for r in rows)
    return f"Teile im Foto: {names}. Alle Teile als ein Körper modellieren."
```

`web/app/jobs.py`: Import `from .parts import cad_text` (nicht das Modul, weil `build_initial_message` eine lokale Variable `parts` hat). `measurement_table` ersetzen:

```python
def measurement_table(project_id: int, part_id: int | None = None) -> tuple[str, list[dict]]:
    rows = db.q("SELECT * FROM measurements WHERE project_id=? AND accepted=1 ORDER BY seq", (project_id,))
    if part_id is not None:
        rows = [m for m in rows if m["part_id"] in (part_id, None)]
    seq = {t["id"]: t["seq"] for t in db.q("SELECT id, seq FROM parts WHERE project_id=?", (project_id,))}
    lines = ["| ID | Bezeichnung | Teil | Art | Wert | ± | Messschieber | Nennmaß | kritisch | Passung | Quelle "
             "| Ansicht/Punkte (mm) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in rows:
        d = db.jload(m["data"], {}) or {}
        pts = d.get("points") or []
        where = d.get("view", "")
        if pts:
            where += " " + " ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in pts[:3])
        teil = f"T{seq[m['part_id']]}" if m["part_id"] in seq else ""
        lines.append(f"| M{m['seq']} | {m['label']} | {teil} | {m['kind']} | {_fmt(m['value'])} {m['unit']} | "
                     f"{_fmt(m['unc'])} | {_fmt(m['caliper'])} | {_fmt(d.get('nominal'))} | {'ja' if m['critical'] else ''} | "
                     f"{m['fit'] or ''} | {SOURCE_LABEL.get(m['source'], m['source'])} | {where.strip()} |")
    return "\n".join(lines), rows
```

In `build_initial_message`: `table, rows = measurement_table(project["id"])` → `table, rows = measurement_table(project["id"], options.get("part_id"))`. Direkt nach dem Aufbau der Liste `parts = [...]` einfügen:

```python
    teile = cad_text(project["id"], options.get("part_id"))
    if teile:
        parts[parts.index("## Messwerte") + 1:parts.index("## Messwerte") + 1] = [teile]
```

Damit steht der Teile-Hinweis direkt unter „## Messwerte“ und vor der Tabelle.

`web/app/ai.py`, `CAD_SYSTEM` Zeilen 25–26 ersetzen durch:

```
- Eine Messtabelle (IDs M1, M2 …) mit Messwert, Unsicherheit, optionalem Messschieber-Wert, Nennmaß-Vorschlag,
  Teil (T1, T2 …), Passung und Kennzeichnung „kritisch“. Ein Messschieber-Wert hat immer Vorrang vor dem Fotowert;
  das Nennmaß ist nur ein Vorschlag, Regel 2 gilt weiter.
```

`web/app/main.py`: `JobIn` um `part_id: int | None = None` ergänzen. In `job_create` nach `project = …`:

```python
    if body.part_id is not None and (not project or not db.q1("SELECT id FROM parts WHERE id=? AND project_id=?",
                                                              (body.part_id, project["id"]))):
        raise HTTPException(400, "Teil gehört nicht zu diesem Projekt")
```

und im Options-Dict `"part_id": body.part_id,` ergänzen.

`web/static/js/cad.js` in `form()`:
- nach `const crit = meas.filter(m => m.critical);` einfügen:

```js
  const partsList = P.parts || [];
  let partSel = "";
  const partBox = partsList.length ? h("select", { id: "part", class: "input", onchange: e => { partSel = e.target.value; drawMeas(); } },
    h("option", { value: "" }, "Alle Teile (ein Körper)"),
    partsList.map(t => h("option", { value: String(t.id) }, `${t.id_label} · ${t.label}`))) : null;
  const sentMeas = () => partSel ? meas.filter(m => m.part_id == null || m.part_id === Number(partSel)) : meas;
  const measBox = h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } });
  function drawMeas() {
    const list = sentMeas();
    clear(measBox, h("span", { class: "label" }, `Maßtabelle · ${list.length}`),
      list.length ? h("table", { class: "t" }, h("thead", {}, h("tr", {}, h("th", {}, "ID"), h("th", {}, "Merkmal"), h("th", { style: { textAlign: "right" } }, "Wert"), h("th", { style: { textAlign: "right" } }, "±"))),
        h("tbody", {}, list.map(m => h("tr", {}, h("td", { class: "mono" }, `M${m.seq}`), h("td", {}, m.label, m.critical ? " ★" : ""),
          h("td", { class: "num" }, m.caliper != null ? `${m.kind === "diameter" ? "Ø " : ""}${num(m.caliper, 2)}` : fmtValue(m).replace(" mm", "")),
          h("td", { class: "num" }, m.caliper != null ? "MS" : num(m.unc, 1))))))
        : h("div", { class: "note warn" }, icon("warn"), h("span", {}, "Noch keine Maße. ", h("a", { href: "/messen" }, "Jetzt messen"), " – oder alles im Feld „Zweck und Funktion“ beschreiben.")),
      list.length ? h("span", { class: "xs muted" }, "★ kritisch · MS = Messschieber-Wert") : null);
  }
```

- In der rechten Spalte den bisherigen Block (Zeilen 109–115, `h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } }, h("span", { class: "label" }, \`Maßtabelle · ${meas.length}\`), … : null),`) durch `measBox,` ersetzen.
- Im Formular nach dem Feld „Bezeichnung“ einfügen:

```js
      partBox ? h("div", { class: "field" }, h("label", { for: "part" }, "Modell für"), partBox,
        h("span", { class: "hint" }, "Bei einem einzelnen Teil gehen nur dessen Maße und Maße ohne Teil in den Auftrag.")) : null,
```

- Im `api("/api/jobs", …)`-Body `photo_ids: [...picked]` → `photo_ids: [...picked], part_id: partSel ? Number(partSel) : null`.
- Vor `setProc(proc);` am Ende von `form()` `drawMeas();` aufrufen.

- [ ] **Step 4: Tests grün**

Run: `/root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check . && node --check web/static/js/cad.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/jobs.py web/app/parts.py web/app/main.py web/app/ai.py web/static/js/cad.js tests/test_edges_api.py
git commit -m "CAD-Auftrag für ein gewähltes Teil, Maßtabelle mit Teil und Nennmaß"
```

---

### Task 8: Oberfläche „Messen“ – Teile zeichnen, bearbeiten, Seitenleiste

**Files:**
- Create: `web/static/js/edges.js`
- Modify: `web/static/js/measure.js`, `web/static/js/lib.js` (`ICONS.edges`), `web/static/css/app.css` (`.src-part`)

**Interfaces:**
- Consumes: `GET /api/projects/{pid}` (`parts`, `measurements[].part_id`, `data.auto_key|raw|nominal|warn|ref_warn|ref|part_fixed`), `POST /api/photos/{id}/edges`, `GET /api/photos/{id}/edges.json`, `POST /api/projects/{pid}/parts`, `PATCH/DELETE /api/parts/{id}`, `PATCH /api/measurements/{id}` (`part_id`, `ref`).
- Produces (`edges.js`): `PART_COLORS`, `partColor(part)`, `ROLE`, `segDist(p, a, b)`, `createPartsLayer(env)` → `{ draw, down, move, up, click, key, select, startNew, cancel, reset, setSegments, selected, drawing }`, `partsPanel({ photoId, selected, onSelect, onNew, onChanged })` → Element.

- [ ] **Step 1: Icon** – in `web/static/js/lib.js` `ICONS` nach `angle:` einfügen:

```js
  edges: '<path d="M4 18L7 5l11 2 2 11z"/><circle cx="4" cy="18" r="1.6" fill="currentColor"/><circle cx="7" cy="5" r="1.6" fill="currentColor"/><circle cx="18" cy="7" r="1.6" fill="currentColor"/><circle cx="20" cy="18" r="1.6" fill="currentColor"/>',
```

In `web/static/css/app.css` nach der Zeile mit `.src-claude{…}` (Zeile 213) einfügen:

```css
.src-part{font-size:11px;font-weight:600;padding:1px 6px;border-radius:3px;color:#fff;margin-left:6px}
```

- [ ] **Step 2: `web/static/js/edges.js` anlegen**

```js
// Kanten und Teile auf der Messflaeche: Zeichnen, Bearbeiten, Seitenleiste (Spec 2026-10-14 §4)
import { api, h, clear, icon, num, toast, fail, confirmDlg } from "./lib.js";
import { S, reloadProject } from "./app.js";

export const PART_COLORS = ["#0F766E", "#7C3AED", "#B45309", "#BE185D", "#4D7C0F", "#0369A1"];
export const partColor = p => PART_COLORS[(p.seq - 1) % PART_COLORS.length];
export const ROLE = { body: "Grundkörper", mounted: "montiertes Teil" };
const HANDLE = 7, DARK = "#17212B";
const r3 = v => Math.round(v * 1000) / 1000;

export function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
  let t = l ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l : 0; t = Math.max(0, Math.min(1, t));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
function inPoly(p, P) {
  let c = false;
  for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
    const [xi, yi] = P[i], [xj, yj] = P[j];
    if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c;
  }
  return c;
}
function area(P) { let a = 0; for (let i = 0; i < P.length; i++) { const q = P[i], r = P[(i + 1) % P.length]; a += q[0] * r[1] - r[0] * q[1]; } return Math.abs(a) / 2; }
function tag(ctx, [x, y], text, col) {
  ctx.font = `600 12px "IBM Plex Sans", sans-serif`;
  const w = ctx.measureText(text).width + 10;
  ctx.fillStyle = "rgba(255,255,255,.92)"; ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.setLineDash([]);
  ctx.beginPath(); ctx.roundRect(x - w / 2, y - 10, w, 20, 3); ctx.fill(); ctx.stroke();
  ctx.fillStyle = col; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, x, y + 0.5);
}
function plus(ctx, [x, y], col) {
  ctx.fillStyle = "#fff"; ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.setLineDash([]);
  ctx.beginPath(); ctx.arc(x, y, HANDLE - 1, 0, 7); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x - 3.5, y); ctx.lineTo(x + 3.5, y); ctx.moveTo(x, y - 3.5); ctx.lineTo(x, y + 3.5); ctx.stroke();
}

// env: { ctx(), scr(ix, iy), toPX(X, Y), cursorMM() -> [X, Y] | null, photoId() -> id | null, active() -> bool,
//        redraw(), changed(), selectPart(id) }
export function createPartsLayer(env) {
  let sel = null, vtx = null, drag = null, drawing = null, segments = [], busy = false;
  const list = () => (env.photoId() ? (S.project.parts || []).filter(p => p.photo_id === env.photoId()) : []);
  const P = q => env.scr(...env.toPX(q[0], q[1]));
  const selPart = () => list().find(p => p.id === sel) || null;

  function unassigned() {
    const ps = list();
    return segments.filter(s => s.kind === "inner" && !ps.some(p => p.polygon.some((a, i) => {
      const b = p.polygon[(i + 1) % p.polygon.length];
      return segDist(s.a, a, b) < 1.5 && segDist(s.b, a, b) < 1.5;
    })));
  }
  function draw() {
    if (!env.photoId()) return;
    const ctx = env.ctx(), act = env.active();
    ctx.save();
    if (act) {
      ctx.strokeStyle = "#8A96A3"; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
      for (const s of unassigned()) { ctx.beginPath(); ctx.moveTo(...P(s.a)); ctx.lineTo(...P(s.b)); ctx.stroke(); }
    }
    for (const part of list()) {
      const live = drag?.id === part.id;
      const pts = (live ? drag.poly : part.polygon).map(P);
      const col = partColor(part), isSel = part.id === sel;
      ctx.setLineDash([]); ctx.fillStyle = col + (isSel ? "22" : "12");
      ctx.beginPath(); pts.forEach((q, i) => (i ? ctx.lineTo(...q) : ctx.moveTo(...q))); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = isSel ? 2.6 : 1.8;
      pts.forEach((q, i) => {
        const hid = !live && part.hidden.includes(part.edge_ids[i]);
        ctx.setLineDash(hid ? [6, 5] : []);
        ctx.beginPath(); ctx.moveTo(...q); ctx.lineTo(...pts[(i + 1) % pts.length]); ctx.stroke();
      });
      const c = pts.reduce((a, q) => [a[0] + q[0] / pts.length, a[1] + q[1] / pts.length], [0, 0]);
      tag(ctx, c, `${part.id_label} ${part.label}`, col);
      if (act && isSel) {
        pts.forEach((q, i) => {
          ctx.setLineDash([]); ctx.fillStyle = i === vtx ? col : "#fff"; ctx.strokeStyle = col; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(q[0], q[1], HANDLE - 2, 0, 7); ctx.fill(); ctx.stroke();
        });
        if (!drag) pts.forEach((q, i) => { const r = pts[(i + 1) % pts.length]; plus(ctx, [(q[0] + r[0]) / 2, (q[1] + r[1]) / 2], col); });
      }
    }
    if (drawing) {
      const pts = drawing.map(P), cur = env.cursorMM();
      if (cur) pts.push(P(cur));
      ctx.setLineDash([]); ctx.strokeStyle = DARK; ctx.lineWidth = 1.8;
      ctx.beginPath(); pts.forEach((q, i) => (i ? ctx.lineTo(...q) : ctx.moveTo(...q))); ctx.stroke();
      ctx.fillStyle = DARK;
      drawing.map(P).forEach(q => { ctx.beginPath(); ctx.arc(q[0], q[1], 4, 0, 7); ctx.fill(); });
    }
    ctx.restore();
  }
  function hitVertex(sx, sy) {
    const part = selPart(); if (!part) return null;
    const i = part.polygon.findIndex(q => { const s = P(q); return Math.hypot(s[0] - sx, s[1] - sy) <= HANDLE + 2; });
    return i >= 0 ? { part, i } : null;
  }
  function hitPlus(sx, sy) {
    const part = selPart(); if (!part) return null;
    const pts = part.polygon.map(P);
    for (let i = 0; i < pts.length; i++) {
      const r = pts[(i + 1) % pts.length];
      if (Math.hypot((pts[i][0] + r[0]) / 2 - sx, (pts[i][1] + r[1]) / 2 - sy) <= HANDLE + 2) return { part, i };
    }
    return null;
  }
  function hitPart(sx, sy) {
    let best = null;
    for (const p of list()) {
      const pts = p.polygon.map(P);
      const edge = Math.min(...pts.map((q, i) => segDist([sx, sy], q, pts[(i + 1) % pts.length])));
      if (edge > 8 && !inPoly([sx, sy], pts)) continue;
      const k = edge <= 8 ? -1 : area(pts);
      if (!best || k < best.k) best = { p, k };
    }
    return best?.p || null;
  }
  function select(id) { sel = id; vtx = null; env.selectPart?.(id); env.redraw(); }
  async function save(id, body) {  // busy: kein zweites Ziehen auf veraltetem Stand, bis neu geladen ist
    busy = true;
    try {
      try { await api(`/api/parts/${id}`, { method: "PATCH", body }); } catch (e) { fail(e); }
      await reloadProject().catch(() => {});
    } finally { busy = false; }
    env.changed();
  }
  async function finishNew() {
    if (!drawing || drawing.length < 3) { toast("Mindestens 3 Punkte setzen", "err"); return; }
    const polygon = drawing; drawing = null;
    try {
      const p = await api(`/api/projects/${S.project.id}/parts`, { method: "POST", body: { photo_id: env.photoId(), label: "", role: "body", polygon } });
      await reloadProject(); sel = p.id; env.changed();
    } catch (e) { fail(e); env.redraw(); }
  }

  // Zeiger: down() liefert true, wenn die Ebene das Ziehen uebernimmt (Eckpunkt oder Griff „+“)
  function down(sx, sy) {
    if (drawing || busy) return false;
    const v = hitVertex(sx, sy);
    if (v) { vtx = v.i; drag = { id: v.part.id, i: v.i, poly: v.part.polygon.map(q => [...q]), moved: false, sx, sy }; env.redraw(); return true; }
    const pl = hitPlus(sx, sy);
    if (pl) {
      const poly = pl.part.polygon.map(q => [...q]), a = poly[pl.i], b = poly[(pl.i + 1) % poly.length];
      poly.splice(pl.i + 1, 0, [r3((a[0] + b[0]) / 2), r3((a[1] + b[1]) / 2)]);
      vtx = pl.i + 1; drag = { id: pl.part.id, i: pl.i + 1, poly, moved: true, sx, sy }; env.redraw(); return true;
    }
    return false;
  }
  function move(sx, sy) {
    if (!drag) return false;
    if (!drag.moved && Math.hypot(sx - drag.sx, sy - drag.sy) < 3) return true;
    drag.moved = true;
    const mm = env.cursorMM(); if (mm) drag.poly[drag.i] = [r3(mm[0]), r3(mm[1])];
    env.redraw(); return true;
  }
  async function up() {
    const d = drag; drag = null;
    if (!d) return false;
    if (!d.moved) { env.redraw(); return true; }
    await save(d.id, { polygon: d.poly });
    return true;
  }
  async function click(sx, sy) {
    if (drawing) {
      const mm = env.cursorMM(); if (!mm) return;
      if (drawing.length >= 3) { const f = P(drawing[0]); if (Math.hypot(f[0] - sx, f[1] - sy) <= 10) { await finishNew(); return; } }
      drawing.push([r3(mm[0]), r3(mm[1])]); env.redraw(); return;
    }
    const p = hitPart(sx, sy); select(p ? p.id : null);
  }
  // Tasten nur im Werkzeug „Kanten“; true = verarbeitet
  function key(e) {
    const k = e.key;
    if (busy && (k === "Delete" || k === "Backspace")) return true;
    if (drawing) {
      if (k === "Escape") { drawing = null; env.redraw(); return true; }
      if (k === "Enter") { finishNew(); return true; }
      if (k === "Backspace" || k === "Delete") { drawing.pop(); env.redraw(); return true; }
      return false;
    }
    if ((k === "Delete" || k === "Backspace") && sel && vtx != null) {
      const part = selPart(); if (!part) return false;
      if (part.polygon.length <= 3) { toast("Ein Teil braucht mindestens 3 Eckpunkte", "err"); return true; }
      const poly = part.polygon.filter((_, i) => i !== vtx); vtx = null;
      save(part.id, { polygon: poly }); return true;
    }
    if (k === "Escape" && sel) { select(null); return true; }
    return false;
  }
  return {
    draw, down, move, up, click, key, select,
    startNew() { drawing = []; sel = null; vtx = null; env.redraw(); },
    cancel() { drawing = null; drag = null; env.redraw(); },
    reset() { sel = null; vtx = null; drag = null; drawing = null; segments = []; },
    setSegments(s) { segments = s || []; env.redraw(); },
    get selected() { return sel; }, get drawing() { return !!drawing; },
  };
}

export function partsPanel({ photoId, selected, onSelect, onNew, onChanged }) {
  const ps = (S.project.parts || []).filter(p => p.photo_id === photoId);
  async function patchPart(p, body) {
    try { await api(`/api/parts/${p.id}`, { method: "PATCH", body }); await reloadProject(); onChanged(); } catch (e) { fail(e); }
  }
  async function delPart(p) {
    if (!await confirmDlg(`${p.id_label} löschen?`, "Automatische Maße des Teils werden entfernt. Maße mit Messschieber-Wert bleiben als normale Messung erhalten.", "Löschen", true)) return;
    try { await api(`/api/parts/${p.id}`, { method: "DELETE" }); await reloadProject(); onSelect(null); onChanged(); } catch (e) { fail(e); }
  }
  function editor(p) {
    const lbl = h("input", { class: "input", value: p.label, maxlength: 80, "aria-label": `Name von ${p.id_label}` });
    lbl.addEventListener("change", () => patchPart(p, { label: lbl.value }));
    lbl.addEventListener("keydown", e => { if (e.key === "Enter") lbl.blur(); });
    const role = h("select", { class: "input", "aria-label": "Rolle", onchange: e => patchPart(p, { role: e.target.value }) },
      Object.entries(ROLE).map(([k, t]) => h("option", { value: k, selected: k === p.role }, t)));
    return h("div", { class: "medit", onclick: e => e.stopPropagation() },
      h("div", { class: "grid2" }, h("div", { class: "field" }, h("label", {}, "Bezeichnung"), lbl), h("div", { class: "field" }, h("label", {}, "Rolle"), role)),
      p.note ? h("span", { class: "xs muted" }, `KI: ${p.note}`) : null,
      h("div", { class: "chips", style: { justifyContent: "flex-end" } }, h("button", { class: "btn sm danger", onclick: () => delPart(p) }, icon("trash", 14), "Teil löschen")));
  }
  const items = ps.map(p => {
    const isSel = p.id === selected, col = partColor(p);
    const scaled = Math.abs(p.scale - 1) > 1e-6;
    return h("li", { class: "mitem", "aria-current": String(isSel), tabindex: 0, style: { borderLeft: `4px solid ${col}` },
      onclick: () => onSelect(isSel ? null : p.id), onkeydown: e => { if (e.key === "Enter" && e.target === e.currentTarget) onSelect(isSel ? null : p.id); } },
      h("span", { class: "mid", style: { color: col } }, p.id_label),
      h("span", { style: { fontWeight: 500, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, p.label),
      h("span", { class: "mval" }, p.rect && p.size ? `${num(p.size[0], 2)} × ${num(p.size[1], 2)} mm` : `${p.n_edges} Kanten`),
      h("span", { class: "msub" }, ROLE[p.role],
        scaled ? h("span", {}, ` · Maßstab × ${num(p.scale, 3)}${p.refs.length ? ` aus ${p.refs.join(", ")}` : ""} `,
          h("button", { class: "btn sm ghost", style: { minHeight: "24px", padding: "0 6px" }, onclick: e => { e.stopPropagation(); patchPart(p, { reset_scale: true }); } }, "Zurücksetzen")) : null),
      p.warn ? h("span", { class: "msub", style: { color: "var(--warn)" } }, p.warn) : null,
      isSel ? editor(p) : null);
  });
  return h("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } },
    h("div", { class: "card-head" }, h("h2", { id: "t-h" }, "Teile ", h("span", { class: "muted", style: { fontWeight: 400 } }, `(${ps.length})`)),
      h("button", { class: "btn sm", onclick: onNew, disabled: !photoId }, icon("plus", 16), "Neues Teil")),
    ps.length ? h("ul", { class: "mlist", "aria-labelledby": "t-h" }, items)
      : h("p", { class: "xs muted", style: { margin: 0 } }, photoId ? "Noch keine Teile. „Kanten erkennen“ oder „Neues Teil“ zeichnen." : "Teile gibt es nur auf einer Draufsicht."),
    photoId ? h("p", { class: "xs muted", style: { margin: 0 } }, "Grenzen: Weiße Teile auf weißem Papier und harte Schlagschatten verfälschen den Umriss – dann die Eckpunkte von Hand korrigieren.") : null);
}
```

- [ ] **Step 3: `measure.js` anbinden** – Änderungen in dieser Reihenfolge:

1. Importe: `reloadProject` ist in Zeile 3 schon importiert. Nach Zeile 4 einfügen:

```js
import { createPartsLayer, partsPanel, partColor, segDist } from "./edges.js";
```

   Die lokale Funktion `segDist` (Zeilen 417–421) löschen.
2. `TOOLS` um `["edges", "Kanten", "E", "edges"]` am Ende ergänzen.
3. Nach `const suggBtn = …` (Zeile 73) einfügen:

```js
  const edgeBtn = h("button", { class: "btn sm", onclick: detectEdges, title: "Kanten und Teile auf diesem Foto erkennen" }, icon("edges", 16), "Kanten erkennen");
  const partsBox = h("div");
  let edgeDrag = false;
```

4. In der Werkzeugleiste nach `h("div", { class: "grp", role: "toolbar" }, Object.values(toolBtns)),` die Zeile `edgeBtn,` einfügen. In der Seitenleiste nach `h("div", { style: { display: "flex", flexDirection: "column", gap: "10px" } }, picker),` die Zeile `partsBox,` einfügen.
5. Nach `const ctx = canvas.getContext("2d");` einfügen:

```js
  const layer = createPartsLayer({
    ctx: () => ctx, scr: (ix, iy) => scr(ix, iy), toPX: (X, Y) => src.toPX(X, Y), cursorMM: () => cursor?.mm || null,
    photoId: () => (src && src.view === "top" ? src.photo.id : null), active: () => tool === "edges",
    redraw: () => { dirty = true; }, changed: () => { renderList(); dirty = true; }, selectPart: () => renderList(),
  });
```

   `scr` ist eine `const`-Pfeilfunktion weiter unten. Der Zugriff passiert erst zur Laufzeit, aber die Pfeilfunktion im `env` kapselt ihn, also gibt es kein TDZ-Problem.
6. `loadSource`: Nach `src = x; pts = []; pixels = null;` die Zeile `layer.reset();` einfügen. Nach `setTool(tool);` einfügen:

```js
    if (x.view === "top") api(`/api/photos/${x.photo.id}/edges.json`).then(r => { if (src === x) layer.setSegments(r.segments); }).catch(() => {});
```

7. `draw()`: Nach `ctx.drawImage(img, …);` die Zeile `layer.draw();` einfügen. Die Bedingung `if (tool !== "pan" && pts.length) {` wird zu `if (tool !== "pan" && tool !== "edges" && pts.length) {`.
8. `HINTS` ergänzen:

```js
    edges: "Kanten: Teil anklicken · Eckpunkt ziehen · Griff + an der Kantenmitte = Punkt einfügen · Entf = Punkt löschen · Esc = abbrechen",
```

9. `setTool(k)`: als erste Zeile `if (k !== "edges") layer.cancel();`.
10. `pointerdown`: Nach dem Pinch-Block (`if (pointers.size === 2) {…}`) und vor `dragStart = {…}` einfügen:

```js
    if (tool === "edges" && e.button === 0) { updateCursor(e); if (layer.down(...evPos(e))) { edgeDrag = true; return; } }
```

   Im Pinch-Block (`if (pointers.size === 2) {…}`) vor `dragStart = null; return;` einfügen: `if (edgeDrag) { edgeDrag = false; layer.cancel(); }`.

11. `pointermove`: nach dem Pinch-Block (`if (pinch && pointers.size === 2) {…}`) einfügen:

```js
    if (edgeDrag) { updateCursor(e); layer.move(...evPos(e)); return; }
```

12. `endPointer`: nach `if (pointers.size < 2) pinch = null;` einfügen:

```js
    if (edgeDrag) { edgeDrag = false; if (e.type === "pointercancel") layer.cancel(); else layer.up(); return; }
```

13. `click(e)`: nach `if (!img || !cursor) return;` einfügen:

```js
    if (tool === "edges") { layer.click(...evPos(e)); return; }
```

14. `onKey`: nach `const k = e.key.toLowerCase();` einfügen:

```js
    if (tool === "edges") {
      if (layer.key(e)) { e.preventDefault(); return; }
      if (k === "delete" || k === "backspace" || k === "enter") return;
    }
```

   In `map` `e: "edges"` ergänzen.
15. `patch(m, body)` und `del(m)`: Nach erfolgreichem API-Aufruf `await reloadProject();` statt `Object.assign(m, n);` bzw. statt des Filterns, dann `renderList(); dirty = true;`. Bei `del` bleibt `if (selId === m.id) selId = null;`. Im Messungs-`click` nach `const m = await api(…)` `await reloadProject();` statt `S.project.measurements.push(m);`. Ebenso in `manual()`: `await reloadProject();` statt `S.project.measurements.push(m);`.
16. `sourceText(m)`: als erste Zeile einfügen:

```js
    if (m.source === "auto") { const t = (S.project.parts || []).find(p => p.id === m.part_id); return `${KIND[m.kind]} · automatisch aus ${t ? t.id_label : "Teil"}`; }
```

17. `renderList`: Am Anfang einfügen:

```js
    clear(partsBox, partsPanel({ photoId: src && src.view === "top" ? src.photo.id : null, selected: layer.selected,
      onSelect: id => { if (id) setTool("edges"); layer.select(id); }, onNew: () => { setTool("edges"); layer.startNew(); },
      onChanged: () => { renderList(); dirty = true; } }));
    const partOf = m => (S.project.parts || []).find(p => p.id === m.part_id);
```

   Im Listeneintrag `m.source === "claude" ? h("span", { class: "src-claude" }, "KI") : null),` ersetzen durch (Komma beachten, die schließende Klammer wandert ans Ende):

```js
          m.source === "claude" ? h("span", { class: "src-claude" }, "KI") : null,
          partOf(m) ? h("span", { class: "src-part", style: { background: partColor(partOf(m)) } }, partOf(m).id_label) : null),
```

   Den Wert-Span (`h("span", { class: "mval" }, m.caliper != null ? … : fmtValue(m)),`) ersetzen durch:

```js
        h("span", { class: "mval", title: m.data?.raw != null && Math.abs(m.data.raw - m.value) > 0.004 ? `Foto ${num(m.data.raw, 2)} mm × ${num(partOf(m)?.scale ?? 1, 3)}` : "" },
          m.caliper != null ? h("span", { title: `Foto: ${fmtValue(m)}` }, `${m.kind === "diameter" ? "Ø " : ""}${num(m.caliper, 2)} mm`) : fmtValue(m),
          m.data?.nominal != null && Math.abs(m.data.nominal - (m.caliper ?? m.value)) > 0.004 ? h("span", { class: "xs muted" }, ` ≈ ${num(m.data.nominal, m.data.nominal % 1 ? 1 : 0)}`) : null),
```

   Nach dem `msub`-Span einfügen:

```js
        m.data?.ref_warn || m.data?.warn ? h("span", { class: "msub", style: { color: "var(--warn)" } }, m.data.ref_warn || m.data.warn) : null,
```

18. `editPanel(m)`: vor `const panel = h("div", { class: "medit", …` einfügen:

```js
    const allParts = S.project.parts || [];
    const own = allParts.find(p => p.id === m.part_id);
    const autoOk = m.source !== "manual" && (m.data?.view || "top") === "top" && m.kind !== "height";
    const partSel = m.source === "auto" ? null : h("select", { class: "input", "aria-label": "Teil", onchange: e => {
      const v = e.target.value; patch(m, { part_id: v === "auto" ? -1 : v === "none" ? null : Number(v) }); } },
      autoOk ? h("option", { value: "auto", selected: !m.data?.part_fixed }, "automatisch") : null,
      allParts.map(p => h("option", { value: String(p.id), selected: !!m.data?.part_fixed && m.part_id === p.id }, `${p.id_label} · ${p.label}`)),
      h("option", { value: "none", selected: (!!m.data?.part_fixed || !autoOk) && m.part_id == null }, "keins"));
    const refBox = m.caliper != null && own && ["length", "diameter", "radius"].includes(m.kind)
      ? h("label", { class: "check small" }, h("input", { type: "checkbox", checked: m.data?.ref !== false, onchange: e => patch(m, { ref: e.target.checked }) }), `Als Referenz für ${own.id_label}`) : null;
```

   Im `panel` nach der `grid2`-Zeile mit Wert/Unsicherheit/Messschieber einfügen:

```js
      own && m.caliper == null && ["length", "diameter", "radius"].includes(m.kind) ? h("span", { class: "xs muted" }, `Messschieber-Wert wird zur Referenz für ${own.id_label} – alle Maße des Teils werden angepasst`) : null,
      refBox,
      partSel ? h("div", { class: "field" }, h("label", {}, "Teil"), partSel) : h("span", { class: "xs muted" }, `Gehört automatisch zu ${own ? own.id_label : "einem Teil"}`),
```

19. `detectEdges` als neue Funktion vor `async function suggest()`:

```js
  async function detectEdges() {
    if (!src || src.view !== "top") { toast("Kanten lassen sich nur auf einer Draufsicht erkennen", "err"); return; }
    if ((S.project.parts || []).some(p => p.photo_id === src.photo.id) &&
      !await confirmDlg("Kanten neu erkennen?", "Teile dieses Fotos werden neu erkannt. Wiedergefundene Teile behalten Bezeichnung und Messschieber-Referenzen.", "Neu erkennen")) return;
    const old = [...edgeBtn.childNodes], phid = src.photo.id;
    clear(edgeBtn, h("span", { class: "spin" }), "Kanten werden erkannt …"); edgeBtn.disabled = true;
    try {
      const r = await api(`/api/photos/${phid}/edges`, { method: "POST", body: { use_ai: true } });
      await reloadProject();
      if (src?.photo.id === phid) { layer.setSegments(r.segments); setTool("edges"); }
      renderList(); dirty = true;
      toast(r.notice || `${r.parts.length} Teil${r.parts.length === 1 ? "" : "e"} erkannt`, r.notice ? "" : "ok");
    } catch (e) { fail(e); } finally { clear(edgeBtn, ...old); edgeBtn.disabled = false; }
  }
```

- [ ] **Step 4: Syntax und Smoke**

Run: `for f in web/static/js/*.js; do node --check "$f" || exit 1; done && /root/Snap2CAD-venv/bin/pytest -q tests/test_texts.py tests/test_api.py`
Expected: keine Syntaxfehler, Tests grün. Der Text-Test ist wichtig: In den neuen Texten darf „Claude“ nicht vorkommen.

- [ ] **Step 5: Commit**

```bash
git add web/static/js/edges.js web/static/js/measure.js web/static/js/lib.js web/static/css/app.css
git commit -m "Messen: Kanten erkennen, Teile zeichnen und bearbeiten, Teil-Zuordnung und Referenz"
```

---

### Task 9: Gesamtprüfung im Browser, Auslieferung

**Files:**
- Create (nur Scratchpad, nicht im Repo): Playwright-Skript

- [ ] **Step 1: Volle Suite und Lint**

Run: `cd /root/Snap2CAD && /root/Snap2CAD-venv/bin/pytest -q && /root/Snap2CAD-venv/bin/ruff check . && for f in web/static/js/*.js; do node --check "$f" || exit 1; done`
Expected: alle Tests grün. Danach in der Spec die Nachweis-Spalte der Abnahmekriterien an die echten Testdateien angleichen (siehe Global Constraints) und das mit committen.

- [ ] **Step 2: App lokal im Testmodus starten** (Hintergrund)

```bash
cd /root/Snap2CAD/web && DATA_DIR=$SCRATCH/data RUNS_DIR=$SCRATCH/runs AI_FAKE=1 SANDBOX_MODE=local \
  /root/Snap2CAD-venv/bin/uvicorn app.main:app --port 8765
```

`$SCRATCH` steht für das Scratchpad-Verzeichnis der Sitzung.

- [ ] **Step 3: Browser-Durchlauf** mit Playwright (`npm i playwright-core` im Scratchpad, Browser `/usr/bin/chromium` oder `~/.cache/ms-playwright/chromium-1243`). Im Skript:
  - Einrichtungsassistent durchlaufen und anmelden.
  - Projekt anlegen und ein synthetisches Foto Quader + Platte hochladen. Die Datei per `python -c` mit `tests/conftest.py:synthetic_photo(objects=…)` erzeugen.
  - Seite `/messen` öffnen, „Kanten erkennen“ anklicken, das Teil T1 muss im Seitenbereich „Teile“ erscheinen.
  - Werkzeug „Kanten“ wählen, T1 anklicken, einen Eckpunkt ziehen. Die Messungsliste muss sich aktualisieren.
  - Bei „… Länge“ den Messschieber-Wert eintragen und prüfen, dass sich „… Breite“ ändert.
  - `/cad` öffnen: Auswahl „Modell für“ vorhanden, „Grundlage für das Modell“ vorhanden, kein „Claude“ im Seitentext (`document.body.innerText`).
  - Kopfzeile ohne „Claude verbunden“.
  - Screenshots in das Scratchpad legen und ansehen.

  Gefundene Fehler mit `superpowers:systematic-debugging` beheben, Test ergänzen, committen.

- [ ] **Step 4: Push, Pull Request, CI auf dem Branch**

CI startet nur bei `pull_request`, bei Push auf `main` und bei `workflow_dispatch` (`ci.yml`). Ein reiner Branch-Push startet nichts.

```bash
git push -u origin kanten-und-teile
gh pr create --base main --head kanten-und-teile --title "Kanten, Teile und mitdenkende Bemaßung" --body-file $SCRATCH/pr.md
sha=$(git rev-parse HEAD)
until id=$(gh run list --workflow CI --commit "$sha" --event pull_request --json databaseId -q '.[0].databaseId') && [ -n "$id" ]; do sleep 10; done
gh run watch --exit-status "$id"
```

`pr.md` beschreibt den Inhalt in drei, vier Sätzen, ohne Claude-Nennung und ohne Co-Autor-Zeile. Expected: Lint, Tests, Trivy und Docker-Smoke grün. Bei Rot: Log mit `gh run view "$id" --log-failed`, beheben, committen, pushen, dieselbe Warteschleife mit dem neuen `sha`.

- [ ] **Step 5: Nach `main` mergen (Nutzerauftrag vom 14.10.2026: „direkt auf GitHub nach main mergen“)**

```bash
gh pr merge kanten-und-teile --merge --delete-branch
git checkout main && git pull --ff-only origin main
sha=$(git rev-parse main)
until id=$(gh run list --workflow CI --commit "$sha" --event push --json databaseId -q '.[0].databaseId') && [ -n "$id" ]; do sleep 10; done
gh run watch --exit-status "$id"
```

Expected: CI auf `main` grün, Image `ghcr.io/callmetechie/snap2cad:latest` mit Version `dev-<7 Zeichen von $sha>` veröffentlicht. Verweigert der Auto-Modus den Merge (Memory: „Merges darf Claude nicht selbst“), stoppen und den Nutzer bitten, den PR in GitHub zu mergen. Danach geht es mit der Warteschleife weiter.

- [ ] **Step 6: DS918+ aktualisieren**

Über SSH (Zugang siehe Memory `snap2cad-nas`) in `/volume1/docker/snap2cad`:

```bash
sudo -n /usr/local/bin/docker compose pull && sudo -n /usr/local/bin/docker compose up -d
sudo -n /usr/local/bin/docker compose ps
sudo -n /usr/local/bin/docker compose exec -T app printenv SNAP2CAD_VERSION
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8097/api/me
```

Expected: beide Dienste laufen (app healthy), `SNAP2CAD_VERSION` = `dev-$(git rev-parse --short=7 main)`, HTTP 200. Die eigene Compose-Datei auf der NAS wird nie durch die aus dem Repo ersetzt (kein `cpus:`, kein `build:`).

- [ ] **Step 7: A8 vermerken**

Der Nutzer probiert mit einem echten Foto Quader + Platte. Die Dauer eines Erkennungslaufs wird notiert. Richtwert: Mit `use_ai:false` dauert eine Erkennung auf der DS918+ unter 10 s. Liegt sie darüber, ist `WORK_PXMM` 3 statt 4 eine Folgeaufgabe, kein Stopp. Ergebnis und neuer Stand in die Memory `snap2cad-nas` schreiben.
