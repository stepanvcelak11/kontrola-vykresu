"""Zalamovací rozvržení: prvky vedle sebe, a když se nevejdou, pokračují na dalším řádku."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLayout, QSizePolicy, QSpacerItem, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 4):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        x, y, line_h = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self._items:
            w = it.widget()
            if w is not None and not w.isVisibleTo(w.parentWidget()) and w.parentWidget() is not None:
                continue
            hint = it.sizeHint()
            nx = x + hint.width() + sp
            if nx - sp > rect.right() + 1 and line_h > 0:
                x = rect.x()
                y += line_h + sp
                nx = x + hint.width() + sp
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


# Řádek tlačítek místo QHBoxLayout (stejné addWidget / addSpacing / addStretch): v úzkém okně (malý
# notebook, zvětšení 125–150 %) se zalomí, takže okno nemusí být širší než obrazovka.
class RadekTlacitek(QLayout):
    def __init__(self, parent=None, mezera: int = 4):
        super().__init__(parent)
        self._items = []
        self._mezera = mezera
        self._roztahnout: set[int] = set()  # id položek se stretch > 0 (dostanou zbytek řádku)

    # --- stejné rozhraní jako QHBoxLayout (to, co se v aplikaci používá)
    def addWidget(self, w, stretch: int = 0, alignment=Qt.Alignment()):  # noqa: N802
        super().addWidget(w)
        if stretch:
            self._roztahnout.add(id(self._items[-1]))

    def addSpacing(self, n: int):  # noqa: N802
        self.addItem(QSpacerItem(n, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

    def addStretch(self, n: int = 0):  # noqa: N802
        pass  # zbytek řádku zůstane prázdný sám

    def setSpacing(self, n: int):  # noqa: N802
        self._mezera = n

    def spacing(self) -> int:
        return self._mezera

    # --- QLayout
    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        if 0 <= i < len(self._items):
            it = self._items.pop(i)
            self._roztahnout.discard(id(it))
            return it
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        return self._rozvrhni(QRect(0, 0, w, 0), jen_spocitat=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._rozvrhni(rect, jen_spocitat=False)

    def sizeHint(self):  # noqa: N802
        w = sum(self._sirka(it) for it in self._items) + self._mezera * max(0, len(self._items) - 1)
        h = max((it.sizeHint().height() for it in self._viditelne()), default=0)
        m = self.contentsMargins()
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):  # noqa: N802
        s = QSize()
        for it in self._viditelne():
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    # ---
    def _viditelne(self):
        return [it for it in self._items if not (it.widget() is not None and it.widget().isHidden())]

    @staticmethod
    def _sirka(it) -> int:
        return max(it.sizeHint().width(), it.minimumSize().width())

    def _rozvrhni(self, rect: QRect, jen_spocitat: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        radky: list[list] = [[]]
        x = 0
        for it in self._viditelne():
            sw = self._sirka(it)
            if radky[-1] and x + sw > r.width():
                radky.append([])
                x = 0
            radky[-1].append(it)
            x += sw + self._mezera
        y = r.y()
        for radek in radky:
            if not radek:
                continue
            vyska = max(it.sizeHint().height() for it in radek)
            if not jen_spocitat:
                zbytek = r.width() - sum(self._sirka(it) for it in radek) - self._mezera * (len(radek) - 1)
                roz = [it for it in radek if id(it) in self._roztahnout]
                navic = max(0, zbytek) // len(roz) if roz else 0
                x = r.x()
                for it in radek:
                    sw = self._sirka(it) + (navic if it in roz else 0)
                    h = it.sizeHint().height()
                    it.setGeometry(QRect(QPoint(x, y + (vyska - h) // 2), QSize(sw, h)))
                    x += sw + self._mezera
            y += vyska + self._mezera
        return y - self._mezera - r.y() + m.top() + m.bottom()


def skupina(*widgety, mezera: int = 4) -> QWidget:
    """Popisek a jeho pole drží pohromadě (při zalomení řádku se neroztrhnou)."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(mezera)
    for i, x in enumerate(widgety):
        lay.addWidget(x, 1 if i == len(widgety) - 1 else 0)  # navíc dostane pole, ne popisek
    return w
