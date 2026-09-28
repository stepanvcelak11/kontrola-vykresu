"""Testy umístění podkladu podle dvou bodů a porovnání popisů s PDF vzorem."""

import math

import pytest

from kontrola.georef import image_to_world, similarity_from_two_points


def test_umisteni_podle_dvou_bodu():
    h = 1000
    true = {"x": -743200.0, "y": -1043500.0, "meritko": 0.05, "rotace": 12.0}
    a, b = (100, 900), (800, 150)
    wa, wb = image_to_world(true, *a, h), image_to_world(true, *b, h)
    got = similarity_from_two_points(a, b, wa, wb, h)
    for k in true:
        assert math.isclose(got[k], true[k], abs_tol=1e-6)
    # libovolný třetí bod musí sedět
    c = (500, 500)
    assert all(math.isclose(p, q, abs_tol=1e-6)
               for p, q in zip(image_to_world(got, *c, h), image_to_world(true, *c, h)))


def test_totozne_body_chyba():
    with pytest.raises(ValueError):
        similarity_from_two_points((1, 1), (1, 1), (0, 0), (5, 5), 100)


def test_popisy_z_pdf_vzoru(tmp_path, make_dxf):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from kontrola.importer.pdf_vzor import compare_labels, pdf_labels

    pdf = tmp_path / "vzor.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    for i, t in enumerate(["125/1", "125/2", "126", "č.p. 12", "1001", "Měřítko 1:500"]):
        c.drawString(100, 700 - 20 * i, t)
    c.save()
    labels = pdf_labels(pdf)
    assert {"125/1", "125/2", "126", "12", "1001"} <= labels
    assert "500" not in labels  # měřítko není popis

    def build(msp, doc):
        msp.add_text("125/1", dxfattribs={"insert": (0, 0)})
        msp.add_text("126", dxfattribs={"insert": (0, 5)})
        msp.add_text("č.p. 12", dxfattribs={"insert": (0, 10)})
        msp.add_text("127", dxfattribs={"insert": (0, 15)})
    d = make_dxf(build)
    missing, extra = compare_labels(labels, d)
    assert missing == ["125/2", "1001"]
    assert extra == ["127"]
