"""„Učitelův pohled“: předpověď, co bude v protokolu od učitele (GISoft symbologie + MGEO topologie).

Aplikace se učí z protokolů, které už od učitele máte: při každém porovnání (Kontrola → Porovnat
s protokolem učitele) si zapíše, kolik prvků s danou kombinací chybných atributů hlásil učitel
a kolik program. Z toho pak u nového výkresu odhadne, co učitel nahlásí:

* skupiny, které učitel hlásí stejně jako program → počítají se celé,
* skupiny, které program hlásí, ale učitel je (zatím) nikdy nehlásil → „nejspíš nehlásí“,
* skupiny, kde učitel našel víc, než program → varování „zkontrolujte ručně“.

Kalibrace je společná pro všechny projekty (soubor vedle projektů).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .checks.base import REGISTRY, Issue, Severity
from .export.mgeo_log import ATTR_CHECKS, issue_groups
from .protokol_ucitele import FIELD_LABEL


def calibration_path() -> Path:
    import os
    if os.environ.get("KONTROLA_KALIBRACE"):  # testy / přenosná instalace
        return Path(os.environ["KONTROLA_KALIBRACE"])
    from .project import default_projects_dir
    return default_projects_dir() / "kalibrace_ucitele.json"


def load_calibration(path: Path | None = None) -> dict:
    p = path or calibration_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"protokolu": 0, "skupiny": {}, "topologie": {}, "hlavicka": {}}


def _key(fields) -> str:
    return "|".join(sorted(fields)) or "-"


def _label(key: str) -> str:
    return ", ".join(FIELD_LABEL.get(f, f) for f in key.split("|") if f and f != "-") or "–"


def learn(rows, prot, raw_text: str = "", path: Path | None = None) -> dict:
    """Zapíše výsledek porovnání s protokolem učitele do kalibrace."""
    cal = load_calibration(path)
    cal["protokolu"] = cal.get("protokolu", 0) + 1
    sk = cal.setdefault("skupiny", {})
    for r in rows:
        k = _key(r.spatne)
        e = sk.setdefault(k, {"ucitel": 0, "program": 0, "vrstvy_ucitel": {}})
        e["ucitel"] += int(r.ucitel)
        e["program"] += int(r.program)
        if r.ucitel > r.program:
            e["vrstvy_ucitel"][r.vrstva] = e["vrstvy_ucitel"].get(r.vrstva, 0) + int(r.ucitel - r.program)
    topo = cal.setdefault("topologie", {})
    for name, n in (prot.topologie or {}).items():
        t = topo.setdefault(name, {"soucet": 0, "protokolu": 0})
        t["soucet"] += int(n)
        t["protokolu"] += 1
    head = cal.setdefault("hlavicka", {})
    for lab, rx in (("meritko", r"Měřítko výkresu:\s*(1:\d+)"), ("presnost", r"Přesnost porovnání:\s*([\d.,]+)")):
        m = re.search(rx, raw_text)
        if m:
            head[lab] = m.group(1)
    cal["posledni"] = dt.datetime.now().isoformat(timespec="seconds")
    p = path or calibration_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    return cal


@dataclass
class Skupina:
    klic: str
    program: int
    predpoved: int
    poznamka: str
    vrstvy: list[str] = field(default_factory=list)


@dataclass
class Predikce:
    atributy: int  # odhad počtu chybných prvků v protokolu symbologie
    skupin: int
    topologie: int  # odhad topologických chyb (MGEO)
    skupiny: list[Skupina]
    pozor: list[str]  # kde učitel dříve našel víc než program
    protokolu: int  # z kolika protokolů se aplikace učila
    verdikt: str
    barva: str


def predict(drawing, rules, issues: list[Issue], cal: dict | None = None) -> Predikce:
    cal = cal if cal is not None else load_calibration()
    learned = cal.get("skupiny", {})
    n_prot = int(cal.get("protokolu", 0))
    open_ = [i for i in issues if i.state == "nová"]
    groups, samples = issue_groups(drawing, rules, open_)
    per_key: Counter = Counter()
    layers: dict[str, set] = {}
    for key, n in groups.items():
        a, wrong = samples[key]
        w = set(wrong)
        if "vrstva" in w:
            w.discard("číslo")
        k = _key(w)
        per_key[k] += n
        layers.setdefault(k, set()).add(a["vrstva"])
    out = []
    for k, n in sorted(per_key.items(), key=lambda kv: -kv[1]):
        e = learned.get(k)
        if not e or n_prot == 0:
            out.append(Skupina(k, n, n, "zatím bez zkušenosti s učitelem – počítá se celé", sorted(layers[k])))
            continue
        u, p = e.get("ucitel", 0), e.get("program", 0)
        if u == 0 and p >= 3:
            pred, note = 0, f"učitel tyto chyby zatím nehlásil (program jich dřív hlásil {p})"
        else:
            ratio = (u + 1) / (p + 1)
            pred = max(0, round(n * min(ratio, 3.0)))
            note = ("učitel hlásí stejně jako program" if 0.8 <= ratio <= 1.25 else
                    f"učitel hlásí zhruba {ratio:.1f}× tolik co program")
        out.append(Skupina(k, n, pred, note, sorted(layers[k])))
    pozor = []
    for k, e in learned.items():
        if e.get("ucitel", 0) > e.get("program", 0) and e.get("vrstvy_ucitel"):
            lay = ", ".join(sorted(e["vrstvy_ucitel"], key=lambda x: -e["vrstvy_ucitel"][x])[:4])
            pozor.append(f"{_label(k)} – učitel dřív našel o {e['ucitel'] - e['program']} víc (vrstvy {lay}): "
                         "zkontrolujte ručně")
    topo = sum(1 for i in open_ if i.severity == Severity.CHYBA and i.check_id not in ATTR_CHECKS
               and getattr(REGISTRY.get(i.check_id), "skupina", "") == "Topologie")
    attr = sum(s.predpoved for s in out)
    skupin = sum(1 for s in out if s.predpoved > 0)
    if attr == 0 and topo == 0:
        verdikt, barva = "Protokol bude nejspíš čistý – bez chyb.", "#16A34A"
    elif attr + topo <= 5:
        verdikt, barva = f"Učitel nejspíš najde jen pár chyb ({attr + topo}).", "#D97706"
    else:
        verdikt, barva = f"Učitel nejspíš nahlásí asi {attr} chybných prvků symbologie a {topo} chyb topologie.", \
            "#DC2626"
    return Predikce(attr, skupin, topo, out, pozor, n_prot, verdikt, barva)


def label(key: str) -> str:
    return _label(key)
