"""Společné chování oken: dlouhé popisky v dialozích se zalamují, aby okno nebylo zbytečně široké/podlouhlé."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

DLOUHY_TEXT = 70  # znaků – delší popisek se zalomí


def _text(lb: QLabel) -> str:
    t = lb.text()
    if lb.textFormat() != Qt.PlainText and re.search(r"<[a-zA-Z/]", t):
        t = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", t, flags=re.I)
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return t


def zalom_popisky(okno) -> int:
    """Zapne zalamování dlouhých jednořádkových popisků v okně; vrací počet upravených."""
    n = 0
    for lb in okno.findChildren(QLabel):
        if lb.wordWrap() or lb.pixmap() is not None and not lb.pixmap().isNull():
            continue
        t = _text(lb)
        if max((len(r) for r in t.splitlines()), default=0) > DLOUHY_TEXT:
            lb.setWordWrap(True)
            n += 1
    return n


def vejdi_se(okno, podil: float = 0.92) -> bool:
    """Okno větší než obrazovka (malý notebook) zmenší a posune celé na obrazovku."""
    scr = okno.screen() or QApplication.primaryScreen()
    if scr is None:
        return False
    g = scr.availableGeometry()
    w, h = min(okno.width(), int(g.width() * podil)), min(okno.height(), int(g.height() * podil))
    if (w, h) == (okno.width(), okno.height()) and g.contains(okno.frameGeometry()):
        return False
    okno.resize(w, h)
    fg = okno.frameGeometry()
    x = min(max(fg.x(), g.x()), g.right() - fg.width())
    y = min(max(fg.y(), g.y()), g.bottom() - fg.height())
    okno.move(max(g.x(), x), max(g.y(), y))
    return True


class _Hlidac(QObject):
    def eventFilter(self, obj, ev):  # noqa: N802
        if ev.type() == QEvent.Polish and isinstance(obj, QDialog) and not isinstance(obj, QMessageBox):
            try:
                zalom_popisky(obj)
            except Exception:  # noqa: BLE001 – jen vzhled, nikdy nesmí shodit aplikaci
                pass
        elif ev.type() == QEvent.Show and isinstance(obj, QDialog) and obj.isWindow():
            try:
                vejdi_se(obj)
            except Exception:  # noqa: BLE001
                pass
        return False


def nainstaluj(app: QApplication | None = None) -> None:
    app = app or QApplication.instance()
    if app is None or getattr(app, "_hlidac_oken", None) is not None:
        return
    app._hlidac_oken = _Hlidac(app)
    app.installEventFilter(app._hlidac_oken)
