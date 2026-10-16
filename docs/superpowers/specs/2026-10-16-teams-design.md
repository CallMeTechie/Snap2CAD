# Teams mit gemeinsamen Bibliotheken – Design

Stand 16.10.2026. Vorgänger: Projektbibliothek (PR #9, main c408b93).

## Ziel

Jeder Benutzer hat eine **private Bibliothek** (wie heute). Zusätzlich gibt es **Teams**: Jedes Team hat eine
**Team-Bibliothek**, deren Projekte – mit Fotos, Messungen, Teilen, Werkstück-Angaben, gelernten Messschieberwerten und
CAD-Aufträgen – alle Mitglieder gemeinsam nutzen. Ein Benutzer kann in mehreren Teams sein.

Nutzerentscheidungen (Marc, 16.10.2026):
- Jeder Benutzer kann Teams gründen; der Gründer wird Leiter.
- Rollen: **Leiter / Mitglied / Lesend**.
- Aufnahme per **Einladung mit Annahme** (Einladung über den exakten Benutzernamen; keine für alle sichtbare Benutzerliste).
- Mitglieder löschen und verschieben **nur selbst angelegte** Projekte; Leiter jedes Projekt; Lesend nichts.
- Projekte kommen ins Team durch **Anlegen im Team, Verschieben und Kopieren**; Kopieren nimmt **alles inklusive der
  aktuellen Version jedes CAD-Auftrags** mit.
- Verlässt ein Mitglied das Team oder wird es gelöscht, **bleiben seine Team-Projekte im Team**.
- Der **Administrator** sieht alle Teams und kann eingreifen (Leiter ernennen, Mitglieder entfernen, Teams löschen –
  **auch mit Inhalt**, nach deutlicher Rückfrage); auf Inhalte einer Team-Bibliothek greift er nur als Mitglied zu.

## Begriffe

- **Bereich** einer Bibliothek: `privat` (Besitzer = Ersteller) oder `team:<id>`.
- **Ersteller** eines Projekts/Auftrags: `projects.user_id` bzw. `jobs.user_id` (künftig nullable; leer = gelöschter Benutzer).
- **Auslöser** einer Version: der Benutzer, der sie erzeugt hat (`job_versions.user_id`).

## §1 Datenmodell

Neue Tabellen (in `db.SCHEMA`, `CREATE TABLE IF NOT EXISTS`):

```sql
CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS team_members (
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('leiter','mitglied','lesend')), joined_at TEXT NOT NULL,
  PRIMARY KEY (team_id, user_id));
CREATE TABLE IF NOT EXISTS team_invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('leiter','mitglied','lesend')),
  invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen','angenommen','abgelehnt','zurueckgezogen')),
  decided_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_team_invite_open ON team_invites(team_id, user_id) WHERE status='offen';
CREATE INDEX IF NOT EXISTS ix_team_members_user ON team_members(user_id);
```

Geänderte Tabellen (Migration in `db._migrate`, einmalig, erkennbar an der fehlenden Spalte `projects.team_id`):
- `projects`: neue Spalte `team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE` (leer = privat); `user_id` wird
  **nullable** mit `ON DELETE SET NULL`.
- `jobs`: `user_id` wird **nullable** mit `ON DELETE SET NULL`.
- `job_versions`: neue Spalte `user_id INTEGER REFERENCES users(id) ON DELETE SET NULL` (Auslöser; Altbestand leer).
- Weil SQLite Fremdschlüssel nicht ändern kann, werden `projects` und `jobs` nach dem SQLite-Verfahren neu aufgebaut
  (`PRAGMA foreign_keys=OFF`, `BEGIN`, neue Tabelle `*_new` mit allen bisherigen Spalten in gleicher Reihenfolge plus
  den Änderungen, `INSERT … SELECT`, `DROP`, `ALTER TABLE … RENAME`, Indizes neu, `PRAGMA foreign_key_check` leer,
  `COMMIT`, `PRAGMA foreign_keys=ON`). Alle Daten bleiben unverändert; alle bestehenden Projekte sind danach privat.
- Indizes: `ix_projects_team ON projects(team_id)`, `ix_projects_user ON projects(user_id)`; bestehende Job-Indizes
  (`ix_jobs_user`, `ix_jobs_project`) werden nach dem Neuaufbau neu angelegt.
- Vor der Migration legt der Server keine eigene Sicherung an; die Auslieferung sichert das Volume (siehe Auslieferung).

## §2 Rechte (neues Modul `web/app/access.py`)

Eine Stelle entscheidet über alle Zugriffe:

```python
ROLE_RANK = {"lesend": 1, "mitglied": 2, "leiter": 3}
def project_role(user, project) -> str | None   # "besitzer" | "leiter" | "mitglied" | "lesend" | "admin" | None
def require_project(user, project_id, need: str) -> dict   # need: "read" | "write" | "delete" | "move" | "manage"
def require_job(user, job_id, need: str) -> dict
def team_role(user_id, team_id) -> str | None
```

| Recht | privat: Ersteller | privat: Admin | Team: Leiter | Team: Mitglied | Team: Lesend | Admin ohne Mitgliedschaft |
|---|---|---|---|---|---|---|
| `read` (ansehen, Dateien, CSV, Modellbild) | ✓ | ✓ (wie heute) | ✓ | ✓ | ✓ | – |
| `write` (Fotos, Messen, Kanten, Werkstück, KI, CAD, Neuaufbau, Werte am Modell, Umbenennen, Archivieren) | ✓ | ✓ (wie heute) | ✓ | ✓ | – | – |
| `delete` Projekt | ✓ | ✓ | ✓ | nur selbst angelegte | – | – |
| `move` (privat ↔ Team) | ✓ | – | ✓ | nur selbst angelegte | – | – |
| Kopieren aus diesem Projekt | ✓ | – | ✓ | ✓ | – | – |

- Kein `read` → **404** („Projekt nicht gefunden“ / „Auftrag nicht gefunden“), damit fremde Projekte nicht erkennbar sind.
  `read`, aber nicht das nötige Recht → **403** „Nur lesender Zugriff“ bzw. „Nur der Ersteller oder ein Team-Leiter darf
  das“.
- **Aufträge** folgen ihrem Projekt (`jobs.project_id`). Aufträge ohne Projekt (Projekt gelöscht) gehören nur dem
  Ersteller (und dem Admin wie heute). Einen Auftrag dürfen alle mit `write` am Projekt fortsetzen, abbrechen,
  parametrisch ändern; **löschen** darf ihn der Ersteller, ein Leiter oder der Besitzer des privaten Projekts.
- `_own_project`, `_own_photo`, `_own_meas`, `_own_part`, `_own_job` in `main.py` werden auf `access.require_*` mit dem
  passenden `need` umgestellt; jede Route bekommt genau ein `need` (Liste im Plan). Lesende Routen (GET, Dateien, CSV,
  ZIP, Modellbild) = `read`; ändernde = `write`; `DELETE /api/projects/{pid}` = `delete`.
- Aktionen in `jobs.create/iterate/param`: Kontingent und Grenzen gelten für den **Auslöser** (siehe §6).

## §3 Teams verwalten (alle Benutzer)

Routen (alle angemeldet, CSRF wie üblich):
- `GET /api/teams` → meine Teams mit Rolle, Mitgliederzahl, Projektzahl; dazu `invites`: meine offenen Einladungen.
- `POST /api/teams {name}` → Team anlegen, Anlegender wird `leiter`. Name 1–80 Zeichen, getrimmt.
- `GET /api/teams/{tid}` (Mitglied) → Team mit Mitgliedern (`user_id, username, display_name, role, joined_at`) und – für
  Leiter – offenen Einladungen.
- `PATCH /api/teams/{tid} {name}` (Leiter).
- `POST /api/teams/{tid}/invites {username, role}` (Leiter): Benutzer per **exaktem Benutzernamen** (Groß/klein egal);
  unbekannt oder deaktiviert → 404 „Benutzer nicht gefunden“ (gleiche Meldung für beide Fälle); sich selbst → 400;
  schon Mitglied → 409; offene Einladung → 409; höchstens 20 Einladungen je Leiter und Stunde (429), damit Benutzernamen
  nicht durchprobiert werden. Audit `team_invite`.
- `DELETE /api/teams/{tid}/invites/{iid}` (Leiter) → `zurueckgezogen`.
- `POST /api/team-invites/{iid}/accept` | `/decline` (nur der Eingeladene) → Mitglied mit der eingeladenen Rolle bzw.
  `abgelehnt`. Audit.
- `PATCH /api/teams/{tid}/members/{uid} {role}` (Leiter) – der letzte Leiter kann sich nicht herabstufen (409).
- `DELETE /api/teams/{tid}/members/{uid}` (Leiter: andere entfernen; jeder: sich selbst = austreten) – der letzte Leiter
  kann nicht austreten, solange andere Mitglieder da sind (409 „Erst einen anderen Leiter bestimmen“); ist er das letzte
  Mitglied, muss das Team leer sein und wird beim Austritt gelöscht, sonst 409.
- `DELETE /api/teams/{tid}` (Leiter): nur ohne Projekte (409 „Das Team hat noch n Projekte“).
- Team-Projekte bleiben beim Austritt im Team; der Ersteller bleibt gespeichert und wird als „ehemaliges Mitglied“
  angezeigt, wenn er nicht mehr Mitglied ist.

## §4 Projekte anlegen, verschieben, kopieren

- `POST /api/projects {name, team_id?}`: mit `team_id` nur als Leiter/Mitglied dieses Teams (sonst 403/404).
- `GET /api/projects?scope=private|team:<id>|all`: Standard `private`; `team:<id>` nur für Mitglieder; `all` liefert
  private und alle Team-Projekte des Benutzers. Jedes Projekt trägt zusätzlich `team_id`, `team_name`, `my_role`,
  `creator` (`{id, name}` oder `null` = gelöschter Benutzer) und `creator_is_member` (bei Team-Projekten).
- `GET /api/projects/current`: bleibt privat (legt bei leerem Konto ein privates Projekt an wie heute).
- `POST /api/projects/{pid}/move {team_id | null}`: Recht `move` am Projekt; Ziel-Team: Leiter/Mitglied. Verschiebt das
  Projekt **samt seinen Aufträgen** (Aufträge folgen dem Projekt). In privat verschieben setzt `team_id = NULL`; das
  Projekt gehört danach dem Verschiebenden (`user_id` = er) – erlaubt nur, wenn er Ersteller oder Leiter ist. Audit.
- `POST /api/projects/{pid}/copy {team_id | null, name?}`: Recht „Kopieren“ (siehe §2) am Quellprojekt und Leiter/
  Mitglied im Ziel-Team bzw. eigener privater Bereich. Kopiert in einem Lauf:
  - Projektzeile (Name „<Name> (Kopie)“ oder angegeben, Werkstück-Felder, Kontrollmaß, `cad_check` nicht).
  - Fotos samt Ordnerinhalt (`orig/overlay/rect/gauge/thumb`, `edges.json`, `align.jpg` falls vorhanden) mit neuen ids;
    `analysis` übernommen, Verweise auf Foto-ids (z. B. `bottom_align.top_photo_id`) auf die neuen ids umgeschrieben.
  - Teile (neue ids, `photo_id` umgeschrieben, `same_as` auf neue Teil-ids umgeschrieben).
  - Messungen (neue ids, `photo_id`/`part_id` umgeschrieben, `seq` gleich).
  - Gelernte Werte (`model_dims`, `job_id`/`dim_id` – `job_id` auf den neuen Auftrag umgeschrieben, falls mitkopiert).
  - Je CAD-Auftrag des Projekts mit gültiger aktueller Version: neuer Auftrag (Ersteller = Kopierender, gleicher Name,
    `messages` gekürzt auf die erste Nutzernachricht der Quelle), **eine** Version 1 mit `trigger='copy'`, `code`,
    `meta`, `result`, `checks`, Status `ok`, Dateien des Versionsordners kopiert (inkl. `preview.png`, falls vorhanden),
    `current_version = 1`, Status `done`. Kein KI-Aufruf, kein Kontingent.
  - Dateikopien geschehen vor dem Datenbankeintrag in einen temporären Ordner und werden erst nach dem Commit an ihren
    Platz verschoben; bei Fehlern wird alles Angelegte wieder entfernt. Grenze: Projekte mit mehr als 200 Fotos → 413.
  - Antwort: das neue Projekt. Audit `project_copy`.
- Löschen eines Team-Projekts löscht wie heute Fotos/Messungen/Teile/Werte; Aufträge bleiben mit `project_id = NULL` beim
  jeweiligen Ersteller (wie heute bei privaten Projekten).

## §5 Admin

- Reiter **„Teams“** in der Benutzerverwaltung: Liste aller Teams (Name, Leiter, Mitglieder, Projektzahl, angelegt),
  Kennzeichen „ohne Leiter“. Je Team: Mitglieder mit Rollen; Rolle setzen (auch Leiter ernennen), Mitglied entfernen,
  Einladungen zurückziehen, **Team löschen** – auch mit Projekten nach Rückfrage mit Eingabe des Teamnamens; dabei werden
  die Projekte wie beim Projekt-Löschen entfernt (Fotos, Messungen, Teile, Werte; Aufträge bleiben bei ihren Erstellern
  ohne Projekt). Audit `team_deleted` mit Projektzahl.
- Routen unter `/api/admin/teams…` mit `require_admin`; Inhalte der Team-Projekte sind dort nicht abrufbar.
- **Benutzer löschen** (`admin_user_delete`): private Projekte und Aufträge ohne Team wie heute löschen; **Team-Projekte
  und Aufträge in Team-Projekten bleiben** (Ersteller wird leer); Mitgliedschaften und Einladungen entfallen per Kaskade.
  War er letzter Leiter eines Teams mit weiteren Mitgliedern, wird das älteste verbleibende Mitglied Leiter (Audit).
  Die Bestätigung nennt die Zahl der Team-Projekte, die bleiben.

## §6 Kontingente und Grenzen

- `job_versions.user_id` = Auslöser; `jobs.create/_iterate_locked/param` und die Kopie setzen ihn.
- `auth.usage_this_month(user_id)` zählt Versionen mit `trigger IN ('create','iterate')` und
  `COALESCE(v.user_id, j.user_id) = ?`.
- Neuaufbau-Grenzen (`_param_limits`): laufend und je Stunde ebenfalls über `COALESCE(v.user_id, j.user_id)`.
- Laufende Aufträge je Nutzer (`create`, max. 3): weiter über `jobs.user_id` (Ersteller) – unverändert.
- KI-Tageskontingent (`_ai_uses_today`, Audit-basiert): unverändert beim Auslöser.

## §7 Oberfläche

- **Bibliothek** (`library.js`): Umschalter oben „Privat · <Team A> · <Team B>“ (Chips; Wahl in `localStorage
  lib.scope`), daneben Link „Teams verwalten“. „Neues Projekt“ legt im gewählten Bereich an. Team-Karten zeigen
  „von <Ersteller>“ bzw. „von ehemaligem Mitglied“, dazu die eigene Rolle als Abzeichen, wenn „Lesend“. Menü „…“:
  Umbenennen/Archivieren (write), „In Team verschieben…“/„In privat verschieben“ (move), „In Team kopieren…“/„In privat
  kopieren“ (Kopieren), Löschen (delete) – nicht erlaubte Einträge fehlen. Dialoge mit Teamauswahl.
- **Projektauswahl** (`projectPicker`): `<optgroup>` „Privat“ und je Team; Projekte aus `scope=all`.
- **Rolle Lesend**: Auf Fotos/Messen/CAD steht oben ein Hinweis „Nur ansehen – Rolle Lesend im Team <Name>“;
  Upload, Werkzeuge außer Verschieben, Bearbeiten-Knöpfe, KI-Knöpfe, „CAD-Modell erzeugen“, Wert-Eingaben im Viewer und
  Löschen sind deaktiviert. Der Server lehnt trotzdem alles mit 403 ab (die Oberfläche ist nur Komfort).
- **Teams** (`/teams`, neue Seite `teams.js`, Link im Benutzermenü und in der Bibliothek): meine Teams (Rolle,
  Mitglieder, Projekte), „Team gründen“; je Team: Mitgliederliste, Einladen (Benutzername + Rolle), Rollen ändern,
  entfernen, umbenennen, austreten, löschen (leer); oben „Einladungen für dich“ mit Annehmen/Ablehnen.
- **Kopfzeile**: Bei offenen Einladungen ein Abzeichen am Benutzermenü und ein Eintrag „Team-Einladungen (n)“.
- **Meine Aufträge**: Filter „Meine · <Team A> · …“; Team-Aufträge zeigen den Ersteller.
- **Anleitung**: neuer Abschnitt `teams` (Bereiche, Rollen-Tabelle, Einladen, Verschieben/Kopieren, Austritt);
  Kurzhilfe unverändert.

## §8 Fehlerfälle und Grenzen

- Konkurrierende Bearbeitung im Team: wie heute (letzte Änderung gewinnt; Aufträge sind per `jobs._lock` geschützt;
  parametrischer Neuaufbau mit `base`-Prüfung → 409 bei veralteter Version).
- Verschieben während ein Auftrag des Projekts läuft: erlaubt (Auftrag folgt dem Projekt, Rechte gelten ab sofort).
- Kopieren während ein Auftrag läuft: kopiert die aktuelle gültige Version; laufende Versionen nicht.
- Benutzer verliert die Mitgliedschaft, während er eine Seite offen hat: nächste Anfrage → 404; die Oberfläche zeigt die
  Meldung und führt zur Bibliothek.
- Team ohne Leiter (nur durch Benutzer-Löschen ohne verbleibende Mitglieder möglich, oder Admin-Eingriff): im Admin-
  Reiter gekennzeichnet; Admin kann einen Leiter ernennen, sobald es Mitglieder gibt, oder das Team löschen.
- Namen von Teams sind nicht eindeutig; Anzeige immer mit Teamname, interne Zuordnung über id.
- Ein Benutzer sieht von anderen Benutzern nur Benutzername und Anzeigename von Mitgliedern seiner Teams und von
  Erstellern in seinen Team-Bibliotheken.

## §9 Nicht im Umfang

Projekt-Freigabe an Einzelpersonen außerhalb eines Teams; Team-eigene Kontingente; Benachrichtigungen per E-Mail;
gleichzeitiges Bearbeiten mit Live-Aktualisierung; Teams verschachteln; Verschieben/Kopieren zwischen zwei Teams in einem
Schritt (geht über „in privat kopieren“ und „in Team kopieren“).

## §10 Abnahme

| Nr. | Prüfung | Nachweis |
|---|---|---|
| T1 | Migration auf einer Kopie der Bestandsdatenbank (Schema main c408b93 mit Projekten, Fotos, Aufträgen, Versionen, Teilen, Messungen, Werten): alle Zeilen und Fremdschlüssel unverändert, `foreign_key_check` leer, alle Projekte privat, zweiter Start ändert nichts | `pytest tests/test_teams.py -k migration` |
| T2 | Rechte-Matrix §2: für Besitzer, Admin, Leiter, Mitglied (selbst/fremd angelegt), Lesend, Außenstehender gegen jede Projekt-, Foto-, Mess-, Teil-, Auftrags- und Datei-Route der erwartete Status (200/403/404) | `pytest tests/test_teams.py -k rechte` (parametrisiert über alle Routen) |
| T3 | Teams: anlegen, einladen (unbekannt/doppelt/schon Mitglied), annehmen/ablehnen/zurückziehen, Rollen, letzter Leiter, austreten, löschen (leer/nicht leer) | `pytest tests/test_teams.py -k team` |
| T4 | Verschieben privat ↔ Team mit Aufträgen; Rechte; Audit | `pytest tests/test_teams.py -k verschieben` |
| T5 | Kopieren: alle Bestandteile mit umgeschriebenen ids, Dateien vorhanden, Auftrag mit Version `copy` ok und Modellbild, Quelle unverändert, Fehler beim Kopieren hinterlässt nichts | `pytest tests/test_teams.py -k kopieren` |
| T6 | Kontingent und Neuaufbau-Grenzen beim Auslöser; Altversionen zählen beim Ersteller | `pytest tests/test_teams.py -k kontingent` |
| T7 | Benutzer löschen: private Daten weg, Team-Projekte und deren Aufträge bleiben, Ersteller leer, Leiter-Nachfolge | `pytest tests/test_teams.py -k benutzer` |
| T8 | Admin-Reiter: Liste, Rollen, Entfernen, Team mit Projekten löschen nach Rückfrage | `pytest tests/test_teams.py -k admin` + Browser |
| T9 | Browser-Durchlauf mit drei Benutzern (Leiter, Mitglied, Lesend): Team gründen, einladen, annehmen, Projekt im Team anlegen, Mitglied misst und erzeugt CAD, Lesend sieht alles ohne Bearbeiten, Verschieben/Kopieren, Austritt; Konsole ohne Fehler | Playwright im Scratchpad |
| T10 | Bestehende Suite unverändert grün (private Abläufe) | volle Suite |

## Auslieferung

Branch `teams` → PR → CI grün → Merge → CI auf `main` → DS918+: **Sicherung des Volumes bei gestoppten Containern**
(`backup-data-<datum>-<n>.tgz`), `compose pull && up -d` (Migration läuft beim Start), Gesundheit, Kontrolle per Skript
im Container: Zeilenzahlen von `projects`, `photos`, `jobs`, `job_versions` vor/nach gleich, `foreign_key_check` leer.
