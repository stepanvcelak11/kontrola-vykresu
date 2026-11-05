"""Okno „Knihovny od učitele“: buňky a styly čar, které jsou v každém výkresu (jako standardy MicroStationu)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from ..cad import knihovny as K


class KnihovnyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Knihovny od učitele – buňky a styly čar")
        self.resize(620, 400)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Knihovny buněk (.cel, .dxf), styly čar (.rsc) a typy čar (.lin). Přidají se jednou a jsou pak "
            "v každém výkresu – když učitel zadá nové buňky nebo styly, přidejte další soubor. Stejnojmenný "
            "soubor nahradí starší verzi."))
        self.seznam = QListWidget()
        lay.addWidget(self.seznam, 1)
        row = QHBoxLayout()
        self.b_pridat = QPushButton("Přidat…")
        self.b_odebrat = QPushButton("Odebrat")
        row.addWidget(self.b_pridat)
        row.addWidget(self.b_odebrat)
        row.addStretch(1)
        lay.addLayout(row)
        self.zprava = QLabel()
        self.zprava.setWordWrap(True)
        lay.addWidget(self.zprava)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        lay.addWidget(bb)
        self.b_pridat.clicked.connect(lambda: self.pridej())
        self.b_odebrat.clicked.connect(self.odeber)
        self.zmeneno = False
        self.obnov()

    def obnov(self) -> None:
        self.seznam.clear()
        for p in K.soubory():
            k = K.popis(p)
            t = f"{p.name}  –  {k.druh}: " + (f"{k.pocet}" if k.pocet >= 0 else f"nejde načíst ({k.chyba})")
            it = QListWidgetItem(t)
            it.setData(256, str(p))
            self.seznam.addItem(it)
        self.b_odebrat.setEnabled(self.seznam.count() > 0)

    def pridej(self, cesty: list[str] | None = None) -> list[K.Knihovna]:
        if cesty is None:
            cesty, _ = QFileDialog.getOpenFileNames(self, "Knihovny od učitele", "",
                                                    "Knihovny (*.cel *.CEL *.rsc *.RSC *.dxf *.lin)")
        vys = [K.pridej(c) for c in cesty]
        ok = [k for k in vys if k.pocet > 0]
        chyby = [k.chyba for k in vys if k.pocet <= 0]
        self.zmeneno = self.zmeneno or bool(ok)
        self.zprava.setText("; ".join([f"✓ {k.cesta.name}: {k.pocet} – {k.druh}" for k in ok]
                                      + [f"⚠ {c}" for c in chyby]))
        self.obnov()
        return vys

    def odeber(self) -> None:
        it = self.seznam.currentItem()
        if it is None:
            return
        K.odeber(Path(it.data(256)))
        self.zmeneno = True
        self.obnov()
