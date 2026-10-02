"""Spuštění aplikace Kontrola výkresu (také vstupní bod pro PyInstaller).

    python spustit.py                         – grafická aplikace
    python spustit.py vykres.dxf              – otevře výkres
    python spustit.py zkontroluj vykres.dxf   – kontrola z příkazové řádky
"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("zkontroluj", "check"):
        from kontrola.app import _splash
        _splash(close=True)  # bez okna – úvodní okénko hned pryč
        from kontrola.cli import main as cli_main
        raise SystemExit(cli_main(sys.argv[1:]))
    try:
        from kontrola.app import main
        kod = main()
    except Exception:  # noqa: BLE001 – při spuštění bez konzole (pythonw) chybu ukázat a uložit
        import traceback
        from pathlib import Path
        text = traceback.format_exc()
        try:
            Path(__file__).with_name("chyba_spusteni.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "Aplikace se nespustila. Chyba je uložená v souboru "
                                             "chyba_spusteni.txt vedle spustit.py – pošlete ji autorovi.\n\n"
                                             + text[-1500:], "Kontrola výkresu", 0x10)
        raise
    raise SystemExit(kod)
