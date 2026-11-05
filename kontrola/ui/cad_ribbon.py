"""Rozvržení CAD jako MicroStation CONNECT: pás karet (ribbon) nahoře, panel Úlohy (Tasks) vlevo,
stavový řádek s úchyty dole. Popisky česky, v bublině je i anglický název nástroje z MicroStationu."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QScrollArea,
                               QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget)

from .cad_ikony import ikona

# příkaz → (český název, název v MicroStationu)
NAZVY = {
    "úsečka": ("Úsečka", "Place Line"), "polylinie": ("Lomená čára (SmartLine)", "Place SmartLine"),
    "čára pod úhlem": ("Čára pod úhlem", "Place Line (Angle)"), "obdélník": ("Obdélník", "Place Block"),
    "mnohoúhelník": ("Mnohoúhelník", "Place Shape"), "kružnice": ("Kružnice", "Place Circle"),
    "oblouk": ("Oblouk", "Place Arc"), "elipsa": ("Elipsa", "Place Ellipse"),
    "křivka": ("Křivka", "Place B-spline Curve"), "bod": ("Bod", "Place Point"),
    "body po prvku": ("Body po prvku", "Construct Points Along Element"),
    "kolmice": ("Kolmice", "Construct Perpendicular"), "osa úhlu": ("Osa úhlu", "Construct Angle Bisector"),
    "text": ("Text", "Place Text"), "uprav text": ("Upravit text", "Edit Text"),
    "text po prvku": ("Text podél prvku", "Place Text Along Element"),
    "zvyš text": ("Kopie textu se zvýšením", "Copy and Increment Text"),
    "popisek": ("Popisek s odkazem", "Place Note"), "popis souřadnic": ("Popis souřadnic", "Label Coordinate"),
    "písmo": ("Písmo", "Text Styles"), "najdi": ("Najít text", "Find Text"),
    "nahraď": ("Nahradit text", "Replace Text"),
    "vlož": ("Vložit buňku", "Place Active Cell"), "knihovna buněk": ("Knihovna buněk", "Cell Library"),
    "nahraď buňku": ("Nahradit buňku", "Replace Cells"), "blok": ("Vytvořit buňku", "Create Cell"),
    "buňky po prvku": ("Buňky po prvku", "Place Cells Along Element"),
    "šrafa": ("Šrafa", "Hatch Area"), "vzorek": ("Vzorek plochy", "Pattern Area"),
    "kóta": ("Kóta délky", "Dimension Linear"), "kóta úhlu": ("Kóta úhlu", "Dimension Angle"),
    "kóta poloměru": ("Kóta poloměru", "Dimension Radial"),
    "posun": ("Posunout", "Move"), "kopie": ("Kopírovat", "Copy"), "otoč": ("Otočit", "Rotate"),
    "měřítko": ("Změnit měřítko", "Scale"), "zrcadli": ("Zrcadlit", "Mirror"), "pole": ("Pole", "Array"),
    "rovnoběžka": ("Rovnoběžka", "Move Parallel / Copy Parallel"),
    "zarovnej": ("Zarovnat podle hrany", "Align Elements by Edge"),
    "posuň vrchol": ("Upravit prvek", "Modify Element"), "vlož vrchol": ("Vložit vrchol", "Insert Vertex"),
    "smaž vrchol": ("Smazat vrchol", "Delete Vertex"), "ořež": ("Oříznout", "Trim Elements"),
    "prodluž": ("Prodloužit", "Extend Element"), "zaobli": ("Zaoblit", "Construct Circular Fillet"),
    "zkos": ("Zkosit", "Construct Chamfer"), "rozděl": ("Rozdělit", "Break Element"),
    "smaž část": ("Smazat část", "Delete Part of Element"), "natáhni": ("Natáhnout", "Fence Stretch"),
    "spoj": ("Spojit do řetězce", "Create Complex Chain"), "rozpoj": ("Rozpojit", "Drop Element"),
    "ořež ohradou": ("Oříznout ohradou", "Fence Clip"), "smaž": ("Smazat", "Delete Element"),
    "skupina": ("Skupina", "Group"), "zruš skupinu": ("Zrušit skupinu", "Ungroup"),
    "zámek skupin": ("Zámek skupin", "Graphic Group Lock"),
    "vše": ("Vybrat vše", "Select All"), "ohrada": ("Ohrada", "Place Fence"),
    "podobné": ("Vybrat podobné", "Select Similar"), "vyber": ("Výběr podle atributů", "Select By Attributes"),
    "převezmi atributy": ("Převzít atributy", "Match Element Attributes"),
    "změň atributy": ("Změnit atributy", "Change Element Attributes"),
    "vzdálenost": ("Vzdálenost", "Measure Distance"), "délka": ("Délka prvků", "Measure Length"),
    "výměra": ("Výměra prvku", "Measure Area (Element)"), "měř plochu": ("Výměra z bodů", "Measure Area (Points)"),
    "měř úhel": ("Úhel", "Measure Angle"), "info": ("Informace o prvku", "Element Information"),
    "vlastnosti": ("Vlastnosti", "Properties"),
    "celý": ("Celý výkres", "Fit View"), "přiblížit": ("Přiblížit", "Zoom In"),
    "předchozí pohled": ("Předchozí pohled", "View Previous"), "otoč pohled": ("Otočit pohled", "Rotate View"),
    "pohled": ("Uložené pohledy", "Saved Views"),
    "vrstvy": ("Správce hladin", "Level Manager"), "zhasni": ("Vypnout hladinu", "Level Display Off"),
    "rozsviť": ("Zapnout hladinu", "Level Display On"), "styly čar": ("Styly čar (.rsc)", "Line Styles"),
    "reference": ("Reference", "References"), "rastr": ("Rastr", "Raster Manager"),
    "georeference": ("Georeference rastru", "Raster Warp"),
    "model": ("Modely", "Models"), "list": ("Nový list", "Sheet Model"), "výřez": ("Výřez na list", "Place Named Boundary"),
    "razítko": ("Rámeček a razítko", "Title Block"), "arch": ("Arch (papír)", "Print Boundary"),
    "tisk": ("Tisk do PDF", "Print"),
    "kopíruj do schránky": ("Kopírovat do schránky", "Copy (Ctrl+C)"),
    "vlož ze schránky": ("Vložit ze schránky", "Paste (Ctrl+V)"),
    "body": ("Body ze seznamu", "Import Coordinates"), "kódy": ("Kresba z kódů", "—"),
    "kódovník": ("Kódovník", "—"), "vrstevnice": ("Vrstevnice a TIN", "—"), "profil": ("Podélný profil", "—"),
    "mračno": ("Mračno bodů", "Point Cloud"), "síť": ("Souřadnicová síť", "Grid / Cross Ticks"),
    "transformace": ("Transformace", "Transform"), "oměrné míry": ("Oměrné míry", "—"),
    "převod atributů": ("Převod atributů na zadání", "—"), "qtrig": ("QTrig", "—"),
    "atributy": ("Atributy ze zadání", "—"), "zkratky": ("Klávesové zkratky", "Function Keys"),
}


def nazev(cmd: str) -> str:
    return NAZVY.get(cmd, (cmd[:1].upper() + cmd[1:], ""))[0]


def bublina(cmd: str, popisy: dict[str, str]) -> str:
    cz, ms = NAZVY.get(cmd, (nazev(cmd), ""))
    r = f"<b>{cz}</b>"
    if ms and ms != "—":
        r += f" <span style='color:#888'>(MicroStation: {ms})</span>"
    if popisy.get(cmd):
        r += f"<br>{popisy[cmd]}"
    return r + f"<br><i>příkaz: {cmd}</i>"


# ---------------------------------------------------------------- panel Úlohy (Tasks → Drawing)
ULOHY = [
    ("Čáry", ["úsečka", "polylinie", "čára pod úhlem", "křivka", "kolmice", "osa úhlu", "rovnoběžka"]),
    ("Mnohoúhelníky", ["obdélník", "mnohoúhelník"]),
    ("Oblouky", ["kružnice", "oblouk", "elipsa"]),
    ("Body", ["bod", "body po prvku", "body"]),
    ("Text", ["text", "uprav text", "text po prvku", "zvyš text", "popisek", "popis souřadnic"]),
    ("Buňky", ["vlož", "knihovna buněk", "nahraď buňku", "buňky po prvku", "blok"]),
    ("Šrafování", ["šrafa", "vzorek"]),
    ("Kótování", ["kóta", "kóta úhlu", "kóta poloměru"]),
    ("Ohrada", ["ohrada", "ořež ohradou", "natáhni"]),
    ("Manipulace", ["kopie", "posun", "otoč", "měřítko", "zrcadli", "pole", "zarovnej"]),
    ("Úpravy", ["posuň vrchol", "vlož vrchol", "smaž vrchol", "ořež", "prodluž", "zaobli", "zkos", "rozděl",
                "smaž část", "spoj", "rozpoj"]),
    ("Mazání", ["smaž"]),
    ("Skupiny", ["skupina", "zruš skupinu", "zámek skupin"]),
    ("Změna atributů", ["změň atributy", "převezmi atributy", "vyber", "podobné"]),
    ("Měření", ["vzdálenost", "délka", "výměra", "měř plochu", "měř úhel", "info"]),
]
ROZBALENE = {"Čáry", "Mnohoúhelníky", "Oblouky", "Text", "Manipulace", "Úpravy"}

# ---------------------------------------------------------------- pás karet
# položka: příkaz, "@atribut" = widget stránky CAD, "|" = zalomení sloupce malých tlačítek
KARTY = [
    ("Domů", [
        ("Atributy", ["@atributy"]),
        ("Základní", ["@b_vrstvy", "@b_ref", "@modely_w", "info"]),
        ("Výběr", ["vše", "ohrada", "vyber"]),
        ("Umístění", ["úsečka", "polylinie", "kružnice", "oblouk", "text", "vlož"]),
        ("Manipulace", ["kopie", "posun", "otoč", "měřítko", "zrcadli", "pole"]),
        ("Úpravy", ["posuň vrchol", "ořež", "prodluž", "zaobli", "rozděl", "smaž"]),
    ]),
    ("Kreslení", [
        ("Umístění", ["úsečka", "polylinie", "obdélník", "mnohoúhelník", "kružnice", "oblouk", "elipsa", "křivka",
                      "bod", "čára pod úhlem"]),
        ("Konstrukce", ["kolmice", "osa úhlu", "rovnoběžka", "body po prvku"]),
        ("Manipulace", ["kopie", "posun", "otoč", "měřítko", "zrcadli", "pole", "zarovnej"]),
        ("Úpravy", ["posuň vrchol", "vlož vrchol", "smaž vrchol", "ořež", "prodluž", "zaobli", "zkos", "rozděl",
                    "smaž část", "natáhni", "spoj", "rozpoj", "ořež ohradou", "smaž"]),
        ("Šrafování", ["šrafa", "vzorek"]),
    ]),
    ("Popisy", [
        ("Text", ["text", "uprav text", "text po prvku", "zvyš text", "popisek", "popis souřadnic", "písmo",
                  "najdi", "nahraď"]),
        ("Kóty", ["kóta", "kóta úhlu", "kóta poloměru"]),
        ("Buňky", ["vlož", "knihovna buněk", "nahraď buňku", "buňky po prvku", "blok"]),
    ]),
    ("Výkres a tisk", [
        ("Arch", ["arch", "tisk"]),
        ("Listy", ["model", "list", "výřez", "razítko"]),
    ]),
    ("Připojit", [
        ("Reference", ["reference"]),
        ("Rastr", ["rastr", "georeference"]),
        ("Styly čar", ["styly čar"]),
    ]),
    ("Nástroje", [
        ("Měření", ["vzdálenost", "délka", "výměra", "měř plochu", "měř úhel", "info", "vlastnosti"]),
        ("Atributy", ["změň atributy", "převezmi atributy", "vrstvy", "zhasni", "rozsviť"]),
        ("Schránka", ["kopíruj do schránky", "vlož ze schránky"]),
        ("Nastavení", ["zkratky"]),
    ]),
    ("Pohled", [
        ("Zobrazení", ["celý", "přiblížit", "předchozí pohled", "otoč pohled", "pohled"]),
    ]),
    ("Geodézie", [
        ("Body", ["body", "qtrig", "kódy", "kódovník"]),
        ("Mapa", ["síť", "oměrné míry", "transformace", "vrstevnice", "profil", "mračno"]),
    ]),
    ("Zadání a kontrola", [
        ("Kontrola", ["@b_check"]),
        ("Zadání", ["@b_novy_zadani", "@b_body", "@b_atributy", "@b_tahak", "převod atributů"]),
    ]),
]


def _tlacitko(cmd: str, popisy, barva, zvyr, velke: bool) -> QToolButton:
    b = QToolButton()
    b.setText(nazev(cmd))
    ik = ikona(cmd, barva, zvyr)
    if ik.isNull():  # bez ikony: prázdné místo, ať jsou názvy zarovnané
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        ik = QIcon(pm)
    b.setIcon(ik)
    b.setAutoRaise(True)
    b.setCheckable(True)
    b.setToolTip(bublina(cmd, popisy))
    if velke:
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setIconSize(QSize(26, 26))
        b.setMinimumWidth(54)
    else:
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setIconSize(QSize(16, 16))
    return b


class PasKaret(QWidget):
    """Pás karet jako v MicroStationu CONNECT: tlačítko Soubor, záložky karet, skupiny nástrojů s názvem dole."""
    nastroj = Signal(str)

    def __init__(self, popisy, stranka, barva="#374151", zvyr="#2563EB", parent=None):
        super().__init__(parent)
        self.setObjectName("cad_ribbon")
        self.tlacitka: dict[str, list[QToolButton]] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        horni = QHBoxLayout()
        horni.setContentsMargins(4, 2, 8, 0)
        horni.setSpacing(6)
        self.b_soubor = QToolButton()
        self.b_soubor.setText("Soubor")
        self.b_soubor.setObjectName("cad_soubor")
        self.b_soubor.setPopupMode(QToolButton.InstantPopup)
        self.b_soubor.setToolTip("Nový, otevřít, uložit, tisk (MicroStation: File)")
        self.b_soubor.setStyleSheet("QToolButton#cad_soubor{background:#1D5FAF;color:white;padding:3px 14px;"
                                    "border-radius:2px;font-weight:600} QToolButton#cad_soubor::menu-indicator"
                                    "{image:none}")
        horni.addWidget(self.b_soubor)
        self.pracovni_postup = QComboBox()
        self.pracovni_postup.setToolTip("Pracovní postup (Workflow): které karty jsou vidět")
        horni.addWidget(self.pracovni_postup)
        self.karty = QTabBar()
        self.karty.setDrawBase(False)
        self.karty.setExpanding(False)
        self.karty.setUsesScrollButtons(True)
        horni.addWidget(self.karty, 1)
        self.vpravo = QHBoxLayout()
        horni.addLayout(self.vpravo)
        lay.addLayout(horni)
        self.stack = QStackedWidget()
        self.stack.setObjectName("cad_ribbon_stack")
        lay.addWidget(self.stack)
        cara = QFrame()
        cara.setFrameShape(QFrame.HLine)
        cara.setFrameShadow(QFrame.Sunken)
        lay.addWidget(cara)
        self._stranky: dict[str, QWidget] = {}
        for titul, skupiny in KARTY:
            sc = QScrollArea()
            sc.setFrameShape(QFrame.NoFrame)
            sc.setWidgetResizable(True)
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(4, 2, 4, 0)
            h.setSpacing(4)
            for gtit, polozky in skupiny:
                h.addWidget(self._skupina(gtit, polozky, popisy, stranka, barva, zvyr))
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setFrameShadow(QFrame.Sunken)
                h.addWidget(sep)
            h.addStretch(1)
            sc.setWidget(w)
            sc.setFixedHeight(w.sizeHint().height() + 14)
            self.stack.addWidget(sc)
            self.karty.addTab(titul)
            self._stranky[titul] = sc
        self.karty.currentChanged.connect(self.stack.setCurrentIndex)
        self.POSTUPY = {"Kreslení": [k for k, _ in KARTY if k not in ("Geodézie",)],
                        "Geodézie a škola": ["Domů", "Geodézie", "Zadání a kontrola", "Popisy", "Výkres a tisk",
                                             "Pohled"],
                        "Vše": [k for k, _ in KARTY]}
        self.pracovni_postup.addItems(list(self.POSTUPY))
        self.pracovni_postup.currentTextChanged.connect(self._postup)
        ul = QSettings("KontrolaVykresu", "KontrolaVykresu").value("cad/pracovni_postup", "Vše")
        self.pracovni_postup.setCurrentText(ul if ul in self.POSTUPY else "Vše")
        self._postup(self.pracovni_postup.currentText())

    def _postup(self, jm: str):
        vid = self.POSTUPY.get(jm, [])
        for i, (k, _) in enumerate(KARTY):
            self.karty.setTabVisible(i, k in vid)
        if not self.karty.isTabVisible(self.karty.currentIndex()):
            self.karty.setCurrentIndex(0)
        QSettings("KontrolaVykresu", "KontrolaVykresu").setValue("cad/pracovni_postup", jm)

    def ukaz_kartu(self, titul: str):
        for i, (k, _) in enumerate(KARTY):
            if k == titul:
                self.karty.setTabVisible(i, True)
                self.karty.setCurrentIndex(i)

    def _skupina(self, titul, polozky, popisy, stranka, barva, zvyr) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(2, 0, 2, 0)
        v.setSpacing(0)
        g = QGridLayout()
        g.setSpacing(0)
        g.setContentsMargins(0, 0, 0, 0)
        prikazy = [p for p in polozky if not p.startswith("@")]
        widgety = [p for p in polozky if p.startswith("@")]
        col, r = 0, 0
        for p in widgety:
            w = getattr(stranka, p[1:], None)
            if w is None:
                continue
            if p == "@atributy":
                g.addWidget(w, 0, col, 3, 1)
                col += 1
                continue
            g.addWidget(w, r, col)
            r += 1
            if r == 3:
                r, col = 0, col + 1
        if r:
            col += 1
        velke = len(prikazy) <= 2 and not widgety
        if velke:
            for p in prikazy:
                b = self._pridej(p, popisy, barva, zvyr, True)
                g.addWidget(b, 0, col, 3, 1)
                col += 1
        else:
            # malá tlačítka po třech pod sebou (jako skupiny v MicroStationu)
            for i, p in enumerate(prikazy):
                b = self._pridej(p, popisy, barva, zvyr, False)
                g.addWidget(b, i % 3, col + i // 3)
        v.addLayout(g)
        v.addStretch(1)
        lbl = QLabel(titul)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#6B7280;font-size:11px")
        v.addWidget(lbl)
        return box

    def _pridej(self, cmd, popisy, barva, zvyr, velke) -> QToolButton:
        b = _tlacitko(cmd, popisy, barva, zvyr, velke)
        b.clicked.connect(lambda _=False, c=cmd: self.nastroj.emit(c))
        self.tlacitka.setdefault(cmd, []).append(b)
        return b


class PanelUloh(QScrollArea):
    """Panel Úlohy (Tasks) vlevo: Výběr prvků nahoře, pod ním rozbalovací skupiny nástrojů s názvy."""
    nastroj = Signal(str)

    def __init__(self, popisy, barva="#374151", zvyr="#2563EB", parent=None):
        super().__init__(parent)
        self.setObjectName("cad_paleta")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(1)
        hl = QLabel("Úlohy – Kreslení")
        hl.setStyleSheet("font-weight:600;padding:3px")
        hl.setToolTip("MicroStation: Tasks → Drawing")
        lay.addWidget(hl)
        self.tlacitka: dict[str, QToolButton] = {}
        self.vyber = QToolButton()
        self.vyber.setText("Výběr prvků")
        self.vyber.setToolTip("<b>Výběr prvků</b> <span style='color:#888'>(MicroStation: Element Selection)"
                              "</span><br>Ukončí nástroj; kliknutím nebo oknem vybíráte prvky (Esc)")
        self.vyber.setIcon(_sipka(barva))
        self.vyber.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.vyber.setAutoRaise(True)
        self.vyber.setCheckable(True)
        self.vyber.setChecked(True)
        self.vyber.clicked.connect(lambda: self.nastroj.emit(""))
        lay.addWidget(self.vyber)
        st = QSettings("KontrolaVykresu", "KontrolaVykresu")
        self._obsahy: dict[str, QWidget] = {}
        for titul, prikazy in ULOHY:
            hlav = QToolButton()
            hlav.setText(titul)
            hlav.setCheckable(True)
            hlav.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            hlav.setSizePolicy(hlav.sizePolicy().horizontalPolicy().Expanding, hlav.sizePolicy().verticalPolicy())
            hlav.setStyleSheet("QToolButton{text-align:left;font-weight:600;padding:3px;border:none;"
                               "background:rgba(127,127,127,0.15)}")
            obsah = QWidget()
            ov = QVBoxLayout(obsah)
            ov.setContentsMargins(6, 0, 0, 2)
            ov.setSpacing(0)
            for cmd in prikazy:
                b = _tlacitko(cmd, popisy, barva, zvyr, False)
                b.setIconSize(QSize(20, 20))
                b.setSizePolicy(b.sizePolicy().horizontalPolicy().Expanding, b.sizePolicy().verticalPolicy())
                b.clicked.connect(lambda _=False, c=cmd: self.nastroj.emit(c))
                ov.addWidget(b)
                self.tlacitka[cmd] = b
            ulozeno = st.value(f"cad/ulohy/{titul}", None)
            otevreno = (str(ulozeno).lower() == "true") if ulozeno is not None else titul in ROZBALENE
            hlav.setChecked(otevreno)
            obsah.setVisible(otevreno)
            hlav.setArrowType(Qt.DownArrow if otevreno else Qt.RightArrow)
            hlav.toggled.connect(lambda on, o=obsah, h=hlav, t=titul: self._rozbal(o, h, t, on))
            lay.addWidget(hlav)
            lay.addWidget(obsah)
            self._obsahy[titul] = obsah
        lay.addStretch(1)
        self.setWidget(w)
        self.setMinimumWidth(150)
        self.setMaximumWidth(280)

    def _rozbal(self, obsah, hlav, titul, on):
        obsah.setVisible(on)
        hlav.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        QSettings("KontrolaVykresu", "KontrolaVykresu").setValue(f"cad/ulohy/{titul}", on)

    def oznac(self, prikaz: str | None) -> None:
        for c, b in self.tlacitka.items():
            b.setChecked(c == prikaz)
        self.vyber.setChecked(not prikaz)


def _sipka(barva: str) -> QIcon:
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(barva))
    p.setPen(Qt.NoPen)
    from PySide6.QtGui import QPolygonF
    p.drawPolygon(QPolygonF([QPointF(10, 4), QPointF(10, 34), QPointF(17, 27), QPointF(22, 37), QPointF(27, 35),
                             QPointF(22, 25), QPointF(31, 25)]))
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def ikona_uchytu(typ: str, barva: str = "#374151") -> QIcon:
    """Malé ikony režimů úchytu (jako tlačítka Snap Mode ve stavovém řádku MicroStationu)."""
    s = 32
    pm = QPixmap(s, s)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(barva), 2)
    p.setPen(pen)
    zv = QColor("#E11D48")
    if typ == "konec":
        p.drawLine(4, 26, 22, 8)
        p.setBrush(zv); p.setPen(Qt.NoPen); p.drawRect(19, 5, 8, 8)
    elif typ == "stred":
        p.drawLine(4, 26, 28, 6)
        p.setBrush(zv); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(16, 16), 4, 4)
    elif typ == "prusecik":
        p.drawLine(4, 4, 28, 28); p.drawLine(4, 28, 28, 4)
        p.setBrush(zv); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(16, 16), 4, 4)
    elif typ == "kolmice":
        p.drawLine(4, 26, 28, 26); p.drawLine(16, 26, 16, 4); p.drawRect(16, 20, 6, 6)
    elif typ == "tecna":
        p.setBrush(Qt.NoBrush); p.drawEllipse(QPointF(16, 18), 8, 8); p.drawLine(2, 10, 30, 10)
    elif typ == "stred_kruznice":
        p.setBrush(Qt.NoBrush); p.drawEllipse(QPointF(16, 16), 11, 11)
        p.setBrush(zv); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(16, 16), 3.5, 3.5)
    elif typ == "bod":
        p.drawLine(9, 9, 23, 23); p.drawLine(9, 23, 23, 9)
    else:  # nejbližší
        p.drawLine(4, 26, 28, 6)
        p.setBrush(zv); p.setPen(Qt.NoPen); p.drawEllipse(QPointF(9, 22), 4, 4)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def menu_soubor(stranka) -> QMenu:
    m = QMenu(stranka)
    for text, b in (("Nový", stranka.b_new), ("Nový podle zadání", stranka.b_novy_zadani),
                    ("Otevřít…", stranka.b_open), ("Uložit", stranka.b_save), ("Uložit jako…", stranka.b_saveas),
                    (None, None), ("Tisk do PDF…", stranka.b_tisk), (None, None),
                    ("Klávesové zkratky…", stranka.b_zkratky)):
        if text is None:
            m.addSeparator()
            continue
        a = m.addAction(text)
        a.setToolTip(b.toolTip())
        a.triggered.connect(b.click)
        a.setData(b)
    m.aboutToShow.connect(lambda: [a.setEnabled(a.data().isEnabled()) for a in m.actions() if a.data()])
    return m
