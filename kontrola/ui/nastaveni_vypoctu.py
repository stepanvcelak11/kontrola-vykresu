"""Okno Nastavení výpočtů (jako v Gromě): účel měření, přístroj, korekce délek, mezní odchylky."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from ..geodezie import nastaveni as N
from ..geodezie.vypocty import MXY_KOD_KVALITY

KLIC = "vypocty/nastaveni"


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


def _cislo(v, lo, hi, dec, suf=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(v)
    if suf:
        s.setSuffix(suf)
    return s


class NastaveniVypoctuDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nastavení výpočtů")
        n = N.aktualni()
        lay = QVBoxLayout(self)

        g1 = QGroupBox("Účel měření")
        f1 = QFormLayout(g1)
        self.ucel = QComboBox()
        self.ucel.addItems(["katastr nemovitostí (kód kvality)", "polohopis / účelová mapa (třída přesnosti)"])
        self.ucel.setCurrentIndex(0 if n.ucel == "katastr" else 1)
        self.kod = QComboBox()
        self.kod.addItems([str(k) for k in sorted(MXY_KOD_KVALITY)])
        self.kod.setCurrentText(str(n.kod_kvality))
        self.trida = QSpinBox()
        self.trida.setRange(1, 5)
        self.trida.setValue(n.trida_presnosti)
        f1.addRow("Účel:", self.ucel)
        f1.addRow("Kód kvality:", self.kod)
        f1.addRow("Třída přesnosti (ČSN 01 3410):", self.trida)
        lay.addWidget(g1)

        g2 = QGroupBox("Přístroj")
        f2 = QFormLayout(g2)
        self.pristroj = QLineEdit(n.pristroj)
        self.s_smer = _cislo(n.sigma_smer_mgon, 0, 100, 2, " mgon")
        self.s_a = _cislo(n.sigma_delka_mm, 0, 100, 2, " mm")
        self.s_b = _cislo(n.sigma_delka_ppm, 0, 100, 2, " ppm")
        f2.addRow("Název:", self.pristroj)
        f2.addRow("σ směru:", self.s_smer)
        f2.addRow("σ délky a:", self.s_a)
        f2.addRow("σ délky b:", self.s_b)
        lay.addWidget(g2)

        g3 = QGroupBox("Korekce měřených délek (rajón, polygon, volné stanovisko, protínání z délek)")
        f3 = QFormLayout(g3)
        self.m_rezim = QComboBox()
        self.m_rezim.addItems(list(N.REZIMY_MERITKA))
        self.m_rezim.setCurrentText(n.meritko_rezim)
        self.m_rucne = _cislo(n.meritko_rucne, 0.9, 1.1, 8)
        self.v_rezim = QComboBox()
        self.v_rezim.addItems(list(N.REZIMY_VYSKY))
        self.v_rezim.setCurrentText(n.vyska_rezim)
        self.vyska = _cislo(n.vyska, -500, 9000, 1, " m")
        self.ppm = _cislo(n.ppm_fyzikalni, -500, 500, 1, " ppm")
        f3.addRow("Měřítko zobrazení:", self.m_rezim)
        f3.addRow("Měřítko ručně:", self.m_rucne)
        f3.addRow("Redukce z nadmořské výšky:", self.v_rezim)
        f3.addRow("Nadmořská výška:", self.vyska)
        f3.addRow("Fyzikální korekce:", self.ppm)
        lay.addWidget(g3)

        g4 = QGroupBox("Polygonové pořady – mezní odchylky")
        f4 = QFormLayout(g4)
        self.p_trida = QComboBox()
        self.p_trida.addItems(["1: úhlová 25·√(n+2) mgon, polohová 0,0025·√Σs + 0,04 m",
                               "2: úhlová 100·√(n+3) mgon, polohová 0,005·√Σs + 0,04 m"])
        self.p_trida.setCurrentIndex(1 if n.polygon_trida == 2 else 0)
        f4.addRow("Třída:", self.p_trida)
        lay.addWidget(g4)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        for w in (self.ucel, self.m_rezim, self.v_rezim):
            w.currentIndexChanged.connect(self._povol)
        self._povol()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _povol(self):
        kat = self.ucel.currentIndex() == 0
        self.kod.setEnabled(kat)
        self.trida.setEnabled(not kat)
        self.m_rucne.setEnabled(self.m_rezim.currentText() == "ručně")
        self.vyska.setEnabled(self.v_rezim.currentText() != "bez redukce")
        self.info.setText("Délky se před výpočtem převedou do roviny S-JTSK: násobí se měřítkem zobrazení "
                          "(spočte se ze souřadnic v těžišti úlohy) a redukcí R/(R+H), R = 6380 km. Výšku "
                          "„z výšek bodů“ vezme z Z daných bodů, jinak použije zadanou. Použité korekce se "
                          "vypíšou do protokolu.")

    def hodnota(self) -> N.NastaveniVypoctu:
        return N.NastaveniVypoctu(
            ucel="katastr" if self.ucel.currentIndex() == 0 else "polohopis", kod_kvality=int(self.kod.currentText()),
            trida_presnosti=self.trida.value(), pristroj=self.pristroj.text().strip() or "Totální stanice",
            sigma_smer_mgon=self.s_smer.value(), sigma_delka_mm=self.s_a.value(), sigma_delka_ppm=self.s_b.value(),
            meritko_rezim=self.m_rezim.currentText(), meritko_rucne=self.m_rucne.value(),
            vyska_rezim=self.v_rezim.currentText(), vyska=self.vyska.value(), ppm_fyzikalni=self.ppm.value(),
            polygon_trida=self.p_trida.currentIndex() + 1)

    def _ok(self):
        uloz(self.hodnota())
        self.accept()
