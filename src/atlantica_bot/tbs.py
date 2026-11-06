"""Bounded, read-only research of the BF route; no TBS commands are executed."""

from __future__ import annotations

import hashlib
import io
import json
import struct
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from . import __version__
from .errors import DiagnosticError, SceneChanged
from .hunting import SUPPORTED_CLIENT_SHA256
from .session import GameSession
from .world import OWNER_ADDRESS, Reader

# Verified against loaded code in combat-20261103-232004 (all 37 block hashes checked).
# In particular, owner+16360 is NOT the receiver used by 008BC836: its +8 subobject is.
TBS_ANCHORS = (
    (0x008B0092, bytes.fromhex("8b8760630100518d4808e822c90000")),
    (0x008B8A48, bytes.fromhex("8d4e08895dfcc706b08d3604e83a660000")),
    (0x008BEF80, bytes.fromhex("8d8e50080000")),
    (
        0x008BC8AD,
        bytes.fromhex("8b872808000083782c00744c8b402c83b854020000007c4083be98070000037537"),
    ),
    (
        0x0052892C,
        bytes.fromhex(
            "8b510c85d274208b44240485c07c183b41087d1369c0b0330000"
            "83bc1094210000ff0f95c0eb0232c0c20400"
        ),
    ),
    (0x005220D6, bytes.fromhex("0fbf81a4210000c30fbf81a6210000c3")),
    (0x008AD25A, bytes.fromhex("c7063c803604")),
)
TBS_CODE_BLOCKS = (
    ("bf-context-dispatch", 0x00431000, 0x2000),
    ("bf-character-dispatch", 0x00435000, 0x2000),
    ("bf-grid-resolution", 0x004A1000, 0x2000),
    ("bf-common-actions", 0x00520000, 0x10000),
    ("bf-common-data", 0x00530000, 0x10000),
    ("bf-client-units", 0x008A8000, 0x8000),
    ("bf-client-actions", 0x008B0000, 0x10000),
    ("bf-client-controller", 0x008C0000, 0x10000),
    ("bf-interface-resolution", 0x00A55000, 0x2000),
    ("bf-common-tables", 0x042DE000, 0x2000),
    ("bf-client-tables", 0x04368000, 0x3000),
)
TBS_STAGES = {
    "map_before": "Mapa antes de entrar",
    "entered": "TBS: al entrar en la misión",
    "main_selected": "TBS: Main seleccionado",
    "before_move": "TBS: antes de mover una casilla",
    "after_move": "TBS: después de mover una casilla",
    "before_basic": "TBS: antes del ataque básico",
    "after_basic": "TBS: después del ataque básico",
    "before_magic": "TBS: antes de la magia",
    "after_magic": "TBS: después de la magia",
    "player_turn": "TBS: mi turno",
    "enemy_turn": "TBS: turno del enemigo",
    "mission_end": "TBS: resultado de la misión",
    "map_after": "Mapa después de salir",
}
MAX_UNITS = 512
MAX_SAMPLES = 32
UNIT_STRIDE = 0x33B0


def _binding(reader: Reader) -> tuple:
    owner = reader.u32(OWNER_ADDRESS)
    scene = reader.i32(owner + 0xB98)
    world = reader.u32(owner + 0x828)
    actor = reader.u32(world + 0x2C) if world else 0
    if not actor or reader.u32(actor + 0x200) != 1 or reader.u32(actor + 0x2C) != world:
        raise SceneChanged("El Main todavía no está disponible; espera a que termine la carga.")
    identity = struct.unpack("<3I", reader.read(actor + 0x204, 12))
    return (
        owner,
        scene,
        world,
        actor,
        identity,
        reader.i32(actor + 0x318),
        reader.i32(actor + 0x254),
        reader.u32(owner + 0x16360),
        reader.u32(actor + 0x30),
    )


def _controls(reader: Reader, common: int, pool: int) -> dict:
    # Names intentionally retain offsets until labelled TBS samples establish their semantics.
    return {
        "phase_798": reader.i32(common + 0x798),
        "selection_7b7": struct.unpack("<b", reader.read(common + 0x7B7, 1))[0],
        "selection_7b8": reader.i32(common + 0x7B8),
        "member_mapping_114": list(struct.unpack("<9i", reader.read(pool + 0x114, 36))),
        "selection_13c": reader.i32(pool + 0x13C),
        "selection_14c": reader.i32(pool + 0x14C),
    }


def _unit(reader: Reader, address: int, index: int, header: bytes, actor_word: int) -> dict:
    entry, owner_word, member = struct.unpack_from("<3i", header)
    row = {
        "index": index,
        "address": f"{address:08X}",
        "entry_2194": entry,
        "owner_word_2198": owner_word,
        "member_index_219c": member,
        "matches_local_identity_word": owner_word == actor_word,
        "table": f"{reader.u32(address):08X}",
    }
    if row["table"] != "0436803C":
        return {**row, "status": "unrecognized_unit_table"}
    row.update(
        {
            "status": "captured",
            "raw_21a0": list(header[12:14]),
            "raw_21a2": struct.unpack_from("<h", header, 14)[0],
            "grid_candidate": list(struct.unpack_from("<2h", header, 16)),
            "raw_21a8_to_21b8": list(struct.unpack_from("<5i", header, 20)),
            "raw_2038": reader.i32(address + 0x2038),
            "raw_2040": reader.i32(address + 0x2040),
            "raw_2ac8": reader.byte(address + 0x2AC8),
        }
    )
    info = reader.u32(address + 0x1FA8)
    if info:
        try:
            row["member_values_4c_50"] = list(struct.unpack("<2i", reader.read(info + 0x4C, 8)))
        except (DiagnosticError, OSError) as exc:
            row["member_values_unavailable"] = str(exc)
        if reader.u32(address + 0x1FA8) != info:
            raise SceneChanged("La información de una unidad cambió; vuelve a capturar.")
    return row


def capture_tbs_snapshot(session: GameSession) -> dict:
    """Observe candidates on either side of a manual action, without normal-battle APIs."""
    if session.creation_time is None:
        raise DiagnosticError("Conecta con una instancia identificada antes de capturar TBS.")
    state = session.snapshot()
    if state.auto_battle or state.hunting or state.files.marker_present:
        raise DiagnosticError("Captura TBS con Auto Battle y caza nativa apagados.")
    reader = Reader(session)
    for address, expected in TBS_ANCHORS:
        if reader.read(address, len(expected)) != expected:
            raise DiagnosticError("La ruta BF/TBS no coincide con el código analizado.")
    binding = _binding(reader)
    owner, scene, world, actor, identity, context_a, context_b, client, info = binding
    result = {
        "pid": session.process.pid,
        "creation_time": session.creation_time,
        "captured_at": datetime.now(UTC).isoformat(),
        "scene_code": scene,
        "local": {"identity": list(identity), "context_a": context_a, "context_b": context_b},
        "route": "bf_context_b_candidate"
        if context_b >= 0 and context_a < 0
        else "normal_context_a"
        if context_a >= 0 and context_b < 0
        else "map_candidate"
        if context_a < 0 and context_b < 0
        else "ambiguous_contexts",
        "tbs_mode_confirmed": False,
        "turn_state_verified": False,
        "grid_semantics_verified": False,
        "turn_execution_available": False,
        "writes_or_client_commands": False,
    }
    # This is the world-map position, not a demonstrated TBS cell.
    if info:
        result["world_grid"] = list(struct.unpack("<3h", reader.read(info + 0xCA, 6)))
    if context_b >= 0 and context_a < 0:
        result["bf"] = _read_bf(reader, client, identity[0])
    session.snapshot()
    if _binding(reader) != binding:
        raise SceneChanged("La escena o misión cambió durante la lectura; vuelve a capturar.")
    return result


def _read_bf(reader: Reader, client: int, actor_word: int) -> dict:
    if not client:
        return {"status": "unavailable", "reason": "bf_client_not_published"}
    common, pool = client + 8, client + 8 + 0x850
    tables = tuple(reader.u32(address) for address in (client, common, pool))
    result = {
        "client": f"{client:08X}",
        "common": f"{common:08X}",
        "pool": f"{pool:08X}",
        "tables": [f"{table:08X}" for table in tables],
    }
    if tables != (0x04368DB0, 0x043691DC, 0x04368C9C):
        return {**result, "status": "unrecognized_layout"}
    descriptor = reader.read(pool + 8, 8)
    count, base = struct.unpack("<iI", descriptor)
    controls = _controls(reader, common, pool)
    result.update({"capacity": count, "controls": controls, "units": []})
    if not 0 <= count <= 65536 or (count and not base):
        return {**result, "status": "invalid_collection"}
    if count and not 0 < base <= 0xFFFFFFFF - count * UNIT_STRIDE:
        return {**result, "status": "invalid_collection"}
    rows, unavailable, headers = [], [], []
    for index in range(min(count, MAX_UNITS)):
        address = base + index * UNIT_STRIDE
        try:
            header = reader.read(address + 0x2194, 40)
            headers.append((address, header))
            if struct.unpack_from("<i", header)[0] == -1:
                continue
            rows.append(_unit(reader, address, index, header, actor_word))
        except SceneChanged:
            raise
        except (DiagnosticError, OSError) as exc:
            unavailable.append({"index": index, "message": str(exc)})
    if (
        reader.read(pool + 8, 8) != descriptor
        or tuple(reader.u32(address) for address in (client, common, pool)) != tables
        or _controls(reader, common, pool) != controls
        or any(reader.read(address + 0x2194, 40) != header for address, header in headers)
    ):
        raise SceneChanged("Las unidades o la selección cambiaron; espera un momento y captura.")
    return {
        **result,
        "status": "partial" if unavailable else "captured",
        "units": rows,
        "unavailable_units": unavailable,
        "observed_entries": min(count, MAX_UNITS),
        "truncated": count > MAX_UNITS,
    }


def read_tbs_code(session: GameSession) -> tuple[list[tuple[str, int, bytes]], list[str]]:
    reader = Reader(session)
    blocks, unavailable = [], []
    for name, address, size in TBS_CODE_BLOCKS:
        try:
            data = reader.read(address, size)
            if not any(data):
                raise DiagnosticError("Bloque vacío")
            blocks.append((name, address, data))
        except (DiagnosticError, OSError):
            unavailable.append(name)
    session.snapshot()
    return blocks, unavailable


class TbsResearch:
    """A user-labelled sequence tied to a single process lifetime."""

    def __init__(self, pid: int, creation_time: int):
        if type(pid) is not int or pid <= 0 or type(creation_time) is not int or creation_time <= 0:
            raise DiagnosticError("Conecta con una instancia válida antes de capturar TBS.")
        self.pid, self.creation_time = pid, creation_time
        self.samples: list[dict] = []
        self.blocks: list[tuple[str, int, bytes]] = []
        self.unavailable_code: list[str] = []

    def add(self, stage: str, snapshot: dict, *, note: str = "") -> None:
        if stage not in TBS_STAGES or len(self.samples) >= MAX_SAMPLES or len(note) > 300:
            raise DiagnosticError(
                "Revisa la etapa y la nota; se permiten hasta 32 capturas por ZIP."
            )
        if (snapshot.get("pid"), snapshot.get("creation_time")) != (self.pid, self.creation_time):
            raise DiagnosticError("La captura pertenece a otra instancia; abre una captura nueva.")
        sample = {
            "stage": stage,
            "label_source": "user_reported",
            "note": note,
            "snapshot": snapshot,
        }
        payload = json.dumps(sample, ensure_ascii=False)
        if len(payload.encode()) > 512 * 1024:
            raise DiagnosticError("La muestra supera el límite del diagnóstico.")
        self.samples.append(json.loads(payload))

    def set_code(self, blocks: list[tuple[str, int, bytes]], unavailable: list[str]) -> None:
        whitelist = {(name, address): size for name, address, size in TBS_CODE_BLOCKS}
        keys = [(name, address) for name, address, _ in blocks]
        if (
            len(keys) != len(set(keys))
            or any(len(data) != whitelist.get((name, address)) for name, address, data in blocks)
            or any(name not in {row[0] for row in TBS_CODE_BLOCKS} for name in unavailable)
        ):
            raise DiagnosticError("Los bloques no pertenecen a la captura TBS permitida.")
        self.blocks = list(blocks)
        self.unavailable_code = list(unavailable)

    def export(self, destination: Path, *, mission: str, formation: str = "Solo Main") -> None:
        if not self.samples or destination.suffix.lower() != ".zip":
            raise DiagnosticError("Añade una captura y elige un archivo ZIP nuevo.")
        if len(mission) > 120 or len(formation) > 120:
            raise DiagnosticError(
                "El nombre de misión y la formación admiten hasta 120 caracteres."
            )
        manifest = {
            "schema_version": 1,
            "tool_version": __version__,
            "purpose": "tbs_memory_research",
            "client_sha256": SUPPORTED_CLIENT_SHA256,
            "pid_at_capture": self.pid,
            "instance_creation_time": self.creation_time,
            "created_at": datetime.now(UTC).isoformat(),
            "mission": mission.strip(),
            "formation": formation.strip(),
            "mission_and_formation_source": "user_reported",
            "samples": self.samples,
            "unavailable_code": self.unavailable_code,
            "tbs_mode_confirmed": False,
            "turn_execution_available": False,
            "writes_or_client_commands": False,
            "scope": "known_bf_fields_and_fixed_image_pages",
            "blocks": [
                {
                    "file": f"{name}_{address:08X}.bin",
                    "address": f"{address:08X}",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "kind": "readonly_constants" if address >= 0x03F85000 else "code",
                }
                for name, address, data in self.blocks
            ],
        }
        report = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        if len(report) > 8 * 1024 * 1024:
            raise DiagnosticError("El informe supera el límite del diagnóstico.")
        payload = io.BytesIO()
        with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", report)
            for entry, (_, _, data) in zip(manifest["blocks"], self.blocks, strict=True):
                archive.writestr(entry["file"], data)
        with destination.open("xb") as output:
            output.write(payload.getvalue())
