"""Převod atributové struktury výkresu na jiná pravidla (úloha „převod“: mapa plynovodu → mapa spojového
vedení podle Směrnice, jiné měřítko).

Značky ČSN 01 3411 jsou v obou předpisech stejné, liší se vrstvy, barvy, tloušťky a velikosti. Prvek se proto
přiřadí k druhu prvku cílových pravidel podle značky:

* buňka podle názvu (4.110 → pravidlo, které buňku 4.110 povoluje),
* čára podle vlastního stylu čáry (2.093 → pravidlo se stylem 2.093),
* ostatní (plné čáry, texty) podle zdrojové vrstvy – tu přiřadí uživatel (skupiny prvků se stejnou vrstvou,
  druhem a stylem); stejná vrstva pak dostane stejný druh prvku.

Nastaví se vrstva, barva, tloušťka, styl, měřítko stylu a buňky a u textů výška a písmo podle cílových pravidel.
Vše je jedna operace (jedno Zpět).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..rules import block_matches, split_alternatives

CARY = ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE")


def druh(e) -> str:
    t = e.dxftype()
    if t == "INSERT":
        return "buňka"
    if t in ("TEXT", "MTEXT"):
        return "text"
    if t == "POINT":
        return "bod"
    return "čára" if t in CARY else t.lower()


@dataclass
class Skupina:
    """Prvky, které se podle značky přiřadit nedají (stejná vrstva, druh a styl)."""
    vrstva: str
    druh: str
    styl: str
    prvky: list = field(default_factory=list)

    def popis(self) -> str:
        st = "" if self.styl in ("", "BYLAYER", "CONTINUOUS") else f", styl {self.styl}"
        return f"vrstva {self.vrstva}, {self.druh}{st} ({len(self.prvky)}×)"


@dataclass
class Navrh:
    prirazeni: list = field(default_factory=list)  # (entita, předvolba)
    skupiny: list = field(default_factory=list)  # Skupina – k ručnímu přiřazení


def _styl(e) -> str:
    return (e.dxf.get("linetype", "BYLAYER") or "BYLAYER").strip()


def _vlastni_styl(styl: str) -> bool:
    return styl.upper() not in ("BYLAYER", "BYBLOCK", "CONTINUOUS", "") and not styl.upper().startswith("DGN STYLE")


def predvolba_pro(e, pv) -> object | None:
    """Druh prvku cílových pravidel podle značky (název buňky, kód stylu čáry), jinak None."""
    d = druh(e)
    if d == "buňka":
        jm = e.dxf.name
        for p in pv:
            if p.blok and any(block_matches(v, jm) for v in split_alternatives(p.blok)):
                return p
        return None
    if d == "čára":
        st = _styl(e)
        if not _vlastni_styl(st):
            return None
        for p in pv:
            if p.geometrie != "text" and p.typ_cary and p.typ_cary.upper() == st.upper():
                return p
    return None


def navrhni(ents, pv, mapa: dict | None = None) -> Navrh:
    """Přiřazení prvků k předvolbám. ``mapa``: {(vrstva, druh, styl): předvolba} z ručního přiřazení."""
    n = Navrh()
    skup: dict = {}
    for e in ents:
        if e.dxftype() in ("VIEWPORT", "IMAGE", "HATCH", "DIMENSION"):
            continue
        p = predvolba_pro(e, pv)
        klic = (e.dxf.get("layer", "0"), druh(e), _styl(e) if druh(e) == "čára" else "")
        if p is None and mapa:
            p = mapa.get(klic)
        if p is not None:
            n.prirazeni.append((e, p))
            continue
        if klic not in skup:
            skup[klic] = Skupina(*klic)
        skup[klic].prvky.append(e)
    n.skupiny = sorted(skup.values(), key=lambda s: (-len(s.prvky), s.vrstva))
    return n


def _atributy(e, p, meritko: float) -> dict:
    a = {"layer": p.vrstva, "color": p.barva}
    d = druh(e)
    if d == "text":
        if p.textovy_styl:
            a["style"] = p.textovy_styl
        if p.vyska:
            a["height" if e.dxftype() == "TEXT" else "char_height"] = p.vyska
        elif meritko != 1.0:
            klic = "height" if e.dxftype() == "TEXT" else "char_height"
            a[klic] = e.dxf.get(klic, 1.0) * meritko
        if e.dxftype() == "TEXT" and abs(p.sirka_faktor - 1.0) > 1e-9:
            a["width"] = p.sirka_faktor
        return a
    if p.tloustka != -1:
        a["lineweight"] = p.tloustka
    if d == "buňka":
        m = p.meritko_bunky
        if m:
            sx = e.dxf.get("xscale", 1.0)
            a.update(xscale=m if sx >= 0 else -m, yscale=m, zscale=m)
        elif meritko != 1.0:
            a.update(xscale=e.dxf.get("xscale", 1.0) * meritko, yscale=e.dxf.get("yscale", 1.0) * meritko,
                     zscale=e.dxf.get("zscale", 1.0) * meritko)
        return a
    if p.typ_cary and p.typ_cary.upper() != "BYLAYER":
        a["linetype"] = p.typ_cary
    if p.meritko_stylu:
        a["ltscale"] = p.meritko_stylu
    elif meritko != 1.0 and _vlastni_styl(_styl(e)):
        a["ltscale"] = e.dxf.get("ltscale", 1.0) * meritko
    return a


def proved(doc, msp, h, navrh: Navrh, meritko: float = 1.0) -> tuple[list, list]:
    """Provede převod (jedna operace Zpět). ``meritko`` = poměr měřítek (1:1000 → 1:500 = 0,5) pro hodnoty,
    které cílová pravidla neurčují. Vrací (nové prvky, původní prvky)."""
    from . import upravy as U
    nove, puvodni = [], []
    for e, p in navrh.prirazeni:
        if p.vrstva not in doc.layers:
            doc.layers.add(p.vrstva)
        c = U._kopie(e)
        for k, v in _atributy(e, p, meritko).items():
            if k == "linetype" and v not in doc.linetypes and v.upper() not in ("BYLAYER", "BYBLOCK"):
                continue  # styl, který výkres nemá – ponechat původní
            c.dxf.set(k, v)
        msp.add_entity(c)
        nove.append(c)
        puvodni.append(e)
    if nove:
        h.proved("Převod atributů", nove, puvodni)
    return nove, puvodni


def souhrn(navrh: Navrh) -> dict:
    """Kolik prvků dostane který druh prvku (pro výpis)."""
    c: dict = defaultdict(int)
    for _e, p in navrh.prirazeni:
        c[p.nazev] += 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))
