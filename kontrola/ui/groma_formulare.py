"""Stavební prvky výpočetních oken jako v Gromě: barevná pole (žlutá = číslo bodu a kód, zelená = souřadnice,
modrá = měřené směry a délky, fialová = výšky a zenitové úhly), bod s přetažením ze seznamu souřadnic,
tabulka řádků (orientace, identické body) a přepínače.

Body se do oken přetahují myší ze seznamu souřadnic (číslo + Y X Z) a měření ze zápisníku (směr, délka,
zenit, výška cíle) – stejně jako v Gromě."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QRadioButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

MIME_BODY = "application/x-kontrola-body"
MIME_MERENI = "application/x-kontrola-mereni"

BARVY = {"cislo": "zluta", "kod": "zluta", "sour": "zelena", "mer": "modra", "vys": "fialova"}


def tint(druh: str) -> str:
    from .theme import is_dark
    sv = {"zluta": "#FFF6CC", "zelena": "#DDF6D6", "modra": "#E4EEFB", "fialova": "#F0E6FB"}
    tm = {"zluta": "#3A3214", "zelena": "#18351E", "modra": "#16283D", "fialova": "#2C2140"}
    return (tm if is_dark() else sv)[BARVY.get(druh, druh)]


def pole(druh: str, sirka: int | None = None, jen_cteni: bool = False, tip: str = "") -> QLineEdit:
    """Vstupní pole v barvě podle druhu údaje (jako v Gromě)."""
    w = QLineEdit()
    w.setStyleSheet(f"QLineEdit {{ background: {tint(druh)}; }}")
    if sirka:
        w.setMinimumWidth(sirka)
    if druh in ("sour", "mer", "vys"):
        w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if jen_cteni:
        w.setReadOnly(True)
        w.setFocusPolicy(Qt.ClickFocus)
    if tip:
        w.setToolTip(tip)
    w.setAcceptDrops(False)  # přetažení zpracuje rámeček (bod, měření), ne vložení textu do pole
    return w


def nadpis(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("nadpis_uloha")
    return lbl


def body_z_mime(md) -> list[tuple[str, float | None, float | None, float | None]]:
    """Přetažené body: [(číslo, Y, X, Z)] – ze seznamu souřadnic, nebo čísla z textu."""
    if md.hasFormat(MIME_BODY):
        t = bytes(md.data(MIME_BODY)).decode("utf-8")
    elif md.hasText():
        t = md.text()
    else:
        return []
    out = []
    for r in t.splitlines():
        p = r.replace(",", ".").split()
        if not p:
            continue
        cis = []
        for v in p[1:4]:
            try:
                cis.append(float(v))
            except ValueError:
                break
        cis += [None] * (3 - len(cis))
        out.append((p[0], *cis[:3]))
    return out


def mereni_z_mime(md) -> tuple[tuple[str, float] | None, list[dict]]:
    """Přetažené záměry ze zápisníku: ((stanovisko, výška stroje) | None, [{bod, hz, sd, z, vc, d}])."""
    if not md.hasFormat(MIME_MERENI):
        return None, []
    st, out = None, []
    for r in bytes(md.data(MIME_MERENI)).decode("utf-8").splitlines():
        p = r.split()
        if not p:
            continue
        if p[0] == "#st" and len(p) >= 3:
            st = (p[1], float(p[2]))
            continue
        try:
            hz, sd, z, vc = (float(v) for v in p[1:5])
        except ValueError:
            continue
        import math
        out.append({"bod": p[0], "hz": hz, "sd": sd, "z": z, "vc": vc,
                    "d": sd * math.sin(z * math.pi / 200.0)})
    return st, out


def fmt(v: float | None, d: int = 3) -> str:
    return "" if v is None else f"{v:.{d}f}"


class BodBox(QWidget):
    """Číslo bodu (+ Y, X, Z) – po zapsání čísla se souřadnice doplní ze seznamu, nebo se bod přetáhne."""

    zmena = Signal()

    def __init__(self, page, z: bool = True, cislo_druh: str = "cislo", radky: bool = True, dva_sloupce: bool = False,
                 vlevo: list | None = None, parent=None):
        super().__init__(parent)
        self.page = page
        self.setAcceptDrops(True)
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(4)
        self.cislo = pole(cislo_druh, 120, tip="Číslo bodu – souřadnice se doplní ze seznamu. Bod lze také "
                                               "přetáhnout myší ze seznamu souřadnic.")
        self.y = pole("sour", 110)
        self.x = pole("sour", 110)
        self.z = pole("sour", 80) if z else None
        prvky = [("Číslo:", self.cislo), ("Y:", self.y), ("X:", self.x)] + ([("Z:", self.z)] if z else [])

        def dej(t, w, r, c):
            lbl = QLabel(t)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            g.addWidget(lbl, r, c)
            g.addWidget(w, r, c + 1)
        if dva_sloupce:  # Groma: číslo (a výška stroje) vlevo, Y X Z vpravo
            dej(*prvky[0], 0, 0)
            for i, (t, w) in enumerate(vlevo or [], 1):
                dej(t, w, i, 0)
            for i, (t, w) in enumerate(prvky[1:]):
                dej(t, w, i, 2)
            g.setColumnStretch(1, 1)
            g.setColumnStretch(3, 1)
            g.setColumnMinimumWidth(2, 30)
        else:
            for i, (t, w) in enumerate(prvky):
                dej(t, w, *((i, 0) if radky else (0, 2 * i)))
            g.setColumnStretch(1 if radky else 3, 1)
        self._ze_seznamu = False
        self.cislo.editingFinished.connect(self._dopln)
        for w in (self.y, self.x, self.z):
            if w is not None:
                w.textEdited.connect(lambda _t: self.zmena.emit())

    def _dopln(self):
        b = self.page.seznam.najdi(self.cislo.text().strip()) if self.cislo.text().strip() else None
        if b is not None:
            self.nastav(b.cislo, b.y, b.x, b.z)
            self._ze_seznamu = True
        elif self._ze_seznamu:  # číslo přepsané na bod, který v seznamu není – staré souřadnice pryč
            self.nastav(self.cislo.text().strip())
        self.zmena.emit()

    def nastav(self, cislo: str, y=None, x=None, z=None):
        self._ze_seznamu = False
        self.cislo.setText(cislo)
        self.y.setText(fmt(y))
        self.x.setText(fmt(x))
        if self.z is not None:
            self.z.setText(fmt(z))

    def vymaz(self):
        self.nastav("")

    def souradnice(self) -> tuple[float, float, float | None] | None:
        try:
            y, x = float(self.y.text().replace(",", ".")), float(self.x.text().replace(",", "."))
        except ValueError:
            return None
        z = None
        if self.z is not None and self.z.text().strip():
            try:
                z = float(self.z.text().replace(",", "."))
            except ValueError:
                z = None
        return y, x, z

    def rucni_bod(self):
        """Bod s ručně zapsanými souřadnicemi, který v seznamu není (pro výpočet bez uložení do seznamu)."""
        from ..geodezie.body import Bod
        c = self.cislo.text().strip()
        s = self.souradnice()
        if not c or s is None or self.page.seznam.najdi(c) is not None:
            return None
        return Bod(c, s[0], s[1], s[2])

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasFormat(MIME_BODY):
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):  # noqa: N802
        b = body_z_mime(e.mimeData())
        if b:
            self.nastav(*b[0])
            self.zmena.emit()
            e.acceptProposedAction()


class TabulkaRadku(QTableWidget):
    """Tabulka řádků zadání (orientace, měření, identické body). Prvních ``vstup`` sloupců je zadání,
    zbylé sloupce jsou výsledky (opravy) – vyplní je výpočet. Hodnota pro výpočet = řádky textu."""

    def __init__(self, sloupce: list[str], vstup: int, parent=None):
        super().__init__(0, len(sloupce), parent)
        self.vstup = vstup
        self.setHorizontalHeaderLabels(sloupce)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.ElideLeft)  # dlouhá čísla bodů: vidět je konec (číslo bodu bez předčíslí)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setMinimumSectionSize(60)
        self.setMinimumHeight(110)
        self.pri_pretazeni = None  # callback(mime) → True, když přetažení zpracoval

    def pridej(self, hodnoty: list) -> int:
        r = self.rowCount()
        self.insertRow(r)
        for c in range(self.columnCount()):
            v = hodnoty[c] if c < len(hodnoty) else ""
            it = QTableWidgetItem("" if v is None else str(v))
            if c >= self.vstup:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c > 0:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(r, c, it)
        return r

    def odeber(self):
        for r in sorted({i.row() for i in self.selectedIndexes()}, reverse=True):
            self.removeRow(r)

    def radky(self) -> list[list[str]]:
        out = []
        for r in range(self.rowCount()):
            v = [(self.item(r, c).text().strip() if self.item(r, c) else "") for c in range(self.vstup)]
            if v[0]:
                out.append(v)
        return out

    def hodnota(self) -> str:
        return "\n".join(" ".join(x or "-" for x in r).rstrip(" -") for r in self.radky())

    def nastav_hodnotu(self, text: str):
        self.setRowCount(0)
        for r in str(text).splitlines():
            p = r.split()
            if p:
                self.pridej(p)

    def nastav_vysledky(self, data: dict[str, list]):
        """Opravy do výsledkových sloupců podle čísla bodu v prvním sloupci."""
        for r in range(self.rowCount()):
            k = self.item(r, 0).text().strip() if self.item(r, 0) else ""
            v = data.get(k)
            for i, c in enumerate(range(self.vstup, self.columnCount())):
                t = ""
                if v is not None and i < len(v) and v[i] is not None:
                    t = v[i] if isinstance(v[i], str) else f"{v[i]:.4f}" if abs(v[i]) < 1 else f"{v[i]:.3f}"
                it = self.item(r, c)
                if it is not None:
                    it.setText(t)

    def dragEnterEvent(self, e):  # noqa: N802
        md = e.mimeData()
        if md.hasFormat(MIME_BODY) or md.hasFormat(MIME_MERENI):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):  # noqa: N802
        self.dragEnterEvent(e)

    def dropEvent(self, e):  # noqa: N802
        if self.pri_pretazeni is not None and self.pri_pretazeni(e.mimeData()):
            e.acceptProposedAction()


class Volba(QWidget):
    """Přepínače (Typ transformace…): hodnota() = text zvolené položky."""

    def __init__(self, polozky: list[str], vychozi: str = "", parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.sk = QButtonGroup(self)
        for p in polozky:
            rb = QRadioButton(p)
            self.sk.addButton(rb)
            v.addWidget(rb)
            if p.lower() == (vychozi or polozky[0]).lower():
                rb.setChecked(True)

    def hodnota(self) -> str:
        b = self.sk.checkedButton()
        return b.text().lower() if b else ""

    def nastav_hodnotu(self, t: str):
        for b in self.sk.buttons():
            if b.text().lower() == str(t).lower():
                b.setChecked(True)


class Prepinac(QCheckBox):
    """Zaškrtávací volba úlohy: hodnota() = „ano“ / „ne“."""

    def hodnota(self) -> str:
        return "ano" if self.isChecked() else "ne"

    def nastav_hodnotu(self, t: str):
        self.setChecked(str(t).startswith("ano") or str(t) in ("1", "True", "true"))


def radek_poli(*dvojice, roztahnout: bool = True) -> QWidget:
    """Řádek „Popisek: pole  Popisek: pole“."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    for t, p in dvojice:
        if t:
            h.addWidget(QLabel(t))
        h.addWidget(p, 1 if roztahnout else 0)
    return w


def formular(radky: list[tuple[str, QWidget]], sirka_popisku: int = 0, nahoru: bool = True) -> QWidget:
    """Dvousloupcový formulář (popisek vpravo zarovnaný, pole) s rozumnými mezerami – nic se nepřekrývá."""
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(8)
    g.setVerticalSpacing(5)
    for i, (t, p) in enumerate(radky):
        lbl = QLabel(t)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if sirka_popisku:
            lbl.setMinimumWidth(sirka_popisku)
        g.addWidget(lbl, i, 0)
        g.addWidget(p, i, 1)
    g.setColumnStretch(1, 1)
    if nahoru:
        g.setRowStretch(len(radky), 1)
    return w
