"""Mutační testy kontroly symbologie na skutečných výkresech od učitele.

U prvku, který je správně, se schválně změní jedna vlastnost (barva, styl, tloušťka, hladina,
buňka, měřítko buňky, výška textu) a kontrola ji musí nahlásit – a na nezměněném výkresu nesmí
hlásit nic navíc.
"""

import copy
from pathlib import Path

import ezdxf
import pytest

from kontrola.checks.base import CheckContext
from kontrola.config import Config
from kontrola.io.dxf_loader import load_drawing
from kontrola.model import GeomType
from kontrola.rules import RuleSet
from kontrola.runner import run_checks

POD = Path(__file__).resolve().parents[1] / "podklady"
DGN1 = POD / "zadani1-microstation" / "Vcelak_13_a0_t0.dgn"
DXF1 = POD / "zadani1-microstation" / "Vcelak_13_navic_opraveno.dxf"
PRAV1 = POD / "zadani1-microstation" / "pravidla_zadani1.yaml"
DXF2 = POD / "zadani2-husovice" / "Husovice_Včelák_mapa.dxf"
PRAV2 = POD / "zadani2-husovice" / "pravidla_zadani2.yaml"

pytestmark = pytest.mark.skipif(not (DGN1.exists() and PRAV1.exists()), reason="podklady nejsou k dispozici")


def _symb(d, rs, only=("symbologie",)):
    return run_checks(d, rs, Config(), only=list(only)).issues


def _nove(d, rs, f, zmena, only=("symbologie",)):
    d2 = copy.copy(d)
    d2.features = list(d.features)
    g = copy.deepcopy(f)
    zmena(g)
    d2.features[d.features.index(f)] = g
    return [i for i in _symb(d2, rs, only) if f.fid in i.feature_ids]


@pytest.fixture(scope="module")
def zadani1():
    d = load_drawing(DGN1)
    rs = RuleSet.load(PRAV1)
    return d, rs, CheckContext(d, rs, Config(), {}, None, None)


def test_spravny_vykres_bez_chyb(zadani1):
    d, rs, _ = zadani1
    assert _symb(d, rs) == []


def test_kazda_zmena_se_odhali(zadani1):
    d, rs, ctx = zadani1
    zkouseno = set()
    for f in d.features:
        r = ctx.rule_for(f)
        if r is None:
            continue
        zmeny = []
        if isinstance(r.barva, int):
            zmeny.append(("barva", lambda g, b=(r.barva + 3) % 64 or 5: g.attributes.__setitem__("MS_BARVA", str(b))))
        if r.tloustka is not None and f.geom_type != GeomType.TEXT:
            zmeny.append(("tloušťka", lambda g: g.attributes.__setitem__("MS_TLOUSTKA", "9")))
        if r.hladina:
            zmeny.append(("vrstva", lambda g: setattr(g, "layer", "Vrstva 63")))
        if f.dxftype == "INSERT" and r.blok:
            zmeny.append(("buňka", lambda g: setattr(g, "block_name", "NEEXISTUJE")))
        if f.dxftype == "INSERT" and r.meritko_bunky:
            zmeny.append(("měřítko buňky", lambda g: setattr(g, "scale", (g.scale[0] * 2, g.scale[1] * 2))))
        if f.geom_type == GeomType.TEXT and r.vyska_textu:
            zmeny.append(("výška textu", lambda g: setattr(g, "text_height", g.text_height * 1.6)))
        for co, zmena in zmeny:
            if co in zkouseno:
                continue
            # neznámou hladinu hlásí kontrola nepovolených hladin (prvek pak nemá pravidlo)
            nalez = _nove(d, rs, f, zmena, ("symbologie", "nepovolene_hladiny"))
            ok = any(co in i.message or (co == "vrstva" and i.check_id == "nepovolene_hladiny") for i in nalez)
            assert ok, (co, f.layer, f.block_name, [i.message for i in nalez])
            zkouseno.add(co)
    assert zkouseno >= {"barva", "tloušťka", "vrstva", "buňka", "měřítko buňky", "výška textu"}


def test_spatna_bunka_vypise_povolene(zadani1):
    d, rs, ctx = zadani1
    f = next(f for f in d.features if f.dxftype == "INSERT" and (ctx.rule_for(f) or rs).blok)
    nalez = _nove(d, rs, f, lambda g: setattr(g, "block_name", "XYZ"))
    assert "buňka XYZ (má být" in nalez[0].message
    assert nalez[0].label().endswith("buňka")


def test_barva_dle_hladiny_z_dgn_nehlasi_spatnou_barvu(zadani1):
    """V DGN se barva hladiny nečte – ByLevel hlásí jen „Atribut dle vrstvy“, ne smyšlenou barvu."""
    d, rs, _ = zadani1
    d2 = copy.copy(d)
    d2.features = [copy.deepcopy(f) for f in d.features]
    for g in d2.features:
        if "MS_BARVA" in g.attributes:
            del g.attributes["MS_BARVA"]
            g.bylayer = frozenset({"barva"})
            g.color_rgb = (200, 200, 200)
    res = run_checks(d2, rs, Config(), only=["symbologie", "atribut_dle_vrstvy"])
    # bez barvy se prvek může přiřadit k jinému pravidlu téže hladiny, ale barvu si kontrola nevymýšlí
    assert not [i for i in res.issues if i.check_id == "symbologie" and "barva" in i.message]
    assert len([i for i in res.issues if i.check_id == "atribut_dle_vrstvy"]) == len(d2.features)
    assert any("dle hladiny" in n for n in res.notes)


@pytest.mark.skipif(not DXF2.exists(), reason="podklady nejsou k dispozici")
def test_tloustka_se_hlasi_i_u_neulozeneho_stylu(tmp_path):
    """Zábradlí: uživatelský styl se do DXF neuložil – i tak se musí ohlásit špatná tloušťka."""
    rs = RuleSet.load(PRAV2)
    d = load_drawing(DXF2)
    pred = [i for i in _symb(d, rs) if "Zábradlí" in i.message]
    assert pred and "neuložil" in pred[0].message
    h = pred[0].handles[0]
    doc = ezdxf.readfile(DXF2)
    doc.entitydb[h].dxf.lineweight = 211
    doc.saveas(tmp_path / "t.dxf")
    po = [i for i in _symb(load_drawing(tmp_path / "t.dxf"), rs) if h in i.handles]
    assert po and "tloušťka" in po[0].message and "ověřte v DGN" in po[0].message


@pytest.mark.skipif(not DXF1.exists(), reason="podklady nejsou k dispozici")
@pytest.mark.parametrize("co", ["barva", "barva ByLayer", "vrstva", "tloušťka"])
def test_zmena_primo_v_dxf(tmp_path, co):
    """Změna zapsaná do souboru DXF a znovu načtená (ověří i čtení, nejen kontrolu)."""
    rs = RuleSet.load(PRAV1)
    d = load_drawing(DXF1)
    ctx = CheckContext(d, rs, Config(), {}, None, None)
    zaklad = {(i.handles[0] if i.handles else "", i.message) for i in _symb(d, rs)}
    f = next(f for f in d.features if f.dxftype == "LWPOLYLINE" and f.handle and ctx.rule_for(f) is not None
             and ctx.rule_for(f).tloustka is not None and ctx.rule_for(f).barva is not None)
    doc = ezdxf.readfile(DXF1)
    e = doc.entitydb[f.handle]
    if co == "barva":
        e.dxf.color = 140
    elif co == "barva ByLayer":
        e.dxf.color = 256
        doc.layers.get(e.dxf.layer).color = 141
    elif co == "vrstva":
        e.dxf.layer = "SPATNA"
    else:
        e.dxf.lineweight = 211
    doc.saveas(tmp_path / "t.dxf")
    po = [i for i in _symb(load_drawing(tmp_path / "t.dxf"), rs, ("symbologie", "nepovolene_hladiny"))
          if f.handle in i.handles and (f.handle, i.message) not in zaklad]
    assert any(co.split()[0] in i.message or (co == "vrstva" and i.check_id == "nepovolene_hladiny")
               for i in po), [i.message for i in po]
