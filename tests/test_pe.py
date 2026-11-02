import hashlib
import struct

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.pe import inspect_executable


def test_identifies_build_by_architecture_and_actual_file_hash(executable):
    result = inspect_executable(executable)
    assert result.name == "Atlantica.exe"
    assert (result.architecture, result.bits) == ("x64", 64)
    assert result.sha256 == hashlib.sha256(executable.read_bytes()).hexdigest()


@pytest.mark.parametrize("machine, expected", [(0x014C, ("x86", 32)), (0xAA64, ("arm64", 64))])
def test_other_machine_types(executable, machine, expected):
    data = bytearray(executable.read_bytes())
    struct.pack_into("<H", data, 0x84, machine)
    executable.write_bytes(data)
    result = inspect_executable(executable)
    assert (result.architecture, result.bits) == expected


@pytest.mark.parametrize("corruption", ["dos", "offset", "signature", "machine", "truncated"])
def test_rejects_invalid_headers(executable, corruption):
    data = bytearray(executable.read_bytes())
    if corruption == "dos":
        data[:2] = b"NO"
    elif corruption == "offset":
        struct.pack_into("<I", data, 0x3C, 0xFFFFFF00)
    elif corruption == "signature":
        data[0x80:0x84] = b"FAIL"
    elif corruption == "machine":
        struct.pack_into("<H", data, 0x84, 0x9999)
    else:
        data = data[:130]
    executable.write_bytes(data)
    with pytest.raises(DiagnosticError):
        inspect_executable(executable)
