"""Cesty k přibaleným souborům (fungují i v .exe z PyInstalleru)."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base, "kontrola", "resources", *parts)
    return Path(__file__).resolve().parent.joinpath("resources", *parts)
