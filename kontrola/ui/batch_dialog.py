"""Hromadná kontrola: více výkresů najednou (např. všechny DXF ve složce) se souhrnnou tabulkou."""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .worker import BackgroundTask

COLS = ["Výkres", "Prvků", "Chyby", "Varování", "Info", "Skóre", "Nejčastější chyba"]


def check_files(files, rules, config, progress, cancelled):
    from collections import Counter

    from ..io.dxf_loader import load_drawing
    from ..runner import run_checks
    from ..skore import compute_score
    out = []
    for k, f in enumerate(files):
        if cancelled():
            break
        progress(int(k * 100 / max(1, len(files))), f"Kontroluji {Path(f).name}…")
        try:
            d = load_drawing(f)
            res = run_checks(d, rules, config)
            c = Counter(i.severity.value for i in res.issues)
            top = Counter(i.check_name for i in res.issues if i.severity.value == "chyba").most_common(1)
            sk = compute_score(res.issues, bool(rules.pravidla))
            out.append({"soubor": str(f), "prvku": len(d.features), "chyby": c.get("chyba", 0),
                        "varovani": c.get("varování", 0), "info": c.get("info", 0), "skore": sk.hodnota,
                        "barva": sk.barva, "top": f"{top[0][0]} ({top[0][1]}×)" if top else "–", "chyba": ""})
        except Exception as exc:  # noqa: BLE001 – jeden vadný soubor nezastaví ostatní
            out.append({"soubor": str(f), "prvku": 0, "chyby": 0, "varovani": 0, "info": 0, "skore": None,
                        "barva": "#6B7280", "top": "", "chyba": str(exc)})
    progress(100, "Hotovo")
    return out


class BatchDialog(QDialog):
    def __init__(self, win, files: list[str]):
        super().__init__(win)
        self.win = win
        self.files = files
        self.rows: list[dict] = []
        self.setWindowTitle("Hromadná kontrola výkresů")
        self.resize(980, 520)
        lay = QVBoxLayout(self)
        self.info = QLabel(f"Kontroluji {len(files)} výkresů s pravidly a nastavením aktuálního projektu…")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.bar = QProgressBar()
        lay.addWidget(self.bar)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._open)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        hint = QLabel("Dvojklik na řádek otevře výkres v aplikaci.")
        hint.setObjectName("karta_popis")
        row.addWidget(hint, 1)
        self.b_csv = QPushButton("Uložit tabulku (CSV)…")
        self.b_csv.setEnabled(False)
        self.b_csv.clicked.connect(self._save)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.reject)
        row.addWidget(self.b_csv)
        row.addWidget(close)
        lay.addLayout(row)
        p = win.project
        rules, config = p.rules, p.config
        self.task = BackgroundTask(lambda prog, canc: check_files(files, rules, config, prog, canc), self)
        self.task.progress.connect(lambda v, m: (self.bar.setValue(v), self.info.setText(m)))
        self.task.finished.connect(self._done)
        self.task.failed.connect(lambda msg: self.info.setText(f"Chyba: {msg}"))
        self.task.start()

    def _done(self, rows):
        self.rows = rows
        self.table.setRowCount(len(rows))
        for r, d in enumerate(rows):
            vals = [Path(d["soubor"]).name, str(d["prvku"]), str(d["chyby"]), str(d["varovani"]), str(d["info"]),
                    "–" if d["skore"] is None else str(d["skore"]), d["chyba"] or d["top"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(d["soubor"])
                if c == 5:
                    it.setForeground(QBrush(QColor(d["barva"])))
                if c in (1, 2, 3, 4, 5):
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if d["chyba"]:
                    it.setForeground(QBrush(QColor("#B91C1C")))
                self.table.setItem(r, c, it)
        ok = sum(1 for d in rows if d["skore"] == 100)
        self.info.setText(f"Hotovo: {len(rows)} výkresů, připraveno k odevzdání {ok}.")
        self.b_csv.setEnabled(bool(rows))

    def _open(self, row, _col):
        if 0 <= row < len(self.rows):
            self.accept()
            self.win.open_path(self.rows[row]["soubor"])

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Uložit souhrn", "hromadna_kontrola.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(COLS + ["Chyba načtení"])
            for d in self.rows:
                w.writerow([d["soubor"], d["prvku"], d["chyby"], d["varovani"], d["info"], d["skore"], d["top"],
                            d["chyba"]])
        QMessageBox.information(self, "Hromadná kontrola", f"Uloženo: {path}")

    def reject(self):
        if self.task.is_running():
            self.task.cancel()
        super().reject()
