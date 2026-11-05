"""Exercise character settings in the packaged GUI using temporary files and fake sessions."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from .character_profiles import CharacterPreferences
from .errors import SceneChanged
from .identity import MainIdentity
from .profiles import WORLD_ATTACK_LABELS, BotProfile, ProfileStore


def check_character_settings(panel) -> None:
    original_templates = panel.template_profile_store

    def changing_state():
        raise SceneChanged("Display-only character settings test")

    def identify(pid, created, name):
        identity = MainIdentity(pid, created, 0x300000, (100, 200, 0), name)
        with patch("atlantica_bot.gui.read_main_identity", return_value=identity):
            panel.refresh_main_identity(force=True)

    def connect(pid, created, name, *, orderly=True):
        if orderly:
            panel.disconnect()
        panel.session = None
        panel.pid.set(str(pid))
        panel.session = SimpleNamespace(
            process=SimpleNamespace(pid=pid),
            creation_time=created,
            directory=Path("C:/Games/Atlantica"),
            snapshot=changing_state,
        )
        panel.sync_identity()
        identify(pid, created, name)

    with TemporaryDirectory(prefix="atlantica-character-settings-") as directory:
        templates = ProfileStore(Path(directory))
        legacy = replace(BotProfile.default(2), search_radius=120)
        templates.save(legacy)
        panel.template_profile_store = templates

        connect(101, 10, "MainUno")
        assert panel.profile_number.get() == "1" and not panel.turns_enabled.get()
        assert not panel.character_store.directory.exists()
        panel.profile_number.set("2")
        panel.load_profile(event=object())
        assert panel.search_radius.get() == "120"
        panel.search_radius.set("275")
        panel.attack_delay.set("1,5")
        panel.collect_loot.set(True)
        panel.neo_loot_grace.set("0,25")
        panel.world_attack_mode.set(WORLD_ATTACK_LABELS["stationary"])
        panel.battle_speed_enabled.set(True)
        panel.battle_speed_rate.set("3")
        panel.turns_enabled.set(True)
        detected = MainIdentity(101, 10, 0x300000, (100, 200, 0), "MainUno")
        with patch("atlantica_bot.gui.read_main_identity", return_value=detected):
            panel.root.after(650, panel.root.quit)
            panel.root.mainloop()
        assert panel.settings_save_job is None and not panel.settings_dirty
        members = tuple(
            replace(m, action="Q" if m.slot == 1 else "basic", enabled=m.slot <= 2)
            for m in reversed(panel.profile.mercenaries)
        )
        panel.persist_profile(replace(panel.profile, mercenaries=members))
        first_store = panel.character_store
        saved = first_store.load(2)
        assert saved.search_radius == 275 and saved.collect_remaining_loot
        assert saved.battle_speed_enabled and saved.battle_speed_rate == 3
        assert saved.neo_loot_grace_seconds == 0.25 and saved.attack_delay_seconds == 1.5
        assert first_store.load_preferences() == CharacterPreferences(2, True)

        # Invalid input keeps the previous file, and name polling preserves live edits.
        path = first_store.directory / "profile-2.json"
        previous = path.read_bytes()
        panel.attack_delay.set("incompleto")
        panel.flush_character_settings()
        assert path.read_bytes() == previous
        assert "Cambios sin guardar" in panel.character_settings_status.get()
        panel.attack_delay.set("1,5")
        panel.search_radius.set("300")
        identify(101, 10, "MainUno")
        assert panel.search_radius.get() == "300"
        panel.flush_character_settings()
        assert templates.load(2) == legacy

        connect(202, 20, "MainDos")
        assert panel.character_store.key != first_store.key
        assert panel.search_radius.get() == "60" and not panel.turns_enabled.get()
        assert not panel.battle_speed_enabled.get()
        panel.search_radius.set("15")
        panel.flush_character_settings()
        second_store = panel.character_store

        connect(303, 30, "MainUno")
        assert panel.character_store.key == first_store.key
        assert panel.profile_number.get() == "2" and panel.turns_enabled.get()
        assert panel.search_radius.get() == "300" and panel.collect_loot.get()
        assert panel.profile.mercenaries == members
        assert panel.bot_worker is None and panel.speed_experiment is None

        # An unflushed callback from a replaced PID must not write into either character.
        panel.search_radius.set("310")
        assert panel.settings_save_job is not None
        connect(404, 40, "MainDos", orderly=False)
        assert panel.settings_save_job is None and not panel.settings_dirty
        assert first_store.load(2).search_radius == 300
        assert panel.search_radius.get() == "15"

        # Manual aliases never load a different character's settings or enable writes.
        panel.main_identity = None
        panel.main_alias.set("MainUno")
        panel.search_radius.set("14")
        panel.flush_character_settings()
        assert second_store.load(1).search_radius == 15
        identify(404, 40, "MainDos")
        panel.flush_character_settings()
        assert second_store.load(1).search_radius == 14

        # Do not replace settings during another operation; load after it finishes.
        panel.calibrating = True
        identify(404, 40, "MainTres")
        assert panel.character_store.key == second_store.key
        assert not panel.character_settings_match()
        panel.calibrating = False
        identify(404, 40, "MainTres")
        third_store = panel.character_store
        assert third_store.key != second_store.key and panel.search_radius.get() == "60"
        assert panel.bot_worker is None

        # Corrupt settings must not disconnect the client or overwrite their contents.
        third_store.save_preferences(CharacterPreferences())
        metadata = third_store.directory / "character.json"
        valid = metadata.read_bytes()
        metadata.write_text("broken")
        connect(505, 50, "MainTres")
        assert panel.session.process.pid == 505 and panel.main_identity.name == "MainTres"
        assert (
            panel.profile is None and "No se pudo cargar" in panel.character_settings_status.get()
        )
        panel.search_radius.set("250")
        panel.flush_character_settings()
        assert metadata.read_text() == "broken"
        metadata.write_bytes(valid)
        identify(505, 50, "MainTres")
        assert panel.profile == BotProfile.default(1)

        panel.session = None
        panel.template_profile_store = original_templates
        panel.sync_identity()
