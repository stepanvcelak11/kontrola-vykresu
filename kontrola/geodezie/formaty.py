"""Import a export seznamu souřadnic v textu (TXT / CSV) s volitelným pořadím sloupců.

Formát se rozpozná sám (oddělovač, počet a význam sloupců, záporné souřadnice, prohozené Y/X),
uživatel ho může upravit. Špatné řádky se nepřeskočí potichu – vrátí se jako varování s číslem řádku.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .body import Bod

SLOUPCE = {"cislo": "Číslo bodu", "y": "Y", "x": "X", "z": "Z (výška)", "kod": "Kód", "kvalita": "Kvalita",
           "poznamka": "Poznámka", "-": "(přeskočit)"}
ODDELOVACE = {"auto": "rozpoznat", " ": "mezera / tabulátor", ";": "středník", ",": "čárka", "\t": "tabulátor"}


@dataclass
class Format:
    sloupce: list[str] = field(default_factory=lambda: ["cislo", "y", "x", "z"])
    oddelovac: str = "auto"
    desetinna_carka: bool = False  # 595975,72 místo 595975.72
    preskocit: int = 0  # počet řádků hlavičky
    zaporne: bool = False  # v souboru jsou souřadnice se znaménkem minus (−Y −X) → převést na kladné
    prohodit_yx: bool = False  # v souboru je nejdřív X, pak Y

    def popis(self) -> str:
        sl = " ".join(SLOUPCE.get(s, s) for s in self.sloupce)
        extra = [ODDELOVACE.get(self.oddelovac, self.oddelovac)]
        if self.desetinna_carka:
            extra.append("desetinná čárka")
        if self.zaporne:
            extra.append("záporné souřadnice")
        if self.prohodit_yx:
            extra.append("prohozené Y/X")
        if self.preskocit:
            extra.append(f"přeskočit {self.preskocit} ř.")
        return f"{sl} ({', '.join(extra)})"


def dekoduj(raw: bytes) -> str:
    if b"\x00" in raw[:4096]:
        raise ValueError("Soubor je binární (např. seznam z Kokeše .ss nebo Gromy .crd) – v původním programu "
                         "ho exportujte jako textový seznam (číslo Y X Z).")
    for enc in ("utf-8-sig", "cp1250"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _rozdel(line: str, odd: str) -> list[str]:
    if odd in ("auto", " "):
        return line.split()
    if odd in (",", ";", "\t"):
        return [p.strip() for p in next(csv.reader([line], delimiter=odd))]
    return line.split(odd)


def _cislo(s: str, carka: bool) -> float:
    s = s.strip().replace(" ", "")
    if carka:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 else s.replace(",", ".")
    return float(s)


def _je_cislo(s: str) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", s.strip()))


_HLAVICKA = {"cislo": ("cislo", "číslo", "c.b.", "č.b.", "cb", "bod", "id", "name", "point"),
             "y": ("y",), "x": ("x",), "z": ("z", "h", "vyska", "výška", "height"),
             "kod": ("kod", "kód", "code", "popis"), "kvalita": ("kvalita", "kk", "kód kvality", "kod kvality"),
             "poznamka": ("poznamka", "poznámka", "note")}


def _z_hlavicky(row: list[str]) -> list[str] | None:
    """Sloupce podle hlavičky („Číslo;Y;X;Z;Kód“)."""
    out = []
    for c in row:
        t = c.strip().lower().strip("[]()")
        hit = next((k for k, names in _HLAVICKA.items() if t in names), None)
        out.append(hit or "-")
    return out if sum(1 for c in out if c != "-") >= 3 else None


def rozpoznej(text: str) -> Format:
    """Odhadne formát podle obsahu: oddělovač, sloupce (číslo, souřadnice, výška, kód), znaménko, pořadí Y/X."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith((";", "#", "//"))]
    vzor = lines[:200]
    # oddělovač: středník / tabulátor / čárka (pozor na desetinnou čárku) / mezery
    odd = " "
    for cand in (";", "\t"):
        if vzor and sum(ln.count(cand) >= 2 for ln in vzor) >= 0.8 * len(vzor):
            odd = cand
            break
    else:
        if vzor and sum(ln.count(",") >= 2 and len(ln.split()) <= 2 for ln in vzor) >= 0.8 * len(vzor):
            odd = ","
    carka = odd != "," and any(re.search(r"\d,\d", ln) for ln in vzor)
    rows = [_rozdel(ln, odd) for ln in vzor]
    preskocit = 0
    for r in rows:  # hlavička = řádek, kde nejsou čísla tam, kde je mají ostatní
        if sum(_je_cislo(c) for c in r[1:3]) < 2:
            preskocit += 1
        else:
            break
    data = rows[preskocit:]
    n = max((len(r) for r in data), default=4)
    # podíl čísel mezi neprázdnými buňkami sloupce (prázdná výška u některých bodů nevadí)
    filled = [sum(1 for r in data if i < len(r) and r[i].strip()) for i in range(n)]
    num = [sum(1 for r in data if i < len(r) and _je_cislo(r[i])) for i in range(n)]
    sloupce = ["cislo"]
    coord = [i for i in range(1, n) if filled[i] and num[i] >= 0.9 * filled[i]]
    rest_text = [i for i in range(1, n) if filled[i] and num[i] < 0.5 * filled[i]]
    zhlavicky = _z_hlavicky(rows[preskocit - 1]) if preskocit else None
    if zhlavicky and "y" in zhlavicky and "x" in zhlavicky:
        sloupce = zhlavicky
    elif len(coord) >= 2:
        sloupce = ["cislo"] + ["-"] * (n - 1)
        sloupce[coord[0]] = "y"
        sloupce[coord[1]] = "x"
        if len(coord) >= 3:
            sloupce[coord[2]] = "z"
        if rest_text:
            sloupce[rest_text[0]] = "kod"
        while sloupce and sloupce[-1] == "-":
            sloupce.pop()
    else:
        sloupce = ["cislo", "y", "x", "z"]
    fmt = Format(sloupce=sloupce, oddelovac=odd, desetinna_carka=carka, preskocit=preskocit)
    # znaménko a pořadí: v S-JTSK je Y (≈ 430–900 km) menší než X (≈ 930–1 230 km)
    ys, xs = [], []
    iy, ix = sloupce.index("y") if "y" in sloupce else 1, sloupce.index("x") if "x" in sloupce else 2
    for r in data[:100]:
        try:
            ys.append(_cislo(r[iy], carka))
            xs.append(_cislo(r[ix], carka))
        except (ValueError, IndexError):
            continue
    if ys:
        if sum(1 for v in ys + xs if v < 0) > 0.8 * (len(ys) + len(xs)):
            fmt.zaporne = True
        ay = sum(abs(v) for v in ys) / len(ys)
        ax = sum(abs(v) for v in xs) / len(xs)
        if ay > 900_000 > ax > 300_000:
            fmt.prohodit_yx = True
    return fmt


def nacti_text(text: str, fmt: Format | None = None) -> tuple[list[Bod], list[str], Format]:
    """Načte body z textu. Vrací (body, varování s čísly řádků, použitý formát)."""
    fmt = fmt or rozpoznej(text)
    body: list[Bod] = []
    varovani: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if i <= fmt.preskocit or not line.strip() or line.lstrip().startswith((";", "#", "//")):
            continue
        cols = _rozdel(line, fmt.oddelovac)
        d: dict = {}
        try:
            for name, val in zip(fmt.sloupce, cols):
                if name in ("-", ""):
                    continue
                if name in ("y", "x", "z"):
                    d[name] = _cislo(val, fmt.desetinna_carka) if val.strip() else None
                elif name == "kvalita":
                    d[name] = int(val) if val.strip() else None
                else:
                    d[name] = val.strip()
        except ValueError:
            varovani.append(f"řádek {i}: nejde přečíst číslo – „{line.strip()[:60]}“")
            continue
        if not d.get("cislo") or d.get("y") is None or d.get("x") is None:
            varovani.append(f"řádek {i}: chybí číslo bodu nebo souřadnice – „{line.strip()[:60]}“")
            continue
        if fmt.prohodit_yx:
            d["y"], d["x"] = d["x"], d["y"]
        if fmt.zaporne:
            d["y"], d["x"] = -d["y"], -d["x"]
        if d.get("kvalita") is not None and not 1 <= d["kvalita"] <= 8:
            varovani.append(f"řádek {i}: kód kvality {d['kvalita']} není 1–8 – vynechán")
            d["kvalita"] = None
        body.append(Bod(**d))
    return body, varovani, fmt


def nacti_soubor(path: str | Path, fmt: Format | None = None) -> tuple[list[Bod], list[str], Format]:
    return nacti_text(dekoduj(Path(path).read_bytes()), fmt)


def zapis_text(body: list[Bod], sloupce: list[str] | None = None, oddelovac: str = " ",
               des_xy: int = 2, des_z: int = 2, hlavicka: bool = False, desetinna_carka: bool = False) -> str:
    """Seznam souřadnic do textu. Mezera = zarovnané sloupce (jako Groma), jinak CSV."""
    sloupce = sloupce or ["cislo", "y", "x", "z"]

    def fmt_val(b: Bod, s: str) -> str:
        v = getattr(b, s, "")
        if s in ("y", "x"):
            t = f"{v:.{des_xy}f}"
        elif s == "z":
            t = "" if v is None else f"{v:.{des_z}f}"
        elif s == "kvalita":
            t = "" if v is None else str(v)
        else:
            t = str(v or "")
        return t.replace(".", ",") if desetinna_carka and s in ("y", "x", "z") else t

    out = io.StringIO()
    if oddelovac == " ":
        if hlavicka:
            out.write("  ".join(SLOUPCE[s] for s in sloupce) + "\n")
        sirky = {"cislo": 16, "y": 14, "x": 14, "z": 10, "kod": 0, "kvalita": 3, "poznamka": 0}
        for b in body:
            parts = []
            for s in sloupce:
                t = fmt_val(b, s)
                w = sirky.get(s, 0)
                parts.append(t.ljust(w) if s == "cislo" else (t.rjust(w) if w else t))
            out.write(" ".join(parts).rstrip() + "\n")
    else:
        wr = csv.writer(out, delimiter=oddelovac, lineterminator="\n")
        if hlavicka:
            wr.writerow([SLOUPCE[s] for s in sloupce])
        for b in body:
            wr.writerow([fmt_val(b, s) for s in sloupce])
    return out.getvalue()


def uloz_soubor(path: str | Path, body: list[Bod], **kw) -> Path:
    from ..safeio import write_text_atomic
    p = Path(path)
    if p.suffix.lower() == ".csv" and "oddelovac" not in kw:
        kw = dict(kw, oddelovac=";", hlavicka=kw.get("hlavicka", True))
    write_text_atomic(p, zapis_text(body, **kw))
    return p


__all__ = ["Format", "SLOUPCE", "ODDELOVACE", "rozpoznej", "nacti_text", "nacti_soubor", "zapis_text",
           "uloz_soubor", "dekoduj", "replace"]
