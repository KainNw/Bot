from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from . import __version__
from .battle import BattleFrame, read_battle_frame
from .combat import CombatDetector
from .errors import DiagnosticError, SceneChanged
from .session import GameSession
from .world import Reader, observe_scene

BONUS_LABELS = {
    "exp": "EXP",
    "equipment": "Armas / equipamiento",
    "exp_books": "Libros de EXP",
    "control": "Sin bonus (control)",
}
# Fixed image pages containing the known search route and its string/property helpers.
BONUS_CODE_BLOCKS = (
    ("string-object-copy", 0x00409000, 0x1000),
    ("search-eligibility", 0x00433000, 0x2000),
    ("member-property-query", 0x00458000, 0x2000),
    ("battle-actions", 0x004F0000, 0x30000),
    ("battle-graphics", 0x00590000, 0x30000),
    ("battle-labels", 0x042D8000, 0x4000),
)
# Global property-key objects used by 00433701/004F1B21/005A2955. Do not follow their pointers.
PROPERTY_KEYS = (0x04C426E4, 0x04C427B4, 0x04C42F38, 0x06591D0C, 0x088AE52C)


def read_bonus_memory(session: GameSession, frame: BattleFrame) -> dict:
    """Read whitelisted fields for comparison; unclassified objects never become action targets."""
    reader = Reader(session)
    ctx = frame.context
    if (ctx.pid, ctx.creation_time) != (session.process.pid, session.creation_time):
        raise DiagnosticError("La lectura pertenece a otra instancia; vuelve a capturar.")
    client = ctx.client_object
    used = reader.read(client + 0xD4, 100)
    pointers = struct.unpack("<100I", reader.read(client + 0x138, 400))
    known = {unit.index: unit for unit in frame.units}
    errors = []

    def optional(name, address, size, fmt):
        try:
            values = struct.unpack(fmt, reader.read(address, size))
            return values[0] if len(values) == 1 else list(values)
        except (DiagnosticError, OSError, struct.error):
            errors.append(name)
            return None

    rows = []
    for index in range(1, 100):
        if used[index] != 1:
            continue
        pointer = pointers[index]
        row = {"index": index, "address": pointer, "in_normal_frame": index in known}
        rows.append(row)
        if not 0 < pointer <= 0xFFFFFFFF - 0x6B8:
            row["status"] = "invalid_pointer"
            continue
        header = optional(f"unit_{index}_header", pointer + 4, 8, "<ii")
        row.update(
            {
                "world_slot": header[0] if header else None,
                "member_index": header[1] if header else None,
                "flags": optional(f"unit_{index}_flags", pointer + 0x20, 4, "<I"),
                "action_state": optional(f"unit_{index}_state", pointer + 0x508, 1, "<B"),
                "search_effect_handles": optional(
                    f"unit_{index}_effect", pointer + 0x6B0, 8, "<2I"
                ),
            }
        )
        unit = known.get(index)
        if unit is not None:
            if unit.address != pointer or header != [unit.world_slot, unit.member_slot - 1]:
                raise SceneChanged("Las unidades cambiaron durante la captura del bonus.")
            row.update(
                {
                    "identity": list(unit.identity),
                    "kind_id": unit.kind_id,
                    "life": unit.life,
                    "group": unit.group,
                }
            )
    result = {
        "selected_action": optional("selected_action", ctx.manager + 0x25C4, 4, "<I"),
        "hover_action": optional("hover_action", ctx.manager + 0x25C8, 4, "<I"),
        "selected_unit_index": optional("selected_unit", client + 0xD0, 4, "<I"),
        "hover_unit_index": optional("hover_unit", client + 0xCC, 4, "<I"),
        "participant_identities": optional("participants", ctx.context + 0xB4, 72, "<18I"),
        "published_units": rows,
        "property_key_words": {
            f"{address:08X}": optional(f"property_{address:08X}", address, 52, "<13I")
            for address in PROPERTY_KEYS
        },
        "unavailable_fields": errors,
        "bonus_type_detected": False,
    }
    if reader.read(client + 0xD4, 100) != used or reader.read(client + 0x138, 400) != struct.pack(
        "<100I", *pointers
    ):
        raise SceneChanged("La colección cambió durante la captura del bonus; vuelve a capturar.")
    return result


def capture_bonus_snapshot(session: GameSession) -> dict:
    detector = CombatDetector.for_supported_session(session)
    before = observe_scene(session)
    classification = detector.classify(before)
    if before.native_active or classification not in ("map", "battle"):
        raise DiagnosticError(
            "Captura en el mapa o combate, con Auto Battle y caza nativa apagados."
        )
    snapshot = {
        "pid": session.process.pid,
        "creation_time": session.creation_time,
        "captured_at": datetime.now(UTC).isoformat(),
        "classification": classification,
        "observation": before.summary(),
    }
    if classification == "battle":
        frame = read_battle_frame(session)
        snapshot.update(
            {
                "binding": list(frame.context.binding()),
                "frame": frame.summary(),
                "memory": read_bonus_memory(session, frame),
            }
        )
        after_frame = read_battle_frame(session)
        if after_frame.context.binding() != frame.context.binding() or (
            after_frame.phase,
            after_frame.turn_number,
            after_frame.turn_tick,
        ) != (frame.phase, frame.turn_number, frame.turn_tick):
            raise SceneChanged("El combate cambió durante la captura del bonus; vuelve a capturar.")
    after = observe_scene(session)
    session.snapshot()
    if (after.pid, after.creation_time, detector.classify(after)) != (
        session.process.pid,
        session.creation_time,
        classification,
    ):
        raise SceneChanged("La escena cambió durante la captura del bonus; vuelve a capturar.")
    return json.loads(json.dumps(snapshot))


def read_bonus_code(session: GameSession) -> tuple[list[tuple[str, int, bytes]], list[str]]:
    blocks, errors = [], []
    for name, address, size in BONUS_CODE_BLOCKS:
        try:
            data = session.system.read_memory(session.process.pid, address, size)
            if len(data) != size or not any(data):
                raise DiagnosticError("Bloque incompleto")
            blocks.append((name, address, data))
        except (DiagnosticError, OSError):
            errors.append(name)
    session.snapshot()
    return blocks, errors


class BonusComparison:
    def __init__(self, pid: int, creation_time: int):
        if type(pid) is not int or pid <= 0 or type(creation_time) is not int or creation_time <= 0:
            raise DiagnosticError("Conecta con una instancia válida antes de comparar bonus.")
        self.pid, self.creation_time = pid, creation_time
        self.category = None
        self.before = self.after = None
        self.blocks = []
        self.code_errors = []
        self.user_result = None

    def _check(self, snapshot: dict) -> None:
        if (snapshot.get("pid"), snapshot.get("creation_time")) != (self.pid, self.creation_time):
            raise DiagnosticError("La captura pertenece a otra instancia; vuelve a conectar.")

    def set_before(self, category: str, snapshot: dict, blocks=(), code_errors=()) -> None:
        self._check(snapshot)
        if (
            type(category) is not str
            or category not in BONUS_LABELS
            or snapshot.get("classification") != "battle"
        ):
            raise DiagnosticError(
                "Elige el tipo que ves y captura mientras esté dentro del combate."
            )
        blocks = list(blocks)
        allowed = {(name, address, size) for name, address, size in BONUS_CODE_BLOCKS}
        if len({name for name, _, _ in blocks}) != len(blocks) or any(
            (name, address, len(data)) not in allowed or type(data) is not bytes
            for name, address, data in blocks
        ):
            raise DiagnosticError("La comparación solo admite los bloques de código definidos.")
        self.category, self.before, self.after = category, json.loads(json.dumps(snapshot)), None
        self.blocks, self.code_errors = blocks, list(code_errors)
        self.user_result = None

    def set_after(self, snapshot: dict, *, user_result: bool | None = None) -> None:
        self._check(snapshot)
        if user_result is not None and type(user_result) is not bool:
            raise DiagnosticError("Indica si viste la recogida o déjalo sin confirmar.")
        if self.before is None:
            raise DiagnosticError("Captura primero el bonus visible.")
        if snapshot.get("classification") == "battle":
            old, new = self.before["frame"], snapshot["frame"]
            if (
                snapshot["binding"] != self.before["binding"]
                or new["turn_number"] < old["turn_number"]
                or new["turn_number"] == old["turn_number"]
                and new["turn_tick"] != old["turn_tick"]
            ):
                raise DiagnosticError(
                    "El encuentro cambió; repite las dos capturas en la misma batalla."
                )
        elif snapshot.get("classification") != "map":
            raise DiagnosticError(
                "Espera a que la escena se estabilice antes de capturar después de X."
            )
        self.after = json.loads(json.dumps(snapshot))
        self.user_result = user_result

    def summary(self) -> dict:
        return {
            "tool_version": __version__,
            "schema_version": 1,
            "purpose": "bonus_memory_comparison",
            "pid": self.pid,
            "creation_time": self.creation_time,
            "category": self.category,
            "category_source": "user_reported",
            "bonus_type_detected": False,
            "collection_confirmed": False,
            "before_x": self.before,
            "after_x": self.after,
            "comparison_complete": self.after is not None,
            "collection_user_reported": self.user_result,
            "code_unavailable": self.code_errors,
            "scope": "known_battle_fields_and_fixed_image_pages",
            "writes_or_client_commands": False,
        }

    def export(self, destination: Path) -> None:
        if self.before is None or destination.suffix.lower() != ".zip":
            raise DiagnosticError("Captura el bonus visible y elige un archivo ZIP.")
        result = self.summary()
        result["blocks"] = [
            {
                "file": f"{name}_{address:08X}.bin",
                "address": f"{address:08X}",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, address, data in self.blocks
        ]
        payload = json.dumps(result, ensure_ascii=False, indent=2).encode()
        if len(payload) > 256 * 1024 or sum(len(data) for _, _, data in self.blocks) > 512 * 1024:
            raise DiagnosticError("La comparación supera el límite del diagnóstico.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, suffix=".zip", delete=False
            ) as handle:
                temporary = Path(handle.name)
            with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", payload)
                for entry, (_, _, data) in zip(result["blocks"], self.blocks, strict=True):
                    archive.writestr(entry["file"], data)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
