import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunt_loop import HuntEngine, HuntWorker
from atlantica_bot.world import Candidate, GridPosition, LocalState, Observation, WorldView

POSITION = GridPosition(52, 193, 340)
NEAR = Candidate(8, 12053, 52, 194, 340, 1, (12053, 77, 88), 1.45173)
FAR = Candidate(7, 12054, 52, 202, 267, 82, (12054, 90, 91), 21)
DETECTOR = CombatDetector(100, 777, "local_context")


def observation(scene=2, player=POSITION, *, pid=100, created=777, native=False, active=False):
    return Observation(
        pid,
        created,
        scene,
        player if scene == 2 else None,
        native,
        LocalState(0, 4 if active else -1, -1, 0),
    )


def view(*candidates, player=POSITION, limit=20):
    return WorldView(player, candidates, 2, range_limit_squared=limit)


def report(code=1, *, candidate=NEAR, pid=100):
    return {
        "pid": pid,
        "slot": candidate.slot,
        "status": code,
        "message": f"result {code}",
        "battle_confirmed": False,
    }


def ready_engine():
    engine = HuntEngine(100, 777, DETECTOR)
    assert not engine.observe(observation(), 0)
    assert engine.observe(observation(), 2)
    return engine


def test_selects_only_verified_nearby_targets_after_stable_map():
    engine = ready_engine()
    assert engine.select(view(FAR, NEAR), 2) == NEAR
    assert engine.select(view(NEAR), 2.1) is None


def test_no_duplicate_request_while_waiting_for_battle_and_one_confirmation():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    for now in (2.5, 3, 4, 5):
        assert not engine.observe(observation(), now)
        assert engine.select(view(NEAR), now) is None
    assert not engine.observe(observation(active=True), 6)
    assert not engine.observe(observation(active=True), 7)
    assert engine.battles == engine.queued == engine.attempts == 1
    assert engine.summary()["last_attack"]["battle_confirmed"] is True
    assert engine.summary()["last_attack"]["confirmation_scene"] == 2


def test_resumes_after_battle_and_stable_return_position_without_auto_battle():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(active=True), 3)
    engine.observe(observation(active=True), 3.5)
    returned = GridPosition(52, 194, 341)
    assert not engine.observe(observation(player=returned), 20)
    assert not engine.observe(observation(player=returned), 21)
    assert engine.observe(observation(player=returned), 22)
    assert engine.select(view(NEAR, player=returned), 22) == NEAR


def test_missing_battle_transition_stops_without_retry():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    assert not engine.observe(observation(3), 5)
    assert engine.last_attack["battle_confirmed"] is False
    assert not engine.observe(observation(), 32.2)
    assert not engine.running and engine.needs_reconnect
    assert engine.queued == 1 and engine.select(view(NEAR), 30) is None


def test_drained_queue_is_not_treated_as_battle_confirmation_and_timeout_keeps_target_history():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.record_transport({"available": True, "queued_bytes": 25, "queue_instance": "1234"}, 2.2)
    engine.record_transport({"available": True, "queued_bytes": 0, "queue_instance": "1234"}, 3)
    assert engine.battles == 0 and not engine.last_attack["battle_confirmed"]
    assert engine.select(view(NEAR), 4) is None
    engine.observe(observation(), 32.2)
    summary = engine.summary()
    assert not summary["running"] and summary["needs_reconnect"]
    assert summary["pending_attack"]["target"]["identity"] == NEAR.identity
    assert summary["transport"]["first"]["queued_bytes"] == 25
    assert summary["transport"]["recent"][-1]["queued_bytes"] == 0
    assert any(event["event"] == "attack_not_confirmed" for event in summary["events"])
    assert summary["queued"] == 1


@pytest.mark.parametrize(
    "changed",
    [
        observation(pid=200),
        observation(created=888),
        observation(native=True),
        observation(player=GridPosition(53, 193, 340)),
    ],
)
def test_instance_native_mode_and_map_changes_stop_the_run(changed):
    engine = ready_engine()
    assert not engine.observe(changed, 3)
    assert not engine.running
    assert engine.attempts == 0


def test_manual_movement_stops_ready_bot():
    engine = ready_engine()
    assert not engine.observe(observation(player=GridPosition(52, 194, 340)), 3)
    assert not engine.running


def test_rejected_target_cooldown_allows_a_different_nearby_mob():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(2), 2.1)
    other = Candidate(9, 12053, 52, 194, 340, 1, (12053, 99, 100), 1)
    assert not engine.observe(observation(), 3)
    assert engine.observe(observation(), 4)
    assert engine.select(view(NEAR, other), 4) == other


@pytest.mark.parametrize("code", [7, 8, 9, 10, 11, 12, 14])
def test_uncertain_or_invalid_native_result_stops_instead_of_repeating(code):
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(code), 2.1)
    assert not engine.running
    assert engine.select(view(NEAR), 10) is None


def test_stopping_with_pending_attack_requires_reconnect():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.stop("user stopped")
    assert engine.needs_reconnect
    assert not engine.observe(observation(), 3)


def test_wrong_process_response_never_starts_another_cycle():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(pid=200), 2.1)
    assert not engine.running and engine.needs_reconnect
    assert engine.queued == 0


def test_unknown_range_stops_without_request():
    engine = ready_engine()
    assert engine.select(view(NEAR, limit=None), 2) is None
    assert not engine.running and engine.attempts == 0


def test_stop_cancels_inflight_worker_and_no_second_request_is_sent(monkeypatch):
    entered, released = threading.Event(), threading.Event()
    signals, calls = [], []

    class Signal:
        def __init__(self, pid):
            self.cancelled = False
            self.closed = False
            signals.append(self)

        def cancel(self):
            self.cancelled = True
            released.set()

        def close(self):
            self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.cancel()
            self.close()

    ticks = iter(range(0, 1000, 2))
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda pid: nullcontext())
    monkeypatch.setattr("atlantica_bot.hunt_loop.Cancellation", Signal)
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda session: observation())
    monkeypatch.setattr("atlantica_bot.hunt_loop.scan_world", lambda session: view(NEAR))

    def send(session, window, candidate, *, cancellation):
        calls.append(candidate)
        entered.set()
        assert released.wait(2)
        assert cancellation.cancelled and not cancellation.closed
        return report(13)

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_attack", send)
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR)
    worker.start()
    assert entered.wait(2)
    worker.stop()
    worker.thread.join(2)
    assert not worker.alive and not worker.engine.running
    assert len(calls) == 1 and signals[0].closed


def test_battle_confirmation_requires_two_samples_and_unknown_state_does_not_repeat_attack():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(active=True), 3)
    engine.observe(observation(3), 3.25)
    assert engine.battles == 0 and not engine.last_attack["battle_confirmed"]
    assert engine.select(view(NEAR), 4) is None
    engine.observe(observation(active=True), 4)
    engine.observe(observation(active=True), 4.25)
    assert engine.battles == 1 and engine.last_attack["battle_confirmed"]


def test_transient_unknown_scene_during_battle_does_not_count_a_second_battle():
    engine = ready_engine()
    for now in (3, 3.5):
        engine.observe(observation(active=True), now)
    engine.observe(observation(3), 4)
    for now in (5, 5.5):
        engine.observe(observation(active=True), now)
    assert engine.battles == 1
    assert not engine.observe(observation(), 6)
    assert engine.observe(observation(), 8)
    for now in (9, 9.5):
        engine.observe(observation(active=True), now)
    assert engine.battles == 2


def test_report_preserves_bounded_observations_and_counts_unchanged_scene_two():
    engine = ready_engine()
    for now in range(3, 43):
        engine.observe(observation(), now)
    summary = engine.summary()
    assert summary["observation_count"] == summary["scene_counts"][2] == 42
    assert len(summary["recent_observations"]) == 24
    assert summary["recent_observations"][-1]["local"]["context_a"] == -1
    assert summary["classification_counts"] == {"map": 42}
    assert summary["first_observation"]["elapsed_seconds"] == 0
    assert summary["profile"]["turn_execution_available"] is False


def test_out_of_range_wait_reports_distance_without_changing_native_limit():
    engine = ready_engine()
    assert engine.select(view(FAR), 2) is None
    assert engine.range_diagnostic == {
        "limit_squared": 20,
        "nearest_slot": FAR.slot,
        "nearest_distance_squared": 21,
        "available_in_range": 0,
        "automatic_approach": False,
    }
    assert engine.running and engine.attempts == 0


def test_calibration_for_another_instance_cannot_start_worker():
    session = SimpleNamespace(creation_time=888, process=SimpleNamespace(pid=100))
    with pytest.raises(DiagnosticError, match="Calibra"):
        HuntWorker(session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR)
