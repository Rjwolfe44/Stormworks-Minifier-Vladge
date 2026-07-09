"""
Whitespace collapsing pass.
Removes or minimises spaces/newlines while keeping the Lua token stream valid.
"""

from typing import List, Literal
from ..lexer import Token, TT

MultilineMode = Literal["singleline", "statements", "preserve"]

# Token types that are identifier-like (need a space between two of them)
_ID_LIKE = frozenset({TT.NAME, TT.KEYWORD, TT.NUMBER})

_STRUCT_BREAK_AFTER = frozenset({
    "end", "else", "elseif", "then", "do", "repeat",
})

_STRUCT_BREAK_BEFORE = frozenset({"else", "elseif", "until"})


def _needs_space(left: Token, right: Token) -> bool:
    """Determine if a single space is required between two adjacent tokens."""
    if left.type in _ID_LIKE and right.type in _ID_LIKE:
        return True
    if left.type == TT.KEYWORD and left.value in ("not", "and", "or", "return"):
        if right.type in _ID_LIKE or (right.type == TT.OP and right.value in ("(", "-", "~", "#")):
            return True
    if right.type == TT.KEYWORD and right.value in ("and", "or", "not"):
        if left.type in _ID_LIKE:
            return True
    if left.type == TT.KEYWORD and left.value == "return":
        if right.type in _ID_LIKE or right.type in (TT.STRING, TT.LONGSTRING, TT.NUMBER):
            return True
    return False


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

        if pending_space and out and out[-1].type != TT.NEWLINE:
            if _needs_space(out[-1], tok):
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
            if _needs_space(non_ws[i - 1], tok):
                out.append(Token(TT.SPACE, " ", tok.pos))
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
    """Original behaviour: collapse to one line."""
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
        if i > 0 and _needs_space(non_ws[i - 1], tok):
            out.append(Token(TT.SPACE, " ", tok.pos))
            chars_saved -= 1
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
