"""Volitelný převod DGN (a DWG) na DXF pomocí ODA File Converteru.

ODA File Converter je bezplatný program od Open Design Alliance
(https://www.opendesign.com/guestfiles/oda_file_converter). Aplikace ho
hledá v obvyklých instalačních složkách nebo v cestě zadané v nastavení.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DGN_NAVOD = (
    "Soubor DGN nelze otevřít přímo.\n\n"
    "Možnost 1 – uložení z MicroStationu (doporučeno):\n"
    "  1. Otevřete výkres v MicroStationu.\n"
    "  2. Soubor → Uložit jako… (File → Save As…).\n"
    "  3. Jako typ souboru zvolte „AutoCAD Drawing Interchange (*.dxf)“.\n"
    "  4. V možnostech exportu ponechte jednotky v metrech a verzi DXF 2013 nebo novější.\n"
    "  5. Uložený DXF otevřete v této aplikaci.\n\n"
    "Možnost 2 – automatický převod:\n"
    "  Nainstalujte bezplatný ODA File Converter "
    "(https://www.opendesign.com/guestfiles/oda_file_converter) a v Nastavení "
    "kontrol vyplňte cestu k ODAFileConverter.exe, pokud se nenajde sám.\n"
    "  Pozor: ne každá verze ODA File Converteru umí číst DGN – pokud převod "
    "selže, použijte možnost 1."
)


class ConversionError(Exception):
    """Převod na DXF se nezdařil. Text výjimky obsahuje český návod."""


def find_oda_converter(configured: str | None = None) -> str | None:
    """Najde spustitelný soubor ODA File Converteru, nebo vrátí None."""
    if configured and Path(configured).is_file():
        return configured
    candidates: list[str] = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        candidates += sorted(glob.glob(os.path.join(base, "ODA", "ODAFileConverter*", "ODAFileConverter.exe")),
                             reverse=True)
    for name in ("ODAFileConverter", "ODAFileConverter.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates += ["/usr/bin/ODAFileConverter", "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def convert_to_dxf(source: str | Path, oda_path: str | None = None, out_dir: str | Path | None = None) -> Path:
    """Převede DGN/DWG na DXF. Vrací cestu k novému DXF, jinak ConversionError."""
    source = Path(source)
    exe = find_oda_converter(oda_path)
    if exe is None:
        raise ConversionError("ODA File Converter nebyl nalezen.\n\n" + DGN_NAVOD)
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="kontrola_dxf_"))
    out.mkdir(parents=True, exist_ok=True)
    work_in = Path(tempfile.mkdtemp(prefix="kontrola_in_"))
    shutil.copy2(source, work_in / source.name)
    pattern = "*" + source.suffix.upper()
    cmd = [exe, str(work_in), str(out), "ACAD2018", "DXF", "0", "1", pattern]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(cmd, check=False, timeout=600, capture_output=True, creationflags=flags)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConversionError(f"Spuštění ODA File Converteru selhalo: {exc}\n\n" + DGN_NAVOD) from exc
    finally:
        shutil.rmtree(work_in, ignore_errors=True)
    result = out / (source.stem + ".dxf")
    if not result.is_file():
        matches = list(out.glob("*.dxf"))
        if not matches:
            raise ConversionError("ODA File Converter tento soubor nepřevedl "
                                  "(tato verze pravděpodobně nepodporuje DGN).\n\n" + DGN_NAVOD)
        result = matches[0]
    return result
