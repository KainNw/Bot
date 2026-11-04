from __future__ import annotations

import math
import struct

from .battle_context import NormalBattleContext
from .errors import DiagnosticError
from .session import GameSession
from .world import Reader

# Direct dependencies of 004F53E9, 0059C225 and 005A0D9C in the captured build.
# Reading these pages does not call the setter or change the animation rate.
SPEED_CODE_BLOCKS = (
    ("graphics-context-access", 0x00A04000, 0x2000),
    ("graphics-rate-access", 0x00A14000, 0x2000),
    ("graphics-clock-helper", 0x00554000, 0x1000),
    ("graphics-rate-backend", 0x00A6F000, 0x2000),
    ("graphics-shared-helper", 0x005FA000, 0x1000),
    ("graphics-rate-implementation", 0x00A46000, 0x2000),
)
SPEED_READONLY_BLOCKS = (
    ("battle-rate-common-constants", 0x042C1000, 0x1000),
    ("battle-rate-movement-constants", 0x042C6000, 0x1000),
    ("battle-rate-limits-and-label", 0x042F3000, 0x1000),
)
SPEED_GLOBAL_FIELDS = (
    ("rate_input", 0x0822F524, "<i"),
    ("rate_divisor", 0x08230E14, "<i"),
    ("graphics_context_index", 0x1539CE18, "<I"),
    ("guard_threshold_candidate", 0x042C11D4, "<f"),
    ("rate_bias_candidate", 0x042C11E8, "<d"),
    ("frame_interval_numerator", 0x042F31E8, "<d"),
    ("reset_rate_candidate", 0x042F320C, "<f"),
    ("movement_time_divisor", 0x042F3688, "<d"),
)
CONTEXT_ACCESS_ADDRESS = 0x00A0481E
CONTEXT_ACCESS_BYTES = bytes.fromhex("a118ce391569c074020000030510ce3915c3")
RATE_WRAPPER_ADDRESS = 0x00A14B10
RATE_WRAPPER_BYTES = bytes.fromhex("8b490ce938af0500")
RATE_GETTER_ADDRESS = 0x00A6FA50
CONTEXT_TABLE_ADDRESS = 0x1539CE10
CONTEXT_STRIDE = 0x274
GETTER_HOP_LIMIT = 4
GETTER_CODE_LIMITS = (0x00401000, 0x03F85000)


def decode_rate_getter(code: bytes) -> tuple[int, str] | None:
    """Recognize a single floating-point load and return; never execute the getter."""
    if len(code) != 7 or code[0] not in (0xD9, 0xDD):
        return None
    if code[1] == 0x81 and code[6] == 0xC3:
        offset = int.from_bytes(code[2:6], "little")
    elif code[1] == 0x41 and code[3] == 0xC3 and set(code[4:]) <= {0x90, 0xCC}:
        offset = int.from_bytes(code[2:3], "little", signed=True)
    else:
        return None
    fmt = "<f" if code[0] == 0xD9 else "<d"
    size = struct.calcsize(fmt)
    return (offset, fmt) if 0 <= offset <= 0x1000 - size and offset % size == 0 else None


def resolve_rate_getter(reader: Reader) -> dict:
    """Follow a bounded chain of direct tail jumps, recording code and receiver loads."""
    address = RATE_GETTER_ADDRESS
    result = {"status": "unavailable", "steps": [], "receiver_dereferences": []}
    seen = set()
    for hop in range(GETTER_HOP_LIMIT + 1):
        if address in seen:
            result["reason"] = "getter_cycle"
            return result
        if not GETTER_CODE_LIMITS[0] <= address <= GETTER_CODE_LIMITS[1] - 16:
            result["reason"] = "getter_target_outside_code"
            return result
        seen.add(address)
        try:
            code = reader.read(address, 16)
        except (DiagnosticError, OSError):
            result["reason"] = "getter_code_unavailable"
            return result
        step = {"address": f"{address:08X}", "code_hex": code.hex()}
        result["steps"].append(step)
        decoded = decode_rate_getter(code[:7])
        if decoded is not None:
            offset, fmt = decoded
            result.update(status="resolved", offset=offset, format=fmt)
            step["code_hex"] = code[:7].hex()
            return result
        jump_at, dereference = 0, None
        if code[:2] == b"\x8b\x09":
            jump_at, dereference = 2, 0
        elif code[:2] == b"\x8b\x49":
            jump_at, dereference = 3, int.from_bytes(code[2:3], "little", signed=True)
        elif code[:2] == b"\x8b\x89":
            jump_at, dereference = 6, int.from_bytes(code[2:6], "little", signed=True)
        if (
            code[jump_at] != 0xE9
            or dereference is not None
            and (not 0 <= dereference <= 0x400 or dereference % 4)
        ):
            result["reason"] = "getter_shape_not_resolved"
            return result
        length = jump_at + 5
        target = (
            address + length + int.from_bytes(code[jump_at + 1 : length], "little", signed=True)
        )
        step.update(code_hex=code[:length].hex(), jump_target=f"{target:08X}")
        if hop == GETTER_HOP_LIMIT:
            result["reason"] = "getter_hop_limit"
            return result
        if dereference is not None:
            result["receiver_dereferences"].append(dereference)
        address = target
    return result


def _read_graphics_rates(reader: Reader) -> dict:
    result = {"status": "unavailable", "contexts": {}}
    try:
        if (
            reader.read(CONTEXT_ACCESS_ADDRESS, len(CONTEXT_ACCESS_BYTES)) != CONTEXT_ACCESS_BYTES
            or reader.read(RATE_WRAPPER_ADDRESS, len(RATE_WRAPPER_BYTES)) != RATE_WRAPPER_BYTES
        ):
            result["reason"] = "accessor_code_changed"
            return result
        getter = resolve_rate_getter(reader)
        result["getter"] = getter
        if getter["status"] != "resolved":
            result["reason"] = getter["reason"]
            return result
        offset, fmt = getter["offset"], getter["format"]
        dereferences = getter["receiver_dereferences"]
        result.update(getter_offset=offset, getter_format=fmt)

        def pointer(address: int, needed: int) -> int:
            value = reader.u32(address)
            if not 0x10000 <= value <= 0xFFFFFFFF - needed:
                raise DiagnosticError("Puntero gráfico no disponible")
            return value

        table = pointer(CONTEXT_TABLE_ADDRESS, CONTEXT_STRIDE * 2)
        result["table"] = table
        for index in (0, 1):
            item = {"status": "unavailable"}
            result["contexts"][str(index)] = item
            try:
                entry = table + index * CONTEXT_STRIDE
                wrapper = pointer(entry + 0x18, 0x10)
                needed = max([offset + struct.calcsize(fmt), *(d + 4 for d in dereferences)])
                backend = pointer(wrapper + 0xC, needed)
                receiver, bindings = backend, []
                for dereference in dereferences:
                    field_address = receiver + dereference
                    receiver = pointer(field_address, needed)
                    bindings.append((field_address, receiver))
                raw = reader.read(receiver + offset, struct.calcsize(fmt))
                value = struct.unpack(fmt, raw)[0]
                if (
                    reader.u32(CONTEXT_TABLE_ADDRESS) != table
                    or reader.u32(entry + 0x18) != wrapper
                    or reader.u32(wrapper + 0xC) != backend
                    or any(reader.u32(address) != value for address, value in bindings)
                ):
                    item["reason"] = "graphics_binding_changed"
                    continue
                item.update(
                    wrapper=wrapper,
                    backend=backend,
                    receiver=receiver,
                    receiver_bindings=bindings,
                    address=f"{receiver + offset:08X}",
                    raw_hex=raw.hex(),
                    status="read" if math.isfinite(value) else "non_finite",
                    value=value if math.isfinite(value) else None,
                )
            except (DiagnosticError, OSError, struct.error):
                item["reason"] = "graphics_field_unavailable"
        result["status"] = (
            "read"
            if any(item["status"] == "read" for item in result["contexts"].values())
            else "unavailable"
        )
        if all(item["status"] == "read" for item in result["contexts"].values()):
            result["shared_receiver"] = (
                result["contexts"]["0"]["receiver"] == result["contexts"]["1"]["receiver"]
            )
    except (DiagnosticError, OSError, struct.error):
        result["reason"] = "graphics_access_unavailable"
    return result


def read_speed_snapshot(session: GameSession, context: NormalBattleContext | None) -> dict:
    """Read observed inputs, retaining raw bytes and unresolved semantics."""
    if context is not None and (context.pid, context.creation_time) != (
        session.process.pid,
        session.creation_time,
    ):
        raise DiagnosticError("La lectura de velocidad pertenece a otra instancia.")
    reader = Reader(session)
    fields = {}

    def field(name: str, address: int, fmt: str) -> None:
        item = {"address": f"{address:08X}"}
        try:
            raw = reader.read(address, struct.calcsize(fmt))
            value = struct.unpack(fmt, raw)[0]
            item["raw_hex"] = raw.hex()
            if isinstance(value, float) and not math.isfinite(value):
                item.update(status="non_finite", value=None)
            else:
                item.update(status="read", value=value)
        except (DiagnosticError, OSError, struct.error):
            item.update(status="unavailable", value=None)
        fields[name] = item

    for name, address, fmt in SPEED_GLOBAL_FIELDS:
        field(name, address, fmt)
    if context is not None:
        if not 0 < context.manager <= 0xFFFFFFFF - 0x2660:
            raise DiagnosticError("El gestor de velocidad no tiene una dirección válida.")
        field("manager_rate_candidate", context.manager + 0x265C, "<f")
    return {
        "status": "research_only",
        "pid": session.process.pid,
        "creation_time": session.creation_time,
        "manager": context.manager if context is not None else None,
        "fields": fields,
        "graphics_rates": _read_graphics_rates(reader),
        "semantics_fully_validated": False,
        "speed_control_available": False,
        "writes_or_client_commands": False,
    }
