from __future__ import annotations

import ctypes
import secrets
import sys
import threading

from .errors import DiagnosticError
from .windows import BOOL, DWORD, HANDLE, _bind, _fail


class Cancellation:
    def __init__(self, pid: int):
        if sys.platform != "win32":
            raise DiagnosticError("La cancelación nativa requiere Windows.")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = _bind(
            kernel, "CreateEventW", [ctypes.c_void_p, BOOL, BOOL, ctypes.c_wchar_p], HANDLE
        )
        self._set = _bind(kernel, "SetEvent", [HANDLE], BOOL)
        self._close = _bind(kernel, "CloseHandle", [HANDLE], BOOL)
        self._lock = threading.Lock()
        self.name = f"Local\\AtlanticaPanel.Cancel.{pid}.{secrets.token_hex(16)}"
        self._handle = create(None, True, False, self.name)
        if not self._handle:
            _fail("Crear cancelación del bot")

    def cancel(self) -> None:
        with self._lock:
            if self._handle and not self._set(self._handle):
                _fail("Solicitar parada del bot")

    def close(self) -> None:
        with self._lock:
            if self._handle:
                self._close(self._handle)
                self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            self.cancel()
        finally:
            self.close()


class BotLease:
    """A thread-owned, recursive Windows mutex; held for a whole bot run or one trial."""

    namespace = "Bot"
    owner_description = "otro bot o prueba"

    def __init__(self, pid: int):
        self.pid = pid
        self._handle = None

    def __enter__(self):
        if sys.platform != "win32":
            raise DiagnosticError("El control por PID requiere Windows.")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = _bind(kernel, "CreateMutexW", [ctypes.c_void_p, BOOL, ctypes.c_wchar_p], HANDLE)
        wait = _bind(kernel, "WaitForSingleObject", [HANDLE, DWORD], DWORD)
        self._release = _bind(kernel, "ReleaseMutex", [HANDLE], BOOL)
        self._close = _bind(kernel, "CloseHandle", [HANDLE], BOOL)
        handle = create(None, False, f"Local\\AtlanticaPanel.{self.namespace}.{self.pid}")
        if not handle:
            _fail("Reservar el cliente para el bot")
        result = wait(handle, 0)
        if result not in (0, 0x80):
            self._close(handle)
            raise DiagnosticError(
                f"El PID {self.pid} ya está bajo control de {self.owner_description}."
            )
        self._handle = handle
        return self

    def __exit__(self, *args):
        if self._handle:
            self._release(self._handle)
            self._close(self._handle)
            self._handle = None


class SpeedLease(BotLease):
    """Exclusive speed controller, independent of the ordinary attack worker."""

    namespace = "Speed"
    owner_description = "otro controlador de velocidad"
