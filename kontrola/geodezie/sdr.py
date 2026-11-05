"""Zápisník SDR33 (Trimble S3 / Sokkia, export „SDR33 observations“): stanoviska, záměry v obou polohách.

Pevné sloupce po 16 znacích: 02 = stanovisko (výška přístroje na konci), 03 = výška cíle, 09F1/09F2 =
měření v I./II. poloze (odkud, kam, šikmá délka, zenitový úhel, vodorovný směr), 11TP / 07 = orientace.
Opakovaná měření Trimble čísluje příponou (4002.1, 4002.2…) – ta se odstraní, aby se polohy spojily.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..vypocet import Obs, Station

_PRIPONA = re.compile(r"^(.+?)\.\d{1,2}$")


def je_sdr(text: str) -> bool:
    return text.lstrip().startswith("00NMSDR")


def _bod(s: str) -> str:
    s = s.strip()
    m = _PRIPONA.match(s)
    return m.group(1) if m else s


def _cisla(s: str) -> list[float]:
    out = []
    for i in range(0, len(s), 16):
        t = s[i:i + 16].strip()
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def read_sdr(cesta: str | Path, dane: set[str] | None = None) -> list[Station]:
    """Stanoviska se záměrami tak, jak jsou zapsané (obě polohy zvlášť, spojí je výpočet).
    Orientace = záměry na orientační bod stanoviska (záznam 11TP / 07) a na dané body na začátku."""
    text = Path(cesta).read_bytes().decode("cp1250", errors="replace")
    dane = dane or set()
    stanoviska: list[Station] = []
    st: Station | None = None
    orient: set[str] = set()
    vc = 0.0
    for r in text.splitlines():
        kod, zbytek = r[:4], r[4:]
        if kod.startswith("02"):
            vp = _cisla(zbytek[16:])
            st = Station(_bod(zbytek[:16]), vp[-1] if vp else 0.0)
            stanoviska.append(st)
            orient = set()
        elif kod.startswith(("11", "07")) and st is not None:
            orient.add(_bod(zbytek[16:32]))
        elif kod.startswith("03"):
            c = _cisla(zbytek)
            vc = c[0] if c else vc
        elif kod.startswith("09") and st is not None:
            c = _cisla(zbytek[32:80])
            if len(c) < 3:
                continue
            sd, z, hz = c[0], c[1], c[2]
            cil = _bod(zbytek[16:32])
            o = Obs(cil, sd, vc, hz, z)
            if cil in orient or (cil in dane and not st.detail):
                st.orient.append(o)
            else:
                st.detail.append(o)
    return [s for s in stanoviska if s.orient or s.detail]
