"""Porovnání dvou verzí výkresu."""

from kontrola.porovnani import ODEBRANO, PRIDANO, UPRAVENO, ZMENENO, compare, summary


def test_porovnani_verzi(make_dxf):
    def v1(msp, doc):
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "PLOT"})
        msp.add_lwpolyline([(0, 0), (5, 0), (5, 5), (0, 5)], close=True, dxfattribs={"layer": "BUDOVY"})
        msp.add_line((20, 0), (30, 0), dxfattribs={"layer": "PLOT"})
        msp.add_line((50, 50), (60, 50), dxfattribs={"layer": "CESTA"})
        msp.add_text("12", dxfattribs={"layer": "POPIS", "insert": (2, 2), "height": 1})

    def v2(msp, doc):
        msp.add_line((10, 0), (0, 0), dxfattribs={"layer": "PLOT"})  # jen obrácený směr = beze změny
        msp.add_lwpolyline([(5, 5), (0, 5), (0, 0), (5, 0)], close=True,
                           dxfattribs={"layer": "BUDOVY", "color": 1})  # jiný začátek, jiná barva
        msp.add_line((20, 0), (30.5, 0), dxfattribs={"layer": "PLOT"})  # prodloužená
        msp.add_line((0, 20), (5, 20), dxfattribs={"layer": "PLOT"})  # nová
        msp.add_text("12", dxfattribs={"layer": "POPIS", "insert": (2, 2), "height": 1})

    old, new = make_dxf(v1), make_dxf(v2)
    ch = compare(old, new)
    druhy = sorted(z.druh for z in ch)
    assert druhy == sorted([ZMENENO, UPRAVENO, PRIDANO, ODEBRANO]), [(z.druh, z.popis) for z in ch]
    z = {c.druh: c for c in ch}
    assert "barva" in z[ZMENENO].popis
    assert "délka +0,5" in z[UPRAVENO].popis
    assert z[ODEBRANO].vrstva == "CESTA"
    assert "přidáno: 1" in summary(ch)
    assert compare(old, old) == []
