"""Okno Kódovník: kód bodu z terénu → linie / plocha / bodová značka, hladina a vzhled podle zadání."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..geodezie.kodovnik import DRUHY, NAZVY_SLOUPCU, SLOUPCE, Kod, Kodovnik

NAPOVEDA = ("<b>Kódy u bodů</b> (v totální stanici, QTrig nebo seznamu souřadnic): <code>PL</code> – bod linie s kódem "
            "PL (spojuje se v pořadí čísel bodů), <code>PL/Z</code> začátek nové linie, <code>PL/K</code> konec, "
            "<code>PL/U</code> uzavřít, <code>PL#2</code> druhá souběžná linie, víc kódů oddělte mezerou "
            "(<code>PL BUD/Z</code>). Kód, který tu není, se hledá v zadání: číslo buňky (3.13 strom) → značka, "
            "číslo stylu (2.13 plot) → linie.")


def soubor_kodovniku(win) -> Path:
    """Kódovník projektu (kodovnik.csv ve složce projektu), bez projektu v datech aplikace."""
    pr = getattr(win, "project", None)
    if pr is not None and getattr(pr, "root", None):
        return Path(pr.root) / "kodovnik.csv"
    d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or str(Path.home() / ".kontrola_vykresu")
    return Path(d) / "kodovnik.csv"


def nacti_kodovnik(win, predvolby) -> Kodovnik:
    f = soubor_kodovniku(win)
    if f.is_file():
        try:
            return Kodovnik.nacti(f)
        except (OSError, ValueError):
            pass
    return Kodovnik.ze_zadani(predvolby)


class KodovnikDialog(QDialog):
    def __init__(self, win, predvolby, parent=None):
        super().__init__(parent or win)
        self.win, self.predvolby = win, list(predvolby or [])
        self.setWindowTitle("Kódovník – kódování prvků účelové mapy")
        self.resize(980, 620)
        lay = QVBoxLayout(self)
        info = QLabel(NAPOVEDA)
        info.setWordWrap(True)
        lay.addWidget(info)
        self.tab = QTableWidget(0, len(SLOUPCE))
        self.tab.setHorizontalHeaderLabels([NAZVY_SLOUPCU[s] for s in SLOUPCE])
        self.tab.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tab.horizontalHeader().setStretchLastSection(True)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        for i, w in enumerate((90, 220, 90, 260, 140, 80, 80)):
            self.tab.setColumnWidth(i, w)
        lay.addWidget(self.tab, 1)
        r = QHBoxLayout()
        for text, fn in (("+ Kód", self.pridej), ("Smazat", self.smaz), ("Doplnit ze zadání", self.ze_zadani),
                         ("Načíst…", self.nacti), ("Uložit jako…", self.uloz_jako)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r.addWidget(b)
        r.addStretch(1)
        self.stav = QLabel()
        r.addWidget(self.stav)
        ok = QPushButton("Uložit")
        ok.setProperty("primarni", True)
        ok.clicked.connect(self.uloz)
        zav = QPushButton("Zavřít")
        zav.clicked.connect(self.reject)
        r.addWidget(ok)
        r.addWidget(zav)
        lay.addLayout(r)
        self.nastav(nacti_kodovnik(win, self.predvolby))

    # ------------------------------------------------------------ tabulka
    def nastav(self, kv: Kodovnik):
        self.tab.setRowCount(0)
        for k in kv.kody:
            self._radek(k)
        self.stav.setText(f"{len(kv)} kódů")

    def _radek(self, k: Kod, row: int | None = None):
        row = self.tab.rowCount() if row is None else row
        self.tab.insertRow(row)
        for i, s in enumerate(SLOUPCE):
            if s == "druh":
                cb = QComboBox()
                cb.addItems(list(DRUHY))
                cb.setCurrentText(k.druh)
                self.tab.setCellWidget(row, i, cb)
            elif s == "predvolba":
                cb = QComboBox()
                cb.setEditable(True)
                cb.addItems([""] + [p.nazev for p in self.predvolby])
                cb.setCurrentText(k.predvolba)
                self.tab.setCellWidget(row, i, cb)
            else:
                self.tab.setItem(row, i, QTableWidgetItem(getattr(k, s)))
        return row

    def kodovnik(self) -> Kodovnik:
        kody = []
        for r in range(self.tab.rowCount()):
            h = {}
            for i, s in enumerate(SLOUPCE):
                w = self.tab.cellWidget(r, i)
                it = self.tab.item(r, i)
                h[s] = (w.currentText() if isinstance(w, QComboBox) else (it.text() if it else "")).strip()
            if h["kod"]:
                kody.append(Kod(**h))
        return Kodovnik(kody)

    def pridej(self):
        r = self._radek(Kod(""), self.tab.currentRow() + 1 if self.tab.currentRow() >= 0 else None)
        self.tab.setCurrentCell(r, 0)
        self.tab.editItem(self.tab.item(r, 0))

    def smaz(self):
        for r in sorted({i.row() for i in self.tab.selectedIndexes()}, reverse=True):
            self.tab.removeRow(r)

    def ze_zadani(self):
        kv = self.kodovnik()
        nove = [k for k in Kodovnik.ze_zadani(self.predvolby).kody if kv.najdi(k.kod) is None]
        for k in nove:
            self._radek(k)
        self.stav.setText(f"Doplněno {len(nove)} kódů ze zadání." if nove else "Ze zadání není co doplnit.")

    def nacti(self):
        f, _ = QFileDialog.getOpenFileName(self, "Načíst kódovník", "", "Kódovník (*.csv *.txt);;Všechny soubory (*)")
        if f:
            try:
                self.nastav(Kodovnik.nacti(f))
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Kódovník", f"Soubor nejde načíst: {e}")

    def uloz_jako(self):
        f, _ = QFileDialog.getSaveFileName(self, "Uložit kódovník", "kodovnik.csv", "Kódovník (*.csv)")
        if f:
            self.kodovnik().uloz(f)

    def uloz(self):
        f = self.kodovnik().uloz(soubor_kodovniku(self.win))
        self.stav.setText(f"Uloženo ({f.name}).")
        self.accept()
