# Snap2CAD – Bauteile per Foto vermessen und als STEP/STL nachbauen

[![CI](https://github.com/CallMeTechie/Snap2CAD/actions/workflows/ci.yml/badge.svg)](https://github.com/CallMeTechie/Snap2CAD/actions/workflows/ci.yml)
[![Image](https://img.shields.io/badge/image-ghcr.io%2Fcallmetechie%2Fsnap2cad-blue)](https://github.com/CallMeTechie/Snap2CAD/pkgs/container/snap2cad)

**Snap2CAD** besteht aus einer druckbaren Messunterlage mit mm-Raster und ArUco-Markern. Du legst ein Bauteil darauf, fotografierst es mit dem Handy, und eine KI (oder das mitgelieferte Skript) entzerrt das Foto auf die Tischebene und misst die Konturen in Millimetern. Ein fertiger Prompt – oder die mitgelieferte Web-App mit Claude – führt anschließend vom Messergebnis zum parametrischen CAD-Modell mit **STEP- und STL-Export** für 3D-Druck oder CNC-Fräsen.

> **English summary:** Snap2CAD is a printable measuring mat (A4/A3) with a 1 mm grid and ArUco markers. Photograph a part on it, and an AI with code execution (or the included script) rectifies the photo to true scale and measures it. A ready-made prompt – or the included self-hosted web app with Claude – then turns the measurements into a parametric CAD model exported as STEP and STL. The prompt and documentation are in German.

<p align="center">
  <img src="docs/preview_a4.png" alt="Messunterlage A4 mit Raster und Markern" width="360">
  &nbsp;&nbsp;
  <img src="docs/preview_hoehenlehre.png" alt="Höhenlehre zum Aufstellen" width="360">
</p>

## Inhalt

| Datei | Zweck |
|---|---|
| [`pdf/Messunterlage_A4.pdf`](pdf/Messunterlage_A4.pdf) | Messfeld 190 × 230 mm, Höhenlehre bis 220 mm, Anleitung |
| [`pdf/Messunterlage_A3.pdf`](pdf/Messunterlage_A3.pdf) | Messfeld 270 × 360 mm, Höhenlehre bis 340 mm, Anleitung |
| [`pdf/Messunterlage_K60.pdf`](pdf/Messunterlage_K60.pdf) | Kleinteile: Feld 60 × 80 mm ohne Raster, Blatt hell und Blatt dunkel, Anleitung |
| [`PROMPT.md`](PROMPT.md) | Prompt für KI-Sessions: Vermessung → Maßtabelle → CAD → STEP/STL |
| [`tools/check_photo.py`](tools/check_photo.py) | Prüft ein Foto (Marker, Restfehler) und erzeugt eine maßstäbliche Draufsicht |
| [`generator/make_mat.py`](generator/make_mat.py) | Erzeugt die PDFs neu, z. B. nach eigenen Anpassungen |
| [`docs/marker_layout.json`](docs/marker_layout.json) | Maschinenlesbare Markerpositionen für alle Formate |
| [`web/`](web/), [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | Web-App: Unterlage erzeugen, Fotos prüfen, im Browser messen, CAD mit Claude ([siehe unten](#web-app-docker)) |

Jedes PDF hat drei Seiten: Messunterlage, Höhenlehre zum Ausschneiden und eine Kurzanleitung.

## So funktioniert's

Die acht Marker sitzen an bekannten Positionen. Aus ihren Ecken im Foto wird eine Homographie berechnet, also die perspektivische Abbildung vom Foto auf die Tischebene. Damit lässt sich jedes Foto auf eine maßstabsgetreue Draufsicht zurückrechnen, auch wenn es leicht schräg aufgenommen wurde. Vier sichtbare Marker reichen, acht machen das Ergebnis robuster, falls das Bauteil einen Marker verdeckt.

In der Web-App gibt es dazu drei Ergänzungen. Beim Hochladen lässt sich die Fotoart „Von unten“ wählen: Die Unteransicht wird am Umriss an der Draufsicht ausgerichtet, und die erkannte Lage lässt sich von Hand korrigieren. Vor dem CAD-Auftrag prüft ein Prüfkasten die Fotos und Maße, stellt Rückfragen oder fordert fehlende Fotos an; wer trotzdem weitermachen will, wählt „Trotzdem erzeugen“. Im Kasten „Werkstück“ lassen sich Farbe, Material und Transparenz angeben, und diese Handeingaben steuern die Kantenerkennung.

Im 3D-Viewer eines Auftrags stehen die Maße des Modells als Bemaßungslinien, gruppenweise ein- und ausschaltbar (Außenmaße, Bohrungen, Tiefen, Fasen, Platten, Sonstige, Annahmen). Ein Klick auf ein Maß nimmt einen Messschieberwert an: Das Modell wird sofort ohne KI neu gebaut, der Wert gilt als „Messschieber am Modell“ für das ganze Projekt, und „Schlüsse ziehen“ lässt die KI die abhängigen Maße daraus ableiten. Die Liste der gemerkten Werte steht auf der Messseite und lässt sich dort löschen.

Jedes Konto hat eine private Projektbibliothek; Teams teilen zusätzlich eine gemeinsame. Wer ein Team gründet, wird Leiter und lädt andere über ihren Benutzernamen ein (Rollen Leiter, Mitglied, Lesend; die Eingeladenen nehmen unter „Teams“ an). Projekte kommen durch Anlegen im Team, Verschieben oder Kopieren hinein; eine Kopie nimmt Fotos, Maße, Teile, gemerkte Werte und von jedem CAD-Auftrag die aktuelle gültige Version mit. CAD-Läufe zählen beim Benutzer, der sie auslöst. Der Administrator verwaltet Teams im Reiter „Teams“ der Benutzerverwaltung, sieht deren Inhalte aber nur als Mitglied.

**Kleinteile:** Für Teile von wenigen Millimetern bis etwa 50 mm gibt es die Unterlage „Kleinteile“ (Feld 60 × 80 mm, Blatt hell und Blatt dunkel, Marker-IDs 20–27 bzw. 30–37). Snap2CAD erkennt das Blatt an den Markern, entzerrt mit 30 px/mm und skaliert die Kantenerkennung entsprechend; Kontrollmaß 50 mm. Fotografieren mit 2×/3×-Zoom aus 25–30 cm, kein Makro.

## Schnellstart

1. **Drucken** mit *100 % / Tatsächliche Größe*. Nicht „An Seite anpassen“.
2. **Kontrollmaß prüfen**: Die 100-mm-Skala unten links mit einem Stahllineal nachmessen und den Wert ins Feld unten rechts schreiben. Steht er mit auf dem Foto, wird eine Abweichung des Druckers herausgerechnet.
3. **Unterlage plan fixieren** (Klebeband an den Ecken) und das Bauteil mittig auflegen. Alle Marker frei lassen.
4. **Fotografieren**: senkrecht von oben, 50–70 cm Abstand, mit 2×- oder 3×-Zoom statt Weitwinkel. Für Höhen das Teil kippen und erneut von oben fotografieren, oder die Höhenlehre direkt neben das Objekt stellen (alle drei Marker im Bild) und von der Seite fotografieren.
5. **Auswerten**: in der [Web-App](#web-app-docker), mit [`PROMPT.md`](PROMPT.md) in einer KI mit Code-Ausführung, oder selbst prüfen:

```bash
pip install -r requirements.txt
python tools/check_photo.py foto.jpg            # Format A4/A3 wird erkannt, sonst --size A4
```

Das Skript meldet die erkannten Marker und den Restfehler je Marker und speichert `foto_entzerrt.jpg` mit 10 px/mm. Ursprung ist die untere linke Rasterecke. In dieser Draufsicht entspricht jeder Pixelabstand direkt einem Maß in mm. Ist eine Höhenlehre im Bild, entsteht zusätzlich `foto_entzerrt_hoehenlehre.jpg` (x = Mitte des Streifens, y = Höhe über dem Tisch).

## Genauigkeit

| Situation | Erwartbar |
|---|---|
| Flache Teile, Kanten liegen auf der Unterlage auf | ca. ±0,5 mm |
| Restfehler der Entzerrung (`check_photo.py`) | ≤ 0,5 mm gut · ≤ 1 mm brauchbar · darüber Foto wiederholen |
| Kanten oberhalb der Tischebene | Parallaxe, siehe unten |

**Parallaxe:** Die Entzerrung gilt exakt nur für die Tischebene. Was höher liegt, ist näher an der Kamera und erscheint größer. Faustregel:

> Fehler ≈ Maß × Höhe über Tisch ÷ Kameraabstand

Beispiel: Eine 100 mm breite Oberkante in 50 mm Höhe, fotografiert aus 500 mm, wirkt etwa 10 mm zu breit. Deshalb an der Auflagekante messen, aus größerem Abstand mit Zoom fotografieren oder das Teil kippen.

**Passungen** (Lagersitze, Wellen, Gewinde, Anschlussmaße) mit dem Messschieber nachmessen. Fotos liefern Geometrie und Lage, keine Passmaßgenauigkeit.

Getestet wurde die Erkennung an gerasterten PDFs und an künstlich schräg verzerrten, unscharfen Aufnahmen: Alle Marker wurden erkannt, der Restfehler lag bei maximal 0,4 mm. Erfahrungswerte mit echten Handyfotos sind als Issue oder Pull Request willkommen.

## Der Prompt

[`PROMPT.md`](PROMPT.md) enthält die komplette Spezifikation der Unterlage, damit eine KI ohne weiteres Vorwissen korrekt rechnet. Der Ablauf hat zwei Stufen:

- **Teil A – Vermessung:** Marker erkennen, entzerren, messen, Maßtabelle mit Unsicherheiten. Danach stoppt die KI und lässt die Maße bestätigen.
- **Teil B – CAD:** parametrisches Modell mit [build123d](https://github.com/gumyr/build123d) (oder CadQuery), fertigungsgerechte Regeln für FDM bzw. CNC, Export als STEP und STL, Pflichtprüfung (STEP-Re-Import, wasserdichtes STL, Abgleich mit dem Foto).

Der Prompt setzt eine KI mit Python-Ausführung voraus. Ohne Code-Ausführung bleibt es bei Schätzwerten vom Raster.

## Spezifikation

- Marker: ArUco `DICT_4X4_50`, aufrecht gedruckt
- Koordinaten: mm, Ursprung untere linke Rasterecke, X nach rechts, Y nach oben

| Format | Raster | Markerkante | Marker-IDs |
|---|---|---|---|
| A4 | 190 × 230 mm | 20 mm | 0–7 |
| A3 | 270 × 360 mm | 25 mm | 0–7 |
| Höhenlehre | Streifen 45 mm breit, 0 = Falz | 18 mm | A: 10, 11, 14 · B: 12, 13, 15 |

Markermitten (X | Y in mm):

| ID | Position | A4 | A3 |
|---|---|---|---|
| 0 | unten links | 13 \| 13 | 15,5 \| 15,5 |
| 1 | unten rechts | 177 \| 13 | 254,5 \| 15,5 |
| 2 | oben rechts | 177 \| 217 | 254,5 \| 344,5 |
| 3 | oben links | 13 \| 217 | 15,5 \| 344,5 |
| 4 | unten Mitte | 95 \| 13 | 135 \| 15,5 |
| 5 | rechts Mitte | 177 \| 115 | 254,5 \| 180 |
| 6 | oben Mitte | 95 \| 217 | 135 \| 344,5 |
| 7 | links Mitte | 13 \| 115 | 15,5 \| 180 |

Höhenlehre, Markermitten über dem Falz (horizontal mittig): A4 – ID 10/12 auf 208 mm, ID 11/13 auf 180 mm, ID 14/15 auf 30 mm · A3 – ID 10/12 auf 328 mm, ID 11/13 auf 300 mm, ID 14/15 auf 30 mm.

Die Markerpositionen stehen zusätzlich klein unten auf jedem Blatt. Ein Foto ist damit auch ohne dieses Repo auswertbar.

## PDFs selbst erzeugen

```bash
pip install -r requirements.txt
python generator/make_mat.py pdf > docs/marker_layout.json
```

Formate, Markergröße, Farben und Texte stehen oben bzw. in den Funktionen `mat_page`, `strip_page` und `guide_page` des Skripts. Nach Änderungen an Markerpositionen auch `PROMPT.md` und diese README anpassen.

## Web-App (Docker)

Alles aus diesem Repo als selbst gehostete Web-Oberfläche: Unterlage als PDF erzeugen, Fotos hochladen und prüfen, im Browser messen und mit Claude ein CAD-Modell erzeugen lassen.

Startseite ist die Projektbibliothek: Jedes Werkstück ist ein Projekt mit Vorschaubild (3D-Modell, sonst erstes Foto), Zahl der Fotos und Maße und dem letzten CAD-Auftrag; Projekte lassen sich suchen, sortieren, umbenennen, archivieren und löschen. Die Anleitung (Fragezeichen oben rechts) erklärt den ganzen Ablauf, enthält den Generator für die Messunterlage und listet alle Tastenkürzel und Mausbefehle. Die Taste `?` oder `F1` zeigt auf jeder Seite die passenden Kürzel als Kurzhilfe (nicht, solange der Fokus in einem Eingabefeld liegt).

<p align="center">
  <img src="docs/webapp_messen.png" alt="Messen im Browser mit Vorschlägen von Claude" width="49%">
  <img src="docs/webapp_cad.png" alt="CAD-Ergebnis mit 3D-Ansicht, Downloads und Prüfung" width="49%">
</p>

| Schritt | Was passiert |
|---|---|
| 1 · Projekte | Projektbibliothek mit Vorschaubild, Suche, Sortierung, Archiv · Messunterlage als PDF (A4/A3, Seiten wählbar, Kopfzeile, Vorschau) in der Anleitung |
| 2 · Fotos prüfen | Marker-Erkennung, Restfehler je Marker, entzerrte Draufsicht und Höhenlehre, Kontrollmaß-Faktoren |
| 3 · Messen | Strecke, Kreis aus 3 Punkten, Punkt, Winkel, Höhe · Kantenfang, Lupe, Zoom · Messschieber-Werte, kritische Maße · Claude schlägt zusätzlich Maße aus dem Foto vor |
| 4 · CAD mit Claude | Claude schreibt build123d-Code, eine Sandbox erzeugt STEP und STL, prüft sie und lässt Fehler automatisch korrigieren · 3D-Ansicht (drehen, zoomen, Schnitt), Foto-Abgleich, Änderungswünsche als neue Versionen, Download als ZIP |

### Starten

```bash
git clone https://github.com/CallMeTechie/snap2cad.git && cd snap2cad
cp .env.example .env          # optional anpassen (Port, Kontingente …)
echo "SECRET_KEY=$(openssl rand -base64 48)" >> .env   # verschlüsselt den API-Schlüssel in der Datenbank
docker compose up -d          # lädt das fertige Image ghcr.io/callmetechie/snap2cad:latest
```

Eigenen Build statt fertigem Image: `docker compose up -d --build`. Eine bestimmte Version: `SNAP2CAD_IMAGE=ghcr.io/callmetechie/snap2cad:0.1.0` in die `.env`. Updates: `docker compose pull && docker compose up -d`.

**Ersteinrichtung im Browser:** Beim ersten Aufruf von `http://localhost:8000` erscheint der Einrichtungsassistent. Dort legst du Benutzername und Passwort des Administrators fest und trägst den Anthropic-API-Schlüssel ein ([console.anthropic.com → API Keys](https://console.anthropic.com/settings/keys)). Der Schlüssel wird vor dem Speichern bei Anthropic geprüft. Erst wenn alles stimmt, wird das Admin-Konto angelegt. Es gibt kein Standardkonto und kein Passwort im Log.

- Die Einrichtung ist nur aus privaten Netzen möglich (LAN, VPN, Tailscale, Docker). Wer sie bewusst über das Internet erledigen will, setzt vorübergehend `SETUP_ALLOW_PUBLIC=1`. Die Seite verschwindet, sobald das erste Konto existiert.
- Schlüssel und Modell lassen sich später unter *Benutzerverwaltung → Einstellungen* ändern; Ersetzen oder Entfernen des Schlüssels verlangt das eigene Passwort. Alternativ als `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` in der `.env`; dann hat die Umgebungsvariable Vorrang und ist in der Oberfläche gesperrt.
- Mit `SECRET_KEY` in der `.env` (mindestens 32 Zeichen) wird der in der App hinterlegte Schlüssel verschlüsselt gespeichert. Ein schon gespeicherter Schlüssel wird beim nächsten Start nachträglich verschlüsselt. Der `SECRET_KEY` gehört zur Sicherung dazu, aber getrennt vom Daten-Volume. Fehlt er oder ist er falsch, ist die KI aus und die Verwaltung bittet um einen neuen Schlüssel.
- Für automatisierte Installationen (CI, Ansible) legt `ADMIN_INITIAL_PASSWORD` stattdessen ein Konto `admin` an, dessen Passwort beim ersten Login geändert werden muss.
- Admin-Passwort vergessen: `docker compose exec app python -m app.manage reset-link <benutzername>` erzeugt einen einmaligen Link zum Setzen eines neuen Passworts (`… manage users` listet die Konten).

Weitere Nutzer kommen nur per Einladungslink dazu (Benutzermenü → Benutzerverwaltung). Ohne API-Schlüssel funktionieren Unterlage, Fotos und Messen, nur die KI-Funktionen sind aus.

Der Port ist standardmäßig nur auf `127.0.0.1` gebunden. Für den Zugriff von außen einen Reverse-Proxy mit HTTPS davorsetzen (Caddy, Traefik, nginx, Synology-Reverse-Proxy) und `PUBLIC_URL` setzen, damit Einladungslinks stimmen. Auch mehrere Proxys hintereinander (z. B. Cloudflare → NAS) werden erkannt.

### Sicherheit

- **Konten:** Passwörter mit Argon2, mindestens 12 Zeichen, Prüfung gegen häufige Passwörter. Login-Sperre nach 5 Fehlversuchen für 15 Minuten. Sitzungen als HttpOnly-Cookie, CSRF-Schutz, strikte Content-Security-Policy. Einladungs- und Reset-Links sind einmalig und werden nur als Hash gespeichert. Protokoll aller sicherheitsrelevanten Ereignisse für Admins.
- **Kosten:** Der API-Schlüssel bleibt auf dem Server, wird in der Oberfläche nie wieder vollständig angezeigt und mit `SECRET_KEY` verschlüsselt gespeichert. Ohne Anmeldung verrät die App weder Version noch Modell. Jeder Nutzer hat ein monatliches Kontingent an CAD-Läufen (`DEFAULT_QUOTA`, pro Nutzer änderbar).
- **Sandbox:** Von Claude erzeugter Code läuft nie im Web-Container, sondern im Dienst `sandbox`: ohne Netzwerk, ohne Datenbank und ohne API-Schlüssel, schreibgeschütztes Dateisystem, jeder Lauf unter einer eigenen Benutzerkennung, mit Zeit-, Speicher- und Prozesslimits, seccomp-Filter (kein Programmstart, keine Sockets) und Python-Audit-Hook.

### Daten

Alles liegt im Docker-Volume `data` (SQLite-Datenbank, Fotos, CAD-Versionen). Sicherung: `docker compose stop && docker run --rm -v snap2cad_data:/d -v "$PWD":/b alpine tar czf /b/backup.tgz -C /d . && docker compose start`

Die Fotos, Maße und Beschreibungen eines CAD-Auftrags werden an die Anthropic-API übertragen. Das steht auch in der Oberfläche direkt am Knopf.

### Entwicklung ohne Docker

```bash
pip install -r web/requirements.txt && pip install --no-deps -r web/requirements-overrides.txt
cd web && npm ci && sh scripts/vendor.sh      # three.js und Schriften nach static/vendor
DATA_DIR=./data RUNS_DIR=./runs SANDBOX_MODE=local AI_FAKE=1 uvicorn app.main:app --reload
```

Tests:

```bash
pip install -r web/requirements.txt -r requirements-dev.txt
pip install --no-deps -r web/requirements-overrides.txt   # Sicherheitsupdates gegen zu enge Obergrenzen
ruff check . && pytest && node --test tests/js/*.test.mjs
```

`SANDBOX_MODE=local` führt den CAD-Code ohne Container-Trennung aus (nur Limits, seccomp und Audit-Hook) und ist nur für die Entwicklung gedacht. `AI_FAKE=1` liefert feste Testantworten statt echter API-Aufrufe.

### CI und Releases

Jeder Push und jeder Pull Request durchläuft [GitHub Actions](.github/workflows/ci.yml):

1. **Lint:** Ruff, JavaScript-Syntax und -Tests (Geometrie der Messfläche), Compose-Datei
2. **Tests:** pytest – PDF-Erzeugung, Marker-Erkennung an synthetischen Fotos, Messgeometrie, Anmeldung und Rechte, kompletter CAD-Ablauf im KI-Testmodus, Sandbox-Abwehr
3. **Trivy (Repo):** Abhängigkeiten, versehentlich eingecheckte Secrets und Dockerfile-Fehlkonfigurationen
4. **Docker:** Image bauen, **Trivy-Scan des Images** (Ergebnis zusätzlich im Reiter *Security* von GitHub), Stack starten, End-to-End-Auftrag über den Sandbox-Container, Ausbruchstests im Container

Behebbare Lücken der Stufe HIGH oder CRITICAL stoppen die Pipeline. Bewusst akzeptierte Befunde stehen mit Begründung in [`.trivyignore`](.trivyignore). Trivy läuft als per Digest festgenageltes Container-Image, nicht über `trivy-action` (deren Tags wurden im März 2026 kompromittiert).

Erst wenn alles grün ist, wird das Image nach `ghcr.io/callmetechie/snap2cad` geschoben: `latest` und `sha-…` von `main`, Versionstags (`1.2.3`, `1.2`) bei einem Git-Tag `v1.2.3`. Pull Requests bauen und testen nur.

## Tipps aus der Praxis

- Mattes Papier verwenden. Glanz und Blitz überstrahlen Marker.
- Die Unterlage auf eine Glasplatte oder einen festen Karton kleben. Welliges Papier ist die häufigste Fehlerquelle.
- Fotos als Originaldatei weitergeben. Messenger komprimieren und verschlechtern die Kantenerkennung.
- Dunkle Teile auf heller Unterlage sind ideal. Bei hellen oder glänzenden Teilen hilft seitliches, diffuses Licht für deutliche Kanten.

## Lizenz

- Code (`core/`, `generator/`, `tools/`, `web/`): MIT
- PDFs, Prompt und Dokumentation: CC BY 4.0

## Mitmachen

Issues und Pull Requests sind willkommen, besonders Messberichte mit echten Fotos (Soll/Ist-Vergleich), weitere Formate (Letter, A5) und Erfahrungen mit verschiedenen KI-Werkzeugen.
