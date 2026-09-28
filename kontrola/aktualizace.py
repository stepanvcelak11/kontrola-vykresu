"""Kontrola, zda je na GitHubu novější verze programu.

Zjišťuje se jen číslo posledního sestavení z veřejné stránky vydání (GitHub API). Nic se neodesílá:
žádné výkresy, cesty ani údaje o počítači – jde o obyčejné stažení veřejné informace.
"""

from __future__ import annotations

import json
import re
import urllib.request

REPO = "stepanvcelak11/kontrola-vykresu"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/KontrolaVykresu.exe"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"

try:  # soubor vytváří sestavení .exe na GitHubu (Actions); při spuštění ze zdrojů chybí
    from ._build import BUILD, COMMIT  # type: ignore
except ImportError:  # pragma: no cover - závisí na sestavení
    BUILD, COMMIT = None, ""


def parse_build(text: str) -> int | None:
    m = re.search(r"Sestavení č\.\s*(\d+)", text or "")
    return int(m.group(1)) if m else None


def fetch_latest(timeout: float = 6.0) -> int | None:
    """Číslo sestavení poslední zveřejněné verze (None = nepodařilo se zjistit)."""
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "KontrolaVykresu"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – pevná https adresa
        data = json.loads(r.read().decode("utf-8"))
    return parse_build(data.get("body", "")) or parse_build(data.get("name", ""))


def is_newer(latest: int | None, current: int | None = None) -> bool:
    current = BUILD if current is None else current
    return latest is not None and current is not None and latest > current


def version_text() -> str:
    from . import __version__
    if BUILD is None:
        return f"{__version__} (spuštěno ze zdrojových kódů)"
    return f"{__version__}, sestavení č. {BUILD}" + (f" ({COMMIT[:7]})" if COMMIT else "")
