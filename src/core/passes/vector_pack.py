"""
Vector table literal packing (Level 4).
Merges `local V={}` + separate `function V.new` into one table literal when shorter.
Only applies when luaparser confirms the result is valid Lua.
"""

from __future__ import annotations
import re
from typing import Tuple


def _try_parse(code: str) -> bool:
    try:
        from luaparser import ast
        ast.parse(code)
        return True
    except Exception:
        return False


def pack_vector_tables(source: str) -> Tuple[str, int]:
    """
    Detect V={} followed by function V.method definitions and pack into one literal.
    Conservative: statement must start at line beginning; result must parse.
    """
    pattern = re.compile(
        r'(?m)^local\s+([A-Z][A-Za-z0-9_]*)\s*=\s*\{\}\s*\n'
        r'((?:function\s+\1\.([a-zA-Z_][a-zA-Z0-9_]*)\([^)]*\)[\s\S]*?^end\s*\n?)+)',
    )
    m = pattern.search(source)
    if not m:
        return source, 0

    table_name = m.group(1)
    block = m.group(0)
    methods = re.findall(
        rf'(?m)^function\s+{re.escape(table_name)}\.([a-zA-Z_][a-zA-Z0-9_]*)\([^)]*\)([\s\S]*?)^end',
        block,
    )
    if len(methods) < 2:
        return source, 0

    parts = []
    for meth_name, body in methods:
        body = body.strip()
        parts.append(f"{meth_name}=function(...){body}end")

    packed = f"local {table_name}={{{','.join(parts)}}}\n"
    if len(packed) >= len(block):
        return source, 0

    candidate = source[:m.start()] + packed + source[m.end():]
    if not _try_parse(candidate):
        return source, 0
    return candidate, len(block) - len(packed)
