"""Ikony nástrojů CAD kreslené vektorově (QPainter) – ostré v každé velikosti a barvě vzhledu.

Každá ikona je seznam jednoduchých tvarů v souřadnicích 0–24 (y dolů):
``("l", x1, y1, x2, y2)`` úsečka, ``("p", [(x, y), …], uzavřená)`` lomená čára, ``("c", x, y, r)`` kružnice,
``("a", x, y, r, začátek°, rozsah°)`` oblouk, ``("d", x, y)`` bod, ``("t", x, y, text, velikost)`` text,
``("f", [(x, y), …])`` vyplněný tvar, ``("ar", x1, y1, x2, y2)`` šipka. Tvar s „*“ na konci názvu
(např. ``"l*"``) se kreslí zvýrazňovací barvou – výsledek úpravy (nová kopie, posunutý prvek…).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

IKONY: dict[str, list] = {
    # ---- kreslení
    "úsečka": [("l", 4, 19, 20, 5), ("d", 4, 19), ("d", 20, 5)],
    "polylinie": [("p", [(3, 19), (9, 7), (15, 15), (21, 5)], False), ("d", 3, 19), ("d", 9, 7), ("d", 15, 15),
                  ("d", 21, 5)],
    "obdélník": [("p", [(4, 6), (20, 6), (20, 18), (4, 18)], True)],
    "mnohoúhelník": [("p", [(12, 3), (20.5, 9), (17.5, 19.5), (6.5, 19.5), (3.5, 9)], True)],
    "kružnice": [("c", 12, 12, 8), ("d", 12, 12)],
    "oblouk": [("a", 12, 15, 9, 20, 140), ("d", 3.5, 12), ("d", 20.5, 12), ("d", 12, 6)],
    "elipsa": [("e", 12, 12, 9, 5.5)],
    "křivka": [("s", [(3, 17), (8, 4), (14, 20), (21, 7)])],
    "bod": [("x", 12, 12)],
    "text": [("t", 12, 13, "A", 15)],
    "popisek": [("ar", 15, 8, 5, 19), ("l", 15, 8, 21, 8), ("t", 18, 5.5, "abc", 6)],
    "šrafa": [("p", [(4, 5), (20, 5), (20, 19), (4, 19)], True), ("l", 4, 11, 10, 5), ("l", 4, 17, 16, 5),
              ("l", 8, 19, 20, 7), ("l", 14, 19, 20, 13)],
    "kóta": [("l", 4, 8, 4, 18), ("l", 20, 8, 20, 18), ("ar", 12, 15, 4.5, 15), ("ar", 12, 15, 19.5, 15),
             ("t", 12, 9.5, "12", 7)],
    "kóta úhlu": [("l", 4, 20, 21, 20), ("l", 4, 20, 16, 5), ("a", 4, 20, 11, 0, 51)],
    "kóta poloměru": [("c", 12, 12, 8), ("ar", 12, 12, 17.7, 6.3), ("d", 12, 12)],
    "vlož": [("c", 12, 12, 7), ("l", 7, 7, 17, 17), ("l", 17, 7, 7, 17), ("d*", 12, 12)],
    "body": [("x", 6, 7), ("x", 17, 6), ("x", 9, 17), ("x", 18, 17), ("t", 7.5, 4, "1", 5), ("t", 18, 3, "2", 5)],
    "vrstevnice": [("s", [(3, 18), (8, 14), (14, 16), (21, 11)]), ("s", [(3, 12), (9, 8), (15, 10), (21, 5)]),
                   ("s*", [(5, 21), (10, 19), (16, 21), (21, 18)])],
    "síť": [("l", 4, 8, 8, 8), ("l", 6, 6, 6, 10), ("l", 16, 8, 20, 8), ("l", 18, 6, 18, 10),
            ("l", 4, 18, 8, 18), ("l", 6, 16, 6, 20), ("l", 16, 18, 20, 18), ("l", 18, 16, 18, 20)],
    # ---- úpravy
    "posun": [("p", [(3, 14), (9, 14), (9, 20), (3, 20)], True), ("ar", 8, 15, 15, 8),
              ("p*", [(14, 4), (20, 4), (20, 10), (14, 10)], True)],
    "kopie": [("p", [(3, 12), (11, 12), (11, 20), (3, 20)], True),
              ("p*", [(12, 4), (20, 4), (20, 12), (12, 12)], True)],
    "otoč": [("l", 5, 19, 20, 19), ("l*", 5, 19, 15, 6), ("a", 5, 19, 11, 8, 40), ("d", 5, 19)],
    "měřítko": [("p", [(4, 14), (10, 14), (10, 20), (4, 20)], True),
                ("p*", [(4, 4), (20, 4), (20, 20), (4, 20)], True), ("ar", 10, 14, 18, 6)],
    "zrcadli": [("l", 12, 3, 12, 21), ("f", [(4, 7), (10, 12), (4, 17)]), ("f*", [(20, 7), (14, 12), (20, 17)])],
    "pole": [("p", [(3, 3), (8, 3), (8, 8), (3, 8)], True), ("p*", [(10, 3), (15, 3), (15, 8), (10, 8)], True),
             ("p*", [(17, 3), (22, 3), (22, 8), (17, 8)], True), ("p*", [(3, 11), (8, 11), (8, 16), (3, 16)], True),
             ("p*", [(10, 11), (15, 11), (15, 16), (10, 16)], True),
             ("p*", [(17, 11), (22, 11), (22, 16), (17, 16)], True)],
    "rovnoběžka": [("l", 3, 16, 17, 4), ("l*", 7, 21, 21, 9)],
    "ořež": [("l", 15, 3, 15, 21), ("l", 3, 12, 15, 12), ("ld", 15, 12, 21, 12), ("x*", 18, 12)],
    "prodluž": [("l", 19, 3, 19, 21), ("l", 3, 12, 11, 12), ("ld*", 11, 12, 19, 12)],
    "zaobli": [("l", 4, 20, 4, 12), ("l", 12, 4, 20, 4), ("a*", 12, 12, 8, 90, 90)],
    "zkos": [("l", 4, 20, 4, 11), ("l", 11, 4, 20, 4), ("l*", 4, 11, 11, 4)],
    "rozděl": [("l", 3, 18, 10, 11), ("l", 14, 7, 21, 0 + 0.5), ("x*", 12, 9)],
    "smaž část": [("l", 3, 18, 8, 13), ("ld", 8, 13, 16, 6), ("l", 16, 6, 21, 2), ("d*", 8, 13), ("d*", 16, 6)],
    "natáhni": [("pd*", [(9, 3), (21, 3), (21, 13), (9, 13)], True), ("p", [(3, 20), (3, 9), (14, 9)], False),
                ("ar", 14, 9, 19, 9)],
    "spoj": [("l", 3, 17, 11, 9), ("l", 11, 9, 21, 17), ("c*", 11, 9, 2.2)],
    "rozpoj": [("p", [(3, 18), (8, 6)], False), ("p", [(10, 6), (14, 18)], False), ("p", [(16, 18), (21, 6)], False)],
    "smaž": [("l", 5, 5, 19, 19), ("l", 19, 5, 5, 19)],
    "uprav text": [("t", 9, 12.5, "A", 13), ("l*", 16, 20, 21, 7), ("l*", 14.5, 20.5, 16, 20)],
    # ---- výběr a měření
    "vše": [("pd", [(3, 4), (21, 4), (21, 20), (3, 20)], True), ("l*", 6, 15, 11, 8), ("c*", 16, 13, 3)],
    "ohrada": [("pd", [(3, 8), (11, 3), (21, 9), (17, 20), (6, 18)], True), ("d*", 12, 12)],
    "podobné": [("c", 6, 7, 3), ("c*", 17, 7, 3), ("c*", 11.5, 17, 3)],
    "vyber": [("f", [(6, 3), (6, 19), (10, 15), (13, 21), (15.5, 20), (12.5, 14), (18, 14)])],
    "skupina": [("pd", [(2, 3), (22, 3), (22, 21), (2, 21)], True), ("c", 8, 9, 3), ("p", [(13, 14), (19, 14),
                                                                                           (19, 18), (13, 18)], True)],
    "vzdálenost": [("l", 4, 18, 20, 6), ("d*", 4, 18), ("d*", 20, 6), ("t", 7, 8, "m", 7)],
    "délka": [("p", [(3, 18), (9, 9), (15, 15), (21, 6)], False), ("t", 15, 21, "Σm", 6)],
    "výměra": [("f*", [(4, 18), (7, 6), (18, 4), (20, 17)]), ("t", 12, 13, "m²", 6)],
    "info": [("c", 12, 12, 9), ("t", 12, 13.5, "i", 11)],
    # ---- geodézie a zobrazení
    "transformace": [("p", [(3, 20), (9, 20), (9, 14), (3, 14)], True), ("ar", 8, 15, 14, 10),
                     ("p*", [(14, 11), (20, 5), (21, 10)], True), ("d", 3, 20), ("d*", 14, 11)],
    "oměrné míry": [("l", 4, 18, 20, 18), ("l", 4, 18, 4, 7), ("t", 12, 15, "12.3", 6), ("t", 8.5, 11, "5", 6)],
    "převod atributů": [("l", 3, 8, 11, 8), ("l*", 13, 16, 21, 16), ("ar", 8, 11, 16, 13)],
    "celý": [("p", [(3, 8), (3, 3), (8, 3)], False), ("p", [(16, 3), (21, 3), (21, 8)], False),
             ("p", [(3, 16), (3, 21), (8, 21)], False), ("p", [(16, 21), (21, 21), (21, 16)], False),
             ("p*", [(8, 8), (16, 8), (16, 16), (8, 16)], True)],
    "přiblížit": [("c", 10, 10, 6.5), ("l", 15, 15, 21, 21), ("l*", 7, 10, 13, 10), ("l*", 10, 7, 10, 13)],
    "předchozí pohled": [("c", 10, 10, 6.5), ("l", 15, 15, 21, 21), ("ar*", 13, 10, 7, 10)],
    "vrstvy": [("f", [(12, 3), (21, 8), (12, 13), (3, 8)]), ("p", [(3, 12), (12, 17), (21, 12)], False),
               ("p*", [(3, 16), (12, 21), (21, 16)], False)],
}


def _cesta_spline(body) -> QPainterPath:
    p = QPainterPath(QPointF(*body[0]))
    for i in range(1, len(body) - 1):
        a, b = body[i], body[i + 1]
        p.quadTo(QPointF(*a), QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    p.lineTo(QPointF(*body[-1]))
    return p


def _sipka(qp: QPainter, x1, y1, x2, y2):
    qp.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    u = math.atan2(y2 - y1, x2 - x1)
    for d in (2.6, -2.6):
        qp.drawLine(QPointF(x2, y2), QPointF(x2 - 4.2 * math.cos(u + d / 5.5), y2 - 4.2 * math.sin(u + d / 5.5)))


def nakresli(qp: QPainter, tvary, barva: QColor, zvyrazneni: QColor, sirka: float = 1.6) -> None:
    for t in tvary:
        druh = t[0]
        zv = druh.endswith("*")
        druh = druh.rstrip("*")
        c = zvyrazneni if zv else barva
        pen = QPen(c, sirka, Qt.DashLine if druh in ("ld", "pd") else Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if druh in ("ld", "pd"):
            pen.setDashPattern([2.0, 1.6])
        qp.setPen(pen)
        qp.setBrush(Qt.NoBrush)
        if druh in ("l", "ld"):
            qp.drawLine(QPointF(t[1], t[2]), QPointF(t[3], t[4]))
        elif druh in ("p", "pd"):
            poly = QPolygonF([QPointF(x, y) for x, y in t[1]])
            (qp.drawPolygon if t[2] else qp.drawPolyline)(poly)
        elif druh == "f":
            qp.setBrush(c)
            qp.drawPolygon(QPolygonF([QPointF(x, y) for x, y in t[1]]))
        elif druh == "c":
            qp.drawEllipse(QPointF(t[1], t[2]), t[3], t[3])
        elif druh == "e":
            qp.drawEllipse(QPointF(t[1], t[2]), t[3], t[4])
        elif druh == "a":
            r = t[3]
            qp.drawArc(QRectF(t[1] - r, t[2] - r, 2 * r, 2 * r), int(t[4] * 16), int(t[5] * 16))
        elif druh == "s":
            qp.drawPath(_cesta_spline(t[1]))
        elif druh == "d":
            qp.setBrush(c)
            qp.drawEllipse(QPointF(t[1], t[2]), 1.5, 1.5)
        elif druh == "x":
            qp.drawLine(QPointF(t[1] - 3, t[2] - 3), QPointF(t[1] + 3, t[2] + 3))
            qp.drawLine(QPointF(t[1] - 3, t[2] + 3), QPointF(t[1] + 3, t[2] - 3))
        elif druh == "ar":
            _sipka(qp, t[1], t[2], t[3], t[4])
        elif druh == "t":
            f = QFont()
            f.setPixelSize(max(4, int(t[4])))
            f.setBold(True)
            qp.setFont(f)
            qp.drawText(QRectF(t[1] - 12, t[2] - t[4], 24, t[4] * 1.4), Qt.AlignHCenter | Qt.AlignVCenter, t[3])


def ikona(prikaz: str, barva: str = "#D1D5DB", zvyrazneni: str = "#60A5FA", velikost: int = 24) -> QIcon:
    """Ikona nástroje (prázdná, když pro příkaz žádná není)."""
    tvary = IKONY.get(prikaz)
    if not tvary:
        return QIcon()
    icon = QIcon()
    for scale in (1, 2):
        pm = QPixmap(velikost * scale, velikost * scale)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.scale(velikost * scale / 24.0, velikost * scale / 24.0)
        nakresli(qp, tvary, QColor(barva), QColor(zvyrazneni))
        qp.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    return icon


def ukazka_cary(styl: str, tloustka_px: float, barva: str = "#D1D5DB", sirka: int = 60, vyska: int = 14) -> QPixmap:
    """Náhled stylu čáry (0–7 jako v MicroStationu) a tloušťky pro rozbalovací seznamy."""
    from ..cad.zadani import MS_STYLY
    pm = QPixmap(sirka, vyska)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(barva), max(1.0, tloustka_px), Qt.SolidLine, Qt.FlatCap)
    vzor = MS_STYLY.get(int(styl), (None, None))[1] if str(styl).isdigit() and int(styl) in MS_STYLY else None
    if vzor:
        delky = [max(0.15, abs(float(v))) for v in vzor[1:]] if isinstance(vzor, (list, tuple)) else []
        if delky:
            m = max(1.0, tloustka_px)
            pen.setDashPattern([max(0.5, d * 6 / m) for d in delky] if len(delky) % 2 == 0
                               else [max(0.5, d * 6 / m) for d in delky + delky])
    qp.setPen(pen)
    qp.drawLine(QPointF(3, vyska / 2), QPointF(sirka - 3, vyska / 2))
    qp.end()
    return pm
