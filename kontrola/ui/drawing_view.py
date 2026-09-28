"""Zobrazení výkresu v QGraphicsView.

* Prvky se kreslí seskupeně po vrstvách (jedna cesta na kombinaci barvy,
  tloušťky a stylu čáry), takže i výkresy se statisíci prvků jsou plynulé.
* Souřadnice se posouvají k počátku výkresu (S-JTSK má velká čísla) a osa Y
  se otáčí, aby sever byl nahoře.
* Chyby se zobrazují jako kroužky s pevnou velikostí na obrazovce
  (:class:`IssueMarker`), nezávisle na přiblížení.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF, QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView)

from ..checks.base import Issue, Severity
from ..model import Drawing, Feature, GeomType

SEVERITY_COLORS = {
    Severity.CHYBA: QColor(220, 30, 30),
    Severity.VAROVANI: QColor(245, 140, 0),
    Severity.INFO: QColor(30, 110, 230),
}

# vzory čárkování (v pixelech / šířkách pera) podle názvu stylu čáry
_DASHES = [
    ("DASHDOTDOT", [8, 3, 1, 3, 1, 3]), ("DIVIDE", [8, 3, 1, 3, 1, 3]),
    ("DASHDOT", [8, 3, 1, 3]), ("CENTER", [12, 3, 3, 3]), ("PHANTOM", [12, 3, 3, 3, 3, 3]),
    ("BORDER", [8, 3, 8, 3, 1, 3]),
    ("DASHED", [6, 4]), ("HIDDEN", [3, 3]), ("DOT", [1, 3]), ("DASH", [6, 4]),
]
# MicroStation standardní styly 0–7 (po exportu často jako názvy "0"–"7")
_MS_STYLES = {"1": [1, 3], "2": [4, 4], "3": [10, 4], "4": [8, 3, 1, 3], "5": [3, 3],
              "6": [8, 3, 1, 3, 1, 3], "7": [12, 3, 3, 3]}


def dash_pattern(linetype: str) -> list[float] | None:
    lt = (linetype or "").upper()
    if lt in ("", "CONTINUOUS", "BYLAYER", "BYBLOCK", "0", "SOLID"):
        return None
    digits = "".join(ch for ch in lt if ch.isdigit())
    if lt in _MS_STYLES:
        return _MS_STYLES[lt]
    for key, pat in _DASHES:
        if key in lt:
            return pat
    if lt.startswith(("DGN", "STYLE", "LS")) and digits in _MS_STYLES:
        return _MS_STYLES[digits]
    return [5, 3]


CUSTOM_STYLE = re.compile(r"^\d+\.\d+[A-Z]?$")


def is_custom_style(linetype: str) -> bool:
    """Uživatelský styl MicroStationu (2.103, 5.303…) – čára se značkami, v DXF bez čárkování."""
    return bool(CUSTOM_STYLE.match((linetype or "").upper()))


def weight_px(mm: float) -> float:
    """Tloušťka čáry v pixelech podobně jako v MicroStationu (tloušťka 0 = 1 px, 2 = 3 px, 4 = 5 px)."""
    if mm <= 0.001:
        return 1.0
    return 1.0 + max(1, round(mm / 0.14))


def style_mark_kind(linetype: str, popis: str = "") -> str:
    """Jakou značku styl kreslí: „oblouky“ (ohradní zeď 2.16x) nebo „carky“ (ploty a ostatní)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", f"{linetype} {popis}".lower()).encode("ascii", "ignore").decode()
    if re.search(r"\bzed\b|\bzdi\b|zdeny", t) or (linetype or "").upper().startswith("2.16"):
        return "oblouky"
    return "carky"


def add_style_marks(path: QPainterPath, pts: list[QPointF], scale: float, kind: str = "carky"):
    """Značky uživatelského stylu na jedné straně čáry: krátké kolmé čárky (plot) nebo obloučky (zeď)."""
    step = 1.2 * max(scale, 0.05)
    tick = 0.35 * max(scale, 0.05)
    rad = 0.3 * max(scale, 0.05)
    carry = step / 2
    for a, b in zip(pts, pts[1:]):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(dx, dy)
        if L <= 1e-9:
            continue
        ux, uy = dx / L, dy / L
        nx, ny = uy, -ux  # levá strana ve směru kreslení (osa Y scény je otočená)
        s = carry
        while s < L:
            px, py = a.x() + ux * s, a.y() + uy * s
            if kind == "oblouky":  # půlkruh vybočený na stranu vlastníka, konce leží na čáře
                for k in range(13):
                    t = math.pi * k / 12
                    qx = px - ux * rad * math.cos(t) + nx * rad * math.sin(t)
                    qy = py - uy * rad * math.cos(t) + ny * rad * math.sin(t)
                    (path.moveTo if k == 0 else path.lineTo)(qx, qy)
            else:
                path.moveTo(px, py)
                path.lineTo(px + nx * tick, py + ny * tick)
            s += step
        carry = s - L


def display_color(rgb: tuple[int, int, int], light_bg: bool) -> QColor:
    r, g, b = rgb
    if light_bg and min(r, g, b) > 215:
        return QColor(0, 0, 0)
    if not light_bg and max(r, g, b) < 50:
        return QColor(255, 255, 255)
    return QColor(r, g, b)


class LayerItem(QGraphicsItem):
    """Neviditelný kontejner prvků jedné vrstvy (vypnutí vrstvy = setVisible)."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.setFlag(QGraphicsItem.ItemHasNoContents, True)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF()

    def paint(self, painter, option, widget=None):  # pragma: no cover - nic nekreslí
        pass


class IssueMarker(QGraphicsItem):
    """Kroužek chyby s popiskem. Velikost je pevná v pixelech obrazovky."""

    RADIUS = 13.0
    show_labels = True

    def __init__(self, issue: Issue):
        super().__init__()
        self.issue = issue
        self.highlighted = False
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10_000)
        self.setToolTip(f"#{issue.number} {issue.check_name}\n{issue.message}")
        self._font = QFont()
        self._font.setPointSizeF(8.5)
        lab = issue.label()
        self._label = lab if len(lab) <= 46 else lab[:44].rstrip(" ,:–") + "…"  # celé znění je v tooltipu
        self.label_on = True  # vypne se, když by se popisek překrýval s jiným (viz DrawingView._declutter)
        fm = QFontMetricsF(self._font)
        self._label_w = fm.horizontalAdvance(self._label) + 10
        self._label_h = fm.height() + 4

    def color(self) -> QColor:
        if self.issue.state == "opraveno":
            return QColor(34, 170, 80, 200)
        if self.issue.state == "ignorovat":
            return QColor(140, 140, 150, 170)
        return QColor(SEVERITY_COLORS.get(self.issue.severity, QColor(128, 128, 128)))

    def boundingRect(self) -> QRectF:  # noqa: N802
        r = self.RADIUS + 8
        rect = QRectF(-r, -r, 2 * r, 2 * r)
        if IssueMarker.show_labels and self.label_on:
            rect = rect.united(QRectF(self.RADIUS + 2, -self.RADIUS - self._label_h,
                                      self._label_w + 4, self._label_h + 4))
        return rect

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        r = self.RADIUS + 4
        p.addEllipse(QPointF(0, 0), r, r)
        return p

    def set_label_on(self, on: bool):
        if on != self.label_on:
            self.prepareGeometryChange()
            self.label_on = on
            self.update()

    def label_rect(self) -> QRectF:
        r = self.RADIUS
        return QRectF(r + 4, -r - self._label_h + 2, self._label_w, self._label_h)

    def set_highlighted(self, on: bool):
        if on != self.highlighted:
            self.highlighted = on
            self.setZValue(10_001 if on else 10_000)
            self.update()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        c = self.color()
        r = self.RADIUS
        if self.highlighted:
            halo = QColor(255, 255, 0, 200)
            painter.setPen(QPen(halo, 7))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 3, r + 3)
        pen = QPen(c, 3 if self.highlighted else 2.2)
        painter.setPen(pen)
        fill = QColor(c)
        fill.setAlpha(35)
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(0, 0), r, r)
        state = self.issue.state
        if state == "opraveno":  # fajfka
            painter.setPen(QPen(c, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline([QPointF(-6, 0), QPointF(-2, 4.5), QPointF(6.5, -5)])
        elif state == "ignorovat":  # křížek
            painter.setPen(QPen(c, 2.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(-5, -5), QPointF(5, 5))
            painter.drawLine(QPointF(-5, 5), QPointF(5, -5))
        else:
            painter.setPen(QPen(c, 1.5))
            painter.drawLine(QPointF(-3, 0), QPointF(3, 0))
            painter.drawLine(QPointF(0, -3), QPointF(0, 3))
        if IssueMarker.show_labels and self.label_on and state == "nová":
            rect = QRectF(r + 4, -r - self._label_h + 2, self._label_w, self._label_h)
            bg = QColor(255, 255, 255, 225)
            painter.setPen(QPen(c, 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setFont(self._font)
            painter.setPen(QColor(20, 20, 20))
            painter.drawText(rect, Qt.AlignCenter, self._label)


class PathBuilder:
    """Převod geometrie na QPainterPath (bez grafických prvků – lze volat i mimo hlavní vlákno)."""

    def __init__(self, origin: tuple[float, float]):
        self.origin = origin

    def to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(x - self.origin[0], -(y - self.origin[1]))

    def add_geometry(self, path: QPainterPath, geom):
        if geom is None or geom.is_empty:
            return
        gt = geom.geom_type
        if gt == "LineString":
            self.add_coords(path, geom.coords, False)
        elif gt == "Polygon":
            self.add_coords(path, geom.exterior.coords, True)
            for i in geom.interiors:
                self.add_coords(path, i.coords, True)
        elif hasattr(geom, "geoms"):
            for g in geom.geoms:
                self.add_geometry(path, g)

    def add_coords(self, path: QPainterPath, coords: Iterable, closed: bool):
        ox, oy = self.origin
        pts = [QPointF(c[0] - ox, oy - c[1]) for c in coords]
        if not pts:
            return
        path.addPolygon(QPolygonF(pts))
        if closed:
            path.closeSubpath()

    def add_insert(self, path: QPainterPath, f: Feature, drawing: Drawing, cross: float,
                   block_cache: dict[str, QPainterPath]):
        bg = drawing.blocks.get(f.block_name or "")
        c = self.to_scene(*f.vertices[0])
        if bg is None or (not bg.paths and not bg.points):
            path.moveTo(c.x() - cross, c.y() - cross); path.lineTo(c.x() + cross, c.y() + cross)
            path.moveTo(c.x() - cross, c.y() + cross); path.lineTo(c.x() + cross, c.y() - cross)
            return
        sub = block_cache.get(bg.name)
        if sub is None:
            sub = QPainterPath()
            for pts, closed in zip(bg.paths, bg.closed):
                sub.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
                if closed:
                    sub.closeSubpath()
            for x, y in bg.points:
                sub.moveTo(x - cross / 3, y)
                sub.lineTo(x + cross / 3, y)
            block_cache[bg.name] = sub
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(-f.rotation)
        t.scale(f.scale[0], -f.scale[1])
        t.translate(-bg.base_point[0], -bg.base_point[1])
        path.addPath(t.map(sub))


@dataclass
class PreparedDrawing:
    drawing: Drawing
    origin: tuple[float, float]
    groups: dict[str, dict[tuple, QPainterPath]]
    fills: dict[str, dict[tuple, QPainterPath]]
    texts: list[Feature]


def prepare_drawing(drawing: Drawing) -> PreparedDrawing:
    """Sestaví cesty pro kreslení seskupené podle vrstvy a stylu. Bezpečné ve vlákně na pozadí."""
    b = drawing.bounds() or (0, 0, 100, 100)
    origin = (b[0], b[1])
    pb = PathBuilder(origin)
    diag = max(1.0, math.hypot(b[2] - b[0], b[3] - b[1]))
    cross = max(0.1, min(0.5, diag / 800))
    groups: dict[str, dict[tuple, QPainterPath]] = {}
    fills: dict[str, dict[tuple, QPainterPath]] = {}
    texts: list[Feature] = []
    block_cache: dict[str, QPainterPath] = {}
    for f in drawing.features:
        if f.geom_type == GeomType.TEXT:
            texts.append(f)
            continue
        if f.dxftype == "HATCH":
            path = fills.setdefault(f.layer, {}).setdefault((f.color_rgb, f.fill), QPainterPath())
            pb.add_geometry(path, f.geometry)
            continue
        custom = is_custom_style(f.linetype)
        key = (f.color_rgb, round(f.lineweight, 2),
               None if custom else (dash_pattern(f.linetype) and f.linetype.upper()))
        path = groups.setdefault(f.layer, {}).setdefault(key, QPainterPath())
        if custom and f.geom_type in (GeomType.LINIE, GeomType.POLYGON) and f.geometry is not None:
            g = f.geometry.exterior if f.geom_type == GeomType.POLYGON else f.geometry
            if g.geom_type in ("LineString", "LinearRing"):
                pts = [pb.to_scene(c[0], c[1]) for c in g.coords]
                marks = groups[f.layer].setdefault(key + ("#znacky",), QPainterPath())
                kind = style_mark_kind(f.linetype, drawing.linetype_popis.get(f.linetype.upper(), ""))
                add_style_marks(marks, pts, f.ltscale or 1.0, kind)
        if f.dxftype == "INSERT":
            pb.add_insert(path, f, drawing, cross, block_cache)
            for (t, x, y, h, rot) in f.display_texts:
                texts.append(Feature(fid=-1, dxftype="ATTRIB", geom_type=GeomType.TEXT, geometry=None,
                                     layer=f.layer, color_rgb=f.color_rgb, text=t, text_height=h,
                                     rotation=rot, vertices=[(x, y)]))
        elif f.dxftype == "CIRCLE":
            path.addEllipse(pb.to_scene(*f.vertices[0]), f.radius, f.radius)
        elif f.dxftype == "POINT":
            c = pb.to_scene(*f.vertices[0])
            path.moveTo(c.x() - cross, c.y()); path.lineTo(c.x() + cross, c.y())
            path.moveTo(c.x(), c.y() - cross); path.lineTo(c.x(), c.y() + cross)
        else:
            pb.add_geometry(path, f.geometry)
    return PreparedDrawing(drawing, origin, groups, fills, texts)


class DrawingView(QGraphicsView):
    """Zobrazení výkresu s kroužky chyb."""

    cursorMoved = Signal(float, float)
    markerClicked = Signal(int)  # číslo chyby
    fileDropped = Signal(str)
    pointPicked = Signal(float, float)
    featureClicked = Signal(int)  # klik na prvek výkresu (fid), -1 = do prázdna  # klik v režimu výběru bodu (souřadnice výkresu)

    def set_pick_mode(self, on: bool):
        self._pick_mode = on
        if on:
            self.viewport().setCursor(Qt.CrossCursor)
        else:
            self.viewport().unsetCursor()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.origin = (0.0, 0.0)
        self.light_bg = False
        self.drawing: Drawing | None = None
        self.layer_items: dict[str, LayerItem] = {}
        self.markers: dict[int, IssueMarker] = {}
        self.background: QGraphicsPixmapItem | None = None
        self._content_rect = QRectF()
        self._press_pos = None
        self._last_pos = None
        self._panning = False
        self._highlight: QGraphicsPathItem | None = None
        self.ms_look = True  # styly a tloušťky čar jako v MicroStationu
        self.set_light_background(False)

    # ---------------------------------------------------------------- souřadnice
    def to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(x - self.origin[0], -(y - self.origin[1]))

    def visible_world_rect(self) -> tuple[float, float, float, float]:
        """Právě zobrazená část výkresu (xmin, ymin, xmax, ymax) v souřadnicích výkresu."""
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        x0, y1 = self.from_scene(r.topLeft())
        x1, y0 = self.from_scene(r.bottomRight())
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def from_scene(self, p: QPointF) -> tuple[float, float]:
        return p.x() + self.origin[0], -p.y() + self.origin[1]

    # ---------------------------------------------------------------- vzhled
    def set_ms_look(self, on: bool):
        self.ms_look = bool(on)
        self.set_light_background(self.light_bg)  # překreslí výkres a zachová pohled

    def set_light_background(self, light: bool):
        self.light_bg = light
        self.setBackgroundBrush(QBrush(QColor(250, 250, 250) if light else QColor(18, 18, 24)))
        if self.drawing is not None:
            vis = {n: it.isVisible() for n, it in self.layer_items.items()}
            center = self.mapToScene(self.viewport().rect().center())
            tr = self.transform()
            self._build(self.drawing)
            for n, v in vis.items():
                self.set_layer_visible(n, v)
            self.setTransform(tr)
            self.centerOn(center)

    def _view_state(self):
        t = self.transform()
        return (round(t.m11(), 9), round(t.m22(), 9), self.horizontalScrollBar().value(),
                self.verticalScrollBar().value(), self.viewport().width(), self.viewport().height(),
                len(self.markers), IssueMarker.show_labels)

    def request_declutter(self):
        if not hasattr(self, "_declutter_timer"):
            self._declutter_timer = QTimer(self)
            self._declutter_timer.setSingleShot(True)
            self._declutter_timer.setInterval(60)
            self._declutter_timer.timeout.connect(self._declutter)
        self._declutter_timer.start()

    def _declutter(self):
        """Popisky kroužků se nesmí překrývat: přednost mají závažnější chyby, ostatní ukáže přiblížení."""
        self._last_view = self._view_state()
        if not IssueMarker.show_labels:
            return
        placed: list[QRectF] = []
        vr = QRectF(self.viewport().rect()).adjusted(-50, -50, 50, 50)
        items = [m for m in self.markers.values() if m.isVisible()]
        items.sort(key=lambda m: (m.issue.state != "nová", m.issue.severity.rank, m.issue.number))
        for m in items:
            p = self.mapFromScene(m.scenePos())
            if not vr.contains(QPointF(p)):
                m.set_label_on(False)
                continue
            lr = m.label_rect().translated(p.x(), p.y())
            circle = QRectF(p.x() - m.RADIUS, p.y() - m.RADIUS, 2 * m.RADIUS, 2 * m.RADIUS)
            ok = (m.issue.state == "nová" and m.issue.severity != Severity.INFO  # info jen kroužek + tooltip
                  and not any(lr.intersects(o) for o in placed))
            m.set_label_on(ok or m.highlighted)
            placed.append(circle)
            if ok:
                placed.append(lr)

    def drawForeground(self, painter: QPainter, rect: QRectF):  # noqa: N802
        """Prázdný výkres: nápověda uprostřed okna."""
        super().drawForeground(painter, rect)
        if self.markers and getattr(self, "_last_view", None) != self._view_state():
            self.request_declutter()
        if self.drawing is not None:
            return
        painter.save()
        painter.resetTransform()
        vr = QRectF(self.viewport().rect())
        col = QColor(90, 90, 100) if self.light_bg else QColor(150, 155, 170)
        box = QRectF(0, 0, min(460.0, vr.width() - 40), 150)
        box.moveCenter(vr.center())
        pen = QPen(col, 1.5, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawRoundedRect(box, 12, 12)
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 1.35)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(box.adjusted(10, 22, -10, -70), Qt.AlignHCenter | Qt.AlignTop,
                         "Přetáhněte sem výkres (DXF)")
        f.setPointSizeF(self.font().pointSizeF())
        f.setBold(False)
        painter.setFont(f)
        painter.drawText(box.adjusted(14, 64, -14, -10), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                         "nebo Soubor → Otevřít výkres (Ctrl+O). Pak Zkontrolovat (F5).\n"
                         "Tabulku atributů od učitele vložte na záložce Zadání.")
        painter.restore()

    # ---------------------------------------------------------------- výkres
    def clear_drawing(self):
        self.clear_overlay()
        sc = self.scene()
        for m in list(self.markers.values()):
            sc.removeItem(m)
        self.markers.clear()
        for it in list(self.layer_items.values()):
            sc.removeItem(it)
        self.layer_items.clear()
        if self._highlight is not None:
            sc.removeItem(self._highlight)
            self._highlight = None
        self.drawing = None
        self.viewport().update()

    def set_drawing(self, drawing: Drawing, prepared: "PreparedDrawing | None" = None):
        """Zobrazí výkres. ``prepared`` lze připravit předem ve vlákně na pozadí (:func:`prepare_drawing`)."""
        self.clear_drawing()
        if prepared is None or prepared.drawing is not drawing:
            prepared = prepare_drawing(drawing)
        self.origin = prepared.origin
        self._prepared = prepared
        self._build(drawing)
        if getattr(self, "_bg_args", None):
            self.set_background_image(*self._bg_args)
        self.fit_all()

    def _build(self, drawing: Drawing):
        sc = self.scene()
        for it in list(self.layer_items.values()):
            sc.removeItem(it)
        self.layer_items.clear()
        self.drawing = drawing
        prep = getattr(self, "_prepared", None)
        if prep is None or prep.drawing is not drawing:
            prep = self._prepared = prepare_drawing(drawing)
        groups, fills, texts = prep.groups, prep.fills, prep.texts
        all_layers = set(groups) | set(fills) | {t.layer for t in texts} | set(drawing.layers)
        for name in sorted(all_layers):
            li = LayerItem(name)
            sc.addItem(li)
            self.layer_items[name] = li
        for layer, d in fills.items():
            for (rgb, solid), path in d.items():
                it = QGraphicsPathItem(path, self.layer_items[layer])
                col = display_color(rgb, self.light_bg)
                pen = QPen(col, 1)
                pen.setCosmetic(True)
                it.setPen(pen)
                fc = QColor(col)
                fc.setAlpha(150 if solid else 45)
                it.setBrush(QBrush(fc))
                it.setZValue(-1)
        for layer, d in groups.items():
            for key, path in d.items():
                rgb, lw, lt = key[:3]
                it = QGraphicsPathItem(path, self.layer_items[layer])
                pen = QPen(display_color(rgb, self.light_bg))
                pen.setCosmetic(True)
                ms = self.ms_look
                pen.setWidthF(weight_px(lw) if ms and len(key) == 3 else 1.0)
                pat = dash_pattern(lt or "") if ms else None
                if pat:
                    pen.setDashPattern(pat)
                if len(key) > 3 and not ms:
                    it.setVisible(False)  # značky uživatelských stylů jen v režimu „jako MicroStation“
                pen.setCapStyle(Qt.FlatCap)
                pen.setJoinStyle(Qt.RoundJoin)
                it.setPen(pen)
        for t in texts:
            self._add_text(t)
        rect = QRectF()
        for li in self.layer_items.values():
            rect = rect.united(li.childrenBoundingRect())
        self._content_rect = rect
        m = max(rect.width(), rect.height(), 10.0) * 2
        self.scene().setSceneRect(rect.adjusted(-m, -m, m, m))

    def _add_geometry(self, path: QPainterPath, geom):
        PathBuilder(self.origin).add_geometry(path, geom)


    def _add_text(self, f: Feature):
        if not f.text:
            return
        parent = self.layer_items.get(f.layer)
        item = QGraphicsSimpleTextItem(f.text.replace("\n", " ")[:200], parent)
        font = QFont("Arial")
        font.setPixelSize(100)
        item.setFont(font)
        item.setBrush(QBrush(display_color(f.color_rgb, self.light_bg)))
        fm = QFontMetricsF(font)
        cap = fm.capHeight() or fm.ascent() * 0.7
        s = (f.text_height or 1.0) / cap
        w = fm.horizontalAdvance(item.text())
        ax = {0: 0.0, 1: w / 2, 2: w}.get(f.halign, 0.0)
        ay = {0: fm.ascent(), 1: fm.ascent() + fm.descent(), 2: fm.ascent() - cap / 2,
              3: fm.ascent() - cap}.get(f.valign, fm.ascent())
        p = self.to_scene(*f.vertices[0])
        t = QTransform()
        t.translate(p.x(), p.y())
        t.rotate(-f.rotation)
        t.scale(s, s)
        t.translate(-ax, -ay)
        item.setTransform(t)

    # ---------------------------------------------------------------- hladiny
    def set_layer_visible(self, name: str, visible: bool):
        it = self.layer_items.get(name)
        if it is not None:
            it.setVisible(visible)

    # ---------------------------------------------------------------- podklad
    def set_background_image(self, pixmap: QPixmap | None, x: float = 0.0, y: float = 0.0,
                             meters_per_px: float = 0.1, rotation: float = 0.0, opacity: float = 0.5):
        """Obrázek pod výkresem: (x, y) = levý dolní roh v souřadnicích výkresu."""
        # parametry si pamatujeme – po načtení jiného výkresu se mění počátek scény
        self._bg_args = (pixmap, x, y, meters_per_px, rotation, opacity) if pixmap is not None else None
        if self.background is not None:
            self.scene().removeItem(self.background)
            self.background = None
        if pixmap is None or pixmap.isNull():
            return
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.SmoothTransformation)
        p = self.to_scene(x, y)
        t = QTransform()
        t.translate(p.x(), p.y())
        t.rotate(-rotation)
        t.scale(meters_per_px, meters_per_px)
        t.translate(0, -pixmap.height())
        item.setTransform(t)
        item.setOpacity(opacity)
        item.setZValue(-100_000)
        self.scene().addItem(item)
        self.background = item

    # ---------------------------------------------------------------- chyby
    def set_issues(self, issues: list[Issue]):
        sc = self.scene()
        for m in self.markers.values():
            sc.removeItem(m)
        self.markers.clear()
        for iss in issues:
            m = IssueMarker(iss)
            m.setPos(self.to_scene(iss.x, iss.y))
            sc.addItem(m)
            self.markers[iss.number] = m

    def set_visible_issues(self, numbers: set[int]):
        for n, m in self.markers.items():
            m.setVisible(n in numbers)

    def refresh_markers(self):
        for m in self.markers.values():
            m.prepareGeometryChange()
            m.update()

    def set_labels_visible(self, on: bool):
        IssueMarker.show_labels = on
        self.refresh_markers()
        self.viewport().update()

    def highlight_issue(self, number: int | None, zoom: bool = True):
        sc = self.scene()
        if self._highlight is not None:
            sc.removeItem(self._highlight)
            self._highlight = None
        for n, m in self.markers.items():
            m.set_highlighted(n == number)
        if number is None or number not in self.markers:
            return
        m = self.markers[number]
        iss = m.issue
        path = QPainterPath()
        if iss.geometry is not None and not iss.geometry.is_empty and iss.geometry.geom_type not in ("Point",
                                                                                                  "MultiPoint"):
            self._add_geometry(path, iss.geometry)
        elif self.drawing is not None and iss.feature_ids:
            by_id = getattr(self, "_by_id", None)
            if by_id is None or getattr(self, "_by_id_of", None) is not self.drawing:
                self._by_id, self._by_id_of = self.drawing.by_id(), self.drawing
                by_id = self._by_id
            for fid in iss.feature_ids[:200]:
                f = by_id.get(fid)
                if f is not None:
                    self._add_feature_outline(path, f)
        if not path.isEmpty():
            item = QGraphicsPathItem(path)
            pen = QPen(QColor(255, 230, 0, 230), 4)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setZValue(9_000)
            sc.addItem(item)
            self._highlight = item
        if zoom:
            self.zoom_to_issue(iss)

    def feature_at(self, x: float, y: float, tol: float) -> int:
        """Nejbližší viditelný prvek k bodu (v toleranci), jinak -1."""
        import numpy as np
        import shapely
        from shapely.geometry import Point
        if getattr(self, "_pick_of", None) is not self.drawing:
            feats = [f for f in self.drawing.features if f.geometry is not None and not f.geometry.is_empty]
            self._pick_feats = feats
            self._pick_tree = shapely.STRtree(np.array([f.geometry for f in feats], dtype=object)) if feats else None
            self._pick_of = self.drawing
        if self._pick_tree is None:
            return -1
        p = Point(x, y)
        best, best_d = -1, None
        for i in self._pick_tree.query(p, predicate="dwithin", distance=max(tol, 1e-6) * 3):
            f = self._pick_feats[int(i)]
            li = self.layer_items.get(f.layer)
            if li is not None and not li.isVisible():
                continue
            d = f.geometry.distance(p)
            if f.geom_type == GeomType.TEXT:
                d = max(0.0, d - max(f.text_height, 0.1) * 0.8)  # text je větší než jeho bod
            if d <= tol and (best_d is None or d < best_d):
                best, best_d = f.fid, d
        return best

    def highlight_feature(self, fid: int):
        sc = self.scene()
        if self._highlight is not None:
            sc.removeItem(self._highlight)
            self._highlight = None
        for m in self.markers.values():
            m.set_highlighted(False)
        f = self.drawing.by_id().get(fid) if (self.drawing is not None and fid >= 0) else None
        if f is None:
            return
        path = QPainterPath()
        self._add_feature_outline(path, f)
        item = QGraphicsPathItem(path)
        pen = QPen(QColor(0, 200, 255, 230), 4)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setZValue(9_000)
        sc.addItem(item)
        self._highlight = item

    def set_overlay(self, items: list[tuple[Feature, QColor, bool]]):
        """Překryvná vrstva (porovnání verzí): prvky obarvené podle druhu změny, čárkovaně = odebrané."""
        self.clear_overlay()
        sc = self.scene()
        groups: dict[tuple[str, bool], QPainterPath] = {}
        colors: dict[tuple[str, bool], QColor] = {}
        for f, color, dashed in items:
            key = (color.name(), dashed)
            path = groups.setdefault(key, QPainterPath())
            colors[key] = color
            self._add_feature_outline(path, f)
        self._overlay = []
        for key, path in groups.items():
            item = QGraphicsPathItem(path)
            pen = QPen(colors[key], 3.5)
            pen.setCosmetic(True)
            if key[1]:
                pen.setStyle(Qt.DashLine)
            item.setPen(pen)
            item.setZValue(8_500)
            sc.addItem(item)
            self._overlay.append(item)

    def clear_overlay(self):
        for it in getattr(self, "_overlay", []):
            if it.scene() is not None:
                it.scene().removeItem(it)
        self._overlay = []

    def zoom_to(self, x: float, y: float, span: float = 15.0):
        c = self.to_scene(x, y)
        self.fitInView(QRectF(c.x() - span / 2, c.y() - span / 2, span, span), Qt.KeepAspectRatio)

    def _add_feature_outline(self, path: QPainterPath, f: Feature):
        """Obrys prvku pro zvýraznění: čára/plocha přímo, text jako obdélník, bod jako kroužek."""
        from shapely.geometry import Polygon
        if f.geom_type == GeomType.TEXT and f.geometry.geom_type == "Point":
            h = max(f.text_height, 0.05)
            w = max(1, len(f.text or "")) * h * 0.75 * (f.width_factor or 1.0)
            x0 = {0: 0.0, 1: -w / 2, 2: -w}.get(f.halign, 0.0)
            y0 = {0: 0.0, 1: 0.0, 2: -h / 2, 3: -h}.get(f.valign, 0.0)
            a = math.radians(f.rotation or 0.0)
            ca, sa = math.cos(a), math.sin(a)
            px, py = f.geometry.x, f.geometry.y
            corners = [(x0 - h * 0.2, y0 - h * 0.2), (x0 + w + h * 0.2, y0 - h * 0.2),
                       (x0 + w + h * 0.2, y0 + h * 1.2), (x0 - h * 0.2, y0 + h * 1.2)]
            poly = Polygon([(px + cx * ca - cy * sa, py + cx * sa + cy * ca) for cx, cy in corners])
            self._add_geometry(path, poly)
        elif f.geom_type == GeomType.BOD:
            c = self.to_scene(f.geometry.x, f.geometry.y)
            r = max(0.3, f.radius * 1.3 if f.radius else 0.3)
            path.addEllipse(c, r, r)
        else:
            self._add_geometry(path, f.geometry)

    def zoom_to_issue(self, iss: Issue, span: float | None = None):
        c = self.to_scene(iss.x, iss.y)
        if span is None:
            span = 10.0
            if iss.geometry is not None and not iss.geometry.is_empty:
                b = iss.geometry.bounds
                span = max(span, (b[2] - b[0]) * 1.4, (b[3] - b[1]) * 1.4)
            span = min(span, 200.0)
        rect = QRectF(c.x() - span / 2, c.y() - span / 2, span, span)
        self.fitInView(rect, Qt.KeepAspectRatio)

    # ---------------------------------------------------------------- navigace
    def fit_all(self):
        rect = self._content_rect
        if rect.isNull() or rect.isEmpty():
            rect = self.scene().itemsBoundingRect()
        if rect.width() <= 0 and rect.height() <= 0:
            return
        self.fitInView(rect.adjusted(-rect.width() * 0.03, -rect.height() * 0.03,
                                     rect.width() * 0.03, rect.height() * 0.03), Qt.KeepAspectRatio)

    def current_scale(self) -> float:
        return self.transform().m11()

    def wheelEvent(self, event):  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            return
        factor = math.pow(1.0015, delta)
        s = self.current_scale() * factor
        if 1e-5 < s < 1e5:
            self.scale(factor, factor)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._press_pos = event.position()
            self._last_pos = event.position()
            self._panning = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        sp = self.mapToScene(event.position().toPoint())
        x, y = self.from_scene(sp)
        self.cursorMoved.emit(x, y)
        if self._last_pos is not None:
            d = event.position() - self._last_pos
            if not self._panning and (event.position() - self._press_pos).manhattanLength() > 4:
                self._panning = True
                self.viewport().setCursor(Qt.ClosedHandCursor)
            if self._panning:
                self._last_pos = event.position()
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
                # posun i mimo rozsah posuvníků
                if self.horizontalScrollBar().maximum() == 0 and self.verticalScrollBar().maximum() == 0:
                    self.translate(d.x() / self.current_scale(), d.y() / self.current_scale())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._press_pos is not None:
            was_pan = self._panning
            self._press_pos = None
            self._last_pos = None
            self._panning = False
            if getattr(self, "_pick_mode", False):
                self.viewport().setCursor(Qt.CrossCursor)
            else:
                self.viewport().unsetCursor()
            if not was_pan and event.button() == Qt.LeftButton and getattr(self, "_pick_mode", False):
                x, y = self.from_scene(self.mapToScene(event.position().toPoint()))
                self.pointPicked.emit(x, y)
                event.accept()
                return
            if not was_pan and event.button() == Qt.LeftButton:
                hit = False
                for item in self.items(event.position().toPoint()):
                    if isinstance(item, IssueMarker) and item.isVisible():
                        self.markerClicked.emit(item.issue.number)
                        hit = True
                        break
                if not hit and self.drawing is not None:
                    x, y = self.from_scene(self.mapToScene(event.position().toPoint()))
                    self.featureClicked.emit(self.feature_at(x, y, 7.0 / max(self.current_scale(), 1e-9)))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MiddleButton:
            self.fit_all()
            return
        super().mouseDoubleClickEvent(event)

    # ---------------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.fileDropped.emit(url.toLocalFile())
                break
        event.acceptProposedAction()

    # ---------------------------------------------------------------- snímky
    def render_overview(self, issues, size: int = 900) -> QPixmap:
        """Celý výkres s kroužky (bez popisků) – přehledka do protokolu."""
        return self.render_overview_positions(issues, size)[0]

    def render_overview_positions(self, issues, size: int = 900, markers: bool = True):
        """Přehledka výkresu a poloha každé chyby v obrázku v pixelech: (obrázek, {číslo: (x, y)})."""
        from PySide6.QtGui import QImage
        rect = self._content_rect if not self._content_rect.isEmpty() else self.scene().itemsBoundingRect()
        rect = rect.adjusted(-rect.width() * 0.03, -rect.height() * 0.03, rect.width() * 0.03, rect.height() * 0.03)
        ratio = rect.height() / rect.width() if rect.width() else 1.0
        w, h = size, max(100, int(size * ratio))
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        labels = IssueMarker.show_labels
        IssueMarker.show_labels = False
        hidden = [m for m in self.markers.values() if m.isVisible()]
        for m in hidden:
            m.setVisible(False)
        self.scene().render(painter, QRectF(0, 0, w, h), rect, Qt.KeepAspectRatio)
        # kroužky kreslíme sami, aby měly pevnou velikost v obrázku
        s = min(w / rect.width(), h / rect.height()) if rect.width() and rect.height() else 1.0
        ox = (w - rect.width() * s) / 2
        oy = (h - rect.height() * s) / 2
        pos = {}
        for iss in issues:
            p = self.to_scene(iss.x, iss.y)
            x = ox + (p.x() - rect.x()) * s
            y = oy + (p.y() - rect.y()) * s
            pos[iss.number] = (x, y)
            if markers:
                painter.setPen(QPen(SEVERITY_COLORS.get(iss.severity, QColor(128, 128, 128)), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(x, y), 8, 8)
        painter.end()
        for m in hidden:
            m.setVisible(True)
        IssueMarker.show_labels = labels
        return QPixmap.fromImage(img), pos

    def set_print_mode(self, on: bool):
        """Dočasně přestaví barvy výkresu pro tisk na bílé pozadí (a zpět)."""
        if self.drawing is None:
            return
        if on:
            self._saved_light = self.light_bg
            light = True
        else:
            light = getattr(self, "_saved_light", self.light_bg)
        if self._highlight is not None:
            self._highlight.setVisible(not on)
        if light == self.light_bg:
            return
        vis = {n: it.isVisible() for n, it in self.layer_items.items()}
        self.light_bg = light
        self._build(self.drawing)
        for n, v in vis.items():
            self.set_layer_visible(n, v)

    def render_region(self, x: float, y: float, span: float, size: int = 480) -> QPixmap:
        """Vykreslí okolí bodu (pro protokol PDF)."""
        from PySide6.QtGui import QImage
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        c = self.to_scene(x, y)
        src = QRectF(c.x() - span / 2, c.y() - span / 2, span, span)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        hidden = []
        for m in self.markers.values():
            if m.isVisible():
                m.setVisible(False)
                hidden.append(m)
        self.scene().render(painter, QRectF(0, 0, size, size), src, Qt.KeepAspectRatio)
        for m in hidden:
            m.setVisible(True)
        # kroužek do středu snímku
        painter.setPen(QPen(QColor(220, 30, 30), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(size / 2, size / 2), 22, 22)
        painter.end()
        return QPixmap.fromImage(img)
