from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import DiagnosticError
from .limits import MAX_ATTACK_DELAY_SECONDS, MAX_SEARCH_RADIUS, MIN_SEARCH_RADIUS, SPEED_RATES

ACTION_LABELS = {
    "basic": "Ataque básico",
    "Q": "Magia Q",
    "W": "Magia W",
    "E": "Magia E",
    "R": "Magia R",
    "T": "Magia T",
    "defend": "Defender (G)",
    "pass": "Pasar acción (F)",
}

LATER_ACTION_LABELS = {key: ACTION_LABELS[key] for key in ("basic", "defend", "pass")}

WORLD_ATTACK_LABELS = {
    "native": "Perseguir y atacar (nativo)",
    "stationary": "Atacar desde mi posición (experimental)",
    "nearby": "Atacar solo a mobs en alcance",
}


def member_label(slot: int) -> str:
    return "Main (1)" if slot == 1 else f"Mercenario {slot}"


TARGET_LABELS = {
    "enemy": "Enemigo",
    "self": "Sí mismo",
    **{f"slot_{n}": member_label(n) for n in range(1, 10)},
}


def atomic_json_write(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Mercenary:
    slot: int
    name: str
    enabled: bool = True
    action: str = "basic"
    fallback_basic: bool = True
    target: str = "enemy"
    later_action: str = "basic"

    def action_for_turn(self, *, opening: bool, first_only: bool) -> str:
        if not opening and first_only and self.action in "QWERT":
            return self.later_action
        return self.action


@dataclass(frozen=True)
class BotProfile:
    number: int
    mercenaries: tuple[Mercenary, ...]
    magic_first_turn_only: bool = True
    attack_delay_seconds: float = 0.0
    search_radius: int = 60
    collect_remaining_loot: bool = False
    world_attack_mode: str = "native"
    battle_speed_enabled: bool = False
    battle_speed_rate: float = 1.25
    neo_loot_grace_seconds: float = 1.0
    pass_remaining: bool = False
    general_speed_enabled: bool = False
    general_speed_rate: float = 1.25
    auto_life_enabled: bool = False
    auto_life_threshold: int = 50
    auto_life_key: str = "F1"
    instant_loot: bool = True

    @property
    def speed_enabled(self) -> bool:
        return self.battle_speed_enabled or self.general_speed_enabled

    @property
    def loot_grace_seconds(self) -> float:
        return 0.0 if self.instant_loot else self.neo_loot_grace_seconds

    def validate(self) -> None:
        if type(self.number) is not int or self.number not in (1, 2, 3):
            raise DiagnosticError("Elige uno de los tres perfiles.")
        if type(self.magic_first_turn_only) is not bool:
            raise DiagnosticError("Revisa la configuración de magia del primer turno.")
        if type(self.pass_remaining) is not bool:
            raise DiagnosticError("Revisa la opción de pasar las acciones restantes.")
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
        if type(self.instant_loot) is not bool:
            raise DiagnosticError("Revisa la opción de recogida inmediata.")
        if (
            type(self.neo_loot_grace_seconds) not in (int, float)
            or not math.isfinite(self.neo_loot_grace_seconds)
            or not 0 <= self.neo_loot_grace_seconds <= 5
        ):
            raise DiagnosticError("La espera del NeoACA debe estar entre 0 y 5 segundos.")
        if (
            type(self.battle_speed_enabled) is not bool
            or type(self.battle_speed_rate) not in (int, float)
            or self.battle_speed_rate not in SPEED_RATES
        ):
            raise DiagnosticError("Elige una velocidad de combate admitida: 1,25, 1,5, 2, 3 o 4×.")
        if (
            type(self.general_speed_enabled) is not bool
            or type(self.general_speed_rate) not in (int, float)
            or self.general_speed_rate not in SPEED_RATES
        ):
            raise DiagnosticError("Elige un Speed general admitido: 1,25, 1,5, 2, 3 o 4×.")
        if self.general_speed_enabled and self.battle_speed_enabled:
            raise DiagnosticError("Elige un modo de Speed: general o solo combate.")
        if (
            type(self.auto_life_enabled) is not bool
            or type(self.auto_life_threshold) is not int
            or not 1 <= self.auto_life_threshold <= 100
            or type(self.auto_life_key) is not str
            or self.auto_life_key not in tuple(f"F{i}" for i in range(1, 10))
        ):
            raise DiagnosticError(
                "Auto Life requiere un umbral de MP de 1–100 % y una tecla F1–F9."
            )
        if (
            type(self.world_attack_mode) is not str
            or self.world_attack_mode not in WORLD_ATTACK_LABELS
        ):
            raise DiagnosticError("Elige el modo de ataque al mob.")
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
                or type(merc.later_action) is not str
                or merc.later_action not in LATER_ACTION_LABELS
            ):
                raise DiagnosticError("Elige básico, magia, defensa o pasar por puesto.")

    def summary(self) -> dict:
        return {
            "schema_version": 11,
            "profile": self.number,
            "mercenaries": [asdict(merc) for merc in self.mercenaries],
            "magic_first_turn_only": self.magic_first_turn_only,
            "attack_delay_seconds": self.attack_delay_seconds,
            "search_radius": self.search_radius,
            "collect_remaining_loot": self.collect_remaining_loot,
            "world_attack_mode": self.world_attack_mode,
            "battle_speed_enabled": self.battle_speed_enabled,
            "battle_speed_rate": self.battle_speed_rate,
            "neo_loot_grace_seconds": self.neo_loot_grace_seconds,
            "pass_remaining": self.pass_remaining,
            "general_speed_enabled": self.general_speed_enabled,
            "general_speed_rate": self.general_speed_rate,
            "auto_life_enabled": self.auto_life_enabled,
            "auto_life_threshold": self.auto_life_threshold,
            "auto_life_key": self.auto_life_key,
            "instant_loot": self.instant_loot,
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
                or payload["schema_version"] not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
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
                ) | ({"later_action"} if payload["schema_version"] >= 8 else set()):
                    raise ValueError
            mercenaries = tuple(Mercenary(**entry) for entry in payload["mercenaries"])
            profile = BotProfile(
                number,
                mercenaries,
                payload["magic_first_turn_only"] if payload["schema_version"] >= 3 else True,
                payload["attack_delay_seconds"] if payload["schema_version"] >= 4 else 0.0,
                payload["search_radius"] if payload["schema_version"] >= 4 else 60,
                payload["collect_remaining_loot"] if payload["schema_version"] >= 4 else False,
                payload["world_attack_mode"] if payload["schema_version"] >= 5 else "native",
                payload["battle_speed_enabled"] if payload["schema_version"] >= 6 else False,
                payload["battle_speed_rate"] if payload["schema_version"] >= 6 else 1.25,
                payload["neo_loot_grace_seconds"] if payload["schema_version"] >= 7 else 1.0,
                payload["pass_remaining"] if payload["schema_version"] >= 8 else False,
                payload["general_speed_enabled"] if payload["schema_version"] >= 9 else False,
                payload["general_speed_rate"] if payload["schema_version"] >= 9 else 1.25,
                payload["auto_life_enabled"] if payload["schema_version"] >= 10 else False,
                payload["auto_life_threshold"] if payload["schema_version"] >= 10 else 50,
                payload["auto_life_key"] if payload["schema_version"] >= 10 else "F1",
                payload["instant_loot"] if payload["schema_version"] >= 11 else True,
            )
            profile.validate()
            return profile
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise DiagnosticError(
                "El perfil guardado no es válido; el archivo se conserva."
            ) from exc

    def save(self, profile: BotProfile) -> None:
        profile.validate()
        atomic_json_write(self._path(profile.number), profile.summary())
