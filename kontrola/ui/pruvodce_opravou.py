"""Okno „Opravný průvodce“: chyby jedna po druhé, s přesným postupem pro MicroStation a key-iny ke zkopírování.
Opravuje se ručně v DGN; aplikace nic nemění."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QTextBrowser, QVBoxLayout)

from ..checks.base import Severity
from ..opravny_postup import krok, poradi


class PruvodceOpravou(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Opravný průvodce – MicroStation")
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setModal(False)
        self.resize(560, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        top.addWidget(self.progress, 1)
        self.only_err = QCheckBox("jen chyby")
        self.only_err.setToolTip("Přeskočit varování")
        self.only_err.toggled.connect(lambda _: self.reload())
        top.addWidget(self.only_err)
        lay.addLayout(top)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 11pt; font-weight: 600;")
        lay.addWidget(self.title)
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self._copy_link)
        lay.addWidget(self.body, 1)
        hint = QLabel("Klik na <b>key-in</b> ho zkopíruje. V MicroStationu: Key-in (Nástroje → Key-in), Ctrl+V, "
                      "Enter. Okno zůstává nahoře, můžete ho mít vedle MicroStationu.")
        hint.setWordWrap(True)
        hint.setObjectName("karta_popis")
        lay.addWidget(hint)
        row = QHBoxLayout()
        self.b_prev = QPushButton("◀ Zpět")
        self.b_prev.clicked.connect(lambda: self.go(self.i - 1))
        self.b_skip = QPushButton("Přeskočit")
        self.b_skip.clicked.connect(lambda: self.go(self.i + 1))
        self.b_ign = QPushButton("Ignorovat")
        self.b_ign.clicked.connect(lambda: self._mark("ignorovat"))
        self.b_done = QPushButton("✓ Opraveno – další")
        self.b_done.setProperty("primarni", True)
        self.b_done.clicked.connect(lambda: self._mark("opraveno"))
        for b in (self.b_prev, self.b_skip, self.b_ign, self.b_done):
            b.setAutoDefault(False)  # jinak by dialog zvýraznil první tlačítko („Zpět“)
            row.addWidget(b)
        self.b_done.setDefault(True)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        b_list = QPushButton("Uložit opravný list (HTML)…")
        b_list.setToolTip("Všechny kroky s key-iny na jedné stránce – k vytištění nebo na druhý monitor")
        b_list.clicked.connect(self.save_list)
        row2.addWidget(b_list)
        row2.addStretch(1)
        close = QPushButton("Zavřít")
        close.clicked.connect(self.close)
        row2.addWidget(close)
        lay.addLayout(row2)
        self.items = []
        self.i = 0
        self.reload()

    def reload(self):
        todo = [i for i in self.win.issues if i.state == "nová" and i.severity != Severity.INFO
                and (not self.only_err.isChecked() or i.severity == Severity.CHYBA)]
        self.items = poradi(todo)
        self.progress.setMaximum(max(1, len(self.items)))
        self.go(0)

    def go(self, i: int):
        self.i = max(0, min(i, len(self.items)))
        self.progress.setValue(self.i)
        self.b_prev.setEnabled(self.i > 0)
        at_end = self.i >= len(self.items)
        for b in (self.b_skip, self.b_ign, self.b_done):
            b.setEnabled(not at_end)
        if at_end:
            self.title.setText("✓ Hotovo – všechno z průvodce máte za sebou." if self.items else
                               "Nic k opravě.")
            self.body.setHtml("<p>Uložte výkres v MicroStationu jako DXF a zkontrolujte znovu (Ctrl+F5).</p>")
            return
        iss = self.items[self.i]
        self.win.issue_panel.select_issue(iss.number)
        self.title.setText(f"{self.i + 1}. #{iss.number} {iss.check_name}")
        self.body.setHtml(self._html(iss))

    def _html(self, iss) -> str:
        k = krok(iss, self.win.drawing, getattr(self.win.project.config, "tolerance", 0.01))
        steps = "".join(f"<li style='margin-bottom:4px'>{escape(s)}</li>" for s in k.postup)
        keys = "".join(f"<p style='margin:4px 0'>{escape(t)}:<br><a href='copy:{escape(v)}' "
                       f"style='font-family:Consolas,monospace; font-size:11pt'>{escape(v)}</a></p>"
                       for t, v in k.keyins)
        return (f"<p><b>{escape(k.nadpis)}</b><br><span style='color:#6B7280'>vrstva {escape(iss.layer or '–')}"
                f"</span></p><ol>{steps}</ol>{keys}")

    def _copy_link(self, url):
        s = url.toString()
        if s.startswith("copy:"):
            QApplication.clipboard().setText(s[5:])
            self.win.statusBar().showMessage(f"Zkopírováno: {s[5:]} – v MicroStationu Key-in, Ctrl+V, Enter", 6000)

    def _mark(self, state: str):
        if self.i >= len(self.items):
            return
        iss = self.items[self.i]
        self.win.issue_panel.select_issue(iss.number)
        self.win.issue_panel.set_state(state)
        self.go(self.i + 1)

    def save_list(self):
        f, _ = QFileDialog.getSaveFileName(self, "Opravný list", "opravny_list.html", "HTML (*.html)")
        if not f:
            return
        parts = []
        for n, iss in enumerate(self.items, 1):
            parts.append(f"<div class='k'><h3>☐ {n}. #{iss.number} {escape(iss.check_name)}</h3>{self._html(iss)}</div>")
        html = ("<!doctype html><meta charset='utf-8'><title>Opravný list</title><style>body{font-family:Segoe UI,"
                "Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px}.k{border-bottom:1px solid #ddd;"
                "padding:6px 0;page-break-inside:avoid}a{color:#1D4ED8;text-decoration:none}</style>"
                f"<h1>Opravný list – {escape(str(self.win.drawing.path) if self.win.drawing else '')}</h1>"
                f"<p>{len(self.items)} míst k opravě, seřazeno podle polohy. Key-in: Nástroje → Key-in, vložit, "
                "Enter.</p>" + "".join(parts))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(html)
        self.win.statusBar().showMessage(f"Opravný list uložen: {f}", 6000)
