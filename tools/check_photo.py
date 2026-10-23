"""Foto einer Messunterlage pruefen und auf die Tischebene entzerren.

Aufruf:
    python tools/check_photo.py foto.jpg [--size A4|A3|K60H|K60D] [--out entzerrt.jpg]

Ohne --size wird das Format automatisch erkannt. Gibt die erkannten Marker und den
Leave-one-out-Restfehler je Marker aus und schreibt eine massstaebliche Draufsicht (px/mm aus dem Profil).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import vision  # noqa: E402

LABEL = {"gut": "gut", "brauchbar": "brauchbar", "unsicher": "unsicher – Papier plan? Foto senkrechter?",
         "nicht_auswertbar": "nicht auswertbar – mindestens 4 Marker frei, scharf und ohne Spiegelung"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--size", choices=["A4", "A3", "K60H", "K60D"], default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    img = vision.load_image(Path(a.image).read_bytes())
    r = vision.analyze(img, a.size)
    print(f"Erkannte Marker: {r['mat_ids']}  ·  Format: {r['format'] or '?'}"
          f"{' (automatisch)' if r.get('format_auto') else ''}")
    for k, v in sorted(r["loo_mm"].items(), key=lambda t: int(t[0])):
        print(f"  ID {k}: {v:.2f} mm")
    if r["max_err_mm"] is not None:
        print(f"Maximaler Restfehler: {r['max_err_mm']:.2f} mm")
    print(f"Bewertung: {LABEL[r['status']]}")
    if r.get("format_note"):
        print(r["format_note"])
    if r["homography"] is None:
        sys.exit(1)
    out = a.out or str(Path(a.image).with_name(Path(a.image).stem + "_entzerrt.jpg"))
    Path(out).write_bytes(vision.encode_jpg(vision.rectify_mat(img, r["homography"], r["format"]), 92))
    pxmm = vision.spec(r["format"])["pxmm"]
    print(f"Draufsicht gespeichert: {out} ({pxmm:g} px/mm, Ursprung unten links)")
    if r["gauge"]:
        g, rng = vision.rectify_gauge(img, r["gauge"])
        gout = str(Path(out).with_name(Path(out).stem + "_hoehenlehre.jpg"))
        Path(gout).write_bytes(vision.encode_jpg(g, 92))
        print(f"Höhenlehre {r['gauge']['strip']} erkannt → {gout} (x {rng[0]:g}…{rng[1]:g} mm, y {rng[2]:g}…{rng[3]:g} mm)")


if __name__ == "__main__":
    main()
