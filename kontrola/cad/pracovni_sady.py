"""Pracovní sady jako v MicroStationu CONNECT: „Bez pracovní sady“, MultiScale, Pasport, TM…

Aplikace si je najde ve složce se školním nastavením MicroStationu (záloha „Skolni_nastaveni_CONNECT“ nebo
přímo …/Configuration/WorkSpaces) a ve složce s knihovnami od učitele (GEO-V8.CEL, GEO.RSC, seed SJTSK-V8.DGN).
Aktivní sada určuje seed nového výkresu (hladiny, nastavení), buňky (.cel) a styly čar (.rsc) – stejně jako
po výběru pracovní sady na úvodní obrazovce MicroStationu. Soubory zůstávají tam, kde jsou (nic se nekopíruje).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

KLIC_SLOZKY = "cad/sady_slozky"
KLIC_AKTIVNI = "cad/aktivni_sada"
BEZ_SADY = "Bez pracovní sady"


@dataclass
class Sada:
    nazev: str
    prostredi: str  # pracovní prostředí (WorkSpace), u „Bez pracovní sady“ složka
    slozka: Path
    seed: Path | None = None
    bunky: list[Path] = field(default_factory=list)
    styly: list[Path] = field(default_factory=list)
    dgnlib: list[Path] = field(default_factory=list)
    seedy: list[Path] = field(default_factory=list)  # všechny seedy sady – volí se podle druhu výkresu
    pasy: list[Path] = field(default_factory=list)  # Dgnlib/GUI: vlastní pásy karet (styl kreslení, např. ÚM)

    @property
    def klic(self) -> str:
        return f"{self.prostredi}/{self.nazev}"

    def popis(self) -> str:
        return (f"seed: {self.seed.name if self.seed else '–'}; buňky: "
                + (", ".join(p.name for p in self.bunky) or "–") + "; styly čar: "
                + (", ".join(p.name for p in self.styly) or "–") + "; knihovny hladin: "
                + (", ".join(p.name for p in self.dgnlib) or "–"))


def _pripona(p: Path, *pr: str) -> bool:
    return p.is_file() and p.suffix.lower() in pr


def _je_knihovna_stylu(p: Path) -> bool:
    try:
        h = p.read_bytes()[:0x40].split(b"\x1a")[0].decode("cp1250", "replace").strip()
    except OSError:
        return False
    return h in ("Line Style Library", "Knihovna druhů čar")


def _seed(kandidati: list[Path], nazev: str) -> Path | None:
    """2D seed: přednostně se jménem sady / S-JTSK V8, ne 3D, list (sheet) ani výkres (drawing)."""
    def skore(p: Path) -> tuple:
        n = p.stem.lower()
        return ("3d" in n, "sheet" in n or "drawing" in n, nazev.lower() not in n,
                not ("sjtsk" in n and "v8" in n), "v7" in n, len(n))
    k = sorted((p for p in kandidati if _pripona(p, ".dgn")), key=skore)
    return k[0] if k else None


def _sada_z_standards(std: Path) -> Sada:
    nazev = std.parent.name
    ws = std.parent.parent.parent.name if std.parent.parent.name.lower() == "worksets" else ""
    soubory = [p for p in std.rglob("*") if p.is_file()]
    seeds = [p for p in soubory if p.parent.name.lower() == "seed"] or [p for p in soubory if _pripona(p, ".dgn")]
    return Sada(nazev, ws or nazev, std.parent, _seed(seeds, nazev),
                sorted(p for p in soubory if _pripona(p, ".cel")),
                sorted(p for p in soubory if _pripona(p, ".rsc") and _je_knihovna_stylu(p)),
                sorted(p for p in soubory if _pripona(p, ".dgnlib") and p.parent.name.lower() != "gui"),
                sorted(p for p in seeds if _pripona(p, ".dgn")),
                sorted(p for p in soubory if _pripona(p, ".dgnlib") and p.parent.name.lower() == "gui"))


def najdi(slozka: str | Path) -> list[Sada]:
    """Pracovní sady ve složce: …/WorkSets/<sada>/Standards, a „Bez pracovní sady“ ze složky, kde jsou
    knihovny buněk a stylů volně (knihovny od učitele)."""
    koren = Path(slozka)
    if not koren.is_dir():
        return []
    out: list[Sada] = []
    for std in sorted(koren.rglob("Standards")):
        if std.is_dir() and std.parent.parent.name.lower() == "worksets":
            out.append(_sada_z_standards(std))
    # projekty MicroStationu V8i: složka s podsložkami cell / symb / seed (gi_MGEO, TM25, MultiScale…)
    projekty = sorted(d for d in koren.rglob("*") if d.is_dir() and "worksets" not in (x.lower() for x in d.parts)
                      and len({c.name.lower() for c in d.iterdir() if c.is_dir()} & {"cell", "symb", "seed"}) >= 2)
    for d in projekty:
        soubory = [p for p in d.rglob("*") if p.is_file()]
        seeds = [p for p in soubory if p.parent.name.lower() == "seed" and _pripona(p, ".dgn")]
        out.append(Sada(d.name, "V8i", d, _seed(seeds, d.name),
                        sorted(p for p in soubory if _pripona(p, ".cel")),
                        sorted(p for p in soubory if _pripona(p, ".rsc") and _je_knihovna_stylu(p)),
                        sorted(p for p in soubory if _pripona(p, ".dgnlib")), sorted(seeds)))
    volne: dict[Path, list[Path]] = {}
    for p in koren.rglob("*"):
        if (_pripona(p, ".cel", ".rsc", ".dgn") and "worksets" not in (x.lower() for x in p.parts)
                and not any(d in p.parents for d in projekty)):
            volne.setdefault(p.parent, []).append(p)
    for d, soubory in sorted(volne.items()):
        cel = sorted(p for p in soubory if _pripona(p, ".cel"))
        rsc = sorted(p for p in soubory if _pripona(p, ".rsc") and _je_knihovna_stylu(p))
        if cel or rsc:
            out.append(Sada(BEZ_SADY, d.name, d, _seed(soubory, "sjtsk"), cel, rsc, [],
                            sorted(p for p in soubory if _pripona(p, ".dgn"))))
    return out


# ------------------------------------------------------------------ uložené nastavení
def _qs():
    from PySide6.QtCore import QSettings
    return QSettings()


def slozky() -> list[str]:
    v = _qs().value(KLIC_SLOZKY, []) or []
    return [v] if isinstance(v, str) else [str(x) for x in v]


def pridej_slozku(slozka: str | Path) -> list[Sada]:
    s = [x for x in slozky() if x != str(slozka)] + [str(slozka)]
    _qs().setValue(KLIC_SLOZKY, s)
    return najdi(slozka)


def odeber_slozku(slozka: str | Path) -> None:
    _qs().setValue(KLIC_SLOZKY, [x for x in slozky() if x != str(slozka)])


def vestavena_slozka() -> Path:
    """Školní pracovní sady MicroStationu CONNECT (MultiScale, Pasport, TM) jsou součástí aplikace."""
    from ..resources import resource_path
    return resource_path("microstation", "skola")


def vsechny() -> list[Sada]:
    out, videne = [], set()
    for s in slozky() + [str(vestavena_slozka())]:  # vlastní nastavení má přednost
        for sada in najdi(s):
            if sada.klic not in videne:
                videne.add(sada.klic)
                out.append(sada)
    return out


def aktivni() -> Sada | None:
    k = str(_qs().value(KLIC_AKTIVNI, "") or "")
    return next((s for s in vsechny() if s.klic == k), None) if k else None


def posledni_seed(sada: Sada | None) -> Path | None:
    """Seed naposledy zvolený v této sadě (jinak výchozí seed sady)."""
    if sada is None:
        return None
    v = str(_qs().value(f"cad/seed/{sada.klic}", "") or "")
    return Path(v) if v and Path(v).is_file() else sada.seed


def zapamatuj_seed(sada: Sada | None, seed: Path | None) -> None:
    if sada is not None:
        _qs().setValue(f"cad/seed/{sada.klic}", str(seed or ""))


_PASY_CACHE: dict = {}


def styly_kresleni(sada: Sada | None) -> list:
    """Pásy karet (styly kreslení) aktivní sady – jen ty, které mají tlačítka s key-iny."""
    from .ms_pas import nacti_pas
    out = []
    pasy = list(sada.pasy if sada is not None else [])
    # bez pracovní sady jen standardní nástroje; každá sada (MultiScale, Pasport, TM) má své vlastní pásy –
    # styly kreslení se mezi sadami nemíchají
    for p in pasy:
        try:
            k = (str(p), p.stat().st_mtime)
        except OSError:
            continue
        if k not in _PASY_CACHE:
            try:
                _PASY_CACHE[k] = nacti_pas(p)
            except Exception:  # noqa: BLE001 – poškozený .dgnlib nesmí shodit CAD
                _PASY_CACHE[k] = None
        pas = _PASY_CACHE[k]
        if pas is not None and not any(o.pocet == pas.pocet and [t for t, _ in o.karty] == [t for t, _ in pas.karty]
                                       for o in out):  # stejný pás ve dvou knihovnách (Pasport_konfigurace_dwg)
            out.append(pas)
    return out


_STYLY_TEXTU_CACHE: dict = {}


def textove_styly(sada: Sada | None) -> dict:
    """Textové styly pracovní sady (název malými písmeny → ``ms_pas.TextovyStyl``): knihovny hladin a stylů
    (Dgnlib/DrawComp) mají přednost před pásy karet a seedem – stejně jako je MicroStation načítá."""
    from .ms_pas import textove_styly as nacti
    out: dict = {}
    if sada is None:
        return out
    for p in [*sada.dgnlib, *sada.pasy, *([sada.seed] if sada.seed else [])]:
        try:
            k = (str(p), p.stat().st_mtime)
        except OSError:
            continue
        if k not in _STYLY_TEXTU_CACHE:
            try:
                _STYLY_TEXTU_CACHE[k] = nacti(p)
            except Exception:  # noqa: BLE001 – poškozená knihovna nesmí shodit CAD
                _STYLY_TEXTU_CACHE[k] = {}
        for jm, st in _STYLY_TEXTU_CACHE[k].items():
            out.setdefault(jm, st)
    return out


def pravidla_sady(sada: Sada | None):
    """Zadání (pravidla kontroly) z knihoven pracovní sady – nástroje pásů karet s hladinami sady. None, když
    sada nemá vlastní pás s nástroji (pak není podle čeho kontrolovat)."""
    from .ms_pas import pravidla_pasu
    if sada is None:
        return None
    pasy = styly_kresleni(sada)
    if not pasy:
        return None
    rs = pravidla_pasu(pasy, textove_styly(sada))
    return rs if rs.pravidla else None


def nastav_aktivni(sada: Sada | None) -> None:
    _qs().setValue(KLIC_AKTIVNI, sada.klic if sada is not None else "")
