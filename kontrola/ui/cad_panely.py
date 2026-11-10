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
                  "bod", "text", "text po prvku", "popisek", "šrafa", "vzorek", "buňky po prvku", "kóta", "kóta úhlu", "kóta poloměru", "vlož", "kolmice",
                  "osa úhlu"]),
    ("Úpravy", ["posun", "kopie", "otoč", "měřítko", "zrcadli", "pole", "rovnoběžka", "ořež", "prodluž", "zaobli",
                "zkos", "rozděl", "smaž část", "natáhni", "spoj", "rozpoj", "uprav text", "zvyš text", "nahraď buňku", "zarovnej", "ořež ohradou",
                "smaž"]),
    ("Výběr", ["vše", "ohrada", "podobné", "vyber", "skupina"]),
    ("Měření", ["vzdálenost", "délka", "výměra", "info"]),
    ("Geodézie", ["body", "kódy", "kódovník", "vrstevnice", "profil", "mračno", "síť", "transformace", "georeference", "oměrné míry", "převod atributů"]),
    ("Zobrazení", ["celý", "přiblížit", "předchozí pohled", "vrstvy", "arch"]),
]
NAZVY = {"vlož": "Vložit buňku", "body": "Body ze seznamu", "vrstvy": "Správce hladin", "celý": "Celý výkres",
         "info": "Informace o prvku", "vše": "Vybrat vše", "vyber": "Výběr podle atributů",
         "podobné": "Vybrat podobné", "ohrada": "Výběr ohradou", "skupina": "Skupina prvků",
         "délka": "Délka výběru", "výměra": "Výměra prvku", "síť": "Souřadnicová síť", "vrstevnice": "Vrstevnice a TIN", "profil": "Podélný profil", "kódy": "Kresba z kódů", "kódovník": "Kódovník", "georeference": "Georeference rastru", "mračno": "Mračno bodů", "zvyš text": "Kopie textu se zvýšením čísla",
         "nahraď buňku": "Nahradit buňku",
         "kolmice": "Kolmice z bodu na prvek", "osa úhlu": "Osa úhlu", "arch": "Arch (papír) pod výkresem", "vzorek": "Vzorek plochy (značky kultur)", "buňky po prvku": "Buňky po prvku (stromořadí)", "text po prvku": "Text podél prvku", "zarovnej": "Zarovnat prvky podle hrany", "ořež ohradou": "Ořezat ohradou (Fence Clip)"}


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
        if callable(getattr(self, "filtr", None)):
            self.filtr()

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


class PanelUpravy(QWidget):
    """Úprava vybraných prvků přímo v Průzkumníku (jako Vlastnosti v MicroStationu): hladina, barva, styl,
    tloušťka; u textu obsah, výška a natočení; u bodu, buňky a textu poloha. Každá změna = jedno Zpět."""

    def __init__(self, stranka, parent=None):
        from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLineEdit
        super().__init__(parent)
        self.s = stranka
        self._plneni = False
        f = QFormLayout(self)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(3)
        self.hladina = QComboBox()
        self.hladina.setEditable(True)
        self.hladina.setInsertPolicy(QComboBox.NoInsert)
        self.hladina.setToolTip("Přesunout vybrané prvky do hladiny (napsaná nová hladina se založí)")
        self.hladina.activated.connect(lambda _i: self._zmen_hladinu())
        self.hladina.lineEdit().editingFinished.connect(self._zmen_hladinu)
        self.barva = QPushButton()
        self.barva.setToolTip("Barva prvku (tabulka MicroStationu 0–255), nebo dle hladiny – každý prvek může mít "
                              "jinou barvu než jeho hladina")
        self.barva.clicked.connect(self._zmen_barvu)
        self.styl = QComboBox()
        self.styl.activated.connect(lambda i: self._styl_tl("styl", self.styl.itemData(i)))
        self.tl = QComboBox()
        self.tl.activated.connect(lambda i: self._styl_tl("tloušťka", self.tl.itemData(i)))
        self.text = QLineEdit()
        self.text.editingFinished.connect(self._zmen_text)
        self.vyska = QDoubleSpinBox()
        self.vyska.setRange(0.01, 1000)
        self.vyska.setDecimals(2)
        self.vyska.setSuffix(" m")
        self.vyska.editingFinished.connect(lambda: self._dxf("height", self.vyska.value(), ("TEXT",)))
        self.uhel = QDoubleSpinBox()
        self.uhel.setRange(-360, 360)
        self.uhel.setDecimals(2)
        self.uhel.setSuffix(" °")
        self.uhel.editingFinished.connect(lambda: self._dxf("rotation", self.uhel.value(), ("TEXT", "INSERT")))
        self.y = QLineEdit()
        self.x = QLineEdit()
        for w in (self.y, self.x):
            w.editingFinished.connect(self._zmen_polohu)
        self.meritko = QDoubleSpinBox()
        self.meritko.setRange(0.001, 10000)
        self.meritko.setDecimals(3)
        self.meritko.editingFinished.connect(self._zmen_meritko)
        self.radky = {}
        for jm, w in (("Hladina", self.hladina), ("Barva", self.barva), ("Styl", self.styl), ("Tloušťka", self.tl),
                      ("Text", self.text), ("Výška textu", self.vyska), ("Natočení", self.uhel),
                      ("Y", self.y), ("X", self.x), ("Měřítko", self.meritko)):
            lb = QLabel(jm + ":")
            f.addRow(lb, w)
            self.radky[jm] = (lb, w)
        self.nastav([])

    def _ukaz(self, jm: str, on: bool):
        for w in self.radky[jm]:
            w.setVisible(on)

    def nastav(self, vyber: list) -> None:
        self._plneni = True
        try:
            self.setVisible(bool(vyber))
            if not vyber:
                return
            s = self.s
            typy = {e.dxftype() for e in vyber}
            jeden = vyber[0] if len(vyber) == 1 else None
            self.hladina.clear()
            if s.dok is not None:
                self.hladina.addItems(sorted((ly.dxf.name for ly in s.dok.doc.layers), key=_klic))
            hl = {e.dxf.get("layer", "0") for e in vyber}
            self.hladina.setCurrentText(hl.pop() if len(hl) == 1 else "")
            barvy = {e.dxf.get("color", 256) for e in vyber}
            self._ukaz_barvu(barvy.pop() if len(barvy) == 1 else None, jeden)
            for cil, zdroj in ((self.styl, s.styl_cb), (self.tl, s.tl_cb)):
                cil.clear()
                for i in range(zdroj.count()):
                    if zdroj.itemData(i) is not None:
                        cil.addItem(zdroj.itemText(i), zdroj.itemData(i))
                cil.insertItem(0, "(beze změny)", None)
                cil.setCurrentIndex(0)
            carove = not typy <= {"TEXT", "MTEXT", "INSERT", "POINT"}
            self._ukaz("Styl", carove)
            self._ukaz("Tloušťka", carove)
            je_text = jeden is not None and jeden.dxftype() == "TEXT"
            self._ukaz("Text", je_text or (jeden is not None and jeden.dxftype() == "MTEXT"))
            if self.text.isVisible() or je_text or (jeden is not None and jeden.dxftype() == "MTEXT"):
                self.text.setText(jeden.dxf.text if je_text else jeden.text)
            vsechny_texty = typy == {"TEXT"}
            self._ukaz("Výška textu", vsechny_texty)
            if vsechny_texty:
                self.vyska.setValue(vyber[0].dxf.height)
            self._ukaz("Natočení", jeden is not None and jeden.dxftype() in ("TEXT", "INSERT"))
            if jeden is not None and jeden.dxftype() in ("TEXT", "INSERT"):
                self.uhel.setValue(jeden.dxf.get("rotation", 0.0))
            poloha = jeden is not None and jeden.dxftype() in ("POINT", "INSERT", "TEXT")
            self._ukaz("Y", poloha)
            self._ukaz("X", poloha)
            if poloha:
                px, py = self._bod(jeden)
                sj = getattr(s, "sjtsk", False) or (px < 0 and py < 0)
                self.radky["Y"][0].setText("Y:" if sj else "x:")
                self.radky["X"][0].setText("X:" if sj else "y:")
                self.y.setText(f"{-px if sj else px:.3f}")
                self.x.setText(f"{-py if sj else py:.3f}")
            self._ukaz("Měřítko", jeden is not None and jeden.dxftype() == "INSERT")
            if jeden is not None and jeden.dxftype() == "INSERT":
                self.meritko.setValue(jeden.dxf.get("xscale", 1.0))
        finally:
            self._plneni = False

    @staticmethod
    def _bod(e):
        if e.dxftype() == "POINT":
            p = e.dxf.location
        elif e.dxftype() == "TEXT" and e.dxf.get("halign", 0) + e.dxf.get("valign", 0) > 0 and e.dxf.hasattr(
                "align_point"):
            p = e.dxf.align_point
        else:
            p = e.dxf.insert
        return p.x, p.y

    def _ukaz_barvu(self, aci, e):
        from ..cad import symbologie as SY
        b = self.barva
        if aci is None:
            b.setText("(různé)")
            b.setStyleSheet("")
            return
        if aci == 256:
            b.setText("dle hladiny")
            b.setStyleSheet("")
            return
        ms = None
        if e is not None and self.s.kresleni is not None:
            ms = self.s.kresleni.ms_barvy_prvku.get(e.dxf.handle)
        if ms is None:
            ms = SY.aci_na_ms(aci, self.s._pravidla())
        r, g, bl = SY.tabulka(self.s._pravidla()).get(ms, (128, 128, 128))
        b.setText(str(ms))
        b.setStyleSheet(f"background: rgb({r},{g},{bl}); color: {'black' if r * .3 + g * .59 + bl * .11 > 140 else 'white'};")

    # --------------------------------------------------------------- změny
    def _zmen_hladinu(self):
        jm = self.hladina.currentText().strip()
        if self._plneni or not jm or not self.s.vyber:
            return
        if all(e.dxf.get("layer", "0") == jm for e in self.s.vyber):
            return
        if jm not in self.s.dok.doc.layers:
            self.s.dok.doc.layers.add(jm)
        self.s.uprav_vyber(layer=jm)

    def _zmen_barvu(self):
        from ..cad import symbologie as SY
        akt = None
        if len(self.s.vyber) == 1 and self.s.kresleni is not None:
            akt = self.s.kresleni.ms_barvy_prvku.get(self.s.vyber[0].dxf.handle)
        d = BarvaDialog(SY.tabulka(self.s._pravidla()), akt, self)
        if d.exec() and d.vysledek is not None and self.s.vyber:
            self.s._barva("dle" if d.vysledek == 256 else str(d.vysledek))
            self.s._zvyrazni()

    def _styl_tl(self, co: str, v):
        if self._plneni or v is None or not self.s.vyber:
            return
        self.s._styl_tloustka(co, v)
        self.s._zvyrazni()

    def _dxf(self, klic: str, hodnota, typy):
        if self._plneni or not self.s.vyber:
            return
        if all(abs(float(e.dxf.get(klic, 0.0)) - hodnota) < 1e-9 for e in self.s.vyber if e.dxftype() in typy):
            return
        self.s.uprav_vyber(_typy=typy, **{klic: hodnota})

    def _zmen_text(self):
        if self._plneni or len(self.s.vyber) != 1:
            return
        e = self.s.vyber[0]
        t = self.text.text()
        if not t or (e.dxftype() == "TEXT" and t == e.dxf.text) or (e.dxftype() == "MTEXT" and t == e.text):
            return
        self.s.uprav_vyber(text=t)

    def _zmen_polohu(self):
        if self._plneni or len(self.s.vyber) != 1:
            return
        e = self.s.vyber[0]
        try:
            a, b = float(self.y.text().replace(",", ".").replace(" ", "")), float(
                self.x.text().replace(",", ".").replace(" ", ""))
        except ValueError:
            return
        px, py = self._bod(e)
        sj = self.radky["Y"][0].text().startswith("Y")
        nx, ny = (-a, -b) if sj else (a, b)
        if abs(nx - px) < 1e-6 and abs(ny - py) < 1e-6:
            return
        self.s.posun_vyber(nx - px, ny - py)

    def _zmen_meritko(self):
        if self._plneni or len(self.s.vyber) != 1:
            return
        m = self.meritko.value()
        e = self.s.vyber[0]
        if e.dxftype() == "INSERT" and abs(e.dxf.get("xscale", 1.0) - m) > 1e-9:
            self.s.uprav_vyber(_typy=("INSERT",), xscale=m, yscale=m)


def _maly(text: str, tip: str, fn) -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tip)
    b.clicked.connect(lambda: fn())
    return b


def obal_vlastnosti(panel: PanelVlastnosti, stranka) -> QWidget:
    """Karta Vlastnosti Průzkumníku: popis vybraných prvků a kopírování atributů (jako MicroStation)."""
    from .flow import RadekTlacitek
    w = QWidget()
    w.setProperty("kompaktni", True)
    v = QVBoxLayout(w)
    v.setContentsMargins(4, 4, 4, 4)
    v.setSpacing(4)
    r = RadekTlacitek()
    r.addWidget(_maly("Převzít atributy", "<b>Převzít atributy</b> (MicroStation: Match Element Attributes)<br>"
                      "Klikněte na vzorový prvek – jeho hladina, barva, styl a tloušťka se stanou aktivními "
                      "(lišta Atributy nahoře). Pak kreslete, nebo je dejte jiným prvkům.",
                      lambda: stranka.proved("převezmi atributy")))
    r.addWidget(_maly("Dát na prvky", "<b>Změnit atributy</b> (MicroStation: Change Element Attributes)<br>"
                      "Aktivní atributy se nastaví vybraným prvkům, nebo prvkům, na které kliknete.",
                      lambda: stranka.proved("změň atributy")))
    r.addWidget(_maly("Vybrat podobné", "Vybere všechny prvky stejného typu ve stejné hladině jako vybraný "
                      "(Shift+B)", lambda: stranka.proved("podobné")))
    v.addLayout(r)
    stranka.panel_upravy = PanelUpravy(stranka)
    v.addWidget(stranka.panel_upravy)
    v.addWidget(panel, 1)
    return w


def obal_hladin(panel: PanelHladin, stranka) -> QWidget:
    """Karta Hladiny Průzkumníku: hledání, zapnout / vypnout vše, správce hladin."""
    from PySide6.QtWidgets import QLineEdit
    from .flow import RadekTlacitek
    w = QWidget()
    w.setProperty("kompaktni", True)
    v = QVBoxLayout(w)
    v.setContentsMargins(4, 4, 4, 4)
    v.setSpacing(4)
    hledat = QLineEdit()
    hledat.setPlaceholderText("🔍 hledat hladinu")
    hledat.setClearButtonEnabled(True)

    def filtr(t: str):
        t = t.strip().lower()
        for i in range(panel.count()):
            it = panel.item(i)
            it.setHidden(bool(t) and t not in str(it.data(Qt.UserRole)).lower())
    hledat.textChanged.connect(filtr)
    panel.filtr = lambda: filtr(hledat.text())
    v.addWidget(hledat)
    r = RadekTlacitek()
    r.addWidget(_maly("Zapnout vše", "Zobrazit všechny hladiny", lambda: stranka.hladiny_zobrazeni("vše", True)))
    r.addWidget(_maly("Jen aktivní", "Vypnout všechny hladiny kromě aktivní",
                      lambda: stranka.hladiny_zobrazeni("vše", False)))
    r.addWidget(_maly("Správce…", "Správce hladin: barva, styl, zámek, nová, přejmenovat, smazat",
                      lambda: stranka.spravce_vrstev()))
    v.addLayout(r)
    v.addWidget(panel, 1)
    tip = QLabel("☑ = zobrazená · dvojklik = aktivní hladina")
    tip.setObjectName("poznamka")
    tip.setWordWrap(True)
    v.addWidget(tip)
    return w


class StartVykresu(QWidget):
    """Úvod CAD bez otevřeného výkresu (jako úvodní obrazovka MicroStationu): nový, otevřít, nedávné soubory."""

    def __init__(self, stranka, parent=None):
        super().__init__(parent)
        from pathlib import Path

        from PySide6.QtCore import QSettings
        self.setObjectName("cad_start")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QWidget#cad_start{background:#F8FAFC;border:1px solid #CBD5E1;border-radius:10px}"
                           "QWidget#cad_start QLabel{color:#1E293B;background:transparent}"
                           "QWidget#cad_start QPushButton{text-align:left;padding:4px 10px}")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 18, 12)
        v.setSpacing(4)
        t = QLabel("<span style='font-size:15pt;font-weight:700'>Začněte výkres</span>")
        v.addWidget(t)
        pozn = QLabel("Souřadnice S-JTSK jako školní seed. Sada určuje hladiny, buňky a styly čar – výkres "
                      "z MultiScale a z Pasportu jsou odlišné soubory.")
        pozn.setWordWrap(True)
        v.addWidget(pozn)
        v.addWidget(QLabel("<b>Nový výkres v pracovní sadě</b> (jako ve škole)"))
        for text, tip, fn in (
                ("✚  MultiScale – Účelová mapa", "Seed, hladiny, buňky a styly čar sady MultiScale, karty Účelové "
                 "mapy (prvek jedním kliknutím) a měřítko anotací 1:1000", stranka.novy_um),
                ("✚  Pasport (pasportizace staveb)", "Seed, buňky a styly čar sady Pasport – jiné hladiny i značky "
                 "než MultiScale", lambda: stranka.novy_v_sade("MultiScale/Pasport")),
                ("✚  TM (technická mapa)", "Seed, buňky TM25 a styly čar sady TM",
                 lambda: stranka.novy_v_sade("MultiScale/TM")),
                ("✚  Bez pracovní sady", "Prázdný výkres jen s nastavením aplikace",
                 lambda: stranka.novy_v_sade(None)),
                ("📄  Nový – vybrat sadu, seed a název…", "Okno Nový jako v MicroStationu: pracovní sada, "
                 "seed (2D, výkres, list, 3D… nebo vlastní soubor přes Procházet), název a složka souboru",
                 lambda: stranka.novy_soubor()),
                ("📋  Nový podle zadání", "Hladiny, styly, písma a buňky podle pravidel ze zadání",
                 lambda: stranka.novy_podle_zadani()),
                ("📂  Otevřít DXF / DGN…", "Otevřít existující výkres", lambda: stranka.otevri())):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, f=fn: f())
            v.addWidget(b)
        items = QSettings("KontrolaVykresu", "KontrolaVykresu").value("cesty/posledni_vykresy", []) or []
        items = [items] if isinstance(items, str) else list(items)
        items = [p for p in items if Path(p).suffix.lower() in (".dxf", ".dgn") and Path(p).is_file()][:5]
        if items:
            v.addSpacing(4)
            v.addWidget(QLabel("<b>Nedávné soubory</b>"))
            for p in items[:3]:
                b = QPushButton(Path(p).name)
                b.setToolTip(p)
                b.setFlat(True)
                b.clicked.connect(lambda _c=False, p=p: stranka.otevri(p))
                v.addWidget(b)
        self.setFixedWidth(400)
        self.adjustSize()
