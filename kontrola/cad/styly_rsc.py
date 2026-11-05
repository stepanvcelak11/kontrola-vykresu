"""Uživatelské styly čar MicroStationu (.rsc) ve vykreslení CAD a v tisku: prvky se stylem z knihovny se místo
plné čáry nakreslí složkami stylu (čárky, symboly plotů, hranic…) – stejně jako v MicroStationu."""

from __future__ import annotations

from pathlib import Path

_CACHE: dict[str, tuple[float, dict]] = {}


def nacti(cesty) -> dict:
    """Styly ze všech knihoven (pozdější přepíší dřívější se stejným jménem); chybné soubory se přeskočí."""
    from ..io.rsc import RscError, nacti_rsc
    out: dict = {}
    for c in cesty or []:
        p = Path(c)
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        k = str(p.resolve())
        if k not in _CACHE or _CACHE[k][0] != mt:
            try:
                _CACHE[k] = (mt, nacti_rsc(p))
            except (RscError, OSError):
                continue
        out.update(_CACHE[k][1])
    return out


_AKTIVNI: dict = {}


def nastav_aktivni(styly: dict) -> None:
    """Styly pro zobrazení na stránce Kontrola (nastaví hlavní okno podle projektu a CAD)."""
    global _AKTIVNI
    _AKTIVNI = dict(styly or {})


def aktivni() -> dict:
    return _AKTIVNI


_BEZ_STYLU = {"", "BYLAYER", "BYBLOCK", "CONTINUOUS", "SOLID", "0"}


def styl_prvku(e, styly: dict):
    """Styl z knihovny pro prvek (i převzatý z hladiny), nebo None."""
    if not styly:
        return None
    from ..io.rsc import najdi
    lt = e.dxf.get("linetype", "BYLAYER") or "BYLAYER"
    if lt.upper() == "BYLAYER":
        try:
            lt = e.doc.layers.get(e.dxf.get("layer", "0")).dxf.get("linetype", "")
        except Exception:  # noqa: BLE001
            return None
    if (lt or "").upper() in _BEZ_STYLU:
        return None
    return najdi(styly, lt)


def body_prvku(e) -> list[list[tuple[float, float]]]:
    """Lomené čáry prvku (úsečka, polylinie, oblouk, kružnice, elipsa, křivka) v souřadnicích výkresu."""
    from .upravy import geometrie
    g = geometrie(e)
    if g is None:
        return []
    if g.geom_type in ("LineString", "LinearRing"):
        return [list(g.coords)]
    if g.geom_type == "MultiLineString":
        return [list(x.coords) for x in g.geoms]
    return []


def nahrad_v_scene(scene, styly: dict, polozky: dict | None = None, entity=None) -> int:
    """V QGraphicsScene vykreslené ezdxf nahradí čáry se stylem z knihovny jeho složkami.
    ``polozky`` = {id(prvek): [položky]} (CAD), jinak se prvky najdou podle dat položek. Vrací počet prvků."""
    if not styly:
        return 0
    from ezdxf.addons.drawing.pyqt import CorrespondingDXFEntity, CorrespondingDXFParentStack
    from PySide6.QtGui import QPainterPath
    from PySide6.QtWidgets import QGraphicsPathItem

    from ..io.rsc import vykresli
    if polozky is None:
        polozky = {}
        prvky = {}
        for it in scene.items():
            stack = it.data(CorrespondingDXFParentStack) or ()
            if stack:
                continue  # části bloků – styl v buňce nechat
            e = it.data(CorrespondingDXFEntity)
            if e is not None:
                polozky.setdefault(id(e), []).append(it)
                prvky[id(e)] = e
        kandidati = list(prvky.values())
    else:
        kandidati = list(entity or [])
    n = 0
    for e in kandidati:
        if e.dxftype() not in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
            continue
        st = styl_prvku(e, styly)
        if st is None:
            continue
        its = polozky.get(id(e)) or []
        if not its:
            continue
        pero = None
        for it in its:
            if hasattr(it, "pen"):
                pero = it.pen()
                break
        cesta = QPainterPath()
        m = float(e.dxf.get("ltscale", 1.0) or 1.0)
        for cara in body_prvku(e):
            for c in vykresli(cara, st, m):
                if len(c) < 2:
                    continue
                cesta.moveTo(*c[0])
                for p in c[1:]:
                    cesta.lineTo(*p)
        if cesta.isEmpty():
            continue
        z = its[0].zValue()
        for it in its:
            if it.scene() is scene:
                scene.removeItem(it)
        nova = QGraphicsPathItem(cesta)
        if pero is not None:
            nova.setPen(pero)
        nova.setZValue(z)
        nova.setData(CorrespondingDXFEntity, e)
        scene.addItem(nova)
        polozky[id(e)] = [nova]
        n += 1
    return n
