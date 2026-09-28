"""Kontrola výkresu proti seznamu souřadnic (bodů) z měření.

Seznam je textový soubor ``číslo  Y  X  Z`` (případně ``číslo X Y Z``) – např. výstup z Gromy.
Kontrola hledá:

* body ze seznamu, které ve výkresu chybí nebo jsou posunuté,
* čísla bodů (text u bodu), která nesouhlasí se seznamem,
* výšky bodů (text s výškou u bodu), které nesouhlasí se seznamem (zaokrouhlení na cm).

Osy a znaménka souřadnic (S-JTSK kladně / záporně, prohozené Y a X) se zjistí samy podle toho,
která varianta nejlépe sedí na body ve výkresu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from ..model import GeomType
from .base import Check, CheckContext, Param, Severity, fmt_m, fmt_num, register


@dataclass
class ListPoint:
    cislo: str
    a: float
    b: float
    z: float | None


_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_LINE = re.compile(rf"^\s*(\S+)[\s;,]+({_NUM})[\s;,]+({_NUM})(?:[\s;,]+({_NUM}))?")


def read_point_list(path: str | Path) -> list[ListPoint]:
    """Načte seznam souřadnic (číslo, dvě souřadnice, volitelně výška). Hlavičky a poznámky přeskočí."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    out = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m or not re.search(r"\d", m.group(1)):
            continue
        f = lambda s: float(s.replace(",", "."))  # noqa: E731
        try:
            a, b = f(m.group(2)), f(m.group(3))
        except ValueError:
            continue
        if abs(a) < 1 and abs(b) < 1:
            continue
        z = f(m.group(4)) if m.group(4) else None
        out.append(ListPoint(m.group(1), a, b, z))
    return out


def short_numbers(cislo: str) -> set[str]:
    """Podoby čísla bodu, jak ho píše výkres: 610844000130001 → {„610844000130001“, „1“, „130001“, „13-1“}."""
    c = cislo.strip()
    out = {c}
    digits = re.sub(r"\D", "", c)
    if len(digits) >= 5:
        cis = str(int(digits[-4:]))
        out.add(cis)
        zpmz = digits[-8:-4] if len(digits) >= 8 else ""
        if zpmz and int(zpmz):
            out.add(f"{int(zpmz)}-{cis}")
            out.add(f"{int(zpmz)}{int(digits[-4:]):04d}")
    elif digits:
        out.add(str(int(digits)))
    return out


_TRANSFORMS = {
    "Y, X (záporně)": lambda a, b: (-a, -b),
    "Y, X": lambda a, b: (a, b),
    "X, Y (záporně)": lambda a, b: (-b, -a),
    "X, Y": lambda a, b: (b, a),
}


@register
class SeznamSouradnic(Check):
    id = "seznam_souradnic"
    nazev = "Seznam souřadnic"
    skupina = "Atributy"
    popis = ("Porovná výkres se seznamem souřadnic z měření (Zadání → Podklady → Seznam souřadnic): "
             "chybějící nebo posunuté body, čísla bodů a výšky bodů u bodů.")
    vychozi_zavaznost = Severity.CHYBA
    parametry = [
        Param("tolerance_polohy", "Tolerance polohy bodu [m]", "float", 0.01,
              "Bod ve výkresu smí být od souřadnic ze seznamu nejvýš takto daleko."),
        Param("hledat_do", "Posunutý bod hledat do [m]", "float", 0.5),
        Param("okruh_popisu", "Číslo a výšku bodu hledat do [m]", "float", 3.0,
              "Správné číslo nebo výška v tomto okruhu = v pořádku. Jinak se porovná text, který je "
              "k bodu nejblíž."),
        Param("kontrolovat_cisla", "Kontrolovat čísla bodů", "bool", True),
        Param("kontrolovat_vysky", "Kontrolovat výšky bodů", "bool", True),
    ]

    def run(self, ctx: CheckContext):
        path = getattr(ctx.config, "seznam_souradnic", "") or ""
        if not path or not Path(path).is_file():
            return
        pts = read_point_list(path)
        if not pts:
            ctx.notes.append(f"seznam souřadnic {Path(path).name} neobsahuje žádné body.")
            return
        feats = [f for f in ctx.features() if f.geom_type == GeomType.BOD and f.dxftype != "TEXT"]
        if not feats:
            return
        tol = float(ctx.param("tolerance_polohy", 0.01))
        far = float(ctx.param("hledat_do", 0.5))
        radius = float(ctx.param("okruh_popisu", 1.0))
        geoms = np.array([f.geometry for f in feats], dtype=object)
        tree = shapely.STRtree(geoms)

        # které natočení os sedí nejlépe
        best, best_n = None, -1
        sample = pts[:: max(1, len(pts) // 60)]
        for name, tr in _TRANSFORMS.items():
            q = [Point(*tr(p.a, p.b)) for p in sample]
            _, hit = tree.query(np.array(q, dtype=object), predicate="dwithin", distance=far)
            n = len(set(_.tolist())) if len(_) else 0
            if n > best_n:
                best, best_n = name, n
        if best_n <= 0:
            ctx.notes.append(f"seznam souřadnic {Path(path).name}: žádný bod ze seznamu neleží ve výkresu – "
                             "je to seznam k tomuto výkresu?")
            return
        tr = _TRANSFORMS[best]

        texts = [f for f in ctx.features() if f.geom_type == GeomType.TEXT and f.text]
        num_texts = [t for t in texts if re.fullmatch(r"\d+(?:-\d+)?", t.text.strip())]
        h_texts = [t for t in texts if re.fullmatch(r"\d+[.,]\d{1,3}", t.text.strip())]
        num_tree = shapely.STRtree(np.array([t.geometry for t in num_texts], dtype=object)) if num_texts else None
        h_tree = shapely.STRtree(np.array([t.geometry for t in h_texts], dtype=object)) if h_texts else None
        have_z = any(p.z not in (None, 0.0) for p in pts)
        do_num = bool(ctx.param("kontrolovat_cisla", True)) and num_tree is not None
        do_h = bool(ctx.param("kontrolovat_vysky", True)) and have_z and h_tree is not None

        # každý text s číslem patří k nejbližšímu bodu ze seznamu (u hustých bodů je popis blíž sousedovi)
        lp = np.array([Point(*tr(p.a, p.b)) for p in pts], dtype=object)
        lp_tree = shapely.STRtree(lp)
        owner: dict[int, list] = {}
        h_owner: dict[int, list] = {}
        for texts_, own in ((num_texts if do_num else [], owner), (h_texts if do_h else [], h_owner)):
            for t in texts_:
                j = lp_tree.nearest(t.geometry)
                if j is not None and t.geometry.distance(lp[j]) <= min(radius, 1.5):
                    own.setdefault(int(j), []).append(t)

        found = 0
        for i, p in enumerate(pts):
            if i % 200 == 0:
                ctx.progress(i / len(pts))
            x, y = tr(p.a, p.b)
            here = Point(x, y)
            idx = tree.query(here, predicate="dwithin", distance=far)
            names = short_numbers(p.cislo)
            label = min(names, key=len)
            if len(idx) == 0:
                yield ctx.issue(self, None, f"Bod č. {label} ze seznamu ve výkresu chybí", at=(x, y))
                continue
            d = min(here.distance(geoms[j]) for j in idx)
            nearest = feats[min(idx, key=lambda j: here.distance(geoms[j]))]
            if d > tol:
                yield ctx.issue(self, nearest, f"Bod č. {label} je posunutý o {fmt_m(d)} proti seznamu",
                                at=(x, y), geometry=LineString([here, nearest.geometry]))
                continue
            found += 1
            if do_num:
                near = [num_texts[j] for j in num_tree.query(here, predicate="dwithin", distance=radius)]
                if not any(t.text.strip() in names for t in near):
                    mine = owner.get(i, [])
                    if mine:
                        t = min(mine, key=lambda t: here.distance(t.geometry))
                        yield ctx.issue(self, t, f"Číslo bodu: ve výkresu „{t.text.strip()}“, v seznamu {label}",
                                        at=(x, y))
            if do_h and p.z not in (None, 0.0):
                def ok(t):
                    v = t.text.strip().replace(",", ".")
                    dec = len(v.split(".")[1])
                    return abs(round(p.z, dec) - float(v)) <= 10 ** -dec / 2
                near = [h_texts[j] for j in h_tree.query(here, predicate="dwithin", distance=radius)]
                mine = [t for t in h_owner.get(i, []) if abs(float(t.text.replace(",", ".")) - p.z) < 5]
                if mine and not any(ok(t) for t in near):
                    t = min(mine, key=lambda t: here.distance(t.geometry))
                    val = float(t.text.replace(",", "."))
                    dec = len(t.text.strip().replace(",", ".").split(".")[1])
                    if True:
                        yield ctx.issue(self, t, f"Výška bodu č. {label}: ve výkresu {fmt_num(val, dec)}, "
                                                 f"v seznamu {fmt_num(round(p.z, dec), dec)}", at=(x, y))
        ctx.notes.append(f"seznam {Path(path).name}: {len(pts)} bodů, ve výkresu nalezeno {found} "
                         f"(souřadnice {best}).")
