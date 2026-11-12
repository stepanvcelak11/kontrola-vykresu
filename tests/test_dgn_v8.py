"""Čtení DGN V8 na výkresu učitele (cvičení Kontrola atributů) a jeho protokolu GISoft."""

from pathlib import Path

import pytest

from kontrola.io.dgn_v8 import read_dgn
ROOT = Path(__file__).resolve().parents[1]
UCITEL = ROOT / "podklady" / "ucitel-geo"


@pytest.mark.skipif(not (UCITEL / "GEO.dgn").exists(), reason="chybí výkres učitele")
def test_ucitel_styly_a_meritko_bunek():
    from collections import Counter
    d = read_dgn(UCITEL / "GEO.dgn")
    styly = {f.linetype for f in d.features}
    assert {"VCHOD", "2.123  PL VP", "4.223 OZ VP"} <= styly  # názvy vlastních stylů i bez čísla
    bunky = Counter((f.block_name, f.scale) for f in d.features if f.dxftype == "INSERT" and f.layer == "Vrstva 27")
    assert bunky[("6.20", (0.5, 0.5))] == 3 and bunky[("3.130", (0.5, 0.5))] == 3  # jako protokol učitele
    assert bunky[("6.20", (1.0, 1.0))] == 40


@pytest.mark.skipif(not (UCITEL / "GEO.log").exists(), reason="chybí protokol učitele")
def test_protokol_ucitele_novy_format():
    from kontrola.protokol_ucitele import read_teacher_log
    p = read_teacher_log(UCITEL / "GEO.log")
    assert p.celkem == 19 and sum(g.pocet for g in p.skupiny) == 19
    assert {(g.vrstva, g.spatne) for g in p.skupiny} >= {("Vrstva 50", frozenset({"vrstva"})),
                                                        ("Vrstva 27", frozenset({"buňka"})),
                                                        ("Vrstva 40", frozenset({"výška", "šířka"}))}


@pytest.mark.skipif(not (UCITEL / "GEO.dgn").exists(), reason="chybí výkres učitele")
def test_pravidla_ze_vzoru_ucitele():
    """Pravidla odvozená z učitelova výkresu a protokolu: kontrola najde jeho chyby, skoro nic navíc."""
    from kontrola.config import Config
    from kontrola.pravidla_ze_vzoru import odvod_pravidla
    from kontrola.protokol_ucitele import compare_with_teacher, read_teacher_log
    from kontrola.runner import run_checks
    d = read_dgn(UCITEL / "GEO.dgn")
    p = read_teacher_log(UCITEL / "GEO.log")
    rs = odvod_pravidla(d, p)
    res = run_checks(d, rs, Config())
    rows, _txt = compare_with_teacher(p, d, rs, res.issues)
    shoda = sum(min(r.ucitel, r.program) for r in rows)
    navic = sum(max(0, r.program - r.ucitel) for r in rows)
    assert shoda >= 15 and navic <= 6  # bez pravidel učitele: shoda 14, navíc přes 1000


HUSOVICE = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"


@pytest.mark.skipif(not (HUSOVICE / "Husovice_Včelák_mapa.dgn").exists(), reason="chybí výkres Husovice")
def test_kurziva_z_dgn_i_dxf():
    """Čísla bodů jsou kurzívou (příznak sklonu v DGN, styl „Arial Narrow IF“ v DXF), výšky ne – kontrola
    řezu písma podle pravidel zadání nehlásí chybu ani u DGN, ani u DXF."""
    from conftest import check

    from kontrola.io import read_dxf
    from kontrola.io.dgn_v8 import read_dgn
    from kontrola.rules import RuleSet, rez_pisma
    rs = RuleSet.load(HUSOVICE / "pravidla_zadani2.yaml")
    for d in (read_dgn(HUSOVICE / "Husovice_Včelák_mapa.dgn"), read_dxf(HUSOVICE / "Husovice_Včelák_mapa.dxf")):
        texty = [f for f in d.features if f.geom_type.name == "TEXT"]
        cisla = [f for f in texty if f.layer == "GS01-body-čísla"]
        vysky = [f for f in texty if "výšky" in f.layer]
        assert cisla and all(rez_pisma(f)[1] for f in cisla)
        assert vysky and not any(rez_pisma(f)[1] for f in vysky)
        assert not [i for i in check(d, "symbologie", rules=rs) if "kurzív" in i.message]


def test_dgn_do_cad_jako_dxf_z_microstationu():
    """Otevření DGN v CAD dá totéž co DXF uložené MicroStationem: oblouky zůstanou oblouky, vyplněné kruhy
    jsou šrafy a buňky mají kresbu přímo z výkresu (stejný rozsah jako v knihovně buněk)."""
    import ezdxf
    from ezdxf import bbox

    from kontrola.cad.dokument import CadDokument
    from kontrola.io.cel import nacti_cel
    slozka = ROOT / "podklady" / "zadani2-husovice"
    d = CadDokument.otevri(slozka / "Husovice_Včelák_mapa.dgn")
    vzor = ezdxf.readfile(slozka / "Husovice_Včelák_mapa.dxf")
    for typ in ("ARC", "HATCH", "INSERT", "TEXT", "POINT", "LINE"):
        assert d.zprava.pocty[typ] == sum(1 for e in vzor.modelspace() if e.dxftype() == typ), typ
    polomery = sorted(round(e.dxf.radius, 3) for e in d.msp if e.dxftype() == "ARC")
    assert polomery == sorted(round(e.dxf.radius, 3) for e in vzor.modelspace() if e.dxftype() == "ARC")
    cel = next((ROOT / "kontrola" / "resources" / "microstation").rglob("MultiScale.cel"))
    knihovna = {b.nazev: b.rozsah() for b in nacti_cel(cel)}
    for jm in ("9.12", "3.13", "6.560", "6.30", "1.07"):
        bb = bbox.extents(d.doc.blocks[jm])
        assert [bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y] == pytest.approx(knihovna[jm], abs=1e-6), jm
    assert not any("značkou bodu" in p for p in d.zprava.poznamky)
    # texty: stejné styly a zarovnání jako v DXF z MicroStationu
    def texty(msp):
        return sorted((e.dxf.layer, e.dxf.text, e.dxf.style, e.dxf.halign, e.dxf.valign) for e in msp
                      if e.dxftype() == "TEXT")
    assert texty(d.msp) == texty(vzor.modelspace())


def test_dgn_krivky_bspline():
    """Křivky (B-spline, typ 27 + póly 21 + uzly 26) se čtou – ve výkresu učitele jich je 112 a nic nezbude."""
    from kontrola.io.dgn_v8 import _bspline, read_dgn
    d = read_dgn(ROOT / "podklady" / "ucitel-geo" / "GEO.dgn")
    assert sum(1 for f in d.features if f.dxftype == "SPLINE") == 112
    assert not any("Nepřečtené" in w for w in d.warnings)
    # Bézierova křivka (4 póly, řád 4): střed = (P0 + 3 P1 + 3 P2 + P3) / 8, konce v krajních pólech
    b = _bspline([(0, 0), (1, 2), (3, 2), (4, 0)], 4, [], 4)
    assert b[0] == (0, 0) and b[-1] == (4, 0) and b[2] == pytest.approx((2.0, 1.5))


def test_dgn_bunky_pro_zobrazeni():
    """Stránka Výkres kreslí buňky z DGN jejich kresbou (strom 3.13 má průměr 2 m v měřítku vložení 1)."""
    d = read_dgn(ROOT / "podklady" / "zadani1-microstation" / "Vcelak_13_a0_t0.dgn")
    bg = d.blocks["3.13"]
    xs = [x for p in bg.paths for x, _y in p]
    assert min(xs) == pytest.approx(-1.0, abs=1e-3) and max(xs) == pytest.approx(1.0, abs=1e-3)
    assert {"6.01A", "6.14A", "8.11"} <= set(d.blocks)


def test_puvodni_dgn_se_neprepise(tmp_path):
    """Výkres otevřený z DGN V8 se ukládá vedle originálu do DXF – původní soubor zůstane bajt po bajtu stejný."""
    import shutil

    from kontrola.cad.dokument import CadDokument
    src = tmp_path / "mapa.dgn"
    shutil.copy(ROOT / "podklady" / "zadani1-microstation" / "Vcelak_13_a0_t0.dgn", src)
    puvodni = src.read_bytes()
    d = CadDokument.otevri(src)
    assert d.zdroj_dgn == src and d.path == tmp_path / "mapa (z DGN).dxf"
    p = d.uloz()
    assert p.suffix == ".dxf" and p.exists() and src.read_bytes() == puvodni
    assert CadDokument.otevri(src).path == tmp_path / "mapa (z DGN 2).dxf"  # dřívější úpravy se také nepřepíšou
    znovu = CadDokument.otevri(p)
    assert znovu.zprava.pocty["INSERT"] == d.zprava.pocty["INSERT"]


def test_kratke_cislo_bodu_ruzne_delky():
    from kontrola.cad.body_seznam import kratke_cislo
    from kontrola.geodezie.body import Bod, SeznamBodu
    assert kratke_cislo("610844000130001") == "1" and kratke_cislo("1000130014") == "14"
    assert kratke_cislo("4001") == "4001" and kratke_cislo("JM-071-519") == "JM-071-519"
    s = SeznamBodu()
    s.pridej([Bod("1000130001", 1.0, 2.0), Bod("1000130014", 3.0, 4.0)], "test")
    assert s.najdi_kratke("14").cislo == "1000130014" and s.najdi_kratke("2") is None
