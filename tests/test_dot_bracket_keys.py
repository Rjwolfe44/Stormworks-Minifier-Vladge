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
