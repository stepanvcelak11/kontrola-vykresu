"""DGN V7: zápis z CAD a čtení zpět (MicroStation), ověřené i nezávislou čtečkou GDAL, je-li nainstalovaná."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import ezdxf
import pytest

from kontrola.cad.dokument import CadDokument
from kontrola.cad.export_dgn import exportuj
from kontrola.io import dgn_v7_zapis as Z
from kontrola.io.dgn_v7 import _vax, nacti_prvky, rad50_text, read_dgn_v7
from kontrola.io.dxf_loader import load_drawing
from kontrola.rules import RuleSet

POD = Path(__file__).resolve().parents[1] / "podklady"


def test_cisla_dgn():
    for v in (1.0, -1.0, 0.5, 5000.0, 743000123.25, -1043000456.5, 1e-3, 12345.6789):
        assert abs(_vax(Z.vax_double(v), 0) - v) <= abs(v) * 1e-15
    assert _vax(Z.vax_double(0.0), 0) == 0.0
    for n in ("3.13A", "6.01", "ST", "BUNKA"):
        assert rad50_text(Z.rad50(n), 0) == n.upper()
    assert Z.zarovnani(0, 0) == 2 and Z.zarovnani(1, 2) == 7 and Z.zarovnani(2, 3) == 12


def _vykres():
    doc = ezdxf.new("R2013", setup=True)
    msp = doc.modelspace()
    for n in ("5", "7", "22", "59"):
        doc.layers.add(n)
    doc.linetypes.add("DGN Style 2", [1.5, 0.9, -0.6])
    blk = doc.blocks.new("3.13A")
    blk.add_circle((0, 0), 0.5)
    blk.add_line((-0.5, 0), (0.5, 0))
    msp.add_line((-743000, -1043000), (-742990, -1043000), dxfattribs={"layer": "5", "color": 1, "lineweight": 30,
                                                                       "linetype": "DGN Style 2"})
    msp.add_lwpolyline([(-743000, -1043010), (-742990, -1043010), (-742990, -1043000)], close=True,
                       dxfattribs={"layer": "7", "color": 3})
    msp.add_circle((-742950, -1043010), 5, dxfattribs={"layer": "7"})
    msp.add_arc((-742950, -1043030), 4, 30, 150, dxfattribs={"layer": "7"})
    msp.add_point((-742940, -1043040), dxfattribs={"layer": "22"})
    t = msp.add_text("12a", height=1.5, rotation=30, dxfattribs={"layer": "59", "color": 5})
    t.set_placement((-743001, -1043002))
    msp.add_blockref("3.13A", (-742900, -1043000), dxfattribs={"layer": "22", "color": 3})
    msp.add_lwpolyline([(-742800 + i, -1043000 + (i % 2)) for i in range(250)], dxfattribs={"layer": "7"})
    return doc


def test_zapis_a_cteni(tmp_path):
    doc = _vykres()
    s = exportuj(doc, doc.modelspace(), tmp_path / "v.dgn")
    assert s.prvky["buňka"] == 1 and s.prvky["kružnice/elipsa"] == 1 and s.prvky["oblouk"] == 1
    assert s.prvky["lomená čára"] == 3  # 250 vrcholů → 3 části po nejvýš 101
    data = (tmp_path / "v.dgn").read_bytes()
    assert len(data) % 512 == 0 and data[1] == 9
    prvky, nezname = nacti_prvky(tmp_path / "v.dgn")
    assert not nezname
    por = {p.typ: p for p in prvky}
    u = next(p for p in prvky if p.typ == 3 and p.hladina == 5)
    assert (u.hladina, u.barva, u.styl) == (5, 3, 2)  # ACI 1 (červená) = barva 3 MicroStationu and u.tloustka > 0
    assert u.geom[1] == [(-743000, -1043000), (-742990, -1043000)]
    assert por[6].geom[2] and por[6].hladina == 7 and por[6].barva == 2
    e = por[15].geom
    assert e[1] == (-742950, -1043010) and abs(e[2] - 5) < 1e-9
    o = por[16].geom
    assert abs(o[5] - 30) < 1e-6 and abs(o[6] - 120) < 1e-6
    t = por[17].geom
    assert t[3] == "12a" and abs(t[4] - 1.5) < 1e-3 and abs(t[6] - 30) < 1e-6 and por[17].hladina == 59
    b = por[2]
    assert b.geom[1] == "3.13A" and (b.geom[2], b.geom[3]) == (-742900, -1043000) and len(b.deti) == 2
    assert {d.typ for d in b.deti} == {15, 3}
    # pro Kontrolu: čísla jako z MicroStationu
    d = read_dgn_v7(tmp_path / "v.dgn")
    f = next(f for f in d.features if f.dxftype == "INSERT")
    assert f.block_name == "3.13A" and f.layer == "Vrstva 22" and f.attributes["MS_BARVA"] == "2"
    assert any(f.zero_length for f in d.features)
    assert load_drawing(tmp_path / "v.dgn").features  # Kontrola otevře DGN V7 sama


def test_cad_otevre_a_ulozi_dgn(tmp_path):
    doc = _vykres()
    exportuj(doc, doc.modelspace(), tmp_path / "a.dgn")
    dok = CadDokument.otevri(tmp_path / "a.dgn")
    typy = sorted(e.dxftype() for e in dok.msp)
    assert typy.count("INSERT") == 1 and "CIRCLE" in typy and "ARC" in typy and "TEXT" in typy
    assert "3.13A" in dok.doc.blocks and len(list(dok.doc.blocks.get("3.13A"))) == 2
    assert dok.ms_barvy and set(dok.ms_barvy.values()) >= {1, 2, 3}
    dok.uloz(tmp_path / "b.dgn", ms_barvy=dok.ms_barvy)
    a, _ = nacti_prvky(tmp_path / "a.dgn")
    b, _ = nacti_prvky(tmp_path / "b.dgn")
    klic = lambda ps: sorted((p.typ, p.hladina, p.barva, p.tloustka, p.styl) for p in ps)  # noqa: E731
    assert klic(a) == klic(b)
    assert dok.path.suffix == ".dgn" and dok.souhrn_dgn is not None


@pytest.mark.skipif(not (POD / "ucitel-dalsi" / "UGEO.DGN").exists(), reason="podklady nejsou k dispozici")
def test_sablona_od_ucitele(tmp_path):
    """UGEO.DGN (prázdný výkres V7 z MicroStationu) se otevře a jde použít jako šablona."""
    assert load_drawing(POD / "ucitel-dalsi" / "UGEO.DGN").features == []
    doc = _vykres()
    exportuj(doc, doc.modelspace(), tmp_path / "s.dgn", seed=POD / "ucitel-dalsi" / "UGEO.DGN")
    prvky, _ = nacti_prvky(tmp_path / "s.dgn")
    assert len(prvky) == 10


@pytest.mark.skipif(not (POD / "zadani1-microstation" / "Vcelak_13_navic_opraveno.dxf").exists(),
                    reason="podklady nejsou k dispozici")
def test_vykres_ze_zadani_do_dgn(tmp_path):
    """DXF z MicroStationu → DGN: hladiny, barvy, tloušťky a styly jako v původním DGN (kromě vlastních
    stylů čar, které DGN V7 neumí – na ty export upozorní)."""
    from kontrola.config import Config
    from kontrola.runner import run_checks
    rs = RuleSet.load(POD / "zadani1-microstation" / "pravidla_zadani1.yaml")
    doc = ezdxf.readfile(POD / "zadani1-microstation" / "Vcelak_13_navic_opraveno.dxf")
    s = exportuj(doc, doc.modelspace(), tmp_path / "v.dgn", rs)
    assert set(s.vlastni_styly) == {"2.103", "2.163"}
    res = run_checks(read_dgn_v7(tmp_path / "v.dgn"), rs, Config(), only=["symbologie"])
    vlastni = {r.nazev for r in rs.pravidla if r.styl_cary and "." in str(r.styl_cary)}
    zbytek = [i.message for i in res.issues if not any(v in i.message for v in vlastni)
              and "Podezdívka plotu" not in i.message]
    assert zbytek == [], zbytek
    orig = load_drawing(POD / "zadani1-microstation" / "Vcelak_13_a0_t0.dgn")
    barvy = lambda d: {(f.layer.split()[-1], f.attributes.get("MS_BARVA")) for f in d.features}  # noqa: E731
    assert barvy(orig) - barvy(read_dgn_v7(tmp_path / "v.dgn")) <= {("11", "0")}


@pytest.mark.skipif(shutil.which("ogr2ogr") is None, reason="GDAL není nainstalovaný")
def test_gdal_cte_stejne(tmp_path):
    doc = _vykres()
    exportuj(doc, doc.modelspace(), tmp_path / "g.dgn")
    subprocess.run(["ogr2ogr", "-f", "GeoJSON", str(tmp_path / "g.json"), str(tmp_path / "g.dgn")], check=True,
                   capture_output=True)
    g = json.loads((tmp_path / "g.json").read_text(encoding="utf-8", errors="replace"))
    gdal = sorted((f["properties"]["Type"], f["properties"]["Level"], f["properties"]["ColorIndex"],
                   f["properties"]["Weight"], f["properties"]["Style"]) for f in g["features"]
                  if f["properties"]["Type"] != 2)
    prvky, _ = nacti_prvky(tmp_path / "g.dgn")
    vse = []
    for p in prvky:
        vse += [p] if p.typ != 2 else p.deti
    assert gdal == sorted((p.typ, p.hladina, p.barva, p.tloustka, p.styl) for p in vse)
    kruh = next(f for f in g["features"] if f["properties"]["Type"] == 15)["geometry"]["coordinates"]
    assert all(abs(math.dist(c, (-742950, -1043010)) - 5) < 1e-6 for c in kruh)
