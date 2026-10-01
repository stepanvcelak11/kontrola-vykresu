"""Ověřovací úlohy geodetických výpočtů – ručně spočitatelné příklady a zpětné výpočty ze známé geometrie.

Přesnost: všechny úlohy sedí na 1e-6 m (zpětné výpočty) nebo přesně (ruční příklady)."""

import math
import random

import pytest

from kontrola.geodezie import vypocty as V

TOL = 1e-6  # m – výsledek se musí shodovat na tisícinu milimetru


def test_smernik_a_delka_rucne():
    a = V.P(1000.0, 1000.0)
    assert V.smernik(a, V.P(1000.0, 1100.0)) == pytest.approx(0.0)  # na sever (+X)
    assert V.smernik(a, V.P(1100.0, 1000.0)) == pytest.approx(100.0)  # +Y
    assert V.smernik(a, V.P(1000.0, 900.0)) == pytest.approx(200.0)
    assert V.smernik(a, V.P(900.0, 1000.0)) == pytest.approx(300.0)
    assert V.delka(a, V.P(1003.0, 1004.0)) == pytest.approx(5.0)


def test_rajon_rucne():
    p = V.rajon(V.P(1000.0, 1000.0), 50.0, 100.0)  # 45° → obě složky 100/√2
    assert p.y == pytest.approx(1070.710678118655, abs=1e-9) and p.x == pytest.approx(1070.710678118655, abs=1e-9)


def _nahodne_body(n, seed):
    r = random.Random(seed)
    return [V.P(595000 + r.uniform(0, 400), 1158000 + r.uniform(0, 400)) for _ in range(n)]


def test_orientace_posun_a_opravy():
    st = V.P(595100.0, 1158100.0)
    zname = _nahodne_body(4, 1)
    posun = 123.4567
    cile = [(str(i), b, V.norm_gon(V.smernik(st, b) - posun)) for i, b in enumerate(zname)]
    o = V.orientace(st, cile)
    assert o.posun == pytest.approx(posun, abs=1e-9)
    assert all(abs(v[1]) < 1e-6 for v in o.opravy)
    # posun přes 0/400
    cile2 = [(c, b, V.norm_gon(V.smernik(st, b) - 399.999)) for c, b, _ in cile]
    assert V.norm_gon(V.orientace(st, cile2).posun) == pytest.approx(399.999, abs=1e-9)


def test_protinani_vpred_smerniky_a_uhly():
    a, b, p = V.P(1000.0, 1000.0), V.P(1200.0, 1050.0), V.P(1080.0, 1180.0)
    q = V.protinani_vpred_smerniky(a, V.smernik(a, p), b, V.smernik(b, p))
    assert math.dist(q, p) < TOL
    alfa = V.norm_gon(V.smernik(a, b) - V.smernik(a, p))
    beta = V.norm_gon(V.smernik(b, p) - V.smernik(b, a))
    q2 = V.protinani_vpred_uhly(a, b, alfa, beta)
    assert math.dist(q2, p) < TOL
    with pytest.raises(ValueError):
        V.protinani_vpred_smerniky(a, 50.0, b, 50.0)


def test_protinani_z_delek_obe_strany():
    a, b = V.P(1000.0, 1000.0), V.P(1100.0, 1000.0)
    for p in (V.P(1040.0, 1070.0), V.P(1040.0, 930.0)):
        da, db = V.delka(a, p), V.delka(b, p)
        sols = [V.protinani_z_delek(a, b, da, db, vlevo=v) for v in (True, False)]
        assert min(math.dist(s, p) for s in sols) < TOL
        assert max(math.dist(s, p) for s in sols) > 1  # druhé řešení je zrcadlové
    with pytest.raises(ValueError):
        V.protinani_z_delek(a, b, 10.0, 10.0)


@pytest.mark.parametrize("seed", range(5))
def test_protinani_zpet(seed):
    r = random.Random(seed)
    s = V.P(595200.0, 1158200.0)
    pts = [V.rajon(s, r.uniform(0, 400), r.uniform(50, 300)) for _ in range(3)]
    pts.sort(key=lambda p: V.smernik(s, p))  # A, B, C ve směru hodin
    posun = r.uniform(0, 400)
    sm = [V.norm_gon(V.smernik(s, p) - posun) for p in pts]
    q = V.protinani_zpet(*pts, *sm)
    assert math.dist(q, s) < 1e-5


@pytest.mark.parametrize("meritko", [False, True])
def test_volne_stanovisko(meritko):
    s = V.P(595300.0, 1158300.0)
    zname = _nahodne_body(5, 7)
    posun = 77.7
    mer = [(str(i), b, V.norm_gon(V.smernik(s, b) - posun), V.delka(s, b)) for i, b in enumerate(zname)]
    vs = V.volne_stanovisko(mer, meritko_volne=meritko)
    assert math.dist(vs.stanovisko, s) < TOL and vs.m0 < 1e-6
    assert V.norm_gon(vs.posun) == pytest.approx(posun, abs=1e-7)
    # chyba 5 cm v délce na jeden bod se projeví v opravách
    mer[2] = (mer[2][0], mer[2][1], mer[2][2], mer[2][3] + 0.05)
    vs2 = V.volne_stanovisko(mer)
    assert max(math.hypot(v[1], v[2]) for v in vs2.opravy) > 0.02


@pytest.mark.parametrize("druh", ["shodnostni", "podobnostni", "afinni"])
def test_transformace_presne(druh):
    src = _nahodne_body(6, 3)
    w, q = V.gon2rad(12.3456), (1.0 if druh == "shodnostni" else 1.0002)

    def f(p):
        y = q * (p.y * math.cos(w) + p.x * math.sin(w)) + 1234.5
        x = q * (-p.y * math.sin(w) + p.x * math.cos(w)) - 987.6
        if druh == "afinni":
            y += 0.0003 * p.x
        return V.P(y, x)
    t = V.transformace(src, [f(p) for p in src], druh)
    assert t.m0 < 1e-6
    test = V.P(595111.1, 1158222.2)
    assert math.dist(t.preved(test), f(test)) < 1e-6
    if druh != "afinni":
        assert V.norm_gon(V.rad2gon(t.rotace)) == pytest.approx(12.3456, abs=1e-9)


def test_transformace_opravy_ukazi_chybny_bod():
    src = _nahodne_body(5, 4)
    cil = [V.P(p.y + 10, p.x - 5) for p in src]
    cil[3] = V.P(cil[3].y + 0.10, cil[3].x)
    t = V.transformace(src, cil, "shodnostni")
    worst = max(range(5), key=lambda i: math.hypot(*t.opravy[i]))
    assert worst == 3 and t.m0 > 0.01


def test_vymera_a_obvod_rucne():
    tri = [V.P(0, 0), V.P(3, 0), V.P(0, 4)]
    assert V.vymera(tri) == pytest.approx(6.0) and V.obvod(tri) == pytest.approx(12.0)
    ctverec = [V.P(0, 0), V.P(10, 0), V.P(10, 10), V.P(0, 10), V.P(0, 0)]
    assert V.vymera(ctverec) == pytest.approx(100.0) and V.obvod(ctverec) == pytest.approx(40.0)


def test_staniceni_a_kolmice_tam_a_zpet():
    a, b = V.P(1000.0, 1000.0), V.P(1000.0, 1100.0)  # na sever
    st, k = V.stanicni_kolmice(a, b, V.P(1003.0, 1040.0))
    assert st == pytest.approx(40.0) and k == pytest.approx(3.0)  # vpravo při pohledu z A do B na mapě
    for p in _nahodne_body(5, 9):
        a2, b2 = V.P(595000.0, 1158000.0), V.P(595300.0, 1158250.0)
        st, k = V.stanicni_kolmice(a2, b2, p)
        assert math.dist(V.bod_ze_stanicni(a2, b2, st, k), p) < TOL


def test_mezni_odchylky():
    assert V.mezni_polohova_odchylka(3) == pytest.approx(0.14 * 2 * math.sqrt(2))
    with pytest.raises(ValueError):
        V.mezni_polohova_odchylka(1)
