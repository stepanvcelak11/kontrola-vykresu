"""Kódování prvků účelové mapy: kódovník, kódy u bodů a sestavení kresby."""

from pathlib import Path

from kontrola.geodezie.body import Bod
from kontrola.geodezie.kodovnik import Kod, Kodovnik, rozloz, sestav

ROOT = Path(__file__).resolve().parents[1]


def _b(c, y, x, kod):
    return Bod(str(c), y, x, 250.0, kod)


def test_rozlozeni_kodu():
    assert rozloz("PL BUD/Z PL#2/K, 3.13;x/u") == [("PL", "", None), ("BUD", "", "zacatek"), ("PL", "2", "konec"),
                                                   ("3.13", "", None), ("x", "", "uzavrit")]
    assert rozloz("") == []


def test_linie_plochy_a_znacky():
    kv = Kodovnik([Kod("PL", "plot"), Kod("BUD", "budova", "plocha", vrstva="5"), Kod("STR", "strom", "bod", bunka="3.13")])
    body = [_b(1, 0, 0, "PL"), _b(2, 10, 0, "PL BUD"), _b(3, 20, 0, "PL/K"), _b(4, 30, 0, "PL"), _b(5, 40, 0, "PL"),
            _b(6, 10, 10, "BUD"), _b(7, 0, 10, "BUD"), _b(8, 5, 5, "STR"), _b(9, 1, 1, "XX"),
            _b(10, 50, 0, "PL#2"), _b(11, 60, 0, "PL#2"), _b(12, 70, 0, "PL/Z"), _b(13, 80, 0, "PL")]
    kr = sestav(body, kv)
    linie = {(lin.kod.kod, tuple(b.cislo for b in lin.body), lin.uzavrena) for lin in kr.linie}
    assert ("PL", ("1", "2", "3"), False) in linie  # /K ukončí
    assert ("PL", ("4", "5"), False) in linie  # /Z bodu 12 ukončí předchozí linii
    assert ("PL", ("12", "13"), False) in linie
    assert ("PL", ("10", "11"), False) in linie  # souběžná linie #2
    assert ("BUD", ("2", "6", "7"), True) in linie  # plocha se uzavře
    assert [(k.kod, b.cislo) for k, b in kr.bodove] == [("STR", "8")]
    assert kr.nezname == {"XX": 1} and "XX" in kr.souhrn()


def test_kodovnik_csv_a_ze_zadani(tmp_path):
    kv = Kodovnik([Kod("PL", "plot drátěný", "linie", "2.xx1 – Ploty", styl="2.13"), Kod("B", "budova", "plocha")])
    f = kv.uloz(tmp_path / "k.csv")
    k2 = Kodovnik.nacti(f)
    assert [(k.kod, k.druh, k.styl, k.predvolba) for k in k2.kody] == [("PL", "linie", "2.13", "2.xx1 – Ploty"),
                                                                       ("B", "plocha", "", "")]
    assert Kodovnik.z_textu("kód;popis;druh\nST;strom;b\n").kody[0].druh == "bod"
    from kontrola.cad.zadani import predvolby
    from kontrola.rules import RuleSet
    pv = predvolby(RuleSet.load(ROOT / "podklady" / "zadani2-husovice" / "pravidla_zadani2.yaml"))
    z = Kodovnik.ze_zadani(pv)
    assert z.najdi("3.13").druh == "bod" and z.najdi("2.13").druh == "linie" and z.najdi("1.05").bunka == "1.05"
    # kód mimo kódovník se najde v zadání (číslo stylu / buňky)
    kr = sestav([_b(1, 0, 0, "2.13"), _b(2, 5, 0, "2.13"), _b(3, 1, 1, "3.13")], Kodovnik(), pv)
    assert len(kr.linie) == 1 and kr.linie[0].kod.styl == "2.13" and kr.bodove[0][0].bunka == "3.13"
