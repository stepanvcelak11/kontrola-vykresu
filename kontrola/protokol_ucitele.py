"""Porovnání výsledků aplikace s protokolem od učitele (GISoft „Kontrola a změna symbologie“, MGEO).

Protokol GISoft má skupiny chybných prvků::

    8      Název vrstvy: Vrstva 7, Číslo vrstvy: 7, Typ prvku: Lomená čára
           Barva: 93, Styl: 2.103 (Měřítko(!): 1.0), Tloušťka: 0
           Font(!): cs_Nimbus Sans C I (159), Výška: 0.75, Šířka(!): 0.5

Číslo na začátku je počet prvků, „(!)“ označuje chybný atribut. Porovnává se podle vrstvy
a množiny chybných atributů. Z protokolu MGEO (topologie) se čtou řádky „text : počet“.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .export.mgeo_log import issue_groups

_KEYS = [  # (regex názvu atributu v protokolu, pole)
    (r"název vrstvy|číslo vrstvy|vrstva|level", "vrstva"),
    (r"typ prvku", "typ"),
    (r"barva|color", "barva"),
    (r"měřítko|meritko|scale", "měřítko stylu"),
    (r"styl|style", "styl"),
    (r"tloušťka|tloustka|weight", "tloušťka"),
    (r"font", "font"),
    (r"výška|vyska|height", "výška"),
    (r"šířka|sirka|width", "šířka"),
    (r"zarovnání|zarovnani|justification", "zarovnání"),
    (r"název buňky|nazev bunky|buňka|bunka|cell", "buňka"),
]
FIELD_LABEL = {"vrstva": "vrstva", "typ": "typ prvku", "barva": "barva", "měřítko stylu": "měřítko stylu",
               "styl": "styl", "tloušťka": "tloušťka", "font": "font", "výška": "výška textu",
               "šířka": "šířka textu", "zarovnání": "zarovnání", "buňka": "buňka"}


def _field(name: str) -> str | None:
    n = name.strip().lower()
    for rx, f in _KEYS:
        if re.fullmatch(rx, n) or re.match(rf"^({rx})\b", n):
            return f
    return None


@dataclass
class Skupina:
    pocet: int
    vrstva: str
    spatne: frozenset[str]
    radky: list[str] = field(default_factory=list)


@dataclass
class Protokol:
    skupiny: list[Skupina]
    topologie: dict[str, int]
    celkem: int | None


def read_teacher_log(path: str | Path) -> Protokol:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1250", "cp852", "latin-1"):
        try:
            text = raw.decode(enc)
            if enc != "latin-1" and "�" in text:
                continue
            break
        except UnicodeDecodeError:
            continue
    groups: list[Skupina] = []
    cur: Skupina | None = None
    topo: dict[str, int] = {}
    total = None
    head = re.compile(r"^\s*(\d+)\s+(?:N[áa]zev vrstvy|Vrstva|Level)\s*(\(!\))?\s*:\s*([^,]+)", re.IGNORECASE)
    # novější verze (13.x): „3      Objekt: ID [68]“ a vrstva až na dalším řádku
    head_obj = re.compile(r"^\s*(\d+)\s+Objekt\s*:", re.IGNORECASE)
    vrstva_rx = re.compile(r"N[áa]zev vrstvy\s*(?:\(!\))?\s*:\s*([^,]+)", re.IGNORECASE)
    for line in text.splitlines():
        m = head.match(line)
        if m:
            cur = Skupina(int(m.group(1)), m.group(3).strip(), frozenset(), [line.strip()])
            groups.append(cur)
            _collect(cur, line)
            continue
        m = head_obj.match(line)
        if m:
            cur = Skupina(int(m.group(1)), "", frozenset(), [line.strip()])
            groups.append(cur)
            continue
        if cur is not None and line.startswith((" ", "\t")) and line.strip():
            if not cur.vrstva:
                mv = vrstva_rx.search(line)
                if mv:
                    cur.vrstva = mv.group(1).strip()
            cur.radky.append(line.strip())
            _collect(cur, line)
            continue
        if line.strip().startswith("---"):
            cur = None
        mt = re.match(r"^\s*Celkem chyb\s*:\s*(\d+)", line, re.IGNORECASE)
        if mt:
            total = int(mt.group(1))
            continue
        mp = re.match(r"^\s*(Počet [^:]+?)\s*:\s*(\d+)\s*$", line)
        if mp:
            topo[mp.group(1).strip()] = int(mp.group(2))
    return Protokol(groups, topo, total)


def _collect(g: Skupina, line: str):
    wrong = set(g.spatne)
    bunka = bool(re.search(r"N[áa]zev bu[ňn]ky", line, re.IGNORECASE))
    for m in re.finditer(r"([A-Za-zÁ-žěščřžýáíéůúťďň .]+?)\(!\)\s*:", line):
        f = _field(m.group(1).strip().strip(",("))
        if f == "měřítko stylu" and bunka:
            f = "buňka"  # „Měřítko(!)“ na řádku buňky je měřítko buňky, ne stylu čáry
        if f:
            wrong.add(f)
    g.spatne = frozenset(wrong)


@dataclass
class Radek:
    vrstva: str
    spatne: frozenset[str]
    ucitel: int
    program: int

    @property
    def popis(self) -> str:
        return ", ".join(FIELD_LABEL.get(f, f) for f in sorted(self.spatne)) or "–"


def compare_with_teacher(prot: Protokol, drawing, rules, issues) -> tuple[list[Radek], str]:
    """Porovná skupiny chyb učitele a programu. Vrací řádky a souhrn."""
    groups, samples = issue_groups(drawing, rules, issues)
    ours: Counter = Counter()
    for key, n in groups.items():
        a, wrong = samples[key]
        w = set(wrong)
        if "vrstva" in w:
            w.discard("číslo")
        ours[(a["vrstva"], frozenset(w))] += n
    theirs: Counter = Counter()
    for g in prot.skupiny:
        theirs[(g.vrstva, g.spatne)] += g.pocet
    rows = []
    for key in sorted(set(ours) | set(theirs), key=lambda k: (_lnum(k[0]), k[0], sorted(k[1]))):
        rows.append(Radek(key[0], key[1], theirs.get(key, 0), ours.get(key, 0)))
    t_total = sum(theirs.values())
    both = sum(min(r.ucitel, r.program) for r in rows)
    missing = sum(max(0, r.ucitel - r.program) for r in rows)
    extra = sum(max(0, r.program - r.ucitel) for r in rows)
    summary = (f"Učitel: {t_total} chybných prvků v {len(theirs)} skupinách. Program našel stejně {both}, "
               f"nenašel {missing}, navíc hlásí {extra}.")
    return rows, summary


def _lnum(layer: str) -> int:
    m = re.search(r"(\d+)\s*$", layer or "")
    return int(m.group(1)) if m else 9999
