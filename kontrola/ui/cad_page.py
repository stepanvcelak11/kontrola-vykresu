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

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
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
    nahled: object = None  # funkce (x, y) → seznam geometrií Shapely: dynamický náhled za kurzorem


def _citelne_pero(it) -> None:
    """ezdxf kreslí tenké čáry kosmetickým perem širokým setiny pixelu – na tmavém pozadí skoro neviditelné.
    Tenké čáry dostanou 1 px, tlusté úměrně víc (jako zobrazení tlouštěk v MicroStationu)."""
    pen_fn = getattr(it, "pen", None)
    if pen_fn is None:
        return
    try:
        p = pen_fn()
    except TypeError:
        return
    if not p.isCosmetic():
        return
    w = p.widthF()
    nova = 1.0 if w < 0.45 else min(8.0, max(1.5, round(w * 2.35 * 2) / 2))
    if abs(nova - w) > 1e-6:
        p.setWidthF(nova)
        it.setPen(p)


class CadView(QGraphicsView):
    mouseMoved = Signal(float, float)  # souřadnice DXF (po úchytu / ortho)
    clicked = Signal(float, float)
    doubleClicked = Signal(float, float)
    windowSelected = Signal(float, float, float, float)  # x0, y0, x1, y1 (zprava doleva = protínající)
    reset = Signal()  # pravé tlačítko bez tažení = Reset (jako v MicroStationu)

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
        self.nahled = None  # funkce (x, y) → geometrie dynamického náhledu (kružnice, obdélník, posun…)
        self.vyber_oknem = True  # tažení levým tlačítkem = výběr oknem
        self.zvyraznene: list = []  # Shapely geometrie vybraných prvků
        self.pod_kurzorem = None  # geometrie prvku pod kurzorem (zvýraznění před klikem)
        self.uchopy: list = []  # body úchopů vybraných prvků (vrcholy) – čtverečky
        self._pan = None
        self._okno_start: tuple[float, float] | None = None
        self._okno_px = None
        self._pohledy: list = []  # předchozí pohledy (View Previous)
        self._posledni_ulozeni = 0.0

    # ------------------------------------------------------------ zoom a posun
    def zapamatuj_pohled(self, vynutit: bool = True):
        """Uloží aktuální pohled pro „předchozí pohled“ (kolečko jen jednou za chvíli)."""
        import time
        if not vynutit and time.monotonic() - self._posledni_ulozeni < 1.5:
            return
        self._posledni_ulozeni = time.monotonic()
        stav = (self.transform(), self.mapToScene(self.viewport().rect().center()))
        self._pohledy = (self._pohledy + [stav])[-30:]

    def predchozi_pohled(self) -> bool:
        if not self._pohledy:
            return False
        t, stred = self._pohledy.pop()
        self.setTransform(t)
        self.centerOn(stred)
        self._posledni_ulozeni = 0.0
        return True

    def wheelEvent(self, e):  # noqa: N802
        self.zapamatuj_pohled(vynutit=False)
        f = 1.0015 ** e.angleDelta().y()
        self.scale(f, f)

    def zoom_all(self, rect: QRectF | None = None):
        r = rect or self.scene().itemsBoundingRect()
        if r.isEmpty():
            return
        self.zapamatuj_pohled()
        self.fitInView(r.adjusted(-r.width() * 0.03, -r.height() * 0.03, r.width() * 0.03, r.height() * 0.03),
                       Qt.KeepAspectRatio)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan = e.position()
            self._pan_start = (e.position(), e.button())
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
            start = getattr(self, "_pan_start", None)
            self._pan_start = None
            if start is not None and start[1] == Qt.RightButton:
                d = e.position() - start[0]
                if abs(d.x()) + abs(d.y()) < 5:  # klik pravým bez posunu pohledu
                    self.reset.emit()
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
        if self.pod_kurzorem is not None:
            p.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(96, 165, 250, 200), 0)
            pen.setCosmetic(True)
            pen.setWidthF(3.0)
            p.setPen(pen)
            _kresli_geometrii(p, self.pod_kurzorem, s)
        if self.uchopy:
            p.setRenderHint(QPainter.Antialiasing, False)
            p.setPen(QPen(QColor("#F59E0B"), 0))
            p.setBrush(QColor("#1F2937"))
            r = 3.5 * s
            for ux, uy in self.uchopy[:4000]:
                p.drawRect(QRectF(ux - r, uy - r, 2 * r, 2 * r))
            p.setBrush(Qt.NoBrush)
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
        if self.nahled is not None:
            try:
                geoms = self.nahled(x, y) or []
            except Exception:  # noqa: BLE001 – náhled nesmí shodit kreslení (např. nulový poloměr)
                geoms = []
            if geoms:
                p.setRenderHint(QPainter.Antialiasing, True)
                pen = QPen(QColor("#FBBF24"), 0)
                pen.setCosmetic(True)
                pen.setWidthF(1.5)
                p.setPen(pen)
                for g in geoms:
                    _kresli_geometrii(p, g, s)
                p.setRenderHint(QPainter.Antialiasing, False)
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
        "kopíruj do schránky": "zkopírovat výběr do schránky (Ctrl+C) – i do jiného výkresu",
        "vlož ze schránky": "vložit prvky ze schránky na stejné souřadnice (Ctrl+V)",
        "uprav text": "upravit text kliknutím (Edit Text)",
        "délka": "celková délka vybraných čar (Measure Length)", "síť": "křížky souřadnicové sítě po intervalu (např. 100 m) s popisy",
        "mnohoúhelník": "pravidelný mnohoúhelník (střed, vrchol, počet stran)",
        "zhasni": "vypnout hladinu („zhasni 58“, „zhasni vše kromě 58“)", "rozsviť": "zapnout hladinu („rozsviť 58“, „rozsviť vše“)",
        "body po prvku": "body po prvku – na N dílů nebo po vzdálenosti (staničení)",
        "vyber": "výběr podle atributů („vyber 58“, „vyber barva 3“, „vyber typ text; hladina 59“)",
        "celý": "celý výkres (zoom)", "přiblížit": "přiblížit oknem (Window Area)",
        "předchozí pohled": "vrátit předchozí pohled (View Previous)", "vzdálenost": "změřit vzdálenost a směrník mezi dvěma body",
        "otevři": "otevřít DXF", "ulož": "uložit DXF", "nápověda": "seznam příkazů",
        "bod": "bod", "úsečka": "úsečky (řetězec, Enter = konec, z = zpět o bod)",
        "polylinie": "lomená čára (k = uzavřít, Enter = konec)", "obdélník": "obdélník ze dvou rohů",
        "kružnice": "kružnice (střed a poloměr)", "oblouk": "oblouk třemi body", "elipsa": "elipsa",
        "křivka": "křivka (spline) body", "text": "text", "šrafa": "šrafa uvnitř uzavřeného prvku",
        "kóta": "kóta délky", "smaž": "smazat výběr (Delete)", "posun": "posunout výběr",
        "kopie": "kopírovat výběr (i vícekrát)", "otoč": "otočit výběr", "měřítko": "změnit velikost výběru",
        "zrcadli": "zrcadlit výběr", "rovnoběžka": "rovnoběžka (offset)", "ořež": "oříznout k průsečíkům",
        "prodluž": "prodloužit úsečku k prvku", "zaobli": "zaoblit / spojit roh dvou úseček",
        "zkos": "zkosit roh dvou úseček (Chamfer)", "popisek": "popisek s odkazovou čárou a šipkou (Place Note)", "pole": "pole kopií výběru – obdélníkové nebo kruhové (Array)", "vlož vrchol": "vložit vrchol do strany polylinie",
        "smaž vrchol": "smazat vrchol polylinie", "posuň vrchol": "posunout vrchol (Modify Element)",
        "rozpoj": "rozpojit polylinie, bloky, kóty", "spoj": "spojit navazující prvky do polylinie",
        "vrstva": "aktuální vrstva / přesun výběru do vrstvy", "barva": "barva (0–256) nových prvků / výběru",
        "vše": "vybrat vše", "zpět": "vrátit poslední změnu (Ctrl+Z)", "vpřed": "znovu provést (Ctrl+Y)",
        "info": "vlastnosti vybraného prvku", "výměra": "výměra a obvod vybraného uzavřeného prvku",
        "model": "přepnout model / list („model List 1“)", "list": "nový výkresový list („list Výkres A3“)",
        "výřez": "výřez modelu na listu v měřítku", "reference": "správce referencí (připojit DXF podklad)",
        "vlastnosti": "vlastnosti vybraného prvku (i dvojklik)", "podobné": "vybrat podobné (stejný typ a vrstva)",
        "najdi": "najít text („najdi 12/1“)", "nahraď": "nahradit text („nahraď staré / nové“)",
        "měř plochu": "výměra a obvod klikáním na body (Enter = konec)", "měř úhel": "úhel mezi třemi body",
        "rozděl": "rozdělit prvek v bodě", "ohrada": "výběr ohradou (mnohoúhelník)",
        "oměrné míry": "popis délek stran vybraných čar (oměrné míry)", "kóta úhlu": "úhlová kóta",
        "kóta poloměru": "kóta poloměru kružnice / oblouku",
        "skupina": "vytvořit skupinu prvků z výběru (Graphic Group) – klik na prvek pak vybere celou skupinu",
        "zruš skupinu": "vyjmout vybrané prvky ze skupiny", "zámek skupin": "zapnout / vypnout výběr celých skupin",
        "smaž část": "smazat část prvku mezi dvěma body (Delete Part of Element)",
        "natáhni": "natažení: vrcholy v okně se posunou, zbytek prvků zůstane (Fence Stretch)",
        "transformace": "transformace výkresu (výběru) podle identických bodů – shodnostní, podobnostní, afinní",
        "převod atributů": "převod výkresu na pravidla ze zadání podle značek (buňky, styly čar) a vrstev",
        "převezmi atributy": "aktivní atributy podle prvku (Match)", "změň atributy": "aktivní atributy na prvky",
        "knihovna buněk": "načíst buňky z knihovny MicroStationu (.CEL) nebo bloky a styly z jiného DXF",
        "vrstevnice": "model terénu: TIN a vrstevnice z výškových bodů (výběr nebo seznam souřadnic)",
        "profil": "podélný profil terénu po trase (čára ve výkresu) z výškových bodů",
        "mračno": "mračno bodů (LAS, XYZ, PLY): prořídnutí, terén, body, vrstevnice nebo body do seznamu",
        "georeference": "transformace rastru podle identických bodů s opravami a m0, uložení world filu",
        "kódy": "kresba z kódů bodů seznamu souřadnic – linie, plochy a značky podle kódovníku a zadání",
        "kódovník": "kódovník: kód bodu → linie / plocha / značka, hladina a vzhled podle zadání",
        "body": "body ze seznamu souřadnic do výkresu", "rastr": "připojit rastr (ortofoto, sken) s georeferencí", "tisk": "tisk do PDF", "razítko": "rámeček a razítko na list", "vrstvy": "správce vrstev", "atributy": "atributy ze zadání – kontrola a úprava", "prvek": "druh prvku ze zadání (např. „prvek budovy“)", "blok": "vytvořit blok (buňku) z výběru", "vlož": "vložit blok",
    }
    ALIASY = {
        "copyclip": "kopíruj do schránky", "kopiruj do schranky": "kopíruj do schránky",
        "pasteclip": "vlož ze schránky", "vloz ze schranky": "vlož ze schránky", "paste": "vlož ze schránky",
        "divide": "body po prvku", "measure": "body po prvku", "bpp": "body po prvku",
        "polygon": "mnohoúhelník", "mnohouhelnik": "mnohoúhelník", "pol": "mnohoúhelník",
        "zhasni hladinu": "zhasni", "lv off": "zhasni", "lvoff": "zhasni", "rozsvit": "rozsviť", "lv on": "rozsviť",
        "lvon": "rozsviť",
        "delka": "délka", "len": "délka", "measure length": "délka", "mer delku": "délka",
        "sit": "síť", "grid": "síť", "krizky": "síť", "křížky": "síť",
        "et": "uprav text", "edit text": "uprav text", "edittext": "uprav text", "upravit text": "uprav text",
        "sel": "vyber", "select": "vyber", "výběr": "vyber", "vyber podle": "vyber", "sba": "vyber",
        "zw": "přiblížit", "okno pohledu": "přiblížit", "window area": "přiblížit", "priblizit": "přiblížit",
        "wa": "přiblížit", "vp": "předchozí pohled", "view previous": "předchozí pohled",
        "predchozi pohled": "předchozí pohled", "zpět pohled": "předchozí pohled",
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
        "prodluz": "prodluž", "f": "zaobli", "fillet": "zaobli", "cha": "zkos", "chamfer": "zkos", "note": "popisek", "le": "popisek", "leader": "popisek", "ar": "pole", "array": "pole",
        "zkoseni": "zkos", "zkosení": "zkos", "iv": "vlož vrchol", "insert vertex": "vlož vrchol",
        "vloz vrchol": "vlož vrchol", "dv": "smaž vrchol", "delete vertex": "smaž vrchol",
        "smaz vrchol": "smaž vrchol", "mo": "posuň vrchol", "modify": "posuň vrchol", "posun vrchol": "posuň vrchol", "x": "rozpoj", "explode": "rozpoj",
        "j": "spoj", "join": "spoj", "la": "vrstva", "layer": "vrstva", "col": "barva", "color": "barva", "co": "barva", "lc": "styl", "wt": "tloušťka",
        "tloustka": "tloušťka", "lv": "vrstva",
        "vse": "vše", "all": "vše", "undo": "zpět", "zpet": "zpět", "redo": "vpřed", "vpred": "vpřed",
        "li": "info", "list": "info", "lm": "vrstvy", "layers": "vrstvy", "knihovna": "knihovna buněk", "rc": "knihovna buněk",
        "knihovna bunek": "knihovna buněk", "cells": "knihovna buněk", "ma": "převezmi atributy", "match": "převezmi atributy",
        "prevezmi atributy": "převezmi atributy",
        "group": "skupina", "gg": "skupina", "add to graphic group": "skupina", "zrus skupinu": "zruš skupinu",
        "ungroup": "zruš skupinu", "drop from graphic group": "zruš skupinu", "zamek skupin": "zámek skupin",
        "graphic group lock": "zámek skupin", "natahni": "natáhni", "stretch": "natáhni", "fence stretch": "natáhni", "natažení": "natáhni",
        "převod": "převod atributů", "transformuj": "transformace",
        "transformace vykresu": "transformace", "helmert": "transformace", "prevod": "převod atributů", "prevod atributu": "převod atributů", "ca": "změň atributy", "change": "změň atributy",
        "zmen atributy": "změň atributy", "br": "rozděl", "break": "rozděl", "rozdel": "rozděl",
        "fence": "ohrada", "oh": "ohrada", "omerne miry": "oměrné míry", "om": "oměrné míry",
        "popis delek": "oměrné míry", "kota uhlu": "kóta úhlu", "dimang": "kóta úhlu", "ku": "kóta úhlu",
        "kota polomeru": "kóta poloměru", "dimrad": "kóta poloměru", "kp": "kóta poloměru", "mp": "měř plochu", "plocha bodů": "měř plochu",
        "mracno": "mračno", "las": "mračno", "point cloud": "mračno", "warp": "georeference", "georef": "georeference", "transformace rastru": "georeference",
        "kody": "kódy", "kresba z kodu": "kódy", "kresba z kódů": "kódy", "kodovnik": "kódovník",
        "tin": "vrstevnice", "profile": "profil", "podélný profil": "profil", "dtm": "vrstevnice", "contour": "vrstevnice", "contours": "vrstevnice",
        "mer plochu": "měř plochu", "measure area": "měř plochu", "mu": "měř úhel", "mer uhel": "měř úhel",
        "uhel": "měř úhel", "úhel": "měř úhel", "pr": "vlastnosti", "props": "vlastnosti",
        "podobne": "podobné", "similar": "podobné", "find": "najdi", "nahrad": "nahraď", "replace": "nahraď", "plot": "tisk", "print": "tisk",
        "pdf": "tisk", "razitko": "razítko", "mv": "výřez", "viewport": "výřez",
        "vyrez": "výřez", "xr": "reference", "xref": "reference", "ref": "reference", "layout": "list", "b": "blok", "block": "blok",
        "cell": "blok", "i": "vlož", "insert": "vlož", "vloz": "vlož", "bunka": "blok", "buňka": "blok", "plocha": "výměra", "area": "výměra", "vymera": "výměra",
    }
    VYBEROVE = {"kopíruj do schránky", "pole", "smaž", "posun", "kopie", "otoč", "měřítko", "zrcadli", "rozpoj", "spoj", "blok"}

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
        # ---- hlavní lišta: soubor, zpět/vpřed, tisk, kontrola, model, reference, zadání
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 5, 8, 3)
        bar.setSpacing(4)
        self.b_open = QPushButton("Otevřít…")
        self.b_open.setToolTip("Otevřít výkres DXF (Ctrl+O)")
        self.b_new = QPushButton("Nový")
        self.b_save = QPushButton("Uložit")
        self.b_save.setToolTip("Uložit DXF (Ctrl+S)")
        self.b_saveas = QPushButton("Uložit jako…")
        self.b_all = QPushButton("Celý výkres")
        self.b_undo = QPushButton("↶ Zpět")
        self.b_undo.setToolTip("Zpět (Ctrl+Z)")
        self.b_redo = QPushButton("↷ Vpřed")
        self.b_redo.setToolTip("Vpřed (Ctrl+Y)")
        self.b_tisk = QPushButton("Tisk do PDF…")
        self.b_tisk.setToolTip("Vytisknout model v měřítku nebo list do PDF (vektorově, na bílý papír)")
        self.b_check = QPushButton("Zkontrolovat")
        self.b_check.setObjectName("primary")
        self.b_check.setToolTip("Uloží výkres a zkontroluje ho v Kontrole výkresu (chyby se ukážou na stránce "
                                "Výkres)")
        for i, b in enumerate((self.b_open, self.b_new, self.b_save, self.b_saveas, None, self.b_undo, self.b_redo,
                               None, self.b_tisk, self.b_check)):
            if b is None:
                bar.addSpacing(10)
            else:
                bar.addWidget(b)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Model:"))
        self.modely = QComboBox()
        self.modely.setMinimumWidth(110)
        self.modely.setToolTip("Model výkresu nebo list (výkresový list s výřezy, rámečkem a razítkem)")
        bar.addWidget(self.modely)
        self.b_ref = QPushButton("Reference…")
        self.b_ref.setToolTip("Připojit jiný výkres DXF jako podklad (jen pro čtení, přichytávání, kopírování)")
        bar.addWidget(self.b_ref)
        self.b_vrstvy = QPushButton("Hladiny…")
        self.b_vrstvy.setToolTip("Správce hladin: zapnutí, zámek, barva, typ čáry, nová, přejmenovat, smazat")
        bar.addWidget(self.b_vrstvy)
        # zadání (méně časté akce v nabídce)
        self.b_novy_zadani = QPushButton("Nový podle zadání")
        self.b_novy_zadani.setToolTip("Založí výkres se všemi hladinami, styly čar, písmy a buňkami podle pravidel "
                                      "ze zadání (Zadání → Pravidla, Směrnice, vzorový výkres)")
        self.b_body = QPushButton("Body ze seznamu…")
        self.b_body.setToolTip("Vložit body ze seznamu souřadnic (Výpočty nebo soubor) na jejich souřadnice, "
                               "s čísly a výškami v hladinách podle zadání")
        self.b_atributy = QPushButton("Atributy ze zadání…")
        self.b_atributy.setToolTip("Zkontrolovat a upravit atributy, které aplikace načetla ze zadání (vrstva, "
                                   "barva, styl, tloušťka, písmo…) a ověřit, že nakreslené prvky projdou kontrolou")
        self.b_tahak = QPushButton("Tahák atributů…")
        self.b_tahak.setToolTip("Přehled atributů všech prvků ze zadání s řádky key-in pro MicroStation (HTML, "
                                "dá se vytisknout)")
        from PySide6.QtWidgets import QMenu
        self.b_zadani = QToolButton()
        self.b_zadani.setText("Zadání ▾")
        self.b_zadani.setToolTip("Výkres podle zadání, body ze seznamu, atributy a tahák")
        self.b_zadani.setPopupMode(QToolButton.InstantPopup)
        mz = QMenu(self.b_zadani)
        for btn in (self.b_novy_zadani, self.b_body, self.b_atributy, self.b_tahak):
            act = mz.addAction(btn.text())
            act.setToolTip(btn.toolTip())
            act.triggered.connect(btn.click)
            act.setData(btn)
        mz.aboutToShow.connect(lambda m=mz: [a.setEnabled(a.data().isEnabled()) for a in m.actions()])
        self.b_zadani.setMenu(mz)
        bar.addWidget(self.b_zadani)
        bar.addStretch(1)
        self.title = QLabel("Žádný výkres")
        self.title.setObjectName("cad_titulek")
        bar.addWidget(self.title)
        lay.addLayout(bar)
        # ---- lišta atributů (jako Attributes v MicroStationu): hladina, barva, styl, tloušťka, druh prvku
        arow = QHBoxLayout()
        arow.setContentsMargins(8, 2, 8, 5)
        arow.setSpacing(4)
        arow.addWidget(QLabel("Hladina:"))
        self.vrstvy = QComboBox()
        self.vrstvy.setMinimumWidth(130)
        self.vrstvy.setToolTip("Aktivní hladina pro nové prvky; s vybranými prvky je do ní přesune")
        arow.addWidget(self.vrstvy)
        arow.addWidget(QLabel("Barva:"))
        self.b_barva = QPushButton("dle hl.")
        self.b_barva.setToolTip("Aktivní barva 0–255 z tabulky barev MicroStationu (s výběrem změní vybrané prvky)")
        self.b_barva.setMinimumWidth(80)
        arow.addWidget(self.b_barva)
        arow.addWidget(QLabel("Styl:"))
        self.styl_cb = QComboBox()
        self.styl_cb.setMinimumWidth(130)
        self.styl_cb.setToolTip("Styl čáry 0–7 nebo vlastní styl (kód) – pro nové prvky, s výběrem změní vybrané")
        arow.addWidget(self.styl_cb)
        arow.addWidget(QLabel("Tloušťka:"))
        self.tl_cb = QComboBox()
        self.tl_cb.setMinimumWidth(110)
        self.tl_cb.setToolTip("Tloušťka čáry wt 0–31 (převod na mm podle zadání)")
        arow.addWidget(self.tl_cb)
        arow.addSpacing(10)
        arow.addWidget(QLabel("Kreslím:"))
        self.predvolby_cb = QComboBox()
        self.predvolby_cb.setMinimumWidth(260)
        self.predvolby_cb.setToolTip("Druh prvku ze zadání – hladina, barva, styl, tloušťka a písmo se nastaví samy")
        arow.addWidget(self.predvolby_cb, 1)
        self.b_na_vyber = QPushButton("Použít na výběr")
        self.b_na_vyber.setToolTip("Vybraným prvkům nastaví atributy zvoleného druhu prvku")
        arow.addWidget(self.b_na_vyber)
        self.predvolba_info = QLabel()
        self.predvolba_info.setObjectName("predvolba_info")
        self.predvolba_info.setMaximumWidth(420)
        arow.addWidget(self.predvolba_info)
        lay.addLayout(arow)
        self._predvolby: list = []
        # ---- střed: paleta nástrojů | výkres | hladiny a vlastnosti
        from PySide6.QtWidgets import QSplitter, QTabWidget

        from .cad_panely import PaletaNastroju, PanelHladin, PanelVlastnosti
        from .theme import accent, is_dark
        self.paleta = PaletaNastroju(self.PRIKAZY, "#D1D5DB" if is_dark() else "#374151", accent())
        self.paleta.nastroj.connect(self._z_palety)
        self.nastroje: dict[str, QToolButton] = dict(self.paleta.tlacitka)
        self.view = CadView()
        self.view.setCursor(Qt.CrossCursor)
        self.panel = QTabWidget()
        self.panel.setObjectName("cad_panel")
        self.panel_hladin = PanelHladin()
        self.panel_hladin.zobrazeni.connect(self._hladina_zobrazeni_panel)
        self.panel_hladin.aktivni.connect(self._hladina_aktivni_panel)
        self.panel_vlastnosti = PanelVlastnosti()
        self.panel.addTab(self.panel_vlastnosti, "Vlastnosti")
        self.panel.addTab(self.panel_hladin, "Hladiny")
        self.panel.setMinimumWidth(220)
        stred = QSplitter(Qt.Horizontal)
        stred.addWidget(self.paleta)
        stred.addWidget(self.view)
        stred.addWidget(self.panel)
        stred.setStretchFactor(1, 1)
        stred.setCollapsible(1, False)
        stred.setSizes([self.paleta.width(), 1000, 260])
        self.stred = stred
        lay.addWidget(stred, 1)
        self.historie = QPlainTextEdit()
        self.historie.setReadOnly(True)
        self.historie.setMaximumHeight(86)
        self.historie.setObjectName("cad_historie")
        lay.addWidget(self.historie)
        crow = QHBoxLayout()
        crow.setContentsMargins(8, 4, 8, 5)
        self.vyzva = QLabel("Příkaz:")
        self.vyzva.setObjectName("cad_vyzva")
        crow.addWidget(self.vyzva)
        self.prikaz = QLineEdit()
        self.prikaz.setObjectName("cad_prikaz")
        self.prikaz.setPlaceholderText("Příkaz (u, pl, kr, m, ?) nebo souřadnice „Y X“, „@dx,dy“, "
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
        # druhy úchytů (jako Snap Mode v MicroStationu) – zapamatují se
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QMenu
        ulozene = QSettings("KontrolaVykresu", "KontrolaVykresu").value("cad/uchyty", None)
        self.zapnute_uchyty = set(ulozene) & set(TYPY) if isinstance(ulozene, list) and ulozene else set(TYPY)
        self.b_druhy_uchytu = QToolButton()
        self.b_druhy_uchytu.setText("▾")
        self.b_druhy_uchytu.setToolTip("Které úchyty používat (koncový bod, střed, průsečík…)")
        self.b_druhy_uchytu.setPopupMode(QToolButton.InstantPopup)
        mu = QMenu(self.b_druhy_uchytu)
        self._akce_uchytu = {}
        for k, popis in TYPY.items():
            a = mu.addAction(popis)
            a.setCheckable(True)
            a.setChecked(k in self.zapnute_uchyty)
            a.toggled.connect(lambda on, k=k: self._druh_uchytu(k, on))
            self._akce_uchytu[k] = a
        self.b_druhy_uchytu.setMenu(mu)
        crow.insertWidget(crow.indexOf(self.b_uchyty) + 1, self.b_druhy_uchytu)
        self.krok = QSpinBox()
        self.krok.setRange(1, 200)
        self.krok.setValue(50)
        self.krok.setSuffix(" g")
        self.krok.setToolTip("Krok polárního režimu v gonech")
        crow.addWidget(self.krok)
        self.aktivni = QLabel("")
        self.aktivni.setObjectName("cad_aktivni")
        self.aktivni.setToolTip("Aktivní atributy pro nové prvky (jako v MicroStationu)")
        self.aktivni.hide()  # zobrazuje je lišta atributů nahoře
        crow.addWidget(self.aktivni)
        self.coords = QLabel("Y –  X –")
        self.coords.setObjectName("cad_souradnice")
        self.coords.setMinimumWidth(300)
        crow.addWidget(self.coords)
        lay.addLayout(crow)
        self.b_barva.clicked.connect(self._vyber_barvy)
        self.styl_cb.activated.connect(self._styl_z_listy)
        self.tl_cb.activated.connect(self._tloustka_z_listy)
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
        self.view.reset.connect(self._reset)
        self.b_uchyty.toggled.connect(lambda on: setattr(self.view, "uchyty_on", on))
        self.b_ortho.toggled.connect(self._ortho)
        self.b_polar.toggled.connect(self._polar)
        self.krok.valueChanged.connect(lambda v: setattr(self.view, "polar_krok", float(v)))
        from PySide6.QtGui import QKeySequence, QShortcut
        for key, fn in (("F3", self.b_uchyty.toggle), ("F8", self.b_ortho.toggle), ("F10", self.b_polar.toggle),
                        ("Escape", self.zrus), ("Delete", lambda: self.proved("smaž")),
                        ("Ctrl+A", lambda: self.proved("vše") if self.dok is not None else None),
                        ("Ctrl+C", lambda: self._schranka_klavesa("kopíruj do schránky")),
                        ("Ctrl+V", lambda: self._schranka_klavesa("vlož ze schránky"))):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self._aktualizuj_tlacitka()
        self.vypis("CAD – otevřete DXF nebo začněte nový výkres. Příkazy: „?“")

    def _schranka_klavesa(self, prikaz: str):
        """Ctrl+C / Ctrl+V: v textovém poli se kopíruje text, jinak prvky výkresu."""
        from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit
        f = QApplication.focusWidget()
        if isinstance(f, (QLineEdit, QPlainTextEdit)):
            if prikaz.startswith("kop"):
                f.copy()
            elif isinstance(f, QLineEdit) and not f.isReadOnly():
                f.paste()
            return
        self.proved(prikaz)

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

    def nacti_mracno(self, cesta: str | None = None):
        """Mračno bodů (XYZ, LAS, PLY) → prořídnutí / terén → body, vrstevnice nebo body do seznamu souřadnic."""
        if self.dok is None:
            return None
        if cesta is None:
            cesta, _ = QFileDialog.getOpenFileName(self, "Načíst mračno bodů", "",
                                                   "Mračna bodů (*.las *.xyz *.txt *.csv *.pts *.ply);;Všechny (*)")
            if not cesta:
                return None
        from ..geodezie import mracno as M
        try:
            m = M.nacti(cesta)
        except (OSError, ValueError) as e:
            self.vypis(f"⚠ {e}")
            return None
        self.vypis(f"Mračno {Path(cesta).name}: {M.souhrn(m)}.")
        self._spust(self._n_mracno(m))
        return m

    def _n_mracno(self, m):
        from ..cad import teren_cad as TC
        from ..geodezie import mracno as M
        from ..geodezie import teren as T
        bunka = yield Pozadavek("cislo", "Prořídnutí – velikost buňky [1 m]:", vychozi=1.0)
        r = yield Pozadavek("text", "Body: t = terén (bez vegetace a staveb), p = povrch (nejvyšší), s = střed "
                            "buňky [t]:", vychozi="t")
        r = (r or "t").strip().lower()[:1]
        vyber = M.teren(m, float(bunka or 1)) if r == "t" else M.prorid(m, float(bunka or 1),
                                                                         "povrch" if r == "p" else "stred")
        body = vyber.do_vykresu()
        self.vypis(f"Po prořídnutí: {M.souhrn(vyber)}.")
        a = yield Pozadavek("text", "Výstup: v = vrstevnice, b = body do výkresu, s = do seznamu souřadnic "
                            "(pro profil, kubaturu…), lze kombinovat [v]:", vychozi="v")
        a = (a or "v").strip().lower()
        if "b" in a:
            if "MRACNO" not in self.dok.doc.layers:
                self.dok.doc.layers.add("MRACNO", color=8)
            nove = [self.prostor.add_point((float(x), float(y), float(z)), dxfattribs={"layer": "MRACNO"})
                    for x, y, z in body[:100_000]]
            self.historie_zmen.proved("Mračno bodů", nove)
            self.vypis(f"Vloženo {len(nove)} bodů do hladiny MRACNO.")
        if "s" in a:
            from ..geodezie.body import Bod
            v = getattr(self.win, "vypocty", None)
            if v is not None:
                nove = [Bod(f"M{i + 1}", -float(x), -float(y), float(z), poznamka="mračno")
                        for i, (x, y, z) in enumerate(body[:200_000])]
                n, _k = v.seznam.pridej(nove, "Mračno bodů")
                v._after_change()
                self.vypis(f"Do seznamu souřadnic přidáno {n} bodů (M1…).")
        if "v" in a:
            interval = yield Pozadavek("cislo", "Interval vrstevnic [1 m]:", vychozi=1.0)
            pts = [tuple(map(float, b)) for b in body]
            mod = T.model(pts, float(interval or 1), max_strana=TC.automaticka_max_strana(pts), vyhladit=2)
            nove = TC.kresli(self.dok.doc, self.prostor, self.historie_zmen, mod, popis=True, vyska_textu=0.75)
            self.vypis(TC.souhrn(mod) + f" Nakresleno {len(nove)} prvků.")

    def pripoj_rastr(self, cesta: str | None = None):
        """Rastr s world filem se umístí sám; bez něj se zeptá na levý dolní roh a šířku."""
        from ..cad import rastr as RA
        if self.dok is None:
            return None
        if cesta is None:
            cesta, _ = QFileDialog.getOpenFileName(self, "Připojit rastr", "",
                                                   "Obrázky (*.jpg *.jpeg *.png *.tif *.tiff *.bmp)")
            if not cesta:
                return None
        if not self._je_model():
            self.nastav_model("Model")
        zaklad = self.dok.path.parent if self.dok.path else None
        if RA.world_file(cesta) is not None:
            try:
                im = RA.pripoj(self.dok.doc, self.prostor, self.historie_zmen, cesta, zaklad)
            except ValueError as e:
                self.vypis(f"⚠ {e}")
                return None
            self._po_zmene([im], [])
            self.view.zoom_all()
            self.vypis(f"Rastr {Path(cesta).name} připojen podle world filu.")
            return im
        self._spust(self._n_rastr_rucne(cesta, zaklad))
        return None

    def _n_rastr_rucne(self, cesta, zaklad):
        from ..cad import rastr as RA
        a = yield self._bod_req(f"Rastr {Path(cesta).name} nemá world file – levý dolní roh:")
        b = yield self._bod_req("Pravý dolní roh (určí šířku a natočení):", a)
        sirka = math.hypot(b[0] - a[0], b[1] - a[1])
        uhel = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        RA.pripoj(self.dok.doc, self.prostor, self.historie_zmen, cesta, zaklad, a, sirka, uhel)
        self.vypis(f"Rastr připojen, šířka {sirka:.2f} m.")

    def knihovna_bunek(self, cesta: str | None = None) -> list[str]:
        """Buňky (bloky), typy čar a textové styly z jiného DXF nebo knihovny buněk MicroStationu (.CEL) – jako
        připojení knihovny buněk v MicroStationu."""
        from ..cad.zadani import prevezmi_bloky, prevezmi_styly
        if self.dok is None:
            return []
        if cesta is None:
            cesta, _ = QFileDialog.getOpenFileName(self, "Knihovna buněk", "",
                                                   "Knihovna buněk (*.cel *.dxf);;Typy čar (*.lin)")
            if not cesta:
                return []
        styly = prevezmi_styly(self.dok.doc, [cesta]) if not cesta.lower().endswith(".cel") else []
        bloky = prevezmi_bloky(self.dok.doc, [cesta]) if cesta.lower().endswith((".dxf", ".cel")) else []
        if self.historie_zmen is not None:
            self.historie_zmen.zmena += 1
        self._titulek()
        self.vypis(f"Z knihovny {Path(cesta).name}: {len(bloky)} buněk"
                   + (f" ({', '.join(bloky[:15])}{'…' if len(bloky) > 15 else ''})" if bloky else "")
                   + (f", {len(styly)} stylů" if styly else "") + ". Vložení příkazem „vlož“.")
        return bloky

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
            vzory += [a.path for a in pr.attachments() if a.path.suffix.lower() in (".cel", ".lin")
                      and a.kind != "vzor"]  # knihovna buněk a styly čar od učitele
        dok, zprava = novy_dokument(rs, vzory)
        self.nastav_dokument(dok)
        self.sjtsk = rs.rozsah == "sjtsk" or rs.rozsah is None
        self.obnov_predvolby()
        self.vypis("Výkres podle zadání připraven:\n  " + "\n  ".join(zprava))
        return dok

    def _napln_vrstvy(self):
        from .cad_panely import _klic, vzorek
        self.vrstvy.blockSignals(True)
        self.vrstvy.clear()
        if self.dok is not None:
            for ly in sorted(self.dok.doc.layers, key=lambda x: _klic(x.dxf.name)):
                self.vrstvy.addItem(vzorek(self._rgb_hladiny(ly), 12), ly.dxf.name)
            self.vrstvy.setCurrentText(self.kresleni.vrstva)
        self.vrstvy.blockSignals(False)
        self.panel_hladin.napln(self.dok.doc if self.dok else None, self.prostor if self.dok else None,
                                self.kresleni.vrstva if self.kresleni else "", self._rgb_hladiny)
        self._napln_styly()
        self.aktivni_atributy()

    def _rgb_hladiny(self, ly):
        from ezdxf.colors import aci2rgb
        try:
            if ly.dxf.hasattr("true_color"):
                tc = ly.dxf.true_color
                return ((tc >> 16) & 255, (tc >> 8) & 255, tc & 255)
            c = abs(int(ly.dxf.get("color", 7)))
            return (255, 255, 255) if c == 7 else tuple(aci2rgb(c))
        except Exception:  # noqa: BLE001
            return (200, 200, 200)

    def _napln_styly(self):
        """Styly čar (dle hladiny, 0–7, vlastní styly výkresu) a tloušťky s náhledem."""
        from .cad_ikony import ukazka_cary
        from .theme import is_dark
        barva = "#D1D5DB" if is_dark() else "#374151"
        self.styl_cb.blockSignals(True)
        self.styl_cb.clear()
        self.styl_cb.addItem("dle hladiny", "dle")
        for n in range(8):
            self.styl_cb.addItem(ukazka_cary(str(n), 1.5, barva), str(n), str(n))
        if self.dok is not None:
            vlastni = sorted(lt.dxf.name for lt in self.dok.doc.linetypes
                             if lt.dxf.name.upper() not in ("BYLAYER", "BYBLOCK", "CONTINUOUS")
                             and not lt.dxf.name.upper().startswith("DGN STYLE"))
            for jm in vlastni:
                self.styl_cb.addItem(jm, jm)
        self.styl_cb.setIconSize(QSize(60, 14))
        self.styl_cb.blockSignals(False)
        self.tl_cb.blockSignals(True)
        self.tl_cb.clear()
        self.tl_cb.addItem("dle hladiny", "dle")
        for n in range(16):
            self.tl_cb.addItem(ukazka_cary("0", 1 + n * 0.6, barva), str(n), str(n))
        self.tl_cb.setIconSize(QSize(60, 14))
        self.tl_cb.blockSignals(False)

    def _vyber_barvy(self):
        from ..cad import symbologie as S
        from .cad_panely import BarvaDialog
        if self.dok is None:
            return
        k = self.kresleni
        akt = k.ms_barva if k.ms_barva is not None and k.barva != 256 else S.aci_na_ms(k.barva, self._pravidla())
        d = BarvaDialog(S.tabulka(self._pravidla()), akt, self)
        if d.exec() and d.vysledek is not None:
            self._barva("dle" if d.vysledek == 256 else str(d.vysledek))

    def _styl_z_listy(self, i: int):
        v = self.styl_cb.itemData(i)
        if v is not None and self.dok is not None:
            self._styl_tloustka("styl", v)

    def _tloustka_z_listy(self, i: int):
        v = self.tl_cb.itemData(i)
        if v is not None and self.dok is not None:
            self._styl_tloustka("tloušťka", v)

    def _hladina_zobrazeni_panel(self, jm: str, zapnout: bool):
        if self.dok is None or jm not in self.dok.doc.layers:
            return
        ly = self.dok.doc.layers.get(jm)
        if not zapnout and jm == self.kresleni.vrstva:
            self.vypis("Aktivní hladinu nejde vypnout – nejdřív zvolte jinou aktivní hladinu (dvojklik).")
            self._napln_vrstvy()
            return
        ly.on() if zapnout else ly.off()
        self.vrstvy_zmeneny()

    def _hladina_aktivni_panel(self, jm: str):
        if self.kresleni is None or not jm:
            return
        self.kresleni.vrstva = jm
        if self.dok is not None and jm in self.dok.doc.layers and self.dok.doc.layers.get(jm).is_off():
            self.dok.doc.layers.get(jm).on()
            self.vrstvy_zmeneny()
        self.vypis(f"Aktivní hladina: {jm}")
        self._napln_vrstvy()

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
        self._kresli_rastry()
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

    def _kresli_rastry(self):
        """Rastry (IMAGE) jako obrázky pod kresbou – ezdxf kreslí jen jejich rámeček."""
        from PySide6.QtGui import QPixmap, QTransform
        from ..cad import rastr as RA
        sc = self.view.scene()
        self._rastry = []
        zaklad = self.dok.path.parent if self.dok.path else None
        for im in self.prostor.query("IMAGE"):
            f = RA.cesta_obrazku(im, zaklad)
            if f is None:
                self.vypis(f"⚠ Rastr {getattr(im.image_def.dxf, 'filename', '?')} nenalezen – zkontrolujte cestu.")
                continue
            pm = QPixmap(str(f))
            if pm.isNull():
                continue
            it = sc.addPixmap(pm)
            it.setTransform(QTransform(*RA.qt_transform(im)))
            it.setZValue(-20)
            it.setOpacity(getattr(self, "pruhlednost_rastru", 0.85))
            it.setTransformationMode(Qt.SmoothTransformation)
            self._rastry.append(it)

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
            for it in nove:
                _citelne_pero(it)
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
            _citelne_pero(it)
            stack = it.data(CorrespondingDXFParentStack) or ()
            e = stack[0] if stack else it.data(CorrespondingDXFEntity)
            if e is not None:
                self._polozky.setdefault(id(e), []).append(it)

    def _obnov_indexy(self, pridano=None, odebrano=()):
        """Úchyty a index výběru. Po běžné úpravě (``pridano``/``odebrano``) se index výběru jen doplní –
        u výkresu s desítkami tisíc prvků by přepočet celého výkresu trval sekundy."""
        msp = self.prostor
        skryte, zamcene = set(), set()
        for ly in self.dok.doc.layers:
            if ly.is_off() or ly.is_frozen():
                skryte.add(ly.dxf.name)
            if ly.is_locked():
                zamcene.add(ly.dxf.name)
        nevybiratelne = skryte | zamcene
        viditelne = [e for e in msp if e.dxf.get("layer", "0") not in skryte]
        if pridano is not None and self.index is not None and getattr(self.index, "msp", None) is msp:
            self.view.uchyty = Uchyty(viditelne + [e for r in getattr(self, "reference", []) if self._je_model()
                                                   and r.viditelna and r.uchyty and r.pripojena
                                                   for e in r.prvky_pro_uchyty()], self.zapnute_uchyty)
            self.index.zmen(pridano, odebrano, lambda e: e.dxf.get("layer", "0") in nevybiratelne)
            return
        if self._je_model():
            for r in getattr(self, "reference", []):
                if r.viditelna and r.uchyty and r.pripojena:
                    viditelne += r.prvky_pro_uchyty()
        self.view.uchyty = Uchyty(viditelne, self.zapnute_uchyty)
        self.index = U.IndexVyberu(msp, (lambda e: e.dxf.get("layer", "0") in nevybiratelne) if nevybiratelne
                                   else None)

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
        if any(e.dxftype() in ("VIEWPORT", "IMAGE") for e in zmenene) or (
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
        self._obnov_indexy(pridano, odebrano)
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
    def _uchopy(self) -> list:
        """Úchopy vybraných prvků: (prvek, bod, je_vrchol) – vrcholy úseček a polylinií, jinak vkládací bod / střed."""
        out = []
        for e in self.vyber[:30]:
            t = e.dxftype()
            try:
                if t == "LINE":
                    out += [(e, (e.dxf.start.x, e.dxf.start.y), True), (e, (e.dxf.end.x, e.dxf.end.y), True)]
                elif t == "LWPOLYLINE":
                    out += [(e, (p[0], p[1]), True) for p in e.get_points("xy")]
                else:
                    for k in ("center", "insert", "location"):
                        if e.dxf.hasattr(k):
                            v = e.dxf.get(k)
                            out.append((e, (v[0], v[1]), False))
                            break
            except Exception:  # noqa: BLE001
                continue
        return out

    def _zvyrazni(self):
        if getattr(self, "view", None) is not None:
            self.view.uchopy = [b for _e, b, _v in self._uchopy()]
        if getattr(self, "panel_vlastnosti", None) is not None:
            self.panel_vlastnosti.ukaz(self.vyber, self._popis_vlastnosti)
        if self.index is None:
            self.view.zvyraznene = []
        else:
            self.view.zvyraznene = [g for g in (self.index.geometrie(e) for e in self.vyber) if g is not None]
        self.view.viewport().update()

    def _popis_vlastnosti(self, e) -> str:
        """HTML vlastností jednoho prvku (Element Information): atributy jako v MicroStationu a rozměry."""
        from html import escape

        from ..cad import symbologie as S
        rs = self._pravidla()
        d = e.dxf
        k = self.kresleni
        znama = k.ms_barvy_prvku.get(d.handle) if k is not None else None
        b = znama if znama is not None else S.aci_na_ms(d.get("color", 256), rs)
        w = S.lw_na_wt(d.get("lineweight", -1), rs)
        jm = {"LINE": "Úsečka", "LWPOLYLINE": "Lomená čára" + (" (uzavřená)" if getattr(e, "closed", False) else ""),
              "POLYLINE": "Lomená čára", "CIRCLE": "Kružnice", "ARC": "Oblouk", "ELLIPSE": "Elipsa",
              "SPLINE": "Křivka", "POINT": "Bod", "TEXT": "Text", "MTEXT": "Text (víceřádkový)",
              "INSERT": "Buňka", "HATCH": "Šrafa", "DIMENSION": "Kóta"}.get(e.dxftype(), e.dxftype())
        r = [("Typ", jm), ("Hladina", d.get("layer", "0")), ("Barva", b if b is not None else "dle hladiny")]
        if e.dxftype() not in ("TEXT", "MTEXT", "POINT"):
            r += [("Styl", S.typ_na_styl(d.get("linetype", "BYLAYER"))), ("Tloušťka", w if w is not None else
                                                                          "dle hladiny")]
        g = self.index.geometrie(e) if self.index else None
        if g is not None and g.geom_type in ("LineString", "MultiLineString") and g.length > 0:
            r.append(("Délka", f"{g.length:.3f} m"))
        if e.dxftype() in ("CIRCLE", "ARC"):
            r.append(("Poloměr", f"{d.radius:.3f} m"))
        if e.dxftype() == "LWPOLYLINE" and e.closed:
            from shapely.geometry import Polygon
            try:
                pg = Polygon([p[:2] for p in e.get_points("xy")])
                r.append(("Výměra", f"{pg.area:.2f} m²"))
                r.append(("Obvod", f"{pg.length:.2f} m"))
            except Exception:  # noqa: BLE001
                pass
        if e.dxftype() == "INSERT":
            r += [("Název", d.name), ("Měřítko", f"{d.get('xscale', 1.0):g}"), ("Natočení", f"{d.get('rotation', 0):.2f}°")]
        if e.dxftype() in ("TEXT", "MTEXT"):
            r += [("Text", e.plain_text() if e.dxftype() == "MTEXT" else d.text),
                  ("Výška", f"{(d.get('height', 0) if e.dxftype() == 'TEXT' else d.get('char_height', 0)):.3f} m"), ("Styl textu", d.get("style", ""))]
        for klic in ("insert", "center", "location", "start"):
            if d.hasattr(klic):
                v = d.get(klic)
                xy = (f"Y {-v[0]:.3f}, X {-v[1]:.3f}" if self.sjtsk else f"x {v[0]:.3f}, y {v[1]:.3f}")
                r.append(("Poloha" if klic != "start" else "Začátek", xy))
                break
        g_ = U.skupina(e)
        if g_ is not None:
            r.append(("Skupina", g_))
        radky = "".join(f"<tr><td style='color:#9CA3AF;padding-right:10px'>{escape(str(a))}</td>"
                        f"<td>{escape(str(v))}</td></tr>" for a, v in r)
        return f"<table>{radky}</table>"

    def _tol(self) -> float:
        return 8.0 / max(1e-12, abs(self.view.transform().m11()))

    def vyber_v_bode(self, x, y, pridat: bool = True):
        if self.index is None:
            return None
        e = self.index.najdi(x, y, self._tol())
        if e is None:
            return None
        cleny = [e]
        g = U.skupina(e) if getattr(self, "zamek_skupin", True) else None
        if g is not None:  # zámek skupin: klik na prvek vybere celou skupinu (Graphic Group lock)
            cleny = [x for x in U.cleny_skupiny(self.prostor, g) if self.index.geometrie(x) is not None] or [e]
        if e in self.vyber and (pridat or len(self.vyber) == len(cleny)):
            for x in cleny:
                if x in self.vyber:
                    self.vyber.remove(x)
        else:
            if not pridat:
                self.vyber = []
            self.vyber += [x for x in cleny if x not in self.vyber]
        self._zvyrazni()
        return e

    def _okno(self, x0, y0, x1, y1):
        if self.index is None:
            return
        if self._req is not None and self._req.typ not in ("vyber",):
            return
        nove = self.index.okno(x0, y0, x1, y1, protinajici=x1 < x0)
        if self._req is None and not (QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
            self.vyber = []  # nový výběr oknem (Ctrl = přidat k výběru)
        for e in nove:
            if e not in self.vyber:
                self.vyber.append(e)
        self._zvyrazni()
        self.vypis(f"Vybráno {len(self.vyber)} prvků.")

    # ------------------------------------------------------------ kurzor a vstupy
    def _druh_uchytu(self, k: str, on: bool):
        from PySide6.QtCore import QSettings
        (self.zapnute_uchyty.add if on else self.zapnute_uchyty.discard)(k)
        QSettings("KontrolaVykresu", "KontrolaVykresu").setValue("cad/uchyty", sorted(self.zapnute_uchyty))
        if self.view.uchyty is not None:
            self.view.uchyty.zapnute = set(self.zapnute_uchyty)

    def _reset(self):
        """Pravé tlačítko (Reset): ukončí řetězec bodů (jako Enter), jinde zruší nástroj; bez nástroje zruší výběr."""
        r = self._req
        if self._gen is not None and r is not None:
            if r.typ == "vyber" and self.vyber:
                self._posli(list(self.vyber))
            elif r.volitelne or r.vychozi is not None:
                self._odpoved("")
            else:
                self.zrus()
        elif self.vyber:
            self.vyber = []
            self._zvyrazni()
        self.view.viewport().update()

    def _pod_kurzorem(self, x, y):
        """Zvýrazní prvek pod kurzorem, když se vybírá (bez nástroje nebo při výběru prvku)."""
        r = self._req
        g = None
        if self.index is not None and self.view.mys is not None and (
                self._gen is None or (r is not None and r.typ in ("vyber", "prvek"))):
            mx, my = self.view.mys
            e = self.index.najdi(mx, my, self._tol())
            if e is not None and e not in self.vyber:
                g = self.index.geometrie(e)
        self.view.pod_kurzorem = g

    def _pohyb(self, x, y):
        self._pod_kurzorem(x, y)
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
        if self.vyber and self._gen is None:  # klik na úchop vybraného prvku → úprava vrcholu / posun prvku
            tol = 7.0 / max(1e-12, abs(self.view.transform().m11()))
            for e, b, vrchol in self._uchopy():
                if math.hypot(mx - b[0], my - b[1]) <= tol:
                    self._posledni_prikaz = None
                    self._spust(self._n_uchop(e, b, vrchol))
                    return
        # jako v MicroStationu: klik vybere prvek (nahradí výběr), Ctrl+klik přidá / ubere, klik do prázdna zruší
        pridat = bool(QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        if self.vyber_v_bode(mx, my, pridat=pridat) is None and not pridat and self.vyber:
            self.vyber = []
            self._zvyrazni()

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
        self.view.nahled = None
        self.view.vyber_oknem = True
        self.vyzva.setText("Příkaz:")
        if getattr(self, "paleta", None) is not None:
            self.paleta.oznac(None)
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
            prima = self._prima_delka(t)
            if prima is not None:
                if isinstance(prima, str):
                    self.vypis(prima)
                    return
                x, y = prima
                self.vypis(f"> bod {(-x if self.sjtsk else x):.3f} {(-y if self.sjtsk else y):.3f}")
                self._posli((x, y))
                return
            try:
                x, y = zadani_bodu(t, self.view.posledni, self.sjtsk, self._bod_seznamu)
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

    def _prima_delka(self, t: str):
        """Přímé zadání délky (jako AccuDraw): samotné číslo = bod v té vzdálenosti od posledního bodu
        ve směru kurzoru (i se zapnutým pravoúhlým / polárním režimem). Vrací bod, chybovou hlášku, nebo None,
        když nejde o samotné číslo."""
        try:
            d = float(t.strip().replace(",", "."))
        except ValueError:
            return None
        if not math.isfinite(d) or d <= 0:
            return "Délka musí být kladné číslo."
        a, k = (self.view.posledni if self.view.gumicka else None), self.view.kurzor
        if a is None:
            return "Samotné číslo je délka od předchozího bodu – nejdřív zadejte první bod."
        if k is None or math.hypot(k[0] - a[0], k[1] - a[1]) < 1e-12:
            return "Najeďte myší směrem, kterým má délka vést, a zadejte ji znovu."
        u = math.hypot(k[0] - a[0], k[1] - a[1])
        return a[0] + (k[0] - a[0]) / u * d, a[1] + (k[1] - a[1]) / u * d

    def _je_prikaz(self, t: str) -> bool:
        slovo = (t.strip().split() or [""])[0].lower()
        return t.lower() in self.ALIASY or slovo in self.ALIASY or slovo in self.PRIKAZY

    # ------------------------------------------------------------ běh nástroje
    def _spust(self, gen):
        self._gen = gen
        if getattr(self, "paleta", None) is not None:
            self.paleta.oznac(self._posledni_prikaz)
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
            self.view.nahled = r.nahled
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
        self.view.nahled = None
        if getattr(self, "paleta", None) is not None:
            self.paleta.oznac(None)
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
                x, y = zadani_bodu(t, self.view.posledni, self.sjtsk, self._bod_seznamu)
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
        elif cmd == "předchozí pohled":
            if not self.view.predchozi_pohled():
                self.vypis("Žádný předchozí pohled.")
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
            # jako MicroStation: prvky ve vypnutých, zmrazených a zamčených hladinách se nevybírají
            ly = self.dok.doc.layers
            nelze = {x.dxf.name for x in ly if not x.is_on() or x.is_frozen() or x.is_locked()}
            self.vyber = [e for e in self.prostor if e.dxf.get("layer", "0") not in nelze
                          and e.dxftype() != "VIEWPORT"]
            self._zvyrazni()
            self.vypis(f"Vybráno {len(self.vyber)} prvků.")
        elif cmd == "vrstvy":
            self.spravce_vrstev()
        elif cmd == "tisk":
            self.tisk_pdf()
        elif cmd == "body":
            self.body_ze_seznamu()
        elif cmd == "knihovna buněk":
            self.knihovna_bunek()
        elif cmd == "rastr":
            self.pripoj_rastr()
        elif cmd == "mračno":
            self.nacti_mracno()
        elif cmd == "vlastnosti":
            if len(self.vyber) != 1:
                self.vypis("Vyberte jeden prvek (nebo na něj dvakrát klikněte).")
            else:
                self.vlastnosti_prvku(self.vyber[0])
        elif cmd in ("zhasni", "rozsviť"):
            self.hladiny_zobrazeni(arg, cmd == "rozsviť")
        elif cmd == "délka":
            if not self.vyber:
                self.vypis("Vyberte čáry (klik, okno, „vyber …“), pak „délka“.")
            else:
                d, n = U.delka_prvku(self.vyber)
                self.vypis(f"Celková délka {n} čar: {d:.3f} m" + (" (body, texty a buňky se nepočítají)"
                                                                   if n < len(self.vyber) else ""))
        elif cmd == "vyber":
            try:
                self.vyber, popis = U.vyber_podle(self.prostor, arg)
            except ValueError as e:
                self.vypis(f"⚠ {e}")
                return
            self._zvyrazni()
            self.vypis(f"Vybráno {len(self.vyber)} prvků ({popis}).")
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
        # lišta atributů ukazuje aktivní hodnoty
        self.vrstvy.blockSignals(True)
        self.vrstvy.setCurrentText(k.vrstva)
        self.vrstvy.blockSignals(False)
        if b is None or k.barva == 256:
            self.b_barva.setText("dle hl.")
            self.b_barva.setIcon(QIcon())
        else:
            from .cad_panely import vzorek
            self.b_barva.setText(str(b))
            self.b_barva.setIcon(vzorek(S.tabulka(rs).get(int(b), (128, 128, 128)), 12))
        st = S.typ_na_styl(k.typ_cary)
        for cb, val in ((self.styl_cb, "dle" if st == "dle hladiny" else st),
                        (self.tl_cb, "dle" if w is None or k.tloustka == -1 else str(w))):
            cb.blockSignals(True)
            i = cb.findData(val)
            if i < 0 and cb is self.styl_cb and val not in ("dle",):
                cb.addItem(val, val)
                i = cb.findData(val)
            cb.setCurrentIndex(max(0, i))
            cb.blockSignals(False)
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
        p = U.vymera_prvku(e)
        if p is None:
            p = Polygon(g.coords).area
        obvod = U._delka_jednoho(e) or (g.length + (0 if g.is_closed else math.dist(g.coords[0], g.coords[-1])))
        self.vypis(f"Výměra {p:.2f} m², obvod {obvod:.3f} m")

    # ------------------------------------------------------------ nástroje kreslení
    def _bod_seznamu(self, cislo: str):
        v = getattr(self.win, "vypocty", None)
        return v.seznam.najdi(cislo) if v is not None else None

    def _bod_req(self, vyzva, ref=None, volitelne=False, slova=(), nahled=None):
        return Pozadavek("bod", vyzva, volitelne, slova, ref, nahled=nahled)

    def _geometrie_vyberu(self, ents) -> list:
        """Geometrie prvků pro dynamický náhled úprav (nejvýš 3000 prvků – jinak by náhled zdržoval)."""
        if self.index is None:
            return []
        out = []
        for e in ents[:3000]:
            g = self.index.geometrie(e)
            if g is not None and not g.is_empty:
                out.append(g)
        return out

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
                                    ("k", "z"), nahled=lambda x, y, b=list(body): [_linie(b + [(x, y)])])
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
        b = yield self._bod_req("Protější roh:", a, nahled=lambda x, y: [_obdelnik(a, (x, y))])
        self.kresleni.obdelnik(a, b)

    def n_kruznice(self):
        s = yield self._bod_req("Kružnice – střed (3 = třemi body, p = průměrem):", slova=("3", "p"))
        if s == "3":
            a = yield self._bod_req("Kružnice třemi body – první bod:")
            b = yield self._bod_req("Druhý bod:", a)
            c = yield self._bod_req("Třetí bod:", b, nahled=lambda x, y: [_kruh3(a, b, (x, y))])
            self.kresleni.kruznice_3body(a, b, c)
            return
        if s == "p":
            a = yield self._bod_req("Kružnice průměrem – první bod:")
            b = yield self._bod_req("Druhý konec průměru:", a, nahled=lambda x, y: [_kruh(
                ((a[0] + x) / 2, (a[1] + y) / 2), math.hypot(x - a[0], y - a[1]) / 2)])
            self.kresleni.kruznice_prumer(a, b)
            return
        r = yield Pozadavek("cislo", "Poloměr (číslo nebo klikněte bod na kružnici):", ref=s,
                            nahled=lambda x, y: [_kruh(s, math.hypot(x - s[0], y - s[1]))])
        self.kresleni.kruznice(s, r)

    def n_oblouk(self):
        a = yield self._bod_req("Oblouk – počáteční bod (s = středem):", slova=("s",))
        if a == "s":
            st = yield self._bod_req("Oblouk středem – střed:")
            z = yield self._bod_req("Počáteční bod (určuje poloměr):", st)
            k = yield self._bod_req("Konec oblouku – směr (proti směru hodin, h = po směru):", st, slova=("h",))
            if k == "h":
                k = yield self._bod_req("Konec oblouku – směr (po směru hodin):", st)
                self.kresleni.oblouk_stred(st, z, k, proti_smeru=False)
            else:
                self.kresleni.oblouk_stred(st, z, k)
            return
        b = yield self._bod_req("Bod na oblouku:", a)
        c = yield self._bod_req("Koncový bod:", b, nahled=lambda x, y: [_oblouk3(a, b, (x, y))])
        self.kresleni.oblouk_3body(a, b, c)

    def n_elipsa(self):
        s = yield self._bod_req("Elipsa – střed:")
        a = yield self._bod_req("Konec první poloosy:", s)
        b = yield Pozadavek("cislo", "Délka druhé poloosy (číslo nebo bod):", ref=s,
                            nahled=lambda x, y: [_elipsa(s, a, math.hypot(x - s[0], y - s[1]))])
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

    def _n_uchop(self, e, b, vrchol: bool):
        """Tah za úchop: vrchol úsečky / polylinie na nové místo, jiný prvek posunout celý (s náhledem)."""
        g = self.index.geometrie(e) if self.index else None
        if vrchol:
            if e.dxftype() == "LINE":
                pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
                zavr = False
            else:
                pts = [tuple(p[:2]) for p in e.get_points("xy")]
                zavr = bool(e.closed)
            i = min(range(len(pts)), key=lambda k: math.hypot(pts[k][0] - b[0], pts[k][1] - b[1]))

            def nahled(x, y):
                q = list(pts)
                q[i] = (x, y)
                return [_linie(q + ([q[0]] if zavr else []))]
            n = yield self._bod_req("Nová poloha vrcholu (pravé tlačítko = zrušit):", b, nahled=nahled)
            nove = U.posun_vrchol(self.prostor, self.historie_zmen, e, b, n)
            self._hotovo_vyber([nove])
        else:
            n = yield self._bod_req("Nová poloha prvku (pravé tlačítko = zrušit):", b,
                                    nahled=lambda x, y: _posunute([g] if g is not None else [], x - b[0], y - b[1]))
            self._hotovo_vyber(U.posun(self.prostor, self.historie_zmen, [e], n[0] - b[0], n[1] - b[1]))

    def _z_palety(self, cmd: str):
        if cmd == "text" and self.dok is not None:
            self.text_dialog()
        else:
            self.proved(cmd)

    def text_dialog(self, modal: bool = True):
        """Okno pro text (jako Text Editor v MicroStationu): text na více řádků, výška, natočení, zarovnání;
        pak se text umístí kliknutím s náhledem rámečku."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout
        if self.dok is None:
            return None
        d = QDialog(self)
        d.setWindowTitle("Text")
        f = QFormLayout(d)
        txt = QPlainTextEdit()
        txt.setPlaceholderText("Text (víc řádků = víc textů pod sebou)")
        txt.setMinimumSize(360, 90)
        f.addRow("Text:", txt)
        vys = QDoubleSpinBox()
        vys.setRange(0.01, 1000)
        vys.setDecimals(3)
        vys.setSuffix(" m")
        p = self.predvolba
        vys.setValue(self.kresleni.vyska_textu or (p.vyska if p is not None and p.vyska else self.vyska_textu))
        f.addRow("Výška:", vys)
        nat = QDoubleSpinBox()
        nat.setRange(-360, 360)
        nat.setDecimals(2)
        nat.setSuffix(" °")
        f.addRow("Natočení:", nat)
        zar = QComboBox()
        for jm, kod in (("vlevo dole (výchozí)", None), ("vlevo uprostřed", "MIDDLE_LEFT"), ("na střed", "MIDDLE_CENTER"),
                        ("vpravo dole", "BOTTOM_RIGHT"), ("vlevo nahoře", "TOP_LEFT"), ("střed dole", "BOTTOM_CENTER")):
            zar.addItem(jm, kod)
        i = zar.findData(self.kresleni.zarovnani)
        zar.setCurrentIndex(max(0, i))
        f.addRow("Zarovnání:", zar)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Umístit")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        d.txt, d.vys, d.nat, d.zar = txt, vys, nat, zar  # pro testy
        if not modal:
            return d
        if d.exec():
            self.umisti_text(txt.toPlainText(), vys.value(), nat.value(), zar.currentData())
        return d

    def umisti_text(self, text: str, vyska: float, natoceni: float = 0.0, zarovnani=None):
        radky = [r for r in (text or "").splitlines() if r.strip()]
        if not radky:
            self.vypis("Prázdný text – nic se neumístí.")
            return
        self.vyska_textu = vyska
        self.kresleni.zarovnani = zarovnani
        self._posledni_prikaz = "text"
        self._spust(self._n_umisti_text(radky, vyska, natoceni))

    def _n_umisti_text(self, radky, v, a):
        r = math.radians(a)
        sirka = max(len(t) for t in radky) * v * 0.75 * (self.kresleni.sirka_faktor or 1.0)
        krok = v * 1.6

        def ramecek(x, y):
            from shapely.geometry import LineString
            out = []
            for i in range(len(radky)):
                ox, oy = x + math.sin(r) * krok * i, y - math.cos(r) * krok * i
                pts = [(0, 0), (sirka, 0), (sirka, v), (0, v), (0, 0)]
                out.append(LineString([(ox + px * math.cos(r) - py * math.sin(r), oy + px * math.sin(r) + py * math.cos(r))
                                       for px, py in pts]))
            return out

        while True:
            p = yield self._bod_req(f"Umístit text „{radky[0][:30]}“ – klikněte bod (Enter = konec):", volitelne=True,
                                    nahled=ramecek)
            if p is None:
                return
            for i, t in enumerate(radky):
                self.kresleni.text((p[0] + math.sin(r) * krok * i, p[1] - math.cos(r) * krok * i), t, v, a)

    def n_popisek(self):
        body = [(yield self._bod_req("Popisek – hrot šipky (bod, na který popisek ukazuje):"))]
        while True:
            q = yield self._bod_req("Další bod odkazové čáry (Enter = konec čáry):", body[-1], len(body) > 1)
            if q is None:
                break
            body.append(q)
            self.view.zvyraznene = [_linie(body)]
        v = yield Pozadavek("cislo", f"Výška textu [{self.vyska_textu}]:", vychozi=self.vyska_textu)
        self.vyska_textu = v
        t = yield Pozadavek("text", "Text popisku:")
        self.kresleni.popisek(body, t, v)

    def n_srafa(self):
        e, _k = yield Pozadavek("prvek", "Šrafa – klikněte na uzavřenou polylinii nebo kružnici:")
        vz = yield Pozadavek("text", "Vzor šrafy [SOLID] (např. ANSI31, NET):", vychozi="SOLID")
        m = 1.0
        if vz.upper() != "SOLID":
            m = yield Pozadavek("cislo", "Měřítko vzoru [1]:", vychozi=1.0)
        self.kresleni.sraf(e, vz, m)

    def n_kopiruj_do_schranky(self):
        from ..cad import schranka as S
        ents = yield from self._vyber_req("Kopírovat do schránky")
        n = S.kopiruj(self.dok.doc, ents)
        self.vypis(f"Do schránky zkopírováno {n} prvků – Ctrl+V je vloží (i do jiného výkresu) na stejné souřadnice.")

    def n_vloz_ze_schranky(self):
        from ..cad import schranka as S
        if not self._je_model():
            self.nastav_model("Model")
        nove = S.vloz(self.dok.doc, self.prostor, self.historie_zmen)
        self._hotovo_vyber(nove)
        self.vypis(f"Vloženo {len(nove)} prvků ze schránky (vybrané – jde je hned posunout).")
        return
        yield  # generátor

    def n_body_po_prvku(self):
        e, _k = yield Pozadavek("prvek", "Body po prvku – klikněte na čáru:")
        t = yield Pozadavek("text", "Počet dílů (např. 5) nebo vzdálenost s „d“ (např. d20):", vychozi="d10")
        t = (t or "").strip().lower().replace(",", ".")
        if t.startswith("d"):
            nove = U.body_po_prvku(self.prostor, self.historie_zmen, e, vzdalenost=float(t[1:]), attrs=self.kresleni._attr())
        else:
            nove = U.body_po_prvku(self.prostor, self.historie_zmen, e, pocet=int(float(t)), attrs=self.kresleni._attr())
        self.vypis(f"Vloženo {len(nove)} bodů po prvku.")

    def n_transformace(self):
        """Transformace výkresu podle identických bodů (jako geodetická transformace v MicroStationu / Gromě):
        bod ve výkresu (úchyt) → cílové souřadnice (Y X, #číslo bodu ze seznamu, nebo klik)."""
        ents = list(self.vyber) or [e for e in self.prostor if e.dxftype() != "VIEWPORT"]
        if not ents:
            raise ValueError("Výkres je prázdný.")
        d = yield Pozadavek("text", "Transformace – druh [p] (s = shodnostní, p = podobnostní / Helmert, a = afinní):",
                            vychozi="p")
        druh = {"s": "shodnostni", "p": "podobnostni", "a": "afinni", "h": "podobnostni"}.get(
            (d or "p").strip().lower()[:1])
        if druh is None:
            raise ValueError("Druh: s, p nebo a.")
        potreba = 3 if druh == "afinni" else 2
        zdroj, cil = [], []
        while True:
            n = len(zdroj) + 1
            a = yield self._bod_req(f"Identický bod {n} ve výkresu" + (" (Enter = konec):" if n > potreba else ":"),
                                    volitelne=n > potreba)
            if a is None:
                break
            b = yield self._bod_req(f"Bod {n} – cílové souřadnice (Y X, #číslo bodu ze seznamu nebo klik):", a)
            zdroj.append(a)
            cil.append(b)
        from ..geodezie.vypocty import transformace
        tr = transformace(zdroj, cil, druh)
        radky = []
        for i, (vx, vy) in enumerate(tr.opravy, 1):
            vY, vX = (-vx, -vy) if self.sjtsk else (vx, vy)
            radky.append(f"  {i}: v{'Y' if self.sjtsk else 'x'} = {vY * 1000:+.1f} mm, v{'X' if self.sjtsk else 'y'} = "
                         f"{vX * 1000:+.1f} mm, |v| = {math.hypot(vx, vy) * 1000:.1f} mm")
        self.vypis(f"Transformace {druh}: {len(zdroj)} identických bodů, m0 = {tr.m0 * 1000:.1f} mm, měřítko "
                   f"{tr.meritko:.7f}, otočení {tr.rotace / GON:.5f} g\n" + "\n".join(radky))
        ok = yield Pozadavek("text", f"Transformovat {len(ents)} prvků? [a] (a/n):", vychozi="a")
        if ok.strip().lower() not in ("a", "ano", "y", "yes"):
            self.vypis("Transformace zrušena.")
            return
        nove, _tr, podob = U.transformace_vykresu(self.prostor, self.historie_zmen, ents, zdroj, cil, druh)
        self.vyber = []
        self._zvyrazni()
        self.view.zoom_all()
        self.vypis(f"Transformováno {len(nove)} prvků." + (f" {podob} prvků (kružnice, texty, buňky) jen podobnostně"
                                                          " – afinní zkosení na ně nejde použít." if podob else ""))
        rastry = [e for e in nove if e.dxftype() == "IMAGE"]
        if rastry:
            t = yield Pozadavek("text", f"Uložit polohu {len(rastry)} rastru do world filu (.jgw/.tfw…) vedle "
                                "obrázku? [a] (a/n):", vychozi="a")
            if (t or "a").strip().lower() in ("a", "ano", "y", "yes"):
                from ..cad import rastr as RA
                zaklad = self.dok.path.parent if self.dok.path else None
                for im in rastry:
                    try:
                        self.vypis(f"World file uložen: {RA.uloz_world_file(im, zaklad).name}")
                    except (ValueError, OSError) as ex:
                        self.vypis(f"⚠ {ex}")

    def n_georeference(self):
        """Transformace rastru podle identických bodů (Raster Manager → Warp): klik na rastr, pak dvojice
        bod v rastru → cílové souřadnice; opravy, m0 a uložení world filu."""
        im, _k = yield Pozadavek("prvek", "Georeference – klikněte na rastr:")
        if im.dxftype() != "IMAGE":
            raise ValueError("Vyberte rastr (připojený obrázek).")
        self.vyber = [im]
        self._zvyrazni()
        yield from self.n_transformace()

    def _najdi_predvolbu(self, text: str):
        t = (text or "").strip().lower()
        if not t:
            return None
        for p in self._predvolby:
            if t == p.kod.lower() or t == p.nazev.lower():
                return p
        for test in (lambda p: p.nazev.lower().split(" – ")[-1].startswith(t) or p.kod.lower().startswith(t),
                     lambda p: t in p.nazev.lower()):
            kand = [p for p in self._predvolby if test(p)]
            if kand:
                return kand[0] if len(kand) == 1 else None
        return None

    def n_prevod_atributu(self):
        """Převod na pravidla ze zadání: podle značky (buňka, styl čáry), zbytek po skupinách podle vrstvy."""
        from ..cad import prevod as PV
        from ..cad.zadani import priprav_dokument
        rs = self._pravidla()
        if rs is None or not self._predvolby:
            raise ValueError("Nejsou cílová pravidla – nahrajte Směrnici (pravidla) v Zadání.")
        ents = list(self.vyber) or [e for e in self.prostor]
        t = yield Pozadavek("text", "Poměr měřítek pro velikosti, které pravidla neurčují (např. 1000:500 "
                            "nebo 0.5) [1]:", vychozi="1")
        try:
            if ":" in t:
                a, b = (float(x.replace(",", ".")) for x in t.split(":", 1))
                k = b / a
            else:
                k = float(t.replace(",", "."))
            if not math.isfinite(k) or k <= 0:
                raise ValueError
        except (ValueError, ZeroDivisionError):
            raise ValueError("Poměr měřítek zadejte jako 1000:500 nebo číslo (0.5).") from None
        navrh = PV.navrhni(ents, self._predvolby)
        self.vypis(f"Podle značky (buňka, styl čáry) přiřazeno {len(navrh.prirazeni)} prvků, "
                   f"zbývá {len(navrh.skupiny)} skupin podle vrstvy.")
        mapa = {}
        for sk in navrh.skupiny:
            while True:
                odp = yield Pozadavek("text", f"{sk.popis()} → druh prvku (kód nebo část názvu; Enter = ponechat):",
                                      vychozi="")
                if not odp:
                    break
                p = self._najdi_predvolbu(odp)
                if p is not None:
                    mapa[(sk.vrstva, sk.druh, sk.styl)] = p
                    self.vypis(f"  → {p.nazev}")
                    break
                self.vypis(f"⚠ „{odp}“ neodpovídá právě jednomu druhu prvku – zadejte přesnější kód nebo název.")
        navrh = PV.navrhni(ents, self._predvolby, mapa)
        priprav_dokument(self.dok.doc, rs)  # vrstvy, styly čar a písma cílových pravidel
        nove, stare = PV.proved(self.dok.doc, self.prostor, self.historie_zmen, navrh, k)
        self._napln_vrstvy()
        self.vyber = []
        self._zvyrazni()
        zb = sum(len(s.prvky) for s in navrh.skupiny)
        self.vypis(f"Převedeno {len(nove)} prvků" + (f", beze změny {zb}" if zb else "") + ":\n  "
                   + "\n  ".join(f"{n}: {c}×" for n, c in list(PV.souhrn(navrh).items())[:25]))

    def n_mnohouhelnik(self):
        st = yield self._bod_req("Mnohoúhelník – střed:")
        v = yield self._bod_req("První vrchol:", st)
        n = yield Pozadavek("cislo", "Počet stran [4]:", vychozi=4)
        self.kresleni.mnohouhelnik(st, v, int(n))

    def hladiny_zobrazeni(self, arg: str, zapnout: bool) -> int:
        """Zapnutí / vypnutí hladin příkazem (jako Level Display): jméno, „vše“ nebo „vše kromě X“."""
        if self.dok is None:
            return 0
        arg = (arg or "").strip()
        if not arg:
            self.vypis("Zadejte hladinu, např. „zhasni 58“ nebo „rozsviť vše“.")
            return 0
        vrstvy = list(self.dok.doc.layers)
        if arg.lower() in ("vše", "vse", "all", "*"):
            cil, krome = vrstvy, set()
        elif arg.lower().startswith(("vše kromě", "vse krome")):
            krome = {x.strip().lower() for x in arg.split(maxsplit=2)[2].replace(",", " ").split()}
            cil = [ly for ly in vrstvy if ly.dxf.name.lower() not in krome]
        else:
            jmena = {x.strip().lower() for x in arg.replace(",", " ").split()}
            cil = [ly for ly in vrstvy if ly.dxf.name.lower() in jmena]
            if not cil:
                self.vypis(f"⚠ Hladina „{arg}“ ve výkresu není.")
                return 0
        aktivni = (self.kresleni.vrstva or "0").lower()
        n = 0
        for ly in cil:
            if not zapnout and ly.dxf.name.lower() == aktivni:
                continue  # aktivní hladinu nejde vypnout (jako v MicroStationu)
            if ly.is_on() != zapnout:
                ly.on() if zapnout else ly.off()
                n += 1
        self.vrstvy_zmeneny()
        self.vypis(f"{'Zapnuto' if zapnout else 'Vypnuto'} {n} hladin.")
        return n

    def n_sit(self):
        ext = self.dok.rozsah() if self.dok is not None else None
        if ext is None:
            raise ValueError("Výkres je prázdný – síť se kreslí v rozsahu kresby.")
        rs = self._pravidla()
        m = float(rs.meritko) if rs is not None and getattr(rs, "meritko", None) else 1000.0
        i = yield Pozadavek("cislo", f"Interval sítě v metrech [{m / 10:g}]:", vychozi=m / 10)
        r = yield Pozadavek("cislo", f"Délka ramene křížku v metrech [{m / 500:g}] (≈ 2 mm v mapě):", vychozi=m / 500)
        p = yield Pozadavek("text", "Popisy souřadnic? a / n [n]:", vychozi="n")
        nove = U.souradnicova_sit(self.prostor, self.historie_zmen, ext, i, r,
                                  (p or "n").strip().lower().startswith("a"), self.vyska_textu,
                                  self.kresleni._attr(), self.sjtsk)
        self.vypis(f"Vloženo {len(nove)} prvků souřadnicové sítě.")

    def n_uprav_text(self):
        while True:
            e, _k = yield Pozadavek("prvek", "Upravit text – klikněte na text (Esc = konec):")
            if e.dxftype() not in ("TEXT", "MTEXT"):
                self.vypis("⚠ To není text.")
                continue
            stary = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
            novy = yield Pozadavek("text", f"Nový text [{stary}]:", vychozi=stary)
            if novy and novy != stary:
                U.nastav_vlastnosti(self.prostor, self.historie_zmen, e, {"text": novy})

    def n_priblizit(self):
        a = yield self._bod_req("Přiblížit oknem – první roh:")
        b = yield self._bod_req("Protilehlý roh:", a)
        if abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9:
            raise ValueError("Okno má nulovou velikost.")
        self.view.zoom_all(QRectF(min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]), abs(a[1] - b[1])))

    def n_kota(self):
        a = yield self._bod_req("Kóta – první bod:")
        b = yield self._bod_req("Druhý bod:", a)
        c = yield self._bod_req("Poloha kótovací čáry:", b)
        self.kresleni.kota(a, b, c, self.vyska_textu)
        # řetězové kótování (jako Dimension Size v MicroStationu): další kóty navazují ve stejné řadě
        ux, uy = b[0] - a[0], b[1] - a[1]
        delka = math.hypot(ux, uy)
        while delka > 0:
            d = yield self._bod_req("Další bod řetězové kóty (Enter = konec):", b, True)
            if d is None:
                return
            # kótovací čára rovnoběžně s první, ve stejné vzdálenosti od kótovaných bodů
            nx, ny = -uy / delka, ux / delka
            odsaz = (c[0] - a[0]) * nx + (c[1] - a[1]) * ny
            poloha = (d[0] + nx * odsaz, d[1] + ny * odsaz)
            self.kresleni.kota(b, d, poloha, self.vyska_textu)
            b = d

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
        geo = self._geometrie_vyberu(ents)
        b = yield self._bod_req("Bod kam:", a, nahled=lambda x, y: _posunute(geo, x - a[0], y - a[1]))
        self._hotovo_vyber(U.posun(self.prostor, self.historie_zmen, ents, b[0] - a[0], b[1] - a[1]))

    def n_skupina(self):
        ents = yield from self._vyber_req("Skupina")
        if len(ents) < 2:
            raise ValueError("Skupina potřebuje aspoň dva prvky.")
        g = U.nova_skupina(self.prostor)
        nove = U.nastav_skupinu(self.prostor, self.historie_zmen, ents, g)
        self._hotovo_vyber(nove)
        self.vypis(f"Skupina {g}: {len(nove)} prvků. Klik na kterýkoli z nich vybere celou skupinu"
                   + ("" if getattr(self, "zamek_skupin", True) else " (po zapnutí „zámek skupin“)") + ".")

    def n_zrus_skupinu(self):
        ents = yield from self._vyber_req("Zrušit skupinu")
        ents = [e for e in ents if U.skupina(e) is not None]
        if not ents:
            raise ValueError("Vybrané prvky nejsou ve skupině.")
        nove = U.nastav_skupinu(self.prostor, self.historie_zmen, ents, None)
        self._hotovo_vyber(nove)
        self.vypis(f"{len(nove)} prvků vyjmuto ze skupiny.")

    def n_zamek_skupin(self):
        self.zamek_skupin = not getattr(self, "zamek_skupin", True)
        self.vypis("Zámek skupin " + ("zapnut – klik vybere celou skupinu." if self.zamek_skupin
                                      else "vypnut – klik vybere jen jeden prvek."))
        return
        yield  # generátor

    def n_smaz_cast(self):
        while True:
            e, k = yield Pozadavek("prvek", "Smazat část – klikněte na prvek v prvním bodě (Esc = konec):")
            b = yield self._bod_req("Druhý bod (konec mazané části):", k)
            try:
                U.smaz_cast(self.prostor, self.historie_zmen, e, k, b)
            except ValueError as ex:
                self.vypis(f"⚠ {ex}")

    def n_natahni(self):
        a = yield self._bod_req("Natažení – první roh okna (vrcholy uvnitř se posunou):")
        b = yield self._bod_req("Protější roh okna:", a)
        ents = list(self.vyber) or [e for e in self.prostor if e.dxftype() != "VIEWPORT"
                                    and not (self.index and self.index.vynechat and self.index.vynechat(e))]
        z = yield self._bod_req("Bod odkud:")
        k = yield self._bod_req("Bod kam:", z)
        nove = U.natahni(self.prostor, self.historie_zmen, ents, a, b, k[0] - z[0], k[1] - z[1])
        if not nove:
            self.vypis("V okně nejsou žádné vrcholy – nic se nenatáhlo.")
        self._hotovo_vyber(nove)

    def n_kopie(self):
        ents = yield from self._vyber_req("Kopie")
        a = yield self._bod_req("Bod odkud:")
        geo = self._geometrie_vyberu(ents)
        while True:
            b = yield self._bod_req("Bod kam (Enter = konec, p = počet kopií v řadě):", a, True, ("p",),
                                    nahled=lambda x, y: _posunute(geo, x - a[0], y - a[1]))
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

    def n_pole(self):
        ents = yield from self._vyber_req("Pole")
        druh = yield Pozadavek("text", "Druh pole – o = obdélníkové, k = kruhové:", vychozi="o")
        if (druh or "o").strip().lower().startswith("k"):
            s = yield self._bod_req("Střed kruhového pole:")
            n = yield Pozadavek("cislo", "Počet položek (včetně originálu):", vychozi=4)
            u = yield Pozadavek("uhel", "Úhel mezi položkami v gonech (+ proti směru hodin):", vychozi=400 / max(int(n), 1),
                                ref=s)
            ot = yield Pozadavek("text", "Otáčet položky? a / n:", vychozi="a")
            nove = U.pole_kruhove(self.prostor, self.historie_zmen, ents, s, int(n), u * GON,
                                  not (ot or "a").strip().lower().startswith("n"))
        else:
            r = yield Pozadavek("cislo", "Počet řádků:", vychozi=1)
            k = yield Pozadavek("cislo", "Počet sloupců:", vychozi=3)
            dx = yield Pozadavek("cislo", "Rozestup sloupců (x):", vychozi=10.0)
            dy = yield Pozadavek("cislo", "Rozestup řádků (y):", vychozi=10.0)
            nove = U.pole_obdelnikove(self.prostor, self.historie_zmen, ents, int(r), int(k), dx, dy)
        self.vypis(f"Pole: {len(nove)} nových prvků.")

    def n_otoc(self):
        ents = yield from self._vyber_req("Otočení")
        s = yield self._bod_req("Střed otočení:")
        geo = self._geometrie_vyberu(ents)
        u = yield Pozadavek("uhel", "Úhel otočení v gonech (+ proti směru hodin) nebo klikněte směr:", ref=s,
                            nahled=lambda x, y: _otocene(geo, s, math.atan2(y - s[1], x - s[0])))
        self._hotovo_vyber(U.otoc(self.prostor, self.historie_zmen, ents, s, u * GON))

    def n_meritko(self):
        ents = yield from self._vyber_req("Měřítko")
        s = yield self._bod_req("Základní bod:")
        k = yield Pozadavek("cislo", "Měřítko (např. 2 = dvojnásobek, 0.5 = polovina):")
        self._hotovo_vyber(U.meritko(self.prostor, self.historie_zmen, ents, s, k))

    def n_zrcadli(self):
        ents = yield from self._vyber_req("Zrcadlení")
        a = yield self._bod_req("První bod osy:")
        geo = self._geometrie_vyberu(ents)
        b = yield self._bod_req("Druhý bod osy:", a, nahled=lambda x, y: _zrcadlene(geo, a, (x, y)))
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

    def n_zkos(self):
        d1 = yield Pozadavek("cislo", "První délka zkosení:", vychozi=1.0)
        d2 = yield Pozadavek("cislo", "Druhá délka zkosení:", vychozi=d1)
        e1, k1 = yield Pozadavek("prvek", "První úsečka (klikněte na část, která zůstane):")
        e2, k2 = yield Pozadavek("prvek", "Druhá úsečka:")
        U.zkos(self.prostor, self.historie_zmen, e1, k1, e2, k2, d1, d2)

    def n_vloz_vrchol(self):
        e, k = yield Pozadavek("prvek", "Vložit vrchol – klikněte na stranu úsečky / polylinie:")
        b = yield self._bod_req("Poloha nového vrcholu:", k)
        U.vloz_vrchol(self.prostor, self.historie_zmen, e, k, b)

    def n_smaz_vrchol(self):
        while True:
            e, k = yield Pozadavek("prvek", "Smazat vrchol – klikněte u vrcholu polylinie (Esc = konec):")
            try:
                U.smaz_vrchol(self.prostor, self.historie_zmen, e, k)
            except ValueError as ex:
                self.vypis(f"⚠ {ex}")

    def n_posun_vrchol(self):
        e, k = yield Pozadavek("prvek", "Posunout vrchol – klikněte u vrcholu úsečky / polylinie:")
        b = yield self._bod_req("Nová poloha vrcholu:", k)
        U.posun_vrchol(self.prostor, self.historie_zmen, e, k, b)

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
        mv = (p.meritko_bunky if p is not None and p.meritko_bunky else None) or 1.0  # měřítko buňky ze zadání
        m = yield Pozadavek("cislo", f"Měřítko [{mv:g}]:", vychozi=mv)
        u = yield Pozadavek("cislo", "Natočení ve stupních [0]:", vychozi=0.0)
        attrs = self.kresleni._attr()
        while True:
            b = yield self._bod_req("Vkládací bod (Enter = konec):", volitelne=True)
            if b is None:
                return
            ins = U.vloz_blok(self.dok.doc, self.prostor, self.historie_zmen, nazev, b, m, u, self.kresleni.vrstva,
                              attrs=attrs)
            if self.kresleni.ms_barva is not None and attrs.get("color", 256) != 256:
                self.kresleni.ms_barvy_prvku[ins.dxf.handle] = self.kresleni.ms_barva

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

    # ------------------------------------------------------------ model terénu
    def _body_terenu(self):
        """Výškové body pro model terénu: z výběru (body, buňky, 3D čáry), jinak ze seznamu souřadnic."""
        from ..cad import teren_cad as TC
        body = TC.body_z_entit(self.vyber) if self.vyber else []
        if body and not all(abs(b[2]) < 1e-9 for b in body):
            return body, "výběru"
        v = getattr(self.win, "vypocty", None)
        sez = [b for b in (v.seznam.body if v is not None else []) if b.z is not None]
        if not sez:
            raise ValueError("Vyberte výškové body (body nebo buňky se souřadnicí Z), nebo načtěte seznam "
                             "souřadnic s výškami ve Výpočtech.")
        return [(-b.y, -b.x, b.z) for b in sez], "seznamu souřadnic"  # S-JTSK jako v MicroStationu

    def n_kody(self):
        """Kresba z kódů bodů seznamu souřadnic (jako kresba z kódů v Gromě / Atlasu): linie, plochy a značky
        podle kódovníku a zadání."""
        from ..cad import kresba_z_kodu as KZ
        from ..geodezie import kodovnik as KV
        from .kodovnik_dialog import nacti_kodovnik
        v = getattr(self.win, "vypocty", None)
        body = [b for b in (v.seznam.body if v is not None else []) if (b.kod or "").strip()]
        if not body:
            raise ValueError("V seznamu souřadnic (Výpočty) nejsou body s kódem. Kódy se zadávají v terénu "
                             "(totální stanice, QTrig) nebo ve sloupci Kód seznamu souřadnic.")
        kv = nacti_kodovnik(self.win, self._predvolby)
        kr = KV.sestav(body, kv, self._predvolby)
        if not kr.linie and not kr.bodove:
            raise ValueError("Žádný kód bodu není v kódovníku ani v zadání. " + kr.souhrn()
                             + " Upravte kódovník (příkaz „kódovník“).")
        t = yield Pozadavek("text", kr.souhrn() + " Nakreslit? [a]/n:", vychozi="a")
        if (t or "a").strip().lower().startswith("n"):
            return
        r = KZ.kresli(self.dok.doc, self.prostor, self.historie_zmen, kr, self._predvolby, self.kresleni)
        self.vypis(f"Kresba z kódů: {r['linie']} linií, {r['plochy']} ploch, {r['bunky']} značek"
                   + (f", {r['body']} bodů bez buňky" if r["body"] else "") + ".")
        for p in r["poznamky"] + kr.varovani[:5]:
            self.vypis("⚠ " + p)

    def n_kodovnik(self):
        from .kodovnik_dialog import KodovnikDialog
        KodovnikDialog(self.win, self._predvolby, self).exec()
        return
        yield  # generátor kvůli jednotnému volání příkazů

    def n_profil(self):
        """Podélný profil terénu po trase (čára ve výkresu) z modelu terénu – jako profil v Atlasu / GEOPAKu."""
        from ..cad import teren_cad as TC
        from ..geodezie import teren as T
        body, zdroj = self._body_terenu()
        self.vyber = []
        e, _k = yield Pozadavek("prvek", "Profil – klikněte na trasu (úsečka nebo lomená čára):")
        if e.dxftype() == "LINE":
            trasa = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        elif e.dxftype() == "LWPOLYLINE":
            trasa = [tuple(p) for p in e.get_points("xy")]
            if e.closed:
                trasa.append(trasa[0])
        elif e.dxftype() == "POLYLINE":
            trasa = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
        else:
            raise ValueError("Trasa profilu musí být úsečka nebo lomená čára.")
        krok = yield Pozadavek("cislo", "Krok popisu staničení [10 m]:", vychozi=10.0)
        prev = yield Pozadavek("cislo", "Převýšení výšek [10×]:", vychozi=10.0)
        p0 = yield self._bod_req("Umístění profilu – levý dolní roh (srovnávací rovina, staničení 0):")
        t = T.tin(body, TC.automaticka_max_strana(body))
        prof = T.profil(t, trasa, min(float(krok or 10), 5.0))
        nove = TC.kresli_profil(self.dok.doc, self.prostor, self.historie_zmen, prof, p0,
                                prevyseni=float(prev or 10), krok_popisu=float(krok or 10),
                                vyska_textu=self.vyska_textu or 1.5)
        zs = [z for _s, z in prof if z is not None]
        self.vypis(f"Profil z {zdroj}: délka {prof[-1][0]:.2f} m, výšky {min(zs):.2f}–{max(zs):.2f} m, "
                   f"{len(prof)} lomových bodů, nakresleno {len(nove)} prvků.")

    def n_vrstevnice(self):
        """TIN a vrstevnice (jako „Vrstevnice“ v Atlasu / GEOPAK Site): z vybraných výškových bodů (body, buňky,
        3D čáry) nebo ze seznamu souřadnic ve Výpočtech."""
        from ..cad import teren_cad as TC
        from ..geodezie import teren as T
        body, zdroj = self._body_terenu()
        auto = TC.automaticka_max_strana(body)
        interval = yield Pozadavek("cislo", "Vrstevnice – interval [1 m]:", vychozi=1.0)
        if not interval or interval <= 0:
            raise ValueError("Interval musí být kladný.")
        zes = yield Pozadavek("cislo", "Zesílená každá [5.]:", vychozi=5)
        ms = yield Pozadavek("cislo", f"Max. délka strany trojúhelníku [{auto:.0f} m, 0 = bez omezení]:"
                             if auto else "Max. délka strany trojúhelníku [0 = bez omezení]:", vychozi=round(auto or 0))
        t = yield Pozadavek("text", "Vyhladit vrstevnice a kreslit TIN? (v = vyhladit, t = TIN, vt = obojí) [v]:",
                            vychozi="v")
        t = (t or "").strip().lower()
        vp = yield Pozadavek("cislo", "Výška popisu zesílených vrstevnic [0.75 m] (0 = bez popisu):", vychozi=0.75)
        m = T.model(body, float(interval), max_strana=float(ms) or None, zesilena_kazda=int(zes or 0),
                    vyhladit=2 if "v" in t else 0)
        vrstvy, atributy = {}, {}
        for druh, klic in (("zesilena", "zesílen"), ("zakladni", "vrstevnic")):  # podle zadání, je-li v něm
            p = next((q for q in self._predvolby if klic in (q.nazev or "").lower()
                      and (druh == "zesilena" or "zesílen" not in (q.nazev or "").lower())), None)
            if p is not None:
                vrstvy[druh] = p.vrstva
                atributy[druh] = {k: x for k, x in (("color", p.barva), ("lineweight", p.tloustka),
                                                     ("linetype", p.typ_cary)) if x not in (256, -1, "BYLAYER", None)}
        nove = TC.kresli(self.dok.doc, self.prostor, self.historie_zmen, m, tin="t" in t, popis=bool(vp),
                         vyska_textu=float(vp or 0), vrstvy=vrstvy, atributy=atributy)
        self.vypis(f"Z {zdroj}: " + TC.souhrn(m) + f" Nakresleno {len(nove)} prvků.")

    # ------------------------------------------------------------ rozdělení, ohrada, oměrné míry, kóty
    def n_rozdel(self):
        while True:
            e, k = yield Pozadavek("prvek", "Rozdělit – klikněte na prvek v místě rozdělení (Esc = konec):")
            bod = self.view.kurzor if self.view.uchyt is not None and self.view.kurzor else k
            try:
                U.rozdel(self.prostor, self.historie_zmen, e, bod)
            except ValueError as ex:
                self.vypis(f"⚠ {ex}")

    def n_ohrada(self):
        body = [(yield self._bod_req("Ohrada – první bod:"))]
        while True:
            q = yield self._bod_req("Další bod (Enter = vybrat uvnitř, p = vybrat i protnuté):", body[-1], True,
                                    ("p",))
            if q is None or q == "p":
                break
            body.append(q)
            self.view.zvyraznene = [_linie(body + [body[0]])]
        self.vyber = self.index.ohrada(body, protinajici=(q == "p"))
        self._zvyrazni()
        self.vypis(f"Ohrada: vybráno {len(self.vyber)} prvků.")

    def n_omerne_miry(self):
        ents = yield from self._vyber_req("Oměrné míry")
        p = next((q for q in self._predvolby if "oměrn" in (q.nazev or "").lower()), None)
        attrs = {}
        vrstva = None
        if p is not None:
            self.kresleni.nastav_predvolbu(p)
            attrs = self.kresleni._attr(text=True)
            vrstva = p.vrstva
        vys = (p.vyska if p is not None and p.vyska else None) or self.vyska_textu
        v = yield Pozadavek("cislo", f"Výška textu [{vys:g}]:", vychozi=vys)
        nove = U.popis_delek(self.prostor, self.historie_zmen, ents, v, vrstva=vrstva or self.kresleni.vrstva,
                             attrs={k: x for k, x in attrs.items() if k != "layer"})
        self.vypis(f"Popsáno {len(nove)} délek" + (f" (hladina {vrstva} podle zadání)" if vrstva else "") + ".")

    def n_kota_uhlu(self):
        a = yield self._bod_req("Úhlová kóta – bod na prvním rameni:")
        v = yield self._bod_req("Vrchol:", a)
        b = yield self._bod_req("Bod na druhém rameni:", v)
        p = yield self._bod_req("Poloha kótovacího oblouku:", v)
        U.kota_uhlu(self.prostor, self.historie_zmen, v, a, b, p, self.vyska_textu, self.kresleni._attr())

    def n_kota_polomeru(self):
        e, k = yield Pozadavek("prvek", "Kóta poloměru – klikněte na kružnici nebo oblouk:")
        U.kota_polomeru(self.prostor, self.historie_zmen, e, k, self.vyska_textu, self.kresleni._attr())

    # ------------------------------------------------------------ převzetí a změna atributů (Match / Change)
    def n_prevezmi_atributy(self):
        e, _k = yield Pozadavek("prvek", "Převzít atributy – klikněte na vzorový prvek:")
        k, d = self.kresleni, e.dxf
        k.vrstva = d.get("layer", "0")
        if k.vrstva not in self.dok.doc.layers:
            self.dok.doc.layers.add(k.vrstva)
        k.barva = d.get("color", 256)
        k.ms_barva = k.ms_barvy_prvku.get(d.handle)
        if e.dxftype() in ("TEXT", "MTEXT"):
            k.textovy_styl = d.get("style", None)
            self.vyska_textu = d.height if e.dxftype() == "TEXT" else d.char_height
            k.vyska_textu = self.vyska_textu
            k.sirka_faktor = d.get("width", 1.0) if e.dxftype() == "TEXT" else 1.0
        else:
            k.typ_cary = d.get("linetype", "BYLAYER")
            k.tloustka = d.get("lineweight", -1)
        self._napln_vrstvy()
        self.vypis("Aktivní atributy převzaty: " + self.aktivni_atributy())

    def _atributy_aktivni(self, e) -> dict:
        k = self.kresleni
        a = {"layer": k.vrstva, "color": k.barva}
        if e.dxftype() in ("TEXT", "MTEXT"):
            if k.textovy_styl:
                a["style"] = k.textovy_styl
            if e.dxftype() == "TEXT" and k.vyska_textu:
                a["height"] = k.vyska_textu
        elif e.dxftype() not in ("INSERT", "POINT"):
            a["linetype"] = k.typ_cary
            a["lineweight"] = k.tloustka
        return a

    def n_zmen_atributy(self):
        if self.vyber:
            ents = list(self.vyber)
            nove = []
            for e in ents:
                nove += U.zmen_vlastnosti(self.prostor, self.historie_zmen, [e], **self._atributy_aktivni(e))
            self.vyber = nove
            self.vypis(f"Atributy změněny u {len(nove)} prvků.")
            return
        while True:
            e, _k = yield Pozadavek("prvek", "Změnit atributy – klikněte na prvek (Esc = konec):")
            U.zmen_vlastnosti(self.prostor, self.historie_zmen, [e], **self._atributy_aktivni(e))


def _linie(body):
    from shapely.geometry import LineString
    return LineString(body)


def _ascii(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


__all__ = ["CadPage", "CadView", "TYPY"]


# ------------------------------------------------------------------ dynamické náhledy (geometrie Shapely)
def _kruh(s, r: float):
    from shapely.geometry import LineString
    if r <= 0:
        return LineString()
    n = 72
    return LineString([(s[0] + r * math.cos(2 * math.pi * i / n), s[1] + r * math.sin(2 * math.pi * i / n))
                       for i in range(n + 1)])


def _obdelnik(a, b):
    from shapely.geometry import LineString
    return LineString([a, (b[0], a[1]), b, (a[0], b[1]), a])


def _stred_3body(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def _kruh3(a, b, c):
    from shapely.geometry import LineString
    st = _stred_3body(a, b, c)
    return _kruh(st, math.dist(st, a)) if st else LineString([a, b, c])


def _oblouk3(a, b, c):
    from shapely.geometry import LineString
    st = _stred_3body(a, b, c)
    if st is None:
        return LineString([a, b, c])
    r = math.dist(st, a)
    u = [math.atan2(p[1] - st[1], p[0] - st[0]) for p in (a, b, c)]
    proti = (u[1] - u[0]) % (2 * math.pi) < (u[2] - u[0]) % (2 * math.pi)  # b leží mezi a a c proti směru
    rozsah = (u[2] - u[0]) % (2 * math.pi) if proti else -((u[0] - u[2]) % (2 * math.pi))
    n = max(8, int(abs(rozsah) / (2 * math.pi) * 72))
    return LineString([(st[0] + r * math.cos(u[0] + rozsah * i / n), st[1] + r * math.sin(u[0] + rozsah * i / n))
                       for i in range(n + 1)])


def _elipsa(s, a, b: float):
    from shapely.geometry import LineString
    ra = math.dist(s, a)
    if ra <= 0 or b <= 0:
        return LineString()
    u0 = math.atan2(a[1] - s[1], a[0] - s[0])
    pts = []
    for i in range(73):
        t = 2 * math.pi * i / 72
        x, y = ra * math.cos(t), b * math.sin(t)
        pts.append((s[0] + x * math.cos(u0) - y * math.sin(u0), s[1] + x * math.sin(u0) + y * math.cos(u0)))
    return LineString(pts)


def _posunute(geo, dx: float, dy: float) -> list:
    from shapely.affinity import translate
    return [translate(g, dx, dy) for g in geo]


def _otocene(geo, s, uhel_rad: float) -> list:
    from shapely.affinity import rotate
    return [rotate(g, uhel_rad, origin=s, use_radians=True) for g in geo]


def _zrcadlene(geo, a, b) -> list:
    from shapely.affinity import affine_transform
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    if ll < 1e-18:
        return []
    c, s_ = (dx * dx - dy * dy) / ll, 2 * dx * dy / ll  # zrcadlení přes přímku a–b
    m = [c, s_, s_, -c, a[0] - c * a[0] - s_ * a[1], a[1] - s_ * a[0] + c * a[1]]
    return [affine_transform(g, m) for g in geo]

