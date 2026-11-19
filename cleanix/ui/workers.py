"""Фоновые задачи: ядро не знает про Qt, поэтому гоняем его в QThread."""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal


class Worker(QThread):
    progress = Signal(str, int, int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[["Worker"], Any], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.fn = fn
        self.cancel_event = threading.Event()

    def report(self, text: str, i: int = 0, n: int = 0) -> None:
        self.progress.emit(text, i, n)

    def run(self) -> None:
        try:
            result = self.fn(self)
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ == "Cancelled":
                self.finished_ok.emit(None)
            else:
                self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished_ok.emit(result)

    def stop(self) -> None:
        self.cancel_event.set()


class TaskRunner(QObject):
    """Держит ссылку на активный Worker и подключает колбэки."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.worker: Optional[Worker] = None

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def start(self, fn, on_done=None, on_error=None, on_progress=None) -> Worker:
        if self.busy:
            raise RuntimeError("busy")
        w = Worker(fn, self)
        if on_progress:
            w.progress.connect(on_progress)
        if on_done:
            w.finished_ok.connect(on_done)
        if on_error:
            w.failed.connect(on_error)
        w.finished.connect(w.deleteLater)
        w.finished.connect(self._cleanup)
        self.worker = w
        w.start()
        return w

    def _cleanup(self) -> None:
        self.worker = None

    def stop(self) -> None:
        if self.worker:
            self.worker.stop()

    def wait(self, ms: int = 5000) -> None:
        if self.worker:
            self.worker.wait(ms)
