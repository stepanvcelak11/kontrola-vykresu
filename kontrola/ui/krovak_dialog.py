"""Zkreslení v Křovákově zobrazení (Groma, kap. 47): z vztažného bodu (Y, X a výška Z) spočte měřítkový
koeficient – opravu z kartografického zkreslení a z nadmořské výšky – a tlačítkem Nastavit ho dá na lištu
nastavení. Tím koeficientem se pak násobí všechny měřené délky (při importu zápisníku i v úlohách)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from ..geodezie import nastaveni as N
from .groma_formulare import BodBox, formular, pole


class ZkresleniDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Zkreslení v Křovákově zobrazení")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setSizeGripEnabled(True)
        self.resize(560, 470)
        lay = QVBoxLayout(self)
        g = QGroupBox("Vztažný bod")
        gl = QVBoxLayout(g)
        self.bod = BodBox(page)
        gl.addWidget(self.bod)
        r = QHBoxLayout()
        self.b_teziste = QPushButton("Těžiště bodů")
        self.b_teziste.setToolTip("Vztažný bod = průměr souřadnic označených bodů v seznamu (nic neoznačeno = "
                                  "všech bodů); výška = průměr výšek")
        r.addWidget(self.b_teziste)
        r.addStretch(1)
        gl.addLayout(r)
        info = QLabel("Zapište číslo bodu, přetáhněte bod ze seznamu souřadnic, nebo vezměte těžiště zaměřené "
                      "oblasti. Má-li bod výšku Z, spočte se i oprava z nadmořské výšky.")
        info.setWordWrap(True)
        info.setObjectName("poznamka")
        gl.addWidget(info)
        lay.addWidget(g)
        v = QGroupBox("Měřítkové koeficienty")
        self.m_zkr = pole("mer", 150, True)
        self.m_vys = pole("vys", 150, True)
        self.m_cel = pole("sour", 150, True)
        self.ch_zkr = QCheckBox("Oprava z kartografického zkreslení")
        self.ch_zkr.setChecked(True)
        self.ch_vys = QCheckBox("Oprava z nadmořské výšky")
        self.ch_vys.setChecked(True)
        vl = QVBoxLayout(v)
        vl.addWidget(formular([("Zkreslení:", self.m_zkr), ("Nadmořská výška:", self.m_vys),
                               ("Výsledný koeficient:", self.m_cel)], 130))
        vl.addWidget(self.ch_zkr)
        vl.addWidget(self.ch_vys)
        self.nyni = QLabel()
        self.nyni.setObjectName("poznamka")
        vl.addWidget(self.nyni)
        lay.addWidget(v)
        lay.addStretch(1)
        b = QHBoxLayout()
        self.b_vypocet = QPushButton("Výpočet")
        self.b_nastavit = QPushButton("Nastavit")
        self.b_nastavit.setProperty("primarni", True)
        self.b_nastavit.setEnabled(False)
        zav = QPushButton("Zavřít")
        b.addStretch(1)
        for w in (self.b_vypocet, self.b_nastavit, zav):
            b.addWidget(w)
        lay.addLayout(b)
        self.b_vypocet.clicked.connect(self.vypocet)
        self.b_nastavit.clicked.connect(self.nastavit)
        self.b_teziste.clicked.connect(self.teziste)
        zav.clicked.connect(self.close)
        self.ch_zkr.toggled.connect(lambda _c: self._celkem())
        self.ch_vys.toggled.connect(lambda _c: self._celkem())
        self.bod.zmena.connect(lambda: self.b_nastavit.setEnabled(False))
        self._k: tuple[float, float | None] | None = None
        self._ukaz_aktualni()

    def _ukaz_aktualni(self):
        k = N.aktualni().koeficient()
        self.nyni.setText("Nastavené měřítko: " + (f"<b>{k:.12f}</b>" if k is not None else "počítá se z bodů"))

    def teziste(self):
        sez = self.page.seznam.body
        vyb = self.page.selected() if hasattr(self.page, "selected") else []
        body = vyb or sez
        if not body:
            return
        zz = [b.z for b in body if b.z is not None]
        self.bod.nastav("těžiště", sum(b.y for b in body) / len(body), sum(b.x for b in body) / len(body),
                        sum(zz) / len(zz) if zz else None)
        self.vypocet()

    def vypocet(self) -> float | None:
        s = self.bod.souradnice()
        if s is None:
            self.bod._dopln()
            s = self.bod.souradnice()
        if s is None:
            self.m_cel.setText("")
            self.nyni.setText("<span style='color:#DC2626'>Zadejte vztažný bod (číslo ze seznamu nebo Y a X).</span>")
            return None
        try:
            self._k = N.zkresleni(s[0], s[1], s[2])
        except (ValueError, ZeroDivisionError):
            self.nyni.setText("<span style='color:#DC2626'>Bod není v S-JTSK (Y a X kladné, v řádu set tisíc metrů).</span>")
            return None
        m, mh = self._k
        self.m_zkr.setText(f"{m:.12f}")
        self.m_vys.setText("" if mh is None else f"{mh:.12f}")
        self.ch_vys.setEnabled(mh is not None)
        self.b_nastavit.setEnabled(True)
        return self._celkem()

    def _celkem(self) -> float | None:
        if self._k is None:
            return None
        m, mh = self._k
        k = (m if self.ch_zkr.isChecked() else 1.0) * (mh if (mh is not None and self.ch_vys.isChecked()) else 1.0)
        self.m_cel.setText(f"{k:.12f}")
        self._ukaz_aktualni()
        return k

    def nastavit(self) -> float | None:
        k = self._celkem()
        if k is None:
            return None
        from .nastaveni_vypoctu import uloz
        n = N.aktualni()
        n.nastav_koeficient(k)
        uloz(n)
        lista = getattr(self.page, "lista", None)
        if lista is not None:
            lista.nacti()
        m, mh = self._k
        s = self.bod.souradnice()
        prot = ["ZKRESLENÍ V KŘOVÁKOVĚ ZOBRAZENÍ", "===============================",
                f"vztažný bod {self.bod.cislo.text().strip() or '–'}: Y = {s[0]:.2f}  X = {s[1]:.2f}"
                + (f"  Z = {s[2]:.2f}" if s[2] is not None else ""),
                f"  měřítko zobrazení (zkreslení)  {m:.12f}  ({(m - 1) * 1e5:+.1f} cm/km)"
                + ("" if self.ch_zkr.isChecked() else "  – nepoužito"),
                *([f"  oprava z nadmořské výšky       {mh:.12f}  ({(mh - 1) * 1e5:+.1f} cm/km)"
                   + ("" if self.ch_vys.isChecked() else "  – nepoužito")] if mh is not None else []),
                f"Nastavený měřítkový koeficient: {k:.12f}"]
        if hasattr(self.page, "protokol_append"):
            self.page.protokol_append(prot)
        self._ukaz_aktualni()
        return k
