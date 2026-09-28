"""Testy kontrol z kroku 2: nezavřené polygony, visící konce, chybějící napojení, duplicity."""

from conftest import check

from kontrola.model import GeomType
from kontrola.rules import Rule, RuleSet

BUDOVA = RuleSet(pravidla=[Rule(kod="101", nazev="Budova", hladina="BUDOVY", geometrie=GeomType.POLYGON)])


def test_nezavreny_polygon_podle_pravidla(make_dxf):
    d = make_dxf(lambda msp, doc: msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0.03)],
                                                     dxfattribs={"layer": "BUDOVY"}))
    issues = check(d, "nezavrene_polygony", BUDOVA)
    assert len(issues) == 1
    assert issues[0].message == "Nezavřený polygon, mezera 0,03 m"


def test_uzavreny_polygon_je_v_poradku(make_dxf):
    d = make_dxf(lambda msp, doc: msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True,
                                                     dxfattribs={"layer": "BUDOVY"}))
    assert check(d, "nezavrene_polygony", BUDOVA) == []


def test_nezavreny_polygon_bez_pravidla_podle_mezery(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0.2)])  # téměř uzavřená
        msp.add_lwpolyline([(20, 0), (30, 0), (30, 10), (20, 10)])  # „U“ – mezera 10 m
    d = make_dxf(build)
    issues = check(d, "nezavrene_polygony", max_mezera=1.0)
    assert len(issues) == 1
    assert "0,2 m" in issues[0].message


def test_visici_konec(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((10, 0), (10, 10))  # napojeno
        msp.add_line((20, 0), (30, 0))  # samostatná linie → 2 visící konce
    d = make_dxf(build)
    issues = check(d, "visici_konce")
    pts = sorted((round(i.x), round(i.y)) for i in issues)
    assert pts == [(0, 0), (10, 10), (20, 0), (30, 0)]


def test_chybejici_napojeni_v_toleranci(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, 0.03), (5, 10))  # nedotaženo o 3 cm
        msp.add_line((8, 0), (8, -10))  # přesně napojeno
    d = make_dxf(build)
    issues = check(d, "chybejici_napojeni")
    assert len(issues) == 1
    assert issues[0].message == "Chybějící napojení, vzdálenost 0,03 m"
    assert (round(issues[0].x, 2), round(issues[0].y, 2)) == (5.0, 0.03)


def test_napojeni_mimo_toleranci_neni_chybejici(make_dxf):
    d = make_dxf(lambda msp, doc: (msp.add_line((0, 0), (10, 0)), msp.add_line((5, 0.5), (5, 10))))
    assert check(d, "chybejici_napojeni") == []
    assert len(check(d, "visici_konce")) == 4


def test_duplicitni_linie_i_opacny_smer(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((10, 0), (0, 0))
        msp.add_line((0, 5), (10, 5))
    d = make_dxf(build)
    issues = check(d, "duplicity")
    assert len(issues) == 1
    assert issues[0].message == "Duplicitní prvek (2×)"


def test_duplicitni_body_a_ruzne_hladiny(make_dxf):
    def build(msp, doc):
        msp.add_point((1, 1))
        msp.add_point((1, 1))
        msp.add_line((0, 0), (5, 5), dxfattribs={"layer": "A"})
        msp.add_line((0, 0), (5, 5), dxfattribs={"layer": "B"})
    d = make_dxf(build)
    issues = check(d, "duplicity")
    assert [i.message for i in issues] == ["Duplicitní bod (2×)"]
    issues = check(d, "duplicity", stejna_hladina=False)
    assert len(issues) == 2
