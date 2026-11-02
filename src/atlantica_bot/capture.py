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
)
ANCHOR_ADDRESS = 0x0043CDA7
ANCHOR_BYTES = bytes.fromhex("68 08 64 2c 04")


def export_code_context(session: GameSession, destination: Path) -> None:
    """Capture bounded code regions; never execute them or alter the client/markers."""
    if destination.suffix.lower() != ".zip":
        raise DiagnosticError("Elige un archivo ZIP para guardar el diagnóstico.")
    state = session.snapshot()  # Reject stale PID, changed directory or unreadable client state.
    hunting.control_hunting(session.directory, "status")  # Revalidate the supported disk build.
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
    session.snapshot()  # Do not label an export valid if the process exited during capture.
    manifest = {
        "schema_version": 1,
        "tool_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "client_sha256": hunting.SUPPORTED_CLIENT_SHA256,
        "process_name": session.process.name,
        "pid_at_capture": pid,
        "purpose": "static_analysis_of_manual_attack_candidates",
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
