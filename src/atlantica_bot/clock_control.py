from __future__ import annotations

import json
import math
import os
import struct
import subprocess

from .errors import DiagnosticError
from .limits import SPEED_RATES
from .native_action import bridge_path

RATES = SPEED_RATES
TELEMETRY = struct.Struct("<8Ii8I")
REASONS = {
    0: "Sin activar",
    1: "Esperando combate",
    2: "En combate",
    3: "Regreso al mapa",
    4: "Cambio gráfico; esperando mapa",
    5: "Esperando un combate nuevo",
    6: "Límite de 60 s; esperando mapa",
    7: "Bot detenido",
    8: "Panel cerrado",
    9: "Lectura no disponible; desactivado",
    10: "El personaje cambió; desactivado",
    11: "Detenido",
}
REJECTED = {
    9: "El cliente no coincide con la compilación admitida.",
    13: "Inicio de velocidad cancelado.",
    14: "No se pudo abrir la cancelación de esta ejecución.",
    46: "Otro controlador de velocidad usa esa instancia.",
    47: "El cliente no está listo para activar la velocidad. Vuelve al mapa y prueba de nuevo.",
    48: (
        "Este cliente tiene los relojes de CE cargados. Cierra CE y reinicia el juego "
        "una vez para usar el speed del panel."
    ),
    49: "No se pudieron preparar los relojes. Reinicia el cliente antes de probar de nuevo.",
    50: (
        "Otra versión del panel dejó relojes cargados. "
        "Reinicia ese cliente para actualizar el Speed."
    ),
}


def bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def rate_from_bits(value: int) -> float:
    rate = struct.unpack("<f", struct.pack("<I", value))[0]
    if not math.isfinite(rate) or rate not in (1.0, *RATES):
        raise DiagnosticError("La tasa informada por el controlador no es válida.")
    return rate


class NativeClock:
    mode = "battle"
    start_argument = "--clock-start"
    start_operation = 13
    reason_labels = REASONS
    start_message = "Esperando combate"
    start_error = "No se confirmó el inicio en velocidad normal."

    @property
    def initial_rate(self) -> float:
        return 1.0

    def __init__(self, session, window, cancellation, rate: float):
        if type(rate) not in (float, int) or rate not in RATES:
            raise DiagnosticError("Elige una velocidad admitida para el combate.")
        self.session, self.window, self.signal, self.rate = session, window, cancellation, rate
        self.owner_pid = os.getpid()
        self.owner_created = session.system.process_creation_time(self.owner_pid)
        self.address = 0
        self.token = (0, 0)
        self.attempted = False
        self.stop_sent = False
        self.report = {
            "enabled": True,
            "mode": self.mode,
            "configured_rate": rate,
            "current_rate": 1.0,
            "armed": False,
            "message": "Preparando velocidad",
        }

    def _request(self, operation: str) -> dict:
        if (
            self.session.system.process_creation_time(self.session.process.pid)
            != self.session.creation_time
        ):
            raise DiagnosticError(
                "La instancia terminó o cambió; no se enviaron relojes a otro PID."
            )
        helper = bridge_path()
        args = [
            str(helper),
            self.start_argument if operation == "start" else "--clock-" + operation,
            "--pid",
            str(self.window.pid),
            "--created",
            str(self.session.creation_time),
            "--window",
            str(self.window.handle),
            "--thread",
            str(self.window.thread_id),
            "--cancel-event",
            self.signal.name,
            "--clock-owner-pid",
            str(self.owner_pid),
            "--clock-owner-created",
            str(self.owner_created),
            "--clock-rate-bits",
            str(bits(self.rate)),
        ]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DiagnosticError(
                "El puente de velocidad no respondió; se conserva la limpieza."
            ) from exc
        if result.returncode:
            raise DiagnosticError(f"Puente de velocidad: código {result.returncode}.")
        try:
            data = json.loads(result.stdout)
            if any(
                type(data[k]) is not int
                for k in ("pid", "status", "thread_id", "operation", "slot", "exception")
            ):
                raise ValueError
            expected = {"start": self.start_operation, "stop": 14, "status": 15}[operation]
            if (
                data["pid"],
                data["thread_id"],
                data["operation"],
                data["slot"],
                data["exception"],
            ) != (self.window.pid, self.window.thread_id, expected, 0, 0):
                raise ValueError
            clock = data["clock"]
            required = {
                "rate_bits",
                "owner_pid",
                "created_lo",
                "created_hi",
                "armed",
                "current_bits",
                "reason",
                "apply_count",
                "restore_count",
                "error",
                "view",
                "address",
                "token_lo",
                "token_hi",
            }
            if (
                not isinstance(clock, dict)
                or not required <= clock.keys()
                or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in clock.values())
            ):
                raise ValueError
            if (
                clock["owner_pid"],
                clock["created_lo"],
                clock["created_hi"],
                clock["rate_bits"],
            ) != (
                self.owner_pid,
                self.owner_created & 0xFFFFFFFF,
                self.owner_created >> 32,
                bits(self.rate),
            ):
                raise ValueError
            return data
        except (ValueError, KeyError, TypeError) as exc:
            raise DiagnosticError(
                "La respuesta de velocidad no corresponde a esta ejecución."
            ) from exc

    def start(self) -> None:
        self.attempted = True
        data = self._request("start")
        status = data["status"]
        if status != 43:
            if status in REJECTED:
                self.attempted = False
            self.report.update(
                current_rate=None, message=REJECTED.get(status, "Inicio sin confirmar")
            )
            raise DiagnosticError(
                REJECTED.get(status, "El inicio de velocidad no está confirmado.")
            )
        c = data["clock"]
        if c["armed"] != 1 or rate_from_bits(c["current_bits"]) != self.initial_rate:
            raise DiagnosticError(self.start_error)
        self.report.update(armed=True, message=self.start_message)
        self.address, self.token = c["address"], (c["token_lo"], c["token_hi"])
        if not 0x10000 <= self.address <= 0xFFFF0000 or not any(self.token):
            raise DiagnosticError("La dirección del control de velocidad no es válida.")
        self.read()

    def read(self) -> dict:
        system, pid = self.session.system, self.session.process.pid
        if system.process_creation_time(pid) != self.session.creation_time:
            raise DiagnosticError("La instancia del control de velocidad terminó.")
        if not self.address:
            return self.report
        before = system.read_memory(pid, self.address + 32, 4)
        raw = system.read_memory(pid, self.address, TELEMETRY.size)
        after = system.read_memory(pid, self.address + 32, 4)
        if len(raw) != TELEMETRY.size or len(before) != 4 or len(after) != 4:
            raise DiagnosticError("La lectura del estado de velocidad está incompleta.")
        values = TELEMETRY.unpack(raw)
        magic, version, target, owner, lo, hi, token_lo, token_hi, sequence = values[:9]
        armed, current, configured, reason, applied, restored, error, view = values[9:]
        if before != after or struct.pack("<i", sequence) != before or sequence & 1:
            return self.report
        if (magic, version, target, owner, lo | hi << 32, token_lo, token_hi) != (
            0x414F5031,
            1,
            pid,
            self.owner_pid,
            self.owner_created,
            *self.token,
        ):
            raise DiagnosticError("El estado de velocidad pertenece a otra ejecución.")
        if (
            armed not in (0, 1)
            or configured != bits(self.rate)
            or reason not in self.reason_labels
            or view > 4
        ):
            raise DiagnosticError("El estado de velocidad no es válido.")
        if system.process_creation_time(pid) != self.session.creation_time:
            raise DiagnosticError("La instancia cambió durante la lectura de velocidad.")
        self.report = {
            "enabled": True,
            "mode": self.mode,
            "configured_rate": self.rate,
            "current_rate": rate_from_bits(current),
            "armed": bool(armed),
            "message": self.reason_labels[reason],
            "reason": reason,
            "applications": applied,
            "restorations": restored,
            "error": error,
            "view": view,
        }
        return self.report

    def _instance_ended(self) -> bool:
        try:
            actual = self.session.system.process_creation_time(self.session.process.pid)
        except (DiagnosticError, OSError) as exc:
            if any(p.pid == self.session.process.pid for p in self.session.system.processes()):
                raise DiagnosticError(
                    "No se pudo verificar la instancia para restaurar velocidad."
                ) from exc
            actual = None
        if actual != self.session.creation_time:
            self.attempted = False
            self.report.update(armed=False, current_rate=None, message="La instancia terminó")
            return True
        return False

    def _confirm_response(self, data: dict, expected: int) -> bool:
        if data["status"] not in (expected, 46):
            raise DiagnosticError("La restauración de velocidad sigue pendiente.")
        if data["status"] == expected:
            if data["clock"]["armed"] != 0 or rate_from_bits(data["clock"]["current_bits"]) != 1.0:
                raise DiagnosticError("No se confirmó la vuelta a velocidad normal.")
        self.attempted = False
        self.report.update(
            armed=False,
            current_rate=1.0 if data["status"] == expected else None,
            message="Velocidad normal; detenido"
            if data["status"] == expected
            else "El control propio ya se retiró",
        )
        return True

    def stop(self) -> bool:
        if not self.attempted or self._instance_ended():
            return True
        if self.stop_sent:
            return self.confirm_stopped()
        # Send at most one stop command, even when its acknowledgement is lost.
        # Cancellation and the native watchdog remain responsible for restoration.
        self.stop_sent = True
        return self._confirm_response(self._request("stop"), 44)

    def confirm_stopped(self) -> bool:
        if not self.attempted or self._instance_ended():
            return True
        if self.address:
            try:
                report = self.read()
            except (DiagnosticError, OSError):
                pass
            else:
                if report.get("armed") is False and report.get("current_rate") == 1.0:
                    self.attempted = False
                    return True
        # Read-only status can recover a lost start/stop acknowledgement without
        # repeating a mutation or releasing another run's instance lease.
        return self._confirm_response(self._request("status"), 45)


class GeneralNativeClock(NativeClock):
    mode = "general"
    start_argument = "--clock-general-start"
    start_operation = 18
    reason_labels = REASONS | {12: "Speed general activo", 13: "Esperando datos del cliente; 1×"}
    start_message = "Speed general activo"
    start_error = "No se confirmó el inicio del Speed general."

    @property
    def initial_rate(self) -> float:
        return self.rate
