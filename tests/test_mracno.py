"""Mračna bodů: XYZ, LAS, PLY, prořídnutí a výběr terénu."""

import struct

import numpy as np
import pytest

from kontrola.geodezie import mracno as M


def _terén_a_strom():
    rng = np.random.default_rng(1)
    xy = rng.uniform(0, 20, size=(4000, 2))
    z = 250 + 0.1 * xy[:, 0]
    strom = (np.hypot(xy[:, 0] - 10, xy[:, 1] - 10) < 2) & (rng.uniform(size=4000) < 0.7)
    z = np.where(strom, z + rng.uniform(2, 6, size=4000), z)
    return np.column_stack([xy, z]), strom


def _las(path, body, trida=None, fmt=1):
    n = len(body)
    delka = {0: 20, 1: 28, 6: 30}[fmt]
    h = bytearray(227)
    h[0:4] = b"LASF"
    h[24], h[25] = 1, 2
    struct.pack_into("<H", h, 94, 227)
    struct.pack_into("<I", h, 96, 227)
    h[104] = fmt
    struct.pack_into("<H", h, 105, delka)
    struct.pack_into("<I", h, 107, n)
    struct.pack_into("<3d", h, 131, 0.001, 0.001, 0.001)
    struct.pack_into("<3d", h, 155, -600000.0, -1160000.0, 0.0)
    zaz = bytearray()
    for i, (x, y, z) in enumerate(body):
        r = bytearray(delka)
        struct.pack_into("<3i", r, 0, round((x + 600000) / 0.001), round((y + 1160000) / 0.001), round(z / 0.001))
        r[16 if fmt >= 6 else 15] = int(trida[i]) if trida is not None else 1
        zaz += r
    path.write_bytes(bytes(h) + bytes(zaz))


def test_xyz_ply_las(tmp_path):
    (tmp_path / "a.xyz").write_text("595975.72 1158246.97 258.27\n1 595976,0;1158247,0;258,5\nhlava\n", encoding="utf-8")
    m = M.nacti(tmp_path / "a.xyz")
    assert len(m) == 2 and m.body[1].tolist() == [595976.0, 1158247.0, 258.5]
    assert m.do_vykresu()[0, 0] == -595975.72  # kladné S-JTSK → výkres
    (tmp_path / "b.ply").write_text("ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nproperty float y\n"
                                    "property float z\nproperty uchar red\nend_header\n1 2 3 255\n4 5 6 0\n")
    assert M.nacti(tmp_path / "b.ply").body.tolist() == [[1, 2, 3], [4, 5, 6]]
    dt = np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f4")])
    arr = np.array([(1.5, 2.5, 3.0), (4.0, 5.0, 6.5)], dtype=dt)
    (tmp_path / "c.ply").write_bytes(b"ply\nformat binary_little_endian 1.0\nelement vertex 2\nproperty double x\n"
                                     b"property double y\nproperty float z\nend_header\n" + arr.tobytes())
    assert M.nacti(tmp_path / "c.ply").body.tolist() == [[1.5, 2.5, 3.0], [4.0, 5.0, 6.5]]
    body = [(-600010.0, -1160020.0, 250.5), (-600011.5, -1160021.0, 251.25)]
    for fmt in (1, 6):
        _las(tmp_path / f"d{fmt}.las", body, [2, 5], fmt)
        m = M.nacti(tmp_path / f"d{fmt}.las")
        assert np.allclose(m.body, body) and m.trida.tolist() == [2, 5]
        assert np.allclose(m.do_vykresu(), body)  # záporné EPSG:5514 zůstanou
    (tmp_path / "e.laz").write_bytes(b"LASF")
    with pytest.raises(ValueError, match="LAZ"):
        M.nacti(tmp_path / "e.laz")


def test_proridnuti_a_teren(tmp_path):
    body, strom = _terén_a_strom()
    m = M.Mracno(body)
    p = M.prorid(m, 1.0, "stred")
    assert 350 <= len(p) <= 400  # 20 × 20 buněk
    t = M.teren(m, 1.0, 0.5)
    # žádný bod koruny stromu nezůstane, terén ano
    assert np.all(t.body[:, 2] - (250 + 0.1 * t.body[:, 0]) < 0.5) and len(t) > 300
    _las(tmp_path / "k.las", body[:500], np.where(strom[:500], 5, 2))
    tk = M.teren(M.nacti(tmp_path / "k.las"), 1.0)
    assert np.all(tk.body[:, 2] - (250 + 0.1 * tk.body[:, 0]) < 2e-3)  # klasifikace terénu z LAS
    assert "bodů" in M.souhrn(m)
