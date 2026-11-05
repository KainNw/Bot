from __future__ import annotations

import json
import queue
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import __version__
from .battle import BattleTrial, read_battle_frame
from .battle_context import read_normal_battle
from .bonus import BONUS_LABELS, BonusComparison, capture_bonus_snapshot, read_bonus_code
from .capture import export_code_context
from .clients import control_native_marker, marker_scope
from .combat import SAMPLES_PER_STAGE, CombatCalibration, CombatDetector
from .errors import DiagnosticError, SceneChanged, WindowUnavailable
from .hunt_loop import HuntWorker
from .hunting import control_hunting, marker_state
from .native_action import try_attack, try_battle_action
from .navigation import ApproachSettings, calibrated_radius
from .overview import OverviewWindow
from .panel_view import build_panel
from .profiles import (
    ACTION_LABELS,
    TARGET_LABELS,
    WORLD_ATTACK_LABELS,
    BotProfile,
    Mercenary,
    ProfileStore,
    member_label,
)
from .session import GameSession, LiveState
from .speed_trial import SpeedExperiment, prepare_speed_plan
from .turns import roster_rows
from .ui_theme import page_heading
from .world import observe_scene, scan_world


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
            self.root.minsize(840, 630)
            self.directory: Path | None = None
            self.session: GameSession | None = None
            self.last_state: LiveState | None = None
            self.system = WindowsSystem()
            self.windows = {}
            self.window_choice = tk.StringVar()
            self.last_trial = {}
            self.trial_unknown = False
            self.battle_trials = set()
            self.bot_worker: HuntWorker | None = None
            self.bot_report = {}
            self.closing = False
            self.calibrating = False
            self.calibration_window = None
            self.bonus_window = None
            self.speed_window = None
            self.speed_experiment = None
            self.profile_editor = None
            self.overview: OverviewWindow | None = None
            self.detector: CombatDetector | None = None
            self.profile_store = ProfileStore.for_windows()
            self.profile: BotProfile | None = None
            self.profile_number = tk.StringVar(value="1")
            self.profile_status = tk.StringVar()
            self.detector_status = tk.StringVar(
                value="Detector de combate: conecta con el cliente."
            )
            self.world_attack_mode = tk.StringVar(value=WORLD_ATTACK_LABELS["native"])
            self.turns_enabled = tk.BooleanVar(value=False)
            self.team_status = tk.StringVar(value="Conecta para consultar el equipo.")
            self.search_radius = tk.StringVar(value="60")
            self.attack_delay = tk.StringVar(value="0")
            self.collect_loot = tk.BooleanVar(value=False)
            self.battle_speed_enabled = tk.BooleanVar(value=False)
            self.battle_speed_rate = tk.StringVar(value="1.25")
            self.battle_speed_status = tk.StringVar(value="Speed desactivado")
            self.bot_status = tk.StringVar(value="Bot detenido.")
            self.execution_status = tk.StringVar()
            self.pid = tk.StringVar()
            self.folder = tk.StringVar(value="Conecta con el juego o selecciona su carpeta.")
            self.request = tk.StringVar(value="Solicitud: sin consultar")
            self.status = tk.StringVar(value="Cliente: sin conexión")
            self.detail = tk.StringVar(value="El panel abre sin activar la caza.")
            self.scope_status = tk.StringVar()
            self.main_alias = tk.StringVar()
            self.header_name = tk.StringVar(value="Main sin identificar")
            self.header_context = tk.StringVar(value="Sin conexión")
            self.run_phase = tk.StringVar(value="Bot detenido")
            self.run_summary = tk.StringVar(value="Speed apagado")
            self.main_aliases: dict[tuple[int, int], str] = {}
            self.identity_key: tuple[int, int] | None = None
            build_panel(self)
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.pid.trace_add("write", self.pid_changed)
            self.turns_enabled.trace_add("write", self.update_execution_mode)
            self.collect_loot.trace_add("write", self.update_execution_mode)
            self.main_alias.trace_add("write", self.alias_changed)
            self.status.trace_add("write", self.sync_identity)
            self.bot_status.trace_add("write", self.sync_identity)
            self.profile_number.trace_add("write", self.sync_identity)
            self.load_profile()
            self.sync_identity()
            if not smoke_test:
                self.root.after(100, self.list_windows)
            self.root.after(750, self.poll)
            self.root.after(100, self.poll_bot)
            if not smoke_test:
                self.root.after(1000, self.poll_team)

        def build_team_tab(self) -> None:
            page_heading(
                self.team_tab,
                "Main y mercenarios",
                "Equipo presente, prioridad y acciones del perfil para los nueve puestos.",
            )
            body = ttk.Frame(self.team_tab, padding=16)
            body.pack(fill="both", expand=True)
            ttk.Label(
                body, textvariable=self.team_status, style="Muted.TLabel", wraplength=880
            ).pack(anchor="w", pady=6)
            columns = (
                "number",
                "name",
                "life",
                "present",
                "enabled",
                "priority",
                "opening",
                "later",
                "target",
                "order",
            )
            table = ttk.Frame(body)
            self.team_tree = ttk.Treeview(table, columns=columns, show="headings", height=9)
            self.team_tree.tag_configure("main", foreground="#f1cd83")
            self.team_tree.tag_configure("alternate", background="#1b2b42")
            for key, label, width in (
                ("number", "Miembro", 110),
                ("name", "Nombre del perfil", 135),
                ("life", "Vida actual", 85),
                ("present", "En combate", 95),
                ("enabled", "Usar bot", 75),
                ("priority", "Orden", 55),
                ("opening", "Primer turno", 125),
                ("later", "Después", 125),
                ("target", "Objetivo de magia", 135),
                ("order", "Última orden", 250),
            ):
                self.team_tree.heading(key, text=label)
                self.team_tree.column(key, width=width, minwidth=50)
            self.team_tree.pack(side="left", fill="both", expand=True)
            vertical = ttk.Scrollbar(table, orient="vertical", command=self.team_tree.yview)
            vertical.pack(side="right", fill="y")
            self.team_tree.configure(yscrollcommand=vertical.set)
            scrollbar = ttk.Scrollbar(body, orient="horizontal", command=self.team_tree.xview)
            self.team_tree.configure(xscrollcommand=scrollbar.set)
            buttons = ttk.Frame(body)
            buttons.pack(side="bottom", fill="x", pady=(12, 0))
            ttk.Button(buttons, text="Actualizar equipo", command=self.refresh_team).pack(
                side="left"
            )
            ttk.Button(buttons, text="Configurar mercenarios", command=self.edit_profile).pack(
                side="left", padx=8
            )
            ttk.Button(buttons, text="Vista general", command=self.show_overview).pack(side="left")
            ttk.Button(buttons, text="Usar/omitir", command=self.toggle_team_member).pack(
                side="left", padx=8
            )
            ttk.Button(buttons, text="Prueba individual", command=self.show_members).pack(
                side="left", padx=8
            )
            scrollbar.pack(side="bottom", fill="x", pady=(8, 0))
            table.pack(fill="both", expand=True, pady=(8, 0))
            self.paint_team(
                roster_rows(BotProfile.default(1), None),
                "Conecta con el cliente para leer la batalla.",
            )

        def paint_team(self, rows: list[dict], message: str) -> None:
            self.team_status.set(message)
            for row in rows:
                present = (
                    "Sin batalla"
                    if row["present"] is None
                    else "No presente"
                    if not row["present"]
                    else "Caído"
                    if not row["alive"]
                    else "Sí"
                )
                values = (
                    row["label"],
                    row["name"],
                    row.get("life") if row.get("life") is not None else "—",
                    present,
                    "Sí" if row["enabled"] else "No",
                    row["priority"],
                    row["opening_action"],
                    row["later_action"],
                    row["target"],
                    row["last_order"],
                )
                item = f"merc_{row['slot']}"
                if self.team_tree.exists(item):
                    self.team_tree.item(item, values=values)
                else:
                    tag = (
                        "main" if row["slot"] == 1 else "alternate" if row["slot"] % 2 == 0 else ""
                    )
                    self.team_tree.insert("", "end", iid=item, values=values, tags=(tag,))
            if self.overview is not None and self.overview.alive:
                self.overview.paint(
                    rows, message, pid=self.session.process.pid if self.session else None
                )

        def alias_changed(self, *_) -> None:
            if self.identity_key is not None:
                self.main_aliases[self.identity_key] = " ".join(self.main_alias.get().split())[:48]
            self.render_identity()

        def sync_identity(self, *_) -> None:
            key = (self.session.process.pid, self.session.creation_time) if self.session else None
            if key != self.identity_key:
                self.identity_key = key
                self.main_alias.set(self.main_aliases.get(key, ""))
            self.alias_entry.configure(state="normal" if key else "disabled")
            self.render_identity()

        def render_identity(self) -> None:
            alias = " ".join(self.main_alias.get().split())[:48]
            name = alias or "Main sin identificar"
            self.header_name.set(name if len(name) <= 26 else name[:25] + "…")
            if self.session is not None:
                pid = self.session.process.pid
                self.header_context.set(f"PID {pid}  ·  Perfil {self.profile_number.get()}")
                self.header_badge.configure(style="Connected.TLabel")
                self.root.title(f"{name} — PID {pid} — Atlantica {__version__}")
            else:
                self.header_context.set("Sin conexión")
                self.header_badge.configure(style="Disconnected.TLabel")
                self.root.title(f"Atlantica — Panel del bot {__version__}")
            worker = self.bot_worker
            phase = self.bot_report.get("phase") if worker else "stopped"
            labels = {
                "stopped": "Bot detenido",
                "battle": "En combate",
                "searching": "Buscando mobs",
                "manual_movement": "Movimiento manual",
                "attack_delay": "Esperando para atacar",
                "waiting_battle": "Esperando combate",
                "native_pursuit": "Persiguiendo mob",
            }
            stopping = worker is not None and worker.stop_event.is_set()
            self.run_phase.set("Deteniendo bot…" if stopping else labels.get(phase, "Bot activo"))
            self.run_badge.configure(
                style="Stopping.Run.TLabel"
                if stopping
                else "Run.TLabel"
                if worker
                else "Idle.Run.TLabel"
            )
            report = self.bot_report
            if (
                self.session is None
                or report.get("pid") != self.session.process.pid
                or report.get("detector", {}).get("instance_creation_time")
                != self.session.creation_time
            ):
                report = {}
            speed = report.get("speed", {})
            rate = speed.get("current_rate")
            speed_label = (
                f"Speed {rate:g}×"
                if speed.get("enabled") and isinstance(rate, (int, float))
                else "Speed apagado"
            )
            self.run_summary.set(f"{report.get('battles_observed', 0)} combates  ·  {speed_label}")
            if self.overview is not None and self.overview.alive:
                self.overview.set_main_name(alias)

        def show_overview(self) -> None:
            if self.overview is not None and self.overview.alive:
                self.overview.window.deiconify()
                self.overview.window.lift()
            else:
                self.overview = OverviewWindow(
                    self.root,
                    execute_turns=self.turns_enabled,
                    profile_number=self.profile_number,
                    on_profile=self.load_profile,
                    on_start=self.start_bot,
                    on_stop=self.stop_bot,
                    on_configure=self.edit_profile,
                    on_refresh=self.refresh_team,
                    on_copy=self.copy_bot,
                    attack_delay=self.attack_delay,
                    search_radius=self.search_radius,
                    collect_loot=self.collect_loot,
                    on_save=self.save_hunt_options,
                    on_calibrate=self.calibrate_radius,
                    world_attack_mode=self.world_attack_mode,
                    on_capture_bonus=self.capture_bonus,
                )
            self.refresh_team()
            self.sync_overview_controls()

        def sync_overview_controls(self) -> None:
            self.update_execution_mode()
            if self.overview is None or not self.overview.alive:
                return
            editable = (
                self.bot_worker is None
                and not self.closing
                and not self.calibrating
                and not self.bonus_open()
                and not self.speed_open()
            )
            self.overview.set_controls(
                start=editable and str(self.bot_start_button.cget("state")) == "normal",
                stop=self.bot_worker is not None and not self.closing,
                editable=editable,
            )
            self.overview.set_main_name(self.main_alias.get())
            report = self.bot_report
            if (
                self.session is None
                or report.get("pid") != self.session.process.pid
                or report.get("detector", {}).get("instance_creation_time")
                != self.session.creation_time
            ):
                report = {}
            self.overview.set_run_status(
                self.bot_status.get() if report else "Bot detenido.", report
            )

        def update_execution_mode(self, *_) -> None:
            worker = self.bot_worker
            automatic = worker.engine.execute_turns if worker else self.turns_enabled.get()
            loot = (
                worker.engine.profile.collect_remaining_loot if worker else self.collect_loot.get()
            )
            self.execution_status.set(
                (
                    "Combate automático: básicos y magias del perfil."
                    if automatic
                    else "Turnos manuales: el bot no ejecutará básicos ni magias."
                )
                + (" Recogida restante: activa." if loot else "")
            )
            if self.overview is not None and self.overview.alive:
                self.overview.set_turn_mode(automatic)

        def refresh_team(self) -> None:
            profile = self.profile or BotProfile.default(1)
            try:
                if self.session is None:
                    self.paint_team(
                        roster_rows(profile, None),
                        "Conecta con el cliente para consultar el equipo.",
                    )
                    return
                if self.bot_worker is not None and self.bot_worker.engine.execute_turns:
                    combat = self.bot_report.get("combat", {})
                    rows = (
                        combat.get("roster") if self.bot_report.get("phase") == "battle" else None
                    )
                    self.paint_team(
                        rows or roster_rows(profile, None),
                        combat.get("message", "Esperando equipo."),
                    )
                    return
                observation = observe_scene(self.session)
                view = (
                    read_battle_frame(self.session)
                    if self.detector and self.detector.classify(observation) == "battle"
                    else None
                )
                rows = roster_rows(profile, view)
                count = sum(row["present"] is True for row in rows)
                self.paint_team(
                    rows,
                    f"PID {self.session.process.pid}: {count} presentes en batalla. "
                    "El bot usa los presentes que estén habilitados en el perfil.",
                )
            except (DiagnosticError, OSError) as exc:
                self.paint_team(roster_rows(profile, None), f"Lectura de equipo pendiente: {exc}")

        def poll_team(self) -> None:
            if self.closing:
                return
            if self.tabs.select() == str(self.team_tab) or (
                self.overview is not None and self.overview.alive
            ):
                self.refresh_team()
            self.root.after(1000, self.poll_team)

        def toggle_team_member(self) -> None:
            try:
                self.require_idle_bot()
                selected = self.team_tree.selection()
                if not selected or self.profile is None:
                    raise DiagnosticError("Selecciona un mercenario de la tabla.")
                slot = int(selected[0].removeprefix("merc_"))
                profile = replace(
                    self.profile,
                    mercenaries=tuple(
                        replace(m, enabled=not m.enabled) if m.slot == slot else m
                        for m in self.profile.mercenaries
                    ),
                )
                self.profile_store.save(profile)
                self.load_profile()
                self.refresh_team()
            except (DiagnosticError, OSError, ValueError) as exc:
                self.error(exc)

        def disconnect(self) -> None:
            if self.speed_experiment is not None and self.speed_experiment.active:
                try:
                    self.speed_experiment.restore()
                except (DiagnosticError, OSError) as exc:
                    self.detail.set(f"Conservando la conexión para restaurar la escala: {exc}")
                    return
            self.stop_bot()
            self.session = None
            self.directory = None
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self.capture_button.configure(state="disabled")
            self.combat_capture_button.configure(state="disabled")
            self.members_button.configure(state="disabled")
            self.targets_button.configure(state="disabled")
            self.trial_button.configure(state="disabled")
            self.bot_start_button.configure(state="disabled")
            self.calibration_button.configure(state="disabled")
            self.detector_status.set("Detector de combate: conecta con la ventana elegida.")
            self.status.set("Cliente: sin conexión; selecciona y pulsa Conectar")
            self.folder.set("Selecciona una ventana y pulsa Conectar.")
            self.scope_status.set("")
            self.request.set("Solicitud: sin consultar")
            if self.bot_worker is None:
                self.bot_status.set("Bot detenido; sin conexión.")
            self.paint_team(
                roster_rows(self.profile or BotProfile.default(1), None),
                "Conecta con el cliente para consultar el equipo.",
            )
            self.sync_overview_controls()

        def toggle_advanced(self) -> None:
            if self.advanced.winfo_manager():
                self.advanced.pack_forget()
                self.more_button.configure(text="Mostrar controles avanzados")
            else:
                self.advanced.pack(fill="x", pady=6, after=self.more_button)
                self.more_button.configure(text="Ocultar controles avanzados")

        def lock_target_controls(self) -> None:
            active = (
                self.bot_worker is not None
                or self.closing
                or self.calibrating
                or self.bonus_open()
                or self.speed_open()
            )
            self.window_list.configure(state="disabled" if active else "readonly")
            self.profile_list.configure(state="disabled" if active else "readonly")
            self.attack_mode_list.configure(state="disabled" if active else "readonly")
            self.battle_speed_list.configure(state="disabled" if active else "readonly")
            for button in (
                self.list_button,
                self.pick_button,
                self.browse_button,
                self.connect_button,
                self.pid_entry,
                self.profile_button,
                self.turns_check,
                self.radius_entry,
                self.radius_calibrate_button,
                self.delay_entry,
                self.loot_check,
                self.battle_speed_check,
                self.save_hunt_button,
            ):
                button.configure(state="disabled" if active else "normal")
            self.bot_stop_button.configure(
                state="normal" if self.bot_worker is not None else "disabled"
            )
            if active:
                for button in (
                    self.capture_button,
                    self.combat_capture_button,
                    self.members_button,
                    self.targets_button,
                ):
                    button.configure(state="disabled")
                self.bot_start_button.configure(state="disabled")
                self.start_button.configure(state="disabled")
                self.stop_button.configure(state="disabled")
                self.trial_button.configure(state="disabled")
                self.calibration_button.configure(state="disabled")
            self.sync_overview_controls()

        def bonus_open(self) -> bool:
            return self.bonus_window is not None and bool(self.bonus_window.winfo_exists())

        def speed_open(self) -> bool:
            return self.speed_window is not None and bool(self.speed_window.winfo_exists())

        def require_idle_bot(self, *, allow_bonus: bool = False, allow_speed: bool = False) -> None:
            if self.speed_open() and not allow_speed:
                raise DiagnosticError(
                    "Cierra la prueba de velocidad antes de iniciar o cambiar de cliente."
                )
            if self.bonus_open() and not allow_bonus:
                raise DiagnosticError(
                    "Cierra la captura de bonus antes de cambiar el cliente o iniciar el bot."
                )
            if self.bot_worker is not None or self.closing or self.calibrating:
                raise DiagnosticError(
                    "Espera a que Parar bot termine antes de cambiar el cliente o modo."
                )

        def target_is_editable(self) -> bool:
            if (
                self.bot_worker is not None
                or self.closing
                or self.calibrating
                or self.bonus_open()
                or self.speed_open()
            ):
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
                if self.detector is None or not self.detector.matches(
                    session.process.pid, session.creation_time
                ):
                    raise DiagnosticError("Usa Calibrar combate antes de iniciar el ciclo.")
                if self.profile is None:
                    raise DiagnosticError("Revisa la configuración del perfil antes de iniciar.")
                profile = self.configured_profile(self.profile)
                worker = HuntWorker(
                    session,
                    self.selected_window(session),
                    self.detector,
                    profile,
                    ApproachSettings(False, profile.search_radius),
                    native_attack=profile.world_attack_mode == "native",
                    execute_turns=self.turns_enabled.get(),
                    battle_ledger=self.battle_trials,
                )
                self.profile_store.save(profile)
                self.profile = profile
                self.bot_report = worker.engine.summary()
                self.bot_worker = worker
                self.bot_status.set(f"PID {session.process.pid}: iniciando bot...")
                worker.start()
                self.lock_target_controls()
            except (DiagnosticError, OSError, ValueError) as exc:
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
                    speed = info.get("speed", {})
                    current_rate = speed.get("current_rate")
                    self.battle_speed_status.set(
                        "Speed: "
                        + (
                            f"{current_rate:g}× · "
                            if isinstance(current_rate, (int, float))
                            else ""
                        )
                        + speed.get("message", "Desactivado")
                    )
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
            self.sync_overview_controls()
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

        def load_profile(self, event=None) -> None:
            try:
                self.require_idle_bot()
                self.profile = self.profile_store.load(int(self.profile_number.get()))
                self.attack_delay.set(f"{self.profile.attack_delay_seconds:g}")
                self.search_radius.set(str(self.profile.search_radius))
                self.collect_loot.set(self.profile.collect_remaining_loot)
                self.battle_speed_enabled.set(self.profile.battle_speed_enabled)
                self.battle_speed_rate.set(f"{self.profile.battle_speed_rate:g}")
                self.world_attack_mode.set(WORLD_ATTACK_LABELS[self.profile.world_attack_mode])
                count = sum(merc.enabled for merc in self.profile.mercenaries)
                magic_count = sum(
                    merc.enabled and merc.action != "basic" for merc in self.profile.mercenaries
                )
                self.profile_status.set(
                    f"Perfil {self.profile.number}: {count} habilitados, {magic_count} con magia. "
                    + (
                        "Magia solo en primer turno; básicos después."
                        if self.profile.magic_first_turn_only
                        else "Repetir la acción configurada por turno."
                    )
                )
            except (DiagnosticError, OSError, ValueError) as exc:
                self.profile = None
                self.profile_status.set(f"No se pudo cargar el perfil: {exc}")
            self.paint_team(
                roster_rows(self.profile or BotProfile.default(1), None),
                "Perfil cargado; actualiza el equipo para consultar la batalla.",
            )
            self.sync_overview_controls()

        def configured_profile(self, profile: BotProfile) -> BotProfile:
            try:
                delay = float(self.attack_delay.get().strip().replace(",", "."))
                radius = int(self.search_radius.get())
                speed_rate = float(self.battle_speed_rate.get().strip().replace(",", "."))
            except ValueError as exc:
                raise DiagnosticError(
                    "Escribe una espera de 0 a 60 s, un radio entero de 5 a 500 "
                    "y elige un factor de Speed de la lista."
                ) from exc
            updated = replace(
                profile,
                attack_delay_seconds=delay,
                search_radius=radius,
                collect_remaining_loot=self.collect_loot.get(),
                battle_speed_enabled=self.battle_speed_enabled.get(),
                battle_speed_rate=speed_rate,
                world_attack_mode=next(
                    (
                        key
                        for key, label in WORLD_ATTACK_LABELS.items()
                        if label == self.world_attack_mode.get()
                    ),
                    None,
                ),
            )
            updated.validate()
            return updated

        def save_hunt_options(self) -> None:
            try:
                self.require_idle_bot()
                if self.profile is None:
                    raise DiagnosticError("Carga un perfil válido antes de guardar.")
                updated = self.configured_profile(self.profile)
                self.profile_store.save(updated)
                self.load_profile()
                self.detail.set(f"Opciones de caza y botín del perfil {updated.number} guardadas.")
            except (DiagnosticError, OSError, ValueError) as exc:
                self.error(exc)

        def calibrate_radius(self) -> None:
            try:
                self.require_idle_bot()
                self.show_targets(calibrate=True)
            except (DiagnosticError, OSError, ValueError) as exc:
                self.error(exc)

        def edit_profile(self) -> None:
            try:
                self.require_idle_bot()
                number = int(self.profile_number.get())
            except (DiagnosticError, ValueError) as exc:
                self.error(exc)
                return
            if self.profile_editor is not None and self.profile_editor.winfo_exists():
                self.profile_editor.lift()
                return
            profile = self.profile or BotProfile.default(number)
            window = self.profile_editor = tk.Toplevel(self.root)
            window.title(f"Perfil {number} — mercenarios")
            frame = ttk.Frame(window, padding=16)
            frame.pack(fill="both", expand=True)
            ttk.Label(
                frame,
                text="Selecciona los puestos de tu equipo y ordénalos por prioridad.\n"
                "Elige ataque básico o la magia Q/W/E/R/T de cada mercenario.\n"
                "Objetivo de magia: enemigo, sí mismo o un puesto de tu equipo.\n"
                "Usar bot solo afecta al perfil; el equipo que llevas se elige en el juego.",
                wraplength=820,
            ).pack(anchor="w", pady=6)
            first_turn = tk.BooleanVar(value=profile.magic_first_turn_only)
            ttk.Checkbutton(
                frame,
                text="Magia configurada solo en primer turno; básicos después",
                variable=first_turn,
            ).pack(anchor="w", pady=4)
            order = [merc.slot for merc in profile.mercenaries]
            names = {merc.slot: tk.StringVar(value=merc.name) for merc in profile.mercenaries}
            enabled = {merc.slot: tk.BooleanVar(value=merc.enabled) for merc in profile.mercenaries}
            actions = {
                merc.slot: tk.StringVar(value=ACTION_LABELS[merc.action])
                for merc in profile.mercenaries
            }
            fallback = {
                merc.slot: tk.BooleanVar(value=merc.fallback_basic) for merc in profile.mercenaries
            }
            targets = {
                m.slot: tk.StringVar(value=TARGET_LABELS[m.target]) for m in profile.mercenaries
            }
            body = ttk.Frame(frame)
            body.pack(fill="x", pady=8)
            rows, priorities = {}, {}

            def render() -> None:
                for row in rows.values():
                    row.pack_forget()
                for priority, slot in enumerate(order, 1):
                    priorities[slot].configure(text=f"{priority}.")
                    rows[slot].pack(fill="x", pady=2)

            def move(slot: int, delta: int) -> None:
                index = order.index(slot)
                target = index + delta
                if 0 <= target < len(order):
                    order[index], order[target] = order[target], order[index]
                    render()

            for slot in order:
                row = rows[slot] = ttk.Frame(body)
                priorities[slot] = ttk.Label(row, width=3)
                priorities[slot].pack(side="left")
                ttk.Checkbutton(row, text=member_label(slot), variable=enabled[slot]).pack(
                    side="left"
                )
                ttk.Entry(row, textvariable=names[slot], width=18).pack(side="left", padx=8)
                action = ttk.Combobox(
                    row,
                    textvariable=actions[slot],
                    values=tuple(ACTION_LABELS.values()),
                    state="readonly",
                    width=15,
                )
                action.pack(side="left", padx=(0, 8))
                alternate = ttk.Checkbutton(row, text="Básico alternativo", variable=fallback[slot])
                alternate.pack(side="left", padx=(0, 8))
                target_list = ttk.Combobox(
                    row,
                    textvariable=targets[slot],
                    values=tuple(TARGET_LABELS.values()),
                    state="readonly",
                    width=14,
                )
                target_list.pack(side="left", padx=4)

                def update_fallback(
                    event=None, slot=slot, alternate=alternate, target_list=target_list
                ) -> None:
                    alternate.configure(
                        state="disabled"
                        if actions[slot].get() == ACTION_LABELS["basic"]
                        else "normal"
                    )
                    target_list.configure(
                        state="disabled"
                        if actions[slot].get() == ACTION_LABELS["basic"]
                        else "readonly"
                    )

                action.bind("<<ComboboxSelected>>", update_fallback)
                update_fallback()
                ttk.Button(
                    row, text="Subir", width=6, command=lambda slot=slot: move(slot, -1)
                ).pack(side="left")
                ttk.Button(
                    row, text="Bajar", width=6, command=lambda slot=slot: move(slot, 1)
                ).pack(side="left", padx=4)
            render()
            status = tk.StringVar(
                value="Guardar configura el perfil. Iniciar bot y Ejecutar turnos aplican el orden "
                "solo a los miembros presentes en la batalla."
            )
            ttk.Label(frame, textvariable=status, wraplength=640).pack(anchor="w", pady=8)

            def save() -> None:
                try:
                    self.require_idle_bot()
                    if self.profile_number.get() != str(number):
                        raise DiagnosticError(
                            "El perfil seleccionado cambió; vuelve a abrir el editor."
                        )
                    updated = BotProfile(
                        number,
                        tuple(
                            Mercenary(
                                slot,
                                names[slot].get().strip(),
                                enabled[slot].get(),
                                next(
                                    key
                                    for key, label in ACTION_LABELS.items()
                                    if label == actions[slot].get()
                                ),
                                fallback[slot].get(),
                                next(
                                    key
                                    for key, label in TARGET_LABELS.items()
                                    if label == targets[slot].get()
                                ),
                            )
                            for slot in order
                        ),
                        first_turn.get(),
                    )
                    self.profile_store.save(self.configured_profile(updated))
                    self.load_profile()
                    status.set(
                        f"Perfil {number} guardado. Revisa el equipo en la pestaña Mercenarios "
                        "y activa Ejecutar turnos para usar la secuencia."
                    )
                except (DiagnosticError, OSError) as exc:
                    status.set(str(exc))

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x", pady=4)
            ttk.Button(buttons, text="Guardar perfil", command=save).pack(side="left")
            ttk.Button(buttons, text="Cerrar", command=window.destroy).pack(side="left", padx=8)

        def calibrate_combat(self) -> None:
            try:
                self.require_idle_bot()
                session = self.session
                if session is None or session.creation_time is None:
                    raise DiagnosticError("Conecta con la ventana elegida antes de calibrar.")
            except DiagnosticError as exc:
                self.error(exc)
                return
            if self.calibration_window is not None and self.calibration_window.winfo_exists():
                self.calibration_window.lift()
                return
            self.detector = None
            self.bot_start_button.configure(state="disabled")
            self.detector_status.set("Detector de combate: calibración pendiente.")
            calibration = CombatCalibration(session.process.pid, session.creation_time)
            capture_times = {}
            last_error = ""
            window = self.calibration_window = tk.Toplevel(self.root)
            window.title(f"PID {session.process.pid} — calibración de combate")
            frame = ttk.Frame(window, padding=16)
            frame.pack(fill="both", expand=True)
            ttk.Label(
                frame,
                text="1. Fuera de combate, deja el personaje quieto y captura el mapa.\n"
                "2. Inicia un combate y captura mientras lo estás viendo.\n"
                "3. Termina el combate, vuelve al mismo mapa y captura el regreso.\n\n"
                "Mantén Auto Battle apagado. La captura solo consulta el estado. "
                "Puedes usar la prueba individual para iniciar el combate.",
                wraplength=640,
            ).pack(anchor="w", pady=8)
            status = tk.StringVar(value="Paso 1: personaje quieto en el mapa, fuera de combate.")
            ttk.Label(frame, textvariable=status, wraplength=640).pack(anchor="w", pady=8)
            labels = {
                "map_before": "1. Capturar mapa",
                "battle": "2. Capturar combate",
                "map_after": "3. Capturar regreso",
            }
            prompts = {
                "battle": "Paso 2: entra en combate y captura mientras esté activo.",
                "map_after": "Paso 3: termina el combate y captura al regresar al mismo mapa.",
            }

            def finish_capture() -> None:
                self.calibrating = False
                self.lock_target_controls()
                try:
                    self.refresh()
                except (DiagnosticError, OSError) as exc:
                    self.detail.set(str(exc))
                stage = calibration.next_stage
                capture.configure(
                    state="normal" if stage is not None else "disabled",
                    text=labels.get(stage, "Capturas completas"),
                )
                copy.configure(state="normal" if calibration.samples else "disabled")
                reset.configure(state="normal")

            def collect() -> None:
                nonlocal last_error
                try:
                    self.require_idle_bot()
                    if self.session is not session:
                        raise DiagnosticError(
                            "La conexión cambió; cierra y vuelve a abrir la calibración."
                        )
                    stage = calibration.next_stage
                    if stage is None:
                        return
                except DiagnosticError as exc:
                    status.set(str(exc))
                    return
                self.calibrating = True
                self.lock_target_controls()
                capture.configure(state="disabled")
                reset.configure(state="disabled")
                samples, times = [], []

                def sample() -> None:
                    nonlocal last_error
                    try:
                        if self.session is not session or self.closing:
                            raise DiagnosticError("La conexión cambió durante la captura.")
                        samples.append(observe_scene(session))
                        times.append(datetime.now().astimezone().isoformat())
                        status.set(
                            f"Capturando {len(samples)}/{SAMPLES_PER_STAGE}; espera un momento."
                        )
                        if len(samples) < SAMPLES_PER_STAGE:
                            self.root.after(300, sample)
                            return
                        calibration.capture(stage, tuple(samples))
                        capture_times[stage] = times
                        last_error = ""
                        if calibration.next_stage is not None:
                            status.set(prompts[calibration.next_stage])
                        else:
                            self.detector = calibration.detector()
                            status.set(
                                "Detector calibrado para esta instancia. "
                                "Copia la calibración para contrastarla. "
                                "Si usaste Probar un ataque, "
                                "reconecta al mismo PID antes de iniciar el bot."
                            )
                    except (DiagnosticError, OSError) as exc:
                        last_error = str(exc)
                        status.set(last_error)
                    finish_capture()

                sample()

            def copy_calibration() -> None:
                detector = self.detector
                if detector is not None and not detector.matches(
                    calibration.pid, calibration.creation_time
                ):
                    detector = None
                report = {
                    "tool_version": __version__,
                    **calibration.summary(),
                    "capture_times": capture_times,
                    "detector": detector.summary() if detector else None,
                    "error": last_error or None,
                }
                self.root.clipboard_clear()
                self.root.clipboard_append(json.dumps(report, ensure_ascii=False, indent=2))

            def restart() -> None:
                nonlocal calibration, last_error
                if self.calibrating:
                    return
                calibration = CombatCalibration(session.process.pid, session.creation_time)
                capture_times.clear()
                last_error = ""
                self.detector = None
                status.set("Paso 1: personaje quieto en el mapa, fuera de combate.")
                finish_capture()

            def close() -> None:
                if self.calibrating:
                    status.set("Espera a que termine esta captura antes de cerrar.")
                    return
                window.destroy()

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x", pady=8)
            capture = ttk.Button(buttons, text=labels["map_before"], command=collect)
            capture.pack(side="left")
            copy = ttk.Button(
                buttons, text="Copiar calibración", command=copy_calibration, state="disabled"
            )
            copy.pack(side="left", padx=8)
            reset = ttk.Button(buttons, text="Reiniciar", command=restart)
            reset.pack(side="left")
            ttk.Button(buttons, text="Cerrar", command=close).pack(side="left", padx=8)
            window.protocol("WM_DELETE_WINDOW", close)

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
            if self.speed_experiment is not None and self.speed_experiment.active:
                return  # Keep the timer running without a modal dialog during restoration.
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
                self.combat_capture_button.configure(state="disabled")
                self.members_button.configure(state="disabled")
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
                if self.detector is None or not self.detector.matches(
                    session.process.pid, session.creation_time
                ):
                    self.detector = CombatDetector.for_supported_session(session)
                self.pid.set(str(session.process.pid))
                self.session = session
                self.trial_unknown = False
                self.battle_trials.clear()
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
                self.combat_capture_button.configure(state="disabled")
                self.members_button.configure(state="disabled")
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
            self.combat_capture_button.configure(state="disabled")
            self.members_button.configure(state="disabled")
            self.targets_button.configure(state="disabled")
            self.trial_button.configure(state="disabled")
            self.bot_start_button.configure(state="disabled")
            self.calibration_button.configure(state="disabled")
            self.refresh_files()
            if self.session is None:
                self.lock_target_controls()
                return
            state = self.session.snapshot()
            self.last_state = state
            self.capture_button.configure(state="normal")
            self.combat_capture_button.configure(state="normal")
            self.members_button.configure(state="normal")
            self.targets_button.configure(state="normal")
            self.calibration_button.configure(state="normal")
            calibrated = self.detector is not None and self.detector.matches(
                self.session.process.pid, self.session.creation_time
            )
            self.detector_status.set(
                f"Detector de combate listo para PID {self.session.process.pid}."
                if calibrated
                else "Detector de combate: usa Calibrar combate antes de iniciar el ciclo."
            )
            if not (
                state.auto_battle
                or state.hunting
                or state.files.marker_present
                or self.trial_unknown
            ):
                self.trial_button.configure(state="normal")
                if calibrated and self.profile is not None:
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
            except SceneChanged as exc:
                # An unstable state is not a different process. Keep the binding and
                # leave actions disabled until a later complete snapshot succeeds.
                self.last_state = None
                pid = self.session.process.pid if self.session is not None else self.pid.get()
                self.status.set(f"PID {pid}: esperando una lectura estable del cliente.")
                self.detail.set(str(exc))
                self.lock_target_controls()
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
            if self.speed_experiment is not None and self.speed_experiment.active:
                try:
                    self.speed_experiment.restore()
                except (DiagnosticError, OSError) as exc:
                    self.error(DiagnosticError(f"Restaura la escala antes de cerrar: {exc}"))
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

        def export(self, *, combat: bool = False) -> None:
            session = self.session
            if session is None:
                self.error(
                    DiagnosticError("Conecta con el juego antes de exportar el diagnóstico.")
                )
                return
            filename = filedialog.asksaveasfilename(
                title="Guardar captura de combate" if combat else "Guardar diagnóstico de código",
                defaultextension=".zip",
                filetypes=[("Archivo ZIP", "*.zip")],
                initialdir=str(session.directory),
                initialfile=(
                    f"Atlantica-PID{session.process.pid}-"
                    f"{'combate' if combat else 'contexto'}-{datetime.now():%Y%m%d-%H%M%S}.zip"
                ),
            )
            if not filename:
                return
            try:
                context = (
                    self.bot_report
                    if (
                        self.bot_report.get("pid") == session.process.pid
                        and self.bot_report.get("detector", {}).get("instance_creation_time")
                        == session.creation_time
                    )
                    else None
                )
                export_code_context(
                    session, Path(filename), bot_context=context, include_combat=combat
                )
                self.detail.set(
                    f"Diagnóstico guardado en {filename}. "
                    "Adjunta ese ZIP al chat para continuar el análisis."
                )
            except (DiagnosticError, OSError) as exc:
                self.error(exc)

        def open_speed_trial(self, *, load: bool = True) -> None:
            if self.speed_open():
                self.speed_window.lift()
                return
            try:
                self.require_idle_bot()
                session = self.session
                if session is None:
                    raise DiagnosticError("Conecta con el juego y detén el bot antes de probar.")
                experiment = SpeedExperiment(session, self.selected_window(session))
            except (DiagnosticError, OSError) as exc:
                self.error(exc)
                return
            self.speed_experiment = experiment
            window = self.speed_window = tk.Toplevel(self.root)
            window.title(f"PID {session.process.pid} — prueba de velocidad en combate")
            frame = ttk.Frame(window, padding=16)
            frame.pack(fill="both", expand=True)
            ttk.Label(
                frame,
                text="Prueba manual de 10 segundos, con el bot detenido y Auto Battle apagado.\n"
                "1. Entra en combate y lee el estado.\n"
                "2. Pulsa Probar y ejecuta una acción manual para observar su animación.\n"
                "3. Se intentará restaurar la escala al terminar el tiempo o salir del combate.\n"
                "También puedes pulsar Restaurar en cualquier momento.\n"
                "La escala pasa de 1,40 a 1,45; "
                "no equivale a un multiplicador del combate completo.\n"
                "Se registran lecturas durante la prueba para comprobar si conserva la escala.\n"
                "El efecto y la estabilidad en el juego todavía requieren esta prueba.",
                wraplength=700,
            ).pack(anchor="w")
            status = tk.StringVar(value="Sin cambios. Lee el estado dentro de un combate.")
            ttk.Label(frame, textvariable=status, wraplength=700).pack(anchor="w", pady=14)
            monitoring_status = tk.StringVar(value="Seguimiento: sin muestras todavía.")
            ttk.Label(frame, textvariable=monitoring_status, wraplength=700).pack(
                anchor="w", pady=(0, 14)
            )
            timer_id = None

            def scope() -> None:
                self.require_idle_bot(allow_speed=True)
                if self.session is not session:
                    raise DiagnosticError(
                        "La conexión cambió; conserva la restauración de esta prueba."
                    )

            def controls() -> None:
                active = experiment.active
                read_button.configure(state="disabled" if active else "normal")
                apply_button.configure(state="disabled" if active else "normal")
                restore_button.configure(state="normal" if active else "disabled")

            def read_state() -> None:
                try:
                    scope()
                    _, snapshot = prepare_speed_plan(session)
                    experiment.report["preview"] = snapshot
                    experiment.report.pop("preview_error", None)
                    status.set(
                        "Lectura válida: escala original 1,40 y campos separados del mapa. "
                        "No se ha aplicado ningún cambio."
                    )
                    apply_button.configure(state="normal")
                except (DiagnosticError, OSError) as exc:
                    apply_button.configure(state="disabled")
                    experiment.report["preview_error"] = str(exc)
                    if hasattr(exc, "speed_snapshot"):
                        experiment.report["preview"] = exc.speed_snapshot
                    status.set(str(exc))

            def apply() -> None:
                try:
                    scope()
                    apply_button.configure(state="disabled")
                    result = experiment.start()
                    status.set(result["message"])
                except (DiagnosticError, OSError) as exc:
                    experiment.report["error"] = str(exc)
                    status.set(str(exc))
                controls()

            def restore() -> bool:
                try:
                    experiment.auto_restore_attempted = True
                    result = experiment.restore()
                    reason = experiment.report.get("monitoring", {}).get("stop_reason")
                    prefix = {
                        "rate_changed": "La escala cambió durante la prueba. ",
                        "map_rate_changed": "Cambió la escala del mapa. ",
                        "sample_read_error": "La lectura dejó de ser válida. ",
                        "battle_state_changed": "Cambió el estado del combate. ",
                    }.get(reason, "")
                    status.set(prefix + result.get("message", "No hay cambios pendientes."))
                    return not experiment.active
                except (DiagnosticError, OSError) as exc:
                    experiment.report["restore_error"] = str(exc)
                    status.set(
                        f"Restauración sin confirmar: {exc}. "
                        "Mantén el juego abierto y pulsa Restaurar."
                    )
                    return False
                finally:
                    controls()

            def tick() -> None:
                nonlocal timer_id
                timer_id = None
                if not window.winfo_exists():
                    return
                if experiment.should_restore():
                    restore()
                observations = experiment.report.get("observations", [])
                if observations:
                    last = observations[-1]
                    count = experiment.report["monitoring"]["samples_read"]
                    if last["status"] == "read":
                        monitoring_status.set(
                            f"Seguimiento: {count} muestras; última a "
                            f"{last['elapsed_ms'] / 1000:.1f} s. "
                            f"Escala de combate {last['manager_rate']:.2f} / "
                            f"{last['battle_graphics_rate']:.2f}; "
                            f"mapa {last['map_graphics_rate']:.2f}."
                        )
                    else:
                        monitoring_status.set(f"Seguimiento interrumpido: {last['error']}")
                timer_id = window.after(200, tick)

            def copy() -> None:
                self.root.clipboard_clear()
                self.root.clipboard_append(
                    json.dumps(
                        {**experiment.report, "active": experiment.active},
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            def close() -> None:
                if experiment.active and not restore():
                    return
                if timer_id is not None:
                    window.after_cancel(timer_id)
                window.destroy()
                self.speed_window = None
                self.speed_experiment = None
                self.lock_target_controls()
                try:
                    self.refresh()
                except (DiagnosticError, OSError) as exc:
                    self.detail.set(str(exc))

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x")
            read_button = ttk.Button(buttons, text="Leer estado", command=read_state)
            read_button.pack(side="left")
            apply_button = ttk.Button(
                buttons, text="Probar escala 1,45 (10 s)", command=apply, state="disabled"
            )
            apply_button.pack(side="left", padx=8)
            restore_button = ttk.Button(
                buttons, text="Restaurar", command=restore, state="disabled"
            )
            restore_button.pack(side="left")
            ttk.Button(buttons, text="Copiar resultado", command=copy).pack(side="left", padx=8)
            ttk.Button(frame, text="Cerrar", command=close).pack(anchor="e", pady=(12, 0))
            window.protocol("WM_DELETE_WINDOW", close)
            self.lock_target_controls()
            if load:
                read_state()
            timer_id = window.after(200, tick)

        def capture_bonus(self) -> None:
            if self.bonus_open():
                self.bonus_window.lift()
                return
            try:
                self.require_idle_bot()
                session = self.session
                if session is None or session.creation_time is None:
                    raise DiagnosticError(
                        "Conecta con la ventana elegida y para el bot antes de capturar."
                    )
                comparison = BonusComparison(session.process.pid, session.creation_time)
            except DiagnosticError as exc:
                self.error(exc)
                return
            window = self.bonus_window = tk.Toplevel(self.root)
            window.title(f"PID {session.process.pid} — comparar bonus en memoria")
            frame = ttk.Frame(window, padding=16)
            frame.pack(fill="both", expand=True)
            ttk.Label(
                frame,
                text="Con el bot detenido y Auto Battle apagado:\n"
                "1. Cuando veas el bonus dentro del combate, elige su tipo y captura.\n"
                "2. Vuelve al juego, pulsa X una vez y observa qué ocurrió.\n"
                "3. Captura después de X y guarda el ZIP, aunque hayas vuelto al mapa.\n"
                "La captura solo lee memoria; no pulsa teclas ni recoge objetos.",
                wraplength=670,
            ).pack(anchor="w", pady=(0, 10))
            row = ttk.Frame(frame)
            row.pack(fill="x")
            ttk.Label(row, text="Tipo que ves:").pack(side="left")
            category = tk.StringVar(value=BONUS_LABELS["equipment"])
            category_list = ttk.Combobox(
                row,
                textvariable=category,
                values=tuple(BONUS_LABELS.values()),
                state="readonly",
                width=25,
            )
            category_list.pack(side="left", padx=8)
            result = tk.StringVar(value="Sin confirmar")
            ttk.Label(row, text="¿X lo recogió?").pack(side="left")
            ttk.Combobox(
                row,
                textvariable=result,
                values=("Sin confirmar", "Sí", "No"),
                state="readonly",
                width=15,
            ).pack(side="left", padx=8)
            status = tk.StringVar(value="Esperando una captura del bonus visible.")
            ttk.Label(frame, textvariable=status, wraplength=670).pack(anchor="w", pady=12)

            def scope() -> None:
                self.require_idle_bot(allow_bonus=True)
                if self.session is not session:
                    raise DiagnosticError(
                        "La conexión cambió; abre una captura del cliente actual."
                    )

            def take_before() -> None:
                try:
                    scope()
                    snapshot = capture_bonus_snapshot(session)
                    key = next(k for k, label in BONUS_LABELS.items() if label == category.get())
                    blocks, errors = read_bonus_code(session)
                    comparison.set_before(key, snapshot, blocks, errors)
                    category_list.configure(state="disabled")
                    before_button.configure(state="disabled")
                    after_button.configure(state="normal")
                    save_button.configure(state="normal")
                    status.set(
                        "Bonus capturado. Vuelve al juego, pulsa X una vez y captura después. "
                        "También puedes guardar ahora si desaparece "
                        "antes de completar la comparación."
                    )
                except (DiagnosticError, OSError, StopIteration) as exc:
                    status.set(str(exc))

            def take_after() -> None:
                try:
                    scope()
                    snapshot = capture_bonus_snapshot(session)
                    comparison.set_after(
                        snapshot, user_result={"Sí": True, "No": False}.get(result.get())
                    )
                    status.set(
                        "Comparación capturada. Guarda el ZIP y adjúntalo al chat "
                        "para analizar la recogida."
                    )
                except (DiagnosticError, OSError) as exc:
                    status.set(str(exc))

            def save() -> None:
                try:
                    filename = filedialog.asksaveasfilename(
                        parent=window,
                        title="Guardar comparación de bonus",
                        defaultextension=".zip",
                        filetypes=[("Archivo ZIP", "*.zip")],
                        initialfile=(
                            f"Atlantica-PID{session.process.pid}-bonus-"
                            f"{comparison.category or 'captura'}-{datetime.now():%Y%m%d-%H%M%S}.zip"
                        ),
                    )
                    if filename:
                        if comparison.after is not None:
                            comparison.user_result = {"Sí": True, "No": False}.get(result.get())
                        comparison.export(Path(filename))
                        status.set(f"Captura guardada en {filename}. Adjunta ese ZIP al chat.")
                except (DiagnosticError, OSError) as exc:
                    status.set(str(exc))

            def reset() -> None:
                nonlocal comparison
                comparison = BonusComparison(session.process.pid, session.creation_time)
                category_list.configure(state="readonly")
                before_button.configure(state="normal")
                after_button.configure(state="disabled")
                save_button.configure(state="disabled")
                result.set("Sin confirmar")
                status.set("Esperando una captura del bonus visible.")

            def close() -> None:
                window.destroy()
                self.bonus_window = None
                self.lock_target_controls()
                if not self.closing:
                    try:
                        self.refresh()
                    except (DiagnosticError, OSError) as exc:
                        self.detail.set(str(exc))

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x")
            before_button = ttk.Button(
                buttons, text="1. Capturar bonus visible", command=take_before
            )
            before_button.pack(side="left")
            after_button = ttk.Button(
                buttons, text="2. Capturar después de X", command=take_after, state="disabled"
            )
            after_button.pack(side="left", padx=8)
            save_button = ttk.Button(buttons, text="Guardar ZIP", command=save, state="disabled")
            save_button.pack(side="left")
            ttk.Button(buttons, text="Nueva comparación", command=reset).pack(side="left", padx=8)
            ttk.Button(frame, text="Cerrar", command=close).pack(anchor="e", pady=(12, 0))
            window.protocol("WM_DELETE_WINDOW", close)
            self.lock_target_controls()

        def show_members(self, *, load: bool = True) -> None:
            selected_session = self.session
            if selected_session is None:
                self.error(DiagnosticError("Conecta con la ventana elegida antes de consultar."))
                return
            window = tk.Toplevel(self.root)
            window.title(f"PID {selected_session.process.pid} — mercenarios en combate")
            frame = ttk.Frame(window, padding=16)
            frame.pack(fill="both", expand=True)
            summary = tk.StringVar(value="Consulta los puestos antes de probar un ataque básico.")
            ttk.Label(frame, textvariable=summary, wraplength=680).pack(anchor="w", pady=6)
            table = ttk.Treeview(
                frame, columns=("slot", "label", "kind", "present"), show="headings", height=9
            )
            for column, label, width in (
                ("slot", "Miembro", 115),
                ("label", "Nombre del perfil", 190),
                ("kind", "Tipo detectado", 120),
                ("present", "Ocupado", 80),
            ):
                table.heading(column, text=label)
                table.column(column, width=width, anchor="w")
            table.pack(fill="both", expand=True, pady=6)
            last = {}
            live = None
            trial_result = {}
            source_choices, target_choices = {}, {}
            source_choice, target_choice = tk.StringVar(), tk.StringVar()
            ttk.Label(frame, text="Miembro para la prueba:").pack(anchor="w", pady=(8, 0))
            source_list = ttk.Combobox(
                frame, textvariable=source_choice, state="readonly", width=65
            )
            source_list.pack(fill="x", pady=4)
            ttk.Label(frame, text="Objetivo en la formación enemiga:").pack(anchor="w")
            target_list = ttk.Combobox(
                frame, textvariable=target_choice, state="readonly", width=65
            )
            target_list.pack(fill="x", pady=4)
            action_choice = tk.StringVar(value="Ataque básico")
            ttk.Label(frame, text="Acción de la prueba:").pack(anchor="w")
            action_list = ttk.Combobox(
                frame, textvariable=action_choice, values=("Ataque básico",), state="readonly"
            )
            action_list.pack(fill="x", pady=4)
            trial_status = tk.StringVar(
                value="Para el bot antes de la prueba. Seleccionar en juego cambia el mercenario "
                "activo y permite leer su barra Q/W/E/R/T. Probar acción solicita un solo básico "
                "o magia. Activa Ejecutar turnos en Control para aplicar el perfil."
            )
            ttk.Label(frame, textvariable=trial_status, wraplength=680).pack(anchor="w", pady=6)

            def refresh_actions(event=None) -> None:
                actions = ["Ataque básico"]
                source = source_choices.get(source_choice.get())
                if (
                    live
                    and source
                    and live.selected_unit == source.address
                    and not live.magic_error
                ):
                    actions.extend(f"Magia {key}" for key in "QWERT"[: len(live.magic_actions)])
                action_list.configure(values=actions)
                if action_choice.get() not in actions:
                    action_choice.set("Ataque básico")
                refresh_action_targets()

            def refresh_action_targets(event=None) -> None:
                selected = target_choice.get()
                target_choices.clear()
                if live:
                    groups = {
                        slot: n
                        for n, slot in enumerate(sorted({u.world_slot for u in live.enemies}), 1)
                    }
                    targets = (
                        live.enemies
                        if action_choice.get() == "Ataque básico"
                        else live.magic_targets
                    )
                    for unit in targets:
                        label = (
                            f"Tu equipo — {member_label(unit.member_slot)}"
                            if unit.world_slot == 1
                            else f"Enemigo {groups[unit.world_slot]} — puesto {unit.member_slot}"
                        )
                        target_choices[f"{label} (tipo {unit.kind_id})"] = unit
                target_list.configure(values=tuple(target_choices))
                target_choice.set(
                    selected if selected in target_choices else next(iter(target_choices), "")
                )
                trial_button.configure(
                    state="normal"
                    if live
                    and live.phase == 3
                    and live.own_turn
                    and source_choices
                    and target_choices
                    else "disabled"
                )

            source_list.bind("<<ComboboxSelected>>", refresh_actions)
            action_list.bind("<<ComboboxSelected>>", refresh_action_targets)

            def refresh_members() -> None:
                nonlocal live
                live = None
                trial_button.configure(state="disabled")
                select_button.configure(state="disabled")
                previous_source = source_choice.get()
                table.delete(*table.get_children())
                last.clear()
                if trial_result:
                    last["combat_trial"] = dict(trial_result)
                    if trial_result.get("action") == "battle_basic":
                        last["basic_trial"] = dict(trial_result)
                source_choices.clear()
                target_choices.clear()
                source_list.configure(values=())
                target_list.configure(values=())
                source_choice.set("")
                target_choice.set("")
                try:
                    if self.session is not selected_session:
                        raise DiagnosticError(
                            "La conexión cambió; abre el visor del cliente elegido."
                        )
                    view = read_normal_battle(selected_session)
                    last.update(view.summary())
                    last["tool_version"] = __version__
                    last["captured_at"] = datetime.now().astimezone().isoformat()
                    if view.member_read_error:
                        summary.set(view.member_read_error)
                        return
                    names = (
                        {m.slot: m.name for m in self.profile.mercenaries} if self.profile else {}
                    )
                    for member in view.members:
                        table.insert(
                            "",
                            "end",
                            values=(
                                member_label(member.slot),
                                names.get(member.slot, f"Puesto {member.slot}"),
                                member.kind_id,
                                "Sí" if member.kind_id else "No",
                            ),
                        )
                    summary.set(
                        f"PID {view.pid}: {sum(m.kind_id > 0 for m in view.members)} puestos "
                        "ocupados. El tipo se leyó del cliente; los nombres proceden del perfil. "
                        "La disponibilidad para actuar todavía no está comprobada."
                    )
                    try:
                        live = read_battle_frame(selected_session)
                        last["battle_frame"] = live.summary()
                        source_choices.update(
                            {
                                f"{member_label(u.member_slot)} — "
                                f"{names.get(u.member_slot, 'Sin nombre')} "
                                f"(tipo {u.kind_id})": u
                                for u in live.sources
                            }
                        )
                        source_list.configure(values=tuple(source_choices))
                        source_choice.set(
                            previous_source
                            if previous_source in source_choices
                            else next(iter(source_choices), "")
                        )
                        refresh_actions()
                        trial_status.set(
                            ("Turno de tu grupo. " if live.own_turn else "Turno del otro grupo. ")
                            + "Comprueba el tipo de los puestos leídos. "
                            "Selecciona en juego para cargar las magias de ese mercenario."
                        )
                        if live.phase == 3 and source_choices:
                            select_button.configure(state="normal")
                        if live.own_turn and live.phase == 3 and source_choices and target_choices:
                            trial_button.configure(state="normal")
                    except (DiagnosticError, OSError) as exc:
                        trial_status.set(str(exc))
                        last["battle_frame"] = {
                            "status": "unavailable",
                            "message": str(exc),
                            "details": getattr(exc, "details", None),
                        }
                except (DiagnosticError, OSError) as exc:
                    summary.set(str(exc))
                    last.update(
                        {
                            "pid": selected_session.process.pid,
                            "status": "unavailable",
                            "message": str(exc),
                            "tool_version": __version__,
                        }
                    )

            def test_action(*, select: bool = False) -> None:
                try:
                    self.require_idle_bot()
                    if self.session is not selected_session or live is None:
                        raise DiagnosticError("La conexión cambió; actualiza el combate.")
                    if self.trial_unknown:
                        raise DiagnosticError(
                            "Comprueba el juego y reconecta antes de otra prueba."
                        )
                    selected_window = self.selected_window(selected_session)
                    source = source_choices.get(source_choice.get())
                    target = target_choices.get(target_choice.get())
                    if source is None or not select and target is None:
                        raise DiagnosticError("Elige el mercenario y el objetivo de la prueba.")
                    action = (
                        "select"
                        if select
                        else "basic"
                        if action_choice.get() == "Ataque básico"
                        else action_choice.get()[-1]
                    )
                    trial = BattleTrial(live, source, None if select else target, action)
                    trial.validate()
                    if not select and trial.key() in self.battle_trials:
                        raise DiagnosticError(
                            "Ya se solicitó una prueba de este mercenario en este turno. "
                            "Espera al siguiente turno o continúa manualmente."
                        )
                except DiagnosticError as exc:
                    trial_status.set(str(exc))
                    return
                trial_button.configure(state="disabled")
                select_button.configure(state="disabled")
                if not select:
                    self.battle_trials.add(trial.key())
                try:
                    result = try_battle_action(selected_session, selected_window, trial)
                    self.last_trial = result
                    if not select and result["status"] not in (26, 32, 10, 11):
                        self.battle_trials.discard(trial.key())
                    self.trial_unknown |= result["status"] in (10, 11)
                    last["combat_trial"] = result
                    if action == "basic":
                        last["basic_trial"] = result
                    trial_result.clear()
                    trial_result.update(result)
                    if result["status"] == 31:
                        refresh_members()
                    trial_status.set(result["message"] + " Leer y elegir una acción no la ejecuta.")
                except (DiagnosticError, OSError) as exc:
                    no_send = isinstance(exc, WindowUnavailable)
                    self.trial_unknown |= not no_send
                    if no_send and not select:
                        self.battle_trials.discard(trial.key())
                    result = (
                        exc.summary()
                        if no_send
                        else {
                            "pid": selected_session.process.pid,
                            "status": "unknown",
                            "message": str(exc),
                            "attack_confirmed": False,
                        }
                    )
                    self.last_trial = result
                    last["combat_trial"] = result
                    trial_result.clear()
                    trial_result.update(result)
                    trial_status.set(str(exc))

            def copy_members() -> None:
                if last:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(json.dumps(last, ensure_ascii=False, indent=2))

            buttons = ttk.Frame(frame)
            buttons.pack(fill="x", pady=6)
            ttk.Button(buttons, text="Actualizar", command=refresh_members).pack(side="left")
            ttk.Button(buttons, text="Copiar mercenarios", command=copy_members).pack(
                side="left", padx=8
            )
            trial_button = ttk.Button(
                buttons, text="Probar acción (experimental)", command=test_action, state="disabled"
            )
            trial_button.pack(side="left", padx=8)
            select_button = ttk.Button(
                buttons,
                text="Seleccionar en juego",
                command=lambda: test_action(select=True),
                state="disabled",
            )
            select_button.pack(side="left", padx=8)
            if load:
                refresh_members()

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
                no_send = isinstance(exc, WindowUnavailable)
                self.trial_unknown |= not no_send
                self.last_trial = (
                    exc.summary()
                    if no_send
                    else {
                        "pid": session.process.pid,
                        "result": "unconfirmed",
                        "message": str(exc),
                    }
                )
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

        def show_targets(self, *, calibrate: bool = False) -> None:
            if self.session is None:
                self.error(DiagnosticError("Conecta con el juego para leer los objetivos."))
                return
            selected_session = self.session
            candidates = {}
            window = tk.Toplevel(self.root)
            window.title(
                f"PID {selected_session.process.pid} — "
                + ("calibrar radio" if calibrate else "candidatos de mapa")
            )
            window.minsize(680, 330)
            frame = ttk.Frame(window, padding=12)
            frame.pack(fill="both", expand=True)
            summary = tk.StringVar(value="Consultando...")
            ttk.Label(frame, textvariable=summary, wraplength=650).pack(anchor="w", pady=6)
            columns = ("slot", "kind", "map", "x", "y", "distance", "in_range")
            table = ttk.Treeview(frame, columns=columns, show="headings", height=10)
            for key, title in zip(
                columns,
                ("N.º", "ID observado", "Mapa", "X", "Y", "Distancia rejilla", "En alcance"),
                strict=True,
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
                    observation = observe_scene(selected_session, include_navigation=True)
                    if (view.scene_code, view.player) != (
                        observation.scene_code,
                        observation.player,
                    ):
                        raise DiagnosticError(
                            "La escena cambió; vuelve a actualizar los objetivos."
                        )
                    last.clear()
                    candidates.clear()
                    last.update(view.summary())
                    last["pid"] = selected_session.process.pid
                    last["observation"] = observation.summary()
                    last["captured_at"] = datetime.now().astimezone().isoformat()
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
                        candidates[str(candidate.slot)] = candidate
                        table.insert(
                            "",
                            "end",
                            iid=str(candidate.slot),
                            values=(
                                candidate.slot,
                                candidate.kind_id,
                                candidate.map_id,
                                candidate.x,
                                candidate.y,
                                candidate.grid_distance,
                                "Sí"
                                if (
                                    view.range_limit_squared is not None
                                    and candidate.distance_squared is not None
                                    and candidate.distance_squared <= view.range_limit_squared
                                )
                                else "No",
                            ),
                        )
                except (DiagnosticError, OSError) as exc:
                    last.clear()
                    candidates.clear()
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
            if calibrate:

                def use_target() -> None:
                    try:
                        self.require_idle_bot()
                        if self.session is not selected_session:
                            raise DiagnosticError(
                                "La conexión cambió; vuelve a abrir la calibración."
                            )
                        choice = table.selection()
                        if not choice or choice[0] not in candidates:
                            raise DiagnosticError(
                                "Selecciona un mob de la lista para incluirlo en el radio."
                            )
                        old = candidates[choice[0]]
                        fresh = scan_world(selected_session)
                        radius = calibrated_radius(fresh, old.identity)
                        if fresh.player.map_id != old.map_id:
                            raise DiagnosticError("Cambió el mapa; vuelve a calibrar.")
                        self.search_radius.set(str(radius))
                        summary.set(
                            f"Radio ajustado a {radius} casillas desde tu posición actual. "
                            "Guarda las opciones o inicia el bot para conservarlo en el perfil."
                        )
                    except (DiagnosticError, OSError, ValueError) as exc:
                        summary.set(str(exc))

                ttk.Button(buttons, text="Incluir mob seleccionado", command=use_target).pack(
                    side="left"
                )
            ttk.Label(
                frame,
                text="El alcance se compara con la distancia 3D del cliente, no con la rejilla. "
                "El acercamiento automático busca dentro del radio configurado.",
                wraplength=650,
            ).pack(anchor="w")
            refresh_targets()

    panel = Panel()
    if smoke_test:
        from .animation_code import decoder_probe

        assert decoder_probe()
        # Exercise the real packaged GUI without connecting or changing any files.
        assert tuple(panel.tabs.tab(tab, "text") for tab in panel.tabs.tabs()) == (
            "Control",
            "Mercenarios",
            "Caza y botín",
            "Diagnóstico",
        )
        for tab in panel.tabs.tabs():
            panel.tabs.select(tab)
            panel.root.update()
            assert panel.bot_start_button.winfo_ismapped()
            assert panel.bot_stop_button.winfo_ismapped()
        original_geometry = panel.root.geometry()
        panel.root.geometry("920x650")
        for tab in panel.tabs.tabs():
            panel.tabs.select(tab)
            panel.root.update_idletasks()
            for button in (panel.bot_start_button, panel.bot_stop_button, panel.bot_copy_button):
                assert button.winfo_rooty() + button.winfo_height() <= (
                    panel.root.winfo_rooty() + panel.root.winfo_height()
                )
        panel.tabs.select(panel.hunt_tab)
        panel.root.update_idletasks()
        assert panel.save_hunt_button.winfo_ismapped()
        assert panel.save_hunt_button.winfo_rooty() + panel.save_hunt_button.winfo_height() <= (
            panel.hunt_tab.winfo_rooty() + panel.hunt_tab.winfo_height()
        )
        panel.root.geometry(original_geometry)
        panel.tabs.select(panel.team_tab)
        assert len(panel.team_tree.get_children()) == 9
        assert panel.team_tree.item("merc_1", "values")[0] == "Main (1)"
        panel.root.update_idletasks()
        panel.tabs.select(0)
        panel.show_overview()
        overview = panel.overview
        assert overview is not None and overview.alive and len(overview.cells) == 9
        assert "Turnos manuales" in overview.identity.get()
        assert "no ejecutará básicos ni magias" in panel.execution_status.get()
        panel.turns_enabled.set(True)
        assert "Combate automático" in overview.identity.get()
        assert "Combate automático" in panel.execution_status.get()
        panel.turns_enabled.set(False)
        assert tuple(overview.tabs.tab(tab, "text") for tab in overview.tabs.tabs()) == (
            "Resumen",
            "Órdenes de combate",
            "Caza y botín",
        )
        panel.attack_delay.set("1,5")
        panel.search_radius.set("350")
        panel.collect_loot.set(True)
        assert not panel.battle_speed_enabled.get()
        panel.battle_speed_enabled.set(True)
        panel.battle_speed_rate.set("3")
        panel.world_attack_mode.set(WORLD_ATTACK_LABELS["stationary"])
        configured = panel.configured_profile(BotProfile.default(1))
        assert configured.attack_delay_seconds == 1.5 and configured.search_radius == 350
        assert configured.collect_remaining_loot
        assert configured.battle_speed_enabled and configured.battle_speed_rate == 3.0
        assert configured.world_attack_mode == "stationary"
        assert overview.attack_mode_list.get() == WORLD_ATTACK_LABELS["stationary"]
        assert overview.hunt_controls[0].get() == "1,5"
        overview.set_controls(start=False, stop=True, editable=False)
        assert all(str(widget.cget("state")) == "disabled" for widget in overview.hunt_controls)
        assert str(overview.attack_mode_list.cget("state")) == "disabled"
        overview.set_controls(start=False, stop=False, editable=True)
        panel.load_profile()
        assert overview.cells[1]["member"].cget("text") == "Main (1)"
        assert overview.cells[9]["member"].cget("text") == "Mercenario 9"
        assert str(overview.start_button.cget("state")) == "disabled"
        assert str(overview.copy_button.cget("state")) == "disabled"
        from types import SimpleNamespace

        fake_frame = SimpleNamespace(
            units=(SimpleNamespace(world_slot=1, member_slot=1, kind_id=2318, life=1234),)
        )
        panel.paint_team(roster_rows(BotProfile.default(1), fake_frame), "Comprobación de vista")
        assert str(overview.cells[1]["life"].cget("text")) == "1234"
        assert overview.cells[2]["life"].cget("text") == "—"
        assert overview.cells[2]["present"].cget("text") == "No presente"
        panel.show_overview()
        assert panel.overview is overview
        assert overview.cells[1]["life"].cget("text") == "—"
        overview.window.destroy()
        panel.show_overview()
        assert panel.overview is not overview and panel.overview.alive
        overview = panel.overview
        overview.window.deiconify()
        panel.root.update()
        for tab, cells in enumerate((overview.cells, overview.order_cells)):
            overview.tabs.select(tab)
            panel.root.update()
            last = cells[9]["member"]
            assert last.winfo_rooty() + last.winfo_height() <= (
                overview.tabs.winfo_rooty() + overview.tabs.winfo_height()
            )
        overview.tabs.select(2)
        panel.root.update()
        last = overview.hunt_controls[-1]
        assert last.winfo_ismapped() and overview.tabs.winfo_height() > 1
        control_bottom = last.winfo_rooty() + last.winfo_height()
        page_bottom = overview.tabs.winfo_rooty() + overview.tabs.winfo_height()
        assert control_bottom <= page_bottom, (control_bottom, page_bottom)
        overview.tabs.select(0)
        panel.toggle_advanced()
        panel.edit_profile()
        panel.profile_editor.destroy()

        def changing_state():
            raise SceneChanged("Cambio de estado simulado")

        panel.session = SimpleNamespace(
            process=SimpleNamespace(pid=1), creation_time=1, snapshot=changing_state
        )
        panel.pid.set("1")
        bound_session = panel.session
        panel.sync_identity()
        panel.main_alias.set("Main Uno")
        assert "Main Uno" in panel.root.title() and "PID 1" in panel.root.title()
        assert "Main Uno" in overview.window.title()
        panel.session = SimpleNamespace(process=SimpleNamespace(pid=2), creation_time=2)
        panel.sync_identity()
        assert panel.main_alias.get() == "" and "PID 2" in panel.root.title()
        panel.main_alias.set("Main Dos")
        panel.session = bound_session
        panel.sync_identity()
        assert panel.main_alias.get() == "Main Uno"
        panel.session = SimpleNamespace(process=SimpleNamespace(pid=1), creation_time=3)
        panel.sync_identity()
        assert panel.main_alias.get() == ""
        panel.session = bound_session
        panel.sync_identity()
        panel.poll()
        assert panel.session is bound_session and panel.pid.get() == "1"
        assert "PID 1" in panel.status.get()
        assert str(panel.bot_start_button.cget("state")) == "disabled"
        panel.bot_report = {
            "pid": 2,
            "detector": {"instance_creation_time": 2},
            "battles_observed": 8,
            "combat": {"queued": 9},
        }
        panel.sync_overview_controls()
        assert overview.counts.get() == "Combates: 0 · Órdenes: 0"
        assert str(overview.copy_button.cget("state")) == "disabled"
        panel.bot_report.update(pid=1, detector={"instance_creation_time": 1})
        panel.sync_overview_controls()
        assert overview.counts.get() == "Combates: 8 · Órdenes: 9"
        assert str(overview.copy_button.cget("state")) == "normal"
        panel.bot_report = {}
        panel.capture_bonus()
        assert panel.bonus_open()
        assert str(panel.bot_start_button.cget("state")) == "disabled"
        assert str(panel.profile_list.cget("state")) == "disabled"
        assert all(str(widget.cget("state")) == "disabled" for widget in overview.hunt_controls)
        panel.bonus_window.destroy()
        panel.bonus_window = None
        panel.lock_target_controls()
        assert str(panel.profile_list.cget("state")) == "readonly"
        from .clients import ClientWindow

        fake_window = ClientWindow(1, 0x1234, "Prueba propia", 1)
        panel.windows[fake_window.label] = fake_window
        panel.window_choice.set(fake_window.label)
        panel.open_speed_trial(load=False)
        assert panel.speed_open() and not panel.speed_experiment.active
        assert str(panel.bot_start_button.cget("state")) == "disabled"
        assert str(panel.capture_button.cget("state")) == "disabled"
        assert str(panel.profile_list.cget("state")) == "disabled"
        assert all(str(widget.cget("state")) == "disabled" for widget in overview.hunt_controls)
        panel.speed_window.tk.call(panel.speed_window.protocol("WM_DELETE_WINDOW"))
        assert not panel.speed_open() and panel.speed_experiment is None
        panel.window_choice.set("")
        panel.lock_target_controls()
        panel.show_members(load=False)
        panel.calibrate_combat()
        panel.calibration_window.destroy()
        panel.session = None
        panel.root.update_idletasks()
        panel.toggle_advanced()
        panel.root.after(500, panel.root.destroy)
    panel.root.mainloop()
