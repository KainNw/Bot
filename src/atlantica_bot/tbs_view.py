"""Manual TBS research interface. Opening it never sends game input."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .errors import DiagnosticError
from .tbs import MAX_SAMPLES, TBS_STAGES, TbsResearch, TbsTrace, capture_tbs_snapshot, read_tbs_code
from .tbs_state import describe_tbs_snapshot
from .ui_theme import card, page_heading


def build_tbs_tab(panel) -> None:
    from tkinter import ttk

    page_heading(panel.tbs_tab, "TBS · Scourge", "Investigación de la misión por casillas")
    box, body = card(panel.tbs_tab, "Capturas de la misión")
    box.pack(fill="x", padx=4, pady=12)
    ttk.Label(
        body,
        text="TBS → Three Kingdoms → Scourge. El visor identifica al Main, su posición "
        "interna, HP/MP y las unidades de otros bandos a partir de cada captura.",
        wraplength=760,
    ).pack(anchor="w", pady=(0, 12))
    ttk.Label(
        body,
        text="Conecta la ventana del juego, detén el bot y abre la captura antes de entrar "
        "en Scourge. Dentro de la misión puedes registrar 12 segundos mientras juegas "
        "para observar el cambio entre tu turno y el del enemigo.",
        style="Caption.TLabel",
        wraplength=760,
    ).pack(anchor="w", pady=(0, 12))
    panel.tbs_capture_button = ttk.Button(
        body, text="Abrir captura TBS", command=panel.capture_tbs, style="Primary.TButton"
    )
    panel.tbs_capture_button.pack(anchor="w")
    ttk.Label(
        body,
        text="Las órdenes automáticas de TBS se habilitarán después de verificar "
        "estos estados. Iniciar bot sigue correspondiendo a la caza normal.",
        style="Caption.TLabel",
        wraplength=760,
    ).pack(anchor="w", pady=(12, 0))


def open_tbs_capture(panel) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk

    if panel.tbs_open():
        panel.tbs_window.lift()
        return
    try:
        panel.require_idle_bot()
        session = panel.session
        if session is None or session.creation_time is None:
            raise DiagnosticError("Conecta con la ventana elegida antes de capturar TBS.")
        research = TbsResearch(session.process.pid, session.creation_time)
    except DiagnosticError as exc:
        panel.error(exc)
        return
    window = panel.tbs_window = tk.Toplevel(panel.root)
    window.title(f"PID {session.process.pid} — TBS Scourge · captura de memoria")
    window.minsize(800, 650)
    body = ttk.Frame(window, padding=18)
    body.pack(fill="both", expand=True)
    ttk.Label(
        body,
        text="Con el bot, Auto Battle y Speed detenidos, captura antes y después de cada "
        "acción manual. Espera a que termine el movimiento o la animación. "
        "Puedes guardar el ZIP aunque falten etapas.",
        wraplength=800,
    ).pack(anchor="w", pady=(0, 12))
    mission, formation = tk.StringVar(value="Scourge"), tk.StringVar(value="Solo Main")
    row = ttk.Frame(body)
    row.pack(fill="x")
    ttk.Label(row, text="Misión:").pack(side="left")
    ttk.Entry(row, textvariable=mission, width=25).pack(side="left", padx=(8, 18))
    ttk.Label(row, text="Formación:").pack(side="left")
    ttk.Entry(row, textvariable=formation, width=28).pack(side="left", padx=8)
    stage = tk.StringVar(value=TBS_STAGES["map_before"])
    stage_list = ttk.Combobox(
        body, textvariable=stage, values=tuple(TBS_STAGES.values()), state="readonly", width=50
    )
    stage_list.pack(anchor="w", pady=(12, 8))
    note = tk.StringVar()
    ttk.Label(body, text="Nota opcional: tecla, casilla o resultado que observaste").pack(
        anchor="w"
    )
    ttk.Entry(body, textvariable=note).pack(fill="x", pady=(4, 10))
    status = tk.StringVar(value="0 capturas. Empieza en el mapa, antes de entrar en Scourge.")
    ttk.Label(body, textvariable=status, wraplength=800).pack(anchor="w", pady=(0, 8))
    latest = tk.StringVar(value="Última captura: sin datos del Main.")
    ttk.Label(body, textvariable=latest, wraplength=800).pack(anchor="w", pady=(0, 8))
    units_table = ttk.Treeview(
        body, columns=("unit", "group", "position", "hp", "mp", "state"), show="headings", height=5
    )
    for key, title, width in (
        ("unit", "Unidad", 75),
        ("group", "Bando", 50),
        ("position", "Posición interna", 95),
        ("hp", "HP", 105),
        ("mp", "MP", 100),
        ("state", "Estado", 295),
    ):
        units_table.heading(key, text=title)
        units_table.column(key, width=width, minwidth=45)
    units_table.pack(fill="both", expand=True, pady=(0, 10))
    table = ttk.Treeview(body, columns=("stage", "route", "units"), show="headings", height=5)
    for key, title, width in (
        ("stage", "Etapa indicada", 315),
        ("route", "Ruta observada", 235),
        ("units", "Unidades", 85),
    ):
        table.heading(key, text=title)
        table.column(key, width=width, minwidth=70)
    table.pack(fill="both", expand=True)
    panel.tbs_research = research
    panel.tbs_stage, panel.tbs_note, panel.tbs_status = stage, note, status
    panel.tbs_units_table, panel.tbs_latest = units_table, latest
    trace = None
    trace_job = None

    def scope() -> None:
        panel.require_idle_bot(allow_tbs=True)
        if panel.session is not session:
            raise DiagnosticError("La conexión cambió; abre una captura del cliente actual.")

    def ensure_code() -> None:
        if not research.blocks and not research.unavailable_code:
            blocks, unavailable = read_tbs_code(session)
            research.set_code(blocks, unavailable)

    def paint(snapshot: dict, label: str) -> None:
        bf = snapshot.get("bf", {})
        units = len(bf.get("units", ())) if "units" in bf else "—"
        item = table.insert("", "end", values=(label, snapshot["route"], units))
        table.see(item)
        save_button.configure(state="normal")
        view = snapshot.get("view") or describe_tbs_snapshot(snapshot)
        units_table.delete(*units_table.get_children())
        for unit in view["units"]:
            position = unit.get("position") or ("—", "—")
            hp, mp = unit.get("hp"), unit.get("mp")
            role = "Main" if unit.get("role") == "main" else f"Unidad {unit['index']}"
            state = "Derrotado" if unit["life_status"] == "defeated" else unit["state_label"]
            units_table.insert(
                "",
                "end",
                values=(
                    role,
                    unit.get("group"),
                    f"{position[0]}, {position[1]}",
                    f"{hp if hp is not None else '—'} / {unit.get('hp_max', '—')}",
                    f"{mp if mp is not None else '—'} / {unit.get('mp_max', '—')}",
                    state,
                ),
            )
        main = view.get("main")
        if main is None:
            latest.set(
                "Última captura: Main TBS no identificado; espera a estar dentro de la misión."
            )
        else:
            relation = {
                "same_group": "bando del Main activo",
                "other_group": "otro bando activo",
                "unknown": "bando activo sin datos",
            }[view["main_turn_relation"]]
            latest.set(
                f"Última captura: Main en {main['position']} · {relation} · "
                f"contador {view.get('turn_counter')} · "
                f"otros bandos vivos: {view.get('other_groups_alive', 0)}. "
                "El estado es parcial; todavía no habilita órdenes automáticas."
            )

    def take() -> None:
        try:
            scope()
            if len(research.samples) >= MAX_SAMPLES:
                raise DiagnosticError("Guarda este ZIP y abre otra captura para continuar.")
            key = next(key for key, value in TBS_STAGES.items() if value == stage.get())
            snapshot = capture_tbs_snapshot(session)
            ensure_code()
            research.add(key, snapshot, note=note.get())
            bf = snapshot.get("bf", {})
            paint(snapshot, stage.get())
            status.set(
                f"{len(research.samples)} capturas · {snapshot['route']} · "
                f"BF: {bf.get('status', 'inactivo')}. Elige la siguiente etapa y realiza "
                "la acción manualmente."
            )
            if (
                key not in ("map_before", "map_after")
                and snapshot["route"] != "bf_context_b_candidate"
            ):
                status.set(
                    "Captura guardada; todavía no aparece el contexto TBS activo. "
                    "Espera a que termine la entrada a la misión y vuelve a capturar."
                )
        except (DiagnosticError, OSError, StopIteration) as exc:
            status.set(str(exc))

    def stop_trace(reason: str = "manual") -> None:
        nonlocal trace_job
        if trace_job is not None:
            window.after_cancel(trace_job)
            trace_job = None
        if trace is not None:
            trace.stop(reason)
        trace_button.configure(text="Registrar turnos 12 s")
        panel.tbs_take_button.configure(state="normal")
        stage_list.configure(state="readonly")

    def tick() -> None:
        nonlocal trace_job
        trace_job = None
        try:
            scope()
            snapshot = trace.step()
            if snapshot is not None:
                paint(snapshot, TBS_STAGES["turn_trace"])
            status.set(
                f"Seguimiento: {trace.added} muestras · "
                f"lecturas transitorias: {trace.transient_reads} · "
                f"{trace.error or ('registrando' if trace.running else 'terminado')}. "
                "Juega normalmente; guarda el ZIP al terminar."
            )
            if trace.running:
                trace_job = window.after(600, tick)
            else:
                stop_trace()
        except (DiagnosticError, OSError) as exc:
            stop_trace("scope_changed")
            status.set(str(exc))

    def toggle_trace() -> None:
        nonlocal trace, trace_job
        if trace is not None and trace.running:
            stop_trace()
            status.set("Seguimiento detenido. Puedes guardar el ZIP.")
            return
        try:
            scope()
            ensure_code()
            trace = TbsTrace(research, session, capture=capture_tbs_snapshot)
            trace_button.configure(text="Detener registro")
            panel.tbs_take_button.configure(state="disabled")
            stage_list.configure(state="disabled")
            trace_job = window.after(0, tick)
        except (DiagnosticError, OSError) as exc:
            status.set(str(exc))

    def save() -> None:
        try:
            stop_trace("saved")
            filename = filedialog.asksaveasfilename(
                parent=window,
                title="Guardar investigación TBS",
                defaultextension=".zip",
                filetypes=[("Archivo ZIP", "*.zip")],
                initialfile=f"Atlantica-PID{session.process.pid}-TBS-"
                f"{datetime.now():%Y%m%d-%H%M%S}.zip",
            )
            if filename:
                research.export(Path(filename), mission=mission.get(), formation=formation.get())
                status.set(f"ZIP guardado: {filename}. Adjunta este archivo al chat.")
        except (DiagnosticError, OSError) as exc:
            status.set(str(exc))

    def copy() -> None:
        if research.samples:
            panel.root.clipboard_clear()
            panel.root.clipboard_append(
                json.dumps(research.samples[-1], ensure_ascii=False, indent=2)
            )

    def close() -> None:
        stop_trace("window_closed")
        window.destroy()
        panel.tbs_window = None
        panel.tbs_research = None
        panel.lock_target_controls()

    buttons = ttk.Frame(body)
    buttons.pack(fill="x", pady=(12, 0))
    panel.tbs_take_button = ttk.Button(buttons, text="Capturar etapa", command=take)
    panel.tbs_take_button.pack(side="left")
    trace_button = panel.tbs_trace_button = ttk.Button(
        buttons, text="Registrar turnos 12 s", command=toggle_trace
    )
    trace_button.pack(side="left", padx=8)
    save_button = ttk.Button(buttons, text="Guardar ZIP", command=save, state="disabled")
    save_button.pack(side="left", padx=8)
    ttk.Button(buttons, text="Copiar última captura", command=copy).pack(side="left")
    ttk.Button(buttons, text="Cerrar", command=close).pack(side="right")
    window.protocol("WM_DELETE_WINDOW", close)
    panel.lock_target_controls()
