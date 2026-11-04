from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING

from .errors import DiagnosticError, SceneChanged
from .session import GameSession
from .speed import CONTEXT_STRIDE, CONTEXT_TABLE_ADDRESS
from .world import OWNER_ADDRESS, Reader

if TYPE_CHECKING:
    from .speed_trial import SpeedPlan


def read_speed_sample(session: GameSession, plan: SpeedPlan) -> dict:
    """Read the trial's current objects; never follow a saved, possibly retired pointer."""
    if (session.process.pid, session.creation_time) != (plan.pid, plan.creation_time):
        raise DiagnosticError("La lectura pertenece a otra instancia.")

    def instance() -> None:
        if session.system.process_creation_time(plan.pid) != plan.creation_time:
            raise SceneChanged("La instancia terminó durante el seguimiento.")

    instance()
    reader = Reader(session)

    def pointer(address: int) -> int:
        value = reader.u32(address)
        if not 0x10000 <= value <= 0xFFFFF000:
            raise SceneChanged("Un objeto cambió durante el seguimiento.")
        return value

    def binding() -> tuple:
        owner = pointer(OWNER_ADDRESS)
        world = pointer(owner + 0x828)
        player = pointer(world + 0x2C)
        manager = pointer(owner + 0x91C)
        if (
            reader.i32(owner + 0xB98) != 2
            or player != plan.player
            or manager != plan.manager
            or reader.u32(player + 0x200) != 1
            or reader.u32(player + 0x2C) != world
            or reader.u32(manager) != 0x042D8AA4
            or struct.unpack("<3I", reader.read(player + 0x204, 12)) != plan.actor_identity
        ):
            raise SceneChanged("El personaje o gestor cambió durante el seguimiento.")
        index = reader.i32(player + 0x318)
        if not 0 <= index < 128 or reader.i32(player + 0x254) >= 0:
            raise SceneChanged("El personaje salió del combate normal.")
        context = pointer(manager + 8 + index * 4)
        if context != plan.context:
            raise SceneChanged("El contexto cambió durante el seguimiento.")
        table = pointer(CONTEXT_TABLE_ADDRESS)
        roots = []
        for index in (0, 1):
            wrapper = pointer(table + index * CONTEXT_STRIDE + 0x18)
            backend = pointer(wrapper + 0xC)
            node = pointer(backend)
            clock = pointer(node + 0x120)
            roots.append((wrapper, backend, node, clock))
        if (table, tuple(roots)) != (plan.table, plan.roots):
            raise SceneChanged("Los objetos gráficos cambiaron durante el seguimiento.")
        return owner, world, player, manager, context, table, tuple(roots)

    before = binding()
    owner, _, _, manager, context, _, roots = before

    def rate(address: int) -> float:
        value = struct.unpack("<f", reader.read(address, 4))[0]
        if not math.isfinite(value):
            raise DiagnosticError("La escala dejó de ser un número válido.")
        return value

    result = {
        "manager_rate": rate(manager + 0x265C),
        "battle_graphics_rate": rate(roots[1][3] + 0x50),
        "map_graphics_rate": rate(roots[0][3] + 0x50),
        "graphics_context_index": reader.u32(0x1539CE18),
        "phase": reader.i32(manager + 0x234C),
        "turn_number": reader.u32(context + 0x6C74),
        "turn_tick": reader.u32(context + 0x6C60),
        # The captured animation consumer reads owner+BA4. Its unit is unverified.
        "client_tick": reader.u32(owner + 0xBA4),
    }
    if binding() != before:
        raise SceneChanged("Los enlaces cambiaron durante el seguimiento.")
    instance()
    return result
