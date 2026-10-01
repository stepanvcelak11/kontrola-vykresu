"""CAD – kreslení a úpravy prvků DXF s neomezeným Zpět / Vpřed.

Každá změna výkresu je operace „přidané prvky + odebrané prvky“. Upravený prvek se nemění na místě:
vznikne jeho kopie s úpravou a původní se z modelu odpojí (zůstane v paměti pro Zpět). Odpojené prvky
se do DXF neukládají. Díky tomu je Zpět/Vpřed pro všechny nástroje stejné a bezpečné.

Vše pracuje v souřadnicích DXF (x, y) v plné přesnosti (float64).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ezdxf.math import Matrix44

from .uchyty import Oblouk, Usecka, primitiva

EPS = 1e-9


# ------------------------------------------------------------------ historie (Zpět / Vpřed)
@dataclass
class Operace:
    nazev: str
    pridano: list = field(default_factory=list)
    odebrano: list = field(default_factory=list)


class Historie:
    """Neomezené Zpět / Vpřed nad modelovým prostorem."""

    def __init__(self, msp):
        self.msp = msp
        self.zpet: list[Operace] = []
        self.vpred: list[Operace] = []
        self.zmena = 0  # počítadlo změn (pro „neuloženo“)

    def proved(self, nazev: str, pridano=(), odebrano=()) -> Operace:
        """Zaznamená operaci: ``pridano`` už jsou v modelu, ``odebrano`` se teď z modelu odpojí."""
        op = Operace(nazev, list(pridano), list(odebrano))
        for e in op.odebrano:
            self._odpoj(e)
        self.zpet.append(op)
        self.vpred.clear()
        self.zmena += 1
        return op

    def _odpoj(self, e):
        if e.dxf.owner is not None:
            self.msp.unlink_entity(e)

    def _pripoj(self, e):
        if e.dxf.owner is None:
            self.msp.add_entity(e)

    def krok_zpet(self) -> Operace | None:
        if not self.zpet:
            return None
        op = self.zpet.pop()
        for e in reversed(op.pridano):
            self._odpoj(e)
        for e in op.odebrano:
            self._pripoj(e)
        self.vpred.append(op)
        self.zmena += 1
        return op

    def krok_vpred(self) -> Operace | None:
        if not self.vpred:
            return None
        op = self.vpred.pop()
        for e in op.odebrano:
            self._odpoj(e)
        for e in op.pridano:
            self._pripoj(e)
        self.zpet.append(op)
        self.zmena += 1
        return op


# ------------------------------------------------------------------ kreslení
class Kresleni:
    """Kreslicí nástroje: nové prvky dostanou aktuální vrstvu a barvu (BYLAYER = 256)."""

    def __init__(self, msp, historie: Historie):
        self.msp = msp
        self.h = historie
        self.vrstva = "0"
        self.barva = 256
        self.typ_cary = "BYLAYER"
        self.tloustka = -1  # setiny mm, −1 = BYLAYER
        self.textovy_styl: str | None = None
        self.zarovnani: str | None = None  # TextEntityAlignment (např. TOP_LEFT)
        self.sirka_faktor = 1.0
        self.vyska_textu: float | None = None
        self.meritko_stylu: float | None = None
        self.predvolba = None

    def nastav_predvolbu(self, p) -> None:
        """Atributy podle druhu prvku ze zadání (viz ``cad.zadani.Predvolba``); None = výchozí."""
        self.predvolba = p
        if p is None:
            self.barva, self.typ_cary, self.tloustka = 256, "BYLAYER", -1
            self.textovy_styl = self.zarovnani = self.vyska_textu = self.meritko_stylu = None
            self.sirka_faktor = 1.0
            return
        self.vrstva, self.barva, self.typ_cary, self.tloustka = p.vrstva, p.barva, p.typ_cary, p.tloustka
        self.textovy_styl, self.zarovnani, self.sirka_faktor = p.textovy_styl, p.zarovnani, p.sirka_faktor
        self.vyska_textu, self.meritko_stylu = p.vyska, p.meritko_stylu

    def _attr(self, text: bool = False, **kw) -> dict:
        a = {"layer": self.vrstva, "color": self.barva}
        if not text:
            if self.typ_cary and self.typ_cary.upper() != "BYLAYER":
                a["linetype"] = self.typ_cary
            if self.tloustka != -1:
                a["lineweight"] = self.tloustka
            if self.meritko_stylu:
                a["ltscale"] = self.meritko_stylu
        else:
            if self.textovy_styl:
                a["style"] = self.textovy_styl
            if abs(self.sirka_faktor - 1.0) > 1e-9:
                a["width"] = self.sirka_faktor
        a.update(kw)
        return a

    def _hotovo(self, nazev, e):
        self.h.proved(nazev, [e] if not isinstance(e, list) else e)
        return e

    def bod(self, p):
        return self._hotovo("Bod", self.msp.add_point(_xy(p), dxfattribs=self._attr()))

    def usecka(self, a, b):
        if _dist(a, b) < EPS:
            raise ValueError("Úsečka nulové délky.")
        return self._hotovo("Úsečka", self.msp.add_line(_xy(a), _xy(b), dxfattribs=self._attr()))

    def polylinie(self, body, uzavrena: bool = False, bulge: list[float] | None = None):
        pts = _bez_duplicit(body)
        if len(pts) < 2:
            raise ValueError("Polylinie potřebuje aspoň dva různé body.")
        if bulge:
            pts = [(x, y, 0, 0, b) for (x, y), b in zip(pts, bulge)]
            e = self.msp.add_lwpolyline(pts, format="xyseb", close=uzavrena, dxfattribs=self._attr())
        else:
            e = self.msp.add_lwpolyline(pts, format="xy", close=uzavrena, dxfattribs=self._attr())
        return self._hotovo("Polylinie", e)

    def obdelnik(self, a, b):
        (x0, y0), (x1, y1) = _xy(a), _xy(b)
        if abs(x1 - x0) < EPS or abs(y1 - y0) < EPS:
            raise ValueError("Obdélník má nulovou šířku nebo výšku.")
        return self.polylinie([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True)

    def kruznice(self, stred, r: float):
        if r <= EPS:
            raise ValueError("Poloměr musí být kladný.")
        return self._hotovo("Kružnice", self.msp.add_circle(_xy(stred), r, dxfattribs=self._attr()))

    def oblouk_3body(self, a, b, c):
        s = stred_kruznice_3b(a, b, c)
        if s is None:
            raise ValueError("Tři body leží na přímce – oblouk neexistuje.")
        r = _dist(s, a)
        ua, uc = _uhel(s, a), _uhel(s, c)
        ub = _uhel(s, b)
        # oblouk v DXF jde proti směru hodin; prochází-li b „po cestě“ a→c CCW, start = a, jinak start = c
        if _ccw_mezi(ua, ub, uc):
            st, ko = ua, uc
        else:
            st, ko = uc, ua
        return self._hotovo("Oblouk", self.msp.add_arc(s, r, math.degrees(st), math.degrees(ko),
                                                       dxfattribs=self._attr()))

    def elipsa(self, stred, konec_hlavni, vedlejsi: float):
        (cx, cy), (ex, ey) = _xy(stred), _xy(konec_hlavni)
        a = math.hypot(ex - cx, ey - cy)
        if a < EPS or vedlejsi <= EPS:
            raise ValueError("Poloosy elipsy musí být kladné.")
        major = (ex - cx, ey - cy, 0)
        ratio = vedlejsi / a
        if ratio > 1:  # DXF vyžaduje poměr ≤ 1: hlavní poloosa je ta delší
            major = (-(ey - cy) * ratio, (ex - cx) * ratio, 0)
            ratio = 1 / ratio
        return self._hotovo("Elipsa", self.msp.add_ellipse((cx, cy), major, ratio, dxfattribs=self._attr()))

    def krivka(self, body):
        pts = _bez_duplicit(body)
        if len(pts) < 2:
            raise ValueError("Křivka potřebuje aspoň dva body.")
        return self._hotovo("Křivka", self.msp.add_spline(fit_points=[(x, y, 0) for x, y in pts],
                                                         dxfattribs=self._attr()))

    def text(self, p, text: str, vyska: float = 2.5, natoceni_deg: float = 0.0):
        if not text:
            raise ValueError("Prázdný text.")
        if vyska <= EPS:
            raise ValueError("Výška textu musí být kladná.")
        e = self.msp.add_text(text, height=vyska, rotation=natoceni_deg, dxfattribs=self._attr(text=True))
        if self.zarovnani:
            from ezdxf.enums import TextEntityAlignment
            e.set_placement(_xy(p), align=TextEntityAlignment[self.zarovnani])
        else:
            e.set_placement(_xy(p))
        return self._hotovo("Text", e)

    def sraf(self, hranice, vzor: str = "SOLID", meritko: float = 1.0):
        """Šrafa uvnitř uzavřeného prvku (uzavřená polylinie, kružnice, elipsa)."""
        h = self.msp.add_hatch(color=self.barva if self.barva != 256 else 256, dxfattribs={"layer": self.vrstva})
        t = hranice.dxftype()
        if t == "LWPOLYLINE" and (hranice.closed or _dist(hranice[0][:2], hranice[-1][:2]) < EPS):
            h.paths.add_polyline_path(list(hranice.get_points("xyb")), is_closed=True)
        elif t == "CIRCLE":
            ep = h.paths.add_edge_path()
            ep.add_arc(hranice.dxf.center, hranice.dxf.radius, 0, 360)
        elif t == "ELLIPSE" and abs((hranice.dxf.end_param - hranice.dxf.start_param) - math.tau) < 1e-9:
            ep = h.paths.add_edge_path()
            ep.add_ellipse(hranice.dxf.center, hranice.dxf.major_axis, hranice.dxf.ratio, 0, 360)
        else:
            self.msp.delete_entity(h)
            raise ValueError("Šrafovat jde jen uvnitř uzavřené polylinie, kružnice nebo celé elipsy.")
        if vzor.upper() != "SOLID":
            try:
                h.set_pattern_fill(vzor.upper(), scale=meritko)
            except Exception:  # noqa: BLE001
                self.msp.delete_entity(h)
                raise ValueError(f"Neznámý vzor šrafy „{vzor}“.") from None
        return self._hotovo("Šrafa", h)

    def kota(self, a, b, poloha, vyska_textu: float = 2.5):
        """Zarovnaná kóta délky A–B, kótovací čára prochází bodem ``poloha``."""
        if _dist(a, b) < EPS:
            raise ValueError("Kótované body splývají.")
        (ax, ay), (bx, by) = _xy(a), _xy(b)
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        d = self.msp.add_linear_dim(base=_xy(poloha), p1=(ax, ay), p2=(bx, by), angle=ang,
                                    override={"dimtxt": vyska_textu, "dimasz": vyska_textu * 0.8,
                                              "dimdec": 2},
                                    dxfattribs=self._attr())
        d.render()
        return self._hotovo("Kóta", d.dimension)


# ------------------------------------------------------------------ úpravy (transformace)
def _kopie(e):
    try:
        return e.copy()
    except Exception as ex:  # noqa: BLE001
        raise ValueError(f"Prvek {e.dxftype()} nejde kopírovat ({ex}).") from None


def transformuj(msp, h: Historie, ents, m: Matrix44, nazev: str, ponechat: bool = False) -> list:
    """Transformuje prvky maticí. ``ponechat`` = kopie (původní zůstanou)."""
    nove = []
    for e in ents:
        c = _kopie(e)
        c.transform(m)
        msp.add_entity(c)
        nove.append(c)
    h.proved(nazev, nove, [] if ponechat else list(ents))
    return nove


def posun(msp, h, ents, dx, dy, kopie=False):
    return transformuj(msp, h, ents, Matrix44.translate(dx, dy, 0), "Kopie" if kopie else "Posun", kopie)


def kopie_vicenasobna(msp, h, ents, dx, dy, pocet: int):
    nove = []
    for i in range(1, pocet + 1):
        for e in ents:
            c = _kopie(e)
            c.transform(Matrix44.translate(dx * i, dy * i, 0))
            msp.add_entity(c)
            nove.append(c)
    h.proved(f"Kopie {pocet}×", nove)
    return nove


def otoc(msp, h, ents, stred, uhel_rad, kopie=False):
    cx, cy = _xy(stred)
    m = Matrix44.chain(Matrix44.translate(-cx, -cy, 0), Matrix44.z_rotate(uhel_rad), Matrix44.translate(cx, cy, 0))
    return transformuj(msp, h, ents, m, "Otočení", kopie)


def meritko(msp, h, ents, stred, k: float, kopie=False):
    if abs(k) < EPS:
        raise ValueError("Měřítko nesmí být nulové.")
    cx, cy = _xy(stred)
    m = Matrix44.chain(Matrix44.translate(-cx, -cy, 0), Matrix44.scale(k, k, k), Matrix44.translate(cx, cy, 0))
    return transformuj(msp, h, ents, m, "Měřítko", kopie)


def zrcadli(msp, h, ents, a, b, kopie=False):
    (ax, ay), (bx, by) = _xy(a), _xy(b)
    if math.hypot(bx - ax, by - ay) < EPS:
        raise ValueError("Osa zrcadlení není určena (body splývají).")
    t = math.atan2(by - ay, bx - ax)
    m = Matrix44.chain(Matrix44.translate(-ax, -ay, 0), Matrix44.z_rotate(-t), Matrix44.scale(1, -1, 1),
                       Matrix44.z_rotate(t), Matrix44.translate(ax, ay, 0))
    return transformuj(msp, h, ents, m, "Zrcadlení", kopie)


def smaz(h, ents):
    ents = list(ents)
    if ents:
        h.proved("Smazání", [], ents)
    return len(ents)


def zmen_vlastnosti(msp, h, ents, **dxf) -> list:
    """Změní vrstvu, barvu, typ čáry… (kopie s novými vlastnostmi, kvůli jednotnému Zpět)."""
    nove = []
    for e in ents:
        c = _kopie(e)
        for k, v in dxf.items():
            c.dxf.set(k, v)
        msp.add_entity(c)
        nove.append(c)
    h.proved("Vlastnosti", nove, list(ents))
    return nove


# ------------------------------------------------------------------ rovnoběžka (offset)
def rovnobezka(msp, h, e, d: float, strana) -> object:
    """Rovnoběžný prvek ve vzdálenosti ``d`` na stranu bodu ``strana`` (úsečka, kružnice, oblouk, polylinie)."""
    if d <= EPS:
        raise ValueError("Vzdálenost musí být kladná.")
    sx, sy = _xy(strana)
    t = e.dxftype()
    c = _kopie(e)
    if t == "LINE":
        s, k = e.dxf.start, e.dxf.end
        dx, dy = k.x - s.x, k.y - s.y
        ll = math.hypot(dx, dy)
        nx, ny = -dy / ll, dx / ll  # normála vlevo
        sg = 1 if (sx - s.x) * nx + (sy - s.y) * ny >= 0 else -1
        c.dxf.start = (s.x + sg * nx * d, s.y + sg * ny * d, s.z)
        c.dxf.end = (k.x + sg * nx * d, k.y + sg * ny * d, k.z)
    elif t in ("CIRCLE", "ARC"):
        cc = e.dxf.center
        r = e.dxf.radius
        nr = r + d if math.hypot(sx - cc.x, sy - cc.y) > r else r - d
        if nr <= EPS:
            raise ValueError("Rovnoběžka dovnitř by měla nulový nebo záporný poloměr.")
        c.dxf.radius = nr
    elif t == "LWPOLYLINE":
        from shapely.geometry import LineString, Point
        pts = [(x, y) for x, y, *_ in e.get_points("xy")]
        if any(abs(b) > 1e-12 for *_x, b in e.get_points("xyb")):
            pts = [(v.x, v.y) for v in _cesta(e).flattening(0.001)]
        if e.closed:
            pts = pts + [pts[0]]
        g = LineString(pts)
        kand = [g.offset_curve(d, join_style="mitre", mitre_limit=10),
                g.offset_curve(-d, join_style="mitre", mitre_limit=10)]
        kand = [k for k in kand if not k.is_empty and k.geom_type == "LineString"]
        if not kand:
            raise ValueError("Rovnoběžku polylinie nejde sestrojit.")
        best = min(kand, key=lambda k: k.distance(Point(sx, sy)))
        coords = list(best.coords)
        if e.closed and _dist(coords[0], coords[-1]) < 1e-9:
            coords = coords[:-1]
        c = msp.add_lwpolyline(coords, format="xy", close=e.closed,
                               dxfattribs={k: e.dxf.get(k) for k in ("layer", "color", "linetype", "lineweight")
                                           if e.dxf.hasattr(k)})
        h.proved("Rovnoběžka", [c])
        return c
    else:
        raise ValueError(f"Rovnoběžka pro prvek {t} není podporovaná (úsečka, kružnice, oblouk, polylinie).")
    msp.add_entity(c)
    h.proved("Rovnoběžka", [c])
    return c


# ------------------------------------------------------------------ ořez a prodloužení
def _prim_hranic(ents, krome) -> tuple[list[Usecka], list[Oblouk]]:
    us, ob, body, _k = primitiva([e for e in ents if e is not krome])
    return us, ob


def _t_primka_usecka(x1, y1, x2, y2, u: Usecka):
    """Parametr t na nekonečné přímce (x1,y1)+t·d pro průsečík s úsečkou u (u v mezích úsečky)."""
    dx, dy = x2 - x1, y2 - y1
    ex, ey = u.x2 - u.x1, u.y2 - u.y1
    den = dx * ey - dy * ex
    if abs(den) < 1e-15:
        return []
    t = ((u.x1 - x1) * ey - (u.y1 - y1) * ex) / den
    s = ((u.x1 - x1) * dy - (u.y1 - y1) * dx) / den
    return [t] if -1e-9 <= s <= 1 + 1e-9 else []


def _t_primka_oblouk(x1, y1, x2, y2, o: Oblouk):
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - o.cx, y1 - o.cy
    A = dx * dx + dy * dy
    B = 2 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - o.r * o.r
    disc = B * B - 4 * A * C
    if A == 0 or disc < 0:
        return []
    out = []
    for s in (-1, 1):
        t = (-B + s * math.sqrt(disc)) / (2 * A)
        x, y = x1 + t * dx, y1 + t * dy
        if o.obsahuje(math.atan2(y - o.cy, x - o.cx)):
            out.append(t)
    return out


def _parametry_na_primce(e, hranice):
    s, k = e.dxf.start, e.dxf.end
    us, ob = hranice
    ts = []
    for u in us:
        ts += _t_primka_usecka(s.x, s.y, k.x, k.y, u)
    for o in ob:
        ts += _t_primka_oblouk(s.x, s.y, k.x, k.y, o)
    return sorted(set(round(t, 12) for t in ts))


def _uhly_na_kruznici(cx, cy, r, hranice):
    us, ob = hranice
    out = []
    for u in us:
        o = Oblouk(cx, cy, r, 0, math.tau, "", True)
        for t in _t_primka_oblouk(u.x1, u.y1, u.x2, u.y2, o):
            if -1e-9 <= t <= 1 + 1e-9:
                x, y = u.x1 + t * (u.x2 - u.x1), u.y1 + t * (u.y2 - u.y1)
                out.append(math.atan2(y - cy, x - cx) % math.tau)
    for b in ob:
        d = math.hypot(b.cx - cx, b.cy - cy)
        if d == 0 or d > r + b.r or d < abs(r - b.r):
            continue
        t = (r * r - b.r * b.r + d * d) / (2 * d)
        hh = math.sqrt(max(0.0, r * r - t * t))
        mx, my = cx + t * (b.cx - cx) / d, cy + t * (b.cy - cy) / d
        for s in (-1, 1):
            x, y = mx + s * hh * (b.cy - cy) / d, my - s * hh * (b.cx - cx) / d
            if b.obsahuje(math.atan2(y - b.cy, x - b.cx)):
                out.append(math.atan2(y - cy, x - cx) % math.tau)
    return sorted(set(round(a, 12) for a in out))


def orez(msp, h, e, klik, hranice_ents) -> list:
    """Ořízne část prvku mezi sousedními průsečíky s hranicemi, na které uživatel klikl.

    Úsečka, oblouk, kružnice. Vrací nově vzniklé prvky (0–2)."""
    hr = _prim_hranic(hranice_ents, e)
    kx, ky = _xy(klik)
    t = e.dxftype()
    nove = []
    if t == "LINE":
        s, k = e.dxf.start, e.dxf.end
        ts = [x for x in _parametry_na_primce(e, hr) if 1e-9 < x < 1 - 1e-9]
        if not ts:
            raise ValueError("Úsečka nemá s ostatními prvky žádný průsečík – není co oříznout.")
        dx, dy = k.x - s.x, k.y - s.y
        tp = ((kx - s.x) * dx + (ky - s.y) * dy) / (dx * dx + dy * dy)
        meze = [0.0] + ts + [1.0]
        for i in range(len(meze) - 1):
            if meze[i] <= tp <= meze[i + 1]:
                break
        else:
            i = 0 if tp < 0 else len(meze) - 2
        for a, b in ((0.0, meze[i]), (meze[i + 1], 1.0)):
            if b - a > 1e-12:
                c = _kopie(e)
                c.dxf.start = (s.x + a * dx, s.y + a * dy, s.z)
                c.dxf.end = (s.x + b * dx, s.y + b * dy, k.z)
                msp.add_entity(c)
                nove.append(c)
    elif t in ("ARC", "CIRCLE"):
        cc, r = e.dxf.center, e.dxf.radius
        uhly = _uhly_na_kruznici(cc.x, cc.y, r, hr)
        ak = math.atan2(ky - cc.y, kx - cc.x) % math.tau
        if t == "ARC":
            a0, a1 = math.radians(e.dxf.start_angle) % math.tau, math.radians(e.dxf.end_angle) % math.tau
            sweep = (a1 - a0) % math.tau or math.tau
            rel = sorted((u - a0) % math.tau for u in uhly if 1e-9 < (u - a0) % math.tau < sweep - 1e-9)
            if not rel:
                raise ValueError("Oblouk nemá s ostatními prvky žádný průsečík – není co oříznout.")
            rk = (ak - a0) % math.tau
            meze = [0.0] + rel + [sweep]
            for i in range(len(meze) - 1):
                if meze[i] <= rk <= meze[i + 1]:
                    break
            else:
                i = len(meze) - 2
            for a, b in ((0.0, meze[i]), (meze[i + 1], sweep)):
                if b - a > 1e-12:
                    c = _kopie(e)
                    c.dxf.start_angle = math.degrees(a0 + a)
                    c.dxf.end_angle = math.degrees(a0 + b)
                    msp.add_entity(c)
                    nove.append(c)
        else:
            if len(uhly) < 2:
                raise ValueError("Kružnici jde oříznout jen mezi dvěma průsečíky.")
            # najít úsek mezi sousedními úhly, ve kterém je klik; zbytek je oblouk
            for i in range(len(uhly)):
                a, b = uhly[i], uhly[(i + 1) % len(uhly)]
                if (ak - a) % math.tau <= (b - a) % math.tau:
                    break
            attrs = {k: e.dxf.get(k) for k in ("layer", "color", "linetype", "lineweight") if e.dxf.hasattr(k)}
            c = msp.add_arc((cc.x, cc.y), r, math.degrees(b), math.degrees(a), dxfattribs=attrs)
            nove.append(c)
    else:
        raise ValueError(f"Ořez prvku {t} není podporovaný (úsečka, oblouk, kružnice) – polylinii nejdřív rozpojte.")
    h.proved("Ořez", nove, [e])
    return nove


def prodluz(msp, h, e, klik, hranice_ents):
    """Prodlouží úsečku (konec bližší kliknutí) k nejbližšímu průsečíku s hranicemi."""
    if e.dxftype() != "LINE":
        raise ValueError("Prodloužit jde úsečka (polylinii nejdřív rozpojte).")
    hr = _prim_hranic(hranice_ents, e)
    s, k = e.dxf.start, e.dxf.end
    kx, ky = _xy(klik)
    ts = _parametry_na_primce(e, hr)
    konec = math.hypot(kx - k.x, ky - k.y) <= math.hypot(kx - s.x, ky - s.y)
    if konec:
        kand = [t for t in ts if t > 1 + 1e-9]
        if not kand:
            raise ValueError("Ve směru prodloužení není žádný prvek.")
        t = min(kand)
    else:
        kand = [t for t in ts if t < -1e-9]
        if not kand:
            raise ValueError("Ve směru prodloužení není žádný prvek.")
        t = max(kand)
    c = _kopie(e)
    p = (s.x + t * (k.x - s.x), s.y + t * (k.y - s.y), s.z)
    if konec:
        c.dxf.end = p
    else:
        c.dxf.start = p
    msp.add_entity(c)
    h.proved("Prodloužení", [c], [e])
    return c


# ------------------------------------------------------------------ zaoblení (a roh)
def zaobli(msp, h, e1, klik1, e2, klik2, r: float):
    """Zaoblí dvě úsečky obloukem o poloměru r (r = 0 → ostrý roh). Ponechají se části, na které se klikl."""
    if e1.dxftype() != "LINE" or e2.dxftype() != "LINE":
        raise ValueError("Zaoblit jde dvě úsečky.")
    if e1 is e2:
        raise ValueError("Vyberte dvě různé úsečky.")
    if r < 0:
        raise ValueError("Poloměr nesmí být záporný.")
    a1, b1 = _xy(e1.dxf.start), _xy(e1.dxf.end)
    a2, b2 = _xy(e2.dxf.start), _xy(e2.dxf.end)
    p = _prusecik_primek(a1, b1, a2, b2)
    if p is None:
        raise ValueError("Úsečky jsou rovnoběžné.")

    def zachovany_konec(a, b, klik):
        # konec úsečky na straně kliknutí od průsečíku
        ux, uy = b[0] - a[0], b[1] - a[1]
        tk = (klik[0] - p[0]) * ux + (klik[1] - p[1]) * uy
        ta = (a[0] - p[0]) * ux + (a[1] - p[1]) * uy
        tb = (b[0] - p[0]) * ux + (b[1] - p[1]) * uy
        if tk >= 0:
            return a if ta > tb else b
        return a if ta < tb else b

    k1 = zachovany_konec(a1, b1, _xy(klik1))
    k2 = zachovany_konec(a2, b2, _xy(klik2))
    d1, d2 = _dist(p, k1), _dist(p, k2)
    if d1 < EPS or d2 < EPS:
        raise ValueError("Úsečka končí v průsečíku na straně kliknutí – klikněte na část, která má zůstat.")
    u1 = ((k1[0] - p[0]) / d1, (k1[1] - p[1]) / d1)
    u2 = ((k2[0] - p[0]) / d2, (k2[1] - p[1]) / d2)
    cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    theta = math.acos(cos_t)
    if theta < 1e-9 or abs(theta - math.pi) < 1e-9:
        raise ValueError("Úsečky leží v jedné přímce.")
    t = r / math.tan(theta / 2) if r > 0 else 0.0
    if t > d1 + 1e-9 or t > d2 + 1e-9:
        raise ValueError("Poloměr je pro tyto úsečky příliš velký.")
    t1 = (p[0] + u1[0] * t, p[1] + u1[1] * t)
    t2 = (p[0] + u2[0] * t, p[1] + u2[1] * t)
    nove = []
    for e, k, tt in ((e1, k1, t1), (e2, k2, t2)):
        c = _kopie(e)
        c.dxf.start = (k[0], k[1], 0)
        c.dxf.end = (tt[0], tt[1], 0)
        msp.add_entity(c)
        nove.append(c)
    if r > 0:
        bx, by = u1[0] + u2[0], u1[1] + u2[1]
        bl = math.hypot(bx, by)
        dc = r / math.sin(theta / 2)
        cx, cy = p[0] + bx / bl * dc, p[1] + by / bl * dc
        s1, s2 = math.atan2(t1[1] - cy, t1[0] - cx), math.atan2(t2[1] - cy, t2[0] - cx)
        if (s2 - s1) % math.tau > math.pi:
            s1, s2 = s2, s1
        attrs = {k: e1.dxf.get(k) for k in ("layer", "color", "linetype", "lineweight") if e1.dxf.hasattr(k)}
        nove.append(msp.add_arc((cx, cy), r, math.degrees(s1), math.degrees(s2), dxfattribs=attrs))
    h.proved("Zaoblení" if r > 0 else "Roh", nove, [e1, e2])
    return nove


# ------------------------------------------------------------------ rozpojení a spojení
def rozpoj(msp, h, ents) -> list:
    """Rozpojí polylinie, bloky, kóty, víceřádkové texty na jednoduché prvky."""
    nove, odeb = [], []
    for e in ents:
        if e.dxftype() not in ("LWPOLYLINE", "POLYLINE", "INSERT", "DIMENSION", "MTEXT", "HATCH"):
            continue
        try:
            casti = list(e.virtual_entities()) if e.dxftype() != "MTEXT" else _mtext_na_texty(e)
        except Exception:  # noqa: BLE001
            continue
        for v in casti:
            if e.dxftype() != "INSERT":
                v.dxf.layer = e.dxf.layer
            msp.add_entity(v)
            nove.append(v)
        odeb.append(e)
    if not odeb:
        raise ValueError("Ve výběru není nic k rozpojení (polylinie, blok, kóta, odstavec textu, šrafa).")
    h.proved("Rozpojení", nove, odeb)
    return nove


def _mtext_na_texty(e):
    from ezdxf.entities import Text
    out = []
    zakl = e.dxf.insert
    vyska = e.dxf.char_height
    for i, radek in enumerate(e.plain_text().split("\n")):
        if not radek.strip():
            continue
        t = Text.new(dxfattribs={"text": radek, "height": vyska, "layer": e.dxf.layer,
                                 "insert": (zakl.x, zakl.y - (i + 1) * vyska * 1.5, 0)})
        out.append(t)
    return out


def _vrcholy(e) -> list[tuple[float, float, float]]:
    """Prvek jako otevřená cesta vrcholů (x, y, bulge k dalšímu vrcholu)."""
    t = e.dxftype()
    if t == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y, 0.0), (e.dxf.end.x, e.dxf.end.y, 0.0)]
    if t == "ARC":
        c, r = e.dxf.center, e.dxf.radius
        a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
        sw = (a1 - a0) % math.tau
        return [(c.x + r * math.cos(a0), c.y + r * math.sin(a0), math.tan(sw / 4)),
                (c.x + r * math.cos(a1), c.y + r * math.sin(a1), 0.0)]
    if t == "LWPOLYLINE" and not e.closed:
        return [(x, y, b) for x, y, b in e.get_points("xyb")]
    raise ValueError(f"Prvek {t} nejde spojit (úsečka, oblouk, otevřená polylinie).")


def _obrat(v):
    n = len(v)
    return [(v[n - 1 - i][0], v[n - 1 - i][1], -v[n - 2 - i][2] if i < n - 1 else 0.0) for i in range(n)]


def spoj(msp, h, ents, tol: float = 1e-6):
    """Spojí navazující úsečky, oblouky a polylinie do jedné polylinie."""
    ents = list(ents)
    if len(ents) < 2:
        raise ValueError("Vyberte aspoň dva navazující prvky.")
    cesty = [(e, _vrcholy(e)) for e in ents]
    e0, cesta = cesty.pop(0)
    pouzite = [e0]
    zmena = True
    while cesty and zmena:
        zmena = False
        for i, (e, v) in enumerate(cesty):
            konec, zac = cesta[-1], cesta[0]
            if _dist(konec[:2], v[0][:2]) <= tol:
                cesta = cesta[:-1] + [(konec[0], konec[1], v[0][2])] + v[1:]
            elif _dist(konec[:2], v[-1][:2]) <= tol:
                w = _obrat(v)
                cesta = cesta[:-1] + [(konec[0], konec[1], w[0][2])] + w[1:]
            elif _dist(zac[:2], v[-1][:2]) <= tol:
                cesta = v[:-1] + [(v[-1][0], v[-1][1], zac[2])] + cesta[1:]
            elif _dist(zac[:2], v[0][:2]) <= tol:
                w = _obrat(v)
                cesta = w[:-1] + [(w[-1][0], w[-1][1], zac[2])] + cesta[1:]
            else:
                continue
            pouzite.append(e)
            cesty.pop(i)
            zmena = True
            break
    if cesty:
        raise ValueError(f"{len(cesty)} prvků nenavazuje (konce se nedotýkají) – spojeno by nebylo vše.")
    uzavrena = _dist(cesta[0][:2], cesta[-1][:2]) <= tol and len(cesta) > 2
    if uzavrena:
        cesta = cesta[:-1]
    attrs = {k: e0.dxf.get(k) for k in ("layer", "color", "linetype", "lineweight") if e0.dxf.hasattr(k)}
    p = msp.add_lwpolyline([(x, y, 0, 0, b) for x, y, b in cesta], format="xyseb", close=uzavrena,
                           dxfattribs=attrs)
    h.proved("Spojení", [p], pouzite)
    return p


# ------------------------------------------------------------------ výběr (hledání prvků pod kurzorem)
class IndexVyberu:
    """Geometrie prvků pro výběr kliknutím a oknem (Shapely, plná přesnost)."""

    def __init__(self, msp):
        self.msp = msp
        self.obnov()

    def obnov(self):
        self.polozky = []
        for e in self.msp:
            g = geometrie(e)
            if g is not None and not g.is_empty:
                self.polozky.append((e, g, g.bounds))

    def najdi(self, x, y, tol) -> object | None:
        from shapely.geometry import Point
        p = Point(x, y)
        best, bd = None, tol
        for e, g, (x0, y0, x1, y1) in self.polozky:
            if x < x0 - tol or x > x1 + tol or y < y0 - tol or y > y1 + tol:
                continue
            d = g.distance(p)
            if d <= bd:
                best, bd = e, d
        return best

    def okno(self, x0, y0, x1, y1, protinajici: bool = False) -> list:
        from shapely.geometry import box
        b = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        out = []
        for e, g, _bb in self.polozky:
            if (b.intersects(g) if protinajici else b.contains(g)):
                out.append(e)
        return out

    def geometrie(self, e):
        for f, g, _bb in self.polozky:
            if f is e:
                return g
        return None


def _cesta(e):
    from ezdxf import path as zpath
    return zpath.make_path(e)


def geometrie(e):
    """Shapely geometrie prvku (čáry jako LineString, body jako Point, texty a bloky obdélníkem)."""
    from shapely.geometry import LineString, MultiLineString, Point, box
    t = e.dxftype()
    try:
        if t == "POINT":
            return Point(e.dxf.location.x, e.dxf.location.y)
        if t == "LINE":
            s, k = e.dxf.start, e.dxf.end
            if (s.x, s.y) == (k.x, k.y):
                return Point(s.x, s.y)
            return LineString([(s.x, s.y), (k.x, k.y)])
        if t in ("LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
            p = _cesta(e)
            pts = [(v.x, v.y) for v in p.flattening(0.01, segments=8)]
            if len(pts) < 2:
                return Point(pts[0]) if pts else None
            return LineString(pts)
        if t in ("TEXT", "MTEXT", "INSERT", "DIMENSION", "HATCH", "SOLID", "IMAGE", "ATTRIB"):
            from ezdxf import bbox
            ext = bbox.extents([e], fast=True)
            if not ext.has_data:
                return None
            x0, y0, x1, y1 = ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y
            if t in ("TEXT", "MTEXT", "INSERT", "IMAGE"):
                return box(x0, y0, x1, y1) if (x1 > x0 or y1 > y0) else Point(x0, y0)
            lines = []
            for v in e.virtual_entities() if t != "HATCH" else []:
                g = geometrie(v)
                if g is not None and g.geom_type == "LineString":
                    lines.append(g)
            if lines:
                return MultiLineString(lines)
            return box(x0, y0, x1, y1).exterior
    except Exception:  # noqa: BLE001 – poškozený prvek jen nepůjde vybrat
        return None
    return None


# ------------------------------------------------------------------ pomocné
def _xy(p) -> tuple[float, float]:
    if hasattr(p, "x"):
        return float(p.x), float(p.y)
    return float(p[0]), float(p[1])


def _dist(a, b) -> float:
    (ax, ay), (bx, by) = _xy(a), _xy(b)
    return math.hypot(bx - ax, by - ay)


def _uhel(s, p) -> float:
    (sx, sy), (px, py) = _xy(s), _xy(p)
    return math.atan2(py - sy, px - sx) % math.tau


def _ccw_mezi(a, b, c) -> bool:
    """Leží úhel b na cestě z a do c proti směru hodin?"""
    return (b - a) % math.tau <= (c - a) % math.tau


def _bez_duplicit(body):
    out = []
    for p in body:
        q = _xy(p)
        if not out or _dist(out[-1], q) > EPS:
            out.append(q)
    return out


def stred_kruznice_3b(a, b, c):
    (ax, ay), (bx, by), (cx, cy) = _xy(a), _xy(b), _xy(c)
    # výpočet relativně k bodu a – kvůli přesnosti u velkých souřadnic S-JTSK
    bx_, by_, cx_, cy_ = bx - ax, by - ay, cx - ax, cy - ay
    d = 2 * (bx_ * cy_ - by_ * cx_)
    if abs(d) < 1e-12 * max(1e-12, _dist(a, b) * _dist(a, c)):
        return None
    ux = (cy_ * (bx_ * bx_ + by_ * by_) - by_ * (cx_ * cx_ + cy_ * cy_)) / d
    uy = (bx_ * (cx_ * cx_ + cy_ * cy_) - cx_ * (bx_ * bx_ + by_ * by_)) / d
    return ax + ux, ay + uy


def _prusecik_primek(a1, b1, a2, b2):
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = a1, b1, a2, b2
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-15:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


# ------------------------------------------------------------------ bloky (buňky)
def vytvor_blok(doc, msp, h: Historie, ents, nazev: str, zakladni_bod, nahradit: bool = True):
    """Z prvků vytvoří definici bloku (základní bod = vkládací bod) a prvky nahradí jeho vložením."""
    nazev = (nazev or "").strip()
    if not nazev or any(c in nazev for c in '<>/\\":;?*|=`'):
        raise ValueError("Neplatný název bloku.")
    if nazev in doc.blocks:
        raise ValueError(f"Blok {nazev} už existuje.")
    ents = list(ents)
    if not ents:
        raise ValueError("Blok musí obsahovat aspoň jeden prvek.")
    bx, by = _xy(zakladni_bod)
    blk = doc.blocks.new(nazev, base_point=(0, 0, 0))
    m = Matrix44.translate(-bx, -by, 0)
    for e in ents:
        c = _kopie(e)
        c.transform(m)
        blk.add_entity(c)
    if not nahradit:
        return None
    ins = msp.add_blockref(nazev, (bx, by), dxfattribs={"layer": ents[0].dxf.get("layer", "0")})
    h.proved(f"Blok {nazev}", [ins], ents)
    return ins


def vloz_blok(doc, msp, h: Historie, nazev: str, bod, meritko: float = 1.0, natoceni_deg: float = 0.0,
              vrstva: str = "0"):
    if nazev not in doc.blocks or nazev.startswith("*"):
        raise ValueError(f"Blok {nazev} ve výkresu není.")
    if abs(meritko) < EPS:
        raise ValueError("Měřítko nesmí být nulové.")
    ins = msp.add_blockref(nazev, _xy(bod), dxfattribs={"layer": vrstva, "xscale": meritko, "yscale": meritko,
                                                         "zscale": meritko, "rotation": natoceni_deg})
    blk = doc.blocks.get(nazev)
    if any(e.dxftype() == "ATTDEF" for e in blk):
        ins.add_auto_attribs({})
    h.proved(f"Vložení {nazev}", [ins])
    return ins


def bloky(doc) -> list[str]:
    """Uživatelské bloky (bez anonymních *D, *U, rozvržení)."""
    return sorted((b.name for b in doc.blocks if not b.name.startswith("*") and not b.is_any_layout),
                  key=str.lower)
