from dataclasses import replace

import pytest

from atlantica_bot.battle import BattleTrial
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, ProfileStore
from atlantica_bot.turns import TurnEngine, roster_rows


def plan(*, action="Q", pass_remaining=False, later="basic"):
    base = BotProfile.default(1)
    return replace(
        base,
        pass_remaining=pass_remaining,
        mercenaries=tuple(
            replace(
                m,
                enabled=m.slot == 1,
                action=action if m.slot == 1 else "basic",
                later_action=later if m.slot == 1 else "basic",
            )
            for m in base.mercenaries
        ),
    )


def engine(profile):
    bot = TurnEngine(100, 777, profile)
    bot.enter(fresh=True)
    return bot


def record(bot, trial, code, now):
    bot.record(trial, {"pid": 100, "operation": trial.operation, "status": code}, now)


def edit(frame, index, **values):
    units = list(frame.units)
    units[index] = replace(units[index], **values)
    return replace(frame, units=tuple(units))


@pytest.mark.parametrize("action,operation", [("defend", 16), ("pass", 17)])
def test_stance_targets_only_the_selected_source_and_requires_normal_own_turn(
    turn_frame, action, operation
):
    source = turn_frame.sources[0]
    trial = BattleTrial(turn_frame, source, source, action)
    trial.validate()
    assert trial.operation == operation
    assert trial.arguments()["target-unit"] == source.address
    for invalid in (
        replace(trial, target=turn_frame.enemies[0]),
        replace(trial, frame=replace(turn_frame, turn_group=1)),
        replace(trial, frame=replace(turn_frame, phase=2)),
        replace(trial, frame=replace(turn_frame, selected_unit=0)),
        replace(trial, frame=replace(turn_frame, units=turn_frame.sources)),
    ):
        with pytest.raises(DiagnosticError):
            invalid.validate()


def test_main_magic_then_pass_all_available_members_including_members_without_offensive_order(
    turn_frame,
):
    bot = engine(plan(pass_remaining=True))
    attack = bot.next(turn_frame, 0)
    assert attack.action == "Q"
    record(bot, attack, 32, 0)
    assert bot.next(turn_frame, 0.3) is None
    hurt = edit(turn_frame, 2, life=900)
    assert bot.next(hurt, 0.5) is None
    first_pass = bot.next(hurt, 1.01)
    assert first_pass.action == "pass" and first_pass.source.member_slot == 1
    assert first_pass.key() != attack.key()
    record(bot, first_pass, 52, 1.01)
    assert bot.next(hurt, 1.1) is None
    inactive_main = edit(hurt, 0, flags=0)
    assert bot.next(inactive_main, 1.2) is None
    select = bot.next(inactive_main, 1.71)
    assert select.action == "select" and select.source.member_slot == 2
    record(bot, select, 31, 1.71)
    selected = replace(inactive_main, selected_unit=select.source.address)
    second_pass = bot.next(selected, 1.72)
    assert second_pass.action == "pass" and second_pass.source.member_slot == 2
    assert not bot.profile.mercenaries[1].enabled  # Authorized by pass_remaining only.
    record(bot, second_pass, 52, 1.72)
    both_inactive = edit(selected, 1, flags=0)
    assert bot.next(both_inactive, 1.8) is None
    assert bot.next(both_inactive, 2.31) is None
    assert bot.queued == 3 and bot.passes_queued == 2 and len(bot.ledger) == 3
    assert bot.next(both_inactive, 5) is None and bot.running


def test_main_killing_all_enemies_stops_passes_and_leaves_time_for_loot(turn_frame):
    bot = engine(plan(pass_remaining=True))
    attack = bot.next(turn_frame, 0)
    record(bot, attack, 32, 0)
    dead = replace(
        turn_frame,
        units=tuple(replace(u, life=0) if u.world_slot != 1 else u for u in turn_frame.units),
    )
    for now in (0.1, 1, 5, 12):
        assert bot.next(dead, now) is None
    assert bot.passes_queued == 0 and bot.running and bot.pending is None


@pytest.mark.parametrize("instant", [False, True])
def test_no_pass_after_victory_when_optional_loot_is_enabled(turn_frame, instant):
    bot = engine(
        replace(plan(pass_remaining=True), collect_remaining_loot=True, instant_loot=instant)
    )
    attack = bot.next(turn_frame, 0)
    record(bot, attack, 32, 0)
    dead = replace(
        turn_frame,
        units=tuple(replace(u, life=0) if u.world_slot != 1 else u for u in turn_frame.units),
    )
    if not instant:
        assert bot.next(dead, 0.2) is None
        assert bot.next(dead, 1.1) is None
    loot = bot.next(dead, 0.2 if instant else 1.21)
    assert loot.action == "loot" and bot.passes_queued == 0


def test_changed_turn_is_reobserved_before_any_pass_and_never_ends_enemy_turn(turn_frame):
    bot = engine(plan(pass_remaining=True))
    attack = bot.next(turn_frame, 0)
    record(bot, attack, 32, 0)
    enemy = replace(turn_frame, turn_group=1, turn_number=1, turn_tick=124000)
    assert bot.next(enemy, 1) is None and bot.pending is None
    assert not bot.passes_queued
    next_own = replace(turn_frame, turn_number=2, turn_tick=125000)
    assert bot.next(next_own, 2).action == "basic"


def test_schema_seven_keeps_existing_magic_and_does_not_enable_passing(tmp_path):
    import json

    old = plan()
    payload = old.summary()
    payload["schema_version"] = 7
    del payload["pass_remaining"]
    for mercenary in payload["mercenaries"]:
        del mercenary["later_action"]
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    loaded = ProfileStore(tmp_path).load(1)
    assert loaded == old and not loaded.pass_remaining
    assert path.read_bytes() == saved


@pytest.mark.parametrize(
    "field,value", [("pass_remaining", 1), ("later_action", "Q"), ("later_action", "unknown")]
)
def test_invalid_pass_settings_cannot_replace_saved_profile(tmp_path, field, value):
    store = ProfileStore(tmp_path)
    original = plan()
    store.save(original)
    if field == "pass_remaining":
        invalid = replace(original, pass_remaining=value)
    else:
        invalid = replace(
            original,
            mercenaries=(
                replace(original.mercenaries[0], later_action=value),
                *original.mercenaries[1:],
            ),
        )
    with pytest.raises(DiagnosticError):
        store.save(invalid)
    assert store.load(1) == original


@pytest.mark.parametrize("later", ["basic", "defend", "pass"])
def test_magic_opener_uses_configured_later_action_and_nonmagic_commands_repeat(turn_frame, later):
    bot = engine(plan(later=later))
    first = bot.next(turn_frame, 0)
    record(bot, first, 32, 0)
    own_next = replace(turn_frame, turn_number=2, turn_tick=124000)
    assert bot.next(own_next, 2).action == later
    for action in ("defend", "pass"):
        guard = engine(plan(action=action))
        queued = guard.next(turn_frame, 0)
        record(guard, queued, 51 if action == "defend" else 52, 0)
        assert guard.next(own_next, 2).action == action


@pytest.mark.parametrize("action,code", [("defend", 51), ("pass", 52)])
def test_queued_stance_waits_for_progress_and_never_resends_on_timeout(turn_frame, action, code):
    bot = engine(plan(action=action))
    first = bot.next(turn_frame, 0)
    record(bot, first, code, 0)
    assert bot.next(turn_frame, 1) is None
    assert bot.next(turn_frame, 12) is None
    assert not bot.running and bot.needs_reconnect and bot.queued == 1


@pytest.mark.parametrize("action,code", [("defend", 53), ("pass", 54)])
def test_rejected_stance_never_falls_back_to_an_attack(turn_frame, action, code):
    bot = engine(plan(action=action))
    first = bot.next(turn_frame, 0)
    record(bot, first, code, 0)
    assert bot.next(turn_frame, 1) is None
    assert bot.running and not bot.ledger and bot.queued == 0


@pytest.mark.parametrize("status", [27, 28, 29])
def test_pass_selection_rechecks_are_bounded_and_keep_backoff(turn_frame, status):
    bot = engine(plan(action="pass"))
    frame = replace(turn_frame, selected_unit=0)
    for now in (0, 0.3, 0.6):
        trial = bot.next(frame, now)
        assert trial.action == "select"
        record(bot, trial, status, now)
        assert bot.next(frame, now + 0.1) is None
    assert bot.pass_unready_attempts == {1: 3} and bot.pass_skipped == {1}
    assert not bot.unready_attempts and bot.queued == 0


def test_restored_ledger_prevents_attack_or_second_pass_after_a_member_was_passed(turn_frame):
    bot = engine(plan(action="pass"))
    trial = bot.next(turn_frame, 0)
    record(bot, trial, 52, 0)
    restarted = TurnEngine(100, 777, plan(), bot.ledger)
    restarted.enter(fresh=True)
    assert restarted.next(turn_frame, 1) is None


def test_manual_turns_never_pass_automatically(turn_frame):
    bot = TurnEngine(100, 777, plan(pass_remaining=True), execute_orders=False)
    bot.enter(fresh=True)
    assert bot.next(turn_frame, 0) is None and not bot.ledger


def test_defend_and_pass_choices_and_followup_are_saved_per_character_profile(tmp_path):
    profile = plan(pass_remaining=True, later="defend")
    profile = replace(
        profile,
        mercenaries=(
            profile.mercenaries[0],
            replace(profile.mercenaries[1], action="pass", enabled=True),
            *profile.mercenaries[2:],
        ),
    )
    store = ProfileStore(tmp_path)
    store.save(profile)
    assert store.load(1) == profile
    rows = roster_rows(profile, None)
    assert rows[0]["later_action"] == "Defender (G)"
    assert rows[1]["opening_action"] == rows[1]["later_action"] == "Pasar acción (F)"
