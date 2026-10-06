"""Grafika seznamu souřadnic (jako grafické okno Gromy): body s čísly, výškami a kódy, zoom, posun,
výběr myší (propojený s tabulkou) a měření vzdálenosti a směrníku mezi body.

Zobrazení jako mapa v S-JTSK: sever nahoře, východ vpravo (na obrazovce x = −Y, y = −X).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..geodezie import vypocty as V


class _Pohled(QGraphicsView):
    klik = Signal(float, float, bool)  # scéna x, y, Ctrl

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.scale(1, -1)
        self._pan = None
        self.vykreslit_popisy = None  # callback(painter, měřítko) – popisy v pixelech (stejně velké při zoomu)

    def wheelEvent(self, e):  # noqa: N802
        f = 1.0015 ** e.angleDelta().y()
        self.scale(f, f)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan = e.position()
            return
        if e.button() == Qt.LeftButton:
            p = self.mapToScene(e.position().toPoint())
            self.klik.emit(p.x(), p.y(), bool(e.modifiers() & Qt.ControlModifier))
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._pan = None
        super().mouseReleaseEvent(e)

    def drawForeground(self, p: QPainter, rect):  # noqa: N802
        if self.vykreslit_popisy:
            self.vykreslit_popisy(p, 1.0 / max(1e-12, abs(self.transform().m11())))


class GrafikaBodu(QWidget):
    vybrano = Signal(list)  # čísla vybraných bodů

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.vyber: list[str] = []
        self.mereni: list = []
        self.mod = "vyber"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        from .flow import RadekTlacitek
        bar = RadekTlacitek()  # v úzkém okně se zalomí
        self.ch_cisla = QCheckBox("Čísla")
        self.ch_vysky = QCheckBox("Výšky")
        self.ch_kody = QCheckBox("Kódy")
        self.ch_cisla.setChecked(True)
        for c in (self.ch_cisla, self.ch_vysky, self.ch_kody):
            c.toggled.connect(lambda _on: self.pohled.viewport().update())
            bar.addWidget(c)
        self.b_cele = QPushButton("Celé")
        self.b_cele.setToolTip("Zobrazit všechny body")
        self.b_mer = QPushButton("Měřit")
        self.b_mer.setCheckable(True)
        self.b_mer.setToolTip("Klikněte na dva body – vzdálenost, směrník, ΔY, ΔX a převýšení")
        self.b_spoj = QPushButton("Spojnice")
        self.b_spoj.setCheckable(True)
        self.b_spoj.setToolTip("Klikněte na dva body – spojnice se přidá (na existující spojnici se smaže)")
        self.b_kod = QPushButton("Spojit podle kódu…")
        self.b_kod.setToolTip("Body se stejným kódem spojit lomenou čarou v pořadí čísel (plot, hrana, …)")
        bar.addWidget(self.b_cele)
        bar.addWidget(self.b_mer)
        bar.addWidget(self.b_spoj)
        bar.addWidget(self.b_kod)
        bar.addStretch(1)
        self.info = QLabel("Klik = výběr bodu (Ctrl = přidat), kolečko = zoom, pravé tlačítko = posun.")
        bar.addWidget(self.info)
        lay.addLayout(bar)
        self.pohled = _Pohled()
        self.pohled.setBackgroundBrush(QColor("#111318"))
        self.pohled.vykreslit_popisy = self._popisy
        lay.addWidget(self.pohled, 1)
        self.b_cele.clicked.connect(self.cele)
        self.b_mer.toggled.connect(self._mod_mereni)
        self.b_spoj.toggled.connect(self._mod_spojnice)
        self.b_kod.clicked.connect(lambda: self.spojit_podle_kodu())
        self.pohled.klik.connect(self._klik)
        self._body: list = []

    # ------------------------------------------------------------ data
    def obnov(self):
        """Překreslí body ze seznamu (volá se po každé změně seznamu)."""
        sc = self.pohled.scene()
        sc.clear()
        self._body = [b for b in self.page.seznam.body if math.isfinite(b.y) and math.isfinite(b.x)]
        if not self._body:
            return
        xs = [-b.y for b in self._body]
        ys = [-b.x for b in self._body]
        r = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        m = max(r.width(), r.height(), 1.0) * 0.05
        sc.setSceneRect(r.adjusted(-m, -m, m, m))
        self.pohled.viewport().update()

    def cele(self):
        r = self.pohled.scene().sceneRect()
        if not r.isEmpty():
            self.pohled.fitInView(r, Qt.KeepAspectRatio)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.obnov()
        self.cele()

    # ------------------------------------------------------------ kreslení
    def _popisy(self, p: QPainter, s: float):
        vyb = set(self.vyber)
        sp = getattr(self.page, "spojnice", None)
        if sp is not None and len(sp):
            p.setPen(QPen(QColor("#34D399"), 0))
            for a, b in sp.platne(self.page.seznam):
                p.drawLine(QPointF(-a.y, -a.x), QPointF(-b.y, -b.x))
        f = QFont()
        f.setPointSizeF(8.5)
        p.setFont(f)
        for b in self._body:
            x, y = -b.y, -b.x
            sel = b.cislo in vyb
            p.setPen(QPen(QColor("#F59E0B") if sel else QColor("#E5E7EB"), 0))
            r = (5 if sel else 3) * s
            p.drawLine(QPointF(x - r, y), QPointF(x + r, y))
            p.drawLine(QPointF(x, y - r), QPointF(x, y + r))
            radky = []
            if self.ch_cisla.isChecked():
                radky.append(b.cislo)
            if self.ch_vysky.isChecked() and b.z is not None:
                radky.append(f"{b.z:.2f}")
            if self.ch_kody.isChecked() and b.kod:
                radky.append(str(b.kod))
            if radky:
                p.save()
                p.translate(x, y)
                p.scale(s, -s)  # text v pixelech a nepřevrácený
                p.setPen(QColor("#FBBF24") if sel else QColor("#93C5FD"))
                for i, t in enumerate(radky):
                    p.drawText(QPointF(6, -4 + i * 12), t)
                p.restore()
        if len(self.mereni) == 2:
            a, b = self.mereni
            p.setPen(QPen(QColor("#22D3EE"), 0, Qt.DashLine))
            p.drawLine(QPointF(-a.y, -a.x), QPointF(-b.y, -b.x))

    # ------------------------------------------------------------ výběr a měření
    def najdi(self, x: float, y: float, tol_px: float = 10.0):
        s = 1.0 / max(1e-12, abs(self.pohled.transform().m11()))
        tol = tol_px * s
        best, bd = None, tol
        for b in self._body:
            d = math.hypot(-b.y - x, -b.x - y)
            if d <= bd:
                best, bd = b, d
        return best

    def _klik(self, x, y, ctrl):
        b = self.najdi(x, y)
        if self.mod == "spojnice":
            if b is None:  # klik do prázdna = konec lomené čáry
                self.mereni = []
                self.info.setText("Spojnice: klikněte na první bod")
                self.pohled.viewport().update()
                return
            if self.mereni and self.mereni[0] is not b:
                a = self.mereni[0]
                je = self.page.spojnice.prepni(a.cislo, b.cislo)
                self.page.uloz_spojnice()
                self.info.setText(f"Spojnice {a.cislo} – {b.cislo} {'přidána' if je else 'smazána'}; "
                                  f"pokračujte z bodu {b.cislo} (klik na prázdno = nová čára).")
            else:
                self.info.setText(f"Spojnice z bodu {b.cislo} → klikněte na další bod")
            self.mereni = [b]
            self.pohled.viewport().update()
            return
        if self.mod == "mereni":
            if b is None:
                return
            self.mereni = (self.mereni + [b])[-2:] if len(self.mereni) < 2 else [b]
            if len(self.mereni) == 2:
                self.info.setText(self.text_mereni(*self.mereni))
            else:
                self.info.setText(f"Měření: {b.cislo} → klikněte na druhý bod")
            self.pohled.viewport().update()
            return
        if b is None:
            if not ctrl:
                self.vyber = []
        elif ctrl:
            self.vyber = [c for c in self.vyber if c != b.cislo] if b.cislo in self.vyber else self.vyber + [b.cislo]
        else:
            self.vyber = [b.cislo]
        if b is not None:
            self.info.setText(f"Bod {b.cislo}: Y {b.y:.3f}  X {b.x:.3f}" + (f"  Z {b.z:.3f}" if b.z is not None else "")
                              + (f"  kód {b.kod}" if b.kod else ""))
        self.pohled.viewport().update()
        self.vybrano.emit(list(self.vyber))

    @staticmethod
    def text_mereni(a, b) -> str:
        d = V.delka(a, b)
        t = (f"{a.cislo} → {b.cislo}: délka {d:.3f} m, směrník {V.smernik(a, b):.4f} g, "
             f"ΔY {b.y - a.y:.3f}, ΔX {b.x - a.x:.3f}")
        if a.z is not None and b.z is not None:
            t += f", Δh {b.z - a.z:.3f}"
        return t

    def _mod_mereni(self, on: bool):
        if on and self.b_spoj.isChecked():
            self.b_spoj.setChecked(False)
        self.mod = "mereni" if on else "vyber"
        self.mereni = []
        self.info.setText("Měření: klikněte na první bod" if on else "Klik = výběr bodu (Ctrl = přidat).")
        self.pohled.viewport().update()

    def _mod_spojnice(self, on: bool):
        if on and self.b_mer.isChecked():
            self.b_mer.setChecked(False)
        self.mod = "spojnice" if on else "vyber"
        self.mereni = []
        self.info.setText("Spojnice: klikněte na první bod" if on else "Klik = výběr bodu (Ctrl = přidat).")
        self.pohled.viewport().update()

    def spojit_podle_kodu(self, kod: str | None = None, uzavrit: bool = False) -> int:
        if kod is None:
            from PySide6.QtWidgets import QInputDialog
            kody = self.page.seznam.kody()
            if not kody:
                self.info.setText("Body nemají kódy.")
                return 0
            kod, ok = QInputDialog.getItem(self, "Spojit podle kódu", "Kód bodů:", kody, 0, False)
            if not ok or not kod:
                return 0
        n = self.page.spojnice.z_kodu(self.page.seznam.body, kod, uzavrit)
        self.page.uloz_spojnice()
        self.info.setText(f"Kód {kod}: přidáno {n} spojnic.")
        return n

    def oznac(self, cisla: list[str]):
        """Výběr z tabulky → zvýraznit v grafice."""
        self.vyber = list(cisla)
        self.pohled.viewport().update()
