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


def _parse_local_decl(tokens: List[Token], i: int, n: int) -> Optional[dict]:
    """
    Parse `local <name> = <single-expr>` starting at index i.
    Returns {'name': Token, 'value': [tokens], 'next_i': int} or None.
    The RHS is captured as everything up to (but not including) the next
    statement boundary at paren/bracket depth 0. Multi-name `local a,b=`
    and `local function` are rejected.
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
    end = j
    value: List[Token] = []
    saw_any = False
    while k < n:
        t = tokens[k]
        if t.type in _WS:
            k += 1
            continue
        if t.type == TT.OP:
            if t.value in ("(", "[", "{"):
                depth += 1
            elif t.value in (")", "]", "}"):
                depth -= 1
            elif t.value == "," and depth == 0:
                break  # multi-value RHS — not a single expr
            elif t.value == ";" and depth == 0:
                break
        if t.type == TT.KEYWORD and depth == 0 and t.value in _STMT_END_KW:
            break
        value.append(t)
        saw_any = True
        k += 1
        end = k
        # stop after a complete balanced expr that isn't obviously continuing
        if depth == 0 and saw_any:
            # peek: if next meaningful token can't extend an expr, stop
            nxt = _skip_ws(tokens, k, n)
            if nxt < n:
                nv = tokens[nxt]
                if nv.type == TT.KEYWORD and nv.value in _STMT_END_KW:
                    break
                # binary/unary operators and call/index continuations keep going
                if not (nv.type == TT.OP and nv.value in (
                        "+", "-", "*", "/", "//", "%", "^", "#", "..",
                        "==", "~=", "<", ">", "<=", ">=", "(", "[", "{", ".", ":")):
                    if not (nv.type == TT.KEYWORD and nv.value in ("and", "or", "not")):
                        break
            else:
                break
    if not saw_any or not value:
        return None
    return {'local': local_tok, 'name': name_tok, 'value': value, 'next_i': end}


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
        while next_i < n:
            j = next_i
            while j < n and (tokens[j].type in _WS or (tokens[j].type == TT.OP and tokens[j].value == ";")):
                j += 1
            if j >= n:
                break
            nxt = _parse_local_decl(tokens, j, n)
            if not nxt:
                break
            decls.append(nxt)
            next_i = nxt['next_i']

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
