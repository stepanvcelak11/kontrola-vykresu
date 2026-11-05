"""Nezávislé ověření geodetických výpočtů: každá úloha se spočítá druhou, odlišnou metodou
(obecná MNČ s maticí plánu, Gauss–Newton, Shapely, komplexní čísla) a výsledky se musí shodovat.
Polární metoda se navíc porovnává se skutečným výstupem Gromy (zadání Husovice)."""

import cmath
import math
import random
from pathlib import Path

import numpy as np
import pytest

from kontrola.geodezie import vypocty as V

ROOT = Path(__file__).resolve().parents[1]
Z = ROOT / "podklady" / "zadani2-husovice"


def _rnd(seed, n=6):
    r = random.Random(seed)
    return r, [V.P(595000 + r.uniform(0, 500), 1158000 + r.uniform(0, 500)) for _ in range(n)]


# ------------------------------------------------------------------ rajón: komplexní čísla
@pytest.mark.parametrize("seed", range(10))
def test_rajon_komplexne(seed):
    r = random.Random(seed)
    st = V.P(r.uniform(-1e6, 0), r.uniform(-1e6, 0))
    sig, d = r.uniform(0, 400), r.uniform(0.1, 2000)
    p = V.rajon(st, sig, d)
    # v rovině (X, Y) s úhlem od X ve směru k Y: z = X + iY, krok = d·e^{iσ}
    z = complex(st.x, st.y) + d * cmath.exp(1j * sig * math.pi / 200)
    assert abs(p.x - z.real) < 1e-9 and abs(p.y - z.imag) < 1e-9
    assert V.delka(st, p) == pytest.approx(d, abs=1e-9)
    assert V.norm_gon(V.smernik(st, p) - sig + 1e-12) % 400 == pytest.approx(0, abs=1e-8) or \
        abs(V.smernik(st, p) - sig) < 1e-8


# ------------------------------------------------------------------ transformace: obecná MNČ maticí plánu
O = (595000.0, 1158000.0)  # počátek pro maticový výpočet (jinak špatně podmíněná matice)


def _mnc_podobnostni(src, dst):
    a = []
    l = []
    for s, t in zip(src, dst):
        sy, sx = s.y - O[0], s.x - O[1]
        a.append([sy, sx, 1, 0]); l.append(t.y)   # Y' = a·Y + b·X + ty
        a.append([sx, -sy, 0, 1]); l.append(t.x)  # X' = a·X − b·Y + tx
    x, *_ = np.linalg.lstsq(np.array(a), np.array(l), rcond=None)
    aa, bb, ty, tx = x
    return aa, bb, ty - aa * O[0] - bb * O[1], tx - aa * O[1] + bb * O[0]


def _mnc_afinni(src, dst):
    a, l = [], []
    for s, t in zip(src, dst):
        sy, sx = s.y - O[0], s.x - O[1]
        a.append([sy, sx, 1, 0, 0, 0]); l.append(t.y)
        a.append([0, 0, 0, sy, sx, 1]); l.append(t.x)
    x, *_ = np.linalg.lstsq(np.array(a), np.array(l), rcond=None)
    a1, a2, ty, b1, b2, tx = x
    return a1, a2, ty - a1 * O[0] - a2 * O[1], b1, b2, tx - b1 * O[0] - b2 * O[1]


@pytest.mark.parametrize("seed", range(5))
def test_transformace_podobnostni_proti_matici_planu(seed):
    r, src = _rnd(seed, 7)
    dst = [V.P(p.y * 1.0003 + 0.02 * p.x - 600000 + r.gauss(0, 0.02), p.x * 1.0003 - 0.02 * p.y + 20 + r.gauss(0, 0.02))
           for p in src]
    t = V.transformace(src, dst, "podobnostni")
    # 1) obecná MNČ maticí plánu (float) – shoda na 0,01 mm
    a, b, ty, tx = _mnc_podobnostni(src, dst)
    test = V.P(595250.0, 1158250.0)
    y, x = t.preved(test)
    assert y == pytest.approx(a * test.y + b * test.x + ty, abs=1e-5)
    assert x == pytest.approx(a * test.x - b * test.y + tx, abs=1e-5)
    # 2) přesně – normální rovnice ve zlomcích (bez zaokrouhlovacích chyb): shoda na 1e-9 m
    from fractions import Fraction as F
    n = len(src)
    sy, sx = sum(F(p.y) for p in src) / n, sum(F(p.x) for p in src) / n
    dy, dx = sum(F(p.y) for p in dst) / n, sum(F(p.x) for p in dst) / n
    na = sum((F(s.y) - sy) * (F(d.y) - dy) + (F(s.x) - sx) * (F(d.x) - dx) for s, d in zip(src, dst))
    nb = sum((F(s.x) - sx) * (F(d.y) - dy) - (F(s.y) - sy) * (F(d.x) - dx) for s, d in zip(src, dst))
    den = sum((F(s.y) - sy) ** 2 + (F(s.x) - sx) ** 2 for s in src)
    ea, eb = na / den, nb / den

    def ex(p):
        return (float(dy + ea * (F(p.y) - sy) + eb * (F(p.x) - sx)),
                float(dx - eb * (F(p.y) - sy) + ea * (F(p.x) - sx)))
    ey, exx = ex(test)
    assert abs(y - ey) < 1e-9 and abs(x - exx) < 1e-9
    res = [(d.y - ex(s)[0], d.x - ex(s)[1]) for s, d in zip(src, dst)]
    for (vy, vx), (wy, wx) in zip(t.opravy, res):
        assert vy == pytest.approx(wy, abs=1e-9) and vx == pytest.approx(wx, abs=1e-9)
    m0 = math.sqrt(sum(vy * vy + vx * vx for vy, vx in res) / (2 * n - 4) / 2)
    assert t.m0 == pytest.approx(m0, abs=1e-9)


@pytest.mark.parametrize("seed", range(5))
def test_transformace_afinni_proti_matici_planu(seed):
    r, src = _rnd(seed + 50, 8)
    dst = [V.P(1.0002 * p.y + 0.0004 * p.x + 5 + r.gauss(0, 0.01), -0.0003 * p.y + 0.9999 * p.x - 7 + r.gauss(0, 0.01))
           for p in src]
    t = V.transformace(src, dst, "afinni")
    a1, a2, ty, b1, b2, tx = _mnc_afinni(src, dst)
    test = V.P(595111.0, 1158333.0)
    y, x = t.preved(test)
    assert y == pytest.approx(a1 * test.y + a2 * test.x + ty, abs=1e-6)
    assert x == pytest.approx(b1 * test.y + b2 * test.x + tx, abs=1e-6)


@pytest.mark.parametrize("seed", range(5))
def test_transformace_shodnostni_je_optimum(seed):
    """Shodnostní: měřítko 1 a součet čtverců oprav je minimální (ověřeno prohledáním úhlů okolo)."""
    r, src = _rnd(seed + 90, 6)
    w = r.uniform(0, 2 * math.pi)
    dst = [V.P(p.y * math.cos(w) + p.x * math.sin(w) + 100 + r.gauss(0, 0.03),
               -p.y * math.sin(w) + p.x * math.cos(w) - 50 + r.gauss(0, 0.03)) for p in src]
    t = V.transformace(src, dst, "shodnostni")
    assert t.meritko == pytest.approx(1.0, abs=1e-12)

    def ss(ang):
        sy = np.mean([p.y for p in src]); sx = np.mean([p.x for p in src])
        dy = np.mean([p.y for p in dst]); dx = np.mean([p.x for p in dst])
        c, s = math.cos(ang), math.sin(ang)
        return sum((d.y - (dy + c * (p.y - sy) + s * (p.x - sx))) ** 2 + (d.x - (dx - s * (p.y - sy) + c * (p.x - sx))) ** 2
                   for p, d in zip(src, dst))
    best = ss(t.rotace)
    for k in (-1e-4, -1e-6, 1e-6, 1e-4):
        assert ss(t.rotace + k) >= best - 1e-9


# ------------------------------------------------------------------ volné stanovisko: Gauss–Newton
def _gn_volne(mer, st0):
    """Volné stanovisko obecnou MNČ: neznámé Ys, Xs, ω; měření převedená na souřadnice bodů."""
    ys, xs, om = st0[0], st0[1], 0.0
    for _ in range(30):
        a, l = [], []
        for _c, b, s, d in mer:
            ang = (s * math.pi / 200) + om
            py, px = ys + d * math.sin(ang), xs + d * math.cos(ang)
            a.append([1, 0, d * math.cos(ang)]); l.append(b.y - py)
            a.append([0, 1, -d * math.sin(ang)]); l.append(b.x - px)
        dxv, *_ = np.linalg.lstsq(np.array(a), np.array(l), rcond=None)
        ys, xs, om = ys + dxv[0], xs + dxv[1], om + dxv[2]
        if max(abs(v) for v in dxv) < 1e-12:
            break
    return ys, xs, (om * 200 / math.pi) % 400


@pytest.mark.parametrize("seed", range(6))
def test_volne_stanovisko_proti_gauss_newton(seed):
    r, zname = _rnd(seed + 7, 5)
    s = V.P(595250.0, 1158250.0)
    posun = r.uniform(0, 400)
    mer = [(str(i), b, V.norm_gon(V.smernik(s, b) - posun) + r.gauss(0, 0.0015),
            V.delka(s, b) + r.gauss(0, 0.003)) for i, b in enumerate(zname)]
    vs = V.volne_stanovisko(mer)
    ys, xs, om = _gn_volne(mer, (s.y + 1, s.x - 1))
    assert vs.stanovisko.y == pytest.approx(ys, abs=1e-6) and vs.stanovisko.x == pytest.approx(xs, abs=1e-6)
    assert ((vs.posun - om + 200) % 400 - 200) == pytest.approx(0, abs=1e-7)


# ------------------------------------------------------------------ protínání zpět: Gauss–Newton ze směrů
@pytest.mark.parametrize("seed", range(6))
def test_protinani_zpet_proti_gauss_newton(seed):
    r = random.Random(seed + 200)
    s = V.P(595250.0, 1158250.0)
    pts = sorted([V.rajon(s, r.uniform(0, 400), r.uniform(80, 400)) for _ in range(3)], key=lambda p: V.smernik(s, p))
    posun = r.uniform(0, 400)
    sm = [V.norm_gon(V.smernik(s, p) - posun) for p in pts]
    q = V.protinani_zpet(*pts, *sm)
    # Gauss–Newton: neznámé Y, X, ω ze tří směrů (přesně určeno)
    # model: směr = atan2(ΔY, ΔX) − ω ; neznámé Y, X stanoviska a ω
    y, x, om = s.y + 5, s.x - 5, (posun + 0.5) * math.pi / 200
    for _ in range(50):
        a, l = [], []
        for p, smer in zip(pts, sm):
            dy, dx = p.y - y, p.x - x
            dd = dy * dy + dx * dx
            theta = math.atan2(dy, dx)
            res = ((smer * math.pi / 200) - (theta - om) + math.pi) % (2 * math.pi) - math.pi
            a.append([-dx / dd, dy / dd, -1.0]); l.append(res)
        dv, *_ = np.linalg.lstsq(np.array(a), np.array(l), rcond=None)
        y, x, om = y + dv[0], x + dv[1], om + dv[2]
    assert q.y == pytest.approx(y, abs=1e-5) and q.x == pytest.approx(x, abs=1e-5)


# ------------------------------------------------------------------ protínání vpřed a z délek: geometrie
@pytest.mark.parametrize("seed", range(6))
def test_protinani_vpred_a_z_delek_nezavisle(seed):
    r, pts = _rnd(seed + 300, 3)
    a, b, p = pts
    # vpřed ze směrníků = průsečík dvou přímek (shapely)
    from shapely.geometry import LineString
    la = LineString([(a.y, a.x), (a.y + 3000 * math.sin(V.smernik(a, p) * math.pi / 200),
                                  a.x + 3000 * math.cos(V.smernik(a, p) * math.pi / 200))])
    lb = LineString([(b.y, b.x), (b.y + 3000 * math.sin(V.smernik(b, p) * math.pi / 200),
                                  b.x + 3000 * math.cos(V.smernik(b, p) * math.pi / 200))])
    ip = la.intersection(lb)
    q = V.protinani_vpred_smerniky(a, V.smernik(a, p), b, V.smernik(b, p))
    assert q.y == pytest.approx(ip.x, abs=1e-6) and q.x == pytest.approx(ip.y, abs=1e-6)
    # z délek: obě řešení leží na obou kružnicích
    for vl in (True, False):
        s = V.protinani_z_delek(a, b, V.delka(a, p), V.delka(b, p), vlevo=vl)
        assert V.delka(a, s) == pytest.approx(V.delka(a, p), abs=1e-6)
        assert V.delka(b, s) == pytest.approx(V.delka(b, p), abs=1e-6)


# ------------------------------------------------------------------ výměra: Shapely
@pytest.mark.parametrize("seed", range(10))
def test_vymera_proti_shapely(seed):
    from shapely.geometry import Polygon
    r = random.Random(seed)
    n = r.randint(3, 12)
    c = (595000.0, 1158000.0)
    ang = sorted(r.uniform(0, 2 * math.pi) for _ in range(n))
    pts = [V.P(c[0] + r.uniform(5, 60) * math.cos(a), c[1] + r.uniform(5, 60) * math.sin(a)) for a in ang]
    poly = Polygon([(p.y, p.x) for p in pts])
    assert V.vymera(pts) == pytest.approx(poly.area, rel=1e-12)
    assert V.obvod(pts) == pytest.approx(poly.length, rel=1e-12)


# ------------------------------------------------------------------ polární metoda: skutečná Groma
@pytest.mark.skipif(not (Z / "zap_husovice.zap").exists(), reason="podklady chybí")
def test_polarni_metoda_shoda_se_seznamem_gromy():
    """Všechny podrobné body proti seznamu vypočtenému v Gromě: poloha ≤ 0,5 mm (zaokrouhlení výpisu Gromy
    na mm), výška ≤ 1,5 mm (Groma počítá výšku stanoviska z převýšení zaokrouhleného na mm)."""
    from kontrola.checks.seznam import read_point_list, short_numbers
    from kontrola.vypocet import compute, read_zap
    r = compute(read_zap(Z / "zap_husovice.zap"), read_point_list(Z / "dane_body.txt"))
    groma = {}
    for p in read_point_list(Z / "Husovice_Včelák_seznam.txt"):
        for f in short_numbers(p.cislo):
            groma.setdefault(f, p)
    n = 0
    for b in r.body:
        g = groma.get(b.bod)
        if b.kontrolni or g is None:
            continue
        n += 1
        if b.bod == "10":  # určen dvakrát – Groma ho má uložit jako průměr (známá chyba v seznamu studenta)
            assert (round(b.y, 3), round(b.x, 3), round(b.z, 3)) == (595977.264, 1158238.567, 258.571)
            continue
        assert abs(b.y - abs(g.a)) <= 0.0006 and abs(b.x - abs(g.b)) <= 0.0006, b.bod
        assert b.z is None or g.z is None or abs(b.z - g.z) <= 0.0015, b.bod
    assert n >= 110
    # výšky stanovisek jako v protokolu Gromy (258.601, 255.887)
    assert r.stanoviska["4001"].z == pytest.approx(258.601, abs=0.0015)
    assert r.stanoviska["4002"].z == pytest.approx(255.887, abs=0.0015)


@pytest.mark.skipif(not (Z / "zap_husovice.zap").exists(), reason="podklady chybí")
def test_obousmerne_delky_jako_groma():
    """Groma: 4001–4002 D tam 21.257, zpět 21.250, rozdíl 0.007, průměr 21.253; dH −2.718 / 2.710, průměr −2.714."""
    from kontrola.checks.seznam import read_point_list
    from kontrola.vypocet import compute, read_zap
    r = compute(read_zap(Z / "zap_husovice.zap"), read_point_list(Z / "dane_body.txt"))
    o = r.obousmerne[0]
    assert round(o["d_tam"], 3) == 21.257 and round(o["d_zpet"], 3) == 21.250 and round(o["d"], 3) == 21.253
    assert abs(o["dh_tam"] - -2.718) <= 0.0006 and abs(o["dh_zpet"] - 2.710) <= 0.001
    assert abs(o["dh"] - -2.714) <= 0.001
    orient = r.protokol[0]["orientace"][1]  # 4002 z 4001: Groma délka 21.253, V délky −0.007
    assert round(orient["delka_mer"], 3) == 21.253 and round(orient["v_delky"], 3) == -0.007


def test_ulohy_nespadnou_na_spatnych_datech():
    """Tisíce náhodných vstupů do všech úloh: výsledek nebo srozumitelná hláška (ChybaVstupu), nikdy pád."""
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.ui.ulohy import ULOHY, ChybaVstupu
    r = random.Random(42)
    s = SeznamBodu()
    s.pridej([Bod("1", 0, 0), Bod("2", 0, 0), Bod("3", 100, 0), Bod("4", 100, 100, 5.0), Bod("5", 50, 50)])
    hodnoty = ["", "1", "2", "3", "4", "5", "99", "abc", "0", "-5", "400", "1e9", "nan", "inf", "1,5", " ",
               "1 2 3", "1 2", "4 5 3 2 1", "1 100 50\n2 200 60\n3 300 70", "3 0 0\n4 1 1\n5 2 2", "x y z"]
    pady = []
    for nazev, _p, pole, fn in ULOHY:
        for _ in range(300):
            h = {p.key: (r.choice(p.volby) if p.typ == "volba" and r.random() < 0.8 else r.choice(hodnoty))
                 for p in pole}
            try:
                fn(s, h)
            except ChybaVstupu:
                pass
            except Exception as e:  # noqa: BLE001
                pady.append(f"{nazev}: {type(e).__name__}: {e} ← {h}")
    assert not pady, "\n".join(pady[:10])


def test_rajon_01_jako_protokol_gromy():
    """Úloha 01 (rajón) proti protokolu Gromy: souřadnice podrobných bodů, orientační posun a bod 2 určený
    ze dvou stanovisek uložený jako průměr 591359.459 1062164.863."""
    from kontrola.checks.seznam import read_point_list
    from kontrola.geodezie.protokol import protokol_polarni
    from kontrola.vypocet import compute, read_zap
    d = Path(__file__).resolve().parents[1] / "podklady" / "groma-01-rajon"
    st, dane = read_zap(d / "01_zap.zap"), read_point_list(d / "01_SezSour.txt")
    r = compute(st, dane, koeficient=0.9999021514)
    assert round(r.posuny["4001"], 4) == 128.9942 and round(r.posuny["4003"], 4) == 243.0302
    groma = {"1": (591366.171, 1062161.511), "3": (591354.073, 1062154.110), "4": (591360.804, 1062150.756),
             "2": (591359.459, 1062164.863)}
    for b in r.body:
        if not b.kontrolni:
            assert (round(b.y, 3), round(b.x, 3)) == groma[b.bod], b.bod
    t = protokol_polarni(r, st, dane)
    assert "Kontrolní určení bodu číslo 2" in t and "Polohová odchylka: 0.055, Stř. souř. chyba: 0.039" in t
    dy, dx = map(float, next(x for x in t.splitlines() if x.startswith("Rozdíl ")).split()[1:3])
    assert abs(dy - -0.053) <= 0.0011 and abs(dx - 0.013) <= 0.0011  # Groma: −0.053 0.013 (zaokrouhlení na mm)


def test_polygon_jako_protokol_gromy():
    """Školní pořad 4008 → 934200160 (protokol Gromy): úhly, délky a orientační posuny z protokolu.
    Groma rozděluje souřadnicovou odchylku úměrně |ΔY| a |ΔX| – vypočtené body na mm stejně."""
    from kontrola.geodezie import ulohy as U
    from kontrola.geodezie.body import Bod, SeznamBodu
    a, b = (584714.530, 1146428.040), (584854.560, 1145852.080)

    def fiktivni(p, sm):  # orientace ve směru nulového směru osnovy (orientační posun z Gromy)
        return (p[0] + 1000 * math.sin(sm * math.pi / 200), p[1] + 1000 * math.cos(sm * math.pi / 200))
    s = SeznamBodu()
    s.pridej([Bod("4008", *a), Bod("160", *b), Bod("O1", *fiktivni(a, 199.9948)), Bod("O2", *fiktivni(b, 196.3304))])
    fn = next(f for n, _p, _pole, f in U.ULOHY if n == "Polygonový pořad")
    v = fn(s, {"ao": "O1", "a": "4008", "b": "160", "bo": "O2",
               "uhly": "4008 337.8310\n25001 244.9713\n25002 198.1256\n25003 227.8916\n25004 204.7555\n160 182.7175",
               "delky": "4008 121.987\n25001 103.266\n25002 182.208\n25003 111.645\n25004 126.289"})
    groma = {"25001": (584815.570, 1146359.733), "25002": (584843.105, 1146260.201),
             "25003": (584896.817, 1146086.082), "25004": (584881.354, 1145975.504)}
    for n in v.nove:
        gy, gx = groma[n.cislo]
        assert abs(n.y - gy) <= 0.0011 and abs(n.x - gx) <= 0.0011, n.cislo


@pytest.mark.parametrize("druh,meritko,st,opravy,posun", [
    ("shodnostní", "pevné (1)", (656888.509, 1128700.478),
     {"932030220": (0.050, 0.006), "932032070": (0.048, -0.007), "932032300": (-0.042, -0.090),
      "932032080": (-0.056, 0.091)}, 67.6702),
    ("podobnostní", "volné", (656888.499, 1128700.468),
     {"932030220": (0.020, 0.008), "932032070": (0.076, 0.000), "932032300": (-0.055, -0.015),
      "932032080": (-0.042, 0.006)}, 67.6696),
])
def test_transformace_a_volne_stanovisko_jako_groma(druh, meritko, st, opravy, posun):
    """Školní cvičení 07 (přílohy 4–7, protokoly Gromy): transformace z místní soustavy a volné stanovisko."""
    from kontrola.geodezie import ulohy as U
    from kontrola.geodezie.body import Bod, SeznamBodu
    f = {n: fn for n, _p, _pole, fn in U.ULOHY}
    sjtsk = {"932032070": (657070.21, 1128676.93), "932032300": (656656.57, 1129352.27),
             "932030220": (656493.10, 1128621.08), "932032080": (656934.11, 1127751.66)}
    mist = {"4009": (5000.000, 10000.000), "932030220": (5000.000, 10403.352), "932032070": (4941.160, 9826.536),
            "932032300": (5684.777, 10099.030), "932032080": (4060.672, 10142.039)}
    s = SeznamBodu()
    s.pridej([Bod(c, *v) for c, v in mist.items()])
    v = f["Transformace"](s, {"druh": druh, "identicke": "\n".join(f"{c} {y} {x}" for c, (y, x) in sjtsk.items()),
                              "transformovat": "4009", "jung": "ne", "predpona": ""})
    assert (round(v.nove[0].y, 3), round(v.nove[0].x, 3)) == st
    for c, (vy, vx) in opravy.items():
        r = next(x for x in v.protokol if x.strip().startswith(c)).split()
        assert abs(float(r[1]) - vy) <= 0.0011 and abs(float(r[2]) - vx) <= 0.0011, c
    s = SeznamBodu()
    s.pridej([Bod(c, *v) for c, v in sjtsk.items()])
    m = "932032070 40.5334 183.172\n932032300 310.5709 691.901\n932030220 219.7141 403.352\n932032080 129.2683 950.006"
    v = f["Volné stanovisko"](s, {"mereni": m, "meritko": meritko, "metoda": "transformace", "vp": "", "nove": "4009"})
    assert (round(v.nove[0].y, 3), round(v.nove[0].x, 3)) == st
    assert f"Orientační posun [g]: {posun:.4f}" in "\n".join(v.protokol)


TRIMBLE = Path(__file__).resolve().parents[1] / "podklady" / "trimble"


def test_trimble_file_and_report_sablona():
    """Šablona Geotronicsu (.xsl + .xdt) na JobXML dá stejný protokol GNSS jako Trimble File and Report."""
    from kontrola.io.trimble import TrimbleError, exportuj
    s = exportuj(TRIMBLE / "Vejda-sk3-mapovani-2026.jxl", TRIMBLE / "protokol" / "Kompletni_Protokol_mereni_GPS_2021.xsl")
    ref = (TRIMBLE / "Vejda-sk3-mapovani-2026.txt").read_bytes().decode("cp1250")
    assert [r.rstrip() for r in s.splitlines()] == [r.rstrip() for r in ref.splitlines()]
    body = exportuj(TRIMBLE / "Vejda-sk3-mapovani-2026.jxl",
                    TRIMBLE / "body" / "Merene body - YXZ - TXT GPS - ver-2.0.xsl")
    assert "4004 -599388.984 -1159322.045   264.675" in body
    with pytest.raises(TrimbleError, match="JobXML"):
        p = TRIMBLE / "x.job"
        try:
            p.write_bytes(b"Trimble General Survey Journal\0\0")
            exportuj(p, TRIMBLE / "body" / "Merene body - YXZ - TXT GPS - ver-2.0.xsl")
        finally:
            p.unlink()


def test_zapisnik_sdr33_trimble_s3():
    """SDR33 z Trimble S3 (cvičení SK3): stanoviska, výšky přístroje a cíle, orientace z 11TP, obě polohy."""
    from kontrola.geodezie import zapisnik as Z
    from kontrola.vypocet import _merge_faces
    st = Z.nacti(TRIMBLE / "SK3.sdr")
    assert [s.bod for s in st] == ["4001", "4011", "4009", "4012", "4010", "4006", "4004", "4003", "4002"]
    s = st[0]
    assert s.vp == 1.51 and s.orient[0].bod == "4002" and s.orient[0].vc == 1.6
    o = s.orient[0]
    assert (round(o.sd, 4), round(o.z, 4), o.hz) == (37.3312, 96.9803, 0.0)
    m = _merge_faces(s.orient)
    assert m[0].n >= 2 and abs(m[0].d_hz) < 0.01  # I. a II. poloha spojené
