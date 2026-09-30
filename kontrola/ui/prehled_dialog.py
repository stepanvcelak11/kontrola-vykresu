"""Okno „Přehled výkresu“: vrstvy, počty prvků, barvy, styly, tloušťky a písmo – co ve výkresu vlastně je."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..checks.base import fmt_num
from ..prehled import popis_counter, prehled, souradnicovy_system

COLS = ["Vrstva", "Prvků", "Čáry", "Plochy", "Body", "Texty", "Buňky", "Délka [m]", "Plocha [m²]", "Barva",
        "Styl čáry", "Tloušťka", "Písmo / výška"]


class PrehledDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        d = win.drawing
        self.setWindowTitle("Přehled výkresu")
        self.resize(1320, 660)
        lay = QVBoxLayout(self)
        rows = prehled(d)
        b = d.bounds()
        ext = (f"{fmt_num(b[2] - b[0], 1)} × {fmt_num(b[3] - b[1], 1)} m" if b else "–")
        n_nejed = sum(1 for v in rows if not v.jednotna)
        head = QLabel(f"<h2 style='margin:0'>Přehled výkresu</h2>{len(d.features)} prvků ve {len(rows)} vrstvách · "
                      f"rozsah {ext} · {souradnicovy_system(d)}"
                      + (f" · <b>{n_nejed} vrstev nemá jednotný vzhled</b> (žlutě)" if n_nejed else ""))
        head.setWordWrap(True)
        lay.addWidget(head)
        t = self.table = QTableWidget(len(rows), len(COLS))
        t.setHorizontalHeaderLabels(COLS)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setAlternatingRowColors(True)
        warn = QColor(255, 243, 205)
        for r, v in enumerate(rows):
            pis = popis_counter(v.pisma, 2)
            if v.vysky:
                pis += (" · " if pis else "") + popis_counter(_vysky(v.vysky), 2)
            vals = [v.nazev, v.celkem, v.linie, v.plochy, v.body, v.texty, v.bunky,
                    fmt_num(v.delka, 1) if v.delka else "", fmt_num(v.plocha, 1) if v.plocha else "",
                    popis_counter(v.barvy), popis_counter(v.styly), popis_counter(v.tloustky), pis]
            for c, val in enumerate(vals):
                it = QTableWidgetItem()
                if isinstance(val, int):
                    if val or c == 1:
                        it.setData(Qt.DisplayRole, val)
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    it.setText(str(val))
                    it.setToolTip(str(val))
                if not v.jednotna and c in (9, 10, 11):
                    it.setBackground(warn)
                if c == 9 and v.rgb:
                    it.setIcon(_swatch(v.rgb.most_common(1)[0][0]))
                t.setItem(r, c, it)
        t.setSortingEnabled(True)
        t.sortByColumn(1, Qt.DescendingOrder)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)
        t.resizeColumnsToContents()
        for c in range(COLS.index("Plocha [m²]") + 1):
            hh.setSectionResizeMode(c, QHeaderView.Interactive)
        t.setColumnWidth(0, min(max(t.columnWidth(0), 160), 300))
        for c in range(1, 7):
            t.setColumnWidth(c, 68)
        t.setColumnWidth(7, 92)
        t.setColumnWidth(8, 104)
        t.doubleClicked.connect(lambda _i: self.only_layer())
        lay.addWidget(t, 1)
        note = QLabel("Dvojklik na vrstvu ji ukáže samotnou. Žlutě = na vrstvě jsou prvky s různou barvou, stylem "
                      "nebo tloušťkou (to hlídá kontrola „Prvek jiný než ostatní na vrstvě“).")
        note.setObjectName("karta_popis")
        note.setWordWrap(True)
        lay.addWidget(note)
        row = QHBoxLayout()
        b_only = QPushButton("Ukázat jen tuto vrstvu")
        b_only.clicked.connect(self.only_layer)
        b_all = QPushButton("Ukázat všechny vrstvy")
        b_all.clicked.connect(lambda: self._show_layers(None))
        b_copy = QPushButton("Kopírovat tabulku")
        b_copy.setToolTip("Zkopíruje přehled do schránky (vložíte do Excelu)")
        b_copy.clicked.connect(self.copy)
        b_close = QPushButton("Zavřít")
        b_close.clicked.connect(self.accept)
        for w in (b_only, b_all, b_copy, b_close):
            w.setAutoDefault(False)
        for w in (b_only, b_all, b_copy):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(b_close)
        lay.addLayout(row)

    def selected_layer(self) -> str | None:
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return it.text() if it else None

    def _show_layers(self, only: str | None):
        lst = self.win.layers.list
        for i in range(lst.count()):
            it = lst.item(i)
            on = only is None or it.data(Qt.UserRole) == only
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)

    def only_layer(self):
        name = self.selected_layer()
        if name:
            self._show_layers(name)

    def copy(self):
        t = self.table
        lines = ["\t".join(COLS)]
        for r in range(t.rowCount()):
            lines.append("\t".join((t.item(r, c).text() if t.item(r, c) else "") for c in range(t.columnCount())))
        QApplication.clipboard().setText("\n".join(lines))


def _vysky(c: Counter) -> Counter:
    """Výšky textu jako „2,5 m“ (čitelné klíče)."""
    return Counter({f"{fmt_num(k, 2)} m": v for k, v in c.items()})


def _swatch(rgb, size: int = 12) -> QIcon:
    """Vzorek barvy s tenkým obrysem (aby byla vidět i bílá)."""
    pm = QPixmap(size, size)
    pm.fill(QColor(*rgb))
    p = QPainter(pm)
    p.setPen(QColor(120, 120, 120))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(pm)
