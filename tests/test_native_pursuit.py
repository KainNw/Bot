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
    NativePursuit,
    NavigationState,
    Observation,
    WorldView,
)

ORIGIN = GridPosition(52, 193, 340)
TARGET = Candidate(6, 12053, 52, 202, 340, 9, (12053, 77, 88), 81)
PURSUIT = NativePursuit(0x30010000, 1234, 52, 202, 340, (202.0, 0.0, 340.0), 1)
IDLE = NavigationState(PURSUIT.player_address, 0, -1, 0, 0, False, False)
DETECTOR = CombatDetector(100, 777, "local_context")


def observation(position=ORIGIN, *, pursuit=None, battle=False, goal=None):
    return Observation(
        100,
        777,
        2,
        position,
        local=LocalState(1, 0 if battle else -1, -1, 0),
        navigation=IDLE,
        world_position=(float(position.x), 0.0, float(position.y)),
        native_goal=goal or (pursuit.world_goal if pursuit else None),
        native_goal_pending_raw=pursuit.pending_raw if pursuit else None,
    )


def view(*targets, position=ORIGIN, limit=20):
    return WorldView(
        position,
        targets,
        2,
        range_limit_squared=limit,
        player_world_position=(float(position.x), 0.0, float(position.y)),
        active_identities=tuple(t.identity for t in targets),
    )


def result(code=22, *, target=TARGET, pursuit=PURSUIT):
    return {
        "pid": 100,
        "slot": target.slot,
        "operation": 4,
        "status": code,
        "message": f"native result {code}",
        "pursuit": pursuit.summary(),
    }


def ready_engine(radius=60):
    engine = HuntEngine(
        100, 777, DETECTOR, approach=ApproachSettings(False, radius), native_attack=True
    )
    assert not engine.observe(observation(), 0)
    assert engine.observe(observation(), 2)
    return engine


def pursuing_engine():
    engine = ready_engine()
    assert engine.select(view(TARGET), 2) == TARGET
    assert engine.phase == "requesting_native_attack"
    assert engine.range_diagnostic["available_in_range"] == 0
    assert engine.range_diagnostic["available_in_search_radius"] == 1
    engine.record_native(TARGET, result(), 2.1)
    return engine


def test_native_pursuit_then_attack_uses_native_range_without_creating_grid_routes():
    engine = pursuing_engine()
    middle = GridPosition(52, 196, 340)
    assert engine.observe(observation(middle, pursuit=PURSUIT), 3)
    assert engine.select(view(replace(TARGET, distance_squared=36), position=middle), 3) is None
    assert engine.native_requests == 1 and engine.attempts == 0
    close = GridPosition(52, 198, 340)
    near = replace(TARGET, distance_squared=16)
    assert engine.observe(observation(close, pursuit=PURSUIT), 4.25)
    assert engine.select(view(near, position=close), 4.25) == near
    engine.record_native(near, result(1, target=near), 4.5)
    assert engine.pursuit is None and engine.deadline == 34.5
    assert engine.pending_pursuit == PURSUIT
    # Native movement can continue after the attack request; do not mistake it for
    # manual movement or replay the attack while waiting for battle confirmation.
    closer = GridPosition(52, 199, 340)
    assert not engine.observe(observation(closer), 5)
    engine.observe(observation(closer, battle=True), 6)
    engine.observe(observation(closer, battle=True), 6.25)
    assert engine.battles == engine.queued == engine.attempts == 1
    assert engine.pending_pursuit is None
    assert engine.moves == 0 and engine.route is None
    assert engine.range_diagnostic["limit_squared"] == 20
    assert not engine.observe(observation(closer), 25)
    assert engine.observe(observation(closer), 27)
    assert engine.origin == ORIGIN and engine.running


def test_radio_is_a_selection_boundary_and_nearby_targets_still_work():
    limited = ready_engine(radius=5)
    assert limited.select(view(TARGET), 2) is None
    engine = ready_engine()
    near = replace(TARGET, slot=9, identity=(12053, 99, 0), x=194, distance_squared=1)
    assert engine.select(view(TARGET, near), 2) == near
    engine.record_native(near, result(1, target=near), 2.1)
    assert engine.queued == 1 and engine.native_requests == 0 and engine.moves == 0


def test_moving_mob_updates_native_goal_at_a_bounded_rate_and_keeps_total_timeout():
    engine = pursuing_engine()
    moved = replace(TARGET, x=205, y=341, distance_squared=100)
    assert engine.observe(observation(pursuit=PURSUIT), 3)
    assert engine.select(view(moved), 3) is None
    assert engine.observe(observation(pursuit=PURSUIT), 4.25)
    assert engine.select(view(moved), 4.25) == moved
    updated = replace(PURSUIT, issued_tick=2234, x=205, y=341, world_goal=(205.0, 0.0, 341.0))
    engine.record_native(moved, result(target=moved, pursuit=updated), 4.5)
    assert engine.pursuit_started == 2.1 and engine.native_requests == 2
    assert not engine.observe(observation(pursuit=updated), 23)
    assert engine.pursuit_reason == "timeout" and engine.phase == "stopping_native_pursuit"


def test_reassigned_slot_uses_fresh_slot_for_the_same_identity():
    engine = pursuing_engine()
    position = GridPosition(52, 198, 340)
    assert engine.observe(observation(position, pursuit=PURSUIT), 4.25)
    moved_slot = replace(TARGET, slot=13, distance_squared=16)
    unrelated = replace(TARGET, identity=(12053, 99, 0), distance_squared=1)
    assert engine.select(view(unrelated, moved_slot, position=position), 4.25) == moved_slot


def test_foreign_goal_is_not_cancelled_or_replaced():
    engine = pursuing_engine()
    assert not engine.observe(observation(pursuit=PURSUIT, goal=(204.0, 0.0, 340.0)), 3)
    assert not engine.running and engine.pursuit is None and engine.attempts == 0


@pytest.mark.parametrize("reason", ["target_changed", "stalled", "outside_area"])
def test_failed_native_pursuit_requests_stop_without_attacking(reason):
    engine = pursuing_engine()
    if reason == "target_changed":
        assert engine.observe(observation(pursuit=PURSUIT), 3)
        assert engine.select(view(), 3) is None
    elif reason == "stalled":
        assert not engine.observe(observation(pursuit=PURSUIT), 8)
    else:
        assert not engine.observe(observation(GridPosition(52, 300, 340), pursuit=PURSUIT), 3)
    assert engine.pursuit_reason == reason
    engine.record_native_stop({"pid": 100, "status": 23}, 8.1)
    assert engine.pursuit is None and engine.native_failures == 1
    assert engine.attempts == 0 and engine.moves == 0
    if reason == "outside_area":
        assert not engine.running
    else:
        assert not engine.observe(observation(), 8.2)
        assert engine.observe(observation(), 10.3)
        assert engine.select(view(TARGET), 10.3) is None


def test_battle_during_native_pursuit_pauses_instead_of_sending_another_attack():
    engine = pursuing_engine()
    engine.observe(observation(pursuit=PURSUIT, battle=True), 3)
    engine.observe(observation(battle=True), 3.25)
    assert engine.running and engine.battles == 1
    assert engine.pursuit is None and engine.queued == engine.attempts == 0


def test_single_battle_sample_does_not_lose_ownership_or_confirm_a_fight():
    engine = pursuing_engine()
    engine.observe(observation(pursuit=PURSUIT, battle=True), 3)
    assert engine.pursuit == PURSUIT and engine.battles == 0
    assert engine.observe(observation(pursuit=PURSUIT), 3.25)
    assert engine.phase == "native_pursuit" and engine.battle_samples == 0
    engine.observe(observation(pursuit=PURSUIT, battle=True), 3.5)
    assert engine.battles == 0
    engine.observe(observation(pursuit=PURSUIT, battle=True), 3.75)
    assert engine.pursuit is None and engine.battles == 1


def test_modes_are_mutually_exclusive():
    with pytest.raises(DiagnosticError):
        HuntEngine(100, 777, DETECTOR, approach=ApproachSettings(True), native_attack=True)


def test_no_replay_when_native_attack_is_queued_but_battle_is_not_observed():
    engine = ready_engine()
    near = replace(TARGET, distance_squared=1)
    engine.select(view(near), 2)
    engine.record_native(near, result(1, target=near), 2.1)
    for now in (3, 5, 10):
        assert not engine.observe(observation(), now)
        assert engine.select(view(near), now) is None
    assert not engine.observe(observation(), 33)
    assert not engine.running and engine.needs_reconnect and engine.queued == 1


def test_stop_cancels_pending_native_request_and_stops_owned_pursuit_before_releasing_pid(
    monkeypatch,
):
    entered, released = threading.Event(), threading.Event()
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
            released.set()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.cancel()
            self.closed = True

    def native(*args, **kwargs):
        actions.append("native_attack")
        entered.set()
        assert released.wait(2)
        return result()

    def stop(session, window, pursuit):
        actions.append("stop_native")
        assert lease_held and signals[0].cancelled and not signals[0].closed
        assert window.pid == 100 and pursuit == PURSUIT
        return {"pid": 100, "status": 23}

    ticks = iter(range(0, 10000, 2))
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", Lease)
    monkeypatch.setattr("atlantica_bot.hunt_loop.Cancellation", Signal)
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: observation())
    monkeypatch.setattr("atlantica_bot.hunt_loop.scan_world", lambda *a, **kw: view(TARGET))
    monkeypatch.setattr("atlantica_bot.hunt_loop.try_native_attack", native)
    monkeypatch.setattr("atlantica_bot.hunt_loop.stop_native_pursuit", stop)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.try_approach", lambda *a, **kw: pytest.fail("grid route")
    )
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.stop_movement", lambda *a, **kw: pytest.fail("grid stop")
    )
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR, native_attack=True
    )
    worker.start()
    assert entered.wait(2)
    worker.stop()
    worker.thread.join(2)
    assert not worker.alive and actions == ["native_attack", "stop_native"]
    assert worker.engine.pursuit is None and not lease_held


def test_uncertain_native_stop_is_not_repeated_during_cleanup(monkeypatch):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR, native_attack=True
    )
    worker.engine = pursuing_engine()
    calls = []

    def stop(*args):
        calls.append(args)
        raise DiagnosticError("unknown stop result")

    monkeypatch.setattr("atlantica_bot.hunt_loop.stop_native_pursuit", stop)
    worker._stop_pursuit()
    worker._stop_pursuit(cleanup=True)
    assert len(calls) == 1 and worker.engine.needs_reconnect


def test_stop_can_cancel_owned_native_movement_after_attack_was_queued(monkeypatch):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR, native_attack=True
    )
    worker.engine = pursuing_engine()
    worker.engine.record_native(TARGET, result(1), 3)
    assert worker.engine.pending_pursuit == PURSUIT and worker.engine.pursuit is None
    calls = []

    def stop(*args):
        calls.append(args)
        assert args[-1] == PURSUIT
        return {"pid": 100, "status": 23}

    monkeypatch.setattr("atlantica_bot.hunt_loop.stop_native_pursuit", stop)
    worker.engine.stop("user stop")
    worker._stop_pursuit(cleanup=True)
    assert len(calls) == 1 and worker.engine.pending_pursuit is None
    assert worker.engine.queued == 1 and worker.engine.needs_reconnect
