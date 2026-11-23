"""Rozpis zadání po řádcích Směrnice: „Č. zadání | řádek | řádek | …“ (Word, Excel, text).

Ve škole dostane každý student číslo zadání a k němu několik čísel řádků tabulky Směrnice (např. zadání 1 →
řádky 7, 15, 28, 59, 92, 241, 247 listu „účelová mapa“). Z toho se pak vezmou jen tyto třídy prvků – datový
model úlohy."""

from __future__ import annotations

import re
from pathlib import Path


def z_textu(text: str) -> dict[int, list[int]]:
    """Text tabulky → {číslo zadání: [řádky]}. Počet sloupců se pozná z hlavičky (kolikrát je tam „řádek“)."""
    t = text.replace("\xa0", " ")
    m = re.search(r"zad[aá]n[ií]", t, re.IGNORECASE)
    hlava = t[m.start():] if m else t
    k = len(re.findall(r"\břád(?:ek|ky|ků)\b|\bradek\b", hlava[:400], re.IGNORECASE))
    cisla = [int(x) for x in re.findall(r"\b\d+\b", hlava[m.end() - m.start():] if m else hlava)]
    out: dict[int, list[int]] = {}
    if k >= 1 and len(cisla) >= k + 1:
        # po skupinách k+1 čísel: číslo zadání a jeho řádky; čísla zadání jdou po sobě
        i, cekane = 0, None
        while i + k < len(cisla):
            skup = cisla[i:i + k + 1]
            if len(skup) < k + 1:
                break
            if cekane is not None and skup[0] != cekane:
                break
            out[skup[0]] = skup[1:]
            cekane = skup[0] + 1
            i += k + 1
        if len(out) >= 2:
            return out
    # řádek po řádku: „1  7 15 28 …“
    out = {}
    for radek in t.splitlines():
        c = [int(x) for x in re.findall(r"\b\d+\b", radek)]
        if len(c) >= 2:
            out.setdefault(c[0], c[1:])
    return out


def nacti(cesta: str | Path) -> dict[int, list[int]]:
    p = Path(cesta)
    suf = p.suffix.lower()
    if suf in (".xls", ".xlsx", ".xlsm", ".ods", ".csv"):
        from .table import read_table
        rows = read_table(p).rows
        return z_textu("\n".join(" ".join(c for c in r if str(c).strip()) for r in rows))
    if suf in (".doc", ".docx", ".odt", ".rtf", ".pdf"):
        from .dokument import read_document
        d = read_document(p)
        tab = getattr(d, "tabulky", None) or []
        for tb in tab:
            r = z_textu("\n".join(" ".join(str(c) for c in row) for row in tb))
            if r:
                return r
        return z_textu(d.text)
    from ..vypocet import text_souboru
    return z_textu(text_souboru(p))


def parse_radky(text: str) -> set[int]:
    """„7, 15, 28-30“ → {7, 15, 28, 29, 30}."""
    out: set[int] = set()
    for a, b in re.findall(r"(\d+)\s*(?:[-–]\s*(\d+))?", text or ""):
        a = int(a)
        b = int(b) if b else a
        if b < a:
            a, b = b, a
        if b - a <= 2000:
            out.update(range(a, b + 1))
    return out
