"""Výběr pracovní sady – jako úvodní obrazovka MicroStationu (Pracovní prostředí / Pracovní sada)."""

from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from ..cad import pracovni_sady as PS


class PracovniSadaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pracovní sada")
        self.resize(760, 460)
        self.zmeneno = False
        self.novy_soubor = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Jako v MicroStationu: pracovní sada určuje seed nového výkresu (hladiny), buňky a styly čar. "
            "Přidejte složku se školním nastavením MicroStationu (např. Skolni_nastaveni_CONNECT nebo "
            "…\\Configuration\\WorkSpaces) nebo složku s knihovnami od učitele (GEO-V8.CEL, GEO.RSC, SJTSK-V8.DGN)."))
        h = QHBoxLayout()
        self.seznam = QListWidget()
        self.seznam.setMinimumWidth(280)
        h.addWidget(self.seznam, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setMinimumWidth(300)
        from PySide6.QtCore import Qt
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        h.addWidget(self.detail, 1)
        lay.addLayout(h, 1)
        row = QHBoxLayout()
        self.b_slozka = QPushButton("Přidat složku…")
        self.b_odebrat = QPushButton("Odebrat složku")
        row.addWidget(self.b_slozka)
        row.addWidget(self.b_odebrat)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox()
        self.b_pouzit = bb.addButton("Použít", QDialogButtonBox.AcceptRole)
        self.b_novy = bb.addButton("Použít a nový soubor", QDialogButtonBox.AcceptRole)
        bb.addButton("Zavřít", QDialogButtonBox.RejectRole)
        lay.addWidget(bb)
        self.b_slozka.clicked.connect(lambda: self.pridej_slozku())
        self.b_odebrat.clicked.connect(self.odeber_slozku)
        self.b_pouzit.clicked.connect(lambda: self.pouzij())
        self.b_novy.clicked.connect(lambda: self.pouzij(novy=True))
        bb.rejected.connect(self.reject)
        self.seznam.currentRowChanged.connect(self._ukaz)
        self.obnov()

    def obnov(self) -> None:
        akt = PS.aktivni()
        self.seznam.clear()
        it = QListWidgetItem("Žádná (vlastní nastavení aplikace)")
        it.setData(256, None)
        self.seznam.addItem(it)
        self._sady = PS.vsechny()
        for s in self._sady:
            it = QListWidgetItem(f"{s.nazev}   –   {s.prostredi}")
            it.setData(256, s.klic)
            self.seznam.addItem(it)
            if akt is not None and s.klic == akt.klic:
                self.seznam.setCurrentItem(it)
        if akt is None:
            self.seznam.setCurrentRow(0)
        self.b_odebrat.setEnabled(bool(PS.slozky()))

    def _vybrana(self) -> PS.Sada | None:
        it = self.seznam.currentItem()
        k = it.data(256) if it is not None else None
        return next((s for s in self._sady if s.klic == k), None)

    def _ukaz(self, _i=None) -> None:
        s = self._vybrana()
        if s is None:
            self.detail.setText("Bez pracovní sady z MicroStationu – výkres podle zadání a knihoven od učitele "
                                "(Připojit → Knihovny).")
            return
        self.detail.setText(f"<b>{s.nazev}</b> ({s.prostredi})<br>{s.slozka}<br><br>"
                            + s.popis().replace("; ", "<br>"))

    def pridej_slozku(self, slozka: str | None = None) -> list[PS.Sada]:
        if slozka is None:
            slozka = QFileDialog.getExistingDirectory(self, "Složka s nastavením MicroStationu")
            if not slozka:
                return []
        nove = PS.pridej_slozku(slozka)
        if not nove:
            self.detail.setText("V této složce nejsou pracovní sady ani knihovny buněk a stylů čar.")
            PS.odeber_slozku(slozka)
        self.obnov()
        return nove

    def odeber_slozku(self) -> None:
        s = self._vybrana()
        for f in PS.slozky():
            if s is not None and str(s.slozka).startswith(f):
                PS.odeber_slozku(f)
                break
        self.obnov()

    def pouzij(self, novy: bool = False) -> None:
        PS.nastav_aktivni(self._vybrana())
        self.zmeneno = True
        self.novy_soubor = novy
        self.accept()
