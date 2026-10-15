"""Fuehrt von Claude erzeugten build123d-Code isoliert aus und exportiert STEP/STL.

Aufruf (nur durch Sandbox-Worker bzw. lokalen Fallback):
    python -I cad_runner.py <rundir> <timeout_s> <mem_mb>

Erwartet <rundir>/model.py. Der Code muss das fertige Teil der Variablen `part` zuweisen.
Schreibt model.step, model.stl und result.json – oder error.json bei Fehlern.
Optional: DIM_ANCHORS im Modellcode -> result.json["dim_anchors"] (Regel 13).
Schutzschichten: eigener Benutzer je Lauf + kein Netz (Container), Ressourcenlimits, seccomp, Audit-Hook.
"""
import json
import os
import resource
import sys
import traceback

RUNDIR, TIMEOUT, MEM_MB = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
NPROC = int(sys.argv[4]) if len(sys.argv) > 4 else 0  # nur mit eigener Kennung je Lauf sinnvoll


def _write(name, data):
    with open(os.path.join(RUNDIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# 1) Ressourcenlimits – hart, koennen vom Code nicht wieder angehoben werden
resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT, TIMEOUT))
resource.setrlimit(resource.RLIMIT_AS, (MEM_MB * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
if NPROC:
    resource.setrlimit(resource.RLIMIT_NPROC, (NPROC, NPROC))
os.chdir(RUNDIR)

# 2) Bibliotheken vorab laden (danach wird Nachladen nativer Module blockiert)
import math  # noqa: E402,F401

import trimesh  # noqa: E402
from build123d import *  # noqa: E402,F401,F403
from build123d import BuildPart, export_step, export_stl, import_step  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

# 3) seccomp: Kernel verweigert Programmstart, Netzwerk-Sockets, ptrace & Co. (gilt auch fuer Kindprozesse)
_DENY = {
    "x86_64": (0xC000003E, [59, 322, 41, 53, 101, 310, 311, 321, 298, 323, 250, 248, 249, 272, 308, 165, 166, 155, 161]),
    "aarch64": (0xC00000B7, [221, 281, 198, 199, 117, 270, 271, 280, 241, 282, 219, 217, 218, 97, 268, 40, 39, 41, 51]),
}


def _seccomp() -> bool:
    import ctypes
    import platform
    arch = platform.machine()
    if arch not in _DENY:
        return False
    audit_arch, nrs = _DENY[arch]

    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]

    class Prog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    ld, jeq, jge, ret = 0x20, 0x15, 0x35, 0x06
    allow, kill, eperm = 0x7FFF0000, 0x80000000, 0x00050000 | 1
    prog = [(ld, 0, 0, 4), (jeq, 1, 0, audit_arch), (ret, 0, 0, kill), (ld, 0, 0, 0)]
    checks = ([(jge, 0x40000000)] if arch == "x86_64" else []) + [(jeq, nr) for nr in nrs]
    deny_at = len(prog) + len(checks) + 1
    for op, k in checks:
        prog.append((op, deny_at - (len(prog)) - 1, 0, k))
    prog += [(ret, 0, 0, allow), (ret, 0, 0, eperm)]
    arr = (Filter * len(prog))(*[Filter(*x) for x in prog])
    fprog = Prog(len(prog), arr)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        return False
    return libc.prctl(22, 2, ctypes.byref(fprog), 0, 0) == 0  # PR_SET_SECCOMP, SECCOMP_MODE_FILTER


try:
    SECCOMP = _seccomp()
except Exception:  # noqa: BLE001
    SECCOMP = False

RUNDIR_REAL = os.path.realpath(RUNDIR)
_BLOCKED = ("socket.", "subprocess.", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
            "os.forkpty", "pty.", "ctypes.", "urllib.", "http.", "ftplib.", "smtplib.", "webbrowser.",
            "os.kill", "os.putenv", "os.unsetenv", "sys.addaudithook", "cpython.run_", "winreg")


def _hook(event, args):
    if event.startswith(_BLOCKED):
        raise PermissionError(f"In der Sandbox nicht erlaubt: {event}")
    if event == "open":
        path, mode = args[0], args[1] if len(args) > 1 else "r"
        if isinstance(path, int) or path is None:
            return
        writing = isinstance(mode, str) and any(c in mode for c in "wax+")
        if isinstance(mode, int):
            writing = bool(mode & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
        if writing:
            real = os.path.realpath(os.fsdecode(path))
            if not (real == RUNDIR_REAL or real.startswith(RUNDIR_REAL + os.sep)):
                raise PermissionError("Schreiben nur im Arbeitsverzeichnis erlaubt")
    elif event in ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.symlink",
                   "os.link", "shutil.rmtree"):
        if not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        real = os.path.realpath(os.fsdecode(args[0]))
        if not real.startswith(RUNDIR_REAL + os.sep):
            raise PermissionError("Dateioperationen nur im Arbeitsverzeichnis erlaubt")


def _model_error(exc):
    tb = traceback.extract_tb(exc.__traceback__)
    frames = [f for f in tb if f.filename == "model.py"]
    line = frames[-1].lineno if frames else None
    code_line = None
    if line:
        try:
            code_line = SOURCE.splitlines()[line - 1].strip()
        except IndexError:
            pass
    return {"type": type(exc).__name__, "message": str(exc)[:2000], "line": line, "code": code_line,
            "traceback": "".join(traceback.format_exception(exc))[-4000:]}


MAX_ANCHORS = 200


def _dim_key(k) -> bool:
    """Schluessel wie ^D[0-9]{1,4}$ (ohne re: der Name re ist unten der STEP-Re-Import). type(k) is str: keine
    str-Unterklasse aus dem Modellcode; die Vertrauensgrenze ist trotzdem erst jobs._filter_anchors (Task 4)."""
    return type(k) is str and 2 <= len(k) <= 5 and k[0] == "D" and k[1:].isascii() and k[1:].isdigit()


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


with open("model.py", encoding="utf-8") as f:
    SOURCE = f.read()

sys.addaudithook(_hook)

# 4) Modellcode ausfuehren
ns = {"__name__": "__model__"}
exec("from build123d import *\nimport math\n", ns)
try:
    exec(compile(SOURCE, "model.py", "exec"), ns)
except BaseException as e:  # noqa: BLE001
    _write("error.json", {"stage": "model", **_model_error(e)})
    sys.exit(1)

part = ns.get("part", ns.get("result"))
if isinstance(part, BuildPart):
    part = part.part
if part is None or not hasattr(part, "wrapped"):
    _write("error.json", {"stage": "model", "type": "ValueError", "line": None, "code": None,
                          "message": "Der Code muss das fertige Teil der Variablen `part` zuweisen "
                                     "(build123d Part/Solid/Compound)."})
    sys.exit(1)

# 5) Export und Pruefung
try:
    solids = part.solids()
    if not solids:
        raise ValueError("Das Ergebnis enthaelt keinen Volumenkoerper (Solid).")
    valid = bool(part.is_valid() if callable(getattr(part, "is_valid", None)) else part.is_valid)
    export_step(part, "model.step")
    export_stl(part, "model.stl", tolerance=0.01, angular_tolerance=0.1)

    re = import_step("model.step")
    bb = re.bounding_box()
    mesh = trimesh.load("model.stl", force="mesh")
    outline = []
    try:
        tri = mesh.triangles[mesh.face_normals[:, 2] > 1e-6][:, :, :2]
        shapes = [Polygon(t) for t in tri]
        poly = unary_union([g for g in shapes if g.area > 1e-9]).buffer(0)
        polys = list(getattr(poly, "geoms", [poly])) if not poly.is_empty else []
        for p in polys:
            p = p.simplify(0.05)
            outline.append({"exterior": [[round(x, 3), round(y, 3)] for x, y in p.exterior.coords],
                            "holes": [[[round(x, 3), round(y, 3)] for x, y in r.coords] for r in p.interiors]})
    except Exception:  # Umriss ist optional
        outline = []

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
