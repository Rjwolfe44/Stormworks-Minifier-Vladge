"""
VladgeMinifier - Main GUI Application

Provides the graphical user interface for the Stormworks Lua minifier utilizing 
CustomTkinter. Features real-time minification, file watching, auto-deployment, 
Discord Rich Presence, and sprite conversion utilities.
"""

from __future__ import annotations
import os
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog
import json
import tkinter as tk
from PIL import Image

import customtkinter as ctk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

from src.gui.watcher import MinifierFileWatcher
from src.gui.discord_rpc import DiscordRPC
from src.gui.editor_install import (
    format_install_success_message,
    install_editor_integration,
    resolve_cli_path,
)

def get_base_path() -> Path:
    """
    Determine the base execution path, ensuring resource resolution works 
    identically whether running from raw Python source or a frozen PyInstaller executable.
    
    Returns:
        Path: The absolute base path to the application root.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent.parent

_HERE = get_base_path()
# Dynamically insert the project root into sys.path to permit absolute imports of internal modules
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(_HERE))

from src.core.minifier import minify, minify_file, CHAR_LIMIT, LEVEL_NAMES, MinifyStats
from src.core.addon_mode import ADDON_CHAR_LIMIT, MC_CHAR_LIMIT
from src.gui import theme as T
from src.version import __version__ as APP_VERSION

# ─── CustomTkinter appearance ─────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

GITHUB_REPO = "rjwolfe44/Stormworks-Minifier-Vladge"
WINDOW_TITLE = f"⚡ VladgeMinifier v{APP_VERSION}"
WINDOW_SIZE  = "980x720"
MIN_SIZE     = (820, 600)


if HAS_DND:
    class _BaseApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class _BaseApp(ctk.CTk):
        pass

class VladgeMinifierApp(_BaseApp):
    def __init__(self):
        super().__init__()

        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_SIZE)
        self.configure(fg_color=T.BG_DARK)

        # Set Window Icon
        icon_path = _HERE / "src" / "assets" / "logo.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # State
        self._current_file: Path | None = None
        self._last_result: str | None = None
        self._last_source: str | None = None
        self._last_stats: MinifyStats | None = None
        self._minify_level = ctk.IntVar(value=3)
        self._auto_copy = ctk.BooleanVar(value=False)
        self._watch_enabled = ctk.BooleanVar(value=False)
        self._obfuscate = ctk.BooleanVar(value=False)
        self._multiline = ctk.BooleanVar(value=False)
        self._inline_functions = ctk.BooleanVar(value=False)
        self._addon_mode = ctk.BooleanVar(value=False)
        self._is_minifying = False
        
        # Subsystems
        self._watcher = MinifierFileWatcher(self._on_watch_trigger)
        self._rpc = DiscordRPC()
        self._rpc.connect()

        # Enable drag-and-drop (Windows)
        self._setup_dnd()

        # Build UI
        self._build_ui()

        # Key bindings
        self.bind("<Control-o>", lambda e: self._browse_file())
        self.bind("<Control-m>", lambda e: self._start_minify())
        self.bind("<Control-c>", lambda e: self._copy_to_clipboard())

        # Check for updates
        self._check_for_updates()

    # ─── Drag-and-drop ────────────────────────────────────────────────────────
    def _setup_dnd(self):
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind('<<Drop>>', self._on_drop)
            except Exception as e:
                print(f"DnD registration failed: {e}")

    def _on_drop(self, event):
        path_str = event.data
        if path_str.startswith('{') and path_str.endswith('}'):
            path_str = path_str[1:-1]
        path = Path(path_str).resolve()
        if path.is_file() and path.suffix.lower() == '.lua':
            self._load_file(path)
            self._start_minify()
        else:
            self._show_error("Please drop a valid .lua file.")

    # ─── UI Construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header bar ────────────────────────────────────────────────────────
        self._build_header()

        # ── File + controls panel ─────────────────────────────────────────────
        self._build_controls()

        # ── Results panel ─────────────────────────────────────────────────────
        self._build_results()

        # ── Bottom action bar ─────────────────────────────────────────────────
        self._build_actions()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=T.BG_MID, corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        # Logo
        logo_img = None
        logo_path = _HERE / "src" / "assets" / "logo.png"
        if logo_path.exists():
            try:
                logo_img = ctk.CTkImage(
                    light_image=Image.open(logo_path),
                    dark_image=Image.open(logo_path),
                    size=(28, 28)
                )
            except Exception:
                pass

        logo_lbl = ctk.CTkLabel(
            header,
            text=" VladgeMinifier",
            image=logo_img,
            compound="left",
            font=T.FONT_TITLE,
            text_color=T.ACCENT,
        )
        logo_lbl.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        # Subtitle
        sub_lbl = ctk.CTkLabel(
            header,
            text="Stormworks Lua Minifier",
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
        )
        sub_lbl.grid(row=0, column=1, padx=0, pady=10, sticky="w")

        # Obfuscate toggle
        obfuscate_cb = ctk.CTkCheckBox(
            header,
            text="Obfuscate",
            variable=self._obfuscate,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.RED,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        obfuscate_cb.grid(row=0, column=2, padx=(20, 10), pady=10, sticky="e")

        multiline_cb = ctk.CTkCheckBox(
            header,
            text="Keep line breaks",
            variable=self._multiline,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        multiline_cb.grid(row=0, column=3, padx=(10, 10), pady=10, sticky="e")

        inline_cb = ctk.CTkCheckBox(
            header,
            text="Inline funcs",
            variable=self._inline_functions,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        inline_cb.grid(row=0, column=4, padx=(10, 10), pady=10, sticky="e")

        addon_cb = ctk.CTkCheckBox(
            header,
            text="Addon / mission (131071)",
            variable=self._addon_mode,
            command=self._on_addon_toggle,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        addon_cb.grid(row=0, column=5, padx=(10, 10), pady=10, sticky="e")

        # Drop Locals toggle (V3 feature)
        self._drop_locals = ctk.BooleanVar(value=False)
        drop_locals_cb = ctk.CTkCheckBox(
            header,
            text="Drop Locals",
            variable=self._drop_locals,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.AMBER,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        drop_locals_cb.grid(row=0, column=6, padx=(10, 10), pady=10, sticky="e")

        # Auto-copy toggle
        auto_copy_cb = ctk.CTkCheckBox(
            header,
            text="Auto-copy",
            variable=self._auto_copy,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        auto_copy_cb.grid(row=0, column=7, padx=(10, 10), pady=10, sticky="e")
        
        # Watch Mode toggle
        watch_cb = ctk.CTkCheckBox(
            header,
            text="Watch File (Auto-Minify on Save)",
            variable=self._watch_enabled,
            command=self._on_watch_toggle,
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            fg_color=T.AMBER,
            hover_color=T.ACCENT_DIM,
            border_color=T.BORDER,
        )
        watch_cb.grid(row=0, column=8, padx=(10, 20), pady=10, sticky="e")

    def _build_controls(self):
        ctrl_frame = ctk.CTkFrame(self, fg_color=T.BG_MID, corner_radius=0)
        ctrl_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=(1, 0))
        ctrl_frame.grid_columnconfigure(1, weight=1)

        inner = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        inner.grid(row=0, column=0, columnspan=3, padx=20, pady=14, sticky="ew")
        inner.grid_columnconfigure(1, weight=1)

        # ── File picker row ───────────────────────────────────────────────────
        browse_btn = ctk.CTkButton(
            inner,
            text="📂 Open File",
            width=120,
            height=36,
            fg_color=T.BG_PANEL,
            hover_color=T.BG_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.TEXT_PRIMARY,
            font=T.FONT_BODY,
            command=self._browse_file,
        )
        browse_btn.grid(row=0, column=0, padx=(0, 10))

        self._file_label = ctk.CTkLabel(
            inner,
            text="Drop a .lua file here or click Open File…",
            font=T.FONT_BODY,
            text_color=T.TEXT_SECONDARY,
            anchor="w",
        )
        self._file_label.grid(row=0, column=1, sticky="ew", padx=5)

        # ── Level selector row ────────────────────────────────────────────────
        level_frame = ctk.CTkFrame(inner, fg_color="transparent")
        level_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        ctk.CTkLabel(
            level_frame,
            text="Level:",
            font=T.FONT_BODY,
            text_color=T.TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 10))

        level_names = ["1 - Strip Only", "2 - Standard", "3 - Aggressive (Default)", "4 - Ultimate"]
        for i, name in enumerate(level_names, start=1):
            color = T.LEVEL_COLORS.get(i, T.ACCENT)
            rb = ctk.CTkRadioButton(
                level_frame,
                text=name,
                variable=self._minify_level,
                value=i,
                fg_color=color,
                hover_color=color,
                border_color=T.BORDER,
                text_color=T.TEXT_PRIMARY,
                font=T.FONT_BODY,
                command=self._on_level_change,
            )
            rb.pack(side="left", padx=12)

        # ── Deploy row ────────────────────────────────────────────────────────
        deploy_frame = ctk.CTkFrame(inner, fg_color="transparent")
        deploy_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        
        ctk.CTkLabel(deploy_frame, text="Deploy:", font=T.FONT_BODY, text_color=T.TEXT_SECONDARY).pack(side="left", padx=(0, 10))
        self._deploy_entry = ctk.CTkEntry(deploy_frame, placeholder_text="Auto-deploy folder (optional)", font=T.FONT_BODY)
        self._deploy_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(
            deploy_frame, text="Browse", width=60, 
            command=self._browse_deploy_dir,
            fg_color=T.BG_PANEL, hover_color=T.BG_HOVER,
            border_width=1, border_color=T.BORDER,
            text_color=T.TEXT_PRIMARY, font=T.FONT_BODY
        ).pack(side="left")

        # ── Action buttons ────────────────────────────────────────────────────
        button_frame = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        button_frame.grid(row=3, column=0, columnspan=3, padx=20, pady=(8, 14), sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1, uniform="b")
        
        self._verify_btn = ctk.CTkButton(
            button_frame,
            text="🧪 VERIFY CODE",
            height=44,
            fg_color=T.BG_PANEL,
            hover_color=T.BG_HOVER,
            text_color=T.TEXT_PRIMARY,
            border_width=1,
            border_color=T.BORDER,
            font=("Segoe UI", 15, "bold"),
            corner_radius=T.CORNER_RADIUS,
            command=self._start_verify,
        )
        self._verify_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self._minify_btn = ctk.CTkButton(
            button_frame,
            text="⚡ MINIFY",
            height=44,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_DIM,
            text_color=T.BG_DARK,
            font=("Segoe UI", 15, "bold"),
            corner_radius=T.CORNER_RADIUS,
            command=self._start_minify,
        )
        self._minify_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        # ── Progress bar (hidden by default) ─────────────────────────────────
        self._progress = ctk.CTkProgressBar(
            ctrl_frame,
            fg_color=T.BG_PANEL,
            progress_color=T.ACCENT,
            height=3,
        )
        self._progress.grid(row=4, column=0, columnspan=3, padx=20, pady=(0, 2), sticky="ew")
        self._progress.set(0)
        self._progress.grid_remove()

    def _build_results(self):
        results_frame = ctk.CTkFrame(self, fg_color="transparent")
        results_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=10)
        results_frame.grid_columnconfigure(0, weight=0)
        results_frame.grid_columnconfigure(1, weight=1)
        results_frame.grid_rowconfigure(0, weight=1)

        # ── Left: Stats panel ─────────────────────────────────────────────────
        stats_outer = ctk.CTkFrame(results_frame, fg_color=T.BG_PANEL,
                                    corner_radius=T.CORNER_RADIUS, width=230)
        stats_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        stats_outer.grid_propagate(False)

        ctk.CTkLabel(
            stats_outer,
            text="STATISTICS",
            font=("Segoe UI", 10, "bold"),
            text_color=T.TEXT_SECONDARY,
        ).pack(pady=(14, 2), padx=16, anchor="w")

        self._stat_before = self._make_stat_row(stats_outer, "Before", "—", T.TEXT_SECONDARY)
        self._stat_after  = self._make_stat_row(stats_outer, "After",  "—", T.TEXT_PRIMARY)
        self._stat_saved  = self._make_stat_row(stats_outer, "Saved",  "—", T.GREEN)
        self._stat_ratio  = self._make_stat_row(stats_outer, "Ratio",  "—", T.ACCENT)
        self._stat_time   = self._make_stat_row(stats_outer, "Time",   "—", T.TEXT_SECONDARY)

        # Character limit bar
        sep = ctk.CTkFrame(stats_outer, fg_color=T.BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=10)

        self._limit_title = ctk.CTkLabel(
            stats_outer,
            text="8192 CHAR LIMIT",
            font=("Segoe UI", 9, "bold"),
            text_color=T.TEXT_SECONDARY,
        )
        self._limit_title.pack(padx=16, anchor="w")

        self._limit_bar = ctk.CTkProgressBar(
            stats_outer,
            fg_color=T.BG_MID,
            progress_color=T.GREEN,
            height=12,
            corner_radius=4,
        )
        self._limit_bar.pack(padx=16, pady=(4, 0), fill="x")
        self._limit_bar.set(0)

        self._limit_label = ctk.CTkLabel(
            stats_outer,
            text="",
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
        )
        self._limit_label.pack(padx=16, pady=(4, 0), anchor="w")

        # Status badge
        self._status_badge = ctk.CTkLabel(
            stats_outer,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color=T.TEXT_DIM,
        )
        self._status_badge.pack(pady=(8, 14), padx=16, anchor="w")

        # ── Right: What Changed panel ─────────────────────────────────────────
        changes_outer = ctk.CTkFrame(results_frame, fg_color=T.BG_PANEL,
                                      corner_radius=T.CORNER_RADIUS)
        changes_outer.grid(row=0, column=1, sticky="nsew")
        changes_outer.grid_columnconfigure(0, weight=1)
        changes_outer.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            changes_outer,
            text="WHAT WAS CHANGED",
            font=("Segoe UI", 10, "bold"),
            text_color=T.TEXT_SECONDARY,
        ).grid(row=0, column=0, pady=(14, 2), padx=16, sticky="w")

        self._tabs = ctk.CTkTabview(changes_outer, fg_color="transparent")
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        
        self._tab_summary = self._tabs.add("Summary")
        self._tab_code = self._tabs.add("Code View")
        
        self._tab_summary.grid_columnconfigure(0, weight=1)
        self._tab_summary.grid_rowconfigure(0, weight=1)
        
        self._changes_text = ctk.CTkTextbox(
            self._tab_summary,
            fg_color="transparent",
            text_color=T.TEXT_PRIMARY,
            font=T.FONT_MONO,
            border_width=0,
            state="disabled",
        )
        self._changes_text.grid(row=0, column=0, sticky="nsew")

        self._tab_code.grid_columnconfigure((0, 1), weight=1, uniform="group1")
        self._tab_code.grid_rowconfigure(0, weight=1)
        
        self._orig_text = ctk.CTkTextbox(
            self._tab_code,
            fg_color=T.BG_DARK,
            text_color=T.TEXT_SECONDARY,
            font=T.FONT_MONO,
            border_width=1,
            border_color=T.BORDER,
            wrap="char"
        )
        self._orig_text.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        
        self._min_text = ctk.CTkTextbox(
            self._tab_code,
            fg_color=T.BG_DARK,
            text_color=T.TEXT_PRIMARY,
            font=T.FONT_MONO,
            border_width=1,
            border_color=T.BORDER,
            wrap="char"
        )
        self._min_text.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

    def _build_actions(self):
        action_bar = ctk.CTkFrame(self, fg_color=T.BG_MID, corner_radius=0, height=100)
        action_bar.grid(row=3, column=0, sticky="ew")
        action_bar.grid_propagate(False)
        action_bar.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        btn_cfg = dict(
            height=36,
            fg_color=T.BG_PANEL,
            hover_color=T.BG_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.TEXT_PRIMARY,
            font=T.FONT_BODY,
            corner_radius=T.CORNER_RADIUS,
        )

        ctk.CTkButton(
            action_bar, text="📋 Copy to Clipboard",
            command=self._copy_to_clipboard, **btn_cfg,
        ).grid(row=0, column=0, padx=(16, 6), pady=12, sticky="ew")

        ctk.CTkButton(
            action_bar, text="💾 Save to _minified/",
            command=self._save_file, **btn_cfg,
        ).grid(row=0, column=1, padx=6, pady=12, sticky="ew")

        ctk.CTkButton(
            action_bar, text="📁 Batch Folder…",
            command=self._batch_folder, **btn_cfg,
        ).grid(row=0, column=2, padx=6, pady=12, sticky="ew")

        ctk.CTkButton(
            action_bar, text="🔌 Install to Editor",
            command=self._install_to_editor, **btn_cfg,
        ).grid(row=0, column=3, padx=6, pady=(12, 6), sticky="ew")

        ctk.CTkButton(
            action_bar, text="↩ Clear",
            command=self._clear, **btn_cfg,
        ).grid(row=0, column=4, padx=(6, 16), pady=(12, 6), sticky="ew")

        ctk.CTkButton(
            action_bar, text="🎨 Sprite to Lua Converter",
            command=self._open_sprite_converter,
            height=36,
            hover_color=T.ACCENT_DIM,
            border_width=1,
            border_color=T.BORDER,
            font=T.FONT_BODY,
            corner_radius=T.CORNER_RADIUS,
            fg_color=T.ACCENT, text_color=T.BG_DARK,
        ).grid(row=1, column=0, columnspan=5, padx=16, pady=(0, 12), sticky="ew")

    # ─── Helpers ──────────────────────────────────────────────────────────────
    def _make_stat_row(self, parent, label: str, value: str, color: str):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(frame, text=label + ":", font=T.FONT_SMALL,
                     text_color=T.TEXT_SECONDARY, width=55, anchor="w").pack(side="left")
        val_lbl = ctk.CTkLabel(frame, text=value, font=("Segoe UI", 11, "bold"),
                               text_color=color, anchor="w")
        val_lbl.pack(side="left")
        return val_lbl

    def _set_changes_text(self, text: str):
        self._changes_text.configure(state="normal")
        self._changes_text.delete("1.0", "end")
        self._changes_text.insert("end", text)
        self._changes_text.configure(state="disabled")

    def _on_level_change(self):
        pass  # Could auto-re-minify if result exists

    # ─── Actions ──────────────────────────────────────────────────────────────
    def _open_sprite_converter(self):
        from src.gui.sprite_converter import SpriteConverterWindow
        SpriteConverterWindow(self)

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Open Lua File",
            filetypes=[("Lua files", "*.lua"), ("All files", "*.*")],
        )
        if path:
            self._load_file(Path(path))

    def _browse_deploy_dir(self):
        folder = filedialog.askdirectory(title="Select Deploy Directory")
        if folder:
            self._deploy_entry.delete(0, "end")
            self._deploy_entry.insert(0, str(Path(folder)))

    def _load_file(self, path: Path):
        self._current_file = path
        self._file_label.configure(
            text=f"📄 {path.name}  ({path.stat().st_size:,} bytes)  — {path.parent}",
            text_color=T.TEXT_PRIMARY,
        )
        # Re-apply watch mode if it's checked
        self._on_watch_toggle()

    def _on_watch_toggle(self):
        if self._watch_enabled.get() and self._current_file:
            self._watcher.start_watching(self._current_file)
            self._rpc.update("Watching", f"File: {self._current_file.name}")
        else:
            self._watcher.stop_watching()
            if self._current_file:
                self._rpc.update("Loaded", f"File: {self._current_file.name}")
            else:
                self._rpc.update("Idling", "Ready to optimize")

    def _on_addon_toggle(self):
        """Switch limit badge between microcontroller (8192) and addon (131071)."""
        if self._addon_mode.get():
            self._limit_title.configure(text=f"{ADDON_CHAR_LIMIT:,} CHAR LIMIT (ADDON)")
            # Addon scripts are safer at L2 by default (rename locals only).
            if self._minify_level.get() >= 3:
                self._minify_level.set(2)
        else:
            self._limit_title.configure(text=f"{MC_CHAR_LIMIT:,} CHAR LIMIT (MC)")

    def _on_watch_trigger(self):
        # Called from watcher thread, safely schedule minify on main thread
        self.after(0, self._start_minify)

    def _start_verify(self):
        if self._current_file is None:
            self._show_error("No file loaded. Open a .lua file first.")
            return
            
        try:
            source_code = self._current_file.read_text(encoding="utf-8", errors="replace")
            from src.core.linter import lint_script
            errors = lint_script(source_code)
            
            if not errors:
                self._show_toast("Verified! No undefined variables or syntax errors found.")
            else:
                msg = "Verification Failed:\n\n" + "\n".join(errors)
                self._show_error(msg)
                
        except Exception as e:
            self._show_error(f"Linter error:\n{e}")

    def _start_minify(self):
        if self._is_minifying:
            return
        if self._current_file is None:
            self._show_error("No file loaded. Open a .lua file first.")
            return

        self._is_minifying = True
        self._minify_btn.configure(text="⏳ Minifying…", state="disabled")
        self._progress.grid()
        self._progress.start()  # indeterminate animation

        level = self._minify_level.get()
        obfuscate = self._obfuscate.get()

        def _worker():
            try:
                from src.core.minifier import minify
                ml = "statements" if self._multiline.get() else False
                result, stats = minify(
                    self._current_file.read_text(encoding="utf-8", errors="replace"),
                    level=level,
                    root_dir=str(self._current_file.parent),
                    obfuscate=obfuscate,
                    drop_locals=self._drop_locals.get(),
                    multiline=ml,
                    inline_functions=self._inline_functions.get(),
                    addon=self._addon_mode.get(),
                )
                self._last_result = result
                self._last_source = self._current_file.read_text(encoding="utf-8", errors="replace")
                self._last_stats = stats
                
                # Auto-Deploy Logic
                deploy_dir = self._deploy_entry.get().strip()
                if deploy_dir:
                    try:
                        from src.core.deployer import deploy_to_target
                        is_xml = deploy_to_target(result, self._current_file.name, Path(deploy_dir))
                        if is_xml:
                            self._append_log(f"Injected {self._current_file.name} -> XML Microcontroller")
                        else:
                            self._append_log(f"Deployed {self._current_file.name} -> {deploy_dir}")
                    except Exception as e:
                        print(f"Deploy failed: {e}")
                
                self.after(0, lambda: self._on_minify_done(result, stats))
            except Exception as e:
                self.after(0, lambda: self._show_error(f"Minification error:\n{e}"))
                self.after(0, self._reset_btn)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_minify_done(self, result: str, stats: MinifyStats):
        self._progress.stop()
        self._progress.grid_remove()
        self._reset_btn()
        self._is_minifying = False

        # Update stats panel
        self._stat_before.configure(text=f"{stats.original_size:,} chars")
        self._stat_after.configure(text=f"{stats.final_size:,} chars")
        self._stat_saved.configure(text=f"{stats.bytes_saved:,} chars")
        self._stat_ratio.configure(text=f"{stats.ratio:.1f}%")
        self._stat_time.configure(text=f"{stats.elapsed_ms:.1f}ms")

        # Limit bar
        limit = getattr(stats, "char_limit", CHAR_LIMIT) or CHAR_LIMIT
        pct = stats.limit_pct / 100
        bar_color = T.GREEN if pct < 0.70 else T.AMBER if pct < 0.90 else T.RED
        self._limit_bar.configure(progress_color=bar_color)
        self._limit_bar.set(min(pct, 1.0))
        mode_label = "ADDON" if getattr(stats, "mode", "") == "addon" else "MC"
        self._limit_title.configure(text=f"{limit:,} CHAR LIMIT ({mode_label})")
        self._limit_label.configure(
            text=f"{stats.final_size:,} / {limit:,}  ({stats.limit_pct:.1f}%)"
        )

        if not stats.semantic_ok:
            n_err = len(stats.semantic_errors)
            self._status_badge.configure(
                text=f"❌ BROKEN: {n_err} semantic error(s)", text_color=T.RED
            )
        elif stats.under_limit:
            self._status_badge.configure(
                text=f"✅ Under {limit:,} limit", text_color=T.GREEN
            )
        else:
            over = stats.final_size - limit
            self._status_badge.configure(
                text=f"❌ Over by {over:,} chars!", text_color=T.RED
            )

        # Changes panel
        lines = [
            f"Level {stats.level} · {stats.level_name}",
            "─" * 36,
        ] + stats.summary_lines()

        if stats.rename_map:
            lines.append("")
            lines.append("─ Local variable renames ─")
            for orig, new in list(stats.rename_map.items())[:15]:
                lines.append(f"  {orig:25s} → {new}")
            if len(stats.rename_map) > 15:
                lines.append(f"  … and {len(stats.rename_map) - 15} more")

        if stats.global_renames_map:
            lines.append("")
            lines.append("─ Global & property renames ─")
            for orig, new in list(stats.global_renames_map.items())[:15]:
                lines.append(f"  {orig:25s} → {new}")
            if len(stats.global_renames_map) > 15:
                lines.append(f"  … and {len(stats.global_renames_map) - 15} more")

        if stats.globals_alias_map:
            lines.append("")
            lines.append("─ Global aliases ─")
            for orig, alias in stats.globals_alias_map.items():
                lines.append(f"  {orig:30s} → {alias}")

        self._set_changes_text("\n".join(lines))
        
        # Populate code viewer tab
        self._orig_text.configure(state="normal")
        self._orig_text.delete("1.0", "end")
        self._orig_text.insert("end", self._last_source)
        self._orig_text.configure(state="disabled")
        
        self._min_text.configure(state="normal")
        self._min_text.delete("1.0", "end")
        self._min_text.insert("end", result)
        self._min_text.configure(state="disabled")

        # Update Discord RPC
        status = "Watching" if self._watch_enabled.get() else "Minified"
        self._rpc.update(status, f"{self._current_file.name} ({stats.ratio:.1f}% ratio)")

        # Auto-copy if enabled
        if self._auto_copy.get():
            self._copy_to_clipboard(silent=True)

    def _copy_to_clipboard(self, silent: bool = False):
        if self._last_result is None:
            if not silent:
                self._show_error("Nothing to copy yet. Minify a file first.")
            return
        try:
            import pyperclip
            pyperclip.copy(self._last_result)
            if not silent:
                self._minify_btn.configure(text="✓ Copied!", fg_color=T.GREEN)
                self.after(1500, self._reset_btn)
        except ImportError:
            self.clipboard_clear()
            self.clipboard_append(self._last_result)
            if not silent:
                self._minify_btn.configure(text="✓ Copied!", fg_color=T.GREEN)
                self.after(1500, self._reset_btn)

    def _save_file(self):
        if self._last_result is None:
            self._show_error("Nothing to save. Minify a file first.")
            return
        if self._current_file is None:
            return
        out_dir = self._current_file.parent / "_minified"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / self._current_file.name
        out_path.write_text(self._last_result, encoding="utf-8")
        self._show_toast(f"✓ Saved → {out_path}")

    def _batch_folder(self):
        folder = filedialog.askdirectory(title="Select folder to batch minify")
        if not folder:
            return
        folder_path = Path(folder)
        level = self._minify_level.get()

        self._minify_btn.configure(text="⏳ Batch…", state="disabled")
        self._progress.grid()
        self._progress.start()

        def _worker():
            from concurrent.futures import ProcessPoolExecutor, as_completed as asc
            lua_files = [
                f for f in folder_path.rglob("*.lua")
                if "_minified" not in f.parts and "_build" not in f.parts
            ]
            out_dir = folder_path / "_minified"
            out_dir.mkdir(exist_ok=True)

            total_before = 0
            total_after = 0
            for path in lua_files:
                try:
                    result, stats = minify_file(
                        str(path), level, self._obfuscate.get(),
                        addon=self._addon_mode.get(),
                    )
                    rel = path.relative_to(folder_path)
                    out = out_dir / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(result.encode("utf-8"))  # no BOM
                    total_before += stats.original_size
                    total_after += stats.final_size
                except Exception:
                    pass

            saved = total_before - total_after
            ratio = (saved / total_before * 100) if total_before else 0
            msg = (f"Batch done!\n{len(lua_files)} files\n"
                   f"{total_before:,} → {total_after:,} chars\n"
                   f"({ratio:.1f}% reduction)\n→ {out_dir}")
            self.after(0, lambda: self._show_toast(msg))
            self.after(0, self._reset_btn)
            self.after(0, lambda: self._progress.grid_remove())
            self.after(0, lambda: self._progress.stop())

        threading.Thread(target=_worker, daemon=True).start()

    def _install_to_editor(self):
        folder = filedialog.askdirectory(title="Select your Stormworks code folder")
        if not folder:
            return

        folder_path = Path(folder)

        level_win = ctk.CTkToplevel(self)
        level_win.title("Install to Editor")
        level_win.geometry("460x300")
        level_win.configure(fg_color=T.BG_PANEL)
        level_win.transient(self)
        level_win.grab_set()

        ctk.CTkLabel(
            level_win,
            text="Default Ctrl+Alt+M preset (paste to clipboard):",
            font=T.FONT_BODY,
            text_color=T.TEXT_PRIMARY,
        ).pack(pady=(20, 10))

        level_var = ctk.IntVar(value=self._minify_level.get())

        combo = ctk.CTkComboBox(
            level_win,
            values=["1 - Strip Only", "2 - Standard", "3 - Aggressive", "4 - Ultimate"],
            font=T.FONT_BODY,
            width=280,
        )
        combo.set(combo.cget("values")[level_var.get() - 1])
        combo.pack(pady=10)

        ctk.CTkLabel(
            level_win,
            text="Re-run on existing projects to migrate old tasks\n"
                 "and remove broken CLI copies from .vscode/",
            font=T.FONT_SMALL,
            text_color=T.TEXT_SECONDARY,
            justify="center",
        ).pack(pady=(0, 6))

        def _confirm_install():
            try:
                selected_level = int(combo.get().split(" - ")[0])
                cli_path = resolve_cli_path()
                if cli_path is None:
                    self._show_error(
                        "Could not find vladgeminifier-cli.exe.\n\n"
                        "Run VladgeMinifier from the full install folder\n"
                        "(VladgeMinifier.exe + vladgeminifier-cli.exe)."
                    )
                    level_win.destroy()
                    return

                result = install_editor_integration(
                    folder_path, selected_level, cli_path,
                )
                level_win.destroy()
                msg = format_install_success_message(folder_path.name, result)
                self._show_toast(msg, geometry="480x320")

            except Exception as e:
                level_win.destroy()
                self._show_error(f"Failed to install:\n{e}")

        ctk.CTkButton(
            level_win,
            text="Install / Update",
            command=_confirm_install,
            fg_color=T.ACCENT,
            text_color=T.BG_DARK,
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=16)

    def _clear(self):
        self._current_file = None
        self._last_result = None
        self._last_stats = None
        self._file_label.configure(
            text="Drop a .lua file here or click Open File…",
            text_color=T.TEXT_SECONDARY,
        )
        for lbl in (self._stat_before, self._stat_after,
                    self._stat_saved, self._stat_ratio, self._stat_time):
            lbl.configure(text="—")
        self._limit_bar.set(0)
        self._limit_label.configure(text="")
        self._status_badge.configure(text="")
        self._set_changes_text("")
        self._orig_text.configure(state="normal")
        self._orig_text.delete("1.0", "end")
        self._orig_text.configure(state="disabled")
        self._min_text.configure(state="normal")
        self._min_text.delete("1.0", "end")
        self._min_text.configure(state="disabled")
        self._rpc.update("Idling", "Ready to optimize")

    def _reset_btn(self):
        self._minify_btn.configure(
            text="⚡ MINIFY", state="normal", fg_color=T.ACCENT
        )
        self._is_minifying = False

    def _show_error(self, msg: str):
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.geometry("420x160")
        win.configure(fg_color=T.BG_PANEL)
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text="❌ " + msg, font=T.FONT_BODY,
                     text_color=T.RED, wraplength=380).pack(pady=30)
        ctk.CTkButton(win, text="OK", command=win.destroy,
                      fg_color=T.ACCENT, text_color=T.BG_DARK).pack()

    # ─── Auto-Updater ──────────────────────────────────────────────────────────
    def _check_for_updates(self):
        threading.Thread(target=self._update_checker_thread, daemon=True).start()

    def _update_checker_thread(self):
        import urllib.request
        import urllib.error
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'VladgeMinifier-Updater'}
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode('utf-8'))
                tag_name = data.get("tag_name", "")
                latest_ver = tag_name.lstrip("v")
                if latest_ver and self._is_newer_version(APP_VERSION, latest_ver):
                    assets = data.get("assets", [])
                    download_url = None
                    # Zip-only releases (folder install). Never pick standalone .exe.
                    for asset in assets:
                        name = asset.get("name", "").lower()
                        if name.endswith(".zip") and "vladgeminifier" in name:
                            download_url = asset.get("browser_download_url")
                            break
                    if not download_url:
                        for asset in assets:
                            if asset.get("name", "").lower().endswith(".zip"):
                                download_url = asset.get("browser_download_url")
                                break
                    if download_url:
                        self.after(0, lambda: self._prompt_update(latest_ver, download_url))
        except Exception as e:
            print("Update check failed:", e)

    def _is_newer_version(self, current: str, latest: str) -> bool:
        try:
            curr_parts = [int(p) for p in current.split(".")]
            late_parts = [int(p) for p in latest.split(".")]
            return late_parts > curr_parts
        except Exception:
            return latest != current

    def _prompt_update(self, latest_version: str, download_url: str):
        win = ctk.CTkToplevel(self)
        win.title("Update Available")
        win.geometry("450x220")
        win.configure(fg_color=T.BG_PANEL)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(
            win,
            text=f"✨ A new update is available!\n\n"
                 f"Current Version:  {APP_VERSION}\n"
                 f"Latest Version:   {latest_version}",
            font=T.FONT_BODY,
            text_color=T.TEXT_PRIMARY,
            anchor="center",
            justify="center"
        ).pack(pady=(20, 10))

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=15)

        def _on_yes():
            win.destroy()
            self._start_update_download(latest_version, download_url)

        ctk.CTkButton(
            btn_frame, text="Update Now", width=120, height=36,
            fg_color=T.ACCENT, text_color=T.BG_DARK, font=("Segoe UI", 12, "bold"),
            command=_on_yes
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="Later", width=120, height=36,
            fg_color=T.BG_DARK, text_color=T.TEXT_SECONDARY, border_width=1, border_color=T.BORDER,
            command=win.destroy
        ).pack(side="left", padx=10)

    def _start_update_download(self, latest_version: str, download_url: str):
        win = ctk.CTkToplevel(self)
        win.title("Downloading Update")
        win.geometry("400x160")
        win.configure(fg_color=T.BG_PANEL)
        win.transient(self)
        win.grab_set()

        lbl = ctk.CTkLabel(
            win, text="Downloading VladgeMinifier update...",
            font=T.FONT_BODY, text_color=T.TEXT_PRIMARY
        )
        lbl.pack(pady=(25, 10))

        bar = ctk.CTkProgressBar(
            win, fg_color=T.BG_MID, progress_color=T.ACCENT, height=10
        )
        bar.pack(padx=30, fill="x", pady=10)
        bar.set(0)

        def _download_thread():
            try:
                import urllib.request
                temp_dir = Path(os.environ.get("TEMP", "."))
                download_dest = temp_dir / "VladgeMinifier_update.zip"

                req = urllib.request.Request(
                    download_url,
                    headers={'User-Agent': 'VladgeMinifier-Updater'}
                )
                with urllib.request.urlopen(req) as response:
                    total_size = int(response.headers.get('content-length', 0))
                    bytes_read = 0
                    block_size = 8192

                    with open(download_dest, "wb") as f:
                        while True:
                            block = response.read(block_size)
                            if not block:
                                break
                            f.write(block)
                            bytes_read += len(block)
                            if total_size > 0:
                                pct = bytes_read / total_size
                                self.after(0, lambda p=pct: bar.set(p))

                self.after(0, lambda: lbl.configure(text="Installing update..."))
                self.after(500, lambda: self._apply_update_and_restart(download_dest, win))
            except Exception as e:
                self.after(0, lambda: self._show_error(f"Download failed:\n{e}"))
                self.after(0, win.destroy)

        threading.Thread(target=_download_thread, daemon=True).start()

    def _apply_update_and_restart(self, download_path: Path, win_to_close: ctk.CTkToplevel):
        win_to_close.destroy()
        try:
            running_exe = Path(sys.executable)
            is_real_exe = running_exe.name.endswith(".exe") and "python" not in running_exe.name.lower()

            if is_real_exe:
                install_dir = running_exe.parent
                extract_dir = Path(os.environ.get("TEMP", ".")) / "VladgeMinifier_update_extract"
                updater_bat = install_dir / "updater.bat"
                # Flat zip (CI: VladgeMinifier\*) or nested VladgeMinifier\ folder both work.
                script_content = f"""@echo off
setlocal EnableDelayedExpansion
timeout /t 2 /nobreak > nul
if exist "{extract_dir}" rmdir /s /q "{extract_dir}"
mkdir "{extract_dir}"
powershell -NoProfile -Command "Expand-Archive -LiteralPath '{download_path}' -DestinationPath '{extract_dir}' -Force"
set "SRC={extract_dir}"
if exist "{extract_dir}\\VladgeMinifier\\VladgeMinifier.exe" set "SRC={extract_dir}\\VladgeMinifier"
if not exist "!SRC!\\VladgeMinifier.exe" (
  echo Update extract failed: VladgeMinifier.exe not found
  exit /b 1
)
xcopy /s /y /q "!SRC!\\*" "{install_dir}\\"
rmdir /s /q "{extract_dir}"
del /q "{download_path}" > nul 2>&1
start "" "{running_exe}"
del "%~f0"
"""
                updater_bat.write_text(script_content, encoding="utf-8")

                import subprocess
                subprocess.Popen(["cmd.exe", "/c", str(updater_bat)], creationflags=subprocess.CREATE_NO_WINDOW)
                self.destroy()
                sys.exit(0)
            else:
                self._show_toast(
                    f"✓ Update downloaded to:\n{download_path}\n\n"
                    f"Since you are running from source, please extract or run it manually."
                )
        except Exception as e:
            self._show_error(f"Failed to apply update:\n{e}")

    def _show_toast(self, msg: str, geometry: str = None):
        win = ctk.CTkToplevel(self)
        win.title("")
        
        # Estimate geometry based on line lengths and count if not provided
        if geometry is None:
            lines = msg.split("\n")
            num_lines = len(lines)
            max_len = max(len(l) for l in lines) if lines else 0
            w = max(400, min(650, max_len * 7 + 80))
            h = max(160, num_lines * 22 + 90)
            geometry = f"{w}x{h}"
            
        win.geometry(geometry)
        win.configure(fg_color=T.BG_PANEL)
        win.transient(self)
        win.grab_set()
        
        w_width = int(geometry.split("x")[0])
        ctk.CTkLabel(win, text=msg, font=T.FONT_BODY,
                     text_color=T.GREEN, wraplength=w_width - 40).pack(pady=(20, 15))
        ctk.CTkButton(win, text="OK", command=win.destroy,
                      fg_color=T.GREEN_DIM, text_color="white").pack(pady=(0, 20))


def launch():
    app = VladgeMinifierApp()
    app.mainloop()


if __name__ == "__main__":
    launch()
