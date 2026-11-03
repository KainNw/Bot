from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .clients import ClientWindow
from .errors import DiagnosticError
from .hunting import control_hunting
from .session import GameSession
from .world import Candidate

RESULTS = {
    0: "Contexto comprobado; no se solicitó un ataque.",
    1: "El cliente encoló una solicitud de ataque. Comprueba el resultado en el juego.",
    2: "La comprobación nativa del cliente rechazó el objetivo o el estado actual.",
    3: "Objetivo fuera del alcance comprobado. Acércate manualmente antes de probar.",
    4: "El cliente no está en la escena de mapa identificada.",
    5: "Apaga Auto Battle y la caza nativa en este cliente antes de probar.",
    6: "La identidad del personaje o del objetivo cambió. Actualiza los candidatos.",
    7: "No se pudo validar la cola interna del cliente; no se solicitó el ataque.",
    8: "La cola del cliente no tiene espacio para la solicitud.",
    9: "El código o los métodos cargados no coinciden con la compilación analizada.",
    10: "El cliente produjo una excepción durante la prueba. No repitas la acción.",
    11: "No se confirmó que la solicitud se copiase a la cola del cliente.",
    12: "El umbral de alcance nativo no está validado; no se solicitó el ataque.",
}


def bridge_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)
        return root / "native" / "AtlanticaBridge.exe"
    return (
        Path(__file__).resolve().parents[2] / "build" / "native" / "Release" / "AtlanticaBridge.exe"
    )


def self_test_bridge() -> None:
    helper = bridge_path()
    result = subprocess.run(
        [str(helper), "--self-test"],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    try:
        report = json.loads(result.stdout)
        if result.returncode or report["status"] != 9 or not report["thread_id"]:
            raise ValueError("Prueba no válida")
    except (ValueError, KeyError, TypeError) as exc:
        raise DiagnosticError("Falló la prueba aislada del puente de Windows.") from exc


def try_attack(
    session: GameSession, window: ClientWindow, candidate: Candidate, *, probe: bool = False
) -> dict:
    """Issue one explicit request on the selected window's thread; never retry or move input."""
    if sys.platform != "win32":
        raise DiagnosticError("La prueba nativa se ejecuta en Windows.")
    state = session.snapshot()
    control_hunting(session.directory, "status")
    if state.auto_battle or state.hunting or state.files.marker_present:
        raise DiagnosticError("La prueba requiere Auto Battle y caza nativa desactivados.")
    if session.creation_time is None or window.pid != session.process.pid or not window.handle:
        raise DiagnosticError("La ventana no corresponde a la instancia conectada.")
    if not 2 <= candidate.slot < 450 or len(candidate.identity) != 3:
        raise DiagnosticError("Actualiza los candidatos antes de solicitar un ataque.")
    helper = bridge_path()
    if not helper.is_file() or not helper.with_name("AtlanticaHook.dll").is_file():
        raise DiagnosticError("Esta copia no contiene el puente Windows de 32 bits compilado.")
    args = [
        str(helper),
        "--probe" if probe else "--attack",
        "--pid",
        str(window.pid),
        "--created",
        str(session.creation_time),
        "--window",
        str(window.handle),
        "--slot",
        str(candidate.slot),
        "--kind",
        str(candidate.identity[0]),
        "--serial",
        str(candidate.identity[1]),
        "--unique",
        str(candidate.identity[2]),
    ]
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DiagnosticError(
            f"El PID {window.pid} no respondió. El resultado de la solicitud es desconocido; "
            "comprueba el juego antes de reconectar. No hubo reintentos."
        ) from exc
    except OSError as exc:
        raise DiagnosticError(
            f"No se pudo abrir el puente del PID {window.pid}. Comprueba los permisos."
        ) from exc
    if result.returncode:
        raise DiagnosticError(
            f"Puente del PID {window.pid}: código {result.returncode}. "
            "Comprueba la ventana y los permisos. El resultado no está confirmado; no se reintenta."
        )
    try:
        report = json.loads(result.stdout)
        if report["pid"] != window.pid or report["slot"] != candidate.slot:
            raise ValueError("Respuesta de otra instancia")
        code = report["status"]
        if type(code) is not int or code not in RESULTS or type(report["thread_id"]) is not int:
            raise ValueError("Respuesta no válida")
    except (ValueError, KeyError, TypeError) as exc:
        raise DiagnosticError(
            "El puente devolvió una respuesta no válida. No se reintenta."
        ) from exc
    report["message"] = RESULTS[code]
    report["battle_confirmed"] = False
    return report
