"""Kontrola z příkazové řádky (bez grafického rozhraní).

Příklady::

    python -m kontrola zkontroluj ukazky/ukazkovy_vykres.dxf
    python -m kontrola zkontroluj vykres.dxf --pravidla ukazky/konfigurace.yaml --csv chyby.csv
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .checks.base import REGISTRY
from .config import Config
from .io import load_drawing
from .rules import RuleSet
from .runner import run_checks


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="python -m kontrola zkontroluj",
                                 description="Kontrola topologie a atributů výkresu DXF.")
    ap.add_argument("prikaz", choices=["zkontroluj", "check"], help=argparse.SUPPRESS)
    ap.add_argument("vykres", help="soubor DXF (DGN jen s ODA File Converterem)")
    ap.add_argument("--pravidla", help="YAML s pravidly (může obsahovat i nastavení kontrol)")
    ap.add_argument("--nastaveni", help="YAML s nastavením kontrol")
    ap.add_argument("--tolerance", type=float, help="tolerance v metrech")
    ap.add_argument("--jen", nargs="*", help="spustit jen vybrané kontroly (id)")
    ap.add_argument("--csv", help="uložit seznam chyb do CSV")
    ap.add_argument("--xlsx", help="uložit seznam chyb do Excelu")
    ap.add_argument("--dxf", help="uložit DXF s hladinou KONTROLA_CHYBY")
    ap.add_argument("--pdf", help="uložit protokol PDF (bez obrázků – ty vytvoří grafická aplikace)")
    ap.add_argument("--seznam-kontrol", action="store_true", help="vypsat dostupné kontroly")
    a = ap.parse_args(argv)

    if a.seznam_kontrol:
        for cid, cls in REGISTRY.items():
            c = cls()
            print(f"{cid:24} {c.skupina:10} {c.nazev} – {c.popis}")
        return 0

    rules = RuleSet()
    config = Config()
    if a.pravidla:
        rules = RuleSet.load(a.pravidla)
        config = Config.load(a.pravidla)
    if a.nastaveni:
        config = Config.load(a.nastaveni)
    if a.tolerance is not None:
        config.tolerance = a.tolerance

    def prog(p, msg=""):
        print(f"\r{p:3d} % {msg[:60]:60}", end="", file=sys.stderr, flush=True)

    drawing = load_drawing(a.vykres, prog, config.oda_cesta or None)
    print(file=sys.stderr)
    for w in drawing.warnings[:10]:
        print("Upozornění:", w)
    res = run_checks(drawing, rules, config, prog, only=a.jen)
    print(file=sys.stderr)
    print(f"Výkres: {Path(a.vykres).name}, prvků: {len(drawing.features)}, pravidel: {len(rules.pravidla)}")
    for iss in res.issues:
        print(f"{iss.number:4d}  {iss.severity.value:9} {iss.check_name:28} {iss.message:50} "
              f"{iss.layer:16} {iss.x:14.3f} {iss.y:14.3f}")
    for n in res.notes:
        print("Poznámka:", n)
    counts = Counter(i.severity.value for i in res.issues)
    print(f"Celkem: {len(res.issues)} (chyby {counts.get('chyba', 0)}, varování {counts.get('varování', 0)}, "
          f"info {counts.get('info', 0)})")
    if a.csv:
        from .export.tables import export_csv
        export_csv(res.issues, a.csv)
    if a.xlsx:
        from .export.tables import export_xlsx
        export_xlsx(res.issues, a.xlsx, drawing_name=Path(a.vykres).name)
    if a.dxf:
        from .export.dxf_export import export_dxf
        export_dxf(drawing, res.issues, a.dxf)
    if a.pdf:
        from .export.pdf_report import export_pdf
        export_pdf(res.issues, a.pdf, drawing_name=Path(a.vykres).name, rules_count=len(rules.pravidla),
                   notes=res.notes, tolerance=config.tolerance)
    return 1 if counts.get("chyba") else 0


if __name__ == "__main__":
    raise SystemExit(main())
