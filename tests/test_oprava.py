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
  # uzly vloženy do hlavní linie
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


def test_oprava_novych_chyb(make_dxf, tmp_path):
    """Zbytečné lomové body, bod těsně u čáry, zdvojené body a vrstva mimo Směrnici."""
    from kontrola.model import GeomType
    from kontrola.rules import Rule, RuleSet

    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (5, 0), (5.03, 0), (10, 0)], dxfattribs={"layer": "PLOT"})  # 3 cm úsek
        msp.add_lwpolyline([(20, 0), (30, 0)], dxfattribs={"layer": "PLOT"})
        msp.add_lwpolyline([(20, 5), (25, 0.005), (30, 5)], dxfattribs={"layer": "PLOT"})  # vrchol 5 mm od čáry
        msp.add_point((40, 40), dxfattribs={"layer": "BODY"})
        msp.add_point((40.003, 40), dxfattribs={"layer": "BODY"})  # zdvojený bod
        for k in range(4):
            msp.add_point((60 + k, 60), dxfattribs={"layer": "58", "color": 5})
    d = make_dxf(build, name="vstup.dxf")
    rs = RuleSet(pravidla=[Rule(kod="P", nazev="Plot", hladina="PLOT"),
                           Rule(kod="B", nazev="Body", hladina="BODY", geometrie=GeomType.BOD),
                           Rule(kod="BP", nazev="Podrobné body", hladina="BODY-POLOHA", geometrie=GeomType.BOD,
                                barva=5)], paleta="autocad")
    out = tmp_path / "o.dxf"
    rep = repair_drawing(d, rs, Config(), out, RepairOptions(presun_vrstvy=True))
    assert rep.counts["Odstraněné zbytečné lomové body"] == 1
    assert rep.counts["Přichycené lomové body"] == 1
    assert rep.counts["Linie rozdělené v uzlu"] == 2
    assert rep.counts["Smazané zdvojené body"] == 1
    assert rep.counts["Přesunuto na vrstvu podle Směrnice"] == 4
    d2 = read_dxf(out)
    assert check(d2, "kratke_linie") == [] and check(d2, "blizke_prvky") == []
    assert check(d2, "pruseciky_bez_uzlu") == []
    assert sum(1 for f in d2.features if f.layer == "BODY-POLOHA") == 4


def test_rozdeleni_v_uzlu(make_dxf, tmp_path):
    """Dvě lomené čáry se kříží ve společném lomovém bodě → obě se v něm rozdělí (MGEO)."""
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (5, 5), (10, 0)], dxfattribs={"layer": "A"})
        msp.add_lwpolyline([(0, 10), (5, 5), (10, 10)], dxfattribs={"layer": "A"})
    d = make_dxf(build, name="uzel.dxf")
    out = tmp_path / "o.dxf"
    assert check(d, "pruseciky_bez_uzlu")
    rep = repair_drawing(d, None, Config(), out)
    assert rep.counts["Linie rozdělené v uzlu"] == 2
    d2 = read_dxf(out)
    assert check(d2, "pruseciky_bez_uzlu") == []
    assert len(d2.features) == 4


def test_oprava_atributu(make_dxf, tmp_path):
    """Automatická oprava atributů: barva, styl, tloušťka, výška a zarovnání textu podle pravidel."""
    from kontrola.model import GeomType
    from kontrola.rules import Rule, RuleSet

    def build(msp, doc):
        doc.linetypes.add("DASHED", pattern=[1.0, 0.6, -0.4])
        msp.add_lwpolyline([(0, 0), (10, 0)], dxfattribs={"layer": "PLOT", "color": 3, "lineweight": 18})
        msp.add_lwpolyline([(0, 5), (10, 5)], dxfattribs={"layer": "PLOT", "color": 1, "linetype": "DASHED",
                                                          "lineweight": 35})  # správně
        msp.add_text("12", dxfattribs={"layer": "POPIS", "height": 1.0, "color": 2}).set_placement((3, 3))
    d = make_dxf(build, name="vstup.dxf")
    rs = RuleSet(pravidla=[Rule(kod="P", nazev="Plot", hladina="PLOT", barva=1, styl_cary="DASHED", tloustka=0.35),
                           Rule(kod="T", nazev="Popis", hladina="POPIS", geometrie=GeomType.TEXT, barva=2,
                                vyska_textu=2.5, zarovnani="střed uprostřed")], paleta="autocad")
    assert RepairOptions().symbologie  # ve výchozím stavu zapnuto
    assert check(d, "symbologie", rules=rs)
    out = tmp_path / "o.dxf"
    rep = repair_drawing(d, rs, Config(), out)
    assert rep.counts["Opravené atributy (symbologie)"] == 2
    d2 = read_dxf(out)
    assert check(d2, "symbologie", rules=rs) == []
    t = next(f for f in d2.features if f.geom_type == GeomType.TEXT)
    assert t.text_height == pytest.approx(2.5) and (t.halign, t.valign) == (1, 2)
    assert t.geometry.distance(__import__("shapely").geometry.Point(3, 3)) < 0.01  # zůstal na místě
