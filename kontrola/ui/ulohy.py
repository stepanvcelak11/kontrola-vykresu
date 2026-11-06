"""Panel geodetických úloh (Qt). Výpočty samotné jsou v ``kontrola.geodezie.ulohy`` (sdílí je i webová verze)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ..geodezie import ulohy as _U
from ..geodezie.ulohy import *  # noqa: F401,F403 – úlohy u_* a ULOHY pro zpětnou kompatibilitu
from ..geodezie.ulohy import ULOHY, ChybaVstupu, Pole, Vysledek, _f  # noqa: F401

globals().update({k: v for k, v in vars(_U).items() if k.startswith("_") and not k.startswith("__")})


class _SeznamSRucnimi:
    """Seznam souřadnic + body s ručně zapsanými souřadnicemi ve výpočetním okně (do seznamu se neukládají)."""

    def __init__(self, seznam, extra, dalsi=()):
        self._s = seznam
        self._e = {b.cislo: b for b in extra}
        self._d = list(dalsi)  # další otevřené seznamy (hledání ve všech otevřených souborech jako v Gromě)

    def najdi(self, c):
        b = self._e.get(c) or self._s.najdi(c)
        if b is None:
            for d in self._d:
                b = d.najdi(c)
                if b is not None:
                    break
        return b

    @property
    def body(self):
        return list(self._s.body) + list(self._e.values())

    def __getattr__(self, k):
        return getattr(self._s, k)


class _Radky(QPlainTextEdit):
    """Víceřádkové zadání: body přetažené ze seznamu souřadnic se vloží jako čísla (nebo celé řádky Y X Z)."""

    def __init__(self, cele_radky: bool = False):
        super().__init__()
        self.cele_radky = cele_radky

    def canInsertFromMimeData(self, md):  # noqa: N802
        from .groma_formulare import MIME_BODY
        return md.hasFormat(MIME_BODY) or super().canInsertFromMimeData(md)

    def insertFromMimeData(self, md):  # noqa: N802
        from .groma_formulare import MIME_BODY, body_z_mime
        if not md.hasFormat(MIME_BODY):
            return super().insertFromMimeData(md)
        body = body_z_mime(md)
        if self.cele_radky:
            t = "\n".join(" ".join([c] + [f"{v:.3f}" for v in (y, x, z) if v is not None]) for c, y, x, z in body)
        else:
            t = "\n".join(c for c, *_r in body)
        cur = self.toPlainText()
        self.setPlainText((cur.rstrip("\n") + "\n" if cur.strip() else "") + t)


class _BodPole(QWidget):
    """Číslo bodu (žluté pole) + souřadnice ze seznamu vedle; bod jde přetáhnout ze seznamu souřadnic."""

    def __init__(self, page, completer_model):
        super().__init__()
        from .groma_formulare import pole
        self.page = page
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.edit = pole("cislo", 140)
        self.edit.setMaximumWidth(220)
        c = QCompleter(completer_model, self.edit)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        c.setFilterMode(Qt.MatchStartsWith)
        self.edit.setCompleter(c)
        self.edit.setPlaceholderText("číslo bodu")
        self.info = QLabel()
        self.info.setObjectName("poznamka")
        h.addWidget(self.edit)
        h.addWidget(self.info, 1)
        self.setAcceptDrops(True)
        self.edit.textChanged.connect(self._info)

    def _info(self, t: str):
        b = self.page.seznam.najdi(t.strip()) if t.strip() else None
        self.info.setText("" if b is None else f"Y {b.y:.2f}   X {b.x:.2f}" + (f"   Z {b.z:.2f}" if b.z is not None
                                                                                else ""))

    def dragEnterEvent(self, e):  # noqa: N802
        from .groma_formulare import MIME_BODY
        if e.mimeData().hasFormat(MIME_BODY):
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):  # noqa: N802
        from .groma_formulare import body_z_mime
        b = body_z_mime(e.mimeData())
        if b:
            self.edit.setText(b[0][0])
            e.acceptProposedAction()


# názvy oken jako v Gromě
def _davka(s, vysky: bool):
    """Polární metoda dávkou / Výšky dávkou (Groma): celý Seznam měření (zápisník) proti seznamu souřadnic."""
    from .groma_formulare import pole
    from .groma_ulohy import formular
    page, p = s.page, s.p
    zap = page.zapisnik
    info = QLabel()
    info.setWordWrap(True)

    def obnov():
        n = len(zap.stanoviska)
        zameru = sum(len(st.orient) + len(st.detail) for st in zap.stanoviska)
        info.setText(f"Měření: <b>{zap.soubor.name if zap.soubor else 'Seznam měření'}</b> – {n} stanovisek, "
                     f"{zameru} záměr<br>Souřadnice: <b>aktivní seznam</b> ({len(page.seznam.body)} bodů)")
    obnov()

    def nacist():
        if zap.nacist():
            obnov()
    s.pridej(s.oddil("Soubory:", info, s.vedle(s.tlacitko("Načíst měření…", nacist,
                                                          "Zápisník Gromy (.zap), Leica GSI…"),
                                               s.tlacitko("Seznam měření", lambda: page.tabs.otevri(zap)), None,
                                               natahnout=(0, 0, 1))))
    ulozit = s.prepinac("", "Vypočtené " + ("výšky" if vysky else "body") + " uložit do aktivního seznamu",
                        zapnuto=True)
    s.pridej(s.oddil("Volby:", ulozit, s.poznamka("Měřítkový koeficient se bere z lišty nastavení (Měřítko). "
                                                  "Orientace = body se známými souřadnicemi v seznamu.")))
    stav = {k: pole("mer", 120, True) for k in ("st", "bod", "met", "nst", "nb", "nn")}
    s.pridej(s.vedle(s.oddil("Okamžitý stav výpočtu:", formular([("Stanovisko:", stav["st"]), ("Bod:", stav["bod"]),
                                                                 ("Metoda:", stav["met"])], nahoru=False)),
                     s.oddil("Celkový stav výpočtu:", formular([("Stanovisek:", stav["nst"]),
                                                                ("Podrobných bodů:", stav["nb"]),
                                                                ("Nepoužito:", stav["nn"])], nahoru=False))))
    p.form.addStretch(1)

    def vypocet(_seznam, _h):
        if not zap.stanoviska:
            raise ChybaVstupu("Seznam měření je prázdný – načtěte zápisník (Načíst měření…).")
        r = zap.vypocitej()
        if r is None:
            raise ChybaVstupu(zap.info.text().lstrip("⚠ ") or "Výpočet se nepovedl.")
        body = [b for b in r.body if not b.kontrolni]
        zameru = sum(len(st.detail) for st in zap.stanoviska)
        stav["st"].setText(body[-1].stanovisko if body else "")
        stav["bod"].setText(body[-1].bod if body else "")
        stav["met"].setText("výšky" if vysky else "polární metoda")
        stav["nst"].setText(str(len(r.stanoviska)))
        stav["nb"].setText(str(len(body)))
        stav["nn"].setText(str(max(0, zameru - len(r.body))))
        prot = zap.vystup.toPlainText().splitlines()
        if vysky:
            vys = {b.bod: b.z for b in body if b.z is not None and page.seznam.najdi(b.bod) is not None}
            v = Vysledek(prot, [], vys)
        else:
            from ..geodezie.body import Bod
            v = Vysledek(prot, [Bod(b.bod, b.y, b.x, b.z, poznamka=f"polární metoda ze st. {b.stanovisko}")
                                for b in body])
        if ulozit.isChecked():
            QTimer_single(lambda: p.pridej())
        return v
    p._vlastni_vypocet = vypocet
    p._pri_pretazeni_mereni = None


def QTimer_single(fn):  # noqa: N802
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, fn)


VLASTNI_OKNA = {"Polární metoda dávkou": lambda s: _davka(s, False), "Výšky dávkou": lambda s: _davka(s, True)}
OKNA_ULOH = list(ULOHY) + [
    ("Polární metoda dávkou", "Celý Seznam měření najednou: orientace, podrobné body, výšky.", [], None),
    ("Výšky dávkou", "Výšky bodů ze Seznamu měření (trigonometricky) do seznamu souřadnic.", [], None),
]

# pole výšek a zenitů (fialová), ostatní čísla jsou měření (modrá)
_VYSKOVE = {"vp", "vc", "zenit", "z", "z1", "z2", "dh", "H", "zref", "vp1", "vp2", "vc1", "vc2", "mez", "interval"}


class UlohyPanel(QWidget):
    """Výpočetní okno jako v Gromě: samostatné okno úlohy (lze posunout, zvětšit, maximalizovat), barevná pole,
    body a měření se přetahují ze seznamů, dole Nový / Protokol / Výpočet."""

    pointsAdded = Signal(int)

    def __init__(self, page, parent=None):
        super().__init__(parent if parent is not None else page, Qt.Window)
        self.page = page
        self.setObjectName("vypocetni_okno")
        self.setMinimumSize(440, 360)
        from .groma_ikony import ikona as g_ikona
        from .groma_okna import KARTY_GROMA
        kde = {}  # úloha → (skupina, tlačítko) v pásu Výpočtů: ikona a barva skupiny
        for _k, skupiny in KARTY_GROMA:
            for sk, tl in skupiny:
                for text, cil in tl:
                    for n in (cil if isinstance(cil, list) else [cil]):
                        kde.setdefault(n, (sk, text))
        self._kde = kde
        # seznam úloh zůstává (hledání, výběr z pásu), v okně se ale neukazuje – úlohy jsou v pásu jako v Gromě
        self.lst = QListWidget(self)
        self.lst.hide()
        for nazev, _p, _f_, _fn in OKNA_ULOH:
            sk, text = kde.get(nazev, ("Další", "Další výpočty"))
            self.lst.addItem(QListWidgetItem(g_ikona(sk, text), nazev))
        self.hledat = QLineEdit(self)
        self.hledat.hide()
        self.hledat.textChanged.connect(self.filtruj)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        from PySide6.QtWidgets import QScrollArea
        self.formbox = QWidget()
        self.formbox.setObjectName("zadani_ulohy")
        self.form = QVBoxLayout(self.formbox)
        self.form.setContentsMargins(4, 4, 4, 4)
        self.form.setSpacing(6)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.formbox)
        self.scroll.setWidgetResizable(True)
        from PySide6.QtWidgets import QFrame
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.vystup = QTextBrowser()
        self.vystup.setObjectName("vypis")
        self.vystup.setPlaceholderText("Výsledek výpočtu (celý protokol je v okně Protokol)")
        self.split = QSplitter(Qt.Vertical)
        self.split.addWidget(self.scroll)
        self.split.addWidget(self.vystup)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(True)
        self.split.setCollapsible(0, False)
        # vpravo návod (ⓘ) a náčrt bodů úlohy (jako kontrolní kresba Gromy)
        from .nacrt_ulohy import Nacrt
        self.prava = QWidget()
        pl = QVBoxLayout(self.prava)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        self.navod = QTextBrowser()
        self.navod.setObjectName("navod_ulohy")
        self.navod.setOpenExternalLinks(False)
        self.nacrt = Nacrt()
        self.psplit = QSplitter(Qt.Vertical)
        self.psplit.addWidget(self.navod)
        self.psplit.addWidget(self.nacrt)
        self.psplit.setChildrenCollapsible(False)
        self.psplit.setSizes([300, 360])
        pl.addWidget(self.psplit)
        self.hsplit = QSplitter(Qt.Horizontal)
        self.hsplit.addWidget(self.split)
        self.hsplit.addWidget(self.prava)
        self.hsplit.setStretchFactor(0, 3)
        self.hsplit.setStretchFactor(1, 2)
        self.hsplit.setChildrenCollapsible(False)
        lay.addWidget(self.hsplit, 1)
        self.chyba = QLabel()
        self.chyba.setWordWrap(True)
        lay.addWidget(self.chyba)
        row = QHBoxLayout()
        self.b_novy = QPushButton("Nový výpočet")
        self.b_novy.setToolTip("Vymazat zadání a začít znovu")
        self.b_add = QPushButton("✓ Do seznamu")
        self.b_add.setToolTip("Vypočtené body uložit do seznamu souřadnic")
        self.b_add.setEnabled(False)
        from PySide6.QtWidgets import QMenu, QToolButton
        self.b_dalsi = QToolButton()
        self.b_dalsi.setText("Další ▾")
        self.b_dalsi.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.b_dalsi)
        self.b_cad = m.addAction("Vypočtené body do výkresu (CAD)")
        self.b_cad.setToolTip("Vypočtené body rovnou do výkresu v CAD (značka nebo buňka, číslo a výška)")
        self.b_cad.setEnabled(False)
        self.b_copy = m.addAction("Kopírovat výsledek")
        self.b_pdf = m.addAction("Protokol do PDF…")
        self.a_vystup = m.addAction("Výsledek výpočtu v okně")
        self.a_vystup.setCheckable(True)
        self.a_vystup.toggled.connect(lambda _c: self._rozdel())
        m.addSeparator()
        self.b_nast = m.addAction("Nastavení výpočtů…")
        self.b_dalsi.setMenu(m)
        self.b_prot = QPushButton("Protokol")
        self.b_prot.setToolTip("Ukázat okno Protokol (zapisuje se do něj každý výpočet)")
        self.b_calc = QPushButton("Výpočet")
        self.b_calc.setProperty("primarni", True)
        self.b_calc.setShortcut("Ctrl+Return")
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Alt+V"), self, activated=lambda: self.vypocitej())
        row.addWidget(self.b_novy)
        row.addWidget(self.b_add)
        row.addStretch(1)
        from PySide6.QtCore import QSettings
        self.b_navod = QPushButton("ⓘ Návod")
        self.b_navod.setCheckable(True)
        self.b_navod.setToolTip("Krátký návod: co úloha počítá, co kam vyplnit a co znamenají pole")
        self.b_nacrt = QPushButton("Náčrt")
        self.b_nacrt.setCheckable(True)
        self.b_nacrt.setToolTip("Náčrt bodů úlohy – modře dané body, červeně vypočtené (sever nahoře)")
        self.b_navod.setChecked(QSettings().value("vypocty/navod", True, type=bool))
        self.b_nacrt.setChecked(QSettings().value("vypocty/nacrt", True, type=bool))
        self.b_navod.toggled.connect(lambda c: (QSettings().setValue("vypocty/navod", c), self._prava()))
        self.b_nacrt.toggled.connect(lambda c: (QSettings().setValue("vypocty/nacrt", c), self._prava()))
        row.addWidget(self.b_navod)
        row.addWidget(self.b_nacrt)
        for w in (self.b_dalsi, self.b_prot, self.b_calc):
            row.addWidget(w)
        lay.addLayout(row)
        self.inputs: dict[str, QWidget] = {}
        self._bodboxy: dict = {}
        self._po_vypoctu = None
        self._rucni: dict = {}
        self.vysledek: Vysledek | None = None
        self._completer_model = QStringListModel(self)
        self.lst.currentRowChanged.connect(self._show)
        self.b_calc.clicked.connect(lambda: self.vypocitej())
        self.b_add.clicked.connect(self.pridej)
        self.b_copy.triggered.connect(self._copy)
        self.b_pdf.triggered.connect(lambda: self.protokol_pdf())
        self.b_nast.triggered.connect(lambda: self.nastaveni_vypoctu())
        self.b_cad.triggered.connect(lambda: self.do_cad())
        self.b_novy.clicked.connect(lambda: self._show(self.lst.currentRow()))
        self.b_prot.clicked.connect(self._ukaz_protokol)
        from .nastaveni_vypoctu import nacti
        nacti()
        from PySide6.QtCore import QTimer
        self._nacrt_podpis = None
        self._nacrt_timer = QTimer(self)
        self._nacrt_timer.setInterval(600)
        self._nacrt_timer.timeout.connect(self.obnov_nacrt)
        self.resize(1040, 700)
        self._prava()
        self.lst.setCurrentRow(0)

    # ------------------------------------------------------------ okno
    KLIC_GEOM = "vypocty/okno_ulohy"

    def otevri(self):
        """Ukáže okno úlohy (poprvé u pravého okraje hlavního okna, pak kde ho uživatel nechal)."""
        from PySide6.QtCore import QByteArray, QSettings
        if not self.isVisible():
            if not getattr(self, "_umisteno", False):
                self._umisteno = True
                g = QSettings().value(self.KLIC_GEOM)
                if isinstance(g, (QByteArray, bytes)) and g:
                    self.restoreGeometry(QByteArray(g))
                else:
                    hl = self.page.window()
                    if hl is not None and hl is not self:
                        r = hl.frameGeometry()
                        self.move(max(r.left(), r.right() - self.width() - 20), r.top() + 160)
            self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def hideEvent(self, e):  # noqa: N802
        from PySide6.QtCore import QSettings
        QSettings().setValue(self.KLIC_GEOM, self.saveGeometry())
        self._nacrt_timer.stop()
        super().hideEvent(e)

    def _ukaz_protokol(self):
        tabs = getattr(self.page, "tabs", None)
        if tabs is not None and hasattr(self.page, "protokol"):
            tabs.otevri(self.page.protokol)
            w = self.page.window()
            if w is not None:
                w.raise_()

    def do_cad(self) -> dict | None:
        """Nové body výpočtu do výkresu v CAD (jako body z terénu – bez spojování linií)."""
        win = getattr(self.page, "win", None)
        cad = getattr(win, "cad", None) if win is not None else None
        if cad is None or not self.vysledek or not self.vysledek.nove:
            return None
        v = cad.body_z_terenu(list(self.vysledek.nove), linie=False)
        self.chyba.setText(f"<span style='color:#16A34A'>✓ Do výkresu v CAD vloženo {v.get('body', 0)} bodů "
                           "(už vložené se nevkládají znovu).</span>")
        return v

    def nastaveni_vypoctu(self, modal: bool = True, stranka: str | None = None):
        from .nastaveni_vypoctu import STRANKY, NastaveniVypoctuDialog
        d = NastaveniVypoctuDialog(self)
        if stranka in STRANKY:
            d.zalozky.setCurrentRow(STRANKY.index(stranka))
        if modal and d.exec():
            self.chyba.setText("Nastavení výpočtů uloženo – použije se při dalším výpočtu.")
        return d

    def filtruj(self, text: str):
        """Schová úlohy, které neodpovídají hledanému textu (bez ohledu na diakritiku, i v popisu)."""
        import unicodedata

        def bez(t: str) -> str:
            return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
        slova = bez(text).split()
        prvni = None
        for i, (nazev, popis, _pole, _fn) in enumerate(OKNA_ULOH):
            ok = all(w in bez(nazev + " " + popis) for w in slova)
            self.lst.item(i).setHidden(not ok)
            if ok and prvni is None:
                prvni = i
        cur = self.lst.currentItem()
        if prvni is not None and (cur is None or cur.isHidden()):
            self.lst.setCurrentRow(prvni)

    def _ze_souboru(self, pole: QPlainTextEdit):
        """Řádky (kontrolní body, délky, úhly…) z textového souboru, např. seznamu z kontrolního měření."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Řádky ze souboru", "",
                                              "Text (*.txt *.csv *.prn *.dat);;Vše (*)")
        if not path:
            return
        data = Path(path).read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1250", errors="replace")  # Groma, Kokeš
        pole.setPlainText(text.replace("\t", " "))

    # ------------------------------------------------------------ stavba okna úlohy
    def _vycisti(self):
        while self.form.count():
            it = self.form.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.inputs = {}
        self._bodboxy = {}
        self._po_vypoctu = None
        self._pred_vypoctem = None
        self._pri_pretazeni_mereni = None
        self._rucni = {}
        self._tlacitka_ulozit = []
        self._ma_ulozeni = False
        self._kvalita_nove = None
        self._vlastni_vypocet = None
        self.zalozky = None

    def _show(self, i: int):
        if i < 0:
            return
        self._vycisti()
        nazev, popis, pole, _fn = OKNA_ULOH[i]
        from .groma_ikony import ikona as g_ikona
        from .groma_ulohy import NOVY, OKNA, TITULKY, Stavitel
        sk, text = self._kde.get(nazev, ("Další", "Další výpočty"))
        self.setWindowTitle(TITULKY.get(nazev, nazev))
        self.setWindowIcon(g_ikona(sk, text))
        self.formbox.setToolTip(popis)
        self._completer_model.setStringList([b.cislo for b in self.page.seznam.body])
        self.b_novy.setText(NOVY.get(nazev, "Nový výpočet"))
        stavba = OKNA.get(nazev) or VLASTNI_OKNA.get(nazev)
        # okna Gromy mají výsledky přímo v polích (a celý protokol v okně Protokol) – pruh s výpisem je sbalený
        self._sbalit_vystup = nazev in OKNA
        self.a_vystup.setChecked(not self._sbalit_vystup)
        if stavba is not None:
            stavba(Stavitel(self))
        else:
            self._obecny(pole)
        self.b_add.setVisible(not self._ma_ulozeni)
        self.vysledek = None
        self.b_add.setEnabled(False)
        self.b_cad.setEnabled(False)
        for t in self._tlacitka_ulozit:
            t.setEnabled(False)
        self.chyba.clear()
        self.vystup.clear()
        from .napoveda_uloh import html as _navod
        self.navod.setHtml(_navod(nazev, popis, pole))
        self._nacrt_podpis = None
        self._rozdel()

    def _prava(self):
        """Pravý sloupec: návod a/nebo náčrt (tlačítka ⓘ Návod a Náčrt dole)."""
        nv, nc = self.b_navod.isChecked(), self.b_nacrt.isChecked()
        self.navod.setVisible(nv)
        self.nacrt.setVisible(nc)
        self.prava.setVisible(nv or nc)
        if nc:
            self._nacrt_podpis = None
            self.obnov_nacrt()

    def _cisla_zadani(self) -> list[str]:
        """Čísla bodů v zadání (v pořadí polí): první slovo každého řádku každého pole."""
        out = []
        for v in self.hodnoty().values():
            for r in str(v).splitlines():
                t = r.replace(",", " ").replace(";", " ").split()
                if t:
                    out.append(t[0])
        return out

    def obnov_nacrt(self):
        if not self.isVisible() or not self.nacrt.isVisible():
            return
        from .napoveda_uloh import NACRT
        from .nacrt_ulohy import sestav
        i = self.lst.currentRow()
        nazev = OKNA_ULOH[i][0] if i >= 0 else ""
        try:
            cisla = self._cisla_zadani()
        except Exception:  # noqa: BLE001 – náčrt nesmí rozbít okno
            return
        nove = list(self.vysledek.nove) if self.vysledek else []
        podpis = (nazev, tuple(cisla), tuple((b.cislo, round(b.y, 3), round(b.x, 3)) for b in nove),
                  len(self.page.seznam.body))
        if podpis == self._nacrt_podpis:
            return
        self._nacrt_podpis = podpis
        rucni = {b.cislo: b for bb in self._bodboxy.values() if (b := bb.rucni_bod()) is not None}
        rucni.update(self._rucni)

        def najdi(c):
            return rucni.get(c) or self.page.seznam.najdi(c)
        body, cary = sestav(cisla, najdi, nove, NACRT.get(nazev, "body"))
        self.nacrt.nastav(body, cary)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._rozdel()
        self._nacrt_timer.start()
        self.obnov_nacrt()

    def _rozdel(self):
        """Zadání nahoře zabere většinu okna, výsledek dole je malý (celý protokol je v okně Protokol)."""
        t = max(self.split.height(), self.height() - 110, 300)
        dole = 140 if self.a_vystup.isChecked() else 0
        self.split.setSizes([t - dole, dole])

    def _polarni_drop(self, md) -> bool:
        """Záměry ze zápisníku do Určovaného bodu: každá se hned spočte (jako přetažení v Gromě)."""
        from .groma_formulare import mereni_z_mime
        sth, mer = mereni_z_mime(md)
        if not mer:
            return False
        bb = self._bodboxy.get("st")
        if sth is not None and bb is not None and not bb.cislo.text().strip():
            b = self.page.seznam.najdi(sth[0])
            bb.nastav(sth[0], *((b.y, b.x, b.z) if b else ()))
            self.inputs["vp"].setText(f"{sth[1]:.3f}")
        prot, nove, posl = [], [], None
        for m in mer:
            self.nastav(nove=m["bod"], sm=f"{m['hz']:.4f}", d=f"{m['sd']:.3f}", zenit=f"{m['z']:.4f}",
                        vc=f"{m['vc']:.3f}", dh="")
            v = self.vypocitej(protokolovat=False)
            if v is None:
                return True
            prot += v.protokol + [""]
            nove += v.nove
            posl = v
        if posl is not None and len(mer) > 1:
            self.vysledek = Vysledek(prot, nove, data=posl.data)
            self.vystup.setPlainText("\n".join(prot))
            self.chyba.setText(f"<span style='color:#16A34A'>✓ Spočteno {len(nove)} bodů.</span>")
        if self.vysledek:
            self.page.protokol_append(self.vysledek.protokol)
        return True

    # --- ostatní úlohy: přehledný formulář (popisek | pole), dlouhé popisky jen v nápovědě
    def _obecny(self, pole):
        from PySide6.QtWidgets import QGridLayout
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(7)
        for r, p in enumerate(pole):
            kratky = p.label.split(" (")[0]
            napoveda = (p.label + (" – " + p.napoveda if p.napoveda else "")) if kratky != p.label or p.napoveda \
                else ""
            if p.typ == "volba":
                w = QComboBox()
                w.addItems(list(p.volby))
                w.setCurrentText(p.vychozi)
                vstup = w
            elif p.typ == "radky":
                w = _Radky(cele_radky="Y" in p.label)
                w.setMinimumHeight(96)
                fmt_ = p.label[len(kratky):].strip(" ()")
                w.setPlaceholderText((fmt_ + "\n" if fmt_ else "") + "body lze přetáhnout ze seznamu souřadnic")
                vstup = w
                obal = QWidget()
                ol = QHBoxLayout(obal)
                ol.setContentsMargins(0, 0, 0, 0)
                ol.addWidget(w, 1)
                b = QPushButton("Ze souboru…")
                b.setToolTip("Načíst řádky z textového souboru (mezery i tabulátory, i seznam souřadnic)")
                b.clicked.connect(lambda _c=False, pole=w: self._ze_souboru(pole))
                ol.addWidget(b, 0, Qt.AlignTop)
                w = obal
            elif p.typ == "bod":
                w = _BodPole(self.page, self._completer_model)
                vstup = w.edit
            else:
                from .groma_formulare import pole as _pole
                druh = "cislo" if p.typ == "text" else ("vys" if p.key in _VYSKOVE else "mer")
                vstup = w = _pole(druh, 120)
                w.setText(p.vychozi)
                w.setMaximumWidth(260 if p.typ == "text" else 180)
            if napoveda:
                vstup.setToolTip(napoveda)
            lbl = QLabel(kratky + ":")
            lbl.setAlignment(Qt.AlignRight | (Qt.AlignTop if p.typ == "radky" else Qt.AlignVCenter))
            lbl.setToolTip(napoveda)
            g.addWidget(lbl, r, 0)
            g.addWidget(w, r, 1)
            self.inputs[p.key] = vstup
        g.setColumnStretch(1, 1)
        from .groma_ulohy import Stavitel
        self.form.addWidget(Stavitel(self).oddil("Zadání:", box))
        self.form.addStretch(1)

    # ------------------------------------------------------------ přetažení měření do okna
    def dragEnterEvent(self, e):  # noqa: N802
        from .groma_formulare import MIME_MERENI
        if e.mimeData().hasFormat(MIME_MERENI) and getattr(self, "_pri_pretazeni_mereni", None):
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):  # noqa: N802
        f = getattr(self, "_pri_pretazeni_mereni", None)
        if f is not None and f(e.mimeData()):
            e.acceptProposedAction()

    # ------------------------------------------------------------ hodnoty
    def hodnoty(self) -> dict:
        out = {}
        for k, w in self.inputs.items():
            if hasattr(w, "hodnota"):
                out[k] = w.hodnota()
            elif isinstance(w, QComboBox):
                out[k] = w.currentText()
            elif isinstance(w, QPlainTextEdit):
                out[k] = w.toPlainText()
            else:
                out[k] = w.text()
        return out

    def nastav(self, **hodnoty):
        for k, v in hodnoty.items():
            w = self.inputs[k]
            if hasattr(w, "nastav_hodnotu"):
                w.nastav_hodnotu(str(v))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(str(v))
            else:
                w.setText(str(v))
            if k in self._bodboxy:
                self._bodboxy[k]._dopln()

    def vypocitej(self, protokolovat: bool = True) -> Vysledek | None:
        i = self.lst.currentRow()
        nazev, _p, _pole, fn = OKNA_ULOH[i]
        fn = self._vlastni_vypocet or fn
        if self._pred_vypoctem:
            self._pred_vypoctem()
        rucni = list(self._rucni.values()) + [r for bb in self._bodboxy.values()
                                               if (r := bb.rucni_bod()) is not None]
        dalsi = [w.seznam for w in getattr(self.page, "dalsi_seznamy", [])]
        seznam = _SeznamSRucnimi(self.page.seznam, rucni, dalsi) if (rucni or dalsi) else self.page.seznam
        try:
            self.vysledek = fn(seznam, self.hodnoty())
        except ChybaVstupu as e:
            self.chyba.setText(f"<span style='color:#DC2626'>⚠ {escape(str(e))}</span>")
            self.vysledek = None
            self.b_add.setEnabled(False)
            self.b_cad.setEnabled(False)
            if self._po_vypoctu:
                self._po_vypoctu(None)
            return None
        except Exception as e:  # noqa: BLE001 – výpočet nesmí shodit aplikaci
            self.chyba.setText(f"<span style='color:#DC2626'>⚠ Výpočet se nepovedl: {escape(str(e))}</span>")
            self.vysledek = None
            return None
        self.chyba.clear()
        from dataclasses import replace as _repl
        kv = self._kvalita_nove.currentText() if self._kvalita_nove is not None else ""
        kod = self.inputs["kod"].text().strip() if "kod" in self.inputs and hasattr(self.inputs["kod"], "text") \
            else ""
        if kv or kod:
            self.vysledek.nove = [_repl(b, kvalita=b.kvalita or (int(kv) if kv else None), kod=b.kod or kod)
                                  for b in self.vysledek.nove]
        self.vystup.setPlainText("\n".join(self.vysledek.protokol))
        for t in self._tlacitka_ulozit:
            t.setEnabled(bool(self.vysledek.nove or self.vysledek.vysky))
        self.b_add.setEnabled(bool(self.vysledek.nove or self.vysledek.vysky))
        self.b_cad.setEnabled(bool(self.vysledek.nove))
        if self._po_vypoctu:
            self._po_vypoctu(self.vysledek)
        if protokolovat:
            self.page.protokol_append(self.vysledek.protokol)
        self.obnov_nacrt()
        return self.vysledek

    def pridej(self) -> int:
        if self.vysledek and getattr(self.vysledek, "vysky", None):
            from dataclasses import asdict

            from ..geodezie.body import Bod
            vy = dict(self.vysledek.vysky)

            def fn(body):
                for i, b in enumerate(body):
                    if b.cislo in vy:
                        d = asdict(b)
                        d["z"] = round(vy[b.cislo], 4)
                        body[i] = Bod(**d)
                return len(vy)

            n = self.page.seznam.zmen(f"{OKNA_ULOH[self.lst.currentRow()][0]}: výšky", fn, len(vy))
            self.page.model.refresh()
            self.page._after_change()
            self.chyba.setText(f"<span style='color:#16A34A'>✓ Výšky zapsány u {n} bodů.</span>")
            if not self.vysledek.nove:
                return n
        if not self.vysledek or not self.vysledek.nove:
            return 0
        from dataclasses import replace

        from ..geodezie.nastaveni import aktualni
        d = aktualni().desetiny
        nove = [replace(b, y=round(b.y, d), x=round(b.x, d), z=None if b.z is None else round(b.z, max(d, 3)))
                for b in self.vysledek.nove]
        n, konf = self.page.seznam.pridej(nove, f"{OKNA_ULOH[self.lst.currentRow()][0]}: nové body")
        self.page.model.refresh()
        self.page._after_change()
        if konf:
            self.chyba.setText("<span style='color:#B45309'>Body " + ", ".join(konf) + " už v seznamu jsou – "
                               "nepřepsaly se (zvolte jiné číslo nebo bod v seznamu nejdřív smažte).</span>")
        else:
            self.chyba.setText(f"<span style='color:#16A34A'>✓ Přidáno do seznamu: {n} bodů.</span>")
        self.pointsAdded.emit(n)
        return n

    def protokol_pdf(self, cesta: str | None = None, vse: bool | None = None):
        """Uloží protokol do PDF: buď poslední výpočet, nebo celý protokol projektu (všechny výpočty)."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..geodezie.protokol import protokol_pdf
        celek = None
        p = getattr(self.page, "_path", None)
        if p is not None and p.with_name("protokol.txt").exists():
            celek = p.with_name("protokol.txt").read_text(encoding="utf-8")
        if vse is None:
            if celek and self.vystup.toPlainText().strip():
                r = QMessageBox.question(self, "Protokol PDF", "Uložit protokol všech výpočtů projektu?\n\n"
                                         "Ano = všechny výpočty, Ne = jen poslední výpočet.",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if r == QMessageBox.Cancel:
                    return None
                vse = r == QMessageBox.Yes
            else:
                vse = bool(celek) and not self.vystup.toPlainText().strip()
        text = celek if vse else self.vystup.toPlainText()
        if not (text or "").strip():
            self.chyba.setText("<span style='color:#B45309'>Zatím není co uložit – nejdřív něco vypočítejte.</span>")
            return None
        if cesta is None:
            cesta, _ = QFileDialog.getSaveFileName(self, "Protokol do PDF", "protokol_vypoctu.pdf", "PDF (*.pdf)")
            if not cesta:
                return None
        win = getattr(self.page, "win", None)
        pr = getattr(win, "project", None) if win is not None else None
        nazev = getattr(pr, "name", "") if pr is not None else ""
        from ..geodezie.nastaveni import aktualni
        n = aktualni()
        hlav = n.hlavicka()
        text = "\n".join(hlav + ["-" * max(len(r) for r in hlav), ""]) + text
        out = protokol_pdf(text, cesta, nazev=f"Výpočetní protokol {n.zakazka or nazev}".strip(),
                           autor=n.zpracovatel)
        self.chyba.setText(f"<span style='color:#16A34A'>✓ Protokol uložen: {out}</span>")
        return out

    def _copy(self):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.vystup.toPlainText())


def protokol_path(root: Path) -> Path:
    return Path(root) / "vypocty" / "protokol.txt"
