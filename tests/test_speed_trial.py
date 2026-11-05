import json
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot import speed_trial
from atlantica_bot.clients import ClientWindow
from atlantica_bot.errors import DiagnosticError, WindowUnavailable
from atlantica_bot.session import LiveState
from atlantica_bot.speed_trial import (
    ORIGINAL_RATE,
    TRIAL_RATE,
    SpeedExperiment,
    SpeedResultUnknown,
    float_bits,
    prepare_speed_plan,
    request_speed,
)
from atlantica_bot.world import GridPosition, LocalState, Observation


def snapshot():
    contexts = {}
    for index in range(2):
        wrapper, backend, node, receiver = (
            base + index * 0x1000 for base in (0x20000000, 0x30000000, 0x40000000, 0x50000000)
        )
        contexts[str(index)] = {
            "status": "read",
            "wrapper": wrapper,
            "backend": backend,
            "receiver": receiver,
            "receiver_bindings": [(backend, node), (node + 0x120, receiver)],
            "value": ORIGINAL_RATE if index else 1.0,
        }
    return {
        "fields": {"manager_rate_candidate": {"status": "read", "value": ORIGINAL_RATE}},
        "graphics_rates": {
            "status": "read",
            "shared_receiver": False,
            "table": 0x10000000,
            "getter": {
                "status": "resolved",
                "offset": 0x50,
                "format": "<f",
                "receiver_dereferences": [0, 0x120],
            },
            "contexts": contexts,
        },
    }


@pytest.fixture
def trial_env(turn_frame, monkeypatch, tmp_path):
    state = LiveState(False, 0, False, SimpleNamespace(marker_present=False))
    session = SimpleNamespace(
        process=SimpleNamespace(pid=100),
        creation_time=777,
        directory=tmp_path,
        snapshot=lambda: state,
        system=SimpleNamespace(process_creation_time=lambda _: 777),
    )
    window = ClientWindow(100, 0x1234, "Atlantica", 1000)
    data = snapshot()
    monkeypatch.setattr("atlantica_bot.speed_trial.read_battle_frame", lambda _: turn_frame)
    monkeypatch.setattr("atlantica_bot.speed_trial.read_speed_snapshot", lambda *a: deepcopy(data))
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.read_speed_sample",
        lambda *a: {
            "manager_rate": TRIAL_RATE,
            "battle_graphics_rate": TRIAL_RATE,
            "map_graphics_rate": 1.0,
            "graphics_context_index": 1,
            "phase": 3,
            "turn_number": turn_frame.turn_number,
            "turn_tick": turn_frame.turn_tick,
            "client_tick": 100,
        },
    )
    monkeypatch.setattr("atlantica_bot.speed_trial.BotLease", lambda _: nullcontext())
    monkeypatch.setattr("atlantica_bot.speed_trial.SpeedLease", lambda _: nullcontext())
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.Cancellation",
        lambda _: nullcontext(SimpleNamespace(name="Local\\AtlanticaPanel.Cancel.100.test")),
    )
    monkeypatch.setattr("atlantica_bot.speed_trial.control_hunting", lambda *a: None)
    helper = tmp_path / "AtlanticaBridge.exe"
    helper.write_bytes(b"test fixture")
    helper.with_name("AtlanticaHook.dll").write_bytes(b"test fixture")
    monkeypatch.setattr("atlantica_bot.speed_trial.bridge_path", lambda: helper)
    return session, window, data


def response(plan, *, restore=False, status=None):
    return {
        "pid": plan.pid,
        "thread_id": 1000,
        "operation": 12 if restore else 11,
        "slot": 0,
        "status": status if status is not None else 39 if restore else 38,
        "exception": 0,
        "speed": {
            **plan.binding(),
            "after_manager": ORIGINAL_RATE if restore else TRIAL_RATE,
            "after_graphics": ORIGINAL_RATE if restore else TRIAL_RATE,
            "map_before": 1.0,
            "map_after": 1.0,
            "map_owned_restore": 0,
        },
    }


def test_plan_binds_battle_and_both_graphics_chains_without_writing(trial_env):
    session, _, _ = trial_env
    plan, _ = prepare_speed_plan(session)
    assert plan.pid == 100 and plan.creation_time == 777
    assert plan.roots[0][3] != plan.roots[1][3]
    assert plan.arguments()["speed-root1-3"] == 0x50001000
    assert plan.arguments()["speed-requested-bits"] == float_bits(1.45)


@pytest.mark.parametrize("failure", ["shared", "manager_rate", "graphics_rate", "unavailable"])
def test_plan_blocks_unverified_isolation_or_unexpected_originals(trial_env, failure):
    session, _, data = trial_env
    if failure == "shared":
        data["graphics_rates"]["shared_receiver"] = True
    elif failure == "manager_rate":
        data["fields"]["manager_rate_candidate"]["value"] = 1.45
    elif failure == "graphics_rate":
        data["graphics_rates"]["contexts"]["1"]["value"] = 1.0
    else:
        data["graphics_rates"]["status"] = "unavailable"
    with pytest.raises(DiagnosticError):
        prepare_speed_plan(session)


def test_changed_battle_during_preparation_never_creates_a_plan(trial_env, turn_frame, monkeypatch):
    frames = iter((turn_frame, replace(turn_frame, turn_number=1)))
    monkeypatch.setattr("atlantica_bot.speed_trial.read_battle_frame", lambda _: next(frames))
    with pytest.raises(DiagnosticError, match="cambió"):
        prepare_speed_plan(trial_env[0])


def test_speed_request_uses_exact_pid_window_and_float_bits_and_confirms_only_memory(
    trial_env, monkeypatch
):
    session, window, _ = trial_env
    plan, _ = prepare_speed_plan(session)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["check"] is False and kwargs["timeout"] == 8
        return SimpleNamespace(returncode=0, stdout=json.dumps(response(plan)))

    monkeypatch.setattr("atlantica_bot.speed_trial.subprocess.run", run)
    result = request_speed(session, window, plan, restore=False)
    assert len(calls) == 1 and "--speed-apply" in calls[0]
    for key, value in (
        ("--pid", 100),
        ("--created", 777),
        ("--window", 0x1234),
        ("--thread", 1000),
    ):
        assert calls[0][calls[0].index(key) + 1] == str(value)
    assert result["memory_change_confirmed"] and not result["visual_speedup_confirmed"]


@pytest.mark.parametrize("field", ["pid", "clock", "actor", "after", "operation"])
def test_foreign_or_unconfirmed_reply_preserves_uncertainty(trial_env, monkeypatch, field):
    session, window, _ = trial_env
    plan, _ = prepare_speed_plan(session)
    report = response(plan)
    if field == "pid":
        report["pid"] += 1
    if field == "clock":
        report["speed"]["roots"][1][3] += 4
    if field == "actor":
        report["speed"]["actor_identity"][2] = False
    if field == "after":
        report["speed"]["after_graphics"] = 1.5
    if field == "operation":
        report["operation"] = 12
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(report)),
    )
    with pytest.raises(SpeedResultUnknown):
        request_speed(session, window, plan, restore=False)


def test_restore_does_not_require_native_hunting_to_remain_off(trial_env, monkeypatch):
    session, window, _ = trial_env
    plan, _ = prepare_speed_plan(session)
    session.snapshot = lambda: pytest.fail("Cleanup must use independent native identity checks")
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout=json.dumps(response(plan, restore=True))
        ),
    )
    assert request_speed(session, window, plan, restore=True)["restoration_confirmed"]


def test_request_rejects_a_different_window_before_launch(trial_env, monkeypatch):
    session, _, _ = trial_env
    plan, _ = prepare_speed_plan(session)
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.subprocess.run", lambda *a, **k: pytest.fail("Other PID")
    )
    with pytest.raises(DiagnosticError, match="otra instancia"):
        request_speed(session, ClientWindow(101, 0x1234, "Atlantica", 1000), plan, restore=False)


def test_experiment_restores_after_ten_seconds_or_battle_end_without_reapplying(
    trial_env, monkeypatch
):
    session, window, _ = trial_env
    clock = [100]
    calls = []
    monkeypatch.setattr("atlantica_bot.speed_trial.time.monotonic", lambda: clock[0])

    def send(session, window, plan, *, restore):
        calls.append(restore)
        result = response(plan, restore=restore)
        result["message"] = "restored" if restore else "applied"
        return result

    monkeypatch.setattr("atlantica_bot.speed_trial.request_speed", send)
    experiment = SpeedExperiment(session, window)
    experiment.start()
    battle = Observation(100, 777, 2, GridPosition(127, 1, 1), False, LocalState(33, 0, -1, 0))
    monkeypatch.setattr("atlantica_bot.speed_trial.observe_scene", lambda _: battle)
    assert experiment.active and not experiment.should_restore()
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.observe_scene",
        lambda _: replace(battle, local=LocalState(1, -1, -1, 0)),
    )
    assert experiment.should_restore()
    monkeypatch.setattr("atlantica_bot.speed_trial.observe_scene", lambda _: battle)
    clock[0] = 110
    assert experiment.should_restore()
    experiment.restore()
    assert not experiment.active and experiment.lease is None and calls == [False, True]


def test_unknown_apply_attempts_restoration_and_retains_state_if_cleanup_fails(
    trial_env, monkeypatch
):
    session, window, _ = trial_env
    calls = []

    def send(*a, restore, **kw):
        calls.append(restore)
        raise SpeedResultUnknown("No response")

    monkeypatch.setattr("atlantica_bot.speed_trial.request_speed", send)
    experiment = SpeedExperiment(session, window)
    with pytest.raises(SpeedResultUnknown):
        experiment.start()
    assert experiment.active and experiment.lease is not None
    assert calls == [False, True] and experiment.auto_restore_attempted
    assert not experiment.should_restore()  # No unbounded automatic retries.
    experiment._release()


def test_window_preflight_failure_never_triggers_a_restore(trial_env, monkeypatch):
    calls = []

    def send(*a, restore, **kw):
        calls.append(restore)
        raise WindowUnavailable(100, "minimized")

    monkeypatch.setattr("atlantica_bot.speed_trial.request_speed", send)
    experiment = SpeedExperiment(*trial_env[:2])
    with pytest.raises(WindowUnavailable):
        experiment.start()
    assert not experiment.active and experiment.lease is None and calls == [False]


def test_reused_pid_ends_old_experiment_without_touching_the_new_instance(trial_env, monkeypatch):
    session, window, _ = trial_env
    monkeypatch.setattr("atlantica_bot.speed_trial.request_speed", lambda s, w, p, **k: response(p))
    experiment = SpeedExperiment(session, window)
    experiment.start()
    session.system.process_creation_time = lambda _: 778
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.request_speed", lambda *a, **k: pytest.fail("New instance")
    )
    result = experiment.restore()
    assert result["status"] == "instance_ended" and not result["restoration_confirmed"]
    assert not experiment.active and experiment.lease is None


def test_retired_context_is_distinct_from_confirmed_restoration_and_releases_the_lease(
    trial_env, monkeypatch
):
    session, window, _ = trial_env

    def send(session, window, plan, *, restore):
        result = response(plan, restore=restore, status=42 if restore else 38)
        result["restoration_confirmed"] = False
        result["control_retired"] = restore
        return result

    monkeypatch.setattr("atlantica_bot.speed_trial.request_speed", send)
    experiment = SpeedExperiment(session, window)
    experiment.start()
    result = experiment.restore()
    assert result["control_retired"] and not result["restoration_confirmed"]
    assert not experiment.active and experiment.lease is None


def test_restore_can_revert_only_the_owned_field_that_moved_to_map_context(trial_env, monkeypatch):
    session, window, _ = trial_env
    plan, _ = prepare_speed_plan(session)
    report = response(plan, restore=True)
    report["speed"].update(map_before=TRIAL_RATE, map_after=ORIGINAL_RATE, map_owned_restore=1)
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(report)),
    )
    assert request_speed(session, window, plan, restore=True)["restoration_confirmed"]


def test_blocked_preview_is_kept_in_the_copied_report_without_sending(trial_env, monkeypatch):
    session, window, data = trial_env
    data["graphics_rates"]["shared_receiver"] = True
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.request_speed", lambda *a, **k: pytest.fail("Shared scale")
    )
    experiment = SpeedExperiment(session, window)
    with pytest.raises(DiagnosticError):
        experiment.start()
    assert experiment.report["preview"]["graphics_rates"]["shared_receiver"]
    assert not experiment.active and experiment.lease is None


def monitored_experiment(trial_env, monkeypatch):
    clock = [100.0]
    commands = []
    monkeypatch.setattr("atlantica_bot.speed_trial.time.monotonic", lambda: clock[0])

    def send(session, window, plan, *, restore):
        commands.append(restore)
        return response(plan, restore=restore)

    monkeypatch.setattr("atlantica_bot.speed_trial.request_speed", send)
    battle = Observation(100, 777, 2, GridPosition(127, 1, 1), False, LocalState(33, 0, -1, 0))
    monkeypatch.setattr("atlantica_bot.speed_trial.observe_scene", lambda _: battle)
    experiment = SpeedExperiment(*trial_env[:2])
    experiment.start()
    return experiment, clock, commands


def test_samples_show_persistence_over_time_without_additional_commands(trial_env, monkeypatch):
    experiment, clock, commands = monitored_experiment(trial_env, monkeypatch)
    assert not experiment.should_restore()
    clock[0] = 100.1
    assert not experiment.should_restore()
    assert len(experiment.report["observations"]) == 1
    clock[0] = 104.0
    assert not experiment.should_restore()
    samples = experiment.report["observations"]
    assert [s["elapsed_ms"] for s in samples] == [0, 4000]
    assert experiment.report["monitoring"]["all_samples_match_requested"] is True
    assert experiment.report["visual_speedup_confirmed"] is False
    assert commands == [False]
    clock[0] = 110.0
    assert experiment.should_restore()
    assert experiment.report["monitoring"]["stop_reason"] == "deadline"
    experiment.restore()
    assert experiment.report["monitoring"]["restored_after_ms"] == 10000
    assert commands == [False, True]


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"manager_rate": ORIGINAL_RATE, "battle_graphics_rate": ORIGINAL_RATE}, "rate_changed"),
        ({"manager_rate": ORIGINAL_RATE}, "rate_changed"),
        ({"map_graphics_rate": 1.1}, "map_rate_changed"),
        ({"graphics_context_index": 0}, "battle_state_changed"),
        ({"phase": 4}, "battle_state_changed"),
    ],
)
def test_changed_sample_requests_cleanup_without_reapplying(
    trial_env, monkeypatch, changes, reason
):
    experiment, _, commands = monitored_experiment(trial_env, monkeypatch)
    original = speed_trial.read_speed_sample
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.read_speed_sample", lambda *a: {**original(*a), **changes}
    )
    assert experiment.should_restore()
    assert experiment.report["monitoring"]["stop_reason"] == reason
    assert commands == [False]
    if reason == "rate_changed":
        assert experiment.report["monitoring"]["first_rate_change_ms"] == 0
        assert not experiment.report["monitoring"]["all_samples_match_requested"]
    experiment.restore()
    assert not experiment.active and commands == [False, True]


def test_read_failure_keeps_an_error_sample_and_requests_cleanup(trial_env, monkeypatch):
    experiment, _, commands = monitored_experiment(trial_env, monkeypatch)

    def unavailable(*args):
        raise DiagnosticError("Objeto sustituido")

    monkeypatch.setattr("atlantica_bot.speed_trial.read_speed_sample", unavailable)
    assert experiment.should_restore()
    assert experiment.report["observations"] == [
        {"elapsed_ms": 0, "status": "read_error", "error": "Objeto sustituido"}
    ]
    assert experiment.report["monitoring"]["samples_read"] == 0
    experiment.restore()
    assert commands == [False, True]


def test_deadline_takes_priority_over_sampling(trial_env, monkeypatch):
    experiment, clock, commands = monitored_experiment(trial_env, monkeypatch)
    clock[0] = 110
    monkeypatch.setattr(
        "atlantica_bot.speed_trial.read_speed_sample", lambda *a: pytest.fail("Cleanup first")
    )
    assert experiment.should_restore()
    assert not experiment.report["observations"]
    experiment.restore()
    assert commands == [False, True]


def test_repeated_trial_resets_previous_samples_and_results(trial_env, monkeypatch):
    experiment, clock, commands = monitored_experiment(trial_env, monkeypatch)
    assert not experiment.should_restore()
    experiment.restore()
    assert experiment.report["observations"] and "restore" in experiment.report
    clock[0] = 120
    experiment.start()
    assert not experiment.report["observations"] and "restore" not in experiment.report
    assert experiment.report["monitoring"]["stop_reason"] is None
    assert not experiment.should_restore()
    assert experiment.report["observations"][0]["elapsed_ms"] == 0
    experiment.restore()
    assert commands == [False, True, False, True]


def test_active_ce_speed_owner_blocks_native_trial_before_reading_or_sending(
    trial_env, monkeypatch
):
    session, window, _ = trial_env

    class BusySpeed:
        def __enter__(self):
            raise DiagnosticError("Otro controlador de velocidad")

        def __exit__(self, *args):
            pytest.fail("The blocked controller never acquired ownership")

    monkeypatch.setattr(speed_trial, "SpeedLease", lambda pid: BusySpeed())
    monkeypatch.setattr(
        speed_trial, "prepare_speed_plan", lambda _: pytest.fail("Reserve speed before reading")
    )
    experiment = SpeedExperiment(session, window)
    with pytest.raises(DiagnosticError, match="Otro controlador"):
        experiment.start()
    assert not experiment.active and experiment.lease is None


def test_busy_attack_worker_releases_new_speed_reservation(trial_env, monkeypatch):
    session, window, _ = trial_env
    events = []

    class SpeedReservation:
        def __enter__(self):
            events.append("speed acquired")

        def __exit__(self, *args):
            events.append("speed released")

    class BusyBot:
        def __enter__(self):
            raise DiagnosticError("Bot activo")

        def __exit__(self, *args):
            pytest.fail("The bot lease was not acquired")

    monkeypatch.setattr(speed_trial, "SpeedLease", lambda pid: SpeedReservation())
    monkeypatch.setattr(speed_trial, "BotLease", lambda pid: BusyBot())
    experiment = SpeedExperiment(session, window)
    with pytest.raises(DiagnosticError, match="Bot activo"):
        experiment.start()
    assert events == ["speed acquired", "speed released"]
    assert experiment.lease is None and not experiment.active


def test_direct_native_speed_request_cannot_bypass_ce_owner(trial_env, monkeypatch):
    session, window, _ = trial_env
    plan, _ = prepare_speed_plan(session)

    class BusySpeed:
        def __enter__(self):
            raise DiagnosticError("Velocidad reservada por CE")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(speed_trial, "SpeedLease", lambda pid: BusySpeed())
    monkeypatch.setattr(
        speed_trial.subprocess, "run", lambda *a, **k: pytest.fail("Do not send a speed command")
    )
    with pytest.raises(DiagnosticError, match="reservada por CE"):
        request_speed(session, window, plan, restore=False)
