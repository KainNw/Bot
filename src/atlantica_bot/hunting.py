from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .errors import DiagnosticError

SUPPORTED_CLIENT_SHA256 = "bc87a0cc5826aa7fb5e4ff10b6b7c1a349962bd8b146ad28ec3ffa9453fe04e6"
MARKER_NAME = "HuntingMode.txt"
BACKUP_NAME = "HuntingMode.txt.disabled.atlantica-bot"


@dataclass(frozen=True)
class HuntingResult:
    marker_present: bool
    backup_present: bool
    changed: bool


def marker_state(directory: Path) -> HuntingResult:
    """Read file state after the directory/build was verified by the caller."""
    return HuntingResult(
        _plain_file_or_missing(directory / MARKER_NAME),
        _plain_file_or_missing(directory / BACKUP_NAME),
        False,
    )


def _plain_file_or_missing(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        raise DiagnosticError(f"Se esperaba un archivo normal: {path.name}.")
    return True


def _move_without_replacing(source: Path, destination: Path) -> None:
    """Preserve file contents/metadata; an existing destination always wins."""
    if os.name == "nt":
        # Unlike POSIX rename(), Windows rename() refuses an existing destination.
        os.rename(source, destination)
    else:
        # The Linux development/test path also needs atomic no-clobber semantics.
        os.link(source, destination, follow_symlinks=False)
        try:
            source.unlink()
        except OSError:
            destination.unlink()
            raise


def control_hunting(directory: Path, action: str) -> HuntingResult:
    """Control the verified client's file marker, not its in-memory HUNT flag."""
    if action not in {"start", "stop", "status"}:
        raise DiagnosticError("Acción de caza no válida.")
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise DiagnosticError("La carpeta del juego no es un directorio.")
    executable = directory / "Atlantica.exe"
    if not _plain_file_or_missing(executable):
        raise DiagnosticError("No se encontró Atlantica.exe en la carpeta indicada.")
    with executable.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != SUPPORTED_CLIENT_SHA256:
        raise DiagnosticError("Este ejecutable no coincide con la compilación que analizamos.")
    marker = directory / MARKER_NAME
    backup = directory / BACKUP_NAME
    marker_exists = _plain_file_or_missing(marker)
    backup_exists = _plain_file_or_missing(backup)
    if action == "status":
        return HuntingResult(marker_exists, backup_exists, False)
    if marker_exists and backup_exists:
        raise DiagnosticError(
            "Existen tanto el marcador como su copia desactivada. "
            "Revisa ambos archivos antes de continuar; se han conservado."
        )
    if action == "start":
        if marker_exists:
            return HuntingResult(True, False, False)
        if backup_exists:
            _move_without_replacing(backup, marker)
        else:
            # Exclusive creation never truncates an existing marker.
            with marker.open("xb"):
                pass
        return HuntingResult(True, False, True)
    if not marker_exists:
        return HuntingResult(False, backup_exists, False)
    _move_without_replacing(marker, backup)
    return HuntingResult(False, True, True)
