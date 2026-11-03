from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field

from .clients import ClientWindow
from .combat import CombatDetector
from .errors import DiagnosticError, SceneChanged
from .ipc import BotLease, Cancellation
from .native_action import (
    stop_movement,
    stop_native_pursuit,
    try_approach,
    try_attack,
    try_native_attack,
)
from .navigation import ApproachSettings
from .profiles import BotProfile
from .session import GameSession
from .world import (
    Candidate,
    GridPosition,
    NativePursuit,
    NavigationState,
    Observation,
    WorldView,
    observe_scene,
    observe_transport,
    scan_world,
)


def target_key(candidate: Candidate) -> tuple:
    # Active-table slots can be reused or reassigned between observations.
    return candidate.identity


def same_world_position(first: tuple | None, second: tuple | None) -> bool:
    if first is None or second is None:
        return first is second
    return sum((a - b) ** 2 for a, b in zip(first, second, strict=True)) <= 0.0001


@dataclass
class HuntEngine:
    pid: int
    creation_time: int
    detector: CombatDetector
    profile: BotProfile = field(default_factory=lambda: BotProfile.default(1))
    approach: ApproachSettings = field(default_factory=ApproachSettings)
    native_attack: bool = False
    running: bool = True
    phase: str = "waiting_map"
    message: str = "Esperando mapa."
    map_id: int | None = None
    anchor: GridPosition | None = None
    anchor_world_position: tuple[float, float, float] | None = None
    next_scan: float = 0
    resume_at: float = 0
    stable_samples: int = 0
    deadline: float | None = None
    cooldowns: dict = field(default_factory=dict)
    engaged_targets: dict[tuple[int, int, int], int] = field(default_factory=dict)
    attempts: int = 0
    queued: int = 0
    battles: int = 0
    scans: int = 0
    transient_reads: int = 0
    needs_reconnect: bool = False
    last_attack: dict = field(default_factory=dict)
    observation_count: int = 0
    scene_counts: dict[int, int] = field(default_factory=dict)
    classification_counts: dict[str, int] = field(default_factory=dict)
    observations: deque = field(default_factory=lambda: deque(maxlen=24))
    first_observation: dict = field(default_factory=dict)
    started_at: float | None = None
    battle_samples: int = 0
    battle_active: bool = False
    range_diagnostic: dict = field(default_factory=dict)
    origin: GridPosition | None = None
    route: NavigationState | None = None
    move_target: Candidate | None = None
    move_started: float = 0
    move_progress: float = 0
    move_position: GridPosition | None = None
    move_world_position: tuple[float, float, float] | None = None
    move_distance_squared: float | None = None
    move_reason: str = ""
    moves: int = 0
    arrivals: int = 0
    move_failures: int = 0
    last_move: dict = field(default_factory=dict)
    last_stop: dict = field(default_factory=dict)
    arrival_target: Candidate | None = None
    verify_arrival: bool = False
    selection_source: str = "nearby"
    pending_target: Candidate | None = None
    attack_queued_at: float | None = None
    trace_time: float = 0
    events: deque = field(default_factory=lambda: deque(maxlen=32))
    transport: deque = field(default_factory=lambda: deque(maxlen=12))
    transport_first: dict = field(default_factory=dict)
    last_failed_approach: dict = field(default_factory=dict)
    pursuit: NativePursuit | None = None
    pending_pursuit: NativePursuit | None = None
    pursuit_target: Candidate | None = None
    pursuit_started: float = 0
    pursuit_progress: float = 0
    pursuit_position: GridPosition | None = None
    pursuit_world_position: tuple[float, float, float] | None = None
    pursuit_update_at: float = 0
    pursuit_reason: str = ""
    native_requests: int = 0
    native_failures: int = 0
    last_native_request: dict = field(default_factory=dict)
    last_native_stop: dict = field(default_factory=dict)

    def _event(self, kind: str, now: float | None = None, **data) -> None:
        if now is not None:
            self.trace_time = now
        self.events.append(
            {
                "event": kind,
                "elapsed_seconds": round(self.trace_time - self.started_at, 3)
                if self.started_at is not None
                else None,
                **data,
            }
        )

    def __post_init__(self) -> None:
        if not self.detector.matches(self.pid, self.creation_time):
            raise DiagnosticError("Calibra el detector para esta instancia antes de iniciar.")
        self.profile.validate()
        if type(self.native_attack) is not bool or self.native_attack and self.approach.enabled:
            raise DiagnosticError("Elige ataque nativo o ruta del bot, no ambos.")

    @property
    def uses_radius(self) -> bool:
        return self.approach.enabled or self.native_attack

    def stop(self, reason: str, *, reconnect: bool = False) -> None:
        previous_phase = self.phase
        self.running = False
        self.phase = "stopped"
        self.message = reason
        self.needs_reconnect |= reconnect or self.deadline is not None
        self._event("stopped", reason=reason, previous_phase=previous_phase)

    def observe(self, observation: Observation, now: float) -> bool:
        """Return True only when a fresh world scan may select a new target."""
        if not self.running:
            return False
        classification = self.detector.classify(observation)
        if self.started_at is None:
            self.started_at = now
        self.trace_time = now
        self.observation_count += 1
        self.scene_counts[observation.scene_code] = (
            self.scene_counts.get(observation.scene_code, 0) + 1
        )
        self.classification_counts[classification] = (
            self.classification_counts.get(classification, 0) + 1
        )
        sample = {
            "elapsed_seconds": round(now - self.started_at, 3),
            "classification": classification,
            **observation.summary(),
        }
        if not self.first_observation:
            self.first_observation = sample
        self.observations.append(sample)
        if (observation.pid, observation.creation_time) != (self.pid, self.creation_time):
            self.stop("La instancia cambió; vuelve a conectar.", reconnect=True)
            return False
        if observation.native_active:
            self.stop("Se activó Auto Battle o caza nativa; bot detenido.")
            return False
        if self.pursuit is not None and classification != "battle":
            self.battle_samples = 0
            return self._observe_native_pursuit(observation, classification, now)
        if self.route is not None:
            return self._observe_movement(observation, classification, now)
        if classification == "battle":
            self.battle_samples += 1
            if self.battle_samples < 2:
                self.phase, self.message = "confirming_battle", "Comprobando la entrada en combate."
                self.anchor = None
                return False
            self.pending_pursuit = None
            if self.pursuit is not None:
                self._event("battle_during_native_pursuit", now, target=asdict(self.pursuit_target))
                self.cooldowns[target_key(self.pursuit_target)] = now + 30
                self.pursuit = self.pursuit_target = None
            if not self.battle_active:
                self.battles += 1
                self.battle_active = True
            if self.deadline is not None:
                if self.pending_target is not None:
                    self.engaged_targets[self.pending_target.identity] = self.pending_target.slot
                self.last_attack = {
                    **self.last_attack,
                    "battle_confirmed": True,
                    "confirmation_scene": observation.scene_code,
                    "confirmation_signal": self.detector.signal,
                }
                self._event(
                    "battle_confirmed",
                    now,
                    attempt=self.attempts,
                    target=asdict(self.pending_target) if self.pending_target else None,
                )
            self.deadline = None
            self.pending_target = None
            self.phase, self.message = "battle", "Combate: solicitudes en pausa; juega los turnos."
            self.anchor = None
            return False
        self.battle_samples = 0
        if (
            observation.player is not None
            and self.map_id is not None
            and observation.player.map_id != self.map_id
        ):
            self.stop("Cambió el mapa; bot detenido.")
            return False
        if self.deadline is not None:
            if now >= self.deadline:
                self._event(
                    "attack_not_confirmed",
                    now,
                    attempt=self.attempts,
                    target=asdict(self.pending_target) if self.pending_target else None,
                )
                self.stop(
                    "No se observó el combate tras la solicitud; detenido sin repetirla.",
                    reconnect=True,
                )
            else:
                self.phase, self.message = "waiting_battle", "Solicitud enviada; esperando combate."
            return False
        if classification != "map" or observation.player is None:
            self.phase, self.message = "waiting_map", "Esperando una escena de mapa estable."
            self.anchor = None
            return False
        position = observation.player
        if self.uses_radius and observation.world_position is None:
            self.stop("No se pudo comprobar la posición 3D del personaje.", reconnect=True)
            return False
        if (
            self.uses_radius
            and observation.navigation is not None
            and observation.navigation.active
        ):
            self.stop("Ya hay una ruta activa fuera del bot; detén al personaje antes de iniciar.")
            return False
        if self.map_id is None:
            self.map_id = position.map_id
            self.origin = position
        if position.map_id != self.map_id:
            self.stop("Cambió el mapa; bot detenido.")
            return False
        if (
            self.uses_radius
            and self.origin is not None
            and not self.approach.contains(self.origin, position)
        ):
            self.stop("Se alcanzó el límite del área de búsqueda; bot detenido.")
            return False
        if self.phase in ("battle", "confirming_battle", "waiting_map", "resuming"):
            if self.anchor != position or (
                self.uses_radius
                and not same_world_position(self.anchor_world_position, observation.world_position)
            ):
                self.anchor = position
                self.anchor_world_position = observation.world_position
                self.resume_at = now + 2
                self.stable_samples = 1
            else:
                self.stable_samples += 1
            self.phase, self.message = "resuming", "Esperando que el mapa se estabilice."
            if now < self.resume_at or self.stable_samples < 2:
                return False
            self.phase = "searching"
            self.battle_active = False
        elif self.anchor != position or (
            self.uses_radius
            and not same_world_position(self.anchor_world_position, observation.world_position)
        ):
            self.stop("El personaje se movió; pulsa Iniciar bot cuando esté quieto.")
            return False
        if now < self.next_scan:
            return False
        self.next_scan = now + 1
        self.phase, self.message = "searching", "Buscando mobs cercanos."
        return True

    def select(self, view: WorldView, now: float) -> Candidate | None:
        if self.running and self.pursuit is not None and self.phase == "native_pursuit":
            self.scans += 1
            return self._inspect_native_pursuit(view, now)
        if self.running and self.route is not None and self.phase == "approaching":
            self.scans += 1
            self._inspect_approach(view, now)
            return None
        if not self.running or self.deadline is not None or self.phase != "searching":
            return None
        self.scans += 1
        if view.scene_code != 2 or view.player != self.anchor:
            raise SceneChanged("La escena o posición cambió antes de seleccionar el objetivo.")
        if self.uses_radius and (
            view.player_world_position is None
            or not same_world_position(self.anchor_world_position, view.player_world_position)
        ):
            self.anchor = None
            self.phase, self.message = (
                "waiting_map",
                "Esperando que termine el desplazamiento real.",
            )
            self._event("position_not_settled", now, world_position=view.player_world_position)
            return None
        limit = view.range_limit_squared
        if limit is None or not math.isfinite(limit) or not 0 < limit <= 1e8:
            self.stop("No se pudo validar el alcance nativo; bot detenido.", reconnect=True)
            return None
        self.cooldowns = {key: until for key, until in self.cooldowns.items() if until > now}
        # Retain identities even if a defeated actor is filtered out or moves slots.
        # Only a complete active-identity scan can prove that an actor has left.
        if view.active_identities is not None:
            active = set(view.active_identities)
            self.engaged_targets = {
                identity: slot
                for identity, slot in self.engaged_targets.items()
                if identity in active
            }
        eligible = [
            candidate
            for candidate in view.candidates
            if candidate.identity not in self.engaged_targets
        ]
        available = []
        for candidate in eligible:
            distance = candidate.distance_squared
            if (
                distance is not None
                and math.isfinite(distance)
                and distance >= 0
                and (
                    self.native_attack
                    and self.origin is not None
                    and self.approach.contains(
                        self.origin, GridPosition(candidate.map_id, candidate.x, candidate.y)
                    )
                    or not self.native_attack
                    and distance <= limit
                )
                and len(candidate.identity) == 3
                and target_key(candidate) not in self.cooldowns
            ):
                available.append(candidate)
        measured = [
            candidate
            for candidate in eligible
            if candidate.distance_squared is not None
            and math.isfinite(candidate.distance_squared)
            and candidate.distance_squared >= 0
        ]
        nearest = min(measured, key=lambda candidate: candidate.distance_squared, default=None)
        self.range_diagnostic = {
            "limit_squared": limit,
            "nearest_slot": nearest.slot if nearest else None,
            "nearest_distance_squared": nearest.distance_squared if nearest else None,
            "available_in_range": sum(c.distance_squared <= limit for c in available),
            "available_in_search_radius": len(available) if self.native_attack else None,
            "excluded_previously_engaged": len(view.candidates) - len(eligible),
            "automatic_approach": self.approach.enabled,
            "native_attack": self.native_attack,
            "search_radius": self.approach.radius if self.uses_radius else None,
        }
        if self.arrival_target is not None:
            pinned = self.arrival_target
            candidate = next((c for c in available if target_key(c) == target_key(pinned)), None)
            self.arrival_target = None
            if candidate is None:
                reason = (
                    "target_missing_after_stop"
                    if not any(target_key(c) == target_key(pinned) for c in view.candidates)
                    else "target_left_range_after_stop"
                )
                if self.verify_arrival:
                    self.move_failures += 1
                    self.last_failed_approach = {"reason": reason, "target": asdict(pinned)}
                self.verify_arrival = False
                self.cooldowns[target_key(pinned)] = now + 3
                self._event("arrival_target_unavailable", now, reason=reason, target=asdict(pinned))
                self.message = "El objetivo cambió después de parar; consultando de nuevo."
                if self.move_failures >= 3:
                    self.stop(
                        "Tres acercamientos no completados; revisa el terreno antes de iniciar."
                    )
                return None
            if self.verify_arrival:
                self.arrivals += 1
                self._event("arrival_verified_after_route_finished", now, target=asdict(candidate))
            self.verify_arrival = False
            self.selection_source = "approach"
            self.phase, self.message = (
                "requesting",
                f"Solicitando ataque al objetivo {candidate.slot}.",
            )
            self._event(
                "target_selected",
                now,
                source="approach",
                target=asdict(candidate),
                player=asdict(view.player),
            )
            return candidate
        if not available:
            if self.approach.enabled and self.origin is not None:
                distant = [
                    candidate
                    for candidate in measured
                    if len(candidate.identity) == 3
                    and candidate.distance_squared > limit
                    and 0 < candidate.x <= 32767
                    and 0 < candidate.y <= 32767
                    and self.approach.contains(
                        self.origin, GridPosition(candidate.map_id, candidate.x, candidate.y)
                    )
                    and target_key(candidate) not in self.cooldowns
                ]
                if distant:
                    candidate = min(distant, key=lambda candidate: candidate.distance_squared)
                    self.phase = "requesting_approach"
                    self.message = f"Solicitando acercamiento al objetivo {candidate.slot}."
                    self._event(
                        "approach_target_selected",
                        now,
                        target=asdict(candidate),
                        player=asdict(view.player),
                    )
                    return candidate
            self.message = (
                "Los mobs ya combatidos siguen visibles; buscando otros objetivos."
                if view.candidates and not eligible
                else "Sin objetivos disponibles dentro del radio de búsqueda."
                if self.uses_radius
                else "Los mobs están fuera de alcance. Para el bot y acércate antes de iniciar."
                if nearest and nearest.distance_squared > limit
                else "Sin mobs cercanos disponibles; esperando."
            )
            return None
        candidate = min(
            available,
            key=lambda candidate: (
                (candidate.grid_distance, candidate.distance_squared, candidate.slot)
                if self.native_attack
                else (candidate.distance_squared,)
            ),
        )
        self.selection_source = "native_radius" if self.native_attack else "nearby"
        self.phase, self.message = (
            "requesting_native_attack" if self.native_attack else "requesting",
            f"Solicitando ataque al objetivo {candidate.slot}.",
        )
        self._event(
            "target_selected",
            now,
            source=self.selection_source,
            target=asdict(candidate),
            player=asdict(view.player),
        )
        return candidate

    def _observe_native_pursuit(
        self,
        observation: Observation,
        classification: str,
        now: float,
    ) -> bool:
        position, navigation = observation.player, observation.navigation
        if classification != "map" or position is None or observation.world_position is None:
            self.stop("Cambió el estado durante la persecución nativa.", reconnect=True)
            return False
        if (
            navigation is None
            or navigation.player_address != self.pursuit.player_address
            or observation.native_goal != self.pursuit.world_goal
            or navigation.active
        ):
            self._event("native_pursuit_ownership_lost", now, pursuit=self.pursuit.summary())
            self.pursuit = self.pursuit_target = None
            self.stop("El destino cambió fuera del bot; detenido sin modificarlo.")
            return False
        if self.origin is None or not self.approach.contains(self.origin, position):
            self.pursuit_reason = "outside_area"
        elif now - self.pursuit_started >= self.approach.timeout:
            self.pursuit_reason = "timeout"
        else:
            if position != self.pursuit_position or not same_world_position(
                self.pursuit_world_position,
                observation.world_position,
            ):
                self.pursuit_position, self.pursuit_progress = position, now
                self.pursuit_world_position = observation.world_position
            if now - self.pursuit_progress >= self.approach.stall_timeout:
                self.pursuit_reason = "stalled"
        if self.pursuit_reason:
            self.phase, self.message = (
                "stopping_native_pursuit",
                "Deteniendo la persecución nativa.",
            )
            return False
        self.phase, self.message = (
            "native_pursuit",
            f"El cliente se acerca al objetivo {self.pursuit_target.slot}.",
        )
        if now < self.next_scan:
            return False
        self.next_scan = now + 0.5
        return True

    def _inspect_native_pursuit(self, view: WorldView, now: float) -> Candidate | None:
        if view.scene_code != 2 or view.player is None or view.player.map_id != self.map_id:
            raise SceneChanged("Cambió el mapa durante la persecución nativa.")
        target = next(
            (c for c in view.candidates if target_key(c) == target_key(self.pursuit_target)),
            None,
        )
        if target is None:
            self.pursuit_reason = "target_changed"
        elif not self.approach.contains(
            self.origin,
            GridPosition(target.map_id, target.x, target.y),
        ):
            self.pursuit_reason = "target_left_area"
        else:
            limit = view.range_limit_squared
            if limit is None or not math.isfinite(limit) or not 0 < limit <= 1e8:
                self.stop("No se pudo validar el alcance nativo.", reconnect=True)
                return None
            self.pursuit_target = target
            self.range_diagnostic = {
                "limit_squared": limit,
                "native_attack": True,
                "target_slot": target.slot,
                "target_distance_squared": target.distance_squared,
                "search_radius": self.approach.radius,
            }
            moved = abs(target.x - self.pursuit.x) + abs(target.y - self.pursuit.y) > 2
            if (
                target.distance_squared is not None
                and now >= self.pursuit_update_at
                and (target.distance_squared <= limit or moved)
            ):
                self.selection_source = "native_pursuit"
                self.phase = "requesting_native_attack"
                return target
        if self.pursuit_reason:
            self.phase, self.message = (
                "stopping_native_pursuit",
                "El objetivo cambió; deteniendo la persecución.",
            )
        return None

    def record_native(self, candidate: Candidate, report: dict, now: float) -> None:
        if report.get("pid") != self.pid or report.get("slot") != candidate.slot:
            self.stop("Respuesta nativa de otra instancia u objetivo.", reconnect=True)
            return
        self.last_native_request = dict(report)
        self._event("native_attack_result", now, target=asdict(candidate), report=dict(report))
        code = report.get("status")
        if code == 22:
            pursuit = NativePursuit.from_report(report["pursuit"])
            if pursuit.map_id != self.map_id:
                self.stop("La persecución pertenece a otro mapa.", reconnect=True)
                return
            if self.pursuit is None:
                self.pursuit_started = self.pursuit_progress = now
                self.pursuit_position = self.anchor
                self.pursuit_world_position = self.anchor_world_position
            self.pursuit, self.pursuit_target = pursuit, candidate
            self.pursuit_update_at = now + 2
            self.pursuit_reason = ""
            self.native_requests += 1
            self.phase, self.message = "native_pursuit", report["message"]
            return
        if code == 1:
            self.pending_pursuit = self.pursuit
        if code in (1, 20, 24):
            self.pursuit = self.pursuit_target = None
        self.record(candidate, report, now)
        if self.pursuit is not None and self.running:
            self.pursuit_reason = "target_rejected"
            self.phase = "stopping_native_pursuit"

    def record_native_stop(self, report: dict, now: float, *, cleanup: bool = False) -> None:
        self.last_native_stop = dict(report)
        self._event("native_pursuit_stop", now, reason=self.pursuit_reason, report=dict(report))
        if report.get("pid") != self.pid or report.get("status") not in (23, 25):
            self.stop(
                f"Parada nativa sin confirmar. {report.get('message', '')}",
                reconnect=report.get("status") != 24,
            )
            return
        if self.pursuit_target is not None:
            self.cooldowns[target_key(self.pursuit_target)] = now + 30
        self.pursuit = self.pursuit_target = None
        self.pending_pursuit = None
        self.anchor = None
        if cleanup and report.get("status") == 23:
            self.message += " Parada nativa enviada; espera a que el personaje se detenga."
        if not cleanup:
            self.native_failures += int(report.get("status") != 25)
            if self.pursuit_reason == "outside_area" or self.native_failures >= 3:
                self.stop("Persecución detenida por el área o tres intentos no completados.")
            else:
                self.phase, self.message = "waiting_map", "Esperando que el personaje se detenga."

    def _observe_movement(self, observation: Observation, classification: str, now: float) -> bool:
        position, navigation = observation.player, observation.navigation
        if classification != "map" or position is None or observation.world_position is None:
            self.stop("Cambió el estado durante el acercamiento; bot detenido.", reconnect=True)
            return False
        if self.origin is None or not self.approach.contains(self.origin, position):
            self.move_reason = "outside_area"
        elif navigation is None:
            self.stop("No se pudo leer el desplazamiento; bot detenido.", reconnect=True)
            return False
        elif navigation.player_address != self.route.player_address:
            self.stop(
                "Cambió el personaje durante el acercamiento; vuelve a conectar.", reconnect=True
            )
            return False
        elif navigation.key != self.route.key:
            if navigation.active is False and navigation.moving is False:
                self.move_reason = "route_finished"
            else:
                self.stop("El movimiento cambió fuera del bot; detenido sin sustituirlo.")
                return False
        elif navigation.active is False and navigation.moving is False:
            self.move_reason = "route_finished"
        elif now - self.move_started >= self.approach.timeout:
            self.move_reason = "timeout"
        else:
            if position != self.move_position or not same_world_position(
                self.move_world_position, observation.world_position
            ):
                self.move_position, self.move_progress = position, now
                self.move_world_position = observation.world_position
            if now - self.move_progress >= self.approach.stall_timeout:
                self.move_reason = "stalled"
        if self.move_reason:
            self.phase, self.message = (
                "stopping_move",
                "Comprobando el fin del recorrido."
                if self.move_reason == "route_finished"
                else "Deteniendo el acercamiento.",
            )
            return False
        self.phase, self.message = (
            "approaching",
            f"Acercándose al objetivo {self.move_target.slot}.",
        )
        if now < self.next_scan:
            return False
        self.next_scan = now + 0.5
        return True

    def _inspect_approach(self, view: WorldView, now: float) -> None:
        if view.scene_code != 2 or view.player is None or view.player.map_id != self.map_id:
            raise SceneChanged("Cambió el mapa durante el acercamiento.")
        limit = view.range_limit_squared
        if limit is None or not math.isfinite(limit) or not 0 < limit <= 1e8:
            self.stop("No se pudo validar el alcance durante el acercamiento.", reconnect=True)
            return
        target = next(
            (
                candidate
                for candidate in view.candidates
                if target_key(candidate) == target_key(self.move_target)
            ),
            None,
        )
        self.move_distance_squared = target.distance_squared if target else None
        if target is None:
            self.move_reason = "target_changed"
        elif abs(target.x - self.route.x) + abs(target.y - self.route.y) > 4:
            self.move_reason = "target_moved"
        else:
            # Being inside the attack radius does not mean that navigation or the
            # current movement segment has finished. Let the client's route end.
            self.move_target = target
        if self.move_reason:
            self.phase, self.message = "stopping_move", "Parando antes de comprobar el ataque."

    def record_approach(self, candidate: Candidate, report: dict, now: float) -> None:
        self.last_move = dict(report)
        self._event("approach_result", now, target=asdict(candidate), report=dict(report))
        if report.get("pid") != self.pid or report.get("slot") != candidate.slot:
            self.stop("Respuesta de acercamiento de otra instancia; detenido.", reconnect=True)
            return
        code = report["status"]
        if code == 15:
            route = NavigationState.from_report(report["navigation"])
            if not route.active or (route.map_id, route.x, route.y) != (
                candidate.map_id,
                candidate.x,
                candidate.y,
            ):
                self.stop("La ruta no corresponde al objetivo; detenido.", reconnect=True)
                return
            self.route, self.move_target = route, candidate
            self.arrival_target, self.verify_arrival = None, False
            self.move_started = self.move_progress = now
            self.move_position = self.anchor
            self.move_world_position = self.anchor_world_position
            self.move_distance_squared = candidate.distance_squared
            self.move_reason = ""
            self.moves += 1
            self.phase, self.message = "approaching", f"Acercándose al objetivo {candidate.slot}."
        elif code in (2, 3, 6, 18, 19):
            self.cooldowns[target_key(candidate)] = now + (0 if code == 19 else 3)
            self.phase, self.message = "waiting_map", report["message"]
            self.anchor = None
        elif code == 13:
            self.stop("Bot detenido; acercamiento pendiente cancelado.")
        else:
            self.stop(report["message"], reconnect=code != 20)

    def record_movement_stop(self, report: dict, now: float, *, cleanup: bool = False) -> None:
        self.last_stop = dict(report)
        self._event(
            "movement_stop_result",
            now,
            reason=self.move_reason,
            cleanup=cleanup,
            target=asdict(self.move_target) if self.move_target else None,
            report=dict(report),
        )
        if report.get("pid") != self.pid or report.get("status") != 16:
            self.stop(
                f"No se confirmó la parada del desplazamiento. {report.get('message', '')}",
                reconnect=True,
            )
            return
        if not cleanup and self.move_reason == "route_finished":
            self.arrival_target, self.verify_arrival = self.move_target, True
        elif not cleanup:
            if self.move_target is not None:
                self.cooldowns[target_key(self.move_target)] = now + 30
            self.move_failures += 1
            self.last_failed_approach = {
                "reason": self.move_reason,
                "target": asdict(self.move_target) if self.move_target else None,
                "report": dict(report),
            }
        self.route = self.move_target = None
        self.anchor = None
        if not cleanup:
            if self.move_failures >= 3:
                self.stop("Tres acercamientos no completados; revisa el terreno antes de iniciar.")
            elif self.move_reason == "outside_area":
                self.stop("Se alcanzó el límite del área de búsqueda; bot detenido.")
            else:
                self.phase = "waiting_map"
                self.message = "Desplazamiento parado; esperando una posición estable."

    def record(self, candidate: Candidate, report: dict, now: float) -> None:
        if report.get("pid") != self.pid or report.get("slot") != candidate.slot:
            self.stop("Respuesta de otra instancia u objetivo; bot detenido.", reconnect=True)
            return
        self.attempts += 1
        self.last_attack = {
            **report,
            "battle_confirmed": False,
            "target": asdict(candidate),
            "selection_source": self.selection_source,
            "approach_id": self.moves if self.selection_source == "approach" else None,
        }
        self._event(
            "attack_result",
            now,
            attempt=self.attempts,
            target=asdict(candidate),
            source=self.selection_source,
            report=dict(report),
        )
        code = report["status"]
        self.next_scan = now + 1.5
        if code == 1:
            self.queued += 1
            self.deadline = now + 30
            self.pending_target = candidate
            self.attack_queued_at = now
            self.transport.clear()
            self.transport_first = {}
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

    def record_transport(self, report: dict, now: float) -> None:
        self.trace_time = now
        sample = {
            **report,
            "attempt": self.attempts,
            "elapsed_since_queue": round(now - self.attack_queued_at, 3)
            if self.attack_queued_at is not None
            else None,
        }
        if not self.transport_first:
            self.transport_first = sample
        previous = self.transport[-1] if self.transport else None
        self.transport.append(sample)
        fields = (set(previous or {}) | set(report)) - {
            "client_tick",
            "attempt",
            "elapsed_since_queue",
        }
        if previous is None or any(previous.get(key) != report.get(key) for key in fields):
            self._event("transport_observed", now, attempt=self.attempts, transport=report)

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
            "detector": self.detector.summary(),
            "observation_count": self.observation_count,
            "scene_counts": dict(self.scene_counts),
            "classification_counts": dict(self.classification_counts),
            "recent_observations": list(self.observations),
            "first_observation": dict(self.first_observation),
            "events": list(self.events),
            "pending_attack": {
                "target": asdict(self.pending_target),
                "elapsed_since_queue": round(self.trace_time - self.attack_queued_at, 3)
                if self.attack_queued_at is not None
                else None,
            }
            if self.pending_target is not None
            else None,
            "transport": {"first": dict(self.transport_first), "recent": list(self.transport)},
            "range": dict(self.range_diagnostic),
            "native_attack": {
                "enabled": self.native_attack,
                "search_radius": self.approach.radius,
                "requests": self.native_requests,
                "failed": self.native_failures,
                "stop_reason": self.pursuit_reason or None,
                "pursuit": self.pursuit.summary() if self.pursuit else None,
                "pending_pursuit": self.pending_pursuit.summary() if self.pending_pursuit else None,
                "target": asdict(self.pursuit_target) if self.pursuit_target else None,
                "last_request": dict(self.last_native_request),
                "last_stop": dict(self.last_native_stop),
            },
            "target_history": [
                {"slot": slot, "identity": identity}
                for identity, slot in sorted(self.engaged_targets.items())
            ],
            "profile": self.profile.summary(),
            "approach": {
                **self.approach.summary(),
                "origin": {"map_id": self.origin.map_id, "x": self.origin.x, "y": self.origin.y}
                if self.origin
                else None,
                "requests": self.moves,
                "arrivals": self.arrivals,
                "failed": self.move_failures,
                "stop_reason": self.move_reason or None,
                "current_distance_squared": self.move_distance_squared,
                "route": self.route.summary() if self.route else None,
                "last_request": dict(self.last_move),
                "last_stop": dict(self.last_stop),
                "arrival_target": asdict(self.arrival_target) if self.arrival_target else None,
                "last_failed": dict(self.last_failed_approach),
            },
        }


class HuntWorker:
    def __init__(
        self,
        session: GameSession,
        window: ClientWindow,
        detector: CombatDetector,
        profile: BotProfile | None = None,
        approach: ApproachSettings | None = None,
        *,
        native_attack: bool = False,
    ):
        if session.creation_time is None or window.pid != session.process.pid:
            raise DiagnosticError("Conecta con una instancia de Windows válida antes de iniciar.")
        self.session, self.window = session, window
        self.engine = HuntEngine(
            session.process.pid,
            session.creation_time,
            detector,
            profile or BotProfile.default(1),
            approach or ApproachSettings(),
            native_attack=native_attack,
        )
        self.events: queue.Queue[dict] = queue.Queue(maxsize=20)
        self.stop_event = threading.Event()
        self.cancellation: Cancellation | None = None
        self.stop_attempted = False
        self.native_stop_attempted = False
        self.next_transport_sample = 0
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
                try:
                    if self.stop_event.is_set():
                        signal.cancel()
                    consecutive_changes = 0
                    while not self.stop_event.is_set() and self.engine.running:
                        try:
                            self._iteration()
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
                        self.stop_event.wait(
                            0.25 if self.engine.deadline is not None or self.engine.route else 0.5
                        )
                    if self.stop_event.is_set():
                        self.engine.stop("Bot detenido; no se enviarán más solicitudes.")
                finally:
                    try:
                        signal.cancel()
                    finally:
                        self._stop_route(cleanup=True)
                        self._stop_pursuit(cleanup=True)
        except (DiagnosticError, OSError) as exc:
            self.engine.stop(str(exc), reconnect=True)
        except Exception as exc:
            self.engine.stop(
                f"Error interno del bot ({type(exc).__name__}); detenido.", reconnect=True
            )
        finally:
            self._publish()

    def _iteration(self) -> None:
        pursuing = self.engine.pursuit is not None
        moving = self.engine.route is not None or pursuing
        waiting_native_attack = self.engine.native_attack and self.engine.deadline is not None
        settling = self.engine.phase in ("waiting_map", "resuming", "battle", "confirming_battle")
        observation = (
            observe_scene(
                self.session,
                include_navigation=True,
                allow_player_movement=moving or settling or waiting_native_attack,
                **(
                    {"include_native_goal": True} if pursuing or self.engine.pending_pursuit else {}
                ),
            )
            if self.engine.uses_radius
            else observe_scene(self.session)
        )
        if self.engine.observe(observation, time.monotonic()):
            view = (
                scan_world(self.session, allow_player_movement=True)
                if moving
                else scan_world(self.session)
            )
            candidate = self.engine.select(view, time.monotonic())
            if candidate is not None and not self.stop_event.is_set():
                self._publish()
                if self.engine.phase == "requesting_native_attack":
                    report = try_native_attack(
                        self.session,
                        self.window,
                        candidate,
                        self.engine.origin,
                        self.engine.approach,
                        pursuit=self.engine.pursuit,
                        cancellation=self.cancellation,
                    )
                    self.engine.record_native(candidate, report, time.monotonic())
                    if self.engine.pursuit is not None:
                        self.native_stop_attempted = False
                elif self.engine.phase == "requesting_approach":
                    report = try_approach(
                        self.session,
                        self.window,
                        candidate,
                        self.engine.origin,
                        self.engine.approach,
                        navigation=observation.navigation,
                        cancellation=self.cancellation,
                    )
                    self.engine.record_approach(candidate, report, time.monotonic())
                    if self.engine.route is not None:
                        self.stop_attempted = False
                else:
                    report = try_attack(
                        self.session, self.window, candidate, cancellation=self.cancellation
                    )
                    self.engine.record(candidate, report, time.monotonic())
        if self.engine.route is not None and self.engine.phase == "stopping_move":
            self._stop_route()
        if self.engine.pursuit is not None and self.engine.phase == "stopping_native_pursuit":
            self._stop_pursuit()
        now = time.monotonic()
        if self.engine.deadline is not None and now >= self.next_transport_sample:
            self.engine.record_transport(observe_transport(self.session), time.monotonic())
            self.next_transport_sample = now + 1

    def _stop_route(self, *, cleanup: bool = False) -> None:
        if self.engine.route is None or self.stop_attempted:
            return
        self.stop_attempted = True
        try:
            report = stop_movement(self.session, self.window, self.engine.route)
            self.engine.record_movement_stop(report, time.monotonic(), cleanup=cleanup)
        except (DiagnosticError, OSError) as exc:
            self.engine.last_stop = {"pid": self.window.pid, "message": str(exc)}
            self.engine.stop(f"Parada del desplazamiento sin confirmar: {exc}", reconnect=True)

    def _stop_pursuit(self, *, cleanup: bool = False) -> None:
        pursuit = self.engine.pursuit or self.engine.pending_pursuit
        if pursuit is None or self.native_stop_attempted:
            return
        self.native_stop_attempted = True
        try:
            report = stop_native_pursuit(self.session, self.window, pursuit)
            self.engine.record_native_stop(report, time.monotonic(), cleanup=cleanup)
        except (DiagnosticError, OSError) as exc:
            self.engine.last_native_stop = {"pid": self.window.pid, "message": str(exc)}
            self.engine.stop(f"Parada nativa sin confirmar: {exc}", reconnect=True)
