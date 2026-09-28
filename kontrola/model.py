"""Datový model načteného výkresu.

Každý prvek výkresu (linie, polygon, bod, buňka, text) je převeden na
:class:`Feature` s geometrií ve formátu shapely a se všemi atributy, které
se podařilo zjistit (hladina, barva, styl a tloušťka čáry, atributy bloku,
XDATA). Souřadnice jsou vždy v metrech.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shapely.geometry.base import BaseGeometry


class GeomType(str, Enum):
    """Typ geometrie prvku z pohledu kontrol."""

    BOD = "bod"
    LINIE = "linie"
    POLYGON = "polygon"
    TEXT = "text"

    @property
    def label(self) -> str:
        return {"bod": "bod", "linie": "linie", "polygon": "polygon", "text": "text"}[self.value]

    @classmethod
    def parse(cls, value: Any) -> "GeomType | None":
        """Převede volný text (např. z tabulky od učitele) na typ geometrie."""
        if value is None:
            return None
        if isinstance(value, GeomType):
            return value
        s = str(value).strip().lower()
        if not s:
            return None
        aliases = {
            "bod": cls.BOD, "body": cls.BOD, "b": cls.BOD, "point": cls.BOD, "bodový": cls.BOD,
            "bodovy": cls.BOD, "značka": cls.BOD, "znacka": cls.BOD, "buňka": cls.BOD, "bunka": cls.BOD,
            "symbol": cls.BOD, "cell": cls.BOD, "blok": cls.BOD,
            "linie": cls.LINIE, "línie": cls.LINIE, "l": cls.LINIE, "line": cls.LINIE, "čára": cls.LINIE,
            "cara": cls.LINIE, "liniový": cls.LINIE, "liniovy": cls.LINIE, "lomená čára": cls.LINIE,
            "polyline": cls.LINIE, "linestring": cls.LINIE, "hrana": cls.LINIE,
            "polygon": cls.POLYGON, "plocha": cls.POLYGON, "p": cls.POLYGON, "plošný": cls.POLYGON,
            "plosny": cls.POLYGON, "area": cls.POLYGON, "uzavřená": cls.POLYGON, "uzavrena": cls.POLYGON,
            "shape": cls.POLYGON, "obvod": cls.POLYGON,
            "text": cls.TEXT, "popis": cls.TEXT, "t": cls.TEXT, "popisek": cls.TEXT,
        }
        if s in aliases:
            return aliases[s]
        for key, val in aliases.items():
            if len(key) > 2 and s.startswith(key):
                return val
        return None


@dataclass
class Feature:
    """Jeden prvek výkresu."""

    fid: int
    dxftype: str
    geom_type: GeomType
    geometry: BaseGeometry
    layer: str
    color_aci: int | None = None
    color_rgb: tuple[int, int, int] = (255, 255, 255)
    linetype: str = "CONTINUOUS"
    lineweight: float = 0.0  # mm, 0 = výchozí
    handle: str = ""
    closed: bool = False
    block_name: str | None = None
    text: str | None = None
    text_height: float = 0.0
    rotation: float = 0.0  # stupně
    scale: tuple[float, float] = (1.0, 1.0)
    radius: float = 0.0
    attributes: dict[str, str] = field(default_factory=dict)
    xdata: dict[str, list[Any]] = field(default_factory=dict)
    fill: bool = False  # vyplněná plocha (HATCH SOLID)
    # vrcholy tak, jak je nakreslil uživatel (pro kontrolu uzlů);
    # oblouky jsou nahrazeny lomenou čarou
    vertices: list[tuple[float, float]] = field(default_factory=list)
    # viditelné atributy bloku k vykreslení: (text, x, y, výška, natočení)
    display_texts: list[tuple[str, float, float, float, float]] = field(default_factory=list)
    halign: int = 0  # 0 vlevo, 1 na střed, 2 vpravo
    valign: int = 0  # 0 účaří, 1 dole, 2 uprostřed, 3 nahoře

    @property
    def is_linear(self) -> bool:
        return self.geom_type in (GeomType.LINIE, GeomType.POLYGON) and self.dxftype != "HATCH"

    def describe(self) -> str:
        parts = [self.dxftype]
        if self.block_name:
            parts.append(f"blok {self.block_name}")
        if self.handle:
            parts.append(f"#{self.handle}")
        return " ".join(parts)


@dataclass
class LayerInfo:
    name: str
    color_aci: int = 7
    color_rgb: tuple[int, int, int] = (255, 255, 255)
    linetype: str = "CONTINUOUS"
    lineweight: float = 0.0
    frozen: bool = False
    off: bool = False
    count: int = 0


@dataclass
class BlockGeometry:
    """Geometrie definice bloku v jeho vlastním souřadnicovém systému (pro zobrazení)."""

    name: str
    paths: list[list[tuple[float, float]]] = field(default_factory=list)  # lomené čáry
    closed: list[bool] = field(default_factory=list)
    points: list[tuple[float, float]] = field(default_factory=list)
    base_point: tuple[float, float] = (0.0, 0.0)


@dataclass
class Drawing:
    """Celý načtený výkres."""

    path: str
    features: list[Feature] = field(default_factory=list)
    layers: dict[str, LayerInfo] = field(default_factory=dict)
    blocks: dict[str, BlockGeometry] = field(default_factory=dict)
    linetypes: set[str] = field(default_factory=set)
    unit_factor: float = 1.0  # převod jednotek výkresu na metry
    warnings: list[str] = field(default_factory=list)
    source_path: str | None = None  # původní soubor (např. DGN), pokud se převáděl

    def bounds(self) -> tuple[float, float, float, float] | None:
        xs0, ys0, xs1, ys1 = [], [], [], []
        for f in self.features:
            if f.geometry is None or f.geometry.is_empty:
                continue
            b = f.geometry.bounds
            xs0.append(b[0]); ys0.append(b[1]); xs1.append(b[2]); ys1.append(b[3])
        if not xs0:
            return None
        return min(xs0), min(ys0), max(xs1), max(ys1)

    def by_id(self) -> dict[int, Feature]:
        return {f.fid: f for f in self.features}

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.features:
            out[f.dxftype] = out.get(f.dxftype, 0) + 1
        return out
