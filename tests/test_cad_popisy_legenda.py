"""Rozmístění popisů bodů a legenda mapy (kontrola.cad.popisy, kontrola.cad.legenda)."""
from pathlib import Path

import ezdxf
import pytest

from kontrola.cad import legenda as LG
from kontrola.cad import popisy as P
from kontrola.cad.upravy import Historie

ROOT = Path(__file__).resolve().parents[1]


def _vykres():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (20, 0))  # čára přes číslo bodu 1
    msp.add_point((5, 0))
    t1 = msp.add_text("101", height=1.0)
    t1.set_placement((5.2, -0.5))  # přeškrtnuté čarou
    msp.add_point((5, 10))
    t2 = msp.add_text("102", height=1.0)
    t2.set_placement((5.4, 10.4))  # v pořádku
    t3 = msp.add_text("Náměstí", height=2.0)
    t3.set_placement((8, -1.0))  # popis plochy přes čáru – k žádnému bodu nepatří, nechat
    return doc, msp, (t1, t2, t3)


def test_rozmisti_popisy_posune_jen_chybne():
    doc, msp, (t1, t2, t3) = _vykres()
    h = Historie(msp)
    v = P.rozmisti(msp, h)
    assert (v.posunuto, v.nevyreseno, v.v_poradku) == (1, 0, 1)
    assert v.stare == [t1] and t2.dxf.owner is not None and t3.dxf.owner is not None
    novy = v.nove[0]
    box = P.obdelnik(novy)
    assert box.bounds[1] > 0.0 or box.bounds[3] < 0.0  # celý popis leží nad nebo pod čarou
    assert box.distance(__import__("shapely").geometry.Point(5, 0)) < 1.0  # pořád u svého bodu
    # druhé spuštění už nic nemění; Zpět vrátí původní text
    assert P.rozmisti(msp, h).nove == []
    h.krok_zpet()
    assert t1.dxf.owner is not None and novy.dxf.owner is None


def test_rozmisti_popisy_jen_vyber():
    doc, msp, (t1, t2, t3) = _vykres()
    v = P.rozmisti(msp, Historie(msp), [t2])
    assert v.nove == [] and t1.dxf.owner is not None
    v = P.rozmisti(msp, Historie(msp), [t3])  # ve výběru se posune i obecný popis u bodu
    assert v.stare == [t3]


@pytest.mark.skipif(not (ROOT / "podklady/zadani1-microstation/Vcelak_13_navic_opraveno.dxf").exists(), reason="data")
def test_rozmisti_popisy_skolni_vykres_bez_nalezu():
    """Odevzdaný výkres zadání 1: po rozmístění Kontrola nehlásí žádný přeškrtnutý popis a nic nového."""
    from kontrola.config import Config
    from kontrola.io.dxf_loader import load_drawing
    from kontrola.rules import RuleSet
    from kontrola.runner import run_checks
    z = ROOT / "podklady/zadani1-microstation"
    rs = RuleSet.load(z / "pravidla_zadani1.yaml")

    def nalezy(p):
        iss = run_checks(load_drawing(p), rs, Config()).issues
        return sum("přeškrtává" in str(i.message) for i in iss), len(iss)
    pred = nalezy(z / "Vcelak_13_navic_opraveno.dxf")
    doc = ezdxf.readfile(z / "Vcelak_13_navic_opraveno.dxf")
    msp = doc.modelspace()
    v = P.rozmisti(msp, Historie(msp))
    assert pred[0] >= 10 and v.posunuto >= pred[0] and v.nevyreseno == 0
    import tempfile
    out = Path(tempfile.mkdtemp()) / "po.dxf"
    doc.saveas(out)
    po = nalezy(out)
    assert po[0] == 0 and po[1] == pred[1] - pred[0]


def test_legenda_polozky_a_kresba():
    from kontrola.cad.zadani import Predvolba
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for n in ("5", "7"):
        doc.layers.add(n)
    doc.linetypes.add("2.103", pattern=[0.0])
    blk = doc.blocks.new("3.13")
    blk.add_circle((0, 0), 0.5)
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "5", "color": 32})
    msp.add_lwpolyline([(0, 5), (5, 5), (5, 9)], dxfattribs={"layer": "5", "color": 32, "linetype": "DASHED"})
    msp.add_line((0, 2), (10, 2), dxfattribs={"layer": "7", "color": 212, "linetype": "2.103"})
    msp.add_line((0, 3), (10, 3), dxfattribs={"layer": "7", "color": 5})
    msp.add_blockref("3.13", (3, 3), dxfattribs={"layer": "22", "color": 3, "xscale": 0.5, "yscale": 0.5})
    msp.add_line((0, 8), (1, 8), dxfattribs={"layer": "POMOCNA"})
    pv = [Predvolba("Budovy zděné", "linie", "polylinie", vrstva="5", barva=32, typ_cary="CONTINUOUS"),
          Predvolba("Budovy kovové", "linie", "polylinie", vrstva="5", barva=134, typ_cary="CONTINUOUS"),
          Predvolba("Plot dřevěný", "linie", "polylinie", vrstva="7", barva=212, typ_cary="2.103"),
          Predvolba("Strom", "bod", "vlož", vrstva="22", barva=3, blok="3.13")]
    pol = LG.polozky(doc, msp, pv)
    # jen použité druhy, v pořadí zadání; co zadání nezná, je na konci podle hladiny
    assert [p.nazev for p in pol] == ["Budovy zděné", "Plot dřevěný", "Strom", "7", "POMOCNA"]
    assert pol[0].pocet == 2 and pol[1].typ_cary == "2.103" and pol[2].meritko == pytest.approx(0.5)
    h = Historie(msp)
    n_pred = len(msp)
    nove = LG.nakresli(doc, msp, h, pol, (100.0, 50.0), 0.5)
    assert all(e.dxf.layer == LG.VRSTVA for e in nove)
    texty = [e.dxf.text for e in nove if e.dxftype() == "TEXT"]
    assert texty == ["LEGENDA", "Budovy zděné", "Plot dřevěný", "Strom", "7", "POMOCNA"]
    assert texty and nove[2].dxf.color == 32 and [e for e in nove if e.dxftype() == "INSERT"][0].dxf.xscale == 0.5
    assert abs([e for e in nove if e.dxftype() == "TEXT"][1].dxf.height - 1.0) < 1e-9  # 2 mm v měřítku 1:500
    # legenda se sama do další legendy nepočítá a Zpět ji odstraní celou
    assert [p.nazev for p in LG.polozky(doc, msp, pv)] == [p.nazev for p in pol]
    h.krok_zpet()
    assert len(msp) == n_pred


def test_legendu_kontrola_nekontroluje():
    from kontrola.config import Config
    assert "LEGENDA" in Config().ignorovane_hladiny
