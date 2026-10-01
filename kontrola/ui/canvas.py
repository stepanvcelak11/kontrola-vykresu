"""Plátno: výkres přes celé okno, nad ním plovoucí karty (panel chyb, vyhledávání, minimapa).

Rozvržení jako u mapových aplikací – výkres je hlavní, ovládání se nad ním „vznáší“. Panel chyb jde
sbalit; místo něj zůstane malé tlačítko s počtem chyb.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QPushButton, QVBoxLayout, QWidget)

MARGIN = 12


def _shadow(w: QWidget, blur: int = 28, alpha: int = 60) -> None:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, 4)
    eff.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(eff)


class Canvas(QWidget):
    """Výkres vyplňuje celé plátno; panel chyb je plovoucí karta vpravo."""

    panelToggled = Signal(bool)

    def __init__(self, view: QWidget, panel: QWidget, parent=None):
        super().__init__(parent)
        self.view = view
        view.setParent(self)
        self.card = QFrame(self)
        self.card.setObjectName("plovouci_panel")
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(panel)
        self.panel = panel
        _shadow(self.card)
        # sbalení panelu: kulaté tlačítko na levém okraji karty
        self.b_hide = QPushButton("›", self)
        self.b_hide.setObjectName("plovouci_tlacitko")
        self.b_hide.setToolTip("Schovat seznam chyb (výkres přes celé okno)")
        self.b_hide.setFixedSize(26, 44)
        self.b_hide.clicked.connect(lambda: self.set_panel_visible(False))
        # po sbalení: tlačítko s počtem chyb vpravo nahoře
        self.b_show = QPushButton("Chyby", self)
        self.b_show.setObjectName("plovouci_tlacitko")
        self.b_show.setToolTip("Ukázat seznam chyb")
        self.b_show.setMinimumHeight(36)
        self.b_show.clicked.connect(lambda: self.set_panel_visible(True))
        self.b_show.hide()
        _shadow(self.b_show, 18, 50)
        self.overlays: list[tuple[QWidget, str]] = []  # další plovoucí prvky a jejich umístění
        self.panel_visible = True
        self._anim: QPropertyAnimation | None = None

    # ---------------------------------------------------------------- rozvržení
    def panel_width(self) -> int:
        return max(380, min(560, int(self.width() * 0.38)))

    def _card_pos(self, visible: bool) -> QPoint:
        x = self.width() - self.panel_width() - MARGIN if visible else self.width() + 8
        return QPoint(x, MARGIN)

    def add_overlay(self, w: QWidget, where: str) -> None:
        """Plovoucí prvek nad výkresem: „nahore“ (uprostřed nahoře) nebo „vlevo_dole“."""
        w.setParent(self)
        self.overlays.append((w, where))
        w.show()
        self._layout()

    def _layout(self):
        W, H = self.width(), self.height()
        self.view.setGeometry(0, 0, W, H)
        pw = self.panel_width()
        self.card.resize(pw, max(200, H - 2 * MARGIN))
        if self._anim is None or self._anim.state() != QPropertyAnimation.Running:
            self.card.move(self._card_pos(self.panel_visible))
        self.card.setVisible(self.panel_visible or (self._anim is not None
                                                    and self._anim.state() == QPropertyAnimation.Running))
        self.b_hide.move(self.card.x() - self.b_hide.width() + 4, MARGIN + 60)
        self.b_hide.setVisible(self.panel_visible)
        self.b_show.adjustSize()
        self.b_show.move(W - self.b_show.width() - MARGIN, MARGIN)
        self.b_show.setVisible(not self.panel_visible)
        right = (W - pw - 2 * MARGIN) if self.panel_visible else W
        if hasattr(self.view, "inset_right"):
            self.view.inset_right = (pw + 2 * MARGIN) if self.panel_visible else 0
            self.view.inset_left = 64 if any(where == "vlevo_nahore" for _w, where in self.overlays) else 0
        for w, where in self.overlays:
            if not w.isVisible():
                continue
            if where != "vlevo_dole":
                w.adjustSize()
            if where == "nahore":
                ww = min(420, max(200, right - 2 * MARGIN - 140))
                w.resize(ww, max(w.sizeHint().height(), 38))
                w.move(max(MARGIN + 70, (right - ww) // 2), MARGIN)
            elif where == "vlevo_dole":
                w.move(MARGIN, H - w.height() - MARGIN)
            elif where == "vlevo_nahore":
                w.resize(w.sizeHint())
                w.move(MARGIN, MARGIN)
            w.raise_()
        self.card.raise_()
        self.b_hide.raise_()
        self.b_show.raise_()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._layout()

    # ---------------------------------------------------------------- sbalení
    def set_panel_visible(self, on: bool, animate: bool = True):
        if on == self.panel_visible:
            return
        self.panel_visible = on
        self.card.show()
        start, end = self._card_pos(not on), self._card_pos(on)
        if animate and self.isVisible():
            self._anim = QPropertyAnimation(self.card, b"pos", self)
            self._anim.setDuration(220)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.setStartValue(start)
            self._anim.setEndValue(end)
            self._anim.finished.connect(self._layout)
            self._anim.start()
        self._layout()
        self.panelToggled.emit(on)

    def set_issue_count(self, n: int):
        self.b_show.setText(f"  Chyby ({n})  ‹" if n else "  Chyby  ‹")
        self._layout()
