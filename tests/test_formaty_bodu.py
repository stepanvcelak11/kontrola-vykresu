"""Import/export seznamu souřadnic s rozpoznáním formátu."""

from pathlib import Path

from kontrola.geodezie.formaty import Format, nacti_soubor, nacti_text, rozpoznej, zapis_text

ROOT = Path(__file__).resolve().parents[1]


def test_groma_seznam_mezery():
    t = ("610844000130001     595975.720    1158246.973     258.269\n"
         "610844000130002     595975.430    1158246.915     258.757\n")
    body, var, fmt = nacti_text(t)
    assert not var and fmt.sloupce == ["cislo", "y", "x", "z"]
    assert body[0].cislo == "610844000130001" and body[0].y == 595975.72 and body[0].z == 258.269


def test_csv_strednik_carka_hlavicka_kod():
    t = "Číslo;Y;X;Z;Kód\n1;595975,72;1158246,97;258,27;plot\n2;595976,10;1158247,01;;roh\n"
    body, var, fmt = nacti_text(t)
    assert fmt.oddelovac == ";" and fmt.desetinna_carka and fmt.preskocit == 1
    assert fmt.sloupce == ["cislo", "y", "x", "z", "kod"], fmt
    assert body[1].z is None and body[1].kod == "roh" and body[0].x == 1158246.97


def test_zaporne_a_prohozene():
    t = "5 -1158246.97 -595975.72 258.3\n6 -1158247.00 -595976.00 258.1\n"
    fmt = rozpoznej(t)
    assert fmt.zaporne and fmt.prohodit_yx
    body, _, _ = nacti_text(t, fmt)
    assert body[0].y == 595975.72 and body[0].x == 1158246.97


def test_spatne_radky_jsou_varovani_ne_pad():
    t = "1 595975.72 1158246.97\nhlouposti tady\n3 abc 1158246.97\n4 595976.72 1158247.97\n"
    body, var, _ = nacti_text(t)
    assert [b.cislo for b in body] == ["1", "4"] and len(var) == 2 and "řádek 3" in var[1]


def test_vlastni_format_sloupcu():
    fmt = Format(sloupce=["cislo", "kod", "x", "y"], oddelovac=",")
    body, var, _ = nacti_text("7,plot,1158246.97,595975.72\n", fmt)
    assert not var and body[0].y == 595975.72 and body[0].kod == "plot"


def test_export_a_zpet_beze_ztraty():
    body, _, _ = nacti_text("1 595975.123456 1158246.987654 258.2691\n")
    t = zapis_text(body, des_xy=6, des_z=4)
    b2, _, _ = nacti_text(t)
    assert b2[0].y == 595975.123456 and b2[0].z == 258.2691
    csv = zapis_text(body, ["cislo", "y", "x"], oddelovac=";", hlavicka=True, desetinna_carka=True)
    assert csv.splitlines()[1] == "1;595975,12;1158246,99"


def test_skutecne_seznamy_ze_zadani():
    for p in (ROOT / "podklady/zadani2-husovice/Husovice_Včelák_seznam.txt",
              ROOT / "podklady/zadani2-husovice/dane_body.txt", ROOT / "podklady/zadani1-microstation/Body13_tr.txt"):
        if not p.exists():
            continue
        body, var, fmt = nacti_soubor(p)
        assert len(body) >= 2 and not var, (p.name, var[:3])
        assert all(300_000 < b.y < 900_000 and 900_000 < b.x < 1_300_000 for b in body), p.name
