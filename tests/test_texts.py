"""Oberflaeche ohne Markennamen (Spec 2026-10-14-kanten-und-teile, A5)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = [*(ROOT / "web/static/js").glob("*.js"), *(ROOT / "web/static/css").glob("*.css"), ROOT / "web/static/index.html"]


def _code_lines(path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s.startswith("//") or s.startswith("#"):
            continue
        yield n, line


def test_static_ohne_claude():
    hits = [f"{p.name}:{n}" for p in STATIC for n, line in _code_lines(p) if "Claude" in line]
    assert hits == []


def test_anthropic_nur_in_einrichtung_und_verwaltung():
    hits = [f"{p.name}:{n}" for p in STATIC if p.name != "app.js"
            for n, line in _code_lines(p) if re.search(r"anthropic", line, re.I)]
    assert hits == []


def test_python_meldungen_neutral():
    allowed = ("Bitte den Anthropic-API-Schlüssel eingeben.",)
    hits = []
    for name in ("main.py", "jobs.py"):
        for n, line in _code_lines(ROOT / "web/app" / name):
            if ("HTTPException(" in line or "log(" in line) and re.search(r"Claude|Anthropic", line) \
                    and not any(a in line for a in allowed):
                hits.append(f"{name}:{n}")
    assert hits == []


def test_ki_fehler_neutral():
    src = (ROOT / "web/app/ai.py").read_text(encoding="utf-8")
    body = src.split("def call(", 1)[1].split("\ndef ", 1)[0]
    assert not re.search(r"AIError\(f?\"[^\"]*(Claude|Anthropic)", body)
