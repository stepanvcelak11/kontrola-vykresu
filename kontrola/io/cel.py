"""Knihovna buněk MicroStationu (.CEL, formát V8) – načtení buněk jako bloků do CADu.

Knihovna V8 je soubor OLE jako výkres DGN, každá buňka je jeden model: ``Dgn-Md/#00000n/Dgn~Mh``
obsahuje název modelu (= název buňky, např. „1.030“), ``Dgn-Md/#00000n/Dgn^G/$1`` jeho prvky
v souřadnicích vůči počátku buňky (UOR). Prvky čte stejný kód jako výkresy DGN (úsečky, lomené čáry,
tvary, kružnice, oblouky, složené řetězce, texty), vyplnění tvarů je připojené datum 0x0041.

Buňky z norem mají jednu barvu (barvu určí hladina / aktivní barva při vložení), proto se kresba
bloku ukládá s barvou a tloušťkou „dle bloku“ – vložená buňka pak má barvu a tloušťku jako vkládací
prvek, stejně jako bodová buňka v MicroStationu.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .dgn_v8 import _JUST, DgnError, _geometry, _inflate, _marked, _MARK, _streams, _uor


@dataclass
class Bunka:
    nazev: str
    prvky: list = field(default_factory=list)  # ("cara", body, uzavrena, vypln) | ("kruh", x, y, r, vypln) | ("text", …)

    def rozsah(self) -> tuple[float, float, float, float] | None:
        xs, ys = [], []
        for p in self.prvky:
            if p[0] == "cara":
                xs += [b[0] for b in p[1]]
                ys += [b[1] for b in p[1]]
            elif p[0] == "kruh":
                xs += [p[1] - p[3], p[1] + p[3]]
                ys += [p[2] - p[3], p[2] + p[3]]
            elif p[0] == "text":
                xs.append(p[1])
                ys.append(p[2])
        return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _vyplneny(e: bytes) -> bool:
    attr, = struct.unpack_from("<I", e, 12)
    o = 4 + attr * 2
    while o + 4 <= len(e):
        hdr, lid = struct.unpack_from("<HH", e, o)
        ln = ((hdr & 0xFF) + 1) * 2
        if ln <= 4:
            break
        if lid == 0x0041:
            return True
        o += ln
    return False


def _prvky(data: bytes, s: float) -> list:
    out: list = []
    off, n = 0, len(data)
    retez = None  # [body, uzavřený, vyplněný, zbývá částí]
    while off + 16 <= n:
        t = data[off + 4]
        size, = struct.unpack_from("<I", data, off + 8)
        if size == 0:
            break
        e = data[off:off + 4 + size * 2]
        off += 4 + size * 2
        if len(e) < 108:
            continue
        try:
            geo = _geometry(t, e, s)
        except (struct.error, ValueError):
            continue
        if retez is not None:
            if geo is not None and geo[0] in ("line", "arc"):  # další část složeného řetězce / tvaru
                pts = list(geo[1])
                if retez[0] and math.dist(retez[0][-1], pts[0]) < 1e-9:
                    pts = pts[1:]
                retez[0].extend(pts)
                retez[3] -= 1
                if retez[3] <= 0:
                    if len(retez[0]) >= 2:
                        out.append(("cara", retez[0], retez[1], retez[2]))
                    retez = None
                continue
            if len(retez[0]) >= 2:
                out.append(("cara", retez[0], retez[1], retez[2]))
            retez = None
        if geo is None:
            continue
        if t in (12, 14):
            retez = [[], t == 14, _vyplneny(e), struct.unpack_from("<I", e, 108)[0]]
            if retez[3] == 0:
                retez = None
            continue
        if geo[0] == "line":
            pts = geo[1]
            if t == 3 and math.dist(pts[0], pts[1]) < 1e-9:
                out.append(("kruh", pts[0][0], pts[0][1], 0.0, False))  # bod (úsečka nulové délky)
            else:
                out.append(("cara", pts, t == 6, t == 6 and _vyplneny(e)))
        elif geo[0] == "arc":
            pts, closed, a = geo[1], geo[2], geo[3]
            if t == 15 and closed:
                cx = sum(p[0] for p in pts[:-1]) / (len(pts) - 1)
                cy = sum(p[1] for p in pts[:-1]) / (len(pts) - 1)
                if all(abs(math.dist((cx, cy), p) - a) < 1e-6 * max(1.0, a) for p in pts):
                    out.append(("kruh", cx, cy, a, _vyplneny(e)))
                    continue
            out.append(("cara", pts, closed, closed and _vyplneny(e)))
        elif geo[0] == "text":
            x, y, text, h, wf, rot, just = geo[1:]
            if text:
                out.append(("text", x, y, text, h, wf, rot, just))
    if retez is not None and len(retez[0]) >= 2:
        out.append(("cara", retez[0], retez[1], retez[2]))
    return out


def nacti_cel(cesta: str | Path) -> list[Bunka]:
    """Buňky knihovny .CEL (V8) v pořadí jako v knihovně."""
    import olefile
    cesta = Path(cesta)
    if not olefile.isOleFile(str(cesta)):
        raise DgnError(f"{cesta.name} není knihovna buněk V8 (starší knihovnu V7 uložte v MicroStationu jako V8).")
    ole = olefile.OleFileIO(str(cesta))
    try:
        s = 1.0 / _uor(ole)
        modely = sorted({n[1] for n in ole.listdir() if len(n) > 2 and n[0] == "Dgn-Md" and n[1].startswith("#")},
                        key=lambda m: int(m[1:], 16))
        out = []
        for m in modely:
            if m == "#000000":
                continue  # výchozí model knihovny, ne buňka
            try:
                h = _inflate(ole.openstream(f"Dgn-Md/{m}/Dgn~Mh").read())
            except OSError:
                continue
            nazev = next((_marked(h, x.start())[0] for x in _MARK.finditer(h)), "") or m.lstrip("#")
            data = b"".join(_inflate(ole.openstream(p).read()) for p in _streams(ole, f"Dgn-Md/{m}/Dgn^G/"))
            prvky = _prvky(data, s)
            if prvky:
                out.append(Bunka(nazev=nazev.strip(), prvky=prvky))
        return out
    finally:
        ole.close()


def _platny_nazev(nazev: str) -> str:
    return re.sub(r'[<>/\\":;?*|=`]', "_", nazev) or "BUNKA"


def do_dokumentu(doc, bunky: list[Bunka], prepsat: bool = False) -> list[str]:
    """Bloky z buněk knihovny (kresba „dle bloku“). Vrátí názvy přidaných bloků; existující bloky se
    nepřepisují, pokud ``prepsat`` není True."""
    out = []
    for b in bunky:
        jmeno = _platny_nazev(b.nazev)
        if jmeno in doc.blocks:
            if not prepsat:
                continue
            doc.blocks.delete_block(jmeno, safe=False)
        blk = doc.blocks.new(jmeno)
        attr = {"layer": "0", "color": 0, "lineweight": -2, "linetype": "CONTINUOUS"}  # barva a tloušťka dle bloku
        for p in b.prvky:
            if p[0] == "cara":
                body, uzavrena, vypln = p[1], p[2], p[3]
                if uzavrena and len(body) > 2 and math.dist(body[0], body[-1]) < 1e-9:
                    body = body[:-1]
                blk.add_lwpolyline(body, close=uzavrena, dxfattribs=attr)
                if vypln and uzavrena and len(body) >= 3:
                    h = blk.add_hatch(color=0, dxfattribs={"layer": "0"})
                    h.paths.add_polyline_path(body, is_closed=True)
            elif p[0] == "kruh":
                _k, x, y, r, vypln = p
                if r <= 0:
                    blk.add_point((x, y), dxfattribs=attr)
                    continue
                blk.add_circle((x, y), r, dxfattribs=attr)
                if vypln:
                    h = blk.add_hatch(color=0, dxfattribs={"layer": "0"})
                    ep = h.paths.add_edge_path()
                    ep.add_arc((x, y), r, 0, 360)
            elif p[0] == "text":
                _k, x, y, text, vyska, wf, rot, just = p
                ha, va = _JUST.get(just, (0, 0))
                t = blk.add_text(text, dxfattribs={**attr, "height": vyska, "rotation": rot,
                                                   "width": wf or 1.0, "insert": (x, y)})
                if (ha, va) != (0, 0):
                    t.dxf.halign, t.dxf.valign, t.dxf.align_point = ha, va, (x, y)
        out.append(jmeno)
    return out
