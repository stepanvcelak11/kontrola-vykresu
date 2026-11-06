"""Rozvržení Výpočtů jako v Gromě 14: roletové menu, lišta nastavení, datová okna a stavový řádek.

Podle příručky Groma v. 14.0, kap. 4 Ovládání programu: nahoře menu (Soubor, Editace, Souřadnice,
Měření, Výpočty, Okno), pod ním lišta nastavení (kód kvality, měřítko, najít bod), pod ní pracovní
plocha s datovými okny (seznam souřadnic, seznam měření, grafika, protokol) a dole stavový řádek
(aktivní seznam, počet položek, počet označených).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMdiArea,
                               QMdiSubWindow, QMenu, QPlainTextEdit, QWidget)

class _Zahlavi(QWidget):
    """Vlastní záhlaví datového okna: název, maximalizace a zavření; tažením se okno přesouvá,
    dvojklikem maximalizuje (stejně jako v Gromě, ale ve vzhledu aplikace)."""

    def __init__(self, sub: "_DatoveOkno"):
        super().__init__()
        from PySide6.QtWidgets import QToolButton
        self.sub = sub
        self._start = None
        self.setObjectName("okno_zahlavi")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 4, 3)
        lay.setSpacing(2)
        self.titul = QLabel()
        self.titul.setObjectName("okno_titul")
        lay.addWidget(self.titul, 1)
        self.b_max = QToolButton()
        self.b_max.setObjectName("okno_tlacitko")
        self.b_max.setText("□")
        self.b_max.setToolTip("Maximalizovat / obnovit (dvojklik na záhlaví)")
        self.b_max.clicked.connect(self.prepni_max)
        self.b_zav = QToolButton()
        self.b_zav.setObjectName("okno_zavrit")
        self.b_zav.setText("✕")
        self.b_zav.setToolTip("Skrýt okno (znovu ho otevřete z karty Soubor → Pohledy → Okna)")
        self.b_zav.clicked.connect(sub.hide)
        lay.addWidget(self.b_max)
        lay.addWidget(self.b_zav)

    def prepni_max(self):
        if self.sub.isMaximized():
            self.sub.showNormal()
        else:
            self.sub.showMaximized()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._start = (e.globalPosition().toPoint(), self.sub.pos())
            area = self.sub.mdiArea()
            if area is not None:
                area.setActiveSubWindow(self.sub)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._start is not None and not self.sub.isMaximized():
            g0, p0 = self._start
            self.sub.move(p0 + e.globalPosition().toPoint() - g0)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._start = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        self.prepni_max()


class _DatoveOkno(QMdiSubWindow):
    """Datové okno: křížek okno jen schová (obsah i stav zůstanou), znovu se otevře z menu Okno.
    Bez systémového rámu – vlastní záhlaví a úchyt pro změnu velikosti ve vzhledu aplikace."""

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QSizeGrip, QVBoxLayout
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setObjectName("datove_okno")
        self.obal = QWidget()
        self.obal.setObjectName("datove_okno_obal")
        self.obal.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(self.obal)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)
        self.zahlavi = _Zahlavi(self)
        v.addWidget(self.zahlavi)
        self._v = v
        self.grip = QSizeGrip(self.obal)
        self.grip.setFixedSize(14, 14)
        super().setWidget(self.obal)

    def nastav_obsah(self, w: QWidget) -> None:
        self._v.addWidget(w, 1)
        self.grip.raise_()

    def setWindowTitle(self, t: str) -> None:  # noqa: N802
        super().setWindowTitle(t)
        self.zahlavi.titul.setText(t)

    def moveEvent(self, e):  # noqa: N802
        super().moveEvent(e)
        self._zmena()

    def _zmena(self):
        a = self.mdiArea()
        if a is not None and hasattr(a, "uloz_rozvrzeni_pozdeji"):
            a.uloz_rozvrzeni_pozdeji()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._zmena()
        self.grip.move(self.obal.width() - self.grip.width(), self.obal.height() - self.grip.height())
        self.grip.raise_()

    def nastav_aktivni(self, on: bool) -> None:
        for w in (self.obal, self.zahlavi, self.zahlavi.titul):
            w.setProperty("aktivni", on)
            w.style().unpolish(w)
            w.style().polish(w)

    def closeEvent(self, e):  # noqa: N802
        e.ignore()
        self.hide()


class DatovaOkna(QMdiArea):
    """Pracovní plocha s datovými okny. Má stejné rozhraní jako dřívější záložky (addTab, setCurrentWidget…),
    takže ostatní části aplikace (Kokeš, QTrig, přehled funkcí) fungují beze změny."""

    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._okna: list[tuple[QWidget, _DatoveOkno, str]] = []
        self._rozvrzeno = False
        self.vychozi: tuple = ()  # (hlavní okno, okno pod ním, okno vpravo) pro výchozí rozvržení
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.subWindowActivated.connect(self._aktivovano)

    # --- rozhraní jako QTabWidget
    def addTab(self, w: QWidget, titul: str, viditelne: bool = True) -> int:  # noqa: N802
        sub = _DatoveOkno()
        sub.nastav_obsah(w)
        sub.setWindowTitle(titul)
        sub.setAttribute(Qt.WA_DeleteOnClose, False)
        self.addSubWindow(sub)
        sub.resize(560, 360)
        self._okna.append((w, sub, titul))
        sub.setVisible(viditelne)
        return len(self._okna) - 1

    def setDocumentMode(self, on: bool) -> None:  # noqa: N802
        QMdiArea.setDocumentMode(self, on)

    def count(self) -> int:
        return len(self._okna)

    def widget(self, i: int) -> QWidget | None:
        return self._okna[i][0] if 0 <= i < len(self._okna) else None

    def tabText(self, i: int) -> str:  # noqa: N802
        return self._okna[i][2] if 0 <= i < len(self._okna) else ""

    def indexOf(self, w: QWidget) -> int:  # noqa: N802
        return next((i for i, (x, _s, _t) in enumerate(self._okna) if x is w), -1)

    def currentIndex(self) -> int:  # noqa: N802
        sub = self.activeSubWindow()
        return next((i for i, (_x, s, _t) in enumerate(self._okna) if s is sub), -1)

    def currentWidget(self) -> QWidget | None:  # noqa: N802
        return self.widget(self.currentIndex())

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        if 0 <= i < len(self._okna):
            self.otevri(self._okna[i][0])

    def setCurrentWidget(self, w: QWidget) -> None:  # noqa: N802
        self.otevri(w)

    # --- práce s okny (menu Okno)
    def okno(self, w: QWidget) -> _DatoveOkno | None:
        return next((s for x, s, _t in self._okna if x is w), None)

    def otevri(self, w: QWidget) -> None:
        sub = self.okno(w)
        if sub is None:
            return
        if sub.isHidden():
            sub.show()
        if sub.isMinimized():
            sub.showNormal()
        self.setActiveSubWindow(sub)
        sub.raise_()
        i = self.indexOf(w)
        self.currentChanged.emit(i)

    def mozaika_vodorovne(self) -> None:
        """Okna pod sebou přes celou šířku (Okno → Mozaika horizontálně)."""
        okna = [s for _x, s, _t in self._okna if not s.isHidden() and not s.isMinimized()]
        if not okna:
            return
        r = self.viewport().rect()
        h = max(80, r.height() // len(okna))
        for i, s in enumerate(okna):
            s.showNormal()
            s.setGeometry(0, i * h, r.width(), h)

    def mozaika_svisle(self) -> None:
        """Okna vedle sebe (Okno → Mozaika vertikálně)."""
        okna = [s for _x, s, _t in self._okna if not s.isHidden() and not s.isMinimized()]
        if not okna:
            return
        r = self.viewport().rect()
        w = max(120, r.width() // len(okna))
        for i, s in enumerate(okna):
            s.showNormal()
            s.setGeometry(i * w, 0, w, r.height())

    def srovnej_ikony(self) -> None:
        r = self.viewport().rect()
        x = 0
        for _w, s, _t in self._okna:
            if not s.isHidden() and s.isMinimized():
                s.move(x, r.height() - s.height())
                x += s.width()

    def zavri_aktivni(self) -> None:
        sub = self.activeSubWindow()
        if sub is not None:
            sub.hide()

    def _aktivovano(self, sub) -> None:
        for _x, s, _t in self._okna:
            s.nastav_aktivni(s is sub)
        i = next((i for i, (_x, s, _t) in enumerate(self._okna) if s is sub), -1)
        if i >= 0:
            self.currentChanged.emit(i)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if not self._rozvrzeno:  # první zobrazení: uložené rozvržení uživatele, jinak výchozí
            self._rozvrzeno = True
            if self._rezim_ulozeny() == "zalozky":
                self.nastav_rezim("zalozky")
            elif not self.obnov_rozvrzeni():
                self.vychozi_rozvrzeni()
            self._nacteno = True

    # --- rozvržení podle uživatele: zapamatuje se poloha a velikost oken (a režim okna / záložky)
    KLIC = "vypocty/rozvrzeni"

    def _qs(self):
        from PySide6.QtCore import QSettings
        return QSettings("KontrolaVykresu", "KontrolaVykresu")

    def _rezim_ulozeny(self) -> str:
        return str(self._qs().value(self.KLIC + "/rezim", "okna"))

    def uloz_rozvrzeni_pozdeji(self) -> None:
        if not getattr(self, "_nacteno", False) or self.viewMode() == QMdiArea.TabbedView:
            return
        from PySide6.QtCore import QTimer
        if not hasattr(self, "_t_uloz"):
            self._t_uloz = QTimer(self)
            self._t_uloz.setSingleShot(True)
            self._t_uloz.setInterval(500)
            self._t_uloz.timeout.connect(self.uloz_rozvrzeni)
        self._t_uloz.start()

    def uloz_rozvrzeni(self) -> None:
        r = self.viewport().rect()
        if r.width() < 50 or r.height() < 50:
            return
        d = {}
        for _w, sub, t in self._okna:
            g = sub.geometry()
            # poměrně k ploše – rozvržení sedí i po změně velikosti okna aplikace
            d[t] = [g.x() / r.width(), g.y() / r.height(), g.width() / r.width(), g.height() / r.height(),
                    not sub.isHidden(), sub.isMaximized()]
        import json
        self._qs().setValue(self.KLIC + "/okna", json.dumps(d))

    def obnov_rozvrzeni(self) -> bool:
        import json
        try:
            d = json.loads(self._qs().value(self.KLIC + "/okna", "") or "{}")
        except (TypeError, ValueError):
            return False
        if not d:
            return False
        r = self.viewport().rect()
        for _w, sub, t in self._okna:
            v = d.get(t)
            if not v:
                continue
            x, y, w, h, vid, mx = v
            sub.setVisible(bool(vid))
            sub.setGeometry(int(x * r.width()), int(y * r.height()), max(160, int(w * r.width())),
                            max(100, int(h * r.height())))
            if mx:
                sub.showMaximized()
        return True

    def nastav_rezim(self, rezim: str) -> None:
        """„okna“ = volná okna (jako Groma), „zalozky“ = každé okno na celou plochu, přepínání záložkami."""
        tab = rezim == "zalozky"
        if tab:
            self.uloz_rozvrzeni()
            self.setViewMode(QMdiArea.TabbedView)
            self.setDocumentMode(True)
            self.setTabsMovable(True)
            from PySide6.QtWidgets import QTabBar
            tb = self.findChild(QTabBar)
            if tb is not None:
                tb.setExpanding(False)
        else:
            self.setViewMode(QMdiArea.SubWindowView)
            if not self.obnov_rozvrzeni():
                self.vychozi_rozvrzeni()
        for _w, sub, _t in self._okna:
            sub.zahlavi.setVisible(not tab)
        self._qs().setValue(self.KLIC + "/rezim", "zalozky" if tab else "okna")

    def prepni_rezim(self) -> None:
        self.nastav_rezim("okna" if self.viewMode() == QMdiArea.TabbedView else "zalozky")

    def vychozi_rozvrzeni(self) -> None:
        """Přehledné rozvržení: seznam souřadnic velký vlevo nahoře, zápisník pod ním, protokol vpravo."""
        if len(self.vychozi) != 3:
            self.mozaika_vodorovne()
            return
        hlavni, dole, vpravo = (self.okno(w) for w in self.vychozi)
        for s in (hlavni, dole, vpravo):
            if s is not None:
                s.show()
                s.showNormal()
        if self.viewMode() == QMdiArea.TabbedView:
            self.nastav_rezim("okna")
        r = self.viewport().rect()
        g = 4
        sl = int(r.width() * 0.64)
        rh = int(r.height() * 0.58)
        rh = min(rh, r.height() - min(300, int(r.height() * 0.55)))  # zápisník potřebuje ~300 px (malý displej)
        if hlavni is not None:
            hlavni.setGeometry(g, g, sl - 2 * g, rh - g)
        if dole is not None:
            dole.setGeometry(g, rh + g, sl - 2 * g, r.height() - rh - 2 * g)
        if vpravo is not None:
            vpravo.setGeometry(sl, g, r.width() - sl - g, r.height() - 2 * g)
        if hlavni is not None:
            self.setActiveSubWindow(hlavni)


class OknoProtokolu(QPlainTextEdit):
    """Okno s protokolem o výpočtech (vypocty/protokol.txt) – každý výpočet se do něj připíše."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setObjectName("vypis")
        self.setPlaceholderText("Protokol o výpočtech – sem se zapisuje každý výpočet z menu Výpočty.")
        self._soubor: Path | None = None

    def nacti(self, soubor: Path | None) -> None:
        self._soubor = soubor
        try:
            text = soubor.read_text(encoding="utf-8") if soubor and soubor.exists() else ""
        except OSError:
            text = ""
        self.setPlainText(text)
        self.moveCursor(self.textCursor().MoveOperation.End)


class ListaNastaveni(QWidget):
    """Lišta nastavení pod menu (jako v Gromě): kód kvality, měřítkový koeficient, najít bod."""

    hledej = Signal(str)
    uloha = Signal(str)  # přepnout / založit úlohu
    vypocet_meritka = Signal()  # tlačítko u měřítka: Zkreslení v Křovákově zobrazení
    nastaveni = Signal()  # ozubené kolo: Nastavení parametrů (jako v Gromě)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lista_nastaveni")
        self.setAttribute(Qt.WA_StyledBackground, True)
        from .flow import RadekTlacitek
        lay = RadekTlacitek(self)  # v úzkém okně (notebook 150 %) se lišta zalomí do dvou řádků
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(6)
        from PySide6.QtWidgets import QToolButton
        self.b_nastaveni = QToolButton()
        self.b_nastaveni.setText("⚙ Nastavení")
        self.b_nastaveni.setObjectName("lista_tlacitko")
        self.b_nastaveni.setToolTip("Nastavení parametrů výpočtů: zpracování zápisníku, tolerance (mezní odchylky), "
                                    "přístroj, redukce délek, desetinná místa …")
        self.b_nastaveni.clicked.connect(self.nastaveni)
        lay.addWidget(self.b_nastaveni)
        lay.addSpacing(6)
        self.ulohy = QComboBox()
        self.ulohy.setToolTip("Rozpracovaná úloha – každá má svůj seznam souřadnic, zápisník a protokol "
                              "(jako soubory v Gromě). Poslední položka založí novou.")
        self.ulohy.setMinimumWidth(110)
        self.ulohy.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.ulohy.setMinimumContentsLength(9)
        self.ulohy.activated.connect(self._vyber_ulohy)
        lay.addWidget(QLabel("Úloha:"))
        lay.addWidget(self.ulohy)
        self.nastav_ulohy([""], "")
        from PySide6.QtCore import QSettings
        self.predcisli = QComboBox()
        self.predcisli.setEditable(True)
        self.predcisli.setMinimumWidth(90)
        self.predcisli.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.predcisli.setMinimumContentsLength(6)  # dlouhá hodnota nesmí roztáhnout lištu
        self.predcisli.setToolTip("Předčíslí (k.ú. + ZPMZ) – doplní se k číslům bodů zadaným bez předčíslí a "
                                  "předvyplní se u nových bodů ve výpočetních oknech (jako v Gromě)")
        self.predcisli.addItem(str(QSettings().value("vypocty/predcisli", "") or ""))
        self.predcisli.currentTextChanged.connect(
            lambda t: QSettings().setValue("vypocty/predcisli", t.strip()))
        lay.addSpacing(6)
        lay.addWidget(QLabel("Předčíslí:"))
        lay.addWidget(self.predcisli)
        self.kod_kvality = QComboBox()
        for k in range(1, 9):
            self.kod_kvality.addItem(str(k), k)
        self.kod_kvality.setToolTip("Kód kvality – podle něj se počítají mezní odchylky (bez platného kódu Groma "
                                    "předpokládá 3)")
        class _Meritko(QDoubleSpinBox):  # přesnost 12 míst, ale bez zbytečných nul (1.000000, 0.99990537)
            def textFromValue(self, v):  # noqa: N802
                t = f"{v:.12f}".rstrip("0")
                cela, _, des = t.partition(".")
                return f"{cela}.{des.ljust(6, '0')}"
        self.meritko = _Meritko()
        self.meritko.setDecimals(12)
        self.meritko.setRange(0.99, 1.01)
        self.meritko.setSingleStep(0.00001)
        self.meritko.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.meritko.setMinimumWidth(118)
        self.meritko.setToolTip("Měřítkový koeficient – násobí měřené délky (zkreslení Křovákova zobrazení "
                                "a nadmořská výška). 1,000000 = bez korekce.")
        self.najit = QLineEdit()
        self.najit.setPlaceholderText("🔍 najít bod")
        self.najit.setMaximumWidth(105)
        self.najit.setClearButtonEnabled(True)
        self.najit.setToolTip("Najít bod v seznamu souřadnic podle čísla (vyhledává průběžně při psaní)")
        self.b_meritko = QToolButton()
        self.b_meritko.setText("Z bodů…")
        self.b_meritko.setObjectName("lista_tlacitko")
        self.b_meritko.setToolTip("Výpočet měřítka ze souřadnic: zkreslení v Křovákově zobrazení a oprava "
                                  "z nadmořské výšky (jako v Gromě)")
        self.b_meritko.clicked.connect(self.vypocet_meritka)
        for t, w in (("Kvalita:", self.kod_kvality), ("Měřítko:", self.meritko), ("", self.najit)):
            lay.addSpacing(6)
            if t:
                lay.addWidget(QLabel(t))
            lay.addWidget(w)
            if w is self.meritko:
                lay.addWidget(self.b_meritko)
        lay.addStretch(1)
        self.nacti()
        self.kod_kvality.currentIndexChanged.connect(self._uloz)
        self.meritko.valueChanged.connect(self._uloz)
        self.najit.textChanged.connect(self.hledej)

    NOVA = "+ Nová úloha…"

    def nastav_ulohy(self, nazvy: list[str], aktivni: str) -> None:
        self.ulohy.blockSignals(True)
        self.ulohy.clear()
        for n in nazvy:
            self.ulohy.addItem(n or "Hlavní seznam projektu", n)
        self.ulohy.addItem(self.NOVA, None)
        self.ulohy.setCurrentIndex(max(0, self.ulohy.findData(aktivni)))
        self.ulohy.blockSignals(False)

    def _vyber_ulohy(self, i: int) -> None:
        n = self.ulohy.itemData(i)
        if n is None:  # nová úloha
            from PySide6.QtWidgets import QInputDialog
            t, ok = QInputDialog.getText(self, "Nová úloha", "Název úlohy (např. 02 Polygon):")
            if not ok or not t.strip():
                self.ulohy.setCurrentIndex(0)
                return
            n = t.strip()
        self.uloha.emit(n)

    def nacti(self) -> None:
        from ..geodezie import nastaveni as N
        n = N.aktualni()
        for w in (self.kod_kvality, self.meritko):
            w.blockSignals(True)
        self.kod_kvality.setCurrentIndex(max(0, self.kod_kvality.findData(n.kod_kvality)))
        self.meritko.setValue(n.koeficient() or 1.0)
        for w in (self.kod_kvality, self.meritko):
            w.blockSignals(False)

    def _uloz(self, *_a) -> None:
        from ..geodezie import nastaveni as N
        from .nastaveni_vypoctu import uloz
        n = N.aktualni()
        n.kod_kvality = int(self.kod_kvality.currentData() or 3)
        m = round(self.meritko.value(), 12)
        if abs(m - 1.0) < 1e-9:
            if n.meritko_rezim == "ručně":
                n.meritko_rezim = "bez korekce"
        else:
            n.meritko_rezim, n.meritko_rucne = "ručně", m
        uloz(n)


# Pás karet jako v Gromě 14 (screenshoty G01–G06): karta → skupiny → tlačítka.
# Tlačítko: (text, cíl) – cíl je název úlohy z ULOHY, seznam názvů (rozbalovací nabídka), nebo „@funkce“ stránky.
KARTY_GROMA = [
    ("Soubor", [
        ("Soubor", [("Import souřadnic…", "@import_dialog"), ("Export souřadnic…", "@export_dialog"),
                    ("Načíst z QTrig…", "@qtrig_dialog")]),
        ("Import", [("Trimble (File and Report)…", "@trimble_dialog")]),
        ("Editace", [("Krok zpět", "@undo"), ("Krok vpřed", "@redo"), ("Odstranit", "@delete_selected")]),
        ("Seznam", [("Další seznam souřadnic…", "@dalsi_seznam"), ("Přidej bod…", "@add_point"), ("Hromadné změny…", "@bulk_dialog"),
                    ("Porovnání souřadnic…", "@porovnat_seznam"), ("Identické body…", "@duplicates_dialog")]),
        ("Kódování", [("Kresba z kódů…", "@kresba_z_kodu"), ("Kódovací tabulka…", "@otevri_kodovnik")]),
        ("Nastavení", [("Nastavení…", "@_nastaveni"), ("Tolerance…", "@_tolerance"), ("Teodolit…", "@_teodolit")]),
        ("Pohledy", [("Výchozí rozvržení", "@_vychozi"), ("Dva seznamy", "@dva_seznamy"), ("Okna / záložky", "@_rezim"), ("Mozaika horizontálně", "@_mozaika_h"), ("Mozaika vertikálně", "@_mozaika_v"),
                     ("Kaskáda", "@_kaskada"), ("Okna", "@okna")]),
    ]),
    ("Protokol", [
        ("Protokol", [("Zobrazit", "@_protokol"), ("Uložit do PDF…", "@_protokol_pdf")]),
        ("Měření", [("Seznam měření", "@_zapisnik"), ("Zpracování zápisníku…", "@_zpracovani")]),
    ]),
    ("Výpočty", [
        ("Podrobné", [("Polární", "Rajón (polární bod)"), ("Polární dávkou", "Polární metoda dávkou"),
                      ("Ortogonální", ["Ortogonální metoda (Groma)", "Ortogonální metoda", "Bod ze staničení a kolmice"])]),
        ("Protínání", [("Ze směrů", ["Protínání vpřed ze směrů", "Protínání vpřed z úhlů", "Protínání zpět"]),
                       ("Z délek", "Protínání z délek")]),
        ("Průsečíky", [("Přímka - přímka", "Průsečíky"), ("Přímka - směr", "Průsečík přímka - směr"),
                       ("Přímka - kružnice", "Průsečík přímka - kružnice")]),
        ("Vyrovnání", [("Na přímku", "Vyrovnání na přímku"), ("Na kružnici", "Vyrovnání na kružnici"),
                       ("MNČ", ["Vyrovnávací přímka", "Vyrovnávací kružnice", "Vyrovnání nivelační sítě"])]),
        ("Oměrné", [("Kontrolní", ["Kontrolní oměrné míry", "Výměra z měr", "Kontrola dvou určení"]),
                    ("Konstrukční", "Konstrukční oměrné")]),
        ("Bodové pole", [("Volné stanovisko", "Volné stanovisko"),
                         ("Polygonový pořad", "Polygonový pořad (Groma)"), ("Transformace", "Transformace")]),
        ("Výšky", [("Výška stanoviska", "Výška stanoviska"), ("Výškový pořad", "Výškový pořad"),
                   ("Výšky dávkou", "Výšky dávkou")]),
        ("Měření", [("Směrník a délka", "Směrník a délka"), ("Výměry", "Výměra a obvod"),
                    ("Kubatury", "Model terénu a kubatura")]),
        ("Vytyčovací prvky", [("Polární", "Vytyčovací prvky"), ("Ortogonální", "Staničení a kolmice")]),
        ("Speciální", [("Rozložení oblouku", "Kružnicový oblouk"), ("Nivelace", "Nivelační zápisník"),
                       ("Křovák", "@zkresleni_dialog"), ("Trojúhelníková kalkulačka", "Trojúhelníková kalkulačka")]),
    ]),
]


class PasGromy(QWidget):
    """Pás karet Výpočtů (Soubor, Protokol, Výpočty) – rozložení skupin a názvy tlačítek jako v Gromě 14."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import (QFrame, QGridLayout, QScrollArea, QStackedWidget, QTabBar, QToolButton,
                                       QVBoxLayout)
        self.page = page
        self.setObjectName("pas_karet")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.akce: dict[str, QAction] = {}  # „Karta/Skupina/Text“ → akce (i položky rozbalovacích nabídek)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.karty = QTabBar()
        self.karty.setDrawBase(False)
        self.karty.setExpanding(False)
        lay.addWidget(self.karty)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        jmena = {n: i for i, (n, _p, _f, _fn) in enumerate(_ulohy())}
        pouzite = {n for _k, sk in KARTY_GROMA for _s, tl in sk for _t, c in tl
                   for n in (c if isinstance(c, list) else [c])}
        zbytek = [n for n in jmena if n not in pouzite]
        self.ulohy_v_pasu = (pouzite | set(zbytek)) & set(jmena)  # všechny úlohy jsou dostupné z pásu
        karty = [(k, sk + ([("Další", [("Další výpočty", zbytek)])] if k == "Výpočty" and zbytek else []))
                 for k, sk in KARTY_GROMA]
        for karta, skupiny in karty:
            self.karty.addTab(karta)
            obsah = QWidget()
            obsah.setObjectName("pas_obsah")
            h = QHBoxLayout(obsah)
            h.setContentsMargins(4, 2, 4, 0)
            h.setSpacing(2)
            for skupina, tlacitka in skupiny:
                box = QWidget()
                v = QVBoxLayout(box)
                v.setContentsMargins(2, 0, 2, 0)
                v.setSpacing(0)
                g = QGridLayout()
                g.setSpacing(0)
                from PySide6.QtCore import QSize

                from .groma_ikony import barva_skupiny
                from .groma_ikony import ikona as g_ikona
                for k, (text, cil) in enumerate(tlacitka):
                    b = QToolButton()
                    b.setAutoRaise(True)
                    b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                    b.setIconSize(QSize(18, 18))
                    b.setIcon(g_ikona(skupina, text))
                    klic = f"{karta}/{skupina}/{text}"
                    if isinstance(cil, list):
                        b.setText(text + " ▾")
                        b.setPopupMode(QToolButton.InstantPopup)
                        m = QMenu(b)
                        for n in cil:
                            if n in jmena:
                                a = m.addAction(n)
                                a.triggered.connect(lambda _c=False, i=jmena[n]: otevri_ulohu(page, i))
                                self.akce[f"{klic}/{n}"] = a
                        b.setMenu(m)
                    else:
                        a = QAction(text, b)
                        a.setIcon(b.icon())
                        fn = self._funkce(cil, jmena)
                        if fn is None:
                            continue
                        a.triggered.connect(lambda _c=False, f=fn: f())
                        b.setDefaultAction(a)
                        self.akce[klic] = a
                    g.addWidget(b, k % 3, k // 3)
                v.addLayout(g)
                v.addStretch(1)
                lbl = QLabel(skupina)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setObjectName("pas_skupina")
                bs = barva_skupiny(skupina)
                lbl.setStyleSheet(f"QLabel#pas_skupina {{ color: {bs}; border-top: 2px solid {bs}; }}")
                v.addWidget(lbl)
                h.addWidget(box)
                sep = QFrame()
                sep.setObjectName("pas_oddelovac")
                h.addWidget(sep)
            h.addStretch(1)
            sc = QScrollArea()
            sc.setWidget(obsah)
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.NoFrame)
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sc.setFixedHeight(obsah.sizeHint().height() + 14)
            self.stack.addWidget(sc)
        self.karty.currentChanged.connect(self.stack.setCurrentIndex)
        i = [k for k, _s in KARTY_GROMA].index("Výpočty")
        self.karty.setCurrentIndex(i)
        self.stack.setCurrentIndex(i)

    def _funkce(self, cil: str, jmena: dict):
        p, o = self.page, self.page.tabs
        if not cil.startswith("@"):
            return (lambda i=jmena[cil]: otevri_ulohu(p, i)) if cil in jmena else None
        vlastni = {
            "@_nastaveni": lambda: (p.ulohy.nastaveni_vypoctu(), p.lista.nacti()),
            "@_vychozi": o.vychozi_rozvrzeni, "@_rezim": o.prepni_rezim, "@_mozaika_h": o.mozaika_vodorovne, "@_mozaika_v": o.mozaika_svisle, "@_kaskada": o.cascadeSubWindows,
            "@okna": lambda: self._menu_oken(), "@_protokol": lambda: o.otevri(p.protokol),
            "@_protokol_pdf": p.ulohy.protokol_pdf, "@_zapisnik": lambda: o.otevri(p.zapisnik),
            "@_zpracovani": lambda: p.zpracovani_dialog(),
            "@_tolerance": lambda: (p.ulohy.nastaveni_vypoctu(stranka="Tolerance"), p.lista.nacti()),
            "@_teodolit": lambda: (p.ulohy.nastaveni_vypoctu(stranka="Teodolit"), p.lista.nacti()),
        }
        return vlastni.get(cil) or getattr(p, cil[1:], None)

    def _menu_oken(self) -> QMenu:
        p, o = self.page, self.page.tabs
        from PySide6.QtGui import QCursor
        m = QMenu(self)
        for w, t in ((p.seznam_okno, "Seznam souřadnic"), (p.zapisnik, "Seznam měření"), (p.grafika, "Grafika"),
                     (p.protokol, "Protokol")):
            m.addAction(t).triggered.connect(lambda _c=False, w=w: o.otevri(w))
        for w in getattr(p, "dalsi_seznamy", []):
            m.addAction(f"Seznam souřadnic – {w.nazev}").triggered.connect(lambda _c=False, w=w: o.otevri(w))
        m.addAction("Výpočetní okno").triggered.connect(p.ulohy.otevri)
        m.addSeparator()
        m.addAction("Srovnání ikon").triggered.connect(o.srovnej_ikony)
        m.addAction("Zavři aktivní okno").triggered.connect(o.zavri_aktivni)
        if p.isVisible():
            m.popup(QCursor.pos())
        return m


def postav_menu(page) -> PasGromy:
    pas = PasGromy(page)
    page.a_zpet = pas.akce.get("Soubor/Editace/Krok zpět")
    page.a_vpred = pas.akce.get("Soubor/Editace/Krok vpřed")
    return pas


def _ulohy():
    from .ulohy import OKNA_ULOH
    return OKNA_ULOH


def otevri_ulohu(page, i: int):
    """Výpočet z pásu: otevře nové výpočetní okno úlohy (jako v Gromě – víc oken najednou, i stejné úlohy
    „Polární metoda - [2]“). Nepoužité (zavřené) okno se použije znovu. Vrátí okno."""
    from .ulohy import UlohyPanel
    okna = page.okna_uloh
    ul = next((o for o in okna if not o.isVisible()), None)
    if ul is None:
        ul = UlohyPanel(page)
        okna.append(ul)
        vid = [o for o in okna if o.isVisible()]
        if vid:  # nové okno kousek vedle posledního, ať se nepřekrývají úplně
            ul.resize(vid[-1].size())
            ul.move(vid[-1].pos() + QPoint(32, 32))
            ul._umisteno = True
    if ul.hledat.text():
        ul.hledat.clear()
    if ul.lst.currentRow() == i:
        ul._show(i)
    else:
        ul.lst.setCurrentRow(i)
    stejne = [o for o in okna if o is not ul and o.isVisible() and o.lst.currentRow() == i]
    if stejne:
        ul.setWindowTitle(f"{ul.windowTitle()} - [{len(stejne) + 1}]")
    page.ulohy = ul
    ul.otevri()
    return ul
