from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

from .combat import CombatDetector
from .errors import DiagnosticError, SceneChanged
from .session import GameSession
from .world import OWNER_ADDRESS, Reader, observe_scene

MEMBER_STRIDE = 0x488
CONTEXT_DIAGNOSTIC_LIMIT = 128
CONTEXT_ANCHOR = bytes.fromhex(
    "8b811803000085c07d0432c0eb258b8904020000ff742404518b0d0c29a904"
    "8b891c0900008b4c8108e808cb0c003c010f95c0c20400"
)
MEMBER_ANCHOR = bytes.fromhex(
    "8b44240485c07e273b41047d228b54240883fa0b77198b0969c0b815020069d28804"
    "000003c28d840808410000eb0233c0c20800"
)


@dataclass(frozen=True)
class MemberSnapshot:
    slot: int
    kind_id: int
    value_4c: int
    value_50: int


@dataclass(frozen=True)
class NormalBattleContext:
    pid: int
    creation_time: int
    actor: int
    actor_identity: tuple[int, int, int]
    manager: int
    index: int
    context: int
    method_table_candidate: int
    member_info: int
    members: tuple[MemberSnapshot, ...]
    member_read_error: str | None = None

    def binding(self) -> tuple:
        return (
            self.pid,
            self.creation_time,
            self.actor,
            self.actor_identity,
            self.manager,
            self.index,
            self.context,
            self.member_info,
        )

    def summary(self) -> dict:
        return {
            "status": "resolved",
            "route": "local_context_a",
            "source": "00431769_owner_091c_indexed_by_actor_0318",
            **asdict(self),
            "turn_state_verified": False,
            "turn_execution_available": False,
            "member_values_semantics_verified": False,
            "members_status": "unavailable" if self.member_read_error else "captured",
        }


def _binding(reader: Reader) -> tuple:
    owner = reader.u32(OWNER_ADDRESS)
    world = reader.u32(owner + 0x828)
    actor = reader.u32(world + 0x2C)
    if not actor or reader.u32(actor + 0x200) != 1 or reader.u32(actor + 0x2C) != world:
        raise SceneChanged("El personaje local cambió durante la consulta.")
    index = reader.i32(actor + 0x318)
    if not 0 <= index < CONTEXT_DIAGNOSTIC_LIMIT or reader.i32(actor + 0x254) >= 0:
        raise DiagnosticError("Esta consulta requiere la ruta de combate normal observada.")
    manager = reader.u32(owner + 0x91C)
    if not manager:
        raise DiagnosticError("El gestor del combate normal todavía no está disponible.")
    context = reader.u32(manager + 8 + index * 4)
    if not context:
        raise DiagnosticError("El contexto del combate normal todavía no está disponible.")
    info_manager = reader.u32(owner + 0x830)
    info = reader.u32(actor + 0x30)
    identity = struct.unpack("<3I", reader.read(actor + 0x204, 12))
    return owner, world, actor, identity, manager, index, context, info_manager, info


def read_normal_battle(session: GameSession) -> NormalBattleContext:
    """Read the observed +318 access path without executing client functions."""
    detector = CombatDetector.for_supported_session(session)
    before = observe_scene(session)
    if detector.classify(before) != "battle" or before.native_active:
        raise DiagnosticError("Entra en combate con Auto Battle y caza nativa apagados.")
    reader = Reader(session)
    if reader.read(0x00431769, len(CONTEXT_ANCHOR)) != CONTEXT_ANCHOR:
        raise DiagnosticError("La ruta del combate normal no coincide con el código analizado.")
    if reader.read(0x004ED38B, len(MEMBER_ANCHOR)) != MEMBER_ANCHOR:
        raise DiagnosticError("La información de miembros no coincide con el código analizado.")
    binding = _binding(reader)
    _, _, actor, identity, manager, index, context, info_manager, info = binding
    members = []
    member_error = None
    try:
        base, count = struct.unpack("<II", reader.read(info_manager, 8))
        if count <= 1 or not base or info != base + 0x215B8:
            raise DiagnosticError("La información de los mercenarios no coincide con su colección.")
        for slot in range(9):
            address = info + 0x4108 + slot * MEMBER_STRIDE
            kind = reader.i32(address + 8)
            value_4c, value_50 = struct.unpack("<ii", reader.read(address + 0x4C, 8))
            if kind < 0:
                raise DiagnosticError("Un puesto de mercenario todavía no está inicializado.")
            members.append(MemberSnapshot(slot + 1, kind, value_4c, value_50))
    except (DiagnosticError, OSError) as exc:
        members.clear()
        member_error = str(exc)
    method_table = reader.u32(context)
    after = observe_scene(session)
    if detector.classify(after) != "battle" or after.native_active or _binding(reader) != binding:
        raise SceneChanged("El combate cambió durante la consulta; vuelve a actualizar.")
    return NormalBattleContext(
        session.process.pid,
        session.creation_time,
        actor,
        identity,
        manager,
        index,
        context,
        method_table,
        info,
        tuple(members),
        member_error,
    )
