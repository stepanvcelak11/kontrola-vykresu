"""Atributy ze zadání v CAD: kontrola a úprava druhů prvků (vrstva, barva, styl, tloušťka, písmo…).

Tabulka ukazuje pravidla tak, jak je aplikace přečetla ze Směrnice / zadání, vedle toho, jak se prvek
v CAD opravdu nakreslí, a výsledek ověření (zkušební nakreslení + kontrola symbologie). Úpravy se po
„Uložit“ zapíšou do pravidel projektu – platí pak pro kreslení i pro kontrolu výkresu.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..model import GeomType
from ..rules import Rule, RuleSet, norm_style, parse_color, parse_weight

SL = ["Kód", "Název", "Geometrie", "Hladina", "Barva", "Styl čáry", "Tloušťka", "Buňka", "Písmo", "Výška písma",
      "Šířka písma", "Zarovnání", "Tučně", "Kurzíva", "Kreslí se jako", "Ověření"]
(C_KOD, C_NAZ, C_GEO, C_HL, C_BAR, C_STY, C_TL, C_BLK, C_FNT, C_VYS, C_SIR, C_ZAR, C_TUC, C_KUR, C_CAD,
 C_OVE) = range(len(SL))
GEO = [("", None), ("bod", GeomType.BOD), ("linie", GeomType.LINIE), ("polygon", GeomType.POLYGON),
       ("text", GeomType.TEXT)]
ZAROVNANI = ["", "vlevo nahoře", "vlevo uprostřed", "vlevo dole", "na střed nahoře", "na střed uprostřed",
             "na střed dole", "vpravo nahoře", "vpravo uprostřed", "vpravo dole"]


def _cislo(t: str) -> float | None:
    t = (t or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _f(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return (f"{v:.4f}".rstrip("0").rstrip(".")).replace(".", ",")
    return str(v)


def mapa_text(m: dict[int, float]) -> str:
    return "; ".join(f"{k}={_f(float(v))}" for k, v in sorted(m.items()))


def parse_mapa(t: str) -> dict[int, float]:
    """„0=0; 1=0,18; 2=0,3“ → {0: 0.0, 1: 0.18, 2: 0.3} (neplatné části → ValueError)."""
    out = {}
    for part in [p for p in t.replace("\n", ";").split(";") if p.strip()]:
        if "=" not in part:
            raise ValueError(f"„{part.strip()}“ – zapište jako tloušťka=mm, např. 1=0,18")
        a, b = part.split("=", 1)
        k, v = int(a.strip()), _cislo(b)
        if v is None or not 0 <= k <= 31 or v < 0:
            raise ValueError(f"„{part.strip()}“ – tloušťka 0–31 a kladné mm")
        out[k] = v
    return out


class AtributyDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.project = page.win.project
        self.rs: RuleSet = copy.deepcopy(self.project.rules)
        self.zmeneno = False
        self._plneni = False
        self.setWindowTitle("Atributy ze zadání – kontrola a úprava")
        self.resize(1300, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Takto aplikace přečetla atributy ze Směrnice a zadání. Opravte, co je špatně (dvojklik do buňky), "
            "a <b>Ověřit</b> každý prvek zkušebně nakreslí a projede kontrolou – zelená = projde. "
            "<b>Uložit</b> změny zapíše do pravidel projektu (platí pro kreslení i kontrolu). Barvy, styly a "
            "tloušťky jsou čísla MicroStationu; výška písma je v mm na papíře v měřítku níže."))
        top = QHBoxLayout()
        self.hledat = QLineEdit()
        self.hledat.setPlaceholderText("Hledat kód, název nebo hladinu…")
        self.hledat.textChanged.connect(self._filtr)
        top.addWidget(self.hledat, 1)
        top.addWidget(QLabel("Měřítko 1:"))
        self.meritko = QSpinBox()
        self.meritko.setRange(0, 100000)
        self.meritko.setSpecialValueText("–")
        self.meritko.setValue(int(self.rs.meritko or 0))
        self.meritko.valueChanged.connect(self._zmena)
        top.addWidget(self.meritko)
        top.addWidget(QLabel("Tloušťky MicroStationu → mm:"))
        self.mapa = QLineEdit(mapa_text(self.rs.mapa_tloustek))
        self.mapa.setPlaceholderText("0=0; 1=0,18; 2=0,3")
        self.mapa.setMinimumWidth(260)
        self.mapa.editingFinished.connect(self._zmena)
        top.addWidget(self.mapa)
        lay.addLayout(top)
        self.tab = QTableWidget(0, len(SL))
        self.tab.setHorizontalHeaderLabels(SL)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.verticalHeader().setVisible(False)
        self.tab.itemChanged.connect(self._zmena)
        lay.addWidget(self.tab, 1)
        self.souhrn = QLabel()
        lay.addWidget(self.souhrn)
        row = QHBoxLayout()
        self.b_over = QPushButton("Ověřit")
        self.b_over.setProperty("primarni", True)
        self.b_pridat = QPushButton("Přidat prvek")
        self.b_smazat = QPushButton("Smazat vybrané")
        self.b_ulozit = QPushButton("Uložit do projektu")
        self.b_zavrit = QPushButton("Zavřít")
        for b in (self.b_over, self.b_pridat, self.b_smazat):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.b_ulozit)
        row.addWidget(self.b_zavrit)
        lay.addLayout(row)
        self.b_over.clicked.connect(self.overit)
        self.b_pridat.clicked.connect(self.pridat)
        self.b_smazat.clicked.connect(self.smazat)
        self.b_ulozit.clicked.connect(self.ulozit)
        self.b_zavrit.clicked.connect(self.close)
        self.naplnit()
        self.overit()

    # ------------------------------------------------------------ tabulka ↔ pravidla
    def naplnit(self):
        self._plneni = True
        self.tab.setRowCount(0)
        for r in self.rs.pravidla:
            self._radek(r)
        self.tab.resizeColumnsToContents()
        for c in (C_NAZ, C_CAD, C_OVE):
            self.tab.setColumnWidth(c, 240)
        self._plneni = False
        self._obnov_cad()

    def _radek(self, r: Rule):
        i = self.tab.rowCount()
        self.tab.insertRow(i)
        hodnoty = {C_KOD: r.kod, C_NAZ: r.nazev, C_HL: r.hladina or "", C_BAR: "" if r.barva is None else str(r.barva),
                   C_STY: r.styl_cary or "", C_TL: _f(r.tloustka), C_BLK: r.blok or "", C_FNT: r.font or "",
                   C_VYS: _f(r.vyska_textu), C_SIR: _f(r.sirka_textu)}
        for c, v in hodnoty.items():
            self.tab.setItem(i, c, QTableWidgetItem(v))
        for c in (C_CAD, C_OVE):
            it = QTableWidgetItem("")
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.tab.setItem(i, c, it)
        g = QComboBox()
        for lab, val in GEO:
            g.addItem(lab, val)
        g.setCurrentIndex(max(0, g.findData(r.geometrie)))
        g.currentIndexChanged.connect(self._zmena)
        self.tab.setCellWidget(i, C_GEO, g)
        z = QComboBox()
        z.setEditable(True)
        z.addItems(ZAROVNANI)
        z.setCurrentText(r.zarovnani or "")
        z.currentTextChanged.connect(self._zmena)
        self.tab.setCellWidget(i, C_ZAR, z)
        for c, v in ((C_TUC, r.tucne), (C_KUR, r.kurziva)):
            ch = QCheckBox()
            ch.setTristate(True)
            ch.setCheckState(Qt.PartiallyChecked if v is None else Qt.Checked if v else Qt.Unchecked)
            ch.setToolTip("zaškrtnuto = ano, prázdné = ne, šedé = zadání neurčuje")
            ch.stateChanged.connect(self._zmena)
            self.tab.setCellWidget(i, c, ch)

    def _t(self, i, c) -> str:
        it = self.tab.item(i, c)
        return it.text().strip() if it else ""

    def _pravidlo(self, i: int, puvodni: Rule) -> Rule:
        r = copy.deepcopy(puvodni)
        r.kod = self._t(i, C_KOD) or puvodni.kod
        r.nazev = self._t(i, C_NAZ)
        r.geometrie = GeomType.parse(self.tab.cellWidget(i, C_GEO).currentData())  # QComboBox vrací text
        r.hladina = self._t(i, C_HL) or None
        r.barva = parse_color(self._t(i, C_BAR))
        r.styl_cary = norm_style(self._t(i, C_STY))
        r.tloustka = parse_weight(self._t(i, C_TL))
        r.blok = self._t(i, C_BLK) or None
        r.font = self._t(i, C_FNT) or None
        r.vyska_textu = _cislo(self._t(i, C_VYS))
        r.sirka_textu = _cislo(self._t(i, C_SIR))
        r.zarovnani = self.tab.cellWidget(i, C_ZAR).currentText().strip() or None
        for c, attr in ((C_TUC, "tucne"), (C_KUR, "kurziva")):
            st = self.tab.cellWidget(i, c).checkState()
            setattr(r, attr, None if st == Qt.PartiallyChecked else st == Qt.Checked)
        return r

    def _zmena(self, *_a):
        if self._plneni:
            return
        self.zmeneno = True
        self._prevzit()
        self._obnov_cad()
        self.souhrn.setText("Změněno – klikněte Ověřit a pak Uložit do projektu.")

    def _prevzit(self) -> bool:
        """Tabulka → pracovní kopie pravidel. Vrací False, když je chyba ve vstupu."""
        self.rs.pravidla[:] = [self._pravidlo(i, r) for i, r in enumerate(self.rs.pravidla)]
        self.rs.meritko = self.meritko.value() or None
        try:
            self.rs.mapa_tloustek = parse_mapa(self.mapa.text())
            self.mapa.setStyleSheet("")
            return True
        except ValueError as e:
            self.mapa.setStyleSheet("border: 1px solid #DC2626;")
            self.souhrn.setText(f"⚠ Převod tlouštěk: {e}")
            return False

    def _obnov_cad(self):
        from ..cad.zadani import predvolby
        self._plneni = True
        try:
            pv = predvolby(self.rs)
            for i, p in enumerate(pv):
                self.tab.item(i, C_CAD).setText(p.popis())
        finally:
            self._plneni = False

    # ------------------------------------------------------------ akce
    def overit(self) -> dict[int, list[str]]:
        from ..cad.zadani import overit_predvolby
        if not self._prevzit():
            return {}
        try:
            v = overit_predvolby(self.rs)
        except Exception as e:  # noqa: BLE001 – ověření nesmí shodit okno
            self.souhrn.setText(f"⚠ Ověření se nepovedlo: {e}")
            return {}
        self._plneni = True
        spatne = 0
        for i, zpravy in v.items():
            it = self.tab.item(i, C_OVE)
            if it is None:
                continue
            if zpravy:
                spatne += 1
                it.setText("⚠ " + "; ".join(zpravy))
                it.setForeground(QColor("#D97706"))
            else:
                it.setText("✓ projde kontrolou")
                it.setForeground(QColor("#16A34A"))
            it.setToolTip("\n".join(zpravy) or "Prvek nakreslený v CAD projde kontrolou symbologie.")
        self._plneni = False
        self.souhrn.setText(f"Ověřeno {len(v)} prvků: {len(v) - spatne} v pořádku, {spatne} s upozorněním."
                            + (" Najeďte myší na sloupec Ověření pro podrobnosti." if spatne else ""))
        self.vysledek = v
        return v

    def pridat(self):
        self._prevzit()
        n = 1
        while any(r.kod == f"nový {n}" for r in self.rs.pravidla):
            n += 1
        r = Rule(kod=f"nový {n}", nazev="", geometrie=GeomType.LINIE)
        self.rs.pravidla.append(r)
        self._plneni = True
        self._radek(r)
        self._plneni = False
        self.tab.scrollToBottom()
        self.tab.selectRow(self.tab.rowCount() - 1)
        self._zmena()

    def smazat(self):
        rows = sorted({i.row() for i in self.tab.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._prevzit()
        for r in rows:
            del self.rs.pravidla[r]
            self.tab.removeRow(r)
        self._zmena()

    def _filtr(self, t: str):
        t = t.strip().lower()
        for i in range(self.tab.rowCount()):
            txt = " ".join(self._t(i, c) for c in (C_KOD, C_NAZ, C_HL)).lower()
            self.tab.setRowHidden(i, bool(t) and t not in txt)

    def ulozit(self) -> bool:
        if not self._prevzit():
            QMessageBox.warning(self, "Atributy", "Opravte převod tlouštěk (zápis tloušťka=mm, např. 1=0,18).")
            return False
        pr = self.project
        pr.rules.pravidla[:] = self.rs.pravidla
        pr.rules.mapa_tloustek = dict(self.rs.mapa_tloustek)
        pr.rules.meritko = self.rs.meritko
        pr.save()
        win = self.page.win
        if hasattr(win, "zadani"):
            try:
                win.zadani.rules_changed()
            except Exception:  # noqa: BLE001
                pass
        self.page.obnov_predvolby()
        self.page._predvolba_zmenena()
        self.zmeneno = False
        self.souhrn.setText(f"Uloženo do projektu ({len(pr.rules.pravidla)} pravidel).")
        self.page.vypis("Atributy ze zadání uloženy do pravidel projektu.")
        return True

    def closeEvent(self, e):  # noqa: N802
        if self.zmeneno and self.isVisible():
            r = QMessageBox.question(self, "Atributy", "Uložit změny do projektu?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.ulozit()):
                e.ignore()
                return
        super().closeEvent(e)
