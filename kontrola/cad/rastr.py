"""Rastrové podklady (ortofoto, naskenovaná mapa, náčrt) s georeferencí – jako Raster Manager v MicroStationu.

Ve výkresu se rastr ukládá standardně jako DXF IMAGE + IMAGEDEF (odkaz na soubor, poloha, velikost pixelu),
takže ho otevře i AutoCAD nebo QGIS. Poloha z world filu (.jgw, .pgw, .tfw, .wld): šest čísel
A, D, B, E, C, F – velikost pixelu, natočení a střed levého horního pixelu ve světových souřadnicích.
Ortofoto ČÚZK v S-JTSK (EPSG:5514) má souřadnice záporné – přesně jako výkresy z MicroStationu (x = −Y, y = −X).
"""

from __future__ import annotations

import os
from pathlib import Path

PRIPONY_WF = {".jpg": ".jgw", ".jpeg": ".jgw", ".png": ".pgw", ".tif": ".tfw", ".tiff": ".tfw", ".bmp": ".bpw",
              ".gif": ".gfw"}


def world_file(obrazek: str | Path) -> Path | None:
    p = Path(obrazek)
    kandidati = [p.with_suffix(PRIPONY_WF.get(p.suffix.lower(), ".wld")), p.with_suffix(".wld"),
                 p.with_suffix(p.suffix + "w")]
    for k in kandidati:
        for v in (k, k.with_suffix(k.suffix.upper())):
            if v.exists():
                return v
    return None


def nacti_world_file(cesta: str | Path) -> tuple[float, float, float, float, float, float]:
    cisla = [float(r.strip().replace(",", ".")) for r in Path(cesta).read_text(encoding="ascii", errors="replace")
             .splitlines() if r.strip()]
    if len(cisla) < 6:
        raise ValueError("World file musí mít 6 čísel (A, D, B, E, C, F).")
    a, d, b, e, c, f = cisla[:6]
    if a == 0 and b == 0 or d == 0 and e == 0:
        raise ValueError("World file má nulovou velikost pixelu.")
    return a, d, b, e, c, f


def velikost_obrazku(cesta: str | Path) -> tuple[int, int]:
    from PySide6.QtGui import QImageReader
    r = QImageReader(str(cesta))
    s = r.size()
    if not s.isValid() or s.width() <= 0:
        raise ValueError(f"Obrázek {Path(cesta).name} nejde přečíst ({r.errorString()}).")
    return s.width(), s.height()


def geometrie_z_world_file(wf, sirka_px: int, vyska_px: int):
    """(vložení = levý dolní roh, u = vektor pixelu doprava, v = vektor pixelu nahoru) ve světových souřadnicích."""
    a, d, b, e, c, f = wf
    # levý horní roh obrázku (wf udává střed levého horního pixelu)
    lhx, lhy = c - a / 2 - b / 2, f - d / 2 - e / 2
    u = (a, d)
    v = (-b, -e)  # řádky jdou dolů (E < 0) → vektor nahoru
    vlozeni = (lhx + vyska_px * b, lhy + vyska_px * e)
    return vlozeni, u, v


def pripoj(doc, msp, h, cesta, zaklad: Path | None = None, vlozeni=None, sirka_m: float | None = None,
           natoceni: float = 0.0, vrstva: str = "RASTR"):
    """Připojí rastr: s world filem na jeho souřadnice, jinak do bodu ``vlozeni`` s šířkou ``sirka_m``."""
    import math
    p = Path(cesta).resolve()
    if not p.exists():
        raise ValueError(f"Soubor {p.name} neexistuje.")
    w, hpx = velikost_obrazku(p)
    wf = world_file(p)
    if wf is not None:
        vl, u, v = geometrie_z_world_file(nacti_world_file(wf), w, hpx)
    else:
        if vlozeni is None or not sirka_m or sirka_m <= 0:
            raise ValueError("Obrázek nemá world file – zadejte levý dolní roh a šířku v metrech.")
        px = sirka_m / w
        t = math.radians(natoceni)
        u = (px * math.cos(t), px * math.sin(t))
        v = (-px * math.sin(t), px * math.cos(t))
        vl = (float(vlozeni[0]), float(vlozeni[1]))
    try:
        rel = os.path.relpath(p, zaklad) if zaklad is not None else str(p)
    except ValueError:
        rel = str(p)
    if vrstva not in doc.layers:
        doc.layers.add(vrstva)
    idef = doc.add_image_def(filename=rel, size_in_pixel=(w, hpx), name=p.stem)
    im = msp.add_image(idef, insert=vl, size_in_units=(w * math.hypot(*u), hpx * math.hypot(*v)), rotation=0,
                       dxfattribs={"layer": vrstva})
    im.dxf.u_pixel = (u[0], u[1], 0)
    im.dxf.v_pixel = (v[0], v[1], 0)
    if h is not None:
        h.proved(f"Rastr {p.name}", [im])
    return im


def cesta_obrazku(im, zaklad: Path | None) -> Path | None:
    """Soubor rastru z IMAGE (relativní cesta vůči výkresu, jinak absolutní)."""
    try:
        f = Path(im.image_def.dxf.filename)
    except Exception:  # noqa: BLE001
        return None
    if not f.is_absolute() and zaklad is not None:
        f = (zaklad / f).resolve()
    return f if f.exists() else None


def qt_transform(im) -> tuple[float, float, float, float, float, float]:
    """QTransform (m11, m12, m21, m22, dx, dy) z pixelů obrázku (řádek 0 nahoře) do souřadnic výkresu."""
    u, v, ins = im.dxf.u_pixel, im.dxf.v_pixel, im.dxf.insert
    hpx = im.dxf.image_size.y
    return u.x, u.y, -v.x, -v.y, ins.x + hpx * v.x, ins.y + hpx * v.y


def world_file_z_obrazku(im) -> tuple[float, float, float, float, float, float]:
    """A, D, B, E, C, F z polohy IMAGE ve výkresu (opak ``geometrie_z_world_file``)."""
    u, v, ins = im.dxf.u_pixel, im.dxf.v_pixel, im.dxf.insert
    hpx = im.dxf.image_size.y
    a, d = u.x, u.y
    b, e = -v.x, -v.y
    lhx, lhy = ins.x - hpx * b, ins.y - hpx * e  # levý horní roh
    return a, d, b, e, lhx + a / 2 + b / 2, lhy + d / 2 + e / 2


def uloz_world_file(im, zaklad: Path | None = None) -> Path:
    """Uloží world file vedle obrázku (.jgw, .pgw, .tfw…), aby rastr seděl i v QGIS, MicroStationu, AutoCADu."""
    f = cesta_obrazku(im, zaklad)
    if f is None:
        raise ValueError("Soubor obrázku se nenašel – world file nejde uložit.")
    cil = f.with_suffix(PRIPONY_WF.get(f.suffix.lower(), ".wld"))
    cil.write_text("\n".join(f"{x:.10f}" for x in world_file_z_obrazku(im)) + "\n", encoding="ascii")
    return cil
