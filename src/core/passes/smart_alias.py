"""
Advanced API Aliasing (The "Macro-izer").
Dynamically evaluates cost/benefit of namespace aliasing (`s=screen`) 
vs full aliasing (`A=screen.drawRectF`) based on script usage.
"""

from typing import List, Tuple, Dict
from collections import Counter
from ..lexer import Token, TT

_NAMESPACES = {
    "screen", "math", "input", "output", "property", "table", "string", "map", "ui", "server", "matrix", "async", "http", "peer"
}

def _alias_name_gen():
    """Generate short alias names: _a, _b, ..., _z, _aa, ..."""
    import string
    chars = string.ascii_lowercase
    for c in chars:
        yield f"_{c}"
    for c1 in chars:
        for c2 in chars:
            yield f"_{c1}{c2}"

def smart_alias_globals(source: str) -> Tuple[str, int, Dict[str, str]]:
    """
    Evaluates and injects the most efficient aliases for a given script.
    """
    import re
    # Find all usages of NAMESPACE.METHOD
    pattern = r'\b(' + '|'.join(_NAMESPACES) + r')\.([a-zA-Z_0-9]+)\b'
    matches = re.findall(pattern, source)
    
    # occurrences: { ("screen", "drawRectF"): 10 }
    occurrences = Counter(matches)
    
    # Two possibilities to evaluate:
    # 1. Alias the namespace: e.g. `s=screen`
    # 2. Alias the full method: e.g. `A=screen.drawRectF`
    
    # A greedy approach evaluates the net character savings of aliasing a namespace.
    # Cost: len("s=screen ") = 9 chars
    # Savings: (len("screen") - len("s")) * number_of_uses = 5 * uses
    
    # Cost of full alias: len("A=screen.drawRectF ") = 19 chars
    # Savings: (len("screen.drawRectF") - len("A")) * uses = 15 * uses
    
    # Aliasing the namespace results in method calls like `s.drawRectF` (11 characters).
    # Aliasing the method directly results in `A` (1 character).
    
    # A combination like `s=screen A=s.drawRectF` provides additional savings.
    # To maintain simplicity, either the namespace OR the specific method is aliased, 
    # allowing a mix of both across the script.
    
    # Calculate the optimal alias map.
    alias_map = {}
    declarations = []
    
    # Count namespace uses
    ns_uses = Counter()
    for (ns, method), count in occurrences.items():
        ns_uses[ns] += count
        
    gen = _alias_name_gen()
    
    # Evaluate namespace aliasing.
    ns_aliases = {}
    ns_names = []
    ns_vals = []
    
    for ns, count in ns_uses.items():
        # Cost to declare `_a=screen`: 4 + len(ns)
        # Savings per use: len(ns) - 2 (since _a is 2 chars)
        alias = next(gen)
        # We group these later, so overhead is approx 1 comma (1 char) + length
        cost = len(alias) + len(ns) + 2
        savings = (len(ns) - len(alias)) * count
        if savings > cost + 1:
            ns_aliases[ns] = alias
            ns_names.append(alias)
            ns_vals.append(ns)
            
    # Evaluate if full method aliasing remains beneficial in addition to namespace aliasing
    meth_names = []
    meth_vals = []
    
    for (ns, method), count in occurrences.items():
        effective_ns = ns_aliases.get(ns, ns)
        full_call = f"{effective_ns}.{method}"
        
        alias = next(gen)
        cost = len(alias) + len(full_call) + 2
        savings = (len(full_call) - len(alias)) * count
        if savings > cost + 1:
            alias_map[f"{ns}.{method}"] = alias
            meth_names.append(alias)
            meth_vals.append(full_call)
        elif ns in ns_aliases:
            # Fallback to the namespace alias
            alias_map[f"{ns}.{method}"] = f"{ns_aliases[ns]}.{method}"
            
    if not ns_names and not meth_names:
        return source, 0, {}
        
    declarations = []
    if ns_names:
        declarations.append(f"local {','.join(ns_names)}={','.join(ns_vals)}")
    if meth_names:
        declarations.append(f"local {','.join(meth_names)}={','.join(meth_vals)}")

    # Single prefix block (Lifeboat-style) before script body
    decl_block = " ".join(declarations) + " " if declarations else ""
    new_source = source
    # Sort keys by length descending to prevent partial replacements (e.g. math.sin vs math.sinh)
    for orig, new in sorted(alias_map.items(), key=lambda x: -len(x[0])):
        if orig != new:
            # Word boundary replace
            new_source = re.sub(r'\b' + orig.replace('.', r'\.') + r'\b', new, new_source)

    new_source = decl_block + new_source
    
    return new_source, len(source) - len(new_source), alias_map
