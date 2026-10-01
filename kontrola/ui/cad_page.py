"""Pracovní plocha CAD: DXF na plátně, plynulý zoom a posun, kurzor se souřadnicemi S-JTSK, úchyty,
ortho / polární režim, příkazový řádek, kreslení a úpravy s neomezeným Zpět / Vpřed.

Vykreslení: ezdxf drawing add-on (MIT) do QGraphicsScene – každý prvek scény ví, ke které entitě patří,
takže po úpravě se překreslí jen změněné prvky.

Nástroje jsou generátory: postupně si říkají o vstup (bod, číslo, text, výběr, prvek) a uživatel ho zadá
kliknutím nebo z příkazového řádku – stejně jako v MicroStationu / AutoCADu.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from ..cad import upravy as U
from ..cad.dokument import CadDokument
from ..cad.uchyty import TYPY, Uchyty, ortho, polarni, zadani_bodu

GON = math.pi / 200


@dataclass
class Pozadavek:
    typ: str  # bod | cislo | text | vyber | prvek
    vyzva: str
    volitelne: bool = False
    slova: tuple = ()
    ref: tuple | None = None  # bod, od kterého vede gumička (a od kterého se měří délka kliknutím)
    vychozi: object = None


class CadView(QGraphicsView):
    mouseMoved = Signal(float, float)  # souřadnice DXF (po úchytu / ortho)
    clicked = Signal(float, float)
    doubleClicked = Signal(float, float)
    windowSelected = Signal(float, float, float, float)  # x0, y0, x1, y1 (zprava doleva = protínající)

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
        self.mys: tuple[float, float] | None = None  # skutečná poloha myši (bez úchytu) – pro výběr
        self.uchyt = None
        self.gumicka = False  # čára od posledního bodu ke kurzoru (při zadávání)
        self.vyber_oknem = True  # tažení levým tlačítkem = výběr oknem
        self.zvyraznene: list = []  # Shapely geometrie vybraných prvků
        self._pan = None
        self._okno_start: tuple[float, float] | None = None
        self._okno_px = None

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
            if self.vyber_oknem and self.mys is not None:
                self._okno_start = self.mys
                self._okno_px = e.position()
                return
            self.clicked.emit(*self.kurzor)
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and self.mys is not None:
            self.doubleClicked.emit(*self.mys)
            return
        super().mouseDoubleClickEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._pan is not None:
            self._pan = None
            self.setCursor(Qt.CrossCursor)
            return
        if self._okno_start is not None and e.button() == Qt.LeftButton:
            start, px = self._okno_start, self._okno_px
            self._okno_start = self._okno_px = None
            d = e.position() - px
            if abs(d.x()) + abs(d.y()) > 5 and self.mys is not None:
                self.windowSelected.emit(start[0], start[1], self.mys[0], self.mys[1])
            elif self.kurzor is not None:
                self.clicked.emit(*self.kurzor)
            self.viewport().update()
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
        self.najed(p.x(), p.y())

    def najed(self, x: float, y: float):
        """Kurzor na bod scény (úchyty, ortho, polární) – volá se z pohybu myši i z testů."""
        self.mys = (x, y)
        self.uchyt = None
        if self.uchyty is not None and self.uchyty_on and self._okno_start is None:
            tol = 12.0 / max(1e-12, abs(self.transform().m11()))
            self.uchyt = self.uchyty.najdi(x, y, tol, self.posledni)
            if self.uchyt is not None:
                x, y = self.uchyt.x, self.uchyt.y
        if self.uchyt is None and self.posledni is not None and self.gumicka:
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

    # ------------------------------------------------------------ kurzor, úchyt, gumička, výběr
    def drawForeground(self, p: QPainter, rect):  # noqa: N802
        s = 1.0 / max(1e-12, abs(self.transform().m11()))
        if self.zvyraznene:
            p.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor("#F59E0B"), 0)
            pen.setCosmetic(True)
            pen.setWidthF(2.5)
            p.setPen(pen)
            for g in self.zvyraznene:
                _kresli_geometrii(p, g, s)
        if self.kurzor is None:
            return
        x, y = self.kurzor
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(QPen(QColor(255, 255, 255, 140), 0))
        p.drawLine(QPointF(x - 2000 * s, y), QPointF(x + 2000 * s, y))
        p.drawLine(QPointF(x, y - 2000 * s), QPointF(x, y + 2000 * s))
        if self._okno_start is not None and self.mys is not None:
            (x0, y0), (x1, y1) = self._okno_start, self.mys
            protinajici = x1 < x0
            pen = QPen(QColor("#22C55E") if protinajici else QColor("#3B82F6"), 0,
                       Qt.DashLine if protinajici else Qt.SolidLine)
            p.setPen(pen)
            p.setBrush(QColor(34, 197, 94, 30) if protinajici else QColor(59, 130, 246, 30))
            p.drawRect(QRectF(QPointF(min(x0, x1), min(y0, y1)), QPointF(max(x0, x1), max(y0, y1))))
            p.setBrush(Qt.NoBrush)
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


def _kresli_geometrii(p: QPainter, g, s: float):
    t = g.geom_type
    if t == "Point":
        r = 4 * s
        p.drawRect(QRectF(g.x - r, g.y - r, 2 * r, 2 * r))
    elif t in ("LineString", "LinearRing"):
        pts = [QPointF(x, y) for x, y, *_ in g.coords]
        p.drawPolyline(pts)
    elif t == "Polygon":
        _kresli_geometrii(p, g.exterior, s)
    elif hasattr(g, "geoms"):
        for q in g.geoms:
            _kresli_geometrii(p, q, s)


class CadPage(QWidget):
    """Stránka CAD: výkres DXF, příkazový řádek, kreslení, úpravy a stav (souřadnice, úchyty, ortho…)."""

    PRIKAZY = {
        "celý": "celý výkres (zoom)", "vzdálenost": "změřit vzdálenost a směrník mezi dvěma body",
        "otevři": "otevřít DXF", "ulož": "uložit DXF", "nápověda": "seznam příkazů",
        "bod": "bod", "úsečka": "úsečky (řetězec, Enter = konec, z = zpět o bod)",
        "polylinie": "lomená čára (k = uzavřít, Enter = konec)", "obdélník": "obdélník ze dvou rohů",
        "kružnice": "kružnice (střed a poloměr)", "oblouk": "oblouk třemi body", "elipsa": "elipsa",
        "křivka": "křivka (spline) body", "text": "text", "šrafa": "šrafa uvnitř uzavřeného prvku",
        "kóta": "kóta délky", "smaž": "smazat výběr (Delete)", "posun": "posunout výběr",
        "kopie": "kopírovat výběr (i vícekrát)", "otoč": "otočit výběr", "měřítko": "změnit velikost výběru",
        "zrcadli": "zrcadlit výběr", "rovnoběžka": "rovnoběžka (offset)", "ořež": "oříznout k průsečíkům",
        "prodluž": "prodloužit úsečku k prvku", "zaobli": "zaoblit / spojit roh dvou úseček",
        "rozpoj": "rozpojit polylinie, bloky, kóty", "spoj": "spojit navazující prvky do polylinie",
        "vrstva": "aktuální vrstva / přesun výběru do vrstvy", "barva": "barva (0–256) nových prvků / výběru",
        "vše": "vybrat vše", "zpět": "vrátit poslední změnu (Ctrl+Z)", "vpřed": "znovu provést (Ctrl+Y)",
        "info": "vlastnosti vybraného prvku", "výměra": "výměra a obvod vybraného uzavřeného prvku",
        "model": "přepnout model / list („model List 1“)", "list": "nový výkresový list („list Výkres A3“)",
        "výřez": "výřez modelu na listu v měřítku", "reference": "správce referencí (připojit DXF podklad)",
        "vlastnosti": "vlastnosti vybraného prvku (i dvojklik)", "podobné": "vybrat podobné (stejný typ a vrstva)",
        "najdi": "najít text („najdi 12/1“)", "nahraď": "nahradit text („nahraď staré / nové“)",
        "měř plochu": "výměra a obvod klikáním na body (Enter = konec)", "měř úhel": "úhel mezi třemi body",
        "body": "body ze seznamu souřadnic do výkresu", "tisk": "tisk do PDF", "razítko": "rámeček a razítko na list", "vrstvy": "správce vrstev", "atributy": "atributy ze zadání – kontrola a úprava", "prvek": "druh prvku ze zadání (např. „prvek budovy“)", "blok": "vytvořit blok (buňku) z výběru", "vlož": "vložit blok",
    }
    ALIASY = {
        "c": "celý", "cel": "celý", "zoom": "celý", "za": "celý", "celý výkres": "celý", "cely": "celý",
        "vzd": "vzdálenost", "dist": "vzdálenost", "di": "vzdálenost", "vzdalenost": "vzdálenost",
        "o": "otevři", "open": "otevři", "otevri": "otevři", "s": "ulož", "save": "ulož", "uloz": "ulož",
        "?": "nápověda", "help": "nápověda", "napoveda": "nápověda",
        "po": "bod", "point": "bod", "u": "úsečka", "l": "úsečka", "line": "úsečka", "usecka": "úsečka",
        "pl": "polylinie", "pline": "polylinie", "lomená": "polylinie", "obd": "obdélník", "rec": "obdélník",
        "obdelnik": "obdélník", "kr": "kružnice", "circle": "kružnice", "kruznice": "kružnice",
        "ob": "oblouk", "a": "oblouk", "arc": "oblouk", "el": "elipsa", "ellipse": "elipsa",
        "spl": "křivka", "spline": "křivka", "krivka": "křivka", "t": "text", "dt": "text",
        "h": "šrafa", "hatch": "šrafa", "sraf": "šrafa", "srafa": "šrafa", "ko": "kóta", "dim": "kóta",
        "kota": "kóta", "del": "smaž", "e": "smaž", "erase": "smaž", "smaz": "smaž",
        "m": "posun", "move": "posun", "cp": "kopie", "copy": "kopie", "ro": "otoč", "rotate": "otoč",
        "otoc": "otoč", "sc": "měřítko", "scale": "měřítko", "meritko": "měřítko", "mi": "zrcadli",
        "mirror": "zrcadli", "of": "rovnoběžka", "offset": "rovnoběžka", "rovnobezka": "rovnoběžka",
        "tr": "ořež", "trim": "ořež", "orez": "ořež", "ex": "prodluž", "extend": "prodluž",
        "prodluz": "prodluž", "f": "zaobli", "fillet": "zaobli", "x": "rozpoj", "explode": "rozpoj",
        "j": "spoj", "join": "spoj", "la": "vrstva", "layer": "vrstva", "col": "barva", "color": "barva", "co": "barva", "lc": "styl", "wt": "tloušťka",
        "tloustka": "tloušťka", "lv": "vrstva",
        "vse": "vše", "all": "vše", "undo": "zpět", "zpet": "zpět", "redo": "vpřed", "vpred": "vpřed",
        "li": "info", "list": "info", "lm": "vrstvy", "layers": "vrstvy", "mp": "měř plochu", "plocha bodů": "měř plochu",
        "mer plochu": "měř plochu", "measure area": "měř plochu", "mu": "měř úhel", "mer uhel": "měř úhel",
        "uhel": "měř úhel", "úhel": "měř úhel", "pr": "vlastnosti", "props": "vlastnosti",
        "podobne": "podobné", "similar": "podobné", "find": "najdi", "nahrad": "nahraď", "replace": "nahraď", "plot": "tisk", "print": "tisk",
        "pdf": "tisk", "razitko": "razítko", "mv": "výřez", "viewport": "výřez",
        "vyrez": "výřez", "xr": "reference", "xref": "reference", "ref": "reference", "layout": "list", "b": "blok", "block": "blok",
        "cell": "blok", "i": "vlož", "insert": "vlož", "vloz": "vlož", "bunka": "blok", "buňka": "blok", "plocha": "výměra", "area": "výměra", "vymera": "výměra",
    }
    VYBEROVE = {"smaž", "posun", "kopie", "otoč", "měřítko", "zrcadli", "rozpoj", "spoj", "blok"}

    def __init__(self, win=None, parent=None):
        super().__init__(parent)
        self.win = win
        self.dok: CadDokument | None = None
        self.sjtsk = True
        self._prikaz: str | None = None
        self._body: list[tuple[float, float]] = []
        self._gen = None
        self._req: Pozadavek | None = None
        self._posledni_prikaz: str | None = None
        self.vyber: list = []
        self.historie_zmen: U.Historie | None = None
        self.kresleni: U.Kresleni | None = None
        self.index: U.IndexVyberu | None = None
        self._polozky: dict[int, list] = {}  # id(entity) → položky scény
        self.vyska_textu = 2.5
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
        self.b_undo = QPushButton("↶")
        self.b_undo.setToolTip("Zpět (Ctrl+Z)")
        self.b_redo = QPushButton("↷")
        self.b_redo.setToolTip("Vpřed (Ctrl+Y)")
        self.b_tisk = QPushButton("Tisk do PDF…")
        self.b_tisk.setToolTip("Vytisknout model v měřítku nebo list do PDF (vektorově, na bílý papír)")
        self.b_check = QPushButton("Zkontrolovat")
        self.b_check.setToolTip("Uloží výkres a zkontroluje ho v Kontrole výkresu (chyby se ukážou na stránce "
                                "Výkres)")
        for b in (self.b_open, self.b_new, self.b_save, self.b_saveas, self.b_all, self.b_undo, self.b_redo,
                  self.b_tisk, self.b_check):
            bar.addWidget(b)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Vrstva:"))
        self.vrstvy = QComboBox()
        self.vrstvy.setMinimumWidth(140)
        self.vrstvy.setToolTip("Aktuální vrstva pro nové prvky")
        bar.addWidget(self.vrstvy)
        bar.addWidget(QLabel("Model:"))
        self.modely = QComboBox()
        self.modely.setMinimumWidth(120)
        self.modely.setToolTip("Model výkresu nebo list (výkresový list s výřezy, rámečkem a razítkem)")
        bar.addWidget(self.modely)
        self.b_ref = QPushButton("Reference…")
        self.b_ref.setToolTip("Připojit jiný výkres DXF jako podklad (jen pro čtení, přichytávání, kopírování)")
        bar.addWidget(self.b_ref)
        self.b_vrstvy = QPushButton("Vrstvy…")
        self.b_vrstvy.setToolTip("Správce vrstev: zapnutí, zámek, barva, typ čáry, nová, přejmenovat, smazat")
        bar.addWidget(self.b_vrstvy)
        bar.addStretch(1)
        self.title = QLabel("Žádný výkres")
        bar.addWidget(self.title)
        lay.addLayout(bar)
        # nástroje
        tools = QHBoxLayout()
        tools.setContentsMargins(10, 0, 10, 4)
        self.nastroje: dict[str, QToolButton] = {}
        for cmd, label in (("úsečka", "Úsečka"), ("polylinie", "Polylinie"), ("obdélník", "Obdélník"),
                           ("kružnice", "Kružnice"), ("oblouk", "Oblouk"), ("elipsa", "Elipsa"),
                           ("křivka", "Křivka"), ("bod", "Bod"), ("text", "Text"), ("šrafa", "Šrafa"),
                           ("kóta", "Kóta"), (None, None), ("posun", "Posun"), ("kopie", "Kopie"),
                           ("otoč", "Otoč"), ("měřítko", "Měřítko"), ("zrcadli", "Zrcadli"),
                           ("rovnoběžka", "Rovnoběžka"), ("ořež", "Ořež"), ("prodluž", "Prodluž"),
                           ("zaobli", "Zaobli"), ("spoj", "Spoj"), ("rozpoj", "Rozpoj"), ("smaž", "Smaž")):
            if cmd is None:
                tools.addSpacing(14)
                continue
            b = QToolButton()
            b.setText(label)
            b.setToolTip(self.PRIKAZY[cmd])
            b.clicked.connect(lambda _=False, c=cmd: self.proved(c))
            tools.addWidget(b)
            self.nastroje[cmd] = b
        tools.addStretch(1)
        lay.addLayout(tools)
        zrow = QHBoxLayout()
        zrow.setContentsMargins(10, 0, 10, 4)
        self.b_novy_zadani = QPushButton("Nový podle zadání")
        self.b_novy_zadani.setToolTip("Založí výkres se všemi vrstvami, styly čar, písmy a buňkami podle pravidel "
                                      "ze zadání (Zadání → Pravidla, Směrnice, vzorový výkres)")
        zrow.addWidget(self.b_novy_zadani)
        zrow.addWidget(QLabel("Kreslím:"))
        self.predvolby_cb = QComboBox()
        self.predvolby_cb.setMinimumWidth(360)
        self.predvolby_cb.setToolTip("Druh prvku ze zadání – vrstva, barva, styl, tloušťka a písmo se nastaví samy")
        zrow.addWidget(self.predvolby_cb, 1)
        self.b_na_vyber = QPushButton("Použít na výběr")
        self.b_na_vyber.setToolTip("Vybraným prvkům nastaví atributy zvoleného druhu prvku")
        zrow.addWidget(self.b_na_vyber)
        self.b_body = QPushButton("Body ze seznamu…")
        self.b_body.setToolTip("Vložit body ze seznamu souřadnic (Výpočty nebo soubor) na jejich souřadnice, "
                               "s čísly a výškami v hladinách podle zadání")
        zrow.addWidget(self.b_body)
        self.b_atributy = QPushButton("Atributy ze zadání…")
        self.b_atributy.setToolTip("Zkontrolovat a upravit atributy, které aplikace načetla ze zadání (vrstva, "
                                   "barva, styl, tloušťka, písmo…) a ověřit, že nakreslené prvky projdou kontrolou")
        zrow.addWidget(self.b_atributy)
        self.b_tahak = QPushButton("Tahák atributů…")
        self.b_tahak.setToolTip("Přehled atributů všech prvků ze zadání s řádky key-in pro MicroStation (HTML, "
                                "dá se vytisknout)")
        zrow.addWidget(self.b_tahak)
        self.predvolba_info = QLabel()
        self.predvolba_info.setObjectName("predvolba_info")
        zrow.addWidget(self.predvolba_info, 1)
        lay.addLayout(zrow)
        self._predvolby: list = []
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
        self.vyzva = QLabel("Příkaz:")
        crow.addWidget(self.vyzva)
        self.prikaz = QLineEdit()
        self.prikaz.setObjectName("cad_prikaz")
        self.prikaz.setPlaceholderText("Příkaz (u, pl, kr, m, tr, ?) nebo souřadnice „Y X“, „@dx,dy“, "
                                       "„@délka<směrník“ – Enter")
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
        self.aktivni = QLabel("")
        self.aktivni.setObjectName("cad_aktivni")
        self.aktivni.setToolTip("Aktivní atributy pro nové prvky (jako v MicroStationu)")
        crow.addWidget(self.aktivni)
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
        self.b_undo.clicked.connect(self.undo)
        self.b_redo.clicked.connect(self.redo)
        self.b_check.clicked.connect(self.zkontroluj)
        self.b_tisk.clicked.connect(lambda: self.tisk_pdf())
        self.b_vrstvy.clicked.connect(lambda: self.spravce_vrstev())
        self.b_ref.clicked.connect(lambda: self.spravce_referenci())
        self.modely.currentTextChanged.connect(lambda t: self.nastav_model(t) if t else None)
        self.b_novy_zadani.clicked.connect(lambda: self.novy_podle_zadani())
        self.predvolby_cb.currentIndexChanged.connect(self._predvolba_zmenena)
        self.b_na_vyber.clicked.connect(self.predvolba_na_vyber)
        self.b_tahak.clicked.connect(lambda: self.uloz_tahak(otevrit=True))
        self.b_atributy.clicked.connect(lambda: self.atributy_zadani())
        self.b_body.clicked.connect(lambda: self.body_ze_seznamu())
        self.vrstvy.currentTextChanged.connect(self._vrstva_zmenena)
        self.prikaz.returnPressed.connect(self._enter)
        self.view.mouseMoved.connect(self._pohyb)
        self.view.clicked.connect(self._klik)
        self.view.windowSelected.connect(self._okno)
        self.view.doubleClicked.connect(self._dvojklik)
        self.b_uchyty.toggled.connect(lambda on: setattr(self.view, "uchyty_on", on))
        self.b_ortho.toggled.connect(self._ortho)
        self.b_polar.toggled.connect(self._polar)
        self.krok.valueChanged.connect(lambda v: setattr(self.view, "polar_krok", float(v)))
        from PySide6.QtGui import QKeySequence, QShortcut
        for key, fn in (("F3", self.b_uchyty.toggle), ("F8", self.b_ortho.toggle), ("F10", self.b_polar.toggle),
                        ("Escape", self.zrus), ("Delete", lambda: self.proved("smaž"))):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self._aktualizuj_tlacitka()
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
        self.zrus(tise=True)
        self.dok = dok
        self.prostor = dok.msp  # aktuální model (Model nebo list)
        self._historie_prostoru = {}
        self.historie_zmen = U.Historie(dok.msp)
        self.kresleni = U.Kresleni(dok.msp, self.historie_zmen)
        self._historie_prostoru[dok.msp.name] = (self.historie_zmen, self.kresleni)
        from ..cad import reference as R
        self.reference = R.najdi(dok.doc, dok.path.parent if dok.path else None)
        for r in self.reference:
            if r.chyba:
                self.vypis(f"⚠ Reference {r.cesta.name}: {r.chyba}")
        if self.predvolba is not None:
            self.kresleni.nastav_predvolbu(self.predvolba)
        self._ulozena_zmena = 0
        self.vyber = []
        self._vykresli()
        z = dok.zprava
        self._titulek()
        ext = dok.rozsah()
        self.sjtsk = bool(ext and ext[2] < 0 and ext[3] < 0)  # S-JTSK z MicroStationu: záporné x, y
        self.vypis(z.text())
        self._napln_vrstvy()
        self._napln_modely()
        self.view.zoom_all()
        self._aktualizuj_tlacitka()
        self.aktivni_atributy()

    # ------------------------------------------------------------ zadání → předvolby
    def _pravidla(self):
        pr = getattr(self.win, "project", None) if self.win is not None else None
        return pr.rules if pr is not None and pr.rules.pravidla else None

    def obnov_predvolby(self):
        from ..cad.zadani import predvolby
        rs = self._pravidla()
        self._predvolby = predvolby(rs) if rs is not None else []
        cur = self.predvolby_cb.currentText()
        self.predvolby_cb.blockSignals(True)
        self.predvolby_cb.clear()
        self.predvolby_cb.addItem("(volně – bez předvolby)" if self._predvolby else
                                  "(nahrajte pravidla v Zadání – pak se atributy nastaví samy)")
        for p in self._predvolby:
            self.predvolby_cb.addItem(f"{p.nazev}  ·  {p.geometrie or '?'}")
        i = self.predvolby_cb.findText(cur)
        self.predvolby_cb.setCurrentIndex(max(0, i))
        self.predvolby_cb.blockSignals(False)
        self.b_novy_zadani.setEnabled(bool(self._predvolby))
        self.b_tahak.setEnabled(bool(self._predvolby))
        self.b_atributy.setEnabled(self.win is not None and getattr(self.win, "project", None) is not None)
        self.predvolby_cb.setEnabled(bool(self._predvolby))

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.obnov_predvolby()

    @property
    def predvolba(self):
        i = self.predvolby_cb.currentIndex() - 1
        return self._predvolby[i] if 0 <= i < len(self._predvolby) else None

    def vyber_predvolbu(self, text: str) -> bool:
        """Zvolí druh prvku podle části názvu nebo kódu (i z příkazového řádku: „prvek budovy“)."""
        t = text.strip().lower()
        for i, p in enumerate(self._predvolby):
            if t and (t == p.kod.lower() or t in p.nazev.lower()):
                self.predvolby_cb.setCurrentIndex(i + 1)
                return True
        return False

    def _predvolba_zmenena(self, _i=None):
        p = self.predvolba
        if self.kresleni is None:
            return
        self.kresleni.nastav_predvolbu(p)
        if p is None:
            self.predvolba_info.setText("")
            return
        if p.vrstva not in self.dok.doc.layers:
            self.dok.doc.layers.add(p.vrstva)
        for lt in (p.typ_cary,):
            if lt not in ("BYLAYER", "CONTINUOUS") and lt not in self.dok.doc.linetypes:
                from ..cad.zadani import priprav_dokument
                priprav_dokument(self.dok.doc, self._pravidla())
        if p.textovy_styl and p.textovy_styl not in self.dok.doc.styles:
            from ..cad.zadani import priprav_dokument
            priprav_dokument(self.dok.doc, self._pravidla())
        self._napln_vrstvy()
        if p.vyska:
            self.vyska_textu = p.vyska
        self.predvolba_info.setText(p.popis())
        self.aktivni_atributy()
        self.predvolba_info.setToolTip("\n".join([p.popis()] + p.poznamky))
        self.vypis(f"Kreslím: {p.nazev} – {p.popis()}" + ("".join(f"\n  ⚠ {x}" for x in p.poznamky)))
        if self._gen is None and not self._prikaz:
            self.proved(p.nastroj)

    def predvolba_na_vyber(self):
        p = self.predvolba
        if p is None or not self.vyber or self.dok is None:
            self.vypis("Vyberte prvky a zvolte druh prvku v poli „Kreslím“.")
            return
        ents = list(self.vyber)
        texty = [e for e in ents if e.dxftype() in ("TEXT", "MTEXT")]
        ostatni = [e for e in ents if e not in texty]
        k = self.kresleni
        nove = []
        if ostatni:
            nove += U.zmen_vlastnosti(self.prostor, self.historie_zmen, ostatni, **k._attr())
            self._po_zmene(nove, ostatni)
        if texty:
            a = k._attr(text=True)
            if p.vyska:
                a["height"] = p.vyska
            nt = U.zmen_vlastnosti(self.prostor, self.historie_zmen, texty, **a)
            self._po_zmene(nt, texty)
            nove += nt
        self.vyber = nove
        self._zvyrazni()
        self.vypis(f"{len(nove)} prvků nastaveno na „{p.nazev}“.")

    def body_ze_seznamu(self, modal: bool = True):
        if self.dok is None:
            self.novy_podle_zadani(vzory=None) if self._pravidla() is not None else self.novy()
        from .cad_body import BodyDialog
        d = BodyDialog(self)
        if modal:
            d.exec()
        return d

    def atributy_zadani(self, modal: bool = True):
        if self.win is None or getattr(self.win, "project", None) is None:
            return None
        from .cad_atributy import AtributyDialog
        d = AtributyDialog(self)
        if modal:
            d.exec()
        return d

    def uloz_tahak(self, path=None, otevrit: bool = False):
        from ..cad.zadani import tahak_html
        rs = self._pravidla()
        if rs is None:
            self.vypis("V projektu nejsou pravidla ze zadání.")
            return None
        pr = self.win.project
        out = Path(path) if path else Path(pr.root) / "tahak_atributu.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(tahak_html(rs, f"Atributy podle zadání – {pr.name if hasattr(pr, 'name') else ''}".rstrip(" –")),
                       encoding="utf-8")
        self.vypis(f"Tahák atributů uložen: {out}")
        if otevrit:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        return out

    def novy_podle_zadani(self, vzory=None):
        from ..cad.zadani import novy_dokument
        rs = self._pravidla()
        if rs is None:
            self.vypis("V projektu nejsou pravidla ze zadání – nahrajte Směrnici nebo zadání na stránce Zadání.")
            return None
        if not self._zahodit_zmeny():
            return None
        if vzory is None:
            pr = self.win.project
            vzory = [a.path for a in pr.attachments("vzor")]
        dok, zprava = novy_dokument(rs, vzory)
        self.nastav_dokument(dok)
        self.sjtsk = rs.rozsah == "sjtsk" or rs.rozsah is None
        self.obnov_predvolby()
        self.vypis("Výkres podle zadání připraven:\n  " + "\n  ".join(zprava))
        return dok

    def _napln_vrstvy(self):
        self.vrstvy.blockSignals(True)
        self.vrstvy.clear()
        if self.dok is not None:
            self.vrstvy.addItems(sorted((ly.dxf.name for ly in self.dok.doc.layers), key=str.lower))
            self.vrstvy.setCurrentText(self.kresleni.vrstva)
        self.vrstvy.blockSignals(False)

    def _vrstva_zmenena(self, name: str):
        if self.kresleni is not None and name:
            self.kresleni.vrstva = name
            self.aktivni_atributy()

    def _titulek(self):
        if self.dok is None:
            self.title.setText("Žádný výkres")
            return
        n = self.dok.path.name if self.dok.path else "Nový výkres"
        self.title.setText(n + (" *" if self.neulozeno else ""))

    @property
    def neulozeno(self) -> bool:
        return self.historie_zmen is not None and self.historie_zmen.zmena != getattr(self, "_ulozena_zmena", 0)

    def _vykresli(self):
        """Celé vykreslení výkresu (po otevření)."""
        sc = self.view.scene()
        sc.clear()
        self._polozky = {}
        if self.dok is None:
            return
        if not self._je_model():
            self._kresli_papir()
        self._kresli_entity(self.prostor, cely=True)
        self._kresli_reference()
        if not self._je_model():
            self._kresli_ramecky_vyrezu()
        self._obnov_indexy()

    def _kresli_papir(self):
        """List: bílý okraj papíru a tečkovaně tisknutelná oblast (jako list v MicroStationu)."""
        from PySide6.QtGui import QBrush, QPen
        sc = self.view.scene()
        try:
            (x0, y0), (x1, y1) = self.prostor.get_paper_limits()
            w, h = float(x1 - x0), float(y1 - y0)
        except Exception:  # noqa: BLE001
            x0, y0, w, h = 0.0, 0.0, 420.0, 297.0
        if w <= 0 or h <= 0:
            x0, y0, w, h = 0.0, 0.0, 420.0, 297.0
        pen = QPen(QColor("#9CA3AF"), 0)
        r = sc.addRect(QRectF(x0, y0, w, h), pen, QBrush(QColor("#15171C")))
        r.setZValue(-30)

    def _kresli_ramecky_vyrezu(self):
        from PySide6.QtGui import QPen
        sc = self.view.scene()
        pen = QPen(QColor("#60A5FA"), 0, Qt.DashLine)
        for vp in self.prostor.query("VIEWPORT"):
            if vp.dxf.get("id", 0) == 1:
                continue
            c, w, h = vp.dxf.center, vp.dxf.width, vp.dxf.height
            it = sc.addRect(QRectF(c.x - w / 2, c.y - h / 2, w, h), pen)
            it.setZValue(50)

    # ------------------------------------------------------------ modely (Model + listy)
    def _napln_modely(self):
        self.modely.blockSignals(True)
        self.modely.clear()
        if self.dok is not None:
            self.modely.addItems(self.dok.doc.layout_names_in_taborder())
            self.modely.setCurrentText(self.prostor.name)
        self.modely.blockSignals(False)

    def nastav_model(self, nazev: str) -> bool:
        if self.dok is None or nazev == getattr(self.prostor, "name", None):
            return False
        try:
            lay = self.dok.doc.layouts.get(nazev)
        except Exception:  # noqa: BLE001
            self.vypis(f"Model {nazev} ve výkresu není.")
            return False
        self.zrus(tise=True)
        zmena = self.historie_zmen.zmena if self.historie_zmen else 0
        self.prostor = lay
        if lay.name not in self._historie_prostoru:
            h = U.Historie(lay)
            h.zmena = zmena
            k = U.Kresleni(lay, h)
            if self.kresleni is not None:
                k.vrstva = self.kresleni.vrstva
            self._historie_prostoru[lay.name] = (h, k)
        h, k = self._historie_prostoru[lay.name]
        h.zmena = max(h.zmena, zmena)
        self.historie_zmen, self.kresleni = h, k
        if self.predvolba is not None:
            k.nastav_predvolbu(self.predvolba)
        self.vyber = []
        self._vykresli()
        self.view.zoom_all()
        self._napln_modely()
        self._aktualizuj_tlacitka()
        self.vypis(f"Model: {lay.name}" + ("" if self._je_model() else " (list – souřadnice v mm na papíře)"))
        return True

    def novy_list(self, nazev: str | None = None) -> str | None:
        if self.dok is None:
            return None
        nazev = (nazev or "").strip() or f"List {len(self.dok.doc.layout_names()) }"
        if nazev in self.dok.doc.layout_names():
            self.vypis(f"List {nazev} už existuje.")
            return None
        lay = self.dok.doc.layouts.new(nazev)
        try:
            lay.page_setup(size=(420, 297), margins=(10, 10, 10, 10), units="mm")  # A3 na šířku
        except Exception:  # noqa: BLE001
            pass
        if self.historie_zmen is not None:
            self.historie_zmen.zmena += 1
        self._napln_modely()
        self.nastav_model(nazev)
        return nazev

    def _je_model(self) -> bool:
        return self.dok is not None and self.prostor is self.dok.msp

    def _kresli_reference(self):
        """Reference pod výkresem: poloprůhledně, nejdou vybrat ani upravit (jako v MicroStationu)."""
        from PySide6.QtGui import QTransform
        from PySide6.QtWidgets import QGraphicsItemGroup
        sc = self.view.scene()
        self._ref_skupiny = {}
        if not self._je_model():
            return
        for r in getattr(self, "reference", []):
            if not r.viditelna or r.doc is None or not r.pripojena:
                continue
            pred = set(id(i) for i in sc.items())
            try:
                fe = self._frontend(r.doc, r.doc.modelspace())
                fe.draw_layout(r.doc.modelspace(), finalize=False)
            except Exception as e:  # noqa: BLE001
                self.vypis(f"⚠ Reference {r.cesta.name} nejde zobrazit: {e}")
                continue
            nove = [i for i in sc.items() if id(i) not in pred]
            g = QGraphicsItemGroup()
            sc.addItem(g)
            for it in nove:
                g.addToGroup(it)
            g.setTransform(QTransform(*r.qt_matice()[:4], *r.qt_matice()[4:]))
            g.setOpacity(0.55)
            g.setZValue(-10)
            self._ref_skupiny[r.nazev] = g

    def _frontend(self, doc=None, layout=None):
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.config import Configuration
        from ezdxf.addons.drawing.pyqt import PyQtBackend
        doc = doc or self.dok.doc
        ctx = RenderContext(doc)
        ctx.set_current_layout(layout or self.prostor)
        try:
            ctx.current_layout_properties.set_colors("#000000")
        except Exception:  # noqa: BLE001
            pass
        from ezdxf.addons.drawing.config import BackgroundPolicy
        # tmavé pozadí i na listech – jinak by ezdxf počítal s bílým papírem a bílé čáry by kreslil černě
        cfg = Configuration(background_policy=BackgroundPolicy.BLACK)
        return Frontend(ctx, PyQtBackend(self.view.scene()), config=cfg)

    def _kresli_entity(self, entity, cely: bool = False):
        from ezdxf.addons.drawing.pyqt import CorrespondingDXFEntity, CorrespondingDXFParentStack
        sc = self.view.scene()
        pred = set(id(i) for i in sc.items()) if not cely else set()
        try:
            fe = self._frontend()
            if cely:
                fe.draw_layout(self.prostor, finalize=True)
            else:
                fe.draw_entities(entity)
        except Exception as e:  # noqa: BLE001 – i z poškozeného výkresu ukázat, co jde
            self.vypis(f"Část výkresu nejde zobrazit: {e}")
        for it in sc.items():
            if id(it) in pred:
                continue
            stack = it.data(CorrespondingDXFParentStack) or ()
            e = stack[0] if stack else it.data(CorrespondingDXFEntity)
            if e is not None:
                self._polozky.setdefault(id(e), []).append(it)

    def _obnov_indexy(self):
        msp = self.prostor
        skryte, zamcene = set(), set()
        for ly in self.dok.doc.layers:
            if ly.is_off() or ly.is_frozen():
                skryte.add(ly.dxf.name)
            if ly.is_locked():
                zamcene.add(ly.dxf.name)
        viditelne = [e for e in msp if e.dxf.get("layer", "0") not in skryte]
        if self._je_model():
            for r in getattr(self, "reference", []):
                if r.viditelna and r.uchyty and r.pripojena:
                    viditelne += r.prvky_pro_uchyty()
        self.view.uchyty = Uchyty(viditelne)
        self.index = U.IndexVyberu(msp)
        nevybiratelne = skryte | zamcene
        if nevybiratelne:
            self.index.polozky = [p for p in self.index.polozky if p[0].dxf.get("layer", "0") not in nevybiratelne]

    def spravce_vrstev(self, modal: bool = True):
        if self.dok is None:
            return None
        from .cad_vrstvy import VrstvyDialog
        d = VrstvyDialog(self)
        if modal:
            d.exec()
        return d

    def vrstvy_zmeneny(self):
        """Změna tabulky vrstev (zapnutí, zámek, barva…): překreslit, obnovit výběr a seznam vrstev."""
        if self.historie_zmen is not None:
            self.historie_zmen.zmena += 1
        self._vykresli()
        self.vyber = [e for e in self.vyber if self.index and self.index.geometrie(e) is not None]
        self._zvyrazni()
        self._napln_vrstvy()
        self._titulek()

    def _po_zmene(self, pridano=(), odebrano=()):
        """Překreslí jen změněné prvky a obnoví úchyty a index výběru."""
        xref = {r.nazev for r in getattr(self, "reference", [])}
        zmenene = list(pridano) + list(odebrano)
        if any(e.dxftype() == "VIEWPORT" for e in zmenene) or (
                xref and any(e.dxftype() == "INSERT" and e.dxf.name in xref for e in zmenene)):
            self._vykresli()  # připojení / odpojení reference (i přes Zpět) → překreslit podklad
            self._titulek()
            self._aktualizuj_tlacitka()
            return
        sc = self.view.scene()
        for e in odebrano:
            for it in self._polozky.pop(id(e), []):
                if it.scene() is sc:
                    sc.removeItem(it)
        if pridano:
            self._kresli_entity(list(pridano))
        self._obnov_indexy()
        self.vyber = [e for e in self.vyber if e.dxf.owner is not None]
        self._zvyrazni()
        self._titulek()
        self._aktualizuj_tlacitka()
        if self.dok is not None:
            self.dok.zmeneno = self.neulozeno

    def _aktualizuj_tlacitka(self):
        h = self.historie_zmen
        self.b_undo.setEnabled(bool(h and h.zpet))
        self.b_redo.setEnabled(bool(h and h.vpred))
        for b in self.nastroje.values():
            b.setEnabled(self.dok is not None)
        for b in (self.b_save, self.b_saveas, self.b_check, self.b_all, self.b_vrstvy, self.b_na_vyber, self.b_ref,
                  self.modely, self.b_tisk, self.b_body):
            b.setEnabled(self.dok is not None)

    def _zahodit_zmeny(self) -> bool:
        if not self.neulozeno or not self.isVisible():
            return True
        r = QMessageBox.question(self, "CAD", "Výkres má neuložené změny. Uložit je?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.uloz() is not None
        return r == QMessageBox.Discard

    def otevri(self, path: str | None = None) -> bool:
        if not self._zahodit_zmeny():
            return False
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
        if not self._zahodit_zmeny():
            return
        self.nastav_dokument(CadDokument())
        self.sjtsk = False

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
        self._ulozena_zmena = self.historie_zmen.zmena if self.historie_zmen else 0
        self._titulek()
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

    # ------------------------------------------------------------ Zpět / Vpřed
    def undo(self):
        if self._gen is not None:
            self.zrus()
        if self.historie_zmen is None:
            return
        op = self.historie_zmen.krok_zpet()
        if op is None:
            self.vypis("Není co vrátit.")
            return
        self._po_zmene(op.odebrano, op.pridano)
        self.vypis(f"Zpět: {op.nazev}")

    def redo(self):
        if self.historie_zmen is None:
            return
        op = self.historie_zmen.krok_vpred()
        if op is None:
            self.vypis("Není co provést znovu.")
            return
        self._po_zmene(op.pridano, op.odebrano)
        self.vypis(f"Vpřed: {op.nazev}")

    # ------------------------------------------------------------ výběr
    def _zvyrazni(self):
        if self.index is None:
            self.view.zvyraznene = []
        else:
            self.view.zvyraznene = [g for g in (self.index.geometrie(e) for e in self.vyber) if g is not None]
        self.view.viewport().update()

    def _tol(self) -> float:
        return 8.0 / max(1e-12, abs(self.view.transform().m11()))

    def vyber_v_bode(self, x, y, pridat: bool = True):
        if self.index is None:
            return None
        e = self.index.najdi(x, y, self._tol())
        if e is None:
            return None
        if e in self.vyber:
            self.vyber.remove(e)
        else:
            if not pridat:
                self.vyber = []
            self.vyber.append(e)
        self._zvyrazni()
        return e

    def _okno(self, x0, y0, x1, y1):
        if self.index is None:
            return
        if self._req is not None and self._req.typ not in ("vyber",):
            return
        nove = self.index.okno(x0, y0, x1, y1, protinajici=x1 < x0)
        for e in nove:
            if e not in self.vyber:
                self.vyber.append(e)
        self._zvyrazni()
        self.vypis(f"Vybráno {len(self.vyber)} prvků.")

    # ------------------------------------------------------------ kurzor a vstupy
    def _pohyb(self, x, y):
        u = self.view.uchyt
        su = f"   [{u.popis}]" if u is not None else ""
        if self.sjtsk:
            self.coords.setText(f"Y {-x:,.3f}   X {-y:,.3f}{su}".replace(",", " "))
        else:
            self.coords.setText(f"x {x:,.3f}   y {y:,.3f}{su}".replace(",", " "))

    def _klik(self, x, y):
        r = self._req
        if self._gen is not None and r is not None:
            if r.typ == "bod":
                self._posli((x, y))
            elif r.typ == "cislo" and r.ref is not None:
                self._posli(math.hypot(x - r.ref[0], y - r.ref[1]))
            elif r.typ == "uhel" and r.ref is not None:
                self._posli((math.atan2(y - r.ref[1], x - r.ref[0]) / GON) % 400)
            elif r.typ == "vyber":
                mx, my = self.view.mys or (x, y)
                if self.vyber_v_bode(mx, my) is None:
                    self.vypis("Tady žádný prvek není.")
            elif r.typ == "prvek":
                mx, my = self.view.mys or (x, y)
                e = self.index.najdi(mx, my, self._tol()) if self.index else None
                if e is None:
                    self.vypis("Tady žádný prvek není – klikněte přímo na čáru.")
                else:
                    self._posli((e, (mx, my)))
            return
        if self._prikaz == "vzdálenost":
            self._bod_mereni(x, y)
            return
        mx, my = self.view.mys or (x, y)
        self.vyber_v_bode(mx, my)

    def _bod(self, x, y):
        """Bod zadaný z příkazového řádku."""
        if self._gen is not None and self._req is not None and self._req.typ == "bod":
            self._posli((x, y))
        elif self._prikaz == "vzdálenost":
            self._bod_mereni(x, y)
        else:
            self.view.posledni = (x, y)

    def _bod_mereni(self, x, y):
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

    def zrus(self, tise: bool = False):
        bezi = self._prikaz or self._gen is not None
        if bezi and not tise:
            self.vypis("*zrušeno*")
        if self._gen is not None:
            try:
                self._gen.close()
            except Exception:  # noqa: BLE001
                pass
        elif not bezi and self.vyber:
            self.vyber = []
        self._zvyrazni()
        self._gen = None
        self._req = None
        self._prikaz = None
        self._body = []
        self.view.gumicka = False
        self.view.vyber_oknem = True
        self.vyzva.setText("Příkaz:")
        self.view.viewport().update()

    def _enter(self):
        t = self.prikaz.text().strip()
        self.prikaz.clear()
        self.zadej(t)

    def zadej(self, t: str):
        """Vstup z příkazového řádku: odpověď běžícímu nástroji, nebo nový příkaz."""
        if self._gen is not None and self._req is not None:
            self._odpoved(t)
            return
        if not t:
            if self._posledni_prikaz:
                self.proved(self._posledni_prikaz)
            return
        self.proved(t)

    def _odpoved(self, t: str):
        r = self._req
        if t.lower() in r.slova:
            self._posli(t.lower())
            return
        if not t:
            if r.typ == "vyber":
                if self.vyber:
                    self._posli(list(self.vyber))
                else:
                    self.vypis("Nic není vybráno – klikněte na prvky nebo táhněte okno, pak Enter.")
                return
            if r.vychozi is not None:
                self._posli(r.vychozi)
            elif r.volitelne:
                self._posli(None)
            else:
                self.vypis(r.vyzva)
            return
        if r.typ == "text":
            self._posli(t)
        elif r.typ in ("cislo", "uhel"):
            try:
                v = float(t.replace(",", "."))
                if not math.isfinite(v):
                    raise ValueError
            except ValueError:
                if self._je_prikaz(t):
                    self.proved(t)
                    return
                self.vypis(f"„{t}“ není číslo. {r.vyzva}")
                return
            self._posli(v)
        elif r.typ == "bod":
            try:
                x, y = zadani_bodu(t, self.view.posledni, self.sjtsk)
            except ValueError as e:
                if self._je_prikaz(t):
                    self.proved(t)
                    return
                self.vypis(f"Neznámé souřadnice: {e}")
                return
            self.vypis(f"> bod {(-x if self.sjtsk else x):.3f} {(-y if self.sjtsk else y):.3f}")
            self._posli((x, y))
        elif self._je_prikaz(t):
            self.proved(t)
        else:
            self.vypis(r.vyzva)

    def _je_prikaz(self, t: str) -> bool:
        slovo = (t.strip().split() or [""])[0].lower()
        return t.lower() in self.ALIASY or slovo in self.ALIASY or slovo in self.PRIKAZY

    # ------------------------------------------------------------ běh nástroje
    def _spust(self, gen):
        self._gen = gen
        self._posli(None, prvni=True)

    def _posli(self, hodnota, prvni: bool = False):
        h = self.historie_zmen
        pred = len(h.zpet) if h else 0
        pred_op = h.zpet[-1] if h and h.zpet else None
        try:
            r = next(self._gen) if prvni else self._gen.send(hodnota)
        except StopIteration:
            self._konec_nastroje()
            r = None
        except ValueError as e:
            self.vypis(f"⚠ {e}")
            self._konec_nastroje()
            r = None
        except Exception as e:  # noqa: BLE001 – nástroj nesmí shodit aplikaci
            self.vypis(f"⚠ Úprava se nepovedla: {type(e).__name__}: {e}")
            self._konec_nastroje()
            r = None
        # nové operace v historii → překreslit
        if h is not None and (len(h.zpet) != pred or (h.zpet and h.zpet[-1] is not pred_op)):
            nove = h.zpet[pred:] if len(h.zpet) >= pred else []
            for op in nove:
                self._po_zmene(op.pridano, op.odebrano)
        if r is not None:
            self._req = r
            self.vyzva.setText(r.vyzva)
            self.vypis(r.vyzva)
            self.view.vyber_oknem = r.typ == "vyber"
            if r.ref is not None:
                self.view.posledni = r.ref
                self.view.gumicka = True
            else:
                self.view.gumicka = False
            self.view.viewport().update()

    def _konec_nastroje(self):
        self._gen = None
        self._req = None
        self.view.gumicka = False
        self.view.vyber_oknem = True
        self.vyzva.setText("Příkaz:")

    # ------------------------------------------------------------ příkazy
    _KEYIN = re.compile(r"^\s*(lv|co|lc|wt|th|tw|ac)\s*=\s*([^;]*)$", re.I)

    def _keyiny(self, t: str) -> bool:
        """Key-iny MicroStationu „lv=5;co=94;lc=0;wt=0“ (i z taháku atributů), „th=0.75“, „ac=3.13“."""
        casti = [c for c in t.split(";") if c.strip()]
        if not casti or not all(self._KEYIN.match(c) for c in casti):
            return False
        if self.dok is None:
            self.vypis("Nejdřív otevřete výkres nebo začněte nový.")
            return True
        vyber, self.vyber = self.vyber, []  # key-in nastavuje aktivní atributy (jako MicroStation), ne výběr
        try:
            for c in casti:
                k, v = (x.strip() for x in self._KEYIN.match(c).groups())
                k = k.lower()
                if k == "lv":
                    self._vrstva(v)
                elif k == "co":
                    self._barva(v)
                elif k == "lc":
                    self._styl_tloustka("styl", v)
                elif k == "wt":
                    self._styl_tloustka("tloušťka", v)
                elif k in ("th", "tw"):
                    try:
                        h = float(v.replace(",", "."))
                        if h <= 0:
                            raise ValueError
                    except ValueError:
                        self.vypis(f"{k}= musí být kladné číslo.")
                        continue
                    if k == "th":
                        self.vyska_textu = h
                        self.kresleni.vyska_textu = h
                    else:
                        self.kresleni.sirka_faktor = h / max(self.vyska_textu, 1e-9)
                elif k == "ac":
                    self._aktivni_bunka = v
                    self.vypis(f"Aktivní buňka {v} (vložení příkazem „vlož“).")
        finally:
            self.vyber = vyber
        self.aktivni_atributy()
        return True

    def proved(self, t: str):
        """Příkaz nebo souřadnice z příkazového řádku."""
        if self._keyiny(t):
            self.vypis(f"> {t}")
            return
        parts = t.strip().split(maxsplit=1)
        slovo = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        cmd = self.ALIASY.get(t.lower(), self.ALIASY.get(slovo, slovo if slovo in self.PRIKAZY else t.lower()))
        if cmd not in self.PRIKAZY:
            try:
                x, y = zadani_bodu(t, self.view.posledni, self.sjtsk)
            except ValueError as e:
                self.vypis(f"Neznámý příkaz nebo souřadnice: {e}")
                return
            self.vypis(f"> bod {(-x if self.sjtsk else x):.3f} {(-y if self.sjtsk else y):.3f}")
            self._bod(x, y)
            return
        if self._gen is not None or self._prikaz:
            self.zrus(tise=True)
        self.vypis(f"> {t}")
        if cmd == "celý":
            self.view.zoom_all()
        elif cmd == "nápověda":
            self.vypis("Příkazy: " + "; ".join(f"{k} – {v}" for k, v in self.PRIKAZY.items()))
            self.vypis("Zkratky: u úsečka, pl polylinie, kr kružnice, ob oblouk, t text, m posun, cp kopie, "
                       "ro otoč, sc měřítko, mi zrcadli, of rovnoběžka, tr ořež, ex prodluž, f zaobli, "
                       "x rozpoj, j spoj, Delete smaž. Enter na prázdném řádku zopakuje poslední příkaz.")
            self.vypis("Souřadnice: „Y X“ (S-JTSK), „x=… y=…“, „@dx,dy“, „@délka<směrník[g]“. "
                       "Úchyty F3, Ortho F8, Polární F10, Esc zruší příkaz / výběr. Kolečko = zoom, "
                       "prostřední/pravé tlačítko = posun. Výběr: klik, okno zleva doprava (celé prvky), "
                       "zprava doleva (i protnuté).")
        elif cmd == "vzdálenost":
            self._prikaz = "vzdálenost"
            self._body = []
            self.vypis("První bod:")
        elif cmd == "otevři":
            self.otevri()
        elif cmd == "ulož":
            self.uloz()
        elif cmd == "zpět":
            self.undo()
        elif cmd == "vpřed":
            self.redo()
        elif self.dok is None:
            self.vypis("Nejdřív otevřete výkres nebo začněte nový (tlačítko Nový).")
        elif cmd == "vše":
            self.vyber = list(self.prostor)
            self._zvyrazni()
            self.vypis(f"Vybráno {len(self.vyber)} prvků.")
        elif cmd == "vrstvy":
            self.spravce_vrstev()
        elif cmd == "tisk":
            self.tisk_pdf()
        elif cmd == "body":
            self.body_ze_seznamu()
        elif cmd == "vlastnosti":
            if len(self.vyber) != 1:
                self.vypis("Vyberte jeden prvek (nebo na něj dvakrát klikněte).")
            else:
                self.vlastnosti_prvku(self.vyber[0])
        elif cmd == "podobné":
            if not self.vyber:
                self.vypis("Vyberte vzorový prvek, pak „podobné“ vybere všechny stejného typu ve stejné vrstvě.")
            else:
                self.vyber = U.vyber_podobne(self.prostor, self.vyber)
                self._zvyrazni()
                self.vypis(f"Vybráno {len(self.vyber)} podobných prvků.")
        elif cmd == "najdi":
            nal = U.najdi_text(self.prostor, arg) if arg else []
            self.vyber = nal
            self._zvyrazni()
            if nal:
                from PySide6.QtCore import QRectF
                g = [self.index.geometrie(e) for e in nal if self.index]
                b = [x.bounds for x in g if x is not None]
                if b:
                    x0, y0 = min(q[0] for q in b), min(q[1] for q in b)
                    x1, y1 = max(q[2] for q in b), max(q[3] for q in b)
                    m = max(x1 - x0, y1 - y0, 5.0)
                    self.view.zoom_all(QRectF(x0 - m, y0 - m, x1 - x0 + 2 * m, y1 - y0 + 2 * m))
            self.vypis(f"Nalezeno {len(nal)} textů s „{arg}“." if arg else "Zadejte „najdi hledaný text“.")
        elif cmd == "nahraď":
            if "/" not in arg:
                self.vypis("Zadejte „nahraď staré / nové“.")
            else:
                co, cim = (x.strip() for x in arg.split("/", 1))
                try:
                    n = U.nahrad_text(self.prostor, self.historie_zmen, co, cim)
                except ValueError as e:
                    self.vypis(f"⚠ {e}")
                else:
                    op = self.historie_zmen.zpet[-1] if n else None
                    if op is not None:
                        self._po_zmene(op.pridano, op.odebrano)
                    self.vypis(f"Nahrazeno v {n} textech.")
        elif cmd == "razítko":
            self.razitko()
        elif cmd == "reference":
            self.spravce_referenci()
        elif cmd == "model":
            if not arg:
                self.vypis("Modely: " + ", ".join(self.dok.doc.layout_names_in_taborder()))
            else:
                self.nastav_model(arg.strip())
        elif cmd == "list":
            self.novy_list(arg)
        elif cmd == "atributy":
            self.atributy_zadani()
        elif cmd == "prvek":
            if not arg:
                self.vypis("Druhy prvků: " + "; ".join(p.nazev for p in self._predvolby[:40]))
            elif not self.vyber_predvolbu(arg):
                self.vypis(f"Druh prvku „{arg}“ v pravidlech zadání není.")
        elif cmd == "vrstva":
            self._vrstva(arg)
        elif cmd == "barva":
            self._barva(arg)
        elif cmd in ("styl", "tloušťka"):
            self._styl_tloustka(cmd, arg)
        elif cmd == "info":
            self._info()
        elif cmd == "výměra":
            self._vymera()
        else:
            self._posledni_prikaz = cmd
            fn = getattr(self, "n_" + _ascii(cmd).replace(" ", "_"))
            self._spust(fn())

    def _vrstva(self, arg: str):
        name = arg.strip()
        if not name:
            self.vypis(f"Aktuální vrstva: {self.kresleni.vrstva}. Zadejte „vrstva NÁZEV“.")
            return
        if name not in self.dok.doc.layers:
            self.dok.doc.layers.add(name)
            self.vypis(f"Nová vrstva {name}.")
        if self.vyber:
            ents = list(self.vyber)
            nove = U.zmen_vlastnosti(self.prostor, self.historie_zmen, ents, layer=name)
            self._po_zmene(nove, ents)
            self.vyber = nove
            self._zvyrazni()
            self.vypis(f"{len(nove)} prvků přesunuto do vrstvy {name}.")
        else:
            self.kresleni.vrstva = name
            self.vypis(f"Aktivní hladina: {name}")
            self.aktivni_atributy()
        self._napln_vrstvy()

    def aktivni_atributy(self) -> str:
        from ..cad import symbologie as S
        k = self.kresleni
        if k is None:
            return ""
        rs = self._pravidla()
        b = k.ms_barva if k.ms_barva is not None and k.barva != 256 else S.aci_na_ms(k.barva, rs)
        w = S.lw_na_wt(k.tloustka, rs)
        t = (f"Hladina {k.vrstva} · Barva {b if b is not None else 'dle hl.'} · Styl {S.typ_na_styl(k.typ_cary)}"
             f" · Tloušťka {w if w is not None else 'dle hl.'}")
        self.aktivni.setText(t)
        return t

    def _barva(self, arg: str):
        """Barva jako v MicroStationu (0–255, prázdné/„dle“ = dle hladiny) – pro nové prvky i výběr."""
        from ..cad import symbologie as S
        try:
            if arg.strip().lower() in ("dle", "dle hladiny", "bylevel"):
                c = 256
            else:
                c = S.ms_na_aci(int(arg), self._pravidla())
        except ValueError:
            self.vypis("Barva je číslo MicroStationu 0–255 (nebo „barva dle“ = dle hladiny).")
            return
        if self.vyber:
            ents = list(self.vyber)
            nove = U.zmen_vlastnosti(self.prostor, self.historie_zmen, ents, color=c)
            self._po_zmene(nove, ents)
            self.vyber = nove
            self._zvyrazni()
        else:
            self.kresleni.barva = c
            self.kresleni.ms_barva = None if c == 256 else int(arg)
        self.vypis(f"Barva {arg.strip()}." + ("" if c == 256 else f" (v DXF ACI {c})"))
        self.aktivni_atributy()

    def _styl_tloustka(self, cmd: str, arg: str):
        """Styl čáry (0–7, kód vlastního stylu) a tloušťka (wt 0–31) jako v MicroStationu."""
        from ..cad import symbologie as S
        rs = self._pravidla()
        a = arg.strip()
        try:
            if cmd == "styl":
                if not a:
                    raise ValueError
                hodnota = "BYLAYER" if a.lower().startswith("dle") else S.styl_na_typ(a)
                if hodnota.startswith("DGN Style"):
                    S.zajisti_styly(self.dok.doc)
                if hodnota not in ("BYLAYER", "CONTINUOUS") and hodnota not in self.dok.doc.linetypes:
                    raise KeyError(hodnota)
                attr = {"linetype": hodnota}
            else:
                if not a:
                    raise ValueError
                lw, odhad = (-1, False) if a.lower().startswith("dle") else S.wt_na_lw(int(a), rs)
                attr = {"lineweight": lw}
                if odhad:
                    self.vypis(f"⚠ Tloušťka {a} není v převodní tabulce zadání – použit odhad {lw / 100:.2f} mm "
                               "(upravte v Atributy ze zadání).")
        except KeyError as e:
            self.vypis(f"Styl {e.args[0]} ve výkresu není – nahrajte vzorový výkres nebo soubor .lin od učitele.")
            return
        except ValueError:
            self.vypis("Styl čáry 0–7 nebo kód (např. 2.103), tloušťka 0–31; „dle“ = dle hladiny.")
            return
        if self.vyber:
            ents = [e for e in self.vyber if e.dxftype() not in ("TEXT", "MTEXT", "INSERT", "POINT")]
            nove = U.zmen_vlastnosti(self.prostor, self.historie_zmen, ents, **attr)
            self._po_zmene(nove, ents)
            self.vyber = nove
            self._zvyrazni()
        elif "linetype" in attr:
            self.kresleni.typ_cary = attr["linetype"]
        else:
            self.kresleni.tloustka = attr["lineweight"]
        self.vypis(f"{'Styl' if cmd == 'styl' else 'Tloušťka'} {a}.")
        self.aktivni_atributy()

    def _info(self):
        if not self.vyber:
            self.vypis("Vyberte prvek a zadejte „info“.")
            return
        for e in self.vyber[:20]:
            d = e.dxf
            r = [f"{e.dxftype()} vrstva {d.get('layer', '0')}, barva {d.get('color', 256)}"]
            g = self.index.geometrie(e) if self.index else None
            if g is not None and g.geom_type in ("LineString", "MultiLineString"):
                r.append(f"délka {g.length:.3f}")
            if e.dxftype() in ("CIRCLE", "ARC"):
                r.append(f"poloměr {d.radius:.3f}")
            if e.dxftype() in ("TEXT", "MTEXT"):
                r.append(f"text „{e.plain_text() if e.dxftype() == 'MTEXT' else d.text}“")
            self.vypis(", ".join(r))

    def _vymera(self):
        from shapely.geometry import Polygon
        if len(self.vyber) != 1:
            self.vypis("Vyberte jeden uzavřený prvek (polylinie, kružnice) a zadejte „výměra“.")
            return
        g = self.index.geometrie(self.vyber[0])
        if g is None or g.geom_type != "LineString" or len(g.coords) < 3:
            self.vypis("Prvek není uzavřený obrazec.")
            return
        e = self.vyber[0]
        if e.dxftype() == "LWPOLYLINE" and not any(abs(b) > 1e-12 for *_x, b in e.get_points("xyb")):
            body = [(x, y) for x, y in e.get_points("xy")]
            from ..geodezie.vypocty import vymera
            p = vymera(body)
        elif e.dxftype() == "CIRCLE":
            p = math.pi * e.dxf.radius ** 2
        else:
            p = Polygon(g.coords).area
        self.vypis(f"Výměra {p:.2f} m², obvod {g.length + (0 if g.is_closed else math.dist(g.coords[0], g.coords[-1])):.3f} m")

    # ------------------------------------------------------------ nástroje kreslení
    def _bod_req(self, vyzva, ref=None, volitelne=False, slova=()):
        return Pozadavek("bod", vyzva, volitelne, slova, ref)

    def n_bod(self):
        while True:
            p = yield self._bod_req("Bod (Enter = konec):", volitelne=True)
            if p is None:
                return
            self.kresleni.bod(p)

    def n_usecka(self):
        body = []
        p = yield self._bod_req("Úsečka – první bod:")
        body.append(p)
        while True:
            q = yield self._bod_req("Další bod (Enter = konec, z = zpět o bod, k = uzavřít):", body[-1], True,
                                    ("z", "k"))
            if q is None:
                return
            if q == "z":
                if len(body) > 1:
                    self.undo_posledni("Úsečka")
                    body.pop()
                continue
            if q == "k":
                if len(body) > 2:
                    self.kresleni.usecka(body[-1], body[0])
                return
            self.kresleni.usecka(body[-1], q)
            body.append(q)

    def undo_posledni(self, nazev: str):
        h = self.historie_zmen
        if h.zpet and h.zpet[-1].nazev == nazev:
            op = h.krok_zpet()
            h.vpred.clear()
            self._po_zmene(op.odebrano, op.pridano)

    def n_polylinie(self):
        body = [(yield self._bod_req("Polylinie – první bod:"))]
        while True:
            q = yield self._bod_req("Další bod (Enter = konec, k = uzavřít, z = zpět o bod):", body[-1], True,
                                    ("k", "z"))
            if q == "z":
                if len(body) > 1:
                    body.pop()
                continue
            if q is None or q == "k":
                if len(body) >= 2:
                    self.kresleni.polylinie(body, uzavrena=(q == "k" and len(body) > 2))
                return
            body.append(q)
            self.view.zvyraznene = self.view.zvyraznene[:0] + [_linie(body)]

    def n_obdelnik(self):
        a = yield self._bod_req("Obdélník – první roh:")
        b = yield self._bod_req("Protější roh:", a)
        self.kresleni.obdelnik(a, b)

    def n_kruznice(self):
        s = yield self._bod_req("Kružnice – střed:")
        r = yield Pozadavek("cislo", "Poloměr (číslo nebo klikněte bod na kružnici):", ref=s)
        self.kresleni.kruznice(s, r)

    def n_oblouk(self):
        a = yield self._bod_req("Oblouk – počáteční bod:")
        b = yield self._bod_req("Bod na oblouku:", a)
        c = yield self._bod_req("Koncový bod:", b)
        self.kresleni.oblouk_3body(a, b, c)

    def n_elipsa(self):
        s = yield self._bod_req("Elipsa – střed:")
        a = yield self._bod_req("Konec první poloosy:", s)
        b = yield Pozadavek("cislo", "Délka druhé poloosy (číslo nebo bod):", ref=s)
        self.kresleni.elipsa(s, a, b)

    def n_krivka(self):
        body = [(yield self._bod_req("Křivka – první bod:"))]
        while True:
            q = yield self._bod_req("Další bod (Enter = konec):", body[-1], True)
            if q is None:
                if len(body) >= 2:
                    self.kresleni.krivka(body)
                return
            body.append(q)

    def n_text(self):
        p = yield self._bod_req("Text – vložit do bodu:")
        v = yield Pozadavek("cislo", f"Výška textu [{self.vyska_textu}]:", vychozi=self.vyska_textu, ref=p)
        self.vyska_textu = v
        a = yield Pozadavek("cislo", "Natočení ve stupních [0]:", vychozi=0.0)
        while True:
            t = yield Pozadavek("text", "Text (Enter = konec):", volitelne=True)
            if not t:
                return
            self.kresleni.text(p, t, v, a)
            r = math.radians(a)
            p = (p[0] + math.sin(r) * v * 1.6, p[1] - math.cos(r) * v * 1.6)  # další řádek pod

    def n_srafa(self):
        e, _k = yield Pozadavek("prvek", "Šrafa – klikněte na uzavřenou polylinii nebo kružnici:")
        vz = yield Pozadavek("text", "Vzor šrafy [SOLID] (např. ANSI31, NET):", vychozi="SOLID")
        m = 1.0
        if vz.upper() != "SOLID":
            m = yield Pozadavek("cislo", "Měřítko vzoru [1]:", vychozi=1.0)
        self.kresleni.sraf(e, vz, m)

    def n_kota(self):
        a = yield self._bod_req("Kóta – první bod:")
        b = yield self._bod_req("Druhý bod:", a)
        c = yield self._bod_req("Poloha kótovací čáry:", b)
        self.kresleni.kota(a, b, c, self.vyska_textu)

    # ------------------------------------------------------------ nástroje úprav
    def _vyber_req(self, nazev):
        if self.vyber:
            return list(self.vyber)
        ents = yield Pozadavek("vyber", f"{nazev} – vyberte prvky (klik / okno), pak Enter:")
        return ents

    def _hotovo_vyber(self, nove):
        self.vyber = list(nove)
        self._zvyrazni()

    def n_smaz(self):
        ents = yield from self._vyber_req("Smazat")
        n = U.smaz(self.historie_zmen, ents)
        self.vyber = []
        self.vypis(f"Smazáno {n} prvků.")

    def n_posun(self):
        ents = yield from self._vyber_req("Posun")
        a = yield self._bod_req("Bod odkud:")
        b = yield self._bod_req("Bod kam:", a)
        self._hotovo_vyber(U.posun(self.prostor, self.historie_zmen, ents, b[0] - a[0], b[1] - a[1]))

    def n_kopie(self):
        ents = yield from self._vyber_req("Kopie")
        a = yield self._bod_req("Bod odkud:")
        while True:
            b = yield self._bod_req("Bod kam (Enter = konec, p = počet kopií v řadě):", a, True, ("p",))
            if b is None:
                return
            if b == "p":
                n = yield Pozadavek("cislo", "Počet kopií:")
                c = yield self._bod_req("Vzdálenost mezi kopiemi – bod první kopie:", a)
                if int(n) < 1:
                    raise ValueError("Počet kopií musí být aspoň 1.")
                U.kopie_vicenasobna(self.prostor, self.historie_zmen, ents, c[0] - a[0], c[1] - a[1], int(n))
                return
            U.posun(self.prostor, self.historie_zmen, ents, b[0] - a[0], b[1] - a[1], kopie=True)

    def n_otoc(self):
        ents = yield from self._vyber_req("Otočení")
        s = yield self._bod_req("Střed otočení:")
        u = yield Pozadavek("uhel", "Úhel otočení v gonech (+ proti směru hodin) nebo klikněte směr:", ref=s)
        self._hotovo_vyber(U.otoc(self.prostor, self.historie_zmen, ents, s, u * GON))

    def n_meritko(self):
        ents = yield from self._vyber_req("Měřítko")
        s = yield self._bod_req("Základní bod:")
        k = yield Pozadavek("cislo", "Měřítko (např. 2 = dvojnásobek, 0.5 = polovina):")
        self._hotovo_vyber(U.meritko(self.prostor, self.historie_zmen, ents, s, k))

    def n_zrcadli(self):
        ents = yield from self._vyber_req("Zrcadlení")
        a = yield self._bod_req("První bod osy:")
        b = yield self._bod_req("Druhý bod osy:", a)
        z = yield Pozadavek("text", "Ponechat původní prvky? [n] (a/n):", vychozi="n")
        self._hotovo_vyber(U.zrcadli(self.prostor, self.historie_zmen, ents, a, b,
                                     kopie=z.strip().lower() in ("a", "ano", "y")))

    def n_rovnobezka(self):
        d = yield Pozadavek("cislo", "Rovnoběžka – vzdálenost:")
        while True:
            r = yield Pozadavek("prvek", "Klikněte na prvek (Esc = konec):")
            e = r[0]
            s = yield self._bod_req("Na kterou stranu (klikněte):")
            U.rovnobezka(self.prostor, self.historie_zmen, e, d, s)

    def n_orez(self):
        while True:
            e, k = yield Pozadavek("prvek", "Ořez – klikněte na část, která se má odstranit (Esc = konec):")
            try:
                U.orez(self.prostor, self.historie_zmen, e, k, list(self.prostor))
            except ValueError as ex:
                self.vypis(f"⚠ {ex}")

    def n_prodluz(self):
        while True:
            e, k = yield Pozadavek("prvek", "Prodloužení – klikněte na úsečku u konce, který prodloužit (Esc = konec):")
            try:
                U.prodluz(self.prostor, self.historie_zmen, e, k, list(self.prostor))
            except ValueError as ex:
                self.vypis(f"⚠ {ex}")

    def n_zaobli(self):
        r = yield Pozadavek("cislo", "Poloměr zaoblení [0 = ostrý roh]:", vychozi=0.0)
        e1, k1 = yield Pozadavek("prvek", "První úsečka (klikněte na část, která zůstane):")
        e2, k2 = yield Pozadavek("prvek", "Druhá úsečka:")
        U.zaobli(self.prostor, self.historie_zmen, e1, k1, e2, k2, r)

    def n_rozpoj(self):
        ents = yield from self._vyber_req("Rozpojit")
        nove = U.rozpoj(self.prostor, self.historie_zmen, ents)
        self.vypis(f"Rozpojeno na {len(nove)} prvků.")
        self.vyber = []

    def n_spoj(self):
        ents = yield from self._vyber_req("Spojit")
        p = U.spoj(self.prostor, self.historie_zmen, ents, tol=max(1e-6, self._tol() / 100))
        self._hotovo_vyber([p])
        self.vypis("Spojeno do " + ("uzavřené " if p.closed else "") + "polylinie.")

    # ------------------------------------------------------------ bloky
    def n_blok(self):
        ents = yield from self._vyber_req("Blok")
        nazev = yield Pozadavek("text", "Název bloku:")
        if nazev in self.dok.doc.blocks:
            raise ValueError(f"Blok {nazev} už existuje.")
        b = yield self._bod_req("Základní (vkládací) bod bloku:")
        ins = U.vytvor_blok(self.dok.doc, self.prostor, self.historie_zmen, ents, nazev, b)
        self._hotovo_vyber([ins])
        self.vypis(f"Blok {nazev} vytvořen z {len(ents)} prvků.")

    def n_vloz(self):
        jmena = U.bloky(self.dok.doc)
        p = self.predvolba
        if p is not None and p.blok:
            from ..rules import block_matches, split_alternatives
            vhodne = [j for j in jmena if any(block_matches(v, j) for v in split_alternatives(p.blok))]
            if not vhodne:
                raise ValueError(f"Buňka {p.blok} pro „{p.nazev}“ ve výkresu není – nahrajte vzorový výkres "
                                 "s buňkami do Zadání → Vzorový výkres a založte výkres tlačítkem Nový podle zadání.")
            jmena = vhodne + [j for j in jmena if j not in vhodne]
        if not jmena:
            raise ValueError("Ve výkresu nejsou žádné bloky (vytvořte příkazem „blok“).")
        self.vypis("Bloky: " + ", ".join(jmena[:40]) + ("…" if len(jmena) > 40 else ""))
        ac = getattr(self, "_aktivni_bunka", None)
        if ac and ac in jmena:
            jmena = [ac] + [j for j in jmena if j != ac]
        nazev = yield Pozadavek("text", f"Název bloku [{jmena[0]}]:", vychozi=jmena[0])
        if nazev not in jmena:
            raise ValueError(f"Blok {nazev} ve výkresu není.")
        m = yield Pozadavek("cislo", "Měřítko [1]:", vychozi=1.0)
        u = yield Pozadavek("cislo", "Natočení ve stupních [0]:", vychozi=0.0)
        while True:
            p = yield self._bod_req("Vkládací bod (Enter = konec):", volitelne=True)
            if p is None:
                return
            U.vloz_blok(self.dok.doc, self.prostor, self.historie_zmen, nazev, p, m, u, self.kresleni.vrstva)

    # ------------------------------------------------------------ výřez na listu
    def n_vyrez(self):
        if self._je_model():
            raise ValueError("Výřez se vkládá na list – přepněte model na list (nebo „list“ vytvoří nový).")
        a = yield self._bod_req("Výřez – první roh na listu [mm]:")
        b = yield self._bod_req("Protější roh:", a)
        rs = self._pravidla()
        vych = float(rs.meritko) if rs is not None and rs.meritko else 500.0
        m = yield Pozadavek("cislo", f"Měřítko 1: [{vych:g}]:", vychozi=vych)
        if m <= 0:
            raise ValueError("Měřítko musí být kladné.")
        ext = self.dok.rozsah()
        vych_s = ((ext[0] + ext[2]) / 2, (ext[1] + ext[3]) / 2) if ext else (0.0, 0.0)
        c = yield Pozadavek("text", "Střed výřezu v modelu (Y X nebo Enter = střed kresby):", vychozi="")
        if c.strip():
            stred = zadani_bodu(c, None, self.sjtsk)
        else:
            stred = vych_s
        w, hgt = abs(b[0] - a[0]), abs(b[1] - a[1])
        if w < 1 or hgt < 1:
            raise ValueError("Výřez je příliš malý.")
        vp = self.prostor.add_viewport(center=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), size=(w, hgt),
                                       view_center_point=stred, view_height=hgt * m / 1000.0,
                                       dxfattribs={"layer": self.kresleni.vrstva})
        self.historie_zmen.proved("Výřez", [vp])
        self.vypis(f"Výřez {w:.0f}×{hgt:.0f} mm v měřítku 1:{m:g}.")

    # ------------------------------------------------------------ vlastnosti prvku
    def _dvojklik(self, x, y):
        if self._gen is not None or self.index is None:
            return
        e = self.index.najdi(x, y, self._tol())
        if e is not None:
            self.vlastnosti_prvku(e)

    def vlastnosti_prvku(self, e, modal: bool = True):
        from .cad_vlastnosti import VlastnostiDialog
        d = VlastnostiDialog(self, e)
        if modal:
            d.exec()
        return d

    # ------------------------------------------------------------ tisk
    def tisk_pdf(self, modal: bool = True):
        if self.dok is None:
            return None
        from .cad_tisk import TiskDialog
        d = TiskDialog(self)
        if modal:
            d.exec()
        return d

    def razitko(self, udaje: dict | None = None):
        from ..cad import tisk as T
        if self._je_model():
            self.vypis("Razítko se dává na list – přepněte Model na list nebo vytvořte nový příkazem „list“.")
            return []
        rs = self._pravidla()
        u = {"Název": self.dok.path.stem if self.dok.path else "",
             "Měřítko": f"1:{rs.meritko}" if rs is not None and rs.meritko else ""}
        pr = getattr(self.win, "project", None) if self.win is not None else None
        if pr is not None:
            u["Zpracoval"] = (pr.meta.get("autor") or pr.meta.get("student") or "") if hasattr(pr, "meta") else ""
        u.update(udaje or {})
        try:
            nove = T.ramecek_a_razitko(self.prostor, self.historie_zmen, u)
        except ValueError as e:
            self.vypis(f"⚠ {e}")
            return []
        self._po_zmene(nove, [])
        self.vypis("Rámeček a razítko nakresleny (texty upravíte dvojklikem / příkazem text).")
        return nove

    # ------------------------------------------------------------ reference
    def spravce_referenci(self, modal: bool = True):
        if self.dok is None:
            return None
        from .cad_reference import ReferenceDialog
        d = ReferenceDialog(self)
        if modal:
            d.exec()
        return d

    def pripoj_referenci(self, cesta, vlozeni=(0.0, 0.0), meritko=1.0, natoceni=0.0):
        from ..cad import reference as R
        if not self._je_model():
            self.nastav_model("Model")
        zaklad = self.dok.path.parent if self.dok.path else None
        r = R.pripoj(self.dok.doc, self.historie_zmen, cesta, zaklad, vlozeni, meritko, natoceni)
        self.reference.append(r)
        self.reference_zmeneny()
        self.vypis(f"Reference {r.cesta.name} připojena ({len(r.doc.modelspace())} prvků).")
        return r

    def reference_zmeneny(self):
        """Poloha, viditelnost nebo seznam referencí se změnil → zapsat do vložení a překreslit."""
        for r in self.reference:
            for ins in r.inserty:
                if ins.dxf.owner is None:
                    continue
                ins.dxf.insert = (r.vlozeni[0], r.vlozeni[1], 0)
                for k in ("xscale", "yscale", "zscale"):
                    ins.dxf.set(k, r.meritko)
                ins.dxf.rotation = r.natoceni
        if self.historie_zmen is not None:
            self.historie_zmen.zmena += 1
        self._vykresli()
        self._titulek()

    # ------------------------------------------------------------ měření
    def n_mer_plochu(self):
        body = [(yield self._bod_req("Výměra – první bod obvodu:"))]
        while True:
            q = yield self._bod_req("Další bod (Enter = spočítat):", body[-1], True)
            if q is None:
                break
            body.append(q)
            self.view.zvyraznene = [_linie(body + [body[0]])] if len(body) > 2 else [_linie(body)]
        if len(body) < 3:
            raise ValueError("Výměra potřebuje aspoň tři body.")
        from ..geodezie.vypocty import obvod, vymera
        p = vymera(body)
        self.vypis(f"Výměra {p:.2f} m² ({round(p)} m²), obvod {obvod(body):.3f} m, bodů {len(body)}")
        self._zvyrazni()

    def n_mer_uhel(self):
        a = yield self._bod_req("Úhel – bod na prvním rameni:")
        v = yield self._bod_req("Vrchol:", a)
        b = yield self._bod_req("Bod na druhém rameni:", v)
        u1 = math.atan2(a[1] - v[1], a[0] - v[0])
        u2 = math.atan2(b[1] - v[1], b[0] - v[0])
        # úhel po směru hodin od prvního ramene (jako geodetický úhel) a vnitřní úhel
        po_smeru = ((u1 - u2) % math.tau) / GON
        vnitrni = min(po_smeru, 400 - po_smeru)
        self.vypis(f"Úhel {po_smeru:.4f} g po směru hodin ({po_smeru * 0.9:.4f}°), vnitřní {vnitrni:.4f} g")


def _linie(body):
    from shapely.geometry import LineString
    return LineString(body)


def _ascii(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


__all__ = ["CadPage", "CadView", "TYPY"]
