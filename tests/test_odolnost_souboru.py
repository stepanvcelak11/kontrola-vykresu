"""Poškozené a neúplné soubory: aplikace nespadne a srozumitelně upozorní."""

import json
from pathlib import Path

import pytest

from kontrola.io.dxf_loader import DrawingLoadError, load_drawing

ROOT = Path(__file__).resolve().parents[1]


def test_useknuty_dxf_varuje(tmp_path):
    src = (ROOT / "ukazky" / "ukazkovy_vykres.dxf").read_bytes()
    p = tmp_path / "useknuty.dxf"
    p.write_bytes(src[: len(src) // 2])
    d = load_drawing(p)
    assert any("nejsou žádné prvky" in w for w in d.warnings)


@pytest.mark.parametrize("obsah", [b"{not json", b"[1, 2]"])
def test_spatny_geojson_srozumitelna_chyba(tmp_path, obsah):
    p = tmp_path / "x.geojson"
    p.write_bytes(obsah)
    with pytest.raises(DrawingLoadError, match="GeoJSON"):
        load_drawing(p)


def test_geojson_s_vadnou_polozkou(tmp_path):
    p = tmp_path / "x.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        None, {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [5, 0]]}}]}), "utf-8")
    d = load_drawing(p)
    assert len(d.features) == 1


def test_useknuty_dgn_varuje(tmp_path):
    src_path = ROOT / "podklady" / "zadani1-microstation" / "Vcelak_13_a0_t0.dgn"
    if not src_path.exists():
        pytest.skip("DGN chybí")
    from kontrola.io.dgn_v8 import read_dgn
    src = src_path.read_bytes()
    p = tmp_path / "x.dgn"
    p.write_bytes(src[: len(src) // 3])
    d = read_dgn(p)
    assert any("poškozený" in w for w in d.warnings)
    p.write_bytes(src)
    assert not any("poškozený" in w for w in read_dgn(p).warnings)
