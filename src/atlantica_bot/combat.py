from __future__ import annotations

from dataclasses import dataclass, field

from .errors import DiagnosticError
from .world import Observation

STAGES = ("map_before", "battle", "map_after")
SAMPLES_PER_STAGE = 3


def _context_active(observation: Observation) -> bool | None:
    local = observation.local
    if local is None:
        return None
    # The captured client predicate 00435D5A checks these two signed fields.
    # Its use on the local actor is enabled only after a labelled round trip.
    return local.context_a >= 0 or local.context_b >= 0


@dataclass(frozen=True)
class CombatDetector:
    pid: int
    creation_time: int
    signal: str

    def matches(self, pid: int, creation_time: int | None) -> bool:
        return (pid, creation_time) == (self.pid, self.creation_time)

    def classify(self, observation: Observation) -> str:
        if not self.matches(observation.pid, observation.creation_time):
            return "unknown"
        if self.signal == "scene_transition":
            if observation.scene_code == 1:
                return "battle"
            if observation.scene_code == 2 and observation.player is not None:
                return "map"
        elif self.signal == "local_context" and observation.scene_code == 2:
            active = _context_active(observation)
            if active is True:
                return "battle"
            if active is False and observation.player is not None:
                return "map"
        return "unknown"

    def summary(self) -> dict:
        return {
            "pid": self.pid,
            "instance_creation_time": self.creation_time,
            "signal": self.signal,
            "source": "labelled_map_battle_map_samples",
        }


@dataclass
class CombatCalibration:
    pid: int
    creation_time: int
    samples: dict[str, tuple[Observation, ...]] = field(default_factory=dict)

    @property
    def next_stage(self) -> str | None:
        return next((stage for stage in STAGES if stage not in self.samples), None)

    def capture(self, stage: str, samples: tuple[Observation, ...]) -> None:
        if stage != self.next_stage or len(samples) != SAMPLES_PER_STAGE:
            raise DiagnosticError("Captura primero mapa, después combate y finalmente regreso.")
        for sample in samples:
            if (sample.pid, sample.creation_time) != (self.pid, self.creation_time):
                raise DiagnosticError("La instancia cambió; reinicia la calibración.")
            if sample.native_active:
                raise DiagnosticError("Calibra con Auto Battle y caza nativa apagados.")
        if stage != "battle":
            if any(sample.scene_code != 2 or sample.player is None for sample in samples):
                raise DiagnosticError("Captura el mapa con el personaje quieto y fuera de combate.")
            if any(sample.player != samples[0].player for sample in samples):
                raise DiagnosticError(
                    "El personaje se movió durante la captura; vuelve a capturar."
                )
        self.samples[stage] = samples

    def detector(self) -> CombatDetector:
        if self.next_stage is not None:
            raise DiagnosticError("Faltan capturas de mapa, combate o regreso.")
        before, battle, after = (self.samples[stage] for stage in STAGES)
        if before[0].player.map_id != after[0].player.map_id:
            raise DiagnosticError("Regresa al mismo mapa para comprobar el detector.")
        if all(sample.scene_code == 1 for sample in battle):
            signal = "scene_transition"
        elif (
            all(sample.scene_code == 2 for sample in battle)
            and all(_context_active(sample) is False for sample in (*before, *after))
            and all(_context_active(sample) is True for sample in battle)
        ):
            signal = "local_context"
        else:
            raise DiagnosticError(
                "Estas capturas no permiten distinguir el combate. "
                "Copia la calibración para revisar las señales; el ciclo seguirá bloqueado."
            )
        return CombatDetector(self.pid, self.creation_time, signal)

    def summary(self) -> dict:
        return {
            "pid": self.pid,
            "instance_creation_time": self.creation_time,
            "samples": {
                stage: [sample.summary() for sample in samples]
                for stage, samples in self.samples.items()
            },
        }
