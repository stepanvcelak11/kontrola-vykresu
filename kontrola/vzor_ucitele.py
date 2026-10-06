"""Porovnání výkresu studenta s hotovým výkresem učitele (stejné zaměření, kreslené zvlášť).

Na rozdíl od porovnání verzí (stejný soubor, shoda na milimetr) se tu kresba páruje s tolerancí:

* čáry podle **pokrytí** – úsek učitelovy čáry, který ve vašem výkresu na stejné vrstvě v toleranci
  není, chybí; úsek vaší čáry, který učitel nemá, je navíc (nezáleží na tom, jak je čára rozdělená
  nebo kolik má lomových bodů),
* když chybějící úsek leží na jiné vrstvě, hlásí se „jiná vrstva“ (typicky prvek ve špatné hladině),
* body a buňky podle nejbližšího prvku do tolerance, texty podle obsahu,
* u spárovaných prvků se porovnají atributy (barva, styl, tloušťka, výška a písmo textu, buňka).

Výsledek je seznam ``porovnani.Zmena`` (stejné okno jako porovnání verzí) a souhrn po vrstvách.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import shapely
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .checks.base import fmt_num
from .model import Drawing, Feature, GeomType
from .porovnani import Zmena, _pos, _what

CHYBI = "chybí (učitel má)"
NAVIC = "navíc (učitel nemá)"
JINA_VRSTVA = "jiná vrstva"
ATRIBUTY = "jiné atributy"
JINY_TEXT = "jiný text"
DRUHY = (CHYBI, JINA_VRSTVA, NAVIC, JINY_TEXT, ATRIBUTY)

_ATTRS = (("barva", lambda f: f.color_aci if f.color_aci is not None else f.color_rgb),
          ("styl", lambda f: (f.linetype or "").upper()),
          ("tloušťka", lambda f: f.attributes.get("MS_TLOUSTKA") or round(f.lineweight, 2)),
          ("měřítko stylu", lambda f: round(f.ltscale, 2)))
_TEXT_ATTRS = (("výška textu", lambda f: round(f.text_height, 2)), ("písmo", lambda f: (f.font or "").lower()))


@dataclass
class RadekVrstvy:
    vrstva: str
    ucitel_pocet: int = 0
    student_pocet: int = 0
    ucitel_delka: float = 0.0
    student_delka: float = 0.0
    chyby: int = 0


@dataclass
class VysledekVzoru:
    zmeny: list[Zmena] = field(default_factory=list)
    vrstvy: list[RadekVrstvy] = field(default_factory=list)
    shoda_kresby: float = 0.0  # podíl délky učitelových čar, které máte (0–1)
    poznamky: list[str] = field(default_factory=list)

    def souhrn(self) -> str:
        if self.poznamky and not self.zmeny:
            return " ".join(self.poznamky)
        if not self.zmeny:
            return "Výkres odpovídá výkresu učitele – nic nechybí ani nepřebývá."
        from collections import Counter
        c = Counter(z.druh for z in self.zmeny)
        return (f"Shoda kresby {self.shoda_kresby * 100:.0f} %. "
                + ", ".join(f"{d}: {c[d]}" for d in DRUHY if c.get(d)))


def _klic(v: str) -> str:
    return (v or "").strip().lower()


def _linie(f: Feature):
    g = f.geometry
    if g is None or g.is_empty:
        return None
    if f.geom_type == GeomType.POLYGON:
        return g.boundary
    if f.geom_type == GeomType.LINIE:
        return g
    return None


def _atributy(a: Feature, b: Feature, attrs) -> list[str]:
    out = []
    for name, get in attrs:
        va, vb = get(a), get(b)
        if va != vb:
            if isinstance(va, float):
                va, vb = fmt_num(va, 2), fmt_num(vb, 2)
            out.append(f"{name} {vb} (učitel {va})")
    return out


def _rozdil(g, p):
    """g − p, odolné vůči neplatné geometrii (výkresy z MicroStationu bývají „špinavé“)."""
    if p is None:
        return g
    try:
        return g.difference(p)
    except shapely.errors.GEOSException:
        return shapely.make_valid(g).difference(shapely.make_valid(p))


def _kusy(g, min_delka: float) -> list:
    return [p for p in getattr(g, "geoms", [g]) if p is not None and not p.is_empty
            and p.geom_type in ("LineString", "LinearRing") and p.length >= min_delka]


def _uzemi(d: Drawing):
    gs = [f.geometry for f in d.features if f.geometry is not None and not f.geometry.is_empty]
    return shapely.convex_hull(shapely.GeometryCollection(gs)) if gs else None


def _orez(d: Drawing, oblast) -> tuple[Drawing, int]:
    """Kopie výkresu jen s prvky, které zasahují do oblasti."""
    from copy import copy
    out = copy(d)
    out.features = [f for f in d.features if f.geometry is not None and f.geometry.intersects(oblast)]
    return out, len(d.features) - len(out.features)


def porovnej(ucitel: Drawing, student: Drawing, tol: float = 0.10, tol_bod: float | None = None,
             tol_text: float = 3.0, min_delka: float | None = None, jen_uzemi_studenta: bool = True,
             okraj: float = 10.0) -> VysledekVzoru:
    """Porovná ``student`` s ``ucitel``. ``tol`` = tolerance polohy čar (m), ``tol_bod`` bodů a buněk,
    ``tol_text`` vzdálenost textu se stejným obsahem, ``min_delka`` nejkratší hlášený úsek čáry.
    ``jen_uzemi_studenta``: kresba učitele mimo vaše území (obálka vaší kresby + ``okraj`` m) se nepočítá –
    učitelův výkres často pokrývá celou lokalitu, vy kreslíte jen svůj díl."""
    poznamky: list[str] = []
    uu, us = _uzemi(ucitel), _uzemi(student)
    if uu is None or us is None:
        return VysledekVzoru(poznamky=["Jeden z výkresů je prázdný."])
    if uu.buffer(okraj).disjoint(us):
        (ux, uy), (sx, sy) = uu.centroid.coords[0], us.centroid.coords[0]
        return VysledekVzoru(poznamky=[
            f"Výkresy se vůbec nepřekrývají – učitelův je kolem ({fmt_num(ux, 0)}; {fmt_num(uy, 0)}), váš kolem "
            f"({fmt_num(sx, 0)}; {fmt_num(sy, 0)}), rozdíl {fmt_num(uu.centroid.distance(us.centroid), 0)} m. "
            "Jde o jinou lokalitu, nebo jeden výkres není v S-JTSK (místní souřadnice, prohozené znaménko)."])
    if jen_uzemi_studenta:
        ucitel, mimo = _orez(ucitel, us.buffer(okraj))
        if mimo:
            poznamky.append(f"{mimo} prvků učitele leží mimo vaše území a nepočítají se.")
    tol_bod = tol_bod if tol_bod is not None else max(3 * tol, 0.3)
    min_delka = min_delka if min_delka is not None else max(0.5, 5 * tol)
    zmeny: list[Zmena] = []
    vrstvy: dict[str, RadekVrstvy] = {}

    def radek(f: Feature) -> RadekVrstvy:
        k = _klic(f.layer)
        if k not in vrstvy:
            vrstvy[k] = RadekVrstvy(f.layer)
        return vrstvy[k]

    def pridej(druh, f: Feature, popis: str, old=None, new=None, kde=None):
        x, y = kde if kde is not None else _pos(f)
        zmeny.append(Zmena(druh, f.layer, popis, x, y, old, new))
        radek(f).chyby += 1

    # ------------------------------------------------------------------ čáry (pokrytí)
    def linie_po_vrstvach(d: Drawing):
        out = defaultdict(list)
        for f in d.features:
            g = _linie(f)
            if g is not None and g.length > 0:
                out[_klic(f.layer)].append((f, g))
        return out

    lu, ls = linie_po_vrstvach(ucitel), linie_po_vrstvach(student)
    for d, por in ((lu, "ucitel"), (ls, "student")):
        for k, fs in d.items():
            for f, g in fs:
                r = radek(f)
                if por == "ucitel":
                    r.ucitel_pocet += 1
                    r.ucitel_delka += g.length
                else:
                    r.student_pocet += 1
                    r.student_delka += g.length

    def pas(lst):
        return unary_union([g.buffer(tol) for _f, g in lst]) if lst else None

    pas_u = {k: pas(v) for k, v in lu.items()}
    pas_s = {k: pas(v) for k, v in ls.items()}
    vse_s = [(f, g) for v in ls.values() for f, g in v]
    vse_u = [(f, g) for v in lu.values() for f, g in v]
    strom_s = STRtree([g for _f, g in vse_s]) if vse_s else None
    strom_u = STRtree([g for _f, g in vse_u]) if vse_u else None

    def jina_vrstva(kus, vrstva: str, seznam, strom):
        """Prvek z druhého výkresu na jiné vrstvě, který kus pokrývá (≥ 80 %)."""
        if strom is None:
            return None
        nej, nej_d = None, 0.0
        for i in strom.query(kus, predicate="dwithin", distance=tol):
            f, g = seznam[int(i)]
            if _klic(f.layer) == vrstva:
                continue
            d = kus.intersection(g.buffer(tol)).length
            if d > nej_d:
                nej, nej_d = f, d
        return nej if nej is not None and nej_d >= 0.8 * kus.length else None

    celkem_u, pokryto_u = 0.0, 0.0
    hlaseno_jina: set[int] = set()
    for k, fs in lu.items():
        p = pas_s.get(k)
        for f, g in fs:
            celkem_u += g.length
            chybi = _rozdil(g, p)
            pokryto_u += g.length - chybi.length
            for kus in _kusy(chybi, min_delka):
                jv = jina_vrstva(kus, k, vse_s, strom_s)
                mid = kus.interpolate(0.5, normalized=True)
                if jv is not None:
                    hlaseno_jina.add(id(jv))
                    pridej(JINA_VRSTVA, f, f"{_what(f).capitalize()} ({fmt_num(kus.length, 1)} m) je ve vrstvě "
                           f"„{jv.layer}“, učitel ji má ve vrstvě „{f.layer}“", f, jv, (mid.x, mid.y))
                else:
                    pridej(CHYBI, f, f"Chybí {_what(f)} – úsek {fmt_num(kus.length, 1)} m (učitel ji má ve vrstvě "
                           f"„{f.layer}“)", f, None, (mid.x, mid.y))
    for k, fs in ls.items():
        p = pas_u.get(k)
        for f, g in fs:
            if id(f) in hlaseno_jina:
                continue
            navic = _rozdil(g, p)
            for kus in _kusy(navic, min_delka):
                if jina_vrstva(kus, k, vse_u, strom_u) is not None:
                    continue  # už nahlášeno jako jiná vrstva z druhé strany
                mid = kus.interpolate(0.5, normalized=True)
                pridej(NAVIC, f, f"Navíc {_what(f)} – úsek {fmt_num(kus.length, 1)} m, učitel ji nemá", None, f,
                       (mid.x, mid.y))

    # atributy spárovaných čar: k učitelově čáře vaše čára na stejné vrstvě s největším společným úsekem
    hlaseno_attr: set[int] = set()
    for k, fs in lu.items():
        if k not in ls:
            continue
        strom = STRtree([g for _f, g in ls[k]])
        for f, g in fs:
            nej, nej_d = None, 0.0
            for i in strom.query(g, predicate="dwithin", distance=tol):
                sf, sg = ls[k][int(i)]
                d = sg.intersection(g.buffer(tol)).length
                if d > nej_d:
                    nej, nej_d = sf, d
            if nej is None or id(nej) in hlaseno_attr or nej_d < 0.5 * min(g.length, nej.geometry.length or 1):
                continue
            rozdil = _atributy(f, nej, _ATTRS)
            if rozdil:
                hlaseno_attr.add(id(nej))
                pridej(ATRIBUTY, nej, f"{_what(nej).capitalize()}: " + ", ".join(rozdil), f, nej)

    # ------------------------------------------------------------------ body a buňky
    def body(d: Drawing):
        return [f for f in d.features if f.geom_type == GeomType.BOD and f.geometry is not None
                and not f.geometry.is_empty]

    bu, bs = body(ucitel), body(student)
    for f in bu:
        radek(f).ucitel_pocet += 1
    for f in bs:
        radek(f).student_pocet += 1
    strom_b = STRtree([f.geometry for f in bs]) if bs else None
    pouzite: set[int] = set()
    for f in bu:
        kand = [] if strom_b is None else [bs[int(i)] for i in strom_b.query(f.geometry, predicate="dwithin",
                                                                              distance=tol_bod)]
        kand = [s for s in kand if id(s) not in pouzite and (s.block_name or "") == (f.block_name or "")]
        kand.sort(key=lambda s: (_klic(s.layer) != _klic(f.layer), s.geometry.distance(f.geometry)))
        if not kand:
            pridej(CHYBI, f, f"Chybí {_what(f)} (učitel ve vrstvě „{f.layer}“)", f, None)
            continue
        s = kand[0]
        pouzite.add(id(s))
        if _klic(s.layer) != _klic(f.layer):
            pridej(JINA_VRSTVA, s, f"{_what(s).capitalize()} je ve vrstvě „{s.layer}“, učitel ji má ve vrstvě "
                   f"„{f.layer}“", f, s)
            continue
        rozdil = _atributy(f, s, _ATTRS[:1])
        if f.block_name and abs(abs(f.scale[0]) - abs(s.scale[0])) > 1e-3 * max(1.0, abs(f.scale[0])):
            rozdil.append(f"měřítko buňky {fmt_num(abs(s.scale[0]), 3)} (učitel {fmt_num(abs(f.scale[0]), 3)})")
        if rozdil:
            pridej(ATRIBUTY, s, f"{_what(s).capitalize()}: " + ", ".join(rozdil), f, s)
    for s in bs:
        if id(s) not in pouzite:
            pridej(NAVIC, s, f"Navíc {_what(s)} – učitel ji tu nemá", None, s)

    # ------------------------------------------------------------------ texty
    def texty(d: Drawing):
        return [f for f in d.features if f.geom_type == GeomType.TEXT and (f.text or "").strip()
                and f.geometry is not None]

    tu, ts = texty(ucitel), texty(student)
    for f in tu:
        radek(f).ucitel_pocet += 1
    for f in ts:
        radek(f).student_pocet += 1
    strom_t = STRtree([f.geometry for f in ts]) if ts else None
    pouzite_t: set[int] = set()
    nesparovane = []
    for f in tu:
        kand = [] if strom_t is None else [ts[int(i)] for i in strom_t.query(f.geometry, predicate="dwithin",
                                                                              distance=tol_text)]
        stejne = [s for s in kand if id(s) not in pouzite_t and s.text.strip() == f.text.strip()]
        stejne.sort(key=lambda s: (_klic(s.layer) != _klic(f.layer), s.geometry.distance(f.geometry)))
        if not stejne:
            nesparovane.append((f, kand))
            continue
        s = stejne[0]
        pouzite_t.add(id(s))
        if _klic(s.layer) != _klic(f.layer):
            pridej(JINA_VRSTVA, s, f"Text „{s.text[:30]}“ je ve vrstvě „{s.layer}“, učitel ho má ve vrstvě "
                   f"„{f.layer}“", f, s)
            continue
        rozdil = _atributy(f, s, _ATTRS[:1] + _TEXT_ATTRS)
        if rozdil:
            pridej(ATRIBUTY, s, f"Text „{s.text[:30]}“: " + ", ".join(rozdil), f, s)
    for f, kand in nesparovane:
        jiny = [s for s in kand if id(s) not in pouzite_t and _klic(s.layer) == _klic(f.layer)
                and s.geometry.distance(f.geometry) <= max(1.0, 2 * (f.text_height or 0.5))]
        if jiny:
            s = min(jiny, key=lambda s: s.geometry.distance(f.geometry))
            pouzite_t.add(id(s))
            pridej(JINY_TEXT, s, f"Text „{s.text[:30]}“, učitel má „{f.text[:30]}“", f, s)
        else:
            pridej(CHYBI, f, f"Chybí text „{f.text[:30]}“ (učitel ve vrstvě „{f.layer}“)", f, None)
    for s in ts:
        if id(s) not in pouzite_t:
            pridej(NAVIC, s, f"Navíc text „{s.text[:30]}“ – učitel ho tu nemá", None, s)

    poradi = {d: i for i, d in enumerate(DRUHY)}
    zmeny.sort(key=lambda z: (poradi[z.druh], z.vrstva.lower(), -z.y, z.x))
    return VysledekVzoru(zmeny, sorted(vrstvy.values(), key=lambda r: r.vrstva.lower()),
                         (pokryto_u / celkem_u) if celkem_u else 1.0, poznamky)

