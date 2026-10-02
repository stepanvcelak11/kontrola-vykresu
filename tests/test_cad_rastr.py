"""Rastrové podklady: world file, poloha pixelů, uložení jako DXF IMAGE."""

import ezdxf
import pytest

from kontrola.cad import rastr as RA
from kontrola.cad import upravy as U
from kontrola.cad.dokument import CadDokument


@pytest.fixture(scope="module", autouse=True)
def _app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _obrazek(tmp_path, wf: str | None):
    from PySide6.QtGui import QColor, QImage
    img = QImage(100, 50, QImage.Format_RGB32)
    img.fill(QColor("red"))
    f = tmp_path / "orto.png"
    img.save(str(f))
    if wf:
        (tmp_path / "orto.pgw").write_text(wf, encoding="ascii")
    return f


def test_world_file_ortofoto_sjtsk(tmp_path):
    # ortofoto ČÚZK v EPSG:5514: pixel 0,25 m, levý horní pixel se středem v (−600000, −1160000)
    f = _obrazek(tmp_path, "0.25\n0\n0\n-0.25\n-600000.0\n-1160000.0\n")
    dok = CadDokument()
    h = U.Historie(dok.msp)
    im = RA.pripoj(dok.doc, dok.msp, h, f, tmp_path)
    assert im.dxf.insert.isclose((-600000.125, -1160000.0 + 0.125 - 50 * 0.25, 0))
    assert im.dxf.u_pixel.isclose((0.25, 0, 0)) and im.dxf.v_pixel.isclose((0, 0.25, 0))
    # pixel (0,0) levý horní roh → přes QTransform na roh obrázku
    m11, m12, m21, m22, dx, dy = RA.qt_transform(im)
    assert abs(dx - (-600000.125)) < 1e-9 and abs(dy - (-1160000 + 0.125)) < 1e-9
    out = dok.uloz(tmp_path / "s_rastrem.dxf")
    d2 = ezdxf.readfile(out)
    im2 = next(iter(d2.modelspace().query("IMAGE")))
    assert im2.image_def.dxf.filename == "orto.png"
    assert RA.cesta_obrazku(im2, out.parent) == f.resolve()
    h.krok_zpet()
    assert not list(dok.msp.query("IMAGE"))


def test_rastr_bez_world_filu(tmp_path):
    f = _obrazek(tmp_path, None)
    dok = CadDokument()
    with pytest.raises(ValueError):
        RA.pripoj(dok.doc, dok.msp, None, f)
    im = RA.pripoj(dok.doc, dok.msp, None, f, vlozeni=(10, 20), sirka_m=50, natoceni=90)
    assert im.dxf.u_pixel.isclose((0, 0.5, 0), abs_tol=1e-12) and im.dxf.v_pixel.isclose((-0.5, 0, 0), abs_tol=1e-12)
    with pytest.raises(ValueError):
        RA.nacti_world_file(_w(tmp_path))


def _w(tmp_path):
    p = tmp_path / "spatny.wld"
    p.write_text("1\n2\n", encoding="ascii")
    return p


def test_world_file_tam_a_zpet(tmp_path):
    wf = (0.25, 0.01, 0.02, -0.25, -600000.0, -1160000.0)
    f = _obrazek(tmp_path, "\n".join(map(str, wf)))
    dok = CadDokument()
    im = RA.pripoj(dok.doc, dok.msp, U.Historie(dok.msp), f, tmp_path)
    assert all(abs(a - b) < 1e-9 for a, b in zip(RA.world_file_z_obrazku(im), wf))
    (tmp_path / "orto.pgw").unlink()
    out = RA.uloz_world_file(im, tmp_path)
    assert out.name == "orto.pgw" and all(abs(a - b) < 1e-9 for a, b in zip(RA.nacti_world_file(out), wf))


def test_georeference_rastru_afinne(tmp_path):
    f = _obrazek(tmp_path, "1\n0\n0\n-1\n0.5\n49.5\n")  # 100×50 px, 1 m, levý dolní roh (0, 0)
    dok = CadDokument()
    h = U.Historie(dok.msp)
    im = RA.pripoj(dok.doc, dok.msp, h, f, tmp_path)
    zdroj = [(0, 0), (100, 0), (0, 50), (100, 50)]
    cil = [(1000, 2000), (1200, 2000), (1000, 2100), (1200, 2100)]  # 2× větší a posunutý
    nove, tr, _p = U.transformace_vykresu(dok.msp, h, [im], zdroj, cil, "afinni")
    assert tr.m0 < 1e-9
    a, d, b, e, c, ff = RA.world_file_z_obrazku(nove[0])
    assert abs(a - 2) < 1e-9 and abs(e + 2) < 1e-9 and abs(c - 1001) < 1e-9 and abs(ff - 2099) < 1e-9
