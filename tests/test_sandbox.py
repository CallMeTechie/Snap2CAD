"""Sandbox: generierter Code darf nichts ausser rechnen. Hier im lokalen Modus (Limits, seccomp, Audit-Hook);
die Container-Trennung (eigene Kennung, kein Netz) prueft tests/docker/escape_check.py in der CI."""
import os
import platform
from pathlib import Path

import pytest

from app import sandbox

OK = "part = Box(10, 10, 10)\n"


def run(code, tmp_path):
    return sandbox.run("from build123d import *\n" + code, tmp_path / "out")


def blocked(res, needle=""):
    assert not res["ok"], res
    msg = f"{res['error'].get('type')}: {res['error'].get('message')}"
    assert needle in msg, msg
    return msg


def test_valid_model(tmp_path):
    r = run(OK, tmp_path)
    assert r["ok"], r
    res = r["result"]
    assert res["valid"] and res["solids"] == 1 and res["bbox"] == [10.0, 10.0, 10.0]
    assert res["stl"]["watertight"]
    if platform.machine() in ("x86_64", "aarch64"):
        assert res["seccomp"] is True
    out = tmp_path / "out"
    assert (out / "model.step").stat().st_size > 1000 and (out / "model.stl").is_file()


def test_model_error_reports_line(tmp_path):
    r = run("x = 1\nfillet(Box(5, 5, 5).edges(), radius=10)\n", tmp_path)
    assert not r["ok"] and r["error"]["line"] == 3  # +1 wegen vorangestelltem Import


def test_missing_part(tmp_path):
    blocked(run("x = Box(1, 1, 1)\n", tmp_path), "part")


@pytest.mark.parametrize("name,code,needle", [
    ("socket", "import socket\nsocket.create_connection(('1.1.1.1', 80), timeout=2)\n", "nicht erlaubt"),
    ("urllib", "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=2)\n", "nicht erlaubt"),
    ("subprocess", "import subprocess\nsubprocess.run(['id'])\n", "nicht erlaubt"),
    ("os_system", "import os\nos.system('id')\n", "nicht erlaubt"),
    ("fork", "import os\nos.fork()\n", "nicht erlaubt"),
    ("ctypes", "import ctypes\nctypes.CDLL(None)\n", "nicht erlaubt"),
    ("write_outside", "open('/tmp/snap2cad-pwned', 'w').write('x')\n", "Arbeitsverzeichnis"),
    ("symlink", "import os\nos.symlink('/etc/passwd', 'error.json')\n", "Arbeitsverzeichnis"),
    ("kill", "import os, signal\nos.kill(os.getppid(), signal.SIGTERM)\n", "nicht erlaubt"),
    ("memory", "x = bytearray(16 * 1024**3)\n", "MemoryError"),
])
def test_blocked(tmp_path, name, code, needle):
    blocked(run(code + OK, tmp_path), needle)
    assert not Path("/tmp/snap2cad-pwned").exists()


@pytest.mark.skipif(platform.machine() not in ("x86_64", "aarch64"), reason="seccomp-Filter nur fuer x86_64/aarch64")
def test_exec_blocked_by_seccomp(tmp_path):
    code = ("import os, time\nimport _posixsubprocess as p\nr, w = os.pipe()\n"
            "p.fork_exec([b'/bin/sh', b'-c', b'echo x > pwned.txt'], [b'/bin/sh'], True, (), None, None, -1, -1, -1, -1,"
            " -1, -1, r, w, True, False, 0, None, None, None, -1, None, False)\n"
            "time.sleep(1)\nraise RuntimeError('START=' + str(os.path.exists('pwned.txt')))\n")
    msg = blocked(run(code, tmp_path), "START=")
    assert "START=False" in msg


def test_timeout(tmp_path):
    msg = blocked(run("while True:\n    pass\n", tmp_path), "TimeoutError")
    assert "Zeitlimit" in msg


def test_collect_ignores_symlinks_and_fifos(tmp_path):
    rundir = tmp_path / "run"
    rundir.mkdir()
    secret = tmp_path / "geheim.txt"
    secret.write_text("streng geheim")
    (rundir / "model.step").symlink_to(secret)
    os.mkfifo(rundir / "model.stl")
    (rundir / "result.json").write_text('{"valid": true}')
    res = sandbox._collect(rundir, tmp_path / "dest")
    assert res["ok"]
    assert not (tmp_path / "dest" / "model.step").exists()
    assert not (tmp_path / "dest" / "model.stl").exists()


def test_dim_anchors_tupel_vector_und_ungueltige(tmp_path):
    code = ("class K(str):\n    pass\n"
            "B = 10\npart = Box(B, B, B)\nDIM_ANCHORS = {\n"
            "    'D1': ((0, 0, 0), (0, 0, B)),\n"
            "    'D2': (Vector(0, 0, 0), Vector(1.23456, 0, 0)),\n"
            "    'D3': ((0, 0, float('nan')), (0, 0, 1)),\n"
            "    'M1': ((0, 0, 0), (1, 0, 0)),\n"
            "    'D4': ((0, 0, 0),),\n"
            "    'D5': ((0, 0, 0), ('x', 0, 0)),\n"
            "    'D12345': ((0, 0, 0), (1, 0, 0)),\n"
            "    7: ((0, 0, 0), (1, 0, 0)),\n"
            "    K('D7'): ((0, 0, 0), (1, 0, 0)),\n"
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
