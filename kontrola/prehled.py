"""Přehled výkresu: co je na které vrstvě (počty, barvy, styly, tloušťky, písmo) – pro neznámý výkres."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .model import Drawing, Feature, GeomType


@dataclass
class VrstvaPrehled:
    nazev: str
    body: int = 0
    linie: int = 0
    plochy: int = 0
    texty: int = 0
    bunky: int = 0
    delka: float = 0.0
    plocha: float = 0.0
    barvy: Counter = field(default_factory=Counter)
    styly: Counter = field(default_factory=Counter)
    tloustky: Counter = field(default_factory=Counter)
    pisma: Counter = field(default_factory=Counter)
    vysky: Counter = field(default_factory=Counter)
    rgb: Counter = field(default_factory=Counter)

    @property
    def celkem(self) -> int:
        return self.body + self.linie + self.plochy + self.texty + self.bunky

    @property
    def jednotna(self) -> bool:
        """Mají všechny prvky vrstvy stejnou barvu, styl a tloušťku?"""
        return len(self.barvy) <= 1 and len(self.styly) <= 1 and len(self.tloustky) <= 1


def _barva(f: Feature) -> str:
    ms = f.attributes.get("MS_BARVA")
    if ms not in (None, ""):
        return f"MS {ms}"
    if f.color_aci is not None:
        return f"ACI {f.color_aci}"
    return "#%02X%02X%02X" % tuple(f.color_rgb)


def _styl(f: Feature) -> str:
    return f.attributes.get("MS_STYL") or f.linetype or "CONTINUOUS"


def _tloustka(f: Feature) -> str:
    ms = f.attributes.get("MS_TLOUSTKA")
    if ms not in (None, ""):
        return f"MS {ms}"
    return f"{f.lineweight:g} mm" if f.lineweight > 0 else "výchozí"


def souradnicovy_system(d: Drawing) -> str:
    b = d.bounds()
    if b is None:
        return "prázdný výkres"
    x0, y0, x1, y1 = b
    if -905000 <= x0 and x1 <= -430000 and -1230000 <= y0 and y1 <= -935000:
        return "S-JTSK (záporné souřadnice, jako MicroStation)"
    if 430000 <= x0 and x1 <= 905000 and 935000 <= y0 and y1 <= 1230000:
        return "S-JTSK (kladné souřadnice Y, X)"
    if -180 <= x0 and x1 <= 180 and -90 <= y0 and y1 <= 90:
        return "zeměpisné souřadnice (stupně) nebo místní malá soustava"
    return "místní / neznámá soustava"


def prehled(d: Drawing) -> list[VrstvaPrehled]:
    out: dict[str, VrstvaPrehled] = {}
    for f in d.features:
        v = out.get(f.layer)
        if v is None:
            v = out[f.layer] = VrstvaPrehled(f.layer)
        g = f.geometry
        if f.dxftype == "INSERT":
            v.bunky += 1
        elif f.geom_type == GeomType.TEXT:
            v.texty += 1
            if f.font:
                v.pisma[f.font] += 1
            if f.text_height > 0:
                v.vysky[round(f.text_height, 3)] += 1
            v.barvy[_barva(f)] += 1
            v.rgb[tuple(f.color_rgb)] += 1
            continue
        elif f.geom_type == GeomType.BOD or f.zero_length:
            v.body += 1
        elif f.geom_type == GeomType.POLYGON:
            v.plochy += 1
            if g is not None and not g.is_empty:
                v.plocha += g.area
                v.delka += g.length
        else:
            v.linie += 1
            if g is not None and not g.is_empty:
                v.delka += g.length
        v.barvy[_barva(f)] += 1
        v.rgb[tuple(f.color_rgb)] += 1
        if f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
            v.styly[_styl(f)] += 1
            v.tloustky[_tloustka(f)] += 1
    return sorted(out.values(), key=lambda v: (-v.celkem, v.nazev))


def popis_counter(c: Counter, n: int = 3) -> str:
    if not c:
        return ""
    items = c.most_common(n)
    txt = ", ".join(f"{k} ({v})" if len(c) > 1 else str(k) for k, v in items)
    return txt + (f" +{len(c) - n}" if len(c) > n else "")
