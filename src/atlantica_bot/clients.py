from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import DiagnosticError
from .hunting import HuntingResult, control_hunting
from .report import Process


@dataclass(frozen=True)
class ClientWindow:
    pid: int
    handle: int
    title: str
    thread_id: int | None = None

    @property
    def label(self) -> str:
        title = self.title.replace("\n", " ").replace("\r", " ")[:100]
        return f"PID {self.pid} · {title or 'Atlantica'} · ventana {self.handle:X}"


class ClientSystem(Protocol):
    def processes(self) -> list[Process]: ...
    def working_directory(self, pid: int) -> Path: ...


@dataclass(frozen=True)
class MarkerScope:
    sharing: tuple[int, ...]
    unknown: tuple[int, ...]

    @property
    def allowed(self) -> bool:
        return len(self.sharing) <= 1 and not self.unknown

    @property
    def explanation(self) -> str:
        if len(self.sharing) > 1:
            pids = ", ".join(map(str, self.sharing))
            return (
                f"Los PID {pids} comparten esta carpeta. HuntingMode.txt afecta a todos: "
                "Iniciar y Parar nativos están bloqueados. Puedes consultar solo el PID elegido."
            )
        if self.unknown:
            return (
                "No se pudo comprobar la carpeta de todos los clientes abiertos. "
                "Los cambios de HuntingMode.txt están bloqueados."
            )
        return "El marcador nativo pertenece a esta carpeta, no a un PID."


def marker_scope(system: ClientSystem, directory: Path) -> MarkerScope:
    directory = directory.resolve(strict=True)
    sharing, unknown = [], []
    for process in system.processes():
        if process.name.casefold() != "atlantica.exe":
            continue
        try:
            other = system.working_directory(process.pid).resolve(strict=True)
            if other.samefile(directory):
                sharing.append(process.pid)
        except (DiagnosticError, OSError):
            unknown.append(process.pid)
    return MarkerScope(tuple(sorted(sharing)), tuple(sorted(unknown)))


def control_native_marker(system: ClientSystem, directory: Path, action: str) -> HuntingResult:
    if action not in ("start", "stop", "status"):
        raise DiagnosticError("Acción del marcador no válida.")
    if action != "status":
        scope = marker_scope(system, directory)
        if not scope.allowed:
            raise DiagnosticError(scope.explanation)
    return control_hunting(directory, action)
