"""
VladgeMinifier - Variable Name Allocator

Responsible for generating and allocating the shortest possible names to local variables 
using a sorted slot-allocator algorithm. To maximize compression, variables that are 
referenced most frequently are prioritised for the shortest available names.
"""

from __future__ import annotations
from typing import Generator, List, Set
from .scope import Scope, VarInfo, collect_all_locals
from .lexer import LUA_KEYWORDS, SW_GLOBALS


def _name_gen() -> Generator[str, None, None]:
    """
    Generate sequential variable names prioritised by length.
    
    Yields names in the sequence: a, b, c...z, A, B...Z, _, then 
    aa, ab...zz, aA...zZ, then aaa...
    Lua keywords and standard Stormworks globals are automatically 
    filtered out at assignment time.
    
    Yields:
        str: The next shortest available variable name.
    """
    import string
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + "_"
    # Ensure single-character names are evaluated first. Digits cannot start an identifier.
    start_chars = string.ascii_lowercase + string.ascii_uppercase + "_"
    for c in start_chars:
        yield c
    # Generate multicharacter names (two characters or more)
    length = 2
    while True:
        def _gen_fixed(n: int):
            if n == 1:
                for c in start_chars:
                    yield c
                return
            for first in start_chars:
                for rest in _gen_fixed(n - 1):
                    yield first + rest
        for name in _gen_fixed(length):
            yield name
        length += 1


_FORBIDDEN: Set[str] = LUA_KEYWORDS | SW_GLOBALS


def _safe_names() -> Generator[str, None, None]:
    """
    Yield valid, non-forbidden Lua identifier names.
    
    Yields:
        str: A generated name that does not conflict with Lua keywords or Stormworks globals.
    """
    for name in _name_gen():
        if name not in _FORBIDDEN:
            yield name


def _obfuscated_names() -> Generator[str, None, None]:
    """
    Yield visually confusing names for the obfuscation mode.
    
    Generates names using visually similar characters ('I', 'l', 'O') to impede 
    reverse engineering and readability.
    
    Yields:
        str: The next obfuscated variable name.
    """
    chars = ['I', 'l', 'O']
    length = 1
    while True:
        def _gen_fixed(n: int):
            if n == 1:
                for c in chars: yield c
                return
            for first in chars:
                for rest in _gen_fixed(n - 1):
                    yield first + rest
        for name in _gen_fixed(length):
            if name not in _FORBIDDEN:
                yield name
        length += 1


class NameAllocator:
    """
    Assigns optimised short names to scoped variables.
    
    This uses a greedy slot-reuse strategy:
    1. Sort variables by usage frequency (most used variables get the shortest names).
    2. Within a specific scope, any names currently utilised by outer scopes are strictly off-limits.
    3. Names from sibling or non-overlapping scopes can be safely reused.
    """

    def __init__(self, obfuscate: bool = False):
        self._gen = _obfuscated_names() if obfuscate else _safe_names()
        self._pool: List[str] = []   # Reusable names returned from processed scopes
        self._issued: List[str] = [] # Complete history of all names ever generated

    def _next_name(self) -> str:
        if self._pool:
            return self._pool.pop(0)
        name = next(self._gen)
        self._issued.append(name)
        return name

    def _return_name(self, name: str):
        self._pool.insert(0, name)

    def assign_scope(self, scope: Scope, used_names: Set[str]) -> int:
        """
        Recursively assigns new names to all local variables within this scope and its children.
        
        Args:
            scope (Scope): The current scope to evaluate.
            used_names (Set[str]): Names currently in use by outer scopes.
            
        Returns:
            int: The total number of variables successfully renamed.
        """
        count = 0
        # Sort variables by use count descending to ensure the most frequently used get the shortest names
        vars_sorted = sorted(scope.locals.values(), key=lambda v: -v.use_count)

        locally_assigned: List[str] = []
        for vi in vars_sorted:
            # Determine an available name not currently in use by any outer or peer scope
            while True:
                name = self._next_name()
                if name not in used_names:
                    break
                locally_assigned.append(name)  # Temporarily block this name for the current scope evaluation

            vi.new_name = name
            used_names.add(name)
            locally_assigned.append(name)
            count += 1

        # Recursively process child scopes with a snapshot of the current used names
        for child in scope.children:
            count += self.assign_scope(child, used_names.copy())

        # Release locally-assigned names back into the pool so peer scopes can safely reuse them
        for name in locally_assigned:
            if name in used_names:
                used_names.discard(name)
            self._return_name(name)

        return count


def assign_names(root_scope: Scope, reserved_names: Set[str] = None, obfuscate: bool = False) -> int:
    """
    Orchestrate the assignment of the shortest possible names to all local variables 
    across the entire scope tree.
    
    Args:
        root_scope (Scope): The highest level scope in the script.
        reserved_names (Set[str], optional): Extra names to avoid renaming to. Defaults to None.
        obfuscate (bool): Whether to use visually confusing names instead of sequential short names.
        
    Returns:
        int: Total number of variables renamed.
    """
    if reserved_names is None:
        reserved_names = set()
        
    allocator = NameAllocator(obfuscate)
    # Initialize used_names with Stormworks globals, standard Lua keywords, and any explicitly reserved names
    used_names: Set[str] = set(_FORBIDDEN) | reserved_names
    return allocator.assign_scope(root_scope, used_names)
