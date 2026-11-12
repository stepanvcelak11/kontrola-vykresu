"""Nastavení aplikace na jednom místě: vzhled, kontrola výkresu, výpočty, CAD a aktualizace.

Dřív bylo nastavení rozházené (vzhled v nabídce Zobrazení, kontroly pod tlačítkem Nastavení, výpočty
v pásu Výpočtů, zkratky v CAD). Tohle okno je rozcestník: vzhled se mění hned, ostatní části otevřou
své podrobné nastavení."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from . import theme


def _radek(nazev: str, popis: str, ovladac: QWidget) -> QFrame:
    """Jedna volba: vlevo tučný název a šedý popis, vpravo ovládací prvek."""
    f = QFrame()
    f.setObjectName("radek_nastaveni")
    h = QHBoxLayout(f)
    h.setContentsMargins(14, 9, 14, 9)
    h.setSpacing(16)
    v = QVBoxLayout()
    v.setSpacing(1)
    n = QLabel(nazev)
    n.setObjectName("dlazdice_nazev")
    v.addWidget(n)
    if popis:
        p = QLabel(popis)
        p.setObjectName("dlazdice_popis")
        p.setWordWrap(True)
        v.addWidget(p)
    h.addLayout(v, 1)
    h.addWidget(ovladac, 0, Qt.AlignVCenter)
    return f


class NastaveniAplikace(QDialog):
    SEKCE = ("Vzhled", "Kontrola výkresu", "Výpočty", "CAD", "Aktualizace a nápověda")

    def __init__(self, win, sekce: str | None = None):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Nastavení")
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(0)
        lay.addWidget(theme.zahlavi_stranky("Nastavení", "Vzhled se mění hned. Ostatní části otevřou své "
                                                         "podrobné nastavení."))
        stred = QHBoxLayout()
        stred.setContentsMargins(12, 12, 12, 8)
        stred.setSpacing(12)
        self.seznam = QListWidget()
        self.seznam.setObjectName("navigace_nastaveni")
        self.seznam.setFixedWidth(200)
        self.seznam.addItems(list(self.SEKCE))
        from PySide6.QtCore import QSize
        vyska = self.fontMetrics().height() + 20
        for i in range(self.seznam.count()):
            self.seznam.item(i).setSizeHint(QSize(0, vyska))
        self.stack = QStackedWidget()
        for stavba in (self._vzhled, self._kontrola, self._vypocty, self._cad, self._aktualizace):
            self.stack.addWidget(self._stranka(stavba()))
        self.seznam.currentRowChanged.connect(self.stack.setCurrentIndex)
        stred.addWidget(self.seznam)
        stred.addWidget(self.stack, 1)
        lay.addLayout(stred, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.setContentsMargins(0, 0, 12, 0)
        lay.addWidget(bb)
        self.seznam.setCurrentRow(self.SEKCE.index(sekce) if sekce in self.SEKCE else 0)

    def _stranka(self, radky: list[QWidget]) -> QWidget:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(8)
        for r in radky:
            v.addWidget(r)
        v.addStretch(1)
        sc.setWidget(w)
        return sc

    @staticmethod
    def _tlacitko(text: str, fn, primarni: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setMinimumWidth(190)
        if primarni:
            b.setProperty("primarni", True)
        b.clicked.connect(lambda: fn())
        return b

    # ------------------------------------------------------------ vzhled
    def _vzhled(self) -> list[QWidget]:
        w = self.win
        self.rezim = QComboBox()
        self.rezim.addItems(["Světlý", "Tmavý"])
        self.rezim.setCurrentIndex(1 if theme.is_dark() else 0)
        self.rezim.activated.connect(self._nastav_rezim)
        self.barva = QComboBox()
        for k, (nazev, _h) in theme.ACCENTS.items():
            self.barva.addItem(nazev, k)
        self.barva.setCurrentIndex(max(0, self.barva.findData(theme.accent_name())))
        self.barva.activated.connect(lambda i: w.set_accent(self.barva.itemData(i)))
        self.pismo = QComboBox()
        for k, (nazev, _k) in theme.FONT_SCALES.items():
            self.pismo.addItem(nazev, k)
        self.pismo.setCurrentIndex(max(0, self.pismo.findData(theme.font_scale_name())))
        self.pismo.activated.connect(lambda i: w.set_font_scale(self.pismo.itemData(i)))
        for c in (self.rezim, self.barva, self.pismo):
            c.setMinimumWidth(190)
        from .rozcestnik import KLIC_PRI_STARTU
        st = QSettings("KontrolaVykresu", "KontrolaVykresu")
        self.start = QCheckBox("Zapnuto")
        self.start.setChecked(st.value(KLIC_PRI_STARTU, True, type=bool))
        self.start.toggled.connect(lambda on: self._start(on))
        self.svetle = QCheckBox("Zapnuto")
        self.svetle.setChecked(w.a_light.isChecked())
        self.svetle.toggled.connect(lambda on: w.a_light.trigger() if w.a_light.isChecked() != on else None)
        self.jako_ms = QCheckBox("Zapnuto")
        self.jako_ms.setChecked(w.a_mslook.isChecked())
        self.jako_ms.toggled.connect(lambda on: w.a_mslook.trigger() if w.a_mslook.isChecked() != on else None)
        return [
            _radek("Režim", "Světlá nebo tmavá okna aplikace (tmavý šetří oči večer).", self.rezim),
            _radek("Barva zvýraznění", "Barva hlavních tlačítek, vybraných položek a odkazů.", self.barva),
            _radek("Velikost písma", "Větší písmo pro malé displeje nebo horší zrak.", self.pismo),
            _radek("Rozcestník při spuštění", "Aplikace začne na stránce Start s výběrem projektu a programu.",
                   self.start),
            _radek("Světlé pozadí výkresu v kontrole", "Výkres na stránce Výkres na bílém pozadí místo černého.",
                   self.svetle),
            _radek("Čáry jako v MicroStationu", "Styly a tloušťky čar na stránce Výkres se kreslí jako "
                                                "v MicroStationu.", self.jako_ms),
        ]

    def _nastav_rezim(self, i: int) -> None:
        a = self.win.a_dark
        if a.isChecked() != bool(i):
            a.trigger()

    def _start(self, on: bool) -> None:
        from .rozcestnik import KLIC_PRI_STARTU
        QSettings("KontrolaVykresu", "KontrolaVykresu").setValue(KLIC_PRI_STARTU, bool(on))
        r = getattr(self.win, "rozcestnik", None)
        if r is not None and hasattr(r, "pri_startu") and r.pri_startu.isChecked() != on:
            r.pri_startu.setChecked(on)

    # ------------------------------------------------------------ kontrola výkresu
    def _kontrola(self) -> list[QWidget]:
        w = self.win
        return [
            _radek("Nastavení kontrol", "Tolerance, přesnost, rozsah výkresu, barevná tabulka a parametry "
                                        "jednotlivých kontrol (topologie, atributy, kartografie, geometrie).",
                   self._tlacitko("Nastavení kontrol…", w.edit_settings, True)),
            _radek("Co zkontrolovat", "Které kontroly se spouštějí a hotové sady (Jako učitel, Jen topologie…).",
                   self._tlacitko("Vybrat kontroly…", w.show_check_selection)),
            _radek("Zadání a pravidla", "Tabulka atributů, pokyny a pravidla, podle kterých se výkres hodnotí.",
                   self._tlacitko("Otevřít Zadání", lambda: (self.accept(), w.show_page("zadani")))),
        ]

    # ------------------------------------------------------------ výpočty
    def _vypocty(self) -> list[QWidget]:
        w = self.win

        def nastaveni(stranka=None):
            v = w.vypocty
            v.ulohy.nastaveni_vypoctu(stranka=stranka)
            v.lista.nacti()
        return [
            _radek("Nastavení výpočtů", "Prostředí, vstup a výstup, redukce délek, přístroj, protokol – jako "
                                        "nastavení v Gromě.", self._tlacitko("Nastavení výpočtů…", nastaveni, True)),
            _radek("Tolerance", "Mezní odchylky a kódy kvality pro výpočty.",
                   self._tlacitko("Tolerance…", lambda: nastaveni("Tolerance"))),
            _radek("Přístroj", "Přesnost teodolitu a dálkoměru pro vyrovnání a odhady přesnosti.",
                   self._tlacitko("Teodolit…", lambda: nastaveni("Teodolit"))),
        ]

    # ------------------------------------------------------------ CAD
    def _cad(self) -> list[QWidget]:
        c = self.win.cad
        return [
            _radek("Pracovní sada", "Bez sady, MultiScale (Účelová mapa), Pasport nebo TM – seed, hladiny, buňky "
                                    "a styly čar jako ve škole.", self._tlacitko("Pracovní sada…", c.pracovni_sada, True)),
            _radek("Knihovny od učitele", "Vlastní buňky (.cel) a styly čar (.rsc) pro všechny výkresy.",
                   self._tlacitko("Knihovny…", c.knihovny)),
            _radek("Klávesové zkratky", "Funkční klávesy pro nástroje a vlastní zkratky příkazového řádku.",
                   self._tlacitko("Zkratky…", c.nastav_zkratky)),
        ]

    # ------------------------------------------------------------ aktualizace a nápověda
    def _aktualizace(self) -> list[QWidget]:
        w = self.win
        self.auto = QCheckBox("Zapnuto")
        self.auto.setChecked(w.a_autoupdate.isChecked())
        self.auto.toggled.connect(lambda on: w.a_autoupdate.trigger() if w.a_autoupdate.isChecked() != on else None)
        return [
            _radek("Hledat aktualizace při spuštění", "Aplikace se po startu podívá, jestli je novější verze.",
                   self.auto),
            _radek("Aktualizace", "Zjistit hned, jestli je k dispozici novější verze.",
                   self._tlacitko("Zkontrolovat aktualizace", lambda: w.check_updates(manual=True))),
            _radek("Co je nového", "Přehled změn v posledních verzích.",
                   self._tlacitko("Co je nového…", lambda: w.show_news(force=True))),
            _radek("Co aplikace umí", "Přehled všech funkcí s odkazem přímo na ně.",
                   self._tlacitko("Přehled funkcí…", w.show_features)),
            _radek("Klávesové zkratky", "Zkratky hlavního okna a kontroly výkresu.",
                   self._tlacitko("Zkratky…", w.show_shortcuts)),
        ]
