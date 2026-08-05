"""
Function inlining pass (Level 4).
Inlines small single-return local functions when net byte savings are positive.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from ..lexer import Token, TT, tokens_to_source

_STMT_KEYWORDS = frozenset({"local", "function", "if", "for", "while", "repeat", "do", "return"})
_WS = frozenset({TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT})


def _skip_ws(tokens: List[Token], i: int) -> int:
    n = len(tokens)
    while i < n and tokens[i].type in _WS:
        i += 1
    return i


def _block_end_after_function(tokens: List[Token], func_kw: int) -> int:
    depth = 1
    n = len(tokens)
    i = func_kw + 1
    while i < n:
        t = tokens[i]
        if t.type == TT.KEYWORD:
            if t.value in ("function", "if", "for", "while", "repeat", "do"):
                depth += 1
            elif t.value == "end":
                depth -= 1
                if depth == 0:
                    return i
            elif t.value == "until":
                depth -= 1
        i += 1
    return n - 1


def _parse_local_function(tokens: List[Token], i: int) -> Optional[Tuple[int, int, str, List[str], int, int]]:
    n = len(tokens)
    if tokens[i].type != TT.KEYWORD or tokens[i].value != "local":
        return None
    j = _skip_ws(tokens, i + 1)
    if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "function":
        return None
    func_kw = j
    j = _skip_ws(tokens, j + 1)
    if j >= n or tokens[j].type != TT.NAME:
        return None
    name = tokens[j].value
    j = _skip_ws(tokens, j + 1)
    if j >= n or tokens[j].type != TT.OP or tokens[j].value != "(":
        return None

    param_names: List[str] = []
    k = j + 1
    while k < n:
        k = _skip_ws(tokens, k)
        if k >= n:
            return None
        if tokens[k].type == TT.OP and tokens[k].value == ")":
            break
        if tokens[k].type == TT.NAME:
            param_names.append(tokens[k].value)
            k += 1
            k = _skip_ws(tokens, k)
            if k < n and tokens[k].type == TT.OP and tokens[k].value == ",":
                k += 1
                continue
        elif tokens[k].type == TT.OP and tokens[k].value == "...":
            return None
        else:
            return None

    body_start = _skip_ws(tokens, k + 1)
    end_idx = _block_end_after_function(tokens, func_kw)
    return i, end_idx + 1, name, param_names, body_start, end_idx


def _body_is_single_return(tokens: List[Token], body_start: int, end_idx: int) -> Optional[List[Token]]:
    i = _skip_ws(tokens, body_start)
    if i >= end_idx or tokens[i].type != TT.KEYWORD or tokens[i].value != "return":
        return None
    ret_start = _skip_ws(tokens, i + 1)
    depth = 0
    j = ret_start
    while j < end_idx:
        t = tokens[j]
        if t.type == TT.OP and t.value in ("(", "{", "["):
            depth += 1
        elif t.type == TT.OP and t.value in (")", "}", "]"):
            depth -= 1
        elif depth == 0 and t.type == TT.KEYWORD and t.value in _STMT_KEYWORDS:
            return None
        j += 1
    return tokens[ret_start:end_idx]


def _call_sites(tokens: List[Token], name: str, decl_start: int, decl_end: int) -> List[int]:
    sites: List[int] = []
    for i, t in enumerate(tokens):
        if decl_start <= i <= decl_end:
            continue
        if t.type == TT.NAME and t.value == name:
            j = _skip_ws(tokens, i + 1)
            if j < len(tokens) and tokens[j].type == TT.OP and tokens[j].value == "(":
                sites.append(i)
    return sites


def _extract_call_args(tokens: List[Token], call_idx: int) -> Optional[List[Tuple[int, int]]]:
    j = _skip_ws(tokens, call_idx + 1)
    if j >= len(tokens) or tokens[j].type != TT.OP or tokens[j].value != "(":
        return None
    args: List[Tuple[int, int]] = []
    i = j + 1
    arg_start = i
    depth = 1
    n = len(tokens)
    while i < n and depth > 0:
        t = tokens[i]
        if t.type == TT.OP:
            if t.value == "(":
                depth += 1
            elif t.value == ")":
                depth -= 1
                if depth == 0:
                    if arg_start < i:
                        args.append((arg_start, i))
                    break
            elif t.value == "," and depth == 1:
                args.append((arg_start, i))
                arg_start = i + 1
        i += 1
    return args


def _call_end(tokens: List[Token], call_idx: int) -> int:
    j = _skip_ws(tokens, call_idx + 1)
    depth = 0
    k = j
    n = len(tokens)
    while k < n:
        if tokens[k].type == TT.OP:
            if tokens[k].value == "(":
                depth += 1
            elif tokens[k].value == ")":
                depth -= 1
                if depth == 0:
                    return k + 1
        k += 1
    return call_idx + 1


def _substitute(body: List[Token], param_names: List[str], args: List[Tuple[int, int]], tokens: List[Token]) -> List[Token]:
    mapping = {
        pname: [Token(t.type, t.value, t.pos) for t in tokens[a0:a1]]
        for pname, (a0, a1) in zip(param_names, args)
    }
    out: List[Token] = []
    for t in body:
        if t.type == TT.NAME and t.value in mapping:
            out.extend(mapping[t.value])
        else:
            out.append(Token(t.type, t.value, t.pos))
    return out


def _net_savings(
    tokens: List[Token],
    start: int,
    stmt_end: int,
    name: str,
    param_names: List[str],
    body: List[Token],
    sites: List[int],
) -> int:
    """Estimate bytes saved by inlining (positive = worth it)."""
    decl_len = len(tokens_to_source(tokens[start:stmt_end]))
    body_wrapped = tokens_to_source([
        Token(TT.OP, "(", 0), *body, Token(TT.OP, ")", 0),
    ])
    inline_len = len(body_wrapped)
    call_saved = 0
    for site in sites:
        call_len = len(tokens_to_source(tokens[site:_call_end(tokens, site)]))
        call_saved += call_len - inline_len
    return call_saved - decl_len


def inline_functions(
    tokens: List[Token],
    *,
    max_body_tokens: int = 32,
    max_call_sites: int = 1,
    require_net_savings: bool = True,
) -> Tuple[List[Token], int]:
    """
    Inline eligible local functions.

    Default (L4 auto): single call-site, net savings required.
    Aggressive (--inline-functions): up to 3 call sites, still requires net savings.
    """
    n = len(tokens)
    candidates: List[Tuple[int, int, str, List[str], List[Token]]] = []

    i = 0
    while i < n:
        parsed = _parse_local_function(tokens, i)
        if parsed:
            start, stmt_end, name, param_names, body_start, end_idx = parsed
            body = _body_is_single_return(tokens, body_start, end_idx)
            if body is not None and len(body) <= max_body_tokens:
                candidates.append((start, stmt_end, name, param_names, body))
                i = stmt_end
                continue
        i += 1

    if not candidates:
        return tokens, 0

    remove_ranges: List[Tuple[int, int]] = []
    call_replacements: List[Tuple[int, int, List[Token]]] = []
    inlined = 0

    for start, stmt_end, name, param_names, body in reversed(candidates):
        sites = _call_sites(tokens, name, start, stmt_end - 1)
        if not sites or len(sites) > max_call_sites:
            continue
        if require_net_savings and _net_savings(tokens, start, stmt_end, name, param_names, body, sites) <= 0:
            continue
        args0 = _extract_call_args(tokens, sites[0])
        if args0 is None or len(args0) != len(param_names):
            continue
        if not all(
            _extract_call_args(tokens, s) is not None
            and len(_extract_call_args(tokens, s)) == len(param_names)  # type: ignore[arg-type]
            for s in sites
        ):
            continue

        for site in sites:
            args = _extract_call_args(tokens, site)
            if args is None:
                continue
            sub = _substitute(body, param_names, args, tokens)
            wrapped = [
                Token(TT.OP, "(", tokens[site].pos),
                *sub,
                Token(TT.OP, ")", tokens[site].pos),
            ]
            call_replacements.append((site, _call_end(tokens, site), wrapped))

        remove_ranges.append((start, stmt_end))
        inlined += 1

    if not remove_ranges:
        return tokens, 0

    skip = set()
    for a, b in remove_ranges:
        skip.update(range(a, b))
    for a, b, _ in call_replacements:
        skip.update(range(a, b))

    inserts: Dict[int, List[Token]] = {a: w for a, _, w in call_replacements}

    out: List[Token] = []
    i = 0
    while i < n:
        if i in inserts:
            out.extend(inserts[i])
            i += 1
            while i < n and i in skip:
                i += 1
            continue
        if i in skip:
            i += 1
            continue
        out.append(tokens[i])
        i += 1

    return out, inlined
