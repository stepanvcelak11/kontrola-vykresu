"""Spuštění grafické aplikace."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
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
    win = MainWindow()
    win.show()
    if not win.settings.value("pruvodce/skryt", False, type=bool):
        QTimer.singleShot(400, win.show_guide)  # průvodce při prvním spuštění
    QTimer.singleShot(3000, win.maybe_check_updates)
    for a in argv[1:]:
        if not a.startswith("-"):
            win.open_path(a)
            break
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
