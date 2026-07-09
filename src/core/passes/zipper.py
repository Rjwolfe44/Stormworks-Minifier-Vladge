"""
Multi-Assignment Consolidation (The "Zipper").
Merges consecutive local variable declarations.
e.g. `local x = 1 local y = 2` -> `local x,y = 1,2`
"""
from typing import List, Tuple
from ..lexer import Token, TT

def consolidate_locals(tokens: List[Token]) -> Tuple[List[Token], int]:
    """
    Returns: (new_tokens, declarations_merged)
    """
    new_tokens = []
    i = 0
    n = len(tokens)
    merged_count = 0
    
    def parse_local_literal(idx):
        j = idx
        if tokens[j].type != TT.KEYWORD or tokens[j].value != "local": return None
        j += 1
        
        while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT): j += 1
        if j >= n or tokens[j].type != TT.NAME: return None
        name_tok = tokens[j]
        j += 1
        
        while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT): j += 1
        if j >= n or tokens[j].type != TT.OP or tokens[j].value != "=": return None
        j += 1
        
        while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT): j += 1
        if j >= n: return None
        
        lit_tok = tokens[j]
        is_literal = (
            lit_tok.type in (TT.NUMBER, TT.STRING, TT.LONGSTRING) or 
            (lit_tok.type == TT.KEYWORD and lit_tok.value in ("true", "false", "nil"))
        )
        if not is_literal: return None
            
        j += 1
        return {'names': [name_tok], 'literals': [lit_tok], 'next_i': j}

    while i < n:
        parsed = parse_local_literal(i)
        if parsed:
            names = parsed['names']
            literals = parsed['literals']
            next_i = parsed['next_i']
            
            while next_i < n:
                j = next_i
                while j < n and (tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT) or (tokens[j].type == TT.OP and tokens[j].value == ";")):
                    j += 1
                    
                if j >= n: break
                
                parsed_next = parse_local_literal(j)
                if parsed_next:
                    names.extend(parsed_next['names'])
                    literals.extend(parsed_next['literals'])
                    next_i = parsed_next['next_i']
                    merged_count += 1
                else:
                    break
                    
            if len(names) > 1:
                # Generate merged declaration
                new_tokens.append(Token(TT.KEYWORD, "local", tokens[i].pos))
                new_tokens.append(Token(TT.SPACE, " ", tokens[i].pos))
                
                for k in range(len(names)):
                    new_tokens.append(names[k])
                    if k < len(names) - 1:
                        new_tokens.append(Token(TT.OP, ",", names[k].pos))
                        
                new_tokens.append(Token(TT.OP, "=", names[0].pos))
                
                for k in range(len(literals)):
                    new_tokens.append(literals[k])
                    if k < len(literals) - 1:
                        new_tokens.append(Token(TT.OP, ",", literals[k].pos))
                        
                i = next_i
            else:
                # Was just a single local declaration
                new_tokens.append(tokens[i])
                i += 1
        else:
            new_tokens.append(tokens[i])
            i += 1
            
    return new_tokens, merged_count
