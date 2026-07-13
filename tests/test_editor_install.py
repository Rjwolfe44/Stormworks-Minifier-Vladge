"""Tests for VS Code / Cursor editor install and legacy migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.gui.editor_install import (
    LEGACY_EXE_NAME,
    LEGACY_TASK_LABEL,
    PRIMARY_KEYBIND,
    SECONDARY_KEYBIND,
    SHIM_NAME,
    TASK_PREFIX,
    build_task_presets,
    build_vladge_keybindings,
    install_editor_integration,
    install_editor_keybindings,
    is_legacy_vladge_task,
    is_vladge_keybinding,
    merge_tasks,
    migrate_legacy_vscode_artifacts,
    write_shim,
)


@pytest.fixture
def fake_cli(tmp_path: Path) -> Path:
    cli = tmp_path / "bin" / LEGACY_EXE_NAME
    cli.parent.mkdir(parents=True)
    cli.write_text("fake", encoding="utf-8")
    return cli


def test_is_legacy_vladge_task_detects_old_labels_and_commands():
    assert is_legacy_vladge_task({"label": LEGACY_TASK_LABEL, "command": "x"})
    assert is_legacy_vladge_task({
        "label": "Vladge: Paste (L4 Ultimate)",
        "command": "${workspaceFolder}/.vscode/vladge-minify.cmd",
    })
    assert is_legacy_vladge_task({
        "label": "Other",
        "command": "${workspaceFolder}/.vscode/vladgeminifier-cli.exe",
    })
    assert not is_legacy_vladge_task({"label": "npm: build", "command": "npm"})


def test_migrate_legacy_vscode_artifacts_removes_exe_and_internal(tmp_path: Path):
    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / LEGACY_EXE_NAME).write_text("broken", encoding="utf-8")
    internal = vscode / "_internal"
    internal.mkdir()
    (internal / "python312.dll").write_text("dll", encoding="utf-8")

    removed = migrate_legacy_vscode_artifacts(vscode)

    assert LEGACY_EXE_NAME in removed
    assert "_internal/" in removed
    assert not (vscode / LEGACY_EXE_NAME).exists()
    assert not internal.exists()


def test_write_shim_points_at_global_cli(tmp_path: Path, fake_cli: Path):
    shim = tmp_path / SHIM_NAME
    write_shim(shim, fake_cli)
    text = shim.read_text(encoding="utf-8")
    assert str(fake_cli.resolve()) in text
    assert "%*" in text


def test_build_task_presets_clipboard_default_level():
    tasks = build_task_presets(default_paste_level=3)
    labels = [t["label"] for t in tasks]
    assert "Vladge: Paste (L3 Aggressive)" in labels
    assert "Vladge: Save readable (L2)" in labels
    assert "Vladge: Batch folder (L4)" in labels

    defaults = [
        t for t in tasks
        if isinstance(t.get("group"), dict) and t["group"].get("isDefault")
    ]
    assert len(defaults) == 1
    assert defaults[0]["label"] == "Vladge: Paste (L3 Aggressive)"
    assert "--clipboard" in defaults[0]["args"]
    assert "--no-save" in defaults[0]["args"]


def test_merge_tasks_preserves_unrelated_tasks():
    existing = [
        {"label": LEGACY_TASK_LABEL, "command": ".vscode/vladgeminifier-cli.exe"},
        {"label": "My Custom Task", "command": "echo"},
    ]
    new = build_task_presets(4)
    merged, removed = merge_tasks(existing, new)
    assert removed == 1
    assert any(t["label"] == "My Custom Task" for t in merged)
    assert not any(t["label"] == LEGACY_TASK_LABEL for t in merged)
    assert sum(1 for t in merged if t["label"].startswith("Vladge:")) == len(new)


def test_build_vladge_keybindings_use_run_task():
    bindings = build_vladge_keybindings("Vladge: Paste (L4 Ultimate)")
    assert bindings[0]["key"] == PRIMARY_KEYBIND
    assert bindings[0]["args"] == "Vladge: Paste (L4 Ultimate)"
    assert bindings[1]["key"] == SECONDARY_KEYBIND
    assert bindings[1].get("args") is None


def test_is_vladge_keybinding():
    assert is_vladge_keybinding({"args": "Vladge: Paste (L4 Ultimate)"})
    assert is_vladge_keybinding({"key": PRIMARY_KEYBIND, "command": "workbench.action.tasks.runTask"})
    assert not is_vladge_keybinding({"key": "ctrl+s", "command": "workbench.action.files.save"})


def test_install_editor_keybindings_merges_and_replaces(tmp_path: Path):
    kb = tmp_path / "keybindings.json"
    kb.write_text(json.dumps([
        {"key": PRIMARY_KEYBIND, "command": "workbench.action.tasks.runTask", "args": "Vladge: Paste (L1 Strip)"},
        {"key": "ctrl+s", "command": "workbench.action.files.save"},
    ]), encoding="utf-8")

    updated = install_editor_keybindings(
        "Vladge: Paste (L4 Ultimate)",
        paths=[("TestEditor", kb)],
    )
    assert updated == ["TestEditor"]
    data = json.loads(kb.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["key"] == "ctrl+s"
    assert data[1]["args"] == "Vladge: Paste (L4 Ultimate)"
    assert data[2]["key"] == SECONDARY_KEYBIND


def test_install_migrates_legacy_project(tmp_path: Path, fake_cli: Path):
    project = tmp_path / "StormworksCode"
    vscode = project / ".vscode"
    vscode.mkdir(parents=True)
    (vscode / LEGACY_EXE_NAME).write_bytes(b"\x00" * 1024)
    internal = vscode / "_internal"
    internal.mkdir()
    (internal / "python312.dll").write_bytes(b"\x00" * 2048)

    tasks_path = vscode / "tasks.json"
    tasks_path.write_text(json.dumps({
        "version": "2.0.0",
        "tasks": [
            {
                "label": LEGACY_TASK_LABEL,
                "type": "process",
                "command": "${workspaceFolder}/.vscode/vladgeminifier-cli.exe",
                "args": ["${file}", "--level", "3"],
                "group": {"kind": "build", "isDefault": True},
            },
            {"label": "Compile shaders", "type": "shell", "command": "echo ok"},
        ],
    }), encoding="utf-8")

    result = install_editor_integration(
        project, 4, fake_cli, keybinding_paths=[],
    )

    assert not (vscode / LEGACY_EXE_NAME).exists()
    assert not internal.exists()
    assert (vscode / SHIM_NAME).exists()
    assert result.legacy_tasks_removed == 1

    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    labels = [t["label"] for t in data["tasks"]]
    assert LEGACY_TASK_LABEL not in labels
    assert "Compile shaders" in labels
    assert labels.count("Vladge: Paste (L4 Ultimate)") == 1
    assert all("vladgeminifier-cli.exe" not in t.get("command", "") for t in data["tasks"])

    manifest = json.loads((vscode / "vladge.json").read_text(encoding="utf-8"))
    assert manifest["cliPath"] == str(fake_cli.resolve())
    assert manifest["defaultPasteLevel"] == 4


def test_install_is_idempotent(tmp_path: Path, fake_cli: Path):
    project = tmp_path / "proj"
    install_editor_integration(project, 4, fake_cli, keybinding_paths=[])
    install_editor_integration(project, 2, fake_cli, keybinding_paths=[])

    data = json.loads((project / ".vscode/tasks.json").read_text(encoding="utf-8"))
    vladge_tasks = [t for t in data["tasks"] if t["label"].startswith("Vladge:")]
    assert len(vladge_tasks) == 8

    defaults = [
        t for t in vladge_tasks
        if isinstance(t.get("group"), dict) and t["group"].get("isDefault")
    ]
    assert len(defaults) == 1
    assert defaults[0]["label"] == "Vladge: Paste (L2 Standard)"


def test_cli_no_save_skips_output_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from src.cli.main import process_single

    src = tmp_path / "test.lua"
    src.write_text("function onTick() x=1 end", encoding="utf-8")
    copied: list[str] = []

    class FakeClip:
        @staticmethod
        def copy(text: str) -> None:
            copied.append(text)

    monkeypatch.setitem(__import__("sys").modules, "pyperclip", FakeClip())

    process_single(
        src, level=1, clipboard=True, no_save=True, save=None,
        deploy=None, quiet=True, obfuscate=False,
    )

    assert not (tmp_path / "_minified").exists()
    assert copied
