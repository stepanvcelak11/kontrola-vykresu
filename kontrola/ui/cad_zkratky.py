"""Okno nastavení klávesových zkratek CAD (funkční klávesy a zkratky příkazového řádku)."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QKeySequenceEdit,
                               QLabel, QPushButton, QTableWidget, QTabWidget, QVBoxLayout, QWidget)

from ..cad import zkratky as Z

KLIC_ZKRATKY = "cad/zkratky"
KLIC_ALIASY = "cad/aliasy"


def nastaveni() -> QSettings:
    return QSettings("KontrolaVykresu", "KontrolaVykresu")


def nactene_zkratky() -> dict[str, str]:
    return Z.nacti_zkratky(nastaveni().value(KLIC_ZKRATKY, None))


def nactene_aliasy() -> dict[str, str]:
    return Z.nacti_aliasy(nastaveni().value(KLIC_ALIASY, None))


def klavesy_aplikace(okno) -> dict[str, str]:
    """Zkratky nabídek hlavního okna (aby se vlastní zkratka CAD s nimi nepřekrývala)."""
    out = {}
    if okno is None:
        return out
    for a in okno.findChildren(QAction):
        k = a.shortcut().toString(QKeySequence.PortableText)
        if k:
            out[Z.normalizuj_klavesu(k)] = a.text().replace("&", "")
    return out


class ZkratkyDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Klávesové zkratky CAD")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        uvod = QLabel("Klávesa spustí libovolný řádek příkazu – nástroj („úsečka“), příkaz s parametrem "
                      "(„zhasni vše kromě 58“, „vyber barva 3“, „prvek budovy“) nebo „předvolba 3“ = třetí druh "
                      "prvku v poli <i>Kreslím</i>. Mezerník ve výkresu ukáže naposledy použité příkazy, "
                      "šipky ↑ ↓ v příkazovém řádku listují historií. Pro levou ruku (jako WASD ve hrách) jsou připravené "
                      "<b>Shift + písmeno</b>: D smaž, Q zpět, E vpřed, W celý, A úsečka, S polylinie, C kopie, "
                      "V posun, R otoč, F rovnoběžka, X ořež, G prodluž, T text, Z předchozí pohled.")
        uvod.setWordWrap(True)
        lay.addWidget(uvod)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        prikazy = sorted(getattr(page, "PRIKAZY", {}).keys()) + [f"předvolba {i}" for i in range(1, 10)]
        self._prikazy = prikazy
        # --- klávesy
        w = QWidget()
        v = QVBoxLayout(w)
        self.tab = QTableWidget(0, 2)
        self.tab.setHorizontalHeaderLabels(["Klávesa", "Příkaz"])
        self.tab.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tab.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tab.verticalHeader().hide()
        v.addWidget(self.tab, 1)
        r = QHBoxLayout()
        b_add = QPushButton("Přidat")
        b_del = QPushButton("Odebrat")
        b_def = QPushButton("Výchozí")
        b_def.setToolTip("Vrátit výchozí funkční klávesy (F2 úsečka, F4 polylinie, Ctrl+1…9 předvolby…)")
        for b in (b_add, b_del, b_def):
            r.addWidget(b)
        r.addStretch(1)
        v.addLayout(r)
        self.konflikt = QLabel()
        self.konflikt.setObjectName("zkratky_konflikt")
        self.konflikt.setWordWrap(True)
        v.addWidget(self.konflikt)
        self.tabs.addTab(w, "Klávesy")
        b_add.clicked.connect(lambda: self.pridej_radek())
        b_del.clicked.connect(lambda: self._odeber(self.tab))
        b_def.clicked.connect(lambda: self.napln(Z.VYCHOZI))
        # --- zkratky příkazového řádku
        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        pop = QLabel("Vlastní zkratky pro příkazový řádek: napíšete zkratku a Enter, spustí se příkaz vpravo "
                     "(i s dalšími slovy za zkratkou).")
        pop.setWordWrap(True)
        v2.addWidget(pop)
        self.tab_al = QTableWidget(0, 2)
        self.tab_al.setHorizontalHeaderLabels(["Zkratka", "Příkaz"])
        self.tab_al.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tab_al.verticalHeader().hide()
        v2.addWidget(self.tab_al, 1)
        r2 = QHBoxLayout()
        b_add2 = QPushButton("Přidat")
        b_del2 = QPushButton("Odebrat")
        r2.addWidget(b_add2)
        r2.addWidget(b_del2)
        r2.addStretch(1)
        v2.addLayout(r2)
        self.tabs.addTab(w2, "Zkratky příkazů")
        b_add2.clicked.connect(lambda: self.pridej_alias())
        b_del2.clicked.connect(lambda: self._odeber(self.tab_al))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        win = getattr(page, "win", None)
        self._obsazene = klavesy_aplikace(win)
        self.napln(nactene_zkratky())
        for k, p in sorted(nactene_aliasy().items()):
            self.pridej_alias(k, p)

    # ------------------------------------------------------------ tabulky
    def _kombo(self, text: str) -> QComboBox:
        c = QComboBox()
        c.setEditable(True)
        c.addItems(self._prikazy)
        c.setCurrentText(text)
        c.currentTextChanged.connect(lambda _t: self._zkontroluj())
        return c

    def napln(self, mapa: dict[str, str]) -> None:
        self.tab.setRowCount(0)
        for k, p in sorted(mapa.items(), key=lambda kv: (len(kv[0]), kv[0])):
            self.pridej_radek(k, p)
        self._zkontroluj()

    def pridej_radek(self, klavesa: str = "", prikaz: str = "") -> int:
        i = self.tab.rowCount()
        self.tab.insertRow(i)
        e = QKeySequenceEdit(QKeySequence(klavesa))
        if hasattr(e, "setMaximumSequenceLength"):
            e.setMaximumSequenceLength(1)
        e.keySequenceChanged.connect(lambda _s: self._zkontroluj())
        self.tab.setCellWidget(i, 0, e)
        self.tab.setCellWidget(i, 1, self._kombo(prikaz))
        return i

    def pridej_alias(self, zkratka: str = "", prikaz: str = "") -> int:
        from PySide6.QtWidgets import QLineEdit
        i = self.tab_al.rowCount()
        self.tab_al.insertRow(i)
        self.tab_al.setCellWidget(i, 0, QLineEdit(zkratka))
        self.tab_al.setCellWidget(i, 1, self._kombo(prikaz))
        return i

    def _odeber(self, tab: QTableWidget) -> None:
        rows = sorted({ix.row() for ix in tab.selectedIndexes()} or {tab.currentRow()}, reverse=True)
        for r in rows:
            if r >= 0:
                tab.removeRow(r)
        self._zkontroluj()

    # ------------------------------------------------------------ hodnoty
    def zkratky(self) -> dict[str, str]:
        out = {}
        for i in range(self.tab.rowCount()):
            k = self.tab.cellWidget(i, 0).keySequence().toString(QKeySequence.PortableText)
            p = self.tab.cellWidget(i, 1).currentText().strip()
            k = Z.normalizuj_klavesu(k)
            if k and p:
                out[k] = p
        return out

    def aliasy(self) -> dict[str, str]:
        out = {}
        for i in range(self.tab_al.rowCount()):
            k = self.tab_al.cellWidget(i, 0).text().strip().lower()
            p = self.tab_al.cellWidget(i, 1).currentText().strip()
            if k and p and k != p.lower():
                out[k] = p
        return out

    def _zkontroluj(self) -> list[str]:
        vidano: dict[str, int] = {}
        for i in range(self.tab.rowCount()):
            k = Z.normalizuj_klavesu(self.tab.cellWidget(i, 0).keySequence().toString(QKeySequence.PortableText))
            if k:
                vidano[k] = vidano.get(k, 0) + 1
        chyby = [f"{k}: použito {n}×" for k, n in vidano.items() if n > 1]
        chyby += Z.konflikty(self.zkratky(), self._obsazene)
        self.konflikt.setText(("⚠ " + "; ".join(chyby)) if chyby else "Bez kolizí.")
        return chyby

    def accept(self):  # noqa: D401
        s = nastaveni()
        s.setValue(KLIC_ZKRATKY, Z.uloz(self.zkratky()))
        s.setValue(KLIC_ALIASY, Z.uloz(self.aliasy()))
        if hasattr(self.page, "pouzij_zkratky"):
            self.page.pouzij_zkratky()
        super().accept()
