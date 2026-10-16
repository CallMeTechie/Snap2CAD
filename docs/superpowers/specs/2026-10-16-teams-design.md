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
- Verschieben nach privat mit Aufträgen anderer Ersteller wird abgelehnt (409); Ersatzweg ist „In privat kopieren“.
- Bestehende Fremdschlüssel-Verstöße der Produktionsdatenbank werden bei der Migration geduldet, dürfen aber nicht
  zunehmen.

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
- `projects`: neue Spalte `team_id INTEGER REFERENCES teams(id)` (leer = privat; ohne ON-DELETE-Aktion: ein Team mit
  Projekten lässt sich auf Datenbankebene nicht löschen, Projekte werden vorher ausdrücklich samt Dateien entfernt);
  `user_id` wird **nullable** mit `ON DELETE SET NULL`.
- `jobs`: `user_id` wird **nullable** mit `ON DELETE SET NULL`.
- `job_versions`: neue Spalte `user_id INTEGER REFERENCES users(id) ON DELETE SET NULL` (Auslöser); die Migration
  füllt sie für den Altbestand in derselben Transaktion mit dem Ersteller (`UPDATE job_versions SET user_id=(SELECT
  user_id FROM jobs WHERE jobs.id=job_versions.job_id) WHERE user_id IS NULL`).
- Reihenfolge in `_migrate`: (a) die bisherigen Nachrüstungen (`measurements.part_id`, Werkstück-Spalten von
  `projects`). (b) Nur wenn `projects.team_id` fehlt, der Neuaufbau in **einer** Transaktion: `PRAGMA foreign_keys=OFF`
  (außerhalb einer Transaktion); `PRAGMA foreign_key_check` merken; die Einträge von `projects` und `jobs` in
  `sqlite_sequence` merken; `BEGIN`; je Tabelle `*_new` mit der **festen** neuen Definition (dieselbe DDL-Konstante wie
  in `SCHEMA`, Tabellenname ersetzt); `INSERT … SELECT` mit der Spaltenliste der alten Tabelle aus `PRAGMA table_info`
  (kennt die neue Tabelle eine alte Spalte nicht → Abbruch); `DROP`; `ALTER TABLE … RENAME`; für jede gemerkte Tabelle
  `DELETE FROM sqlite_sequence WHERE name=?` und `INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)` mit dem gemerkten
  Stand (ohne früheren Eintrag nichts schreiben; der Neuaufbau setzt den Stand sonst auf `MAX(id)` bzw. 0, und
  gelöschte ids würden wieder vergeben); `job_versions.user_id` anlegen und auffüllen; `ix_jobs_user`, `ix_jobs_project`
  neu; `PRAGMA foreign_key_check` – die Liste darf nicht länger sein als vorher (Vergleich über `table, rowid, parent`,
  nicht über `fkid`, das sich durch den neuen Fremdschlüssel verschiebt), sonst Abbruch –; `COMMIT`. Abbruch heißt
  `ROLLBACK` und `RuntimeError("Migration abgebrochen: …")`. (c) Im `finally`, also erst nach `COMMIT`/`ROLLBACK` (in
  einer offenen Transaktion ist das Pragma wirkungslos): `PRAGMA foreign_keys=ON`. (d) `CREATE INDEX IF NOT EXISTS
  ix_projects_team ON projects(team_id)` und `ix_projects_user ON projects(user_id)` bei **jedem** Start nach (b), damit
  auch neue Datenbanken sie bekommen (in `SCHEMA` würde `ix_projects_team` auf einer Bestandsdatenbank scheitern).
  `conn()` schließt die Verbindung bei einer Ausnahme aus `_migrate` und gibt die Ausnahme weiter; der Start bricht ab.
- In `db.SCHEMA` erhalten `projects`, `jobs` (mit `run_by`) und `job_versions` (mit `user_id`) die neue Form; auf neuen
  Datenbanken entfällt der Neuaufbau. Alle bestehenden Werte bleiben unverändert; alle bestehenden Projekte sind danach
  privat.
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

- Ist ein Admin Mitglied eines Teams, gilt für dessen Projekte seine Team-Rolle; `project_role` liefert `"admin"` nur
  für private Projekte anderer und für Aufträge ohne Projekt.
- Kein `read` → **404** („Projekt nicht gefunden“ / „Auftrag nicht gefunden“), damit fremde Projekte nicht erkennbar sind.
  `read`, aber nicht das nötige Recht → **403** „Nur lesender Zugriff“ bzw. „Nur der Ersteller oder ein Team-Leiter darf
  das“.
- **Aufträge** folgen ihrem Projekt (`jobs.project_id`). Aufträge ohne Projekt (Projekt gelöscht) gehören nur dem
  Ersteller (und dem Admin wie heute); Aufträge ohne Projekt und ohne Ersteller gibt es nicht (siehe §4 Löschen).
  `job_public` liefert `user_id` = `null` für gelöschte Ersteller; alle Auftragslisten verwenden `LEFT JOIN users`.
  „Meine Aufträge“ mit Team-Filter fragt über `jobs.project_id → projects.team_id` ab. Einen Auftrag dürfen alle mit
  `write` am Projekt fortsetzen, abbrechen, parametrisch ändern; **löschen** darf ihn der Ersteller, solange er
  `write` am Projekt hat, ein Leiter des Teams, der Besitzer des privaten Projekts und – bei Aufträgen ohne Projekt und
  in privaten Projekten – der Admin (wie heute). Die Rechteprüfung geschieht immer vor `jobs.delete` (das selbst nicht
  prüft); `admin_user_delete` ruft `jobs.delete` nur für die in §5 genannten Aufträge auf.
- `_own_project`, `_own_photo`, `_own_meas`, `_own_part`, `_own_job` in `main.py` werden auf `access.require_*` mit dem
  passenden `need` umgestellt; jede Route bekommt genau ein `need` (Liste im Plan). Lesende Routen (GET, Dateien, CSV,
  ZIP, Modellbild) = `read`; ändernde = `write`; `DELETE /api/projects/{pid}` = `delete`.
- Aktionen in `jobs.create/iterate/param`: Kontingent und Grenzen gelten für den **Auslöser** (siehe §6).

## §3 Teams verwalten (alle Benutzer)

Routen (alle angemeldet, CSRF wie üblich):
- `GET /api/teams` → meine Teams mit Rolle, Mitgliederzahl, Projektzahl; dazu `invites`: meine offenen Einladungen als
  `{id, team_id, team_name, role, invited_by_name, created_at}`; Mitglieder und Projekte des Teams sieht der Eingeladene
  erst nach der Annahme. Annehmen geschieht in einer Transaktion und nur bei Status `offen` (sonst 409 „Einladung nicht
  mehr offen“).
- `POST /api/teams {name}` → Team anlegen, Anlegender wird `leiter`. Name 1–80 Zeichen, getrimmt.
- `GET /api/teams/{tid}` (Mitglied) → Team mit Mitgliedern (`user_id, username, display_name, role, joined_at`) und – für
  Leiter – offenen Einladungen.
- `PATCH /api/teams/{tid} {name}` (Leiter).
- `POST /api/teams/{tid}/invites {username, role}` (Leiter): Benutzer per **exaktem Benutzernamen** (Groß/klein egal);
  unbekannt oder deaktiviert → 404 „Benutzer nicht gefunden“ (gleiche Meldung für beide Fälle); sich selbst → 400;
  schon Mitglied → 409; offene Einladung → 409; höchstens 20 Einladungsversuche je Benutzer (über alle seine Teams) und
  Stunde (429), gezählt über die Audit-Einträge `team_invite` und `team_invite_failed` der letzten Stunde (auch
  abgewiesene Versuche zählen), damit Benutzernamen nicht durchprobiert werden. Audit `team_invite`.
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
- Audit-Aktionen: `team_created`, `team_renamed`, `team_invite`, `team_invite_failed` (unbekannt, deaktiviert, doppelt,
  schon Mitglied), `team_invite_revoked`, `team_invite_accepted`, `team_invite_declined`, `team_role`,
  `team_member_removed`, `team_left`, `team_deleted`, `team_leader_auto`, `project_move`, `project_copy`. Die Texte
  nennen Team-id, Teamname, Projekt-id und Benutzernamen, keine Projektinhalte. Alle Namen kommen in `ACTIONS`
  (`app.js`).

## §4 Projekte anlegen, verschieben, kopieren

- `POST /api/projects {name, team_id?}`: mit `team_id` nur als Leiter/Mitglied dieses Teams (sonst 403/404).
- `GET /api/projects?scope=private|team:<id>|all`: Standard `private` (`WHERE user_id=? AND team_id IS NULL`); `team:<id>` nur für Mitglieder;
  `all` liefert private und alle Team-Projekte des Benutzers. Jedes Projekt trägt zusätzlich `team_id`, `team_name`,
  `my_role`, `creator` (`{id, name}` oder `null` = gelöschter Benutzer) und `creator_is_member` (bei Team-Projekten).
- `GET /api/projects/current`: bleibt privat (`user_id=? AND team_id IS NULL AND archived=0`; legt bei leerem privatem
  Bereich ein privates Projekt an wie heute).
- `POST /api/projects/{pid}/move {team_id | null}`: Recht `move` am Projekt; Ziel-Team: Leiter/Mitglied. Verschiebt das
  Projekt **samt seinen Aufträgen** (Aufträge folgen dem Projekt). In privat verschieben setzt `team_id = NULL`; das
  Projekt gehört danach dem Verschiebenden (`user_id` = er) – erlaubt nur, wenn er Ersteller oder Leiter ist. Enthält
  das Projekt Aufträge anderer Ersteller (auch gelöschter), lehnt der Server das Verschieben nach privat mit 409 „Das
  Projekt enthält Aufträge anderer Mitglieder – bitte „In privat kopieren“ verwenden“ ab. Audit.
- `POST /api/projects/{pid}/copy {team_id | null, name?}`: Recht „Kopieren“ (siehe §2) am Quellprojekt und Leiter/
  Mitglied im Ziel-Team bzw. eigener privater Bereich. Kopiert in einem Lauf:
  - Projektzeile (Name „<Name> (Kopie)“ oder angegeben, Werkstück-Felder, Kontrollmaß, `cad_check` nicht).
  - Fotos mit neuen ids; der Fotoordner wird vollständig kopiert (alle Dateien, u. a.
    `orig/overlay/rect/gauge/thumb/small/rect_top.jpg`, `edges.json`, `edges_ki.jpg`; `align.jpg` ist keine Datei);
    `analysis` übernommen, `bottom_align.top_photo_id` auf die neue id umgeschrieben.
  - Teile (neue ids, `photo_id` umgeschrieben, `data.same_as` auf neue Teil-ids und `data.refs` auf neue Mess-ids
    umgeschrieben).
  - Messungen (neue ids, `photo_id`/`part_id` umgeschrieben, `seq` gleich).
  - Gelernte Werte (`model_dims`, `job_id`/`dim_id` – `job_id` auf den neuen Auftrag umgeschrieben, falls mitkopiert).
  - Je CAD-Auftrag des Projekts, dessen aktuelle Version (`jobs.current_version`) den Status `ok` hat: neuer Auftrag
    (Ersteller = Kopierender, gleicher Name, `messages` gekürzt auf die erste Nutzernachricht der Quelle, darin
    `image_ref.path` auf die neuen Fotoordner und die Beschriftungen „Foto <id>“ auf die neuen Foto-ids umgeschrieben;
    Bildverweise auf nicht mehr vorhandene Fotos entfallen samt Beschriftung; `request.photo_ids` und `request.part_id`
    auf die neuen ids umgeschrieben (nicht mehr vorhandene entfallen)), **eine** Version 1 mit `trigger='copy'`, `code`,
    `meta`, `result`, `checks`, Status `ok`, Dateien des Versionsordners kopiert (inkl. `preview.png`, falls vorhanden),
    `current_version = 1`, Status `done`. Kein KI-Aufruf, kein Kontingent.
  - Ablauf: (1) ohne Sperre **zuerst** die Quellzeilen lesen (Projekt; Fotos mit `analysis`, `format`, `view`; je Auftrag
    `current_version` und deren Status), **danach** die Ordner nach `DATA_DIR/tmp/copy-<zufall>/photos/<alte id>/` bzw.
    `…/jobs/<alte id>/v<n>/` kopieren, ohne `*.tmp` (`DATA_DIR/tmp` liegt auf dem Daten-Volume, daher ist `rename`
    atomar; `/tmp` ist ein tmpfs und scheidet aus); (2) in einer Transaktion (`db.atomic`) die Quellzeilen erneut lesen
    und mit (1) vergleichen – andere Foto-ids, geänderte `analysis`/`format`/`view`, anderes `current_version` oder
    fehlendes Projekt → 409 „Projekt wurde während des Kopierens geändert – bitte erneut kopieren“; Teile, Messungen
    und Werte aus diesem zweiten Lesen anlegen, ids umschreiben (`model_dims.job_id` ohne mitkopierten Auftrag =
    `NULL`), je neuem Auftrag eine `job_log`-Zeile „Kopie von Auftrag <alt>, Version <n>“; kein `jobs._lock` und kein
    `jobs.delete` in diesem Block; `COMMIT`; (3) danach `jobs/<neue id>/` anlegen und die Ordner per `rename` nach
    `photos/<neue id>` bzw. `jobs/<neue id>/v1` verschieben; scheitert das, werden das neue Projekt (Zeilen, Fotoordner)
    und seine Aufträge (`jobs.delete`) wieder gelöscht, Antwort 500. `DATA_DIR/tmp/copy-*` wird bei jedem Fehler und beim
    Serverstart entfernt. Eine eigene Größengrenze entfällt; der Upload begrenzt ein Projekt bereits auf 30 Fotos.
  - Antwort: das neue Projekt. Audit `project_copy`.
- Löschen eines Team-Projekts löscht wie heute Fotos/Messungen/Teile/Werte; Aufträge bleiben mit `project_id = NULL` beim
  jeweiligen Ersteller (wie heute bei privaten Projekten); Aufträge, deren Ersteller gelöscht ist (`user_id` leer),
  werden mitgelöscht (`jobs.delete`), damit keine Aufträge ohne Projekt und ohne Ersteller entstehen. Gleiches gilt beim
  Löschen eines Teams durch den Admin. `jobs.delete` läuft nie innerhalb von `db.atomic`.

## §5 Admin

- Reiter **„Teams“** in der Benutzerverwaltung: Liste aller Teams (Name, Leiter, Mitglieder, Projektzahl, angelegt),
  Kennzeichen „ohne Leiter“. Je Team: Mitglieder mit Rollen; Rolle setzen (auch Leiter ernennen), Mitglied entfernen,
  Einladungen zurückziehen, **Team löschen** – auch mit Projekten nach Rückfrage mit Eingabe des Teamnamens; dabei werden
  die Projekte wie beim Projekt-Löschen (§4) entfernt: (1) Aufträge ohne Ersteller in diesen Projekten per `jobs.delete`
  – außerhalb von `db.atomic`, weil `jobs.delete` `jobs._lock` nimmt und `jobs` die Sperren in umgekehrter Reihenfolge
  nimmt; (2) in einer Transaktion (`db.atomic`) Foto-ids sammeln, Projektzeilen und Team löschen; (3) nach dem COMMIT die
  Fotoordner entfernen. Alle übrigen Aufträge bleiben bei ihren Erstellern ohne Projekt.
  Audit `team_deleted` mit Projektzahl. Die Route der Benutzerverwaltung (`app.js`, Regex
  `^/admin(?:/(einladungen|protokoll|einstellungen))?$`) erhält `teams`.
- **Benutzer direkt aufnehmen** (Marc, 16.10.2026): `POST /api/admin/teams/{tid}/members {username, role}` mit
  `require_admin`, ohne Einladung und Annahme – der Ausweg für ein Team ohne Mitglieder, aber mit Projekten. Benutzer
  per exaktem Benutzernamen (Groß/klein egal) und aktiv, sonst 404 „Benutzer nicht gefunden“; schon Mitglied → 409;
  eine offene Einladung an ihn wird zurückgezogen. Audit `team_member_added_admin` (in `ACTIONS`). Der Admin-Reiter
  erhält dafür das Feld „Benutzer aufnehmen“ mit Rollenauswahl.
- **Leere Teams**: Ein Team ohne Mitglieder **und** ohne Projekte wird automatisch gelöscht, sobald es dazu kommt –
  beim Austritt des letzten Mitglieds (§3), wenn der Admin das letzte Mitglied entfernt, und beim Löschen des letzten
  Mitglieds (`succeed_leaders`, in derselben Transaktion); Audit `team_deleted`. Ein Team ohne Mitglieder mit
  Projekten bleibt und ist „ohne Leiter“ gekennzeichnet.
- Routen unter `/api/admin/teams…` mit `require_admin`; Inhalte der Team-Projekte sind dort nicht abrufbar.
  `GET /api/jobs?all=1` liefert dem Admin nur Aufträge ohne Projekt, in privaten Projekten und in Teams, in denen er
  Mitglied ist (`LEFT JOIN users`, Ersteller leer = „gelöschter Benutzer“); die Auftragszahl in `admin_users` zählt nur
  Aufträge, die der Benutzer selbst angelegt hat (Zahl, keine Inhalte).
- **Benutzer löschen** (`admin_user_delete`): löscht Aufträge des Benutzers mit `project_id IS NULL` oder in privaten
  Projekten (`jobs.delete`), dann Dateien und Zeilen seiner privaten Projekte ausdrücklich (`_delete_project_files`,
  `DELETE FROM projects WHERE user_id=? AND team_id IS NULL` – die Kaskade greift wegen `ON DELETE SET NULL` nicht
  mehr); **Team-Projekte und Aufträge in Team-Projekten bleiben** (Ersteller wird leer); Mitgliedschaften und
  Einladungen entfallen per Kaskade. War er letzter Leiter eines Teams mit weiteren Mitgliedern, wird das älteste
  verbleibende Mitglied (frühestes `joined_at`) Leiter (Audit `team_leader_auto`); war er das letzte Mitglied eines
  Teams ohne Projekte, wird das Team gelöscht (siehe „Leere Teams“). Die Nachfolge wird vor dem Löschen
  der Benutzerzeile ermittelt und in derselben Transaktion wie `DELETE FROM users` gesetzt. Die Bestätigung
  (`admin_users` und `app.js`) nennt die Zahl der Team-Projekte, die bleiben.

## §6 Kontingente und Grenzen

- Neue Spalte `jobs.run_by INTEGER REFERENCES users(id) ON DELETE SET NULL` (Auslöser des laufenden oder letzten Laufs);
  `jobs.create`, `_iterate_locked` und `param` setzen sie unter `jobs._lock` zusammen mit `status='queued'`;
  `_new_version` übernimmt sie in `job_versions.user_id` (auch für Autofix-Versionen desselben Laufs); die Kopie setzt
  `user_id` = Kopierender.
- `auth.usage_this_month(user_id)` zählt Versionen mit `trigger IN ('create','iterate')` und `v.user_id = ?` – ohne
  Rückgriff auf `jobs.user_id`, damit die Versionen eines gelöschten Auslösers nicht dem Ersteller angerechnet werden.
- Neuaufbau-Grenzen (`_param_limits`): laufend und je Stunde über `v.user_id`; Versionen ohne Auslöser zählen über
  `COALESCE(v.user_id, j.user_id)` beim Ersteller – in Produktion betrifft das nur Neuaufbauten eines gelöschten
  Auslösers der letzten Stunde.
- Laufende Aufträge je Nutzer (max. 3): gezählt über `jobs.run_by` bei Status `queued`/`running`, geprüft wie heute nur
  in `create`; `iterate` und `param` setzen `run_by`, prüfen die Zahl aber nicht (`param` behält seine eigene Grenze).
- KI-Tageskontingent (`_ai_uses_today`, Audit-basiert): unverändert beim Auslöser.

## §7 Oberfläche

- **Bibliothek** (`library.js`): Umschalter oben „Privat · <Team A> · <Team B>“ (Chips; Wahl in `localStorage
  lib.scope`), daneben Link „Teams verwalten“. „Neues Projekt“ legt im gewählten Bereich an. Team-Karten zeigen
  „von <Ersteller>“ bzw. „von ehemaligem Mitglied“, dazu die eigene Rolle als Abzeichen, wenn „Lesend“. Menü „…“:
  Umbenennen/Archivieren (write), „In Team verschieben…“/„In privat verschieben“ (move), „In Team kopieren…“/„In privat
  kopieren“ (Kopieren), Löschen (delete) – nicht erlaubte Einträge fehlen. Dialoge mit Teamauswahl.
- **Projektauswahl** (`projectPicker`): `<optgroup>` „Privat“ und je Team; Projekte aus `scope=all`.
- **Rolle Lesend**: Auf Fotos/Messen/CAD steht oben ein Hinweis „Nur ansehen – Rolle Lesend im Team <Name>“;
  Upload, alle Werkzeuge außer dem Werkzeug Verschieben (Bild ziehen), Bearbeiten-Knöpfe, KI-Knöpfe, „CAD-Modell
  erzeugen“, Wert-Eingaben im Viewer und Löschen sind deaktiviert. Der Server lehnt trotzdem alles mit 403 ab (die Oberfläche ist nur Komfort).
- **Teams** (`/teams`, neue Seite `teams.js`, Link im Benutzermenü und in der Bibliothek): meine Teams (Rolle,
  Mitglieder, Projekte), „Team gründen“; je Team: Mitgliederliste, Einladen (Benutzername + Rolle), Rollen ändern,
  entfernen, umbenennen, austreten, löschen (leer); oben „Einladungen für dich“ mit Annehmen/Ablehnen.
- **Kopfzeile**: Bei offenen Einladungen ein Abzeichen am Benutzermenü und ein Eintrag „Team-Einladungen (n)“.
- **Meine Aufträge**: Filter „Meine · <Team A> · …“; Team-Aufträge zeigen den Ersteller.
- **Anleitung**: neuer Abschnitt `teams` (Bereiche, Rollen-Tabelle, Einladen, Verschieben/Kopieren, Austritt);
  Kurzhilfe unverändert. `SECTIONS` in `help.js` erhält `teams` (Test `tests/js/help.test.mjs` angepasst);
  `groupsFor('/teams')` liefert die Standardgruppen.

## §8 Fehlerfälle und Grenzen

- Konkurrierende Bearbeitung im Team: wie heute (letzte Änderung gewinnt; Aufträge sind per `jobs._lock` geschützt;
  parametrischer Neuaufbau mit `base`-Prüfung → 409 bei veralteter Version).
- Verschieben während ein Auftrag des Projekts läuft: erlaubt (Auftrag folgt dem Projekt, Rechte gelten ab sofort).
- Kopieren während ein Auftrag läuft: kopiert die aktuelle gültige Version; laufende Versionen nicht.
- Benutzer verliert die Mitgliedschaft, während er eine Seite offen hat: nächste Anfrage → 404; die Oberfläche zeigt die
  Meldung und führt zur Bibliothek; auf der Auftragsseite führt sie zu „Meine Aufträge“.
- Team ohne Leiter (nur durch Benutzer-Löschen ohne verbleibende Mitglieder möglich, oder Admin-Eingriff): im Admin-
  Reiter gekennzeichnet; der Admin ernennt einen Leiter unter den Mitgliedern, nimmt einen Benutzer direkt auf (auch
  als Leiter, §5 – so bekommt auch ein Team ohne Mitglieder mit Projekten wieder einen Leiter) oder löscht das Team.
  Ein Team ohne Mitglieder und ohne Projekte entsteht nicht; es wird gelöscht (§5).
- Namen von Teams sind nicht eindeutig; Anzeige immer mit Teamname, interne Zuordnung über id.
- Ein Benutzer sieht von anderen Benutzern nur Benutzername und Anzeigename von Mitgliedern seiner Teams, von
  Erstellern in seinen Team-Bibliotheken und vom Einladenden einer an ihn gerichteten offenen Einladung.
- Kopieren und Absturz: Stirbt der Server zwischen COMMIT und Umbenennen, bleibt eine Kopie ohne (alle) Dateien zurück;
  die Quelle ist unberührt, die Kopie lässt sich normal löschen und neu anlegen. Schreibt ein gleichzeitiger
  Formatwechsel die Bilder eines Quellfotos vor (1) und seine Auswertung erst nach (2), kann die Kopie neue Bilder mit
  alter Auswertung enthalten; erneutes Setzen des Formats in der Kopie behebt das.

## §9 Nicht im Umfang

Projekt-Freigabe an Einzelpersonen außerhalb eines Teams; Team-eigene Kontingente; Benachrichtigungen per E-Mail;
gleichzeitiges Bearbeiten mit Live-Aktualisierung; Teams verschachteln; Verschieben/Kopieren zwischen zwei Teams in einem
Schritt (geht über „in privat kopieren“ und „in Team kopieren“).

## Umsetzung in zwei Wellen

Welle 1: §1, §2, §3, §4 ohne Kopieren, §5, §6, §7 ohne Kopier-Dialoge; Abnahme T1–T4, T6–T8, T10. Welle 2: Kopieren
(§4) samt Dialogen; Abnahme T5, T9 sowie erneut T2 (die Kopier-Route mit dem Recht „Kopieren“ in der Rechte-Tabelle von
`test_rechte_vollstaendig`) und T10. Beide Wellen auf Branch `teams`; ausgeliefert wird einmal nach Welle 2.

## §10 Abnahme

| Nr. | Prüfung | Nachweis |
|---|---|---|
| T1 | Migration auf einer Bestandsdatenbank aus dem `SCHEMA` von c408b93 (Fixture-Datei in `tests/`) mit Projekten, Fotos, Aufträgen, Versionen, Teilen, Messungen, Werten, einem gelöschten letzten Projekt und Auftrag (`sqlite_sequence` > `MAX(id)`), einer leeren, früher benutzten AUTOINCREMENT-Tabelle und einem Altverstoß (Zeile mit Verweis auf ein nicht vorhandenes Projekt): alle Zeilen und Fremdschlüssel unverändert (einzige Ergänzung `job_versions.user_id` = Ersteller), `foreign_key_check` nicht länger als vorher, `sqlite_sequence` unverändert, alle Projekte privat, `ix_projects_team` vorhanden (auch auf einer neuen Datenbank), `PRAGMA foreign_keys` = 1 auf der Verbindung; zweiter Start ändert nichts. Erzwungener Fehler nach `DROP TABLE jobs` (z. B. über eine `factory` für `sqlite3.connect`, die beim `RENAME` von `jobs_new` wirft): `conn()` wirft „Migration abgebrochen“, `iterdump()` vorher = nachher, ein folgender normaler Start migriert. | `pytest tests/test_teams.py -k migration` |
| T2 | Rechte-Matrix §2: für Besitzer, Admin, Leiter, Mitglied (selbst/fremd angelegt), Lesend, Außenstehender gegen jede Projekt-, Foto-, Mess-, Teil-, Auftrags- und Datei-Route der erwartete Status (200/403/404). Zusätzlich prüft `test_rechte_vollstaendig`, dass jede Route aus `app.routes` unter `/api/projects`, `/api/photos`, `/api/measurements`, `/api/parts`, `/api/jobs` und `/api/teams` genau einen Eintrag in der Rechte-Tabelle des Tests hat; eine neue Route ohne Eintrag lässt den Test fehlschlagen. | `pytest tests/test_teams.py -k rechte` (parametrisiert über alle Routen) |
| T3 | Teams: anlegen, einladen (unbekannt/doppelt/schon Mitglied), annehmen/ablehnen/zurückziehen, Rollen, letzter Leiter, austreten, löschen (leer/nicht leer) | `pytest tests/test_teams.py -k verwaltung` |
| T4 | Verschieben privat ↔ Team mit Aufträgen; Rechte; Audit; Verschieben nach privat mit fremdem Auftrag → 409 | `pytest tests/test_teams.py -k verschieben` |
| T5 | Kopieren: alle Bestandteile mit umgeschriebenen ids, Dateien vorhanden, Auftrag mit Version `copy` ok und Modellbild, Quelle unverändert, Fehler beim Kopieren hinterlässt nichts; im kopierten Auftrag zeigen alle `image_ref`-Pfade und `request.photo_ids`/`part_id` auf die Kopie, `parts.data.refs`/`same_as` auf neue ids; ein Änderungswunsch am kopierten Auftrag findet alle Bilder; gleichzeitiges Löschen eines Quellfotos → 409 ohne Rückstände; erzwungene Fehler in (1), (2) und (3) (`monkeypatch` auf `shutil.copytree` bzw. `os.rename`) hinterlassen keine Zeilen, keine neuen Ordner unter `photos/`/`jobs/` und kein `tmp/copy-*`; eine Änderung von `analysis` eines Quellfotos zwischen (1) und (2) → 409. | `pytest tests/test_teams.py -k kopieren` |
| T6 | Kontingent und Neuaufbau-Grenzen beim Auslöser; Altversionen zählen beim Ersteller; laufende Aufträge zählen beim Auslöser (`jobs.run_by`): Mitglied lässt drei Aufträge des Leiters ändern, der Leiter kann trotzdem neu anlegen; wird ein Mitglied gelöscht, das am Auftrag des Leiters Versionen ausgelöst hat, bleibt `usage_this_month` des Leiters gleich. | `pytest tests/test_teams.py -k kontingent` |
| T7 | Benutzer löschen: private Daten weg, Team-Projekte und deren Aufträge bleiben, Ersteller leer, Leiter-Nachfolge | `pytest tests/test_teams.py -k benutzer` |
| T8 | Admin-Reiter: Liste, Rollen, Entfernen, Team mit Projekten löschen nach Rückfrage | `pytest tests/test_teams.py -k admin` + Browser |
| T9 | Browser-Durchlauf mit drei Benutzern (Leiter, Mitglied, Lesend): Team gründen, einladen, annehmen, Projekt im Team anlegen, Mitglied misst und erzeugt CAD, Lesend sieht alles ohne Bearbeiten, Verschieben/Kopieren, Austritt; Konsole ohne Fehler | Playwright im Scratchpad |
| T10 | Bestehende Suite grün (private Abläufe unverändert); bestehende Tests werden nur an diesen Stellen angepasst: `tests/js/help.test.mjs` (`SECTIONS` um `teams`), `tests/test_library.py:188, :310` (direkte Inserts mit neuen Spalten) | `pytest -v` und `node --test tests/js/*.test.mjs` |

Testnamen in `tests/test_teams.py` beginnen mit `test_<stichwort>_`; Stichwörter: `migration`, `rechte`, `verwaltung`,
`verschieben`, `kopieren`, `kontingent`, `benutzer`, `admin`. Kein Stichwort darf Teil von „teams“ sein, weil `-k` auch
den Modulnamen prüft (`-k team` wählt die ganze Datei). Jeder Nachweis muss mindestens einen Test wählen (sonst
Exit-Code 5 = rot).

## Auslieferung

Branch `teams` → PR → CI grün → Merge → CI auf `main` → DS918+: Zeilenzahlen von `projects`, `photos`, `measurements`,
`parts`, `model_dims`, `jobs`, `job_versions`, `job_log`, die Einträge von `sqlite_sequence` und die Ausgabe von
`PRAGMA foreign_key_check` im laufenden alten Container festhalten; **Sicherung des Volumes bei gestoppten Containern**
(`backup-data-<datum>-<n>.tgz`); `compose pull && up -d` (Migration läuft beim Start); Gesundheit; wird der App-Container nicht `healthy`
(Neustartschleife wegen `restart: unless-stopped`, im Log „Migration abgebrochen“): `docker compose stop`, Log sichern,
Rückweg wie unten – jeder Startversuch hat vollständig zurückgerollt; Kontrolle per Skript im Container: alle genannten
Zeilenzahlen und `sqlite_sequence` gleich, `foreign_key_check` nicht länger als vorher, alle Projekte privat. Rückweg: nur durch Rücksicherung der Sicherung samt altem Image – das alte Image auf der neuen
Datenbank würde Team-Projekte als private Projekte ihrer Ersteller zeigen.
