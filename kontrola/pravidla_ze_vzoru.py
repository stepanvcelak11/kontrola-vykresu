"""Pravidla symbologie odvozená ze vzorového výkresu (a případně protokolu kontroly od učitele).

Když učitel dá hotový (správný) výkres, ale ne soubor pravidel, dají se pravidla odvodit: pro každou
vrstvu převažující barva, styl a měřítko stylu, tloušťka, povolené typy prvků; pro texty výška,
šířka a písmo; pro buňky jejich názvy, barva a měřítko. Ojedinělé odchylky (méně než ``podil``
prvků vrstvy) se berou jako chyby, ne jako další povolená varianta.

S protokolem učitele (GISoft) je odvození přesnější: hodnoty, které učitel označil „(!)“, se
nikdy nepovolí, a vrstva, kterou označil jako chybnou („Číslo vrstvy(!)“), se z pravidel vynechá.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .model import GeomType
from .rules import Rule, RuleSet, feature_element_type, layer_number


def _ms_barva(f) -> str | None:
    v = f.attributes.get("MS_BARVA")
    return str(v) if v not in (None, "") else (str(f.color_aci) if f.color_aci is not None else None)


def _ms_tloustka(f) -> str | None:
    v = f.attributes.get("MS_TLOUSTKA")
    return str(v) if v not in (None, "") else None


def _vrstva_klic(layer: str) -> str:
    n = layer_number(layer)
    return str(n) if n is not None else layer


def _chybne_hodnoty(prot) -> tuple[dict, set]:
    """Z protokolu učitele: {(vrstva, pole): {hodnoty označené (!)}} a vrstvy, které jsou celé špatně."""
    spatne: dict = defaultdict(set)
    spatne_vrstvy = set()
    if prot is None:
        return spatne, spatne_vrstvy
    vzory = {"barva": r"Barva\(!\)\s*:\s*(\d+)", "styl": r"Styl\(!\)\s*:\s*([^,(]+?)\s*(?:\(|,|$)",
             "buňka": r"N[áa]zev bu[ňn]ky\(!\)\s*:\s*([^,\s]+)", "výška": r"V[ýy][šs]ka\(!\)\s*:\s*([\d.]+)",
             "tloušťka": r"Tlou[šs][ťt]ka\(!\)\s*:\s*(\d+)", "šířka": r"[ŠS][íi][řr]ka\(!\)\s*:\s*([\d.]+)"}
    for g in prot.skupiny:
        v = _vrstva_klic(g.vrstva)
        text = "\n".join(g.radky)
        if re.search(r"(Č|C)[íi]slo vrstvy\(!\)", text, re.IGNORECASE):
            spatne_vrstvy.add(v)
        for pole, rx in vzory.items():
            for m in re.finditer(rx, text, re.IGNORECASE):
                h = m.group(1).strip()
                spatne[(v, pole)].add(h)
        for radek in g.radky:  # „Měřítko(!): 0.5“ – u buňky měřítko buňky, jinak měřítko stylu
            for m in re.finditer(r"M[ěe][řr][íi]tko\(!\)\s*:\s*\(?\s*([\d.]+)", radek, re.IGNORECASE):
                pole = "měřítko buňky" if re.search(r"bu[ňn]k", radek, re.IGNORECASE) else "měřítko stylu"
                spatne[(v, pole)].add(str(round(float(m.group(1)), 4)))
    return spatne, spatne_vrstvy


def _prevazujici(hodnoty: list, podil: float, zakazane: set) -> list:
    """Hodnoty, které tvoří aspoň ``podil`` výskytů (nejčastější vždy, pokud není zakázaná)."""
    c = Counter(h for h in hodnoty if h is not None)
    if not c:
        return []
    n = sum(c.values())
    out = [h for h, k in c.most_common() if str(h) not in zakazane and (k / n >= podil)]
    if not out:
        out = [h for h, _k in c.most_common() if str(h) not in zakazane][:1]
    return out


def odvod_pravidla(drawing, prot=None, podil: float | None = None) -> RuleSet:
    """Pravidla symbologie ze vzorového výkresu (a volitelně protokolu učitele).

    Bez protokolu se povolí jen převažující hodnoty (aspoň 15 % prvků vrstvy). S protokolem učitele
    platí, že každý prvek, který v protokolu není, je správně – povolí se všechny hodnoty kromě
    označených „(!)“."""
    if podil is None:
        podil = 0.0 if prot is not None else 0.15
    spatne, spatne_vrstvy = _chybne_hodnoty(prot)
    po_vrstvach: dict[str, list] = defaultdict(list)
    for f in drawing.features:
        po_vrstvach[f.layer].append(f)
    pravidla: list[Rule] = []
    for layer, feats in sorted(po_vrstvach.items(), key=lambda kv: (layer_number(kv[0]) or 9999, kv[0])):
        v = _vrstva_klic(layer)
        if v in spatne_vrstvy and len(feats) <= 10:
            continue  # učitel celou vrstvu označil jako chybnou (např. popis ve vrstvě 50 místo 49)
        texty = [f for f in feats if f.geom_type == GeomType.TEXT]
        bunky = [f for f in feats if f.dxftype == "INSERT"]
        cary = [f for f in feats if f not in texty and f not in bunky]
        if cary:
            # typ prvku z protokolu se nevylučuje: „Typ prvku(!)“ učitel hlásí vůči pravidlu jiného objektu
            typy = _prevazujici([feature_element_type(f) for f in cary], podil, set())
            barvy = _prevazujici([_ms_barva(f) for f in cary], podil, spatne[(v, "barva")])
            styly = _prevazujici([f.linetype for f in cary], podil, spatne[(v, "styl")])
            for barva in barvy:
                vyber = [f for f in cary if _ms_barva(f) == barva] or cary
                st = _prevazujici([f.linetype for f in vyber], podil, spatne[(v, "styl")]) or styly
                tl = _prevazujici([_ms_tloustka(f) for f in vyber], podil, spatne[(v, "tloušťka")])
                meritka = _prevazujici([round(f.ltscale, 4) for f in vyber if f.linetype not in ("0", "CONTINUOUS")],
                                       podil, spatne[(v, "měřítko stylu")])
                pravidla.append(Rule(
                    kod=f"{v} čáry {barva}", nazev=f"Vrstva {v} – čáry ({barva})", geometrie=GeomType.LINIE,
                    hladina=v, barva=int(barva) if str(barva).isdigit() else barva,
                    styl_cary=",".join(str(s) for s in st) or None,
                    tloustka="|".join(tl) if tl else None, typy_prvku=sorted(t for t in typy if t is not None),
                    meritko_stylu=meritka[0] if len(meritka) == 1 and meritka[0] != 1.0 else
                    (1.0 if meritka == [1.0] and any(s not in ("0", "CONTINUOUS") for s in st) else None),
                    zdroj="vzorový výkres"))
        if texty:
            barvy = _prevazujici([_ms_barva(f) for f in texty], podil, spatne[(v, "barva")])
            vysky = _prevazujici([round(f.text_height, 3) for f in texty], podil,
                                 {str(x) for x in spatne[(v, "výška")]})
            sirky = _prevazujici([round(f.text_height * (f.width_factor or 1.0), 3) for f in texty], podil,
                                 {str(x) for x in spatne[(v, "šířka")]})
            fonty = _prevazujici([f.font for f in texty if f.font], podil, set())
            pravidla.append(Rule(
                kod=f"{v} texty", nazev=f"Vrstva {v} – texty", geometrie=GeomType.TEXT, hladina=v,
                barva=int(barvy[0]) if barvy and str(barvy[0]).isdigit() else None,
                vyska_textu=vysky[0] if len(vysky) == 1 else None,
                sirka_textu=sirky[0] if len(sirky) == 1 and len(vysky) == 1 else None,
                font=fonty[0] if len(fonty) == 1 else None, typy_prvku=[17], zdroj="vzorový výkres"))
        nazvy = Counter(f.block_name for f in bunky)
        for nazev, k in nazvy.items():
            if nazev in spatne[(v, "buňka")] or k / max(1, len(bunky)) < 0.02 and k == 1:
                continue
            vyber = [f for f in bunky if f.block_name == nazev]
            barvy = _prevazujici([_ms_barva(f) for f in vyber], podil, spatne[(v, "barva")])
            meritka = _prevazujici([round(abs(f.scale[0]), 4) for f in vyber], podil, spatne[(v, "měřítko buňky")])
            pravidla.append(Rule(
                kod=f"{v} buňka {nazev}", nazev=f"Vrstva {v} – buňka {nazev}", geometrie=GeomType.BOD, hladina=v,
                blok=nazev, barva=int(barvy[0]) if barvy and str(barvy[0]).isdigit() else None,
                meritko_bunky=meritka[0] if len(meritka) == 1 else None, typy_prvku=[2], zdroj="vzorový výkres"))
    return RuleSet(pravidla=pravidla, paleta="microstation")
