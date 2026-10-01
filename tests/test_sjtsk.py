"""Převod S-JTSK ↔ WGS84: vlastní implementace proti pyproj (PROJ) se stejnou transformací EPSG:5239."""

import random

import pytest

from kontrola.geodezie import sjtsk as S

# referenční hodnoty z PROJ (pyproj, transformace „S-JTSK to WGS 84 (5)“ = EPSG:5239)
REFERENCE = [
    (598000, 1160000, 49.201998257, 16.609095125),
    (743000, 1044000, 50.078439421, 14.420499103),
    (470000, 1100000, 49.850013682, 18.289074948),
]


def test_pevne_referencni_body():
    for y, x, la, lo in REFERENCE:
        lat, lon, _h = S.sjtsk_na_wgs84(y, x)
        assert abs(lat - la) < 2e-8 and abs(lon - lo) < 2e-8


def _proj():
    pyproj = pytest.importorskip("pyproj")
    g = pyproj.transformer.TransformerGroup("EPSG:5514", "EPSG:4326", always_xy=True)
    return next(t for t in g.transformers if "(5)" in t.description)


def test_krovak_tam_a_zpet_na_mikrometry():
    r = random.Random(1)
    for _ in range(200):
        y, x = r.uniform(430000, 900000), r.uniform(935000, 1230000)
        phi, lam = S.krovak_inv(y, x)
        y2, x2 = S.krovak(phi, lam)
        assert abs(y - y2) < 1e-6 and abs(x - x2) < 1e-6


def test_proti_pyproj_cela_republika():
    t = _proj()
    r = random.Random(2)
    for _ in range(200):
        y, x = r.uniform(430000, 900000), r.uniform(935000, 1230000)
        lon_p, lat_p = t.transform(-y, -x)
        lat, lon, _h = S.sjtsk_na_wgs84(y, x)
        # 1e-8° ≈ 1 mm
        assert abs(lat - lat_p) < 2e-8 and abs(lon - lon_p) < 2e-8, (y, x)


def test_husovice_a_zpet():
    lat, lon, h = S.sjtsk_na_wgs84(595975.72, 1158246.97, 258.0)
    assert 49.21 < lat < 49.23 and 16.62 < lon < 16.65  # Brno-Husovice
    y, x, _ = S.wgs84_na_sjtsk(lat, lon, h)
    assert abs(y - 595975.72) < 0.002 and abs(x - 1158246.97) < 0.002
    assert S.stupne_text(49.2196195, "N", "S").startswith("49°13'")
    assert "mapy.cz" in S.odkaz_mapy_cz(lat, lon)
