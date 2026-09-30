"""Vlastní čtení DGN V8 – ověřeno proti DXF exportu stejného výkresu z MicroStationu."""

from pathlib import Path

import numpy as np
import pytest
import shapely

ROOT = Path(__file__).resolve().parents[1]
HUS_DGN = ROOT / "podklady" / "zadani2-husovice" / "Husovice_Včelák_mapa.dgn"
HUS_DXF = ROOT / "podklady" / "zadani2-husovice" / "Husovice_Včelák_mapa.dxf"
Z1_DGN = ROOT / "podklady" / "zadani1-microstation" / "Vcelak_13_a0_t0.dgn"


@pytest.mark.skipif(not (HUS_DGN.exists() and HUS_DXF.exists()), reason="data chybí")
def test_dgn_odpovida_dxf_exportu():
    from collections import Counter

    from kontrola.io.dgn_v8 import read_dgn
    from kontrola.io.dxf_loader import read_dxf
    a, b = read_dgn(HUS_DGN), read_dxf(HUS_DXF)
    assert Counter(f.geom_type for f in a.features) == Counter(f.geom_type for f in b.features)
    la, lb = Counter(f.layer for f in a.features), Counter(f.layer for f in b.features)
    shared = sum(min(la[k], lb[k]) for k in la)
    assert shared >= len(b.features) - 2  # vrstvy podle názvů z tabulky vrstev DGN
    for gt in ("linie", "polygon", "bod", "text"):
        A = [f.geometry for f in a.features if f.geom_type.value == gt]
        B = [f.geometry for f in b.features if f.geom_type.value == gt]
        d = shapely.distance(shapely.points(shapely.get_coordinates(np.array(A, dtype=object))),
                             shapely.union_all(np.array(B, dtype=object)))
        assert np.mean(d < 0.03) > 0.98, gt
    ta = sorted((f.text, round(f.text_height, 3)) for f in a.features if f.geom_type.value == "text")
    tb = sorted((f.text, round(f.text_height, 3)) for f in b.features if f.geom_type.value == "text")
    assert ta == tb


@pytest.mark.skipif(not Z1_DGN.exists(), reason="data chybí")
def test_dgn_2d_zadani1_a_otevreni(tmp_path):
    import shutil

    from kontrola.io.dxf_loader import load_drawing
    f = tmp_path / "vykres.dgn"
    shutil.copy(Z1_DGN, f)  # bez DXF vedle → čte se přímo DGN
    d = load_drawing(f)
    assert d.path.endswith(".dgn") and any("přímo z DGN" in w for w in d.warnings)
    texts = {x.text for x in d.features if x.geom_type.value == "text"}
    assert "chodník" in texts and "Dřevovýroba" in texts
    cells = [x for x in d.features if x.dxftype == "INSERT"]
    assert cells and all(x.layer != "Vrstva 0" for x in cells) and cells[0].block_name == "6.01A"
    assert all("MS_BARVA" in x.attributes or x.bylayer for x in d.features)
