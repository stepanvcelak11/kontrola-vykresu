"""Minimapa: celý výkres v malém s tečkami chyb a rámečkem právě zobrazené části; klik/tažení posune pohled."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame

from .drawing_view import SEVERITY_COLORS, IssueMarker


class Minimap(QFrame):
    W = 220

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.setObjectName("minimapa")
        self.setToolTip("Minimapa – klikněte nebo táhněte pro posun výkresu")
        self.setCursor(Qt.PointingHandCursor)
        self._pm: QPixmap | None = None
        self._map = None  # (rect scény, měřítko, posun x, posun y)
        self._key = None
        self._last_state = None
        self.setFixedSize(self.W, 150)
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ---------------------------------------------------------------- obsah
    def _tick(self):
        v = self.view
        if v.drawing is None or getattr(self, "suppressed", False):
            if self.isVisible():
                self.hide()
            return
        key = (id(v.drawing), len(v.markers), tuple(sorted((n, m.issue.state) for n, m in v.markers.items()))[:400],
               v.light_bg)
        if key != self._key:
            self._key = key
            self.rebuild()
            if not self.isVisible():
                self.show()
                p = self.parentWidget()
                if p is not None and hasattr(p, "_layout"):
                    p._layout()
        st = v._view_state()
        if st != self._last_state:
            self._last_state = st
            self.update()

    def rebuild(self):
        v = self.view
        rect = v._content_rect if not v._content_rect.isEmpty() else v.scene().itemsBoundingRect()
        if rect.width() <= 0 or rect.height() <= 0:
            self._pm = None
            return
        rect = rect.adjusted(-rect.width() * 0.04, -rect.height() * 0.04, rect.width() * 0.04, rect.height() * 0.04)
        w = self.W - 8
        h = int(max(70, min(180, w * rect.height() / rect.width())))
        self.setFixedSize(self.W, h + 8)
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(v.backgroundBrush().color())
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        labels = IssueMarker.show_labels
        IssueMarker.show_labels = False
        shown = [m for m in v.markers.values() if m.isVisible()]
        for m in shown:
            m.setVisible(False)
        overlay = [it for it in getattr(v, "_overlay", []) if it.isVisible()]
        for it in overlay:
            it.setVisible(False)
        try:
            v.scene().render(p, QRectF(0, 0, w, h), rect, Qt.KeepAspectRatio)
        finally:
            for m in shown:
                m.setVisible(True)
            for it in overlay:
                it.setVisible(True)
            IssueMarker.show_labels = labels
        s = min(w / rect.width(), h / rect.height())
        ox, oy = (w - rect.width() * s) / 2, (h - rect.height() * s) / 2
        self._map = (rect, s, ox, oy)
        for m in shown:  # chyby jako barevné tečky (neopravené)
            if m.issue.state != "nová":
                continue
            pt = self._to_mini(m.scenePos())
            c = QColor(SEVERITY_COLORS.get(m.issue.severity, QColor(128, 128, 128)))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(pt, 2.6, 2.6)
        p.end()
        self._pm = QPixmap.fromImage(img)
        self.update()

    def _to_mini(self, sp: QPointF) -> QPointF:
        rect, s, ox, oy = self._map
        return QPointF(ox + (sp.x() - rect.x()) * s, oy + (sp.y() - rect.y()) * s)

    def _to_scene(self, mp: QPointF) -> QPointF:
        rect, s, ox, oy = self._map
        return QPointF(rect.x() + (mp.x() - 4 - ox) / s, rect.y() + (mp.y() - 4 - oy) / s)

    # ---------------------------------------------------------------- kreslení a myš
    def paintEvent(self, e):  # noqa: N802
        super().paintEvent(e)
        if self._pm is None or self._map is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(4, 4, self._pm)
        vp = self.view.viewport().rect()
        # viditelná část (bez plovoucích panelů) jako rámeček
        vis = vp.adjusted(self.view.inset_left, 0, -self.view.inset_right, 0)
        poly = self.view.mapToScene(vis)
        pts = [self._to_mini(poly.at(i)) + QPointF(4, 4) for i in range(poly.count())]
        from .theme import accent
        col = QColor(accent())
        p.setPen(QPen(col, 2))
        fill = QColor(col)
        fill.setAlpha(40)
        p.setBrush(fill)
        p.drawPolygon(QPolygonF(pts))
        p.end()

    def _go(self, pos):
        if self._map is None:
            return
        target = self._to_scene(QPointF(pos))
        v = self.view
        vp = v.viewport().rect()
        # posun tak, aby bod byl uprostřed viditelné části
        s = v.transform().m11() or 1.0
        dx = (vp.width() / 2 - (v.inset_left + (vp.width() - v.inset_left - v.inset_right) / 2)) / s
        v.centerOn(QPointF(target.x() + dx, target.y()))
        v.request_declutter()
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        self._go(e.position().toPoint())

    def mouseMoveEvent(self, e):  # noqa: N802
        if e.buttons() & Qt.LeftButton:
            self._go(e.position().toPoint())
