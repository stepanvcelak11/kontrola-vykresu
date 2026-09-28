"""Testy kontrol doplněných podle MGEO (přetažení, krátké linie, rozdělení v uzlu, jeden popis v ploše)."""

from conftest import check

from kontrola.model import GeomType
from kontrola.rules import Rule, RuleSet, TextRule


def test_pretazena_linie(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, 5), (5, -0.2))  # přetaženo o 20 cm přes vodorovnou linii
    d = make_dxf(build)
    issues = check(d, "chybejici_napojeni")
    assert [i.message for i in issues] == ["Přetažená linie o 0,2 m"]
    # přetažený konec se nehlásí jako visící ani jako průsečík bez uzlu
    assert all(round(i.y, 1) != -0.2 for i in check(d, "visici_konce", okraj=0))
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
    assert msgs == ["Krátká linie, délka 0,02 m", "Krátký úsek linie, délka 0,003 m"]


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
