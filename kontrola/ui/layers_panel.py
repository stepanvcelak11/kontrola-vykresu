"""Seznam vrstev se zaškrtávátky (zapnutí/vypnutí vrstev ve výkresu)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from ..model import Drawing


def color_icon(rgb: tuple[int, int, int], size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(QColor(*rgb))
    return QIcon(pm)


class LayersPanel(QWidget):
    layerToggled = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat vrstvu…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._changed)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        b_all = QPushButton("Zapnout vše")
        b_none = QPushButton("Vypnout vše")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none.clicked.connect(lambda: self._set_all(False))
        row.addWidget(b_all)
        row.addWidget(b_none)
        lay.addLayout(row)
        self._updating = False

    def set_drawing(self, drawing: Drawing | None):
        self._updating = True
        self.list.clear()
        if drawing is not None:
            for name in sorted(drawing.layers, key=str.lower):
                info = drawing.layers[name]
                if info.count == 0:
                    continue
                it = QListWidgetItem(color_icon(info.color_rgb), f"{name}  ({info.count})")
                it.setData(Qt.UserRole, name)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked if (info.off or info.frozen) else Qt.Checked)
                it.setToolTip(f"Barva {info.color_aci}, styl {info.linetype}, "
                              f"tloušťka {info.lineweight} mm")
                self.list.addItem(it)
        self._updating = False
        for i in range(self.list.count()):
            it = self.list.item(i)
            self.layerToggled.emit(it.data(Qt.UserRole), it.checkState() == Qt.Checked)

    def _changed(self, it: QListWidgetItem):
        if not self._updating:
            self.layerToggled.emit(it.data(Qt.UserRole), it.checkState() == Qt.Checked)

    def _set_all(self, on: bool):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _filter(self, text: str):
        t = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())
