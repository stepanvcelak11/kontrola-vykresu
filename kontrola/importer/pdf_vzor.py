"""Vzor od učitele jako PDF: porovnání popisů (čísla parcel, bodů, č.p.) s kontrolovaným výkresem.

PDF uložené z MicroStationu obsahuje texty jako text, takže je lze přečíst. Porovnávají se jen
„popisy“ – čísla (1001, 125/1, 12a); běžná slova, měřítka a datumy se ignorují.
Sken nebo fotka (JPG) žádný text neobsahuje – ty slouží jen k vizuálnímu porovnání.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model import Drawing, GeomType

_LABEL = re.compile(r"^\d{1,6}(/\d{1,4})?[a-zA-Z]?$")
_SKIP_PREV = ("1:", "měřítko", "meritko")


def _tokens(text: str) -> list[str]:
    text = text.replace("č.p.", " ").replace("č. p.", " ").replace("ev.č.", " ")
    out = []
    for tok in re.split(r"[\s,;()\[\]]+", text):
        tok = tok.strip(".:")
        if _LABEL.match(tok):
            out.append(tok)
    return out


def pdf_labels(path: str | Path) -> set[str]:
    import pdfplumber
    labels: set[str] = set()
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                low = line.lower()
                if any(s in low for s in _SKIP_PREV):
                    continue
                if re.search(r"\d{1,2}\.\s?\d{1,2}\.\s?\d{4}", line):  # datum
                    continue
                labels.update(_tokens(line))
    return labels


def drawing_labels(drawing: Drawing) -> set[str]:
    labels: set[str] = set()
    for f in drawing.features:
        if f.geom_type == GeomType.TEXT and f.text:
            labels.update(_tokens(f.text))
        for t in f.display_texts:
            labels.update(_tokens(t[0]))
        for k, v in f.attributes.items():
            if k in ("CISLO", "CISLO_BODU", "CB", "CP", "PARCELA", "PARC_CISLO") and v:
                labels.update(_tokens(str(v)))
    return labels


def _sort_key(s: str):
    m = re.match(r"(\d+)(?:/(\d+))?([a-zA-Z]?)", s)
    return (int(m.group(1)), int(m.group(2) or 0), m.group(3)) if m else (0, 0, s)


def compare_labels(vzor: set[str], drawing: Drawing) -> tuple[list[str], list[str]]:
    """Vrací (chybí ve výkresu, navíc ve výkresu)."""
    have = drawing_labels(drawing)
    return sorted(vzor - have, key=_sort_key), sorted(have - vzor, key=_sort_key)
