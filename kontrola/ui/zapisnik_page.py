"""Záložka Zápisník ve Výpočtech (jako zápisník Gromy): stanoviska a záměry, úpravy, uložení .zap,
výpočet polární metody dávkou proti seznamu souřadnic projektu a vypočtené body do seznamu."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..geodezie import zapisnik as Z
from ..vypocet import Obs, Station

SL = ("Bod", "Šikmá délka [m]", "Výška cíle [m]", "Hz [g]", "Z [g]", "Část")


class ZapisnikPanel(QWidget):
    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.stanoviska: list[Station] = []
        self.soubor: Path | None = None
        self.vysledek = None
        self._plneni = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        bar = QHBoxLayout()
        self.b_nacist = QPushButton("Načíst…")
        self.b_nacist.setToolTip("Zápisník Gromy (.zap) nebo Leica GSI")
        self.b_ulozit = QPushButton("Uložit .zap…")
        self.b_st = QPushButton("+ Stanovisko")
        self.b_zam = QPushButton("+ Záměra")
        self.b_smaz = QPushButton("Smazat")
        self.b_vyp = QPushButton("Vypočítat (polární metoda)")
        self.b_vyp.setProperty("primarni", True)
        self.b_vyr = QPushButton("Vyrovnat síť (MNČ)…")
        self.b_vyr.setToolTip("Vyrovnání sítě ze všech směrů a délek zápisníku; pevné body ze seznamu souřadnic")
        self.b_do = QPushButton("Do seznamu bodů")
        self.b_do.setEnabled(False)
        for b in (self.b_nacist, self.b_ulozit, self.b_st, self.b_zam, self.b_smaz, self.b_vyp, self.b_vyr, self.b_do):
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        sp = QSplitter()
        levy = QWidget()
        ll = QVBoxLayout(levy)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Stanoviska:"))
        self.seznam_st = QListWidget()
        ll.addWidget(self.seznam_st, 1)
        row = QHBoxLayout()
        self.st_cislo = QLineEdit()
        self.st_cislo.setPlaceholderText("číslo stanoviska")
        self.st_vp = QDoubleSpinBox()
        self.st_vp.setRange(0, 5)
        self.st_vp.setDecimals(3)
        self.st_vp.setSuffix(" m")
        self.st_vp.setToolTip("Výška přístroje")
        row.addWidget(self.st_cislo)
        row.addWidget(self.st_vp)
        ll.addLayout(row)
        sp.addWidget(levy)
        pravy = QSplitter(Qt.Vertical)
        self.tab = QTableWidget(0, len(SL))
        self.tab.setHorizontalHeaderLabels(SL)
        self.tab.verticalHeader().setVisible(False)
        pravy.addWidget(self.tab)
        self.vystup = QTextBrowser()
        self.vystup.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace;")
        pravy.addWidget(self.vystup)
        sp.addWidget(pravy)
        sp.setStretchFactor(1, 1)
        lay.addWidget(sp, 1)
        self.info = QLabel("Načtěte zápisník nebo založte stanovisko. Dané body (orientace) se berou ze seznamu "
                           "souřadnic projektu.")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.b_nacist.clicked.connect(lambda: self.nacist())
        self.b_ulozit.clicked.connect(lambda: self.ulozit())
        self.b_st.clicked.connect(self.pridej_stanovisko)
        self.b_zam.clicked.connect(lambda: self.pridej_zameru())
        self.b_smaz.clicked.connect(self.smaz)
        self.b_vyp.clicked.connect(self.vypocitej)
        self.b_do.clicked.connect(self.do_seznamu)
        self.b_vyr.clicked.connect(lambda: self.vyrovnat())
        self.seznam_st.currentRowChanged.connect(self._zobraz)
        self.st_cislo.editingFinished.connect(self._st_zmena)
        self.st_vp.valueChanged.connect(self._st_zmena)
        self.tab.itemChanged.connect(self._zmena_zamery)

    # ------------------------------------------------------------ data ↔ zobrazení
    def _dane(self) -> set[str]:
        return {b.cislo for b in self.page.seznam.body}

    def nastav(self, stanoviska: list[Station]):
        self.stanoviska = stanoviska
        self._obnov_seznam()
        if stanoviska:
            self.seznam_st.setCurrentRow(0)

    def _obnov_seznam(self):
        i = self.seznam_st.currentRow()
        self.seznam_st.blockSignals(True)
        self.seznam_st.clear()
        for st in self.stanoviska:
            self.seznam_st.addItem(f"{st.bod}  (vp {st.vp:.3f}, {len(st.orient)} orient., {len(st.detail)} podr.)")
        self.seznam_st.blockSignals(False)
        if 0 <= i < len(self.stanoviska):
            self.seznam_st.setCurrentRow(i)

    def _st(self) -> Station | None:
        i = self.seznam_st.currentRow()
        return self.stanoviska[i] if 0 <= i < len(self.stanoviska) else None

    def _zobraz(self, _i=None):
        st = self._st()
        self._plneni = True
        self.tab.setRowCount(0)
        if st is not None:
            self.st_cislo.setText(st.bod)
            self.st_vp.setValue(st.vp)
            for cast, obs in (("orientace", st.orient), ("podrobný", st.detail)):
                for o in obs:
                    self._radek(o, cast)
        self._plneni = False

    def _radek(self, o: Obs, cast: str):
        r = self.tab.rowCount()
        self.tab.insertRow(r)
        for c, v in enumerate((o.bod, f"{o.sd:.3f}", f"{o.vc:.3f}", f"{o.hz:.4f}", f"{o.z:.4f}")):
            self.tab.setItem(r, c, QTableWidgetItem(v))
        cb = QComboBox()
        cb.addItems(["orientace", "podrobný"])
        cb.setCurrentText(cast)
        cb.currentTextChanged.connect(lambda _t: self._zmena_zamery())
        self.tab.setCellWidget(r, 5, cb)

    def _z_tabulky(self) -> tuple[list[Obs], list[Obs]] | None:
        orient, detail = [], []
        for r in range(self.tab.rowCount()):
            try:
                bod = self.tab.item(r, 0).text().strip()
                vals = [float(self.tab.item(r, c).text().replace(",", ".")) for c in range(1, 5)]
            except (ValueError, AttributeError):
                self.info.setText(f"⚠ Řádek {r + 1}: zadejte čísla (délka, výška cíle, Hz, Z).")
                return None
            if not bod:
                self.info.setText(f"⚠ Řádek {r + 1}: chybí číslo bodu.")
                return None
            o = Obs(bod, *vals)
            (orient if self.tab.cellWidget(r, 5).currentText() == "orientace" else detail).append(o)
        return orient, detail

    def _zmena_zamery(self, *_a):
        if self._plneni:
            return
        st = self._st()
        z = self._z_tabulky()
        if st is None or z is None:
            return
        st.orient, st.detail = z
        self.info.setText("")
        self._obnov_seznam()

    def _st_zmena(self, *_a):
        st = self._st()
        if st is None or self._plneni:
            return
        st.bod = self.st_cislo.text().strip() or st.bod
        st.vp = self.st_vp.value()
        self._obnov_seznam()

    # ------------------------------------------------------------ akce
    def nacist(self, cesta: str | None = None) -> bool:
        if cesta is None:
            cesta, _ = QFileDialog.getOpenFileName(self, "Načíst zápisník", "", "Zápisník (*.zap *.gsi *.txt)")
            if not cesta:
                return False
        try:
            st = Z.nacti(cesta, self._dane())
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Zápisník", f"Zápisník nejde načíst: {e}")
            return False
        if not st:
            QMessageBox.warning(self, "Zápisník", "V souboru nejsou žádná stanoviska.")
            return False
        self.soubor = Path(cesta)
        self.nastav(st)
        n = sum(len(s.orient) + len(s.detail) for s in st)
        self.info.setText(f"Načteno {len(st)} stanovisek, {n} záměr ({self.soubor.name}).")
        return True

    def ulozit(self, cesta: str | None = None):
        if not self.stanoviska:
            return None
        if cesta is None:
            cesta, _ = QFileDialog.getSaveFileName(self, "Uložit zápisník", str(self.soubor or "zapisnik.zap"),
                                                   "Zápisník Gromy (*.zap)")
            if not cesta:
                return None
        Path(cesta).write_text(Z.zapis_zap(self.stanoviska), encoding="cp1250")
        self.info.setText(f"Zápisník uložen: {cesta}")
        return Path(cesta)

    def pridej_stanovisko(self):
        self.stanoviska.append(Station(f"{len(self.stanoviska) + 1}", 1.5))
        self._obnov_seznam()
        self.seznam_st.setCurrentRow(len(self.stanoviska) - 1)

    def pridej_zameru(self, bod: str = "", sd: float = 0.0, vc: float = 0.0, hz: float = 0.0, z: float = 100.0,
                      cast: str = "podrobný"):
        st = self._st()
        if st is None:
            self.info.setText("Nejdřív založte nebo vyberte stanovisko.")
            return
        (st.orient if cast == "orientace" else st.detail).append(Obs(bod or "?", sd, vc, hz, z))
        self._zobraz()
        self._obnov_seznam()

    def smaz(self):
        rows = sorted({i.row() for i in self.tab.selectedIndexes()}, reverse=True)
        if rows:
            for r in rows:
                self.tab.removeRow(r)
            self._zmena_zamery()
        elif self._st() is not None:
            del self.stanoviska[self.seznam_st.currentRow()]
            self._obnov_seznam()
            self._zobraz()

    def vypocitej(self):
        from ..checks.seznam import ListPoint
        from ..geodezie.protokol import protokol_polarni
        from ..vypocet import compute
        if not self.stanoviska:
            self.info.setText("Zápisník je prázdný.")
            return None
        upoz = Z.zkontroluj(self.stanoviska)
        dane = [ListPoint(b.cislo, b.y, b.x, b.z) for b in self.page.seznam.body]
        if not dane:
            self.info.setText("⚠ V seznamu souřadnic nejsou dané body – importujte je na záložce Seznam souřadnic.")
            return None
        st = Z.pro_vypocet(self.stanoviska)
        try:
            self.vysledek = compute(st, dane)
        except Exception as e:  # noqa: BLE001 – výpočet nesmí shodit aplikaci
            self.info.setText(f"⚠ Výpočet se nepovedl: {e}")
            return None
        text = protokol_polarni(self.vysledek, st, dane, soubor_mereni=self.soubor.name if self.soubor else "")
        self.vystup.setPlainText(text)
        self.page.protokol_append(text.splitlines())
        nove = [b for b in self.vysledek.body if not b.kontrolni]
        self.b_do.setEnabled(bool(nove))
        self.info.setText(f"Vypočteno {len(nove)} bodů." + (" Upozornění: " + "; ".join(upoz[:3]) if upoz else ""))
        return self.vysledek

    def vyrovnat(self, sigma_smer_cc: float | None = None, sigma_delka_mm: float | None = None,
                 sigma_ppm: float | None = None):
        """Vyrovnání sítě MNČ ze zápisníku: směry a vodorovné délky (redukované do zobrazení)."""
        from PySide6.QtWidgets import QInputDialog
        if not self.stanoviska:
            self.info.setText("Zápisník je prázdný.")
            return None
        if sigma_smer_cc is None:
            t, ok = QInputDialog.getText(self, "Vyrovnání sítě", "Apriorní střední chyby: směr [cc], délka [mm], "
                                         "délka [ppm]:", text="10 3 2")
            if not ok:
                return None
            try:
                sigma_smer_cc, sigma_delka_mm, sigma_ppm = (float(x.replace(",", ".")) for x in t.split()[:3])
            except ValueError:
                self.info.setText("⚠ Zadejte tři čísla, např. 10 3 2.")
                return None
        try:
            v, text = Z.vyrovnani_site(self.stanoviska, self.page.seznam.body, sigma_smer_cc, sigma_delka_mm,
                                       sigma_ppm)
        except ValueError as e:
            self.info.setText(f"⚠ {e}")
            return None
        self.vystup.setPlainText(text)
        self.page.protokol_append(text.splitlines())
        self.vyrovnani = v
        self.info.setText(f"Vyrovnáno {len(v.souradnice)} bodů, σ0 = {v.sigma0:.2f}, nadbytečných měření "
                          f"{v.redundance}. Body určené jen jednou (rajóny) spočítá polární metoda.")
        return v

    def do_seznamu(self) -> int:
        from ..geodezie.body import Bod
        if self.vysledek is None:
            return 0
        nove = [Bod(b.bod, b.y, b.x, b.z, poznamka=f"polární metoda ze st. {b.stanovisko}")
                for b in self.vysledek.body if not b.kontrolni]
        n, konf = self.page.seznam.pridej(nove, "Zápisník: vypočtené body")
        self.page._after_change()
        self.info.setText(f"Přidáno {n} bodů do seznamu." + (f" {len(konf)} čísel už v seznamu bylo a ponechala se "
                                                              "původní." if konf else ""))
        return n
