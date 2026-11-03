from __future__ import annotations

import ctypes
import struct
import sys
from contextlib import contextmanager
from pathlib import Path

from .clients import ClientWindow
from .errors import DiagnosticError, NativeError
from .report import Module, Process

DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
BOOL = ctypes.c_int32
HANDLE = ctypes.c_void_p
SIZE_T = ctypes.c_size_t
INVALID_HANDLE = ctypes.c_void_p(-1).value
ERROR_NO_MORE_FILES = 18
ERROR_BAD_LENGTH = 24


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", DWORD),
        ("cntUsage", DWORD),
        ("th32ProcessID", DWORD),
        ("th32DefaultHeapID", SIZE_T),
        ("th32ModuleID", DWORD),
        ("cntThreads", DWORD),
        ("th32ParentProcessID", DWORD),
        ("pcPriClassBase", ctypes.c_int32),
        ("dwFlags", DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class ModuleEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", DWORD),
        ("th32ModuleID", DWORD),
        ("th32ProcessID", DWORD),
        ("GlblcntUsage", DWORD),
        ("ProccntUsage", DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", DWORD),
        ("hModule", HANDLE),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


class FixedFileInfo(ctypes.Structure):
    _fields_ = [
        (name, DWORD)
        for name in (
            "dwSignature",
            "dwStrucVersion",
            "dwFileVersionMS",
            "dwFileVersionLS",
            "dwProductVersionMS",
            "dwProductVersionLS",
            "dwFileFlagsMask",
            "dwFileFlags",
            "dwFileOS",
            "dwFileType",
            "dwFileSubtype",
            "dwFileDateMS",
            "dwFileDateLS",
        )
    ]


class ProcessBasicInformation(ctypes.Structure):
    _fields_ = [
        ("reserved1", ctypes.c_void_p),
        ("peb", ctypes.c_void_p),
        ("reserved2", ctypes.c_void_p * 2),
        ("pid", SIZE_T),
        ("reserved3", ctypes.c_void_p),
    ]


def _bind(library, name, arguments, result):
    function = getattr(library, name)
    function.argtypes = arguments
    function.restype = result
    return function


def _fail(operation: str) -> None:
    code = ctypes.get_last_error()
    raise NativeError(operation, code)


class WindowsSystem:
    """Documented Windows APIs with query/read access only; never writes to the game."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise DiagnosticError(
                "Ejecuta este diagnóstico en el PC Windows donde tienes el juego."
            )
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        user = ctypes.WinDLL("user32", use_last_error=True)
        self._window_callback_type = ctypes.WINFUNCTYPE(BOOL, HANDLE, ctypes.c_ssize_t)
        self._enum_windows = _bind(
            user, "EnumWindows", [self._window_callback_type, ctypes.c_ssize_t], BOOL
        )
        self._window_pid = _bind(
            user, "GetWindowThreadProcessId", [HANDLE, ctypes.POINTER(DWORD)], DWORD
        )
        self._window_visible = _bind(user, "IsWindowVisible", [HANDLE], BOOL)
        self._window_title = _bind(
            user, "GetWindowTextW", [HANDLE, ctypes.c_wchar_p, ctypes.c_int], ctypes.c_int
        )
        self._foreground = _bind(user, "GetForegroundWindow", [], HANDLE)
        version = ctypes.WinDLL("version", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        self._query_information = _bind(
            ntdll,
            "NtQueryInformationProcess",
            [HANDLE, DWORD, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)],
            ctypes.c_int32,
        )
        self._snapshot = _bind(kernel, "CreateToolhelp32Snapshot", [DWORD, DWORD], HANDLE)
        self._close = _bind(kernel, "CloseHandle", [HANDLE], BOOL)
        self._process_first = _bind(
            kernel, "Process32FirstW", [HANDLE, ctypes.POINTER(ProcessEntry)], BOOL
        )
        self._process_next = _bind(
            kernel, "Process32NextW", [HANDLE, ctypes.POINTER(ProcessEntry)], BOOL
        )
        self._module_first = _bind(
            kernel, "Module32FirstW", [HANDLE, ctypes.POINTER(ModuleEntry)], BOOL
        )
        self._module_next = _bind(
            kernel, "Module32NextW", [HANDLE, ctypes.POINTER(ModuleEntry)], BOOL
        )
        self._open = _bind(kernel, "OpenProcess", [DWORD, BOOL, DWORD], HANDLE)
        self._process_times = _bind(
            kernel,
            "GetProcessTimes",
            [HANDLE, *([ctypes.POINTER(ctypes.c_uint64)] * 4)],
            BOOL,
        )
        self._query_path = _bind(
            kernel,
            "QueryFullProcessImageNameW",
            [HANDLE, DWORD, ctypes.c_wchar_p, ctypes.POINTER(DWORD)],
            BOOL,
        )
        self._read = _bind(
            kernel,
            "ReadProcessMemory",
            [HANDLE, ctypes.c_void_p, ctypes.c_void_p, SIZE_T, ctypes.POINTER(SIZE_T)],
            BOOL,
        )
        self._version_size = _bind(
            version, "GetFileVersionInfoSizeW", [ctypes.c_wchar_p, ctypes.POINTER(DWORD)], DWORD
        )
        self._version_info = _bind(
            version,
            "GetFileVersionInfoW",
            [ctypes.c_wchar_p, DWORD, DWORD, ctypes.c_void_p],
            BOOL,
        )
        self._version_query = _bind(
            version,
            "VerQueryValueW",
            [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(DWORD),
            ],
            BOOL,
        )

    @contextmanager
    def _managed(self, handle, operation: str):
        if handle is None or handle == 0 or handle == INVALID_HANDLE:
            _fail(operation)
        try:
            yield handle
        finally:
            self._close(handle)

    def _take_snapshot(self, flags: int, pid: int):
        # Microsoft documents ERROR_BAD_LENGTH as a transient module-list change.
        for _ in range(3):
            handle = self._snapshot(flags, pid)
            if handle != INVALID_HANDLE or ctypes.get_last_error() != ERROR_BAD_LENGTH:
                return handle
        return handle

    @staticmethod
    def _finished(operation: str) -> None:
        if ctypes.get_last_error() != ERROR_NO_MORE_FILES:
            _fail(operation)

    def processes(self) -> list[Process]:
        found = []
        with self._managed(self._take_snapshot(0x00000002, 0), "Enumerar procesos") as snapshot:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not self._process_first(snapshot, ctypes.byref(entry)):
                self._finished("Leer primer proceso")
                return found
            while True:
                found.append(Process(int(entry.th32ProcessID), entry.szExeFile))
                if not self._process_next(snapshot, ctypes.byref(entry)):
                    self._finished("Enumerar procesos")
                    break
        return found

    def game_windows(self) -> list[ClientWindow]:
        pids = {p.pid for p in self.processes() if p.name.casefold() == "atlantica.exe"}
        windows = []

        def visit(handle, parameter):
            pid = DWORD()
            self._window_pid(handle, ctypes.byref(pid))
            if pid.value in pids and self._window_visible(handle):
                title = ctypes.create_unicode_buffer(512)
                self._window_title(handle, title, len(title))
                windows.append(ClientWindow(pid.value, int(handle), title.value))
            return True

        callback = self._window_callback_type(visit)
        if not self._enum_windows(callback, 0):
            _fail("Enumerar ventanas del juego")
        return sorted(windows, key=lambda window: (window.pid, window.handle))

    def active_game_window(self) -> ClientWindow:
        active = self._foreground()
        for window in self.game_windows():
            if window.handle == active:
                return window
        raise DiagnosticError("La ventana activa no pertenece a Atlantica.exe.")

    def executable_path(self, pid: int) -> Path:
        # PROCESS_QUERY_LIMITED_INFORMATION, not PROCESS_ALL_ACCESS.
        with self._managed(self._open(0x1000, False, pid), "Consultar proceso") as handle:
            buffer = ctypes.create_unicode_buffer(32768)
            length = DWORD(len(buffer))
            if not self._query_path(handle, 0, buffer, ctypes.byref(length)):
                _fail("Consultar ejecutable")
            return Path(buffer.value)

    def process_creation_time(self, pid: int) -> int:
        with self._managed(self._open(0x1000, False, pid), "Consultar instancia") as handle:
            times = [ctypes.c_uint64() for _ in range(4)]
            if not self._process_times(handle, *(ctypes.byref(value) for value in times)):
                _fail("Consultar inicio del proceso")
            return times[0].value

    def main_module(self, pid: int, name: str) -> Module:
        # Include WOW64 modules when this interpreter is 64-bit.
        with self._managed(self._take_snapshot(0x00000018, pid), "Consultar módulos") as snapshot:
            entry = ModuleEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not self._module_first(snapshot, ctypes.byref(entry)):
                self._finished("Leer primer módulo")
            else:
                while True:
                    if entry.szModule.casefold() == name.casefold() and entry.modBaseAddr:
                        return Module(int(entry.modBaseAddr), int(entry.modBaseSize))
                    if not self._module_next(snapshot, ctypes.byref(entry)):
                        self._finished("Enumerar módulos")
                        break
        raise DiagnosticError("No se encontró el módulo principal del cliente.")

    def working_directory(self, pid: int) -> Path:
        """Read only the current-directory string of the verified 32-bit client."""
        with self._managed(
            self._open(0x0400, False, pid), "Consultar carpeta de trabajo"
        ) as handle:
            if ctypes.sizeof(ctypes.c_void_p) == 8:
                peb32 = SIZE_T()
                status = self._query_information(
                    handle, 26, ctypes.byref(peb32), ctypes.sizeof(peb32), None
                )
                peb_address = peb32.value
            else:
                basic = ProcessBasicInformation()
                status = self._query_information(
                    handle, 0, ctypes.byref(basic), ctypes.sizeof(basic), None
                )
                peb_address = basic.peb
            if status < 0:
                raise DiagnosticError(
                    f"Consulta del proceso fallida: NTSTATUS {status & 0xFFFFFFFF:08X}."
                )
            if not peb_address:
                raise DiagnosticError("No se pudo localizar el PEB del cliente de 32 bits.")
        parameters = int.from_bytes(self.read_memory(pid, peb_address + 0x10, 4), "little")
        if not parameters:
            raise DiagnosticError("El cliente todavía no publica su carpeta de trabajo.")
        info = self.read_memory(pid, parameters + 0x24, 8)
        length = int.from_bytes(info[:2], "little")
        maximum = int.from_bytes(info[2:4], "little")
        address = int.from_bytes(info[4:], "little")
        if not address or not 0 < length <= maximum <= 32768 or length % 2 or maximum % 2:
            raise DiagnosticError("La información de la carpeta de trabajo no es válida.")
        try:
            directory = self.read_memory(pid, address, length).decode("utf-16le")
        except UnicodeDecodeError as exc:
            raise DiagnosticError("No se pudo interpretar la carpeta de trabajo.") from exc
        if "\0" in directory:
            raise DiagnosticError("La carpeta de trabajo contiene datos no válidos.")
        return Path(directory)

    def read_memory(self, pid: int, address: int, size: int) -> bytes:
        address_limit = 1 << (struct.calcsize("P") * 8)
        if type(address) is not int or type(size) is not int:
            raise DiagnosticError("La dirección y el tamaño deben ser enteros.")
        if address <= 0 or not 1 <= size <= 1024 * 1024 or address + size > address_limit:
            raise DiagnosticError("Rango de lectura no válido (máximo 1 MiB).")
        # PROCESS_VM_READ. No write, operation, thread-creation or debug privileges.
        with self._managed(self._open(0x0010, False, pid), "Abrir proceso para lectura") as handle:
            buffer = ctypes.create_string_buffer(size)
            received = SIZE_T()
            if not self._read(handle, address, buffer, size, ctypes.byref(received)):
                _fail("Leer memoria")
            if received.value != size:
                raise DiagnosticError("La lectura de memoria quedó incompleta.")
            return buffer.raw

    def file_version(self, path: Path) -> str | None:
        ignored = DWORD()
        size = self._version_size(str(path), ctypes.byref(ignored))
        if size == 0:
            return None
        if size > 16 * 1024 * 1024:
            raise DiagnosticError("El recurso de versión del ejecutable es demasiado grande.")
        buffer = ctypes.create_string_buffer(size)
        if not self._version_info(str(path), 0, size, buffer):
            _fail("Leer versión del archivo")
        pointer = ctypes.c_void_p()
        length = DWORD()
        if not self._version_query(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        if not pointer.value or length.value < ctypes.sizeof(FixedFileInfo):
            return None
        info = ctypes.cast(pointer, ctypes.POINTER(FixedFileInfo)).contents
        if info.dwSignature != 0xFEEF04BD:
            return None
        return ".".join(
            str(part)
            for part in (
                info.dwFileVersionMS >> 16,
                info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16,
                info.dwFileVersionLS & 0xFFFF,
            )
        )
