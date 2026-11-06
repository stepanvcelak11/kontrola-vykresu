"""Výpočetní okna úloh jako v Gromě 14 (podle snímků G10–G22 a kapitoly „Menu Výpočty“ návodu).

Každá úloha má své okno se stejnými oddíly, popisky a barvami polí jako Groma: Stanovisko / Orientace (tabulka
s opravami a vpravo Předč., Číslo, Směr, Y, X; tlačítka Přidat, Odebrat, Aktualizovat souř.), Měřené hodnoty,
Vypočtené souřadnice (Předč., Číslo, Kód, Kvalita, Y, X, Z a zelené ✓ = uložit do seznamu), dole Nový výpočet,
Protokol, Výpočet. Výpočty samotné jsou v ``kontrola.geodezie.ulohy``."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QPushButton, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)

from .groma_formulare import (BodBox, Prepinac, TabulkaRadku, Volba, body_z_mime, fmt, formular, mereni_z_mime,
                              nadpis, pole, predcisli_listy, rozdel_cislo)

# názvy oken jako v Gromě
TITULKY = {
    "Rajón (polární bod)": "Polární metoda", "Transformace": "Transformace souřadnic",
    "Protínání vpřed ze směrů": "Protínání ze směrů", "Ortogonální metoda (Groma)": "Ortogonální metoda",
    "Polygonový pořad (Groma)": "Polygonový pořad", "Výška stanoviska": "Výpočet výšky stanoviska",
    "Výměra a obvod": "Výpočet výměr", "Průsečíky": "Průsečík přímek", "Vytyčovací prvky": "Polární vytyčovací prvky",
    "Staničení a kolmice": "Ortogonální vytyčovací prvky", "Kontrolní oměrné míry": "Kontrolní oměrné",
    "Kružnicový oblouk": "Rozložení oblouku", "Nivelační zápisník": "Nivelace", "Model terénu a kubatura": "Kubatury",
}
NOVY = {"Rajón (polární bod)": "Nové stanovisko", "Volné stanovisko": "Nové stanovisko",
        "Výška stanoviska": "Nové stanovisko", "Transformace": "Nová transformace",
        "Ortogonální metoda (Groma)": "Nová přímka", "Polygonový pořad (Groma)": "Nový pořad",
        "Výškový pořad": "Nový pořad", "Staničení a kolmice": "Nová přímka"}


class NoveCislo(QWidget):
    """Předč. + Číslo nového (určovaného) bodu; předčíslí se předvyplní z lišty nastavení."""

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.predc = pole("cislo", 90, tip="Předčíslí (k.ú. a ZPMZ)")
        self.predc.setText(predcisli_listy())
        self.cislo = pole("cislo", 70, tip="Číslo určovaného bodu")
        h.addWidget(self.predc, 3)
        h.addWidget(self.cislo, 2)

    def hodnota(self) -> str:
        c = self.cislo.text().strip()
        return (self.predc.text().strip() + c) if c else ""

    def nastav_hodnotu(self, t: str):
        pc, c = rozdel_cislo(str(t))
        self.predc.setText(pc)
        self.cislo.setText(c)

    def text(self) -> str:
        return self.hodnota()

    def setText(self, t: str):  # noqa: N802
        self.nastav_hodnotu(t)

    def clear(self):
        self.cislo.clear()


class Stavitel:
    """Pomůcky pro skládání okna úlohy (oddíly, pole, body, tabulky orientací, výsledky)."""

    def __init__(self, panel):
        self.p = panel
        self.page = panel.page

    # --- pole
    def pole(self, key: str, druh: str, sirka: int = 100, tip: str = "", vychozi: str = ""):
        w = pole(druh, sirka, tip=tip)
        if vychozi:
            w.setText(vychozi)
        if key:
            self.p.inputs[key] = w
        return w

    def bod(self, key: str, **kw) -> BodBox:
        bb = BodBox(self.page, **kw)
        c = QCompleter(self.p._completer_model, bb.cislo)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        c.setFilterMode(Qt.MatchStartsWith)
        bb.cislo.setCompleter(c)
        if key:
            self.p.inputs[key] = bb
            self.p._bodboxy[key] = bb
        return bb

    def volba(self, key: str, polozky: list[str], vychozi: str = "") -> QComboBox:
        w = QComboBox()
        w.addItems(polozky)
        if vychozi:
            w.setCurrentText(vychozi)
        if key:
            self.p.inputs[key] = w
        return w

    def prepinac(self, key: str, text: str, tip: str = "", zapnuto: bool = False) -> Prepinac:
        w = Prepinac(text)
        w.setChecked(zapnuto)
        if tip:
            w.setToolTip(tip)
        if key:
            self.p.inputs[key] = w
        return w

    # --- rozložení
    def oddil(self, titul: str, *obsah, natahnout: bool = False) -> QFrame:
        box = QFrame()
        box.setObjectName("oddil_ulohy")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 8)
        v.setSpacing(5)
        if titul:
            v.addWidget(nadpis(titul))
        for w in obsah:
            if w is None:
                v.addStretch(1)
            elif isinstance(w, QWidget):
                v.addWidget(w, 1 if natahnout else 0)
            else:
                v.addLayout(w)
        return box

    def pridej(self, w, natahnout: int = 0):
        self.p.form.addWidget(w, natahnout)
        return w

    @staticmethod
    def vedle(*widgety, natahnout: tuple = ()) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for i, x in enumerate(widgety):
            if x is None:
                h.addStretch(1)
            elif isinstance(x, QWidget):
                h.addWidget(x, natahnout[i] if i < len(natahnout) else 1)
            else:
                h.addLayout(x)
        return w

    @staticmethod
    def pod(*widgety) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        for x in widgety:
            if x is None:
                v.addStretch(1)
            else:
                v.addWidget(x)
        return w

    def zalozky(self, stranky: list[tuple[str, QWidget]]) -> QTabWidget:
        t = QTabWidget()
        for n, w in stranky:
            t.addTab(w, n)
        self.p.zalozky = t
        return t

    @staticmethod
    def stranka(*obsah) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(6)
        for x in obsah:
            if x is None:
                v.addStretch(1)
            elif isinstance(x, tuple):
                v.addWidget(x[0], x[1])
            else:
                v.addWidget(x)
        return w

    def tlacitko(self, text: str, fn, tip: str = "") -> QPushButton:
        b = QPushButton(text)
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(lambda _c=False: fn())
        return b

    # --- tabulka orientací / identických bodů / lomových bodů
    def tabulka(self, key: str, sloupce: list[str], vstup: int, zadani: list[tuple[str, str, str]] | None = None,
                bod: dict | None = None, mereni=None, body_radek=None, aktualizovat: bool = True):
        """Tabulka se zadáním vpravo (jako Orientace v Gromě). ``zadani`` = [(popisek, druh, tip)] – pole
        za číslem bodu ve stejném pořadí jako sloupce 1…vstup-1. ``mereni(m) → řádek`` převede přetaženou
        záměru ze zápisníku, ``body_radek(číslo) → řádek`` přetažený bod."""
        tab = TabulkaRadku(sloupce, vstup)
        self.p.inputs[key] = tab
        bb = self.bod("", rozlozeni="pod", **(bod or {}))
        pole_ = [(t, pole(d, 90, tip=tip)) for t, d, tip in (zadani or [])]
        prava = QWidget()
        pl = QVBoxLayout(prava)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        pl.addWidget(bb)
        if pole_:
            pl.addWidget(formular(pole_, nahoru=False))
        pl.addStretch(1)

        def pridat():
            c = bb.hodnota()
            if not c:
                self.p.chyba.setText("<span style='color:#B45309'>Vyplňte číslo bodu (nebo bod přetáhněte).</span>")
                return
            r = bb.rucni_bod()
            if r is not None:
                self.p._rucni[r.cislo] = r
            tab.pridej([c] + [w.text().strip() for _t, w in pole_])
            bb.vymaz()
            for _t, w in pole_:
                w.clear()
            self.p.chyba.clear()

        def drop(md):
            sth, mer = mereni_z_mime(md)
            if mer and mereni is not None:
                if sth is not None and getattr(tab, "pri_stanovisku", None):
                    tab.pri_stanovisku(sth)
                for m in mer:
                    tab.pridej(mereni(m))
                return True
            for c, *_r in body_z_mime(md):
                tab.pridej(body_radek(c) if body_radek else [c])
            return True
        tab.pri_pretazeni = drop
        tl = [self.tlacitko("Přidat", pridat), self.tlacitko("Odebrat", tab.odeber)]
        if aktualizovat:
            tl.append(self.tlacitko("Aktualizovat souř.", lambda: self._aktualizuj(),
                                    "Souřadnice bodů znovu ze seznamu souřadnic (po jeho změně)"))
        levy = self.pod(tab, self.vedle(*tl, None))
        tab.setMinimumHeight(120)
        celek = self.vedle(levy, prava, natahnout=(3, 2))
        tab.zadani_bod, tab.zadani_pole, tab.pridat = bb, pole_, pridat
        return tab, celek

    def _aktualizuj(self):
        for bb in self.p._bodboxy.values():
            bb._dopln()
        self.p.chyba.setText("<span style='color:#16A34A'>✓ Souřadnice aktualizovány ze seznamu.</span>")

    # --- výsledky
    def vysledek(self, titul: str = "Vypočtené souřadnice:", nove: str = "nove", z: bool = True,
                 kod: bool = True, kvalita: bool = True, vlevo: list | None = None, cislo: bool = True) -> tuple:
        """Oddíl s určovaným bodem: Předč./Číslo/Kód/Kvalita vlevo, Y/X/Z (jen ke čtení) vpravo, zelené ✓."""
        from .groma_formulare import tint
        lev = []
        if cislo:
            nc = NoveCislo()
            if nove:
                self.p.inputs[nove] = nc
            lev.append(("Číslo:", nc))
        if kod:
            lev.append(("Kód:", self.pole("kod", "kod", 80)))
        if kvalita:
            kv = QComboBox()
            kv.addItems([""] + [str(i) for i in range(1, 9)])
            kv.setStyleSheet(f"QComboBox {{ background: {tint('cislo')}; color: #111827; }}")
            kv.setMaximumWidth(56)
            self.p._kvalita_nove = kv
            lev.append(("Kvalita:", kv))
        lev += list(vlevo or [])
        vys = {k: pole("sour", 110, True) for k in ("y", "x", "z")}
        prav = [("Y:", vys["y"]), ("X:", vys["x"])] + ([("Z:", vys["z"])] if z else [])
        ok = QToolButton()
        ok.setText("✓")
        ok.setObjectName("ulozit_vysledek")
        ok.setToolTip("Uložit vypočtené souřadnice do seznamu souřadnic")
        ok.setMinimumSize(30, 54)
        ok.clicked.connect(lambda: self.p.pridej())
        ok.setEnabled(False)
        self.p._tlacitka_ulozit.append(ok)
        self.p._ma_ulozeni = True
        w = self.vedle(formular(lev), formular(prav), ok, natahnout=(3, 3, 0))
        return self.oddil(titul, w), vys

    def vypln(self, vys: dict, bod):
        c, y, x, zz = bod if bod else ("", None, None, None)
        vys["y"].setText(fmt(y))
        vys["x"].setText(fmt(x))
        vys["z"].setText(fmt(zz))

    def po(self, fn):
        self.p._po_vypoctu = fn

    def poznamka(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setObjectName("poznamka")
        return lbl


# ====================================================================== okna úloh
def _mereni_orient(m):
    return [m["bod"], f"{m['hz']:.4f}", f"{m['d']:.3f}"]


def polarni(s: Stavitel):
    """G10 Polární metoda: záložky Stanovisko (stanovisko + orientace) a Určovaný bod."""
    vp = s.pole("vp", "vys", 80, "Výška stroje nad stabilizací [m]")
    st = s.bod("st", kvalita=True, vlevo=[("Výška stroje:", vp)])
    tab, orient = s.tabulka("orientace", ["Bod", "Směr", "Délka", "V or.", "V délky"], 3,
                            [("Směr:", "mer", "Měřený vodorovný směr [gon]"),
                             ("Vod. délka:", "mer", "Vodorovná délka na orientaci [m] (nepovinné)")],
                            mereni=_mereni_orient)

    def na_st(sth):
        if not st.hodnota():
            st.nastav_hodnotu(sth[0])
            vp.setText(f"{sth[1]:.3f}")
    tab.pri_stanovisku = na_st
    # rozepsaná orientace v polích jde při výpočtu do tabulky (aby u ní byly vidět opravy)
    s.p._pred_vypoctem = lambda: tab.pridat() if tab.zadani_bod.hodnota() and tab.zadani_pole[0][1].text() else None
    s.p.inputs["o"] = tab.zadani_bod
    s.p.inputs["so"] = tab.zadani_pole[0][1]
    s.p.inputs["od"] = tab.zadani_pole[1][1]
    s.p._bodboxy["o"] = tab.zadani_bod
    str1 = s.stranka(s.oddil("Stanovisko:", st), (s.oddil("Orientace:", orient, natahnout=True), 1))
    sm = s.pole("sm", "mer", 100, "Měřený vodorovný směr [gon]")
    d = s.pole("d", "mer", 100, "Délka [m] – vodorovná; se zenitovým úhlem šikmá")
    dh = s.pole("dh", "vys", 100, "Převýšení [m] (terén – terén, bez zenitového úhlu)")
    zen = s.pole("zenit", "vys", 100, "Zenitový úhel [gon] – délka je pak šikmá")
    vc = s.pole("vc", "vys", 100, "Výška signálu (cíle) [m]")
    mer = s.oddil("Měřené hodnoty:", s.vedle(
        s.pod(s.poznamka("Záměry přetáhněte myší ze Seznamu měření – bod se hned spočítá (víc označených "
                         "záměr = víc bodů najednou)."), None),
        formular([("Směr:", sm), ("Délka:", d), ("Převýšení:", dh), ("Zenitový úhel:", zen),
                  ("Výška signálu:", vc)])))
    volby = s.pod(s.prepinac("ze_smerniku", "Výpočet ze směrníků",
                             "Směr je přímo směrník (jižník) na bod – orientace osnovy není potřeba"),
                  s.prepinac("bodove_pole", "Výpočet pro bodové pole",
                             "Bod se spočte s každým orientačním směrem zvlášť, výsledek je průměr"))
    vysl, vys = s.vysledek()
    str2 = s.stranka(mer, volby, vysl, None)
    s.pridej(s.zalozky([("Stanovisko", str1), ("Určovaný bod", str2)]), 1)
    s.p._pri_pretazeni_mereni = s.p._polarni_drop

    def po(v):
        o = v.data.get("orientace") if v else None
        if o:
            tab.nastav_vysledky({k: [a, b] for k, (a, b) in o.items()})
        s.vypln(vys, v.data.get("bod") if v else None)
    s.po(po)


def volne(s: Stavitel):
    """G15 Volné stanovisko."""
    tab, orient = s.tabulka(
        "mereni", ["Bod", "Směr", "Délka", "Zenit", "Výška sig.", "V or.", "V délky", "V přev."], 5,
        [("Směr:", "mer", "Měřený vodorovný směr [gon]"), ("Délka:", "mer", "Délka [m] – se zenitem šikmá"),
         ("Zenitový úhel:", "vys", "Zenitový úhel [gon] (pak se spočte i výška)"),
         ("Výška signálu:", "vys", "Výška signálu (cíle) [m]")],
        mereni=lambda m: [m["bod"], f"{m['hz']:.4f}", f"{m['sd']:.3f}", f"{m['z']:.4f}", f"{m['vc']:.3f}"])
    vyp = s.volba("vypocet", ["Podobnostní transformace", "Shodnostní transformace",
                              "Vyrovnání jako vázaná síť (MNČ)"])
    vyp.setToolTip("Podobnostní = se změnou měřítka, shodnostní = bez změny měřítka, vázaná síť = vyrovnání MNČ "
                   "podle středních chyb směrů a délek (Nastavení → Teodolit)")
    s.pridej(s.oddil("Orientace:", orient, s.vedle(QLabel("Výpočet:"), vyp, None, natahnout=(0, 2, 1)),
                     natahnout=True), 1)
    vp = s.pole("vp", "vys", 80, "Výška stroje [m] – pro výšku stanoviska ze zenitových úhlů")

    def na_st(sth):
        if not s.p.inputs["nove"].hodnota():
            s.p.inputs["nove"].nastav_hodnotu(sth[0])
        vp.setText(f"{sth[1]:.3f}")
    tab.pri_stanovisku = na_st
    vysl, vys = s.vysledek(vlevo=[("Výška stroje:", vp)])
    s.pridej(vysl)

    def po(v):
        if v:
            tab.nastav_vysledky(v.data.get("opravy", {}))
        s.vypln(vys, v.data.get("bod") if v else None)
    s.po(po)


def transformace(s: Stavitel):
    """G17 Transformace souřadnic."""
    cil = s.bod("", z=False)
    mis = s.bod("", z=False)
    tab = TabulkaRadku(["Bod", "Y cíl", "X cíl", "dY", "dX", "dP"], 3)
    s.p.inputs["identicke"] = tab

    def pridat():
        c = mis.hodnota()
        sc = cil.souradnice()
        if not c or sc is None:
            s.p.chyba.setText("<span style='color:#B45309'>Vyplňte místní bod a cílové souřadnice Y, X.</span>")
            return
        rb = mis.rucni_bod()
        if rb is not None:
            s.p._rucni[rb.cislo] = rb
        tab.pridej([c, f"{sc[0]:.3f}", f"{sc[1]:.3f}"])
        cil.vymaz()
        mis.vymaz()
    levy = s.pod(nadpis("Cílové souřadnice:"), cil, nadpis("Místní souřadnice:"), mis, None)
    prava = s.pod(tab, s.vedle(s.tlacitko("Přidat", pridat), s.tlacitko("Odebrat", tab.odeber)))
    s.pridej(s.oddil("Identické body:", s.vedle(levy, prava, natahnout=(2, 3)), natahnout=True), 1)
    typ = Volba(["Shodnostní", "Podobnostní", "Afinní"], "Podobnostní")
    s.p.inputs["druh"] = typ
    pre = s.pole("predpona", "cislo", 60, "Předpona čísel transformovaných bodů", "T")
    volby = s.pod(s.prepinac("jung", "Jungova dotransformace", "Rozdělí opravy z identických bodů na transformované "
                                                                "body (váhy 1/d²)"),
                  formular([("Předpona čísel:", pre)], nahoru=False))
    s.pridej(s.vedle(s.oddil("Typ transformace:", typ), s.oddil("Volby:", volby), natahnout=(1, 2)))
    from .ulohy import _Radky
    tr = _Radky()
    tr.setPlaceholderText("Čísla bodů k transformaci – přetáhněte je ze seznamu souřadnic")
    tr.setMinimumHeight(64)
    s.p.inputs["transformovat"] = tr
    bv = s.tlacitko("Všechny body seznamu", lambda: tr.setPlainText("\n".join(
        b.cislo for b in s.page.seznam.body if b.cislo not in {r[0] for r in tab.radky()})))
    s.pridej(s.oddil("Transformovat body:", tr, s.vedle(bv, None, natahnout=(0, 1))))
    s.po(lambda v: tab.nastav_vysledky(v.data.get("opravy", {})) if v else None)


def smernik(s: Stavitel):
    """Směrník a délka: počáteční a koncový bod (s výškami i prostorová délka, sklon a spád)."""
    s.pridej(s.oddil("Počáteční bod:", s.bod("a", kvalita=False)))
    s.pridej(s.oddil("Koncový bod:", s.bod("b", kvalita=False)))
    v = {k: pole("mer" if k in ("smernik", "delka") else "vys", 120, True)
         for k in ("smernik", "delka", "prevyseni", "prostorova", "sklon", "spad")}
    s.pridej(s.oddil("Výsledky:", s.vedle(
        formular([("Směrník [g]:", v["smernik"]), ("Délka [m]:", v["delka"])]),
        formular([("Převýšení [m]:", v["prevyseni"]), ("Prostorová délka [m]:", v["prostorova"]),
                  ("Sklon [°]:", v["sklon"]), ("Spád [%]:", v["spad"])]))))
    s.pridej(s.poznamka("Prostorová délka, sklon a spád se spočtou, když mají oba body výšku."))
    s.p.form.addStretch(1)

    def po(r):
        d = r.data if r else {}
        for k, w in v.items():
            x = d.get(k)
            w.setText("" if x is None else f"{x:.4f}" if k in ("smernik", "sklon") else f"{x:.2f}" if k == "spad"
                      else f"{x:.3f}")
    s.po(po)


def ortogonalni(s: Stavitel):
    """G11 Ortogonální metoda: identické body se staničením a kolmicí, měřené hodnoty, vypočtené souřadnice."""
    tab, ident = s.tabulka("identicke", ["Bod", "Staničení", "Kolmice", "dY", "dX", "dP"], 3,
                           [("Staničení:", "mer", "Staničení identického bodu [m]"),
                            ("Kolmice:", "mer", "Kolmice identického bodu [m] (kladná vpravo)")],
                           bod={"kvalita": True}, body_radek=lambda c: [c, "", "0"])
    oprava = pole("mer", 90, True)
    s.pridej(s.oddil("Identické body:", ident, s.vedle(QLabel("Oprava délky mezi 1. a 2. identickým bodem:"),
                                                       oprava, None, natahnout=(0, 1, 1)), natahnout=True), 1)
    st = s.pole("st", "mer", 100, "Staničení určovaného bodu [m]")
    kol = s.pole("kol", "mer", 100, "Kolmice určovaného bodu [m] (kladná vpravo)")
    s.pridej(s.oddil("Měřené hodnoty:", formular([("Staničení:", st), ("Kolmice:", kol)])))
    vysl, vys = s.vysledek(z=False)
    s.pridej(vysl)

    def po(v):
        if v:
            tab.nastav_vysledky(v.data.get("opravy", {}))
            oprava.setText(f"{v.data.get('oprava_delky', 0):.3f}")
        s.vypln(vys, v.data.get("bod") if v else None)
    s.po(po)


def _orientace_stanoviska(s: Stavitel, klic_st: str, klic_or: str):
    st = s.bod(klic_st, z=False)
    tab, orient = s.tabulka(klic_or, ["Bod", "Směr", "V or."], 2,
                            [("Směr:", "mer", "Měřený vodorovný směr na orientaci [gon]")],
                            bod={"z": False}, mereni=lambda m: [m["bod"], f"{m['hz']:.4f}"])
    tab.pri_stanovisku = lambda sth: st.nastav_hodnotu(sth[0]) if not st.hodnota() else None
    return st, tab, s.stranka(s.oddil("Stanovisko:", st), (s.oddil("Orientace:", orient, natahnout=True), 1))


def protinani_smery(s: Stavitel):
    """G12 Protínání ze směrů: záložky Stanovisko A / Stanovisko B, určovaný bod se směry z A a z B."""
    _a, ta, pa = _orientace_stanoviska(s, "a", "ora")
    _b, tb, pb = _orientace_stanoviska(s, "b", "orb")
    s.pridej(s.zalozky([("Stanovisko A", pa), ("Stanovisko B", pb)]), 1)
    sa = s.pole("sa", "mer", 100, "Měřený směr ze stanoviska A na určovaný bod [gon]")
    sb = s.pole("sb", "mer", 100, "Měřený směr ze stanoviska B na určovaný bod [gon]")
    vysl, vys = s.vysledek("Určovaný bod:", z=False, vlevo=[("Směr z A:", sa), ("Směr z B:", sb)])
    s.pridej(vysl)

    def po(v):
        if v:
            ta.nastav_vysledky(v.data.get("ora", {}))
            tb.nastav_vysledky(v.data.get("orb", {}))
        s.vypln(vys, v.data.get("bod") if v else None)
    s.po(po)


def z_delek(s: Stavitel):
    """G13 Protínání z délek: levé a pravé stanovisko (při pohledu k určovanému bodu) s délkami."""
    da = s.pole("da", "mer", 90, "Délka z levého stanoviska [m]")
    db = s.pole("db", "mer", 90, "Délka z pravého stanoviska [m]")
    la = s.bod("a", z=False, kvalita=True, rozlozeni="pod", vpravo=[("Délka:", da)])
    pb = s.bod("b", z=False, kvalita=True, rozlozeni="pod", vpravo=[("Délka:", db)])
    s.p.inputs["strana"] = _Pevne("vlevo")
    s.pridej(s.vedle(s.oddil("Levé stanovisko:", la), s.oddil("Pravé stanovisko:", pb)))
    vysl, vys = s.vysledek("Určovaný bod:", z=False)
    s.pridej(vysl)
    s.pridej(s.poznamka("Levé a pravé stanovisko se berou při pohledu ze stanovisek směrem k určovanému bodu."))
    s.p.form.addStretch(1)
    s.po(lambda v: s.vypln(vys, v.data.get("bod") if v else None))


class _Pevne:
    """Pevná hodnota pole, které v okně Gromy není (např. strana u protínání z délek)."""

    def __init__(self, t: str):
        self.t = t

    def hodnota(self) -> str:
        return self.t

    def nastav_hodnotu(self, t: str):
        self.t = t


def prusecik_primek(s: Stavitel):
    """Průsečík přímek: dvě přímky dané koncovými body, s odsazením (± tlačítkem)."""
    s.p.inputs["druh"] = _Pevne("dvou přímek")
    rad = []
    for titul, k1, k2, ko in (("První přímka:", "a", "b", "o1"), ("Druhá přímka:", "c", "d", "o2")):
        o = s.pole(ko, "mer", 80, "Odsazení přímky [m] – vlevo od směru počátek→konec záporné")
        pm = s.tlacitko("±", lambda w=o: w.setText(w.text()[1:] if w.text().startswith("-") else
                                                  ("-" + w.text() if w.text() else "")), "Změnit znaménko odsazení")
        pm.setMaximumWidth(30)
        rad.append(s.oddil(titul, nadpis("Počáteční bod"), s.bod(k1, kvalita=False), nadpis("Koncový bod"),
                           s.bod(k2, kvalita=False), s.vedle(QLabel("Odsazení:"), o, pm, None, natahnout=(0, 1, 0, 2))))
    s.pridej(s.vedle(*rad))
    vysl, vys = s.vysledek("Průsečík:")
    s.pridej(vysl)
    s.p.form.addStretch(1)
    s.po(lambda v: s.vypln(vys, v.data.get("bod") if v else None))


def prusecik_smer(s: Stavitel):
    """Průsečík přímka – směr: stanovisko s orientací (jako polární metoda) a přímka A–B."""
    vp = s.pole("vp", "vys", 80, "Výška stroje [m]")
    st = s.bod("st", vlevo=[("Výška stroje:", vp)])
    tab, orient = s.tabulka("orientace", ["Bod", "Směr", "Délka", "V or.", "V délky"], 3,
                            [("Směr:", "mer", "Měřený směr na orientaci [gon]"),
                             ("Vod. délka:", "mer", "Vodorovná délka na orientaci [m] (nepovinné)")],
                            mereni=_mereni_orient)
    tab.pri_stanovisku = lambda sth: st.nastav_hodnotu(sth[0]) if not st.hodnota() else None
    str1 = s.stranka(s.oddil("Stanovisko:", st), (s.oddil("Orientace:", orient, natahnout=True), 1))
    sm = s.pole("sm", "mer", 100, "Měřený směr na určovaný bod [gon]")
    zen = s.pole("zenit", "vys", 100, "Zenitový úhel [gon] – pro výšku průsečíku")
    str2 = s.stranka(s.oddil("Přímka:", nadpis("Bod A"), s.bod("a", kvalita=False), nadpis("Bod B"),
                             s.bod("b", kvalita=False)),
                     s.oddil("Měřené hodnoty:", formular([("Směr:", sm), ("Zenitový úhel:", zen)], nahoru=False)),
                     None)
    s.pridej(s.zalozky([("Stanovisko", str1), ("Přímka a směr", str2)]), 1)
    vysl, vys = s.vysledek("Průsečík:")
    s.pridej(vysl)

    def po(v):
        if v:
            tab.nastav_vysledky({k: list(x) for k, x in v.data.get("orientace", {}).items()})
        s.vypln(vys, v.data.get("bod") if v else None)
    s.po(po)


def prusecik_kruznice(s: Stavitel):
    """Průsečík přímka – kružnice: kružnice třemi body, přímka dvěma body, volba řešení."""
    kr = s.oddil("Kružnice:", *[w for i, k in enumerate(("k1", "k2", "k3"), 1)
                                for w in (nadpis(f"{i}. bod"), s.bod(k, z=False))])
    pr = s.oddil("Přímka:", nadpis("Bod A"), s.bod("a", z=False), nadpis("Bod B"), s.bod("b", z=False),
                 s.vedle(QLabel("Řešení:"), s.volba("reseni", ["1", "2"]), None, natahnout=(0, 0, 1)))
    s.pridej(s.vedle(kr, s.pod(pr, None)))
    vysl, vys = s.vysledek("Průsečík:", z=False)
    s.pridej(vysl)
    s.p.form.addStretch(1)
    s.po(lambda v: s.vypln(vys, v.data.get("bod") if v else None))


def na_primku(s: Stavitel):
    """Vyrovnání na přímku: pata kolmice z bodu na přímku."""
    s.pridej(s.vedle(s.oddil("Počáteční bod přímky:", s.bod("a", kvalita=False)),
                     s.oddil("Koncový bod přímky:", s.bod("b", kvalita=False))))
    vzd = pole("mer", 100, True)
    s.pridej(s.oddil("Vyrovnávaný bod:", s.bod("p", kvalita=False),
                     s.vedle(QLabel("Vzdálenost od přímky:"), vzd, None, natahnout=(0, 1, 2))))
    vysl, vys = s.vysledek()
    s.pridej(vysl)
    s.p.form.addStretch(1)

    def po(v):
        s.vypln(vys, v.data.get("bod") if v else None)
        vzd.setText(f"{v.data['vzdalenost']:.3f}" if v else "")
    s.po(po)


def na_kruznici(s: Stavitel):
    """Vyrovnání na kružnici: středový průmět bodu na kružnici danou třemi body."""
    s.pridej(s.oddil("Kružnice:", s.vedle(*[s.pod(nadpis(f"{i}. bod"), s.bod(k, z=False, rozlozeni="pod"))
                                            for i, k in enumerate(("k1", "k2", "k3"), 1)])))
    vzd = pole("mer", 100, True)
    s.pridej(s.oddil("Vyrovnávaný bod:", s.bod("p", kvalita=False),
                     s.vedle(QLabel("Vzdálenost od kružnice:"), vzd, None, natahnout=(0, 1, 2))))
    vysl, vys = s.vysledek()
    s.pridej(vysl)
    s.p.form.addStretch(1)

    def po(v):
        s.vypln(vys, v.data.get("bod") if v else None)
        vzd.setText(f"{v.data['vzdalenost']:.3f}" if v else "")
    s.po(po)


def vyrovnavaci(s: Stavitel, kruznice: bool):
    """Vyrovnávací přímka / kružnice: definiční body (přetažením), vzdálenosti od přímky / kružnice."""
    pouzit = Prepinac("Použít přidávaný bod pro určení " + ("kružnice" if kruznice else "přímky"))
    pouzit.setChecked(True)
    tab = TabulkaRadku(["Bod", "Definiční", "Vzdálenost"], 2)
    s.p.inputs["body"] = tab
    bb = s.bod("", z=False)

    def pridat(c=None):
        c = c or bb.hodnota()
        if c:
            tab.pridej([c, "1" if pouzit.isChecked() else "0"])
            bb.vymaz()
            s.p.vypocitej()
    tab.pri_pretazeni = lambda md: [pridat(c) for c, *_r in body_z_mime(md)] or True
    levy = s.pod(tab, s.vedle(s.tlacitko("Přidat", pridat), s.tlacitko("Odebrat", tab.odeber), None))
    s.pridej(s.oddil("Definiční body:", s.vedle(levy, s.pod(bb, pouzit, None), natahnout=(3, 2)), natahnout=True), 1)
    vse = s.prepinac("vse", "Vyrovnat i body nepoužité pro určení " + ("kružnice" if kruznice else "přímky"),
                     zapnuto=True)
    pre = s.pole("predpona", "cislo", 60, "Předpona čísel průmětů bodů", "P")
    radky = [("Předpona průmětů:", pre)]
    vys = {}
    if kruznice:
        radky = [("Pevný poloměr [m]:", s.pole("r", "mer", 90, "Prázdné = poloměr se vyrovná")),
                 ("Číslo středu:", s.pole("stred", "cislo", 90))] + radky
        vys = {k: pole("sour", 110, True) for k in ("y", "x", "r")}
        par = s.oddil("Parametry kružnice:", formular([("Střed Y:", vys["y"]), ("Střed X:", vys["x"]),
                                                      ("Poloměr:", vys["r"])], nahoru=False))
    else:
        vys = {k: pole("sour", 110, True) for k in ("y1", "x1", "y2", "x2")}
        par = s.oddil("Koncové body vyrovnávací přímky:", formular(
            [("Y:", vys["y1"]), ("X:", vys["x1"]), ("Y:", vys["y2"]), ("X:", vys["x2"])], nahoru=False))
    s.pridej(s.vedle(s.oddil("Volby:", vse, formular(radky, nahoru=False)), par))

    def po(v):
        if not v:
            return
        tab.nastav_vysledky(v.data.get("opravy", {}))
        if kruznice:
            y, x, r = v.data["stred"]
            vys["y"].setText(f"{y:.3f}")
            vys["x"].setText(f"{x:.3f}")
            vys["r"].setText(f"{r:.3f}")
        else:
            k1, k2 = v.data["koncove"]
            for k, val in (("y1", k1.y), ("x1", k1.x), ("y2", k2.y), ("x2", k2.x)):
                vys[k].setText(f"{val:.3f}")
    s.po(po)


def kontrolni_omerne(s: Stavitel):
    """Kontrolní oměrné: body postupně s měřenou vzdáleností od předchozího bodu."""
    tab = TabulkaRadku(["Bod", "Měřená oměrná"], 2)
    bb = s.bod("", z=False, kvalita=True)
    om = pole("mer", 90, tip="Měřená vzdálenost od předchozího bodu [m] (prázdná nebo 0 = nelze měřit)")
    zs = pole("mer", 90, True, "Vzdálenost od předchozího bodu ze souřadnic")

    def predchozi():
        if tab.rowCount() and bb.souradnice():
            b = s.page.seznam.najdi(tab.item(tab.rowCount() - 1, 0).text())
            sc = bb.souradnice()
            if b is not None:
                import math
                zs.setText(f"{math.hypot(sc[0] - b.y, sc[1] - b.x):.2f}")
    bb.zmena.connect(predchozi)

    def pridat():
        if bb.hodnota():
            tab.pridej([bb.hodnota(), om.text().strip()])
            bb.vymaz()
            om.clear()
            zs.clear()
            bb.cislo.setFocus()
    om.returnPressed.connect(pridat)
    tab.pri_pretazeni = lambda md: [tab.pridej([c, ""]) for c, *_r in body_z_mime(md)] or True
    levy = s.pod(tab, s.vedle(s.tlacitko("Přidat", pridat), s.tlacitko("Odebrat", tab.odeber),
                              s.tlacitko("Aktualizovat souř.", lambda: None), None))
    prava = s.pod(bb, formular([("Oměrná:", om), ("Ze souřadnic:", zs)], nahoru=False), None)
    s.pridej(s.oddil("Oměrné:", s.vedle(levy, prava, natahnout=(3, 2)), natahnout=True), 1)
    kk = s.prepinac("", "Použít kód kvality z lišty nastavení", zapnuto=True)
    s.pridej(s.oddil("Volby:", kk))

    class _Miry:
        def hodnota(self):
            r = tab.radky()
            out = []
            for (a, _x), (b, m) in zip(r, r[1:]):
                if m and float(m.replace(",", ".") or 0) > 0:
                    out.append(f"{a} {b} {m}")
            return "\n".join(out)

        def nastav_hodnotu(self, t):
            tab.nastav_hodnotu(t)
    s.p.inputs["miry"] = _Miry()

    class _KK:
        def hodnota(self):
            from ..geodezie.nastaveni import aktualni
            return str(aktualni().kod_kvality)

        def nastav_hodnotu(self, t):
            pass
    s.p.inputs["kk"] = _KK()


def konstrukcni(s: Stavitel):
    """Konstrukční oměrné: body obrazce s oměrnými (+ vpravo, − vlevo), umístění transformací."""
    tab, obr = s.tabulka("mereni", ["Bod", "Oměrná"], 2, [("Oměrná:", "mer", "Oměrná od předchozího bodu [m] – "
                                                                           "kladná vpravo, záporná vlevo")],
                         body_radek=lambda c: [c, ""])
    tab.zadani_pole[0][1].returnPressed.connect(tab.pridat)
    s.pridej(s.oddil("Zaměřené body:", obr, natahnout=True), 1)
    s.pridej(s.oddil("Volby:", s.vedle(QLabel("Transformace:"), s.volba("druh", ["shodnostní", "podobnostní"]),
                                       s.prepinac("jen_nove", "Označit pouze nově určené body", zapnuto=True), None,
                                       natahnout=(0, 1, 1, 1))))
    s.pridej(s.poznamka("Mezi body musí být aspoň dva body o známých souřadnicích. Stejný první a poslední bod = "
                        "uzavřený obrazec (uzávěr se rozdělí)."))


def polygon(s: Stavitel):
    """G16 Polygonový pořad: Počáteční bod, Koncový bod, Měřená data, Výsledky, Nastavení."""
    stranky = []
    for kl_st, kl_or, titul in (("a", "ora", "Počáteční bod"), ("b", "orb", "Koncový bod")):
        st = s.bod(kl_st)
        tab, orient = s.tabulka(kl_or, ["Bod", "Směr", "Délka", "V or.", "V délky"], 3,
                                [("Směr:", "mer", "Měřený směr na orientaci [gon]"),
                                 ("Délka:", "mer", "Délka na orientaci [m] (nepovinné)")], mereni=_mereni_orient)
        tab.pri_stanovisku = lambda sth, st=st: st.nastav_hodnotu(sth[0]) if not st.hodnota() else None
        stranky.append((titul, s.stranka(s.oddil("Stanovisko:", st),
                                         (s.oddil("Orientace:", orient, natahnout=True), 1))))
    # měřená data
    tab = TabulkaRadku(["Bod", "Směr zpět", "Délka zpět", "Směr vpřed", "Délka vpřed"], 5)
    s.p.inputs["mereni"] = tab
    bb = s.bod("", z=False)
    zp = {k: pole(d, 90) for k, d in (("sz", "mer"), ("dz", "mer"))}
    vp = {k: pole(d, 90) for k, d in (("sv", "mer"), ("dv", "mer"))}

    def pridat():
        if bb.hodnota():
            tab.pridej([bb.hodnota(), zp["sz"].text(), zp["dz"].text(), vp["sv"].text(), vp["dv"].text()])
            bb.vymaz()
            for w in list(zp.values()) + list(vp.values()):
                w.clear()

    def drop(md):
        sth, mer = mereni_z_mime(md)
        if sth is None or len(mer) < 1:
            for c, *_r in body_z_mime(md):
                tab.pridej([c, "", "", "", ""])
            return True
        # stanovisko pořadu: první záměra = zpět, poslední = vpřed (jako při měření pořadu)
        z, v = mer[0], mer[-1]
        tab.pridej([sth[0], f"{z['hz']:.4f}", f"{z['d']:.3f}", f"{v['hz']:.4f}" if len(mer) > 1 else "",
                    f"{v['d']:.3f}" if len(mer) > 1 else ""])
        return True
    tab.pri_pretazeni = drop
    stranky.append(("Měřená data", s.stranka((s.vedle(
        s.pod(tab, s.vedle(s.tlacitko("Přidat", pridat), s.tlacitko("Odebrat", tab.odeber), None)),
        s.pod(s.oddil("Stanovisko:", bb), s.vedle(
            s.oddil("Měření zpět:", formular([("Směr:", zp["sz"]), ("Délka:", zp["dz"])], nahoru=False)),
            s.oddil("Měření vpřed:", formular([("Směr:", vp["sv"]), ("Délka:", vp["dv"])], nahoru=False))), None),
        natahnout=(2, 3)), 1), s.poznamka("Do měřených dat patří i počáteční a koncový bod. Stanovisko jde "
                                          "přetáhnout ze zápisníku (záměry zpět a vpřed)."))))
    # výsledky
    typ = pole("cislo", 220, True)
    vt = TabulkaRadku(["Bod", "Y", "X", "Z"], 0)
    uz = {k: pole("mer", 110, True) for k in ("uhl", "xy", "pol", "vys")}
    stranky.append(("Výsledky", s.stranka(
        s.vedle(QLabel("Typ pořadu:"), typ, QLabel("Vyrovnání:"), s.volba("vyrovnani", ["Klasicky"]), None,
                natahnout=(0, 2, 0, 1, 1)),
        (s.vedle(vt, s.pod(formular([("Úhlový uzávěr:", uz["uhl"]), ("Odchylka X/Y:", uz["xy"]),
                                     ("Polohová odchylka:", uz["pol"]), ("Výškový uzávěr:", uz["vys"])],
                                    nahoru=False), None), natahnout=(3, 2)), 1))))
    stranky.append(("Nastavení, Vst./Výstupy", s.stranka(
        s.oddil("Typ pořadu pro mezní odchylky:", s.poznamka(
            "Mezní odchylky pořadu se řídí třídou v Nastavení výpočtů (Soubor → Nastavení → Tolerance).")), None)))
    s.pridej(s.zalozky(stranky), 1)
    s.p._ma_ulozeni = False

    def po(v):
        vt.setRowCount(0)
        if not v:
            typ.clear()
            return
        typ.setText(v.data.get("typ", ""))
        for b in v.nove:
            vt.pridej([b.cislo, f"{b.y:.3f}", f"{b.x:.3f}", "" if b.z is None else f"{b.z:.3f}"])
        import re
        txt = "\n".join(v.protokol)
        m = re.search(r"úhlová odchylka (-?\d+) cc", txt)
        uz["uhl"].setText(f"{m.group(1)} cc" if m else "")
        m = re.search(r"dY = (-?[\d.]+) m, dX = (-?[\d.]+) m, polohová ([\d.]+)", txt)
        uz["xy"].setText(f"{m.group(2)} / {m.group(1)}" if m else "")
        uz["pol"].setText(m.group(3) if m else "")
        s.p.zalozky.setCurrentIndex(3)
    s.po(po)


def vyska_stanoviska(s: Stavitel):
    """G18 Výpočet výšky stanoviska."""
    tab, orient = s.tabulka("orientace", ["Bod", "Délka", "Zenit", "Převýšení", "Výška sig.", "V přev."], 5,
                            [("Délka:", "mer", "Šikmá délka [m]"), ("Zenitový úhel:", "vys", "Zenitový úhel [gon]"),
                             ("Převýšení:", "vys", "Měřené převýšení stroj → cíl [m] (místo délky a zenitu)"),
                             ("Výška signálu:", "vys", "Výška signálu (cíle) [m]")],
                            mereni=lambda m: [m["bod"], f"{m['sd']:.3f}", f"{m['z']:.4f}", "", f"{m['vc']:.3f}"],
                            aktualizovat=False)
    s.pridej(s.oddil("Orientace:", orient, natahnout=True), 1)
    vp = s.pole("vp", "vys", 80, "Výška stroje [m]")
    y = s.pole("y", "sour", 110, "Y stanoviska – jen když stanovisko v seznamu není")
    x = s.pole("x", "sour", 110)
    nc = NoveCislo()
    s.p.inputs["nove"] = nc
    z = pole("sour", 110, True)

    def najdi():
        b = s.page.seznam.najdi(nc.hodnota()) if nc.hodnota() else None
        if b is not None:
            y.setText(fmt(b.y))
            x.setText(fmt(b.x))
    nc.cislo.editingFinished.connect(najdi)
    tab.pri_stanovisku = lambda sth: (nc.nastav_hodnotu(sth[0]), vp.setText(f"{sth[1]:.3f}"), najdi())
    ok = QToolButton()
    ok.setText("✓")
    ok.setObjectName("ulozit_vysledek")
    ok.setToolTip("Uložit výšku stanoviska do seznamu souřadnic")
    ok.setMinimumSize(30, 54)
    ok.setEnabled(False)
    ok.clicked.connect(lambda: s.p.pridej())
    s.p._tlacitka_ulozit.append(ok)
    s.p._ma_ulozeni = True
    s.pridej(s.oddil("Určovaný bod:", s.vedle(formular([("Číslo:", nc), ("Výška stroje:", vp)]),
                                              formular([("Y:", y), ("X:", x), ("Z:", z)]), ok, natahnout=(3, 3, 0))))

    def po(v):
        if v:
            tab.nastav_vysledky(v.data.get("opravy", {}))
        z.setText(fmt(v.data["bod"][3]) if v else "")
    s.po(po)


def vymery(s: Stavitel):
    """G19 Výpočet výměr: označení parcely, lomové body (i vrcholy oblouků), výsledek a kalkulačka."""
    par = s.pole("parcela", "cislo", 110)
    dil = s.pole("dil", "cislo", 110)
    s.pridej(s.oddil("Označení parcely:", s.vedle(QLabel("Parcela:"), par, QLabel("Díl:"), dil, None,
                                                  natahnout=(0, 1, 0, 1, 1))))
    tab = TabulkaRadku(["Bod", "Oblouk"], 2)
    bb = s.bod("", z=False, kvalita=True)
    vrchol = Prepinac("Vrchol oblouku")

    def pridat(c=None):
        c = c or bb.hodnota()
        if c:
            tab.pridej([c, "o" if vrchol.isChecked() else ""])
            bb.vymaz()
            vrchol.setChecked(False)
    bb.cislo.returnPressed.connect(lambda: (bb._dopln(), pridat()))
    tab.pri_pretazeni = lambda md: [pridat(c) for c, *_r in body_z_mime(md)] or True
    levy = s.pod(tab, s.vedle(s.tlacitko("Přidat", pridat), s.tlacitko("Odebrat", tab.odeber),
                              s.tlacitko("Aktualizovat souř.", lambda: None), None))
    s.pridej(s.oddil("Lomové body:", s.vedle(levy, s.pod(bb, vrchol, None), natahnout=(2, 3)), natahnout=True), 1)

    class _Body:
        def hodnota(self):
            return "\n".join(" ".join(r) for r in tab.radky())

        def nastav_hodnotu(self, t):
            tab.setRowCount(0)
            for r in str(t).replace(",", " ").split("\n"):
                for c in r.split() if len(r.split()) > 2 or (len(r.split()) == 2 and r.split()[1] != "o") else [r]:
                    if c.strip():
                        tab.pridej(c.split())
    s.p.inputs["body"] = _Body()
    vym = pole("mer", 120, True)
    soucet = pole("mer", 120, True)
    soucet.setText("0")
    kalk = {"v": 0.0}

    def pricti(zn):
        try:
            kalk["v"] += zn * float(vym.text())
        except ValueError:
            return
        soucet.setText(f"{kalk['v']:.2f}")

    def smaz():
        kalk["v"] = 0.0
        soucet.setText("0")
    s.pridej(s.vedle(s.oddil("Výsledky:", s.vedle(QLabel("Výměra:"), vym, QLabel("m²"), None, natahnout=(0, 1, 0, 1))),
                     s.oddil("Kalkulačka:", s.vedle(QLabel("Součet:"), soucet, QLabel("m²"),
                                                    s.tlacitko("+", lambda: pricti(1)), s.tlacitko("−", lambda: pricti(-1)),
                                                    s.tlacitko("C", smaz), natahnout=(0, 1, 0, 0, 0, 0)))))
    s.po(lambda v: vym.setText(f"{v.data['vymera']:.2f}" if v else ""))


def vytyceni_polarni(s: Stavitel):
    """Polární vytyčovací prvky: stanovisko, orientace, volba počítaných údajů, vytyčované body."""
    vp = s.pole("vp", "vys", 80, "Výška stroje [m] – pro převýšení a zenitový úhel")
    vc = s.pole("vc", "vys", 80, "Výška cíle [m]")
    s.pridej(s.oddil("Stanovisko:", s.bod("st", vlevo=[("Výška stroje:", vp)])))
    so = s.pole("so", "mer", 100, "Vodorovný směr na orientaci [gon] (výchozí 0)")
    s.pridej(s.oddil("Orientace:", s.bod("o", z=False), formular([("Vodorovný směr na orientaci:", so)],
                                                                  nahoru=False)))
    s.pridej(s.oddil("Počítat:", s.vedle(s.volba("volba", ["Orientace + směry", "Orientace + směrníky", "Směrníky"]),
                                         QLabel("Výška cíle:"), vc, None, natahnout=(2, 0, 1, 1))))
    tab = TabulkaRadku(["Bod", "Směr", "Směrník", "Délka", "Převýšení", "Zenit"], 1)
    tab.pri_pretazeni = lambda md: ([tab.pridej([c]) for c, *_r in body_z_mime(md)], s.p.vypocitej()) and True
    bb = s.bod("", kvalita=False)
    bp = s.tlacitko("Přidat", lambda: (tab.pridej([bb.hodnota()]), bb.vymaz()) if bb.hodnota() else None)
    s.pridej(s.oddil("Vytyčované body:", bb, s.vedle(bp, s.tlacitko("Odebrat", tab.odeber), None), tab,
                     natahnout=True), 1)

    class _Body:
        def hodnota(self):
            return "\n".join(r[0] for r in tab.radky())

        def nastav_hodnotu(self, t):
            tab.setRowCount(0)
            for c in str(t).replace(",", " ").split():
                tab.pridej([c])
    s.p.inputs["body"] = _Body()

    def po(v):
        if v:
            tab.nastav_vysledky({k: [x for x in r] for k, r in v.data.get("prvky", {}).items()})
    s.po(po)


def vytyceni_ortogonalni(s: Stavitel):
    """Ortogonální vytyčovací prvky: přímka A–B a vytyčované body → staničení, kolmice."""
    s.pridej(s.vedle(s.oddil("Počáteční bod přímky:", s.bod("a", z=False)),
                     s.oddil("Koncový bod přímky:", s.bod("b", z=False))))
    from .ulohy import _Radky
    tr = _Radky()
    tr.setPlaceholderText("Čísla vytyčovaných bodů – přetáhněte je ze seznamu souřadnic")
    s.p.inputs["body"] = tr
    s.pridej(s.oddil("Vytyčované body:", tr, natahnout=True), 1)


def oblouk(s: Stavitel):
    """Rozložení oblouku: definice kruhového oblouku (vrchol tečen, tečné body, poloměr) a způsob rozložení."""
    s.pridej(s.oddil("Definice kruhového oblouku:", nadpis("Vrchol tečen"), s.bod("v", z=False),
                     s.vedle(s.pod(nadpis("Začátek oblouku (na tečně)"), s.bod("a", z=False, rozlozeni="pod")),
                             s.pod(nadpis("Konec oblouku (na tečně)"), s.bod("b", z=False, rozlozeni="pod"))),
                     formular([("Poloměr [m]:", s.pole("r", "mer", 100))], nahoru=False)))
    s.pridej(s.oddil("Definice způsobu rozložení:", formular(
        [("Krok po oblouku [m]:", s.pole("krok", "mer", 100, "Vzdálenost podrobných bodů po oblouku")),
         ("Počáteční číslo bodu (předpona):", s.pole("predpona", "cislo", 100, vychozi="O"))], nahoru=False)))
    s.p.form.addStretch(1)


def trojuhelnik(s: Stavitel):
    """Trojúhelníková kalkulačka: tři údaje → dopočte zbytek, výměru."""
    p = {k: s.pole(k, "mer" if k in "abc" else "vys", 110) for k in ("a", "b", "c", "alfa", "beta", "gama")}
    vym = pole("mer", 110, True)
    s.pridej(s.oddil("Trojúhelník:", s.vedle(
        formular([("Strana a [m]:", p["a"]), ("Strana b [m]:", p["b"]), ("Strana c [m]:", p["c"])]),
        formular([("Úhel α [g]:", p["alfa"]), ("Úhel β [g]:", p["beta"]), ("Úhel γ [g]:", p["gama"])]))),
        )
    s.pridej(s.oddil("Výsledky:", s.vedle(QLabel("Výměra:"), vym, QLabel("m²"), None, natahnout=(0, 1, 0, 1))))
    s.pridej(s.poznamka("Zadejte aspoň tři údaje (ne tři úhly). Úhel α leží proti straně a. Po výpočtu se doplní "
                        "všechny strany i úhly."))
    s.p.form.addStretch(1)

    def po(v):
        if not v:
            return
        for k, x in v.data["hodnoty"].items():
            if k in p:
                p[k].setText(f"{x:.4f}" if k in ("alfa", "beta", "gama") else f"{x:.3f}")
        vym.setText(f"{v.data['hodnoty']['P']:.2f}")
    s.po(po)


def vyskovy_porad(s: Stavitel):
    """Výškový pořad (trigonometrický): počáteční a koncový bod s výškou, měření tam a zpět."""
    s.pridej(s.vedle(s.oddil("Počáteční bod:", s.bod("a", kvalita=False, rozlozeni="pod")),
                     s.oddil("Koncový bod:", s.bod("b", kvalita=False, rozlozeni="pod"))))
    tab = TabulkaRadku(["Bod", "Výška stroje", "Délka zpět", "Zenit zpět", "V. cíle zpět", "Délka vpřed",
                        "Zenit vpřed", "V. cíle vpřed"], 8)
    s.p.inputs["mereni"] = tab
    bb = s.bod("", z=False)

    def drop(md):
        sth, mer = mereni_z_mime(md)
        if sth is None or not mer:
            for c, *_r in body_z_mime(md):
                tab.pridej([c] + [""] * 7)
            return True
        z, v = mer[0], mer[-1]
        tab.pridej([sth[0], f"{sth[1]:.3f}", f"{z['sd']:.3f}", f"{z['z']:.4f}", f"{z['vc']:.3f}",
                    *([f"{v['sd']:.3f}", f"{v['z']:.4f}", f"{v['vc']:.3f}"] if len(mer) > 1 else ["", "", ""])])
        return True
    tab.pri_pretazeni = drop
    s.pridej(s.oddil("Měřená data:", s.vedle(bb, s.tlacitko("Přidat", lambda: (tab.pridej([bb.hodnota()] + [""] * 7),
                                                                               bb.vymaz()) if bb.hodnota() else None),
                                             s.tlacitko("Odebrat", tab.odeber), None, natahnout=(3, 0, 0, 1)), tab,
                     s.poznamka("Hodnoty se píší přímo do tabulky; stanovisko jde přetáhnout ze zápisníku (první "
                                "záměra = zpět, poslední = vpřed)."), natahnout=True), 1)


def nivelace(s: Stavitel):
    """G20 Nivelace: tabulka nivelačního zápisníku (Číslo bodu, Zpět, Vpřed, Bočně, Délka)."""
    s.pridej(s.vedle(s.oddil("Počáteční bod:", s.bod("a", kvalita=False, rozlozeni="pod")),
                     s.oddil("Koncový bod:", s.bod("b", kvalita=False, rozlozeni="pod"))))
    tab = TabulkaRadku(["Číslo bodu", "Zpět", "Vpřed", "Bočně", "Délka", "Vyp. výška"], 5)
    tab.setMinimumHeight(200)
    for _ in range(3):
        tab.pridej([""] * 6)
    tab.pri_pretazeni = lambda md: [tab.pridej([c] + [""] * 5) for c, *_r in body_z_mime(md)] or True

    class _Zap:
        def hodnota(self):
            out = []
            for r in tab.radky():
                c, zp, vp, bo, dl = (r + [""] * 5)[:5]
                for zn, x in (("Z", zp), ("P", vp), ("B", bo)):
                    if x:
                        out.append(f"{zn} {c} {x}" + (f" {dl}" if dl and zn != "B" else ""))
            return "\n".join(out)

        def nastav_hodnotu(self, t):
            tab.setRowCount(0)
            for r in str(t).splitlines():
                p = r.split()
                if len(p) >= 3:
                    row = [p[1], "", "", "", p[3] if len(p) > 3 else ""]
                    row[{"Z": 1, "P": 2, "B": 3}.get(p[0].upper(), 3)] = p[2]
                    tab.pridej(row)
    s.p.inputs["zapisnik"] = _Zap()
    mez = s.pole("mez", "mer", 70, "Mezní odchylka [mm/√km]", "40")
    s.pridej(s.oddil("Nivelační zápisník:", tab, s.vedle(
        s.tlacitko("Přidat řádek", lambda: tab.pridej([""] * 6)), s.tlacitko("Odebrat", tab.odeber),
        QLabel("Mezní odchylka [mm/√km]:"), mez, None, natahnout=(0, 0, 0, 0, 1)), natahnout=True), 1)

    def po(v):
        if v:
            tab.nastav_vysledky({k: [x] for k, x in v.vysky.items()})
    s.po(po)


def kubatury(s: Stavitel):
    """Kubatury: body s výškou (přetažením), interval vrstevnic, srovnávací výška."""
    from .ulohy import _Radky
    tr = _Radky()
    tr.setPlaceholderText("Body s výškou – přetáhněte je ze seznamu (prázdné = všechny body s výškou)")
    s.p.inputs["body"] = tr
    s.pridej(s.oddil("Body terénu:", tr, natahnout=True), 1)
    s.pridej(s.oddil("Parametry:", formular([
        ("Interval vrstevnic [m]:", s.pole("interval", "vys", 90, vychozi="1")),
        ("Max. délka strany trojúhelníku [m]:", s.pole("ms", "mer", 90, "Odřízne dlouhé trojúhelníky na okraji")),
        ("Srovnávací výška [m]:", s.pole("zref", "vys", 90, "Pro objem výkopu a násypu"))], nahoru=False)))


OKNA = {
    "Rajón (polární bod)": polarni, "Volné stanovisko": volne, "Transformace": transformace,
    "Směrník a délka": smernik, "Ortogonální metoda (Groma)": ortogonalni,
    "Protínání vpřed ze směrů": protinani_smery, "Protínání z délek": z_delek, "Průsečíky": prusecik_primek,
    "Průsečík přímka - směr": prusecik_smer, "Průsečík přímka - kružnice": prusecik_kruznice,
    "Vyrovnání na přímku": na_primku, "Vyrovnání na kružnici": na_kruznici,
    "Vyrovnávací přímka": lambda s: vyrovnavaci(s, False), "Vyrovnávací kružnice": lambda s: vyrovnavaci(s, True),
    "Kontrolní oměrné míry": kontrolni_omerne, "Konstrukční oměrné": konstrukcni,
    "Polygonový pořad (Groma)": polygon, "Výška stanoviska": vyska_stanoviska, "Výměra a obvod": vymery,
    "Vytyčovací prvky": vytyceni_polarni, "Staničení a kolmice": vytyceni_ortogonalni,
    "Kružnicový oblouk": oblouk, "Trojúhelníková kalkulačka": trojuhelnik, "Výškový pořad": vyskovy_porad,
    "Nivelační zápisník": nivelace, "Model terénu a kubatura": kubatury,
}
