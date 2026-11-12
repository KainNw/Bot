from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError, SceneChanged
from atlantica_bot.hunt_loop import HuntWorker
from atlantica_bot.profiles import BotProfile
from atlantica_bot.world import GridPosition, LocalState, Observation


@pytest.fixture
def combat_worker(turn_frame, monkeypatch):
    state = SimpleNamespace(
        frame=replace(turn_frame, selected_unit=0),
        calls=[],
        reads=0,
        now=10.0,
        after_select=None,
        unstable=False,
        left_battle=False,
    )
    plan = BotProfile.default(1)
    plan = replace(
        plan,
        mercenaries=(
            replace(plan.mercenaries[0], action="Q", fallback_basic=False),
            *plan.mercenaries[1:],
        ),
    )
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    worker = HuntWorker(
        session,
        ClientWindow(100, 0x1234, "Atlantica", 1234),
        CombatDetector(100, 777, "local_context"),
        plan,
        execute_turns=True,
    )

    def observe(*args, **kwargs):
        return Observation(
            100,
            777,
            2,
            GridPosition(127, 33, 75),
            False,
            LocalState(33 if not state.left_battle else 1, -1 if state.left_battle else 0, -1, 0),
        )

    worker.engine.observe(observe(), 0)
    worker.engine.observe(observe(), 1)
    worker.seen_map = True

    def read_frame(selected_session):
        assert selected_session is session
        state.reads += 1
        state.now += 0.01
        if state.reads > 1:
            if state.unstable:
                raise SceneChanged("The bar changed during the refresh")
            if state.left_battle:
                raise DiagnosticError("The battle has ended")
        return state.frame

    def send(selected_session, selected_window, trial, *, cancellation):
        assert selected_session is session and selected_window is worker.window
        state.calls.append(trial)
        state.now += 0.1
        status = {6: 26, 7: 31, 8: 32}[trial.operation]
        if trial.operation == 7:
            # Native selection has rebuilt this mercenary's bar with a different Q.
            state.frame = replace(
                state.frame, selected_unit=trial.source.address, magic_actions=(440, 222)
            )
            if state.after_select is not None:
                state.after_select()
        return {"pid": 100, "operation": trial.operation, "status": status}

    monkeypatch.setattr("atlantica_bot.hunt_loop.observe_scene", observe)
    monkeypatch.setattr("atlantica_bot.hunt_loop.read_battle_frame", read_frame)
    monkeypatch.setattr("atlantica_bot.hunt_loop.try_battle_action", send)
    monkeypatch.setattr("atlantica_bot.hunt_loop.time.monotonic", lambda: state.now)
    return worker, state


def test_selection_and_fresh_magic_execute_in_one_iteration_without_polling_pause(combat_worker):
    worker, state = combat_worker
    worker._iteration()
    assert [t.operation for t in state.calls] == [7, 8]
    assert state.reads == 2
    assert state.calls[1].arguments()["magic-action"] == 440  # Not the previous bar's 207.
    events = list(worker.turns.events)
    assert events[2]["time"] - events[1]["time"] == pytest.approx(0.01)
    assert worker.turns.queued == 1 and worker.turns.pending is not None
    worker._iteration()
    assert len(state.calls) == 2  # No duplicate magic after the queue acknowledgement.


@pytest.mark.parametrize("change", ["stop", "enemy_turn", "all_enemies_dead", "other_instance"])
def test_fresh_changes_after_selection_prevent_immediate_magic(combat_worker, change):
    worker, state = combat_worker

    def change_frame():
        if change == "stop":
            worker.stop_event.set()
        elif change == "enemy_turn":
            state.frame = replace(state.frame, turn_group=1, turn_number=1, turn_tick=123500)
        elif change == "all_enemies_dead":
            state.frame = replace(
                state.frame,
                units=tuple(
                    replace(u, life=0) if u.world_slot != 1 else u for u in state.frame.units
                ),
            )
        else:
            state.frame = replace(
                state.frame, context=replace(state.frame.context, creation_time=888)
            )

    state.after_select = change_frame
    worker._iteration()
    assert [t.operation for t in state.calls] == [7]
    assert worker.turns.queued == 0 and worker.turns.inflight is None
    if change == "stop":
        assert state.reads == 1
    if change == "other_instance":
        assert not worker.engine.running and worker.engine.needs_reconnect


def test_changing_bar_defers_cast_until_a_fresh_coherent_read(combat_worker):
    worker, state = combat_worker
    state.after_select = lambda: setattr(state, "unstable", True)
    with pytest.raises(SceneChanged):
        worker._iteration()
    assert [t.operation for t in state.calls] == [7]
    assert worker.turns.inflight is None and worker.turns.queued == 0
    assert worker._poll_delay() == 0.1
    state.unstable = False
    worker._iteration()
    assert [t.operation for t in state.calls] == [7, 8]
    assert state.calls[-1].arguments()["magic-action"] == 440


def test_battle_ending_between_selection_and_refresh_returns_to_map_without_cast(combat_worker):
    worker, state = combat_worker
    state.after_select = lambda: setattr(state, "left_battle", True)
    worker._iteration()
    assert [t.operation for t in state.calls] == [7]
    assert worker.engine.phase == "resuming"
    assert worker.engine.running and not worker.engine.needs_reconnect


def test_unavailable_refreshed_magic_does_not_reuse_old_action(combat_worker):
    worker, state = combat_worker
    state.after_select = lambda: setattr(state, "frame", replace(state.frame, magic_actions=()))
    worker._iteration()
    assert [t.operation for t in state.calls] == [7, 6]
    assert state.calls[1].source.member_slot == 2  # Slot 1 has no fallback configured.


def test_immediate_refresh_is_bounded_even_if_two_members_need_selection(combat_worker):
    worker, state = combat_worker
    plan = worker.turns.profile
    worker.turns.profile = replace(
        plan,
        mercenaries=(
            replace(plan.mercenaries[0], action="T"),
            replace(plan.mercenaries[1], action="Q"),
            *plan.mercenaries[2:],
        ),
    )
    worker._iteration()
    assert [t.operation for t in state.calls] == [7, 7]
    assert state.reads == 2 and worker.turns.queued == 0
    worker._iteration()
    assert [t.operation for t in state.calls] == [7, 7, 8]
    assert state.calls[-1].source.member_slot == 2


def test_fast_polling_covers_pending_animations_and_preserves_idle_intervals(combat_worker):
    worker, state = combat_worker
    assert worker._poll_delay() == 0.1
    worker.turns.last_frame = replace(state.frame, phase=2)
    assert worker._poll_delay() == 0.1
    worker.turns.last_frame = replace(state.frame, turn_number=0xFFFFFFFF)
    assert worker._poll_delay() == 0.1
    worker.turns.last_frame = replace(state.frame, units=state.frame.sources)
    assert worker._poll_delay() == 0.1  # Initial enemy publication is still loading.
    worker._iteration()
    assert worker._poll_delay() == 0.1  # Observe short animations without resending the action.
    worker.turns.pending = None
    worker.turns.last_frame = replace(state.frame, units=state.frame.sources)
    assert worker._poll_delay() == 0.5
    worker.turns.last_frame = replace(worker.turns.last_frame, phase=4)
    assert worker._poll_delay() == 0.5
    worker.turns.last_frame = replace(state.frame, turn_group=1)
    assert worker._poll_delay() == 0.5


@pytest.mark.parametrize(
    "phase,deadline,delay",
    [
        ("waiting_map", None, 0.5),
        ("searching", None, 0.1),
        ("native_pursuit", None, 0.5),
        ("waiting_battle", 20, 0.25),
    ],
)
def test_world_polling_intervals_are_preserved(combat_worker, phase, deadline, delay):
    worker, _ = combat_worker
    worker.engine.phase, worker.engine.deadline = phase, deadline
    assert worker._poll_delay() == delay


def test_manual_turn_mode_preserves_previous_intervals(combat_worker):
    worker, _ = combat_worker
    assert worker._poll_delay() == 0.1
    worker.turns = None
    assert worker._poll_delay() == 0.5
    worker.engine.deadline = 20
    assert worker._poll_delay() == 0.25
