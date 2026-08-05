"""Tests for the variable renamer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.lexer import tokenize, TT, SW_GLOBALS
from src.core.renamer import assign_names, NameAllocator, _safe_names
from src.core.scope import build_scope_tree
from src.core.passes.rename_locals import rename_locals


class TestNameGenerator:
    def test_starts_with_single_chars(self):
        gen = _safe_names()
        names = [next(gen) for _ in range(10)]
        # First several should be single letters
        single = [n for n in names if len(n) == 1]
        assert len(single) > 0

    def test_no_keywords(self):
        gen = _safe_names()
        names = [next(gen) for _ in range(200)]
        from src.core.lexer import LUA_KEYWORDS
        for name in names:
            assert name not in LUA_KEYWORDS, f"Keyword {name!r} in name pool"

    def test_no_sw_globals(self):
        gen = _safe_names()
        names = set(next(gen) for _ in range(500))
        for name in names:
            assert name not in SW_GLOBALS, f"SW global {name!r} in name pool"

    def test_names_are_unique(self):
        gen = _safe_names()
        names = [next(gen) for _ in range(300)]
        assert len(names) == len(set(names))

    def test_names_shortest_first(self):
        gen = _safe_names()
        names = [next(gen) for _ in range(100)]
        lengths = [len(n) for n in names]
        # Should start short and get longer
        assert lengths[0] <= lengths[-1]


class TestScopeBuilder:
    def test_simple_locals(self):
        tokens = tokenize("local x = 1\nlocal y = 2")
        scope = build_scope_tree(tokens)
        assert "x" in scope.locals
        assert "y" in scope.locals

    def test_function_params(self):
        tokens = tokenize("function f(a, b, c)\nreturn a + b + c\nend")
        scope = build_scope_tree(tokens)
        # Params go into child scope (function scope)
        assert len(scope.children) == 1
        fn_scope = scope.children[0]
        assert "a" in fn_scope.locals
        assert "b" in fn_scope.locals
        assert "c" in fn_scope.locals

    def test_nested_scopes(self):
        src = """
local outer = 1
function inner()
    local x = 2
    do
        local y = 3
    end
end
"""
        tokens = tokenize(src)
        scope = build_scope_tree(tokens)
        assert "outer" in scope.locals
        assert len(scope.children) >= 1  # at least the function scope

    def test_for_loop_var(self):
        tokens = tokenize("for i = 1, 10 do local x = i end")
        scope = build_scope_tree(tokens)
        # i and x should be in child scopes
        child_locals = set()
        for child in scope.children:
            child_locals.update(child.locals.keys())
            for grandchild in child.children:
                child_locals.update(grandchild.locals.keys())
        assert "i" in child_locals


class TestRenameLocals:
    def test_basic_rename(self):
        src = "local myLongVariableName = 1\noutput.setNumber(1, myLongVariableName)"
        tokens = tokenize(src)
        new_tokens, count, name_map = rename_locals(tokens)
        result = "".join(t.value for t in new_tokens if t.type != TT.EOF)
        assert "myLongVariableName" not in result
        assert count >= 1

    def test_sw_globals_not_renamed(self):
        src = "output.setNumber(1, input.getNumber(1))"
        tokens = tokenize(src)
        new_tokens, count, name_map = rename_locals(tokens)
        result = "".join(t.value for t in new_tokens if t.type != TT.EOF)
        assert "output" in result
        assert "input" in result

    def test_ontick_not_renamed(self):
        src = "function onTick()\nlocal x = 1\nend"
        tokens = tokenize(src)
        new_tokens, count, name_map = rename_locals(tokens)
        result = "".join(t.value for t in new_tokens if t.type != TT.EOF)
        assert "onTick" in result

    def test_multiple_scopes_no_collision(self):
        """Variables in separate scopes can get the same short name safely."""
        src = """
function f1()
    local longName1 = 1
    return longName1
end
function f2()
    local longName2 = 2
    return longName2
end
"""
        tokens = tokenize(src)
        new_tokens, count, _ = rename_locals(tokens)
        result = "".join(t.value for t in new_tokens if t.type != TT.EOF)
        assert "longName1" not in result
        assert "longName2" not in result

    def test_consistent_renaming(self):
        """Same variable name maps to same short name throughout its scope."""
        src = "local total = 0\ntotal = total + 1\noutput.setNumber(1, total)"
        tokens = tokenize(src)
        new_tokens, count, name_map = rename_locals(tokens)
        result = "".join(t.value for t in new_tokens if t.type != TT.EOF)
        # 'total' should appear exactly 0 times (renamed throughout)
        assert "total" not in result
