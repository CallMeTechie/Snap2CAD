"""PDFs der Messunterlage erzeugen: python generator/make_mat.py <ausgabeordner>"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.matgen import PRINT_FORMATS, build  # noqa: E402

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "pdf"
    specs = {f: build(f"{out}/Messunterlage_{f}.pdf", f) for f in PRINT_FORMATS}
    print(json.dumps(specs, indent=1))
