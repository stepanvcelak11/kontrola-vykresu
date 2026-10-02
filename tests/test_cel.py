from pathlib import Path

import ezdxf
import pytest

from kontrola.cad.zadani import prevezmi_bloky
from kontrola.io.cel import do_dokumentu, nacti_cel
from kontrola.io.dgn_v8 import DgnError

DALSI = Path(__file__).resolve().parents[1] / "podklady" / "ucitel-dalsi"
NORMA = DALSI / "NORMA.CEL"
GEO = DALSI / "GEO-V8.CEL"
pytestmark = pytest.mark.skipif(not NORMA.is_file(), reason="knihovny buněk od učitele nejsou k dispozici")


def test_nacte_vsechny_bunky_s_nazvy():
    bunky = nacti_cel(NORMA)
    assert len(bunky) == 170
    jmena = [b.nazev for b in bunky]
    assert jmena[:3] == ["1.010", "1.030", "1.040"]
    geo = [b.nazev for b in nacti_cel(GEO)]
    assert len(geo) == 256 and {"KRIZEK", "VCHOD", "2.12K"} <= set(geo)


def test_geometrie_vuci_pocatku_bunky():
    b = {x.nazev: x for x in nacti_cel(NORMA)}
    x0, y0, x1, y1 = b["1.010"].rozsah()
    assert (x0, y0, x1, y1) == pytest.approx((-0.75, -0.75, 0.75, 0.75))
    assert [p[0] for p in b["1.010"].prvky] == ["kruh", "kruh"]
    assert any(p[0] == "cara" and p[3] for p in b["1.030"].prvky)  # vyplněné kvadranty
    assert any(p[0] == "kruh" and p[4] for p in b["6.410"].prvky)  # vyplněný kruh
    assert any(p[0] == "text" and p[3] == "A" for p in b["6.471"].prvky)


def test_bloky_dle_bloku():
    doc = ezdxf.new()
    jmena = do_dokumentu(doc, nacti_cel(NORMA))
    assert len(jmena) == 170 and "1.030" in doc.blocks
    blk = doc.blocks["1.030"]
    assert any(e.dxftype() == "HATCH" for e in blk)
    assert all(e.dxf.color == 0 for e in blk)  # barva dle bloku – určí ji vložená buňka
    assert do_dokumentu(doc, nacti_cel(NORMA)) == []  # existující bloky se nepřepisují
    ref = doc.modelspace().add_blockref("1.030", (100, 200), dxfattribs={"color": 5})
    assert len(list(ref.virtual_entities())) == len(blk)


def test_knihovna_ve_vzorech_zadani(tmp_path):
    doc = ezdxf.new()
    assert len(prevezmi_bloky(doc, [GEO])) == 256
    doc.saveas(tmp_path / "s_bunkami.dxf")
    assert "KRIZEK" in ezdxf.readfile(tmp_path / "s_bunkami.dxf").blocks


def test_neni_knihovna_v8(tmp_path):
    f = tmp_path / "stara.cel"
    f.write_bytes(b"\x08\x09" + b"\0" * 100)
    with pytest.raises(DgnError):
        nacti_cel(f)
