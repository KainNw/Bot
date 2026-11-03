from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass, field

from .clients import ClientWindow
from .errors import DiagnosticError, SceneChanged
from .ipc import BotLease, Cancellation
from .native_action import try_attack
from .session import GameSession
from .world import Candidate, GridPosition, Observation, WorldView, observe_scene, scan_world


def target_key(candidate: Candidate) -> tuple:
    return candidate.slot, candidate.identity


@dataclass
class HuntEngine:
    pid: int
    creation_time: int
    running: bool = True
    phase: str = "waiting_map"
    message: str = "Esperando mapa."
    map_id: int | None = None
    anchor: GridPosition | None = None
    next_scan: float = 0
    resume_at: float = 0
    stable_samples: int = 0
    deadline: float | None = None
    cooldowns: dict = field(default_factory=dict)
    attempts: int = 0
    queued: int = 0
    battles: int = 0
    scans: int = 0
    transient_reads: int = 0
    needs_reconnect: bool = False
    last_attack: dict = field(default_factory=dict)

    def stop(self, reason: str, *, reconnect: bool = False) -> None:
        self.running = False
        self.phase = "stopped"
        self.message = reason
        self.needs_reconnect |= reconnect or self.deadline is not None

    def observe(self, observation: Observation, now: float) -> bool:
        """Return True only when a fresh world scan may select a new target."""
        if not self.running:
            return False
        if (observation.pid, observation.creation_time) != (self.pid, self.creation_time):
            self.stop("La instancia cambió; vuelve a conectar.", reconnect=True)
            return False
        if observation.native_active:
            self.stop("Se activó Auto Battle o caza nativa; bot detenido.")
            return False
        if observation.scene_code == 1:
            if self.phase != "battle":
                self.battles += 1
            if self.deadline is not None:
                self.last_attack = {
                    **self.last_attack,
                    "battle_confirmed": True,
                    "confirmation_scene": 1,
                }
            self.deadline = None
            self.phase, self.message = "battle", "Combate: solicitudes en pausa; juega los turnos."
            self.anchor = None
            return False
        if (
            observation.player is not None
            and self.map_id is not None
            and observation.player.map_id != self.map_id
        ):
            self.stop("Cambió el mapa; bot detenido.")
            return False
        if self.deadline is not None:
            if now >= self.deadline:
                self.stop(
                    "No se observó el combate tras la solicitud; detenido sin repetirla.",
                    reconnect=True,
                )
            else:
                self.phase, self.message = "waiting_battle", "Solicitud enviada; esperando combate."
            return False
        if observation.scene_code != 2 or observation.player is None:
            self.phase, self.message = "waiting_map", "Esperando una escena de mapa estable."
            self.anchor = None
            return False
        position = observation.player
        if self.map_id is None:
            self.map_id = position.map_id
        if position.map_id != self.map_id:
            self.stop("Cambió el mapa; bot detenido.")
            return False
        if self.phase in ("battle", "waiting_map", "resuming"):
            if self.anchor != position:
                self.anchor = position
                self.resume_at = now + 2
                self.stable_samples = 1
            else:
                self.stable_samples += 1
            self.phase, self.message = "resuming", "Esperando que el mapa se estabilice."
            if now < self.resume_at or self.stable_samples < 2:
                return False
            self.phase = "searching"
        elif self.anchor != position:
            self.stop("El personaje se movió; pulsa Iniciar bot cuando esté quieto.")
            return False
        if now < self.next_scan:
            return False
        self.next_scan = now + 1
        self.phase, self.message = "searching", "Buscando mobs cercanos."
        return True

    def select(self, view: WorldView, now: float) -> Candidate | None:
        if not self.running or self.deadline is not None or self.phase != "searching":
            return None
        self.scans += 1
        if view.scene_code != 2 or view.player != self.anchor:
            raise SceneChanged("La escena o posición cambió antes de seleccionar el objetivo.")
        limit = view.range_limit_squared
        if limit is None or not math.isfinite(limit) or not 0 < limit <= 1e8:
            self.stop("No se pudo validar el alcance nativo; bot detenido.", reconnect=True)
            return None
        self.cooldowns = {key: until for key, until in self.cooldowns.items() if until > now}
        for candidate in view.candidates:
            distance = candidate.distance_squared
            if (
                distance is not None
                and math.isfinite(distance)
                and 0 <= distance <= limit
                and len(candidate.identity) == 3
                and target_key(candidate) not in self.cooldowns
            ):
                self.phase, self.message = (
                    "requesting",
                    f"Solicitando ataque al objetivo {candidate.slot}.",
                )
                return candidate
        self.message = "Sin mobs cercanos disponibles; esperando."
        return None

    def record(self, candidate: Candidate, report: dict, now: float) -> None:
        if report.get("pid") != self.pid or report.get("slot") != candidate.slot:
            self.stop("Respuesta de otra instancia u objetivo; bot detenido.", reconnect=True)
            return
        self.attempts += 1
        self.last_attack = dict(report)
        code = report["status"]
        self.next_scan = now + 1.5
        if code == 1:
            self.queued += 1
            self.deadline = now + 10
            self.cooldowns[target_key(candidate)] = now + 10
            self.phase, self.message = "waiting_battle", "Solicitud enviada; esperando combate."
        elif code in (2, 3, 6):
            self.cooldowns[target_key(candidate)] = now + (10 if code == 2 else 3)
            self.phase, self.message = "searching", report["message"]
        elif code == 4:
            self.phase, self.message = "waiting_map", "La escena cambió; esperando al mapa."
            self.anchor = None
        elif code == 13:
            self.stop("Bot detenido; solicitud pendiente cancelada.")
        else:
            self.stop(report["message"], reconnect=code in (7, 9, 10, 11, 12, 14))

    def summary(self) -> dict:
        return {
            "pid": self.pid,
            "running": self.running,
            "phase": self.phase,
            "message": self.message,
            "scans": self.scans,
            "attempts": self.attempts,
            "queued": self.queued,
            "battles_observed": self.battles,
            "transient_reads": self.transient_reads,
            "needs_reconnect": self.needs_reconnect,
            "last_attack": dict(self.last_attack),
        }


class HuntWorker:
    def __init__(self, session: GameSession, window: ClientWindow):
        if session.creation_time is None or window.pid != session.process.pid:
            raise DiagnosticError("Conecta con una instancia de Windows válida antes de iniciar.")
        self.session, self.window = session, window
        self.engine = HuntEngine(session.process.pid, session.creation_time)
        self.events: queue.Queue[dict] = queue.Queue(maxsize=20)
        self.stop_event = threading.Event()
        self.cancellation: Cancellation | None = None
        self.thread = threading.Thread(
            target=self._run, name=f"AtlanticaBot-{window.pid}", daemon=True
        )

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    def start(self) -> None:
        try:
            self.thread.start()
        except RuntimeError as exc:
            self.engine.stop("No se pudo iniciar el hilo del bot.")
            raise DiagnosticError(self.engine.message) from exc

    def stop(self) -> None:
        self.stop_event.set()
        signal = self.cancellation
        if signal is not None:
            signal.cancel()

    def _publish(self) -> None:
        report = self.engine.summary()
        if self.events.full():
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
        self.events.put_nowait(report)

    def _run(self) -> None:
        try:
            with BotLease(self.window.pid), Cancellation(self.window.pid) as signal:
                self.cancellation = signal
                if self.stop_event.is_set():
                    self.cancellation.cancel()
                consecutive_changes = 0
                while not self.stop_event.is_set() and self.engine.running:
                    try:
                        observation = observe_scene(self.session)
                        if self.engine.observe(observation, time.monotonic()):
                            view = scan_world(self.session)
                            candidate = self.engine.select(view, time.monotonic())
                            if candidate is not None and not self.stop_event.is_set():
                                self._publish()
                                report = try_attack(
                                    self.session,
                                    self.window,
                                    candidate,
                                    cancellation=self.cancellation,
                                )
                                self.engine.record(candidate, report, time.monotonic())
                        consecutive_changes = 0
                    except SceneChanged:
                        self.engine.transient_reads += 1
                        consecutive_changes += 1
                        self.engine.message = (
                            "La escena cambió durante la lectura; esperando datos nuevos."
                        )
                        if consecutive_changes >= 3:
                            self.engine.stop("La escena no se estabiliza; bot detenido.")
                    self._publish()
                    self.stop_event.wait(0.5)
                if self.stop_event.is_set():
                    self.engine.stop("Bot detenido; no se enviarán más solicitudes.")
        except (DiagnosticError, OSError) as exc:
            self.engine.stop(str(exc), reconnect=True)
        except Exception as exc:
            self.engine.stop(
                f"Error interno del bot ({type(exc).__name__}); detenido.", reconnect=True
            )
        finally:
            self._publish()
