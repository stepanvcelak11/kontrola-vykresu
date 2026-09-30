"""Okno „Časová osa výkresu“: uložené verze, přehrání vzniku výkresu, porovnání a vytažení smazaných prvků."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QSlider, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..casova_osa import export_removed, extract, removed_since, snapshots
from ..model import GeomType


def render_drawing(drawing, bounds, size=(640, 480)) -> QImage:
    """Rychlý náhled výkresu (čáry a body barvou prvku na bílém papíře) v pevném rozsahu ``bounds``."""
    w, h = size
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    x0, y0, x1, y1 = bounds
    sx = w / max(x1 - x0, 1e-9)
    sy = h / max(y1 - y0, 1e-9)
    s = min(sx, sy) * 0.96
    ox = (w - (x1 - x0) * s) / 2
    oy = (h - (y1 - y0) * s) / 2

    def pt(x, y):
        return QPointF(ox + (x - x0) * s, h - (oy + (y - y0) * s))

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    paths: dict[tuple, QPainterPath] = {}
    for f in drawing.features:
        g = f.geometry
        if g is None or g.is_empty:
            continue
        r, gg, b = f.color_rgb or (0, 0, 0)
        if r + gg + b > 600:  # bílá / světlá barva na bílém papíře → tmavě šedá
            r, gg, b = 60, 60, 60
        key = (r, gg, b)
        path = paths.setdefault(key, QPainterPath())
        if f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
            lines = [g.exterior] if g.geom_type == "Polygon" else list(getattr(g, "geoms", [g]))
            for ln in lines:
                cs = list(ln.coords)
                if len(cs) < 2:
                    continue
                path.moveTo(pt(*cs[0][:2]))
                for c in cs[1:]:
                    path.lineTo(pt(*c[:2]))
        elif f.geom_type == GeomType.BOD and g.geom_type == "Point":
            path.addEllipse(pt(g.x, g.y), 1.2, 1.2)
    for (r, gg, b), path in paths.items():
        p.setPen(QPen(QColor(r, gg, b), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.end()
    return img


def _fmt_time(iso: str) -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime("%d.%m. %H:%M")
    except ValueError:
        return iso


class TimelineDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.project = win.project
        self.recs = snapshots(self.project)
        self._cache: dict[int, object] = {}
        self._images: dict[int, QImage] = {}
        self.setWindowTitle("Časová osa výkresu")
        self.resize(1100, 640)
        lay = QVBoxLayout(self)
        intro = QLabel("Při každé kontrole změněného výkresu se uloží jeho verze. Můžete si přehrát, jak výkres "
                       "vznikal, zjistit, kdy přibyla chyba, porovnat starou verzi s dneškem a vytáhnout omylem "
                       "smazané prvky do DXF.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Kdy", "Prvků", "Změna", "Chyby", "Varování", "Skóre"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(lambda r, *_: self._show(r))
        split.addWidget(self.table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(560, 420)
        self.preview.setStyleSheet("background: white; border: 1px solid #D1D5DB;")
        rl.addWidget(self.preview, 1)
        self.caption = QLabel()
        rl.addWidget(self.caption)
        prow = QHBoxLayout()
        self.b_play = QPushButton("▶ Přehrát")
        self.b_play.clicked.connect(self._toggle_play)
        prow.addWidget(self.b_play)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max(0, len(self.recs) - 1))
        self.slider.valueChanged.connect(lambda v: self.table.selectRow(v))
        prow.addWidget(self.slider, 1)
        rl.addLayout(prow)
        split.addWidget(right)
        split.setSizes([420, 660])
        lay.addWidget(split, 1)
        brow = QHBoxLayout()
        self.b_cmp = QPushButton("Porovnat s aktuálním výkresem")
        self.b_cmp.clicked.connect(self.compare_current)
        self.b_rest = QPushButton("Vytáhnout smazané prvky do DXF…")
        self.b_rest.setToolTip("Prvky, které v této verzi byly a v aktuálním výkresu chybí – do samostatného DXF, "
                               "odkud je v MicroStationu zkopírujete zpět (Reference → kopírovat).")
        self.b_rest.clicked.connect(self.restore_removed)
        self.b_save = QPushButton("Uložit tuto verzi jako DXF…")
        self.b_save.clicked.connect(self.save_version)
        for b in (self.b_cmp, self.b_rest, self.b_save):
            brow.addWidget(b)
        brow.addStretch(1)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.accept)
        brow.addWidget(close)
        lay.addLayout(brow)
        self.timer = QTimer(self)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self._tick)
        self._fill()

    # ------------------------------------------------------------ data
    def _fill(self):
        self.table.setRowCount(len(self.recs))
        prev = None
        for r, rec in enumerate(self.recs):
            n = rec.get("prvku")
            ch = "" if prev is None or n is None or prev.get("prvku") is None else f"{n - prev['prvku']:+d}"
            vals = [_fmt_time(rec.get("cas", "")), "" if n is None else str(n), ch, str(rec.get("chyby", "")),
                    str(rec.get("varovani", "")), str(rec.get("skore", ""))]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 3 and prev is not None and isinstance(rec.get("chyby"), int) and \
                        isinstance(prev.get("chyby"), int) and rec["chyby"] > prev["chyby"]:
                    it.setForeground(QBrush(QColor("#DC2626")))
                    it.setToolTip("Tady chyby přibyly")
                self.table.setItem(r, c, it)
            prev = rec
        has = bool(self.recs)
        for b in (self.b_cmp, self.b_rest, self.b_save, self.b_play):
            b.setEnabled(has)
        if has:
            self.table.selectRow(len(self.recs) - 1)
        else:
            self.preview.setText("Zatím žádná verze – uloží se při příští kontrole výkresu (F5).")

    def _drawing(self, r: int):
        if r not in self._cache:
            from ..io.dxf_loader import load_drawing
            self._cache[r] = load_drawing(extract(self.project, self.recs[r]))
        return self._cache[r]

    def _bounds(self):
        if not hasattr(self, "_bb"):
            d = self.win.drawing if self.win.drawing is not None else self._drawing(len(self.recs) - 1)
            xs, ys = [], []
            for f in d.features:
                if f.geometry is not None and not f.geometry.is_empty:
                    b = f.geometry.bounds
                    xs += [b[0], b[2]]
                    ys += [b[1], b[3]]
            self._bb = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)
        return self._bb

    def _show(self, r: int):
        if not (0 <= r < len(self.recs)):
            return
        self.slider.blockSignals(True)
        self.slider.setValue(r)
        self.slider.blockSignals(False)
        rec = self.recs[r]
        if r not in self._images:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self._images[r] = render_drawing(self._drawing(r), self._bounds(), (720, 540))
            except Exception as exc:  # noqa: BLE001 – poškozený snímek
                self.preview.setText(f"Verzi nejde načíst: {exc}")
                return
            finally:
                QApplication.restoreOverrideCursor()
        self.preview.setPixmap(QPixmap.fromImage(self._images[r]).scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.caption.setText(f"<b>{_fmt_time(rec.get('cas', ''))}</b> · {rec.get('nazev', '')} · "
                             f"verze {r + 1} z {len(self.recs)}")

    def _toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.b_play.setText("▶ Přehrát")
            return
        if self.slider.value() >= len(self.recs) - 1:
            self.table.selectRow(0)
        self.timer.start()
        self.b_play.setText("■ Zastavit")

    def _tick(self):
        r = self.table.currentRow() + 1
        if r >= len(self.recs):
            self._toggle_play()
            return
        self.table.selectRow(r)

    def _current_rec(self) -> int:
        r = self.table.currentRow()
        return r if 0 <= r < len(self.recs) else -1

    # ------------------------------------------------------------ akce
    def compare_current(self):
        r = self._current_rec()
        if r < 0 or self.win.drawing is None:
            return
        self.accept()
        self.win._show_compare(self._drawing(r))

    def restore_removed(self):
        r = self._current_rec()
        if r < 0 or self.win.drawing is None:
            return
        old = self._drawing(r)
        gone = removed_since(old, self.win.drawing)
        if not gone:
            QMessageBox.information(self, "Časová osa", "Oproti této verzi v aktuálním výkresu nic nechybí.")
            return
        f, _ = QFileDialog.getSaveFileName(self, "Smazané prvky", str(Path(old.path).with_name("smazane_prvky.dxf")),
                                           "DXF (*.dxf)")
        if not f:
            return
        n = export_removed(old.path, [x.handle for x in gone], f)
        QMessageBox.information(self, "Časová osa", f"Uloženo {n} prvků, které v aktuálním výkresu chybí:\n{f}\n\n"
                                "V MicroStationu soubor připojte jako referenci a potřebné prvky zkopírujte zpět.")

    def save_version(self):
        r = self._current_rec()
        if r < 0:
            return
        rec = self.recs[r]
        f, _ = QFileDialog.getSaveFileName(self, "Uložit verzi", rec.get("nazev", "verze.dxf").replace(
            ".dxf", f"_{rec.get('cas', '')[:16].replace(':', '').replace('T', '_')}.dxf"), "DXF (*.dxf)")
        if f:
            extract(self.project, rec, f)
