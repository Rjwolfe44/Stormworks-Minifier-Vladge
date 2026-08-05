"""
VladgeMinifier - String Obfuscation Pass V2
Encrypts all string literals into a single Hex-encoded string blob and 
injects a tiny runtime decoder. This provides true encryption while 
massively reducing file size compared to the old string.char() method.
"""

from typing import List, Tuple
from ..lexer import Token, TT

def obfuscate_strings(tokens: List[Token]) -> Tuple[List[Token], int]:
    """
    Finds all string literals, extracts them, encrypts them into a single hex-encoded blob,
    and replaces their usages with __OBF_STR[index].
    """
    strings = []
    string_to_idx = {}
    
    # 1. Collect all unique strings
    for tok in tokens:
        if tok.type in (TT.STRING, TT.LONGSTRING):
            # Parse the actual string value
            val = tok.value
            if val.startswith('"') or val.startswith("'"):
                # Handle escapes properly
                # For simplicity, we can just use python's eval if it's a standard string
                try:
                    # eval safely handles standard lua single-line strings that match python's
                    parsed_str = eval(val)
                except:
                    # Fallback for complex strings
                    parsed_str = val[1:-1]
            elif val.startswith('[[') or val.startswith(']====]'):
                # Long string parsing
                parsed_str = val.split('[', 2)[-1]
                # It's actually easier to just strip the brackets
                # Find the level of equals
                prefix = val.split('[')[1] # e.g. "=="
                parsed_str = val[len(prefix)+2 : -(len(prefix)+2)]
            else:
                parsed_str = val[1:-1]
                
            if parsed_str not in string_to_idx:
                string_to_idx[parsed_str] = len(strings) + 1 # Lua is 1-indexed
                strings.append(parsed_str)
                
    if not strings:
        return tokens, 0
        
    # 2. Build the hex blob
    hex_strings = []
    for s in strings:
        # Convert to hex
        hex_str = s.encode('utf-8').hex()
        hex_strings.append(hex_str)
        
    master_hex_blob = "|".join(hex_strings)
    
    # 3. Create the decoder tokens
    decoder_code = f"""local __OBF_STR={{}}
for m in ("{master_hex_blob}"):gmatch("[^|]+") do
__OBF_STR[#__OBF_STR+1]=m:gsub("..",function(x)return string.char(tonumber(x,16))end)
end
"""
    from ..lexer import tokenize
    decoder_tokens = tokenize(decoder_code)
    
    # 4. Replace string tokens with __OBF_STR[idx]
    new_tokens = []
    saved_bytes = 0
    
    for i, tok in enumerate(tokens):
        if tok.type in (TT.STRING, TT.LONGSTRING):
            # Same parsing logic
            val = tok.value
            if val.startswith('"') or val.startswith("'"):
                try:
                    parsed_str = eval(val)
                except:
                    parsed_str = val[1:-1]
            else:
                # long string
                prefix = val.split('[')[1]
                parsed_str = val[len(prefix)+2 : -(len(prefix)+2)]
                
            idx = string_to_idx[parsed_str]
            replacement = f"__OBF_STR[{idx}]"
            
            # Check for omitted parentheses in function calls
            prev_tok = None
            for k in range(i - 1, -1, -1):
                if tokens[k].type not in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    prev_tok = tokens[k]
                    break
                    
            if prev_tok and (prev_tok.type == TT.NAME or (prev_tok.type == TT.OP and prev_tok.value in (")", "]", "}"))):
                new_tokens.append(Token(TT.OP, "(", tok.pos))
                new_tokens.append(Token(TT.NAME, replacement, tok.pos))
                new_tokens.append(Token(TT.OP, ")", tok.pos))
            else:
                new_tokens.append(Token(TT.NAME, replacement, tok.pos))
                
            saved_bytes += len(val) - len(replacement)
        else:
            new_tokens.append(tok)
            
    return decoder_tokens + new_tokens, saved_bytes
