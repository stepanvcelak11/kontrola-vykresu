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


@pytest.mark.skipif(not (UCITEL / "GEO.dgn").exists(), reason="chybí výkres učitele")
def test_pravidla_ze_vzoru_ucitele():
    """Pravidla odvozená z učitelova výkresu a protokolu: kontrola najde jeho chyby, skoro nic navíc."""
    from kontrola.config import Config
    from kontrola.pravidla_ze_vzoru import odvod_pravidla
    from kontrola.protokol_ucitele import compare_with_teacher, read_teacher_log
    from kontrola.runner import run_checks
    d = read_dgn(UCITEL / "GEO.dgn")
    p = read_teacher_log(UCITEL / "GEO.log")
    rs = odvod_pravidla(d, p)
    res = run_checks(d, rs, Config())
    rows, _txt = compare_with_teacher(p, d, rs, res.issues)
    shoda = sum(min(r.ucitel, r.program) for r in rows)
    navic = sum(max(0, r.program - r.ucitel) for r in rows)
    assert shoda >= 15 and navic <= 6  # bez pravidel učitele: shoda 14, navíc přes 1000


HUSOVICE = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"


@pytest.mark.skipif(not (HUSOVICE / "Husovice_Včelák_mapa.dgn").exists(), reason="chybí výkres Husovice")
def test_kurziva_z_dgn_i_dxf():
    """Čísla bodů jsou kurzívou (příznak sklonu v DGN, styl „Arial Narrow IF“ v DXF), výšky ne – kontrola
    řezu písma podle pravidel zadání nehlásí chybu ani u DGN, ani u DXF."""
    from conftest import check

    from kontrola.io import read_dxf
    from kontrola.io.dgn_v8 import read_dgn
    from kontrola.rules import RuleSet, rez_pisma
    rs = RuleSet.load(HUSOVICE / "pravidla_zadani2.yaml")
    for d in (read_dgn(HUSOVICE / "Husovice_Včelák_mapa.dgn"), read_dxf(HUSOVICE / "Husovice_Včelák_mapa.dxf")):
        texty = [f for f in d.features if f.geom_type.name == "TEXT"]
        cisla = [f for f in texty if f.layer == "GS01-body-čísla"]
        vysky = [f for f in texty if "výšky" in f.layer]
        assert cisla and all(rez_pisma(f)[1] for f in cisla)
        assert vysky and not any(rez_pisma(f)[1] for f in vysky)
        assert not [i for i in check(d, "symbologie", rules=rs) if "kurzív" in i.message]
