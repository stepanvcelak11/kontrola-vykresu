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


def test_bloky():
    doc, msp, h, k = _novy()
    a = k.usecka((100, 100), (102, 100))
    b = k.kruznice((101, 100), 0.5)
    ins = U.vytvor_blok(doc, msp, h, [a, b], "ZNACKA", (101, 100))
    assert list(msp) == [ins] and ins.dxf.name == "ZNACKA" and "ZNACKA" in U.bloky(doc)
    blk = doc.blocks.get("ZNACKA")
    assert sorted(e.dxftype() for e in blk) == ["CIRCLE", "LINE"]
    assert next(e for e in blk if e.dxftype() == "CIRCLE").dxf.center.isclose((0, 0, 0))
    i2 = U.vloz_blok(doc, msp, h, "ZNACKA", (200, 50), 2.0, 90)
    v = [e for e in i2.virtual_entities() if e.dxftype() == "LINE"][0]
    assert v.dxf.start.isclose((200, 48, 0), abs_tol=1e-9) and v.dxf.end.isclose((200, 52, 0), abs_tol=1e-9)
    with pytest.raises(ValueError):
        U.vytvor_blok(doc, msp, h, [i2], "ZNACKA", (0, 0))
    with pytest.raises(ValueError):
        U.vloz_blok(doc, msp, h, "NENI", (0, 0))
    h.krok_zpet()
    h.krok_zpet()
    assert sorted(e.dxftype() for e in msp) == ["CIRCLE", "LINE"]
    d2 = _znovu_nacti(doc)
    assert "ZNACKA" in d2.blocks
    # rozpojení bloku vrátí prvky na místo
    h.krok_vpred()
    casti = U.rozpoj(msp, h, [ins])
    c = next(e for e in casti if e.dxftype() == "CIRCLE")
    assert c.dxf.center.isclose((101, 100, 0))


def test_vlastnosti_prvku_a_hledani():
    doc, msp, h, k = _novy()
    l = k.usecka((0, 0), (3, 4))
    v = dict((a, c) for a, _b, c in U.vlastnosti(l))
    assert v["_delka"] == 5 and v["start"] == (0, 0)
    n = U.nastav_vlastnosti(msp, h, l, {"end": (6, 8), "color": 1, "layer": "NOVA", "_delka": 99})
    assert n.dxf.end.isclose((6, 8, 0)) and n.dxf.color == 1 and "NOVA" in doc.layers and len(msp) == 1
    h.krok_zpet()
    assert list(msp) == [l]
    c = k.kruznice((0, 0), 2)
    with pytest.raises(ValueError):
        U.nastav_vlastnosti(msp, h, c, {"radius": 0})
    t1 = k.text((0, 0), "Parcela 12", 2)
    k.text((0, 5), "parcela 13", 2)
    t = U.nastav_vlastnosti(msp, h, t1, {"text": "Parcela 12/1", "height": 3.0})
    assert t.dxf.text == "Parcela 12/1" and t.dxf.height == 3.0
    assert len(U.najdi_text(msp, "PARCELA")) == 2
    assert U.nahrad_text(msp, h, "Parcela", "Pozemek") == 1
    assert sorted(e.dxf.text for e in msp.query("TEXT")) == ["Pozemek 12/1", "parcela 13"]
    h.krok_zpet()
    assert sorted(e.dxf.text for e in msp.query("TEXT")) == ["Parcela 12/1", "parcela 13"]
    p = k.polylinie([(0, 0), (10, 0), (10, 10), (0, 10)], uzavrena=True)
    assert dict((a, c) for a, _b, c in U.vlastnosti(p))["_vymera"] == pytest.approx(100)
    k.usecka((50, 50), (60, 60))
    assert len(U.vyber_podobne(msp, [l])) == 2  # obě úsečky ve vrstvě 0
    assert U.vyber_podobne(msp, [c], ("typ",)) == [c]


def test_rozdeleni_ohrada_omerne_miry_koty():
    doc, msp, h, k = _novy()
    l = k.usecka((0, 0), (10, 0))
    a, b = U.rozdel(msp, h, l, (4, 0.3))
    assert a.dxf.end.isclose((4, 0, 0)) and b.dxf.start.isclose((4, 0, 0)) and len(msp) == 2
    with pytest.raises(ValueError):
        U.rozdel(msp, h, a, (0, 0))
    p = k.polylinie([(0, 10), (10, 10), (10, 20)])
    p1, p2 = U.rozdel(msp, h, p, (10, 15))
    assert [tuple(q) for q in p1.get_points("xy")] == [(0, 10), (10, 10), (10, 15)]
    assert [tuple(q) for q in p2.get_points("xy")] == [(10, 15), (10, 20)]
    ob = k.oblouk_3body((10, 0), (0, 10), (-10, 0))
    o1, o2 = U.rozdel(msp, h, ob, (0, 10))
    assert abs(o1.dxf.end_angle - 90) < 1e-9 and abs(o2.dxf.start_angle - 90) < 1e-9
    ix = U.IndexVyberu(msp)
    vyb = ix.ohrada([(-1, -1), (5, -1), (5, 1), (-1, 1)])
    assert vyb == [a]
    assert set(ix.ohrada([(-1, -1), (5, -1), (5, 1), (-1, 1)], protinajici=True)) >= {a, b}
    # oměrné míry: 4.00 a 6.00, text rovnoběžně se stranou a nad ní
    t = U.popis_delek(msp, h, [a, b], 1.0)
    assert sorted(x.dxf.text for x in t) == ["4.00", "6.00"]
    assert all(abs(x.dxf.rotation) < 1e-9 and x.dxf.align_point.y > 0 for x in t)
    tv = U.popis_delek(msp, h, [U.nastav_vlastnosti(msp, h, a, {"start": (4, 0), "end": (0, 0)})], 1.0)
    assert abs(tv[0].dxf.rotation) < 1e-9  # obrácená úsečka – text pořád čitelný
    c = k.kruznice((50, 50), 7)
    kp = U.kota_polomeru(msp, h, c, (57, 50))
    assert abs(kp.get_measurement() - 7) < 1e-9
    ku = U.kota_uhlu(msp, h, (0, 0), (10, 0), (0, 10), (5, 5))
    assert abs(math.degrees(ku.get_measurement()) - 90) < 1e-6 or abs(ku.get_measurement() - 90) < 1e-6


def test_zkoseni_a_vrcholy():
    doc, msp, h, k = _novy()
    a = k.usecka((0, 0), (10, 0))
    b = k.usecka((10, -2), (10, 10))
    l1, l2, z = U.zkos(msp, h, a, (2, 0), b, (10, 8), 2, 3)
    assert (l1.dxf.end.x, l1.dxf.end.y) == pytest.approx((8, 0))
    assert (l2.dxf.end.x, l2.dxf.end.y) == pytest.approx((10, 3))
    assert z.dxf.start.distance(z.dxf.end) == pytest.approx(math.hypot(2, 3))
    with pytest.raises(ValueError):
        U.zkos(msp, h, l1, (2, 0), l2, (10, 2), 50)
    assert len(msp.query("LINE")) == 3  # chybné zkosení výkres nezměnilo
    h.krok_zpet()
    assert {e.dxf.handle for e in msp.query("LINE")} == {a.dxf.handle, b.dxf.handle}

    p = k.polylinie([(0, 0), (10, 0), (10, 10)])
    p2 = U.vloz_vrchol(msp, h, p, (5, 0.1), (5, -2))
    assert [tuple(q[:2]) for q in p2.get_points("xy")] == [(0, 0), (5, -2), (10, 0), (10, 10)]
    p3 = U.posun_vrchol(msp, h, p2, (9.8, 9.9), (12, 12))
    assert tuple(list(p3.get_points("xy"))[-1]) == pytest.approx((12, 12))
    p4 = U.smaz_vrchol(msp, h, p3, (5, -2))
    assert len(p4) == 3
    p5 = U.smaz_vrchol(msp, h, p4, (0, 0))
    with pytest.raises(ValueError):
        U.smaz_vrchol(msp, h, p5, (10, 0))
    l = k.usecka((0, 0), (4, 0))
    pl = U.vloz_vrchol(msp, h, l, (2, 0), (2, 1))
    assert pl.dxftype() == "LWPOLYLINE" and len(pl) == 3 and l.dxf.owner is None
    l2 = U.posun_vrchol(msp, h, k.usecka((0, 0), (4, 0)), (3.9, 0), (5, 5))
    assert (l2.dxf.end.x, l2.dxf.end.y) == (5, 5)
    for _ in range(3):  # posun vrcholu, nakreslení úsečky, vložení vrcholu
        h.krok_zpet()
    assert l.dxf.owner is not None


def test_pole_obdelnikove_a_kruhove():
    doc, msp, h, k = _novy()
    c = k.kruznice((0, 0), 1)
    nove = U.pole_obdelnikove(msp, h, [c], 2, 3, 10, 5)
    assert len(nove) == 5
    assert sorted((e.dxf.center.x, e.dxf.center.y) for e in msp.query("CIRCLE")) == [
        (0, 0), (0, 5), (10, 0), (10, 5), (20, 0), (20, 5)]
    h.krok_zpet()
    assert len(msp.query("CIRCLE")) == 1
    l = k.usecka((10, 0), (12, 0))
    nove = U.pole_kruhove(msp, h, [l], (0, 0), 4, math.pi / 2)
    konce = sorted((round(e.dxf.start.x, 9) + 0.0, round(e.dxf.start.y, 9) + 0.0) for e in msp.query("LINE"))
    assert konce == [(-10, 0), (0, -10), (0, 10), (10, 0)]
    assert any(abs(e.dxf.end.y - 12) < 1e-9 for e in nove)  # otočené i prvky
    h.krok_zpet()
    nove = U.pole_kruhove(msp, h, [l], (0, 0), 2, math.pi, otacet=False)
    assert (nove[0].dxf.start.x, nove[0].dxf.end.x) == pytest.approx((-12, -10))  # jen posun
    with pytest.raises(ValueError):
        U.pole_obdelnikove(msp, h, [l], 1, 1, 1, 1)
