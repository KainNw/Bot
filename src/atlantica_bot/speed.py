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
        "semantics_fully_validated": False,
        "speed_control_available": False,
        "writes_or_client_commands": False,
    }
