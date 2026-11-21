"""
Stormworks microcontroller runtime shims.

MC Lua is a sandbox: no pcall/xpcall. Scripts that wrap property reads in
pcall() crash with `attempt to call a nil value (global 'pcall')`.
"""

from __future__ import annotations

from typing import List, Tuple

from ..lexer import Token, TT, tokenize, tokens_to_source

_TRIVIA = frozenset({TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT})

# Keywords after which a new statement begins.
_STMT_AFTER_KEYWORDS = frozenset({
    "then", "do", "else", "repeat", "end", "break", "true", "false", "nil",
})

# Tokens that, right after `pcall(...)`, would keep using its result.
_CONTINUATION_OPS = frozenset({"(", ".", ":", "[", "{"})

_SHIMS = {
    "pcall": "local function pcall(f,...)return true,f(...)end\n",
    "xpcall": "local function xpcall(f,h,...)return true,f(...)end\n",
}


def _skip_ws(tokens: List[Token], j: int) -> int:
    n = len(tokens)
    while j < n and tokens[j].type in _TRIVIA:
        j += 1
    return j


def _prev_sig(tokens: List[Token], i: int) -> Token | None:
    i -= 1
    while i >= 0 and tokens[i].type in _TRIVIA:
        i -= 1
    return tokens[i] if i >= 0 else None


def _at_statement_start(tokens: List[Token], i: int) -> bool:
    """True when tokens[i] begins a statement (not an expression or field)."""
    prev = _prev_sig(tokens, i)
    if prev is None:
        return True
    if prev.type in (TT.NAME, TT.NUMBER, TT.STRING, TT.LONGSTRING):
        return True
    if prev.type == TT.OP:
        return prev.value in (";", ")", "]", "}", "...")
    if prev.type == TT.KEYWORD:
        return prev.value in _STMT_AFTER_KEYWORDS
    return False


def _is_global_ref(tokens: List[Token], i: int) -> bool:
    """`pcall` used as a variable (not `obj.pcall` / `obj:pcall`)."""
    prev = _prev_sig(tokens, i)
    return not (prev is not None and prev.type == TT.OP and prev.value in (".", ":"))


def _user_defines(tokens: List[Token], name: str) -> bool:
    """True when the script defines `name` itself (local, function or assignment)."""
    for i, t in enumerate(tokens):
        if t.type != TT.NAME or t.value != name:
            continue
        prev = _prev_sig(tokens, i)
        if prev is not None and prev.type == TT.KEYWORD and prev.value in ("local", "function"):
            return True
        if prev is not None and prev.type == TT.OP and prev.value in (".", ":"):
            continue
        j = _skip_ws(tokens, i + 1)
        if j < len(tokens) and tokens[j].type == TT.OP and tokens[j].value in ("=", ","):
            return True
    return False


def _scan_body(tokens: List[Token], start: int) -> Tuple[int, bool, bool]:
    """
    Walk a `function() ... end` body from `start`.

    Returns (index of its closing `end` or -1, has an own-level `return`,
    declares own-level locals/labels that would leak if unwrapped).
    """
    blocks: List[str] = []
    pending_do = 0
    has_return = False
    leaks = False
    n = len(tokens)
    j = start
    while j < n:
        t = tokens[j]
        if t.type == TT.KEYWORD:
            v = t.value
            if v == "return" and "function" not in blocks:
                has_return = True
            elif v == "local" and not blocks:
                leaks = True
            if v in ("function", "if", "repeat"):
                blocks.append(v)
            elif v in ("while", "for"):
                blocks.append(v)
                pending_do += 1
            elif v == "do":
                if pending_do:
                    pending_do -= 1
                else:
                    blocks.append("do")
            elif v in ("end", "until"):
                if not blocks:
                    return (j, has_return, leaks) if v == "end" else (-1, False, False)
                blocks.pop()
        elif t.type == TT.OP and t.value == "::" and not blocks:
            leaks = True
        j += 1
    return -1, False, False


def _find_close_paren(tokens: List[Token], start: int) -> int:
    """Index of the `)` closing an argument list we are already inside, or -1."""
    depth = 1
    for m in range(start, len(tokens)):
        t = tokens[m]
        if t.type != TT.OP:
            continue
        if t.value in ("(", "[", "{"):
            depth += 1
        elif t.value in (")", "]", "}"):
            depth -= 1
            if depth == 0:
                return m
    return -1


def _try_unwrap(tokens: List[Token], i: int) -> Tuple[List[Token], int] | None:
    """
    `pcall(function() BODY end)` as a whole statement -> BODY (in `do ... end`
    when it declares locals). Returns (replacement tokens, index after the
    call) or None when unwrapping would change behaviour.
    """
    n = len(tokens)
    if not _at_statement_start(tokens, i):
        return None
    j = _skip_ws(tokens, i + 1)
    if j >= n or tokens[j].type != TT.OP or tokens[j].value != "(":
        return None
    k = _skip_ws(tokens, j + 1)
    if k >= n or tokens[k].type != TT.KEYWORD or tokens[k].value != "function":
        return None
    p1 = _skip_ws(tokens, k + 1)
    if p1 >= n or tokens[p1].type != TT.OP or tokens[p1].value != "(":
        return None
    p2 = _skip_ws(tokens, p1 + 1)
    if p2 >= n or tokens[p2].type != TT.OP or tokens[p2].value != ")":
        return None

    body_start = p2 + 1
    body_end, has_return, leaks = _scan_body(tokens, body_start)
    if body_end < 0 or has_return:
        return None
    close = _find_close_paren(tokens, body_end + 1)
    if close < 0:
        return None
    after = _skip_ws(tokens, close + 1)
    if after < n and (
        (tokens[after].type == TT.OP and tokens[after].value in _CONTINUATION_OPS)
        or tokens[after].type in (TT.STRING, TT.LONGSTRING)
    ):
        return None  # `pcall(...)()` / `pcall(...).x` uses the result

    pos = tokens[i].pos
    repl: List[Token] = []
    if leaks:
        repl += [Token(TT.KEYWORD, "do", pos), Token(TT.SPACE, " ", pos)]
    repl += tokens[body_start:body_end]
    if leaks:
        repl += [Token(TT.SPACE, " ", pos), Token(TT.KEYWORD, "end", pos)]
    repl.append(Token(TT.NEWLINE, "\n", pos))
    return repl, close + 1


def unwrap_pcall(source: str) -> Tuple[str, int]:
    """
    Make pcall/xpcall use safe on Stormworks.

    * `pcall(function() ... end)` as a statement is replaced by its body.
    * Any other use (`local ok = pcall(...)`, `if pcall(f) then`, a body
      that returns, `pcall(fn, arg)`) keeps the call and gets a small local
      shim that calls the function directly and returns `true, ...`.
    """
    tokens = tokenize(source)
    out: List[Token] = []
    i = 0
    unwrapped = 0
    needs_shim = set()
    n = len(tokens)

    while i < n:
        tok = tokens[i]
        if tok.type == TT.EOF:
            break
        if tok.type != TT.NAME or tok.value not in ("pcall", "xpcall") or not _is_global_ref(tokens, i):
            out.append(tok)
            i += 1
            continue

        result = _try_unwrap(tokens, i)
        if result is not None:
            repl, i = result
            out.extend(repl)
            unwrapped += 1
            continue

        needs_shim.add(tok.value)
        out.append(tok)
        i += 1

    shims = "".join(
        _SHIMS[name] for name in ("pcall", "xpcall")
        if name in needs_shim and not _user_defines(tokens, name)
    )
    if unwrapped == 0 and not shims:
        return source, 0
    return shims + tokens_to_source(out), unwrapped + len(needs_shim)
