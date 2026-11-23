"""Datový model z řádků Směrnice podle čísla zadání (úloha z MGEO)."""

from kontrola.cad.zadani import keyin, predvolby
from kontrola.importer.table import detect_header_row, generate_rules, guess_mapping, split_scale_columns
from kontrola.importer.zadani_radky import parse_radky, z_textu

HLAVA = ["SK", "TŘÍDA PRVKŮ", "VR", "BA", "TL", "ST", "US", "MĚŘÍTKO", "KNIHOVNA", "BUŇKA", "MĚŘÍTKO",
         "FONT", "VÝŠKA", "ŠÍŘKA", "PRVKY", "POZNÁMKA"]


def _r(*v):
    return list(v) + [""] * (16 - len(v))


ROWS = [HLAVA,
        _r("", "ÚČELOVÁ MAPA"),
        _r(),
        _r("", "1. Budovy"),
        _r("01", "Budovy zděné, betonové", "5", "94", "0", "0,2,4,7", "", "", "", "", "", "", "", "", "3,4,15,16"),
        _r("02", "Plot drátěný", "7", "5", "0", "0", "2.123  PL VP", "1.00", "geo.rsc", "", "", "", "", "",
           "3,4,15,16"),
        _r("07", "Telefonní budka", "24", "34", "0", "0,4", "", "", "", "", "", "", "", "", "3,4,15,16"),
        _r("08", "Telefonní budka", "24", "34", "0", "0", "", "", "geo.cel", "6.750", "1.00", "", "", "", "2"),
        _r("10", "Popis povrchů", "40", "75", "0", "0", "", "", "", "", "", "1 - CS_WORKING", "0.65", "0.65",
           "17"),
        _r("14", "Okótování situace", "59", "98", "0", "0", "", "", "", "", "", "1 - CS_WORKING", "0.75", "0.75",
           "33")]


def _mapping():
    h = detect_header_row(ROWS)
    m = guess_mapping(ROWS[h])
    split_scale_columns(ROWS[h], m)
    return h, m


def test_rozpis_zadani_z_wordu():
    t = ("Č. zadání řádek řádek řádek řádek řádek řádek řádek 1 7 15 28 59 92 241 247 "
         "2 8 16 29 60 93 242 248 3 9 17 30 61 94 243 249")
    z = z_textu(t)
    assert z == {1: [7, 15, 28, 59, 92, 241, 247], 2: [8, 16, 29, 60, 93, 242, 248],
                 3: [9, 17, 30, 61, 94, 243, 249]}
    assert parse_radky("7, 15, 28-30") == {7, 15, 28, 29, 30}


def test_jen_radky_zadani_a_stejne_nazvy():
    h, m = _mapping()
    vse = generate_rules(ROWS, h, m)
    assert not vse.errors and not vse.warnings
    kody = [r.kod for r in vse.rules.pravidla]
    assert "Telefonní budka" in kody and "Telefonní budka (značka)" in kody
    jen = generate_rules(ROWS, h, m, jen_radky={5, 6, 9})
    assert [r.kod for r in jen.rules.pravidla] == ["Budovy zděné, betonové", "Plot drátěný", "Popis povrchů"]
    p = {x.kod: x for x in predvolby(jen.rules)}
    assert keyin(p["Popis povrchů"]) == "lv=40;co=75;th=0.65;tw=0.65"
    assert keyin(p["Plot drátěný"]) == "lv=7;co=5;lc=2.123  PL VP;wt=0"
    assert not p["Budovy zděné, betonové"].poznamky  # tloušťka 0 nepotřebuje převodní tabulku



def test_styl_kresli_celym_jmenem():
    """MGEO bere „2.123“ jako jiný styl než „2.123  PL VP“ – CAD musí kreslit celým jménem z knihovny."""
    from kontrola.rules import linetype_matches
    h, m = _mapping()
    p = {x.kod: x for x in predvolby(generate_rules(ROWS, h, m).rules)}
    assert p["Plot drátěný"].typ_cary == "2.123  PL VP"
    assert linetype_matches("2.123  PL VP", p["Plot drátěný"].typ_cary)
    assert not linetype_matches("2.123  PL VP", "2.123")
