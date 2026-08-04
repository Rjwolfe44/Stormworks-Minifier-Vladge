"""
Post-minify semantic validation.

Flags undefined globals and renamed Stormworks API properties so the CLI/GUI
do not report size-only [OK] when the output would crash in-game.
"""

from __future__ import annotations
from typing import List

from .lexer import Token, TT, SW_GLOBALS, SW_API_PROPERTIES, LUA_KEYWORDS, LUA_METAMETHODS, tokenize
from .linter import lint_script

# Engine-owned tables with arbitrary user keys — not SW API property surfaces.
_SW_USER_DATA_TABLES = frozenset({"g_savedata"})
# Receivers that are Lua OO / metatable conventions, not Stormworks API tables.
_SW_META_RECEIVERS = frozenset({"self"})
# Properties that are always legal on SW_GLOBALS receivers (stdlib + metamethods).
_ALLOWED_PROPS = SW_API_PROPERTIES | LUA_METAMETHODS | LUA_KEYWORDS


def _check_parse(source: str) -> List[str]:
    """luaparser must accept minified output as valid Lua syntax."""
    try:
        from luaparser import ast as luast
        luast.parse(source)
    except Exception as e:
        return [f"Parse error: {e}"]
    return []


def _check_unresolved_requires(source: str) -> List[str]:
    """
    Stormworks microcontroller Lua has no working require() — leftover requires
    after bundling mean the module was not inlined and will be nil at runtime.
    """
    import re
    errors: List[str] = []
    for m in re.finditer(
        r"""\brequire\s*(?:\(\s*(['"])([^'"]+)\1\s*\)|(['"])([^'"]+)\3)""",
        source,
    ):
        mod = m.group(2) or m.group(4) or "?"
        line_no = source.count("\n", 0, m.start()) + 1
        errors.append(
            f"Line {line_no}: Unresolved require('{mod}') — "
            f"will be nil in Stormworks (module was not bundled)."
        )
    return errors


def validate_minified(source: str, *, addon: bool = False) -> List[str]:
    """
    Validate minified Lua for semantic corruption.

    Returns a list of error messages (empty = OK).
    addon=True skips the leftover-require check (mission scripts may keep require).
    """
    errors: List[str] = []

    errors.extend(_check_parse(source))

    # Reuse undefined-global detection from the linter
    try:
        errors.extend(lint_script(source))
    except Exception as e:
        errors.append(f"Validation error: {e}")
        return _dedup(errors)

    if not addon:
        errors.extend(_check_unresolved_requires(source))

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
        if recv in _SW_META_RECEIVERS:
            continue
        if (
            recv in SW_GLOBALS
            and recv not in _SW_USER_DATA_TABLES
            and prop not in _ALLOWED_PROPS
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
