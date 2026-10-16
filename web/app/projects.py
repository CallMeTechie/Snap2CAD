"""Projekte samt Dateien loeschen (Spec Teams §4, §5): Projekt-Loeschen, Team-Loeschen durch den Admin, Benutzer-Loeschen."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from . import config, db, jobs


def photo_dir(phid: int) -> Path:
    """Ordner eines Fotos – einzige Stelle (main._photo_dir und projcopy nutzen sie)."""
    return config.DATA_DIR / "photos" / str(phid)


def delete_projects(pids: list[int], then: Callable[[], None] | None = None,
                    guard: Callable[[], None] | None = None) -> None:
    """(1) In einer Transaktion zuerst guard() – Rechte bzw. Projektliste erneut pruefen, wirft bei einem Wettlauf
    (Verschieben, Austritt, neues Projekt) und loescht dann nichts, auch keine Auftraege –, danach die ids der
    Auftraege ohne Ersteller und die Foto-ids sammeln, Projektzeilen loeschen und then() (z. B. Team oder Benutzer
    loeschen). Alle anderen Auftraege bleiben bei ihren Erstellern ohne Projekt (ON DELETE SET NULL). (2) Nach dem
    COMMIT die gesammelten Auftraege ohne Ersteller per jobs.delete – ausserhalb von db.atomic, weil jobs.delete
    jobs._lock nimmt (Sperrreihenfolge jobs._lock -> db._lock) – und die Fotoordner entfernen. Deshalb nie innerhalb
    eines aeusseren db.atomic aufrufen (dort gaebe es kein eigenes COMMIT): RuntimeError."""
    with db._lock:   # die Verbindung ist geteilt: in_transaction nur unter db._lock eindeutig dem eigenen Thread zuzuordnen
        if db.conn().in_transaction:
            raise RuntimeError("delete_projects nicht innerhalb von db.atomic aufrufen")
    marks = ",".join("?" * len(pids))
    photo_ids: list[int] = []
    orphans: list[int] = []
    with db.atomic():
        if guard is not None:
            guard()
        if pids:
            orphans = [r["id"] for r in db.q(f"SELECT id FROM jobs WHERE project_id IN ({marks}) AND user_id IS NULL",
                                             tuple(pids))]
            photo_ids = [r["id"] for r in db.q(f"SELECT id FROM photos WHERE project_id IN ({marks})", tuple(pids))]
            db.ex(f"DELETE FROM projects WHERE id IN ({marks})", tuple(pids))
        if then is not None:
            then()
    for jid in orphans:
        j = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
        if j:
            jobs.delete(j)
    for phid in photo_ids:
        shutil.rmtree(photo_dir(phid), ignore_errors=True)


def sweep() -> None:
    """Serverstart (Plan, Lueckenfuellung 22): Auftraege ohne Ersteller und ohne Projekt – Spec §2 schliesst sie aus,
    ohne Ersteller haben sie keinen Empfaenger – per jobs.delete und Fotoordner photos/<id> ohne Zeile entfernen."""
    for j in db.q("SELECT * FROM jobs WHERE user_id IS NULL AND project_id IS NULL"):
        jobs.delete(j)
    root = config.DATA_DIR / "photos"
    if not root.is_dir():
        return
    known = {r["id"] for r in db.q("SELECT id FROM photos")}
    for d in root.iterdir():
        if d.is_dir() and d.name.isascii() and d.name.isdigit() and int(d.name) not in known:
            shutil.rmtree(d, ignore_errors=True)
