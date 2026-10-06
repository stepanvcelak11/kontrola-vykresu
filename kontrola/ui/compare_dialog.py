"""Okno „Porovnání verzí výkresu“: seznam změn, barevně ve výkresu."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..porovnani import DRUHY, ODEBRANO, PRIDANO, UPRAVENO, ZMENENO, Zmena, summary

COLORS = {PRIDANO: QColor("#16A34A"), ODEBRANO: QColor("#DC2626"), UPRAVENO: QColor("#F59E0B"),
          ZMENENO: QColor("#7C3AED")}


class CompareDialog(QDialog):
    otherRequested = Signal()

    def __init__(self, view, changes: list[Zmena], old_name: str, new_name: str, parent=None, druhy=DRUHY,
                 barvy=None, titulek: str = "Porovnání verzí výkresu", hlavicka: str | None = None,
                 carkovane=(ODEBRANO,), dalsi_html: str = ""):
        super().__init__(parent)
        self.view = view
        self.changes = changes
        self.druhy = tuple(druhy)
        self.barvy = barvy or COLORS
        self.carkovane = tuple(carkovane)
        self.setWindowTitle(titulek)
        self.setWindowFlag(Qt.Tool, True)  # nechá výkres ovladatelný
        self.setModal(False)
        self.resize(700, 520)
        lay = QVBoxLayout(self)
        head = QLabel(hlavicka if hlavicka is not None else
                      f"<b>Předchozí:</b> {old_name}<br><b>Nyní:</b> {new_name}<br><br>{summary(changes)}")
        head.setWordWrap(True)
        lay.addWidget(head)
        legend = QLabel("  ".join(f"<span style='color:{self.barvy[d].name()}'>■</span> {d}" for d in self.druhy)
                        + "  (" + ", ".join(self.carkovane) + " – čárkovaně)")
        legend.setWordWrap(True)
        lay.addWidget(legend)
        row = QHBoxLayout()
        row.addWidget(QLabel("Zobrazit:"))
        self.kind = QComboBox()
        self.kind.addItem("Všechny změny", None)
        for d in self.druhy:
            n = sum(1 for z in changes if z.druh == d)
            if n:
                self.kind.addItem(f"{d} ({n})", d)
        self.kind.currentIndexChanged.connect(self._fill)
        row.addWidget(self.kind, 1)
        b_other = QPushButton("Porovnat s jiným souborem…")
        b_other.clicked.connect(self.otherRequested.emit)
        row.addWidget(b_other)
        lay.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Změna", "Vrstva", "Popis"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 140)
        self.table.currentCellChanged.connect(lambda r, *_: self._go(r))
        lay.addWidget(self.table, 1)
        if dalsi_html:
            from PySide6.QtWidgets import QTextBrowser
            tb = QTextBrowser()
            tb.setHtml(dalsi_html)
            tb.setMaximumHeight(170)
            lay.addWidget(tb)
        b_close = QPushButton("Zavřít")
        b_close.clicked.connect(self.close)
        lay.addWidget(b_close, 0, Qt.AlignRight)
        self._fill()

    def shown_changes(self) -> list[Zmena]:
        d = self.kind.currentData()
        return [z for z in self.changes if d is None or z.druh == d]

    def _fill(self, *_):
        rows = self.shown_changes()
        self.table.setRowCount(len(rows))
        for r, z in enumerate(rows):
            for c, text in enumerate((z.druh, z.vrstva, z.popis)):
                it = QTableWidgetItem(text)
                if c == 0:
                    it.setForeground(QBrush(self.barvy[z.druh]))
                self.table.setItem(r, c, it)
        items = []
        for z in rows:
            if z.old is not None and z.druh in self.carkovane + (UPRAVENO,):
                items.append((z.old, self.barvy[z.druh] if z.druh in self.carkovane else QColor(220, 38, 38, 120),
                               True))
            if z.new is not None:
                items.append((z.new, self.barvy[z.druh], False))
        self.view.set_overlay(items)

    def _go(self, row: int):
        rows = self.shown_changes()
        if 0 <= row < len(rows):
            z = rows[row]
            span = 15.0
            f = z.new or z.old
            if f is not None and f.geometry is not None and not f.geometry.is_empty:
                b = f.geometry.bounds
                span = min(200.0, max(span, (b[2] - b[0]) * 1.5, (b[3] - b[1]) * 1.5))
            self.view.zoom_to(z.x, z.y, span)

    def closeEvent(self, e):  # noqa: N802
        self.view.clear_overlay()
        super().closeEvent(e)
