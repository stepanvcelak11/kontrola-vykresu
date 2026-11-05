"""Styly čar MicroStationu ze souboru prostředků (.rsc – „Line Style Library“) a jejich vykreslení.

Formát není veřejně popsaný; struktura zjištěná ze školních knihoven (GEO.RSC, UGEO_VP.RSC):

* hlavička: na 0x4C ukazatel na adresář typů; adresář = záznamy po 24 B (typ obráceně „MNsl“ = lsNM,
  počet, ukazatel na rejstřík); rejstřík = záznamy po 32 B (?, id, ukazatel na data, velikost);
* data každého prostředku začínají popisem (char[128]);
* ``lsNM`` (jména): záhlaví 8 B, záznamy [7, typ, id, 20 B, délka, jméno\\0] – jméno stylu → složený styl;
* ``lsLS`` (složený styl): na +44 počet složek, složky po 56 B od +48: typ, id (typ 0 = plná čára);
* ``lsLC`` (kód čáry = čárkování): na +76 počet úseků, úseky po 48 B od +80: délka (double),
  na +44 režim (bit 0 = čárka, jinak mezera);
* ``lsLP`` (bodová složka): na +0x1C id kódu čáry (rozteč), na +0x24 počet symbolů, symboly po 88 B od +0x28:
  typ, id, úsek (u16), režim (u16: 1 začátek / 2 konec / 3 střed úseku, 4 začátek čáry, 8 konec čáry,
  0x10 vrcholy), posun x, y a úhel (double od +0x10);
* ``lsPS`` (symbol): rozsah a měřítko (UOR na jednotku na +0x58), na +0xC4 délka prvků v bajtech a od +0xC8
  prvky DGN V7 (úsečka, lomená čára, tvar, elipsa, oblouk; souřadnice v UOR).

Délky jsou v hlavních jednotkách výkresu (m) násobené měřítkem stylu.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path


class RscError(ValueError):
    pass


@dataclass
class Usek:
    delka: float
    carka: bool


@dataclass
class Symbol:
    useky: int  # číslo úseku kódu čáry
    rezim: int
    dx: float
    dy: float
    uhel: float  # stupně
    cary: list[list[tuple[float, float]]]  # geometrie v jednotkách stylu, počátek symbolu = (0, 0)


@dataclass
class Slozka:
    druh: str  # "plna" | "carky" | "body"
    useky: list[Usek] = field(default_factory=list)
    symboly: list[Symbol] = field(default_factory=list)


@dataclass
class StylCary:
    nazev: str
    popis: str
    slozky: list[Slozka]

    @property
    def kod(self) -> str:
        """Číslo značky na začátku jména („2.103 Pl. dřev.“ → „2.103“)."""
        m = re.match(r"^\s*(\d+(?:\.\d+)*)", self.nazev)
        return m.group(1) if m else self.nazev.strip()


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _i32v(d, o):
    """int32 v pořadí slov VAX (DGN V7)."""
    return struct.unpack_from("<i", bytes((d[o + 2], d[o + 3], d[o], d[o + 1])))[0]


def _vax(d, o):
    from .dgn_v7 import _vax as v
    return v(d, o)


def _txt(b: bytes) -> str:
    return b.split(b"\0")[0].decode("cp1250", "replace").strip()


def _prvky_symbolu(d: bytes, o: int, n: int, k: float) -> list[list[tuple[float, float]]]:
    """Prvky DGN V7 symbolu → lomené čáry (souřadnice × k)."""
    out = []
    end = o + n
    while o + 36 <= end:
        typ = d[o + 1] & 0x7F
        w = struct.unpack_from("<H", d, o + 2)[0]
        dl = (w + 2) * 2
        if dl < 4:
            break
        try:
            if typ == 3:
                out.append([(_i32v(d, o + 36) * k, _i32v(d, o + 40) * k), (_i32v(d, o + 44) * k, _i32v(d, o + 48) * k)])
            elif typ in (4, 6):
                c = struct.unpack_from("<H", d, o + 36)[0]
                out.append([(_i32v(d, o + 38 + 8 * j) * k, _i32v(d, o + 42 + 8 * j) * k) for j in range(c)])
            elif typ in (15, 16):
                if typ == 15:
                    a1, a2 = _vax(d, o + 36), _vax(d, o + 44)
                    rot = _i32v(d, o + 52) / 360000.0
                    cx, cy = _vax(d, o + 56), _vax(d, o + 64)
                    zac, rozs = 0.0, 360.0
                else:
                    zac = _i32v(d, o + 36) / 360000.0
                    sw = struct.unpack_from("<I", bytes((d[o + 42], d[o + 43], d[o + 40], d[o + 41])))[0]
                    rozs = (-(sw & 0x7FFFFFFF) if sw & 0x80000000 else sw) / 360000.0
                    a1, a2 = _vax(d, o + 44), _vax(d, o + 52)
                    rot = _i32v(d, o + 60) / 360000.0
                    cx, cy = _vax(d, o + 64), _vax(d, o + 72)
                r = math.radians(rot)
                pts = []
                m = max(8, int(abs(rozs) / 10))
                for j in range(m + 1):
                    t = math.radians(zac + rozs * j / m)
                    x, y = a1 * math.cos(t), a2 * math.sin(t)
                    pts.append(((cx + x * math.cos(r) - y * math.sin(r)) * k, (cy + x * math.sin(r) + y * math.cos(r)) * k))
                out.append(pts)
        except (struct.error, IndexError):
            pass
        o += dl
    return [p for p in out if len(p) >= 2]


def nacti_rsc(cesta: str | Path) -> dict[str, StylCary]:
    """Styly čar z knihovny .rsc: {jméno: StylCary}."""
    d = Path(cesta).read_bytes()
    if not d.startswith(b"Line Style Library") or len(d) < 0x60:
        raise RscError(f"{Path(cesta).name} není knihovna stylů čar MicroStationu (.rsc).")
    try:
        tr = _u32(d, 0x4C)
        o = tr + 4
        typy: dict[str, dict[int, tuple[int, int]]] = {}
        while o + 12 <= len(d):
            t = d[o:o + 4][::-1].decode("latin1")
            n, off = _u32(d, o + 4), _u32(d, o + 8)
            typy[t] = {_u32(d, off + 32 * j + 4): (_u32(d, off + 32 * j + 8), _u32(d, off + 32 * j + 12))
                       for j in range(n)}
            o += 24
    except struct.error as e:
        raise RscError(f"Knihovna stylů {Path(cesta).name} je poškozená ({e}).") from None

    def kod_cary(rid) -> list[Usek]:
        if rid not in typy.get("lsLC", {}):
            return []
        b = typy["lsLC"][rid][0] + 128
        n = _u32(d, b + 76)
        return [Usek(struct.unpack_from("<d", d, b + 80 + 48 * j)[0], bool(d[b + 80 + 48 * j + 44] & 1))
                for j in range(min(n, 64))]

    def symbol(rid):
        if rid not in typy.get("lsPS", {}):
            return []
        b = typy["lsPS"][rid][0] + 128
        uor = struct.unpack_from("<d", d, b + 0x58)[0] or 1000.0
        return _prvky_symbolu(d, b + 0xC8, _u32(d, b + 0xC4), 1.0 / uor)

    def slozka(typ, rid) -> Slozka | None:
        if typ in ("\0\0\0\0", ""):
            return Slozka("plna")
        if typ == "lsLC":
            u = kod_cary(rid)
            return Slozka("carky", u) if any(x.carka for x in u) and not all(x.carka for x in u) else Slozka("plna")
        if typ == "lsLP" and rid in typy.get("lsLP", {}):
            b = typy["lsLP"][rid][0] + 128
            base = kod_cary(_u32(d, b + 0x1C))
            n = _u32(d, b + 0x24)
            sy = []
            for j in range(min(n, 32)):
                s = b + 0x28 + 88 * j
                if d[s:s + 4][::-1] != b"lsPS":
                    continue
                stroke, rez = struct.unpack_from("<HH", d, s + 8)
                dx, dy, uh = struct.unpack_from("<3d", d, s + 0x10)
                if not all(math.isfinite(v) and abs(v) < 1e6 for v in (dx, dy, uh)):
                    dx = dy = uh = 0.0
                sy.append(Symbol(stroke, rez, dx, dy, uh, symbol(_u32(d, s + 4))))
            return Slozka("body", base, sy)
        return None

    def slozeny(typ, rid) -> list[Slozka]:
        if typ != "lsLS":
            s = slozka(typ, rid)
            return [s] if s else []
        b = typy["lsLS"][rid][0] + 128
        n = _u32(d, b + 44)
        out = []
        for j in range(min(n, 16)):
            c = b + 48 + 56 * j
            t = d[c:c + 4][::-1].decode("latin1")
            s = slozka(t, _u32(d, c + 4))
            if s is not None:
                out.append(s)
        return out

    styly: dict[str, StylCary] = {}
    for _rid, (off, sz) in typy.get("lsNM", {}).items():
        n = _u32(d, off + 4)
        o = off + 8
        for _j in range(n):
            if o + 36 > off + sz + 64:
                break
            t = d[o + 4:o + 8][::-1].decode("latin1")
            rid = _u32(d, o + 8)
            ln = _u32(d, o + 32)
            jm = _txt(d[o + 36:o + 36 + ln])
            o += 36 + ln
            if not jm:
                continue
            popis = _txt(d[typy[t][rid][0]:typy[t][rid][0] + 128]) if rid in typy.get(t, {}) else ""
            try:
                sl = slozeny(t, rid)
            except (struct.error, KeyError, IndexError):
                continue
            if sl:
                styly[jm] = StylCary(jm, popis, sl)
    if not styly:
        raise RscError(f"V {Path(cesta).name} nejsou žádné styly čar.")
    return styly


def najdi(styly: dict[str, StylCary], nazev: str) -> StylCary | None:
    """Styl podle jména z výkresu: přesně, bez ohledu na velikost písmen, nebo podle čísla značky („2.103“)."""
    if not nazev:
        return None
    if nazev in styly:
        return styly[nazev]
    low = nazev.strip().lower()
    for k, v in styly.items():
        if k.lower() == low:
            return v
    m = re.match(r"^\s*(\d+(?:\.\d+)+)", nazev)
    if m:
        for v in styly.values():
            if v.kod == m.group(1):
                return v
    return None


# ------------------------------------------------------------------ vykreslení stylu podél čáry
def _pozice(body, s):
    """Bod a směr (rad) ve vzdálenosti s po lomené čáře."""
    zbyva = s
    for (x0, y0), (x1, y1) in zip(body, body[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L <= 0:
            continue
        if zbyva <= L + 1e-12:
            t = zbyva / L
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t), math.atan2(y1 - y0, x1 - x0)
        zbyva -= L
    (x0, y0), (x1, y1) = body[-2], body[-1]
    return (x1, y1), math.atan2(y1 - y0, x1 - x0)


def _usek_cary(body, s0, s1):
    """Část lomené čáry mezi vzdálenostmi s0 a s1."""
    out = [_pozice(body, s0)[0]]
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(body, body[1:]):
        acc += math.hypot(x1 - x0, y1 - y0)
        if s0 < acc < s1:
            out.append((x1, y1))
    out.append(_pozice(body, s1)[0])
    return out


def vykresli(body: list[tuple[float, float]], styl: StylCary, meritko: float = 1.0,
             max_prvku: int = 20000) -> list[list[tuple[float, float]]]:
    """Lomené čáry, které nakreslí čáru ``body`` stylem (plná čára, čárky, symboly podél)."""
    body = [tuple(p[:2]) for p in body]
    body = [p for i, p in enumerate(body) if i == 0 or math.dist(p, body[i - 1]) > 1e-12]
    if len(body) < 2:
        return []
    L = sum(math.dist(a, b) for a, b in zip(body, body[1:]))
    m = meritko if meritko and meritko > 0 else 1.0
    out: list[list[tuple[float, float]]] = []
    for sl in styl.slozky:
        if sl.druh == "plna":
            out.append(list(body))
            continue
        delky = [u.delka * m for u in sl.useky]
        perioda = sum(delky)
        if sl.druh == "carky":
            if perioda <= 1e-9 or L / perioda > max_prvku:
                out.append(list(body))
                continue
            s = 0.0
            while s < L - 1e-12:
                for u, dl in zip(sl.useky, delky):
                    if s >= L:
                        break
                    if u.carka and dl > 0:
                        out.append(_usek_cary(body, s, min(L, s + dl)))
                    s += dl
            continue
        # body: symboly po úsecích kódu čáry, na začátku / konci čáry, ve vrcholech
        mista: list[tuple[Symbol, float]] = []
        for sy in sl.symboly:
            if sy.rezim & 0x04:
                mista.append((sy, 0.0))
            if sy.rezim & 0x08:
                mista.append((sy, L))
            if sy.rezim & 0x10:
                acc = 0.0
                for a, b in zip(body[:-1], body[1:-1] + [body[-1]]):
                    acc += math.dist(a, b)
                    if acc < L - 1e-9:
                        mista.append((sy, acc))
        if perioda > 1e-9 and L / perioda <= max_prvku:
            s = 0.0
            while s < L - 1e-9:
                zac = s
                for j, dl in enumerate(delky):
                    for sy in sl.symboly:
                        if sy.useky != j or not sy.rezim & 0x03:
                            continue
                        r = sy.rezim & 0x03
                        p = zac + (0 if r == 1 else dl if r == 2 else dl / 2)
                        if p <= L + 1e-9:
                            mista.append((sy, min(p, L)))
                    zac += dl
                s += perioda
        for sy, sp in mista[:max_prvku]:
            (px, py), smer = _pozice(body, sp)
            a = smer + math.radians(sy.uhel)
            c, s_ = math.cos(a), math.sin(a)
            ox, oy = sy.dx * m, sy.dy * m
            for cara in sy.cary:
                pts = []
                for x, y in cara:
                    x, y = x * m + ox, y * m + oy
                    pts.append((px + x * c - y * s_, py + x * s_ + y * c))
                out.append(pts)
    return out
