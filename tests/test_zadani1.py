"""Testy podle zadání 1 (MicroStation, Směrnice-výběr.xls, kontrola symbologie jako GISoft/MGEO)."""

from pathlib import Path

import pytest
from conftest import check

from kontrola.importer.table import generate_rules, import_table
from kontrola.model import GeomType
from kontrola.rules import Rule, RuleSet, layer_number

SMERNICE = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "Směrnice-výběr.xls"
PRAVIDLA = SMERNICE.with_name("pravidla_zadani1.yaml")


@pytest.mark.skipif(not SMERNICE.exists(), reason="podklady od učitele nejsou k dispozici")
def test_import_smernice_xls():
    td, hi, m = import_table(SMERNICE)
    assert td.rows[hi][m["hladina"]] == "VR" and td.rows[hi][m["barva"]] == "BA"
    res = generate_rules(td.rows, hi, m, str(SMERNICE))
    assert res.errors == [] and len(res.rules.pravidla) == 49
    r = res.rules.by_code()
    assert r["Budovy zděné, betonové"].hladina == "5" and r["Budovy zděné, betonové"].barva == 94
    assert r["Budovy zděné, betonové"].styl_cary == "0,2,4,7"
    assert r["Budovy zděné, betonové"].typy_prvku == [3, 4, 15, 16]
    assert r["Plot drátěný"].styl_cary == "2.123"  # uživatelský styl má přednost
    assert r["Strom listnatý"].blok == "3.13A" and r["Strom listnatý"].geometrie == GeomType.BOD
    assert r["Název ulice"].vyska_textu == 1.5 and r["Název ulice"].font == "CS_WORKING"
    assert r["Vstup do objektu"].topologie is False


def test_cislo_vrstvy():
    for name in ("Vrstva 7", "Level 7", "LV07", "7", "vrstva_7"):
        assert layer_number(name) == 7
    assert layer_number("BUDOVY") is None
    assert Rule(kod="x", hladina="7").matches_layer("Vrstva 7")
    assert not Rule(kod="x", hladina="7").matches_layer("Vrstva 17")


RS = RuleSet(pravidla=[
    Rule(kod="Budovy", nazev="Budovy", hladina="5", barva=3, styl_cary="0,2,4,7", typy_prvku=[3, 4, 15, 16],
         geometrie=GeomType.LINIE),
    Rule(kod="Body", nazev="Body", hladina="58", barva=0, typy_prvku=[3], geometrie=GeomType.BOD),
    Rule(kod="Čísla", nazev="Čísla bodů", hladina="59", barva=0, typy_prvku=[17], geometrie=GeomType.TEXT,
         vyska_textu=0.75, sirka_textu=0.75, zarovnani="vlevo nahoře"),
])


def test_typ_prvku_a_texty(make_dxf):
    from ezdxf.enums import TextEntityAlignment

    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (5, 0), (5, 5)], dxfattribs={"layer": "Vrstva 5", "color": 1})  # 4 – OK
        msp.add_lwpolyline([(0, 0), (5, 0), (5, 5)], close=True,
                           dxfattribs={"layer": "Vrstva 5", "color": 1})  # tvar – nepovolen
        msp.add_line((1, 1), (1, 1), dxfattribs={"layer": "Vrstva 58", "color": 7})  # bod – OK
        t = msp.add_text("15", dxfattribs={"layer": "Vrstva 59", "color": 7, "height": 0.75})
        t.set_placement((1, 1), align=TextEntityAlignment.TOP_LEFT)
        t2 = msp.add_text("16", dxfattribs={"layer": "Vrstva 59", "color": 7, "height": 1.0, "width": 0.5})
        t2.set_placement((2, 2))
    d = make_dxf(build)
    assert [i.message for i in check(d, "typ_geometrie", RS)] == \
        ["Budovy: typ prvku Tvar (povoleno: Úsečka, Lomená čára, Elipsa, Oblouk)"]
    msgs = [i.message for i in check(d, "symbologie", RS)]
    assert msgs == ["Čísla bodů: výška textu 1 (má být 0,75), šířka textu 0,5 (má být 0,75), "
                    "zarovnání vlevo účaří (má být vlevo nahoře)"]
    assert check(d, "nulova_delka", RS) == []  # úsečka nulové délky na vrstvě bodů je záměr


def test_atribut_dle_vrstvy(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "Vrstva 5"})  # vše BYLAYER
        msp.add_line((0, 1), (5, 1), dxfattribs={"layer": "Vrstva 5", "color": 3, "linetype": "Continuous",
                                                  "lineweight": 0})
    d = make_dxf(build)
    assert [i.message for i in check(d, "atribut_dle_vrstvy", RS)] == \
        ["Atribut dle vrstvy: barva, styl, tloušťka"]


def test_protokol_log(make_dxf, tmp_path):
    from kontrola.config import Config
    from kontrola.export.mgeo_log import export_mgeo_log
    from kontrola.runner import run_checks

    def build(msp, doc):
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "Vrstva 5", "color": 5, "linetype": "Continuous",
                                                  "lineweight": 0})
        msp.add_line((0, 1), (5, 1), dxfattribs={"layer": "Vrstva 15", "color": 3, "linetype": "Continuous",
                                                  "lineweight": 0})
    d = make_dxf(build)
    res = run_checks(d, RS, Config())
    text = export_mgeo_log(d, RS, res.issues, tmp_path / "v.log").read_text(encoding="utf-8-sig")
    assert "Název vrstvy: Vrstva 5, Číslo vrstvy: 5, Typ prvku: Úsečka" in text
    assert "Barva(!): 1" in text  # ACI 5 = modrá = MicroStation 1
    assert "Název vrstvy: Vrstva 15, Číslo vrstvy(!): 15" in text


@pytest.mark.skipif(not PRAVIDLA.exists(), reason="pravidla zadání 1 nejsou k dispozici")
def test_pravidla_zadani1_se_nactou():
    rs = RuleSet.load(PRAVIDLA)
    assert rs.paleta == "microstation" and len(rs.pravidla) == 52
    assert rs.by_code()["Čísla podrobných bodů"].zarovnani == "vlevo nahoře"
