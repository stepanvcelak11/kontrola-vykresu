"""Spojnice bodů seznamu souřadnic (kresba jako v grafice Gromy): ručně nebo podle kódů.

Spojnice odkazuje na čísla bodů, takže po opravě souřadnic bodu se „pohne“ s ním. Ukládá se
do projektu vedle seznamu souřadnic (vypocty/spojnice.json) a jde jedním příkazem přenést do CAD.
"""

from __future__ import annotations

import json
from pathlib import Path

from .body import klic_cisla


class Spojnice:
    def __init__(self, dvojice=None):
        self.dvojice: list[tuple[str, str]] = []
        for a, b in dvojice or []:
            self.pridej(a, b)

    def __len__(self) -> int:
        return len(self.dvojice)

    @staticmethod
    def _klic(a: str, b: str) -> frozenset:
        return frozenset((a, b))

    def je(self, a: str, b: str) -> bool:
        k = self._klic(a, b)
        return any(self._klic(*d) == k for d in self.dvojice)

    def pridej(self, a: str, b: str) -> bool:
        a, b = str(a).strip(), str(b).strip()
        if not a or not b or a == b or self.je(a, b):
            return False
        self.dvojice.append((a, b))
        return True

    def smaz(self, a: str, b: str) -> bool:
        k = self._klic(a, b)
        pred = len(self.dvojice)
        self.dvojice = [d for d in self.dvojice if self._klic(*d) != k]
        return len(self.dvojice) < pred

    def prepni(self, a: str, b: str) -> bool:
        """Přidá spojnici, nebo ji smaže, pokud už je. Vrací True = teď existuje."""
        if self.smaz(a, b):
            return False
        return self.pridej(a, b)

    def smaz_body(self, cisla) -> int:
        s = set(cisla)
        pred = len(self.dvojice)
        self.dvojice = [d for d in self.dvojice if d[0] not in s and d[1] not in s]
        return pred - len(self.dvojice)

    def z_kodu(self, body, kod: str, uzavrit: bool = False) -> int:
        """Spojí body se stejným kódem do lomené čáry v pořadí čísel bodů (jak se měří po sobě)."""
        rada = sorted((b for b in body if (b.kod or "").strip() == kod.strip()), key=lambda b: klic_cisla(b.cislo))
        n = 0
        for p, q in zip(rada, rada[1:]):
            n += self.pridej(p.cislo, q.cislo)
        if uzavrit and len(rada) > 2:
            n += self.pridej(rada[-1].cislo, rada[0].cislo)
        return n

    def platne(self, seznam) -> list[tuple[object, object]]:
        """Dvojice bodů, které v seznamu existují (spojnice na smazaný bod se nekreslí)."""
        out = []
        for a, b in self.dvojice:
            pa, pb = seznam.najdi(a), seznam.najdi(b)
            if pa is not None and pb is not None:
                out.append((pa, pb))
        return out

    def uloz(self, cesta: str | Path) -> None:
        Path(cesta).parent.mkdir(parents=True, exist_ok=True)
        Path(cesta).write_text(json.dumps({"spojnice": self.dvojice}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def nacti(cls, cesta: str | Path) -> "Spojnice":
        p = Path(cesta)
        if not p.exists():
            return cls()
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(tuple(x) for x in d.get("spojnice", []) if isinstance(x, (list, tuple)) and len(x) == 2)
