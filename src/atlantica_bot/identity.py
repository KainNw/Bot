"""Read the local Main's display name using the captured character-name getter."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import DiagnosticError, SceneChanged
from .world import OWNER_ADDRESS, Reader

# 004352DB follows actor+30, adds 8 and enters 00435046. That getter returns
# (this+DC), so its returned name buffer is character_info+E4. Read the buffer;
# never call either routine or the helper called by the getter.
NAME_OFFSET = 0xE4
NAME_UNITS = 24
NAME_ANCHORS = (
    (0x004352DB, bytes.fromhex("8b413085c07501c38d4808e95bfdffff")),
    (0x00435046, bytes.fromhex("568db1dc000000566a1856e89e1a4d0083c40c8bc65ec3")),
    # This call supplies the Name:[%s] argument to the captured CharUnique log.
    (0x00436665, bytes.fromhex("e871ecffff50ffb608020000ffb6040200006830592c04")),
)


@dataclass(frozen=True)
class MainIdentity:
    pid: int
    creation_time: int
    actor: int
    actor_identity: tuple[int, int, int]
    name: str


def _pointer(value: int, size: int = 4) -> int:
    if value < 0x10000 or value > 0xFFFFFFFF - size + 1 or value % 4:
        raise SceneChanged("El personaje todavía no publica los datos de su nombre.")
    return value


def _binding(reader: Reader) -> tuple[int, ...]:
    owner = _pointer(reader.u32(OWNER_ADDRESS), 0xB9C)
    if reader.i32(owner + 0xB98) != 2:
        raise SceneChanged("Entra con tu personaje para leer el nombre del Main.")
    world = _pointer(reader.u32(owner + 0x828), 0x30)
    actor = _pointer(reader.u32(world + 0x2C), 0x214)
    if reader.u32(actor + 0x200) != 1 or reader.u32(actor + 0x2C) != world:
        raise SceneChanged("La identidad del Main no está disponible.")
    identity = struct.unpack("<III", reader.read(actor + 0x204, 12))
    if not identity[0] or not identity[1]:
        raise SceneChanged("La identidad del Main todavía está incompleta.")
    info = _pointer(reader.u32(actor + 0x30), NAME_OFFSET + NAME_UNITS * 2)
    return owner, world, actor, info, *identity


def _name(raw: bytes) -> str:
    if len(raw) != NAME_UNITS * 2:
        raise DiagnosticError("La lectura del nombre quedó incompleta.")
    units = struct.unpack(f"<{NAME_UNITS}H", raw)
    try:
        end = units.index(0)
        value = raw[: end * 2].decode("utf-16le", errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise DiagnosticError("El nombre del Main no tiene el formato esperado.") from exc
    if (
        not value
        or value != value.strip()
        or not value.isprintable()
        or not any(character.isalnum() for character in value)
    ):
        raise DiagnosticError("El cliente todavía no publica un nombre válido.")
    return value


def read_main_identity(session) -> MainIdentity:
    system = getattr(session, "system", None)
    creation = getattr(system, "process_creation_time", None)
    if not callable(creation) or type(session.creation_time) is not int:
        raise DiagnosticError("No se pudo verificar la instancia para leer el nombre.")
    pid = session.process.pid
    if creation(pid) != session.creation_time:
        raise SceneChanged("La instancia cambió durante la lectura del nombre.")
    reader = Reader(session)
    for address, expected in NAME_ANCHORS:
        if reader.read(address, len(expected)) != expected:
            raise DiagnosticError("La ruta del nombre no coincide con el cliente analizado.")
    before = _binding(reader)
    raw = reader.read(before[3] + NAME_OFFSET, NAME_UNITS * 2)
    second = reader.read(before[3] + NAME_OFFSET, NAME_UNITS * 2)
    if _binding(reader) != before or raw != second:
        raise SceneChanged("El personaje cambió mientras se leía su nombre.")
    name = _name(raw)
    if creation(pid) != session.creation_time:
        raise SceneChanged("La instancia cambió durante la lectura del nombre.")
    return MainIdentity(pid, session.creation_time, before[2], tuple(before[4:]), name)
