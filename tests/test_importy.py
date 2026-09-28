"""Další formáty: VFK z katastru (Kokeš), tabulky ODS, binární seznamy souřadnic."""

import zipfile

import pytest

from kontrola.io.dxf_loader import load_drawing
from kontrola.model import GeomType

VFK = """&HVERZE;"5.1"
&HCODEPAGE;"EE8MSWIN1250"
&BSOBR;ID N30;STAV_DAT N2;KATUZE_KOD N6;CISLO_ZPMZ N5;CISLO_TL N4;CISLO_BODU N12;UPLNE_CISLO N12;SOURADNICE_Y N10.2;SOURADNICE_X N10.2;KODCHB_KOD N2
&DSOBR;1;0;610844;130;;1;;743100.00;1043400.00;3
&DSOBR;2;0;610844;130;;2;;743110.00;1043400.00;3
&DSOBR;3;0;610844;130;;3;;743110.00;1043410.00;3
&BSBP;ID N30;STAV_DAT N2;BP_ID N30;PORADOVE_CISLO_BODU N38;OB_ID N30;HP_ID N30;DPM_ID N30
&DSBP;10;0;1;1;;500;
&DSBP;11;0;2;2;;500;
&DSBP;12;0;3;3;;500;
&BHP;ID N30;STAV_DAT N2;TYPPPD_KOD N10;PAR_ID_1 N30;PAR_ID_2 N30
&DHP;500;0;1;900;
&BPAR;ID N30;STAV_DAT N2;KMENOVE_CISLO_PAR N5;PODDELENI_CISLA_PAR N3
&DPAR;900;0;1234;5
&BOBDEBO;ID N30;PAR_ID N30;SOURADNICE_Y N10.2;SOURADNICE_X N10.2;TEXT T20
&DOBDEBO;7;900;743105.00;1043405.00;"x"
&K
"""


def test_vfk_jako_vykres(tmp_path):
    f = tmp_path / "katastr.vfk"
    f.write_bytes(VFK.encode("cp1250"))
    d = load_drawing(f)
    body = [x for x in d.features if x.geom_type == GeomType.BOD]
    lines = [x for x in d.features if x.geom_type == GeomType.LINIE]
    texts = [x for x in d.features if x.geom_type == GeomType.TEXT]
    assert len(body) == 3 and body[0].geometry.x == -743100.0 and body[0].geometry.y == -1043400.0
    assert len(lines) == 1 and len(lines[0].geometry.coords) == 3 and lines[0].layer == "KN-hranice parcel"
    assert texts[0].text == "1234/5"


def test_ods_tabulka(tmp_path):
    from kontrola.importer.table import read_table
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"')
    cell = lambda t: f'<table:table-cell><text:p>{t}</text:p></table:table-cell>'  # noqa: E731
    rows = [["Kód", "Vrstva", "Barva"], ["101", "BUDOVY", "3"]]
    body = "".join("<table:table-row>" + "".join(cell(c) for c in r) + "</table:table-row>" for r in rows)
    xml = (f'<?xml version="1.0"?><office:document-content {ns}><office:body><office:spreadsheet>'
           f'<table:table table:name="Směrnice">{body}<table:table-row table:number-rows-repeated="1000">'
           f'<table:table-cell table:number-columns-repeated="1024"/></table:table-row></table:table>'
           f'</office:spreadsheet></office:body></office:document-content>')
    f = tmp_path / "smernice.ods"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("content.xml", xml)
    t = read_table(f)
    assert t.sheet == "Směrnice" and t.rows == rows


def test_binarni_seznam_srozumitelna_chyba(tmp_path):
    from kontrola.checks.seznam import read_point_list
    f = tmp_path / "body.ss"
    f.write_bytes(b"GEPRO\x00\x01\x02" * 50)
    with pytest.raises(ValueError, match="binární"):
        read_point_list(f)
