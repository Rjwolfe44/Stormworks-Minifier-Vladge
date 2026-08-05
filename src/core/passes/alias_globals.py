"""
Global alias injection pass.
Detects repeated access to Stormworks API methods and injects short alias
declarations at the top of the script to reduce character count.

e.g. input.getNumber called 10 times:
  Before: input.getNumber(1)  — 18 chars × 10 = 180
  After:  local _a=input.getNumber _a(1)  — adds 22, saves 12 per call → net +22-120=-98 chars
"""

from __future__ import annotations
import re
from typing import List, Dict, Tuple
from ..lexer import Token, TT


# Stormworks API method patterns suitable for aliasing
_ALIASABLE = [
    # (pattern_in_source, alias_prefix)
    "input.getNumber",
    "input.getBool",
    "output.setNumber",
    "output.setBool",
    "property.getNumber",
    "property.getBool",
    "property.getText",
    "screen.setColor",
    "screen.drawClear",
    "screen.drawRect",
    "screen.drawRectF",
    "screen.drawCircle",
    "screen.drawCircleF",
    "screen.drawLine",
    "screen.drawText",
    "screen.drawTextBox",
    "screen.drawTriangle",
    "screen.drawTriangleF",
    "screen.getWidth",
    "screen.getHeight",
    "math.sin",
    "math.cos",
    "math.atan",
    "math.abs",
    "math.sqrt",
    "math.floor",
    "math.ceil",
    "math.max",
    "math.min",
    "math.pi",
    "math.huge",
    "math.random",
    "table.insert",
    "table.remove",
    "table.concat",
    "string.format",
    "string.sub",
    "string.len",
    "string.find",
    "string.byte",
    "string.char",
]


def _count_occurrences(source: str, pattern: str) -> int:
    return source.count(pattern)


def _alias_name_gen():
    """Generate short alias names: _a, _b, ..., _z, _aa, ..."""
    import string
    chars = string.ascii_lowercase
    for c in chars:
        yield f"_{c}"
    for c1 in chars:
        for c2 in chars:
            yield f"_{c1}{c2}"


def inject_global_aliases(source: str) -> Tuple[str, int, Dict[str, str]]:
    """
    Analyse source for repeated SW API calls and inject aliases.

    Returns:
        new_source    — source with aliases prepended
        chars_saved   — net character reduction
        alias_map     — {original_api: alias_name}
    """
    # Count occurrences of each aliasable pattern
    counts: Dict[str, int] = {}
    for pattern in _ALIASABLE:
        c = _count_occurrences(source, pattern)
        if c > 0:
            counts[pattern] = c

    if not counts:
        return source, 0, {}

    # Only alias if it's actually worth it
    # Cost of alias declaration: "local _x=<pattern>" = 9 + len(pattern) chars
    # Savings per call: len(pattern) - len(alias_name) chars
    gen = _alias_name_gen()
    alias_map: Dict[str, str] = {}
    declarations: List[str] = []

    for pattern, count in sorted(counts.items(), key=lambda x: -x[1]):
        alias = next(gen)
        decl_cost = len(f"local {alias}={pattern} ")
        savings_per_call = len(pattern) - len(alias)
        net = savings_per_call * count - decl_cost
        if net > 0:
            alias_map[pattern] = alias
            declarations.append(f"local {alias}={pattern}")

    if not alias_map:
        return source, 0, {}

    # Replace all occurrences in source
    new_source = source
    for pattern, alias in alias_map.items():
        new_source = new_source.replace(pattern, alias)

    # Prepend declarations
    decl_block = " ".join(declarations) + " "
    new_source = decl_block + new_source

    chars_saved = len(source) - len(new_source)
    return new_source, chars_saved, alias_map
