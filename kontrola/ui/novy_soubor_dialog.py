"""Nový soubor jako v MicroStationu: seed podle druhu výkresu (seedy aktivní pracovní sady nebo libovolný)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from ..cad import pracovni_sady as PS

BEZ_SEEDU = "(bez seedu – prázdný výkres)"


class NovySouborDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nový soubor")
        self.resize(620, 170)
        self.sada = PS.aktivni()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Pracovní sada: <b>" + (f"{self.sada.nazev}</b> ({self.sada.prostredi})"
                                                     if self.sada else "žádná</b> (Soubor → Pracovní sada…)")
                             + "<br>Seed zvolte podle druhu výkresu (2D / 3D, výkres, list…), jak chce zadání."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Seed:"))
        self.seedy = QComboBox()
        self.seedy.setMinimumWidth(380)
        row.addWidget(self.seedy, 1)
        self.b_jiny = QPushButton("Procházet…")
        row.addWidget(self.b_jiny)
        lay.addLayout(row)
        self.cesta = QLabel()
        self.cesta.setStyleSheet("color: gray;")
        self.cesta.setWordWrap(True)
        lay.addWidget(self.cesta)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Vytvořit")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.seedy.addItem(BEZ_SEEDU, "")
        for p in (self.sada.seedy if self.sada else []):
            self.seedy.addItem(p.name, str(p))
        posl = PS.posledni_seed(self.sada)
        if posl is not None:
            self.pridej_seed(str(posl))
        self.seedy.currentIndexChanged.connect(lambda _i: self.cesta.setText(self.seedy.currentData() or ""))
        self.cesta.setText(self.seedy.currentData() or "")
        self.b_jiny.clicked.connect(self._prochazet)

    def pridej_seed(self, cesta: str) -> None:
        i = self.seedy.findData(cesta)
        if i < 0:
            self.seedy.addItem(Path(cesta).name, cesta)
            i = self.seedy.count() - 1
        self.seedy.setCurrentIndex(i)

    def _prochazet(self):
        start = str(self.sada.slozka) if self.sada else ""
        c, _ = QFileDialog.getOpenFileName(self, "Seed", start, "Seed (*.dgn *.dxf)")
        if c:
            self.pridej_seed(c)

    def seed(self) -> str:
        return self.seedy.currentData() or ""

    def _ok(self):
        PS.zapamatuj_seed(self.sada, Path(self.seed()) if self.seed() else None)
        self.accept()
