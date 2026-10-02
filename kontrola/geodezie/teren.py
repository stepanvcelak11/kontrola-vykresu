"""Digitální model terénu z bodů: TIN (Delaunayova trojúhelníková síť) a vrstevnice.

Jako v Atlasu / Gromě / MicroStationu (GEOPAK Site): z bodů s výškou se sestaví trojúhelníková síť, dlouhé
okrajové trojúhelníky se odříznou (max. délka strany), vrstevnice se lineárně interpolují po stranách trojúhelníků
a pospojují do lomených čar. Zesílené vrstevnice jsou každá n-tá (obvykle 5×interval). Souřadnice jsou
v rovině výkresu (x, y) – volající si převede S-JTSK sám. Bez Qt, běží i ve webové verzi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Tin:
    body: list[tuple[float, float, float]]
    trojuhelniky: list[tuple[int, int, int]]  # indexy do ``body``, proti směru hodin
    vynechane: int = 0  # body bez výšky nebo duplicitní polohy

    def rozsah_z(self) -> tuple[float, float]:
        zs = [b[2] for b in self.body]
        return (min(zs), max(zs)) if zs else (0.0, 0.0)

    def plocha(self) -> float:
        return sum(_plocha2(*(self.body[i] for i in t)) for t in self.trojuhelniky)

    def vyska_v(self, x: float, y: float) -> float | None:
        """Výška terénu v bodě (lineárně v trojúhelníku), None mimo síť."""
        for t in self.trojuhelniky:
            a, b, c = (self.body[i] for i in t)
            w = _barycentr(a, b, c, x, y)
            if w is not None:
                return w[0] * a[2] + w[1] * b[2] + w[2] * c[2]
        return None


@dataclass
class Vrstevnice:
    z: float
    body: list[tuple[float, float]]
    zesilena: bool = False
    uzavrena: bool = False


@dataclass
class ModelTerenu:
    tin: Tin
    vrstevnice: list[Vrstevnice] = field(default_factory=list)
    interval: float = 1.0


def _plocha2(a, b, c) -> float:
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0


def _barycentr(a, b, c, x, y):
    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(d) < 1e-15:
        return None
    l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
    l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
    l3 = 1.0 - l1 - l2
    eps = -1e-9
    return (l1, l2, l3) if l1 >= eps and l2 >= eps and l3 >= eps else None


def tin(body, max_strana: float | None = None) -> Tin:
    """Delaunayova síť z bodů (x, y, z). ``max_strana`` odřízne trojúhelníky s delší stranou (okraj, zálivy)."""
    from shapely import MultiPoint, delaunay_triangles
    pts, klice = [], {}
    vynechane = 0
    for b in body:
        if len(b) < 3 or b[2] is None or not all(math.isfinite(v) for v in b[:3]):
            vynechane += 1
            continue
        k = (round(b[0], 3), round(b[1], 3))
        if k in klice:
            vynechane += 1
            continue
        klice[k] = len(pts)
        pts.append((float(b[0]), float(b[1]), float(b[2])))
    if len(pts) < 3:
        raise ValueError("Pro model terénu jsou potřeba aspoň tři body s výškou.")
    g = delaunay_triangles(MultiPoint([p[:2] for p in pts]), tolerance=0.0)
    troj = []
    for poly in getattr(g, "geoms", []):
        c = list(poly.exterior.coords)[:3]
        try:
            idx = [klice[(round(x, 3), round(y, 3))] for x, y in c]
        except KeyError:
            continue
        a, b, cc = (pts[i] for i in idx)
        if _plocha2(a, b, cc) < 1e-9:
            continue
        if max_strana and max(math.dist(a[:2], b[:2]), math.dist(b[:2], cc[:2]), math.dist(cc[:2], a[:2])) > max_strana:
            continue
        if (b[0] - a[0]) * (cc[1] - a[1]) - (cc[0] - a[0]) * (b[1] - a[1]) < 0:  # proti směru hodin
            idx = [idx[0], idx[2], idx[1]]
        troj.append(tuple(idx))
    if not troj:
        raise ValueError("Z bodů nevznikl žádný trojúhelník (leží v přímce, nebo je maximální strana příliš malá).")
    return Tin(pts, troj, vynechane)


def _urovne(zmin: float, zmax: float, interval: float) -> list[float]:
    if interval <= 0:
        raise ValueError("Interval vrstevnic musí být kladný.")
    n0 = math.ceil(zmin / interval - 1e-9)
    n1 = math.floor(zmax / interval + 1e-9)
    if n1 - n0 > 5000:
        raise ValueError(f"Interval {interval} m je na výškový rozsah {zmax - zmin:.1f} m příliš malý.")
    return [round(n * interval, 6) for n in range(n0, n1 + 1)]


def _rez_trojuhelniku(a, b, c, z):
    """Úsečka vrstevnice z v trojúhelníku (nebo None). Výšky přesně na úrovni se posunou o nepatrnou hodnotu,
    aby vrstevnice nevznikaly dvakrát po hraně."""
    def h(p):
        return p[2] + 1e-7 if abs(p[2] - z) < 1e-9 else p[2]
    pts = []
    for p, q in ((a, b), (b, c), (c, a)):
        hp, hq = h(p), h(q)
        if (hp - z) * (hq - z) < 0:
            t = (z - hp) / (hq - hp)
            if t < 1e-5:  # vrstevnice prochází vrcholem → přesně vrchol (jinak vzniknou střípky u bodu)
                pts.append((p[0], p[1]))
            elif t > 1 - 1e-5:
                pts.append((q[0], q[1]))
            else:
                pts.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return (pts[0], pts[1]) if len(pts) == 2 else None


def _spoj(useky: list[tuple]) -> list[tuple[list, bool]]:
    """Úsečky → lomené čáry (spojení přes společné konce). Vrací [(body, uzavřená)]."""
    def k(p):
        return (round(p[0], 6), round(p[1], 6))
    sousede: dict = {}
    for i, (p, q) in enumerate(useky):
        sousede.setdefault(k(p), []).append(i)
        sousede.setdefault(k(q), []).append(i)
    pouzite = [False] * len(useky)
    out = []

    def prodluz(cara):
        while True:
            konec = k(cara[-1])
            dalsi = next((j for j in sousede.get(konec, []) if not pouzite[j]), None)
            if dalsi is None:
                return
            pouzite[dalsi] = True
            p, q = useky[dalsi]
            cara.append(q if k(p) == konec else p)

    # nejdřív otevřené čáry od konců (bod s jediným sousedem), pak zbylé uzavřené smyčky
    poradi = [i for i, (p, q) in enumerate(useky) if len(sousede[k(p)]) == 1 or len(sousede[k(q)]) == 1]
    poradi += range(len(useky))
    for i in poradi:
        if pouzite[i]:
            continue
        pouzite[i] = True
        p, q = useky[i]
        if len(sousede[k(q)]) == 1 and len(sousede[k(p)]) != 1:
            p, q = q, p
        cara = [p, q]
        prodluz(cara)
        if len(sousede[k(p)]) != 1:  # z druhé strany
            cara.reverse()
            prodluz(cara)
        uzavrena = len(cara) > 3 and k(cara[0]) == k(cara[-1])
        out.append((cara, uzavrena))
    return out


def vrstevnice(t: Tin, interval: float = 1.0, zesilena_kazda: int = 5, vyhladit: int = 0) -> list[Vrstevnice]:
    """Vrstevnice po ``interval`` metrech; zesílené jsou násobky ``interval × zesilena_kazda``."""
    zmin, zmax = t.rozsah_z()
    out = []
    for z in _urovne(zmin, zmax, interval):
        useky = []
        for tr in t.trojuhelniky:
            s = _rez_trojuhelniku(*(t.body[i] for i in tr), z)
            if s is not None and math.dist(*s) > 1e-9:
                useky.append(s)
        if not useky:
            continue
        zes = zesilena_kazda > 0 and abs(z / (interval * zesilena_kazda) - round(z / (interval * zesilena_kazda))) < 1e-6
        for cara, uz in _spoj(useky):
            if vyhladit:
                cara = _vyhlad(cara, uz, vyhladit)
            out.append(Vrstevnice(z, cara, zes, uz))
    return out


def _vyhlad(cara: list, uzavrena: bool, kroku: int) -> list:
    """Chaikinovo vyhlazení (jako „vyhladit vrstevnice“ v Atlasu); konce otevřené čáry zůstanou na místě."""
    for _ in range(kroku):
        if len(cara) < 3:
            return cara
        body = cara[:-1] if uzavrena else cara
        nove = [] if uzavrena else [body[0]]
        n = len(body)
        rozsah = range(n) if uzavrena else range(n - 1)
        for i in rozsah:
            p, q = body[i], body[(i + 1) % n]
            nove.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            nove.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        if uzavrena:
            nove.append(nove[0])
        else:
            nove.append(body[-1])
        cara = nove
    return cara


def model(body, interval: float = 1.0, max_strana: float | None = None, zesilena_kazda: int = 5,
          vyhladit: int = 0) -> ModelTerenu:
    t = tin(body, max_strana)
    return ModelTerenu(t, vrstevnice(t, interval, zesilena_kazda, vyhladit), interval)


def kubatura(t: Tin, z_ref: float) -> tuple[float, float]:
    """Objem nad a pod srovnávací rovinou z_ref (výkop, násyp) – přesně po trojúhelnících (hranoly)."""
    nad = pod = 0.0
    for tr in t.trojuhelniky:
        a, b, c = (t.body[i] for i in tr)
        n, p = _objem_hranolu(a, b, c, z_ref)
        nad += n
        pod += p
    return nad, pod


def _objem_hranolu(a, b, c, z0):
    hs = [a[2] - z0, b[2] - z0, c[2] - z0]
    s = _plocha2(a, b, c)
    if all(h >= 0 for h in hs):
        return s * sum(hs) / 3.0, 0.0
    if all(h <= 0 for h in hs):
        return 0.0, -s * sum(hs) / 3.0
    # rovina řeže trojúhelník: malý trojúhelník u osamělého vrcholu má objem s_m·h0/3, zbytek je doplněk
    body = [(a, hs[0]), (b, hs[1]), (c, hs[2])]
    kladne = [q for q in body if q[1] > 0]
    osamely = kladne[0] if len(kladne) == 1 else next(q for q in body if q[1] <= 0)
    druzi = [q for q in body if q is not osamely]
    p0, h0 = osamely
    rezy = []
    for q, hq in druzi:
        t = h0 / (h0 - hq)
        rezy.append((p0[0] + t * (q[0] - p0[0]), p0[1] + t * (q[1] - p0[1])))
    v_mala = _plocha2(p0, rezy[0], rezy[1]) * h0 / 3.0  # se znaménkem
    v_zbytek = s * sum(hs) / 3.0 - v_mala  # se znaménkem druhých dvou vrcholů
    return (v_mala, -v_zbytek) if h0 > 0 else (v_zbytek, -v_mala)


def profil(t: Tin, trasa: list[tuple[float, float]], krok: float = 5.0) -> list[tuple[float, float | None]]:
    """Podélný profil po trase (lomená čára): [(staničení, výška | None mimo model)] v bodech po ``krok``
    metrech, ve vrcholech trasy a na všech průsečících se stranami trojúhelníků (přesný lom terénu)."""
    if len(trasa) < 2:
        raise ValueError("Trasa profilu potřebuje aspoň dva body.")
    if krok <= 0:
        raise ValueError("Krok profilu musí být kladný.")
    hrany = set()
    for a, b, c in t.trojuhelniky:
        for i, j in ((a, b), (b, c), (c, a)):
            hrany.add((min(i, j), max(i, j)))
    stanice = []
    s0 = 0.0
    for (x0, y0), (x1, y1) in zip(trasa, trasa[1:]):
        d = math.hypot(x1 - x0, y1 - y0)
        if d < 1e-9:
            continue
        ts = {0.0, 1.0}
        n = int(d // krok)
        ts.update((k * krok) / d for k in range(1, n + 1) if k * krok < d)
        for i, j in hrany:  # průsečíky úseku trasy se stranami TIN
            p, q = t.body[i], t.body[j]
            den = (x1 - x0) * (q[1] - p[1]) - (y1 - y0) * (q[0] - p[0])
            if abs(den) < 1e-12:
                continue
            u = ((p[0] - x0) * (q[1] - p[1]) - (p[1] - y0) * (q[0] - p[0])) / den
            v = ((p[0] - x0) * (y1 - y0) - (p[1] - y0) * (x1 - x0)) / den
            if 0 <= u <= 1 and 0 <= v <= 1:
                ts.add(u)
        for u in sorted(ts):
            stanice.append((s0 + u * d, x0 + u * (x1 - x0), y0 + u * (y1 - y0)))
        s0 += d
    out, posl = [], None
    for s, x, y in stanice:
        if posl is not None and abs(s - posl) < 1e-6:
            continue
        posl = s
        out.append((s, t.vyska_v(x, y)))
    return out
