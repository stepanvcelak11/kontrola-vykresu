"""Propojení s QTrig (terénní aplikace pro geodety): body a zápisníky z terénu do kanceláře.

Dvě cesty, obě jen ČTOU – v QTrig se nic nemění:

1) Firemní cloud QTrig (stejný server, přes který si body sdílejí mobily ve firmě):
   přihlášení kódem účtu a heslem (nebo kódem firmy + jménem + heslem), výběr zakázky
   a stažení jejích bodů (``GET /sync/points``). Synchronizace je přírůstková – drží se
   kurzor serveru, takže další stažení přinese jen nové a změněné body. V QTrig je potřeba
   u zakázky zapnout Nastavení → Data → Firemní cloud → „Sdílet body této zakázky ve firmě“.
2) Soubory exportované z QTrig: body (JSON „moje_body_*.json“ i CSV/TXT „název;Y;X;Z;kód“),
   nivelační zápisník a zápisník vodorovných směrů (CSV).

QTrig ukládá body ve WGS84; do S-JTSK se převádějí stejnými parametry jako v QTrig
(proj4 +towgs84, viz ``sjtsk.HELMERT_PROJ4``), takže souřadnice sedí na milimetr s tím,
co QTrig ukazuje a exportuje.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .geodezie import sjtsk
from .geodezie.body import Bod

API = "https://ar-geodet-api.ar-geodet.workers.dev"
VERZE = "kontrola-vykresu"


class ChybaQTrig(Exception):
    pass


# ------------------------------------------------------------------ body
def bod_z_qtrig(p: dict) -> Bod | None:
    """Bod QTrig ({id, name, lat, lng, vyska, kod, acc, …}) → bod seznamu souřadnic v S-JTSK."""
    try:
        la, lo = float(p["lat"]), float(p["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (47 < la < 52 and 11 < lo < 20):
        return None  # mimo území S-JTSK (QTrig umí i body v zahraničí)
    y, x, _h = sjtsk.wgs84_na_sjtsk(la, lo, parametry=sjtsk.HELMERT_PROJ4)
    z = p.get("vyska")
    try:
        z = None if z is None or z == "" else float(z)
    except (TypeError, ValueError):
        z = None
    pozn = ["QTrig"]
    if p.get("acc") is not None:
        pozn.append(f"přesnost GNSS {p['acc']} m")
    puvod = (p.get("prov") or {}).get("origin") if isinstance(p.get("prov"), dict) else None
    if puvod:
        pozn.append(f"původ {puvod}")
    return Bod(str(p.get("name") or p.get("id") or "?").strip(), round(y, 4), round(x, 4), z,
               kod=str(p.get("kod") or "").strip(), poznamka=", ".join(pozn))


def body_z_json(data) -> list[Bod]:
    """Body z JSON exportu QTrig (pole bodů, případně {points: […]} / záloha s arCustomPoints12)."""
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    if isinstance(data, dict):
        for k in ("points", "body", "arCustomPoints12"):
            if k in data:
                data = data[k]
                break
        if isinstance(data, str):
            data = json.loads(data)
    if not isinstance(data, list):
        raise ChybaQTrig("Soubor neobsahuje body QTrig.")
    out = [b for b in (bod_z_qtrig(p) for p in data if isinstance(p, dict)) if b is not None]
    return out


def je_qtrig_json(text: str) -> bool:
    t = text.lstrip("﻿ \r\n\t")
    return t[:1] in "[{" and '"lat"' in t[:4000] and '"lng"' in t[:4000]


# ------------------------------------------------------------------ zápisníky (CSV export QTrig)
def _cislo(s: str):
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class NivelaceQTrig:
    nazev: str
    vychozi_vyska: float | None
    radky: list[tuple[str, float | None, float | None]]  # bod, čtení vzad, čtení vpřed


@dataclass
class SmeryQTrig:
    nazev: str
    stanovisko: str
    # cíl, průměrný redukovaný směr [gon], průměrný zenit [gon], vodorovná délka [m], převýšení [m]
    cile: list[tuple[str, float | None, float | None, float | None, float | None]] = field(default_factory=list)


def nacti_zapisnik(text: str):
    """Nivelační zápisník nebo zápisník směrů z exportu QTrig (CSV se středníky)."""
    radky = [r.rstrip("\r") for r in text.lstrip("﻿").splitlines()]
    if not radky:
        raise ChybaQTrig("Prázdný soubor.")
    hlava = radky[0]
    if hlava.startswith("NIVELAČNÍ ZÁPISNÍK"):
        nazev = hlava.split("—", 1)[-1].strip()
        h0 = None
        m = re.search(r"Výchozí výška:\s*([-\d.,]+)", "\n".join(radky[:3]))
        if m:
            h0 = _cislo(m.group(1))
        out = []
        data = False
        for r in radky[1:]:
            if r.startswith("bod;"):
                data = True
                continue
            if not data or not r.strip() or r.startswith("Σ") or r.startswith("Uzávěr"):
                if data and not r.strip():
                    data = False
                continue
            c = r.split(";")
            out.append((c[0].strip(), _cislo(c[1]) if len(c) > 1 else None, _cislo(c[2]) if len(c) > 2 else None))
        return NivelaceQTrig(nazev, h0, out)
    if hlava.startswith("ZÁPISNÍK VODOROVNÝCH SMĚRŮ"):
        nazev = hlava.split("—", 1)[-1].strip()
        st = ""
        if len(radky) > 1:
            m = re.match(r"Stanovisko:\s*([^;]*)", radky[1])
            if m:
                st = m.group(1).strip().strip("—").strip()
        z = SmeryQTrig(nazev, st)
        for r in radky[3:]:
            c = r.split(";")
            if len(c) < 13 or c[0] == "cíl" or c[1].strip() != "1":
                continue  # souhrnné hodnoty jsou u první skupiny cíle
            z.cile.append((c[0].strip(), _cislo(c[7]), _cislo(c[9]), _cislo(c[11]), _cislo(c[12])))
        return z
    raise ChybaQTrig("Soubor není zápisník exportovaný z QTrig.")


def smery_na_stanovisko(z: SmeryQTrig, vp: float = 0.0):
    """Zápisník směrů QTrig → stanovisko zápisníku (orientace a podrobné body doplní uživatel)."""
    import math

    from .vypocet import Obs, Station
    if not z.stanovisko:
        raise ChybaQTrig("V zápisníku směrů chybí stanovisko.")
    st = Station(z.stanovisko, vp)
    for cil, hz, zen, d, dh in z.cile:
        if hz is None:
            continue
        zen = 100.0 if zen is None else zen
        # vodorovná délka → šikmá (výpočet zápisníku pracuje se šikmou délkou a zenitem)
        sd = d / max(1e-9, math.sin(zen * math.pi / 200)) if d else 0.0
        st.detail.append(Obs(cil, sd, 0.0, hz, zen))
    return st


# ------------------------------------------------------------------ cloud
def klic_zakazky(nazev: str) -> str:
    """Klíč zakázky na serveru = normalizovaný název (jako v QTrig: mezery, malá písmena, max 60)."""
    k = re.sub(r"\s+", " ", str(nazev)).strip().lower()
    return k[:60]


class Klient:
    """Klient firemního cloudu QTrig (jen čtení bodů)."""

    def __init__(self, api: str = API, token: str | None = None, otevri=None, timeout: float = 20.0):
        self.api = api.rstrip("/")
        self.token = token
        self.uzivatel = ""
        self.firma = ""
        self._otevri = otevri or urllib.request.urlopen
        self.timeout = timeout

    def _pozadavek(self, metoda: str, cesta: str, telo: dict | None = None, query: dict | None = None):
        url = self.api + cesta + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(telo).encode() if telo is not None else None
        hl = {"Content-Type": "application/json", "X-AG-Ver": VERZE, "Accept": "application/json"}
        if self.token:
            hl["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(url, data=data, headers=hl, method=metoda)
        try:
            with self._otevri(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                zprava = json.loads(e.read().decode("utf-8")).get("error")
            except Exception:  # noqa: BLE001
                zprava = None
            if e.code == 401 and cesta != "/login":
                self.token = None
                raise ChybaQTrig("Přihlášení vypršelo – přihlaste se znovu.") from None
            raise ChybaQTrig(zprava or f"Server QTrig odpověděl chybou {e.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ChybaQTrig(f"Server QTrig není dostupný ({getattr(e, 'reason', e)}). Zkontrolujte připojení "
                             "k internetu.") from None
        except json.JSONDecodeError:
            raise ChybaQTrig("Server QTrig vrátil nečitelnou odpověď.") from None

    def prihlas(self, kod: str, heslo: str, jmeno: str = "") -> dict:
        """Kód účtu (8 znaků) + heslo, nebo kód firmy + jméno + heslo (starší firemní účty)."""
        telo = {"code": kod.strip(), "password": heslo}
        if jmeno.strip():
            telo["name"] = jmeno.strip()
        r = self._pozadavek("POST", "/login", telo)
        if not r.get("token"):
            raise ChybaQTrig(r.get("error") or "Přihlášení se nepovedlo.")
        self.token = r["token"]
        self.uzivatel = (r.get("user") or {}).get("name", "")
        self.firma = ((r.get("config") or {}).get("firm") or {}).get("name", "") if isinstance(
            (r.get("config") or {}).get("firm"), dict) else ""
        return r

    def zakazky(self) -> list[dict]:
        """[{key, name, …}] – zakázky firmy, které server zná (živé, ne smazané)."""
        r = self._pozadavek("GET", "/jobs")
        return [j for j in r.get("jobs", []) if not j.get("deleted")]

    def zmeny_bodu(self, klic: str, od: int = 0):
        """Všechny změny bodů zakázky od kurzoru → (seznam řádků {id, data, deleted, …}, nový kurzor)."""
        radky, kurzor = [], od
        for _ in range(200):  # max 100 000 změn
            r = self._pozadavek("GET", "/sync/points", query={"job": klic, "since": kurzor})
            dav = r.get("points", [])
            radky += dav
            if dav:
                kurzor = max(kurzor, max(int(x.get("srv") or 0) for x in dav))
            if not r.get("more") or not dav:
                break
        return radky, kurzor


@dataclass
class StavSync:
    """Co už bylo z cloudu staženo (kvůli přírůstkové synchronizaci)."""

    klic: str = ""
    kurzor: int = 0
    body: dict[str, dict] = field(default_factory=dict)  # id QTrig → data bodu


def sync(klient: Klient, stav: StavSync, klic: str) -> tuple[list[Bod], list[str], StavSync]:
    """Stáhne změny zakázky. Vrací (aktuální body zakázky v S-JTSK, čísla smazaných bodů, nový stav)."""
    if stav.klic != klic:
        stav = StavSync(klic)
    radky, kurzor = klient.zmeny_bodu(klic, stav.kurzor)
    smazane = []
    for r in radky:
        pid = str(r.get("id"))
        if r.get("deleted"):
            stary = stav.body.pop(pid, None)
            if stary is not None:
                smazane.append(str(stary.get("name") or pid))
            continue
        try:
            d = json.loads(r["data"]) if isinstance(r.get("data"), str) else r.get("data")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(d, dict):
            stav.body[pid] = d
    stav.kurzor = kurzor
    body = [b for b in (bod_z_qtrig(d) for d in stav.body.values()) if b is not None]
    return body, smazane, stav


def nacti_soubor(cesta: str | Path):
    """Libovolný export QTrig: body (JSON) → list[Bod], zápisník (CSV) → NivelaceQTrig / SmeryQTrig."""
    raw = Path(cesta).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1250", errors="replace")
    if je_qtrig_json(text):
        return body_z_json(text)
    return nacti_zapisnik(text)


def sloucit(seznam, body: list[Bod], smazane: list[str] = (), smazat: bool = True) -> tuple[int, int, int]:
    """Body z QTrig do seznamu souřadnic jako jedna změna (jedno Zpět). Vrací (nové, změněné, smazané).

    Změněný bod (jiné souřadnice, výška nebo kód) se přepíše. Smaže se jen bod, který do seznamu
    přišel z QTrig (poznámka „QTrig…“) – ručně zadané nebo spočtené body se nikdy nesmažou."""
    import copy
    vysledek = [0, 0, 0]
    smaz = set(smazane) if smazat else set()

    def stejny(a: Bod, b: Bod) -> bool:
        return (abs(a.y - b.y) < 5e-5 and abs(a.x - b.x) < 5e-5 and a.kod == b.kod
                and (a.z is None) == (b.z is None) and (a.z is None or abs(a.z - b.z) < 5e-5))

    def fn(seznam_body):
        index = {b.cislo: i for i, b in enumerate(seznam_body)}
        for b in body:
            i = index.get(b.cislo)
            if i is None:
                index[b.cislo] = len(seznam_body)
                seznam_body.append(copy.copy(b))
                vysledek[0] += 1
            elif not stejny(seznam_body[i], b):
                seznam_body[i] = copy.copy(b)
                vysledek[1] += 1
        if smaz:
            pred = len(seznam_body)
            seznam_body[:] = [b for b in seznam_body
                              if not (b.cislo in smaz and (b.poznamka or "").startswith("QTrig"))]
            vysledek[2] = pred - len(seznam_body)
        return sum(vysledek)

    if body or smaz:
        seznam.zmen("Body z QTrig", fn, len(body) + len(smaz))
    return tuple(vysledek)


def nivelace_vypocet(n: NivelaceQTrig) -> tuple[list[tuple[str, float]], list[str]]:
    """Výšky bodů nivelačního zápisníku QTrig (z výchozí výšky) a řádky protokolu."""
    if n.vychozi_vyska is None:
        raise ChybaQTrig("V nivelačním zápisníku chybí výchozí výška.")
    vysky, prot = [], [f"NIVELACE Z QTRIG – {n.nazev}", f"výchozí výška {n.vychozi_vyska:.3f} m",
                       "  bod             vzad z     vpřed p     převýšení      výška"]
    h, zpet = n.vychozi_vyska, None
    for i, (bod, z, p) in enumerate(n.radky):
        dh = None
        if i > 0:
            if zpet is None or p is None:
                raise ChybaQTrig(f"Nivelace: u bodu {bod} chybí čtení (vzad na předchozím nebo vpřed).")
            dh = zpet - p
            h += dh
        vysky.append((bod, h))
        prot.append(f"  {bod:<14}{'' if z is None else f'{z:.3f}':>9}{'' if p is None else f'{p:.3f}':>12}"
                    f"{'' if dh is None else f'{dh:+.3f}':>14}{h:>11.3f}")
        zpet = z
    return vysky, prot
