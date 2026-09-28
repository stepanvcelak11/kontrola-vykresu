"""Testy kontrol atributů a konvencí."""

import pytest
from conftest import check

from kontrola.model import GeomType
from kontrola.rules import Rule, RuleSet, TextRule


@pytest.fixture
def pravidla():
    return RuleSet(
        pravidla=[
            # barvy jsou čísla MicroStationu: 3 = červená, 1 = modrá
            Rule(kod="101", nazev="Budova", geometrie=GeomType.POLYGON, hladina="BUDOVY", barva=3,
                 styl_cary="CONTINUOUS", text=TextRule(povinny=True, hladina="POPIS_BUDOV")),
            Rule(kod="301", nazev="Plot", geometrie=GeomType.LINIE, hladina="PLOTY", barva=1, styl_cary="DASHED"),
            Rule(kod="402", nazev="Strom", geometrie=GeomType.BOD, hladina="VEGETACE", blok="STROM",
                 povinne_atributy=["DRUH"], povolene_hodnoty={"DRUH": ["lípa", "dub"]}),
            Rule(kod="501", nazev="Popis budovy", geometrie=GeomType.TEXT, hladina="POPIS_BUDOV"),
        ],
        povolene_hladiny=["RAM"],
    )


def _strom(doc):
    b = doc.blocks.new("STROM")
    b.add_circle((0, 0), 1)
    b.add_attdef("DRUH", (1, 0))


def _budova(msp, pts, **kw):
    return msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "BUDOVY", "color": 1, **kw})


SQ = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_povinne_a_povolene_hodnoty(make_dxf, pravidla):
    def build(msp, doc):
        _strom(doc)
        msp.add_blockref("STROM", (0, 0), dxfattribs={"layer": "VEGETACE"}).add_auto_attribs({"DRUH": "lípa"})
        msp.add_blockref("STROM", (5, 0), dxfattribs={"layer": "VEGETACE"}).add_auto_attribs({"DRUH": "smrk"})
        msp.add_blockref("STROM", (9, 0), dxfattribs={"layer": "VEGETACE"})
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "atributy", pravidla))
    assert msgs == ["Nepovolená hodnota DRUH = „smrk“ (povoleno: lípa, dub)", "Strom: chybí atribut DRUH"]


def test_atribut_z_xdata(make_dxf):
    rs = RuleSet(pravidla=[Rule(kod="1", nazev="Bod", hladina="B", povinne_atributy=["CISLO"])])

    def build(msp, doc):
        doc.appids.add("MGEO")
        p = msp.add_point((0, 0), dxfattribs={"layer": "B"})
        p.set_xdata("MGEO", [(1000, "CISLO=15")])
        msp.add_point((1, 0), dxfattribs={"layer": "B"})
    d = make_dxf(build)
    issues = check(d, "atributy", rs)
    assert len(issues) == 1 and round(issues[0].x) == 1


def test_symbologie(make_dxf, pravidla):
    def build(msp, doc):
        _budova(msp, SQ)
        _budova(msp, [(20, 0), (30, 0), (30, 10), (20, 10)], color=3)
        msp.add_line((0, 20), (10, 20), dxfattribs={"layer": "PLOTY", "color": 5, "linetype": "DASHED"})
        msp.add_line((0, 30), (10, 30), dxfattribs={"layer": "PLOTY", "color": 5})
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "symbologie", pravidla))
    # DXF barva 3 (ACI zelená) odpovídá MicroStation barvě 2
    assert msgs == ["Tvar (pravidlo „Budova“): barva 2 (má být 3)",
                    "Úsečka (pravidlo „Plot“): styl CONTINUOUS (má být DASHED)"]


def test_symbologie_paleta_autocad(make_dxf):
    rs = RuleSet(pravidla=[Rule(kod="1", nazev="Budova", hladina="B", barva=1)], paleta="autocad")

    def build(msp, doc):
        msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "B", "color": 1})
        msp.add_line((0, 1), (1, 1), dxfattribs={"layer": "B", "color": 3})
    d = make_dxf(build)
    assert [i.message for i in check(d, "symbologie", rs)] == ["Úsečka (pravidlo „Budova“): barva 3 (má být 1)"]


def test_symbologie_barevna_tabulka_microstation(make_dxf, tmp_path):
    from kontrola.config import Config
    from kontrola.rules import load_ms_color_table
    from kontrola.runner import run_checks

    rs = RuleSet(pravidla=[Rule(kod="1", nazev="Plot", hladina="P", barva=100)])

    def build(msp, doc):
        msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "P", "true_color": 0x804020})
        msp.add_line((0, 1), (1, 1), dxfattribs={"layer": "P", "true_color": 0x00FF00})
    d = make_dxf(build)
    # bez barevné tabulky nelze barvu 100 ověřit – jen poznámka, žádná chyba
    res = run_checks(d, rs, Config(), only=["symbologie"])
    assert res.issues == [] and any("nelze ověřit" in n for n in res.notes)
    # binární color.tbl: 256 × RGB, barva 100 = #804020
    from kontrola.rules import MICROSTATION_COLORS
    data = bytearray(768)
    for i, rgb in MICROSTATION_COLORS.items():
        data[3 * i:3 * i + 3] = bytes(rgb)
    data[300:303] = bytes((0x80, 0x40, 0x20))
    (tmp_path / "color.tbl").write_bytes(bytes(data))
    rs.barevna_tabulka = load_ms_color_table(tmp_path / "color.tbl")
    assert rs.barevna_tabulka[100] == (0x80, 0x40, 0x20)
    msgs = [i.message for i in check(d, "symbologie", rs)]
    assert msgs == ["Úsečka (pravidlo „Plot“): barva 2 (má být 100)"]
    # textová tabulka a uložení do YAML
    (tmp_path / "barvy.txt").write_text("100 128 64 32\n101;#FF8000\n", encoding="utf-8")
    t = load_ms_color_table(tmp_path / "barvy.txt")
    assert t == {100: (128, 64, 32), 101: (255, 128, 0)}
    rs.save(tmp_path / "p.yaml")
    assert RuleSet.load(tmp_path / "p.yaml").barevna_tabulka[100] == (0x80, 0x40, 0x20)


def test_nepovolene_hladiny_a_nekodovane(make_dxf, pravidla):
    def build(msp, doc):
        msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "POKUS"})
        msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "RAM"})  # povoleno bez kódu
        msp.add_point((3, 3), dxfattribs={"layer": "POPIS_BUDOV"})  # povolená hladina, ale bod nemá pravidlo
    d = make_dxf(build)
    assert [i.message for i in check(d, "nepovolene_hladiny", pravidla)] == ["Vrstva POKUS není ve Směrnici (1 prvek)"]
    assert [i.message for i in check(d, "nekodovane", pravidla)] == ["Nekódovaný bod na vrstvě POPIS_BUDOV"]


def test_texty_chybi_a_mimo(make_dxf, pravidla):
    def build(msp, doc):
        _budova(msp, SQ)
        msp.add_text("č.p. 1", dxfattribs={"layer": "POPIS_BUDOV", "insert": (5, 5)})
        _budova(msp, [(20, 0), (30, 0), (30, 10), (20, 10)])  # bez popisu
        msp.add_text("č.p. 2", dxfattribs={"layer": "POPIS_BUDOV", "insert": (50, 5)})  # mimo
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "texty", pravidla))
    assert msgs == ["Budova: chybí popis uvnitř polygonu (vrstva POPIS_BUDOV)",
                    "Text „č.p. 2“ leží mimo polygon, ke kterému patří"]


def test_typ_geometrie(make_dxf, pravidla):
    def build(msp, doc):
        msp.add_circle((0, 0), 1, dxfattribs={"layer": "BUDOVY"})  # bod místo polygonu
        _budova(msp, SQ)
        msp.add_lwpolyline([(0, 20), (5, 20), (5, 25)], dxfattribs={"layer": "BUDOVY"})  # řeší nezavřené polygony
    d = make_dxf(build)
    assert [i.message for i in check(d, "typ_geometrie", pravidla)] == ["Budova: bod místo polygon"]


def test_jednotnost_hladiny_bez_pravidel(make_dxf):
    def build(msp, doc):
        for i in range(8):
            msp.add_line((0, i), (10, i), dxfattribs={"layer": "PLOTY", "color": 5, "linetype": "DASHED"})
        msp.add_line((0, 20), (10, 20), dxfattribs={"layer": "PLOTY", "color": 1, "linetype": "DASHED"})
        msp.add_line((0, 21), (10, 21), dxfattribs={"layer": "PLOTY", "color": 5})
        for i in range(3):  # malá hladina se nekontroluje
            msp.add_line((0, 30 + i), (10, 30 + i), dxfattribs={"layer": "MALA", "color": i + 1})
    d = make_dxf(build)
    msgs = sorted(i.message for i in check(d, "jednotnost_hladiny"))
    assert msgs == ["Úsečka se liší od ostatních na vrstvě PLOTY: barva 3 (ostatní mají 1)",
                    "Úsečka se liší od ostatních na vrstvě PLOTY: styl CONTINUOUS (ostatní mají DASHED)"]


def test_kontroly_atributu_bez_pravidel_se_preskoci(make_dxf):
    from kontrola.config import Config
    from kontrola.runner import run_checks
    d = make_dxf(lambda msp, doc: msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "X"}))
    res = run_checks(d, RuleSet(), Config(), only=["atributy", "nepovolene_hladiny"])
    assert res.issues == []
    assert len(res.notes) == 2 and all("přeskočeno" in n for n in res.notes)
