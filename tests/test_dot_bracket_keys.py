"""Regression: dot vs bracket key renames and token_optimizer table-key packing."""

from src.core.minifier import minify
from src.core.lexer import tokenize, tokens_to_source
from src.core.passes.token_optimizer import optimize_tokens
from src.core.validate import validate_minified
from luaparser import ast


class TestDotVsBracketKeys:
    def test_mixed_dot_and_bracket_stay_consistent_l3(self):
        src = (
            "function onTick()\n"
            "  local t = {}\n"
            '  t["foo"] = 1\n'
            "  output.setNumber(1, t.foo)\n"
            "end\n"
        )
        result, stats = minify(src, level=3)
        assert stats.semantic_ok, stats.semantic_errors
        ast.parse(result)
        # Bracket write and dot read must use the same renamed key
        assert '["a"]' in result and ".a" in result
        assert "foo" not in result

    def test_mixed_dot_write_bracket_read_l3(self):
        src = (
            "function onTick()\n"
            "  local t = {}\n"
            "  t.foo = 1\n"
            '  output.setNumber(1, t["foo"])\n'
            "end\n"
        )
        result, stats = minify(src, level=3)
        assert stats.semantic_ok, stats.semantic_errors
        ast.parse(result)
        assert '["a"]' in result and ".a" in result
        assert "foo" not in result

    def test_l4_does_not_destroy_index_assign(self):
        src = (
            "function onTick()\n"
            "  local t = {}\n"
            '  t["foo"] = 1\n'
            '  output.setNumber(1, t["foo"])\n'
            "end\n"
        )
        result, stats = minify(src, level=4)
        assert stats.semantic_ok, stats.semantic_errors
        ast.parse(result)
        # Assignment must survive (not become bare `a;`)
        compact = result.replace(" ", "")
        assert "]=1" in compact or ".a=1" in compact or '["foo"]=1' in compact
        assert validate_minified(result) == []

    def test_token_optimizer_only_packs_constructor_keys(self):
        src = 'local t={["foo"]=1} t["bar"]=2'
        out, n = optimize_tokens(tokenize(src))
        text = tokens_to_source(out)
        # constructor packed
        assert "foo=" in text.replace(" ", "")
        # index assign NOT packed into tbar=
        assert "tbar" not in text.replace(" ", "")
        assert 't["bar"]' in text or "t['bar']" in text

    def test_constructor_string_key_still_packs(self):
        src = 'local t={["foo"]=1,["bar"]=2}'
        out, n = optimize_tokens(tokenize(src))
        text = tokens_to_source(out).replace(" ", "")
        assert '["foo"]' not in text
        assert "foo=1" in text and "bar=2" in text


class TestSelfFieldRename:
    """User report: self.prevErr stayed literal while { prevErr = 0 } renamed → nil."""

    PID = (
        "function makePID(p, i, d)\n"
        "  return {\n"
        "    p = p, i = i, d = d,\n"
        "    prevErr = 0, lastErr = 0, lastDer = 0, intg = 0,\n"
        "    step = function(self, sp, pv, dt)\n"
        "      dt = dt or 1\n"
        "      local err = sp - pv\n"
        "      local der = (err - self.prevErr) * 0.5\n"
        "      self.prevErr = self.lastErr\n"
        "      self.lastErr = err\n"
        "      self.lastDer = der\n"
        "      self.intg = self.intg + err * self.i * dt\n"
        "      return err * self.p * dt + self.intg + der * self.d * dt\n"
        "    end\n"
        "  }\n"
        "end\n"
        "function onTick()\n"
        "  local W = makePID(1, 0.1, 0.05)\n"
        "  output.setNumber(1, W:step(0, input.getNumber(1), 1))\n"
        "end\n"
    )

    def test_self_fields_rename_with_constructor_keys_l3(self):
        result, stats = minify(self.PID, level=3)
        assert stats.semantic_ok, stats.semantic_errors
        ast.parse(result)
        # Original field names must not survive as a mismatched mix
        assert ".prevErr" not in result
        assert "prevErr=" not in result.replace(" ", "")
        assert ".lastErr" not in result and ".intg" not in result

    def test_self_fields_rename_with_constructor_keys_l4(self):
        result, stats = minify(self.PID, level=4)
        assert stats.semantic_ok, stats.semantic_errors
        ast.parse(result)
        assert ".prevErr" not in result
        assert "prevErr=" not in result.replace(" ", "")

    def test_colon_method_self_fields_consistent(self):
        src = (
            "local T={}\n"
            "function T:new(x)\n"
            "  local o={prevErr=x or 0}\n"
            "  setmetatable(o, self)\n"
            "  self.__index = self\n"
            "  return o\n"
            "end\n"
            "function T:step()\n"
            "  self.prevErr = self.prevErr + 1\n"
            "  return self.prevErr\n"
            "end\n"
            "function onTick()\n"
            "  local a=T:new(input.getNumber(1))\n"
            "  output.setNumber(1, a:step())\n"
            "end\n"
        )
        result, stats = minify(src, level=3)
        assert stats.semantic_ok, stats.semantic_errors
        ast.parse(result)
        assert "__index" in result  # metamethod preserved
        assert ".prevErr" not in result
        assert "prevErr=" not in result.replace(" ", "")
