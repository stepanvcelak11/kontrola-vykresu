"""Vyrovnání sítě MNČ: přesná síť → přesné souřadnice; se šumem shoda s nezávislou MNČ (numerické derivace)."""

import math
import random

import numpy as np
import pytest

from kontrola.geodezie import vyrovnani as VR

GON = math.pi / 200


def _sm(a, b):
    return math.atan2(b[0] - a[0], b[1] - a[1]) % (2 * math.pi)


def _sit(sum_smer_cc=0.0, sum_d_mm=0.0, seed=1):
    r = random.Random(seed)
    pevne = {"A": (1000.0, 2000.0), "B": (1400.0, 2050.0), "C": (1200.0, 2400.0)}
    pravda = {"P": (1150.0, 2150.0), "Q": (1300.0, 2250.0)}
    vse = {**pevne, **pravda}
    plan = {"A": ["B", "P", "Q", "C"], "B": ["A", "P", "Q"], "P": ["A", "B", "Q", "C"], "Q": ["P", "B", "C"]}
    smery, delky = [], []
    for st, cile in plan.items():
        o = r.uniform(0, 2 * math.pi)  # libovolná orientace limbu
        for c in cile:
            hz = (_sm(vse[st], vse[c]) - o) % (2 * math.pi) + r.gauss(0, sum_smer_cc * VR.CC)
            smery.append(VR.Smer(st, c, hz / GON))
            if c in ("P", "Q") or st in ("P", "Q"):
                d = math.dist(vse[st], vse[c]) + r.gauss(0, sum_d_mm / 1000)
                delky.append(VR.Delka(st, c, d))
    return pevne, pravda, smery, delky


def test_presna_sit_vyjde_presne():
    pevne, pravda, smery, delky = _sit()
    v = VR.vyrovnej(smery, delky, pevne)
    for b, (y, x) in pravda.items():
        assert abs(v.souradnice[b][0] - y) < 1e-6 and abs(v.souradnice[b][1] - x) < 1e-6
    assert v.sigma0 < 1e-3 and v.redundance > 0
    assert all(abs(o) < 1e-3 for _s, o in v.opravy_smeru)


def test_se_sumem_shoda_s_nezavislou_mnc():
    pevne, pravda, smery, delky = _sit(10, 3, seed=7)
    v = VR.vyrovnej(smery, delky, pevne, 10, 3, 0)
    # nezávislá MNČ: Gauss–Newton s numerickými derivacemi, neznámé = souřadnice P, Q + posuny stanovisek
    nove, sts = ["P", "Q"], sorted({s.st for s in smery})
    x = np.array([1100.0, 2100.0, 1350.0, 2300.0] + [0.0] * len(sts))
    w_s, w_d = 1 / (10 * VR.CC), 1 / 0.003

    def body(x):
        b = dict(pevne)
        b.update({"P": (x[0], x[1]), "Q": (x[2], x[3])})
        return b

    for st in sts:  # přibližná orientace
        b = body(x)
        s = next(q for q in smery if q.st == st)
        x[4 + sts.index(st)] = _sm(b[st], b[s.cil]) - s.hz * GON

    def rezidua(x):
        b = body(x)
        out = []
        for s in smery:
            vyp = (_sm(b[s.st], b[s.cil]) - x[4 + sts.index(s.st)]) % (2 * math.pi)
            out.append(((s.hz * GON - vyp + math.pi) % (2 * math.pi) - math.pi) * w_s)
        for d in delky:
            out.append((d.d - math.dist(b[d.st], b[d.cil])) * w_d)
        return np.array(out)

    for _ in range(30):
        f0 = rezidua(x)
        J = np.zeros((len(f0), len(x)))
        for j in range(len(x)):
            h = 1e-6 if j < 4 else 1e-9
            xp = x.copy()
            xp[j] += h
            J[:, j] = (rezidua(xp) - f0) / h
        dx = np.linalg.lstsq(J, f0, rcond=None)[0]  # krok Gauss–Newtona: J·dx = f0
        x = x - dx
        if np.max(np.abs(dx[:4])) < 1e-9:
            break
    assert abs(v.souradnice["P"][0] - x[0]) < 1e-5 and abs(v.souradnice["P"][1] - x[1]) < 1e-5
    assert abs(v.souradnice["Q"][0] - x[2]) < 1e-5 and abs(v.souradnice["Q"][1] - x[3]) < 1e-5
    # výsledek je blízko pravdy (pár mm) a σ0 rozumná
    for b, (y, xx) in pravda.items():
        assert math.dist(v.souradnice[b], (y, xx)) < 0.02
    assert 0.2 < v.sigma0 < 3
    a, bb, _fi = v.elipsy["P"]
    assert a >= bb > 0 and abs(math.hypot(a, bb) - v.stredni_chyby["P"][2]) < 1e-9
    t = "\n".join(VR.protokol(v, 10, 3, 0))
    assert "VYROVNANÉ SOUŘADNICE" in t and "P" in t


def test_nedourcena_sit():
    pevne = {"A": (0.0, 0.0), "B": (100.0, 0.0)}
    with pytest.raises(ValueError):
        VR.vyrovnej([VR.Smer("A", "Z", 0.0)], [], pevne)
