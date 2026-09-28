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
    d_hz: float | None = None  # rozdíl Hz mezi polohami (I − II ± 200) [g] – kolimační chyba ×2
    index_z: float | None = None  # indexová chyba zenitového úhlu (z_I + z_II − 400) / 2 [g]
    d_sd: float | None = None  # rozdíl šikmých délek mezi polohami [m]


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
class Kontrola:
    """Jedna kontrola kvality měření (dvě polohy, orientace, kontrolní délka, druhé určení bodu)."""
    druh: str
    stanovisko: str
    bod: str
    hodnota: str
    ok: bool
    vysvetleni: str = ""


@dataclass
class Result:
    body: list[Point]
    stanoviska: dict[str, Point]
    koeficient: float
    zpravy: list[str]
    kontroly: list[Kontrola] = field(default_factory=list)
    posuny: dict[str, float] = field(default_factory=dict)  # orientační posun na stanovisku [g]


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
            if prev.n == 1:
                prev.d_hz = d
                prev.index_z = (o.z + prev._z_raw - 400.0) / 2.0 if o.z > 200 >= prev._z_raw else None
                prev.d_sd = o.sd - prev.sd
            n = prev.n
            prev.hz = (prev.hz + d / (n + 1)) % 400.0
            prev.z = (prev.z * n + z2) / (n + 1)
            prev.sd = (prev.sd * n + o.sd) / (n + 1)
            prev.n = n + 1
        else:
            hz, z = o.hz, o.z
            if z > 200:
                hz, z = (o.hz - 200.0) % 400.0, 400.0 - o.z
            nw = Obs(o.bod, o.sd, o.vc, hz, z)
            nw._z_raw = o.z
            out.append(nw)
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
    kontroly: list[Kontrola] = []
    posuny: dict[str, float] = {}
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
            if o.sd > 0.5:  # délka na orientaci ověří, že jde opravdu o daný bod
                dm = _dh(o, st.vp, m)[0]
                dd = dm - w
                lim = max(0.03, 0.0002 * w)
                kontroly.append(Kontrola("Délka na orientaci", st.bod, o.bod, f"{dd * 1000:+.0f} mm", abs(dd) <= lim,
                                         f"měřená vodorovná délka {dm:.3f} m, ze souřadnic {w:.3f} m"
                                         + ("" if abs(dd) <= lim else " – zkontrolujte číslo a souřadnice "
                                            "orientačního bodu (jiný bod? překlep v souřadnicích?)")))
        if not rows:
            msgs.append(f"Stanovisko {st.bod}: žádná orientace s danými souřadnicemi – nelze počítat.")
            continue
        ref = rows[0][1]
        for _, p_, w in rows:
            num += w * ((p_ - ref + 200.0) % 400.0 - 200.0)
            den += w
        posun = (ref + num / den) % 400.0
        posuny[st.bod] = posun
        for b, p_, w in rows:
            v = ((p_ - posun + 200) % 400) - 200
            lin = abs(v) * GON * w
            kontroly.append(Kontrola("Oprava orientace", st.bod, b, f"{v * 10000:+.0f} cc ({lin * 1000:.0f} mm)",
                                     lin <= 0.03, "oprava směru na orientaci vůči průměrnému posunu; "
                                     "velká oprava = chybná orientace nebo souřadnice orientačního bodu"))
        for o in st.orient + st.detail:
            if o.d_hz is not None and abs(o.d_hz) > 0.01:
                kontroly.append(Kontrola("Dvě polohy – Hz", st.bod, o.bod, f"{o.d_hz * 10000:+.0f} cc", False,
                                         "rozdíl směru v I. a II. poloze je velký (> 100 cc) – špatně zacílený "
                                         "bod nebo chyba v zápisníku"))
            if o.d_sd is not None and abs(o.d_sd) > 0.01:
                kontroly.append(Kontrola("Dvě polohy – délka", st.bod, o.bod, f"{o.d_sd * 1000:+.0f} mm", False,
                                         "délky v I. a II. poloze se liší o víc než 1 cm"))
        idx = [o.index_z for o in st.orient + st.detail if o.index_z is not None]
        if idx:
            mi = sum(idx) / len(idx)
            kontroly.append(Kontrola("Indexová chyba z", st.bod, "", f"{mi * 10000:+.0f} cc", abs(mi) < 0.01,
                                     f"průměr z {len(idx)} měření ve dvou polohách; zprůměrováním poloh se "
                                     "vyloučí"))
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
    # druhé (kontrolní) určení bodu z jiného stanoviska
    first: dict[frozenset, Point] = {}
    for b in body:
        key = frozenset(short_numbers(b.bod))
        prev = next((p for k, p in first.items() if k & key), None)
        if prev is None or not b.kontrolni:
            first.setdefault(key, b)
            continue
        dxy = math.hypot(b.y - prev.y, b.x - prev.x)
        dz = (b.z - prev.z) if (b.z is not None and prev.z is not None) else None
        kontroly.append(Kontrola("Kontrolní určení", f"{prev.stanovisko} / {b.stanovisko}", b.bod,
                                 f"{dxy * 1000:.0f} mm" + (f", výška {dz * 1000:+.0f} mm" if dz is not None else ""),
                                 dxy <= 0.05 and (dz is None or abs(dz) <= 0.05),
                                 "rozdíl dvou nezávislých určení téhož bodu z různých stanovisek"))
    return Result(body, st_pts, m, msgs, kontroly, posuny)


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


def text_report(res: Result, rows: list[Rozdil], bad: list[Rozdil], diag: list[str] | None = None) -> str:
    out = ["KONTROLA VÝPOČTU SOUŘADNIC (polární metoda)", "=" * 44, ""]
    out += res.zpravy + [""]
    if res.kontroly:
        out.append("Kontrola měření:")
        for k in res.kontroly:
            out.append(f"  {'OK ' if k.ok else '!! '} {k.druh:<20} {k.stanovisko:<12} {k.bod:<18} {k.hodnota}")
        out.append("")
    if diag:
        out.append("Pravděpodobné příčiny rozdílů:")
        out += [f"  • {d}" for d in diag] + [""]
    out.append(f"Vypočteno bodů: {sum(1 for b in res.body if not b.kontrolni)}, porovnáno: "
               f"{sum(1 for r in rows if r.student is not None and r.vypocet is not None)}, rozdílů: {len(bad)}")
    out.append("")
    out.append(f"{'Bod':<18}{'Stan.':<8}{'dY':>9}{'dX':>9}{'dZ':>9}  Poznámka")
    for r in rows:
        f = lambda v: f"{v:+.3f}" if v is not None else "–"  # noqa: E731
        out.append(f"{r.bod:<18}{r.stanovisko:<8}{f(r.dy):>9}{f(r.dx):>9}{f(r.dz):>9}  {r.poznamka}")
    return "\n".join(out)


def _mean_std(v: list[float]) -> tuple[float, float]:
    if not v:
        return 0.0, 0.0
    m = sum(v) / len(v)
    return m, (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5


def diagnose(res: Result, rows: list[Rozdil], tol_xy: float = 0.01, tol_z: float = 0.01) -> list[str]:
    """Proč se seznam studenta liší: hledá typické chyby výpočtu podle vzoru rozdílů na stanovisku.

    * body jsou pootočené kolem stanoviska → jiný orientační posun,
    * rozdíl roste s délkou → jiný (nebo žádný) měřítkový koeficient,
    * všechny body posunuté stejně → jiné souřadnice stanoviska,
    * všechny výšky posunuté stejně → jiná výška stanoviska / výška přístroje,
    * dva body „prohozené“ → přehozená čísla bodů.
    """
    out: list[str] = []
    by_st: dict[str, list[Rozdil]] = {}
    for r in rows:
        if r.vypocet is not None and r.student is not None:
            by_st.setdefault(r.stanovisko, []).append(r)
    for st, rs in by_st.items():
        sp = res.stanoviska.get(st)
        if sp is None or len(rs) < 3:
            continue
        bad = [r for r in rs if (r.dxy or 0) > tol_xy or (r.dz is not None and abs(r.dz) > tol_z)]
        if not bad:
            continue
        rot, ratio, dys, dxs, dzs = [], [], [], [], []
        for r in rs:
            cy, cx = r.vypocet.y - sp.y, r.vypocet.x - sp.x
            sy, sx = abs(r.student.a) - sp.y, abs(r.student.b) - sp.x
            dc, ds = math.hypot(cy, cx), math.hypot(sy, sx)
            if dc > 1.0 and ds > 1.0:
                a = (math.atan2(sy, sx) - math.atan2(cy, cx)) / GON
                rot.append((a + 200) % 400 - 200)
                ratio.append(ds / dc - 1.0)
            dys.append(r.dy)
            dxs.append(r.dx)
            if r.dz is not None:
                dzs.append(r.dz)
        n_bad = len([r for r in bad if (r.dxy or 0) > tol_xy])
        if n_bad >= max(2, len(rs) // 2):
            mr, sr = _mean_std(rot)
            mk, sk = _mean_std(ratio)
            my, sy_ = _mean_std(dys)
            mx, sx_ = _mean_std(dxs)
            if abs(mr) > 0.002 and sr < max(0.0015, abs(mr) * 0.25):
                out.append(f"Stanovisko {st}: vaše body jsou pootočené o {mr * 10000:+.0f} cc kolem stanoviska – "
                           "jiný orientační posun. Zkontrolujte orientace (číslo a souřadnice orientačních bodů, "
                           "vážený průměr posunu, vynechanou II. polohu).")
            elif abs(mk) > 30e-6 and sk < max(10e-6, abs(mk) * 0.3):
                exp = res.koeficient - 1.0
                if abs(mk + exp) < max(15e-6, abs(exp) * 0.3):
                    out.append(f"Stanovisko {st}: vaše délky jsou delší/kratší o {mk * 1e6:+.0f} ppm – vypadá to, "
                               f"že jste nepoužili měřítkový koeficient ({res.koeficient:.6f}).")
                else:
                    out.append(f"Stanovisko {st}: rozdíl roste s délkou ({mk * 1e6:+.0f} ppm = {mk * 1e5:+.0f} mm "
                               "na 100 m) – jiný měřítkový koeficient nebo redukce délek.")
            elif math.hypot(mx, my) > tol_xy and max(sy_, sx_) < max(0.005, math.hypot(mx, my) * 0.3):
                out.append(f"Stanovisko {st}: všechny body jsou posunuté stejně (dY {my:+.3f}, dX {mx:+.3f} m) – "
                           "jiné souřadnice stanoviska.")
        if len(dzs) >= 3:
            mz, sz = _mean_std(dzs)
            if abs(mz) > tol_z and sz < max(0.005, abs(mz) * 0.3):
                out.append(f"Stanovisko {st}: všechny výšky se liší o {mz:+.3f} m – jiná výška stanoviska nebo "
                           "výška přístroje (zapomenutá / dvakrát započtená?).")
    # prohozená čísla bodů
    calc = [r for r in rows if r.vypocet is not None]
    for r in rows:
        if r.student is None or r.vypocet is None or (r.dxy or 0) <= 0.1:
            continue
        sa, sb = abs(r.student.a), abs(r.student.b)
        other = next((c for c in calc if c is not r and math.hypot(c.vypocet.y - sa, c.vypocet.x - sb) <= tol_xy * 2),
                     None)
        if other is not None:
            out.append(f"Bod {r.bod}: vaše souřadnice patří vypočtenému bodu {other.bod} – prohozená / překlepnutá "
                       "čísla bodů?")
    if not out and any((r.dxy or 0) > tol_xy for r in rows if r.vypocet is not None and r.student is not None):
        out.append("Rozdíly nemají společnou příčinu – jde o jednotlivé body (překlep v zápisníku nebo v čísle bodu, "
                   "špatně opsaná výška cíle). Porovnejte je v tabulce jednotlivě.")
    return out
