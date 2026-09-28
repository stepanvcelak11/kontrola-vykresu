"""Načtení výkresu DXF pomocí knihovny ezdxf.

Z modelového prostoru se čtou entity LINE, LWPOLYLINE, POLYLINE, ARC,
CIRCLE, POINT, INSERT, TEXT, MTEXT a HATCH (navíc i SPLINE a ELLIPSE).
Oblouky se pro geometrické kontroly nahradí lomenou čarou, původní
vrcholy se ale uchovají, aby šlo kontrolovat uzly.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Callable, Iterable

import ezdxf
from ezdxf import colors as ezcolors
from ezdxf import path as ezpath
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from ..model import BlockGeometry, Drawing, Feature, GeomType, LayerInfo

ProgressFn = Callable[[int, str], None]

# $INSUNITS -> násobek na metry
_UNITS = {0: 1.0, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0, 14: 0.1}

FLATTEN_DISTANCE = 0.005  # m – odchylka náhrady oblouku lomenou čarou

SUPPORTED = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "POINT", "INSERT",
             "TEXT", "MTEXT", "HATCH", "SPLINE", "ELLIPSE"}

_KV_RE = re.compile(r"^\s*([^=:]{1,64}?)\s*[=:]\s*(.*)$")


class DrawingLoadError(Exception):
    """Výkres se nepodařilo načíst."""


def _lineweight_mm(value: int | None, fallback: float = 0.0) -> float:
    if value is None or value < 0:
        return fallback
    return value / 100.0


def _aci_rgb(aci: int | None) -> tuple[int, int, int]:
    if aci is None or aci <= 0 or aci > 255:
        return (255, 255, 255)
    r, g, b = ezcolors.aci2rgb(aci)
    return (r, g, b)


class _Ctx:
    def __init__(self, doc, factor: float):
        self.doc = doc
        self.factor = factor
        self.layers: dict[str, LayerInfo] = {}
        for layer in doc.layers:
            aci = abs(layer.dxf.get("color", 7)) or 7
            rgb = _aci_rgb(aci)
            if layer.has_dxf_attrib("true_color"):
                rgb = tuple(layer.rgb)  # type: ignore[assignment]
            self.layers[layer.dxf.name] = LayerInfo(
                name=layer.dxf.name,
                color_aci=aci,
                color_rgb=rgb,
                linetype=(layer.dxf.get("linetype", "CONTINUOUS") or "CONTINUOUS").upper(),
                lineweight=_lineweight_mm(layer.dxf.get("lineweight", -3)),
                frozen=layer.is_frozen(),
                off=layer.is_off(),
            )

    def layer(self, name: str) -> LayerInfo:
        info = self.layers.get(name)
        if info is None:
            info = LayerInfo(name=name)
            self.layers[name] = info
        return info

    def xy(self, v) -> tuple[float, float]:
        return (float(v[0]) * self.factor, float(v[1]) * self.factor)


def _entity_style(e, ctx: _Ctx, parent: Feature | None = None):
    layer_name = e.dxf.get("layer", "0")
    if layer_name == "0" and parent is not None:
        layer_name = parent.layer
    layer = ctx.layer(layer_name)
    aci = e.dxf.get("color", 256)
    if aci == 256:  # BYLAYER
        color_aci, rgb = layer.color_aci, layer.color_rgb
    elif aci == 0 and parent is not None:  # BYBLOCK
        color_aci, rgb = parent.color_aci, parent.color_rgb
    else:
        color_aci, rgb = aci, _aci_rgb(aci)
    if e.dxf.hasattr("true_color"):
        rgb = tuple(e.rgb)
    lt = (e.dxf.get("linetype", "BYLAYER") or "BYLAYER").upper()
    if lt == "BYLAYER":
        lt = layer.linetype
    elif lt == "BYBLOCK" and parent is not None:
        lt = parent.linetype
    lw_raw = e.dxf.get("lineweight", -1)
    if lw_raw == -1:
        lw = layer.lineweight
    elif lw_raw == -2 and parent is not None:
        lw = parent.lineweight
    else:
        lw = _lineweight_mm(lw_raw)
    bylayer = set()
    if aci == 256 and not e.dxf.hasattr("true_color"):
        bylayer.add("barva")
    if (e.dxf.get("linetype", "BYLAYER") or "BYLAYER").upper() == "BYLAYER":
        bylayer.add("styl")
    if lw_raw == -1:
        bylayer.add("tloušťka")
    return layer_name, color_aci, rgb, lt, lw, frozenset(bylayer)


def _xdata(e) -> tuple[dict[str, list], dict[str, str]]:
    raw: dict[str, list] = {}
    attrs: dict[str, str] = {}
    xd = getattr(e, "xdata", None)
    if not xd:
        return raw, attrs
    try:
        items = list(xd.data.items())
    except Exception:  # pragma: no cover - neobvyklá XDATA
        return raw, attrs
    for appid, tags in items:
        values = [t.value for t in tags]
        raw[appid] = values
        strings = [v for (code, v) in ((t.code, t.value) for t in tags) if code == 1000]
        pending_key = None
        for s in strings:
            m = _KV_RE.match(str(s))
            if m:
                attrs[m.group(1).strip().upper()] = m.group(2).strip()
                pending_key = None
            elif pending_key is None:
                pending_key = str(s).strip().upper()
            else:
                attrs[pending_key] = str(s).strip()
                pending_key = None
    return raw, attrs


def _flatten(e, ctx: _Ctx) -> list[tuple[float, float]]:
    p = ezpath.make_path(e)
    pts = [ctx.xy(v) for v in p.flattening(FLATTEN_DISTANCE / ctx.factor)]
    return _dedupe(pts)


def _to_wcs(e, v):
    """Bod v OCS prvku → WCS (prvky v obecné rovině, např. 3D výkres z MicroStationu)."""
    ex = e.dxf.get("extrusion", None)
    if ex is None or (abs(ex[0]) < 1e-12 and abs(ex[1]) < 1e-12 and ex[2] > 0):
        return v
    return e.ocs().to_wcs(v)


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) > 1e-9 or abs(out[-1][1] - p[1]) > 1e-9):
            out.append(p)
    return out


def _linear_geometry(pts: list[tuple[float, float]], closed: bool) -> tuple[BaseGeometry, GeomType]:
    if closed and len(pts) >= 3:
        ring = pts if pts[0] == pts[-1] else pts + [pts[0]]
        if len(ring) >= 4:
            return Polygon(ring), GeomType.POLYGON
    if len(pts) >= 2:
        return LineString(pts), GeomType.LINIE
    if len(pts) == 1:
        return LineString([pts[0], pts[0]]), GeomType.LINIE
    return LineString(), GeomType.LINIE


def _text_align(e) -> tuple[int, int]:
    if e.dxftype() == "MTEXT":
        ap = e.dxf.get("attachment_point", 1)
        h = (ap - 1) % 3
        v = {0: 3, 1: 2, 2: 1}[(ap - 1) // 3]
        return h, v
    h = e.dxf.get("halign", 0)
    v = e.dxf.get("valign", 0)
    if h in (3, 5):  # ALIGNED, FIT
        h = 0
    if h == 4:  # MIDDLE
        return 1, 2
    return min(h, 2), v


class _Loader:
    def __init__(self, doc, path: str, progress: ProgressFn | None):
        insunits = doc.header.get("$INSUNITS", 6)
        self.factor = _UNITS.get(insunits, 1.0)
        self.ctx = _Ctx(doc, self.factor)
        self.doc = doc
        self.drawing = Drawing(path=path, unit_factor=self.factor)
        self.progress = progress
        self._next_id = 0

    def _new(self, **kw) -> Feature:
        f = Feature(fid=self._next_id, **kw)
        self._next_id += 1
        return f

    def run(self) -> Drawing:
        msp = self.doc.modelspace()
        entities = [e for e in msp if e.dxftype() in SUPPORTED]
        skipped: dict[str, int] = {}
        for e in msp:
            t = e.dxftype()
            if t not in SUPPORTED:
                skipped[t] = skipped.get(t, 0) + 1
        total = max(1, len(entities))
        step = max(1, total // 100)
        for i, e in enumerate(entities):
            try:
                for f in self._convert(e):
                    self.drawing.features.append(f)
            except Exception as exc:  # jednotlivý vadný prvek nesmí shodit načtení
                self.drawing.warnings.append(
                    f"Prvek {e.dxftype()} #{e.dxf.get('handle', '?')} se nepodařilo načíst: {exc}")
            if self.progress and i % step == 0:
                self.progress(int(i * 100 / total), f"Načítám prvky… {i}/{total}")
        for t, n in sorted(skipped.items()):
            self.drawing.warnings.append(f"Nepodporovaný typ prvku {t} ({n}×) byl přeskočen.")
        for f in self.drawing.features:
            self.ctx.layer(f.layer).count += 1
        self.drawing.layers = self.ctx.layers
        self.drawing.linetypes = {lt.dxf.name.upper() for lt in self.doc.linetypes}
        if self.progress:
            self.progress(100, "Hotovo")
        return self.drawing

    # ------------------------------------------------------------------
    def _base(self, e, parent: Feature | None = None) -> dict:
        layer, aci, rgb, lt, lw, bylayer = _entity_style(e, self.ctx, parent)
        raw, xattrs = _xdata(e)
        return dict(layer=layer, color_aci=aci, color_rgb=rgb, linetype=lt, lineweight=lw,
                    ltscale=float(e.dxf.get("ltscale", 1.0) or 1.0),
                    handle=e.dxf.get("handle", ""), xdata=raw, attributes=xattrs, bylayer=bylayer)

    def _is_reference(self, name: str) -> bool:
        """Je blok připojený referenční výkres (MicroStation reference, xref), ne buňka/značka?

        Reference se při exportu z MicroStationu uloží jako blok s celou kresbou na mnoha
        hladinách – takový blok se rozbalí na samostatné prvky, aby šly zkontrolovat."""
        cache = self.__dict__.setdefault("_ref_cache", {})
        if name not in cache:
            block = self.doc.blocks.get(name)
            if block is None:
                cache[name] = False
            elif block.block.dxf.get("flags", 0) & (4 | 8):
                cache[name] = True
            else:
                ents = list(block)
                layers = {be.dxf.get("layer", "0") for be in ents} - {"0"}
                cache[name] = len(ents) >= 30 and len(layers) >= 3
        return cache[name]

    def _convert(self, e, depth: int = 0) -> Iterable[Feature]:
        t = e.dxftype()
        if t == "INSERT" and depth < 4 and self._is_reference(e.dxf.name):
            n0 = self._next_id
            for ve in e.virtual_entities():
                if ve.dxftype() in SUPPORTED:
                    try:
                        yield from self._convert(ve, depth + 1)
                    except Exception:
                        continue
            self.drawing.warnings.append(
                f"Referenční výkres „{e.dxf.name}“ byl rozbalen na {self._next_id - n0} prvků a kontroluje se s výkresem.")
            return
        base = self._base(e)
        if t == "LINE":
            a, b = self.ctx.xy(e.dxf.start), self.ctx.xy(e.dxf.end)
            if math.dist(a, b) < 1e-9:
                # úsečka nulové délky = bod MicroStationu („umístit aktivní bod“)
                yield self._new(dxftype=t, geom_type=GeomType.BOD, geometry=Point(a), vertices=[a],
                                zero_length=True, **base)
                return
            yield self._new(dxftype=t, geom_type=GeomType.LINIE, geometry=LineString([a, b]),
                            vertices=[a, b], **base)
        elif t in ("LWPOLYLINE", "POLYLINE"):
            if t == "POLYLINE" and not (e.is_2d_polyline or e.is_3d_polyline):
                self.drawing.warnings.append(f"POLYLINE #{base['handle']} (síť/plochy) přeskočena.")
                return
            closed = bool(e.closed) if t == "LWPOLYLINE" else bool(e.is_closed)
            if t == "LWPOLYLINE":
                raw = list(e.get_points("xyb"))
                verts = [self.ctx.xy(p) for p in e.vertices_in_wcs()]
                has_arc = any(abs(p[2]) > 1e-12 for p in raw)
            else:
                verts = [self.ctx.xy(p) for p in e.points_in_wcs()]
                has_arc = any(abs(v.dxf.get("bulge", 0.0)) > 1e-12 for v in e.vertices)
            verts = _dedupe(verts)
            pts = _flatten(e, self.ctx) if (has_arc and len(verts) > 1) else list(verts)
            if closed and pts and pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            geom, gt = _linear_geometry(pts, closed)
            yield self._new(dxftype=t, geom_type=gt, geometry=geom, closed=closed, vertices=verts, **base)
        elif t in ("ARC", "SPLINE", "ELLIPSE"):
            pts = _flatten(e, self.ctx)
            closed = False
            if t == "ELLIPSE" or (t == "SPLINE" and e.closed):
                closed = len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1e-9
            geom, gt = _linear_geometry(pts, closed)
            verts = [pts[0], pts[-1]] if pts else []
            yield self._new(dxftype=t, geom_type=gt, geometry=geom, closed=closed, vertices=verts, **base)
        elif t == "CIRCLE":
            c = self.ctx.xy(_to_wcs(e, e.dxf.center))
            yield self._new(dxftype=t, geom_type=GeomType.BOD, geometry=Point(c), vertices=[c],
                            radius=e.dxf.radius * self.factor, **base)
        elif t == "POINT":
            c = self.ctx.xy(e.dxf.location)
            yield self._new(dxftype=t, geom_type=GeomType.BOD, geometry=Point(c), vertices=[c], **base)
        elif t == "INSERT":
            yield self._insert(e, base)
        elif t in ("TEXT", "MTEXT"):
            yield self._text(e, base)
        elif t == "HATCH":
            yield from self._hatch(e, base)

    def _insert(self, e, base: dict) -> Feature:
        c = self.ctx.xy(_to_wcs(e, e.dxf.insert))
        name = e.dxf.name
        attrs = dict(base.pop("attributes"))
        texts = []
        for a in e.attribs:
            tag = (a.dxf.get("tag", "") or "").strip().upper()
            val = a.dxf.get("text", "")
            if tag:
                attrs[tag] = val
            if not a.is_invisible and val:
                p = self.ctx.xy(a.dxf.insert)
                texts.append((val, p[0], p[1], a.dxf.get("height", 1.0) * self.factor,
                              a.dxf.get("rotation", 0.0)))
        f = self._new(dxftype="INSERT", geom_type=GeomType.BOD, geometry=Point(c), vertices=[c],
                      block_name=name, rotation=e.dxf.get("rotation", 0.0),
                      scale=(e.dxf.get("xscale", 1.0), e.dxf.get("yscale", 1.0)),
                      attributes=attrs, display_texts=texts, **base)
        if name not in self.drawing.blocks:
            self.drawing.blocks[name] = self._block_geometry(name)
        return f

    def _block_geometry(self, name: str, depth: int = 0) -> BlockGeometry:
        bg = BlockGeometry(name=name)
        block = self.doc.blocks.get(name)
        if block is None:
            return bg
        bp = block.block.dxf.get("base_point", (0, 0, 0))
        bg.base_point = (bp[0] * self.factor, bp[1] * self.factor)
        for be in self._iter_block(block, depth):
            bt = be.dxftype()
            try:
                if bt in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "ELLIPSE", "SOLID"):
                    p = ezpath.make_path(be)
                    for sub in p.sub_paths():
                        pts = [self.ctx.xy(v) for v in sub.flattening(FLATTEN_DISTANCE / self.factor)]
                        if len(pts) >= 2:
                            bg.paths.append(pts)
                            bg.closed.append(sub.is_closed or bt in ("CIRCLE",))
                elif bt == "HATCH":
                    for p in ezpath.from_hatch(be):
                        pts = [self.ctx.xy(v) for v in p.flattening(FLATTEN_DISTANCE / self.factor)]
                        if len(pts) >= 2:
                            bg.paths.append(pts)
                            bg.closed.append(True)
                elif bt == "POINT":
                    bg.points.append(self.ctx.xy(be.dxf.location))
            except Exception:
                continue
        return bg

    def _iter_block(self, block, depth: int):
        for be in block:
            if be.dxftype() == "INSERT" and depth < 8:
                try:
                    for ve in be.virtual_entities():
                        if ve.dxftype() == "INSERT":
                            yield from self._iter_virtual_insert(ve, depth + 1)
                        else:
                            yield ve
                except Exception:
                    continue
            elif be.dxftype() not in ("ATTDEF",):
                yield be

    def _iter_virtual_insert(self, ins, depth: int):
        if depth >= 8:
            return
        try:
            for ve in ins.virtual_entities():
                if ve.dxftype() == "INSERT":
                    yield from self._iter_virtual_insert(ve, depth + 1)
                else:
                    yield ve
        except Exception:
            return

    def _text(self, e, base: dict) -> Feature:
        t = e.dxftype()
        if t == "MTEXT":
            text = e.plain_text()
            p = self.ctx.xy(e.dxf.insert)
            height = e.dxf.get("char_height", 1.0) * self.factor
            rotation = e.get_rotation()
        else:
            text = e.plain_text()
            pt = _to_wcs(e, e.get_placement()[1])
            p = self.ctx.xy(pt)
            height = e.dxf.get("height", 1.0) * self.factor
            rotation = e.dxf.get("rotation", 0.0)
        h, v = _text_align(e)
        style_name = e.dxf.get("style", "Standard") or "Standard"
        font = style_name
        try:
            st = self.doc.styles.get(style_name)
            if st is not None and st.dxf.get("font"):
                font = f"{style_name} ({st.dxf.font})"
        except Exception:
            pass
        wf = e.dxf.get("width", 1.0) if t == "TEXT" else 1.0
        return self._new(dxftype=t, geom_type=GeomType.TEXT, geometry=Point(p), vertices=[p],
                         text=text.strip(), text_height=height, rotation=rotation,
                         halign=h, valign=v, width_factor=float(wf or 1.0), font=font, **base)

    def _hatch(self, e, base: dict) -> Iterable[Feature]:
        rings = []
        for p in ezpath.from_hatch(e):
            pts = _dedupe([self.ctx.xy(v) for v in p.flattening(FLATTEN_DISTANCE / self.factor)])
            if len(pts) >= 3:
                rings.append(pts)
        if not rings:
            return
        rings.sort(key=lambda r: abs(Polygon(r).area) if len(r) >= 3 else 0, reverse=True)
        shell, holes = rings[0], rings[1:]
        poly = Polygon(shell, [h for h in holes if Polygon(shell).contains(Polygon(h))])
        if not poly.is_valid:
            poly = make_valid(poly)
        yield self._new(dxftype="HATCH", geom_type=GeomType.POLYGON, geometry=poly, closed=True,
                        vertices=list(shell), fill=bool(e.dxf.get("solid_fill", 0)), **base)


def read_dxf(path: str | Path, progress: ProgressFn | None = None) -> Drawing:
    """Načte DXF soubor a vrátí :class:`Drawing`."""
    path = str(path)
    if progress:
        progress(0, "Otevírám soubor…")
    try:
        doc = ezdxf.readfile(path)
    except IOError as exc:
        raise DrawingLoadError(f"Soubor nelze otevřít: {exc}") from exc
    except ezdxf.DXFStructureError:
        try:
            from ezdxf import recover
            doc, auditor = recover.readfile(path)
        except Exception as exc:
            raise DrawingLoadError(f"Soubor není platný DXF: {exc}") from exc
    return _Loader(doc, path, progress).run()


def load_drawing(path: str | Path, progress: ProgressFn | None = None,
                 oda_path: str | None = None) -> Drawing:
    """Načte DXF, případně DGN/DWG přes ODA File Converter."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".dxf":
        return read_dxf(p, progress)
    if suffix in (".dgn", ".dwg"):
        from .dgn import convert_to_dxf
        # DXF se stejným názvem vedle DGN (uložený z MicroStationu / dávkovým převodem)
        sibling = next((s for s in (p.with_suffix(".dxf"), p.with_suffix(".DXF")) if s.is_file()), None)
        if sibling is not None:
            d = read_dxf(sibling, progress)
            d.source_path = str(sibling)
            if sibling.stat().st_mtime + 1 < p.stat().st_mtime:
                d.warnings.insert(0, f"{sibling.name} je starší než {p.name} – uložte výkres z MicroStationu "
                                     f"znovu jako DXF, jinak kontrolujete starou verzi.")
            else:
                d.warnings.insert(0, f"Použit {sibling.name} uložený vedle {p.name}.")
            return d
        if progress:
            progress(0, "Převádím výkres na DXF (ODA File Converter)…")
        dxf = convert_to_dxf(p, oda_path)
        d = read_dxf(dxf, progress)
        d.source_path = str(p)
        return d
    raise DrawingLoadError(f"Nepodporovaný formát souboru: {p.suffix}. Použijte DXF.")
