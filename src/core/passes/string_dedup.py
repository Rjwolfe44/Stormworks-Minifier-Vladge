"""
String literal deduplication pass (Level 4 - Nuclear).
Finds string literals that appear 3+ times and replaces them
with a short local variable, prepended to the script.
"""

from __future__ import annotations
from collections import Counter
from typing import List, Dict, Tuple
from ..lexer import Token, TT


def _alias_gen():
    import string
    for c in string.ascii_lowercase:
        yield f"_s{c}"
    for c1 in string.ascii_lowercase:
        for c2 in string.ascii_lowercase:
            yield f"_s{c1}{c2}"


def dedup_strings(tokens: List[Token]) -> Tuple[List[Token], int, Dict[str, str]]:
    """
    Find repeated string literals and replace them with aliases.
    Only deduplicate strings used 3+ times where net saving is positive.

    Returns:
        new_tokens   — modified token list
        chars_saved  — net characters saved
        alias_map    — {string_literal: alias_name}
    """
    # Count string literal occurrences
    str_counts: Counter = Counter()
    for tok in tokens:
        if tok.type == TT.STRING:
            str_counts[tok.value] += 1

    gen = _alias_gen()
    alias_map: Dict[str, str] = {}
    declarations: List[Token] = []

    for literal, count in str_counts.most_common():
        inner = literal.strip("\"'")
        min_count = 2 if len(inner) >= 12 else 3
        if count < min_count:
            continue
        alias = next(gen)
        decl_cost = len(f"local {alias}={literal} ")
        savings = (len(literal) - len(alias)) * count
        if savings > decl_cost:
            alias_map[literal] = alias

    if not alias_map:
        return tokens, 0, {}

    # Build declaration tokens to prepend
    prefix_tokens: List[Token] = []
    for literal, alias in alias_map.items():
        # local _sX=<literal>
        from ..lexer import LUA_KEYWORDS
        prefix_tokens.extend([
            Token(TT.KEYWORD, "local", 0),
            Token(TT.SPACE, " ", 0),
            Token(TT.NAME, alias, 0),
            Token(TT.OP, "=", 0),
            Token(TT.STRING, literal, 0),
            Token(TT.SPACE, " ", 0),
        ])

    # Replace string occurrences in original tokens
    new_tokens: List[Token] = list(prefix_tokens)
    chars_saved = 0
    for tok in tokens:
        if tok.type == TT.STRING and tok.value in alias_map:
            alias = alias_map[tok.value]
            chars_saved += len(tok.value) - len(alias)
            new_tokens.append(Token(TT.NAME, alias, tok.pos))
        else:
            new_tokens.append(tok)

    # Subtract declaration overhead
    chars_saved -= sum(len(f"local {a}={l} ") for l, a in alias_map.items())

    return new_tokens, max(0, chars_saved), alias_map
