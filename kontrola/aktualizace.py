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
# instalátor (doporučený) a přenosný jeden soubor (staré verze se aktualizují na něj)
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/KontrolaVykresu-instalace.exe"
PRENOSNY_URL = f"https://github.com/{REPO}/releases/latest/download/KontrolaVykresu.exe"
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


def je_nainstalovano(exe=None) -> bool:
    """Program běží z instalace (vedle .exe je odinstalátor Inno Setup), ne jako přenosný jeden soubor."""
    import sys
    from pathlib import Path
    exe = Path(exe or sys.executable)
    return any(exe.parent.glob("unins*.exe"))


def prikaz_instalace(instalator, tise: bool) -> list[str]:
    """Spuštění staženého instalátoru. Při aktualizaci nainstalovaného programu tiše (jen průběh),
    přenosnou verzi převede na instalovanou s běžným průvodcem."""
    cmd = [str(instalator)]
    if tise:
        cmd += ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    return cmd


def install_and_restart(instalator) -> None:
    """Spustí stažený instalátor jako běžný viditelný program (žádná skrytá dávka, která by přepisovala
    běžící .exe – to antiviry právem považují za podezřelé). Program se pak musí ukončit; instalátor
    ho po dokončení spustí znovu."""
    import subprocess
    subprocess.Popen(prikaz_instalace(instalator, je_nainstalovano()), close_fds=True)  # noqa: S603


# ------------------------------------------------------------------ spuštění ze zdrojových kódů (bez .exe)
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
COMMITS_URL = f"https://api.github.com/repos/{REPO}/commits/main"
STAMP = "verze_zdroju.txt"  # SHA nainstalované verze (zapisuje aktualizace)
_NEKOPIROVAT = {".venv", ".git", "__pycache__", "build", "dist"}


def app_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]


def je_zdrojova_instalace(root=None) -> bool:
    """Spuštěno ze staženého ZIPu (spustit.py, bez .exe a bez gitu) – jde aktualizovat stažením ZIPu."""
    root = root or app_root()
    return BUILD is None and (root / "spustit.py").is_file() and not (root / ".git").exists()


def nainstalovana_sha(root=None) -> str:
    root = root or app_root()
    try:
        return (root / STAMP).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def fetch_latest_sha(timeout: float = 6.0) -> str:
    req = urllib.request.Request(COMMITS_URL, headers={"Accept": "application/vnd.github+json",
                                                       "User-Agent": "KontrolaVykresu"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – pevná https adresa
        return str(json.loads(r.read().decode("utf-8")).get("sha") or "")


def rozbal_aktualizaci(zip_path, root, sha: str = "") -> int:
    """Rozbalí ZIP z GitHubu přes složku aplikace (bez .venv a uživatelských souborů). Python soubory
    aplikace, které v nové verzi nejsou, smaže. Vrací počet zapsaných souborů."""
    import zipfile
    from pathlib import Path, PurePosixPath
    root = Path(root)
    nove = set()
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        jmena = [i for i in z.infolist() if not i.is_dir()]
        if not jmena or not any(PurePosixPath(i.filename).parts[1:] == ("spustit.py",) for i in jmena):
            raise OSError("Stažený soubor není aplikace Kontrola výkresu.")
        for i in jmena:
            casti = PurePosixPath(i.filename).parts[1:]  # bez horní složky „kontrola-vykresu-main“
            if not casti or casti[0] in _NEKOPIROVAT or ".." in casti:
                continue
            cil = root.joinpath(*casti)
            cil.parent.mkdir(parents=True, exist_ok=True)
            tmp = cil.with_name(cil.name + ".novy")
            tmp.write_bytes(z.read(i))
            tmp.replace(cil)
            nove.add(cil.resolve())
            n += 1
    for f in (root / "kontrola").rglob("*.py"):  # odstraněné moduly staré verze
        if f.resolve() not in nove and "__pycache__" not in f.parts:
            try:
                f.unlink()
            except OSError:
                pass
    if sha:
        (root / STAMP).write_text(sha + "\n", encoding="utf-8")
    return n


def aktualizuj_zdroje(root=None, sha: str = "", progress=None, url: str = ZIP_URL, timeout: float = 60.0) -> str:
    """Stáhne nejnovější verzi z GitHubu, přepíše soubory aplikace a doinstaluje knihovny.
    Vrací výpis pip (pro případ chyby)."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    root = Path(root or app_root())
    dest = Path(tempfile.gettempdir()) / "kontrola_vykresu_main.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "KontrolaVykresu"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:  # noqa: S310
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            if progress:
                progress("stahuji")
    if progress:
        progress("rozbaluji")
    rozbal_aktualizaci(dest, root, sha)
    dest.unlink(missing_ok=True)
    if progress:
        progress("knihovny")
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe":
        py = py.with_name("python.exe")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",  # noqa: S603
                        str(root / "requirements.txt")], capture_output=True, text=True, creationflags=flags,
                       cwd=str(root), timeout=1800)
    return (r.stdout or "") + (r.stderr or "")


def restartuj_zdroje(root=None) -> None:
    import subprocess
    import sys
    from pathlib import Path
    root = Path(root or app_root())
    py = Path(sys.executable)
    if sys.platform == "win32" and py.with_name("pythonw.exe").exists():
        py = py.with_name("pythonw.exe")
    subprocess.Popen([str(py), str(root / "spustit.py")], cwd=str(root), close_fds=True)  # noqa: S603
