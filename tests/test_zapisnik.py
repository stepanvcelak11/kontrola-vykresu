"""Zápisník: načtení, zápis .zap tam a zpět a výpočet stejný jako ze souboru."""

from pathlib import Path

import pytest

from kontrola.checks.seznam import read_point_list
from kontrola.geodezie import zapisnik as Z
from kontrola.vypocet import compute, read_zap

P = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"


def test_zap_tam_a_zpet_stejny_vypocet(tmp_path):
    if not (P / "zap_husovice.zap").exists():
        pytest.skip("chybí podklady")
    raw = Z.nacti(P / "zap_husovice.zap")
    assert sum(len(s.orient) + len(s.detail) for s in raw) > sum(
        len(s.orient) + len(s.detail) for s in read_zap(P / "zap_husovice.zap"))  # obě polohy zvlášť
    f = tmp_path / "upraveny.zap"
    f.write_text(Z.zapis_zap(raw, "HUSOVICE"), encoding="cp1250")
    dane = read_point_list(P / "dane_body.txt")
    a = compute(read_zap(P / "zap_husovice.zap"), dane)
    b = compute(Z.pro_vypocet(Z.nacti(f)), dane)
    pa, pb = {p.bod: p for p in a.body}, {p.bod: p for p in b.body}
    assert set(pa) == set(pb)
    for k in pa:
        assert abs(pa[k].y - pb[k].y) < 2e-4 and abs(pa[k].x - pb[k].x) < 2e-4, k
    assert Z.zkontroluj(raw) == []


def test_kontrola_chyb_zapisniku():
    from kontrola.vypocet import Obs, Station
    st = Station("1", 5.0)
    st.detail.append(Obs("2", -1, 1.5, 450, 100))
    msgs = Z.zkontroluj([st])
    assert any("orientace" in m for m in msgs) and any("výška přístroje" in m for m in msgs)
    assert any("kladná" in m for m in msgs) and any("0–400" in m for m in msgs)
