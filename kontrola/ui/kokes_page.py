"""Stránka Kokeš – práce jako v geodetickém systému KOKEŠ (GEPRO): seznam souřadnic s čísly bodů KN
(k.ú., ZPMZ, pořadové číslo) a kódy kvality, kreslící klíče ze Směrnice, tabulky Kokeše (barvy, čáry,
texty, fonty) podle Zadání Kokeš, výkres a jeho kontrola, katastr a geometrický plán.

Seznam souřadnic je společný se stránkou Výpočty (stejné body, stejné Zpět), výkres se kreslí v CAD
s kreslícími klíči jako aktivním prvkem a kontroluje se v režimu Kokeš.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from .. import kokes as K
from .flow import RadekTlacitek, skupina


class KokesPage(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        nadpis = QLabel("<b>KOKEŠ</b> – seznam souřadnic s čísly bodů KN, kreslící klíče, tabulky ze Směrnice, "
                        "výkres a katastr. Body jsou společné se stránkou Výpočty, výkres se kreslí v CAD.")
        nadpis.setWordWrap(True)
        nadpis.setObjectName("stranka_info")
        lay.addWidget(nadpis)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self._tab_ss()
        self._tab_klice()
        self._tab_tabulky()
        self._tab_katastr()
        self.tabs.currentChanged.connect(lambda _i: self.obnov())

    # ------------------------------------------------------------ seznam souřadnic
    def _tab_ss(self):
        w = QWidget()
        v = QVBoxLayout(w)
        r = RadekTlacitek()
        self.ku = QLineEdit()
        self.ku.setPlaceholderText("např. 610844")
        self.ku.setMaximumWidth(110)
        self.ku.setToolTip("Číslo katastrálního území (6 číslic) – nepovinné")
        self.zpmz = QSpinBox()
        self.zpmz.setRange(1, 99999)
        self.zpmz.setToolTip("Číslo záznamu podrobného měření změn")
        r.addWidget(skupina(QLabel("k.ú.:"), self.ku))
        r.addWidget(skupina(QLabel("ZPMZ:"), self.zpmz))
        self.b_kn = QPushButton("Krátká čísla → čísla KN")
        self.b_kn.setToolTip("Body s číslem 1–9999 dostanou úplné číslo KN (k.ú. + ZPMZ + pořadové číslo), "
                             "jako v seznamu souřadnic Kokeše; vybrané body, nebo všechny")
        self.kvalita = QSpinBox()
        self.kvalita.setRange(1, 8)
        self.kvalita.setValue(3)
        self.b_kk = QPushButton("Kód kvality vybraným")
        self.b_zpet = QPushButton("Zpět")
        self.b_export = QPushButton("Uložit seznam (text)…")
        self.b_export.setToolTip("Textový seznam souřadnic: číslo, Y, X, Z, kód kvality – do Kokeše načtete "
                                 "importem textového seznamu")
        self.b_import = QPushButton("Načíst seznam…")
        self.b_import.setToolTip("Textový export seznamu z Kokeše (číslo Y X Z kk), z Gromy nebo z přístroje")
        for b in (self.b_kn, skupina(QLabel("Kód kvality:"), self.kvalita), self.b_kk, self.b_zpet,
                  self.b_import, self.b_export):
            r.addWidget(b)
        v.addLayout(r)
        self.tab = QTableWidget(0, 7)
        from .theme import prazdny_stav
        prazdny_stav(self.tab, 'Seznam souřadnic je prázdný.\nNačtěte seznam (Načíst seznam…) nebo body spočítejte na stránce Výpočty – seznam je společný.')
        self.tab.setHorizontalHeaderLabels(["Číslo bodu", "ZPMZ-číslo", "Y", "X", "Z", "KK", "Kód"])
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.verticalHeader().hide()
        self.tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tab.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tab, 1)
        self.stav = QLabel()
        v.addWidget(self.stav)
        self.tabs.addTab(w, "Seznam souřadnic")
        self.b_kn.clicked.connect(lambda: self.na_kn())
        self.b_kk.clicked.connect(lambda: self.nastav_kvalitu())
        self.b_zpet.clicked.connect(lambda: self.zpet())
        self.b_export.clicked.connect(lambda: self.export_ss())
        self.b_import.clicked.connect(lambda: self.import_ss())

    def _seznam(self):
        v = getattr(self.win, "vypocty", None)
        return v.seznam if v is not None else None

    def _po_zmene(self):
        v = getattr(self.win, "vypocty", None)
        if v is not None:
            v.model.refresh()
            v._after_change()
        self.obnov()

    def vybrane(self) -> list[str]:
        rows = sorted({i.row() for i in self.tab.selectedIndexes()})
        return [self.tab.item(r, 0).text() for r in rows if self.tab.item(r, 0) is not None]

    def obnov(self):
        s = self._seznam()
        body = list(s.body) if s is not None else []
        self.tab.setRowCount(len(body))
        for i, b in enumerate(body):
            for c, t in enumerate((b.cislo, K.zkracene(b.cislo), f"{b.y:.2f}", f"{b.x:.2f}",
                                   "" if b.z is None else f"{b.z:.2f}", "" if b.kvalita is None else str(b.kvalita),
                                   b.kod or "")):
                it = QTableWidgetItem(t)
                if c in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tab.setItem(i, c, it)
        bez = sum(1 for b in body if b.kvalita is None)
        self.stav.setText(f"{len(body)} bodů" + (f", {bez} bez kódu kvality" if bez else ""))
        self._obnov_klice()
        self._obnov_tabulky()

    def na_kn(self) -> int:
        s = self._seznam()
        if s is None:
            return 0
        try:
            n = K.na_cisla_kn(s, self.ku.text().strip() or None, self.zpmz.value(), self.vybrane() or None)
        except ValueError as e:
            QMessageBox.warning(self, "Kokeš", str(e))
            return 0
        self._po_zmene()
        self.stav.setText(f"Převedeno {n} čísel bodů na čísla KN (ZPMZ {self.zpmz.value()}).")
        return n

    def nastav_kvalitu(self) -> int:
        s = self._seznam()
        cisla = self.vybrane()
        if s is None or not cisla:
            self.stav.setText("Vyberte body v tabulce.")
            return 0
        n = s.hromadne(cisla, kvalita=self.kvalita.value())
        self._po_zmene()
        return n

    def zpet(self):
        s = self._seznam()
        if s is not None and s.zpet():
            self._po_zmene()

    def export_ss(self, path: str | None = None):
        s = self._seznam()
        if s is None or not s.body:
            self.stav.setText("Seznam souřadnic je prázdný.")
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Seznam souřadnic pro Kokeš", "seznam.txt",
                                                  "Text (*.txt)")
            if not path:
                return None
        Path(path).write_text(K.seznam_text(s.body), encoding="cp1250", errors="replace")
        self.stav.setText(f"Uloženo {len(s.body)} bodů: {path}")
        return Path(path)

    def import_ss(self, path: str | None = None):
        v = getattr(self.win, "vypocty", None)
        if v is None:
            return None
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Seznam souřadnic", "", "Seznamy (*.txt *.csv *.ss);;Vše (*)")
            if not path:
                return None
        if Path(path).suffix.lower() == ".ss":
            QMessageBox.information(self, "Kokeš", "Soubor .ss je binární seznam Kokeše. V Kokeši ho uložte jako "
                                                   "textový seznam (číslo Y X Z kód kvality) a načtěte ten.")
            return None
        r = v.import_dialog(path)
        self.obnov()
        return r

    # ------------------------------------------------------------ kreslící klíče
    def _tab_klice(self):
        w = QWidget()
        v = QVBoxLayout(w)
        info = QLabel("Kreslící klíče ze sloupce KK Směrnice. Dvojklik na klíč = kreslit tímto prvkem v CAD "
                      "(hladina, barva, styl a tloušťka se nastaví samy, jako aktivní klíč v Kokeši).")
        info.setWordWrap(True)
        info.setObjectName("stranka_info")
        v.addWidget(info)
        r = RadekTlacitek()
        self.b_rezim = QPushButton("Kontrolovat jako výkres z Kokeše")
        self.b_rezim.setCheckable(True)
        self.b_rezim.setToolTip("Pravidla v režimu Kokeš: kreslící klíče, barva 100 = 0, styl −13 = 4, texty 1xx")
        self.b_novy = QPushButton("Nový výkres podle zadání")
        self.b_kontrola = QPushButton("Zkontrolovat výkres…")
        self.b_kontrola.setToolTip("Výkres z Kokeše exportovaný do DXF (nebo DGN) – kontrola podle Směrnice")
        for b in (self.b_rezim, self.b_novy, self.b_kontrola):
            r.addWidget(b)
        v.addLayout(r)
        self.klice = QTableWidget(0, 6)
        from .theme import prazdny_stav
        prazdny_stav(self.klice, 'Zatím žádné kreslící klíče.\nKlíče se vezmou ze sloupce KK tabulky atributů (Zadání → Tabulka atributů).')
        self.klice.setHorizontalHeaderLabels(["KK", "Prvek", "Hladina", "Barva", "Styl", "Tloušťka"])
        self.klice.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.klice.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.klice.verticalHeader().hide()
        self.klice.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        v.addWidget(self.klice, 1)
        self.tabs.addTab(w, "Kreslící klíče")
        self.b_rezim.toggled.connect(self.nastav_rezim)
        self.b_novy.clicked.connect(lambda: self.novy_vykres())
        self.b_kontrola.clicked.connect(lambda: self.win.open_dialog())
        self.klice.cellDoubleClicked.connect(lambda r, _c: self.kreslit_klicem(r))

    def _pravidla(self):
        pr = getattr(self.win, "project", None)
        return pr.rules if pr is not None else None

    def _obnov_klice(self):
        rs = self._pravidla()
        self.b_rezim.blockSignals(True)
        self.b_rezim.setChecked(bool(rs is not None and rs.program == "kokes"))
        self.b_rezim.blockSignals(False)
        cary = K.tabulky(rs)["cary"] if rs is not None and rs.pravidla else []
        self.klice.setRowCount(len(cary))
        for i, radek in enumerate(cary):
            for c, t in enumerate(radek):
                self.klice.setItem(i, c, QTableWidgetItem(str(t)))

    def nastav_rezim(self, on: bool):
        rs = self._pravidla()
        if rs is None:
            return
        prog = "kokes" if on else "microstation"
        z = getattr(self.win, "zadani", None)
        ed = getattr(z, "rules_editor", None)
        if ed is not None and ed.rules is rs:  # přes editor pravidel – uloží se do projektu jako ruční změna
            ed.program.setCurrentIndex(max(0, ed.program.findData(prog)))
        else:
            rs.program = prog
        rs.program = prog

    def kreslit_klicem(self, radek: int) -> bool:
        it = self.klice.item(radek, 1)
        cad = getattr(self.win, "cad", None)
        if it is None or cad is None:
            return False
        if cad.dok is None:
            cad.novy_podle_zadani(vzory=None) if cad._pravidla() is not None else cad.novy()
        cad.obnov_predvolby()
        ok = cad.vyber_predvolbu(it.text())
        self.win.show_page("cad")
        return ok

    def novy_vykres(self):
        cad = getattr(self.win, "cad", None)
        if cad is None:
            return None
        self.win.show_page("cad")
        return cad.novy_podle_zadani()

    # ------------------------------------------------------------ tabulky ze Směrnice
    def _tab_tabulky(self):
        w = QWidget()
        v = QVBoxLayout(w)
        r = RadekTlacitek()
        self.b_tab = QPushButton("Uložit tabulky (HTML)…")
        self.b_tab.setToolTip("Přehled tabulky barev, čar, textových klíčů a fontů k vytištění – podle něj "
                              "upravíte tabulky v Kokeši (Zadání Kokeš)")
        r.addWidget(self.b_tab)
        v.addLayout(r)
        self.html = QTextBrowser()
        v.addWidget(self.html, 1)
        self.tabs.addTab(w, "Tabulky ze Směrnice")
        self.b_tab.clicked.connect(lambda: self.uloz_tabulky())

    def _obnov_tabulky(self):
        rs = self._pravidla()
        if rs is None or not rs.pravidla:
            self.html.setHtml("<p>Nahrajte Směrnici v Zadání – z ní se tabulky pro Kokeš sestaví samy.</p>")
            return
        self.html.setHtml(K.tabulky_html(rs))

    def uloz_tabulky(self, path: str | None = None):
        rs = self._pravidla()
        if rs is None or not rs.pravidla:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Tabulky pro Kokeš", "tabulky_kokes.html", "HTML (*.html)")
            if not path:
                return None
        Path(path).write_text(K.tabulky_html(rs), encoding="utf-8")
        return Path(path)

    # ------------------------------------------------------------ katastr a GP
    def _tab_katastr(self):
        w = QWidget()
        v = QVBoxLayout(w)
        info = QLabel("Katastr a geometrický plán: data KN (VFK) jako podklad, výměry a výkaz výměr GP, kontrola "
                      "dvou určení bodu (kód kvality), převod souřadnic.")
        info.setWordWrap(True)
        info.setObjectName("stranka_info")
        v.addWidget(info)
        from PySide6.QtWidgets import QGridLayout
        g = QGridLayout()
        g.setSpacing(10)
        # dlaždice: název funkce + krátký popis, co dělá (jako Nástroje na Úvodu)
        popisy = {
            "Otevřít data KN (VFK)…": "Výměnný formát katastru jako podklad pod výkres (parcely, body, budovy).",
            "Výkaz výměr GP": "Výměry dílů a parcel geometrického plánu a výkaz pro GP.",
            "Výměry parcel dávkou": "Výměry všech parcel ze seznamu souřadnic najednou.",
            "Oddělení parcely": "Rozdělení parcely na zadanou výměru (posun dělicí čáry).",
            "Kontrola dvou určení": "Porovnání dvou určení bodu proti meznímu rozdílu podle kódu kvality.",
            "Výměra a obvod": "Výměra a obvod plochy z čísel bodů.",
            "Převod S-JTSK ↔ WGS84": "Převod souřadnic mezi S-JTSK a zeměpisnými souřadnicemi.",
        }
        self._ulohy_tlacitka = []
        for k, (nazev, popis) in enumerate(popisy.items()):
            from .theme import dlazdice
            b = dlazdice(nazev, popis)
            if k == 0:
                self.b_vfk = b
            else:
                b.clicked.connect(lambda _c=False, n=nazev: self.otevri_ulohu(n))
                self._ulohy_tlacitka.append(b)
            g.addWidget(b, k // 3, k % 3)
        for c in range(3):
            g.setColumnStretch(c, 1)
        v.addSpacing(6)
        v.addLayout(g)
        v.addStretch(1)
        self.tabs.addTab(w, "Katastr a GP")
        self.b_vfk.clicked.connect(lambda: self.otevri_vfk())

    def otevri_ulohu(self, nazev: str) -> bool:
        v = getattr(self.win, "vypocty", None)
        if v is None:
            return False
        from ..geodezie.ulohy import ULOHY
        i = next((k for k, u in enumerate(ULOHY) if u[0] == nazev), None)
        if i is None:
            return False
        self.win.show_page("vypocty")
        v.tabs.setCurrentWidget(v.ulohy)
        v.ulohy.hledat.clear()
        v.ulohy.lst.setCurrentRow(i)
        return True

    def otevri_vfk(self, path: str | None = None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Data katastru", "", "VFK (*.vfk)")
            if not path:
                return None
        self.win.load_drawing_file(Path(path))
        self.win.show_page("vykres")
        return path

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.obnov()
