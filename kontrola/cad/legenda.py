"""Legenda mapy: z prvků, které jsou ve výkresu opravdu použité, sestaví tabulku „vzorek – název“.

Názvy se berou ze zadání (druhy prvků: budovy, ploty, stromy…); bez zadání podle hladin a buněk. Legenda se kreslí
do hladiny ``LEGENDA`` s atributy přímo na prvcích (barva, styl, tloušťka jako v mapě) – Kontrola tuto hladinu
nekontroluje, takže vzorky čar nehlásí jako volné konce."""

from __future__ import annotations

from dataclasses import dataclass

from ..rules import block_matches

VRSTVA = "LEGENDA"
CARY = ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "ELLIPSE")


@dataclass
class Polozka:
    nazev: str
    druh: str  # cara | bunka | bod
    barva: int = 7
    typ_cary: str = "CONTINUOUS"
    tloustka: int = 0
    ltscale: float = 1.0
    blok: str = ""
    meritko: float = 1.0
    pocet: int = 0


def _vlastnosti(doc, e) -> tuple[int, str, int]:
    """Barva, styl a tloušťka prvku s rozepsaným „dle hladiny“ (vzorek leží v jiné hladině)."""
    d = e.dxf
    try:
        ly = doc.layers.get(d.layer)
    except Exception:  # noqa: BLE001
        ly = None
    barva = d.get("color", 256)
    if barva in (256, 0) and ly is not None:
        barva = abs(ly.color) or 7
    lt = (d.get("linetype", "BYLAYER") or "BYLAYER")
    if lt.upper() in ("BYLAYER", "BYBLOCK"):
        lt = ly.dxf.get("linetype", "CONTINUOUS") if ly is not None else "CONTINUOUS"
    lw = d.get("lineweight", -1)
    if lw < 0:
        lw = ly.dxf.get("lineweight", 0) if ly is not None else 0
    return int(barva), lt, max(int(lw), 0)


def polozky(doc, msp, predvolby=()) -> list[Polozka]:
    """Položky legendy v pořadí zadání; prvky bez druhu v zadání se přidají na konec podle hladiny / buňky."""
    cary: dict[tuple, list] = {}
    bunky: dict[tuple, list] = {}
    body: dict[tuple, list] = {}
    for e in msp:
        t = e.dxftype()
        if e.dxf.layer.upper() in (VRSTVA, "RAZITKO", "DEFPOINTS", "KONTROLA_CHYBY"):
            continue
        if t in CARY:
            b, lt, lw = _vlastnosti(doc, e)
            cary.setdefault((e.dxf.layer, b, lt.upper()), []).append(e)
        elif t == "INSERT":
            b, _lt, _lw = _vlastnosti(doc, e)
            bunky.setdefault((e.dxf.layer, e.dxf.name), []).append(e)
        elif t == "POINT":
            b, _lt, _lw = _vlastnosti(doc, e)
            body.setdefault((e.dxf.layer, b), []).append(e)
    out: list[Polozka] = []
    pouzite: set = set()

    def cara(nazev, klice):
        ents = [x for k in klice for x in cary[k]]
        b, lt, lw = _vlastnosti(doc, ents[0])
        out.append(Polozka(nazev, "cara", b, lt, lw, float(ents[0].dxf.get("ltscale", 1.0) or 1.0), pocet=len(ents)))
        pouzite.update(("c", k) for k in klice)

    for p in predvolby or ():
        if p.blok:
            klice = [k for k in bunky if k[0] == p.vrstva and block_matches(p.blok, k[1]) and ("b", k) not in pouzite]
            for k in klice:
                e = bunky[k][0]
                b, _lt, _lw = _vlastnosti(doc, e)
                out.append(Polozka(p.nazev, "bunka", b, blok=k[1], meritko=abs(float(e.dxf.get("xscale", 1.0) or 1.0)),
                                   pocet=len(bunky[k])))
                pouzite.add(("b", k))
        elif p.geometrie in ("linie", "polygon", None):
            stejne = [q for q in predvolby if q is not p and not q.blok and q.geometrie in ("linie", "polygon", None)
                      and q.vrstva == p.vrstva and q.barva == p.barva]
            # dva druhy na stejné hladině a barvě se rozliší stylem čáry – jen když se stylem opravdu liší
            rozlisit = any((q.typ_cary or "").upper() != (p.typ_cary or "").upper() for q in stejne)
            klice = [k for k in cary if k[0] == p.vrstva and k[1] == p.barva and ("c", k) not in pouzite
                     and (not rozlisit or k[2] == (p.typ_cary or "").upper())]
            if klice:
                cara(p.nazev, klice)
        elif p.geometrie == "bod":
            klice = [k for k in body if k[0] == p.vrstva and ("p", k) not in pouzite]
            if klice:
                e = body[klice[0]][0]
                b, _lt, lw = _vlastnosti(doc, e)
                out.append(Polozka(p.nazev, "bod", b, tloustka=lw, pocet=sum(len(body[k]) for k in klice)))
                pouzite.update(("p", k) for k in klice)
    for k in sorted(cary, key=str):
        if ("c", k) not in pouzite:
            styl = "" if k[2] in ("CONTINUOUS", "BYLAYER") else f", styl {k[2].replace('DGN STYLE ', '')}"
            cara(f"{k[0]}{styl}", [k])
    for k in sorted(bunky, key=str):
        if ("b", k) not in pouzite and not k[1].startswith("*"):
            e = bunky[k][0]
            b, _lt, _lw = _vlastnosti(doc, e)
            out.append(Polozka(f"značka {k[1]}", "bunka", b, blok=k[1],
                               meritko=abs(float(e.dxf.get("xscale", 1.0) or 1.0)), pocet=len(bunky[k])))
    return out


def rozmer(n: int, k: float, nejdelsi: int = 24) -> tuple[float, float]:
    """Šířka a výška legendy o ``n`` položkách; ``k`` = jednotek výkresu na 1 mm papíru."""
    return (24.0 + nejdelsi * 2.0 * 0.72 + 6.0) * k, (10.0 + 6.0 * n + 3.0) * k


def nakresli(doc, prostor, historie, polozky_: list[Polozka], roh, k: float, nadpis: str = "LEGENDA",
             styl: str | None = None, kb: float = 1.0) -> list:
    """Nakreslí legendu s levým horním rohem v ``roh``. ``k`` = jednotek výkresu na 1 mm papíru (model v metrech
    v měřítku 1:M → M/1000, výkresový list → 1). Jedna operace historie (jedno Zpět)."""
    if not polozky_:
        raise ValueError("Ve výkresu nejsou žádné prvky do legendy.")
    if VRSTVA not in doc.layers:
        doc.layers.add(VRSTVA, color=7)
    x0, y0 = float(roh[0]), float(roh[1])
    sirka, vyska = rozmer(len(polozky_), k, max(len(p.nazev) for p in polozky_))
    at = {"layer": VRSTVA, "color": 7, "linetype": "CONTINUOUS", "lineweight": 0}
    ts = {"style": styl} if styl and styl in doc.styles else {}
    nove = [prostor.add_lwpolyline([(x0, y0), (x0 + sirka, y0), (x0 + sirka, y0 - vyska), (x0, y0 - vyska)],
                                   close=True, dxfattribs={**at, "lineweight": 25})]
    t = prostor.add_text(nadpis, height=3.0 * k, dxfattribs={**at, **ts})
    t.set_placement((x0 + 3.0 * k, y0 - 6.5 * k))
    nove.append(t)
    for i, p in enumerate(polozky_):
        y = y0 - (13.0 + 6.0 * i) * k
        if p.druh == "cara":
            lt = p.typ_cary if p.typ_cary in doc.linetypes else "CONTINUOUS"
            nove.append(prostor.add_line((x0 + 3.0 * k, y), (x0 + 19.0 * k, y), dxfattribs={
                "layer": VRSTVA, "color": p.barva, "linetype": lt, "lineweight": p.tloustka, "ltscale": p.ltscale * kb}))
        elif p.druh == "bunka" and p.blok in doc.blocks:
            m = p.meritko * kb  # značka ve stejné velikosti jako v mapě (kb = přepočet modelu na list)
            nove.append(prostor.add_blockref(p.blok, (x0 + 11.0 * k, y), dxfattribs={
                "layer": VRSTVA, "color": p.barva, "xscale": m, "yscale": m}))
        else:
            nove.append(prostor.add_point((x0 + 11.0 * k, y), dxfattribs={
                "layer": VRSTVA, "color": p.barva, "lineweight": p.tloustka}))
        t = prostor.add_text(p.nazev, height=2.0 * k, dxfattribs={**at, **ts})
        t.set_placement((x0 + 24.0 * k, y - 1.0 * k))
        nove.append(t)
    if historie is not None:
        historie.proved("Legenda", nove)
    return nove
