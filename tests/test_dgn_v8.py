"""Čtení DGN V8 na výkresu učitele (cvičení Kontrola atributů) a jeho protokolu GISoft."""

from pathlib import Path

import pytest

from kontrola.io.dgn_v8 import read_dgn
UCITEL = Path(__file__).resolve().parents[1] / "podklady" / "ucitel-geo"


@pytest.mark.skipif(not (UCITEL / "GEO.dgn").exists(), reason="chybí výkres učitele")
def test_ucitel_styly_a_meritko_bunek():
    from collections import Counter
    d = read_dgn(UCITEL / "GEO.dgn")
    styly = {f.linetype for f in d.features}
    assert {"VCHOD", "2.123  PL VP", "4.223 OZ VP"} <= styly  # názvy vlastních stylů i bez čísla
    bunky = Counter((f.block_name, f.scale) for f in d.features if f.dxftype == "INSERT" and f.layer == "Vrstva 27")
    assert bunky[("6.20", (0.5, 0.5))] == 3 and bunky[("3.130", (0.5, 0.5))] == 3  # jako protokol učitele
    assert bunky[("6.20", (1.0, 1.0))] == 40


@pytest.mark.skipif(not (UCITEL / "GEO.log").exists(), reason="chybí protokol učitele")
def test_protokol_ucitele_novy_format():
    from kontrola.protokol_ucitele import read_teacher_log
    p = read_teacher_log(UCITEL / "GEO.log")
    assert p.celkem == 19 and sum(g.pocet for g in p.skupiny) == 19
    assert {(g.vrstva, g.spatne) for g in p.skupiny} >= {("Vrstva 50", frozenset({"vrstva"})),
                                                        ("Vrstva 27", frozenset({"buňka"})),
                                                        ("Vrstva 40", frozenset({"výška", "šířka"}))}
