from __future__ import annotations

from test_ce_speed_trial import FakeCE, install_fake_gui


def map_state(ce):
    ce.memory[ce.actor + 0x318], ce.memory[0x1539CE18] = 0xFFFFFFFF, 0


def battle_state(ce):
    ce.memory[ce.actor + 0x318], ce.memory[0x1539CE18] = 0, 1


def active_auto(ce, rate=3):
    auto = ce.module.newAutomatic(ce.api)
    assert auto.start(rate)
    auto.tick()
    assert ce.rate_calls == [] and auto.phase == "arming"
    ce.now += 199
    auto.tick()
    assert ce.rate_calls == []
    ce.now += 1
    auto.tick()
    assert auto.phase == "active" and ce.rate_calls[-1][-1] == rate
    return auto


def rates(ce):
    return [call[-1] for call in ce.rate_calls]


def test_automatic_can_wait_on_map_with_bot_running_without_injecting_speed():
    ce = FakeCE()
    ce.lease_available = False  # The ordinary bot owns its own mutex.
    map_state(ce)
    auto = ce.module.newAutomatic(ce.api)
    assert auto.start(1.5)
    for _ in range(8):
        ce.now += 60000
        auto.tick()
    assert rates(ce) == []
    assert ce.speed_mutex_owned and not ce.mutex_owned
    assert auto.running and auto.phase == "waiting_battle"
    assert auto.restore("Parada manual")
    assert not ce.speed_mutex_owned and rates(ce) == []


def test_automatic_repeats_after_verified_map_even_with_recycled_battle_token():
    ce = FakeCE()
    auto = active_auto(ce)
    for _ in range(2):
        ce.now += 5000
        map_state(ce)
        auto.tick()
        assert auto.lastRestoration.cause == "battle_exit" and auto.running
        assert ce.speed_mutex_owned  # Keep the speed controller exclusive.
        battle_state(ce)  # The same addresses/identity are deliberately reused.
        auto.tick()
        ce.now += 200
        auto.tick()
        assert auto.phase == "active"
    assert rates(ce) == [3, 1, 3, 1, 3]
    assert auto.close()
    assert rates(ce) == [3, 1, 3, 1, 3, 1]
    assert not ce.speed_mutex_owned


def test_graphics_precaution_does_not_reapply_in_the_same_battle():
    ce = FakeCE()
    auto = active_auto(ce)
    ce.memory[0x1539CE18] = 0
    auto.tick()
    assert auto.lastRestoration.cause == "graphics_context_changed"
    battle_state(ce)
    for _ in range(10):
        ce.now += 1000
        auto.tick()
    assert rates(ce) == [3, 1] and auto.phase == "waiting_map"
    map_state(ce)
    auto.tick()
    battle_state(ce)
    auto.tick()
    ce.now += 200
    auto.tick()
    assert rates(ce) == [3, 1, 3]
    assert auto.close()


def test_battle_time_cap_waits_for_map_before_another_apply():
    ce = FakeCE()
    auto = active_auto(ce)
    ce.now += 60000
    auto.tick()
    assert auto.lastRestoration.cause == "time_limit"
    ce.now += 180000
    auto.tick()
    assert auto.running and rates(ce) == [3, 1] and auto.phase == "waiting_map"
    assert auto.close()


def test_stopping_automatic_during_apply_is_serialized_and_restores_once():
    ce = FakeCE()
    auto = ce.module.newAutomatic(ce.api)

    def nested_stop():
        assert not auto.restore("Parada manual")
        auto.tick()
        assert rates(ce) == [3]

    ce.apply_callback = nested_stop
    assert auto.start(3)
    auto.tick()
    ce.now += 200
    auto.tick()
    assert rates(ce) == [3, 1]
    assert not auto.running and auto.binding is None and not ce.speed_mutex_owned


def test_restore_failure_retains_speed_lease_without_automatic_retry():
    ce = FakeCE()
    auto = active_auto(ce)
    ce.fail_restore = True
    map_state(ce)
    auto.tick()
    assert auto.phase == "restore_failed" and not auto.running
    assert ce.speed_mutex_owned and auto.binding is not None
    for _ in range(3):
        auto.tick()
    assert rates(ce) == [3, 1]
    ce.fail_restore = False
    assert auto.restore("Restaurar de nuevo")
    assert rates(ce) == [3, 1, 1] and not ce.speed_mutex_owned


def test_pending_manual_stop_does_not_retry_a_failed_restore_automatically():
    ce = FakeCE()
    auto = ce.module.newAutomatic(ce.api)

    def nested_stop():
        ce.fail_restore = True
        assert not auto.restore("Parada manual")

    ce.apply_callback = nested_stop
    assert auto.start(3)
    auto.tick()
    ce.now += 200
    auto.tick()
    assert rates(ce) == [3, 1]
    assert auto.phase == "restore_failed" and ce.speed_mutex_owned
    ce.fail_restore = False
    assert auto.restore("Restaurar")
    assert rates(ce) == [3, 1, 1]


def test_unknown_read_during_battle_restores_then_disables_automatic():
    ce = FakeCE()
    auto = active_auto(ce)
    ce.memory[0x1539CE18] = 2
    auto.tick()
    assert rates(ce) == [3, 1]
    assert not auto.running and auto.binding is None and not ce.speed_mutex_owned


def test_changed_character_while_waiting_stops_without_a_speed_command():
    ce = FakeCE()
    map_state(ce)
    auto = ce.module.newAutomatic(ce.api)
    assert auto.start(3)
    ce.memory[ce.actor + 0x204] += 1
    auto.tick()
    assert not auto.running and rates(ce) == [] and not ce.speed_mutex_owned


def test_changed_ce_process_is_returned_only_for_cleanup_then_automatic_stops():
    ce = FakeCE()
    auto = active_auto(ce)
    ce.open_process(456)
    auto.tick()
    assert not auto.running and rates(ce) == [3, 1]
    assert [pid for pid, _, _ in ce.rate_calls] == [123, 123]


def test_changed_ce_process_while_on_map_does_not_receive_a_reset_command():
    ce = FakeCE()
    map_state(ce)
    auto = ce.module.newAutomatic(ce.api)
    assert auto.start(3)
    ce.open_process(456)
    auto.tick()
    assert not auto.running and rates(ce) == [] and ce.pid == 456
    assert not ce.speed_mutex_owned


def test_dead_original_does_not_reset_other_instance():
    ce = FakeCE()
    auto = active_auto(ce)
    ce.alive.remove(123)
    ce.open_process(456)
    auto.tick()
    assert not auto.running and rates(ce) == [3] and ce.pid == 456
    assert not ce.speed_mutex_owned


def test_existing_speed_controller_blocks_auto_even_if_bot_is_free():
    ce = FakeCE()
    ce.speed_available = False
    auto = ce.module.newAutomatic(ce.api)
    assert not auto.start(3)
    assert rates(ce) == [] and not ce.mutex_owned and not ce.speed_mutex_owned


def test_preexisting_foreign_speed_is_not_overwritten():
    ce = FakeCE()
    ce.rate = 2
    auto = ce.module.newAutomatic(ce.api)
    assert not auto.start(3)
    assert ce.rate == 2 and rates(ce) == [] and not ce.speed_mutex_owned


def test_gui_automatic_mode_runs_with_bot_and_stop_releases_speed():
    ce = FakeCE()
    ce.lease_available = False
    map_state(ce)

    def on_show(form, widgets):
        modes = next(w for w in widgets if w.Name == "TrialMode")
        modes.ItemIndex = 2
        modes.OnChange()
        start = next(w for w in widgets if w.Caption == "Activar en cada combate")
        stop = next(w for w in widgets if w.Caption == "Restaurar 1× / parar")
        timer = next(w for w in widgets if w.OnTimer is not None)
        start.OnClick()
        auto = ce.lua.globals().AtlanticaTimerTrial.trial
        assert auto.automatic and auto.running and start.Enabled is False
        assert ce.speed_mutex_owned and not ce.mutex_owned
        battle_state(ce)
        timer.OnTimer()
        ce.now += 200
        timer.OnTimer()
        assert rates(ce) == [1.25]
        map_state(ce)
        timer.OnTimer()
        assert rates(ce) == [1.25, 1] and auto.running
        stop.OnClick()
        assert not ce.speed_mutex_owned and start.Enabled is True
        assert form.OnClose() == 1

    forms = install_fake_gui(ce, on_show)
    ce.module.open()
    assert forms[0].destroyed
