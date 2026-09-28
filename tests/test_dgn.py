"""Otevření DGN: rozpoznání verze, DXF uložený vedle DGN, český návod."""

import os
import shutil
import time
from pathlib import Path

import pytest

from kontrola.io import load_drawing
from kontrola.io.dgn import ConversionError, dgn_version

UKAZKY = Path(__file__).resolve().parents[1] / "ukazky"


def test_verze_dgn(tmp_path):
    v8 = tmp_path / "v8.dgn"
    v8.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    v7 = tmp_path / "v7.dgn"
    v7.write_bytes(b"\x08\x09\xfe\x02" + b"\0" * 100)
    assert dgn_version(v8) == "V8"
    assert dgn_version(v7) == "V7"


def test_dgn_bez_prevodu_dava_navod(tmp_path, monkeypatch):
    monkeypatch.setattr("kontrola.io.dgn.find_oda_converter", lambda *a: None)
    dgn = tmp_path / "vykres.dgn"
    dgn.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    with pytest.raises(ConversionError) as e:
        load_drawing(dgn)
    assert "MicroStation V8" in str(e.value) and "Batch Converter" in str(e.value)


def test_dgn_pouzije_dxf_vedle(tmp_path):
    dgn = tmp_path / "vykres.dgn"
    dgn.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    shutil.copy(UKAZKY / "ukazkovy_vykres.dxf", tmp_path / "vykres.dxf")
    d = load_drawing(dgn)
    assert len(d.features) > 10
    assert d.warnings[0].startswith("Použit vykres.dxf")
    # DXF starší než DGN → upozornění
    old = time.time() - 3600
    os.utime(tmp_path / "vykres.dxf", (old, old))
    d = load_drawing(dgn)
    assert "starší" in d.warnings[0]
