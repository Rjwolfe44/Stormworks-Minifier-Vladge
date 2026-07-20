"""Tests for the core minifier."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.minifier import minify, CHAR_LIMIT


# ─── Fixtures ─────────────────────────────────────────────────────────────────
SIMPLE_LUA = """
-- This is a comment
local x = 1.0
local y = 0.5
local z = x + y
output.setNumber(1, z)
"""

FUNCTION_LUA = """
local function add(a, b)
    return a + b
end

local function mul(x, y)
    local result = x * y
    return result
end

local val = add(1, 2)
output.setNumber(1, mul(val, 3))
"""

STORMWORKS_TYPICAL = """
-- Stormworks microcontroller
local IN = input.getNumber
local IB = input.getBool
local ON = output.setNumber

local posX = IN(1)
local posY = IN(2)
local posZ = IN(3)
local armed = IB(1)

local speed = math.sqrt(posX^2 + posY^2 + posZ^2)

if armed then
    ON(1, speed)
    ON(2, posX)
else
    ON(1, 0)
    ON(2, 0)
end

function onTick()
    local tick = input.getNumber(4)
    output.setNumber(3, tick)
end
"""

NESTED_SCOPES = """
local outer = 100

function process(value)
    local scale = 2.0
    local scaled = value * scale
    for i = 1, 10 do
        local temp = scaled + i
        scaled = temp
    end
    return scaled
end

local result = process(outer)
"""


class TestLevel1_StripOnly:
    def test_removes_comments(self):
        result, stats = minify("-- comment\nlocal x = 1\n", level=1)
        assert "--" not in result
        assert "comment" not in result
        assert stats.comments_removed >= 1

    def test_removes_block_comments(self):
        result, stats = minify("--[[block\ncomment]]local x=1", level=1)
        assert "block" not in result
        assert "comment" not in result

    def test_collapses_whitespace(self):
        result, stats = minify("local    x    =    1", level=1)
        assert "    " not in result  # no multi-space

    def test_preserves_strings(self):
        result, stats = minify('local s = "hello world"', level=1)
        assert '"hello world"' in result

    def test_valid_after_strip(self):
        result, stats = minify(SIMPLE_LUA, level=1)
        assert "local" in result
        assert "output" in result
        assert stats.original_size > stats.final_size

    def test_number_optimisation(self):
        result, stats = minify("local x = 1.0\nlocal y = 0.5", level=1)
        assert "1.0" not in result
        assert "0.5" not in result
        assert " 1" in result or "=1" in result
        assert ".5" in result


class TestLevel2_Standard:
    def test_renames_locals(self):
        result, stats = minify(FUNCTION_LUA, level=2)
        assert stats.vars_renamed > 0
        # Long names should be gone or renamed
        assert len(result) < len(FUNCTION_LUA)

    def test_preserves_output(self):
        result, stats = minify(FUNCTION_LUA, level=2)
        # output.setNumber must remain intact
        assert "output" in result
        assert "setNumber" in result

    def test_preserves_on_tick(self):
        result, stats = minify(STORMWORKS_TYPICAL, level=2)
        assert "onTick" in result  # must never be renamed

    def test_preserves_input_output(self):
        result, stats = minify(STORMWORKS_TYPICAL, level=2)
        assert "input" in result
        assert "output" in result
        assert "math" in result

    def test_nested_scopes(self):
        result, stats = minify(NESTED_SCOPES, level=2)
        # Should rename locals but keep structure intact
        assert stats.vars_renamed > 0
        assert "function" in result  # keyword preserved

    def test_size_reduction(self):
        result, stats = minify(STORMWORKS_TYPICAL, level=2)
        assert stats.ratio > 20  # at least 20% reduction


class TestLevel3_Aggressive:
    def test_aliases_repeated_api(self):
        # input.getNumber called 6 times — should be aliased
        source = "\n".join([
            f"local v{i} = input.getNumber({i})"
            for i in range(1, 7)
        ])
        result, stats = minify(source, level=3)
        # After aliasing, "input.getNumber" should appear much less
        count = result.count("input.getNumber")
        assert count <= 1  # either gone or just in the alias decl

    def test_number_literals_optimised(self):
        result, stats = minify("local x=1.0 local y=0.50 local z=2.000", level=3)
        assert "1.0" not in result
        assert "0.50" not in result
        assert "2.000" not in result

    def test_better_than_level2(self):
        src = STORMWORKS_TYPICAL
        _, s2 = minify(src, level=2)
        _, s3 = minify(src, level=3)
        # Level 3 should be at least as good as level 2
        assert s3.final_size <= s2.final_size + 50  # small tolerance for alias overhead

    def test_stats_completeness(self):
        result, stats = minify(STORMWORKS_TYPICAL, level=3)
        assert stats.level == 3
        assert stats.level_name == "Aggressive"
        assert stats.elapsed_ms > 0
        assert stats.original_size > 0
        assert stats.final_size > 0


class TestLevel4_Ultimate:
    def test_deduplicates_strings(self):
        # Repeated string 5 times
        source = '\n'.join(['local x = "stormworks"'] * 5)
        result, stats = minify(source, level=4)
        # The string should appear far fewer times (aliased)
        count = result.count('"stormworks"')
        assert count <= 2  # at most in the alias decl + maybe 1

    def test_all_passes_run(self):
        result, stats = minify(STORMWORKS_TYPICAL, level=4)
        assert stats.comments_removed >= 0
        assert stats.level == 4


class TestEdgeCases:
    def test_empty_source(self):
        result, stats = minify("", level=3)
        assert result == ""
        assert stats.final_size == 0

    def test_only_comments(self):
        result, stats = minify("-- just a comment\n-- another", level=1)
        # Should result in essentially empty output
        assert len(result.strip()) == 0
        assert stats.comments_removed == 2

    def test_single_line(self):
        result, stats = minify("output.setNumber(1, 42)", level=3)
        assert "42" in result

    def test_multiline_strings_preserved(self):
        source = 'local s = [[hello\nworld\n!]]'
        result, stats = minify(source, level=3)
        assert "hello" in result
        assert "world" in result

    def test_char_limit_check(self):
        result, stats = minify("local x = 1", level=3)
        assert stats.under_limit  # tiny script is always under

    def test_hex_preserved(self):
        result, stats = minify("local c = 0xFF", level=3)
        assert "0xFF" in result or "0xff" in result.lower()

    def test_crlf_normalised(self):
        source = "local x = 1\r\nlocal y = 2\r\n"
        result, stats = minify(source, level=1)
        assert "\r\n" not in result

    def test_stats_ratio_correct(self):
        result, stats = minify(SIMPLE_LUA, level=3)
        expected_ratio = (stats.bytes_saved / stats.original_size) * 100
        assert abs(stats.ratio - expected_ratio) < 0.01

    def test_global_local_collision(self):
        source = (
            "function vecAdd(x, y, a)\n"
            "    return (x + y) * a\n"
            "end\n"
            "function vecSub(x, y, a)\n"
            "    return vecAdd(x, -y, a)\n"
            "end\n"
        )
        result, stats = minify(source, level=3)
        # Verify minified function structure.
        # Expected structure: function a(x, y, a_new) ... end function b(x, y, a_new) return a(x, -y, a_new) end
        # Verifies that function calls do not resolve to local parameter names.
        import re
        match = re.search(r"function\s+\w+\(\w+,\w+,(\w+)\)return\s+(\w+)\(", result)
        assert match is not None, f"Could not parse function in minified result: {result}"
        param_name, func_called = match.groups()
        assert func_called != param_name, f"Function call {func_called} incorrectly renamed to local param {param_name}!"


class TestWhitespaceSafety:
    def test_keyword_adjacent_name(self):
        """Ensure 'return x' doesn't become 'returnx'"""
        result, stats = minify("function f(x) return x end", level=1)
        assert "return" in result
        # After return there must be a space before the variable
        idx = result.index("return")
        after = result[idx + 6]
        assert after == " " or after == "("

    def test_not_keyword(self):
        result, stats = minify("if not x then end", level=1)
        assert "not" in result

    def test_and_or_keywords(self):
        result, stats = minify("local z = x and y or 0", level=1)
        assert "and" in result
        assert "or" in result

    def test_paren_then_name_gets_semicolon(self):
        """`)name` must not glue — Stormworks Lua rejects it."""
        src = "am(au,AA,az(m))\nai=ai+1"
        result, _ = minify(src, level=1)
        assert ")ai" not in result
        assert ");ai" in result or ")\nai" in result

    def test_call_then_call_gets_semicolon(self):
        src = "_v(1,B.a.x)\n_v(2,B.a.y)"
        result, _ = minify(src, level=1)
        assert ")_v" not in result
        assert ");_v" in result

    def test_name_then_name_gets_semicolon(self):
        """Space between bare names is not a statement separator."""
        src = "o.E=AB\nE[x]=AA"
        result, _ = minify(src, level=1)
        assert "AB E" not in result
        assert "AB;E" in result

    def test_and_call_then_assign_gets_semicolon(self):
        src = "aB=(f[ac]>0)and al(ac)\nf[ac]=0"
        result, _ = minify(src, level=1)
        assert ")f" not in result
        assert ");f" in result
        assert "and al" in result  # keyword spacing preserved

    def test_function_body_keyword_still_glues(self):
        """`)return` / `)end` are valid — do not force a semicolon before keywords."""
        result, _ = minify("local function f() return 1 end", level=1)
        assert ");return" not in result
        assert ")return" in result or ") return" in result
        assert ");end" not in result


