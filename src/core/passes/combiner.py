"""
Require bundler for LifeBoat / multi-file Stormworks projects.

Inlines ``require("mod.path")`` by wrapping module bodies in an IIFE with a
shared module cache. Search paths include project root, lib/, src/, _build/libs,
and optional LifeBoat VS Code libraryPaths.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Sequence

from ..lifeboat_project import discover_library_paths

# Matches require("file") or require 'file' or require("file.lua")
REQUIRE_PATTERN = re.compile(
    r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)|require\s+['"]([^'"]+)['"]'''
)


def _resolve_path(req_path: str, search_dirs: Sequence[Path]) -> Path | None:
    """Finds the absolute path to the required file."""
    # Lifeboat converts . to / for module paths BEFORE adding .lua
    alt_path = req_path.replace(".", "/")

    candidates = [req_path, alt_path]
    with_ext: List[str] = []
    for c in candidates:
        with_ext.append(c if c.endswith(".lua") else c + ".lua")

    for d in search_dirs:
        for rel in with_ext:
            p = d / rel
            if p.exists() and p.is_file():
                return p
    return None


def bundle_requires(
    source: str,
    root_dir: Path | str | None,
    loaded_files: dict | None = None,
    *,
    extra_paths: Sequence[Path | str] | None = None,
    search_dirs: Sequence[Path] | None = None,
) -> str:
    """
    Recursively scans for require() statements and inlines the file contents.
    Wraps the injected content in an IIFE to preserve scope and return values.

    Module cache ids use a ``__mN`` global pattern that is unlikely to collide
    with user identifiers; rename_globals may still shorten them safely once
    the whole bundle is in one stream.
    """
    if loaded_files is None:
        loaded_files = {}

    if search_dirs is None:
        if not root_dir and not extra_paths:
            return source
        search_dirs = discover_library_paths(root_dir, extra_paths)
    else:
        search_dirs = list(search_dirs)

    if not search_dirs:
        return source

    def replacer(match):
        req_path = match.group(1) or match.group(2)

        file_path = _resolve_path(req_path, search_dirs)
        if not file_path:
            return match.group(0)

        abs_path = str(file_path.resolve())

        if abs_path in loaded_files:
            module_id = loaded_files[abs_path]
            return f"{module_id}"

        module_id = f"__m{len(loaded_files)}"
        loaded_files[abs_path] = module_id

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return match.group(0)

        # Recurse with the SAME search dirs (+ file parent) so sibling/library
        # requires keep resolving after the first hop.
        child_dirs = list(search_dirs)
        parent = file_path.parent
        if parent not in child_dirs:
            child_dirs.insert(0, parent)
        content = bundle_requires(
            content,
            root_dir,
            loaded_files,
            search_dirs=child_dirs,
        )

        # Cache slot assigned below; hoisted `local __mN` decl is prepended after
        # the full rewrite so slots are real locals (not free globals).
        wrapped = (
            f"(function() if not {module_id} then {module_id} = (function()\n"
            f"{content}\n"
            f"end)() end return {module_id} end)()"
        )
        return wrapped

    bundled = REQUIRE_PATTERN.sub(replacer, source)
    if not loaded_files:
        return bundled

    # Hoist module cache as locals so rename/scope treat them correctly and they
    # cannot leak as undefined globals after rename_globals.
    ids = sorted(
        loaded_files.values(),
        key=lambda n: int(n[3:]) if isinstance(n, str) and n.startswith("__m") else 0,
    )
    return f"local {','.join(ids)};{bundled}"
