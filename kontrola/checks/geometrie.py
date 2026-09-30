"""Obecné kontroly geometrie – fungují na jakýkoli výkres, i bez pravidel od učitele.

* zbytečné lomové body (bod na rovné čáře, na který nic nenavazuje),
* špička – čára se v lomovém bodě vrací zpět,
* nepatrná nebo úzká plocha (zbytek po editaci, „štěrbina“),
* nečitelně malý text (podle měřítka tisku).
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import shapely

from ..model import GeomType
from .base import Check, CheckContext, Param, Severity, fmt_m, fmt_num, register


def _vertices(f):
    v = f.vertices if len(f.vertices) >= 2 else [c[:2] for c in f.geometry.coords]
    return [tuple(p[:2]) for p in v]


@register
class ZbytecneLomoveBody(Check):
    id = "zbytecne_lomove_body"
    nazev = "Zbytečné lomové body"
    skupina = "Geometrie"
    popis = ("Lomový bod leží na rovné čáře (čára v něm nemění směr) a nic na něj nenavazuje. Nevadí, ale "
             "výkres zbytečně zatěžuje a při editaci se na něm snadno udělá chyba.")
    vychozi_zavaznost = Severity.INFO
    parametry = [Param("odchylka", "Odchylka od přímky do [m]", "float", 0.001)]

    def run(self, ctx: CheckContext):
        tol = float(ctx.param("odchylka", 0.001))
        feats = [f for f in ctx.linear() if f.geom_type == GeomType.LINIE and len(f.vertices) >= 3]
        if not feats:
            return
        all_geoms = np.array([ctx.boundary(f) for f in ctx.linear()], dtype=object)
        tree = shapely.STRtree(all_geoms)
        eps = max(ctx.precision, 1e-6)
        for f in feats:
            v = _vertices(f)
            for k in range(1, len(v) - 1):
                a, p, b = v[k - 1], v[k], v[k + 1]
                ab = math.dist(a, b)
                if ab <= eps or math.dist(a, p) <= eps or math.dist(p, b) <= eps:
                    continue
                # vzdálenost bodu od spojnice sousedů a to, že leží mezi nimi (ne zpětný zlom)
                cross = abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / ab
                dot = (p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])
                if cross > tol or dot <= 0 or dot >= ab * ab:
                    continue
                pt = shapely.points(p)
                touching = [j for j in tree.query(pt, predicate="dwithin", distance=eps)
                            if all_geoms[j] is not ctx.boundary(f)]
                if touching:
                    continue  # uzel – navazuje sem jiná čára
                yield ctx.issue(self, f, "Zbytečný lomový bod na rovné čáře", at=p)


@register
class Spicka(Check):
    id = "spicka"
    nazev = "Špička (čára se vrací zpět)"
    skupina = "Geometrie"
    popis = ("V lomovém bodě se čára otočí téměř o 180° a vede zpět po sobě – typicky omylem kliknutý bod "
             "nebo „zub“ po úpravě vrcholu. Na výkrese je to často neviditelné.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("uhel", "Hlásit ostřejší úhel než [°]", "float", 10.0)]

    def run(self, ctx: CheckContext):
        lim = math.radians(float(ctx.param("uhel", 10.0)))
        for f in ctx.linear():
            if f.geom_type != GeomType.LINIE or len(f.vertices) < 3:
                continue
            v = _vertices(f)
            if f.closed and len(v) > 3 and math.dist(v[0], v[-1]) < 1e-9:
                v = v[:-1] + [v[0], v[1]]
            for k in range(1, len(v) - 1):
                a, p, b = v[k - 1], v[k], v[k + 1]
                u = (a[0] - p[0], a[1] - p[1])
                w = (b[0] - p[0], b[1] - p[1])
                lu, lw = math.hypot(*u), math.hypot(*w)
                if lu < 1e-6 or lw < 1e-6:
                    continue
                ang = math.acos(max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (lu * lw))))
                if ang < lim:
                    yield ctx.issue(self, f, f"Špička – čára se vrací pod úhlem {fmt_num(math.degrees(ang), 1)}° "
                                            f"(délka zpětného úseku {fmt_m(min(lu, lw))})", at=p)


@register
class NepatrnaPlocha(Check):
    id = "nepatrna_plocha"
    nazev = "Nepatrná nebo úzká plocha"
    skupina = "Geometrie"
    popis = ("Uzavřená plocha s nepatrnou výměrou nebo velmi úzká („štěrbina“) – zbytek po editaci nebo "
             "omylem uzavřený tvar.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("min_plocha", "Menší než [m²]", "float", 0.05),
                 Param("min_sirka", "Užší než [m] (průměrná šířka)", "float", 0.02)]

    def run(self, ctx: CheckContext):
        amin = float(ctx.param("min_plocha", 0.05))
        wmin = float(ctx.param("min_sirka", 0.02))
        for f in ctx.linear():
            if f.geom_type != GeomType.POLYGON or f.dxftype in ("HATCH", "CIRCLE", "ELLIPSE"):
                continue  # kružnice a elipsy jsou značky, ne plochy
            g = f.geometry
            if not g.is_valid or g.area <= 0:
                continue  # neplatné / nulové hlásí jiné kontroly
            width = 2 * g.area / g.length if g.length else 0.0
            if g.area < amin:
                yield ctx.issue(self, f, f"Nepatrná plocha {fmt_num(g.area, 4)} m²")
            elif width < wmin:
                yield ctx.issue(self, f, f"Velmi úzká plocha (průměrná šířka {fmt_m(width)})")


@register
class MalyText(Check):
    id = "maly_text"
    nazev = "Nečitelně malý text"
    skupina = "Kartografie"
    popis = ("Text je tak malý, že po vytištění v měřítku výkresu nepůjde přečíst (výška na papíře pod "
             "zadanou mezí). Měřítko se bere z pravidel (Směrnice).")
    vychozi_zavaznost = Severity.INFO
    vychozi_zapnuto = False
    parametry = [Param("min_mm", "Nejmenší výška písma na papíře [mm]", "float", 1.0),
                 Param("meritko", "Měřítko 1: (0 = z pravidel)", "float", 0.0)]

    def run(self, ctx: CheckContext):
        m = float(ctx.param("meritko", 0.0)) or float(getattr(ctx.rules, "meritko", 0) or 0)
        if not m:
            ctx.notes.append("nečitelně malý text: není známé měřítko – zadejte ho v Nastavení kontrol.")
            return
        hmin = float(ctx.param("min_mm", 1.0)) * m / 1000.0
        for f in ctx.features():
            if f.geom_type == GeomType.TEXT and f.text and f.text.strip() and 0 < f.text_height < hmin:
                yield ctx.issue(self, f, f"Text „{f.text.strip()[:20]}“ má na papíře "
                                         f"{fmt_num(f.text_height * 1000 / m, 2)} mm (měřítko 1:{m:g})")


@register
class ZatoulanyPrvek(Check):
    id = "zatoulany_prvek"
    nazev = "Zatoulaný prvek daleko od kresby"
    skupina = "Geometrie"
    popis = ("Prvek (nebo malá skupinka prvků) leží daleko od ostatní kresby – typicky omylem kliknutý bod, "
             "prvek v počátku souřadnic nebo kopie mimo mapu. Kvůli němu je „Zobrazit vše“ prázdné.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("vzdalenost", "Dál od ostatní kresby než [m] (0 = automaticky)", "float", 0.0)]

    def run(self, ctx: CheckContext):
        feats = [f for f in ctx.features() if f.geometry is not None and not f.geometry.is_empty]
        n = len(feats)
        if n < 10:
            return
        cx = np.array([f.geometry.centroid.x for f in feats])
        cy = np.array([f.geometry.centroid.y for f in feats])
        x0, x1 = np.percentile(cx, [5, 95])
        y0, y1 = np.percentile(cy, [5, 95])
        diag = math.hypot(x1 - x0, y1 - y0)
        lim = float(ctx.param("vzdalenost", 0.0)) or max(20.0, 0.25 * diag)
        # shluky obsazených buněk mřížky o velikosti lim (sousední buňky = jeden shluk) – rychlé i na
        # velkých výkresech; prvek patří do buňky svého těžiště
        cells: dict[tuple[int, int], list[int]] = {}
        for i in range(n):
            cells.setdefault((int(math.floor(cx[i] / lim)), int(math.floor(cy[i] / lim))), []).append(i)
        comp: dict[tuple[int, int], int] = {}
        groups: list[list[tuple[int, int]]] = []
        for start in cells:
            if start in comp:
                continue
            comp[start] = len(groups)
            stack, members = [start], []
            while stack:
                c = stack.pop()
                members.append(c)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nb = (c[0] + dx, c[1] + dy)
                        if nb in cells and nb not in comp:
                            comp[nb] = comp[start]
                            stack.append(nb)
            groups.append(members)
        sizes = [sum(len(cells[c]) for c in g) for g in groups]
        main = max(range(len(groups)), key=sizes.__getitem__)
        small = max(3, n // 100)
        main_geom = shapely.union_all([shapely.box(c[0] * lim, c[1] * lim, (c[0] + 1) * lim, (c[1] + 1) * lim)
                                       for c in groups[main]])
        for k, g in enumerate(groups):
            if k == main or sizes[k] > small:
                continue
            for c in g:
                for i in cells[c]:
                    d = main_geom.distance(feats[i].geometry)
                    yield ctx.issue(self, feats[i], f"Prvek je daleko od ostatní kresby (asi {fmt_num(d, 0)} m)")


@register
class RozdelenaCara(Check):
    id = "rozdelena_cara"
    nazev = "Zbytečně rozdělená čára"
    skupina = "Geometrie"
    popis = ("Dvě čáry stejné vrstvy a vzhledu na sebe navazují v přímém směru a v místě napojení nic "
             "dalšího není – mohla by to být jedna čára. Nevadí, jen je výkres zbytečně rozdrobený.")
    vychozi_zavaznost = Severity.INFO
    vychozi_zapnuto = False
    parametry = [Param("uhel", "Odchylka od přímého směru do [°]", "float", 1.0)]

    def run(self, ctx: CheckContext):
        lim = math.radians(float(ctx.param("uhel", 1.0)))
        feats = [f for f in ctx.linear() if f.geom_type == GeomType.LINIE and not f.closed
                 and len(f.geometry.coords) >= 2]
        eps = max(ctx.precision, 1e-6)
        ends: dict[tuple[int, int], list[tuple[object, tuple, tuple]]] = {}
        q = 1.0 / eps
        for f in feats:
            c = [tuple(p[:2]) for p in f.geometry.coords]
            for p, nb in ((c[0], c[1]), (c[-1], c[-2])):
                ends.setdefault((round(p[0] * q), round(p[1] * q)), []).append((f, p, nb))
        all_geoms = np.array([ctx.boundary(f) for f in ctx.linear()], dtype=object)
        tree = shapely.STRtree(all_geoms)
        pts = [f.geometry for f in ctx.features() if f.geom_type == GeomType.BOD]
        ptree = shapely.STRtree(np.array(pts, dtype=object)) if pts else None
        for items in ends.values():
            if len(items) != 2:
                continue
            (fa, p, na), (fb, _p, nb) = items
            if fa is fb or fa.layer != fb.layer or fa.linetype != fb.linetype or fa.color_rgb != fb.color_rgb \
                    or round(fa.lineweight, 2) != round(fb.lineweight, 2):
                continue
            u = (na[0] - p[0], na[1] - p[1])
            w = (nb[0] - p[0], nb[1] - p[1])
            lu, lw = math.hypot(*u), math.hypot(*w)
            if lu < 1e-9 or lw < 1e-9:
                continue
            ang = math.acos(max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (lu * lw))))
            if math.pi - ang > lim:
                continue
            if len(tree.query(shapely.points(p), predicate="dwithin", distance=eps)) > 2:
                continue  # uzel – navazuje sem ještě něco
            if ptree is not None and len(ptree.query(shapely.points(p), predicate="dwithin", distance=0.01)):
                continue  # v místě napojení je bod (měřený bod, značka) – rozdělení je v pořádku
            yield ctx.issue(self, [fa, fb], "Čára je zbytečně rozdělená na dvě (navazují v přímém směru)", at=p)


_NUM = re.compile(r"(\d+)([.,])(\d+)|\d+(?:[^\W\d_]\b)?")  # „12a“ (orientační číslo) = celé číslo


def _vzor_popisu(text: str) -> str:
    """Tvar popisu: číslice celé části sloučené, desetinná místa počítaná („245.37“ → „9.99“, „12a“ → „9a“)."""
    def num(m):
        if m.group(2):
            return "9" + m.group(2) + "9" * len(m.group(3))
        return "9"
    s = _NUM.sub(num, text.strip())
    return re.sub(r"[^\W\d_]+", "a", s)


@register
class FormatPopisu(Check):
    id = "format_popisu"
    nazev = "Nejednotný formát popisů na vrstvě"
    skupina = "Kartografie"
    popis = ("Na vrstvě s číselnými popisy (výšky, čísla bodů) má popis jiný tvar než ostatní – např. výška "
             "s jedním desetinným místem místo dvou, desetinná čárka místo tečky nebo písmeno navíc.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [Param("podil", "Většinový tvar musí mít aspoň [%] popisů", "float", 80.0)]

    def run(self, ctx: CheckContext):
        share = float(ctx.param("podil", 80.0)) / 100.0
        by_layer: dict[str, list] = {}
        for f in ctx.features():
            if f.geom_type == GeomType.TEXT and (f.text or "").strip():
                by_layer.setdefault(f.layer, []).append(f)
        for layer, feats in by_layer.items():
            if len(feats) < 5:
                continue
            pats = Counter(_vzor_popisu(f.text) for f in feats)
            main, n = pats.most_common(1)[0]
            if "9" not in main or n < share * len(feats) or len(pats) == 1:
                continue
            example = next(f.text.strip() for f in feats if _vzor_popisu(f.text) == main)
            for f in feats:
                if _vzor_popisu(f.text) != main:
                    yield ctx.issue(self, f, f"Popis „{f.text.strip()[:20]}“ má jiný tvar než ostatní na vrstvě "
                                             f"(obvykle např. „{example[:20]}“)")
