"""Pracovní plocha CAD (fáze 1): DXF na plátně, plynulý zoom a posun, kurzor se souřadnicemi S-JTSK,
úchyty, ortho / polární režim a příkazový řádek.

Vykreslení: ezdxf drawing add-on (MIT) do QGraphicsScene – každý prvek scény ví, ke které entitě patří.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QFileDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..cad.dokument import CadDokument
from ..cad.uchyty import TYPY, Uchyty, ortho, polarni, zadani_bodu


class CadView(QGraphicsView):
    mouseMoved = Signal(float, float)  # souřadnice DXF (po úchytu / ortho)
    clicked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QColor("#000000"))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.scale(1, -1)  # DXF: y nahoru
        self.uchyty: Uchyty | None = None
        self.uchyty_on = True
        self.ortho_on = False
        self.polar_on = False
        self.polar_krok = 50.0
        self.posledni: tuple[float, float] | None = None
        self.kurzor: tuple[float, float] | None = None
        self.uchyt = None
        self.gumicka = False  # čára od posledního bodu ke kurzoru (při zadávání)
        self._pan = None

    # ------------------------------------------------------------ zoom a posun
    def wheelEvent(self, e):  # noqa: N802
        f = 1.0015 ** e.angleDelta().y()
        self.scale(f, f)

    def zoom_all(self, rect: QRectF | None = None):
        r = rect or self.scene().itemsBoundingRect()
        if r.isEmpty():
            return
        self.fitInView(r.adjusted(-r.width() * 0.03, -r.height() * 0.03, r.width() * 0.03, r.height() * 0.03),
                       Qt.KeepAspectRatio)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.LeftButton and self.kurzor is not None:
            self.clicked.emit(*self.kurzor)
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._pan is not None:
            self._pan = None
            self.setCursor(Qt.CrossCursor)
            return
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            return
        p = self.mapToScene(e.position().toPoint())
        x, y = p.x(), p.y()
        self.uchyt = None
        if self.uchyty is not None and self.uchyty_on:
            tol = 12.0 / max(1e-12, abs(self.transform().m11()))
            self.uchyt = self.uchyty.najdi(x, y, tol, self.posledni)
            if self.uchyt is not None:
                x, y = self.uchyt.x, self.uchyt.y
        if self.uchyt is None and self.posledni is not None:
            if self.ortho_on:
                x, y = ortho(self.posledni, x, y)
            elif self.polar_on:
                x, y = polarni(self.posledni, x, y, self.polar_krok)
        self.kurzor = (x, y)
        self.mouseMoved.emit(x, y)
        self.viewport().update()

    def leaveEvent(self, e):  # noqa: N802
        self.kurzor = None
        self.viewport().update()
        super().leaveEvent(e)

    # ------------------------------------------------------------ kurzor, úchyt, gumička
    def drawForeground(self, p: QPainter, rect):  # noqa: N802
        if self.kurzor is None:
            return
        s = 1.0 / max(1e-12, abs(self.transform().m11()))
        x, y = self.kurzor
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(QPen(QColor(255, 255, 255, 140), 0))
        p.drawLine(QPointF(x - 2000 * s, y), QPointF(x + 2000 * s, y))
        p.drawLine(QPointF(x, y - 2000 * s), QPointF(x, y + 2000 * s))
        if self.gumicka and self.posledni is not None:
            p.setPen(QPen(QColor("#FBBF24"), 0, Qt.DashLine))
            p.drawLine(QPointF(*self.posledni), QPointF(x, y))
        if self.uchyt is not None:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor("#22D3EE"), 2 * s))
            r = 7 * s
            t = self.uchyt.typ
            if t == "konec":
                p.drawRect(QRectF(x - r, y - r, 2 * r, 2 * r))
            elif t in ("stred",):
                p.drawPolygon([QPointF(x, y + r), QPointF(x - r, y - r), QPointF(x + r, y - r)])
            elif t == "prusecik":
                p.drawLine(QPointF(x - r, y - r), QPointF(x + r, y + r))
                p.drawLine(QPointF(x - r, y + r), QPointF(x + r, y - r))
            elif t == "kolmice":
                p.drawLine(QPointF(x - r, y - r), QPointF(x + r, y - r))
                p.drawLine(QPointF(x, y - r), QPointF(x, y + r))
            else:
                p.drawEllipse(QPointF(x, y), r, r)


class CadPage(QWidget):
    """Stránka CAD: výkres DXF, příkazový řádek a stav (souřadnice, úchyty, ortho, polární)."""

    PRIKAZY = {"celý": "celý výkres (zoom)", "vzdálenost": "změřit vzdálenost a směrník mezi dvěma body",
               "otevři": "otevřít DXF", "ulož": "uložit DXF", "nápověda": "seznam příkazů"}
    ALIASY = {"c": "celý", "cel": "celý", "zoom": "celý", "za": "celý", "vzd": "vzdálenost", "dist": "vzdálenost",
              "di": "vzdálenost", "o": "otevři", "open": "otevři", "s": "ulož", "save": "ulož", "?": "nápověda",
              "help": "nápověda", "napoveda": "nápověda", "celý výkres": "celý", "cely": "celý",
              "vzdalenost": "vzdálenost", "otevri": "otevři", "uloz": "ulož"}

    def __init__(self, win=None, parent=None):
        super().__init__(parent)
        self.win = win
        self.dok: CadDokument | None = None
        self.sjtsk = True
        self._prikaz: str | None = None
        self._body: list[tuple[float, float]] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 6, 10, 6)
        self.b_open = QPushButton("Otevřít DXF…")
        self.b_new = QPushButton("Nový")
        self.b_save = QPushButton("Uložit")
        self.b_saveas = QPushButton("Uložit jako…")
        self.b_all = QPushButton("Celý výkres")
        self.b_check = QPushButton("Zkontrolovat")
        self.b_check.setToolTip("Uloží výkres a zkontroluje ho v Kontrole výkresu (chyby se ukážou na stránce "
                                "Výkres)")
        for b in (self.b_open, self.b_new, self.b_save, self.b_saveas, self.b_all, self.b_check):
            bar.addWidget(b)
        bar.addStretch(1)
        self.title = QLabel("Žádný výkres")
        bar.addWidget(self.title)
        lay.addLayout(bar)
        self.view = CadView()
        self.view.setCursor(Qt.CrossCursor)
        lay.addWidget(self.view, 1)
        self.historie = QPlainTextEdit()
        self.historie.setReadOnly(True)
        self.historie.setMaximumHeight(90)
        self.historie.setObjectName("cad_historie")
        lay.addWidget(self.historie)
        crow = QHBoxLayout()
        crow.setContentsMargins(10, 4, 10, 6)
        self.prikaz = QLineEdit()
        self.prikaz.setObjectName("cad_prikaz")
        self.prikaz.setPlaceholderText("Příkaz (např. vzd, celý, ?) nebo souřadnice „Y X“, „@dx,dy“, "
                                       "„@délka<směrník“ – Enter")
        crow.addWidget(QLabel("Příkaz:"))
        crow.addWidget(self.prikaz, 1)
        self.b_uchyty = QPushButton("Úchyty")
        self.b_ortho = QPushButton("Ortho")
        self.b_polar = QPushButton("Polární")
        for b, tip in ((self.b_uchyty, "Úchyty: koncový bod, střed, průsečík, kolmice, tečna (F3)"),
                       (self.b_ortho, "Jen vodorovně / svisle od posledního bodu (F8)"),
                       (self.b_polar, "Směr po násobcích úhlu (F10)")):
            b.setCheckable(True)
            b.setToolTip(tip)
            crow.addWidget(b)
        self.b_uchyty.setChecked(True)
        self.krok = QSpinBox()
        self.krok.setRange(1, 200)
        self.krok.setValue(50)
        self.krok.setSuffix(" g")
        self.krok.setToolTip("Krok polárního režimu v gonech")
        crow.addWidget(self.krok)
        self.coords = QLabel("Y –  X –")
        self.coords.setMinimumWidth(320)
        crow.addWidget(self.coords)
        lay.addLayout(crow)
        # signály
        self.b_open.clicked.connect(lambda: self.otevri())
        self.b_new.clicked.connect(self.novy)
        self.b_save.clicked.connect(lambda: self.uloz())
        self.b_saveas.clicked.connect(lambda: self.uloz(jako=True))
        self.b_all.clicked.connect(lambda: self.view.zoom_all())
        self.b_check.clicked.connect(self.zkontroluj)
        self.prikaz.returnPressed.connect(self._enter)
        self.view.mouseMoved.connect(self._pohyb)
        self.view.clicked.connect(self._klik)
        self.b_uchyty.toggled.connect(lambda on: setattr(self.view, "uchyty_on", on))
        self.b_ortho.toggled.connect(self._ortho)
        self.b_polar.toggled.connect(self._polar)
        self.krok.valueChanged.connect(lambda v: setattr(self.view, "polar_krok", float(v)))
        from PySide6.QtGui import QKeySequence, QShortcut
        for key, fn in (("F3", self.b_uchyty.toggle), ("F8", self.b_ortho.toggle), ("F10", self.b_polar.toggle),
                        ("Escape", self.zrus)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self.vypis("CAD – otevřete DXF nebo začněte nový výkres. Příkazy: „?“")

    # ------------------------------------------------------------ režimy
    def _ortho(self, on):
        self.view.ortho_on = on
        if on and self.b_polar.isChecked():
            self.b_polar.setChecked(False)

    def _polar(self, on):
        self.view.polar_on = on
        if on and self.b_ortho.isChecked():
            self.b_ortho.setChecked(False)

    def vypis(self, text: str):
        self.historie.appendPlainText(text)

    # ------------------------------------------------------------ dokument
    def nastav_dokument(self, dok: CadDokument):
        self.dok = dok
        self._vykresli()
        z = dok.zprava
        self.title.setText(dok.path.name if dok.path else "Nový výkres")
        ext = dok.rozsah()
        self.sjtsk = bool(ext and ext[2] < 0 and ext[3] < 0)  # S-JTSK z MicroStationu: záporné x, y
        self.vypis(z.text())
        self.view.zoom_all()

    def _vykresli(self):
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.config import Configuration
        from ezdxf.addons.drawing.pyqt import PyQtBackend
        sc = self.view.scene()
        sc.clear()
        if self.dok is None:
            return
        ctx = RenderContext(self.dok.doc)
        ctx.set_current_layout(self.dok.msp)
        try:
            ctx.current_layout_properties.set_colors("#000000")
        except Exception:  # noqa: BLE001
            pass
        backend = PyQtBackend(sc)
        try:
            Frontend(ctx, backend, config=Configuration()).draw_layout(self.dok.msp, finalize=True)
        except Exception as e:  # noqa: BLE001 – i z poškozeného výkresu ukázat, co jde
            self.vypis(f"Část výkresu nejde zobrazit: {e}")
        self.view.uchyty = Uchyty(self.dok.msp)

    def otevri(self, path: str | None = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Otevřít výkres DXF", "", "DXF (*.dxf)")
        if not path:
            return False
        try:
            dok = CadDokument.otevri(path)
        except ValueError as e:
            QMessageBox.warning(self, "CAD", str(e))
            return False
        self.nastav_dokument(dok)
        return True

    def novy(self):
        self.nastav_dokument(CadDokument())

    def uloz(self, jako: bool = False, path: str | None = None) -> Path | None:
        if self.dok is None:
            return None
        if path is None and (jako or self.dok.path is None):
            path, _ = QFileDialog.getSaveFileName(self, "Uložit výkres", str(self.dok.path or "vykres.dxf"),
                                                  "DXF R2000 (*.dxf)")
            if not path:
                return None
        try:
            p = self.dok.uloz(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "CAD", f"Výkres nejde uložit: {e}")
            return None
        self.title.setText(p.name)
        self.vypis(f"Uloženo: {p}")
        return p

    def zkontroluj(self):
        """Propojení s Kontrolou: uloží výkres a zkontroluje ho (chyby na stránce Výkres)."""
        if self.dok is None or self.win is None:
            return
        p = self.uloz()
        if p is None:
            return
        self.win.load_drawing_file(p)
        self.win.show_page("vykres")
        self.win.a_check.trigger()

    # ------------------------------------------------------------ kurzor a příkazy
    def _pohyb(self, x, y):
        u = self.view.uchyt
        su = f"   [{u.popis}]" if u is not None else ""
        if self.sjtsk:
            self.coords.setText(f"Y {-x:,.3f}   X {-y:,.3f}{su}".replace(",", " "))
        else:
            self.coords.setText(f"x {x:,.3f}   y {y:,.3f}{su}".replace(",", " "))

    def _klik(self, x, y):
        self._bod(x, y)

    def _bod(self, x, y):
        if self._prikaz == "vzdálenost":
            self._body.append((x, y))
            self.view.posledni = (x, y)
            self.view.gumicka = True
            if len(self._body) == 2:
                (x1, y1), (x2, y2) = self._body
                d = math.hypot(x2 - x1, y2 - y1)
                if self.sjtsk:  # směrník v S-JTSK (Y = −x, X = −y)
                    sig = (math.atan2(-(x2 - x1), -(y2 - y1)) * 200 / math.pi) % 400
                    self.vypis(f"Vzdálenost {d:.3f} m, směrník {sig:.4f} g, ΔY {-(x2 - x1):.3f}, ΔX {-(y2 - y1):.3f}")
                else:
                    a = (math.atan2(y2 - y1, x2 - x1) * 200 / math.pi) % 400
                    self.vypis(f"Vzdálenost {d:.3f}, úhel {a:.4f} g, Δx {x2 - x1:.3f}, Δy {y2 - y1:.3f}")
                self.zrus(tise=True)
            else:
                self.vypis("Druhý bod:")
        else:
            self.view.posledni = (x, y)

    def zrus(self, tise: bool = False):
        if self._prikaz and not tise:
            self.vypis("*zrušeno*")
        self._prikaz = None
        self._body = []
        self.view.gumicka = False
        self.view.viewport().update()

    def _enter(self):
        t = self.prikaz.text().strip()
        self.prikaz.clear()
        if not t:
            return
        self.proved(t)

    def proved(self, t: str):
        """Příkaz nebo souřadnice z příkazového řádku."""
        cmd = self.ALIASY.get(t.lower(), t.lower())
        if cmd in self.PRIKAZY:
            self.vypis(f"> {t}")
            if cmd == "celý":
                self.view.zoom_all()
            elif cmd == "nápověda":
                self.vypis("Příkazy: " + "; ".join(f"{k} – {v}" for k, v in self.PRIKAZY.items()))
                self.vypis("Souřadnice: „Y X“ (S-JTSK), „x=… y=…“, „@dx,dy“, „@délka<směrník[g]“. "
                           "Úchyty F3, Ortho F8, Polární F10, Esc zruší příkaz. Kolečko = zoom, "
                           "prostřední/pravé tlačítko = posun.")
            elif cmd == "vzdálenost":
                self._prikaz = "vzdálenost"
                self._body = []
                self.vypis("První bod:")
            elif cmd == "otevři":
                self.otevri()
            elif cmd == "ulož":
                self.uloz()
            return
        try:
            x, y = zadani_bodu(t, self.view.posledni, self.sjtsk)
        except ValueError as e:
            self.vypis(f"Neznámý příkaz nebo souřadnice: {e}")
            return
        self.vypis(f"> bod {(-x if self.sjtsk else x):.3f} {(-y if self.sjtsk else y):.3f}")
        self._bod(x, y)


__all__ = ["CadPage", "CadView", "TYPY"]
