"""CAD – kreslení a úpravy s Zpět/Vpřed; výsledky ověřené výpočtem a uložením do DXF a zpět."""

import io
import math

import ezdxf
import pytest

from kontrola.cad import upravy as U


def _novy():
    doc = ezdxf.new("R2000", setup=True)
    msp = doc.modelspace()
    h = U.Historie(msp)
    return doc, msp, h, U.Kresleni(msp, h)


def _znovu_nacti(doc):
    s = io.StringIO()
    doc.write(s)
    return ezdxf.read(io.StringIO(s.getvalue()))


def test_kresleni_a_ulozeni():
    doc, msp, h, k = _novy()
    k.vrstva = "HRANICE"
    doc.layers.add("HRANICE")
    k.bod((1, 2))
    k.usecka((0, 0), (10, 0))
    k.polylinie([(0, 0), (5, 0), (5, 5)], uzavrena=True)
    k.obdelnik((20, 20), (30, 25))
    k.kruznice((50, 50), 3)
    ob = k.oblouk_3body((10, 0), (0, 10), (-10, 0))
    assert abs(ob.dxf.radius - 10) < 1e-12 and abs(ob.dxf.start_angle) < 1e-9 and abs(ob.dxf.end_angle - 180) < 1e-9
    ob2 = k.oblouk_3body((-10, 0), (0, -10), (10, 0))  # spodní půlkruh: CCW z (−10,0) přes (0,−10)
    assert abs(ob2.dxf.start_angle - 180) < 1e-9 and abs(ob2.dxf.end_angle % 360) < 1e-9
    k.elipsa((0, 0), (10, 0), 4)
    k.krivka([(0, 0), (1, 1), (2, 0), (3, 1)])
    k.text((5, 5), "Příliš žluťoučký kůň", 2.0, 30)
    kr = k.kruznice((100, 100), 5)
    k.sraf(kr)
    k.kota((0, 0), (10, 0), (5, 3))
    with pytest.raises(ValueError):
        k.oblouk_3body((0, 0), (1, 1), (2, 2))
    with pytest.raises(ValueError):
        k.usecka((1, 1), (1, 1))
    d2 = _znovu_nacti(doc)
    typy = sorted(e.dxftype() for e in d2.modelspace())
    assert typy == sorted(["POINT", "LINE", "LWPOLYLINE", "LWPOLYLINE", "CIRCLE", "ARC", "ARC", "ELLIPSE",
                           "SPLINE", "TEXT", "CIRCLE", "HATCH", "DIMENSION"])
    t = next(e for e in d2.modelspace() if e.dxftype() == "TEXT")
    assert t.dxf.text == "Příliš žluťoučký kůň" and t.dxf.layer == "HRANICE"
    dim = next(e for e in d2.modelspace() if e.dxftype() == "DIMENSION")
    assert abs(dim.get_measurement() - 10) < 1e-12


def test_zpet_vpred_neomezene():
    doc, msp, h, k = _novy()
    for i in range(300):
        k.usecka((i, 0), (i, 1))
    assert len(msp) == 300
    for _ in range(300):
        assert h.krok_zpet() is not None
    assert len(msp) == 0 and h.krok_zpet() is None
    for _ in range(150):
        h.krok_vpred()
    assert len(msp) == 150
    # nová operace smaže možnost Vpřed
    k.bod((0, 0))
    assert h.krok_vpred() is None and len(msp) == 151
    assert len(list(_znovu_nacti(doc).modelspace())) == 151


def test_transformace_a_zpet():
    doc, msp, h, k = _novy()
    l = k.usecka((600000.0, 1160000.0), (600010.0, 1160000.0))
    (n,) = U.posun(msp, h, [l], 5, 5)
    assert (n.dxf.start.x, n.dxf.start.y) == (600005.0, 1160005.0) and len(msp) == 1
    (o,) = U.otoc(msp, h, [n], (600005.0, 1160005.0), math.pi / 2)
    assert abs(o.dxf.end.x - 600005.0) < 1e-9 and abs(o.dxf.end.y - 1160015.0) < 1e-9
    (m,) = U.meritko(msp, h, [o], (600005.0, 1160005.0), 2.0)
    assert abs(m.dxf.end.y - 1160025.0) < 1e-9
    (z,) = U.zrcadli(msp, h, [m], (0, 1160000.0), (1, 1160000.0), kopie=True)
    assert abs(z.dxf.end.y - (1160000.0 - 25.0)) < 1e-9 and len(msp) == 2
    kk = U.kopie_vicenasobna(msp, h, [z], 1, 0, 3)
    assert len(kk) == 3 and len(msp) == 5
    for _ in range(5):
        h.krok_zpet()
    assert len(msp) == 1 and next(iter(msp)) is l
    assert (l.dxf.end.x, l.dxf.end.y) == (600010.0, 1160000.0)  # původní prvek beze změny


def test_rovnobezka():
    doc, msp, h, k = _novy()
    l = k.usecka((0, 0), (10, 0))
    r = U.rovnobezka(msp, h, l, 2.5, (3, -1))
    assert r.dxf.start.y == -2.5 and r.dxf.end.y == -2.5
    c = k.kruznice((0, 0), 5)
    assert U.rovnobezka(msp, h, c, 1, (0, 0.5)).dxf.radius == 4
    assert U.rovnobezka(msp, h, c, 1, (0, 9)).dxf.radius == 6
    with pytest.raises(ValueError):
        U.rovnobezka(msp, h, c, 6, (0, 0))
    p = k.polylinie([(0, 0), (10, 0), (10, 10)])
    rp = U.rovnobezka(msp, h, p, 1, (5, 1))  # dovnitř rohu
    pts = [tuple(round(v, 9) for v in q[:2]) for q in rp.get_points("xy")]
    assert pts == [(0, 1), (9, 1), (9, 10)] or pts == [(9, 10), (9, 1), (0, 1)]


def test_orez_a_prodlouzeni():
    doc, msp, h, k = _novy()
    l = k.usecka((0, 0), (10, 0))
    s1 = k.usecka((3, -1), (3, 1))
    s2 = k.usecka((7, -1), (7, 1))
    nove = U.orez(msp, h, l, (5, 0), list(msp))
    assert sorted((round(e.dxf.start.x, 9), round(e.dxf.end.x, 9)) for e in nove) == [(0, 3), (7, 10)]
    h.krok_zpet()
    nove = U.orez(msp, h, l, (9, 0.1), list(msp))
    assert [(e.dxf.start.x, e.dxf.end.x) for e in nove] == [(0, 7)]
    # prodloužení krátké úsečky ke kružnici
    c = k.kruznice((20, 0), 2)
    kr = k.usecka((12, 0), (15, 0))
    p = U.prodluz(msp, h, kr, (14.9, 0), list(msp))
    assert abs(p.dxf.end.x - 18) < 1e-12 and p.dxf.start.x == 12
    # ořez oblouku a kružnice
    U.orez(msp, h, c, (22, 0), [c, k.usecka((20, -5), (20, 5))])
    arc = [e for e in msp if e.dxftype() == "ARC"][-1]
    assert abs(arc.dxf.start_angle % 360 - 90) < 1e-9 and abs(arc.dxf.end_angle % 360 - 270) < 1e-9
    with pytest.raises(ValueError):
        U.orez(msp, h, k.usecka((100, 100), (101, 100)), (100.5, 100), list(msp))
    assert s1.dxf.owner and s2.dxf.owner


def test_zaobleni_a_roh():
    doc, msp, h, k = _novy()
    a = k.usecka((0, 0), (12, 0))
    b = k.usecka((10, -2), (10, 10))
    l1, l2, arc = U.zaobli(msp, h, a, (2, 0), b, (10, 8), 3)
    assert (l1.dxf.start.x, l1.dxf.end.x) == (0, 7) and abs(l2.dxf.end.y - 3) < 1e-12
    assert abs(arc.dxf.center.x - 7) < 1e-12 and abs(arc.dxf.center.y - 3) < 1e-12 and arc.dxf.radius == 3
    assert abs(arc.dxf.start_angle % 360 - 270) < 1e-9 and abs(arc.dxf.end_angle % 360) < 1e-9
    h.krok_zpet()
    l1, l2 = U.zaobli(msp, h, a, (2, 0), b, (10, 8), 0)
    assert (l1.dxf.end.x, l1.dxf.end.y) == (10, 0) and (l2.dxf.end.x, l2.dxf.end.y) == (10, 0)
    with pytest.raises(ValueError):
        U.zaobli(msp, h, l1, (2, 0), l2, (10, 8), 100)


def test_spojeni_a_rozpojeni():
    doc, msp, h, k = _novy()
    e1 = k.usecka((0, 0), (10, 0))
    e2 = k.usecka((10, 10), (10, 0))  # obráceně
    e3 = k.oblouk_3body((10, 10), (5, 15), (0, 10))
    e4 = k.usecka((0, 10), (0, 0))
    p = U.spoj(msp, h, [e1, e2, e3, e4])
    assert p.closed and len(msp) == 1 and len(p) == 4
    g = U.geometrie(p)
    plocha = 100 + math.pi * 25 / 2
    from shapely.geometry import Polygon
    assert abs(Polygon(g.coords).area - plocha) < 0.1  # geometrie pro výběr je zjednodušená (0,01 m)
    assert sorted(round(abs(b), 12) for *_xy, b in p.get_points("xyb")) == [0, 0, 0, 1]  # půlkruh: bulge 1
    casti = U.rozpoj(msp, h, [p])
    assert sorted(e.dxftype() for e in casti) == ["ARC", "LINE", "LINE", "LINE"]
    h.krok_zpet()
    h.krok_zpet()
    assert len(msp) == 4
    with pytest.raises(ValueError):
        U.spoj(msp, h, [e1, k.usecka((50, 50), (60, 60))])


def test_vyber_kliknutim_a_oknem():
    doc, msp, h, k = _novy()
    l = k.usecka((0, 0), (10, 0))
    c = k.kruznice((20, 0), 2)
    t = k.text((40, 0), "ABC", 2)
    ix = U.IndexVyberu(msp)
    assert ix.najdi(5, 0.1, 0.5) is l and ix.najdi(22.1, 0, 0.5) is c and ix.najdi(20, 0, 0.5) is None
    assert ix.najdi(41, 1, 0.5) is t
    assert set(ix.okno(-1, -5, 25, 5)) == {l, c}
    assert set(ix.okno(5, -1, 19, 1, protinajici=True)) == {l, c}
    assert ix.okno(5, -1, 19, 1) == []


def test_vlastnosti_a_smazani():
    doc, msp, h, k = _novy()
    doc.layers.add("NOVA")
    l = k.usecka((0, 0), (1, 0))
    (n,) = U.zmen_vlastnosti(msp, h, [l], layer="NOVA", color=1)
    assert n.dxf.layer == "NOVA" and n.dxf.color == 1 and l.dxf.layer == "0"
    U.smaz(h, [n])
    assert len(msp) == 0
    h.krok_zpet()
    h.krok_zpet()
    assert list(msp) == [l]
