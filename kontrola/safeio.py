"""Bezpečný zápis souborů: nejdřív do dočasného souboru, pak výměna – při pádu nebo plném disku
zůstane starý soubor celý (projekt se nikdy „nerozbije“ napůl uložený)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
