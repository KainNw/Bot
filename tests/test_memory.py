import ctypes
import sys

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.report import self_test
from atlantica_bot.windows import WindowsSystem


def fake_native_reader(*, partial=False, failed=False):
    system = WindowsSystem.__new__(WindowsSystem)
    opened, closed = [], []

    def open_process(access, inherit, pid):
        opened.append((access, inherit, pid))
        return 42

    def read_process(handle, address, output, size, received):
        assert handle == 42
        assert address == 0x1000
        ctypes.memmove(output, b"MZ", size)
        ctypes.cast(received, ctypes.POINTER(ctypes.c_size_t)).contents.value = (
            size - 1 if partial else size
        )
        return not failed

    system._open = open_process
    system._close = closed.append
    system._read = read_process
    return system, opened, closed


def test_requests_only_read_access_and_closes_handle():
    system, opened, closed = fake_native_reader()
    assert system.read_memory(123, 0x1000, 2) == b"MZ"
    assert opened == [(0x0010, False, 123)]
    assert closed == [42]


def test_partial_read_is_failure_and_handle_is_closed():
    system, _, closed = fake_native_reader(partial=True)
    with pytest.raises(DiagnosticError, match="incompleta"):
        system.read_memory(123, 0x1000, 2)
    assert closed == [42]


def test_read_error_is_failure_and_handle_is_closed(monkeypatch):
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    system, _, closed = fake_native_reader(failed=True)
    with pytest.raises(DiagnosticError, match="WinError 5"):
        system.read_memory(123, 0x1000, 2)
    assert closed == [42]


@pytest.mark.parametrize(
    "address,size",
    [(0, 2), (-1, 2), (0x1000, 0), (0x1000, 1048577), (True, 2), (0x1000, 1.5), (1 << 64, 1)],
)
def test_invalid_ranges_do_not_open_process(address, size):
    system, opened, closed = fake_native_reader()
    with pytest.raises(DiagnosticError):
        system.read_memory(123, address, size)
    assert opened == closed == []


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita las APIs nativas de Windows.")
def test_real_windows_api_on_own_process():
    self_test(WindowsSystem())
