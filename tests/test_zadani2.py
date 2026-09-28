"""Testy podle zadání 2 (účelová mapa Husovice, „Atributy ÚM.xlsx“) a exportu z MicroStationu do DXF."""

from pathlib import Path

import pytest
from conftest import check

from kontrola.importer.table import generate_rules, import_table, text_units_mm
from kontrola.model import GeomType
from kontrola.rules import (Rule, RuleSet, block_matches, code_in_range, color_matches, font_style,
                            linetype_matches, load_ms_color_table, parse_color, parse_weight, rgb_to_aci)

PODKLADY = Path(__file__).resolve().parents[1] / "podklady"
ATRIBUTY = PODKLADY / "zadani2-husovice" / "Atributy ÚM.xlsx"
COLOR_TBL = PODKLADY / "color.tbl"


@pytest.mark.skipif(not COLOR_TBL.exists(), reason="barevná tabulka není k dispozici")
def test_color_tbl_a_prevod_na_aci():
    t = load_ms_color_table(COLOR_TBL)
    assert t[0] == (255, 255, 255) and t[3] == (255, 0, 0)  # pozadí je v souboru první
    # dvojice (barva MicroStationu → ACI) zjištěné z exportu výkresů studentů
    for ms, aci in ((99, 14), (97, 174), (11, 62), (14, 253), (94, 32), (146, 96), (70, 32), (80, 253)):
        assert aci in rgb_to_aci(t[ms]), ms


def test_barva_ms_v_dxf_bez_rgb(make_dxf):
    rs = RuleSet(barevna_tabulka={99: (165, 0, 0)})

    def build(msp, doc):
        msp.add_line((0, 0), (1, 0), dxfattribs={"color": 14})  # MicroStation 99 → ACI 14
        msp.add_line((0, 1), (1, 1), dxfattribs={"color": 12})
    d = make_dxf(build)
    ok, bad = d.features
    assert color_matches(99, ok, "microstation", rs.barevna_tabulka)
    assert not color_matches(99, bad, "microstation", rs.barevna_tabulka)
    assert rs.describe_feature_color(ok) == "99"


def test_alternativy_a_rozsahy():
    assert parse_color("6|0") == "6|0"
    assert parse_weight("0|1") == "0|1" and parse_weight(2.0) == 2.0
    assert code_in_range("2.09–2.17", "2.12") and not code_in_range("2.09–2.17", "2.18")
    assert linetype_matches("0|2.09–2.17|5.30", "CONTINUOUS")
    assert linetype_matches("0|2.09–2.17|5.30", "2.10")
    assert not linetype_matches("5.29|5.30", "CONTINUOUS")
    assert block_matches("1.01–1.09|1.GPS", "1.07_2")  # MicroStation přidává pořadí buňky
    assert block_matches("9.12", "9.12_153") and not block_matches("4.01–4.20", "4.23_1")


def test_rez_pisma():
    assert font_style("Style-Arial Narrow IF (ARIALNI.TTF)") == (False, True)
    assert font_style("Zdůrazněné (ARIALNB.TTF)") == (True, False)
    assert font_style("Style-Arial Narrow (ARIALN.TTF)") == (False, False)
    assert font_style("Style-cs_Working (cs_Working.shx)") == (False, False)


def test_vyska_textu_v_mm_na_papire(make_dxf):
    rs = RuleSet(meritko=200, pravidla=[Rule(kod="10.xx2", hladina="POPIS", geometrie=GeomType.TEXT,
                                             vyska_textu=2.3, sirka_textu=2.2, kurziva=False)])

    def build(msp, doc):
        msp.add_text("dobře", height=0.46, dxfattribs={"layer": "POPIS", "width": 2.2 / 2.3})
        msp.add_text("malý", height=0.32, dxfattribs={"layer": "POPIS", "width": 2.2 / 2.3})
    d = make_dxf(build)
    msgs = [i.message for i in check(d, "symbologie", rs)]
    assert len(msgs) == 1 and "výška textu 1,6 mm (má být 2,3 mm)" in msgs[0]


def test_3d_prvky_v_obecne_rovine(make_dxf):
    """Výkres z MicroStationu ve 3D: lomená čára v šikmé rovině (OCS) se musí převést do WCS."""
    import ezdxf.math as m

    ex = m.Vec3(0.3, -0.2, 0.93).normalize()
    ocs = m.OCS(ex)
    p0 = ocs.from_wcs(m.Vec3(1000, 2000, 250))
    p1 = p0 + m.Vec3(10, 0, 0)
    w0, w1 = ocs.to_wcs(p0), ocs.to_wcs(p1)

    def build(msp, doc):
        msp.add_lwpolyline([(p0.x, p0.y), (p1.x, p1.y)], dxfattribs={"extrusion": ex, "elevation": p0.z})
    d = make_dxf(build)
    (f,) = d.features
    c = list(f.geometry.coords)
    assert abs(c[0][0] - w0.x) < 1e-6 and abs(c[0][1] - w0.y) < 1e-6
    assert abs(c[-1][0] - w1.x) < 1e-6 and abs(c[-1][1] - w1.y) < 1e-6
    assert abs(w1.x - w0.x) > 5  # bez převodu z OCS by souřadnice vyšly úplně jinde


def test_reference_se_rozbali(make_dxf):
    def build(msp, doc):
        blk = doc.blocks.new("Husovice_mapa")
        for i in range(40):
            blk.add_line((i, 0), (i, 1), dxfattribs={"layer": f"H{i % 4}"})
        msp.add_blockref("Husovice_mapa", (0, 0))
        cell = doc.blocks.new("3.13_1")
        cell.add_circle((0, 0), 0.5)
        msp.add_blockref("3.13_1", (5, 5), dxfattribs={"layer": "STROMY"})
    d = make_dxf(build)
    assert sum(1 for f in d.features if f.layer.startswith("H")) == 40
    assert [f.block_name for f in d.features if f.dxftype == "INSERT"] == ["3.13_1"]
    assert any("rozbalen" in w for w in d.warnings)


def test_body_blizko_jednou_na_misto(make_dxf):
    def build(msp, doc):
        for lay in ("poloha", "info", "bunky"):
            msp.add_point((0, 0), dxfattribs={"layer": lay})
            msp.add_point((0.006, 0), dxfattribs={"layer": lay})
    d = make_dxf(build)
    issues = check(d, "body_blizko")
    assert len(issues) == 1 and len(issues[0].feature_ids) == 6


@pytest.mark.skipif(not ATRIBUTY.exists(), reason="podklady od učitele nejsou k dispozici")
def test_import_atributy_um():
    td, hi, m = import_table(ATRIBUTY)
    assert m["kod"] == 0 and m["nazev"] == 1 and m["tucne"] == 10 and m["kurziva"] == 11
    assert text_units_mm(td.rows, hi, m)
    res = generate_rules(td.rows, hi, m, str(ATRIBUTY))
    r = res.rules.by_code()
    assert len(res.rules.pravidla) >= 110
    assert r["2.xx1"].styl_cary == "0|2.09–2.17|5.30"
    assert r["9.01"].tloustka == "0|1" and r["9.08"].barva == "6|0" and r["9.08"].topologie is False
    assert r["10.xx5"].geometrie == GeomType.TEXT and r["10.xx5"].tucne and r["10.xx5"].kurziva
    assert "6.xx2 Kanalizace dešťová" in r and r["6.xx2 Kanalizace dešťová"].barva == 2
    assert not any("Řádek 14" in e for e in res.errors)  # poznámky pod tabulkou se nehlásí


def test_seznam_souradnic_najde_chyby(make_dxf, tmp_path):
    from kontrola.config import Config
    from kontrola.runner import run_checks
    seznam = tmp_path / "seznam.txt"
    seznam.write_text("610844000130001  595975.720 1158246.973 258.269\n"
                      "610844000130002  595975.430 1158240.000 258.757\n"
                      "610844000130003  595970.000 1158246.939 258.525\n"
                      "610844000130004  595965.000 1158246.000 258.000\n", encoding="utf-8")

    def build(msp, doc):
        for i, (y, x) in enumerate([(595975.720, 1158246.973), (595975.430, 1158240.000),
                                    (595970.000, 1158246.939)], start=1):
            msp.add_point((-y, -x), dxfattribs={"layer": "BODY"})
            msp.add_text(str(i if i != 2 else 7), height=0.1, dxfattribs={"layer": "CISLA", "insert": (-y + 0.2, -x)})
            h = {1: "258.27", 2: "258.76", 3: "258.62"}[i]
            msp.add_text(h, height=0.1, dxfattribs={"layer": "VYSKY", "insert": (-y + 0.2, -x - 0.2)})
    d = make_dxf(build)
    cfg = Config()
    cfg.seznam_souradnic = str(seznam)
    msgs = sorted(i.message for i in run_checks(d, None, cfg, only=["seznam_souradnic"]).issues)
    assert msgs == ["Bod č. 4 ze seznamu ve výkresu chybí",
                    "Výška bodu č. 3: ve výkresu 258,62, v seznamu 258,52",
                    "Číslo bodu: ve výkresu „7“, v seznamu 2"] or len(msgs) == 3, msgs
    assert any("chybí" in m for m in msgs) and any("Výška bodu č. 3" in m for m in msgs)
    assert any("„7“" in m for m in msgs)
