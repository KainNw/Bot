"""Local settings keyed by the verified Main name and game installation, never by PID."""

from __future__ import annotations

import hashlib
import json
import ntpath
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .errors import DiagnosticError
from .profiles import BotProfile, ProfileStore, atomic_json_write


def character_key(client_directory: str | Path, name: str) -> tuple[str, str]:
    client = ntpath.normcase(ntpath.normpath(str(client_directory)))
    if (
        not ntpath.isabs(client)
        or not isinstance(name, str)
        or not name
        or name != name.strip()
        or not name.isprintable()
        or not any(char.isalnum() for char in name)
    ):
        raise DiagnosticError("Espera al nombre del personaje antes de guardar su configuración.")
    try:
        if len(name.encode("utf-16le")) > 46:
            raise ValueError
    except (UnicodeError, ValueError) as exc:
        raise DiagnosticError("El nombre del personaje no tiene el formato esperado.") from exc
    return client, unicodedata.normalize("NFC", name)


@dataclass(frozen=True)
class CharacterPreferences:
    selected_profile: int = 1
    execute_turns: bool = False

    def validate(self) -> None:
        if (
            type(self.selected_profile) is not int
            or self.selected_profile not in (1, 2, 3)
            or type(self.execute_turns) is not bool
        ):
            raise DiagnosticError("La configuración guardada del personaje no es válida.")


class CharacterProfileStore(ProfileStore):
    def __init__(self, templates: ProfileStore, client_directory: str | Path, name: str):
        self.key = character_key(client_directory, name)
        encoded = json.dumps(self.key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        super().__init__(templates.directory / "characters" / digest)
        self.templates = templates

    @property
    def name(self) -> str:
        return self.key[1]

    def load(self, number: int) -> BotProfile:
        # Legacy profiles seed new characters. Saving never modifies those templates.
        if not self._path(number).exists():
            return self.templates.load(number)
        return super().load(number)

    def load_preferences(self) -> CharacterPreferences:
        try:
            with (self.directory / "character.json").open("rb") as source:
                data = source.read(4097)
        except FileNotFoundError:
            return CharacterPreferences()
        try:
            if len(data) > 4096:
                raise ValueError
            payload = json.loads(data)
            if (
                type(payload["schema_version"]) is not int
                or payload["schema_version"] != 1
                or (payload["client_directory"], payload["character_name"]) != self.key
            ):
                raise ValueError
            preferences = CharacterPreferences(
                payload["selected_profile"], payload["execute_turns"]
            )
            preferences.validate()
            return preferences
        except (ValueError, TypeError, KeyError, UnicodeError, DiagnosticError) as exc:
            raise DiagnosticError(
                "La configuración del personaje no es válida; el archivo se conserva."
            ) from exc

    def save_preferences(self, preferences: CharacterPreferences) -> None:
        preferences.validate()
        # Do not replace a malformed or foreign record with an automatic save.
        self.load_preferences()
        atomic_json_write(
            self.directory / "character.json",
            {
                "schema_version": 1,
                "client_directory": self.key[0],
                "character_name": self.name,
                "selected_profile": preferences.selected_profile,
                "execute_turns": preferences.execute_turns,
            },
        )
