"""Styly čar MicroStationu z knihoven .rsc od učitele (GEO.RSC, UGEO_VP.RSC)."""

import math
from pathlib import Path

import ezdxf
import pytest

from kontrola.io.rsc import RscError, nacti_rsc, najdi, vykresli

DALSI = Path(__file__).resolve().parents[1] / "podklady" / "ucitel-dalsi"
GEO, UGEO = DALSI / "GEO.RSC", DALSI / "UGEO_VP.RSC"
pytestmark = pytest.mark.skipif(not GEO.is_file(), reason="knihovny stylů od učitele nejsou k dispozici")


def test_nacte_vsechny_styly():
    g, u = nacti_rsc(GEO), nacti_rsc(UGEO)
    assert len(g) == 38 and len(u) == 236
    assert {"2.103 PLD VP", "2.163 PLZ VP", "4.223 OZ VP"} <= set(g)
    assert najdi(g, "2.103").nazev == "2.103 PLD VP" and najdi(g, "2.103 pld vp") is not None
    assert najdi(g, "9.999") is None
    plot = g["2.103 PLD VP"]
    assert [s.druh for s in plot.slozky] == ["plna", "body"]
    assert plot.slozky[1].symboly and plot.slozky[1].symboly[0].cary
    carky = u["0.02"].slozky[0]
    assert carky.druh == "carky" and [x.carka for x in carky.useky] == [True, False]


def test_vykresleni_plotu_po_roztecich():
    plot = nacti_rsc(GEO)["2.103 PLD VP"]
    body = [(0.0, 0.0), (50.0, 0.0)]
    cary = vykresli(body, plot)
    assert cary[0] == body  # plná čára
    zuby = cary[1:]
    roztec = sum(u.delka for u in plot.slozky[1].useky)
    assert len(zuby) == pytest.approx(50 / roztec, abs=1)
    # zub kolmo k čáře, na jedné straně (plot jednostranný)
    for z in zuby:
        assert abs(z[0][0] - z[-1][0]) < 1e-9 and max(abs(p[1]) for p in z) > 0.1
    # měřítko stylu zředí zuby
    assert len(vykresli(body, plot, 2.0)) - 1 == pytest.approx(len(zuby) / 2, abs=1)
    # na šikmé čáře jsou zuby otočené s čárou
    s = vykresli([(0, 0), (30, 30)], plot)[1]
    v = (s[-1][0] - s[0][0], s[-1][1] - s[0][1])
    assert abs(v[0] + v[1]) < 1e-6 and math.hypot(*v) > 0.1


def test_carkovana_cara():
    st = nacti_rsc(UGEO)["0.02"]
    c = vykresli([(0, 0), (10, 0)], st)
    dl = st.slozky[0].useky[0].delka
    assert all(abs(math.dist(x[0], x[-1]) - dl) < 1e-9 for x in c[:-1])


def test_spatny_soubor(tmp_path):
    p = tmp_path / "x.rsc"
    p.write_bytes(b"neco")
    with pytest.raises(RscError):
        nacti_rsc(p)


def test_tisk_se_styly(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kontrola.cad import tisk as T
    from kontrola.cad.styly_rsc import nacti
    d = ezdxf.new("R2013")
    d.linetypes.add("2.103", pattern=[0.0])
    d.modelspace().add_lwpolyline([(0, 0), (40, 0), (40, 30)], dxfattribs={"linetype": "2.103"})
    styly = nacti([GEO])
    sc = T._scena(d, d.modelspace(), styly)
    from PySide6.QtWidgets import QGraphicsPathItem
    cesty = [i for i in sc.items() if isinstance(i, QGraphicsPathItem)]
    assert cesty and cesty[0].path().elementCount() > 20
    a = T.Arch("A4", 297, 210, 500)
    a.na_stred(20, 15)
    T.tisk_archu(d, d.modelspace(), tmp_path / "p.pdf", a, styly=styly)
    assert (tmp_path / "p.pdf").stat().st_size > 500


def test_zobrazeni_v_kontrole_podle_rsc():
    from kontrola.cad.styly_rsc import nacti, nastav_aktivni
    from kontrola.io.dxf_loader import load_drawing
    from kontrola.ui.drawing_view import prepare_drawing
    sit = Path(__file__).resolve().parents[1] / "podklady" / "Situace-topologie.dgn"
    if not sit.is_file():
        return
    d = load_drawing(sit)
    nastav_aktivni({})
    bez = prepare_drawing(d)
    nastav_aktivni(nacti([GEO]))
    try:
        s = prepare_drawing(d)
    finally:
        nastav_aktivni({})
    znacky = lambda p: sum(1 for g in p.groups.values() for k in g if "#znacky" in k)  # noqa: E731
    assert znacky(bez) > 0 and znacky(s) < znacky(bez)  # ploty ze stylu, ne přibližné značky


SKOLA = Path(__file__).resolve().parents[1] / "podklady" / "skola-ms"


def test_ceske_knihovny_stylu_zarovnana_jmena():
    """Knihovny z českého MicroStationu (hlavička „Knihovna druhů čar“, jména zarovnaná na 4 bajty)."""
    t = nacti_rsc(SKOLA / "TM25dodatek.rsc")
    assert set(t) == {"1", "hranice vojenských újezdů"}
    m = nacti_rsc(SKOLA / "linkyMJ.rsc")
    assert len(m) == 28 and "2.09_" in m
