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
    "Soubor DGN nelze otevřít přímo – uložte ho z MicroStationu jako DXF.\n\n"
    "Jeden výkres:\n"
    "  1. Otevřete výkres v MicroStationu.\n"
    "  2. Soubor → Uložit jako… (File → Save As…).\n"
    "  3. Typ souboru: „AutoCAD Drawing Interchange (*.dxf)“.\n"
    "  4. Tlačítko Možnosti (Options): jednotky „Master Units“ (metry), verze DXF 2013 nebo novější.\n"
    "  5. Uložený DXF přetáhněte do této aplikace.\n\n"
    "Všechny výkresy najednou (dávkový převod):\n"
    "  1. V MicroStationu: Utilities → Batch Converter (Nástroje → Dávkový převod).\n"
    "  2. Přetáhněte do seznamu všechny soubory .dgn (nebo Add Files / Add Folder).\n"
    "  3. Výstupní formát (Output Format): DXF, zvolte výstupní složku.\n"
    "  4. Nastavení DXF (Options) jako výše, případně je uložte pro příště.\n"
    "  5. Process → vzniknou soubory .dxf se stejnými názvy.\n\n"
    "Tip: DXF ukládejte vedle DGN. Po opravě v MicroStationu stačí DXF uložit znovu a v aplikaci "
    "stisknout „Zkontrolovat znovu“.\n\n"
    "Automatický převod: pokud máte nainstalovaný program, který umí DGN převést na DXF příkazem "
    "(např. ODA File Converter ve verzi s podporou DGN), nastavte cestu v Nastavení kontrol."
)


JINE_PROGRAMY_NAVOD = (
    "Aplikace kontroluje DXF – ten umí uložit většina geodetických programů.\n\n"
    "KOKEŠ (Gepro):\n"
    "  • Výkres: v nabídce Soubor najděte export (Export / Uložit jako) a zvolte formát DXF. "
    "Vrstvy a barvy Kokeše se přenesou do vrstev DXF.\n"
    "  • Data katastru (VFK): soubor .vfk můžete otevřít přímo – aplikace z něj vykreslí body, hranice "
    "parcel, budovy a čísla parcel (hodí se jako podklad nebo vzor k porovnání).\n"
    "  • Seznam souřadnic: exportujte ho jako textový soubor (řádky „číslo Y X Z“) – binární seznam "
    "(.ss) aplikace neotevře.\n\n"
    "ATLAS DMT:\n"
    "  • Kresbu / model exportujte do DXF (nabídka exportu, formát DXF) a DXF přetáhněte do aplikace.\n"
    "  • Body exportujte jako textový seznam souřadnic.\n\n"
    "AutoCAD / GstarCAD / BricsCAD: uložte jako DXF (DWG jen s nainstalovaným ODA File Converterem).\n\n"
    "Pozor: pravidla (vrstvy, barvy, styly) v aplikaci musí odpovídat programu, ve kterém kreslíte – "
    "u Kokeše nahrajte do Zadání jeho tabulku kódů / Směrnici od učitele."
)


def dgn_version(path: str | Path) -> str | None:
    """Pozná verzi souboru DGN podle hlavičky: „V8“ (MicroStation V8/V8i/CONNECT) nebo „V7“."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # OLE – DGN V8
        return "V8"
    if len(head) >= 4 and head[2:4] == b"\xfe\x02" and head[0] & 0x3F in (8, 9):  # typ 9 = hlavička V7
        return "V7"
    return None


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
        ver = dgn_version(source) if source.suffix.lower() == ".dgn" else None
        kind = {"V8": "MicroStation V8 / V8i / CONNECT", "V7": "MicroStation V7 (starší formát)"}.get(ver, "")
        head = f"Soubor {source.name}" + (f" je ve formátu {kind}." if kind else ".")
        raise ConversionError(head + "\n\n" + DGN_NAVOD)
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
