import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunt_loop import HuntEngine, HuntWorker
from atlantica_bot.navigation import ApproachSettings
from atlantica_bot.world import (
    Candidate,
    GridPosition,
    LocalState,
    NavigationState,
    Observation,
    WorldView,
)

ORIGIN = GridPosition(52, 193, 340)
TARGET = Candidate(6, 12053, 52, 202, 340, 9, (12053, 77, 88), 49.44)
ROUTE = NavigationState(0x30010000, 1234, 52, 202, 340, True, True)
IDLE = NavigationState(ROUTE.player_address, 0, -1, 0, 0, False, False)
DETECTOR = CombatDetector(100, 777, "local_context")


def observation(position=ORIGIN, navigation=IDLE, *, battle=False):
    return Observation(
        100,
        777,
        2,
        position,
        local=LocalState(1, 0 if battle else -1, -1, 0),
        navigation=navigation,
    )


def view(*candidates, position=ORIGIN):
    return WorldView(position, candidates, 2, range_limit_squared=20)


def move_report():
    return {
        "pid": 100,
        "slot": TARGET.slot,
        "status": 15,
        "message": "accepted",
        "navigation": ROUTE.summary(),
    }


def stopped(code=16):
    return {"pid": 100, "slot": 0, "status": code, "message": "stopped"}


def ready_engine(*, enabled=True, radius=60):
    engine = HuntEngine(100, 777, DETECTOR, approach=ApproachSettings(enabled, radius))
    assert not engine.observe(observation(), 0)
    assert engine.observe(observation(), 2)
    return engine


def moving_engine():
    engine = ready_engine()
    assert engine.select(view(TARGET), 2) == TARGET
    assert engine.phase == "requesting_approach"
    engine.record_approach(TARGET, move_report(), 2.1)
    return engine


def test_walk_stop_stabilize_attack_battle_and_return_without_auto_battle():
    engine = moving_engine()
    middle = GridPosition(52, 196, 340)
    assert engine.observe(observation(middle, ROUTE), 3)
    assert engine.select(view(replace(TARGET, distance_squared=25), position=middle), 3) is None
    assert engine.phase == "approaching" and engine.attempts == 0
    arrived = GridPosition(52, 198, 340)
    assert engine.observe(observation(arrived, ROUTE), 3.5)
    nearby = replace(TARGET, distance_squared=10)
    assert engine.select(view(nearby, position=arrived), 3.5) is None
    assert engine.phase == "stopping_move" and engine.attempts == 0
    engine.record_movement_stop(stopped(), 3.6)
    assert not engine.observe(observation(arrived), 3.7)
    assert engine.observe(observation(arrived), 5.8)
    assert engine.select(view(nearby, position=arrived), 5.8) == nearby
    engine.record(nearby, {"pid": 100, "slot": 6, "status": 1, "message": "queued"}, 5.9)
    for now in (6, 6.25):
        engine.observe(observation(arrived, battle=True), now)
    assert engine.battles == engine.arrivals == engine.queued == 1
    assert not engine.observe(observation(arrived), 25)
    assert engine.observe(observation(arrived), 27)
    assert engine.origin == ORIGIN and engine.running


def arrived_engine(*, reason="in_range"):
    engine = moving_engine()
    engine.move_reason = reason
    engine.record_movement_stop(stopped(), 3)
    assert not engine.observe(observation(), 3.1)
    assert engine.observe(observation(), 5.2)
    return engine


def test_keeps_approached_identity_when_another_mob_becomes_closer():
    engine = arrived_engine()
    original = replace(TARGET, distance_squared=10)
    closer = replace(original, slot=9, identity=(12053, 99, 0), distance_squared=0.1)
    assert engine.select(view(closer, original), 5.2) == original
    assert engine.selection_source == "approach"
    selection = engine.summary()["events"][-1]
    assert selection["event"] == "target_selected"
    assert selection["target"]["identity"] == TARGET.identity


def test_reused_slot_does_not_silently_replace_arrival_target():
    engine = arrived_engine()
    replacement = replace(TARGET, identity=(12053, 99, 0), distance_squared=1)
    assert engine.select(view(replacement), 5.2) is None
    assert engine.attempts == 0
    assert engine.summary()["events"][-1]["event"] == "arrival_target_unavailable"
    assert engine.observe(observation(), 6.3)
    assert engine.select(view(replacement), 6.3) == replacement
    assert engine.selection_source == "nearby"


def test_naturally_finished_route_is_verified_before_counting_success_or_failure():
    engine = arrived_engine(reason="route_finished")
    assert engine.arrivals == engine.move_failures == 0
    target = replace(TARGET, distance_squared=1)
    assert engine.select(view(target), 5.2) == target
    assert engine.arrivals == 1 and engine.move_failures == 0


def test_finished_route_out_of_range_records_reason_without_attacking_other_mob():
    engine = arrived_engine(reason="route_finished")
    other = replace(TARGET, slot=9, identity=(12053, 99, 0), distance_squared=1)
    assert engine.select(view(TARGET, other), 5.2) is None
    assert engine.move_failures == 1 and engine.arrivals == engine.attempts == 0
    assert engine.last_failed_approach["reason"] == "target_left_range_after_stop"


def test_failed_approach_reason_survives_a_later_successful_arrival():
    engine = moving_engine()
    assert not engine.observe(observation(ORIGIN, ROUTE), 8)
    engine.record_movement_stop(stopped(), 8)
    assert engine.last_failed_approach["reason"] == "stalled"
    assert not engine.observe(observation(), 8.1)
    assert engine.observe(observation(), 10.2)
    other = replace(TARGET, slot=9, identity=(12053, 99, 0))
    assert engine.select(view(other), 10.2) == other
    report = {**move_report(), "slot": 9}
    engine.record_approach(other, report, 10.3)
    engine.move_reason = "in_range"
    engine.record_movement_stop(stopped(), 11)
    assert engine.arrivals == engine.move_failures == 1
    assert engine.last_failed_approach["reason"] == "stalled"
    stops = [event for event in engine.events if event["event"] == "movement_stop_result"]
    assert [event["reason"] for event in stops] == ["stalled", "in_range"]


def test_nearby_mode_preserves_previous_behavior_and_radius_bounds_far_targets():
    assert ready_engine(enabled=False).select(view(TARGET), 2) is None
    limited = ready_engine(radius=5)
    assert limited.select(view(TARGET), 2) is None
    assert limited.moves == limited.attempts == 0
    normal = ready_engine()
    near = replace(TARGET, distance_squared=1)
    assert normal.select(view(TARGET, near), 2) == near
    assert normal.phase == "requesting"


@pytest.mark.parametrize("elapsed,reason", [(7.2, "stalled"), (23, "timeout")])
def test_no_progress_or_total_timeout_requests_stop_without_attacking(elapsed, reason):
    engine = moving_engine()
    assert not engine.observe(observation(ORIGIN, ROUTE), elapsed)
    assert engine.phase == "stopping_move" and engine.move_reason == reason
    engine.record_movement_stop(stopped(), elapsed)
    assert engine.route is None and engine.move_failures == 1 and engine.attempts == 0
    assert not engine.observe(observation(), elapsed + 0.1)
    assert engine.observe(observation(), elapsed + 2.2)
    assert engine.select(view(TARGET), elapsed + 2.2) is None


@pytest.mark.parametrize(
    "field,value", [("x", 203), ("tick", 5555), ("player_address", 0x30020000)]
)
def test_changed_route_is_not_followed_or_replaced(field, value):
    engine = moving_engine()
    assert not engine.observe(observation(ORIGIN, replace(ROUTE, **{field: value})), 3)
    assert not engine.running and engine.attempts == 0


def test_target_disappearance_stops_before_selecting_a_different_target():
    engine = moving_engine()
    assert engine.observe(observation(ORIGIN, ROUTE), 3)
    assert engine.select(view(replace(TARGET, identity=(12053, 99, 0))), 3) is None
    assert engine.phase == "stopping_move" and engine.move_reason == "target_changed"
    assert engine.attempts == 0


def test_leaving_search_area_or_entering_battle_during_approach_never_sends_attack():
    engine = moving_engine()
    outside = GridPosition(52, 300, 340)
    assert not engine.observe(observation(outside, ROUTE), 3)
    assert engine.move_reason == "outside_area"
    engine.record_movement_stop(stopped(), 3.1)
    assert not engine.running and engine.attempts == 0
    engine = moving_engine()
    assert not engine.observe(observation(ORIGIN, ROUTE, battle=True), 3)
    assert not engine.running and engine.needs_reconnect and engine.attempts == 0


def test_invalid_or_failed_stop_prevents_a_new_attack():
    engine = moving_engine()
    engine.record_movement_stop(stopped(21), 3)
    assert not engine.running and engine.needs_reconnect
    assert engine.select(view(replace(TARGET, distance_squared=1)), 4) is None


def test_starting_with_a_foreign_route_does_not_attack_or_replace_it():
    engine = HuntEngine(100, 777, DETECTOR, approach=ApproachSettings(True))
    assert not engine.observe(observation(ORIGIN, ROUTE), 0)
    assert not engine.running and engine.route is None and engine.attempts == engine.moves == 0


def test_unknown_movement_flag_is_reported_and_only_fresh_route_can_be_selected():
    idle_unknown = replace(IDLE, active_raw=255, moving=None, moving_raw=255)
    engine = HuntEngine(100, 777, DETECTOR, approach=ApproachSettings(True))
    assert not engine.observe(observation(ORIGIN, idle_unknown), 0)
    assert engine.observe(observation(ORIGIN, idle_unknown), 2)
    assert engine.select(view(TARGET), 2) == TARGET
    assert engine.phase == "requesting_approach"
    assert engine.summary()["recent_observations"][-1]["navigation"]["moving_raw"] == 255
    assert engine.summary()["first_observation"]["navigation"]["moving_raw"] == 255
    assert engine.moves == engine.attempts == 0


def test_unknown_movement_flag_does_not_prove_a_foreign_route_finished():
    engine = moving_engine()
    changed = replace(IDLE, tick=9999, moving=None, moving_raw=255)
    assert not engine.observe(observation(ORIGIN, changed), 3)
    assert not engine.running and engine.move_reason != "route_finished"
    assert engine.route == ROUTE


def test_route_revision_rejection_does_not_register_a_movement_or_an_attack():
    engine = ready_engine()
    engine.record_approach(
        TARGET, {"pid": 100, "slot": 6, "status": 17, "message": "route changed"}, 3
    )
    assert not engine.running and engine.route is None and engine.moves == engine.attempts == 0


@pytest.mark.parametrize("field,value", [("active", False), ("moving", False)])
def test_inconsistent_raw_navigation_flags_are_rejected(field, value):
    payload = replace(ROUTE, active_raw=1, moving_raw=255, moving=None).summary()
    payload[field] = value
    with pytest.raises(DiagnosticError):
        NavigationState.from_report(payload)


@pytest.mark.parametrize("radius", [0, 121, True, "60"])
def test_invalid_search_radius_is_rejected(radius):
    with pytest.raises(DiagnosticError):
        ApproachSettings(True, radius)


def test_worker_stop_after_approach_acceptance_stops_owned_route_before_releasing_pid(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    signals, actions = [], []
    lease_held = False

    class Lease:
        def __init__(self, pid):
            assert pid == 100

        def __enter__(self):
            nonlocal lease_held
            lease_held = True

        def __exit__(self, *args):
            nonlocal lease_held
            lease_held = False

    class Signal:
        def __init__(self, pid):
            self.cancelled = self.closed = False
            signals.append(self)

        def cancel(self):
            self.cancelled = True
            release.set()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.cancel()
            self.closed = True

    def approach(*args, **kwargs):
        actions.append("approach")
        entered.set()
        assert release.wait(2)
        return move_report()

    def stop(session, window, route):
        actions.append("stop")
        assert lease_held and signals[0].cancelled and not signals[0].closed
        assert window.pid == 100 and route == ROUTE
        return stopped()

    ticks = iter(range(0, 1000, 2))
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", Lease)
    monkeypatch.setattr("atlantica_bot.hunt_loop.Cancellation", Signal)
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda *args, **kw: observation())
    monkeypatch.setattr("atlantica_bot.hunt_loop.scan_world", lambda *args, **kw: view(TARGET))
    monkeypatch.setattr("atlantica_bot.hunt_loop.try_approach", approach)
    monkeypatch.setattr("atlantica_bot.hunt_loop.stop_movement", stop)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.try_attack", lambda *args, **kw: pytest.fail("attack while moving")
    )
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR, approach=ApproachSettings(True)
    )
    worker.start()
    assert entered.wait(2)
    worker.stop()
    worker.thread.join(2)
    assert not worker.alive and actions == ["approach", "stop"]
    assert worker.engine.route is None and not worker.engine.needs_reconnect
    assert not lease_held


def test_worker_does_not_retry_an_uncertain_stop_during_final_cleanup(monkeypatch):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR)
    worker.engine.route = ROUTE
    calls = []

    def stop(*args):
        calls.append(args)
        raise DiagnosticError("unknown result")

    monkeypatch.setattr("atlantica_bot.hunt_loop.stop_movement", stop)
    worker._stop_route()
    worker._stop_route(cleanup=True)
    assert len(calls) == 1 and worker.engine.needs_reconnect
