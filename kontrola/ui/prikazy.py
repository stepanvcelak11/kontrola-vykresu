"""Vyhledávání „Co chcete udělat?“: napíšete část názvu funkce (i bez diakritiky) a Enter ji spustí."""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QCompleter, QLineEdit


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class CommandSearch(QLineEdit):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setObjectName("hledat_prikaz")
        self.setPlaceholderText("🔍  Co chcete udělat?  (Ctrl+F)")
        self.setToolTip("Najde funkci aplikace podle názvu – např. „protokol“, „seznam“, „vrstvy“ – Enter ji spustí")
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(320)
        self._model = QStringListModel(self)
        self._comp = QCompleter(self._model, self)
        self._comp.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._comp.setMaxVisibleItems(12)
        self._comp.activated[str].connect(self._run)
        self.setCompleter(self._comp)
        self.textEdited.connect(self._update)
        self.returnPressed.connect(lambda: self._run(self._first()))
        QShortcut(QKeySequence("Ctrl+F"), win, activated=self._focus)
        self._actions: dict[str, QAction] = {}

    def _focus(self):
        self.setFocus()
        self.selectAll()

    def _collect(self):
        acts: dict[str, QAction] = {}
        for a in self.win.findChildren(QAction):
            t = a.text().replace("&", "").rstrip("…").strip()
            if not t or a.isSeparator() or not a.isEnabled() or a.menu() is not None:
                continue
            sc = a.shortcut().toString(QKeySequence.NativeText)
            label = f"{t}   ({sc})" if sc else t
            acts.setdefault(label, a)
        self._actions = acts

    def _matches(self, text: str) -> list[str]:
        words = _norm(text).split()
        if not words:
            return []
        out = []
        for label, a in self._actions.items():
            hay = _norm(label + " " + a.toolTip())
            if all(w in hay for w in words):
                # přednost mají shody v názvu, pak kratší názvy
                out.append((0 if all(w in _norm(label) for w in words) else 1, len(label), label))
        return [x[2] for x in sorted(out)[:20]]

    def _update(self, text: str):
        if not self._actions:
            self._collect()
        self._model.setStringList(self._matches(text))
        if self._model.rowCount():
            self._comp.complete()

    def _first(self) -> str | None:
        m = self._matches(self.text())
        return m[0] if m else None

    def _run(self, label: str | None):
        if not label:
            return
        a = self._actions.get(label)
        self.clear()
        self.clearFocus()
        self._actions = {}  # akce se mohou měnit (sady kontrol) – při dalším hledání se načtou znovu
        if a is not None:
            if a.isCheckable():
                a.toggle()
            else:
                a.trigger()

    def focusInEvent(self, e):  # noqa: N802
        self._collect()
        super().focusInEvent(e)

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.clear()
            self.clearFocus()
            return
        super().keyPressEvent(e)
