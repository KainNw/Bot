from __future__ import annotations

import json
import os
import platform
import struct
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from . import __version__
from .errors import DiagnosticError, NativeError
from .pe import inspect_executable


@dataclass(frozen=True)
class Process:
    pid: int
    name: str


@dataclass(frozen=True)
class Module:
    base_address: int
    image_size: int


class System(Protocol):
    def processes(self) -> list[Process]: ...

    def executable_path(self, pid: int) -> Path: ...

    def file_version(self, path: Path) -> str | None: ...

    def main_module(self, pid: int, name: str) -> Module: ...

    def read_memory(self, pid: int, address: int, size: int) -> bytes: ...


def select_process(processes: list[Process], *, name: str, pid: int | None) -> Process:
    if pid is not None:
        matches = [process for process in processes if process.pid == pid]
    else:
        matches = [process for process in processes if process.name.casefold() == name.casefold()]
    if not matches:
        target = f"PID {pid}" if pid is not None else name
        raise DiagnosticError(
            f"No se encontró {target}. Abre el juego y revisa el nombre del proceso."
        )
    if len(matches) > 1:
        choices = ", ".join(str(process.pid) for process in matches)
        raise DiagnosticError(
            f"Hay varios clientes abiertos (PID: {choices}). Elige uno con --pid."
        )
    return matches[0]


def diagnose(system: System, *, name: str, pid: int | None = None) -> dict:
    process = select_process(system.processes(), name=name, pid=pid)
    path = system.executable_path(process.pid)
    executable = inspect_executable(path)
    if executable.bits > struct.calcsize("P") * 8:
        raise DiagnosticError(
            "Este cliente necesita que ejecutes la herramienta con Python de 64 bits."
        )
    # Only report the basename: local account names and installation paths stay on the PC.
    report = {
        "schema_version": 1,
        "tool_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "python_bits": struct.calcsize("P") * 8,
        },
        "process": asdict(process),
        "executable_on_disk": {
            **asdict(executable),
            "file_version": system.file_version(path),
        },
        "main_module": None,
        "memory_read": {"status": "unavailable"},
        "game_mapping": "not_configured",
        "attack_automation": "not_exercised_by_diagnostic",
    }
    stage = "module_snapshot"
    try:
        module = system.main_module(process.pid, process.name)
        report["main_module"] = {
            "base_address": hex(module.base_address),
            "image_size": module.image_size,
        }
        stage = "header_read"
        signature = system.read_memory(process.pid, module.base_address, 2)
        if signature != b"MZ":
            raise DiagnosticError("La cabecera leída no corresponde a un módulo PE.")
        report["memory_read"] = {"status": "verified", "bytes_verified": 2}
    except DiagnosticError as exc:
        # Native failures may include private paths. Share only a fixed, non-sensitive status.
        report["memory_read"] = {
            "status": "unavailable",
            "reason": "No se pudo consultar el módulo o leer su cabecera.",
            "stage": stage,
        }
        if isinstance(exc, NativeError):
            report["memory_read"]["winerror"] = exc.code
    if system.executable_path(process.pid) != path:
        raise DiagnosticError("El proceso cambió durante el diagnóstico. Vuelve a ejecutarlo.")
    return report


def save_report(report: dict, path: Path) -> None:
    """Do not silently replace an earlier report or follow an existing symlink."""
    with path.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")


def self_test(system: System) -> None:
    """Exercise the native read path against a known buffer in this Python process."""
    import ctypes

    expected = b"Atlantica diagnostics self-test"
    buffer = ctypes.create_string_buffer(expected)
    actual = system.read_memory(os.getpid(), ctypes.addressof(buffer), len(expected))
    if actual != expected:
        raise DiagnosticError("La lectura de prueba devolvió datos distintos de los esperados.")
    own_process = select_process(system.processes(), name="", pid=os.getpid())
    path = system.executable_path(own_process.pid)
    inspect_executable(path)
    module = system.main_module(own_process.pid, own_process.name)
    if system.read_memory(own_process.pid, module.base_address, 2) != b"MZ":
        raise DiagnosticError("No se pudo validar la cabecera del proceso de prueba.")
