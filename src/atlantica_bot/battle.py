from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

from .battle_context import MEMBER_STRIDE, NormalBattleContext, read_normal_battle
from .errors import DiagnosticError, SceneChanged
from .session import GameSession
from .world import OWNER_ADDRESS, Reader

UNIT_LOOKUP_ANCHOR = bytes.fromhex(
    "558bec518365fc0053568bd9578dbb380100008b3785f6741eff75fc8bcbe82bcee7ff"
    "84c074108b46043b450875088b46083b450c7415ff45fc83c704837dfc647cd033c05f5e"
    "5bc9c208008b45fcebf4"
)
OWN_TURN_ANCHOR = bytes.fromhex(
    "568bf1837e08007d0432c05ec3e803f1ffff85c07ef3a10c29a9048b90280800008b4e04"
    "8b4c8a288b801c090000ffb1040200008b4808e81ec2f5ff84c074c9ff76088b8e1c02"
    "0000e8e110ebff3c0174b783ec348bcc682ce58a08e8bc6be6ffff76088b8e1c020000"
    "e87a62ebff3c0174966a0068008000008bcee869efffff84c00f95c05ec3"
)


class BattleReadError(SceneChanged):
    def __init__(self, message: str, **details):
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class BattleUnit:
    index: int
    address: int
    world_slot: int
    identity: tuple[int, int, int]
    member_slot: int  # One-based member record, not a verified keyboard shortcut.
    kind_id: int
    life: int
    group: int
    action_state: int
    flags: int


@dataclass(frozen=True)
class BattleFrame:
    context: NormalBattleContext
    phase: int
    turn_group: int
    local_group: int
    turn_number: int
    turn_tick: int
    units: tuple[BattleUnit, ...]

    @property
    def own_turn(self) -> bool:
        return self.turn_group == self.local_group

    @property
    def sources(self) -> tuple[BattleUnit, ...]:
        return tuple(u for u in self.units if u.world_slot == 1 and u.life > 0)

    @property
    def enemies(self) -> tuple[BattleUnit, ...]:
        return tuple(
            u
            for u in self.units
            if u.group != self.local_group and 3500 <= u.identity[0] < 22000 and u.life > 0
        )

    def summary(self) -> dict:
        return {
            **asdict(self),
            "own_turn": self.own_turn,
            "turn_source": "005A2955_and_004FEBAF_group_vs_context_6c5c",
            "basic_trial_available": self.phase == 3
            and self.own_turn
            and bool(self.sources)
            and bool(self.enemies),
            "native_eligibility_fully_validated": False,
            "turn_execution_available": False,
            "keyboard_slot_mapping_verified": False,
        }


@dataclass(frozen=True)
class BattleTrial:
    frame: BattleFrame
    source: BattleUnit
    target: BattleUnit

    def validate(self) -> None:
        if (
            self.source not in self.frame.sources
            or self.target not in self.frame.enemies
            or self.frame.context.index != 0
            or self.frame.phase != 3
        ):
            raise DiagnosticError("Actualiza el combate y elige un mercenario y enemigo vivos.")
        if not self.frame.own_turn:
            raise DiagnosticError("Todavía no es el turno del grupo del personaje.")
        if self.source.action_state != 1 or not self.source.flags & 0x8000:
            raise DiagnosticError(
                "El mercenario no está en el estado nativo para probar un ataque."
            )

    def key(self) -> tuple:
        ctx = self.frame.context
        return (
            ctx.pid,
            ctx.creation_time,
            ctx.context,
            self.frame.turn_number,
            self.frame.turn_tick,
            self.source.member_slot,
        )

    def arguments(self) -> dict[str, int]:
        ctx = self.frame.context
        return {
            "battle-manager": ctx.manager,
            "battle-context": ctx.context,
            "battle-client": ctx.client_object,
            "turn-number": self.frame.turn_number,
            "turn-tick": self.frame.turn_tick,
            "mercenary": self.source.member_slot,
            "enemy-member": self.target.member_slot,
            "source-unit": self.source.address,
            "target-unit": self.target.address,
            "actor-kind": ctx.actor_identity[0],
            "actor-serial": ctx.actor_identity[1],
            "actor-unique": ctx.actor_identity[2],
        }


def _turn(reader: Reader, context: NormalBattleContext) -> tuple[int, int, int, int]:
    return (
        reader.i32(context.manager + 0x234C),
        reader.i32(context.context + 0x6C5C),
        reader.u32(context.context + 0x6C74),
        reader.u32(context.context + 0x6C60),
    )


def read_battle_frame(session: GameSession) -> BattleFrame:
    """Read the normal client's bounded unit collection; execute no client functions."""
    context = read_normal_battle(session)
    reader = Reader(session)
    if context.index != 0 or context.method_table_candidate != 0x042D8AA4:
        raise DiagnosticError("La prueba requiere el gestor de combate normal identificado.")
    if (
        reader.read(0x005A4519, len(UNIT_LOOKUP_ANCHOR)) != UNIT_LOOKUP_ANCHOR
        or reader.read(0x005A2955, len(OWN_TURN_ANCHOR)) != OWN_TURN_ANCHOR
    ):
        raise DiagnosticError("La colección de unidades no coincide con el código analizado.")
    client = context.client_object
    manager_client = reader.u32(context.manager + 0x25E0)
    if not client or manager_client != client:
        raise BattleReadError(
            "El gestor y la colección de unidades no coinciden.",
            owner_client=client,
            manager_client=manager_client,
        )
    token = _turn(reader, context)
    records = reader.read(context.context + 0xB4, 6 * 12)
    groups = struct.unpack("<6h", reader.read(context.context + 0x11A, 12))
    participants = {}
    for number in range(6):
        identity = struct.unpack_from("<3I", records, number * 12)
        if identity[0]:
            if identity in participants or any(i[0] == identity[0] for i in participants):
                raise DiagnosticError("Las identidades del combate son ambiguas; actualiza.")
            participants[identity] = groups[number]
    if context.actor_identity not in participants:
        raise BattleReadError(
            "El personaje ya no pertenece a este combate.",
            actor_identity=context.actor_identity,
            participants=[{"identity": k, "group": v} for k, v in participants.items()],
        )
    world = reader.u32(context.actor + 0x2C)
    owner = reader.u32(OWNER_ADDRESS)
    info_manager = reader.u32(owner + 0x830)
    info_base, info_count = struct.unpack("<II", reader.read(info_manager, 8))
    used = reader.read(client + 0xD4, 100)
    pointers = struct.unpack("<100I", reader.read(client + 0x138, 400))
    units = []
    seen = set()
    for index, pointer in enumerate(pointers):
        if index == 0 or used[index] != 1 or not pointer:
            continue
        world_slot, member = struct.unpack("<ii", reader.read(pointer + 4, 8))
        if not 0 < world_slot < min(info_count, 450) or not 0 <= member < 9:
            continue
        actor = reader.u32(world + 0x28 + world_slot * 4)
        if not actor:
            raise SceneChanged("Una unidad del combate cambió durante la consulta.")
        identity = struct.unpack("<3I", reader.read(actor + 0x204, 12))
        if identity not in participants:
            continue
        info = reader.u32(actor + 0x30)
        record = info + 0x4108 + member * MEMBER_STRIDE
        actual = (
            info,
            reader.u32(actor + 0x200),
            reader.u32(actor + 0x2C),
            reader.u32(pointer + 0x21C),
            reader.u32(pointer + 0x230),
        )
        expected = (info_base + world_slot * 0x215B8, world_slot, world, info, record)
        if actual != expected:
            raise BattleReadError(
                "La unidad no coincide con su registro de miembro; actualiza.",
                unit_index=index,
                unit_address=pointer,
                world_slot=world_slot,
                member_slot=member + 1,
                expected=expected,
                actual=actual,
            )
        key = (world_slot, member)
        if key in seen:
            raise SceneChanged("La colección de unidades cambió durante la consulta.")
        seen.add(key)
        kind, life = reader.i32(record + 8), reader.i32(record + 0x4C)
        if kind <= 0:
            continue
        units.append(
            BattleUnit(
                index,
                pointer,
                world_slot,
                identity,
                member + 1,
                kind,
                life,
                participants[identity],
                reader.byte(pointer + 0x508),
                reader.u32(pointer + 0x20),
            )
        )
    if (
        read_normal_battle(session).binding() != context.binding()
        or _turn(reader, context) != token
        or reader.read(client + 0xD4, 100) != used
        or reader.read(client + 0x138, 400) != struct.pack("<100I", *pointers)
        or reader.read(context.context + 0xB4, 72) != records
        or reader.read(context.context + 0x11A, 12) != struct.pack("<6h", *groups)
    ):
        raise SceneChanged("El combate o su turno cambió; vuelve a actualizar.")
    phase, turn_group, turn_number, turn_tick = token
    return BattleFrame(
        context,
        phase,
        turn_group,
        participants[context.actor_identity],
        turn_number,
        turn_tick,
        tuple(units),
    )
