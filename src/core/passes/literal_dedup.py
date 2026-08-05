from typing import List, Tuple, Dict
from collections import Counter
from ..lexer import Token, TT

def dedup_literals(tokens: List[Token], allocated_globals: set) -> Tuple[List[Token], int]:
    # Find all strings and large numbers used multiple times
    freq = Counter()
    for tok in tokens:
        if tok.type in (TT.STRING, TT.LONGSTRING):
            freq[tok.value] += 1
        elif tok.type == TT.NUMBER:
            freq[tok.value] += 1
        elif tok.type == TT.KEYWORD and tok.value in ("true", "false", "nil"):
            freq[tok.value] += 1

    # Calculate savings
    # local A=value (6 + 1 + 1 + len(value) = 8 + len(value))
    # or just A=value (1 + 1 + len(value) = 2 + len(value)) if a global is used
    # Using global variables: `A="string"` -> 2 + len(value)
    # Replaced usages: 1 char
    
    to_replace = {}
    saved_bytes = 0
    
    def generate_name(index: int) -> str:
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        res = ""
        while index >= 0:
            res = chars[index % 52] + res
            index = (index // 52) - 1
        return res

    name_idx = 0
    new_globals = []
    
    for val, count in freq.items():
        if count > 1:
            # Assign a name
            # Cost of declaring it as global: len(name) + 1 (comma or eq) + len(val)
            # Cost of usages: len(name) * count
            # Original cost: len(val) * count
            
            # Find a free name first to determine its actual length
            # Force test_idx >= 52 to avoid conflict with 1-letter local names
            test_idx = max(name_idx, 52)
            name = ""
            while True:
                name = generate_name(test_idx)
                test_idx += 1
                if name not in allocated_globals and name not in ("in", "do", "if", "or", "and"):
                    break
                    
            est_name_len = len(name)
            original_cost = len(val) * count
            # Use +2 for the declaration overhead (comma + val)
            new_cost = (est_name_len + len(val) + 2) + (est_name_len * count)
            
            if new_cost < original_cost:
                # Use this replacement
                name_idx = test_idx
                to_replace[val] = name
                allocated_globals.add(name)
                saved_bytes += (original_cost - new_cost)
                
                # Add to new_globals definition
                new_globals.append(f"{name}={val}")

    if not to_replace:
        return tokens, 0
        
    # Replace tokens
    new_tokens = []
    for i, tok in enumerate(tokens):
        if tok.type in (TT.STRING, TT.LONGSTRING, TT.NUMBER) or (tok.type == TT.KEYWORD and tok.value in ("true", "false", "nil")):
            if tok.value in to_replace:
                new_tok = Token(TT.NAME, to_replace[tok.value], tok.pos)
                
                # Check if we need to restore omitted parentheses for string function calls (e.g. `e"string"` -> `e(A)`)
                if tok.type in (TT.STRING, TT.LONGSTRING):
                    prev_tok = None
                    for k in range(i - 1, -1, -1):
                        if tokens[k].type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                            prev_tok = tokens[k]
                            break
                    if prev_tok and (prev_tok.type == TT.NAME or (prev_tok.type == TT.OP and prev_tok.value in (")", "]", "}"))):
                        # We are replacing a string argument that had its parens omitted!
                        new_tokens.append(Token(TT.OP, "(", tok.pos))
                        new_tokens.append(new_tok)
                        new_tokens.append(Token(TT.OP, ")", tok.pos))
                        continue

                new_tokens.append(new_tok)
                continue
        new_tokens.append(tok)
        
    # Prepend the global declarations to the start
    # "A,B,C=1,2,3 "
    prepend_tokens = []
    
    names = []
    vals = []
    
    for expr in new_globals:
        name, val = expr.split('=', 1)
        names.append(name)
        vals.append(val)
        
    for i, name in enumerate(names):
        prepend_tokens.append(Token(TT.NAME, name, 0))
        if i < len(names) - 1:
            prepend_tokens.append(Token(TT.OP, ",", 0))
            
    prepend_tokens.append(Token(TT.OP, "=", 0))
    
    for i, val in enumerate(vals):
        if val in ("true", "false", "nil"):
            prepend_tokens.append(Token(TT.KEYWORD, val, 0))
        elif val.startswith('"') or val.startswith("'"):
            prepend_tokens.append(Token(TT.STRING, val, 0))
        else:
            prepend_tokens.append(Token(TT.NUMBER, val, 0))
            
        if i < len(vals) - 1:
            prepend_tokens.append(Token(TT.OP, ",", 0))
            
    prepend_tokens.append(Token(TT.SPACE, " ", 0))
        
    return prepend_tokens + new_tokens, saved_bytes
