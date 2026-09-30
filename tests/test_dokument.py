"""Zadání ve Wordu: text, požadavky a popisy vrstev → pravidla."""

import zipfile
from pathlib import Path

import pytest

from kontrola.importer.dokument import layer_rules, read_document, requirements
from kontrola.model import GeomType

DOC = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "Zadání-Microstation.doc"


@pytest.mark.skipif(not DOC.exists(), reason="zadání chybí")
def test_stary_word_doc_vrstvy_58_59_60():
    d = read_document(DOC)
    assert "Vrstva 58" in d.text and "CS WORKING" in d.text
    rules = {r.hladina: r for r in layer_rules(d)}
    assert set(rules) == {"58", "59", "60"}
    assert rules["58"].geometrie == GeomType.BOD and rules["58"].barva == 0 and rules["58"].tloustka == 2
    t = rules["59"]
    assert t.geometrie == GeomType.TEXT and t.barva == 86 and t.font == "CS WORKING"
    assert t.vyska_textu == 0.75 and t.zarovnani == "vlevo nahoře"  # 1,5 m pro 1:1000 → 1:500
    assert layer_rules(d, 500)[1].vyska_textu == 1.5  # pravidla v mm na papíře
    druhy = {q.druh for q in requirements(d)}
    assert {"Měřítko", "Písmo", "Pokyn"} <= druhy


def _docx(path: Path, paras: list[str], table: list[list[str]]):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    p = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paras)
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r) + "</w:tr>"
                   for r in table)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{p}<w:tbl>{rows}</w:tbl></w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def test_docx_text_tabulka_a_pozadavky(tmp_path):
    f = tmp_path / "zadani.docx"
    _docx(f, ["Kresbu proveďte v měřítku 1 : 500.", "Čísla bodů musí být písmem Arial Narrow.",
              "Vrstva 12 – Ploty", "Typy kresebných prvků lomená čára Barva 3 Tloušťka čáry 1"],
          [["Vrstva", "Barva", "Styl"], ["PLOTY", "3", "0"]])
    d = read_document(f)
    assert d.tabulky == [[["Vrstva", "Barva", "Styl"], ["PLOTY", "3", "0"]]]
    reqs = {(q.druh, q.hodnota) for q in requirements(d)}
    assert ("Měřítko", "1:500") in reqs and ("Písmo", "Arial Narrow") in reqs
    (r,) = layer_rules(d)
    assert r.hladina == "12" and r.geometrie == GeomType.LINIE and r.barva == 3 and r.tloustka == 1


GEOGRAF = Path(__file__).resolve().parents[1] / "geograf V1.dxf"


@pytest.mark.skipif(not (GEOGRAF.exists() and DOC.exists()), reason="výkres uživatele chybí")
def test_vykres_geograf_s_wordem():
    """Výkres zadání 1: body na vrstvách 58/59 jsou podle Wordu správně, volné konce nejsou chyba."""
    from kontrola.checks.base import Severity
    from kontrola.config import Config
    from kontrola.io.dxf_loader import load_drawing
    from kontrola.rules import RuleSet
    from kontrola.runner import run_checks
    y = DOC.parent / "pravidla_zadani1.yaml"
    rs = RuleSet.load(y)
    rs.pravidla = [r for r in rs.pravidla if r.hladina not in ("58", "59", "60")]  # jen Excel Směrnice
    d = load_drawing(GEOGRAF)
    before = run_checks(d, rs, Config.load(y)).issues
    assert {i.layer for i in before if i.check_id == "nepovolene_hladiny"} == {"Vrstva 58", "Vrstva 59"}
    rs.pravidla += layer_rules(read_document(DOC), rs.meritko)
    after = run_checks(d, rs, Config.load(y)).issues
    assert not [i for i in after if i.check_id == "nepovolene_hladiny"]
    assert not [i for i in after if i.check_id == "visici_konce" and i.severity == Severity.CHYBA]


def test_body_do_dxf_projdou_kontrolou(tmp_path):
    from collections import Counter

    from kontrola.checks.seznam import read_point_list, verify_points
    from kontrola.config import Config
    from kontrola.export.body_dxf import export_points_dxf, guess_rules
    from kontrola.io.dxf_loader import load_drawing
    from kontrola.rules import RuleSet
    from kontrola.runner import run_checks
    root = Path(__file__).resolve().parents[1] / "podklady"
    for y, lst in (("zadani1-microstation/pravidla_zadani1.yaml", "zadani1-microstation/Body13_tr.txt"),
                   ("zadani2-husovice/pravidla_zadani2.yaml", "zadani2-husovice/Husovice_Včelák_seznam.txt")):
        rs = RuleSet.load(root / y)
        g = guess_rules(rs)
        assert all(g.values()), g
        pts = read_point_list(root / lst)
        out = tmp_path / "body.dxf"
        export_points_dxf(pts, rs, out)
        d = load_drawing(out)
        res = run_checks(d, rs, Config.load(root / y),
                         only=["symbologie", "nepovolene_hladiny", "atribut_dle_vrstvy", "typ_geometrie"])
        assert res.issues == [], [i.message for i in res.issues[:3]]
        r, best, found = verify_points(d, pts)
        assert Counter(x.stav for x in r) == Counter({"ok": len(pts)})
