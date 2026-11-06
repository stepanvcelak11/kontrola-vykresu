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
    vysky: dict[str, float] = field(default_factory=dict)  # výšky existujících bodů (nivelace) → Z v seznamu
    data: dict = field(default_factory=dict)  # opravy apod. pro tabulky ve výpočetním okně (jako v Gromě)


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


def _korekce(body: list) -> tuple[float, list[str]]:
    """Násobitel měřených vodorovných délek podle Nastavení výpočtů (měřítko, výška, ppm) v těžišti bodů
    a řádek do protokolu (prázdný, když jsou korekce vypnuté)."""
    from .nastaveni import aktualni
    n = aktualni()
    if not n.korekce_zapnuta:
        return 1.0, []
    body = [b for b in body if b is not None]
    y = sum(b.y for b in body) / len(body) if body else None
    x = sum(b.x for b in body) / len(body) if body else None
    zz = [b.z for b in body if b.z is not None]
    k, popis = n.faktor_delky(y, x, sum(zz) / len(zz) if zz else None)
    return k, [n.popis_korekce(k, popis)]


# ------------------------------------------------------------------ úlohy
def u_smernik(s, h):
    """Směrník a délka (Groma): směrník z prvního bodu na druhý a délka; s výškami i prostorová délka,
    sklon ve stupních a spád v procentech."""
    a, b = _bod(s, h, "a", "počáteční bod"), _bod(s, h, "b", "koncový bod")
    _ruzne(a, b)
    sm, d = V.smernik(a, b), V.delka(a, b)
    p = _hlavicka("Směrník a délka")
    p += [f"z bodu {a.cislo} na bod {b.cislo}",
          f"  směrník σ = {_f(sm, 4)} gon",
          f"  délka   d = {_f(d)} m",
          f"  ΔY = {_f(b.y - a.y)} m, ΔX = {_f(b.x - a.x)} m"]
    data = {"smernik": sm, "delka": d}
    if a.z is not None and b.z is not None:
        dz = b.z - a.z
        data.update(prevyseni=dz, prostorova=math.hypot(d, dz), sklon=math.degrees(math.atan2(dz, d)),
                    spad=dz / d * 100)
        p += [f"  převýšení Δh = {_f(dz)} m",
              f"  prostorová délka {_f(data['prostorova'])} m, sklon {data['sklon']:.4f}°, spád {data['spad']:.2f} %"]
    return Vysledek(p, data=data)


def _orientace_osnovy(s, h, st: Bod, k: float) -> tuple[float, list[tuple]]:
    """Orientace osnovy na stanovisku jako v Gromě: řádky „bod směr [délka]“ (a pole o/so/od),
    posun = průměr (směrník − směr) vážený délkami, opravy V or. [g] a V délky [m]."""
    radky: list[tuple[Bod, float, float | None]] = []
    if (h.get("o") or "").strip():
        o = _bod(s, h, "o", "orientaci")
        od = _cislo(h, "od", "délku na orientaci") if (h.get("od") or "").strip() else None
        radky.append((o, _cislo(h, "so", "směr na orientaci"), od))
    for i, line in enumerate((h.get("orientace") or "").splitlines(), 1):
        p = line.replace(",", ".").split()
        if not p:
            continue
        b = s.najdi(p[0])
        if b is None:
            raise ChybaVstupu(f"Orientace, řádek {i}: bod {p[0]} v seznamu souřadnic není.")
        try:
            smer = float(p[1])
            dl = float(p[2]) if len(p) > 2 and p[2] not in ("-", "") else None
        except (IndexError, ValueError):
            raise ChybaVstupu(f"Orientace, řádek {i}: zadejte „bod směr [délka]“ (čísla).") from None
        if all(b.cislo != r[0].cislo for r in radky):
            radky.append((b, smer, dl))
    if not radky:
        raise ChybaVstupu("Zadejte orientaci: číslo orientačního bodu a měřený směr (nebo ho přetáhněte).")
    for b, _sm, _d in radky:
        _ruzne(st, b)
    posuny = [V.norm_gon(V.smernik(st, b) - sm) for b, sm, _d in radky]
    vahy = [math.hypot(b.y - st.y, b.x - st.x) for b, _sm, _d in radky]
    ref = posuny[0]
    posun = V.norm_gon(ref + sum(w * (((p - ref + 200) % 400) - 200) for p, w in zip(posuny, vahy)) / sum(vahy))
    out = []
    for (b, sm, dl), p, w in zip(radky, posuny, vahy):
        out.append((b, sm, V.smernik(st, b), ((p - posun + 200) % 400) - 200, w, dl,
                    None if dl is None else w - dl * k))
    return posun, out


def u_rajon(s, h):
    """Polární metoda (Groma): stanovisko, orientace (jedna i více, posun vážený délkami), určovaný bod.
    Volby: výpočet ze směrníků (bez orientace), výpočet pro bodové pole (bod z každé orientace zvlášť)."""
    st = _bod(s, h, "st", "stanovisko")
    ze_smerniku = str(h.get("ze_smerniku") or "").startswith("ano")
    pro_pole = str(h.get("bodove_pole") or "").startswith("ano")
    sm, d = _cislo(h, "sm", "měřený směr"), _cislo(h, "d", "délku")
    if d <= 0:
        raise ChybaVstupu("Délka musí být kladná.")
    n = _nove_cislo(s, h)
    zen = (h.get("zenit") or "").strip()
    dh_trig = None
    vp = _cislo(h, "vp", "výšku přístroje") if (h.get("vp") or "").strip() else 0.0
    if zen:  # prostorová polární metoda: d je šikmá délka
        zg = _cislo(h, "zenit", "zenitový úhel")
        vc = _cislo(h, "vc", "výšku cíle") if (h.get("vc") or "").strip() else 0.0
        _hh, dh_trig = V.trigonometricka_vyska(0.0, d, zg, vp, vc)
        d = d * math.sin(V.gon2rad(zg))
    k, kor = _korekce([st])
    d_m, d = d, d * k
    prot = _hlavicka("Rajón (polární bod)")
    prot.append(f"stanovisko {st.cislo}:  Y = {_f(st.y)}   X = {_f(st.x)}"
                + (f"   Z = {_f(st.z)}" if st.z is not None else "") + (f", výška stroje {_f(vp)} m" if vp else ""))
    prot += kor
    data: dict = {}
    if ze_smerniku:
        posun, orient = 0.0, []
        sig = V.norm_gon(sm)
        prot.append("výpočet ze směrníků: zadaný směr je přímo směrník (bez orientace osnovy)")
    else:
        posun, orient = _orientace_osnovy(s, h, st, k)
        prot += ["", "orientace osnovy:",
                 f"  {'bod':<18} {'směr':>9} {'směrník':>9} {'V or.':>8} {'délka':>9} {'V délky':>8}"]
        for b, smer, smk, v, _w, dl, vd in orient:
            prot.append(f"  {b.cislo:<18} {smer:>9.4f} {smk:>9.4f} {v:>8.4f} "
                        + (f"{dl:>9.3f} {vd:>8.3f}" if dl is not None else f"{'':>9} {'':>8}"))
        prot.append(f"orientační posun {_f(posun, 4)} gon (vážený délkami)")
        data["orientace"] = {b.cislo: (v, vd) for b, _sm, _smk, v, _w, _dl, vd in orient}
        sig = V.norm_gon(sm + posun)
    p = V.rajon(st, sig, d)
    if pro_pole and len(orient) > 1:
        body = []
        prot += ["", f"výpočet pro bodové pole – bod {n} z každé orientace zvlášť:"]
        for b, smer, smk, _v, _w, _dl, _vd in orient:
            pi = V.rajon(st, V.norm_gon(sm + V.norm_gon(smk - smer)), d)
            body.append(pi)
            prot.append(f"  orientace {b.cislo:<14} Y = {_f(pi.y)}   X = {_f(pi.x)}")
        p = V.P(sum(q.y for q in body) / len(body), sum(q.x for q in body) / len(body))
        prot.append(f"  průměr: rozdíly do {max(math.hypot(q.y - p.y, q.x - p.x) for q in body) * 1000:.0f} mm")
    z = None
    if st.z is not None and dh_trig is not None:
        z = st.z + dh_trig
    elif st.z is not None and (h.get("dh") or "").strip():
        z = st.z + _cislo(h, "dh", "převýšení")
    prot += ["", f"bod {n}: směr {_f(sm, 4)} gon → směrník {_f(sig, 4)} gon, délka {_f(d_m)} m"
             + (f" → {_f(d)} m" if kor else "") + (" (vodorovná ze šikmé a zenitu)" if zen else ""),
             *([f"  převýšení terén–terén {_f(dh_trig)} m (zakřivení a refrakce k = 0,13)"] if dh_trig is not None
               else []),
             f"  Y = {_f(p.y)}   X = {_f(p.x)}" + (f"   Z = {_f(z)}" if z is not None else "")]
    kod = (h.get("kod") or "").strip()
    data["bod"] = (n, p.y, p.x, z)
    return Vysledek(prot, [Bod(n, p.y, p.x, z, kod, poznamka="rajón")], data=data)


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


def _orientace(s, h, key: str, st: Bod, nazev: str) -> tuple[float, list[str]]:
    """Řádky „bod směr“ → průměrný orientační posun stanoviska [gon] a řádky protokolu."""
    radky = [r.split() for r in (h.get(key) or "").replace(",", ".").splitlines() if r.strip()]
    if not radky:
        raise ChybaVstupu(f"Zadejte aspoň jednu orientaci na stanovisku {nazev} (řádek: bod směr).")
    posuny, prot = [], []
    for r in radky:
        if len(r) < 2:
            raise ChybaVstupu(f"Orientace „{' '.join(r)}“: zadejte číslo bodu a směr v gonech.")
        b = s.najdi(r[0])
        if b is None:
            raise ChybaVstupu(f"Orientační bod {r[0]} v seznamu souřadnic není.")
        _ruzne(st, b)
        try:
            smer = float(r[1])
        except ValueError:
            raise ChybaVstupu(f"Směr „{r[1]}“ na bod {r[0]} není číslo.") from None
        posuny.append((b.cislo, V.norm_gon(V.smernik(st, b) - smer), V.delka(st, b)))
    # průměr posunů vážený délkami (jako Groma), přes 0/400 gon
    ref = posuny[0][1]
    vazeny = sum(((o - ref + 200) % 400 - 200) * d for _c, o, d in posuny) / sum(d for *_x, d in posuny)
    prumer = V.norm_gon(ref + vazeny)
    for c, o, d in posuny:
        prot.append(f"  {nazev}: orientace na {c}: posun {_f(o, 4)} gon, délka {_f(d)} m, oprava "
                    f"{_f((((prumer - o + 200) % 400) - 200) * 10000 + 0.0, 1).replace('-0.0', '0.0')} cc")
    return prumer, prot


def u_vpred_smery(s, h):
    """Protínání vpřed ze směrů: na obou stanoviscích orientace a směr na určovaný bod (jako v Gromě)."""
    a, b = _bod(s, h, "a", "stanovisko A"), _bod(s, h, "b", "stanovisko B")
    _ruzne(a, b)
    oa, pa = _orientace(s, h, "ora", a, a.cislo)
    ob, pb = _orientace(s, h, "orb", b, b.cislo)
    sa, sb = _cislo(h, "sa", "směr z A na bod"), _cislo(h, "sb", "směr z B na bod")
    n = _nove_cislo(s, h)
    sig_a, sig_b = V.norm_gon(sa + oa), V.norm_gon(sb + ob)
    try:
        p = V.protinani_vpred_smerniky(a, sig_a, b, sig_b)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    gama = abs(((sig_a - sig_b + 200) % 400) - 200)
    prot = _hlavicka("Protínání vpřed ze směrů")
    prot += pa + pb
    prot += [f"stanovisko {a.cislo}: orientační posun {_f(oa, 4)} gon, směr {_f(sa, 4)} → směrník {_f(sig_a, 4)} gon",
             f"stanovisko {b.cislo}: orientační posun {_f(ob, 4)} gon, směr {_f(sb, 4)} → směrník {_f(sig_b, 4)} gon",
             f"úhel protnutí {_f(min(gama, 200 - gama) if gama > 100 else gama, 4)} gon"
             + ("  (POZOR: ostrý úhel protnutí, výsledek je nejistý)" if min(gama, 200 - gama) < 30 else ""),
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    data = {"bod": (n, float(p.y), float(p.x), None)}
    for k_, st_ in (("ora", a), ("orb", b)):
        try:
            _po, orr = _orientace_osnovy(s, {"orientace": h.get(k_)}, st_, 1.0)
            data[k_] = {b_.cislo: (v,) for b_, _s, _k, v, _w, _d, _vd in orr}
        except ChybaVstupu:
            pass
    return Vysledek(prot, [Bod(n, float(p.y), float(p.x), (h.get("kod") or "").strip(),
                               poznamka="protínání vpřed ze směrů")], data=data)


def u_z_delek(s, h):
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    da, db = _cislo(h, "da", "délku z A"), _cislo(h, "db", "délku z B")
    n = _nove_cislo(s, h)
    vlevo = (h.get("strana") or "vlevo") == "vlevo"
    k, kor = _korekce([a, b])
    da, db = da * k, db * k
    try:
        p = V.protinani_z_delek(a, b, da, db, vlevo=vlevo)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Protínání z délek") + kor
    prot += [f"{a.cislo}–{b.cislo}: {_f(V.delka(a, b))} m, dA = {_f(da)} m, dB = {_f(db)} m, bod "
             f"{'vlevo' if vlevo else 'vpravo'} od směru {a.cislo}→{b.cislo}",
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}"]
    return Vysledek(prot, [Bod(n, p.y, p.x, None, (h.get("kod") or "").strip(), poznamka="protínání z délek")],
                    data={"bod": (n, p.y, p.x, None)})


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
    """Volné stanovisko: řádek „bod směr délka“ (vodorovná), nebo „bod směr šikmá zenit [výška cíle]“ –
    pak se z trigonometrických převýšení určí i výška stanoviska (průměr, se zakřivením a refrakcí)."""
    mer, trig, jen_smery = [], [], []
    for i, line in enumerate((h.get("mereni") or "").splitlines(), 1):
        parts = line.replace(",", ".").split()
        if not parts:
            continue
        if len(parts) == 2:  # jen směr (bez délky) – vyrovnání MNČ
            b = s.najdi(parts[0])
            if b is None:
                raise ChybaVstupu(f"Řádek {i}: bod {parts[0]} v seznamu není.")
            try:
                jen_smery.append((b, float(parts[1])))
            except ValueError:
                raise ChybaVstupu(f"Řádek {i}: směr musí být číslo.") from None
            continue
        if len(parts) < 3:
            raise ChybaVstupu(f"Řádek {i}: zadejte „číslo_bodu směr [délka [zenit výška_cíle]]“.")
        b = s.najdi(parts[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {parts[0]} v seznamu není.")
        try:
            vals = [float(t) for t in parts[1:6]]
            if not all(math.isfinite(v) for v in vals) or vals[1] <= 0:
                raise ValueError
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: směr, délka, zenit a výška cíle musí být čísla (délka kladná).") from None
        sm_, d_ = vals[0], vals[1]
        if len(vals) >= 3:  # šikmá délka + zenitový úhel
            z = vals[2]
            vc = vals[3] if len(vals) >= 4 else 0.0
            trig.append((b, d_, z, vc))
            d_ = d_ * math.sin(V.gon2rad(z))
        mer.append((b.cislo, b, sm_, d_))
    n = _nove_cislo(s, h)
    k, kor = _korekce([m[1] for m in mer] + [b for b, _s in jen_smery])
    mer = [(c, b, sm_, d_ * k) for c, b, sm_, d_ in mer]
    vyp = str(h.get("vypocet") or "")
    if vyp:  # Groma: Výpočet = podobnostní / shodnostní transformace, nebo vyrovnání jako vázaná síť
        h = dict(h, metoda="MNČ" if "síť" in vyp or "MNČ" in vyp else "transformace",
                 meritko="volné" if vyp.lower().startswith("podobnost") else "pevné (1)")
    mnc = bool(jen_smery) or str(h.get("metoda") or "").startswith("MNČ")
    if mnc:
        st_yx, posun, prot_mnc = _volne_mnc(n, mer, jen_smery)
        prot = _hlavicka("Volné stanovisko (vyrovnání MNČ – směry a délky)") + kor
        prot += [f"stanovisko {n}:  Y = {_f(st_yx[0])}   X = {_f(st_yx[1])}",
                 f"orientační posun {_f(posun, 4)} gon"] + prot_mnc
        vs_st = V.P(*st_yx)
    else:
        try:
            vs = V.volne_stanovisko(mer, meritko_volne=(h.get("meritko") == "volné"))
        except ValueError as e:
            raise ChybaVstupu(str(e)) from None
        prot = _hlavicka("Volné stanovisko (transformace)") + kor
        prot += [f"stanovisko {n}:  Y = {_f(vs.stanovisko.y)}   X = {_f(vs.stanovisko.x)}",
                 f"orientační posun {_f(vs.posun, 4)} gon, měřítko {vs.meritko:.7f}, "
                 f"střední souřadnicová chyba m0 = {_f(vs.m0)} m", "", "opravy na známých bodech:",
                 "  bod                  vY [m]    vX [m]    vp [m]"]
        for c, vy, vx in vs.opravy:
            prot.append(f"  {c:<18} {vy:>9.3f} {vx:>9.3f} {math.hypot(vy, vx):>9.3f}")
        vs_st = vs.stanovisko
        prot += _orientace_volneho(n, vs_st, mer)
    z_st = None
    vp = _cislo(h, "vp", "výšku přístroje") if (h.get("vp") or "").strip() else 0.0
    s_vyskou = [(b, d_, z, vc) for b, d_, z, vc in trig if b.z is not None]
    if s_vyskou:
        prot += ["", f"výška stanoviska z trigonometrických převýšení (výška přístroje {_f(vp)} m):",
                 "  bod                  H cíle      Δh       H stanoviska"]
        hs = []
        for b, d_, z, vc in s_vyskou:
            _h, dh = V.trigonometricka_vyska(0.0, d_, z, vp, vc)
            hs.append(b.z - dh)
            prot.append(f"  {b.cislo:<18} {b.z:>9.3f} {dh:>9.3f} {b.z - dh:>12.3f}")
        z_st = sum(hs) / len(hs)
        rozp = max(hs) - min(hs)
        prot.append(f"  průměr H = {_f(z_st)} m, rozpětí {rozp * 1000:.0f} mm")
    opravy = {}
    if mer:
        rows = [(c, hz, V.smernik(vs_st, b), math.hypot(b.y - vs_st.y, b.x - vs_st.x) - d_) for c, b, hz, d_ in mer]
        ref = (rows[0][2] - rows[0][1]) % 400
        posun_o = (ref + sum(((sm_ - hz - ref + 200) % 400) - 200 for _c, hz, sm_, _v in rows) / len(rows)) % 400
        for c, hz, sm_, vd in rows:
            opravy[c] = [((sm_ - hz - posun_o + 200) % 400) - 200, vd, None]
    if z_st is not None:
        for b, d_, z, vc in s_vyskou:
            _h, dh = V.trigonometricka_vyska(0.0, d_, z, vp, vc)
            opravy.setdefault(b.cislo, [None, None, None])[2] = (b.z - dh) - z_st
    kod = (h.get("kod") or "").strip()
    return Vysledek(prot, [Bod(n, vs_st.y, vs_st.x, z_st, kod, poznamka="volné stanovisko")],
                    data={"opravy": opravy, "bod": (n, vs_st.y, vs_st.x, z_st)})


def _orientace_volneho(n: str, st, mer: list) -> list[str]:
    """Orientace osnovy na vypočteném volném stanovisku jako v Gromě: posun = prostý průměr
    (směrník − směr), opravy směrů a délek (ze souřadnic − měřená)."""
    rows = []
    for c, b, hz, d in mer:
        sm = V.smernik(st, b)
        rows.append((c, hz, sm, d, math.hypot(b.y - st.y, b.x - st.x) - d))
    ref = (rows[0][2] - rows[0][1]) % 400
    posun = (ref + sum(((sm - hz - ref + 200) % 400) - 200 for _c, hz, sm, _d, _v in rows) / len(rows)) % 400
    vv = [((sm - hz - posun + 200) % 400) - 200 for _c, hz, sm, _d, _v in rows]
    # V or. jako v Gromě: (směrník − směr) − posun
    out = ["", f"Orientace osnovy na bodě {n}", "",
           f"  {'bod':<18} {'Hz':>9} {'Směrník':>9} {'V or.':>8} {'Délka':>9} {'V délky':>8}"]
    for (c, hz, sm, d, vd), v in zip(rows, vv):
        out.append(f"  {c:<18} {hz:>9.4f} {sm:>9.4f} {v:>8.4f} {d:>9.3f} {vd:>8.3f}")
    out.append(f"Orientační posun [g]: {posun:.4f} (směrník nulového směru, prostý průměr jako v Gromě)")
    if len(vv) > 1:
        out.append(f"m0 = SQRT([vv]/(n-1)) [g]: {math.sqrt(sum(v * v for v in vv) / (len(vv) - 1)):.4f}")
    return out


def _volne_mnc(n: str, mer: list, jen_smery: list) -> tuple[tuple[float, float], float, list[str]]:
    """Volné stanovisko vyrovnáním MNČ (směry a délky s váhami podle přesnosti přístroje z Nastavení)."""
    from .nastaveni import aktualni
    from .vyrovnani import Delka, Smer, vyrovnej
    nast = aktualni()
    if n in {b.cislo for _c, b, _s, _d in mer} | {b.cislo for b, _s in jen_smery}:
        raise ChybaVstupu(f"Číslo stanoviska {n} je mezi měřenými body.")
    pevne = {b.cislo: (b.y, b.x) for _c, b, _s, _d in mer}
    pevne.update({b.cislo: (b.y, b.x) for b, _s in jen_smery})
    smery = [Smer(n, b.cislo, sm_) for _c, b, sm_, _d in mer] + [Smer(n, b.cislo, sm_) for b, sm_ in jen_smery]
    delky = [Delka(n, b.cislo, d_) for _c, b, _s, d_ in mer]
    if len(smery) + len(delky) < 4:
        raise ChybaVstupu("Na volné stanovisko je potřeba aspoň 2 body se směrem a délkou, nebo 3 body se směrem.")
    # přibližná poloha: transformací (≥ 2 délky) nebo protínáním zpět ze tří směrů
    if len(mer) >= 2:
        pr = V.volne_stanovisko(mer).stanovisko
        pribl = (pr.y, pr.x)
    else:
        tri = [(b, sm_) for _c, b, sm_, _d in mer] + list(jen_smery)
        if len(tri) < 3:
            raise ChybaVstupu("Bez délek je potřeba směr aspoň na tři známé body.")
        (a, sa), (b_, sb), (c, sc) = tri[:3]
        try:
            pr = V.protinani_zpet(a, b_, c, sa, sb, sc)
        except ValueError as e:
            raise ChybaVstupu(str(e)) from None
        pribl = (pr.y, pr.x)
    try:
        v = vyrovnej(smery, delky, pevne, sigma_smer_cc=nast.sigma_smer_mgon * 10, sigma_delka_mm=nast.sigma_delka_mm,
                     sigma_delka_ppm=nast.sigma_delka_ppm, pribl={n: pribl})
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    yx = v.souradnice[n]
    my, mx, mp = v.stredni_chyby.get(n, (0.0, 0.0, 0.0))
    out = [f"střední chyby: my = {my * 1000:.1f} mm, mx = {mx * 1000:.1f} mm, mp = {mp * 1000:.1f} mm; "
           f"jednotková střední chyba σ0 = {v.sigma0:.2f}, nadbytečných měření {v.redundance}",
           f"váhy: σ směru {nast.sigma_smer_mgon:g} mgon, σ délky {nast.sigma_delka_mm:g} mm + "
           f"{nast.sigma_delka_ppm:g} ppm (Nastavení výpočtů)", "", "opravy měření:",
           "  bod                 směr [cc]   délka [mm]"]
    od = {d.cil: o for d, o in v.opravy_delek}
    for sm_, o in v.opravy_smeru:
        dl = od.get(sm_.cil)
        out.append(f"  {sm_.cil:<18} {o:>10.1f} {'' if dl is None else f'{dl * 1000:>11.1f}'}")
    return yx, v.posuny.get(n, 0.0), out


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
    opravy = {}
    for (b, _), (vy, vx) in zip(pary, t.opravy):
        prot.append(f"  {b.cislo:<18} {vy:>9.3f} {vx:>9.3f} {math.hypot(vy, vx):>9.3f}")
        opravy[b.cislo] = (vy, vx, math.hypot(vy, vx))
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
    return Vysledek(prot, nove, data={"opravy": opravy})


def u_vymera(s, h):
    """Výměra a obvod (Groma Výpočet výměr): body po obvodu; řádek „bod o“ = vrchol oblouku (oblouk je dán
    předchozím bodem, vrcholem a následujícím bodem – připočte se kruhová úseč)."""
    radky = [r.split() for r in (h.get("body") or "").replace(",", " ").replace(";", "\n").splitlines() if r.strip()]
    if len(radky) == 1:  # čísla na jednom řádku
        radky = [[c] for c in radky[0]]
    body, vrch = [], set()
    for r in radky:
        b = s.najdi(r[0])
        if b is None:
            raise ChybaVstupu(f"Bod {r[0]} v seznamu souřadnic není.")
        if len(r) > 1 and r[1].lower() in ("o", "oblouk", "1", "ano"):
            vrch.add(len(body))
        body.append(b)
    if len(body) < 3:
        raise ChybaVstupu("Výměra potřebuje aspoň tři body (zadejte čísla bodů po obvodu).")
    poly = [b for i, b in enumerate(body) if i not in vrch]
    p = V.vymera(poly) if len(poly) >= 3 else 0.0
    obv = 0.0
    use = []
    n = len(body)
    i = 0
    while i < n:
        a = body[i]
        if (i + 1) % n in vrch:
            v, c = body[(i + 1) % n], body[(i + 2) % n]
            sy, sx, r = _kruznice3(a, v, c)
            t = V.delka(a, c)
            uhel = 2 * math.asin(min(1.0, t / (2 * r)))
            # vrchol na opačné straně tětivy než střed → oblouk větší než půlkruh
            if (V.stanicni_kolmice(a, c, v)[1] > 0) == (V.stanicni_kolmice(a, c, V.P(sy, sx))[1] > 0):
                uhel = 2 * math.pi - uhel
            usec = r * r / 2 * (uhel - math.sin(uhel))
            # vrchol mimo obrazec (bez vrcholu) → úseč se přičte, uvnitř → odečte
            s_vrch = abs(V.vymera([b_ for j, b_ in enumerate(body) if j not in vrch or j == (i + 1) % n]))
            ven = s_vrch > abs(p)
            use.append((a.cislo, v.cislo, c.cislo, r, usec if ven else -usec))
            obv += r * uhel
            i += 2
        else:
            obv += V.delka(a, body[(i + 1) % n])
            i += 1
    celkem = abs(p) + sum(u[4] for u in use)
    prot = _hlavicka("Výpočet výměr")
    parc = " ".join(x for x in ((h.get("parcela") or "").strip(), (h.get("dil") or "").strip() and
                                f"díl {(h.get('dil') or '').strip()}") if x)
    if parc:
        prot.append(f"parcela {parc}")
    prot += ["body: " + " – ".join(b.cislo + (" (vrchol oblouku)" if i in vrch else "") for i, b in enumerate(body))]
    for a, v, c, r, u in use:
        prot.append(f"  oblouk {a} – {v} – {c}: poloměr {_f(r)} m, úseč {u:+.2f} m²")
    prot += [f"výměra P = {_f(celkem, 2)} m²  (zaokrouhleně {round(celkem):d} m²)",
             f"obvod  o = {_f(obv)} m"]
    return Vysledek(prot, data={"vymera": celkem, "obvod": obv})


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
        o1 = _f_nebo((h.get("o1") or "").strip() or None) or 0.0
        o2 = _f_nebo((h.get("o2") or "").strip() or None) or 0.0

        def posun(p1, p2, o):  # odsazení: kladné vpravo od směru p1→p2 (záporné vlevo), jako v Gromě
            if not o:
                return p1, p2
            dl = V.delka(p1, p2)
            uy, ux = (p2.y - p1.y) / dl, (p2.x - p1.x) / dl
            return V.P(p1.y + ux * o, p1.x - uy * o), V.P(p2.y + ux * o, p2.x - uy * o)
        a1, b1 = posun(a, b, o1)
        c1, d1 = posun(c, d, o2)
        try:
            body = [V.prusecik_primek(a1, b1, c1, d1)]
        except ValueError as e:
            raise ChybaVstupu(str(e)) from None
        prot.append(f"přímky {a.cislo}–{b.cislo}" + (f" (odsazení {_f(o1)} m)" if o1 else "")
                    + f" a {c.cislo}–{d.cislo}" + (f" (odsazení {_f(o2)} m)" if o2 else ""))
        t1 = V.stanicni_kolmice(a1, b1, body[0])[0] / V.delka(a1, b1)
        prot.append("průsečík leží " + {(True, True): "na obou úsečkách", (True, False): f"na úsečce {a.cislo}–{b.cislo}",
                                         (False, True): f"na úsečce {c.cislo}–{d.cislo}",
                                         (False, False): "mimo obě úsečky"}[
            (0 <= t1 <= 1, 0 <= V.stanicni_kolmice(c1, d1, body[0])[0] / V.delka(c1, d1) <= 1)])
        if a.z is not None and b.z is not None:
            h["_z"] = a.z + (b.z - a.z) * t1
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
    z = h.get("_z")
    for i, p in enumerate(body):
        c = n if i == 0 else n + "b"
        prot.append(f"bod {c}:  Y = {_f(p.y)}   X = {_f(p.x)}" + (f"   Z = {_f(z)}" if z is not None and not i else ""))
        nove.append(Bod(c, p.y, p.x, z if not i else None, (h.get("kod") or "").strip(), poznamka="průsečík"))
    if len(body) > 1:
        prot.append("(dvě řešení – druhé má k číslu připojené „b“)")
    return Vysledek(prot, nove, data={"bod": (n, body[0].y, body[0].x, z)})


def u_vytyceni(s, h):
    """Polární vytyčovací prvky (Groma): Orientace + směry / Orientace + směrníky / Směrníky; směr na orientaci
    (nenulový), délky děleny měřítkem (skutečné délky v terénu), s výškou stroje a cíle i převýšení a zenit."""
    st = _bod(s, h, "st", "stanovisko")
    volba = (h.get("volba") or "Orientace + směry").lower()
    body = _radky_bodu(s, h.get("body") or "")
    if not body:
        raise ChybaVstupu("Zadejte vytyčované body (čísla, nebo je přetáhněte ze seznamu).")
    o = None
    if not volba.startswith("směrník"):
        o = _bod(s, h, "o", "orientaci")
        _ruzne(st, o)
    so = _cislo_nepovinne(h, "so", "směr na orientaci", 0.0) or 0.0
    vp = _cislo_nepovinne(h, "vp", "výšku stroje", None)
    vc = _cislo_nepovinne(h, "vc", "výšku cíle", 0.0) or 0.0
    from .nastaveni import aktualni
    k = aktualni().koeficient() or 1.0
    prot = _hlavicka("Polární vytyčovací prvky")
    prot.append(f"stanovisko {st.cislo}" + (f", orientace na {o.cislo} (směrník {_f(V.smernik(st, o), 4)} gon, "
                                            f"směr na orientaci {_f(so, 4)} gon)" if o else "") + f"; {volba}")
    if abs(k - 1) > 1e-12:
        prot.append(f"délky jsou skutečné (v terénu) – vyděleny měřítkem {k:.10f}")
    prot.append(f"  {'bod':<16} {'směr [gon]':>11} {'směrník [gon]':>14} {'délka [m]':>10}"
                + ("   převýšení   zenit [gon]" if vp is not None else ""))
    vysl = {}
    for b in body:
        if V.delka(st, b) < 1e-9:
            prot.append(f"  {b.cislo:<16} leží na stanovisku")
            continue
        sm = V.smernik(st, b)
        d = V.delka(st, b) / k
        smer = V.norm_gon(sm - V.smernik(st, o) + so) if o is not None and volba.startswith("orientace + směry") \
            else None
        rad = f"  {b.cislo:<16} {('' if smer is None else f'{smer:.4f}'):>11} {sm:>14.4f} {d:>10.3f}"
        dz = zen = None
        if vp is not None and st.z is not None and b.z is not None:
            dz = b.z - st.z
            zen = V.rad2gon(math.atan2(d, dz - vp + vc))
            rad += f" {dz:>11.3f} {zen:>13.4f}"
        prot.append(rad)
        if o is not None and volba.startswith("orientace + směrník"):
            prot.append(f"  {'':<16} z orientace {o.cislo}: směrník {V.smernik(o, b):.4f} gon, délka "
                        f"{V.delka(o, b) / k:.3f} m")
        vysl[b.cislo] = (smer, sm, d, dz, zen)
    return Vysledek(prot, data={"prvky": vysl})


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


R_ZEME = 6_380_000.0  # střední poloměr Země pro redukci z nadmořské výšky (jako Groma)


def u_redukce(s, h):
    """Redukce měřené délky do S-JTSK: šikmá → vodorovná → nulový horizont → zobrazení (Křovák)."""
    from .sjtsk import meritko_zobrazeni
    d = _cislo(h, "d", "měřenou délku")
    if d <= 0:
        raise ChybaVstupu("Délka musí být kladná.")
    z = _cislo_nepovinne(h, "z", "zenitový úhel", None)
    vys = _cislo_nepovinne(h, "H", "nadmořskou výšku", None)
    a = _bod(s, h, "a", "bod A") if (h.get("a") or "").strip() else None
    b = _bod(s, h, "b", "bod B") if (h.get("b") or "").strip() else None
    if vys is None:
        zs = [x.z for x in (a, b) if x is not None and x.z is not None]
        vys = sum(zs) / len(zs) if zs else 0.0
    if not -500 <= vys <= 5000:
        raise ChybaVstupu("Nadmořská výška má být v metrech (−500 až 5000).")
    prot = _hlavicka("Redukce délky")
    dv = d
    if z is not None:
        if not 0 < z < 400:
            raise ChybaVstupu("Zenitový úhel má být v gonech (0–400).")
        dv = d * abs(math.sin(V.gon2rad(z)))
        prot.append(f"šikmá délka {_f(d, 4)} m, zenitový úhel {_f(z, 4)} gon → vodorovná {_f(dv, 4)} m")
    else:
        prot.append(f"vodorovná délka {_f(dv, 4)} m")
    d0 = dv * R_ZEME / (R_ZEME + vys)
    prot.append(f"redukce z nadmořské výšky H = {_f(vys, 1)} m (R = 6380 km): {_f((d0 - dv) * 1000, 1)} mm "
                f"→ {_f(d0, 4)} m")
    m = 1.0
    if a is not None:
        y, x = ((a.y + b.y) / 2, (a.x + b.x) / 2) if b is not None else (a.y, a.x)
        if not (400_000 < y < 950_000 and 900_000 < x < 1_300_000):
            raise ChybaVstupu("Body nejsou v S-JTSK – měřítko zobrazení se počítá jen pro souřadnice v ČR.")
        m = meritko_zobrazeni(y, x)
        prot.append(f"měřítko Křovákova zobrazení v místě: m = {m:.8f} ({(m - 1) * 1e6:+.1f} ppm): "
                    f"{_f((d0 * m - d0) * 1000, 1)} mm")
    else:
        prot.append("měřítko zobrazení: zadejte bod A (případně B), jinak se nezapočte")
    ds = d0 * m
    prot.append(f"délka v S-JTSK  d = {_f(ds, 4)} m   (celková redukce {_f((ds - dv) * 1000, 1)} mm, "
                f"{(ds / dv - 1) * 1e6:+.1f} ppm)")
    if a is not None and b is not None:
        _ruzne(a, b)
        dsour = V.delka(a, b)
        prot.append(f"délka ze souřadnic {a.cislo}–{b.cislo}: {_f(dsour, 4)} m, rozdíl měřená − souřadnicová "
                    f"{_f((ds - dsour) * 1000, 1)} mm")
    return Vysledek(prot)


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


def u_ortogonalni_groma(s, h):
    """Ortogonální metoda (Groma): transformační klíč z identických bodů (řádek: bod staničení kolmice, aspoň
    dva), podobnostní transformace; oprava délky mezi 1. a 2. identickým bodem; určované body (staničení,
    kolmice). Kolmice kladná vpravo."""
    ident = []
    for i, r in enumerate(_radky_mereni(h.get("identicke"), "identické"), 1):
        b = s.najdi(r[0])
        if b is None:
            raise ChybaVstupu(f"Identický bod {r[0]} v seznamu souřadnic není.")
        st_, kol = (_f_nebo(r[k]) if len(r) > k else None for k in (1, 2))
        ident.append((b, st_ or 0.0, kol or 0.0))
    if len(ident) < 2:
        raise ChybaVstupu("Zadejte aspoň dva identické body (číslo, staničení a kolmice).")
    o0, o1 = V.P(0.0, 0.0), V.P(0.0, 1.0)
    mist = [V.bod_ze_stanicni(o0, o1, st_, kol) for _b, st_, kol in ident]
    try:
        t = V.transformace(mist, [(b.y, b.x) for b, _s, _k in ident], "podobnostni")
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    d_sour = V.delka(ident[0][0], ident[1][0])
    d_mist = V.delka(mist[0], mist[1])
    from .nastaveni import aktualni
    k = aktualni().koeficient() or 1.0
    prot = _hlavicka("Ortogonální metoda")
    prot += [f"identických bodů {len(ident)}, měřítko klíče {t.meritko:.6f}",
             f"oprava délky mezi 1. a 2. identickým bodem: {_f(d_sour - d_mist * k)} m "
             f"(ze souřadnic {_f(d_sour)} m, měřeno {_f(d_mist)} m)",
             "", f"  {'bod':<16} {'staničení':>10} {'kolmice':>10} {'dY':>8} {'dX':>8} {'dP':>8}"]
    opravy = {}
    for (b, st_, kol), (vy, vx) in zip(ident, t.opravy):
        opravy[b.cislo] = (vy, vx, math.hypot(vy, vx))
        prot.append(f"  {b.cislo:<16} {st_:>10.3f} {kol:>10.3f} {vy:>8.3f} {vx:>8.3f} {math.hypot(vy, vx):>8.3f}")
    nove = []
    rad = _radky_mereni(h.get("mereni"), "měření")
    if (h.get("nove") or "").strip() and (h.get("st") or "").strip():
        rad.append([h["nove"].strip(), h["st"], h.get("kol") or "0"])
    if not rad:
        raise ChybaVstupu("Zadejte určovaný bod: číslo, staničení a kolmici.")
    prot += ["", "určované body:", f"  {'bod':<16} {'staničení':>10} {'kolmice':>10} {'Y':>12} {'X':>12}"]
    for r in rad:
        if len(r) < 2:
            raise ChybaVstupu(f"Bod {r[0]}: zadejte staničení (a kolmici).")
        st_, kol = _f_nebo(r[1]) or 0.0, (_f_nebo(r[2]) if len(r) > 2 else 0.0) or 0.0
        y, x = t.preved(V.bod_ze_stanicni(o0, o1, st_, kol))
        prot.append(f"  {r[0]:<16} {st_:>10.3f} {kol:>10.3f} {y:>12.3f} {x:>12.3f}")
        nove.append(Bod(r[0], y, x, None, (h.get("kod") or "").strip(), poznamka="ortogonální metoda"))
    return Vysledek(prot, nove, data={"opravy": opravy, "oprava_delky": d_sour - d_mist * k,
                                       "bod": (nove[-1].cislo, nove[-1].y, nove[-1].x, None)})


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
    from .nastaveni import aktualni
    k, kor = _korekce([a, b])
    strany = [(c, d * k) for c, d in strany]
    try:
        r = V.polygonovy_porad(a, ao, b, bo, [u[1] for u in uhly], [d[1] for d in strany], cisla)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    nast = aktualni()
    mez_u, mez_p = nast.mez_polygonu(len(cisla), r.delka)
    ok = abs(r.uhlova_odchylka) <= mez_u and r.polohova <= mez_p
    prot = _hlavicka("Polygonový pořad oboustranně připojený a orientovaný") + kor
    prot += [f"{ao.cislo} → {a.cislo} … {b.cislo} → {bo.cislo}, nových bodů {len(cisla)}, délka {_f(r.delka)} m",
             f"úhlová odchylka {r.uhlova_odchylka * 10000:.0f} cc, mezní {mez_u * 10000:.0f} cc"
             + ("" if abs(r.uhlova_odchylka) <= mez_u else "  ← PŘEKROČENA"),
             f"souřadnicové odchylky dY = {_f(r.dy)} m, dX = {_f(r.dx)} m, polohová {_f(r.polohova)} m, "
             f"mezní {_f(mez_p)} m" + ("" if r.polohova <= mez_p else "  ← PŘEKROČENA"),
             f"(mezní odchylky pro třídu {nast.polygon_trida} – Nastavení výpočtů) → "
             + ("pořad VYHOVUJE" if ok else "pořad NEVYHOVUJE"),
             "",
             "  bod           úhel β [gon] opr.[cc]  směrník [gon]  délka [m]     ΔY [m]     ΔX [m]  vY[mm]  vX[mm]"
             "            Y            X"]
    n_v = len(cisla) + 2
    opr = -r.uhlova_odchylka / n_v * 10000
    vrcholy = [(a.cislo, a.y, a.x)] + [(c, p.y, p.x) for c, p in r.body] + [(b.cislo, b.y, b.x)]
    nove = []
    for i, (c, y, x) in enumerate(vrcholy):
        radek = f"  {c:<12} {uhly[i][1]:>13.4f} {opr:>8.1f}"
        if i < len(r.smerniky):
            d = strany[i][1]
            sg = r.smerniky[i]
            dy_, dx_ = d * math.sin(V.gon2rad(sg)), d * math.cos(V.gon2rad(sg))
            vy_, vx_ = r.vy[i] * 1000, r.vx[i] * 1000
            radek += f" {sg:>14.4f} {d:>10.3f} {dy_:>10.3f} {dx_:>10.3f} {vy_:>7.1f} {vx_:>7.1f}"
        else:
            radek += " " * 68
        radek += f" {y:>12.3f} {x:>12.3f}"
        prot.append(radek.rstrip())
    for c, p in r.body:
        nove.append(Bod(c, p.y, p.x, poznamka="polygonový pořad"))
    prot.append(f"  součty: Σ délek {_f(r.delka)} m, Σ oprav úhlů {-r.uhlova_odchylka * 10000:.1f} cc, "
                f"Σ vY {-r.dy * 1000:.1f} mm, Σ vX {-r.dx * 1000:.1f} mm")
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
    k, kor = _korekce([a])
    strany = [(c, d * k) for c, d in strany]
    try:
        body = V.polygonovy_porad_volny(a, ao, [u[1] for u in uhly], [d[1] for d in strany], cisla)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot = _hlavicka("Polygonový pořad volný (jednostranně připojený)") + kor
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



def u_kruznice_3b(s, h):
    """Kružnice třemi body: střed a poloměr (Groma – Kružnice ze tří bodů)."""
    a, b, c = _bod(s, h, "a", "bod 1"), _bod(s, h, "b", "bod 2"), _bod(s, h, "c", "bod 3")
    ax, ay, bx, by, cx, cy = a.y, a.x, b.y, b.x, c.y, c.x
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9 * max(1.0, V.delka(a, b) * V.delka(b, c)):
        raise ChybaVstupu("Body leží na přímce – kružnice jimi neprochází.")
    # těžiště jako počátek kvůli přesnosti na velkých souřadnicích S-JTSK
    oy, ox = (ay + by + cy) / 3, (ax + bx + cx) / 3
    ax, ay, bx, by, cx, cy = ax - ox, ay - oy, bx - ox, by - oy, cx - ox, cy - oy
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    uy = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    ux = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    sy, sx = uy + ox, ux + oy  # uy je Y (první souřadnice), ux je X
    r = math.hypot(a.y - sy, a.x - sx)
    prot = _hlavicka("Kružnice ze tří bodů")
    prot += [f"body {a.cislo}, {b.cislo}, {c.cislo}",
             f"  střed  Y = {_f(sy)}   X = {_f(sx)}",
             f"  poloměr r = {_f(r)} m, obvod {_f(2 * math.pi * r)} m"]
    nove = []
    n = (h.get("nove") or "").strip()
    if n:
        nove.append(Bod(n, sy, sx, poznamka="střed kružnice"))
    return Vysledek(prot, nove)


def u_uhel(s, h):
    """Vrcholový úhel ze souřadnic: v bodě V od levého ramene L k pravému P (po směru hodin)."""
    v, l_, p_ = _bod(s, h, "v", "vrchol"), _bod(s, h, "l", "levé rameno"), _bod(s, h, "p", "pravé rameno")
    _ruzne(v, l_)
    _ruzne(v, p_)
    sl, sp = V.smernik(v, l_), V.smernik(v, p_)
    w = V.norm_gon(sp - sl)
    prot = _hlavicka("Úhel ze souřadnic")
    prot += [f"vrchol {v.cislo}: směrník na {l_.cislo} {_f(sl, 4)} gon, na {p_.cislo} {_f(sp, 4)} gon",
             f"  úhel ω = {_f(w, 4)} gon  ({_f(w * 0.9, 4)}°), doplněk do 400 gon {_f(400 - w, 4)} gon",
             f"  délky {v.cislo}–{l_.cislo} {_f(V.delka(v, l_))} m, {v.cislo}–{p_.cislo} {_f(V.delka(v, p_))} m"]
    return Vysledek(prot)


def u_bod_na_primce(s, h):
    """Bod na přímce A–B: ve vzdálenosti od A (i za B / před A), nebo dělení úsečky na n dílů."""
    a, b = _bod(s, h, "a", "bod A"), _bod(s, h, "b", "bod B")
    _ruzne(a, b)
    dab = V.delka(a, b)
    ey, ex = (b.y - a.y) / dab, (b.x - a.x) / dab
    prot = _hlavicka("Bod na přímce")
    nove = []
    dily = (h.get("dily") or "").strip()
    if dily:
        try:
            n = int(dily)
        except ValueError:
            raise ChybaVstupu("Počet dílů musí být celé číslo.") from None
        if not 2 <= n <= 1000:
            raise ChybaVstupu("Počet dílů 2 až 1000.")
        zac = _nove_cislo(s, h)
        cisla = _rada_cisel(zac, n - 1)
        prot.append(f"úsečka {a.cislo}–{b.cislo} ({_f(dab)} m) rozdělena na {n} dílů po {_f(dab / n)} m")
        for i, c in enumerate(cisla, 1):
            t = dab * i / n
            nove.append(Bod(c, a.y + ey * t, a.x + ex * t, _z_interp(a, b, i / n), poznamka="dělení úsečky"))
    else:
        t = _cislo(h, "d", "vzdálenost od A")
        c = _nove_cislo(s, h)
        prot.append(f"přímka {a.cislo}–{b.cislo} ({_f(dab)} m), vzdálenost od {a.cislo} {_f(t)} m")
        nove.append(Bod(c, a.y + ey * t, a.x + ex * t, _z_interp(a, b, t / dab), poznamka="bod na přímce"))
    for bb in nove:
        prot.append(f"  {bb.cislo:<14} Y = {_f(bb.y)}   X = {_f(bb.x)}" + (f"   Z = {_f(bb.z)}" if bb.z is not None
                                                                         else ""))
    return Vysledek(prot, nove)


def _z_interp(a, b, t):
    return None if a.z is None or b.z is None else a.z + (b.z - a.z) * t


def _rada_cisel(zac: str, n: int) -> list[str]:
    m = re.match(r"^(.*?)(\d+)$", zac)
    if not m:
        return [f"{zac}{i}" for i in range(1, n + 1)]
    pre, num = m.group(1), m.group(2)
    return [f"{pre}{int(num) + i:0{len(num)}d}" for i in range(n)]


def u_polygon_vetknuty(s, h):
    """Vetknutý pořad: připojený na A a B, ale bez orientací – tvar z měření, poloha a natočení z A a B
    (podobnostní transformace); kontrolou je jen délka (měřítko pořadu)."""
    a, b = _bod(s, h, "a", "počáteční bod"), _bod(s, h, "b", "koncový bod")
    _ruzne(a, b)
    uhly = _radky_cisel(h.get("uhly") or "", 2, "bod úhel[gon]")
    strany = _radky_cisel(h.get("delky") or "", 2, "bod délka[m] (délka strany k dalšímu bodu)")
    if not uhly:
        raise ChybaVstupu("Zadejte vrcholové úhly na nových bodech pořadu.")
    if len(strany) != len(uhly) + 1:
        raise ChybaVstupu(f"Pořad s {len(uhly)} novými body potřebuje {len(uhly) + 1} délek stran.")
    if any(d[1] <= 0 for d in strany):
        raise ChybaVstupu("Délky stran musí být kladné.")
    k, kor = _korekce([a, b])
    delky = [d[1] * k for d in strany]
    sig, y, x, volne = 0.0, 0.0, 0.0, []
    for i, d in enumerate(delky):
        if i:
            sig = V.norm_gon(sig + uhly[i - 1][1] - 200)
        y += d * math.sin(V.gon2rad(sig))
        x += d * math.cos(V.gon2rad(sig))
        volne.append((y, x))
    dv = math.hypot(*volne[-1])
    dab = V.delka(a, b)
    if dv < 1e-9:
        raise ChybaVstupu("Pořad se vrací do počátku – vetknutý pořad nejde vypočítat.")
    q = dab / dv
    rot = V.gon2rad(V.smernik(a, b)) - math.atan2(volne[-1][0], volne[-1][1])
    c, sn = math.cos(rot) * q, math.sin(rot) * q
    from .nastaveni import aktualni
    _mu, mez_p = aktualni().mez_polygonu(len(uhly), sum(delky))
    odch = dv - dab
    prot = _hlavicka("Polygonový pořad vetknutý (bez orientací)") + kor
    prot += [f"{a.cislo} … {b.cislo}, nových bodů {len(uhly)}, délka pořadu {_f(sum(delky))} m",
             f"vzdálenost {a.cislo}–{b.cislo}: ze souřadnic {_f(dab)} m, z měření {_f(dv)} m, odchylka "
             f"{_f(odch)} m (mezní {_f(mez_p)} m)" + ("" if abs(odch) <= mez_p else "  ← PŘEKROČENA"),
             f"měřítko pořadu q = {q:.7f}, stočení {_f(V.norm_gon(V.rad2gon(rot)), 4)} gon",
             "úhlová kontrola není (chybí orientace) – pořad používejte jen výjimečně",
             "  bod                 Y            X"]
    nove = []
    for (c_, _u), (vy, vx) in zip(uhly, volne[:-1]):
        py = a.y + vx * sn + vy * c
        px = a.x + vx * c - vy * sn
        prot.append(f"  {c_:<14} {py:>12.3f} {px:>12.3f}")
        nove.append(Bod(c_, py, px, poznamka="vetknutý polygonový pořad"))
    return Vysledek(prot, nove)


def u_centrace(s, h):
    """Centrace směrů měřených na excentrickém stanovisku S' (excentricita e, směr na centr S):
    centrační změny a směry z centru, přesně ze souřadnic v místní soustavě."""
    e = _cislo(h, "e", "excentricitu e")
    fs = _cislo(h, "fs", "směr na centr")
    if e < 0:
        raise ChybaVstupu("Excentricita musí být kladná.")
    rad = _radky_cisel(h.get("smery") or "", 3, "bod směr[gon] délka[m]")
    if not rad:
        raise ChybaVstupu("Zadejte měřené směry: bod směr délka.")
    sy, sx = e * math.sin(V.gon2rad(fs)), e * math.cos(V.gon2rad(fs))
    prot = _hlavicka("Centrace směrů (excentrické stanovisko)")
    prot += [f"excentricita e = {_f(e)} m, směr na centr {_f(fs, 4)} gon",
             "  bod            měřený směr     délka   centrační změna   centrovaný směr",
             "                    [gon]         [m]         [cc]              [gon]"]
    for c, phi, d in rad:
        if d <= e:
            raise ChybaVstupu(f"Bod {c}: délka musí být větší než excentricita.")
        py, px = d * math.sin(V.gon2rad(phi)), d * math.cos(V.gon2rad(phi))
        cen = V.norm_gon(V.rad2gon(math.atan2(py - sy, px - sx)))
        delta = (cen - phi + 200) % 400 - 200
        prot.append(f"  {c:<14} {phi:>12.4f} {d:>10.3f} {delta * 10000:>14.1f} {cen:>18.4f}")
    return Vysledek(prot)


def u_nivelacni_zapisnik(s, h):
    """Zápisník technické nivelace ze středu: čtení vzad (Z), vpřed (P) a boční záměry (B) po sestavách.

    Řádky: „Z bod čtení [délka]“, „B bod čtení“, „P bod čtení [délka]“ – čtení v metrech (nebo v mm, je-li > 10).
    Sestava = Z, případné B, P. Uzávěr na koncový výškový bod se rozdělí na sestavy (úměrně délkám, jinak rovným
    dílem); boční záměry dostanou výšku z opraveného horizontu přístroje."""
    a, b = _bod(s, h, "a", "počáteční bod"), _bod(s, h, "b", "koncový bod")
    if a.z is None or b.z is None:
        raise ChybaVstupu("Počáteční i koncový bod musí mít výšku.")
    sestavy, cur = [], None
    for i, line in enumerate((h.get("zapisnik") or "").splitlines(), 1):
        t = line.replace(",", ".").split()
        if not t:
            continue
        if len(t) < 3 or t[0].upper() not in ("Z", "P", "B"):
            raise ChybaVstupu(f"Řádek {i}: zadejte „Z|B|P bod čtení [délka]“.")
        try:
            cteni = float(t[2])
            delka = float(t[3]) if len(t) > 3 else None
        except ValueError:
            raise ChybaVstupu(f"Řádek {i}: čtení a délka musí být čísla.") from None
        if abs(cteni) > 10:
            cteni /= 1000.0  # čtení v mm
        druh = t[0].upper()
        if druh == "Z":
            if cur is not None:
                raise ChybaVstupu(f"Řádek {i}: sestava před ním nemá čtení vpřed (P).")
            cur = {"z": (t[1], cteni, delka), "b": [], "p": None}
        elif cur is None:
            raise ChybaVstupu(f"Řádek {i}: sestava musí začít čtením vzad (Z).")
        elif druh == "B":
            cur["b"].append((t[1], cteni))
        else:
            cur["p"] = (t[1], cteni, delka)
            sestavy.append(cur)
            cur = None
    if cur is not None:
        raise ChybaVstupu("Poslední sestava nemá čtení vpřed (P).")
    if not sestavy:
        raise ChybaVstupu("Zápisník je prázdný.")
    if sestavy[0]["z"][0] != a.cislo:
        raise ChybaVstupu(f"První záměra vzad má být na počáteční bod {a.cislo}.")
    if sestavy[-1]["p"][0] != b.cislo:
        raise ChybaVstupu(f"Poslední záměra vpřed má být na koncový bod {b.cislo}.")
    for k in range(1, len(sestavy)):
        if sestavy[k]["z"][0] != sestavy[k - 1]["p"][0]:
            raise ChybaVstupu(f"Sestava {k + 1}: záměra vzad na {sestavy[k]['z'][0]}, ale předchozí vpřed byla "
                              f"na {sestavy[k - 1]['p'][0]} (přestavový bod musí navazovat).")
    delky = [(x["z"][2] or 0.0) + (x["p"][2] or 0.0) for x in sestavy]
    maji_delky = all(x["z"][2] is not None and x["p"][2] is not None for x in sestavy)
    L = sum(delky) if maji_delky else 100.0 * len(sestavy)
    dh = [x["z"][1] - x["p"][1] for x in sestavy]
    w = sum(dh) - (b.z - a.z)
    mez_km = _cislo(h, "mez", "mezní odchylku") if (h.get("mez") or "").strip() else 40.0
    mez = mez_km / 1000.0 * math.sqrt(max(L, 1.0) / 1000.0)
    sz, sp = sum(x["z"][1] for x in sestavy), sum(x["p"][1] for x in sestavy)
    prot = _hlavicka("Nivelační zápisník (nivelace ze středu)")
    prot += [f"{a.cislo} (H = {_f(a.z, 4)}) → {b.cislo} (H = {_f(b.z, 4)}), sestav {len(sestavy)}, délka "
             + (f"{L:.1f} m" if maji_delky else f"neměřena (počítáno 100 m na sestavu = {L:.0f} m)"),
             f"kontrola zápisníku: Σ vzad − Σ vpřed = {_f(sz, 4)} − {_f(sp, 4)} = {_f(sz - sp, 4)} m = Σ Δh",
             f"odchylka uzávěru {w * 1000:.1f} mm, mezní {mez * 1000:.1f} mm ({mez_km:g} mm·√L) – "
             + ("VYHOVUJE" if abs(w) <= mez else "NEVYHOVUJE"),
             "  sest. bod              vzad      vpřed     boční   převýšení  oprava[mm]      výška"]
    H, nove = a.z, []
    for k, (x, d_) in enumerate(zip(sestavy, delky), 1):
        v = -w * (d_ / L if maji_delky and L > 0 else 1 / len(sestavy))
        horiz = H + x["z"][1] + v / 2  # horizont: polovina opravy na záměru vzad (rovnoměrně v sestavě)
        prot.append(f"  {k:>4}  {x['z'][0]:<14} {x['z'][1]:>9.4f} {'':>9} {'':>9} {'':>10} {'':>10} {H:>10.4f}")
        for c, ct in x["b"]:
            hb = horiz - ct
            prot.append(f"        {c:<14} {'':>9} {'':>9} {ct:>9.4f} {'':>10} {'':>10} {hb:>10.4f}")
            nove.append((c, hb))
        H = H + dh[k - 1] + v
        prot.append(f"        {x['p'][0]:<14} {'':>9} {x['p'][1]:>9.4f} {'':>9} {dh[k - 1]:>10.4f} {v * 1000:>10.2f}"
                    f" {H:>10.4f}")
        if k < len(sestavy):
            nove.append((x["p"][0], H))
    vysky = {s.najdi(c).cislo: hz for c, hz in nove if s.najdi(c) is not None and c not in (a.cislo, b.cislo)}
    if vysky:
        prot.append(f"výšky {len(vysky)} bodů ze seznamu souřadnic se tlačítkem Přidat do seznamu zapíšou jako Z")
    return Vysledek(prot, [], vysky)


def u_vymera_z_mer(s, h):
    """Výměra z měr: plocha rozdělená na trojúhelníky se změřenými stranami (Heronův vzorec)."""
    rad = _radky_cisel(h.get("trojuhelniky") or "", 4, "název a b c")
    if not rad:
        raise ChybaVstupu("Zadejte trojúhelníky: název a b c (strany v metrech).")
    prot = _hlavicka("Výměra z měr (trojúhelníky)")
    prot.append("  trojúhelník          a         b         c        výměra [m²]")
    celkem = 0.0
    for nazev, a, b, c in rad:
        if min(a, b, c) <= 0 or a + b <= c or a + c <= b or b + c <= a:
            raise ChybaVstupu(f"Trojúhelník {nazev}: ze stran {a}, {b}, {c} trojúhelník nesestrojíte.")
        p = (a + b + c) / 2
        P = math.sqrt(p * (p - a) * (p - b) * (p - c))
        celkem += P
        prot.append(f"  {nazev:<14} {a:>9.2f} {b:>9.2f} {c:>9.2f} {P:>14.2f}")
    prot.append(f"  celkem {celkem:.2f} m² = {round(celkem)} m² (zaokrouhleno na celé m²)")
    return Vysledek(prot)


def u_polygon_jednostranne_orientovany(s, h):
    """Pořad oboustranně připojený, orientovaný jen na začátku: úhlová kontrola není, souřadnicová odchylka
    se rozdělí úměrně délkám stran."""
    ao, a = _bod(s, h, "ao", "orientaci na začátku"), _bod(s, h, "a", "počáteční bod")
    b = _bod(s, h, "b", "koncový bod")
    _ruzne(a, ao)
    uhly = _radky_cisel(h.get("uhly") or "", 2, "bod úhel[gon]")
    strany = _radky_cisel(h.get("delky") or "", 2, "bod délka[m] (délka strany k dalšímu bodu)")
    n = len(uhly) - 1  # úhly na A a na nových bodech
    if n < 1 or len(strany) != n + 1:
        raise ChybaVstupu("Zadejte úhly na A a na všech nových bodech a o jednu délku víc než nových bodů.")
    k, kor = _korekce([a, b])
    delky = [d[1] * k for d in strany]
    try:
        volne = V.polygonovy_porad_volny(a, ao, [u[1] for u in uhly], delky, [u[0] for u in uhly[1:]] + [b.cislo])
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    ody, odx = volne[-1][1].y - b.y, volne[-1][1].x - b.x
    L = sum(delky)
    from .nastaveni import aktualni
    _mu, mez_p = aktualni().mez_polygonu(n, L)
    pol = math.hypot(ody, odx)
    prot = _hlavicka("Polygonový pořad jednostranně orientovaný") + kor
    prot += [f"{ao.cislo} → {a.cislo} … {b.cislo}, nových bodů {n}, délka {_f(L)} m",
             "úhlová kontrola není (chybí orientace na konci)",
             f"souřadnicové odchylky dY = {_f(ody)} m, dX = {_f(odx)} m, polohová {_f(pol)} m, mezní {_f(mez_p)} m"
             + ("" if pol <= mez_p else "  ← PŘEKROČENA"),
             "  bod                 Y            X"]
    # souřadnicové rozdíly stran z volného pořadu → opravy úměrně |ΔY|, |ΔX| (jako Groma)
    vrch = [(a.y, a.x)] + [(p.y, p.x) for _c, p in volne]
    vy, vx = V.rozdel_odchylku([q[0] - p[0] for p, q in zip(vrch, vrch[1:])],
                               [q[1] - p[1] for p, q in zip(vrch, vrch[1:])], ody, odx)
    nove, sy, sx = [], 0.0, 0.0
    for i, (c, p) in enumerate(volne[:-1]):
        sy, sx = sy + vy[i], sx + vx[i]
        y, x = p.y + sy, p.x + sx
        prot.append(f"  {c:<14} {y:>12.3f} {x:>12.3f}")
        nove.append(Bod(c, y, x, poznamka="polygonový pořad jednostranně orientovaný"))
    return Vysledek(prot, nove)


def u_trig_oboustranne(s, h):
    """Oboustranně měřené převýšení A ↔ B: průměr vylučuje zakřivení Země i refrakci; rozdíl tam–zpět je kontrolou."""
    a = _bod(s, h, "a", "bod A (s výškou)")
    if a.z is None:
        raise ChybaVstupu(f"Bod {a.cislo} nemá výšku.")
    d1, z1 = _cislo(h, "d1", "šikmou délku A→B"), _cislo(h, "z1", "zenit A→B")
    d2, z2 = _cislo(h, "d2", "šikmou délku B→A"), _cislo(h, "z2", "zenit B→A")
    vp1 = _cislo(h, "vp1", "výšku přístroje na A") if (h.get("vp1") or "").strip() else 0.0
    vc1 = _cislo(h, "vc1", "výšku cíle na B") if (h.get("vc1") or "").strip() else 0.0
    vp2 = _cislo(h, "vp2", "výšku přístroje na B") if (h.get("vp2") or "").strip() else 0.0
    vc2 = _cislo(h, "vc2", "výšku cíle na A") if (h.get("vc2") or "").strip() else 0.0
    if min(d1, d2) <= 0:
        raise ChybaVstupu("Délky musí být kladné.")
    tam = d1 * math.cos(V.gon2rad(z1)) + vp1 - vc1
    zpet = d2 * math.cos(V.gon2rad(z2)) + vp2 - vc2
    dh = (tam - zpet) / 2
    rozdil = tam + zpet  # bez zakřivení a refrakce by byl 0 – zbývá jejich vliv a chyby měření
    dv = (d1 * math.sin(V.gon2rad(z1)) + d2 * math.sin(V.gon2rad(z2))) / 2
    oprava = dv * dv * (1 - 0.13) / (2 * 6380000.0)
    n = (h.get("nove") or "").strip()
    prot = _hlavicka("Trigonometrické převýšení oboustranně")
    prot += [f"A = {a.cislo} (H = {_f(a.z)} m), vodorovná délka {_f(dv)} m",
             f"  tam  A→B: šikmá {_f(d1)} m, zenit {_f(z1, 4)} gon, vp {_f(vp1)}, vc {_f(vc1)} → Δh {_f(tam, 4)} m",
             f"  zpět B→A: šikmá {_f(d2)} m, zenit {_f(z2, 4)} gon, vp {_f(vp2)}, vc {_f(vc2)} → Δh {_f(zpet, 4)} m",
             f"  průměrné převýšení A→B Δh = {_f(dh, 4)} m (zakřivení a refrakce se vyloučí)",
             f"  součet tam + zpět {_f(rozdil * 1000, 1)} mm (očekávaný vliv zakřivení a refrakce "
             f"{_f(2 * oprava * 1000, 1)} mm)",
             f"  H_B = {_f(a.z + dh)} m"]
    vysky = {}
    nove = []
    if n:
        b = s.najdi(n)
        if b is not None:
            vysky[b.cislo] = a.z + dh
    return Vysledek(prot, nove, vysky)


def _uhel_z_textu(t: str) -> float:
    """Úhel z textu → gony: „123.4567“ / „123,4567g“ = gony, „45°30'15\"“ nebo „45 30 15 d“ = stupně, „1.2r“ = rad."""
    t = (t or "").strip().lower().replace(",", ".")
    if not t:
        raise ChybaVstupu("Zadejte úhel.")
    try:
        if t.endswith("r"):
            return float(t[:-1]) * 200 / math.pi
        if "°" in t or "'" in t or '"' in t or t.endswith("d"):
            casti = [c for c in re.split(r"[°'\"d\s]+", t) if c]
            vals = [float(c) for c in casti]
            znam = -1 if t.startswith("-") else 1
            st = abs(vals[0]) + (vals[1] / 60 if len(vals) > 1 else 0) + (vals[2] / 3600 if len(vals) > 2 else 0)
            return znam * st / 0.9
        if t.endswith("g"):
            t = t[:-1]
        return float(t)
    except (ValueError, IndexError):
        raise ChybaVstupu(f"Úhel „{t}“ nerozumím – např. 123.4567 (gony), 45°30'15\" nebo 1.2r.") from None


def u_prevod_uhlu(s, h):
    """Převod úhlů mezi gony, stupni (desetinně i ° ' "), radiány a dílci (řádek = jeden úhel)."""
    prot = _hlavicka("Převod úhlů")
    prot.append("  zadáno                gony          stupně       ° ′ ″                 radiány")
    radky = [r for r in (h.get("uhly") or "").splitlines() if r.strip()]
    if not radky:
        raise ChybaVstupu("Zadejte úhly (řádek = úhel).")
    for r in radky:
        g = _uhel_z_textu(r)
        if not math.isfinite(g) or abs(g) > 1e9:
            raise ChybaVstupu(f"Úhel „{r.strip()}“ není konečné číslo.")
        deg = g * 0.9
        a = abs(deg)
        d_ = int(a)
        m_ = int((a - d_) * 60)
        s_ = (a - d_ - m_ / 60) * 3600
        if s_ >= 59.9995:
            s_, m_ = 0.0, m_ + 1
        if m_ == 60:
            m_, d_ = 0, d_ + 1
        dms = f"{'-' if deg < 0 else ''}{d_}°{m_:02d}′{s_:06.3f}″"
        prot.append(f"  {r.strip():<18} {g:>12.5f} {deg:>14.6f}   {dms:<18} {g * math.pi / 200:>12.8f}")
    return Vysledek(prot)

ULOHY: list[tuple[str, str, list[Pole], object]] = [
    ("Směrník a délka", "Směrník, délka a souřadnicové rozdíly mezi dvěma body.",
     [Pole("a", "Bod A"), Pole("b", "Bod B")], u_smernik),
    ("Rajón (polární bod)", "Polární metoda: stanovisko, orientace osnovy (jeden i více bodů) a určovaný bod.",
     [Pole("st", "Stanovisko"), Pole("vp", "Výška stroje [m]", "m"),
      Pole("o", "Orientace (bod)"), Pole("so", "Směr na orientaci [gon]", "gon"),
      Pole("od", "Délka na orientaci [m]", "m"),
      Pole("orientace", "Další orientace (řádek: bod směr [délka])", "radky"),
      Pole("nove", "Číslo určovaného bodu", "text"), Pole("kod", "Kód", "text"),
      Pole("sm", "Směr [gon]", "gon"), Pole("d", "Délka [m] (vodorovná; se zenitem šikmá)", "m"),
      Pole("dh", "Převýšení [m]", "m"), Pole("zenit", "Zenitový úhel [gon]", "gon"),
      Pole("vc", "Výška signálu [m]", "m"),
      Pole("ze_smerniku", "Výpočet ze směrníků", "volba", "ne", ("ne", "ano")),
      Pole("bodove_pole", "Výpočet pro bodové pole", "volba", "ne", ("ne", "ano"))], u_rajon),
    ("Protínání vpřed z úhlů", "Bod z úhlů α (v A) a β (v B) měřených od základny A–B.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("alfa", "Úhel α [gon]", "gon"), Pole("beta", "Úhel β [gon]", "gon"),
      Pole("nove", "Číslo nového bodu", "text")], u_vpred_uhly),
    ("Protínání vpřed ze směrů", "Bod ze směrů měřených na dvou stanoviscích; každé se orientuje na známé body "
     "(posun vážený délkami), jako v Gromě.",
     [Pole("a", "Stanovisko A"), Pole("ora", "Orientace na A (řádek: bod směr)", "radky"),
      Pole("sa", "Směr z A na určovaný bod [gon]", "gon"),
      Pole("b", "Stanovisko B"), Pole("orb", "Orientace na B (řádek: bod směr)", "radky"),
      Pole("sb", "Směr z B na určovaný bod [gon]", "gon"), Pole("nove", "Číslo nového bodu", "text")], u_vpred_smery),
    ("Protínání z délek", "Bod ze dvou měřených délek od známých bodů.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("da", "Délka z A [m]", "m"), Pole("db", "Délka z B [m]", "m"),
      Pole("strana", "Bod leží", "volba", "vlevo", ("vlevo", "vpravo"), "vlevo / vpravo od směru A → B na mapě"),
      Pole("nove", "Číslo nového bodu", "text")], u_z_delek),
    ("Protínání zpět", "Stanovisko z měřených směrů na tři známé body.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("c", "Bod C"), Pole("sa", "Směr na A [gon]", "gon"),
      Pole("sb", "Směr na B [gon]", "gon"), Pole("sc", "Směr na C [gon]", "gon"),
      Pole("nove", "Číslo stanoviska", "text")], u_zpet),
    ("Volné stanovisko", "Stanovisko a orientace z ≥ 2 známých bodů (směr + délka), vyrovnání MNČ s opravami.",
     [Pole("mereni", "Měření (řádek: bod směr[gon] délka[m], nebo bod směr šikmá zenit [výška cíle])",
           "radky"),
      Pole("vypocet", "Výpočet", "volba", "Podobnostní transformace",
           ("Podobnostní transformace", "Shodnostní transformace", "Vyrovnání jako vázaná síť (MNČ)")),
      Pole("vp", "Výška stroje [m]", "m"),
      Pole("nove", "Číslo stanoviska", "text"), Pole("kod", "Kód", "text")], u_volne),
    ("Transformace", "Transformační klíč z identických bodů (shodnostní / podobnostní / afinní) s opravami; "
     "transformace dalších bodů.",
     [Pole("druh", "Druh", "volba", "podobnostní", ("shodnostní", "podobnostní", "afinní")),
      Pole("identicke", "Identické body (řádek: bod Y_cíl X_cíl)", "radky"),
      Pole("transformovat", "Transformovat body (čísla)", "radky"),
      Pole("jung", "Jungova dotransformace", "volba", "ne", ("ne", "ano – opravy z identických bodů")),
      Pole("predpona", "Předpona nových čísel", "text", "T")], u_transformace),
    ("Výměra a obvod", "Výměra a obvod plochy z bodů zadaných po obvodu.",
     [Pole("body", "Body po obvodu (čísla; „bod o“ = vrchol oblouku)", "radky"), Pole("parcela", "Parcela", "text"),
      Pole("dil", "Díl", "text")], u_vymera),
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
    ("Výměra z měr", "Výměra plochy rozdělené na trojúhelníky z měřených stran (Heronův vzorec).",
     [Pole("trojuhelniky", "Trojúhelníky (řádek: název a b c)", "radky")], u_vymera_z_mer),
    ("Kružnice ze tří bodů", "Střed a poloměr kružnice procházející třemi body.",
     [Pole("a", "Bod 1"), Pole("b", "Bod 2"), Pole("c", "Bod 3"),
      Pole("nove", "Číslo středu (nepovinné)", "text")], u_kruznice_3b),
    ("Úhel ze souřadnic", "Vrcholový úhel ve vrcholu od levého k pravému rameni (po směru hodin).",
     [Pole("v", "Vrchol"), Pole("l", "Levé rameno (bod)"), Pole("p", "Pravé rameno (bod)")], u_uhel),
    ("Bod na přímce", "Bod na přímce A–B ve vzdálenosti od A, nebo dělení úsečky na stejné díly.",
     [Pole("a", "Bod A"), Pole("b", "Bod B"), Pole("d", "Vzdálenost od A [m]", "m"),
      Pole("dily", "nebo počet dílů (dělení úsečky)", "text"),
      Pole("nove", "Číslo nového (prvního) bodu", "text")], u_bod_na_primce),
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
    ("Polygonový pořad jednostranně orientovaný", "Připojený na začátku i na konci, orientovaný jen na začátku – "
     "rozdělí se souřadnicová odchylka.",
     [Pole("ao", "Orientace na začátku (bod)"), Pole("a", "Počáteční bod"), Pole("b", "Koncový bod"),
      Pole("uhly", "Vrcholové úhly (řádek: bod úhel) – na A a na nových bodech", "radky"),
      Pole("delky", "Délky stran (řádek: bod délka k dalšímu bodu)", "radky")], u_polygon_jednostranne_orientovany),
    ("Polygonový pořad vetknutý", "Pořad připojený na dva body bez orientací – poloha a natočení z koncových bodů, "
     "kontrolou je jen délka.",
     [Pole("a", "Počáteční bod"), Pole("b", "Koncový bod"),
      Pole("uhly", "Vrcholové úhly na nových bodech (řádek: bod úhel)", "radky"),
      Pole("delky", "Délky stran (řádek: bod délka k dalšímu bodu), o jednu víc než úhlů", "radky")],
     u_polygon_vetknuty),
    ("Centrace směrů", "Excentrické stanovisko: centrační změny a směry převedené na centr (přesný výpočet).",
     [Pole("e", "Excentricita e [m]", "m"), Pole("fs", "Směr na centr [gon]", "gon"),
      Pole("smery", "Měřené směry (řádek: bod směr délka)", "radky")], u_centrace),
    ("Vytyčovací prvky", "Úhel od orientace a délka ze stanoviska pro vytyčení bodů.",
     [Pole("st", "Stanovisko"), Pole("o", "Orientace (bod)"), Pole("so", "Směr na orientaci [gon]", "gon"),
      Pole("volba", "Počítat", "volba", "Orientace + směry", ("Orientace + směry", "Orientace + směrníky", "Směrníky")),
      Pole("vp", "Výška stroje [m]", "m"), Pole("vc", "Výška cíle [m]", "m"),
      Pole("body", "Vytyčované body (čísla)", "radky")], u_vytyceni),
    ("Trigonometrická výška", "Výška bodu ze šikmé délky a zenitového úhlu (se zakřivením a refrakcí).",
     [Pole("st", "Stanovisko (s výškou)"), Pole("d", "Šikmá délka [m]", "m"), Pole("z", "Zenitový úhel [gon]", "gon"),
      Pole("vp", "Výška přístroje [m]", "m"), Pole("vc", "Výška cíle [m]", "m"),
      Pole("nove", "Číslo bodu (nepovinné)", "text")], u_trig_vyska),
    ("Trigonometrická výška oboustranně", "Převýšení měřené tam i zpět – průměr bez vlivu zakřivení a refrakce.",
     [Pole("a", "Bod A (s výškou)"), Pole("d1", "Šikmá délka A→B [m]", "m"), Pole("z1", "Zenit A→B [gon]", "gon"),
      Pole("vp1", "Výška přístroje na A [m]", "m"), Pole("vc1", "Výška cíle na B [m]", "m"),
      Pole("d2", "Šikmá délka B→A [m]", "m"), Pole("z2", "Zenit B→A [gon]", "gon"),
      Pole("vp2", "Výška přístroje na B [m]", "m"), Pole("vc2", "Výška cíle na A [m]", "m"),
      Pole("nove", "Bod B ze seznamu (výška se zapíše)", "text")], u_trig_oboustranne),
    ("Redukce délky", "Měřená délka do S-JTSK: na vodorovnou, do nulového horizontu a měřítkem Křovákova "
     "zobrazení v místě; s body A, B porovná se souřadnicovou délkou (jako Redukce délek v Gromě).",
     [Pole("d", "Měřená délka [m]", "m"),
      Pole("z", "Zenitový úhel [gon] (nepovinné – prázdné = délka je vodorovná)", "gon"),
      Pole("H", "Nadmořská výška [m] (nepovinné – jinak z výšek bodů)", "m"),
      Pole("a", "Bod A (nepovinné – poloha pro měřítko)"), Pole("b", "Bod B (nepovinné)")], u_redukce),
    ("Nivelační pořad", "Výšky bodů pořadu mezi dvěma výškově danými body, rozdělení uzávěru úměrně délkám.",
     [Pole("a", "Počáteční bod"), Pole("b", "Koncový bod"),
      Pole("oddily", "Oddíly (řádek: cílový bod převýšení délka)", "radky"),
      Pole("mez", "Mezní odchylka [mm/√km]", "m", "40")], u_nivelace),
    ("Nivelační zápisník", "Technická nivelace ze středu: čtení vzad / vpřed / boční po sestavách, kontrola zápisníku, "
     "uzávěr a výšky přestavových i bočních bodů.",
     [Pole("a", "Počáteční výškový bod"), Pole("b", "Koncový výškový bod"),
      Pole("zapisnik", "Zápisník (řádky: Z bod čtení [délka] / B bod čtení / P bod čtení [délka])", "radky"),
      Pole("mez", "Mezní odchylka [mm/√km]", "m", "40")], u_nivelacni_zapisnik),
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
    ("Převod úhlů", "Gony ↔ stupně (desetinně i ° ′ ″) ↔ radiány; řádek = jeden úhel (123.4567, 45°30'15\", 1.2r).",
     [Pole("uhly", "Úhly (řádek: hodnota; g = gony, ° nebo d = stupně, r = radiány)", "radky")], u_prevod_uhlu),
    ("Převod S-JTSK ↔ WGS84", "Zeměpisné souřadnice bodů (s odkazem na mapy.cz) a opačně, přesnost ≈ 1 m.",
     [Pole("smer", "Směr", "volba", "S-JTSK → WGS84", ("S-JTSK → WGS84", "WGS84 → S-JTSK")),
      Pole("body", "Body (čísla) pro S-JTSK → WGS84", "radky"),
      Pole("wgs", "WGS84 → S-JTSK (řádek: číslo šířka délka)", "radky")], u_wgs),
]


# ------------------------------------------------------------------ další úlohy podle Gromy 14 (okna Výpočty)
def _kruznice3(a, b, c) -> tuple[float, float, float]:
    """(Y středu, X středu, poloměr) kružnice třemi body (počítáno od těžiště kvůli přesnosti)."""
    oy, ox = (a.y + b.y + c.y) / 3, (a.x + b.x + c.x) / 3
    ay, ax, by, bx, cy, cx = a.y - oy, a.x - ox, b.y - oy, b.x - ox, c.y - oy, c.x - ox
    d = 2 * (ay * (bx - cx) + by * (cx - ax) + cy * (ax - bx))
    if abs(d) < 1e-9 * max(1.0, V.delka(a, b) * V.delka(b, c)):
        raise ChybaVstupu("Body kružnice leží na přímce – kružnice jimi neprochází.")
    sy = ((ay * ay + ax * ax) * (bx - cx) + (by * by + bx * bx) * (cx - ax) + (cy * cy + cx * cx) * (ax - bx)) / d
    sx = ((ay * ay + ax * ax) * (cy - by) + (by * by + bx * bx) * (ay - cy) + (cy * cy + cx * cx) * (by - ay)) / d
    return sy + oy, sx + ox, math.hypot(ay - sy, ax - sx)


def _radky_mereni(text: str, nazev: str) -> list[list[str]]:
    return [r.replace(",", ".").split() for r in (text or "").splitlines() if r.strip()]


def _f_nebo(t: str | None) -> float | None:
    if t is None or t in ("", "-"):
        return None
    try:
        v = float(t)
    except ValueError:
        raise ChybaVstupu(f"„{t}“ není číslo.") from None
    if not math.isfinite(v):
        raise ChybaVstupu(f"„{t}“ není konečné číslo.")
    return v


def u_vyska_stanoviska(s, h):
    """Výpočet výšky stanoviska (Groma): z orientací s výškou – délka + zenitový úhel (trigonometricky,
    se zakřivením a refrakcí), nebo měřené převýšení; výška stanoviska = průměr, opravy V přev."""
    radky = _radky_mereni(h.get("orientace"), "orientace")
    if not radky:
        raise ChybaVstupu("Zadejte orientace s výškou (bod, délka a zenitový úhel nebo převýšení).")
    vp = _cislo(h, "vp", "výšku stroje") if (h.get("vp") or "").strip() else 0.0
    vys, prot_r = [], []
    for i, r in enumerate(radky, 1):
        b = s.najdi(r[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {r[0]} v seznamu souřadnic není.")
        if b.z is None:
            raise ChybaVstupu(f"Řádek {i}: bod {b.cislo} nemá výšku.")
        d, z, dh, vc = (_f_nebo(r[k]) if len(r) > k else None for k in (1, 2, 3, 4))
        vc = vc or 0.0
        if d is not None and z is not None:
            _hh, dhtt = V.trigonometricka_vyska(0.0, d, z, vp, vc)
            zp = f"délka {d:.3f}, zenit {z:.4f}"
        elif dh is not None:
            dhtt = dh + vp - vc
            zp = f"převýšení {dh:.3f}"
        else:
            raise ChybaVstupu(f"Řádek {i}: zadejte délku a zenitový úhel, nebo převýšení.")
        vys.append((b, b.z - dhtt))
        prot_r.append((b, zp, vc, dhtt))
    hst = sum(v for _b, v in vys) / len(vys)
    n = _nove_cislo(s, h)
    prot = _hlavicka("Výpočet výšky stanoviska")
    prot += [f"stanovisko {n}, výška stroje {_f(vp)} m", "",
             f"  {'bod':<18} {'H bodu':>9} {'měření':<32} {'výška cíle':>10} {'Δh':>9} {'H st.':>9} {'V přev.':>8}"]
    opravy = {}
    for (b, zp, vc, dhtt), (_b, v) in zip(prot_r, vys):
        opravy[b.cislo] = [v - hst]
        prot.append(f"  {b.cislo:<18} {b.z:>9.3f} {zp:<32} {vc:>10.3f} {dhtt:>9.3f} {v:>9.3f} {v - hst:>8.3f}")
    prot.append(f"výška stanoviska H = {_f(hst)} m" + (f" (průměr z {len(vys)}, rozpětí "
                                                       f"{(max(v for _b, v in vys) - min(v for _b, v in vys)) * 1000:.0f} mm)"
                                                       if len(vys) > 1 else ""))
    st = s.najdi(n)
    data = {"opravy": opravy, "bod": (n, st.y if st else None, st.x if st else None, hst)}
    if st is not None:
        return Vysledek(prot, [], {n: hst}, data=data)
    yy, xx = (h.get("y") or "").strip(), (h.get("x") or "").strip()
    if yy and xx:
        return Vysledek(prot, [Bod(n, float(yy), float(xx), hst, poznamka="výška stanoviska")], data=data)
    raise ChybaVstupu(f"Stanovisko {n} v seznamu není – zapište jeho souřadnice Y a X, nebo ho nejdřív spočtěte.")


def u_na_primku(s, h):
    """Vyrovnání na přímku (Groma): pata kolmice z bodu na přímku A–B a vzdálenost bodu od přímky."""
    a, b, p = _bod(s, h, "a", "počáteční bod přímky"), _bod(s, h, "b", "koncový bod přímky"), _bod(s, h, "p", "vyrovnávaný bod")
    _ruzne(a, b)
    st, kol = V.stanicni_kolmice(a, b, p)
    q = V.bod_ze_stanicni(a, b, st, 0.0)
    n = (h.get("nove") or "").strip() or p.cislo
    z = None
    if a.z is not None and b.z is not None:
        z = a.z + (b.z - a.z) * st / V.delka(a, b)
    prot = _hlavicka("Vyrovnání na přímku")
    prot += [f"přímka {a.cislo} – {b.cislo}, délka {_f(V.delka(a, b))} m, vyrovnávaný bod {p.cislo}",
             f"  staničení {_f(st)} m, vzdálenost od přímky (kolmice) {_f(kol)} m",
             f"bod {n}:  Y = {_f(q.y)}   X = {_f(q.x)}" + (f"   Z = {_f(z)}" if z is not None else "")]
    return Vysledek(prot, [Bod(n, q.y, q.x, z if z is not None else p.z, p.kod, p.kvalita, "vyrovnání na přímku")],
                    data={"bod": (n, q.y, q.x, z), "vzdalenost": kol})


def u_na_kruznici(s, h):
    """Vyrovnání na kružnici (Groma): středový průmět bodu na kružnici danou třemi body."""
    k1, k2, k3 = _bod(s, h, "k1", "1. bod kružnice"), _bod(s, h, "k2", "2. bod kružnice"), _bod(s, h, "k3", "3. bod kružnice")
    p = _bod(s, h, "p", "vyrovnávaný bod")
    sy, sx, r = _kruznice3(k1, k2, k3)
    d = math.hypot(p.y - sy, p.x - sx)
    if d < 1e-9:
        raise ChybaVstupu("Vyrovnávaný bod je ve středu kružnice – průmět není určený.")
    q = V.P(sy + (p.y - sy) * r / d, sx + (p.x - sx) * r / d)
    n = (h.get("nove") or "").strip() or p.cislo
    prot = _hlavicka("Vyrovnání na kružnici")
    prot += [f"kružnice {k1.cislo}, {k2.cislo}, {k3.cislo}: střed Y = {_f(sy)} X = {_f(sx)}, poloměr {_f(r)} m",
             f"vyrovnávaný bod {p.cislo}: vzdálenost od kružnice {_f(d - r)} m",
             f"bod {n}:  Y = {_f(q.y)}   X = {_f(q.x)}"]
    return Vysledek(prot, [Bod(n, q.y, q.x, p.z, p.kod, p.kvalita, "vyrovnání na kružnici")],
                    data={"bod": (n, q.y, q.x, p.z), "vzdalenost": d - r})


def _definicni(s, h) -> list[tuple[Bod, bool]]:
    out = []
    for i, r in enumerate(_radky_mereni(h.get("body"), "body"), 1):
        b = s.najdi(r[0])
        if b is None:
            raise ChybaVstupu(f"Řádek {i}: bod {r[0]} v seznamu souřadnic není.")
        out.append((b, not (len(r) > 1 and r[1] in ("0", "ne", "-"))))
    return out


def u_vyrovnavaci_primka(s, h):
    """Vyrovnávací přímka (Groma): přímka MNČ (min. součet čtverců kolmých vzdáleností), vzdálenosti bodů
    a průměty bodů na přímku. Řádek: bod [1 = definiční (výchozí) / 0 = jen vzdálenost]."""
    body = _definicni(s, h)
    defin = [b for b, d in body if d]
    if len(defin) < 2:
        raise ChybaVstupu("Vyrovnávací přímka potřebuje aspoň dva definiční body.")
    my, mx = sum(b.y for b in defin) / len(defin), sum(b.x for b in defin) / len(defin)
    syy = sum((b.y - my) ** 2 for b in defin)
    sxx = sum((b.x - mx) ** 2 for b in defin)
    syx = sum((b.y - my) * (b.x - mx) for b in defin)
    th = 0.5 * math.atan2(2 * syx, syy - sxx)  # směr přímky v rovině (Y, X)
    uy, ux = math.cos(th), math.sin(th)

    def proj(b):
        t = (b.y - my) * uy + (b.x - mx) * ux
        return t, (b.y - my) * ux - (b.x - mx) * uy, V.P(my + t * uy, mx + t * ux)
    vse = str(h.get("vse") or "ano").startswith("ano")
    pre = (h.get("predpona") or "").strip()
    prot = _hlavicka("Vyrovnávací přímka")
    prot += [f"definičních bodů {len(defin)}, směrník přímky {_f(V.norm_gon(V.rad2gon(math.atan2(uy, ux))), 4)} gon",
             "", f"  {'bod':<18} {'def.':>4} {'vzdálenost [m]':>15}"]
    vzd, nove = {}, []
    for b, d in body:
        _t, v, _q = proj(b)
        vzd[b.cislo] = [v]
        prot.append(f"  {b.cislo:<18} {'ano' if d else 'ne':>4} {v:>15.3f}")
    ts = [proj(b)[0] for b in defin]
    k1, k2 = V.P(my + min(ts) * uy, mx + min(ts) * ux), V.P(my + max(ts) * uy, mx + max(ts) * ux)
    prot += ["", f"koncové body přímky:  Y = {_f(k1.y)} X = {_f(k1.x)}  –  Y = {_f(k2.y)} X = {_f(k2.x)}",
             "", "průměty bodů na přímku:"]
    for b, d in body:
        if not d and not vse:
            continue
        _t, v, q = proj(b)
        nove.append(Bod(pre + b.cislo, q.y, q.x, b.z, b.kod, b.kvalita, "vyrovnávací přímka"))
        prot.append(f"  {pre + b.cislo:<18} Y = {_f(q.y)}   X = {_f(q.x)}   vzdálenost {_f(v)} m")
    if len(defin) > 2:
        m0 = math.sqrt(sum(proj(b)[1] ** 2 for b in defin) / (len(defin) - 2))
        prot.append(f"střední vzdálenost od přímky m0 = {_f(m0)} m")
    return Vysledek(prot, nove, data={"opravy": vzd, "koncove": (k1, k2)})


def u_vyrovnavaci_kruznice(s, h):
    """Vyrovnávací kružnice (Groma): kružnice MNČ (iteračně, start ze tří bodů), volitelně s pevným poloměrem;
    vzdálenosti bodů od kružnice, střed a průměty bodů na kružnici."""
    body = _definicni(s, h)
    defin = [b for b, d in body if d]
    if len(defin) < 3:
        raise ChybaVstupu("Vyrovnávací kružnice potřebuje aspoň tři definiční body.")
    sy, sx, r = _kruznice3(defin[0], defin[len(defin) // 2], defin[-1])
    pevny = _f_nebo((h.get("r") or "").strip() or None)
    if pevny is not None:
        r = pevny
    for _it in range(50):  # Gauss–Newton: v_i = |P_i − S| − r
        rows, rhs = [], []
        for b in defin:
            d = math.hypot(b.y - sy, b.x - sx) or 1e-12
            rows.append([-(b.y - sy) / d, -(b.x - sx) / d] + ([] if pevny is not None else [-1.0]))
            rhs.append(-(d - r))
        n = len(rows[0])
        ata = [[sum(rw[i] * rw[j] for rw in rows) for j in range(n)] for i in range(n)]
        atb = [sum(rw[i] * v for rw, v in zip(rows, rhs)) for i in range(n)]
        try:
            dx = _resit(ata, atb)
        except ZeroDivisionError:
            raise ChybaVstupu("Kružnici nelze vyrovnat (body leží na přímce?).") from None
        sy, sx = sy + dx[0], sx + dx[1]
        if pevny is None:
            r += dx[2]
        if max(abs(v) for v in dx) < 1e-9:
            break
    else:
        raise ChybaVstupu("Vyrovnání kružnice nekonverguje – zkontrolujte body a pevný poloměr.")
    pre = (h.get("predpona") or "").strip()
    stred = (h.get("stred") or "").strip()
    vse = str(h.get("vse") or "ano").startswith("ano")
    prot = _hlavicka("Vyrovnávací kružnice")
    prot += [f"definičních bodů {len(defin)}" + (", pevný poloměr" if pevny is not None else ""),
             f"střed  Y = {_f(sy)}   X = {_f(sx)}, poloměr r = {_f(r)} m", "",
             f"  {'bod':<18} {'def.':>4} {'vzdálenost [m]':>15}"]
    vzd, nove = {}, []
    for b, d in body:
        v = math.hypot(b.y - sy, b.x - sx) - r
        vzd[b.cislo] = [v]
        prot.append(f"  {b.cislo:<18} {'ano' if d else 'ne':>4} {v:>15.3f}")
    if stred:
        nove.append(Bod(stred, sy, sx, poznamka="střed vyrovnávací kružnice"))
    prot += ["", "průměty bodů na kružnici:"]
    for b, d in body:
        if not d and not vse:
            continue
        dd = math.hypot(b.y - sy, b.x - sx) or 1e-12
        q = V.P(sy + (b.y - sy) * r / dd, sx + (b.x - sx) * r / dd)
        nove.append(Bod(pre + b.cislo, q.y, q.x, b.z, b.kod, b.kvalita, "vyrovnávací kružnice"))
        prot.append(f"  {pre + b.cislo:<18} Y = {_f(q.y)}   X = {_f(q.x)}")
    return Vysledek(prot, nove, data={"opravy": vzd, "stred": (sy, sx, r)})


def _resit(a: list[list[float]], b: list[float]) -> list[float]:
    """Malá soustava lineárních rovnic (Gaussova eliminace s výběrem pivotu)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-15:
            raise ZeroDivisionError
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def u_prusecik_smer(s, h):
    """Průsečík přímka – směr (Groma): orientovaný směr ze stanoviska (orientace jako u polární metody)
    a přímka A–B; výška z paprsku, pokud je výška stanoviska, výška stroje a zenitový úhel."""
    st = _bod(s, h, "st", "stanovisko")
    a, b = _bod(s, h, "a", "bod A přímky"), _bod(s, h, "b", "bod B přímky")
    _ruzne(a, b)
    k, kor = _korekce([st])
    posun, orient = _orientace_osnovy(s, h, st, k)
    sm = _cislo(h, "sm", "měřený směr")
    sig = V.norm_gon(sm + posun)
    t = V.rajon(st, sig, 1000.0)
    try:
        p = V.prusecik_primek(st, t, a, b)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    n = _nove_cislo(s, h)
    z = None
    zen = (h.get("zenit") or "").strip()
    if zen and st.z is not None:
        vp = _cislo(h, "vp", "výšku stroje") if (h.get("vp") or "").strip() else 0.0
        d = V.delka(st, p)
        z = st.z + vp + d / math.tan(V.gon2rad(_cislo(h, "zenit", "zenitový úhel")))
    prot = _hlavicka("Průsečík přímka - směr") + kor
    prot += [f"stanovisko {st.cislo}, orientační posun {_f(posun, 4)} gon, směr {_f(sm, 4)} → směrník {_f(sig, 4)} gon",
             f"přímka {a.cislo} – {b.cislo}",
             f"bod {n}:  Y = {_f(p.y)}   X = {_f(p.x)}" + (f"   Z = {_f(z)}" if z is not None else "")]
    return Vysledek(prot, [Bod(n, p.y, p.x, z, (h.get("kod") or "").strip(), poznamka="průsečík přímka - směr")],
                    data={"orientace": {b_.cislo: (v, vd) for b_, _s, _k, v, _w, _d, vd in orient},
                          "bod": (n, p.y, p.x, z)})


def u_prusecik_kruznice3(s, h):
    """Průsečík přímka – kružnice (Groma): kružnice třemi body, přímka dvěma body; dvě řešení."""
    k1, k2, k3 = _bod(s, h, "k1", "1. bod kružnice"), _bod(s, h, "k2", "2. bod kružnice"), _bod(s, h, "k3", "3. bod kružnice")
    a, b = _bod(s, h, "a", "bod A přímky"), _bod(s, h, "b", "bod B přímky")
    _ruzne(a, b)
    sy, sx, r = _kruznice3(k1, k2, k3)
    body = V.prusecik_primky_kruznice(a, b, V.P(sy, sx), r)
    if not body:
        raise ChybaVstupu("Přímka kružnici neprotíná.")
    n = _nove_cislo(s, h)
    reseni = 1 if str(h.get("reseni") or "1").startswith("2") and len(body) > 1 else 0
    prot = _hlavicka("Průsečík přímka - kružnice")
    prot += [f"kružnice {k1.cislo}, {k2.cislo}, {k3.cislo}: střed Y = {_f(sy)} X = {_f(sx)}, r = {_f(r)} m",
             f"přímka {a.cislo} – {b.cislo}"]
    for i, p in enumerate(body, 1):
        prot.append(f"  řešení {i}:  Y = {_f(p.y)}   X = {_f(p.x)}" + ("  ← uloženo" if i - 1 == reseni else ""))
    p = body[reseni]
    return Vysledek(prot, [Bod(n, p.y, p.x, poznamka="průsečík přímka - kružnice")], data={"bod": (n, p.y, p.x, None)})


def u_konstrukcni(s, h):
    """Konstrukční oměrné (Groma): obrazec z oměrných (pravé úhly, + vpravo / − vlevo od předchozí spojnice),
    umístěný shodnostní nebo podobnostní transformací na body o známých souřadnicích (aspoň dva)."""
    radky = _radky_mereni(h.get("mereni"), "oměrné")
    if len(radky) < 3:
        raise ChybaVstupu("Zadejte body obrazce s oměrnými (řádek: bod oměrná), aspoň tři.")
    lok = [(radky[0][0], 0.0, 0.0)]
    smer = (0.0, 1.0)  # (dY, dX) – první strana do +X místní soustavy
    for i, r in enumerate(radky[1:], 2):
        m = _f_nebo(r[1] if len(r) > 1 else None)
        if m is None:
            raise ChybaVstupu(f"Řádek {i}: zadejte oměrnou.")
        if i > 2:  # od třetího bodu: pravý úhel vpravo (+) nebo vlevo (−)
            smer = (smer[1], -smer[0]) if m > 0 else (-smer[1], smer[0])
        d = abs(m) if i > 2 else m
        y0, x0 = lok[-1][1], lok[-1][2]
        lok.append((r[0], y0 + smer[0] * d, x0 + smer[1] * d))
    prot = _hlavicka("Konstrukční oměrné")
    uzavr = len(lok) > 3 and lok[0][0] == lok[-1][0]
    if uzavr:
        ey, ex = lok[-1][1] - lok[0][1], lok[-1][2] - lok[0][2]
        prot.append(f"uzavřený obrazec: uzávěr dY = {_f(ey)} m, dX = {_f(ex)} m – rozdělen úměrně pořadí")
        n = len(lok) - 1
        lok = [(c, y - ey * i / n, x - ex * i / n) for i, (c, y, x) in enumerate(lok)][:-1]
    zdroj, cil = [], []
    for c, y, x in lok:
        b = s.najdi(c)
        if b is not None:
            zdroj.append(V.P(y, x))
            cil.append((b.y, b.x))
    if len(zdroj) < 2:
        raise ChybaVstupu("Mezi body obrazce musí být aspoň dva body o známých souřadnicích.")
    druh = "podobnostni" if str(h.get("druh") or "").startswith("podob") else "shodnostni"
    try:
        t = V.transformace(zdroj, cil, druh)
    except ValueError as e:
        raise ChybaVstupu(str(e)) from None
    prot += [f"identických bodů {len(zdroj)}, transformace {'podobnostní' if druh == 'podobnostni' else 'shodnostní'}, "
             f"měřítko {t.meritko:.6f}, m0 = {_f(t.m0)} m", "",
             f"  {'bod':<18} {'Y':>12} {'X':>12}"]
    jen_nove = str(h.get("jen_nove") or "ano").startswith("ano")
    nove = []
    for c, y, x in lok:
        yy, xx = t.preved(V.P(y, x))
        dany = s.najdi(c) is not None
        prot.append(f"  {c:<18} {yy:>12.3f} {xx:>12.3f}" + ("  (identický)" if dany else ""))
        if not (dany and jen_nove):
            nove.append(Bod(c, yy, xx, poznamka="konstrukční oměrné"))
    return Vysledek(prot, nove)


def u_trojuhelnik(s, h):
    """Trojúhelníková kalkulačka (Groma): ze tří údajů (strany a, b, c a úhly α, β, γ v gonech, ne tři úhly)
    dopočte zbytek trojúhelníku, výměru a výšky."""
    a, b, c = (_f_nebo((h.get(k) or "").strip() or None) for k in ("a", "b", "c"))
    al, be, ga = (_f_nebo((h.get(k) or "").strip() or None) for k in ("alfa", "beta", "gama"))
    rad = V.gon2rad
    strany = [x for x in (a, b, c) if x is not None]
    uhly = [x for x in (al, be, ga) if x is not None]
    if len(strany) + len(uhly) < 3 or not strany:
        raise ChybaVstupu("Zadejte aspoň tři údaje, z toho aspoň jednu stranu (ne tři úhly).")
    if any(x <= 0 for x in strany + uhly):
        raise ChybaVstupu("Strany i úhly musí být kladné.")
    if len(uhly) >= 2:  # dva úhly → třetí
        if al is None:
            al = 200 - be - ga
        elif be is None:
            be = 200 - al - ga
        elif ga is None:
            ga = 200 - al - be
        if min(al, be, ga) <= 0:
            raise ChybaVstupu("Součet úhlů musí být 200 gon.")
        k = next(x / math.sin(rad(u)) for x, u in ((a, al), (b, be), (c, ga)) if x is not None)
        a, b, c = (k * math.sin(rad(u)) for u in (al, be, ga))
    elif len(strany) == 3:
        if max(strany) * 2 >= sum(strany):
            raise ChybaVstupu("Strany nesplňují trojúhelníkovou nerovnost.")
    elif len(strany) == 2 and len(uhly) == 1:
        if a is None and al is not None or b is None and be is not None or c is None and ga is not None:
            # úhel proti chybějící straně (sevřený úhel) → kosinová věta
            if a is None:
                a = math.sqrt(b * b + c * c - 2 * b * c * math.cos(rad(al)))
            elif b is None:
                b = math.sqrt(a * a + c * c - 2 * a * c * math.cos(rad(be)))
            else:
                c = math.sqrt(a * a + b * b - 2 * a * b * math.cos(rad(ga)))
        else:  # úhel proti známé straně (SSA) – jednoznačné řešení s ostrým úhlem
            par = [(a, al, "a"), (b, be, "b"), (c, ga, "c")]
            zn = next(p for p in par if p[0] is not None and p[1] is not None)
            k = zn[0] / math.sin(rad(zn[1]))
            dr = next(p for p in par if p[0] is not None and p[1] is None)
            sv = dr[0] / k
            if sv > 1:
                raise ChybaVstupu("Trojúhelník s těmito údaji neexistuje.")
            u2 = V.rad2gon(math.asin(sv))
            u3 = 200 - zn[1] - u2
            if u3 <= 0:
                raise ChybaVstupu("Trojúhelník s těmito údaji neexistuje.")
            vals = {zn[2]: (zn[0], zn[1]), dr[2]: (dr[0], u2)}
            tret = ({"a", "b", "c"} - set(vals)).pop()
            vals[tret] = (k * math.sin(rad(u3)), u3)
            (a, al), (b, be), (c, ga) = vals["a"], vals["b"], vals["c"]
    else:
        raise ChybaVstupu("Z těchto údajů nejde trojúhelník určit – zadejte jinou trojici.")

    def uhel(x, y, z):  # úhel proti straně x
        return V.rad2gon(math.acos(max(-1.0, min(1.0, (y * y + z * z - x * x) / (2 * y * z)))))
    al, be, ga = uhel(a, b, c), uhel(b, a, c), uhel(c, a, b)
    sp = (a + b + c) / 2
    pl = math.sqrt(max(0.0, sp * (sp - a) * (sp - b) * (sp - c)))
    prot = _hlavicka("Trojúhelníková kalkulačka")
    prot += [f"  a = {_f(a)} m   b = {_f(b)} m   c = {_f(c)} m",
             f"  α = {_f(al, 4)} gon   β = {_f(be, 4)} gon   γ = {_f(ga, 4)} gon",
             f"  výměra P = {_f(pl, 2)} m², obvod {_f(a + b + c)} m",
             f"  výšky: va = {_f(2 * pl / a)} m, vb = {_f(2 * pl / b)} m, vc = {_f(2 * pl / c)} m"]
    return Vysledek(prot, data={"hodnoty": {"a": a, "b": b, "c": c, "alfa": al, "beta": be, "gama": ga, "P": pl}})


def u_polygon_groma(s, h):
    """Polygonový pořad jako v Gromě: počáteční a koncový bod s orientacemi, měřená data po stanoviscích
    (směr a délka zpět / vpřed); typ pořadu se pozná sám ze zadání."""
    a = _bod(s, h, "a", "počáteční bod")
    b = _bod(s, h, "b", "koncový bod")
    rad = _radky_mereni(h.get("mereni"), "měřená data")
    if len(rad) < 2:
        raise ChybaVstupu("Zadejte měřená data: počáteční bod, nové body a koncový bod (řádek: bod směr_zpět "
                          "délka_zpět směr_vpřed délka_vpřed).")
    if rad[0][0] != a.cislo or rad[-1][0] != b.cislo:
        raise ChybaVstupu("První řádek měřených dat musí být počáteční bod a poslední koncový bod pořadu.")
    st = [(r[0], *[_f_nebo(r[k]) if len(r) > k else None for k in (1, 2, 3, 4)]) for r in rad]
    cisla = [r[0] for r in st[1:-1]]
    # délky stran: průměr vpřed z i a zpět z i+1
    strany = []
    for i in range(len(st) - 1):
        d = [x for x in (st[i][4], st[i + 1][2]) if x is not None]
        if not d:
            raise ChybaVstupu(f"Chybí délka strany {st[i][0]} – {st[i + 1][0]}.")
        strany.append(sum(d) / len(d))
    # vrcholové úhly na nových bodech: vpřed − zpět
    uhly_n = []
    for c, sz, _dz, sv, _dv in st[1:-1]:
        if sz is None or sv is None:
            raise ChybaVstupu(f"Na bodě {c} zadejte směr zpět i vpřed.")
        uhly_n.append(V.norm_gon(sv - sz))
    or_a = bool((h.get("ora") or "").strip())
    or_b = bool((h.get("orb") or "").strip())
    k, _kor = _korekce([a, b])

    def uhel_orient(bod, klic, smer, vpred: bool):
        posun, orient = _orientace_osnovy(s, {"orientace": h.get(klic)}, bod, k)
        o = orient[0][0]
        # úhel od orientace k sousednímu bodu (vpřed) / od sousedního k orientaci (zpět)
        return o, (V.norm_gon(smer + posun - V.smernik(bod, o)) if vpred else V.norm_gon(V.smernik(bod, o) - (smer + posun)))
    d = {"delky": "\n".join(f"{st[i][0]} {strany[i]}" for i in range(len(strany)))}
    if a.cislo == b.cislo and or_a:
        typ = "uzavřený"
        o, ua = uhel_orient(a, "ora", st[0][3], True)
        _o2, ub = uhel_orient(b, "ora", st[-1][1], False)
        d.update(ao=o.cislo, a=a.cislo, uhly="\n".join(
            f"{c} {u}" for c, u in [(a.cislo, ua)] + list(zip(cisla, uhly_n)) + [(a.cislo, ub)]))
        r = u_polygon_uzavreny(s, d)
    elif or_a and or_b:
        typ = "oboustranně připojený a orientovaný"
        o, ua = uhel_orient(a, "ora", st[0][3], True)
        ob, ub = uhel_orient(b, "orb", st[-1][1], False)
        d.update(ao=o.cislo, a=a.cislo, b=b.cislo, bo=ob.cislo, uhly="\n".join(
            f"{c} {u}" for c, u in [(a.cislo, ua)] + list(zip(cisla, uhly_n)) + [(b.cislo, ub)]))
        r = u_polygon(s, d)
    elif or_a and h.get("volny") != "ano" and s.najdi(b.cislo) is not None:
        typ = "oboustranně připojený, jednostranně orientovaný"
        o, ua = uhel_orient(a, "ora", st[0][3], True)
        d.update(ao=o.cislo, a=a.cislo, b=b.cislo, uhly="\n".join(
            f"{c} {u}" for c, u in [(a.cislo, ua)] + list(zip(cisla, uhly_n))))
        r = u_polygon_jednostranne_orientovany(s, d)
    elif not or_a and not or_b:
        typ = "vetknutý (bez orientací)"
        d.update(a=a.cislo, b=b.cislo, uhly="\n".join(f"{c} {u}" for c, u in zip(cisla, uhly_n)))
        r = u_polygon_vetknuty(s, d)
    else:
        raise ChybaVstupu("Orientaci zadejte na počátečním bodě (pořad jen orientovaný na konci obraťte).")
    r.protokol.insert(3, f"typ pořadu: {typ}")
    r.data["typ"] = typ
    return r


def u_vyskovy_porad(s, h):
    """Výškový pořad (Groma): trigonometrická převýšení mezi body pořadu měřená vpřed a zpět (délka, zenit,
    výška stroje a cíle), průměr, uzávěr na koncový bod a jeho rozdělení úměrně délkám."""
    a, b = _bod(s, h, "a", "počáteční bod"), _bod(s, h, "b", "koncový bod")
    if a.z is None or b.z is None:
        raise ChybaVstupu("Počáteční i koncový bod musí mít výšku.")
    rad = _radky_mereni(h.get("mereni"), "měření")
    # řádek: bod výška_stroje délka_zpět zenit_zpět výška_cíle_zpět délka_vpřed zenit_vpřed výška_cíle_vpřed
    st = []
    for i, r in enumerate(rad, 1):
        st.append((r[0], *[_f_nebo(r[k]) if len(r) > k else None for k in range(1, 8)]))
    if len(st) < 2 or st[0][0] != a.cislo or st[-1][0] != b.cislo:
        raise ChybaVstupu("Měření zadejte od počátečního ke koncovému bodu (první a poslední řádek).")
    oddily = []
    for i in range(len(st) - 1):
        c0, vp0, *_z, dv, zv, vcv = st[i]
        c1, vp1, dz, zz, vcz, *_v = st[i + 1]
        dh, dd = [], []
        if dv is not None and zv is not None:
            _hh, x = V.trigonometricka_vyska(0.0, dv, zv, vp0 or 0.0, vcv or 0.0)
            dh.append(x)
            dd.append(dv * math.sin(V.gon2rad(zv)))
        if dz is not None and zz is not None:
            _hh, x = V.trigonometricka_vyska(0.0, dz, zz, vp1 or 0.0, vcz or 0.0)
            dh.append(-x)
            dd.append(dz * math.sin(V.gon2rad(zz)))
        if not dh:
            raise ChybaVstupu(f"Mezi body {c0} a {c1} chybí měření (délka a zenit vpřed nebo zpět).")
        oddily.append((c1, sum(dh) / len(dh), sum(dd) / len(dd), dh))
    sum_dh = sum(o[1] for o in oddily)
    sum_d = sum(o[2] for o in oddily)
    uzaver = (b.z - a.z) - sum_dh
    prot = _hlavicka("Výškový pořad")
    prot += [f"{a.cislo} (H = {_f(a.z)}) → {b.cislo} (H = {_f(b.z)}), délka {_f(sum_d)} m",
             f"výškový uzávěr {uzaver * 1000:.0f} mm", "",
             f"  {'bod':<18} {'Δh tam':>9} {'Δh zpět':>9} {'rozdíl':>8} {'délka':>9} {'oprava':>8} {'H':>9}"]
    vys, hcur = {}, a.z
    for c, dh, d, mer in oddily:
        opr = uzaver * d / sum_d if sum_d else 0.0
        hcur += dh + opr
        tam = f"{mer[0]:9.3f}" if len(mer) > 0 else " " * 9
        zpet = f"{mer[1]:9.3f}" if len(mer) > 1 else " " * 9
        roz = f"{(mer[0] - mer[1]) * 1000:6.0f}mm" if len(mer) > 1 else " " * 8
        prot.append(f"  {c:<18} {tam} {zpet} {roz} {d:9.3f} {opr:8.3f} {hcur:9.3f}")
        if c != b.cislo:
            vys[c] = hcur
    return Vysledek(prot, [], vys, data={"vysky": vys, "uzaver": uzaver})


ULOHY += [
    ("Ortogonální metoda (Groma)", "Ortogonální metoda s identickými body (staničení, kolmice) – klíč transformací.",
     [Pole("identicke", "Identické body (řádek: bod staničení kolmice)", "radky"),
      Pole("nove", "Číslo určovaného bodu", "text"), Pole("st", "Staničení [m]", "m"), Pole("kol", "Kolmice [m]", "m"),
      Pole("mereni", "Další body (řádek: bod staničení kolmice)", "radky")], u_ortogonalni_groma),
    ("Výška stanoviska", "Výška stanoviska z orientací s výškou (délka + zenit, nebo převýšení).",
     [Pole("orientace", "Orientace (řádek: bod délka zenit převýšení výška_signálu)", "radky"),
      Pole("nove", "Stanovisko (číslo)", "text"), Pole("vp", "Výška stroje [m]", "m")], u_vyska_stanoviska),
    ("Vyrovnání na přímku", "Pata kolmice z bodu na přímku a vzdálenost bodu od přímky.",
     [Pole("a", "Počáteční bod přímky"), Pole("b", "Koncový bod přímky"), Pole("p", "Vyrovnávaný bod"),
      Pole("nove", "Číslo výsledného bodu", "text")], u_na_primku),
    ("Vyrovnání na kružnici", "Středový průmět bodu na kružnici danou třemi body.",
     [Pole("k1", "1. bod kružnice"), Pole("k2", "2. bod kružnice"), Pole("k3", "3. bod kružnice"),
      Pole("p", "Vyrovnávaný bod"), Pole("nove", "Číslo výsledného bodu", "text")], u_na_kruznici),
    ("Vyrovnávací přímka", "Přímka MNČ z definičních bodů, vzdálenosti a průměty bodů.",
     [Pole("body", "Body (řádek: bod [1 = definiční / 0])", "radky"),
      Pole("vse", "Vyrovnat i body nepoužité pro určení přímky", "volba", "ano", ("ano", "ne")),
      Pole("predpona", "Předpona čísel průmětů", "text", "P")], u_vyrovnavaci_primka),
    ("Vyrovnávací kružnice", "Kružnice MNČ z definičních bodů (i s pevným poloměrem), střed a průměty.",
     [Pole("body", "Body (řádek: bod [1 = definiční / 0])", "radky"), Pole("r", "Pevný poloměr [m]", "m"),
      Pole("stred", "Číslo středu", "text"),
      Pole("vse", "Vyrovnat i body nepoužité pro určení kružnice", "volba", "ano", ("ano", "ne")),
      Pole("predpona", "Předpona čísel průmětů", "text", "P")], u_vyrovnavaci_kruznice),
    ("Průsečík přímka - směr", "Průsečík orientovaného směru ze stanoviska s přímkou A–B.",
     [Pole("st", "Stanovisko"), Pole("orientace", "Orientace (řádek: bod směr [délka])", "radky"),
      Pole("sm", "Směr [gon]", "gon"), Pole("zenit", "Zenitový úhel [gon]", "gon"), Pole("vp", "Výška stroje [m]", "m"),
      Pole("a", "Bod A přímky"), Pole("b", "Bod B přímky"), Pole("nove", "Číslo bodu", "text")], u_prusecik_smer),
    ("Průsečík přímka - kružnice", "Průsečík přímky (2 body) a kružnice (3 body).",
     [Pole("k1", "1. bod kružnice"), Pole("k2", "2. bod kružnice"), Pole("k3", "3. bod kružnice"),
      Pole("a", "Bod A přímky"), Pole("b", "Bod B přímky"),
      Pole("reseni", "Řešení", "volba", "1", ("1", "2")), Pole("nove", "Číslo bodu", "text")], u_prusecik_kruznice3),
    ("Konstrukční oměrné", "Body obrazce z oměrných (pravé úhly) umístěné transformací na známé body.",
     [Pole("mereni", "Body a oměrné (řádek: bod oměrná, + vpravo / − vlevo)", "radky"),
      Pole("druh", "Transformace", "volba", "shodnostní", ("shodnostní", "podobnostní")),
      Pole("jen_nove", "Ukládat jen nově určené body", "volba", "ano", ("ano", "ne"))], u_konstrukcni),
    ("Trojúhelníková kalkulačka", "Trojúhelník ze tří údajů (strany a úhly v gonech).",
     [Pole("a", "Strana a [m]", "m"), Pole("b", "Strana b [m]", "m"), Pole("c", "Strana c [m]", "m"),
      Pole("alfa", "Úhel α [gon]", "gon"), Pole("beta", "Úhel β [gon]", "gon"), Pole("gama", "Úhel γ [gon]", "gon")],
     u_trojuhelnik),
    ("Polygonový pořad (Groma)", "Polygonový pořad ze směrů a délek zpět / vpřed, typ pořadu se pozná sám.",
     [Pole("a", "Počáteční bod"), Pole("ora", "Orientace na počátečním bodě (řádek: bod směr [délka])", "radky"),
      Pole("b", "Koncový bod"), Pole("orb", "Orientace na koncovém bodě (řádek: bod směr [délka])", "radky"),
      Pole("mereni", "Měřená data (řádek: bod směr_zpět délka_zpět směr_vpřed délka_vpřed)", "radky")],
     u_polygon_groma),
    ("Výškový pořad", "Trigonometrický výškový pořad tam a zpět s rozdělením uzávěru.",
     [Pole("a", "Počáteční bod"), Pole("b", "Koncový bod"),
      Pole("mereni", "Měření (řádek: bod vp d_zpět z_zpět vc_zpět d_vpřed z_vpřed vc_vpřed)", "radky")],
     u_vyskovy_porad),
]
