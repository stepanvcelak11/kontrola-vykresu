"""Kontroly atributů a konvencí (podle pravidel z tabulky od učitele)."""

from __future__ import annotations

import fnmatch

import numpy as np
import shapely

from ..model import Feature, GeomType
from ..rules import color_matches, linetype_matches
from .base import Check, CheckContext, Param, Severity, fmt_num, register


def _value_allowed(value: str, allowed: list[str]) -> bool:
    v = value.strip().lower()
    for a in allowed:
        a = a.strip().lower()
        if any(ch in a for ch in "*?["):
            if fnmatch.fnmatchcase(v, a):
                return True
        elif v == a:
            return True
    return False


@register
class PovinneAtributy(Check):
    id = "atributy"
    nazev = "Atributy prvku"
    skupina = "Atributy"
    popis = ("Kontroluje, že kódovaný prvek má vyplněné povinné atributy (z atributů buňky, XDATA "
             "nebo z textu u prvku) a že hodnoty patří mezi povolené hodnoty číselníku.")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True

    def run(self, ctx: CheckContext):
        feats = ctx.features()
        for i, f in enumerate(feats):
            if i % 2000 == 0:
                ctx.progress(i / max(1, len(feats)))
            r = ctx.rule_for(f)
            if r is None or (not r.povinne_atributy and not r.povolene_hodnoty):
                continue
            attrs = ctx.attributes(f)
            missing = [a for a in r.povinne_atributy if not str(attrs.get(a, "")).strip()]
            if missing:
                word = "atribut" if len(missing) == 1 else "atributy"
                yield ctx.issue(self, f, f"{r.nazev or r.kod}: chybí {word} {', '.join(missing)}")
            for a, allowed in r.povolene_hodnoty.items():
                if not allowed:
                    continue
                v = str(attrs.get(a, "")).strip()
                if v and not _value_allowed(v, allowed):
                    ukazka = ", ".join(allowed[:6]) + ("…" if len(allowed) > 6 else "")
                    yield ctx.issue(self, f, f"Nepovolená hodnota {a} = „{v}“ (povoleno: {ukazka})")


@register
class Symbologie(Check):
    id = "symbologie"
    nazev = "Hladina, barva nebo styl"
    skupina = "Atributy"
    popis = "Porovná hladinu, barvu, styl a tloušťku čáry prvku s pravidlem pro jeho kód."
    vychozi_zavaznost = Severity.VAROVANI
    potrebuje_pravidla = True
    parametry = [
        Param("kontrolovat_barvu", "Kontrolovat barvu", "bool", True),
        Param("kontrolovat_styl", "Kontrolovat styl čáry", "bool", True),
        Param("kontrolovat_tloustku", "Kontrolovat tloušťku", "bool", True),
    ]

    def run(self, ctx: CheckContext):
        do_color = bool(ctx.param("kontrolovat_barvu", True))
        do_style = bool(ctx.param("kontrolovat_styl", True))
        do_weight = bool(ctx.param("kontrolovat_tloustku", True))
        pal = ctx.rules.paleta
        feats = ctx.features()
        for i, f in enumerate(feats):
            if i % 2000 == 0:
                ctx.progress(i / max(1, len(feats)))
            r = ctx.rule_for(f)
            if r is None:
                continue
            diffs = []
            if r.hladina and not r.matches_layer(f.layer):
                diffs.append(f"hladina {f.layer} (má být {r.hladina})")
            if do_color and r.barva is not None and not color_matches(r.barva, f, pal):
                diffs.append(f"barva {f.color_aci} (má být {r.barva})")
            if (do_style and r.styl_cary and f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
                    and not linetype_matches(r.styl_cary, f.linetype)):
                diffs.append(f"styl {f.linetype} (má být {r.styl_cary})")
            if do_weight and r.tloustka is not None and abs(r.tloustka - f.lineweight) > 0.051:
                diffs.append(f"tloušťka {fmt_num(f.lineweight, 2)} mm (má být {fmt_num(r.tloustka, 2)})")
            if diffs:
                yield ctx.issue(self, f, f"{r.nazev or r.kod}: " + ", ".join(diffs))


@register
class NepovoleneHladiny(Check):
    id = "nepovolene_hladiny"
    nazev = "Nepovolená hladina"
    skupina = "Atributy"
    popis = ("Prvek leží na hladině, která není v pravidlech ani v seznamu povolených hladin. "
             "Hlásí se jedna chyba na každý prvek (u velkého počtu použijte filtr podle hladiny).")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True
    parametry = [Param("jedna_na_hladinu", "Jen jedna chyba na hladinu", "bool", False)]

    def run(self, ctx: CheckContext):
        once = bool(ctx.param("jedna_na_hladinu", False))
        reported: set[str] = set()
        cache: dict[str, bool] = {}
        for f in ctx.features():
            ok = cache.get(f.layer)
            if ok is None:
                ok = cache[f.layer] = ctx.rules.allowed_layer(f.layer)
            if ok:
                continue
            if once:
                if f.layer in reported:
                    continue
                reported.add(f.layer)
                n = sum(1 for x in ctx.features() if x.layer == f.layer)
                yield ctx.issue(self, f, f"Nepovolená hladina {f.layer} ({n} prvků)")
            else:
                yield ctx.issue(self, f, f"Nepovolená hladina {f.layer}")


@register
class Nekodovane(Check):
    id = "nekodovane"
    nazev = "Nekódovaný prvek"
    skupina = "Atributy"
    popis = ("Prvek, ke kterému nejde přiřadit žádný kód z pravidel (podle atributu KOD, buňky ani "
             "hladiny). Prvky na hladinách povolených bez kódu a popisy se nehlásí.")
    vychozi_zavaznost = Severity.VAROVANI
    potrebuje_pravidla = True

    def run(self, ctx: CheckContext):
        text_layers = ctx.rules.text_layers()
        for f in ctx.features():
            if ctx.rule_for(f) is not None:
                continue
            if ctx.rules.explicit_layer(f.layer):
                continue
            if f.geom_type == GeomType.TEXT and f.layer.upper() in text_layers:
                continue
            if not ctx.rules.allowed_layer(f.layer):
                continue  # hlásí kontrola nepovolených hladin
            what = {GeomType.BOD: "bod", GeomType.LINIE: "linie", GeomType.POLYGON: "polygon",
                    GeomType.TEXT: "text"}[f.geom_type]
            extra = f" (buňka {f.block_name})" if f.block_name else ""
            yield ctx.issue(self, f, f"Nekódovaný {what} na hladině {f.layer}{extra}")


@register
class Texty(Check):
    id = "texty"
    nazev = "Popis (text) prvku"
    skupina = "Atributy"
    popis = ("U prvků, jejichž pravidlo vyžaduje popis, hledá text: u polygonu uvnitř, jinak v okruhu "
             "hledání textu. Hlásí také popisy, které neleží v žádném polygonu, ke kterému patří.")
    vychozi_zavaznost = Severity.VAROVANI
    potrebuje_pravidla = True
    parametry = [Param("hlasit_text_mimo", "Hlásit text mimo polygon", "bool", True)]

    def run(self, ctx: CheckContext):
        rules_with_text = [r for r in ctx.rules.pravidla if r.text is not None]
        if not rules_with_text:
            return
        feats = ctx.features()
        owners: dict[str, list[Feature]] = {}  # hladina textu -> polygony, ke kterým texty patří
        for i, f in enumerate(feats):
            if i % 2000 == 0:
                ctx.progress(0.7 * i / max(1, len(feats)))
            if f.geom_type == GeomType.TEXT:
                continue
            r = ctx.rule_for(f)
            if r is None or r.text is None:
                continue
            area = ctx.area_geometry(f, r)
            if area is not None and r.text.hladina and r.text.uvnitr:
                owners.setdefault(r.text.hladina.upper(), []).append(area)
            if not r.text.povinny:
                continue
            if ctx.text_for(f, r) is None:
                where = "uvnitř polygonu" if area is not None else "u prvku"
                lay = f" (hladina {r.text.hladina})" if r.text.hladina else ""
                yield ctx.issue(self, f, f"{r.nazev or r.kod}: chybí popis {where}{lay}")
        if not ctx.param("hlasit_text_mimo", True):
            return
        ctx.progress(0.8)
        for layer, polys in owners.items():
            texts = ctx.texts(layer)
            if not texts:
                continue
            tree = shapely.STRtree(np.array(polys, dtype=object))
            pts = np.array([t.geometry for t in texts], dtype=object)
            ti, _ = tree.query(pts, predicate="within")
            inside = set(int(x) for x in ti)
            for k, t in enumerate(texts):
                if k not in inside:
                    yield ctx.issue(self, t, f"Text „{(t.text or '')[:30]}“ leží mimo polygon, ke kterému patří")


@register
class TypGeometrie(Check):
    id = "typ_geometrie"
    nazev = "Typ geometrie"
    skupina = "Atributy"
    popis = ("Typ prvku (bod / linie / polygon / text) neodpovídá typu očekávanému pro jeho kód. "
             "Neuzavřená linie tam, kde má být polygon, se hlásí v kontrole nezavřených polygonů.")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True

    def run(self, ctx: CheckContext):
        for f in ctx.features():
            r = ctx.rule_for(f)
            if r is None or r.geometrie is None:
                continue
            got = f.geom_type
            if got == r.geometrie:
                continue
            if r.geometrie == GeomType.POLYGON and got == GeomType.LINIE:
                continue
            yield ctx.issue(self, f, f"{r.nazev or r.kod}: {got.label} místo {r.geometrie.label}")
