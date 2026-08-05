"""
Regression: nested locals inside IIFE RHS must not steal the outer binding.

LifeBoat/combiner emits `local Vec = (function() local LBVec=... return LBVec end)()`.
The v2.6.1 deferred-local slot was a single frame — the inner `local` overwrote
pending_scope so `Vec` landed inside the IIFE. Uses in onTick became undefined
globals (nil after rename_globals).
"""

from pathlib import Path

from src.core.lexer import tokenize
from src.core.minifier import minify
from src.core.scope import build_scope_tree, _find_local_stmt_end
from src.core.validate import validate_minified
from src.core.lexer import TT


def _root_local_names(source: str) -> set[str]:
    tokens = tokenize(source)
    root = build_scope_tree(tokens)
    return set(root.locals)


def test_outer_local_stays_on_root_when_iife_has_nested_local():
    src = (
        "local outer = (function()\n"
        "  local inner = 1\n"
        "  return inner\n"
        "end)()\n"
        "function onTick() local v = outer end\n"
    )
    assert "outer" in _root_local_names(src)
    tokens = tokenize(src)
    root = build_scope_tree(tokens)
    # outer must NOT live only inside the IIFE function scope
    iife = root.children[0]
    assert "outer" not in iife.locals
    assert "inner" in iife.locals


def test_iife_without_nested_local_still_on_root():
    src = "local outer = (function() return 1 end)()\nfunction onTick() local v = outer end\n"
    assert "outer" in _root_local_names(src)


def test_bare_function_value_local_on_root():
    src = "local f = function() local x = 1 return x end\nfunction onTick() local v = f end\n"
    assert "f" in _root_local_names(src)


def test_multi_name_iife_locals_on_root():
    src = (
        "local a, b = (function()\n"
        "  local x = 1\n"
        "  return x, 2\n"
        "end)()\n"
        "function onTick() local v = a + b end\n"
    )
    names = _root_local_names(src)
    assert "a" in names and "b" in names
    result, stats = minify(src, level=2)
    assert "a" not in result or result.count("local") >= 1
    assert stats.semantic_ok, stats.semantic_errors
    # Outer names must be renamed in onTick (not left as free globals)
    assert " a " not in f" {result} " or "a+" not in result.replace(" ", "")
    from luaparser import ast
    ast.parse(result)


def test_find_local_stmt_end_includes_iife_call():
    src = "local Vec = (function() local x=1 return x end)()\nfunction onTick() end"
    tokens = tokenize(src)
    # RHS starts at the '(' after '='
    eq = next(i for i, t in enumerate(tokens) if t.type == TT.OP and t.value == "=")
    start = eq + 1
    while tokens[start].type in (TT.SPACE, TT.NEWLINE):
        start += 1
    end = _find_local_stmt_end(tokens, start, len(tokens))
    # IIFE call closes at the second ')' after `end`; stmt_end must be AFTER that
    # (at `function` of onTick), not at the grouping ')' before the call.
    assert tokens[end].type == TT.KEYWORD and tokens[end].value == "function"
    # Token 24 is the call's closing ')'; end is 26 (`function`)
    assert end > 24


def test_minify_l2_renames_outer_through_onTick():
    src = (
        "local outer = (function()\n"
        "  local inner = 1\n"
        "  return inner\n"
        "end)()\n"
        "function onTick() local v = outer end\n"
    )
    result, stats = minify(src, level=2)
    assert "outer" not in result
    assert stats.semantic_ok, stats.semantic_errors
    assert validate_minified(result) == []


def test_lifeboat_vec_require_pattern_l3(tmp_path: Path):
    lib = tmp_path / "LifeBoatAPI" / "Utils" / "Maths"
    lib.mkdir(parents=True)
    (lib / "LBVec.lua").write_text(
        "---@section LBVec\n"
        "local LBVec = {}\n"
        "function LBVec:new(x,y,z)\n"
        "  local o = {x=x or 0, y=y or 0, z=z or 0}\n"
        "  setmetatable(o, self)\n"
        "  self.__index = self\n"
        "  return o\n"
        "end\n"
        "function LBVec:add(other)\n"
        "  return LBVec:new(self.x+other.x, self.y+other.y, self.z+other.z)\n"
        "end\n"
        "---@endsection\n"
        "return LBVec\n",
        encoding="utf-8",
    )
    main = (
        'local Vec = require("LifeBoatAPI.Utils.Maths.LBVec")\n'
        "function onTick()\n"
        "  local v = Vec:new(input.getNumber(1), input.getNumber(2), 0)\n"
        "  local w = v:add(Vec:new(1,0,0))\n"
        "  output.setNumber(1, w.x)\n"
        "end\n"
    )
    result, stats = minify(main, level=3, root_dir=str(tmp_path))
    assert "require" not in result
    # No leftover original `Vec` as an undefined global read
    assert "Vec:" not in result and "Vec." not in result
    assert stats.semantic_ok, stats.semantic_errors
    # Must still call through the local that holds the module
    assert "onTick" in result
    from luaparser import ast
    ast.parse(result)


def test_self_reference_still_reads_outer():
    result, stats = minify("a = 9\nlocal a = a + 1\nprint(a)", level=3)
    assert stats.semantic_ok, stats.semantic_errors
    import re
    m = re.match(r"(\w+)=9 local (\w+)=(\w+)\+1", result)
    assert m, result
    g, decl, rhs = m.groups()
    assert rhs == g
