"""Build the desktop layout without issuing game commands or changing profiles."""

from .limits import MAX_SEARCH_RADIUS, MIN_SEARCH_RADIUS
from .profiles import WORLD_ATTACK_LABELS
from .ui_theme import apply_theme, card, page_heading, scrollable


def build_panel(p) -> None:
    from tkinter import ttk

    apply_theme(p.root)
    p.root.minsize(920, 650)
    p.root.geometry(
        f"{min(1060, p.root.winfo_screenwidth() - 70)}x{min(760, p.root.winfo_screenheight() - 90)}"
    )
    shell = ttk.Frame(p.root, style="Page.TFrame", padding=(22, 18, 22, 16))
    shell.pack(fill="both", expand=True)
    heading = ttk.Frame(shell, style="Page.TFrame")
    heading.pack(fill="x", pady=(0, 18))
    brand = ttk.Frame(heading, style="Page.TFrame")
    brand.pack(side="left")
    ttk.Label(brand, text="ATLANTICA", style="Brand.TLabel").pack(anchor="w")
    ttk.Label(brand, text="Panel del bot", style="Title.TLabel").pack(anchor="w")
    identity = ttk.Frame(heading, style="Page.TFrame")
    identity.pack(side="right")
    ttk.Label(identity, textvariable=p.header_name, style="Title.TLabel").pack(anchor="e")
    p.header_badge = ttk.Label(identity, textvariable=p.header_context, style="Disconnected.TLabel")
    p.header_badge.pack(anchor="e", pady=(3, 0))

    # The action bar is outside the notebook and stays available on every tab.
    footer = ttk.Frame(shell, style="Card.TFrame", padding=(18, 12))
    footer.pack(side="bottom", fill="x", pady=(16, 0))
    footer.columnconfigure(0, weight=1)
    state = ttk.Frame(footer)
    state.grid(row=0, column=0, sticky="w")
    p.run_badge = ttk.Label(state, textvariable=p.run_phase, style="Idle.Run.TLabel")
    p.run_badge.pack(anchor="w")
    ttk.Label(state, textvariable=p.run_summary, style="Caption.TLabel").pack(
        anchor="w", pady=(3, 0)
    )
    actions = ttk.Frame(footer)
    actions.grid(row=0, column=1, sticky="e", padx=(12, 0))
    p.bot_start_button = ttk.Button(
        actions, text="Iniciar bot", command=p.start_bot, state="disabled", style="Primary.TButton"
    )
    p.bot_start_button.pack(side="left", padx=(0, 8))
    p.bot_stop_button = ttk.Button(
        actions, text="Parar bot", command=p.stop_bot, state="disabled", style="Stop.TButton"
    )
    p.bot_stop_button.pack(side="left", padx=(0, 8))
    p.bot_copy_button = ttk.Button(
        actions, text="Copiar estado", command=p.copy_bot, state="disabled"
    )
    p.bot_copy_button.pack(side="left")

    p.tabs = ttk.Notebook(shell)
    p.tabs.pack(fill="both", expand=True)
    p.control_tab = ttk.Frame(p.tabs, style="Page.TFrame")
    p.team_tab = ttk.Frame(p.tabs, style="Page.TFrame")
    p.hunt_tab = ttk.Frame(p.tabs, style="Page.TFrame")
    p.diagnostics_tab = ttk.Frame(p.tabs, style="Page.TFrame")
    for frame, title in (
        (p.control_tab, "Control"),
        (p.team_tab, "Mercenarios"),
        (p.hunt_tab, "Caza y botín"),
        (p.diagnostics_tab, "Diagnóstico"),
    ):
        p.tabs.add(frame, text=title)

    _control(p)
    p.build_team_tab()
    _hunting(p)
    _diagnostics(p)


def _control(p) -> None:
    from tkinter import ttk

    scroll, content = scrollable(p.control_tab)
    scroll.pack(fill="both", expand=True)
    columns = ttk.Frame(content, style="Page.TFrame")
    columns.pack(fill="x")
    columns.columnconfigure(0, weight=3, uniform="control")
    columns.columnconfigure(1, weight=2, uniform="control")
    connection, body = card(columns, "01  Cliente del juego")
    connection.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
    ttk.Label(body, text="Ventana de Atlantica", style="Caption.TLabel").pack(anchor="w")
    p.window_list = ttk.Combobox(body, textvariable=p.window_choice, state="readonly", width=36)
    p.window_list.pack(fill="x", pady=(5, 8))
    p.window_list.bind("<<ComboboxSelected>>", p.choose_window)
    row = ttk.Frame(body)
    row.pack(fill="x")
    p.list_button = ttk.Button(row, text="Actualizar lista", command=p.list_windows)
    p.list_button.pack(side="left", padx=(0, 8))
    p.pick_button = ttk.Button(row, text="Elegir ventana", command=p.pick_window)
    p.pick_button.pack(side="left")
    row = ttk.Frame(body)
    row.pack(fill="x", pady=(12, 0))
    ttk.Label(row, text="PID", style="Caption.TLabel").pack(side="left", padx=(0, 8))
    p.pid_entry = ttk.Entry(row, textvariable=p.pid, width=10)
    p.pid_entry.pack(side="left", padx=(0, 8))
    p.connect_button = ttk.Button(row, text="Conectar", command=p.connect, style="Primary.TButton")
    p.connect_button.pack(side="left")
    ttk.Label(body, text="Nombre del Main", style="Caption.TLabel").pack(anchor="w", pady=(14, 5))
    p.alias_entry = ttk.Entry(body, textvariable=p.main_alias, state="disabled")
    p.alias_entry.pack(fill="x")
    ttk.Label(body, textvariable=p.main_name_status, style="Caption.TLabel", wraplength=460).pack(
        anchor="w", pady=(6, 0)
    )

    profile, body = card(columns, "02  Perfil de combate")
    profile.grid(row=0, column=1, sticky="nsew")
    row = ttk.Frame(body)
    row.pack(fill="x")
    ttk.Label(row, text="Perfil", style="Caption.TLabel").pack(side="left", padx=(0, 10))
    p.profile_list = ttk.Combobox(
        row, textvariable=p.profile_number, values=("1", "2", "3"), state="readonly", width=5
    )
    p.profile_list.pack(side="left")
    p.profile_list.bind("<<ComboboxSelected>>", p.load_profile)
    p.profile_button = ttk.Button(body, text="Configurar mercenarios", command=p.edit_profile)
    p.profile_button.pack(fill="x", pady=(12, 8))
    ttk.Button(body, text="Abrir vista general", command=p.show_overview).pack(fill="x")
    p.turns_check = ttk.Checkbutton(
        body, text="Ejecutar turnos del perfil", variable=p.turns_enabled
    )
    p.turns_check.pack(anchor="w", pady=(12, 4))
    ttk.Label(body, textvariable=p.profile_status, style="Caption.TLabel", wraplength=280).pack(
        anchor="w"
    )
    ttk.Label(
        body, textvariable=p.character_settings_status, style="Caption.TLabel", wraplength=280
    ).pack(anchor="w", pady=(8, 0))

    session, body = card(content, "Estado de la sesión")
    session.pack(fill="both", expand=True, pady=(14, 0))
    ttk.Label(body, textvariable=p.status, style="Accent.TLabel").pack(anchor="w")
    ttk.Label(body, textvariable=p.execution_status, wraplength=780).pack(anchor="w", pady=(6, 0))
    ttk.Label(body, textvariable=p.bot_status, style="Muted.TLabel", wraplength=780).pack(
        anchor="w", pady=(6, 0)
    )
    ttk.Label(body, textvariable=p.detail, style="Caption.TLabel", wraplength=780).pack(
        anchor="w", pady=(6, 0)
    )


def _hunting(p) -> None:
    from tkinter import ttk

    page_heading(
        p.hunt_tab, "Caza y botín", "Ajusta la búsqueda, el ritmo y las opciones del perfil."
    )
    scroll, content = scrollable(p.hunt_tab)
    columns = ttk.Frame(content, style="Page.TFrame")
    for column in (0, 1):
        columns.columnconfigure(column, weight=1, uniform="hunt")
    hunting, body = card(columns, "Búsqueda y ataque")
    hunting.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
    ttk.Label(body, text="Modo de ataque", style="Caption.TLabel").pack(anchor="w")
    p.attack_mode_list = ttk.Combobox(
        body,
        textvariable=p.world_attack_mode,
        values=tuple(WORLD_ATTACK_LABELS.values()),
        state="readonly",
        width=32,
    )
    p.attack_mode_list.pack(fill="x", pady=(5, 10))
    row = ttk.Frame(body)
    row.pack(fill="x")
    ttk.Label(row, text="Radio (casillas)", style="Caption.TLabel").pack(side="left")
    p.radius_entry = ttk.Spinbox(
        row, from_=MIN_SEARCH_RADIUS, to=MAX_SEARCH_RADIUS, textvariable=p.search_radius, width=6
    )
    p.radius_entry.pack(side="left", padx=8)
    p.radius_calibrate_button = ttk.Button(row, text="Calibrar", command=p.calibrate_radius)
    p.radius_calibrate_button.pack(side="right")
    ttk.Label(
        body,
        text="De 5 a 500 casillas. Se usan los mobs cargados por el juego.",
        wraplength=370,
        style="Caption.TLabel",
    ).pack(anchor="w", pady=(4, 10))
    row = ttk.Frame(body)
    row.pack(fill="x")
    ttk.Label(row, text="Espera antes de atacar", style="Caption.TLabel").pack(side="left")
    p.delay_entry = ttk.Combobox(row, textvariable=p.attack_delay, values=("0", "1", "3"), width=6)
    p.delay_entry.pack(side="left", padx=8)
    ttk.Label(row, text="s", style="Muted.TLabel").pack(side="left")
    ttk.Label(
        body,
        text="De 0 a 60 s. La magia del primer turno conserva su rapidez.",
        wraplength=370,
        style="Caption.TLabel",
    ).pack(anchor="w", pady=(6, 8))
    ttk.Label(
        body,
        text="Desde mi posición solicita combate sin ordenar acercamiento. "
        "La distancia aceptada depende del servidor.",
        wraplength=370,
        style="Muted.TLabel",
    ).pack(anchor="w")

    extras = ttk.Frame(columns, style="Page.TFrame")
    extras.grid(row=0, column=1, sticky="nsew")
    speed, body = card(extras, "Speed en combate")
    speed.pack(fill="x")
    row = ttk.Frame(body)
    row.pack(fill="x")
    p.battle_speed_check = ttk.Checkbutton(
        row, text="Activar Speed", variable=p.battle_speed_enabled
    )
    p.battle_speed_check.pack(side="left")
    p.battle_speed_list = ttk.Combobox(
        row,
        textvariable=p.battle_speed_rate,
        values=("1.25", "1.5", "2", "3", "4"),
        state="readonly",
        width=6,
    )
    p.battle_speed_list.pack(side="left", padx=8)
    ttk.Label(row, text="×").pack(side="left")
    ttk.Label(body, textvariable=p.battle_speed_status, style="Accent.TLabel", wraplength=370).pack(
        anchor="w", pady=(8, 4)
    )
    ttk.Label(
        body,
        text="Vuelve a 1× al salir del combate o parar el bot.",
        style="Caption.TLabel",
        wraplength=370,
    ).pack(anchor="w")
    loot, body = card(extras, "Botín y bonus")
    loot.pack(fill="both", expand=True, pady=(14, 0))
    p.loot_check = ttk.Checkbutton(
        body, text="Recoger botín restante / bonus", variable=p.collect_loot
    )
    p.loot_check.pack(anchor="w")
    row = ttk.Frame(body)
    row.pack(fill="x", pady=(10, 0))
    ttk.Label(row, text="Espera del NeoACA (0–5 s)").pack(side="left")
    p.neo_loot_grace_entry = ttk.Spinbox(
        row, from_=0, to=5, increment=0.25, textvariable=p.neo_loot_grace, width=6
    )
    p.neo_loot_grace_entry.pack(side="left", padx=8)
    ttk.Label(
        body,
        text="Al terminar con los mobs, espera al NeoACA y después busca el botín restante. "
        "La recogida del bonus es experimental.",
        style="Caption.TLabel",
        wraplength=370,
    ).pack(anchor="w", pady=(8, 0))
    save = ttk.Frame(p.hunt_tab, style="Page.TFrame")
    save.pack(side="bottom", fill="x", pady=(14, 0))
    p.save_hunt_button = ttk.Button(
        save, text="Guardar opciones del perfil", command=p.save_hunt_options
    )
    p.save_hunt_button.pack(side="left")
    ttk.Label(
        save, text="Iniciar bot también guarda estas opciones.", style="PageHint.TLabel"
    ).pack(side="left", padx=12)

    scroll.pack(fill="both", expand=True)
    columns.pack(fill="both", expand=True)


def _diagnostics(p) -> None:
    from tkinter import ttk

    page_heading(p.diagnostics_tab, "Diagnóstico", "Consultas, capturas y pruebas individuales.")
    scroll, content = scrollable(p.diagnostics_tab)
    scroll.pack(fill="both", expand=True)
    diagnostics, body = card(content, "Lecturas y capturas")
    diagnostics.pack(fill="x")
    row = ttk.Frame(body)
    row.pack(fill="x")
    p.capture_button = ttk.Button(
        row, text="Exportar diagnóstico", command=p.export, state="disabled"
    )
    p.capture_button.pack(side="left", padx=(0, 8))
    p.combat_capture_button = ttk.Button(
        row, text="Exportar combate", command=lambda: p.export(combat=True), state="disabled"
    )
    p.combat_capture_button.pack(side="left", padx=(0, 8))
    p.targets_button = ttk.Button(
        row, text="Ver objetivos", command=p.show_targets, state="disabled"
    )
    p.targets_button.pack(side="left")
    row = ttk.Frame(body)
    row.pack(fill="x", pady=(10, 0))
    p.members_button = ttk.Button(
        row, text="Ver mercenarios", command=p.show_members, state="disabled"
    )
    p.members_button.pack(side="left", padx=(0, 8))
    p.calibration_button = ttk.Button(
        row, text="Calibrar combate", command=p.calibrate_combat, state="disabled"
    )
    p.calibration_button.pack(side="left", padx=(0, 8))
    ttk.Button(row, text="Capturar bonus", command=p.capture_bonus).pack(side="left")
    ttk.Label(body, textvariable=p.detector_status, style="Caption.TLabel", wraplength=780).pack(
        anchor="w", pady=(12, 0)
    )
    tools, body = card(content, "Herramientas adicionales")
    tools.pack(fill="both", expand=True, pady=(14, 0))
    row = ttk.Frame(body)
    row.pack(fill="x")
    p.browse_button = ttk.Button(row, text="Seleccionar carpeta", command=p.browse)
    p.browse_button.pack(side="left", padx=(0, 8))
    ttk.Button(row, text="Prueba de velocidad nativa", command=p.open_speed_trial).pack(side="left")
    ttk.Label(body, textvariable=p.folder, style="Caption.TLabel", wraplength=780).pack(
        anchor="w", pady=(10, 6)
    )
    p.more_button = ttk.Button(body, text="Mostrar controles avanzados", command=p.toggle_advanced)
    p.more_button.pack(anchor="w")
    p.advanced = ttk.Frame(body)
    row = ttk.Frame(p.advanced)
    row.pack(fill="x", pady=(10, 0))
    p.start_button = ttk.Button(row, text="Activar caza nativa", command=p.start, state="disabled")
    p.start_button.pack(side="left", padx=(0, 8))
    p.stop_button = ttk.Button(row, text="Parar caza nativa", command=p.stop, state="disabled")
    p.stop_button.pack(side="left", padx=(0, 8))
    p.trial_button = ttk.Button(
        row, text="Probar ataque cercano", command=p.attack_once, state="disabled"
    )
    p.trial_button.pack(side="left", padx=(0, 8))
    p.copy_trial_button = ttk.Button(
        row, text="Copiar prueba", command=p.copy_trial, state="disabled"
    )
    p.copy_trial_button.pack(side="left")
    ttk.Label(p.advanced, textvariable=p.scope_status, style="Caption.TLabel", wraplength=780).pack(
        anchor="w", pady=(8, 0)
    )
    ttk.Label(p.advanced, textvariable=p.request, style="Caption.TLabel").pack(anchor="w", pady=4)
