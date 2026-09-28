"""Čtení VFK (výměnný formát katastru nemovitostí) jako výkresu – pro práci s daty z KN (Kokeš).

VFK je textový soubor s bloky: ``&B<NÁZEV>;SLOUPEC typ;…`` (hlavička bloku) a ``&D<NÁZEV>;hodnota;…``
(řádky dat). Kresba se skládá z:

* SOBR – souřadnice bodů (ID, CISLO_ZPMZ, CISLO_BODU, SOURADNICE_Y, SOURADNICE_X),
* SBP – spojení bodů do linií (BP_ID → SOBR, PORADOVE_CISLO_BODU, HP_ID / OB_ID / DPM_ID),
* HP – hranice parcel, OB – obvody budov, DPM – další prvky mapy,
* PAR + OBDEBO – čísla parcel a jejich definiční body.

Souřadnice S-JTSK jsou ve VFK kladné; výkres z MicroStationu je má záporné (−Y, −X),
proto se převádějí stejně, aby šel VFK položit pod výkres nebo porovnat se vzorem.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point

from ..model import Drawing, Feature, GeomType, LayerInfo

LAYERS = {"HP": ("KN-hranice parcel", 7, (255, 255, 255)),
          "OB": ("KN-budovy", 1, (255, 0, 0)),
          "DPM": ("KN-vnitřní kresba", 3, (0, 255, 0)),
          "SOBR": ("KN-body", 2, (255, 255, 0)),
          "PAR": ("KN-čísla parcel", 4, (0, 255, 255))}


def _encoding(raw: bytes) -> str:
    head = raw[:4000].decode("latin-1", "replace").upper()
    if "EE8MSWIN1250" in head or "WIN1250" in head:
        return "cp1250"
    if "8859P2" in head or "8859-2" in head:
        return "iso-8859-2"
    return "cp1250"


def _split(line: str) -> list[str]:
    out, cur, quoted = [], [], False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == ";" and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def read_blocks(path: str | Path, wanted: set[str]) -> dict[str, list[dict[str, str]]]:
    raw = Path(path).read_bytes()
    text = raw.decode(_encoding(raw), "replace")
    cols: dict[str, list[str]] = {}
    data: dict[str, list[dict[str, str]]] = defaultdict(list)
    pending = ""
    for line in text.splitlines():
        line = pending + line.rstrip("\r")
        if line.endswith("¤"):  # pokračování řádku
            pending = line[:-1]
            continue
        pending = ""
        if line.startswith("&B"):
            parts = _split(line[2:])
            cols[parts[0]] = [p.split(" ")[0].strip() for p in parts[1:]]
        elif line.startswith("&D"):
            parts = _split(line[2:])
            name = parts[0]
            if name in wanted and name in cols:
                data[name].append(dict(zip(cols[name], parts[1:])))
    return data


def _num(v: str | None) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def read_vfk(path: str | Path, progress=None) -> Drawing:
    path = Path(path)
    blocks = read_blocks(path, {"SOBR", "SBP", "HP", "OB", "DPM", "PAR", "OBDEBO"})
    if not blocks.get("SOBR"):
        from .dxf_loader import DrawingLoadError
        raise DrawingLoadError(f"{path.name}: ve VFK nejsou souřadnice bodů (blok SOBR) – nejde z něj udělat kresbu.")
    d = Drawing(path=str(path))
    fid = 0

    def add(kind, geom_type, geom, dxftype, **kw):
        nonlocal fid
        layer, aci, rgb = LAYERS[kind]
        coords = list(geom.coords) if geom.geom_type != "Point" else [(geom.x, geom.y)]
        f = Feature(fid=fid, dxftype=dxftype, geom_type=geom_type, geometry=geom, layer=layer, color_aci=aci,
                    color_rgb=rgb, handle=f"VFK{fid}", vertices=[tuple(c[:2]) for c in coords], **kw)
        d.features.append(f)
        info = d.layers.setdefault(layer, LayerInfo(name=layer, color_aci=aci, color_rgb=rgb))
        info.count += 1
        fid += 1

    pts: dict[str, tuple[float, float]] = {}
    for r in blocks["SOBR"]:
        y, x = _num(r.get("SOURADNICE_Y")), _num(r.get("SOURADNICE_X"))
        if y is None or x is None:
            continue
        pts[r.get("ID", "")] = (-y, -x)
        num = r.get("CISLO_BODU", "")
        zpmz = r.get("CISLO_ZPMZ", "")
        add("SOBR", GeomType.BOD, Point(-y, -x), "POINT",
            attributes={"CISLO_BODU": num, "CISLO_ZPMZ": zpmz})
    if progress:
        progress(40, "VFK: spojuji body do linií…")
    lines: dict[tuple[str, str], list[tuple[float, str]]] = defaultdict(list)
    for r in blocks.get("SBP", []):
        bp = pts.get(r.get("BP_ID", ""))
        if bp is None:
            continue
        order = _num(r.get("PORADOVE_CISLO_BODU")) or 0.0
        for kind, key in (("HP", "HP_ID"), ("OB", "OB_ID"), ("DPM", "DPM_ID")):
            if r.get(key):
                lines[(kind, r[key])].append((order, r["BP_ID"]))
    for (kind, _id), seq in lines.items():
        coords = [pts[b] for _, b in sorted(seq)]
        if len(coords) >= 2:
            add(kind, GeomType.LINIE, LineString(coords), "LWPOLYLINE")
    # čísla parcel v definičních bodech
    par = {r.get("ID"): r for r in blocks.get("PAR", [])}
    for r in blocks.get("OBDEBO", []):
        p = par.get(r.get("PAR_ID"))
        y, x = _num(r.get("SOURADNICE_Y")), _num(r.get("SOURADNICE_X"))
        if p is None or y is None or x is None:
            continue
        kmen, pod = p.get("KMENOVE_CISLO_PAR", ""), p.get("PODDELENI_CISLA_PAR", "")
        label = kmen + (f"/{pod}" if pod else "")
        add("PAR", GeomType.TEXT, Point(-y, -x), "TEXT", text=label, text_height=1.5)
    if progress:
        progress(100, "Hotovo")
    d.warnings.append(f"VFK: {len(pts)} bodů, {len(lines)} linií (hranice parcel, budovy, vnitřní kresba).")
    return d
