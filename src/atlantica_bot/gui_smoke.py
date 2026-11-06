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
        assert panel.instant_loot.get()
        assert str(panel.neo_loot_grace_entry.cget("state")) == "disabled"
        panel.instant_loot_check.invoke()
        assert not panel.instant_loot.get()
        assert str(panel.neo_loot_grace_entry.cget("state")) == "normal"
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
        panel.edit_profile()

        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)

        editor_widgets = list(children(panel.profile_editor))
        main_check = next(
            widget
            for widget in editor_widgets
            if widget.winfo_class() == "TCheckbutton" and widget.cget("text") == "Main (1)"
        )
        main_controls = list(children(main_check.master))
        initial = next(
            widget
            for widget in main_controls
            if widget.winfo_class() == "TCombobox" and len(widget.cget("values")) == 8
        )
        initial.set("Magia Q")
        initial.event_generate("<<ComboboxSelected>>")
        later = next(
            widget
            for widget in main_controls
            if widget.winfo_class() == "TCombobox" and len(widget.cget("values")) == 3
        )
        later.set("Defender (G)")
        next(
            widget
            for widget in editor_widgets
            if widget.winfo_class() == "TCheckbutton"
            and str(widget.cget("text")).startswith("Pasar las acciones restantes")
        ).invoke()
        next(
            widget
            for widget in editor_widgets
            if widget.winfo_class() == "TButton"
            and widget.cget("text") == "Solo Main + pasar las acciones restantes"
        ).invoke()
        next(
            widget
            for widget in editor_widgets
            if widget.winfo_class() == "TButton" and widget.cget("text") == "Guardar perfil"
        ).invoke()
        assert panel.profile.pass_remaining
        assert [m.slot for m in panel.profile.mercenaries if m.enabled] == [1]
        assert next(m for m in panel.profile.mercenaries if m.slot == 1).later_action == "defend"
        members = panel.profile.mercenaries
        panel.profile_editor.destroy()
        first_store = panel.character_store
        saved = first_store.load(2)
        assert saved.search_radius == 275 and saved.collect_remaining_loot
        assert not saved.instant_loot
        assert saved.battle_speed_enabled and saved.battle_speed_rate == 3
        assert saved.neo_loot_grace_seconds == 0.25 and saved.attack_delay_seconds == 1.5
        assert first_store.load_preferences() == CharacterPreferences(2, True)
        assert not panel.general_speed_enabled.get()
        with patch.object(panel, "apply_general_speed") as apply_speed:
            panel.general_speed_check.invoke()
            apply_speed.assert_called_once()
        panel.general_speed_rate.set("2")
        panel.auto_life_enabled.set(True)
        panel.auto_life_threshold.set("45")
        panel.auto_life_key.set("F9")
        panel.flush_character_settings()
        assert panel.general_speed_enabled.get() and not panel.battle_speed_enabled.get()
        assert first_store.load(2).general_speed_rate == 2
        assert first_store.load(2).battle_speed_rate == 3
        assert first_store.load(2).auto_life_enabled
        assert first_store.load(2).auto_life_threshold == 45
        assert first_store.load(2).auto_life_key == "F9"
        panel.battle_speed_check.invoke()
        panel.flush_character_settings()
        assert panel.battle_speed_enabled.get() and not panel.general_speed_enabled.get()
        assert panel.battle_speed_rate.get() == "3" and panel.general_speed_rate.get() == "2"
        with patch.object(panel, "apply_general_speed"):
            panel.general_speed_check.invoke()
        panel.flush_character_settings()

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
        assert not panel.general_speed_enabled.get()
        panel.search_radius.set("15")
        panel.flush_character_settings()
        second_store = panel.character_store

        connect(303, 30, "MainUno")
        assert panel.character_store.key == first_store.key
        assert panel.profile_number.get() == "2" and panel.turns_enabled.get()
        assert panel.search_radius.get() == "300" and panel.collect_loot.get()
        assert not panel.instant_loot.get()
        assert panel.profile.mercenaries == members
        assert panel.profile.pass_remaining
        assert panel.general_speed_enabled.get() and panel.general_speed_rate.get() == "2"
        assert panel.auto_life_enabled.get() and panel.auto_life_key.get() == "F9"
        assert panel.auto_life_threshold.get() == "45"
        assert not panel.battle_speed_enabled.get() and panel.battle_speed_rate.get() == "3"
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

        # The new independent preference survives PID changes without replacing
        # the existing bot's battle speed or starting either clock on load.
        panel.battle_speed_enabled.set(True)
        panel.battle_speed_rate.set("3")
        panel.independent_battle_speed_rate.set("2")
        with patch.object(panel, "apply_independent_battle_speed") as apply_speed:
            panel.independent_battle_speed_check.invoke()
            apply_speed.assert_called_once()
        panel.flush_character_settings()
        saved = third_store.load(1)
        assert saved.independent_battle_speed_enabled and saved.independent_battle_speed_rate == 2
        assert saved.battle_speed_enabled and saved.battle_speed_rate == 3
        connect(606, 60, "MainTres")
        assert panel.independent_battle_speed_enabled.get()
        assert panel.independent_battle_speed_rate.get() == "2"
        assert panel.battle_speed_enabled.get() and panel.battle_speed_rate.get() == "3"
        assert panel.independent_battle_speed_worker is None and panel.bot_worker is None

        panel.session = None
        panel.template_profile_store = original_templates
        panel.sync_identity()


def check_general_speed_controls(panel) -> None:
    """The real checkbox must start a clock with no hunting worker or game access."""
    calls = []

    class Worker:
        def __init__(self, session, window, rate):
            self.window = window
            self.alive = False
            self.report = {
                "pid": window.pid,
                "creation_time": session.creation_time,
                "mode": "general",
                "enabled": True,
                "armed": True,
                "current_rate": rate,
                "message": "General activo",
            }

        def start(self):
            calls.append("start general")
            self.alive = True

        def stop(self):
            calls.append("stop general")
            self.alive = False
            self.report.update(armed=False, current_rate=1, message="Velocidad normal")

    original = panel.session
    panel.session = SimpleNamespace(
        process=SimpleNamespace(pid=777),
        creation_time=888,
        snapshot=lambda: None,
    )
    window = SimpleNamespace(pid=777, handle=0x1234, thread_id=500)
    try:
        with (
            patch("atlantica_bot.gui.GeneralSpeedWorker", Worker),
            patch.object(panel, "selected_window", return_value=window),
        ):
            panel.general_speed_enabled.set(False)
            panel.battle_speed_enabled.set(False)
            panel.lock_target_controls()
            panel.general_speed_check.invoke()
            assert panel.bot_worker is None and panel.general_speed_worker.alive
            panel.poll_general_speed()
            assert "General activo" in panel.general_speed_status.get()
            panel.stop_bot()
            assert panel.general_speed_worker.alive and calls == ["start general"]
            panel.general_speed_check.invoke()
            panel.poll_general_speed()
            assert panel.general_speed_worker is None and panel.bot_worker is None
            assert panel.general_speed_report["current_rate"] == 1
            assert calls == ["start general", "stop general"]
    finally:
        panel.session = original
        panel.general_speed_report = {}
        panel.lock_target_controls()


def check_independent_battle_speed_controls(panel) -> None:
    calls = []

    class Worker:
        def __init__(self, session, window, rate):
            assert rate == 2
            self.window = window
            self.alive = False
            self.report = {
                "pid": window.pid,
                "creation_time": session.creation_time,
                "mode": "battle",
                "independent": True,
                "enabled": True,
                "armed": True,
                "current_rate": 1,
                "message": "Esperando combate",
            }

        def start(self):
            calls.append("arm")
            self.alive = True

        def stop(self):
            calls.append("restore")
            self.alive = False
            self.report.update(armed=False, current_rate=1, message="Velocidad normal")

    original_session, original_profile, original_detector = (
        panel.session,
        panel.profile,
        panel.detector,
    )
    panel.session = SimpleNamespace(
        process=SimpleNamespace(pid=777),
        creation_time=888,
        snapshot=lambda: SimpleNamespace(
            auto_battle=False, hunting=False, files=SimpleNamespace(marker_present=False)
        ),
    )
    window = SimpleNamespace(pid=777, handle=0x1234, thread_id=500)
    try:
        with (
            patch("atlantica_bot.gui.IndependentBattleSpeedWorker", Worker),
            patch.object(panel, "selected_window", return_value=window),
            patch.object(panel, "error") as error,
        ):
            panel.independent_battle_speed_enabled.set(False)
            panel.independent_battle_speed_rate.set("2")
            panel.general_speed_enabled.set(False)
            panel.battle_speed_enabled.set(True)
            panel.battle_speed_rate.set("3")
            panel.profile = replace(
                BotProfile.default(1), battle_speed_enabled=True, battle_speed_rate=3
            )
            panel.lock_target_controls()
            panel.independent_battle_speed_check.invoke()
            worker = panel.independent_battle_speed_worker
            assert worker.alive and panel.bot_worker is None and calls == ["arm"]
            assert not panel.target_is_editable() and "independiente" in panel.detail.get()
            assert panel.battle_speed_enabled.get() and panel.battle_speed_rate.get() == "3"
            assert str(panel.general_speed_check.cget("state")) == "disabled"
            panel.poll_independent_battle_speed()
            assert "Esperando combate" in panel.independent_battle_speed_status.get()
            worker.report.update(current_rate=2, message="En combate")
            panel.poll_independent_battle_speed()
            assert "2×" in panel.independent_battle_speed_status.get()
            worker.report.update(current_rate=1, message="Regreso al mapa")
            panel.poll_independent_battle_speed()
            assert worker.alive and worker.report["armed"]
            panel.stop_bot()
            assert worker.alive and calls == ["arm"]
            # Starting the original bot must never add a second clock owner.
            from .combat import CombatDetector

            panel.detector = CombatDetector(777, 888, "local_context")
            with (
                patch.object(panel, "refresh_main_identity"),
                patch("atlantica_bot.gui.HuntWorker") as hunt,
            ):
                panel.start_bot()
                hunt.assert_not_called()
            assert error.call_count == 1 and "independiente" in str(error.call_args.args[0])
            assert panel.battle_speed_enabled.get() and panel.battle_speed_rate.get() == "3"
            panel.independent_battle_speed_check.invoke()
            panel.poll_independent_battle_speed()
            assert panel.independent_battle_speed_worker is None
            assert (
                calls == ["arm", "restore"]
                and panel.independent_battle_speed_report["current_rate"] == 1
            )
            assert panel.battle_speed_enabled.get() and panel.battle_speed_rate.get() == "3"
    finally:
        panel.session, panel.profile, panel.detector = (
            original_session,
            original_profile,
            original_detector,
        )
        panel.independent_battle_speed_report = {}
        panel.lock_target_controls()
