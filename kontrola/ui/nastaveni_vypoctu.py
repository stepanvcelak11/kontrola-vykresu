"""Okno „Nastavení parametrů“ jako v Gromě 14: 13 stránek (Prostředí, Vstup/výstup, Výpočty, Tolerance, Redukce,
Záznamník, Teodolit, Kódování, Protokol, formáty souřadnic a měření, DXF, Aktualizace číselníků).

Volby, které ovlivňují výpočty (desetinná místa, měřítkový koeficient, mezní odchylky, přístroj, redukce délek,
zakázka a zpracovatel do hlavičky protokolu), jdou do sdíleného NastaveniVypoctu; ostatní se jen pamatují
(QSettings), aby okno vypadalo a chovalo se jako v Gromě."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..geodezie import nastaveni as N
from ..geodezie.vypocty import MXY_KOD_KVALITY

KLIC = "vypocty/nastaveni"
KLIC_GROMA = "vypocty/groma_parametry"

STRANKY = ["Prostředí", "Vstup/výstup", "Výpočty", "Tolerance", "Redukce", "Záznamník", "Teodolit", "Kódování",
           "Protokol", "Vst./výst. formát souřadnic", "Vst./výst. formát měření", "DXF", "Aktualizace číselníků"]

FORMATY_SOURADNIC = {
    "Geodimeter XY": "<NUM:10>\\t<Y:14:3>\\t<X:14:3>",
    "Geodimeter XYZ": "<NUM:10>\\t<Y:14:3>\\t<X:14:3>\\t<Z:14:3>",
    "XY Pevný s kódem": "<NUM:10> <X:14:3> <Y:14:3> <CODE>",
    "XY Volný s kódem": "<NUM> <X> <Y> <CODE>",
    "XYZ Pevný s kódem": "<NUM:10> <X:14:3> <Y:14:3> <Z:14:3> <CODE>",
    "XYZ Volný s kódem": "<NUM> <X> <Y> <Z> <CODE>",
    "YX Pevný s kódem": "<NUM:10> <Y:14:3> <X:14:3> <CODE>",
    "YX Volný s kódem": "<NUM> <Y> <X> <CODE>",
    "YXZ Pevný s kódem": "<NUM:10> <Y:14:3> <X:14:3> <Z:14:3> <CODE>",
    "YXZ Pevný s kódem - Tab": "<NUM:10>\\t<Y:14:3>\\t<X:14:3>\\t<Z:14:3>\\t<CODE>",
    "YXZ Volný s kódem": "<NUM> <Y> <X> <Z> <CODE>",
}
FORMATY_MERENI = {
    "Bez předčíslí": "<NUM:8> <HZ:10> <D:10> <DH:10> <SIG:8>",
    "S předčíslím": "<NUM:10> <HZ:10> <D:10> <DH:10> <SIG:8>",
    "Sdílený s předčíslím": "<NUM:12> <HZ:10> <D:10> <DH:10> <SIG:8>",
}
TOLERANCE = {  # uživatelské tolerance Gromy (min. úhel, orientace, polygon, transformace)
    "1 - Velmi přesné měření": ("30.0000", "0.0100", "0.001*SQRT(s) + 0.02", "0.00*SQRT(s) + 0.05",
                                "0.000*SQRT(s) + 0.030", "40.00*SQRT(n + 0.00)", "", "0.07", ""),
    "2 - Přesné měření": ("25.0000", "0.0150", "0.0015*SQRT(s) + 0.03", "0.00*SQRT(s) + 0.07",
                          "0.000*SQRT(s) + 0.045", "70.00*SQRT(n + 0.00)", "", "0.10", ""),
    "3 - Standardní měření": ("20.0000", "0.0200", "0.002*SQRT(s) + 0.04", "0.00*SQRT(s) + 0.10",
                              "0.000*SQRT(s) + 0.060", "100.00*SQRT(n + 0.00)", "", "0.14", ""),
    "Netestovat": ("", "", "", "", "", "", "", "", ""),
}

def _styl() -> str:
    """Záložky vlevo a kompaktní skupiny – barvy z tématu aplikace (světlý i tmavý vzhled)."""
    from .theme import BORDER, BORDER_STRONG, HEADER, HOVER, MUTED, PANEL, TEXT, accent, themed
    t = themed
    return f"""
QListWidget#zalozky {{ background: transparent; border: none; outline: 0; }}
QListWidget#zalozky::item {{ background: {t(HEADER)}; border: 1px solid {t(BORDER)}; border-right: none;
    margin: 0 0 2px 0; padding: 5px 8px; color: {t(MUTED)}; border-radius: 0; }}
QListWidget#zalozky::item:hover {{ background: {t(HOVER)}; color: {t(TEXT)}; }}
QListWidget#zalozky::item:selected {{ background: {t(PANEL)}; color: {t(TEXT)}; border-left: 3px solid {accent()}; }}
QStackedWidget#stranky {{ background: {t(PANEL)}; border: 1px solid {t(BORDER_STRONG)}; }}
QStackedWidget#stranky QGroupBox {{ margin-top: 16px; padding: 8px 8px 6px 8px; border-radius: 6px; }}
QStackedWidget#stranky QGroupBox::title {{ top: 1px; }}
"""


def _tint(nazev: str) -> str:
    """Barevné podbarvení polí jako v Gromě (žlutá, zelená, modrá, fialová) – v tmavém vzhledu tlumené."""
    from .theme import is_dark
    sv = {"zluta": "#FFF6CC", "zelena": "#D7F5D0", "modra": "#E6F0FB", "fialova": "#EFE3FB"}
    tm = {"zluta": "#3A3214", "zelena": "#18351E", "modra": "#16283D", "fialova": "#2C2140"}
    return f"background: {(tm if is_dark() else sv)[nazev]};"



def nacti() -> N.NastaveniVypoctu:
    """Z QSettings do sdíleného nastavení úloh (volá se při startu Výpočtů)."""
    try:
        d = json.loads(QSettings().value(KLIC, "") or "{}")
    except (TypeError, ValueError):
        d = {}
    n = N.NastaveniVypoctu.z_dict(d)
    N.nastav(n)
    return n


def uloz(n: N.NastaveniVypoctu) -> None:
    N.nastav(n)
    QSettings().setValue(KLIC, json.dumps(n.do_dict(), ensure_ascii=False))


def groma_parametry() -> dict:
    try:
        return dict(json.loads(QSettings().value(KLIC_GROMA, "") or "{}"))
    except (TypeError, ValueError):
        return {}


def _cislo(v, lo, hi, dec, suf=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(v)
    s.setButtonSymbols(QDoubleSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight)
    if suf:
        s.setSuffix(suf)
    return s


def _skupina(titulek, *prvky) -> QGroupBox:
    g = QGroupBox(titulek)
    v = QVBoxLayout(g)
    v.setSpacing(2)
    for p in prvky:
        if isinstance(p, QWidget):
            v.addWidget(p)
        else:
            v.addLayout(p)
    return g


def _formular(*radky) -> QFormLayout:
    f = QFormLayout()
    f.setLabelAlignment(Qt.AlignRight)
    for t, w in radky:
        f.addRow(t, w)
    return f


class NastaveniVypoctuDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nastavení parametrů")
        self.setStyleSheet(_styl())
        self.resize(800, 660)
        self._n = N.aktualni()
        self._ulozene = groma_parametry()
        self._prvky: dict[str, QWidget] = {}
        lay = QVBoxLayout(self)
        h = QHBoxLayout()
        h.setSpacing(0)
        self.zalozky = QListWidget()
        self.zalozky.setObjectName("zalozky")
        self.zalozky.addItems(STRANKY)
        self.zalozky.setFixedWidth(205)
        self.zalozky.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        from PySide6.QtCore import QSize
        for i in range(self.zalozky.count()):
            self.zalozky.item(i).setSizeHint(QSize(195, 31))
        self.zalozky.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        h.addWidget(self.zalozky)
        self.stranky = QStackedWidget()
        self.stranky.setObjectName("stranky")
        h.addWidget(self.stranky, 1)
        lay.addLayout(h, 1)
        for tvor in (self._prostredi, self._vstup_vystup, self._vypocty, self._tolerance, self._redukce,
                     self._zaznamnik, self._teodolit, self._kodovani, self._protokol, self._format_souradnic,
                     self._format_mereni, self._dxf, self._ciselniky):
            w = QWidget()
            v = QVBoxLayout(w)
            tvor(v)
            v.addStretch(1)
            self.stranky.addWidget(w)
        self.zalozky.currentRowChanged.connect(self.stranky.setCurrentIndex)
        self.zalozky.setCurrentRow(0)
        row = QHBoxLayout()
        row.addStretch(1)
        self.b_ok = QPushButton("Ok")
        self.b_ok.setDefault(True)
        self.b_ok.setMinimumWidth(110)
        self.b_ok.clicked.connect(self._ok)
        row.addWidget(self.b_ok)
        lay.addLayout(row)
        self.ucel.toggled.connect(self._povol)
        for w in (self.m_rezim, self.v_rezim):
            w.currentIndexChanged.connect(self._povol)
        self._povol()

    # ------------------------------------------------------------ pomocníci (pamatované volby)
    def _reg(self, klic: str, w: QWidget, vychozi=None):
        self._prvky[klic] = w
        v = self._ulozene.get(klic, vychozi)
        if v is not None:
            if isinstance(w, QAbstractButton):
                w.setChecked(bool(v))
            elif isinstance(w, QLineEdit):
                w.setText(str(v))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(str(v))
        return w

    def _ch(self, klic, text, vychozi=False) -> QCheckBox:
        return self._reg(klic, QCheckBox(text), vychozi)

    def _ed(self, klic, vychozi="", sirka=None) -> QLineEdit:
        e = self._reg(klic, QLineEdit(), vychozi)
        if sirka:
            e.setFixedWidth(sirka)
        return e

    def _cb(self, klic, polozky, vychozi="") -> QComboBox:
        c = QComboBox()
        c.addItems(polozky)
        return self._reg(klic, c, vychozi)

    def _radia(self, klic, texty, vychozi=0) -> list[QRadioButton]:
        g = QButtonGroup(self)
        out = []
        for i, t in enumerate(texty):
            r = QRadioButton(t)
            g.addButton(r)
            out.append(self._reg(f"{klic}:{i}", r, i == vychozi))
        if not any(r.isChecked() for r in out):
            out[vychozi].setChecked(True)
        return out

    # ------------------------------------------------------------ stránky
    def _prostredi(self, v):
        g = QGridLayout()
        g.addWidget(_skupina("Řazení:", *self._radia("razeni", ["Neřadit (dle pořadí vložení)", "Předčíslí",
                                                                "Číslo"]),
                             self._ch("zvyraznene_napred", "Zvýrazněné napřed")), 0, 0)
        g.addWidget(_skupina("Pořadí souřadnic:", *self._radia("poradi", ["X - Y", "Y - X"], 1)), 0, 1)
        g.addWidget(_skupina("Souřadnicová soustava:", *self._radia("soustava", ["1. kvadrant   (Gauss - Krüger)",
                                                                                 "3. kvadrant   (Křovák)"], 1)), 0, 2)
        g.addWidget(_skupina("Seznamy:", self._ch("duplicitni", "Povolit duplicitní body v seznamu souřadnic"),
                             self._ch("oznacovani_win", "Označování položek v seznamech dle Windows"),
                             self._ch("rychle_zamykani", "Rychlé zamykání/odemykání bodů myší", True),
                             self._ch("zvyraznit_aktivni", "Zvýraznit aktivní seznam souřadnic", True),
                             self._ch("zvyraznit_plochu", "   Zvýraznit celou plochu aktivního seznamu"),
                             self._ch("sobr_spol", "Zvýraznit body s odlišným SOBR a SPOL", True),
                             QPushButton("Font pro seznamy ...")), 1, 0, 1, 2)
        g.addWidget(_skupina("Nastavení internetu:", self._ch("info_net", "Stahovat informace z internetu", True),
                             self._ch("akt_net", "Stahovat aktualizace z internetu", True),
                             QLabel("Nastavení proxy serveru:"),
                             *self._radia("proxy", ["Bez použití proxy", "Dle nastavení Windows",
                                                    "Adresa a port serveru:"]), self._ed("proxy_adresa")), 1, 2)
        g.addWidget(_skupina("Vyhledávání bodů:", self._ch("hledat_predcisli", "Hledat podle předčíslí", True),
                             self._ch("hledat_vsude", "Hledat ve všech otevřených souborech", True)), 2, 0, 1, 2)
        g.addWidget(_skupina("Další volby:", self._ch("kontrolni_kresba", "Automaticky otevřít kontrolní kresbu"),
                             self._ch("kresba_v_planu", "Zobrazovat kontrolní kresbu i v plánu"),
                             self._ch("bublinova", "Zobrazovat bublinovou nápovědu", True)), 2, 2)
        v.addLayout(g)
        zs = QGridLayout()
        for i, t in enumerate(("Seznam souřadnic:", "Polární měření:", "Ortogonální měření:", "Nivelace:")):
            zs.addWidget(QLabel(t), i, 0)
            zs.addWidget(self._ed(f"zakladaci:{i}"), i, 1)
            zs.addWidget(QPushButton("..."), i, 2)
        v.addWidget(_skupina("Zakládací soubory:", zs))
        self.zpracovatel = QLineEdit(self._n.zpracovatel)
        v.addWidget(_skupina("Informace o instalaci:", _formular(("Název uživatele:", self.zpracovatel))))
        g2 = QGridLayout()
        g2.addWidget(_skupina("Formát nově zakládaných datových souborů:",
                              *self._radia("format_novych", ["Nový formát (.crds, .mess)",
                                                             "Starý formát (.crd, .mes)"], 1)), 0, 0)
        g2.addWidget(_skupina("Vzhled aplikace:", *self._radia("vzhled", ["Nový vzhled (pás karet)",
                                                                          "Starý vzhled (roletové menu)"])), 0, 1)
        g2.addWidget(_skupina("Umístění výpočetních oken:",
                              *self._radia("umisteni", ["Pravý spodní roh obrazovky",
                                                        "Pravý spodní roh hlavního okna aplikace"])), 1, 0)
        g2.addWidget(_skupina("Zálohování:", self._ch("zalohy", "Vytvářet záložní soubory při otevření")), 1, 1)
        v.addLayout(g2)

    def _vstup_vystup(self, v):
        g = QGridLayout()
        self.desetiny = QSpinBox()
        self.desetiny.setRange(0, 4)
        self.desetiny.setValue(self._n.desetiny)
        self.desetiny.setButtonSymbols(QSpinBox.NoButtons)
        self.desetiny.setFixedWidth(34)
        g.addWidget(_skupina("Počet desetinných míst:", _formular(
            ("Souřadnice:", self.desetiny), ("Výšky:", self._ed("des_vysky", "3", 34)),
            ("Délky:", self._ed("des_delky", "3", 34)), ("Úhly:", self._ed("des_uhly", "4", 34)),
            ("Plochy:", self._ed("des_plochy", "0", 34)), ("Objemy:", self._ed("des_objemy", "1", 34)))), 0, 0)
        g.addWidget(_skupina("Zobrazování čísel bodů:", self._ch("uplna_cisla", "Úplná čísla v seznamech", True),
                             self._ch("doplnit_nuly", "Čísla doplnit nulami", True),
                             self._ch("pomlcka", "Oddělit předčíslí pomlčkou"),
                             self._ch("rozdelit", "Rozdělit předčíslí na části"),
                             self._ch("bez_ku", "Nezobrazovat číslo k.ú."),
                             self._ch("redukovat_pc", "Redukovat předčíslí"),
                             self._ch("zpmz_vzdy", "   ZPMZ zobrazovat vždy"),
                             self._ch("alfanum", "Čísla vždy alfanumerická")), 0, 1)
        self.m_rezim = QComboBox()
        self.m_rezim.addItems(list(N.REZIMY_MERITKA))
        self.m_rezim.setCurrentText(self._n.meritko_rezim)
        self.m_rucne = _cislo(self._n.meritko_rucne, 0.9, 1.1, 14)
        self.m_rucne.setAlignment(Qt.AlignLeft)
        g.addWidget(_skupina("Měřítkový koeficient:", QLabel("Měřítkový koeficient"), self.m_rucne,
                             QLabel("Použít:"), self.m_rezim), 0, 2)
        g.addWidget(_skupina("Délkové jednotky:", *self._radia("delk_jedn", ["Metry", "Stopy"])), 1, 0)
        g.addWidget(_skupina("Úhlové jednotky:", *self._radia("uhl_jedn", ["Grády", "Stupně minuty vteřiny",
                                                                           "Stupně desetinné", "Radiány"])), 1, 1)
        g.addWidget(_skupina("Zeměpisné souřadnice:",
                             *self._radia("zem", ["Stupně minuty vteřiny", "Stupně desetinné",
                                                  "Stupně m. v. s mezerami"]),
                             _formular(("Počet číslic:", self._ed("zem_cislic", "8", 34)))), 1, 2)
        v.addLayout(g)
        v.addWidget(_skupina("Ukládání bodů do seznamů souřadnic:",
                             self._ch("prenaset_ms", "Body automaticky přenášet do řídící aplikace (MicroStation, ...)"),
                             self._ch("zaokrouhlovat", "Zaokrouhlovat souřadnice dle nastaveného počtu desetinných "
                                                       "míst"),
                             self._ch("tridit_kk", "V seznamu souřadnic s dvojími souřadnicemi třídit ukládané souř. "
                                                   "dle kódu kvality")))
        g2 = QGridLayout()
        g2.addWidget(_skupina("Přenos bodů do databáze:",
                              self._ch("db_dup_sour", "Kontrolovat duplicitní souřadnice", True),
                              self._ch("db_dup_cisla", "Kontrolovat duplicitní čísla bodů", True),
                              self._ch("db_katuzemer", "Automaticky doplnit KATUZEMER a ZPMZ_MER", True)), 0, 0)
        g2.addWidget(_skupina("Export do záznamníků:", self._ch("exp_pc", "Včetně předčíslí"),
                              self._ch("exp_vysky", "Včetně výšek", True), self._ch("exp_kody", "Včetně kódů"),
                              self._ch("exp_red", "Redukovat souřadnice")), 0, 1)
        v.addLayout(g2)
        v.addWidget(_skupina("Přenos bodů do MicroStation:",
                             self._ch("ms_info", "Po dávkovém přenosu zobrazit informaci o počtu bodů")))

    def _vypocty(self, v):
        g = QGridLayout()
        g.addWidget(_skupina("Dávkový výpočet:", self._ch("jen_oznacene", "Použít pouze označené hodnoty"),
                             self._ch("edit_orient", "Editovat orientace", True),
                             self._ch("davka_polar", "Počítat polární metodu", True),
                             self._ch("davka_volna", "Počítat volná stanoviska", True),
                             self._ch("davka_protinani", "Počítat protínání ze směrů", True),
                             self._ch("zaokr_vstup", "Zaokrouhlovat vstupní hodnoty", True),
                             _formular(("Nepočítat výšky u bodů s kódem:", self._ed("bez_vysky_kod", "", 50)))), 0, 0)
        g.addWidget(_skupina("Váhy směrů při orientaci osnov:", *self._radia("vahy_smeru", ["1", "s/1000"]),
                             self._ed("vahy_smeru_vzorec", "1")), 0, 1)
        g.addWidget(_skupina("Volné stanovisko:", self._ch("dopocet_delek", "Dopočítat neznámé délky", True),
                             _formular(("Způsob vyrovnání:", self._cb("vyrovnani", [
                                 "Podobnostní transformace", "Shodnostní transformace", "MNČ"],
                                 "Podobnostní transformace")))), 1, 0)
        g.addWidget(_skupina("Váhy převýšení:", *self._radia("vahy_prev", ["1", "1/s", "1/s^2"], 2),
                             self._ed("vahy_prev_vzorec", "1/(S*S)")), 1, 1)
        g.addWidget(_skupina("Nabízet jako orientace:",
                             *self._radia("orientace", ["Všechny body o známých souřadnicích",
                                                        "Body s atributem Orientace"])), 2, 0)
        g.addWidget(_skupina("Různé:", self._ch("zpetna", "Provádět zpětnou kontrolu výpočtů"),
                             self._ch("dotaz_zavreni", "Dotázat se před uzavřením neuloženého výpočetního okna",
                                      True)), 3, 0)
        v.addLayout(g)

    def _tolerance(self, v):
        self.ucel = QCheckBox("Testovat mezní odchylky dle předpisů pro práci v katastru nemovitostí")
        self.ucel.setChecked(self._n.ucel == "katastr")
        self.kod = QComboBox()
        self.kod.addItems([str(k) for k in sorted(MXY_KOD_KVALITY)])
        self.kod.setCurrentText(str(self._n.kod_kvality))
        self.trida = QSpinBox()
        self.trida.setRange(1, 5)
        self.trida.setValue(self._n.trida_presnosti)
        h = QHBoxLayout()
        h.addWidget(self.ucel, 1)
        h.addWidget(QPushButton("Předpisy ..."))
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Kód kvality:"))
        h2.addWidget(self.kod)
        h2.addSpacing(16)
        h2.addWidget(QLabel("Jinak třída přesnosti (ČSN 01 3410):"))
        h2.addWidget(self.trida)
        h2.addStretch(1)
        v.addWidget(_skupina("Mezní odchylky pro práci v katastru nemovitostí:", h, h2))
        u = QGridLayout()
        lv = QVBoxLayout()
        lv.addWidget(QLabel("Název:"))
        self.tol_nazev = self._ed("tol_nazev", "3 - Standardní měření")
        lv.addWidget(self.tol_nazev)
        self.tol_seznam = QListWidget()
        self.tol_seznam.addItems(list(TOLERANCE))
        lv.addWidget(self.tol_seznam, 1)
        b = QGridLayout()
        b.addWidget(QPushButton("Uložit"), 0, 0)
        b.addWidget(QPushButton("Odebrat"), 0, 1)
        b.addWidget(QPushButton("Zapsat do protokolu"), 1, 0, 1, 2)
        lv.addLayout(b)
        u.addLayout(lv, 0, 0)
        self.tol_pole = [QLineEdit() for _ in range(9)]
        pv = QVBoxLayout()
        pv.addWidget(_skupina("Jednotlivé výpočty:", _formular(
            ("Minimální úhel protnutí\nu průsečíku a protínání:", self.tol_pole[0]))))
        pv.addWidget(_skupina("Orientace osnov:", _formular(
            ("Max. oprava orientace:", self.tol_pole[1]), ("Maximální oprava or. délky:", self.tol_pole[2]),
            ("Maximální oprava or. převýšení:", self.tol_pole[3]))))
        self.p_trida = QComboBox()
        self.p_trida.addItems(["1: úhlová 25·√(n+2) mgon, polohová 0,0025·√Σs + 0,04 m",
                               "2: úhlová 100·√(n+3) mgon, polohová 0,005·√Σs + 0,04 m"])
        self.p_trida.setCurrentIndex(1 if self._n.polygon_trida == 2 else 0)
        pv.addWidget(_skupina("Polygonové pořady:", _formular(
            ("Rozdíl v dvakrát měřené délce:", self.tol_pole[4]), ("Úhlový uzávěr [cc]:", self.tol_pole[5]),
            ("Polohová odchylka:", self.tol_pole[6]), ("Mezní odchylky (katastr):", self.p_trida))))
        pv.addWidget(_skupina("Transformace souřadnic:", _formular(
            ("Maximální střední chyba transformačního klíče:", self.tol_pole[7]),
            ("Mezní změna měřítka: 1 ±", self.tol_pole[8]))))
        u.addLayout(pv, 0, 1)
        v.addWidget(_skupina("Uživatelské tolerance:", u))
        self.tol_seznam.currentTextChanged.connect(self._vyber_toleranci)
        i = self.tol_seznam.findItems(self.tol_nazev.text(), Qt.MatchExactly)
        self.tol_seznam.setCurrentItem(i[0] if i else self.tol_seznam.item(2))

    def _vyber_toleranci(self, nazev: str):
        if nazev in TOLERANCE:
            self.tol_nazev.setText(nazev)
            for e, t in zip(self.tol_pole, TOLERANCE[nazev]):
                e.setText(t)

    def _redukce(self, v):
        g = QGridLayout()
        pc = self._ed("red_predcisli")
        pc.setStyleSheet(_tint("zluta"))
        ry, rx, rz = self._ed("red_y"), self._ed("red_x"), self._ed("red_z")
        for e in (ry, rx, rz):
            e.setStyleSheet(_tint("zelena"))
        g.addWidget(_skupina("Redukce:", _formular(("Předčíslí:", pc)),
                             self._ch("red_doplnovat", "Doplňovat části předčíslí"),
                             _formular(("Redukce Y:", ry), ("Redukce X:", rx), ("Redukce Z:", rz))), 0, 0)
        g.addWidget(_skupina("Přičítání redukce:", *self._radia("pricitani", ["Inteligentní", "Vždy", "Nikdy"])),
                    0, 1, Qt.AlignTop)
        g.addWidget(_skupina("Charakteristiky bodů:", _formular(
            ("Kvalita:", self._cb("kvalita", ["", "1", "2", "3", "4", "5", "6", "7", "8"])),
            ("Typ:", self._cb("typ_bodu", ["", "trvale stabilizovaný", "dočasně stabilizovaný", "podrobný"])),
            ("Pořízení:", self._ed("porizeni", "", 30)))), 1, 0)
        v.addLayout(g)
        self.v_rezim = QComboBox()
        self.v_rezim.addItems(list(N.REZIMY_VYSKY))
        self.v_rezim.setCurrentText(self._n.vyska_rezim)
        self.vyska = _cislo(self._n.vyska, -500, 9000, 1, " m")
        self.ppm = _cislo(self._n.ppm_fyzikalni, -500, 500, 1, " ppm")
        self.info = QLabel()
        self.info.setWordWrap(True)
        v.addWidget(_skupina("Redukce měřených délek do S-JTSK:", _formular(
            ("Redukce z nadmořské výšky:", self.v_rezim), ("Nadmořská výška:", self.vyska),
            ("Fyzikální korekce:", self.ppm)), self.info))

    def _zaznamnik(self, v):
        g = QGridLayout()
        g.addWidget(_skupina("Záznamník:", QLabel("Maska datových souborů (*.ext):"), self._ed("maska"),
                             QLabel("Ve formátu MAPA2\nvynechat řádků v hlavičce:"), self._ed("mapa2", "7")), 0, 0)
        g.addWidget(_skupina("Souřadnice:", _formular(
            ("Koeficient X:", self._ed("koef_x", "1.000000000000")),
            ("Koeficient Y:", self._ed("koef_y", "1.000000000000")),
            ("Koeficient Z:", self._ed("koef_z", "1.000000000000"))), self._ch("zamenit_xy", "Zaměnit X a Y")), 1, 0)
        vc = self._ed("vyska_cile")
        vc.setStyleSheet(_tint("fialova"))
        g.addWidget(_skupina("Volby výšek:", self._ch("nulove_vc", "Nulové výšky cíle", True),
                             _formular(("Standardní výška cíle:", vc))), 2, 0)
        g.addWidget(_skupina("Typ délek:", *self._radia("typ_delek", ["Vodorovné", "Šikmé"], 1),
                             self._ch("neredukovat", "Neredukovat"),
                             QLabel("Vzorec pro redukci na vodorovnou:"), self._ed("vzorec_red"),
                             *self._radia("prepocet", ["Standardní přepočet (2)", "Tachymetrická (1)",
                                                       "Tachymetrická Redta (3)", "Dimess (4)", "Dimess (5)"])),
                    0, 1, 2, 1)
        g.addWidget(_skupina("Úhlové jednotky:", *self._radia("zazn_uhly", ["Grády", "Stupně minuty vteřiny",
                                                                            "Stupně desetinné", "Radiány"])), 2, 1)
        g.addWidget(_skupina("Kontroly:", QLabel("Podmínka pro test výšky cíle:"),
                             self._ed("podminka_vc", "(SIGNAL > 0.5) & (SIGNAL < 3)")), 3, 1)
        v.addLayout(g)

    def _teodolit(self, v):
        g = QGridLayout()
        self.pristroj = QLineEdit(self._n.pristroj)
        sez = QListWidget()
        sez.addItem(self._n.pristroj)
        sez.setMaximumHeight(90)
        b = QHBoxLayout()
        b.addWidget(QPushButton("Uložit"))
        b.addWidget(QPushButton("Odebrat"))
        g.addWidget(_skupina("Teodolit:", QLabel("Název:"), self.pristroj, sez, b), 0, 0, 2, 1, Qt.AlignTop)
        modra, fial = _tint("modra"), _tint("fialova")

        def pole(k, d, styl):
            e = self._ed(k, d, 70)
            e.setAlignment(Qt.AlignRight)
            e.setStyleSheet(styl)
            return e
        g.addWidget(_skupina("Kolimační chyba:", _formular(("Nastavená hodnota:", pole("kol", "0.0000", modra))),
                             QLabel("Rozdíl od nast. hodnoty:"),
                             _formular(("Podezřelé:", pole("kol_p", "0.0100", modra)),
                                       ("Chybné:", pole("kol_ch", "0.0500", modra)))), 0, 1)
        g.addWidget(_skupina("Indexová chyba:", _formular(("Nastavená hodnota:", pole("idx", "0.0116", fial))),
                             QLabel("Rozdíl od nast. hodnoty:"),
                             _formular(("Podezřelé:", pole("idx_p", "0.0200", fial)),
                                       ("Chybné:", pole("idx_ch", "0.0500", fial)))), 0, 2)
        g.addWidget(_skupina("Mezní oprava délky:", _formular(
            ("Podezřelé:", pole("md_p", "0.100", modra)), ("Chybné:", pole("md_ch", "0.200", modra)))), 1, 1)
        g.addWidget(_skupina("Mezní oprava převýšení:", _formular(
            ("Podezřelé:", pole("mp_p", "0.100", fial)), ("Chybné:", pole("mp_ch", "0.200", fial)))), 1, 2)
        self.s_smer = _cislo(self._n.sigma_smer_mgon, 0, 100, 4, " mgon")
        self.s_a = _cislo(self._n.sigma_delka_mm, 0, 100, 1, " mm")
        self.s_b = _cislo(self._n.sigma_delka_ppm, 0, 100, 1, " ppm")
        d = QHBoxLayout()
        d.addWidget(self.s_a)
        d.addWidget(QLabel("+"))
        d.addWidget(self.s_b)
        g.addWidget(_skupina("Střední chyby:", _formular(("Směr:", self.s_smer), ("Délka:", d))), 2, 1)
        v.addLayout(g)

    def _kodovani(self, v):
        g = QGridLayout()
        for i, (t, k) in enumerate((("Kódovací tabulka:", "kod_tab"), ("Tabulka typů:", "typ_tab"))):
            b = QHBoxLayout()
            for x in ("Připojit ...", "Odpojit", "Editovat ..."):
                b.addWidget(QPushButton(x))
            g.addWidget(_skupina(t, self._ed(k), b, self._ch(k + "_pouzit", "Použít tabulku")), 0, i)
        g.addWidget(_skupina("Nastavení pro import:", self._ch("kody_casti", "Rozdělit kódy na části"),
                             self._ch("prekodovat", "Překódovat při importu"),
                             self._ch("bez_kodu", "Akceptovat body bez kódu", True),
                             _formular(("Počet znaků:", self._ed("kod_znaku", "0")),
                                       ("Oddělovače kódů:", self._ed("kod_oddel", ",")),
                                       ("Kód orientace:", self._ed("kod_orient")))), 1, 0)
        styp = QLabel("Standard")
        styp.setObjectName("stranka_info")
        g.addWidget(_skupina("Kódování kresby:", QLabel("Typ kódování:"), styp, QPushButton("Nastavení ...")),
                    1, 1, Qt.AlignTop)
        v.addLayout(g)

    def _protokol(self, v):
        self.zakazka = QLineEdit(self._n.zakazka)
        v.addWidget(_skupina("Volby:", self._ch("vytvaret", "Vytvářet protokol", True),
                             self._ch("auto_zapis", "Automaticky zapisovat protokol", True),
                             self._ch("vstupni_body", "Zapisovat souřadnice vstupních bodů", True),
                             self._ch("davka_body", "Zapisovat vypočtené body v dávce", True),
                             self._ch("bez_z", "Neprotokolovat souřadnici Z", True),
                             self._ch("ku_pomlcka", "Oddělit číslo k.ú. pomlčkou"),
                             self._ch("bez_cesty", "Zapisovat názvy souborů bez cesty")))
        h = QHBoxLayout()
        h.addWidget(QPushButton("Font na obrazovku ..."))
        h.addWidget(QPushButton("Font pro tisk..."))
        h.addStretch(1)
        v.addLayout(h)
        v.addWidget(_skupina("Hlavička protokolu:", _formular(("Zakázka:", self.zakazka))))

    def _format(self, v, klic, formaty, vychozi, volby):
        g = QGridLayout()
        lv = QVBoxLayout()
        lv.addWidget(QLabel("Název:"))
        nazev = self._ed(klic + "_nazev", vychozi)
        lv.addWidget(nazev)
        sez = QListWidget()
        sez.addItems(list(formaty))
        lv.addWidget(sez, 1)
        lv.addWidget(QLabel("Aktivní formát:"))
        akt = QLabel(f"<b>{nazev.text()}</b>")
        lv.addWidget(akt)
        g.addWidget(_skupina("Formát:", lv), 0, 0)
        pred = self._reg(klic + "_predpis", QPlainTextEdit(), formaty.get(vychozi, ""))
        pred.setObjectName("vypis")
        b = QHBoxLayout()
        for x in ("Uložit", "Odebrat", "Vytvořit kopii"):
            b.addWidget(QPushButton(x))
        b.addStretch(1)
        g.addWidget(_skupina("Předpis formátu:", pred, _skupina("Volby:", *volby), b), 0, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)

        def vyber(t):
            if t in formaty:
                nazev.setText(t)
                pred.setPlainText(formaty[t])
                akt.setText(f"<b>{t}</b>")
        sez.currentTextChanged.connect(vyber)
        return sez

    def _format_souradnic(self, v):
        self.formaty_souradnic = self._format(
            v, "fsour", FORMATY_SOURADNIC, "YXZ Pevný s kódem - Tab",
            [self._ch("fs_volny", "Volný formát"), self._ch("fs_nuly", "Nedefinované nahradit nulami", True),
             self._ch("fs_red", "Redukovat souřadnice při výstupu"), self._ch("fs_radky", "Oddělit řády"),
             self._ch("fs_carka", "Čárka jako oddělovač des. části")])

    def _format_mereni(self, v):
        self.formaty_mereni = self._format(v, "fmer", FORMATY_MERENI, "S předčíslím",
                                           [self._ch("fm_nuly", "Nedefinované nahradit nulami")])

    def _dxf(self, v):
        g = QGridLayout()
        g.addWidget(self._ch("dxf_hlavicka", "Hlavička", True), 0, 0)
        g.addWidget(self._ch("dxf_zamenit", "Zaměnit X a Y", True), 1, 0)
        g.addWidget(self._ch("dxf_3d", "3D", True), 2, 0)
        g.addWidget(self._ch("dxf_red", "Redukovat"), 3, 0)
        for i, (t, d) in enumerate((("Koeficient X:", "-1.00000000"), ("Koeficient Y:", "-1.00000000"),
                                    ("Koeficient Z:", "1.00000000"))):
            g.addWidget(QLabel(t), i, 1, Qt.AlignRight)
            g.addWidget(self._ed(f"dxf_k{i}", d), i, 2)
        v.addWidget(_skupina("Volby:", g))
        v.addWidget(_skupina("Vrstvy:", _formular(
            ("Vrstva pro body:", self._ed("dxf_v_body", "1")), ("Vrstva pro čísla bodů:", self._ed("dxf_v_cisla", "2")),
            ("Vrstva pro výšky:", self._ed("dxf_v_vysky", "3")),
            ("Vrstva pro popisy:", self._ed("dxf_v_popisy", "5")))))
        t = QGridLayout()
        t.addWidget(QLabel("Výška textu:"), 0, 0)
        vt = QHBoxLayout()
        vt.addWidget(self._ed("dxf_vyska_textu", "2.00", 40))
        vt.addWidget(QLabel("m"))
        t.addLayout(vt, 1, 0)
        for i, (x, d) in enumerate((("Font pro čísla bodů:", ""), ("Font pro výšky:", ""),
                                    ("Font pro popisy:", "PNTCODE"))):
            t.addWidget(QLabel(x), i, 1, Qt.AlignRight)
            t.addWidget(self._ed(f"dxf_font{i}", d), i, 2)
        v.addWidget(_skupina("Texty:", t))

    def _ciselniky(self, v):
        h = QHBoxLayout()
        h.addWidget(QLabel("Poslední aktualizace:"))
        self.datum_ciselniku = QLabel("<b>" + str(self._ulozene.get("ciselniky", "–")) + "</b>")
        h.addWidget(self.datum_ciselniku)
        h.addStretch(1)
        b = QPushButton("Aktualizovat")
        b.setToolTip("Číselník katastrálních území je součástí aplikace (aktualizuje se s novou verzí).")

        def akt():
            from datetime import datetime
            t = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            self._ulozene["ciselniky"] = t
            self.datum_ciselniku.setText(f"<b>{t}</b>")
        b.clicked.connect(akt)
        v.addWidget(_skupina("Číselníky katastrálních území:", h, b))

    # ------------------------------------------------------------ chování
    def _povol(self, *_):
        kat = self.ucel.isChecked()
        self.kod.setEnabled(kat)
        self.trida.setEnabled(not kat)
        self.m_rucne.setEnabled(self.m_rezim.currentText() == "ručně")
        self.vyska.setEnabled(self.v_rezim.currentText() != "bez redukce")
        self.info.setText("Délky se před výpočtem převedou do roviny S-JTSK: násobí se měřítkovým koeficientem "
                          "a redukcí R/(R+H), R = 6380 km. Použité korekce se vypíšou do protokolu.")

    def hodnota(self) -> N.NastaveniVypoctu:
        return N.NastaveniVypoctu(
            zakazka=self.zakazka.text().strip(), zpracovatel=self.zpracovatel.text().strip(),
            ucel="katastr" if self.ucel.isChecked() else "polohopis", kod_kvality=int(self.kod.currentText()),
            trida_presnosti=self.trida.value(), pristroj=self.pristroj.text().strip() or "Totální stanice",
            sigma_smer_mgon=self.s_smer.value(), sigma_delka_mm=self.s_a.value(), sigma_delka_ppm=self.s_b.value(),
            meritko_rezim=self.m_rezim.currentText(), meritko_rucne=self.m_rucne.value(),
            vyska_rezim=self.v_rezim.currentText(), vyska=self.vyska.value(), ppm_fyzikalni=self.ppm.value(),
            polygon_trida=self.p_trida.currentIndex() + 1, desetiny=self.desetiny.value())

    def parametry(self) -> dict:
        d = dict(self._ulozene)
        for k, w in self._prvky.items():
            if isinstance(w, QAbstractButton):
                d[k] = w.isChecked()
            elif isinstance(w, QLineEdit):
                d[k] = w.text()
            elif isinstance(w, QComboBox):
                d[k] = w.currentText()
            elif isinstance(w, QPlainTextEdit):
                d[k] = w.toPlainText()
        return d

    def _ok(self):
        uloz(self.hodnota())
        QSettings().setValue(KLIC_GROMA, json.dumps(self.parametry(), ensure_ascii=False))
        self.accept()
