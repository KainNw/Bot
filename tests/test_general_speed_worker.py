from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.general_speed import GeneralSpeedWorker


@pytest.mark.parametrize("stop_fault", [False, True])
def test_general_owns_only_speed_and_restores_before_releasing_it(monkeypatch, stop_fault):
    events = []

    @contextmanager
    def lease(pid):
        assert pid == 100
        events.append("lease")
        yield
        events.append("release")

    class Signal:
        def __init__(self, pid):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True
            events.append("cancel")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            events.append("signal closed")

    class Clock:
        def __init__(self, session, window, signal, rate):
            assert rate == 3 and window.pid == 100
            self.signal, self.attempted = signal, True
            self.report = {"armed": True, "current_rate": 3, "message": "General activo"}

        def start(self):
            events.append("start general")

        def read(self):
            events.append("read")
            worker.stop()

        def stop(self):
            assert self.signal.cancelled and "release" not in events
            events.append("stop")
            if stop_fault:
                raise DiagnosticError("lost acknowledgement")
            self.confirm_stopped()

        def confirm_stopped(self):
            assert "release" not in events
            events.append("confirm")
            self.attempted = False
            self.report.update(armed=False, current_rate=1)

    monkeypatch.setattr("atlantica_bot.general_speed.SpeedLease", lease)
    monkeypatch.setattr("atlantica_bot.general_speed.Cancellation", Signal)
    monkeypatch.setattr("atlantica_bot.general_speed.GeneralNativeClock", Clock)
    worker = GeneralSpeedWorker(
        SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777),
        SimpleNamespace(pid=100),
        3,
    )
    worker._run()
    assert events.count("start general") == events.count("stop") == 1
    assert events[-3:] == ["confirm", "signal closed", "release"]
    assert worker.report["current_rate"] == 1 and not worker.report["armed"]
    assert not worker.report["cleanup_pending"]


def test_general_stop_before_start_does_not_install_clock(monkeypatch):
    worker = GeneralSpeedWorker(
        SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777),
        SimpleNamespace(pid=100),
        2,
    )
    worker.stop()
    from contextlib import nullcontext

    monkeypatch.setattr("atlantica_bot.general_speed.SpeedLease", lambda pid: nullcontext())
    signal = SimpleNamespace(cancel=lambda: None)
    monkeypatch.setattr("atlantica_bot.general_speed.Cancellation", lambda pid: nullcontext(signal))
    monkeypatch.setattr(
        "atlantica_bot.general_speed.GeneralNativeClock",
        lambda *_: pytest.fail("A cancelled standalone controller must not start"),
    )
    worker._run()
