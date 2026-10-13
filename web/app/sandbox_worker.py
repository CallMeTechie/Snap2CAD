"""CAD-Sandbox-Worker. Laeuft im Container "sandbox" ohne Netzwerk und ohne Datenbank.

Holt Auftragsverzeichnisse aus RUNS_DIR (Marker READY), fuehrt den Runner unter einem eigenen
Benutzer (SANDBOX_UID) mit Ressourcenlimits aus und markiert das Ende mit DONE.
"""
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from app import config


def log(msg):
    print(time.strftime("%H:%M:%S"), "[sandbox]", msg, flush=True)


def _chown_tree(path: Path, uid: int, gid: int):
    """Besitz aendern, ohne Symlinks zu folgen."""
    for root, dirs, files in os.walk(path, followlinks=False):
        os.chown(root, uid, gid, follow_symlinks=False)
        for n in dirs + files:
            os.chown(os.path.join(root, n), uid, gid, follow_symlinks=False)


def _sanitize(path: Path):
    """Nach dem Lauf: alles entfernen, was keine normale Datei bzw. kein Verzeichnis ist
    (Symlinks, Hardlinks, FIFOs, Sockets, Geraete) – die App liest danach aus diesem Baum."""
    for root, dirs, files in os.walk(path, topdown=False, followlinks=False):
        for n in dirs + files:
            p = os.path.join(root, n)
            try:
                st = os.lstat(p)
                if stat.S_ISDIR(st.st_mode):
                    continue
                if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
                    os.unlink(p)
            except OSError:
                pass


# Jeder gleichzeitige Lauf bekommt eine eigene Benutzerkennung, damit sich parallele Laeufe
# weder ueber Dateien noch ueber /proc gegenseitig sehen koennen.
_uid_lock = threading.Lock()
_uids_busy: set[int] = set()


def _take_uid() -> int:
    with _uid_lock:
        for i in range(64):
            uid = config.SANDBOX_UID + i
            if uid not in _uids_busy:
                _uids_busy.add(uid)
                return uid
    raise RuntimeError("keine freie Sandbox-Kennung")


def _give_uid(uid: int):
    with _uid_lock:
        _uids_busy.discard(uid)


def _drop(uid: int):
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    os.umask(0o077)


def execute(rundir: Path):
    is_root = os.geteuid() == 0
    marker = rundir.parent / rundir.name
    uid = _take_uid() if is_root else None
    try:
        if is_root:
            _chown_tree(rundir, uid, uid)
            os.chmod(rundir, 0o700)
        cmd = [sys.executable, "-I", str(config.RUNNER), str(rundir), str(config.SANDBOX_TIMEOUT),
               str(config.SANDBOX_MEM_MB)] + (["128"] if is_root else [])
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(rundir), "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "2"}
        p = subprocess.Popen(cmd, cwd=rundir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             preexec_fn=partial(_drop, uid) if is_root else None, close_fds=True)
        deadline = time.time() + config.SANDBOX_TIMEOUT + 15
        while p.poll() is None:
            if marker.with_suffix(".cancel").exists() or time.time() > deadline:
                p.kill()
                p.wait()
                if time.time() > deadline:
                    marker.with_suffix(".timeout").write_text("1")
                break
            time.sleep(0.2)
        if p.returncode in (-9, 137) and not (rundir / "error.json").exists():
            marker.with_suffix(".timeout").write_text("1")
        log(f"{rundir.name[:8]} fertig (rc={p.returncode}, uid {uid})")
    except Exception as e:  # noqa: BLE001
        log(f"{rundir.name[:8]} Fehler: {e}")
    finally:
        if is_root:
            _sanitize(rundir)
            _chown_tree(rundir, config.APP_UID, config.APP_UID)
            os.chmod(rundir, 0o700)
            _give_uid(uid)
        if marker.with_suffix(".cancel").exists():
            shutil.rmtree(rundir, ignore_errors=True)
            for suffix in (".cancel", ".timeout", ".claimed", ".ready"):
                try:
                    marker.with_suffix(suffix).unlink()
                except OSError:
                    pass
        else:
            marker.with_suffix(".done").write_text("1")
            try:
                marker.with_suffix(".claimed").unlink()
            except OSError:
                pass


def main():
    runs = config.RUNS_DIR
    runs.mkdir(parents=True, exist_ok=True)
    log(f"bereit · {runs} · {config.SANDBOX_WORKERS} parallel · Limit {config.SANDBOX_TIMEOUT} s / "
        f"{config.SANDBOX_MEM_MB} MB · uid ab {config.SANDBOX_UID}")
    pool = ThreadPoolExecutor(max_workers=config.SANDBOX_WORKERS)
    lock = threading.Lock()
    while True:
        try:
            (runs / ".heartbeat").write_text(str(time.time()))
            for ready in runs.glob("*.ready"):
                name = ready.name[:-6]
                d = runs / name
                if not (len(name) == 32 and all(c in "0123456789abcdef" for c in name)):
                    continue
                try:
                    if not stat.S_ISDIR(os.lstat(d).st_mode):  # kein Symlink, echtes Verzeichnis
                        continue
                except OSError:
                    continue
                with lock:
                    try:
                        ready.rename(runs / f"{name}.claimed")
                    except OSError:
                        continue
                log(f"{name[:8]} übernommen")
                pool.submit(execute, d)
        except Exception as e:  # noqa: BLE001
            log(f"Fehler in der Warteschleife: {e}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
