"""Opravný průvodce pro MicroStation: u každé chyby přesný postup s čísly (odkud kam, o kolik)
a příkazy (key-in) ke zkopírování. Opravuje student sám v DGN – aplikace nic nemění.

Pořadí chyb se skládá podle polohy (nejbližší další), aby se v MicroStationu nepřeskakovalo po mapě.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import Point
from shapely.ops import nearest_points

from .checks.base import Issue
from .navody import navod


@dataclass
class Krok:
    nadpis: str
    postup: list[str]
    keyins: list[tuple[str, str]] = field(default_factory=list)  # (popis, key-in)
    cil: tuple[float, float] | None = None


def xy(p) -> str:
    return f"{p[0]:.3f},{p[1]:.3f}"


def _m(v: float) -> str:
    if v < 0.01:
        return f"{v * 1000:.1f} mm".replace(".", ",")
    return f"{v * 1000:.0f} mm" if v < 0.1 else f"{v:.3f} m".replace(".", ",")


def _feats(iss: Issue, drawing):
    by_id = drawing.by_id() if drawing is not None else {}
    return [by_id[i] for i in iss.feature_ids if i in by_id]


def _line(f):
    g = f.geometry
    return g.boundary if g is not None and g.geom_type == "Polygon" else g


def _end_near(f, p):
    c = list(_line(f).coords)
    return min((c[0], c[-1]), key=lambda q: math.dist(q[:2], p))[:2]


def _snap_target(other, p, tol: float = 0.05):
    """Cíl na druhé čáře: její lomový bod, je-li blízko, jinak nejbližší bod na čáře."""
    g = _line(other)
    v = min(g.coords, key=lambda q: math.dist(q[:2], p))[:2]
    q = nearest_points(g, Point(p))[0]
    if math.dist(v, p) <= max(tol, math.dist((q.x, q.y), p) * 3):
        return v, True
    return (q.x, q.y), False


def krok(iss: Issue, drawing, tol: float = 0.01) -> Krok:
    p = (iss.x, iss.y)
    center = ("Vycentrovat pohled na chybu", f"WINDOW CENTER;XY={xy(p)}")
    feats = _feats(iss, drawing)
    lay = ", ".join(sorted({f.layer for f in feats})) or iss.layer
    low = iss.message.lower()
    obecne = navod(iss)
    k = Krok(iss.message, [], [center])
    try:
        if iss.check_id == "chybejici_napojeni" and len(feats) >= 2:
            f, other = feats[0], feats[1]
            end = _end_near(f, p)
            if "přetažen" in low:
                inter = _line(f).intersection(_line(other))
                pts = [g for g in getattr(inter, "geoms", [inter]) if g.geom_type == "Point"]
                tgt = min(((g.x, g.y) for g in pts), key=lambda q: math.dist(q, end)) if pts else p
                k.postup = [f"Čára na vrstvě {f.layer} přečnívá o {_m(math.dist(end, tgt))} přes čáru na vrstvě "
                            f"{other.layer}.",
                            "Upravit prvek (Modify Element) → klikněte na konec čáry.",
                            f"Nový konec zadejte přesně do průsečíku: přichycení Intersection, nebo v AccuDraw "
                            f"klávesa Enter → XY={xy(tgt)}.",
                            "Nebo nástroj Oříznout k prvku (Trim to Element): nejdřív hraniční čára, pak přečnívající "
                            "konec."]
            else:
                tgt, vertex = _snap_target(other, end, max(tol * 5, 0.05))
                k.postup = [f"Konec čáry na vrstvě {f.layer} chybí {_m(math.dist(end, tgt))} k čáře na vrstvě "
                            f"{other.layer}.",
                            "Upravit prvek (Modify Element) → klikněte na konec čáry "
                            f"(je v XY={xy(end)}).",
                            (f"Přetáhněte ho na lomový bod sousední čáry – přichycení Keypoint, nebo XY={xy(tgt)}."
                             if vertex else
                             f"Přetáhněte ho na sousední čáru – přichycení Nearest, nebo XY={xy(tgt)}."),
                            "Nebo Prodloužit prvek k průsečíku (Extend Element to Intersection)."]
            k.cil = tgt
            k.keyins.append(("Souřadnice cíle (vložte do AccuDraw / zadání bodu)", f"XY={xy(tgt)}"))
        elif iss.check_id == "pruseciky_bez_uzlu":
            k.postup = [f"Čáry ({lay}) se v XY={xy(p)} kříží nebo dotýkají bez společného uzlu.",
                        ("Rozdělit prvek (Break Element / Částečné smazání) – u obou čar klikněte přesně do "
                         "tohoto bodu s přichycením Intersection." if "rozdělen" in low or "průsečík" in low else
                         "Vložit vrchol (Insert Vertex) do čáry, na kterou druhá navazuje, přesně v tomto bodě."),
                        "Ověřte v Informacích o prvku, že obě čáry v bodě končí / mají vrchol."]
            k.cil = p
            k.keyins.append(("Souřadnice uzlu", f"XY={xy(p)}"))
        elif iss.check_id == "blizke_prvky" and len(feats) >= 2:
            tgt, vertex = _snap_target(feats[1], p, max(tol * 5, 0.05))
            k.postup = [f"Lomový bod čáry na vrstvě {feats[0].layer} je {_m(math.dist(p, tgt))} od čáry na vrstvě "
                        f"{feats[1].layer}, ale nedotýká se jí.",
                        f"Upravit prvek (Modify Element) → klikněte na lomový bod (XY={xy(p)}).",
                        f"Přesuňte ho na druhou čáru ({'přichycení Keypoint' if vertex else 'přichycení Nearest'}),"
                        f" nebo XY={xy(tgt)}. Pokud se čáry dotýkat nemají, odsuňte ho dál."]
            k.cil = tgt
            k.keyins.append(("Souřadnice cíle", f"XY={xy(tgt)}"))
        elif iss.check_id == "visici_konce" and feats:
            end = _end_near(feats[0], p)
            k.postup = [f"Konec čáry na vrstvě {feats[0].layer} v XY={xy(end)} nikam nenavazuje.",
                        "Má-li navazovat: Prodloužit prvek k průsečíku (Extend Element to Intersection), nebo "
                        "Upravit prvek s přichycením na sousední čáru.",
                        "Je-li to okraj kresby nebo záměr: v aplikaci Ignorovat."]
        elif iss.check_id == "seznam_souradnic" and iss.geometry is not None and iss.geometry.geom_type == \
                "LineString":
            a = iss.geometry.coords[0]
            k.postup = [f"Bod má podle seznamu ležet v XY={xy(a)}.",
                        "Přesunout (Move) → vyberte bod (a jeho popisy) → první bod: přichycení na bod, druhý bod: "
                        f"v AccuDraw Enter → XY={xy(a)}."]
            k.cil = (a[0], a[1])
            k.keyins.append(("Souřadnice ze seznamu", f"XY={xy(a)}"))
        elif iss.check_id in ("kratke_linie", "nulova_delka"):
            k.postup = [f"{iss.message} ({lay}).", "Vyberte ji (Tab přepíná mezi prvky na sobě) a smažte, nebo "
                        "spojte s navazující čárou (Create Complex Chain)."]
        elif iss.check_id == "duplicity":
            k.postup = [f"Dva stejné prvky na sobě ({lay}).",
                        "Výběr prvku → klik → Reset (pravé tlačítko) přepne na druhý prvek → Delete. Smažte jen jeden."]
    except Exception:  # noqa: BLE001 – geometrie, se kterou nejde počítat: jen obecný návod
        k.postup = []
    if obecne and not k.postup:
        k.postup = [obecne]
    elif obecne:
        k.postup.append("Obecně: " + obecne)
    if not k.postup:
        k.postup = [f"{iss.message} ({lay}) – najděte místo a opravte podle Směrnice."]
    return k


def poradi(issues: list[Issue]) -> list[Issue]:
    """Pořadí oprav: od levého horního rohu vždy k nejbližší další chybě (kratší cesta po mapě)."""
    rest = list(issues)
    if len(rest) < 3:
        return rest
    if len(rest) > 1500:  # velké výkresy: jen po pásech zleva doprava
        return sorted(rest, key=lambda i: (round(i.y / 50), i.x))
    cur = min(rest, key=lambda i: (i.x - i.y))
    out = [cur]
    rest.remove(cur)
    while rest:
        cur = min(rest, key=lambda i: (i.x - cur.x) ** 2 + (i.y - cur.y) ** 2)
        out.append(cur)
        rest.remove(cur)
    return out
