import struct

import pytest

from atlantica_bot.battle import BattleFrame, BattleUnit
from atlantica_bot.battle_context import MemberSnapshot, NormalBattleContext


@pytest.fixture
def turn_frame():
    """A battle with two deployed own members and two living enemies."""
    context = NormalBattleContext(
        100,
        777,
        0x500000,
        (209, 8888, 0),
        0x600000,
        0,
        0x700000,
        0x042D8AA4,
        0x10215B8,
        (MemberSnapshot(1, 2318, 1000, 100), MemberSnapshot(2, 1224, 1000, 200)),
        client_object=0x900000,
    )
    units = (
        BattleUnit(1, 0xA01000, 1, context.actor_identity, 1, 2318, 1000, 0, 1, 0x8000),
        BattleUnit(2, 0xA02000, 1, context.actor_identity, 2, 1224, 1000, 0, 1, 0x8000),
        BattleUnit(3, 0xA03000, 6, (5633, 9999, 0), 1, 317, 1000, 1, 1, 0x8000),
        BattleUnit(4, 0xA04000, 6, (5633, 9999, 0), 2, 318, 1000, 1, 1, 0x8000),
    )
    return BattleFrame(context, 3, 0, 0, 0, 123450, units, units[0].address, (207, 222))


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
