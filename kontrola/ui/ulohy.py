"""Geodetické úlohy nad seznamem souřadnic: formulář → výpočet → protokol → nové body do seznamu.

Každá úloha je popsaná daty (pole formuláře) a funkcí výpočtu; chyby vstupu se ukážou srozumitelně
(neznámý bod, chybějící číslo, nesmyslná geometrie), nikdy nespadnou.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..geodezie import vypocty as V
from ..geodezie.body import Bod, SeznamBodu


class ChybaVstupu(ValueError):
    pass


@dataclass
class Vysledek:
    protokol: list[str]
    nove: list[Bod] = field(default_factory=list)


@dataclass
class Pole:
    key: str
    label: str
    typ: str = "bod"  # bod | gon | m | text | volba | radky | cislo_noveho
    vychozi: str = ""
    volby: tuple = ()
    napoveda: str = ""


# ------------------------------------------------------------------ pomocné
def _f(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}"


def _bod(seznam: SeznamBodu, h: dict, key: str, nazev: str) -> Bod:
    c = (h.get(key) or "").strip()
    if not c:
        raise ChybaVstupu(f"Vyplňte {nazev}.")
    b = seznam.najdi(c)
    if b is None:
        raise ChybaVstupu(f"Bod {c} ({nazev}) v seznamu souřadnic není.")
    return b


def _cislo(h: dict, key: str, nazev: str) -> float:
    t = (h.get(key) or "").strip().replace(",", ".")
    if not t:
        raise ChybaVstupu(f"Vyplňte {nazev}.")
    try:
        return float(t)
    except ValueError:
        raise ChybaVstupu(f"{nazev}: „{t}“ není číslo.") from None


def _nove_cislo(seznam: SeznamBodu, h: dict, key: str = "nove") -> str:
    c = (h.get(key) or "").strip()
    if not c:
        raise ChybaVstupu("Vyplňte číslo nového bodu.")
    return c


def _radky_bodu(seznam: SeznamBodu, text: str) -> list[Bod]:
    cisla = [c for c in text.replace(",", " ").replace(";", " ").split() if c]
    out = []
    for c in cisla:
        b = seznam.najdi(c)
        if b is None:
            raise ChybaVstupu(f"Bod {c} v seznamu souřadnic není.")
        out.append(b)
    return out


def _hlavicka(nazev: str) -> list[str]:
    return [f"{nazev}", f"vypočteno {dt.datetime.now():%d.%m.%Y %H:%M}", "-" * 60]


# ------------------------------------------------------------------ úlohy
def u_smernik(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    p = _hlavicka("Směrník a délka")
    p += [f"z bodu {a.cislo} na bod {b.cislo}",
          f"  směrník σ = {_f(V.smernik(a, b), 4)} gon",
          f"  délka   d = {_f(V.delka(a, b))} m",
          f"  ΔY = {_f(b.y - a.y)} m, ΔX = {_f(b.x - a.x)} m"]
    if a.z is not None and b.z is not None:
        p.append(f"  převýšení Δh = {_f(b.z - a.z)} m")
    return Vysledek(p)


def u_rajon(s, h):
    st, o = _bod(s, h, "st", "stanovisko"), _bod(s, h, "o", "orientaci")
    so, sm, d = _cislo(h, "so", "směr na orientaci"), _cislo(h, "sm", "měřený směr"), _cislo(h, "d", "délku")
    if d <= 0:
        raise ChybaVstupu("Délka musí být kladná.")
    n = _nove_cislo(s, h)
    posun = V.norm_gon(V.smernik(st, o) - so)
    sig = V.norm_gon(sm + posun)
    p = V.rajon(st, sig, d)
    z = None
    if st.z is not None and (h.get("dh") or "").strip():
        z = st.z + _cislo(h, "dh", "převýšení")
    prot = _hlavicka("Rajón (polární bod)")
    prot += [f"stanovisko {st.cislo}, orientace na {o.cislo}: směrník {_f(V.smernik(st, o), 4)} gon, "
             f"směr {_f(so, 4)} gon → posun {_f(posun, 4)} gon",
             f"bod {n}: směr {_f(sm, 4)} gon → směrník {_f(sig, 4)} gon, délka {_f(d)} m",
             f"  Y = {_f(p.y)}   X = {_f(p.x)}" + (f"   Z = {_f(z)}" if z is not None else "")]
    return Vysledek(prot, [Bod(n, p.y, p.x, z, poznamka="rajón")])


def u_vpred_uhly(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    alfa, beta = _cislo(h, "alfa", "úhel α"), _cislo(h, "beta", "úhel β")
    n = _nove_cislo(s, h)
    try:
        p = V.protinani_vpred_uhly(a, b, alfa, beta)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    g = 400 - alfa - beta
    prot = _hlavicka("Protínání vpřed z úhlů")
    prot += [f"základna {a.cislo}–{b.cislo}: {_f(V.delka(a, b))} m, α = {_f(alfa, 4)} gon, β = {_f(beta, 4)} gon",
             f"úhel na určovaném bodě γ = {_f(V.norm_gon(200 - alfa - beta) if g > 200 else 200 - alfa - beta, 4)} "
             "gon" + ("  (POZOR: ostrý úhel protnutí, výsledek je nejistý)" if min(abs(200 - alfa - beta), 400) < 30
                      else ""),
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="protínání vpřed")])


def u_z_delek(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    da, db = _cislo(h, "da", "délku z A"), _cislo(h, "db", "délku z B")
    n = _nove_cislo(s, h)
    vlevo = (h.get("strana") or "vlevo") == "vlevo"
    try:
        p = V.protinani_z_delek(a, b, da, db, vlevo=vlevo)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Protínání z délek")
    prot += [f"{a.cislo}–{b.cislo}: {_f(V.delka(a, b))} m, dA = {_f(da)} m, dB = {_f(db)} m, bod "
             f"{'vlevo' if vlevo else 'vpravo'} od směru {a.cislo}→{b.cislo}",
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="protínání z délek")])


def u_zpet(s, h):
    a, b, c = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B"), _bod(s, h, "c", "bod C")
    sa, sb, sc = _cislo(h, "sa", "směr na A"), _cislo(h, "sb", "směr na B"), _cislo(h, "sc", "směr na C")
    n = _nove_cislo(s, h)
    try:
        p = V.protinani_zpet(a, b, c, sa, sb, sc)
    except (ValueError, ZeroDivisionError):
        raise ChybaVstupu("Stanovisko nejde určit – body leží na nebezpečné kružnici nebo jsou směry chybné.") \
            from None
    o = V.orientace(p, [(a.cislo, a, sa), (b.cislo, b, sb), (c.cislo, c, sc)])
    prot = _hlavicka("Protínání zpět (ze tří bodů)")
    prot += [f"směry: {a.cislo} {_f(sa, 4)}, {b.cislo} {_f(sb, 4)}, {c.cislo} {_f(sc, 4)} gon",
             f"stanovisko {n}:  Y = {_f(p.y)}   X = {_f(p.x)}",
             f"orientační posun {_f(o.posun, 4)} gon"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="protínání zpět")])


def u_volne(s, h):
    mer = []
    for i, line in enumerate((h.get("mereni") or "").splitlines(), 1):
        parts = line.replace(",", ".").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „číslo_bodu směr délka“.")
        b = s.najdi(parts[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {parts[0]} v seznamu není.")
        try:
            mer.append((b.cislo, b, float(parts[1]), float(parts[2])))
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: směr a délka musí být čísla.") from None
    n = _nove_cislo(s, h)
    try:
        vs = V.volne_stanovisko(mer, meritko_volne=(h.get("meritko") == "volné"))
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Volné stanovisko (MNČ)")
    prot += [f"stanovisko {n}:  Y = {_f(vs.stanovisko.y)}   X = {_f(vs.stanovisko.x)}",
             f"orientační posun {_f(vs.posun, 4)} gon, měřítko {vs.meritko:.7f}, "
             f"střední souřadnicová chyba m0 = {_f(vs.m0)} m", "", "opravy na známých bodech:",
             "  bod                  vY [m]    vX [m]    vp [m]"]
    for c, vy, vx in vs.opravy:
        prot.append(f"  {c:<18} {vy:>9.3f} {vx:>9.3f} {math.hypot(vy, vx):>9.3f}")
    return Vysledek(prot, [Bod(n, vs.stanovisko.y, vs.stanovisko.x, poznamka="volné stanovisko")])


def u_transformace(s, h):
    pary = []
    for i, line in enumerate((h.get("identicke") or "").splitlines(), 1):
        parts = line.replace(",", ".").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „číslo_bodu Y_cíl X_cíl“.")
        b = s.najdi(parts[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {parts[0]} v seznamu není.")
        try:
            pary.append((b, (float(parts[1]), float(parts[2]))))
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: souřadnice musí být čísla.") from None
    druh = {"shodnostní": "shodnostni", "podobnostní": "podobnostni", "afinní": "afinni"}[h.get("druh") or
                                                                                         "podobnostní"]
    try:
        t = V.transformace([b for b, _ in pary], [c for _, c in pary], druh)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka(f"Transformace {h.get('druh')}")
    prot += [f"identických bodů {len(pary)}, střední souřadnicová chyba m0 = {_f(t.m0)} m",
             f"měřítko {t.meritko:.8f}, otočení {_f(V.norm_gon(V.rad2gon(t.rotace)), 5)} gon, "
             f"posun Y {_f(t.t[0])} X {_f(t.t[1])}", "", "opravy na identických bodech:",
             "  bod                  vY [m]    vX [m]    vp [m]"]
    for (b, _), (vy, vx) in zip(pary, t.opravy):
        prot.append(f"  {b.cislo:<18} {vy:>9.3f} {vx:>9.3f} {math.hypot(vy, vx):>9.3f}")
    nove = []
    pre = (h.get("predpona") or "").strip()
    cil = _radky_bodu(s, h.get("transformovat") or "")
    if cil:
        prot += ["", "transformované body:"]
        for b in cil:
            y, x = t.preved(b)
            nove.append(Bod(pre + b.cislo, y, x, b.z, b.kod, b.kvalita, "transformace"))
            prot.append(f"  {pre + b.cislo:<14} Y = {_f(y)}   X = {_f(x)}")
    return Vysledek(prot, nove)


def u_vymera(s, h):
    body = _radky_bodu(s, h.get("body") or "")
    if len(body) < 3:
        raise ChybaVstupu("Výměra potřebuje aspoň tři body (zadejte čísla bodů po obvodu).")
    p = V.vymera(body)
    prot = _hlavicka("Výměra a obvod")
    prot += ["body: " + " – ".join(b.cislo for b in body),
             f"výměra P = {_f(p, 2)} m²  (zaokrouhleně {round(p):d} m²)",
             f"obvod  o = {_f(V.obvod(body))} m"]
    return Vysledek(prot)


def u_staniceni(s, h):
    a, b = _bod(s, h, "a", "bod A (začátek přímky)"), _bod(s, h, "b", "bod B (směr přímky)")
    body = _radky_bodu(s, h.get("body") or "")
    if not body:
        raise ChybaVstupu("Zadejte čísla bodů, ke kterým se počítá staničení a kolmice.")
    prot = _hlavicka("Staničení a kolmice")
    prot += [f"měřická přímka {a.cislo} → {b.cislo} ({_f(V.delka(a, b))} m), kolmice kladná vpravo",
             "  bod             staničení    kolmice"]
    for p in body:
        st, k = V.stanicni_kolmice(a, b, p)
        prot.append(f"  {p.cislo:<14} {st:>10.3f} {k:>10.3f}")
    return Vysledek(prot)


def u_ze_staniceni(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    st, k = _cislo(h, "st", "staničení"), _cislo(h, "kol", "kolmici")
    n = _nove_cislo(s, h)
    p = V.bod_ze_stanicni(a, b, st, k)
    prot = _hlavicka("Bod ze staničení a kolmice")
    prot += [f"přímka {a.cislo} → {b.cislo}, staničení {_f(st)} m, kolmice {_f(k)} m (vpravo kladná)",
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="staničení a kolmice")])


def u_odchylka(s, h):
    a, b = _bod(s, h, "a", "první určení"), _bod(s, h, "b", "druhé určení")
    kk = int(h.get("kk") or 3)
    d = V.polohova_odchylka(a, b)
    lim = V.mezni_polohova_odchylka(kk)
    prot = _hlavicka("Kontrola dvou určení bodu")
    prot += [f"{a.cislo} a {b.cislo}: polohová odchylka Δp = {_f(d)} m (ΔY {_f(b.y - a.y)}, ΔX {_f(b.x - a.x)})",
             f"mezní odchylka pro kód kvality {kk}: {_f(lim)} m (2·√2·m_xy, m_xy = "
             f"{_f(V.MXY_KOD_KVALITY[kk], 2)} m – ověřte v platném znění vyhlášky)",
             "VYHOVUJE" if d <= lim else "NEVYHOVUJE – překročena mezní odchylka"]
    return Vysledek(prot)


ULOHY: list[tuple[str, str, list[Pole], object]] = [
    ("Směrník a délka", "Směrník, délka a souřadnicové rozdíly mezi dvěma body.",
     [Pole("a", "Bod A"), Pole("b", "Bod B")], u_smernik),
    ("Rajón (polární bod)", "Nový bod ze stanoviska: orientace na známý bod, měřený směr a délka.",
     [Pole("st", "Stanovisko"), Pole("o", "Orientace (bod)"), Pole("so", "Směr na orientaci [gon]", "gon"),
      Pole("sm", "Měřený směr [gon]", "gon"), Pole("d", "Vodorovná délka [m]", "m"),
      Pole("dh", "Převýšení [m] (nepovinné)", "m"), Pole("nove", "Číslo nového bodu", "text")], u_rajon),
    ("Protínání vpřed z úhlů", "Bod z úhlů α (v A) a β (v B) měřených od základny A–B.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("alfa", "Úhel α [gon]", "gon"), Pole("beta", "Úhel β [gon]", "gon"),
      Pole("nove", "Číslo nového bodu", "text")], u_vpred_uhly),
    ("Protínání z délek", "Bod ze dvou měřených délek od známých bodů.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("da", "Délka z A [m]", "m"), Pole("db", "Délka z B [m]", "m"),
      Pole("strana", "Bod leží", "volba", "vlevo", ("vlevo", "vpravo"), "vlevo / vpravo od směru A → B na mapě"),
      Pole("nove", "Číslo nového bodu", "text")], u_z_delek),
    ("Protínání zpět", "Stanovisko z měřených směrů na tři známé body.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("c", "Bod C"), Pole("sa", "Směr na A [gon]", "gon"),
      Pole("sb", "Směr na B [gon]", "gon"), Pole("sc", "Směr na C [gon]", "gon"),
      Pole("nove", "Číslo stanoviska", "text")], u_zpet),
    ("Volné stanovisko", "Stanovisko a orientace z ≥ 2 známých bodů (směr + délka), vyrovnání MNČ s opravami.",
     [Pole("mereni", "Měření (řádek: bod směr[gon] délka[m])", "radky"),
      Pole("meritko", "Měřítko", "volba", "pevné (1)", ("pevné (1)", "volné")),
      Pole("nove", "Číslo stanoviska", "text")], u_volne),
    ("Transformace", "Transformační klíč z identických bodů (shodnostní / podobnostní / afinní) s opravami; "
     "transformace dalších bodů.",
     [Pole("druh", "Druh", "volba", "podobnostní", ("shodnostní", "podobnostní", "afinní")),
      Pole("identicke", "Identické body (řádek: bod Y_cíl X_cíl)", "radky"),
      Pole("transformovat", "Transformovat body (čísla)", "radky"),
      Pole("predpona", "Předpona nových čísel", "text", "T")], u_transformace),
    ("Výměra a obvod", "Výměra a obvod plochy z bodů zadaných po obvodu.",
     [Pole("body", "Body po obvodu (čísla)", "radky")], u_vymera),
    ("Staničení a kolmice", "Staničení a kolmice bodů k měřické přímce (oměrné, kontrola).",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("body", "Body (čísla)", "radky")], u_staniceni),
    ("Bod ze staničení a kolmice", "Nový bod ze staničení a kolmice k přímce A–B (vytyčení).",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("st", "Staničení [m]", "m"), Pole("kol", "Kolmice [m] (vpravo +)", "m"),
      Pole("nove", "Číslo nového bodu", "text")], u_ze_staniceni),
    ("Kontrola dvou určení", "Polohová odchylka dvou určení bodu a mezní odchylka podle kódu kvality.",
     [Pole("a", "První určení (bod)"), Pole("b", "Druhé určení (bod)"),
      Pole("kk", "Kód kvality", "volba", "3", ("3", "4", "5", "6", "7"))], u_odchylka),
]


class UlohyPanel(QWidget):
    pointsAdded = Signal(int)

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        sp = QSplitter()
        self.lst = QListWidget()
        for nazev, _p, _f, _fn in ULOHY:
            self.lst.addItem(nazev)
        self.lst.setMaximumWidth(260)
        self.lst.setObjectName("seznam_uloh")
        self.lst.setStyleSheet("QListWidget#seznam_uloh::item { padding: 7px 8px; }")
        sp.addWidget(self.lst)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.popis = QLabel()
        self.popis.setWordWrap(True)
        rl.addWidget(self.popis)
        self.formbox = QGroupBox("Zadání")
        self.form = QFormLayout(self.formbox)
        rl.addWidget(self.formbox)
        row = QHBoxLayout()
        self.b_calc = QPushButton("Vypočítat")
        self.b_calc.setProperty("primarni", True)
        self.b_calc.setShortcut("Ctrl+Return")
        self.b_add = QPushButton("Přidat do seznamu")
        self.b_add.setEnabled(False)
        self.b_copy = QPushButton("Kopírovat protokol")
        for b in (self.b_calc, self.b_add, self.b_copy):
            row.addWidget(b)
        row.addStretch(1)
        rl.addLayout(row)
        self.chyba = QLabel()
        self.chyba.setWordWrap(True)
        rl.addWidget(self.chyba)
        self.vystup = QTextBrowser()
        self.vystup.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace;")
        rl.addWidget(self.vystup, 1)
        sp.addWidget(right)
        sp.setStretchFactor(1, 1)
        lay.addWidget(sp)
        self.inputs: dict[str, QWidget] = {}
        self.vysledek: Vysledek | None = None
        self._completer_model = QStringListModel(self)
        self.lst.currentRowChanged.connect(self._show)
        self.b_calc.clicked.connect(self.vypocitej)
        self.b_add.clicked.connect(self.pridej)
        self.b_copy.clicked.connect(self._copy)
        self.lst.setCurrentRow(0)

    def _show(self, i: int):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.inputs = {}
        nazev, popis, pole, _fn = ULOHY[i]
        self.popis.setText(f"<b style='font-size:12pt'>{escape(nazev)}</b><br>{escape(popis)}")
        self._completer_model.setStringList([b.cislo for b in self.page.seznam.body])
        for p in pole:
            if p.typ == "volba":
                w = QComboBox()
                w.addItems(list(p.volby))
                w.setCurrentText(p.vychozi)
            elif p.typ == "radky":
                w = QPlainTextEdit()
                w.setFixedHeight(90)
                w.setPlaceholderText(p.label)
            else:
                w = QLineEdit(p.vychozi)
                if p.typ == "bod":
                    c = QCompleter(self._completer_model, w)
                    c.setCaseSensitivity(Qt.CaseInsensitive)
                    c.setFilterMode(Qt.MatchStartsWith)
                    w.setCompleter(c)
                    w.setPlaceholderText("číslo bodu ze seznamu")
            if p.napoveda:
                w.setToolTip(p.napoveda)
            self.form.addRow(p.label + ":", w)
            self.inputs[p.key] = w
        self.vysledek = None
        self.b_add.setEnabled(False)
        self.chyba.clear()

    def hodnoty(self) -> dict:
        out = {}
        for k, w in self.inputs.items():
            if isinstance(w, QComboBox):
                out[k] = w.currentText()
            elif isinstance(w, QPlainTextEdit):
                out[k] = w.toPlainText()
            else:
                out[k] = w.text()
        return out

    def nastav(self, **hodnoty):
        for k, v in hodnoty.items():
            w = self.inputs[k]
            if isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(str(v))
            else:
                w.setText(str(v))

    def vypocitej(self) -> Vysledek | None:
        i = self.lst.currentRow()
        nazev, _p, _pole, fn = ULOHY[i]
        try:
            self.vysledek = fn(self.page.seznam, self.hodnoty())
        except ChybaVstupu as e:
            self.chyba.setText(f"<span style='color:#DC2626'>⚠ {escape(str(e))}</span>")
            self.vysledek = None
            self.b_add.setEnabled(False)
            return None
        except Exception as e:  # noqa: BLE001 – výpočet nesmí shodit aplikaci
            self.chyba.setText(f"<span style='color:#DC2626'>⚠ Výpočet se nepovedl: {escape(str(e))}</span>")
            self.vysledek = None
            return None
        self.chyba.clear()
        self.vystup.setPlainText("\n".join(self.vysledek.protokol))
        self.b_add.setEnabled(bool(self.vysledek.nove))
        self.page.protokol_append(self.vysledek.protokol)
        return self.vysledek

    def pridej(self) -> int:
        if not self.vysledek or not self.vysledek.nove:
            return 0
        n, konf = self.page.seznam.pridej(self.vysledek.nove, f"{ULOHY[self.lst.currentRow()][0]}: nové body")
        self.page.model.refresh()
        self.page._after_change()
        if konf:
            self.chyba.setText("<span style='color:#B45309'>Body " + ", ".join(konf) + " už v seznamu jsou – "
                               "nepřepsaly se (zvolte jiné číslo nebo bod v seznamu nejdřív smažte).</span>")
        else:
            self.chyba.setText(f"<span style='color:#16A34A'>✓ Přidáno do seznamu: {n} bodů.</span>")
        self.pointsAdded.emit(n)
        return n

    def _copy(self):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.vystup.toPlainText())


def protokol_path(root: Path) -> Path:
    return Path(root) / "vypocty" / "protokol.txt"
