from __future__ import annotations

from collections.abc import Callable

from .limits import MAX_SEARCH_RADIUS, MIN_SEARCH_RADIUS
from .profiles import WORLD_ATTACK_LABELS, member_label

BACKGROUND = "#25272d"
SURFACE = "#30333b"
TEXT = "#f1f2f5"
GOLD = "#ffd166"
MUTED = "#a8afbc"
GREEN = "#91e0a8"
RED = "#ff8585"
BLUE = "#8fcaff"


class OverviewWindow:
    """Render already-read roster data; callbacks use the panel's existing controls."""

    def __init__(
        self,
        parent,
        *,
        execute_turns,
        profile_number,
        on_profile: Callable,
        on_start: Callable,
        on_stop: Callable,
        on_configure: Callable,
        on_refresh: Callable,
        on_copy: Callable,
        attack_delay,
        search_radius,
        collect_loot,
        on_save: Callable,
        on_calibrate: Callable,
        world_attack_mode,
    ):
        import tkinter as tk
        from tkinter import ttk

        self._tcl_error = tk.TclError
        self._pid: int | None = None
        self._execute_orders = execute_turns.get()
        self.window = tk.Toplevel(parent)
        self.window.title("Atlantica — Vista general")
        self.window.configure(background=BACKGROUND)
        self.window.minsize(800, 570)
        self.window.geometry("860x610")
        outer = tk.Frame(self.window, background=BACKGROUND, padx=14, pady=12)
        outer.pack(fill="both", expand=True)
        heading = tk.Frame(outer, background=BACKGROUND)
        heading.pack(fill="x", pady=(0, 10))
        tk.Label(
            heading,
            text="Main y mercenarios",
            background=BACKGROUND,
            foreground=GOLD,
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left")
        self.identity = tk.StringVar(value="Sin conexión")
        self.identity_label = tk.Label(
            heading, textvariable=self.identity, background=BACKGROUND, font=("Segoe UI", 9, "bold")
        )
        self.identity_label.pack(side="right")
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        summary = tk.Frame(self.tabs, background=SURFACE, padx=10, pady=10)
        orders = tk.Frame(self.tabs, background=SURFACE, padx=10, pady=10)
        hunting = tk.Frame(self.tabs, background=SURFACE, padx=16, pady=16)
        self.tabs.add(summary, text="Resumen")
        self.tabs.add(orders, text="Órdenes de combate")
        self.tabs.add(hunting, text="Caza y botín")
        self.hunt_controls = []

        def option_label(text):
            tk.Label(
                hunting,
                text=text,
                background=SURFACE,
                foreground=TEXT,
                anchor="w",
                justify="left",
                wraplength=710,
            ).pack(anchor="w", pady=(2, 3))

        mode_row = tk.Frame(hunting, background=SURFACE)
        mode_row.pack(fill="x", pady=(0, 10))
        tk.Label(mode_row, text="Modo de ataque al mob:", background=SURFACE, foreground=TEXT).pack(
            side="left", padx=(0, 8)
        )
        self.attack_mode_list = ttk.Combobox(
            mode_row,
            textvariable=world_attack_mode,
            values=tuple(WORLD_ATTACK_LABELS.values()),
            state="readonly",
            width=43,
        )
        self.attack_mode_list.pack(side="left")
        fields_row = tk.Frame(hunting, background=SURFACE)
        fields_row.pack(fill="x", pady=(0, 8))
        tk.Label(
            fields_row, text="Espera antes de atacar (0–60 s):", background=SURFACE, foreground=TEXT
        ).pack(side="left", padx=(0, 6))
        delay = ttk.Combobox(fields_row, textvariable=attack_delay, values=("0", "1", "3"), width=7)
        delay.pack(side="left")
        self.hunt_controls.append(delay)
        tk.Label(
            fields_row, text="Radio (5–500 casillas):", background=SURFACE, foreground=TEXT
        ).pack(side="left", padx=(16, 6))
        radius = ttk.Spinbox(
            fields_row,
            from_=MIN_SEARCH_RADIUS,
            to=MAX_SEARCH_RADIUS,
            textvariable=search_radius,
            width=8,
        )
        radius.pack(side="left")
        self.hunt_controls.append(radius)
        option_label(
            "Desde mi posición solicita combate sin ordenar movimiento; la aceptación a distancia "
            "depende del servidor. Perseguir y atacar usa el recorrido nativo."
        )
        loot = tk.Checkbutton(
            hunting,
            text="Recoger bonus / botín restante al terminar con los mobs (experimental)",
            variable=collect_loot,
            background=SURFACE,
            foreground=TEXT,
            activebackground=SURFACE,
            activeforeground=TEXT,
            selectcolor=BACKGROUND,
        )
        loot.pack(anchor="w", pady=8)
        self.hunt_controls.append(loot)
        option_label(
            "Da 1 s al NeoACA. Después usa la búsqueda nativa en enemigos derrotados. "
            "La recogida del bonus necesita confirmación en el juego."
        )
        controls = tk.Frame(hunting, background=SURFACE)
        controls.pack(anchor="w", pady=8)
        for title, callback in (
            ("Calibrar radio", on_calibrate),
            ("Guardar opciones del perfil", on_save),
        ):
            button = ttk.Button(controls, text=title, command=callback)
            button.pack(side="left", padx=(0, 8))
            self.hunt_controls.append(button)

        def table(frame, columns):
            for index, (_key, title, weight) in enumerate(columns):
                frame.grid_columnconfigure(index, weight=weight)
                tk.Label(
                    frame,
                    text=title,
                    background=SURFACE,
                    foreground=GOLD,
                    font=("Segoe UI", 9, "bold"),
                    anchor="w",
                ).grid(row=0, column=index, sticky="ew", padx=4, pady=(0, 9))
            result = {}
            for slot in range(1, 10):
                result[slot] = {}
                for index, (key, _, _) in enumerate(columns):
                    label = tk.Label(
                        frame,
                        text=member_label(slot) if key == "member" else "—",
                        background=SURFACE,
                        foreground=GOLD if key == "member" else RED if key == "life" else TEXT,
                        font=("Segoe UI", 9, "bold" if slot == 1 else "normal"),
                        anchor="w",
                    )
                    label.grid(row=slot, column=index, sticky="ew", padx=4, pady=4)
                    result[slot][key] = label
            return result

        self.cells = table(
            summary,
            (
                ("member", "Miembro", 0),
                ("name", "Nombre del perfil", 2),
                ("life", "Vida", 1),
                ("present", "En combate", 1),
                ("enabled", "Usar bot", 0),
                ("priority", "Orden", 0),
                ("opening_action", "Acción inicial", 1),
            ),
        )
        self.order_cells = table(
            orders,
            (
                ("member", "Miembro", 0),
                ("opening_action", "Primer turno", 1),
                ("later_action", "Después", 1),
                ("target", "Objetivo de magia", 1),
                ("last_order", "Última orden", 2),
            ),
        )
        for cells in self.order_cells.values():
            cells["last_order"].configure(width=30)

        self.message = tk.StringVar(value="Conecta para consultar el equipo.")
        tk.Label(
            outer,
            textvariable=self.message,
            background=BACKGROUND,
            foreground=MUTED,
            anchor="w",
            justify="left",
            wraplength=790,
        ).pack(fill="x", pady=(8, 3))
        self.run_status = tk.StringVar(value="Bot detenido.")
        tk.Label(
            outer,
            textvariable=self.run_status,
            background=BACKGROUND,
            foreground=BLUE,
            anchor="w",
            justify="left",
            wraplength=790,
        ).pack(fill="x", pady=(0, 6))
        options = tk.Frame(outer, background=BACKGROUND)
        options.pack(fill="x", pady=5)
        tk.Label(options, text="Perfil", background=BACKGROUND, foreground=TEXT).pack(side="left")
        self.profile_list = ttk.Combobox(
            options, textvariable=profile_number, values=("1", "2", "3"), width=3, state="readonly"
        )
        self.profile_list.pack(side="left", padx=(6, 14))
        self.profile_list.bind("<<ComboboxSelected>>", on_profile)
        self.turns_check = tk.Checkbutton(
            options,
            text="Ejecutar turnos del perfil",
            variable=execute_turns,
            background=BACKGROUND,
            foreground=TEXT,
            activebackground=BACKGROUND,
            activeforeground=TEXT,
            selectcolor=SURFACE,
        )
        self.turns_check.pack(side="left")
        self.counts = tk.StringVar(value="")
        tk.Label(options, textvariable=self.counts, background=BACKGROUND, foreground=GOLD).pack(
            side="right"
        )
        buttons = tk.Frame(outer, background=BACKGROUND)
        buttons.pack(fill="x", pady=(4, 0))

        def button(text, command, color=SURFACE):
            result = tk.Button(
                buttons,
                text=text,
                command=command,
                background=color,
                foreground=TEXT,
                activebackground=color,
                activeforeground=TEXT,
                disabledforeground=MUTED,
                relief="flat",
                padx=12,
                pady=5,
            )
            result.pack(side="left", padx=(0, 7))
            return result

        self.start_button = button("Iniciar bot", on_start, "#285b3d")
        self.stop_button = button("Parar bot", on_stop, "#813939")
        self.configure_button = button("Configurar", on_configure)
        button("Actualizar", on_refresh)
        self.copy_button = button("Copiar estado", on_copy)
        self.copy_button.configure(state="disabled")
        self.set_controls(start=False, stop=False, editable=True)

    @property
    def alive(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except self._tcl_error:
            return False

    def paint(self, rows: list[dict], message: str, *, pid: int | None) -> None:
        self.window.title(f"Atlantica — Vista general{f' — PID {pid}' if pid else ''}")
        self._pid = pid
        self.set_turn_mode(self._execute_orders)
        self.message.set(message)
        by_slot = {row["slot"]: row for row in rows}
        for slot, cells in self.cells.items():
            row = by_slot.get(slot, {})
            present = row.get("present")
            alive = row.get("alive")
            state, color = (
                ("Sin batalla", MUTED)
                if present is None
                else ("No presente", MUTED)
                if not present
                else ("Caído", RED)
                if not alive
                else ("Vivo", GREEN)
            )
            values = {
                **row,
                "member": member_label(slot),
                "life": row["life"] if present and row.get("life") is not None else "—",
                "present": state,
                "enabled": "Sí"
                if row.get("enabled") is True
                else "No"
                if row.get("enabled") is False
                else "—",
                "opening_action": row.get("opening_action", "—").replace("Ataque básico", "Básico"),
            }
            for key, label in cells.items():
                label.configure(text=values.get(key, "—"))
            cells["present"].configure(foreground=color)
            cells["opening_action"].configure(foreground=BLUE)
            cells["enabled"].configure(foreground=GREEN if row.get("enabled") else MUTED)
            for key, label in self.order_cells[slot].items():
                value = member_label(slot) if key == "member" else row.get(key, "—")
                label.configure(text=value)

    def set_turn_mode(self, automatic: bool) -> None:
        self._execute_orders = automatic
        identity = f"PID {self._pid}" if self._pid else "Sin conexión"
        mode = "Combate automático" if automatic else "Turnos manuales"
        self.identity.set(f"{identity} · {mode}")
        self.identity_label.configure(foreground=GREEN if automatic else GOLD)

    def set_controls(self, *, start: bool, stop: bool, editable: bool) -> None:
        self.attack_mode_list.configure(state="readonly" if editable else "disabled")
        for widget in self.hunt_controls:
            widget.configure(state="normal" if editable else "disabled")
        self.start_button.configure(state="normal" if start else "disabled")
        self.stop_button.configure(state="normal" if stop else "disabled")
        self.configure_button.configure(state="normal" if editable else "disabled")
        self.turns_check.configure(state="normal" if editable else "disabled")
        self.profile_list.configure(state="readonly" if editable else "disabled")

    def set_run_status(self, message: str, report: dict) -> None:
        self.run_status.set(message)
        self.copy_button.configure(state="normal" if report else "disabled")
        self.counts.set(
            f"Combates: {report.get('battles_observed', 0)} · "
            f"Órdenes: {report.get('combat', {}).get('queued', 0)}"
        )
