import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunt_loop import HuntEngine, HuntWorker
from atlantica_bot.navigation import ApproachSettings, calibrated_radius
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


def observation(position=ORIGIN, navigation=IDLE, *, battle=False, world_position=None):
    return Observation(
        100,
        777,
        2,
        position,
        local=LocalState(1, 0 if battle else -1, -1, 0),
        navigation=navigation,
        world_position=world_position or (float(position.x), 0.0, float(position.y)),
    )


def view(*candidates, position=ORIGIN, world_position=None):
    return WorldView(
        position,
        candidates,
        2,
        range_limit_squared=20,
        player_world_position=world_position or (float(position.x), 0.0, float(position.y)),
        active_identities=tuple(candidate.identity for candidate in candidates),
    )


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


def test_calibration_uses_fresh_coordinates_and_expanded_radius_not_strike_range():
    far = replace(TARGET, x=493, y=340, grid_distance=1, distance_squared=90000)
    assert calibrated_radius(view(far), far.identity) == 302
    engine = ready_engine(enabled=False, radius=302)
    engine.native_attack = True
    assert engine.select(view(far), 2) == far
    assert engine.range_diagnostic["limit_squared"] == 20
    assert not engine.range_diagnostic["available_in_range"]
    assert engine.phase == "requesting_native_attack"
    outside = replace(far, x=496)
    another = ready_engine(enabled=False, radius=302)
    another.native_attack = True
    assert another.select(view(outside), 2) is None


@pytest.mark.parametrize("distance,expected", [(1, 5), (499, 500), (500, 500)])
def test_calibration_clamps_margin_within_supported_bounds(distance, expected):
    target = replace(TARGET, x=ORIGIN.x + distance, y=ORIGIN.y)
    assert calibrated_radius(view(target), target.identity) == expected


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "different_map", "too_far", "not_map"])
def test_calibration_rejects_stale_ambiguous_or_unsupported_targets(invalid):
    target = TARGET
    current = view(target)
    if invalid == "missing":
        current = view()
    elif invalid == "duplicate":
        current = view(target, replace(target, slot=8))
    elif invalid == "different_map":
        current = view(replace(target, map_id=53))
    elif invalid == "too_far":
        current = view(replace(target, x=ORIGIN.x + 501, y=ORIGIN.y))
    else:
        current = replace(current, scene_code=3)
    with pytest.raises(DiagnosticError):
        calibrated_radius(current, target.identity)


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
    assert engine.phase == "approaching" and engine.attempts == 0
    assert not engine.observe(observation(arrived, IDLE), 3.6)
    assert engine.phase == "stopping_move" and engine.attempts == 0
    engine.record_movement_stop(stopped(), 3.7)
    assert not engine.observe(observation(arrived), 3.8)
    assert engine.observe(observation(arrived), 5.9)
    assert engine.select(view(nearby, position=arrived), 5.9) == nearby
    engine.record(nearby, {"pid": 100, "slot": 6, "status": 1, "message": "queued"}, 6)
    for now in (6.25, 6.5):
        engine.observe(observation(arrived, battle=True), now)
    assert engine.battles == engine.arrivals == engine.queued == 1
    assert not engine.observe(observation(arrived), 25)
    assert engine.observe(observation(arrived), 27)
    assert engine.origin == ORIGIN and engine.running


def arrived_engine(*, reason="route_finished"):
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


def test_same_mob_can_move_to_a_different_active_slot_before_attack():
    engine = arrived_engine()
    relocated = replace(TARGET, slot=13, distance_squared=1)
    replacement = replace(TARGET, identity=(12053, 99, 0), distance_squared=0.1)
    assert engine.select(view(replacement, relocated), 5.2) == relocated
    assert engine.selection_source == "approach" and engine.arrivals == 1


def test_route_can_finish_without_changing_destination_or_revision():
    engine = moving_engine()
    idle = replace(ROUTE, active=False, moving=False, active_raw=0, moving_raw=0)
    assert not engine.observe(observation(ORIGIN, idle), 3)
    assert engine.move_reason == "route_finished"
    assert engine.phase == "stopping_move" and engine.attempts == 0


def test_actual_position_must_settle_even_if_grid_does_not_change():
    engine = moving_engine()
    assert not engine.observe(observation(ORIGIN, IDLE), 3)
    engine.record_movement_stop(stopped(), 3.1)
    for now, x in ((3.2, 193.0), (5.3, 193.25), (7.4, 193.5)):
        assert not engine.observe(observation(world_position=(x, 0.0, 340.0)), now)
        assert engine.select(view(replace(TARGET, distance_squared=1)), now) is None
    settled = (193.5, 0.0, 340.0)
    assert engine.observe(observation(world_position=settled), 9.5)
    assert (
        engine.select(view(replace(TARGET, distance_squared=1), world_position=settled), 9.5)
        is not None
    )
    assert engine.attempts == 0 and engine.arrivals == 1


def test_movement_between_observation_and_scan_restarts_stability_wait():
    engine = arrived_engine()
    drifted = (193.25, 0.0, 340.0)
    assert (
        engine.select(view(replace(TARGET, distance_squared=1), world_position=drifted), 5.2)
        is None
    )
    assert engine.phase == "waiting_map" and engine.arrivals == engine.attempts == 0
    assert engine.arrival_target == TARGET
    assert not engine.observe(observation(world_position=drifted), 5.3)
    assert engine.observe(observation(world_position=drifted), 7.4)
    assert (
        engine.select(view(replace(TARGET, distance_squared=1), world_position=drifted), 7.4)
        is not None
    )


def test_physical_progress_inside_one_grid_cell_does_not_count_as_stalled():
    engine = moving_engine()
    for now, x in ((6, 193.1), (10, 193.2), (14, 193.3)):
        assert engine.observe(observation(navigation=ROUTE, world_position=(x, 0.0, 340.0)), now)
        assert engine.phase == "approaching" and not engine.move_reason


def test_missing_actual_position_does_not_allow_an_attack():
    engine = HuntEngine(100, 777, DETECTOR, approach=ApproachSettings(True))
    assert not engine.observe(replace(observation(), world_position=None), 0)
    assert not engine.running and engine.needs_reconnect and engine.attempts == 0


def test_worker_observes_residual_movement_while_waiting_after_route_finished(monkeypatch):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR, approach=ApproachSettings(True)
    )
    worker.engine = moving_engine()
    assert not worker.engine.observe(observation(ORIGIN, IDLE), 3)
    worker.engine.record_movement_stop(stopped(), 3.1)

    def observe(session_arg, *, include_navigation, allow_player_movement):
        assert session_arg is session and include_navigation and allow_player_movement
        return observation(world_position=(193.25, 0.0, 340.0))

    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: 3.5)
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", observe)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.try_attack", lambda *args, **kw: pytest.fail("still moving")
    )
    worker._iteration()
    assert worker.engine.running and worker.engine.phase == "resuming"
    assert worker.engine.attempts == worker.engine.arrivals == 0


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
    engine.move_reason = "route_finished"
    engine.record_movement_stop(stopped(), 11)
    assert not engine.observe(observation(), 11.1)
    assert engine.observe(observation(), 13.2)
    assert engine.select(view(replace(other, distance_squared=1)), 13.2) is not None
    assert engine.arrivals == engine.move_failures == 1
    assert engine.last_failed_approach["reason"] == "stalled"
    stops = [event for event in engine.events if event["event"] == "movement_stop_result"]
    assert [event["reason"] for event in stops] == ["stalled", "route_finished"]


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
    assert engine.attempts == 0
    if field == "player_address":
        assert not engine.running and engine.needs_reconnect
    else:
        assert engine.running and engine.manual_active and engine.route is None


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
    assert engine.running and engine.phase == "confirming_battle" and engine.route is not None
    assert not engine.observe(observation(ORIGIN, ROUTE, battle=True), 3.25)
    assert engine.running and not engine.needs_reconnect and engine.attempts == 0
    assert engine.phase == "battle" and engine.route is None and engine.battles == 1


def test_invalid_or_failed_stop_prevents_a_new_attack():
    engine = moving_engine()
    engine.record_movement_stop(stopped(21), 3)
    assert not engine.running and engine.needs_reconnect
    assert engine.select(view(replace(TARGET, distance_squared=1)), 4) is None


def test_starting_with_a_foreign_route_does_not_attack_or_replace_it():
    engine = HuntEngine(100, 777, DETECTOR, approach=ApproachSettings(True))
    assert not engine.observe(observation(ORIGIN, ROUTE), 0)
    assert engine.running and engine.manual_active and engine.route is None
    assert engine.attempts == engine.moves == 0


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
    assert engine.route is None  # The old ownership is released without stopping the foreign route.


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


@pytest.mark.parametrize("radius", [0, 4, 501, True, "60"])
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
