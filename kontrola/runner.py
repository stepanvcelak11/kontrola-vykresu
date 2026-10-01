"""Spuštění všech zapnutých kontrol nad výkresem."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .checks.base import REGISTRY, Cancelled, CheckContext, Issue
from .config import Config
from .model import Drawing
from .rules import RuleSet

ProgressFn = Callable[[int, str], None]


@dataclass
class CheckResult:
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    durations: dict[str, float] = field(default_factory=dict)
    cancelled: bool = False


def run_checks(drawing: Drawing, rules: RuleSet | None, config: Config,
               progress: ProgressFn | None = None, cancelled: Callable[[], bool] | None = None,
               only: list[str] | None = None) -> CheckResult:
    config.ensure_defaults()
    rules = rules or RuleSet()
    from .config import WIP_SKIP_CHECKS, WIP_SKIP_MESSAGES
    enabled = [cid for cid in REGISTRY if config.settings(cid).zapnuto and (only is None or cid in only)]
    result = CheckResult()
    if config.rozpracovany:
        enabled = [cid for cid in enabled if cid not in WIP_SKIP_CHECKS]
        result.notes.append("Rozpracovaný výkres: nehlásí se volné konce, neuzavřené plochy, mezery mezi "
                            "plochami a chybějící popisy. Před odevzdáním režim vypněte.")
    shared_cache: dict = {}
    n = max(1, len(enabled))
    for i, cid in enumerate(enabled):
        check = REGISTRY[cid]()
        cs = config.settings(cid)

        def sub(frac: float, i=i, name=check.nazev):
            if progress:
                progress(int((i + frac) * 100 / n), f"Kontrola: {name}")

        ctx = CheckContext(drawing, rules, config, cs.parametry, sub, cancelled)
        ctx._cache = shared_cache
        ctx.severity = cs.zavaznost
        if check.potrebuje_pravidla and not rules.pravidla:
            result.notes.append(f"{check.nazev}: přeskočeno – nejsou načtena pravidla (záložka Zadání).")
            continue
        sub(0.0)
        t0 = time.perf_counter()
        count = 0
        try:
            skip_msgs = WIP_SKIP_MESSAGES.get(cid, ()) if config.rozpracovany else ()
            for iss in check.run(ctx):
                if skip_msgs and any(m in iss.message for m in skip_msgs):
                    continue
                if count >= config.max_chyb_na_kontrolu:
                    result.notes.append(f"{check.nazev}: zobrazeno jen prvních "
                                        f"{config.max_chyb_na_kontrolu} chyb.")
                    break
                result.issues.append(iss)
                count += 1
        except Cancelled:
            result.cancelled = True
            break
        except Exception as exc:  # chyba v jedné kontrole nesmí zastavit ostatní
            result.notes.append(f"{check.nazev}: kontrola selhala ({exc}).")
        result.durations[cid] = time.perf_counter() - t0
        result.notes.extend(f"{check.nazev}: {m}" for m in ctx.notes)
    result.notes[:0] = shared_cache.get("_obecne_poznamky", [])
    result.issues.sort(key=lambda s: (s.severity.rank, s.check_name, s.y, s.x))
    for k, iss in enumerate(result.issues, start=1):
        iss.number = k
    if progress:
        progress(100, "Kontrola dokončena")
    return result


@dataclass
class Comparison:
    fixed: int
    new: int
    remaining: int

    def text(self) -> str:
        return (f"Ubylo chyb: {self.fixed}, nových: {self.new}, zůstává: {self.remaining}.")


def compare(old: list[Issue], new: list[Issue]) -> Comparison:
    # počítáme s násobnostmi – dvě stejné chyby na stejném místě jsou dvě chyby
    ok = Counter(i.key for i in old)
    nk = Counter(i.key for i in new)
    return Comparison(fixed=sum((ok - nk).values()), new=sum((nk - ok).values()),
                      remaining=sum((ok & nk).values()))


def carry_states(old_states: dict[str, dict], issues: list[Issue], recheck: bool = False):
    """Přenese stavy (opraveno/ignorovat, poznámka) z uloženého projektu.

    Při opakované kontrole se chyba označená jako „opraveno“, která ve výkresu
    stále je, vrací do stavu „nová“ – oprava se neprojevila.
    """
    for iss in issues:
        st = old_states.get(iss.key)
        if st:
            state = st.get("stav", iss.state)
            if recheck and state == "opraveno":
                state = "nová"
                iss.note = "Označeno jako opraveno, ale chyba ve výkresu stále je."
            else:
                iss.note = st.get("poznamka", iss.note)
            iss.state = state
