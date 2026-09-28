"""Spuštění aplikace Kontrola výkresu (také vstupní bod pro PyInstaller).

    python spustit.py                         – grafická aplikace
    python spustit.py vykres.dxf              – otevře výkres
    python spustit.py zkontroluj vykres.dxf   – kontrola z příkazové řádky
"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("zkontroluj", "check"):
        from kontrola.cli import main as cli_main
        raise SystemExit(cli_main(sys.argv[1:]))
    from kontrola.app import main
    raise SystemExit(main())
