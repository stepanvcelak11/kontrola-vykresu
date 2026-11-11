"""Pásy karet a textové styly školní pracovní sady MultiScale proti tabulce atributů ÚM od učitele."""

from pathlib import Path

import pytest
import yaml

from kontrola.cad import pracovni_sady as PS
from kontrola.rules import RuleSet

KOREN = Path(__file__).resolve().parents[1]


def test_textove_styly_sady_odpovidaji_tabulce_ucitele():
    """Výška a šířka písma z textových stylů knihovny MultiScale = hodnoty v tabulce „Atributy ÚM“ (zadání 2)."""
    cesta = KOREN / "podklady" / "zadani2-husovice" / "pravidla_zadani2.yaml"
    sada = next((s for s in PS.vsechny() if s.klic == "MultiScale/MultiScale"), None)
    if not cesta.is_file() or sada is None:
        pytest.skip("chybí podklady zadání 2 nebo pracovní sada MultiScale")
    ucitel = RuleSet.from_dict(yaml.safe_load(cesta.read_text(encoding="utf-8")))
    um = PS.pravidla_sady(sada)
    texty_sady = {}
    for r in um.pravidla:
        if r.vyska_textu:
            texty_sady.setdefault(r.hladina, []).append((r.vyska_textu, r.sirka_textu))
    shodne, ruzne = 0, []
    for r in ucitel.pravidla:
        if not r.vyska_textu or r.hladina not in texty_sady:
            continue
        if (r.vyska_textu, r.sirka_textu) in texty_sady[r.hladina]:
            shodne += 1
        else:
            ruzne.append((r.kod, r.hladina, r.vyska_textu, r.sirka_textu, texty_sady[r.hladina]))
    # jediný rozdíl: výškové kóty podrobných bodů (tabulka 0,6 / 0,3 mm, knihovna 1,6 / 1,3 mm)
    assert shodne >= 12 and [x[0] for x in ruzne] == ["9.23"], ruzne


def test_pravidla_sady_barvy_a_hladiny_jako_tabulka_ucitele():
    """Liniové nástroje pásu ÚM mají na hladinách z tabulky učitele stejnou barvu jako tabulka."""
    cesta = KOREN / "podklady" / "zadani2-husovice" / "pravidla_zadani2.yaml"
    sada = next((s for s in PS.vsechny() if s.klic == "MultiScale/MultiScale"), None)
    if not cesta.is_file() or sada is None:
        pytest.skip("chybí podklady zadání 2 nebo pracovní sada MultiScale")
    ucitel = RuleSet.from_dict(yaml.safe_load(cesta.read_text(encoding="utf-8")))
    barvy = {}
    for r in PS.pravidla_sady(sada).pravidla:
        barvy.setdefault(r.hladina, set()).add(str(r.barva))
    spolecne = [r for r in ucitel.pravidla if r.hladina in barvy and r.barva is not None]
    shodne = [r for r in spolecne if set(str(r.barva).split("|")) & barvy[r.hladina]]
    assert len(spolecne) >= 50 and len(shodne) >= 0.9 * len(spolecne), \
        [(r.kod, r.hladina, r.barva, barvy[r.hladina]) for r in spolecne if r not in shodne]


def test_pravidla_sady_povoli_hladiny_knihovny():
    """Hladiny z tabulky učitele, které nemají tlačítko v pásu, jsou v zadání ze sady povolené (ne „není ve Směrnici“)."""
    cesta = KOREN / "podklady" / "zadani2-husovice" / "pravidla_zadani2.yaml"
    sada = next((s for s in PS.vsechny() if s.klic == "MultiScale/MultiScale"), None)
    if not cesta.is_file() or sada is None:
        pytest.skip("chybí podklady zadání 2 nebo pracovní sada MultiScale")
    ucitel = RuleSet.from_dict(yaml.safe_load(cesta.read_text(encoding="utf-8")))
    rs = PS.pravidla_sady(sada)
    zname = {r.hladina for r in rs.pravidla} | set(rs.povolene_hladiny)
    chybi = sorted({r.hladina for r in ucitel.pravidla if r.hladina and r.hladina not in zname})
    assert len(chybi) <= 3, chybi
