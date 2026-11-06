import json
import struct
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlantica_bot.clock_control import TELEMETRY, GeneralNativeClock, bits
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, ProfileStore


@pytest.fixture
def general_clock(monkeypatch):
    state = SimpleNamespace(current=2.0, reason=12, view=1, armed=1, created=777, calls=[])

    def created(pid):
        return state.created if pid == 100 else 900

    def read(pid, address, count):
        assert pid == 100 and address in (0x800000, 0x800020)
        if count == 4:
            return struct.pack("<i", 2)
        return TELEMETRY.pack(
            0x414F5031,
            1,
            100,
            control.owner_pid,
            900,
            0,
            123,
            456,
            2,
            state.armed,
            bits(state.current),
            bits(2.0),
            state.reason,
            1,
            0,
            0,
            state.view,
        )

    session = SimpleNamespace(
        process=SimpleNamespace(pid=100),
        creation_time=777,
        system=SimpleNamespace(process_creation_time=created, read_memory=read),
    )
    window = SimpleNamespace(pid=100, handle=0x1234, thread_id=500)
    control = GeneralNativeClock(session, window, SimpleNamespace(name="general-run"), 2.0)
    monkeypatch.setattr("atlantica_bot.clock_control.bridge_path", lambda: Path("bridge.exe"))

    def run(args, **_kwargs):
        state.calls.append(args)
        start = args[1] == "--clock-general-start"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "pid": 100,
                    "thread_id": 500,
                    "exception": 0,
                    "slot": 0,
                    "operation": 18 if start else 14 if args[1] == "--clock-stop" else 15,
                    "status": 43 if start else 44 if args[1] == "--clock-stop" else 45,
                    "clock": {
                        "rate_bits": bits(2.0),
                        "owner_pid": control.owner_pid,
                        "created_lo": 900,
                        "created_hi": 0,
                        "armed": int(start),
                        "current_bits": bits(2.0 if start else 1.0),
                        "reason": 12 if start else 11,
                        "apply_count": 1,
                        "restore_count": int(not start),
                        "error": 0,
                        "view": state.view,
                        "address": 0x800000,
                        "token_lo": 123,
                        "token_hi": 456,
                    },
                }
            ),
        )

    monkeypatch.setattr("atlantica_bot.clock_control.subprocess.run", run)
    return control, state


def test_general_starts_with_separate_operation_and_uses_same_owned_restore(general_clock):
    control, state = general_clock
    control.start()
    assert control.report["mode"] == "general" and control.report["current_rate"] == 2.0
    assert state.calls[0][1] == "--clock-general-start"
    assert "--clock-start" not in state.calls[0]
    assert control.stop() and control.stop()
    assert [args[1] for args in state.calls] == ["--clock-general-start", "--clock-stop"]
    assert control.report["current_rate"] == 1.0 and not control.report["armed"]


@pytest.mark.parametrize("view", [1, 2, 3, 4])
def test_general_telemetry_accepts_map_battle_and_graphic_transitions(general_clock, view):
    control, state = general_clock
    control.start()
    state.view = view
    assert control.read()["current_rate"] == 2.0
    assert control.report["mode"] == "general" and control.report["armed"]
    assert len(state.calls) == 1


def test_general_waits_at_one_on_incomplete_scene_and_recovers_without_restart(general_clock):
    control, state = general_clock
    control.start()
    state.current, state.reason, state.view = 1.0, 13, 0
    assert control.read()["current_rate"] == 1.0 and control.report["armed"]
    state.current, state.reason, state.view = 2.0, 12, 1
    assert control.read()["current_rate"] == 2.0
    assert len(state.calls) == 1


def test_general_does_not_start_on_reused_pid(general_clock):
    control, state = general_clock
    state.created = 888
    with pytest.raises(DiagnosticError, match="instancia"):
        control.start()
    assert not state.calls


@pytest.mark.parametrize("rate", [1.25, 1.5, 2, 3, 4])
def test_general_rate_and_mode_round_trip_without_altering_battle_factor(tmp_path, rate):
    profile = replace(
        BotProfile.default(1),
        general_speed_enabled=True,
        general_speed_rate=rate,
        battle_speed_rate=3,
    )
    store = ProfileStore(tmp_path)
    store.save(profile)
    loaded = store.load(1)
    assert loaded == profile and loaded.speed_enabled
    assert not loaded.battle_speed_enabled and loaded.battle_speed_rate == 3


def test_general_and_battle_cannot_be_stacked_in_one_profile(tmp_path):
    store = ProfileStore(tmp_path)
    original = replace(BotProfile.default(1), battle_speed_enabled=True, battle_speed_rate=3)
    store.save(original)
    with pytest.raises(DiagnosticError, match="modo de Speed"):
        store.save(replace(original, general_speed_enabled=True))
    assert store.load(1) == original


def test_previous_profile_keeps_existing_battle_mode_and_general_is_off(tmp_path):
    original = replace(BotProfile.default(1), battle_speed_enabled=True, battle_speed_rate=3)
    payload = original.summary()
    payload["schema_version"] = 8
    del payload["general_speed_enabled"], payload["general_speed_rate"]
    path = tmp_path / "profile-1.json"
    saved = json.dumps(payload).encode()
    path.write_bytes(saved)
    loaded = ProfileStore(tmp_path).load(1)
    assert loaded == original and not loaded.general_speed_enabled
    assert path.read_bytes() == saved


@pytest.mark.parametrize("rate", [True, 0, 1, 5, "2", float("nan")])
def test_invalid_general_factor_preserves_saved_settings(tmp_path, rate):
    store = ProfileStore(tmp_path)
    original = BotProfile.default(1)
    store.save(original)
    with pytest.raises(DiagnosticError):
        store.save(replace(original, general_speed_rate=rate))
    assert store.load(1) == original
