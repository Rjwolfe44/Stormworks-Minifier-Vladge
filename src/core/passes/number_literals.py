"""Number literal optimisation pass."""
import re
from typing import List
from ..lexer import Token, TT


_FLOAT_RE = re.compile(r'^(\d+)\.0+$')
_LEAD_ZERO = re.compile(r'^0(\.\d+)$')
_TRAIL_ZERO = re.compile(r'^(\d+\.\d*?)0+$')


def _optimise_number(s: str) -> str:
    """
    Shorten a number literal:
      1.0    → 1
      0.5    → .5
      1.500  → 1.5
      0x...  → unchanged (hex)
    """
    if s.startswith('0x') or s.startswith('0X'):
        return s  # hex — leave alone

    # 1.500 → 1.5 (DO THIS FIRST SO DECIMALS HAVE NO TRAILING ZEROS)
    m = _TRAIL_ZERO.match(s)
    if m:
        result = m.group(1).rstrip('.')
        if result.endswith('.'):
            result = result[:-1]
        s = result if result else s

    # E-Notation crunching for trailing zeros
    # 10000 -> 1e4 (saves 2)
    # 15000 -> 15e3 (saves 1)
    if not '.' in s:
        m = re.match(r'^([1-9]\d*?)(000+)$', s)
        if m:
            base = m.group(1)
            zeros = m.group(2)
            e_format = f"{base}e{len(zeros)}"
            if len(e_format) < len(s):
                return e_format

    # E-Notation crunching for small decimals
    # 0.0001 -> 1e-4 (saves 2)
    # 0.00005 -> 5e-5 (saves 3)
    match = re.match(r'^0\.(0+)([1-9]\d*)$', s)
    if match:
        zeros = match.group(1)
        digits = match.group(2)
        exponent = len(zeros) + len(digits)
        e_format = f"{digits}e-{exponent}"
        
        # We must compare against the optimized float length (e.g. .0001 is 5 chars, 1e-4 is 4 chars)
        optimized_float_len = len(s) - 1 # subtracting leading 0
        if len(e_format) < optimized_float_len:
            return e_format

    # 1.0 -> 1
    m = _FLOAT_RE.match(s)
    if m:
        return m.group(1)

    # 0.5 -> .5
    m = _LEAD_ZERO.match(s)
    if m:
        return m.group(1)

    return s


def optimise_numbers(tokens: List[Token]) -> tuple[List[Token], int]:
    """Optimise number literals in-place. Returns (tokens, chars_saved)."""
    saved = 0
    new_tokens = []
    for tok in tokens:
        if tok.type == TT.NUMBER:
            opt = _optimise_number(tok.value)
            saved += len(tok.value) - len(opt)
            new_tokens.append(Token(TT.NUMBER, opt, tok.pos))
        else:
            new_tokens.append(tok)
    return new_tokens, saved
