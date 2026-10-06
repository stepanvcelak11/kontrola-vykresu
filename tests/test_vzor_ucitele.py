"""Porovnání s hotovým výkresem učitele (tolerantní párování kresby)."""

from kontrola.vzor_ucitele import ATRIBUTY, CHYBI, JINA_VRSTVA, JINY_TEXT, NAVIC, porovnej


def _ucitel(msp, doc):
    msp.add_lwpolyline([(0, 0), (50, 0), (50, 30)], dxfattribs={"layer": "PLOT", "color": 1})
    msp.add_line((0, 10), (40, 10), dxfattribs={"layer": "PLOT", "color": 1})
    msp.add_lwpolyline([(10, 15), (20, 15), (20, 25), (10, 25)], close=True, dxfattribs={"layer": "BUDOVA"})
    msp.add_line((0, 40), (30, 40), dxfattribs={"layer": "CESTA"})
    msp.add_point((5, 5), dxfattribs={"layer": "BODY"})
    msp.add_point((45, 5), dxfattribs={"layer": "BODY"})
    msp.add_text("125/3", dxfattribs={"layer": "PARCELY", "height": 1.0}).set_placement((30, 20))
    msp.add_text("Husova", dxfattribs={"layer": "ULICE", "height": 2.0}).set_placement((5, 45))


def _student(msp, doc):
    d = 0.03  # kreslí ze svého výpočtu – posun o 3 cm je v toleranci
    # plot rozdělený na dvě čáry s lomovým bodem navíc
    msp.add_lwpolyline([(0 + d, 0), (25, 0), (50 + d, 0)], dxfattribs={"layer": "PLOT", "color": 1})
    msp.add_line((50 + d, 0), (50 + d, 30), dxfattribs={"layer": "PLOT", "color": 1})
    msp.add_line((0, 10 + d), (40, 10 + d), dxfattribs={"layer": "PLOT", "color": 3})  # jiná barva
    # budova chybí, cesta je ve špatné vrstvě, plus čára navíc
    msp.add_line((0, 40), (30, 40), dxfattribs={"layer": "PLOT"})
    msp.add_line((60, 0), (60, 20), dxfattribs={"layer": "PLOT"})
    msp.add_point((5.02, 5), dxfattribs={"layer": "BODY"})  # druhý bod chybí
    msp.add_text("125/4", dxfattribs={"layer": "PARCELY", "height": 1.0}).set_placement((30.2, 20))
    msp.add_text("Husova", dxfattribs={"layer": "ULICE", "height": 2.0}).set_placement((6, 45))


def test_porovnani_s_ucitelem(make_dxf):
    u = make_dxf(_ucitel, name="ucitel.dxf")
    s = make_dxf(_student, name="student.dxf")
    r = porovnej(u, s, tol=0.10)
    podle = {}
    for z in r.zmeny:
        podle.setdefault(z.druh, []).append(z)
    assert {z.vrstva for z in podle[CHYBI]} == {"BUDOVA", "BODY"}, [z.popis for z in podle[CHYBI]]
    assert len(podle[JINA_VRSTVA]) == 1 and "CESTA" in podle[JINA_VRSTVA][0].popis
    assert len(podle[NAVIC]) == 1 and "20 m" in podle[NAVIC][0].popis
    assert len(podle[ATRIBUTY]) == 1 and "barva" in podle[ATRIBUTY][0].popis
    assert len(podle[JINY_TEXT]) == 1 and "125/3" in podle[JINY_TEXT][0].popis
    assert 0.6 < r.shoda_kresby < 0.9
    plot = next(v for v in r.vrstvy if v.vrstva == "PLOT")
    assert plot.ucitel_pocet == 2 and plot.student_pocet == 5


def test_jina_lokalita(make_dxf):
    u = make_dxf(_ucitel, name="ucitel.dxf")

    def daleko(msp, doc):
        msp.add_line((5000, 0), (5010, 0))
    s = make_dxf(daleko, name="student.dxf")
    r = porovnej(u, s)
    assert not r.zmeny and "nepřekrývají" in r.souhrn()
