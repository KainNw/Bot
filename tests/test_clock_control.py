import json
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlantica_bot.clock_control import TELEMETRY, NativeClock, bits
from atlantica_bot.errors import DiagnosticError


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(
        created=777,
        listed=True,
        calls=[],
        failure=None,
        malformed=None,
        sequence=2,
        token=(123, 456),
        armed=1,
        current=1.0,
        reason=1,
        short=False,
        after_read=None,
        status_armed=0,
        status_code=45,
    )

    def created(pid):
        if pid != 100:
            return 900
        if isinstance(state.created, Exception):
            raise state.created
        return state.created

    def read(pid, address, count):
        assert pid == 100 and address in (0x800000, 0x800020)
        if state.short:
            return b""
        if count == 4:
            return struct.pack("<i", state.sequence)
        if state.after_read:
            state.after_read()
        return TELEMETRY.pack(
            0x414F5031,
            1,
            100,
            control.owner_pid,
            900,
            0,
            *state.token,
            state.sequence,
            state.armed,
            bits(state.current),
            bits(3.0),
            state.reason,
            2,
            1,
            0,
            2,
        )

    session = SimpleNamespace(
        process=SimpleNamespace(pid=100),
        creation_time=777,
        system=SimpleNamespace(
            process_creation_time=created,
            read_memory=read,
            processes=lambda: [SimpleNamespace(pid=100)] if state.listed else [],
        ),
    )
    window = SimpleNamespace(pid=100, handle=0x1234, thread_id=500)
    control = NativeClock(session, window, SimpleNamespace(name="cancel-this-run"), 3.0)
    monkeypatch.setattr("atlantica_bot.clock_control.bridge_path", lambda: Path("bridge.exe"))

    def run(args, **kwargs):
        operation = args[1].removeprefix("--clock-")
        state.calls.append((operation, args))
        if state.failure:
            raise state.failure
        fields = dict(zip(args[2::2], args[3::2], strict=True))
        data = {
            "pid": 100,
            "thread_id": 500,
            "exception": 0,
            "slot": 0,
            "operation": {"start": 13, "stop": 14, "status": 15}[operation],
            "status": {"start": 43, "stop": 44, "status": state.status_code}[operation],
            "clock": {
                "rate_bits": int(fields["--clock-rate-bits"]),
                "owner_pid": int(fields["--clock-owner-pid"]),
                "created_lo": 900,
                "created_hi": 0,
                "armed": 1 if operation == "start" else state.status_armed,
                "current_bits": bits(1.0),
                "reason": 1,
                "apply_count": 0,
                "restore_count": 0,
                "error": 0,
                "view": 1,
                "address": 0x800000,
                "token_lo": 123,
                "token_hi": 456,
            },
        }
        if state.malformed:
            state.malformed(data)
        return SimpleNamespace(returncode=0, stdout=json.dumps(data))

    monkeypatch.setattr("atlantica_bot.clock_control.subprocess.run", run)
    return control, state


def test_start_binds_owner_instance_window_and_cancellation_then_stop_confirms_one(clock):
    control, state = clock
    assert not state.calls
    control.start()
    assert control.report["armed"] and control.report["current_rate"] == 1.0
    args = state.calls[0][1]
    assert args[args.index("--pid") + 1] == "100"
    assert args[args.index("--created") + 1] == "777"
    assert args[args.index("--cancel-event") + 1] == "cancel-this-run"
    assert control.stop() and control.stop()
    assert [operation for operation, _ in state.calls] == ["start", "stop"]
    assert not control.report["armed"] and control.report["current_rate"] == 1.0


def test_telemetry_tracks_actual_factor_and_rejects_another_run(clock):
    control, state = clock
    control.start()
    state.current, state.reason = 3.0, 2
    assert control.read()["current_rate"] == 3.0
    assert control.read()["applications"] == 2
    state.token = (999, 456)
    with pytest.raises(DiagnosticError, match="otra ejecución"):
        control.read()
    assert [op for op, _ in state.calls] == ["start"]


def test_odd_sequence_keeps_last_complete_observation(clock):
    control, state = clock
    control.start()
    state.sequence, state.current, state.armed = 3, 3.0, 0
    assert control.read()["armed"] and control.report["current_rate"] == 1.0
    state.sequence = 4
    assert not control.read()["armed"] and control.report["current_rate"] == 3.0


def test_short_telemetry_is_a_diagnostic_error(clock):
    control, state = clock
    control.start()
    state.short = True
    with pytest.raises(DiagnosticError, match="incompleta"):
        control.read()


@pytest.mark.parametrize("when", ["before", "during"])
def test_pid_reuse_never_sends_stop_to_new_instance(clock, when):
    control, state = clock
    control.start()
    if when == "before":
        state.created = 778
    else:
        state.after_read = lambda: setattr(state, "created", 778)
    with pytest.raises(DiagnosticError, match="instancia|instancia|Instancia"):
        control.read()
    assert control.stop() and not control.attempted
    assert [op for op, _ in state.calls] == ["start"]


def test_unknown_stop_acknowledgement_only_uses_readonly_status_afterwards(clock):
    control, state = clock
    control.start()
    state.failure = subprocess.TimeoutExpired("bridge", 5)
    with pytest.raises(DiagnosticError):
        control.stop()
    assert control.attempted and control.stop_sent
    state.failure = None
    assert control.stop()
    assert [op for op, _ in state.calls] == ["start", "stop", "status"]


def test_cancelled_native_telemetry_confirms_restore_without_another_command(clock):
    control, state = clock
    control.start()
    state.failure = OSError("ack lost")
    with pytest.raises(DiagnosticError):
        control.stop()
    state.armed, state.current, state.reason = 0, 1.0, 7
    assert control.confirm_stopped()
    assert [op for op, _ in state.calls] == ["start", "stop"]


def test_lost_start_ack_can_be_retired_by_status_without_resending_start(clock):
    control, state = clock
    state.failure = OSError("ack lost")
    with pytest.raises(DiagnosticError):
        control.start()
    state.failure = None
    assert control.confirm_stopped()
    assert [op for op, _ in state.calls] == ["start", "status"]


def test_unreadable_live_instance_keeps_cleanup_pending_but_exit_releases_it(clock):
    control, state = clock
    control.start()
    state.created = OSError("access temporarily unavailable")
    with pytest.raises(DiagnosticError):
        control.stop()
    assert control.attempted and len(state.calls) == 1
    state.listed = False
    assert control.confirm_stopped() and not control.attempted
    assert control.report["current_rate"] is None


def test_foreign_native_owner_is_not_restored_or_claimed_normal(clock):
    control, state = clock
    control.start()
    control.address = 0
    state.status_code = 46
    assert control.confirm_stopped() and not control.attempted
    assert control.report["current_rate"] is None
    assert [op for op, _ in state.calls] == ["start", "status"]


@pytest.mark.parametrize("field,value", [("pid", True), ("slot", 1), ("operation", 14)])
def test_wrong_bridge_response_keeps_cleanup_reserved(clock, field, value):
    control, state = clock
    state.malformed = lambda data: data.update({field: value})
    with pytest.raises(DiagnosticError, match="respuesta"):
        control.start()
    assert control.attempted


def test_incomplete_response_keeps_cleanup_reserved(clock):
    control, state = clock
    state.malformed = lambda data: data["clock"].pop("address")
    with pytest.raises(DiagnosticError, match="respuesta"):
        control.start()
    assert control.attempted


@pytest.mark.parametrize("code", [9, 13, 14, 46, 47, 48, 49, 50])
def test_explicit_start_rejection_does_not_send_cleanup_or_drop_pid(clock, code):
    control, state = clock
    state.malformed = lambda data: data.update(status=code)
    with pytest.raises(DiagnosticError):
        control.start()
    assert not control.attempted and control.stop()
    assert [op for op, _ in state.calls] == ["start"]
