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


def test_porovnani_seznamu():
    from kontrola.geodezie.body import Bod
    a = [Bod("1", 100, 200, 10.0, kvalita=3), Bod("2", 0, 0), Bod("5", 1, 1)]
    b = [Bod("1", 100.03, 200.04, 10.02), Bod("2", 0.5, 0), Bod("7", 2, 2)]
    r, jen_a, jen_b = V.porovnani_seznamu(a, b)
    assert [x.cislo for x in r] == ["1", "2"]
    assert r[0].dp == pytest.approx(0.05) and r[0].dz == pytest.approx(0.02) and r[0].vyhovuje
    assert not r[1].vyhovuje  # 0,5 m > 2·√2·0,14
    assert jen_a == ["5"] and jen_b == ["7"]


def test_porovnani_seznamu_cela_a_zkracena_cisla():
    """Seznam učitele s celými čísly KN (610844000130001) ↔ seznam studenta se zkrácenými (1, 2)."""
    from kontrola.geodezie.body import Bod
    a = [Bod("610844000130001", 100, 200, 10.0), Bod("610844000130002", 50, 60), Bod("610844000130003", 5, 5)]
    b = [Bod("1", 100.004, 200.0, 10.01), Bod("2", 50, 60.003), Bod("99", 0, 0)]
    r, jen_a, jen_b = V.porovnani_seznamu(a, b)
    assert [x.cislo for x in r] == ["610844000130001 = 1", "610844000130002 = 2"]
    assert all(x.vyhovuje for x in r) and r[0].dp == pytest.approx(0.004)
    assert jen_a == ["610844000130003"] and jen_b == ["99"]


def test_vymery_davkou():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.ui.ulohy import u_vymery_davkou
    s = SeznamBodu()
    s.pridej([Bod("1", 0, 0), Bod("2", 10, 0), Bod("3", 10, 10), Bod("4", 0, 10), Bod("5", 20, 0), Bod("6", 20, 10)])
    r = u_vymery_davkou(s, {"parcely": "125/3: 1 2 3 4\n125/4: 2 5 6 3\n"})
    t = "\n".join(r.protokol)
    assert "125/3" in t and "100.00" in t and "200.00" in t  # celkem


def test_kruzny_oblouk():
    # pravý úhel tečen ve V = (0, 0): tečna k A po +Y, k B po +X, R = 10 → T = 10, α = 100 g
    o = V.kruzny_oblouk((0, 0), (100, 0), (0, 100), 10, krok=5)
    assert (o.zo.y, o.zo.x) == pytest.approx((10, 0)) and (o.ko.y, o.ko.x) == pytest.approx((0, 10))
    assert (o.stred.y, o.stred.x) == pytest.approx((10, 10))
    assert o.alfa == pytest.approx(100) and o.tecna == pytest.approx(10)
    assert o.delka == pytest.approx(10 * math.pi / 2)
    assert o.vzepeti == pytest.approx(10 * math.sqrt(2) - 10)
    for st, p in o.podrobne:  # podrobné body leží na kružnici
        assert math.hypot(p.y - 10, p.x - 10) == pytest.approx(10)
    assert [round(st) for st, _p in o.podrobne] == [5, 10, 15]
    with pytest.raises(ValueError):
        V.kruzny_oblouk((0, 0), (1, 0), (2, 0), 5)


def test_oblouk_formular():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.ui.ulohy import u_oblouk
    s = SeznamBodu()
    s.pridej([Bod("V", 0, 0), Bod("A", 100, 0), Bod("B", 0, 100)])
    r = u_oblouk(s, {"v": "V", "a": "A", "b": "B", "r": "10", "krok": "5", "predpona": "O"})
    assert [b.cislo for b in r.nove] == ["OZO", "O1", "O2", "O3", "OKO", "OVO", "OS"]


def test_nivelacni_sit_formular():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.ui.ulohy import ChybaVstupu, u_nivelacni_sit
    s = SeznamBodu()
    s.pridej([Bod("A", 0, 0, 250.0), Bod("B", 100, 0, 252.1), Bod("1", 50, 0), Bod("2", 70, 0)])
    r = u_nivelacni_sit(s, {"dane": "A B", "oddily": "A 1 1.234 500\n1 2 -1.358 400\n2 B 2.224 600\n1 B 0.866 700"})
    vysky = {b.cislo: b.z for b in r.nove}
    assert vysky["1_niv"] == pytest.approx(251.234, abs=1e-4) and vysky["2_niv"] == pytest.approx(249.876, abs=1e-4)
    with pytest.raises(ChybaVstupu):
        u_nivelacni_sit(s, {"dane": "1", "oddily": "A 1 1 100"})  # daný bod bez výšky


def test_kontrolni_omerne_miry():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.ui.ulohy import ChybaVstupu, u_omerne
    s = SeznamBodu()
    s.pridej([Bod("1", 0, 0), Bod("2", 30, 40), Bod("3", 0, 10)])
    # d = 50 m, KK 3: u_d = 2·0,14·√(62/70) = 0,2635 m
    assert V.mezni_odchylka_delky(50, 3) == pytest.approx(2 * 0.14 * math.sqrt(62 / 70))
    r = u_omerne(s, {"miry": "1 2 50.10\n1 3 10.40\n", "kk": "3"})
    t = "\n".join(r.protokol)
    radky = [x for x in r.protokol if x.strip().startswith("1 ")]
    assert "NEVYHOVUJE" not in radky[0] and "+0.10" in radky[0]
    assert "NEVYHOVUJE" in radky[1]  # 0,40 m > u_d(10 m) = 0,23 m
    assert "1 překračuje" in t
    with pytest.raises(ChybaVstupu):
        u_omerne(s, {"miry": "1 9 10", "kk": "3"})
    with pytest.raises(ChybaVstupu):
        u_omerne(s, {"miry": "", "kk": "3"})


def test_vykaz_vymer_gp():
    import pytest

    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import ChybaVstupu, u_vykaz_vymer
    s = SeznamBodu([Bod("1", 0, 0), Bod("2", 20, 0), Bod("3", 20, 30), Bod("4", 0, 30), Bod("5", 40, 0),
                    Bod("6", 40, 30), Bod("7", 10, 0), Bod("8", 10, 30)])
    v = u_vykaz_vymer(s, {"dosavadni": "125/3 600 zahrada: 1 2 3 4\n125/4 orná: 2 5 6 3",
                          "nove": "125/5 zahrada: 1 7 8 4\n125/6: 7 5 6 8"})
    t = "\n".join(v.protokol)
    assert "125/5" in t and "Součty souhlasí" in t
    # 125/6 vzniká ze dvou dílů: 300 m² z 125/3 a 600 m² z 125/4
    assert any("125/3" in r and r.rstrip().endswith("300") for r in v.protokol)
    assert any("125/4" in r and r.rstrip().endswith("600") for r in v.protokol)
    with pytest.raises(ChybaVstupu):
        u_vykaz_vymer(s, {"dosavadni": "125/3: 1 2", "nove": "x: 1 2 3"})


def test_polygonovy_porad_uzavreny_a_volny():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import ULOHY, u_polygon_uzavreny, u_polygon_volny
    A, O = (1000.0, 2000.0), (1100.0, 2050.0)
    P = [(1050.0, 2080.0), (1010.0, 2150.0), (950.0, 2120.0), (940.0, 2040.0)]
    pts = [A] + P + [A]
    seq = [O] + pts + [O]
    uhly = [(V.smernik(seq[i], seq[i + 1]) - V.smernik(seq[i], seq[i - 1])) % 400 for i in range(1, len(seq) - 1)]
    delky = [V.delka(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    s = SeznamBodu()
    s.pridej([Bod("O", *O), Bod("A", *A)])
    jm = ["A", "1", "2", "3", "4", "A"]
    r = u_polygon_uzavreny(s, {"ao": "O", "a": "A",
                               "uhly": "\n".join(f"{c} {u + 0.0005!r}" for c, u in zip(jm, uhly)),  # +5 cc
                               "delky": "\n".join(f"{c} {d!r}" for c, d in zip(jm, delky))})
    assert r.protokol[0] == "POLYGONOVÝ POŘAD UZAVŘENÝ" and "úhlová odchylka 30 cc" in "\n".join(r.protokol)
    for n, q in zip(r.nove, P):
        assert abs(n.y - q[0]) < 0.01 and abs(n.x - q[1]) < 0.01
    # volný pořad: přesná data → přesné body, poslední bod z pole
    v = u_polygon_volny(s, {"ao": "O", "a": "A", "posledni": "4",
                            "uhly": "\n".join(f"{c} {u!r}" for c, u in zip(jm[:4], uhly[:4])),
                            "delky": "\n".join(f"{c} {d!r}" for c, d in zip(jm[:4], delky[:4]))})
    assert [n.cislo for n in v.nove] == ["1", "2", "3", "4"]
    for n, q in zip(v.nove, P):
        assert abs(n.y - q[0]) < 1e-6 and abs(n.x - q[1]) < 1e-6
    assert {"Polygonový pořad uzavřený", "Polygonový pořad volný"} <= {u[0] for u in ULOHY}


def test_testovani_presnosti_um():
    """Pokyn pro tvorbu ÚM 5.1/5.2: 3. třída u_xy 0,14 m – Δp ≤ 0,238 m, s_xy ≤ 1,1·0,14; délky u_d."""
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import u_test_delek, u_test_souradnic
    assert V.u_delky(8.0, 0.14) == pytest.approx(1.5 * 0.14 * 20 / 28)
    s = SeznamBodu()
    rnd = random.Random(3)
    radky = []
    for i in range(20):
        y, x, z = 600000 + rnd.uniform(0, 200), 1160000 + rnd.uniform(0, 200), 250 + rnd.uniform(0, 5)
        s.pridej([Bod(str(i), y, x, z)])
        radky.append(f"{i} {y + rnd.gauss(0, 0.03):.3f} {x + rnd.gauss(0, 0.03):.3f} {z + rnd.gauss(0, 0.02):.3f}")
    t = "\n".join(u_test_souradnic(s, {"trida": "3", "kontrolni": "\n".join(radky)}).protokol)
    assert "Přesnost souřadnic: VYHOVUJE" in t and "Přesnost výšek: VYHOVUJE" in t and "N = 20 " in t
    radky[0] = "0 1 1 1"  # hrubá chyba
    t = "\n".join(u_test_souradnic(s, {"trida": "3", "kontrolni": "\n".join(radky)}).protokol)
    assert "Přesnost souřadnic: NEVYHOVUJE" in t
    b0, b1 = s.najdi("0"), s.najdi("1")
    d = math.hypot(b0.y - b1.y, b0.x - b1.x)
    ok = "\n".join(u_test_delek(s, {"delky": f"0 1 {d + 0.02:.3f}"}).protokol)
    spatne = "\n".join(u_test_delek(s, {"delky": f"0 1 {d + 1:.3f}"}).protokol)
    assert "Relativní přesnost: VYHOVUJE" in ok and "Relativní přesnost: NEVYHOVUJE" in spatne


def test_redukce_delky():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.sjtsk import meritko_zobrazeni
    from kontrola.geodezie.ulohy import ChybaVstupu, u_redukce
    # Křovák: na základní rovnoběžce 0,9999, Praha asi −96 ppm, západ Čech kladné
    assert abs(meritko_zobrazeni(500000, 1200000) - 0.9999) < 2e-6
    assert -100e-6 < meritko_zobrazeni(743000, 1043000) - 1 < -90e-6
    assert meritko_zobrazeni(870000, 1110000) > 1
    s = SeznamBodu()
    s.body = [Bod("1", 743000.0, 1043000.0, 250.0), Bod("2", 743100.0, 1043000.0, 252.0)]
    p = "\n".join(u_redukce(s, {"d": "100.0123", "z": "99", "a": "1", "b": "2"}).protokol)
    assert "vodorovná 100.0000 m" in p and "H = 251.0 m" in p and "-3.9 mm" in p
    assert "d = 99.9864 m" in p and "rozdíl měřená − souřadnicová -13.6 mm" in p
    p = "\n".join(u_redukce(s, {"d": "50", "H": "0"}).protokol)
    assert "d = 50.0000 m" in p and "nezapočte" in p
    import pytest
    for h in ({"d": "-1"}, {"d": "10", "z": "500"}, {"d": "10", "H": "123456"}, {"d": "x"}):
        with pytest.raises(ChybaVstupu):
            u_redukce(s, h)


def test_protinani_vpred_ze_smeru():
    import pytest

    from kontrola.geodezie import vypocty as V
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import ChybaVstupu, u_vpred_smery
    s = SeznamBodu()
    A, B, O1, O2, P = (Bod("A", 1000, 5000), Bod("B", 1100, 5000), Bod("O1", 1000, 5200), Bod("O2", 1150, 4900),
                       Bod("P", 1040, 5080))
    s.body = [A, B, O1, O2]

    def smer(st, c, posun):
        return V.norm_gon(V.smernik(st, c) - posun)
    h = {"a": "A", "b": "B", "ora": f"O1 {smer(A, O1, 12.3456):.7f}\nO2 {smer(A, O2, 12.3456) + 0.0010:.7f}",
         "orb": f"O1 {smer(B, O1, 350):.7f}", "sa": f"{smer(A, P, 12.3456):.7f}", "sb": f"{smer(B, P, 350):.7f}",
         "nove": "P"}
    v = u_vpred_smery(s, h)
    b = v.nove[0]
    # druhá orientace má chybu 10 cc → průměr vážený délkami posune bod jen o pár milimetrů
    assert abs(b.y - 1040) < 0.01 and abs(b.x - 5080) < 0.01 and isinstance(b.y, float)
    t = "\n".join(v.protokol)
    assert "oprava" in t and "orientační posun" in t
    h["ora"] = "O9 10"
    with pytest.raises(ChybaVstupu, match="O9"):
        u_vpred_smery(s, h)
    h["ora"] = ""
    with pytest.raises(ChybaVstupu, match="orientaci"):
        u_vpred_smery(s, h)


def test_nastaveni_vypoctu_korekce_delek_v_rajonu():
    from kontrola.geodezie import nastaveni as N
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.sjtsk import meritko_zobrazeni
    from kontrola.geodezie.ulohy import u_rajon
    s = SeznamBodu()
    s.body[:] = [Bod("1", 740000.0, 1050000.0, 400.0), Bod("2", 740100.0, 1050000.0, 400.0)]
    h = {"st": "1", "o": "2", "so": "0", "sm": "100", "d": "100", "nove": "5"}
    puvodni = N.aktualni()
    try:
        N.nastav(N.NastaveniVypoctu())
        r0 = u_rajon(s, h)
        assert abs(r0.nove[0].x - 1049900.0) < 1e-6 and not any("Korekce" in t for t in r0.protokol)
        N.nastav(N.NastaveniVypoctu(meritko_rezim="Křovák ze souřadnic", vyska_rezim="z výšek bodů"))
        r = u_rajon(s, h)
        k = meritko_zobrazeni(740000.0, 1050000.0) * N.R_ZEME / (N.R_ZEME + 400.0)
        assert abs((1050000.0 - r.nove[0].x) - 100 * k) < 1e-6
        assert any("Korekce délek" in t and "měřítko zobrazení" in t for t in r.protokol)
        n2 = N.NastaveniVypoctu.z_dict(N.NastaveniVypoctu(ucel="polohopis", trida_presnosti=4).do_dict())
        assert n2.mxy == 0.26 and "třída přesnosti 4" in n2.popis_ucelu()
        u, p = N.NastaveniVypoctu().mez_polygonu(2, 400.0)
        assert abs(u - 0.025 * 2) < 1e-12 and abs(p - (0.0025 * 20 + 0.04)) < 1e-12
    finally:
        N.nastav(puvodni)


def test_kruznice_uhel_a_bod_na_primce():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import u_bod_na_primce, u_kruznice_3b, u_uhel
    rnd = random.Random(5)
    for _ in range(50):
        sy, sx, r = 700000 + rnd.uniform(-5e4, 5e4), 1100000 + rnd.uniform(-5e4, 5e4), rnd.uniform(1, 500)
        uh = sorted(rnd.uniform(0, 2 * math.pi) for _ in range(3))
        s = SeznamBodu()
        s.body[:] = [Bod(str(i), sy + r * math.sin(t), sx + r * math.cos(t)) for i, t in enumerate(uh)]
        v = u_kruznice_3b(s, {"a": "0", "b": "1", "c": "2", "nove": "S"})
        assert abs(v.nove[0].y - sy) < 1e-5 and abs(v.nove[0].x - sx) < 1e-5
    s = SeznamBodu()
    s.body[:] = [Bod("1", 0.0, 0.0), Bod("2", 0.0, 10.0), Bod("3", 10.0, 0.0), Bod("4", 0.0, 20.0, None)]
    assert "100.0000 gon" in "\n".join(u_uhel(s, {"v": "1", "l": "2", "p": "3"}).protokol)
    with pytest.raises(Exception):
        u_kruznice_3b(s, {"a": "1", "b": "2", "c": "4"})
    r = u_bod_na_primce(s, {"a": "1", "b": "2", "d": "25", "nove": "9"})
    assert (r.nove[0].y, r.nove[0].x) == (0.0, 25.0)
    r = u_bod_na_primce(s, {"a": "1", "b": "3", "dily": "5", "nove": "P08"})
    assert [b.cislo for b in r.nove] == ["P08", "P09", "P10", "P11"] and r.nove[-1].y == 8.0


def test_polygon_vetknuty_a_centrace():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import u_centrace, u_polygon_vetknuty
    rnd = random.Random(11)
    pts = [(700000.0, 1050000.0)]
    for _ in range(4):
        y, x = pts[-1]
        pts.append((y + rnd.uniform(60, 150), x + rnd.uniform(-80, 80)))
    s = SeznamBodu()
    s.body[:] = [Bod("A", *pts[0]), Bod("B", *pts[-1])]
    P = [Bod(str(i), *p) for i, p in enumerate(pts)]
    uhly = "\n".join(f"{i} {_uhel(P[i], P[i - 1], P[i + 1]):.6f}" for i in range(1, 4))
    delky = "\n".join(f"{i} {V.delka(P[i], P[i + 1]):.4f}" for i in range(4))
    r = u_polygon_vetknuty(s, {"a": "A", "b": "B", "uhly": uhly, "delky": delky})
    for b, p in zip(r.nove, pts[1:-1]):
        assert math.hypot(b.y - p[0], b.x - p[1]) < 2e-4
    # centrace: centr S, excentrické stanovisko S' 0,3 m od něj; centrovaný směr = směr ze S
    S, Sp = Bod("S", 1000.0, 2000.0), Bod("Sx", 1000.3, 2000.1)
    T = Bod("T", 1200.0, 2150.0)
    o = V.smernik(Sp, Bod("o", 1000.0, 3000.0))  # libovolná orientace kruhu
    phi = V.norm_gon(V.smernik(Sp, T) - o)
    fs = V.norm_gon(V.smernik(Sp, S) - o)
    v = u_centrace(SeznamBodu(), {"e": f"{V.delka(S, Sp):.6f}", "fs": f"{fs:.6f}",
                                  "smery": f"T {phi:.6f} {V.delka(Sp, T):.4f}"})
    cen = float(v.protokol[-1].split()[-1])
    assert abs(V.norm_gon(cen + o) - V.smernik(S, T)) < 2e-4


def test_nivelacni_zapisnik():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import ChybaVstupu, u_nivelacni_zapisnik
    s = SeznamBodu()
    s.body[:] = [Bod("A", 0, 0, 250.000), Bod("B", 100, 0, 251.000), Bod("5", 50, 0)]
    # skutečné převýšení +1,000 m, měření s uzávěrem +4 mm; boční záměra na bod 5
    z = ("Z A 1.500 40\nB 5 1.200\nP T1 1.000 40\n"
         "Z T1 1.800 35\nP B 1.296 35")
    r = u_nivelacni_zapisnik(s, {"a": "A", "b": "B", "zapisnik": z})
    t = "\n".join(r.protokol)
    assert "odchylka uzávěru 4.0 mm" in t and "VYHOVUJE" in t
    assert "Σ vzad − Σ vpřed = 3.3000 − 2.2960 = 1.0040" in t
    # oprava −4 mm úměrně délkám (80 : 70); boční záměra z horizontu s polovinou opravy 1. sestavy
    v1 = -0.004 * 80 / 150
    assert abs(r.vysky["5"] - (250 + 1.5 + v1 / 2 - 1.2)) < 1e-9
    with __import__("pytest").raises(ChybaVstupu):
        u_nivelacni_zapisnik(s, {"a": "A", "b": "B", "zapisnik": "Z A 1500\nP T1 1000\nZ T2 1800\nP B 1296"})


def test_volne_stanovisko_s_vyskou_ze_zenitu():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import u_volne
    st = Bod("S", 1000.0, 2000.0, 300.0)
    cile = [Bod("1", 1100.0, 2050.0, 305.0), Bod("2", 950.0, 2120.0, 296.0), Bod("3", 1020.0, 1900.0, 301.5)]
    s = SeznamBodu()
    s.body[:] = cile
    vp, vc, o = 1.6, 1.3, 37.0
    radky = []
    for b in cile:
        d = V.delka(st, b)
        # převýšení terén–terén včetně zakřivení a refrakce → zenit a šikmá délka
        dh = b.z - st.z
        oprava = d * d * (1 - 0.13) / (2 * 6380000.0)
        dv = dh - vp + vc - oprava
        z = V.rad2gon(math.atan2(d, dv))
        radky.append(f"{b.cislo} {V.norm_gon(V.smernik(st, b) - o):.6f} {math.hypot(d, dv):.5f} {z:.6f} {vc}")
    r = u_volne(s, {"mereni": "\n".join(radky), "vp": str(vp), "nove": "S"})
    b = r.nove[0]
    assert math.hypot(b.y - st.y, b.x - st.x) < 1e-3 and abs(b.z - 300.0) < 1e-3


def test_rajon_prostorovy_a_vymera_z_mer():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import ChybaVstupu, u_rajon, u_vymera_z_mer
    s = SeznamBodu()
    s.body[:] = [Bod("1", 0.0, 0.0, 100.0), Bod("2", 0.0, 100.0)]
    r = u_rajon(s, {"st": "1", "o": "2", "so": "0", "sm": "0", "d": "50", "zenit": "100", "vp": "1.5",
                    "vc": "1.5", "nove": "9"})
    b = r.nove[0]
    assert abs(b.x - 50.0) < 1e-9 and abs(b.z - (100 + 50 * 50 * 0.87 / (2 * 6380000))) < 1e-9
    v = u_vymera_z_mer(SeznamBodu(), {"trojuhelniky": "T1 3 4 5\nT2 3 4 5"})
    assert "celkem 12.00 m²" in "\n".join(v.protokol)
    with pytest.raises(ChybaVstupu):
        u_vymera_z_mer(SeznamBodu(), {"trojuhelniky": "T 1 1 5"})


def test_volne_stanovisko_mnc_i_jen_ze_smeru():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import u_volne
    st = Bod("S", 1000.0, 2000.0)
    cile = [Bod("1", 1100.0, 2050.0), Bod("2", 950.0, 2120.0), Bod("3", 1020.0, 1900.0), Bod("4", 880.0, 1950.0)]
    s = SeznamBodu()
    s.body[:] = cile
    o = 123.4567
    sm = {b.cislo: V.norm_gon(V.smernik(st, b) - o) for b in cile}
    radky = [f"{b.cislo} {sm[b.cislo]:.6f} {V.delka(st, b):.4f}" for b in cile[:2]] + \
            [f"{b.cislo} {sm[b.cislo]:.6f}" for b in cile[2:]]
    r = u_volne(s, {"mereni": "\n".join(radky), "nove": "S"})
    b = r.nove[0]
    assert math.hypot(b.y - st.y, b.x - st.x) < 1e-4 and "MNČ" in r.protokol[0]
    r = u_volne(s, {"mereni": "\n".join(f"{b.cislo} {sm[b.cislo]:.6f}" for b in cile), "nove": "S"})
    assert math.hypot(r.nove[0].y - st.y, r.nove[0].x - st.x) < 1e-4
    r = u_volne(s, {"mereni": "\n".join(f"{b.cislo} {sm[b.cislo]:.6f} {V.delka(st, b):.4f}" for b in cile),
                    "nove": "S", "metoda": "MNČ – směry a délky s váhami"})
    assert math.hypot(r.nove[0].y - st.y, r.nove[0].x - st.x) < 1e-4
    assert any("orientační posun" in t and f"{V.norm_gon(o):.4f}" in t for t in r.protokol)
