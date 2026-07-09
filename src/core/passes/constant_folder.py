"""
Constant Folding (Compile-time Math).
Evaluates simple math operations on numbers during minification.
e.g. `60 * 60 * 24` -> `86400`
"""

from typing import List, Tuple
from ..lexer import Token, TT

def fold_constants(tokens: List[Token]) -> Tuple[List[Token], int]:
    """
    Evaluates literal math. Returns (new_tokens, expressions_folded).
    """
    import ast
    new_tokens = []
    i = 0
    n = len(tokens)
    folded_count = 0
    
    _MATH_OPS = {"+", "-", "*", "/", "//", "%", "^"}
    
    while i < n:
        # Check if this token starts a math sequence
        if tokens[i].type == TT.NUMBER:
            # Look backwards to ensure we aren't stealing operands from a preceding operator
            prev_tok = None
            k = i - 1
            while k >= 0:
                if tokens[k].type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    prev_tok = tokens[k]
                    break
                k -= 1
            
            # If preceded by any math operator or name, it's unsafe to fold a sequence
            # (e.g. `a - 1 + 2` cannot safely fold `1+2` to `3` without changing logic to `a - 3`)
            if prev_tok and (prev_tok.type == TT.NAME or (prev_tok.type == TT.OP and prev_tok.value in _MATH_OPS)):
                new_tokens.append(tokens[i])
                i += 1
                continue

            # Gather consecutive NUMBER OP NUMBER ...
            seq = [tokens[i]]
            j = i + 1
            while j < n:
                # Skip spaces
                while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    seq.append(tokens[j])
                    j += 1
                
                if j < n and tokens[j].type == TT.OP and tokens[j].value in _MATH_OPS:
                    op_tok = tokens[j]
                    seq.append(op_tok)
                    j += 1
                    
                    # Next must be a number (potentially after spaces)
                    while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                        seq.append(tokens[j])
                        j += 1
                        
                    if j < n and tokens[j].type == TT.NUMBER:
                        seq.append(tokens[j])
                        j += 1
                    else:
                        # Missing number after OP. 
                        # We cannot safely fold a partial math sequence!
                        # e.g., 1 + 2 * a -> we gathered "1 + 2", next is "*", which fails.
                        # We must abort folding this sequence entirely.
                        seq.clear()
                        break
                else:
                    break
                    
            if len(seq) > 1 and sum(1 for t in seq if t.type == TT.NUMBER) > 1:
                # Math sequence detected. Evaluate it.
                expr_str = ""
                for t in seq:
                    v = t.value
                    if v == "^": v = "**"
                    expr_str += v
                
                try:
                    # Very safe eval
                    val = eval(expr_str, {"__builtins__": None}, {})
                    if isinstance(val, (int, float)):
                        # Format it
                        if isinstance(val, float) and val.is_integer():
                            val = int(val)
                        sval = str(val)
                        # Only fold if it's actually shorter!
                        if len(sval) < len(expr_str):
                            new_tokens.append(Token(TT.NUMBER, sval, seq[0].pos))
                            folded_count += 1
                            i = j
                            continue
                except Exception:
                    pass
        
        new_tokens.append(tokens[i])
        i += 1

    return new_tokens, folded_count
