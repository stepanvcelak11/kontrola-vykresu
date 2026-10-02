from pathlib import Path

import pytest

from kontrola.importer.dokument import _doc_text
from kontrola.importer.smernice_objekty import nacti_pravidla, prevod_meritka

DOC = Path(__file__).resolve().parents[1] / "podklady" / "ucitel-dalsi" / "Směrnice-výběr.doc"


@pytest.mark.skipif(not DOC.exists(), reason="chybí Směrnice")
def test_smernice_po_objektech_a_prevod_meritka():
    rs = nacti_pravidla(_doc_text(DOC), 1000)
    assert len(rs.pravidla) >= 30
    plot = next(r for r in rs.pravidla if r.hladina == "8" and r.styl_cary)
    assert "2.123" in plot.styl_cary.split(",") and "4.081" not in plot.styl_cary.split(",")
    strom = next(r for r in rs.pravidla if r.blok == "3.130")
    assert strom.hladina == "12" and strom.barva == 2 and strom.typy_prvku == [2]
    cisla = next(r for r in rs.pravidla if r.hladina == "59")
    assert (cisla.barva, cisla.vyska_textu, cisla.zarovnani) == (86, 1.5, "vlevo nahoře")
    rs500 = prevod_meritka(rs, 1000, 500)
    c500 = next(r for r in rs500.pravidla if r.hladina == "59")
    assert c500.vyska_textu == 0.75 and next(r for r in rs500.pravidla if r.blok == "3.130").meritko_bunky == 0.5
    assert cisla.vyska_textu == 1.5  # původní pravidla se nezměnila
