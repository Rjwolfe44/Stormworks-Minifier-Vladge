"""
VS Code / Cursor editor integration — shim launcher, task presets, legacy migration.

Installs only lightweight files into the project's ``.vscode/`` folder (shim + tasks).
The full PyInstaller CLI bundle stays in the global VladgeMinifier install directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.version import __version__

SHIM_NAME = "vladge-minify.cmd"
MANIFEST_NAME = "vladge.json"
KEYBIND_SNIPPET_NAME = "vladge-keybindings.json"
TASK_PREFIX = "Vladge:"
LEGACY_TASK_LABEL = "Minify Current Lua File"
LEGACY_EXE_NAME = "vladgeminifier-cli.exe"
LEGACY_DIR_NAMES = ("_internal", "vladgeminifier-cli")

# Cursor binds Ctrl+Shift+B to the browser; use Lua-scoped chords instead.
PRIMARY_KEYBIND = "ctrl+alt+m"
SECONDARY_KEYBIND = "ctrl+alt+shift+m"
KEYBIND_WHEN = "editorTextFocus && editorLangId == lua"

LEVEL_NAMES = {
    1: "Strip",
    2: "Standard",
    3: "Aggressive",
    4: "Ultimate",
}


@dataclass
class EditorInstallResult:
    vscode_dir: Path
    shim_path: Path
    cli_path: Path
    default_task: str
    tasks_written: int
    legacy_removed: list[str] = field(default_factory=list)
    legacy_tasks_removed: int = 0
    keybindings_updated: list[str] = field(default_factory=list)


def resolve_cli_path(
    *,
    executable: Path | None = None,
    project_root: Path | None = None,
) -> Path | None:
    """Locate ``vladgeminifier-cli.exe`` next to the running app or under ``dist/``."""
    executable = executable or Path(sys.executable)
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent

    if getattr(sys, "frozen", False):
        sibling = executable.parent / LEGACY_EXE_NAME
        if sibling.is_file():
            return sibling.resolve()

    for rel in (
        Path("dist/VladgeMinifier_Export") / LEGACY_EXE_NAME,
        Path("dist") / LEGACY_EXE_NAME,
        Path("_export/VladgeMinifier") / LEGACY_EXE_NAME,
    ):
        candidate = project_root / rel
        if candidate.is_file():
            return candidate.resolve()

    sibling = executable.parent / LEGACY_EXE_NAME
    if sibling.is_file():
        return sibling.resolve()
    return None


def is_legacy_vladge_task(task: dict) -> bool:
    """True for old or previous Vladge task entries that should be replaced."""
    label = task.get("label") or ""
    if label == LEGACY_TASK_LABEL or label.startswith(TASK_PREFIX):
        return True
    command = task.get("command") or ""
    if isinstance(command, str) and "vladgeminifier-cli" in command.lower():
        return True
    if isinstance(command, str) and SHIM_NAME in command:
        return True
    return False


def migrate_legacy_vscode_artifacts(vscode_dir: Path) -> list[str]:
    """Remove broken legacy CLI copies from ``.vscode/``."""
    removed: list[str] = []
    legacy_exe = vscode_dir / LEGACY_EXE_NAME
    if legacy_exe.is_file():
        legacy_exe.unlink()
        removed.append(LEGACY_EXE_NAME)

    for dirname in LEGACY_DIR_NAMES:
        legacy_dir = vscode_dir / dirname
        if legacy_dir.is_dir():
            shutil.rmtree(legacy_dir)
            removed.append(f"{dirname}/")

    return removed


def write_shim(shim_path: Path, cli_path: Path) -> None:
    cli_str = str(cli_path.resolve())
    shim_path.write_text(f'@echo off\r\n"{cli_str}" %*\r\n', encoding="utf-8")


def build_task_presets(default_paste_level: int) -> list[dict]:
    """Build VS Code task definitions; one Paste preset is the default build task."""
    shim_cmd = f"${{workspaceFolder}}/.vscode/{SHIM_NAME}"
    presentation = {"reveal": "silent", "panel": "shared", "showReuseMessage": False}

    def paste_task(level: int) -> dict:
        name = LEVEL_NAMES[level]
        return {
            "label": f"{TASK_PREFIX} Paste (L{level} {name})",
            "type": "process",
            "command": shim_cmd,
            "args": [
                "${file}",
                "--level", str(level),
                "--clipboard", "--no-save", "--quiet",
            ],
            "group": {"kind": "build", "isDefault": level == default_paste_level},
            "presentation": presentation,
            "problemMatcher": [],
        }

    tasks = [paste_task(level) for level in (1, 2, 3, 4)]

    tasks.extend([
        {
            "label": f"{TASK_PREFIX} Save readable (L2)",
            "type": "process",
            "command": shim_cmd,
            "args": [
                "${file}",
                "--level", "2",
                "--multiline", "statements",
            ],
            "group": "build",
            "presentation": {"reveal": "always", "panel": "shared"},
            "problemMatcher": [],
        },
        {
            "label": f"{TASK_PREFIX} Save readable (L3)",
            "type": "process",
            "command": shim_cmd,
            "args": [
                "${file}",
                "--level", "3",
                "--multiline", "preserve",
            ],
            "group": "build",
            "presentation": {"reveal": "always", "panel": "shared"},
            "problemMatcher": [],
        },
        {
            "label": f"{TASK_PREFIX} Save ultimate (L4)",
            "type": "process",
            "command": shim_cmd,
            "args": ["${file}", "--level", "4"],
            "group": "build",
            "presentation": {"reveal": "always", "panel": "shared"},
            "problemMatcher": [],
        },
        {
            "label": f"{TASK_PREFIX} Batch folder (L4)",
            "type": "process",
            "command": shim_cmd,
            "args": ["${workspaceFolder}", "--batch", "--level", "4"],
            "group": "build",
            "presentation": {"reveal": "always", "panel": "shared"},
            "problemMatcher": [],
        },
    ])
    return tasks


def merge_tasks(existing: list[dict], new_vladge_tasks: list[dict]) -> tuple[list[dict], int]:
    """Drop legacy Vladge tasks and append fresh presets; preserve unrelated tasks."""
    kept = [t for t in existing if not is_legacy_vladge_task(t)]
    removed = len(existing) - len(kept)
    return kept + new_vladge_tasks, removed


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines: list[str] = []
    for line in text.splitlines():
        if "//" not in line:
            lines.append(line)
            continue
        out: list[str] = []
        in_string = False
        for i, char in enumerate(line):
            if char == '"' and (i == 0 or line[i - 1] != "\\"):
                in_string = not in_string
            if (
                not in_string
                and char == "/"
                and i + 1 < len(line)
                and line[i + 1] == "/"
            ):
                break
            out.append(char)
        lines.append("".join(out))
    return "\n".join(lines)


def _load_keybindings(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(_strip_jsonc(raw))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def is_vladge_keybinding(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    args = entry.get("args")
    if isinstance(args, str) and args.startswith(TASK_PREFIX):
        return True
    if entry.get("key") in {PRIMARY_KEYBIND, SECONDARY_KEYBIND}:
        cmd = entry.get("command")
        if cmd in {"workbench.action.tasks.runTask", "workbench.action.tasks.build"}:
            return True
    return False


def build_vladge_keybindings(default_task: str) -> list[dict]:
    """User keybinding entries (installed into Cursor / VS Code globally)."""
    return [
        {
            "key": PRIMARY_KEYBIND,
            "command": "workbench.action.tasks.runTask",
            "args": default_task,
            "when": KEYBIND_WHEN,
        },
        {
            "key": SECONDARY_KEYBIND,
            "command": "workbench.action.tasks.runTask",
            "when": KEYBIND_WHEN,
        },
    ]


def editor_keybindings_paths() -> list[tuple[str, Path]]:
    appdata = Path(os.environ.get("APPDATA", ""))
    if not appdata:
        return []
    return [
        ("Cursor", appdata / "Cursor" / "User" / "keybindings.json"),
        ("VS Code", appdata / "Code" / "User" / "keybindings.json"),
        ("VSCodium", appdata / "VSCodium" / "User" / "keybindings.json"),
    ]


def install_editor_keybindings(
    default_task: str,
    *,
    paths: list[tuple[str, Path]] | None = None,
) -> list[str]:
    """Merge Vladge keybinds into installed editors; returns editor names updated."""
    updated: list[str] = []
    fresh = build_vladge_keybindings(default_task)

    for editor_name, path in paths or editor_keybindings_paths():
        if not path.parent.exists():
            continue

        existing = _load_keybindings(path)
        merged = [entry for entry in existing if not is_vladge_keybinding(entry)]
        merged.extend(fresh)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=4) + "\n", encoding="utf-8")
        updated.append(editor_name)

    return updated


def write_keybinding_snippet(vscode_dir: Path, default_task: str) -> None:
    """Reference copy in the project if global keybind merge is unavailable."""
    snippet = {
        "_comment": "Paste these into Cursor/VS Code: File > Preferences > Keyboard Shortcuts > Open JSON",
        "keybindings": build_vladge_keybindings(default_task),
    }
    (vscode_dir / KEYBIND_SNIPPET_NAME).write_text(
        json.dumps(snippet, indent=4) + "\n",
        encoding="utf-8",
    )


def install_editor_integration(
    folder: Path,
    default_paste_level: int,
    cli_path: Path,
    *,
    keybinding_paths: list[tuple[str, Path]] | None = None,
) -> EditorInstallResult:
    """Write shim, manifest, and task presets; migrate legacy install artifacts."""
    if default_paste_level not in LEVEL_NAMES:
        raise ValueError(f"default_paste_level must be 1-4, got {default_paste_level}")

    vscode_dir = folder / ".vscode"
    folder.mkdir(parents=True, exist_ok=True)
    vscode_dir.mkdir(exist_ok=True)

    legacy_removed = migrate_legacy_vscode_artifacts(vscode_dir)

    shim_path = vscode_dir / SHIM_NAME
    write_shim(shim_path, cli_path)

    manifest = {
        "version": 1,
        "cliPath": str(cli_path.resolve()),
        "minifierVersion": __version__,
        "installedAt": datetime.now(timezone.utc).isoformat(),
        "defaultPasteLevel": default_paste_level,
    }
    (vscode_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    tasks_path = vscode_dir / "tasks.json"
    tasks_data: dict = {"version": "2.0.0", "tasks": []}
    if tasks_path.exists():
        try:
            tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "tasks" not in tasks_data or not isinstance(tasks_data["tasks"], list):
        tasks_data["tasks"] = []

    new_tasks = build_task_presets(default_paste_level)
    merged, legacy_tasks_removed = merge_tasks(tasks_data["tasks"], new_tasks)
    tasks_data["tasks"] = merged
    tasks_path.write_text(json.dumps(tasks_data, indent=4) + "\n", encoding="utf-8")

    default_task = f"{TASK_PREFIX} Paste (L{default_paste_level} {LEVEL_NAMES[default_paste_level]})"
    write_keybinding_snippet(vscode_dir, default_task)
    keybindings_updated = install_editor_keybindings(
        default_task, paths=keybinding_paths,
    )

    return EditorInstallResult(
        vscode_dir=vscode_dir,
        shim_path=shim_path,
        cli_path=cli_path.resolve(),
        default_task=default_task,
        tasks_written=len(new_tasks),
        legacy_removed=legacy_removed,
        legacy_tasks_removed=legacy_tasks_removed,
        keybindings_updated=keybindings_updated,
    )


def format_install_success_message(folder_name: str, result: EditorInstallResult) -> str:
    def _display_key(key: str) -> str:
        return "+".join(part.capitalize() for part in key.split("+"))

    lines = [f"Installed to {folder_name}!", ""]
    if result.legacy_removed or result.legacy_tasks_removed:
        lines.append("Migration:")
        for item in result.legacy_removed:
            lines.append(f"  removed .vscode/{item}")
        if result.legacy_tasks_removed:
            lines.append(f"  replaced {result.legacy_tasks_removed} old task(s)")
        lines.append("")

    key_line = _display_key(PRIMARY_KEYBIND)
    shift_line = _display_key(SECONDARY_KEYBIND)

    lines.extend([
        "HOW TO USE:",
        "1. Open the folder in VS Code or Cursor.",
        "2. Open a .lua file.",
        f"3. {key_line} -> paste minify ({result.default_task})",
        f"4. {shift_line} -> pick any Vladge preset",
        "   (both copy/save depending on preset)",
    ])
    if result.keybindings_updated:
        editors = ", ".join(result.keybindings_updated)
        lines.append(f"\nKeybinds added to: {editors}")
    else:
        lines.append(
            f"\nCopy keybinds from .vscode/{KEYBIND_SNIPPET_NAME}"
            " into Keyboard Shortcuts (JSON)."
        )
    return "\n".join(lines)
