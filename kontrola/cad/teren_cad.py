"""Model terénu do výkresu: vrstevnice (základní a zesílené, s výškou jako elevation), popis zesílených
vrstevnic a volitelně TIN jako 3D plošky (3DFACE). Vše jedna operace – jedno Zpět."""

from __future__ import annotations

import math
import statistics

from ..geodezie import teren as T

VRSTVY = {"zakladni": "VRSTEVNICE_ZAKLADNI", "zesilena": "VRSTEVNICE_ZESILENE", "popis": "VRSTEVNICE_POPIS",
          "tin": "TIN"}
# hnědá jako na mapách; tloušťky jako v ÚM (základní 0,18, zesílená 0,35)
VYCHOZI = {"zakladni": {"color": 32, "lineweight": 18}, "zesilena": {"color": 32, "lineweight": 35},
           "popis": {"color": 32}, "tin": {"color": 8}}


def body_z_entit(ents) -> list[tuple[float, float, float]]:
    """Výškové body z výběru: POINT a vložené buňky (INSERT) s výškou z (3D), čáry vrcholy se z."""
    out = []
    for e in ents:
        t = e.dxftype()
        try:
            if t == "POINT":
                p = e.dxf.location
                out.append((p.x, p.y, p.z))
            elif t == "INSERT":
                p = e.dxf.insert
                out.append((p.x, p.y, p.z))
            elif t == "LWPOLYLINE":
                z = e.dxf.get("elevation", 0.0)
                out += [(x, y, z) for x, y in e.get_points("xy")]
            elif t == "POLYLINE":
                out += [(v.dxf.location.x, v.dxf.location.y, v.dxf.location.z) for v in e.vertices]
            elif t == "LINE":
                out += [(e.dxf.start.x, e.dxf.start.y, e.dxf.start.z), (e.dxf.end.x, e.dxf.end.y, e.dxf.end.z)]
        except (AttributeError, TypeError):
            continue
    return out


def automaticka_max_strana(body) -> float | None:
    """Doporučená max. délka strany TIN: 4× medián vzdálenosti k nejbližšímu sousedovi (odřízne dlouhé okraje)."""
    try:
        t = T.tin(body)
    except ValueError:
        return None
    hrany = []
    for a, b, c in t.trojuhelniky:
        for i, j in ((a, b), (b, c), (c, a)):
            hrany.append(math.dist(t.body[i][:2], t.body[j][:2]))
    return 4.0 * statistics.median(hrany) if hrany else None


def _vrstva(doc, nazev: str):
    if nazev not in doc.layers:
        doc.layers.add(nazev)
    return nazev


def kresli(doc, msp, h, model: T.ModelTerenu, *, tin: bool = False, popis: bool = True,
           vyska_textu: float = 1.5, vrstvy: dict | None = None, atributy: dict | None = None) -> list:
    """Vrstevnice (a TIN) do modelového prostoru. ``vrstvy``/``atributy`` přepíší výchozí hladiny a vzhled
    (podle zadání). Vrací nové prvky."""
    vr = dict(VRSTVY, **(vrstvy or {}))
    at = {k: dict(VYCHOZI[k], **((atributy or {}).get(k) or {})) for k in VYCHOZI}
    nove = []
    for v in model.vrstevnice:
        druh = "zesilena" if v.zesilena else "zakladni"
        body = v.body[:-1] if v.uzavrena else v.body
        if len(body) < 2:
            continue
        a = dict(at[druh], layer=_vrstva(doc, vr[druh]), elevation=v.z)
        texty, mezery = (_popis(msp, v, vyska_textu, dict(at["popis"], layer=_vrstva(doc, vr["popis"])))
                         if popis and v.zesilena and vyska_textu > 0 else ([], None))
        nove += texty
        if mezery is None:
            nove.append(msp.add_lwpolyline(body, format="xy", close=v.uzavrena, dxfattribs=a))
            continue
        # vrstevnice se pod popisem přeruší (jako na mapě)
        from shapely.geometry import LineString
        zbytek = LineString(v.body).difference(mezery)
        for g in getattr(zbytek, "geoms", [zbytek]):
            if g.geom_type == "LineString" and g.length > 0:
                nove.append(msp.add_lwpolyline(list(g.coords), format="xy", dxfattribs=a))
    if tin:
        a = dict(at["tin"], layer=_vrstva(doc, vr["tin"]))
        for i, j, k in model.tin.trojuhelniky:
            p, q, r = (model.tin.body[n] for n in (i, j, k))
            nove.append(msp.add_3dface([p, q, r, r], dxfattribs=a))
    if h is not None and nove:
        h.proved("Vrstevnice", nove)
    return nove


def _popis(msp, v: T.Vrstevnice, vyska: float, attrs: dict):
    """Výška zesílené vrstevnice na čáře, text ve směru vrstevnice a čitelně (nikdy vzhůru nohama).
    Vrací (texty, plocha mezer pro přerušení čáry)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    g = LineString(v.body)
    if g.length < 20 * vyska:
        return [], None
    out, mezery = [], []
    for f in ((0.5,) if g.length < 200 else (0.25, 0.75)):
        d = g.length * f
        p, q = g.interpolate(d - vyska), g.interpolate(d + vyska)
        u = math.degrees(math.atan2(q.y - p.y, q.x - p.x))
        if u > 90 or u < -90:
            u += 180
        s = g.interpolate(d)
        txt = f"{v.z:g}" if abs(v.z - round(v.z)) < 1e-6 else f"{v.z:.1f}"
        from ezdxf.enums import TextEntityAlignment
        e = msp.add_text(txt, height=vyska, rotation=u, dxfattribs=attrs)
        e.set_placement((s.x, s.y), align=TextEntityAlignment.MIDDLE_CENTER)
        out.append(e)
        mezery.append(Point(s.x, s.y).buffer(0.45 * vyska * len(txt) + 0.3 * vyska))
    return out, unary_union(mezery)


def souhrn(model: T.ModelTerenu) -> str:
    zmin, zmax = model.tin.rozsah_z()
    zes = sum(1 for v in model.vrstevnice if v.zesilena)
    return (f"TIN: {len(model.tin.body)} bodů, {len(model.tin.trojuhelniky)} trojúhelníků, plocha "
            f"{model.tin.plocha():.0f} m², výšky {zmin:.2f}–{zmax:.2f} m"
            + (f", vynecháno {model.tin.vynechane} bodů (bez výšky / duplicitní)" if model.tin.vynechane else "")
            + f". Vrstevnice po {model.interval:g} m: {len(model.vrstevnice)} čar, z toho {zes} zesílených.")


def kresli_profil(doc, msp, h, prof: list, pocatek, *, prevyseni: float = 10.0, srovnavaci: float | None = None,
                  krok_popisu: float = 10.0, vyska_textu: float = 1.5, vrstva: str = "PROFIL") -> list:
    """Podélný profil jako výkres: profil terénu, srovnávací rovina, staničení a výšky po ``krok_popisu``
    (a na konci), výšky převýšené ``prevyseni``×. Vrací nové prvky (jedna operace)."""
    from ezdxf.enums import TextEntityAlignment
    zs = [z for _s, z in prof if z is not None]
    if len(zs) < 2:
        raise ValueError("Trasa profilu neprochází modelem terénu.")
    if srovnavaci is None:
        srovnavaci = math.floor(min(zs)) - 1.0
    x0, y0 = pocatek
    delka = prof[-1][0]
    a = {"layer": _vrstva(doc, vrstva), "color": 7}
    nove = []

    def bod(s, z):
        return (x0 + s, y0 + (z - srovnavaci) * prevyseni)

    usek = []
    for s, z in prof + [(None, None)]:
        if z is None:
            if len(usek) >= 2:
                nove.append(msp.add_lwpolyline(usek, dxfattribs=dict(a, color=32, lineweight=35)))
            usek = []
        else:
            usek.append(bod(s, z))
    nove.append(msp.add_line((x0, y0), (x0 + delka, y0), dxfattribs=a))
    t = msp.add_text(f"S.R. {srovnavaci:.2f}", height=vyska_textu, dxfattribs=a)
    t.set_placement((x0 - vyska_textu, y0), align=TextEntityAlignment.MIDDLE_RIGHT)
    nove.append(t)
    popisy = []
    s = 0.0
    while s < delka - 1e-6:
        popisy.append(s)
        s += krok_popisu
    popisy.append(delka)
    for s in popisy:
        z = _vyska_na(prof, s)
        if z is None:
            continue
        x, y = bod(s, z)
        nove.append(msp.add_line((x, y0), (x, y), dxfattribs=dict(a, color=8)))
        ts = msp.add_text(_staniceni(s), height=vyska_textu, rotation=90, dxfattribs=a)
        ts.set_placement((x, y0 - 0.5 * vyska_textu), align=TextEntityAlignment.MIDDLE_RIGHT)
        tz = msp.add_text(f"{z:.2f}", height=vyska_textu, rotation=90, dxfattribs=a)
        tz.set_placement((x - 0.3 * vyska_textu, y0 + 0.5 * vyska_textu), align=TextEntityAlignment.BOTTOM_LEFT)
        nove += [ts, tz]
    pop = msp.add_text(f"Podélný profil – převýšení {prevyseni:g}×, délka {delka:.2f} m", height=1.5 * vyska_textu,
                       dxfattribs=a)
    pop.set_placement((x0, y0 + (max(zs) - srovnavaci) * prevyseni + 3 * vyska_textu))
    nove.append(pop)
    if h is not None:
        h.proved("Podélný profil", nove)
    return nove


def _staniceni(s: float) -> str:
    """Staničení jako v trasování: km,metry („0,025.00“)."""
    km, m = divmod(s, 1000.0)
    return f"{int(km)},{m:06.2f}"


def _vyska_na(prof, s):
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s0 - 1e-9 <= s <= s1 + 1e-9:
            if z0 is None or z1 is None:
                return z0 if abs(s - s0) < 1e-9 else (z1 if abs(s - s1) < 1e-9 else None)
            return z0 if s1 - s0 < 1e-12 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1] if prof and abs(s - prof[-1][0]) < 1e-9 else None
