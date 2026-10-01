"""Seznam souřadnic: body (číslo, Y, X, Z, kód, kvalita), úpravy, duplicity, historie a Zpět / Znovu.

Každá změna seznamu jde přes :meth:`SeznamBodu.zmen` – uloží se stav pro Zpět a záznam do historie
(„co, kdy, kolik bodů“). Data se nikdy neztrácí potichu: slučování duplicit nechá rozhodnout uživatele,
mazání jde vrátit.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Bod:
    cislo: str
    y: float
    x: float
    z: float | None = None
    kod: str = ""  # kód (typ) bodu, např. „plot“, „roh budovy“, nebo číselný kód zaměření
    kvalita: int | None = None  # kód kvality 1–8 podle katastrální vyhlášky
    poznamka: str = ""

    def vzdalenost(self, o: "Bod") -> float:
        return math.hypot(self.y - o.y, self.x - o.x)


def klic_cisla(cislo: str):
    """Řazení čísel bodů „jako člověk“: 2 < 10 < 4001, 13-1 < 13-2, text za čísly."""
    parts = re.split(r"(\d+)", cislo.strip())
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.lower()) for p in parts if p != ""]


@dataclass
class Duplicita:
    """Skupina bodů se stejným číslem (druh „cislo“) nebo téměř stejnou polohou (druh „poloha“)."""

    druh: str
    body: list[Bod]
    odchylka: float  # největší vzdálenost mezi body skupiny [m]

    def popis(self) -> str:
        cisla = ", ".join(b.cislo for b in self.body)
        if self.druh == "cislo":
            return f"Číslo {self.body[0].cislo} je {len(self.body)}× (rozdíl poloh {self.odchylka:.3f} m)"
        return f"Body {cisla} jsou na stejném místě (do {self.odchylka:.3f} m)"


@dataclass
class Zmena:
    cas: str
    popis: str
    pocet: int


@dataclass
class SeznamBodu:
    body: list[Bod] = field(default_factory=list)
    historie: list[Zmena] = field(default_factory=list)
    _zpet: list[list[Bod]] = field(default_factory=list, repr=False)
    _znovu: list[list[Bod]] = field(default_factory=list, repr=False)
    MAX_ZPET = 200

    # ------------------------------------------------------------ hledání
    def __len__(self) -> int:
        return len(self.body)

    def najdi(self, cislo: str) -> Bod | None:
        c = cislo.strip()
        return next((b for b in self.body if b.cislo == c), None)

    def filtruj(self, text: str = "", kod: str | None = None, kvalita: int | None = None) -> list[Bod]:
        """Body podle hledaného textu (v čísle, kódu, poznámce), kódu a kódu kvality."""
        t = text.strip().lower()
        out = []
        for b in self.body:
            if t and t not in b.cislo.lower() and t not in b.kod.lower() and t not in b.poznamka.lower():
                continue
            if kod is not None and b.kod != kod:
                continue
            if kvalita is not None and b.kvalita != kvalita:
                continue
            out.append(b)
        return out

    def kody(self) -> list[str]:
        return sorted({b.kod for b in self.body if b.kod})

    # ------------------------------------------------------------ změny (všechny jdou vrátit)
    def zmen(self, popis: str, fn, pocet: int | None = None):
        """Provede změnu ``fn(body)`` se zálohou pro Zpět a záznamem do historie; vrátí výsledek ``fn``."""
        zaloha = copy.deepcopy(self.body)
        vysledek = fn(self.body)
        if self.body == zaloha:
            return vysledek  # nic se nezměnilo – nic do historie
        self._zpet.append(zaloha)
        del self._zpet[:-self.MAX_ZPET]
        self._znovu.clear()
        self.historie.append(Zmena(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), popis,
                                   pocet if pocet is not None else len(self.body)))
        del self.historie[:-500]
        return vysledek

    def lze_zpet(self) -> bool:
        return bool(self._zpet)

    def lze_znovu(self) -> bool:
        return bool(self._znovu)

    def zpet(self) -> bool:
        if not self._zpet:
            return False
        self._znovu.append(copy.deepcopy(self.body))
        self.body = self._zpet.pop()
        self.historie.append(Zmena(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Zpět", len(self.body)))
        return True

    def znovu(self) -> bool:
        if not self._znovu:
            return False
        self._zpet.append(copy.deepcopy(self.body))
        self.body = self._znovu.pop()
        self.historie.append(Zmena(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Znovu", len(self.body)))
        return True

    def pridej(self, nove: list[Bod], popis: str = "Přidání bodů", prepsat: bool = False) -> tuple[int, list[str]]:
        """Přidá body. Číslo, které už v seznamu je, se **nepřepíše** (vrátí se v seznamu konfliktů),
        pokud není ``prepsat=True``. Vrací (počet přidaných/přepsaných, čísla v konfliktu)."""
        konflikty: list[str] = []

        def fn(body):
            index = {b.cislo: i for i, b in enumerate(body)}
            n = 0
            for b in nove:
                if b.cislo in index:
                    if prepsat:
                        body[index[b.cislo]] = copy.copy(b)
                        n += 1
                    else:
                        konflikty.append(b.cislo)
                    continue
                index[b.cislo] = len(body)
                body.append(copy.copy(b))
                n += 1
            return n

        n = self.zmen(popis, fn, len(nove))
        return n, konflikty

    def uprav(self, cislo: str, /, **hodnoty) -> bool:
        """Upraví jeden bod (např. ``uprav("12", z=258.3, kod="plot")``). Nové číslo nesmí kolidovat."""
        b = self.najdi(cislo)
        if b is None:
            return False
        nove_cislo = hodnoty.get("cislo")
        if nove_cislo is not None and nove_cislo.strip() != cislo and self.najdi(nove_cislo) is not None:
            raise ValueError(f"Bod číslo {nove_cislo} už v seznamu je.")

        def fn(body):
            for i, x in enumerate(body):
                if x.cislo == cislo:
                    d = asdict(x)
                    d.update({k: (v.strip() if isinstance(v, str) and k == "cislo" else v)
                              for k, v in hodnoty.items()})
                    body[i] = Bod(**d)
                    return True
            return False

        return self.zmen(f"Úprava bodu {cislo}", fn, 1)

    def smaz(self, cisla: list[str]) -> int:
        s = {c.strip() for c in cisla}

        def fn(body):
            pred = len(body)
            body[:] = [b for b in body if b.cislo not in s]
            return pred - len(body)

        return self.zmen(f"Smazání {len(s)} bodů", fn, len(s))

    def serad(self, podle: str = "cislo", obracene: bool = False) -> None:
        kl = {"cislo": lambda b: klic_cisla(b.cislo), "y": lambda b: b.y, "x": lambda b: b.x,
              "z": lambda b: (b.z is None, b.z or 0.0), "kod": lambda b: (b.kod.lower(), klic_cisla(b.cislo)),
              "kvalita": lambda b: (b.kvalita is None, b.kvalita or 0)}[podle]
        self.zmen(f"Seřazení podle {podle}", lambda body: body.sort(key=kl, reverse=obracene))

    # ------------------------------------------------------------ hromadné úpravy
    def hromadne(self, cisla: list[str], *, kod: str | None = None, kvalita: int | None = None,
                 dy: float = 0.0, dx: float = 0.0, dz: float = 0.0,
                 predpona: str | None = None, pricti_k_cislu: int = 0) -> int:
        """Hromadná úprava vybraných bodů: kód, kvalita, posun, předpona čísla, přičtení k číslu."""
        s = {c.strip() for c in cisla}
        nova_cisla: dict[str, str] = {}
        for b in self.body:
            if b.cislo not in s:
                continue
            c = b.cislo
            if pricti_k_cislu:
                if not c.isdigit():
                    raise ValueError(f"K číslu „{c}“ nejde přičítat (není číselné).")
                c = str(int(c) + pricti_k_cislu)
            if predpona:
                c = predpona + c
            nova_cisla[b.cislo] = c
        ostatni = {b.cislo for b in self.body if b.cislo not in s}
        kolize = sorted({c for c in nova_cisla.values() if c in ostatni}, key=klic_cisla)
        if len(set(nova_cisla.values())) != len(nova_cisla) or kolize:
            raise ValueError("Po přečíslování by vznikla stejná čísla bodů: " + ", ".join(kolize[:10]))

        def fn(body):
            n = 0
            for i, b in enumerate(body):
                if b.cislo not in s:
                    continue
                d = asdict(b)
                d["cislo"] = nova_cisla[b.cislo]
                if kod is not None:
                    d["kod"] = kod
                if kvalita is not None:
                    d["kvalita"] = kvalita
                d["y"] += dy
                d["x"] += dx
                if dz and d["z"] is not None:
                    d["z"] += dz
                body[i] = Bod(**d)
                n += 1
            return n

        return self.zmen(f"Hromadná úprava {len(s)} bodů", fn, len(s))

    # ------------------------------------------------------------ duplicity
    def duplicity(self, tol: float = 0.01) -> list[Duplicita]:
        """Stejné číslo vícekrát a různá čísla na stejném místě (do ``tol`` m)."""
        out: list[Duplicita] = []
        podle: dict[str, list[Bod]] = {}
        for b in self.body:
            podle.setdefault(b.cislo, []).append(b)
        for skup in podle.values():
            if len(skup) > 1:
                d = max(a.vzdalenost(b) for a in skup for b in skup)
                out.append(Duplicita("cislo", skup, d))
        # poloha – mřížka o velikosti tol
        if tol > 0:
            cell: dict[tuple[int, int], list[Bod]] = {}
            for b in self.body:
                cell.setdefault((int(b.y // tol), int(b.x // tol)), []).append(b)
            videno: set[int] = set()
            for (cy, cx), lst in cell.items():
                for b in lst:
                    if id(b) in videno:
                        continue
                    skup = [b]
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            for o in cell.get((cy + dy, cx + dx), ()):
                                if o is not b and id(o) not in videno and o.cislo != b.cislo \
                                        and b.vzdalenost(o) <= tol:
                                    skup.append(o)
                    if len(skup) > 1:
                        videno.update(id(o) for o in skup)
                        out.append(Duplicita("poloha", skup, max(a.vzdalenost(c) for a in skup for c in skup)))
        return out

    def sluc(self, ponechat: Bod, odstranit: list[Bod], prumerovat: bool = False) -> None:
        """Bezpečné sloučení duplicit: ``ponechat`` zůstane (volitelně s průměrem polohy a výšky),
        ``odstranit`` zmizí. Jde vrátit Zpět; v poznámce zůstane, co se sloučilo."""
        ids = {id(b) for b in odstranit}
        if id(ponechat) in ids:
            raise ValueError("Bod, který má zůstat, nemůže být zároveň mezi odstraněnými.")

        def fn(body):
            for i, b in enumerate(body):
                if b is ponechat:
                    d = asdict(b)
                    if prumerovat:
                        vse = [ponechat] + list(odstranit)
                        d["y"] = sum(v.y for v in vse) / len(vse)
                        d["x"] = sum(v.x for v in vse) / len(vse)
                        zs = [v.z for v in vse if v.z is not None]
                        d["z"] = sum(zs) / len(zs) if zs else None
                    pozn = "sloučeno s " + ", ".join(o.cislo for o in odstranit)
                    d["poznamka"] = (d["poznamka"] + "; " if d["poznamka"] else "") + pozn
                    body[i] = Bod(**d)
            body[:] = [b for b in body if id(b) not in ids]

        self.zmen(f"Sloučení {ponechat.cislo} s {len(odstranit)} body", fn, 1 + len(odstranit))

    # ------------------------------------------------------------ uložení (automaticky v projektu)
    def to_json(self) -> str:
        return json.dumps({"verze": 1, "body": [asdict(b) for b in self.body],
                           "historie": [asdict(h) for h in self.historie[-200:]]},
                          ensure_ascii=False, indent=0)

    @classmethod
    def from_json(cls, text: str) -> "SeznamBodu":
        d = json.loads(text)
        s = cls()
        s.body = [Bod(**{k: v for k, v in b.items() if k in Bod.__dataclass_fields__}) for b in d.get("body", [])]
        s.historie = [Zmena(**h) for h in d.get("historie", [])]
        return s

    def uloz(self, path: str | Path) -> None:
        from ..safeio import write_text_atomic
        write_text_atomic(Path(path), self.to_json())

    @classmethod
    def nacti(cls, path: str | Path) -> "SeznamBodu":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.from_json(p.read_text(encoding="utf-8"))
