"""Kontroly atributů a konvencí (podle pravidel z tabulky od učitele)."""

from __future__ import annotations

import fnmatch
import re

import numpy as np
import shapely

from ..model import Feature, GeomType
from ..rules import (color_known, color_matches, font_style, layer_matches, layer_number, linetype_matches,
                     weight_values)
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
    nazev = "Symbologie (vrstva, barva, styl, písmo)"
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
        Param("kontrolovat_font", "Kontrolovat font textu", "bool", True,
              "Porovná název fontu z pravidla s fontem textového stylu v DXF (např. CS WORKING → cs_Working.shx)."),
    ]

    def run(self, ctx: CheckContext):
        do_color = bool(ctx.param("kontrolovat_barvu", True))
        do_style = bool(ctx.param("kontrolovat_styl", True))
        do_weight = bool(ctx.param("kontrolovat_tloustku", True))
        do_text = bool(ctx.param("kontrolovat_text", True))
        do_font = bool(ctx.param("kontrolovat_font", True))
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
                diffs.append(f"vrstva {f.layer} (má být {r.hladina})")
            if do_color and r.barva is not None:
                if not color_known(r.barva, pal, table) and "MS_BARVA" not in f.attributes:
                    unknown_colors.add(r.barva)
                elif not color_matches(r.barva, f, pal, table):
                    got = rs.describe_feature_color(f)
                    if got.startswith("ACI ") and pal == "microstation":
                        # v DXF je barva, která z tabulky color.tbl vzniknout nemohla
                        got = (f"{got} = RGB {','.join(map(str, f.color_rgb))} – taková barva v tabulce color.tbl "
                               "není (jiná tabulka barev nebo barva RGB?)")
                    diffs.append(f"barva {got} (má být {r.barva})")
            linear = f.geom_type in (GeomType.LINIE, GeomType.POLYGON)
            unexported = False
            if do_style and r.styl_cary and linear and f.linetype == "VLASTNI_STYL":
                # DGN: vlastní styl čáry – jeho název je v knihovně stylů, ne ve výkresu
                if not re.search(r"\d+\.\d+", str(r.styl_cary)):
                    diffs.append(f"styl vlastní (id {f.attributes.get('MS_STYL')}) (má být {r.styl_cary})")
            elif do_style and r.styl_cary and linear and not linetype_matches(r.styl_cary, f.linetype):
                if _custom_style_not_exported(r.styl_cary, f, ctx.drawing.linetypes):
                    unexported = True
                else:
                    diffs.append(f"styl {f.linetype} (má být {r.styl_cary})")
            if do_style and r.meritko_stylu and linear and (unexported or f.linetype != "CONTINUOUS") \
                    and abs(f.ltscale - r.meritko_stylu) > 1e-4:
                diffs.append(f"měřítko stylu {fmt_num(f.ltscale, 3)} (má být {fmt_num(r.meritko_stylu, 3)})")
            if r.meritko_bunky and f.dxftype == "INSERT" and \
                    abs(abs(f.scale[0]) - r.meritko_bunky) > 1e-4 * max(1.0, r.meritko_bunky):
                diffs.append(f"měřítko buňky {fmt_num(abs(f.scale[0]), 3)} (má být {fmt_num(r.meritko_bunky, 3)})")
            if unexported and not diffs:
                iss = ctx.issue(self, f, f"{r.nazev or r.kod}: styl v DXF je Continuous – uživatelský styl "
                                         f"{r.styl_cary} MicroStation do DXF neuložil, ověřte ho v DGN"
                                         + (f" (měřítko stylu {fmt_num(f.ltscale, 3)} odpovídá)"
                                            if r.meritko_stylu and abs(f.ltscale - r.meritko_stylu) <= 1e-4 else ""))
                iss.severity = Severity.VAROVANI
                yield iss
                continue
            if do_weight and r.tloustka is not None and f.geom_type != GeomType.TEXT and \
                    f.attributes.get("MS_TLOUSTKA") is not None:
                wants = [int(w) for w in weight_values(r.tloustka) if float(w).is_integer() and 0 <= w <= 31]
                got = int(f.attributes["MS_TLOUSTKA"])
                if wants and got not in wants:
                    diffs.append(f"tloušťka {got} (má být {' nebo '.join(map(str, wants))})")
            elif do_weight and r.tloustka is not None and f.geom_type != GeomType.TEXT:
                # tloušťka MicroStationu (wt 0–31) se v DXF ověří přes převodní tabulku na mm
                expected, unknown = rs.expected_weights(r)
                ms_weights.update(unknown)
                if expected and not unknown and all(abs(w - f.lineweight) > 0.051 for w in expected):
                    diffs.append(f"tloušťka {fmt_num(f.lineweight, 2)} mm (má být "
                                 f"{' nebo '.join(fmt_num(w, 2) for w in expected)} mm, wt {fmt_num(float(r.tloustka), 0) if str(r.tloustka).replace('.', '', 1).isdigit() else r.tloustka})"
                                 if pal == "microstation" and wmap else
                                 f"tloušťka {fmt_num(f.lineweight, 2)} mm (má být {r.tloustka})")
            if f.geom_type == GeomType.TEXT and do_text:
                diffs += _text_diffs(r, f, rs)
            if f.geom_type == GeomType.TEXT and do_font and r.font and f.attributes.get("ZDROJ") != "DGN" and \
                    _norm_font(r.font) not in _norm_font(f.font):  # z DGN se písmo nečte
                diffs.append(f"font {f.font or '–'} (má být {r.font})")
            if diffs:
                yield ctx.issue(self, f, f"{_what(f)} (pravidlo „{r.nazev or r.kod}“): " + ", ".join(diffs))
        if unknown_colors:
            ctx.notes.append("barvy MicroStationu " + ", ".join(map(str, sorted(unknown_colors, key=str)))
                             + " nelze ověřit bez barevné tabulky – načtěte color.tbl v Nastavení kontrol → Obecné.")
        if ms_weights:
            ctx.notes.append("tloušťky MicroStationu (wt " + ", ".join(map(str, sorted(ms_weights)))
                             + ") se ověřují jen s převodní tabulkou tlouštěk (mapa_tloustek v pravidlech).")


def _custom_style_not_exported(expected: str, f: Feature, linetypes: set[str]) -> bool:
    """Prvek má v DXF Continuous, pravidlo chce uživatelský styl (např. 5.303), který v DXF vůbec není.

    MicroStation některé uživatelské styly (se značkami) do DXF nepřevede a uloží čáru jako
    Continuous – z DXF pak nejde poznat, jestli je styl ve výkresu správně."""
    if (f.linetype or "CONTINUOUS").upper() != "CONTINUOUS":
        return False
    from ..rules import split_alternatives
    alts = split_alternatives(expected)
    custom = [a for a in alts if re.match(r"^\d+\.\d+", a)]
    if not custom or any(a.strip() in ("0", "CONTINUOUS") for a in alts):
        return False
    known = {lt.upper() for lt in (linetypes or set())}
    return not any(c.upper() in known for c in custom)


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


def _text_diffs(r, f: Feature, rs=None) -> list[str]:
    out = []
    tol = lambda x: max(0.005, 0.02 * x)  # noqa: E731
    scale = rs.meritko if rs is not None and rs.meritko else None

    def show(v_m: float, rule_v: float) -> tuple[str, str]:
        if scale:  # pravidla jsou v mm na papíře
            return f"{fmt_num(v_m * 1000 / scale, 2)} mm", f"{fmt_num(rule_v, 2)} mm"
        return fmt_num(v_m, 2), fmt_num(rule_v, 2)
    size = rs.text_size if rs is not None else (lambda v: v)
    h_exp = size(r.vyska_textu)
    if h_exp and abs(f.text_height - h_exp) > tol(h_exp):
        got, exp = show(f.text_height, r.vyska_textu)
        out.append(f"výška textu {got} (má být {exp})")
    w_exp = size(r.sirka_textu)
    if w_exp and f.dxftype == "TEXT":
        w = f.text_height * (f.width_factor or 1.0)
        if abs(w - w_exp) > tol(w_exp):
            got, exp = show(w, r.sirka_textu)
            out.append(f"šířka textu {got} (má být {exp})")
    if (r.tucne is not None or r.kurziva is not None) and f.font:
        bold, italic = font_style(f.font)
        if r.tucne is not None and bold != r.tucne:
            out.append("písmo " + ("není tučné" if r.tucne else "je tučné") + f" ({f.font})")
        if r.kurziva is not None and italic != r.kurziva:
            out.append("písmo " + ("není kurzíva" if r.kurziva else "je kurzíva") + f" ({f.font})")
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
    nazev = "Prvek jiný než ostatní na vrstvě"
    skupina = "Atributy"
    popis = ("Funguje i bez tabulky od učitele: na každé vrstvě zjistí převažující barvu, styl a tloušťku "
             "čáry a nahlásí prvky, které se od většiny liší (např. omylem přebarvená linie nebo prvek "
             "nakreslený jiným stylem). Texty a buňky se porovnávají jen barvou.")
    vychozi_zavaznost = Severity.VAROVANI
    parametry = [
        Param("min_prvku", "Jen vrstvy s aspoň N prvky", "int", 5),
        Param("min_podil", "Převažující hodnota musí mít podíl aspoň [%]", "float", 70.0),
        Param("jen_bez_pravidla", "Jen prvky bez pravidla", "bool", True,
              "Prvky s pravidlem kontroluje přesněji kontrola „Vrstva, barva nebo styl“."),
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
                    yield ctx.issue(self, f, f"{_what(f)} se liší od ostatních na vrstvě {layer}: " + ", ".join(diffs))


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
        return f"barva {col(got)} (ostatní mají {col(expected)})"
    if name == "tloušťka":
        return f"tloušťka {fmt_num(got, 2)} mm (ostatní mají {fmt_num(expected, 2)} mm)"
    return f"styl {got} (ostatní mají {expected})"


def _what(f: Feature) -> str:
    """Typ prvku slovy jako v MicroStationu (Úsečka, Lomená čára, Text, Buňka…)."""
    from ..rules import MS_ELEMENT_NAMES, feature_element_type
    t = feature_element_type(f)
    name = MS_ELEMENT_NAMES.get(t) if t is not None else None
    if f.dxftype == "POINT" or f.zero_length:
        name = "Bod"
    return name or f.dxftype.capitalize()


def _kinds(feats: list[Feature]) -> str:
    from collections import Counter
    c = Counter(_what(f).split(" ")[0].lower() for f in feats)
    return ", ".join(f"{n}× {k}" for k, n in c.most_common(3))


def _rule_score(r, f: Feature, rs) -> float | None:
    """Jak dobře prvek odpovídá pravidlu podle vzhledu (0–1); None = jiný druh prvku."""
    if r.geometrie is not None and r.geometrie != f.geom_type:
        return None
    if f.geom_type == GeomType.TEXT and not (r.font or r.vyska_textu or r.geometrie == GeomType.TEXT):
        return None
    if f.geom_type != GeomType.TEXT and (r.font or r.vyska_textu) and r.geometrie is None:
        return None
    if r.blok:
        from ..rules import block_matches
        if not f.block_name or not any(block_matches(p, f.block_name) for p in _alts(r.blok)):
            return None
    elif f.block_name:
        return None
    hits = total = 0
    if r.barva is not None and color_known(r.barva, rs.paleta, rs.barevna_tabulka):
        total += 1
        hits += color_matches(r.barva, f, rs.paleta, rs.barevna_tabulka)
    if r.tloustka is not None and f.geom_type != GeomType.TEXT:
        exp, unknown = rs.expected_weights(r)
        if exp and not unknown:
            total += 1
            hits += any(abs(w - f.lineweight) <= 0.051 for w in exp)
    if f.geom_type == GeomType.TEXT:
        if r.font and f.font:
            total += 1
            hits += _norm_font(r.font) in _norm_font(f.font)
        h = rs.text_size(r.vyska_textu) if r.vyska_textu else None
        if h:
            total += 1
            hits += abs(f.text_height - h) <= max(0.005, 0.02 * h)
    if r.styl_cary and f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
        total += 1
        hits += linetype_matches(r.styl_cary, f.linetype)
    return hits / total if total else None


def _alts(v) -> list[str]:
    from ..rules import split_alternatives
    return split_alternatives(str(v))


def guess_layer(feats: list[Feature], rs, drawing=None) -> str:
    """Na kterou vrstvu ze Směrnice prvky z neznámé vrstvy nejspíš patří (podle barvy, tloušťky, písma…)."""
    sample = feats[:30]
    best: dict[str, float] = {}
    for r in rs.pravidla:
        if not r.hladina or any(ch in r.hladina for ch in "*?"):
            continue
        scores = [_rule_score(r, f, rs) for f in sample]
        scores = [x for x in scores if x is not None]
        if len(scores) < max(1, len(sample) // 2):
            continue
        sc = sum(scores) / len(sample)
        if sc >= 0.75:
            best[r.hladina] = max(best.get(r.hladina, 0.0), sc)
    if not best:
        return ""
    top = max(best.values())
    cands = [h for h, v in best.items() if v >= top - 1e-9]
    if len(cands) > 1 and drawing is not None:  # přednost má vrstva, která ve výkresu chybí nebo je prázdná
        empty = [h for h in cands if not any(layer_matches(h, n) and li.count for n, li in drawing.layers.items())]
        if empty:
            cands = empty
    if len(cands) > 3:
        return ""
    return " nebo ".join(cands)


def _prvku(n: int) -> str:
    return f"{n} prvek" if n == 1 else f"{n} prvky" if 2 <= n <= 4 else f"{n} prvků"


@register
class NepovoleneHladiny(Check):
    id = "nepovolene_hladiny"
    nazev = "Vrstva není ve Směrnici"
    skupina = "Atributy"
    popis = ("Prvek leží na vrstvě, která není v pravidlech ani v seznamu povolených vrstev. "
             "Hlásí se jedna chyba na vrstvu s počtem prvků (lze přepnout na chybu u každého prvku).")
    vychozi_zavaznost = Severity.CHYBA
    potrebuje_pravidla = True
    parametry = [Param("jedna_na_hladinu", "Jen jedna chyba na vrstvu", "bool", True)]

    def run(self, ctx: CheckContext):
        once = bool(ctx.param("jedna_na_hladinu", True))
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
                feats = [x for x in ctx.features() if x.layer == f.layer]
                name = f.layer if re.match(r"(?i)(vrstva|level|hladina)\b", f.layer) else f"Vrstva {f.layer}"
                msg = f"{name} není ve Směrnici: {_kinds(feats)}"
                guess = guess_layer(feats, ctx.rules, ctx.drawing)
                if guess:
                    msg += f" – podle vzhledu patří na vrstvu {guess}"
                elif layer_number(f.layer) is not None:  # číslované vrstvy bývají popsané ve Wordu (zadání 1)
                    msg += " – je-li popsaná ve Wordu se zadáním, nahrajte ho do Zadání → Pokyny ze zadání"
                if len(feats) > 1:
                    msg += f" (týká se všech {_prvku(len(feats))}, kroužek je jen u prvního)"
                yield ctx.issue(self, feats, msg)
            else:
                yield ctx.issue(self, f, f"{_what(f)} na vrstvě {f.layer}, která není ve Směrnici")


@register
class Nekodovane(Check):
    id = "nekodovane"
    nazev = "Nekódovaný prvek"
    skupina = "Atributy"
    popis = ("Prvek, ke kterému nejde přiřadit žádný kód z pravidel (podle atributu KOD, buňky ani "
             "vrstvy). Prvky na vrstvách povolených bez kódu a popisy se nehlásí.")
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
            yield ctx.issue(self, f, f"Nekódovaný {what} na vrstvě {f.layer}{extra}")


@register
class Texty(Check):
    id = "texty"
    nazev = "Popis (text) prvku"
    skupina = "Atributy"
    popis = ("U prvků, jejichž pravidlo vyžaduje popis, hledá text (na vrstvě popisu i bodový prvek – "
             "definiční bod): u polygonu uvnitř, jinak v okruhu hledání textu. Hlásí také popisy mimo "
             "polygon, ke kterému patří, a plochy s více popisy (jako pravidlo „jeden definiční bod "
             "v ploše“).")
    vychozi_zavaznost = Severity.VAROVANI
    potrebuje_pravidla = True
    parametry = [
        Param("hlasit_text_mimo", "Hlásit text mimo polygon", "bool", True),
        Param("jeden_popis", "V ploše smí být jen jeden popis", "bool", True,
              "Plocha s více popisy / definičními body na vrstvě popisu je chyba."),
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
                lay = f" (vrstva {r.text.hladina})" if r.text.hladina else ""
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
