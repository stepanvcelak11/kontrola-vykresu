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
    tvar: int | None = None  # tvar značky bodu ($PDMODE: 0 tečka, 2 +, 3 ×, 32 kroužek, 34 kroužek s +)
    velikost_znacky: float | None = None  # m ($PDSIZE), None = beze změny
    bunka: str | None = None  # značka bodu jako buňka (blok) – vlastní volba bez zadání
    meritko_bunky: float = 1.0


TVARY = {"tečka": 0, "křížek +": 2, "křížek ×": 3, "kroužek": 32, "kroužek s křížkem": 34}


def odhad_vysky_textu(body) -> float:
    """Výška čísel bodů podle hustoty bodů (čtvrtina typické vzdálenosti k nejbližšímu bodu), 0,2–2 m –
    husté body z podrobného měření nesmí překrýt kresbu obřími čísly."""
    import math
    pts = [(b.y, b.x) for b in body if b.y is not None and b.x is not None][:400]
    if len(pts) < 2:
        return 1.0
    nn = []
    for i, (y, x) in enumerate(pts):
        d = min(math.hypot(y - y2, x - x2) for j, (y2, x2) in enumerate(pts) if j != i)
        if d > 1e-6:
            nn.append(d)
    if not nn:
        return 1.0
    nn.sort()
    typ = nn[len(nn) // 2]
    v = max(0.2, min(2.0, typ * 0.25))
    return round(v * 10) / 10 if v >= 0.5 else round(v * 20) / 20


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
    for pv_ in (nast.znacka, nast.cislo, nast.vyska, nast.kod, nast.spojnice):  # hladiny, které ve výkresu nejsou
        jm = getattr(pv_, "vrstva", None)
        if jm and jm not in doc.layers:
            doc.layers.add(jm)
    if nast.tvar is not None:
        doc.header["$PDMODE"] = int(nast.tvar)
    if nast.velikost_znacky is not None:
        doc.header["$PDSIZE"] = float(nast.velikost_znacky)
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
            elif nast.znacka is not None and nast.bunka and nast.bunka in doc.blocks:
                k.nastav_predvolbu(nast.znacka)
                m = nast.meritko_bunky or 1.0
                nove.append(msp.add_blockref(nast.bunka, (x, y, z), dxfattribs=k._attr(xscale=m, yscale=m)))
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
            else:  # bez zadání: bod v aktivní hladině
                nove.append(k.bod((x, y)) if not z else msp.add_point((x, y, z), dxfattribs=k._attr()))
            if nast.cislo is None and nast.znacka is None and pk is None:  # bez zadání: číslo bodu vedle
                vys = nast.vyska_textu or 1.0
                nove.append(k.text((x + 0.6 * vys, y + 0.3 * vys), str(b.cislo), vys))
            for pv_txt, text, posun in ((nast.cislo, b.cislo, (0.6, 0.3)),
                                         (nast.vyska, None if b.z is None else f"{b.z:.{nast.des_vysky}f}",
                                          (0.6, -1.4)),
                                         (nast.kod, b.kod or None, (0.6, -2.6))):
                if pv_txt is None or not text:
                    continue
                k.nastav_predvolbu(pv_txt)
                vys = pv_txt.vyska or nast.vyska_textu
                k.zarovnani = None if pv_txt.zarovnani is None else pv_txt.zarovnani
                if pv_txt.zarovnani:  # text se zarovnáním (textový styl): od bodu na stranu, kam zarovnání míří
                    z = pv_txt.zarovnani
                    posun = (0.6 if "LEFT" in z else -0.6 if "RIGHT" in z else 0.0,
                             -0.4 if "TOP" in z else 0.4 if "BOTTOM" in z else 0.0)
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
