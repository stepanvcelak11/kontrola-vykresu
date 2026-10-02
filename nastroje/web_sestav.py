"""Sestaví webovou verzi do složky (výchozí _site): stránky z web/ a jádro aplikace jako kontrola.zip (bez Qt UI)."""

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sestav(cil: Path) -> Path:
    if cil.exists():
        shutil.rmtree(cil)
    shutil.copytree(ROOT / "web", cil)
    with zipfile.ZipFile(cil / "kontrola.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((ROOT / "kontrola").rglob("*")):
            rel = f.relative_to(ROOT)
            if f.is_dir() or "__pycache__" in rel.parts or rel.parts[1:2] == ("ui",):
                continue
            if f.suffix in (".py", ".json", ".yaml", ".txt", ".tbl") or "resources" in rel.parts:
                z.write(f, rel.as_posix())
    # písma s českou diakritikou do PDF (protokoly) – ze systému, kde se web sestavuje
    fonty = cil / "fonty"
    fonty.mkdir(exist_ok=True)
    for f in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf"):
        for d in (Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu")):
            if (d / f).is_file():
                shutil.copy(d / f, fonty / f)
                break
    return cil


if __name__ == "__main__":
    print(sestav(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"))
