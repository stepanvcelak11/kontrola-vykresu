"""Export výkresu CAD (ezdxf) do DGN V7 pro MicroStation – hladiny, barvy, tloušťky a styly v číslech
MicroStationu (jako je předepisuje Směrnice), buňky jako buňky.

Převody jsou stejné jako v CAD (``cad.symbologie``): barva DXF → nejbližší barva tabulky MicroStationu
(u prvků nakreslených s předvolbou ze zadání přesné číslo), lineweight → wt podle převodní tabulky
zadání, typ čáry „DGN Style n“ → styl n. Hladina = číslo z názvu („5“, „Vrstva 5“, „LV05“); hladiny
bez čísla dostanou volná čísla 1–63 (vypíše se jejich přehled).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..io import dgn_v7_zapis as D
from ..rules import RuleSet, layer_number
from . import symbologie as SY


@dataclass
class Souhrn:
    prvky: Counter = field(default_factory=Counter)
    preskoceno: Counter = field(default_factory=Counter)
    hladiny: dict[str, int] = field(default_factory=dict)  # název hladiny bez čísla → přidělené číslo
    vlastni_styly: Counter = field(default_factory=Counter)  # vlastní styly čar (do V7 jako styl 0)
    poznamky: list[str] = field(default_factory=list)

    def text(self) -> str:
        t = "DGN: " + ", ".join(f"{n}× {k}" for k, n in self.prvky.most_common())
        if self.hladiny:
            t += ". Hladiny bez čísla → " + ", ".join(f"{k} = {v}" for k, v in sorted(self.hladiny.items(),
                                                                                    key=lambda kv: kv[1]))
            t += (" – DGN V7 názvy hladin neumí, v MicroStationu budou jen čísla. Výkres s pojmenovanými hladinami "
                  "(Účelová mapa, Pasport) proto ukládejte jako DXF: MicroStation ho otevře i s názvy hladin")
        if self.vlastni_styly:
            t += (". Vlastní styly čar (" + ", ".join(sorted(self.vlastni_styly)) + ") DGN V7 neumí – uloženy "
                  "stylem 0, v MicroStationu je přiřaďte (nebo uložte DXF)")
        if self.preskoceno:
            t += ". Vynecháno: " + ", ".join(f"{n}× {k}" for k, n in self.preskoceno.items())
        return t + "."


_NAZVY = {3: "úsečka", 4: "lomená čára", 6: "tvar", 15: "kružnice/elipsa", 16: "oblouk", 17: "text", 2: "buňka"}


class _Export:
    def __init__(self, doc, rs: RuleSet | None, ms_barvy: dict | None):
        self.doc, self.rs = doc, rs
        self.ms_barvy = dict(ms_barvy or {})
        self.s = Souhrn()
        self.tab = SY.tabulka(rs)
        obsazene = {layer_number(ly.dxf.name) for ly in doc.layers}
        self._volne = [n for n in range(1, 64) if n not in obsazene]

    # ------------------------------------------------------------ symbologie
    def hladina(self, nazev: str) -> int:
        n = layer_number(nazev or "0")
        if n is not None and 1 <= n <= 63:
            return n
        if nazev in self.s.hladiny:
            return self.s.hladiny[nazev]
        n = self._volne.pop(0) if self._volne else 63
        self.s.hladiny[nazev] = n
        return n

    def _vrstva(self, e, rodic):
        ly = e.dxf.get("layer", "0")
        if ly == "0" and rodic is not None:
            ly = rodic.dxf.get("layer", "0")
        return ly

    def _barva(self, e, rodic, vrstva: str) -> int:
        h = e.dxf.get("handle")
        if h in self.ms_barvy:
            return int(self.ms_barvy[h])
        aci = e.dxf.get("color", 256)
        if aci == 0 and rodic is not None:  # dle bloku
            return self._barva(rodic, None, vrstva)
        tc = e.dxf.get("true_color")
        if tc is not None and aci not in (0, 256):
            rgb = ((tc >> 16) & 255, (tc >> 8) & 255, tc & 255)
            return min(self.tab, key=lambda k: (sum((a - b) ** 2 for a, b in zip(self.tab[k], rgb)), k))
        if aci == 256:
            if vrstva in self.doc.layers:
                ly = self.doc.layers.get(vrstva)
                aci = abs(ly.dxf.get("color", 7))
                if ly.dxf.hasattr("true_color"):
                    tc = ly.dxf.true_color
                    rgb = ((tc >> 16) & 255, (tc >> 8) & 255, tc & 255)
                    return min(self.tab, key=lambda k: (sum((a - b) ** 2 for a, b in zip(self.tab[k], rgb)), k))
            else:
                aci = 7
        # ACI je víceznačná (víc barev MicroStationu má stejnou ACI) – rozhodne barva ze zadání pro hladinu
        c = self._barva_ze_zadani(e, rodic, vrstva, aci)
        if c is not None:
            return c
        m = SY.aci_na_ms(aci, self.rs)
        return 0 if m is None else int(m)

    def _barva_ze_zadani(self, e, rodic, vrstva: str, aci: int) -> int | None:
        """ACI je víceznačná (MicroStation ji volí z několika barev) – rozhodne pravidlo zadání pro hladinu:
        barva, ze které tahle ACI vzniknout mohla (stejně jako ji ověřuje Kontrola), nejlépe pravidla se
        stejnou buňkou, stylem čáry a druhem prvku (text / čára)."""
        if self.rs is None or not self.rs.pravidla:
            return None
        from ..model import GeomType
        from ..rules import block_matches, linetype_matches, rgb_to_aci
        blok = (e if e.dxftype() == "INSERT" else rodic if rodic is not None and rodic.dxftype() == "INSERT"
                else None)
        jmeno = blok.dxf.name if blok is not None else None
        je_text = e.dxftype() in ("TEXT", "MTEXT", "ATTRIB")
        styl = SY.typ_na_styl(e.dxf.get("linetype", "BYLAYER"))
        nej, skore = None, None
        for r in self.rs.pravidla:
            if not (r.hladina and r.matches_layer(vrstva)) or r.barva is None:
                continue
            for c in str(r.barva).split("|"):
                c = c.strip()
                if not c.isdigit() or int(c) not in self.tab:
                    continue
                if aci not in rgb_to_aci(tuple(self.tab[int(c)])):
                    continue
                sk = 0
                if jmeno and r.blok and block_matches(r.blok, jmeno):
                    sk += 4
                if (r.geometrie == GeomType.TEXT) == je_text:
                    sk += 2
                if r.styl_cary and styl not in ("dle hladiny", "") and linetype_matches(r.styl_cary, styl):
                    sk += 1
                if skore is None or sk > skore:
                    nej, skore = int(c), sk
        return nej

    def _barvy_hladiny(self, vrstva: str, blok: str | None = None) -> list[int]:
        from ..rules import block_matches
        cache = self.__dict__.setdefault("_bh", {})
        if (vrstva, blok) not in cache:
            out = []
            pravidla = list(self.rs.pravidla if self.rs is not None else [])
            if blok:  # pravidla pro tuto buňku napřed
                pravidla.sort(key=lambda r: not (r.blok and block_matches(r.blok, blok)))
            for r in pravidla:
                if r.hladina and r.matches_layer(vrstva):
                    for c in str(r.barva).split("|") if r.barva is not None else []:
                        if c.strip().isdigit() and int(c) not in out:
                            out.append(int(c))
            cache[(vrstva, blok)] = out
        return cache[(vrstva, blok)]

    def _tloustka(self, e, rodic, vrstva: str) -> int:
        lw = e.dxf.get("lineweight", -1)
        if lw == -2 and rodic is not None:
            return self._tloustka(rodic, None, vrstva)
        if lw is None or lw < 0:
            lw = self.doc.layers.get(vrstva).dxf.get("lineweight", -3) if vrstva in self.doc.layers else -3
        wt = SY.lw_na_wt(lw, self.rs) if lw is not None and lw >= 0 else 0
        return max(0, min(31, int(wt or 0)))

    def _styl(self, e, rodic, vrstva: str) -> int:
        typ = e.dxf.get("linetype", "BYLAYER")
        if typ.upper() == "BYBLOCK" and rodic is not None:
            return self._styl(rodic, None, vrstva)
        if typ.upper() == "BYLAYER":
            typ = self.doc.layers.get(vrstva).dxf.get("linetype", "CONTINUOUS") if vrstva in self.doc.layers \
                else "CONTINUOUS"
        s = SY.typ_na_styl(typ)
        if s.isdigit() and 0 <= int(s) <= 7:
            return int(s)
        if typ.upper() not in ("BYBLOCK", "CONTINUOUS"):
            self.s.vlastni_styly[typ] += 1
        return 0

    def sym(self, e, rodic=None) -> D.Symbologie:
        v = self._vrstva(e, rodic)
        return D.Symbologie(self.hladina(v), self._barva(e, rodic, v), self._tloustka(e, rodic, v),
                            self._styl(e, rodic, v))

    # ------------------------------------------------------------ prvky
    def prvky(self, e, rodic=None) -> list[D.Prvek]:
        t = e.dxftype()
        try:
            return self._prvky(e, t, rodic)
        except (D.ChybaDgn, ValueError, ZeroDivisionError, AttributeError, TypeError) as ex:
            self.s.preskoceno[t] += 1
            if len(self.s.poznamky) < 10:
                self.s.poznamky.append(f"{t}: {ex}")
            return []

    def _prvky(self, e, t: str, rodic) -> list[D.Prvek]:
        sym = lambda: self.sym(e, rodic)  # noqa: E731
        if t == "LINE":
            a, b = e.dxf.start, e.dxf.end
            return [D.usecka((a.x, a.y), (b.x, b.y), sym())]
        if t == "POINT":
            p = e.dxf.location
            return [D.usecka((p.x, p.y), (p.x, p.y), sym())]  # bod MicroStationu = úsečka nulové délky
        if t == "LWPOLYLINE":
            if any(abs(p[0]) > 1e-12 for p in e.get_points("b")):
                return self._cesta(e, sym(), e.closed)
            return D.lomena([tuple(p) for p in e.get_points("xy")], sym(), e.closed)
        if t == "POLYLINE":
            if e.is_2d_polyline or e.is_3d_polyline:
                if e.is_2d_polyline and any(abs(v.dxf.get("bulge", 0)) > 1e-12 for v in e.vertices):
                    return self._cesta(e, sym(), e.is_closed)
                return D.lomena([(v.dxf.location.x, v.dxf.location.y) for v in e.vertices], sym(), e.is_closed)
            return self._rozlozit(e, rodic)
        if t == "CIRCLE":
            c = e.dxf.center
            return [D.elipsa((c.x, c.y), e.dxf.radius, e.dxf.radius, 0.0, sym())]
        if t == "ARC":
            c = e.dxf.center
            a0, a1 = e.dxf.start_angle, e.dxf.end_angle
            return [D.oblouk((c.x, c.y), e.dxf.radius, a0, (a1 - a0) % 360 or 360, sym())]
        if t == "ELLIPSE":
            c, mj = e.dxf.center, e.dxf.major_axis
            a = math.hypot(mj.x, mj.y)
            if abs((e.dxf.end_param - e.dxf.start_param) % (2 * math.pi)) < 1e-9:
                return [D.elipsa((c.x, c.y), a, a * e.dxf.ratio, math.degrees(math.atan2(mj.y, mj.x)), sym())]
            return self._cesta(e, sym(), False)
        if t in ("SPLINE",):
            return self._cesta(e, sym(), bool(e.closed))
        if t == "TEXT":
            return [self._text(e, e.dxf.text, sym())]
        if t == "MTEXT":
            return self._mtext(e, sym())
        if t == "ATTRIB":
            return [] if e.is_invisible else [self._text(e, e.dxf.text, sym())]
        if t in ("SOLID", "TRACE", "3DFACE"):
            body = [(v.x, v.y) for v in e.wcs_vertices()] if hasattr(e, "wcs_vertices") else []
            if len(body) == 4 and t in ("SOLID", "TRACE"):
                body = [body[0], body[1], body[3], body[2]]
            return D.lomena(body, sym(), True)
        if t == "HATCH":
            out = []
            from ezdxf import path as P
            for cesta in P.from_hatch(e):
                pts = [(v.x, v.y) for v in cesta.flattening(0.005)]
                if len(pts) >= 3:
                    out += D.lomena(pts, sym(), True)
            return out
        if t == "INSERT":
            return self._bunka(e, rodic)
        if t in ("DIMENSION", "LEADER", "MLEADER", "MULTILEADER", "ARC_DIMENSION", "RADIAL_DIMENSION"):
            return self._rozlozit(e, rodic)
        self.s.preskoceno[t] += 1
        return []

    def _cesta(self, e, sym: D.Symbologie, uzavrena: bool) -> list[D.Prvek]:
        from ezdxf import path as P
        pts = [(v.x, v.y) for v in P.make_path(e).flattening(0.005)]
        return D.lomena(pts, sym, uzavrena)

    def _rozlozit(self, e, rodic) -> list[D.Prvek]:
        out = []
        for x in e.virtual_entities():
            out += self.prvky(x, rodic if rodic is not None else e)
        return out

    def _text(self, e, retezec: str, sym: D.Symbologie) -> D.Prvek:
        h = float(e.dxf.get("height", 1.0) or 1.0)
        w = h * float(e.dxf.get("width", 1.0) or 1.0)
        rot = float(e.dxf.get("rotation", 0.0) or 0.0)
        ha, va = int(e.dxf.get("halign", 0) or 0), int(e.dxf.get("valign", 0) or 0)
        if ha > 2:  # ALIGNED / MIDDLE / FIT – bere se jako na střed
            ha, va = 1, (2 if ha == 4 else va)
        p = e.dxf.align_point if (ha or va) and e.dxf.hasattr("align_point") else e.dxf.insert
        # DGN ukládá levý dolní roh textu; zarovnání se zapíše pro další úpravy v MicroStationu
        delka = w * max(1, len(retezec))
        dx = {0: 0.0, 1: -delka / 2, 2: -delka}[ha]
        dy = {0: 0.0, 1: 0.0, 2: -h / 2, 3: -h}[va]
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        x, y = p.x + dx * c - dy * s, p.y + dx * s + dy * c
        return D.text((x, y), retezec, h, sym, rot, font=self._font(e), just=D.zarovnani(ha, va), sirka=w)

    def _font(self, e) -> int:
        import re
        st = e.dxf.get("style", "")
        m = re.search(r"(\d+)\s*$", st or "")
        return int(m.group(1)) if m and int(m.group(1)) < 256 else 1

    def _mtext(self, e, sym: D.Symbologie) -> list[D.Prvek]:
        h = float(e.dxf.get("char_height", 1.0) or 1.0)
        rot = math.degrees(math.atan2(e.dxf.text_direction.y, e.dxf.text_direction.x)) \
            if e.dxf.hasattr("text_direction") else float(e.dxf.get("rotation", 0.0) or 0.0)
        radky = [r for r in e.plain_text().split("\n")]
        ap = int(e.dxf.get("attachment_point", 1) or 1)
        ha = (ap - 1) % 3
        mezera = h * 1.66 * float(e.dxf.get("line_spacing_factor", 1.0) or 1.0)
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        p = e.dxf.insert
        out = []
        celkem = mezera * (len(radky) - 1) + h
        y0 = {0: -h, 1: -h + celkem / 2 - h / 2, 2: -h + celkem - h}[(ap - 1) // 3]
        for i, r in enumerate(radky):
            if not r.strip():
                continue
            delka = h * len(r)
            dx = {0: 0.0, 1: -delka / 2, 2: -delka}[ha]
            dy = y0 - i * mezera
            out.append(D.text((p.x + dx * c - dy * s, p.y + dx * s + dy * c), r, h, sym, rot, just=2))
        return out

    def _bunka(self, e, rodic) -> list[D.Prvek]:
        deti = []
        for x in e.virtual_entities():
            deti += self.prvky(x, e)
        for a in e.attribs:
            if not a.is_invisible:
                deti.append(self._text(a, a.dxf.text, self.sym(a, e)))
        if not deti:
            return []
        p = e.dxf.insert
        return [D.bunka(e.dxf.name, (p.x, p.y), float(e.dxf.get("rotation", 0.0) or 0.0), deti, self.sym(e, rodic))]


def exportuj(doc, prostor, cesta: str | Path, rs: RuleSet | None = None, ms_barvy: dict | None = None,
             seed: str | Path | None = None) -> Souhrn:
    """Uloží model (nebo jiný prostor) výkresu do DGN V7. Vrátí souhrn (co se zapsalo a co ne)."""
    ex = _Export(doc, rs, ms_barvy)
    prvky = []
    for e in prostor:
        nove = ex.prvky(e)
        for p in nove:
            ex.s.prvky[_NAZVY.get(p.typ, str(p.typ))] += 1
        prvky += nove
    if not prvky:
        raise ValueError("Ve výkresu není nic, co by šlo uložit do DGN.")
    D.zapis(prvky, cesta, seed)
    return ex.s
