"""Časová osa výkresu: při každé kontrole změněného výkresu se uloží komprimovaný snímek DXF do projektu.

Ze snímků jde výkres „přehrát“, porovnat s dneškem, zjistit, kdy chyba přibyla, a vytáhnout
omylem smazané prvky do samostatného DXF (vlastní práce – zkopírujete ji zpět v MicroStationu).
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import shutil
import tempfile
from pathlib import Path

MAX_SNIMKU = 60
MAX_MB = 300


def _hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshots(project) -> list[dict]:
    return list(project.meta.get("casova_osa", [])) if project is not None else []


def snapshot(project, drawing_path: str | Path, stats: dict | None = None) -> dict | None:
    """Uloží snímek, pokud se výkres od posledního snímku změnil. Vrací nový záznam nebo None."""
    if project is None:
        return None
    src = Path(drawing_path)
    if not src.is_file() or src.suffix.lower() != ".dxf":
        return None
    digest = _hash(src)
    osa = project.meta.setdefault("casova_osa", [])
    if osa and osa[-1].get("hash") == digest:
        osa[-1].update(stats or {})  # stejný výkres – jen aktualizovat počty z poslední kontroly
        return None
    d = project.root / "historie"
    d.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    name = f"{now:%Y%m%d_%H%M%S}_{src.stem}.dxf.gz"
    k = 1
    while (d / name).exists():  # dvě verze ve stejné sekundě
        k += 1
        name = f"{now:%Y%m%d_%H%M%S}_{k}_{src.stem}.dxf.gz"
    with open(src, "rb") as fi, gzip.open(d / name, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)
    rec = {"cas": now.isoformat(timespec="seconds"), "soubor": f"historie/{name}", "hash": digest,
           "nazev": src.name, **(stats or {})}
    osa.append(rec)
    _prune(project)
    return rec


def _prune(project):
    osa = project.meta.get("casova_osa", [])

    def size() -> int:
        return sum((project.root / r["soubor"]).stat().st_size for r in osa if (project.root / r["soubor"]).is_file())
    # první snímek (začátek práce) se nechává vždy
    while len(osa) > MAX_SNIMKU or (len(osa) > 2 and size() > MAX_MB * 1024 * 1024):
        r = osa.pop(1)
        try:
            (project.root / r["soubor"]).unlink()
        except OSError:
            pass


def extract(project, rec: dict, out: str | Path | None = None) -> Path:
    """Rozbalí snímek do DXF (do dočasné složky, nebo do ``out``)."""
    src = project.root / rec["soubor"]
    if out is None:
        out = Path(tempfile.mkdtemp(prefix="kontrola_snimek_")) / rec.get("nazev", "snimek.dxf")
    out = Path(out)
    with gzip.open(src, "rb") as fi, open(out, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    return out


def export_removed(old_dxf: str | Path, handles: list[str], out: str | Path) -> int:
    """Prvky ze starší verze (podle handle) do nového DXF – se stejnými vrstvami, barvami a styly."""
    import ezdxf
    from ezdxf.addons import Importer
    src = ezdxf.readfile(old_dxf)
    tgt = ezdxf.new(src.dxfversion)
    tgt.header["$INSUNITS"] = src.header.get("$INSUNITS", 6)
    ents = [e for e in (src.entitydb.get(h) for h in handles) if e is not None]
    imp = Importer(src, tgt)
    imp.import_entities(ents, tgt.modelspace())
    imp.finalize()
    tgt.saveas(out)
    return len(ents)


def removed_since(old, new) -> list:
    """Prvky, které ve starší verzi byly a v novější chybí (ne jen upravené)."""
    from .porovnani import ODEBRANO, compare
    return [z.old for z in compare(old, new) if z.druh == ODEBRANO and z.old is not None and z.old.handle]
