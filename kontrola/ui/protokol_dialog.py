"""Okno s porovnáním výsledků aplikace a protokolu od učitele."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .theme import fit_headers


class ProtokolDialog(QDialog):
    def __init__(self, rows, summary: str, topo: dict[str, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Porovnání s protokolem učitele")
        self.resize(860, 600)
        lay = QVBoxLayout(self)
        info = QLabel(f"<b>{summary}</b><br>Řádky, kde se počty liší, ukazují, co program hlásí jinak než "
                      "učitelova kontrola. Pošlete protokol autorovi aplikace – podle něj se pravidla doladí.")
        info.setWordWrap(True)
        lay.addWidget(info)
        t = QTableWidget(len(rows), 5)
        t.setHorizontalHeaderLabels(["Vrstva", "Chybné atributy", "Učitel", "Program", "Výsledek"])
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setStretchLastSection(True)
        for i, r in enumerate(rows):
            if r.ucitel == r.program:
                res, col = "shoda", QColor(21, 128, 61)
            elif r.program < r.ucitel:
                res, col = f"program nenašel {r.ucitel - r.program}", QColor(185, 28, 28)
            else:
                res, col = f"program hlásí navíc {r.program - r.ucitel}", QColor(180, 83, 9)
            for c, v in enumerate([r.vrstva, r.popis, str(r.ucitel), str(r.program), res]):
                it = QTableWidgetItem(v)
                if c in (2, 3):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if c == 4:
                    it.setForeground(QBrush(col))
                t.setItem(i, c, it)
        for c, w in enumerate((140, 260, 70, 80)):
            t.setColumnWidth(c, w)
        fit_headers(t)
        lay.addWidget(t, 1)
        if topo:
            lay.addWidget(QLabel("<b>Topologie z protokolu</b> (MGEO): " +
                                 ", ".join(f"{k}: {v}" for k, v in topo.items())))
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton("Zavřít")
        b.setDefault(True)
        b.clicked.connect(self.accept)
        row.addWidget(b)
        lay.addLayout(row)
