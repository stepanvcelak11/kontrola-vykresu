"""Tisk CAD do PDF: správné měřítko, rozměr papíru, list s razítkem."""

import ezdxf
import pdfplumber
import pytest

from kontrola.cad import tisk as T

MM = 72 / 25.4


@pytest.fixture(scope="module", autouse=True)
def _app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _cary(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        pg = pdf.pages[0]
        return pg.width, pg.height, pg.lines + [c for c in pg.curves] + pg.rects


def test_model_v_meritku_na_a3(tmp_path):
    d = ezdxf.new("R2000")
    m = d.modelspace()
    m.add_line((-600000, -1160000), (-599900, -1160000))  # 100 m
    m.add_line((-600000, -1160000), (-600000, -1159950))  # 50 m
    f = tmp_path / "model.pdf"
    r = T.tisk_pdf(d, m, f, papir="A3", meritko=1000)
    w, h, cary = _cary(f)
    assert abs(w - 420 * MM) < 1 and abs(h - 297 * MM) < 1 and r["meritko"] == 1000
    delky = sorted(max(abs(c["x1"] - c["x0"]), abs(c["bottom"] - c["top"])) for c in cary)
    # 100 m v 1:1000 = 100 mm na papíře, 50 m = 50 mm (tolerance 0,3 mm)
    assert any(abs(x - 100 * MM) < 0.3 * MM for x in delky), delky
    assert any(abs(x - 50 * MM) < 0.3 * MM for x in delky), delky


def test_automaticke_meritko():
    assert T.automaticke_meritko((0, 0, 150, 100), (420, 297)) == 500
    assert T.automaticke_meritko((0, 0, 1000, 10), (420, 297)) == 2500


def test_list_s_razitkem(tmp_path):
    d = ezdxf.new("R2000")
    d.modelspace().add_circle((0, 0), 10)
    lay = d.layouts.new("A3")
    lay.page_setup(size=(420, 297), margins=(0, 0, 0, 0), units="mm")
    nove = T.ramecek_a_razitko(lay, udaje={"Název": "Účelová mapa Husovice", "Měřítko": "1:500"})
    assert any(e.dxftype() == "TEXT" and e.dxf.text == "Účelová mapa Husovice" for e in nove)
    f = tmp_path / "list.pdf"
    T.tisk_pdf(d, lay, f)
    # na bílém papíře musí být tmavé čáry (bílá barva 7 se tiskne černě) – rámeček a razítko
    import pypdfium2 as pdfium
    img = pdfium.PdfDocument(str(f))[0].render(scale=1).to_pil().convert("L")
    tmave = sum(1 for p in img.getdata() if p < 100)
    assert tmave > 2000
    assert img.getpixel((img.width // 2, img.height // 2)) > 200  # papír zůstal bílý
    with pytest.raises(ValueError):
        T.tisk_pdf(ezdxf.new(), ezdxf.new().modelspace(), tmp_path / "x.pdf")
