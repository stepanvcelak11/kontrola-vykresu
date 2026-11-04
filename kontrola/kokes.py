"""Výkresy z Kokeše (GEPRO): převody čísel podle Zadání Kokeš a rozpoznání kreslícího klíče.

Ze zadání (Zadaní-Kokeš.doc):

* číslo barvy v Kokeši = číslo barvy v MicroStationu, jen barva 0 MicroStationu je v Kokeši 100;
* kreslící klíče (KK) jsou ve sloupci KK Směrnice-výběr.xls, styl 4 MicroStationu je v Kokeši −13;
* texty se barví zvláštním klíčem 1xx, kde xx je číslo barvy textu (175 = popis povrchů barvou 75);
* font 1 MicroStationu je v Kokeši font 2;
* odevzdává se Prijmeni_cz_xx.vyk (výkres) a Prijmeni_cz_xx.ss (seznam souřadnic).

Vlastní formát Kokeše (.vyk, .ss) je binární – kontroluje se jeho export do DXF/DGN (v Kokeši
export výkresu do DXF) a textový export seznamu souřadnic.
"""

from __future__ import annotations

import re

PRIPONY = (".vyk", ".vtx", ".ss")

NAVOD = (
    "Soubor {nazev} je ve vlastním formátu Kokeše – ten aplikace přímo nepřečte.\n\n"
    "Výkres: v Kokeši ho vyexportujte do DXF (export výkresu v nabídce Soubor) a DXF otevřete tady. "
    "Barvy, kreslící klíče a vrstvy se při kontrole převedou podle Zadání Kokeš (barva 100 = 0, "
    "styl −13 = 4, klíče ze sloupce KK Směrnice) – v Zadání → Pravidla nastavte „Výkres kreslen v: Kokeš“.\n\n"
    "Seznam souřadnic (.ss): v Kokeši ho vyexportujte jako textový seznam „číslo Y X Z“ a nahrajte "
    "do Zadání → Podklady nebo do Výpočtů."
)

_KLIC_ATR = ("KK", "KRESLICI_KLIC", "KRESLICIKLIC", "KLIC", "KOKES_KK")
_KLIC_TYP = re.compile(r"^(?:KK[_ ]?)?(-?\d{1,4})$", re.IGNORECASE)


def navod(nazev: str) -> str:
    return NAVOD.format(nazev=nazev)


def barva_kokes_na_ms(n: int | str | None) -> int | None:
    """Číslo barvy Kokeše → MicroStation (100 → 0, ostatní stejně)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return 0 if n == 100 else n


def styl_kokes_na_ms(s: str | None) -> str | None:
    return "4" if str(s or "").strip() == "-13" else s


def klic_prvku(f) -> int | None:
    """Kreslící klíč prvku: z atributu (KK…) nebo z názvu typu čáry („13“, „-13“, „KK13“)."""
    for k in _KLIC_ATR:
        v = (f.attributes or {}).get(k)
        if v not in (None, ""):
            try:
                return int(float(str(v).replace(",", ".")))
            except ValueError:
                pass
    m = _KLIC_TYP.match(str(f.linetype or "").strip())
    return int(m.group(1)) if m else None


def klic_v_rozsahu(vzor: str | None, klic: int) -> bool:
    """„1-4“, „20“, „1-4,9“ obsahuje klíč? (rozsahy celých čísel ze sloupce KK)."""
    if not vzor:
        return True
    for cast in re.split(r"[,;|]", str(vzor)):
        cast = cast.strip()
        m = re.match(r"^(-?\d+)\s*[-–—]\s*(-?\d+)$", cast)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if min(a, b) <= klic <= max(a, b):
                return True
        elif re.fullmatch(r"-?\d+", cast) and int(cast) == klic:
            return True
    return False


def barva_textu_z_klice(klic: int | None) -> int | None:
    """Textový klíč 1xx → barva xx (175 → 75)."""
    if klic is not None and 100 <= klic <= 199:
        return klic - 100
    return None
