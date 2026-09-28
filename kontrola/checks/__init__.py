"""Kontroly výkresu. Každá kontrola je samostatná třída odvozená od :class:`Check`.

Import modulů níže kontroly zaregistruje (pořadí = pořadí v nastavení).
"""

from . import topology  # noqa: F401  (pořadí importu = pořadí kontrol)
from . import attributes  # noqa: F401,I001
from .base import REGISTRY, Check, CheckContext, Issue, Param, Severity, all_checks, register

__all__ = ["REGISTRY", "Check", "CheckContext", "Issue", "Param", "Severity", "all_checks", "register"]
