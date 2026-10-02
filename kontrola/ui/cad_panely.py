"""Panely CAD jako v MicroStationu: paleta nástrojů s ikonami, výběr barvy z tabulky 0–255, hladiny a vlastnosti."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from .cad_ikony import ikona

# skupiny nástrojů palety (pořadí jako v MicroStationu: kreslení, úpravy, manipulace, výběr, měření…)
SKUPINY = [
    ("Kreslení", ["úsečka", "polylinie", "obdélník", "mnohoúhelník", "kružnice", "oblouk", "elipsa", "křivka",
                  "bod", "text", "popisek", "šrafa", "kóta", "kóta úhlu", "kóta poloměru", "vlož"]),
    ("Úpravy", ["posun", "kopie", "otoč", "měřítko", "zrcadli", "pole", "rovnoběžka", "ořež", "prodluž", "zaobli",
                "zkos", "rozděl", "smaž část", "natáhni", "spoj", "rozpoj", "uprav text", "smaž"]),
    ("Výběr", ["vše", "ohrada", "podobné", "vyber", "skupina"]),
    ("Měření", ["vzdálenost", "délka", "výměra", "info"]),
    ("Geodézie", ["body", "kódy", "kódovník", "vrstevnice", "profil", "mračno", "síť", "transformace", "georeference", "oměrné míry", "převod atributů"]),
    ("Zobrazení", ["celý", "přiblížit", "předchozí pohled", "vrstvy"]),
]
NAZVY = {"vlož": "Vložit buňku", "body": "Body ze seznamu", "vrstvy": "Správce hladin", "celý": "Celý výkres",
         "info": "Informace o prvku", "vše": "Vybrat vše", "vyber": "Výběr podle atributů",
         "podobné": "Vybrat podobné", "ohrada": "Výběr ohradou", "skupina": "Skupina prvků",
         "délka": "Délka výběru", "výměra": "Výměra prvku", "síť": "Souřadnicová síť", "vrstevnice": "Vrstevnice a TIN", "profil": "Podélný profil", "kódy": "Kresba z kódů", "kódovník": "Kódovník", "georeference": "Georeference rastru", "mračno": "Mračno bodů"}


class PaletaNastroju(QScrollArea):
    """Svislá paleta nástrojů s ikonami ve skupinách (tooltip = název a popis)."""
    nastroj = Signal(str)

    def __init__(self, popisy: dict[str, str], barva="#D1D5DB", zvyrazneni="#60A5FA", sloupcu: int = 3,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("cad_paleta")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        self.tlacitka: dict[str, QToolButton] = {}
        for nazev, prikazy in SKUPINY:
            lbl = QLabel(nazev)
            lbl.setObjectName("cad_paleta_nadpis")
            lay.addWidget(lbl)
            g = QGridLayout()
            g.setSpacing(2)
            for i, cmd in enumerate(prikazy):
                b = QToolButton()
                b.setIcon(ikona(cmd, barva, zvyrazneni))
                b.setIconSize(QSize(24, 24))
                b.setFixedSize(QSize(36, 34))
                b.setAutoRaise(True)
                b.setCheckable(True)
                titul = NAZVY.get(cmd, cmd[:1].upper() + cmd[1:])
                b.setToolTip(f"<b>{titul}</b><br>{popisy.get(cmd, '')}<br><i>příkaz: {cmd}</i>")
                b.clicked.connect(lambda _=False, c=cmd: self.nastroj.emit(c))
                g.addWidget(b, i // sloupcu, i % sloupcu)
                self.tlacitka[cmd] = b
            lay.addLayout(g)
        lay.addStretch(1)
        self.setWidget(w)
        self.setFixedWidth(sloupcu * 38 + 22)

    def oznac(self, prikaz: str | None) -> None:
        """Zvýrazní běžící nástroj (jako stisknutá ikona v MicroStationu)."""
        for c, b in self.tlacitka.items():
            b.setChecked(c == prikaz)


def vzorek(rgb, velikost: int = 14) -> QIcon:
    pm = QPixmap(velikost, velikost)
    pm.fill(QColor(*rgb) if rgb is not None else QColor(0, 0, 0, 0))
    return QIcon(pm)


class BarvaDialog(QDialog):
    """Tabulka barev MicroStationu 0–255 (jako výběr barvy v liště Atributy) + „dle hladiny“."""

    def __init__(self, tabulka: dict[int, tuple[int, int, int]], aktualni: int | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Barva (tabulka barev MicroStationu)")
        self.vysledek: int | None = None  # 0–255, 256 = dle hladiny
        lay = QVBoxLayout(self)
        g = QGridLayout()
        g.setSpacing(1)
        for i in range(256):
            rgb = tabulka.get(i, (128, 128, 128))
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setToolTip(f"Barva {i}  (RGB {rgb[0]}, {rgb[1]}, {rgb[2]})")
            ram = "2px solid #FFFFFF" if i == aktualni else "1px solid #202020"
            b.setStyleSheet(f"background: rgb{tuple(rgb)}; border: {ram}; padding: 0; min-width: 0;")
            b.clicked.connect(lambda _=False, c=i: self._vyber(c))
            g.addWidget(b, i // 16, i % 16)
        lay.addLayout(g)
        b = QPushButton("Dle hladiny (ByLevel)")
        b.clicked.connect(lambda: self._vyber(256))
        lay.addWidget(b)

    def _vyber(self, c: int):
        self.vysledek = c
        self.accept()


class PanelHladin(QListWidget):
    """Seznam hladin: zaškrtnutí = zobrazení, barevný vzorek, počet prvků; dvojklik = aktivní hladina."""
    zobrazeni = Signal(str, bool)
    aktivni = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cad_hladiny")
        self._plneni = False
        self.itemChanged.connect(self._zmena)
        self.itemDoubleClicked.connect(lambda it: self.aktivni.emit(it.data(Qt.UserRole)))
        self.setToolTip("Zaškrtnutí = hladina zobrazena · dvojklik = aktivní hladina pro nové prvky")

    def napln(self, doc, msp, aktivni: str, barva_hladiny) -> None:
        self._plneni = True
        self.clear()
        pocty = Counter(e.dxf.get("layer", "0") for e in msp) if msp is not None else Counter()
        if doc is not None:
            for ly in sorted(doc.layers, key=lambda x: _klic(x.dxf.name)):
                jm = ly.dxf.name
                it = QListWidgetItem(vzorek(barva_hladiny(ly)), f"{jm}   ({pocty.get(jm, 0)})")
                it.setData(Qt.UserRole, jm)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked if (ly.is_off() or ly.is_frozen()) else Qt.Checked)
                if jm == aktivni:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setText(f"▶ {jm}   ({pocty.get(jm, 0)})")
                self.addItem(it)
        self._plneni = False

    def _zmena(self, it):
        if not self._plneni:
            self.zobrazeni.emit(it.data(Qt.UserRole), it.checkState() == Qt.Checked)


def _klic(jm: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", jm)]


class PanelVlastnosti(QTextBrowser):
    """Vlastnosti vybraných prvků (typ, hladina, barva, styl, tloušťka, rozměry) – jako Element Information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cad_vlastnosti")
        self.setOpenLinks(False)

    def ukaz(self, vyber: list, popis) -> None:
        if not vyber:
            self.setHtml("<p style='color:#9CA3AF'>Nic není vybráno.<br><br>Klikněte na prvek nebo táhněte okno "
                         "(zleva doprava = jen celé prvky, zprava doleva = i protnuté).</p>")
            return
        if len(vyber) == 1:
            self.setHtml(popis(vyber[0]))
            return
        c = Counter(e.dxftype() for e in vyber)
        hl = Counter(e.dxf.get("layer", "0") for e in vyber)
        r = [f"<b>Vybráno {len(vyber)} prvků</b><br>"]
        r += [f"{t}: {n}×<br>" for t, n in c.most_common()]
        r.append("<br><b>Hladiny:</b> " + ", ".join(f"{h} ({n})" for h, n in hl.most_common(12)))
        r.append("<br><br><span style='color:#9CA3AF'>Změna hladiny, barvy, stylu nebo tloušťky v liště nahoře "
                 "se použije na všechny vybrané prvky.</span>")
        self.setHtml("".join(r))
