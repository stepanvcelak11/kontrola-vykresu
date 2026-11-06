"""Zpracování zápisníku (Groma: Měření → Zpracování zápisníku): které úpravy měření se mají při výpočtu provést.

Volby se uloží do nastavení výpočtů a použije je výpočet polární metody ze zápisníku (i Polární metoda dávkou).
U každé volby je krátké vysvětlení – kdy ji zapnout a kdy ne (např. když totální stanice už opravila zakřivení
a refrakci nebo uložila vodorovné délky)."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from PySide6.QtCore import Qt

from ..geodezie import nastaveni as N


def _cislo(v: float, dec: int, suf: str, lo: float = 0.0, hi: float = 10.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(v)
    s.setSuffix(suf)
    s.setSingleStep(10 ** -dec)
    s.setMaximumWidth(120)
    return s


def _vysvetleni(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setObjectName("poznamka")
    lab.setContentsMargins(24, 0, 0, 6)
    return lab


class ZpracovaniDialog(QDialog):
    def __init__(self, parent=None, prepocitat=None):
        super().__init__(parent)
        self.setWindowTitle("Zpracování zápisníku")
        self.setSizeGripEnabled(True)
        self.resize(700, 720)
        self._prepocitat = prepocitat
        n = self._n = N.aktualni()
        lay = QVBoxLayout(self)
        uvod = QLabel("Zvolte, jaké úpravy se mají s měřením provést před výpočtem (jako v Gromě "
                      "Měření → Zpracování zápisníku). Změna se projeví při dalším výpočtu zápisníku.")
        uvod.setWordWrap(True)
        lay.addWidget(uvod)
        obsah = QWidget()
        ol = QVBoxLayout(obsah)
        ol.setContentsMargins(0, 0, 6, 0)

        g = QGroupBox("Úpravy měření")
        gl = QVBoxLayout(g)
        self.ch_sikme = QCheckBox("Převod šikmých délek na vodorovné")
        self.ch_sikme.setChecked(n.zp_sikme)
        gl.addWidget(self.ch_sikme)
        gl.addWidget(_vysvetleni("Zapněte, když zápisník obsahuje šikmé délky (běžné). Vypněte, jen když stanice "
                                 "ukládala už vodorovné délky – jinak by se redukovaly dvakrát."))
        self.ch_polohy = QCheckBox("Zpracování měření v obou polohách (průměr I. a II. polohy)")
        self.ch_polohy.setChecked(n.zp_polohy)
        gl.addWidget(self.ch_polohy)
        gl.addWidget(_vysvetleni("Průměr z obou poloh dalekohledu vyloučí kolimační a indexovou chybu. Vypnuto = "
                                 "použije se jen I. poloha (rozdíly poloh se přesto zkontrolují)."))
        r = QHBoxLayout()
        self.ch_zakriveni = QCheckBox("Oprava ze zakřivení Země")
        self.ch_zakriveni.setChecked(n.zp_zakriveni)
        self.ch_refrakce = QCheckBox("Oprava refrakce, koeficient k =")
        self.ch_refrakce.setChecked(n.zp_refrakce)
        self.k = _cislo(n.k_refrakce, 2, "", 0.0, 1.0)
        r.addWidget(self.ch_zakriveni)
        r.addSpacing(16)
        r.addWidget(self.ch_refrakce)
        r.addWidget(self.k)
        r.addStretch(1)
        gl.addLayout(r)
        gl.addWidget(_vysvetleni("Opravují převýšení (výšky bodů) u delších záměr. Obvykle se zavádějí obě "
                                 "společně, k = 0,13. Pokud už totální stanice zakřivení a refrakci opravila "
                                 "(volba v nastavení přístroje), obě vypněte."))
        self.ch_obous = QCheckBox("Zpracování obousměrně měřených délek a převýšení")
        self.ch_obous.setChecked(n.zp_obousmerne)
        gl.addWidget(self.ch_obous)
        gl.addWidget(_vysvetleni("Délka a převýšení měřené tam i zpět mezi stanovisky se zprůměrují."))
        r = QHBoxLayout()
        self.ch_prumer = QCheckBox("Bod určený dvakrát uložit jako průměr, když se liší nejvýše o")
        self.ch_prumer.setChecked(n.zp_prumer_kontrolnich)
        self.max_xy = _cislo(n.prumer_max_xy, 3, " m")
        r.addWidget(self.ch_prumer)
        r.addWidget(self.max_xy)
        r.addStretch(1)
        gl.addLayout(r)
        gl.addWidget(_vysvetleni("Kontrolně zaměřený bod z jiného stanoviska (stejné číslo). Při větším rozdílu "
                                 "se průměr neuloží a v kontrolách se bod označí."))
        ol.addWidget(g)

        g = QGroupBox("Váhy orientací")
        gl = QVBoxLayout(g)
        self.r_delka = QRadioButton("Úměrné délce (jako Groma)")
        self.r_jedna = QRadioButton("Všechny orientace stejně (váha 1)")
        (self.r_delka if n.zp_vahy == "délka" else self.r_jedna).setChecked(True)
        gl.addWidget(self.r_delka)
        gl.addWidget(self.r_jedna)
        ol.addWidget(g)

        g = QGroupBox("Tolerance měření (Nastavení → Teodolit)")
        f = QGridLayout(g)
        f.addWidget(QLabel("podezřelé (?) nad"), 0, 1)
        f.addWidget(QLabel("chybné (x) nad"), 0, 2)
        self.tol = {}
        for r_, (k, t, dec, suf) in enumerate((("kol", "Kolimační chyba", 4, " g"), ("idx", "Indexová chyba", 4, " g"),
                                               ("md", "Oprava délky ze dvou poloh", 3, " m")), 1):
            f.addWidget(QLabel(t + ":"), r_, 0)
            for c_, typ in enumerate(("p", "ch"), 1):
                e = _cislo(getattr(n, f"{k}_{typ}"), dec, suf, 0.0, 5.0)
                self.tol[f"{k}_{typ}"] = e
                f.addWidget(e, r_, c_)
        f.setColumnStretch(3, 1)
        ol.addWidget(g)
        ol.addWidget(_vysvetleni("Mezní odchylky pro orientace, polygony a transformace najdete v Nastavení → "
                                 "Tolerance."))
        ol.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setWidget(obsah)
        lay.addWidget(sc, 1)
        b = QHBoxLayout()
        self.b_vychozi = QPushButton("Výchozí")
        self.b_vychozi.setToolTip("Vrátit výchozí volby (jako školní Groma)")
        self.b_ok = QPushButton("Uložit a přepočítat" if prepocitat else "Uložit")
        self.b_ok.setProperty("primarni", True)
        zav = QPushButton("Zavřít")
        b.addWidget(self.b_vychozi)
        b.addStretch(1)
        b.addWidget(self.b_ok)
        b.addWidget(zav)
        lay.addLayout(b)
        self.b_ok.clicked.connect(self.uloz)
        self.b_vychozi.clicked.connect(self.vychozi)
        zav.clicked.connect(self.reject)
        self.ch_refrakce.toggled.connect(self.k.setEnabled)
        self.ch_prumer.toggled.connect(self.max_xy.setEnabled)
        self.k.setEnabled(n.zp_refrakce)
        self.max_xy.setEnabled(n.zp_prumer_kontrolnich)

    def vychozi(self):
        d = N.NastaveniVypoctu()
        for ch, v in ((self.ch_sikme, d.zp_sikme), (self.ch_polohy, d.zp_polohy), (self.ch_zakriveni, d.zp_zakriveni),
                      (self.ch_refrakce, d.zp_refrakce), (self.ch_obous, d.zp_obousmerne),
                      (self.ch_prumer, d.zp_prumer_kontrolnich)):
            ch.setChecked(v)
        self.k.setValue(d.k_refrakce)
        self.max_xy.setValue(d.prumer_max_xy)
        self.r_delka.setChecked(True)
        for k, e in self.tol.items():
            e.setValue(getattr(d, k))

    def hodnoty(self) -> dict:
        d = {"zp_sikme": self.ch_sikme.isChecked(), "zp_polohy": self.ch_polohy.isChecked(),
             "zp_zakriveni": self.ch_zakriveni.isChecked(), "zp_refrakce": self.ch_refrakce.isChecked(),
             "k_refrakce": self.k.value(), "zp_obousmerne": self.ch_obous.isChecked(),
             "zp_prumer_kontrolnich": self.ch_prumer.isChecked(), "prumer_max_xy": self.max_xy.value(),
             "prumer_max_z": self.max_xy.value(), "zp_vahy": "délka" if self.r_delka.isChecked() else "1"}
        d.update({k: e.value() for k, e in self.tol.items()})
        return d

    def uloz(self):
        from .nastaveni_vypoctu import uloz
        n = self._n
        for k, v in self.hodnoty().items():
            setattr(n, k, v)
        uloz(n)
        self.accept()
        if self._prepocitat is not None:
            self._prepocitat()

