"""Import zápisníku z totálních stanic Leica ve formátu GSI-8 a GSI-16.

Formát je veřejně popsaný (Leica „GSI Online“): řádek = bloky slov ``WI`` (2 číslice) + 4 znaky
informace + znaménko + data (8 nebo 16 číslic); GSI-16 začíná řádek hvězdičkou. Šestý znak informace
je jednotka. Použitá slova: 11 číslo bodu, 21 Hz, 22 V (zenit), 31 šikmá délka, 32 vodorovná délka,
87 výška cíle, 88 výška přístroje, 84–86 souřadnice stanoviska.

Stanovisko se pozná podle řádku s výškou přístroje (88) nebo souřadnicemi stanoviska (84–86).
Rozdělení na orientace a podrobné body: záměry na dané body na začátku stanoviska jsou orientace.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from ..vypocet import Obs, Station, _merge_faces

_SLOVO = re.compile(r"^(\d{2})([\d.]{4})([+-])(\S+)$")

# jednotky úhlů (6. znak): 0 = 360° ″, 1 = 360° desetinné, 2 = gon, 3 = mil, 4 = 360° ddd.mmss
_UHLY = {"0": None, "1": "deg", "2": "gon", "3": "mil", "4": "dms", "5": "gon", "6": "gon"}
# jednotky délek: počet desetinných míst v metrech (0/6/8 = mm, 0,1 mm, 0,01 mm; 1, 7 stopy)
_DELKY = {"0": (3, 1.0), "1": (3, 0.3048), "6": (4, 1.0), "7": (4, 0.3048), "8": (5, 1.0)}


def je_gsi(text: str) -> bool:
    for line in text.splitlines()[:20]:
        s = line.strip().lstrip("*")
        if not s:
            continue
        w = s.split()[0]
        return bool(_SLOVO.match(w)) and w[:2] in ("11", "41", "42", "43", "44", "45")
    return False


def _uhel(info: str, sign: str, data: str) -> float:
    jed = _UHLY.get(info[-1], "gon")
    v = int(data) * (-1 if sign == "-" else 1)
    if jed == "gon":
        return v / 100000.0
    if jed == "deg":
        return v / 100000.0 * 400 / 360
    if jed == "mil":
        return v / 10000.0 * 400 / 6400
    if jed == "dms":
        t = f"{abs(v):08d}"
        d, m, s = int(t[:-5]), int(t[-5:-3]), int(t[-3:]) / 10
        return math.copysign(d + m / 60 + s / 3600, v) * 400 / 360
    # 360° ″ : data v desetinách vteřiny
    return v / 10.0 / 3600 * 400 / 360


def _delka(info: str, sign: str, data: str) -> float:
    des, k = _DELKY.get(info[-1], (3, 1.0))
    return int(data) / 10 ** des * k * (-1 if sign == "-" else 1)


def precti_radek(line: str) -> dict[str, object]:
    out: dict[str, object] = {}
    for w in line.strip().lstrip("*").split():
        m = _SLOVO.match(w)
        if not m:
            continue
        wi, info, sign, data = m.groups()
        try:
            if wi == "11":
                out["bod"] = data.lstrip("0") or "0"
            elif wi == "21":
                out["hz"] = _uhel(info, sign, data)
            elif wi == "22":
                out["z"] = _uhel(info, sign, data)
            elif wi in ("31", "32", "33", "81", "82", "83", "84", "85", "86", "87", "88"):
                out[wi] = _delka(info, sign, data)
        except ValueError:
            continue
    return out


def read_gsi(path: str | Path) -> tuple[list[Station], list[str]]:
    """Stanoviska se všemi záměrami jako podrobné body + varování (řádky, které nešlo použít)."""
    text = Path(path).read_bytes().decode("cp1250", errors="replace")
    stations: list[Station] = []
    cur: Station | None = None
    vc = 0.0
    varovani = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        r = precti_radek(line)
        if not r:
            varovani.append(f"řádek {i}: neznámý formát")
            continue
        if "88" in r or ("84" in r and "21" not in r):
            cur = Station(str(r.get("bod", f"st{len(stations) + 1}")), float(r.get("88", 0.0)))
            stations.append(cur)
            continue
        if "87" in r:
            vc = float(r["87"])
        if "hz" not in r or "bod" not in r:
            continue
        if cur is None:
            varovani.append(f"řádek {i}: měření před prvním stanoviskem – přeskočeno")
            continue
        if "31" in r and "z" in r:
            sd, z = float(r["31"]), float(r["z"])
        elif "32" in r:  # jen vodorovná délka: zenit 100 g
            sd, z = float(r["32"]), float(r.get("z", 100.0))
            if "z" in r and abs(math.sin(z * math.pi / 200)) > 1e-9:
                sd = sd / math.sin(z * math.pi / 200)
        else:
            varovani.append(f"řádek {i}: bod {r['bod']} bez délky – přeskočeno")
            continue
        cur.detail.append(Obs(str(r["bod"]), sd, vc, float(r["hz"]), z))
    return stations, varovani


def rozdel_orientace(stations: list[Station], dane: set[str]) -> None:
    """Záměry na dané body na začátku stanoviska jsou orientace (jako v zápisníku Gromy), dané body měřené
    později mezi podrobnými body zůstanou jako kontrolní měření. Obě polohy dalekohledu se spojí."""
    for st in stations:
        n = 0
        while n < len(st.detail) and st.detail[n].bod in dane and st.detail[n].bod != st.bod:
            n += 1
        orient = st.detail[:n]
        st.detail = st.detail[n:]
        st.orient = _merge_faces(st.orient + orient)
        st.detail = _merge_faces(st.detail)


def zapis_gsi(stations: list[Station], gsi16: bool = True) -> str:
    """Zápis stanovisek do GSI (gon, 0,1 mm) – pro testy a výměnu dat."""
    n = 16 if gsi16 else 8

    def slovo(wi, info, v, des):
        val = round(v * 10 ** des)
        return f"{wi}{info}{'-' if val < 0 else '+'}{abs(val):0{n}d}"

    def bod(c):
        return f"11....+{c.rjust(n, '0')[-n:]}"

    radky = []
    for st in stations:
        radky.append(" ".join([bod(st.bod), slovo("88", "..16", st.vp, 4)]))
        for o in st.orient + st.detail:
            radky.append(" ".join([bod(o.bod), slovo("21", ".322", o.hz, 5), slovo("22", ".322", o.z, 5),
                                   slovo("31", "..06", o.sd, 4), slovo("87", "..16", o.vc, 4)]))
    pre = "*" if gsi16 else ""
    return "\n".join(pre + r + " " for r in radky) + "\n"
