"""DXF s novou hladinou KONTROLA_CHYBY (kroužky a texty chyb) pro otevření v MicroStationu."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from ..checks.base import Issue, Severity
from ..model import Drawing

LAYER = "KONTROLA_CHYBY"
ACI = {Severity.CHYBA: 1, Severity.VAROVANI: 30, Severity.INFO: 5}


def export_dxf(drawing: Drawing, issues: list[Issue], path: str | Path, radius: float | None = None,
               text_height: float | None = None, only_new: bool = False):
    """Zkopíruje původní výkres a přidá hladinu KONTROLA_CHYBY s kroužky a popisy.

    Poloměr kroužku a výška textu se odvodí z velikosti výkresu, pokud nejsou zadány.
    Souřadnice se převádějí zpět do jednotek výkresu.
    """
    src = drawing.path
    try:
        doc = ezdxf.readfile(src)
    except Exception:
        from ezdxf import recover
        doc, _ = recover.readfile(src)
    f = drawing.unit_factor or 1.0
    b = drawing.bounds()
    diag = 100.0
    if b is not None:
        diag = max(1.0, ((b[2] - b[0]) ** 2 + (b[3] - b[1]) ** 2) ** 0.5)
    r = radius if radius is not None else min(5.0, max(0.5, diag / 150))
    h = text_height if text_height is not None else r * 0.6
    if LAYER not in doc.layers:
        doc.layers.add(LAYER, color=1)
    msp = doc.modelspace()
    for e in list(msp.query(f'*[layer=="{LAYER}"]')):  # starší kroužky z předchozí kontroly pryč
        msp.delete_entity(e)
    for iss in issues:
        if only_new and iss.state != "nová":
            continue
        x, y = iss.x / f, iss.y / f
        attribs = {"layer": LAYER, "color": ACI[iss.severity]}
        msp.add_circle((x, y), r / f, dxfattribs=attribs)
        label = f"#{iss.number} {iss.message}"
        if iss.state != "nová":
            label += f" [{iss.state}]"
        t = msp.add_text(label, height=h / f, dxfattribs=attribs)
        t.set_placement((x + r / f * 1.1, y + r / f * 0.3))
    doc.saveas(path)
    return path
