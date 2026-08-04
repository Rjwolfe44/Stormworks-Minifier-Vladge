"""
LifeBoat / VS Code project helpers.

Discovers library search paths from `.vscode/settings.json` and common
LifeBoat layout conventions (`_build/libs`, `lib`, `src`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List


_SETTINGS_KEYS = (
    "lifeboatapi.stormworks.libs.libraryPaths",
    "lifeboatapi.stormworks.libraryPaths",
)


def _unique(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    out: List[Path] = []
    for p in paths:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        if p.exists() and p.is_dir():
            seen.add(key)
            out.append(p)
    return out


def discover_library_paths(root: Path | str | None, extra: Iterable[Path | str] | None = None) -> List[Path]:
    """
    Return directories to search for ``require()`` modules.

    Always includes ``root``, ``root/lib``, ``root/src``, ``root/_build/libs``
    (and each immediate child of ``_build/libs``). Also reads LifeBoat VS Code
    settings when present.
    """
    paths: List[Path] = []
    if extra:
        for e in extra:
            paths.append(Path(e))

    if not root:
        return _unique(paths)

    root = Path(root).resolve()
    paths.append(root)
    for name in ("lib", "src"):
        paths.append(root / name)

    build_libs = root / "_build" / "libs"
    paths.append(build_libs)
    if build_libs.is_dir():
        for child in sorted(build_libs.iterdir()):
            if child.is_dir():
                paths.append(child)

    settings = root / ".vscode" / "settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for key in _SETTINGS_KEYS:
            raw = data.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        paths.append(Path(item))

    return _unique(paths)
