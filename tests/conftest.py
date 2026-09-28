"""Pomocné funkce pro testy: malé testovací DXF se vytvářejí přímo v testu."""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kontrola.config import Config  # noqa: E402
from kontrola.io import read_dxf  # noqa: E402
from kontrola.rules import RuleSet  # noqa: E402
from kontrola.runner import run_checks  # noqa: E402


@pytest.fixture
def make_dxf(tmp_path):
    """Vrátí funkci, která z callbacku ``build(msp, doc)`` vytvoří a načte DXF."""
    counter = {"n": 0}

    def _make(build, name=None):
        doc = ezdxf.new("R2013", setup=True)
        doc.header["$INSUNITS"] = 6
        msp = doc.modelspace()
        build(msp, doc)
        counter["n"] += 1
        path = tmp_path / (name or f"test{counter['n']}.dxf")
        doc.saveas(path)
        return read_dxf(path)

    return _make


def check(drawing, check_id, rules=None, config=None, **params):
    """Spustí jedinou kontrolu a vrátí seznam chyb."""
    cfg = config or Config()
    cfg.settings(check_id).parametry.update(params)
    res = run_checks(drawing, rules or RuleSet(), cfg, only=[check_id])
    assert not res.cancelled
    for n in res.notes:
        assert "selhala" not in n, n
    return res.issues
