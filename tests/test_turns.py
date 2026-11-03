from dataclasses import replace

import pytest

from atlantica_bot.profiles import BotProfile
from atlantica_bot.turns import TurnEngine, roster_rows


def profile(*, order=range(1, 10), magic=None, fallback=True, target="enemy", first_only=True):
    plans = {m.slot: m for m in BotProfile.default(1).mercenaries}
    for slot, action in (magic or {}).items():
        plans[slot] = replace(plans[slot], action=action, fallback_basic=fallback, target=target)
    return BotProfile(1, tuple(plans[s] for s in order), first_only)


def engine(plan=None, *, fresh=True, ledger=None):
    bot = TurnEngine(100, 777, plan or profile(), ledger)
    bot.enter(fresh=fresh)
    return bot


def reply(bot, trial, status=None, *, error=0, now=0):
    if status is None:
        status = {6: 26, 7: 31, 8: 32}[trial.operation]
    bot.record(
        trial,
        {
            "pid": 100,
            "operation": trial.operation,
            "status": status,
            "battle": {"native_error": [error, 0, 0, 0]},
        },
        now,
    )


def changed(frame, index=2, **values):
    units = list(frame.units)
    units[index] = replace(units[index], **values)
    return replace(frame, units=tuple(units))


def test_two_deployed_members_act_in_profile_order_without_waiting_for_other_seven(turn_frame):
    bot = engine(profile(order=(9, 2, 1, 3, 4, 5, 6, 7, 8)))
    trial = bot.next(turn_frame, 0)
    assert trial.source.member_slot == 2 and trial.action == "basic"
    reply(bot, trial)
    assert bot.next(turn_frame, 0.5) is None  # A queue acknowledgement is not progress.
    fresh = changed(turn_frame, life=900)
    assert bot.next(fresh, 1) is None
    second = bot.next(fresh, 1.5)
    assert second.source.member_slot == 1
    reply(bot, second, now=1.5)
    fresh = changed(fresh, life=800)
    assert bot.next(fresh, 2) is None
    assert bot.next(fresh, 2.5) is None
    assert bot.queued == 2


def test_roster_has_nine_slots_and_distinguishes_disabled_dead_absent_and_unknown(turn_frame):
    plan = profile(order=reversed(range(1, 10)))
    plans = tuple(replace(m, enabled=False) if m.slot == 1 else m for m in plan.mercenaries)
    plan = replace(plan, mercenaries=plans)
    frame = changed(turn_frame, 1, life=0)
    rows = roster_rows(plan, frame)
    assert [r["slot"] for r in rows] == list(range(1, 10))
    assert rows[0]["label"] == "Main (1)" and rows[0]["priority"] == 9
    assert rows[1]["label"] == "Mercenario 2"
    assert rows[0]["present"] and rows[0]["alive"] and not rows[0]["enabled"]
    assert rows[0]["life"] == 1000
    assert rows[0]["opening_action"] == rows[0]["later_action"] == "Sin orden"
    assert rows[1]["present"] and rows[1]["alive"] is False
    assert rows[1]["life"] == 0
    assert all(r["present"] is False for r in rows[2:])
    assert all(r["life"] is None for r in rows[2:])
    assert rows[1]["priority"] == 8
    assert all(r["present"] is None for r in roster_rows(plan, None))
    assert all(r["life"] is None for r in roster_rows(plan, None))
    assert engine(plan).next(frame, 0) is None


def test_no_remaining_orders_after_last_enemy_dies_even_for_buff_mercenary(turn_frame):
    bot = engine(profile(magic={2: "Q"}, target="self"))
    first = bot.next(turn_frame, 0)
    reply(bot, first)
    frame = changed(changed(turn_frame, 2, life=0), 3, life=0)
    for now in (0.5, 1, 10, 30):
        assert bot.next(frame, now) is None
    assert bot.pending is None and bot.queued == 1 and bot.running
    assert "Sin enemigos vivos" in bot.message


def test_magic_first_own_turn_then_basic_and_magic_again_in_next_battle(turn_frame):
    bot = engine(profile(magic={1: "Q"}))
    first = bot.next(turn_frame, 0)
    assert first.action == "Q"
    reply(bot, first)
    enemy_turn = replace(turn_frame, turn_group=1, turn_number=1, turn_tick=123480)
    assert bot.next(enemy_turn, 1) is None
    later = replace(turn_frame, turn_number=2, turn_tick=123500)
    basic = bot.next(later, 2)
    assert basic.action == "basic" and basic.source.member_slot == 1
    reply(bot, basic, now=2)
    bot.leave()
    bot.enter(fresh=True)
    assert bot.next(replace(turn_frame, turn_tick=200000), 10).action == "Q"


def test_enemy_initiative_waits_for_first_own_turn_to_use_opening_magic(turn_frame):
    bot = engine(profile(magic={1: "W"}))
    assert bot.next(replace(turn_frame, turn_group=1), 0) is None
    own = replace(turn_frame, turn_number=1, turn_tick=123480)
    assert bot.next(own, 1).action == "W"


def test_uninitialized_turn_does_not_consume_opening_or_send_an_order(turn_frame):
    bot = engine(profile(magic={1: "Q"}))
    assert bot.next(replace(turn_frame, turn_number=0xFFFFFFFF), 0) is None
    assert bot.opening_turn is None and not bot.finished_opening
    assert bot.next(turn_frame, 0.5).action == "Q"


def test_starting_midbattle_avoids_late_opener_unless_repeat_mode_is_configured(turn_frame):
    frame = replace(turn_frame, turn_number=4)
    assert engine(profile(magic={1: "Q"}), fresh=False).next(frame, 0).action == "basic"
    repeating = engine(profile(magic={1: "Q"}, first_only=False), fresh=False)
    assert repeating.next(frame, 0).action == "Q"


def test_select_then_read_new_bar_before_cast_and_do_not_select_for_basic(turn_frame):
    bot = engine(profile(magic={2: "Q"}, order=(2, 1, *range(3, 10))))
    trial = bot.next(turn_frame, 0)
    assert trial.operation == 7 and trial.target is None
    reply(bot, trial)
    selected = replace(
        turn_frame, selected_unit=turn_frame.sources[1].address, magic_actions=(440,)
    )
    magic = bot.next(selected, 0.5)
    assert magic.operation == 8 and magic.arguments()["magic-action"] == 440
    assert engine().next(turn_frame, 0).operation == 6


@pytest.mark.parametrize("target,member", [("self", 1), ("slot_2", 2), ("enemy", 1)])
def test_magic_target_uses_configured_own_or_enemy_member(turn_frame, target, member):
    trial = engine(profile(magic={1: "Q"}, target=target)).next(turn_frame, 0)
    assert trial.target.member_slot == member
    assert trial.target.world_slot == (6 if target == "enemy" else 1)


def test_absent_magic_target_falls_back_before_lower_priority_member(turn_frame):
    bot = engine(profile(magic={1: "Q"}, target="slot_9"))
    assert bot.next(turn_frame, 0) is None
    trial = bot.next(turn_frame, 0.5)
    assert trial.source.member_slot == 1 and trial.action == "basic"


@pytest.mark.parametrize("fallback", [True, False])
@pytest.mark.parametrize("code", [34, 35])
def test_explicit_magic_rejection_falls_back_only_if_configured(turn_frame, fallback, code):
    bot = engine(profile(magic={1: "Q"}, fallback=fallback))
    trial = bot.next(turn_frame, 0)
    reply(bot, trial, code)
    next_order = bot.next(turn_frame, 0.5)
    assert next_order.action == "basic"
    assert next_order.source.member_slot == (1 if fallback else 2)
    assert bot.queued == 0


def test_missing_magic_key_uses_configured_fallback_without_native_magic_call(turn_frame):
    bot = engine(profile(magic={1: "T"}))
    trial = bot.next(turn_frame, 0)
    assert trial.operation == 6 and trial.source.member_slot == 1


@pytest.mark.parametrize("code", [10, 11, 33, 13])
def test_uncertain_or_cancelled_orders_never_retry_or_fall_back(turn_frame, code):
    bot = engine(profile(magic={1: "Q"}))
    trial = bot.next(turn_frame, 0)
    reply(bot, trial, code)
    assert bot.next(turn_frame, 1) is None
    assert not bot.running and bot.queued == 0
    assert bot.needs_reconnect is (code in (10, 11))


def test_queued_but_unobserved_order_stops_after_timeout_without_retry(turn_frame):
    bot = engine()
    trial = bot.next(turn_frame, 0)
    reply(bot, trial)
    assert bot.next(turn_frame, 1) is None
    assert bot.next(turn_frame, 12) is None
    assert not bot.running and bot.needs_reconnect and bot.queued == 1


def test_busy_priority_member_is_not_overtaken_and_animation_completion_allows_next(turn_frame):
    bot = engine()
    assert bot.next(changed(turn_frame, 0, action_state=2), 0) is None
    trial = bot.next(turn_frame, 1)
    reply(bot, trial, now=1)
    assert bot.next(changed(turn_frame, 0, action_state=2), 1.5) is None
    assert bot.next(turn_frame, 2) is None
    assert bot.next(turn_frame, 2.5).source.member_slot == 2


def test_resource_change_is_progress_without_claiming_damage_confirmation(turn_frame):
    bot = engine(profile(magic={1: "Q"}, target="self"))
    trial = bot.next(turn_frame, 0)
    reply(bot, trial)
    members = (replace(turn_frame.context.members[0], value_50=50), turn_frame.context.members[1])
    frame = replace(turn_frame, context=replace(turn_frame.context, members=members))
    assert bot.next(frame, 1) is None
    assert bot.next(frame, 1.5).source.member_slot == 2
    assert bot.summary()["observed_changes"] == 1
    assert "attack_confirmed" not in bot.summary()


def test_ineligible_basic_skips_rejected_target_but_insufficient_ap_skips_member(turn_frame):
    bot = engine()
    first = bot.next(turn_frame, 0)
    reply(bot, first, 30, error=0x1C2)
    second = bot.next(turn_frame, 0.5)
    assert second.source == first.source and second.target != first.target
    reply(bot, second, 30, error=0x1C1)
    assert bot.next(turn_frame, 1).source.member_slot == 2


def test_shared_ledger_avoids_duplicate_manual_and_restarted_bot_orders(turn_frame):
    ledger = set()
    first_bot = engine(ledger=ledger)
    first = first_bot.next(turn_frame, 0)
    reply(first_bot, first)
    restarted = engine(ledger=ledger)
    assert restarted.next(turn_frame, 1).source.member_slot == 2


@pytest.mark.parametrize("pid,created", [(999, 777), (100, 888)])
def test_foreign_instance_stops_before_any_order(turn_frame, pid, created):
    bot = engine()
    frame = replace(turn_frame, context=replace(turn_frame.context, pid=pid, creation_time=created))
    assert bot.next(frame, 0) is None
    assert not bot.running and bot.needs_reconnect and bot.queued == 0


def test_wrong_response_operation_stops_without_consuming_member(turn_frame):
    bot = engine()
    trial = bot.next(turn_frame, 0)
    bot.record(trial, {"pid": 100, "operation": 8, "status": 32}, 0)
    assert not bot.running and not bot.ledger and bot.queued == 0
