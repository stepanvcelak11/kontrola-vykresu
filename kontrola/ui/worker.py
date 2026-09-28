"""Běh dlouhých úloh (načtení výkresu, kontroly) ve vlákně na pozadí."""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal


class _Worker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], cancel_event: threading.Event):
        super().__init__()
        self._fn = fn
        self._cancel = cancel_event

    def run(self):
        try:
            result = self._fn(lambda p, msg="": self.progress.emit(int(p), msg), self._cancel.is_set)
        except Exception as exc:  # předáme do GUI vlákna
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            try:
                from .crash import write_log
                write_log("Úloha na pozadí selhala:\n" + traceback.format_exc())
            except Exception:  # noqa: BLE001
                pass
            self.failed.emit(str(exc) if str(exc) else detail)
            return
        self.finished.emit(result)


class BackgroundTask(QObject):
    """Spustí ``fn(progress, cancelled)`` v samostatném QThread.

    ``progress(procenta, text)`` hlásí průběh, ``cancelled()`` vrací True, pokud
    uživatel úlohu zrušil.
    """

    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], parent: QObject | None = None):
        super().__init__(parent)
        self._cancel = threading.Event()
        self._thread = QThread()
        self._worker = _Worker(fn, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

    def start(self):
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def _cleanup(self):
        self._thread.quit()
        self._thread.wait()

    def _on_finished(self, result):
        self._cleanup()
        self.finished.emit(result)

    def _on_failed(self, msg):
        self._cleanup()
        self.failed.emit(msg)
