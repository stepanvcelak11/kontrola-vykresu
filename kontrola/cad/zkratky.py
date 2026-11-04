"""Vlastní klávesové zkratky a zkratky příkazového řádku v CAD (jako funkční klávesy a key-in aliasy
MicroStationu).

Klávesa spouští libovolný řádek příkazu – nástroj („úsečka“), příkaz s parametrem („zhasni vše kromě 58“,
„vyber barva 3“, „prvek budovy“) nebo předvolbu „předvolba 3“ (třetí druh prvku v poli Kreslím).
Zkratka příkazového řádku nahradí napsané slovo jiným příkazem („bu“ → „prvek budovy“).

Ukládá se jako JSON do QSettings (klíče ``cad/zkratky`` a ``cad/aliasy``), tady je jen čistá logika
bez Qt, aby šla testovat.
"""

from __future__ import annotations

import json

# klávesy, které CAD používá napevno (nejdou přemapovat, jen upozorníme na kolizi)
PEVNE = {
    "F3": "úchyty zap/vyp", "F8": "ortho", "F10": "polární režim", "Esc": "zrušit příkaz / výběr",
    "Del": "smazat výběr", "Ctrl+A": "vybrat vše", "Ctrl+C": "kopírovat do schránky",
    "Ctrl+V": "vložit ze schránky", "Ctrl+Z": "zpět", "Ctrl+Y": "vpřed", "Return": "potvrdit / zopakovat",
    "Enter": "potvrdit / zopakovat", "Space": "nabídka naposledy použitých příkazů",
}

# výchozí funkční klávesy – volné klávesy, které aplikace jinde nepoužívá
VYCHOZI: dict[str, str] = {
    "F2": "úsečka",
    "F4": "polylinie",
    "F6": "text",
    "F7": "posun",
    "F9": "kopie",
    "F12": "celý",
    "Shift+F2": "bod",
    "Shift+F4": "kružnice",
    "Shift+F6": "uprav text",
    "Shift+F7": "otoč",
    "Shift+F9": "rovnoběžka",
    "Shift+F12": "předchozí pohled",
    **{f"Ctrl+{i}": f"předvolba {i}" for i in range(1, 10)},
}

VYCHOZI_ALIASY: dict[str, str] = {}


def normalizuj_klavesu(k: str) -> str:
    """Sjednotí zápis klávesy („ctrl + f2“ → „Ctrl+F2“), aby šly zkratky porovnat."""
    parts = [p.strip() for p in str(k or "").replace(" ", "").split("+") if p.strip()]
    if not parts:
        return ""
    mods = {"ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift", "alt": "Alt", "meta": "Meta"}
    out_m = [mods[p.lower()] for p in parts[:-1] if p.lower() in mods]
    key = parts[-1]
    key = {"esc": "Esc", "escape": "Esc", "del": "Del", "delete": "Del", "space": "Space", "mezerník": "Space",
           "enter": "Enter", "return": "Return"}.get(key.lower(), key.upper() if len(key) == 1 else
                                                     key[0].upper() + key[1:])
    poradi = ["Ctrl", "Alt", "Shift", "Meta"]
    return "+".join(sorted(set(out_m), key=poradi.index) + [key])


def nacti(text: str | None, vychozi: dict[str, str]) -> dict[str, str]:
    """JSON z nastavení → mapa. Poškozené nebo chybějící nastavení = výchozí."""
    if not text:
        return dict(vychozi)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return dict(vychozi)
    if not isinstance(data, dict):
        return dict(vychozi)
    return {str(k): str(v).strip() for k, v in data.items() if str(k).strip() and str(v).strip()}


def uloz(mapa: dict[str, str]) -> str:
    return json.dumps({k: v for k, v in mapa.items() if k and v}, ensure_ascii=False, sort_keys=True)


def nacti_zkratky(text: str | None) -> dict[str, str]:
    return {normalizuj_klavesu(k): v for k, v in nacti(text, VYCHOZI).items() if normalizuj_klavesu(k)}


def nacti_aliasy(text: str | None) -> dict[str, str]:
    return {k.strip().lower(): v for k, v in nacti(text, VYCHOZI_ALIASY).items()}


def konflikty(mapa: dict[str, str], obsazene: dict[str, str] | None = None) -> list[str]:
    """Kolize zkratek: s pevnými klávesami CAD a s klávesami zbytku aplikace (``obsazene``)."""
    obs = {normalizuj_klavesu(k): v for k, v in {**PEVNE, **(obsazene or {})}.items()}
    out = []
    for k, v in sorted(mapa.items()):
        n = normalizuj_klavesu(k)
        if n in obs:
            out.append(f"{n}: „{v}“ koliduje s „{obs[n]}“")
    return out


def rozbal_alias(text: str, aliasy: dict[str, str]) -> str:
    """Zkratka příkazového řádku: celé slovo nebo první slovo („bu“, „bu 2“ → „prvek budovy 2“)."""
    t = text.strip()
    if not t or not aliasy:
        return text
    if t.lower() in aliasy:
        return aliasy[t.lower()]
    prvni, _, zbytek = t.partition(" ")
    if prvni.lower() in aliasy and zbytek:
        return f"{aliasy[prvni.lower()]} {zbytek}"
    return text


class HistorieRadku:
    """Historie příkazového řádku (šipky nahoru / dolů jako v key-in MicroStationu)."""

    def __init__(self, maximum: int = 100):
        self.polozky: list[str] = []
        self.maximum = maximum
        self._i: int | None = None

    def pridej(self, t: str) -> None:
        t = t.strip()
        self._i = None
        if not t:
            return
        if self.polozky and self.polozky[-1] == t:
            return
        self.polozky.append(t)
        del self.polozky[:-self.maximum]

    def zpet(self) -> str | None:
        if not self.polozky:
            return None
        self._i = len(self.polozky) - 1 if self._i is None else max(0, self._i - 1)
        return self.polozky[self._i]

    def vpred(self) -> str:
        if self._i is None:
            return ""
        self._i += 1
        if self._i >= len(self.polozky):
            self._i = None
            return ""
        return self.polozky[self._i]


def nedavne(seznam: list[str], prikaz: str, maximum: int = 10) -> list[str]:
    """Naposledy použité příkazy – nejnovější první, bez opakování."""
    out = [prikaz] + [p for p in seznam if p != prikaz]
    return out[:maximum]
