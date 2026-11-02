from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import DiagnosticError

MACHINES = {0x014C: ("x86", 32), 0x8664: ("x64", 64), 0xAA64: ("arm64", 64)}


@dataclass(frozen=True)
class Executable:
    name: str
    architecture: str
    bits: int
    sha256: str


def inspect_executable(path: Path) -> Executable:
    """Inspect the file on disk, without loading or executing its code."""
    with path.open("rb") as executable:
        dos = executable.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise DiagnosticError("El archivo no contiene una cabecera DOS/PE válida.")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        executable.seek(0, 2)
        length = executable.tell()
        if pe_offset < 64 or pe_offset + 24 > length:
            raise DiagnosticError("La cabecera PE está truncada o fuera del archivo.")
        executable.seek(pe_offset)
        header = executable.read(24)
        if header[:4] != b"PE\x00\x00":
            raise DiagnosticError("La firma PE del ejecutable no es válida.")
        machine = struct.unpack_from("<H", header, 4)[0]
        if machine not in MACHINES:
            raise DiagnosticError(f"Arquitectura PE no admitida: 0x{machine:04x}.")
        architecture, bits = MACHINES[machine]
        executable.seek(0)
        digest = hashlib.file_digest(executable, "sha256").hexdigest()
    return Executable(path.name, architecture, bits, digest)
