"""
Token-based AST Optimizer (Level 4 Ultimate).
Performs advanced Lua 5.3 golfing optimizations directly on the token stream.
"""
from typing import List, Tuple
from ..lexer import Token, TT

def optimize_tokens(tokens: List[Token], *, lua53_floor: bool = False) -> Tuple[List[Token], int]:
    new_tokens = []
    i = 0
    n = len(tokens)
    optimizations_made = 0
    
    def skip_spaces(idx: int) -> int:
        while idx < n and tokens[idx].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
            idx += 1
        return idx
        
    def get_balanced_expr(start_idx: int, open_tok: str, close_tok: str) -> Tuple[List[Token], int]:
        """Extracts tokens between balanced brackets/parens, returning (expr_tokens, next_idx)"""
        depth = 1
        idx = start_idx
        expr = []
        while idx < n:
            t = tokens[idx]
            if t.type == TT.OP:
                if t.value == open_tok:
                    depth += 1
                elif t.value == close_tok:
                    depth -= 1
                    if depth == 0:
                        return expr, idx + 1
            expr.append(t)
            idx += 1
        return None, idx
        
    while i < n:
        tok = tokens[i]
        
        # ── 1. Parentheses Stripping (Strings & Tables) ──
        # e.g., require("foo") -> require"foo"
        if tok.type == TT.NAME:
            j = skip_spaces(i + 1)
            if j < n and tokens[j].type == TT.OP and tokens[j].value == "(":
                k = skip_spaces(j + 1)
                if k < n and tokens[k].type in (TT.STRING, TT.LONGSTRING):
                    l = skip_spaces(k + 1)
                    if l < n and tokens[l].type == TT.OP and tokens[l].value == ")":
                        # Strip parentheses
                        new_tokens.append(tok)
                        new_tokens.append(tokens[k])
                        optimizations_made += 1
                        i = l + 1
                        continue
                # Also check for table: func({a=1}) -> func{a=1}
                if k < n and tokens[k].type == TT.OP and tokens[k].value == "{":
                    # Find balanced '}'
                    expr, next_idx = get_balanced_expr(k + 1, "{", "}")
                    if expr is not None:
                        # Check if next token is ')'
                        l = skip_spaces(next_idx)
                        if l < n and tokens[l].type == TT.OP and tokens[l].value == ")":
                            # Strip parentheses
                            new_tokens.append(tok)
                            new_tokens.append(tokens[k]) # '{'
                            new_tokens.extend(expr)
                            new_tokens.append(tokens[next_idx - 1]) # '}'
                            optimizations_made += 1
                            i = l + 1
                            continue

        # ── 2. Stormworks Lua 5.3 API Golfing ──
        # table.insert(t, v) -> t[#t+1]=v
        if tok.type == TT.NAME and tok.value in ("table", "math"):
            j = skip_spaces(i + 1)
            if j < n and tokens[j].type == TT.OP and tokens[j].value == ".":
                k = skip_spaces(j + 1)
                if k < n and tokens[k].type == TT.NAME:
                    method = tokens[k].value
                    m = skip_spaces(k + 1)
                    if m < n and tokens[m].type == TT.OP and tokens[m].value == "(":
                        expr, next_idx = get_balanced_expr(m + 1, "(", ")")
                        if expr is not None:
                            if tok.value == "table" and method == "insert":
                                # Calculate threshold for global aliasing vs inline golfing.
                                # Inline golfing is more efficient if the frequency is below 5.
                                count_insert = sum(1 for t1 in tokens if t1.type == TT.NAME and t1.value == "insert")
                                if count_insert < 5:
                                    # Find the argument separator
                                    commas = []
                                    depth = 0
                                    for c_idx, c_tok in enumerate(expr):
                                        if c_tok.type == TT.OP:
                                            if c_tok.value in ("(", "{", "["): depth += 1
                                            elif c_tok.value in (")", "}", "]"): depth -= 1
                                            elif c_tok.value == "," and depth == 0:
                                                commas.append(c_idx)
                                    # Only inline if there is exactly 1 comma (2 arguments)
                                    # 3-argument table.insert(t, pos, v) cannot be optimized to t[#t+1]=v
                                    if len(commas) == 1:
                                        comma_idx = commas[0]
                                        # Split into target array and value
                                        t_expr = expr[:comma_idx]
                                        v_expr = expr[comma_idx+1:]
                                        
                                        # Construct t[#t+1]=v
                                        new_tokens.extend(t_expr)
                                        new_tokens.append(Token(TT.OP, "[", tok.pos))
                                        new_tokens.append(Token(TT.OP, "#", tok.pos))
                                        new_tokens.extend(t_expr)
                                        new_tokens.append(Token(TT.OP, "+", tok.pos))
                                        new_tokens.append(Token(TT.NUMBER, "1", tok.pos))
                                        new_tokens.append(Token(TT.OP, "]", tok.pos))
                                        new_tokens.append(Token(TT.OP, "=", tok.pos))
                                        new_tokens.extend(v_expr)
                                        
                                        optimizations_made += 1
                                        i = next_idx
                                        continue
                            
                            # math.floor → (expr)//1 (opt-in via --lua53-floor)
                            elif lua53_floor and tok.value == "math" and method == "floor":
                                new_tokens.append(Token(TT.OP, "(", tok.pos))
                                new_tokens.extend(expr)
                                new_tokens.append(Token(TT.OP, ")", tok.pos))
                                new_tokens.append(Token(TT.OP, "//", tok.pos))
                                new_tokens.append(Token(TT.NUMBER, "1", tok.pos))
                                optimizations_made += 1
                                i = next_idx
                                continue
                            elif tok.value == "math" and method == "ceil":
                                # Calculate threshold for global aliasing vs inline golfing.
                                count_ceil = sum(1 for t1 in tokens if t1.type == TT.NAME and t1.value == "ceil")
                                if count_ceil < 3:
                                    new_tokens.append(Token(TT.OP, "-", tok.pos))
                                    new_tokens.append(Token(TT.OP, "(", tok.pos))
                                    new_tokens.append(Token(TT.OP, "-", tok.pos))
                                    new_tokens.append(Token(TT.OP, "(", tok.pos))
                                    new_tokens.extend(expr)
                                    new_tokens.append(Token(TT.OP, ")", tok.pos))
                                    new_tokens.append(Token(TT.OP, "//", tok.pos))
                                    new_tokens.append(Token(TT.NUMBER, "1", tok.pos))
                                    new_tokens.append(Token(TT.OP, ")", tok.pos))
                                    optimizations_made += 1
                                    i = next_idx
                                    continue

        # ── 3. Table Constructor Packing ──
        # {["key"] = val} -> {key=val}
        if tok.type == TT.OP and tok.value == "[":
            j = skip_spaces(i + 1)
            if j < n and tokens[j].type == TT.STRING:
                str_val = tokens[j].value
                # Verify that the key is a valid Lua identifier
                import re
                if re.match(r"^['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]$", str_val):
                    key_name = str_val[1:-1]
                    k = skip_spaces(j + 1)
                    if k < n and tokens[k].type == TT.OP and tokens[k].value == "]":
                        l = skip_spaces(k + 1)
                        if l < n and tokens[l].type == TT.OP and tokens[l].value == "=":
                            new_tokens.append(Token(TT.NAME, key_name, tok.pos))
                            new_tokens.append(tokens[l]) # '='
                            optimizations_made += 1
                            i = l + 1
                            continue

        # ── 4. For-Loop Step Removal ──
        # for i=1,10,1 do -> for i=1,10 do
        if tok.type == TT.KEYWORD and tok.value == "for":
            j = skip_spaces(i + 1)
            if j < n and tokens[j].type == TT.NAME:
                k = skip_spaces(j + 1)
                if k < n and tokens[k].type == TT.OP and tokens[k].value == "=":
                    # Resolve bounds of numeric for loop definition
                    do_idx = -1
                    for m in range(k + 1, min(n, k + 50)):
                        if tokens[m].type == TT.KEYWORD and tokens[m].value == "do":
                            do_idx = m
                            break
                    if do_idx != -1:
                        # Extract the loop definition expressions
                        loop_def = tokens[k+1:do_idx]
                        commas = []
                        depth = 0
                        for c_idx, c_tok in enumerate(loop_def):
                            if c_tok.type == TT.OP:
                                if c_tok.value in ("(", "{", "["): depth += 1
                                elif c_tok.value in (")", "}", "]"): depth -= 1
                                elif c_tok.value == "," and depth == 0:
                                    commas.append(c_idx)
                                    
                        if len(commas) == 2:
                            # Evaluate the step expression (3rd argument)
                            expr3 = loop_def[commas[1]+1:]
                            clean_expr3 = [t for t in expr3 if t.type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT)]
                            if len(clean_expr3) == 1 and clean_expr3[0].type == TT.NUMBER and clean_expr3[0].value == "1":
                                # Remove the default step increment of 1
                                new_tokens.append(tok) # for
                                new_tokens.extend(tokens[i+1:k+1+commas[1]]) 
                                optimizations_made += 1
                                i = do_idx
                                continue
                                

        new_tokens.append(tok)
        i += 1
        
    return new_tokens, optimizations_made
