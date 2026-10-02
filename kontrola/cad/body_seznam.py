"""Body ze seznamu souřadnic do výkresu CAD (jako import bodů z Gromy do MicroStationu).

Body se umístí na své souřadnice „shodně se světem“ – stejně jako výkresy z MicroStationu v S-JTSK:
x = −Y, y = −X (v metrech). Značka bodu, číslo, výška (a případně kód) se zapíšou do hladin
a s atributy podle pravidel zadání (předvolby). Bod s kódem, který odpovídá buňce ze Směrnice
(např. 9.12, 3.13), se vloží jako buňka, je-li ve výkresu.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..rules import block_matches, split_alternatives


@dataclass
class NastaveniBodu:
    znacka: object | None = None  # Predvolba pro značku bodu (bod / buňka)
    cislo: object | None = None  # Predvolba pro číslo bodu (text)
    vyska: object | None = None  # Predvolba pro výšku (text), None = nevkládat
    kod: object | None = None  # Predvolba pro kód (text), None = nevkládat
    podle_kodu: bool = True  # bod s kódem buňky → buňka
    vyska_textu: float = 1.0  # m, když předvolba výšku neurčuje
    des_vysky: int = 2
    preskocit_existujici: bool = True
    spojnice: object | None = None  # Predvolba pro spojnice z grafiky (linie), None = nevkládat
    spojnice_aktivni: bool = False  # spojnice aktivními atributy (když předvolba není)
    v3d: bool = False  # značky bodů a spojnice ve 3D (souřadnice Z = výška bodu)


def _hleda(pv, *slova, geometrie=None):
    for p in pv:
        n = (p.nazev or "").lower()
        if all(s in n for s in slova) and (geometrie is None or p.geometrie in geometrie):
            return p
    return None


def vychozi_nastaveni(pv) -> NastaveniBodu:
    """Rozumné výchozí předvolby podle názvů pravidel (podrobné body, čísla, výšky)."""
    znacka = (_hleda(pv, "podrobné body polohopisu") or _hleda(pv, "body (elementy)")
              or _hleda(pv, "podrobn", "bod", geometrie=("bod", None)))
    if znacka is not None and znacka.geometrie == "text":
        znacka = None
    cislo = (_hleda(pv, "čísla podrobných") or _hleda(pv, "podrobné body - čísla")
             or _hleda(pv, "čísl", "bod", geometrie=("text",)))
    vyska = (_hleda(pv, "výšky podrobných") or _hleda(pv, "podrobné body - výšk")
             or _hleda(pv, "výšk", "podrobn", geometrie=("text",)))
    return NastaveniBodu(znacka=znacka, cislo=cislo, vyska=vyska)


def _predvolba_kodu(pv, kod: str, doc):
    """Předvolba buňky pro kód bodu (kód = název buňky ze Směrnice, např. 9.12) – jen je-li buňka ve výkresu."""
    if not kod:
        return None, None
    for p in pv:
        if p.blok and any(block_matches(v, kod) for v in split_alternatives(p.blok)):
            jm = next((b.name for b in doc.blocks if block_matches(kod, b.name) or b.name == kod), None)
            if jm:
                return p, jm
    return None, None


def vloz_body(msp, h, body, nast: NastaveniBodu, pv=(), kresleni=None, spojnice=()) -> dict:
    """Vloží body; vrací souhrn {vlozeno, preskoceno, bunky}. Vše jako jedna operace (jedno Zpět)."""
    from . import upravy as U
    doc = msp.doc
    k = kresleni or U.Kresleni(msp, h)
    puvodni = (k.predvolba, k.vrstva)
    nove, preskoceno, bunky = [], 0, 0
    existujici = set()
    if nast.preskocit_existujici and nast.cislo is not None:
        for t in msp.query("TEXT"):
            if t.dxf.layer == nast.cislo.vrstva:
                existujici.add(t.dxf.text.strip())
    pomocna = U.Historie(msp)  # jednotlivé kroky do pomocné historie, do hlavní jedna operace
    k.h = pomocna
    try:
        for b in body:
            if b.cislo in existujici:
                preskoceno += 1
                continue
            x, y = -b.y, -b.x  # shodně se světem: S-JTSK jako v MicroStationu
            z = float(b.z) if nast.v3d and b.z is not None else 0.0
            pk, blok = _predvolba_kodu(pv, (b.kod or "").strip(), doc) if nast.podle_kodu else (None, None)
            if pk is not None:
                k.nastav_predvolbu(pk)
                ins = msp.add_blockref(blok, (x, y, z), dxfattribs=k._attr())
                nove.append(ins)
                bunky += 1
            elif nast.znacka is not None:
                k.nastav_predvolbu(nast.znacka)
                if nast.znacka.blok:
                    _pk, jm = _predvolba_kodu([nast.znacka], split_alternatives(nast.znacka.blok)[0], doc)
                    if jm:
                        nove.append(msp.add_blockref(jm, (x, y, z), dxfattribs=k._attr()))
                        bunky += 1
                    else:
                        nove.append(k.bod((x, y)) if not z else msp.add_point((x, y, z), dxfattribs=k._attr()))
                else:
                    nove.append(k.bod((x, y)) if not z else msp.add_point((x, y, z), dxfattribs=k._attr()))
            for pv_txt, text, posun in ((nast.cislo, b.cislo, (0.6, 0.3)),
                                         (nast.vyska, None if b.z is None else f"{b.z:.{nast.des_vysky}f}",
                                          (0.6, -1.4)),
                                         (nast.kod, b.kod or None, (0.6, -2.6))):
                if pv_txt is None or not text:
                    continue
                k.nastav_predvolbu(pv_txt)
                vys = pv_txt.vyska or nast.vyska_textu
                k.zarovnani = None if pv_txt.zarovnani is None else pv_txt.zarovnani
                nove.append(k.text((x + posun[0] * vys, y + posun[1] * vys), str(text), vys))
        if spojnice and (nast.spojnice is not None or nast.spojnice_aktivni):
            k.nastav_predvolbu(nast.spojnice if nast.spojnice is not None else puvodni[0])
            if nast.spojnice is None:
                k.vrstva = puvodni[1]
            vlozene = {b.cislo for b in body}
            for a, b in spojnice:  # dvojice bodů (Y, X kladné), jen mezi vkládanými body
                if a.cislo in vlozene and b.cislo in vlozene:
                    if nast.v3d and a.z is not None and b.z is not None:
                        nove.append(msp.add_line((-a.y, -a.x, a.z), (-b.y, -b.x, b.z), dxfattribs=k._attr()))
                    else:
                        nove.append(k.usecka((-a.y, -a.x), (-b.y, -b.x)))
    finally:
        k.h = h
        k.nastav_predvolbu(puvodni[0])
        k.vrstva = puvodni[1]
    if nove:
        h.proved(f"Body ze seznamu ({len(body) - preskoceno})", nove)
    return {"vlozeno": len(body) - preskoceno, "preskoceno": preskoceno, "bunky": bunky, "prvky": nove}
