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


# ---------------------------------------------------------------- poslední kroky a tvrdé pády
_steps: list[str] = []
_fault_fh = None


def steps_file() -> Path:
    return log_dir() / "posledni_kroky.log"


def fault_file() -> Path:
    return log_dir() / "pad.log"


def running_flag() -> Path:
    return log_dir() / "bezi.flag"


def step(text: str) -> None:
    """Zapamatuje si krok uživatele (název funkce) – do hlášení „co jsem dělal před chybou“."""
    line = f"{dt.datetime.now():%H:%M:%S}  {text}"
    _steps.append(line)
    del _steps[:-60]
    try:
        with open(steps_file(), "a", encoding="utf-8") as fh:  # přežije i tvrdý pád
            fh.write(line + "\n")
    except OSError:
        pass


def _tail(path: Path, n: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def previous_run_crashed() -> bool:
    """Skončila minulá relace bez řádného zavření (pád, zamrznutí, ukončení ve Správci úloh)?"""
    return running_flag().exists()


def start_session() -> None:
    """Na začátku běhu: příznak „běží“, faulthandler pro tvrdé pády, zkrácení starých záznamů."""
    global _fault_fh
    for f, keep in ((steps_file(), 300), (fault_file(), 400)):
        try:
            if f.exists() and f.stat().st_size > 200_000:
                f.write_text(_tail(f, keep) + "\n", encoding="utf-8")
        except OSError:
            pass
    try:
        with open(steps_file(), "a", encoding="utf-8") as fh:
            fh.write(f"----- spuštění {dt.datetime.now():%Y-%m-%d %H:%M:%S}, verze {_version()}\n")
    except OSError:
        pass
    try:
        import faulthandler
        _fault_fh = open(fault_file(), "a", encoding="utf-8")
        _fault_fh.write(f"----- relace {dt.datetime.now():%Y-%m-%d %H:%M:%S}, verze {_version()}\n")
        _fault_fh.flush()
        faulthandler.enable(file=_fault_fh)
    except (OSError, RuntimeError, ValueError):
        pass
    try:
        running_flag().write_text(f"{os.getpid()} {dt.datetime.now().isoformat()}", encoding="utf-8")
    except OSError:
        pass


def end_session() -> None:
    """Řádné zavření aplikace – příznak „běží“ pryč."""
    try:
        running_flag().unlink()
    except OSError:
        pass


def build_report(win=None, problem: str = "") -> str:
    """Hlášení o problému: verze, systém, poslední chyby, tvrdé pády, poslední kroky a stav projektu.

    Obsahuje jen technické údaje – žádné výkresy ani souřadnice.
    """
    out = ["HLÁŠENÍ O PROBLÉMU – Kontrola výkresu",
           f"Vytvořeno: {dt.datetime.now():%Y-%m-%d %H:%M:%S}",
           f"Verze: {_version()}",
           f"Systém: {platform.platform()} · Python {platform.python_version()}"]
    try:
        import PySide6
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        scr = app.primaryScreen() if app else None
        out.append(f"Qt: PySide6 {PySide6.__version__}" + (
            f" · obrazovka {scr.size().width()}×{scr.size().height()}, měřítko {scr.devicePixelRatio():g}"
            if scr else ""))
    except Exception:  # noqa: BLE001
        pass
    if problem:
        out += ["", "Co se stalo (popis):", problem]
    if win is not None:
        out += ["", "Stav aplikace:"]
        try:
            d = getattr(win, "drawing", None)
            if d is not None:
                src = Path(d.source_path or d.path)
                out.append(f"  výkres: {src.suffix.lower()} soubor, {len(d.features)} prvků, {len(d.layers)} vrstev")
            else:
                out.append("  výkres: žádný")
            iss = getattr(win, "issues", []) or []
            if iss:
                from collections import Counter
                c = Counter(i.check_id for i in iss)
                out.append(f"  chyby: {len(iss)} (" + ", ".join(f"{k} {v}" for k, v in c.most_common(8)) + ")")
            pr = getattr(win, "project", None)
            if pr is not None:
                out.append(f"  pravidla: {len(pr.rules.pravidla)}")
            st = getattr(win, "settings", None)
            if st is not None:
                out.append("  vzhled: " + ", ".join(f"{k}={st.value('zobrazeni/' + k, '')}"
                                                   for k in ("vzhled", "barva", "pismo")))
            tabs = getattr(win, "tabs", None)
            if tabs is not None:
                out.append(f"  stránka: {tabs.tabText(tabs.currentIndex())}")
        except Exception as e:  # noqa: BLE001 – hlášení se musí vytvořit vždy
            out.append(f"  (stav nejde zjistit: {e})")
    steps = "\n".join(_steps[-30:]) or _tail(steps_file(), 30)
    out += ["", "Poslední kroky:", steps or "  –"]
    out += ["", "Poslední chyby (chyby.log):", _tail(log_file(), 80) or "  žádné"]
    fault = _tail(fault_file(), 60)
    if "Fatal Python error" in fault or "Current thread" in fault:
        out += ["", "Tvrdý pád (pad.log):", fault]
    return "\n".join(out) + "\n"


def save_report(text: str) -> Path:
    """Uloží hlášení na plochu (jinak do Dokumentů / složky s logy) a vrátí cestu."""
    name = f"KontrolaVykresu_hlaseni_{dt.datetime.now():%Y-%m-%d_%H%M}.txt"
    cands = []
    try:
        from PySide6.QtCore import QStandardPaths
        for loc in (QStandardPaths.DesktopLocation, QStandardPaths.DocumentsLocation):
            p = QStandardPaths.writableLocation(loc)
            if p:
                cands.append(Path(p))
    except Exception:  # noqa: BLE001
        pass
    cands.append(log_dir())
    for d in cands:
        try:
            d.mkdir(parents=True, exist_ok=True)
            f = d / name
            f.write_text(text, encoding="utf-8")
            return f
        except OSError:
            continue
    raise OSError("Hlášení nejde nikam uložit.")


def show_report_dialog(win=None, problem: str = "", title: str = "Hlášení o problému") -> None:
    """Okno s hotovým hlášením: zkopírovat (a vložit do chatu) nebo uložit jako soubor."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                                   QVBoxLayout)
    dlg = QDialog(win)
    dlg.setWindowTitle(title)
    dlg.resize(760, 560)
    lay = QVBoxLayout(dlg)
    lab = QLabel("<b>Co se stalo?</b> Napište pár slov (co jste dělal, co se objevilo). Pak hlášení "
                 "<b>zkopírujte a vložte do chatu</b>, nebo ho uložte jako soubor a pošlete. Obsahuje jen "
                 "technické údaje – žádné výkresy ani souřadnice.")
    lab.setWordWrap(True)
    lay.addWidget(lab)
    what = QPlainTextEdit(problem)
    what.setPlaceholderText("Např.: Klikl jsem na Protokol PDF a aplikace se zavřela…")
    what.setFixedHeight(70)
    lay.addWidget(what)
    view = QPlainTextEdit()
    view.setReadOnly(True)
    lay.addWidget(view, 1)

    def text():
        return build_report(win, what.toPlainText().strip())

    view.setPlainText(text())
    what.textChanged.connect(lambda: view.setPlainText(text()))
    row = QHBoxLayout()
    b_copy = QPushButton("📋 Kopírovat hlášení")
    b_copy.setProperty("primarni", True)
    b_save = QPushButton("💾 Uložit na plochu")
    b_close = QPushButton("Zavřít")
    row.addWidget(b_copy)
    row.addWidget(b_save)
    row.addStretch(1)
    row.addWidget(b_close)
    lay.addLayout(row)
    info = QLabel("")
    info.setWordWrap(True)
    lay.addWidget(info)

    def copy():
        QGuiApplication.clipboard().setText(text())
        info.setText("✓ Zkopírováno – vložte do chatu (Ctrl+V).")

    def save():
        try:
            f = save_report(text())
            info.setText(f"✓ Uloženo: {f}")
        except OSError as e:
            QMessageBox.warning(dlg, title, str(e))

    b_copy.clicked.connect(copy)
    b_save.clicked.connect(save)
    b_close.clicked.connect(dlg.accept)
    dlg._copy, dlg._save, dlg._text = copy, save, text  # pro testy
    dlg.setAttribute(Qt_WA_DeleteOnClose())
    dlg.show()
    return dlg


def Qt_WA_DeleteOnClose():  # noqa: N802
    from PySide6.QtCore import Qt
    return Qt.WA_DeleteOnClose


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
        b_rep = box.addButton("Vytvořit hlášení…", QMessageBox.ActionRole)
        b_copy = box.addButton("Kopírovat podrobnosti", QMessageBox.ActionRole)
        b_report = box.addButton("Nahlásit na GitHub…", QMessageBox.ActionRole)
        box.addButton("Pokračovat", QMessageBox.AcceptRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_rep:
            show_report_dialog(parent)
        elif clicked is b_copy:
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
