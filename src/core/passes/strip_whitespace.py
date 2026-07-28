"""
Whitespace collapsing pass.
Removes or minimises spaces/newlines while keeping the Lua token stream valid.

Separator contract (Lua 5.3 grammar):
  * `;` only when the left token ends a value/statement AND the right token can
    start a new value/statement that Lua would otherwise mis-parse as a
    continuation of the left (call chain, string call, or pure gibberish).
  * ` ` (space) when the two tokens merely need to be separated so they do not
    merge into a different token (`foo bar`, `a then`, `1 do`).
  * `None` when the pair is unambiguous and can glue safely (`)local`, `]end`,
    `)then`, `"a"("b")` handled by Lua's call syntax).

Statement-level keywords (`local`, `if`, `for`, `while`, `function`, `repeat`,
`return`, `end`, `break`, `goto`, `do`) always start a fresh statement context —
they can glue after `)`, `]`, `}`, or a string without any separator.
"""

from typing import List, Literal, Optional
from ..lexer import Token, TT

MultilineMode = Literal["singleline", "statements", "preserve"]

# Token types that are identifier-like (need a space between two of them)
_ID_LIKE = frozenset({TT.NAME, TT.KEYWORD, TT.NUMBER})

_STRUCT_BREAK_AFTER = frozenset({
    "end", "else", "elseif", "then", "do", "repeat",
})

_STRUCT_BREAK_BEFORE = frozenset({"else", "elseif", "until"})

# Keywords that continue / close a block mid-construct — these continue the
# current construct, so the left token is *not* ending a value for them.
_BLOCK_CONTINUE_KEYWORDS = frozenset({
    "else", "elseif", "until", "then", "do", "in",
    "and", "or", "not",
})

# Statement-starting keywords that can begin a new Lua statement after a value
# without needing `;` — Lua's grammar already starts a new statement there.
# Note: `end`/`return` close the current block, so they are handled via the
# keyword-keyword rule rather than needing `;` after a value.
_STMT_KEYWORDS = frozenset({
    "local", "if", "for", "while", "function", "repeat",
    "break", "goto", "do",
})

# Literal value keywords — `nil a` / `true x` / `false {` are syntax errors.
_VALUE_KEYWORDS = frozenset({"true", "false", "nil"})

# Tokens that, when preceded by a value-ending token, Lua would parse as a
# continuation of the same expression (function call, index, string call).
# These are the only pairs that require a real `;` statement break.
_VALUE_CONTINUATION_TOKENS = frozenset({"(", "{"})


def _is_value_end(tok: Token) -> bool:
    """True when `tok` can legally terminate a value expression."""
    if tok.type == TT.NAME:
        return True
    if tok.type == TT.NUMBER:
        return True
    if tok.type in (TT.STRING, TT.LONGSTRING):
        return True
    if tok.type == TT.OP and tok.value in (")", "]", "}"):
        return True
    if tok.type == TT.KEYWORD and tok.value in _VALUE_KEYWORDS:
        return True
    return False


def _needs_separator(left: Token, right: Token) -> Optional[str]:
    """
    Return the separator required between two adjacent non-ws tokens:
      ' '  — keyword / identifier spacing
      ';'  — statement boundary (space is not enough to disambiguate)
      None — safe to glue
    """
    # ── Semicolon rules ──────────────────────────────────────────────────────
    # `)name` / `]name` / `}name` — a name cannot follow a closing token in an
    # expression (it would be a call argument list without an operator), so
    # this is always a statement boundary and space alone is not enough for
    # Stormworks.
    if left.type == TT.OP and left.value in (")", "]", "}") and right.type == TT.NAME:
        return ";"

    # `a b`, `1 x`, `true nil` — two identifier-like tokens where a space would
    # still parse as gibberish; `;` is the only safe statement break.
    if left.type == TT.NAME and right.type == TT.NAME:
        return ";"
    if left.type == TT.NUMBER and right.type == TT.NAME:
        return ";"
    if left.type == TT.KEYWORD and left.value in _VALUE_KEYWORDS:
        if right.type in (TT.NAME, TT.NUMBER):
            return ";"

    # ── Space rules: tokens must not merge into a single token ────────────────
    # `not`/`and`/`or`/`return` must be separated from what follows.
    if left.type == TT.KEYWORD and left.value in ("not", "and", "or", "return"):
        if right.type in _ID_LIKE or (
            right.type == TT.OP and right.value in ("(", "-", "~", "#")
        ):
            return " "
        if left.value == "return" and right.type in (TT.STRING, TT.LONGSTRING, TT.NUMBER):
            return " "

    # `x and`, `1 or`, `foo not` — right-hand keyword must not merge with left name/number.
    if right.type == TT.KEYWORD and right.value in ("and", "or", "not"):
        if left.type in _ID_LIKE:
            return " "

    # `local x`, `function f`, `for i`, `if a`, `while x`, `until n` — keywords
    # taking a name/expression must not glue to it.
    if left.type == TT.KEYWORD and left.value in (
        "local", "function", "goto", "for", "while", "if", "elseif", "until",
    ):
        if right.type in _ID_LIKE:
            return " "

    # Value-end followed by a block-continue keyword — space is enough
    # (`foo then`, `1 do`, `(a) and (b)`).
    if _is_value_end(left) and right.type == TT.KEYWORD and right.value in _BLOCK_CONTINUE_KEYWORDS:
        return " "

    # Two keywords — `end then` etc. need separation so they don't merge.
    if left.type == TT.KEYWORD and right.type == TT.KEYWORD:
        return " "

    # Fallback: any two identifier-like tokens still need a space.
    if left.type in _ID_LIKE and right.type in _ID_LIKE:
        return " "

    return None


def _is_top_level_function(tokens: List[Token], idx: int) -> bool:
    """True for `function name` or `local function name` at statement start."""
    if idx >= len(tokens):
        return False
    if tokens[idx].type == TT.KEYWORD and tokens[idx].value == "function":
        return True
    if (
        tokens[idx].type == TT.KEYWORD
        and tokens[idx].value == "local"
        and idx + 1 < len(tokens)
        and tokens[idx + 1].type == TT.KEYWORD
        and tokens[idx + 1].value == "function"
    ):
        return True
    return False


def _should_break_after(tokens: List[Token], idx: int, depth: int) -> bool:
    tok = tokens[idx]
    if tok.type == TT.KEYWORD:
        if tok.value in _STRUCT_BREAK_AFTER:
            return True
        if tok.value == "function" and depth == 0 and _is_top_level_function(tokens, idx):
            return True
        if tok.value == "local" and depth == 0 and _is_top_level_function(tokens, idx):
            return True
    if depth == 0 and tok.type == TT.OP and tok.value == ";":
        return True
    return False


def _should_break_before(tokens: List[Token], idx: int) -> bool:
    tok = tokens[idx]
    if tok.type == TT.KEYWORD and tok.value in _STRUCT_BREAK_BEFORE:
        return True
    return False


def _emit_separator(out: List[Token], left: Token, right: Token, chars_saved: int) -> int:
    sep = _needs_separator(left, right)
    if sep is None:
        return chars_saved
    out.append(Token(TT.OP if sep == ";" else TT.SPACE, sep, right.pos))
    return chars_saved - len(sep)


def _strip_preserve(tokens: List[Token]) -> tuple[List[Token], int]:
    """Keep source newlines; collapse horizontal whitespace only."""
    chars_saved = 0
    out: List[Token] = []
    pending_space = False

    for tok in tokens:
        if tok.type == TT.EOF:
            continue
        if tok.type == TT.SPACE:
            chars_saved += len(tok.value)
            pending_space = True
            continue
        if tok.type == TT.NEWLINE:
            chars_saved += len(tok.value)
            if out and out[-1].type != TT.NEWLINE:
                out.append(Token(TT.NEWLINE, "\n", tok.pos))
            pending_space = False
            continue

        if out and out[-1].type != TT.NEWLINE:
            sep = _needs_separator(out[-1], tok)
            if sep == ";":
                out.append(Token(TT.OP, ";", tok.pos))
                chars_saved -= 1
            elif sep == " " and pending_space:
                out.append(Token(TT.SPACE, " ", tok.pos))
                chars_saved -= 1
            elif sep == " ":
                out.append(Token(TT.SPACE, " ", tok.pos))
                chars_saved -= 1
        pending_space = False
        out.append(tok)

    return out, chars_saved


def _strip_statements(tokens: List[Token]) -> tuple[List[Token], int]:
    """One statement per line after structural boundaries."""
    non_ws = [
        t for t in tokens
        if t.type not in (TT.SPACE, TT.NEWLINE) and t.type != TT.EOF
    ]
    chars_saved = sum(
        len(t.value) for t in tokens
        if t.type in (TT.SPACE, TT.NEWLINE)
    )

    out: List[Token] = []
    depth = 0

    for i, tok in enumerate(non_ws):
        if _should_break_before(non_ws, i) and out and out[-1].type != TT.NEWLINE:
            out.append(Token(TT.NEWLINE, "\n", tok.pos))
            chars_saved -= 1

        if i > 0 and out and out[-1].type != TT.NEWLINE:
            prev = non_ws[i - 1]
            sep = _needs_separator(prev, tok)
            if sep == " ":
                out.append(Token(TT.SPACE, " ", tok.pos))
                chars_saved -= 1
            elif sep == ";":
                out.append(Token(TT.OP, ";", tok.pos))
                chars_saved -= 1

        out.append(tok)

        if tok.type == TT.KEYWORD and tok.value in ("function", "if", "for", "while", "repeat", "do"):
            if tok.value != "do" or (i > 0 and non_ws[i - 1].type == TT.KEYWORD and non_ws[i - 1].value in ("while", "for")):
                if tok.value in ("function", "if", "for", "while", "repeat"):
                    depth += 1
                elif tok.value == "do":
                    depth += 1
        elif tok.type == TT.KEYWORD and tok.value == "end":
            depth = max(0, depth - 1)
        elif tok.type == TT.KEYWORD and tok.value == "until":
            depth = max(0, depth - 1)

        if _should_break_after(non_ws, i, depth) and i + 1 < len(non_ws):
            out.append(Token(TT.NEWLINE, "\n", tok.pos))
            chars_saved -= 1

    return out, chars_saved


def _strip_singleline(tokens: List[Token]) -> tuple[List[Token], int]:
    """Collapse to one line, inserting spaces or semicolons where Lua requires them."""
    non_ws = [
        t for t in tokens
        if t.type not in (TT.SPACE, TT.NEWLINE) and t.type != TT.EOF
    ]
    chars_saved = sum(
        len(t.value) for t in tokens
        if t.type in (TT.SPACE, TT.NEWLINE)
    )

    out: List[Token] = []
    for i, tok in enumerate(non_ws):
        if i > 0:
            chars_saved = _emit_separator(out, non_ws[i - 1], tok, chars_saved)
        out.append(tok)

    return out, chars_saved


def strip_whitespace(
    tokens: List[Token],
    mode: MultilineMode = "singleline",
) -> tuple[List[Token], int]:
    """
    Remove/minimise whitespace.

    mode:
      - singleline: one line (default)
      - statements: line breaks after structural tokens
      - preserve: keep source newlines, collapse horizontal space only
    """
    if mode == "preserve":
        return _strip_preserve(tokens)
    if mode == "statements":
        return _strip_statements(tokens)
    return _strip_singleline(tokens)
