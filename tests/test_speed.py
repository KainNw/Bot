import json
import struct
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.speed import (
    CONTEXT_ACCESS_ADDRESS,
    CONTEXT_ACCESS_BYTES,
    CONTEXT_STRIDE,
    CONTEXT_TABLE_ADDRESS,
    RATE_GETTER_ADDRESS,
    RATE_WRAPPER_ADDRESS,
    RATE_WRAPPER_BYTES,
    SPEED_GLOBAL_FIELDS,
    decode_rate_getter,
    read_speed_snapshot,
)


def speed_session(*, overrides=None):
    memory = {
        address: struct.pack(fmt, 100 if fmt in ("<i", "<I") else 1.0)
        for _, address, fmt in SPEED_GLOBAL_FIELDS
    }
    memory[0x60265C] = struct.pack("<f", 1.25)
    memory.update(
        {
            CONTEXT_ACCESS_ADDRESS: CONTEXT_ACCESS_BYTES,
            RATE_WRAPPER_ADDRESS: RATE_WRAPPER_BYTES,
            RATE_GETTER_ADDRESS: bytes.fromhex("d98120010000c3"),
            CONTEXT_TABLE_ADDRESS: struct.pack("<I", 0x10000000),
            0x10000018: struct.pack("<I", 0x20000000),
            0x10000000 + CONTEXT_STRIDE + 0x18: struct.pack("<I", 0x20000100),
            0x2000000C: struct.pack("<I", 0x30000000),
            0x2000010C: struct.pack("<I", 0x30001000),
            0x30000120: struct.pack("<f", 1.0),
            0x30001120: struct.pack("<f", 1.4),
        }
    )
    memory.update(overrides or {})
    calls = []

    def read(pid, address, size):
        assert pid == 100
        calls.append((address, size))
        value = memory[address]
        if value is None:
            raise DiagnosticError("Dato no disponible")
        return value

    return SimpleNamespace(
        process=SimpleNamespace(pid=100),
        creation_time=777,
        system=SimpleNamespace(read_memory=read),
    ), calls


def test_speed_snapshot_reads_only_observed_fields_and_retains_unverified_semantics(turn_frame):
    session, calls = speed_session()
    context = replace(turn_frame.context, manager=0x600000)
    result = read_speed_snapshot(session, context)
    assert result["fields"]["manager_rate_candidate"] == {
        "address": "0060265C",
        "raw_hex": struct.pack("<f", 1.25).hex(),
        "status": "read",
        "value": 1.25,
    }
    allowed = {address for _, address, _ in SPEED_GLOBAL_FIELDS} | {
        0x60265C,
        CONTEXT_ACCESS_ADDRESS,
        RATE_WRAPPER_ADDRESS,
        RATE_GETTER_ADDRESS,
        CONTEXT_TABLE_ADDRESS,
        0x10000018,
        0x10000000 + CONTEXT_STRIDE + 0x18,
        0x2000000C,
        0x2000010C,
        0x30000120,
        0x30001120,
    }
    assert {address for address, _ in calls} <= allowed
    graphics = result["graphics_rates"]
    assert graphics["status"] == "read" and graphics["getter_offset"] == 0x120
    assert graphics["contexts"]["0"]["value"] == 1.0
    assert graphics["contexts"]["1"]["value"] == pytest.approx(1.4)
    assert not result["speed_control_available"] and not result["semantics_fully_validated"]
    assert not result["writes_or_client_commands"]


@pytest.mark.parametrize("replacement", [None, b"\0", struct.pack("<f", float("nan"))])
def test_unavailable_short_or_nonfinite_field_does_not_invent_a_rate(replacement):
    session, _ = speed_session(overrides={0x042F320C: replacement})
    result = read_speed_snapshot(session, None)
    field = result["fields"]["reset_rate_candidate"]
    assert field["status"] in ("unavailable", "non_finite") and field["value"] is None
    assert "manager_rate_candidate" not in result["fields"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("changed", [{"pid": 101}, {"creation_time": 778}])
def test_foreign_instance_is_rejected_before_reading_any_speed_address(turn_frame, changed):
    session, calls = speed_session()
    with pytest.raises(DiagnosticError, match="otra instancia"):
        read_speed_snapshot(session, replace(turn_frame.context, **changed))
    assert not calls


@pytest.mark.parametrize(
    "code,expected",
    [
        ("d98120010000c3", (0x120, "<f")),
        ("dd8120010000c3", (0x120, "<d")),
        ("d94120c3cccccc", (0x20, "<f")),
        ("d98101000000c3", None),
        ("d98100100000c3", None),
        ("d941f0c3cccccc", None),
        ("e90000000090c3", None),
        ("d94120c3ebfecc", None),
    ],
)
def test_rate_getter_decoder_accepts_only_a_bounded_single_load(code, expected):
    assert decode_rate_getter(bytes.fromhex(code)) == expected


@pytest.mark.parametrize(
    "address,replacement",
    [
        (CONTEXT_ACCESS_ADDRESS, bytes(len(CONTEXT_ACCESS_BYTES))),
        (RATE_WRAPPER_ADDRESS, bytes(len(RATE_WRAPPER_BYTES))),
        (RATE_GETTER_ADDRESS, b"\x90" * 7),
    ],
)
def test_changed_code_never_follows_graphics_pointers(address, replacement):
    session, calls = speed_session(overrides={address: replacement})
    result = read_speed_snapshot(session, None)
    assert result["graphics_rates"]["status"] == "unavailable"
    assert CONTEXT_TABLE_ADDRESS not in {a for a, _ in calls}


def test_graphics_pointer_replacement_discards_that_context():
    session, _ = speed_session()
    original = session.system.read_memory
    entry_reads = 0

    def changing(pid, address, size):
        nonlocal entry_reads
        if address == 0x10000018:
            entry_reads += 1
            if entry_reads == 2:
                return struct.pack("<I", 0x22220000)
        return original(pid, address, size)

    session.system.read_memory = changing
    contexts = read_speed_snapshot(session, None)["graphics_rates"]["contexts"]
    assert contexts["0"]["status"] == "unavailable"
    assert contexts["0"]["reason"] == "graphics_binding_changed"
    assert contexts["1"]["status"] == "read"


def test_invalid_graphics_root_is_not_dereferenced():
    session, calls = speed_session(overrides={CONTEXT_TABLE_ADDRESS: bytes(4)})
    result = read_speed_snapshot(session, None)
    assert result["graphics_rates"]["status"] == "unavailable"
    assert not any(address == 0x18 for address, _ in calls)
