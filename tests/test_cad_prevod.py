import ezdxf
import pytest

from kontrola.cad import prevod as PV
from kontrola.cad import upravy as U
from kontrola.cad.zadani import predvolby, priprav_dokument
from kontrola.model import GeomType
from kontrola.rules import Rule, RuleSet


def _rs():
    return RuleSet(paleta="microstation", pravidla=[
        Rule(kod="8.1", nazev="Doplňkové značky", geometrie=GeomType.BOD, hladina="8", barva=1,
             blok="4.110|4.120", meritko_bunky=0.5, typy_prvku=[2]),
        Rule(kod="3.1", nazev="Plot", geometrie=GeomType.LINIE, hladina="3", barva=3, styl_cary="2.093",
             meritko_stylu=0.5),
        Rule(kod="2.1", nazev="Kabel", geometrie=GeomType.LINIE, hladina="2", barva=4, styl_cary="0"),
        Rule(kod="5.1", nazev="Popis kabelu", geometrie=GeomType.TEXT, hladina="5", barva=2, vyska_textu=1.25),
    ])


def _doc():
    doc = ezdxf.new("R2000")
    doc.blocks.new("4.110").add_circle((0, 0), 1)
    doc.linetypes.add("2.093", pattern=[1.0, 0.5, -0.5])
    msp = doc.modelspace()
    msp.add_blockref("4.110", (10, 10), dxfattribs={"layer": "PLYN_ZNACKY", "xscale": 1, "yscale": 1})
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "PLYN_PLOT", "linetype": "2.093"})
    msp.add_line((0, 1), (5, 1), dxfattribs={"layer": "PLYN_POTRUBI"})
    msp.add_line((0, 2), (5, 2), dxfattribs={"layer": "PLYN_POTRUBI"})
    msp.add_text("STL 100", dxfattribs={"layer": "PLYN_POPIS", "height": 2.5})
    return doc


def test_podle_znacky_a_skupiny():
    doc = _doc()
    pv = predvolby(_rs())
    n = PV.navrhni(list(doc.modelspace()), pv)
    assert {(e.dxftype(), p.kod) for e, p in n.prirazeni} == {("INSERT", "8.1"), ("LINE", "3.1")}
    assert [(s.vrstva, s.druh, len(s.prvky)) for s in n.skupiny] == [("PLYN_POTRUBI", "čára", 2),
                                                                      ("PLYN_POPIS", "text", 1)]


def test_proved_jedno_zpet():
    doc = _doc()
    rs = _rs()
    pv = predvolby(rs)
    priprav_dokument(doc, rs)
    msp = doc.modelspace()
    h = U.Historie(msp)
    kab = next(p for p in pv if p.kod == "2.1")
    pop = next(p for p in pv if p.kod == "5.1")
    n = PV.navrhni(list(msp), pv, {("PLYN_POTRUBI", "čára", "BYLAYER"): kab, ("PLYN_POPIS", "text", ""): pop})
    assert not n.skupiny
    nove, stare = PV.proved(doc, msp, h, n, meritko=0.5)
    assert len(nove) == len(stare) == 5
    ins = msp.query("INSERT")[0]
    assert ins.dxf.layer == "8" and ins.dxf.xscale == pytest.approx(0.5)
    plot = [e for e in msp.query("LINE") if e.dxf.linetype == "2.093"][0]
    assert plot.dxf.layer == "3" and plot.dxf.ltscale == pytest.approx(0.5)
    assert {e.dxf.layer for e in msp.query("LINE") if e.dxf.linetype != "2.093"} == {"2"}
    t = msp.query("TEXT")[0]
    assert t.dxf.layer == "5" and t.dxf.height == pytest.approx(1.25)
    h.krok_zpet()
    assert sorted(e.dxf.layer for e in msp) == ["PLYN_PLOT", "PLYN_POPIS", "PLYN_POTRUBI", "PLYN_POTRUBI",
                                                "PLYN_ZNACKY"]


def test_meritko_kdyz_pravidlo_neurcuje():
    doc = _doc()
    rs = RuleSet(paleta="microstation", pravidla=[
        Rule(kod="8.1", nazev="Značky", geometrie=GeomType.BOD, hladina="8", barva=1, blok="4.110")])
    msp = doc.modelspace()
    n = PV.navrhni(list(msp), predvolby(rs))
    PV.proved(doc, msp, U.Historie(msp), n, meritko=0.5)
    assert msp.query("INSERT")[0].dxf.xscale == pytest.approx(0.5)
