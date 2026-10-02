from kontrola.geodezie.body import Bod, SeznamBodu
from kontrola.geodezie.spojnice import Spojnice


def test_spojnice(tmp_path):
    s = SeznamBodu()
    s.pridej([Bod("10", 0, 0, kod="plot"), Bod("2", 1, 0, kod="plot"), Bod("3", 2, 0, kod="plot"),
              Bod("4", 0, 5, kod="budova")])
    sp = Spojnice()
    assert sp.z_kodu(s.body, "plot") == 2
    assert sp.dvojice == [("2", "3"), ("3", "10")]  # v pořadí čísel bodů
    assert not sp.pridej("3", "2") and not sp.pridej("4", "4")
    assert sp.prepni("4", "2") and not sp.prepni("2", "4")
    sp.pridej("4", "99")
    assert len(sp.platne(s)) == 2  # na neexistující bod 99 se nekreslí
    sp.uloz(tmp_path / "s.json")
    sp2 = Spojnice.nacti(tmp_path / "s.json")
    assert sp2.dvojice == sp.dvojice
    assert sp2.smaz_body(["3"]) == 2 and len(sp2) == 1
    assert len(Spojnice.nacti(tmp_path / "neni.json")) == 0
