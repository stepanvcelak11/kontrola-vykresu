"""Kontrola před spuštěním ze zdrojových kódů (spustit_python.bat): verze Pythonu a knihovny.

Vypíše srozumitelně, co chybí nebo co Windows zablokovalo (Inteligentní řízení aplikací umí zablokovat
i knihovny Pythonu – soubory .pyd/.dll), a vrátí kód 1, aby .bat okno nechal otevřené.
"""

from __future__ import annotations

import importlib
import sys
import traceback

KNIHOVNY = [("PySide6.QtWidgets", "PySide6"), ("numpy", "numpy"), ("shapely", "shapely"), ("ezdxf", "ezdxf"),
            ("openpyxl", "openpyxl"), ("yaml", "PyYAML"), ("olefile", "olefile"), ("reportlab", "reportlab"),
            ("pdfplumber", "pdfplumber"), ("xlrd", "xlrd"), ("qrcode", "qrcode")]


def je_blokace(text: str) -> bool:
    t = text.lower()
    return ("application control" in t or "4551" in t or "zásady řízení aplikací" in t
            or "rizeni aplikaci" in t or "blocked this file" in t or "zablokoval" in t)


def zkontroluj() -> list[str]:
    """Seznam problémů (prázdný = vše v pořádku)."""
    chyby = []
    if sys.version_info < (3, 10):
        chyby.append(f"Python {sys.version.split()[0]} je moc starý – nainstalujte Python 3.12 z Microsoft Store.")
        return chyby
    for modul, balik in KNIHOVNY:
        try:
            importlib.import_module(modul)
        except Exception as e:  # noqa: BLE001 – i chyba načtení DLL
            text = f"{type(e).__name__}: {e}"
            if je_blokace(text):
                chyby.append(f"BLOKACE:{balik}: {text}")
            elif isinstance(e, ModuleNotFoundError):
                chyby.append(f"Chybí knihovna {balik} (instalace knihoven se nepovedla – viz pip_log.txt).")
            else:
                chyby.append(f"Knihovna {balik} nejde načíst: {text}")
    return chyby


def _bezpecny_vystup() -> None:
    """Konzole Windows může mít kódování bez češtiny (cp1252) – znaky, které nejdou zapsat, se nahradí."""
    for proud in (sys.stdout, sys.stderr):
        try:
            proud.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _bezpecny_vystup()
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    try:
        chyby = zkontroluj()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1
    if not chyby:
        print("Knihovny v pořádku, spouštím aplikaci…")
        return 0
    print()
    print("SPUŠTĚNÍ SE NEPOVEDLO:")
    for c in chyby:
        print("  - " + c.replace("BLOKACE:", "zablokováno – ", 1))
    if any(c.startswith("BLOKACE:") for c in chyby):
        print()
        print("Windows (Inteligentní řízení aplikací) zablokoval knihovny Pythonu. Tuto ochranu nejde vypnout")
        print("jen pro jednu aplikaci. Možnosti:")
        print("  1) Zabezpečení Windows -> Řízení aplikací a prohlížeče -> Inteligentní řízení aplikací -> Vypnuto.")
        print("     (Pozor: zpět zapnout jde jen přeinstalací Windows. Antivirus i SmartScreen dál chrání.)")
        print("  2) Pošlete mi tento výpis – zkusím jiné řešení.")
    elif sys.version_info >= (3, 14):
        print()
        print("Máte velmi novou verzi Pythonu, pro kterou ještě nemusí být všechny knihovny.")
        print("Nainstalujte Python 3.12 z Microsoft Store, smažte složku .venv a spusťte znovu.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
