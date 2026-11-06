import json
from dataclasses import replace

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, Mercenary, ProfileStore


def remove_new_turn_commands(payload):
    payload.pop("pass_remaining", None)
    for mercenary in payload["mercenaries"]:
        mercenary.pop("later_action", None)


def test_persists_selection_names_and_priority_without_touching_other_profiles(tmp_path):
    store = ProfileStore(tmp_path)
    first = BotProfile.default(1)
    assert store.load(1) == first
    assert list(tmp_path.iterdir()) == []
    mercenaries = list(reversed(first.mercenaries))
    mercenaries[0] = Mercenary(9, "Sanadora", False)
    updated = replace(first, mercenaries=tuple(mercenaries))
    store.save(updated)
    assert store.load(1) == updated
    assert store.load(2) == BotProfile.default(2)
    assert [path.name for path in tmp_path.iterdir()] == ["profile-1.json"]
    assert store.load(1).summary()["turn_execution_available"] is True


def test_magic_actions_and_fallback_are_saved_per_mercenary_in_priority_order(tmp_path):
    original = BotProfile.default(1)
    actions = ("basic", "Q", "W", "E", "R", "T", "basic", "basic", "basic")
    mercs = tuple(
        replace(merc, action=action, fallback_basic=merc.slot % 2 == 0)
        for merc, action in zip(original.mercenaries, actions, strict=True)
    )
    updated = replace(original, mercenaries=tuple(reversed(mercs)))
    store = ProfileStore(tmp_path)
    store.save(updated)
    assert store.load(1) == updated
    payload = json.loads((tmp_path / "profile-1.json").read_text())
    assert payload["schema_version"] == 11
    assert [m["action"] for m in payload["mercenaries"]] == list(reversed(actions))
    assert payload["turn_execution_available"] is True


def test_legacy_profile_migrates_in_memory_without_rewriting_or_losing_settings(tmp_path):
    original = BotProfile.default(1)
    mercs = list(reversed(original.mercenaries))
    mercs[0] = replace(mercs[0], name="Sanadora", enabled=False)
    legacy = {
        "schema_version": 1,
        "profile": 1,
        "mercenaries": [{"slot": m.slot, "name": m.name, "enabled": m.enabled} for m in mercs],
        "turn_execution_available": False,
    }
    path = tmp_path / "profile-1.json"
    saved = json.dumps(legacy, ensure_ascii=False).encode()
    path.write_bytes(saved)
    store = ProfileStore(tmp_path)
    loaded = store.load(1)
    assert loaded.mercenaries == tuple(mercs)
    assert all(m.action == "basic" and m.fallback_basic for m in loaded.mercenaries)
    assert path.read_bytes() == saved
    store.save(loaded)
    assert json.loads(path.read_bytes())["schema_version"] == 11
    assert store.load(1) == loaded


@pytest.mark.parametrize("instant", [False, True])
def test_instant_loot_keeps_saved_neo_wait_and_other_features(tmp_path, instant):
    profile = replace(
        BotProfile.default(1),
        collect_remaining_loot=True,
        instant_loot=instant,
        neo_loot_grace_seconds=3,
        general_speed_rate=2,
        auto_life_key="F9",
    )
    store = ProfileStore(tmp_path)
    store.save(profile)
    saved = store.load(1)
    assert saved == profile and saved.loot_grace_seconds == (0 if instant else 3)


def test_previous_profile_gets_instant_loot_without_rewriting_or_losing_neo_value(tmp_path):
    old = replace(BotProfile.default(1), collect_remaining_loot=True, neo_loot_grace_seconds=2.5)
    payload = old.summary()
    payload["schema_version"] = 10
    del payload["instant_loot"]
    path = tmp_path / "profile-1.json"
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    loaded = ProfileStore(tmp_path).load(1)
    assert loaded.instant_loot and loaded.loot_grace_seconds == 0
    assert loaded.neo_loot_grace_seconds == 2.5 and path.read_bytes() == raw


@pytest.mark.parametrize("invalid", [0, 1, "true", None])
def test_invalid_instant_loot_preserves_saved_profile(tmp_path, invalid):
    store = ProfileStore(tmp_path)
    original = BotProfile.default(1)
    store.save(original)
    with pytest.raises(DiagnosticError, match="inmediata"):
        store.save(replace(original, instant_loot=invalid))
    assert store.load(1) == original


@pytest.mark.parametrize("grace", [0, 0.25, 1, 5])
def test_neo_grace_is_saved_without_changing_combat_settings(tmp_path, grace):
    original = BotProfile.default(1)
    profile = replace(original, neo_loot_grace_seconds=grace)
    store = ProfileStore(tmp_path)
    store.save(profile)
    assert store.load(1) == profile


def test_schema_six_keeps_previous_neo_wait_and_does_not_rewrite_saved_profile(tmp_path):
    payload = replace(BotProfile.default(1), battle_speed_enabled=True).summary()
    payload["schema_version"] = 6
    remove_new_turn_commands(payload)
    del payload["neo_loot_grace_seconds"]
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    loaded = ProfileStore(tmp_path).load(1)
    assert loaded.neo_loot_grace_seconds == 1 and loaded.battle_speed_enabled
    assert path.read_bytes() == saved


@pytest.mark.parametrize("grace", [-0.1, 5.1, float("nan"), float("inf"), True, "0"])
def test_invalid_neo_wait_preserves_saved_profile(tmp_path, grace):
    store = ProfileStore(tmp_path)
    original = BotProfile.default(1)
    store.save(original)
    with pytest.raises(DiagnosticError, match="NeoACA"):
        store.save(replace(original, neo_loot_grace_seconds=grace))
    assert store.load(1) == original


def test_incomplete_neo_wait_in_current_schema_is_rejected(tmp_path):
    payload = BotProfile.default(1).summary()
    del payload["neo_loot_grace_seconds"]
    path = tmp_path / "profile-1.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(DiagnosticError, match="archivo se conserva"):
        ProfileStore(tmp_path).load(1)


@pytest.mark.parametrize(
    "action,fallback", [("Z", True), ("q", True), ([], True), (1, True), ("Q", 1)]
)
def test_invalid_actions_preserve_existing_profile(tmp_path, action, fallback):
    profile = BotProfile.default(1)
    store = ProfileStore(tmp_path)
    store.save(profile)
    bad = replace(profile.mercenaries[0], action=action, fallback_basic=fallback)
    with pytest.raises(DiagnosticError):
        store.save(replace(profile, mercenaries=(bad, *profile.mercenaries[1:])))
    assert store.load(1) == profile


@pytest.mark.parametrize("missing", ["action", "fallback_basic", "target", "later_action"])
def test_incomplete_new_schema_is_rejected_instead_of_silently_changing_actions(tmp_path, missing):
    payload = BotProfile.default(1).summary()
    del payload["mercenaries"][0][missing]
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    with pytest.raises(DiagnosticError, match="archivo se conserva"):
        ProfileStore(tmp_path).load(1)
    assert path.read_bytes() == saved


def test_schema_two_preserves_order_actions_and_fallback_without_rewriting(tmp_path):
    payload = BotProfile.default(1).summary()
    payload["schema_version"] = 2
    remove_new_turn_commands(payload)
    del payload["magic_first_turn_only"]
    payload["mercenaries"].reverse()
    for merc in payload["mercenaries"]:
        del merc["target"]
    payload["mercenaries"][0].update(action="W", fallback_basic=False, enabled=False)
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    profile = ProfileStore(tmp_path).load(1)
    assert profile.mercenaries[0] == Mercenary(9, "Puesto 9", False, "W", False)
    assert profile.magic_first_turn_only
    assert all(m.target == "enemy" for m in profile.mercenaries)
    assert path.read_bytes() == saved


def test_magic_target_and_repeat_mode_survive_roundtrip(tmp_path):
    original = BotProfile.default(1)
    mercs = list(original.mercenaries)
    mercs[0] = replace(mercs[0], action="Q", target="self")
    mercs[1] = replace(mercs[1], action="W", target="slot_1")
    profile = replace(original, mercenaries=tuple(mercs), magic_first_turn_only=False)
    store = ProfileStore(tmp_path)
    store.save(profile)
    assert store.load(1) == profile


def test_hunt_options_are_saved_per_profile_with_mercenary_order(tmp_path):
    original = BotProfile.default(2)
    updated = replace(
        original,
        attack_delay_seconds=1.25,
        search_radius=400,
        collect_remaining_loot=True,
        mercenaries=tuple(reversed(original.mercenaries)),
    )
    store = ProfileStore(tmp_path)
    store.save(updated)
    assert store.load(2) == updated
    assert store.load(1) == BotProfile.default(1)


@pytest.mark.parametrize("mode", ["native", "stationary", "nearby"])
def test_encounter_mode_is_saved_with_delay_and_mercenaries(tmp_path, mode):
    profile = replace(
        BotProfile.default(2), world_attack_mode=mode, search_radius=200, attack_delay_seconds=1.5
    )
    store = ProfileStore(tmp_path)
    store.save(profile)
    assert store.load(2) == profile


@pytest.mark.parametrize("rate", [1.25, 1.5, 2, 3, 4])
def test_speed_options_survive_profile_save_and_reload(tmp_path, rate):
    profile = replace(BotProfile.default(1), battle_speed_enabled=True, battle_speed_rate=rate)
    store = ProfileStore(tmp_path)
    store.save(profile)
    assert store.load(1) == profile


def test_schema_five_keeps_hunt_and_team_but_starts_with_speed_disabled(tmp_path):
    payload = replace(BotProfile.default(1), world_attack_mode="stationary").summary()
    payload["schema_version"] = 5
    remove_new_turn_commands(payload)
    del payload["battle_speed_enabled"], payload["battle_speed_rate"]
    path = tmp_path / "profile-1.json"
    saved = json.dumps(payload).encode()
    path.write_bytes(saved)
    profile = ProfileStore(tmp_path).load(1)
    assert profile.world_attack_mode == "stationary" and not profile.battle_speed_enabled
    assert profile.battle_speed_rate == 1.25 and path.read_bytes() == saved


@pytest.mark.parametrize("rate", [True, "3", 0, 1, 1.45, 5, float("nan"), float("inf")])
def test_invalid_speed_cannot_replace_saved_profile(tmp_path, rate):
    store = ProfileStore(tmp_path)
    original = BotProfile.default(1)
    store.save(original)
    with pytest.raises(DiagnosticError):
        store.save(replace(original, battle_speed_rate=rate))
    assert store.load(1) == original


def test_schema_four_preserves_previous_hunt_settings_and_defaults_to_native_pursuit(tmp_path):
    payload = replace(
        BotProfile.default(1),
        search_radius=200,
        collect_remaining_loot=True,
        attack_delay_seconds=3,
    ).summary()
    payload["schema_version"] = 4
    remove_new_turn_commands(payload)
    del payload["world_attack_mode"]
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    loaded = ProfileStore(tmp_path).load(1)
    assert loaded.world_attack_mode == "native" and loaded.search_radius == 200
    assert loaded.collect_remaining_loot and loaded.attack_delay_seconds == 3
    assert path.read_bytes() == saved


@pytest.mark.parametrize("mode", [None, "", "teleport", 1, True, []])
def test_invalid_encounter_mode_cannot_overwrite_saved_profile(tmp_path, mode):
    store = ProfileStore(tmp_path)
    original = BotProfile.default(1)
    store.save(original)
    with pytest.raises(DiagnosticError):
        store.save(replace(original, world_attack_mode=mode))
    assert store.load(1) == original


def test_missing_mode_in_new_schema_is_rejected_without_resetting_profile(tmp_path):
    payload = BotProfile.default(1).summary()
    del payload["world_attack_mode"]
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    with pytest.raises(DiagnosticError):
        ProfileStore(tmp_path).load(1)
    assert path.read_bytes() == saved


def test_schema_three_keeps_team_settings_and_uses_safe_hunt_defaults_without_rewriting(tmp_path):
    payload = replace(BotProfile.default(1), magic_first_turn_only=False).summary()
    payload["schema_version"] = 3
    remove_new_turn_commands(payload)
    for key in ("attack_delay_seconds", "search_radius", "collect_remaining_loot"):
        del payload[key]
    payload["mercenaries"][0].update(action="Q", target="self", fallback_basic=False)
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    loaded = ProfileStore(tmp_path).load(1)
    assert loaded.mercenaries[0].action == "Q" and loaded.mercenaries[0].target == "self"
    assert not loaded.magic_first_turn_only and not loaded.mercenaries[0].fallback_basic
    assert loaded.attack_delay_seconds == 0 and loaded.search_radius == 60
    assert not loaded.collect_remaining_loot and path.read_bytes() == saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("attack_delay_seconds", -1),
        ("attack_delay_seconds", 60.1),
        ("attack_delay_seconds", True),
        ("attack_delay_seconds", float("nan")),
        ("attack_delay_seconds", float("inf")),
        ("search_radius", 4),
        ("search_radius", 501),
        ("search_radius", True),
        ("collect_remaining_loot", 1),
    ],
)
def test_invalid_hunt_options_preserve_saved_profile(tmp_path, field, value):
    original = BotProfile.default(1)
    store = ProfileStore(tmp_path)
    store.save(original)
    with pytest.raises(DiagnosticError):
        store.save(replace(original, **{field: value}))
    assert store.load(1) == original


@pytest.mark.parametrize(
    "field", ["attack_delay_seconds", "search_radius", "collect_remaining_loot"]
)
def test_incomplete_hunt_options_in_new_schema_do_not_reset_saved_settings(tmp_path, field):
    payload = BotProfile.default(1).summary()
    del payload[field]
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    with pytest.raises(DiagnosticError):
        ProfileStore(tmp_path).load(1)
    assert path.read_bytes() == saved


@pytest.mark.parametrize("target", ["slot_0", "slot_10", "everyone", 1, []])
def test_invalid_targets_preserve_saved_profile(tmp_path, target):
    original = BotProfile.default(1)
    store = ProfileStore(tmp_path)
    store.save(original)
    bad = replace(original.mercenaries[0], target=target)
    with pytest.raises(DiagnosticError):
        store.save(replace(original, mercenaries=(bad, *original.mercenaries[1:])))
    assert store.load(1) == original


@pytest.mark.parametrize("mode", [None, 1, "true"])
def test_invalid_or_missing_first_turn_setting_does_not_rewrite_file(tmp_path, mode):
    payload = BotProfile.default(1).summary()
    if mode is None:
        del payload["magic_first_turn_only"]
    else:
        payload["magic_first_turn_only"] = mode
    saved = json.dumps(payload).encode()
    path = tmp_path / "profile-1.json"
    path.write_bytes(saved)
    with pytest.raises(DiagnosticError):
        ProfileStore(tmp_path).load(1)
    assert path.read_bytes() == saved


@pytest.mark.parametrize("number", [0, 4, True, "../game", 1.0])
def test_profile_selection_cannot_write_outside_the_three_profiles(tmp_path, number):
    with pytest.raises(DiagnosticError):
        ProfileStore(tmp_path).load(number)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "mercenary",
    [Mercenary(1, ""), Mercenary(1, "a" * 41), Mercenary(1, "x\nx"), Mercenary(1, "X", 1)],
)
def test_invalid_names_and_boolean_values_do_not_overwrite_a_saved_profile(tmp_path, mercenary):
    store = ProfileStore(tmp_path)
    profile = BotProfile.default(1)
    store.save(profile)
    with pytest.raises(DiagnosticError):
        store.save(replace(profile, mercenaries=(mercenary, *profile.mercenaries[1:])))
    assert store.load(1) == profile


def test_duplicate_or_missing_positions_are_rejected(tmp_path):
    profile = BotProfile.default(1)
    store = ProfileStore(tmp_path)
    with pytest.raises(DiagnosticError):
        store.save(replace(profile, mercenaries=profile.mercenaries[:8]))
    with pytest.raises(DiagnosticError):
        store.save(replace(profile, mercenaries=(profile.mercenaries[1], *profile.mercenaries[1:])))


@pytest.mark.parametrize("data", [b"{broken", b"[]", b"x" * 32769, b"\xff"])
def test_corrupt_profiles_are_preserved_and_not_silently_replaced(tmp_path, data):
    path = tmp_path / "profile-1.json"
    path.write_bytes(data)
    with pytest.raises(DiagnosticError):
        ProfileStore(tmp_path).load(1)
    assert path.read_bytes() == data


def test_wrong_profile_number_is_rejected_on_load(tmp_path):
    payload = BotProfile.default(2).summary()
    (tmp_path / "profile-1.json").write_text(json.dumps(payload))
    with pytest.raises(DiagnosticError):
        ProfileStore(tmp_path).load(1)


def test_atomic_save_failure_preserves_previous_file_and_removes_temporary(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path)
    profile = BotProfile.default(1)
    store.save(profile)

    def fail_replace(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr("atlantica_bot.profiles.os.replace", fail_replace)
    with pytest.raises(OSError):
        store.save(replace(profile, mercenaries=tuple(reversed(profile.mercenaries))))
    assert store.load(1) == profile
    assert [path.name for path in tmp_path.iterdir()] == ["profile-1.json"]
