"""Kontrola výpočtu souřadnic ze zápisníku (polární metoda jako v Gromě)."""

from pathlib import Path

import pytest

from kontrola.checks.seznam import ListPoint, read_point_list, short_numbers
from kontrola.vypocet import compare, compute, krovak_scale, read_zap

P = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"


def test_cisla_bodu():
    assert {"1", "13-1"} <= short_numbers("610844000130001")
    assert "4001" in short_numbers("610844000134001")


def test_meritko_krovak():
    # Groma pro Husovice: 0.9998596552 (−14,0 mm/100 m)
    assert abs(krovak_scale(595980, 1158240, 257.2) - 0.9998596552) < 2e-6


def test_polarni_metoda_jednoduse(tmp_path):
    zap = tmp_path / "z.zap"
    zap.write_text("1 A 1.500 *\nB  100.000 1.500 0.0000 100.0000\n-1\n"
                   "1  10.000 1.500 100.0000 100.0000\n2  20.000 1.000 200.0000 99.0000\n/\n", encoding="cp1250")
    known = [ListPoint("A", 1000.0, 5000.0, 200.0), ListPoint("B", 1000.0, 5100.0, None)]
    res = compute(read_zap(zap), known, koeficient=1.0)
    p1, p2 = res.body
    assert abs(p1.y - 1010.0) < 1e-6 and abs(p1.x - 5000.0) < 1e-6 and abs(p1.z - 200.0) < 1e-4
    assert abs(p2.x - (5000.0 - 20.0 * 0.99987663)) < 1e-4  # z = 99 g → šikmá délka se zkrátí


@pytest.mark.skipif(not (P / "zap_husovice.zap").exists(), reason="podklady nejsou k dispozici")
def test_husovice_jako_groma(tmp_path):
    stations = read_zap(P / "zap_husovice.zap")
    known = read_point_list(P / "dane_body.txt")
    res = compute(stations, known)
    student = read_point_list(P / "Husovice_Včelák_seznam.txt")
    bad, rows = compare(res, student, known=known)
    assert bad == []
    assert max(r.dxy for r in rows if r.dxy is not None) < 0.002
    # chyba ve výpočtu (přehozená číslice) se najde
    student[4] = ListPoint(student[4].cislo, student[4].a + 0.09, student[4].b, student[4].z)
    bad, _ = compare(res, student, known=known)
    assert len(bad) == 1 and "poloha o 0.090" in bad[0].poznamka
