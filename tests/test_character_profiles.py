import json
from dataclasses import replace

import pytest

from atlantica_bot.character_profiles import (
    CharacterPreferences,
    CharacterProfileStore,
    character_key,
)
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, ProfileStore

CLIENT = r"C:\Games\Atlantica"


def configured(number=2):
    profile = BotProfile.default(number)
    return replace(
        profile,
        mercenaries=tuple(
            replace(m, action="Q" if m.slot == 1 else "basic", enabled=m.slot <= 2)
            for m in reversed(profile.mercenaries)
        ),
        magic_first_turn_only=False,
        attack_delay_seconds=3,
        search_radius=350,
        collect_remaining_loot=True,
        neo_loot_grace_seconds=0.25,
        world_attack_mode="stationary",
        battle_speed_enabled=True,
        battle_speed_rate=3,
    )


def test_character_reconnect_restores_all_settings_and_last_profile_without_pid(tmp_path):
    templates = ProfileStore(tmp_path)
    legacy = replace(BotProfile.default(2), search_radius=100)
    templates.save(legacy)
    first = CharacterProfileStore(templates, CLIENT, "MainUno")
    assert first.load(2) == legacy
    assert first.load_preferences() == CharacterPreferences()
    assert not first.directory.exists()  # Connecting and reading do not write defaults.
    profile = configured()
    first.save(profile)
    first.save_preferences(CharacterPreferences(2, True))
    reconnected = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "MainUno")
    assert reconnected.directory == first.directory
    assert reconnected.load_preferences() == CharacterPreferences(2, True)
    assert reconnected.load(2) == profile
    assert templates.load(2) == legacy
    record = json.loads((first.directory / "character.json").read_text())
    assert "pid" not in record and "creation_time" not in record


def test_different_characters_and_installations_have_independent_profiles(tmp_path):
    templates = ProfileStore(tmp_path)
    first = CharacterProfileStore(templates, CLIENT, "MainUno")
    second = CharacterProfileStore(templates, CLIENT, "MainDos")
    other_server = CharacterProfileStore(templates, r"C:\OtherServer", "MainUno")
    first.save(configured())
    first.save_preferences(CharacterPreferences(2, True))
    for store in (second, other_server):
        assert store.load_preferences() == CharacterPreferences()
        assert store.load(2) == BotProfile.default(2)
    second.save(replace(configured(), search_radius=25))
    assert first.load(2).search_radius == 350
    assert second.load(2).search_radius == 25
    assert other_server.load(2).search_radius == 60


def test_windows_directory_casing_and_slashes_and_unicode_normalization_keep_same_key(tmp_path):
    templates = ProfileStore(tmp_path)
    first = CharacterProfileStore(templates, r"C:\Games\Atlantica\.", "José")
    second = CharacterProfileStore(templates, "c:/games/atlantica", "Jose\u0301")
    assert first.directory == second.directory
    first.save(configured())
    assert second.load(2) == configured()


def test_names_are_hashed_in_filenames_and_never_interpreted_as_paths(tmp_path):
    store = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "../Hero:Uno")
    store.save(configured())
    assert store.directory.parent == tmp_path / "characters"
    assert len(store.directory.name) == 64
    assert all(char in "0123456789abcdef" for char in store.directory.name)


@pytest.mark.parametrize("name", [None, 1, "", " Hero", "Hero\n", "?", "a" * 24, "\ud800"])
def test_invalid_or_unverified_names_cannot_create_character_files(tmp_path, name):
    with pytest.raises(DiagnosticError):
        CharacterProfileStore(ProfileStore(tmp_path), CLIENT, name)
    assert list(tmp_path.iterdir()) == []


def test_relative_installation_is_not_a_character_key():
    with pytest.raises(DiagnosticError):
        character_key("Atlantica", "Main")


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("character_name", "OtherMain"),
        ("client_directory", r"c:\other"),
        ("selected_profile", True),
        ("selected_profile", 4),
        ("execute_turns", 1),
        ("execute_turns", "false"),
    ],
)
def test_invalid_character_record_is_preserved_without_automatic_replacement(tmp_path, key, value):
    store = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "MainUno")
    store.save_preferences(CharacterPreferences(3, False))
    path = store.directory / "character.json"
    payload = json.loads(path.read_text())
    payload[key] = value
    saved = json.dumps(payload).encode()
    path.write_bytes(saved)
    with pytest.raises(DiagnosticError, match="se conserva"):
        store.load_preferences()
    with pytest.raises(DiagnosticError, match="se conserva"):
        store.save_preferences(CharacterPreferences())
    assert path.read_bytes() == saved


@pytest.mark.parametrize("raw", [b"[]", b"null", b"{", b"\xff", b" " * 4097])
def test_broken_or_oversized_record_cannot_be_applied(tmp_path, raw):
    store = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "MainUno")
    store.directory.mkdir(parents=True)
    (store.directory / "character.json").write_bytes(raw)
    with pytest.raises(DiagnosticError):
        store.load_preferences()


def test_corrupt_character_profile_is_not_silently_replaced_with_global_template(tmp_path):
    templates = ProfileStore(tmp_path)
    templates.save(configured())
    store = CharacterProfileStore(templates, CLIENT, "MainUno")
    store.directory.mkdir(parents=True)
    path = store.directory / "profile-2.json"
    path.write_text("broken")
    with pytest.raises(DiagnosticError):
        store.load(2)
    assert path.read_text() == "broken" and templates.load(2) == configured()


def test_independent_panel_instances_preserve_other_profiles_of_same_character(tmp_path):
    first = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "MainUno")
    second = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "MainUno")
    first.save(configured(1))
    second.save(configured(3))
    assert first.load(3) == configured(3)
    assert second.load(1) == configured(1)
    assert second.load(2) == BotProfile.default(2)


def test_failed_atomic_preferences_save_keeps_previous_settings_and_cleans_temporary(
    tmp_path, monkeypatch
):
    store = CharacterProfileStore(ProfileStore(tmp_path), CLIENT, "MainUno")
    store.save_preferences(CharacterPreferences(3, True))
    path = store.directory / "character.json"
    saved = path.read_bytes()

    def fail(*_):
        raise OSError("simulated write failure")

    monkeypatch.setattr("atlantica_bot.profiles.os.replace", fail)
    with pytest.raises(OSError):
        store.save_preferences(CharacterPreferences(1, False))
    assert path.read_bytes() == saved
    assert list(store.directory.iterdir()) == [path]
