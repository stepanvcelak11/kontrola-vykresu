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
                               QMdiSubWindow, QMenu, QMenuBar, QPlainTextEdit, QWidget)

# Menu Výpočty v pořadí z Gromy (kap. 28) → názvy úloh v ULOHY; podnabídka = n-tice (titul, [úlohy])
MENU_VYPOCTY = [
    ("Polární metoda", "Rajón (polární bod)"),
    ("Ortogonální metoda", "Ortogonální metoda"),
    ("Volné stanovisko", "Volné stanovisko"),
    None,
    ("Protínání z délek", "Protínání z délek"),
    ("Protínání z orientovaných směrů", "Protínání vpřed ze směrů"),
    ("Protínání vpřed z úhlů", "Protínání vpřed z úhlů"),
    ("Protínání zpět", "Protínání zpět"),
    ("Průsečík přímek", "Průsečíky"),
    ("Bod na přímce", "Bod na přímce"),
    ("Kružnice ze tří bodů", "Kružnice ze tří bodů"),
    None,
    ("Polygonový pořad", ["Polygonový pořad", "Polygonový pořad uzavřený", "Polygonový pořad volný",
                          "Polygonový pořad jednostranně orientovaný", "Polygonový pořad vetknutý"]),
    ("Výškový pořad", ["Nivelační pořad", "Nivelační zápisník", "Vyrovnání nivelační sítě",
                       "Trigonometrická výška", "Trigonometrická výška oboustranně"]),
    ("Transformace souřadnic", "Transformace"),
    None,
    ("Směrník a délka", "Směrník a délka"),
    ("Úhel ze souřadnic", "Úhel ze souřadnic"),
    ("Kontrolní oměrné", "Kontrolní oměrné míry"),
    ("Výpočet výměr", ["Výměra a obvod", "Výměry parcel dávkou", "Výměra z měr", "Výkaz výměr GP",
                       "Oddělení parcely"]),
    ("Polární vytyčovací prvky", "Vytyčovací prvky"),
    ("Ortogonální vytyčovací prvky", ["Staničení a kolmice", "Bod ze staničení a kolmice"]),
    ("Rozložení oblouku", "Kružnicový oblouk"),
    ("Kubatury", "Model terénu a kubatura"),
    None,
    ("Testování přesnosti", ["Kontrola dvou určení", "Testování přesnosti ÚM – body",
                             "Testování přesnosti ÚM – délky"]),
]


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
        if not self._rozvrzeno:  # první zobrazení: viditelná okna vedle sebe (rozměr plochy už je známý)
            self._rozvrzeno = True
            self.mozaika_svisle()


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

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)
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


def postav_menu(page) -> QMenuBar:
    """Roletové menu Výpočtů s názvy z Gromy; položky volají existující funkce stránky."""
    mb = QMenuBar()
    mb.setNativeMenuBar(False)
    o = page.tabs
    ul = page.ulohy

    def akce(menu: QMenu, text: str, fn, zkratka: str | None = None):
        a = menu.addAction(text)
        a.triggered.connect(lambda _c=False: fn())
        if zkratka:
            a.setShortcut(zkratka)
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            page.addAction(a)
        return a

    m = mb.addMenu("&Soubor")
    akce(m, "Import seznamu souřadnic…", page.import_dialog)
    akce(m, "Export seznamu souřadnic…", page.export_dialog)
    akce(m, "Načíst z QTrig…", page.qtrig_dialog)
    m.addSeparator()
    akce(m, "Protokol do PDF…", ul.protokol_pdf)
    m.addSeparator()
    akce(m, "Nastavení…", lambda: (ul.nastaveni_vypoctu(), page.lista.nacti()))

    m = mb.addMenu("&Editace")
    page.a_zpet = akce(m, "Krok zpět", page.undo)
    page.a_vpred = akce(m, "Krok vpřed", page.redo)
    m.addSeparator()
    akce(m, "Vymaž", page.delete_selected)

    m = mb.addMenu("S&ouřadnice")
    akce(m, "Přidej položku…", page.add_point)
    akce(m, "Hromadné změny…", page.bulk_dialog)
    m.addSeparator()
    akce(m, "Zobrazit graficky", lambda: o.otevri(page.grafika))
    akce(m, "Porovnání souřadnic…", page.porovnat_seznam)
    akce(m, "Vyhledání identických bodů…", page.duplicates_dialog)
    m.addSeparator()
    akce(m, "Kresba z kódů…", page.kresba_z_kodu)
    akce(m, "Kódovací tabulka…", page.otevri_kodovnik)

    m = mb.addMenu("&Měření")
    akce(m, "Seznam měření (zápisník)", lambda: o.otevri(page.zapisnik))
    akce(m, "Zpracování zápisníku…", lambda: getattr(page.win, "show_vypocet", lambda: None)())

    m = mb.addMenu("&Výpočty")
    jmena = {n: i for i, (n, _p, _f, _fn) in enumerate(_ulohy())}
    pouzite: set[str] = set()

    def uloha(menu: QMenu, text: str, nazev: str):
        if nazev in jmena:
            pouzite.add(nazev)
            akce(menu, text + "…", lambda i=jmena[nazev]: otevri_ulohu(page, i))

    for polozka in MENU_VYPOCTY:
        if polozka is None:
            m.addSeparator()
            continue
        text, cil = polozka
        if isinstance(cil, list):
            sub = m.addMenu(text)
            for n in cil:
                uloha(sub, n, n)
        else:
            uloha(m, text, cil)
    zbytek = [n for n in jmena if n not in pouzite]
    if zbytek:
        sub = m.addMenu("Další výpočty")
        for n in zbytek:
            uloha(sub, n, n)
    page.menu_vypocty = m

    m = mb.addMenu("O&kno")
    for w, t in ((page.seznam_okno, "Seznam souřadnic"), (page.zapisnik, "Seznam měření"),
                 (page.grafika, "Grafika"), (page.protokol, "Protokol"), (page.ulohy, "Výpočetní okno")):
        akce(m, t, lambda w=w: o.otevri(w))
    m.addSeparator()
    akce(m, "Mozaika horizontálně", o.mozaika_vodorovne)
    akce(m, "Mozaika vertikálně", o.mozaika_svisle)
    akce(m, "Kaskáda", o.cascadeSubWindows)
    akce(m, "Srovnání ikon", o.srovnej_ikony)
    m.addSeparator()
    akce(m, "Zavři", o.zavri_aktivni)
    return mb


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
