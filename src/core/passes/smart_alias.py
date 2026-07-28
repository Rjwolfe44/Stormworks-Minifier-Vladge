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
        
    # Greedy-optimal per-namespace decision. For each namespace we choose the plan
    # with the highest net savings among:
    #   A) alias namespace once, route every method through it  (ns.drawRectF)
    #   B) fully alias the hot methods to bare names, rest via namespace (drawRectF -> A)
    #   C) no namespace alias; fully alias only methods worth it
    gen = _alias_name_gen()

    # group methods by namespace
    by_ns: Dict[str, list] = {}
    for (ns, method), count in occurrences.items():
        by_ns.setdefault(ns, []).append((method, count))

    ns_names: List[str] = []
    ns_vals: List[str] = []
    meth_names: List[str] = []
    meth_vals: List[str] = []

    for ns, meths in by_ns.items():
        total_uses = sum(c for _, c in meths)
        # reserve a candidate namespace alias name (peek, commit only if used)
        ns_alias = next(gen)

        # Plan A cost/benefit: alias the namespace itself
        ns_cost = len(ns_alias) + len(ns) + 2
        ns_save = (len(ns) - len(ns_alias)) * total_uses
        use_ns = ns_save > ns_cost + 1

        effective_ns = ns_alias if use_ns else ns

        # Decide each method: full-alias (bare) vs route through effective_ns.
        plan_meth = []   # (orig, alias)
        plan_route = []  # orig routed via namespace
        net_gain = 0
        for method, count in meths:
            full_call = f"{effective_ns}.{method}"
            m_alias = next(gen)
            m_cost = len(m_alias) + len(full_call) + 2
            m_save = (len(full_call) - len(m_alias)) * count
            if m_save > m_cost + 1:
                plan_meth.append((f"{ns}.{method}", m_alias, full_call))
                net_gain += m_save - m_cost
            else:
                plan_route.append(f"{ns}.{method}")

        if use_ns:
            ns_names.append(ns_alias)
            ns_vals.append(ns)
            for orig in plan_route:
                alias_map[orig] = f"{ns_alias}.{orig.split('.', 1)[1]}"
        for orig, m_alias, full_call in plan_meth:
            alias_map[orig] = m_alias
            meth_names.append(m_alias)
            meth_vals.append(full_call)

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
