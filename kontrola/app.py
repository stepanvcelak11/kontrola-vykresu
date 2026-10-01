"""Spuštění grafické aplikace."""

from __future__ import annotations

import sys


def _splash(text: str | None = None, close: bool = False) -> None:
    """Úvodní okénko sestaveného .exe (PyInstaller); ze zdrojových kódů neexistuje."""
    try:
        import pyi_splash  # type: ignore
    except ImportError:
        return
    try:
        if close:
            pyi_splash.close()
        elif text:
            pyi_splash.update_text(text)
    except Exception:  # noqa: BLE001 – okénko je jen ozdoba, nesmí zastavit start
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _splash("Spouštím…")
    from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTimer, QTranslator
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("KontrolaVykresu")
    QLocale.setDefault(QLocale(QLocale.Czech, QLocale.CzechRepublic))
    tr = QTranslator(app)
    if tr.load(QLocale(QLocale.Czech), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr)
    from .ui.theme import apply_theme
    # tmavý (profesionální) vzhled je výchozí; světlý jde přepnout v Zobrazení → Tmavý režim
    vzhled = QSettings("KontrolaVykresu", "KontrolaVykresu").value("zobrazeni/vzhled", "tmavy")
    from .ui.theme import set_accent, set_font_scale
    _st = QSettings("KontrolaVykresu", "KontrolaVykresu")
    set_accent(str(_st.value("zobrazeni/barva", "modra")))
    set_font_scale(str(_st.value("zobrazeni/pismo", "normalni")))
    apply_theme(app, vzhled != "svetly")
    from PySide6.QtGui import QIcon

    from .resources import resource_path
    app.setWindowIcon(QIcon(str(resource_path("ikona.png"))))
    if sys.platform == "win32":  # vlastní ikona na hlavním panelu Windows
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KontrolaVykresu.App")
        except (AttributeError, OSError):
            pass
    from .ui import crash
    crash.install(lambda: QApplication.activeWindow())
    _splash("Načítám poslední projekt…")
    win = MainWindow()
    win.show()
    _splash(close=True)
    if not win.settings.value("pruvodce/skryt", False, type=bool):
        QTimer.singleShot(400, win.show_guide)  # průvodce při prvním spuštění
    QTimer.singleShot(1500, win.maybe_show_news)  # po aktualizaci jednou „Co je nového“
    QTimer.singleShot(3000, win.maybe_check_updates)
    for a in argv[1:]:
        if not a.startswith("-"):
            win.open_path(a)
            break
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
