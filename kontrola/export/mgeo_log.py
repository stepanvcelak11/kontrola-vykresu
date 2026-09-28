"""Protokol ve formátu programu „Kontrola a změna symbologie“ (GISoft/MGEO).

Učitel kontroluje výkresy tímto programem a vrací protokol ``*.log``. Tento export vytvoří
protokol ve stejné podobě: chybné prvky jsou seskupené podle kombinace atributů a chybný
atribut je označen „(!)“. Za atributovou částí následuje přehled topologických chyb
(obdoba protokolu kontroly čárové kresby MGEO).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, OrderedDict
from pathlib import Path

from ..checks.base import Issue, fmt_num
from ..model import Drawing, Feature, GeomType
from ..rules import MS_ELEMENT_NAMES, RuleSet, feature_element_type, layer_number

ATTR_CHECKS = ("symbologie", "typ_geometrie", "atribut_dle_vrstvy", "nepovolene_hladiny", "nekodovane",
               "jednotnost_hladiny")
_HNAME = {0: "Vlevo", 1: "Střed", 2: "Vpravo"}
_VNAME = {0: "účaří", 1: "dole", 2: "uprostřed", 3: "nahoře"}


def _wrong_fields(msg: str, check_id: str) -> set[str]:
    m = msg.lower()
    out = set()
    if check_id in ("nepovolene_hladiny", "nekodovane") or "hladina " in m or "hladině" in m:
        out.add("vrstva")
    if check_id == "typ_geometrie":
        out.add("typ")
    for key, fld in (("barva", "barva"), ("styl", "styl"), ("tloušťka", "tloušťka"), ("výška textu", "výška"),
                     ("šířka textu", "šířka"), ("zarovnání", "zarovnání"), ("font", "font"),
                     ("písmo", "font")):
        if key in m:
            out.add(fld)
    return out


def _attrs(f: Feature, rules: RuleSet) -> "OrderedDict[str, str]":
    a: OrderedDict[str, str] = OrderedDict()
    a["vrstva"] = f.layer
    num = layer_number(f.layer)
    a["číslo"] = str(num) if num is not None else "–"
    t = feature_element_type(f)
    a["typ"] = MS_ELEMENT_NAMES.get(t, f.dxftype) if t is not None else f.dxftype
    a["barva"] = rules.describe_feature_color(f)
    a["styl"] = f.linetype or "CONTINUOUS"
    a["tloušťka"] = fmt_num(f.lineweight, 2)
    if f.geom_type == GeomType.TEXT:
        a["font"] = f.font or "–"
        a["výška"] = fmt_num(f.text_height, 2)
        a["šířka"] = fmt_num(f.text_height * (f.width_factor or 1.0), 2)
        a["zarovnání"] = f"{_HNAME.get(f.halign, '?')} {_VNAME.get(f.valign, '?')}"
    if f.block_name:
        a["buňka"] = f.block_name
    return a


def _fmt(label: str, key: str, attrs, wrong: set[str]) -> str:
    return f"{label}{'(!)' if key in wrong else ''}: {attrs[key]}"


def export_mgeo_log(drawing: Drawing, rules: RuleSet, issues: list[Issue], path: str | Path,
                    rules_name: str = "", scale: str = "", tolerance: float | None = None) -> Path:
    by_id = drawing.by_id()
    wrong_by_feature: dict[int, set[str]] = {}
    for iss in issues:
        if iss.check_id not in ATTR_CHECKS or iss.state == "ignorovat":
            continue
        fids = iss.feature_ids if iss.check_id == "nepovolene_hladiny" else iss.feature_ids[:1]
        for fid in fids:
            wrong_by_feature.setdefault(fid, set()).update(_wrong_fields(iss.message, iss.check_id))
    groups: Counter = Counter()
    samples: dict[tuple, tuple] = {}
    for fid, wrong in wrong_by_feature.items():
        f = by_id.get(fid)
        if f is None:
            continue
        a = _attrs(f, rules)
        key = (tuple(a.items()), frozenset(wrong))
        groups[key] += 1
        samples[key] = (a, wrong)

    now = dt.datetime.now().strftime("%d.%m.%Y  %H:%M:%S")
    L = []
    L.append("Zpracováno programem 'Kontrola výkresu' (obdoba protokolu 'Kontrola a změna symbologie' GISoft)")
    L.append("")
    L.append("Podmínky zpracování")
    L.append("-------------------")
    L.append("Režim zpracování:               Kontrola symbologie")
    L.append(f"Výkres:                         {drawing.source_path or drawing.path}")
    L.append(f"Soubor pravidel:                {rules_name or '(pravidla projektu)'}  ({len(rules.pravidla)} pravidel)")
    if scale:
        L.append(f"Měřítko výkresu:                {scale}")
    if tolerance is not None:
        L.append(f"Přesnost porovnání:             {fmt_num(tolerance, 3)}")
    L.append("")
    L.append("Výsledky zpracování")
    L.append("-------------------")
    L.append("")
    total = sum(groups.values())
    L.append(f"Ve výkresu bylo nalezeno {len(groups)} typů chyb - celkem {total} prvků.")
    L.append("")
    L.append("Počet výskytů a atributy chybných prvků")
    L.append("---------------------------------------")
    for key, n in sorted(groups.items(), key=lambda kv: (layer_number(dict(kv[0][0])["vrstva"]) or 9999,
                                                          dict(kv[0][0])["vrstva"], -kv[1])):
        a, wrong = samples[key]
        first = (f"{n:<6} Název vrstvy: {a['vrstva']}, {_fmt('Číslo vrstvy', 'číslo', a, wrong | ({'číslo'} if 'vrstva' in wrong else set()))}, "
                 f"{_fmt('Typ prvku', 'typ', a, wrong)}")
        L.append(first)
        L.append("       " + ", ".join([_fmt("Barva", "barva", a, wrong), _fmt("Styl", "styl", a, wrong),
                                        _fmt("Tloušťka", "tloušťka", a, wrong)]))
        if "font" in a:
            L.append("       " + ", ".join([_fmt("Font", "font", a, wrong), _fmt("Výška", "výška", a, wrong),
                                            _fmt("Šířka", "šířka", a, wrong)]))
            L.append("       " + _fmt("Zarovnání", "zarovnání", a, wrong))
        if "buňka" in a:
            L.append(f"       Buňka: {a['buňka']}")
    L.append("-" * 96)
    L.append(f"Celkem chyb: {total}")
    L.append("")

    # topologie (obdoba protokolu MGEO)
    topo = Counter(i.check_id for i in issues if i.check_id not in ATTR_CHECKS and i.state != "ignorovat")
    msgs = Counter(i.message.split(",")[0] for i in issues if i.check_id == "pruseciky_bez_uzlu")
    L.append("Topologická kontrola")
    L.append("----------------------------------------------------------")
    L.append(f"Počet duplicitních čar            : {topo.get('duplicity', 0)}")
    L.append(f"Počet nedotažení / přetažení      : {topo.get('chybejici_napojeni', 0)}")
    L.append(f"Počet nerozdělených čar v uzlu    : {msgs.get('Linie nejsou v uzlu rozdělené', 0)}")
    L.append(f"Počet průsečíků bez uzlu          : {sum(v for k, v in msgs.items() if k != 'Linie nejsou v uzlu rozdělené')}")
    L.append(f"Počet volných konců čar           : {topo.get('visici_konce', 0)}")
    L.append(f"Počet krátkých a nulových čar     : {topo.get('kratke_linie', 0) + topo.get('nulova_delka', 0)}")
    others = sum(v for k, v in topo.items() if k not in ("duplicity", "chybejici_napojeni", "pruseciky_bez_uzlu",
                                                         "visici_konce", "kratke_linie", "nulova_delka"))
    L.append(f"Počet ostatních chyb              : {others}")
    L.append("----------------------------------------------------------")
    L.append(f"Datum zpracování: {now}")
    L.append("")
    L.append("Pozn.: volné konce čar na okrajích výkresu a nedělené čáry v T-spojení se nepočítají.")
    path = Path(path)
    path.write_text("\r\n".join(L) + "\r\n", encoding="utf-8-sig")
    return path
