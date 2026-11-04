"""Nastavení výpočtů (jako Nastavení / Konfigurace výpočtů v Gromě).

* účel měření: katastr (kód kvality) nebo polohopis / účelové mapy (třída přesnosti ČSN 01 3410);
* přístroj a jeho přesnost (směr, délka a + b·ppm) – pro odhad přesnosti v protokolech;
* korekce měřených délek: měřítko Křovákova zobrazení, redukce z nadmořské výšky, fyzikální korekce ppm;
* mezní odchylky polygonových pořadů (dvě třídy, parametry jdou změnit).

Bez Qt: úlohy čtou ``aktualni()``, desktop ho při startu naplní z QSettings (``z_dict``).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

R_ZEME = 6_380_000.0

# střední souřadnicová chyba m_xy podle třídy přesnosti ČSN 01 3410 (polohopis, účelové mapy)
MXY_TRIDA = {1: 0.014, 2: 0.04, 3: 0.14, 4: 0.26, 5: 0.50}

UCELY = ("katastr", "polohopis")
REZIMY_MERITKA = ("bez korekce", "Křovák ze souřadnic", "ručně")
REZIMY_VYSKY = ("bez redukce", "z výšek bodů", "ručně")


@dataclass
class NastaveniVypoctu:
    ucel: str = "katastr"
    kod_kvality: int = 3
    trida_presnosti: int = 3
    pristroj: str = "Totální stanice"
    sigma_smer_mgon: float = 0.3  # σ směru [mgon] (1 mgon = 10 cc)
    sigma_delka_mm: float = 1.0  # σ délky = a [mm] + b [ppm]
    sigma_delka_ppm: float = 1.5
    meritko_rezim: str = "bez korekce"
    meritko_rucne: float = 1.0
    vyska_rezim: str = "bez redukce"
    vyska: float = 300.0  # m n. m.
    ppm_fyzikalni: float = 0.0  # atmosférická (fyzikální) korekce [ppm], pokud ji nezavedla stanice
    # polygonové pořady: mezní úhlová a_u·√(n + k_u) [mgon], mezní polohová a_p·√Σs + c_p [m]
    polygon_trida: int = 1
    desetiny: int = 3

    # -------------------------------------------------- korekce délek
    @property
    def korekce_zapnuta(self) -> bool:
        return (self.meritko_rezim != "bez korekce" or self.vyska_rezim != "bez redukce"
                or abs(self.ppm_fyzikalni) > 0)

    def faktor_delky(self, y: float | None = None, x: float | None = None, h: float | None = None
                     ) -> tuple[float, list[str]]:
        """Násobitel vodorovné délky (do roviny S-JTSK) a popis složek pro protokol."""
        k, popis = 1.0, []
        if abs(self.ppm_fyzikalni) > 0:
            k *= 1 + self.ppm_fyzikalni * 1e-6
            popis.append(f"fyzikální korekce {self.ppm_fyzikalni:+.1f} ppm")
        vys = None
        if self.vyska_rezim == "ručně":
            vys = self.vyska
        elif self.vyska_rezim == "z výšek bodů":
            vys = h if h is not None else self.vyska
        if vys is not None:
            k *= R_ZEME / (R_ZEME + vys)
            popis.append(f"z nadmořské výšky H = {vys:.1f} m ({(R_ZEME / (R_ZEME + vys) - 1) * 1e6:+.1f} ppm)")
        m = None
        if self.meritko_rezim == "ručně":
            m = self.meritko_rucne
        elif self.meritko_rezim == "Křovák ze souřadnic" and y is not None and x is not None and y > 0 and x > 0:
            from .sjtsk import meritko_zobrazeni
            try:
                m = meritko_zobrazeni(y, x)
            except (ValueError, ZeroDivisionError):
                m = None
        if m is not None:
            k *= m
            popis.append(f"měřítko zobrazení m = {m:.8f} ({(m - 1) * 1e6:+.1f} ppm)")
        return k, popis

    def popis_korekce(self, k: float, popis: list[str]) -> str:
        if not popis:
            return "Délky bez korekcí (nastavení výpočtů)."
        return f"Korekce délek: násobitel {k:.8f} = " + ", ".join(popis)

    # -------------------------------------------------- přesnost
    @property
    def mxy(self) -> float:
        if self.ucel == "katastr":
            from .vypocty import MXY_KOD_KVALITY
            return MXY_KOD_KVALITY.get(self.kod_kvality, 0.14)
        return MXY_TRIDA.get(self.trida_presnosti, 0.14)

    def popis_ucelu(self) -> str:
        if self.ucel == "katastr":
            return f"katastr nemovitostí, kód kvality {self.kod_kvality} (m_xy = {self.mxy:.2f} m)"
        return f"polohopis, třída přesnosti {self.trida_presnosti} ČSN 01 3410 (m_xy = {self.mxy:.3f} m)"

    def sigma_delky(self, d: float) -> float:
        return (self.sigma_delka_mm + self.sigma_delka_ppm * d / 1000.0) / 1000.0

    def mez_polygonu(self, n_vrcholu: int, delka: float) -> tuple[float, float]:
        """(mezní úhlová [gon], mezní polohová [m]) polygonového pořadu; n = počet nových bodů."""
        if self.polygon_trida == 2:
            return 0.100 * math.sqrt(n_vrcholu + 3), 0.005 * math.sqrt(delka) + 0.04
        return 0.025 * math.sqrt(n_vrcholu + 2), 0.0025 * math.sqrt(delka) + 0.04

    # -------------------------------------------------- uložení
    def do_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def z_dict(cls, d: dict | None) -> NastaveniVypoctu:
        n = cls()
        for f in fields(cls):
            if d and f.name in d:
                try:
                    setattr(n, f.name, type(getattr(n, f.name))(d[f.name]))
                except (TypeError, ValueError):
                    pass
        return n

    def hlavicka(self) -> list[str]:
        """Řádky do hlavičky protokolu."""
        r = [f"Účel: {self.popis_ucelu()}",
             f"Přístroj: {self.pristroj} (σ směru {self.sigma_smer_mgon:g} mgon, σ délky "
             f"{self.sigma_delka_mm:g} mm + {self.sigma_delka_ppm:g} ppm)"]
        return r


_AKTUALNI = NastaveniVypoctu()


def aktualni() -> NastaveniVypoctu:
    return _AKTUALNI


def nastav(n: NastaveniVypoctu) -> None:
    global _AKTUALNI
    _AKTUALNI = n
