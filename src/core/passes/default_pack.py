"""
Default-value chain compression (Level 3+).
Packs consecutive `if x==0 then x=N end` into semicolon chain when shorter and valid.
"""

from __future__ import annotations
import re
from typing import List, Tuple


_CHAIN_RE = re.compile(
    r'if\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*==\s*0\s+then\s+\1\s*=\s*([^;\n]+?)\s+end',
)


def _try_parse(code: str) -> bool:
    try:
        from luaparser import ast
        ast.parse(code)
        return True
    except Exception:
        return False


def compress_default_chains(source: str) -> Tuple[str, int]:
    """Detect runs of default-value if-chains and replace when net shorter and parseable."""
    matches = list(_CHAIN_RE.finditer(source))
    if len(matches) < 2:
        return source, 0

    groups: List[List[re.Match]] = []
    current: List[re.Match] = [matches[0]]
    for m in matches[1:]:
        if m.start() - current[-1].end() <= 5:
            current.append(m)
        else:
            if len(current) >= 2:
                groups.append(current)
            current = [m]
    if len(current) >= 2:
        groups.append(current)

    new_source = source
    total_saved = 0
    for group in groups:
        names = [m.group(1) for m in group]
        vals = [m.group(2).strip() for m in group]
        old_block = source[group[0].start():group[-1].end()]
        if len(set(names)) != len(names):
            continue
        packed = ";".join(f"if {n}==0 then {n}={v} end" for n, v in zip(names, vals))
        if len(packed) >= len(old_block):
            continue
        candidate = new_source.replace(old_block, packed, 1)
        if not _try_parse(candidate):
            continue
        new_source = candidate
        total_saved += len(old_block) - len(packed)

    return new_source, total_saved
