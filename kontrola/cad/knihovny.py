"""Knihovny od učitele (jako „standardy“ pracovního prostředí MicroStationu): buňky (.cel, .dxf), styly čar
(.rsc) a typy čar (.lin). Přidají se jednou, zkopírují do složky aplikace a jsou pak v každém výkresu –
nové buňky nebo styly, které učitel zadá později, stačí přidat dalším souborem."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

KLIC = "cad/knihovny"
PRIPONY = {".cel": "buňky", ".dxf": "buňky a typy čar", ".rsc": "styly čar", ".lin": "typy čar"}


@dataclass
class Knihovna:
    cesta: Path
    druh: str  # buňky / styly čar / …
    pocet: int  # buněk nebo stylů (−1 = nejde načíst)
    chyba: str = ""


def slozka() -> Path:
    from PySide6.QtCore import QStandardPaths
    d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or str(Path.home() / ".kontrola_vykresu")
    p = Path(d) / "knihovny"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ulozene() -> list[str]:
    from PySide6.QtCore import QSettings
    v = QSettings().value(KLIC, []) or []
    return [v] if isinstance(v, str) else [str(x) for x in v]


def _uloz(cesty: list[str]) -> None:
    from PySide6.QtCore import QSettings
    QSettings().setValue(KLIC, cesty)


def soubory(pripony: tuple[str, ...] | None = None) -> list[Path]:
    """Připojené knihovny, které existují (volitelně jen s danými příponami)."""
    out = [Path(c) for c in _ulozene()]
    return [p for p in out if p.is_file() and (pripony is None or p.suffix.lower() in pripony)]


def popis(cesta: Path) -> Knihovna:
    """Co knihovna obsahuje (počet buněk / stylů), nebo proč ji nejde načíst."""
    s = cesta.suffix.lower()
    druh = PRIPONY.get(s, "?")
    try:
        if s == ".cel":
            from ..io.cel import nacti_cel
            return Knihovna(cesta, druh, len(nacti_cel(cesta)))
        if s == ".rsc":
            from ..io.rsc import nacti_rsc
            return Knihovna(cesta, druh, len(nacti_rsc(cesta)))
        if s == ".dxf":
            import ezdxf
            doc = ezdxf.readfile(str(cesta))
            return Knihovna(cesta, druh, sum(1 for b in doc.blocks if not b.name.startswith("*")))
        if s == ".lin":
            n = sum(1 for r in cesta.read_text(encoding="utf-8", errors="replace").splitlines() if r.startswith("*"))
            return Knihovna(cesta, druh, n)
    except Exception as e:  # noqa: BLE001 – poškozený nebo cizí soubor: ukázat důvod, nespadnout
        return Knihovna(cesta, druh, -1, str(e))
    return Knihovna(cesta, druh, -1, "nepodporovaný typ souboru")


def pridej(cesta: str | Path) -> Knihovna:
    """Zkontroluje knihovnu, zkopíruje ji do složky aplikace a připojí. Stejnojmenná se nahradí (novější verze
    od učitele). Nejde-li načíst, nepřipojí se a vrátí se důvod."""
    src = Path(cesta)
    if src.suffix.lower() not in PRIPONY:
        return Knihovna(src, "?", -1, f"{src.name}: podporované jsou {', '.join(PRIPONY)}")
    info = popis(src)
    if info.pocet < 0:
        return info
    if info.pocet == 0:
        return Knihovna(src, info.druh, -1, f"{src.name}: knihovna je prázdná")
    cil = slozka() / src.name
    if src.resolve() != cil.resolve():
        shutil.copy2(src, cil)
    cesty = [c for c in _ulozene() if Path(c).name.lower() != cil.name.lower()] + [str(cil)]
    _uloz(cesty)
    return Knihovna(cil, info.druh, info.pocet)


def odeber(cesta: str | Path) -> None:
    p = Path(cesta)
    _uloz([c for c in _ulozene() if Path(c) != p])
    try:
        if p.parent.resolve() == slozka().resolve():
            p.unlink()
    except OSError:
        pass


def do_vykresu(doc) -> list[str]:
    """Buňky ze všech připojených knihoven do výkresu (definice bloků; existující se nepřepisují)."""
    from .zadani import prevezmi_bloky, prevezmi_styly
    out: list[str] = []
    for p in soubory((".cel", ".dxf")):
        try:
            out += prevezmi_bloky(doc, [str(p)])
        except Exception:  # noqa: BLE001
            continue
    lin = [str(p) for p in soubory((".lin", ".dxf"))]
    if lin:
        try:
            prevezmi_styly(doc, lin)
        except Exception:  # noqa: BLE001
            pass
    return out
