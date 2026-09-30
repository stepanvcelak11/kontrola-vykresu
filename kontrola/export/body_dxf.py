"""Body ze seznamu souřadnic rovnou do DXF – značka bodu, číslo a výška na vrstvách podle Směrnice.

Nahrazuje ruční import bodů z Gromy do MicroStationu: DXF se otevře nebo připojí v MicroStationu
a body už mají správnou vrstvu, barvu, tloušťku, písmo, výšku textu i zarovnání z pravidel.

Rozmístění popisů jako Groma: číslo bodu vpravo nahoře, výška vpravo dole.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import ezdxf

from ..checks.seznam import ListPoint, short_numbers
from ..model import GeomType
from ..rules import AUTOCAD_ACI, Rule, RuleSet, color_rgb, layer_matches, weight_values


def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def guess_rules(rs: RuleSet) -> dict[str, Rule | None]:
    """Najde v pravidlech pravidlo pro značku bodu, číslo bodu a výšku bodu."""
    def score(r: Rule, want: str) -> int:
        n = _norm(f"{r.nazev} {r.kod} {r.hladina}")
        if want == "bod":
            if r.geometrie not in (GeomType.BOD, None) or r.font or r.vyska_textu:
                return 0
            s = 3 * ("podrobn" in n) + 2 * ("poloha" in n or "element" in n) + ("bod" in n)
            return s if "bod" in n and "cisl" not in n and "vys" not in n and "bp+" not in n else 0
        if r.geometrie not in (GeomType.TEXT, None) or not (r.font or r.vyska_textu or r.geometrie == GeomType.TEXT):
            return 0
        if want == "cislo":
            return (3 * ("cisl" in n) + ("bod" in n) + ("podrobn" in n) + ("popis" in n)) if "cisl" in n and \
                "bod" in n and "bp+" not in n and "parc" not in n else 0
        if want == "vyska":
            return (3 * ("vysk" in n) + ("bod" in n) + ("podrobn" in n)) if "vysk" in n and "bod" in n and \
                "tisk" not in n and "bp+" not in n else 0
        return 0
    out = {}
    for want in ("bod", "cislo", "vyska"):
        best = max(rs.pravidla, key=lambda r: score(r, want), default=None)
        out[want] = best if best is not None and score(best, want) > 0 else None
    return out


def _layer_name(r: Rule, existing: list[str]) -> str:
    """Název vrstvy: jak se jmenuje ve výkresu (např. „Vrstva 58“), jinak podle pravidla."""
    h = str(r.hladina or "0").split("|")[0].strip()
    for name in existing:
        if layer_matches(h, name):
            return name
    return f"Vrstva {h}" if h.isdigit() else h


def _aci(rgb) -> int:
    return min(AUTOCAD_ACI, key=lambda i: sum((a - b) ** 2 for a, b in zip(AUTOCAD_ACI[i], rgb)))


@dataclass
class Moznosti:
    kratka_cisla: bool = True
    vysky: bool = True
    desetinna: int = 2
    zaporne: bool = True  # S-JTSK v MicroStationu záporně (−Y, −X)


def export_points_dxf(pts: list[ListPoint], rs: RuleSet, out: str | Path, rules: dict[str, Rule | None] | None = None,
                      opts: Moznosti | None = None, existing_layers: list[str] | None = None) -> dict:
    """Vytvoří DXF s body. Vrací souhrn {bodů, čísel, výšek, vrstvy}."""
    opts = opts or Moznosti()
    rules = rules or guess_rules(rs)
    existing = list(existing_layers or [])
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    info = {"bodu": 0, "cisel": 0, "vysek": 0, "vrstvy": {}}

    def attribs(r: Rule) -> dict:
        name = _layer_name(r, existing)
        if name not in doc.layers:
            doc.layers.add(name)
        info["vrstvy"][name] = r.nazev or r.kod
        a = {"layer": name, "linetype": "CONTINUOUS", "color": 7, "lineweight": 0}  # nic „dle vrstvy“
        if r.barva is not None:
            rgb = color_rgb(r.barva if not isinstance(r.barva, str) or r.barva.startswith("#") else
                            int(re.sub(r"\D", "", r.barva) or 0), rs.paleta, rs.barevna_tabulka)
            if rgb is not None:
                a["color"] = _aci(rgb)
                a["true_color"] = ezdxf.colors.rgb2int(rgb)
        if r.tloustka is not None and rs.mapa_tloustek:
            w = weight_values(r.tloustka)
            if w:
                mm = rs.mapa_tloustek.get(int(w[0])) if float(w[0]).is_integer() else float(w[0])
                if mm is not None:
                    a["lineweight"] = int(round(mm * 100))
        return a

    def text_style(r: Rule) -> str:
        if not r.font:
            return "Standard"
        base = r.font.strip()
        name = base + (" Bold" if r.tucne else "") + (" Italic" if r.kurziva else "")
        if name not in doc.styles:
            n = _norm(base)
            if "arial" in n:  # TrueType jako v MicroStationu (arialn.ttf, arialni.ttf…)
                stem = ("arialn" if "narrow" in n else "arial") + ("b" if r.tucne else "") + \
                       ("i" if r.kurziva else "")
                font = stem.replace("arialb", "arialbd") + ".ttf" if not r.kurziva or r.tucne else stem + ".ttf"
            else:
                font = base.lower().replace(" ", "_") + ".shx"
            doc.styles.add(name, font=font)
        return name

    rb, rc, rv = rules.get("bod"), rules.get("cislo"), rules.get("vyska")
    sgn = -1.0 if opts.zaporne else 1.0
    for p in pts:
        y, x = abs(p.a) * sgn, abs(p.b) * sgn
        if rb is not None:
            a = attribs(rb)
            if 3 in (rb.typy_prvku or []) or "nulov" in _norm(rb.poznamka or ""):
                msp.add_line((y, x), (y, x), dxfattribs=a)  # bod MicroStationu = úsečka nulové délky
            else:
                msp.add_point((y, x), dxfattribs=a)
            info["bodu"] += 1
        if rc is not None:
            h = rs.text_size(rc.vyska_textu) or 1.0
            w = rs.text_size(rc.sirka_textu) or h
            label = min(short_numbers(p.cislo), key=len) if opts.kratka_cisla else p.cislo
            a = attribs(rc)
            a.update(style=text_style(rc), height=h, width=w / h if h else 1.0)
            t = msp.add_text(label, dxfattribs=a)
            t.set_placement((y + 0.4 * h, x + 1.2 * h), align=ezdxf.enums.TextEntityAlignment.TOP_LEFT)
            info["cisel"] += 1
        if rv is not None and opts.vysky and p.z not in (None, 0.0):
            h = rs.text_size(rv.vyska_textu) or 1.0
            w = rs.text_size(rv.sirka_textu) or h
            a = attribs(rv)
            a.update(style=text_style(rv), height=h, width=w / h if h else 1.0)
            t = msp.add_text(f"{p.z:.{opts.desetinna}f}".replace(".", ","), dxfattribs=a)
            t.set_placement((y + 0.4 * h, x - 1.2 * h), align=ezdxf.enums.TextEntityAlignment.BOTTOM_LEFT)
            info["vysek"] += 1
    doc.saveas(out)
    return info
