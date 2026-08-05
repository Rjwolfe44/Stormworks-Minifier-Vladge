"""Shared post-minify verification helpers for tests and pipeline."""

from __future__ import annotations
from typing import List, Tuple

from src.core.minifier import minify, MinifyStats
from src.core.validate import validate_minified


def check_parse(source: str) -> List[str]:
    """Return parse error strings (empty if luaparser accepts the source)."""
    try:
        from luaparser import ast as luast
        luast.parse(source)
    except Exception as e:
        return [f"Parse error: {e}"]
    return []


def verify_minified(source: str, *, parse: bool = True, semantic: bool = True) -> List[str]:
    """Full static verification: optional parse + semantic checks."""
    errors: List[str] = []
    if parse:
        errors.extend(check_parse(source))
    if semantic:
        errors.extend(validate_minified(source))
    seen = set()
    dedup: List[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            dedup.append(err)
    return dedup


def minify_and_verify(
    source: str,
    level: int = 4,
    root_dir: str | None = None,
    **minify_kw,
) -> Tuple[str, MinifyStats, List[str]]:
    """Minify then run full verification; returns (output, stats, errors)."""
    result, stats = minify(source, level=level, root_dir=root_dir, **minify_kw)
    errors = verify_minified(result)
    return result, stats, errors
