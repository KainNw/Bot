import struct

import pytest


@pytest.fixture
def executable(tmp_path):
    """A small PE header fixture; never executable code."""
    path = tmp_path / "Atlantica.exe"
    data = bytearray(160)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", data, 0x84, 0x8664)
    path.write_bytes(data)
    return path
