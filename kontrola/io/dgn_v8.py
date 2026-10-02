"""Vlastní čtení výkresu MicroStation DGN V8 (V8i, CONNECT) – bez převodu na DXF (experimentální).

DGN V8 je soubor OLE (Structured Storage). Prvky modelu jsou v proudech ``Dgn-Md/#000000/Dgn^G/$n``
komprimovaných zlib (16 B hlavička + data). Každý prvek::

    +0  u32   0
    +4  u8    typ (3 úsečka, 4 lomená čára, 6 tvar, 2 buňka, 12/14 složený řetězec/tvar,
              15 elipsa, 16 oblouk, 17 text, 22 řetězec bodů …)
    +6  u8    příznaky (0x40 = součást buňky / složeného prvku)
    +8  u32   délka prvku ve 2B slovech (celkem 4 + 2·délka bajtů)
    +12 u32   začátek připojených dat (slova)
    +16 u32   ID vrstvy
    +48 i32   styl čáry (0–7, jinak vlastní styl)
    +52 u32   tloušťka (0–31)
    +56 u32   barva (0–255, index tabulky color.tbl)
    +108 …    geometrie v jednotkách UOR (souřadnice / UOR = metry); 2D = x,y, 3D = x,y,z

Názvy vrstev jsou v ``Dgn^Nm``: záznam ``?? 10 d2 56 01 00 00 00 | délka | ff fe 01 00 | název`` (nebo
``ff fe`` + UTF-16), ID vrstvy je u32 208 B před touto hlavičkou. Texty a názvy buněk mají stejnou hlavičku.

Ověřeno na výkresech obou zadání proti DXF exportu z MicroStationu (souřadnice na 1 mm, vrstvy).
Vlastní styly čar: v ``Dgn^Nm`` je záporné ID stylu (i32) a za ním název v UTF-16 („5.303“).
Písmo: číslo fontu je u textu na +108; TrueType fonty (od 1024) mají název v ``Dgn^Nm``, fonty
MicroStationu (RSC) jen číslo (1 = cs_Working). Řez (tučné, kurzíva) se nečte. Nečtou se B-spline a tělesa. To aplikace přizná v poznámce ke kontrole.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from collections import Counter
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

from ..model import Drawing, Feature, GeomType, LayerInfo
from ..rules import MICROSTATION_COLORS

_MARK = re.compile(rb"[\x00-\xff]\x10\xd2\x56\x01\x00\x00\x00", re.DOTALL)  # hlavička řetězce v DGN
_JUST = {j: ({0: 0, 1: 0, 2: 1, 3: 2, 4: 2}[j // 3], {0: 3, 1: 2, 2: 1}[j % 3]) for j in range(15)}


class DgnError(Exception):
    pass


def _inflate(raw: bytes, broken: list | None = None) -> bytes:
    i = raw.find(b"\x78\x5e")
    if i < 0:
        i = raw.find(b"\x78\x9c")
    if i < 0:
        return b""  # prázdný proud (jen 16B hlavička)
    z = zlib.decompressobj()
    try:
        out = z.decompress(raw[i:])
    except zlib.error:
        if broken is not None:
            broken.append(1)
        return b""
    if broken is not None and not z.eof:
        broken.append(1)  # proud skončil dřív – soubor je useknutý / poškozený
    return out


def _streams(ole, prefix: str) -> list[str]:
    names = ["/".join(e) for e in ole.listdir()]
    sel = [n for n in names if n.startswith(prefix)]
    return sorted(sel, key=lambda n: int(re.sub(r"\D", "", n.rsplit("$", 1)[-1]) or 0))


def _decode(body: bytes) -> str:
    if body.startswith(b"\xff\xfe\x01\x00"):
        return body[4:].split(b"\0")[0].decode("cp1250", "replace")
    if body.startswith(b"\xff\xfe"):
        return body[2:].decode("utf-16-le", "ignore").split("\0")[0]
    return body.split(b"\0")[0].decode("cp1250", "replace")


def _marked(d: bytes, i: int) -> tuple[str, int]:
    """Řetězec za hlavičkou na pozici i: (text, konec)."""
    ln, = struct.unpack_from("<I", d, i + 8)
    return _decode(d[i + 12:i + 12 + ln]), i + 12 + ln


def _levels(ole) -> dict[int, str]:
    out: dict[int, str] = {}
    for n in _streams(ole, "Dgn^Nm/"):
        d = _inflate(ole.openstream(n).read())
        for m in _MARK.finditer(d):
            try:
                name, end = _marked(d, m.start())
            except struct.error:
                continue
            if not name or m.start() < 208:
                continue
            # ID vrstvy je 208 B před názvem (záznam vrstvy končí jejím názvem)
            lid, = struct.unpack_from("<I", d, m.start() - 208)
            tail = d[end:end + 160]
            if 0 < lid < 1_000_000 and tail.find(b"\xff\xff\xff\xff\x06\x00") >= 0:
                out.setdefault(lid, name)
    return out


_STYLE = re.compile(rb"([\x00-\xff][\x00-\xff]\xff\xff)((?:[\x20-\x7e]\x00){1,40})\x00\x00", re.DOTALL)


def _styles(ole) -> dict[int, str]:
    """Názvy vlastních stylů čar: záporné ID stylu (i32) a hned za ním název v UTF-16 („5.303“)."""
    out: dict[int, str] = {}
    for n in _streams(ole, "Dgn^Nm/"):
        d = _inflate(ole.openstream(n).read())
        for m in _STYLE.finditer(d):
            sid, = struct.unpack("<i", m.group(1))
            name = m.group(2).decode("utf-16-le")
            if not -1_000_000 < sid < 0:
                continue
            pred = d[m.start() - 8:m.start()]
            # záznam stylu: 4 nulové bajty (+ název s číslem kódu), nebo „00000000 02000000“ (i názvy
            # bez čísla – „VCHOD“); jiné výskyty jsou náhodné shody v binárních datech
            if pred == b"\0\0\0\0\x02\0\0\0" or (pred[4:] == b"\0\0\0\0" and re.search(r"\d", name)):
                out.setdefault(sid, name.strip())
    return out


# fonty MicroStationu (RSC) nejsou v DGN pojmenované – čísla podle českého pracovního prostředí (protokol GISoft)
RSC_FONTS = {1: "cs_Working", 159: "cs_Nimbus Sans C I"}
_FONT = re.compile(rb"([\x00-\xff][\x04-\x07]\x00\x00)([\x02-\x7e])\x00((?:[\x20-\x7e]\x00){1,40})", re.DOTALL)


def _fonts(ole) -> dict[int, str]:
    """TrueType fonty výkresu: číslo (od 1024) a název v UTF-16 z tabulky ``Dgn^Nm``."""
    out: dict[int, str] = dict(RSC_FONTS)
    for n in _streams(ole, "Dgn^Nm/"):
        d = _inflate(ole.openstream(n).read())
        for m in _FONT.finditer(d):
            fid, = struct.unpack("<I", m.group(1))
            name = m.group(3).decode("utf-16-le")
            if m.group(2)[0] == len(name) * 2 and d[m.start() - 8:m.start() - 1].count(0) >= 6:
                out.setdefault(fid, name)
    return out


def _uor(ole) -> float:
    try:
        d = _inflate(ole.openstream("Dgn-Md/#000000/Dgn~Mh").read())
        v = struct.unpack_from("<d", d, 4324)[0]
        if 0.5 <= v <= 1e7:
            return v
    except (OSError, struct.error):
        pass
    return 1000.0


def _string(e: bytes, start: int, end: int) -> str:
    s = e[start:end]
    m = _MARK.search(s)
    if m:  # řetězec s hlavičkou
        return _marked(s, m.start())[0]
    if s[:2] == b"\0\0":
        s = s[2:]
    if s.startswith(b"\xff\xfe\x01\x00"):
        s = s[4:]
    elif s.startswith(b"\xff\xfe"):
        return s[2:].decode("utf-16-le", "ignore").split("\0")[0]
    out = []
    for b in s:
        if b < 0x20:
            break
        out.append(b)
    return bytes(out).decode("cp1250", "replace")


def _cell_name(e: bytes) -> str | None:
    m = _MARK.search(e)
    return _marked(e, m.start())[0] if m else None


def _quat_xy(w, x, y, z):
    """Horní 2×2 část rotační matice z kvaternionu (w, x, y, z) – průmět do půdorysu (i zrcadlení).

    DGN ukládá kvaternion inverzní rotace, proto je matice transponovaná (ověřeno na obloucích
    v nakloněné rovině: koncové body sedí s DXF exportem MicroStationu na 0,0 mm)."""
    return (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * y - w * z), 1 - 2 * (x * x + z * z))


def _style_scale(e: bytes) -> float:
    """Měřítko stylu čáry z připojených dat (linkage 0x79F9 „modifikátory stylu“, bit 0 = měřítko)."""
    attr, = struct.unpack_from("<I", e, 12)
    o = 4 + attr * 2
    while o + 4 <= len(e):
        hdr, lid = struct.unpack_from("<HH", e, o)
        ln = ((hdr & 0xFF) + 1) * 2
        if ln <= 4:
            break
        if lid == 0x79F9 and o + 16 <= len(e):
            flags, = struct.unpack_from("<I", e, o + 4)
            if flags & 1:
                v, = struct.unpack_from("<d", e, o + 8)
                if 0 < v < 1e6:
                    return v
        o += ln
    return 1.0


def _angle_from_quat(w, x, y, z) -> float:
    r00, _, r10, _ = _quat_xy(w, x, y, z)
    return math.atan2(r10, r00)


def read_dgn(path: str | Path, progress=None) -> Drawing:
    import olefile
    path = Path(path)
    if not olefile.isOleFile(str(path)):
        raise DgnError("Soubor není DGN V8 (MicroStation V8i / CONNECT).")
    ole = olefile.OleFileIO(str(path))
    try:
        levels = _levels(ole)
        styles = _styles(ole)
        fonts = _fonts(ole)
        uor = _uor(ole)
        broken: list = []
        data = b"".join(_inflate(ole.openstream(n).read(), broken)
                        for n in _streams(ole, "Dgn-Md/#000000/Dgn^G/"))
    finally:
        ole.close()
    d = Drawing(path=str(path), source_path=str(path))
    if broken:
        d.warnings.append(f"{path.name} je nejspíš poškozený nebo neúplně uložený – přečetla se jen část kresby. "
                          "Uložte výkres v MicroStationu znovu.")
    skipped: Counter = Counter()
    fid = 0
    s = 1.0 / uor

    def lname(lid: int) -> str:
        return levels.get(lid) or f"Vrstva {lid}"

    def add(geom, gtype, dxftype, e, **kw):
        nonlocal fid
        lid, = struct.unpack_from("<I", e, 16)
        style, = struct.unpack_from("<i", e, 48)
        weight, color = struct.unpack_from("<II", e, 52)
        layer = lname(lid)
        bylevel = set()
        if color == 0xFFFFFFFF:
            bylevel.add("barva")
        if weight == 0xFFFFFFFF:
            bylevel.add("tloušťka")
        if style == 0x7FFFFFFF:
            bylevel.add("styl")
        rgb = MICROSTATION_COLORS.get(color, (200, 200, 200))
        lt = str(style) if 0 <= style <= 7 else ("0" if "styl" in bylevel else styles.get(style, "VLASTNI_STYL"))
        attrs = {"ZDROJ": "DGN", "MS_STYL": str(style)}
        if "barva" not in bylevel:
            attrs["MS_BARVA"] = str(color)
        if "tloušťka" not in bylevel:
            attrs["MS_TLOUSTKA"] = str(weight)
        if geom.geom_type == "Point":
            verts = [(geom.x, geom.y)]
        elif geom.geom_type == "Polygon":
            verts = [tuple(c[:2]) for c in geom.exterior.coords]
        else:
            verts = [tuple(c[:2]) for c in geom.coords]
        f = Feature(fid=fid, dxftype=dxftype, geom_type=gtype, geometry=geom, layer=layer, color_aci=None,
                    color_rgb=rgb, linetype=lt, lineweight=0.0, handle=f"DGN{fid}", vertices=verts,
                    ltscale=_style_scale(e) if style < 0 else 1.0,
                    attributes=attrs, bylayer=frozenset(bylevel), **kw)
        d.features.append(f)
        info = d.layers.setdefault(layer, LayerInfo(name=layer, color_aci=None, color_rgb=rgb))
        info.count += 1
        fid += 1
        return f

    off, n = 0, len(data)
    chain: list | None = None  # rozpracovaný složený řetězec/tvar: [hlavička, body]
    cell: tuple | None = None  # (hlavička, název, x, y, natočení)
    cell_pts: list = []

    def close_chain():
        nonlocal chain
        if chain and len(chain[1]) >= 2:
            e, pts, closed = chain
            if closed and len(pts) >= 4:
                add(Polygon(pts), GeomType.POLYGON, "LWPOLYLINE", e, closed=True)
            else:
                add(LineString(pts), GeomType.LINIE, "LWPOLYLINE", e)
        chain = None

    def close_cell():
        nonlocal cell, cell_pts
        if cell is not None:
            e, name, x, y, rot, meritko = cell
            if cell_pts and struct.unpack_from("<I", e, 16)[0] == 0:
                e = e[:16] + cell_pts[0][16:20] + e[20:48] + cell_pts[0][48:60] + e[60:]
            add(Point(x, y), GeomType.BOD, "INSERT", e, block_name=name or "buňka", rotation=rot, scale=meritko)
        cell, cell_pts = None, []

    pending = 0  # kolik následujících prvků ještě patří do buňky / složeného prvku (počet z hlavičky)
    while off + 16 <= n:
        t = data[off + 4]
        size, = struct.unpack_from("<I", data, off + 8)
        if size == 0:
            break
        e = data[off:off + 4 + size * 2]
        off += 4 + size * 2
        if len(e) < 108:
            continue
        comp = pending > 0
        if comp:
            pending -= 1
            if t in (2, 12, 14, 7):  # vnořená buňka / řetězec: jeho části patří také do vnější buňky
                pending += struct.unpack_from("<I", e, 108)[0]
        else:
            close_chain()
            close_cell()
        try:
            geo = _geometry(t, e, s)
        except (struct.error, ValueError):
            skipped[t] += 1
            continue
        if t in (12, 14) and not comp:
            pending = struct.unpack_from("<I", e, 108)[0]
            chain = [e, [], t == 14]
            continue
        if t == 2 and not comp:
            pending = struct.unpack_from("<I", e, 108)[0]
            name = _cell_name(e[180:]) if len(e) > 180 else None
            x, y, rot, sx, sy = _cell_origin(e, s)
            cell = (e, name, x, y, rot, (sx, sy))
            continue
        if comp and chain is not None and geo is not None and geo[0] in ("line", "arc"):
            pts = geo[1]
            if chain[1] and math.dist(chain[1][-1], pts[0]) < 1e-9:
                pts = pts[1:]
            chain[1].extend(pts)
            continue
        if comp and cell is not None:
            if not cell_pts and struct.unpack_from("<I", e, 16)[0]:  # vrstva buňky = vrstva jejích částí
                cell_pts.append(e)
            continue  # kresba uvnitř buňky – buňka je jeden prvek (značka)
        if geo is None:
            skipped[t] += 1
            continue
        kind = geo[0]
        if kind == "line":
            pts = geo[1]
            if t == 3 and math.dist(pts[0], pts[1]) < 1e-9:
                f = add(Point(*pts[0]), GeomType.BOD, "LINE", e)
                f.zero_length = True
            elif t == 6 and len(pts) >= 4:
                add(Polygon(pts), GeomType.POLYGON, "LWPOLYLINE", e, closed=True)
            else:
                add(LineString(pts), GeomType.LINIE, "LINE" if t == 3 else "LWPOLYLINE", e)
        elif kind == "arc":
            pts, closed = geo[1], geo[2]
            if closed:
                add(Polygon(pts), GeomType.POLYGON, "ELLIPSE", e, closed=True, radius=geo[3])
            else:
                add(LineString(pts), GeomType.LINIE, "ARC", e, radius=geo[3])
        elif kind == "text":
            x, y, text, h, wf, rot, just = geo[1:]
            ha, va = _JUST.get(just, (0, 0))
            font_id, = struct.unpack_from("<I", e, 108)
            add(Point(x, y), GeomType.TEXT, "TEXT", e, text=text, text_height=h, width_factor=wf, rotation=rot,
                halign=ha, valign=va, font=fonts.get(font_id, f"font č. {font_id}"))
        elif kind == "points":
            for p in geo[1]:
                add(Point(*p), GeomType.BOD, "POINT", e)
        if progress and fid % 2000 == 0:
            progress(min(95, 100 * off // max(1, n)), "Čtu DGN…")
    close_chain()
    close_cell()
    d.warnings.append(f"Výkres přečten přímo z DGN ({len(d.features)} prvků) – experimentálně. Řez písma (tučné, "
                      "kurzíva) se z DGN nečte a nekontroluje.")
    if skipped:
        d.warnings.append("Nepřečtené prvky: " + ", ".join(f"typ {k}: {v}×" for k, v in sorted(skipped.items())))
    return d


def _is3d(e: bytes, n2: int, n3: int) -> bool | None:
    if len(e) == n3:
        return True
    if len(e) == n2:
        return False
    return None


def _geometry(t: int, e: bytes, s: float):
    attr, = struct.unpack_from("<I", e, 12)
    end = min(len(e), 4 + attr * 2)  # za geometrií mohou být připojená data (linkage)
    if t == 3:
        dim = 3 if end >= 156 else 2
        c = struct.unpack_from(f"<{2 * dim}d", e, 108)
        return ("line", [(c[0] * s, c[1] * s), (c[dim] * s, c[dim + 1] * s)])
    if t in (4, 6, 22):
        cnt, = struct.unpack_from("<I", e, 108)
        if cnt == 0 or cnt > 100000:
            return None
        body = end - 116
        dim = 3 if body >= cnt * 24 else 2
        c = struct.unpack_from(f"<{cnt * dim}d", e, 116)
        pts = [(c[i] * s, c[i + 1] * s) for i in range(0, cnt * dim, dim)]
        return ("points", pts) if t == 22 else ("line", pts)
    if t in (15, 16):
        three = _is3d(e[:end], 148 if t == 15 else 164, 180 if t == 15 else 196)
        if three is None:
            return None
        o = 108
        if t == 16:
            start, sweep = struct.unpack_from("<2d", e, o)
            o += 16
        else:
            start, sweep = 0.0, 2 * math.pi
        a, b = struct.unpack_from("<2d", e, o)
        o += 16
        if three:
            w, x, y, z = struct.unpack_from("<4d", e, o)
            m = _quat_xy(w, x, y, z)
            o += 32
            cx, cy = struct.unpack_from("<2d", e, o)
        else:
            rot, = struct.unpack_from("<d", e, o)
            m = (math.cos(rot), -math.sin(rot), math.sin(rot), math.cos(rot))
            cx, cy = struct.unpack_from("<2d", e, o + 8)
        a, b, cx, cy = a * s, b * s, cx * s, cy * s
        k = max(8, int(abs(sweep) / (2 * math.pi) * 72))
        pts = []
        for i in range(k + 1):
            u = start + sweep * i / k
            px, py = a * math.cos(u), b * math.sin(u)
            pts.append((cx + m[0] * px + m[1] * py, cy + m[2] * px + m[3] * py))
        closed = t == 15 or abs(abs(sweep) - 2 * math.pi) < 1e-9
        return ("arc", pts, closed, a)
    if t == 17:
        just, nchar = struct.unpack_from("<HH", e, 112)  # zarovnání a počet znaků
        lng, hgt = struct.unpack_from("<2d", e, 116)
        tl, th = struct.unpack_from("<2d", e, 132)  # délka a výška textu (UOR)
        k = 6.0 / 1000.0 * s  # násobitel výšky textu (jako ve V7: UOR · 6 / 1000)
        h = hgt * k
        wf = (lng / hgt) if hgt else 1.0
        # 2D: natočení (1 double) + počátek (2), 3D: kvaternion (4) + počátek (3)
        if end - 148 >= 56:
            w, x, y, z = struct.unpack_from("<4d", e, 148)
            if abs(w * w + x * x + y * y + z * z - 1.0) < 1e-6:
                ox, oy = struct.unpack_from("<2d", e, 180)
                text = _string(e, 204, end)
                rot = _angle_from_quat(w, x, y, z)
                px, py = _just_point(ox * s, oy * s, tl * s, th * s, rot, just)
                return ("text", px, py, text, h, wf, math.degrees(rot) % 360, just)
        rot, = struct.unpack_from("<d", e, 148)
        ox, oy = struct.unpack_from("<2d", e, 156)
        text = _string(e, 174, min(end, 176 + nchar) if nchar else end)
        px, py = _just_point(ox * s, oy * s, tl * s, th * s, rot, just)
        return ("text", px, py, text, h, wf, math.degrees(rot) % 360, just)
    if t in (2, 12, 14):
        return ("header",)
    return None


def _just_point(x: float, y: float, length: float, height: float, rot: float, just: int) -> tuple[float, float]:
    """DGN ukládá levý dolní roh textu; kontrola (jako DXF) pracuje s bodem zarovnání."""
    fx = {0: 0.0, 1: 0.0, 2: 0.5, 3: 1.0, 4: 1.0}.get(just // 3, 0.0)  # vlevo, vlevo okraj, střed, vpravo…
    fy = {0: 1.0, 1: 0.5, 2: 0.0}.get(just % 3, 0.0)  # nahoře, uprostřed, dole
    dx, dy = length * fx, height * fy
    return x + dx * math.cos(rot) - dy * math.sin(rot), y + dx * math.sin(rot) + dy * math.cos(rot)


def _cell_origin(e: bytes, s: float) -> tuple[float, float, float, float, float]:
    """Počátek, natočení a měřítko buňky z její matice (x, y, úhel [°], měřítko x, měřítko y)."""
    # 2D buňka: matice 2×2 na +148, počátek na +180; 3D: matice 3×3 na +164, počátek na +236
    attr, = struct.unpack_from("<I", e, 12)
    try:
        if 4 + attr * 2 >= 260:
            m = struct.unpack_from("<9d", e, 164)
            m00, m01, m10, m11 = m[0], m[1], m[3], m[4]
            x, y = struct.unpack_from("<2d", e, 236)
        else:
            m00, m01, m10, m11 = struct.unpack_from("<4d", e, 148)
            x, y = struct.unpack_from("<2d", e, 180)
    except struct.error:
        return 0.0, 0.0, 0.0, 1.0, 1.0
    sx, sy = math.hypot(m00, m01), math.hypot(m10, m11)
    sx = round(sx, 9) if 1e-9 < sx < 1e6 else 1.0
    sy = round(sy, 9) if 1e-9 < sy < 1e6 else 1.0
    return x * s, y * s, math.degrees(math.atan2(-m01, m00)) % 360, sx, sy