"""Čtení GIS dat jako výkresu: ESRI Shapefile (.shp + .dbf) a GeoJSON – z QGISu, ArcGISu, Geoportálu.

Bez dalších knihoven: Shapefile je jednoduchý binární formát (hlavička 100 B, záznamy s tvary),
atributy jsou v .dbf (dBASE). Vrstva prvku je hodnota atributu LAYER / VRSTVA / HLADINA, jinak
název souboru. Vícedílné tvary se rozdělí na samostatné prvky (každá čára / plocha zvlášť), aby
šly kontrolovat jako čáry z CAD výkresu.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from shapely.geometry import LinearRing, LineString, Point, Polygon, shape

from ..model import Drawing, Feature, GeomType, LayerInfo

LAYER_KEYS = ("LAYER", "VRSTVA", "HLADINA", "LEVEL", "LAYER_NAME")
PALETTE = [(255, 255, 255), (255, 80, 80), (80, 200, 80), (80, 160, 255), (255, 200, 0), (0, 220, 220),
           (230, 110, 230), (255, 140, 0), (170, 170, 170), (140, 255, 140)]


class GisError(Exception):
    pass


class _Builder:
    def __init__(self, path: Path):
        self.d = Drawing(path=str(path))
        self.stem = path.stem
        self.fid = 0

    def layer_of(self, attrs: dict[str, str]) -> str:
        up = {k.upper(): v for k, v in attrs.items()}
        for k in LAYER_KEYS:
            v = up.get(k)
            if v not in (None, ""):
                return str(v)
        return self.stem

    def add(self, geom, attrs: dict[str, str]):
        layer = self.layer_of(attrs)
        info = self.d.layers.get(layer)
        if info is None:
            rgb = PALETTE[len(self.d.layers) % len(PALETTE)]
            info = self.d.layers[layer] = LayerInfo(name=layer, color_aci=None, color_rgb=rgb)
        for g in getattr(geom, "geoms", [geom]):
            if g.is_empty:
                continue
            if g.geom_type == "Point":
                gt, dxftype, verts = GeomType.BOD, "POINT", [(g.x, g.y)]
            elif g.geom_type in ("LineString", "LinearRing"):
                g = LineString(g.coords)
                gt, dxftype, verts = GeomType.LINIE, "LWPOLYLINE", [tuple(c[:2]) for c in g.coords]
            elif g.geom_type == "Polygon":
                gt, dxftype, verts = GeomType.POLYGON, "LWPOLYLINE", [tuple(c[:2]) for c in g.exterior.coords]
            else:
                self.add(g, attrs)  # vnořená kolekce
                continue
            closed = gt == GeomType.POLYGON or (gt == GeomType.LINIE and len(verts) > 2 and verts[0] == verts[-1])
            self.d.features.append(Feature(
                fid=self.fid, dxftype=dxftype, geom_type=gt, geometry=g, layer=layer, color_aci=None,
                color_rgb=info.color_rgb, handle=f"GIS{self.fid}", closed=closed, vertices=verts,
                attributes={k: str(v) for k, v in attrs.items() if v is not None}))
            info.count += 1
            self.fid += 1


def _dbf_encoding(path: Path) -> list[str]:
    cpg = path.with_suffix(".cpg")
    encs = []
    if cpg.is_file():
        e = cpg.read_text("ascii", "ignore").strip().lower()
        encs.append({"1250": "cp1250", "ansi 1250": "cp1250"}.get(e, e))
    return encs + ["utf-8", "cp1250"]


def read_dbf(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    if len(raw) < 32:
        return []
    nrec, hlen, rlen = struct.unpack("<IHH", raw[4:12])
    fields = []
    pos = 32
    while pos + 32 <= hlen and raw[pos] != 0x0D:
        name = raw[pos:pos + 11].split(b"\0", 1)[0].decode("latin-1").strip()
        fields.append((name, chr(raw[pos + 11]), raw[pos + 16]))
        pos += 32
    encs = _dbf_encoding(path)
    out = []
    for r in range(nrec):
        base = hlen + r * rlen
        rec = raw[base:base + rlen]
        if len(rec) < rlen:
            break
        row, off = {}, 1
        for name, typ, flen in fields:
            b = rec[off:off + flen]
            off += flen
            for e in encs:
                try:
                    v = b.decode(e)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                v = b.decode("latin-1")
            v = v.strip().rstrip("\0")
            if typ in "NF" and v:
                try:
                    num = float(v)
                    v = str(int(num)) if num.is_integer() and "." not in v else str(num)
                except ValueError:
                    pass
            row[name] = v
        out.append(row)
    return out


def _rings_to_polygons(rings: list[list[tuple[float, float]]]):
    """Vnější kruhy jsou ve Shapefile po směru hodinových ručiček, díry proti směru."""
    shells, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        (holes if LinearRing(r).is_ccw else shells).append(r)
    if not shells:  # špatně orientovaná data – vše jako vnější
        shells, holes = holes, []
    polys = [[s, []] for s in shells]
    for h in holes:
        hp = Point(h[0])
        for p in polys:
            if Polygon(p[0]).contains(hp):
                p[1].append(h)
                break
    return [Polygon(s, hs) for s, hs in polys]


def read_shapefile(path: str | Path, progress=None) -> Drawing:
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) < 100 or struct.unpack(">i", raw[:4])[0] != 9994:
        raise GisError(f"{path.name} není platný Shapefile.")
    attrs = read_dbf(path.with_suffix(".dbf")) or read_dbf(path.with_suffix(".DBF"))
    b = _Builder(path)
    pos, n = 100, 0
    total = len(raw)
    while pos + 8 <= total:
        clen = struct.unpack(">i", raw[pos + 4:pos + 8])[0] * 2
        rec = raw[pos + 8:pos + 8 + clen]
        pos += 8 + clen
        a = attrs[n] if n < len(attrs) else {}
        n += 1
        if len(rec) < 4:
            continue
        st = struct.unpack("<i", rec[:4])[0]
        if st == 0:
            continue  # prázdný tvar
        if st in (1, 11, 21):
            x, y = struct.unpack("<2d", rec[4:20])
            b.add(Point(x, y), a)
        elif st in (8, 18, 28):
            npts = struct.unpack("<i", rec[36:40])[0]
            xy = struct.unpack(f"<{2 * npts}d", rec[40:40 + 16 * npts])
            for k in range(npts):
                b.add(Point(xy[2 * k], xy[2 * k + 1]), a)
        elif st in (3, 13, 23, 5, 15, 25):
            nparts, npts = struct.unpack("<2i", rec[36:44])
            parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])) + [npts]
            p0 = 44 + 4 * nparts
            xy = struct.unpack(f"<{2 * npts}d", rec[p0:p0 + 16 * npts])
            pts = [(xy[2 * k], xy[2 * k + 1]) for k in range(npts)]
            chains = [pts[parts[i]:parts[i + 1]] for i in range(nparts)]
            if st in (3, 13, 23):
                for c in chains:
                    if len(c) >= 2:
                        b.add(LineString(c), a)
            else:
                for poly in _rings_to_polygons(chains):
                    b.add(poly, a)
        if progress and n % 2000 == 0:
            progress(min(0.95, pos / total), f"Načítám {path.name}…")
    if not b.d.features:
        b.d.warnings.append(f"{path.name}: žádné prvky (nebo nepodporovaný typ tvaru).")
    if not path.with_suffix(".dbf").is_file() and not path.with_suffix(".DBF").is_file():
        b.d.warnings.append(f"K {path.name} chybí soubor .dbf – prvky jsou bez atributů.")
    return b.d


def read_geojson(path: str | Path, progress=None) -> Drawing:
    path = Path(path)
    try:
        data = json.loads(path.read_text("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise GisError(f"{path.name} není platný GeoJSON: {e}") from e
    b = _Builder(path)
    if data.get("type") == "FeatureCollection":
        items = data.get("features") or []
    elif data.get("type") == "Feature":
        items = [data]
    else:
        items = [{"type": "Feature", "geometry": data, "properties": {}}]
    for it in items:
        g = it.get("geometry")
        if not g:
            continue
        try:
            geom = shape(g)
        except (ValueError, TypeError, AttributeError, KeyError):
            continue
        props = it.get("properties") or {}
        b.add(geom, {k: v for k, v in props.items() if not isinstance(v, (dict, list))})
    crs = str((data.get("crs") or {}).get("properties", {}).get("name", ""))
    if b.d.features and not crs and all(abs(c) <= 180 for f in b.d.features[:50] for c in f.vertices[0]):
        b.d.warnings.append(f"{path.name} je nejspíš v zeměpisných souřadnicích (WGS-84, stupně) – délky "
                            "a tolerance v metrech nebudou sedět. Uložte ho v S-JTSK (EPSG:5514).")
    return b.d
