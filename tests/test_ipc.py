import ctypes
import os
import sys
import threading

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.ipc import BotLease, Cancellation
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
