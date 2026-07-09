"""
Short-Circuit Injector (Level 4).
Mutates `if A then B() end` into `_=A and B()` where safe.
"""

from typing import List, Tuple
from ..lexer import Token, TT

def inject_short_circuit(tokens: List[Token]) -> Tuple[List[Token], int]:
    """Returns (new_tokens, inject_count)"""
    new_tokens = []
    i = 0
    n = len(tokens)
    inject_count = 0
    
    # We want to match: `if <cond> then <func()> end`
    # and replace with: `_ = <cond> and <func()>`
    
    while i < n:
        tok = tokens[i]
        
        if tok.type == TT.KEYWORD and tok.value == "if":
            j = i + 1
            cond_tokens = []
            while j < n and not (tokens[j].type == TT.KEYWORD and tokens[j].value == "then"):
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
            
            body_tokens_raw = []
            while j < n and not (tokens[j].type == TT.KEYWORD and tokens[j].value == "end"):
                if tokens[j].type == TT.KEYWORD and tokens[j].value in ("if", "else", "elseif"):
                    break
                body_tokens_raw.append(tokens[j])
                j += 1
                
            if j >= n or tokens[j].type != TT.KEYWORD or tokens[j].value != "end":
                new_tokens.append(tokens[i])
                i += 1
                continue
                
            end_idx = j
            
            # Analyze body for safety
            body_clean = [t for t in body_tokens_raw if t.type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT)]
            
            is_safe_func_call = len(body_clean) > 0
            for t in body_clean:
                if t.type == TT.KEYWORD or (t.type == TT.OP and t.value == "="):
                    is_safe_func_call = False
                    break
                    
            if is_safe_func_call:
                # Inject: `_ = (cond) and body`
                new_tokens.append(Token(TT.NAME, "_", tokens[i].pos))
                new_tokens.append(Token(TT.OP, "=", tokens[i].pos))
                
                new_tokens.append(Token(TT.OP, "(", cond_tokens[0].pos))
                for t in cond_tokens: new_tokens.append(t)
                new_tokens.append(Token(TT.OP, ")", cond_tokens[-1].pos))
                
                new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                new_tokens.append(Token(TT.KEYWORD, "and", tokens[i].pos))
                new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                
                for t in body_tokens_raw: new_tokens.append(t)
                
                inject_count += 1
                i = end_idx + 1
                continue
        
        new_tokens.append(tokens[i])
        i += 1
        
    return new_tokens, inject_count
