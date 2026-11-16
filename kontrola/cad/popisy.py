"""Rozmístění popisů bodů: čísla a výšky bodů, které přeškrtává čára nebo překrývá jiný popis, se posunou
na volné místo kolem svého bodu (vpravo nahoře, vpravo dole, vlevo…). Totéž hlídá Kontrola
(„Popis přeškrtnutý čarou“, „Popisy přes sebe“) – tady se to opraví jedním příkazem a jedním Zpět."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
import shapely
from ezdxf.math import Matrix44
from shapely.geometry import Point, Polygon

from . import upravy as U

_CISLO = re.compile(r"^[+-]?\d[\d.,/\-]*[a-zA-Z]?$")
SIRKA_ZNAKU = 0.72  # odhad šířky znaku v násobcích výšky písma – stejný jako v kontrole kartografie


@dataclass
class Vysledek:
    posunuto: int = 0
    nevyreseno: int = 0
    v_poradku: int = 0
    nove: list = None
    stare: list = None


def _kotva(e) -> tuple[float, float]:
    d = e.dxf
    p = d.align_point if (d.get("halign", 0) or d.get("valign", 0)) and d.hasattr("align_point") else d.insert
    return float(p[0]), float(p[1])


def _rozmer(e) -> tuple[float, float]:
    h = max(float(e.dxf.get("height", 0.0) or 0.0), 0.01)
    return max(1, len((e.dxf.text or "").strip())) * h * SIRKA_ZNAKU * float(e.dxf.get("width", 1.0) or 1.0), h


def _roh(e) -> tuple[float, float]:
    """Levý dolní roh textu v souřadnicích textu (vůči kotvě) podle zarovnání."""
    w, h = _rozmer(e)
    return ({0: 0.0, 1: -w / 2, 2: -w}.get(e.dxf.get("halign", 0), 0.0),
            {0: 0.0, 1: 0.0, 2: -h / 2, 3: -h}.get(e.dxf.get("valign", 0), 0.0))


def obdelnik(e, posun=(0.0, 0.0)) -> Polygon:
    w, h = _rozmer(e)
    x0, y0 = _roh(e)
    a = math.radians(float(e.dxf.get("rotation", 0.0) or 0.0))
    ca, sa = math.cos(a), math.sin(a)
    px, py = _kotva(e)
    px, py = px + posun[0], py + posun[1]
    return Polygon([(px + cx * ca - cy * sa, py + cx * sa + cy * ca)
                    for cx, cy in ((x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h))])


def _polohy(w: float, h: float) -> list[tuple[float, float]]:
    """Levý dolní roh popisu vůči bodu (v osách textu) – pořadí = kartografická přednost (vpravo nahoře první)."""
    g = 0.35 * h
    return [(g, g), (g, -h - g), (-w - g, g), (-w - g, -h - g), (g, -h / 2), (-w - g, -h / 2),
            (-w / 2, g + 0.2 * h), (-w / 2, -h - g - 0.2 * h),
            (2.5 * g, 2.5 * g), (2.5 * g, -h - 2.5 * g), (-w - 2.5 * g, 2.5 * g), (-w - 2.5 * g, -h - 2.5 * g)]


def rozmisti(msp, historie, texty=None, max_vzdalenost: float = 4.0, jen_cisla: bool = False) -> Vysledek:
    """Posune popisy bodů (TEXT u značky bodu), které kříží čára nebo překrývá jiný popis či značka.

    ``texty`` = jen tyto prvky (výběr), jinak všechny texty modelu, které mají do ``max_vzdalenost`` × výška písma
    značku bodu (POINT / buňku). Popisy, které jsou v pořádku, zůstávají na místě."""
    vse = [e for e in msp if e.dxftype() == "TEXT" and (e.dxf.text or "").strip()]
    kandidati = [e for e in (texty if texty is not None else vse) if e.dxftype() == "TEXT" and (e.dxf.text or "").strip()]
    if jen_cisla or texty is None:
        # bez výběru jen čísla a výšky bodů (12, 4001-3, 256.48) – názvy ulic a popisy ploch u bodu zůstávají
        kandidati = [e for e in kandidati if _CISLO.match((e.dxf.text or "").strip())]
    body = [e for e in msp if e.dxftype() in ("POINT", "INSERT")]
    v = Vysledek(nove=[], stare=[])
    if not kandidati or not body:
        return v
    bxy = np.array([(float((e.dxf.location if e.dxftype() == "POINT" else e.dxf.insert)[0]),
                     float((e.dxf.location if e.dxftype() == "POINT" else e.dxf.insert)[1])) for e in body])
    strom_bodu = shapely.STRtree(np.array([Point(x, y) for x, y in bxy], dtype=object))
    cary = []
    for e in msp:
        if e.dxftype() in ("TEXT", "MTEXT", "POINT", "INSERT", "HATCH", "IMAGE"):
            continue
        g = U.geometrie(e)
        if g is not None and not g.is_empty and g.length > 0:
            cary.append(g)
    strom_car = shapely.STRtree(np.array(cary, dtype=object)) if cary else None
    boxy = {id(e): obdelnik(e) for e in vse}

    def cena(e, box: Polygon, vlastni=None) -> tuple[float, bool]:
        """Cena polohy (0 = volno) a zda by ji hlásila Kontrola (čára přes ≥ 40 % šířky, překryv ≥ 25 %)."""
        w, h = _rozmer(e)
        vnitrek = box.buffer(-min(0.1, h * 0.15))
        c, chyba = 0.0, False
        if strom_car is not None:
            for j in strom_car.query(vnitrek, predicate="intersects"):
                g = cary[j]
                if g.length < w:  # krátká čárka patří k popisu (podtržení, odkazová čára) – kontrola ji také nehlásí
                    continue
                podil = g.intersection(vnitrek).length / w
                c += 10.0 * podil
                chyba = chyba or podil >= 0.4
        for o in vse:
            if o is e:
                continue
            ob = boxy[id(o)]
            if ob.intersects(box):
                podil = ob.intersection(box).area / max(min(box.area, ob.area), 1e-12)
                c += 6.0 * podil
                chyba = chyba or podil >= 0.25
        for j in strom_bodu.query(vnitrek, predicate="intersects"):
            if vlastni is not None and math.dist(bxy[int(j)], vlastni) < 1e-3:
                continue  # vlastní bod (a jeho druhá značka na stejném místě) pod popisem nevadí
            c += 2.0
        return c, chyba

    for e in kandidati:
        w, h = _rozmer(e)
        kx, ky = _kotva(e)
        stred = boxy[id(e)].centroid
        i = strom_bodu.nearest(stred)
        bx, by = bxy[int(i)]
        if boxy[id(e)].distance(Point(bx, by)) > max_vzdalenost * h:
            continue  # popis nepatří k žádnému bodu (název ulice, popis plochy) – nechat být
        c0, chyba0 = cena(e, boxy[id(e)], (bx, by))
        if not chyba0:  # co by Kontrola nehlásila, zůstává, jak to uživatel umístil
            v.v_poradku += 1
            continue
        a = math.radians(float(e.dxf.get("rotation", 0.0) or 0.0))
        ca, sa = math.cos(a), math.sin(a)
        rx, ry = _roh(e)
        nej, nej_posun = c0 + 100.0, None
        for poradi, (lx, ly) in enumerate(_polohy(w, h)):
            # kotva tak, aby levý dolní roh ležel v (lx, ly) od bodu v osách textu
            ox, oy = lx - rx, ly - ry
            nx, ny = bx + ox * ca - oy * sa, by + ox * sa + oy * ca
            posun = (nx - kx, ny - ky)
            c, chyba = cena(e, obdelnik(e, posun), (bx, by))
            c += 0.01 * poradi + (100.0 if chyba else 0.0)
            if c < nej - 1e-9:
                nej, nej_posun = c, posun
                if c < 0.2:
                    break
        if nej_posun is None:
            v.nevyreseno += 1
            continue
        k = U._kopie(e)
        k.transform(Matrix44.translate(nej_posun[0], nej_posun[1], 0))
        msp.add_entity(k)
        boxy[id(e)] = obdelnik(k)  # další popisy se vyhýbají už nové poloze
        v.nove.append(k)
        v.stare.append(e)
        if nej >= 100.0:
            v.nevyreseno += 1
        else:
            v.posunuto += 1
    if v.nove:
        historie.proved("Rozmístění popisů", v.nove, v.stare)
    return v
