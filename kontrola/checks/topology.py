"""Topologické kontroly (shapely + prostorový index STRtree)."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPoint, Point

from ..model import Feature, GeomType
from .base import Check, CheckContext, Param, Severity, fmt_m, fmt_num, register

LAYERS_PARAM = Param("hladiny", "Jen hladiny (čárkou, * = zástupný znak)", "layers", "",
                     "Prázdné = všechny hladiny.")


def _expects_polygon(ctx: CheckContext, f: Feature) -> bool | None:
    r = ctx.rule_for(f)
    if r is None or r.geometrie is None:
        return None
    return r.geometrie == GeomType.POLYGON


@register
class NezavrenePolygony(Check):
    id = "nezavrene_polygony"
    nazev = "Nezavřený polygon"
    skupina = "Topologie"
    popis = ("Linie, které mají být polygonem (podle pravidel), ale nejsou uzavřené, a lomené čáry, "
             "jejichž konce jsou blízko sebe – pravděpodobně zapomenuté uzavření.")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("max_mezera", "Bez pravidla hlásit mezeru do [m]", "float", 1.0,
              "U prvků bez pravidla se hlásí jen lomené čáry, jejichž konce jsou blíž než tato hodnota."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        max_gap = float(ctx.param("max_mezera", 1.0))
        feats = ctx.linear()
        for i, f in enumerate(feats):
            if i % 2000 == 0:
                ctx.progress(i / max(1, len(feats)))
            if f.geom_type != GeomType.LINIE or f.dxftype in ("ARC",):
                continue
            coords = list(f.geometry.coords)
            if len(coords) < 2:
                continue
            a, b = coords[0], coords[-1]
            gap = math.dist(a[:2], b[:2])
            expects = _expects_polygon(ctx, f)
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if expects:
                if gap <= ctx.precision:
                    msg = "Polygon je uzavřen jen geometricky (chybí příznak uzavření)"
                else:
                    msg = f"Nezavřený polygon, mezera {fmt_m(gap)}"
                yield ctx.issue(self, f, msg, at=mid)
            elif expects is None and len(coords) >= 4 and ctx.precision < gap <= max_gap:
                length = f.geometry.length
                if gap < 0.25 * length:
                    yield ctx.issue(self, f, f"Nezavřený polygon, mezera {fmt_m(gap)}", at=mid)


class _EndpointAnalysis:
    """Sdílený výpočet konců linií a jejich nejbližších sousedů."""

    def __init__(self, ctx: CheckContext, feats: list[Feature]):
        self.feats = feats
        geoms = np.array([ctx.boundary(f) for f in feats], dtype=object)
        self.geoms = geoms
        self.tree = shapely.STRtree(geoms) if len(geoms) else None
        pts, owner, is_end, own_gap = [], [], [], []
        for i, f in enumerate(feats):
            if f.geom_type != GeomType.LINIE:
                continue
            coords = f.geometry.coords
            if len(coords) < 2:
                continue
            a, b = coords[0][:2], coords[-1][:2]
            if math.dist(a, b) <= ctx.precision:
                continue  # geometricky uzavřená linie nemá volné konce
            pts += [a, b]
            owner += [i, i]
            is_end += [0, 1]
            own_gap += [math.dist(a, b)] * 2
        self.points = np.array(pts, dtype=float).reshape(-1, 2)
        self.owner = np.array(owner, dtype=int)
        self.is_end = np.array(is_end, dtype=int)
        self.own_gap = np.array(own_gap, dtype=float)
        self.nearest = np.full(len(self.points), np.inf)
        self.nearest_idx = np.full(len(self.points), -1)
        if self.tree is None or not len(self.points):
            return
        pgeoms = shapely.points(self.points)
        self.pgeoms = pgeoms
        pi, gi = self.tree.query(pgeoms, predicate="dwithin", distance=ctx.tolerance)
        mask = gi != self.owner[pi]
        pi, gi = pi[mask], gi[mask]
        if len(pi):
            d = shapely.distance(pgeoms[pi], geoms[gi])
            order = np.lexsort((d, pi))
            pi, gi, d = pi[order], gi[order], d[order]
            first = np.ones(len(pi), dtype=bool)
            first[1:] = pi[1:] != pi[:-1]
            self.nearest[pi[first]] = d[first]
            self.nearest_idx[pi[first]] = gi[first]
        # konec, který se dotýká jiné části téže linie (např. tvar „P“), se nepovažuje za visící
        own = shapely.distance(pgeoms, _without_end_segments(feats, self.owner, self.is_end))
        self.self_touch = own <= ctx.precision


def _without_end_segments(feats, owner, is_end):
    out = []
    for o, e in zip(owner, is_end):
        coords = list(feats[o].geometry.coords)
        part = coords[:-2] if e == 1 else coords[2:]
        out.append(LineString(part) if len(part) >= 2 else LineString())
    return np.array(out, dtype=object)


def _endpoint_analysis(ctx: CheckContext) -> _EndpointAnalysis:
    key = "endpoints|" + ",".join(ctx.layer_filter() or []) + f"|{ctx.tolerance}"
    if key not in ctx._cache:
        ctx._cache[key] = _EndpointAnalysis(ctx, ctx.linear())
    return ctx._cache[key]


@register
class VisiciKonce(Check):
    id = "visici_konce"
    nazev = "Visící konec linie"
    skupina = "Topologie"
    popis = ("Konec linie, u kterého v okruhu tolerance není žádná jiná linie (dangle). "
             "U plotů a jiných volně končících linií může být v pořádku.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [LAYERS_PARAM]

    def run(self, ctx: CheckContext):
        an = _endpoint_analysis(ctx)
        ctx.progress(0.5)
        for k in range(len(an.points)):
            if np.isfinite(an.nearest[k]) or an.self_touch[k] or an.own_gap[k] <= ctx.tolerance:
                continue  # napojeno, nebo jde o téměř uzavřený polygon (řeší jiná kontrola)
            f = an.feats[an.owner[k]]
            if _expects_polygon(ctx, f):
                continue  # řeší kontrola nezavřených polygonů
            x, y = an.points[k]
            yield ctx.issue(self, f, "Visící konec linie", at=(x, y))


@register
class ChybejiciNapojeni(Check):
    id = "chybejici_napojeni"
    nazev = "Chybějící napojení"
    skupina = "Topologie"
    popis = ("Konec linie je od jiné linie blíž než tolerance, ale není na ni napojen "
             "(nedotažení nebo přetažení).")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [LAYERS_PARAM]

    def run(self, ctx: CheckContext):
        an = _endpoint_analysis(ctx)
        ctx.progress(0.5)
        for k in range(len(an.points)):
            d = an.nearest[k]
            if not np.isfinite(d) or d <= ctx.precision or an.self_touch[k]:
                continue
            f = an.feats[an.owner[k]]
            other = an.feats[an.nearest_idx[k]]
            x, y = an.points[k]
            yield ctx.issue(self, [f, other], f"Chybějící napojení, vzdálenost {fmt_m(d)}", at=(x, y),
                            geometry=f.geometry)


@register
class Duplicity(Check):
    id = "duplicity"
    nazev = "Duplicitní prvek"
    skupina = "Topologie"
    popis = "Dva prvky se stejnou geometrií (i s opačným směrem kreslení) nebo dva body na stejném místě."
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("stejna_hladina", "Jen prvky na stejné hladině", "bool", True,
              "Hranice budovy a parcely se mohou legitimně krýt – proto se výchozí porovnávají jen "
              "prvky na stejné hladině."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        same_layer = bool(ctx.param("stejna_hladina", True))
        feats = [f for f in ctx.features(ctx.layer_filter())
                 if f.geometry is not None and not f.geometry.is_empty]
        grid = max(ctx.precision, 1e-6)
        groups: dict[tuple, list[Feature]] = defaultdict(list)
        for i, f in enumerate(feats):
            if i % 5000 == 0:
                ctx.progress(i / max(1, len(feats)))
            if f.geom_type == GeomType.TEXT:
                key_extra = (f.text or "",)
            elif f.dxftype == "INSERT":
                key_extra = (f.block_name,)
            else:
                key_extra = ()
            kind = "bod" if f.geom_type == GeomType.BOD else f.geom_type.value
            g = shapely.normalize(shapely.transform(f.geometry, lambda c: np.round(c / grid) * grid))
            key = (kind, f.layer.upper() if same_layer else "", key_extra, g.wkb)
            groups[key].append(f)
        for key, fs in groups.items():
            if len(fs) < 2:
                continue
            first = fs[0]
            what = "bod" if key[0] in ("bod", "text") else "prvek"
            msg = f"Duplicitní {what} ({len(fs)}×)"
            if key[0] == "text":
                msg = f"Duplicitní text „{(first.text or '')[:20]}“ ({len(fs)}×)"
            yield ctx.issue(self, fs, msg, geometry=first.geometry)
