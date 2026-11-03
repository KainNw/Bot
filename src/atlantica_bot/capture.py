from __future__ import annotations

import hashlib
import io
import json
import struct
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from . import __version__, hunting
from .battle_context import NormalBattleContext, read_normal_battle
from .combat import CombatDetector
from .errors import DiagnosticError
from .session import GameSession
from .world import observe_scene

# Fixed regions of the verified executable image, never arbitrary heap-memory exports.
CODE_BLOCKS = (
    ("request-builder", 0x0040C000, 0x2000),
    ("character-dispatch", 0x00435000, 0x2000),
    ("target-selection", 0x0044C000, 0x2000),
    ("vector-helpers", 0x0043A000, 0x1000),
    ("identity-and-target-guards", 0x00433000, 0x2000),
    ("active-index", 0x00446000, 0x1000),
    ("target-command-validation", 0x00431000, 0x2000),
    ("send-buffer-pipeline", 0x009A1000, 0x5000),
    ("navigation-route", 0x0043B000, 0x4000),
    ("movement-dispatch", 0x00443000, 0x2000),
)
COMBAT_CODE_BLOCKS = (
    ("battle-character-actions", 0x00520000, 0x10000),
    ("battle-character-data", 0x00530000, 0x10000),
    ("member-info-manager", 0x004EC000, 0x4000),
    ("battle-selection", 0x00444000, 0x2000),
    # Direct dependencies found in the 0.8.0 battle capture, including the client
    # implementations instantiated by 00528B9D/00528BA2 and callbacks from common code.
    ("battle-character-client", 0x008A8000, 0x8000),
    ("battle-client-actions", 0x008B0000, 0x10000),
    ("battle-client-controller", 0x008C0000, 0x10000),
    ("battle-interface-resolution", 0x00A55000, 0x2000),
    ("battle-grid-resolution", 0x004A1000, 0x2000),
    ("character-property-flags", 0x00427000, 0x2000),
    ("member-properties", 0x00447000, 0x3000),
    ("battle-effect-query", 0x0044F000, 0x1000),
    ("magic-catalog", 0x00503000, 0x1000),
    ("magic-property-query", 0x008F8000, 0x6000),
    ("magic-policy", 0x00544000, 0x1000),
    # 00431769 indexes owner+091C by actor+0318 and calls 004FE29F.
    ("normal-battle-manager-and-members", 0x004F0000, 0x30000),
    # The normal-context cleanup calls 005A481F on owner+16358, not the BF object.
    ("normal-battle-client", 0x00590000, 0x30000),
)
COMBAT_READONLY_BLOCKS = (
    # Common character/manager method tables at 042DE14C/042DE770 and their strings.
    ("battle-method-tables-and-labels", 0x042DE000, 0x2000),
    ("normal-battle-labels", 0x042D8000, 0x4000),
)
ANCHOR_ADDRESS = 0x0043CDA7
ANCHOR_BYTES = bytes.fromhex("68 08 64 2c 04")
NORMAL_METHOD_LIMIT = 64
KNOWN_METHOD_COUNTS = {0x042D8AA4: 13}


def _normal_methods(
    session: GameSession, context: NormalBattleContext, blocks: list, *, role: str = "manager"
) -> dict:
    """Collect candidate methods from the normal manager and related client; never call them."""
    if role == "client" and context.method_table_candidate == 0x042D8AA4:
        return {"status": "unavailable", "reason": "normal_unit_collection_is_not_polymorphic"}
    table = (
        context.method_table_candidate
        if role == "manager"
        else context.client_method_table_candidate
    )
    if not 0x03F85000 <= table <= 0x044F9000 - 256:
        return {"status": "unavailable", "reason": "object_word_is_not_a_known_readonly_table"}
    reader = session.system.read_memory
    data = reader(session.process.pid, table, 256)
    if len(data) != 256:
        raise DiagnosticError("Lectura incompleta de los métodos del combate normal.")
    pointers = struct.unpack("<64I", data)
    if not all(0x00401000 <= address < 0x03F85000 for address in pointers[:3]):
        return {"status": "unavailable", "reason": "object_word_is_not_a_candidate_method_table"}
    prefix = f"normal-{role}"
    blocks.append((f"{prefix}-method-table", table, data))
    entries = []
    entry_limit = KNOWN_METHOD_COUNTS.get(table, NORMAL_METHOD_LIMIT)
    for offset, address in enumerate(pointers):
        if not 0x00401000 <= address < 0x03F85000:
            break
        if len(entries) == entry_limit:
            break
        existing = next(
            (name for name, start, code in blocks if start <= address < start + len(code)), None
        )
        if existing is None:
            start = address & ~0xFFF
            size = min(0x2000, 0x03F85000 - start)
            code = reader(session.process.pid, start, size)
            if len(code) != size or not any(code):
                raise DiagnosticError("Lectura incompleta de un método del combate normal.")
            existing = f"{prefix}-method-{offset:02d}"
            blocks.append((existing, start, code))
        entries.append({"offset": offset * 4, "address": f"{address:08X}", "block": existing})
    return {
        "status": "captured",
        "table_address": f"{table:08X}",
        "entries": entries,
        "entry_limit": entry_limit,
        "limit_reached": len(entries) == entry_limit,
        "boundary_source": "verified_table_end_before_utf16_label"
        if table in KNOWN_METHOD_COUNTS
        else "bounded_candidate_scan",
    }


def _dispatcher_context(session: GameSession) -> tuple[dict, tuple[str, int, bytes] | None]:
    read = session.system.read_memory
    pid = session.process.pid
    owner_data = read(pid, 0x04A9290C, 4)
    if len(owner_data) != 4:
        raise DiagnosticError("Lectura incompleta del objeto del cliente.")
    owner = int.from_bytes(owner_data, "little")
    if not 0 < owner <= 0xFFFFFFFF - 0xBA0:
        raise DiagnosticError("Objeto del cliente no válido para identificar el despachador.")
    context_data = read(pid, owner + 0xB98, 4)
    if len(context_data) != 4:
        raise DiagnosticError("Lectura incompleta del contexto del cliente.")
    context = {"owner_context_code": int.from_bytes(context_data, "little", signed=True)}
    table_data = read(pid, owner, 4)
    if len(table_data) != 4:
        raise DiagnosticError("Lectura incompleta de la tabla de métodos.")
    table = int.from_bytes(table_data, "little")
    if not 0x03F85000 <= table < 0x044F9000 - 0x68:
        return {
            **context,
            "status": "unavailable",
            "reason": "method_table_outside_known_readonly_section",
            "table_address": f"{table:08X}",
        }, None
    function_data = read(pid, table + 0x64, 4)
    if len(function_data) != 4:
        raise DiagnosticError("Lectura incompleta del método de envío.")
    function = int.from_bytes(function_data, "little")
    if not 0x00401000 <= function < 0x03F85000:
        return {
            **context,
            "status": "unavailable",
            "reason": "method_outside_known_code_section",
            "function_address": f"{function:08X}",
        }, None
    start = function & ~0xFFF
    size = min(0x2000, 0x03F85000 - start)
    data = read(pid, start, size)
    if len(data) != size or not any(data):
        raise DiagnosticError("El contexto del método de envío quedó incompleto.")
    if read(pid, 0x04A9290C, 4) != owner_data:
        raise DiagnosticError("El objeto del cliente cambió durante la lectura.")
    return {**context, "status": "captured", "function_address": f"{function:08X}"}, (
        "global-send",
        start,
        data,
    )


def _bot_context(session: GameSession, report: dict | None) -> dict | None:
    if report is None:
        return None
    if (
        report.get("pid") != session.process.pid
        or report.get("detector", {}).get("instance_creation_time") != session.creation_time
    ):
        raise DiagnosticError(
            "El informe del bot pertenece a otra instancia; no se mezclan capturas."
        )
    allowed = (
        "pid",
        "phase",
        "message",
        "running",
        "needs_reconnect",
        "detector",
        "scans",
        "attempts",
        "queued",
        "battles_observed",
        "last_attack",
        "range",
        "target_history",
        "native_attack",
        "first_observation",
        "recent_observations",
        "events",
        "pending_attack",
        "transport",
        "approach",
        "combat",
    )
    exported = {key: report[key] for key in allowed if key in report}
    if isinstance(exported.get("combat"), dict):
        exported["combat"] = {
            **exported["combat"],
            "roster": [
                {key: value for key, value in row.items() if key != "name"}
                for row in exported["combat"].get("roster", [])
            ],
        }
    payload = json.dumps(exported, ensure_ascii=False)
    if len(payload.encode("utf-8")) > 128 * 1024:
        raise DiagnosticError("El contexto del bot supera el límite del diagnóstico.")
    return json.loads(payload)


def export_code_context(
    session: GameSession,
    destination: Path,
    *,
    bot_context: dict | None = None,
    include_combat: bool = False,
) -> None:
    """Read bounded executable regions without executing code or changing the client."""
    if destination.suffix.lower() != ".zip":
        raise DiagnosticError("Elige un archivo ZIP para guardar el diagnóstico.")
    state = session.snapshot()  # Reject stale PID, changed directory or unreadable client state.
    hunting.control_hunting(session.directory, "status")  # Revalidate the supported disk build.
    context = _bot_context(session, bot_context)
    combat = None
    detector = None
    normal = None
    if include_combat:
        detector = CombatDetector.for_supported_session(session)
        before = observe_scene(session)
        if detector.classify(before) != "battle":
            raise DiagnosticError("Entra en combate antes de pulsar Exportar combate.")
        if before.native_active:
            raise DiagnosticError("Captura el combate con Auto Battle y caza nativa apagados.")
        combat = {"before": before.summary()}
        try:
            normal = read_normal_battle(session)
            combat["normal_combat"] = normal.summary()
        except (DiagnosticError, OSError) as exc:
            combat["normal_combat"] = {"status": "unavailable", "message": str(exc)}
    read = session.system.read_memory
    pid = session.process.pid
    if read(pid, ANCHOR_ADDRESS, len(ANCHOR_BYTES)) != ANCHOR_BYTES:
        raise DiagnosticError("El código cargado no coincide con el contexto analizado.")
    blocks = []
    selected = CODE_BLOCKS + (COMBAT_CODE_BLOCKS + COMBAT_READONLY_BLOCKS if include_combat else ())
    for name, address, size in selected:
        data = read(pid, address, size)
        if len(data) != size:
            raise DiagnosticError(f"Lectura incompleta del bloque {name}.")
        if not any(data):
            raise DiagnosticError(f"El bloque {name} está vacío; no se puede analizar.")
        blocks.append((name, address, data))
    dispatch, dispatch_block = _dispatcher_context(session)
    if dispatch_block is not None:
        blocks.append(dispatch_block)
    if normal is not None:
        combat["normal_method_resolution"] = _normal_methods(session, normal, blocks)
        combat["normal_client_method_resolution"] = _normal_methods(
            session, normal, blocks, role="client"
        )
    session.snapshot()  # Do not label an export valid if the process exited during capture.
    if detector is not None:
        after = observe_scene(session)
        if detector.classify(after) != "battle" or after.native_active:
            raise DiagnosticError("El combate cambió durante la captura; vuelve a exportarlo.")
        if normal is not None and read_normal_battle(session).binding() != normal.binding():
            raise DiagnosticError("El contexto del combate cambió durante la captura.")
        combat.update(
            {
                "after": after.summary(),
                "detector": detector.summary(),
                "scope": "normal_manager_and_related_client_code_dependencies",
                "turn_state_verified": False,
                "turn_execution_available": False,
                "reported_controls": {
                    "source": "user_reported",
                    "mercenary_selection": "1-9",
                    "basic_attack": "left_click",
                    "magic_shortcuts": list("QWERT"),
                    "loot": "X",
                },
            }
        )
    readonly_names = {name for name, _, _ in COMBAT_READONLY_BLOCKS} | {
        "normal-manager-method-table",
        "normal-client-method-table",
    }
    manifest = {
        "schema_version": 4 if include_combat else 2,
        "tool_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "client_sha256": hunting.SUPPORTED_CLIENT_SHA256,
        "process_name": session.process.name,
        "pid_at_capture": pid,
        "instance_creation_time": session.creation_time,
        "purpose": "battle_turn_diagnostic"
        if include_combat
        else "attack_and_navigation_diagnostic",
        "bot_context": context,
        "dispatch_resolution": dispatch,
        "state_at_start": {
            "auto_battle": state.auto_battle,
            "condition_b": state.condition_b,
            "hunting_flag": state.hunting,
        },
        "blocks": [
            {
                "file": f"{name}_{address:08X}.bin",
                "address": f"{address:08X}",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                **(
                    {"kind": "readonly_constants" if name in readonly_names else "code"}
                    if include_combat
                    else {}
                ),
            }
            for name, address, data in blocks
        ],
    }
    if combat is not None:
        manifest["combat"] = combat
    payload = io.BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, address, data in blocks:
            archive.writestr(f"{name}_{address:08X}.bin", data)
    # The complete payload is assembled before creating a file. Existing files are preserved.
    with destination.open("xb") as output:
        output.write(payload.getvalue())
