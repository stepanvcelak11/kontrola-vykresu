"""Automatická oprava výkresu (obdoba režimu „oprava“ v MGEO).

Oprava se nikdy neukládá do původního souboru – vznikne nový DXF, který si uživatel
prohlédne a znovu zkontroluje. Opravují se jen jednoznačné chyby v toleranci:

* duplicitní prvky (ponechá se první),
* linie nulové délky (smažou se),
* téměř uzavřené polygony (mezera do tolerance → uzavření),
* nedotažené linie (konec se přitáhne na nejbližší bod / lomový bod druhé linie),
* přetažené linie (konec se zkrátí na průsečík),
* do cílové linie se v místě napojení vloží lomový bod (uzel),
* atributy podle pravidla: vrstva, barva, styl a měřítko stylu, tloušťka, výška/šířka/zarovnání a písmo textu.

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
    rozdelit_v_uzlu: bool = True
    kratke_useky: bool = True
    prichytit_vrcholy: bool = True
    body_na_sobe: bool = True
    presun_vrstvy: bool = False
    symbologie: bool = True

    LABELS = {
        "duplicity": "Smazat duplicitní prvky",
        "nulova_delka": "Smazat linie nulové délky",
        "uzavrit_polygony": "Uzavřít téměř uzavřené polygony (mezera do tolerance)",
        "nedotazeni": "Dotáhnout nedotažené linie",
        "pretazeni": "Zkrátit přetažené linie",
        "vlozit_uzly": "Vložit uzly do křížení (a do T-napojení, jen když je hlásíte v nastavení)",
        "rozdelit_v_uzlu": "Rozdělit linie v uzlu, kde se kříží ve společném lomovém bodě (MGEO)",
        "kratke_useky": "Odstranit zbytečné lomové body (zdvojené a krátké úseky pod min. délkou)",
        "prichytit_vrcholy": "Přichytit lomové body ležící těsně u jiné čáry (pod Limitem)",
        "body_na_sobe": "Smazat zdvojené body / značky (stejná vrstva, na sobě)",
        "presun_vrstvy": "Přesunout prvky z vrstvy mimo Směrnici na vrstvu, kam podle vzhledu patří",
        "symbologie": "Opravit atributy podle pravidel (vrstva, barva, styl, tloušťka, výška/šířka/zarovnání textu)",
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

    def geom(self, handle: str):
        """Aktuální geometrie čáry v opravovaném souboru (v metrech)."""
        from shapely.geometry import LineString
        e = self.entity(handle)
        if e is None:
            return LineString()
        if e.dxftype() == "LINE":
            cs = [tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]]
        else:
            cs = [q[:2] for q in e.get_points("xy")]
            if e.closed and cs:
                cs.append(cs[0])
        return LineString([(x * self.f, y * self.f) for x, y in cs]) if len(cs) >= 2 else LineString()

    def lines_near(self, p, dist: float, exclude: str = "") -> list[str]:
        """Handly čar (LINE, LWPOLYLINE) v modelovém prostoru, které procházejí blízko bodu p (v metrech)."""
        from shapely.geometry import LineString
        out = []
        pt = Point(p)
        for e in self.msp.query("LINE LWPOLYLINE"):
            h = e.dxf.handle
            if h == exclude or h in self.deleted:
                continue
            if e.dxftype() == "LINE":
                cs = [tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]]
            else:
                cs = [q[:2] for q in e.get_points("xy")]
                if e.closed and cs:
                    cs.append(cs[0])
            if len(cs) < 2:
                continue
            g = LineString([(x * self.f, y * self.f) for x, y in cs])
            if g.distance(pt) <= dist:
                out.append(h)
        return out

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

    def split_polyline(self, handle: str, points: list[tuple[float, float]], eps: float) -> int:
        """Rozdělí otevřenou LWPOLYLINE ve vnitřních lomových bodech ležících v ``points`` (uzel → dvě čáry)."""
        e = self.entity(handle)
        if e is None or e.dxftype() != "LWPOLYLINE" or e.closed:
            return 0
        pts = list(e.get_points("xyseb"))
        cut = sorted({k for p in points for k in range(1, len(pts) - 1)
                      if math.dist((pts[k][0] * self.f, pts[k][1] * self.f), p) <= eps})
        if not cut:
            return 0
        attribs = e.dxfattribs(drop={"handle", "owner"})
        bounds = [0] + cut + [len(pts) - 1]
        parts = [pts[a:b + 1] for a, b in zip(bounds[:-1], bounds[1:])]
        for part in parts[1:]:
            part = part[:-1] + [(*part[-1][:4], 0.0)]
            self.msp.add_lwpolyline(part, format="xyseb", dxfattribs=attribs)
        first = parts[0][:-1] + [(*parts[0][-1][:4], 0.0)]
        e.set_points(first, format="xyseb")
        return len(cut)

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


def _platna_tloustka(mm: float) -> int:
    """Nejbližší povolená tloušťka DXF (setiny mm)."""
    from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS
    return min(VALID_DXF_LINEWEIGHTS, key=lambda v: abs(v - mm * 100))


def oprav_atributy(e, f, r, rules: RuleSet, doc) -> list[str]:
    """Nastaví entitě atributy podle pravidla (jako „Kontrola a změna symbologie“ GISoft v režimu změna).
    Vrací seznam provedených změn."""
    from .checks.attributes import parse_alignment
    zmeny: list[str] = []
    linie = f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
    if r.hladina and not any(c in r.hladina for c in "*?[") and not r.matches_layer(f.layer):
        if r.hladina not in doc.layers:
            doc.layers.add(r.hladina)
        e.dxf.layer = r.hladina
        zmeny.append(f"vrstva → {r.hladina}")
    if r.barva is not None:
        rgb = color_rgb(r.barva, rules.paleta, rules.barevna_tabulka)
        if rules.paleta == "autocad" and isinstance(r.barva, int):
            if e.dxf.get("color") != r.barva or e.dxf.hasattr("true_color"):
                e.dxf.discard("true_color")
                e.dxf.color = r.barva
                zmeny.append(f"barva → {r.barva}")
        elif rgb is not None and (e.rgb != tuple(rgb) or e.dxf.get("color", 256) == 256):
            e.dxf.color = 7 if e.dxf.get("color", 256) in (0, 256) else e.dxf.color  # ne „dle vrstvy“
            e.rgb = tuple(rgb)
            zmeny.append(f"barva → {r.barva}")
    if r.styl_cary and linie:
        from .rules import split_alternatives
        alt = split_alternatives(r.styl_cary)[0].strip()
        lt = "CONTINUOUS" if alt.upper() in ("CONTINUOUS", "0", "PLNÁ", "PLNA") else alt
        nalez = next((x.dxf.name for x in doc.linetypes if x.dxf.name.upper() == lt.upper()), None)
        if nalez and (e.dxf.get("linetype", "BYLAYER") or "").upper() != nalez.upper():
            e.dxf.linetype = nalez
            zmeny.append(f"styl → {nalez}")
    if r.meritko_stylu and linie and abs(float(e.dxf.get("ltscale", 1.0)) - r.meritko_stylu) > 1e-4:
        e.dxf.ltscale = float(r.meritko_stylu)
        zmeny.append(f"měřítko stylu → {r.meritko_stylu:g}")
    if r.tloustka is not None and f.geom_type != GeomType.TEXT and e.dxf.is_supported("lineweight"):
        mm, _nezname = rules.expected_weights(r)
        if mm and all(abs(e.dxf.get("lineweight", -1) / 100.0 - w) > 0.051 for w in mm):
            e.dxf.lineweight = _platna_tloustka(mm[0])
            zmeny.append(f"tloušťka → {e.dxf.lineweight / 100:.2f} mm")
    if f.geom_type == GeomType.TEXT and e.dxftype() in ("TEXT", "MTEXT"):
        h = rules.text_size(r.vyska_textu)
        vys = "height" if e.dxftype() == "TEXT" else "char_height"
        if h and abs(float(e.dxf.get(vys, 0.0)) - h) > max(0.005, 0.02 * h):
            stara = float(e.dxf.get(vys, 0.0)) or h
            e.dxf.set(vys, h)
            if e.dxftype() == "MTEXT" and e.dxf.hasattr("width") and stara:
                e.dxf.width = float(e.dxf.width) * h / stara
            zmeny.append(f"výška textu → {r.vyska_textu:g}")
        w = rules.text_size(r.sirka_textu)
        if w and e.dxftype() == "TEXT":
            hh = float(e.dxf.get("height", 0.0)) or h
            if hh and abs(hh * float(e.dxf.get("width", 1.0)) - w) > max(0.005, 0.02 * w):
                e.dxf.width = w / hh
                zmeny.append(f"šířka textu → {r.sirka_textu:g}")
        if r.zarovnani and e.dxftype() == "TEXT":
            ha, va = parse_alignment(r.zarovnani)
            stare = (e.dxf.get("halign", 0), e.dxf.get("valign", 0))
            nove = (stare[0] if ha is None else ha, stare[1] if va is None else va)
            if nove != stare:
                bod = e.dxf.align_point if stare != (0, 0) and e.dxf.hasattr("align_point") else e.dxf.insert
                e.dxf.halign, e.dxf.valign = nove
                e.dxf.insert = bod
                e.dxf.align_point = bod  # vkládací bod zůstane na místě, text se zarovná k němu
                zmeny.append(f"zarovnání → {r.zarovnani}")
        if r.font:
            styl = _textovy_styl(doc, r.font)
            if styl and (e.dxf.get("style", "Standard") or "").lower() != styl.lower():
                e.dxf.style = styl
                zmeny.append(f"písmo → {r.font}")
    return zmeny


def _textovy_styl(doc, font: str) -> str | None:
    """Textový styl ve výkresu, jehož písmo odpovídá fontu z pravidla."""
    import re as _re
    def norm(t: str) -> str:
        return _re.sub(r"[\s_\-]+", "", t.lower())
    zavorka = _re.search(r"\((.*?)\)", font)
    hledej = [norm(_re.sub(r"\(.*?\)", "", font))] + ([norm(zavorka.group(1)).rsplit(".", 1)[0]] if zavorka else [])
    hledej = [h for h in hledej if h]
    for st in doc.styles:
        jm = norm(st.dxf.get("font", "") or "") + "|" + norm(st.dxf.name)
        if any(h in jm for h in hledej):
            return st.dxf.name
    return None


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
    split_nodes = opts.rozdelit_v_uzlu and bool(_param("pruseciky_bez_uzlu", "vyzadovat_rozdeleni", True, config))
    splits: dict[str, list] = defaultdict(list)
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
                if split_nodes:
                    for fid in iss.feature_ids:
                        f = by_id.get(fid)
                        if f is not None and f.handle not in D.deleted:
                            splits[f.handle].append((iss.x, iss.y))
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
    for h, pts in splits.items():
        n = D.split_polyline(h, pts, eps * 10)
        if n:
            rep.counts["Linie rozdělené v uzlu"] += n

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

    # 3b) zbytečné lomové body: zdvojené a krátké úseky uvnitř lomené čáry (ne v uzlu s jinou čárou)
    if opts.kratke_useky:
        from shapely.strtree import STRtree
        lin = [f for f in drawing.features if f.dxftype == "LWPOLYLINE" and f.handle not in D.deleted]
        all_lin = [f for f in drawing.features if f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
                   and f.geometry is not None]
        tree_all = STRtree([f.geometry for f in all_lin]) if all_lin else None
        for f in lin:
            e = D.entity(f.handle)
            if e is None:
                continue
            pts = list(e.get_points("xyseb"))
            if len(pts) < 3 or any(abs(p[4]) > 1e-12 for p in pts):
                continue
            keep = [pts[0]]
            removed = 0
            for k in range(1, len(pts) - 1):
                p, prev, nxt = pts[k], keep[-1], pts[k + 1]
                dprev = math.dist(p[:2], prev[:2]) * D.f
                dnext = math.dist(p[:2], nxt[:2]) * D.f
                if min(dprev, dnext) >= min_seg:
                    keep.append(p)
                    continue
                pw = Point(p[0] * D.f, p[1] * D.f)
                node = tree_all is not None and any(
                    all_lin[i].handle != f.handle for i in tree_all.query(pw, predicate="dwithin", distance=eps * 10))
                if node:
                    keep.append(p)  # uzel s jinou čarou – nechat
                    continue
                removed += 1
            keep.append(pts[-1])
            if removed and len(keep) >= 2:
                e.set_points(keep, format="xyseb")
                rep.counts["Odstraněné zbytečné lomové body"] += removed

    # 3c) lomové body těsně u jiné čáry → přichytit na ni (na její aktuální polohu v opravovaném souboru)
    if opts.prichytit_vrcholy:
        limit = float(_param("blizke_prvky", "limit", 0.01, config))
        res = run_checks(drawing, rules, config, only=["blizke_prvky"])
        for iss in res.issues:
            f = by_id.get(iss.feature_ids[0]) if iss.feature_ids else None
            e = D.entity(f.handle) if f is not None else None
            if e is None or e.dxftype() != "LWPOLYLINE":
                continue
            pts = list(e.get_points("xyseb"))
            k = min(range(len(pts)), key=lambda i: math.dist((pts[i][0] * D.f, pts[i][1] * D.f), (iss.x, iss.y)))
            v = (pts[k][0] * D.f, pts[k][1] * D.f)
            if math.dist(v, (iss.x, iss.y)) > eps * 10:
                continue
            cands = [(D.geom(h).distance(Point(v)), h) for h in D.lines_near(v, limit * 1.5, exclude=f.handle)]
            cands = [c for c in cands if c[0] > eps]
            if not cands:
                rep.skipped.append(f"Lomový bod u {iss.x:.3f}, {iss.y:.3f} leží u oblouku nebo prvku, který oprava "
                                   "neumí upravit – přichyťte ho ručně")
                continue
            _, h = min(cands)
            g = D.geom(h)
            near_v = min(g.coords, key=lambda c: math.dist(c, v))
            if math.dist(near_v, v) <= max(limit, min_seg):
                q, node = Point(near_v), False  # lomový bod druhé čáry je blízko → přichytit rovnou na něj
            else:
                q, node = g.interpolate(g.project(Point(v))), True
            pts[k] = (q.x / D.f, q.y / D.f, *pts[k][2:])
            e.set_points(pts, format="xyseb")
            rep.counts["Přichycené lomové body"] += 1
            if node:
                oe = D.entity(h)
                if oe is not None and oe.dxftype() == "LINE":
                    D.split_line(h, [(q.x, q.y)])
                elif oe is not None:
                    D.insert_vertices(h, [(q.x, q.y)], max(tol, eps * 10))
            if split_nodes:  # uzel, kde se čáry kříží ve společném lomovém bodě, má obě čáry rozdělit
                g_f = D.geom(f.handle)
                if g_f.coords and min(math.dist(g_f.coords[0], (q.x, q.y)),
                                      math.dist(g_f.coords[-1], (q.x, q.y))) > eps * 10:
                    n = D.split_polyline(h, [(q.x, q.y)], eps * 10)
                    if n:
                        n += D.split_polyline(f.handle, [(q.x, q.y)], eps * 10)
                        rep.counts["Linie rozdělené v uzlu"] += n

    # 3d) zdvojené body a značky (stejná vrstva, stejná buňka, na sobě)
    if opts.body_na_sobe:
        res = run_checks(drawing, rules, config, only=["body_blizko"])
        for iss in res.issues:
            fs = [by_id.get(i) for i in iss.feature_ids]
            fs = [f for f in fs if f is not None and f.handle not in D.deleted]
            if len(fs) < 2:
                continue
            a = fs[0]
            for b in fs[1:]:
                if b.layer == a.layer and (b.block_name or "") == (a.block_name or "") and \
                        a.geometry.distance(b.geometry) <= tol and D.delete(b.handle):
                    rep.counts["Smazané zdvojené body"] += 1

    # 3e) prvky z vrstvy mimo Směrnici → vrstva podle vzhledu
    if opts.presun_vrstvy and rules.pravidla:
        from .checks.attributes import guess_layer
        by_layer: dict[str, list] = defaultdict(list)
        for f in drawing.features:
            if f.handle and not rules.allowed_layer(f.layer):
                by_layer[f.layer].append(f)
        for layer, fs in by_layer.items():
            g = guess_layer(fs, rules, drawing)
            if not g or " nebo " in g:
                rep.skipped.append(f"Vrstva {layer}: není jasné, kam prvky patří – přesuňte ručně")
                continue
            if g not in D.doc.layers:
                D.doc.layers.add(g)
            n = 0
            for f in fs:
                e = D.entity(f.handle)
                if e is not None:
                    e.dxf.layer = g
                    n += 1
            if n:
                rep.counts["Přesunuto na vrstvu podle Směrnice"] += n
                rep.details.append(f"Vrstva {layer} → {g}: {n} prvků")

    # 4) atributy (symbologie) podle pravidel – vrstva, barva, styl, měřítko stylu, tloušťka, text
    if opts.symbologie and rules.pravidla:
        res = run_checks(drawing, rules, config, only=["symbologie", "atribut_dle_vrstvy"])
        hotovo: set[str] = set()
        for iss in res.issues:
            f = by_id.get(iss.feature_ids[0]) if iss.feature_ids else None
            if f is None or f.handle in hotovo:
                continue
            e = D.entity(f.handle)
            r = ctx.rule_for(f)
            if e is None or r is None:
                continue
            hotovo.add(f.handle)
            zmeny = oprav_atributy(e, f, r, rules, D.doc)
            if zmeny:
                rep.counts["Opravené atributy (symbologie)"] += 1
                if len(rep.details) < 400:
                    rep.details.append(f"{r.nazev or r.kod} [{f.handle}]: " + ", ".join(zmeny))
            else:
                rep.skipped.append(f"{iss.message} – atribut nejde v DXF opravit automaticky")

    D.doc.saveas(out_path)
    return rep
