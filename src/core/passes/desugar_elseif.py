"""
Desugar `elseif` chains into nested `else`/`if` blocks.

Compacting nested `if`/`elseif`/`else` can make a trailing `elseif`/`else`
appear bound to an inner `if` (silent control-flow bug on Stormworks). Rewriting
to nested `else` + `if` keeps the same semantics with unambiguous matching.
"""

from __future__ import annotations

from luaparser import ast
from luaparser.astnodes import Block, ElseIf, If


def _elseif_to_nested_if(node: ElseIf) -> If:
    """Convert one ElseIf (possibly chained) into an If with nested else."""
    orelse = node.orelse
    if isinstance(orelse, ElseIf):
        orelse = Block(body=[_elseif_to_nested_if(orelse)])
    return If(test=node.test, body=node.body, orelse=orelse)


def desugar_elseif(source: str) -> tuple[str, int]:
    """
    Rewrite elseif chains to nested else/if.

    Returns (source, number_of_top_level_chains_converted).
    On parse failure, returns the original source unchanged.
    """
    try:
        tree = ast.parse(source)
    except Exception:
        return source, 0

    converted = 0
    for node in list(ast.walk(tree)):
        if isinstance(node, If) and isinstance(node.orelse, ElseIf):
            node.orelse = Block(body=[_elseif_to_nested_if(node.orelse)])
            converted += 1

    if converted == 0:
        return source, 0

    if any(isinstance(n, ElseIf) for n in ast.walk(tree)):
        # Should not happen; refuse to emit a partial rewrite.
        return source, 0

    try:
        out = ast.to_lua_source(tree)
    except Exception:
        return source, 0
    return out, converted
