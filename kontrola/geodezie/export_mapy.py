"""Export seznamu souřadnic do DXF (shodně se světem, jako výkresy z MicroStationu) a do KML / GeoJSON (WGS84).

DXF: body jako POINT v hladině BODY, čísla a výšky jako texty v hladinách CISLA a VYSKY, spojnice
z grafiky jako úsečky v hladině SPOJNICE. Souřadnice x = −Y, y = −X (S-JTSK), výška v z.
KML / GeoJSON: zeměpisné souřadnice WGS84 (pro mapy.cz, Google Earth, QGIS, mobil) – převod
s přesností přibližně 1 m (stejně jako v QTrig).
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from . import sjtsk


def do_dxf(path: str | Path, body, spojnice=(), vyska_textu: float = 1.0, des_z: int = 2) -> Path:
    import ezdxf
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.header["$PDMODE"] = 3
    doc.header["$PDSIZE"] = vyska_textu * 0.6
    for jm, barva in (("BODY", 7), ("CISLA", 3), ("VYSKY", 5), ("KODY", 6), ("SPOJNICE", 1)):
        doc.layers.add(jm, color=barva)
    msp = doc.modelspace()
    for b in body:
        x, y, z = -abs(b.y), -abs(b.x), (b.z or 0.0)
        msp.add_point((x, y, z), dxfattribs={"layer": "BODY"})
        msp.add_text(b.cislo, height=vyska_textu, dxfattribs={"layer": "CISLA"}).set_placement(
            (x + 0.6 * vyska_textu, y + 0.3 * vyska_textu))
        if b.z is not None:
            msp.add_text(f"{b.z:.{des_z}f}", height=vyska_textu * 0.8, dxfattribs={"layer": "VYSKY"}).set_placement(
                (x + 0.6 * vyska_textu, y - 1.2 * vyska_textu))
        if b.kod:
            msp.add_text(str(b.kod), height=vyska_textu * 0.8, dxfattribs={"layer": "KODY"}).set_placement(
                (x + 0.6 * vyska_textu, y - 2.4 * vyska_textu))
    for a, b in spojnice:
        msp.add_line((-abs(a.y), -abs(a.x)), (-abs(b.y), -abs(b.x)), dxfattribs={"layer": "SPOJNICE"})
    p = Path(path)
    doc.saveas(p)
    return p


def _wgs(b):
    la, lo, _h = sjtsk.sjtsk_na_wgs84(abs(b.y), abs(b.x), parametry=sjtsk.HELMERT_PROJ4)
    return la, lo


def do_geojson(path: str | Path, body, spojnice=()) -> Path:
    feats = []
    for b in body:
        la, lo = _wgs(b)
        prop = {"name": b.cislo, "Y": b.y, "X": b.x}
        if b.z is not None:
            prop["Z"] = b.z
        if b.kod:
            prop["kod"] = b.kod
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lo, 9), round(la, 9)]},
                      "properties": prop})
    for a, b in spojnice:
        (la1, lo1), (la2, lo2) = _wgs(a), _wgs(b)
        feats.append({"type": "Feature", "properties": {"name": f"{a.cislo}-{b.cislo}"},
                      "geometry": {"type": "LineString", "coordinates": [[round(lo1, 9), round(la1, 9)],
                                                                         [round(lo2, 9), round(la2, 9)]]}})
    p = Path(path)
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def do_kml(path: str | Path, body, spojnice=(), nazev: str = "Seznam souřadnic") -> Path:
    r = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         f"<name>{escape(nazev)}</name>"]
    for b in body:
        la, lo = _wgs(b)
        popis = f"Y {b.y:.3f}  X {b.x:.3f}" + (f"  Z {b.z:.3f}" if b.z is not None else "") + (
            f"  kód {b.kod}" if b.kod else "")
        r.append(f"<Placemark><name>{escape(b.cislo)}</name><description>{escape(popis)}</description>"
                 f"<Point><coordinates>{lo:.9f},{la:.9f},0</coordinates></Point></Placemark>")
    for a, b in spojnice:
        (la1, lo1), (la2, lo2) = _wgs(a), _wgs(b)
        r.append(f"<Placemark><name>{escape(a.cislo)}-{escape(b.cislo)}</name><LineString><coordinates>"
                 f"{lo1:.9f},{la1:.9f},0 {lo2:.9f},{la2:.9f},0</coordinates></LineString></Placemark>")
    r.append("</Document></kml>")
    p = Path(path)
    p.write_text("\n".join(r), encoding="utf-8")
    return p
