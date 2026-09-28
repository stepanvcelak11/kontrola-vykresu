"""Kontroly atributů a konvencí (podle pravidel z tabulky od učitele)."""

from __future__ import annotations

import fnmatch
import re

import numpy as np
import shapely

from ..model import Feature, GeomType
from ..rules import color_known, color_matches, layer_matches, linetype_matches
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
    popis = ("Porovná vrstvu, barvu, styl a tloušťku čáry prvku s pravidlem pro jeho kód (jako „Kontrola "
             "symbologie“ GISoft/MGEO). U textů také výšku, šířku, zarovnání a volitelně font.")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True
    parametry = [
        Param("kontrolovat_barvu", "Kontrolovat barvu", "bool", True),
        Param("kontrolovat_styl", "Kontrolovat styl čáry", "bool", True),
        Param("kontrolovat_tloustku", "Kontrolovat tloušťku", "bool", True),
        Param("kontrolovat_text", "Kontrolovat výšku, šířku a zarovnání textu", "bool", True),
        Param("kontrolovat_font", "Kontrolovat font textu", "bool", False,
              "Název fontu v DXF nemusí odpovídat názvu v MicroStationu – zapněte, až ověříte."),
    ]

    def run(self, ctx: CheckContext):
        do_color = bool(ctx.param("kontrolovat_barvu", True))
        do_style = bool(ctx.param("kontrolovat_styl", True))
        do_weight = bool(ctx.param("kontrolovat_tloustku", True))
        do_text = bool(ctx.param("kontrolovat_text", True))
        do_font = bool(ctx.param("kontrolovat_font", False))
        rs = ctx.rules
        pal, table = rs.paleta, rs.barevna_tabulka
        wmap = rs.mapa_tloustek
        unknown_colors: set = set()
        ms_weights: set = set()
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
            if do_color and r.barva is not None:
                if not color_known(r.barva, pal, table):
                    unknown_colors.add(r.barva)
                elif not color_matches(r.barva, f, pal, table):
                    diffs.append(f"barva {rs.describe_feature_color(f)} (má být {r.barva})")
            if (do_style and r.styl_cary and f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
                    and not linetype_matches(r.styl_cary, f.linetype)):
                diffs.append(f"styl {f.linetype} (má být {r.styl_cary})")
            if do_weight and r.tloustka is not None and f.geom_type != GeomType.TEXT:
                expected = r.tloustka
                if pal == "microstation" and float(r.tloustka).is_integer() and 0 <= r.tloustka <= 31:
                    # tloušťka MicroStationu (wt 0–31) – v DXF jen přes převodní tabulku na mm
                    expected = wmap.get(int(r.tloustka))
                    if expected is None:
                        ms_weights.add(int(r.tloustka))
                if expected is not None and abs(expected - f.lineweight) > 0.051:
                    diffs.append(f"tloušťka {fmt_num(f.lineweight, 2)} mm (má být {fmt_num(expected, 2)})")
            if f.geom_type == GeomType.TEXT and do_text:
                diffs += _text_diffs(r, f)
            if f.geom_type == GeomType.TEXT and do_font and r.font and \
                    _norm_font(r.font) not in _norm_font(f.font):
                diffs.append(f"font {f.font or '–'} (má být {r.font})")
            if diffs:
                yield ctx.issue(self, f, f"{r.nazev or r.kod}: " + ", ".join(diffs))
        if unknown_colors:
            ctx.notes.append("barvy MicroStationu " + ", ".join(map(str, sorted(unknown_colors, key=str)))
                             + " nelze ověřit bez barevné tabulky – načtěte color.tbl v Nastavení kontrol → Obecné.")
        if ms_weights:
            ctx.notes.append("tloušťky MicroStationu (wt " + ", ".join(map(str, sorted(ms_weights)))
                             + ") se ověřují jen s převodní tabulkou tlouštěk (mapa_tloustek v pravidlech).")


def _norm_font(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", (s or "").lower())


_HALIGN = {"vlevo": 0, "left": 0, "střed": 1, "stred": 1, "na střed": 1, "center": 1, "vpravo": 2, "right": 2}
_VALIGN = {"nahoře": 3, "nahore": 3, "top": 3, "uprostřed": 2, "uprostred": 2, "middle": 2,
           "dole": 1, "bottom": 1, "účaří": 0, "ucari": 0, "baseline": 0}
_HNAME = {0: "vlevo", 1: "střed", 2: "vpravo"}
_VNAME = {0: "účaří", 1: "dole", 2: "uprostřed", 3: "nahoře"}


def parse_alignment(text: str) -> tuple[int | None, int | None]:
    t = (text or "").lower()
    h = next((v for k, v in _HALIGN.items() if k in t), None)
    v = next((v for k, v in _VALIGN.items() if k in t), None)
    if h is None and "střed uprostřed" in t:
        h = 1
    return h, v


def _text_diffs(r, f: Feature) -> list[str]:
    out = []
    tol = lambda x: max(0.01, 0.02 * x)  # noqa: E731
    if r.vyska_textu and abs(f.text_height - r.vyska_textu) > tol(r.vyska_textu):
        out.append(f"výška textu {fmt_num(f.text_height, 2)} (má být {fmt_num(r.vyska_textu, 2)})")
    if r.sirka_textu and f.dxftype == "TEXT":
        w = f.text_height * (f.width_factor or 1.0)
        if abs(w - r.sirka_textu) > tol(r.sirka_textu):
            out.append(f"šířka textu {fmt_num(w, 2)} (má být {fmt_num(r.sirka_textu, 2)})")
    if r.zarovnani:
        h, v = parse_alignment(r.zarovnani)
        if (h is not None and h != f.halign) or (v is not None and v != f.valign):
            out.append(f"zarovnání {_HNAME.get(f.halign, '?')} {_VNAME.get(f.valign, '?')} "
                       f"(má být {r.zarovnani})")
    return out


@register
class AtributDleVrstvy(Check):
    id = "atribut_dle_vrstvy"
    nazev = "Atribut dle vrstvy (ByLevel)"
    skupina = "Atributy"
    popis = ("Prvek má barvu, styl nebo tloušťku nastavenou „dle vrstvy“ (ByLevel, v DXF BYLAYER). "
             "Podle zadání se atribut dle vrstvy nesmí používat – každý prvek má mít vlastní hodnoty.")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True
    parametry = [
        Param("barva", "Kontrolovat barvu", "bool", True),
        Param("styl", "Kontrolovat styl čáry", "bool", True),
        Param("tloustka", "Kontrolovat tloušťku", "bool", True),
    ]

    def run(self, ctx: CheckContext):
        watch = {k for k, p in (("barva", "barva"), ("styl", "styl"), ("tloušťka", "tloustka"))
                 if ctx.param(p, True)}
        for f in ctx.features():
            got = sorted(set(f.bylayer) & watch)
            if f.geom_type == GeomType.TEXT or f.dxftype == "INSERT":
                got = [g for g in got if g == "barva"]
            if got:
                yield ctx.issue(self, f, "Atribut dle vrstvy: " + ", ".join(got))


@register
class JednotnostHladiny(Check):
    id = "jednotnost_hladiny"
    nazev = "Nejednotná symbologie hladiny"
    skupina = "Atributy"
    popis = ("Funguje i bez tabulky od učitele: na každé hladině zjistí převažující barvu, styl a tloušťku "
             "čáry a nahlásí prvky, které se od většiny liší (např. omylem přebarvená linie nebo prvek "
             "nakreslený jiným stylem). Texty a buňky se porovnávají jen barvou.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [
        Param("min_prvku", "Jen hladiny s aspoň N prvky", "int", 5),
        Param("min_podil", "Převažující hodnota musí mít podíl aspoň [%]", "float", 70.0),
        Param("jen_bez_pravidla", "Jen prvky bez pravidla", "bool", True,
              "Prvky s pravidlem kontroluje přesněji kontrola „Hladina, barva nebo styl“."),
    ]

    def run(self, ctx: CheckContext):
        from collections import Counter, defaultdict
        min_n = int(ctx.param("min_prvku", 5))
        share = float(ctx.param("min_podil", 70.0)) / 100.0
        only_free = bool(ctx.param("jen_bez_pravidla", True)) and bool(ctx.rules.pravidla)
        by_layer: dict[str, list[Feature]] = defaultdict(list)
        for f in ctx.features():
            by_layer[f.layer].append(f)
        for li, (layer, feats) in enumerate(by_layer.items()):
            ctx.progress(li / max(1, len(by_layer)))
            if len(feats) < min_n:
                continue
            lin = [f for f in feats if f.geom_type in (GeomType.LINIE, GeomType.POLYGON) and f.dxftype != "HATCH"]
            props = {
                "barva": ([f for f in feats if f.dxftype != "HATCH"], lambda f: tuple(f.color_rgb)),
                "styl": (lin, lambda f: (f.linetype or "CONTINUOUS").upper()),
                "tloušťka": (lin, lambda f: round(f.lineweight, 2)),
            }
            dominant = {}
            for name, (items, key) in props.items():
                if len(items) < min_n:
                    continue
                c = Counter(key(f) for f in items)
                val, cnt = c.most_common(1)[0]
                if cnt / len(items) >= share and cnt < len(items):
                    dominant[name] = (val, key, {id(f) for f in items})
            if not dominant:
                continue
            for f in feats:
                if only_free and ctx.rule_for(f) is not None:
                    continue
                diffs = []
                for name, (val, key, members) in dominant.items():
                    if id(f) in members and key(f) != val:
                        diffs.append(_describe_prop(name, key(f), val, ctx, f))
                if diffs:
                    yield ctx.issue(self, f, f"Na hladině {layer} se liší: " + ", ".join(diffs))


def _describe_prop(name, got, expected, ctx: CheckContext, f: Feature) -> str:
    if name == "barva":
        rs = ctx.rules

        def col(rgb):
            from ..rules import nearest_ms_index
            if rs.paleta == "microstation":
                idx = nearest_ms_index(rgb, rs.barevna_tabulka)
                if idx is not None:
                    return str(idx)
            return "#%02X%02X%02X" % rgb
        return f"barva {col(got)} (většina {col(expected)})"
    if name == "tloušťka":
        return f"tloušťka {fmt_num(got, 2)} mm (většina {fmt_num(expected, 2)} mm)"
    return f"styl {got} (většina {expected})"


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
            if f.geom_type == GeomType.TEXT and any(layer_matches(p, f.layer) for p in text_layers):
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
    popis = ("U prvků, jejichž pravidlo vyžaduje popis, hledá text (na hladině popisu i bodový prvek – "
             "definiční bod): u polygonu uvnitř, jinak v okruhu hledání textu. Hlásí také popisy mimo "
             "polygon, ke kterému patří, a plochy s více popisy (jako pravidlo „jeden definiční bod "
             "v ploše“).")
    vychozi_zavaznost = Severity.VAROVANI
    potrebuje_pravidla = True
    parametry = [
        Param("hlasit_text_mimo", "Hlásit text mimo polygon", "bool", True),
        Param("jeden_popis", "V ploše smí být jen jeden popis", "bool", True,
              "Plocha s více popisy / definičními body na hladině popisu je chyba."),
    ]

    @staticmethod
    def _label(t: Feature) -> str:
        if t.geom_type == GeomType.TEXT:
            return f"Text „{(t.text or '')[:30]}“"
        return f"Definiční bod ({t.block_name or t.dxftype})"

    def run(self, ctx: CheckContext):
        rules_with_text = [r for r in ctx.rules.pravidla if r.text is not None]
        if not rules_with_text:
            return
        one = bool(ctx.param("jeden_popis", True))
        feats = ctx.features()
        owners: dict[str, list[Feature]] = {}  # hladina textu -> polygony, ke kterým texty patří
        text_layers = {r.text.hladina.upper() for r in rules_with_text if r.text.hladina}
        for i, f in enumerate(feats):
            if i % 2000 == 0:
                ctx.progress(0.7 * i / max(1, len(feats)))
            if f.geom_type == GeomType.TEXT:
                continue
            if f.geom_type == GeomType.BOD and any(layer_matches(p, f.layer) for p in text_layers):
                continue  # definiční bod sám je popisem
            r = ctx.rule_for(f)
            if r is None or r.text is None:
                continue
            area = ctx.area_geometry(f, r)
            if area is not None and r.text.hladina and r.text.uvnitr:
                owners.setdefault(r.text.hladina.upper(), []).append(area)
                if one:
                    inside = ctx.texts_inside(area, r.text.hladina)
                    if len(inside) > 1:
                        names = ", ".join(f"„{(t.text or t.block_name or '•')[:12]}“" for t in inside[:4])
                        yield ctx.issue(self, f, f"{r.nazev or r.kod}: více popisů v ploše ({len(inside)}: "
                                                 f"{names})")
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
                    yield ctx.issue(self, t, f"{self._label(t)} leží mimo polygon, ke kterému patří")


@register
class TypGeometrie(Check):
    id = "typ_geometrie"
    nazev = "Typ geometrie"
    skupina = "Atributy"
    popis = ("Typ prvku neodpovídá pravidlu: buď povoleným typům prvků MicroStationu (úsečka, lomená "
             "čára, tvar, elipsa, oblouk, text, buňka…), nebo typu bod / linie / polygon / text. "
             "Neuzavřená linie tam, kde má být polygon, se hlásí v kontrole nezavřených polygonů.")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True

    def run(self, ctx: CheckContext):
        from ..rules import MS_ELEMENT_NAMES, feature_element_type
        for f in ctx.features():
            r = ctx.rule_for(f)
            if r is None:
                continue
            if r.typy_prvku:
                t = feature_element_type(f)
                if t is not None and t not in r.typy_prvku:
                    allowed = ", ".join(MS_ELEMENT_NAMES.get(x, str(x)) for x in r.typy_prvku)
                    yield ctx.issue(self, f, f"{r.nazev or r.kod}: typ prvku {MS_ELEMENT_NAMES.get(t, t)} "
                                             f"(povoleno: {allowed})")
                continue
            if r.geometrie is None:
                continue
            got = f.geom_type
            if got == r.geometrie:
                continue
            if r.geometrie == GeomType.POLYGON and got == GeomType.LINIE:
                continue
            yield ctx.issue(self, f, f"{r.nazev or r.kod}: {got.label} místo {r.geometrie.label}")
