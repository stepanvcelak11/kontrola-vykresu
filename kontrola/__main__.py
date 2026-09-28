"""``python -m kontrola`` spustí aplikaci, ``python -m kontrola zkontroluj …`` kontrolu z příkazové řádky."""

import sys

if len(sys.argv) > 1 and sys.argv[1] in ("zkontroluj", "check", "-h", "--help"):
    from .cli import main as cli_main
    raise SystemExit(cli_main(sys.argv[1:]))

from .app import main

raise SystemExit(main())
