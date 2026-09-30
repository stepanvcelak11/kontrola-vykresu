"""Spojnice podle náčrtu: student zapíše, které body jsou v náčrtu spojené (např. „plot: 1-2-3-4“),
a aplikace ověří, že je má ve výkresu nakreslené – nic do výkresu nevkládá.

Zápis (jeden řádek = jedna linie):

    plot: 1-2-3-4
    budova 10-11-12-13-10
    5 - 6
    # komentář

Text před čísly (nepovinný) je nápověda, co to je; porovná se s názvy a vrstvami pravidel.
Čísla bodů se hledají v seznamu souřadnic (i zkrácená 4001 ↔ 610844001).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from ..model import GeomType
from ..rules import layer_matches
from .seznam import ListPoint, short_numbers, verify_points


@dataclass
class Spojnice:
    popis: str
    body: list[str]
    radek: int


@dataclass
class UsekVysledek:
    linie: Spojnice
    od: str
    do: str
    stav: str  # ok | chybi | vrstva | jinak | bod
    poznamka: str = ""
    geometry: object = None
    vrstvy: list[str] = field(default_factory=list)


STAVY_SPOJNIC = {"ok": "✓ nakresleno", "chybi": "chybí", "vrstva": "jiná vrstva", "jinak": "nakresleno jinak",
                 "bod": "bod není v seznamu"}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def parse_spojnice(text: str) -> list[Spojnice]:
    out = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^\s*([^\d:]*?)\s*:?\s*(\d[\w/]*(?:\s*[-–—,;]\s*\d[\w/]*)+)\s*$", line)
        if not m:
            continue
        nums = [n.strip() for n in re.split(r"[-–—,;]", m.group(2)) if n.strip()]
        out.append(Spojnice(m.group(1).strip(), nums, i))
    return out


def _expected_layers(popis: str, rules) -> list[str]:
    """Vrstvy z pravidel, jejichž název obsahuje slova z popisu (plot → „Plot dřevěný“ …)."""
    words = [w for w in re.findall(r"[a-z]{3,}", _norm(popis))]
    if not words or rules is None:
        return []
    out = []
    for r in rules.pravidla:
        n = _norm(f"{r.nazev} {r.kod}")
        if all(w[:5] in n for w in words) and r.geometrie in (GeomType.LINIE, GeomType.POLYGON, None):
            out.append(str(r.hladina))
    return out


def verify_lines(drawing, pts: list[ListPoint], text: str, rules=None, tol: float = 0.01) -> list[UsekVysledek]:
    """Ověří spojnice z náčrtu proti čarám ve výkresu."""
    res, best, _ = verify_points(drawing, pts, tol)
    pos: dict[str, tuple[float, float]] = {}
    if best is not None:
        from .seznam import _TRANSFORMS
        tr = _TRANSFORMS[best]
        for p in pts:
            xy = tr(p.a, p.b)
            for n in short_numbers(p.cislo):
                pos.setdefault(n, xy)
            pos.setdefault(p.cislo, xy)
    feats = [f for f in drawing.features if f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
             and f.geometry is not None]
    geoms = np.array([f.geometry.boundary if f.geom_type == GeomType.POLYGON else f.geometry for f in feats],
                     dtype=object)
    tree = shapely.STRtree(geoms) if len(geoms) else None
    out: list[UsekVysledek] = []
    for sp in parse_spojnice(text):
        expected = _expected_layers(sp.popis, rules)
        for a, b in zip(sp.body[:-1], sp.body[1:]):
            if a not in pos or b not in pos:
                miss = ", ".join(n for n in (a, b) if n not in pos)
                out.append(UsekVysledek(sp, a, b, "bod", f"bod {miss} není v seznamu souřadnic"))
                continue
            seg = LineString([pos[a], pos[b]])
            if seg.length <= tol or tree is None:
                continue
            idx = tree.query(seg, predicate="dwithin", distance=tol)
            covering, cover = [], None
            for j in idx:
                part = seg.intersection(geoms[j].buffer(tol))
                if part.length > 0.05 * seg.length:
                    covering.append(int(j))
                    cover = part if cover is None else cover.union(part)
            ratio = 0.0 if cover is None else cover.length / seg.length
            layers = sorted({feats[j].layer for j in covering})
            if ratio >= 0.98:
                if expected and not any(layer_matches(h, lay) for h in expected for lay in layers):
                    out.append(UsekVysledek(sp, a, b, "vrstva", f"je na vrstvě {', '.join(layers)}, čekal bych "
                                            f"{', '.join(expected)}", seg, layers))
                else:
                    out.append(UsekVysledek(sp, a, b, "ok", ", ".join(layers), seg, layers))
                continue
            # nakreslené jinak (oblouk, lomená čára): jeden prvek prochází oběma body
            both = [j for j in tree.query(Point(pos[a]), predicate="dwithin", distance=tol)
                    if geoms[j].distance(Point(pos[b])) <= tol]
            if both:
                lay = sorted({feats[j].layer for j in both})
                out.append(UsekVysledek(sp, a, b, "jinak", f"body spojuje prvek na vrstvě {', '.join(lay)}, ale ne "
                                        "přímou čarou (oblouk / lomená čára) – ověřte podle náčrtu", seg, lay))
            elif ratio > 0:
                out.append(UsekVysledek(sp, a, b, "chybi", f"nakresleno jen {ratio * 100:.0f} % délky", seg, layers))
            else:
                out.append(UsekVysledek(sp, a, b, "chybi", f"mezi body {a} a {b} není čára ({seg.length:.2f} m)",
                                        seg, []))
    return out
