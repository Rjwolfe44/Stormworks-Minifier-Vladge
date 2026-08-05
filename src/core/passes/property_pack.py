"""
Property string packing (Level 3+).
Hoists repeated property.getNumber/getBool/PIN("…") string literals into a local table.
"""

from __future__ import annotations
import re
from collections import Counter
from typing import Dict, List, Tuple

from ..lexer import Token, tokenize, tokens_to_source

_PROP_METHODS = ("getNumber", "getBool", "getText", "getString", "getSwitch", "getToggle")

_PROP_PATTERN = re.compile(
    r'\bproperty\.(' + "|".join(_PROP_METHODS) + r')\(\s*(["\'])(.+?)\2\s*\)'
)


def _try_parse(code: str) -> bool:
    try:
        from luaparser import ast
        ast.parse(code)
        return True
    except Exception:
        return False


def pack_property_strings(source: str) -> Tuple[str, int]:
    """Replace repeated property/PIN string literals with _P.key when net shorter."""
    alias_names: List[str] = []
    for m in re.finditer(
        r'\b([A-Z][A-Za-z0-9_]{0,8})\s*=\s*property\.(?:' + "|".join(_PROP_METHODS) + r')\b',
        source,
    ):
        alias_names.append(m.group(1))

    str_counts: Counter = Counter()
    for m in _PROP_PATTERN.finditer(source):
        str_counts[m.group(3)] += 1
    for name in alias_names:
        pat = re.compile(rf'\b{re.escape(name)}\(\s*["\'](.+?)["\']\s*\)')
        for m in pat.finditer(source):
            str_counts[m.group(1)] += 1

    repeated = {s for s, c in str_counts.items() if c >= 2}
    if not repeated:
        return source, 0

    key_map: Dict[str, str] = {}
    chars = "abcdefghijklmnopqrstuvwxyz"
    for i, s in enumerate(sorted(repeated, key=len)):
        key_map[s] = chars[i] if i < 26 else f"p{i}"

    entries = ",".join(f'{k}="{v}"' for v, k in sorted(key_map.items(), key=lambda x: x[1]))
    decl = f"local _P={{{entries}}} "

    all_callers = list(alias_names) + [f"property.{m}" for m in _PROP_METHODS]
    new_source = source
    gross_saved = 0
    for s, k in key_map.items():
        for caller in all_callers:
            pat = re.compile(rf'\b{re.escape(caller)}\(\s*["\']{re.escape(s)}["\']\s*\)')
            repl = f"{caller}(_P.{k})"
            for m in pat.finditer(new_source):
                gross_saved += len(m.group(0)) - len(repl)
            new_source = pat.sub(repl, new_source)

    net_saved = gross_saved - len(decl)
    if net_saved <= 0:
        return source, 0

    candidate = decl + new_source
    if not _try_parse(candidate):
        return source, 0
    return candidate, net_saved


def pack_property_strings_tokens(tokens: List[Token]) -> Tuple[List[Token], int]:
    source = tokens_to_source(tokens)
    new_source, saved = pack_property_strings(source)
    if saved <= 0:
        return tokens, 0
    return tokenize(new_source), saved
