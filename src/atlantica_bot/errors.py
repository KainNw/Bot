class DiagnosticError(RuntimeError):
    """An actionable diagnostic failure that the CLI can show without a traceback."""


class NativeError(DiagnosticError):
    def __init__(self, operation: str, code: int) -> None:
        self.code = code
        super().__init__(f"{operation} falló (WinError {code}).")
