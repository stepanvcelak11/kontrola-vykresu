"""Kresba z kódů bodů do výkresu CAD: linie, plochy a bodové značky podle kódovníku a pravidel zadání
(hladina, barva, tloušťka, styl čáry, buňka). Vše jedna operace – jedno Zpět."""

from __future__ import annotations

from ..geodezie.kodovnik import Kresba
from ..rules import block_matches


def _predvolba(pv, nazev: str):
    if not nazev:
        return None
    n = nazev.strip().lower()
    return (next((p for p in pv if (p.nazev or "").strip().lower() == n), None)
            or next((p for p in pv if n in (p.nazev or "").lower()), None))


def _blok(doc, nazev: str) -> str | None:
    if not nazev:
        return None
    return next((b.name for b in doc.blocks if b.name == nazev), None) or \
        next((b.name for b in doc.blocks if block_matches(nazev, b.name)), None)


def kresli(doc, msp, h, kresba: Kresba, pv=(), kresleni=None, v3d: bool = False) -> dict:
    """Nakreslí kresbu z kódů (``v3d`` = 3D lomené čáry a značky ve výšce bodů).
    Vrací {prvky, linie, plochy, bunky, body, poznamky}."""
    from . import upravy as U
    k = kresleni or U.Kresleni(msp, h)
    puvodni = (k.predvolba, k.vrstva)
    nove, poznamky = [], []
    chybi_styl, chybi_bunka = set(), set()
    n = {"linie": 0, "plochy": 0, "bunky": 0, "body": 0}

    def priprav(kod):
        p = _predvolba(pv, kod.predvolba)
        k.nastav_predvolbu(p)
        if p is None:
            k.vrstva = kod.vrstva or puvodni[1]
        if kod.vrstva:
            k.vrstva = kod.vrstva
        if k.vrstva not in doc.layers:
            doc.layers.add(k.vrstva)
        if kod.styl and kod.druh != "bod":
            if kod.styl in doc.linetypes:
                k.typ_cary = kod.styl
            else:
                chybi_styl.add(kod.styl)

    pomocna = U.Historie(msp)
    k.h = pomocna
    try:
        for lin in kresba.linie:
            priprav(lin.kod)
            body = [(-b.y, -b.x) for b in lin.body]
            try:
                if v3d and all(b.z is not None for b in lin.body):
                    e = msp.add_polyline3d([(-b.y, -b.x, float(b.z)) for b in lin.body], close=lin.uzavrena,
                                           dxfattribs=k._attr())
                else:
                    e = k.polylinie(body, uzavrena=lin.uzavrena)
            except ValueError as ex:
                poznamky.append(f"{lin.kod.kod}: {ex}")
                continue
            nove.append(e)
            n["plochy" if lin.uzavrena else "linie"] += 1
        for kod, b in kresba.bodove:
            priprav(kod)
            jm = _blok(doc, kod.bunka or kod.kod)
            z = float(b.z) if v3d and b.z is not None else 0.0
            if jm:
                nove.append(msp.add_blockref(jm, (-b.y, -b.x, z), dxfattribs=k._attr()))
                n["bunky"] += 1
            else:
                chybi_bunka.add(kod.bunka or kod.kod)
                nove.append(k.bod((-b.y, -b.x)) if not z else msp.add_point((-b.y, -b.x, z), dxfattribs=k._attr()))
                n["body"] += 1
    finally:
        k.h = h
        k.nastav_predvolbu(puvodni[0])
        k.vrstva = puvodni[1]
    if chybi_styl:
        poznamky.append("Styl čáry není ve výkresu (kreslí se plnou čarou): " + ", ".join(sorted(chybi_styl))
                        + " – načtěte styly ze vzorového výkresu (Zadání ▾ → knihovna).")
    if chybi_bunka:
        poznamky.append("Buňka není ve výkresu (vložen bod): " + ", ".join(sorted(chybi_bunka))
                        + " – načtěte buňky z knihovny .cel nebo vzorového DXF.")
    if nove and h is not None:
        h.proved("Kresba z kódů", nove)
    return dict(n, prvky=nove, poznamky=poznamky)
