"""CAD podle zadání: výkres nakreslený s předvolbami z pravidel učitele projde kontrolou symbologie."""

from pathlib import Path

import pytest

from kontrola.cad import upravy as U
from kontrola.cad.zadani import novy_dokument, predvolby
from kontrola.config import Config
from kontrola.io.dxf_loader import load_drawing
from kontrola.rules import RuleSet
from kontrola.runner import run_checks

P = Path(__file__).resolve().parents[1] / "podklady"
SOUBORY = [P / "zadani1-microstation" / "pravidla_zadani1.yaml", P / "zadani2-husovice" / "pravidla_zadani2.yaml"]


@pytest.mark.parametrize("soubor", SOUBORY, ids=lambda p: p.parent.name)
def test_vykres_podle_predvoleb_projde_symbologii(soubor, tmp_path):
    if not soubor.exists():
        pytest.skip("chybí pravidla")
    rs = RuleSet.load(soubor)
    dok, zprava = novy_dokument(rs)
    assert any("Vrstvy" in z for z in zprava)
    h = U.Historie(dok.msp)
    k = U.Kresleni(dok.msp, h)
    pv = predvolby(rs)
    assert len(pv) == len(rs.pravidla)
    nakresleno = 0
    for i, p in enumerate(pv):
        if p.blok:
            continue  # buňky potřebují definici ze vzorového výkresu
        k.nastav_predvolbu(p)
        x0, y0 = -600000.0 - i * 40, -1160000.0
        if p.geometrie == "text":
            k.text((x0, y0), "123", p.vyska or 1.0)
        elif p.geometrie == "bod":
            k.bod((x0, y0))
        elif p.geometrie == "polygon":
            k.polylinie([(x0, y0), (x0 + 10, y0), (x0 + 10, y0 + 10), (x0, y0 + 10)], uzavrena=True)
        else:
            k.usecka((x0, y0), (x0 + 10, y0 + 3))
        nakresleno += 1
    assert nakresleno > 10
    f = dok.uloz(tmp_path / "podle_zadani.dxf")
    drawing = load_drawing(f)
    res = run_checks(drawing, rs, Config(), only=["symbologie"])
    chyby = [i for i in res.issues if i.check_id == "symbologie"] if hasattr(res.issues[0] if res.issues else None,
                                                                         "check_id") else list(res.issues)
    assert not chyby, "\n".join(str(getattr(i, "zprava", i))[:200] for i in chyby[:10])


def test_bunky_ze_vzoroveho_vykresu_a_keyin(tmp_path):
    import ezdxf
    from kontrola.cad.zadani import keyin, prevezmi_bloky
    src = ezdxf.new("R2000")
    b = src.blocks.new("3.13")
    b.add_circle((0, 0), 0.5)
    src.modelspace().add_blockref("3.13", (1, 1))
    f = tmp_path / "vzor.dxf"
    src.saveas(f)
    dok, _ = novy_dokument(RuleSet.load(SOUBORY[0]) if SOUBORY[0].exists() else RuleSet())
    assert prevezmi_bloky(dok.doc, [f]) == ["3.13"]
    assert "3.13" in dok.doc.blocks and prevezmi_bloky(dok.doc, [f]) == []  # podruhé už nic
    if SOUBORY[0].exists():
        pv = {p.nazev: p for p in predvolby(RuleSet.load(SOUBORY[0]))}
        assert keyin(pv["Budovy zděné, betonové"]) == "lv=5;co=94;lc=0;wt=0"
        assert keyin(pv["Strom nerozlišený"]).endswith("ac=3.13")


def test_styly_car_a_textu_ze_vzoru_jako_microstation(tmp_path):
    from kontrola.cad.symbologie import styl_na_typ, typ_na_styl
    from kontrola.cad.zadani import nacti_lin, prevezmi_styly
    vzor = P / "zadani1-microstation" / "Vcelak_13_navic.dxf"
    if not vzor.exists() or not SOUBORY[0].exists():
        pytest.skip("chybí podklady")
    rs = RuleSet.load(SOUBORY[0])
    dok, zprava = novy_dokument(rs, [vzor])
    lt = dok.doc.linetypes
    # ploty převzaté ze vzoru se skutečným vzorem a popisem (ne přibližné)
    assert "2.103" in lt and "Dreveny plot" in lt.get("2.103").dxf.description
    assert any("převzaty" in z for z in zprava)
    pv = {p.nazev: p for p in predvolby(rs)}
    plot = next(p for n, p in pv.items() if "Plot dřevěný" in n)
    assert plot.typ_cary == "2.103"
    # pojmenování jako MicroStation při exportu
    assert styl_na_typ(2) == "DGN Style 2" and typ_na_styl("DGN Style 4") == "4" and typ_na_styl("Continuous") == "0"
    # soubor .lin od učitele
    f = tmp_path / "ploty.lin"
    f.write_text("*2.123,Plot drátěný\nA,1.0,-0.25,0,-0.25\n*2.143,Plot živý\nA,2,-1\n", encoding="cp1250")
    assert set(nacti_lin(f)) == {"2.123", "2.143"}
    d2, _ = novy_dokument(RuleSet())
    assert set(prevezmi_styly(d2.doc, [f])) == {"2.123", "2.143"}
    assert d2.doc.linetypes.get("2.123").dxf.description == "Plot drátěný"


def test_textove_styly_pojmenovane_jako_microstation():
    if not SOUBORY[1].exists():
        pytest.skip("chybí pravidla")
    rs = RuleSet.load(SOUBORY[1])
    dok, _ = novy_dokument(rs)
    jmena = {s.dxf.name: s.dxf.font for s in dok.doc.styles}
    assert jmena.get("Style-Arial Narrow") == "ARIALN.TTF"
    assert jmena.get("Style-Arial Narrow IF") == "ARIALNI.TTF"
    vzor = P / "zadani2-husovice" / "Husovice_Včelák_mapa.dxf"
    if vzor.exists():  # knihovna textových stylů učitele: styl pojmenovaný jako prvek („Popis ploch“)
        dok, _ = novy_dokument(rs, [vzor])
        p = next(p for p in predvolby(rs) if p.nazev.endswith("Popis ploch"))
        from kontrola.cad.zadani import priprav_dokument
        pv = predvolby(rs)
        priprav_dokument(dok.doc, rs, [vzor])
        assert "Popis ploch" in dok.doc.styles


def test_body_ze_seznamu_shodne_se_svetem_a_podle_zadani(tmp_path):
    from kontrola.cad import upravy as U
    from kontrola.cad.body_seznam import vloz_body, vychozi_nastaveni
    from kontrola.geodezie.body import Bod
    if not SOUBORY[0].exists():
        pytest.skip("chybí pravidla")
    rs = RuleSet.load(SOUBORY[0])
    pv = predvolby(rs)
    nast = vychozi_nastaveni(pv)
    assert nast.znacka.vrstva == "58" and nast.cislo.vrstva == "59" and nast.vyska.vrstva == "60"
    dok, _ = novy_dokument(rs)
    h = U.Historie(dok.msp)
    body = [Bod("1000130001", 565501.41, 1187927.40, 245.67), Bod("1000130002", 565492.18, 1187931.27, None)]
    r = vloz_body(dok.msp, h, body, nast, pv)
    assert r["vlozeno"] == 2 and len(h.zpet) == 1  # jedno Zpět pro celý import
    pt = [e for e in dok.msp if e.dxftype() == "POINT"]
    assert len(pt) == 2 and pt[0].dxf.location.isclose((-565501.41, -1187927.40, 0)) and pt[0].dxf.layer == "58"
    texty = {e.dxf.text: e for e in dok.msp.query("TEXT")}
    assert texty["1000130001"].dxf.layer == "59" and texty["245.67"].dxf.layer == "60"
    assert "None" not in texty  # bod bez výšky – výška se nepíše
    # opakovaný import přeskočí body, které už ve výkresu jsou
    assert vloz_body(dok.msp, h, body, nast, pv)["preskoceno"] == 2
    # výkres projde kontrolou symbologie (hladiny, barvy, písmo podle zadání)
    f = dok.uloz(tmp_path / "body.dxf")
    res = run_checks(load_drawing(f), rs, Config(), only=["symbologie", "atribut_dle_vrstvy"])
    assert not res.issues, [i.message for i in res.issues][:5]
    h.krok_zpet()
    assert not list(dok.msp.query("POINT"))


def test_body_s_kodem_bunky(tmp_path):
    from kontrola.cad import upravy as U
    from kontrola.cad.body_seznam import NastaveniBodu, vloz_body
    from kontrola.geodezie.body import Bod
    if not SOUBORY[1].exists():
        pytest.skip("chybí pravidla")
    rs = RuleSet.load(SOUBORY[1])
    pv = predvolby(rs)
    dok, _ = novy_dokument(rs)
    dok.doc.blocks.new("9.12").add_circle((0, 0), 0.3)
    h = U.Historie(dok.msp)
    r = vloz_body(dok.msp, h, [Bod("501", 1000.0, 2000.0, 250.0, "9.12")], NastaveniBodu(), pv)
    ins = list(dok.msp.query("INSERT"))
    assert r["bunky"] == 1 and ins[0].dxf.name == "9.12" and ins[0].dxf.layer == "GS09-výškopis-body podrobné-buňky"
    assert ins[0].dxf.insert.isclose((-1000, -2000, 0))
