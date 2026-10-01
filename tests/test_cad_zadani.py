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
