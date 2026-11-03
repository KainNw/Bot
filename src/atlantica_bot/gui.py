from __future__ import annotations

import json
import queue
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .capture import export_code_context
from .clients import control_native_marker, marker_scope
from .errors import DiagnosticError
from .hunt_loop import HuntWorker
from .hunting import control_hunting, marker_state
from .native_action import try_attack
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
            self.root.minsize(800, 520)
            self.directory: Path | None = None
            self.session: GameSession | None = None
            self.last_state: LiveState | None = None
            self.system = WindowsSystem()
            self.windows = {}
            self.window_choice = tk.StringVar()
            self.last_trial = {}
            self.trial_unknown = False
            self.bot_worker: HuntWorker | None = None
            self.bot_report = {}
            self.closing = False
            self.bot_status = tk.StringVar(value="Bot detenido.")
            self.pid = tk.StringVar()
            self.folder = tk.StringVar(value="Conecta con el juego o selecciona su carpeta.")
            self.request = tk.StringVar(value="Solicitud: sin consultar")
            self.status = tk.StringVar(value="Cliente: sin conexión")
            self.detail = tk.StringVar(value="El panel abre sin activar la caza.")
            self.scope_status = tk.StringVar()
            frame = ttk.Frame(self.root, padding=18)
            frame.pack(fill="both", expand=True)
            ttk.Label(frame, text="Control de caza", font=("Segoe UI", 18)).pack(anchor="w")
            ttk.Label(
                frame,
                text="Iniciar bot ataca mobs cercanos con Auto Battle apagado.",
            ).pack(anchor="w", pady=4)
            ttk.Label(frame, textvariable=self.folder, wraplength=680).pack(anchor="w", pady=8)
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=4)
            self.window_list = ttk.Combobox(
                row, textvariable=self.window_choice, state="readonly", width=65
            )
            self.window_list.pack(side="left", fill="x", expand=True)
            self.window_list.bind("<<ComboboxSelected>>", self.choose_window)
            self.list_button = ttk.Button(row, text="Actualizar lista", command=self.list_windows)
            self.list_button.pack(side="left", padx=8)
            self.pick_button = ttk.Button(row, text="Elegir ventana", command=self.pick_window)
            self.pick_button.pack(side="left")
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=4)
            self.browse_button = ttk.Button(row, text="Seleccionar carpeta", command=self.browse)
            self.browse_button.pack(side="left")
            ttk.Label(row, text="PID opcional:").pack(side="left", padx=(12, 4))
            self.pid_entry = ttk.Entry(row, textvariable=self.pid, width=9)
            self.pid_entry.pack(side="left")
            self.connect_button = ttk.Button(row, text="Conectar", command=self.connect)
            self.connect_button.pack(side="left", padx=8)
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=10)
            self.bot_start_button = ttk.Button(
                row, text="Iniciar bot", command=self.start_bot, state="disabled"
            )
            self.bot_start_button.pack(side="left")
            self.bot_stop_button = ttk.Button(
                row, text="Parar bot", command=self.stop_bot, state="disabled"
            )
            self.bot_stop_button.pack(side="left", padx=10)
            self.bot_copy_button = ttk.Button(
                row, text="Copiar estado del bot", command=self.copy_bot, state="disabled"
            )
            self.bot_copy_button.pack(side="left")
            ttk.Label(
                frame, textvariable=self.bot_status, font=("Segoe UI", 12, "bold"), wraplength=760
            ).pack(anchor="w", pady=4)
            read_row = ttk.Frame(frame)
            read_row.pack(fill="x", pady=6)
            self.advanced = ttk.Frame(frame)
            self.more_button = ttk.Button(
                frame,
                text="Más controles: caza nativa y prueba individual",
                command=self.toggle_advanced,
            )
            self.more_button.pack(anchor="w", pady=4)
            row = ttk.Frame(self.advanced)
            row.pack(fill="x", pady=6)
            self.start_button = ttk.Button(
                row, text="Activar caza nativa", command=self.start, state="disabled"
            )
            self.start_button.pack(side="left", padx=(0, 10))
            self.stop_button = ttk.Button(
                row, text="Parar caza nativa", command=self.stop, state="disabled"
            )
            self.stop_button.pack(side="left")
            self.capture_button = ttk.Button(
                read_row, text="Exportar diagnóstico", command=self.export, state="disabled"
            )
            self.capture_button.pack(side="left", padx=10)
            self.targets_button = ttk.Button(
                read_row, text="Ver objetivos", command=self.show_targets, state="disabled"
            )
            self.targets_button.pack(side="left")
            row = ttk.Frame(self.advanced)
            row.pack(fill="x", pady=4)
            self.trial_button = ttk.Button(
                row,
                text="Probar un ataque (experimental)",
                command=self.attack_once,
                state="disabled",
            )
            self.trial_button.pack(side="left")
            self.copy_trial_button = ttk.Button(
                row, text="Copiar prueba", command=self.copy_trial, state="disabled"
            )
            self.copy_trial_button.pack(side="left", padx=8)
            ttk.Label(self.advanced, textvariable=self.scope_status, wraplength=760).pack(
                anchor="w"
            )
            ttk.Label(self.advanced, textvariable=self.request).pack(anchor="w", pady=4)
            ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 12, "bold")).pack(
                anchor="w", pady=4
            )
            ttk.Label(frame, textvariable=self.detail, wraplength=680).pack(anchor="w", pady=8)
            ttk.Label(
                frame,
                text="Para moverte, pulsa Parar bot y espera a que se detenga.\n"
                "Durante el combate, el bot espera: los turnos siguen siendo manuales.",
                wraplength=680,
            ).pack(anchor="w", pady=10)
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.pid.trace_add("write", self.pid_changed)
            if not smoke_test:
                self.root.after(100, self.list_windows)
            self.root.after(750, self.poll)
            self.root.after(100, self.poll_bot)

        def disconnect(self) -> None:
            self.stop_bot()
            self.session = None
            self.directory = None
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self.capture_button.configure(state="disabled")
            self.targets_button.configure(state="disabled")
            self.trial_button.configure(state="disabled")
            self.bot_start_button.configure(state="disabled")
            self.status.set("Cliente: sin conexión; selecciona y pulsa Conectar")
            self.folder.set("Selecciona una ventana y pulsa Conectar.")
            self.scope_status.set("")
            self.request.set("Solicitud: sin consultar")
            if self.bot_worker is None:
                self.bot_status.set("Bot detenido; sin conexión.")

        def toggle_advanced(self) -> None:
            if self.advanced.winfo_manager():
                self.advanced.pack_forget()
            else:
                self.advanced.pack(fill="x", pady=6, after=self.more_button)

        def lock_target_controls(self) -> None:
            active = self.bot_worker is not None or self.closing
            self.window_list.configure(state="disabled" if active else "readonly")
            for button in (
                self.list_button,
                self.pick_button,
                self.browse_button,
                self.connect_button,
                self.pid_entry,
            ):
                button.configure(state="disabled" if active else "normal")
            self.bot_stop_button.configure(
                state="normal" if self.bot_worker is not None else "disabled"
            )
            if active:
                self.bot_start_button.configure(state="disabled")
                self.start_button.configure(state="disabled")
                self.stop_button.configure(state="disabled")
                self.trial_button.configure(state="disabled")

        def require_idle_bot(self) -> None:
            if self.bot_worker is not None or self.closing:
                raise DiagnosticError(
                    "Espera a que Parar bot termine antes de cambiar el cliente o modo."
                )

        def target_is_editable(self) -> bool:
            if self.bot_worker is not None or self.closing:
                self.detail.set(
                    "Pulsa Parar bot y espera a que termine antes de cambiar el cliente."
                )
                return False
            return True

        def selected_window(self, session: GameSession):
            window = self.windows.get(self.window_choice.get())
            if window is None or window.pid != session.process.pid:
                windows = [w for w in self.system.game_windows() if w.pid == session.process.pid]
                if len(windows) != 1:
                    raise DiagnosticError("Usa Elegir ventana para identificar el cliente exacto.")
                window = windows[0]
            return window

        def start_bot(self) -> None:
            try:
                self.require_idle_bot()
                session = self.session
                if session is None:
                    raise DiagnosticError("Conecta con la ventana elegida antes de iniciar el bot.")
                if self.trial_unknown:
                    raise DiagnosticError("Comprueba la solicitud anterior y vuelve a conectar.")
                state = session.snapshot()
                if state.auto_battle or state.hunting or state.files.marker_present:
                    raise DiagnosticError(
                        "Deja Auto Battle y caza nativa apagados para iniciar el bot."
                    )
                worker = HuntWorker(session, self.selected_window(session))
                self.bot_report = worker.engine.summary()
                self.bot_worker = worker
                self.bot_status.set(f"PID {session.process.pid}: iniciando bot...")
                worker.start()
                self.lock_target_controls()
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def stop_bot(self) -> None:
            worker = self.bot_worker
            if worker is not None:
                self.bot_status.set(
                    f"PID {worker.window.pid}: deteniendo bot; esperando la solicitud en curso..."
                )
                try:
                    worker.stop()
                except DiagnosticError as exc:
                    self.detail.set(str(exc))

        def poll_bot(self) -> None:
            worker = self.bot_worker
            if worker is not None:
                try:
                    while True:
                        self.bot_report = worker.events.get_nowait()
                except queue.Empty:
                    pass
                if not worker.alive:
                    self.bot_report = worker.engine.summary()
                    self.trial_unknown |= self.bot_report["needs_reconnect"]
                    self.bot_worker = None
                    self.lock_target_controls()
                if self.bot_report:
                    info = self.bot_report
                    message = info["message"]
                    if worker.alive and worker.stop_event.is_set():
                        message = "Deteniendo; puede completarse la solicitud en curso."
                    self.bot_status.set(
                        f"PID {info['pid']}: {message} "
                        f"Enviadas: {info['queued']}; "
                        f"combates observados: {info['battles_observed']}."
                    )
                    self.bot_copy_button.configure(state="normal")
                    self.bot_copy_button.configure(text=f"Copiar estado PID {info['pid']}")
            self.root.after(100, self.poll_bot)

        def copy_bot(self) -> None:
            if self.bot_report:
                self.root.clipboard_clear()
                self.root.clipboard_append(
                    json.dumps(
                        {"tool_version": __version__, **self.bot_report},
                        ensure_ascii=False,
                        indent=2,
                    )
                )

        def pid_changed(self, *args) -> None:
            selected = self.windows.get(self.window_choice.get())
            if selected is not None and self.pid.get().strip() != str(selected.pid):
                self.window_choice.set("")
            if self.session is not None and self.pid.get().strip() != str(self.session.process.pid):
                self.disconnect()

        def list_windows(self) -> None:
            try:
                self.windows = {window.label: window for window in self.system.game_windows()}
                self.window_list.configure(values=list(self.windows))
                if self.window_choice.get() not in self.windows:
                    self.window_choice.set("")
                self.detail.set(
                    f"{len(self.windows)} ventanas encontradas. Elige una y pulsa Conectar. "
                    "Elegir ventana te da 3 segundos para activarla con Alt+Tab "
                    "o desde su barra de título."
                )
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def choose_window(self, event=None) -> None:
            if not self.target_is_editable():
                return
            window = self.windows.get(self.window_choice.get())
            if window is not None:
                self.disconnect()
                self.pid.set(str(window.pid))
                self.detail.set(f"Seleccionado: {window.label}. Pulsa Conectar.")

        def pick_window(self) -> None:
            if not self.target_is_editable():
                return
            self.disconnect()
            self.root.iconify()

            def capture_active() -> None:
                try:
                    window = self.system.active_game_window()
                    self.windows[window.label] = window
                    self.window_list.configure(values=list(self.windows))
                    self.window_choice.set(window.label)
                    self.choose_window()
                except (DiagnosticError, OSError) as exc:
                    self.detail.set(str(exc))
                finally:
                    self.root.deiconify()

            self.root.after(3000, capture_active)

        def error(self, exc: Exception) -> None:
            self.detail.set(str(exc))
            messagebox.showerror("Control de caza", str(exc))

        def browse(self) -> None:
            if not self.target_is_editable():
                return
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
                self.trial_button.configure(state="disabled")
                self.bot_start_button.configure(state="disabled")
                self.folder.set(str(directory))
                self.status.set("Cliente: sin conexión; estado real sin confirmar")
                self.refresh_files()
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def connect(self) -> None:
            from .__main__ import positive_pid

            if not self.target_is_editable():
                return
            self.disconnect()
            try:
                pid = positive_pid(self.pid.get().strip()) if self.pid.get().strip() else None
                session = GameSession.connect(self.system, pid)
                self.pid.set(str(session.process.pid))
                self.session = session
                self.trial_unknown = False
                self.directory = session.directory
                self.folder.set(str(session.directory))
                self.detail.set(
                    f"Conectado al PID {session.process.pid}. "
                    "Las lecturas quedan vinculadas a ese cliente."
                )
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
            scope = marker_scope(self.system, self.directory)
            self.scope_status.set(scope.explanation)
            if not scope.allowed:
                self.stop_button.configure(state="disabled")

        def refresh(self) -> None:
            self.start_button.configure(state="disabled")
            self.capture_button.configure(state="disabled")
            self.targets_button.configure(state="disabled")
            self.trial_button.configure(state="disabled")
            self.bot_start_button.configure(state="disabled")
            self.refresh_files()
            if self.session is None:
                self.lock_target_controls()
                return
            state = self.session.snapshot()
            self.last_state = state
            self.capture_button.configure(state="normal")
            self.targets_button.configure(state="normal")
            if not (
                state.auto_battle
                or state.hunting
                or state.files.marker_present
                or self.trial_unknown
            ):
                self.trial_button.configure(state="normal")
                self.bot_start_button.configure(state="normal")
            self.status.set(f"PID {self.session.process.pid}: {state.label}")
            scope = marker_scope(self.system, self.directory)
            if (
                scope.allowed
                and state.auto_battle
                and state.condition_b > 0
                and not state.files.marker_present
            ):
                self.start_button.configure(state="normal")
            self.lock_target_controls()

        def poll(self) -> None:
            try:
                self.refresh()
            except (DiagnosticError, OSError) as exc:
                self.disconnect()
                self.status.set("Cliente: sin confirmación actual")
                self.detail.set(str(exc))
            self.root.after(750, self.poll)

        def start(self) -> None:
            try:
                self.require_idle_bot()
                if self.session is None:
                    raise DiagnosticError("Conecta con el juego antes de iniciar.")
                self.session.start()
                self.detail.set("Inicio solicitado. Esperando la lectura del cliente.")
                self.refresh()
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def stop(self) -> None:
            try:
                self.require_idle_bot()
                if self.directory is None:
                    raise DiagnosticError("Selecciona la carpeta del juego.")
                if self.session is not None:
                    self.session.stop()
                else:
                    control_native_marker(self.system, self.directory, "stop")
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
            if self.closing:
                return
            self.stop_bot()
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
            self.closing = True
            self.lock_target_controls()

            def finish_close() -> None:
                if self.bot_worker is not None and self.bot_worker.alive:
                    self.root.after(100, finish_close)
                else:
                    self.root.destroy()

            finish_close()

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
                initialfile=f"Atlantica-PID{session.process.pid}-contexto-{datetime.now():%Y%m%d-%H%M%S}.zip",
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

        def attack_once(self) -> None:
            session = self.session
            if session is None:
                self.error(DiagnosticError("Conecta con la ventana elegida antes de probar."))
                return
            self.trial_button.configure(state="disabled")
            try:
                self.require_idle_bot()
                window = self.selected_window(session)
                view = scan_world(session)
                if not view.candidates:
                    raise DiagnosticError(
                        "No hay candidatos de mapa; acércate a un mob y actualiza."
                    )
                self.detail.set(
                    f"Prueba individual en PID {session.process.pid}; esperando al cliente..."
                )
                self.root.update_idletasks()
                self.last_trial = try_attack(session, window, view.candidates[0])
                self.trial_unknown = self.last_trial["status"] in (1, 10, 11)
                self.copy_trial_button.configure(state="normal")
                self.copy_trial_button.configure(text=f"Copiar prueba PID {session.process.pid}")
                self.detail.set(f"PID {session.process.pid}: {self.last_trial['message']}")
            except (DiagnosticError, OSError) as exc:
                self.trial_unknown = True
                self.last_trial = {
                    "pid": session.process.pid,
                    "result": "unconfirmed",
                    "message": str(exc),
                }
                self.copy_trial_button.configure(state="normal")
                self.copy_trial_button.configure(text=f"Copiar prueba PID {session.process.pid}")
                self.error(exc)
            finally:
                self.trial_button.configure(state="disabled")

        def copy_trial(self) -> None:
            if self.last_trial:
                self.root.clipboard_clear()
                self.root.clipboard_append(
                    json.dumps(self.last_trial, ensure_ascii=False, indent=2)
                )

        def show_targets(self) -> None:
            if self.session is None:
                self.error(DiagnosticError("Conecta con el juego para leer los objetivos."))
                return
            selected_session = self.session
            window = tk.Toplevel(self.root)
            window.title(f"PID {selected_session.process.pid} — candidatos de mapa")
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
                    if self.session is not selected_session:
                        raise DiagnosticError(
                            "La conexión cambió. Cierra este visor y abre el del cliente elegido."
                        )
                    view = scan_world(selected_session)
                    last.clear()
                    last.update(view.summary())
                    last["pid"] = selected_session.process.pid
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
                        f"{view.changed_entries} punteros cambiados, "
                        f"{view.inactive_entries} entradas inactivas omitidas."
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
        panel.toggle_advanced()
        panel.root.update_idletasks()
        panel.toggle_advanced()
        panel.root.after(500, panel.root.destroy)
    panel.root.mainloop()
