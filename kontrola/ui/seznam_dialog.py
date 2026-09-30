"""Okno „Ověřit seznam souřadnic“: sedí body ve výkresu na seznam (poloha, číslo, výška)?"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ..checks.seznam import STAVY, read_point_list, verify_points

COL = {"ok": "#16A34A", "chybi": "#DC2626", "posunuty": "#DC2626", "cislo": "#D97706", "vyska": "#D97706",
       "navic": "#2563EB"}


class SeznamDialog(QDialog):
    def __init__(self, win, path: str = ""):
        super().__init__(win)
        self.win = win
        self.results = []
        self.setWindowTitle("Ověřit seznam souřadnic")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(820, 620)
        lay = QVBoxLayout(self)
        intro = QLabel("Porovná body ve výkresu se seznamem souřadnic (např. z Gromy): jestli každý bod ve výkresu "
                       "je, leží na správném místě a má správné číslo a výšku.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        self.path = QLineEdit(path)
        self.path.setPlaceholderText("Seznam souřadnic (číslo Y X Z) – .txt, .csv…")
        b = QPushButton("Vybrat…")
        b.clicked.connect(self._pick)
        row.addWidget(QLabel("Seznam:"))
        row.addWidget(self.path, 1)
        row.addWidget(b)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tolerance polohy:"))
        self.tol = QDoubleSpinBox()
        self.tol.setDecimals(3)
        self.tol.setRange(0.001, 5.0)
        self.tol.setValue(0.01)
        self.tol.setSuffix(" m")
        row.addWidget(self.tol)
        row.addStretch(1)
        self.b_run = QPushButton("Ověřit")
        self.b_run.setProperty("primarni", True)
        self.b_run.setDefault(True)
        self.b_run.clicked.connect(self.run)
        row.addWidget(self.b_run)
        lay.addLayout(row)
        self.cards = QHBoxLayout()
        self.card_labels = {}
        for key, title in (("ok", "v pořádku"), ("chybi", "chybí"), ("posunuty", "posunuté"),
                           ("cislo", "špatné číslo"), ("vyska", "špatná výška"), ("navic", "navíc")):
            fr = QFrame()
            fr.setObjectName("karta")
            fl = QVBoxLayout(fr)
            fl.setContentsMargins(10, 6, 10, 6)
            n = QLabel("–")
            n.setObjectName("karta_cislo")
            n.setStyleSheet(f"color: {COL[key]};")
            c = QLabel(title)
            c.setObjectName("karta_popis")
            fl.addWidget(n)
            fl.addWidget(c)
            self.card_labels[key] = n
            self.cards.addWidget(fr, 1)
        lay.addLayout(self.cards)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Zobrazit:"))
        self.filter = QComboBox()
        self.filter.addItem("jen problémy", "problem")
        self.filter.addItem("všechny body", None)
        self.filter.currentIndexChanged.connect(self._fill)
        frow.addWidget(self.filter)
        frow.addStretch(1)
        hint = QLabel("Dvojklik na řádek přiblíží bod ve výkresu.")
        hint.setObjectName("karta_popis")
        frow.addWidget(hint)
        lay.addLayout(frow)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Bod", "Stav", "Odchylka", "Poznámka"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 90)
        self.table.cellDoubleClicked.connect(self._go)
        lay.addWidget(self.table, 1)
        brow = QHBoxLayout()
        self.b_save_list = QPushButton("Uložit seznam do projektu")
        self.b_save_list.setToolTip("Seznam se pak porovná při každé kontrole (F5)")
        self.b_save_list.clicked.connect(self._save_to_project)
        self.b_csv = QPushButton("Uložit výsledek (CSV)…")
        self.b_csv.clicked.connect(self._csv)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.close)
        brow.addWidget(self.b_save_list)
        brow.addWidget(self.b_csv)
        brow.addStretch(1)
        brow.addWidget(close)
        lay.addLayout(brow)
        if path:
            self.run()

    def _pick(self):
        f, _ = QFileDialog.getOpenFileName(self, "Seznam souřadnic", str(Path(self.path.text()).parent),
                                           "Seznam souřadnic (*.txt *.csv *.xyz *.crd *.sez *.pts);;Vše (*)")
        if f:
            self.path.setText(f)
            self.run()

    def run(self):
        d = getattr(self.win, "drawing", None)
        if d is None:
            QMessageBox.information(self, "Ověřit seznam", "Nejdřív otevřete výkres.")
            return
        path = self.path.text().strip()
        if not path or not Path(path).is_file():
            QMessageBox.information(self, "Ověřit seznam", "Vyberte soubor se seznamem souřadnic.")
            return
        try:
            pts = read_point_list(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Ověřit seznam", str(exc))
            return
        if not pts:
            QMessageBox.warning(self, "Ověřit seznam", "V souboru nejsou žádné body (očekává se „číslo Y X Z“).")
            return
        self.results, best, found = verify_points(d, pts, self.tol.value())
        c = Counter(r.stav for r in self.results)
        for k, lab in self.card_labels.items():
            lab.setText(str(c.get(k, 0)))
        if best is None:
            self.summary.setText("<span style='color:#B91C1C'><b>Žádný bod ze seznamu neleží ve výkresu.</b></span> "
                                 "Je to seznam k tomuto výkresu? (souřadnice S-JTSK Y X)")
        else:
            bad = len(pts) - c.get("ok", 0)
            self.summary.setText(
                (f"<span style='color:#15803D'><b>✓ Všech {len(pts)} bodů sedí</b></span>" if not bad else
                 f"<span style='color:#B91C1C'><b>{bad} z {len(pts)} bodů nesedí</b></span>")
                + f" · souřadnice ze seznamu jako {best}"
                + (f" · {c['navic']} bodů ve výkresu navíc" if c.get("navic") else ""))
        self._fill()
        self._overlay()

    def _shown(self):
        f = self.filter.currentData()
        return [r for r in self.results if f is None or r.stav != "ok"]

    def _fill(self, *_):
        rows = self._shown()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r.cislo, STAVY[r.stav], "" if r.odchylka is None else f"{r.odchylka * 1000:.0f} mm", r.poznamka]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 1:
                    it.setForeground(QBrush(QColor(COL[r.stav])))
                self.table.setItem(i, c, it)

    def _overlay(self):
        items = [(r.feature, QColor(COL[r.stav]), r.stav == "navic") for r in self.results
                 if r.stav != "ok" and r.feature is not None and getattr(r.feature, "geometry", None) is not None]
        self.win.view.set_overlay(items)

    def _go(self, row, _col):
        rows = self._shown()
        if 0 <= row < len(rows):
            r = rows[row]
            self.win.tabs.setCurrentWidget(self.win.split)
            self.win.view.zoom_to(r.x, r.y, 12.0)
            if r.feature is not None and getattr(r.feature, "fid", -1) >= 0:
                self.win.view.highlight_feature(r.feature.fid)

    def _save_to_project(self):
        p = getattr(self.win, "project", None)
        path = self.path.text().strip()
        if p is None or not Path(path).is_file():
            return
        p.add_attachment("seznamy", path)
        p.save()
        self.win.refresh_home()
        QMessageBox.information(self, "Seznam souřadnic", "Seznam je v projektu – porovná se při každé kontrole.")

    def _csv(self):
        if not self.results:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Uložit výsledek", "overeni_seznamu.csv", "CSV (*.csv)")
        if not f:
            return
        with open(f, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Bod", "Stav", "Odchylka [m]", "Y", "X", "Poznámka"])
            for r in self.results:
                w.writerow([r.cislo, STAVY[r.stav], "" if r.odchylka is None else f"{r.odchylka:.3f}",
                            f"{r.x:.3f}", f"{r.y:.3f}", r.poznamka])

    def closeEvent(self, e):  # noqa: N802
        self.win.view.clear_overlay()
        super().closeEvent(e)
