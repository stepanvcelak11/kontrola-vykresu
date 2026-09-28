"""Vzorový výkres: rozbor použitých hladin/barev/stylů/bloků, návrh pravidel a porovnání."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..model import Drawing, GeomType
from ..rules import Rule, RuleSet, TextRule


@dataclass
class LayerUsage:
    name: str
    count: int = 0
    colors: Counter = field(default_factory=Counter)
    linetypes: Counter = field(default_factory=Counter)
    lineweights: Counter = field(default_factory=Counter)
    geoms: Counter = field(default_factory=Counter)
    blocks: Counter = field(default_factory=Counter)
    attribs: Counter = field(default_factory=Counter)

    def main(self, c: Counter):
        return c.most_common(1)[0][0] if c else None

    @property
    def color(self):
        return self.main(self.colors)

    @property
    def linetype(self):
        return self.main(self.linetypes)

    @property
    def geom(self) -> GeomType | None:
        return self.main(self.geoms)


@dataclass
class TemplateInfo:
    layers: dict[str, LayerUsage] = field(default_factory=dict)
    blocks: Counter = field(default_factory=Counter)
    linetypes: set[str] = field(default_factory=set)


def analyze(drawing: Drawing) -> TemplateInfo:
    info = TemplateInfo(linetypes=set(drawing.linetypes))
    for f in drawing.features:
        lu = info.layers.setdefault(f.layer, LayerUsage(f.layer))
        lu.count += 1
        lu.colors[f.color_aci] += 1
        lu.geoms[f.geom_type] += 1
        if f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
            lu.linetypes[f.linetype] += 1
            lu.lineweights[round(f.lineweight, 2)] += 1
        if f.block_name:
            lu.blocks[f.block_name] += 1
            info.blocks[f.block_name] += 1
            for k in f.attributes:
                lu.attribs[(f.block_name, k)] += 1
    return info


def propose_rules(info: TemplateInfo, existing: RuleSet | None = None) -> list[Rule]:
    """Navrhne pravidla: pro každou buňku jedno bodové pravidlo, pro ostatní prvky pravidlo na hladinu."""
    existing = existing or RuleSet()
    have_codes = {r.kod.upper() for r in existing.pravidla}
    have_layers = {r.hladina.upper() for r in existing.pravidla if r.hladina}
    have_blocks = {r.blok.upper() for r in existing.pravidla if r.blok}
    out: list[Rule] = []
    text_only = {n for n, lu in info.layers.items() if lu.geoms and set(lu.geoms) == {GeomType.TEXT}}
    for name in sorted(info.layers, key=str.lower):
        lu = info.layers[name]
        # buňky
        for block, n in lu.blocks.most_common():
            if block.upper() in have_blocks or block.upper() in have_codes:
                continue
            attrs = sorted({k for (b, k), c in lu.attribs.items() if b == block and c == n})
            out.append(Rule(kod=block, nazev=f"Buňka {block}", geometrie=GeomType.BOD, hladina=name,
                            barva=lu.color, blok=block, povinne_atributy=attrs,
                            zdroj=f"vzor: hladina {name}, {n}× buňka"))
            have_blocks.add(block.upper())
        rest = Counter({g: c for g, c in lu.geoms.items()})
        if lu.blocks:
            rest[GeomType.BOD] -= sum(lu.blocks.values())
        rest = +rest
        if not rest or name.upper() in have_layers or name.upper() in have_codes:
            continue
        geom = rest.most_common(1)[0][0]
        lt = lu.linetype if geom in (GeomType.LINIE, GeomType.POLYGON) else None
        lw = lu.main(lu.lineweights) if geom in (GeomType.LINIE, GeomType.POLYGON) else None
        out.append(Rule(kod=name, nazev=name.replace("_", " ").capitalize(), geometrie=geom, hladina=name,
                        barva=lu.color, styl_cary=lt, tloustka=lw or None,
                        zdroj=f"vzor: hladina {name}, {sum(rest.values())} prvků"))
    # polygon s texty na hladině se stejným základem názvu (např. BUDOVY + POPIS_BUDOV)
    for r in out:
        if r.geometrie == GeomType.POLYGON:
            base = r.hladina.upper().rstrip("Y").rstrip("E")[:5]
            for t in text_only:
                if base and base in t.upper():
                    r.text = TextRule(povinny=True, hladina=t)
                    break
    return out


@dataclass
class Difference:
    kategorie: str
    polozka: str
    vzor: str
    vykres: str
    popis: str


def compare(template: TemplateInfo, drawing: TemplateInfo) -> list[Difference]:
    out: list[Difference] = []
    tl = {k.upper(): v for k, v in template.layers.items()}
    dl = {k.upper(): v for k, v in drawing.layers.items()}
    for k in sorted(tl.keys() - dl.keys()):
        out.append(Difference("Hladina", tl[k].name, f"{tl[k].count} prvků", "–",
                              "Hladina ze vzoru ve výkresu chybí"))
    for k in sorted(dl.keys() - tl.keys()):
        out.append(Difference("Hladina", dl[k].name, "–", f"{dl[k].count} prvků",
                              "Hladina navíc (ve vzoru není)"))
    for k in sorted(tl.keys() & dl.keys()):
        t, d = tl[k], dl[k]
        if t.color is not None and d.color is not None and t.color != d.color:
            out.append(Difference("Barva", t.name, str(t.color), str(d.color), "Jiná převažující barva"))
        extra_colors = set(d.colors) - set(t.colors)
        if extra_colors and t.color == d.color:
            out.append(Difference("Barva", t.name, ", ".join(map(str, sorted(t.colors, key=str))),
                                  ", ".join(map(str, sorted(d.colors, key=str))),
                                  "Některé prvky mají barvu, která ve vzoru na hladině není"))
        if t.linetype and d.linetype and t.linetype != d.linetype:
            out.append(Difference("Styl čáry", t.name, t.linetype, d.linetype, "Jiný převažující styl čáry"))
        tg, dg = t.geom, d.geom
        if tg and dg and tg != dg:
            out.append(Difference("Typ geometrie", t.name, tg.label, dg.label, "Jiný převažující typ prvků"))
    for b in sorted(set(template.blocks) - set(drawing.blocks)):
        out.append(Difference("Buňka", b, f"{template.blocks[b]}×", "–", "Buňka ze vzoru není použita"))
    for b in sorted(set(drawing.blocks) - set(template.blocks)):
        out.append(Difference("Buňka", b, "–", f"{drawing.blocks[b]}×", "Buňka navíc (ve vzoru není)"))
    return out
