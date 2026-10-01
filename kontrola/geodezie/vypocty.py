"""Základní geodetické úlohy (vlastní implementace podle učebnicových vzorců).

Úhly v gonech (400 gon = plný úhel), směrníky měřené od osy +X po směru hodinových ručiček (S-JTSK:
Y roste k západu, X k jihu – v číslech seznamu se počítá přímo s kladnými Y, X, jak je zvykem v Gromě).
Všechny výpočty v plné přesnosti, nic se nezaokrouhluje.

Úlohy: směrník a délka, rajón (polární bod), orientace osnovy, protínání vpřed z úhlů / směrníků,
protínání z délek, protínání zpět (ze tří bodů), volné stanovisko (MNČ, směry + délky), transformace
(shodnostní, podobnostní, afinní) s opravami, výměra a obvod, staničení a kolmice, polohová odchylka.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

GON = math.pi / 200.0


def gon2rad(g: float) -> float:
    return g * GON


def rad2gon(r: float) -> float:
    return r / GON


def norm_gon(g: float) -> float:
    g = math.fmod(g, 400.0)
    return g + 400.0 if g < 0 else g


@dataclass
class P:
    """Bod pro výpočty (Y, X)."""

    y: float
    x: float

    def __iter__(self):
        yield self.y
        yield self.x


def _yx(b) -> tuple[float, float]:
    return (b.y, b.x) if hasattr(b, "y") else (float(b[0]), float(b[1]))


# ------------------------------------------------------------------ směrník a délka, rajón
def smernik(a, b) -> float:
    """Směrník z A na B v gonech (0–400)."""
    (ya, xa), (yb, xb) = _yx(a), _yx(b)
    return norm_gon(rad2gon(math.atan2(yb - ya, xb - xa)))


def delka(a, b) -> float:
    (ya, xa), (yb, xb) = _yx(a), _yx(b)
    return math.hypot(yb - ya, xb - xa)


def rajon(st, sigma_gon: float, d: float) -> P:
    """Polární bod: ze stanoviska směrníkem σ a vodorovnou délkou d."""
    ys, xs = _yx(st)
    s = gon2rad(sigma_gon)
    return P(ys + d * math.sin(s), xs + d * math.cos(s))


# ------------------------------------------------------------------ orientace osnovy
@dataclass
class Orientace:
    posun: float  # orientační posun (směrník = směr + posun) [gon]
    opravy: list[tuple[str, float, float]] = field(default_factory=list)  # (bod, oprava [mgon], příčná [m])
    stredni_chyba_mgon: float = 0.0


def orientace(st, cile: list[tuple[str, object, float]], vahy_delkou: bool = True) -> Orientace:
    """Orientační posun ze směrů na známé body: ``cile`` = [(číslo, bod, měřený směr [gon]), …].

    Posun = vážený průměr (váha = délka, jako je obvyklé), opravy v miligonech i příčně v metrech."""
    if not cile:
        raise ValueError("Orientace potřebuje aspoň jeden známý bod.")
    ref = None
    hodnoty = []
    for c, b, smer in cile:
        o = norm_gon(smernik(st, b) - smer)
        if ref is None:
            ref = o
        # do intervalu kolem prvního posunu (přechod přes 0/400)
        while o - ref > 200:
            o -= 400
        while o - ref < -200:
            o += 400
        hodnoty.append((c, b, smer, o, delka(st, b)))
    w = [h[4] if vahy_delkou else 1.0 for h in hodnoty]
    posun = sum(h[3] * wi for h, wi in zip(hodnoty, w)) / sum(w)
    opr = [(c, (posun - o) * 1000.0, (posun - o) * GON * d) for c, _b, _s, o, d in hodnoty]
    n = len(opr)
    m = math.sqrt(sum(v[1] ** 2 for v in opr) / (n - 1)) if n > 1 else 0.0
    return Orientace(norm_gon(posun), opr, m)


# ------------------------------------------------------------------ protínání
def protinani_vpred_smerniky(a, sig_a: float, b, sig_b: float) -> P:
    """Průsečík dvou paprsků: z A směrníkem σA, z B směrníkem σB."""
    (ya, xa), (yb, xb) = _yx(a), _yx(b)
    sa, sb = gon2rad(sig_a), gon2rad(sig_b)
    da = np.array([math.sin(sa), math.cos(sa)])
    db = np.array([math.sin(sb), math.cos(sb)])
    m = np.column_stack([da, -db])
    if abs(np.linalg.det(m)) < 1e-12:
        raise ValueError("Paprsky jsou rovnoběžné – průsečík nejde určit.")
    t = np.linalg.solve(m, np.array([yb - ya, xb - xa]))
    return P(ya + t[0] * da[0], xa + t[0] * da[1])


def protinani_vpred_uhly(a, b, alfa: float, beta: float) -> P:
    """Protínání vpřed z úhlů: α v bodě A (mezi AB a AP), β v bodě B (mezi BA a BP), P vlevo od AB
    při pohledu z A do B (úhly v gonech, ve směru hodinových ručiček od základny)."""
    s_ab = smernik(a, b)
    return protinani_vpred_smerniky(a, norm_gon(s_ab - alfa), b, norm_gon(s_ab + 200 + beta))


def protinani_z_delek(a, b, da: float, db: float, vlevo: bool = True) -> P:
    """Protínání z délek: bod ve vzdálenosti da od A a db od B; ``vlevo`` = vlevo od směru A→B."""
    (ya, xa), (yb, xb) = _yx(a), _yx(b)
    c = math.hypot(yb - ya, xb - xa)
    if c == 0 or da + db < c - 1e-9 or abs(da - db) > c + 1e-9:
        raise ValueError("Z těchto délek trojúhelník nevznikne (kružnice se neprotínají).")
    t = (da * da - db * db + c * c) / (2 * c)  # vzdálenost paty od A podél AB
    h = math.sqrt(max(0.0, da * da - t * t))
    uy, ux = (yb - ya) / c, (xb - xa) / c
    # vlevo od A→B v soustavě (Y, X) s měřením od X po směru hodin: normála (−ux, uy)… ověřeno testem
    ny, nx = (-ux, uy) if vlevo else (ux, -uy)
    return P(ya + t * uy + h * ny, xa + t * ux + h * nx)


def protinani_zpet(a, b, c, smer_a: float, smer_b: float, smer_c: float) -> P:
    """Protínání zpět (Cassiniho řešení): stanovisko z měřených směrů na tři známé body."""
    (ya, xa), (yb, xb), (yc, xc) = _yx(a), _yx(b), _yx(c)
    alfa = gon2rad(smer_b - smer_a)  # úhel A–S–B
    beta = gon2rad(smer_c - smer_b)  # úhel B–S–C
    ca, cb = 1 / math.tan(alfa), 1 / math.tan(beta)
    # pomocné body (Cassini) – přímka P1P2 prochází hledaným stanoviskem, které je patou kolmice z B
    y1 = ya + (xb - xa) * ca
    x1 = xa - (yb - ya) * ca
    y2 = yc - (xb - xc) * cb
    x2 = xc + (yb - yc) * cb
    dy, dx = y2 - y1, x2 - x1
    nn = dy * dy + dx * dx
    if nn < 1e-18:
        raise ValueError("Body leží na nebezpečné kružnici – stanovisko nejde určit.")
    t = ((yb - y1) * dy + (xb - x1) * dx) / nn
    return P(y1 + t * dy, x1 + t * dx)


# ------------------------------------------------------------------ volné stanovisko (MNČ)
@dataclass
class VolneStanovisko:
    stanovisko: P
    posun: float  # orientační posun [gon]
    meritko: float
    opravy: list[tuple[str, float, float]]  # (bod, vy [m], vx [m]) – rozdíly známé − vypočtené
    m0: float  # střední souřadnicová chyba ze zbytků [m]


def volne_stanovisko(mereni: list[tuple[str, object, float, float]], meritko_volne: bool = False) -> VolneStanovisko:
    """Volné stanovisko z ≥ 2 známých bodů se směrem [gon] a vodorovnou délkou [m].

    Měřené body se převedou do místní soustavy (polárně ze směru a délky) a na známé souřadnice se
    nasadí podobnostní (nebo shodnostní) transformace MNČ – výsledek je stanovisko, orientační posun
    a opravy na bodech."""
    if len(mereni) < 2:
        raise ValueError("Volné stanovisko potřebuje aspoň dva známé body se směrem a délkou.")
    mistni = [(c, (d * math.sin(gon2rad(s)), d * math.cos(gon2rad(s)))) for c, _b, s, d in mereni]
    zname = [(c, _yx(b)) for c, b, _s, _d in mereni]
    t = transformace([m[1] for m in mistni], [z[1] for z in zname],
                     "podobnostni" if meritko_volne else "shodnostni")
    st = t.preved((0.0, 0.0))
    opr = [(c, v[0], v[1]) for (c, _), v in zip(zname, t.opravy)]
    return VolneStanovisko(P(*st), norm_gon(rad2gon(t.rotace)), t.meritko, opr, t.m0)


# ------------------------------------------------------------------ transformace
@dataclass
class Transformace:
    druh: str
    a: np.ndarray  # matice 2×2 (Y, X)
    t: np.ndarray  # posun
    opravy: list[tuple[float, float]]  # na identických bodech: cílové − transformované (vy, vx)
    m0: float  # střední souřadnicová chyba [m]

    @property
    def meritko(self) -> float:
        return float(math.sqrt(abs(np.linalg.det(self.a))))

    @property
    def rotace(self) -> float:
        """Úhel otočení [rad] (u afinní přibližně)."""
        return float(math.atan2(self.a[0, 1] - self.a[1, 0], self.a[0, 0] + self.a[1, 1]))

    def preved(self, p) -> tuple[float, float]:
        v = self.a @ np.array(_yx(p)) + self.t
        return float(v[0]), float(v[1])


def transformace(zdroj: list, cil: list, druh: str = "podobnostni") -> Transformace:
    """Transformační klíč z identických bodů (MNČ): ``shodnostni`` (posun + otočení), ``podobnostni``
    (+ měřítko, Helmert), ``afinni`` (6 prvků). Vrací klíč s opravami a střední chybou."""
    s = np.array([_yx(p) for p in zdroj], float)
    c = np.array([_yx(p) for p in cil], float)
    n = len(s)
    need = {"shodnostni": 2, "podobnostni": 2, "afinni": 3}[druh]
    if n < need or len(c) != n:
        raise ValueError(f"Transformace {druh} potřebuje aspoň {need} identické body.")
    sc, cc = s.mean(0), c.mean(0)
    s0, c0 = s - sc, c - cc
    if druh == "afinni":
        a_t, *_ = np.linalg.lstsq(s0, c0, rcond=None)
        a = a_t.T
    else:
        # Y' = a·Y + b·X, X' = −b·Y + a·X  (otočení ve smyslu směrníků; b = q·sin ω, a = q·cos ω)
        num_a = float((s0 * c0).sum())
        num_b = float((s0[:, 1] * c0[:, 0] - s0[:, 0] * c0[:, 1]).sum())
        den = float((s0 ** 2).sum())
        if den == 0:
            raise ValueError("Identické body splývají – transformaci nejde určit.")
        aa, bb = num_a / den, num_b / den
        if druh == "shodnostni":
            q = math.hypot(aa, bb)
            aa, bb = aa / q, bb / q
        a = np.array([[aa, bb], [-bb, aa]])
    t = cc - a @ sc
    res = c - (s @ a.T + t)
    u = {"shodnostni": 3, "podobnostni": 4, "afinni": 6}[druh]
    dof = 2 * n - u
    m0 = float(math.sqrt((res ** 2).sum() / dof / 2)) if dof > 0 else 0.0
    return Transformace(druh, a, t, [(float(r[0]), float(r[1])) for r in res], m0)


# ------------------------------------------------------------------ výměra, staničení
def vymera(body: list) -> float:
    """Výměra mnohoúhelníku (L'Huilierovy vzorce / Gauss), kladná, v m²."""
    pts = [_yx(b) for b in body]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    # souřadnice vztažené k prvnímu bodu – u velkých čísel S-JTSK se jinak ztrácí přesnost odčítáním
    y0, x0 = pts[0]
    s = 0.0
    for i in range(len(pts)):
        y1, x1 = pts[i][0] - y0, pts[i][1] - x0
        y2, x2 = pts[(i + 1) % len(pts)][0] - y0, pts[(i + 1) % len(pts)][1] - x0
        s += y1 * x2 - y2 * x1
    return abs(s) / 2.0


def obvod(body: list, uzavreny: bool = True) -> float:
    pts = [_yx(b) for b in body]
    s = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if uzavreny and len(pts) > 2 and pts[0] != pts[-1]:
        s += math.dist(pts[-1], pts[0])
    return s


def stanicni_kolmice(a, b, p) -> tuple[float, float]:
    """Staničení (od A po přímce AB) a kolmice bodu P – kladná vpravo při pohledu z A do B na mapě
    (Y roste na západ, X na jih)."""
    (ya, xa), (yb, xb), (yp, xp) = _yx(a), _yx(b), _yx(p)
    c = math.hypot(yb - ya, xb - xa)
    if c == 0:
        raise ValueError("Body A a B splývají.")
    uy, ux = (yb - ya) / c, (xb - xa) / c
    dy, dx = yp - ya, xp - xa
    st = dy * uy + dx * ux
    kol = dy * ux - dx * uy  # vpravo od směru A→B (v souřadnicích Y, X s měřením od X)
    return st, kol


def bod_ze_stanicni(a, b, staniceni: float, kolmice: float) -> P:
    """Opačná úloha: bod ze staničení a kolmice (vpravo kladná) – vytyčení, oměrné."""
    (ya, xa), (yb, xb) = _yx(a), _yx(b)
    c = math.hypot(yb - ya, xb - xa)
    uy, ux = (yb - ya) / c, (xb - xa) / c
    return P(ya + staniceni * uy + kolmice * ux, xa + staniceni * ux - kolmice * uy)


def polohova_odchylka(a, b) -> float:
    return delka(a, b)


# ------------------------------------------------------------------ mezní odchylky (katastr)
# Základní střední souřadnicová chyba m_xy podle kódu kvality (katastrální vyhláška 357/2013 Sb., příloha).
# POZOR: hodnoty jsou nastavitelné – ověřte je v platném znění vyhlášky.
MXY_KOD_KVALITY = {3: 0.14, 4: 0.26, 5: 0.50, 6: 1.00, 7: 2.00}


def mezni_polohova_odchylka(kod_kvality: int, nasobek: float = 2.0 * math.sqrt(2.0)) -> float:
    """Mezní polohová odchylka dvou nezávislých určení bodu: u_p = k · m_xy (výchozí k = 2·√2)."""
    if kod_kvality not in MXY_KOD_KVALITY:
        raise ValueError(f"Pro kód kvality {kod_kvality} není střední chyba stanovena.")
    return nasobek * MXY_KOD_KVALITY[kod_kvality]
