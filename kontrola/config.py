"""Nastavení kontrol (tolerance, zapnutí/vypnutí, závažnost, parametry)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .checks.base import REGISTRY, Severity


@dataclass
class CheckSettings:
    zapnuto: bool = True
    zavaznost: Severity = Severity.CHYBA
    parametry: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    tolerance: float = 0.05  # m – hledací tolerance (napojení, body blízko sebe, mezery)
    presnost: float = 0.0001  # m – pod touto vzdáleností jsou body totožné
    okruh_textu: float = 5.0  # m – do jaké vzdálenosti hledat text k bodu/linii
    max_chyb_na_kontrolu: int = 5000
    ignorovane_hladiny: list[str] = field(default_factory=lambda: ["KONTROLA_CHYBY", "DEFPOINTS"])
    oda_cesta: str = ""
    kontroly: dict[str, CheckSettings] = field(default_factory=dict)

    def __post_init__(self):
        self.ensure_defaults()

    def ensure_defaults(self):
        from . import checks  # noqa: F401 – registrace kontrol
        for cid, cls in REGISTRY.items():
            inst = cls()
            cs = self.kontroly.get(cid)
            if cs is None:
                cs = CheckSettings(True, inst.vychozi_zavaznost, {})
                self.kontroly[cid] = cs
            for k, v in inst.default_params().items():
                cs.parametry.setdefault(k, v)

    def settings(self, check_id: str) -> CheckSettings:
        self.ensure_defaults()
        return self.kontroly[check_id]

    # ------------------------------------------------------------ YAML
    def to_dict(self) -> dict:
        return {
            "nastaveni": {
                "tolerance": self.tolerance,
                "presnost": self.presnost,
                "okruh_textu": self.okruh_textu,
                "max_chyb_na_kontrolu": self.max_chyb_na_kontrolu,
                "ignorovane_hladiny": list(self.ignorovane_hladiny),
                "oda_cesta": self.oda_cesta,
            },
            "kontroly": {
                cid: {"zapnuto": cs.zapnuto, "zavaznost": cs.zavaznost.value, **cs.parametry}
                for cid, cs in self.kontroly.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "Config":
        d = d or {}
        n = d.get("nastaveni") or {}
        cfg = cls(
            tolerance=float(n.get("tolerance", 0.05)),
            presnost=float(n.get("presnost", 0.0001)),
            okruh_textu=float(n.get("okruh_textu", 5.0)),
            max_chyb_na_kontrolu=int(n.get("max_chyb_na_kontrolu", 5000)),
            ignorovane_hladiny=list(n.get("ignorovane_hladiny", ["KONTROLA_CHYBY", "DEFPOINTS"]) or []),
            oda_cesta=str(n.get("oda_cesta", "") or ""),
            kontroly={},
        )
        for cid, v in (d.get("kontroly") or {}).items():
            if not isinstance(v, dict):
                v = {"zapnuto": bool(v)}
            v = dict(v)
            cs = CheckSettings(
                zapnuto=bool(v.pop("zapnuto", True)),
                zavaznost=Severity.parse(v.pop("zavaznost", "chyba")),
                parametry=v,
            )
            cfg.kontroly[cid] = cs
        cfg.ensure_defaults()
        return cfg

    def save(self, path: str | Path):
        Path(path).write_text(yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data if isinstance(data, dict) else {})
