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
        self.ms_barvy: dict[str, int] = {}  # handle → barva MicroStationu (z DGN)
        self.souhrn_dgn = None  # souhrn posledního uložení do DGN
        self._souhrn()

    @staticmethod
    def novy_doc(verze: str = "R2000") -> Drawing:
        doc = ezdxf.new(verze, setup=True)
        doc.header["$INSUNITS"] = 6  # metry
        doc.header["$MEASUREMENT"] = 1
        _cesky(doc)
        return doc

    @classmethod
    def otevri(cls, path: str | Path, rs=None) -> "CadDokument":
        """Otevře DXF; poškozený soubor se zkusí opravit (ezdxf.recover) a ve zprávě je, co se stalo."""
        p = Path(path)
        if p.suffix.lower() in (".dgn", ".dgnlib"):  # .dgnlib = knihovna hladin a stylů (DGN V8)
            return cls._otevri_dgn(p, rs)
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

    @classmethod
    def _otevri_dgn(cls, p: Path, rs=None) -> "CadDokument":
        """DGN V7 (i uložený z CAD) přímo s buňkami; DGN V8 přes vlastní čtení (buňky jako značky)."""
        from ..io.dgn import dgn_version
        verze = dgn_version(p)
        if verze == "V7":
            from ..io.dgn_v7 import DgnV7Error, do_ezdxf
            try:
                doc, ms_barvy, pozn = do_ezdxf(p, rs)
            except (DgnV7Error, OSError) as e:
                raise ValueError(f"{p.name}: {e}") from None
        elif verze == "V8":
            doc, ms_barvy, pozn = _v8_do_ezdxf(p, rs)
        else:
            raise ValueError(f"{p.name} není výkres DGN.")
        d = cls(doc, p)
        d.ms_barvy = ms_barvy
        d.zprava.opravy = pozn
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

    def uloz(self, path: str | Path | None = None, verze: str | None = None, rs=None,
             ms_barvy: dict | None = None) -> Path:
        """Uloží DXF (ASCII). Verze jde jen zvýšit (např. R12 → R2000); nižší než původní se odmítne,
        aby se nic neztratilo. Zápis přes dočasný soubor – při chybě zůstane původní soubor celý."""
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("Výkres ještě nemá jméno – použijte Uložit jako.")
        if p.suffix.lower() == ".dgn":  # MicroStation: DGN V7 (hladiny, barvy, tloušťky, styly, buňky)
            from .export_dgn import exportuj
            self.souhrn_dgn = exportuj(self.doc, self.doc.modelspace(), p, rs, ms_barvy)
            self.path = p
            self.zmeneno = False
            return p
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

    def uloz_kopii(self, path: str | Path) -> Path:
        """Záložní kopie (automatické ukládání): cesta výkresu ani příznak změny se nemění."""
        import os
        import tempfile
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        jmeno = self.doc.filename
        fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
        os.close(fd)
        try:
            self.doc.saveas(tmp)
            os.replace(tmp, p)
        finally:
            self.doc.filename = jmeno
            if os.path.exists(tmp):
                os.unlink(tmp)
        return p

    def rozsah(self) -> tuple[float, float, float, float] | None:
        """Rozsah kresby (x0, y0, x1, y1) v souřadnicích DXF.

        Běžné prvky se počítají přímo z jejich bodů (rychle i pro desítky tisíc prvků), jen složité
        (bloky, kóty, šrafy…) přes obálku ezdxf. Pro texty stačí bod vložení – jde o rozsah pro zoom."""
        from ezdxf import bbox
        xs, ys, slozite = [], [], []
        for e in self.msp:
            t = e.dxftype()
            try:
                if t == "LINE":
                    xs += (e.dxf.start.x, e.dxf.end.x)
                    ys += (e.dxf.start.y, e.dxf.end.y)
                elif t == "POINT":
                    xs.append(e.dxf.location.x)
                    ys.append(e.dxf.location.y)
                elif t in ("CIRCLE", "ARC"):
                    c, r = e.dxf.center, e.dxf.radius
                    xs += (c.x - r, c.x + r)
                    ys += (c.y - r, c.y + r)
                elif t == "LWPOLYLINE":
                    for x, y in e.get_points("xy"):
                        xs.append(x)
                        ys.append(y)
                elif t in ("TEXT", "MTEXT"):
                    xs.append(e.dxf.insert.x)
                    ys.append(e.dxf.insert.y)
                elif t == "VIEWPORT":
                    continue
                else:
                    slozite.append(e)
            except Exception:  # noqa: BLE001
                slozite.append(e)
        if slozite:
            try:
                ext = bbox.extents(slozite, fast=True)
                if ext.has_data:
                    xs += (ext.extmin.x, ext.extmax.x)
                    ys += (ext.extmin.y, ext.extmax.y)
            except Exception:  # noqa: BLE001
                pass
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)


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


def hladiny_v8(p: Path) -> list[str]:
    """Názvy všech hladin z tabulky hladin DGN V8 / .dgnlib (i nepoužitých); chyba → prázdný seznam."""
    import olefile

    from ..io.dgn_v8 import _levels
    try:
        o = olefile.OleFileIO(str(p))
    except OSError:
        return []
    try:
        jm = list(dict.fromkeys(n for n in _levels(o).values() if n and n.isprintable()))
    except Exception:  # noqa: BLE001
        jm = []
    finally:
        o.close()
    return jm


def _v8_do_ezdxf(p: Path, rs=None):
    """DGN V8 → ezdxf pro úpravy v CAD: čáry, plochy, oblouky (jako lomené čáry), texty a buňky jako
    vložené bloky (kresba buňky se z výkresu V8 nečte – blok je značka bodu, kresbu doplní knihovna .CEL)."""
    from ..io.dgn_v8 import DgnError, read_dgn
    from ..model import GeomType
    from . import symbologie as SY
    try:
        d = read_dgn(p)
    except (DgnError, OSError) as e:
        raise ValueError(f"{p.name}: {e}") from None
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 6
    SY.zajisti_styly(doc)
    msp = doc.modelspace()
    ms_barvy: dict[str, int] = {}
    for jm in hladiny_v8(p):  # všechny hladiny jako ve Správci vrstev MicroStationu (i prázdné ze seedu)
        if jm not in doc.layers:
            doc.layers.add(jm)
    for f in d.features:
        if f.layer not in doc.layers:
            doc.layers.add(f.layer)
        a = {"layer": f.layer}
        mb = f.attributes.get("MS_BARVA")
        if mb is not None:
            try:
                a["color"] = SY.ms_na_aci(int(mb), rs)
            except ValueError:
                pass
        if f.geom_type != GeomType.TEXT:
            wt = f.attributes.get("MS_TLOUSTKA")
            if wt is not None and wt.isdigit() and int(wt) <= 31:
                a["lineweight"] = SY.wt_na_lw(int(wt), rs)[0]
            st = f.attributes.get("MS_STYL", "0")
            if st.lstrip("-").isdigit() and 0 <= int(st) <= 7:
                a["linetype"] = SY.styl_na_typ(st)
            elif st.startswith("-") and (f.linetype or "").strip():
                # vlastní styl MicroStationu (ploty, zdi…) – jméno ponechat, CAD ho nakreslí z knihovny .rsc
                jm = f.linetype.strip()
                if jm not in doc.linetypes:
                    try:
                        doc.linetypes.add(jm, pattern=[0.0], description=f"styl MicroStationu {jm}")
                    except Exception:  # noqa: BLE001 – neplatné jméno pro DXF
                        jm = None
                if jm:
                    a["linetype"] = jm
        g = f.geometry
        if f.dxftype == "INSERT" and f.block_name:
            jm = f.block_name
            if jm not in doc.blocks:
                doc.blocks.new(jm).add_point((0, 0))
            e = msp.add_blockref(jm, (g.x, g.y), dxfattribs={**a, "rotation": f.rotation or 0.0,
                                                             "xscale": f.scale[0] or 1.0, "yscale": f.scale[1] or 1.0})
        elif f.geom_type == GeomType.TEXT:
            e = msp.add_text(f.text or "", height=f.text_height or 1.0, rotation=f.rotation or 0.0,
                             dxfattribs={**a, "width": f.width_factor or 1.0})
            from ezdxf.enums import TextEntityAlignment as TA
            al = {(0, 0): TA.LEFT, (0, 1): TA.BOTTOM_LEFT, (0, 2): TA.MIDDLE_LEFT, (0, 3): TA.TOP_LEFT,
                  (1, 0): TA.CENTER, (1, 1): TA.BOTTOM_CENTER, (1, 2): TA.MIDDLE_CENTER, (1, 3): TA.TOP_CENTER,
                  (2, 0): TA.RIGHT, (2, 1): TA.BOTTOM_RIGHT, (2, 2): TA.MIDDLE_RIGHT, (2, 3): TA.TOP_RIGHT}
            e.set_placement((g.x, g.y), align=al.get((f.halign, f.valign), TA.LEFT))
        elif f.geom_type == GeomType.BOD:
            e = msp.add_point((g.x, g.y), dxfattribs=a)
        elif f.geom_type == GeomType.POLYGON:
            pts = [tuple(c[:2]) for c in g.exterior.coords][:-1]
            e = msp.add_lwpolyline(pts, close=True, dxfattribs=a)
        else:
            pts = [tuple(c[:2]) for c in g.coords]
            e = msp.add_line(pts[0], pts[1], dxfattribs=a) if len(pts) == 2 else \
                msp.add_lwpolyline(pts, dxfattribs=a)
        if mb is not None and mb.isdigit():
            ms_barvy[e.dxf.handle] = int(mb)
    pozn = list(d.warnings)
    if any(f.dxftype == "INSERT" for f in d.features):
        pozn.append("Buňky z DGN V8 jsou jen značky bodu – kresbu načtete příkazem „knihovna buněk“ (.CEL).")
    return doc, ms_barvy, pozn
