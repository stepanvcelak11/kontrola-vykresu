"""Ověření dalších úloh Gromy (průsečíky, vytyčení, výšky, nivelace, ortogonální metoda, polygonový pořad,
oddělení parcely) na příkladech se známým výsledkem a nezávislým výpočtem."""

import math
import random

import pytest
from shapely.geometry import Point, Polygon

from kontrola.geodezie import vypocty as V


def _uhel(st, zad, pred):
    """Vrcholový úhel měřený po směru hodin od zadní k přední záměře."""
    return V.norm_gon(V.smernik(st, pred) - V.smernik(st, zad))


def test_prusecik_primek_proti_shapely():
    rnd = random.Random(3)
    for _ in range(200):
        a1, a2, b1, b2 = [(rnd.uniform(-1e3, 1e3) + 600000, rnd.uniform(-1e3, 1e3) + 1160000) for _ in range(4)]
        try:
            p = V.prusecik_primek(a1, a2, b1, b2)
        except ValueError:
            continue
        # bod leží na obou přímkách
        for u, v in ((a1, a2), (b1, b2)):
            cross = (v[0] - u[0]) * (p.x - u[1]) - (v[1] - u[1]) * (p.y - u[0])
            assert abs(cross) / V.delka(u, v) < 1e-6
    with pytest.raises(ValueError):
        V.prusecik_primek((0, 0), (1, 1), (0, 1), (1, 2))


def test_prusecik_primky_kruznice_a_kruznic():
    body = V.prusecik_primky_kruznice((-10, 0), (10, 0), (0, 0), 5)
    assert [(round(p.y, 9), round(p.x, 9)) for p in body] == [(-5, 0), (5, 0)]
    assert V.prusecik_primky_kruznice((-10, 6), (10, 6), (0, 0), 5) == []
    tecna = V.prusecik_primky_kruznice((-10, 5), (10, 5), (0, 0), 5)
    assert len(tecna) == 1 and abs(tecna[0].y) < 1e-9
    # proti Shapely
    rnd = random.Random(7)
    for _ in range(100):
        s = (rnd.uniform(-50, 50), rnd.uniform(-50, 50))
        r = rnd.uniform(1, 40)
        a, b = (rnd.uniform(-60, 60), rnd.uniform(-60, 60)), (rnd.uniform(-60, 60), rnd.uniform(-60, 60))
        for p in V.prusecik_primky_kruznice(a, b, s, r):
            assert abs(V.delka(p, s) - r) < 1e-7
        ps = V.prusecik_kruznic(s, r, (s[0] + 10, s[1] + 3), r * 0.8)
        for p in ps:
            assert abs(V.delka(p, s) - r) < 1e-7
            assert abs(V.delka(p, (s[0] + 10, s[1] + 3)) - r * 0.8) < 1e-7
    assert V.prusecik_kruznic((0, 0), 1, (5, 0), 1) == []
    assert len(V.prusecik_kruznic((0, 0), 3, (5, 0), 4)) == 2


def test_vytycovaci_prvky_zpetne():
    st, o = (1000.0, 2000.0), (1100.0, 2050.0)
    for b in [(1050.0, 1900.0), (900.0, 2100.0), (1000.0, 2100.0)]:
        uhel, d, sm = V.vytycovaci_prvky(st, o, b)
        p = V.rajon(st, V.smernik(st, o) + uhel, d)
        assert abs(p.y - b[0]) < 1e-9 and abs(p.x - b[1]) < 1e-9
        assert 0 <= uhel < 400 and abs(sm - V.smernik(st, b)) < 1e-12


def test_trigonometricka_vyska():
    # vodorovná záměra 100 m: převýšení jen ze zakřivení a refrakce
    h, dh = V.trigonometricka_vyska(250.0, 100.0, 100.0)
    assert abs(dh - 100 ** 2 * 0.87 / (2 * 6380000)) < 1e-12
    # 45°: dh = d·cos z + vp − vc
    h, dh = V.trigonometricka_vyska(250.0, 100.0, 50.0, vp=1.5, vc=1.8, k_refr=1.0)
    assert abs(dh - (100 / math.sqrt(2) - 0.3)) < 1e-9 and abs(h - 250.0 - dh) < 1e-12


def test_nivelacni_porad():
    # skutečné výšky 300.000 → 301.000 → 299.500 → 300.250, měřeno s chybou +6 mm
    od = [("1", 1.002, 400.0), ("2", -1.498, 600.0), ("3", 0.752, 1000.0)]
    r = V.nivelacni_porad(300.0, 300.25, od)
    assert abs(r.odchylka - 0.006) < 1e-12
    assert abs(r.vysky[-1][1] - 300.25) < 1e-12  # vyrovnaný pořad končí přesně na daném bodě
    assert abs(sum(r.opravy) + 0.006) < 1e-12
    assert abs(r.opravy[0] / r.opravy[2] - 0.4) < 1e-12  # úměrně délkám
    assert abs(r.mezni - 0.040 * math.sqrt(2.0)) < 1e-12 and r.vyhovuje
    assert not V.nivelacni_porad(300.0, 300.25, [("3", 0.40, 100.0)]).vyhovuje
    with pytest.raises(ValueError):
        V.nivelacni_porad(1, 2, [])


def test_ortogonalni_davka_s_meritkem():
    a, b = (1000.0, 1000.0), (1030.0, 1040.0)  # délka 50 m
    body, q, odch = V.ortogonalni_davka(a, b, [("1", 25.0, 0.0), ("2", 10.0, 3.0)])
    assert q == 1.0 and odch == 0.0
    assert abs(body[0][1].y - 1015.0) < 1e-12 and abs(body[0][1].x - 1020.0) < 1e-12
    st, k = V.stanicni_kolmice(a, b, body[1][1])
    assert abs(st - 10.0) < 1e-12 and abs(k - 3.0) < 1e-12
    # měřená délka 50.02 → měřítko 50/50.02, konec měření padne přesně na B
    body, q, odch = V.ortogonalni_davka(a, b, [("B", 50.02, 0.0)], delka_merena=50.02)
    assert abs(odch + 0.02) < 1e-12
    assert abs(body[0][1].y - b[0]) < 1e-9 and abs(body[0][1].x - b[1]) < 1e-9


def _porad(rnd):
    a_or = (rnd.uniform(-1e4, 1e4) + 600000, rnd.uniform(-1e4, 1e4) + 1100000)
    a = (a_or[0] + rnd.uniform(200, 500), a_or[1] + rnd.uniform(-300, 300))
    body = [a]
    for _ in range(rnd.randint(1, 6)):
        y, x = body[-1]
        body.append((y + rnd.uniform(50, 250), x + rnd.uniform(-200, 200)))
    b_or = (body[-1][0] + rnd.uniform(200, 500), body[-1][1] + rnd.uniform(-300, 300))
    seq = [a_or] + body + [b_or]
    uhly = [_uhel(seq[i], seq[i - 1], seq[i + 1]) for i in range(1, len(seq) - 1)]
    delky = [V.delka(body[i], body[i + 1]) for i in range(len(body) - 1)]
    return a_or, a, body[1:-1], body[-1], b_or, uhly, delky


def test_polygonovy_porad_bez_chyb_je_presny():
    rnd = random.Random(11)
    for _ in range(50):
        a_or, a, nove, b, b_or, uhly, delky = _porad(rnd)
        r = V.polygonovy_porad(a, a_or, b, b_or, uhly, delky, [str(i) for i in range(len(nove))])
        assert abs(r.uhlova_odchylka) < 1e-9 and r.polohova < 1e-6
        for (_c, p), q in zip(r.body, nove):
            assert abs(p.y - q[0]) < 1e-6 and abs(p.x - q[1]) < 1e-6


def test_polygonovy_porad_rozdeli_chyby():
    rnd = random.Random(5)
    a_or, a, nove, b, b_or, uhly, delky = _porad(rnd)
    n = len(nove)
    uhly = [u + 0.0010 for u in uhly]  # každý úhel +10 cc
    delky = [d + 0.01 for d in delky]
    r = V.polygonovy_porad(a, a_or, b, b_or, uhly, delky, [str(i) for i in range(n)])
    assert abs(r.uhlova_odchylka - 0.0010 * (n + 2)) < 1e-9
    assert 0 < r.polohova < 0.01 * (n + 1) + 0.05
    # odchylky se rozdělí: pořad vyrovnaný znovu by měl nulovou souřadnicovou odchylku
    pts = [a] + [(p.y, p.x) for _c, p in r.body] + [b]
    for i in range(len(pts) - 1):
        assert abs(V.delka(pts[i], pts[i + 1]) - delky[i]) < 0.05
    with pytest.raises(ValueError):
        V.polygonovy_porad(a, a_or, b, b_or, uhly[:-1], delky, [str(i) for i in range(n)])


def test_oddeleni_rovnobezne():
    parc = [(0, 0), (100, 0), (100, 50), (0, 50)]  # 5000 m²
    cast, t = V.oddeleni_rovnobezne(parc, (0, 0), (100, 0), 1234.5)
    assert abs(Polygon([(p.y, p.x) for p in cast]).area - 1234.5) < 1e-5
    assert abs(t - 12.345) < 1e-6
    # nepravidelná parcela, dělení rovnoběžně s šikmou hranicí
    parc = [(600000, 1160000), (600080, 1160010), (600095, 1160070), (600020, 1160090), (599990, 1160040)]
    plocha = Polygon(parc).area
    for cil in (0.1 * plocha, 0.5 * plocha, 0.93 * plocha):
        cast, t = V.oddeleni_rovnobezne(parc, parc[0], parc[1], cil)
        g = Polygon([(p.y, p.x) for p in cast])
        assert abs(g.area - cil) < 1e-4
        assert g.buffer(1e-6).contains(Point(parc[0])) or g.buffer(1e-6).contains(Point(parc[1]))
    with pytest.raises(ValueError):
        V.oddeleni_rovnobezne(parc, parc[0], parc[1], plocha * 2)


def test_ulohy_formulare_polygon_a_wgs():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.ui.ulohy import u_oddeleni, u_ortogonalni, u_polygon, u_prusecik, u_wgs
    rnd = random.Random(2)
    a_or, a, nove, b, b_or, uhly, delky = _porad(rnd)
    s = SeznamBodu()
    s.pridej([Bod("AO", *a_or), Bod("A", *a), Bod("B", *b), Bod("BO", *b_or)])
    cisla = ["A"] + [f"N{i}" for i in range(len(nove))] + ["B"]
    r = u_polygon(s, {"ao": "AO", "a": "A", "b": "B", "bo": "BO",
                      "uhly": "\n".join(f"{c} {u!r}" for c, u in zip(cisla, uhly)),
                      "delky": "\n".join(f"{c} {d!r}" for c, d in zip(cisla, delky))})
    assert [n.cislo for n in r.nove] == cisla[1:-1]
    for n, q in zip(r.nove, nove):
        assert abs(n.y - q[0]) < 1e-6 and abs(n.x - q[1]) < 1e-6
    # WGS84 tam a zpět přes formulář (Brno, ~1 m přesnost převodu, ale tam-zpět na mm)
    s.pridej([Bod("BR", 598000.0, 1160000.0)])
    t = "\n".join(u_wgs(s, {"smer": "S-JTSK → WGS84", "body": "BR"}).protokol)
    assert "mapy.cz" in t and "49°" in t and "16°" in t
    from kontrola.geodezie import sjtsk as J
    la, lo, _ = J.sjtsk_na_wgs84(598000.0, 1160000.0)
    zpet = u_wgs(s, {"smer": "WGS84 → S-JTSK", "wgs": f"Z {la!r} {lo!r}"}).nove[0]
    assert abs(zpet.y - 598000.0) < 0.01 and abs(zpet.x - 1160000.0) < 0.01
    # průsečík a ortogonální metoda
    s.pridej([Bod("P1", 0, 0), Bod("P2", 10, 10), Bod("P3", 0, 10), Bod("P4", 10, 0)])
    p = u_prusecik(s, {"druh": "dvou přímek", "a": "P1", "b": "P2", "c": "P3", "d": "P4", "nove": "X"}).nove[0]
    assert abs(p.y - 5) < 1e-12 and abs(p.x - 5) < 1e-12
    assert len(u_prusecik(s, {"druh": "dvou kružnic", "a": "P1", "b": "P4", "r1": "8", "r2": "8",
                              "nove": "K"}).nove) == 2
    o = u_ortogonalni(s, {"a": "P1", "b": "P3", "mereni": "O1 5 2"}).nove[0]
    assert abs(o.x - 5) < 1e-12 and abs(abs(o.y) - 2) < 1e-12
    # oddělení čtverce 10×10 na polovinu
    r = u_oddeleni(s, {"body": "P1 P4 P2 P3", "a": "P1", "b": "P4", "vymera": "50", "predpona": "D"})
    assert len(r.nove) == 2 and all(abs(n.x - 5) < 1e-6 for n in r.nove)
    # dělicí čarou z rohu P1: polovina čtverce → úhlopříčka do P2 (jediný nový bod není, P2 je daný)
    r = u_oddeleni(s, {"zpusob": "dělicí čarou z bodu A", "body": "P1 P4 P2 P3", "a": "P1", "vymera": "25"})
    assert len(r.nove) == 1 and (r.nove[0].y, r.nove[0].x) == pytest.approx((10, 5))
    assert "dělicí čarou z bodu" in r.protokol[0] + "".join(r.protokol)


def test_oddeleni_bodem():
    parc = [(0, 0), (100, 0), (100, 50), (0, 50)]  # 5000 m²
    cast, q = V.oddeleni_bodem(parc, (0, 0), 1000)
    assert abs(Polygon([(p.y, p.x) for p in cast]).area - 1000) < 1e-6
    assert (q.y, q.x) == pytest.approx((100, 20))
    cast, q = V.oddeleni_bodem(parc, (50, 0), 3000)  # bod na straně
    assert abs(Polygon([(p.y, p.x) for p in cast]).area - 3000) < 1e-6
    assert (q.y, q.x) == pytest.approx((30, 50))
    parc = [(600000, 1160000), (600080, 1160010), (600095, 1160070), (600020, 1160090), (599990, 1160040)]
    plocha = Polygon(parc).area
    for cil in (0.1 * plocha, 0.5 * plocha, 0.9 * plocha):
        for orient in (parc, parc[::-1]):
            cast, q = V.oddeleni_bodem(orient, parc[0], cil)
            assert abs(Polygon([(p.y, p.x) for p in cast]).area - cil) < 1e-6
            assert Polygon(parc).exterior.distance(Point(q.y, q.x)) < 1e-6
    with pytest.raises(ValueError):
        V.oddeleni_bodem(parc, (600050, 1160050), 100)  # bod uvnitř


def test_jungova_dotransformace():
    zdroj = [(0, 0), (100, 0), (100, 100), (0, 100)]
    cil = [(1000.00, 2000.00), (1100.02, 2000.00), (1100.00, 2100.03), (999.98, 2100.00)]
    t = V.transformace(zdroj, cil, "podobnostni")
    for q, c in zip(zdroj, cil):  # identické body dostanou přesně cílové souřadnice
        assert t.preved_jung(q, zdroj) == pytest.approx(c, abs=1e-9)
    # bod uprostřed: oprava = průměr oprav (stejné vzdálenosti)
    y, x = t.preved_jung((50, 50), zdroj)
    y0, x0 = t.preved((50, 50))
    vy = sum(v[0] for v in t.opravy) / 4
    vx = sum(v[1] for v in t.opravy) / 4
    assert (y - y0, x - x0) == pytest.approx((vy, vx), abs=1e-12)
    # blízko identického bodu převažuje jeho oprava
    y, x = t.preved_jung((1, 0), zdroj)
    assert abs((y - t.preved((1, 0))[0]) - t.opravy[0][0]) < 0.001
