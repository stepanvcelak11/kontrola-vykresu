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
    info: object | None = None  # Predvolba pro druhý bod „Informace o bodu“ (import Gromou ve škole)
    vyskova_znacka: object | None = None  # Predvolba buňky u každého bodu (ÚM: 9.12 podrobný výškový bod)
    kratka_cisla: bool = False  # číslo bodu ve výkresu bez předčíslí a úvodních nul (610844000130001 → 1)
    na_bod: float | None = None  # měřítko anotací: číslo těsně u bodu, výška zarovnaná přesně na bod


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


HLADINA_UM = "GS01-body-poloha"  # podle ní se pozná výkres Účelové mapy (pracovní sada MultiScale)


def nastaveni_um(doc, rs=None, anotace: int | None = None) -> NastaveniBodu:
    """Import bodů přesně podle atributové tabulky Účelové mapy (jako import Gromou do MicroStationu ve škole):
    bod v GS01-body-poloha a GS01-body-info (barva 5, tloušťka 4), číslo bez předčíslí v GS01-body-čísla
    (Arial Narrow kurzíva 0,3 mm), výška na dvě desetinná místa v GS09-výškopis-body podrobné-výšky
    (Arial Narrow 0,6 / 0,3 mm, barva 70) a značka 9.12 v GS09-výškopis-body podrobné-buňky (barva 70).
    Velikosti jsou v mm na papíře – přepočte je měřítko anotací."""
    from . import symbologie as SY
    from .dokument import _textovy_styl
    from .zadani import Predvolba
    b5, b70 = SY.ms_na_aci(5, rs), SY.ms_na_aci(70, rs)
    lw4 = SY.wt_na_lw(4, rs)[0]
    # styl čáry výslovně 0 (ne „dle hladiny“) – jinak ho hlásí kontrola atributů dle vrstvy
    bod = dict(geometrie="bod", nastroj="bod", barva=b5, tloustka=lw4, typ_cary="CONTINUOUS", ms={"barva": 5})
    return NastaveniBodu(
        znacka=Predvolba(nazev="Body (elementy)", vrstva=HLADINA_UM, **bod),
        info=Predvolba(nazev="Informace o bodu", vrstva="GS01-body-info", **bod),
        cislo=Predvolba(nazev="Podrobné body - čísla", geometrie="text", nastroj="text", vrstva="GS01-body-čísla",
                        barva=b5, vyska=0.3, zarovnani="TOP_LEFT", ms={"barva": 5},
                        textovy_styl=_textovy_styl(doc, "Arial Narrow", True)),
        vyska=Predvolba(nazev="Podrobné body - výškové kóty", geometrie="text", nastroj="text",
                        vrstva="GS09-výškopis-body podrobné-výšky", barva=b70, vyska=0.6, sirka_faktor=0.5,
                        zarovnani="CENTER", ms={"barva": 70}, textovy_styl=_textovy_styl(doc, "Arial Narrow", False)),
        vyskova_znacka=Predvolba(nazev="Podrobné výškové body - bodové značky", geometrie="bod", nastroj="vlož",
                                 vrstva="GS09-výškopis-body podrobné-buňky", barva=b70, blok="9.12",
                                 meritko_bunky=0.001, ms={"barva": 70}),  # jako Groma: 1:200 → měřítko 0,2
        podle_kodu=False, kratka_cisla=True, na_bod=float(anotace or 1000), tvar=0, des_vysky=2)


def kratke_cislo(cislo: str) -> str:
    """Číslo bodu pro popis ve výkresu: z úplného čísla (k.ú. + ZPMZ + číslo) jen vlastní číslo bez nul."""
    c = (cislo or "").strip()
    if len(c) >= 8 and c.isdigit() and int(c[-4:]):  # 15 míst (k.ú. + ZPMZ), 12 míst (Groma), 10 míst (škola)
        return str(int(c[-4:]))
    return c


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
    for pv_ in (nast.znacka, nast.cislo, nast.vyska, nast.kod, nast.spojnice, nast.info, nast.vyskova_znacka):
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
            if (kratke_cislo(b.cislo) if nast.kratka_cisla else b.cislo) in existujici:
                preskoceno += 1
                continue
            # shodně se světem: S-JTSK jako v MicroStationu; na mm jako v seznamu souřadnic (Groma)
            x, y = -round(b.y, 3), -round(b.x, 3)
            z = round(float(b.z), 3) if nast.v3d and b.z is not None else 0.0
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
            if nast.info is not None:  # druhý bod s informacemi o bodu (ve škole ho vkládá Groma)
                k.nastav_predvolbu(nast.info)
                nove.append(msp.add_point((x, y, z), dxfattribs=k._attr()))
            vz = nast.vyskova_znacka
            if vz is not None and vz.blok and vz.blok in doc.blocks:
                k.nastav_predvolbu(vz)
                m = vz.meritko_bunky or 1.0
                nove.append(msp.add_blockref(vz.blok, (x, y, z), dxfattribs=k._attr(xscale=m, yscale=m)))
                bunky += 1
            if nast.cislo is None and nast.znacka is None and pk is None:  # bez zadání: číslo bodu vedle
                vys = nast.vyska_textu or 1.0
                nove.append(k.text((x + 0.6 * vys, y + 0.3 * vys), str(b.cislo), vys))
            for pv_txt, text, posun in ((nast.cislo, kratke_cislo(b.cislo) if nast.kratka_cisla else b.cislo,
                                          (0.6, 0.3)),
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
                if nast.na_bod:  # jako import Gromou: číslo těsně u bodu, výška zarovnaná přesně na bod
                    o = 1e-5 * nast.na_bod if pv_txt is nast.cislo else 0.0
                    posun, vys_p = (o, -o), 1.0
                else:
                    vys_p = vys
                nove.append(k.text((x + posun[0] * vys_p, y + posun[1] * vys_p), str(text), vys))
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
