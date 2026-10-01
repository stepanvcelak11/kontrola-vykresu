"""Okno Tisk do PDF (CAD): papír, orientace, měřítko, oblast; razítko na list."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..cad import tisk as T


class TiskDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Tisk do PDF")
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.model = page._je_model()
        self.papir = QComboBox()
        self.papir.addItems(list(T.PAPIRY))
        self.papir.setCurrentText("A3")
        self.orientace = QComboBox()
        self.orientace.addItems(["na šířku", "na výšku"])
        self.meritko = QSpinBox()
        self.meritko.setRange(0, 1000000)
        self.meritko.setSpecialValueText("automaticky (vejde se)")
        rs = page._pravidla()
        self.meritko.setValue(int(rs.meritko) if rs is not None and rs.meritko else 0)
        self.meritko.setPrefix("1:")
        self.oblast = QComboBox()
        self.oblast.addItems(["celý výkres", "aktuální pohled"])
        self.soubor = QLineEdit(str(self._vychozi_soubor()))
        b = QPushButton("…")
        b.clicked.connect(self._vyber)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.soubor, 1)
        h.addWidget(b)
        if self.model:
            f.addRow("Papír:", self.papir)
            f.addRow("Orientace:", self.orientace)
            f.addRow("Měřítko:", self.meritko)
            f.addRow("Oblast:", self.oblast)
        else:
            f.addRow(QLabel(f"List „{page.prostor.name}“ se vytiskne 1:1 na svůj papír."))
        f.addRow("Soubor PDF:", row)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Tisknout")
        bb.accepted.connect(self.tisk)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.vysledek = None

    def _vychozi_soubor(self) -> Path:
        d = self.page.dok
        base = d.path.with_suffix("") if d and d.path else Path.home() / "vykres"
        suf = "" if self.model else f"_{self.page.prostor.name}"
        return Path(f"{base}{suf}.pdf")

    def _vyber(self):
        f, _ = QFileDialog.getSaveFileName(self, "Uložit PDF", self.soubor.text(), "PDF (*.pdf)")
        if f:
            self.soubor.setText(f)

    def tisk(self):
        pg = self.page
        oblast = None
        if self.model and self.oblast.currentIndex() == 1:
            r = pg.view.mapToScene(pg.view.viewport().rect()).boundingRect()
            oblast = (r.left(), r.top(), r.right(), r.bottom())
        try:
            self.vysledek = T.tisk_pdf(pg.dok.doc, pg.prostor, self.soubor.text(), papir=self.papir.currentText(),
                                       na_sirku=self.orientace.currentIndex() == 0,
                                       meritko=float(self.meritko.value()) or None, oblast=oblast,
                                       nazev=pg.dok.path.stem if pg.dok.path else "")
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Tisk", str(e))
            return
        m = self.vysledek["meritko"]
        pg.vypis(f"Vytištěno do PDF: {self.soubor.text()}" + (f" (1:{m:g}, {self.papir.currentText()})"
                                                             if self.model else " (list 1:1)"))
        self.accept()
