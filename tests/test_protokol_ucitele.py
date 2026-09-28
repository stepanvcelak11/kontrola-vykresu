"""Čtení protokolu GISoft od učitele a porovnání s výsledky aplikace."""

from pathlib import Path

from conftest import check  # noqa: F401

from kontrola.protokol_ucitele import compare_with_teacher, read_teacher_log

LOG = Path(__file__).with_name("data_protokol_gisoft.log")


def test_cteni_protokolu_gisoft():
    p = read_teacher_log(LOG)
    assert p.celkem == 187 and len(p.skupiny) == 6 and sum(g.pocet for g in p.skupiny) == 187
    g = {s.vrstva: s for s in p.skupiny}
    assert g["Vrstva 7"].spatne == {"měřítko stylu"}
    assert g["Vrstva 15"].spatne == {"vrstva"}
    assert g["Vrstva 47"].spatne == {"typ"}
    assert g["Vrstva 58"].spatne == {"typ", "tloušťka"}
    assert g["Vrstva 59"].spatne == {"font", "šířka"}


def test_cteni_cp1250(tmp_path):
    f = tmp_path / "p.log"
    f.write_bytes(LOG.read_text(encoding="utf-8").encode("cp1250"))
    assert read_teacher_log(f).skupiny[3].spatne == {"typ"}


def test_porovnani(make_dxf):
    from kontrola.config import Config
    from kontrola.rules import Rule, RuleSet
    from kontrola.runner import run_checks
    rs = RuleSet(pravidla=[Rule(kod="a", hladina="7", barva=3)])

    def build(msp, doc):
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "Vrstva 15", "color": 1, "lineweight": 0,
                                                 "linetype": "Continuous"})
        msp.add_line((0, 1), (5, 1), dxfattribs={"layer": "Vrstva 15", "color": 1, "lineweight": 0,
                                                 "linetype": "Continuous"})
    d = make_dxf(build)
    res = run_checks(d, rs, Config(), only=["nepovolene_hladiny"])
    rows, summary = compare_with_teacher(read_teacher_log(LOG), d, rs, res.issues)
    r15 = next(r for r in rows if r.vrstva == "Vrstva 15")
    assert r15.ucitel == 2 and r15.program == 2
    assert "Program našel stejně 2" in summary
