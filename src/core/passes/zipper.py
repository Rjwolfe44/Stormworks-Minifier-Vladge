"""
Multi-Assignment Consolidation (The "Zipper").
Merges consecutive local variable declarations.
e.g. `local x = 1 local y = 2` -> `local x,y = 1,2`

Generalized (Level 4): merges declarations whose right-hand side is ANY single
expression, not just literals — `local a = f() local b = t.x` -> `local a,b = f(),t.x`.
A declaration is only zipped when its RHS is exactly one expression (so the merge
cannot shift multi-value call returns across names) and the merge is smaller.
"""
from typing import List, Optional, Tuple
from ..lexer import Token, TT

_WS = (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT)

# tokens that terminate a single-expression RHS at depth 0
_STMT_END_KW = {"local", "if", "for", "while", "function", "repeat", "return",
                "end", "else", "elseif", "until", "do", "break", "then", "in"}


def _skip_ws(tokens: List[Token], i: int, n: int) -> int:
    while i < n and tokens[i].type in _WS:
        i += 1
    return i


# Expression-boundary sets (mirrors scope.py): a token that can END an
# expression, and a token that can CONTINUE one. A binary operator can never
# end an expression — `1 - d` must not be truncated after the `-`.
_EXPR_END_TYPES = (TT.NAME, TT.NUMBER, TT.STRING, TT.LONGSTRING)
_EXPR_END_OPS = frozenset({")", "]", "}", "..."})
_EXPR_END_KWS = frozenset({"true", "false", "nil"})
_EXPR_CONT_OPS = frozenset({
    "+", "-", "*", "/", "//", "%", "^", "#", "..",
    "==", "~=", "<", ">", "<=", ">=", "(", "[", "{", ".", ":",
})
_EXPR_CONT_KWS = frozenset({"and", "or"})


def _ends_expr(t: Token) -> bool:
    return (
        t.type in _EXPR_END_TYPES
        or (t.type == TT.OP and t.value in _EXPR_END_OPS)
        or (t.type == TT.KEYWORD and t.value in _EXPR_END_KWS)
    )


def _continues_expr(t: Token) -> bool:
    if t.type == TT.OP and t.value in _EXPR_CONT_OPS:
        return True
    if t.type == TT.KEYWORD and t.value in _EXPR_CONT_KWS:
        return True
    if t.type in (TT.STRING, TT.LONGSTRING):
        return True  # call with string arg: f "x"
    return False


def _parse_local_decl(tokens: List[Token], i: int, n: int) -> Optional[dict]:
    """
    Parse `local <name> = <single-expr>` starting at index i.
    Returns {'name': Token, 'value': [tokens], 'next_i': int} or None.
    The RHS is captured as everything up to (but not including) the next
    statement boundary at paren/bracket depth 0. Multi-name `local a,b=`,
    `local function`, and multi-value RHS (`local a = f(), g()`) are rejected.
    """
    j = _skip_ws(tokens, i, n)
    if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "local":
        return None
    local_tok = tokens[j]
    j = _skip_ws(tokens, j + 1, n)
    if j >= n or tokens[j].type != TT.NAME:
        return None
    name_tok = tokens[j]
    j = _skip_ws(tokens, j + 1, n)
    # reject `local a,` (multi) and `local function`
    if j >= n or tokens[j].type != TT.OP or tokens[j].value != "=":
        return None
    j = _skip_ws(tokens, j + 1, n)
    if j >= n:
        return None

    # capture a single expression: stop at depth-0 ',' or a statement boundary
    depth = 0
    k = j
    value: List[Token] = []
    prev: Optional[Token] = None
    while k < n:
        t = tokens[k]
        if t.type in _WS:
            k += 1
            continue
        if t.type == TT.OP:
            if t.value in ("(", "[", "{"):
                depth += 1
                value.append(t)
                prev = t
                k += 1
                continue
            if t.value in (")", "]", "}"):
                depth -= 1
                value.append(t)
                prev = t
                k += 1
                continue
            if t.value == "," and depth == 0:
                return None  # multi-value RHS — merging would drop values
            if t.value == ";" and depth == 0:
                break
        if t.type == TT.KEYWORD and depth == 0 and t.value in _STMT_END_KW:
            break
        if depth == 0 and prev is not None and _ends_expr(prev) and not _continues_expr(t):
            break  # statement boundary
        value.append(t)
        prev = t
        k += 1
    if not value:
        return None
    return {'local': local_tok, 'name': name_tok, 'value': value, 'next_i': k}


def _rhs_references(value: List[Token], names: set) -> bool:
    """
    True if the RHS token list references any variable in `names`.

    In `local a, b = e1, e2` the RHS evaluates BEFORE the new locals bind, so a
    reference in e2 to `a` would resolve to the outer scope, not the local being
    declared. Merging is only safe when no RHS references a same-group name.

    Property (`.x` / `:m()`) and table-key (`{k = ...}`) positions are not
    variable references and are ignored. A name referencing ITSELF in its own
    RHS is safe (it resolves to the outer binding in both forms), so callers
    must only pass names of EARLIER group members.
    """
    meaningful = [t for t in value if t.type not in _WS]
    for k, t in enumerate(meaningful):
        if t.type != TT.NAME or t.value not in names:
            continue
        prev = meaningful[k - 1] if k > 0 else None
        nxt = meaningful[k + 1] if k + 1 < len(meaningful) else None
        if prev is not None and prev.type == TT.OP and prev.value in (".", ":"):
            continue  # property / method name, not a variable read
        if nxt is not None and nxt.type == TT.OP and nxt.value == "=":
            continue  # table constructor key `{ name = ... }`
        return True
    return False


def consolidate_locals(tokens: List[Token]) -> Tuple[List[Token], int]:
    """Returns: (new_tokens, declarations_merged)."""
    new_tokens: List[Token] = []
    i = 0
    n = len(tokens)
    merged_count = 0

    while i < n:
        parsed = _parse_local_decl(tokens, i, n)
        if not parsed:
            new_tokens.append(tokens[i])
            i += 1
            continue

        decls = [parsed]
        next_i = parsed['next_i']
        scan = next_i
        while scan < n:
            j = scan
            while j < n and (tokens[j].type in _WS or (tokens[j].type == TT.OP and tokens[j].value == ";")):
                j += 1
            if j >= n:
                break
            nxt = _parse_local_decl(tokens, j, n)
            if not nxt:
                break
            # RHS of a candidate must not reference locals already in this merge
            # group — after merging, the whole RHS evaluates before any of the
            # group's new locals bind, so such a reference would read a global.
            group_names = {d['name'].value for d in decls}
            if _rhs_references(nxt['value'], group_names):
                break
            decls.append(nxt)
            next_i = nxt['next_i']
            scan = next_i

        if len(decls) < 2:
            new_tokens.append(tokens[i])
            i += 1
            continue

        # Build `local a,b,c = va,vb,vc`. Only keep if smaller than the originals.
        merged: List[Token] = [Token(TT.KEYWORD, "local", tokens[i].pos), Token(TT.SPACE, " ", tokens[i].pos)]
        for k, d in enumerate(decls):
            merged.append(d['name'])
            if k < len(decls) - 1:
                merged.append(Token(TT.OP, ",", d['name'].pos))
        merged.append(Token(TT.OP, "=", decls[0]['name'].pos))
        for k, d in enumerate(decls):
            merged.extend(d['value'])
            if k < len(decls) - 1:
                merged.append(Token(TT.OP, ",", d['value'][-1].pos))

        orig_len = sum(len(t.value) for t in tokens[i:next_i] if t.type not in _WS)
        merged_len = sum(len(t.value) for t in merged)
        if merged_len < orig_len:
            new_tokens.extend(merged)
            merged_count += len(decls) - 1
            i = next_i
        else:
            new_tokens.append(tokens[i])
            i += 1

    return new_tokens, merged_count
