"""
Local variable renaming pass.
Uses the scope tree + name allocator to replace all local variable
names with the shortest possible safe identifiers.
"""

from typing import List, Dict, Tuple, Set
from ..lexer import Token, TT, SW_GLOBALS, LUA_KEYWORDS
from ..scope import Scope, VarInfo, build_scope_tree
from ..renamer import assign_names


def rename_locals(tokens: List[Token], reserved_names: Set[str] = None, obfuscate: bool = False) -> Tuple[List[Token], int, Dict[str, str]]:
    """
    Perform scope-aware local variable renaming.

    Returns:
        new_tokens   — token list with renames applied
        count        — number of variables renamed
        name_map     — {original: new} mapping (for stats display)
    """
    if reserved_names is None:
        reserved_names = set()

    # Build scope tree
    root = build_scope_tree(tokens)

    # Assign shortest names
    count = assign_names(root, reserved_names, obfuscate)

    # Build a flat lookup: (scope_id, original_name) → new_name
    # Walk the scope tree to create per-token renames
    name_map: Dict[str, str] = {}
    _collect_map(root, name_map)

    if not name_map:
        return tokens, 0, {}

    # Apply renames: perform a second scope-aware pass
    # Build a stack-based lookup for the actual token stream
    new_tokens = _apply_renames(tokens, root)

    return new_tokens, count, name_map


def _collect_map(scope: Scope, out: Dict[str, str]):
    """Flatten scope tree into {original: new} — for display only (may collide)."""
    for vi in scope.locals.values():
        if vi.new_name and vi.new_name != vi.original_name:
            out[vi.original_name] = vi.new_name
    for child in scope.children:
        _collect_map(child, out)


def _apply_renames(tokens: List[Token], root: Scope) -> List[Token]:
    """
    Walk token stream, maintaining a scope stack to resolve the correct
    new_name for each NAME token.
    """
    # Build an index: token_idx → VarInfo for declarations
    decl_at: Dict[int, VarInfo] = {}
    _index_decls(root, decl_at)

    new_tokens = list(tokens)  # copy

    # Track scope open/close by token index (list-valued: multiple scopes may share an index).
    scope_start: Dict[int, List[Scope]] = {}
    scope_end: Dict[int, List[Scope]] = {}
    _index_scopes(root, scope_start, scope_end)

    # Second pass: replace NAME tokens using live scope stack
    current_scopes = [root]
    ctx_stack: List[str] = []

    for i, tok in enumerate(new_tokens):
        # Check if a child scope starts here
        if i in scope_start:
            for s in scope_start[i]:
                current_scopes.append(s)
                ctx_stack.append(s)
            
        if tok.type == TT.OP and tok.value == "{":
            ctx_stack.append("TABLE")
        elif tok.type == TT.OP and tok.value == "}":
            for k in range(len(ctx_stack)-1, -1, -1):
                if ctx_stack[k] == "TABLE":
                    ctx_stack.pop(k)
                    break

        if tok.type == TT.NAME:
            is_prop = False
            prev_i = i - 1
            while prev_i >= 0 and new_tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and new_tokens[prev_i].type == TT.OP and new_tokens[prev_i].value in (".", ":"):
                is_prop = True

            is_key = False
            if not is_prop and ctx_stack and ctx_stack[-1] == "TABLE":
                next_i = i + 1
                n = len(new_tokens)
                while next_i < n and new_tokens[next_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    next_i += 1
                if next_i < n and new_tokens[next_i].type == TT.OP and new_tokens[next_i].value == "=":
                    is_key = True

            if not is_prop and not is_key and not tok.is_global:
                resolved = _lookup_in_scopes(tok.value, current_scopes, i)
                if resolved and resolved.new_name and resolved.new_name != tok.value:
                    new_tokens[i] = Token(TT.NAME, resolved.new_name, tok.pos)

        # Check if scopes end here (pop all that share this end_idx)
        if i in scope_end:
            for s in scope_end[i]:
                if s in current_scopes:
                    current_scopes.remove(s)
                if s in ctx_stack:
                    ctx_stack.remove(s)

    return new_tokens


def _lookup_in_scopes(name: str, scope_stack: List[Scope], token_idx: int = -1) -> "VarInfo | None":
    """
    Search scope stack from innermost to outermost.
    
    CRITICAL: A local/parameter VarInfo is only valid if the current token index
    falls within the scope's range. This prevents a parameter like 'function foo(a,b,foo)'
    from incorrectly shadowing the global 'foo' at call sites in other functions.
    """
    for scope in reversed(scope_stack):
        if name in scope.locals:
            vi = scope.locals[name]
            # If a token index is provided, verify this scope actually covers it.
            # For parameters (is_param=True), their scope must contain token_idx.
            # For regular locals, their declaration must precede token_idx.
            if token_idx >= 0:
                # The variable must be declared BEFORE this usage
                if vi.declaration_idx > token_idx:
                    continue
                # The scope must still be open at this token position
                if scope.end_idx > 0 and token_idx > scope.end_idx:
                    continue
            return vi
    return None


def _index_decls(scope: Scope, out: Dict[int, "VarInfo"]):
    for vi in scope.locals.values():
        out[vi.declaration_idx] = vi
    for child in scope.children:
        _index_decls(child, out)


def _index_scopes(scope: Scope, start: Dict[int, List[Scope]], end: Dict[int, List[Scope]]):
    """Index scopes by start/end token index. Multiple scopes may share an index."""
    start.setdefault(scope.start_idx, []).append(scope)
    end.setdefault(scope.end_idx, []).append(scope)
    for child in scope.children:
        _index_scopes(child, start, end)
