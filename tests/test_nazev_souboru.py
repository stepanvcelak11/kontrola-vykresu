from kontrola.nazev_souboru import zhodnot


def test_spravny_nazev_a_dalsi_oprava():
    h = zhodnot("C:/x/Vcelak_13_a0_t0.dgn")
    assert h.ok and h.dalsi_a == "Vcelak_13_a1_t0.dgn" and h.dalsi_t == "Vcelak_13_a0_t1.dgn"


def test_spatny_nazev_s_radou():
    h = zhodnot("Včelák_13_a0_t0.dgn")
    assert not h.ok and "Vcelak_13_a0_t0.dgn" in h.text
    h = zhodnot("Vcelak_13.dgn")
    assert not h.ok and "Vcelak_13_a0_t0.dgn" in h.text
    h = zhodnot("Vcelak_13_navic.dxf")
    assert not h.ok


def test_jine_zadani_se_neresi():
    assert zhodnot("Husovice_Včelák_mapa_Kresba.dxf") is None
    assert zhodnot("ukazkovy_vykres.dxf") is None
