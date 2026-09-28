"""Testy kontrol doplněných podle MGEO (přetažení, krátké linie, rozdělení v uzlu, jeden popis v ploše)."""

from conftest import check

from kontrola.model import GeomType
from kontrola.rules import Rule, RuleSet, TextRule


def test_pretazena_linie(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, 5), (5, -0.015))  # přetaženo o 15 mm (tolerance MGEO 0,020 m)
    d = make_dxf(build)
    issues = check(d, "chybejici_napojeni")
    assert [i.message for i in issues] == ["Přetažená linie o 0,015 m"]
    # přetažený konec se nehlásí jako visící ani jako průsečík bez uzlu
    assert all(round(i.y, 3) != -0.015 for i in check(d, "visici_konce", okraj=0))
    assert check(d, "pruseciky_bez_uzlu") == []


def test_dlouhy_presah_je_zamerny(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, 5), (5, -3))  # přesah 3 m > max. přetažení
    d = make_dxf(build)
    assert check(d, "chybejici_napojeni") == []
    assert [i.message for i in check(d, "pruseciky_bez_uzlu")] == ["Průsečík linií bez uzlu"]


def test_kratka_linie_a_kratky_usek(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (0.02, 0))  # 2 cm
        msp.add_lwpolyline([(0, 5), (10, 5), (10.003, 5), (20, 5)])  # úsek 3 mm
        msp.add_line((0, 10), (10, 10))
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "kratke_linie"))
    assert msgs == ["Krátká linie, délka 0,02 m", "Krátký úsek linie, délka 3 mm"]


def test_vyzadovat_rozdeleni_v_uzlu(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (5, 0), (10, 0)])
        msp.add_lwpolyline([(5, -5), (5, 0), (5, 5)])  # společný lomový bod, ale linie nerozdělené
    d = make_dxf(build)
    assert check(d, "pruseciky_bez_uzlu", vyzadovat_rozdeleni=False) == []
    assert [i.message for i in check(d, "pruseciky_bez_uzlu")] == ["Linie nejsou v uzlu rozdělené"]


def test_t_spojeni_se_delit_nemusi(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (5, 0), (10, 0)])
        msp.add_line((5, 0), (5, 5))  # T-spojení v lomovém bodě
    d = make_dxf(build)
    assert check(d, "pruseciky_bez_uzlu") == []


def test_jeden_popis_nebo_definicni_bod_v_plose(make_dxf):
    rs = RuleSet(pravidla=[Rule(kod="1", nazev="Parcela", geometrie=GeomType.POLYGON, hladina="P",
                                text=TextRule(povinny=True, hladina="DB"))])

    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "P"})
        msp.add_point((5, 5), dxfattribs={"layer": "DB"})  # definiční bod – v pořádku
        msp.add_lwpolyline([(20, 0), (30, 0), (30, 10), (20, 10)], close=True, dxfattribs={"layer": "P"})
        msp.add_point((25, 5), dxfattribs={"layer": "DB"})
        msp.add_point((26, 6), dxfattribs={"layer": "DB"})  # druhý definiční bod
        msp.add_point((50, 5), dxfattribs={"layer": "DB"})  # definiční bod bez plochy
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "texty", rs))
    assert len(msgs) == 2
    assert msgs[0].startswith("Definiční bod") and "mimo polygon" in msgs[0]
    assert msgs[1].startswith("Parcela: více popisů v ploše (2")


def test_tolerance_podle_mgeo_a_prevod_starych_projektu():
    from kontrola.config import Config
    c = Config()
    assert c.tolerance == 0.010
    assert c.settings("chybejici_napojeni").parametry["max_pretazeni"] == 0.020
    assert c.settings("kratke_linie").parametry["min_delka"] == 0.090
    assert c.settings("pruseciky_bez_uzlu").parametry["napojeni_bez_uzlu"] is False
    old = Config.from_dict({"nastaveni": {"tolerance": 0.05},
                            "kontroly": {"chybejici_napojeni": {"max_pretazeni": 0.5},
                                         "kratke_linie": {"min_delka": 0.05, "zavaznost": "varování"}}})
    assert old.tolerance == 0.010
    assert old.settings("chybejici_napojeni").parametry["max_pretazeni"] == 0.020
    assert old.settings("kratke_linie").parametry["min_delka"] == 0.090


def test_kratka_cara_mgeo(make_dxf):
    d = make_dxf(lambda msp, doc: (msp.add_line((0, 0), (0.08, 0)), msp.add_line((5, 0), (5.1, 0))))
    assert [i.message.split(",")[0] for i in check(d, "kratke_linie")] == ["Krátká linie"]


def test_meritko_stylu_a_bunky(make_dxf):
    from kontrola.rules import Rule, RuleSet
    rs = RuleSet(pravidla=[Rule(kod="plot", hladina="7", styl_cary="2.103", meritko_stylu=0.5),
                           Rule(kod="strom", blok="3.13", meritko_bunky=1.0)])

    def build(msp, doc):
        doc.linetypes.add("2.103", pattern=[0.2, 0.1, -0.1])
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "7", "linetype": "2.103", "ltscale": 0.5})
        msp.add_line((0, 1), (5, 1), dxfattribs={"layer": "7", "linetype": "2.103", "ltscale": 1.0})
        doc.blocks.new("3.13_1").add_circle((0, 0), 0.5)
        msp.add_blockref("3.13_1", (9, 9), dxfattribs={"layer": "3", "xscale": 2, "yscale": 2})
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "symbologie", rs))
    assert msgs == ["Buňka (pravidlo „strom“): měřítko buňky 2 (má být 1)",
                    "Úsečka (pravidlo „plot“): měřítko stylu 1 (má být 0,5)"]


def test_uzivatelsky_styl_neulozeny_do_dxf_je_varovani(make_dxf):
    from kontrola.checks.base import Severity
    from kontrola.rules import Rule, RuleSet
    rs = RuleSet(pravidla=[Rule(kod="Zábradlí", hladina="9", styl_cary="5.303", meritko_stylu=0.5)])
    d = make_dxf(lambda msp, doc: msp.add_line((0, 0), (5, 0), dxfattribs={
        "layer": "9", "linetype": "Continuous", "ltscale": 0.5}))
    (iss,) = check(d, "symbologie", rs)
    assert iss.severity == Severity.VAROVANI and "neuložil" in iss.message and "odpovídá" in iss.message


def test_rozpracovany_vykres(make_dxf):
    from kontrola.config import Config
    from kontrola.runner import run_checks

    def build(msp, doc):
        msp.add_lwpolyline([(-10, -10), (40, -10), (40, 30), (-10, 30)], close=True)  # rám mapy
        msp.add_line((0, 0), (10, 0))
        msp.add_line((10, 0), (10, 7))  # kresba ještě nepokračuje – volné konce uvnitř mapy
        msp.add_line((20, 0), (20, 0.08))  # krátká čára – chyba i v rozpracovaném výkresu
    d = make_dxf(build)
    full = run_checks(d, RuleSet(), Config())
    wip_cfg = Config()
    wip_cfg.rozpracovany = True
    wip = run_checks(d, RuleSet(), wip_cfg)
    ids = lambda r: {i.check_id for i in r.issues}  # noqa: E731
    assert "visici_konce" in ids(full) and "visici_konce" not in ids(wip)
    assert "kratke_linie" in ids(wip)
    assert any("Rozpracovaný" in n for n in wip.notes)
    assert Config.from_dict(wip_cfg.to_dict()).rozpracovany is True
