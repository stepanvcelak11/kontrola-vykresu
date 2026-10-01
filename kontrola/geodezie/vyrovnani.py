"""Vyrovnání polohové sítě metodou nejmenších čtverců (zprostředkující měření) – jako „Vyrovnání sítě“ v Gromě.

Měření: osnovy vodorovných směrů (každé stanovisko má neznámý orientační posun) a vodorovné délky.
Pevné body ze seznamu souřadnic, ostatní body (i stanoviska) jsou neznámé. Váhy z apriorních středních
chyb (směr v cc, délka a + b·ppm). Výstup: vyrovnané souřadnice, střední chyby my, mx, mp, elipsy chyb,
opravy měření, jednotková střední chyba a posteriori σ0.

Konvence jako v Gromě: Y, X kladné (S-JTSK), směrník od +X po směru hodin v gonech.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

GON = math.pi / 200.0
CC = GON / 10000.0  # 1 cc v radiánech


@dataclass
class Smer:
    st: str
    cil: str
    hz: float  # gon


@dataclass
class Delka:
    st: str
    cil: str
    d: float  # vodorovná délka v zobrazení [m]


@dataclass
class VysledekVyrovnani:
    souradnice: dict[str, tuple[float, float]]
    stredni_chyby: dict[str, tuple[float, float, float]]  # my, mx, mp [m]
    elipsy: dict[str, tuple[float, float, float]]  # a, b [m], směrník hlavní poloosy [gon]
    posuny: dict[str, float]  # orientační posuny stanovisek [gon]
    opravy_smeru: list[tuple[Smer, float]]  # oprava [cc]
    opravy_delek: list[tuple[Delka, float]]  # oprava [m]
    sigma0: float
    redundance: int
    iterace: int
    zpravy: list[str] = field(default_factory=list)


def _smernik(a, b) -> float:
    return math.atan2(b[0] - a[0], b[1] - a[1]) % (2 * math.pi)


def priblizne(smery: list[Smer], delky: list[Delka], pevne: dict[str, tuple[float, float]]) -> dict:
    """Přibližné souřadnice nových bodů postupným rajónem (orientace z pevných / už určených bodů)."""
    zname = dict(pevne)
    dl = {}
    for d in delky:
        dl.setdefault((d.st, d.cil), []).append(d.d)
        dl.setdefault((d.cil, d.st), []).append(d.d)
    po_st: dict[str, list[Smer]] = {}
    for s in smery:
        po_st.setdefault(s.st, []).append(s)
    for _ in range(len(smery) + 2):
        zmena = False
        for st, osnova in po_st.items():
            if st not in zname:
                continue
            orient = [(_smernik(zname[st], zname[s.cil]) - s.hz * GON) for s in osnova if s.cil in zname
                      and s.cil != st]
            if not orient:
                continue
            # průměr úhlů přes jednotkové vektory (kolem 0/2π)
            o = math.atan2(sum(math.sin(v) for v in orient), sum(math.cos(v) for v in orient))
            for s in osnova:
                if s.cil in zname or (st, s.cil) not in dl:
                    continue
                d = float(np.mean(dl[(st, s.cil)]))
                t = s.hz * GON + o
                zname[s.cil] = (zname[st][0] + d * math.sin(t), zname[st][1] + d * math.cos(t))
                zmena = True
        if not zmena:
            break
    return {k: v for k, v in zname.items() if k not in pevne}


def vyrovnej(smery: list[Smer], delky: list[Delka], pevne: dict[str, tuple[float, float]],
             sigma_smer_cc: float = 10.0, sigma_delka_mm: float = 3.0, sigma_delka_ppm: float = 2.0,
             pribl: dict[str, tuple[float, float]] | None = None, max_iter: int = 20) -> VysledekVyrovnani:
    body_v_mereni = {s.st for s in smery} | {s.cil for s in smery} | {d.st for d in delky} | {d.cil for d in delky}
    nove = sorted(body_v_mereni - set(pevne))
    xy = dict(pevne)
    xy.update(priblizne(smery, delky, pevne))
    if pribl:
        xy.update({k: v for k, v in pribl.items() if k in nove})
    chybi = [b for b in nove if b not in xy]
    if chybi:
        raise ValueError("Pro body " + ", ".join(chybi[:10]) + " nejde určit přibližné souřadnice – chybí "
                         "orientace nebo délka (doplňte měření nebo přibližné souřadnice).")
    stanoviska = sorted({s.st for s in smery})
    ix = {b: i for i, b in enumerate(nove)}
    n_xy = 2 * len(nove)
    io = {st: n_xy + i for i, st in enumerate(stanoviska)}
    n = n_xy + len(stanoviska)
    m = len(smery) + len(delky)
    if m < n:
        raise ValueError(f"Málo měření: {m} měření na {n} neznámých – síť nejde vyrovnat.")
    # orientační posuny – přibližně
    posun = {}
    for st in stanoviska:
        v = [(_smernik(xy[st], xy[s.cil]) - s.hz * GON) for s in smery if s.st == st]
        posun[st] = math.atan2(sum(math.sin(a) for a in v), sum(math.cos(a) for a in v))
    p_smer = 1.0 / (sigma_smer_cc * CC) ** 2

    def sig_d(d):
        return sigma_delka_mm / 1000.0 + sigma_delka_ppm * 1e-6 * d

    it = 0
    for it in range(1, max_iter + 1):
        A = np.zeros((m, n))
        lv = np.zeros(m)
        P = np.zeros(m)
        r = 0
        for s in smery:
            (ya, xa), (yb, xb) = xy[s.st], xy[s.cil]
            dy, dx = yb - ya, xb - xa
            s2 = dy * dy + dx * dx
            vyp = (math.atan2(dy, dx) - posun[s.st]) % (2 * math.pi)
            mer = s.hz * GON
            lv[r] = (mer - vyp + math.pi) % (2 * math.pi) - math.pi
            # d(atan2(dy,dx))/dY_b = dx/s2, /dX_b = -dy/s2
            if s.cil in ix:
                A[r, 2 * ix[s.cil]] += dx / s2
                A[r, 2 * ix[s.cil] + 1] += -dy / s2
            if s.st in ix:
                A[r, 2 * ix[s.st]] += -dx / s2
                A[r, 2 * ix[s.st] + 1] += dy / s2
            A[r, io[s.st]] = -1.0
            P[r] = p_smer
            r += 1
        for d in delky:
            (ya, xa), (yb, xb) = xy[d.st], xy[d.cil]
            dy, dx = yb - ya, xb - xa
            s = math.hypot(dy, dx)
            lv[r] = d.d - s
            if d.cil in ix:
                A[r, 2 * ix[d.cil]] += dy / s
                A[r, 2 * ix[d.cil] + 1] += dx / s
            if d.st in ix:
                A[r, 2 * ix[d.st]] += -dy / s
                A[r, 2 * ix[d.st] + 1] += -dx / s
            P[r] = 1.0 / sig_d(d.d) ** 2
            r += 1
        N = A.T @ (A * P[:, None])
        u = A.T @ (P * lv)
        try:
            dxv = np.linalg.solve(N, u)
        except np.linalg.LinAlgError:
            raise ValueError("Síť je singulární – některý bod není dostatečně určen (chybí orientace, "
                             "délka nebo pevný bod).") from None
        for b, i in ix.items():
            xy[b] = (xy[b][0] + dxv[2 * i], xy[b][1] + dxv[2 * i + 1])
        for st, i in io.items():
            posun[st] += dxv[i]
        if np.max(np.abs(dxv[:n_xy])) < 1e-7 if n_xy else True:
            break
    v = A @ dxv - lv  # opravy v poslední linearizaci (po malém posledním kroku ≈ konečné)
    red = m - n
    vpv = float(v @ (P * v))
    sigma0 = math.sqrt(vpv / red) if red > 0 else float("nan")
    Q = np.linalg.inv(N)
    s0 = sigma0 if red > 0 else 1.0
    chyby, elipsy = {}, {}
    for b, i in ix.items():
        qyy, qxx, qxy = Q[2 * i, 2 * i], Q[2 * i + 1, 2 * i + 1], Q[2 * i, 2 * i + 1]
        my, mx = s0 * math.sqrt(qyy), s0 * math.sqrt(qxx)
        chyby[b] = (my, mx, math.hypot(my, mx))
        # elipsa: vlastní čísla matice [[qxx, qxy],[qxy, qyy]] v osách (X, Y)
        t = math.sqrt(((qxx - qyy) / 2) ** 2 + qxy ** 2)
        l1, l2 = (qxx + qyy) / 2 + t, (qxx + qyy) / 2 - t
        fi = 0.5 * math.atan2(2 * qxy, qxx - qyy)  # od osy +X k +Y = směrník
        elipsy[b] = (s0 * math.sqrt(max(l1, 0)), s0 * math.sqrt(max(l2, 0)), (fi / GON) % 200)
    opr_s = [(s, float(v[k]) / CC) for k, s in enumerate(smery)]
    opr_d = [(d, float(v[len(smery) + k])) for k, d in enumerate(delky)]
    zpravy = []
    if red > 0 and (sigma0 > 2.0):
        zpravy.append(f"σ0 = {sigma0:.2f} je výrazně větší než 1 – měření jsou horší, než udávají apriorní "
                      "střední chyby, nebo je v měření hrubá chyba (viz největší opravy).")
    return VysledekVyrovnani({b: xy[b] for b in nove}, chyby, elipsy, {k: (v_ / GON) % 400 for k, v_ in posun.items()},
                             opr_s, opr_d, sigma0, red, it, zpravy)


def _klic(s: str):
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def protokol(v: VysledekVyrovnani, sigma_smer_cc: float, sigma_delka_mm: float, sigma_delka_ppm: float) -> list[str]:
    r = ["VYROVNÁNÍ SÍTĚ MNČ", "==================",
         f"apriorní střední chyby: směr {sigma_smer_cc:g} cc, délka {sigma_delka_mm:g} mm + {sigma_delka_ppm:g} ppm",
         f"počet nadbytečných měření {v.redundance}, iterací {v.iterace}, "
         f"jednotková střední chyba a posteriori σ0 = {v.sigma0:.3f}", "",
         "VYROVNANÉ SOUŘADNICE", "Bod                    Y              X        my     mx     mp   "
         "  a      b    směr a"]
    for b in sorted(v.souradnice, key=_klic):
        y, x = v.souradnice[b]
        my, mx, mp = v.stredni_chyby[b]
        a, bb, fi = v.elipsy[b]
        r.append(f"{b:<16}{y:>15.3f}{x:>15.3f}{my * 1000:>7.1f}{mx * 1000:>7.1f}{mp * 1000:>7.1f}"
                 f"{a * 1000:>7.1f}{bb * 1000:>7.1f}{fi:>9.2f}")
    r += ["(střední chyby a poloosy elips v mm)", "", "ORIENTAČNÍ POSUNY", ]
    r += [f"  {st:<16}{o:>12.4f} g" for st, o in sorted(v.posuny.items())]
    r += ["", "OPRAVY SMĚRŮ [cc]"]
    r += [f"  {s.st:<12} → {s.cil:<14} {o:>9.1f}" for s, o in v.opravy_smeru]
    r += ["", "OPRAVY DÉLEK [mm]"]
    r += [f"  {d.st:<12} → {d.cil:<14} {o * 1000:>9.1f}" for d, o in v.opravy_delek]
    if v.zpravy:
        r += ["", *("UPOZORNĚNÍ: " + z for z in v.zpravy)]
    return r
