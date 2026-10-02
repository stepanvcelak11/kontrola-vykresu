from pathlib import Path

import pytest

from kontrola import mgeo_cleaner as M
from kontrola.config import Config

XML = Path(__file__).resolve().parents[1] / "podklady" / "ucitel-geo" / "Topologie2021.clean.xml"


@pytest.mark.skipif(not XML.exists(), reason="chybí konfigurace učitele")
def test_nastaveni_ucitele():
    n = M.nacti(XML)
    assert (n.tolerance, n.min_delka, n.pretah) == (0.01, 0.09, 0.02)
    assert n.volne_konce and len(n.vrstvy) == 63
    cfg = Config()
    cfg.tolerance = 0.05
    zmeny = M.pouzij(cfg, n)
    assert cfg.tolerance == 0.01 and cfg.settings("kratke_linie").parametry["min_delka"] == 0.09
    assert cfg.settings("chybejici_napojeni").parametry["max_pretazeni"] == 0.02
    assert not cfg.settings("visici_konce").parametry.get("hladiny")  # všech 63 vrstev = bez omezení
    assert zmeny


def test_omezeni_vrstev(tmp_path):
    f = tmp_path / "t.clean.xml"
    f.write_text('<Header><Config><Vars><Struct name="G"><Var name="cleanTolerance" type="float">0.02</Var>'
                 '<Var name="OznacitVolneKonce" type="boolean">0</Var></Struct>'
                 '<Array name="ProcessLevels"><Struct name="0"><Var name="level">5</Var></Struct>'
                 '<Struct name="1"><Var name="level">12</Var></Struct></Array></Vars></Config></Header>',
                 encoding="utf-8")
    cfg = Config()
    M.pouzij(cfg, M.nacti(f))
    assert cfg.tolerance == 0.02 and not cfg.settings("visici_konce").zapnuto
    assert cfg.settings("duplicity").parametry["hladiny"] == "5,Vrstva 5,12,Vrstva 12"
    with pytest.raises(ValueError):
        f.write_text("<a/>", encoding="utf-8")
        M.nacti(f)
