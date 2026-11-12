"""Okno „Body ze seznamu“ v CAD: zdroj (seznam projektu / soubor), výběr bodů a předvolby ze zadání."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
                               QLineEdit, QMessageBox, QVBoxLayout)

from ..cad.body_seznam import TVARY, NastaveniBodu, odhad_vysky_textu, vloz_body, vychozi_nastaveni


def _klic(c: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", c)]


class BodyDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Body ze seznamu souřadnic")
        self._soubor_body = None
        lay = QVBoxLayout(self)
        uvod = QLabel("Body se umístí na své souřadnice (shodně se světem S-JTSK jako v MicroStationu). "
                      "U značky, čísla, výšky a kódu zvolte hladinu, barvu a velikost – nebo druh prvku ze zadání či nástroj "
                      "pracovní sady (Účelová mapa).")
        uvod.setWordWrap(True)
        from PySide6.QtWidgets import QSizePolicy
        uvod.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # zalomený úvod okno nerozšiřuje
        lay.addWidget(uvod)
        f = QFormLayout()
        self.zdroj = QComboBox()
        self.zdroj.addItems(["Seznam souřadnic projektu (Výpočty)", "Ze souboru…"])
        self.zdroj.activated.connect(self._zdroj)
        f.addRow("Zdroj:", self.zdroj)
        self.filtr = QLineEdit()
        self.filtr.setPlaceholderText("vše, nebo čísla „1-50, 101“, nebo kód „kód=3.13“")
        f.addRow("Body:", self.filtr)
        from ..cad.body_seznam import HLADINA_UM
        self.podle_um = QCheckBox("Podle atributové tabulky Účelové mapy – bod, informace o bodu, číslo, výška "
                                  "a značka 9.12 (jako import Gromou ve škole)")
        self.podle_um.setToolTip("Hladiny GS01-body-poloha / -info / -čísla a GS09-výškopis-body podrobné-výšky / "
                                 "-buňky, barvy, písmo a velikosti podle tabulky atributů ÚM. Číslo bodu se píše "
                                 "bez předčíslí. Vypněte, když chcete atributy nastavit sami.")
        je_um = page.dok is not None and HLADINA_UM in page.dok.doc.layers
        self._je_um = je_um
        self.podle_um.setVisible(je_um)
        self.podle_um.setChecked(je_um and self._nast_um())
        f.addRow(self.podle_um)
        self._pv_sady = page.predvolby_sady()
        self._pv = list(page._predvolby) + self._pv_sady  # zadání + nástroje pásu pracovní sady (ÚM)
        vych = vychozi_nastaveni(self._pv)
        lay.addLayout(f)
        f = QFormLayout()
        # atributy jako při importu bodů do MicroStationu: co vložit, hladina, barva, velikost
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QDoubleSpinBox, QGridLayout, QGroupBox, QPushButton
        self._nast = QSettings("KontrolaVykresu", "KontrolaVykresu")
        grp = self.grp_atributy = QGroupBox("Co vložit a s jakými atributy")
        g = QGridLayout(grp)
        for c, t in enumerate(("", "Podle", "Hladina", "Barva", "Vel. [m]")):
            if t:
                lb = QLabel(f"<b>{t}</b>")
                g.addWidget(lb, 0, c)
        vrstvy = sorted(ly.dxf.name for ly in page.dok.doc.layers) if page.dok is not None else ["0"]
        self.cb, self.ch, self.hl, self.barvy, self.vel = {}, {}, {}, {}, {}
        odhad = odhad_vysky_textu(self._vsechny_body())
        radky = (("znacka", "Značka", ("bod", None), vych.znacka, "body", 0.3),
                 ("cislo", "Číslo", ("text",), vych.cislo, "čísla bodů", odhad),
                 ("vyska", "Výška", ("text",), vych.vyska, "výšky bodů", odhad * 0.8),
                 ("kod", "Kód", ("text",), None, "kódy bodů", odhad * 0.8))
        for r, (klic, popis, typy, hodnota, vrstva, velikost) in enumerate(radky, start=1):
            ch = QCheckBox(popis)
            ch.setChecked(self._nast.value(f"cad/body/{klic}/ano", "true" if klic in ("znacka", "cislo") else
                                           "false") in (True, "true"))
            cb = QComboBox()
            cb.addItem("vlastní atributy", "vlastni")
            for p in self._pv:
                z_pasu = bool(p.nastroj == "vlož" and p.nazev_pravidla and p.kod)  # buňka z pásu sady
                if klic == "znacka" and z_pasu and "bod" not in p.kod.lower():
                    continue  # ze 175 značek ÚM jen značky bodů
                if p.geometrie in typy or (klic == "znacka" and p.blok):
                    cb.addItem(f"{'nástroj' if p in self._pv_sady else 'zadání'}: {p.nazev}", p)
                    cb.setItemData(cb.count() - 1, p.popis(), Qt.ToolTipRole)
            ulozene = str(self._nast.value(f"cad/body/{klic}/podle", ""))
            if ulozene and cb.findText(ulozene) > 0:  # naposledy zvolený druh prvku / nástroj (ne „vlastní“)
                cb.setCurrentIndex(cb.findText(ulozene))
            elif hodnota is not None:
                cb.setCurrentIndex(max(0, cb.findText(f"zadání: {hodnota.nazev}")))
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(4)
            cb.setToolTip("Vlastní atributy, nebo druh prvku ze zadání (hladina, barva i velikost podle Směrnice)")
            hl = QComboBox()
            hl.setEditable(True)
            hl.addItems(vrstvy)
            hl.setCurrentText(str(self._nast.value(f"cad/body/{klic}/hladina", vrstva)))
            hl.setToolTip("Hladina – vyberte, nebo napište novou (založí se)")
            hl.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            hl.setMinimumContentsLength(5)
            bv = QPushButton()
            bv.setToolTip("Barva z tabulky MicroStationu (0–255), nebo dle hladiny")
            bv.setMaximumWidth(90)
            bv.clicked.connect(lambda _=False, k=klic: self._vyber_barvu(k))
            sp = QDoubleSpinBox()
            sp.setRange(0.01, 100.0)
            sp.setDecimals(2)
            sp.setSingleStep(0.1)
            try:
                sp.setValue(float(self._nast.value(f"cad/body/{klic}/velikost", round(velikost, 2))))
            except (TypeError, ValueError):
                sp.setValue(round(velikost, 2))
            sp.setMaximumWidth(90)
            sp.setToolTip("Výška textu v metrech výkresu" if klic != "znacka" else
                          "Velikost značky (křížek, kroužek) v metrech; u buňky měřítko")
            self.ch[klic], self.cb[klic], self.hl[klic], self.barvy[klic], self.vel[klic] = ch, cb, hl, bv, sp
            try:
                self._barva_ms = getattr(self, "_barva_ms", {})
                b = int(self._nast.value(f"cad/body/{klic}/barva", 256))
            except (TypeError, ValueError):
                b = 256
            self._nastav_barvu(klic, b)
            for c, w in enumerate((ch, cb, hl, bv, sp)):
                g.addWidget(w, r, c)
            cb.currentIndexChanged.connect(lambda _i, k=klic: self._povol(k))
            ch.toggled.connect(lambda _on, k=klic: self._povol(k))
        self.tvar = QComboBox()
        for t, kod in TVARY.items():
            self.tvar.addItem(t, ("tvar", kod))
        if page.dok is not None:
            for b in sorted(b.name for b in page.dok.doc.blocks if not b.name.startswith(("*", "_"))
                            and not b.is_any_layout and not getattr(b.block, "is_xref", False)):
                self.tvar.addItem(f"buňka {b}", ("bunka", b))
        self.tvar.addItem("buňka z knihovny…", ("knihovna", None))
        self.tvar.setCurrentIndex(max(0, self.tvar.findText(str(self._nast.value("cad/body/tvar", "křížek ×")))))
        self.tvar.activated.connect(self._tvar_vybran)
        self.tvar.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.tvar.setMinimumContentsLength(4)
        self.tvar.setToolTip("Tvar značky bodu (pro celý výkres, jako PDMODE), nebo buňka")
        g.addWidget(QLabel("Tvar:"), len(radky) + 1, 0)
        g.addWidget(self.tvar, len(radky) + 1, 1)
        tip = QLabel(f"Výška textu {odhad:.2f} m je odhad podle hustoty bodů (čísla se nepřekrývají).")
        tip.setWordWrap(True)
        from PySide6.QtWidgets import QSizePolicy
        tip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # zalomený popisek okno nerozšiřuje
        tip.setStyleSheet("color: gray;")
        g.addWidget(tip, len(radky) + 2, 0, 1, 5)
        lay.addWidget(grp)
        for k in self.cb:
            self._povol(k)
        self.cb_spoj = QComboBox()
        self.cb_spoj.addItem("(nevkládat)", None)
        self.cb_spoj.addItem("aktivní atributy", "aktivni")
        for p in self._pv:
            if p.geometrie in ("linie", None) and not p.blok:
                self.cb_spoj.addItem(p.nazev, p)
        self.cb_spoj.setToolTip("Spojnice nakreslené v grafice Výpočtů (mezi vkládanými body) jako úsečky")
        f.addRow("Spojnice z grafiky:", self.cb_spoj)
        self.podle_kodu = QCheckBox("Kód 9.12 → buňka")
        self.podle_kodu.setToolTip("Bod s kódem buňky (např. 9.12) se vloží jako buňka")
        self.podle_kodu.setChecked(True)
        self.preskocit = QCheckBox("Přeskočit body už ve výkresu")
        self.preskocit.setChecked(True)
        self.v3d = QCheckBox("Ve 3D (ve výšce bodu Z)")
        self.v3d.setToolTip("Značky a spojnice ve výšce bodu (Z) – pro 3D výkres a model terénu")
        # dlouhé názvy předvoleb nesmí okno roztáhnout (celý název je v rozbalení)
        for c in (self.zdroj, self.cb_spoj):
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(14)
        f.addRow(self.podle_kodu)
        f.addRow(self.preskocit)
        f.addRow(self.v3d)
        lay.addLayout(f)
        self.info = QLabel()
        lay.addWidget(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Vložit body")
        bb.accepted.connect(self.vlozit)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.vysledek = None
        g.setColumnStretch(1, 3)  # „Podle“ (názvy nástrojů a druhů prvků) dostane volné místo
        g.setColumnStretch(2, 2)
        self.podle_um.toggled.connect(self._prepni_um)
        self._prepni_um(self.podle_um.isChecked())
        self.resize(max(self.sizeHint().width(), 620), self.sizeHint().height())
        self._obnov_info()

    def _zdroj(self, i: int):
        if i == 1:
            from ..geodezie.formaty import nacti_soubor
            path, _ = QFileDialog.getOpenFileName(self, "Seznam souřadnic", "", "Seznam (*.txt *.csv *.xyz);;Vše (*)")
            if not path:
                self.zdroj.setCurrentIndex(0)
                return
            try:
                self._soubor_body, var, _f = nacti_soubor(path)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Body", f"Soubor nejde načíst: {e}")
                self.zdroj.setCurrentIndex(0)
                return
        self._obnov_info()

    def nastav_body(self, body):
        """Body ze souboru (i z testů)."""
        self._soubor_body = list(body)
        self.zdroj.setCurrentIndex(1)
        self._obnov_info()

    def body(self) -> list:
        if self.zdroj.currentIndex() == 1:
            src = list(self._soubor_body or [])
        else:
            v = getattr(self.page.win, "vypocty", None) if self.page.win is not None else None
            src = list(v.seznam.body) if v is not None else []
        t = self.filtr.text().strip()
        if not t or t.lower() in ("vše", "vse"):
            return src
        if t.lower().startswith("kód=") or t.lower().startswith("kod="):
            k = t.split("=", 1)[1].strip()
            return [b for b in src if (b.kod or "") == k]
        out = []
        for cast in re.split(r"[,;\s]+", t):
            if "-" in cast and not cast.startswith("-"):
                a, b = cast.split("-", 1)
                ka, kb = _klic(a.strip()), _klic(b.strip())
                out += [p for p in src if ka <= _klic(p.cislo) <= kb]
            elif cast:
                out += [p for p in src if p.cislo == cast]
        return out

    def _obnov_info(self):
        n = len(self.body())
        self.info.setText(f"Vloží se {n} bodů." if n else "Ve zdroji nejsou žádné body.")

    @staticmethod
    def _nast_um() -> bool:
        from PySide6.QtCore import QSettings
        return QSettings().value("cad/body/podle_um", "true") in (True, "true")

    def _prepni_um(self, on: bool):
        self.grp_atributy.setEnabled(not on)
        self.podle_kodu.setEnabled(not on)

    def nastaveni(self) -> NastaveniBodu:
        from ..cad import symbologie as SY
        from ..cad.zadani import Predvolba
        if self.podle_um.isChecked():
            from ..cad.body_seznam import nastaveni_um
            n = nastaveni_um(self.page.dok.doc, self.page._pravidla(), self.page.anotace)
            n.preskocit_existujici, n.v3d = self.preskocit.isChecked(), self.v3d.isChecked()
            d = self.cb_spoj.currentData()
            n.spojnice = d if d not in (None, "aktivni") else None
            n.spojnice_aktivni = d == "aktivni"
            return n
        n = NastaveniBodu(podle_kodu=self.podle_kodu.isChecked(), preskocit_existujici=self.preskocit.isChecked(),
                          v3d=self.v3d.isChecked())
        rs = self.page._pravidla()
        for klic, cb in self.cb.items():
            if not self.ch[klic].isChecked():
                setattr(n, klic, None)
                continue
            d = cb.currentData()
            if d != "vlastni":
                setattr(n, klic, d)
                continue
            ms = self._barva_ms.get(klic, 256)
            aci = 256 if ms == 256 else SY.ms_na_aci(ms, rs)
            geom = "bod" if klic == "znacka" else "text"
            vrstva = self.hl[klic].currentText().strip() or "0"
            setattr(n, klic, Predvolba(nazev="vlastní", geometrie=geom, nastroj=geom, vrstva=vrstva, barva=aci,
                                       vyska=None if klic == "znacka" else self.vel[klic].value(),
                                       ms={} if ms == 256 else {"barva": ms}))
        if n.znacka is not None and self.cb["znacka"].currentData() == "vlastni":
            druh, hodnota = self.tvar.currentData() or ("tvar", 3)
            if druh == "bunka":
                n.bunka, n.meritko_bunky = hodnota, self.vel["znacka"].value()
            else:
                n.tvar, n.velikost_znacky = int(hodnota), self.vel["znacka"].value()
        n.vyska_textu = self.vel["cislo"].value()
        d = self.cb_spoj.currentData()
        n.spojnice = d if d not in (None, "aktivni") else None
        n.spojnice_aktivni = d == "aktivni"
        return n

    def _uloz_volby(self):
        if self._je_um:
            self._nast.setValue("cad/body/podle_um", self.podle_um.isChecked())
        for k in self.cb:
            self._nast.setValue(f"cad/body/{k}/ano", self.ch[k].isChecked())
            self._nast.setValue(f"cad/body/{k}/podle", self.cb[k].currentText())
            self._nast.setValue(f"cad/body/{k}/hladina", self.hl[k].currentText())
            self._nast.setValue(f"cad/body/{k}/barva", self._barva_ms.get(k, 256))
            self._nast.setValue(f"cad/body/{k}/velikost", self.vel[k].value())
        self._nast.setValue("cad/body/tvar", self.tvar.currentText())

    def _povol(self, klic: str):
        on = self.ch[klic].isChecked()
        vlastni = self.cb[klic].currentData() == "vlastni"
        d = self.cb[klic].currentData()
        self.cb[klic].setToolTip(self.cb[klic].currentText() + (" – " + d.popis() if hasattr(d, "popis") else ""))
        self.cb[klic].setEnabled(on)
        for w in (self.hl[klic], self.barvy[klic], self.vel[klic]):
            w.setEnabled(on and vlastni)
        if klic == "znacka":
            self.tvar.setEnabled(on and vlastni)

    def _nastav_barvu(self, klic: str, ms: int):
        from ..cad import symbologie as SY
        self._barva_ms[klic] = ms
        b = self.barvy[klic]
        if ms == 256:
            b.setText("dle hl.")
            b.setStyleSheet("")
        else:
            r, g_, bl = SY.tabulka(self.page._pravidla()).get(ms, (128, 128, 128))
            svetla = r * 0.3 + g_ * 0.59 + bl * 0.11 > 140
            b.setText(str(ms))
            b.setStyleSheet(f"background: rgb({r},{g_},{bl}); color: {'black' if svetla else 'white'};")

    def _vyber_barvu(self, klic: str):
        from ..cad import symbologie as SY
        from .cad_panely import BarvaDialog
        d = BarvaDialog(SY.tabulka(self.page._pravidla()), self._barva_ms.get(klic), self)
        if d.exec() and d.vysledek is not None:
            self._nastav_barvu(klic, d.vysledek)

    def _tvar_vybran(self, i: int):
        druh, _h = self.tvar.itemData(i) or ("tvar", 0)
        if druh != "knihovna":
            return
        jmena = self.page.knihovna_bunek() or []
        for jm in jmena:
            if self.tvar.findData(("bunka", jm)) < 0:
                self.tvar.insertItem(self.tvar.count() - 1, f"buňka {jm}", ("bunka", jm))
        self.tvar.setCurrentIndex(self.tvar.findData(("bunka", jmena[0])) if jmena else 0)

    def _vsechny_body(self) -> list:
        v = getattr(self.page.win, "vypocty", None) if self.page.win is not None else None
        return list(v.seznam.body) if v is not None else []

    def spojnice(self) -> list:
        v = getattr(self.page.win, "vypocty", None) if self.page.win is not None else None
        if v is None or self.zdroj.currentIndex() == 1:
            return []
        return v.spojnice.platne(v.seznam)

    def vlozit(self):
        pg = self.page
        body = self.body()
        if not body:
            QMessageBox.information(self, "Body", "Nejsou vybrané žádné body.")
            return
        if not pg._je_model():
            pg.nastav_model("Model")
        self._uloz_volby()
        self.vysledek = vloz_body(pg.prostor, pg.historie_zmen, body, self.nastaveni(), self._pv, pg.kresleni,
                                  self.spojnice())
        pg._po_zmene(self.vysledek["prvky"], [])
        pg.sjtsk = True
        pg.view.zoom_all()
        r = self.vysledek
        pg.vypis(f"Vloženo {r['vlozeno']} bodů" + (f", {r['bunky']} jako buňky" if r["bunky"] else "")
                 + (f", přeskočeno {r['preskoceno']} (už ve výkresu)" if r["preskoceno"] else "") + ".")
        self.accept()
