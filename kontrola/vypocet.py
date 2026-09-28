"""Kontrola výpočtu souřadnic podrobných bodů ze zápisníku totální stanice (polární metoda).

Postup odpovídá výpočtu v programu Groma (polární metoda dávkou):

1. zápisník (formát Groma ``*.zap``) – stanovisko, výška přístroje, orientace, podrobné body
   (šikmá délka, výška cíle, vodorovný směr Hz a zenitový úhel z v gonech),
2. měření ve dvou polohách dalekohledu se zprůměrují,
3. šikmá délka → vodorovná ``d = D·sin z``, vynásobená měřítkovým koeficientem (zobrazení
   S-JTSK + nadmořská výška; lze zadat ručně z protokolu Gromy),
4. orientační posun = vážený průměr (váha = délka) ze směrníků na dané body,
5. ``Y = Ys + d·sin σ, X = Xs + d·cos σ``, ``Z = Zs + D·cos z + vp − vc`` (+ zakřivení a refrakce),
6. výšky stanovisek: z nivelačního bodu (bod s výškou a písmeny v čísle, např. JM-071-519),
   další stanovisko přes obousměrně měřené převýšení; jinak výška ze seznamu daných bodů.

Výsledek se porovná se seznamem souřadnic, který student spočítal sám.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .checks.seznam import ListPoint, read_point_list, short_numbers

GON = math.pi / 200.0
R_EARTH = 6380703.6105  # poloměr Gaussovy koule Křovákova zobrazení [m]
RHO0 = 1298039.0046  # poloměr základní rovnoběžky v rovině [m]
K_REFR = 0.13


@dataclass
class Obs:
    bod: str
    sd: float  # šikmá délka
    vc: float  # výška cíle
    hz: float  # gony
    z: float  # gony
    n: int = 1  # počet měření (poloh)


@dataclass
class Station:
    bod: str
    vp: float
    orient: list[Obs] = field(default_factory=list)
    detail: list[Obs] = field(default_factory=list)


@dataclass
class Point:
    bod: str
    y: float
    x: float
    z: float | None
    stanovisko: str = ""
    kontrolni: bool = False  # druhé (kontrolní) určení bodu


@dataclass
class Result:
    body: list[Point]
    stanoviska: dict[str, Point]
    koeficient: float
    zpravy: list[str]


def _merge_faces(obs: list[Obs]) -> list[Obs]:
    """Měření stejného bodu ve dvou polohách dalekohledu (za sebou) se zprůměrují."""
    out: list[Obs] = []
    for o in obs:
        prev = out[-1] if out else None
        if prev is not None and prev.bod == o.bod and abs(prev.sd - o.sd) < 0.5:
            hz2, z2 = o.hz, o.z
            if z2 > 200:  # II. poloha
                hz2, z2 = (o.hz - 200.0) % 400.0, 400.0 - o.z
            d = (hz2 - prev.hz + 200.0) % 400.0 - 200.0
            n = prev.n
            prev.hz = (prev.hz + d / (n + 1)) % 400.0
            prev.z = (prev.z * n + z2) / (n + 1)
            prev.sd = (prev.sd * n + o.sd) / (n + 1)
            prev.n = n + 1
        else:
            hz, z = o.hz, o.z
            if z > 200:
                hz, z = (o.hz - 200.0) % 400.0, 400.0 - o.z
            out.append(Obs(o.bod, o.sd, o.vc, hz, z))
    return out


def read_zap(path: str | Path) -> list[Station]:
    """Zápisník Gromy: ``1 <stanovisko> <vp> *``, orientace, ``-1``, podrobné body, ``/``."""
    raw = Path(path).read_bytes()
    text = raw.decode("cp1250", errors="replace")
    stations: list[Station] = []
    cur: Station | None = None
    part = "orient"
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        tok = s.split()
        if tok[0] == "1" and len(tok) >= 3 and (s.endswith("*") or len(tok) == 3):
            try:
                cur = Station(tok[1], float(tok[2]))
            except ValueError:
                continue
            stations.append(cur)
            part = "orient"
            continue
        if cur is None:
            continue
        if s == "-1":
            part = "detail"
            continue
        if s == "/":
            cur = None
            continue
        if len(tok) >= 5:
            try:
                o = Obs(tok[0], float(tok[1]), float(tok[2]), float(tok[3]), float(tok[4]))
            except ValueError:
                continue
            (cur.orient if part == "orient" else cur.detail).append(o)
    for st in stations:
        st.orient = _merge_faces(st.orient)
        st.detail = _merge_faces(st.detail)
    return stations


def krovak_scale(y: float, x: float, h: float) -> float:
    """Měřítkový koeficient: měřítko Křovákova zobrazení a redukce z nadmořské výšky."""
    rho = math.hypot(abs(x), abs(y))
    m = 0.9999 * (1.0 + (rho - RHO0) ** 2 / (2.0 * R_EARTH ** 2))
    return m - h / R_EARTH


def _find(known: dict[str, ListPoint], name: str) -> ListPoint | None:
    if name in known:
        return known[name]
    forms = short_numbers(name)
    for k, v in known.items():
        if forms & short_numbers(k) and (name == k or len(re.sub(r"\D", "", name)) <= 5
                                         or len(re.sub(r"\D", "", k)) <= 5):
            return v
    return None


def _dh(o: Obs, vp: float, m: float) -> tuple[float, float]:
    """(vodorovná délka v zobrazení, převýšení terén–terén)."""
    d = o.sd * math.sin(o.z * GON)
    dh = o.sd * math.cos(o.z * GON) + vp - o.vc
    dh += d * d * (1.0 - K_REFR) / (2.0 * R_EARTH)
    return d * m, dh


def compute(stations: list[Station], known_points: list[ListPoint], koeficient: float | None = None) -> Result:
    known = {p.cislo: p for p in known_points}
    msgs: list[str] = []
    st_pts: dict[str, Point] = {}
    # souřadnice stanovisek (kladné S-JTSK: a = Y, b = X)
    for st in stations:
        k = _find(known, st.bod)
        if k is None:
            msgs.append(f"Stanovisko {st.bod}: chybí jeho souřadnice v seznamu daných bodů.")
            continue
        st_pts[st.bod] = Point(st.bod, abs(k.a), abs(k.b), k.z)
    if not st_pts:
        return Result([], {}, koeficient or 1.0, msgs + ["Nelze počítat – žádné stanovisko nemá souřadnice."])
    if koeficient is None:
        ys = [p.y for p in st_pts.values()]
        xs = [p.x for p in st_pts.values()]
        hs = [p.z for p in st_pts.values() if p.z] or [0.0]
        koeficient = krovak_scale(sum(ys) / len(ys), sum(xs) / len(xs), sum(hs) / len(hs))
        msgs.append(f"Měřítkový koeficient (Křovák + nadmořská výška): {koeficient:.10f} "
                    f"({(koeficient - 1) * 1e5:+.1f} mm/100 m).")
    else:
        msgs.append(f"Měřítkový koeficient zadaný ručně: {koeficient:.10f}.")
    m = koeficient

    # výšky stanovisek: nivelační bod, pak obousměrná převýšení mezi stanovisky
    for st in stations:
        sp = st_pts.get(st.bod)
        if sp is None:
            continue
        for o in st.orient + st.detail:
            kp = known.get(o.bod) or (_find(known, o.bod) if re.search(r"[A-Za-z]", o.bod) else None)
            if kp is not None and kp.z and re.search(r"[A-Za-z]", o.bod):
                _, dh = _dh(o, st.vp, 1.0)
                sp.z = kp.z - dh
                msgs.append(f"Výška stanoviska {st.bod} z nivelačního bodu {o.bod}: "
                            f"{kp.z:.3f} − ({dh:.3f}) = {sp.z:.3f} m")
                sp.stanovisko = "niv"
                break
    for st in stations:
        sp = st_pts.get(st.bod)
        if sp is None or sp.stanovisko == "niv":
            continue
        for other in stations:
            op = st_pts.get(other.bod)
            if other is st or op is None or op.stanovisko != "niv":
                continue
            tam = next((o for o in other.orient + other.detail if short_numbers(o.bod) & short_numbers(st.bod)),
                       None)
            zpet = next((o for o in st.orient + st.detail if short_numbers(o.bod) & short_numbers(other.bod)), None)
            vals = []
            if tam is not None:
                vals.append(_dh(tam, other.vp, 1.0)[1])
            if zpet is not None:
                vals.append(-_dh(zpet, st.vp, 1.0)[1])
            if vals:
                sp.z = op.z + sum(vals) / len(vals)
                msgs.append(f"Výška stanoviska {st.bod} z {other.bod} (převýšení "
                            f"{'obousměrně' if len(vals) == 2 else 'jednosměrně'}): {sp.z:.3f} m")
                sp.stanovisko = "niv"
                break

    body: list[Point] = []
    seen: set[str] = set()
    for st in stations:
        sp = st_pts.get(st.bod)
        if sp is None:
            continue
        # orientace
        num = den = 0.0
        rows = []
        for o in st.orient:
            kp = _find(known, o.bod)
            if kp is None:
                msgs.append(f"Stanovisko {st.bod}: orientace na {o.bod} vynechána – bod nemá souřadnice "
                            "(doplňte ho do seznamu daných bodů, např. z www.cuzk.cz).")
                continue
            dy, dx = abs(kp.a) - sp.y, abs(kp.b) - sp.x
            if abs(dy) < 1e-6 and abs(dx) < 1e-6:
                continue
            smer = (math.atan2(dy, dx) / GON) % 400.0
            posun = (smer - o.hz) % 400.0
            w = math.hypot(dy, dx)
            rows.append((o.bod, posun, w))
        if not rows:
            msgs.append(f"Stanovisko {st.bod}: žádná orientace s danými souřadnicemi – nelze počítat.")
            continue
        ref = rows[0][1]
        for _, p_, w in rows:
            num += w * ((p_ - ref + 200.0) % 400.0 - 200.0)
            den += w
        posun = (ref + num / den) % 400.0
        msgs.append(f"Stanovisko {st.bod}: orientační posun {posun:.4f} g ("
                    + ", ".join(f"{b} v={(((p_ - posun + 200) % 400) - 200):+.4f} g" for b, p_, _ in rows) + ")")
        for o in st.detail:
            d, dh = _dh(o, st.vp, m)
            sigma = (posun + o.hz) % 400.0
            y = sp.y + d * math.sin(sigma * GON)
            x = sp.x + d * math.cos(sigma * GON)
            z = sp.z + dh if sp.z is not None else None
            key = frozenset(short_numbers(o.bod))
            ctrl = any(key & frozenset(short_numbers(s)) for s in seen)
            body.append(Point(o.bod, y, x, z, st.bod, ctrl))
            seen.add(o.bod)
    return Result(body, st_pts, m, msgs)


@dataclass
class Rozdil:
    bod: str
    stanovisko: str
    dy: float | None
    dx: float | None
    dz: float | None
    poznamka: str
    vypocet: Point | None = None
    student: ListPoint | None = None

    @property
    def dxy(self) -> float | None:
        return None if self.dy is None else math.hypot(self.dy, self.dx)


def compare(res: Result, student: list[ListPoint], tol_xy: float = 0.01, tol_z: float = 0.01,
            known: list[ListPoint] | None = None) -> tuple[list[Rozdil], list[Rozdil]]:
    """Porovná vypočtené body se seznamem studenta. Vrací (chyby, vše)."""
    by_short: dict[str, ListPoint] = {}
    for p in student:
        for f in short_numbers(p.cislo):
            by_short.setdefault(f, p)
    rows: list[Rozdil] = []
    used: set[str] = set()
    kn = {p.cislo: p for p in (known or [])}
    for b in res.body:
        if b.kontrolni or (kn and _find(kn, b.bod) is not None):
            continue  # kontrolní určení a dané body (nivelační bod…) se neporovnávají
        sp = next((by_short[f] for f in short_numbers(b.bod) if f in by_short), None)
        if sp is None:
            rows.append(Rozdil(b.bod, b.stanovisko, None, None, None, "chybí v seznamu", b, None))
            continue
        used.add(sp.cislo)
        dy, dx = abs(sp.a) - b.y, abs(sp.b) - b.x
        dz = (sp.z - b.z) if (sp.z not in (None, 0.0) and b.z is not None) else None
        bad = []
        if math.hypot(dy, dx) > tol_xy:
            bad.append(f"poloha o {math.hypot(dy, dx):.3f} m")
        if dz is not None and abs(dz) > tol_z:
            bad.append(f"výška o {dz:+.3f} m")
        rows.append(Rozdil(b.bod, b.stanovisko, dy, dx, dz, ", ".join(bad) or "v pořádku", b, sp))
    for p in student:
        if p.cislo not in used and not any(_find({p.cislo: p}, s.bod) for s in res.stanoviska.values()) \
                and not (kn and _find(kn, p.cislo) is not None):
            rows.append(Rozdil(p.cislo, "", None, None, None, "navíc – není v zápisníku", None, p))
    bad = [r for r in rows if r.poznamka != "v pořádku"]
    return bad, rows


def text_report(res: Result, rows: list[Rozdil], bad: list[Rozdil]) -> str:
    out = ["KONTROLA VÝPOČTU SOUŘADNIC (polární metoda)", "=" * 44, ""]
    out += res.zpravy + [""]
    out.append(f"Vypočteno bodů: {sum(1 for b in res.body if not b.kontrolni)}, porovnáno: "
               f"{sum(1 for r in rows if r.student is not None and r.vypocet is not None)}, rozdílů: {len(bad)}")
    out.append("")
    out.append(f"{'Bod':<18}{'Stan.':<8}{'dY':>9}{'dX':>9}{'dZ':>9}  Poznámka")
    for r in rows:
        f = lambda v: f"{v:+.3f}" if v is not None else "–"  # noqa: E731
        out.append(f"{r.bod:<18}{r.stanovisko:<8}{f(r.dy):>9}{f(r.dx):>9}{f(r.dz):>9}  {r.poznamka}")
    return "\n".join(out)
