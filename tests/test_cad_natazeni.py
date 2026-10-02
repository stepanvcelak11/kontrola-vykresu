import ezdxf
import pytest

from kontrola.cad import upravy as U


def test_natazeni_oblouky_texty_bulge():
    doc = ezdxf.new()
    msp = doc.modelspace()
    h = U.Historie(msp)
    obl_uvnitr = msp.add_arc((5, 5), 1, 0, 90)
    obl_napul = msp.add_arc((0, 5), 5, 0, 90)  # konec (0, 10) mimo okno
    txt = msp.add_text("A", dxfattribs={"insert": (4, 4), "height": 1})
    pl = msp.add_lwpolyline([(0, 0, 0, 0, 0.5), (5, 0, 0, 0, 0), (5, 5)], format="xyseb")
    nove = U.natahni(msp, h, [obl_uvnitr, obl_napul, txt, pl], (3, -1), (8, 8), 10, 0)
    assert len(nove) == 3  # oblouk napůl v okně zůstane
    a = [e for e in msp.query("ARC") if e.dxf.radius == 1][0]
    assert a.dxf.center.x == pytest.approx(15)
    assert msp.query("TEXT")[0].dxf.insert.x == pytest.approx(14)
    p = msp.query("LWPOLYLINE")[0].get_points("xyseb")
    assert [(q[0], q[1], q[4]) for q in p] == [(0, 0, 0.5), (15, 0, 0), (15, 5, 0)]  # bulge zachován
    h.krok_zpet()
    assert msp.query("TEXT")[0].dxf.insert.x == pytest.approx(4)
