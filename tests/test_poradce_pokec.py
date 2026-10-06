"""Poradce: obecné otázky a vtipné odpovědi."""

import datetime as dt

from kontrola.poradce_pokec import pokec


def test_obecne_otazky():
    assert pokec("Ahoj!")[0] == "Ahoj"
    assert pokec("co teď?")[0] == "Co teď"
    assert pokec("Co mám dělat")[0] == "Co teď"
    assert pokec("co umíš")[0] == "Co umím"
    assert "14:05" in pokec("kolik je hodin?", dt.datetime(2026, 10, 6, 14, 5))[1]


def test_vtipne_odpovedi_a_odborne_otazky_nechava_navodum():
    for q in ("řekni vtip", "jaké bude počasí", "dej mi jedničku", "umíš vařit?", "42"):
        assert pokec(q) is not None, q
    for q in ("jak udělat kolmici", "kde je bod 42", "jaká barva má plot", "nedotažená linie"):
        assert pokec(q) is None, q
