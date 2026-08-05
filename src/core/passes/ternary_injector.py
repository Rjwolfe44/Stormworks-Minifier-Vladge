"""
Ternary Injector (Level 4).
Mutates `if A then B=C else B=D end` into `B=A and C or D` where safe.
"""

from typing import List, Tuple
from ..lexer import Token, TT

def _tokens_match(t1: List[Token], t2: List[Token]) -> bool:
    if len(t1) != len(t2): return False
    for a, b in zip(t1, t2):
        if a.type != b.type or a.value != b.value:
            return False
    return True

def inject_ternary(tokens: List[Token]) -> Tuple[List[Token], int]:
    """Returns (new_tokens, inject_count)"""
    new_tokens = []
    i = 0
    n = len(tokens)
    inject_count = 0
    
    # We want to match: `if <cond> then <target> = <expr1> else <target> = <expr2> end`
    # and replace with: `<target> = <cond> and <expr1> or <expr2>`
    
    while i < n:
        tok = tokens[i]
        
        if tok.type == TT.KEYWORD and tok.value == "if":
            # Attempt to parse
            start_idx = i
            j = i + 1
            
            def get_next_meaningful(idx):
                while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    idx += 1
                return idx
            
            # Find 'then'
            cond_tokens = []
            while j < n and not (tokens[j].type == TT.KEYWORD and tokens[j].value == "then"):
                # if we hit another structural keyword, abort
                if tokens[j].type == TT.KEYWORD and tokens[j].value in ("if", "else", "elseif", "end"):
                    break
                cond_tokens.append(tokens[j])
                j += 1
                
            if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "then":
                new_tokens.append(tokens[i])
                i += 1
                continue
                
            then_idx = j
            j += 1
            
            # Now parse `<target1> = <expr1>` until `else`
            target1 = []
            while j < n and not (tokens[j].type == TT.OP and tokens[j].value == "="):
                if tokens[j].type == TT.KEYWORD and tokens[j].value in ("if", "else", "elseif", "end"):
                    break
                if tokens[j].type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    target1.append(tokens[j])
                j += 1
                
            if j >= n or tokens[j].type != TT.OP or tokens[j].value != "=":
                new_tokens.append(tokens[i])
                i += 1
                continue
                
            j += 1
            expr1 = []
            while j < n and not (tokens[j].type == TT.KEYWORD and tokens[j].value == "else"):
                if tokens[j].type == TT.KEYWORD and tokens[j].value in ("if", "elseif", "end"):
                    break
                expr1.append(tokens[j])
                j += 1
                
            if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "else":
                new_tokens.append(tokens[i])
                i += 1
                continue
                
            else_idx = j
            j += 1
            
            # Parse `<target2> = <expr2>` until `end`
            target2 = []
            while j < n and not (tokens[j].type == TT.OP and tokens[j].value == "="):
                if tokens[j].type == TT.KEYWORD and tokens[j].value in ("if", "else", "elseif", "end"):
                    break
                if tokens[j].type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    target2.append(tokens[j])
                j += 1
                
            if j >= n or tokens[j].type != TT.OP or tokens[j].value != "=":
                new_tokens.append(tokens[i])
                i += 1
                continue
                
            j += 1
            expr2 = []
            while j < n and not (tokens[j].type == TT.KEYWORD and tokens[j].value == "end"):
                if tokens[j].type == TT.KEYWORD and tokens[j].value in ("if", "else", "elseif"):
                    break
                expr2.append(tokens[j])
                j += 1
                
            if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "end":
                new_tokens.append(tokens[i])
                i += 1
                continue
                
            end_idx = j
            
            # Verify targets match
            if len(target1) > 0 and _tokens_match(target1, target2):
                # Target must not be empty and must just be a valid assignment left-hand side.
                # For safety, let's only do it if expr1 is a literal Number, String, or 'true' (truthy)
                # If expr1 can be false or nil, `a and false or true` will evaluate to `true` incorrectly!
                
                # Check if expr1 is guaranteed truthy.
                # A single token that is NUMBER, STRING, LONGSTRING, or KEYWORD 'true'.
                # We strip spaces from expr1 to check.
                clean_expr1 = [t for t in expr1 if t.type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT)]
                is_safe = False
                if len(clean_expr1) == 1:
                    t1 = clean_expr1[0]
                    if t1.type in (TT.NUMBER, TT.STRING, TT.LONGSTRING):
                        is_safe = True
                    elif t1.type == TT.KEYWORD and t1.value == "true":
                        is_safe = True
                        
                if is_safe:
                    # Inject: `<target> = <cond> and <expr1> or <expr2>`
                    for t in target1: new_tokens.append(t)
                    new_tokens.append(Token(TT.OP, "=", target1[-1].pos))
                    
                    # condition might need parentheses if it contains `or` but and/or precedence in Lua usually makes it safe,
                    # but let's wrap it in parentheses to be absolutely bulletproof.
                    new_tokens.append(Token(TT.OP, "(", cond_tokens[0].pos))
                    for t in cond_tokens: new_tokens.append(t)
                    new_tokens.append(Token(TT.OP, ")", cond_tokens[-1].pos))
                    
                    new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                    new_tokens.append(Token(TT.KEYWORD, "and", tokens[i].pos))
                    new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                    
                    for t in expr1: new_tokens.append(t)
                    
                    new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                    new_tokens.append(Token(TT.KEYWORD, "or", tokens[i].pos))
                    new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                    
                    for t in expr2: new_tokens.append(t)
                    
                    inject_count += 1
                    i = end_idx + 1
                    continue
        
        new_tokens.append(tokens[i])
        i += 1
        
    return new_tokens, inject_count
