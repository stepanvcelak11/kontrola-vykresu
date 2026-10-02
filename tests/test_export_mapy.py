import json

import ezdxf
import pytest

from kontrola.geodezie import export_mapy as E
from kontrola.geodezie import sjtsk
from kontrola.geodezie.body import Bod


def _body():
    return [Bod("1", 743011.771, 1043823.163, 251.25, kod="plot"), Bod("2", 743021.771, 1043823.163)]


def test_dxf_shodne_se_svetem(tmp_path):
    b = _body()
    E.do_dxf(tmp_path / "s.dxf", b, [(b[0], b[1])])
    doc = ezdxf.readfile(tmp_path / "s.dxf")
    msp = doc.modelspace()
    pts = list(msp.query("POINT"))
    assert (pts[0].dxf.location.x, pts[0].dxf.location.y, pts[0].dxf.location.z) == pytest.approx(
        (-743011.771, -1043823.163, 251.25))
    texty = {t.dxf.layer: t.dxf.text for t in msp.query("TEXT") if t.dxf.text in ("1", "251.25", "plot")}
    assert texty == {"CISLA": "1", "VYSKY": "251.25", "KODY": "plot"}
    assert len(msp.query("LINE")) == 1


def test_kml_a_geojson(tmp_path):
    b = _body()
    E.do_kml(tmp_path / "s.kml", b, [(b[0], b[1])])
    t = (tmp_path / "s.kml").read_text(encoding="utf-8")
    assert "<name>1</name>" in t and "LineString" in t
    E.do_geojson(tmp_path / "s.geojson", b)
    d = json.loads((tmp_path / "s.geojson").read_text(encoding="utf-8"))
    lo, la = d["features"][0]["geometry"]["coordinates"]
    y, x, _ = sjtsk.wgs84_na_sjtsk(la, lo, parametry=sjtsk.HELMERT_PROJ4)
    assert abs(y - 743011.771) < 0.002 and abs(x - 1043823.163) < 0.002  # zpět do S-JTSK (stejný převod jako QTrig)
    assert d["features"][0]["properties"]["kod"] == "plot"
