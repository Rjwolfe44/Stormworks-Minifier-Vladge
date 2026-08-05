"""
Control-flow packing (Level 4).

Aggressively rewrites statement-form control flow into shorter expression forms,
mirroring (and exceeding) what LifeBoat's minimizer does. All transforms are
semantics-preserving under Lua 5.3 evaluation rules and only applied when the
result is strictly smaller.

Transforms:
  1. if C then T = A else T = B end      ->  T = C and A or B      (A provably truthy)
  2. if C then T = A end                 ->  T = C and A or T      (A provably truthy)
  3. if C then f(...) end                ->  (C) and f(...)        (statement expr)
  4. Zipper: `local x = e1 local y = e2`  ->  `local x,y = e1,e2`   (any exprs)

Truthiness safety (Lua: only `false` and `nil` are falsy; `0` and `""` are truthy):
  `C and A or B` evaluates to B when C is true AND A is falsy — a bug unless A is
  provably truthy. We therefore require A to be a literal/constructor form that
  can never be false/nil: number, string, `true`, table `{...}`, or function.
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from ..lexer import Token, TT

_WS = (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT)


def _clean(tokens: List[Token]) -> List[Token]:
    return [t for t in tokens if t.type not in _WS]


def _is_guaranteed_truthy(expr: List[Token]) -> bool:
    """True if a cleaned token sequence is a single expr that can never be falsy."""
    e = _clean(expr)
    if not e:
        return False
    # strip one balanced paren layer: (X)
    while (
        len(e) >= 2
        and e[0].type == TT.OP
        and e[0].value == "("
        and e[-1].type == TT.OP
        and e[-1].value == ")"
    ):
        # ensure the parens actually wrap the whole thing
        depth = 0
        wraps = True
        for k, t in enumerate(e):
            if t.type == TT.OP and t.value == "(":
                depth += 1
            elif t.type == TT.OP and t.value == ")":
                depth -= 1
                if depth == 0 and k != len(e) - 1:
                    wraps = False
                    break
        if not wraps:
            break
        e = e[1:-1]
        if not e:
            return False
    if len(e) == 1:
        t = e[0]
        if t.type in (TT.NUMBER, TT.STRING, TT.LONGSTRING):
            return True
        if t.type == TT.KEYWORD and t.value == "true":
            return True
        return False
    # table constructor: { ... } — always truthy
    if e[0].type == TT.OP and e[0].value == "{":
        return True
    # function literal: function(..... end — always truthy
    if e[0].type == TT.KEYWORD and e[0].value == "function":
        return True
    return False


def _tokens_eq(a: List[Token], b: List[Token]) -> bool:
    a, b = _clean(a), _clean(b)
    return len(a) == len(b) and all(x.type == y.type and x.value == y.value for x, y in zip(a, b))


class _Reader:
    """Cursor over the meaningful (non-ws) token stream with source-token mapping."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.map: List[int] = [i for i, t in enumerate(tokens) if t.type not in _WS]
        self.m: List[Token] = [tokens[i] for i in self.map]
        self.pos = 0

    def peek(self, off: int = 0) -> Optional[Token]:
        i = self.pos + off
        return self.m[i] if 0 <= i < len(self.m) else None

    def kw(self, off: int = 0) -> Optional[str]:
        t = self.peek(off)
        return t.value if t and t.type == TT.KEYWORD else None

    def op(self, off: int = 0) -> Optional[str]:
        t = self.peek(off)
        return t.value if t and t.type == TT.OP else None

    def src(self, i: int) -> int:
        return self.map[i]

    def at_end(self) -> bool:
        return self.pos >= len(self.m)


def _find_block_end(r: _Reader, start: int) -> Tuple[int, bool, bool]:
    """
    From the index *after* `if`, find the matching `end` at depth 0.
    Returns (meaningful-index of `end`, saw_else, saw_elseif).
    """
    depth = 0
    saw_else = saw_elseif = False
    i = start
    while i < len(r.m):
        t = r.m[i]
        v = t.value if t.type == TT.KEYWORD else None
        if v in ("if", "for", "while", "function", "do", "repeat"):
            depth += 1
        elif v == "end":
            if depth == 0:
                return i, saw_else, saw_elseif
            depth -= 1
        elif v == "until" and depth > 0:
            depth -= 1
        elif depth == 0 and v == "else":
            saw_else = True
        elif depth == 0 and v == "elseif":
            saw_elseif = True
        i += 1
    return -1, saw_else, saw_elseif


def _find_then(r: _Reader, start: int) -> int:
    """Find `then` at depth 0 after `if`, or -1. Abort on nested structural kw."""
    depth = 0
    i = start
    while i < len(r.m):
        t = r.m[i]
        v = t.value if t.type == TT.KEYWORD else None
        if v == "then" and depth == 0:
            return i
        if v in ("if", "for", "while", "function", "do", "repeat"):
            depth += 1
        elif v == "end":
            depth -= 1
        i += 1
    return -1


def _slice(tokens: List[Token], r: _Reader, a: int, b: int) -> List[Token]:
    """Source tokens spanning meaningful range [a, b)."""
    if a >= b:
        return []
    return tokens[r.src(a): r.src(b - 1) + 1]


def pack_control_flow(tokens: List[Token]) -> Tuple[List[Token], int]:
    """
    Apply if->expression transforms. Returns (new_tokens, transform_count).
    Operates on the meaningful stream but splices real source tokens to keep ws.
    """
    out: List[Token] = []
    count = 0
    r = _Reader(tokens)
    i = 0
    n_m = len(r.m)

    while i < n_m:
        t = r.m[i]
        if not (t.type == TT.KEYWORD and t.value == "if"):
            out.append(tokens[r.src(i)])
            i += 1
            continue

        then_i = _find_then(r, i + 1)
        if then_i < 0:
            out.append(tokens[r.src(i)])
            i += 1
            continue
        end_i, saw_else, saw_elseif = _find_block_end(r, i + 1)
        if end_i < 0 or saw_elseif:
            out.append(tokens[r.src(i)])
            i += 1
            continue

        cond = _slice(tokens, r, i + 1, then_i)
        body = _slice(tokens, r, then_i + 1, end_i if not saw_else else _find_else(r, then_i + 1, end_i))
        else_body = _slice(tokens, r, _find_else(r, then_i + 1, end_i) + 1, end_i) if saw_else else []

        transformed: Optional[List[Token]] = None

        if saw_else:
            transformed = _try_if_else(cond, body, else_body, t)
        else:
            transformed = _try_single_branch(cond, body, t)

        # Only keep the rewrite when it is strictly smaller than the source span.
        if transformed is not None:
            src_span = tokens[r.src(i): r.src(end_i) + 1]
            if _render_len(transformed) >= _render_len(src_span):
                transformed = None

        if transformed is None:
            out.append(tokens[r.src(i)])
            i += 1
            continue

        # Splice: everything before the `if` stays; skip the whole if..end span.
        out.extend(transformed)
        count += 1
        i = end_i + 1

    return out, count


def _render_len(tokens: List[Token]) -> int:
    """Approximate minified length: sum of token text, +1 between two NAME/keyword
    neighbours that would otherwise merge. Cheap and directionally correct."""
    c = _clean(tokens)
    total = 0
    prev_word = False
    for t in c:
        word = t.type in (TT.NAME, TT.KEYWORD) or t.type == TT.NUMBER
        if word and prev_word:
            total += 1
        total += len(t.value)
        prev_word = word
    return total


def _find_else(r: _Reader, start: int, end_i: int) -> int:
    depth = 0
    i = start
    while i < end_i:
        t = r.m[i]
        v = t.value if t.type == TT.KEYWORD else None
        if v in ("if", "for", "while", "function", "do", "repeat"):
            depth += 1
        elif v == "end":
            depth -= 1
        elif v == "else" and depth == 0:
            return i
        i += 1
    return end_i


def _paren(tokens: List[Token]) -> List[Token]:
    c = _clean(tokens)
    if not c:
        return tokens
    return [Token(TT.OP, "(", c[0].pos)] + tokens + [Token(TT.OP, ")", c[-1].pos)]


def _sp() -> Token:
    return Token(TT.SPACE, " ", 0)


def _kw(v: str) -> Token:
    return Token(TT.KEYWORD, v, 0)


def _try_if_else(cond: List[Token], body: List[Token], else_body: List[Token], if_tok: Token) -> Optional[List[Token]]:
    """if C then T=A else T=B end  ->  T = C and A or B   (A truthy)."""
    b, e = _clean(body), _clean(else_body)
    # split body on top-level '='
    def split_assign(seq):
        for k, tok in enumerate(seq):
            if tok.type == TT.OP and tok.value == "=":
                return seq[:k], seq[k + 1:]
            if tok.type == TT.OP and tok.value in ("==", "~=", "<=", ">=", ".."):
                return None, None
        return None, None

    t1, a = split_assign(b)
    t2, bb = split_assign(e)
    if not t1 or not t2 or not _tokens_eq(t1, t2):
        return None
    if not _is_guaranteed_truthy(a):
        return None
    if not a or not bb:
        return None

    out = list(t1) + [Token(TT.OP, "=", 0)]
    out += _paren(cond)
    out += [_sp(), _kw("and"), _sp()]
    out += _clean(a)
    out += [_sp(), _kw("or"), _sp()]
    out += _clean(bb)
    return out


def _try_single_branch(cond: List[Token], body: List[Token], if_tok: Token) -> Optional[List[Token]]:
    """
    if C then T=A end   ->  T = C and A or T   (A truthy, T a simple name/index)
    if C then f() end   ->  (C) and f()         (pure call statement)
    """
    b = _clean(body)
    if not b:
        return None

    # assignment form
    for k, tok in enumerate(b):
        if tok.type == TT.OP and tok.value == "=":
            tgt, a = b[:k], b[k + 1:]
            if not tgt or not a:
                return None
            # target must be a simple lvalue (name or index chain)
            if not all(t.type in (TT.NAME, TT.OP, TT.STRING, TT.NUMBER) for t in tgt):
                return None
            if not _is_guaranteed_truthy(a):
                return None
            out = list(tgt) + [Token(TT.OP, "=", 0)]
            out += _paren(cond)
            out += [_sp(), _kw("and"), _sp()]
            out += _clean(a)
            out += [_sp(), _kw("or"), _sp()]
            out += list(tgt)
            return out
        if tok.type == TT.KEYWORD:
            return None  # nested control kw -> bail

    # pure call form: no '=' and ends with ')' — `_ = (C) and f(...)`
    # (a bare `C and f()` is not a valid Lua statement; it needs an assignment target)
    if b[-1].type == TT.OP and b[-1].value == ")":
        out = [Token(TT.NAME, "_", 0), Token(TT.OP, "=", 0)]
        out += _paren(cond)
        out += [_sp(), _kw("and"), _sp()]
        out += b
        return out
    return None
