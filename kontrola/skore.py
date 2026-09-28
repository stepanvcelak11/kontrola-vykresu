"""Skóre připravenosti výkresu k odevzdání (0–100) – orientační, ne známka učitele.

Srážky: chyby topologie (to učitel hlídá programem MGEO) váží víc než chyby atributů (GISoft),
varování málo, informace vůbec. Opravené a ignorované nálezy se nepočítají.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .checks.base import REGISTRY, Issue, Severity


@dataclass
class Skore:
    hodnota: int
    popis: str
    barva: str
    rozpad: list[tuple[str, int]] = field(default_factory=list)  # (co, srážka)


def compute_score(issues: list[Issue], has_rules: bool = True) -> Skore:
    open_ = [i for i in issues if i.state == "nová"]
    topo = attr = var = 0
    for i in open_:
        grp = getattr(REGISTRY.get(i.check_id), "skupina", "")
        if i.severity == Severity.CHYBA:
            if grp == "Topologie":
                topo += 1
            else:
                attr += 1
        elif i.severity == Severity.VAROVANI:
            var += 1
    rozpad = []
    if topo:
        rozpad.append((f"chyby topologie ({topo}×)", min(60, 4 * topo)))
    if attr:
        rozpad.append((f"chyby atributů ({attr}×)", min(40, 2 * attr)))
    if var:
        rozpad.append((f"varování ({var}×)", min(15, round(0.5 * var))))
    if not has_rules:
        rozpad.append(("atributy nekontrolovány (chybí pravidla)", 10))
    value = max(0, 100 - sum(s for _, s in rozpad))
    if value >= 100 and not topo and not attr:
        popis, barva = "Připraveno k odevzdání", "#16A34A"
    elif value >= 85:
        popis, barva = "Skoro hotovo", "#65A30D"
    elif value >= 50:
        popis, barva = "Je co opravovat", "#D97706"
    else:
        popis, barva = "Hodně chyb", "#DC2626"
    return Skore(value, popis, barva, rozpad)
