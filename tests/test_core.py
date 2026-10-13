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
