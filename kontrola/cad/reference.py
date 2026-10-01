"""Reference (připojené výkresy) jako v MicroStationu: jiný DXF zobrazený pod výkresem, jen pro čtení.

Ve výkresu se reference ukládá standardně jako XREF (definice bloku s cestou k souboru + vložení
s polohou, měřítkem a natočením) – AutoCAD i jiné programy ji tak poznají. Obsah reference se načte
zvlášť; lze se na ni přichytávat a kopírovat z ní prvky do výkresu.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.math import Matrix44

MAX_UCHYTU = 60000  # u obřích podkladů se pro úchyty vezme jen tolik prvků


@dataclass
class Reference:
    nazev: str
    cesta: Path
    vlozeni: tuple[float, float] = (0.0, 0.0)
    meritko: float = 1.0
    natoceni: float = 0.0  # stupně proti směru hodin (DXF)
    viditelna: bool = True
    uchyty: bool = True
    doc: object | None = None
    chyba: str = ""
    inserty: list = field(default_factory=list)

    @property
    def pripojena(self) -> bool:
        """Vložení reference je ve výkresu (po odpojení / Zpět není)."""
        return any(i.dxf.owner is not None for i in self.inserty)

    @property
    def matice(self) -> Matrix44:
        return Matrix44.chain(Matrix44.scale(self.meritko, self.meritko, self.meritko),
                              Matrix44.z_rotate(math.radians(self.natoceni)),
                              Matrix44.translate(self.vlozeni[0], self.vlozeni[1], 0))

    def qt_matice(self) -> tuple[float, float, float, float, float, float]:
        """(m11, m12, m21, m22, dx, dy) pro QTransform."""
        s, t = self.meritko, math.radians(self.natoceni)
        c, n = s * math.cos(t), s * math.sin(t)
        return c, n, -n, c, self.vlozeni[0], self.vlozeni[1]

    def nacti(self) -> bool:
        try:
            try:
                self.doc = ezdxf.readfile(self.cesta)
            except ezdxf.DXFStructureError:
                from ezdxf import recover
                self.doc, _a = recover.readfile(self.cesta)
            from .dokument import _dekoduj_unicode
            _dekoduj_unicode(self.doc)  # „\U+010d“ → „č“ (podklady z programů bez české kódové stránky)
            self.chyba = ""
            return True
        except (OSError, ezdxf.DXFError, UnicodeDecodeError) as e:
            self.doc = None
            self.chyba = f"nejde načíst: {e}"
            return False

    def prvky_pro_uchyty(self) -> list:
        """Kopie prvků reference v souřadnicích výkresu (pro úchyty)."""
        if self.doc is None:
            return []
        out, m = [], self.matice
        for e in self.doc.modelspace():
            if len(out) >= MAX_UCHYTU:
                break
            if e.dxftype() not in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "POINT", "INSERT", "TEXT"):
                continue
            try:
                c = e.copy()
                c.transform(m)
                out.append(c)
            except Exception:  # noqa: BLE001 – prvek, který nejde kopírovat, se jen nepřichytí
                continue
        return out


def _relativni(cesta: Path, zaklad: Path | None) -> str:
    if zaklad is None:
        return str(cesta)
    try:
        return os.path.relpath(cesta, zaklad)
    except ValueError:  # jiný disk ve Windows
        return str(cesta)


def najdi(doc, zaklad: Path | None) -> list[Reference]:
    """Reference uložené ve výkresu (XREF bloky a jejich vložení v modelu)."""
    msp = doc.modelspace()
    out = []
    for blk in doc.blocks:
        try:
            if not blk.block_record.is_xref:
                continue
            p = Path(blk.block.dxf.get("xref_path", "") or "")
        except Exception:  # noqa: BLE001
            continue
        if not p.is_absolute() and zaklad is not None:
            p = (zaklad / p).resolve()
        ins = [e for e in msp.query("INSERT") if e.dxf.name == blk.name]
        r = Reference(blk.name, p, inserty=ins)
        if ins:
            i = ins[0]
            r.vlozeni = (i.dxf.insert.x, i.dxf.insert.y)
            r.meritko = float(i.dxf.get("xscale", 1.0))
            r.natoceni = float(i.dxf.get("rotation", 0.0))
        r.nacti()
        out.append(r)
    return out


def pripoj(doc, h, cesta: str | Path, zaklad: Path | None = None, vlozeni=(0.0, 0.0), meritko: float = 1.0,
           natoceni: float = 0.0, nazev: str | None = None) -> Reference:
    """Připojí DXF jako referenci (zápis XREF do výkresu, vložení jde vrátit Zpět)."""
    p = Path(cesta).resolve()
    if p.suffix.lower() != ".dxf":
        raise ValueError("Referenci jde připojit jen jako výkres DXF.")
    if not p.exists():
        raise ValueError(f"Soubor {p.name} neexistuje.")
    if meritko <= 0:
        raise ValueError("Měřítko reference musí být kladné.")
    jm = nazev or "REF_" + "".join(ch if ch.isalnum() else "_" for ch in p.stem)
    base, n = jm, 2
    while jm in doc.blocks:
        jm, n = f"{base}_{n}", n + 1
    r = Reference(jm, p, (float(vlozeni[0]), float(vlozeni[1])), meritko, natoceni)
    if not r.nacti():
        raise ValueError(f"Reference {p.name} {r.chyba}")
    doc.add_xref_def(_relativni(p, zaklad), jm)
    ins = doc.modelspace().add_blockref(jm, r.vlozeni, dxfattribs={"xscale": meritko, "yscale": meritko,
                                                                    "zscale": meritko, "rotation": natoceni})
    r.inserty = [ins]
    if h is not None:
        h.proved(f"Reference {p.name}", [ins])
    return r


def odpoj(doc, h, r: Reference) -> None:
    """Odpojí referenci: smaže vložení (jde vrátit Zpět); definice XREF zůstane jen při Zpět."""
    ins = [e for e in r.inserty if e.dxf.owner is not None]
    if h is not None and ins:
        h.proved(f"Odpojení {r.cesta.name}", [], ins)


def kopiruj(msp, h, r: Reference, prvky=None) -> list:
    """Zkopíruje prvky z reference do výkresu (v souřadnicích výkresu)."""
    if r.doc is None:
        raise ValueError("Reference není načtená.")
    zdroj = list(prvky) if prvky is not None else list(r.doc.modelspace())
    m, nove = r.matice, []
    for e in zdroj:
        if e.dxftype() == "INSERT":
            try:
                parts = list(e.virtual_entities())
            except Exception:  # noqa: BLE001
                continue
        else:
            parts = [e]
        for v in parts:
            try:
                c = v.copy()
                c.transform(m)
            except Exception:  # noqa: BLE001
                continue
            if c.dxf.hasattr("layer") and c.dxf.layer not in msp.doc.layers:
                msp.doc.layers.add(c.dxf.layer)
            if c.dxf.hasattr("linetype") and c.dxf.linetype not in msp.doc.linetypes:
                lt = r.doc.linetypes.get(c.dxf.linetype) if c.dxf.linetype in r.doc.linetypes else None
                try:
                    if lt is None:
                        raise ValueError
                    msp.doc.linetypes.add(c.dxf.linetype, pattern=lt.pattern_tags.tags and
                                          [t.value for t in lt.pattern_tags.tags if t.code in (40, 49)],
                                          description=lt.dxf.get("description", ""))
                except Exception:  # noqa: BLE001 – neznámý vzor → plná čára
                    c.dxf.linetype = "CONTINUOUS"
            if c.dxf.hasattr("style") and c.dxftype() in ("TEXT", "MTEXT") and c.dxf.style not in msp.doc.styles:
                c.dxf.style = "Standard"
            try:
                msp.add_foreign_entity(c, copy=False)  # prvek z jiného výkresu
            except Exception:  # noqa: BLE001 – typ, který nejde převést mezi výkresy
                continue
            nove.append(c)
    if h is not None and nove:
        h.proved(f"Kopie z reference {r.cesta.name}", nove)
    return nove
