"""Topologické kontroly (shapely + prostorový index STRtree)."""

from __future__ import annotations

import math
import re
from collections import defaultdict

import numpy as np
import shapely
import shapely.errors
from shapely.geometry import LineString, Point
from shapely.validation import make_valid

from ..model import Feature, GeomType
from .base import Check, CheckContext, Param, Severity, fmt_m, fmt_num, register

LAYERS_PARAM = Param("hladiny", "Jen vrstvy (čárkou, * = zástupný znak)", "layers", "",
                     "Prázdné = všechny vrstvy.")


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

    def __init__(self, ctx: CheckContext, feats: list[Feature], targets: list[Feature] | None = None):
        n_checked = len(feats)
        feats = list(feats) + list(targets or [])
        self.feats = feats
        geoms = np.array([ctx.boundary(f) for f in feats], dtype=object)
        self.geoms = geoms
        self.tree = shapely.STRtree(geoms) if len(geoms) else None
        # konce se hledají jen u kontrolovaných linií (hromadně, bez procházení souřadnic po prvcích)
        idx = np.array([i for i, f in enumerate(feats[:n_checked]) if f.geom_type == GeomType.LINIE
                        and f.geometry.geom_type == "LineString"], dtype=int)
        if len(idx):
            lg = np.array([feats[i].geometry for i in idx], dtype=object)
            npts = shapely.get_num_points(lg)
            ok = npts >= 2
            idx, lg = idx[ok], lg[ok]
        if len(idx):
            a = shapely.get_coordinates(shapely.get_point(lg, 0))
            b = shapely.get_coordinates(shapely.get_point(lg, -1))
            gap = np.hypot(*(a - b).T)
            keep = gap > ctx.precision  # geometricky uzavřená linie nemá volné konce
            idx, a, b, gap = idx[keep], a[keep], b[keep], gap[keep]
            self.points = np.column_stack([a, b]).reshape(-1, 2)
            self.owner = np.repeat(idx, 2)
            self.is_end = np.tile(np.array([0, 1]), len(idx))
            self.own_gap = np.repeat(gap, 2)
        else:
            self.points = np.zeros((0, 2))
            self.owner = np.zeros(0, dtype=int)
            self.is_end = np.zeros(0, dtype=int)
            self.own_gap = np.zeros(0)
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
    out = np.empty(len(owner), dtype=object)
    empty = LineString()
    cache: dict[int, np.ndarray] = {}
    for k, (o, e) in enumerate(zip(owner, is_end)):
        g = feats[o].geometry
        if shapely.get_num_points(g) < 4:
            out[k] = empty  # bez koncového úseku zbude nejvýš jeden bod
            continue
        c = cache.get(o)
        if c is None:
            c = cache[o] = shapely.get_coordinates(g)
        part = c[:-2] if e == 1 else c[2:]
        out[k] = shapely.linestrings(part)
    return out


def _endpoint_analysis(ctx: CheckContext) -> _EndpointAnalysis:
    key = "endpoints|" + ",".join(ctx.layer_filter() or []) + f"|{ctx.tolerance}"
    if key not in ctx._cache:
        ctx._cache[key] = _EndpointAnalysis(ctx, ctx.linear(), ctx.linear_targets())
    return ctx._cache[key]


def _max_overshoot(ctx: CheckContext) -> float:
    try:
        v = ctx.config.settings("chybejici_napojeni").parametry.get("max_pretazeni", 0.5)
        return max(float(v or 0.0), ctx.tolerance)
    except (AttributeError, KeyError, TypeError, ValueError):
        return max(0.5, ctx.tolerance)


def _overshoots(ctx: CheckContext, an: _EndpointAnalysis) -> dict[int, tuple[float, tuple[float, float], int]]:
    """Přetažené konce linií (MGEO: „přetažení“).

    Konec linie, který přesahuje přes jinou linii o méně než ``max_pretazeni``: poslední úsek
    linie jinou linii protne a konec za ní „visí“. Vrací {index konce: (délka přesahu, průsečík,
    index druhé linie)}.
    """
    key = f"overshoots|{id(an)}|{_max_overshoot(ctx)}"
    if key in ctx._cache:
        return ctx._cache[key]
    from shapely.ops import substring
    out: dict[int, tuple[float, tuple[float, float], int]] = {}
    max_len = _max_overshoot(ctx)
    if an.tree is not None and len(an.points):
        lengths = shapely.length(an.geoms)
        ks, parts = [], []
        for k in range(len(an.points)):
            if an.self_touch[k]:
                continue  # (konec ležící na jiné čáře se zkoumá také – může po ní zajíždět)
            f = an.feats[an.owner[k]]
            L = float(lengths[an.owner[k]])
            if L <= ctx.precision:
                continue
            seg_len = min(max_len, L * 0.999)
            coords = f.vertices if len(f.vertices) >= 2 else list(f.geometry.coords)
            e0, e1 = (coords[-1], coords[-2]) if an.is_end[k] else (coords[0], coords[1])
            last = math.dist(e0[:2], e1[:2])
            if last >= seg_len > 0:  # koncový úsek je rovný – stačí jeho kus (bez drahého substring)
                t = seg_len / last
                a = (e0[0] + (e1[0] - e0[0]) * t, e0[1] + (e1[1] - e0[1]) * t)
                part = LineString([a, e0[:2]]) if an.is_end[k] else LineString([e0[:2], a])
            else:
                line = f.geometry
                part = substring(line, L - seg_len, L) if an.is_end[k] else substring(line, 0, seg_len)
            ks.append(k)
            parts.append(part)
        if parts:
            # jeden hromadný dotaz do prostorového indexu místo tisíců jednotlivých
            pi, gi = an.tree.query(np.array(parts, dtype=object), predicate="intersects")
            keep = gi != an.owner[np.asarray(ks)[pi]]
            best_by: dict[int, tuple] = {}
            for a_, g_ in zip(pi[keep], gi[keep]):
                k = ks[int(a_)]
                part = parts[int(a_)]
                og = an.geoms[g_]
                end_pt = an.pgeoms[k]
                eps = max(ctx.precision, 1e-4)
                if og.distance(end_pt) <= eps and og.distance(Point(part.coords[0])) <= eps and \
                        og.distance(Point(part.coords[-1])) <= eps:
                    # koncový kus leží celý na druhé čáře (překryv) – průsečíky z nepřesnosti výpočtu
                    # nejsou přetažení; společný úsek se vezme z obálky druhé čáry
                    inter = _safe_intersection(part, og.buffer(eps, cap_style="flat"))
                    cands = []
                else:
                    inter = _safe_intersection(part, og)
                    cands = list(_points_of(inter))
                # konec linie zajíždí po navazující čáře (společný úsek) – přetah je délka překryvu
                for piece in getattr(inter, "geoms", [inter]):
                    if piece.geom_type == "LineString" and piece.length > ctx.precision and \
                            piece.distance(end_pt) <= ctx.precision:
                        a, b = piece.coords[0][:2], piece.coords[-1][:2]
                        far = a if Point(a).distance(end_pt) > Point(b).distance(end_pt) else b
                        oc = list(og.coords) if og.geom_type == "LineString" else []
                        # jen když překryv končí v konci nebo lomu druhé čáry (roh) dřív než sledovaný
                        # koncový kus – ne duplicitní čáry po celé délce
                        if oc and (min(math.dist(far, oc[0][:2]), math.dist(far, oc[-1][:2])) <= eps or (
                                piece.length < part.length - eps
                                and min(math.dist(far, c[:2]) for c in oc) <= eps)):
                            cands.append(far)
                for p in cands:
                    along = part.project(Point(p))
                    dist = (part.length - along) if an.is_end[k] else along
                    if dist <= ctx.precision:
                        continue
                    cur = best_by.get(k)
                    if cur is None or dist < cur[0]:
                        best_by[k] = (dist, p, int(g_))
            for k, best in best_by.items():
                if an.pgeoms[k].distance(Point(best[1])) > ctx.precision:
                    out[k] = best
            # překryv dvou konců (každý zajíždí po druhém) je jedno přetažení – hlásit jednou
            ends = {k: an.pgeoms[k] for k in out}
            for k in sorted(out):
                if k not in out:
                    continue
                p = Point(out[k][1])
                for k2 in [k2 for k2 in out if k2 != k and ends[k2].distance(p) <= ctx.precision
                           and Point(out[k2][1]).distance(ends[k]) <= ctx.precision]:
                    del out[k2]
    ctx._cache[key] = out
    return out


def _nearest_other(an: _EndpointAnalysis, k: int) -> float | None:
    """Vzdálenost konce k nejbližší jiné čáře (pro srozumitelnější hlášku)."""
    if an.tree is None:
        return None
    idx = [i for i in an.tree.query(an.pgeoms[k], predicate="dwithin", distance=5.0) if i != an.owner[k]]
    if not idx:
        return None
    return float(np.min(shapely.distance(an.pgeoms[k], an.geoms[idx])))


def _leads_out(an: _EndpointAnalysis, k: int, reach: float, precision: float) -> bool:
    """Vede čára z tohoto konce ven z kresby? (V prodloužení čáry už nic není.)

    Kresba bývá „roztřepená“ (bloky domů, ulice), takže okraj nejde poznat jen podle obalu.
    Konec, za kterým v prodloužení čáry (±12°) až k hranici výkresu nic neleží, je okraj
    zaměřeného území – učitelova kontrola ho nepočítá.
    """
    coords = shapely.get_coordinates(an.feats[an.owner[k]].geometry)
    if an.is_end[k] == 0:
        coords = coords[::-1]
    end = coords[-1]
    prev = None
    for c in coords[-2::-1]:
        if math.dist(c, end) > precision:
            prev = c
            break
    if prev is None:
        return False
    ang = math.atan2(end[1] - prev[1], end[0] - prev[0])
    start_off = max(precision * 2, 1e-3)
    for da in (0.0, math.radians(12), -math.radians(12)):
        a = ang + da
        dx, dy = math.cos(a), math.sin(a)
        ray = LineString([(end[0] + dx * start_off, end[1] + dy * start_off),
                          (end[0] + dx * reach, end[1] + dy * reach)])
        for gi in an.tree.query(ray, predicate="intersects"):
            if gi != an.owner[k]:
                return False
    return True


@register
class VisiciKonce(Check):
    id = "visici_konce"
    nazev = "Visící konec linie"
    skupina = "Topologie"
    popis = ("Konec linie, u kterého v okruhu tolerance není žádná jiná linie (dangle). "
             "U plotů a jiných volně končících linií může být v pořádku.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [
        Param("okraj", "Nehlásit konce u okraje výkresu do [m]", "float", 1.0,
              "Volné konce čar na okrajích výkresu nejsou chybou (kresba končí na hranici území)."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        an = _endpoint_analysis(ctx)
        ctx.progress(0.3)
        over = _overshoots(ctx, an)
        ctx.progress(0.7)
        edge = float(ctx.param("okraj", 1.0))
        hull = None
        reach = 0.0
        hull_d = None
        if edge > 0 and len(an.geoms):
            hull = shapely.multipoints(shapely.get_coordinates(an.geoms)).convex_hull.boundary
            b = shapely.total_bounds(an.geoms)
            reach = math.hypot(b[2] - b[0], b[3] - b[1])
            if len(an.points):
                hull_d = shapely.distance(hull, an.pgeoms)
        cand = []
        for k in range(len(an.points)):
            if np.isfinite(an.nearest[k]) or an.self_touch[k] or an.own_gap[k] <= ctx.tolerance:
                continue  # napojeno, nebo jde o téměř uzavřený polygon (řeší jiná kontrola)
            if k in over:
                continue  # přetažená linie – hlásí kontrola nedotažení/přetažení
            if _expects_polygon(ctx, an.feats[an.owner[k]]):
                continue  # řeší kontrola nezavřených polygonů
            cand.append(k)
        for k in cand:
            f = an.feats[an.owner[k]]
            x, y = an.points[k]
            if hull is not None and (hull_d[k] <= edge or _leads_out(an, k, reach, ctx.precision)):
                # konec na okraji kresby: MGEO ho nepočítá, ale ukázat ho (aby bylo jasné, proč jinde ano)
                iss = ctx.issue(self, f, "Volný konec na okraji kresby (učitelova kontrola ho nepočítá)",
                                at=(x, y))
                iss.severity = Severity.INFO
                yield iss
                continue
            msg = "Volný konec linie uvnitř kresby"
            near = _nearest_other(an, k)
            if near is not None and near <= 0.5:
                msg += f" – nejbližší čára je {fmt_m(near)} daleko (nedotaženo?)"
            yield ctx.issue(self, f, msg, at=(x, y))


@register
class ChybejiciNapojeni(Check):
    id = "chybejici_napojeni"
    nazev = "Nedotažená / přetažená linie"
    skupina = "Topologie"
    popis = ("Konec linie není přesně napojen na jinou linii: buď k ní nedosahuje (nedotažení – konec "
             "je blíž než tolerance), nebo ji přesahuje (přetažení – linie jinou linii protne "
             "a pokračuje nejvýše o „max. přetažení“). Stejné chyby hledá MGEO při kontrole čárové kresby.")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("max_pretazeni", "Přetah / křížení do [m]", "float", 0.020,
              "Jako tolerance přetahu v MGEO (0,020 m). Delší přesah za jinou linií je křížení bez uzlu "
              "a volný konec."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        an = _endpoint_analysis(ctx)
        ctx.progress(0.3)
        over = _overshoots(ctx, an)
        ctx.progress(0.7)
        for k in range(len(an.points)):
            if an.self_touch[k]:
                continue
            f = an.feats[an.owner[k]]
            x, y = an.points[k]
            if k in over:
                dist, p, gi = over[k]
                yield ctx.issue(self, [f, an.feats[gi]], f"Přetažená linie o {fmt_m(dist)}", at=(x, y),
                                geometry=f.geometry)
                continue
            d = an.nearest[k]
            if not np.isfinite(d) or d <= ctx.precision:
                continue
            other = an.feats[an.nearest_idx[k]]
            yield ctx.issue(self, [f, other], f"Nedotažená linie, chybí {fmt_m(d)}", at=(x, y),
                            geometry=f.geometry)


@register
class Duplicity(Check):
    id = "duplicity"
    nazev = "Duplicitní prvek"
    skupina = "Topologie"
    popis = "Dva prvky se stejnou geometrií (i s opačným směrem kreslení) nebo dva body na stejném místě."
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("stejna_hladina", "Jen prvky na stejné vrstvě", "bool", True,
              "Hranice budovy a parcely se mohou legitimně krýt – proto se výchozí porovnávají jen "
              "prvky na stejné vrstvě."),
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
            elif first.dxftype == "INSERT":
                msg = f"Duplicitní značka (buňka) {first.block_name or ''} ({len(fs)}×)".replace("  ", " ")
            yield ctx.issue(self, fs, msg, geometry=first.geometry)
        # stejná čára jinak zapsaná: jiný počet lomových bodů na přímce, uzavřená čára s jiným počátkem
        # (jako modul Duplicity MGEO – geometrické porovnání, ne jen shoda souřadnic)
        hlasene = {id(f) for fs in groups.values() if len(fs) > 1 for f in fs}
        lin = [f for f in feats if f.geom_type in (GeomType.LINIE, GeomType.POLYGON) and id(f) not in hlasene]
        if len(lin) < 2:
            return
        geoms = np.array([f.geometry.boundary if f.geom_type == GeomType.POLYGON else f.geometry for f in lin],
                         dtype=object)
        eps = max(ctx.precision, 1e-4)
        tree = shapely.STRtree(geoms)
        a, b = tree.query(geoms, predicate="dwithin", distance=eps)
        m = a < b
        spojene: dict[int, set[int]] = {}
        for i, j in zip(a[m], b[m]):
            fi, fj = lin[i], lin[j]
            if same_layer and fi.layer.upper() != fj.layer.upper():
                continue
            li, lj = geoms[i].length, geoms[j].length
            if abs(li - lj) > 10 * eps or li <= 10 * eps:
                continue
            if geoms[i].hausdorff_distance(geoms[j]) <= 10 * eps:
                spojene.setdefault(i, {i}).add(j)
        videno: set[int] = set()
        for i, skup in spojene.items():
            if i in videno:
                continue
            videno |= skup
            fs = [lin[k] for k in sorted(skup)]
            yield ctx.issue(self, fs, f"Duplicitní prvek ({len(fs)}×) – stejná čára s jinými lomovými body",
                            geometry=fs[0].geometry)


@register
class PrekryvLinii(Check):
    id = "prekryv_linii"
    nazev = "Překrývající se čáry"
    skupina = "Topologie"
    popis = ("Část jedné čáry leží na jiné čáře (společný úsek) – typicky kus čáry nakreslený dvakrát nebo "
             "čára vedená po jiné. MGEO takový úsek hlásí; celé stejné čáry hlásí kontrola duplicit, krátké "
             "zajetí konce po navazující čáře kontrola přetažení.")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("stejna_hladina", "Jen čáry na stejné vrstvě", "bool", True,
              "Hranice budovy a parcely se mohou legitimně krýt – výchozí se porovnávají jen čáry na stejné vrstvě."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        same_layer = bool(ctx.param("stejna_hladina", True))
        feats = [f for f in ctx.linear() if f.geom_type == GeomType.LINIE]
        if len(feats) < 2:
            return
        geoms = np.array([f.geometry for f in feats], dtype=object)
        tree = shapely.STRtree(geoms)
        eps = max(ctx.precision, 1e-4)  # 0,1 mm – průnik čar v jedné přímce je numericky citlivý
        a, b = tree.query(geoms, predicate="dwithin", distance=eps)
        m = a < b
        a, b = a[m], b[m]
        if same_layer:
            keep = np.array([feats[i].layer == feats[j].layer for i, j in zip(a, b)], dtype=bool)
            a, b = a[keep], b[keep]
        if not len(a):
            return
        min_len = max(_max_overshoot(ctx), ctx.tolerance * 2)
        # společný úsek = část kratší čáry v pásu ±0,1 mm kolem delší (průnik linie s linií by vrátil jen bod)
        short_first = shapely.length(geoms[a]) <= shapely.length(geoms[b])
        s_idx = np.where(short_first, a, b)
        l_idx = np.where(short_first, b, a)
        inters = shapely.intersection(geoms[s_idx], shapely.buffer(geoms[l_idx], eps, cap_style="flat"))
        for i, j, g in zip(a, b, inters):
            parts = [p for p in getattr(g, "geoms", [g]) if p.geom_type in ("LineString", "MultiLineString")]
            length = sum(p.length for p in parts)
            if length <= min_len:
                continue
            gi, gj = geoms[i], geoms[j]
            if gi.hausdorff_distance(gj) <= eps * 10:
                continue  # celá duplicita – hlásí kontrola duplicit
            part = max(parts, key=lambda p: p.length)
            mid = part.interpolate(0.5, normalized=True)
            yield ctx.issue(self, [feats[i], feats[j]], f"Čáry se překrývají v délce {fmt_m(length)}",
                            at=(mid.x, mid.y), geometry=part)


_COORD_RE = re.compile(r"\[\s*([-+\d.eE]+)\s+([-+\d.eE]+)")


def _points_of(g) -> list[tuple[float, float]]:
    if g is None or g.is_empty:
        return []
    t = g.geom_type
    if t == "Point":
        return [(g.x, g.y)]
    if t in ("MultiPoint", "GeometryCollection"):
        out = []
        for part in g.geoms:
            out += _points_of(part)
        return out
    return []


def _valid(g):
    return g if g.is_valid else make_valid(g)


def _safe_intersection(g1, g2):
    try:
        return g1.intersection(g2)
    except shapely.errors.GEOSException:
        return shapely.GeometryCollection()


@register
class Samoprotnuti(Check):
    id = "samoprotnuti"
    nazev = "Samoprotnutí"
    skupina = "Topologie"
    popis = "Linie nebo polygon, který protíná sám sebe (např. „motýlek“ nebo smyčka)."
    vychozi_zavaznost = Severity.CHYBA
    parametry = [LAYERS_PARAM]

    def run(self, ctx: CheckContext):
        feats = ctx.linear()
        for i, f in enumerate(feats):
            if i % 2000 == 0:
                ctx.progress(i / max(1, len(feats)))
            g = f.geometry
            if f.geom_type == GeomType.POLYGON:
                if g.is_valid:
                    continue
                reason = shapely.is_valid_reason(g)
                m = _COORD_RE.search(reason)
                at = (float(m.group(1)), float(m.group(2))) if m else None
                if "Self-intersection" in reason or "self-intersection" in reason.lower():
                    msg = "Samoprotnutí polygonu"
                elif "Too few points" in reason:
                    msg = "Polygon má příliš málo bodů"
                else:
                    msg = "Neplatný polygon (" + reason.split("[")[0].strip() + ")"
                yield ctx.issue(self, f, msg, at=at)
            elif not g.is_simple:
                for p in self._self_crossings(g, f.closed)[:3]:
                    yield ctx.issue(self, f, "Samoprotnutí linie", at=p)

    @staticmethod
    def _self_crossings(g: LineString, closed: bool) -> list[tuple[float, float]]:
        c = np.asarray(g.coords)[:, :2]
        n = len(c) - 1
        if n < 2:
            return []
        segs = shapely.linestrings(np.stack([c[:-1], c[1:]], axis=1))
        tree = shapely.STRtree(segs)
        a, b = tree.query(segs, predicate="intersects")
        # uzavřená čára: první a poslední úsek se v počátku dotýkají legitimně (absolutní tolerance –
        # relativní by u souřadnic S-JTSK dala ~10 m a samoprotnutí mezi nimi by se ztratilo)
        closed_ring = bool(np.hypot(*(c[0] - c[-1])) <= 1e-9)
        mask = (b > a + 1) & ~((a == 0) & (b == n - 1) & closed_ring)
        pts: list[tuple[float, float]] = []
        seen = set()
        for i, j in zip(a[mask], b[mask]):
            inter = segs[i].intersection(segs[j])
            found = _points_of(inter)
            if not found and not inter.is_empty:  # překrývající se úseky
                rp = inter.representative_point()
                found = [(rp.x, rp.y)]
            for p in found:
                key = (round(p[0], 3), round(p[1], 3))
                if key not in seen:
                    seen.add(key)
                    pts.append(p)
        return pts


@register
class PrusecikyBezUzlu(Check):
    id = "pruseciky_bez_uzlu"
    nazev = "Průsečík bez uzlu"
    skupina = "Topologie"
    popis = ("Místo, kde se dvě linie kříží nebo kde linie končí na jiné linii, ale v tomto místě "
             "není lomový bod (uzel) na obou liniích.")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("napojeni_bez_uzlu", "Hlásit i napojení (T-spoj) bez uzlu", "bool", False,
              "Konec linie leží na jiné linii, ta ale v tom místě nemá lomový bod."),
        Param("vyzadovat_rozdeleni", "Linie musí být v uzlu (křížení) rozdělené", "bool", True,
              "Jako topologická kontrola MGEO („nerozdělená čára v uzlovém bodě“): kříží-li se dvě linie "
              "ve společném lomovém bodě, musí v něm obě končit. T-spojení se dělit nemusí."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        report_t = bool(ctx.param("napojeni_bez_uzlu", True))
        split = bool(ctx.param("vyzadovat_rozdeleni", False))
        feats = ctx.linear()
        if len(feats) < 2:
            return
        geoms = np.array([ctx.boundary(f) for f in feats], dtype=object)
        verts = [np.asarray(f.vertices, dtype=float).reshape(-1, 2) for f in feats]
        tree = shapely.STRtree(geoms)
        a, b = tree.query(geoms, predicate="intersects")
        mask = a < b
        a, b = a[mask], b[mask]
        eps = max(ctx.precision, 1e-6)
        seen: set[tuple[float, float]] = set()
        # průsečík u přetažené linie hlásí kontrola nedotažení/přetažení – nehlásit dvakrát
        for _, p, _ in _overshoots(ctx, _endpoint_analysis(ctx)).values():
            seen.add((round(p[0], 3), round(p[1], 3)))

        def has_vertex(k: int, p) -> bool:
            v = verts[k]
            if not len(v):
                return False
            return bool(np.min(np.hypot(v[:, 0] - p[0], v[:, 1] - p[1])) <= eps)

        def is_end(k: int, p) -> bool:
            f = feats[k]
            if f.geom_type != GeomType.LINIE:
                return False
            c = f.geometry.coords
            return math.dist(c[0][:2], p) <= eps or math.dist(c[-1][:2], p) <= eps

        # průniky počítáme vektorově po dávkách; úsekové (liniové) průniky sdílených hran přeskočíme
        total = max(1, len(a))
        step = 20000
        inters = np.empty(0, dtype=object)
        keep_a, keep_b = [], []
        for s in range(0, len(a), step):
            ctx.progress(0.8 * s / total)
            try:
                chunk = shapely.intersection(geoms[a[s:s + step]], geoms[b[s:s + step]])
            except shapely.errors.GEOSException:
                chunk = np.array([_safe_intersection(geoms[i], geoms[j])
                                  for i, j in zip(a[s:s + step], b[s:s + step])], dtype=object)
            types = shapely.get_type_id(chunk)
            m = np.isin(types, (0, 4, 7))  # Point, MultiPoint, GeometryCollection
            inters = np.concatenate([inters, chunk[m]])
            keep_a.append(a[s:s + step][m])
            keep_b.append(b[s:s + step][m])
        a = np.concatenate(keep_a) if keep_a else a[:0]
        b = np.concatenate(keep_b) if keep_b else b[:0]
        ov_eps = max(ctx.precision, 1e-4)

        def overlapping(i: int, j: int, p) -> bool:
            """Leží čáry u bodu po sobě (překryv)? To hlásí kontrola překryvu, ne průsečík."""
            r = 0.05
            try:
                near = geoms[i].intersection(Point(p).buffer(r))
                on = near.intersection(geoms[j].buffer(ov_eps, cap_style="flat"))
            except shapely.errors.GEOSException:
                return False
            return on.length >= 0.4 * r

        for i, j, inter in zip(a, b, inters):
            for p in _points_of(inter):
                vi, vj = has_vertex(i, p), has_vertex(j, p)
                key = (round(p[0], 3), round(p[1], 3))
                if key not in seen and overlapping(i, j, p):
                    seen.add(key)
                    continue
                if vi and vj:
                    # MGEO-styl: linie mají být v uzlu rozdělené (končit v něm), ne jen mít lomový bod
                    # (T-spojení, kde jedna linie v uzlu končí, se podle zadání dělit nemusí)
                    if split and key not in seen and feats[i].geom_type == GeomType.LINIE \
                            and feats[j].geom_type == GeomType.LINIE and not is_end(i, p) and not is_end(j, p):
                        seen.add(key)
                        yield ctx.issue(self, [feats[i], feats[j]], "Linie nejsou v uzlu rozdělené", at=p,
                                        geometry=Point(p).buffer(0.01))
                    continue
                if key in seen:
                    continue
                if is_end(i, p) or is_end(j, p):
                    if not report_t:
                        continue
                    msg = "Napojení na linii bez uzlu"
                else:
                    msg = "Průsečík linií bez uzlu"
                seen.add(key)
                yield ctx.issue(self, [feats[i], feats[j]], msg, at=p, geometry=Point(p).buffer(0.01))


@register
class NulovaDelka(Check):
    id = "nulova_delka"
    nazev = "Prvek nulové délky"
    skupina = "Topologie"
    popis = "Linie nulové délky, polygon s nulovou plochou, kružnice s nulovým poloměrem, prázdný text nebo text s nulovou výškou."
    vychozi_zavaznost = Severity.CHYBA
    parametry = [LAYERS_PARAM]

    def run(self, ctx: CheckContext):
        eps = max(ctx.precision, 1e-9)
        feats = ctx.features(ctx.layer_filter())
        # hladiny, kde úsečky nulové délky tvoří většinu prvků = záměrné body (MicroStation „aktivní bod“)
        per_layer: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for f in feats:
            per_layer[f.layer][0] += 1
            per_layer[f.layer][1] += int(f.zero_length)
        point_layers = {k for k, (n, z) in per_layer.items() if n >= 5 and z / n >= 0.8}
        for f in feats:
            g = f.geometry
            if f.zero_length:
                r = ctx.rule_for(f)
                intended = (r is not None and r.geometrie == GeomType.BOD) \
                    or ((r is None or r.geometrie is None) and f.layer in point_layers)
                if not intended:
                    yield ctx.issue(self, f, "Linie nulové délky")
                continue
            if f.geom_type == GeomType.LINIE:
                if g.is_empty or g.length <= eps:
                    yield ctx.issue(self, f, "Linie nulové délky")
            elif f.geom_type == GeomType.POLYGON:
                # neplatný polygon („motýlek“) může mít nulovou plochu – ten hlásí kontrola samoprotnutí
                if g.is_empty or g.length <= eps or (g.is_valid and g.area <= eps * eps * 10):
                    yield ctx.issue(self, f, "Polygon s nulovou plochou")
            elif f.geom_type == GeomType.TEXT:
                if not (f.text or "").strip():
                    yield ctx.issue(self, f, "Prázdný text")
                elif f.dxftype in ("TEXT", "MTEXT") and f.text_height <= 0:
                    yield ctx.issue(self, f, f"Text „{f.text.strip()[:20]}“ má nulovou výšku (není vidět)")
            elif f.dxftype == "CIRCLE" and f.radius <= eps:
                yield ctx.issue(self, f, "Kružnice s nulovým poloměrem")
            elif f.dxftype == "INSERT" and (abs(f.scale[0]) <= 1e-12 or abs(f.scale[1]) <= 1e-12):
                yield ctx.issue(self, f, f"Buňka {f.block_name} s nulovým měřítkem")


@register
class KratkeLinie(Check):
    id = "kratke_linie"
    nazev = "Krátká linie nebo úsek"
    skupina = "Topologie"
    popis = ("Linie kratší než zadaná délka (často zbytek po editaci) a úsek mezi dvěma lomovými body "
             "kratší než zadaná délka (téměř totožné vrcholy). Odpovídá „krátkým liniím“ v MGEO.")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("min_delka", "Min. délka linie [m]", "float", 0.090,
              "Jako tolerance krátké čáry v MGEO (0,090 m)."),
        Param("min_usek", "Min. délka úseku [m]", "float", 0.005,
              "0 = úseky nekontrolovat. Oblouky nahrazené lomenou čarou se nekontrolují."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        min_len = float(ctx.param("min_delka", 0.05))
        min_seg = float(ctx.param("min_usek", 0.005))
        feats = ctx.linear()
        for n, f in enumerate(feats):
            if n % 5000 == 0:
                ctx.progress(n / max(1, len(feats)))
            length = f.geometry.length
            if length <= ctx.precision:
                continue  # nulová délka – hlásí jiná kontrola
            if f.geom_type == GeomType.LINIE and length < min_len:
                yield ctx.issue(self, f, f"Krátká linie, délka {fmt_m(length)}")
                continue
            if min_seg <= 0 or len(f.vertices) < 2:
                continue
            v = np.asarray(f.vertices, dtype=float)
            if f.closed and len(v) > 2:
                v = np.vstack([v, v[:1]])
            seg = np.hypot(np.diff(v[:, 0]), np.diff(v[:, 1]))
            bad = np.nonzero((seg > ctx.precision) & (seg < min_seg))[0]
            for k in bad[:3]:
                mid = ((v[k, 0] + v[k + 1, 0]) / 2, (v[k, 1] + v[k + 1, 1]) / 2)
                yield ctx.issue(self, f, f"Krátký úsek linie, délka {fmt_m(float(seg[k]))}", at=mid)


def _polygons_by_layer(ctx: CheckContext, same_layer: bool) -> dict[str, list[tuple[Feature, object]]]:
    groups: dict[str, list[tuple[Feature, object]]] = defaultdict(list)
    for f in ctx.features(ctx.layer_filter()):
        if f.geom_type != GeomType.POLYGON or f.dxftype == "HATCH" or f.geometry.is_empty:
            continue
        g = _valid(f.geometry)
        if g.area <= 0:
            continue
        groups[f.layer.upper() if same_layer else ""].append((f, g))
    return groups


@register
class PrekryvyPolygonu(Check):
    id = "prekryvy_polygonu"
    nazev = "Překryv polygonů"
    skupina = "Topologie"
    popis = "Dva polygony (výchozí na stejné vrstvě) se částečně nebo úplně překrývají."
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("min_plocha", "Hlásit od plochy [m²]", "float", 0.001),
        Param("stejna_hladina", "Jen polygony na stejné vrstvě", "bool", True,
              "Budova uvnitř parcely se nehlásí, protože leží na jiné vrstvě."),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        min_area = float(ctx.param("min_plocha", 0.001))
        groups = _polygons_by_layer(ctx, bool(ctx.param("stejna_hladina", True)))
        for gi, items in enumerate(groups.values()):
            ctx.progress(gi / max(1, len(groups)))
            if len(items) < 2:
                continue
            geoms = np.array([g for _, g in items], dtype=object)
            tree = shapely.STRtree(geoms)
            a, b = tree.query(geoms, predicate="intersects")
            m = a < b
            a, b = a[m], b[m]
            if not len(a):
                continue
            try:
                inters = shapely.intersection(geoms[a], geoms[b])
            except shapely.errors.GEOSException:
                inters = np.array([_safe_intersection(geoms[i], geoms[j]) for i, j in zip(a, b)], dtype=object)
            areas = shapely.area(inters)
            sel = areas > min_area
            for i, j, inter, area in zip(a[sel], b[sel], inters[sel], areas[sel]):
                yield ctx.issue(self, [items[i][0], items[j][0]],
                                f"Překryv polygonů, plocha {fmt_num(area, 3)} m²", at=inter, geometry=inter)


@register
class MezeryPolygonu(Check):
    id = "mezery_polygonu"
    nazev = "Mezera mezi polygony"
    skupina = "Topologie"
    popis = ("Úzká mezera (štěrbina) mezi sousedními polygony na stejné vrstvě nebo malá díra, "
             "kterou polygony neuzavírají – typicky nepřesně navazující parcely.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [
        Param("max_sirka", "Max. šířka mezery [m]", "float", 0.1),
        Param("max_plocha_diry", "Hlásit díry do plochy [m²]", "float", 0.5),
        Param("min_plocha", "Ignorovat mezery menší než [m²]", "float", 0.00001),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        w = float(ctx.param("max_sirka", 0.1))
        max_hole = float(ctx.param("max_plocha_diry", 0.5))
        min_area = float(ctx.param("min_plocha", 0.00001))
        groups = _polygons_by_layer(ctx, True)
        for gi, (layer, items) in enumerate(groups.items()):
            ctx.progress(gi / max(1, len(groups)))
            if len(items) < 2:
                continue
            geoms_arr = np.array([g for _, g in items], dtype=object)
            union = shapely.union_all(geoms_arr)
            gaps = []
            if w > 0:
                # štěrbina může vzniknout jen mezi polygony, které mají souseda blíž než w – osamocené
                # (např. jednotlivé budovy) se do drahého „uzavření“ bufferem vůbec nedávají
                ta, tb = shapely.STRtree(geoms_arr).query(geoms_arr, predicate="dwithin", distance=w)
                near_idx = np.unique(np.concatenate([ta[ta != tb], tb[ta != tb]]))
                if len(near_idx):
                    part = shapely.union_all(geoms_arr[near_idx])
                    closed = part.buffer(w / 2, join_style="mitre", mitre_limit=5).buffer(
                        -w / 2, join_style="mitre", mitre_limit=5)
                    diff = closed.difference(part)
                    gaps += list(getattr(diff, "geoms", [diff]))
            polys = getattr(union, "geoms", [union])
            for p in polys:
                for ring in getattr(p, "interiors", []):
                    hole = shapely.Polygon(ring)
                    if hole.area <= max_hole:
                        gaps.append(hole)
            seen = set()
            feats = [f for f, _ in items]
            tree = shapely.STRtree(np.array([g for _, g in items], dtype=object))
            for gap in gaps:
                if gap.is_empty or gap.area <= min_area:
                    continue
                c = gap.representative_point()
                key = (round(c.x, 2), round(c.y, 2))
                if key in seen:
                    continue
                seen.add(key)
                width = 2 * gap.area / gap.length if gap.length else 0
                near = [feats[k] for k in tree.query(gap, predicate="dwithin", distance=w)][:4]
                yield ctx.issue(self, near or feats[:1],
                                f"Mezera mezi polygony, šířka {fmt_m(width)}", at=c, geometry=gap)


@register
class MimoRozsah(Check):
    id = "mimo_rozsah"
    nazev = "Prvek mimo rozsah"
    skupina = "Topologie"
    popis = ("Prvek leží mimo definovaný rozsah výkresu (obdélník z nastavení nebo území ČR v S-JTSK). "
             "Rozsah se nastavuje v Nastavení kontrol → Obecné, nebo v YAML (rozsah).")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [LAYERS_PARAM]

    SJTSK = [(-905000.0, -1230000.0, -430000.0, -935000.0), (430000.0, 935000.0, 905000.0, 1230000.0)]

    def run(self, ctx: CheckContext):
        r = ctx.rules.rozsah
        if not r:
            ctx.notes.append("rozsah výkresu není nastaven – kontrola přeskočena.")
            return
        if isinstance(r, str) and r.lower() in ("sjtsk", "s-jtsk", "cr", "čr"):
            boxes = [shapely.box(*b) for b in self.SJTSK]
            name = "území ČR v S-JTSK"
        else:
            try:
                boxes = [shapely.box(float(r["xmin"]), float(r["ymin"]), float(r["xmax"]), float(r["ymax"]))]
            except (KeyError, TypeError, ValueError):
                ctx.notes.append("rozsah výkresu má neplatný formát (čekám xmin, ymin, xmax, ymax).")
                return
            name = "rozsah výkresu"
        area = shapely.union_all(boxes)
        for f in ctx.features(ctx.layer_filter()):
            g = f.geometry
            if g is None or g.is_empty or area.contains(g):
                continue
            if area.intersects(g):
                yield ctx.issue(self, f, f"Prvek zasahuje mimo {name}")
            else:
                yield ctx.issue(self, f, f"Prvek mimo {name} ({fmt_num(area.distance(g), 1)} m od hranice)")


@register
class BodyBlizko(Check):
    id = "body_blizko"
    nazev = "Body téměř na sobě"
    skupina = "Topologie"
    popis = ("Dva body (body, buňky, kružnice) jsou blíž než tolerance, ale nejsou totožné – "
             "obvykle omylem dvakrát zaměřený nebo posunutý bod.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [
        Param("stejna_hladina", "Jen body na stejné vrstvě", "bool", False),
        LAYERS_PARAM,
    ]

    def run(self, ctx: CheckContext):
        same = bool(ctx.param("stejna_hladina", False))
        feats = [f for f in ctx.features(ctx.layer_filter()) if f.geom_type == GeomType.BOD]
        if len(feats) < 2:
            return
        pts = np.array([f.geometry for f in feats], dtype=object)
        tree = shapely.STRtree(pts)
        a, b = tree.query(pts, predicate="dwithin", distance=ctx.tolerance)
        mask = a < b
        a, b = a[mask], b[mask]
        if not len(a):
            return
        d = shapely.distance(pts[a], pts[b])
        # jedna chyba na dvojici poloh – bod, jeho číslo, buňka… na stejném místě se nehlásí vícekrát
        groups: dict[tuple, tuple[list[Feature], float]] = {}
        for i, j, dist in zip(a, b, d):
            if dist <= ctx.precision:
                continue
            fi, fj = feats[i], feats[j]
            if same and fi.layer != fj.layer:
                continue
            q = max(ctx.precision, 1e-6)
            key = tuple(sorted(((round(f.geometry.x / q), round(f.geometry.y / q)) for f in (fi, fj))))
            fl, _ = groups.setdefault(key, ([], dist))
            for f in (fi, fj):
                if all(x.fid != f.fid for x in fl):
                    fl.append(f)
        for fl, dist in groups.values():
            fi = fl[0]
            fj = next(f for f in fl[1:] if f.geometry.distance(fi.geometry) > ctx.precision)
            mid = ((fi.geometry.x + fj.geometry.x) / 2, (fi.geometry.y + fj.geometry.y) / 2)
            yield ctx.issue(self, fl, f"Body téměř na sobě, vzdálenost {fmt_m(dist)}", at=mid,
                            geometry=LineString([fi.geometry, fj.geometry]))
