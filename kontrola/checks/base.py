"""Společné rozhraní kontrol.

Novou kontrolu přidáte takto::

    from kontrola.checks.base import Check, Param, Severity, register

    @register
    class MojeKontrola(Check):
        id = "moje_kontrola"
        nazev = "Moje kontrola"
        skupina = "Atributy"
        popis = "Co kontrola hlídá."
        vychozi_zavaznost = Severity.VAROVANI
        parametry = [Param("limit", "Limit [m]", "float", 1.0)]

        def run(self, ctx):
            for f in ctx.features():
                if ...:
                    yield ctx.issue(self, f, "Popis chyby")

a modul naimportujete v ``kontrola/checks/__init__.py``.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Iterator

import numpy as np
import shapely
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from ..model import Drawing, Feature, GeomType


class Severity(str, Enum):
    CHYBA = "chyba"
    VAROVANI = "varování"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"chyba": 0, "varování": 1, "info": 2}[self.value]

    @classmethod
    def parse(cls, v: Any) -> "Severity":
        if isinstance(v, Severity):
            return v
        s = str(v).strip().lower()
        for sev in cls:
            if s == sev.value or s == sev.name.lower():
                return sev
        if s.startswith("var") or s == "warning":
            return cls.VAROVANI
        if s.startswith("inf"):
            return cls.INFO
        return cls.CHYBA


ISSUE_STATES = ("nová", "opraveno", "ignorovat")


def fmt_num(value: float, decimals: int = 3) -> str:
    """Číslo s desetinnou čárkou bez zbytečných nul: 0.030 -> "0,03"."""
    s = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s.replace(".", ",")


def fmt_m(value: float, decimals: int = 3) -> str:
    """Délka v metrech; pod 1 cm v milimetrech (0,0004 -> "0,4 mm")."""
    if 0 < abs(value) < 0.01:
        mm = abs(value) * 1000
        return "< 0,1 mm" if mm < 0.1 else f"{fmt_num(mm, 1)} mm"
    return f"{fmt_num(value, decimals)} m"


@dataclass
class Issue:
    """Jedna nalezená chyba."""

    check_id: str
    check_name: str
    severity: Severity
    message: str
    x: float
    y: float
    layer: str = ""
    feature_ids: list[int] = field(default_factory=list)
    handles: list[str] = field(default_factory=list)
    geometry: BaseGeometry | None = None
    number: int = 0
    state: str = "nová"
    note: str = ""

    def label(self) -> str:
        """Krátký popisek ke kroužku ve výkresu (celé znění je v seznamu a v tooltipu)."""
        m = re.match(r"^.+? \(pravidlo „([^“]+)“\): (.*)$", self.message)
        if m:
            keys = [k for k in ("vrstva", "barva", "styl", "měřítko stylu", "tloušťka", "výška textu", "šířka textu",
                                "písmo", "font", "zarovnání", "měřítko buňky")
                    if re.search(r"(^|, )" + re.escape(k) + r"\b", m.group(2))]
            return f"{m.group(1)}: {', '.join(keys)}" if keys else f"{m.group(1)}: {m.group(2)}"
        return self.message

    @property
    def key(self) -> str:
        """Stabilní otisk chyby – slouží k porovnání mezi kontrolami a k uložení stavu."""
        base = f"{self.check_id}|{round(self.x, 2)}|{round(self.y, 2)}|{self.message}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "cislo": self.number, "kontrola": self.check_id, "typ": self.check_name,
            "zavaznost": self.severity.value, "popis": self.message, "hladina": self.layer,
            "x": self.x, "y": self.y, "stav": self.state, "poznamka": self.note,
            "handle": ",".join(self.handles), "klic": self.key,
        }


@dataclass
class Param:
    """Nastavitelný parametr kontroly."""

    name: str
    label: str
    type: str = "float"  # float | int | bool | str | layers
    default: Any = None
    help: str = ""


class Cancelled(Exception):
    """Uživatel kontrolu přerušil."""


class Check(ABC):
    id: str = ""
    nazev: str = ""
    skupina: str = "Topologie"
    popis: str = ""
    vychozi_zavaznost: Severity = Severity.CHYBA
    parametry: list[Param] = []
    potrebuje_pravidla: bool = False

    @abstractmethod
    def run(self, ctx: "CheckContext") -> Iterable[Issue]:
        """Vrací (generuje) nalezené chyby."""

    def default_params(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.parametry}


REGISTRY: dict[str, type[Check]] = {}


def register(cls: type[Check]) -> type[Check]:
    if not cls.id:
        raise ValueError("Kontrola musí mít id")
    REGISTRY[cls.id] = cls
    return cls


def all_checks() -> list[Check]:
    return [cls() for cls in REGISTRY.values()]


class CheckContext:
    """Vše, co kontrola potřebuje: výkres, pravidla, nastavení a sdílené indexy."""

    def __init__(self, drawing: Drawing, rules, config, params: dict[str, Any] | None = None,
                 progress: Callable[[float], None] | None = None,
                 cancelled: Callable[[], bool] | None = None):
        from ..rules import RuleSet
        self.drawing = drawing
        self.rules: RuleSet = rules if rules is not None else RuleSet()
        self.config = config
        self.params: dict[str, Any] = params or {}
        self._progress = progress
        self._cancelled = cancelled
        self.notes: list[str] = []
        self.severity: Severity = Severity.CHYBA
        self._cache: dict[str, Any] = {}

    # ------------------------------------------------------------ nastavení
    @property
    def tolerance(self) -> float:
        return float(self.config.tolerance)

    @property
    def precision(self) -> float:
        return float(self.config.presnost)

    def param(self, name: str, default: Any = None) -> Any:
        v = self.params.get(name, default)
        return default if v is None else v

    def progress(self, fraction: float):
        if self._progress:
            self._progress(max(0.0, min(1.0, fraction)))
        self.check_cancel()

    def check_cancel(self):
        if self._cancelled and self._cancelled():
            raise Cancelled()

    # ------------------------------------------------------------ výběry prvků
    def features(self, layers: Iterable[str] | None = None) -> list[Feature]:
        ignore = {s.upper() for s in self.config.ignorovane_hladiny}
        lay = None
        if layers:
            lay = {s.upper() for s in layers if s}
        out = []
        for f in self.drawing.features:
            up = f.layer.upper()
            if up in ignore:
                continue
            if lay and not _layer_in(up, lay):
                continue
            out.append(f)
        return out

    def layer_filter(self) -> list[str] | None:
        v = self.params.get("hladiny")
        if not v:
            return None
        if isinstance(v, str):
            return [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
        return list(v)

    def linear(self) -> list[Feature]:
        """Liniové prvky (linie a polygony, bez šraf) podle filtru hladin kontroly."""
        key = "linear|" + ",".join(self.layer_filter() or [])
        if key not in self._cache:
            out = []
            extra: list[Feature] = []
            allowed: dict[str, bool] = {}
            for f in self.features(self.layer_filter()):
                if not f.is_linear or f.geometry.is_empty:
                    continue
                if self.rules.pravidla:
                    ok = allowed.get(f.layer)
                    if ok is None:
                        ok = allowed[f.layer] = self.rules.allowed_layer(f.layer)
                    if not ok:
                        continue  # nepovolená hladina (kóty, pomocné čáry…) – hlásí ji kontrola atributů
                r = self.rule_for(f) if self.rules.pravidla else None
                if r is not None and not r.topologie:
                    extra.append(f)
                    continue  # vstupy, šrafy – samy se nekontrolují, ale jiné čáry se na ně napojují
                out.append(f)
            self._cache[key] = out
            self._cache["linear_extra|" + key] = extra
        return self._cache[key]

    def linear_targets(self) -> list[Feature]:
        """Linie vyjmuté z topologie (vstupy, šrafy): nehlásí se u nich chyby, ale napojení na ně platí."""
        key = "linear|" + ",".join(self.layer_filter() or [])
        self.linear()
        return self._cache.get("linear_extra|" + key, [])

    def boundary(self, f: Feature) -> BaseGeometry:
        if f.geom_type == GeomType.POLYGON:
            return f.geometry.boundary
        return f.geometry

    def rule_for(self, f: Feature):
        cache = self._cache.setdefault("rules", {})
        if f.fid not in cache:
            cache[f.fid] = self.rules.resolve(f) if self.rules.pravidla else None
        return cache[f.fid]

    def attributes(self, f: Feature) -> dict[str, str]:
        """Atributy prvku včetně hodnot převzatých z textů (pravidlo text.atribut)."""
        attrs = self._cache.setdefault("attrs", {})
        if f.fid in attrs:
            return attrs[f.fid]
        out = {k.upper(): v for k, v in f.attributes.items()}
        r = self.rule_for(f)
        if r is not None and r.text is not None and r.text.atribut:
            t = self.text_for(f, r)
            if t is not None and t.text:
                out.setdefault(r.text.atribut.upper(), t.text)
        attrs[f.fid] = out
        return out

    def texts(self, layer: str | None = None) -> list[Feature]:
        """Popisy: texty, a na zadané hladině i bodové prvky (definiční body ploch, buňky)."""
        key = f"texts|{layer or ''}"
        if key not in self._cache:
            from ..rules import layer_matches
            if layer:
                self._cache[key] = [f for f in self.features()
                                    if f.geom_type in (GeomType.TEXT, GeomType.BOD)
                                    and layer_matches(layer, f.layer)]
            else:
                self._cache[key] = [f for f in self.features() if f.geom_type == GeomType.TEXT]
        return self._cache[key]

    def texts_inside(self, area: BaseGeometry, layer: str | None) -> list[Feature]:
        texts, tree = self.text_tree(layer)
        if tree is None:
            return []
        return [texts[int(i)] for i in tree.query(area, predicate="contains")]

    def text_tree(self, layer: str | None = None):
        key = f"texttree|{layer or ''}"
        if key not in self._cache:
            texts = self.texts(layer)
            geoms = np.array([t.geometry for t in texts], dtype=object)
            self._cache[key] = (texts, shapely.STRtree(geoms) if len(geoms) else None)
        return self._cache[key]

    def area_geometry(self, f: Feature, rule=None) -> BaseGeometry | None:
        """Plocha prvku: polygon, nebo neuzavřená linie, která má být podle pravidla polygonem."""
        if f.geom_type == GeomType.POLYGON:
            if f.geometry.is_valid:
                return f.geometry
            from shapely.validation import make_valid
            return make_valid(f.geometry)
        rule = rule if rule is not None else self.rule_for(f)
        if (f.geom_type == GeomType.LINIE and rule is not None and rule.geometrie == GeomType.POLYGON
                and len(f.geometry.coords) >= 3):
            from shapely.geometry import Polygon
            from shapely.validation import make_valid
            poly = Polygon(list(f.geometry.coords))
            return poly if poly.is_valid else make_valid(poly)
        return None

    def text_for(self, f: Feature, rule) -> Feature | None:
        """Najde text patřící k prvku: uvnitř polygonu, jinak nejbližší v okruhu."""
        texts, tree = self.text_tree(rule.text.hladina if rule.text else None)
        if tree is None:
            return None
        g = f.geometry
        area = self.area_geometry(f, rule)
        if area is not None and (rule.text is None or rule.text.uvnitr):
            idx = tree.query(area, predicate="contains")
            if len(idx):
                return texts[int(idx[0])]
            return None
        radius = float(self.config.okruh_textu)
        idx = tree.query(g, predicate="dwithin", distance=radius)
        if not len(idx):
            return None
        best = min(idx, key=lambda i: g.distance(texts[int(i)].geometry))
        return texts[int(best)]

    # ------------------------------------------------------------ tvorba chyb
    def issue(self, check: Check, f: Feature | list[Feature] | None, message: str,
              at: tuple[float, float] | BaseGeometry | None = None,
              geometry: BaseGeometry | None = None) -> Issue:
        feats = f if isinstance(f, list) else ([f] if f is not None else [])
        if at is None:
            g = geometry if geometry is not None else (feats[0].geometry if feats else Point(0, 0))
            p = _anchor(g)
        elif isinstance(at, BaseGeometry):
            p = _anchor(at)
        else:
            p = at
        return Issue(
            check_id=check.id, check_name=check.nazev, severity=self.severity, message=message,
            x=float(p[0]), y=float(p[1]), layer=feats[0].layer if feats else "",
            feature_ids=[x.fid for x in feats], handles=[x.handle for x in feats if x.handle],
            geometry=geometry if geometry is not None else (feats[0].geometry if len(feats) == 1 else None),
        )


def _layer_in(layer_upper: str, patterns: set[str]) -> bool:
    import fnmatch
    if layer_upper in patterns:
        return True
    return any(fnmatch.fnmatchcase(layer_upper, p) for p in patterns if any(c in p for c in "*?["))


def _anchor(g: BaseGeometry) -> tuple[float, float]:
    if g is None or g.is_empty:
        return (0.0, 0.0)
    if g.geom_type == "Point":
        return (g.x, g.y)
    if g.geom_type in ("LineString", "LinearRing"):
        p = g.interpolate(0.5, normalized=True)
        return (p.x, p.y)
    p = g.representative_point()
    return (p.x, p.y)


def endpoints(f: Feature) -> Iterator[tuple[float, float]]:
    coords = list(f.geometry.coords)
    if coords:
        yield coords[0][:2]
        if len(coords) > 1:
            yield coords[-1][:2]
