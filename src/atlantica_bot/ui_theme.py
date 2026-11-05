"""Shared presentation for the desktop panel and its floating overview."""

BACKGROUND = "#0d1422"
SURFACE = "#172338"
RAISED = "#21314a"
FIELD = "#101b2d"
TEXT = "#e6edf7"
MUTED = "#9badc6"
ACCENT = "#79aeff"
GREEN = "#6edbb7"
RED = "#ff8b9e"
GOLD = "#f1cd83"
BORDER = "#2c405d"


def apply_theme(root) -> None:
    from tkinter import font, ttk

    root.configure(background=BACKGROUND)
    root.option_add("*Toplevel.background", BACKGROUND)
    root.option_add("*Listbox.background", FIELD)
    root.option_add("*Listbox.foreground", TEXT)
    root.option_add("*Listbox.selectBackground", "#345989")
    root.option_add("*Listbox.selectForeground", "#ffffff")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        font.nametofont(name).configure(family="Segoe UI", size=10)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=SURFACE, foreground=TEXT, bordercolor=BORDER)
    style.configure("TFrame", background=SURFACE)
    style.configure("Page.TFrame", background=BACKGROUND)
    style.configure("Card.TFrame", background=SURFACE, relief="flat")
    style.configure("TLabel", background=SURFACE, foreground=TEXT)
    style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), background=BACKGROUND)
    style.configure(
        "Brand.TLabel", font=("Segoe UI", 10, "bold"), foreground=ACCENT, background=BACKGROUND
    )
    style.configure("PageTitle.TLabel", font=("Segoe UI", 16, "bold"), background=BACKGROUND)
    style.configure("PageHint.TLabel", foreground=MUTED, background=BACKGROUND)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Caption.TLabel", foreground=MUTED, font=("Segoe UI", 9))
    style.configure("Accent.TLabel", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
    style.configure("Connected.TLabel", foreground=GREEN, background=BACKGROUND)
    style.configure("Disconnected.TLabel", foreground=MUTED, background=BACKGROUND)
    style.configure("Run.TLabel", font=("Segoe UI", 12, "bold"), foreground=GREEN)
    style.configure("Idle.Run.TLabel", foreground=MUTED)
    style.configure("Stopping.Run.TLabel", foreground=GOLD)
    style.configure(
        "TButton",
        background=RAISED,
        foreground=TEXT,
        borderwidth=1,
        relief="flat",
        padding=(12, 8),
        focusthickness=2,
        focuscolor=ACCENT,
    )
    style.map(
        "TButton",
        background=[("disabled", SURFACE), ("pressed", "#304968"), ("active", "#2b4263")],
        foreground=[("disabled", "#65778f")],
        bordercolor=[("focus", ACCENT)],
    )
    style.configure(
        "Primary.TButton", background="#346ce0", foreground="#ffffff", font=("Segoe UI", 10, "bold")
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", RAISED), ("pressed", "#2852b0"), ("active", "#447cf0")],
    )
    style.configure("Stop.TButton", foreground=RED, background="#3b2638")
    style.map(
        "Stop.TButton",
        background=[("disabled", SURFACE), ("pressed", "#633446"), ("active", "#523044")],
    )
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(
            name,
            fieldbackground=FIELD,
            foreground=TEXT,
            background=RAISED,
            insertcolor=TEXT,
            arrowcolor=MUTED,
            padding=7,
            selectbackground="#345989",
            selectforeground="#ffffff",
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            name,
            fieldbackground=[("disabled", SURFACE), ("readonly", FIELD)],
            foreground=[("disabled", "#65778f"), ("readonly", TEXT)],
            bordercolor=[("focus", ACCENT), ("!focus", BORDER)],
        )
    style.configure(
        "TCheckbutton",
        foreground=TEXT,
        background=SURFACE,
        padding=(0, 5),
        focuscolor=ACCENT,
        indicatorbackground=FIELD,
        indicatorforeground=TEXT,
    )
    style.map(
        "TCheckbutton",
        background=[("active", SURFACE)],
        foreground=[("disabled", "#65778f")],
        indicatorbackground=[("selected", "#346ce0"), ("!selected", FIELD)],
    )
    style.configure(
        "TNotebook",
        background=BACKGROUND,
        borderwidth=0,
        tabmargins=(0, 0, 0, 12),
        lightcolor=BACKGROUND,
        darkcolor=BACKGROUND,
        bordercolor=BACKGROUND,
    )
    style.configure(
        "TNotebook.Tab",
        background=BACKGROUND,
        foreground=MUTED,
        padding=(20, 11),
        borderwidth=0,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        bordercolor=SURFACE,
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", SURFACE), ("active", RAISED)],
        foreground=[("selected", ACCENT), ("active", TEXT)],
        lightcolor=[("selected", SURFACE), ("!selected", BACKGROUND)],
        darkcolor=[("selected", SURFACE), ("!selected", BACKGROUND)],
        bordercolor=[("selected", SURFACE), ("!selected", BACKGROUND)],
        expand=[("selected", (0, 0, 0, 0))],
    )
    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        rowheight=28,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        bordercolor=SURFACE,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        background=RAISED,
        foreground=MUTED,
        padding=(8, 10),
        font=("Segoe UI", 9, "bold"),
        relief="flat",
    )
    style.map(
        "Treeview", background=[("selected", "#294b78")], foreground=[("selected", "#ffffff")]
    )
    style.map("Treeview.Heading", background=[("active", "#304968")])
    style.configure(
        "TScrollbar",
        background=RAISED,
        troughcolor=FIELD,
        arrowcolor=MUTED,
        borderwidth=0,
        lightcolor=RAISED,
        darkcolor=RAISED,
        bordercolor=RAISED,
    )
    style.configure("TSeparator", background=BORDER)


def card(parent, title: str, *, subtitle: str = ""):
    from tkinter import ttk

    frame = ttk.Frame(parent, style="Card.TFrame", padding=16)
    ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(frame, text=subtitle, style="Muted.TLabel", wraplength=520).pack(
            anchor="w", pady=(4, 0)
        )
    body = ttk.Frame(frame)
    body.pack(fill="both", expand=True, pady=(10, 0))
    return frame, body


def page_heading(parent, title: str, subtitle: str):
    from tkinter import ttk

    heading = ttk.Frame(parent, style="Page.TFrame")
    heading.pack(fill="x", pady=(0, 16))
    ttk.Label(heading, text=title, style="PageTitle.TLabel").pack(anchor="w")
    ttk.Label(heading, text=subtitle, style="PageHint.TLabel", wraplength=880).pack(
        anchor="w", pady=(4, 0)
    )
