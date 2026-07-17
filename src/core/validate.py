"""
Post-minify semantic validation.

Flags undefined globals and renamed Stormworks API properties so the CLI/GUI
do not report size-only [OK] when the output would crash in-game.
"""

from __future__ import annotations
from typing import List

from .lexer import Token, TT, SW_GLOBALS, SW_API_PROPERTIES, LUA_KEYWORDS, tokenize
from .linter import lint_script

# Engine-owned tables with arbitrary user keys — not SW API property surfaces.
_SW_USER_DATA_TABLES = frozenset({"g_savedata"})


def _check_parse(source: str) -> List[str]:
    """luaparser must accept minified output as valid Lua syntax."""
    try:
        from luaparser import ast as luast
        luast.parse(source)
    except Exception as e:
        return [f"Parse error: {e}"]
    return []


def validate_minified(source: str) -> List[str]:
    """
    Validate minified Lua for semantic corruption.

    Returns a list of error messages (empty = OK).
    """
    errors: List[str] = []

    errors.extend(_check_parse(source))

    # Reuse undefined-global detection from the linter
    try:
        errors.extend(lint_script(source))
    except Exception as e:
        errors.append(f"Validation error: {e}")
        return _dedup(errors)

    # Additionally: SW_GLOBALS.receiver must use a known API property name
    try:
        tokens = tokenize(source)
    except Exception as e:
        errors.append(f"Tokenization error during validation: {e}")
        return _dedup(errors)

    n = len(tokens)
    for i, tok in enumerate(tokens):
        if tok.type != TT.NAME:
            continue

        prev_i = i - 1
        while prev_i >= 0 and tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            prev_i -= 1
        if prev_i < 0 or tokens[prev_i].type != TT.OP or tokens[prev_i].value not in (".", ":"):
            continue

        recv_i = prev_i - 1
        while recv_i >= 0 and tokens[recv_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            recv_i -= 1
        if recv_i < 0 or tokens[recv_i].type != TT.NAME:
            continue

        recv = tokens[recv_i].value
        prop = tok.value
        if (
            recv in SW_GLOBALS
            and recv not in _SW_USER_DATA_TABLES
            and prop not in SW_API_PROPERTIES
            and prop not in LUA_KEYWORDS
        ):
            line_no = source.count("\n", 0, tok.pos) + 1
            errors.append(
                f"Line {line_no}: Unknown or renamed API property '{recv}.{prop}'. "
                f"This may cause a nil-field crash in Stormworks."
            )

    # Deduplicate while preserving order
    return _dedup(errors)


def _dedup(errors: List[str]) -> List[str]:
    seen = set()
    dedup: List[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            dedup.append(err)
    return dedup
