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

    def preved_jung(self, p, identicke_zdroj: list) -> tuple[float, float]:
        """Transformace s Jungovou dotransformací: opravy z identických bodů se rozloží na bod
        s vahami 1/d² (d = vzdálenost od identického bodu ve zdrojové soustavě). Identický bod
        tak dostane přesně cílové souřadnice a okolí se „dotáhne“ plynule."""
        y, x = self.preved(p)
        py, px = _yx(p)
        sw = swy = swx = 0.0
        for q, (vy, vx) in zip(identicke_zdroj, self.opravy):
            qy, qx = _yx(q)
            d2 = (py - qy) ** 2 + (px - qx) ** 2
            if d2 < 1e-12:
                return y + vy, x + vx
            w = 1.0 / d2
            sw += w
            swy += w * vy
            swx += w * vx
        if sw == 0:
            return y, x
        return y + swy / sw, x + swx / sw


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
    if c == 0:
        raise ValueError("Body A a B splývají – směr přímky není určen.")
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


# ------------------------------------------------------------------ průsečíky
def prusecik_primek(a1, a2, b1, b2) -> P:
    """Průsečík přímek A1A2 a B1B2 (i mimo úsečky)."""
    (y1, x1), (y2, x2), (y3, x3), (y4, x4) = _yx(a1), _yx(a2), _yx(b1), _yx(b2)
    d = (y2 - y1) * (x4 - x3) - (x2 - x1) * (y4 - y3)
    if abs(d) < 1e-12 * max(1.0, abs(y2 - y1) + abs(x2 - x1)) ** 2:
        raise ValueError("Přímky jsou rovnoběžné – průsečík neexistuje.")
    t = ((y3 - y1) * (x4 - x3) - (x3 - x1) * (y4 - y3)) / d
    return P(y1 + t * (y2 - y1), x1 + t * (x2 - x1))


def prusecik_primky_kruznice(a, b, s, r: float) -> list[P]:
    """Průsečíky přímky AB s kružnicí (střed S, poloměr r) – 0, 1 nebo 2 body (seřazené od A)."""
    (ya, xa), (yb, xb), (ys, xs) = _yx(a), _yx(b), _yx(s)
    dy, dx = yb - ya, xb - xa
    fy, fx = ya - ys, xa - xs
    aa = dy * dy + dx * dx
    if aa == 0:
        raise ValueError("Body přímky splývají.")
    bb = 2 * (fy * dy + fx * dx)
    cc = fy * fy + fx * fx - r * r
    disc = bb * bb - 4 * aa * cc
    if disc < -1e-9:
        return []
    disc = max(0.0, disc)
    ts = sorted({(-bb - math.sqrt(disc)) / (2 * aa), (-bb + math.sqrt(disc)) / (2 * aa)})
    return [P(ya + t * dy, xa + t * dx) for t in ts]


def prusecik_kruznic(s1, r1: float, s2, r2: float) -> list[P]:
    """Průsečíky dvou kružnic (= protínání z délek, obě řešení)."""
    (y1, x1), (y2, x2) = _yx(s1), _yx(s2)
    d = math.hypot(y2 - y1, x2 - x1)
    if d == 0 or d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    out = [protinani_z_delek(s1, s2, r1, r2, True)]
    other = protinani_z_delek(s1, s2, r1, r2, False)
    if delka(other, out[0]) > 1e-9:
        out.append(other)
    return out


# ------------------------------------------------------------------ vytyčovací prvky
def vytycovaci_prvky(st, orientace, bod) -> tuple[float, float, float]:
    """Pro vytyčení bodu ze stanoviska orientovaného na známý bod: (vytyčovací úhel od orientace ve směru
    hodin [gon], vodorovná délka [m], směrník [gon])."""
    s_o, s_b = smernik(st, orientace), smernik(st, bod)
    return norm_gon(s_b - s_o), delka(st, bod), s_b


# ------------------------------------------------------------------ výšky
def trigonometricka_vyska(h_st: float, sikma: float, zenit_gon: float, vp: float = 0.0, vc: float = 0.0,
                          k_refr: float = 0.13, r_zeme: float = 6380000.0) -> tuple[float, float]:
    """Výška bodu z trigonometrického měření: (výška, převýšení terén–terén) se zakřivením a refrakcí."""
    z = gon2rad(zenit_gon)
    d = sikma * math.sin(z)
    dh = sikma * math.cos(z) + vp - vc + d * d * (1 - k_refr) / (2 * r_zeme)
    return h_st + dh, dh


@dataclass
class NivelacniPorad:
    vysky: list[tuple[str, float]]  # (bod, vyrovnaná výška)
    odchylka: float  # uzávěr = Σ měřených převýšení − (H_konec − H_začátek) [m]
    mezni: float  # mezní odchylka [m]
    delka_km: float
    opravy: list[float]

    @property
    def vyhovuje(self) -> bool:
        return abs(self.odchylka) <= self.mezni


def nivelacni_porad(h_zac: float, h_kon: float, oddily: list[tuple[str, float, float]],
                    mez_mm_na_km: float = 40.0) -> NivelacniPorad:
    """Nivelační pořad mezi dvěma výškově danými body: ``oddily`` = [(cílový bod, převýšení [m], délka [m])].

    Uzávěr se rozdělí úměrně délkám; mezní odchylka = mez · √L[km] (technická nivelace 40 mm/√km)."""
    if not oddily:
        raise ValueError("Pořad nemá žádný oddíl.")
    L = sum(max(0.0, d) for _b, _h, d in oddily)
    suma = sum(h for _b, h, _d in oddily)
    w = suma - (h_kon - h_zac)
    mezni = mez_mm_na_km / 1000.0 * math.sqrt(max(L, 1.0) / 1000.0)
    vysky, opravy, h = [], [], h_zac
    for b, dh, d in oddily:
        v = -w * (d / L if L > 0 else 1 / len(oddily))
        h += dh + v
        opravy.append(v)
        vysky.append((b, h))
    return NivelacniPorad(vysky, w, mezni, L / 1000.0, opravy)


# ------------------------------------------------------------------ ortogonální metoda
def ortogonalni_davka(a, b, mereni: list[tuple[str, float, float]], delka_merena: float | None = None):
    """Ortogonální metoda dávkou: body ze staničení a kolmic k měřické přímce A→B.

    Je-li zadaná měřená délka přímky (konec měření na B), staničení i kolmice se opraví v poměru
    délka ze souřadnic / měřená délka (jako zavedení měřítka). Vrací (body, poměr, odchylka délky)."""
    c = delka(a, b)
    q = c / delka_merena if delka_merena else 1.0
    body = [(cislo, bod_ze_stanicni(a, b, st * q, k * q)) for cislo, st, k in mereni]
    return body, q, (c - delka_merena) if delka_merena else 0.0


# ------------------------------------------------------------------ polygonový pořad
@dataclass
class PolygonovyPorad:
    body: list[tuple[str, P]]
    uhlova_odchylka: float  # [gon] – měřené − teoretické
    dy: float
    dx: float
    polohova: float  # √(dy² + dx²) [m]
    delka: float  # [m]
    smerniky: list[float]


def polygonovy_porad(a, a_orient, b, b_orient, uhly: list[float], delky: list[float],
                     cisla: list[str]) -> PolygonovyPorad:
    """Oboustranně připojený a oboustranně orientovaný polygonový pořad.

    Začátek A (známý) s orientací na známý bod, konec B (známý) s orientací na známý bod.
    ``uhly`` = vrcholové (levé) úhly β měřené ve směru hodin od zadní k přední záměře na A, P1, …, Pn, B
    (n+2 úhlů), ``delky`` = délky stran A–P1, …, Pn–B (n+1), ``cisla`` = čísla nových bodů P1…Pn (n).
    Úhlová odchylka se rozdělí rovnoměrně, souřadnicová úměrně délkám stran."""
    n = len(cisla)
    if len(uhly) != n + 2 or len(delky) != n + 1:
        raise ValueError(f"Pořad s {n} novými body potřebuje {n + 2} úhlů a {n + 1} délek.")
    if any(d <= 0 for d in delky):
        raise ValueError("Délky stran musí být kladné.")
    s0 = smernik(a_orient, a)  # směrník „příchozí“ strany: z orientace na A
    s_konec = smernik(b, b_orient)
    # směrník přední záměry: σ_i = σ_{i−1} + β_i − 200
    s = s0
    sm = []
    for beta in uhly:
        s = norm_gon(s + beta - 200)
        sm.append(s)
    # sm[-1] je směrník z B na orientaci konce (vypočtený z měření)
    w = (sm[-1] - s_konec + 200) % 400 - 200  # úhlová odchylka
    oprava = -w / (n + 2)
    s = s0
    smer = []
    for beta in uhly:
        s = norm_gon(s + beta + oprava - 200)
        smer.append(s)
    strany = smer[:-1]  # směrníky stran A→P1 … Pn→B
    dys = [d * math.sin(gon2rad(sg)) for d, sg in zip(delky, strany)]
    dxs = [d * math.cos(gon2rad(sg)) for d, sg in zip(delky, strany)]
    ya, xa = _yx(a)
    yb, xb = _yx(b)
    ody = sum(dys) - (yb - ya)
    odx = sum(dxs) - (xb - xa)
    L = sum(delky)
    body, y, x = [], ya, xa
    for i in range(n):
        y += dys[i] - ody * delky[i] / L
        x += dxs[i] - odx * delky[i] / L
        body.append((cisla[i], P(y, x)))
    return PolygonovyPorad(body, w, ody, odx, math.hypot(ody, odx), L, strany)


# ------------------------------------------------------------------ oddělení parcely
def oddeleni_rovnobezne(parcela: list, a, b, vymera_cil: float) -> tuple[list[P], float]:
    """Oddělí od parcely (mnohoúhelník) část dané výměry dělicí čarou rovnoběžnou s přímkou A–B.

    Část se odděluje na straně přímky A–B, posun dělicí čáry se hledá půlením intervalu.
    Vrací (body oddělené části, vzdálenost dělicí čáry od A–B)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import split
    poly = Polygon([_yx(p) for p in parcela])
    if not poly.is_valid or poly.area <= 0:
        raise ValueError("Parcela není platný mnohoúhelník.")
    if not 0 < vymera_cil < poly.area:
        raise ValueError(f"Výměra musí být mezi 0 a {poly.area:.2f} m².")
    (ya, xa), (yb, xb) = _yx(a), _yx(b)
    c = math.hypot(yb - ya, xb - xa)
    if c == 0:
        raise ValueError("Body A a B splývají.")
    uy, ux = (yb - ya) / c, (xb - xa) / c
    ny, nx = -ux, uy  # normála (jedna strana)
    big = 10 * math.sqrt(poly.area) + c + max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
    # strana, na které leží parcela
    cy, cx = poly.centroid.x, poly.centroid.y
    sgn = 1 if (cy - ya) * ny + (cx - xa) * nx >= 0 else -1
    ny, nx = ny * sgn, nx * sgn

    def cast(t):
        oy, ox = ya + ny * t, xa + nx * t
        line = LineString([(oy - uy * big, ox - ux * big), (oy + uy * big, ox + ux * big)])
        parts = split(poly, line)
        side = [g for g in parts.geoms if ((g.centroid.x - oy) * ny + (g.centroid.y - ox) * nx) < 0]
        if not side:
            return None, 0.0
        g = side[0] if len(side) == 1 else max(side, key=lambda q: q.area)
        return g, sum(q.area for q in side)

    lo, hi = 0.0, max(math.hypot(px - ya, py - xa) for px, py in poly.exterior.coords) * 2
    for _ in range(200):
        mid = (lo + hi) / 2
        _g, area = cast(mid)
        if area < vymera_cil:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    g, _area = cast((lo + hi) / 2)
    if g is None:
        raise ValueError("Oddělení se nepodařilo – zkontrolujte, že přímka A–B leží na hranici parcely.")
    return [P(y, x) for y, x in list(g.exterior.coords)[:-1]], (lo + hi) / 2


def oddeleni_bodem(parcela: list, bod, vymera_cil: float, tol: float = 0.001) -> tuple[list[P], P]:
    """Oddělí od parcely část dané výměry dělicí čarou vedenou daným bodem na hranici (jako v Gromě).

    Oddělená část začíná v bodě a pokračuje po obvodu v pořadí zadaných lomových bodů, dokud nemá
    požadovanou výměru; druhý konec dělicí čáry (nový bod) leží na hranici. Výsledek je přesný
    (plocha trojúhelníku je na straně lineární). Vrací (body oddělené části, nový bod na hranici)."""
    pts = [_yx(p) for p in parcela]
    if len(pts) > 3 and math.dist(pts[0], pts[-1]) < 1e-9:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("Parcela musí mít aspoň tři body.")
    n = len(pts)
    s2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    celkem = abs(s2) / 2
    if celkem <= 0:
        raise ValueError("Parcela má nulovou výměru.")
    if not 0 < vymera_cil < celkem:
        raise ValueError(f"Výměra musí být mezi 0 a {celkem:.2f} m².")
    znam = 1.0 if s2 > 0 else -1.0
    py_, px_ = _yx(bod)
    # bod na hranici: vrchol, nebo na straně (vloží se jako vrchol)
    best = None
    for i in range(n):
        (y1, x1), (y2, x2) = pts[i], pts[(i + 1) % n]
        dy, dx = y2 - y1, x2 - x1
        ll = dy * dy + dx * dx
        t = 0.0 if ll == 0 else max(0.0, min(1.0, ((py_ - y1) * dy + (px_ - x1) * dx) / ll))
        d = math.hypot(y1 + t * dy - py_, x1 + t * dx - px_)
        if best is None or d < best[0]:
            best = (d, i, t)
    d, i, t = best
    if d > tol:
        raise ValueError(f"Bod dělicí čáry neleží na hranici parcely (vzdálenost {d:.3f} m).")
    if t < 1e-9:
        start = i
    elif t > 1 - 1e-9:
        start = (i + 1) % n
    else:
        pts.insert(i + 1, (py_, px_))
        n += 1
        start = i + 1
    kruh = pts[start:] + pts[:start]
    p0 = kruh[0]
    akum = 0.0
    for k in range(1, n - 1):
        a, b = kruh[k], kruh[k + 1]
        tri = znam * ((a[0] - p0[0]) * (b[1] - p0[1]) - (b[0] - p0[0]) * (a[1] - p0[1])) / 2
        if akum + tri >= vymera_cil - 1e-12:
            t = (vymera_cil - akum) / tri if tri > 0 else 0.0
            q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            cast = [p0] + kruh[1:k + 1] + ([q] if t > 1e-12 else [])
            if t >= 1 - 1e-12:
                cast = [p0] + kruh[1:k + 2]
                q = b
            from shapely.geometry import LineString, Polygon
            poly = Polygon(pts)
            if not poly.buffer(1e-6).contains(LineString([p0, q])):
                raise ValueError("Dělicí čára by vedla mimo parcelu (nekonvexní tvar) – zvolte jiný bod "
                                 "nebo opačné pořadí lomových bodů.")
            return [P(y, x) for y, x in cast], P(*q)
        akum += tri
    raise ValueError("Oddělení se nepodařilo (zkontrolujte pořadí lomových bodů parcely).")
