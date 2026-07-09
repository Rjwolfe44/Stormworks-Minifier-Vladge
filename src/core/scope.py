"""
VladgeMinifier - Lexical Scope Analysis

Constructs a hierarchical scope tree directly from the token stream. This module is 
essential for tracking local variable declarations, monitoring their lifecycles, and 
identifying safe opportunities for variable renaming without causing namespace collisions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from .lexer import Token, TT, SW_GLOBALS, LUA_KEYWORDS


@dataclass
class VarInfo:
    """
    Metadata capturing the lifecycle and usage statistics of a specific local variable declaration.
    """
    original_name: str
    new_name: str = ""
    declaration_idx: int = 0   # Token index where the variable is first declared
    last_use_idx: int = 0      # Token index of the variable's final reference
    use_count: int = 0         # Total number of times this variable is referenced
    is_param: bool = False     # Indicates if the variable is a function parameter
    scope: "Scope" = None      # Reference to the Scope instance where it was declared


@dataclass
class Scope:
    """
    Represents a discrete lexical scope block within the Lua code.
    This can represent the global scope, a function body, a do-block, a for-loop, etc.
    """
    parent: Optional["Scope"] = None
    children: List["Scope"] = field(default_factory=list)
    # Dictionary mapping original variable names to VarInfo strictly for variables declared in THIS scope
    locals: Dict[str, VarInfo] = field(default_factory=dict)
    # The inclusive token index range defining the boundaries of this specific scope block
    start_idx: int = 0
    end_idx: int = 0

    def declare(self, name: str, idx: int, is_param: bool = False) -> VarInfo:
        vi = VarInfo(
            original_name=name,
            declaration_idx=idx,
            last_use_idx=idx,
            use_count=0,
            is_param=is_param,
            scope=self,
        )
        self.locals[name] = vi
        return vi

    def lookup(self, name: str) -> Optional[VarInfo]:
        """
        Walk up the scope hierarchy chain to locate a declared local variable.
        
        Args:
            name (str): The original variable name to resolve.
            
        Returns:
            Optional[VarInfo]: The variable information if found, else None.
        """
        if name in self.locals:
            return self.locals[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def is_shadowed(self, name: str) -> bool:
        """
        Verify whether any immediate child scope declares a variable with the same name,
        which would inadvertently shadow this variable definition.
        
        Args:
            name (str): The variable name to check against.
            
        Returns:
            bool: True if shadowed by a child scope, False otherwise.
        """
        for child in self.children:
            if name in child.locals:
                return True
        return False


# ─── Keywords that open/close scopes ────────────────────────────────────────
_SCOPE_OPEN = frozenset({"do", "then", "repeat", "function"})
_SCOPE_CLOSE = frozenset({"end", "until"})


def build_scope_tree(tokens: List[Token]) -> Scope:
    """
    Perform a single-pass analysis over the token stream to build a complete scope hierarchy.
    
    Args:
        tokens (List[Token]): The complete sequence of lexed tokens to parse.
        
    Returns:
        Scope: The root (global) scope node containing the fully constructed tree.
    """
    root = Scope(parent=None, start_idx=0)
    current = root
    i = 0
    n = len(tokens)
    
    # Context stack is utilised to accurately distinguish table literal keys from standard assignments.
    # Context types: "TABLE" indicates table literal context ({}), "BLOCK" indicates standard code block (function/do).
    ctx_stack: List[str] = []
    # One-shot flags: after `for` opens a scope, its own `do` must not open a child.
    # Nested `while … do` / bare `do` inside that for must still open children.
    pending_for_do: List[bool] = []

    def push_ctx(ctx: str):
        ctx_stack.append(ctx)

    def pop_ctx(expected: str = None):
        if ctx_stack:
            # The 'expected' parameter is intentionally not strictly enforced to gracefully tolerate malformed or incomplete Lua code
            ctx_stack.pop()
    while i < n:
        tok = tokens[i]

        if tok.type == TT.EOF:
            break

        # ── Skip non-structural tokens ───────────────────────────────────
        if tok.type in (TT.COMMENT, TT.LONGCOMMENT, TT.SPACE,
                        TT.NEWLINE, TT.STRING, TT.LONGSTRING, TT.NUMBER):
            i += 1
            continue

        if tok.type == TT.KEYWORD:
            kw = tok.value

            # ── local [function] NAME ────────────────────────────────────
            if kw == "local":
                j = i + 1
                # skip whitespace
                while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                    j += 1
                if j < n and tokens[j].type == TT.KEYWORD and tokens[j].value == "function":
                    # Matched pattern: `local function NAME` -> Register NAME in the current scope immediately, then transition into a new child scope
                    j += 1
                    while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                        j += 1
                    if j < n and tokens[j].type == TT.NAME:
                        current.declare(tokens[j].value, j)
                        j += 1
                        
                    child = Scope(parent=current, start_idx=i)
                    current.children.append(child)
                    current = child
                    push_ctx("BLOCK")
                    
                    while j < n and not (tokens[j].type == TT.OP and tokens[j].value == "("):
                        if tokens[j].type == TT.KEYWORD and tokens[j].value in _SCOPE_CLOSE:
                            break
                        j += 1
                    if j < n and tokens[j].type == TT.OP and tokens[j].value == "(":
                        j += 1
                        while j < n and not (tokens[j].type == TT.OP and tokens[j].value == ")"):
                            if tokens[j].type == TT.NAME:
                                current.declare(tokens[j].value, j, is_param=True)
                            j += 1
                        j += 1
                    i = j
                    continue
                else:
                    # Matched pattern: `local NAME[, NAME ...] [= ...]`
                    while j < n:
                        while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                            j += 1
                        if j < n and tokens[j].type == TT.NAME:
                            current.declare(tokens[j].value, j)
                            j += 1
                        # comma → more names
                        while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                            j += 1
                        if j < n and tokens[j].type == TT.OP and tokens[j].value == ",":
                            j += 1
                        else:
                            break
                    i = j
                    continue

            elif kw == "function":
                child = Scope(parent=current, start_idx=i)
                current.children.append(child)
                current = child
                push_ctx("BLOCK")
                # Scan ahead to locate the parameter list opening '(' — skip past the function identifier (which may be a complex NAME.NAME:NAME path)
                j = i + 1
                # Skip whitespace and function name tokens to find '('
                while j < n and not (tokens[j].type == TT.OP and tokens[j].value == "("):
                    if tokens[j].type == TT.KEYWORD and tokens[j].value in _SCOPE_CLOSE:
                        break  # malformed, stop
                    j += 1
                if j < n and tokens[j].type == TT.OP and tokens[j].value == "(":
                    j += 1  # skip '('
                    # Collect params until ")"
                    while j < n and not (tokens[j].type == TT.OP and tokens[j].value == ")"):
                        if tokens[j].type == TT.NAME:
                            current.declare(tokens[j].value, j, is_param=True)
                        j += 1
                    j += 1  # consume ")"
                i = j
                continue

            # ── do / then / repeat ───────────────────────────────────────
            elif kw in ("do", "then", "repeat"):
                if kw == "do" and pending_for_do:
                    pending_for_do.pop()
                    # Scope already created by 'for' — consume only this for's do
                else:
                    child = Scope(parent=current, start_idx=i)
                    current.children.append(child)
                    current = child
                push_ctx("BLOCK")

            # ── elseif / else ────────────────────────────────────────────
            elif kw == "elseif":
                current.end_idx = i
                if current.parent:
                    current = current.parent
                pop_ctx()
                # The preceding 'then' keyword will be sequentially processed to construct the new execution block and push the context block
                
            elif kw == "else":
                current.end_idx = i
                if current.parent:
                    current = current.parent
                pop_ctx()
                
                child = Scope(parent=current, start_idx=i)
                current.children.append(child)
                current = child
                push_ctx("BLOCK")

            # ── for ... in / for i=... ───────────────────────────────────
            elif kw == "for":
                child = Scope(parent=current, start_idx=i)
                current.children.append(child)
                current = child
                pending_for_do.append(True)
                j = i + 1
                # Collect loop variable names until "in" or "="
                while j < n:
                    while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                        j += 1
                    if j < n and tokens[j].type == TT.NAME:
                        current.declare(tokens[j].value, j, is_param=True)
                        j += 1
                    while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                        j += 1
                    if j < n and tokens[j].type == TT.OP and tokens[j].value == ",":
                        j += 1
                        continue
                    break  # hit "in" or "="
                i = j
                continue

            # ── end / until (close scope) ────────────────────────────────
            elif kw in ("end", "until"):
                current.end_idx = i
                if current.parent:
                    current = current.parent
                pop_ctx()

        # ── Table tracking ───────────────────────────────────────────────
        elif tok.type == TT.OP:
            if tok.value == "{":
                push_ctx("TABLE")
            elif tok.value == "}":
                if ctx_stack and ctx_stack[-1] == "TABLE":
                    pop_ctx()

        # ── Reference tracking — record uses of local vars ───────────────
        elif tok.type == TT.NAME:
            # Check if it's a property access (preceded by . or :)
            is_prop = False
            prev_i = i - 1
            while prev_i >= 0 and tokens[prev_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                prev_i -= 1
            if prev_i >= 0 and tokens[prev_i].type == TT.OP and tokens[prev_i].value in (".", ":"):
                is_prop = True

            # Check if it's a table key (inside TABLE, followed by =)
            is_key = False
            if not is_prop and ctx_stack and ctx_stack[-1] == "TABLE":
                next_i = i + 1
                while next_i < n and tokens[next_i].type in (TT.SPACE, TT.NEWLINE, TT.COMMENT, TT.LONGCOMMENT):
                    next_i += 1
                if next_i < n and tokens[next_i].type == TT.OP and tokens[next_i].value == "=":
                    is_key = True

            if not is_prop and not is_key and not tok.is_global:
                vi = current.lookup(tok.value)
                if vi is not None:
                    vi.last_use_idx = i
                    vi.use_count += 1

        i += 1

    root.end_idx = n
    return root


def collect_all_locals(scope: Scope) -> List[VarInfo]:
    """
    Recursively traverse and flatten all VarInfo objects from the provided scope tree into a single list.
    
    Args:
        scope (Scope): The top-level root scope to begin collection.
        
    Returns:
        List[VarInfo]: A flattened list containing all local variables defined within the tree.
    """
    result = list(scope.locals.values())
    for child in scope.children:
        result.extend(collect_all_locals(child))
    return result
