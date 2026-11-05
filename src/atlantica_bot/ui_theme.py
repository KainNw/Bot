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


def scrollable(parent):
    """Keep settings reachable in small windows without scrolling the action bar."""
    import tkinter as tk
    from tkinter import ttk

    outer = ttk.Frame(parent, style="Page.TFrame")
    canvas = tk.Canvas(
        outer, background=BACKGROUND, highlightthickness=0, borderwidth=0, yscrollincrement=24
    )
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    body = ttk.Frame(canvas, style="Page.TFrame")
    item = canvas.create_window((0, 0), window=body, anchor="nw")
    pending = [False]

    def resize():
        pending[0] = False
        try:
            width, height = canvas.winfo_width(), canvas.winfo_height()
            content_height = max(height, body.winfo_reqheight())
            canvas.itemconfigure(item, width=width, height=content_height)
            canvas.configure(scrollregion=(0, 0, width, content_height))
            if content_height > height + 1:
                if not scrollbar.winfo_manager():
                    scrollbar.pack(side="right", fill="y", padx=(8, 0))
            else:
                scrollbar.pack_forget()
                canvas.yview_moveto(0)
        except tk.TclError:
            pass  # The window may have closed before this idle redraw.

    def schedule(_event=None):
        if not pending[0]:
            pending[0] = True
            outer.after_idle(resize)

    def contains(widget):
        while widget is not None:
            if widget == body or widget == canvas or widget == scrollbar:
                return True
            widget = getattr(widget, "master", None)
        return False

    def wheel(event):
        if not canvas.winfo_ismapped() or not contains(event.widget):
            return None
        if event.widget.winfo_class() in ("TCombobox", "TSpinbox", "Treeview", "Text"):
            return None
        delta = getattr(event, "delta", 0)
        direction = -1 if getattr(event, "num", None) == 4 or delta > 0 else 1
        canvas.yview_scroll(direction * max(1, abs(delta) // 120), "units")
        return "break"

    def focus(event):
        if not canvas.winfo_ismapped() or not contains(event.widget):
            return
        top = event.widget.winfo_rooty() - body.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        visible = canvas.canvasy(0)
        size = max(1, body.winfo_height())
        if top < visible:
            canvas.yview_moveto(max(0, top - 8) / size)
        elif bottom > visible + canvas.winfo_height():
            canvas.yview_moveto((bottom - canvas.winfo_height() + 8) / size)

    body.bind("<Configure>", schedule)
    canvas.bind("<Configure>", schedule)
    window = outer.winfo_toplevel()
    window.bind("<MouseWheel>", wheel, add="+")
    window.bind("<Button-4>", wheel, add="+")
    window.bind("<Button-5>", wheel, add="+")
    window.bind("<FocusIn>", focus, add="+")
    return outer, body
