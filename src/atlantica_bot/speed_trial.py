from __future__ import annotations

import json
import math
import struct
import subprocess
import time
from dataclasses import asdict, dataclass

from . import __version__
from .battle import read_battle_frame
from .clients import ClientWindow
from .combat import CombatDetector
from .errors import DiagnosticError, WindowUnavailable
from .hunting import control_hunting
from .ipc import BotLease, Cancellation
from .native_action import bridge_path
from .session import GameSession
from .speed import read_speed_snapshot
from .world import observe_scene

ORIGINAL_RATE = 1.4
TRIAL_RATE = 1.45
TRIAL_SECONDS = 10
MESSAGES = {
    9: "El código del cliente no coincide; no se cambió la escala.",
    13: "Prueba cancelada antes del cambio.",
    14: "No se pudo validar la cancelación; no se cambió la escala.",
    38: "Escala 1,45 aplicada. Prueba una acción manual; se restaurará automáticamente.",
    39: "Escala original restaurada y comprobada en ambos campos.",
    40: "El contexto o sus valores cambiaron; no se sobrescribieron.",
    41: "El cliente no cumple las condiciones de la prueba; no se cambió la escala.",
    42: (
        "El juego sustituyó el objeto o su valor; "
        "se retiró la prueba sin sobrescribir el estado nuevo."
    ),
}


def float_bits(value: float) -> int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise DiagnosticError("La escala no es un número válido.")
    try:
        return struct.unpack("<I", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise DiagnosticError("La escala no cabe en el formato del cliente.") from exc


class SpeedResultUnknown(DiagnosticError):
    """The helper may have changed a rate; retain the plan for restoration."""


@dataclass(frozen=True)
class SpeedPlan:
    pid: int
    creation_time: int
    manager: int
    context: int
    player: int
    actor_identity: tuple[int, int, int]
    turn_number: int
    turn_tick: int
    table: int
    roots: tuple[tuple[int, int, int, int], tuple[int, int, int, int]]

    def binding(self) -> dict:
        return {
            "table": self.table,
            "roots": [list(root) for root in self.roots],
            "player": self.player,
            "manager": self.manager,
            "context": self.context,
            "turn_number": self.turn_number,
            "turn_tick": self.turn_tick,
            "actor_identity": list(self.actor_identity),
            "original_bits": float_bits(ORIGINAL_RATE),
            "requested_bits": float_bits(TRIAL_RATE),
        }

    def arguments(self) -> dict:
        return {
            "speed-table": self.table,
            **{
                f"speed-root{context}-{i}": root[i]
                for context, root in enumerate(self.roots)
                for i in range(4)
            },
            "speed-player": self.player,
            "speed-original-bits": float_bits(ORIGINAL_RATE),
            "speed-requested-bits": float_bits(TRIAL_RATE),
            "battle-manager": self.manager,
            "battle-context": self.context,
            "turn-number": self.turn_number,
            "turn-tick": self.turn_tick,
            **dict(
                zip(
                    ("actor-kind", "actor-serial", "actor-unique"), self.actor_identity, strict=True
                )
            ),
        }


def _roots(snapshot: dict) -> tuple:
    rates = snapshot["graphics_rates"]
    if rates.get("shared_receiver") is True:
        raise DiagnosticError("El mapa comparte la escala; prueba bloqueada.")
    getter = rates.get("getter", {})
    if (
        rates.get("status") != "read"
        or rates.get("shared_receiver") is not False
        or getter.get("status") != "resolved"
        or getter.get("offset") != 0x50
        or getter.get("format") != "<f"
        or getter.get("receiver_dereferences") != [0, 0x120]
    ):
        raise DiagnosticError("No se ha comprobado una escala gráfica separada del mapa.")
    result = []
    for index in ("0", "1"):
        item = rates["contexts"][index]
        bindings = item.get("receiver_bindings", [])
        if item["status"] != "read" or len(bindings) != 2:
            raise DiagnosticError("La cadena gráfica todavía no está resuelta.")
        node = bindings[0][1]
        if bindings[0][0] != item["backend"] or bindings[1] != (node + 0x120, item["receiver"]):
            raise DiagnosticError("La cadena gráfica cambió; vuelve a leer.")
        root = (item["wrapper"], item["backend"], node, item["receiver"])
        if any(type(value) is not int or not 0x10000 <= value <= 0xFFFFF000 for value in root):
            raise DiagnosticError("La cadena gráfica no tiene direcciones válidas.")
        result.append(root)
    if result[0][3] == result[1][3]:
        raise DiagnosticError("El mapa comparte la escala; prueba bloqueada.")
    return tuple(result)


def prepare_speed_plan(session: GameSession) -> tuple[SpeedPlan, dict]:
    state = session.snapshot()
    if state.auto_battle or state.hunting or state.files.marker_present:
        raise DiagnosticError("Deja Auto Battle y la caza nativa apagados para esta prueba.")
    frame = read_battle_frame(session)
    if frame.phase != 3 or frame.turn_number == 0xFFFFFFFF:
        raise DiagnosticError("Entra en combate antes de probar la escala.")
    snapshot = read_speed_snapshot(session, frame.context)
    try:
        roots = _roots(snapshot)
        manager = snapshot["fields"]["manager_rate_candidate"]
        graphics = snapshot["graphics_rates"]["contexts"]["1"]
        if manager["status"] != "read" or any(
            float_bits(item["value"]) != float_bits(ORIGINAL_RATE) for item in (manager, graphics)
        ):
            raise DiagnosticError("La prueba requiere escala original 1,4 en ambos campos.")
    except DiagnosticError as exc:
        exc.speed_snapshot = snapshot
        raise
    fresh = read_battle_frame(session)
    if fresh.context.binding() != frame.context.binding() or (
        fresh.phase,
        fresh.turn_number,
        fresh.turn_tick,
    ) != (frame.phase, frame.turn_number, frame.turn_tick):
        raise DiagnosticError("El combate cambió durante la lectura; vuelve a leer.")
    session.snapshot()
    ctx = frame.context
    return SpeedPlan(
        ctx.pid,
        ctx.creation_time,
        ctx.manager,
        ctx.context,
        ctx.actor,
        ctx.actor_identity,
        frame.turn_number,
        frame.turn_tick,
        snapshot["graphics_rates"]["table"],
        roots,
    ), snapshot


def request_speed(
    session: GameSession, window: ClientWindow, plan: SpeedPlan, *, restore: bool
) -> dict:
    if (
        (session.process.pid, session.creation_time, window.pid)
        != (plan.pid, plan.creation_time, plan.pid)
        or not window.handle
        or not window.thread_id
    ):
        raise DiagnosticError("La prueba pertenece a otra instancia o ventana.")
    if not restore:
        state = session.snapshot()
        control_hunting(session.directory, "status")
        if state.auto_battle or state.hunting or state.files.marker_present:
            raise DiagnosticError("Apaga Auto Battle y la caza nativa antes de probar.")
    helper = bridge_path()
    if not helper.is_file() or not helper.with_name("AtlanticaHook.dll").is_file():
        raise DiagnosticError("Falta el puente de Windows de esta versión.")
    operation = 12 if restore else 11
    with BotLease(plan.pid), Cancellation(plan.pid) as cancellation:
        args = [
            str(helper),
            "--speed-restore" if restore else "--speed-apply",
            "--pid",
            str(plan.pid),
            "--created",
            str(plan.creation_time),
            "--window",
            str(window.handle),
            "--thread",
            str(window.thread_id),
            "--cancel-event",
            cancellation.name,
        ]
        for name, value in plan.arguments().items():
            args.extend((f"--{name}", str(value)))
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
            raise SpeedResultUnknown(
                "El puente no respondió; el cambio de escala no está confirmado."
            ) from exc
        except OSError as exc:
            raise DiagnosticError("No se pudo abrir el puente de velocidad.") from exc
    if result.returncode == 20:
        reason = "unavailable"
        try:
            data = json.loads(result.stdout)
            if (
                isinstance(data, dict)
                and data.get("pid") == plan.pid
                and data.get("command_sent") is False
            ):
                candidate = data.get("reason")
                if type(candidate) is str and candidate in WindowUnavailable.REASONS:
                    reason = candidate
        except (ValueError, TypeError):
            pass
        raise WindowUnavailable(plan.pid, reason)
    if result.returncode:
        error = (
            DiagnosticError
            if result.returncode in (2, 3, 4, 21, 22, 23, 24, 25)
            else SpeedResultUnknown
        )
        raise error(f"Puente de velocidad: código {result.returncode}.")
    try:
        report = json.loads(result.stdout)
        if (report["pid"], report["thread_id"], report["operation"], report["slot"]) != (
            plan.pid,
            window.thread_id,
            operation,
            0,
        ) or any(type(report[key]) is not int for key in ("pid", "thread_id", "operation", "slot")):
            raise ValueError("Respuesta de otra ventana")
        speed = report["speed"]
        if not isinstance(speed, dict) or json.dumps(
            {key: speed.get(key) for key in plan.binding()}, sort_keys=True
        ) != json.dumps(plan.binding(), sort_keys=True):
            raise ValueError("Respuesta de otra lectura")
        status = report["status"]
        allowed = {9, 10, 11, 13, 14, 40, 41} | ({39, 42} if restore else {38})
        if type(status) is not int or status not in allowed:
            raise ValueError("Estado no válido")
        if status in (10, 11) or report.get("exception", 0):
            raise ValueError("Cambio no confirmado")
        if status in (38, 39, 42):
            map_owned = speed["map_owned_restore"]
            if type(map_owned) is not int or map_owned not in (0, 1) or map_owned and not restore:
                raise ValueError("Respuesta de otra restauración")
            if map_owned:
                if (float_bits(speed["map_before"]), float_bits(speed["map_after"])) != (
                    float_bits(TRIAL_RATE),
                    float_bits(ORIGINAL_RATE),
                ):
                    raise ValueError("No se restauró el campo propio que cambió de contexto")
            elif float_bits(speed["map_before"]) != float_bits(speed["map_after"]):
                raise ValueError("La escala del mapa cambió")
        if status in (38, 39):
            expected = float_bits(ORIGINAL_RATE if restore else TRIAL_RATE)
            if any(
                float_bits(speed[key]) != expected for key in ("after_manager", "after_graphics")
            ):
                raise ValueError("No se comprobó la escala esperada")
    except (KeyError, TypeError, ValueError, DiagnosticError) as exc:
        raise SpeedResultUnknown(
            "La respuesta de velocidad no es válida; conserva la restauración."
        ) from exc
    return {
        **report,
        "message": MESSAGES[status],
        "memory_change_confirmed": status == 38,
        "restoration_confirmed": status == 39,
        "control_retired": status == 42,
        "visual_speedup_confirmed": False,
    }


class SpeedExperiment:
    def __init__(self, session: GameSession, window: ClientWindow):
        self.session, self.window = session, window
        self.plan = None
        self.lease = None
        self.active = False
        self.deadline = None
        self.auto_restore_attempted = False
        self.detector = None
        self.report = {
            "tool_version": __version__,
            "pid": session.process.pid,
            "creation_time": session.creation_time,
            "trial_rate": TRIAL_RATE,
            "duration_seconds": TRIAL_SECONDS,
            "visual_speedup_confirmed": False,
        }

    def _release(self) -> None:
        if self.lease is not None:
            self.lease.__exit__(None, None, None)
            self.lease = None

    def start(self) -> dict:
        if self.active:
            raise DiagnosticError("Restaura la escala antes de otra prueba.")
        self.lease = BotLease(self.session.process.pid)
        self.lease.__enter__()
        try:
            plan, snapshot = prepare_speed_plan(self.session)
            self.plan = plan
            self.detector = CombatDetector(plan.pid, plan.creation_time, "local_context")
            self.report.update(plan=asdict(plan), before=snapshot)
            self.active = True  # Retain originals if the helper's answer is lost.
            try:
                result = request_speed(self.session, self.window, plan, restore=False)
            except SpeedResultUnknown as exc:
                self.report["apply_error"] = str(exc)
                self.auto_restore_attempted = True
                try:
                    self.restore()
                except DiagnosticError as cleanup:
                    self.report["restore_error"] = str(cleanup)
                raise
            except DiagnosticError:
                self.active = False
                raise
            self.report["apply"] = result
            if result["status"] == 38:
                self.deadline = time.monotonic() + TRIAL_SECONDS
                self.auto_restore_attempted = False
            else:
                self.active = False
            return result
        except DiagnosticError as exc:
            self.report["error"] = str(exc)
            if hasattr(exc, "speed_snapshot"):
                self.report["preview"] = exc.speed_snapshot
            raise
        finally:
            if not self.active:
                self._release()

    def restore(self) -> dict:
        if not self.active or self.plan is None:
            return self.report.get("restore", {})
        creation = getattr(self.session.system, "process_creation_time", None)
        ended = False
        if creation is not None:
            try:
                ended = creation(self.plan.pid) != self.plan.creation_time
            except (DiagnosticError, OSError):
                ended = not any(p.pid == self.plan.pid for p in self.session.system.processes())
        if ended:
            self.active = False
            self.deadline = None
            self._release()
            result = {
                "status": "instance_ended",
                "restoration_confirmed": False,
                "message": "La instancia terminó; no se modificó otro proceso.",
            }
            self.report["restore"] = result
            return result
        result = request_speed(self.session, self.window, self.plan, restore=True)
        self.report["restore"] = result
        if result["status"] not in (39, 42):
            raise DiagnosticError(result["message"] + " La restauración sigue pendiente.")
        self.active = False
        self.deadline = None
        self._release()
        return result

    def should_restore(self) -> bool:
        if not self.active or self.auto_restore_attempted:
            return False
        if self.deadline is None or time.monotonic() >= self.deadline:
            return True
        try:
            observation = observe_scene(self.session)
            return observation.native_active or self.detector.classify(observation) != "battle"
        except (DiagnosticError, OSError):
            return True
