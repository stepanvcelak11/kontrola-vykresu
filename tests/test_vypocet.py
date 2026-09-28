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


def test_diagnoza_typickych_chyb():
    import math
    from pathlib import Path

    from kontrola.checks.seznam import ListPoint, read_point_list
    from kontrola.vypocet import GON, compare, compute, diagnose, read_zap
    Z = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"
    st = read_zap(Z / "zap_husovice.zap")
    known = read_point_list(Z / "dane_body.txt") + read_point_list(Z / "gnss_husovice.txt")
    r = compute(st, known)
    assert r.kontroly and all(k.ok for k in r.kontroly if k.druh != "Kontrolní určení")
    base = [b for b in r.body if not b.kontrolni]
    # pootočení kolem stanoviska 4001
    rot = []
    for b in base:
        sp, a = r.stanoviska[b.stanovisko], (0.05 * GON if b.stanovisko == "4001" else 0.0)
        rot.append(ListPoint(b.bod, sp.y + (b.y - sp.y) * math.cos(a) + (b.x - sp.x) * math.sin(a),
                             sp.x - (b.y - sp.y) * math.sin(a) + (b.x - sp.x) * math.cos(a), b.z))
    d = diagnose(r, compare(r, rot, known=known)[1])
    assert len(d) == 1 and "4001" in d[0] and "pootočené" in d[0]
    # výšky o 10 cm
    d = diagnose(r, compare(r, [ListPoint(b.bod, b.y, b.x, b.z + 0.1) for b in base], known=known)[1])
    assert d and all("výšky" in x for x in d)
    # prohozená čísla
    p = [ListPoint(b.bod, b.y, b.x, b.z) for b in base]
    p[3].a, p[4].a, p[3].b, p[4].b = p[4].a, p[3].a, p[4].b, p[3].b
    d = diagnose(r, compare(r, p, known=known)[1])
    assert any("prohozená" in x for x in d)
    # správný seznam → žádná diagnóza
    assert diagnose(r, compare(r, read_point_list(Z / "Husovice_Včelák_seznam.txt"), known=known)[1]) == []
