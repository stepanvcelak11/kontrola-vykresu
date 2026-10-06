"""clicked/triggered/toggled posílají do slotu bool (checked) – metoda s volitelným prvním parametrem
by ho dostala místo výchozí hodnoty (např. tolerance duplicit 0 místo 1 cm, hodnoty = False)."""

import ast
import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "kontrola" / "ui"


def test_signal_s_checked_neprepise_vychozi_parametr():
    spatne = []
    for p in sorted(UI.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        s_vychozim = {
            n.name for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and len(n.args.args) > 1 and n.args.args[0].arg == "self"
            and len(n.args.defaults) >= len(n.args.args) - 1}
        for m in re.finditer(r"\.(clicked|triggered|toggled)\.connect\(self\.(\w+)\)", src):
            if m.group(2) in s_vychozim:
                spatne.append(f"{p.name}:{src[:m.start()].count(chr(10)) + 1} {m.group(2)}")
    assert not spatne, "napojte přes lambda: " + ", ".join(spatne)
