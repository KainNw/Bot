"""Manual TBS research interface. Opening it never sends game input."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .errors import DiagnosticError
from .tbs import MAX_SAMPLES, TBS_STAGES, TbsResearch, capture_tbs_snapshot, read_tbs_code
from .ui_theme import card, page_heading


def build_tbs_tab(panel) -> None:
    from tkinter import ttk

    page_heading(panel.tbs_tab, "TBS · Scourge", "Investigación de la misión por casillas")
    box, body = card(panel.tbs_tab, "Capturas de la misión")
    box.pack(fill="x", padx=4, pady=12)
    ttk.Label(
        body,
        text="Comenzaremos con Scourge y solo el Main. La captura registra la selección, "
        "las unidades y los cambios al mover, atacar y pasar de turno manualmente.",
        wraplength=760,
    ).pack(anchor="w", pady=(0, 12))
    ttk.Label(
        body,
        text="Conecta la ventana del juego, detén el bot y abre la captura antes de entrar "
        "en Scourge. Guarda las etapas en un ZIP para analizar sus diferencias.",
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
    window.minsize(760, 520)
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
    table = ttk.Treeview(body, columns=("stage", "route", "units"), show="headings", height=8)
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

    def scope() -> None:
        panel.require_idle_bot(allow_tbs=True)
        if panel.session is not session:
            raise DiagnosticError("La conexión cambió; abre una captura del cliente actual.")

    def take() -> None:
        try:
            scope()
            if len(research.samples) >= MAX_SAMPLES:
                raise DiagnosticError("Guarda este ZIP y abre otra captura para continuar.")
            key = next(key for key, value in TBS_STAGES.items() if value == stage.get())
            snapshot = capture_tbs_snapshot(session)
            if not research.samples:
                blocks, unavailable = read_tbs_code(session)
                research.set_code(blocks, unavailable)
            research.add(key, snapshot, note=note.get())
            bf = snapshot.get("bf", {})
            units = len(bf.get("units", ())) if "units" in bf else "—"
            item = table.insert("", "end", values=(stage.get(), snapshot["route"], units))
            table.see(item)
            save_button.configure(state="normal")
            status.set(
                f"{len(research.samples)} capturas · {snapshot['route']} · "
                f"BF: {bf.get('status', 'inactivo')}. Elige la siguiente etapa y realiza "
                "la acción manualmente."
            )
        except (DiagnosticError, OSError, StopIteration) as exc:
            status.set(str(exc))

    def save() -> None:
        try:
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
        window.destroy()
        panel.tbs_window = None
        panel.tbs_research = None
        panel.lock_target_controls()

    buttons = ttk.Frame(body)
    buttons.pack(fill="x", pady=(12, 0))
    panel.tbs_take_button = ttk.Button(buttons, text="Capturar etapa", command=take)
    panel.tbs_take_button.pack(side="left")
    save_button = ttk.Button(buttons, text="Guardar ZIP", command=save, state="disabled")
    save_button.pack(side="left", padx=8)
    ttk.Button(buttons, text="Copiar última captura", command=copy).pack(side="left")
    ttk.Button(buttons, text="Cerrar", command=close).pack(side="right")
    window.protocol("WM_DELETE_WINDOW", close)
    panel.lock_target_controls()
