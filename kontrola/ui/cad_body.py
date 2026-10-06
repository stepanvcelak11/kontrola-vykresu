"""Okno „Body ze seznamu“ v CAD: zdroj (seznam projektu / soubor), výběr bodů a předvolby ze zadání."""

from __future__ import annotations

import re

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
                               QLineEdit, QMessageBox, QVBoxLayout)

from ..cad.body_seznam import NastaveniBodu, vloz_body, vychozi_nastaveni


def _klic(c: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", c)]


class BodyDialog(QDialog):
    def __init__(self, page, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("Body ze seznamu souřadnic")
        self._soubor_body = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Body se umístí na své souřadnice (shodně se světem S-JTSK jako v MicroStationu). "
                             "Značka, číslo a výška se zapíšou do hladin a s atributy podle zadání."))
        f = QFormLayout()
        self.zdroj = QComboBox()
        self.zdroj.addItems(["Seznam souřadnic projektu (Výpočty)", "Ze souboru…"])
        self.zdroj.activated.connect(self._zdroj)
        f.addRow("Zdroj:", self.zdroj)
        self.filtr = QLineEdit()
        self.filtr.setPlaceholderText("vše, nebo čísla „1-50, 101“, nebo kód „kód=3.13“")
        f.addRow("Body:", self.filtr)
        self._pv = page._predvolby
        vych = vychozi_nastaveni(self._pv)
        self.cb = {}
        for klic, popis, typy, hodnota in (("znacka", "Značka bodu", ("bod", None), vych.znacka),
                                           ("cislo", "Číslo bodu", ("text",), vych.cislo),
                                           ("vyska", "Výška", ("text",), vych.vyska),
                                           ("kod", "Kód", ("text",), None)):
            cb = QComboBox()
            cb.addItem("(nevkládat)", None)
            for p in self._pv:
                if p.geometrie in typy or (klic == "znacka" and p.blok):
                    cb.addItem(p.nazev, p)
            if klic == "znacka":
                cb.addItem("bod v aktivní hladině", "aktivni")
            else:
                cb.addItem("text v aktivní hladině", "aktivni")
            if hodnota is not None:
                cb.setCurrentIndex(max(0, cb.findText(hodnota.nazev)))
            elif klic in ("znacka", "cislo") and not any(p.geometrie in typy for p in self._pv):
                cb.setCurrentIndex(cb.findData("aktivni"))
            self.cb[klic] = cb
            f.addRow(popis + ":", cb)
        self.cb_spoj = QComboBox()
        self.cb_spoj.addItem("(nevkládat)", None)
        self.cb_spoj.addItem("aktivní atributy", "aktivni")
        for p in self._pv:
            if p.geometrie in ("linie", None) and not p.blok:
                self.cb_spoj.addItem(p.nazev, p)
        self.cb_spoj.setToolTip("Spojnice nakreslené v grafice Výpočtů (mezi vkládanými body) jako úsečky")
        f.addRow("Spojnice z grafiky:", self.cb_spoj)
        self.podle_kodu = QCheckBox("Bod s kódem buňky (např. 9.12) vložit jako buňku")
        self.podle_kodu.setChecked(True)
        self.preskocit = QCheckBox("Přeskočit body, jejichž číslo už ve výkresu je")
        self.preskocit.setChecked(True)
        self.v3d = QCheckBox("Ve 3D – značky a spojnice ve výšce bodu (Z), pro 3D výkres a model terénu")
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

    def nastaveni(self) -> NastaveniBodu:
        n = NastaveniBodu(podle_kodu=self.podle_kodu.isChecked(), preskocit_existujici=self.preskocit.isChecked(),
                          v3d=self.v3d.isChecked())
        for k, cb in self.cb.items():
            d = cb.currentData()
            setattr(n, k, None if d in (None, "aktivni") else d)
        from ..cad.zadani import Predvolba
        k = self.page.kresleni
        for klic in ("znacka", "cislo", "vyska", "kod"):
            if self.cb[klic].currentData() == "aktivni":
                geom = "bod" if klic == "znacka" else "text"
                setattr(n, klic, Predvolba(nazev="aktivní", geometrie=geom, nastroj=geom, vrstva=k.vrstva,
                                           barva=k.barva))
        n.vyska_textu = self.page.vyska_textu
        d = self.cb_spoj.currentData()
        n.spojnice = d if d not in (None, "aktivni") else None
        n.spojnice_aktivni = d == "aktivni"
        return n

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
        self.vysledek = vloz_body(pg.prostor, pg.historie_zmen, body, self.nastaveni(), self._pv, pg.kresleni,
                                  self.spojnice())
        pg._po_zmene(self.vysledek["prvky"], [])
        pg.sjtsk = True
        pg.view.zoom_all()
        r = self.vysledek
        pg.vypis(f"Vloženo {r['vlozeno']} bodů" + (f", {r['bunky']} jako buňky" if r["bunky"] else "")
                 + (f", přeskočeno {r['preskoceno']} (už ve výkresu)" if r["preskoceno"] else "") + ".")
        self.accept()
