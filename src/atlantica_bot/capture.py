from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from . import __version__, hunting
from .errors import DiagnosticError
from .session import GameSession

# Fixed code-only regions for the one verified build, not arbitrary process-memory exports.
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
ANCHOR_ADDRESS = 0x0043CDA7
ANCHOR_BYTES = bytes.fromhex("68 08 64 2c 04")


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
    )
    payload = json.dumps({key: report[key] for key in allowed if key in report}, ensure_ascii=False)
    if len(payload.encode("utf-8")) > 128 * 1024:
        raise DiagnosticError("El contexto del bot supera el límite del diagnóstico.")
    return json.loads(payload)


def export_code_context(
    session: GameSession, destination: Path, *, bot_context: dict | None = None
) -> None:
    """Capture bounded code regions; never execute them or alter the client/markers."""
    if destination.suffix.lower() != ".zip":
        raise DiagnosticError("Elige un archivo ZIP para guardar el diagnóstico.")
    state = session.snapshot()  # Reject stale PID, changed directory or unreadable client state.
    hunting.control_hunting(session.directory, "status")  # Revalidate the supported disk build.
    context = _bot_context(session, bot_context)
    read = session.system.read_memory
    pid = session.process.pid
    if read(pid, ANCHOR_ADDRESS, len(ANCHOR_BYTES)) != ANCHOR_BYTES:
        raise DiagnosticError("El código cargado no coincide con el contexto analizado.")
    blocks = []
    for name, address, size in CODE_BLOCKS:
        data = read(pid, address, size)
        if len(data) != size:
            raise DiagnosticError(f"Lectura incompleta del bloque {name}.")
        if not any(data):
            raise DiagnosticError(f"El bloque {name} está vacío; no se puede analizar.")
        blocks.append((name, address, data))
    dispatch, dispatch_block = _dispatcher_context(session)
    if dispatch_block is not None:
        blocks.append(dispatch_block)
    session.snapshot()  # Do not label an export valid if the process exited during capture.
    manifest = {
        "schema_version": 2,
        "tool_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "client_sha256": hunting.SUPPORTED_CLIENT_SHA256,
        "process_name": session.process.name,
        "pid_at_capture": pid,
        "instance_creation_time": session.creation_time,
        "purpose": "attack_and_navigation_diagnostic",
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
            }
            for name, address, data in blocks
        ],
    }
    payload = io.BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, address, data in blocks:
            archive.writestr(f"{name}_{address:08X}.bin", data)
    # The complete payload is assembled before creating a file. Existing files are preserved.
    with destination.open("xb") as output:
        output.write(payload.getvalue())
