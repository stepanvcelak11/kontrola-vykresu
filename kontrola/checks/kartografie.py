"""Kartografické kontroly – co MGEO nehlídá, ale učitel vidí okem na mapě:

* popisy přes sebe,
* popis přeškrtnutý čarou,
* číslo bodu daleko od bodu,
* popis vzhůru nohama.
"""

from __future__ import annotations

import math
import re

import numpy as np
import shapely
from shapely.geometry import Polygon

from ..model import Feature, GeomType
from .base import Check, CheckContext, Param, Severity, fmt_m, register


def text_box(f: Feature, pad: float = 0.0) -> Polygon | None:
    """Obdélník textu (odhad podle výšky, počtu znaků, zarovnání a natočení) – jako kroužek ve výkresu."""
    if f.geom_type != GeomType.TEXT or not f.text or f.geometry is None or f.geometry.geom_type != "Point":
        return None
    h = max(f.text_height or 0.0, 0.01)
    w = max(1, len(f.text.strip())) * h * 0.72 * (f.width_factor or 1.0)
    x0 = {0: 0.0, 1: -w / 2, 2: -w}.get(f.halign, 0.0)
    y0 = {0: 0.0, 1: 0.0, 2: -h / 2, 3: -h}.get(f.valign, 0.0)
    a = math.radians(f.rotation or 0.0)
    ca, sa = math.cos(a), math.sin(a)
    px, py = f.geometry.x, f.geometry.y
    corners = [(x0 - pad, y0 - pad), (x0 + w + pad, y0 - pad), (x0 + w + pad, y0 + h + pad), (x0 - pad, y0 + h + pad)]
    return Polygon([(px + cx * ca - cy * sa, py + cx * sa + cy * ca) for cx, cy in corners])


def _texts(ctx: CheckContext):
    feats = [f for f in ctx.features() if f.geom_type == GeomType.TEXT and f.text and f.text.strip()]
    boxes = [text_box(f) for f in feats]
    keep = [(f, b) for f, b in zip(feats, boxes) if b is not None and b.is_valid and b.area > 0]
    return [f for f, _ in keep], [b for _, b in keep]


@register
class PopisyPresSebe(Check):
    id = "popisy_pres_sebe"
    nazev = "Popisy přes sebe"
    skupina = "Kartografie"
    popis = ("Dva popisy (texty) se na mapě překrývají, takže nejdou přečíst. Posuňte jeden z nich. "
             "Hlídá se podle velikosti písma, takže sedí i s tiskem.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("min_prekryv", "Hlásit překryv od [% menšího popisu]", "float", 25.0)]

    def run(self, ctx: CheckContext):
        feats, boxes = _texts(ctx)
        if len(boxes) < 2:
            return
        lim = float(ctx.param("min_prekryv", 25.0)) / 100.0
        arr = np.array(boxes, dtype=object)
        tree = shapely.STRtree(arr)
        a, b = tree.query(arr, predicate="intersects")
        m = a < b
        for i, j in zip(a[m], b[m]):
            fi, fj = feats[i], feats[j]
            if fi.text.strip() == fj.text.strip() and fi.geometry.distance(fj.geometry) < 1e-6:
                continue  # stejný text na stejném místě řeší kontrola duplicit
            if max(_h(fi), _h(fj)) > 2 * min(_h(fi), _h(fj)):
                continue  # pracovní drobné popisy vs. popisy pro tisk (jiná sada, netisknou se spolu)
            inter = boxes[i].intersection(boxes[j]).area
            if inter >= lim * min(boxes[i].area, boxes[j].area):
                c = boxes[i].intersection(boxes[j]).centroid
                yield ctx.issue(self, [fi, fj], f"Popisy „{fi.text.strip()}“ a „{fj.text.strip()}“ jsou přes sebe",
                                at=(c.x, c.y), geometry=boxes[i].union(boxes[j]))


@register
class PopisPresCaru(Check):
    id = "popis_pres_caru"
    nazev = "Popis přeškrtnutý čarou"
    skupina = "Kartografie"
    popis = ("Čára vede přes popis (text), takže je popis špatně čitelný. Posuňte popis vedle čáry. "
             "Ignorují se čáry, které k popisu patří (odkazová čára, rámeček) – kratší než popis.")
    vychozi_zavaznost = Severity.INFO
    parametry = [Param("min_podil", "Hlásit, když čára vede přes [% šířky popisu]", "float", 40.0)]

    def run(self, ctx: CheckContext):
        feats, boxes = _texts(ctx)
        lines = [f for f in ctx.linear() if f.dxftype != "HATCH"]
        if not boxes or not lines:
            return
        lim = float(ctx.param("min_podil", 40.0)) / 100.0
        geoms = np.array([ctx.boundary(f) for f in lines], dtype=object)
        tree = shapely.STRtree(geoms)
        tb, lg = tree.query(np.array([b.buffer(-min(0.1, _h(f) * 0.15)) for f, b in zip(feats, boxes)],
                                     dtype=object), predicate="intersects")
        seen = set()
        for i, j in zip(tb, lg):
            if i in seen:
                continue
            f, box, g = feats[i], boxes[i], geoms[j]
            width = _width(f)
            if g.length < width:
                continue
            inside = g.intersection(box.buffer(-min(0.1, _h(f) * 0.15))).length
            if inside >= lim * width:
                seen.add(i)
                c = box.centroid
                yield ctx.issue(self, [f, lines[j]], f"Popis „{f.text.strip()}“ přeškrtává čára na vrstvě "
                                f"{lines[j].layer}", at=(c.x, c.y), geometry=box)


def _h(f: Feature) -> float:
    return max(f.text_height or 0.0, 0.01)


def _width(f: Feature) -> float:
    return max(1, len(f.text.strip())) * _h(f) * 0.72 * (f.width_factor or 1.0)


@register
class CisloBoduDaleko(Check):
    id = "cislo_bodu_daleko"
    nazev = "Číslo bodu daleko od bodu"
    skupina = "Kartografie"
    popis = ("Číslo bodu (text z číslic) je daleko od nejbližšího bodu, takže není jasné, ke kterému bodu patří – "
             "často po posunu bodu nebo textu. Číslo má být hned u značky bodu.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("max_vzdalenost", "Nejvýš [× výška písma]", "float", 4.0),
                 Param("vrstvy_cisel", "Vrstvy čísel bodů (prázdné = poznat samo)", "layers", "")]

    def run(self, ctx: CheckContext):
        pts = [f for f in ctx.features() if f.geom_type == GeomType.BOD and f.dxftype != "TEXT"
               and f.geometry is not None and f.geometry.geom_type == "Point"]
        if len(pts) < 3:
            return
        want = ctx.param("vrstvy_cisel", "")
        if isinstance(want, str):
            want = [s.strip() for s in want.split(",") if s.strip()]
        from ..rules import layer_matches
        texts = [f for f in ctx.features() if f.geom_type == GeomType.TEXT and f.text
                 and re.fullmatch(r"\d{1,6}", f.text.strip()) and f.geometry is not None
                 and (not want or any(layer_matches(w, f.layer) for w in want))]
        if not texts:
            return
        if not want:  # jen vrstvy, kde jsou čísla převážně hned u bodů (jinak to nejsou čísla bodů)
            tree = shapely.STRtree(np.array([p.geometry for p in pts], dtype=object))
            by_layer: dict[str, list] = {}
            for t in texts:
                by_layer.setdefault(t.layer, []).append(t)
            texts = []
            for lay, ts in by_layer.items():
                near = sum(1 for t in ts if t.geometry.distance(pts[tree.nearest(t.geometry)].geometry) <= 3 * _h(t))
                if len(ts) >= 3 and near >= 0.6 * len(ts):
                    texts.extend(ts)
        if not texts:
            return
        tree = shapely.STRtree(np.array([p.geometry for p in pts], dtype=object))
        k = float(ctx.param("max_vzdalenost", 4.0))
        for t in texts:
            box = text_box(t) or t.geometry
            j = tree.nearest(box)
            d = box.distance(pts[j].geometry)
            if d > k * _h(t):
                yield ctx.issue(self, [t, pts[j]], f"Číslo bodu {t.text.strip()} je {fmt_m(d)} od nejbližšího bodu",
                                at=(t.geometry.x, t.geometry.y))


@register
class PopisVzhuruNohama(Check):
    id = "popis_vzhuru_nohama"
    nazev = "Popis vzhůru nohama"
    skupina = "Kartografie"
    popis = ("Text je natočený tak, že se na mapě čte vzhůru nohama (natočení mezi 90° a 270°). Popisy se "
             "otáčejí tak, aby se četly zdola nebo zprava – otočte ho o 180°.")
    vychozi_zavaznost = Severity.INFO
    parametry = [Param("rezerva", "Rezerva kolem 90° a 270° [°]", "float", 10.0)]

    def run(self, ctx: CheckContext):
        r = float(ctx.param("rezerva", 10.0))
        for f in ctx.features():
            if f.geom_type != GeomType.TEXT or not f.text or not f.text.strip():
                continue
            a = (f.rotation or 0.0) % 360
            if 90 + r < a < 270 - r:
                yield ctx.issue(self, f, f"Popis „{f.text.strip()}“ je vzhůru nohama (natočení {a:.0f}°)")
