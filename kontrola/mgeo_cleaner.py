"""Nastavení topologie od učitele: konfigurační soubor MGEO Cleaner (*.clean.xml) → nastavení kontrol.

Učitel kontroluje topologii programem MGEO (Cleaner) s konfigurací uloženou v XML. Z ní se převezme:
tolerance začištění (cleanTolerance), minimální délka čáry (minLineLength), tolerance průsečíku /
přetažení (intersectTolerance), zda se označují volné konce (OznacitVolneKonce) a které vrstvy se
zpracovávají (ProcessLevels). Kontrola v aplikaci pak počítá se stejnými hodnotami jako učitel.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NastaveniCleaner:
    tolerance: float | None = None  # cleanTolerance [m]
    min_delka: float | None = None  # minLineLength [m]
    pretah: float | None = None  # intersectTolerance [m]
    volne_konce: bool = True  # OznacitVolneKonce
    volne_konce_na_znackach: bool = True  # VolneKonceNaZnackach (konec na buňce = napojený)
    kratke_cary: int = 0  # markShortLines (0 = neoznačovat)
    vrstvy: list[str] = field(default_factory=list)  # ProcessLevels
    vrstvy_znacek_na_vrcholu: list[str] = field(default_factory=list)  # CellOnVertexLevels
    soubor_hlaseni: str = ""

    def popis(self) -> list[str]:
        r = []
        if self.tolerance is not None:
            r.append(f"tolerance začištění {self.tolerance:g} m")
        if self.min_delka is not None:
            r.append(f"min. délka čáry {self.min_delka:g} m")
        if self.pretah is not None:
            r.append(f"tolerance průsečíku / přetažení {self.pretah:g} m")
        r.append("volné konce " + ("se hlásí" if self.volne_konce else "se nehlásí"))
        if self.vrstvy:
            r.append(f"zpracované vrstvy: {len(self.vrstvy)}")
        return r


def _cislo(v: str | None) -> float | None:
    try:
        x = float((v or "").strip().replace(",", "."))
    except ValueError:
        return None
    return x if x > 0 else None  # −1 = nepoužito


def nacti(cesta: str | Path) -> NastaveniCleaner:
    try:
        root = ET.parse(cesta).getroot()
    except (ET.ParseError, OSError) as e:
        raise ValueError(f"Soubor nastavení MGEO nejde přečíst: {e}") from None
    hodnoty: dict[str, str] = {}
    for v in root.iter("Var"):
        if v.get("name") and v.get("name") not in ("level", "isLevelName") and v.text is not None:
            hodnoty.setdefault(v.get("name"), v.text.strip())
    if "cleanTolerance" not in hodnoty and "ToleranceZacisteni" not in hodnoty:
        raise ValueError("Soubor není konfigurace MGEO Cleaner (chybí tolerance začištění).")

    def vrstvy(pole: str) -> list[str]:
        out = []
        for a in root.iter("Array"):
            if a.get("name") == pole:
                for s in a.iter("Struct"):
                    lv = s.find("Var[@name='level']")
                    if lv is not None and lv.text and lv.text.strip():
                        out.append(lv.text.strip())
        return out
    n = NastaveniCleaner(
        tolerance=_cislo(hodnoty.get("cleanTolerance")) or _cislo(hodnoty.get("ToleranceZacisteni")),
        min_delka=_cislo(hodnoty.get("minLineLength")) or _cislo(hodnoty.get("MinimalniDelkaCar")),
        pretah=_cislo(hodnoty.get("intersectTolerance")) or _cislo(hodnoty.get("TolerancePretahu")),
        volne_konce=hodnoty.get("OznacitVolneKonce", "1") != "0",
        volne_konce_na_znackach=hodnoty.get("VolneKonceNaZnackach", "1") != "0",
        kratke_cary=int(float(hodnoty.get("markShortLines", "0") or 0)),
        vrstvy=vrstvy("ProcessLevels"),
        vrstvy_znacek_na_vrcholu=vrstvy("CellOnVertexLevels"),
        soubor_hlaseni=hodnoty.get("SouborProHlaseni", ""),
    )
    return n


def _vzory_vrstev(vrstvy: list[str]) -> str:
    """Čísla vrstev → vzory pro DXF („12“) i DGN („Vrstva 12“)."""
    out = []
    for v in vrstvy:
        out.append(v)
        if v.isdigit():
            out.append(f"Vrstva {v}")
    return ",".join(out)


TOPO_KONTROLY = ("visici_konce", "chybejici_napojeni", "pruseciky_bez_uzlu", "kratke_linie", "duplicity",
                 "prekryv_linii", "samoprotnuti", "nulova_delka", "nezavrene_polygony")


def pouzij(cfg, n: NastaveniCleaner, vsechny_vrstvy: bool = False) -> list[str]:
    """Přenese nastavení do konfigurace kontrol. Vrací popis změn (pro zprávu uživateli)."""
    zmeny = []
    if n.tolerance is not None:
        cfg.tolerance = n.tolerance
        zmeny.append(f"tolerance {n.tolerance:g} m")
    if n.min_delka is not None:
        cfg.settings("kratke_linie").parametry["min_delka"] = n.min_delka
        cfg.settings("kratke_linie").zapnuto = n.kratke_cary != 0
        zmeny.append(f"min. délka čáry {n.min_delka:g} m")
    if n.pretah is not None:
        cfg.settings("chybejici_napojeni").parametry["max_pretazeni"] = n.pretah
        zmeny.append(f"přetažení {n.pretah:g} m")
    cfg.settings("visici_konce").zapnuto = n.volne_konce
    zmeny.append("volné konce " + ("zapnuto" if n.volne_konce else "vypnuto"))
    if n.vrstvy and not vsechny_vrstvy and len(n.vrstvy) < 63:
        vz = _vzory_vrstev(n.vrstvy)
        for cid in TOPO_KONTROLY:
            cfg.settings(cid).parametry["hladiny"] = vz
        zmeny.append(f"topologie jen ve vrstvách {', '.join(n.vrstvy[:12])}" + ("…" if len(n.vrstvy) > 12 else ""))
    return zmeny
