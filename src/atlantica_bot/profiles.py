from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import DiagnosticError
from .limits import MAX_ATTACK_DELAY_SECONDS, MAX_SEARCH_RADIUS, MIN_SEARCH_RADIUS

ACTION_LABELS = {
    "basic": "Ataque básico",
    "Q": "Magia Q",
    "W": "Magia W",
    "E": "Magia E",
    "R": "Magia R",
    "T": "Magia T",
}


def member_label(slot: int) -> str:
    return "Main (1)" if slot == 1 else f"Mercenario {slot}"


TARGET_LABELS = {
    "enemy": "Enemigo",
    "self": "Sí mismo",
    **{f"slot_{n}": member_label(n) for n in range(1, 10)},
}


@dataclass(frozen=True)
class Mercenary:
    slot: int
    name: str
    enabled: bool = True
    action: str = "basic"
    fallback_basic: bool = True
    target: str = "enemy"


@dataclass(frozen=True)
class BotProfile:
    number: int
    mercenaries: tuple[Mercenary, ...]
    magic_first_turn_only: bool = True
    attack_delay_seconds: float = 0.0
    search_radius: int = 60
    collect_remaining_loot: bool = False

    def validate(self) -> None:
        if type(self.number) is not int or self.number not in (1, 2, 3):
            raise DiagnosticError("Elige uno de los tres perfiles.")
        if type(self.magic_first_turn_only) is not bool:
            raise DiagnosticError("Revisa la configuración de magia del primer turno.")
        if (
            type(self.attack_delay_seconds) not in (int, float)
            or not math.isfinite(self.attack_delay_seconds)
            or not 0 <= self.attack_delay_seconds <= MAX_ATTACK_DELAY_SECONDS
        ):
            raise DiagnosticError("El tiempo antes de atacar debe estar entre 0 y 60 segundos.")
        if (
            type(self.search_radius) is not int
            or not MIN_SEARCH_RADIUS <= self.search_radius <= MAX_SEARCH_RADIUS
        ):
            raise DiagnosticError("El radio de búsqueda debe estar entre 5 y 500 casillas.")
        if type(self.collect_remaining_loot) is not bool:
            raise DiagnosticError("Revisa la opción de recogida de botín restante.")
        if (
            len(self.mercenaries) != 9
            or any(type(merc.slot) is not int for merc in self.mercenaries)
            or {merc.slot for merc in self.mercenaries} != set(range(1, 10))
        ):
            raise DiagnosticError("El perfil debe contener los nueve puestos sin repetirlos.")
        for merc in self.mercenaries:
            if (
                not isinstance(merc.name, str)
                or not 1 <= len(merc.name.strip()) <= 40
                or any(ord(char) < 32 for char in merc.name)
                or type(merc.enabled) is not bool
            ):
                raise DiagnosticError("Revisa los nombres y la selección de mercenarios.")
            if (
                type(merc.action) is not str
                or merc.action not in ACTION_LABELS
                or type(merc.fallback_basic) is not bool
                or type(merc.target) is not str
                or merc.target not in TARGET_LABELS
            ):
                raise DiagnosticError("Elige ataque básico o una magia Q/W/E/R/T por puesto.")

    def summary(self) -> dict:
        return {
            "schema_version": 4,
            "profile": self.number,
            "mercenaries": [asdict(merc) for merc in self.mercenaries],
            "magic_first_turn_only": self.magic_first_turn_only,
            "attack_delay_seconds": self.attack_delay_seconds,
            "search_radius": self.search_radius,
            "collect_remaining_loot": self.collect_remaining_loot,
            "turn_execution_available": True,
        }

    @classmethod
    def default(cls, number: int) -> BotProfile:
        profile = cls(number, tuple(Mercenary(slot, f"Puesto {slot}") for slot in range(1, 10)))
        profile.validate()
        return profile


class ProfileStore:
    def __init__(self, directory: Path):
        self.directory = directory

    @classmethod
    def for_windows(cls) -> ProfileStore:
        directory = os.environ.get("LOCALAPPDATA")
        if not directory:
            raise DiagnosticError("Windows no publica la carpeta de configuración del usuario.")
        return cls(Path(directory) / "AtlanticaPanel" / "profiles")

    def _path(self, number: int) -> Path:
        BotProfile.default(number)
        return self.directory / f"profile-{number}.json"

    def load(self, number: int) -> BotProfile:
        path = self._path(number)
        try:
            with path.open("rb") as source:
                data = source.read(32769)
        except FileNotFoundError:
            return BotProfile.default(number)
        if len(data) > 32768:
            raise DiagnosticError("El perfil guardado excede el tamaño permitido.")
        try:
            payload = json.loads(data)
            if (
                type(payload["schema_version"]) is not int
                or payload["schema_version"] not in (1, 2, 3, 4)
                or type(payload["profile"]) is not int
                or payload["profile"] != number
            ):
                raise ValueError
            for entry in payload["mercenaries"]:
                if not isinstance(entry, dict):
                    raise ValueError
                if payload["schema_version"] == 1:
                    if set(entry) - {"slot", "name", "enabled"}:
                        raise ValueError
                elif set(entry) != {"slot", "name", "enabled", "action", "fallback_basic"} | (
                    {"target"} if payload["schema_version"] >= 3 else set()
                ):
                    raise ValueError
            mercenaries = tuple(Mercenary(**entry) for entry in payload["mercenaries"])
            profile = BotProfile(
                number,
                mercenaries,
                payload["magic_first_turn_only"] if payload["schema_version"] >= 3 else True,
                payload["attack_delay_seconds"] if payload["schema_version"] >= 4 else 0.0,
                payload["search_radius"] if payload["schema_version"] >= 4 else 60,
                payload["collect_remaining_loot"] if payload["schema_version"] >= 4 else False,
            )
            profile.validate()
            return profile
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise DiagnosticError(
                "El perfil guardado no es válido; el archivo se conserva."
            ) from exc

    def save(self, profile: BotProfile) -> None:
        profile.validate()
        path = self._path(profile.number)
        payload = json.dumps(profile.summary(), ensure_ascii=False, indent=2) + "\n"
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
