"""Malé okno „Další chyba“ – vždy navrchu, vedle MicroStationu: popis, postup, key-in, Opraveno / Další.

Při opravování v MicroStationu není potřeba přepínat do aplikace: okénko ukazuje vybranou chybu a jedním
klikem zkopíruje key-in (vycentrování na chybu, souřadnice cíle).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ..opravny_postup import krok


class MiniOkno(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.win = win
        self.setWindowTitle("Další chyba")
        self.setObjectName("mini_okno")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        self.head = QLabel()
        self.head.setWordWrap(True)
        self.head.setTextFormat(Qt.RichText)
        lay.addWidget(self.head)
        self.steps = QLabel()
        self.steps.setWordWrap(True)
        self.steps.setObjectName("karta_popis")
        lay.addWidget(self.steps)
        self.keyrow = QVBoxLayout()
        self.keyrow.setSpacing(3)
        lay.addLayout(self.keyrow)
        row = QHBoxLayout()
        self.b_prev = QPushButton("◀")
        self.b_prev.setFixedWidth(38)
        self.b_prev.setToolTip("Předchozí chyba")
        self.b_prev.clicked.connect(lambda: self._step(-1))
        self.b_ok = QPushButton("✓ Opraveno – další")
        self.b_ok.setProperty("uspech", True)
        self.b_ok.clicked.connect(self._fixed)
        self.b_next = QPushButton("▶")
        self.b_next.setFixedWidth(38)
        self.b_next.setToolTip("Další chyba (bez označení)")
        self.b_next.clicked.connect(lambda: self._step(1))
        for b in (self.b_prev, self.b_ok, self.b_next):
            row.addWidget(b)
        lay.addLayout(row)
        self.count = QLabel()
        self.count.setObjectName("karta_popis")
        lay.addWidget(self.count)
        win.issue_panel.issueSelected.connect(lambda _n: self.refresh())
        win.issue_panel.stateChanged.connect(lambda *a: self.refresh())
        self.refresh()

    def _step(self, d: int):
        self.win.issue_panel.step(d)
        self.refresh()

    def _fixed(self):
        self.win.issue_panel.set_state("opraveno")  # panel sám přejde na další chybu
        self.refresh()

    def _copy(self, text: str, btn: QPushButton):
        QApplication.clipboard().setText(text)
        old = btn.text()
        btn.setText("Zkopírováno ✓")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, btn, lambda: btn.setText(old))  # btn jako kontext: smazané tlačítko se přeskočí

    def refresh(self):
        iss = self.win.issue_panel.current_issue()
        while self.keyrow.count():
            it = self.keyrow.takeAt(0)
            if it.widget():
                it.widget().hide()  # deleteLater smaže až později – staré tlačítko nesmí zůstat vidět
                it.widget().deleteLater()
        todo = sum(1 for i in self.win.issues if i.state == "nová")
        self.count.setText(f"Zbývá opravit: {todo}")
        if iss is None:
            self.head.setText("<b>Vyberte chybu</b> v seznamu nebo stiskněte ▶.")
            self.steps.setText("")
            return
        from .theme import themed
        col = {"chyba": "#DC2626", "varování": "#D97706", "info": "#2563EB"}.get(iss.severity.value, "#6B7280")
        self.head.setText(f"<span style='color:{themed(col)};font-weight:800'>#{iss.number} {iss.severity.value}"
                          f"</span> · {iss.check_name}<br><b style='font-size:11pt'>{iss.message}</b>"
                          f"<br><span style='color:{themed('#6B7280')}'>vrstva {iss.layer or '–'} · "
                          f"Y {iss.x:.2f}  X {iss.y:.2f}</span>")
        try:
            k = krok(iss, self.win.drawing, self.win.project.config.tolerance if self.win.project else 0.01)
        except Exception:  # noqa: BLE001 – postup je jen pomůcka
            k = None
        self.steps.setText("<br>".join(f"{n}. {s}" for n, s in enumerate(k.postup[:4], 1)) if k else "")
        for popis, ki in (k.keyins[:3] if k else []):
            b = QPushButton(f"📋  {popis}")
            b.setToolTip(ki)
            b.setStyleSheet("text-align: left; padding: 4px 8px;")
            b.clicked.connect(lambda _c=False, t=ki, bb=b: self._copy(t, bb))
            self.keyrow.addWidget(b)
        self.adjustSize()
