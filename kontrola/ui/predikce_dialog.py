"""Okno „Učitelův pohled“: předpověď protokolu od učitele a náhled protokolu v jeho formátu."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout)

from ..predikce import label, predict


class PredikceDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Učitelův pohled – předpověď protokolu")
        self.resize(900, 620)
        lay = QVBoxLayout(self)
        p = predict(win.drawing, win.project.rules, win.issues)
        self.pred = p
        head = QLabel(f"<h2 style='margin:0; color:{p.barva}'>{p.verdikt}</h2>"
                      + (f"Odhad vychází z {p.protokolu} protokolů od učitele, které jste porovnali."
                         if p.protokolu else
                         "Zatím jste neporovnali žádný protokol od učitele – odhad je stejný jako výsledek kontroly. "
                         "Až dostanete protokol (.log), dejte <b>Kontrola → Porovnat s protokolem učitele</b> "
                         "a aplikace se naučí, co učitel hlásí."))
        head.setWordWrap(True)
        lay.addWidget(head)
        tabs = QTabWidget()
        self.table = QTableWidget(len(p.skupiny), 5)
        self.table.setHorizontalHeaderLabels(["Chybné atributy", "Program hlásí", "Učitel nejspíš", "Vrstvy",
                                              "Proč"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        for r, s in enumerate(p.skupiny):
            for c, v in enumerate([label(s.klic), str(s.program), str(s.predpoved), ", ".join(s.vrstvy[:5]),
                                   s.poznamka]):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        tabs.addTab(self.table, f"Symbologie ({p.atributy})")
        warn = QPlainTextEdit("\n".join(p.pozor) if p.pozor else "Z dřívějších protokolů nic navíc.")
        warn.setReadOnly(True)
        tabs.addTab(warn, f"Pozor ({len(p.pozor)})")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        self.log.setFont(f)
        self.log.setPlainText(self._log_text())
        tabs.addTab(self.log, "Náhled protokolu (jako od učitele)")
        lay.addWidget(tabs, 1)
        info = QLabel(f"Topologie (kontrola kresby MGEO): nejspíš <b>{p.topologie}</b> chyb. "
                      "Odhad není známka – slouží k tomu, abyste věděli, co učitel uvidí.")
        info.setWordWrap(True)
        lay.addWidget(info)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _log_text(self) -> str:
        from ..export.mgeo_log import export_mgeo_log
        w = self.win
        out = Path(tempfile.mkdtemp(prefix="kontrola_log_")) / "nahled.log"
        try:
            export_mgeo_log(w.drawing, w.project.rules, [i for i in w.issues if i.state == "nová"], out,
                            w.project.name, f"1:{w.project.rules.meritko}" if w.project.rules.meritko else "")
            return out.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return f"Náhled protokolu nejde vytvořit: {exc}"
