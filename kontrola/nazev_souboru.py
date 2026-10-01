"""Název odevzdávaného souboru podle zadání MicroStation: Prijmeni_cz_ax_tx.dgn.

cz = číslo zadání, a = pořadí opravy po atributové kontrole, t = pořadí opravy po topologické kontrole
(např. Vcelak_13_a0_t0.dgn – první odevzdání, Vcelak_13_a1_t0.dgn – po první opravě atributů).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

VZOR = re.compile(r"^(?P<prijmeni>[A-Za-z]+)_(?P<cz>\d+)_a(?P<a>\d+)_t(?P<t>\d+)$", re.IGNORECASE)
# jen soubory, které se o vzor zjevně pokoušejí (Příjmení_číslo…); jiné zadání (např. Husovice_…) se neřeší
POKUS = re.compile(r"^[^\W\d_]+_\d+(?:_|$)", re.UNICODE)


@dataclass
class Hodnoceni:
    ok: bool
    text: str
    dalsi_a: str = ""  # název po další opravě atributů
    dalsi_t: str = ""  # název po další opravě topologie


def _bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def zhodnot(path: str | Path) -> Hodnoceni | None:
    """Vrátí hodnocení názvu, nebo None, když soubor vzor zadání vůbec nepoužívá."""
    p = Path(path)
    stem = p.stem
    if not POKUS.match(stem):
        return None
    m = VZOR.match(stem)
    if m is None:
        cist = _bez_diakritiky(stem)
        rada = ""
        if cist != stem and VZOR.match(cist):
            rada = f" – bez diakritiky: {cist}.dgn"
        else:
            parts = cist.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                rada = f" – např. {parts[0]}_{parts[1]}_a0_t0.dgn"
        return Hodnoceni(False, f"Název „{p.name}“ neodpovídá vzoru ze zadání Prijmeni_cz_ax_tx.dgn{rada}")
    base = f"{m['prijmeni']}_{m['cz']}"
    a, t = int(m["a"]), int(m["t"])
    dalsi_a = f"{base}_a{a + 1}_t{t}.dgn"
    dalsi_t = f"{base}_a{a}_t{t + 1}.dgn"
    text = (f"Název „{p.stem}“ odpovídá vzoru Prijmeni_cz_ax_tx (zadání {m['cz']}, oprava atributů {a}, "
            f"topologie {t}). Po další opravě: {dalsi_a} (atributy) nebo {dalsi_t} (topologie).")
    return Hodnoceni(True, text, dalsi_a, dalsi_t)
