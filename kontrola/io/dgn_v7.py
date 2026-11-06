"""Čtení DGN V7 (Intergraph ISFF) – starší formát MicroStationu (a formát, do kterého ukládá CAD).

Prvky: úsečka (3), lomená čára (4), tvar (6), složený řetězec / tvar (12 / 14), kružnice / elipsa (15),
oblouk (16), text (17), textový uzel (7, jeho texty), buňka (2, jako jeden prvek s názvem). Z hlaviček
prvků se čte hladina 1–63, barva 0–255, tloušťka wt a styl 0–7 – stejná čísla, jaká kontroluje Směrnice.

Dva výstupy: ``read_dgn_v7`` → ``Drawing`` pro Kontrolu (jako čtení V8), ``do_ezdxf`` → dokument ezdxf
pro CAD (buňky jako bloky, hladiny jako vrstvy „1“–„63“).
"""

from __future__ import annotations

import math
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Drawing, Feature, GeomType, LayerInfo

_RAD50 = " ABCDEFGHIJKLMNOPQRSTUVWXYZ$.?0123456789"
_JUST = {j: ({0: 0, 1: 0, 2: 1, 3: 2, 4: 2}[j // 3], {0: 3, 1: 2, 2: 1}[j % 3]) for j in range(15)}


# řídicí (negrafické) prvky: hlavička, nastavení, tabulky barev, referenční výkresy, data aplikací
_RIDICI = {1, 5, 8, 9, 10, 26, 66}


class DgnV7Error(Exception):
    pass


def _i32(b: bytes, o: int) -> int:
    return struct.unpack("<i", bytes((b[o + 2], b[o + 3], b[o], b[o + 1])))[0]


def _u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def _vax(b: bytes, o: int) -> float:
    """VAX D-float v pořadí DGN → IEEE (jako DGN2IEEEDouble v GDAL)."""
    s = b[o:o + 8]
    w = bytes((s[2], s[3], s[0], s[1], s[6], s[7], s[4], s[5]))
    hi, lo = struct.unpack("<II", w)
    sign = hi & 0x80000000
    exp = (hi >> 23) & 0xFF
    if exp == 0:
        return 0.0
    exp = exp - 129 + 1023
    lo2 = ((lo >> 3) & 0x1FFFFFFF) | ((hi << 29) & 0xFFFFFFFF)
    hi2 = ((hi >> 3) & 0x000FFFFF) | (exp << 20) | sign
    return struct.unpack("<d", struct.pack("<II", lo2, hi2))[0]


def rad50_text(b: bytes, o: int, slov: int = 2) -> str:
    out = ""
    for i in range(slov):
        v = _u16(b, o + 2 * i)
        out += _RAD50[(v // 1600) % 40] + _RAD50[(v // 40) % 40] + _RAD50[v % 40]
    return out.strip()


@dataclass
class Prvek:
    typ: int
    hladina: int
    barva: int
    tloustka: int
    styl: int
    geom: tuple  # ("cara", body, uzavrena) | ("elipsa", stred, a, b, rot°, start°, sweep°) | ("text", …) | ("bunka", …)
    deti: list = field(default_factory=list)


def _hlavicka(e: bytes) -> tuple[int, int, int, int, int]:
    sym = _u16(e, 34) if len(e) >= 36 else 0
    return e[1] & 0x7F, e[0] & 0x3F, (sym >> 8) & 0xFF, (sym >> 3) & 0x1F, sym & 0x7


def _tcb(d: bytes) -> tuple[float, bool, tuple[float, float]]:
    sub_m = _i32(d, 1112) or 1
    uor_s = _i32(d, 1116) or 1
    trojrozmerny = bool(d[1214] & 0x40)
    ox, oy = _vax(d, 1240), _vax(d, 1248)
    return float(sub_m * uor_s), trojrozmerny, (ox, oy)


def nacti_prvky(path: str | Path) -> tuple[list[Prvek], Counter]:
    d = Path(path).read_bytes()
    if len(d) < 1536 or d[1] & 0x7F != 9:
        raise DgnV7Error("Soubor není DGN V7.")
    uor, d3, (ox, oy) = _tcb(d)
    if d3:
        raise DgnV7Error("3D výkres DGN V7 zatím neumím – uložte ho z MicroStationu jako DXF nebo V8.")
    k = 1.0 / uor

    def bod(e, o):
        return (_i32(e, o) - ox) * k, (_i32(e, o + 4) - oy) * k

    prvky: list[Prvek] = []
    neznamy: Counter = Counter()
    zasobnik: list[tuple[Prvek, int]] = []  # rozpracované složené prvky (prvek, zbývající bajty)
    off = 0
    while off + 4 <= len(d):
        if d[off:off + 2] == b"\xff\xff":
            break
        n = 4 + 2 * _u16(d, off + 2)
        e = d[off:off + n]
        off += n
        if len(e) < 36 or e[1] & 0x80:  # smazaný prvek
            _odecti(zasobnik, n)
            continue
        typ, lv, barva, wt, st = _hlavicka(e)
        p = Prvek(typ, lv, barva, wt, st, ())
        try:
            if typ == 3:
                p.geom = ("cara", [bod(e, 36), bod(e, 44)], False)
            elif typ in (4, 6, 11):
                cnt = _u16(e, 36)
                p.geom = ("cara", [bod(e, 38 + 8 * i) for i in range(cnt)], typ == 6)
            elif typ == 15:
                a, b = _vax(e, 36) * k, _vax(e, 44) * k
                rot = _i32(e, 52) / 360000.0
                p.geom = ("elipsa", ((_vax(e, 56) - ox) * k, (_vax(e, 64) - oy) * k), a, b, rot, 0.0, 360.0)
            elif typ == 16:
                start = _i32(e, 36) / 360000.0
                sw = struct.unpack("<I", bytes((e[42], e[43], e[40], e[41])))[0]
                sweep = -(sw & 0x7FFFFFFF) / 360000.0 if sw & 0x80000000 else sw / 360000.0
                sweep = sweep or 360.0
                a, b = _vax(e, 44) * k, _vax(e, 52) * k
                rot = _i32(e, 60) / 360000.0
                p.geom = ("elipsa", ((_vax(e, 64) - ox) * k, (_vax(e, 72) - oy) * k), a, b, rot, start, sweep)
            elif typ == 17:
                font, just = e[36], e[37]
                sirka = _i32(e, 38) * 6 / 1000 * k
                vyska = _i32(e, 42) * 6 / 1000 * k
                rot = _i32(e, 46) / 360000.0
                x, y = bod(e, 50)
                nch = e[58]
                text = e[60:60 + nch].decode("cp1250", errors="replace")
                p.geom = ("text", x, y, text, vyska, sirka, rot, just, font)
            elif typ == 2:
                nazev = rad50_text(e, 38)
                c = [_i32(e, 68 + 4 * i) / 2 ** 31 for i in range(4)]
                x, y = bod(e, 84)
                rot = math.degrees(math.atan2(c[2], c[0])) if (c[0] or c[2]) else 0.0
                p.geom = ("bunka", nazev, x, y, rot)
            elif typ in (12, 14, 7):
                p.geom = ("slozeny", typ == 14)
            else:
                if typ not in _RIDICI:
                    neznamy[typ] += 1
                _odecti(zasobnik, n)
                continue
        except (struct.error, IndexError):
            neznamy[typ] += 1
            _odecti(zasobnik, n)
            continue
        rodic = zasobnik[-1][0] if zasobnik and (e[0] & 0x80) else None
        _odecti(zasobnik, n)
        (rodic.deti if rodic is not None else prvky).append(p)
        if typ in (2, 12, 14, 7):
            zbyva = (_u16(e, 36) + 19) * 2 - n  # celková délka složeného prvku minus hlavička
            if zbyva > 0:
                zasobnik.append((p, zbyva))
    return prvky, neznamy


def _odecti(zasobnik: list, n: int) -> None:
    """Odečte délku prvku od všech rozpracovaných složených prvků; dokončené vyjme."""
    for i in range(len(zasobnik)):
        zasobnik[i] = (zasobnik[i][0], zasobnik[i][1] - n)
    while zasobnik and zasobnik[-1][1] <= 0:
        zasobnik.pop()


def _body_elipsy(g, krok: int = 72):
    (cx, cy), a, b, rot, start, sweep = g[1:]
    n = max(8, int(abs(sweep) / 360 * krok))
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for i in range(n + 1):
        u = math.radians(start + sweep * i / n)
        px, py = a * math.cos(u), b * math.sin(u)
        out.append((cx + c * px - s * py, cy + s * px + c * py))
    return out


def _cara_slozeneho(p: Prvek) -> list:
    pts = []
    for x in p.deti:
        if x.geom and x.geom[0] == "cara":
            q = x.geom[1]
        elif x.geom and x.geom[0] == "elipsa":
            q = _body_elipsy(x.geom)
        else:
            continue
        if pts and q and math.dist(pts[-1], q[0]) < 1e-9:
            q = q[1:]
        pts += q
    return pts


# ------------------------------------------------------------------ pro Kontrolu
def read_dgn_v7(path: str | Path, progress=None) -> Drawing:
    from shapely.geometry import LineString, Point, Polygon

    from ..rules import MICROSTATION_COLORS
    path = Path(path)
    prvky, neznamy = nacti_prvky(path)
    d = Drawing(path=str(path), source_path=str(path))
    fid = 0

    def add(p: Prvek, geom, gtype, dxftype, **kw):
        nonlocal fid
        layer = f"Vrstva {p.hladina}"
        f = Feature(fid=fid, dxftype=dxftype, geom_type=gtype, geometry=geom, layer=layer, color_aci=None,
                    color_rgb=MICROSTATION_COLORS.get(p.barva, (200, 200, 200)), linetype=str(p.styl),
                    handle=f"DGN{fid}", attributes={"ZDROJ": "DGN", "MS_STYL": str(p.styl),
                                                    "MS_BARVA": str(p.barva), "MS_TLOUSTKA": str(p.tloustka)},
                    vertices=[tuple(c[:2]) for c in (geom.exterior.coords if gtype == GeomType.POLYGON
                                                     else geom.coords)], **kw)
        d.features.append(f)
        info = d.layers.setdefault(layer, LayerInfo(name=layer, color_aci=None))
        info.count += 1
        fid += 1
        return f

    def jeden(p: Prvek):
        g = p.geom
        if not g:
            return
        if g[0] == "cara":
            pts = g[1]
            if len(pts) == 2 and math.dist(*pts) < 1e-9:
                add(p, Point(*pts[0]), GeomType.BOD, "LINE").zero_length = True
            elif g[2] and len(pts) >= 4:
                add(p, Polygon(pts), GeomType.POLYGON, "LWPOLYLINE", closed=True)
            elif len(pts) >= 2:
                add(p, LineString(pts), GeomType.LINIE, "LINE" if p.typ == 3 else "LWPOLYLINE")
        elif g[0] == "elipsa":
            pts = _body_elipsy(g)
            if abs(abs(g[6]) - 360) < 1e-9:
                add(p, Polygon(pts), GeomType.POLYGON, "ELLIPSE", closed=True, radius=g[2])
            else:
                add(p, LineString(pts), GeomType.LINIE, "ARC", radius=g[2])
        elif g[0] == "text":
            _t, x, y, text, h, w, rot, just, font = g
            ha, va = _JUST.get(just, (0, 1))
            delka = w * max(1, len(text))
            fx, fy = {0: 0.0, 1: 0.5, 2: 1.0}[ha], {0: 0.0, 1: 0.0, 2: 0.5, 3: 1.0}[va]
            c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            px, py = x + delka * fx * c - h * fy * s, y + delka * fx * s + h * fy * c
            add(p, Point(px, py), GeomType.TEXT, "TEXT", text=text, text_height=h,
                width_factor=(w / h) if h else 1.0, rotation=rot % 360, halign=ha, valign=va, font=f"font č. {font}")
        elif g[0] == "slozeny":
            if p.typ == 7:
                for x in p.deti:
                    jeden(x)
                return
            pts = _cara_slozeneho(p)
            if g[1] and len(pts) >= 4:
                add(p, Polygon(pts), GeomType.POLYGON, "LWPOLYLINE", closed=True)
            elif len(pts) >= 2:
                add(p, LineString(pts), GeomType.LINIE, "LWPOLYLINE")
        elif g[0] == "bunka":
            hl = p.hladina or next((x.hladina for x in p.deti if x.hladina), 0)
            q = Prvek(p.typ, hl, p.barva, p.tloustka, p.styl, p.geom)
            add(q, Point(g[2], g[3]), GeomType.BOD, "INSERT", block_name=g[1] or "buňka", rotation=g[4])

    for p in prvky:
        jeden(p)
    d.warnings.append(f"Výkres přečten přímo z DGN V7 ({len(d.features)} prvků).")
    if neznamy:
        d.warnings.append("Nepřečtené prvky: " + ", ".join(f"typ {k}: {v}×" for k, v in sorted(neznamy.items())))
    return d


# ------------------------------------------------------------------ pro CAD
def do_ezdxf(path: str | Path, rs=None):
    """DGN V7 → dokument ezdxf (R2018). Vrací (doc, ms_barvy {handle: barva MicroStationu}, poznámky)."""
    import ezdxf

    from ..cad import symbologie as SY
    prvky, neznamy = nacti_prvky(path)
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 6
    SY.zajisti_styly(doc)
    msp = doc.modelspace()
    ms_barvy: dict[str, int] = {}

    def attr(p: Prvek, text: bool = False) -> dict:
        ly = str(p.hladina or 1)
        if ly not in doc.layers:
            doc.layers.add(ly)
        try:
            aci = SY.ms_na_aci(p.barva, rs)
        except ValueError:
            aci = 7
        a = {"layer": ly, "color": aci}
        if not text:
            lw, _odhad = SY.wt_na_lw(p.tloustka, rs)
            a["lineweight"] = lw
            a["linetype"] = SY.styl_na_typ(p.styl)
        return a

    def kresli(p: Prvek, cil, posun=(0.0, 0.0)):
        g = p.geom
        dx, dy = posun
        nove = []
        if not g:
            return nove
        if g[0] == "cara":
            pts = [(x - dx, y - dy) for x, y in g[1]]
            if len(pts) == 2 and not g[2]:
                if math.dist(*pts) < 1e-9:
                    nove.append(cil.add_point(pts[0], dxfattribs=attr(p)))
                else:
                    nove.append(cil.add_line(pts[0], pts[1], dxfattribs=attr(p)))
            elif len(pts) >= 2:
                if g[2] and math.dist(pts[0], pts[-1]) < 1e-9:
                    pts = pts[:-1]
                nove.append(cil.add_lwpolyline(pts, close=g[2], dxfattribs=attr(p)))
        elif g[0] == "elipsa":
            (cx, cy), a, b, rot, start, sweep = g[1:]
            c = (cx - dx, cy - dy)
            if abs(a - b) < 1e-9 * max(1, a):
                if abs(abs(sweep) - 360) < 1e-9:
                    nove.append(cil.add_circle(c, a, dxfattribs=attr(p)))
                else:
                    a0, a1 = (start + rot, start + rot + sweep) if sweep > 0 else (start + rot + sweep, start + rot)
                    nove.append(cil.add_arc(c, a, a0, a1, dxfattribs=attr(p)))
            else:
                osa = (a * math.cos(math.radians(rot)), a * math.sin(math.radians(rot)))
                u0, u1 = math.radians(start), math.radians(start + sweep)
                if sweep < 0:
                    u0, u1 = u1, u0
                nove.append(cil.add_ellipse(c, osa, b / a if a else 1.0, u0 if abs(sweep) < 360 else 0,
                                            u1 if abs(sweep) < 360 else 2 * math.pi, dxfattribs=attr(p)))
        elif g[0] == "text":
            _t, x, y, text, h, w, rot, just, _font = g
            t = cil.add_text(text, height=h, rotation=rot, dxfattribs={**attr(p, True),
                                                                       "width": (w / h) if h else 1.0})
            t.set_placement((x - dx, y - dy))
            nove.append(t)
        elif g[0] == "slozeny":
            if p.typ == 7:
                for x in p.deti:
                    nove += kresli(x, cil, posun)
            else:
                pts = [(x - dx, y - dy) for x, y in _cara_slozeneho(p)]
                if len(pts) >= 2:
                    nove.append(cil.add_lwpolyline(pts, close=g[1], dxfattribs=attr(p)))
        elif g[0] == "bunka":
            nazev = _blok(p)
            ins = cil.add_blockref(nazev, (g[2] - dx, g[3] - dy),
                                   dxfattribs={**attr(Prvek(2, p.hladina or _hl(p), p.barva, p.tloustka, p.styl, ())),
                                               "rotation": 0.0})
            nove.append(ins)
        for e in nove:
            ms_barvy[e.dxf.handle] = p.barva
        return nove

    bloky: dict[str, str] = {}

    def _hl(p: Prvek) -> int:
        return next((x.hladina for x in p.deti if x.hladina), 1)

    def _blok(p: Prvek) -> str:
        g = p.geom
        zaklad = g[1] or "BUNKA"
        nazev, i = zaklad, 1
        while nazev in doc.blocks and bloky.get(nazev) != _otisk(p):
            i += 1
            nazev = f"{zaklad}_{i}"
        if nazev not in doc.blocks:
            blk = doc.blocks.new(nazev)
            for x in p.deti:
                kresli(x, blk, (g[2], g[3]))
            bloky[nazev] = _otisk(p)
        return nazev

    def _otisk(p: Prvek) -> str:
        g = p.geom
        return repr([(x.typ, x.geom[0] if x.geom else None,
                      [tuple(round(c - o, 4) for c, o in zip(b, (g[2], g[3]))) for b in x.geom[1]]
                      if x.geom and x.geom[0] == "cara" else None) for x in p.deti])

    for p in prvky:
        kresli(p, msp)
    pozn = [f"Nepřečtené prvky DGN: typ {k}: {v}×" for k, v in sorted(neznamy.items())]
    return doc, ms_barvy, pozn
