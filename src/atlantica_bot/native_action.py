from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .clients import ClientWindow
from .errors import DiagnosticError
from .hunting import control_hunting
from .ipc import BotLease, Cancellation
from .navigation import ApproachSettings
from .session import GameSession
from .world import Candidate, GridPosition, NavigationState

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
    13: "Solicitud cancelada antes de ejecutar la acción.",
    14: "No se pudo validar el control de parada; no se solicitó un ataque.",
    15: "El cliente aceptó una ruta de acercamiento; esperando el desplazamiento.",
    16: "El cliente desactivó el desplazamiento; esperando una posición estable.",
    17: "La ruta cambió fuera del bot; no se interrumpió ese movimiento.",
    18: "El objetivo o el personaje están fuera del radio de búsqueda.",
    19: "El objetivo ya está en alcance; se comprobará de nuevo antes de atacar.",
    20: "El personaje ya tiene un desplazamiento activo; no se sustituyó.",
    21: "No se confirmó el cambio de desplazamiento; comprueba el juego antes de reconectar.",
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
    session: GameSession,
    window: ClientWindow,
    candidate: Candidate,
    *,
    probe: bool = False,
    cancellation: Cancellation | None = None,
) -> dict:
    return _request(
        session, window, candidate, operation=0 if probe else 1, cancellation=cancellation
    )


def try_approach(
    session: GameSession,
    window: ClientWindow,
    candidate: Candidate,
    origin: GridPosition,
    settings: ApproachSettings,
    *,
    navigation: NavigationState,
    cancellation: Cancellation | None = None,
) -> dict:
    if not settings.enabled or not settings.contains(
        origin, GridPosition(candidate.map_id, candidate.x, candidate.y)
    ):
        raise DiagnosticError("El objetivo está fuera del radio de acercamiento configurado.")
    return _request(
        session,
        window,
        candidate,
        operation=2,
        origin=origin,
        radius=settings.radius,
        route=navigation,
        cancellation=cancellation,
    )


def stop_movement(session: GameSession, window: ClientWindow, route: NavigationState) -> dict:
    # A fresh cancellation channel lets cleanup stop a route after the run was cancelled.
    # The native guard compares actor, tick and destination before touching a live route.
    return _request(session, window, None, operation=3, route=route)


def _request(
    session: GameSession,
    window: ClientWindow,
    candidate: Candidate | None,
    *,
    operation: int,
    cancellation: Cancellation | None = None,
    origin: GridPosition | None = None,
    radius: int = 0,
    route: NavigationState | None = None,
) -> dict:
    with BotLease(session.process.pid):
        signal = cancellation or Cancellation(session.process.pid)
        try:
            return _try_action(
                session,
                window,
                candidate,
                operation=operation,
                cancellation=signal,
                origin=origin,
                radius=radius,
                route=route,
            )
        finally:
            if cancellation is None:
                try:
                    signal.cancel()
                finally:
                    signal.close()


def _try_action(
    session: GameSession,
    window: ClientWindow,
    candidate: Candidate | None,
    *,
    operation: int,
    cancellation: Cancellation | None,
    origin: GridPosition | None,
    radius: int,
    route: NavigationState | None,
) -> dict:
    """Issue one explicit request on the selected window's thread; never retry or move input."""
    if sys.platform != "win32":
        raise DiagnosticError("La prueba nativa se ejecuta en Windows.")
    state = session.snapshot()
    control_hunting(session.directory, "status")
    if state.auto_battle or state.hunting or state.files.marker_present:
        raise DiagnosticError("La prueba requiere Auto Battle y caza nativa desactivados.")
    if (
        session.creation_time is None
        or window.pid != session.process.pid
        or not window.handle
        or not window.thread_id
    ):
        raise DiagnosticError("La ventana no corresponde a la instancia conectada.")
    if candidate is not None and (not 2 <= candidate.slot < 450 or len(candidate.identity) != 3):
        raise DiagnosticError("Actualiza los candidatos antes de solicitar un ataque.")
    helper = bridge_path()
    if not helper.is_file() or not helper.with_name("AtlanticaHook.dll").is_file():
        raise DiagnosticError("Esta copia no contiene el puente Windows de 32 bits compilado.")
    args = [
        str(helper),
        ("--probe", "--attack", "--approach", "--stop-move")[operation],
        "--pid",
        str(window.pid),
        "--created",
        str(session.creation_time),
        "--window",
        str(window.handle),
        "--thread",
        str(window.thread_id),
    ]
    if candidate is not None:
        args.extend(
            (
                "--slot",
                str(candidate.slot),
                "--kind",
                str(candidate.identity[0]),
                "--serial",
                str(candidate.identity[1]),
                "--unique",
                str(candidate.identity[2]),
            )
        )
    if operation == 2:
        if origin is None or candidate is None or route is None:
            raise DiagnosticError(
                "Falta el punto de inicio o la revisión de ruta del acercamiento."
            )
        if (
            type(route.player_address) is not int
            or not 0 < route.player_address <= 0xFFFFFFFF
            or type(route.tick) is not int
            or not 0 <= route.tick <= 0xFFFFFFFF
            or route.active is not False
        ):
            raise DiagnosticError(
                "Actualiza la ruta del personaje antes de solicitar el acercamiento."
            )
        args.extend(
            (
                "--map",
                str(candidate.map_id),
                "--x",
                str(candidate.x),
                "--y",
                str(candidate.y),
                "--origin-map",
                str(origin.map_id),
                "--origin-x",
                str(origin.x),
                "--origin-y",
                str(origin.y),
                "--radius",
                str(radius),
                "--route-player",
                str(route.player_address),
                "--route-tick",
                str(route.tick),
            )
        )
    elif operation == 3:
        if route is None:
            raise DiagnosticError("Falta la ruta propia que se desea detener.")
        NavigationState.from_report(route.summary())
        args.extend(
            (
                "--map",
                str(route.map_id),
                "--x",
                str(route.x),
                "--y",
                str(route.y),
                "--route-tick",
                str(route.tick),
                "--route-player",
                str(route.player_address),
            )
        )
    if cancellation is not None:
        args.extend(("--cancel-event", cancellation.name))
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
        if report["pid"] != window.pid or report["slot"] != (candidate.slot if candidate else 0):
            raise ValueError("Respuesta de otra instancia")
        if report["thread_id"] != window.thread_id:
            raise ValueError("Respuesta de otro hilo de ventana")
        if type(report["operation"]) is not int or report["operation"] != operation:
            raise ValueError("Respuesta de otra operación")
        code = report["status"]
        if type(code) is not int or code not in RESULTS or type(report["thread_id"]) is not int:
            raise ValueError("Respuesta no válida")
        if code >= 15 and code not in (
            {15, 17, 18, 19, 20, 21}
            if operation == 2
            else {16, 17, 21}
            if operation == 3
            else set()
        ):
            raise ValueError("Resultado de otra operación")
        if code == 15:
            navigation = NavigationState.from_report(report["navigation"])
            if not navigation.active or (navigation.map_id, navigation.x, navigation.y) != (
                candidate.map_id,
                candidate.x,
                candidate.y,
            ):
                raise ValueError("Ruta de otro objetivo")
        if code == 16 and (
            report["navigation"]["active"] is not False
            or report["navigation"]["moving"] is not False
            or report["navigation"].get("active_raw") != 0
            or report["navigation"].get("moving_raw") != 0
        ):
            raise ValueError("La ruta sigue activa")
    except (ValueError, KeyError, TypeError) as exc:
        raise DiagnosticError(
            "El puente devolvió una respuesta no válida. No se reintenta."
        ) from exc
    report["message"] = RESULTS[code]
    report["battle_confirmed"] = False
    report["action"] = ("probe", "attack", "approach", "stop_movement")[operation]
    return report
