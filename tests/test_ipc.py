import ctypes
import os
import sys
import threading

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.ipc import BotLease, Cancellation, SpeedLease
from atlantica_bot.windows import DWORD, HANDLE, _bind


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita sincronización real de Windows.")
def test_own_pid_lease_is_recursive_but_blocks_a_second_controller_thread():
    blocked = []

    def second_controller():
        try:
            with BotLease(os.getpid()):
                blocked.append(False)
        except DiagnosticError:
            blocked.append(True)

    with BotLease(os.getpid()), BotLease(os.getpid()):
        thread = threading.Thread(target=second_controller)
        thread.start()
        thread.join(2)
        assert not thread.is_alive() and blocked == [True]
    with BotLease(os.getpid()):
        pass


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita eventos reales de Windows.")
def test_cancelled_run_cannot_cancel_a_later_run_after_its_handle_closes():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    wait = _bind(kernel, "WaitForSingleObject", [HANDLE, DWORD], DWORD)
    old = Cancellation(os.getpid())
    try:
        assert wait(old._handle, 0) == 258
        old.cancel()
        assert wait(old._handle, 0) == 0
    finally:
        old.close()
    current = Cancellation(os.getpid())
    try:
        assert old.name != current.name
        old.cancel()
        assert wait(current._handle, 0) == 258
    finally:
        current.cancel()
        current.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita mutex reales de Windows.")
@pytest.mark.parametrize(
    "held,allowed,blocked",
    [(BotLease, SpeedLease, BotLease), (SpeedLease, BotLease, SpeedLease)],
)
def test_speed_and_attack_owners_coexist_but_same_kind_cannot_compete(held, allowed, blocked):
    results = []

    def contender():
        with allowed(os.getpid()):
            results.append("independent owner allowed")
        try:
            with blocked(os.getpid()):
                results.append("unexpected second owner")
        except DiagnosticError:
            results.append("same owner kind blocked")

    with held(os.getpid()):
        thread = threading.Thread(target=contender)
        thread.start()
        thread.join(2)
        assert not thread.is_alive()
    assert results == ["independent owner allowed", "same owner kind blocked"]
