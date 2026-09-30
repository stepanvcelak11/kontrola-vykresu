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
    issues = check(d, "visici_konce", okraj=0)
    pts = sorted((round(i.x), round(i.y)) for i in issues)
    assert pts == [(0, 0), (10, 10), (20, 0), (30, 0)]


def test_chybejici_napojeni_v_toleranci(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, 0.008), (5, 10))  # nedotaženo o 8 mm (tolerance MGEO 0,010 m)
        msp.add_line((8, 0), (8, -10))  # přesně napojeno
    d = make_dxf(build)
    issues = check(d, "chybejici_napojeni")
    assert len(issues) == 1
    assert issues[0].message == "Nedotažená linie, chybí 8 mm"
    assert (round(issues[0].x, 2), round(issues[0].y, 2)) == (5.0, 0.01)


def test_napojeni_mimo_toleranci_neni_chybejici(make_dxf):
    d = make_dxf(lambda msp, doc: (msp.add_line((0, 0), (10, 0)), msp.add_line((5, 0.5), (5, 10))))
    assert check(d, "chybejici_napojeni") == []
    assert len(check(d, "visici_konce", okraj=0)) == 4


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


def test_visici_konce_na_okraji_vykresu_se_nehlasi(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)  # hranice území
        msp.add_line((50, 100), (50, 60))  # plot od okraje dovnitř – konec uvnitř visí
        msp.add_line((100.5, 50), (80, 50))  # konec 0,5 m od okraje
    d = make_dxf(build)
    from kontrola.checks.base import Severity
    issues = check(d, "visici_konce")
    pts = sorted((round(i.x), round(i.y)) for i in issues if i.severity != Severity.INFO)
    assert pts == [(50, 60), (80, 50)]
    # konec u okraje se ukáže jen jako info s vysvětlením, aby bylo jasné, proč se nepočítá
    edge = [i for i in issues if i.severity == Severity.INFO]
    assert [(round(i.x, 1), round(i.y)) for i in edge] == [(100.5, 50)] and "okraji" in edge[0].message


def test_konec_vedouci_ven_z_roztrepene_kresby_je_okraj(make_dxf):
    """Kresba ve tvaru L: konec v „zálivu“, za kterým už nic není, je okraj (info), ne chyba."""
    from kontrola.checks.base import Severity

    def build(msp, doc):
        msp.add_line((0, 0), (100, 0))
        msp.add_line((0, 0), (0, 100))
        msp.add_line((0, 50), (60, 50))  # vede do prázdna → okraj zaměřeného území
        msp.add_line((30, 30), (30, 49.7))  # končí 0,3 m před čárou → opravdu nedotažená
    d = make_dxf(build)
    issues = check(d, "visici_konce", okraj=1.0)
    by_pt = {(round(i.x), round(i.y)): i for i in issues}
    assert by_pt[(60, 50)].severity == Severity.INFO
    inner = by_pt[(30, 50)]
    assert inner.severity != Severity.INFO and "0,3 m daleko" in inner.message


def test_blizke_prvky_a_kontrola_ploch(make_dxf):
    from kontrola.config import Config
    from kontrola.rules import RuleSet
    from kontrola.runner import run_checks

    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0)], dxfattribs={"layer": "HRANICE"})
        msp.add_lwpolyline([(0, 5), (5, 0.004), (10, 5)], dxfattribs={"layer": "PLOT"})  # vrchol 4 mm od čáry
        msp.add_lwpolyline([(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)], dxfattribs={"layer": "HRANICE"})
        msp.add_lwpolyline([(40, 0), (50, 0), (50, 10), (40, 10), (40, 0)], dxfattribs={"layer": "HRANICE"})
        msp.add_text("12", dxfattribs={"layer": "POPIS-PARCEL", "insert": (25, 5), "height": 1})
    d = make_dxf(build)
    iss = check(d, "blizke_prvky")
    assert len(iss) == 1 and "4 mm" in iss[0].message
    cfg = Config()
    cfg.ensure_defaults()
    assert not cfg.settings("kontrola_ploch").zapnuto  # ve výchozím stavu vypnutá
    cfg.settings("kontrola_ploch").zapnuto = True
    cfg.settings("kontrola_ploch").parametry.update(vrstvy_hranic="HRANICE", vrstvy_popisu="POPIS-PARCEL")
    res = run_checks(d, RuleSet(), cfg, only=["kontrola_ploch"])
    assert [i.message for i in res.issues] == ["Plocha 100 m² nemá popis ani definiční bod"]
