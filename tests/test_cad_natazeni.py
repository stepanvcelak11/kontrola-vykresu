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


def test_smaz_cast():
    doc = ezdxf.new()
    msp = doc.modelspace()
    h = U.Historie(msp)
    ln = msp.add_line((0, 0), (10, 0))
    nove = U.smaz_cast(msp, h, ln, (7, 0.1), (3, -0.1))
    assert sorted((e.dxf.start.x, e.dxf.end.x) for e in nove) == [(0, 3), (7, 10)]
    pl = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)])
    nove = U.smaz_cast(msp, h, pl, (5, 0), (10, 5))
    assert sorted(len(list(e.vertices())) if e.dxftype() == "LWPOLYLINE" else 2 for e in nove) == [2, 2]
    konce = sorted((round(e.dxf.start.x, 6), round(e.dxf.start.y, 6)) for e in nove if e.dxftype() == "LINE")
    assert konce == [(0, 0), (10, 5)]
    ctverec = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
    nove = U.smaz_cast(msp, h, ctverec, (5, 0), (10, 5))  # smaže roh (10, 0), zbytek otevřená polylinie
    assert len(nove) == 1 and not nove[0].closed
    body = [tuple(round(v, 6) for v in p[:2]) for p in nove[0].get_points("xy")]
    assert body == [(10, 5), (10, 10), (0, 10), (0, 0), (5, 0)]
    kr = msp.add_circle((0, 0), 5)
    nove = U.smaz_cast(msp, h, kr, (5, 0), (0, 5))  # proti směru hodin od 0° do 90°
    assert nove[0].dxftype() == "ARC"
    assert (nove[0].dxf.start_angle, nove[0].dxf.end_angle) == (pytest.approx(90), pytest.approx(0))
    obl = msp.add_arc((0, 0), 5, 0, 180)
    nove = U.smaz_cast(msp, h, obl, (0, 5), (-5 * 0.7071, 5 * 0.7071))
    assert sorted(round(e.dxf.end_angle - e.dxf.start_angle) for e in nove) == [45, 90]
    for _ in range(5):
        h.krok_zpet()
    assert {e.dxftype() for e in msp} == {"LINE", "LWPOLYLINE", "CIRCLE", "ARC"} and len(msp) == 5
