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


def _scena(doc, layout, styly: dict | None = None):
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.pyqt import PyQtBackend
    from PySide6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    ctx = RenderContext(doc)
    ctx.set_current_layout(layout)
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)  # bílá → černá
    Frontend(ctx, PyQtBackend(sc), config=cfg).draw_layout(layout, finalize=True)
    if styly:
        from .styly_rsc import nahrad_v_scene
        nahrad_v_scene(sc, styly)
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
             oblast: tuple[float, float, float, float] | None = None, nazev: str = "",
             styly: dict | None = None) -> dict:
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
    sc = _scena(doc, layout, styly)
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


# ------------------------------------------------------------------ arch (papír pod výkresem v modelu)
# Jako v tiskovém dialogu MicroStationu: nastaví se velikost papíru a měřítko, obdélník papíru se v modelu
# posune pod výkres a tiskne se přesně to, co je na papíře. Uloží se do výkresu (vlastní vlastnosti DXF).
from dataclasses import dataclass  # noqa: E402

_ARCH_KLICE = ("ARCH_PAPIR", "ARCH_SIRKA", "ARCH_VYSKA", "ARCH_MERITKO", "ARCH_X", "ARCH_Y", "ARCH_NATOCENI")


@dataclass
class Arch:
    papir: str = "A3"  # název (A4…A0) nebo „vlastní“
    sirka: float = 420.0  # mm (už podle orientace)
    vyska: float = 297.0
    meritko: float = 1000.0  # 1:N
    x: float = 0.0  # levý dolní roh papíru v souřadnicích modelu (m)
    y: float = 0.0
    natoceni: float = 0.0  # stupně proti směru hodin, kolem levého dolního rohu

    @property
    def rozmer_m(self) -> tuple[float, float]:
        return self.sirka * self.meritko / 1000.0, self.vyska * self.meritko / 1000.0

    def _bod(self, u: float, v: float) -> tuple[float, float]:
        import math
        r = math.radians(self.natoceni)
        return self.x + u * math.cos(r) - v * math.sin(r), self.y + u * math.sin(r) + v * math.cos(r)

    def rohy(self, okraj_mm: float = 0.0) -> list[tuple[float, float]]:
        w, h = self.rozmer_m
        o = okraj_mm * self.meritko / 1000.0
        return [self._bod(o, o), self._bod(w - o, o), self._bod(w - o, h - o), self._bod(o, h - o)]

    def obdelnik(self) -> tuple[float, float, float, float]:
        """Obálka papíru v modelu (u natočeného archu větší než papír)."""
        r = self.rohy()
        return min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)

    def stred(self) -> tuple[float, float]:
        w, h = self.rozmer_m
        return self._bod(w / 2, h / 2)

    def na_stred(self, cx: float, cy: float) -> None:
        sx, sy = self.stred()
        self.x, self.y = self.x + cx - sx, self.y + cy - sy

    def otoc(self, uhel: float) -> None:
        """Natočí arch kolem jeho středu (střed zůstane na místě)."""
        c = self.stred()
        self.natoceni = (uhel + 180.0) % 360.0 - 180.0
        self.na_stred(*c)

    def popis(self) -> str:
        return (f"{self.papir} {self.sirka:g} × {self.vyska:g} mm, 1:{self.meritko:g}"
                + (f", natočení {self.natoceni:g}°" if abs(self.natoceni) > 1e-9 else ""))


def papir_z_textu(text: str, na_sirku: bool = True) -> tuple[str, float, float]:
    """„A3“, „A4 na výšku“, „594x420“, „vlastní 500 300“ → (název, šířka, výška) v mm."""
    import re
    t = (text or "").strip().lower()
    vyska_napred = "výšku" in t or "vysku" in t or "portrait" in t
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[x×* ]\s*(\d+(?:[.,]\d+)?)", t)
    if m:
        w, h = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        if w <= 0 or h <= 0:
            raise ValueError("Rozměry papíru musí být kladné.")
        return "vlastní", w, h
    m = re.search(r"\ba([0-4])\b", t)
    nazev = f"A{m.group(1)}" if m else "A3"
    w, h = rozmer_papiru(nazev, na_sirku and not vyska_napred)
    return nazev, w, h


def arch_z_textu(text: str) -> tuple[str, float, float, float | None]:
    """„A3 1000“, „A4 na výšku 1:500“, „500x300 2000“ → (název, šířka, výška, měřítko nebo None)."""
    import re
    t = (text or "").strip()
    meritko = None
    m = re.search(r"1\s*:\s*(\d+(?:[.,]\d+)?)", t)
    if m:
        meritko = float(m.group(1).replace(",", "."))
        t = t[:m.start()] + t[m.end():]
    else:
        bez = re.sub(r"\d+(?:[.,]\d+)?\s*[x×*]\s*\d+(?:[.,]\d+)?", " ", t)
        cisla = re.findall(r"(?<![\w.,])(\d+)(?![\w.,])", bez)
        if cisla:
            meritko = float(cisla[-1])
            t = re.sub(rf"(?<![\w.,]){cisla[-1]}(?![\w.,])\s*$", "", t.rstrip())
    nazev, w, h = papir_z_textu(t)
    return nazev, w, h, meritko


def _slovnik(doc, vytvor: bool):
    rd = doc.rootdict
    if "KONTROLA_ARCH" in rd:
        return rd["KONTROLA_ARCH"]
    return rd.add_new_dict("KONTROLA_ARCH") if vytvor else None


def nacti_arch(doc) -> Arch | None:
    d = _slovnik(doc, False)
    hodn = {}
    if d is not None:
        for k in _ARCH_KLICE:
            if k in d:
                hodn[k] = d[k].dxf.get("value", "")
    else:  # starší uložení do vlastních vlastností
        cv = doc.header.custom_vars
        hodn = {k: cv.get(k) for k in _ARCH_KLICE if cv.has_tag(k)}
    if "ARCH_MERITKO" not in hodn:
        return None
    try:
        return Arch(hodn.get("ARCH_PAPIR") or "A3", float(hodn["ARCH_SIRKA"]), float(hodn["ARCH_VYSKA"]),
                    float(hodn["ARCH_MERITKO"]), float(hodn["ARCH_X"]), float(hodn["ARCH_Y"]),
                    float(hodn.get("ARCH_NATOCENI") or 0.0))
    except (KeyError, TypeError, ValueError):
        return None


def uloz_arch(doc, a: Arch | None) -> None:
    d = _slovnik(doc, a is not None)
    if a is None:
        if d is not None:
            del doc.rootdict["KONTROLA_ARCH"]
        return
    for k, v in zip(_ARCH_KLICE, (a.papir, f"{a.sirka:.3f}", f"{a.vyska:.3f}", f"{a.meritko:g}", f"{a.x:.4f}",
                                  f"{a.y:.4f}", f"{a.natoceni:.6f}")):
        if k in d:
            d[k].dxf.value = v
        else:
            d.add_dict_var(k, v)


def tisk_archu(doc, layout, cesta, a: Arch, nazev: str = "", styly: dict | None = None) -> dict:
    """Vytiskne přesně to, co leží na archu (papír v modelu), v měřítku archu – i natočený arch."""
    if abs(a.natoceni) < 1e-12:
        x0, y0, x1, y1 = a.obdelnik()
        return _tisk_oblasti(doc, layout, cesta, a.sirka, a.vyska, a.meritko, (x0, y0, x1 - x0, y1 - y0), nazev,
                             styly)
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    x0, y0, x1, y1 = a.obdelnik()
    src = QRectF(x0, y0, x1 - x0, y1 - y0)
    sc = _scena(doc, layout, styly)
    cesta = Path(cesta)
    cesta.parent.mkdir(parents=True, exist_ok=True)
    w = QPdfWriter(str(cesta))
    w.setResolution(1200)
    w.setTitle(nazev or cesta.stem)
    w.setCreator("Kontrola výkresu – CAD")
    w.setPageLayout(QPageLayout(QPageSize(QSizeF(a.sirka, a.vyska), QPageSize.Millimeter), QPageLayout.Portrait,
                                QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter))
    p = QPainter(w)
    try:
        k = w.width() / a.sirka * 1000.0 / a.meritko  # px na metr modelu
        p.setTransform(transformace_archu(a, k, w.height()))
        p.setClipRect(src)
        sc.render(p, src, src, Qt.IgnoreAspectRatio)
    finally:
        p.end()
    return {"papir": (a.sirka, a.vyska), "meritko": a.meritko, "oblast": (x0, y0, x1, y1)}


def transformace_archu(a: Arch, k: float, vyska_px: float):
    """QTransform model → papír (px, osa y dolů): posun do rohu archu, natočení zpět, měřítko, převrácení y."""
    import math

    from PySide6.QtGui import QTransform
    r = math.radians(-a.natoceni)
    c, s_ = math.cos(r) * k, math.sin(r) * k
    # u = c·(X−x) − s·(Y−y),  v = s·(X−x) + c·(Y−y);  px = u,  py = H − v
    # QTransform(m11, m12, m21, m22, dx, dy): x' = m11·x + m21·y + dx, y' = m12·x + m22·y + dy
    return QTransform(c, -s_, -s_, -c, -c * a.x + s_ * a.y, vyska_px + s_ * a.x + c * a.y)


def _tisk_oblasti(doc, layout, cesta, pw, ph, meritko, rect, nazev, styly=None) -> dict:
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    zdroj = QRectF(*rect)
    sc = _scena(doc, layout, styly)
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
        p.translate(0, cil.height())
        p.scale(1, -1)
        sc.render(p, cil, zdroj, Qt.IgnoreAspectRatio)
    finally:
        p.end()
    return {"papir": (pw, ph), "meritko": meritko, "oblast": (zdroj.left(), zdroj.top(), zdroj.right(),
                                                             zdroj.bottom())}
