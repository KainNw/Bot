import json
from dataclasses import replace

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, Mercenary, ProfileStore


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
    assert payload["schema_version"] == 3
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
    assert json.loads(path.read_bytes())["schema_version"] == 3
    assert store.load(1) == loaded


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


@pytest.mark.parametrize("missing", ["action", "fallback_basic", "target"])
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
