"""Laeuft im App-Container (docker compose exec -T app python - < escape_check.py).
Schickt boesartigen Code durch die echte Sandbox (Worker-Container) und prueft, dass alles abgewehrt wird."""
import sys
import tempfile
import threading
from pathlib import Path

from app import sandbox

OK = "part = Box(10, 10, 10)\n"
CASES = {  # name: (code, erwarteter Textteil im Fehler)
    "netz": ("import socket\nsocket.create_connection(('1.1.1.1', 80), timeout=3)\n" + OK, "nicht erlaubt"),
    "datei_ausserhalb": ("open('/tmp/pwned', 'w').write('x')\n" + OK, "Arbeitsverzeichnis"),
    "daten_lesen": ("import os\nos.listdir('/data')\n" + OK, "Errno"),
    "env": ("import os\nraise RuntimeError('KEY' if 'ANTHROPIC_API_KEY' in os.environ else 'sauber')\n", "sauber"),
    "proc1": ("open('/proc/1/environ', 'rb').read()\n" + OK, "Permission denied"),
    "subprocess": ("import subprocess\nsubprocess.run(['id'])\n" + OK, "nicht erlaubt"),
    "exec_seccomp": ("import os, time\nimport _posixsubprocess as p\nr, w = os.pipe()\n"
                     "p.fork_exec([b'/bin/sh', b'-c', b'echo x > pwned.txt'], [b'/bin/sh'], True, (), None, None, -1, -1, -1,"
                     " -1, -1, -1, r, w, True, False, 0, None, None, None, -1, None, False)\n"
                     "time.sleep(1)\nraise RuntimeError('START=' + str(os.path.exists('pwned.txt')))\n", "START=False"),
    "speicher": ("x = bytearray(16 * 1024**3)\n" + OK, "MemoryError"),
    "kennung": ("import os\nraise RuntimeError('uid=%d' % os.getuid())\n", "uid=101"),
    "runs_listen": ("import os\nos.listdir('/runs')\n" + OK, "Permission denied"),
    "symlink": ("import os\nos.symlink('/etc/passwd', 'error.json')\n" + OK, "Arbeitsverzeichnis"),
    "endlos": ("while True:\n    pass\n", "TimeoutError"),
}

failed = 0
for name, (code, needle) in CASES.items():
    r = sandbox.run("from build123d import *\n" + code, Path(tempfile.mkdtemp()))
    text = "OK" if r["ok"] else f"{r['error'].get('type')}: {r['error'].get('message')}"
    good = (not r["ok"]) and needle in text
    failed += not good
    print(f"{'PASS' if good else 'FAIL'}  {name:16s} {text[:110]}")

r = sandbox.run("from build123d import *\n" + OK, Path(tempfile.mkdtemp()))
good = r["ok"] and r["result"]["seccomp"] and r["result"]["stl"]["watertight"]
failed += not good
print(f"{'PASS' if good else 'FAIL'}  gueltiges_modell  {r.get('result', r.get('error'))}")

uids = []


def probe():
    res = sandbox.run("from build123d import *\nimport os, time\ntime.sleep(3)\nraise RuntimeError(str(os.getuid()))\n",
                      Path(tempfile.mkdtemp()))
    uids.append(res["error"]["message"])


ts = [threading.Thread(target=probe) for _ in range(2)]
[t.start() for t in ts]
[t.join() for t in ts]
good = len(set(uids)) == 2
failed += not good
print(f"{'PASS' if good else 'FAIL'}  eigene_kennungen  {uids}")

leftover = [p.name for p in Path("/runs").iterdir() if not p.name.startswith(".")]
good = not leftover
failed += not good
print(f"{'PASS' if good else 'FAIL'}  aufgeraeumt      {leftover}")
sys.exit(1 if failed else 0)
