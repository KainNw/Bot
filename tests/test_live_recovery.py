from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import SceneChanged
from atlantica_bot.hunt_loop import HuntEngine, HuntWorker
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


def observation(position=ORIGIN, *, walking=False, battle=False, pid=100, created=777):
    return Observation(
        pid,
        created,
        2,
        position,
        False,
        LocalState(33 if battle else 1, 0 if battle else -1, -1, 0),
        replace(IDLE, active=walking, moving=walking),
        (float(position.x), 0.0, float(position.y)),
    )


def plan():
    result = BotProfile.default(1)
    return replace(
        result,
        mercenaries=(
            replace(result.mercenaries[0], action="Q", fallback_basic=False),
            *result.mercenaries[1:],
        ),
    )


@pytest.mark.parametrize("mode", ["native", "stationary"])
def test_manual_walk_waits_without_attacking_and_recenters_after_two_seconds_still(mode):
    engine = HuntEngine(
        100,
        777,
        CombatDetector(100, 777, "local_context"),
        replace(BotProfile.default(1), world_attack_mode=mode),
        native_attack=mode == "native",
    )
    assert not engine.observe(observation(), 0)
    assert engine.observe(observation(), 2)
    moved = GridPosition(52, 300, 340)  # Explicit manual movement outside the old area.
    assert not engine.observe(observation(moved, walking=True), 3)
    assert not engine.observe(observation(moved, walking=True), 4)
    assert not engine.observe(observation(moved), 5)
    assert engine.running and engine.scans == 0 and engine.attempts == 0
    assert engine.observe(observation(moved), 6)
    assert engine.origin == moved and engine.manual_pauses == 1 and not engine.manual_active
    candidate = Candidate(8, 12053, 52, 306, 340, 6, (12053, 77, 0), 36)
    view = WorldView(
        moved,
        (candidate,),
        2,
        range_limit_squared=20,
        player_world_position=(300.0, 0.0, 340.0),
        active_identities=(candidate.identity,),
    )
    assert engine.select(view, 6) == candidate


def test_manual_pause_keeps_instance_and_map_checks():
    engine = HuntEngine(100, 777, CombatDetector(100, 777, "local_context"), native_attack=True)
    engine.observe(observation(walking=True), 0)
    assert engine.manual_active
    engine.observe(observation(GridPosition(53, 193, 340)), 1)
    assert not engine.running
    other = HuntEngine(100, 777, CombatDetector(100, 777, "local_context"))
    other.observe(observation(walking=True), 0)
    other.observe(observation(pid=101), 1)
    assert not other.running and other.needs_reconnect


def test_one_window_can_walk_while_an_ambushed_window_waits_enemy_turn_then_casts_q(
    turn_frame, monkeypatch
):
    workers, observations, frames, calls = {}, {}, {}, []
    for pid, created in ((100, 777), (101, 888)):
        session = SimpleNamespace(process=SimpleNamespace(pid=pid), creation_time=created)
        workers[pid] = HuntWorker(
            session,
            ClientWindow(pid, 0x1000 + pid, "Atlantica", pid + 1000),
            CombatDetector(pid, created, "local_context"),
            plan(),
            native_attack=True,
            execute_turns=True,
        )
        workers[pid].cancellation = object()
        observations[pid] = observation(pid=pid, created=created)
        context = replace(turn_frame.context, pid=pid, creation_time=created)
        units = tuple(replace(u, group=1 if u.world_slot == 1 else 0) for u in turn_frame.units)
        frames[pid] = replace(turn_frame, context=context, local_group=1, turn_group=0, units=units)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene",
        lambda session, **kw: observations[session.process.pid],
    )
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.read_battle_frame", lambda session: frames[session.process.pid]
    )
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.scan_world",
        lambda *a, **kw: pytest.fail("No hunting scan during walking or battle"),
    )

    def send(session, window, trial, *, cancellation):
        assert session.process.pid == window.pid == trial.frame.context.pid
        assert cancellation is workers[window.pid].cancellation
        calls.append((window.pid, trial.action))
        return {"pid": window.pid, "operation": trial.operation, "status": 32}

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    for worker in workers.values():
        worker._iteration()  # Both first observed the map; no bot attack was sent.
    observations[100] = observation(GridPosition(52, 194, 340), walking=True)
    observations[101] = observation(pid=101, created=888, battle=True)
    workers[100]._iteration()
    workers[101]._iteration()
    workers[101]._iteration()
    assert not calls and workers[101].engine.battle_entry["source"] == "external"
    frames[101] = replace(frames[101], turn_group=1, turn_number=1, turn_tick=123500)
    workers[101]._iteration()
    assert calls == [(101, "Q")]
    assert workers[100].engine.manual_active and workers[100].engine.running
    assert workers[101].engine.running and workers[101].turns.queued == 1
    assert workers[100].turns.queued == 0


@pytest.mark.parametrize("execute_turns", [False, True])
def test_ambush_with_loot_enabled_obeys_the_separate_automatic_turn_switch(
    turn_frame, monkeypatch, execute_turns
):
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    profile = replace(plan(), collect_remaining_loot=True)
    worker = HuntWorker(
        session,
        ClientWindow(100, 0x1234, "Atlantica", 1234),
        CombatDetector(100, 777, "local_context"),
        profile,
        native_attack=True,
        execute_turns=execute_turns,
    )
    worker.cancellation = object()
    # Match the reported ambush: own group is 1, enemy group is 0, then turn 1 is ours.
    frame = replace(
        turn_frame,
        local_group=1,
        turn_group=0,
        units=tuple(replace(u, group=1 if u.world_slot == 1 else 0) for u in turn_frame.units),
    )
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.observe_scene", lambda *a, **kw: observation(battle=True)
    )
    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", lambda *a: frame)
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.scan_world", lambda *a, **kw: pytest.fail("Battle only")
    )
    calls = []

    def send(session, window, trial, **kwargs):
        calls.append(trial)
        return {"pid": 100, "operation": trial.operation, "status": 32}

    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    worker._iteration()
    worker._iteration()
    assert not calls
    frame = replace(frame, turn_group=1, turn_number=1, turn_tick=123500)
    worker._iteration()
    summary = worker.engine.summary()
    assert summary["execute_turns"] == execute_turns
    assert summary["battle_entry"]["source"] == "external"
    assert summary["combat"]["enabled"] and summary["combat"]["loot"]["enabled"]
    assert summary["combat"]["execute_orders"] == execute_turns
    assert summary["combat"]["frame"]["own_turn"]
    assert summary["running"] and not summary["needs_reconnect"]
    assert len(calls) == int(execute_turns)
    if execute_turns:
        assert calls[0].source.member_slot == 1 and calls[0].action == "Q"


@pytest.mark.parametrize("queued", [False, True])
def test_combat_read_recovery_has_time_grace_and_does_not_repeat_a_queued_order(
    turn_frame, monkeypatch, queued
):
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    worker = HuntWorker(
        session,
        ClientWindow(100, 0x1234, "Atlantica"),
        CombatDetector(100, 777, "local_context"),
        execute_turns=True,
    )
    worker.engine.phase = "battle"
    if queued:
        worker.turns.enter(fresh=True)
        trial = worker.turns.next(turn_frame, 0)
        worker.turns.record(trial, {"pid": 100, "operation": 6, "status": 26}, 0)
    clock, waits = [0.0], []

    class Event:
        def is_set(self):
            return False

        def wait(self, delay):
            waits.append(delay)
            clock[0] += delay

    def unstable():
        raise SceneChanged("Battle data still loading")

    worker.stop_event = Event()
    worker._iteration = unstable
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda pid: nullcontext())
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.Cancellation",
        lambda pid: nullcontext(SimpleNamespace(cancel=lambda: None)),
    )
    worker._run()
    assert 3 <= worker.engine.last_read_error["recovery_seconds"] < 3.6
    assert worker.engine.transient_reads > 3 and not worker.engine.running
    assert worker.engine.needs_reconnect is queued
    assert worker.turns.queued == int(queued)  # Read recovery never invokes an action.


def test_several_transient_combat_reads_recover_before_time_grace(monkeypatch):
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    worker = HuntWorker(
        session,
        ClientWindow(100, 0x1234, "Atlantica"),
        CombatDetector(100, 777, "local_context"),
        execute_turns=True,
    )
    worker.engine.phase = "battle"
    clock, calls = [0.0], []

    class Event:
        def is_set(self):
            return False

        def wait(self, delay):
            clock[0] += delay

    def step():
        calls.append(1)
        if len(calls) <= 5:
            raise SceneChanged("Not ready yet")
        worker.engine.stop("End of recovery test")

    worker.stop_event = Event()
    worker._iteration = step
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("atlantica_bot.hunt_loop.BotLease", lambda pid: nullcontext())
    monkeypatch.setattr(
        "atlantica_bot.hunt_loop.Cancellation",
        lambda pid: nullcontext(SimpleNamespace(cancel=lambda: None)),
    )
    worker._run()
    assert len(calls) == 6 and worker.engine.transient_reads == 5
    assert worker.engine.last_read_error["recovered"] is True
    assert worker.engine.last_read_error["recovered_after_seconds"] == 0.5
    assert not worker.engine.needs_reconnect
