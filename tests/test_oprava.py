"""Testy automatické opravy (režim „oprava“ jako v MGEO)."""

import pytest
from conftest import check

from kontrola.config import Config
from kontrola.io import read_dxf
from kontrola.repair import RepairOptions, repair_drawing


def test_oprava_topologie(make_dxf, tmp_path):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (20, 0)])  # hlavní linie
        msp.add_line((5, 5), (5, 0.008))  # nedotažená o 8 mm
        msp.add_lwpolyline([(15, 5), (15, -0.015)])  # přetažená o 15 mm
        msp.add_line((0, 10), (10, 10))
        msp.add_line((0, 10), (10, 10))  # duplicita
        msp.add_line((3, 3), (3, 3))  # nulová délka
        msp.add_lwpolyline([(30, 0), (40, 0), (40, 10), (30, 10), (30, 0.005)])  # téměř uzavřený
    d = make_dxf(build, name="vstup.dxf")
    assert check(d, "chybejici_napojeni") and check(d, "duplicity") and check(d, "nulova_delka")
    out = tmp_path / "opraveno.dxf"
    rep = repair_drawing(d, None, Config(), out)
    assert rep.counts["Dotažené linie"] == 1
    assert rep.counts["Zkrácené přetažené linie"] == 1
    assert rep.counts["Smazané duplicity"] == 1
    assert rep.counts["Smazané linie nulové délky"] == 1
    assert rep.counts["Uzavřené polygony"] == 1
    assert "Vložené uzly" not in rep.counts  # T-napojení učitel (MGEO) nevyžaduje rozdělit

    d2 = read_dxf(out)
    assert check(d2, "chybejici_napojeni") == []
    assert check(d2, "duplicity") == []
    assert check(d2, "nulova_delka") == []
    assert check(d2, "pruseciky_bez_uzlu") == []  # uzly vloženy do hlavní linie
    assert check(d2, "nezavrene_polygony") == []
    assert sum(1 for f in d2.features if f.closed) == 1
    assert check(d2, "kratke_linie") == []
    # když je v nastavení zapnuté hlášení T-napojení, oprava uzly vloží
    cfg = Config()
    cfg.settings("pruseciky_bez_uzlu").parametry["napojeni_bez_uzlu"] = True
    rep = repair_drawing(d, None, cfg, tmp_path / "opraveno2.dxf")
    assert rep.counts["Vložené uzly"] == 2


def test_oprava_nevytvori_kratky_usek(make_dxf, tmp_path):
    """Křížení 5 cm od lomového bodu: rozdělení by vytvořilo krátkou čáru – nechá se k ruční opravě."""
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)])
        msp.add_line((9.95, -5), (9.95, 5))
    d = make_dxf(build, name="vstup.dxf")
    rep = repair_drawing(d, None, Config(), tmp_path / "o.dxf")
    assert any("kratší" in s for s in rep.skipped)
    assert check(read_dxf(tmp_path / "o.dxf"), "kratke_linie") == []


def test_oprava_jen_vybrane_a_nikdy_do_originalu(make_dxf, tmp_path):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, 5), (5, 0.008))
    d = make_dxf(build, name="vstup.dxf")
    with pytest.raises(ValueError):
        repair_drawing(d, None, Config(), d.path)
    rep = repair_drawing(d, None, Config(), tmp_path / "o.dxf",
                         RepairOptions(duplicity=False, nedotazeni=True))
    assert "Smazané duplicity" not in rep.counts
    assert rep.counts["Dotažené linie"] == 1
