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

    def __init__(self, seznam, extra):
        self._s = seznam
        self._e = {b.cislo: b for b in extra}

    def najdi(self, c):
        return self._e.get(c) or self._s.najdi(c)

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
TITULKY = {"Rajón (polární bod)": "Polární metoda", "Transformace": "Transformace souřadnic"}
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
        for nazev, _p, _f, _fn in ULOHY:
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
        self.split.setChildrenCollapsible(False)
        lay.addWidget(self.split, 1)
        self.chyba = QLabel()
        self.chyba.setWordWrap(True)
        lay.addWidget(self.chyba)
        row = QHBoxLayout()
        self.b_novy = QPushButton("Nový výpočet")
        self.b_novy.setToolTip("Vymazat zadání a začít znovu")
        self.b_add = QPushButton("✓ Do seznamu")
        self.b_add.setToolTip("Vypočtené body uložit do seznamu souřadnic")
        self.b_add.setEnabled(False)
        self.b_cad = QPushButton("Do výkresu")
        self.b_cad.setToolTip("Vypočtené body rovnou do výkresu v CAD (značka nebo buňka, číslo a výška)")
        self.b_cad.setEnabled(False)
        from PySide6.QtWidgets import QMenu, QToolButton
        self.b_dalsi = QToolButton()
        self.b_dalsi.setText("Další ▾")
        self.b_dalsi.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.b_dalsi)
        self.b_copy = m.addAction("Kopírovat výsledek")
        self.b_pdf = m.addAction("Protokol do PDF…")
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
        row.addWidget(self.b_cad)
        row.addStretch(1)
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
        self.b_cad.clicked.connect(lambda: self.do_cad())
        self.b_novy.clicked.connect(lambda: self._show(self.lst.currentRow()))
        self.b_prot.clicked.connect(self._ukaz_protokol)
        from .nastaveni_vypoctu import nacti
        nacti()
        self.resize(720, 700)
        self.lst.setCurrentRow(0)

    # ------------------------------------------------------------ okno
    KLIC_GEOM = "vypocty/okno_ulohy"

    def otevri(self):
        """Ukáže okno úlohy (poprvé u pravého okraje hlavního okna, pak kde ho uživatel nechal)."""
        from PySide6.QtCore import QByteArray, QSettings
        if not self.isVisible():
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

    def nastaveni_vypoctu(self, modal: bool = True):
        from .nastaveni_vypoctu import NastaveniVypoctuDialog
        d = NastaveniVypoctuDialog(self)
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
        for i, (nazev, popis, _pole, _fn) in enumerate(ULOHY):
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

    def _show(self, i: int):
        if i < 0:
            return
        self._vycisti()
        nazev, popis, pole, _fn = ULOHY[i]
        from .groma_ikony import ikona as g_ikona
        sk, text = self._kde.get(nazev, ("Další", "Další výpočty"))
        self.setWindowTitle(TITULKY.get(nazev, nazev))
        self.setWindowIcon(g_ikona(sk, text))
        self.setToolTip("")
        self.formbox.setToolTip(popis)
        self._completer_model.setStringList([b.cislo for b in self.page.seznam.body])
        stavba = {"Rajón (polární bod)": self._polarni, "Volné stanovisko": self._volne,
                  "Transformace": self._transformace}.get(nazev)
        nove = {"Rajón (polární bod)": "Nové stanovisko", "Volné stanovisko": "Nové stanovisko",
                "Transformace": "Nová transformace"}.get(nazev, "Nový výpočet")
        self.b_novy.setText(nove)
        if stavba is not None:
            stavba()
        else:
            self._obecny(pole)
        self.vysledek = None
        self.b_add.setEnabled(False)
        self.b_cad.setEnabled(False)
        self.chyba.clear()
        self.vystup.clear()
        self._rozdel()

    def _rozdel(self):
        """Zadání nahoře zabere většinu okna, výsledek dole je malý (celý protokol je v okně Protokol)."""
        t = max(self.split.height(), self.height() - 110, 300)
        self.split.setSizes([t - 140, 140])

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._rozdel()

    def _sekce(self, text: str, *widgety, natahnout: bool = False) -> QWidget:
        """Oddíl okna jako v Gromě: tučný nadpis a pod ním obsah v rámečku."""
        from PySide6.QtWidgets import QFrame
        from .groma_formulare import nadpis
        box = QFrame()
        box.setObjectName("oddil_ulohy")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 8)
        v.setSpacing(5)
        v.addWidget(nadpis(text))
        for w in widgety:
            if isinstance(w, QWidget):
                v.addWidget(w, 1 if natahnout else 0)
            else:
                v.addLayout(w)
        return box

    def _pole(self, key: str, druh: str, sirka: int = 110, tip: str = ""):
        from .groma_formulare import pole
        w = pole(druh, sirka, tip=tip)
        self.inputs[key] = w
        return w

    def _bodbox(self, key: str, z: bool = True, **kw):
        from .groma_formulare import BodBox
        bb = BodBox(self.page, z=z, **kw)
        c = QCompleter(self._completer_model, bb.cislo)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        c.setFilterMode(Qt.MatchStartsWith)
        bb.cislo.setCompleter(c)
        if key:
            self.inputs[key] = bb.cislo
            self._bodboxy[key] = bb
        return bb

    def _vypoctene(self, s_cislem: bool = True) -> tuple[QWidget, dict]:
        """Oddíl Vypočtené souřadnice (jen ke čtení) – vyplní ho výpočet."""
        from .groma_formulare import pole, radek_poli
        p = {k: pole("cislo" if k == "c" else "sour", 110, True) for k in ("c", "y", "x", "z")}
        w = radek_poli(*([("Číslo:", p["c"])] if s_cislem else []), ("Y:", p["y"]), ("X:", p["x"]), ("Z:", p["z"]))
        return w, p

    @staticmethod
    def _vypln(p: dict, bod):
        from .groma_formulare import fmt
        c, y, x, z = bod if bod else ("", None, None, None)
        p["c"].setText(c)
        p["y"].setText(fmt(y))
        p["x"].setText(fmt(x))
        p["z"].setText(fmt(z))

    # --- Polární metoda (G10): Stanovisko | Určovaný bod
    def _polarni(self):
        from PySide6.QtWidgets import QTabWidget
        from .groma_formulare import Prepinac, TabulkaRadku, formular, radek_poli
        tabs = QTabWidget()
        self.zalozky = tabs
        # Stanovisko
        st = QWidget()
        sl = QVBoxLayout(st)
        sl.setContentsMargins(0, 6, 0, 0)
        vp = self._pole("vp", "vys", 90, "Výška stroje (přístroje) nad stabilizací [m]")
        bb = self._bodbox("st", dva_sloupce=True, vlevo=[("Výška stroje:", vp)])
        sl.addWidget(self._sekce("Stanovisko:", bb))
        ob = self._bodbox("o")
        so = self._pole("so", "mer", 110, "Měřený vodorovný směr na orientaci [gon]")
        od = self._pole("od", "mer", 110, "Vodorovná délka na orientaci [m] (nepovinné – pro kontrolu)")
        tab = TabulkaRadku(["Bod", "Směr [g]", "Délka [m]", "V or. [g]", "V délky [m]"], 3)
        self.inputs["orientace"] = tab
        prava = QWidget()
        pl = QVBoxLayout(prava)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(ob)
        pl.addWidget(formular([("Směr:", so), ("Vod. délka:", od)]))
        bp, bo = QPushButton("Přidat"), QPushButton("Odebrat")
        pl.addWidget(radek_poli(("", bp), ("", bo)))
        pl.addStretch(1)
        h = QHBoxLayout()
        h.addWidget(tab, 3)
        h.addWidget(prava, 2)
        sl.addWidget(self._sekce("Orientace:", h, natahnout=True), 1)

        def pridej_or():
            c = ob.cislo.text().strip()
            if not c or not so.text().strip():
                self.chyba.setText("<span style='color:#B45309'>Pro přidání orientace vyplňte číslo bodu a směr."
                                   "</span>")
                return
            r = ob.rucni_bod()
            if r is not None:
                self._rucni[r.cislo] = r
            tab.pridej([c, so.text().strip(), od.text().strip()])
            ob.vymaz()
            so.clear()
            od.clear()
        bp.clicked.connect(pridej_or)
        bo.clicked.connect(tab.odeber)
        self._pred_vypoctem = lambda: pridej_or() if ob.cislo.text().strip() and so.text().strip() else None

        def or_drop(md):
            from .groma_formulare import body_z_mime, mereni_z_mime
            sth, mer = mereni_z_mime(md)
            if sth is not None and not bb.cislo.text().strip():
                b = self.page.seznam.najdi(sth[0])
                bb.nastav(sth[0], *((b.y, b.x, b.z) if b else ()))
                vp.setText(f"{sth[1]:.3f}")
            for m in mer:
                tab.pridej([m["bod"], f"{m['hz']:.4f}", f"{m['d']:.3f}"])
            for c, *_r in ([] if mer else body_z_mime(md)):
                tab.pridej([c, "", ""])
            return True
        tab.pri_pretazeni = or_drop
        tabs.addTab(st, "Stanovisko")
        # Určovaný bod
        ur = QWidget()
        ul = QVBoxLayout(ur)
        ul.setContentsMargins(0, 6, 0, 0)
        nove = self._pole("nove", "cislo", 120, "Číslo určovaného bodu")
        kod = self._pole("kod", "kod", 90)
        sm = self._pole("sm", "mer", 110, "Měřený vodorovný směr [gon]")
        d = self._pole("d", "mer", 110, "Délka [m] – vodorovná; se zenitovým úhlem šikmá")
        dh = self._pole("dh", "vys", 110, "Převýšení [m] (bez zenitového úhlu)")
        zen = self._pole("zenit", "vys", 110, "Zenitový úhel [gon] – délka je pak šikmá")
        vc = self._pole("vc", "vys", 110, "Výška signálu (cíle) [m]")
        g = QHBoxLayout()
        g.addWidget(formular([("Číslo:", nove), ("Kód:", kod)]), 1)
        g.addWidget(formular([("Směr:", sm), ("Délka:", d), ("Převýšení:", dh), ("Zenitový úhel:", zen),
                              ("Výška signálu:", vc)]), 1)
        mer_box = self._sekce("Měřené hodnoty:", g)
        mer_box.setAcceptDrops(True)
        ul.addWidget(mer_box)
        ch1 = Prepinac("Výpočet ze směrníků")
        ch1.setToolTip("Směr je přímo směrník (jižník) na bod – orientace osnovy není potřeba")
        ch2 = Prepinac("Výpočet pro bodové pole")
        ch2.setToolTip("Bod se spočte zvlášť s každým orientačním směrem, výsledek je průměr, rozdíly v protokolu")
        self.inputs["ze_smerniku"] = ch1
        self.inputs["bodove_pole"] = ch2
        ul.addWidget(ch1)
        ul.addWidget(ch2)
        vw, vpole = self._vypoctene()
        ul.addWidget(self._sekce("Vypočtené souřadnice:", vw))
        hint = QLabel("Tip: záměry přetáhněte myší ze Seznamu měření (zápisníku) sem do okna – bod se hned "
                      "spočítá. Víc označených záměr = víc bodů najednou.")
        hint.setWordWrap(True)
        hint.setObjectName("poznamka")
        ul.addWidget(hint)
        ul.addStretch(1)
        tabs.addTab(ur, "Určovaný bod")
        tabs.setAcceptDrops(True)
        self.form.addWidget(tabs, 1)

        def po(v):
            o = v.data.get("orientace") if v else None
            if o:
                tab.nastav_vysledky({k: [a, b] for k, (a, b) in o.items()})
            self._vypln(vpole, v.data.get("bod") if v else None)
        self._po_vypoctu = po
        self._pri_pretazeni_mereni = self._polarni_drop
        self.formbox.setAcceptDrops(True)

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

    # --- Volné stanovisko (G15)
    def _volne(self):
        from PySide6.QtWidgets import QComboBox as _CB
        from .groma_formulare import TabulkaRadku, formular, pole, radek_poli
        ob = self._bodbox("", z=True)
        ob.setToolTip("Orientační bod – zapište číslo nebo přetáhněte bod ze seznamu souřadnic; záměry jdou "
                      "přetáhnout ze zápisníku rovnou do tabulky")
        sm = pole("mer", 110, tip="Měřený vodorovný směr [gon]")
        dl = pole("mer", 110, tip="Délka [m] – vodorovná, se zenitovým úhlem šikmá (nepovinné)")
        zen = pole("vys", 110, tip="Zenitový úhel [gon] (nepovinné – pak se spočte i výška stanoviska)")
        vc = pole("vys", 110, tip="Výška signálu (cíle) [m]")
        h = QHBoxLayout()
        h.addWidget(ob, 1)
        h.addWidget(formular([("Směr:", sm), ("Délka:", dl), ("Zenitový úhel:", zen), ("Výška signálu:", vc)]), 1)
        vyp = _CB()
        vyp.addItems(["Podobnostní transformace", "Shodnostní transformace", "Vyrovnání jako vázaná síť (MNČ)"])
        vyp.setToolTip("Podobnostní = s měřítkem (volné), shodnostní = bez změny měřítka, vázaná síť = vyrovnání "
                       "MNČ podle středních chyb směrů a délek (Nastavení → Teodolit)")
        self.inputs["vypocet"] = vyp
        bp, bo = QPushButton("Přidat"), QPushButton("Odebrat")
        tab = TabulkaRadku(["Bod", "Směr [g]", "Délka [m]", "Zenit [g]", "Výška sig.", "V or. [g]", "V délky [m]",
                            "V přev. [m]"], 5)
        self.inputs["mereni"] = tab
        r = radek_poli(("Výpočet:", vyp), ("", bp), ("", bo), roztahnout=False)
        self.form.addWidget(self._sekce("Orientace:", h, r, tab, natahnout=True), 1)

        def pridej():
            c = ob.cislo.text().strip()
            if not c or not sm.text().strip():
                self.chyba.setText("<span style='color:#B45309'>Vyplňte číslo orientace a směr.</span>")
                return
            rb = ob.rucni_bod()
            if rb is not None:
                self._rucni[rb.cislo] = rb
            tab.pridej([c, sm.text().strip(), dl.text().strip(), zen.text().strip(), vc.text().strip()])
            ob.vymaz()
            for w in (sm, dl, zen, vc):
                w.clear()
        bp.clicked.connect(pridej)
        bo.clicked.connect(tab.odeber)

        def drop(md):
            from .groma_formulare import body_z_mime, mereni_z_mime
            sth, mer = mereni_z_mime(md)
            if sth is not None:
                if not self.inputs["nove"].text().strip():
                    self.inputs["nove"].setText(sth[0])
                self.inputs["vp"].setText(f"{sth[1]:.3f}")
            for m in mer:
                tab.pridej([m["bod"], f"{m['hz']:.4f}", f"{m['sd']:.3f}", f"{m['z']:.4f}", f"{m['vc']:.3f}"])
            for c, *_r in ([] if mer else body_z_mime(md)):
                tab.pridej([c, "", "", "", ""])
            return True
        tab.pri_pretazeni = drop
        nove = self._pole("nove", "cislo", 120, "Číslo volného stanoviska")
        vp = self._pole("vp", "vys", 90, "Výška stroje [m] – pro výšku stanoviska ze zenitových úhlů")
        kod = self._pole("kod", "kod", 90)
        vw, vpole = self._vypoctene(False)
        self.form.addWidget(self._sekce("Vypočtené souřadnice:",
                                        radek_poli(("Číslo:", nove), ("Výška stroje:", vp), ("Kód:", kod)), vw))

        def po(v):
            if v:
                tab.nastav_vysledky(v.data.get("opravy", {}))
            self._vypln(vpole, v.data.get("bod") if v else None)
        self._po_vypoctu = po

    # --- Transformace souřadnic (G17)
    def _transformace(self):
        from .groma_formulare import Prepinac, TabulkaRadku, Volba, formular, nadpis, radek_poli
        cil = self._bodbox("", z=False)
        mis = self._bodbox("", z=False)
        lv = QWidget()
        ll = QVBoxLayout(lv)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(nadpis("Cílové souřadnice:"))
        ll.addWidget(cil)
        ll.addWidget(nadpis("Místní souřadnice:"))
        ll.addWidget(mis)
        tab = TabulkaRadku(["Bod", "Y cíl", "X cíl", "dY [m]", "dX [m]", "dP [m]"], 3)
        self.inputs["identicke"] = tab
        bp, bo = QPushButton("Přidat"), QPushButton("Odebrat")
        pv = QWidget()
        pl = QVBoxLayout(pv)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(tab, 1)
        pl.addWidget(radek_poli(("", bp), ("", bo)))
        h = QHBoxLayout()
        h.addWidget(lv, 2)
        h.addWidget(pv, 3)
        self.form.addWidget(self._sekce("Identické body:", h, natahnout=True), 1)

        def pridej():
            c = mis.cislo.text().strip()
            sc = cil.souradnice()
            if not c or sc is None:
                self.chyba.setText("<span style='color:#B45309'>Vyplňte místní bod (číslo) a cílové souřadnice Y, X."
                                   "</span>")
                return
            rb = mis.rucni_bod()
            if rb is not None:
                self._rucni[rb.cislo] = rb
            tab.pridej([c, f"{sc[0]:.3f}", f"{sc[1]:.3f}"])
            cil.vymaz()
            mis.vymaz()
        bp.clicked.connect(pridej)
        bo.clicked.connect(tab.odeber)
        typ = Volba(["Shodnostní", "Podobnostní", "Afinní"], "Podobnostní")
        self.inputs["druh"] = typ
        jung = Prepinac("Jungova dotransformace")
        jung.setToolTip("Rozdělí opravy z identických bodů na transformované body (váhy 1/d²)")
        self.inputs["jung"] = jung
        pre = self._pole("predpona", "cislo", 70, "Předpona čísel transformovaných bodů")
        pre.setText("T")
        g = QHBoxLayout()
        g.addWidget(self._sekce("Typ transformace:", typ))
        g.addWidget(self._sekce("Volby:", jung, formular([("Předpona čísel:", pre)])), 1)
        w = QWidget()
        w.setLayout(g)
        g.setContentsMargins(0, 0, 0, 0)
        self.form.addWidget(w)
        tr = _Radky()
        tr.setPlaceholderText("Čísla bodů k transformaci – přetáhněte je ze seznamu souřadnic")
        tr.setMinimumHeight(70)
        self.inputs["transformovat"] = tr
        bv = QPushButton("Všechny body seznamu")
        bv.clicked.connect(lambda: tr.setPlainText("\n".join(
            b.cislo for b in self.page.seznam.body if b.cislo not in {r[0] for r in tab.radky()})))
        self.form.addWidget(self._sekce("Transformovat body:", tr, radek_poli(("", bv), roztahnout=False)))

        def po(v):
            if v:
                tab.nastav_vysledky(v.data.get("opravy", {}))
        self._po_vypoctu = po

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
        self.form.addWidget(self._sekce("Zadání:", box))
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
        nazev, _p, _pole, fn = ULOHY[i]
        if self._pred_vypoctem:
            self._pred_vypoctem()
        rucni = list(self._rucni.values()) + [r for bb in self._bodboxy.values()
                                               if (r := bb.rucni_bod()) is not None]
        seznam = _SeznamSRucnimi(self.page.seznam, rucni) if rucni else self.page.seznam
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
        self.vystup.setPlainText("\n".join(self.vysledek.protokol))
        self.b_add.setEnabled(bool(self.vysledek.nove or self.vysledek.vysky))
        self.b_cad.setEnabled(bool(self.vysledek.nove))
        if self._po_vypoctu:
            self._po_vypoctu(self.vysledek)
        if protokolovat:
            self.page.protokol_append(self.vysledek.protokol)
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

            n = self.page.seznam.zmen(f"{ULOHY[self.lst.currentRow()][0]}: výšky", fn, len(vy))
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
        n, konf = self.page.seznam.pridej(nove, f"{ULOHY[self.lst.currentRow()][0]}: nové body")
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
