import ctypes
import struct
from pathlib import Path

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.windows import WindowsSystem


def fake_directory_reader(*, status=0, length=None, peb=0x1000):
    system = WindowsSystem.__new__(WindowsSystem)
    closed, reads = [], []
    value = "C:\\Games\\Atlantica".encode("utf-16le")
    system._open = lambda access, inherit, pid: 42
    system._close = closed.append

    def query(handle, info_class, output, size, returned):
        assert handle == 42
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            assert info_class == 26
            ctypes.cast(output, ctypes.POINTER(ctypes.c_size_t)).contents.value = peb
        else:
            output._obj.peb = peb
        return status

    def read(pid, address, size):
        reads.append((address, size))
        values = {
            0x1010: (0x2000).to_bytes(4, "little"),
            0x2024: struct.pack(
                "<HHI", len(value) if length is None else length, len(value) + 2, 0x3000
            ),
            0x3000: value,
        }
        assert len(values[address]) == size
        return values[address]

    system._query_information = query
    system.read_memory = read
    return system, closed, reads


def test_reads_only_current_directory_not_process_environment():
    system, closed, reads = fake_directory_reader()
    assert system.working_directory(123) == Path("C:\\Games\\Atlantica")
    assert closed == [42]
    assert [address for address, _ in reads] == [0x1010, 0x2024, 0x3000]


@pytest.mark.parametrize("length", [0, 1, 1000])
def test_rejects_malformed_unicode_metadata_without_reading_string(length):
    system, closed, reads = fake_directory_reader(length=length)
    with pytest.raises(DiagnosticError, match="no es válida"):
        system.working_directory(123)
    assert len(reads) == 2
    assert closed == [42]


def test_query_access_error_closes_handle_without_reading_memory():
    system, closed, reads = fake_directory_reader(status=-1073741790)
    with pytest.raises(DiagnosticError, match="NTSTATUS C0000022"):
        system.working_directory(123)
    assert closed == [42]
    assert reads == []


def test_does_not_guess_peb_if_wow64_query_returns_zero():
    system, closed, reads = fake_directory_reader(peb=0)
    with pytest.raises(DiagnosticError, match="PEB"):
        system.working_directory(123)
    assert reads == []
    assert closed == [42]
