"""Správce vrstev CAD: zapnutí, zmrazení, zámek, barva, typ čáry, tloušťka, nová / přejmenovat / smazat,
aktuální vrstva a počet prvků ve vrstvě."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel,
                               QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

SLOUPCE = ("Vrstva", "Zapnutá", "Zmrazená", "Zamčená", "Barva", "Typ čáry", "Tloušťka", "Prvků")
TLOUSTKY = [-3, 0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]


def pocty_ve_vrstvach(msp) -> Counter:
    return Counter(e.dxf.get("layer", "0") for e in msp)


class VrstvyDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.doc = page.dok.doc
        self.zmeneno = False
        self.setWindowTitle("Vrstvy")
        self.resize(820, 480)
        lay = QVBoxLayout(self)
        self.info = QLabel()
        lay.addWidget(self.info)
        self.tab = QTableWidget(0, len(SLOUPCE))
        self.tab.setHorizontalHeaderLabels(SLOUPCE)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab.verticalHeader().setVisible(False)
        lay.addWidget(self.tab, 1)
        row = QHBoxLayout()
        self.b_new = QPushButton("Nová…")
        self.b_ren = QPushButton("Přejmenovat…")
        self.b_del = QPushButton("Smazat")
        self.b_cur = QPushButton("Nastavit jako aktuální")
        self.b_vyber = QPushButton("Vybrat prvky vrstvy")
        self.b_close = QPushButton("Zavřít")
        for b in (self.b_new, self.b_ren, self.b_del, self.b_cur, self.b_vyber):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.b_close)
        lay.addLayout(row)
        self.b_new.clicked.connect(lambda: self.nova())
        self.b_ren.clicked.connect(lambda: self.prejmenuj())
        self.b_del.clicked.connect(self.smaz)
        self.b_cur.clicked.connect(self.aktualni)
        self.b_vyber.clicked.connect(self.vyber_prvky)
        self.b_close.clicked.connect(self.accept)
        self.tab.itemChanged.connect(self._zmena_checku)
        self.naplnit()

    # ------------------------------------------------------------ tabulka
    def naplnit(self):
        self.tab.blockSignals(True)
        pocty = pocty_ve_vrstvach(self.page.dok.msp)
        vrstvy = sorted(self.doc.layers, key=lambda ly: ly.dxf.name.lower())
        self.tab.setRowCount(len(vrstvy))
        typy = [lt.dxf.name for lt in self.doc.linetypes]
        for r, ly in enumerate(vrstvy):
            name = ly.dxf.name
            it = QTableWidgetItem(("● " if name == self.page.kresleni.vrstva else "") + name)
            it.setData(Qt.UserRole, name)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.tab.setItem(r, 0, it)
            for c, stav in ((1, ly.is_on()), (2, ly.is_frozen()), (3, ly.is_locked())):
                ch = QTableWidgetItem()
                ch.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                ch.setCheckState(Qt.Checked if stav else Qt.Unchecked)
                self.tab.setItem(r, c, ch)
            sp = QSpinBox()
            sp.setRange(1, 255)
            sp.setValue(abs(ly.dxf.get("color", 7)) or 7)
            sp.valueChanged.connect(lambda v, n=name: self._nastav(n, color=v))
            self.tab.setCellWidget(r, 4, sp)
            cb = QComboBox()
            cb.addItems(typy)
            cb.setCurrentText(ly.dxf.get("linetype", "Continuous"))
            cb.currentTextChanged.connect(lambda t, n=name: self._nastav(n, linetype=t))
            self.tab.setCellWidget(r, 5, cb)
            tw = QComboBox()
            tw.addItems(["výchozí" if t == -3 else f"{t / 100:.2f} mm" for t in TLOUSTKY])
            lw = ly.dxf.get("lineweight", -3)
            tw.setCurrentIndex(TLOUSTKY.index(lw) if lw in TLOUSTKY else 0)
            tw.currentIndexChanged.connect(lambda i, n=name: self._nastav(n, lineweight=TLOUSTKY[i]))
            self.tab.setCellWidget(r, 6, tw)
            pc = QTableWidgetItem(str(pocty.get(name, 0)))
            pc.setFlags(pc.flags() & ~Qt.ItemIsEditable)
            pc.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tab.setItem(r, 7, pc)
        self.tab.resizeColumnsToContents()
        self.tab.blockSignals(False)
        self.info.setText(f"{len(vrstvy)} vrstev, aktuální: {self.page.kresleni.vrstva}. Zamčené vrstvy nejdou "
                          "vybrat ani upravit, vypnuté a zmrazené se nezobrazují.")

    def _jmeno(self, r: int | None = None) -> str | None:
        r = self.tab.currentRow() if r is None else r
        it = self.tab.item(r, 0) if r is not None and r >= 0 else None
        return it.data(Qt.UserRole) if it else None

    def _zmena_checku(self, it: QTableWidgetItem):
        name = self._jmeno(it.row())
        if name is None or it.column() not in (1, 2, 3):
            return
        ly = self.doc.layers.get(name)
        on = it.checkState() == Qt.Checked
        if it.column() == 1:
            if name == self.page.kresleni.vrstva and not on:
                QMessageBox.information(self, "Vrstvy", "Aktuální vrstvu nejde vypnout.")
                self.naplnit()
                return
            ly.on() if on else ly.off()
        elif it.column() == 2:
            if name == self.page.kresleni.vrstva and on:
                QMessageBox.information(self, "Vrstvy", "Aktuální vrstvu nejde zmrazit.")
                self.naplnit()
                return
            ly.freeze() if on else ly.thaw()
        else:
            ly.lock() if on else ly.unlock()
        self._zmeneno()

    def _nastav(self, name: str, **dxf):
        ly = self.doc.layers.get(name)
        for k, v in dxf.items():
            if k == "color":
                v = -v if ly.is_off() else v  # vypnutá vrstva má v DXF zápornou barvu
            ly.dxf.set(k, v)
        self._zmeneno()

    def _zmeneno(self):
        self.zmeneno = True
        self.page.vrstvy_zmeneny()

    # ------------------------------------------------------------ akce
    def nova(self, name: str | None = None) -> str | None:
        if name is None:
            name, ok = QInputDialog.getText(self, "Nová vrstva", "Název vrstvy:")
            if not ok:
                return None
        name = (name or "").strip()
        if not name or any(c in name for c in '<>/\\":;?*|=`'):
            QMessageBox.warning(self, "Vrstvy", "Neplatný název vrstvy.")
            return None
        if name in self.doc.layers:
            QMessageBox.warning(self, "Vrstvy", f"Vrstva {name} už existuje.")
            return None
        self.doc.layers.add(name)
        self._zmeneno()
        self.naplnit()
        return name

    def prejmenuj(self, nove: str | None = None) -> bool:
        stare = self._jmeno()
        if stare is None:
            return False
        if stare in ("0", "Defpoints"):
            QMessageBox.information(self, "Vrstvy", f"Vrstvu {stare} nejde přejmenovat.")
            return False
        if nove is None:
            nove, ok = QInputDialog.getText(self, "Přejmenovat vrstvu", "Nový název:", text=stare)
            if not ok:
                return False
        nove = (nove or "").strip()
        if not nove or nove in self.doc.layers:
            QMessageBox.warning(self, "Vrstvy", "Neplatný nebo už použitý název.")
            return False
        self.doc.layers.get(stare).rename(nove)  # přejmenuje i odkazy v prvcích
        if self.page.kresleni.vrstva == stare:
            self.page.kresleni.vrstva = nove
        self._zmeneno()
        self.naplnit()
        return True

    def smaz(self) -> bool:
        name = self._jmeno()
        if name is None:
            return False
        if name in ("0", "Defpoints") or name == self.page.kresleni.vrstva:
            QMessageBox.information(self, "Vrstvy", "Vrstvu 0, Defpoints ani aktuální vrstvu nejde smazat.")
            return False
        pocet = sum(1 for e in self.doc.entitydb.values()
                    if hasattr(e, "dxf") and e.dxf.hasattr("layer") and e.dxf.get("layer") == name and e.is_alive
                    and e.dxf.owner is not None)
        if pocet:
            QMessageBox.information(self, "Vrstvy", f"Ve vrstvě {name} je {pocet} prvků (i v blocích) – "
                                    "nejdřív je smažte nebo přesuňte.")
            return False
        self.doc.layers.remove(name)
        self._zmeneno()
        self.naplnit()
        return True

    def aktualni(self):
        name = self._jmeno()
        if name is None:
            return
        ly = self.doc.layers.get(name)
        if ly.is_off() or ly.is_frozen():
            ly.on()
            ly.thaw()
            self._zmeneno()
        self.page.kresleni.vrstva = name
        self.page._napln_vrstvy()
        self.naplnit()

    def vyber_prvky(self):
        name = self._jmeno()
        if name is None:
            return
        self.page.vyber = [e for e in self.page.dok.msp if e.dxf.get("layer", "0") == name]
        self.page._zvyrazni()
        self.page.vypis(f"Vybráno {len(self.page.vyber)} prvků vrstvy {name}.")
