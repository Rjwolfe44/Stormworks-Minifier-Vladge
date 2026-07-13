"""
Constant Inliner (Level 4).
Finds variables that are assigned exactly once to a constant literal
or global API path, and inlines that constant everywhere.
"""

from typing import List, Tuple, Dict, Set, Optional
from collections import defaultdict
from ..lexer import Token, TT, SW_GLOBALS
from ..scope import Scope, build_scope_tree


def _skip_ws(tokens: List[Token], idx: int) -> int:
    n = len(tokens)
    while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
        idx += 1
    return idx


def _is_name_path(val_tokens: List[Token]) -> bool:
    """True for a bare Name or Name.Name.Name path (valid prefixexp / var)."""
    if not val_tokens or val_tokens[0].type != TT.NAME:
        return False
    i = 1
    while i < len(val_tokens):
        if val_tokens[i].type == TT.OP and val_tokens[i].value == ".":
            i += 1
            if i >= len(val_tokens) or val_tokens[i].type != TT.NAME:
                return False
            i += 1
            continue
        return False
    return True


def _needs_inline_parens(val_tokens: List[Token], next_tok: Optional[Token]) -> bool:
    """
    Wrap inlined values when Lua requires a prefixexp.

    Bare string/number/bool/nil literals are NOT prefixexps, so
    ``s:sub(1,2)`` must become ``("hello"):sub(1,2)``, not ``"hello":sub(1,2)``.
    Same for ``.`` field access and ``[]`` indexing.
    """
    if not val_tokens:
        return False
    if val_tokens[0].type == TT.OP and val_tokens[0].value == "-":
        return True
    if next_tok is None or next_tok.type != TT.OP or next_tok.value not in (".", ":", "["):
        return False
    if _is_name_path(val_tokens):
        return False
    if (
        val_tokens[0].type == TT.OP
        and val_tokens[0].value == "("
        and val_tokens[-1].type == TT.OP
        and val_tokens[-1].value == ")"
    ):
        return False
    return True


def inline_constants(tokens: List[Token]) -> Tuple[List[Token], int]:
    root = build_scope_tree(tokens)
    
    # Track scopes
    scope_start: Dict[int, Scope] = {}
    scope_end: Dict[int, Scope] = {}
    
    def _index_scopes(s: Scope, st: dict, en: dict):
        if s.parent is not None:
            st[s.start_idx] = s
            en[s.end_idx] = s
        for child in s.children:
            _index_scopes(child, st, en)

    _index_scopes(root, scope_start, scope_end)
    
    def _lookup_in_scopes(name: str, scopes: List[Scope], current_idx: int):
        for s in reversed(scopes):
            vi = s.lookup(name)
            if vi and vi.scope == s and vi.declaration_idx <= current_idx:
                return vi
        return None

    current_scopes = [root]
    ctx_stack: List[str] = []
    
    n = len(tokens)
    
    # 1. Identify all assignments
    # We want to map: local_VarInfo -> number of assignments
    # and global_name -> number of assignments
    
    local_assign_count = defaultdict(int)
    global_assign_count = defaultdict(int)
    
    # We also need to map the "first" assignment value if it's a constant
    local_const_val = {}
    global_const_val = {}
    
    def is_literal_sequence(start_idx: int) -> List[Token]:
        """
        Returns the literal tokens if the RHS is a literal or simple path.
        Otherwise returns None.
        """
        idx = start_idx
        while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            idx += 1
            
        if idx >= n: return None
        
        val_tokens = None
        
        # 1. Valid literals: NUMBER, STRING, true, false, nil
        if tokens[idx].type in (TT.NUMBER, TT.STRING, TT.LONGSTRING) or (tokens[idx].type == TT.KEYWORD and tokens[idx].value in ("true", "false", "nil")):
            val_tokens = [tokens[idx]]
            idx += 1
            
        # 2. Valid API paths: NAME, NAME.NAME, NAME.NAME.NAME
        elif tokens[idx].type == TT.NAME and tokens[idx].value in SW_GLOBALS:
            val_tokens = [tokens[idx]]
            idx += 1
            while idx < n:
                # skip space
                while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    val_tokens.append(tokens[idx])
                    idx += 1
                if idx < n and tokens[idx].type == TT.OP and tokens[idx].value == ".":
                    val_tokens.append(tokens[idx])
                    idx += 1
                    while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                        val_tokens.append(tokens[idx])
                        idx += 1
                    if idx < n and tokens[idx].type == TT.NAME:
                        val_tokens.append(tokens[idx])
                        idx += 1
                    else:
                        return None
                else:
                    break
            
        # 3. Unary minus for numbers
        elif tokens[idx].type == TT.OP and tokens[idx].value == "-":
            val_tokens = [tokens[idx]]
            idx += 1
            while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                val_tokens.append(tokens[idx])
                idx += 1
            if idx < n and tokens[idx].type == TT.NUMBER:
                val_tokens.append(tokens[idx])
                idx += 1
            else:
                return None
        
        if not val_tokens:
            return None
            
        # Unified Terminator Check
        while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            idx += 1
            
        if idx < n:
            tok_next = tokens[idx]
            # Any of these mean the expression CONTINUES, or it's a multiple assignment list. We MUST reject!
            if tok_next.type == TT.OP and tok_next.value not in (";", "}", ")", "]"):
                return None
            if tok_next.type == TT.KEYWORD and tok_next.value in ("and", "or", "not"):
                return None
            if tok_next.type in (TT.STRING, TT.LONGSTRING):
                return None
                
        # Clean trailing spaces
        while val_tokens and val_tokens[-1].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            val_tokens.pop()
            
        return val_tokens

    # First pass: Count assignments
    i = 0
    while i < n:
        tok = tokens[i]
        
        if i in scope_start:
            current_scopes.append(scope_start[i])
            
        if tok.type == TT.KEYWORD and tok.value == "function":
            ctx_stack.append("BLOCK")
        elif tok.type == TT.KEYWORD and tok.value in ("end", "until"):
            if ctx_stack:
                ctx_stack.pop()
        elif tok.type == TT.OP and tok.value == "{":
            ctx_stack.append("TABLE")
        elif tok.type == TT.OP and tok.value == "}":
            if ctx_stack:
                ctx_stack.pop()

        if tok.type == TT.NAME:
            # We don't do assignment counting here anymore.
            pass
            
        elif tok.type == TT.OP and tok.value == "=":
            # We found an assignment!
            is_key = (ctx_stack and ctx_stack[-1] == "TABLE")
            if not is_key:
                # Scan backwards to collect all LHS variables
                lhs_vars = []
                j = i - 1
                while j >= 0:
                    while j >= 0 and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                        j -= 1
                    if j < 0: break
                    
                    if tokens[j].type == TT.NAME:
                        # Check if it's a property (e.g. a.b = 1)
                        is_prop = False
                        prev_j = j - 1
                        while prev_j >= 0 and tokens[prev_j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                            prev_j -= 1
                        if prev_j >= 0 and tokens[prev_j].type == TT.OP and tokens[prev_j].value in (".", ":"):
                            is_prop = True
                            
                        if not is_prop:
                            lhs_vars.append(tokens[j])
                            
                        j = prev_j # skip the name and dot if any
                        # We must continue backwards if there is a comma
                        # Wait, we need to find the comma!
                        while j >= 0 and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                            j -= 1
                        if j >= 0 and tokens[j].type == TT.OP and tokens[j].value == ",":
                            j -= 1 # skip comma and continue
                        else:
                            break # No more LHS variables
                    else:
                        break # Not a name, stop
                        
                # Now we have all LHS vars.
                # If there are multiple LHS vars, we DO NOT inline any of them.
                # But we MUST mark them all as assigned!
                
                is_multiple = len(lhs_vars) > 1
                
                for var_tok in lhs_vars:
                    resolved_local = _lookup_in_scopes(var_tok.value, current_scopes, i)
                    if resolved_local:
                        v_id = id(resolved_local)
                        local_assign_count[v_id] += 1
                        if local_assign_count[v_id] == 1 and not is_multiple:
                            rhs_tokens = is_literal_sequence(i + 1)
                            if rhs_tokens:
                                local_const_val[v_id] = rhs_tokens
                            else:
                                if v_id in local_const_val: del local_const_val[v_id]
                        else:
                            if v_id in local_const_val: del local_const_val[v_id]
                    else:
                        global_assign_count[var_tok.value] += 1
                        if global_assign_count[var_tok.value] == 1 and not is_multiple:
                            rhs_tokens = is_literal_sequence(i + 1)
                            if rhs_tokens:
                                global_const_val[var_tok.value] = rhs_tokens
                            else:
                                if var_tok.value in global_const_val: del global_const_val[var_tok.value]
                        else:
                            if var_tok.value in global_const_val: del global_const_val[var_tok.value]
                
        if i in scope_end:
            s = scope_end[i]
            if s in current_scopes:
                current_scopes.remove(s)
        i += 1

    # Filter out parameters and invalid locals
    safe_locals = {}
    
    # We need to map v_id back to VarInfo to check is_param
    # So let's build an id map
    
    id_to_vi = {}
    for s in current_scopes: # Wait, current_scopes is just [root] at the end. We need all locals.
        pass
        
    from ..scope import collect_all_locals
    for vi in collect_all_locals(root):
        id_to_vi[id(vi)] = vi

    for v_id, count in local_assign_count.items():
        vi = id_to_vi.get(v_id)
        if vi and count == 1 and not vi.is_param and v_id in local_const_val:
            safe_locals[v_id] = local_const_val[v_id]
            
    safe_globals = {}
    for name, count in global_assign_count.items():
        if count == 1 and name in global_const_val:
            safe_globals[name] = global_const_val[name]
            
    if not safe_locals and not safe_globals:
        return tokens, 0

    # Second pass: Inline usages
    # NOTE: We DO NOT inline the assignment itself! The assignment stays. 
    # But because we inline all references, the variable will be unreferenced!
    # Then `dce.py` (ast_dce) or local token passes will naturally delete it as dead code.
    # Wait, token-based dce doesn't delete `x = 60` if it's global!
    # If we want the global to be deleted, we might have to manually delete it here.
    # Or, actually, `x = 60` is relatively small, but deleting it saves 6 chars.
    # Let's leave it for now. In Stormworks, having a global `tps=60` left at the top is fine if it's small,
    # but the user requested replacing it. Wait, `literal_dedup` will extract `60` anyway, so `tps=E` and `E=60`. 
    # If we delete the original assignment, it's perfect!
    
    # Actually, removing the assignment is complex because it might be `local tps = 60`.
    # Let's just do the replacement for now!
    
    new_tokens = []
    current_scopes = [root]
    ctx_stack = []
    
    i = 0
    inlined_count = 0
    
    while i < n:
        tok = tokens[i]
        
        if i in scope_start:
            current_scopes.append(scope_start[i])
            
        if tok.type == TT.KEYWORD and tok.value == "function":
            ctx_stack.append("BLOCK")
        elif tok.type == TT.KEYWORD and tok.value in ("end", "until"):
            if ctx_stack:
                ctx_stack.pop()
        elif tok.type == TT.OP and tok.value == "{":
            ctx_stack.append("TABLE")
        elif tok.type == TT.OP and tok.value == "}":
            if ctx_stack:
                ctx_stack.pop()

        if tok.type == TT.NAME:
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

            if not is_prop and not is_key:
                resolved_local = _lookup_in_scopes(tok.value, current_scopes, i)
                
                # Are we at the assignment itself?
                # We do not inline the LHS of the assignment!
                j = i + 1
                while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    j += 1
                is_lhs = (j < n and tokens[j].type == TT.OP and tokens[j].value == "=")
                
                if is_lhs:
                    should_delete = False
                    val_len = 0
                    if resolved_local and id(resolved_local) in safe_locals:
                        should_delete = True
                        val_len = len(safe_locals[id(resolved_local)])
                    elif not resolved_local and tok.value in safe_globals:
                        should_delete = True
                        val_len = len(safe_globals[tok.value])
                        
                    if should_delete:
                        # 1. Pop 'local' from new_tokens if it exists
                        k = len(new_tokens) - 1
                        while k >= 0 and new_tokens[k].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                            k -= 1
                        if k >= 0 and new_tokens[k].type == TT.KEYWORD and new_tokens[k].value == "local":
                            # Pop everything from k to end
                            new_tokens = new_tokens[:k]
                            
                        # 2. Skip tokens until we've consumed the RHS
                        # We know the sequence: NAME, (spaces), =, (spaces), RHS_TOKENS
                        # The RHS tokens length is exactly `val_len` (excluding trailing spaces).
                        # We just skip until we've matched `val_len` non-whitespace tokens after `=`.
                        
                        idx = i + 1
                        while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                            idx += 1
                        idx += 1 # Skip '='
                        
                        matched = 0
                        while idx < n and matched < val_len:
                            if tokens[idx].type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                                matched += 1
                            idx += 1
                            
                        i = idx
                        continue
                
                if not is_lhs:
                    next_i = _skip_ws(tokens, i + 1)
                    next_tok = tokens[next_i] if next_i < n else None

                    if resolved_local and id(resolved_local) in safe_locals:
                        # Inline!
                        val_tokens = safe_locals[id(resolved_local)]
                        needs_parens = _needs_inline_parens(val_tokens, next_tok)
                        if needs_parens:
                            new_tokens.append(Token(TT.OP, "(", tok.pos))
                        for t in val_tokens:
                            new_tokens.append(Token(t.type, t.value, tok.pos))
                        if needs_parens:
                            new_tokens.append(Token(TT.OP, ")", tok.pos))
                        inlined_count += 1

                        if i in scope_end:
                            s = scope_end[i]
                            if s in current_scopes:
                                current_scopes.remove(s)
                        i += 1
                        continue

                    elif not resolved_local and tok.value in safe_globals:
                        # Inline!
                        val_tokens = safe_globals[tok.value]
                        needs_parens = _needs_inline_parens(val_tokens, next_tok)
                        if needs_parens:
                            new_tokens.append(Token(TT.OP, "(", tok.pos))
                        for t in val_tokens:
                            new_tokens.append(Token(t.type, t.value, tok.pos))
                        if needs_parens:
                            new_tokens.append(Token(TT.OP, ")", tok.pos))
                        inlined_count += 1

                        if i in scope_end:
                            s = scope_end[i]
                            if s in current_scopes:
                                current_scopes.remove(s)
                        i += 1
                        continue

        new_tokens.append(tok)
        
        if i in scope_end:
            s = scope_end[i]
            if s in current_scopes:
                current_scopes.remove(s)
        i += 1

    return new_tokens, inlined_count
