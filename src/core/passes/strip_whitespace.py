"""
Whitespace collapsing pass.
Removes or minimises spaces/newlines while keeping the Lua token stream valid.
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

# Keywords that continue / close a block mid-construct — never force ';' before these
# after `)` / `]` (e.g. `if(x)then`, `(a)and(b)`, `for i=1,n do`).
_BLOCK_CONTINUE_KEYWORDS = frozenset({
    "else", "elseif", "until", "then", "do", "in",
    "and", "or", "not",
})

# New statement (or function-body `return`/`end`) — Stormworks rejects `)local` / `)if`
# without ';' even though stock Lua often accepts keyword adjacency.
_STMT_START_KEYWORDS = frozenset({
    "local", "while", "repeat", "if", "for", "function", "goto",
    "break", "return", "end",
})

# Expression value keywords — `nil a` / `false local` need ';' (space is illegal).
_VALUE_KEYWORDS = frozenset({"true", "false", "nil"})


def _needs_separator(left: Token, right: Token) -> Optional[str]:
    """
    Return the separator required between two adjacent non-ws tokens:
      ' '  — keyword / identifier spacing
      ';'  — statement boundary (space is not enough for Stormworks Lua)
      None — safe to glue
    """
    # ── Keyword / identifier spacing (must stay spaces) ──────────────────────
    if left.type == TT.KEYWORD and left.value in ("not", "and", "or", "return"):
        if right.type in _ID_LIKE or (
            right.type == TT.OP and right.value in ("(", "-", "~", "#")
        ):
            return " "
        if left.value == "return" and right.type in (TT.STRING, TT.LONGSTRING, TT.NUMBER):
            return " "

    if right.type == TT.KEYWORD and right.value in ("and", "or", "not"):
        if left.type in _ID_LIKE:
            return " "

    if left.type == TT.KEYWORD and left.value in (
        "local", "function", "goto", "for", "while", "if", "elseif", "until",
    ):
        if right.type in _ID_LIKE:
            return " "

    # `AA,AB,AC=true,false,nil aH=...` — space after nil/true/false is not a stmt break.
    if left.type == TT.KEYWORD and left.value in _VALUE_KEYWORDS:
        if right.type == TT.NAME:
            return ";"
        if right.type == TT.KEYWORD and right.value in _STMT_START_KEYWORDS:
            return ";"
        if right.type in (TT.STRING, TT.LONGSTRING):
            return ";"
        if right.type == TT.OP and right.value in ("(", "{"):
            return ";"

    if left.type == TT.KEYWORD and right.type == TT.KEYWORD:
        # `end local` / `end if` need a statement break for Stormworks.
        if left.value == "end" and right.value in _STMT_START_KEYWORDS:
            return ";"
        return " "

    # NAME/NUMBER before block-continue: `1 end` is wrong — use ';' for stmt starts,
    # space for `x then` / `1 do` style continuations.
    if left.type in (TT.NAME, TT.NUMBER) and right.type == TT.KEYWORD:
        if right.value in _BLOCK_CONTINUE_KEYWORDS:
            return " "
        if right.value in _STMT_START_KEYWORDS:
            return ";"

    # ── Statement boundaries — semicolon (space is illegal / ambiguous) ──────
    # `o.E=AB E[x]=AA` — space still errors; need `AB;E`
    if left.type in (TT.NAME, TT.NUMBER) and right.type == TT.NAME:
        return ";"

    # `)f`, `)local`, `)if`, `ag()for`, `]if`, `}{`, etc.
    if left.type == TT.OP and left.value in (")", "]", "}"):
        if right.type == TT.NAME:
            return ";"
        if right.type in (TT.STRING, TT.LONGSTRING):
            return ";"
        if right.type == TT.OP and right.value in ("(", "{"):
            return ";"
        if right.type == TT.KEYWORD and right.value in _STMT_START_KEYWORDS:
            return ";"

    if left.type in (TT.STRING, TT.LONGSTRING):
        if right.type == TT.NAME:
            return ";"
        if right.type in (TT.STRING, TT.LONGSTRING):
            return ";"
        if right.type == TT.OP and right.value in ("(", "{"):
            return ";"
        if right.type == TT.KEYWORD and right.value in _STMT_START_KEYWORDS:
            return ";"

    # Fallback: two ID-like tokens that still need a space (e.g. keyword edge cases)
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
            # Prefer real separators over a collapsed space when required.
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
            # Newline already acts as a statement break; only insert space/'; when glued.
            prev = non_ws[i - 1]
            sep = _needs_separator(prev, tok)
            if sep == " ":
                out.append(Token(TT.SPACE, " ", tok.pos))
                chars_saved -= 1
            elif sep == ";":
                # Prefer newline over semicolon when we are about to break structurally;
                # otherwise insert ';' so `)name` cannot glue on the same line.
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
