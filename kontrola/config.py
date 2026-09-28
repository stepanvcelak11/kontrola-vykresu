"""Nastavení kontrol (tolerance, zapnutí/vypnutí, závažnost, parametry)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .checks.base import REGISTRY, Severity


CONFIG_VERSION = 3
# Rozpracovaný výkres: kontroly a hlášení, která vznikají jen tím, že kresba ještě není hotová
WIP_SKIP_CHECKS = ("visici_konce", "nezavrene_polygony", "mezery_polygonu")
WIP_SKIP_MESSAGES = {"texty": (": chybí popis",)}
DEFAULT_TOLERANCE = 0.010
# výchozí hodnoty verze 1, které se v uložených projektech nahradí hodnotami podle MGEO
_MIGRATE = {
    "chybejici_napojeni": {"max_pretazeni": 0.5},
    "kratke_linie": {"min_delka": 0.05},
    "pruseciky_bez_uzlu": {"napojeni_bez_uzlu": True},
    "symbologie": {"kontrolovat_font": False},
}


@dataclass
class CheckSettings:
    zapnuto: bool = True
    zavaznost: Severity = Severity.CHYBA
    parametry: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.zavaznost, Severity):
            self.zavaznost = Severity.parse(self.zavaznost)

    def __setattr__(self, name, value):
        if name == "zavaznost" and not isinstance(value, Severity):
            value = Severity.parse(value)
        super().__setattr__(name, value)


@dataclass
class Config:
    tolerance: float = 0.010  # m – tolerance začištění jako v MGEO (nedotažení, body blízko sebe)
    presnost: float = 0.0001  # m – pod touto vzdáleností jsou body totožné
    okruh_textu: float = 5.0  # m – do jaké vzdálenosti hledat text k bodu/linii
    max_chyb_na_kontrolu: int = 5000
    ignorovane_hladiny: list[str] = field(default_factory=lambda: ["KONTROLA_CHYBY", "DEFPOINTS"])
    oda_cesta: str = ""
    rozpracovany: bool = False  # rozpracovaný výkres: nehlásit, co vzniká jen nedokončenou kresbou
    seznam_souradnic: str = ""  # cesta k seznamu souřadnic (nastaví projekt / příkazová řádka, neukládá se)
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
            "verze_nastaveni": CONFIG_VERSION,
            "nastaveni": {
                "tolerance": self.tolerance,
                "presnost": self.presnost,
                "okruh_textu": self.okruh_textu,
                "max_chyb_na_kontrolu": self.max_chyb_na_kontrolu,
                "ignorovane_hladiny": list(self.ignorovane_hladiny),
                "oda_cesta": self.oda_cesta,
                "rozpracovany": self.rozpracovany,
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
            tolerance=float(n.get("tolerance", DEFAULT_TOLERANCE)),
            presnost=float(n.get("presnost", 0.0001)),
            okruh_textu=float(n.get("okruh_textu", 5.0)),
            max_chyb_na_kontrolu=int(n.get("max_chyb_na_kontrolu", 5000)),
            ignorovane_hladiny=list(n.get("ignorovane_hladiny", ["KONTROLA_CHYBY", "DEFPOINTS"]) or []),
            oda_cesta=str(n.get("oda_cesta", "") or ""),
            rozpracovany=bool(n.get("rozpracovany", False)),
            kontroly={},
        )
        ver = int(d.get("verze_nastaveni", 1) or 1) if ("nastaveni" in d or "kontroly" in d) else CONFIG_VERSION
        old = ver < 2
        if old:
            # starší projekty: tolerance podle MGEO (učitelova kontrola) místo původních výchozích hodnot
            if abs(cfg.tolerance - 0.05) < 1e-9:
                cfg.tolerance = DEFAULT_TOLERANCE
        for cid, v in (d.get("kontroly") or {}).items():
            if not isinstance(v, dict):
                v = {"zapnuto": bool(v)}
            v = dict(v)
            if old:
                for k, oldval in _MIGRATE.get(cid, {}).items():
                    if k in v and v[k] == oldval:
                        v.pop(k)
                if cid == "kratke_linie" and v.get("zavaznost") == "varování":
                    v.pop("zavaznost")
            if ver < 3 and cid == "visici_konce" and v.get("zavaznost") in ("chyba", Severity.CHYBA):
                v.pop("zavaznost")  # dřív omylem „chyba“: volné konce uvnitř jsou varování, na okraji info
            cls_ = REGISTRY.get(cid)
            default_sev = cls_.vychozi_zavaznost if cls_ is not None else Severity.CHYBA
            cs = CheckSettings(
                zapnuto=bool(v.pop("zapnuto", True)),
                zavaznost=Severity.parse(v.pop("zavaznost", default_sev.value)),
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
