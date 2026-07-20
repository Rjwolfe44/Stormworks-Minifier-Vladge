"""
Stormworks microcontroller runtime shims.

MC Lua is a sandbox: no pcall/xpcall. Scripts that wrap property reads in
pcall() crash with `attempt to call a nil value (global 'pcall')`.
"""

from __future__ import annotations

from typing import List, Tuple

from ..lexer import Token, TT, tokenize, tokens_to_source


def _skip_ws(tokens: List[Token], j: int) -> int:
    n = len(tokens)
    while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
        j += 1
    return j


def unwrap_pcall(source: str) -> Tuple[str, int]:
    """
    Replace `pcall(function() ... end)` / `xpcall(function() ... end, ...)`
    with the inner body so MC scripts do not call missing globals.
    """
    tokens = tokenize(source)
    out: List[Token] = []
    i = 0
    unwrapped = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]
        if tok.type == TT.EOF:
            break

        if tok.type != TT.NAME or tok.value not in ("pcall", "xpcall"):
            out.append(tok)
            i += 1
            continue

        j = _skip_ws(tokens, i + 1)
        if j >= n or tokens[j].type != TT.OP or tokens[j].value != "(":
            out.append(tok)
            i += 1
            continue
        j = _skip_ws(tokens, j + 1)
        if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "function":
            out.append(tok)
            i += 1
            continue
        j = _skip_ws(tokens, j + 1)
        if j >= n or tokens[j].type != TT.OP or tokens[j].value != "(":
            out.append(tok)
            i += 1
            continue
        j = _skip_ws(tokens, j + 1)
        if j >= n or tokens[j].type != TT.OP or tokens[j].value != ")":
            out.append(tok)
            i += 1
            continue

        body_start = j + 1
        depth = 1  # function ... end
        j = body_start
        while j < n:
            t = tokens[j]
            if t.type == TT.KEYWORD:
                if t.value in ("function", "if", "for", "while", "repeat"):
                    depth += 1
                elif t.value == "end":
                    depth -= 1
                    if depth == 0:
                        break
                elif t.value == "until":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        if j >= n or depth != 0:
            out.append(tok)
            i += 1
            continue

        body_end = j
        # Still inside pcall( ... ) — consume through its closing ')'.
        j = body_end + 1
        paren = 1
        while j < n:
            t = tokens[j]
            if t.type == TT.OP:
                if t.value == "(":
                    paren += 1
                elif t.value == ")":
                    paren -= 1
                    if paren == 0:
                        break
            j += 1
        if j >= n or paren != 0:
            out.append(tok)
            i += 1
            continue

        body = list(tokens[body_start:body_end])
        while body and body[0].type in (TT.SPACE, TT.NEWLINE):
            body.pop(0)
        while body and body[-1].type in (TT.SPACE, TT.NEWLINE):
            body.pop()
        out.extend(body)
        unwrapped += 1
        i = j + 1

    if unwrapped == 0:
        return source, 0
    return tokens_to_source(out), unwrapped
