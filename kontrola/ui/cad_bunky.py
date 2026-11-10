"""Knihovna buněk (jako Cell Library v MicroStationu): přehled buněk s náhledem, hledání, načtení knihovny
.CEL / DXF a výběr buňky, která se pak klikem umisťuje do výkresu."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from ..cad import upravy as U


def _cary_bloku(doc, jmeno: str, hloubka: int = 0) -> list[list[tuple[float, float]]]:
    """Lomené čáry kresby bloku (i vnořených buněk) pro náhled."""
    from ezdxf import path as P
    out = []
    try:
        blk = doc.blocks.get(jmeno)
    except Exception:  # noqa: BLE001
        return out
    if blk is None:
        return out
    for e in blk:
        t = e.dxftype()
        if t == "INSERT" and hloubka < 3:
            try:
                ents = list(e.virtual_entities())
            except Exception:  # noqa: BLE001
                continue
        else:
            ents = [e]
        for v in ents:
            if v.dxftype() in ("TEXT", "MTEXT", "ATTDEF", "ATTRIB", "INSERT"):
                if v.dxftype() == "TEXT":  # text jako obdélníček v místě textu
                    p, h = v.dxf.insert, max(v.dxf.height, 1e-6)
                    w = h * 0.6 * max(1, len(v.dxf.text or ""))
                    out.append([(p.x, p.y), (p.x + w, p.y), (p.x + w, p.y + h), (p.x, p.y + h), (p.x, p.y)])
                continue
            try:
                pth = P.make_path(v)
            except Exception:  # noqa: BLE001
                continue
            try:
                for sp in pth.sub_paths():
                    pts = [(q.x, q.y) for q in sp.flattening(0.01, segments=24)]
                    if len(pts) >= 2:
                        out.append(pts)
            except Exception:  # noqa: BLE001
                continue
    return out


def nahled(doc, jmeno: str, velikost: int = 56, barva: str = "#E5E7EB") -> QPixmap:
    pm = QPixmap(velikost, velikost)
    pm.fill(Qt.transparent)
    cary = _cary_bloku(doc, jmeno)
    if not cary:
        return pm
    xs = [x for c in cary for x, _y in c]
    ys = [y for c in cary for _x, y in c]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    m = (velikost - 8) / max(w, h, 1e-9)
    ox = (velikost - w * m) / 2 - min(xs) * m
    oy = (velikost + h * m) / 2 + min(ys) * m
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(barva), 1.2)
    qp.setPen(pen)
    for c in cary:
        pp = QPainterPath(QPointF(ox + c[0][0] * m, oy - c[0][1] * m))
        for x, y in c[1:]:
            pp.lineTo(QPointF(ox + x * m, oy - y * m))
        qp.drawPath(pp)
    qp.end()
    return pm


class BunkyDialog(QDialog):
    """Výběr buňky k umístění. ``vysledek`` = (název, měřítko, natočení) po potvrzení."""

    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Buňky (Cell Library)")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        r = QHBoxLayout()
        self.hledat = QLineEdit()
        self.hledat.setPlaceholderText("🔍 hledat buňku (název nebo číslo, např. 9.12)")
        self.hledat.setClearButtonEnabled(True)
        self.hledat.textChanged.connect(self._filtr)
        r.addWidget(self.hledat, 1)
        b = QPushButton("Načíst knihovnu…")
        b.setToolTip("Knihovna buněk MicroStationu (.CEL) nebo DXF s bloky – buňky se přidají do výkresu")
        b.clicked.connect(self._nacti)
        r.addWidget(b)
        lay.addLayout(r)
        self.seznam = QListWidget()
        self.seznam.setViewMode(QListView.IconMode)
        self.seznam.setIconSize(QSize(56, 56))
        self.seznam.setGridSize(QSize(96, 92))
        self.seznam.setResizeMode(QListView.Adjust)
        self.seznam.setMovement(QListView.Static)
        self.seznam.setWordWrap(True)
        self.seznam.itemDoubleClicked.connect(lambda _it: self._ok())
        lay.addWidget(self.seznam, 1)
        self.info = QLabel()
        self.info.setStyleSheet("color: gray;")
        lay.addWidget(self.info)
        f = QFormLayout()
        p = page.predvolba
        self.meritko = QDoubleSpinBox()
        self.meritko.setRange(0.001, 100000)
        self.meritko.setDecimals(3)
        self.meritko.setValue((p.meritko_bunky if p is not None and p.meritko_bunky else None) or
                              getattr(page, "_meritko_bunky", 1.0))
        self.uhel = QDoubleSpinBox()
        self.uhel.setRange(-360, 360)
        self.uhel.setDecimals(2)
        self.uhel.setSuffix(" °")
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Měřítko:"))
        r2.addWidget(self.meritko)
        r2.addSpacing(16)
        r2.addWidget(QLabel("Natočení:"))
        r2.addWidget(self.uhel)
        r2.addStretch(1)
        f.addRow(r2)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Umístit")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.vysledek = None
        self.napln()

    def napln(self):
        doc = self.page.dok.doc
        self.seznam.clear()
        jmena = U.bloky(doc)
        p = self.page.predvolba
        vhodne: list[str] = []
        if p is not None and p.blok:
            from ..rules import block_matches, split_alternatives
            vhodne = [j for j in jmena if any(block_matches(v, j) for v in split_alternatives(p.blok))]
        jmena = vhodne + [j for j in jmena if j not in vhodne]
        tmave = True
        try:
            from .theme import is_dark
            tmave = is_dark()
        except Exception:  # noqa: BLE001
            pass
        for j in jmena:
            it = QListWidgetItem(QIcon(nahled(doc, j, barva="#E5E7EB" if tmave else "#1F2937")), j)
            it.setData(Qt.UserRole, j)
            it.setToolTip(j + ("  (podle zadání pro „" + p.nazev + "“)" if j in vhodne else ""))
            self.seznam.addItem(it)
        ac = getattr(self.page, "_aktivni_bunka", None)
        i = jmena.index(ac) if ac in jmena else 0
        if jmena:
            self.seznam.setCurrentRow(i)
        self.info.setText(f"{len(jmena)} buněk ve výkresu." if jmena else
                          "Ve výkresu zatím nejsou buňky – načtěte knihovnu (.CEL od učitele nebo ze školní "
                          "pracovní sady), nebo vytvořte buňku z kresby příkazem „blok“.")
        self._filtr(self.hledat.text())

    def _filtr(self, t: str):
        t = t.strip().lower()
        for i in range(self.seznam.count()):
            it = self.seznam.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _nacti(self):
        if self.page.knihovna_bunek():
            self.napln()

    def _ok(self):
        it = self.seznam.currentItem()
        if it is None or it.isHidden():
            return
        self.vysledek = (it.data(Qt.UserRole), self.meritko.value(), self.uhel.value())
        self.page._meritko_bunky = self.meritko.value()
        self.accept()
