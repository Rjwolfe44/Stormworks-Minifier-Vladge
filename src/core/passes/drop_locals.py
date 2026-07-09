"""
Pass: Drop Global Locals
Converts top-level local variables into global variables by stripping the 'local' keyword.
Because Stormworks isolates each microcontroller script into its own global environment, 
this is highly effective for reducing character count without bleeding to other microcontrollers.
"""
from typing import List, Tuple, Set
from ..lexer import Token, TT
from ..scope import build_scope_tree

def drop_global_locals(tokens: List[Token]) -> Tuple[List[Token], int]:
    """
    Strips the 'local' keyword from any variable or function declared in the global scope.
    Returns: (new_tokens, chars_saved)
    """
    root_scope = build_scope_tree(tokens)
    
    # Collect all token indices that represent a global declaration
    global_decl_indices: Set[int] = set()
    for varinfo in root_scope.locals.values():
        global_decl_indices.add(varinfo.declaration_idx)
        
    new_tokens = []
    saved = 0
    i = 0
    n = len(tokens)
    
    while i < n:
        tok = tokens[i]
        
        if tok.type == TT.KEYWORD and tok.value == "local":
            # Peek ahead to see if this 'local' declares a global-scope variable
            j = i + 1
            while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                j += 1
                
            if j < n:
                is_global_decl = False
                
                if tokens[j].type == TT.NAME and j in global_decl_indices:
                    # local NAME ...
                    is_global_decl = True
                elif tokens[j].type == TT.KEYWORD and tokens[j].value == "function":
                    # local function NAME ...
                    k = j + 1
                    while k < n and tokens[k].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                        k += 1
                    if k < n and tokens[k].type == TT.NAME and k in global_decl_indices:
                        is_global_decl = True
                        
                if is_global_decl:
                    # Strip 'local'
                    saved += 5
                    i += 1
                    # Also strip the immediate trailing space to be clean
                    if i < n and tokens[i].type == TT.SPACE:
                        saved += len(tokens[i].value)
                        i += 1
                    continue
                    
        new_tokens.append(tok)
        i += 1
        
    return new_tokens, saved
