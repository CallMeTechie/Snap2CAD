"""A4/A3 bleiben exakt wie auf main ff95d9b (Spec Kleinteile §6, Goldwerte).

Neu erzeugen nur auf dem unveraenderten Stand (Plan Kleinteile, Task 1):
    SNAP2CAD_WRITE_GOLDEN=1 python -m pytest -q -p no:cacheprovider tests/test_golden_a4a3.py
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from conftest import synthetic_photo
from core import edges, vision

GOLDEN = Path(__file__).parent / "fixtures" / "golden_a4a3.json"
pytestmark = pytest.mark.skipif(os.environ.get("GITHUB_ACTIONS") == "true",
                                reason="Goldwerte sind CPU-abhaengig (lokal SSE4.2, CI AVX2/AVX-512); "
                                       "A4/A3 wird lokal geprueft")
BOX = {"rect": [60, 80, 60, 40], "gray": 150}
PLATE = {"rect": [50, 105, 80, 20], "gray": 90}
HOLE = {"circle": [90, 115, 5], "gray": 235}
GLASS = {"rect": [60, 80, 60, 40], "gray": 200, "alpha": 0.5}
SHADOW = {"mm": 8, "sides": ("left", "bottom"), "dark": 0.8}
L_SHAPE = [[60, 80], [120, 80], [120, 95], [75, 95], [75, 120], [60, 120]]

# Name -> (Format, Seite, synthetic_photo-Argumente, Format fuer analyze, Hinweise fuer detect oder None = ohne Kanten)
CASES = {
    "a4_standard": ("A4", 0, {}, None, {}),
    "a3_standard": ("A3", 0, {}, None, {}),
    "a4_explizit": ("A4", 0, {}, "A4", None),
    "a4_hoehenlehre": ("A4", 1, {"tilt": 0.03}, "A4", None),
    "a4_quader": ("A4", 0, {"objects": [BOX]}, "A4", {}),
    "a4_zwei": ("A4", 0, {"objects": [BOX, PLATE, HOLE]}, "A4", {}),
    "a4_leer": ("A4", 0, {"objects": []}, "A4", {}),
    "a4_rand": ("A4", 0, {"objects": [{"rect": [0, 60, 50, 30], "gray": 120}]}, "A4", {}),
    "a4_hell": ("A4", 0, {"objects": [{"rect": [60, 80, 60, 40], "gray": 246}]}, "A4", {}),
    "a4_hell_hinweis": ("A4", 0, {"objects": [{"rect": [60, 80, 60, 40], "gray": 225}]}, "A4", {"light": True}),
    "a4_schatten": ("A4", 0, {"objects": [BOX], "shadow": SHADOW}, "A4", {}),
    "a4_glas_t2": ("A4", 0, {"objects": [GLASS]}, "A4", {"transparent": 2}),
    "a4_glas_t1": ("A4", 0, {"objects": [GLASS]}, "A4", {"transparent": 1}),
    "a4_l_bohrung": ("A4", 0, {"objects": [{"polygon": L_SHAPE, "gray": 150}, {"circle": [110, 87.5, 5], "gray": 235}]},
                     "A4", {}),
    "a3_quader": ("A3", 0, {"objects": [BOX]}, "A3", {}),
    "a4_viele": ("A4", 0, {"objects": [{"rect": [30 + 20 * i, 30 + 22 * j, 15, 15], "gray": 120}
                                       for i in range(6) for j in range(7)]}, "A4", {}),
    "a4_glas_ohne": ("A4", 0, {"objects": [GLASS]}, "A4", {}),
    "a4_grau225_ohne": ("A4", 0, {"objects": [{"rect": [60, 80, 60, 40], "gray": 225}]}, "A4", {}),
    "a4_hoehenlehre_auto": ("A4", 1, {"tilt": 0.03}, None, None),
}


def _snap(name: str) -> dict:
    fmt, page, kw, afmt, hints = CASES[name]
    img = vision.load_image(synthetic_photo(fmt, page, **kw))
    a = vision.analyze(img, afmt)
    out = {"analyze": a}
    if a.get("homography") and a.get("format"):
        rect = vision.rectify_mat(img, a["homography"], a["format"])
        out["rect_shape"] = list(rect.shape)
        out["rect_md5"] = hashlib.md5(np.ascontiguousarray(rect).tobytes()).hexdigest()
        if hints is not None:
            cv2.setRNGSeed(12345)  # GrabCut zieht aus cv::theRNG; ab Task 4 setzt detect denselben Seed selbst
            out["detect"] = edges.detect(rect, a["format"], hints)
    return json.loads(json.dumps(out))  # Tupel -> Listen, int-Schluessel -> str (wie im JSON)


def _same(old, new, path="$"):
    """Alte Werte muessen gleich bleiben; neue Schluessel sind erlaubt. Floats nach Rundung (Homographie 9, sonst 3)."""
    if isinstance(old, dict):
        assert isinstance(new, dict), path
        for k, v in old.items():
            assert k in new, f"{path}.{k} fehlt"
            _same(v, new[k], f"{path}.{k}")
    elif isinstance(old, list):
        assert isinstance(new, list), f"{path}: keine Liste"
        assert len(new) == len(old), f"{path}: Laenge {len(old)} -> {len(new)}"
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            _same(a, b, f"{path}[{i}]")
    elif isinstance(old, float) or isinstance(new, float):
        digits = 9 if "homography" in path else 3
        assert round(float(old), digits) == round(float(new), digits), f"{path}: {old} -> {new}"
    else:
        assert old == new, f"{path}: {old!r} -> {new!r}"


@pytest.fixture(scope="module")
def golden() -> dict:
    if os.environ.get("SNAP2CAD_WRITE_GOLDEN") == "1":
        root = Path(__file__).resolve().parents[1]
        unchanged = subprocess.run(["git", "diff", "--quiet", "ff95d9b", "--", "core", "web", "tests/conftest.py"], cwd=root)
        assert unchanged.returncode == 0, "Goldwerte nur auf dem unveraenderten Stand erzeugen"
        GOLDEN.write_text(json.dumps({n: _snap(n) for n in CASES}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(CASES))
def test_golden_a4a3_unveraendert(golden, name):
    _same(golden[name], _snap(name))
