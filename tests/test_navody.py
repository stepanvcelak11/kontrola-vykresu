"""Každá chyba má návod k opravě."""

from pathlib import Path

from kontrola.config import Config
from kontrola.io import read_dxf
from kontrola.navody import navod
from kontrola.rules import RuleSet
from kontrola.runner import run_checks

ROOT = Path(__file__).resolve().parents[1]


def test_kazda_chyba_ma_navod():
    cases = [(ROOT / "ukazky" / "ukazkovy_vykres.dxf", ROOT / "ukazky" / "konfigurace.yaml")]
    z1 = ROOT / "podklady" / "zadani1-microstation"
    if (z1 / "Vcelak_13_navic.dxf").exists():
        cases.append((z1 / "Vcelak_13_navic.dxf", z1 / "pravidla_zadani1.yaml"))
    seen = set()
    for dxf, rules in cases:
        res = run_checks(read_dxf(dxf), RuleSet.load(rules), Config.load(rules))
        for i in res.issues:
            assert navod(i), (i.check_id, i.message)
            seen.add(i.check_id)
    assert len(seen) >= 8


def test_navod_symbologie():
    from kontrola.checks.base import Issue, Severity
    i = Issue("symbologie", "x", Severity.CHYBA, "Plot: barva 3 (má být 93), měřítko stylu 1 (má být 0,5)", 0, 0)
    t = navod(i)
    assert "barvu na 93" in t and "měřítko stylu čáry (Line Style Scale) na 0,5" in t


def test_kazda_kontrola_ma_napovedu_a_navod():
    from kontrola.checks.base import REGISTRY, Issue, Severity
    from kontrola.ui.help_topics import TOPICS
    chybi_napoveda = [cid for cid in REGISTRY if cid not in TOPICS]
    chybi_navod = [cid for cid in REGISTRY if not navod(Issue(cid, REGISTRY[cid].nazev, Severity.CHYBA, "x", 0, 0))]
    assert not chybi_napoveda, chybi_napoveda
    assert not chybi_navod, chybi_navod
