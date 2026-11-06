"""Nový soubor jako v MicroStationu CONNECT: při založení výkresu se zvolí pracovní prostředí a pracovní sada
(v čem výkres bude – buňky, styly čar, hladiny) a seed podle druhu výkresu, k tomu název a složka souboru."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from ..cad import pracovni_sady as PS

BEZ_SEEDU = "(bez seedu – prázdný výkres)"
ZADNA = "(žádná – vlastní nastavení aplikace)"
KLIC_SLOZKA = "cad/nove_slozka"


class NovySouborDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nový")
        self.resize(660, 260)
        self._sady = PS.vsechny()
        lay = QVBoxLayout(self)
        g = QGridLayout()
        self.prostredi = QComboBox()
        self.sada_cb = QComboBox()
        self.b_slozky = QPushButton("Přidat nastavení…")
        self.b_slozky.setToolTip("Přidat složku se školním nastavením MicroStationu nebo s knihovnami od učitele")
        self.seedy = QComboBox()
        self.seedy.setMinimumWidth(380)
        self.b_jiny = QPushButton("Procházet…")
        self.nazev = QLineEdit()
        self.nazev.setPlaceholderText("např. 1_Mapa_Husovice (prázdné = zeptá se až při uložení)")
        self.slozka = QLineEdit(str(QSettings().value(KLIC_SLOZKA, "") or ""))
        self.b_slozka = QPushButton("Procházet…")
        self.typ = QComboBox()
        self.typ.addItem("DGN V7 – MicroStation (*.dgn)", ".dgn")
        self.typ.addItem("DXF – AutoCAD 2018 (*.dxf)", ".dxf")
        for r, (t, w, b) in enumerate((("Pracovní prostředí:", self.prostredi, self.b_slozky),
                                       ("Pracovní sada:", self.sada_cb, None),
                                       ("Seed:", self.seedy, self.b_jiny),
                                       ("Název souboru:", self.nazev, None),
                                       ("Složka:", self.slozka, self.b_slozka),
                                       ("Typ:", self.typ, None))):
            g.addWidget(QLabel(t), r, 0)
            g.addWidget(w, r, 1)
            if b is not None:
                g.addWidget(b, r, 2)
        lay.addLayout(g)
        self.cesta = QLabel()
        self.cesta.setStyleSheet("color: gray;")
        self.cesta.setWordWrap(True)
        lay.addWidget(self.cesta)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Vytvořit")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.prostredi.currentIndexChanged.connect(lambda _i: self._napln_sady())
        self.sada_cb.currentIndexChanged.connect(lambda _i: self._napln_seedy())
        self.seedy.currentIndexChanged.connect(lambda _i: self._popis())
        self.b_jiny.clicked.connect(self._prochazet)
        self.b_slozka.clicked.connect(self._vyber_slozku)
        self.b_slozky.clicked.connect(lambda: self.pridej_nastaveni())
        self._napln_prostredi(PS.aktivni())

    # ------------------------------------------------------------ pracovní prostředí / sada / seed
    def _napln_prostredi(self, vyber: PS.Sada | None = None) -> None:
        self.prostredi.blockSignals(True)
        self.prostredi.clear()
        self.prostredi.addItem(ZADNA, None)
        for p in dict.fromkeys(s.prostredi for s in self._sady):
            self.prostredi.addItem(p, p)
        i = self.prostredi.findData(vyber.prostredi) if vyber is not None else 0
        self.prostredi.setCurrentIndex(max(i, 0))
        self.prostredi.blockSignals(False)
        self._napln_sady(vyber)

    def _napln_sady(self, vyber: PS.Sada | None = None) -> None:
        p = self.prostredi.currentData()
        self.sada_cb.blockSignals(True)
        self.sada_cb.clear()
        for s in self._sady:
            if s.prostredi == p:
                self.sada_cb.addItem(s.nazev, s.klic)
        self.sada_cb.setEnabled(p is not None)
        if vyber is not None:
            self.sada_cb.setCurrentIndex(max(self.sada_cb.findData(vyber.klic), 0))
        self.sada_cb.blockSignals(False)
        self._napln_seedy()

    @property
    def sada(self) -> PS.Sada | None:
        k = self.sada_cb.currentData() if self.prostredi.currentData() is not None else None
        return next((s for s in self._sady if s.klic == k), None)

    def vyber_sadu(self, klic: str) -> None:
        s = next((s for s in self._sady if s.klic == klic), None)
        self._napln_prostredi(s)

    def _napln_seedy(self) -> None:
        self.seedy.blockSignals(True)
        self.seedy.clear()
        self.seedy.addItem(BEZ_SEEDU, "")
        for p in (self.sada.seedy if self.sada else []):
            self.seedy.addItem(p.name, str(p))
        self.seedy.blockSignals(False)
        posl = PS.posledni_seed(self.sada)
        if posl is not None:
            self.pridej_seed(str(posl))
        self._popis()

    def _popis(self) -> None:
        s = self.sada
        self.cesta.setText((self.seed() or "Prázdný výkres") + (f"<br>Sada: {s.popis()}" if s else ""))

    def pridej_seed(self, cesta: str) -> None:
        i = self.seedy.findData(cesta)
        if i < 0:
            self.seedy.addItem(Path(cesta).name, cesta)
            i = self.seedy.count() - 1
        self.seedy.setCurrentIndex(i)

    def pridej_nastaveni(self, slozka: str | None = None) -> None:
        if slozka is None:
            slozka = QFileDialog.getExistingDirectory(self, "Složka s nastavením MicroStationu")
            if not slozka:
                return
        nove = PS.pridej_slozku(slozka)
        if not nove:
            PS.odeber_slozku(slozka)
            self.cesta.setText("V této složce nejsou pracovní sady ani knihovny buněk a stylů čar.")
            return
        self._sady = PS.vsechny()
        self._napln_prostredi(nove[0])

    def _prochazet(self):
        start = str(self.sada.slozka) if self.sada else ""
        c, _ = QFileDialog.getOpenFileName(self, "Seed", start, "Seed (*.dgn *.dxf)")
        if c:
            self.pridej_seed(c)

    def _vyber_slozku(self):
        c = QFileDialog.getExistingDirectory(self, "Složka nového výkresu", self.slozka.text())
        if c:
            self.slozka.setText(c)

    # ------------------------------------------------------------ výsledek
    def seed(self) -> str:
        return self.seedy.currentData() or ""

    def soubor(self) -> Path | None:
        """Cesta nového souboru (None = bez názvu, zeptá se při uložení)."""
        n = self.nazev.text().strip()
        if not n:
            return None
        p = Path(n)
        if p.suffix.lower() not in (".dgn", ".dxf"):
            p = p.with_name(p.name + self.typ.currentData())
        return p if p.is_absolute() else Path(self.slozka.text() or ".") / p

    def _ok(self):
        PS.nastav_aktivni(self.sada)
        PS.zapamatuj_seed(self.sada, Path(self.seed()) if self.seed() else None)
        if self.slozka.text():
            QSettings().setValue(KLIC_SLOZKA, self.slozka.text())
        self.accept()
