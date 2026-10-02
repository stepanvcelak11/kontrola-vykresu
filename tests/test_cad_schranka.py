import ezdxf
import pytest

from kontrola.cad import schranka as S
from kontrola.cad import upravy as U


def test_kopirovani_mezi_vykresy():
    a = ezdxf.new("R2013", setup=True)
    a.layers.add("PLOTY", color=3)
    a.linetypes.add("DGN Style 2", pattern=[1.0, 0.5, -0.5])
    blk = a.blocks.new("3.13")
    blk.add_circle((0, 0), 0.5)
    m = a.modelspace()
    l1 = m.add_line((-600000, -1160000), (-600010, -1160000), dxfattribs={"layer": "PLOTY", "linetype": "DGN Style 2"})
    ins = m.add_blockref("3.13", (-600005, -1160005), dxfattribs={"layer": "PLOTY"})
    assert S.kopiruj(a, [l1, ins]) == 2
    del a  # schránka platí i po zavření původního výkresu
    b = ezdxf.new("R2013")
    mb = b.modelspace()
    h = U.Historie(mb)
    nove = S.vloz(b, mb, h)
    assert len(nove) == 2 and "PLOTY" in b.layers and "3.13" in b.blocks and "DGN Style 2" in b.linetypes
    car = mb.query("LINE").first
    assert (car.dxf.start.x, car.dxf.start.y) == (-600000, -1160000)  # shodně se světem
    S.vloz(b, mb, h, 5, 0)
    assert len(mb.query("LINE")) == 2
    h.krok_zpet()
    h.krok_zpet()
    assert len(mb) == 0


def test_prazdny_vyber():
    with pytest.raises(ValueError):
        S.kopiruj(ezdxf.new(), [])
