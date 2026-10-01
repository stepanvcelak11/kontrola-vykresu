"""CAD – DXF dokument (otevření, zpráva, uložení beze ztrát) a úchyty."""

import math
from pathlib import Path

import ezdxf
import pytest

from kontrola.cad.dokument import CadDokument
from kontrola.cad.uchyty import Uchyty, ortho, polarni, zadani_bodu

ROOT = Path(__file__).resolve().parents[1]


def _doc():
    doc = ezdxf.new("R2000")
    m = doc.modelspace()
    m.add_line((0, 0), (10, 0))
    m.add_line((5, -5), (5, 5))
    m.add_circle((20, 0), 3)
    m.add_lwpolyline([(30, 0), (40, 0), (40, 10)])
    m.add_point((50, 50))
    return doc


def test_uchyty_zakladni():
    u = Uchyty(_doc().modelspace())
    k = u.najdi(10.2, 0.1, 0.5)
    assert k.typ == "konec" and (k.x, k.y) == (10, 0)
    k = u.najdi(5.1, 0.1, 0.5)
    assert k.typ == "prusecik" and abs(k.x - 5) < 1e-12 and abs(k.y) < 1e-12
    k = u.najdi(2.6, 0.1, 0.5)
    assert k is None or k.typ != "konec"
    assert u.najdi(20.1, 0.1, 0.5).typ == "stred_kruznice"
    assert u.najdi(40.1, 9.9, 0.5).typ == "konec"  # vrchol polylinie
    assert u.najdi(50.1, 50.0, 0.5).typ == "bod"
    k = u.najdi(35.0, 0.2, 0.5)
    assert k.typ == "stred" and k.x == 35.0


def test_kolmice_a_tecna():
    u = Uchyty(_doc().modelspace(), zapnute={"kolmice", "tecna"})
    k = u.najdi(7.0, 0.2, 0.5, posledni=(7.0, 4.0))
    assert k.typ == "kolmice" and abs(k.x - 7) < 1e-12 and abs(k.y) < 1e-12
    # tečna z bodu (20, 10) ke kružnici (20,0) r=3
    p = (20.0, 10.0)
    d = 10.0
    beta = math.acos(3 / d)
    a = math.pi / 2 + beta
    t = (20 + 3 * math.cos(a), 3 * math.sin(a))
    k = u.najdi(t[0] + 0.05, t[1], 0.5, posledni=p)
    assert k.typ == "tecna" and math.dist((k.x, k.y), t) < 1e-9
    # tečna je opravdu kolmá na poloměr
    assert abs((k.x - 20) * (k.x - p[0]) + k.y * (k.y - p[1])) < 1e-9


def test_ortho_polarni_a_zadani():
    assert ortho((0, 0), 10, 2) == (10, 0) and ortho((0, 0), 1, 7) == (0, 7)
    x, y = polarni((0, 0), 10, 1, 50.0)  # nejbližší 0 gon
    assert abs(y) < 1e-12 and abs(x - math.hypot(10, 1)) < 1e-12
    assert zadani_bodu("595975.72 1158246.97", None, sjtsk=True) == (-595975.72, -1158246.97)
    assert zadani_bodu("x=1,5 y=-2", None, True) == (1.5, -2)
    assert zadani_bodu("@3,4", (1, 1), False) == (4, 5)
    x, y = zadani_bodu("@10<100", (0, 0), sjtsk=True)  # směrník 100 g = +Y → DXF −x
    assert abs(x + 10) < 1e-9 and abs(y) < 1e-9
    with pytest.raises(ValueError):
        zadani_bodu("nesmysl", None, True)
    with pytest.raises(ValueError):
        zadani_bodu("@1,1", None, True)


def test_dokument_zprava_a_ulozeni_beze_ztrat(tmp_path):
    src = ROOT / "podklady" / "zadani2-husovice" / "Husovice_Včelák_mapa_Kresba.dxf"
    if not src.exists():
        pytest.skip("podklady chybí")
    d = CadDokument.otevri(src)
    assert sum(d.zprava.pocty.values()) > 100 and "DXF" in d.zprava.text()
    out = d.uloz(tmp_path / "kopie.dxf")
    d2 = CadDokument.otevri(out)
    assert d2.zprava.pocty == d.zprava.pocty  # nic se neztratilo
    h1 = {e.dxf.handle: e.dxftype() for e in d.msp}
    h2 = {e.dxf.handle: e.dxftype() for e in d2.msp}
    assert h1 == h2
    # souřadnice v plné přesnosti
    e1 = next(e for e in d.msp if e.dxftype() == "LINE")
    e2 = next(e for e in d2.msp if e.dxf.handle == e1.dxf.handle)
    assert e1.dxf.start == e2.dxf.start and e1.dxf.end == e2.dxf.end
    # opakované uložení nic nemění
    out2 = d2.uloz(tmp_path / "kopie2.dxf")
    assert CadDokument.otevri(out2).zprava.pocty == d.zprava.pocty


def test_dokument_novy_a_starsi_verze(tmp_path):
    d = CadDokument()
    d.msp.add_line((0, 0), (1, 1))
    p = d.uloz(tmp_path / "novy.dxf", verze="R2004")
    assert ezdxf.readfile(p).dxfversion == "AC1018"
    with pytest.raises(ValueError):
        d.uloz(tmp_path / "x.dxf", verze="R2000")  # do starší verze ne – ztráta dat


def test_poskozeny_dxf(tmp_path):
    p = tmp_path / "rozbity.dxf"
    p.write_text("tohle není DXF", encoding="utf-8")
    with pytest.raises(ValueError):
        CadDokument.otevri(p)


def test_uchyty_jedna_mala_kruznice_a_velky_kruh():
    doc = ezdxf.new("R2000")
    m = doc.modelspace()
    m.add_circle((0, 0), 1)
    u = Uchyty(m)
    assert len(u.grid) < 100000 and u.najdi(0.05, 0, 0.2).typ == "stred_kruznice"
    m.add_circle((0, 0), 1e6)
    m.add_line((0, 0), (0.001, 0))
    u = Uchyty(m)
    assert len(u.grid) < 100000 and u.velke


def test_keyiny_a_cislo_bodu():
    from types import SimpleNamespace

    from kontrola.cad.uchyty import zadani_bodu
    assert zadani_bodu("xy=1.5,-2", None, True) == (1.5, -2)
    assert zadani_bodu("DL=3,4", (1, 1), False) == (4, 5)
    x, y = zadani_bodu("di=10,100", (0, 0), sjtsk=True)
    assert abs(x + 10) < 1e-9 and abs(y) < 1e-9
    body = {"4001": SimpleNamespace(y=595975.72, x=1158246.97)}.get
    assert zadani_bodu("#4001", None, True, body) == (-595975.72, -1158246.97)
    with pytest.raises(ValueError, match="není"):
        zadani_bodu("#9", None, True, body)
