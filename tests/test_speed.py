import json
import struct
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.speed import SPEED_GLOBAL_FIELDS, read_speed_snapshot


def speed_session(*, overrides=None):
    memory = {
        address: struct.pack(fmt, 100 if fmt in ("<i", "<I") else 1.0)
        for _, address, fmt in SPEED_GLOBAL_FIELDS
    }
    memory[0x60265C] = struct.pack("<f", 1.25)
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
    assert calls == [(address, struct.calcsize(fmt)) for _, address, fmt in SPEED_GLOBAL_FIELDS] + [
        (0x60265C, 4)
    ]
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
