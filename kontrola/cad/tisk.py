"""Tisk výkresu do PDF (vektorově) – z modelu v měřítku nebo z listu 1:1, a rámeček s razítkem na list.

Vykreslení stejné jako na obrazovce (ezdxf drawing add-on), ale na bílý papír: bílé čáry (barva 7)
se tisknou černě, jak to dělá MicroStation i AutoCAD. Zápis PDF přes QPdfWriter (Qt).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

PAPIRY = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0),
          "A0": (1189.0, 841.0)}  # na šířku, mm


def rozmer_papiru(papir: str, na_sirku: bool = True) -> tuple[float, float]:
    w, h = PAPIRY.get(papir.upper(), PAPIRY["A3"])
    return (w, h) if na_sirku else (h, w)


def _scena(doc, layout):
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.pyqt import PyQtBackend
    from PySide6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    ctx = RenderContext(doc)
    ctx.set_current_layout(layout)
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)  # bílá → černá
    Frontend(ctx, PyQtBackend(sc), config=cfg).draw_layout(layout, finalize=True)
    return sc


def automaticke_meritko(oblast, papir_mm, okraj: float = 10.0) -> float:
    """Nejmenší „kulaté“ měřítko 1:N, ve kterém se oblast vejde na papír."""
    x0, y0, x1, y1 = oblast
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    pw, ph = papir_mm[0] - 2 * okraj, papir_mm[1] - 2 * okraj
    n = max(w * 1000 / pw, h * 1000 / ph)
    for kulate in (100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 25000, 50000, 100000):
        if kulate >= n:
            return float(kulate)
    return float(n)


def tisk_pdf(doc, layout, cesta, papir: str = "A3", na_sirku: bool = True, meritko: float | None = None,
             oblast: tuple[float, float, float, float] | None = None, nazev: str = "") -> dict:
    """Vytiskne model (v měřítku 1:N, jednotky m) nebo list (1:1, jednotky mm) do PDF.

    Vrací {papir, meritko, oblast}. U modelu bez měřítka se zvolí nejbližší kulaté, aby se vešel."""
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    model = layout.name == "Model"
    if model:
        if oblast is None:
            from ezdxf import bbox
            ext = bbox.extents(layout, fast=True)
            if not ext.has_data:
                raise ValueError("Model je prázdný – není co tisknout.")
            oblast = (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)
        pw, ph = rozmer_papiru(papir, na_sirku)
        meritko = meritko or automaticke_meritko(oblast, (pw, ph))
        if meritko <= 0:
            raise ValueError("Měřítko musí být kladné.")
        # střed oblasti na střed papíru, papír v metrech modelu
        cx, cy = (oblast[0] + oblast[2]) / 2, (oblast[1] + oblast[3]) / 2
        mw, mh = pw * meritko / 1000, ph * meritko / 1000
        zdroj = QRectF(cx - mw / 2, cy - mh / 2, mw, mh)
    else:
        (x0, y0), (x1, y1) = layout.get_paper_limits()
        pw, ph = float(x1 - x0), float(y1 - y0)
        if pw <= 0 or ph <= 0:
            pw, ph = rozmer_papiru(papir, na_sirku)
            x0, y0 = 0.0, 0.0
        zdroj = QRectF(float(x0), float(y0), pw, ph)
        meritko = 1.0
    sc = _scena(doc, layout)
    cesta = Path(cesta)
    cesta.parent.mkdir(parents=True, exist_ok=True)
    w = QPdfWriter(str(cesta))
    w.setResolution(1200)
    w.setTitle(nazev or cesta.stem)
    w.setCreator("Kontrola výkresu – CAD")
    w.setPageLayout(QPageLayout(QPageSize(QSizeF(pw, ph), QPageSize.Millimeter), QPageLayout.Portrait,
                                QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter))
    p = QPainter(w)
    try:
        cil = QRectF(0, 0, w.width(), w.height())
        p.save()
        # DXF má osu y nahoru → převrátit (stejně jako zobrazení na obrazovce)
        p.translate(0, cil.height())
        p.scale(1, -1)
        sc.render(p, cil, zdroj, Qt.IgnoreAspectRatio)
        p.restore()
    finally:
        p.end()
    return {"papir": (pw, ph), "meritko": meritko, "oblast": (zdroj.left(), zdroj.top(), zdroj.right(),
                                                             zdroj.bottom())}


def ramecek_a_razitko(layout, h=None, udaje: dict | None = None, okraj: float = 10.0) -> list:
    """Na list nakreslí rámeček (okraj 10 mm) a razítko vpravo dole (185 × 40 mm) s údaji."""
    u = {"Název": "", "Zpracoval": "", "Škola / firma": "", "Měřítko": "", "Datum": dt.date.today().strftime(
        "%d.%m.%Y"), "Číslo výkresu": ""}
    u.update({k: v for k, v in (udaje or {}).items() if v is not None})
    (x0, y0), (x1, y1) = layout.get_paper_limits()
    x0, y0, x1, y1 = float(x0) + okraj, float(y0) + okraj, float(x1) - okraj, float(y1) - okraj
    if x1 - x0 < 200 or y1 - y0 < 60:
        raise ValueError("List je pro razítko příliš malý.")
    if "RAZITKO" not in layout.doc.layers:
        layout.doc.layers.add("RAZITKO")
    at = {"layer": "RAZITKO", "color": 7}
    nove = [layout.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                                  dxfattribs={**at, "lineweight": 50})]
    rw, rh = 185.0, 40.0
    rx, ry = x1 - rw, y0
    nove.append(layout.add_lwpolyline([(rx, ry), (x1, ry), (x1, ry + rh), (rx, ry + rh)], close=True,
                                      dxfattribs={**at, "lineweight": 35}))
    radky = [("Název", 12.0)] + [(k, 7.0) for k in ("Zpracoval", "Škola / firma", "Měřítko", "Datum",
                                                     "Číslo výkresu")]
    # Název přes celou šířku nahoře, ostatní ve dvou sloupcích
    y = ry + rh
    nove.append(layout.add_line((rx, y - 14), (x1, y - 14), dxfattribs={**at, "lineweight": 25}))
    t = layout.add_text(u["Název"] or "Název výkresu", height=5.0, dxfattribs={**at})
    t.set_placement((rx + 3, y - 10))
    nove.append(t)
    pole = radky[1:]
    for i, (k, _v) in enumerate(pole):
        sl, rd = i % 2, i // 2
        bx, by = rx + sl * rw / 2, y - 14 - (rd + 1) * (rh - 14) / 3
        lab = layout.add_text(k, height=1.8, dxfattribs={**at})
        lab.set_placement((bx + 2, by + 6.0))
        val = layout.add_text(str(u[k]) or "–", height=3.0, dxfattribs={**at})
        val.set_placement((bx + 2, by + 1.3))
        nove += [lab, val]
        if sl == 0:
            nove.append(layout.add_line((rx, by), (x1, by), dxfattribs={**at, "lineweight": 18}))
    nove.append(layout.add_line((rx + rw / 2, ry), (rx + rw / 2, y - 14), dxfattribs={**at, "lineweight": 18}))
    if h is not None:
        h.proved("Rámeček a razítko", nove)
    return nove
