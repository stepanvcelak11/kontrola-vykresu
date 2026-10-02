"""Zápisník měření (jako zápisník Gromy): načtení .zap / GSI, zápis .zap, příprava pro výpočet."""

from __future__ import annotations

import copy
from pathlib import Path

from ..vypocet import Obs, Station, _merge_faces, read_zap


def nacti(cesta: str | Path, dane: set[str] | None = None) -> list[Station]:
    """Zápisník .zap (Groma) nebo GSI (Leica) – měření tak, jak jsou zapsaná (obě polohy zvlášť)."""
    from .gsi import je_gsi, read_gsi
    text = Path(cesta).read_bytes()[:4000].decode("cp1250", errors="replace")
    if not je_gsi(text):
        return read_zap(cesta, spojit=False)
    stations, _var = read_gsi(cesta)
    dane = dane or set()
    for st in stations:  # orientace = dané body na začátku stanoviska (jako při výpočtu)
        n = 0
        while n < len(st.detail) and st.detail[n].bod in dane and st.detail[n].bod != st.bod:
            n += 1
        st.orient, st.detail = st.detail[:n], st.detail[n:]
    return stations


def _f(v: float, d: int) -> str:
    return f"{v:.{d}f}"


def zapis_zap(stations: list[Station], zakazka: str = "") -> str:
    """Text zápisníku ve formátu Gromy (čte ho Groma i tato aplikace)."""
    r = [f";Zakazka:{zakazka}"] if zakazka else []
    for st in stations:
        r.append(f"1 {st.bod:<10} {_f(st.vp, 3)} *")
        for o in st.orient:
            r.append(f"{o.bod:<12}{_f(o.sd, 3):>9}{_f(o.vc, 3):>8}{_f(o.hz, 4):>10}{_f(o.z, 4):>10}")
        r.append("-1")
        for o in st.detail:
            r.append(f"{o.bod:<12}{_f(o.sd, 3):>9}{_f(o.vc, 3):>8}{_f(o.hz, 4):>10}{_f(o.z, 4):>10}")
        r.append("/")
    return "\n".join(r) + "\n"


def pro_vypocet(stations: list[Station]) -> list[Station]:
    """Kopie stanovisek se zprůměrovanými polohami dalekohledu (vstup výpočtu polární metody)."""
    out = []
    for st in stations:
        c = Station(st.bod, st.vp)
        c.orient = _merge_faces([Obs(o.bod, o.sd, o.vc, o.hz, o.z) for o in st.orient])
        c.detail = _merge_faces([Obs(o.bod, o.sd, o.vc, o.hz, o.z) for o in st.detail])
        out.append(c)
    return out


def zkontroluj(stations: list[Station]) -> list[str]:
    """Srozumitelná upozornění na zjevné chyby v zápisníku (před výpočtem)."""
    out = []
    for st in stations:
        if not st.orient:
            out.append(f"Stanovisko {st.bod}: chybí orientace.")
        if not 0 <= st.vp < 3:
            out.append(f"Stanovisko {st.bod}: neobvyklá výška přístroje {st.vp:.3f} m.")
        for o in st.orient + st.detail:
            if o.sd <= 0:
                out.append(f"St. {st.bod}, bod {o.bod}: délka musí být kladná.")
            if not 0 <= o.hz < 400 or not 0 < o.z < 400:
                out.append(f"St. {st.bod}, bod {o.bod}: úhel mimo 0–400 gon.")
            if o.vc < 0 or o.vc > 10:
                out.append(f"St. {st.bod}, bod {o.bod}: neobvyklá výška cíle {o.vc:.3f} m.")
    return out


def kopie(stations: list[Station]) -> list[Station]:
    return copy.deepcopy(stations)


def vyrovnani_site(stanoviska: list[Station], body, sigma_smer_cc: float = 10.0, sigma_delka_mm: float = 3.0,
                   sigma_ppm: float = 2.0):
    """Vyrovnání sítě MNČ ze zápisníku: směry a vodorovné délky redukované do zobrazení; pevné body = ``body``
    (seznam souřadnic). Body určené jen jednou (rajóny) síť nezpevní, do vyrovnání nejdou.
    Vrací (VysledekVyrovnani, text protokolu)."""
    import math

    from ..vypocet import krovak_scale
    from . import vyrovnani as VR
    pevne = {b.cislo: (b.y, b.x) for b in body}
    if not pevne:
        raise ValueError("V seznamu souřadnic nejsou pevné body.")
    ys = [v[0] for v in pevne.values()]
    xs = [v[1] for v in pevne.values()]
    zs = [b.z for b in body if b.z is not None]
    m = krovak_scale(sum(ys) / len(ys), sum(xs) / len(xs), sum(zs) / len(zs) if zs else 0.0)
    smery, delky = [], []
    for st in pro_vypocet(stanoviska):
        for o in st.orient + st.detail:
            smery.append(VR.Smer(st.bod, o.bod, o.hz))
            delky.append(VR.Delka(st.bod, o.bod, o.sd * math.sin(o.z * VR.GON) * m))
    pocet: dict[str, int] = {}
    for s in smery:
        pocet[s.cil] = pocet.get(s.cil, 0) + 1
    sit = {b for b, n in pocet.items() if n >= 2 or b in pevne} | {s.st for s in smery}
    smery = [s for s in smery if s.cil in sit]
    delky = [d for d in delky if d.cil in sit]
    v = VR.vyrovnej(smery, delky, pevne, sigma_smer_cc, sigma_delka_mm, sigma_ppm)
    return v, "\n".join(VR.protokol(v, sigma_smer_cc, sigma_delka_mm, sigma_ppm))
