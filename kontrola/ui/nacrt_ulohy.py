"""Náčrt ve výpočetním okně (jako kontrolní kresba Gromy): body úlohy s čísly, spojnice podle druhu úlohy.

Dané body (ze seznamu souřadnic) = modré trojúhelníky, vypočtené body = červená kolečka. Sever nahoře, východ
vpravo (S-JTSK: obrazovka x = −Y, y = X). Náčrt se překreslí po každé změně zadání a po výpočtu, takže je vidět,
jestli zadané body a výsledek odpovídají skutečnosti."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

DANY = QColor("#2563EB")
NOVY = QColor("#DC2626")
CARA = QColor("#64748B")


def kratke(cislo: str) -> str:
    """Číslo bez předčíslí (jako popis v kresbě Gromy)."""
    c = cislo.strip()
    if len(c) > 8 and c.isdigit():
        return c[-4:].lstrip("0") or "0"
    return c


class Nacrt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 160)
        self.setObjectName("nacrt_ulohy")
        self.body: list[tuple[str, float, float, bool]] = []  # číslo, y, x, nový
        self.cary: list[tuple[int, int, bool]] = []  # indexy do body, čárkovaně
        self.druh = "body"

    def nastav(self, body, cary, druh="body"):
        self.body, self.cary, self.druh = list(body), list(cary), druh
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.base())
        txt = pal.text().color()
        p.setPen(QPen(pal.mid().color(), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        p.setFont(f)
        if not self.body:
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect().adjusted(10, 10, -10, -10), Qt.AlignCenter | Qt.TextWordWrap,
                       "Náčrt\n\nZadejte body – tady uvidíte, jak leží\n(modře dané, červeně vypočtené).")
            return
        ys = [b[1] for b in self.body]
        xs = [b[2] for b in self.body]
        w, h = self.width() - 90, self.height() - 70  # okraj na popisy, severku a měřítko
        sy, sx = max(ys) - min(ys), max(xs) - min(xs)
        m = min(w / sy if sy > 1e-9 else 1e9, h / sx if sx > 1e-9 else 1e9)
        if m >= 1e9:
            m = 1.0
        cy, cx = (max(ys) + min(ys)) / 2, (max(xs) + min(xs)) / 2

        def bod(y, x) -> QPointF:
            return QPointF(self.width() / 2 - 12 - (y - cy) * m, self.height() / 2 + 4 + (x - cx) * m)
        # spojnice
        for i, j, carkovane in self.cary:
            if i >= len(self.body) or j >= len(self.body):
                continue
            a, b = self.body[i], self.body[j]
            nova = a[3] or b[3]
            pen = QPen(NOVY if nova else CARA, 1.4)
            if carkovane:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(bod(a[1], a[2]), bod(b[1], b[2]))
        # body a čísla
        for c, y, x, novy in self.body:
            q = bod(y, x)
            if novy:
                p.setPen(QPen(NOVY, 1.6))
                p.setBrush(QColor(NOVY.red(), NOVY.green(), NOVY.blue(), 60))
                p.drawEllipse(q, 4.5, 4.5)
            else:
                p.setPen(QPen(DANY, 1.4))
                p.setBrush(QColor(DANY.red(), DANY.green(), DANY.blue(), 60))
                p.drawPolygon(QPolygonF([q + QPointF(0, -6), q + QPointF(5.2, 3.5), q + QPointF(-5.2, 3.5)]))
            p.setPen(NOVY if novy else txt)
            p.drawText(q + QPointF(7, -5), kratke(c))
        # severka a měřítko
        p.setPen(QPen(txt, 1))
        p.setBrush(txt)
        s0 = QPointF(self.width() - 16, 26)
        path = QPainterPath(s0 + QPointF(0, -14))
        path.lineTo(s0 + QPointF(5, 2))
        path.lineTo(s0 + QPointF(-5, 2))
        path.closeSubpath()
        p.drawPath(path)
        p.drawText(QRectF(s0.x() - 8, s0.y() + 2, 16, 14), Qt.AlignCenter, "S")
        p.setBrush(Qt.NoBrush)
        if m > 0:
            delka = 10 ** math.floor(math.log10(max(1e-6, 60 / m)))
            for k in (5, 2, 1):
                if k * delka * m <= 90:
                    delka *= k
                    break
            px = delka * m
            y0 = self.height() - 12
            p.drawLine(QPointF(10, y0), QPointF(10 + px, y0))
            p.drawLine(QPointF(10, y0 - 3), QPointF(10, y0 + 3))
            p.drawLine(QPointF(10 + px, y0 - 3), QPointF(10 + px, y0 + 3))
            p.drawText(QPointF(14 + px, y0 + 4), f"{delka:g} m")


def sestav(cisla: list[str], najdi, nove: list, druh: str):
    """Body a spojnice náčrtu: ``cisla`` = čísla bodů v pořadí zadání, ``najdi`` = číslo → bod ze seznamu,
    ``nove`` = vypočtené body. Vrátí (body, čáry)."""
    nove_d = {b.cislo: b for b in nove}
    body, index = [], {}
    poradi = []
    for c in cisla:
        c = c.strip()
        if not c:
            continue
        b = nove_d.get(c) or najdi(c)
        if b is None:
            continue
        if c not in index:
            index[c] = len(body)
            body.append((c, b.y, b.x, c in nove_d))
        poradi.append(index[c])
    for b in nove:
        if b.cislo not in index:
            index[b.cislo] = len(body)
            body.append((b.cislo, b.y, b.x, True))
            poradi.append(index[b.cislo])
    dane = [i for i in dict.fromkeys(poradi) if not body[i][3]]
    novi = [i for i in dict.fromkeys(poradi) if body[i][3]]
    cary = []
    if druh == "polar" and dane:
        st = dane[0]
        cary += [(st, i, True) for i in dane[1:]] + [(st, i, False) for i in novi]
    elif druh == "volne" and novi:
        st = novi[0]
        cary += [(st, i, True) for i in dane] + [(st, i, False) for i in novi[1:]]
    elif druh == "protinani":
        cary += [(d, n, False) for d in dane for n in novi]
    elif druh in ("lomena", "uzavrena"):
        seq = [i for k, i in enumerate(poradi) if k == 0 or poradi[k - 1] != i]
        cary += [(a, b, False) for a, b in zip(seq, seq[1:])]
        if druh == "uzavrena" and len(seq) > 2 and seq[0] != seq[-1]:
            cary.append((seq[-1], seq[0], False))
    elif druh == "primky":
        for a, b in zip(dane[0::2], dane[1::2]):
            cary.append((a, b, False))
        if novi and dane:
            cary += [(dane[0], n, True) for n in novi if len(dane) % 2]
    return body, cary
