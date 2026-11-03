from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass

from .errors import DiagnosticError, SceneChanged
from .hunting import control_hunting
from .session import GameSession

OWNER_ADDRESS = 0x04A9290C
SLOT_COUNT = 450
TABLE_OFFSET = 0x28
INDEX_LIMIT = 0x5BCB
INDEX_VECTOR_OFFSET = 0x44D9C
INDEX_COUNT_OFFSET = 0x44DA0


@dataclass(frozen=True)
class ActiveIndex:
    address: int
    vector_address: int
    capacity: int
    slots: tuple[int, ...]
    membership: bytes

    @classmethod
    def read(cls, reader: Reader, manager: int) -> ActiveIndex:
        address = reader.u32(manager + 0x24)
        if not address:
            raise DiagnosticError("El cliente todavía no publica los índices activos.")
        capacity = reader.u32(address)
        vector_address, count = struct.unpack("<II", reader.read(address + INDEX_VECTOR_OFFSET, 8))
        if not 1 <= capacity <= INDEX_LIMIT + 1 or count > capacity:
            raise DiagnosticError("La colección de índices activos no es válida.")
        if not vector_address:
            raise DiagnosticError("El cliente todavía no publica la lista de índices activos.")
        slots = struct.unpack(f"<{count}I", reader.read(vector_address, count * 4)) if count else ()
        if len(set(slots)) != len(slots) or any(
            not 1 <= slot < capacity or slot > INDEX_LIMIT for slot in slots
        ):
            raise DiagnosticError("La lista de índices activos cambió o contiene datos no válidos.")
        # 0044611C tests the first dword of record (slot + 1), with a 12-byte stride.
        membership = reader.read(address + 12, SLOT_COUNT * 12)
        if any(
            struct.unpack_from("<I", membership, slot * 12)[0] == 0
            for slot in slots
            if slot < SLOT_COUNT
        ):
            raise SceneChanged("Los índices activos cambiaron durante la lectura; actualiza.")
        return cls(address, vector_address, capacity, slots, membership)


class Reader:
    def __init__(self, session: GameSession):
        self.session = session

    def read(self, address: int, size: int) -> bytes:
        if not 0 < address <= 0xFFFFFFFF - size + 1:
            raise DiagnosticError("Dirección no válida en la lectura de personajes.")
        data = self.session.system.read_memory(self.session.process.pid, address, size)
        if len(data) != size:
            raise DiagnosticError("La lectura de personajes quedó incompleta.")
        return data

    def u32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little")

    def i32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little", signed=True)

    def byte(self, address: int) -> int:
        return self.read(address, 1)[0]


@dataclass(frozen=True)
class GridPosition:
    map_id: int
    x: int
    y: int


@dataclass(frozen=True)
class Candidate:
    slot: int
    kind_id: int
    map_id: int
    x: int
    y: int
    grid_distance: int
    identity: tuple[int, int, int] = ()
    distance_squared: float | None = None


@dataclass(frozen=True)
class WorldView:
    player: GridPosition | None
    candidates: tuple[Candidate, ...]
    scene_code: int
    read_errors: int = 0
    changed_entries: int = 0
    observed_entries: int = 0
    rejected_by: tuple[tuple[str, int], ...] = ()
    active_index_entries: int = 0
    inactive_entries: int = 0
    out_of_scope_entries: int = 0
    range_limit_squared: float | None = None

    def summary(self) -> dict:
        return {
            "scene_code": self.scene_code,
            "player": asdict(self.player) if self.player else None,
            "candidates": [asdict(candidate) for candidate in self.candidates[:10]],
            "candidate_count": len(self.candidates),
            "read_errors": self.read_errors,
            "changed_entries": self.changed_entries,
            "observed_entries": self.observed_entries,
            "rejected_by": dict(self.rejected_by),
            "active_index_entries": self.active_index_entries,
            "inactive_entries": self.inactive_entries,
            "out_of_scope_entries": self.out_of_scope_entries,
            "range_limit_squared": self.range_limit_squared,
            "attack_eligibility_fully_validated": False,
        }


def _grid(reader: Reader, actor: int) -> GridPosition:
    info = reader.u32(actor + 0x30)
    if not info:
        raise DiagnosticError("El personaje todavía no publica su posición de rejilla.")
    return GridPosition(*struct.unpack("<hhh", reader.read(info + 0xCA, 6)))


def _world_position(reader: Reader, actor: int) -> tuple[float, float, float]:
    position = struct.unpack("<fff", reader.read(actor + 0xB8C, 12))
    if not all(math.isfinite(value) for value in position):
        raise DiagnosticError("El cliente publica una posición 3D no válida.")
    return position


@dataclass(frozen=True)
class LocalState:
    state: int
    context_a: int
    context_b: int
    flags: int
    linked_state: int | None = None


@dataclass(frozen=True)
class NavigationState:
    player_address: int
    tick: int
    map_id: int
    x: int
    y: int
    active: bool
    moving: bool

    @property
    def key(self) -> tuple[int, ...]:
        return self.player_address, self.tick, self.map_id, self.x, self.y

    def summary(self) -> dict:
        return asdict(self)

    @classmethod
    def from_report(cls, payload: dict) -> NavigationState:
        try:
            result = cls(**payload)
            if (
                any(type(value) is not int for value in result.key)
                or not 0 < result.player_address <= 0xFFFFFFFF
                or not 0 <= result.tick <= 0xFFFFFFFF
                or not 0 <= result.map_id <= 0x157B
                or not 0 < result.x <= 32767
                or not 0 < result.y <= 32767
                or type(result.active) is not bool
                or type(result.moving) is not bool
            ):
                raise ValueError
            return result
        except (ValueError, TypeError) as exc:
            raise DiagnosticError("La respuesta de desplazamiento no es válida.") from exc


@dataclass(frozen=True)
class Observation:
    pid: int
    creation_time: int | None
    scene_code: int
    player: GridPosition | None
    native_active: bool = False
    local: LocalState | None = None
    navigation: NavigationState | None = None

    def summary(self) -> dict:
        return asdict(self)


def _local_state(reader: Reader, actor: int) -> LocalState:
    linked = reader.u32(actor + 0x14)
    try:
        linked_state = reader.i32(linked + 0x380) if linked else None
    except (DiagnosticError, OSError):
        linked_state = None  # Optional diagnostic; never used to classify combat.
    return LocalState(
        reader.byte(actor + 0x38),
        reader.i32(actor + 0x318),
        reader.i32(actor + 0x254),
        reader.u32(actor + 0x388),
        linked_state,
    )


def _navigation(reader: Reader, actor: int) -> NavigationState:
    data = reader.read(actor + 0x1012, 12)
    moving = reader.byte(actor + 0xB78)
    if data[0] not in (0, 1) or moving not in (0, 1):
        raise DiagnosticError("El estado de desplazamiento del cliente no es válido.")
    return NavigationState(
        actor,
        struct.unpack_from("<I", data, 2)[0],
        *struct.unpack_from("<hhh", data, 6),
        bool(data[0]),
        bool(moving),
    )


def observe_scene(
    session: GameSession, *, include_navigation: bool = False, allow_player_movement: bool = False
) -> Observation:
    state = session.snapshot()
    reader = Reader(session)
    owner = reader.u32(OWNER_ADDRESS)
    if not owner:
        raise DiagnosticError("El cliente todavía no publica una escena válida.")
    scene = reader.i32(owner + 0xB98)
    player = local = navigation = None
    if scene == 2:
        manager = reader.u32(owner + 0x828)
        if not manager:
            raise DiagnosticError("No se pudo leer el personaje del mapa.")
        actor = reader.u32(manager + TABLE_OFFSET + 4)
        if not actor or reader.u32(actor + 0x200) != 1:
            raise DiagnosticError("No se pudo validar el personaje del mapa.")
        player = _grid(reader, actor)
        local = _local_state(reader, actor)
        navigation = _navigation(reader, actor) if include_navigation else None
        current_position = _grid(reader, actor)
        if (
            reader.u32(owner + 0x828) != manager
            or reader.u32(manager + TABLE_OFFSET + 4) != actor
            or reader.u32(actor + 0x200) != 1
            or current_position.map_id != player.map_id
            or (not allow_player_movement and current_position != player)
            or reader.i32(actor + 0x318) != local.context_a
            or reader.i32(actor + 0x254) != local.context_b
        ):
            raise SceneChanged("El personaje cambió durante la observación.")
    session.snapshot()
    if reader.u32(OWNER_ADDRESS) != owner or reader.i32(owner + 0xB98) != scene:
        raise SceneChanged("La escena cambió durante la observación.")
    return Observation(
        session.process.pid,
        session.creation_time,
        scene,
        player,
        state.auto_battle or state.hunting or state.files.marker_present,
        local,
        navigation,
    )


def scan_world(session: GameSession, *, allow_player_movement: bool = False) -> WorldView:
    """Read/rank candidate NPCs with no Auto Battle requirement and no game input."""
    session.snapshot()
    control_hunting(session.directory, "status")
    reader = Reader(session)
    owner = reader.u32(OWNER_ADDRESS)
    if not 0 < owner <= 0xFFFFFFFF - 0xBA0:
        raise DiagnosticError("El cliente todavía no publica una escena válida.")
    scene = reader.i32(owner + 0xB98)
    # This is the scene accepted by the captured world selector; other scenes are unvalidated.
    if scene != 2:
        return WorldView(None, (), scene)
    manager = reader.u32(owner + 0x828)
    if not manager:
        raise DiagnosticError("El cliente todavía no publica la tabla de personajes.")
    pointers = struct.unpack(f"<{SLOT_COUNT}I", reader.read(manager + TABLE_OFFSET, SLOT_COUNT * 4))
    active = ActiveIndex.read(reader, manager)
    player_actor = pointers[1]
    if 1 not in active.slots or not player_actor or reader.u32(player_actor + 0x200) != 1:
        raise DiagnosticError("No se pudo validar el personaje local en la tabla.")
    player = _grid(reader, player_actor)
    if player.map_id < 0:
        raise DiagnosticError("El personaje todavía no publica un mapa válido.")
    player_position = _world_position(reader, player_actor)
    limit = struct.unpack("<f", reader.read(0x045079EC, 4))[0]
    range_limit = limit if math.isfinite(limit) and 0 < limit <= 1e8 else None
    candidates = []
    errors = changed = 0
    rejected: dict[str, int] = {}

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    scoped = tuple(slot for slot in active.slots if 2 <= slot < SLOT_COUNT)
    for slot in scoped:
        actor = pointers[slot]
        if not actor:
            reject("missing_actor")
            continue
        try:
            if reader.u32(actor + 0x200) != slot:
                reject("slot_mismatch")
                continue
            identity = struct.unpack("<III", reader.read(actor + 0x204, 12))
            kind_id = identity[0]
            if not 3500 <= kind_id < 22000:
                reject("kind_range")
                continue
            if reader.byte(actor + 0x38) in (0x22, 0x23):
                reject("state")
                continue
            if reader.u32(actor + 0x388) & 0x810:
                reject("flag")
                continue
            if reader.i32(actor + 0x318) >= 0 or reader.i32(actor + 0x254) >= 0:
                reject("active_context")
                continue
            position = _grid(reader, actor)
            if position.map_id != player.map_id:
                reject("different_map")
                continue
            if reader.u32(manager + TABLE_OFFSET + slot * 4) != actor:
                changed += 1
                reject("pointer_changed")
                continue
            distance = abs(position.x - player.x) + abs(position.y - player.y)
            world_position = _world_position(reader, actor)
            squared = sum(
                (a - b) ** 2 for a, b in zip(player_position, world_position, strict=True)
            )
            candidates.append(
                Candidate(
                    slot,
                    kind_id,
                    position.map_id,
                    position.x,
                    position.y,
                    distance,
                    identity,
                    squared,
                )
            )
        except (DiagnosticError, OSError):
            errors += 1
            reject("read_error")
    session.snapshot()
    current_position = _grid(reader, player_actor)
    if (
        reader.u32(OWNER_ADDRESS) != owner
        or reader.i32(owner + 0xB98) != scene
        or reader.u32(owner + 0x828) != manager
    ):
        raise SceneChanged("La escena cambió durante la lectura; vuelve a consultar.")
    if ActiveIndex.read(reader, manager) != active:
        raise SceneChanged("Los índices activos cambiaron durante la lectura; actualiza.")
    if (
        reader.u32(manager + TABLE_OFFSET + 4) != player_actor
        or reader.u32(player_actor + 0x200) != 1
        or current_position.map_id != player.map_id
        or (not allow_player_movement and current_position != player)
    ):
        raise SceneChanged(
            "El personaje cambió de posición durante la lectura; vuelve a consultar."
        )
    return WorldView(
        player,
        tuple(sorted(candidates, key=lambda c: (c.grid_distance, c.slot))),
        scene,
        errors,
        changed,
        sum(bool(pointers[slot]) for slot in scoped),
        tuple(sorted(rejected.items())),
        len(active.slots),
        sum(bool(pointer) and slot not in scoped for slot, pointer in enumerate(pointers[2:], 2)),
        sum(slot >= SLOT_COUNT for slot in active.slots),
        range_limit,
    )
