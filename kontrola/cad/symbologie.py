"""Jednotné pojmenování atributů jako v MicroStationu: barva 0–255, styl čáry 0–7 (nebo vlastní styl
podle kódu), tloušťka wt 0–31, hladina.

DXF ukládá barvu jako ACI (AutoCAD), tloušťku v setinách mm a styl jako typ čáry. CAD i Kontrola výkresu
převádějí mezi nimi stejně, jako to dělá MicroStation při exportu do DXF:
barva MicroStationu → RGB z tabulky barev (color.tbl) → nejbližší ACI; tloušťka wt → mm podle převodní
tabulky ze zadání; styl 0 → plná čára, 1–7 → typ čáry „DGN Style 1“…„DGN Style 7“, vlastní styl → typ čáry
s jeho kódem (např. „2.103“). Textové styly „Style-Arial Narrow“, kurzíva „Style-Arial Narrow IF“.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..rules import RuleSet, ms_index_for_aci, rgb_to_aci

# převod tloušťek, když zadání žádný neurčuje (hodnoty z převodních tabulek zadání: wt 0, 2, 3, 4)
VYCHOZI_TLOUSTKY = {0: 0.0, 2: 0.3, 3: 0.4, 4: 0.53}
_DXF_TLOUSTKY = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211)


@lru_cache(maxsize=1)
def vychozi_tabulka() -> dict[int, tuple[int, int, int]]:
    """Tabulka 256 barev MicroStationu (color.tbl), vestavěná pro výkresy bez vlastní tabulky."""
    p = Path(__file__).resolve().parents[1] / "resources" / "ms_barvy.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return {int(k): (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16)) for k, v in data.items()}


def tabulka(rs: RuleSet | None = None) -> dict[int, tuple[int, int, int]]:
    t = dict(vychozi_tabulka())
    if rs is not None and rs.barevna_tabulka:
        t.update(rs.barevna_tabulka)
    return t


def ms_na_aci(barva: int, rs: RuleSet | None = None) -> int:
    """Barva MicroStationu → ACI, jak ji uloží MicroStation do DXF (nejbližší barva palety AutoCADu)."""
    if not 0 <= int(barva) <= 255:
        raise ValueError("Barva MicroStationu je číslo 0–255.")
    rgb = tabulka(rs).get(int(barva))
    if rgb is None:
        raise ValueError(f"Barva {barva} není v tabulce barev.")
    return min(rgb_to_aci(tuple(rgb)))


def aci_na_ms(aci: int | None, rs: RuleSet | None = None) -> int | None:
    """ACI z DXF → číslo barvy MicroStationu (nejpodobnější); 256 (dle hladiny) → None."""
    if aci is None or aci in (0, 256):
        return None
    return ms_index_for_aci(int(aci), tabulka(rs))


def mapa_tloustek(rs: RuleSet | None = None) -> dict[int, float]:
    m = dict(VYCHOZI_TLOUSTKY)
    if rs is not None and rs.mapa_tloustek:
        m.update({int(k): float(v) for k, v in rs.mapa_tloustek.items()})
    return m


def wt_na_lw(wt: int, rs: RuleSet | None = None) -> tuple[int, bool]:
    """Tloušťka MicroStationu → (DXF lineweight v setinách mm, odhad?).

    Není-li wt v převodní tabulce, odhadne se lineárně mezi známými hodnotami (a vrátí odhad=True)."""
    wt = int(wt)
    if not 0 <= wt <= 31:
        raise ValueError("Tloušťka MicroStationu je číslo 0–31.")
    m = mapa_tloustek(rs)
    if wt in m:
        mm, odhad = m[wt], False
    else:
        kl = sorted(m)
        nizsi = max((k for k in kl if k < wt), default=kl[0])
        vyssi = min((k for k in kl if k > wt), default=None)
        if vyssi is None:  # za koncem tabulky: krok posledních dvou
            a, b = kl[-2], kl[-1]
            mm = m[b] + (wt - b) * (m[b] - m[a]) / (b - a)
        else:
            mm = m[nizsi] + (wt - nizsi) * (m[vyssi] - m[nizsi]) / (vyssi - nizsi)
        odhad = True
    return min(_DXF_TLOUSTKY, key=lambda t: abs(t / 100 - mm)), odhad


def lw_na_wt(lw: int | None, rs: RuleSet | None = None) -> int | None:
    """DXF lineweight → nejbližší tloušťka MicroStationu z převodní tabulky (−1/−2/−3 → None)."""
    if lw is None or lw < 0:
        return None
    m = mapa_tloustek(rs)
    return min(m, key=lambda k: (abs(m[k] - lw / 100), k))


def styl_na_typ(styl) -> str:
    """Styl MicroStationu (0–7 nebo kód vlastního stylu „2.123“) → název typu čáry v DXF."""
    s = str(styl).strip()
    if s in ("0", "", "CONTINUOUS"):
        return "CONTINUOUS"
    if s.isdigit() and 1 <= int(s) <= 7:
        return f"DGN Style {s}"  # jako MicroStation při exportu do DXF
    if re.match(r"^\d+\.[0-9A-Za-z]+$", s):
        return s
    return s.upper()


def typ_na_styl(typ: str | None) -> str:
    """Typ čáry DXF → styl MicroStationu („0“–„7“, kód vlastního stylu, nebo „dle hladiny“)."""
    t = (typ or "BYLAYER").upper()
    if t in ("BYLAYER",):
        return "dle hladiny"
    if t in ("CONTINUOUS", "SOLID", "0"):
        return "0"
    m = re.match(r"^(?:MS|DGN STYLE )([1-7])$", t)
    if m:
        return m.group(1)
    return typ or ""


def zajisti_styly(doc) -> None:
    """Typy čar „DGN Style 1“–„DGN Style 7“ (styly MicroStationu 1–7) ve výkresu."""
    from .zadani import MS_STYLY
    for n, (popis, vzor) in MS_STYLY.items():
        if f"DGN Style {n}" not in doc.linetypes:
            doc.linetypes.add(f"DGN Style {n}", pattern=vzor, description=popis)


def popis_prvku(e, rs: RuleSet | None = None, znama_barva: int | None = None) -> str:
    """„hladina 5 · barva 94 · styl 0 · tloušťka 0“ – jako v MicroStationu.

    ``znama_barva`` = přesné číslo barvy, pokud ho známe (prvek nakreslený v CAD); jinak se odhadne z ACI."""
    d = e.dxf
    b = znama_barva if znama_barva is not None else aci_na_ms(d.get("color", 256), rs)
    w = lw_na_wt(d.get("lineweight", -1), rs)
    casti = [f"hladina {d.get('layer', '0')}", f"barva {b if b is not None else 'dle hladiny'}"]
    if e.dxftype() not in ("TEXT", "MTEXT", "INSERT", "POINT"):
        casti += [f"styl {typ_na_styl(d.get('linetype', 'BYLAYER'))}",
                  f"tloušťka {w if w is not None else 'dle hladiny'}"]
    return " · ".join(casti)
