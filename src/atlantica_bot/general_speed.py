from __future__ import annotations

import threading

from .clock_control import GeneralNativeClock
from .errors import DiagnosticError
from .ipc import Cancellation, SpeedLease


class GeneralSpeedWorker:
    """Own only the selected instance's clock, independently of the hunting worker."""

    def __init__(self, session, window, rate: float):
        if session.creation_time is None or session.process.pid != window.pid:
            raise DiagnosticError("Conecta con una instancia válida antes de activar General.")
        self.session, self.window, self.rate = session, window, rate
        self.stop_event = threading.Event()
        self.signal = None
        self.report = {
            "pid": window.pid,
            "creation_time": session.creation_time,
            "enabled": True,
            "mode": "general",
            "configured_rate": rate,
            "current_rate": 1.0,
            "armed": False,
            "message": "Preparando Speed general",
        }
        self.thread = threading.Thread(
            target=self._run, name=f"AtlanticaSpeed-{window.pid}", daemon=True
        )

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.signal is not None:
            self.signal.cancel()

    def _update(self, clock, **changes) -> None:
        self.report = {**self.report, **clock.report, **changes}

    def _run(self) -> None:
        clock = None
        try:
            with SpeedLease(self.window.pid), Cancellation(self.window.pid) as signal:
                self.signal = signal
                try:
                    if self.stop_event.is_set():
                        return
                    clock = GeneralNativeClock(self.session, self.window, signal, self.rate)
                    clock.start()
                    self._update(clock)
                    while not self.stop_event.wait(0.25):
                        clock.read()
                        self._update(clock)
                        if not clock.report.get("armed"):
                            break
                finally:
                    try:
                        signal.cancel()
                    finally:
                        if clock is not None:
                            self._restore(clock)
        except (DiagnosticError, OSError, RuntimeError) as exc:
            self.report = {**self.report, "message": str(exc), "error": True}
        finally:
            self.signal = None

    def _restore(self, clock) -> None:
        try:
            clock.stop()
        except (DiagnosticError, OSError):
            # Keep the exclusive lease until the native watchdog's restore is
            # confirmed; never repeat an uncertain stop.
            while clock.attempted:
                self._update(clock, cleanup_pending=True, message="Restauración a 1× pendiente")
                threading.Event().wait(0.5)
                try:
                    clock.confirm_stopped()
                except (DiagnosticError, OSError):
                    continue
        self._update(clock, cleanup_pending=False)
