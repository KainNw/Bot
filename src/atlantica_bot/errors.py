class DiagnosticError(RuntimeError):
    """An actionable diagnostic failure that the CLI can show without a traceback."""


class SceneChanged(DiagnosticError):
    """A coherent snapshot was interrupted; discard it before requesting another."""


class WindowUnavailable(DiagnosticError):
    """The bridge rejected the window before installing a hook or sending a command."""

    REASONS = {
        "not_found": "ya no existe. Vuelve a elegir la ventana y conectar.",
        "wrong_process": "pertenece a otro proceso. Vuelve a elegir la ventana y conectar.",
        "thread_changed": "cambió de hilo. Vuelve a elegir la ventana y conectar.",
        "minimized": "está minimizada. Restáurala antes de iniciar el bot.",
        "disabled": "está bloqueada. Cierra los diálogos del juego antes de iniciar el bot.",
        "unavailable": (
            "no está disponible. Restáurala y cierra los diálogos del juego; "
            "si cambió, vuelve a elegirla y conectar."
        ),
    }

    def __init__(self, pid: int, reason: str = "unavailable") -> None:
        self.pid = pid
        self.reason = reason if reason in self.REASONS else "unavailable"
        super().__init__(
            f"La ventana del PID {pid} {self.REASONS[self.reason]} "
            "No se envió esta orden al juego (puente: código 20)."
        )

    def summary(self) -> dict:
        return {
            "pid": self.pid,
            "bridge_exit_code": 20,
            "result": "not_sent",
            "reason": self.reason,
            "command_sent": False,
            "message": str(self),
        }


class NativeError(DiagnosticError):
    def __init__(self, operation: str, code: int) -> None:
        self.code = code
        super().__init__(f"{operation} falló (WinError {code}).")
