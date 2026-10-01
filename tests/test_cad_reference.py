"""CAD – reference (XREF) a modely (listy)."""

import ezdxf
import pytest

from kontrola.cad import reference as R
from kontrola.cad import upravy as U
from kontrola.cad.dokument import CadDokument


def _podklad(tmp_path):
    d = ezdxf.new("R2000", setup=True)
    d.layers.add("PODKLAD")
    m = d.modelspace()
    m.add_line((0, 0), (10, 0), dxfattribs={"layer": "PODKLAD", "linetype": "DASHED"})
    m.add_circle((5, 5), 2, dxfattribs={"layer": "PODKLAD"})
    m.add_text("Parcela č. 12", height=1, dxfattribs={"layer": "PODKLAD"}).set_placement((1, 1))
    f = tmp_path / "podklad.dxf"
    d.saveas(f)
    return f


def test_pripojeni_ulozeni_a_nacteni(tmp_path):
    f = _podklad(tmp_path)
    dok = CadDokument()
    h = U.Historie(dok.msp)
    r = R.pripoj(dok.doc, h, f, zaklad=tmp_path, vlozeni=(100, 200), meritko=2, natoceni=90)
    assert r.doc is not None and len(dok.msp) == 1
    # transformace: bod (10, 0) podkladu → otočit o 90°, měřítko 2, posun (100, 200) → (100, 220)
    p = r.matice.transform((10, 0, 0))
    assert abs(p.x - 100) < 1e-9 and abs(p.y - 220) < 1e-9
    c = [e for e in r.prvky_pro_uchyty() if e.dxftype() == "CIRCLE"][0]
    assert c.dxf.center.isclose((90, 210, 0)) and abs(c.dxf.radius - 4) < 1e-12
    out = dok.uloz(tmp_path / "vykres.dxf")
    # znovu otevřít: reference se najde s relativní cestou, polohou, měřítkem a natočením
    d2 = CadDokument.otevri(out)
    refs = R.najdi(d2.doc, out.parent)
    assert len(refs) == 1 and refs[0].cesta == f.resolve() and refs[0].doc is not None
    assert refs[0].vlozeni == (100, 200) and refs[0].meritko == 2 and refs[0].natoceni == 90
    assert d2.doc.blocks.get(refs[0].nazev).block.dxf.xref_path == "podklad.dxf"
    # odpojení a Zpět
    h2 = U.Historie(d2.msp)
    R.odpoj(d2.doc, h2, refs[0])
    assert len(d2.msp) == 0
    h2.krok_zpet()
    assert len(d2.msp) == 1


def test_kopie_z_reference(tmp_path):
    f = _podklad(tmp_path)
    dok = CadDokument()
    h = U.Historie(dok.msp)
    r = R.pripoj(dok.doc, h, f, vlozeni=(1000, 0))
    nove = R.kopiruj(dok.msp, h, r)
    assert sorted(e.dxftype() for e in nove) == ["CIRCLE", "LINE", "TEXT"]
    ln = next(e for e in nove if e.dxftype() == "LINE")
    assert ln.dxf.start.isclose((1000, 0, 0)) and ln.dxf.layer == "PODKLAD" and "PODKLAD" in dok.doc.layers
    assert ln.dxf.linetype == "DASHED" and "DASHED" in dok.doc.linetypes
    assert next(e for e in nove if e.dxftype() == "TEXT").dxf.text == "Parcela č. 12"
    h.krok_zpet()
    assert len(dok.msp) == 1  # zbylo jen vložení reference
    with pytest.raises(ValueError):
        R.pripoj(dok.doc, h, tmp_path / "neni.dxf")
    with pytest.raises(ValueError):
        R.pripoj(dok.doc, h, f, meritko=0)
