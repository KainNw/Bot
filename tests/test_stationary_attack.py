from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunt_loop import HuntEngine, HuntWorker
from atlantica_bot.navigation import ApproachSettings
from atlantica_bot.profiles import BotProfile
from atlantica_bot.world import (
    Candidate,
    GridPosition,
    LocalState,
    NavigationState,
    Observation,
    WorldView,
)

ORIGIN = GridPosition(52, 193, 340)
IDLE = NavigationState(0x30010000, 0, -1, 0, 0, False, False)
FAR = Candidate(6, 12053, 52, 213, 340, 20, (12053, 77, 0), 400)
DETECTOR = CombatDetector(100, 777, "local_context")


def plan(delay=0):
    return replace(
        BotProfile.default(1), world_attack_mode="stationary", attack_delay_seconds=delay
    )


def observation(*, position=ORIGIN, battle=False, navigation=IDLE, scene=2):
    return Observation(
        100,
        777,
        scene,
        position,
        False,
        LocalState(33 if battle else 1, 0 if battle else -1, -1, 0),
        navigation,
        (float(position.x), 0.0, float(position.y)),
    )


def view(*targets):
    return WorldView(
        ORIGIN,
        targets,
        2,
        range_limit_squared=20,
        player_world_position=(193.0, 0.0, 340.0),
        active_identities=tuple(t.identity for t in targets),
    )


def ready(delay=0):
    bot = HuntEngine(100, 777, DETECTOR, plan(delay))
    assert not bot.observe(observation(), 0)
    assert bot.observe(observation(), 2)
    return bot


def result(target=FAR, status=1):
    return {
        "pid": 100,
        "slot": target.slot,
        "operation": 10,
        "status": status,
        "message": "direct request",
    }


def test_selects_nearest_by_actual_distance_even_beyond_native_range_without_creating_a_route():
    bot = ready()
    grid_closer = replace(
        FAR, slot=7, x=194, identity=(12054, 88, 0), grid_distance=1, distance_squared=500
    )
    assert bot.select(view(grid_closer, FAR), 2) == FAR
    assert bot.phase == "requesting_stationary_attack" and bot.selection_source == "stationary"
    assert bot.range_diagnostic["limit_squared"] == 20
    assert bot.range_diagnostic["available_in_range"] == 0
    assert bot.pursuit is None and bot.route is None and bot.moves == bot.native_requests == 0


def test_radius_and_previous_battle_history_still_exclude_targets():
    bot = ready()
    outside = replace(FAR, x=ORIGIN.x + 61, grid_distance=61)
    assert bot.select(view(outside), 2) is None
    bot.engaged_targets[FAR.identity] = FAR.slot
    assert bot.select(view(FAR), 3) is None
    replacement = replace(FAR, identity=(FAR.kind_id, 999, 0))
    assert bot.select(view(replacement), 4) == replacement


def test_configured_delay_revalidates_stationary_request_without_entering_pursuit():
    bot = ready(3)
    assert bot.select(view(FAR), 2) is None
    assert bot.observe(observation(), 5)
    moved = replace(FAR, slot=8)
    assert bot.select(view(moved), 5) == moved
    assert bot.phase == "requesting_stationary_attack" and bot.pursuit is None


def test_one_direct_request_waits_for_confirmation_and_never_replays_on_server_silence():
    bot = ready()
    bot.select(view(FAR), 2)
    bot.record(FAR, result(), 2.1)
    for now in (3, 5, 20):
        assert not bot.observe(observation(), now)
        assert bot.select(view(FAR), now) is None
    bot.observe(observation(), 32.1)
    assert not bot.running and bot.needs_reconnect and bot.attempts == bot.queued == 1
    assert bot.native_requests == bot.moves == 0 and bot.pursuit is None


def test_battle_confirmation_sets_the_result_without_confusing_an_intermediate_map_frame():
    bot = ready()
    bot.select(view(FAR), 2)
    bot.record(FAR, result(), 2.1)
    assert not bot.observe(observation(battle=True), 3)
    assert bot.anchor is None
    assert not bot.observe(observation(), 3.2) and bot.running
    bot.observe(observation(battle=True), 3.4)
    bot.observe(observation(battle=True), 3.6)
    assert bot.battles == 1 and bot.last_attack["battle_confirmed"]
    assert bot.phase == "battle" and bot.deadline is None and bot.running


@pytest.mark.parametrize("changed", ["grid", "world", "route"])
def test_movement_after_a_queued_direct_request_stops_without_sending_a_stop_or_attack(changed):
    bot = ready()
    bot.select(view(FAR), 2)
    bot.record(FAR, result(), 2.1)
    sample = observation()
    if changed == "grid":
        sample = observation(position=GridPosition(52, 194, 340))
    elif changed == "world":
        sample = replace(sample, world_position=(193.2, 0.0, 340.0))
    else:
        sample = observation(navigation=replace(IDLE, active=True, moving=True))
    bot.observe(sample, 3)
    assert not bot.running and bot.needs_reconnect
    assert bot.last_attack["stationary_movement_observed"]
    assert bot.pursuit is None and bot.route is None and bot.attempts == 1


@pytest.mark.parametrize("code", [17, 20])
def test_pre_send_position_change_waits_for_a_new_stable_map_without_claiming_an_attack(code):
    bot = ready()
    bot.select(view(FAR), 2)
    bot.record(FAR, result(status=code), 2.1)
    assert bot.running and not bot.needs_reconnect and bot.phase == "waiting_map"
    assert bot.deadline is None and bot.queued == 0


def test_stationary_mode_rejects_combining_native_pursuit_or_legacy_route():
    with pytest.raises(DiagnosticError):
        HuntEngine(100, 777, DETECTOR, plan(), native_attack=True)
    with pytest.raises(DiagnosticError):
        HuntEngine(100, 777, DETECTOR, plan(), approach=ApproachSettings(True))


def test_worker_dispatches_only_stationary_request_and_reuses_bound_source_position(monkeypatch):
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    worker = HuntWorker(session, ClientWindow(100, 12345, "Atlantica", 1234), DETECTOR, plan())
    worker.engine = ready()
    worker.cancellation = object()
    calls = []
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: observation())
    monkeypatch.setattr("atlantica_bot.hunt_loop.scan_world", lambda *a, **kw: view(FAR))
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_transport", lambda *a: {})
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: 3)

    def send(session, window, candidate, origin, settings, *, player_position, cancellation):
        calls.append((window.pid, candidate.identity, player_position))
        assert origin == ORIGIN and cancellation is worker.cancellation
        return result()

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_stationary_attack", send)
    for name in (
        "try_native_attack",
        "try_approach",
        "try_attack",
        "stop_movement",
        "stop_native_pursuit",
    ):
        monkeypatch.setattr(
            f"atlantica_bot.hunt_loop.{name}",
            lambda *a, **kw: pytest.fail("Movement or other attack"),
        )
    worker._iteration()
    worker._iteration()
    worker._stop_pursuit(cleanup=True)
    worker._stop_route(cleanup=True)
    assert calls == [(100, FAR.identity, (193.0, 0.0, 340.0))]
    assert worker.engine.queued == 1 and worker.engine.pursuit is None


def test_stationary_encounter_still_executes_opening_magic_after_confirmed_battle(
    turn_frame, monkeypatch
):
    profile = plan()
    profile = replace(
        profile, mercenaries=(replace(profile.mercenaries[0], action="Q"), *profile.mercenaries[1:])
    )
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    worker = HuntWorker(
        session, ClientWindow(100, 12345, "Atlantica", 1234), DETECTOR, profile, execute_turns=True
    )
    worker.cancellation = object()
    now = [0]
    sample = [observation()]
    calls = []
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: now[0])
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: sample[0])
    monkeypatch.setattr("atlantica_bot.hunt_loop.scan_world", lambda *a, **kw: view(FAR))
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_transport", lambda *a: {})
    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", lambda *a: turn_frame)

    def direct(*args, **kwargs):
        calls.append(("world", 10))
        return result()

    def combat(session, window, trial, **kwargs):
        calls.append(("battle", trial.action))
        return {"pid": 100, "operation": trial.operation, "status": 32}

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_stationary_attack", direct)
    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", combat)
    for name in ("try_native_attack", "try_approach", "stop_movement", "stop_native_pursuit"):
        monkeypatch.setattr(
            f"atlantica_bot.hunt_loop.{name}", lambda *a, **kw: pytest.fail("Movement")
        )
    worker._iteration()
    now[0] = 2
    worker._iteration()
    sample[0] = observation(battle=True)
    now[0] = 3
    worker._iteration()
    now[0] = 3.25
    worker._iteration()
    assert calls == [("world", 10), ("battle", "Q")]
    assert worker.engine.last_attack["battle_confirmed"]
    assert worker.engine.execute_turns and worker.turns.queued == 1
