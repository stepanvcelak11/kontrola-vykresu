"""Výkresy z Kokeše: převody podle Zadání Kokeš (barva 100 = 0, styl −13 = 4, kreslící klíče, texty 1xx)."""

from pathlib import Path

import pytest
from conftest import check

from kontrola import kokes as K
from kontrola.io.dxf_loader import DrawingLoadError, load_drawing
from kontrola.nazev_souboru import zhodnot
from kontrola.rules import Rule, RuleSet

SMERNICE = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "Směrnice-výběr.xls"


def test_prevody():
    assert K.barva_kokes_na_ms(100) == 0 and K.barva_kokes_na_ms("94") == 94 and K.barva_kokes_na_ms("x") is None
    assert K.styl_kokes_na_ms("-13") == "4" and K.styl_kokes_na_ms("2") == "2"
    assert K.klic_v_rozsahu("1-4", 3) and not K.klic_v_rozsahu("1-4", 5)
    assert K.klic_v_rozsahu("20", 20) and K.klic_v_rozsahu("1-4, 9", 9) and K.klic_v_rozsahu(None, 7)
    assert K.barva_textu_z_klice(175) == 75 and K.barva_textu_z_klice(20) is None


def test_klic_prvku():
    class F:
        attributes = {}
        linetype = "KK13"
    assert K.klic_prvku(F()) == 13
    F.linetype = "-13"
    assert K.klic_prvku(F()) == -13
    F.linetype = "CONTINUOUS"
    assert K.klic_prvku(F()) is None
    F.attributes = {"KK": "175"}
    assert K.klic_prvku(F()) == 175


def _pravidla():
    rs = RuleSet(paleta="autocad", program="kokes")
    rs.pravidla = [Rule("BUD", "Budovy zděné", hladina="5", barva=1, styl_cary="0,2,4,7", kreslici_klic="1-4"),
                   Rule("POP", "Popis povrchů", hladina="9", barva=3, geometrie="text")]
    return rs


def test_kresleni_klic_v_kokesi(make_dxf):
    def build(msp, doc):
        for n in ("3", "13", "-13"):
            doc.linetypes.add(n, [0.5, 0.25, -0.25])
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "5", "color": 1, "linetype": "3"})
        msp.add_line((0, 5), (10, 5), dxfattribs={"layer": "5", "color": 1, "linetype": "13"})
    d = make_dxf(build)
    iss = check(d, "symbologie", _pravidla())
    assert len(iss) == 1 and "kreslící klíč 13 (má být 1-4)" in iss[0].message
    # stejný výkres v režimu MicroStation: „3“ a „13“ jsou styly mimo 0,2,4,7
    rs = _pravidla()
    rs.program = "microstation"
    assert len(check(d, "symbologie", rs)) == 2


def test_textovy_klic_a_barva_100(make_dxf):
    def build(msp, doc):
        msp.add_text("ostatní plocha", dxfattribs={"layer": "9", "color": 3, "height": 1}).set_placement((0, 0))
        msp.add_text("zahrada", dxfattribs={"layer": "9", "color": 3, "height": 1}).set_placement((0, 9))
    d = make_dxf(build)
    d.features[0].attributes["KK"] = "103"
    d.features[1].attributes["KK"] = "175"
    iss = check(d, "symbologie", _pravidla())
    assert len(iss) == 1 and "textový klíč 175 = barva 75 (má být klíč 103)" in iss[0].message
    # barva 100 Kokeše = barva 0 MicroStationu (prvek z DGN s číslem barvy)
    rs = RuleSet(program="kokes")
    rs.pravidla = [Rule("X", "Obrys", hladina="5", barva=0)]

    def build2(msp, doc):
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "5"})
    d2 = make_dxf(build2)
    d2.features[0].attributes["MS_BARVA"] = "100"
    assert check(d2, "symbologie", rs) == []
    rs.program = "microstation"
    assert len(check(d2, "symbologie", rs)) == 1


def test_soubory_kokese(tmp_path):
    f = tmp_path / "Vcelak_13_a0_t0.vyk"
    f.write_bytes(b"\x00\x01binarni")
    with pytest.raises(DrawingLoadError, match="export"):
        load_drawing(f)
    h = zhodnot(tmp_path / "Vcelak_13_a0_t0.vyk")
    assert h.ok and h.dalsi_a == "Vcelak_13_a1_t0.vyk"
    assert zhodnot(tmp_path / "Včelák_13_a0_t0.ss").text.endswith("Vcelak_13_a0_t0.ss")


def test_pravidla_s_klicem_yaml(tmp_path):
    rs = _pravidla()
    rs.save(tmp_path / "p.yaml")
    rs2 = RuleSet.load(tmp_path / "p.yaml")
    assert rs2.program == "kokes" and rs2.pravidla[0].kreslici_klic == "1-4"


@pytest.mark.skipif(not SMERNICE.exists(), reason="podklady nejsou k dispozici")
def test_smernice_sloupec_kk():
    from kontrola.importer.table import generate_rules, import_table
    td, hi, m = import_table(SMERNICE)
    r = generate_rules(td.rows, hi, m, str(SMERNICE)).rules.by_code()
    assert r["Budovy zděné, betonové"].kreslici_klic == "1-4" and r["Plot drátěný"].kreslici_klic == "20"


def test_cisla_kn_a_seznam():
    from kontrola.geodezie.body import Bod, SeznamBodu
    assert K.cislo_kn("610844", 13, 1) == "610844000130001" and K.cislo_kn(None, 13, 25) == "000130025"
    assert K.rozloz_cislo("610844000130001") == ("610844", 13, 1) and K.rozloz_cislo("15") == (None, None, 15)
    assert K.rozloz_cislo("A12") is None and K.zkracene("000130025") == "13-25" and K.zkracene("7") == "7"
    with pytest.raises(ValueError):
        K.cislo_kn("12", 13, 1)
    s = SeznamBodu()
    s.body = [Bod("1", 1, 2), Bod("2", 3, 4), Bod("P5", 5, 6)]
    assert K.na_cisla_kn(s, None, 13, ["1"]) == 1 and s.body[0].cislo == "000130001" and s.body[1].cislo == "2"
    s.zpet()
    assert s.body[0].cislo == "1"
    s.body.append(Bod("000130002", 0, 0))
    with pytest.raises(ValueError, match="už v seznamu"):
        K.na_cisla_kn(s, None, 13)
    t = K.seznam_text([Bod("000130001", 743000.123, 1043000.5, 250.0, kvalita=3)])
    assert t.split() == ["000130001", "743000.12", "1043000.50", "250.00", "3"]


def test_tabulky_kokese():
    rs = RuleSet(pravidla=[Rule("A", "Budovy", hladina="5", barva=0, styl_cary="0,2,4,7", kreslici_klic="1-4",
                                tloustka=2),
                           Rule("B", "Popis povrchů", hladina="9", barva=75, geometrie="text", font="CS_WORKING")])
    t = K.tabulky(rs)
    assert [b[:2] for b in t["barvy"]] == [(100, 0), (75, 75)]
    assert t["cary"] == [("1-4", "Budovy", "5", "100", "0,2,-13,7", "2")]
    assert t["texty"] == [(175, 75, "Popis povrchů")] and ("1", "2") in t["fonty"]
    h = K.tabulky_html(rs)
    assert "Tabulka barev" in h and "-13" in h and "175" in h
