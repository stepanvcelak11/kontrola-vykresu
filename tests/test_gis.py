"""Čtení GIS dat (Shapefile, GeoJSON) jako výkresu."""

import json
import struct

from kontrola.config import Config
from kontrola.io.dxf_loader import load_drawing
from kontrola.model import GeomType
from kontrola.rules import RuleSet
from kontrola.runner import run_checks


def _write_shp(path, shape_type, records, fields, rows):
    """Minimální zápis Shapefile (.shp + .dbf) pro test."""
    recs = b""
    for i, content in enumerate(records, 1):
        recs += struct.pack(">2i", i, len(content) // 2) + content
    hdr = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(recs)) // 2) + struct.pack("<2i", 1000, shape_type)
    hdr += struct.pack("<8d", 0, 0, 0, 0, 0, 0, 0, 0)
    path.write_bytes(hdr + recs)
    flen = 20
    dbf = struct.pack("<B3BIHH20x", 3, 125, 1, 1, len(rows), 32 + 32 * len(fields) + 1, 1 + flen * len(fields))
    for name in fields:
        dbf += name.encode().ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([flen, 0]) + b"\0" * 14
    dbf += b"\r"
    for r in rows:
        dbf += b" " + b"".join(str(r[f]).encode("cp1250").ljust(flen) for f in fields)
    path.with_suffix(".dbf").write_bytes(dbf + b"\x1a")


def _poly(parts):
    pts = [p for part in parts for p in part]
    idx, k = [], 0
    for part in parts:
        idx.append(k)
        k += len(part)
    c = struct.pack("<i4d2i", 3, 0, 0, 0, 0, len(parts), len(pts)) + struct.pack(f"<{len(parts)}i", *idx)
    return c + b"".join(struct.pack("<2d", *p) for p in pts)


def test_shapefile_cary_s_atributy_a_kontrola(tmp_path):
    p = tmp_path / "ploty.shp"
    _write_shp(p, 3, [_poly([[(0, 0), (10, 0)]]), _poly([[(10.005, 0), (10.005, 5)]]),
                      _poly([[(0, 20), (5, 20)], [(7, 20), (9, 20)]])],
               ["VRSTVA", "POPIS"], [{"VRSTVA": "Plot", "POPIS": "drátěný"}, {"VRSTVA": "Plot", "POPIS": "zeď"},
                                    {"VRSTVA": "Zeď", "POPIS": "část"}])
    d = load_drawing(p)
    assert len(d.features) == 4 and set(d.layers) == {"Plot", "Zeď"}
    assert d.features[0].attributes["POPIS"] == "drátěný"
    assert all(f.geom_type == GeomType.LINIE for f in d.features)
    res = run_checks(d, RuleSet(), Config())
    assert any(i.check_id == "chybejici_napojeni" for i in res.issues)


def test_shapefile_plocha_s_dirou(tmp_path):
    p = tmp_path / "budovy.shp"
    outer = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]  # po směru hodinových ručiček
    hole = [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)]
    c = _poly([outer, hole])
    c = struct.pack("<i", 5) + c[4:]
    _write_shp(p, 5, [c], ["ID"], [{"ID": "1"}])
    d = load_drawing(p)
    assert len(d.features) == 1 and d.features[0].geom_type == GeomType.POLYGON
    assert abs(d.features[0].geometry.area - 96) < 1e-9
    assert d.features[0].layer == "budovy"


def test_geojson(tmp_path):
    p = tmp_path / "data.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"layer": "Cesty"},
         "geometry": {"type": "MultiLineString", "coordinates": [[[-600000, -1150000], [-600010, -1150000]],
                                                                 [[-600020, -1150000], [-600030, -1150000]]]}},
        {"type": "Feature", "properties": {"cislo": 5},
         "geometry": {"type": "Point", "coordinates": [-600000, -1150005]}}]}), "utf-8")
    d = load_drawing(p)
    assert [f.layer for f in d.features] == ["Cesty", "Cesty", "data"]
    assert d.features[2].attributes["cislo"] == "5" and not d.warnings


def test_upozorneni_na_milimetry(tmp_path):
    p = tmp_path / "mm.geojson"
    p.write_text(json.dumps({"type": "LineString", "coordinates": [[-600000000, -1150000000],
                                                                   [-600010000, -1150000000]]}), "utf-8")
    d = load_drawing(p)
    assert any("milimetrech" in w for w in d.warnings)
