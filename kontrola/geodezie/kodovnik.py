"""Kódování prvků účelové mapy: kódovník (kód bodu z terénu → linie, plocha nebo bodová značka) a sestavení
kresby z kódů bodů v pořadí měření – jako „kresba z kódů“ v Gromě / Atlasu / MicroStationu.

Zápis kódů u bodu (jak se zadávají v totální stanici nebo v QTrig):

* ``PL`` – bod patří do linie s kódem PL; body se stejným kódem se spojují v pořadí čísel (měření);
* ``PL/Z`` – začátek nové linie (předchozí linie s tímto kódem se ukončí), ``PL/K`` – konec linie,
  ``PL/U`` – uzavřít (spojit s prvním bodem linie, např. budova);
* ``PL#2`` – druhá souběžná linie se stejným kódem (např. obě hrany chodníku měřené střídavě);
* víc kódů na jednom bodě oddělených mezerou, čárkou nebo středníkem (``PL BUD/Z`` – roh plotu a budovy).

Kód, který v kódovníku není, se zkusí podle zadání: název buňky (``3.13`` strom) → bodová značka, název
stylu čáry (``2.13`` plot) → linie ve vrstvě pravidla, jehož styly ho obsahují. Bez Qt (desktop i web).
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .body import klic_cisla

DRUHY = ("linie", "plocha", "bod")
RIDICI = {"Z": "zacatek", "K": "konec", "U": "uzavrit"}
SLOUPCE = ["kod", "popis", "druh", "predvolba", "vrstva", "bunka", "styl"]
NAZVY_SLOUPCU = {"kod": "Kód", "popis": "Popis", "druh": "Druh", "predvolba": "Pravidlo ze zadání",
                 "vrstva": "Hladina", "bunka": "Buňka", "styl": "Styl čáry"}


@dataclass
class Kod:
    kod: str
    popis: str = ""
    druh: str = "linie"  # linie | plocha | bod
    predvolba: str = ""  # název pravidla ze zadání (hladina, barva, tloušťka, styl…)
    vrstva: str = ""  # hladina (má přednost před pravidlem)
    bunka: str = ""  # buňka bodové značky
    styl: str = ""  # typ čáry (např. 2.13 – plot)
    odvozeny: bool = False  # nevznikl z kódovníku, ale ze zadání (buňka / styl)


@dataclass
class Linie:
    kod: Kod
    body: list
    uzavrena: bool = False
    cislo: str = ""  # index souběžné linie (#2)


@dataclass
class Kresba:
    linie: list[Linie] = field(default_factory=list)
    bodove: list[tuple[Kod, object]] = field(default_factory=list)
    nezname: Counter = field(default_factory=Counter)
    varovani: list[str] = field(default_factory=list)

    def souhrn(self) -> str:
        plochy = sum(1 for x in self.linie if x.kod.druh == "plocha")
        t = (f"Z kódů: {len(self.linie) - plochy} linií, {plochy} ploch, {len(self.bodove)} bodových značek")
        if self.nezname:
            t += ". Neznámé kódy: " + ", ".join(f"{k} ({n}×)" for k, n in self.nezname.most_common(12))
        return t + "."


class Kodovnik:
    def __init__(self, kody: list[Kod] | None = None):
        self.kody: list[Kod] = list(kody or [])

    def __len__(self) -> int:
        return len(self.kody)

    def najdi(self, kod: str) -> Kod | None:
        k = kod.strip().upper()
        return next((x for x in self.kody if x.kod.strip().upper() == k), None)

    # ------------------------------------------------------------ soubor (CSV se středníkem, otevře i Excel)
    def text(self) -> str:
        out = io.StringIO()
        w = csv.writer(out, delimiter=";", lineterminator="\n")
        w.writerow([NAZVY_SLOUPCU[s] for s in SLOUPCE])
        for k in self.kody:
            w.writerow([getattr(k, s) for s in SLOUPCE])
        return out.getvalue()

    def uloz(self, cesta: str | Path) -> Path:
        p = Path(cesta)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("﻿" + self.text(), encoding="utf-8")
        return p

    @classmethod
    def z_textu(cls, text: str) -> "Kodovnik":
        text = text.lstrip("﻿")
        prvni = text.splitlines()[0] if text.strip() else ""
        odd = ";" if ";" in prvni else ("\t" if "\t" in prvni else ",")
        radky = list(csv.reader(io.StringIO(text), delimiter=odd))
        if not radky:
            return cls()
        hlava = [h.strip().lower() for h in radky[0]]
        podle = {v.lower(): k for k, v in NAZVY_SLOUPCU.items()} | {k: k for k in SLOUPCE}
        idx = {podle[h]: i for i, h in enumerate(hlava) if h in podle}
        if "kod" not in idx:  # bez hlavičky: kód; popis; druh; …
            idx = {s: i for i, s in enumerate(SLOUPCE)}
        else:
            radky = radky[1:]
        kody = []
        for r in radky:
            hod = {s: (r[i].strip() if i < len(r) else "") for s, i in idx.items()}
            if not hod.get("kod"):
                continue
            druh = (hod.get("druh") or "linie").lower()
            druh = {"l": "linie", "p": "plocha", "b": "bod", "značka": "bod", "znacka": "bod",
                    "polygon": "plocha"}.get(druh, druh)
            if druh not in DRUHY:
                druh = "linie"
            kody.append(Kod(hod["kod"], hod.get("popis", ""), druh, hod.get("predvolba", ""), hod.get("vrstva", ""),
                            hod.get("bunka", ""), hod.get("styl", "")))
        return cls(kody)

    @classmethod
    def nacti(cls, cesta: str | Path) -> "Kodovnik":
        from .formaty import dekoduj
        return cls.z_textu(dekoduj(Path(cesta).read_bytes()))

    # ------------------------------------------------------------ výchozí kódovník ze zadání
    @classmethod
    def ze_zadani(cls, predvolby) -> "Kodovnik":
        """Kódy podle Směrnice: každá buňka bodové značky a každý styl čáry z pravidel (čísla mapových značek,
        např. 3.13 strom, 2.13 plot) – kód = číslo značky. Kódovník se pak dá upravit (vlastní zkratky)."""
        kody: list[Kod] = []
        videno: set[str] = set()
        for p in predvolby:
            nazev = p.nazev or ""
            for b in _rozsah(p.blok or ""):
                if b.upper() not in videno:
                    videno.add(b.upper())
                    kody.append(Kod(b, _bez_kodu(nazev), "bod", nazev, bunka=b))
            for s in _rozsah((p.ms or {}).get("styl_vse") or "") or ([p.typ_cary] if _je_styl_ms(p.typ_cary) else []):
                if s.upper() not in videno:
                    videno.add(s.upper())
                    druh = "plocha" if p.geometrie == "polygon" else "linie"
                    kody.append(Kod(s, _bez_kodu(nazev), druh, nazev, styl=s))
        # linie a plochy bez vlastního stylu (budovy, hrany…) dostanou zkratku z názvu – dá se přepsat
        for p in predvolby:
            if p.geometrie not in ("linie", "polygon", None) or p.blok or p.geometrie == "text":
                continue
            styly = _rozsah((p.ms or {}).get("styl_vse") or "")
            if styly or _je_styl_ms(p.typ_cary):
                continue
            zk = _zkratka(_bez_kodu(p.nazev), videno)
            videno.add(zk.upper())
            kody.append(Kod(zk, _bez_kodu(p.nazev), "plocha" if p.geometrie == "polygon" else "linie", p.nazev))
        return cls(kody)

    def to_dicts(self) -> list[dict]:
        return [asdict(k) for k in self.kody]


def _zkratka(nazev: str, obsazene: set[str]) -> str:
    """„Budovy zděné, betonové“ → BZB (bez diakritiky, jedinečná)."""
    import unicodedata
    t = unicodedata.normalize("NFD", nazev)
    t = "".join(c for c in t if not unicodedata.combining(c))
    slova = [w for w in re.split(r"[^A-Za-z0-9]+", t) if w and w.lower() not in ("a", "s", "v", "na", "do", "z", "se")]
    zk = "".join(w[0] for w in slova[:4]).upper() or "K"
    if len(zk) == 1 and slova:
        zk = slova[0][:3].upper()
    vys, n = zk, 2
    while vys.upper() in obsazene:
        vys, n = f"{zk}{n}", n + 1
    return vys


def _bez_kodu(nazev: str) -> str:
    return re.sub(r"^\S+\s+–\s+", "", nazev or "")


def _je_styl_ms(s: str | None) -> bool:
    return bool(s) and bool(re.match(r"^\d+\.[0-9A-Za-z]+$", s))


def _rozsah(text: str) -> list[str]:
    """„1.01–1.09|1.GPS|3.13“ → [1.01, 1.02, …, 1.09, 1.GPS, 3.13] (rozsahy čísel značek se rozepíší)."""
    out = []
    for cast in re.split(r"[|,;]", text or ""):
        c = cast.strip()
        if not c:
            continue
        m = re.match(r"^(\d+)\.(\d+)\s*[–-]\s*(\d+)\.(\d+)$", c)
        if m and m.group(1) == m.group(3):
            a, b = int(m.group(2)), int(m.group(4))
            sirka = len(m.group(2))
            out += [f"{m.group(1)}.{i:0{sirka}d}" for i in range(a, b + 1)] if 0 <= b - a <= 200 else [c]
        elif re.match(r"^\d+\.[0-9A-Za-z]+$", c):
            out.append(c)
    return out


# ------------------------------------------------------------------ kódy u bodu
def rozloz(kody: str) -> list[tuple[str, str, str | None]]:
    """„PL BUD/Z PL#2/K“ → [(PL, "", None), (BUD, "", zacatek), (PL, "2", konec)]."""
    out = []
    for t in re.split(r"[\s,;]+", (kody or "").strip()):
        if not t:
            continue
        ridici = None
        m = re.match(r"^(.*?)/([ZKUzku])$", t)
        if m:
            t, ridici = m.group(1), RIDICI[m.group(2).upper()]
        cislo = ""
        m = re.match(r"^(.*?)#(\w+)$", t)
        if m:
            t, cislo = m.group(1), m.group(2)
        if t:
            out.append((t, cislo, ridici))
    return out


def _odvozeny(kod: str, predvolby) -> Kod | None:
    """Kód mimo kódovník podle zadání: buňka (bodová značka) nebo styl čáry (linie)."""
    k = kod.strip().upper()
    for p in predvolby or ():
        if any(b.upper() == k for b in _rozsah(p.blok or "")):
            return Kod(kod, _bez_kodu(p.nazev), "bod", p.nazev, bunka=kod, odvozeny=True)
    for p in predvolby or ():
        styly = _rozsah((p.ms or {}).get("styl_vse") or "") or ([p.typ_cary] if _je_styl_ms(p.typ_cary) else [])
        if any(s.upper() == k for s in styly):
            return Kod(kod, _bez_kodu(p.nazev), "plocha" if p.geometrie == "polygon" else "linie", p.nazev,
                       styl=kod, odvozeny=True)
    return None


def sestav(body, kodovnik: Kodovnik | None = None, predvolby=()) -> Kresba:
    """Kresba z kódů bodů: linie a plochy (spojení v pořadí čísel bodů) a bodové značky."""
    kodovnik = kodovnik or Kodovnik()
    kr = Kresba()
    otevrene: dict[tuple[str, str], Linie] = {}
    pamet: dict[str, Kod | None] = {}

    def uzavri(klic, uzavrit=False):
        lin = otevrene.pop(klic, None)
        if lin is None:
            return
        if uzavrit or lin.kod.druh == "plocha":
            lin.uzavrena = len(lin.body) >= 3
        if len(lin.body) >= 2:
            kr.linie.append(lin)
        else:
            kr.varovani.append(f"Linie {lin.kod.kod} má jen bod {lin.body[0].cislo} – nekreslí se.")

    for b in sorted(body, key=lambda b: klic_cisla(b.cislo)):
        for kod, cislo, ridici in rozloz(getattr(b, "kod", "") or ""):
            if kod.upper() not in pamet:
                pamet[kod.upper()] = kodovnik.najdi(kod) or _odvozeny(kod, predvolby)
            k = pamet[kod.upper()]
            if k is None:
                kr.nezname[kod] += 1
                continue
            if k.druh == "bod":
                kr.bodove.append((k, b))
                continue
            klic = (k.kod.upper(), cislo)
            if ridici == "zacatek":
                uzavri(klic)
            lin = otevrene.get(klic)
            if lin is None:
                lin = otevrene[klic] = Linie(k, [], cislo=cislo)
            lin.body.append(b)
            if ridici in ("konec", "uzavrit"):
                uzavri(klic, ridici == "uzavrit")
    for klic in list(otevrene):
        uzavri(klic)
    return kr
