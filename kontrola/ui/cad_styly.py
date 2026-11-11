"""Okno Styly čar (jako Line Styles v MicroStationu): standardní styly 0–7 a vlastní styly z knihoven .rsc
(ploty, hranice, vedení…) s náhledem, hledání, načtení knihovny a nastavení aktivního stylu."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

SIRKA, VYSKA = 220, 26
NAZVY_MS = {0: "plná", 1: "tečkovaná", 2: "krátké čárky", 3: "dlouhé čárky", 4: "čerchovaná", 5: "krátké čárky",
            6: "dvojčerchovaná", 7: "střídavá čárka"}


def nahled_stylu(st, barva: str, sirka: int = SIRKA, vyska: int = VYSKA) -> QPixmap:
    """Náhled vlastního stylu čáry: několik period vzoru i se symboly (kolmé čárky plotu, křížky…)."""
    from ..io.rsc import vykresli
    pm = QPixmap(sirka, vyska)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(barva), 1.2))
    delky = [sum(u.delka for u in sl.useky) for sl in st.slozky if sl.useky]
    perioda = max(max(delky or [1.0]), 1e-6)
    k = (sirka - 8) / (perioda * 3.5)  # asi 3,5 periody na šířku
    try:
        cary = vykresli([(0.0, 0.0), ((sirka - 8) / k, 0.0)], st)
    except Exception:  # noqa: BLE001 – poškozený styl nesmí shodit okno
        cary = []
    if cary:
        vys = max((abs(y) for c in cary for _x, y in c), default=0.0)
        if vys * k > vyska / 2 - 2:  # vysoké symboly zmenšit, ať se vejdou
            k2 = (vyska / 2 - 2) / vys
        else:
            k2 = k
        cesta = QPainterPath()
        for c in cary:
            if len(c) < 2:
                continue
            cesta.moveTo(4 + c[0][0] * k, vyska / 2 - c[0][1] * k2)
            for x, y in c[1:]:
                cesta.lineTo(4 + x * k, vyska / 2 - y * k2)
        p.drawPath(cesta)
    else:
        p.drawLine(4, vyska // 2, sirka - 4, vyska // 2)
    p.end()
    return pm


class StylyCarDialog(QDialog):
    """Výběr stylu čáry. ``vysledek`` = kód stylu („3“, „2.103“) po potvrzení."""

    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Styly čar (Line Styles)")
        self.resize(520, 520)
        lay = QVBoxLayout(self)
        r = QHBoxLayout()
        self.hledat = QLineEdit()
        self.hledat.setPlaceholderText("🔍 hledat styl (název nebo číslo značky, např. 2.103)")
        self.hledat.setClearButtonEnabled(True)
        self.hledat.textChanged.connect(self._filtr)
        r.addWidget(self.hledat, 1)
        b = QPushButton("Načíst knihovnu…")
        b.setToolTip("Knihovna stylů čar MicroStationu (.rsc) od učitele nebo ze školní pracovní sady")
        b.clicked.connect(lambda: self._nacti())
        r.addWidget(b)
        lay.addLayout(r)
        self.seznam = QListWidget()
        self.seznam.setIconSize(QSize(SIRKA, VYSKA))
        self.seznam.itemDoubleClicked.connect(lambda _it: self._ok())
        self.seznam.currentItemChanged.connect(lambda *_: self._popis())
        lay.addWidget(self.seznam, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: gray;")
        lay.addWidget(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.b_ok = bb.button(QDialogButtonBox.Ok)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.vysledek = None
        self._pocet = 0
        self.napln()

    def napln(self):
        from .cad_ikony import ukazka_cary
        from .theme import is_dark
        barva = "#E5E7EB" if is_dark() else "#1F2937"
        pg = self.page
        self.seznam.clear()
        n_vyber = len(getattr(pg, "vyber", []) or [])
        self.b_ok.setText(f"Dát na vybrané prvky ({n_vyber})" if n_vyber else "Nastavit jako aktivní")
        for n in range(8):
            it = QListWidgetItem(QIcon(ukazka_cary(str(n), 1.6, barva, SIRKA, VYSKA)), f"{n} – {NAZVY_MS[n]}")
            it.setData(Qt.UserRole, str(n))
            it.setData(Qt.UserRole + 1, f"Standardní styl čáry MicroStationu {n} ({NAZVY_MS[n]}).")
            self.seznam.addItem(it)
        styly = pg.styly_rsc() if pg.dok is not None else {}
        uz = set()
        for jm, st in styly.items():
            if st.kod in uz:
                continue
            uz.add(st.kod)
            it = QListWidgetItem(QIcon(nahled_stylu(st, barva)), jm)
            it.setData(Qt.UserRole, st.kod)
            it.setData(Qt.UserRole + 1, (st.popis or jm) + f" – vlastní styl z knihovny .rsc, {len(st.slozky)} složek.")
            self.seznam.addItem(it)
        if pg.dok is not None:  # typy čar výkresu, které nejsou v žádné knihovně (z DXF, .lin)
            for lt in sorted(x.dxf.name for x in pg.dok.doc.linetypes):
                if lt.upper() in ("BYLAYER", "BYBLOCK", "CONTINUOUS") or lt.upper().startswith("DGN STYLE") \
                        or lt in uz:
                    continue
                it = QListWidgetItem(lt)
                it.setData(Qt.UserRole, lt)
                it.setData(Qt.UserRole + 1, "Typ čáry z výkresu (DXF) – bez náhledu z knihovny.")
                self.seznam.addItem(it)
        akt = str(getattr(pg.kresleni, "typ_cary", "") or "") if getattr(pg, "kresleni", None) is not None else ""
        for i in range(self.seznam.count()):
            kod = self.seznam.item(i).data(Qt.UserRole)
            if akt == kod or akt.upper() == f"DGN STYLE {kod}".upper():
                self.seznam.setCurrentRow(i)
                break
        else:
            self.seznam.setCurrentRow(0)
        self._pocet = len(uz)
        self._filtr(self.hledat.text())
        self._popis()

    def _popis(self):
        it = self.seznam.currentItem()
        zaklad = (f"{self._pocet} vlastních stylů z knihoven." if self._pocet else
                  "Vlastní styly zatím nejsou – načtěte knihovnu .rsc (od učitele nebo z pracovní sady).")
        self.info.setText((it.data(Qt.UserRole + 1) + "  " if it is not None else "") + zaklad)

    def _filtr(self, t: str):
        t = t.strip().lower()
        for i in range(self.seznam.count()):
            it = self.seznam.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _nacti(self):
        self.page._styly_car("připoj")
        self.napln()

    def _ok(self):
        it = self.seznam.currentItem()
        if it is None or it.isHidden():
            return
        self.vysledek = it.data(Qt.UserRole)
        self.accept()
