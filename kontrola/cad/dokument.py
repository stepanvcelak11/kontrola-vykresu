"""DXF dokument CAD: otevření (i poškozeného souboru), zpráva o načtení, uložení ve zvolené verzi."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing

# entity, které CAD umí zobrazit i upravovat (ostatní zobrazí jen ezdxf a beze změny je uloží zpět)
PODPOROVANE = {"POINT", "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "TEXT", "MTEXT",
               "HATCH", "INSERT", "DIMENSION", "SOLID", "IMAGE", "ATTRIB", "ATTDEF"}
VERZE = {"R12": "AC1009", "R2000": "AC1015", "R2004": "AC1018", "R2007": "AC1021", "R2010": "AC1024",
         "R2013": "AC1027", "R2018": "AC1032"}
NAZEV_VERZE = {v: k for k, v in VERZE.items()}


@dataclass
class ZpravaNacteni:
    verze: str = ""
    kodovani: str = ""
    pocty: Counter = field(default_factory=Counter)
    nezname: Counter = field(default_factory=Counter)  # typy entit, které CAD jen zachová
    opravy: list[str] = field(default_factory=list)  # co se při načtení opravilo (poškozený soubor)
    chyby: list[str] = field(default_factory=list)

    def text(self) -> str:
        r = [f"DXF {self.verze}, kódování {self.kodovani}, {sum(self.pocty.values())} prvků v modelu."]
        if self.nezname:
            r.append("Zachováno beze změny (CAD je zobrazí, ale neupravuje): "
                     + ", ".join(f"{k} {v}×" for k, v in self.nezname.most_common()))
        if self.opravy:
            r.append(f"Soubor byl poškozený – opraveno {len(self.opravy)} míst: " + "; ".join(self.opravy[:5])
                     + ("…" if len(self.opravy) > 5 else ""))
        if self.chyby:
            r.append("Nepodařilo se načíst: " + "; ".join(self.chyby[:5]))
        return "\n".join(r)


class CadDokument:
    def __init__(self, doc: Drawing | None = None, path: str | Path | None = None):
        self.doc = doc if doc is not None else self.novy_doc()
        self.path = Path(path) if path else None
        self.zprava = ZpravaNacteni()
        self.zmeneno = False
        self._souhrn()

    @staticmethod
    def novy_doc(verze: str = "R2000") -> Drawing:
        doc = ezdxf.new(verze, setup=True)
        doc.header["$INSUNITS"] = 6  # metry
        doc.header["$MEASUREMENT"] = 1
        _cesky(doc)
        return doc

    @classmethod
    def otevri(cls, path: str | Path) -> "CadDokument":
        """Otevře DXF; poškozený soubor se zkusí opravit (ezdxf.recover) a ve zprávě je, co se stalo."""
        p = Path(path)
        opravy: list[str] = []
        try:
            doc = ezdxf.readfile(p)
        except ezdxf.DXFStructureError:
            from ezdxf import recover
            try:
                doc, auditor = recover.readfile(p)
            except ezdxf.DXFStructureError as e:
                raise ValueError(f"Soubor {p.name} není čitelný DXF ({e}).") from None
            opravy = [str(f.message) for f in auditor.fixes] + [str(e.message) for e in auditor.errors]
        except OSError as e:
            raise ValueError(f"Soubor {p.name} nejde otevřít: {e}") from None
        except UnicodeDecodeError:
            raise ValueError(f"Soubor {p.name} má neznámé kódování textu.") from None
        _dekoduj_unicode(doc)
        d = cls(doc, p)
        d.zprava.opravy = opravy
        return d

    def _souhrn(self):
        z = self.zprava
        z.verze = NAZEV_VERZE.get(self.doc.dxfversion, self.doc.dxfversion)
        z.kodovani = getattr(self.doc, "encoding", "") or ""
        z.pocty = Counter(e.dxftype() for e in self.doc.modelspace())
        z.nezname = Counter({k: v for k, v in z.pocty.items() if k not in PODPOROVANE})

    @property
    def msp(self):
        return self.doc.modelspace()

    def uloz(self, path: str | Path | None = None, verze: str | None = None) -> Path:
        """Uloží DXF (ASCII). Verze jde jen zvýšit (např. R12 → R2000); nižší než původní se odmítne,
        aby se nic neztratilo. Zápis přes dočasný soubor – při chybě zůstane původní soubor celý."""
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("Výkres ještě nemá jméno – použijte Uložit jako.")
        if verze:
            cil = VERZE[verze]
            if cil < self.doc.dxfversion:
                raise ValueError(f"Výkres je ve verzi {NAZEV_VERZE.get(self.doc.dxfversion)} – uložit do starší "
                                 f"{verze} by znamenalo ztrátu dat.")
            if cil != self.doc.dxfversion:
                self.doc.dxfversion = cil
        _cesky(self.doc)
        import os
        import tempfile
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
        os.close(fd)
        try:
            self.doc.saveas(tmp)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self.path = p
        self.zmeneno = False
        return p

    def rozsah(self) -> tuple[float, float, float, float] | None:
        """Rozsah kresby (x0, y0, x1, y1) v souřadnicích DXF."""
        from ezdxf import bbox
        try:
            ext = bbox.extents(self.msp, fast=True)
        except Exception:  # noqa: BLE001
            return None
        if not ext.has_data:
            return None
        return ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y


def _cesky(doc: Drawing) -> None:
    """Verze do R2004 ukládají texty v kódové stránce: výchozí ANSI_1252 neumí č, ř, ě, ů… (ty by se zapsaly
    jako \\U+xxxx), proto česká ANSI_1250. R2007 a novější jsou v UTF-8."""
    if doc.dxfversion < "AC1021" and (doc.encoding or "").lower() in ("cp1252", ""):
        doc.encoding = "cp1250"


def _dekoduj_unicode(doc: Drawing) -> None:
    """Texty se zápisem \\U+xxxx (z programů, které neznají češtinu v kódové stránce) převede na znaky."""
    from ezdxf.lldxf.encoding import decode_dxf_unicode, has_dxf_unicode
    for e in doc.entitydb.values():
        for attr in ("text", "tag", "prompt"):
            try:
                if e.dxf.hasattr(attr):
                    v = e.dxf.get(attr)
                    if isinstance(v, str) and has_dxf_unicode(v):
                        e.dxf.set(attr, decode_dxf_unicode(v))
            except Exception:  # noqa: BLE001
                continue
    for layer in doc.layers:
        n = layer.dxf.name
        if has_dxf_unicode(n):
            try:
                layer.rename(decode_dxf_unicode(n))
            except Exception:  # noqa: BLE001
                pass


def sjtsk(x: float, y: float) -> tuple[float, float]:
    """DXF (x, y) → S-JTSK (Y, X): výkresy z MicroStationu mají souřadnice se znaménkem minus."""
    return -x, -y
