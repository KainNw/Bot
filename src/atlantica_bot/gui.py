from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .capture import export_code_context
from .errors import DiagnosticError
from .hunting import control_hunting, marker_state
from .session import GameSession, LiveState
from .world import scan_world


def launch_panel(*, smoke_test: bool = False) -> None:
    if sys.platform != "win32":
        raise DiagnosticError("El panel con lectura del cliente se ejecuta en Windows.")
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from .windows import WindowsSystem

    class Panel:
        def __init__(self) -> None:
            self.root = tk.Tk()
            self.root.title(f"Atlantica — Control de caza {__version__}")
            self.root.minsize(720, 390)
            self.directory: Path | None = None
            self.session: GameSession | None = None
            self.last_state: LiveState | None = None
            self.pid = tk.StringVar()
            self.folder = tk.StringVar(value="Conecta con el juego o selecciona su carpeta.")
            self.request = tk.StringVar(value="Solicitud: sin consultar")
            self.status = tk.StringVar(value="Cliente: sin conexión")
            self.detail = tk.StringVar(value="El panel abre sin activar la caza.")
            frame = ttk.Frame(self.root, padding=18)
            frame.pack(fill="both", expand=True)
            ttk.Label(frame, text="Control de caza", font=("Segoe UI", 18)).pack(anchor="w")
            ttk.Label(
                frame,
                text="Iniciar requiere Auto Battle. Ver objetivos: solo lectura.",
            ).pack(anchor="w", pady=4)
            ttk.Label(frame, textvariable=self.folder, wraplength=680).pack(anchor="w", pady=8)
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=4)
            ttk.Button(row, text="Seleccionar carpeta", command=self.browse).pack(side="left")
            ttk.Label(row, text="PID opcional:").pack(side="left", padx=(12, 4))
            ttk.Entry(row, textvariable=self.pid, width=9).pack(side="left")
            ttk.Button(row, text="Conectar", command=self.connect).pack(side="left", padx=8)
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=18)
            self.start_button = ttk.Button(
                row, text="Iniciar", command=self.start, state="disabled"
            )
            self.start_button.pack(side="left", padx=(0, 10))
            self.stop_button = ttk.Button(row, text="Parar", command=self.stop, state="disabled")
            self.stop_button.pack(side="left")
            self.capture_button = ttk.Button(
                row, text="Exportar diagnóstico", command=self.export, state="disabled"
            )
            self.capture_button.pack(side="left", padx=10)
            self.targets_button = ttk.Button(
                row, text="Ver objetivos", command=self.show_targets, state="disabled"
            )
            self.targets_button.pack(side="left")
            ttk.Label(frame, textvariable=self.request).pack(anchor="w", pady=4)
            ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 12, "bold")).pack(
                anchor="w", pady=4
            )
            ttk.Label(frame, textvariable=self.detail, wraplength=680).pack(anchor="w", pady=8)
            ttk.Label(
                frame,
                text="Antes de moverte: solicita parar, espera confirmación y apaga Auto Battle.\n"
                "El cierre del juego comunicado durante la prueba sigue pendiente de diagnóstico.",
                wraplength=680,
            ).pack(anchor="w", pady=10)
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.root.after(750, self.poll)

        def error(self, exc: Exception) -> None:
            self.detail.set(str(exc))
            messagebox.showerror("Control de caza", str(exc))

        def browse(self) -> None:
            value = filedialog.askdirectory(title="Carpeta de trabajo de Atlantica")
            if not value:
                return
            try:
                directory = Path(value).resolve(strict=True)
                control_hunting(directory, "status")
                self.directory = directory
                self.session = None
                self.last_state = None
                self.start_button.configure(state="disabled")
                self.capture_button.configure(state="disabled")
                self.targets_button.configure(state="disabled")
                self.folder.set(str(directory))
                self.status.set("Cliente: sin conexión; estado real sin confirmar")
                self.refresh_files()
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def connect(self) -> None:
            from .__main__ import positive_pid

            try:
                pid = positive_pid(self.pid.get().strip()) if self.pid.get().strip() else None
                session = GameSession.connect(WindowsSystem(), pid)
                self.session = session
                self.directory = session.directory
                self.folder.set(str(session.directory))
                self.detail.set("Conectado. El panel observa el cliente y controla su marcador.")
                self.refresh()
            except Exception as exc:
                self.session = None
                self.start_button.configure(state="disabled")
                self.capture_button.configure(state="disabled")
                self.targets_button.configure(state="disabled")
                self.status.set("Cliente: sin conexión; estado real sin confirmar")
                self.error(exc)

        def refresh_files(self) -> None:
            if self.directory is None:
                return
            files = marker_state(self.directory)
            self.request.set(
                "Solicitud: caza activada"
                if files.marker_present
                else "Solicitud: caza desactivada"
            )
            self.stop_button.configure(state="normal" if files.marker_present else "disabled")

        def refresh(self) -> None:
            self.start_button.configure(state="disabled")
            self.capture_button.configure(state="disabled")
            self.targets_button.configure(state="disabled")
            self.refresh_files()
            if self.session is None:
                return
            state = self.session.snapshot()
            self.last_state = state
            self.capture_button.configure(state="normal")
            self.targets_button.configure(state="normal")
            self.status.set(f"Cliente: {state.label}")
            if state.auto_battle and state.condition_b > 0 and not state.files.marker_present:
                self.start_button.configure(state="normal")

        def poll(self) -> None:
            try:
                self.refresh()
            except (DiagnosticError, OSError) as exc:
                self.session = None
                self.start_button.configure(state="disabled")
                self.status.set("Cliente: sin confirmación actual")
                self.detail.set(str(exc))
            self.root.after(750, self.poll)

        def start(self) -> None:
            try:
                if self.session is None:
                    raise DiagnosticError("Conecta con el juego antes de iniciar.")
                self.session.start()
                self.detail.set("Inicio solicitado. Esperando la lectura del cliente.")
                self.refresh()
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def stop(self) -> None:
            try:
                if self.directory is None:
                    raise DiagnosticError("Selecciona la carpeta del juego.")
                control_hunting(self.directory, "stop")
                self.detail.set(
                    "Parada solicitada. Espera confirmación; apaga Auto Battle antes de moverte."
                )
                self.refresh_files()
            except (DiagnosticError, OSError) as exc:
                self.error(exc)
                return
            try:
                self.refresh()
            except (DiagnosticError, OSError) as exc:
                self.session = None
                self.start_button.configure(state="disabled")
                self.status.set("Cliente: sin confirmación actual")
                self.detail.set(f"Marcador desactivado. Lectura del cliente no disponible: {exc}")

        def close(self) -> None:
            try:
                active = self.directory is not None and marker_state(self.directory).marker_present
                active = active or bool(
                    self.last_state is not None
                    and self.last_state.auto_battle
                    and self.last_state.condition_b > 0
                    and self.last_state.hunting
                )
            except (DiagnosticError, OSError):
                active = True
            if active and not messagebox.askyesno(
                "Cerrar el panel",
                "La caza puede seguir activada al cerrar el panel. ¿Quieres cerrarlo igualmente?",
            ):
                return
            self.root.destroy()

        def export(self) -> None:
            session = self.session
            if session is None:
                self.error(
                    DiagnosticError("Conecta con el juego antes de exportar el diagnóstico.")
                )
                return
            filename = filedialog.asksaveasfilename(
                title="Guardar diagnóstico de código",
                defaultextension=".zip",
                filetypes=[("Archivo ZIP", "*.zip")],
                initialdir=str(session.directory),
                initialfile=f"Atlantica-contexto-{datetime.now():%Y%m%d-%H%M%S}.zip",
            )
            if not filename:
                return
            try:
                export_code_context(session, Path(filename))
                self.detail.set(
                    f"Diagnóstico guardado en {filename}. "
                    "Adjunta ese ZIP al chat para continuar el análisis."
                )
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def show_targets(self) -> None:
            if self.session is None:
                self.error(DiagnosticError("Conecta con el juego para leer los objetivos."))
                return
            window = tk.Toplevel(self.root)
            window.title("Candidatos de mapa — solo lectura")
            window.minsize(680, 330)
            frame = ttk.Frame(window, padding=12)
            frame.pack(fill="both", expand=True)
            summary = tk.StringVar(value="Consultando...")
            ttk.Label(frame, textvariable=summary, wraplength=650).pack(anchor="w", pady=6)
            columns = ("slot", "kind", "map", "x", "y", "distance")
            table = ttk.Treeview(frame, columns=columns, show="headings", height=10)
            for key, title in zip(
                columns, ("N.º", "ID observado", "Mapa", "X", "Y", "Distancia rejilla"), strict=True
            ):
                table.heading(key, text=title)
                table.column(key, width=100, anchor="center")
            table.pack(fill="both", expand=True)
            last = {}

            def refresh_targets() -> None:
                try:
                    if self.session is None:
                        raise DiagnosticError("El cliente se desconectó; vuelve a conectar.")
                    view = scan_world(self.session)
                    last.clear()
                    last.update(view.summary())
                    table.delete(*table.get_children())
                    if view.player is None:
                        summary.set(
                            "El cliente no está en el estado de mapa que hemos identificado."
                        )
                        return
                    summary.set(
                        f"Jugador: mapa {view.player.map_id}, "
                        f"X={view.player.x}, Y={view.player.y}. "
                        f"{len(view.candidates)} candidatos de {view.observed_entries} entradas; "
                        f"{view.read_errors} lecturas fallidas, "
                        f"{view.changed_entries} entradas cambiadas."
                    )
                    for candidate in view.candidates:
                        table.insert(
                            "",
                            "end",
                            values=(
                                candidate.slot,
                                candidate.kind_id,
                                candidate.map_id,
                                candidate.x,
                                candidate.y,
                                candidate.grid_distance,
                            ),
                        )
                except (DiagnosticError, OSError) as exc:
                    last.clear()
                    table.delete(*table.get_children())
                    summary.set(str(exc))

            def copy_results() -> None:
                if last:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(json.dumps(last, ensure_ascii=False, indent=2))

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x", pady=8)
            ttk.Button(buttons, text="Actualizar", command=refresh_targets).pack(side="left")
            ttk.Button(buttons, text="Copiar resultados", command=copy_results).pack(
                side="left", padx=8
            )
            ttk.Label(
                frame,
                text="Son candidatos; falta validar la acción de ataque.",
                wraplength=650,
            ).pack(anchor="w")
            refresh_targets()

    panel = Panel()
    if smoke_test:
        # Exercise the real packaged GUI without connecting or changing any files.
        panel.root.after(500, panel.root.destroy)
    panel.root.mainloop()
