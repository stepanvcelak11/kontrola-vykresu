"""Seznam souřadnic: úpravy, hromadné změny, duplicity, Zpět/Znovu, uložení."""

import pytest

from kontrola.geodezie.body import Bod, SeznamBodu, klic_cisla


def _s():
    s = SeznamBodu()
    s.pridej([Bod("10", 100.0, 200.0, 250.0, "plot"), Bod("2", 110.0, 200.0, None, "roh", 3),
              Bod("4001", 120.123456789, 205.987654321, 251.5)])
    return s


def test_pridani_bez_prepisu_a_razeni():
    s = _s()
    n, konf = s.pridej([Bod("2", 0, 0), Bod("5", 1, 1)])
    assert n == 1 and konf == ["2"] and s.najdi("2").y == 110.0  # existující se nepřepíše
    s.serad("cislo")
    assert [b.cislo for b in s.body] == ["2", "5", "10", "4001"]
    assert klic_cisla("13-2") > klic_cisla("13-1") and klic_cisla("9") < klic_cisla("10")


def test_presnost_se_neztraci():
    s = _s()
    t = s.to_json()
    s2 = SeznamBodu.from_json(t)
    assert s2.najdi("4001").y == 120.123456789 and s2.najdi("4001").x == 205.987654321


def test_filtr_a_hledani():
    s = _s()
    assert [b.cislo for b in s.filtruj("plot")] == ["10"]
    assert [b.cislo for b in s.filtruj(kvalita=3)] == ["2"]
    assert s.kody() == ["plot", "roh"]


def test_zpet_znovu_a_historie():
    s = _s()
    s.uprav("10", z=260.0, kod="zeď")
    s.smaz(["2"])
    assert s.najdi("2") is None and s.najdi("10").z == 260.0
    assert s.zpet() and s.najdi("2") is not None
    assert s.zpet() and s.najdi("10").z == 250.0
    assert s.znovu() and s.najdi("10").kod == "zeď"
    popisy = [h.popis for h in s.historie]
    assert "Úprava bodu 10" in popisy and "Smazání 1 bodů" in popisy and "Zpět" in popisy


def test_hromadne_upravy():
    s = _s()
    s.hromadne(["10", "2"], kod="hranice", kvalita=3, dy=0.5)
    assert s.najdi("10").kod == "hranice" and s.najdi("2").y == 110.5 and s.najdi("10").kvalita == 3
    s.hromadne(["10", "2"], pricti_k_cislu=1000)
    assert s.najdi("1010") and s.najdi("1002")
    with pytest.raises(ValueError):
        s.hromadne(["1010"], pricti_k_cislu=2991)  # → 4001 už existuje
    s.zpet()
    assert s.najdi("10") and s.najdi("1010") is None


def test_duplicity_a_bezpecne_slouceni():
    s = SeznamBodu()
    s.body = [Bod("1", 0, 0, 10), Bod("1", 0.004, 0, 12), Bod("7", 50, 50), Bod("8", 50.003, 50)]
    d = s.duplicity(tol=0.01)
    druhy = sorted(x.druh for x in d)
    assert druhy == ["cislo", "poloha"]
    cis = next(x for x in d if x.druh == "cislo")
    s.sluc(cis.body[0], cis.body[1:], prumerovat=True)
    b = s.najdi("1")
    assert len([x for x in s.body if x.cislo == "1"]) == 1
    assert abs(b.y - 0.002) < 1e-12 and b.z == 11 and "sloučeno" in b.poznamka
    s.zpet()
    assert len([x for x in s.body if x.cislo == "1"]) == 2  # sloučení jde vrátit


def test_ulozeni_a_nacteni(tmp_path):
    s = _s()
    p = tmp_path / "seznam.json"
    s.uloz(p)
    s2 = SeznamBodu.nacti(p)
    assert [b.cislo for b in s2.body] == [b.cislo for b in s.body] and s2.najdi("2").kvalita == 3
    assert SeznamBodu.nacti(tmp_path / "neni.json").body == []


def test_uprava_na_existujici_cislo_selze():
    s = _s()
    with pytest.raises(ValueError):
        s.uprav("10", cislo="2")
