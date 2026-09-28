"""Umístění podkladu (náčrt, sken, PDF vzoru) pod výkres podle dvou identických bodů."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout)

from ..georef import similarity_from_two_points
from .image_viewer import ImageView


class _PickImageView(ImageView):
    picked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press = None
        self.marks = []

    def mousePressEvent(self, e):  # noqa: N802
        self._press = e.position()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        super().mouseReleaseEvent(e)
        if self._press is not None and (e.position() - self._press).manhattanLength() < 4 \
                and e.button() == Qt.LeftButton and self.item is not None:
            p = self.item.mapFromScene(self.mapToScene(e.position().toPoint()))
            self.picked.emit(p.x(), p.y())
        self._press = None

    def add_mark(self, x: float, y: float, text: str):
        sc = self.scene()
        r = max(4.0, (self.item.pixmap().width() if self.item else 1000) / 150)
        pen = QPen(QColor(230, 0, 0), 0)
        pen.setCosmetic(True)
        pen.setWidth(3)
        c = sc.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, QBrush(Qt.NoBrush))
        c.setParentItem(self.item)
        t = sc.addSimpleText(text)
        t.setBrush(QBrush(QColor(230, 0, 0)))
        t.setFlag(t.GraphicsItemFlag.ItemIgnoresTransformations, True)
        t.setParentItem(self.item)
        t.setPos(QPointF(x + r, y - r))
        self.marks += [c, t]


class GeorefDialog(QDialog):
    """Nemodální okno: 1) bod v obrázku, 2) stejný bod ve výkresu, 3) druhý bod v obrázku, 4) ve výkresu."""

    finished_params = Signal(dict)

    def __init__(self, pixmap: QPixmap, drawing_view, opacity: float = 0.5, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Umístit podklad podle 2 bodů")
        self.setModal(False)
        self.resize(720, 620)
        self.pixmap = pixmap
        self.view = drawing_view
        self.img_pts: list[tuple[float, float]] = []
        self.world_pts: list[tuple[float, float]] = []
        lay = QVBoxLayout(self)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet("font-weight: bold; padding: 4px;")
        lay.addWidget(self.help)
        self.img = _PickImageView()
        self.img.set_pixmap(pixmap)
        self.img.picked.connect(self._image_picked)
        lay.addWidget(self.img, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Průhlednost:"))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(int(opacity * 100))
        row.addWidget(self.opacity, 1)
        b_reset = QPushButton("Začít znovu")
        b_reset.clicked.connect(self.reset)
        b_close = QPushButton("Zavřít")
        b_close.clicked.connect(self.close)
        row.addWidget(b_reset)
        row.addWidget(b_close)
        lay.addLayout(row)
        self.view.pointPicked.connect(self._world_picked)
        self.reset()

    def reset(self):
        self.img_pts.clear()
        self.world_pts.clear()
        for m in self.img.marks:
            self.img.scene().removeItem(m)
        self.img.marks.clear()
        self.view.set_pick_mode(False)
        self._update_help()

    def _update_help(self):
        step = len(self.img_pts) + len(self.world_pts)
        texts = [
            "1/4: Klikněte v obrázku na 1. výrazný bod (roh budovy, lomový bod hranice…). "
            "Kolečkem přibližujete, tažením posouváte.",
            "2/4: Klikněte ve VÝKRESU (hlavní okno) na stejný bod.",
            "3/4: Klikněte v obrázku na 2. bod – co nejdál od prvního.",
            "4/4: Klikněte ve VÝKRESU na stejný bod.",
        ]
        self.help.setText(texts[step] if step < 4 else "Hotovo – podklad je umístěn.")
        self.view.set_pick_mode(step in (1, 3))

    def _image_picked(self, x: float, y: float):
        if len(self.img_pts) != len(self.world_pts) or len(self.img_pts) >= 2:
            return
        self.img_pts.append((x, y))
        self.img.add_mark(x, y, str(len(self.img_pts)))
        self._update_help()

    def _world_picked(self, x: float, y: float):
        if len(self.world_pts) >= len(self.img_pts) or not self.isVisible():
            return
        self.world_pts.append((x, y))
        self._update_help()
        if len(self.world_pts) == 2:
            try:
                params = similarity_from_two_points(self.img_pts[0], self.img_pts[1], self.world_pts[0],
                                                    self.world_pts[1], self.pixmap.height())
            except ValueError as exc:
                self.help.setText(str(exc) + " Klikněte na „Začít znovu“.")
                return
            params["pruhlednost"] = self.opacity.value() / 100
            self.finished_params.emit(params)

    def closeEvent(self, e):  # noqa: N802
        self.view.set_pick_mode(False)
        try:
            self.view.pointPicked.disconnect(self._world_picked)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(e)
