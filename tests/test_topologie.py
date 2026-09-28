"""Testy topologických kontrol z kroku 5."""

from conftest import check

from kontrola.rules import RuleSet


def test_samoprotnuti_polygonu(make_dxf):
    d = make_dxf(lambda msp, doc: msp.add_lwpolyline([(0, 0), (10, 10), (10, 0), (0, 10)], close=True))
    issues = check(d, "samoprotnuti")
    assert len(issues) == 1
    assert issues[0].message == "Samoprotnutí polygonu"
    assert (round(issues[0].x, 3), round(issues[0].y, 3)) == (5.0, 5.0)


def test_samoprotnuti_linie_a_jednoducha_linie(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (5, -5)])  # smyčka – kříží první úsek
        msp.add_lwpolyline([(20, 0), (30, 0), (30, 10)])  # v pořádku
    d = make_dxf(build)
    issues = check(d, "samoprotnuti")
    assert [i.message for i in issues] == ["Samoprotnutí linie"]
    assert round(issues[0].y, 3) == 0.0


def test_prusecik_bez_uzlu(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((5, -5), (5, 5))  # kříží bez uzlu
        msp.add_lwpolyline([(20, 0), (25, 0), (30, 0)])
        msp.add_lwpolyline([(25, -5), (25, 0), (25, 5)])  # kříží v uzlu obou linií
    d = make_dxf(build)
    issues = check(d, "pruseciky_bez_uzlu", vyzadovat_rozdeleni=False)
    assert [(i.message, round(i.x), round(i.y)) for i in issues] == [("Průsečík linií bez uzlu", 5, 0)]
    # výchozí (jako MGEO): křížení ve společném lomovém bodě musí být rozdělené
    msgs = sorted(i.message for i in check(d, "pruseciky_bez_uzlu"))
    assert msgs == ["Linie nejsou v uzlu rozdělené", "Průsečík linií bez uzlu"]


def test_napojeni_bez_uzlu_t_spoj(make_dxf):
    def build(msp, doc):
        msp.add_line((0, 0), (10, 0))
        msp.add_line((4, 0), (4, 6))  # končí na linii, ta v bodě 4,0 nemá vrchol
    d = make_dxf(build)
    # MGEO nerozdělené čáry v T-spojení za chybu nepovažuje – hlásí se jen na požádání
    assert check(d, "pruseciky_bez_uzlu") == []
    assert [i.message for i in check(d, "pruseciky_bez_uzlu", napojeni_bez_uzlu=True)] == \
        ["Napojení na linii bez uzlu"]


def test_nulova_delka(make_dxf):
    def build(msp, doc):
        msp.add_line((1, 1), (1, 1))
        msp.add_line((0, 0), (5, 0))
        msp.add_text("", dxfattribs={"insert": (2, 2)})
        msp.add_circle((3, 3), 0.0)
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "nulova_delka"))
    assert msgs == ["Kružnice s nulovým poloměrem", "Linie nulové délky", "Prázdný text"]


def test_prekryv_polygonu(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "P"})
        msp.add_lwpolyline([(9, 0), (20, 0), (20, 10), (9, 10)], close=True, dxfattribs={"layer": "P"})
        # budova uvnitř parcely na jiné hladině – není překryv
        msp.add_lwpolyline([(2, 2), (4, 2), (4, 4), (2, 4)], close=True, dxfattribs={"layer": "B"})
    d = make_dxf(build)
    issues = check(d, "prekryvy_polygonu")
    assert [i.message for i in issues] == ["Překryv polygonů, plocha 10 m²"]
    assert len(check(d, "prekryvy_polygonu", stejna_hladina=False)) == 2


def test_mezera_mezi_polygony(make_dxf):
    def build(msp, doc):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
        msp.add_lwpolyline([(10.02, 0), (20, 0), (20, 10), (10.02, 10)], close=True)  # štěrbina 2 cm
        msp.add_lwpolyline([(0, 10), (20, 10), (20, 20), (0, 20)], close=True)  # přesně navazuje
    d = make_dxf(build)
    issues = check(d, "mezery_polygonu")
    assert len(issues) == 1
    assert issues[0].message == "Mezera mezi polygony, šířka 0,02 m"
    assert round(issues[0].x, 2) == 10.01


def test_mimo_rozsah(make_dxf):
    def build(msp, doc):
        msp.add_point((5, 5))
        msp.add_point((150, 5))
        msp.add_line((90, 5), (110, 5))
    d = make_dxf(build)
    rs = RuleSet(rozsah={"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100})
    msgs = sorted(i.message for i in check(d, "mimo_rozsah", rs))
    assert msgs == ["Prvek mimo rozsah výkresu (50 m od hranice)", "Prvek zasahuje mimo rozsah výkresu"]
    # bez nastaveného rozsahu se kontrola přeskočí
    assert check(d, "mimo_rozsah") == []


def test_mimo_rozsah_sjtsk(make_dxf):
    def build(msp, doc):
        msp.add_point((-743200, -1043500))  # Praha
        msp.add_point((12, 34))  # zapomenutý bod u počátku
    d = make_dxf(build)
    issues = check(d, "mimo_rozsah", RuleSet(rozsah="sjtsk"))
    assert len(issues) == 1 and round(issues[0].x) == 12


def test_body_blizko(make_dxf):
    def build(msp, doc):
        msp.add_point((0, 0))
        msp.add_point((0.004, 0))  # 4 mm
        msp.add_point((5, 5))
        msp.add_point((5, 5))  # totožné – to je duplicita, ne „blízko“
        msp.add_point((9, 9))
        msp.add_point((9.2, 9))  # 20 cm – mimo toleranci
    d = make_dxf(build)
    issues = check(d, "body_blizko")
    assert [i.message for i in issues] == ["Body téměř na sobě, vzdálenost 4 mm"]
