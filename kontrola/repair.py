"""Automatická oprava výkresu (obdoba režimu „oprava“ v MGEO).

Oprava se nikdy neukládá do původního souboru – vznikne nový DXF, který si uživatel
prohlédne a znovu zkontroluje. Opravují se jen jednoznačné chyby v toleranci:

* duplicitní prvky (ponechá se první),
* linie nulové délky (smažou se),
* téměř uzavřené polygony (mezera do tolerance → uzavření),
* nedotažené linie (konec se přitáhne na nejbližší bod / lomový bod druhé linie),
* přetažené linie (konec se zkrátí na průsečík),
* do cílové linie se v místě napojení vloží lomový bod (uzel),
* volitelně: vrstva, barva a styl čáry podle pravidla.

Upravují se entity LINE a LWPOLYLINE, ostatní typy se jen vypíšou jako neopravitelné.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
import numpy as np
from shapely.geometry import Point

from .checks.base import CheckContext
from .config import Config
from .model import Drawing, GeomType
from .rules import RuleSet, color_rgb


@dataclass
class RepairOptions:
    duplicity: bool = True
    nulova_delka: bool = True
    uzavrit_polygony: bool = True
    nedotazeni: bool = True
    pretazeni: bool = True
    vlozit_uzly: bool = True
    symbologie: bool = False

    LABELS = {
        "duplicity": "Smazat duplicitní prvky",
        "nulova_delka": "Smazat linie nulové délky",
        "uzavrit_polygony": "Uzavřít téměř uzavřené polygony (mezera do tolerance)",
        "nedotazeni": "Dotáhnout nedotažené linie",
        "pretazeni": "Zkrátit přetažené linie",
        "vlozit_uzly": "Vložit uzly do křížení (a do T-napojení, jen když je hlásíte v nastavení)",
        "symbologie": "Sjednotit vrstvu, barvu a styl podle pravidel",
    }


@dataclass
class RepairReport:
    path: str = ""
    counts: Counter = field(default_factory=Counter)
    details: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def text(self) -> str:
        if not self.total:
            lines = ["Nebylo co automaticky opravit."]
        else:
            lines = [f"Provedeno oprav: {self.total}"]
            lines += [f"  • {k}: {v}" for k, v in self.counts.items()]
        if self.skipped:
            lines.append(f"Nelze opravit automaticky: {len(self.skipped)} (opravte ručně v MicroStationu)")
        return "\n".join(lines)


class _Doc:
    """Pomocník pro úpravy entit v jednotkách výkresu."""

    def __init__(self, drawing: Drawing):
        try:
            self.doc = ezdxf.readfile(drawing.path)
        except Exception:
            from ezdxf import recover
            self.doc, _ = recover.readfile(drawing.path)
        self.msp = self.doc.modelspace()
        self.f = drawing.unit_factor or 1.0
        self.deleted: set[str] = set()

    def entity(self, handle: str):
        if not handle or handle in self.deleted:
            return None
        e = self.doc.entitydb.get(handle)
        if e is not None and e.dxftype() == "LWPOLYLINE":
            ex = e.dxf.get("extrusion", (0, 0, 1))
            if abs(ex[0]) > 1e-12 or abs(ex[1]) > 1e-12 or ex[2] < 0:
                return None  # lomená čára v obecné rovině (3D) – souřadnice nejsou v rovině XY, neopravuje se
        return e

    def delete(self, handle: str) -> bool:
        e = self.entity(handle)
        if e is None:
            return False
        self.msp.delete_entity(e)
        self.deleted.add(handle)
        return True

    def to_du(self, p) -> tuple[float, float]:
        return (p[0] / self.f, p[1] / self.f)

    def move_end(self, handle: str, is_end: bool, p) -> bool:
        e = self.entity(handle)
        if e is None:
            return False
        x, y = self.to_du(p)
        t = e.dxftype()
        if t == "LINE":
            attr = "end" if is_end else "start"
            z = e.dxf.get(attr)[2] if len(e.dxf.get(attr)) > 2 else 0.0
            e.dxf.set(attr, (x, y, z))
            return True
        if t == "LWPOLYLINE":
            pts = list(e.get_points("xyseb"))
            if not pts:
                return False
            k = len(pts) - 1 if is_end else 0
            pts[k] = (x, y, *pts[k][2:])
            e.set_points(pts, format="xyseb")
            return True
        return False

    def filter_short(self, handle: str, points, min_seg: float):
        """Body, jejichž vložení by vytvořilo úsek kratší než ``min_seg`` (učitel by hlásil krátkou čáru)."""
        e = self.entity(handle)
        if e is None or min_seg <= 0:
            return list(points), []
        if e.dxftype() == "LINE":
            verts = [tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]]
        elif e.dxftype() == "LWPOLYLINE":
            verts = [p[:2] for p in e.get_points("xy")]
        else:
            return list(points), []
        verts = [(v[0] * self.f, v[1] * self.f) for v in verts]
        ok, bad = [], []
        for p in sorted(set(map(tuple, points))):
            near = min((math.dist(p, v) for v in verts + ok), default=math.inf)
            (bad if near < min_seg else ok).append(p)
        return ok, bad

    def split_line(self, handle: str, points: list[tuple[float, float]]) -> int:
        """Rozdělí úsečku (LINE) v zadaných bodech na více úseček se stejnými vlastnostmi."""
        e = self.entity(handle)
        if e is None or e.dxftype() != "LINE":
            return 0
        s, t = e.dxf.start, e.dxf.end
        dx, dy = t[0] - s[0], t[1] - s[1]
        L2 = dx * dx + dy * dy
        if L2 <= 0:
            return 0
        params = set()
        for p in points:
            x, y = self.to_du(p)
            u = ((x - s[0]) * dx + (y - s[1]) * dy) / L2
            if 1e-9 < u < 1 - 1e-9:
                params.add(round(u, 12))
        if not params:
            return 0
        cuts = [0.0] + sorted(params) + [1.0]
        attribs = e.dxfattribs(drop={"handle", "owner", "start", "end"})
        z = s[2] if len(s) > 2 else 0.0
        for a, b in zip(cuts[:-1], cuts[1:]):
            self.msp.add_line((s[0] + a * dx, s[1] + a * dy, z), (s[0] + b * dx, s[1] + b * dy, z),
                              dxfattribs=attribs)
        self.delete(handle)
        return len(params)

    def insert_vertices(self, handle: str, points: list[tuple[float, float]], eps: float) -> int:
        """Vloží lomové body do LWPOLYLINE na úseky, na kterých leží (bez oblouků)."""
        e = self.entity(handle)
        if e is None or e.dxftype() != "LWPOLYLINE":
            return 0
        pts = list(e.get_points("xyseb"))
        closed = bool(e.closed)
        n_added = 0
        for p in points:
            x, y = self.to_du(p)
            n = len(pts)
            segs = range(n if closed else n - 1)
            best = None
            for i in segs:
                a, b = pts[i], pts[(i + 1) % n]
                if abs(a[4]) > 1e-12:
                    continue  # oblouk
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                if L2 <= 0:
                    continue
                t = ((x - a[0]) * dx + (y - a[1]) * dy) / L2
                if t <= 1e-9 or t >= 1 - 1e-9:
                    continue
                d = math.hypot(a[0] + t * dx - x, a[1] + t * dy - y)
                if d <= eps / self.f and (best is None or d < best[0]):
                    best = (d, i)
            if best is None:
                continue
            i = best[1]
            pts.insert(i + 1, (x, y, pts[i][2], pts[i][3], 0.0))
            n_added += 1
        if n_added:
            e.set_points(pts, format="xyseb")
            e.closed = closed
        return n_added


def _param(check_id: str, name: str, default, config: Config):
    from .checks.base import REGISTRY
    v = config.settings(check_id).parametry.get(name)
    if v is None:
        cls = REGISTRY.get(check_id)
        v = next((p.default for p in getattr(cls, "parametry", []) if p.name == name), default)
    return v


def _explode_references(drawing: Drawing, out_path: Path) -> Drawing:
    """Rozbalí referenční výkresy (bloky s celou kresbou) do modelového prostoru a výkres znovu načte."""
    import tempfile

    from .io.dxf_loader import load_drawing, read_dxf
    try:
        doc = ezdxf.readfile(drawing.path)
    except Exception:
        from ezdxf import recover
        doc, _ = recover.readfile(drawing.path)
    msp = doc.modelspace()
    for ins in [e for e in msp if e.dxftype() == "INSERT"]:
        block = doc.blocks.get(ins.dxf.name)
        if block is None:
            continue
        ents = list(block)
        layers = {be.dxf.get("layer", "0") for be in ents} - {"0"}
        if block.block.dxf.get("flags", 0) & (4 | 8) or (len(ents) >= 30 and len(layers) >= 3):
            try:
                ins.explode()
            except Exception:  # noqa: BLE001
                continue
    tmp = Path(tempfile.mkdtemp(prefix="kontrola_oprava_")) / (Path(drawing.path).stem + "_rozbaleno.dxf")
    doc.saveas(tmp)
    d = read_dxf(tmp) if tmp.suffix.lower() == ".dxf" else load_drawing(tmp)
    return d


def repair_drawing(drawing: Drawing, rules: RuleSet | None, config: Config, out_path: str | Path,
                   options: RepairOptions | None = None) -> RepairReport:
    from .checks.topology import _endpoint_analysis, _overshoots
    from .runner import run_checks

    opts = options or RepairOptions()
    rules = rules or RuleSet()
    out_path = Path(out_path)
    if out_path.resolve() == Path(drawing.path).resolve():
        raise ValueError("Opravený výkres se musí uložit do nového souboru.")
    rep = RepairReport(path=str(out_path))
    if any(not f.handle for f in drawing.features if f.geom_type in (GeomType.LINIE, GeomType.POLYGON)):
        # kresba je v referenčním výkresu (bloku) – pro úpravy se reference rozbalí do výkresu
        drawing = _explode_references(drawing, out_path)
        rep.details.append("Referenční výkres byl v opraveném souboru rozbalen přímo do výkresu.")
    min_seg = _param("kratke_linie", "min_delka", 0.09, config)
    t_nodes = bool(_param("pruseciky_bez_uzlu", "napojeni_bez_uzlu", False, config))
    D = _Doc(drawing)
    tol, eps = config.tolerance, max(config.presnost, 1e-6)
    by_id = drawing.by_id()

    def fname(f) -> str:
        return f"{f.dxftype} #{f.handle} ({f.layer})"

    # 1) duplicity a nulové délky
    wanted = [c for c, on in (("duplicity", opts.duplicity), ("nulova_delka", opts.nulova_delka)) if on]
    if wanted:
        res = run_checks(drawing, rules, config, only=wanted)
        for iss in res.issues:
            if iss.check_id == "duplicity":
                for h in iss.handles[1:]:
                    if D.delete(h):
                        rep.counts["Smazané duplicity"] += 1
            elif iss.check_id == "nulova_delka" and iss.message.startswith("Linie nulové"):
                for h in iss.handles:
                    if D.delete(h):
                        rep.counts["Smazané linie nulové délky"] += 1

    # 2) nedotažení / přetažení
    ctx = CheckContext(drawing, rules, config, config.settings("chybejici_napojeni").parametry)
    moved: set[tuple[str, int]] = set()
    inserts: dict[str, list[tuple[float, float]]] = defaultdict(list)
    if opts.nedotazeni or opts.pretazeni:
        an = _endpoint_analysis(ctx)
        over = _overshoots(ctx, an)
        for k in range(len(an.points)):
            f = an.feats[an.owner[k]]
            if an.self_touch[k] or f.handle in D.deleted or an.own_gap[k] <= tol:
                continue  # téměř uzavřený polygon se uzavírá v kroku 3
            if k in over and opts.pretazeni:
                dist, p, gi = over[k]
                target = an.feats[gi]
                new = p
                label = "Zkrácené přetažené linie"
            elif k not in over and opts.nedotazeni and np.isfinite(an.nearest[k]) \
                    and eps < an.nearest[k] <= tol:
                target = an.feats[an.nearest_idx[k]]
                tg = an.geoms[an.nearest_idx[k]]
                end = Point(an.points[k])
                v = np.asarray(target.vertices, dtype=float).reshape(-1, 2)
                dv = np.hypot(v[:, 0] - end.x, v[:, 1] - end.y) if len(v) else np.array([])
                if len(dv) and dv.min() <= tol:
                    new = tuple(v[int(dv.argmin())])  # přednostně na existující lomový bod
                else:
                    q = tg.interpolate(tg.project(end))
                    new = (q.x, q.y)
                label = "Dotažené linie"
            else:
                continue
            key = (f.handle, int(an.is_end[k]))
            if key in moved:
                continue
            if D.move_end(f.handle, bool(an.is_end[k]), new):
                moved.add(key)
                rep.counts[label] += 1
                rep.details.append(f"{label}: {fname(f)} → {new[0]:.3f}, {new[1]:.3f}")
                if opts.vlozit_uzly and t_nodes:
                    # uzel do všech linií, které místem procházejí (např. sdílená hranice dvou parcel)
                    for gi in an.tree.query(Point(new), predicate="dwithin", distance=eps * 10):
                        other = an.feats[int(gi)]
                        if other.handle == f.handle or not other.handle:
                            continue
                        tv = np.asarray(other.vertices, dtype=float).reshape(-1, 2)
                        if len(tv) and np.hypot(tv[:, 0] - new[0], tv[:, 1] - new[1]).min() <= eps:
                            continue
                        inserts[other.handle].append(new)
            else:
                rep.skipped.append(f"Konec linie {fname(f)} – typ {f.dxftype} nelze upravit automaticky")
    # 2b) uzly do průsečíků a T-napojení bez uzlu
    if opts.vlozit_uzly:
        res = run_checks(drawing, rules, config, only=["pruseciky_bez_uzlu"])
        for iss in res.issues:
            if iss.message.startswith("Linie nejsou v uzlu rozdělené"):
                continue
            p = (iss.x, iss.y)
            for fid in iss.feature_ids:
                f = by_id.get(fid)
                if f is None or f.handle in D.deleted:
                    continue
                tv = np.asarray(f.vertices, dtype=float).reshape(-1, 2)
                if len(tv) and np.hypot(tv[:, 0] - p[0], tv[:, 1] - p[1]).min() <= eps:
                    continue
                inserts[f.handle].append(p)
    if inserts:
        for h, pts in inserts.items():
            ent = D.entity(h)
            ok_pts, short = D.filter_short(h, pts, min_seg)
            for p in short:
                rep.skipped.append(f"Uzel v bodě {p[0]:.3f}, {p[1]:.3f} by vytvořil úsek kratší než "
                                   f"{min_seg:.2f} m – opravte ručně (posuňte lomový bod)")
            pts = ok_pts
            if not pts:
                continue
            if ent is not None and ent.dxftype() == "LINE":
                n = D.split_line(h, pts)
                if n:
                    rep.counts["Vložené uzly"] += n
                continue
            n = D.insert_vertices(h, pts, max(tol, eps * 10))
            if n:
                rep.counts["Vložené uzly"] += n
            if n < len(pts):
                ent = D.entity(h)
                rep.skipped.append(f"Uzel do prvku #{h} ({ent.dxftype() if ent else '?'}) se nepodařilo "
                                   f"vložit ({len(pts) - n}×)")

    # 3) téměř uzavřené polygony
    if opts.uzavrit_polygony:
        res = run_checks(drawing, rules, config, only=["nezavrene_polygony"])
        for iss in res.issues:
            for fid in iss.feature_ids:
                f = by_id.get(fid)
                if f is None or f.handle in D.deleted:
                    continue
                e = D.entity(f.handle)
                coords = list(f.geometry.coords)
                gap = math.dist(coords[0][:2], coords[-1][:2]) if coords else math.inf
                if e is None or e.dxftype() != "LWPOLYLINE" or gap > tol:
                    rep.skipped.append(f"{iss.message}: {fname(f)} – mezera větší než tolerance "
                                       f"nebo nepodporovaný typ")
                    continue
                pts = list(e.get_points("xyseb"))
                if len(pts) >= 4:
                    pts = pts[:-1]  # poslední bod leží (téměř) na prvním
                    e.set_points(pts, format="xyseb")
                e.closed = True
                rep.counts["Uzavřené polygony"] += 1

    # 4) symbologie podle pravidel
    if opts.symbologie and rules.pravidla:
        res = run_checks(drawing, rules, config, only=["symbologie"])
        for iss in res.issues:
            f = by_id.get(iss.feature_ids[0]) if iss.feature_ids else None
            if f is None:
                continue
            e = D.entity(f.handle)
            r = ctx.rule_for(f)
            if e is None or r is None:
                continue
            if r.hladina and not any(c in r.hladina for c in "*?["):
                if r.hladina not in D.doc.layers:
                    D.doc.layers.add(r.hladina)
                e.dxf.layer = r.hladina
            if r.barva is not None:
                rgb = color_rgb(r.barva, rules.paleta, rules.barevna_tabulka)
                if rules.paleta == "autocad" and isinstance(r.barva, int):
                    e.dxf.color = r.barva
                elif rgb is not None:
                    e.rgb = rgb
            if r.styl_cary and f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
                lt = "CONTINUOUS" if r.styl_cary.upper() in ("CONTINUOUS", "0") else r.styl_cary.upper()
                if lt in D.doc.linetypes:
                    e.dxf.linetype = lt
            rep.counts["Sjednocená symbologie"] += 1

    D.doc.saveas(out_path)
    return rep
