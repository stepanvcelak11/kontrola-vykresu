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

# střední souřadnicová chyba m_xy podle třídy přesnosti ČSN 01 3410 (polohopis, účelové mapy) – stejná tabulka
# jako testování přesnosti (vypocty.TRIDY_PRESNOSTI)
from .vypocty import TRIDY_PRESNOSTI as _TP  # noqa: E402

MXY_TRIDA = {k: v[0] for k, v in _TP.items()}

UCELY = ("katastr", "polohopis")
REZIMY_MERITKA = ("bez korekce", "Křovák ze souřadnic", "ručně")
REZIMY_VYSKY = ("bez redukce", "z výšek bodů", "ručně")


@dataclass
class NastaveniVypoctu:
    zakazka: str = ""
    zpracovatel: str = ""
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
    # zpracování zápisníku (Groma: Měření → Zpracování zápisníku)
    zp_polohy: bool = True  # zprůměrovat měření v I. a II. poloze dalekohledu
    zp_sikme: bool = True  # délky v zápisníku jsou šikmé → redukovat na vodorovné (False = už vodorovné)
    zp_refrakce: bool = True  # oprava převýšení z refrakce
    zp_zakriveni: bool = True  # oprava převýšení ze zakřivení Země
    k_refrakce: float = 0.13
    zp_obousmerne: bool = True  # obousměrně měřené délky a převýšení – průměr tam a zpět
    zp_vahy: str = "délka"  # váhy orientací: „délka“ (Groma) nebo „1“
    zp_prumer_kontrolnich: bool = True  # bod určený dvakrát → uložit průměr
    prumer_max_xy: float = 0.35
    prumer_max_z: float = 0.35
    # teodolit (Groma: Nastavení → Teodolit): podezřelé / chybné rozdíly
    kol_p: float = 0.0100
    kol_ch: float = 0.0400
    idx_p: float = 0.0200
    idx_ch: float = 0.0500
    md_p: float = 0.020
    md_ch: float = 0.030
    # uživatelské tolerance (Groma: Nastavení → Tolerance); prázdné = předpisy pro katastr
    tol_min_uhel: str = ""  # [g]
    tol_orient: str = ""  # max. oprava orientace [g]
    tol_orient_delka: str = ""  # max. oprava orientační délky [m], vzorec se „s“
    tol_orient_prev: str = ""  # max. oprava orientačního převýšení [m]
    tol_dvakrat_delka: str = ""  # rozdíl dvakrát měřené délky [m]
    tol_uhlovy: str = ""  # úhlový uzávěr polygonu [cc], vzorec s „n“
    tol_polohova: str = ""  # polohová odchylka polygonu [m], vzorec se „s“
    tol_tr_m0: str = ""  # max. střední chyba transformačního klíče [m]
    tol_tr_meritko: str = ""  # mezní změna měřítka 1 ± …

    # -------------------------------------------------- tolerance
    def tolerance(self, nazev: str, **promenne) -> float | None:
        """Uživatelská tolerance (vzorec jako v Gromě, např. „0.002*SQRT(s) + 0.04“); None = není zadaná."""
        return vzorec(getattr(self, "tol_" + nazev, "") or "", **promenne)

    def mez_orientace(self) -> float:
        t = self.tolerance("orient")
        return 0.08 if t is None else t

    def mez_orient_delky(self, d: float) -> float:
        t = self.tolerance("orient_delka", s=d, d=d)
        return 0.10 + 0.012 * math.sqrt(d) if t is None else t

    def zpracovani(self):
        """Volby zpracování zápisníku pro výpočet polární metody (kontrola.vypocet.Zpracovani)."""
        from ..vypocet import Zpracovani
        return Zpracovani(polohy=self.zp_polohy, sikme=self.zp_sikme, refrakce=self.zp_refrakce,
                          zakriveni=self.zp_zakriveni, k_refrakce=self.k_refrakce, obousmerne=self.zp_obousmerne,
                          vahy=self.zp_vahy, prumer_kontrolnich=self.zp_prumer_kontrolnich,
                          prumer_max_xy=self.prumer_max_xy, prumer_max_z=self.prumer_max_z,
                          kol_p=self.kol_p, kol_ch=self.kol_ch, idx_p=self.idx_p, idx_ch=self.idx_ch,
                          md_p=self.md_p, md_ch=self.md_ch)

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

    def koeficient(self) -> float | None:
        """Měřítkový koeficient z lišty nastavení (Groma: jedno číslo pro všechny délky);
        None = počítat z bodů (režim „Křovák ze souřadnic“)."""
        if self.meritko_rezim == "ručně":
            return self.meritko_rucne
        if self.meritko_rezim == "bez korekce":
            return 1.0
        return None

    def nastav_koeficient(self, k: float) -> None:
        """Jako tlačítko Nastavit v modulu Zkreslení v Křovákově zobrazení: jeden koeficient, v němž je
        zkreslení i nadmořská výška (redukce z výšky se už zvlášť nepočítá)."""
        if abs(k - 1.0) < 1e-12:
            self.meritko_rezim, self.meritko_rucne = "bez korekce", 1.0
        else:
            self.meritko_rezim, self.meritko_rucne = "ručně", k
        self.vyska_rezim = "bez redukce"

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
        tu = self.tolerance("uhlovy", n=n_vrcholu)
        tp = self.tolerance("polohova", s=delka, d=delka)
        if tu is not None or tp is not None:
            du, dp = self._mez_polygonu_predpis(n_vrcholu, delka)
            return (du if tu is None else tu / 10000.0), (dp if tp is None else tp)
        return self._mez_polygonu_predpis(n_vrcholu, delka)

    def _mez_polygonu_predpis(self, n_vrcholu: int, delka: float) -> tuple[float, float]:
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
                    t = type(getattr(n, f.name))
                    v = d[f.name]
                    if t is bool and isinstance(v, str):
                        v = v.strip().lower() in ("1", "true", "ano", "yes")
                    setattr(n, f.name, t(v))
                except (TypeError, ValueError):
                    pass
        return n

    def hlavicka(self) -> list[str]:
        """Řádky do hlavičky protokolu."""
        r = []
        if self.zakazka:
            r.append(f"Zakázka: {self.zakazka}")
        if self.zpracovatel:
            r.append(f"Zpracoval: {self.zpracovatel}")
        r += [f"Účel: {self.popis_ucelu()}",
             f"Přístroj: {self.pristroj} (σ směru {self.sigma_smer_mgon:g} mgon, σ délky "
             f"{self.sigma_delka_mm:g} mm + {self.sigma_delka_ppm:g} ppm)"]
        return r


def vzorec(text: str, **promenne) -> float | None:
    """Vyhodnotí vzorec tolerance z Gromy („0.002*SQRT(s) + 0.04“, „100*SQRT(n + 0)“); jen čísla, + − * / **,
    závorky, SQRT a proměnné. Prázdný nebo chybný vzorec → None."""
    import ast
    t = (text or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        strom = ast.parse(t.replace("^", "**"), mode="eval")
    except SyntaxError:
        return None
    prom = {k.lower(): float(v) for k, v in promenne.items()}

    def hod(u):
        if isinstance(u, ast.Expression):
            return hod(u.body)
        if isinstance(u, ast.Constant) and isinstance(u.value, (int, float)):
            return float(u.value)
        if isinstance(u, ast.Name) and u.id.lower() in prom:
            return prom[u.id.lower()]
        if isinstance(u, ast.UnaryOp) and isinstance(u.op, (ast.USub, ast.UAdd)):
            v = hod(u.operand)
            return -v if isinstance(u.op, ast.USub) else v
        if isinstance(u, ast.BinOp) and isinstance(u.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            a, b = hod(u.left), hod(u.right)
            if isinstance(u.op, ast.Pow) and abs(b) > 10:
                raise ValueError
            return {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b,
                    ast.Div: a / b if b else math.inf, ast.Pow: a ** b}[type(u.op)]
        if (isinstance(u, ast.Call) and isinstance(u.func, ast.Name) and u.func.id.lower() == "sqrt"
                and len(u.args) == 1 and not u.keywords):
            return math.sqrt(max(0.0, hod(u.args[0])))
        raise ValueError
    try:
        v = hod(strom)
    except (ValueError, TypeError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def zkresleni(y: float, x: float, h: float | None = None) -> tuple[float, float | None]:
    """(měřítko Křovákova zobrazení v bodě, oprava z nadmořské výšky R/(R+H) nebo None bez výšky)."""
    from .sjtsk import meritko_zobrazeni
    m = meritko_zobrazeni(abs(y), abs(x))
    return m, (None if h is None else R_ZEME / (R_ZEME + h))


_AKTUALNI = NastaveniVypoctu()


def aktualni() -> NastaveniVypoctu:
    return _AKTUALNI


def nastav(n: NastaveniVypoctu) -> None:
    global _AKTUALNI
    _AKTUALNI = n
