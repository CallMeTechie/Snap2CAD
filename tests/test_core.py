"""Kernfunktionen: PDF-Erzeugung und Marker-Auswertung."""
import io

import pytest

from core import matgen, vision


@pytest.mark.parametrize("fmt,grid", [("A4", [190, 230]), ("A3", [270, 360])])
def test_layout(fmt, grid):
    sp = matgen.layout(fmt)
    assert sp["grid_mm"] == grid
    assert len(sp["centers_mm"]) == 8
    hg = sp["height_gauge"]["centers_above_fold_mm"]
    assert {int(k) for k in hg} == {10, 11, 12, 13, 14, 15}
    assert float(hg[14] if 14 in hg else hg["14"]) == 30.0


@pytest.mark.parametrize("fmt", ["A4", "A3"])
def test_pdf_has_three_pages(fmt):
    import pypdfium2 as pdfium
    buf = io.BytesIO()
    matgen.build(buf, fmt, header="Werkstatt Test")
    pdf = pdfium.PdfDocument(buf.getvalue())
    assert len(pdf) == 3
    pdf.close()


def test_pdf_page_selection():
    import pypdfium2 as pdfium
    buf = io.BytesIO()
    matgen.build(buf, "A4", pages=["mat"])
    assert len(pdfium.PdfDocument(buf.getvalue())) == 1


def test_bad_format():
    with pytest.raises(ValueError):
        matgen.build(io.BytesIO(), "A5")


@pytest.mark.parametrize("fixture,fmt", [("photo_a4", "A4"), ("photo_a3", "A3")])
def test_analyze_detects_format_and_is_accurate(request, fixture, fmt):
    img = vision.load_image(request.getfixturevalue(fixture))
    a = vision.analyze(img)
    assert a["format"] == fmt and a["format_auto"]
    assert a["mat_ids"] == list(range(8))
    assert a["status"] == "gut"
    assert a["max_err_mm"] < 0.5


def test_rectify_scale(photo_a4):
    img = vision.load_image(photo_a4)
    a = vision.analyze(img)
    rect = vision.rectify_mat(img, a["homography"], "A4")
    assert rect.shape[1] == 1900 and rect.shape[0] == 2300  # 10 px/mm


def test_too_few_markers():
    import numpy as np
    blank = np.full((800, 600, 3), 200, np.uint8)
    a = vision.analyze(blank)
    assert a["status"] == "nicht_auswertbar"
    assert a["homography"] is None


def test_gauge_detected(photo_gauge):
    img = vision.load_image(photo_gauge)
    a = vision.analyze(img, "A4")
    g = a["gauge"]
    assert g is not None and len(g["ids"]) == 3
    assert g["rms_mm"] < 0.5
    out, (x0, x1, y0, y1) = vision.rectify_gauge(img, g)
    assert out.shape[0] == int((y1 - y0) * 10)


@pytest.mark.parametrize("fmt,ok", [("JPEG", True), ("PNG", True), ("WEBP", True), ("GIF", False), ("TIFF", False),
                                    ("BMP", False)])
def test_upload_formats_restricted(fmt, ok):
    """Nur Kamera-Formate werden dekodiert (kleinere Angriffsflaeche der Bild-Decoder)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, fmt)
    if ok:
        assert vision.load_image(buf.getvalue()).shape == (8, 8, 3)
    else:
        with pytest.raises(Exception):  # noqa: B017
            vision.load_image(buf.getvalue())


def _pages(pdf_bytes: bytes) -> int:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    n = len(pdf)
    pdf.close()
    return n


def test_profile_a4_a3_unveraendert():
    for f in ("A4", "A3"):
        sp = matgen.layout(f)
        assert (sp["pxmm"], sp["edge_scale"], sp["field"], sp["ctrl_mm"], sp["marker_pos"]) == (10.0, 1.0, "grid", 100.0, "grid")
        assert sp["quality_mm"] == [0.5, 1.0] and sp["hole_max_mm2"] == 2000.0 and sp["ids"] == list(range(8))
        assert "height_gauge" in sp


@pytest.mark.parametrize("f,ids,field", [("K60H", list(range(20, 28)), "plain_light"),
                                         ("K60D", list(range(30, 38)), "plain_dark")])
def test_profile_k60(f, ids, field):
    sp = matgen.layout(f)
    assert sp["grid_mm"] == [60, 80] and sp["marker_size_mm"] == 8.0 and sp["grid_origin_on_page_mm"] == [75.0, 170.0]
    assert sp["ids"] == ids and sp["field"] == field and sp["marker_pos"] == "frame"
    assert (sp["pxmm"], sp["edge_scale"], sp["ctrl_mm"]) == (30.0, 0.25, 50.0)
    assert sp["quality_mm"] == [0.125, 0.25] and sp["hole_max_mm2"] == pytest.approx(1256.6, abs=0.1)
    assert "height_gauge" not in sp
    assert sorted(int(k) for k in sp["centers_mm"]) == ids
    for x, y in sp["centers_mm"].values():  # Marker-Mitte mindestens 8 mm ausserhalb des Feldes
        assert x <= -8 or x >= 68 or y <= -8 or y >= 88


def test_print_formats_und_helfer():
    assert matgen.PRINT_FORMATS == {"A4": ("A4",), "A3": ("A3",), "K60": ("K60H", "K60D")}
    assert matgen.PRINT_PAGES["K60"] == ("mat", "dark", "guide") and matgen.PAGES == ("mat", "gauge", "guide")
    assert matgen.print_format_of("K60D") == "K60" and matgen.print_format_of("A3") == "A3"
    assert matgen.print_format_of(None) is None and matgen.print_format_of("A5") is None
    assert matgen.edge_scale("K60H") == 0.25 and matgen.edge_scale("A4") == 1.0 and matgen.edge_scale(None) == 1.0
    assert matgen.ctrl_ref("K60D") == 50.0 and matgen.ctrl_ref("A3") == 100.0 and matgen.ctrl_ref(None) == 100.0
    assert matgen.SIBLING == {"K60H": "K60D", "K60D": "K60H"}


def test_k60_pdf_drei_seiten_und_marker_erkennbar():
    from conftest import _render_page
    buf = io.BytesIO()
    spec = matgen.build(buf, "K60", header="Werkstatt Test")
    assert set(spec) == {"K60H", "K60D"}
    assert _pages(buf.getvalue()) == 3
    for i, f in enumerate(("K60H", "K60D")):
        assert sorted(vision.detect(_render_page("K60", i, 12.0))) == spec[f]["ids"]


def test_k60_spezifikationszeile_wie_layout():
    import pypdfium2 as pdfium
    buf = io.BytesIO()
    spec = matgen.build(buf, "K60")
    pdf = pdfium.PdfDocument(buf.getvalue())
    try:
        for i, f in enumerate(("K60H", "K60D")):
            txt = pdf[i].get_textpage().get_text_range()
            assert f"Kante {matgen.fmt(spec[f]['marker_size_mm'])} mm" in txt
            for k, (x, y) in spec[f]["centers_mm"].items():
                assert f"ID{k} ({matgen.fmt(x)}|{matgen.fmt(y)})" in txt, (f, k)
    finally:
        pdf.close()


def test_k60_feldfarbe_und_ueberstand():
    from conftest import _render_page
    px = 12.0
    for i, (lo, hi) in enumerate(((235, 256), (0, 60))):
        img = _render_page("K60", i, px)
        h = img.shape[0]
        for x_mm, y_mm in ((105, 210), (75.5, 170.5), (134.5, 249.5)):  # Feldmitte und 0,5 mm innerhalb der Feldecken
            v = int(img[int(h - y_mm * px), int(x_mm * px)].mean())
            assert lo <= v < hi, (i, x_mm, y_mm, v)


def test_k60_seitenwahl():
    for fmt, pages, n in (("K60", ["dark"], 1), ("K60", ["gauge"], 3), ("A4", ["dark"], 3), ("A4", ["mat"], 1)):
        buf = io.BytesIO()
        matgen.build(buf, fmt, pages=pages)
        assert _pages(buf.getvalue()) == n, (fmt, pages)


def test_build_nur_druckformate():
    for bad in ("A5", "K60H", "K60D"):
        with pytest.raises(ValueError, match="Format muss A4, A3 oder K60 sein"):
            matgen.build(io.BytesIO(), bad)
