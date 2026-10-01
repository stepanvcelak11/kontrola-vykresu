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


def download(dest, progress=None, url: str = DOWNLOAD_URL, timeout: float = 30.0):
    """Stáhne nové KontrolaVykresu.exe do ``dest``; ``progress(stazeno, celkem)``. Ověří, že jde o program."""
    from pathlib import Path
    dest = Path(dest)
    req = urllib.request.Request(url, headers={"User-Agent": "KontrolaVykresu"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:  # noqa: S310
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    with open(dest, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or dest.stat().st_size < 5_000_000 or (total and dest.stat().st_size != total):
        dest.unlink(missing_ok=True)
        raise OSError("Stažený soubor není celý program – zkuste to znovu.")
    return dest


def updater_script(pid: int, new_exe, target_exe) -> str:
    """Dávka pro Windows: počká, až se program zavře, nahradí .exe novým a spustí ho."""
    return (
        "@echo off\r\n"
        ":cekej\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        f'tasklist /fi "PID eq {pid}" | find "{pid}" >nul && goto cekej\r\n'
        f'move /y "{new_exe}" "{target_exe}" >nul\r\n'
        f'start "" "{target_exe}"\r\n'
        'del "%~f0"\r\n'
    )


def install_and_restart(new_exe) -> None:
    """Spustí dávku nahrazení (jen sestavené .exe na Windows); program se pak musí ukončit."""
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    target = Path(sys.executable)
    bat = Path(tempfile.gettempdir()) / "kontrola_vykresu_aktualizace.bat"
    bat.write_text(updater_script(os.getpid(), new_exe, target), encoding="cp1250")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True)  # noqa: S603,S607
