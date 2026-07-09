"""Tests for the Lua lexer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.lexer import tokenize, TT, Token


def tok_types(source: str):
    return [t.type for t in tokenize(source) if t.type != TT.EOF]


def tok_vals(source: str):
    return [(t.type, t.value) for t in tokenize(source) if t.type != TT.EOF]


class TestKeywords:
    def test_basic_keywords(self):
        tokens = tokenize("local function end if then else")
        kw = [t for t in tokens if t.type == TT.KEYWORD]
        assert [t.value for t in kw] == ["local", "function", "end", "if", "then", "else"]

    def test_name_vs_keyword(self):
        tokens = tokenize("local myVar do")
        types = [(t.type, t.value) for t in tokens if t.type != TT.SPACE]
        assert (TT.KEYWORD, "local") in types
        assert (TT.NAME, "myVar") in types
        assert (TT.KEYWORD, "do") in types


class TestStrings:
    def test_double_quoted(self):
        toks = [t for t in tokenize('"hello world"') if t.type != TT.EOF]
        assert toks[0].type == TT.STRING
        assert toks[0].value == '"hello world"'

    def test_single_quoted(self):
        toks = [t for t in tokenize("'test'") if t.type != TT.EOF]
        assert toks[0].type == TT.STRING

    def test_escaped_quote(self):
        toks = [t for t in tokenize(r'"say \"hi\""') if t.type != TT.EOF]
        assert toks[0].type == TT.STRING

    def test_long_string(self):
        toks = [t for t in tokenize("[[hello\nworld]]") if t.type != TT.EOF]
        assert toks[0].type == TT.LONGSTRING

    def test_long_string_eq(self):
        toks = [t for t in tokenize("[==[test]==]") if t.type != TT.EOF]
        assert toks[0].type == TT.LONGSTRING


class TestNumbers:
    def test_integer(self):
        toks = [t for t in tokenize("42") if t.type != TT.EOF]
        assert toks[0].type == TT.NUMBER
        assert toks[0].value == "42"

    def test_float(self):
        toks = [t for t in tokenize("3.14") if t.type != TT.EOF]
        assert toks[0].type == TT.NUMBER

    def test_sci_notation(self):
        toks = [t for t in tokenize("1e-5") if t.type != TT.EOF]
        assert toks[0].type == TT.NUMBER

    def test_hex(self):
        toks = [t for t in tokenize("0xFF") if t.type != TT.EOF]
        assert toks[0].type == TT.NUMBER

    def test_leading_dot(self):
        toks = [t for t in tokenize(".5") if t.type != TT.EOF]
        assert toks[0].type == TT.NUMBER


class TestComments:
    def test_line_comment(self):
        toks = tokenize("-- this is a comment\nlocal x")
        comments = [t for t in toks if t.type == TT.COMMENT]
        assert len(comments) == 1
        assert "comment" in comments[0].value

    def test_block_comment(self):
        toks = tokenize("--[[ block\ncomment ]]")
        long_cmts = [t for t in toks if t.type == TT.LONGCOMMENT]
        assert len(long_cmts) == 1

    def test_comment_not_in_string(self):
        toks = tokenize('"-- not a comment"')
        comments = [t for t in toks if t.type == TT.COMMENT]
        assert len(comments) == 0


class TestOperators:
    def test_two_char_ops(self):
        source = "== ~= <= >= .. ::"
        toks = [t for t in tokenize(source) if t.type == TT.OP]
        assert "==" in [t.value for t in toks]
        assert "~=" in [t.value for t in toks]
        assert ".." in [t.value for t in toks]

    def test_three_char_op(self):
        toks = [t for t in tokenize("...") if t.type == TT.OP]
        assert toks[0].value == "..."

    def test_one_char_ops(self):
        source = "+ - * / % ^ # & | ~"
        toks = [t for t in tokenize(source) if t.type == TT.OP]
        assert len(toks) == 10


class TestWhitespace:
    def test_spaces_and_tabs(self):
        toks = tokenize("  \t  ")
        spaces = [t for t in toks if t.type == TT.SPACE]
        assert len(spaces) == 1

    def test_newlines(self):
        toks = tokenize("a\nb\nc")
        newlines = [t for t in toks if t.type == TT.NEWLINE]
        assert len(newlines) == 2

    def test_crlf(self):
        toks = tokenize("a\r\nb")
        newlines = [t for t in toks if t.type == TT.NEWLINE]
        assert len(newlines) == 1


class TestComplexLua:
    def test_function_definition(self):
        source = "function add(a, b) return a + b end"
        toks = [t for t in tokenize(source) if t.type not in (TT.SPACE, TT.EOF)]
        keywords = [t.value for t in toks if t.type == TT.KEYWORD]
        assert "function" in keywords
        assert "return" in keywords
        assert "end" in keywords

    def test_table_constructor(self):
        source = "local t = {x=1, y=2.5, z=.5}"
        toks = tokenize(source)
        nums = [t.value for t in toks if t.type == TT.NUMBER]
        assert "1" in nums
        assert "2.5" in nums
        assert ".5" in nums

    def test_method_call(self):
        source = "screen.drawRect(0, 0, 100, 100)"
        toks = [t for t in tokenize(source) if t.type not in (TT.SPACE, TT.NEWLINE, TT.EOF)]
        names = [t.value for t in toks if t.type == TT.NAME]
        assert "screen" in names
        assert "drawRect" in names

    def test_stormworks_typical(self):
        source = """
local x = input.getNumber(1)
local y = input.getNumber(2)
output.setNumber(1, x + y)
"""
        toks = tokenize(source)
        names = [t.value for t in toks if t.type == TT.NAME]
        assert "input" in names
        assert "output" in names
        assert "getNumber" in names
        assert "setNumber" in names
