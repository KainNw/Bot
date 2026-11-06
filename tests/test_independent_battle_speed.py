import json
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.battle_speed import IndependentBattleSpeedWorker
from atlantica_bot.clock_control import NativeClock
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, ProfileStore


def test_independent_worker_uses_the_exact_existing_battle_clock():
    session = SimpleNamespace(
        process=SimpleNamespace(pid=100),
        creation_time=777,
        system=SimpleNamespace(process_creation_time=lambda pid: 900),
    )
    window, signal = SimpleNamespace(pid=100), SimpleNamespace(name="independent")
    worker = IndependentBattleSpeedWorker(session, window, 3)
    clock = worker._make_clock(signal)
    assert type(clock) is NativeClock and clock.initial_rate == 1.0
    assert clock.start_operation == 13 and clock.start_argument == "--clock-start"
    assert clock.session is session and clock.window is window and clock.signal is signal
    assert worker.report["independent"] and worker.report["mode"] == "battle"


@pytest.mark.parametrize("stop_fault", [False, True])
def test_independent_lifecycle_without_bot_reserves_and_restores_only_its_clock(
    monkeypatch, stop_fault
):
    events = []

    @contextmanager
    def lease(pid):
        assert pid == 100
        events.append("reserve speed")
        yield
        events.append("release speed")

    class Signal:
        def __init__(self, pid):
            self.cancelled = False

        def __enter__(self):
            return self

        def cancel(self):
            self.cancelled = True

        def __exit__(self, *_):
            events.append("close signal")

    class Clock:
        def __init__(self, session, window, signal, rate):
            assert rate == 3
            self.signal, self.attempted = signal, True
            self.report = {"armed": True, "current_rate": 1, "mode": "battle"}
            self.reads = 0

        def start(self):
            events.append("start battle clock at 1x")

        def read(self):
            self.reads += 1
            self.report["current_rate"] = 3 if self.reads == 1 else 1
            events.append("battle 3x" if self.reads == 1 else "map 1x")
            if self.reads == 2:
                worker.stop()

        def stop(self):
            assert self.signal.cancelled and "release speed" not in events
            events.append("stop once")
            if stop_fault:
                raise DiagnosticError("ack lost")
            self.confirm_stopped()

        def confirm_stopped(self):
            assert "release speed" not in events
            self.attempted = False
            self.report.update(armed=False, current_rate=1)
            events.append("restore confirmed")

    monkeypatch.setattr("atlantica_bot.general_speed.SpeedLease", lease)
    monkeypatch.setattr("atlantica_bot.general_speed.Cancellation", Signal)
    monkeypatch.setattr("atlantica_bot.battle_speed.NativeClock", Clock)
    worker = IndependentBattleSpeedWorker(
        SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777),
        SimpleNamespace(pid=100),
        3,
    )
    worker._run()
    assert events[:4] == ["reserve speed", "start battle clock at 1x", "battle 3x", "map 1x"]
    assert events.count("stop once") == 1
    assert events[-3:] == ["restore confirmed", "close signal", "release speed"]
    assert worker.report["current_rate"] == 1 and not worker.report["armed"]


@pytest.mark.parametrize("rate", [1.25, 1.5, 2, 3, 4])
def test_independent_settings_preserve_the_original_bot_speed(tmp_path, rate):
    original = replace(BotProfile.default(1), battle_speed_enabled=True, battle_speed_rate=3)
    updated = replace(
        original, independent_battle_speed_enabled=True, independent_battle_speed_rate=rate
    )
    store = ProfileStore(tmp_path)
    store.save(updated)
    assert store.load(1) == updated
    assert store.load(1).battle_speed_enabled and store.load(1).battle_speed_rate == 3


def test_schema_eleven_keeps_bot_speed_and_independent_is_off_without_rewriting(tmp_path):
    original = replace(BotProfile.default(1), battle_speed_enabled=True, battle_speed_rate=3)
    data = original.summary()
    data["schema_version"] = 11
    del data["independent_battle_speed_enabled"], data["independent_battle_speed_rate"]
    path = tmp_path / "profile-1.json"
    raw = json.dumps(data).encode()
    path.write_bytes(raw)
    assert ProfileStore(tmp_path).load(1) == original
    assert path.read_bytes() == raw


@pytest.mark.parametrize("rate", [True, 0, 1, 5, "3", float("nan")])
def test_invalid_independent_factor_preserves_saved_profile(tmp_path, rate):
    store = ProfileStore(tmp_path)
    original = BotProfile.default(1)
    store.save(original)
    with pytest.raises(DiagnosticError, match="independiente"):
        store.save(replace(original, independent_battle_speed_rate=rate))
    assert store.load(1) == original


def test_busy_speed_lease_does_not_start_or_stop_another_controller(monkeypatch):
    @contextmanager
    def busy(pid):
        raise DiagnosticError("Speed reservado por otro controlador")
        yield  # pragma: no cover

    monkeypatch.setattr("atlantica_bot.general_speed.SpeedLease", busy)
    monkeypatch.setattr(
        "atlantica_bot.battle_speed.NativeClock", lambda *_: pytest.fail("Busy PID")
    )
    worker = IndependentBattleSpeedWorker(
        SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777),
        SimpleNamespace(pid=100),
        3,
    )
    worker._run()
    assert worker.report["error"] and not worker.report["armed"]
    assert "reservado" in worker.report["message"]


def test_manual_modes_cannot_both_be_saved_as_enabled(tmp_path):
    store = ProfileStore(tmp_path)
    original = replace(BotProfile.default(1), general_speed_enabled=True)
    store.save(original)
    with pytest.raises(DiagnosticError, match="control manual"):
        store.save(replace(original, independent_battle_speed_enabled=True))
    assert store.load(1) == original
