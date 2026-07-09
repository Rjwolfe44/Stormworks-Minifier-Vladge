"""Short-circuit / dead-branch helpers for the linter."""

from __future__ import annotations
from typing import List, Set

from .lexer import Token, TT

_WS = frozenset({TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT})
_STOP_BEFORE_AND = frozenset({"then", "else", "elseif", "do"})


def _skip_ws(tokens: List[Token], i: int) -> int:
    n = len(tokens)
    while i < n and tokens[i].type in _WS:
        i += 1
    return n if i >= n else i


def _is_falsy_literal(tok: Token) -> bool:
    return (tok.type == TT.KEYWORD and tok.value in ("false", "nil")) or (
        tok.type == TT.NUMBER and tok.value in ("0", "0.0")
    )


def _or_chain_always_falsy(tokens: List[Token], start: int, end: int, user_defined: Set[str]) -> bool:
    """True if `a or b or ...` uses only globals not in user_defined / falsy literals."""
    i = start
    n = min(end, len(tokens))
    saw_operand = False
    while i < n:
        i = _skip_ws(tokens, i)
        if i >= n:
            break
        t = tokens[i]
        if t.type == TT.KEYWORD and t.value == "or":
            i += 1
            continue
        if t.type == TT.OP and t.value in ("(", ")"):
            i += 1
            continue
        if t.type == TT.NAME and t.value not in user_defined:
            saw_operand = True
            i += 1
            continue
        if _is_falsy_literal(t):
            saw_operand = True
            i += 1
            continue
        return False
    return saw_operand


def _expr_span_before_and(tokens: List[Token], and_idx: int) -> tuple[int, int]:
    """Token range [start, end) of expression immediately left of `and`."""
    i = and_idx - 1
    while i >= 0 and tokens[i].type in _WS:
        i -= 1
    if i < 0:
        return 0, 0
    end = i + 1
    depth = 0
    while i >= 0:
        t = tokens[i]
        if depth == 0:
            if t.type == TT.KEYWORD and t.value in _STOP_BEFORE_AND:
                i += 1
                break
            if t.type == TT.OP and t.value in (";", "="):
                i += 1
                break
        if t.type == TT.OP:
            if t.value in (")", "}", "]"):
                depth += 1
            elif t.value in ("(", "{", "["):
                depth -= 1
                if depth < 0:
                    i += 1
                    break
        i -= 1
    start = max(0, i)
    return start, end


def _depth_at(tokens: List[Token], idx: int) -> int:
    depth = 0
    for i in range(idx):
        if tokens[i].type == TT.OP:
            if tokens[i].value == "(":
                depth += 1
            elif tokens[i].value == ")":
                depth -= 1
    return depth


def _scan_operand_end(tokens: List[Token], start: int) -> int:
    start = _skip_ws(tokens, start)
    if start >= len(tokens):
        return start
    t = tokens[start]
    if t.type == TT.NAME or _is_falsy_literal(t):
        return start + 1
    if t.type == TT.OP and t.value == "(":
        depth = 1
        j = start + 1
        while j < len(tokens) and depth > 0:
            if tokens[j].type == TT.OP:
                if tokens[j].value == "(":
                    depth += 1
                elif tokens[j].value == ")":
                    depth -= 1
            j += 1
        return j
    return start + 1


def _or_operand_span(tokens: List[Token], name_idx: int) -> tuple[int, int] | None:
    """If name_idx is inside `a or b or ...`, return [start, end) of that chain."""
    if name_idx >= len(tokens) or tokens[name_idx].type != TT.NAME:
        return None
    depth = _depth_at(tokens, name_idx)

    start = name_idx
    end = name_idx + 1
    extended = False
    while True:
        j = _skip_ws(tokens, end)
        if j >= len(tokens) or tokens[j].type != TT.KEYWORD or tokens[j].value != "or":
            break
        if _depth_at(tokens, j) != depth:
            break
        extended = True
        end = _scan_operand_end(tokens, j + 1)

    while True:
        j = name_idx - 1
        while j >= 0 and tokens[j].type in _WS:
            j -= 1
        if j < 0 or tokens[j].type != TT.KEYWORD or tokens[j].value != "or":
            break
        if _depth_at(tokens, j) != depth:
            break
        extended = True
        k = j - 1
        while k >= 0 and tokens[k].type in _WS:
            k -= 1
        if k < 0:
            break
        if tokens[k].type == TT.NAME:
            start = k
            name_idx = k
            continue
        if tokens[k].type == TT.OP and tokens[k].value == ")":
            depth2 = 1
            m = k - 1
            while m >= 0 and depth2 > 0:
                if tokens[m].type == TT.OP:
                    if tokens[m].value == ")":
                        depth2 += 1
                    elif tokens[m].value == "(":
                        depth2 -= 1
                m -= 1
            start = m + 1
            name_idx = start
            continue
        break

    if not extended:
        return None
    return start, end


def _in_safe_or_operand(tokens: List[Token], name_idx: int, user_defined: Set[str]) -> bool:
    """Nil-read of undefined global inside an all-falsy `or` chain is safe in Lua."""
    span = _or_operand_span(tokens, name_idx)
    if span is None:
        return False
    start, end = span
    return _or_chain_always_falsy(tokens, start, end, user_defined)


def _lhs_never_truthy(tokens: List[Token], start: int, end: int, user_defined: Set[str]) -> bool:
    """
    True if expression cannot be truthy (e.g. ends with `and (undef or undef)`).
    """
    s = _skip_ws(tokens, start)
    e = end
    while e > s and tokens[e - 1].type in _WS:
        e -= 1
    if s >= e:
        return False

    if s < e and tokens[s].type == TT.OP and tokens[s].value == "(":
        depth = 0
        for i in range(s, e):
            if tokens[i].type == TT.OP:
                if tokens[i].value == "(":
                    depth += 1
                elif tokens[i].value == ")":
                    depth -= 1
                    if depth == 0 and i == e - 1:
                        return _lhs_never_truthy(tokens, s + 1, e - 1, user_defined)
                    if depth == 0:
                        break

    if _or_chain_always_falsy(tokens, start, end, user_defined):
        return True

    last_and = None
    depth = 0
    for i in range(start, end):
        t = tokens[i]
        if t.type == TT.OP:
            if t.value in ("(", "{", "["):
                depth += 1
            elif t.value in (")", "}", "]"):
                depth -= 1
        elif depth == 0 and t.type == TT.KEYWORD and t.value == "and":
            last_and = i

    if last_and is not None:
        rhs = _skip_ws(tokens, last_and + 1)
        if _or_chain_always_falsy(tokens, rhs, end, user_defined):
            return True

    return False


def is_short_circuit_dead_read(tokens: List[Token], name_idx: int, user_defined: Set[str]) -> bool:
    """
    True if reading NAME at name_idx won't run or is a safe nil-read on assignment RHS.
    """
    j = name_idx - 1
    while j >= 0 and tokens[j].type in _WS:
        j -= 1
    if j >= 0 and tokens[j].type == TT.OP and tokens[j].value == "=":
        return True

    if _in_safe_or_operand(tokens, name_idx, user_defined):
        return True

    for i in range(name_idx - 1, -1, -1):
        if tokens[i].type != TT.KEYWORD or tokens[i].value != "and":
            continue
        lhs_start, lhs_end = _expr_span_before_and(tokens, i)
        if lhs_start <= name_idx < lhs_end:
            continue
        if name_idx <= i:
            continue
        if _lhs_never_truthy(tokens, lhs_start, lhs_end, user_defined):
            return True

    return False
