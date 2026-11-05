from __future__ import annotations

import hashlib
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from lupa.lua53 import LuaError, LuaRuntime

from atlantica_bot import __version__
from atlantica_bot.battle_context import CONTEXT_ANCHOR

SOURCE = Path(__file__).resolve().parents[1] / "tools/cheat_engine/atlantica_speed_trial.lua"
package = runpy.run_path(str(SOURCE.parents[1] / "package_ce_speed.py"))["package"]


@pytest.fixture
def controller():
    lua = LuaRuntime(unpack_returned_tuples=True)
    module = lua.execute(SOURCE.read_text(encoding="utf-8"))
    state = SimpleNamespace(
        now=0,
        rate=1,
        battle="battle:1",
        selected=123,
        alive=True,
        observation_error=None,
        fail_apply=False,
        fail_restore=False,
        apply_duration=0,
        apply_callback=None,
        observe_callback=None,
        calls=[],
        releases=0,
    )
    binding = lua.table_from({"pid": 123, "created": "0123456789ABCDEF"})

    def observe(_binding):
        if state.observe_callback:
            state.observe_callback()
        if state.observation_error:
            raise RuntimeError(state.observation_error)
        return state.battle

    def set_rate(_binding, rate):
        state.calls.append((state.selected, rate))
        if rate == 1 and state.fail_restore:
            raise RuntimeError("restore unavailable")
        state.rate = rate
        if rate != 1:
            state.now += state.apply_duration
            if state.apply_callback:
                state.apply_callback()
        if rate != 1 and state.fail_apply:
            raise RuntimeError("apply result unknown")

    def release(_binding):
        state.releases += 1

    def return_to_original(_binding):
        if not state.alive:
            return False
        state.selected = 123
        return True

    api = lua.table_from(
        {
            "now": lambda: state.now,
            "bind": lambda: binding,
            "observe": observe,
            "release": release,
            "reportedRate": lambda: state.rate,
            "returnToOriginal": return_to_original,
            "setRate": set_rate,
        }
    )
    return module.newTrial(api), state


def activate(trial, state, rate=1.25):
    assert trial.start(rate)
    assert state.calls == []
    state.now = 199
    trial.tick()
    assert state.calls == []
    state.now = 200
    trial.tick()
    assert trial.phase == "active"
    assert state.calls == [(123, rate)]


def test_ten_seconds_uses_host_clock_and_restores_once(controller):
    trial, state = controller
    assert state.calls == []  # Loading/constructing the trial does not set a rate.
    activate(trial, state, 4)
    state.now = 10199
    trial.tick()
    assert trial.phase == "active"
    state.now = 10200
    trial.tick()
    assert state.calls == [(123, 4), (123, 1)]
    assert trial.phase == "idle" and trial.binding is None
    assert state.releases == 1
    assert "CE informa 1×" in trial.message
    trial.tick()
    assert len(state.calls) == 2


@pytest.mark.parametrize("rate", [1.25, 1.5, 2, 3, 4])
def test_supported_factors_require_explicit_start(controller, rate):
    trial, state = controller
    activate(trial, state, rate)
    assert trial.restore("manual")
    state.now += 10000
    trial.tick()
    assert state.calls == [(123, rate), (123, 1)]


@pytest.mark.parametrize("rate", [0, 1, 1.4, 4.1, float("nan"), float("inf"), "2"])
def test_rejects_unlisted_factors_without_binding(controller, rate):
    trial, state = controller
    with pytest.raises(LuaError, match="velocidades de prueba"):
        trial.start(rate)
    assert trial.binding is None and state.calls == []


def test_refuses_existing_speed_without_resetting_it(controller):
    trial, state = controller
    state.rate = 2
    assert not trial.start(1.25)
    assert trial.phase == "idle" and state.releases == 1
    assert state.calls == [] and state.rate == 2


def test_map_or_unknown_state_before_apply_releases_without_changing_speed(controller):
    trial, state = controller
    assert trial.start(1.5)
    state.observation_error = "not in battle"
    state.now = 200
    trial.tick()
    assert trial.phase == "idle"
    assert state.calls == [] and state.releases == 1


@pytest.mark.parametrize("changed", ["map", "unreadable", "different battle"])
def test_map_unknown_or_different_battle_restores(controller, changed):
    trial, state = controller
    activate(trial, state)
    if changed == "different battle":
        state.battle = "battle:2"
    else:
        state.observation_error = changed
    trial.tick()
    assert trial.phase == "idle"
    assert state.calls == [(123, 1.25), (123, 1)]


def test_apply_failure_keeps_ownership_until_cleanup(controller):
    trial, state = controller
    state.fail_apply = True
    assert trial.start(2)
    state.now = 200
    trial.tick()
    assert state.calls == [(123, 2), (123, 1)]
    assert trial.phase == "idle" and not trial.ownsChange


def test_restore_failure_keeps_lease_and_close_blocked_without_automatic_retries(controller):
    trial, state = controller
    activate(trial, state)
    state.fail_restore = True
    assert not trial.restore("manual")
    assert trial.phase == "restore_failed" and trial.ownsChange
    assert trial.binding is not None and state.releases == 0
    trial.tick()
    assert len(state.calls) == 2
    with pytest.raises(LuaError, match="prueba anterior"):
        trial.start(2)
    assert not trial.close()
    assert state.releases == 0
    state.fail_restore = False
    assert trial.restore("retry")
    assert state.releases == 1 and trial.binding is None


def test_dead_original_retires_without_changing_new_target(controller):
    trial, state = controller
    activate(trial, state)
    state.alive, state.selected = False, 456
    assert trial.restore("exit")
    assert state.calls == [(123, 1.25)]
    assert state.selected == 456 and state.releases == 1


def test_slow_initialization_requests_restore_before_returning_to_ui(controller):
    trial, state = controller
    state.apply_duration = 12000
    assert trial.start(1.5)
    state.now = 200
    trial.tick()
    assert state.calls == [(123, 1.5), (123, 1)]
    assert trial.phase == "idle"


def test_nested_timer_during_ce_initialization_does_not_apply_twice(controller):
    trial, state = controller
    state.apply_callback = trial.tick
    activate(trial, state)
    assert state.calls == [(123, 1.25)]


def test_nested_close_during_initialization_defers_restore_until_request_returns(controller):
    trial, state = controller

    def nested_close():
        assert not trial.close()
        trial.tick()
        assert state.calls == [(123, 1.25)]

    state.apply_callback = nested_close
    assert trial.start(1.25)
    state.now = 200
    trial.tick()
    assert state.calls == [(123, 1.25), (123, 1)]
    assert trial.phase == "idle" and state.releases == 1


def test_battle_end_mode_waits_past_ten_seconds_then_restores_on_map(controller):
    trial, state = controller
    assert trial.start(1.5, "battle_end")
    state.now = 200
    trial.tick()
    state.now = 25000
    trial.tick()
    assert state.calls == [(123, 1.5)] and trial.phase == "active"
    state.battle = "__map__"
    state.now = 26000
    trial.tick()
    assert state.calls == [(123, 1.5), (123, 1)]
    assert trial.lastRestoration.cause == "battle_exit"
    assert trial.lastRestoration.seconds == pytest.approx(25.8)
    assert "Salida del combate detectada" in trial.message


def test_battle_end_mode_has_sixty_second_cap_without_claiming_battle_exit(controller):
    trial, state = controller
    assert trial.start(1.25, "battle_end")
    state.now = 200
    trial.tick()
    state.now = 60199
    trial.tick()
    assert trial.phase == "active"
    state.now = 60200
    trial.tick()
    assert state.calls == [(123, 1.25), (123, 1)]
    assert trial.lastRestoration.cause == "time_limit"
    assert "sin confirmar salida del combate" in trial.message


def test_timed_mode_can_detect_map_before_deadline(controller):
    trial, state = controller
    activate(trial, state)
    state.battle = "__map__"
    state.now = 3000
    trial.tick()
    assert trial.lastRestoration.cause == "battle_exit"
    assert state.calls[-1] == (123, 1)


def test_cannot_start_speed_from_map(controller):
    trial, state = controller
    state.battle = "__map__"
    assert not trial.start(1.5, "battle_end")
    assert state.calls == [] and state.releases == 1
    assert "Entra en un combate" in trial.message


def test_rejects_unknown_mode_without_binding(controller):
    trial, state = controller
    with pytest.raises(LuaError, match="modo de prueba"):
        trial.start(1.5, "forever")
    assert trial.binding is None and state.calls == []


def test_read_error_does_not_count_as_battle_exit(controller):
    trial, state = controller
    activate(trial, state)
    state.observation_error = "read failed"
    trial.tick()
    assert state.calls[-1] == (123, 1)
    assert trial.lastRestoration.cause == "observation_or_context_changed"


def test_manual_request_received_during_read_takes_priority_over_deadline(controller):
    trial, state = controller
    activate(trial, state)

    def stop_during_read():
        assert not trial.restore("Parada manual")
        state.now = 10201

    state.now = 10000
    state.observe_callback = stop_during_read
    trial.tick()
    assert state.calls == [(123, 1.25), (123, 1)]
    assert trial.lastRestoration.cause == "manual"
    history = "\n".join(trial.history.values())
    assert "recibida a 9.80 s" in history
    assert "Plazo de 10 s cumplido" not in history


def test_later_restore_button_preserves_original_cause_and_stopped_elapsed(controller):
    trial, state = controller
    activate(trial, state)
    state.now = 10200
    trial.tick()
    assert trial.lastRestoration.cause == "time_limit"
    state.now = 20000
    assert trial.restore("Parada manual")
    assert trial.lastRestoration.cause == "time_limit" and trial.elapsed() == 10
    assert "Última causa: Plazo de 10 s cumplido" in trial.message
    assert "recibida a 19.80 s" in "\n".join(trial.history.values())


def test_manual_request_during_post_apply_read_is_not_attributed_to_map_exit(controller):
    trial, state = controller
    assert trial.start(1.25, "battle_end")
    reads = 0

    def stop_during_post_apply_read():
        nonlocal reads
        reads += 1
        if reads == 2:
            assert not trial.restore("Parada manual")
            state.battle = "__map__"

    state.observe_callback = stop_during_post_apply_read
    state.now = 200
    trial.tick()
    assert trial.lastRestoration.cause == "manual"
    assert state.calls == [(123, 1.25), (123, 1)]


def test_graphics_context_change_restores_without_claiming_battle_exit(controller):
    trial, state = controller
    activate(trial, state, 3)
    state.battle = "__graphics_other__"
    trial.tick()
    assert state.calls == [(123, 3), (123, 1)]
    assert trial.lastRestoration.cause == "graphics_context_changed"
    assert "vuelta preventiva" in trial.message


def test_rejected_graphics_attempt_keeps_last_verified_exit(controller):
    trial, state = controller
    assert trial.start(3, "battle_end")
    state.now = 200
    trial.tick()
    state.now, state.battle = 6890, "__map__"
    trial.tick()
    assert trial.lastRestoration.cause == "battle_exit"
    state.now, state.battle = 9000, "__graphics_other__"
    assert not trial.start(3)
    assert trial.lastRestoration.cause == "battle_exit"
    assert trial.elapsed() == pytest.approx(6.69)
    assert trial.mode == "battle_end" and trial.duration == 60
    assert "Última causa: Salida del combate detectada" in trial.message
    assert state.calls == [(123, 3), (123, 1)] and state.releases == 2


class FakeCE:
    """Mock the documented CE/Win32 boundary; never open a real process."""

    def __init__(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.pid, self.ce_handle = 123, 0x100
        self.created = 134383363734202228
        self.handles = {self.ce_handle: (self.pid, self.created)}
        self.next_handle = 0x900
        self.alive = {self.pid}
        self.local, self.calls, self.rate_calls = {}, [], []
        self.lease_available = True
        self.speed_available = True
        self.mutex_owned = False
        self.speed_mutex_owned = False
        self.rate = 1
        self.now = 0
        self.apply_callback = None
        self.fail_restore = False
        self.marker = False
        self.disk_hash = "a5267787d5dc3f1699a3500d04129020"
        self.anchor = CONTEXT_ANCHOR
        self.owner, self.world, self.actor = 0x100000, 0x200000, 0x300000
        self.manager, self.context = 0x400000, 0x500000
        self.memory = {
            0x04A9290C: self.owner,
            self.owner + 0xB98: 2,
            self.owner + 0x16394: 0,
            0x04E52C5A: 0,
            self.owner + 0x828: self.world,
            self.world + 0x2C: self.actor,
            self.actor + 0x200: 1,
            self.actor + 0x2C: self.world,
            self.actor + 0x318: 0,
            self.actor + 0x254: 0xFFFFFFFF,
            self.owner + 0x91C: self.manager,
            self.manager: 0x042D8AA4,
            self.manager + 0x234C: 3,
            self.manager + 8: self.context,
            self.context + 0x6C74: 1,
            0x1539CE18: 1,
            self.actor + 0x204: 100,
            self.actor + 0x208: 200,
            self.actor + 0x20C: 0,
        }
        self.symbols = {
            name: 0x1000 + i
            for i, name in enumerate(
                (
                    "OpenProcess",
                    "GetProcessTimes",
                    "GetProcessId",
                    "WaitForSingleObject",
                    "CloseHandle",
                    "CreateMutexW",
                    "ReleaseMutex",
                )
            )
        }
        self.apis = {value: name for name, value in self.symbols.items()}
        functions = {
            "cheatEngineIs64Bit": lambda: True,
            "targetIs64Bit": lambda: False,
            "createMemoryStream": lambda: self.lua.table_from(
                {"Memory": 0x100000000, "destroy": lambda: None}
            ),
            "getAddress": self.address,
            "executeCodeLocalEx": self.win,
            "readIntegerLocal": lambda address: self.local[address],
            "getOpenedProcessID": lambda: self.pid,
            "getOpenedProcessHandle": lambda: self.ce_handle,
            "enumModules": lambda pid: self.lua.table_from(
                [
                    self.lua.table_from(
                        {
                            "Name": "Atlantica.exe",
                            "Address": 0x400000,
                            "Is64Bit": False,
                            "PathToFile": "C:\\Atlantica\\Atlantica.exe",
                        }
                    )
                ]
            ),
            "md5file": lambda path: self.disk_hash,
            "readBytes": self.read_bytes,
            "readInteger": lambda address: self.memory[address],
            "fileExists": lambda path: self.marker,
            "getTickCount": lambda: self.now,
            "speedhack_getSpeed": lambda: self.rate,
            "speedhack_setSpeed": self.set_rate,
            "openProcess": self.open_process,
        }
        for name, function in functions.items():
            self.lua.globals()[name] = function
        self.module = self.lua.execute(SOURCE.read_text(encoding="utf-8"))
        self.api = self.module.newCEAdapter()

    def address(self, symbol, local):
        assert local is True
        return self.symbols[symbol.removeprefix("kernel32.")]

    def win(self, address, *args):
        name = self.apis[address]
        self.calls.append((name, args))
        if name == "OpenProcess":
            assert args[0:2] == (0x101000, 0)
            self.next_handle += 1
            self.handles[self.next_handle] = (args[2], self.created)
            return self.next_handle
        if name == "GetProcessTimes":
            _, created = self.handles[args[0]]
            self.local[args[1]] = created & 0xFFFFFFFF
            self.local[args[1] + 4] = created >> 32
            return 1
        if name == "GetProcessId":
            return self.handles[args[0]][0]
        if name == "WaitForSingleObject":
            if args[0] == 0xAAB:
                return 0 if self.speed_available else 0x102
            if args[0] == 0xAAA:
                return 0 if self.lease_available else 0x102
            return 0x102 if self.handles[args[0]][0] in self.alive else 0
        if name == "CreateMutexW":
            assert args[2]["type"] == 4
            if args[2]["value"] == f"Local\\AtlanticaPanel.Speed.{self.pid}":
                self.speed_mutex_owned = self.speed_available
                return 0xAAB
            assert args[2]["value"] == f"Local\\AtlanticaPanel.Bot.{self.pid}"
            self.mutex_owned = self.lease_available
            return 0xAAA
        if name == "ReleaseMutex":
            if args[0] == 0xAAB:
                self.speed_mutex_owned = False
                return 1
            self.mutex_owned = False
            return 1
        if name == "CloseHandle":
            self.handles.pop(args[0], None)
            return 1
        raise AssertionError(name)

    def read_bytes(self, address, count, as_table=False):
        if address == 0x00431769:
            assert as_table
            return self.lua.table_from(list(self.anchor[:count]))
        assert count == 1 and not as_table
        return self.memory[address]

    def set_rate(self, rate):
        self.rate_calls.append((self.pid, self.handles[self.ce_handle][1], rate))
        if rate == 1 and self.fail_restore:
            raise RuntimeError("restore unavailable")
        self.rate = rate
        if rate != 1 and self.apply_callback:
            self.apply_callback()

    def open_process(self, pid):
        self.pid = pid
        self.ce_handle += 1
        self.handles[self.ce_handle] = (pid, self.created)
        return True


def test_ce_refuses_to_layer_speed_over_native_panel_hooks():
    ce = FakeCE()
    ce.memory[0x800080] = 1
    ce.lua.execute(
        "function getAddressSafe(name) "
        'assert(name == "AtlanticaHook.AtlanticaClockHooksInstalled"); return 0x800080 end'
    )
    with pytest.raises(LuaError, match="relojes del panel"):
        ce.api.bind()
    assert ce.rate_calls == [] and not ce.mutex_owned
    assert all(handle < 0x900 for handle in ce.handles)


def test_adapter_only_local_api_until_explicit_rate_request():
    ce = FakeCE()
    b = ce.api.bind()
    assert b.created == f"{ce.created:016X}"
    assert ce.api.observe(b)
    assert ce.mutex_owned and ce.rate_calls == []
    ce.api.setRate(b, 1.25)
    assert ce.rate_calls == [(123, ce.created, 1.25)]
    ce.api.release(b)
    assert not ce.mutex_owned


@pytest.mark.parametrize("problem", ["hash", "anchor", "bot", "pid"])
def test_adapter_rejects_wrong_build_or_busy_pid_and_releases_resources(problem):
    ce = FakeCE()
    if problem == "hash":
        ce.disk_hash = "0" * 32
    elif problem == "anchor":
        ce.anchor = b"\xcc" * len(CONTEXT_ANCHOR)
    elif problem == "bot":
        ce.lease_available = False
    else:
        ce.handles[ce.ce_handle] = (456, ce.created)
    with pytest.raises(LuaError):
        ce.api.bind()
    assert ce.rate_calls == []
    assert not ce.mutex_owned
    assert all(handle < 0x900 for handle in ce.handles)


@pytest.mark.parametrize("problem", ["context", "manager", "auto", "hunting", "marker", "instance"])
def test_adapter_gates_battle_and_native_modes(problem):
    ce = FakeCE()
    b = ce.api.bind()
    if problem == "context":
        ce.memory[ce.actor + 0x318] = 0xFFFFFFFF
        ce.memory[ce.actor + 0x254] = 0
    elif problem == "manager":
        ce.memory[ce.manager] = 0
    elif problem == "auto":
        ce.memory[ce.owner + 0x16394] = 1
    elif problem == "hunting":
        ce.memory[0x04E52C5A] = 1
    elif problem == "marker":
        ce.marker = True
    else:
        ce.handles[ce.ce_handle] = (ce.pid, ce.created + 1)
    with pytest.raises(LuaError):
        ce.api.observe(b)
    assert ce.rate_calls == []
    ce.api.release(b)


def test_adapter_recognizes_map_without_following_retired_battle_manager():
    ce = FakeCE()
    b = ce.api.bind()
    ce.memory[ce.actor + 0x318] = 0xFFFFFFFF
    ce.memory[0x1539CE18] = 0
    del ce.memory[ce.owner + 0x91C]
    token, detail = ce.api.observe(b)
    assert token == ce.module.MAP
    assert (detail.context_a, detail.context_b, detail.graphics_context_index) == (-1, -1, 0)
    with pytest.raises(LuaError, match="ya volvió al mapa"):
        ce.api.setRate(b, 1.25)
    assert ce.rate_calls == []
    ce.api.release(b)


def test_adapter_rejects_mixed_map_battle_read_as_unconfirmed():
    ce = FakeCE()
    b = ce.api.bind()
    count = 0

    def changing_read(address):
        nonlocal count
        value = ce.memory[address]
        if address == ce.actor + 0x318:
            count += 1
            if count == 1:
                ce.memory[address] = 0xFFFFFFFF
        return value

    ce.lua.globals().readInteger = changing_read
    with pytest.raises(LuaError, match="cambiaron durante la lectura"):
        ce.api.observe(b)
    assert ce.api.lastObservation.classification == "unknown"
    assert ce.rate_calls == []
    ce.api.release(b)


def test_adapter_recognizes_graphics_change_without_calling_it_map():
    ce = FakeCE()
    b = ce.api.bind()
    ce.memory[0x1539CE18] = 0
    token, detail = ce.api.observe(b)
    assert token == ce.module.GRAPHICS_OTHER
    assert (detail.classification, detail.context_a, detail.battle_phase) == (
        "graphics_other",
        0,
        3,
    )
    with pytest.raises(LuaError, match="contexto gráfico cambió"):
        ce.api.setRate(b, 3)
    assert ce.rate_calls == []
    ce.api.setRate(b, 1)
    assert ce.rate_calls == [(123, ce.created, 1)]
    ce.api.release(b)


@pytest.mark.parametrize("local_index", [0, 0xFFFFFFFF])
def test_unknown_graphics_value_remains_unconfirmed(local_index):
    ce = FakeCE()
    b = ce.api.bind()
    ce.memory[ce.actor + 0x318] = local_index
    ce.memory[0x1539CE18] = 2
    with pytest.raises(LuaError, match="valor reconocido"):
        ce.api.observe(b)
    assert ce.api.lastObservation.classification == "unknown"
    assert ce.rate_calls == []
    ce.api.release(b)


def test_adapter_rejects_graphics_switch_between_snapshots():
    ce = FakeCE()
    b = ce.api.bind()
    ce.memory[0x1539CE18] = 0

    def changing_read(address):
        value = ce.memory[address]
        if address == 0x1539CE18:
            ce.memory[address] = 1
        return value

    ce.lua.globals().readInteger = changing_read
    with pytest.raises(LuaError, match="cambiaron durante la lectura"):
        ce.api.observe(b)
    assert ce.api.lastObservation.classification == "unknown"
    assert ce.rate_calls == []
    ce.api.release(b)


def test_adapter_rejects_a_turn_becoming_ready_between_the_two_snapshots():
    ce = FakeCE()
    b = ce.api.bind()
    ce.memory[ce.context + 0x6C74] = 0xFFFFFFFF

    def changing_read(address):
        value = ce.memory[address]
        if address == ce.context + 0x6C74:
            ce.memory[address] = 1
        return value

    ce.lua.globals().readInteger = changing_read
    with pytest.raises(LuaError, match="cambiaron durante la lectura"):
        ce.api.observe(b)
    assert ce.api.lastObservation.classification == "unknown" and ce.rate_calls == []
    ce.api.release(b)


def test_replays_two_graphics_restorations_and_final_verified_map_exit():
    """Replay the reported field combinations through fake CE, not a game process."""
    ce = FakeCE()
    trial = ce.module.newTrial(ce.api)
    causes = []
    for index, duration_ms in enumerate((13080, 1420, 6690)):
        ce.memory[ce.actor + 0x318], ce.memory[0x1539CE18] = 0, 1
        assert trial.start(3, "battle_end")
        ce.now += 250
        trial.tick()
        assert trial.phase == "active"
        ce.now += duration_ms
        ce.memory[0x1539CE18] = 0
        if index == 2:
            ce.memory[ce.actor + 0x318] = 0xFFFFFFFF
        trial.tick()
        causes.append(trial.lastRestoration.cause)
        assert not ce.mutex_owned
    assert causes == ["graphics_context_changed", "graphics_context_changed", "battle_exit"]
    assert ce.rate_calls == [(123, ce.created, rate) for _ in range(3) for rate in (3, 1)]


def test_adapter_reattaches_only_live_original_for_restore():
    ce = FakeCE()
    b = ce.api.bind()
    ce.api.setRate(b, 1.5)
    ce.open_process(456)
    with pytest.raises(LuaError, match="cambió de PID"):
        ce.api.setRate(b, 1)
    assert ce.api.returnToOriginal(b)
    ce.api.setRate(b, 1)
    assert [item[0] for item in ce.rate_calls] == [123, 123]
    assert ce.rate_calls[-1] == (123, ce.created, 1)
    ce.api.release(b)


def test_adapter_will_not_restore_to_recycled_pid():
    ce = FakeCE()
    b = ce.api.bind()
    ce.api.setRate(b, 1.5)
    ce.open_process(456)
    ce.alive.remove(123)
    ce.created += 1
    assert not ce.api.returnToOriginal(b)
    assert ce.pid == 456 and len(ce.rate_calls) == 1
    ce.api.release(b)


def test_adapter_can_restore_after_ce_loses_its_handle():
    ce = FakeCE()
    b = ce.api.bind()
    ce.api.setRate(b, 1.5)
    ce.ce_handle = 0
    assert ce.api.returnToOriginal(b)
    ce.api.setRate(b, 1)
    assert ce.rate_calls[-1] == (123, ce.created, 1)
    ce.api.release(b)


def install_fake_gui(ce, on_show):
    widgets, forms = [], []

    def widget(*_args):
        control = ce.lua.table_from(
            {
                "Lines": ce.lua.table_from({"Text": ""}),
                "Items": ce.lua.table_from({"add": lambda text: None}),
            }
        )
        widgets.append(control)
        return control

    def form(*_args):
        control = widget()
        control.destroyed, control.raised = False, False

        def destroy():
            control.destroyed = True

        def raise_form():
            control.raised = True

        control.destroy, control.bringToFront = destroy, raise_form
        control.showModal = lambda: on_show(control, widgets)
        forms.append(control)
        return control

    for name in ("createLabel", "createComboBox", "createButton", "createMemo", "createTimer"):
        ce.lua.globals()[name] = widget
    ce.lua.globals().createForm = form
    ce.lua.globals().caNone, ce.lua.globals().caHide = 0, 1
    ce.lua.globals().caFree = 2
    return forms


def test_gui_open_does_not_change_rate_and_duplicate_open_keeps_original():
    ce = FakeCE()

    def on_show(form, widgets):
        assert ce.rate_calls == []
        ce.module.open()
        assert form.raised
        assert form.OnClose() == 1

    forms = install_fake_gui(ce, on_show)
    ce.module.open()
    assert len(forms) == 1 and forms[0].destroyed
    assert ce.lua.globals().AtlanticaTimerTrial is None
    assert ce.rate_calls == []


def test_gui_buttons_timer_and_normal_close_release_trial():
    ce = FakeCE()

    def on_show(form, widgets):
        start = next(w for w in widgets if w.Caption == "Probar 10 segundos")
        timer = next(w for w in widgets if w.OnTimer is not None)
        start.OnClick()
        assert ce.rate_calls == [] and ce.mutex_owned
        ce.now = 200
        timer.OnTimer()
        assert ce.rate_calls[-1] == (123, ce.created, 1.25)
        assert start.Enabled is False
        assert form.OnClose() == 1
        assert ce.rate_calls[-1] == (123, ce.created, 1)
        assert not ce.mutex_owned

    forms = install_fake_gui(ce, on_show)
    ce.module.open()
    assert forms[0].destroyed


def test_gui_battle_end_mode_map_exit_and_copy_button():
    ce = FakeCE()
    copied = []
    ce.lua.globals().writeToClipboard = copied.append

    def on_show(form, widgets):
        modes = next(w for w in widgets if w.Name == "TrialMode")
        modes.ItemIndex = 1
        modes.OnChange()
        start = next(w for w in widgets if w.Caption == "Probar hasta salir del combate")
        copy = next(w for w in widgets if w.Caption == "Copiar registro")
        timer = next(w for w in widgets if w.OnTimer is not None)
        start.OnClick()
        ce.now = 200
        timer.OnTimer()
        ce.now = 15000
        timer.OnTimer()
        assert len(ce.rate_calls) == 1 and modes.Enabled is False
        ce.memory[ce.actor + 0x318] = 0xFFFFFFFF
        ce.memory[0x1539CE18] = 0
        timer.OnTimer()
        trial = ce.lua.globals().AtlanticaTimerTrial.trial
        assert trial.lastRestoration.cause == "battle_exit"
        assert ce.rate_calls[-1] == (123, ce.created, 1)
        copy.OnClick()
        assert copied[0].startswith(f"Atlantica — prueba CE {__version__}")
        assert "modo=battle_end" in copied[0]
        assert "contextos=-1/-1" in copied[0]
        assert "Salida del combate detectada" in copied[0]
        assert not ce.mutex_owned
        assert form.OnClose() == 1

    forms = install_fake_gui(ce, on_show)
    ce.module.open()
    assert forms[0].destroyed


def test_gui_close_failure_retains_form_until_manual_restore():
    ce = FakeCE()

    def on_show(form, widgets):
        start = next(w for w in widgets if w.Caption == "Probar 10 segundos")
        stop = next(w for w in widgets if w.Caption == "Restaurar 1× / parar")
        timer = next(w for w in widgets if w.OnTimer is not None)
        start.OnClick()
        ce.now = 200
        timer.OnTimer()
        ce.lua.globals().speedhack_setSpeed = lambda rate: None
        # api.setRate resolves the global each time. Keeping the reported rate
        # unchanged simulates a failed restoration, rather than an acknowledged 1x.
        assert form.OnClose() == 0
        assert ce.mutex_owned and not form.destroyed
        assert start.Enabled is False
        ce.lua.globals().speedhack_setSpeed = ce.set_rate
        stop.OnClick()
        assert not ce.mutex_owned and start.Enabled is True
        assert form.OnClose() == 1

    forms = install_fake_gui(ce, on_show)
    ce.module.open()
    assert forms[0].destroyed


def test_interrupted_modal_keeps_restore_accessible_and_eventually_frees_resources():
    ce = FakeCE()
    controls = {}

    def on_show(form, widgets):
        start = next(w for w in widgets if w.Caption == "Probar 10 segundos")
        controls["stop"] = next(w for w in widgets if w.Caption == "Restaurar 1× / parar")
        controls["timer"] = next(w for w in widgets if w.OnTimer is not None)
        form.show = lambda: None
        start.OnClick()
        ce.now = 200
        controls["timer"].OnTimer()
        ce.lua.globals().speedhack_setSpeed = lambda rate: None
        raise RuntimeError("modal interrupted")

    forms = install_fake_gui(ce, on_show)
    ce.module.open()
    assert ce.mutex_owned and not forms[0].destroyed
    assert ce.lua.globals().AtlanticaTimerTrial is not None
    ce.lua.globals().speedhack_setSpeed = ce.set_rate
    controls["stop"].OnClick()
    assert forms[0].OnClose() == 2  # CE frees the form for caFree.
    assert not ce.mutex_owned and not controls["timer"].Enabled
    assert ce.lua.globals().AtlanticaTimerTrial is None


def test_package_contains_exact_tested_lua_and_valid_checksums(tmp_path):
    files = package(tmp_path)
    embedded = ET.parse(files[0]).getroot().findtext("LuaScript")
    assert embedded == SOURCE.read_text(encoding="utf-8")
    assert files[1].read_text(encoding="utf-8") == embedded
    assert f'version = "{__version__}"' in embedded
    for line in files[-1].read_text(encoding="ascii").splitlines():
        checksum, name = line.split("  ")
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == checksum
