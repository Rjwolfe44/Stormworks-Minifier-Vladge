"""Strip comments (both -- and --[[ ]]) from token stream."""
from typing import List
from ..lexer import Token, TT


def strip_comments(tokens: List[Token]) -> tuple[List[Token], int]:
    """Remove all comment tokens. Returns (new_tokens, count_removed)."""
    out = []
    removed = 0
    for tok in tokens:
        if tok.type in (TT.COMMENT, TT.LONGCOMMENT):
            removed += 1
        else:
            out.append(tok)
    return out, removed
