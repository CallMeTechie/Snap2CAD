"""Auftraege an die CAD-Sandbox uebergeben.

Modus "worker" (empfohlen, docker-compose): Ein zweiter Container desselben Images ohne Netzwerk
und ohne Datenbank-Volume holt Auftraege aus RUNS_DIR ab und fuehrt sie aus.
Modus "local": Ausfuehrung im App-Container (nur Ressourcenlimits + Audit-Hook, kein Netztrennung).
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import config

OUTPUT_FILES = ("model.step", "model.stl", "outline.json", "result.json", "error.json")
MAX_OUTPUT_BYTES = 300 * 1024 * 1024
MARKERS = (".ready", ".claimed", ".done", ".cancel", ".timeout")


class Cancelled(Exception):
    pass


def _copy_regular(src: Path, dst: Path) -> bool:
    """Nur echte, normale Dateien kopieren (keine Symlinks, FIFOs, Geraete; Groessenlimit)."""
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_OUTPUT_BYTES:
            return False
        with os.fdopen(fd, "rb", closefd=False) as f, open(dst, "wb") as out:
            shutil.copyfileobj(f, out, 1024 * 1024)
        return True
    finally:
        os.close(fd)


def _collect(rundir: Path, dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_FILES:
        (dest / name).unlink(missing_ok=True)
        _copy_regular(rundir / name, dest / name)
    if (dest / "result.json").is_file():
        try:
            return {"ok": True, "result": json.loads((dest / "result.json").read_text())}
        except ValueError:
            pass
    if (dest / "error.json").is_file():
        try:
            err = json.loads((dest / "error.json").read_text())
            if isinstance(err, dict):
                return {"ok": False, "error": {k: err.get(k) for k in ("stage", "type", "message", "line", "code", "traceback")}}
        except ValueError:
            pass
    return {"ok": False, "error": {"stage": "sandbox", "type": "SandboxError", "line": None, "code": None,
                                   "message": "Die Sandbox hat kein Ergebnis geliefert."}}


def run(code: str, dest: Path, cancel: threading.Event | None = None) -> dict:
    """Code ausfuehren, Ausgaben nach dest kopieren. Rueckgabe {ok, result|error, seconds}."""
    t0 = time.time()
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rundir = config.RUNS_DIR / uuid.uuid4().hex
    rundir.mkdir(mode=0o700)
    marker = config.RUNS_DIR / rundir.name
    cleanup = True
    try:
        (rundir / "model.py").write_text(code, encoding="utf-8")
        if config.SANDBOX_MODE == "local":
            out = _run_local(rundir, cancel)
        else:
            out = _run_worker(rundir, cancel)
        if out is not None:
            return {**out, "seconds": round(time.time() - t0, 1)}
        res = _collect(rundir, dest)
        res["seconds"] = round(time.time() - t0, 1)
        return res
    except Cancelled:
        if config.SANDBOX_MODE != "local":
            try:
                marker.with_suffix(".ready").unlink()  # noch nicht uebernommen -> selbst aufraeumen
            except FileNotFoundError:
                cleanup = False  # der Worker hat den Lauf: er beendet ihn und raeumt auf (.cancel bleibt)
        raise
    finally:
        if cleanup:
            shutil.rmtree(rundir, ignore_errors=True)
            for suffix in MARKERS:
                try:
                    marker.with_suffix(suffix).unlink()
                except OSError:
                    pass


def _timeout_error():
    return {"ok": False, "error": {"stage": "sandbox", "type": "TimeoutError", "line": None, "code": None,
                                   "message": f"Zeitlimit von {config.SANDBOX_TIMEOUT} s überschritten. "
                                              "Modell vereinfachen (weniger Features, gröbere Muster)."}}


def _run_local(rundir: Path, cancel):
    cmd = [sys.executable, "-I", str(config.RUNNER), str(rundir), str(config.SANDBOX_TIMEOUT),
           str(config.SANDBOX_MEM_MB)]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(rundir), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "2"}
    p = subprocess.Popen(cmd, cwd=rundir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.time() + config.SANDBOX_TIMEOUT + 30
    while p.poll() is None:
        if cancel is not None and cancel.is_set():
            p.kill()
            raise Cancelled()
        if time.time() > deadline:
            p.kill()
            return _timeout_error()
        time.sleep(0.2)
    if p.returncode in (-9, 137) and not (rundir / "error.json").exists():
        return _timeout_error()
    return None


def _run_worker(rundir: Path, cancel):
    # Marker liegen neben dem Laufverzeichnis in RUNS_DIR; dort darf nur die App schreiben.
    deadline = time.time() + config.SANDBOX_TIMEOUT + 90
    marker = config.RUNS_DIR / rundir.name
    marker.with_suffix(".ready").write_text("1")
    while not marker.with_suffix(".done").exists():
        if cancel is not None and cancel.is_set():
            marker.with_suffix(".cancel").write_text("1")
            raise Cancelled()
        if time.time() > deadline:
            marker.with_suffix(".cancel").write_text("1")
            return {"ok": False, "error": {"stage": "sandbox", "type": "SandboxUnavailable", "line": None,
                                           "code": None, "message": "Die CAD-Sandbox antwortet nicht. "
                                           "Läuft der Dienst „sandbox“ (docker compose ps)?"}}
        time.sleep(0.3)
    if marker.with_suffix(".timeout").exists():
        return _timeout_error()
    return None


def worker_alive() -> bool:
    """Prueft den Herzschlag des Sandbox-Workers (Datei RUNS_DIR/.heartbeat)."""
    if config.SANDBOX_MODE == "local":
        return True
    hb = config.RUNS_DIR / ".heartbeat"
    try:
        return time.time() - hb.stat().st_mtime < 30
    except OSError:
        return False
