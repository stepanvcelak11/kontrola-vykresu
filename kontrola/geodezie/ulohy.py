"""Geodetické úlohy nad seznamem souřadnic: formulář → výpočet → protokol → nové body do seznamu.

Bez Qt – používá je desktopová stránka Výpočty i webová verze.

Každá úloha je popsaná daty (pole formuláře) a funkcí výpočtu; chyby vstupu se ukážou srozumitelně
(neznámý bod, chybějící číslo, nesmyslná geometrie), nikdy nespadnou.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field

from . import vypocty as V
from .body import Bod, SeznamBodu, klic_cisla


class ChybaVstupu(ValueError):
    pass


@dataclass
class Vysledek:
    protokol: list[str]
    nove: list[Bod] = field(default_factory=list)


@dataclass
class Pole:
    key: str
    label: str
    typ: str = "bod"  # bod | gon | m | text | volba | radky | cislo_noveho
    vychozi: str = ""
    volby: tuple = ()
    napoveda: str = ""


# ------------------------------------------------------------------ pomocné
def _f(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}"


def _bod(seznam: SeznamBodu, h: dict, key: str, nazev: str) -> Bod:
    c = (h.get(key) or "").strip()
    if not c:
        raise ChybaVstupu(f"Vyplňte {nazev}.")
    b = seznam.najdi(c)
    if b is None:
        raise ChybaVstupu(f"Bod {c} ({nazev}) v seznamu souřadnic není.")
    return b


def _cislo(h: dict, key: str, nazev: str) -> float:
    t = (h.get(key) or "").strip().replace(",", ".")
    if not t:
        raise ChybaVstupu(f"Vyplňte {nazev}.")
    try:
        v = float(t)
    except ValueError:
        raise ChybaVstupu(f"{nazev}: „{t}“ není číslo.") from None
    if not math.isfinite(v):
        raise ChybaVstupu(f"{nazev}: „{t}“ není konečné číslo.")
    return v


def _ruzne(a: Bod, b: Bod) -> None:
    if math.hypot(a.y - b.y, a.x - b.x) < 1e-9:
        raise ChybaVstupu(f"Body {a.cislo} a {b.cislo} jsou na stejném místě – zvolte dva různé body.")


def _nove_cislo(seznam: SeznamBodu, h: dict, key: str = "nove") -> str:
    c = (h.get(key) or "").strip()
    if not c:
        raise ChybaVstupu("Vyplňte číslo nového bodu.")
    return c


def _radky_bodu(seznam: SeznamBodu, text: str) -> list[Bod]:
    cisla = [c for c in text.replace(",", " ").replace(";", " ").split() if c]
    out = []
    for c in cisla:
        b = seznam.najdi(c)
        if b is None:
            raise ChybaVstupu(f"Bod {c} v seznamu souřadnic není.")
        out.append(b)
    return out


def _hlavicka(nazev: str) -> list[str]:
    """Nadpis úlohy jako ve výpočetním protokolu: velkými písmeny, podtržený, s datem výpočtu."""
    t = nazev.upper()
    return [t, "=" * len(t), f"Vypočteno: {dt.datetime.now():%d.%m.%Y %H:%M}"]


# ------------------------------------------------------------------ úlohy
def u_smernik(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    p = _hlavicka("Směrník a délka")
    p += [f"z bodu {a.cislo} na bod {b.cislo}",
          f"  směrník σ = {_f(V.smernik(a, b), 4)} gon",
          f"  délka   d = {_f(V.delka(a, b))} m",
          f"  ΔY = {_f(b.y - a.y)} m, ΔX = {_f(b.x - a.x)} m"]
    if a.z is not None and b.z is not None:
        p.append(f"  převýšení Δh = {_f(b.z - a.z)} m")
    return Vysledek(p)


def u_rajon(s, h):
    st, o = _bod(s, h, "st", "stanovisko"), _bod(s, h, "o", "orientaci")
    _ruzne(st, o)
    so, sm, d = _cislo(h, "so", "směr na orientaci"), _cislo(h, "sm", "měřený směr"), _cislo(h, "d", "délku")
    if d <= 0:
        raise ChybaVstupu("Délka musí být kladná.")
    n = _nove_cislo(s, h)
    posun = V.norm_gon(V.smernik(st, o) - so)
    sig = V.norm_gon(sm + posun)
    p = V.rajon(st, sig, d)
    z = None
    if st.z is not None and (h.get("dh") or "").strip():
        z = st.z + _cislo(h, "dh", "převýšení")
    prot = _hlavicka("Rajón (polární bod)")
    prot += [f"stanovisko {st.cislo}, orientace na {o.cislo}: směrník {_f(V.smernik(st, o), 4)} gon, "
             f"směr {_f(so, 4)} gon → posun {_f(posun, 4)} gon",
             f"bod {n}: směr {_f(sm, 4)} gon → směrník {_f(sig, 4)} gon, délka {_f(d)} m",
             f"  Y = {_f(p.y)}   X = {_f(p.x)}" + (f"   Z = {_f(z)}" if z is not None else "")]
    return Vysledek(prot, [Bod(n, p.y, p.x, z, poznamka="rajón")])


def u_vpred_uhly(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    alfa, beta = _cislo(h, "alfa", "úhel α"), _cislo(h, "beta", "úhel β")
    n = _nove_cislo(s, h)
    try:
        p = V.protinani_vpred_uhly(a, b, alfa, beta)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    g = 400 - alfa - beta
    prot = _hlavicka("Protínání vpřed z úhlů")
    prot += [f"základna {a.cislo}–{b.cislo}: {_f(V.delka(a, b))} m, α = {_f(alfa, 4)} gon, β = {_f(beta, 4)} gon",
             f"úhel na určovaném bodě γ = {_f(V.norm_gon(200 - alfa - beta) if g > 200 else 200 - alfa - beta, 4)} "
             "gon" + ("  (POZOR: ostrý úhel protnutí, výsledek je nejistý)" if min(abs(200 - alfa - beta), 400) < 30
                      else ""),
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="protínání vpřed")])


def u_z_delek(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    da, db = _cislo(h, "da", "délku z A"), _cislo(h, "db", "délku z B")
    n = _nove_cislo(s, h)
    vlevo = (h.get("strana") or "vlevo") == "vlevo"
    try:
        p = V.protinani_z_delek(a, b, da, db, vlevo=vlevo)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Protínání z délek")
    prot += [f"{a.cislo}–{b.cislo}: {_f(V.delka(a, b))} m, dA = {_f(da)} m, dB = {_f(db)} m, bod "
             f"{'vlevo' if vlevo else 'vpravo'} od směru {a.cislo}→{b.cislo}",
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="protínání z délek")])


def u_zpet(s, h):
    a, b, c = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B"), _bod(s, h, "c", "bod C")
    sa, sb, sc = _cislo(h, "sa", "směr na A"), _cislo(h, "sb", "směr na B"), _cislo(h, "sc", "směr na C")
    n = _nove_cislo(s, h)
    try:
        p = V.protinani_zpet(a, b, c, sa, sb, sc)
    except (ValueError, ZeroDivisionError):
        raise ChybaVstupu("Stanovisko nejde určit – body leží na nebezpečné kružnici nebo jsou směry chybné.") \
            from None
    o = V.orientace(p, [(a.cislo, a, sa), (b.cislo, b, sb), (c.cislo, c, sc)])
    prot = _hlavicka("Protínání zpět (ze tří bodů)")
    prot += [f"směry: {a.cislo} {_f(sa, 4)}, {b.cislo} {_f(sb, 4)}, {c.cislo} {_f(sc, 4)} gon",
             f"stanovisko {n}:  Y = {_f(p.y)}   X = {_f(p.x)}",
             f"orientační posun {_f(o.posun, 4)} gon"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="protínání zpět")])


def u_volne(s, h):
    mer = []
    for i, line in enumerate((h.get("mereni") or "").splitlines(), 1):
        parts = line.replace(",", ".").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „číslo_bodu směr délka“.")
        b = s.najdi(parts[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {parts[0]} v seznamu není.")
        try:
            sm_, d_ = float(parts[1]), float(parts[2])
            if not (math.isfinite(sm_) and math.isfinite(d_)) or d_ <= 0:
                raise ValueError
            mer.append((b.cislo, b, sm_, d_))
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: směr a délka musí být čísla (délka kladná).") from None
    n = _nove_cislo(s, h)
    try:
        vs = V.volne_stanovisko(mer, meritko_volne=(h.get("meritko") == "volné"))
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Volné stanovisko (MNČ)")
    prot += [f"stanovisko {n}:  Y = {_f(vs.stanovisko.y)}   X = {_f(vs.stanovisko.x)}",
             f"orientační posun {_f(vs.posun, 4)} gon, měřítko {vs.meritko:.7f}, "
             f"střední souřadnicová chyba m0 = {_f(vs.m0)} m", "", "opravy na známých bodech:",
             "  bod                  vY [m]    vX [m]    vp [m]"]
    for c, vy, vx in vs.opravy:
        prot.append(f"  {c:<18} {vy:>9.3f} {vx:>9.3f} {math.hypot(vy, vx):>9.3f}")
    return Vysledek(prot, [Bod(n, vs.stanovisko.y, vs.stanovisko.x, poznamka="volné stanovisko")])


def u_transformace(s, h):
    pary = []
    for i, line in enumerate((h.get("identicke") or "").splitlines(), 1):
        parts = line.replace(",", ".").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „číslo_bodu Y_cíl X_cíl“.")
        b = s.najdi(parts[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {parts[0]} v seznamu není.")
        try:
            yy, xx = float(parts[1]), float(parts[2])
            if not (math.isfinite(yy) and math.isfinite(xx)):
                raise ValueError
            pary.append((b, (yy, xx)))
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: souřadnice musí být čísla.") from None
    druh = {"shodnostní": "shodnostni", "podobnostní": "podobnostni", "afinní": "afinni"}.get(
        h.get("druh") or "podobnostní")
    if druh is None:
        raise ChybaVstupu("Zvolte druh transformace: shodnostní, podobnostní nebo afinní.")
    try:
        t = V.transformace([b for b, _ in pary], [c for _, c in pary], druh)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka(f"Transformace {h.get('druh')}")
    prot += [f"identických bodů {len(pary)}, střední souřadnicová chyba m0 = {_f(t.m0)} m",
             f"měřítko {t.meritko:.8f}, otočení {_f(V.norm_gon(V.rad2gon(t.rotace)), 5)} gon, "
             f"posun Y {_f(t.t[0])} X {_f(t.t[1])}", "", "opravy na identických bodech:",
             "  bod                  vY [m]    vX [m]    vp [m]"]
    for (b, _), (vy, vx) in zip(pary, t.opravy):
        prot.append(f"  {b.cislo:<18} {vy:>9.3f} {vx:>9.3f} {math.hypot(vy, vx):>9.3f}")
    nove = []
    pre = (h.get("predpona") or "").strip()
    cil = _radky_bodu(s, h.get("transformovat") or "")
    jung = (h.get("jung") or "").startswith("ano")
    if cil:
        prot += ["", "transformované body" + (" (s Jungovou dotransformací, váhy 1/d²):" if jung else ":")]
        zdroj = [b for b, _ in pary]
        for b in cil:
            y, x = t.preved_jung(b, zdroj) if jung else t.preved(b)
            nove.append(Bod(pre + b.cislo, y, x, b.z, b.kod, b.kvalita, "transformace"))
            prot.append(f"  {pre + b.cislo:<14} Y = {_f(y)}   X = {_f(x)}")
    return Vysledek(prot, nove)


def u_vymera(s, h):
    body = _radky_bodu(s, h.get("body") or "")
    if len(body) < 3:
        raise ChybaVstupu("Výměra potřebuje aspoň tři body (zadejte čísla bodů po obvodu).")
    p = V.vymera(body)
    prot = _hlavicka("Výměra a obvod")
    prot += ["body: " + " – ".join(b.cislo for b in body),
             f"výměra P = {_f(p, 2)} m²  (zaokrouhleně {round(p):d} m²)",
             f"obvod  o = {_f(V.obvod(body))} m"]
    return Vysledek(prot)


def _cislo_nepovinne(h: dict, key: str, nazev: str, vychozi: float | None) -> float | None:
    return _cislo(h, key, nazev) if (h.get(key) or "").strip() else vychozi


def u_teren(s, h):
    from . import teren as T
    text = (h.get("body") or "").strip()
    body = _radky_bodu(s, text) if text else [b for b in s.body if b.z is not None]
    bez = [b.cislo for b in body if b.z is None]
    body = [b for b in body if b.z is not None]
    if len(body) < 3:
        raise ChybaVstupu("Model terénu potřebuje aspoň tři body s výškou.")
    interval = _cislo_nepovinne(h, "interval", "interval vrstevnic", 1.0)
    if interval <= 0:
        raise ChybaVstupu("Interval vrstevnic musí být kladný.")
    ms = _cislo_nepovinne(h, "ms", "max. délka strany", None)
    try:
        m = T.model([(b.y, b.x, b.z) for b in body], interval, max_strana=ms or None)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    zmin, zmax = m.tin.rozsah_z()
    prot = _hlavicka("Model terénu a kubatura")
    prot += [f"bodů s výškou: {len(m.tin.body)}" + (f", bez výšky vynecháno: {', '.join(bez[:10])}" if bez else "")
             + (f", duplicitní polohy: {m.tin.vynechane}" if m.tin.vynechane else ""),
             f"trojúhelníků TIN: {len(m.tin.trojuhelniky)}" + (f" (max. strana {_f(ms, 1)} m)" if ms else ""),
             f"plocha modelu (průmět): {_f(m.tin.plocha(), 2)} m²",
             f"výšky: min {_f(zmin)}  max {_f(zmax)}  rozdíl {_f(zmax - zmin)} m",
             f"vrstevnice po {interval:g} m: {len(m.vrstevnice)} čar ({len({v.z for v in m.vrstevnice})} výškových úrovní)"]
    zref = _cislo_nepovinne(h, "zref", "srovnávací výška", None)
    if zref is not None:
        nad, pod = T.kubatura(m.tin, zref)
        prot += ["", f"Kubatura vůči rovině H = {_f(zref)} m:",
                 f"  nad rovinou (výkop)  V = {_f(nad, 2)} m³",
                 f"  pod rovinou (násyp)  V = {_f(pod, 2)} m³",
                 f"  rozdíl (výkop − násyp) = {_f(nad - pod, 2)} m³"]
    prot.append("Vrstevnice do výkresu: v CAD příkaz „vrstevnice“.")
    return Vysledek(prot)


def u_vymery_davkou(s, h):
    radky = [r for r in (h.get("parcely") or "").splitlines() if r.strip()]
    if not radky:
        raise ChybaVstupu("Zadejte řádky „parcela: čísla bodů po obvodu“, např. „125/3: 1 2 3 4“.")
    prot = _hlavicka("Výměry parcel")
    prot += ["  parcela              výměra [m²]   zaokr.     obvod [m]   bodů"]
    celkem = 0.0
    for i, r in enumerate(radky, 1):
        if ":" in r:
            nazev, cisla = r.split(":", 1)
        else:
            nazev, cisla = f"plocha {i}", r
        body = _radky_bodu(s, cisla)
        if len(body) < 3:
            raise ChybaVstupu(f"Řádek {i} ({nazev.strip()}): výměra potřebuje aspoň tři body.")
        p = V.vymera(body)
        celkem += p
        prot.append(f"  {nazev.strip():<18}{p:>14.2f}{round(p):>9d}{V.obvod(body):>14.3f}{len(body):>7d}")
    prot.append(f"  {'celkem':<18}{celkem:>14.2f}{round(celkem):>9d}")
    return Vysledek(prot)


def _parcely_gp(s, text: str, nazev: str) -> list[tuple[str, float | None, str, object]]:
    """Řádky „parcela [výměra] [druh]: čísla bodů po obvodu“ → [(parcela, evidovaná výměra, druh, Polygon)]."""
    from shapely.geometry import Polygon
    out = []
    for i, r in enumerate([r for r in (text or "").splitlines() if r.strip()], 1):
        if ":" not in r:
            raise ChybaVstupu(f"{nazev}, řádek {i}: chybí dvojtečka – „parcela [výměra] [druh]: čísla bodů“.")
        hlava, cisla = r.split(":", 1)
        casti = hlava.split()
        if not casti:
            raise ChybaVstupu(f"{nazev}, řádek {i}: chybí číslo parcely.")
        parc, vym, druh = casti[0], None, ""
        zbytek = casti[1:]
        if zbytek and re.match(r"^\d+(?:[.,]\d+)?$", zbytek[0]):
            vym = float(zbytek[0].replace(",", "."))
            zbytek = zbytek[1:]
        druh = " ".join(zbytek)
        body = _radky_bodu(s, cisla)
        if len(body) < 3:
            raise ChybaVstupu(f"{nazev}, parcela {parc}: potřebuje aspoň tři body po obvodu.")
        g = Polygon([(b.y, b.x) for b in body])
        if not g.is_valid:
            raise ChybaVstupu(f"{nazev}, parcela {parc}: obvod se kříží – zkontrolujte pořadí bodů.")
        out.append((parc, vym, druh, g))
    return out


def u_vykaz_vymer(s, h):
    """Výkaz výměr geometrického plánu: dosavadní a nový stav, díly (srovnávací sestavení) a kontrola součtů."""
    dos = _parcely_gp(s, h.get("dosavadni") or "", "Dosavadní stav")
    nov = _parcely_gp(s, h.get("nove") or "", "Nový stav")
    if not dos or not nov:
        raise ChybaVstupu("Zadejte dosavadní i nový stav (řádek: parcela [výměra] [druh]: čísla bodů po obvodu).")
    prot = _hlavicka("Výkaz výměr geometrického plánu")
    prot += ["", "DOSAVADNÍ STAV", f"  {'parcela':<12}{'výměra z souř. [m²]':>21}{'evidovaná [m²]':>16}{'rozdíl':>9}  druh"]
    for parc, vym, druh, g in dos:
        rozd = f"{round(g.area) - vym:+.0f}" if vym is not None else ""
        prot.append(f"  {parc:<12}{g.area:>21.2f}{(f'{vym:.0f}' if vym is not None else '–'):>16}{rozd:>9}  {druh}")
    prot += ["", "NOVÝ STAV A POROVNÁNÍ SE STAVEM EVIDENCE",
             f"  {'parcela':<12}{'výměra [m²]':>13}  {'druh':<16}{'díl':>5}  {'z parcely':<12}{'výměra dílu [m²]':>18}"]
    pismena = "abcdefghijklmnopqrstuvwxyz"
    n_dil = 0
    for parc, _vym, druh, g in nov:
        prvni = True
        for dparc, _v, _d, dg in dos:
            prunik = g.intersection(dg).area
            if prunik < 0.01:
                continue
            znak = pismena[n_dil % 26] + ("" if n_dil < 26 else str(n_dil // 26))
            n_dil += 1
            prot.append(f"  {(parc if prvni else ''):<12}{(f'{round(g.area):d}' if prvni else ''):>13}  "
                        f"{(druh if prvni else ''):<16}{znak:>5}  {dparc:<12}{round(prunik):>18d}")
            prvni = False
        if prvni:
            prot.append(f"  {parc:<12}{round(g.area):>13d}  {druh:<16}{'':>5}  (mimo dosavadní parcely)")
    sd = sum(g.area for *_x, g in dos)
    sn = sum(g.area for *_x, g in nov)
    prot += ["", f"Součet dosavadního stavu: {sd:.2f} m² ({round(sd)} m²)",
             f"Součet nového stavu:      {sn:.2f} m² ({round(sn)} m²)"]
    if abs(sd - sn) > 0.5:
        prot.append(f"⚠ Součty se liší o {sn - sd:+.2f} m² – nový stav nepokrývá přesně dosavadní parcely "
                    "(chybí nebo přebývá část obvodu).")
    else:
        prot.append("Součty souhlasí – nový stav pokrývá dosavadní parcely.")
    prot.append("Výměry jsou z ploch zaokrouhlené na celé m². Vyrovnání na evidovanou výměru a mezní odchylku "
                "výměry posuďte podle katastrální vyhlášky (zde se nepočítá).")
    return Vysledek(prot)


def u_oblouk(s, h):
    v, a, b = _bod(s, h, "v", "vrchol tečen V"), _bod(s, h, "a", "bod na první tečně A"), _bod(s, h, "b", "bod na druhé tečně B")
    r = _cislo(h, "r", "poloměr")
    krok = _cislo(h, "krok", "krok podrobných bodů") if (h.get("krok") or "").strip() else None
    if krok is not None and (krok <= 0 or krok < r * 1e-6):
        raise ChybaVstupu("Krok podrobných bodů musí být kladný a rozumně velký.")
    try:
        o = V.kruzny_oblouk(v, a, b, r, krok)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    pre = (h.get("predpona") or "").strip() or "O"
    prot = _hlavicka("Kružnicový oblouk")
    prot += [f"tečny {a.cislo} – {v.cislo} – {b.cislo}, poloměr R = {_f(r)} m",
             f"středový úhel α = {_f(o.alfa, 4)} gon, tečna T = {_f(o.tecna)} m, délka oblouku o = {_f(o.delka)} m,"
             f" vzepětí (V–VO) = {_f(o.vzepeti)} m", "  bod                 staničení            Y            X"]
    nove = []
    for nazev, st, p in (("ZO", 0.0, o.zo), *((f"{i}", st, p) for i, (st, p) in enumerate(o.podrobne, 1)),
                         ("KO", o.delka, o.ko)):
        c = pre + nazev
        prot.append(f"  {c:<14}{st:>14.3f}{p.y:>13.3f}{p.x:>13.3f}")
        nove.append(Bod(c, p.y, p.x, poznamka="kružnicový oblouk"))
    for nazev, p in (("VO", o.vo), ("S", o.stred)):
        prot.append(f"  {pre + nazev:<14}{'':>14}{p.y:>13.3f}{p.x:>13.3f}")
        nove.append(Bod(pre + nazev, p.y, p.x, poznamka="kružnicový oblouk"))
    return Vysledek(prot, nove)


def u_staniceni(s, h):
    a, b = _bod(s, h, "a", "bod A (začátek přímky)"), _bod(s, h, "b", "bod B (směr přímky)")
    _ruzne(a, b)
    body = _radky_bodu(s, h.get("body") or "")
    if not body:
        raise ChybaVstupu("Zadejte čísla bodů, ke kterým se počítá staničení a kolmice.")
    prot = _hlavicka("Staničení a kolmice")
    prot += [f"měřická přímka {a.cislo} → {b.cislo} ({_f(V.delka(a, b))} m), kolmice kladná vpravo",
             "  bod             staničení    kolmice"]
    for p in body:
        st, k = V.stanicni_kolmice(a, b, p)
        prot.append(f"  {p.cislo:<14} {st:>10.3f} {k:>10.3f}")
    return Vysledek(prot)


def u_ze_staniceni(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    st, k = _cislo(h, "st", "staničení"), _cislo(h, "kol", "kolmici")
    n = _nove_cislo(s, h)
    p = V.bod_ze_stanicni(a, b, st, k)
    prot = _hlavicka("Bod ze staničení a kolmice")
    prot += [f"přímka {a.cislo} → {b.cislo}, staničení {_f(st)} m, kolmice {_f(k)} m (vpravo kladná)",
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="staničení a kolmice")])


def u_odchylka(s, h):
    a, b = _bod(s, h, "a", "první určení"), _bod(s, h, "b", "druhé určení")
    try:
        kk = int(h.get("kk") or 3)
    except ValueError:
        raise ChybaVstupu("Kód kvality je číslo 3–7.") from None
    if kk not in V.MXY_KOD_KVALITY:
        raise ChybaVstupu("Kód kvality je číslo 3–7.")
    d = V.polohova_odchylka(a, b)
    lim = V.mezni_polohova_odchylka(kk)
    prot = _hlavicka("Kontrola dvou určení bodu")
    prot += [f"{a.cislo} a {b.cislo}: polohová odchylka Δp = {_f(d)} m (ΔY {_f(b.y - a.y)}, ΔX {_f(b.x - a.x)})",
             f"mezní odchylka pro kód kvality {kk}: {_f(lim)} m (2·√2·m_xy, m_xy = "
             f"{_f(V.MXY_KOD_KVALITY[kk], 2)} m – ověřte v platném znění vyhlášky)",
             "VYHOVUJE" if d <= lim else "NEVYHOVUJE – překročena mezní odchylka"]
    return Vysledek(prot)


def u_omerne(s, h):
    """Kontrolní oměrné míry: měřená délka mezi body proti délce ze souřadnic."""
    try:
        kk = int(h.get("kk") or 3)
    except ValueError:
        raise ChybaVstupu("Kód kvality je číslo 3–7.") from None
    if kk not in V.MXY_KOD_KVALITY:
        raise ChybaVstupu("Kód kvality je číslo 3–7.")
    radky = []
    for i, line in enumerate((h.get("miry") or "").splitlines(), 1):
        parts = line.replace(";", " ").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „bod bod měřená_délka“.")
        a, b = s.najdi(parts[0]), s.najdi(parts[1])
        for c, x in ((parts[0], a), (parts[1], b)):
            if x is None:
                raise ChybaVstupu(f"Řádek {i}: bod {c} v seznamu souřadnic není.")
        try:
            dm = float(parts[2].replace(",", "."))
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: „{parts[2]}“ není číslo.") from None
        if not math.isfinite(dm) or dm <= 0:
            raise ChybaVstupu(f"Řádek {i}: měřená délka musí být kladná.")
        radky.append((a, b, dm))
    if not radky:
        raise ChybaVstupu("Zadejte oměrné míry – řádky „bod bod měřená_délka“.")
    prot = _hlavicka("Kontrolní oměrné míry")
    prot += [f"kód kvality {kk}, m_xy = {_f(V.MXY_KOD_KVALITY[kk], 2)} m, mezní odchylka "
             "u_d = 2·m_xy·√((d+12)/(d+20)) – ověřte v platném znění vyhlášky",
             "  od          do            měřená   ze souř.    rozdíl    mezní",
             "  " + "-" * 66]
    spatne = 0
    for a, b, dm in radky:
        ds = V.delka(a, b)
        rozdil = dm - ds
        lim = V.mezni_odchylka_delky(ds, kk)
        ok = abs(rozdil) <= lim
        spatne += not ok
        prot.append(f"  {a.cislo:<11} {b.cislo:<11} {dm:>9.2f} {ds:>9.2f} {rozdil:>+9.2f} {lim:>8.2f}"
                    + ("" if ok else "  NEVYHOVUJE"))
    prot += ["", f"{len(radky)} měr, " + ("všechny vyhovují." if not spatne else f"{spatne} překračuje mezní odchylku.")]
    return Vysledek(prot)


def _radky_cisel(text: str, n_min: int, popis: str) -> list[list[str]]:
    """Řádky „text číslo číslo…“; vrací rozdělené řádky (první položka text, ostatní ověřená čísla)."""
    out = []
    for i, line in enumerate((text or "").splitlines(), 1):
        parts = line.replace(";", " ").split()
        if not parts:
            continue
        if len(parts) < n_min:
            raise ChybaVstupu(f"Řádek {i}: zadejte „{popis}“.")
        for t in parts[1:n_min]:
            try:
                v = float(t.replace(",", "."))
            except ValueError:
                raise ChybaVstupu(f"Řádek {i}: „{t}“ není číslo.") from None
            if not math.isfinite(v):
                raise ChybaVstupu(f"Řádek {i}: „{t}“ není konečné číslo.")
        out.append([parts[0]] + [float(t.replace(",", ".")) for t in parts[1:n_min]])
    return out


def u_prusecik(s, h):
    druh = h.get("druh") or "dvou přímek"
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    n = _nove_cislo(s, h)
    prot = _hlavicka(f"Průsečík {druh}")
    if druh == "dvou přímek":
        c, d = _bod(s, h, "c", "bod C"), _bod(s, h, "d", "bod D")
        _ruzne(c, d)
        try:
            body = [V.prusecik_primek(a, b, c, d)]
        except ValueError as e:
            raise ChybaVstupu(str(e)) from None
        prot.append(f"přímky {a.cislo}–{b.cislo} a {c.cislo}–{d.cislo}")
    elif druh == "přímky a kružnice":
        c = _bod(s, h, "c", "střed kružnice (bod C)")
        r = _cislo(h, "r1", "poloměr")
        if r <= 0:
            raise ChybaVstupu("Poloměr musí být kladný.")
        body = V.prusecik_primky_kruznice(a, b, c, r)
        prot.append(f"přímka {a.cislo}–{b.cislo}, kružnice se středem {c.cislo} a poloměrem {_f(r)} m")
    elif druh == "dvou kružnic":
        r1, r2 = _cislo(h, "r1", "poloměr kolem A"), _cislo(h, "r2", "poloměr kolem B")
        if r1 <= 0 or r2 <= 0:
            raise ChybaVstupu("Poloměry musí být kladné.")
        body = V.prusecik_kruznic(a, r1, b, r2)
        prot.append(f"kružnice {a.cislo} (r = {_f(r1)} m) a {b.cislo} (r = {_f(r2)} m)")
    else:
        raise ChybaVstupu("Zvolte druh průsečíku.")
    if not body:
        raise ChybaVstupu("Průsečík neexistuje (přímka kružnici neprotíná / kružnice se neprotínají).")
    nove = []
    for i, p in enumerate(body):
        c = n if i == 0 else n + "b"
        prot.append(f"bod {c}:  Y = {_f(p.y)}   X = {_f(p.x)}")
        nove.append(Bod(c, p.y, p.x, poznamka="průsečík"))
    if len(body) > 1:
        prot.append("(dvě řešení – druhé má k číslu připojené „b“)")
    return Vysledek(prot, nove)


def u_vytyceni(s, h):
    st, o = _bod(s, h, "st", "stanovisko"), _bod(s, h, "o", "orientaci")
    _ruzne(st, o)
    body = _radky_bodu(s, h.get("body") or "")
    if not body:
        raise ChybaVstupu("Zadejte čísla vytyčovaných bodů.")
    prot = _hlavicka("Vytyčovací prvky")
    prot += [f"stanovisko {st.cislo}, orientace na {o.cislo} (směrník {_f(V.smernik(st, o), 4)} gon, "
             f"délka {_f(V.delka(st, o))} m); úhel měřen od orientace po směru hodin",
             "  bod              úhel [gon]   délka [m]  směrník [gon]"]
    for b in body:
        if V.delka(st, b) < 1e-9:
            prot.append(f"  {b.cislo:<14} leží na stanovisku")
            continue
        u, d, sm = V.vytycovaci_prvky(st, o, b)
        prot.append(f"  {b.cislo:<14} {u:>12.4f} {d:>11.3f} {sm:>14.4f}")
    return Vysledek(prot)


def u_trig_vyska(s, h):
    st = _bod(s, h, "st", "stanovisko")
    if st.z is None:
        raise ChybaVstupu(f"Stanovisko {st.cislo} nemá výšku.")
    d, z = _cislo(h, "d", "šikmou délku"), _cislo(h, "z", "zenitový úhel")
    if d <= 0:
        raise ChybaVstupu("Délka musí být kladná.")
    if not 0 < z < 400:
        raise ChybaVstupu("Zenitový úhel musí být mezi 0 a 400 gon.")
    vp = _cislo(h, "vp", "výšku přístroje") if (h.get("vp") or "").strip() else 0.0
    vc = _cislo(h, "vc", "výšku cíle") if (h.get("vc") or "").strip() else 0.0
    hh, dh = V.trigonometricka_vyska(st.z, d, z, vp, vc)
    prot = _hlavicka("Trigonometrická výška")
    prot += [f"stanovisko {st.cislo} (H = {_f(st.z)} m), šikmá délka {_f(d)} m, zenit {_f(z, 4)} gon, "
             f"výška přístroje {_f(vp)} m, cíle {_f(vc)} m",
             f"vodorovná délka {_f(d * math.sin(V.gon2rad(z)))} m, převýšení terén–terén {_f(dh)} m "
             "(se zakřivením Země a refrakcí k = 0,13)",
             f"výška bodu H = {_f(hh)} m"]
    nove = []
    c = (h.get("nove") or "").strip()
    if c:
        b = s.najdi(c)
        if b is not None:
            prot.append(f"(bod {c} je v seznamu – výška se doplní úpravou v seznamu, zde jen výpočet)")
        else:
            prot.append("(bod bez polohy se do seznamu nepřidává)")
    return Vysledek(prot, nove)


def u_nivelace(s, h):
    a, b = _bod(s, h, "a", "počáteční bod"), _bod(s, h, "b", "koncový bod")
    if a.z is None or b.z is None:
        raise ChybaVstupu("Počáteční i koncový bod musí mít výšku.")
    rad = _radky_cisel(h.get("oddily") or "", 3, "cílový_bod převýšení[m] délka[m]")
    if not rad:
        raise ChybaVstupu("Zadejte oddíly pořadu.")
    if any(r[2] < 0 for r in rad):
        raise ChybaVstupu("Délky oddílů nesmí být záporné.")
    try:
        mez = _cislo(h, "mez", "mezní odchylku") if (h.get("mez") or "").strip() else 40.0
        r = V.nivelacni_porad(a.z, b.z, [(c, dh, d) for c, dh, d in rad], mez)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Nivelační pořad")
    prot += [f"{a.cislo} (H = {_f(a.z)}) → {b.cislo} (H = {_f(b.z)}), délka {r.delka_km:.3f} km",
             f"odchylka uzávěru {r.odchylka * 1000:.1f} mm, mezní {r.mezni * 1000:.1f} mm "
             f"({_f(mez, 1)} mm·√L) – " + ("VYHOVUJE" if r.vyhovuje else "NEVYHOVUJE"),
             "  bod              převýšení    oprava      výška"]
    nove = []
    for (c, dh, _d), v, (_c, hh) in zip(rad, r.opravy, r.vysky):
        prot.append(f"  {c:<14} {dh:>10.4f} {v * 1000:>8.2f}mm {hh:>10.4f}")
        bod = s.najdi(c)
        if bod is not None and bod.cislo not in (a.cislo, b.cislo):
            nove.append(Bod(c + "_niv", bod.y, bod.x, hh, bod.kod, bod.kvalita, "nivelace"))
    return Vysledek(prot, nove)


def u_nivelacni_sit(s, h):
    from .vyrovnani import Oddil, vyrovnej_nivelaci
    oddily = []
    for i, line in enumerate((h.get("oddily") or "").splitlines(), 1):
        p = line.replace(";", " ").replace(",", ".").split()
        if not p:
            continue
        if len(p) < 4:
            raise ChybaVstupu(f"Řádek {i}: zadejte „od do převýšení[m] délka[m]“.")
        try:
            dh, d = float(p[2]), float(p[3])
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: převýšení a délka musí být čísla.") from None
        if not (math.isfinite(dh) and math.isfinite(d)) or d <= 0:
            raise ChybaVstupu(f"Řádek {i}: délka musí být kladné číslo.")
        oddily.append(Oddil(p[0], p[1], dh, d))
    dane = _radky_bodu(s, h.get("dane") or "")
    if not dane:
        raise ChybaVstupu("Zadejte výškově dané body (čísla bodů se známou výškou v seznamu).")
    if any(b.z is None for b in dane):
        raise ChybaVstupu("Dané body musí mít v seznamu výšku: " + ", ".join(b.cislo for b in dane if b.z is None))
    try:
        r = vyrovnej_nivelaci(oddily, {b.cislo: b.z for b in dane})
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Vyrovnání nivelační sítě")
    prot += [f"oddílů {len(oddily)}, daných bodů {len(dane)}, nadbytečných měření {r.redundance}"
             + (f", jednotková střední chyba na 1 km m0 = {r.m0_km * 1000:.2f} mm" if r.redundance else ""),
             "", "  bod                výška [m]    m_H [mm]"]
    nove = []
    for c in sorted(r.vysky, key=lambda x: klic_cisla(x)):
        prot.append(f"  {c:<16}{r.vysky[c]:>13.4f}{r.stredni_chyby[c] * 1000:>11.2f}")
        bod = s.najdi(c)
        if bod is not None:
            nove.append(Bod(c + "_niv", bod.y, bod.x, round(r.vysky[c], 4), bod.kod, bod.kvalita, "nivelační síť"))
    prot += ["", "  oddíl                    převýšení   oprava [mm]"]
    for o, v in r.opravy:
        prot.append(f"  {o.od:>8} → {o.do:<10}{o.dh:>12.4f}{v * 1000:>12.2f}")
    return Vysledek(prot, nove)


def u_ortogonalni(s, h):
    a, b = _bod(s, h, "a", "bod A (začátek přímky)"), _bod(s, h, "b", "bod B (konec přímky)")
    _ruzne(a, b)
    rad = _radky_cisel(h.get("mereni") or "", 3, "číslo staničení kolmice")
    if not rad:
        raise ChybaVstupu("Zadejte měření (řádek: číslo staničení kolmice).")
    dm = _cislo(h, "dm", "měřenou délku A–B") if (h.get("dm") or "").strip() else None
    if dm is not None and dm <= 0:
        raise ChybaVstupu("Měřená délka musí být kladná.")
    body, q, odch = V.ortogonalni_davka(a, b, [(c, st, k) for c, st, k in rad], dm)
    prot = _hlavicka("Ortogonální metoda")
    prot.append(f"měřická přímka {a.cislo} → {b.cislo}: ze souřadnic {_f(V.delka(a, b))} m"
                + (f", měřeno {_f(dm)} m, rozdíl {_f(odch)} m, měřítko {q:.6f}" if dm else ""))
    prot.append("  bod             staničení    kolmice            Y            X")
    nove = []
    for (c, st, k), (_c, p) in zip(rad, body):
        prot.append(f"  {c:<14} {st:>10.3f} {k:>10.3f} {p.y:>12.3f} {p.x:>12.3f}")
        nove.append(Bod(c, p.y, p.x, poznamka="ortogonální metoda"))
    return Vysledek(prot, nove)


def u_polygon(s, h):
    ao, a = _bod(s, h, "ao", "orientaci na začátku"), _bod(s, h, "a", "počáteční bod")
    b, bo = _bod(s, h, "b", "koncový bod"), _bod(s, h, "bo", "orientaci na konci")
    _ruzne(a, ao)
    _ruzne(b, bo)
    uhly = _radky_cisel(h.get("uhly") or "", 2, "bod úhel[gon]")
    strany = _radky_cisel(h.get("delky") or "", 2, "bod délka[m] (délka strany k dalšímu bodu)")
    if len(uhly) < 2:
        raise ChybaVstupu("Zadejte vrcholové úhly na počátečním bodě, všech nových bodech a koncovém bodě.")
    cisla = [u[0] for u in uhly[1:-1]]
    try:
        r = V.polygonovy_porad(a, ao, b, bo, [u[1] for u in uhly], [d[1] for d in strany], cisla)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    mez_u = 0.0060 * math.sqrt(len(uhly))  # orientační mez 60 cc·√n (k ověření podle předpisu)
    prot = _hlavicka("Polygonový pořad oboustranně připojený a orientovaný")
    prot += [f"{ao.cislo} → {a.cislo} … {b.cislo} → {bo.cislo}, nových bodů {len(cisla)}, délka {_f(r.delka)} m",
             f"úhlová odchylka {r.uhlova_odchylka * 10000:.0f} cc (orientačně mezní {mez_u * 10000:.0f} cc)",
             f"souřadnicové odchylky dY = {_f(r.dy)} m, dX = {_f(r.dx)} m, polohová {_f(r.polohova)} m",
             "  bod                 směrník        délka            Y            X"]
    nove = []
    for i, (c, p) in enumerate(r.body):
        prot.append(f"  {c:<14} {r.smerniky[i]:>12.4f} {strany[i][1]:>12.3f} {p.y:>12.3f} {p.x:>12.3f}")
        nove.append(Bod(c, p.y, p.x, poznamka="polygonový pořad"))
    return Vysledek(prot, nove)


def u_polygon_uzavreny(s, h):
    """Uzavřený pořad: začíná i končí na bodě A (orientace na stejný bod) – stejný výpočet jako oboustranně
    připojený pořad s B = A; úhlová i souřadnicová odchylka se rozdělí."""
    h = dict(h)
    h["b"], h["bo"] = h.get("a"), h.get("ao")
    v = u_polygon(s, h)
    v.protokol[0:2] = _hlavicka("Polygonový pořad uzavřený")[:2]
    return v


def u_polygon_volny(s, h):
    ao, a = _bod(s, h, "ao", "orientaci na začátku"), _bod(s, h, "a", "počáteční bod")
    _ruzne(a, ao)
    uhly = _radky_cisel(h.get("uhly") or "", 2, "bod úhel[gon]")
    strany = _radky_cisel(h.get("delky") or "", 2, "bod délka[m] (délka strany k dalšímu bodu)")
    # nové body: P1…Pn−1 jsou stanoviska z řádků úhlů, poslední bod je jen v poli „Číslo posledního bodu“
    cisla = [u[0] for u in uhly[1:]] + [_nove_cislo(s, h, "posledni")]
    try:
        body = V.polygonovy_porad_volny(a, ao, [u[1] for u in uhly], [d[1] for d in strany], cisla)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Polygonový pořad volný (jednostranně připojený)")
    prot += [f"{ao.cislo} → {a.cislo}, nových bodů {len(body)} – bez kontroly, žádná odchylka se nedá zjistit!",
             "  bod                délka            Y            X"]
    nove = []
    for (c, p), d in zip(body, strany):
        prot.append(f"  {c:<14} {d[1]:>12.3f} {p.y:>12.3f} {p.x:>12.3f}")
        nove.append(Bod(c, p.y, p.x, poznamka="volný polygonový pořad"))
    return Vysledek(prot, nove)


def _trida(h) -> int:
    t = str(h.get("trida") or "3").strip()[:1]
    return int(t) if t in ("1", "2", "3", "4", "5") else 3


def u_test_souradnic(s, h):
    """Testování přesnosti ÚM: výsledné souřadnice ze seznamu × nezávislé kontrolní určení."""
    trida = _trida(h)
    k = 1.0 if str(h.get("k") or "").startswith("1") else 2.0
    povrch = h.get("povrch") or "zpevněný"
    dvojice, chybi = [], []
    for i, line in enumerate((h.get("kontrolni") or "").splitlines(), 1):
        parts = line.replace(";", " ").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „číslo Y X [Z]“.")
        try:
            cis = [float(t.replace(",", ".")) for t in parts[1:4]]
        except ValueError:
            cis = []
        if len(cis) < 2 or not all(math.isfinite(v) for v in cis):
            raise ChybaVstupu(f"Řádek {i}: souřadnice musí být čísla.")
        b = s.najdi(parts[0])
        if b is None:
            chybi.append(parts[0])
            continue
        kz = cis[2] if len(cis) > 2 else None
        dvojice.append((b.cislo, (b.y, b.x, b.z), (cis[0], cis[1], kz)))
    if not dvojice:
        raise ChybaVstupu("Žádný z kontrolních bodů není v seznamu souřadnic.")
    t = V.test_presnosti_souradnic(dvojice, trida, k, povrch)
    u_xy, u_h, _ = V.TRIDY_PRESNOSTI[trida]
    ano = lambda ok: "vyhovuje" if ok else "NEVYHOVUJE"  # noqa: E731
    prot = _hlavicka("Testování přesnosti souřadnic a výšek (ČSN 01 3410)")
    prot += [f"třída přesnosti {trida}: u_xy = {u_xy:.2f} m, u_H = {u_h:.2f} m; k = {k:g} "
             f"({'stejná přesnost obou určení' if k == 2 else 'kontrolní určení výrazně přesnější'})",
             "  bod                 ΔY       ΔX       Δp           ΔH"]
    for c, dy, dx, dp, ok, dh, okh in t.radky:
        hh = "" if dh is None else f"{dh:>9.3f}{'' if okh else '  !'}"
        prot.append(f"  {c:<14} {dy:>8.3f} {dx:>8.3f} {dp:>8.3f}{'' if ok else ' !'}   {hh}")
    prot += ["",
             f"N = {t.n}" + (f" – méně než N_min = {V.N_MIN}, statistický test je jen orientační"
                                  if t.n < V.N_MIN else ""),
             f"1) |Δp| ≤ 1,7·u_xy = {t.mez_dp:.3f} m: {ano(all(r[4] for r in t.radky))}"
             + ("" if all(r[4] for r in t.radky) else f" (označeno !: {sum(not r[4] for r in t.radky)})"),
             f"2) s_x = {t.s_x:.3f} m, s_y = {t.s_y:.3f} m, s_xy = {t.s_xy:.3f} m ≤ ω·u_xy = {t.mez_sxy:.3f} m: "
             f"{ano(t.s_xy <= t.mez_sxy)}",
             f"Přesnost souřadnic: {ano(t.vyhovuje).upper()}"]
    if t.n_h:
        prot += ["",
                 f"Výšky (N = {t.n_h}, {povrch} povrch):",
                 f"1) |ΔH| ≤ 2·u_H·√k = {t.mez_dh:.3f} m: {ano(all(r[6] for r in t.radky if r[6] is not None))}",
                 f"2) s_H = {t.s_h:.3f} m ≤ {t.mez_sh:.3f} m: {ano(t.s_h <= t.mez_sh)}",
                 f"Přesnost výšek: {ano(t.vyhovuje_h).upper()}"]
    if chybi:
        prot.append(f"V seznamu chybí body: {', '.join(chybi)}")
    return Vysledek(prot)


def u_test_delek(s, h):
    trida = _trida(h)
    mereni = []
    for i, line in enumerate((h.get("delky") or "").splitlines(), 1):
        parts = line.replace(";", " ").split()
        if not parts:
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „bod bod délka“.")
        try:
            dk = float(parts[2].replace(",", "."))
        except ValueError:
            dk = math.nan
        if not math.isfinite(dk) or dk <= 0:
            raise ChybaVstupu(f"Řádek {i}: „{parts[2]}“ není kladná délka.")
        a, b = s.najdi(parts[0]), s.najdi(parts[1])
        if a is None or b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {parts[0] if a is None else parts[1]} není v seznamu souřadnic.")
        mereni.append((a.cislo, b.cislo, a, b, dk))
    if not mereni:
        raise ChybaVstupu("Zadejte kontrolní délky (řádek: bod bod délka).")
    t = V.test_presnosti_delek(mereni, trida)
    prot = _hlavicka("Testování přesnosti – kontrolní délky (ČSN 01 3410)")
    prot += [f"třída přesnosti {trida}: u_xy = {V.TRIDY_PRESNOSTI[trida][0]:.2f} m, "
             "u_d = 1,5·u_xy·(d + 12)/(d + 20)",
             "  od        do           d_m        d_k       Δd      u_d"]
    for a, b, dm, dk, dd, ud, ok2, ok1 in t.radky:
        prot.append(f"  {a:<9} {b:<9} {dm:>9.3f} {dk:>9.3f} {dd:>8.3f} {ud:>8.3f}"
                    + ("" if ok1 else ("  (> u_d)" if ok2 else "  ! > 2·u_d")))
    vse2 = all(r[6] for r in t.radky)
    prot += ["",
             f"I.  |Δd| ≤ 2·u_d u všech délek: {'ano' if vse2 else 'NE'}",
             f"II. |Δd| ≤ u_d u {t.podil * 100:.0f} % délek (potřeba aspoň 60 %): {'ano' if t.podil >= 0.6 else 'NE'}",
             f"Relativní přesnost: {'VYHOVUJE' if t.vyhovuje else 'NEVYHOVUJE'}"]
    return Vysledek(prot)


def u_oddeleni(s, h):
    parc = _radky_bodu(s, h.get("body") or "")
    if len(parc) < 3:
        raise ChybaVstupu("Zadejte body parcely po obvodu (aspoň tři).")
    cil = _cislo(h, "vymera", "oddělovanou výměru")
    bodem = (h.get("zpusob") or "").startswith("dělicí čarou z bodu")
    a = _bod(s, h, "a", "bod A" + ("" if bodem else " hranice"))
    try:
        if bodem:
            cast, q = V.oddeleni_bodem(parc, a, cil)
        else:
            b = _bod(s, h, "b", "bod B hranice")
            _ruzne(a, b)
            cast, t = V.oddeleni_rovnobezne(parc, a, b, cil)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    pre = (h.get("predpona") or "").strip() or "D"
    prot = _hlavicka("Oddělení části parcely " + ("dělicí čarou z bodu" if bodem else "rovnoběžně s hranicí"))
    prot += [f"parcela {' – '.join(p.cislo for p in parc)}: výměra {_f(V.vymera(parc), 2)} m²",
             (f"oddělit {_f(cil, 2)} m² dělicí čarou z bodu {a.cislo} (po obvodu v pořadí bodů): druhý konec "
              f"Y = {_f(q.y)}, X = {_f(q.x)}, délka dělicí čáry {_f(V.delka(a, q))} m") if bodem else
             (f"oddělit {_f(cil, 2)} m² rovnoběžně s hranicí {a.cislo}–{b.cislo}: dělicí čára ve vzdálenosti "
              f"{_f(t)} m"), f"oddělená část: {_f(V.vymera(cast), 2)} m², body:"]
    nove, i = [], 0
    zname = parc + [a]  # bod A může ležet na straně parcely
    for p in cast:
        if any(abs(p.y - q.y) < 1e-6 and abs(p.x - q.x) < 1e-6 for q in zname):
            c = next(q.cislo for q in zname if abs(p.y - q.y) < 1e-6 and abs(p.x - q.x) < 1e-6)
            prot.append(f"  {c:<14} Y = {_f(p.y)}   X = {_f(p.x)}  (daný)")
        else:
            i += 1
            prot.append(f"  {pre + str(i):<14} Y = {_f(p.y)}   X = {_f(p.x)}  (nový)")
            nove.append(Bod(pre + str(i), p.y, p.x, poznamka="oddělení parcely"))
    return Vysledek(prot, nove)


def u_wgs(s, h):
    from . import sjtsk as J
    smer = h.get("smer") or "S-JTSK → WGS84"
    prot = _hlavicka("Převod S-JTSK ↔ WGS84")
    prot.append("přesnost převodu přibližně 1 m (parametry EPSG:5239) – pro katastr používejte síť a opravnou "
                "tabulku ČÚZK")
    if smer == "S-JTSK → WGS84":
        body = _radky_bodu(s, h.get("body") or "")
        if not body:
            raise ChybaVstupu("Zadejte čísla bodů.")
        prot.append("  bod             šířka              délka              mapy.cz")
        for b in body:
            if not (300000 < abs(b.y) < 1000000 and 900000 < abs(b.x) < 1400000):
                prot.append(f"  {b.cislo:<14} mimo území S-JTSK")
                continue
            la, lo, _hh = J.sjtsk_na_wgs84(b.y, b.x, b.z or 0.0)
            prot.append(f"  {b.cislo:<14} {J.stupne_text(la, 'N', 'S')}  {J.stupne_text(lo, 'E', 'W')}  "
                        f"({la:.7f}, {lo:.7f})  {J.odkaz_mapy_cz(la, lo)}")
        return Vysledek(prot)
    rad = _radky_cisel(h.get("wgs") or "", 3, "číslo šířka[°] délka[°]")
    if not rad:
        raise ChybaVstupu("Zadejte řádky „číslo šířka délka“ ve stupních.")
    nove = []
    for c, la, lo in rad:
        if not (47 < la < 52 and 11 < lo < 20):
            raise ChybaVstupu(f"Bod {c}: souřadnice {la}, {lo} neleží v Česku ani na Slovensku.")
        y, x, _hb = J.wgs84_na_sjtsk(la, lo)
        prot.append(f"  {c:<14} Y = {_f(y, 2)}   X = {_f(x, 2)}")
        nove.append(Bod(c, y, x, poznamka="převod z WGS84 (≈1 m)"))
    return Vysledek(prot, nove)


ULOHY: list[tuple[str, str, list[Pole], object]] = [
    ("Směrník a délka", "Směrník, délka a souřadnicové rozdíly mezi dvěma body.",
     [Pole("a", "Bod A"), Pole("b", "Bod B")], u_smernik),
    ("Rajón (polární bod)", "Nový bod ze stanoviska: orientace na známý bod, měřený směr a délka.",
     [Pole("st", "Stanovisko"), Pole("o", "Orientace (bod)"), Pole("so", "Směr na orientaci [gon]", "gon"),
      Pole("sm", "Měřený směr [gon]", "gon"), Pole("d", "Vodorovná délka [m]", "m"),
      Pole("dh", "Převýšení [m] (nepovinné)", "m"), Pole("nove", "Číslo nového bodu", "text")], u_rajon),
    ("Protínání vpřed z úhlů", "Bod z úhlů α (v A) a β (v B) měřených od základny A–B.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("alfa", "Úhel α [gon]", "gon"), Pole("beta", "Úhel β [gon]", "gon"),
      Pole("nove", "Číslo nového bodu", "text")], u_vpred_uhly),
    ("Protínání z délek", "Bod ze dvou měřených délek od známých bodů.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("da", "Délka z A [m]", "m"), Pole("db", "Délka z B [m]", "m"),
      Pole("strana", "Bod leží", "volba", "vlevo", ("vlevo", "vpravo"), "vlevo / vpravo od směru A → B na mapě"),
      Pole("nove", "Číslo nového bodu", "text")], u_z_delek),
    ("Protínání zpět", "Stanovisko z měřených směrů na tři známé body.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("c", "Bod C"), Pole("sa", "Směr na A [gon]", "gon"),
      Pole("sb", "Směr na B [gon]", "gon"), Pole("sc", "Směr na C [gon]", "gon"),
      Pole("nove", "Číslo stanoviska", "text")], u_zpet),
    ("Volné stanovisko", "Stanovisko a orientace z ≥ 2 známých bodů (směr + délka), vyrovnání MNČ s opravami.",
     [Pole("mereni", "Měření (řádek: bod směr[gon] délka[m])", "radky"),
      Pole("meritko", "Měřítko", "volba", "pevné (1)", ("pevné (1)", "volné")),
      Pole("nove", "Číslo stanoviska", "text")], u_volne),
    ("Transformace", "Transformační klíč z identických bodů (shodnostní / podobnostní / afinní) s opravami; "
     "transformace dalších bodů.",
     [Pole("druh", "Druh", "volba", "podobnostní", ("shodnostní", "podobnostní", "afinní")),
      Pole("identicke", "Identické body (řádek: bod Y_cíl X_cíl)", "radky"),
      Pole("transformovat", "Transformovat body (čísla)", "radky"),
      Pole("jung", "Jungova dotransformace", "volba", "ne", ("ne", "ano – opravy z identických bodů")),
      Pole("predpona", "Předpona nových čísel", "text", "T")], u_transformace),
    ("Výměra a obvod", "Výměra a obvod plochy z bodů zadaných po obvodu.",
     [Pole("body", "Body po obvodu (čísla)", "radky")], u_vymera),
    ("Kružnicový oblouk", "Hlavní body oblouku (ZO, KO, VO, střed) a podrobné body po délce – vytyčení oblouku.",
     [Pole("v", "Vrchol tečen V"), Pole("a", "Bod na první tečně A (směr k ZO)"), Pole("b", "Bod na druhé tečně B"),
      Pole("r", "Poloměr R [m]", "m"), Pole("krok", "Podrobné body po [m] (nepovinné)", "m"),
      Pole("predpona", "Předpona čísel", "text", "O")], u_oblouk),
    ("Výměry parcel dávkou", "Výměry a obvody více parcel najednou (řádek: parcela: čísla bodů po obvodu).",
     [Pole("parcely", "Parcely (řádek: 125/3: 1 2 3 4)", "radky")], u_vymery_davkou),
    ("Staničení a kolmice", "Staničení a kolmice bodů k měřické přímce (oměrné, kontrola).",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("body", "Body (čísla)", "radky")], u_staniceni),
    ("Bod ze staničení a kolmice", "Nový bod ze staničení a kolmice k přímce A–B (vytyčení).",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("st", "Staničení [m]", "m"), Pole("kol", "Kolmice [m] (vpravo +)", "m"),
      Pole("nove", "Číslo nového bodu", "text")], u_ze_staniceni),
    ("Kontrola dvou určení", "Polohová odchylka dvou určení bodu a mezní odchylka podle kódu kvality.",
     [Pole("a", "První určení (bod)"), Pole("b", "Druhé určení (bod)"),
      Pole("kk", "Kód kvality", "volba", "3", ("3", "4", "5", "6", "7"))], u_odchylka),
    ("Kontrolní oměrné míry", "Měřené délky (oměrné míry) proti délkám ze souřadnic, mezní odchylka podle kódu "
     "kvality.",
     [Pole("miry", "Míry (řádek: bod bod měřená_délka)", "radky"),
      Pole("kk", "Kód kvality", "volba", "3", ("3", "4", "5", "6", "7"))], u_omerne),
    ("Průsečíky", "Průsečík dvou přímek, přímky a kružnice nebo dvou kružnic.",
     [Pole("druh", "Druh", "volba", "dvou přímek", ("dvou přímek", "přímky a kružnice", "dvou kružnic")),
      Pole("a", "Bod A"), Pole("b", "Bod B"),
      Pole("c", "Bod C (přímka C–D / střed kružnice)", napoveda="u dvou kružnic nevyplňujte"),
      Pole("d", "Bod D (jen dvě přímky)"), Pole("r1", "Poloměr (kolem C, u dvou kružnic kolem A) [m]", "m"),
      Pole("r2", "Poloměr kolem B [m] (dvě kružnice)", "m"), Pole("nove", "Číslo nového bodu", "text")],
     u_prusecik),
    ("Ortogonální metoda", "Body ze staničení a kolmic k měřické přímce dávkou, s vyrovnáním na měřenou délku.",
     [Pole("a", "Bod A (začátek)"), Pole("b", "Bod B (konec)"),
      Pole("dm", "Měřená délka A–B [m] (nepovinné)", "m"),
      Pole("mereni", "Měření (řádek: číslo staničení kolmice)", "radky")], u_ortogonalni),
    ("Polygonový pořad", "Oboustranně připojený a orientovaný pořad: úhlové a souřadnicové vyrovnání.",
     [Pole("ao", "Orientace na začátku (bod)"), Pole("a", "Počáteční bod"), Pole("b", "Koncový bod"),
      Pole("bo", "Orientace na konci (bod)"),
      Pole("uhly", "Vrcholové úhly (řádek: bod úhel) – počátek, nové body, konec", "radky",
           napoveda="levé úhly od zadní k přední záměře, po směru hodin"),
      Pole("delky", "Délky stran (řádek: bod délka k dalšímu bodu)", "radky")], u_polygon),
    ("Testování přesnosti ÚM – body", "Výsledné souřadnice × nezávislé kontrolní zaměření: Δp, s_xy, výšky "
     "(Pokyn pro tvorbu ÚM 5.1 b, 5.2; ČSN 01 3410).",
     [Pole("trida", "Třída přesnosti", "volba", "3", ("1", "2", "3", "4", "5")),
      Pole("k", "Kontrolní určení", "volba", "2 – stejná přesnost",
           ("2 – stejná přesnost", "1 – výrazně přesnější")),
      Pole("povrch", "Povrch (pro výšky)", "volba", "zpevněný", ("zpevněný", "nezpevněný")),
      Pole("kontrolni", "Kontrolní určení (řádek: číslo Y X [Z])", "radky",
           napoveda="čísla bodů ze seznamu souřadnic, souřadnice z kontrolního měření")], u_test_souradnic),
    ("Testování přesnosti ÚM – délky", "Kontrolní délky přímých spojnic × délky ze souřadnic "
     "(Pokyn pro tvorbu ÚM 5.1 a; ČSN 01 3410).",
     [Pole("trida", "Třída přesnosti", "volba", "3", ("1", "2", "3", "4", "5")),
      Pole("delky", "Kontrolní délky (řádek: bod bod délka[m])", "radky")], u_test_delek),
    ("Polygonový pořad uzavřený", "Pořad začíná i končí na stejném bodě: úhlové a souřadnicové vyrovnání.",
     [Pole("ao", "Orientace (bod)"), Pole("a", "Počáteční a koncový bod"),
      Pole("uhly", "Vrcholové úhly (řádek: bod úhel) – A od orientace, nové body, A k orientaci", "radky",
           napoveda="levé úhly od zadní k přední záměře; poslední úhel na A je od posledního bodu k orientaci"),
      Pole("delky", "Délky stran (řádek: bod délka k dalšímu bodu)", "radky")], u_polygon_uzavreny),
    ("Polygonový pořad volný", "Jednostranně připojený pořad – bez kontroly (jen výjimečně, krátký).",
     [Pole("ao", "Orientace na začátku (bod)"), Pole("a", "Počáteční bod"),
      Pole("uhly", "Vrcholové úhly (řádek: bod úhel) – na A a na nových bodech kromě posledního", "radky"),
      Pole("delky", "Délky stran (řádek: bod délka k dalšímu bodu)", "radky"),
      Pole("posledni", "Číslo posledního (koncového) bodu", "text")], u_polygon_volny),
    ("Vytyčovací prvky", "Úhel od orientace a délka ze stanoviska pro vytyčení bodů.",
     [Pole("st", "Stanovisko"), Pole("o", "Orientace (bod)"), Pole("body", "Vytyčované body (čísla)", "radky")],
     u_vytyceni),
    ("Trigonometrická výška", "Výška bodu ze šikmé délky a zenitového úhlu (se zakřivením a refrakcí).",
     [Pole("st", "Stanovisko (s výškou)"), Pole("d", "Šikmá délka [m]", "m"), Pole("z", "Zenitový úhel [gon]", "gon"),
      Pole("vp", "Výška přístroje [m]", "m"), Pole("vc", "Výška cíle [m]", "m"),
      Pole("nove", "Číslo bodu (nepovinné)", "text")], u_trig_vyska),
    ("Nivelační pořad", "Výšky bodů pořadu mezi dvěma výškově danými body, rozdělení uzávěru úměrně délkám.",
     [Pole("a", "Počáteční bod"), Pole("b", "Koncový bod"),
      Pole("oddily", "Oddíly (řádek: cílový bod převýšení délka)", "radky"),
      Pole("mez", "Mezní odchylka [mm/√km]", "m", "40")], u_nivelace),
    ("Vyrovnání nivelační sítě", "Výšky bodů sítě z převýšení metodou nejmenších čtverců (váhy 1/L), opravy a m0.",
     [Pole("dane", "Výškově dané body (čísla)", "radky"),
      Pole("oddily", "Oddíly (řádek: od do převýšení[m] délka[m])", "radky")], u_nivelacni_sit),
    ("Oddělení parcely", "Oddělí část zadané výměry dělicí čarou rovnoběžnou s hranicí A–B, nebo dělicí čarou "
     "vedenou bodem A na hranici.",
     [Pole("zpusob", "Způsob", "volba", "rovnoběžně s hranicí A–B",
           ("rovnoběžně s hranicí A–B", "dělicí čarou z bodu A")),
      Pole("body", "Body parcely po obvodu (čísla)", "radky"), Pole("a", "Bod A (hranice / dělicí čára)"),
      Pole("b", "Hranice – bod B (jen rovnoběžně)"), Pole("vymera", "Oddělit výměru [m²]", "m"),
      Pole("predpona", "Předpona nových bodů", "text", "D")], u_oddeleni),
    ("Model terénu a kubatura", "TIN z bodů s výškou, výškový rozsah, vrstevnice a objem nad / pod srovnávací "
     "rovinou (výkop, násyp).",
     [Pole("body", "Body (čísla, prázdné = všechny s výškou)", "radky"),
      Pole("interval", "Interval vrstevnic [m]", "m", "1"),
      Pole("ms", "Max. délka strany trojúhelníku [m] (nepovinné)", "m",
           napoveda="odřízne dlouhé trojúhelníky na okraji a v zálivech"),
      Pole("zref", "Srovnávací výška pro kubaturu [m] (nepovinné)", "m")], u_teren),
    ("Výkaz výměr GP", "Geometrický plán: výměry dosavadního a nového stavu ze souřadnic, díly (srovnávací "
     "sestavení – z které parcely díl přechází) a kontrola součtů.",
     [Pole("dosavadni", "Dosavadní stav (řádek: parcela [evidovaná výměra] [druh]: čísla bodů)", "radky",
           napoveda="např. 125/3 450 zahrada: 1 2 3 4"),
      Pole("nove", "Nový stav (řádek: parcela [druh]: čísla bodů)", "radky",
           napoveda="např. 125/5 zahrada: 1 2 6 5")], u_vykaz_vymer),
    ("Převod S-JTSK ↔ WGS84", "Zeměpisné souřadnice bodů (s odkazem na mapy.cz) a opačně, přesnost ≈ 1 m.",
     [Pole("smer", "Směr", "volba", "S-JTSK → WGS84", ("S-JTSK → WGS84", "WGS84 → S-JTSK")),
      Pole("body", "Body (čísla) pro S-JTSK → WGS84", "radky"),
      Pole("wgs", "WGS84 → S-JTSK (řádek: číslo šířka délka)", "radky")], u_wgs),
]
