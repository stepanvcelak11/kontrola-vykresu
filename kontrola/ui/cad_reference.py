"""Správce referencí CAD: připojit DXF podklad, poloha / měřítko / natočení, zobrazení, úchyty, kopie."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

SL = ("Reference", "Soubor", "Vložení Y", "Vložení X", "Měřítko", "Natočení [°]", "Zobrazit", "Úchyty", "Prvků",
      "Stav")


def _cislo(t: str) -> float:
    return float(t.strip().replace(",", ".").replace(" ", ""))


class ReferenceDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Reference (připojené výkresy)")
        self.resize(980, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Reference je jiný výkres DXF zobrazený pod vaším výkresem – jen pro čtení. Dá se na "
                             "něj přichytávat a kopírovat z něj prvky. Ve výkresu se uloží jako XREF (cesta "
                             "k souboru), obsah reference se do vašeho výkresu nekopíruje."))
        self.tab = QTableWidget(0, len(SL))
        self.tab.setHorizontalHeaderLabels(SL)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab.verticalHeader().setVisible(False)
        self.tab.itemChanged.connect(self._zmena)
        lay.addWidget(self.tab, 1)
        row = QHBoxLayout()
        self.b_pripojit = QPushButton("Připojit…")
        self.b_odpojit = QPushButton("Odpojit")
        self.b_nacist = QPushButton("Znovu načíst")
        self.b_kopie = QPushButton("Kopírovat prvky do výkresu")
        self.b_zoom = QPushButton("Přiblížit na referenci")
        self.b_zavrit = QPushButton("Zavřít")
        for b in (self.b_pripojit, self.b_odpojit, self.b_nacist, self.b_kopie, self.b_zoom):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.b_zavrit)
        lay.addLayout(row)
        self.b_pripojit.clicked.connect(lambda: self.pripojit())
        self.b_odpojit.clicked.connect(self.odpojit)
        self.b_nacist.clicked.connect(self.nacist)
        self.b_kopie.clicked.connect(self.kopirovat)
        self.b_zoom.clicked.connect(self.priblizit)
        self.b_zavrit.clicked.connect(self.accept)
        self._plneni = False
        self.naplnit()

    def _refs(self):
        return [r for r in self.page.reference if r.pripojena]

    def naplnit(self):
        self._plneni = True
        refs = self._refs()
        self.tab.setRowCount(len(refs))
        sj = self.page.sjtsk
        for i, r in enumerate(refs):
            y, x = (-r.vlozeni[0], -r.vlozeni[1]) if sj else r.vlozeni
            vals = [r.nazev, str(r.cesta), f"{y:.3f}", f"{x:.3f}", f"{r.meritko:g}", f"{r.natoceni:g}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (0, 1):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tab.setItem(i, c, it)
            for c, on in ((6, r.viditelna), (7, r.uchyty)):
                ch = QTableWidgetItem()
                ch.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                ch.setCheckState(Qt.Checked if on else Qt.Unchecked)
                self.tab.setItem(i, c, ch)
            n = len(r.doc.modelspace()) if r.doc is not None else 0
            for c, v in ((8, str(n)), (9, r.chyba or "načteno")):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tab.setItem(i, c, it)
        self.tab.resizeColumnsToContents()
        self.tab.setColumnWidth(1, min(320, self.tab.columnWidth(1)))
        self._plneni = False

    def _zmena(self, it: QTableWidgetItem):
        if self._plneni:
            return
        refs = self._refs()
        if it.row() >= len(refs):
            return
        r = refs[it.row()]
        c = it.column()
        try:
            if c in (2, 3):
                y, x = _cislo(self.tab.item(it.row(), 2).text()), _cislo(self.tab.item(it.row(), 3).text())
                r.vlozeni = (-y, -x) if self.page.sjtsk else (y, x)
            elif c == 4:
                m = _cislo(it.text())
                if m <= 0:
                    raise ValueError
                r.meritko = m
            elif c == 5:
                r.natoceni = _cislo(it.text())
            elif c == 6:
                r.viditelna = it.checkState() == Qt.Checked
            elif c == 7:
                r.uchyty = it.checkState() == Qt.Checked
            else:
                return
        except ValueError:
            QMessageBox.warning(self, "Reference", "Zadejte číslo (měřítko kladné).")
            self.naplnit()
            return
        self.page.reference_zmeneny()

    def _aktualni(self):
        refs = self._refs()
        i = self.tab.currentRow()
        return refs[i] if 0 <= i < len(refs) else (refs[0] if len(refs) == 1 else None)

    def pripojit(self, cesta: str | None = None):
        if cesta is None:
            cesta, _ = QFileDialog.getOpenFileName(self, "Připojit referenci", "", "DXF (*.dxf)")
            if not cesta:
                return None
        try:
            r = self.page.pripoj_referenci(cesta)
        except ValueError as e:
            QMessageBox.warning(self, "Reference", str(e))
            return None
        self.naplnit()
        return r

    def odpojit(self):
        from ..cad import reference as R
        r = self._aktualni()
        if r is None:
            return
        R.odpoj(self.page.dok.doc, self.page.historie_zmen, r)
        self.page.reference_zmeneny()
        self.page._aktualizuj_tlacitka()
        self.page.vypis(f"Reference {r.cesta.name} odpojena (Zpět ji vrátí).")
        self.naplnit()

    def nacist(self):
        for r in self._refs():
            r.nacti()
        self.page.reference_zmeneny()
        self.naplnit()

    def kopirovat(self):
        from ..cad import reference as R
        r = self._aktualni()
        if r is None:
            return []
        nove = R.kopiruj(self.page.prostor, self.page.historie_zmen, r)
        self.page._po_zmene(nove, [])
        self.page.vypis(f"Z reference {r.cesta.name} zkopírováno {len(nove)} prvků do výkresu (Zpět je vrátí).")
        return nove

    def priblizit(self):
        from PySide6.QtCore import QRectF
        r = self._aktualni()
        g = getattr(self.page, "_ref_skupiny", {}).get(r.nazev) if r else None
        if g is not None:
            self.page.view.zoom_all(g.sceneBoundingRect() if not g.sceneBoundingRect().isEmpty() else QRectF())
