"""Společné díly pásů karet (CAD i Výpočty): posuvná oblast karty bez posuvníku a popisek skupiny."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QToolButton


class PasScroll(QScrollArea):
    """Karta pásu: když se nástroje nevejdou na šířku, místo posuvníku pod pásem se na krajích ukážou
    šipky ‹ › (a jde to i kolečkem myši) – pás má pořád stejnou výšku a nic nepřekrývá."""

    def __init__(self, obsah, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(obsah)
        self.setFixedHeight(obsah.sizeHint().height() + 2)
        self._sipky = []
        for znak, smer in (("‹", -1), ("›", 1)):
            b = QToolButton(self)
            b.setObjectName("pas_posun")
            b.setArrowType(Qt.LeftArrow if smer < 0 else Qt.RightArrow)
            b.setAutoRepeat(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip("Další nástroje pásu (také kolečkem myši)")
            b.clicked.connect(lambda _c=False, s=smer: self._posun(s))
            b.hide()
            self._sipky.append(b)
        sb = self.horizontalScrollBar()
        sb.rangeChanged.connect(lambda *_: self._obnov())
        sb.valueChanged.connect(lambda *_: self._obnov())

    def _posun(self, smer: int) -> None:
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() + smer * max(120, self.viewport().width() // 3))

    def _obnov(self) -> None:
        sb = self.horizontalScrollBar()
        vlevo, vpravo = self._sipky
        h = self.height()
        for b in self._sipky:
            b.setFixedSize(18, h)
        vlevo.move(0, 0)
        vpravo.move(self.width() - 18, 0)
        vlevo.setVisible(sb.value() > sb.minimum())
        vpravo.setVisible(sb.value() < sb.maximum())
        for b in self._sipky:
            b.raise_()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._obnov()

    def wheelEvent(self, e):  # noqa: N802
        sb = self.horizontalScrollBar()
        if sb.maximum() > sb.minimum():
            d = e.angleDelta().y() or e.angleDelta().x()
            sb.setValue(sb.value() - d)
            e.accept()
        else:
            super().wheelEvent(e)


def popisek_skupiny(text: str) -> QLabel:
    """Název skupiny nástrojů pod tlačítky (jednotný v celé aplikaci)."""
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setObjectName("pas_skupina")
    return lbl
