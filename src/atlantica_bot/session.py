from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .clients import control_native_marker
from .errors import DiagnosticError, SceneChanged
from .hunting import HuntingResult, control_hunting, marker_state
from .report import Module, Process, select_process


class LiveSystem(Protocol):
    def processes(self) -> list[Process]: ...
    def executable_path(self, pid: int) -> Path: ...
    def working_directory(self, pid: int) -> Path: ...
    def main_module(self, pid: int, name: str) -> Module: ...
    def read_memory(self, pid: int, address: int, size: int) -> bytes: ...


@dataclass(frozen=True)
class LiveState:
    auto_battle: bool
    condition_b: int
    hunting: bool
    files: HuntingResult

    @property
    def label(self) -> str:
        if not self.auto_battle:
            return "Auto Battle apagado"
        if self.condition_b <= 0:
            return "Caza bloqueada por el estado del cliente"
        if self.files.marker_present:
            return (
                "Caza habilitada en el cliente"
                if self.hunting
                else "Inicio solicitado; esperando al cliente"
            )
        return (
            "Parada solicitada; esperando al cliente"
            if self.hunting
            else "Parada confirmada por el cliente"
        )


@dataclass
class GameSession:
    system: LiveSystem
    process: Process
    executable: Path
    directory: Path
    creation_time: int | None = None

    @classmethod
    def connect(cls, system: LiveSystem, pid: int | None = None) -> GameSession:
        process = select_process(system.processes(), name="Atlantica.exe", pid=pid)
        executable = system.executable_path(process.pid).resolve(strict=True)
        directory = system.working_directory(process.pid).resolve(strict=True)
        if not (directory / "Atlantica.exe").samefile(executable):
            raise DiagnosticError(
                "La carpeta de trabajo no contiene el ejecutable del proceso elegido."
            )
        control_hunting(
            directory, "status"
        )  # Validate the exact supported build once on connection.
        module = system.main_module(process.pid, process.name)
        if module.base_address != 0x00400000:
            raise DiagnosticError("La base de este proceso no coincide con la sesión analizada.")
        mode = system.read_memory(process.pid, 0x042C3108, 6)
        if mode != "rt\0".encode("utf-16le"):
            raise DiagnosticError("El cliente todavía no tiene el código esperado cargado.")
        creation = getattr(system, "process_creation_time", None)
        session = cls(
            system, process, executable, directory, creation(process.pid) if creation else None
        )
        session.snapshot()
        return session

    def snapshot(self) -> LiveState:
        if self.creation_time is not None:
            if self.system.process_creation_time(self.process.pid) != self.creation_time:
                raise DiagnosticError("La instancia del cliente cambió; vuelve a conectar.")
        if self.system.executable_path(self.process.pid).resolve(strict=True) != self.executable:
            raise DiagnosticError("El proceso cambió; vuelve a conectar.")
        if self.system.working_directory(self.process.pid).resolve(strict=True) != self.directory:
            raise DiagnosticError("La carpeta del proceso cambió; vuelve a conectar.")
        read = self.system.read_memory
        owner = int.from_bytes(read(self.process.pid, 0x04A9290C, 4), "little")
        if not 0 < owner <= 0xFFFFFFFF - 0x1639C:
            raise SceneChanged("El cliente todavía no publica un estado válido.")
        auto = read(self.process.pid, owner + 0x16394, 1)[0]
        condition = int.from_bytes(
            read(self.process.pid, owner + 0x16398, 4), "little", signed=True
        )
        hunting = read(self.process.pid, 0x04E52C5A, 1)[0]
        if auto not in (0, 1) or hunting not in (0, 1):
            raise SceneChanged("Los indicadores del cliente no tienen los valores esperados.")
        if int.from_bytes(read(self.process.pid, 0x04A9290C, 4), "little") != owner:
            raise SceneChanged("El estado del cliente cambió durante la lectura.")
        return LiveState(bool(auto), condition, bool(hunting), marker_state(self.directory))

    def start(self) -> HuntingResult:
        state = self.snapshot()
        if not state.auto_battle:
            raise DiagnosticError("Activa Auto Battle desde el juego antes de iniciar la caza.")
        if state.condition_b <= 0:
            raise DiagnosticError("El estado del cliente no permite habilitar la caza ahora.")
        return control_native_marker(self.system, self.directory, "start")

    def stop(self) -> HuntingResult:
        self.snapshot()
        return control_native_marker(self.system, self.directory, "stop")
