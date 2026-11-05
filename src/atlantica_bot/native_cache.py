"""Keep the same native DLL path across launches of a packaged panel build."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .errors import DiagnosticError


def stable_bridge(source: Path, directory: Path) -> Path:
    names = ("AtlanticaBridge.exe", "AtlanticaHook.dll")
    try:
        content = {name: (source / name).read_bytes() for name in names}
        digest = hashlib.sha256()
        for name, data in content.items():
            digest.update(name.encode("ascii"))
            digest.update(hashlib.sha256(data).digest())
        target = directory / digest.hexdigest()
        target.mkdir(parents=True, exist_ok=True)
        for name, data in content.items():
            path = target / name
            if not path.exists():
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target, delete=False) as file:
                        temporary = Path(file.name)
                        file.write(data)
                    try:
                        os.replace(temporary, path)
                    except OSError:
                        # Another panel may have installed and loaded this exact
                        # build while this process was copying its private file.
                        if not path.exists():
                            raise
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            if path.read_bytes() != data:
                raise DiagnosticError(
                    "El puente guardado no coincide con esta versión. No se ejecutó."
                )
        return target / names[0]
    except OSError as exc:
        raise DiagnosticError("No se pudo preparar el puente estable del panel.") from exc
