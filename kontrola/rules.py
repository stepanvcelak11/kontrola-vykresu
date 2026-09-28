"""Pravidla kontrol atributů (číselník prvků).

Pravidlo popisuje jeden typ prvku (kód) – na jaké hladině má být, jakou
barvou a stylem čáry, jakého typu geometrie je, jaké atributy musí mít
a jaké hodnoty jsou povolené. Pravidla vznikají importem tabulky od
učitele, ze vzorového výkresu nebo ručně a ukládají se do YAML.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .model import Feature, GeomType

CODE_ATTRS = ("KOD", "KÓD", "CODE", "KOD_PRVKU", "KODPRVKU", "KOD_ZPMZ", "TYP")

# Výchozí barevná tabulka MicroStationu (color.tbl) – barvy 0–15.
MICROSTATION_COLORS = {
    0: (255, 255, 255), 1: (0, 0, 255), 2: (0, 255, 0), 3: (255, 0, 0), 4: (255, 255, 0),
    5: (255, 0, 255), 6: (255, 127, 0), 7: (0, 255, 255), 8: (64, 64, 64), 9: (192, 192, 192),
    10: (254, 0, 96), 11: (160, 224, 0), 12: (0, 254, 160), 13: (128, 0, 160), 14: (176, 176, 176),
    15: (0, 240, 240),
}

COLOR_NAMES = {
    "červená": 1, "cervena": 1, "red": 1, "žlutá": 2, "zluta": 2, "yellow": 2,
    "zelená": 3, "zelena": 3, "green": 3, "azurová": 4, "azurova": 4, "tyrkysová": 4, "cyan": 4,
    "modrá": 5, "modra": 5, "blue": 5, "purpurová": 6, "purpurova": 6, "fialová": 6, "fialova": 6,
    "magenta": 6, "bílá": 7, "bila": 7, "černá": 7, "cerna": 7, "white": 7, "black": 7,
    "šedá": 8, "seda": 8, "tmavě šedá": 8, "gray": 8, "grey": 8, "světle šedá": 9, "svetle seda": 9,
    "hnědá": 34, "hneda": 34, "brown": 34, "oranžová": 30, "oranzova": 30, "orange": 30,
}

LINETYPE_ALIASES = {
    "plná": "CONTINUOUS", "plna": "CONTINUOUS", "souvislá": "CONTINUOUS", "souvisla": "CONTINUOUS",
    "continuous": "CONTINUOUS", "solid": "CONTINUOUS", "0": "CONTINUOUS", "bylayer": "",
    "čárkovaná": "DASHED", "carkovana": "DASHED", "přerušovaná": "DASHED", "prerusovana": "DASHED",
    "tečkovaná": "DOT", "teckovana": "DOT", "čerchovaná": "DASHDOT", "cerchovana": "DASHDOT",
    "dvojčerchovaná": "DASHDOTDOT", "dvojcerchovana": "DASHDOTDOT",
}


def normalize_linetype(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    low = s.lower()
    if low in LINETYPE_ALIASES:
        return LINETYPE_ALIASES[low] or None
    return s.upper()


def parse_color(value: Any) -> int | str | None:
    """Barva: číslo ACI, název ("červená") nebo "#RRGGBB"."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s or s.lower() in ("bylayer", "dle hladiny", "-"):
        return None
    if s.startswith("#") and len(s) == 7:
        return s.upper()
    m = re.match(r"^\s*(\d{1,3})\b", s)
    if m:
        return int(m.group(1))
    low = s.lower()
    for name, aci in COLOR_NAMES.items():
        if low.startswith(name):
            return aci
    return None


def color_rgb(value: int | str, palette: str = "autocad") -> tuple[int, int, int] | None:
    if isinstance(value, str) and value.startswith("#"):
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    if isinstance(value, int):
        if palette == "microstation":
            return MICROSTATION_COLORS.get(value)
        from ezdxf import colors
        if 1 <= value <= 255:
            return tuple(colors.aci2rgb(value))  # type: ignore[return-value]
    return None


def split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s or s in ("-", "–"):
        return []
    return [p.strip() for p in re.split(r"[,;\n/|]+", s) if p.strip()]


def parse_allowed_values(value: Any, default_attr: str | None = None) -> dict[str, list[str]]:
    """Povolené hodnoty.

    Podporované zápisy:
      * slovník ``{DRUH: [lípa, dub]}`` (YAML),
      * ``DRUH=lípa,dub; MATERIAL=zděná,dřevěná``,
      * ``lípa, dub`` – platí pro první povinný atribut (``default_attr``).
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k).strip().upper(): split_list(v) for k, v in value.items()}
    s = str(value).strip()
    if not s or s in ("-", "–"):
        return {}
    out: dict[str, list[str]] = {}
    if "=" in s or re.search(r"\b[A-ZÁ-Ž_]{2,}\s*:", s):
        for part in re.split(r"[;\n]+", s):
            if not part.strip():
                continue
            m = re.match(r"^\s*([^=:]+?)\s*[=:]\s*(.*)$", part)
            if m:
                out[m.group(1).strip().upper()] = split_list(m.group(2).replace("/", ","))
        return out
    if default_attr:
        out[default_attr.upper()] = split_list(s)
    return out


@dataclass
class TextRule:
    """Požadavek na popis (text) prvku."""

    povinny: bool = False
    hladina: str | None = None  # na které hladině text leží
    atribut: str | None = None  # text se použije jako hodnota atributu
    uvnitr: bool = True  # u polygonu musí text ležet uvnitř

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"povinny": self.povinny}
        if self.hladina:
            d["hladina"] = self.hladina
        if self.atribut:
            d["atribut"] = self.atribut
        if not self.uvnitr:
            d["uvnitr"] = False
        return d

    @classmethod
    def from_dict(cls, d: Any) -> "TextRule | None":
        if not d:
            return None
        if d is True:
            return cls(povinny=True)
        return cls(povinny=bool(d.get("povinny", False)), hladina=d.get("hladina") or None,
                   atribut=(d.get("atribut") or None) and str(d.get("atribut")).upper(),
                   uvnitr=bool(d.get("uvnitr", True)))


@dataclass
class Rule:
    kod: str
    nazev: str = ""
    geometrie: GeomType | None = None
    hladina: str | None = None
    barva: int | str | None = None
    styl_cary: str | None = None
    tloustka: float | None = None
    blok: str | None = None
    povinne_atributy: list[str] = field(default_factory=list)
    povolene_hodnoty: dict[str, list[str]] = field(default_factory=dict)
    text: TextRule | None = None
    obrazek: str | None = None
    poznamka: str | None = None
    zdroj: str | None = None  # odkud pravidlo vzniklo (řádek tabulky, vzor…)

    @property
    def label(self) -> str:
        return f"{self.kod} {self.nazev}".strip()

    def matches_layer(self, layer: str) -> bool:
        if not self.hladina:
            return False
        return fnmatch.fnmatchcase(layer.upper(), self.hladina.upper())

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"kod": self.kod}
        if self.nazev:
            d["nazev"] = self.nazev
        if self.geometrie:
            d["geometrie"] = self.geometrie.value
        for k in ("hladina", "barva", "styl_cary", "tloustka", "blok"):
            v = getattr(self, k)
            if v not in (None, ""):
                d[k] = v
        if self.povinne_atributy:
            d["povinne_atributy"] = list(self.povinne_atributy)
        if self.povolene_hodnoty:
            d["povolene_hodnoty"] = {k: list(v) for k, v in self.povolene_hodnoty.items()}
        if self.text:
            d["text"] = self.text.to_dict()
        for k in ("obrazek", "poznamka", "zdroj"):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        tl = d.get("tloustka")
        try:
            tl = float(tl) if tl not in (None, "") else None
        except (TypeError, ValueError):
            tl = None
        attrs = [a.upper() for a in split_list(d.get("povinne_atributy"))]
        return cls(
            kod=str(d.get("kod", "")).strip(),
            nazev=str(d.get("nazev", "") or "").strip(),
            geometrie=GeomType.parse(d.get("geometrie")),
            hladina=(str(d["hladina"]).strip() if d.get("hladina") else None),
            barva=parse_color(d.get("barva")),
            styl_cary=normalize_linetype(d.get("styl_cary")),
            tloustka=tl,
            blok=(str(d["blok"]).strip() if d.get("blok") else None),
            povinne_atributy=attrs,
            povolene_hodnoty=parse_allowed_values(d.get("povolene_hodnoty"), attrs[0] if attrs else None),
            text=TextRule.from_dict(d.get("text")),
            obrazek=d.get("obrazek") or None,
            poznamka=d.get("poznamka") or None,
            zdroj=d.get("zdroj") or None,
        )


@dataclass
class RuleSet:
    pravidla: list[Rule] = field(default_factory=list)
    povolene_hladiny: list[str] = field(default_factory=list)  # hladiny povolené i bez kódu
    paleta: str = "autocad"  # jak číst čísla barev: autocad (ACI) / microstation
    rozsah: dict | str | None = None  # {xmin, ymin, xmax, ymax} nebo "sjtsk"

    # ------------------------------------------------------------ přiřazení kódu
    def by_code(self) -> dict[str, Rule]:
        return {r.kod: r for r in self.pravidla}

    def text_layers(self) -> set[str]:
        return {r.text.hladina.upper() for r in self.pravidla if r.text and r.text.hladina}

    def allowed_layer(self, layer: str) -> bool:
        up = layer.upper()
        patterns = [r.hladina for r in self.pravidla if r.hladina] + list(self.povolene_hladiny)
        patterns += [r.text.hladina for r in self.pravidla if r.text and r.text.hladina]
        return any(fnmatch.fnmatchcase(up, p.upper()) for p in patterns)

    def explicit_layer(self, layer: str) -> bool:
        up = layer.upper()
        return any(fnmatch.fnmatchcase(up, p.upper()) for p in self.povolene_hladiny)

    def resolve(self, f: Feature) -> Rule | None:
        """Najde pravidlo (kód) pro prvek."""
        codes = self.by_code()
        for key in CODE_ATTRS:
            v = f.attributes.get(key)
            if v and str(v).strip() in codes:
                return codes[str(v).strip()]
        if f.block_name:
            bn = f.block_name.upper()
            for r in self.pravidla:
                if r.blok and fnmatch.fnmatchcase(bn, r.blok.upper()):
                    return r
        cands = [r for r in self.pravidla if r.matches_layer(f.layer) and not r.blok]
        if not cands:
            cands = [r for r in self.pravidla if r.matches_layer(f.layer)]
        if not cands:
            return None
        if len(cands) == 1:
            r = cands[0]
            if (r.geometrie == GeomType.TEXT) != (f.geom_type == GeomType.TEXT):
                return None
            return r
        return max(cands, key=lambda r: self._score(r, f))

    def _score(self, r: Rule, f: Feature) -> float:
        s = 0.0
        is_text = f.geom_type == GeomType.TEXT
        if (r.geometrie == GeomType.TEXT) != is_text:
            s -= 10
        if r.geometrie == f.geom_type:
            s += 3
        elif r.geometrie == GeomType.POLYGON and f.geom_type == GeomType.LINIE:
            s += 1
        if r.barva is not None and color_matches(r.barva, f, self.paleta):
            s += 2
        if r.styl_cary and linetype_matches(r.styl_cary, f.linetype):
            s += 2
        if r.tloustka is not None and abs(r.tloustka - f.lineweight) < 0.06:
            s += 1
        return s

    # ------------------------------------------------------------ YAML
    def to_dict(self) -> dict:
        d: dict[str, Any] = {"paleta": self.paleta}
        if self.rozsah:
            d["rozsah"] = self.rozsah
        if self.povolene_hladiny:
            d["povolene_hladiny"] = list(self.povolene_hladiny)
        d["pravidla"] = [r.to_dict() for r in self.pravidla]
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "RuleSet":
        d = d or {}
        rs = cls(
            pravidla=[Rule.from_dict(x) for x in (d.get("pravidla") or []) if isinstance(x, dict)],
            povolene_hladiny=split_list(d.get("povolene_hladiny")),
            paleta=str(d.get("paleta", "autocad")).lower(),
            rozsah=d.get("rozsah"),
        )
        return rs

    def save(self, path: str | Path, header: str | None = None):
        text = yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False, width=120)
        if header:
            text = "".join(f"# {line}\n" for line in header.splitlines()) + text
        Path(path).write_text(text, encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "RuleSet":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data if isinstance(data, dict) else {})

    def merge(self, other: "RuleSet", replace: bool = True) -> tuple[int, int]:
        """Sloučí pravidla, vrací (přidáno, nahrazeno)."""
        added = replaced = 0
        idx = {r.kod: i for i, r in enumerate(self.pravidla)}
        for r in other.pravidla:
            if r.kod in idx:
                if replace:
                    self.pravidla[idx[r.kod]] = r
                    replaced += 1
            else:
                idx[r.kod] = len(self.pravidla)
                self.pravidla.append(r)
                added += 1
        for h in other.povolene_hladiny:
            if h not in self.povolene_hladiny:
                self.povolene_hladiny.append(h)
        return added, replaced


def color_matches(expected: int | str, f: Feature, palette: str = "autocad") -> bool:
    if isinstance(expected, int) and palette != "microstation" and f.color_aci is not None:
        if expected == f.color_aci:
            return True
    rgb = color_rgb(expected, palette)
    if rgb is None:
        return isinstance(expected, int) and expected == f.color_aci
    return sum((a - b) ** 2 for a, b in zip(rgb, f.color_rgb)) ** 0.5 < 40


def linetype_matches(expected: str, actual: str) -> bool:
    e = normalize_linetype(expected)
    a = normalize_linetype(actual) or "CONTINUOUS"
    if not e:
        return True
    if e == a:
        return True
    de = "".join(c for c in e if c.isdigit())
    da = "".join(c for c in a if c.isdigit())
    if de and de == da and (e.isdigit() or a.isdigit()):
        return True
    return False


def describe_color(value: int | str | None) -> str:
    if value is None:
        return "–"
    return str(value)
