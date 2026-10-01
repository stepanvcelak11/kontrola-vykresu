"""Osobní tahák: které chyby student dělá nejčastěji (podle posledních kontrol všech jeho projektů)."""

from __future__ import annotations

import json
from collections import Counter

KEY = "tahak/projekty"
MAX_PROJEKTU = 20


def _load(settings) -> dict[str, dict[str, int]]:
    try:
        data = json.loads(settings.value(KEY, "{}") or "{}")
        return {str(k): {str(a): int(b) for a, b in v.items()} for k, v in data.items() if isinstance(v, dict)}
    except (ValueError, TypeError, AttributeError):
        return {}


def record(settings, project_key: str, issues) -> None:
    """Uloží typy chyb z poslední kontroly projektu (přepíše předchozí – počítá se stav, ne počet kontrol)."""
    c = Counter(i.check_name for i in issues if i.severity.value != "info")
    data = _load(settings)
    data.pop(project_key, None)
    data[project_key] = dict(c)
    while len(data) > MAX_PROJEKTU:
        data.pop(next(iter(data)))
    settings.setValue(KEY, json.dumps(data, ensure_ascii=False))


def top(settings, n: int = 3) -> list[tuple[str, int, int]]:
    """Nejčastější typy chyb: (typ, celkem, ve kolika projektech) – přednost mají ty, co se opakují."""
    data = _load(settings)
    total: Counter = Counter()
    proj: Counter = Counter()
    for c in data.values():
        for k, v in c.items():
            if v > 0:
                total[k] += v
                proj[k] += 1
    order = sorted(total, key=lambda k: (-proj[k], -total[k], k))
    return [(k, total[k], proj[k]) for k in order[:n]]


def text(settings, n: int = 3) -> str:
    t = top(settings, n)
    if not t:
        return ""
    parts = [f"<b>{k}</b> ({v}×" + (f" v {p} projektech)" if p > 1 else ")") for k, v, p in t]
    return "💡 Na co si dát pozor – vaše nejčastější chyby: " + ", ".join(parts) + "."
