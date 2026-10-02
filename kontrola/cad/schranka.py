"""Schránka CAD (Ctrl+C / Ctrl+V) – kopírování prvků mezi výkresy jako v MicroStationu.

Prvky se zkopírují do pomocného DXF dokumentu i s hladinami, styly čar, textovými styly a buňkami
(bloky), takže schránka platí, i když se původní výkres zavře. Vkládají se na stejné souřadnice
(shodně se světem), nebo s posunem.
"""

from __future__ import annotations

import ezdxf
from ezdxf.addons import Importer
from ezdxf.math import Matrix44

_schranka = {"doc": None, "pocet": 0}


def kopiruj(doc, ents) -> int:
    """Uloží prvky do schránky. Vrací počet zkopírovaných prvků."""
    ents = [e for e in ents if e.dxf.owner is not None]
    if not ents:
        raise ValueError("Nic není vybráno.")
    cil = ezdxf.new(doc.dxfversion if doc.dxfversion >= "AC1015" else "R2000")
    imp = Importer(doc, cil)
    imp.import_entities(ents, cil.modelspace())
    imp.finalize()
    _schranka["doc"] = cil
    _schranka["pocet"] = len(cil.modelspace())
    return _schranka["pocet"]


def je_plna() -> bool:
    return _schranka["doc"] is not None and _schranka["pocet"] > 0


def vloz(doc, layout, historie, dx: float = 0.0, dy: float = 0.0) -> list:
    """Vloží obsah schránky do výkresu (jedna operace pro Zpět). Vrací nové prvky."""
    zdroj = _schranka["doc"]
    if zdroj is None or not _schranka["pocet"]:
        raise ValueError("Schránka je prázdná – nejdřív vyberte prvky a zkopírujte je (Ctrl+C).")
    pred = {id(e) for e in layout}
    imp = Importer(zdroj, doc)
    imp.import_entities(list(zdroj.modelspace()), layout)
    imp.finalize()
    nove = [e for e in layout if id(e) not in pred]
    if dx or dy:
        m = Matrix44.translate(dx, dy, 0)
        for e in nove:
            e.transform(m)
    if historie is not None and nove:
        historie.proved(f"Vložení ze schránky ({len(nove)})", nove)
    return nove
