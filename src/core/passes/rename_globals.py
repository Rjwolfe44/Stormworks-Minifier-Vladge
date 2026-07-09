"""
Global variable and property renaming pass.
Renames standalone globals, user table keys, and user property accesses.
Stormworks/Lua API properties (map.mapToScreen, math.pi, etc.) are never renamed.
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import Counter
from ..lexer import Token, TT, SW_GLOBALS, SW_API_PROPERTIES, LUA_KEYWORDS
from ..scope import Scope, build_scope_tree


def _receiver_name(tokens: List[Token], dot_idx: int) -> Optional[str]:
    """Return the NAME immediately before a '.' or ':' at dot_idx, or None."""
    j = dot_idx - 1
    while j >= 0 and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
        j -= 1
    if j >= 0 and tokens[j].type == TT.NAME:
        return tokens[j].value
    return None


def _pop_scopes_at(i: int, scope_end: Dict[int, List[Scope]], current_scopes: List[Scope], ctx_stack: List):
    if i not in scope_end:
        return
    for s in scope_end[i]:
        if s in current_scopes:
            current_scopes.remove(s)
        if s in ctx_stack:
            ctx_stack.remove(s)


def _is_protected_prop_or_key(tokens: List[Token], tok: Token, is_prop: bool, is_key: bool, prev_i: int) -> bool:
    """True if this name must not be renamed (SW/Lua API surface)."""
    if is_prop:
        recv = _receiver_name(tokens, prev_i)
        # Default-deny: never rename anything after a known SW/Lua global table
        if recv in SW_GLOBALS:
            return True
        # Also protect known API member names even on user receivers (e.g. :len())
        if tok.value in SW_API_PROPERTIES:
            return True
    if is_key and tok.value in SW_API_PROPERTIES:
        # Keep { len = function... } matching :len() calls
        return True
    return False


def rename_globals(tokens: List[Token], existing_globals: set = None, obfuscate: bool = False) -> Tuple[List[Token], int, Dict[str, str], set]:
    """
    Renames standalone globals, user table keys, and user property accesses.
    Returns: (new_tokens, rename_count, name_map, allocated_names)
    """
    if existing_globals is None:
        allocated_names = set()
    else:
        allocated_names = set(existing_globals)

    whitelist = SW_GLOBALS | LUA_KEYWORDS

    root = build_scope_tree(tokens)

    from .rename_locals import _index_scopes, _lookup_in_scopes
    scope_start: Dict[int, List[Scope]] = {}
    scope_end: Dict[int, List[Scope]] = {}
    _index_scopes(root, scope_start, scope_end)

    current_scopes = [root]
    ctx_stack: List = []

    freq_map: Counter = Counter()
    standalone_globals: Set[str] = set()
    n = len(tokens)

    for i, tok in enumerate(tokens):
        if i in scope_start:
            for s in scope_start[i]:
                current_scopes.append(s)
                ctx_stack.append(s)

        if tok.type == TT.OP and tok.value == "{":
            ctx_stack.append("TABLE")
        elif tok.type == TT.OP and tok.value == "}":
            for k in range(len(ctx_stack) - 1, -1, -1):
                if ctx_stack[k] == "TABLE":
                    ctx_stack.pop(k)
                    break

        if tok.type == TT.NAME and tok.value not in whitelist:
            is_prop = False
            prev_i = i - 1
            while prev_i >= 0 and tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and tokens[prev_i].type == TT.OP and tokens[prev_i].value in (".", ":"):
                is_prop = True

            is_key = False
            if not is_prop and ctx_stack and ctx_stack[-1] == "TABLE":
                next_i = i + 1
                while next_i < n and tokens[next_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    next_i += 1
                if next_i < n and tokens[next_i].type == TT.OP and tokens[next_i].value == "=":
                    is_key = True

            if _is_protected_prop_or_key(tokens, tok, is_prop, is_key, prev_i):
                _pop_scopes_at(i, scope_end, current_scopes, ctx_stack)
                continue

            resolved_local = None
            if not is_prop and not is_key:
                resolved_local = _lookup_in_scopes(tok.value, current_scopes, i)

            if is_prop or is_key or not resolved_local:
                freq_map[tok.value] += 1
                if not is_prop and not is_key:
                    standalone_globals.add(tok.value)

        _pop_scopes_at(i, scope_end, current_scopes, ctx_stack)

    from ..renamer import _safe_names, _obfuscated_names
    name_gen = _obfuscated_names() if obfuscate else _safe_names()

    name_map: Dict[str, str] = {}
    internal_allocated = set(allocated_names)

    for orig_name, _ in freq_map.most_common():
        while True:
            short_name = next(name_gen)
            if short_name not in internal_allocated and short_name not in whitelist:
                name_map[orig_name] = short_name
                internal_allocated.add(short_name)
                if orig_name in standalone_globals:
                    allocated_names.add(short_name)
                break

    if not name_map:
        return tokens, 0, {}, allocated_names

    new_tokens = list(tokens)
    current_scopes = [root]
    ctx_stack = []

    for i, tok in enumerate(new_tokens):
        if i in scope_start:
            for s in scope_start[i]:
                current_scopes.append(s)
                ctx_stack.append(s)

        if tok.type == TT.OP and tok.value == "{":
            ctx_stack.append("TABLE")
        elif tok.type == TT.OP and tok.value == "}":
            for k in range(len(ctx_stack) - 1, -1, -1):
                if ctx_stack[k] == "TABLE":
                    ctx_stack.pop(k)
                    break

        if tok.type == TT.NAME and tok.value in name_map:
            is_prop = False
            prev_i = i - 1
            while prev_i >= 0 and new_tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and new_tokens[prev_i].type == TT.OP and new_tokens[prev_i].value in (".", ":"):
                is_prop = True

            is_key = False
            if not is_prop and ctx_stack and ctx_stack[-1] == "TABLE":
                next_i = i + 1
                while next_i < n and new_tokens[next_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    next_i += 1
                if next_i < n and new_tokens[next_i].type == TT.OP and new_tokens[next_i].value == "=":
                    is_key = True

            if _is_protected_prop_or_key(new_tokens, tok, is_prop, is_key, prev_i):
                _pop_scopes_at(i, scope_end, current_scopes, ctx_stack)
                continue

            resolved_local = None
            if not is_prop and not is_key:
                resolved_local = _lookup_in_scopes(tok.value, current_scopes, i)

            if is_prop or is_key or not resolved_local:
                new_tokens[i] = Token(TT.NAME, name_map[tok.value], tok.pos, is_global=True)

        _pop_scopes_at(i, scope_end, current_scopes, ctx_stack)

    return new_tokens, len(name_map), name_map, allocated_names
