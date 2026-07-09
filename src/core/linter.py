"""
VladgeMinifier - Static Analysis Engine (Linter)

Performs static analysis on Lua scripts to identify potential runtime issues 
such as undefined global variables, missing functions, and syntax errors 
before deploying code to Stormworks.
"""

from typing import List, Tuple
from .lexer import Token, TT, SW_GLOBALS, tokenize
from .scope import build_scope_tree, Scope
from .linter_shortcircuit import is_short_circuit_dead_read

# Game-engine / Lua builtins the linter should ignore (includes full SW_GLOBALS).
SW_GAME_GLOBALS = set(SW_GLOBALS) | {
    "simulator",
    "__simulator",
    "__ENV",
    "_ENV",
}

SW_CALLBACKS = frozenset({
    "onTick", "onDraw", "onButtonPress", "onTogglePress", "onSwitchPress",
    "onChatInput", "onMouseWheel", "onMouseMove", "onMouseDown", "onMouseUp",
})

def lint_script(source_code: str) -> List[str]:
    """
    Performs a static analysis linting pass on the provided source code.
    
    Args:
        source_code (str): The raw Lua source code to analyse.
        
    Returns:
        List[str]: A list of formatted error messages. An empty list indicates no issues were found.
    """
    errors = []
    
    try:
        # Step 1: Validate that the code lexes correctly into tokens
        tokens = tokenize(source_code)
    except Exception as e:
        return [f"Syntax Error during tokenization: {e}"]

    # Step 2: Construct the scope tree to understand local definitions and lifetimes
    try:
        root_scope = build_scope_tree(tokens)
    except Exception as e:
        return [f"Scope Error (Check your brackets/ends): {e}"]
        
    # Step 3: Map individual tokens to their respective lexical scopes to accurately resolve variable references
    from .passes.rename_locals import _index_scopes, _lookup_in_scopes
    scope_start = {}
    scope_end = {}
    _index_scopes(root_scope, scope_start, scope_end)
    
    current_scopes = [root_scope]
    ctx_stack = []
    
    n = len(tokens)

    def _push_scopes(i):
        if i in scope_start:
            for s in scope_start[i]:
                current_scopes.append(s)

    def _pop_scopes(i):
        if i in scope_end:
            for s in scope_end[i]:
                if s in current_scopes:
                    current_scopes.remove(s)
    
    # Pass 1: Scan and register all user-defined global variables (e.g. `myGlobal = 1`)
    user_defined_globals = set()
    for i, tok in enumerate(tokens):
        _push_scopes(i)
            
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
            # Determine if this variable name is part of an assignment expression
            is_assignment = False
            
            # Sub-check A: Ignore property access patterns (e.g. `obj.name`)
            is_prop = False
            prev_i = i - 1
            while prev_i >= 0 and tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and tokens[prev_i].type == TT.OP and tokens[prev_i].value in (".", ":"):
                is_prop = True
                
            # Sub-check B: Ignore the base identifier of a field mutation (e.g. `name.prop = 1` or `name[1] = 1`)
            is_mutating_field = False
            next_i = i + 1
            while next_i < n and tokens[next_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                next_i += 1
            if next_i < n and tokens[next_i].type == TT.OP and tokens[next_i].value in (".", "["):
                is_mutating_field = True
                
            if not is_prop and not is_mutating_field:
                # Sub-check C: Scan forward to detect an '=' operator before the current statement concludes
                fwd_i = next_i
                nesting = 0
                while fwd_i < n:
                    ftok = tokens[fwd_i]
                    if ftok.type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                        fwd_i += 1
                        continue
                        
                    if ftok.type == TT.OP:
                        if ftok.value in ("(", "[", "{"):
                            nesting += 1
                        elif ftok.value in (")", "]", "}"):
                            nesting -= 1
                            if nesting < 0:
                                break
                        elif nesting == 0:
                            if ftok.value == "=":
                                if not (ctx_stack and ctx_stack[-1] == "TABLE"):
                                    is_assignment = True
                                break
                            elif ftok.value == ",":
                                pass
                            elif ftok.value == ".":
                                pass
                            else:
                                break
                    elif ftok.type == TT.NAME:
                        pass
                    elif ftok.type in (TT.NUMBER, TT.STRING, TT.KEYWORD):
                        if nesting == 0:
                            break
                    
                    fwd_i += 1

            # Evaluate if this constitutes a global function definition `function NAME()`
            prev_i = i - 1
            while prev_i >= 0 and tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and tokens[prev_i].type == TT.KEYWORD and tokens[prev_i].value == "function":
                # Confirm this is a global function and not a local function (which would resolve in `_lookup_in_scopes`)
                is_assignment = True
                
            if is_assignment:
                resolved_local = _lookup_in_scopes(tok.value, current_scopes, i)
                if not resolved_local:
                    user_defined_globals.add(tok.value)

        _pop_scopes(i)

    called_functions: set[str] = set()
    for i, tok in enumerate(tokens):
        if tok.type != TT.NAME:
            continue
        j = i + 1
        while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            j += 1
        if j < n and tokens[j].type == TT.OP and tokens[j].value == "(":
            called_functions.add(tok.value)

    global_func_spans: dict[str, tuple[int, int]] = {}
    i = 0
    while i < n:
        tok = tokens[i]
        if tok.type == TT.KEYWORD and tok.value == "function":
            j = i + 1
            while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                j += 1
            if j < n and tokens[j].type == TT.NAME:
                fname = tokens[j].value
                is_local = False
                k = i - 1
                while k >= 0 and tokens[k].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    k -= 1
                if k >= 0 and tokens[k].type == TT.KEYWORD and tokens[k].value == "local":
                    is_local = True
                if not is_local:
                    depth = 1
                    k = i + 1
                    while k < n and depth > 0:
                        t = tokens[k]
                        if t.type == TT.KEYWORD:
                            if t.value in ("function", "if", "for", "while", "repeat", "do"):
                                depth += 1
                            elif t.value == "end":
                                depth -= 1
                        k += 1
                    global_func_spans[fname] = (j + 1, k - 1)
        i += 1

    reachable_functions = set(SW_CALLBACKS)
    changed = True
    while changed:
        changed = False
        for fname, (start, end) in global_func_spans.items():
            if fname not in reachable_functions:
                continue
            for ci in range(start, end + 1):
                ct = tokens[ci]
                if ct.type != TT.NAME:
                    continue
                cj = ci + 1
                while cj < n and tokens[cj].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    cj += 1
                if cj < n and tokens[cj].type == TT.OP and tokens[cj].value == "(":
                    callee = ct.value
                    if callee in global_func_spans and callee not in reachable_functions:
                        reachable_functions.add(callee)
                        changed = True

    uncalled_functions = {
        name for name in global_func_spans
        if name not in reachable_functions
    }

    uncalled_spans: List[tuple[int, int]] = [
        global_func_spans[name] for name in uncalled_functions
    ]

    def _in_uncalled_function(idx: int) -> bool:
        return any(start <= idx <= end for start, end in uncalled_spans)

    # Reset environment tracking for the validation pass
    current_scopes = [root_scope]
    ctx_stack = []
    
    # Pass 2: Identify any reads from undefined global variables
    for i, tok in enumerate(tokens):
        _push_scopes(i)
            
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
            # Ignore property access using `.` or `:`
            prev_i = i - 1
            while prev_i >= 0 and tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and tokens[prev_i].type == TT.OP and tokens[prev_i].value in (".", ":"):
                _pop_scopes(i)
                continue
                
            # Ignore assignments that declare table keys, e.g. `{ name = 1 }`
            is_key = False
            if ctx_stack and ctx_stack[-1] == "TABLE":
                next_i = i + 1
                while next_i < n and tokens[next_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    next_i += 1
                if next_i < n and tokens[next_i].type == TT.OP and tokens[next_i].value == "=":
                    is_key = True
            
            if is_key:
                _pop_scopes(i)
                continue
                
            # Ignore variables that resolve correctly to a local scope definition
            resolved_local = _lookup_in_scopes(tok.value, current_scopes, i)
            if resolved_local:
                _pop_scopes(i)
                continue

            if _in_uncalled_function(i):
                _pop_scopes(i)
                continue

            # Flag issue: Attempted read from a global variable that is neither a game API nor user-defined
            if tok.value not in user_defined_globals and tok.value not in SW_GAME_GLOBALS:
                if is_short_circuit_dead_read(tokens, i, user_defined_globals):
                    _pop_scopes(i)
                    continue
                line_no = source_code.count("\n", 0, tok.pos) + 1
                errors.append(f"Line {line_no}: Undefined global variable '{tok.value}'. This may cause a 'nil value' crash in Stormworks.")
                
        _pop_scopes(i)
                
    # Deduplicate accumulated errors while strictly preserving their original sequential order
    seen = set()
    dedup = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            dedup.append(err)
            
    return dedup
