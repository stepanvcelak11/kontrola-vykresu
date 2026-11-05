"""Import GSI (Leica): stejný výpočet jako ze zápisníku Gromy."""

from pathlib import Path

from kontrola.geodezie.gsi import je_gsi, precti_radek, read_gsi, rozdel_orientace, zapis_gsi
from kontrola.checks.seznam import read_point_list
from kontrola.vypocet import compute, read_zap

Z = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"


def test_cteni_slov_a_jednotek():
    r = precti_radek("*110001+0000000000004001 21.322+0000000012345678 22.322+0000000009876543 "
                     "31..06+0000000000213456 87..16+0000000000015000")
    assert r["bod"] == "4001" and abs(r["hz"] - 123.45678) < 1e-12 and abs(r["z"] - 98.76543) < 1e-12
    assert abs(r["31"] - 21.3456) < 1e-12 and abs(r["87"] - 1.5) < 1e-12
    # GSI-8, stupně ddd.mmss a mm
    r = precti_radek("110001+00000012 21.324+09030000 31..00+00012345")
    assert r["bod"] == "12" and abs(r["hz"] - 100.5555555555) < 1e-6 and abs(r["31"] - 12.345) < 1e-12
    assert je_gsi("*110001+0000000000004001 21.322+0000000012345678")
    assert not je_gsi("1 4001 1.523 *")


def test_husovice_gsi_dava_stejne_souradnice_jako_zapisnik(tmp_path):
    zap = Z / "zap_husovice.zap"
    if not zap.exists():
        import pytest
        pytest.skip("chybí podklady")
    dane = read_point_list(Z / "dane_body.txt")
    st = read_zap(zap)
    jmena = {p.cislo for p in dane}
    # GSI nemá oddělení orientací a podrobných bodů: daný bod měřený hned po orientacích by se vzal jako
    # další orientace. Pro přesné porovnání se tyto kontrolní záměry vynechají v obou výpočtech.
    for s_ in st:
        while s_.detail and s_.detail[0].bod in jmena:
            s_.detail.pop(0)
    ref = compute(st, dane)
    f = tmp_path / "husovice.gsi"
    f.write_text(zapis_gsi(st), encoding="ascii")
    st2, var = read_gsi(f)
    assert not var and len(st2) == len(st)
    rozdel_orientace(st2, {p.cislo for p in dane})
    res = compute(st2, dane)
    a = {p.bod: p for p in ref.body}
    b = {p.bod: p for p in res.body}
    assert set(a) == set(b) and len(b) > 100
    for k in a:
        assert abs(a[k].y - b[k].y) < 2e-4 and abs(a[k].x - b[k].x) < 2e-4, k
        if a[k].z is not None:
            assert abs(a[k].z - b[k].z) < 2e-4, k


def test_gsi_souradnice_tam_a_zpet():
    from kontrola.geodezie.body import Bod
    from kontrola.geodezie.formaty import nacti_text
    from kontrola.geodezie.gsi import zapis_gsi_body
    body = [Bod("4001", 744123.4567, 1045678.9012, 312.345), Bod("A12", 744100.0, 1045600.0)]
    t = zapis_gsi_body(body)
    assert t.startswith("*110001+0000000000004001 81..16+0000007441234567 82..16+0000010456789012")
    zpet, var, _f = nacti_text(t)
    assert not var and [b.cislo for b in zpet] == ["4001", "A12"]
    assert abs(zpet[0].y - 744123.4567) < 1e-9 and abs(zpet[0].z - 312.345) < 1e-9 and zpet[1].z is None
