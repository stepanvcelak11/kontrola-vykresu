"""Rozvržení Výpočtů jako v Gromě 14: roletové menu, lišta nastavení, datová okna a stavový řádek.

Podle příručky Groma v. 14.0, kap. 4 Ovládání programu: nahoře menu (Soubor, Editace, Souřadnice,
Měření, Výpočty, Okno), pod ním lišta nastavení (kód kvality, měřítko, najít bod), pod ní pracovní
plocha s datovými okny (seznam souřadnic, seznam měření, grafika, protokol) a dole stavový řádek
(aktivní seznam, počet položek, počet označených).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMdiArea,
                               QMdiSubWindow, QMenu, QPlainTextEdit, QWidget)

class _DatoveOkno(QMdiSubWindow):
    """Datové okno: křížek okno jen schová (obsah i stav zůstanou), znovu se otevře z menu Okno."""

    def closeEvent(self, e):  # noqa: N802
        e.ignore()
        self.hide()


class DatovaOkna(QMdiArea):
    """Pracovní plocha s datovými okny. Má stejné rozhraní jako dřívější záložky (addTab, setCurrentWidget…),
    takže ostatní části aplikace (Kokeš, QTrig, přehled funkcí) fungují beze změny."""

    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._okna: list[tuple[QWidget, _DatoveOkno, str]] = []
        self._rozvrzeno = False
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.subWindowActivated.connect(self._aktivovano)

    # --- rozhraní jako QTabWidget
    def addTab(self, w: QWidget, titul: str, viditelne: bool = True) -> int:  # noqa: N802
        sub = _DatoveOkno()
        sub.setWidget(w)
        sub.setWindowTitle(titul)
        sub.setAttribute(Qt.WA_DeleteOnClose, False)
        self.addSubWindow(sub)
        sub.resize(560, 360)
        self._okna.append((w, sub, titul))
        sub.setVisible(viditelne)
        return len(self._okna) - 1

    def setDocumentMode(self, _on: bool) -> None:  # noqa: N802
        pass

    def count(self) -> int:
        return len(self._okna)

    def widget(self, i: int) -> QWidget | None:
        return self._okna[i][0] if 0 <= i < len(self._okna) else None

    def tabText(self, i: int) -> str:  # noqa: N802
        return self._okna[i][2] if 0 <= i < len(self._okna) else ""

    def indexOf(self, w: QWidget) -> int:  # noqa: N802
        return next((i for i, (x, _s, _t) in enumerate(self._okna) if x is w), -1)

    def currentIndex(self) -> int:  # noqa: N802
        sub = self.activeSubWindow()
        return next((i for i, (_x, s, _t) in enumerate(self._okna) if s is sub), -1)

    def currentWidget(self) -> QWidget | None:  # noqa: N802
        return self.widget(self.currentIndex())

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        if 0 <= i < len(self._okna):
            self.otevri(self._okna[i][0])

    def setCurrentWidget(self, w: QWidget) -> None:  # noqa: N802
        self.otevri(w)

    # --- práce s okny (menu Okno)
    def okno(self, w: QWidget) -> _DatoveOkno | None:
        return next((s for x, s, _t in self._okna if x is w), None)

    def otevri(self, w: QWidget) -> None:
        sub = self.okno(w)
        if sub is None:
            return
        if sub.isHidden():
            sub.show()
        if sub.isMinimized():
            sub.showNormal()
        self.setActiveSubWindow(sub)
        sub.raise_()
        i = self.indexOf(w)
        self.currentChanged.emit(i)

    def mozaika_vodorovne(self) -> None:
        """Okna pod sebou přes celou šířku (Okno → Mozaika horizontálně)."""
        okna = [s for _x, s, _t in self._okna if not s.isHidden() and not s.isMinimized()]
        if not okna:
            return
        r = self.viewport().rect()
        h = max(80, r.height() // len(okna))
        for i, s in enumerate(okna):
            s.showNormal()
            s.setGeometry(0, i * h, r.width(), h)

    def mozaika_svisle(self) -> None:
        """Okna vedle sebe (Okno → Mozaika vertikálně)."""
        okna = [s for _x, s, _t in self._okna if not s.isHidden() and not s.isMinimized()]
        if not okna:
            return
        r = self.viewport().rect()
        w = max(120, r.width() // len(okna))
        for i, s in enumerate(okna):
            s.showNormal()
            s.setGeometry(i * w, 0, w, r.height())

    def srovnej_ikony(self) -> None:
        r = self.viewport().rect()
        x = 0
        for _w, s, _t in self._okna:
            if not s.isHidden() and s.isMinimized():
                s.move(x, r.height() - s.height())
                x += s.width()

    def zavri_aktivni(self) -> None:
        sub = self.activeSubWindow()
        if sub is not None:
            sub.hide()

    def _aktivovano(self, sub) -> None:
        i = next((i for i, (_x, s, _t) in enumerate(self._okna) if s is sub), -1)
        if i >= 0:
            self.currentChanged.emit(i)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if not self._rozvrzeno:  # první zobrazení: okna pod sebou jako v Gromě (rozměr plochy už je známý)
            self._rozvrzeno = True
            self.mozaika_vodorovne()


class OknoProtokolu(QPlainTextEdit):
    """Okno s protokolem o výpočtech (vypocty/protokol.txt) – každý výpočet se do něj připíše."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setStyleSheet("font-family: Consolas, 'Courier New', 'DejaVu Sans Mono', monospace;")
        self.setPlaceholderText("Protokol o výpočtech – sem se zapisuje každý výpočet z menu Výpočty.")
        self._soubor: Path | None = None

    def nacti(self, soubor: Path | None) -> None:
        self._soubor = soubor
        try:
            text = soubor.read_text(encoding="utf-8") if soubor and soubor.exists() else ""
        except OSError:
            text = ""
        self.setPlainText(text)
        self.moveCursor(self.textCursor().MoveOperation.End)


class ListaNastaveni(QWidget):
    """Lišta nastavení pod menu (jako v Gromě): kód kvality, měřítkový koeficient, najít bod."""

    hledej = Signal(str)
    uloha = Signal(str)  # přepnout / založit úlohu

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)
        self.ulohy = QComboBox()
        self.ulohy.setToolTip("Rozpracovaná úloha – každá má svůj seznam souřadnic, zápisník a protokol "
                              "(jako soubory v Gromě). Poslední položka založí novou.")
        self.ulohy.setMinimumWidth(150)
        self.ulohy.activated.connect(self._vyber_ulohy)
        lay.addWidget(QLabel("Úloha:"))
        lay.addWidget(self.ulohy)
        self.nastav_ulohy([""], "")
        self.kod_kvality = QComboBox()
        for k in range(1, 9):
            self.kod_kvality.addItem(str(k), k)
        self.kod_kvality.setToolTip("Kód kvality – podle něj se počítají mezní odchylky (bez platného kódu Groma "
                                    "předpokládá 3)")
        self.meritko = QDoubleSpinBox()
        self.meritko.setDecimals(6)
        self.meritko.setRange(0.99, 1.01)
        self.meritko.setSingleStep(0.00001)
        self.meritko.setToolTip("Měřítkový koeficient – násobí měřené délky (zkreslení Křovákova zobrazení "
                                "a nadmořská výška). 1,000000 = bez korekce.")
        self.najit = QLineEdit()
        self.najit.setPlaceholderText("číslo bodu")
        self.najit.setMaximumWidth(120)
        self.najit.setClearButtonEnabled(True)
        self.najit.setToolTip("Najít bod v seznamu souřadnic podle čísla (vyhledává průběžně při psaní)")
        for t, w in (("Kód kvality:", self.kod_kvality), ("Měřítko:", self.meritko), ("Najít bod:", self.najit)):
            lay.addWidget(QLabel(t))
            lay.addWidget(w)
        lay.addStretch(1)
        self.nacti()
        self.kod_kvality.currentIndexChanged.connect(self._uloz)
        self.meritko.valueChanged.connect(self._uloz)
        self.najit.textChanged.connect(self.hledej)

    NOVA = "+ Nová úloha…"

    def nastav_ulohy(self, nazvy: list[str], aktivni: str) -> None:
        self.ulohy.blockSignals(True)
        self.ulohy.clear()
        for n in nazvy:
            self.ulohy.addItem(n or "Hlavní seznam projektu", n)
        self.ulohy.addItem(self.NOVA, None)
        self.ulohy.setCurrentIndex(max(0, self.ulohy.findData(aktivni)))
        self.ulohy.blockSignals(False)

    def _vyber_ulohy(self, i: int) -> None:
        n = self.ulohy.itemData(i)
        if n is None:  # nová úloha
            from PySide6.QtWidgets import QInputDialog
            t, ok = QInputDialog.getText(self, "Nová úloha", "Název úlohy (např. 02 Polygon):")
            if not ok or not t.strip():
                self.ulohy.setCurrentIndex(0)
                return
            n = t.strip()
        self.uloha.emit(n)

    def nacti(self) -> None:
        from ..geodezie import nastaveni as N
        n = N.aktualni()
        for w in (self.kod_kvality, self.meritko):
            w.blockSignals(True)
        self.kod_kvality.setCurrentIndex(max(0, self.kod_kvality.findData(n.kod_kvality)))
        self.meritko.setValue(n.meritko_rucne if n.meritko_rezim == "ručně" else 1.0)
        for w in (self.kod_kvality, self.meritko):
            w.blockSignals(False)

    def _uloz(self, *_a) -> None:
        from ..geodezie import nastaveni as N
        from .nastaveni_vypoctu import uloz
        n = N.aktualni()
        n.kod_kvality = int(self.kod_kvality.currentData() or 3)
        m = round(self.meritko.value(), 6)
        if abs(m - 1.0) < 1e-9:
            if n.meritko_rezim == "ručně":
                n.meritko_rezim = "bez korekce"
        else:
            n.meritko_rezim, n.meritko_rucne = "ručně", m
        uloz(n)


# Pás karet jako v Gromě 14 (screenshoty G01–G06): karta → skupiny → tlačítka.
# Tlačítko: (text, cíl) – cíl je název úlohy z ULOHY, seznam názvů (rozbalovací nabídka), nebo „@funkce“ stránky.
KARTY_GROMA = [
    ("Soubor", [
        ("Soubor", [("Import souřadnic…", "@import_dialog"), ("Export souřadnic…", "@export_dialog"),
                    ("Načíst z QTrig…", "@qtrig_dialog")]),
        ("Editace", [("Krok zpět", "@undo"), ("Krok vpřed", "@redo"), ("Odstranit", "@delete_selected")]),
        ("Seznam", [("Přidej bod…", "@add_point"), ("Hromadné změny…", "@bulk_dialog"),
                    ("Porovnání souřadnic…", "@porovnat_seznam"), ("Identické body…", "@duplicates_dialog")]),
        ("Kódování", [("Kresba z kódů…", "@kresba_z_kodu"), ("Kódovací tabulka…", "@otevri_kodovnik")]),
        ("Nastavení", [("Nastavení…", "@_nastaveni")]),
        ("Pohledy", [("Mozaika horizontálně", "@_mozaika_h"), ("Mozaika vertikálně", "@_mozaika_v"),
                     ("Kaskáda", "@_kaskada"), ("Okna", "@okna")]),
    ]),
    ("Protokol", [
        ("Protokol", [("Zobrazit", "@_protokol"), ("Uložit do PDF…", "@_protokol_pdf")]),
        ("Měření", [("Seznam měření", "@_zapisnik"), ("Zpracování zápisníku…", "@_zpracovani")]),
    ]),
    ("Výpočty", [
        ("Podrobné", [("Polární", "Rajón (polární bod)"), ("Polární dávkou", "@_zpracovani"),
                      ("Ortogonální", "Ortogonální metoda")]),
        ("Protínání", [("Ze směrů", "Protínání vpřed ze směrů"), ("Z úhlů", "Protínání vpřed z úhlů"),
                       ("Z délek", "Protínání z délek"), ("Zpět", "Protínání zpět")]),
        ("Průsečíky", [("Přímka - přímka", "Průsečíky"), ("Bod na přímce", "Bod na přímce"),
                       ("Kružnice ze 3 bodů", "Kružnice ze tří bodů")]),
        ("Oměrné", [("Kontrolní", "Kontrolní oměrné míry"), ("Výměra z měr", "Výměra z měr")]),
        ("Bodové pole", [("Volné stanovisko", "Volné stanovisko"),
                         ("Polygonový pořad", ["Polygonový pořad", "Polygonový pořad uzavřený",
                                               "Polygonový pořad volný", "Polygonový pořad jednostranně orientovaný",
                                               "Polygonový pořad vetknutý"]),
                         ("Transformace", "Transformace")]),
        ("Výšky", [("Trigonometrická výška", ["Trigonometrická výška", "Trigonometrická výška oboustranně"]),
                   ("Výškový pořad", ["Nivelační pořad", "Nivelační zápisník", "Vyrovnání nivelační sítě"]),
                   ("Redukce délky", "Redukce délky")]),
        ("Měření", [("Směrník a délka", "Směrník a délka"), ("Úhel", "Úhel ze souřadnic"),
                    ("Výměry", ["Výměra a obvod", "Výměry parcel dávkou", "Výkaz výměr GP", "Oddělení parcely"]),
                    ("Kubatury", "Model terénu a kubatura")]),
        ("Vytyčovací prvky", [("Polární", "Vytyčovací prvky"),
                              ("Ortogonální", ["Staničení a kolmice", "Bod ze staničení a kolmice"])]),
        ("Speciální", [("Rozložení oblouku", "Kružnicový oblouk"), ("Centrace", "Centrace směrů"),
                       ("Křovák (WGS84)", "Převod S-JTSK ↔ WGS84"), ("Převod úhlů", "Převod úhlů"),
                       ("Testování přesnosti", ["Kontrola dvou určení", "Testování přesnosti ÚM – body",
                                                "Testování přesnosti ÚM – délky"])]),
    ]),
]


class PasGromy(QWidget):
    """Pás karet Výpočtů (Soubor, Protokol, Výpočty) – rozložení skupin a názvy tlačítek jako v Gromě 14."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import (QFrame, QGridLayout, QScrollArea, QStackedWidget, QTabBar, QToolButton,
                                       QVBoxLayout)
        self.page = page
        self.akce: dict[str, QAction] = {}  # „Karta/Skupina/Text“ → akce (i položky rozbalovacích nabídek)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.karty = QTabBar()
        self.karty.setDrawBase(False)
        self.karty.setExpanding(False)
        lay.addWidget(self.karty)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        jmena = {n: i for i, (n, _p, _f, _fn) in enumerate(_ulohy())}
        pouzite = {n for _k, sk in KARTY_GROMA for _s, tl in sk for _t, c in tl
                   for n in (c if isinstance(c, list) else [c])}
        zbytek = [n for n in jmena if n not in pouzite]
        self.ulohy_v_pasu = (pouzite | set(zbytek)) & set(jmena)  # všechny úlohy jsou dostupné z pásu
        karty = [(k, sk + ([("Další", [("Další výpočty", zbytek)])] if k == "Výpočty" and zbytek else []))
                 for k, sk in KARTY_GROMA]
        for karta, skupiny in karty:
            self.karty.addTab(karta)
            obsah = QWidget()
            h = QHBoxLayout(obsah)
            h.setContentsMargins(4, 2, 4, 0)
            h.setSpacing(2)
            for skupina, tlacitka in skupiny:
                box = QWidget()
                v = QVBoxLayout(box)
                v.setContentsMargins(2, 0, 2, 0)
                v.setSpacing(0)
                g = QGridLayout()
                g.setSpacing(0)
                for k, (text, cil) in enumerate(tlacitka):
                    b = QToolButton()
                    b.setAutoRaise(True)
                    b.setToolButtonStyle(Qt.ToolButtonTextOnly)
                    klic = f"{karta}/{skupina}/{text}"
                    if isinstance(cil, list):
                        b.setText(text + " ▾")
                        b.setPopupMode(QToolButton.InstantPopup)
                        m = QMenu(b)
                        for n in cil:
                            if n in jmena:
                                a = m.addAction(n)
                                a.triggered.connect(lambda _c=False, i=jmena[n]: otevri_ulohu(page, i))
                                self.akce[f"{klic}/{n}"] = a
                        b.setMenu(m)
                    else:
                        a = QAction(text, b)
                        fn = self._funkce(cil, jmena)
                        if fn is None:
                            continue
                        a.triggered.connect(lambda _c=False, f=fn: f())
                        b.setDefaultAction(a)
                        self.akce[klic] = a
                    g.addWidget(b, k % 3, k // 3)
                v.addLayout(g)
                v.addStretch(1)
                lbl = QLabel(skupina)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("color: gray; font-size: 8pt;")
                v.addWidget(lbl)
                h.addWidget(box)
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet("color: #d0d0d0;")
                h.addWidget(sep)
            h.addStretch(1)
            sc = QScrollArea()
            sc.setWidget(obsah)
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.NoFrame)
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sc.setFixedHeight(obsah.sizeHint().height() + 14)
            self.stack.addWidget(sc)
        self.karty.currentChanged.connect(self.stack.setCurrentIndex)
        i = [k for k, _s in KARTY_GROMA].index("Výpočty")
        self.karty.setCurrentIndex(i)
        self.stack.setCurrentIndex(i)

    def _funkce(self, cil: str, jmena: dict):
        p, o = self.page, self.page.tabs
        if not cil.startswith("@"):
            return (lambda i=jmena[cil]: otevri_ulohu(p, i)) if cil in jmena else None
        vlastni = {
            "@_nastaveni": lambda: (p.ulohy.nastaveni_vypoctu(), p.lista.nacti()),
            "@_mozaika_h": o.mozaika_vodorovne, "@_mozaika_v": o.mozaika_svisle, "@_kaskada": o.cascadeSubWindows,
            "@okna": lambda: self._menu_oken(), "@_protokol": lambda: o.otevri(p.protokol),
            "@_protokol_pdf": p.ulohy.protokol_pdf, "@_zapisnik": lambda: o.otevri(p.zapisnik),
            "@_zpracovani": lambda: getattr(p.win, "show_vypocet", lambda: None)(),
        }
        return vlastni.get(cil) or getattr(p, cil[1:], None)

    def _menu_oken(self) -> QMenu:
        p, o = self.page, self.page.tabs
        from PySide6.QtGui import QCursor
        m = QMenu(self)
        for w, t in ((p.seznam_okno, "Seznam souřadnic"), (p.zapisnik, "Seznam měření"), (p.grafika, "Grafika"),
                     (p.protokol, "Protokol"), (p.ulohy, "Výpočetní okno")):
            m.addAction(t).triggered.connect(lambda _c=False, w=w: o.otevri(w))
        m.addSeparator()
        m.addAction("Srovnání ikon").triggered.connect(o.srovnej_ikony)
        m.addAction("Zavři aktivní okno").triggered.connect(o.zavri_aktivni)
        if p.isVisible():
            m.popup(QCursor.pos())
        return m


def postav_menu(page) -> PasGromy:
    pas = PasGromy(page)
    page.a_zpet = pas.akce.get("Soubor/Editace/Krok zpět")
    page.a_vpred = pas.akce.get("Soubor/Editace/Krok vpřed")
    return pas


def _ulohy():
    from ..geodezie.ulohy import ULOHY
    return ULOHY


def otevri_ulohu(page, i: int) -> None:
    """Výpočet z menu: otevře výpočetní okno s danou úlohou (zadání, Vypočítat, protokol)."""
    ul = page.ulohy
    if ul.hledat.text():
        ul.hledat.clear()
    ul.lst.setCurrentRow(i)
    page.tabs.otevri(ul)
