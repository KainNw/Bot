from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import DiagnosticError


@dataclass(frozen=True)
class Mercenary:
    slot: int
    name: str
    enabled: bool = True


@dataclass(frozen=True)
class BotProfile:
    number: int
    mercenaries: tuple[Mercenary, ...]

    def validate(self) -> None:
        if type(self.number) is not int or self.number not in (1, 2, 3):
            raise DiagnosticError("Elige uno de los tres perfiles.")
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

    def summary(self) -> dict:
        return {
            "schema_version": 1,
            "profile": self.number,
            "mercenaries": [asdict(merc) for merc in self.mercenaries],
            "turn_execution_available": False,
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
                or payload["schema_version"] != 1
                or type(payload["profile"]) is not int
                or payload["profile"] != number
            ):
                raise ValueError
            mercenaries = tuple(Mercenary(**entry) for entry in payload["mercenaries"])
            profile = BotProfile(number, mercenaries)
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
