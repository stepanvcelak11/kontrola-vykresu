"""Okno „Spojnice podle náčrtu“: co je v náčrtu spojené, musí být nakreslené (jen kontrola, nic nevkládá)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..checks.seznam import read_point_list
from ..checks.spojnice import STAVY_SPOJNIC, verify_lines
from ..model import GeomType

COL = {"ok": "#16A34A", "chybi": "#DC2626", "vrstva": "#D97706", "jinak": "#2563EB", "bod": "#6B7280"}
PRIKLAD = "# jeden řádek = jedna čára podle náčrtu (popis je nepovinný)\nplot: 1-2-3-4\nbudova 10-11-12-13-10\n"


class SpojniceDialog(QDialog):
    def __init__(self, win, path: str = ""):
        super().__init__(win)
        self.win = win
        self.results = []
        self.setWindowTitle("Spojnice podle náčrtu")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(900, 620)
        lay = QVBoxLayout(self)
        intro = QLabel("Zapište, které body jsou v náčrtu spojené, a aplikace ověří, že to ve výkresu máte "
                       "nakreslené (a na správné vrstvě, pokud napíšete, co to je). Do výkresu nic nevkládá – "
                       "kreslíte sami v MicroStationu.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        self.path = QLineEdit(path)
        self.path.setPlaceholderText("Seznam souřadnic (číslo Y X Z) – kvůli poloze bodů")
        b = QPushButton("Vybrat…")
        b.clicked.connect(self._pick)
        row.addWidget(QLabel("Seznam:"))
        row.addWidget(self.path, 1)
        row.addWidget(b)
        lay.addLayout(row)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Spojnice z náčrtu:"))
        self.text = QPlainTextEdit()
        p = getattr(win, "project", None)
        self.text.setPlainText((p.meta.get("spojnice") if p is not None else None) or PRIKLAD)
        ll.addWidget(self.text, 1)
        self.b_run = QPushButton("Ověřit")
        self.b_run.setProperty("primarni", True)
        self.b_run.clicked.connect(self.run)
        ll.addWidget(self.b_run)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel("Zatím neověřeno.")
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Čára", "Úsek", "Stav", "Poznámka"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 120)
        self.table.cellDoubleClicked.connect(self._go)
        rl.addWidget(self.table, 1)
        hint = QLabel("Dvojklik přiblíží úsek ve výkresu. Červeně čárkovaně = chybí.")
        hint.setObjectName("karta_popis")
        rl.addWidget(hint)
        split.addWidget(right)
        split.setSizes([300, 600])
        lay.addWidget(split, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.close)
        brow.addWidget(close)
        lay.addLayout(brow)

    def _pick(self):
        f, _ = QFileDialog.getOpenFileName(self, "Seznam souřadnic", "",
                                           "Seznam souřadnic (*.txt *.csv *.xyz *.crd *.sez *.pts);;Vše (*)")
        if f:
            self.path.setText(f)

    def run(self):
        d = getattr(self.win, "drawing", None)
        if d is None:
            QMessageBox.information(self, "Spojnice", "Nejdřív otevřete výkres.")
            return
        path = self.path.text().strip()
        if not path or not Path(path).is_file():
            QMessageBox.information(self, "Spojnice", "Vyberte seznam souřadnic – z něj se vezme poloha bodů.")
            return
        try:
            pts = read_point_list(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Spojnice", str(exc))
            return
        text = self.text.toPlainText()
        p = getattr(self.win, "project", None)
        if p is not None:
            p.meta["spojnice"] = text
            p.save()
        rules = p.rules if p is not None else None
        self.results = verify_lines(d, pts, text, rules, getattr(p.config, "tolerance", 0.01) if p else 0.01)
        c = Counter(r.stav for r in self.results)
        if not self.results:
            self.summary.setText("Nenašel jsem žádnou spojnici – zapište např. <i>plot: 1-2-3</i>.")
        else:
            bad = len(self.results) - c.get("ok", 0)
            self.summary.setText(
                (f"<span style='color:#15803D'><b>✓ Všech {len(self.results)} úseků je nakresleno</b></span>"
                 if not bad else f"<b>{bad} z {len(self.results)} úseků nesedí</b>: ")
                + ", ".join(f"<span style='color:{COL[k]}'>{STAVY_SPOJNIC[k]} {n}</span>"
                            for k, n in c.items() if k != "ok"))
        self.table.setRowCount(len(self.results))
        for i, r in enumerate(self.results):
            vals = [r.linie.popis or f"řádek {r.linie.radek}", f"{r.od} – {r.do}", STAVY_SPOJNIC[r.stav],
                    r.poznamka]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if col == 2:
                    it.setForeground(QBrush(QColor(COL[r.stav])))
                self.table.setItem(i, col, it)
        items = [(SimpleNamespace(geom_type=GeomType.LINIE, geometry=r.geometry), QColor(COL[r.stav]),
                  r.stav == "chybi") for r in self.results if r.stav != "ok" and r.geometry is not None]
        self.win.view.set_overlay(items)

    def _go(self, row, _col):
        if 0 <= row < len(self.results) and self.results[row].geometry is not None:
            c = self.results[row].geometry.centroid
            self.win.tabs.setCurrentWidget(self.win.split)
            self.win.view.zoom_to(c.x, c.y, max(8.0, self.results[row].geometry.length * 1.5))

    def closeEvent(self, e):  # noqa: N802
        self.win.view.clear_overlay()
        super().closeEvent(e)
