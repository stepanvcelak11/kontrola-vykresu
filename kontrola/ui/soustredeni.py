"""Režim soustředění: jen výkres a jedna chyba velkým písmem dole; Opraveno / Další, Esc konec.

Všechny lišty, panely a minimapa se schovají, aby nic nerušilo – jako „čtecí režim“.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class FocusBar(QFrame):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("plovouci_panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 12, 12)
        lay.setSpacing(10)
        txt = QVBoxLayout()
        txt.setSpacing(2)
        self.title = QLabel()
        self.title.setTextFormat(Qt.RichText)
        self.title.setWordWrap(True)
        self.sub = QLabel()
        self.sub.setObjectName("karta_popis")
        self.sub.setWordWrap(True)
        txt.addWidget(self.title)
        txt.addWidget(self.sub)
        lay.addLayout(txt, 1)
        self.b_prev = QPushButton("◀")
        self.b_prev.setToolTip("Předchozí chyba (F7)")
        self.b_prev.clicked.connect(lambda: self._step(-1))
        self.b_ok = QPushButton("✓ Opraveno")
        self.b_ok.setProperty("uspech", True)
        self.b_ok.setToolTip("Označit jako opravenou a přejít na další")
        self.b_ok.clicked.connect(self._fixed)
        self.b_next = QPushButton("Další ▶")
        self.b_next.setToolTip("Další chyba (F8)")
        self.b_next.clicked.connect(lambda: self._step(1))
        self.b_end = QPushButton("✕ Konec")
        self.b_end.setToolTip("Ukončit režim soustředění (Esc)")
        self.b_end.clicked.connect(lambda: win.a_focus.setChecked(False))
        for b in (self.b_prev, self.b_ok, self.b_next, self.b_end):
            b.setMinimumHeight(40)
            lay.addWidget(b)
        self.b_prev.setFixedWidth(44)

    def _step(self, d: int):
        self.win.issue_panel.step(d)
        self.refresh()

    def _fixed(self):
        self.win.issue_panel.set_state("opraveno")
        self.refresh()

    def refresh(self):
        iss = self.win.issue_panel.current_issue()
        todo = sum(1 for i in self.win.issues if i.state == "nová")
        if iss is None or (todo == 0 and iss.state != "nová"):
            if todo == 0 and self.win.issues:
                self.title.setText("<span style='font-size:15pt;font-weight:800'>Hotovo – vše opraveno 🎉</span>")
            else:
                self.title.setText("<span style='font-size:15pt;font-weight:800'>Žádná vybraná chyba</span>")
            self.sub.setText(f"Zbývá opravit: {todo}  ·  Esc = konec")
            return
        from .theme import themed
        col = {"chyba": "#DC2626", "varování": "#D97706", "info": "#2563EB"}.get(iss.severity.value, "#6B7280")
        self.title.setText(f"<span style='color:{themed(col)};font-size:11pt;font-weight:800'>#{iss.number} "
                           f"{iss.severity.value}</span>&nbsp;&nbsp;<span style='font-size:16pt;font-weight:800'>"
                           f"{iss.message}</span>")
        self.sub.setText(f"{iss.check_name} · vrstva {iss.layer or '–'} · Y {iss.x:.2f}  X {iss.y:.2f}"
                         f"   ·   zbývá opravit: {todo}   ·   Esc = konec")
