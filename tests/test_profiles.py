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
    assert store.load(1).summary()["turn_execution_available"] is False


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
