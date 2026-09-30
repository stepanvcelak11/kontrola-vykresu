"""Pravidla kontrol atributů (číselník prvků).

Pravidlo popisuje jeden typ prvku (kód) – na jaké hladině má být, jakou
barvou a stylem čáry, jakého typu geometrie je, jaké atributy musí mít
a jaké hodnoty jsou povolené. Pravidla vznikají importem tabulky od
učitele, ze vzorového výkresu nebo ručně a ukládají se do YAML.
"""

from __future__ import annotations

import fnmatch
import functools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .model import Feature, GeomType

CODE_ATTRS = ("KOD", "KÓD", "CODE", "KOD_PRVKU", "KODPRVKU", "KOD_ZPMZ", "TYP")

# Výchozí barevná tabulka MicroStationu (color.tbl) – barvy 0–15. Ostatní barvy (16–255) se
# liší podle nastavení MicroStationu; přesnou tabulku lze načíst (Nastavení kontrol →
# „Načíst barevnou tabulku MicroStationu“), pak se porovnává všech 256 barev.
MICROSTATION_COLORS = {
    0: (255, 255, 255), 1: (0, 0, 255), 2: (0, 255, 0), 3: (255, 0, 0), 4: (255, 255, 0),
    5: (255, 0, 255), 6: (255, 127, 0), 7: (0, 255, 255), 8: (64, 64, 64), 9: (192, 192, 192),
    10: (254, 0, 96), 11: (160, 224, 0), 12: (0, 254, 160), 13: (128, 0, 160), 14: (176, 176, 176),
    15: (0, 240, 240),
}

# Názvy barev se převádějí na RGB, takže fungují pro obě palety (MicroStation i AutoCAD).
COLOR_NAMES = {
    "červená": "#FF0000", "cervena": "#FF0000", "red": "#FF0000",
    "žlutá": "#FFFF00", "zluta": "#FFFF00", "yellow": "#FFFF00",
    "zelená": "#00FF00", "zelena": "#00FF00", "green": "#00FF00",
    "azurová": "#00FFFF", "azurova": "#00FFFF", "tyrkysová": "#00FFFF", "cyan": "#00FFFF",
    "modrá": "#0000FF", "modra": "#0000FF", "blue": "#0000FF",
    "purpurová": "#FF00FF", "purpurova": "#FF00FF", "fialová": "#FF00FF", "fialova": "#FF00FF",
    "magenta": "#FF00FF", "bílá": "#FFFFFF", "bila": "#FFFFFF", "white": "#FFFFFF",
    "černá": "#FFFFFF", "cerna": "#FFFFFF", "black": "#FFFFFF",  # černá na bílém = bílá na černém
    "tmavě šedá": "#404040", "tmave seda": "#404040", "světle šedá": "#C0C0C0", "svetle seda": "#C0C0C0",
    "šedá": "#808080", "seda": "#808080", "gray": "#808080", "grey": "#808080",
    "hnědá": "#A0522D", "hneda": "#A0522D", "brown": "#A0522D",
    "oranžová": "#FF7F00", "oranzova": "#FF7F00", "orange": "#FF7F00",
}

COLOR_TOLERANCE = 40  # max. vzdálenost v RGB, kdy se barvy považují za shodné

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


ALT_SPLIT = re.compile(r"\s*[|;]\s*|\s*,\s*(?=\S)")


def split_alternatives(value: Any) -> list[str]:
    """„0|2.09–2.17|5.30“ nebo „0,2,4,7“ → jednotlivé povolené hodnoty (i rozsahy)."""
    if value is None:
        return []
    return [p for p in ALT_SPLIT.split(str(value).strip()) if p]


_RANGE = re.compile(r"^\s*([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)\s*[–—-]\s*([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)\s*$")


def _code_key(s: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p.upper() for p in re.split(r"[.\s]+", s.strip()) if p)


def code_in_range(pattern: str, value: str) -> bool:
    """Shoda s hodnotou nebo rozsahem kódů značek: „2.09–2.17“ obsahuje „2.12“, „4.01-4.20“ obsahuje „4.02“."""
    pattern, value = pattern.strip(), value.strip()
    m = _RANGE.match(pattern)
    if m and "." in pattern:
        lo, hi, v = _code_key(m.group(1)), _code_key(m.group(2)), _code_key(value)
        if len(lo) == len(hi) == len(v) and lo[:-1] == hi[:-1] == v[:-1]:
            try:
                return lo <= v <= hi
            except TypeError:
                return False
        return False
    return fnmatch.fnmatchcase(value.upper(), pattern.upper())


def block_matches(pattern: str, name: str) -> bool:
    """Shoda názvu buňky s pravidlem. MicroStation při exportu přidává k buňce pořadí („9.12_153“)."""
    names = {name.strip().upper()}
    base = re.sub(r"_\d+$", "", name.strip())
    names.add(base.upper())
    for alt in split_alternatives(pattern):
        if any(code_in_range(alt, n) for n in names):
            return True
    return False


def parse_color(value: Any) -> int | str | None:
    """Barva: číslo ACI, název ("červená") nebo "#RRGGBB"; alternativy „6|0“ zůstanou jako text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if "|" in s or ";" in s:
        parts = [parse_color(p) for p in split_alternatives(s)]
        if parts and all(p is not None for p in parts):
            return "|".join(str(p) for p in parts)
        return None
    if not s or s.lower() in ("bylayer", "dle hladiny", "-"):
        return None
    if s.startswith("#") and len(s) == 7:
        return s.upper()
    m = re.match(r"^\s*(\d{1,3})\b", s)
    if m:
        return int(m.group(1))
    low = s.lower()
    for name in sorted(COLOR_NAMES, key=len, reverse=True):
        if low.startswith(name):
            return COLOR_NAMES[name]
    return None


def color_rgb(value: int | str, palette: str = "microstation",
              table: dict[int, tuple[int, int, int]] | None = None) -> tuple[int, int, int] | None:
    """RGB barvy z pravidla. Pro MicroStation se použije načtená tabulka, jinak výchozí barvy 0–15."""
    if isinstance(value, str) and value.startswith("#"):
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    if isinstance(value, int):
        if palette == "microstation":
            if table and value in table:
                return table[value]
            return MICROSTATION_COLORS.get(value)
        from ezdxf import colors
        if 1 <= value <= 255:
            return tuple(colors.aci2rgb(value))  # type: ignore[return-value]
    return None


def _autocad_palette() -> dict[int, tuple[int, int, int]]:
    """Paleta ACI, jak ji používá AutoCAD (a MicroStation při exportu do DXF).

    Liší se od palety ezdxf v odstínech 10–249 (jasy 100/80/60/50/30 %) a v šedých 250–255.
    """
    import colorsys
    pal = {1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255), 5: (0, 0, 255),
           6: (255, 0, 255), 7: (255, 255, 255), 8: (128, 128, 128), 9: (192, 192, 192)}
    levels = (1.0, 0.8, 0.6, 0.5, 0.3)
    for i in range(10, 250):
        k = i % 10
        r, g, b = colorsys.hsv_to_rgb(((i - 10) // 10) * 15 / 360, 1.0 if k % 2 == 0 else 0.5, levels[k // 2])
        pal[i] = (round(r * 255), round(g * 255), round(b * 255))
    for i, g in zip(range(250, 256), (51, 91, 132, 173, 214, 255)):
        pal[i] = (g, g, g)
    return pal


AUTOCAD_ACI = _autocad_palette()


def _ezdxf_palette() -> dict[int, tuple[int, int, int]]:
    from ezdxf import colors
    return {i: tuple(colors.aci2rgb(i)) for i in range(1, 256)}  # type: ignore[misc]


_EZDXF_ACI: dict[int, tuple[int, int, int]] = {}


@functools.lru_cache(maxsize=4096)
def rgb_to_aci(rgb: tuple[int, int, int]) -> frozenset[int]:
    """Čísla ACI, na která převede RGB export do DXF (MicroStation: nejbližší barva palety AutoCADu).

    Paleta ezdxf (starší paleta AutoCADu) dává u tmavších odstínů jiná čísla – MicroStation ji nepoužívá."""
    out = set()
    pal = AUTOCAD_ACI
    out.add(min(pal, key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], rgb))))
    return frozenset(out)


def ms_index_for_aci(aci: int, table: dict[int, tuple[int, int, int]] | None = None) -> int | None:
    """Číslo barvy MicroStationu, ze kterého mohlo při exportu vzniknout dané ACI (nejpodobnější)."""
    tab = dict(MICROSTATION_COLORS)
    if table:
        tab.update(table)
    cands = [i for i, c in tab.items() if aci in rgb_to_aci(tuple(c))]
    if not cands:
        return None
    ref = AUTOCAD_ACI.get(aci, (255, 255, 255))
    return min(cands, key=lambda i: (rgb_distance(tab[i], ref), i))


def has_true_color(f: Feature) -> bool:
    """Má prvek skutečnou barvu (RGB)? Výkres z MicroStationu v DXF má jen čísla ACI."""
    if f.color_aci is None or not 1 <= f.color_aci <= 255:
        return True
    if not _EZDXF_ACI:
        _EZDXF_ACI.update(_ezdxf_palette())
    return tuple(f.color_rgb) != _EZDXF_ACI[f.color_aci]


def rgb_distance(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def nearest_ms_index(rgb: tuple[int, int, int], table: dict[int, tuple[int, int, int]] | None = None
                     ) -> int | None:
    """Číslo barvy MicroStationu, které odpovídá RGB (nebo None, pokud žádné není dost blízko)."""
    tab = dict(MICROSTATION_COLORS)
    if table:
        tab.update(table)
    best, dist = None, COLOR_TOLERANCE
    for idx, c in tab.items():
        d = rgb_distance(c, rgb)
        if d < dist:
            best, dist = idx, d
    return best


def load_ms_color_table(path: str | Path) -> dict[int, tuple[int, int, int]]:
    """Načte barevnou tabulku MicroStationu.

    Podporované formáty:
      * binární ``*.tbl`` z MicroStationu – 256 trojic RGB (768 bajtů, případně s hlavičkou),
      * textový soubor / CSV: na řádku ``číslo r g b`` nebo ``číslo;#RRGGBB``.
    """
    p = Path(path)
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        is_text = all(ch.isprintable() or ch in "\r\n\t" for ch in text[:2000])
    except UnicodeDecodeError:
        is_text = False
    table: dict[int, tuple[int, int, int]] = {}
    if is_text:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "//")) and not re.match(r"^#[0-9A-Fa-f]{6}", line):
                continue
            m = re.match(r"^(\d{1,3})\s*[;,\s]\s*#?([0-9A-Fa-f]{6})\s*$", line)
            if m:
                h = m.group(2)
                table[int(m.group(1))] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                continue
            nums = [int(x) for x in re.findall(r"\d+", line)]
            if len(nums) >= 4 and nums[0] <= 255 and all(0 <= v <= 255 for v in nums[1:4]):
                table[nums[0]] = (nums[1], nums[2], nums[3])
        if not table:
            raise ValueError("V souboru nejsou řádky ve tvaru „číslo r g b“ ani „číslo;#RRGGBB“.")
        return table
    if len(raw) < 768:
        raise ValueError(f"Soubor má {len(raw)} bajtů, barevná tabulka musí mít aspoň 768 (256 × RGB).")
    data = raw[len(raw) - 768:] if len(raw) != 768 else raw  # případná hlavička je na začátku
    trip = [tuple(data[3 * i:3 * i + 3]) for i in range(256)]
    # MicroStation ukládá v color.tbl nejdřív barvu pozadí (255) a pak barvy 0–254.
    # Rozhodne shoda se známými výchozími barvami 0–15.
    direct = sum(trip[i] == MICROSTATION_COLORS[i] for i in range(16))
    shifted = sum(trip[i + 1] == MICROSTATION_COLORS[i] for i in range(16))
    if shifted > direct:
        for i in range(255):
            table[i] = trip[i + 1]
        table[255] = trip[0]
    else:
        for i in range(256):
            table[i] = trip[i]
    return table


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


# Typy prvků MicroStationu (sloupec „PRVKY“ ve směrnici; stejné názvy používá protokol GISoft)
MS_ELEMENT_NAMES = {
    2: "Buňka", 3: "Úsečka", 4: "Lomená čára", 6: "Tvar", 7: "Textový uzel", 11: "Křivka",
    12: "Komplexní řetězec", 14: "Komplexní tvar", 15: "Elipsa", 16: "Oblouk", 17: "Text",
    22: "Bodový řetězec",
}


def parse_element_types(value: Any) -> list[int]:
    """„3,4,15,16“ → [3, 4, 15, 16]; „2.0“ → [2]."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = re.split(r"[,;\s]+", str(value).strip())
    out = []
    for it in items:
        try:
            n = int(float(str(it).replace(",", ".")))
        except ValueError:
            continue
        if n in MS_ELEMENT_NAMES and n not in out:
            out.append(n)
    return out


def geometry_from_element_types(types: list[int]) -> GeomType | None:
    if not types:
        return None
    s = set(types)
    if s <= {17, 7}:
        return GeomType.TEXT
    if s == {2}:
        return GeomType.BOD
    if s <= {6, 14}:
        return GeomType.POLYGON
    if s & {3, 4, 11, 12, 15, 16, 22}:
        return GeomType.LINIE
    return None


def feature_element_type(f: Feature) -> int | None:
    """Typ prvku MicroStationu, kterému odpovídá entita DXF."""
    t = f.dxftype
    if t in ("LINE", "POINT"):
        return 3  # bod MicroStationu = úsečka nulové délky
    if t in ("LWPOLYLINE", "POLYLINE"):
        return 6 if f.closed else 4
    if t == "ARC":
        return 16
    if t in ("CIRCLE", "ELLIPSE"):
        return 15
    if t == "SPLINE":
        return 11
    if t == "INSERT":
        return 2
    if t == "TEXT":
        return 17
    if t == "MTEXT":
        return 7
    return None


_LEVEL_NUM = re.compile(r"^(?:vrstva|level|hladina|lv|layer|úroveň|uroven)?[\s_\-]*0*(\d+)$", re.IGNORECASE)


def layer_number(layer: str) -> int | None:
    """Číslo hladiny z názvu: „Vrstva 7“, „Level 7“, „LV07“, „7“ → 7."""
    m = _LEVEL_NUM.match(layer.strip())
    return int(m.group(1)) if m else None


def layer_matches(pattern: str, layer: str) -> bool:
    """Hladina odpovídá vzoru: číslo vrstvy MicroStationu, přesný název nebo zástupné znaky (*, ?)."""
    p = str(pattern).strip()
    if p.isdigit():
        return layer_number(layer) == int(p)
    return fnmatch.fnmatchcase(layer.upper(), p.upper())


@dataclass
class Rule:
    kod: str
    nazev: str = ""
    geometrie: GeomType | None = None
    hladina: str | None = None
    barva: int | str | None = None
    styl_cary: str | None = None  # název, číslo stylu MicroStationu, nebo seznam „0,2,4,7“
    tloustka: float | str | None = None  # číslo, nebo alternativy „0|1“
    blok: str | None = None  # název buňky, alternativy a rozsahy „4.01–4.20|4.23“
    povinne_atributy: list[str] = field(default_factory=list)
    povolene_hodnoty: dict[str, list[str]] = field(default_factory=dict)
    text: TextRule | None = None
    obrazek: str | None = None
    poznamka: str | None = None
    zdroj: str | None = None  # odkud pravidlo vzniklo (řádek tabulky, vzor…)
    typy_prvku: list[int] = field(default_factory=list)  # povolené typy prvků MicroStationu
    vyska_textu: float | None = None
    sirka_textu: float | None = None
    font: str | None = None
    zarovnani: str | None = None  # např. „vlevo nahoře“
    meritko_stylu: float | None = None  # měřítko uživatelského stylu čáry (např. 0,5)
    meritko_bunky: float | None = None  # měřítko buňky (značky)
    tucne: bool | None = None  # řez písma (None = nekontroluje se)
    kurziva: bool | None = None
    topologie: bool = True  # False = prvky se nekontrolují topologicky (vstupy, sdružené značky)

    def __post_init__(self):
        if self.geometrie is not None and not isinstance(self.geometrie, GeomType):
            self.geometrie = GeomType.parse(self.geometrie)

    @property
    def label(self) -> str:
        return f"{self.kod} {self.nazev}".strip()

    def matches_layer(self, layer: str) -> bool:
        if not self.hladina:
            return False
        return layer_matches(self.hladina, layer)

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
        if self.typy_prvku:
            d["typy_prvku"] = list(self.typy_prvku)
        for k in ("vyska_textu", "sirka_textu", "font", "zarovnani", "tucne", "kurziva", "meritko_stylu",
                  "meritko_bunky"):
            v = getattr(self, k)
            if v not in (None, ""):
                d[k] = v
        if not self.topologie:
            d["topologie"] = False
        for k in ("obrazek", "poznamka", "zdroj"):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        tl = parse_weight(d.get("tloustka"))
        attrs = [a.upper() for a in split_list(d.get("povinne_atributy"))]

        def fnum(k):
            try:
                v = d.get(k)
                return float(str(v).replace(",", ".")) if v not in (None, "") else None
            except (TypeError, ValueError):
                return None
        types = parse_element_types(d.get("typy_prvku"))
        return cls(
            kod=str(d.get("kod", "")).strip(),
            nazev=str(d.get("nazev", "") or "").strip(),
            geometrie=GeomType.parse(d.get("geometrie")) or geometry_from_element_types(types),
            typy_prvku=types,
            vyska_textu=fnum("vyska_textu"),
            sirka_textu=fnum("sirka_textu"),
            font=(str(d["font"]).strip() if d.get("font") else None),
            zarovnani=(str(d["zarovnani"]).strip() if d.get("zarovnani") else None),
            tucne=parse_bool(d.get("tucne")),
            meritko_stylu=fnum("meritko_stylu"),
            meritko_bunky=fnum("meritko_bunky"),
            kurziva=parse_bool(d.get("kurziva")),
            topologie=bool(d.get("topologie", True)),
            hladina=(str(d["hladina"]).strip() if d.get("hladina") else None),
            barva=parse_color(d.get("barva")),
            styl_cary=norm_style(d.get("styl_cary")),
            tloustka=tl,
            blok=(str(d["blok"]).strip() if d.get("blok") else None),
            povinne_atributy=attrs,
            povolene_hodnoty=parse_allowed_values(d.get("povolene_hodnoty"), attrs[0] if attrs else None),
            text=TextRule.from_dict(d.get("text")),
            obrazek=d.get("obrazek") or None,
            poznamka=d.get("poznamka") or None,
            zdroj=d.get("zdroj") or None,
        )


def norm_style(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if re.search(r"[,;|]|[–—]", str(v)):
        return str(v).strip()
    return normalize_linetype(v)


def parse_weight(value: Any) -> float | str | None:
    """Tloušťka: číslo, nebo alternativy „0|1“ (text)."""
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parts = split_alternatives(str(value).replace(",", "."))
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except ValueError:
            m = re.search(r"\d+(?:\.\d+)?", p)
            if m:
                nums.append(float(m.group(0)))
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    return "|".join(fmt_plain(n) for n in nums)


def fmt_plain(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def weight_values(value: float | str | None) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    return [float(p) for p in str(value).split("|") if p.strip()]


def parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    t = str(value).strip().lower()
    if t in ("ano", "a", "yes", "y", "true", "1", "x"):
        return True
    if t in ("ne", "n", "no", "false", "0"):
        return False
    return None


def font_style(font: str | None) -> tuple[bool, bool]:
    """Odhad řezu písma z názvu stylu a souboru fontu → (tučně, kurzíva).

    „Style-Arial Narrow IF (ARIALNI.TTF)“ → kurzíva, „ARIALNB.TTF“ / „arialbd.ttf“ → tučně."""
    t = (font or "")
    m = re.search(r"\(([^()]*)\)\s*$", t)
    stem = re.sub(r"\.[a-z0-9]+$", "", (m.group(1) if m else "").strip().lower())
    name = t[:m.start()] if m else t
    low = name.lower()
    bold = bool(re.search(r"\b(bold|bd)\b|\b(tučn|tucn)", low)) or bool(re.search(r"(bd|bi|nb|z)$", stem)) \
        or stem.endswith("b") and len(stem) > 4
    italic = bool(re.search(r"\b(italic|it|if)\b|\bkurz", low)) or bool(re.search(r"(i|bi|z|it)$", stem)) \
        and len(stem) > 4
    return bold, italic


@dataclass
class RuleSet:
    pravidla: list[Rule] = field(default_factory=list)
    povolene_hladiny: list[str] = field(default_factory=list)  # hladiny povolené i bez kódu
    paleta: str = "microstation"  # jak číst čísla barev: microstation (color.tbl) / autocad (ACI)
    rozsah: dict | str | None = None  # {xmin, ymin, xmax, ymax} nebo "sjtsk"
    barevna_tabulka: dict[int, tuple[int, int, int]] = field(default_factory=dict)  # načtený color.tbl
    mapa_tloustek: dict[int, float] = field(default_factory=dict)  # tloušťka MicroStationu → mm v DXF
    meritko: int | None = None  # výšky/šířky textu v pravidlech jsou v mm na papíře v tomto měřítku

    def text_size(self, value: float | None) -> float | None:
        """Výška/šířka textu z pravidla převedená na jednotky výkresu (m)."""
        if value is None:
            return None
        return value * self.meritko / 1000.0 if self.meritko else value

    def expected_weights(self, r: Rule) -> tuple[list[float], list[int]]:
        """Povolené tloušťky v mm (DXF) a tloušťky MicroStationu, které nejde převést."""
        out, unknown = [], []
        for w in weight_values(r.tloustka):
            if self.paleta == "microstation" and float(w).is_integer() and 0 <= w <= 31:
                mm = self.mapa_tloustek.get(int(w))
                if mm is None:
                    unknown.append(int(w))
                else:
                    out.append(mm)
            else:
                out.append(w)
        return out, unknown

    def rule_rgb(self, value) -> tuple[int, int, int] | None:
        return color_rgb(value, self.paleta, self.barevna_tabulka)

    def describe_feature_color(self, f: Feature) -> str:
        """Barva prvku v soustavě pravidel (číslo MicroStationu, jinak ACI/RGB)."""
        if self.paleta == "microstation":
            if not has_true_color(f):
                idx = ms_index_for_aci(f.color_aci, self.barevna_tabulka)
                return str(idx) if idx is not None else f"ACI {f.color_aci}"
            idx = nearest_ms_index(f.color_rgb, self.barevna_tabulka)
            if idx is not None:
                return str(idx)
            return "#%02X%02X%02X" % tuple(f.color_rgb)
        return str(f.color_aci)

    # ------------------------------------------------------------ přiřazení kódu
    def by_code(self) -> dict[str, Rule]:
        return {r.kod: r for r in self.pravidla}

    def text_layers(self) -> set[str]:
        return {r.text.hladina.upper() for r in self.pravidla if r.text and r.text.hladina}

    def allowed_layer(self, layer: str) -> bool:
        patterns = [r.hladina for r in self.pravidla if r.hladina] + list(self.povolene_hladiny)
        patterns += [r.text.hladina for r in self.pravidla if r.text and r.text.hladina]
        return any(layer_matches(p, layer) for p in patterns)

    def explicit_layer(self, layer: str) -> bool:
        return any(layer_matches(p, layer) for p in self.povolene_hladiny)

    def resolve(self, f: Feature) -> Rule | None:
        """Najde pravidlo (kód) pro prvek."""
        codes = self.by_code()
        for key in CODE_ATTRS:
            v = f.attributes.get(key)
            if v and str(v).strip() in codes:
                return codes[str(v).strip()]
        if f.block_name:
            by_block = [r for r in self.pravidla if r.blok and block_matches(r.blok, f.block_name)]
            if by_block:
                on_layer = [r for r in by_block if r.matches_layer(f.layer)]
                return max(on_layer or by_block, key=lambda r: self._score(r, f))
        cands = [r for r in self.pravidla if r.matches_layer(f.layer) and not r.blok]
        if not cands:
            cands = [r for r in self.pravidla if r.matches_layer(f.layer)]
        if f.geom_type == GeomType.TEXT and not any(r.geometrie == GeomType.TEXT for r in cands) and cands:
            # text na hladině linií (např. popis sítě „ve vrstvě a barvě dle sítě“) – pravidlo pro text bez hladiny
            free = [r for r in self.pravidla if not r.hladina and not r.blok and r.geometrie == GeomType.TEXT]
            if free:
                return max(free, key=lambda r: self._score(r, f) + (
                    2 if r.font and re.sub(r"\W", "", r.font.lower()) in re.sub(r"\W", "", (f.font or "").lower())
                    else 0))
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
        if r.barva is not None and color_matches(r.barva, f, self.paleta, self.barevna_tabulka):
            s += 2
        if r.styl_cary and linetype_matches(r.styl_cary, f.linetype):
            s += 2
        if r.tloustka is not None:
            ws, _ = self.expected_weights(r)
            if any(abs(w - f.lineweight) < 0.06 for w in ws):
                s += 1
        return s

    # ------------------------------------------------------------ YAML
    def to_dict(self) -> dict:
        d: dict[str, Any] = {"paleta": self.paleta}
        if self.meritko:
            d["meritko"] = int(self.meritko)
        if self.mapa_tloustek:
            d["mapa_tloustek"] = {int(k): float(v) for k, v in sorted(self.mapa_tloustek.items())}
        if self.barevna_tabulka:
            d["barevna_tabulka"] = {i: "#%02X%02X%02X" % c for i, c in sorted(self.barevna_tabulka.items())}
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
            paleta=str(d.get("paleta", "microstation")).lower(),
            rozsah=d.get("rozsah"),
        )
        try:
            rs.meritko = int(d["meritko"]) if d.get("meritko") else None
        except (TypeError, ValueError):
            rs.meritko = None
        for k, v in (d.get("mapa_tloustek") or {}).items():
            try:
                rs.mapa_tloustek[int(k)] = float(v)
            except (TypeError, ValueError):
                pass
        for k, v in (d.get("barevna_tabulka") or {}).items():
            rgb = color_rgb(str(v)) if str(v).startswith("#") else None
            if rgb is not None:
                rs.barevna_tabulka[int(k)] = rgb
        return rs

    def save(self, path: str | Path, header: str | None = None):
        text = yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False, width=120)
        if header:
            text = "".join(f"# {line}\n" for line in header.splitlines()) + text
        from .safeio import write_text_atomic
        write_text_atomic(path, text)

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
        if other.meritko:
            self.meritko = other.meritko
        for k, v in other.mapa_tloustek.items():
            self.mapa_tloustek.setdefault(k, v)
        if other.barevna_tabulka and not self.barevna_tabulka:
            self.barevna_tabulka = dict(other.barevna_tabulka)
        return added, replaced


def _color_alts(expected: int | str) -> list[int | str]:
    if isinstance(expected, str) and "|" in expected:
        return [c for c in (parse_color(p) for p in expected.split("|")) if c is not None]
    return [expected]


def color_known(expected: int | str, palette: str = "microstation", table=None) -> bool:
    """Lze barvu z pravidla ověřit? (U MicroStationu bez načtené tabulky jen barvy 0–15.)"""
    return all(color_rgb(c, palette, table) is not None for c in _color_alts(expected))


def color_matches(expected: int | str, f: Feature, palette: str = "microstation", table=None) -> bool:
    """Shoduje se barva prvku s pravidlem? Neznámou barvu (nelze ověřit) bere jako shodu."""
    alts = _color_alts(expected)
    if len(alts) > 1:
        return any(color_matches(c, f, palette, table) for c in alts)
    ms = f.attributes.get("MS_BARVA") if f.attributes else None
    if ms is not None and palette == "microstation" and isinstance(expected, int):
        return int(ms) == expected  # výkres čtený přímo z DGN: přesné číslo barvy
    if isinstance(expected, int) and palette == "autocad" and f.color_aci is not None:
        if expected == f.color_aci:
            return True
    rgb = color_rgb(expected, palette, table)
    if rgb is None:
        return True
    if palette == "microstation" and not has_true_color(f):
        # DXF z MicroStationu: barva byla při exportu převedena na nejbližší ACI
        return f.color_aci in rgb_to_aci(tuple(rgb))
    return rgb_distance(rgb, f.color_rgb) < COLOR_TOLERANCE


def linetype_matches(expected: str, actual: str) -> bool:
    """Shoda stylu čáry; ``expected`` smí být seznam povolených stylů („0,2,4,7“, „0|2.09–2.17“)."""
    if expected and re.search(r"[,;|]", str(expected)):
        return any(linetype_matches(e, actual) for e in split_alternatives(expected))
    if expected and _RANGE.match(str(expected)) and "." in str(expected):
        return code_in_range(str(expected), normalize_linetype(actual) or "")
    return _linetype_matches_one(expected, actual)


def _linetype_matches_one(expected: str, actual: str) -> bool:
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
