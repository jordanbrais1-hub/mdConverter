"""CustomTkinter user interface.

Layout::

    +---------------------------------------------------------------+
    | header: title · appearance · settings                         |
    +------------------------------+--------------------------------+
    | drop zone + Add buttons      | Tabs: Preview | Report | Log   |
    | file queue (Treeview)        |                                |
    | output destination options   |                                |
    +------------------------------+--------------------------------+
    | Convert · Cancel · progress · status · Open Output Folder     |
    +---------------------------------------------------------------+

All conversion work happens in :class:`ConversionWorker`; this module only
reacts to the events it posts, polled with ``after()`` on the Tk main loop.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import __app_name__, __version__
from .converter import (
    BatchFinished,
    BatchStarted,
    ConversionResult,
    ConversionWorker,
    FileFinished,
    FileStarted,
    Status,
    format_report,
    summarize,
)
from .settings import AppSettings, validate_llm_endpoint
from .utils import (
    SUPPORTED_EXTENSIONS,
    PathEscapeError,
    SourceItem,
    UnsafePathError,
    discover_files,
    human_size,
    open_path,
    plan_output_paths,
    prepare_output_dir,
    resource_path,
    reveal_in_file_manager,
)

log = logging.getLogger(__name__)

try:  # Drag and drop is a nice-to-have: the app still works without it.
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # pragma: no cover - depends on install
    TkinterDnD = None
    DND_FILES = None

# tkinterdnd2 adds its methods to child widgets automatically, but the root
# window needs the DnDWrapper mixin.
_DnDBase = TkinterDnD.DnDWrapper if TkinterDnD is not None else object

PREVIEW_CHAR_LIMIT = 300_000          # keep the Text widget responsive on huge outputs
POLL_INTERVAL_MS = 100

STATUS_COLORS = {                      # (light, dark) foreground for queue rows
    Status.SUCCESS: ("#1a7f37", "#4ac26b"),
    Status.WARNING: ("#9a6700", "#d4a72c"),
    Status.FAILED: ("#cf222e", "#ff7b72"),
    Status.SKIPPED: ("#9a6700", "#d4a72c"),
    Status.CANCELLED: ("#6e7781", "#8b949e"),
    Status.CONVERTING: ("#0969da", "#58a6ff"),
}

FILE_DIALOG_TYPES = [
    ("Supported files", " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))),
    ("All files", "*.*"),
]


class App(ctk.CTk, _DnDBase):
    def __init__(self) -> None:
        self.settings = AppSettings.load()
        ctk.set_appearance_mode(self.settings.appearance_mode)
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.dnd_enabled = self._init_dnd()

        self.title(f"{__app_name__} — Convert documents to Markdown")
        self.geometry("1280x800")
        self.minsize(1000, 640)
        self._set_icon()

        # Queue state. Treeview row ids are the resolved source paths.
        self.items: dict[str, SourceItem] = {}
        self.results: dict[str, ConversionResult] = {}
        self.worker: ConversionWorker | None = None
        self.last_output_dir: Path | None = None
        self.last_report: Path | None = None
        self.last_finished: BatchFinished | None = None
        self._job_ids: list[str] = []
        self._preview_iid: str | None = None

        self.grid_columnconfigure(0, weight=5, uniform="cols")
        self.grid_columnconfigure(1, weight=6, uniform="cols")
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_input_panel()
        self._build_side_tabs()
        self._build_action_bar()
        self._style_treeview()
        self._refresh_queue_summary()
        self._refresh_network_badge()
        self._show_preview(None)
        self._register_drop_targets(self)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log(f"{__app_name__} {__version__} ready.")
        if not self.dnd_enabled:
            self._log("Drag and drop is unavailable on this system; use the Add buttons instead.")

    # ------------------------------------------------------------------ #
    # Setup helpers
    # ------------------------------------------------------------------ #
    def _init_dnd(self) -> bool:
        if TkinterDnD is None:
            return False
        try:
            TkinterDnD._require(self)  # loads the tkdnd Tcl extension into this interpreter
            return True
        except Exception as exc:  # noqa: BLE001 - e.g. missing native library
            log.warning("Drag and drop disabled: %s", exc)
            return False

    def _set_icon(self) -> None:
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            try:
                self.iconbitmap(default=str(icon))
            except tk.TclError:  # not supported on some Linux window managers
                pass

    def _register_drop_targets(self, widget: tk.Misc) -> None:
        """Accept dropped files on ``widget`` and every widget inside it.

        CustomTkinter widgets are built from nested canvases and labels, and tkdnd
        only delivers a drop to the exact widget under the cursor, so the whole
        tree is registered. Files can therefore be dropped anywhere in the window.
        """
        if not self.dnd_enabled:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                self._register_drop_targets(child)

    # ------------------------------------------------------------------ #
    # Header
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray14"))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text=__app_name__, font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, padx=(20, 10), pady=(12, 0), sticky="w"
        )
        ctk.CTkLabel(
            header,
            text="Turn PDFs, Word, PowerPoint, Excel, web pages and more into Markdown.",
            text_color=("gray35", "gray65"),
        ).grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="w")

        self.network_badge = ctk.CTkLabel(header, text="", corner_radius=8, padx=10)
        self.network_badge.grid(row=0, column=2, rowspan=2, padx=10)

        self.appearance_menu = ctk.CTkOptionMenu(
            header, values=["System", "Light", "Dark"], width=110, command=self._on_appearance_change
        )
        self.appearance_menu.set(self.settings.appearance_mode)
        self.appearance_menu.grid(row=0, column=3, rowspan=2, padx=5)

        self.settings_button = ctk.CTkButton(header, text="Settings", width=100, command=self._open_settings)
        self.settings_button.grid(row=0, column=4, rowspan=2, padx=(5, 20))

    # ------------------------------------------------------------------ #
    # Left panel: inputs, queue and output options
    # ------------------------------------------------------------------ #
    def _build_input_panel(self) -> None:
        panel = ctk.CTkFrame(self, fg_color="transparent")
        panel.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(12, 0))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        # --- Drop zone ---------------------------------------------------
        drop = ctk.CTkFrame(panel, border_width=2, border_color=("#8cb4e8", "#3b6aa5"), corner_radius=12)
        drop.grid(row=0, column=0, sticky="ew")
        drop.grid_columnconfigure(0, weight=1)
        drop_text = (
            "Drag and drop files or folders here" if self.dnd_enabled else "Add the files or folders to convert"
        )
        self.drop_label = ctk.CTkLabel(drop, text=drop_text, font=ctk.CTkFont(size=16, weight="bold"))
        self.drop_label.grid(row=0, column=0, columnspan=2, pady=(16, 2))
        ctk.CTkLabel(
            drop,
            text="Folders keep their sub-folder structure in the output.",
            text_color=("gray40", "gray60"),
        ).grid(row=1, column=0, columnspan=2, pady=(0, 8))

        buttons = ctk.CTkFrame(drop, fg_color="transparent")
        buttons.grid(row=2, column=0, pady=(0, 16))
        self.add_files_button = ctk.CTkButton(buttons, text="Add Files…", width=140, command=self._add_files_dialog)
        self.add_files_button.pack(side="left", padx=6)
        self.add_folder_button = ctk.CTkButton(
            buttons, text="Select Folder…", width=140, command=self._add_folder_dialog
        )
        self.add_folder_button.pack(side="left", padx=6)

        # --- Queue -------------------------------------------------------
        queue_frame = ctk.CTkFrame(panel)
        queue_frame.grid(row=1, column=0, sticky="nsew", pady=12)
        queue_frame.grid_columnconfigure(0, weight=1)
        queue_frame.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(queue_frame, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 4))
        top.grid_columnconfigure(0, weight=1)
        self.queue_label = ctk.CTkLabel(top, text="", font=ctk.CTkFont(weight="bold"), anchor="w")
        self.queue_label.grid(row=0, column=0, sticky="w")
        self.remove_button = ctk.CTkButton(
            top, text="Remove Selected", width=130, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self._remove_selected,
        )
        self.remove_button.grid(row=0, column=1, padx=4)
        self.clear_button = ctk.CTkButton(
            top, text="Clear List", width=90, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self._clear_queue,
        )
        self.clear_button.grid(row=0, column=2)

        columns = ("type", "size", "status")
        self.tree = ttk.Treeview(queue_frame, columns=columns, selectmode="extended", style="Queue.Treeview")
        self.tree.heading("#0", text="File", anchor="w")
        self.tree.heading("type", text="Type", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.heading("status", text="Status", anchor="w")
        self.tree.column("#0", width=280, stretch=True)
        self.tree.column("type", width=60, stretch=False)
        self.tree.column("size", width=80, stretch=False, anchor="e")
        self.tree.column("status", width=90, stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        scrollbar = ctk.CTkScrollbar(queue_frame, command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 6), pady=(0, 10))
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda _e: self._open_converted_file())
        self.tree.bind("<Delete>", lambda _e: self._remove_selected())

        # --- Output options ---------------------------------------------
        out = ctk.CTkFrame(panel)
        out.grid(row=2, column=0, sticky="ew")
        out.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out, text="Save to:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(12, 6), pady=(10, 4), sticky="w"
        )
        self.destination_var = tk.StringVar(value=str(self.settings.destination_path))
        self.destination_entry = ctk.CTkEntry(out, textvariable=self.destination_var, state="readonly")
        self.destination_entry.grid(row=0, column=1, sticky="ew", pady=(10, 4))
        self.destination_button = ctk.CTkButton(out, text="Change…", width=90, command=self._choose_destination)
        self.destination_button.grid(row=0, column=2, padx=12, pady=(10, 4))

        self.timestamp_var = tk.BooleanVar(value=self.settings.create_timestamped_subfolder)
        self.lock_var = tk.BooleanVar(value=self.settings.lock_destination)
        self.overwrite_var = tk.BooleanVar(value=self.settings.overwrite_existing)
        options = [
            (self.timestamp_var, "Put each batch in a new “Converted_Markdown_[date-time]” folder"),
            (self.lock_var, "Remember this location next time"),
            (self.overwrite_var, "Overwrite existing Markdown files with the same name"),
        ]
        self.option_checkboxes = []
        for row, (var, text) in enumerate(options, start=1):
            box = ctk.CTkCheckBox(out, text=text, variable=var, command=self._save_output_options)
            box.grid(row=row, column=0, columnspan=3, sticky="w", padx=12, pady=(2, 10 if row == 3 else 2))
            self.option_checkboxes.append(box)

    # ------------------------------------------------------------------ #
    # Right panel: Preview / Report / Log
    # ------------------------------------------------------------------ #
    def _build_side_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 0))
        preview = self.tabs.add("Preview")
        report = self.tabs.add("Conversion Report")
        logs = self.tabs.add("Log")

        # --- Preview -----------------------------------------------------
        preview.grid_columnconfigure(0, weight=1)
        preview.grid_rowconfigure(1, weight=1)

        details = ctk.CTkFrame(preview)
        details.grid(row=0, column=0, sticky="ew")
        details.grid_columnconfigure(1, weight=1)
        self.detail_values: dict[str, ctk.CTkLabel] = {}
        fields = ["File", "Folder", "Type / Size", "Modified", "Status", "Output", "Result"]
        for row, name in enumerate(fields):
            ctk.CTkLabel(details, text=f"{name}:", text_color=("gray35", "gray65"), anchor="e").grid(
                row=row, column=0, sticky="e", padx=(10, 8), pady=1
            )
            value = ctk.CTkLabel(details, text="", anchor="w", justify="left", wraplength=480)
            value.grid(row=row, column=1, sticky="w", padx=(0, 10), pady=1)
            self.detail_values[name] = value

        self.preview_text = ctk.CTkTextbox(
            preview, wrap="word", font=ctk.CTkFont(family="Consolas", size=13), state="disabled"
        )
        self.preview_text.grid(row=1, column=0, sticky="nsew", pady=8)

        actions = ctk.CTkFrame(preview, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew")
        self.open_file_button = ctk.CTkButton(actions, text="Open Converted File", command=self._open_converted_file)
        self.open_file_button.pack(side="left", padx=(0, 6))
        self.show_file_button = ctk.CTkButton(actions, text="Show in Folder", command=self._show_in_folder)
        self.show_file_button.pack(side="left", padx=6)
        self.copy_button = ctk.CTkButton(actions, text="Copy Markdown", command=self._copy_markdown)
        self.copy_button.pack(side="left", padx=6)

        # --- Report ------------------------------------------------------
        report.grid_columnconfigure(0, weight=1)
        report.grid_rowconfigure(1, weight=1)
        self.summary_label = ctk.CTkLabel(
            report, text="No conversions yet.", font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        )
        self.summary_label.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        self.report_text = ctk.CTkTextbox(report, wrap="none", font=ctk.CTkFont(family="Consolas", size=12))
        self.report_text.grid(row=1, column=0, sticky="nsew", pady=8)
        self.report_text.configure(state="disabled")
        self.open_report_button = ctk.CTkButton(
            report, text="Open Report File", command=lambda: self._safe_open(self.last_report)
        )
        self.open_report_button.grid(row=2, column=0, sticky="w")

        # --- Log ---------------------------------------------------------
        logs.grid_columnconfigure(0, weight=1)
        logs.grid_rowconfigure(0, weight=1)
        self.log_text = ctk.CTkTextbox(logs, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Bottom action bar
    # ------------------------------------------------------------------ #
    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray14"))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        bar.grid_columnconfigure(2, weight=1)

        self.convert_button = ctk.CTkButton(
            bar, text="Convert to Markdown", height=42, width=200,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._start_conversion,
        )
        self.convert_button.grid(row=0, column=0, rowspan=2, padx=(16, 8), pady=12)
        self.cancel_button = ctk.CTkButton(
            bar, text="Cancel", height=42, width=90, state="disabled",
            fg_color=("#cf222e", "#a40e26"), hover_color=("#a40e26", "#82071e"), command=self._cancel_conversion,
        )
        self.cancel_button.grid(row=0, column=1, rowspan=2, padx=8, pady=12)

        self.status_label = ctk.CTkLabel(bar, text="Add some files to get started.", anchor="w")
        self.status_label.grid(row=0, column=2, sticky="ew", padx=8, pady=(12, 0))
        self.progress = ctk.CTkProgressBar(bar)
        self.progress.grid(row=1, column=2, sticky="ew", padx=8, pady=(4, 12))
        self.progress.set(0)

        self.open_output_button = ctk.CTkButton(
            bar, text="Open Output Folder", height=42, width=170, state="disabled",
            command=lambda: self._safe_open(self.last_output_dir),
        )
        self.open_output_button.grid(row=0, column=3, rowspan=2, padx=(8, 16), pady=12)

    # ------------------------------------------------------------------ #
    # Treeview theming (ttk widgets do not follow CustomTkinter themes)
    # ------------------------------------------------------------------ #
    def _is_dark(self) -> bool:
        return ctk.get_appearance_mode() == "Dark"

    def _style_treeview(self) -> None:
        dark = self._is_dark()
        bg, fg, head_bg, sel = (
            ("#1f1f1f", "#e6e6e6", "#2b2b2b", "#1f538d") if dark else ("#ffffff", "#1f1f1f", "#e9e9e9", "#3b8ed0")
        )
        try:
            scale = self._get_widget_scaling()
        except AttributeError:
            scale = 1.0
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Queue.Treeview", background=bg, fieldbackground=bg, foreground=fg,
            rowheight=int(26 * scale), borderwidth=0, font=("Segoe UI", 10),
        )
        style.configure(
            "Queue.Treeview.Heading", background=head_bg, foreground=fg, relief="flat", font=("Segoe UI", 10, "bold")
        )
        style.map("Queue.Treeview", background=[("selected", sel)], foreground=[("selected", "#ffffff")])
        style.map("Queue.Treeview.Heading", background=[("active", head_bg)])
        for status, (light, dark_color) in STATUS_COLORS.items():
            self.tree.tag_configure(status.name, foreground=dark_color if dark else light)

    def _on_appearance_change(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        self.settings.appearance_mode = mode
        self.settings.save()
        # Give CustomTkinter a moment to resolve "System" before restyling.
        self.after(50, self._style_treeview)

    # ------------------------------------------------------------------ #
    # Adding / removing files
    # ------------------------------------------------------------------ #
    def _add_files_dialog(self) -> None:
        paths = filedialog.askopenfilenames(title="Choose files to convert", filetypes=FILE_DIALOG_TYPES)
        if paths:
            self._add_paths(paths)

    def _add_folder_dialog(self) -> None:
        path = filedialog.askdirectory(title="Choose a folder to convert", mustexist=True)
        if path:
            self._add_paths([path])

    def _on_drop(self, event) -> str:
        self._add_paths(self.tk.splitlist(event.data))
        return event.action

    def _add_paths(self, paths) -> None:
        if self._busy():
            return
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            found = discover_files(paths)
        finally:
            self.configure(cursor="")

        added = 0
        for item in found:
            iid = str(item.path)
            if iid in self.items:
                continue
            self.items[iid] = item
            try:
                stat = item.path.stat()
                size = human_size(stat.st_size)
            except OSError:
                size = "?"
            ext = item.path.suffix.lstrip(".").upper() or "—"
            self.tree.insert("", "end", iid=iid, text=item.display_name, values=(ext, size, Status.PENDING.value))
            added += 1

        skipped = len(found) - added
        msg = f"Added {added} file(s)."
        if skipped:
            msg += f" {skipped} already in the list."
        if not found:
            msg = "No supported files were found in what you added."
        self._log(msg)
        self.status_label.configure(text=msg)
        self._refresh_queue_summary()

    def _remove_selected(self) -> None:
        if self._busy():
            return
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.items.pop(iid, None)
            self.results.pop(iid, None)
        self._refresh_queue_summary()
        self._show_preview(None)

    def _clear_queue(self) -> None:
        if self._busy() or not self.items:
            return
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.results.clear()
        self._refresh_queue_summary()
        self._show_preview(None)
        self.progress.set(0)
        self.status_label.configure(text="List cleared.")

    def _refresh_queue_summary(self) -> None:
        n = len(self.items)
        self.queue_label.configure(text=f"Files to convert ({n})" if n else "No files added yet")
        idle = not self._busy()
        self.convert_button.configure(state="normal" if n and idle else "disabled")

    # ------------------------------------------------------------------ #
    # Output options
    # ------------------------------------------------------------------ #
    def _choose_destination(self) -> None:
        path = filedialog.askdirectory(
            title="Choose where to save the Markdown files", initialdir=self.destination_var.get()
        )
        if path:
            self.destination_var.set(str(Path(path)))
            self._save_output_options()

    def _save_output_options(self) -> None:
        self.settings.destination = self.destination_var.get()
        self.settings.create_timestamped_subfolder = self.timestamp_var.get()
        self.settings.lock_destination = self.lock_var.get()
        self.settings.overwrite_existing = self.overwrite_var.get()
        self.settings.save()

    def _refresh_network_badge(self) -> None:
        s = self.settings
        if s.uses_network:
            parts = []
            if s.llm_enabled:
                parts.append(f"AI model: {s.llm_model}")
            if s.allow_online_audio:
                parts.append("audio transcription")
            text, colors = "Online: " + ", ".join(parts), (("#fff1c2", "#4d3800"), ("#6b4c00", "#f0c75e"))
        else:
            text, colors = "Offline mode — files stay on this computer", (("#dafbe1", "#0f3d1f"), ("#1a7f37", "#4ac26b"))
        self.network_badge.configure(text=text, fg_color=colors[0], text_color=colors[1])

    # ------------------------------------------------------------------ #
    # Conversion lifecycle
    # ------------------------------------------------------------------ #
    def _busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (
            self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button,
            self.destination_button, self.settings_button, self.convert_button, *self.option_checkboxes,
        ):
            widget.configure(state=state)
        self.cancel_button.configure(state="disabled" if enabled else "normal")

    def _start_conversion(self) -> None:
        if self._busy() or not self.items:
            return
        self._save_output_options()

        if self.settings.llm_enabled and not self.settings.effective_api_key:
            messagebox.showwarning(
                __app_name__, "An AI model is enabled but no API key is set.\n\nOpen Settings to add one or turn it off."
            )
            return

        try:
            output_dir = prepare_output_dir(
                Path(self.destination_var.get()), self.settings.create_timestamped_subfolder
            )
        except OSError as exc:
            messagebox.showerror(__app_name__, f"Could not create the output folder:\n\n{exc}")
            return

        order = list(self.tree.get_children())
        try:
            plan = plan_output_paths((self.items[i] for i in order), output_dir, self.settings.overwrite_existing)
        except PathEscapeError as exc:
            log.error("Blocked unsafe output path: %s", exc)
            messagebox.showerror(__app_name__, f"A file would be written outside the output folder:\n\n{exc}")
            return
        jobs = [(self.items[i], plan[self.items[i]]) for i in order]
        self._job_ids = order

        self.results.clear()
        for iid in order:
            self._set_row_status(iid, Status.PENDING)
        self.last_output_dir = output_dir
        self.progress.set(0)
        self._set_controls_enabled(False)
        self._log(f"Starting batch of {len(jobs)} file(s) → {output_dir}")

        self.worker = ConversionWorker(jobs, output_dir, self.settings)
        self.worker.start()
        self.after(POLL_INTERVAL_MS, self._poll_worker)

    def _cancel_conversion(self) -> None:
        if self._busy():
            self.worker.cancel()
            self.cancel_button.configure(state="disabled")
            self.status_label.configure(text="Cancelling after the current file finishes…")
            self._log("Cancellation requested.")

    def _poll_worker(self) -> None:
        worker = self.worker
        if worker is None:
            return
        # Drain a bounded number of events per tick so the UI stays responsive.
        for _ in range(200):
            try:
                event = worker.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
            if isinstance(event, BatchFinished):
                return
        self.after(POLL_INTERVAL_MS, self._poll_worker)

    def _handle_event(self, event) -> None:
        if isinstance(event, BatchStarted):
            self.status_label.configure(text=f"Preparing converter for {event.total} file(s)…")

        elif isinstance(event, FileStarted):
            iid = self._job_ids[event.index]
            self._set_row_status(iid, Status.CONVERTING)
            self.tree.see(iid)
            total = len(self._job_ids)
            self.status_label.configure(text=f"Converting {event.index + 1} of {total}: {event.item.path.name}")

        elif isinstance(event, FileFinished):
            iid = self._job_ids[event.index]
            result = event.result
            self.results[iid] = result
            self._set_row_status(iid, result.status)
            self.progress.set((event.index + 1) / len(self._job_ids))
            if result.status is not Status.SUCCESS:
                self._log(f"{result.status.value}: {result.item.path.name} — {result.message}")
            # Refresh the preview if the user is looking at this file.
            if self._preview_iid == iid:
                self._show_preview(iid)

        elif isinstance(event, BatchFinished):
            self._on_batch_finished(event)

    def _on_batch_finished(self, event: BatchFinished) -> None:
        self.worker = None
        self._set_controls_enabled(True)
        self._refresh_queue_summary()

        if event.error:
            self.status_label.configure(text="Conversion could not start.")
            self._log(f"Error: {event.error}")
            messagebox.showerror(__app_name__, f"Conversion could not start:\n\n{event.error}")
            return

        self.last_finished = event
        self.last_report = event.report_path
        self.open_output_button.configure(state="normal")
        counts = summarize(event.results)
        empty = counts[Status.WARNING]
        problems = counts[Status.FAILED] + counts[Status.SKIPPED]
        verb = "Cancelled" if event.cancelled else "Finished"
        summary = f"{verb}: {counts[Status.SUCCESS]} of {len(event.results)} converted"
        if empty:
            summary += f", {empty} with no text"
        if problems:
            summary += f", {problems} could not be converted"
        summary += f" ({event.elapsed:.1f} s)."
        problems += empty
        self.status_label.configure(text=summary)
        self._log(summary)

        self.summary_label.configure(text=summary)
        self._set_text(self.report_text, format_report(event.results, event.output_dir, event.elapsed))
        if problems:
            self.tabs.set("Conversion Report")

        # Show the first successfully converted file, which is what users want to check.
        first_ok = next((iid for iid in self._job_ids if self.results.get(iid, None) and
                         self.results[iid].status is Status.SUCCESS), None)
        if first_ok and not self.tree.selection():
            self.tree.selection_set(first_ok)
            self.tree.see(first_ok)

    def _set_row_status(self, iid: str, status: Status) -> None:
        if self.tree.exists(iid):
            self.tree.set(iid, "status", status.value)
            self.tree.item(iid, tags=(status.name,))

    # ------------------------------------------------------------------ #
    # Preview pane
    # ------------------------------------------------------------------ #
    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        self._show_preview(selection[0] if selection else None)

    def _show_preview(self, iid: str | None) -> None:
        self._preview_iid = iid
        item = self.items.get(iid) if iid else None
        result = self.results.get(iid) if iid else None

        if item is None:
            for label in self.detail_values.values():
                label.configure(text="—")
            self._set_text(self.preview_text, "Select a file in the list to see its details and Markdown preview.")
            self._update_preview_buttons(None)
            return

        try:
            stat = item.path.stat()
            size, modified = human_size(stat.st_size), datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            size, modified = "?", "?"
        v = self.detail_values
        v["File"].configure(text=item.path.name)
        v["Folder"].configure(text=str(item.path.parent))
        v["Type / Size"].configure(text=f"{item.path.suffix.upper().lstrip('.') or '—'}  ·  {size}")
        v["Modified"].configure(text=modified)
        v["Status"].configure(text=result.status.value if result else Status.PENDING.value)
        v["Output"].configure(text=str(result.output_path) if result and result.output_path else "—")
        if result and result.status is Status.SUCCESS:
            v["Result"].configure(text=f"{result.char_count:,} characters in {result.duration:.2f} s")
        else:
            v["Result"].configure(text=result.message if result and result.message else "—")

        if result and result.output_path and result.output_path.exists():
            try:
                with result.output_path.open(encoding="utf-8") as fh:
                    text = fh.read(PREVIEW_CHAR_LIMIT + 1)
                if len(text) > PREVIEW_CHAR_LIMIT:
                    text = text[:PREVIEW_CHAR_LIMIT] + "\n\n… preview truncated — open the file to see everything."
            except OSError as exc:
                text = f"Could not read the converted file: {exc}"
        elif result:
            text = f"No Markdown was created for this file.\n\n{result.message}"
        else:
            text = "Not converted yet. Click “Convert to Markdown” to create the Markdown file."
        self._set_text(self.preview_text, text)
        self._update_preview_buttons(result)

    def _update_preview_buttons(self, result: ConversionResult | None) -> None:
        has_output = bool(result and result.output_path and result.output_path.exists())
        state = "normal" if has_output else "disabled"
        for button in (self.open_file_button, self.show_file_button, self.copy_button):
            button.configure(state=state)

    def _current_output(self) -> Path | None:
        result = self.results.get(self._preview_iid) if self._preview_iid else None
        return result.output_path if result and result.output_path else None

    def _open_converted_file(self) -> None:
        self._safe_open(self._current_output())

    def _show_in_folder(self) -> None:
        path = self._current_output()
        if path and path.exists():
            try:
                reveal_in_file_manager(path)
            except (OSError, UnsafePathError) as exc:
                messagebox.showerror(__app_name__, f"Could not show the file:\n\n{exc}")

    def _copy_markdown(self) -> None:
        path = self._current_output()
        if not path:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(__app_name__, f"Could not read the file:\n\n{exc}")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_label.configure(text=f"Copied Markdown from {path.name} to the clipboard.")

    # ------------------------------------------------------------------ #
    # Settings dialog
    # ------------------------------------------------------------------ #
    def _open_settings(self) -> None:
        SettingsDialog(self, self.settings, on_save=self._on_settings_saved)

    def _on_settings_saved(self) -> None:
        self.settings.save()
        self._refresh_network_badge()
        self._log("Settings saved. " + ("Online features enabled." if self.settings.uses_network else "Offline mode."))

    # ------------------------------------------------------------------ #
    # Misc helpers
    # ------------------------------------------------------------------ #
    def _safe_open(self, path: Path | None) -> None:
        if not path:
            return
        try:
            open_path(path)
        except (OSError, UnsafePathError) as exc:
            messagebox.showerror(__app_name__, f"Could not open:\n{path}\n\n{exc}")

    @staticmethod
    def _set_text(box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _log(self, message: str) -> None:
        log.info(message)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        if self._busy():
            if not messagebox.askyesno(__app_name__, "A conversion is still running. Stop it and quit?"):
                return
            self.worker.cancel()
        self._save_output_options()
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    """Modal dialog for the optional online features."""

    def __init__(self, master: App, settings: AppSettings, on_save) -> None:
        super().__init__(master)
        self.settings = settings
        self.on_save = on_save
        self.title("Settings")
        self.geometry("560x560")
        self.resizable(False, False)
        self.transient(master)
        self.grid_columnconfigure(1, weight=1)

        row = 0

        def section(title: str, note: str) -> None:
            nonlocal row
            ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=16, weight="bold")).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(18, 0)
            )
            ctk.CTkLabel(self, text=note, wraplength=510, justify="left", text_color=("gray35", "gray65")).grid(
                row=row + 1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 8)
            )
            row += 2

        def entry(label: str, value: str, placeholder: str = "", secret: bool = False) -> ctk.CTkEntry:
            nonlocal row
            ctk.CTkLabel(self, text=label).grid(row=row, column=0, sticky="w", padx=(20, 10), pady=4)
            widget = ctk.CTkEntry(self, placeholder_text=placeholder, show="•" if secret else "")
            if value:
                widget.insert(0, value)
            widget.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=4)
            row += 1
            return widget

        section(
            "AI vision model (optional, online)",
            "By default everything is converted on this computer. Turn this on to have an "
            "OpenAI-compatible model describe images and the pictures inside documents. "
            "Files you convert are then sent to that service.",
        )
        self.llm_var = tk.BooleanVar(value=settings.llm_enabled)
        ctk.CTkSwitch(self, text="Use an AI model for images", variable=self.llm_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=20, pady=4
        )
        row += 1
        self.base_url = entry("API endpoint", settings.llm_base_url, "https://api.openai.com/v1 (default)")
        self.api_key = entry("API key", settings.llm_api_key, "Uses OPENAI_API_KEY if left blank", secret=True)
        self.model = entry("Model", settings.llm_model, "e.g. gpt-4o-mini")
        self.prompt = entry("Custom prompt", settings.llm_prompt, "Optional")
        ctk.CTkLabel(
            self, text="The API key is stored encrypted in Windows Credential Manager.",
            text_color=("gray40", "gray60"), font=ctk.CTkFont(size=11),
        ).grid(row=row, column=1, sticky="w", pady=(0, 4))
        row += 1

        section(
            "Audio transcription (optional, online)",
            "MarkItDown transcribes speech in audio files (.mp3, .wav, .m4a, .mp4) using Google's "
            "free web speech service. Audio files are skipped unless you allow this.",
        )
        self.audio_var = tk.BooleanVar(value=settings.allow_online_audio)
        ctk.CTkSwitch(self, text="Allow online audio transcription", variable=self.audio_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=20, pady=4
        )
        row += 1

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", padx=20, pady=20)
        self.grid_rowconfigure(row, weight=1)
        ctk.CTkButton(
            buttons, text="Cancel", width=100, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.destroy,
        ).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Save", width=100, command=self._save).pack(side="left")

        # CTkToplevel needs a short delay on Windows before it can grab focus.
        self.after(150, self._make_modal)

    def _make_modal(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def _save(self) -> None:
        # Validate everything first so an invalid form never half-applies.
        enabled = self.llm_var.get()
        base_url = self.base_url.get().strip()
        api_key = self.api_key.get().strip()
        model = self.model.get().strip()
        endpoint_error = validate_llm_endpoint(base_url)
        if endpoint_error:
            messagebox.showwarning("Settings", endpoint_error, parent=self)
            return
        if enabled and not model:
            messagebox.showwarning("Settings", "Please enter a model name, or turn the AI model off.", parent=self)
            return
        if len(api_key) > 512 or any(ch.isspace() for ch in api_key):
            messagebox.showwarning("Settings", "The API key looks invalid (it contains spaces or is too long).", parent=self)
            return

        s = self.settings
        s.llm_enabled = enabled
        s.llm_base_url = base_url
        s.llm_model = model
        s.llm_prompt = self.prompt.get().strip()
        s.allow_online_audio = self.audio_var.get()
        if api_key != s.llm_api_key and not s.set_api_key(api_key):
            messagebox.showwarning(
                "Settings",
                "No secure credential store is available, so the API key will be kept only until you close the app.",
                parent=self,
            )
        self.on_save()
        self.destroy()
