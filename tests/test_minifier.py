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
        match = re.search(r"function\s+\w+\(\w+,\w+,(\w+)\);?return\s+(\w+)\(", result)
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

    def test_paren_before_stmt_keywords_glues(self):
        """`)local` / `)if` / `)for` glue cleanly — Lua starts a new statement there."""
        cases = [
            "f()\nlocal x=1",
            "f()\nif x then end",
            "f()\nfor i=1,2 do end",
            "ag()\nfor B=1,P do end",
            "b[h]\nlocal m=1",
            "M[E][X]\nif not D then end",
        ]
        for src in cases:
            result, _ = minify(src, level=1)
            # no wasted ';' before statement keywords after ')' / ']'
            assert ");local" not in result, f"{src!r} => {result!r}"
            assert ");if" not in result
            assert ");for" not in result
            assert "];local" not in result
            assert "];if" not in result

    def test_paren_before_name_gets_semicolon(self):
        """`)name` is still a hard statement break — a space is not enough."""
        result, _ = minify("local x=f()\ng=1", level=1)
        assert ");g" in result or ";g" in result
        assert ")g" not in result

    def test_if_then_not_broken_by_semicolon(self):
        """`if(x)then` must not become `if(x);then`."""
        result, _ = minify("if(x)then y=1 end", level=1)
        assert ");then" not in result
        assert ")then" in result or ") then" in result

    def test_nil_true_false_before_name_gets_semicolon(self):
        """`nil a` / `false x` need ';' — a space is still a hard syntax error."""
        result, _ = minify("AA,AB,AC=true,false,nil\naH,aa=math.pi,math.pi*2", level=1)
        assert "nil aH" not in result
        assert "nil;aH" in result
        result2, _ = minify("local x=false\ny=1", level=1)
        assert "false y" not in result2 and "false;y" in result2

    def test_pcall_unwrapped_for_stormworks(self):
        src = 'useDiscrete=true\npcall(function() useDiscrete=property.getBool("Discrete Denoise") end)'
        result, _ = minify(src, level=1)
        assert "pcall" not in result
        assert "property.getBool" in result
        assert "useDiscrete" in result

    def test_elseif_preserved_and_binds_correctly(self):
        """Trailing else must stay sibling to the elseif chain, not rebind inward."""
        src = (
            "if not active then\n"
            "  ping=0\n"
            "elseif ping>0 then\n"
            "  ping=ping+1\n"
            "  if ping>=lim then\n"
            "    ping=0\n"
            "  end\n"
            "else\n"
            "  idle=true\n"
            "end\n"
        )
        result, _ = minify(src, level=1)
        # elseif stays (shorter than else-if-end); structure must be preserved
        assert "elseif" in result
        assert "idle=true" in result.replace(" ", "")
        import re
        # else must NOT bind to the inner `if ping>=lim` — it follows the inner `end`
        assert not re.search(r"ping>=lim then[^e]*else idle", result.replace(" ", ""))
        assert "else" in result


    def test_elseif_contact_pattern_binds_correctly(self):
        src = (
            "if abs(az)+abs(el)>0 then\n"
            "  if not hit and ping>6 then\n"
            "    if rng>20 then save() end\n"
            "  elseif hit and useDiscrete then\n"
            "    denoise()\n"
            "  end\n"
            "end\n"
        )
        result, _ = minify(src, level=1)
        # elseif survives and stays bound to `if not hit...` under the outer if
        assert "elseif" in result
        assert "denoise" in result
        assert result.count("end") == 3



