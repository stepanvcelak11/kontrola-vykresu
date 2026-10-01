"""Úchyty (snapy), ortho / polární režim a zadávání souřadnic z klávesnice.

Pracuje v souřadnicích DXF (x, y). Výkresy z MicroStationu v S-JTSK mají x = −Y, y = −X.
Geometrie se z entit vytáhne jednou (úsečky, oblouky, body) a uloží do mřížkového indexu;
po změně výkresu se index přestaví (``Uchyty.obnov``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

TYPY = {"konec": "koncový bod", "stred": "střed", "prusecik": "průsečík", "kolmice": "kolmice",
        "tecna": "tečna", "stred_kruznice": "střed kružnice", "bod": "bod"}
PRIORITA = {"konec": 0, "prusecik": 1, "bod": 1, "stred_kruznice": 2, "stred": 2, "kolmice": 3, "tecna": 3}


@dataclass
class Usecka:
    x1: float
    y1: float
    x2: float
    y2: float
    handle: str


@dataclass
class Oblouk:
    cx: float
    cy: float
    r: float
    a0: float  # rad, proti směru hodin (DXF)
    a1: float
    handle: str
    plny: bool = False

    def obsahuje(self, a: float) -> bool:
        if self.plny:
            return True
        a0 = self.a0 % (2 * math.pi)
        a1 = self.a1 % (2 * math.pi)
        a = a % (2 * math.pi)
        return (a0 <= a <= a1) if a0 <= a1 else (a >= a0 or a <= a1)

    def bod(self, a: float) -> tuple[float, float]:
        return self.cx + self.r * math.cos(a), self.cy + self.r * math.sin(a)


@dataclass
class Uchyt:
    typ: str
    x: float
    y: float
    handle: str = ""

    @property
    def popis(self) -> str:
        return TYPY.get(self.typ, self.typ)


def _bulge_arc(p1, p2, bulge, handle) -> Oblouk:
    (x1, y1), (x2, y2) = p1, p2
    ang = 4 * math.atan(bulge)
    c = math.hypot(x2 - x1, y2 - y1)
    r = c / (2 * math.sin(abs(ang) / 2))
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    h = math.sqrt(max(0.0, r * r - c * c / 4))
    ux, uy = (x2 - x1) / c, (y2 - y1) / c
    s = 1 if (bulge > 0) == (abs(ang) < math.pi) else -1
    cx, cy = mx - s * uy * h, my + s * ux * h
    a1, a2 = math.atan2(y1 - cy, x1 - cx), math.atan2(y2 - cy, x2 - cx)
    return Oblouk(cx, cy, r, a1, a2, handle) if bulge > 0 else Oblouk(cx, cy, r, a2, a1, handle)


def primitiva(entities) -> tuple[list[Usecka], list[Oblouk], list[tuple[float, float, str, str]], list]:
    """Z entit DXF: úsečky, oblouky, body (x, y, handle, druh) a koncové body polylinií."""
    us: list[Usecka] = []
    ob: list[Oblouk] = []
    body: list[tuple[float, float, str, str]] = []
    konce: list[tuple[float, float, str]] = []
    for e in entities:
        t = e.dxftype()
        h = e.dxf.handle
        try:
            if t == "LINE":
                s, k = e.dxf.start, e.dxf.end
                us.append(Usecka(s.x, s.y, k.x, k.y, h))
                konce += [(s.x, s.y, h), (k.x, k.y, h)]
            elif t == "LWPOLYLINE":
                pts = list(e.get_points("xyb"))
                n = len(pts)
                rng = range(n if e.closed else n - 1)
                for i in rng:
                    x1, y1, b = pts[i]
                    x2, y2, _ = pts[(i + 1) % n]
                    if abs(b) > 1e-9 and (x1, y1) != (x2, y2):
                        ob.append(_bulge_arc((x1, y1), (x2, y2), b, h))
                    else:
                        us.append(Usecka(x1, y1, x2, y2, h))
                konce += [(p[0], p[1], h) for p in pts]
            elif t == "POLYLINE":
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                n = len(pts)
                for i in range(n if e.is_closed else n - 1):
                    (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
                    us.append(Usecka(x1, y1, x2, y2, h))
                konce += [(p[0], p[1], h) for p in pts]
            elif t in ("ARC", "CIRCLE"):
                c = e.dxf.center
                if t == "CIRCLE":
                    ob.append(Oblouk(c.x, c.y, e.dxf.radius, 0, 2 * math.pi, h, True))
                else:
                    o = Oblouk(c.x, c.y, e.dxf.radius, math.radians(e.dxf.start_angle),
                               math.radians(e.dxf.end_angle), h)
                    ob.append(o)
                    konce += [(*o.bod(o.a0), h), (*o.bod(o.a1), h)]
            elif t in ("ELLIPSE", "SPLINE"):
                from ezdxf import path as zpath
                p = zpath.make_path(e)
                v = [(q.x, q.y) for q in p.flattening(0.01)]
                for a, b in zip(v, v[1:]):
                    us.append(Usecka(a[0], a[1], b[0], b[1], h))
                if v:
                    konce += [(v[0][0], v[0][1], h), (v[-1][0], v[-1][1], h)]
            elif t == "POINT":
                p = e.dxf.location
                body.append((p.x, p.y, h, "bod"))
            elif t in ("INSERT", "TEXT", "MTEXT"):
                p = e.dxf.insert
                body.append((p.x, p.y, h, "bod"))
        except Exception:  # noqa: BLE001 – poškozená entita nesmí shodit úchyty
            continue
    return us, ob, body, konce


def _pata(px, py, u: Usecka):
    dx, dy = u.x2 - u.x1, u.y2 - u.y1
    ll = dx * dx + dy * dy
    if ll == 0:
        return None
    t = ((px - u.x1) * dx + (py - u.y1) * dy) / ll
    if not 0 <= t <= 1:
        return None
    return u.x1 + t * dx, u.y1 + t * dy


def _prusecik_uu(a: Usecka, b: Usecka):
    d = (a.x2 - a.x1) * (b.y2 - b.y1) - (a.y2 - a.y1) * (b.x2 - b.x1)
    if abs(d) < 1e-15:
        return []
    t = ((b.x1 - a.x1) * (b.y2 - b.y1) - (b.y1 - a.y1) * (b.x2 - b.x1)) / d
    u = ((b.x1 - a.x1) * (a.y2 - a.y1) - (b.y1 - a.y1) * (a.x2 - a.x1)) / d
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return [(a.x1 + t * (a.x2 - a.x1), a.y1 + t * (a.y2 - a.y1))]
    return []


def _prusecik_uo(a: Usecka, o: Oblouk):
    dx, dy = a.x2 - a.x1, a.y2 - a.y1
    fx, fy = a.x1 - o.cx, a.y1 - o.cy
    A = dx * dx + dy * dy
    B = 2 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - o.r * o.r
    disc = B * B - 4 * A * C
    if A == 0 or disc < 0:
        return []
    out = []
    for s in (-1, 1):
        t = (-B + s * math.sqrt(disc)) / (2 * A)
        if -1e-9 <= t <= 1 + 1e-9:
            x, y = a.x1 + t * dx, a.y1 + t * dy
            if o.obsahuje(math.atan2(y - o.cy, x - o.cx)):
                out.append((x, y))
    return out


def _prusecik_oo(a: Oblouk, b: Oblouk):
    d = math.hypot(b.cx - a.cx, b.cy - a.cy)
    if d == 0 or d > a.r + b.r or d < abs(a.r - b.r):
        return []
    t = (a.r * a.r - b.r * b.r + d * d) / (2 * d)
    h = math.sqrt(max(0.0, a.r * a.r - t * t))
    mx, my = a.cx + t * (b.cx - a.cx) / d, a.cy + t * (b.cy - a.cy) / d
    out = []
    for s in (-1, 1):
        x, y = mx + s * h * (b.cy - a.cy) / d, my - s * h * (b.cx - a.cx) / d
        if a.obsahuje(math.atan2(y - a.cy, x - a.cx)) and b.obsahuje(math.atan2(y - b.cy, x - b.cx)):
            out.append((x, y))
    return out


class Uchyty:
    def __init__(self, entities=(), zapnute: set[str] | None = None):
        self.zapnute = set(zapnute) if zapnute is not None else set(TYPY)
        self.obnov(entities)

    def obnov(self, entities) -> None:
        self.us, self.ob, self.body, self.konce = primitiva(entities)
        xs = [u.x1 for u in self.us] + [u.x2 for u in self.us] + [o.cx for o in self.ob] + [b[0] for b in self.body]
        ys = [u.y1 for u in self.us] + [u.y2 for u in self.us] + [o.cy for o in self.ob] + [b[1] for b in self.body]
        span = max((max(xs) - min(xs)) if xs else 1.0, (max(ys) - min(ys)) if ys else 1.0, 1e-6)
        self.cell = span / 150.0
        self.grid: dict[tuple[int, int], list] = {}

        def add(obj, x0, y0, x1, y1):
            c = self.cell
            for i in range(int(math.floor(min(x0, x1) / c)), int(math.floor(max(x0, x1) / c)) + 1):
                for j in range(int(math.floor(min(y0, y1) / c)), int(math.floor(max(y0, y1) / c)) + 1):
                    self.grid.setdefault((i, j), []).append(obj)
        for u in self.us:
            add(u, u.x1, u.y1, u.x2, u.y2)
        for o in self.ob:
            add(o, o.cx - o.r, o.cy - o.r, o.cx + o.r, o.cy + o.r)
        for b in self.body:
            add(b, b[0], b[1], b[0], b[1])
        for k in self.konce:
            add(("k",) + k, k[0], k[1], k[0], k[1])

    def _blizko(self, x, y, tol):
        c = self.cell
        seen, out = set(), []
        for i in range(int(math.floor((x - tol) / c)), int(math.floor((x + tol) / c)) + 1):
            for j in range(int(math.floor((y - tol) / c)), int(math.floor((y + tol) / c)) + 1):
                for o in self.grid.get((i, j), ()):
                    if id(o) not in seen:
                        seen.add(id(o))
                        out.append(o)
        return out

    def najdi(self, x: float, y: float, tol: float, posledni: tuple[float, float] | None = None) -> Uchyt | None:
        """Nejlepší úchyt v okolí kurzoru (tolerance ve výkresových jednotkách)."""
        objs = self._blizko(x, y, tol)
        kand: list[Uchyt] = []
        z = self.zapnute
        segs = [o for o in objs if isinstance(o, Usecka)]
        arcs = [o for o in objs if isinstance(o, Oblouk)]
        for o in objs:
            if isinstance(o, tuple) and o[0] == "k" and "konec" in z:
                kand.append(Uchyt("konec", o[1], o[2], o[3]))
            elif isinstance(o, tuple) and len(o) == 4 and "bod" in z:
                kand.append(Uchyt("bod", o[0], o[1], o[2]))
        for u in segs:
            if "konec" in z:
                kand += [Uchyt("konec", u.x1, u.y1, u.handle), Uchyt("konec", u.x2, u.y2, u.handle)]
            if "stred" in z:
                kand.append(Uchyt("stred", (u.x1 + u.x2) / 2, (u.y1 + u.y2) / 2, u.handle))
            if "kolmice" in z and posledni is not None:
                p = _pata(posledni[0], posledni[1], u)
                if p:
                    kand.append(Uchyt("kolmice", p[0], p[1], u.handle))
        for o in arcs:
            if "stred_kruznice" in z:
                kand.append(Uchyt("stred_kruznice", o.cx, o.cy, o.handle))
            if "stred" in z and not o.plny:
                a1 = o.a1 if o.a1 > o.a0 else o.a1 + 2 * math.pi
                kand.append(Uchyt("stred", *o.bod((o.a0 + a1) / 2), o.handle))
            if posledni is not None:
                px, py = posledni
                d = math.hypot(px - o.cx, py - o.cy)
                if "kolmice" in z and d > 0:
                    a = math.atan2(py - o.cy, px - o.cx)
                    for aa in (a, a + math.pi):
                        if o.obsahuje(aa):
                            kand.append(Uchyt("kolmice", *o.bod(aa), o.handle))
                if "tecna" in z and d > o.r:
                    a = math.atan2(py - o.cy, px - o.cx)
                    beta = math.acos(o.r / d)
                    for aa in (a + beta, a - beta):
                        if o.obsahuje(aa):
                            kand.append(Uchyt("tecna", *o.bod(aa), o.handle))
        if "prusecik" in z:
            prim = segs + arcs
            for i, a in enumerate(prim):
                for b in prim[i + 1:]:
                    if a.handle == b.handle and isinstance(a, Usecka) and isinstance(b, Usecka):
                        continue  # sousední úseky téže čáry se protínají ve vrcholu – to je „konec“
                    if isinstance(a, Usecka) and isinstance(b, Usecka):
                        pts = _prusecik_uu(a, b)
                    elif isinstance(a, Usecka):
                        pts = _prusecik_uo(a, b)
                    elif isinstance(b, Usecka):
                        pts = _prusecik_uo(b, a)
                    else:
                        pts = _prusecik_oo(a, b)
                    kand += [Uchyt("prusecik", px, py, a.handle) for px, py in pts]
        best, best_key = None, None
        for k in kand:
            d = math.hypot(k.x - x, k.y - y)
            if d > tol:
                continue
            key = (PRIORITA.get(k.typ, 9), d)
            if best_key is None or key < best_key:
                best, best_key = k, key
        return best


def ortho(posledni: tuple[float, float], x: float, y: float) -> tuple[float, float]:
    """Ortho: jen vodorovně nebo svisle od posledního bodu."""
    dx, dy = x - posledni[0], y - posledni[1]
    return (x, posledni[1]) if abs(dx) >= abs(dy) else (posledni[0], y)


def polarni(posledni: tuple[float, float], x: float, y: float, krok_gon: float = 50.0) -> tuple[float, float]:
    """Polární režim: směr od posledního bodu zaokrouhlený na násobek ``krok_gon`` (vzdálenost zůstane)."""
    dx, dy = x - posledni[0], y - posledni[1]
    d = math.hypot(dx, dy)
    if d == 0:
        return x, y
    krok = krok_gon * math.pi / 200.0
    a = round(math.atan2(dy, dx) / krok) * krok
    return posledni[0] + d * math.cos(a), posledni[1] + d * math.sin(a)


_NUM = r"[+-]?\d+(?:[.,]\d+)?"


def zadani_bodu(text: str, posledni: tuple[float, float] | None, sjtsk: bool) -> tuple[float, float]:
    """Souřadnice z příkazového řádku (výsledek v DXF x, y):

    * ``Y X`` nebo ``Y,X`` – absolutně; u výkresu v S-JTSK (záporné souřadnice) se kladné Y X převedou,
    * ``x=… y=…`` – přímo souřadnice DXF,
    * ``@dx,dy`` – relativně (DXF),
    * ``@d<σ`` – polárně: délka a směrník v gonech (S-JTSK: od +X po směru hodin), u ostatních výkresů
      úhel v gonech od osy x proti směru hodin.
    """
    t = text.strip().replace(";", ",")
    f = lambda s: float(s.replace(",", "."))  # noqa: E731
    m = re.fullmatch(rf"@\s*({_NUM})\s*<\s*({_NUM})", t)
    if m:
        if posledni is None:
            raise ValueError("Relativní zadání potřebuje předchozí bod.")
        d, ang = f(m.group(1)), f(m.group(2)) * math.pi / 200.0
        if sjtsk:  # směrník: dY = d·sin σ, dX = d·cos σ; DXF x = −Y, y = −X
            return posledni[0] - d * math.sin(ang), posledni[1] - d * math.cos(ang)
        return posledni[0] + d * math.cos(ang), posledni[1] + d * math.sin(ang)
    m = re.fullmatch(rf"@\s*({_NUM})\s*[ ,]\s*({_NUM})", t)
    if m:
        if posledni is None:
            raise ValueError("Relativní zadání potřebuje předchozí bod.")
        return posledni[0] + f(m.group(1)), posledni[1] + f(m.group(2))
    m = re.fullmatch(rf"x\s*=\s*({_NUM})\s*[ ,]?\s*y\s*=\s*({_NUM})", t, re.IGNORECASE)
    if m:
        return f(m.group(1)), f(m.group(2))
    m = re.fullmatch(rf"({_NUM})\s*[ ,]\s*({_NUM})", t) or re.fullmatch(rf"({_NUM})\s+({_NUM})", t)
    if m:
        a, b = f(m.group(1)), f(m.group(2))
        if sjtsk and a > 0 and b > 0:
            return -a, -b  # S-JTSK Y X → DXF
        return a, b
    raise ValueError(f"„{text}“ – zadejte „Y X“, „@dx,dy“ nebo „@délka<směrník“.")
