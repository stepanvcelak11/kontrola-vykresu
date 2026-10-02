"""Podrobná pravidla ze Směrnice ve Wordu (účelová mapa / DTM, výběr pro cvičení):

    VRSTVA 8 - DOPLŇKOVÉ ZNAČKY
    Objekt            značka umísťovaná v zaměřeném bodu
    Typy kresebných prvků  buňka
    Barva             1 - modrá
    bodové značky: Značka Knihovna Popis
    4.110  norma.cel  Střed předmětu malého rozsahu …
    liniové značky: Značka Popis
    2.093  Plot bez rozlišení druhu …

Z každého „Objektu“ vznikne pravidlo: vrstva, barva, tloušťka, typy prvků MicroStationu, povolené
buňky (bodové značky) nebo styly čar (liniové značky), u textů písmo, výška, šířka a vztažný bod.
Hodnoty ve Směrnici platí pro měřítko, pro které je napsaná (např. 1:1000); ``prevod_meritka``
je přepočítá na jiné měřítko (výšky textů, měřítko buněk a stylů čar).
"""

from __future__ import annotations

import copy
import re

from ..model import GeomType
from ..rules import Rule, RuleSet

TYPY = [  # (text ve Směrnici, typ prvku MicroStationu)
    ("uzavřený řetězec", 14), ("složený řetězec", 12), ("lomená čára", 4), ("úsečka", 3), ("oblouk", 16),
    ("křivka", 11), ("útvar", 6), ("tvar", 6), ("elipsa", 15), ("kružnice", 15), ("buňka", 2), ("text", 17),
]
_ZNACKA_BOD = re.compile(r"(\d+\.\d+(?:\s*[-–]\s*\d+\.\d+)?[A-Z]?|[A-Z]{3,})\s+(\w+\.cel)\s+", re.IGNORECASE)
_ZNACKA_CARA = re.compile(r"(?<![\d.])(\d+\.\d+)\s*(?=[A-ZČŘŠŽÚŮa-zěščřžýáíéúů])")


def _typy(text: str) -> list[int]:
    t = text.lower()
    out = []
    for slovo, typ in TYPY:
        if slovo in t and typ not in out:
            out.append(typ)
            t = t.replace(slovo, " ")
    return sorted(out)


def _cislo(rx: str, text: str) -> float | None:
    m = re.search(rx, text, re.IGNORECASE)
    return float(m.group(1).replace(",", ".")) if m else None


def _rozsah(z: str) -> str:
    """„4.2011-4.2016“ → „4.2011–4.2016“ (rozsah buněk jako v pravidlech)."""
    return re.sub(r"\s*[-–]\s*", "–", z.strip())


def nacti_pravidla(text: str, meritko: int | None = 1000, zdroj: str = "Směrnice") -> RuleSet:
    """Pravidla po objektech ze textu Směrnice (hodnoty pro ``meritko``)."""
    text = text.replace("\x07", " ").replace("\r", "\n").replace("\xa0", " ")
    bloky = re.split(r"(?i)VRSTVA\s+(\d+)\s*[-–]\s*", text)
    pravidla: list[Rule] = []
    for i in range(1, len(bloky) - 1, 2):
        cislo, obsah = bloky[i], bloky[i + 1]
        nazev_vrstvy = re.split(r"\(|Objekt|Značka", obsah, maxsplit=1)[0].strip(" –-").capitalize()
        for k, obj in enumerate(re.split(r"\bObjekt\b", obsah)[1:], 1):
            popis = re.split(r"Typy kresebných prvků", obj, maxsplit=1)[0].strip()
            m = re.search(r"Typy kresebných prvků\s*(.*?)\s*(?:Barva|$)", obj, re.DOTALL)
            typy = _typy(m.group(1)) if m else []
            barva = _cislo(r"Barva\s+(\d+)", obj)
            tl = _cislo(r"Tloušťka čáry\s*(\d+)", obj)
            vyska = _cislo(r"Výška textu\s*([\d,.]+)", obj)
            sirka = _cislo(r"Šířka textu\s*([\d,.]+)", obj)
            font = "CS WORKING" if re.search(r"CS\s*-?\s*WORKING", obj, re.IGNORECASE) else None
            vztazny = re.search(r"Vztažný bod\s*(vlevo nahoře|vlevo dole|vpravo nahoře|vpravo dole|uprostřed)", obj,
                                re.IGNORECASE)
            bodove = liniove = ""
            mb = re.search(r"bodové značky:(.*?)(?:liniové značky:|$)", obj, re.DOTALL | re.IGNORECASE)
            ml = re.search(r"liniové značky:(.*?)(?:bodové značky:|$)", obj, re.DOTALL | re.IGNORECASE)
            if mb:
                bodove = mb.group(1)
            if ml:
                liniove = ml.group(1)
            bunky = [_rozsah(z) for z, _lib in _ZNACKA_BOD.findall(bodove)]
            liniove = re.sub(r"viz\s+\d+\.\d+", " ", liniove)  # odkaz na normu („viz 4.081 ČSN“), ne značka
            styly = [] if not liniove else _ZNACKA_CARA.findall(liniove.replace("ZnačkaPopis", " "))
            if re.search(r"Značka\s*Popis\s*0\s*Čára plná", liniove):
                styly.append("0")
            spolecne = dict(hladina=cislo, barva=int(barva) if barva is not None else None,
                            zdroj=f"{zdroj}, vrstva {cislo}, objekt {k}")
            kod = f"{cislo}.{k} {popis[:60]}".strip()
            if "text" in popis.lower() or typy == [17] or (vyska and not bunky and not styly and 17 in typy):
                pravidla.append(Rule(kod=kod, nazev=popis[:80] or nazev_vrstvy, geometrie=GeomType.TEXT,
                                     typy_prvku=[17], vyska_textu=vyska, sirka_textu=sirka, font=font,
                                     zarovnani=vztazny.group(1).lower() if vztazny else None, **spolecne))
                continue
            if bunky:
                pravidla.append(Rule(kod=kod + (" (značky)" if styly else ""), nazev=popis[:80] or nazev_vrstvy,
                                     geometrie=GeomType.BOD, typy_prvku=[2], blok="|".join(bunky),
                                     meritko_bunky=1.0, **spolecne))
            if styly or (not bunky and typy and 2 not in typy):
                lin_typy = [t for t in typy if t not in (2, 17)] or [3, 4, 12]
                if 3 in lin_typy and "nulové délky" in obj:
                    geo = GeomType.BOD
                else:
                    geo = GeomType.LINIE
                pravidla.append(Rule(kod=kod, nazev=popis[:80] or nazev_vrstvy, geometrie=geo,
                                     typy_prvku=lin_typy, styl_cary=",".join(dict.fromkeys(styly)) or None,
                                     tloustka=tl if tl is not None else None,
                                     meritko_stylu=1.0 if any(s not in ("0", "0.01") for s in styly) else None,
                                     **spolecne))
    rs = RuleSet(pravidla=pravidla, paleta="microstation")
    rs.meritko = None  # výšky textů jsou ve Směrnici v metrech (pro uvedené měřítko), ne v mm na papíře
    rs.puvodni_meritko = meritko  # type: ignore[attr-defined]
    return rs


def prevod_meritka(rs: RuleSet, z: int, na: int) -> RuleSet:
    """Pravidla pro jiné měřítko: výšky a šířky textů, měřítko buněk a stylů čar × na/z
    (např. Směrnice pro 1:1000 → výkres 1:500 = poloviční velikosti)."""
    k = na / z
    out = copy.deepcopy(rs)
    for r in out.pravidla:
        if r.vyska_textu:
            r.vyska_textu = round(r.vyska_textu * k, 4)
        if r.sirka_textu:
            r.sirka_textu = round(r.sirka_textu * k, 4)
        if r.meritko_bunky:
            r.meritko_bunky = round(r.meritko_bunky * k, 4)
        if r.meritko_stylu:
            r.meritko_stylu = round(r.meritko_stylu * k, 4)
        r.zdroj = (r.zdroj or "") + f" (přepočteno z 1:{z} na 1:{na})"
    out.puvodni_meritko = na  # type: ignore[attr-defined]
    return out
