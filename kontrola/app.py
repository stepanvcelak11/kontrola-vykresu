"""Spuštění grafické aplikace."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo
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
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    for a in argv[1:]:
        if not a.startswith("-"):
            win.open_path(a)
            break
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
