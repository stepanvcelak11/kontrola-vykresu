"""Zachycení neočekávaných chyb: zápis do logu, srozumitelné okno a možnost chybu nahlásit.

Aplikace nesmí po chybě „tiše zmizet“. Chyba se zapíše do souboru (i s verzí programu),
uživatel uvidí okno s vysvětlením a může podrobnosti zkopírovat nebo je sám poslat
(odkaz na GitHub se předvyplní – nic se neodesílá automaticky).
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import sys
import threading
import traceback
from pathlib import Path
from urllib.parse import quote

ISSUES_URL = "https://github.com/stepanvcelak11/kontrola-vykresu/issues/new"
_showing = False


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    d = Path(base) / "KontrolaVykresu" / "logy"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        import tempfile
        d = Path(tempfile.gettempdir()) / "KontrolaVykresu"
        d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return log_dir() / "chyby.log"


def _version() -> str:
    try:
        from ..aktualizace import version_text
        return version_text()
    except Exception:  # noqa: BLE001
        return "?"


def write_log(text: str) -> None:
    try:
        f = log_file()
        if f.exists() and f.stat().st_size > 2_000_000:  # log nesmí růst donekonečna
            f.replace(f.with_suffix(".old.log"))
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {dt.datetime.now():%Y-%m-%d %H:%M:%S} | verze {_version()} | "
                     f"{platform.platform()} | Python {platform.python_version()}\n{text}\n")
    except OSError:
        pass


def report_text(exc_type, exc, tb) -> str:
    return "".join(traceback.format_exception(exc_type, exc, tb))


def show_dialog(details: str, parent=None) -> None:
    global _showing
    if _showing:
        return
    _showing = True
    try:
        from PySide6.QtGui import QDesktopServices, QGuiApplication
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Nastala neočekávaná chyba")
        box.setText("V aplikaci nastala chyba. Rozpracovaný projekt zůstal uložený – můžete pokračovat, "
                    "případně aplikaci zavřít a znovu otevřít.")
        box.setInformativeText(f"Podrobnosti jsou zapsané v souboru:\n{log_file()}")
        box.setDetailedText(details)
        b_copy = box.addButton("Kopírovat podrobnosti", QMessageBox.ActionRole)
        b_report = box.addButton("Nahlásit chybu…", QMessageBox.ActionRole)
        box.addButton("Pokračovat", QMessageBox.AcceptRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_copy:
            QGuiApplication.clipboard().setText(details)
        elif clicked is b_report:
            last = details.strip().splitlines()[-1] if details.strip() else "chyba"
            body = (f"Verze: {_version()}\nSystém: {platform.platform()}\n\nCo jsem dělal(a):\n\n\n"
                    f"Podrobnosti:\n```\n{details[-5000:]}\n```")
            url = f"{ISSUES_URL}?title={quote('Chyba: ' + last[:80])}&body={quote(body)}"
            QDesktopServices.openUrl(QUrl(url))
    except Exception:  # noqa: BLE001 – okno s chybou nesmí samo spadnout
        pass
    finally:
        _showing = False


def install(get_parent=lambda: None) -> None:
    """Nastaví zachytávání chyb v hlavním vlákně i ve vláknech na pozadí."""

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        details = report_text(exc_type, exc, tb)
        write_log(details)
        try:
            sys.__stderr__.write(details)
        except Exception:  # noqa: BLE001
            pass
        try:
            from PySide6.QtCore import QThread
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None and QThread.currentThread() is app.thread():
                show_dialog(details, get_parent())
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
