"""Model terénu: TIN, vrstevnice a kubatury."""

import math

import pytest

from kontrola.geodezie import teren as T


def _rovina(n=6):
    # nakloněná rovina z = 100 + 0.5·x na mřížce 0..50 m
    return [(i * 10.0, j * 10.0, 100 + 0.5 * i * 10.0) for i in range(n) for j in range(n)]


def test_tin_a_vyska():
    t = T.tin(_rovina())
    assert len(t.trojuhelniky) == 50 and abs(t.plocha() - 2500) < 1e-6
    assert abs(t.vyska_v(12.5, 33.0) - 106.25) < 1e-9 and t.vyska_v(-5, 0) is None
    with pytest.raises(ValueError):
        T.tin([(0, 0, 1), (1, 1, 2)])
    assert T.tin(_rovina() + [(0, 0, None), (0.0001, 0, 5)]).vynechane == 2


def test_vrstevnice_na_rovine():
    v = T.vrstevnice(T.tin(_rovina()), interval=5.0, zesilena_kazda=2)
    zs = sorted({c.z for c in v})
    assert {105.0, 110.0, 115.0, 120.0} <= set(zs) and set(zs) <= {100.0, 105.0, 110.0, 115.0, 120.0, 125.0}  # úroveň přesně na okraji sítě je hraniční případ
    for c in v:  # vrstevnice roviny jsou přímky x = (z − 100) / 0.5, vždy jedna souvislá čára přes celou šířku
        assert all(abs(p[0] - (c.z - 100) / 0.5) < 1e-6 for p in c.body)
    assert len([c for c in v if c.z == 105.0]) == 1
    assert {c.z for c in v if c.zesilena} >= {110.0, 120.0} and 105.0 not in {c.z for c in v if c.zesilena}


def test_uzavrena_vrstevnice_kupy_a_vyhlazeni():
    body = [(math.cos(a / 8 * math.tau) * r, math.sin(a / 8 * math.tau) * r, 10 - r / 10)
            for r in (10, 20, 30) for a in range(8)] + [(0, 0, 10)]
    t = T.tin(body)
    v = [c for c in T.vrstevnice(t, 0.5) if c.z == 8.5]
    assert len(v) == 1 and v[0].uzavrena
    h = T.vrstevnice(t, 0.5, vyhladit=2)
    assert len(next(c for c in h if c.z == 8.5).body) > len(v[0].body)


def test_max_strana_a_kubatura():
    body = _rovina() + [(500.0, 0.0, 100.0)]
    assert len(T.tin(body, max_strana=20).trojuhelniky) == 50
    t = T.tin([(0, 0, 0), (10, 0, 0), (0, 10, 0), (10, 10, 0)])
    assert T.kubatura(t, -2) == pytest.approx((200.0, 0.0))
    t = T.tin(_rovina())  # z 100..125, plocha 2500: průměr 112.5 → nad 110 = …
    nad, pod = T.kubatura(t, 110.0)
    # z = 100 + 0.5x; nad 110 pro x > 20: ∫(0.5x−10) dx od 20 do 50 × 50 = 50·(0.25·(2500−400) − 10·30) = 11250
    assert nad == pytest.approx(11250.0) and pod == pytest.approx(50 * 100.0)


def test_uloha_model_terenu():
    from kontrola.geodezie.body import Bod, SeznamBodu
    from kontrola.geodezie.ulohy import ULOHY, ChybaVstupu
    fn = next(f for n, _p, _pole, f in ULOHY if n == "Model terénu a kubatura")
    s = SeznamBodu([Bod(f"{i}{j}", i * 10.0, j * 10.0, 100 + 0.5 * i * 10.0) for i in range(6) for j in range(6)])
    s.body.append(Bod("bez", 3.0, 3.0))
    v = fn(s, {"interval": "5", "zref": "110"})
    t = "\n".join(v.protokol)
    assert "trojúhelníků TIN: 50" in t and "11250.00 m³" in t and "5000.00 m³" in t
    with pytest.raises(ChybaVstupu):
        fn(s, {"body": "bez 00"})
