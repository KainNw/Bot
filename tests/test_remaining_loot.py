from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.battle import BattleTrial
from atlantica_bot.clients import ClientWindow
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunt_loop import HuntWorker
from atlantica_bot.profiles import BotProfile
from atlantica_bot.turns import TurnEngine, loot_key


def defeated(frame):
    return replace(
        frame, units=tuple(replace(u, life=0) if u.world_slot != 1 else u for u in frame.units)
    )


def collector(frame, *, ledger=None, execute=False):
    profile = replace(BotProfile.default(1), collect_remaining_loot=True)
    bot = TurnEngine(
        frame.context.pid, frame.context.creation_time, profile, ledger, execute_orders=execute
    )
    bot.enter(fresh=True)
    return bot


def record(bot, trial, code, now):
    bot.record(trial, {"pid": bot.pid, "operation": trial.operation, "status": code}, now)


def test_collection_waits_for_all_enemies_and_neo_grace_without_attacking_manual_turns(turn_frame):
    bot = collector(turn_frame)
    assert bot.next(turn_frame, 0) is None
    assert bot.queued == 0 and bot.inflight is None
    dead = defeated(turn_frame)
    assert bot.next(dead, 1) is None
    assert bot.next(dead, 1.9) is None
    trial = bot.next(dead, 2)
    assert trial.action == "loot" and trial.target.life == 0
    record(bot, trial, 36, 2)
    summary = bot.summary()
    assert summary["loot"]["queued"] == 1 and summary["queued"] == 0
    assert summary["loot"]["collection_confirmed"] is False
    assert summary["loot"]["bonus_detection_verified"] is False


def test_collection_is_optional_and_never_delays_the_opening_magic(turn_frame):
    original = BotProfile.default(1)
    profile = replace(
        original,
        mercenaries=(replace(original.mercenaries[0], action="Q"), *original.mercenaries[1:]),
        collect_remaining_loot=True,
        attack_delay_seconds=60,
    )
    bot = TurnEngine(100, 777, profile)
    bot.enter(fresh=True)
    trial = bot.next(turn_frame, 0)
    assert trial.action == "Q"
    record(bot, trial, 32, 0.1)
    dead = defeated(turn_frame)
    assert bot.next(dead, 0.2) is None
    loot = bot.next(dead, 1.2)
    assert loot.action == "loot" and loot.source == trial.source
    assert 1 in bot.consumed  # An offensive order does not block a separate search action.
    disabled = TurnEngine(100, 777, original)
    disabled.enter(fresh=True)
    assert disabled.next(dead, 0) is None
    assert disabled.next(dead, 30) is None and disabled.inflight is None


def test_loot_selects_an_enabled_present_member_and_reads_again_before_search(turn_frame):
    frame = defeated(turn_frame)
    bot = collector(frame)
    mercs = tuple(replace(m, enabled=m.slot == 2) for m in bot.profile.mercenaries)
    bot.profile = replace(bot.profile, mercenaries=mercs)
    assert bot.next(frame, 0) is None
    select = bot.next(frame, 1)
    assert select.action == "select" and select.source.member_slot == 2
    record(bot, select, 31, 1)
    selected = replace(frame, selected_unit=select.source.address)
    loot = bot.next(selected, 1.01)
    assert loot.operation == 9 and loot.source.member_slot == 2
    assert bot.selections == 1


@pytest.mark.parametrize(
    "change", ["enemy_turn", "live_enemy", "own_target", "not_selected", "loading"]
)
def test_loot_trial_refuses_invalid_or_live_targets(turn_frame, change):
    frame = defeated(turn_frame)
    source, target = frame.sources[0], frame.corpses[0]
    if change == "enemy_turn":
        frame = replace(frame, turn_group=1)
    elif change == "live_enemy":
        frame = turn_frame
    elif change == "own_target":
        target = source
    elif change == "not_selected":
        frame = replace(frame, selected_unit=frame.sources[1].address)
    else:
        frame = replace(frame, phase=1)
    with pytest.raises(DiagnosticError):
        BattleTrial(frame, source, target, "loot").validate()


def test_queued_search_is_never_repeated_for_another_source_turn_or_worker(turn_frame):
    frame = defeated(turn_frame)
    shared = set()
    bot = collector(frame, ledger=shared)
    bot.next(frame, 0)
    trial = bot.next(frame, 1)
    record(bot, trial, 36, 1)
    assert loot_key(frame, trial.target) in shared
    # No progress: do not send a second request while the first is unresolved.
    assert bot.next(frame, 3) is None
    assert bot.next(frame, 13) is None
    assert not bot.running and bot.needs_reconnect and bot.loot_queued == 1
    restarted = collector(frame, ledger=shared)
    restarted.next(frame, 20)
    later = replace(frame, turn_number=2, turn_tick=124000)
    second = restarted.next(later, 21)
    assert second.target != trial.target and second.action == "loot"


def test_progress_after_search_allows_next_corpse_without_claiming_received_loot(turn_frame):
    frame = defeated(turn_frame)
    bot = collector(frame)
    bot.next(frame, 0)
    trial = bot.next(frame, 1)
    record(bot, trial, 36, 1)
    changed = replace(frame, units=tuple(u for u in frame.units if u != trial.target))
    assert bot.next(changed, 1.5) is None
    next_trial = bot.next(changed, 2)
    assert next_trial.action == "loot" and next_trial.target != trial.target
    assert bot.observed == 1 and not bot.summary()["loot"]["collection_confirmed"]


def test_native_loot_rejection_can_try_another_corpse_but_does_not_retry_rejected_pair(turn_frame):
    frame = defeated(turn_frame)
    bot = collector(frame)
    bot.next(frame, 0)
    first = bot.next(frame, 1)
    record(bot, first, 37, 1)
    second = bot.next(frame, 1.5)
    assert second.target != first.target and second.source == first.source
    assert bot.loot_queued == 0 and bot.pending is None


def test_no_collection_after_map_return_or_from_foreign_instance(turn_frame):
    frame = defeated(turn_frame)
    bot = collector(frame)
    assert bot.next(frame, 0) is None
    bot.leave()
    assert bot.next(frame, 3) is None
    foreign = collector(frame)
    foreign.next(frame, 0)
    changed = replace(frame, context=replace(frame.context, pid=999))
    assert foreign.next(changed, 1) is None
    assert foreign.needs_reconnect and not foreign.running


def test_worker_can_collect_with_manual_turns_and_uses_saved_search_radius():
    session = SimpleNamespace(process=SimpleNamespace(pid=100), creation_time=777)
    profile = replace(BotProfile.default(1), collect_remaining_loot=True, search_radius=350)
    worker = HuntWorker(
        session,
        ClientWindow(100, 12345, "Atlantica", 1234),
        CombatDetector(100, 777, "local_context"),
        profile,
        native_attack=True,
        execute_turns=False,
    )
    assert worker.engine.approach.radius == 350 and not worker.engine.execute_turns
    assert worker.turns is not None and not worker.turns.execute_orders


@pytest.mark.parametrize("stage", ["select", "loot"])
def test_selection_change_pauses_only_collection_until_the_next_battle(turn_frame, stage):
    frame = defeated(turn_frame)
    if stage == "select":
        frame = replace(frame, selected_unit=0)
    bot = collector(frame, execute=True)
    assert bot.next(frame, 0) is None
    trial = bot.next(frame, 1)
    assert trial.action == stage
    record(bot, trial, 33, 1)
    assert bot.running and not bot.needs_reconnect and bot.inflight is None
    assert bot.pending is None and not bot.ledger and bot.loot_queued == 0
    assert bot.summary()["loot"]["paused"]
    for later in (frame, replace(frame, turn_number=2, turn_tick=123500)):
        assert bot.next(later, 10) is None
        assert bot.running
    # A paused optional collector cannot suppress attacks if a live enemy appears.
    assert bot.next(turn_frame, 11).action == "basic"
    bot.leave()
    bot.enter(fresh=True)
    assert not bot.loot_suspended and bot.loot_pause_reason is None


@pytest.mark.parametrize("status", [10, 11])
def test_uncertain_collection_still_stops_without_retry(turn_frame, status):
    frame = defeated(turn_frame)
    bot = collector(frame)
    bot.next(frame, 0)
    trial = bot.next(frame, 1)
    record(bot, trial, status, 1)
    assert not bot.running and bot.needs_reconnect
    assert bot.next(frame, 2) is None and bot.loot_queued == 0


@pytest.mark.parametrize("stage", ["select", "Q"])
def test_selection_change_during_offensive_orders_keeps_existing_stop_policy(turn_frame, stage):
    frame = replace(turn_frame, selected_unit=0) if stage == "select" else turn_frame
    bot = collector(frame, execute=True)
    bot.profile = replace(
        bot.profile,
        mercenaries=(replace(bot.profile.mercenaries[0], action="Q"), *bot.profile.mercenaries[1:]),
    )
    trial = bot.next(frame, 0)
    assert trial.action == stage
    record(bot, trial, 33, 0)
    assert not bot.running and not bot.loot_suspended
    assert not bot.ledger and bot.queued == bot.loot_queued == 0
