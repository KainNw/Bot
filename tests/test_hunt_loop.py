import threading
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.battle import BattleTrial
from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import BeforeSendChanged, DiagnosticError, WindowUnavailable
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
        world_position=(float(player.x), 0.0, float(player.y)) if player and scene == 2 else None,
    )


def view(*candidates, player=POSITION, limit=20, active_identities=None):
    return WorldView(
        player,
        candidates,
        2,
        range_limit_squared=limit,
        player_world_position=(float(player.x), 0.0, float(player.y)),
        active_identities=active_identities
        if active_identities is not None
        else tuple(candidate.identity for candidate in candidates),
    )


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


@pytest.mark.parametrize("delay", [0, 0.25, 1, 3, 60])
def test_attack_delay_uses_deadline_and_revalidates_mob_without_changing_strike_range(delay):
    engine = ready_engine()
    engine.profile = replace(BotProfile.default(1), attack_delay_seconds=delay)
    if delay == 0:
        assert engine.select(view(NEAR), 2) == NEAR
        return
    assert engine.select(view(NEAR), 2) is None and engine.phase == "attack_delay"
    assert engine.observe(observation(), 2.1)
    assert engine.select(view(NEAR), 2.1) is None
    # The same actor moved table slots. Use the fresh slot, never the stale entry.
    moved = replace(NEAR, slot=12)
    assert engine.observe(observation(), 2 + delay)
    assert engine.select(view(moved), 2 + delay) == moved
    assert engine.phase == "requesting" and engine.attempts == 0
    assert engine.range_diagnostic["limit_squared"] == 20


def test_attack_delay_pins_identity_and_restarts_for_replacement_mob():
    engine = ready_engine()
    engine.profile = replace(BotProfile.default(1), attack_delay_seconds=3)
    assert engine.select(view(NEAR), 2) is None
    closer = replace(NEAR, slot=12, identity=(12053, 999, 0), distance_squared=0.5)
    assert engine.observe(observation(), 3)
    assert engine.select(view(NEAR, closer), 3) is None
    assert engine.delayed_target == NEAR
    assert engine.observe(observation(), 4)
    assert engine.select(view(closer), 4) is None
    assert engine.delayed_target is None
    assert engine.observe(observation(), 5)
    assert engine.select(view(closer), 5) is None
    assert engine.attack_ready_at == 8


@pytest.mark.parametrize("cause", ["manual_walk", "battle", "stop"])
def test_attack_delay_can_be_interrupted_without_sending_a_world_request(cause):
    engine = ready_engine()
    engine.profile = replace(BotProfile.default(1), attack_delay_seconds=60)
    assert engine.select(view(NEAR), 2) is None
    if cause == "manual_walk":
        engine.observe(observation(player=GridPosition(52, 194, 340)), 3)
        assert engine.phase == "manual_movement"
    elif cause == "battle":
        engine.observe(observation(active=True), 3)
        engine.observe(observation(active=True), 3.1)
        assert engine.phase == "battle" and engine.battle_entry["source"] == "external"
    else:
        engine.stop("Parada solicitada")
    assert engine.delayed_target is None and engine.attack_ready_at is None
    assert engine.attempts == engine.queued == 0


def test_selects_only_verified_nearby_targets_after_stable_map():
    engine = ready_engine()
    assert engine.select(view(FAR, NEAR), 2) == NEAR
    assert engine.select(view(NEAR), 2.1) is None


def test_zero_delay_detects_new_nearby_mob_on_next_fast_scan():
    engine = ready_engine()
    engine.profile = replace(BotProfile.default(1), attack_delay_seconds=0)
    assert engine.select(view(), 2) is None
    assert not engine.observe(observation(), 2.05)
    assert engine.observe(observation(), 2.11)
    assert engine.select(view(NEAR), 2.11) == NEAR


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
    fresh = replace(NEAR, slot=9, identity=(12053, 99, 100), distance_squared=3)
    assert engine.select(view(NEAR, fresh, player=returned), 22) == fresh
    assert engine.range_diagnostic["excluded_previously_engaged"] == 1
    assert engine.summary()["target_history"] == [{"slot": NEAR.slot, "identity": NEAR.identity}]


@pytest.mark.parametrize("distance", [1, 49])
def test_confirmed_target_stays_excluded_from_attack_and_approach_after_cooldown(distance):
    engine = ready_engine()
    engine.approach = ApproachSettings(enabled=True)
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(active=True), 3)
    engine.observe(observation(active=True), 3.5)
    assert not engine.observe(observation(), 20)
    assert engine.observe(observation(), 22)
    visible = replace(NEAR, distance_squared=distance)
    for now in (22, 60, 600):
        assert engine.select(view(visible), now) is None
    assert engine.running and engine.attempts == engine.battles == 1
    assert engine.moves == 0 and engine.range_diagnostic["excluded_previously_engaged"] == 1
    # Reusing the actor slot for a different identity must not block a fresh mob
    # of the same species, even at the same coordinates.
    respawn = replace(visible, identity=(NEAR.kind_id, 999, 88))
    assert engine.select(view(respawn), 601) == respawn
    assert engine.phase == ("requesting" if distance <= 20 else "requesting_approach")
    assert engine.summary()["target_history"] == []


def test_engaged_identity_is_excluded_across_slot_reassignment_and_filtered_scans():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(active=True), 3)
    engine.observe(observation(active=True), 3.5)
    assert not engine.observe(observation(), 20)
    assert engine.observe(observation(), 22)
    # A filtered corpse remains active, and a new mob reuses its former slot.
    fresh = replace(NEAR, identity=(12053, 99, 100), distance_squared=3)
    active = (NEAR.identity, fresh.identity)
    assert engine.select(view(active_identities=active), 22) is None
    assert len(engine.engaged_targets) == 1
    relocated = replace(NEAR, slot=13)
    # A partially unreadable active collection cannot clear the exclusion either.
    assert engine.select(replace(view(relocated), active_identities=None), 23) is None
    assert engine.select(view(relocated, fresh), 24) == fresh
    assert engine.range_diagnostic["excluded_previously_engaged"] == 1


def test_missing_battle_transition_keeps_watching_without_retry_or_reconnect():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    assert not engine.observe(observation(3), 5)
    assert engine.last_attack["battle_confirmed"] is False
    assert not engine.observe(observation(), 32.2)
    assert engine.running and not engine.needs_reconnect
    assert engine.phase == "waiting_late_battle" and engine.battle_wait_delayed
    assert engine.queued == 1 and engine.select(view(NEAR), 30) is None


def test_drained_queue_is_not_confirmation_and_delayed_wait_keeps_pending_target():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    engine.record_transport({"available": True, "queued_bytes": 25, "queue_instance": "1234"}, 2.2)
    engine.record_transport({"available": True, "queued_bytes": 0, "queue_instance": "1234"}, 3)
    assert engine.battles == 0 and not engine.last_attack["battle_confirmed"]
    assert engine.select(view(NEAR), 4) is None
    engine.observe(observation(), 32.2)
    summary = engine.summary()
    assert summary["running"] and not summary["needs_reconnect"]
    assert summary["pending_attack"]["target"]["identity"] == NEAR.identity
    assert summary["transport"]["first"]["queued_bytes"] == 25
    assert summary["transport"]["recent"][-1]["queued_bytes"] == 0
    assert any(event["event"] == "battle_confirmation_delayed" for event in summary["events"])
    assert summary["pending_attack"]["new_world_attacks_blocked"]
    assert summary["queued"] == 1


def test_delayed_battle_is_confirmed_once_then_search_resumes_after_stable_map():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    for now in (32.2, 40, 90, 120):
        assert not engine.observe(observation(), now)
        assert engine.select(view(NEAR, FAR), now) is None
        assert engine.attempts == engine.queued == 1
    assert engine.delayed_battle_requests == 1
    assert sum(e["event"] == "battle_confirmation_delayed" for e in engine.events) == 1
    assert not engine.observe(observation(active=True), 121)
    assert engine.pending_target == NEAR and not engine.battles
    assert not engine.observe(observation(active=True), 121.25)
    assert not engine.observe(observation(active=True), 121.5)
    assert engine.phase == "battle" and engine.late_battles_observed == 1
    assert engine.last_attack["confirmation_delayed"]
    assert engine.last_attack["seconds_to_observed_battle"] == 119.15
    assert engine.deadline is None and engine.pending_target is None
    assert not engine.needs_reconnect and not engine.battle_wait_delayed
    assert not engine.observe(observation(), 130)
    assert engine.observe(observation(), 132)
    fresh = replace(NEAR, identity=(12053, 123, 0), slot=12)
    assert engine.select(view(NEAR, fresh), 132) == fresh


def test_transient_battle_sample_does_not_release_a_delayed_pending_request():
    engine = ready_engine()
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(), 32.2)
    engine.observe(observation(active=True), 40)
    engine.observe(observation(), 40.25)
    assert engine.running and engine.phase == "waiting_late_battle"
    assert engine.battles == 0 and engine.pending_target == NEAR
    assert engine.select(view(NEAR), 50) is None
    assert engine.delayed_battle_requests == 1


def test_first_observation_after_long_read_gap_can_confirm_a_late_battle():
    engine = ready_engine()
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(active=True), 70)
    engine.observe(observation(active=True), 70.25)
    assert engine.running and engine.phase == "battle"
    assert engine.delayed_battle_requests == engine.late_battles_observed == 1
    assert engine.last_attack["confirmation_delayed"] and not engine.needs_reconnect


@pytest.mark.parametrize(
    "cause", ["manual_stop", "instance_changed", "native_active", "map_changed"]
)
def test_delayed_watch_still_stops_on_explicit_stop_or_changed_instance_or_map(cause):
    engine = ready_engine()
    engine.record(NEAR, report(), 2.1)
    engine.observe(observation(), 32.2)
    if cause == "manual_stop":
        engine.stop("Parada solicitada")
    else:
        sample = (
            observation(pid=200)
            if cause == "instance_changed"
            else observation(native=True)
            if cause == "native_active"
            else observation(player=GridPosition(53, 193, 340))
        )
        engine.observe(sample, 40)
    assert not engine.running and engine.needs_reconnect
    engine.observe(observation(active=True), 41)
    engine.observe(observation(active=True), 41.25)
    assert engine.battles == 0 and engine.queued == 1


@pytest.mark.parametrize("code", [7, 9, 10, 11, 12, 14])
def test_unknown_or_rejected_helper_result_is_never_converted_to_a_late_battle_watch(code):
    engine = ready_engine()
    engine.record(NEAR, report(code), 2.1)
    assert not engine.running and engine.needs_reconnect
    assert engine.deadline is None and not engine.battle_wait_delayed
    assert not engine.observe(observation(active=True), 40)


def test_transport_clock_does_not_evict_selection_and_battle_events():
    engine = ready_engine()
    engine.select(view(NEAR), 2)
    engine.record(NEAR, report(), 2.1)
    state = {"available": True, "queued_bytes": 25, "queue_instance": "1234"}
    for tick in range(50):
        engine.record_transport({**state, "client_tick": tick}, 2.2 + tick / 10)
    events = engine.summary()["events"]
    assert [event["event"] for event in events] == [
        "target_selected",
        "attack_result",
        "transport_observed",
    ]
    assert engine.summary()["transport"]["first"]["client_tick"] == 0
    assert engine.summary()["transport"]["recent"][-1]["client_tick"] == 49
    engine.record_transport({**state, "queued_bytes": 0, "client_tick": 50}, 7.2)
    assert engine.summary()["events"][-1]["transport"]["queued_bytes"] == 0
    engine.observe(observation(active=True), 7.5)
    engine.observe(observation(active=True), 8)
    assert engine.summary()["events"][-1]["event"] == "battle_confirmed"


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


def test_manual_movement_pauses_and_resumes_ready_bot_from_new_position():
    engine = ready_engine()
    moved = GridPosition(52, 194, 340)
    assert not engine.observe(observation(player=moved), 3)
    assert engine.running and engine.manual_active and engine.phase == "manual_movement"
    assert not engine.observe(observation(player=moved), 4)
    assert engine.observe(observation(player=moved), 5)
    assert not engine.manual_active and engine.origin == moved and engine.attempts == 0


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
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: observation())
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


@pytest.mark.parametrize("previous_request", ["none", "deadline", "route_cleanup"])
def test_blocked_window_preflight_stops_worker_without_losing_previous_uncertainty(
    turn_frame, monkeypatch, previous_request
):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica", 1234), DETECTOR, execute_turns=True
    )
    trial = BattleTrial(turn_frame, turn_frame.units[0], turn_frame.units[2], "basic")
    worker.turns.inflight = trial
    if previous_request == "deadline":
        worker.engine.deadline = 1234
    if previous_request == "route_cleanup":
        worker.engine.route = NavigationState(0x500000, 123, 52, 193, 340, True, True)
    calls = []

    def rejected(*args):
        calls.append(args)
        raise WindowUnavailable(100, "disabled")

    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda _: nullcontext())
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.Cancellation",
        lambda _: nullcontext(SimpleNamespace(cancel=lambda: None)),
    )
    monkeypatch.setattr(worker, "_iteration", rejected)
    monkeypatch.setattr(worker.stop_event, "wait", lambda _: False)
    monkeypatch.setattr("atlantica_bot.hunt_loop.stop_movement", rejected)
    worker._run()
    assert not worker.engine.running and not worker.turns.running
    assert worker.turns.inflight is None and not worker.turns.ledger
    assert worker.engine.needs_reconnect is (previous_request != "none")
    assert len(calls) == (2 if previous_request == "route_cleanup" else 1)
    assert "bloqueada" in worker.engine.message
    if previous_request == "route_cleanup":
        assert "Parada del desplazamiento sin confirmar" in worker.engine.message


def test_unstable_pre_send_snapshot_does_not_leave_a_phantom_battle_order(turn_frame, monkeypatch):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica", 1234), DETECTOR, execute_turns=True
    )
    calls = []
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda _: nullcontext())
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.Cancellation",
        lambda _: nullcontext(SimpleNamespace(cancel=lambda: None)),
    )
    monkeypatch.setattr(worker.stop_event, "wait", lambda _: False)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: observation(active=True)
    )
    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", lambda _: turn_frame)

    def send(session, window, trial, **kwargs):
        calls.append(trial)
        if len(calls) == 1:
            raise BeforeSendChanged("Estado en transición antes de abrir el puente")
        worker.stop_event.set()
        return {"pid": 100, "operation": trial.operation, "status": 26}

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    worker._run()
    assert len(calls) == 2 and calls[0].key() == calls[1].key()
    assert worker.turns.queued == 1 and len(worker.turns.ledger) == 1
    assert worker.turns.inflight is None and not worker.engine.needs_reconnect


@pytest.mark.parametrize("execute_turns", [False, True])
def test_worker_dispatches_turns_only_when_enabled_and_never_scans_world_in_battle(
    turn_frame, monkeypatch, execute_turns
):
    calls, reads, ledger = [], [], set()
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    window = ClientWindow(100, 0x1234, "Atlantica", 1234)
    worker = HuntWorker(
        session,
        window,
        DETECTOR,
        execute_turns=execute_turns,
        battle_ledger=ledger,
        native_attack=True,
    )
    signal = worker.cancellation = object()
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene", lambda *args, **kwargs: observation(active=True)
    )
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.scan_world", lambda *args, **kwargs: pytest.fail("world scan")
    )

    def read_frame(selected_session):
        assert selected_session is session
        reads.append(1)
        return turn_frame

    def send(selected_session, selected_window, trial, *, cancellation):
        assert selected_session is session and selected_window is window
        assert cancellation is signal
        calls.append(trial)
        return {"pid": 100, "operation": trial.operation, "status": 26}

    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", read_frame)
    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    worker._iteration()
    assert not calls and not reads  # Two observations are needed to enter battle.
    worker._iteration()
    worker._iteration()
    assert worker.engine.phase == "battle" and worker.engine.battles == 1
    assert len(calls) == int(execute_turns)
    assert bool(reads) is execute_turns
    assert len(ledger) == int(execute_turns)
    if execute_turns:
        assert worker.engine.summary()["combat"]["queued"] == 1
        assert len(worker.engine.summary()["combat"]["roster"]) == 9


@pytest.mark.parametrize("first_code,expected_calls", [(37, 2), (36, 1), (10, 1), (11, 1)])
def test_instant_loot_reads_fresh_after_definite_rejection_without_wait_or_uncertain_repeat(
    turn_frame, monkeypatch, first_code, expected_calls
):
    frame = replace(
        turn_frame,
        units=tuple(replace(u, life=0) if u.world_slot != 1 else u for u in turn_frame.units),
    )
    worker = HuntWorker(
        SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777),
        ClientWindow(100, 12345, "Atlantica", 1234),
        DETECTOR,
        profile=replace(BotProfile.default(1), collect_remaining_loot=True),
    )
    reads, requests = [], []
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: observation(active=True)
    )

    def read_frame(_):
        reads.append(1)
        return frame

    def send(_session, _window, trial, **_kwargs):
        requests.append(trial)
        return {
            "pid": 100,
            "operation": trial.operation,
            "status": first_code if len(requests) == 1 else 36,
        }

    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", read_frame)
    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    worker._iteration()
    worker._iteration()
    assert len(requests) == len(reads) == expected_calls
    assert all(t.action == "loot" for t in requests)
    if expected_calls == 2:
        assert requests[0].target != requests[1].target
        assert worker.turns.loot_queued == 1 and worker.engine.running
    else:
        assert worker.turns.loot_queued == int(first_code == 36)


@pytest.mark.parametrize("mode", ["nearby", "native", "stationary"])
@pytest.mark.parametrize("execute_turns", [False, True])
def test_worker_handles_late_battle_without_resending_world_attack_or_losing_pid(
    turn_frame, monkeypatch, mode, execute_turns
):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    window = ClientWindow(100, 0x1234, "Atlantica", 1234)
    profile = replace(BotProfile.default(1), world_attack_mode=mode)
    worker = HuntWorker(
        session,
        window,
        DETECTOR,
        profile,
        native_attack=mode == "native",
        execute_turns=execute_turns,
    )
    worker.engine.observe(observation(), 0)
    worker.engine.observe(observation(), 2)
    assert worker.engine.select(view(NEAR), 2) == NEAR
    worker.engine.record(NEAR, report(), 2.1)
    worker.seen_map = True
    signal = worker.cancellation = object()
    clock, scenes, calls = [33.0], [observation()], []
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", lambda *a, **k: scenes[0])
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_transport",
        lambda *a: {"available": True, "queued_bytes": 0},
    )
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.scan_world", lambda *a, **k: pytest.fail("Pending world attack")
    )
    for name in ("try_attack", "try_native_attack", "try_stationary_attack"):
        monkeypatch.setattr(
            f"atlantica_bot.hunt_loop.{name}", lambda *a, **k: pytest.fail("Duplicate world attack")
        )
    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", lambda _: turn_frame)

    def send(selected_session, selected_window, trial, *, cancellation):
        assert selected_session is session and selected_window is window
        assert cancellation is signal
        calls.append(trial)
        return {"pid": 100, "operation": trial.operation, "status": 26}

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    worker._iteration()
    assert worker.engine.phase == "waiting_late_battle" and not calls
    scenes[0], clock[0] = observation(active=True), 45
    worker._iteration()
    assert worker.engine.phase == "confirming_battle" and not calls
    clock[0] = 45.25
    worker._iteration()
    clock[0] = 45.5
    worker._iteration()
    assert worker.engine.running and not worker.engine.needs_reconnect
    assert worker.session is session and worker.window.pid == 100
    assert worker.engine.phase == "battle" and worker.engine.late_battles_observed == 1
    assert worker.engine.queued == worker.engine.attempts == 1
    assert len(calls) == int(execute_turns)


def test_battle_frame_race_to_map_does_not_dispatch_or_require_reconnection(monkeypatch):
    session = SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100))
    worker = HuntWorker(
        session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR, execute_turns=True
    )
    worker.engine.observe(observation(active=True), 0)
    worker.engine.observe(observation(active=True), 1)
    scenes = iter((observation(active=True), observation()))
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene", lambda *args, **kwargs: next(scenes)
    )

    def read_frame(_):
        raise DiagnosticError("The battle has already ended")

    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", read_frame)
    worker._iteration()
    assert worker.engine.running and not worker.engine.needs_reconnect
    assert worker.engine.phase == "resuming" and worker.turns.queued == 0


def test_stop_during_native_combat_request_uses_worker_cancellation_without_next_order(
    turn_frame, monkeypatch
):
    entered, released = threading.Event(), threading.Event()
    signals, calls = [], []

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

    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda pid: nullcontext())
    monkeypatch.setattr("atlantica_bot.hunt_loop.Cancellation", Signal)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene", lambda *args, **kwargs: observation(active=True)
    )
    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", lambda _: turn_frame)

    def send(session, window, trial, *, cancellation):
        calls.append(trial)
        entered.set()
        assert released.wait(2)
        assert cancellation.cancelled and not cancellation.closed
        return {"pid": 100, "operation": trial.operation, "status": 13}

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    worker = HuntWorker(
        SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100)),
        ClientWindow(100, 0x1234, "Atlantica"),
        DETECTOR,
        execute_turns=True,
    )
    worker.start()
    assert entered.wait(2)
    worker.stop()
    worker.thread.join(2)
    assert not worker.alive and not worker.engine.running and not worker.turns.running
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
    assert summary["profile"]["turn_execution_available"] is True
    assert summary["combat"]["enabled"] is False


def test_out_of_range_wait_reports_distance_without_changing_native_limit():
    engine = ready_engine()
    assert engine.select(view(FAR), 2) is None
    assert engine.range_diagnostic == {
        "limit_squared": 20,
        "nearest_slot": FAR.slot,
        "nearest_distance_squared": 21,
        "available_in_range": 0,
        "available_in_search_radius": None,
        "excluded_previously_engaged": 0,
        "automatic_approach": False,
        "native_attack": False,
        "stationary_attack": False,
        "search_radius": None,
    }
    assert engine.running and engine.attempts == 0


@pytest.mark.parametrize(
    "enabled,stop_fault,general",
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, False, True),
        (True, True, True),
    ],
)
def test_worker_owns_speed_until_cancelled_and_restore_is_confirmed(
    monkeypatch, enabled, stop_fault, general
):
    lifecycle = []

    class Lease:
        def __init__(self, name):
            self.name = name

        def __enter__(self):
            lifecycle.append("enter " + self.name)
            return self

        def __exit__(self, *args):
            lifecycle.append("exit " + self.name)

    class Signal(Lease):
        def __init__(self, pid):
            super().__init__("cancel")
            self.cancelled = False

        def cancel(self):
            self.cancelled = True
            lifecycle.append("cancel")

    class Clock:
        def __init__(self, session, window, signal, rate):
            assert rate == 1.25
            self.signal, self.attempted = signal, True
            self.report = {"armed": True, "current_rate": 1.0, "message": "Esperando combate"}

        def start(self):
            lifecycle.append("start speed")

        def read(self):
            return self.report

        def stop(self):
            assert self.signal.cancelled and "exit speed" not in lifecycle
            lifecycle.append("stop speed")
            if stop_fault:
                raise DiagnosticError("ack lost")
            self.attempted = False
            self.report.update(armed=False, current_rate=1.0)

        def confirm_stopped(self):
            assert "exit speed" not in lifecycle and "exit cancel" not in lifecycle
            lifecycle.append("confirm speed")
            self.attempted = False
            self.report.update(armed=False, current_rate=1.0)

    monkeypatch.setattr("atlantica_bot.hunt_loop.SpeedLease", lambda pid: Lease("speed"))
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda pid: Lease("bot"))
    monkeypatch.setattr("atlantica_bot.hunt_loop.Cancellation", Signal)

    def other_mode(*_args):
        pytest.fail("The unselected Speed mode must not start")

    monkeypatch.setattr("atlantica_bot.hunt_loop.NativeClock", other_mode if general else Clock)
    worker = HuntWorker(
        SimpleNamespace(creation_time=777, process=SimpleNamespace(pid=100)),
        ClientWindow(100, 0x1234, "Atlantica"),
        DETECTOR,
        profile=replace(
            BotProfile.default(1),
            battle_speed_enabled=enabled and not general,
            general_speed_enabled=enabled and general,
            general_speed_rate=2.0,
        ),
    )
    monkeypatch.setattr(worker, "_iteration", lambda: worker.engine.stop("Finished"))
    worker._run()
    assert not worker.engine.running and not worker.engine.needs_reconnect
    if enabled and not general:
        assert lifecycle[:4] == ["enter speed", "enter bot", "enter cancel", "start speed"]
        assert lifecycle.count("stop speed") == 1
        assert lifecycle[-3:] == ["exit cancel", "exit bot", "exit speed"]
        assert lifecycle.count("confirm speed") == int(stop_fault)
        assert worker.engine.speed["current_rate"] == 1.0
    else:
        assert lifecycle == ["enter bot", "enter cancel", "cancel", "exit cancel", "exit bot"]


def test_calibration_for_another_instance_cannot_start_worker():
    session = SimpleNamespace(creation_time=888, process=SimpleNamespace(pid=100))
    with pytest.raises(DiagnosticError, match="Calibra"):
        HuntWorker(session, ClientWindow(100, 0x1234, "Atlantica"), DETECTOR)
